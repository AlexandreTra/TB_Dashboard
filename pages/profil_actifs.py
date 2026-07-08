"""
Profil Intrinsèque des Actifs — page autonome, indépendante des stratégies.

Objectif : caractériser la nature statistique de chaque actif sur les prix bruts,
pour expliquer a priori pourquoi une famille de stratégie (Trend Following, Mean
Reversion, Breakout) devrait convenir ou non.

Source de données : TB-MT5/*_M15_MT5.csv (format chronologique MT5, YYYY.MM.DD HH:MM).
Tous les timeframes (H1, H4, D1) sont obtenus par rééchantillonnage depuis le M15.
Période : 2015-01-01 à 2025-12-31.

⚠️ PLATINUM : données M15 très éparses (~38 % de barres normales, gap médian 45 min).
   Les statistiques sont calculées mais à interpréter avec prudence sur ce symbole.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import scipy.stats as sp_stats
import streamlit as st

from config import TB_MT5_DIR
from config_analyse import ASSET_LABELS as _CFG_ASSET_LABELS, ROBOT_FAMILY
from core.constants import GLOBAL_CSS, PLOTLY_DARK
from core.ui_helpers import chart_badge, st_plotly

try:
    from statsmodels.tsa.stattools import adfuller as _adfuller
    _HAS_STATSMODELS = True
except ImportError:
    _HAS_STATSMODELS = False


# ── Chemin données MT5 ────────────────────────────────────────────────────────
_TB_MT5 = TB_MT5_DIR
_START = "2015-01-01"
_END   = "2025-12-31"

ASSETS: dict[str, str] = {   # actif_clean → code fichier _M15_MT5.csv
    "BRENT":      "XBZ",
    "NATURALGAS": "NG",
    "GOLD":       "GC",
    "PLATINUM":   "PL",
    "COFFEE":     "KC",
    "COCOA":      "CC",
}

TIMEFRAMES   = ["H1", "H4", "D1"]
_FREQ_MAP    = {"H1": "1h", "H4": "4h", "D1": "1D"}
_MONTH_NAMES = ["Jan", "Fév", "Mar", "Avr", "Mai", "Jun",
                "Jul", "Aoû", "Sep", "Oct", "Nov", "Déc"]

# Platinum est connu comme épars — seuil minimal pour signalement
_SPARSE_ASSETS = {"PLATINUM"}
_MIN_BARS_RELIABLE = 500  # en dessous : statistiques peu fiables

# ── Chargement ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=86_400, show_spinner=False)
def _load_m15(code: str) -> pd.DataFrame:
    """
    Charge *_M15_MT5.csv depuis TB-MT5/.
    Format détecté Step 0 : <DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<TICKVOL>,<VOL>,<SPREAD>
    Date YYYY.MM.DD, Time HH:MM, ordre chronologique ascendant.
    """
    path = _TB_MT5 / f"{code}_M15_MT5.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(
        path, header=0,
        usecols=[0, 1, 2, 3, 4, 5],
        names=["Date", "Time", "Open", "High", "Low", "Close"],
        skiprows=1, dtype=str,
    )
    df["Datetime"] = pd.to_datetime(
        df["Date"] + " " + df["Time"], format="%Y.%m.%d %H:%M", errors="coerce"
    )
    for c in ("Open", "High", "Low", "Close"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = (
        df.dropna(subset=["Datetime", "Close"])
        .sort_values("Datetime")
        .set_index("Datetime")[["Open", "High", "Low", "Close"]]
    )
    return df


def _resample(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    return df.resample(freq).agg(
        Open=("Open", "first"),
        High=("High", "max"),
        Low=("Low", "min"),
        Close=("Close", "last"),
    ).dropna(subset=["Close"])


# ── Calculs métriques ─────────────────────────────────────────────────────────
def _hurst(log_prices: np.ndarray, n_lags: int = 50) -> float:
    """
    Exposant de Hurst par la méthode des variances de différences.
    std(X(t+k) − X(t)) ~ k^H → pente du log-log = H.
    Appliqué sur log-prix (non log-rendements).
    H > 0.5 : persistant/tendanciel
    H ≈ 0.5 : marche aléatoire
    H < 0.5 : retour à la moyenne
    """
    n = len(log_prices)
    max_lag = min(n // 4, 2000)
    if max_lag < 20:
        return float("nan")
    lags = np.unique(np.logspace(1, np.log10(max_lag), n_lags).astype(int))
    tau  = np.array([np.std(log_prices[lag:] - log_prices[:-lag]) for lag in lags])
    valid = tau > 0
    if valid.sum() < 5:
        return float("nan")
    slope, *_ = np.polyfit(np.log(lags[valid]), np.log(tau[valid]), 1)
    return float(slope)


def _adx_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    ADX(14) via Wilder EWM (alpha=1/period, adjust=False).
    Approximation acceptable pour l'analyse de tendance sur longue série.
    """
    h = df["High"].astype(float)
    lo = df["Low"].astype(float)
    c  = df["Close"].astype(float)

    tr = pd.concat([h - lo, (h - c.shift(1)).abs(), (lo - c.shift(1)).abs()], axis=1).max(axis=1)
    up   = h - h.shift(1)
    down = lo.shift(1) - lo
    pdm  = pd.Series(np.where((up > down) & (up > 0), up, 0.0),   index=df.index, dtype=float)
    mdm  = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index, dtype=float)

    α   = 1.0 / period
    atr = tr.ewm(alpha=α, adjust=False).mean()
    pdi = 100 * pdm.ewm(alpha=α, adjust=False).mean() / atr.replace(0, np.nan)
    mdi = 100 * mdm.ewm(alpha=α, adjust=False).mean() / atr.replace(0, np.nan)
    dx  = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=α, adjust=False).mean().fillna(0.0)


def _seasonality(log_ret: pd.Series) -> dict:
    """Saisonnalité mensuelle sur rendements log journaliers (D1)."""
    months  = log_ret.index.month
    monthly = log_ret.groupby(months).mean() * 100   # → %
    grand   = log_ret.mean()
    ss_tot  = ((log_ret - grand) ** 2).sum()
    groups  = [log_ret[months == m].values for m in range(1, 13)]
    ss_btwn = sum(len(g) * (g.mean() - grand) ** 2 for g in groups if len(g) > 0)
    r2      = ss_btwn / ss_tot if ss_tot > 0 else float("nan")
    try:
        valid_g = [g for g in groups if len(g) >= 3]
        _, anova_p = sp_stats.f_oneway(*valid_g)
    except Exception:
        anova_p = float("nan")
    return {"monthly": monthly, "r2": r2, "anova_p": anova_p}


# ── Calcul principal (mis en cache) ──────────────────────────────────────────
@st.cache_data(ttl=86_400, show_spinner=False)
def _build_profiles() -> tuple[pd.DataFrame, dict]:
    """
    Calcule toutes les métriques pour 6 actifs × 3 TF.
    Retourne (df_metrics, seas_dict).
    Période basée sur les données disponibles dans la plage 2015-2025.
    """
    rows: list[dict] = []
    seas: dict[str, dict] = {}

    for asset, code in ASSETS.items():
        m15_raw = _load_m15(code)
        if m15_raw.empty:
            continue
        m15_raw = m15_raw.loc[_START:_END]
        if m15_raw.empty:
            continue

        for tf in TIMEFRAMES:
            df = _resample(m15_raw, _FREQ_MAP[tf]).dropna()
            n  = len(df)
            if n < 20:
                continue

            close   = df["Close"]
            log_ret = np.log(close / close.shift(1)).dropna()
            log_px  = np.log(close.values)
            n_ret   = len(log_ret)

            reliable = (n_ret >= _MIN_BARS_RELIABLE)

            # ── 1. Volatilité annualisée ──────────────────────────────────────
            gaps      = df.index.to_series().diff().dropna()
            med_gap_s = gaps.median().total_seconds()
            bars_yr   = (365.25 * 86400) / med_gap_s if med_gap_s > 0 else 252
            vol_ann   = log_ret.std() * np.sqrt(bars_yr) * 100   # en %

            # ── 2. Exposant de Hurst ──────────────────────────────────────────
            h = _hurst(log_px) if reliable else float("nan")

            # ── 3. Test ADF (statsmodels adfuller sur niveaux de prix) ────────
            if _HAS_STATSMODELS and reliable:
                try:
                    ml = max(1, int(np.sqrt(n_ret)))
                    adf_pval = float(_adfuller(close.values, maxlag=ml, autolag=None)[1])
                except Exception:
                    adf_pval = float("nan")
            else:
                adf_pval = float("nan")

            # ── 4. Autocorrélation lag 1 des rendements log ───────────────────
            autocorr = float(log_ret.autocorr(lag=1)) if n_ret > 30 else float("nan")

            # ── 5. Skewness / Kurtosis ────────────────────────────────────────
            skew = float(log_ret.skew())
            kurt = float(log_ret.kurt())   # kurtosis excédentaire (0 = normale)

            # ── 6. ADX(14) ────────────────────────────────────────────────────
            adx_s    = _adx_series(df.dropna())
            adx_mean = float(adx_s.mean())
            adx_p25  = float((adx_s > 25).mean() * 100)

            # ── 7. Saisonnalité (D1 uniquement) ──────────────────────────────
            if tf == "D1":
                s_info    = _seasonality(log_ret)
                seas[f"{asset}_D1"] = s_info
                r2_seas   = round(s_info["r2"]    * 100, 1) if not np.isnan(s_info["r2"])    else None
                anova_p   = round(s_info["anova_p"],   4) if not np.isnan(s_info["anova_p"]) else None
            else:
                r2_seas = None
                anova_p = None

            # ── Famille prédite a priori ──────────────────────────────────────
            if not np.isnan(h) and not np.isnan(autocorr):
                if h > 0.5 and autocorr > 0:
                    famille = "Trend Following"
                elif h < 0.5 and autocorr < 0:
                    famille = "Mean Reversion"
                else:
                    famille = "Ambigu"
            else:
                famille = "N/A"

            # Interprétation Hurst
            if np.isnan(h):
                h_interp = "N/A"
            elif h > 0.55:
                h_interp = "Tendanciel"
            elif h < 0.45:
                h_interp = "Mean-Revertant"
            else:
                h_interp = "Aléatoire"

            rows.append({
                "Actif":           asset,
                "TF":              tf,
                "N barres":        n_ret,
                "Fiabilité":       "✅" if reliable else "⚠️ données éparses",
                "Période":         f"{df.index.min().date()} → {df.index.max().date()}",
                "Vol Ann %":       round(vol_ann, 1),
                "Hurst":           round(h, 3)        if not np.isnan(h)       else None,
                "Hurst Interp":    h_interp,
                "ADF p-val":       round(adf_pval, 4) if not np.isnan(adf_pval) else None,
                "Autocorr L1":     round(autocorr, 4) if not np.isnan(autocorr) else None,
                "Skewness":        round(skew, 3),
                "Kurtosis":        round(kurt, 2),
                "ADX Moyen":       round(adx_mean, 1),
                "ADX>25 %":        round(adx_p25,  1),
                "Saison R² %":     r2_seas,
                "Saison ANOVA p":  anova_p,
                "Famille Prédite": famille,
            })

    return pd.DataFrame(rows), seas


# ── Helpers d'affichage ───────────────────────────────────────────────────────
_FAM_ICON = {"Trend Following": "🟢", "Mean Reversion": "🔵", "Ambigu": "🟡", "N/A": "⚪"}

# Couleurs avec bon contraste sur fond blanc
_FAM_COLOR = {
    "Trend Following": "#2E7D32",   # vert foncé
    "Mean Reversion":  "#C62828",   # rouge foncé
    "Ambigu":          "#E65100",   # orange foncé
    "N/A":             "#757575",   # gris
}
_HURST_COLOR = {
    "Tendanciel":     "#2E7D32",
    "Aléatoire":      "#1565C0",
    "Mean-Revertant": "#C62828",
    "N/A":            "#757575",
}
_BAR_PALETTE = ["#1565C0", "#E65100", "#2E7D32"]  # H1 / H4 / D1

_LW = PLOTLY_DARK

def _extremes_caption(df: pd.DataFrame) -> str:
    parts = []
    for col, label in [
        ("Vol Ann %", "Plus volatil"),
        ("ADX Moyen", "Tendance la + forte"),
    ]:
        if col in df.columns:
            df_c = df.dropna(subset=[col])
            if not df_c.empty:
                parts.append(f"**{label} :** {df_c.loc[df_c[col].idxmax(), 'Actif']}")
    if "Hurst" in df.columns:
        df_h = df.dropna(subset=["Hurst"])
        if not df_h.empty:
            parts.append(f"**Hurst max (+ tendanciel) :** {df_h.loc[df_h['Hurst'].idxmax(), 'Actif']}")
            parts.append(f"**Hurst min (+ mean-rev) :** {df_h.loc[df_h['Hurst'].idxmin(), 'Actif']}")
    return " | ".join(parts)


_COL_CFG = {
    "Vol Ann %":      st.column_config.NumberColumn("Vol Ann %",      format="%.1f %%"),
    "Hurst":          st.column_config.NumberColumn("Hurst",          format="%.3f"),
    "ADF p-val":      st.column_config.NumberColumn("ADF p-val",      format="%.4f"),
    "Autocorr L1":    st.column_config.NumberColumn("Autocorr L1",    format="%.4f"),
    "Skewness":       st.column_config.NumberColumn("Skewness",       format="%.3f"),
    "Kurtosis":       st.column_config.NumberColumn("Kurtosis",       format="%.2f"),
    "ADX Moyen":      st.column_config.NumberColumn("ADX Moyen",      format="%.1f"),
    "ADX>25 %":       st.column_config.NumberColumn("ADX>25 %",       format="%.1f %%"),
    "Saison R² %":    st.column_config.NumberColumn("Saison R² %",    format="%.1f %%"),
    "Saison ANOVA p": st.column_config.NumberColumn("Saison ANOVA p", format="%.4f"),
    "N barres":       st.column_config.NumberColumn("N barres",       format="%d"),
}

_DISPLAY_COLS = [
    "Actif", "N barres", "Fiabilité", "Période",
    "Vol Ann %", "Hurst", "Hurst Interp",
    "ADF p-val", "Autocorr L1", "Skewness", "Kurtosis",
    "ADX Moyen", "ADX>25 %",
    "Saison R² %", "Saison ANOVA p",
    "Famille Prédite",
]

# ══════════════════════════════════════════════════════════════════════════════
# PAGE STREAMLIT
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Profil Intrinsèque des Actifs", page_icon="🧬", layout="wide"
)
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
st.title("🧬 Profil Intrinsèque des Actifs")

st.markdown(
    """
    Caractérisation **statistique des prix bruts** — page autonome, indépendante des résultats
    de stratégies.
    Objectif : établir une inférence *a priori* sur la famille de stratégie théoriquement adaptée,
    à croiser ensuite avec les performances Walk-Forward réelles.

    | | |
    |---|---|
    | **Source** | `TB-MT5/*_M15_MT5.csv` — rééchantillonné en H1 / H4 / D1 |
    | **Période** | 2015-01-01 à 2025-12-31 |
    | **Métriques** | sur rendements log sauf ADF (niveau de prix) et ADX (OHLC) |
    | ⚠️ **Platinum** | données éparses (38 % de barres normales) — interpréter avec prudence |
    """
)

if not _HAS_STATSMODELS:
    st.warning(
        "⚠️ `statsmodels` non disponible — colonne ADF p-val désactivée. "
        "Installez avec `pip install statsmodels`."
    )

with st.spinner("Calcul des profils en cours (peut prendre 30–60 s à froid)…"):
    df_all, seasonality = _build_profiles()

if df_all.empty:
    st.error("Aucune donnée — vérifiez les fichiers `*_M15_MT5.csv` dans `TB-MT5/`.")
    st.stop()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_recap, tab_cross, tab_vis, tab_pred, tab_export = st.tabs([
    "📋 Tableaux Récap",
    "↔️ Comparaison Inter-TF",
    "📊 Visualisations",
    "🎯 Prédiction vs Réalité",
    "💾 Export CSV",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — TABLEAUX RÉCAP PAR TIMEFRAME
# ══════════════════════════════════════════════════════════════════════════════
with tab_recap:
    st.markdown(
        "Trois tableaux : un par timeframe. "
        "**Famille Prédite** = inférence théorique *a priori* depuis Hurst + Autocorr L1 uniquement — "
        "à confronter avec les performances réelles dans les autres pages."
    )

    subtabs = st.tabs([f"⏱ {tf}" for tf in TIMEFRAMES])

    for i, tf in enumerate(TIMEFRAMES):
        with subtabs[i]:
            df_tf = df_all[df_all["TF"] == tf].copy()
            if df_tf.empty:
                st.warning(f"Aucune donnée calculée pour {tf}.")
                continue

            df_tf["Famille Prédite"] = df_tf["Famille Prédite"].apply(
                lambda v: f"{_FAM_ICON.get(v, '')} {v}"
            )
            display = [c for c in _DISPLAY_COLS if c in df_tf.columns]
            chart_badge(46)
            st.dataframe(
                df_tf[display],
                use_container_width=True, hide_index=True,
                column_config=_COL_CFG,
            )
            cap = _extremes_caption(df_all[df_all["TF"] == tf].dropna(subset=["Hurst"]))
            if cap:
                st.caption(cap)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — COMPARAISON INTER-TIMEFRAMES
# ══════════════════════════════════════════════════════════════════════════════
with tab_cross:
    st.markdown(
        "### Stabilité de la nature de l'actif selon le timeframe  \n"
        "Une nature stable (Hurst et Autocorr cohérents entre H1, H4, D1) renforce "
        "la confiance dans l'inférence a priori."
    )

    chart_badge(47)
    for metric, fmt in [("Hurst", "%.3f"), ("Autocorr L1", "%.4f"), ("Vol Ann %", "%.1f %%")]:
        pivot = (
            df_all.pivot(index="Actif", columns="TF", values=metric)
            .reindex(columns=[tf for tf in TIMEFRAMES if tf in df_all["TF"].values])
        )
        st.markdown(f"#### {metric}")
        col_cfg_p = {tf: st.column_config.NumberColumn(tf, format=fmt) for tf in TIMEFRAMES}
        st.dataframe(pivot, use_container_width=False, column_config=col_cfg_p)
        st.markdown("")

    st.markdown("#### Famille Prédite par TF")
    fam_pivot = (
        df_all.pivot(index="Actif", columns="TF", values="Famille Prédite")
        .reindex(columns=[tf for tf in TIMEFRAMES if tf in df_all["TF"].values])
    )
    st.dataframe(fam_pivot, use_container_width=False)

    st.markdown("#### ADX Moyen par actif × TF")
    adx_pivot = (
        df_all.pivot(index="Actif", columns="TF", values="ADX Moyen")
        .reindex(columns=[tf for tf in TIMEFRAMES if tf in df_all["TF"].values])
    )
    col_cfg_adx = {tf: st.column_config.NumberColumn(tf, format="%.1f") for tf in TIMEFRAMES}
    st.dataframe(adx_pivot, use_container_width=False, column_config=col_cfg_adx)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — VISUALISATIONS
# ══════════════════════════════════════════════════════════════════════════════
with tab_vis:
    tf_sel = st.selectbox(
        "Timeframe de référence pour les visuels",
        TIMEFRAMES, index=2, key="vis_tf",
    )
    df_vis = df_all[df_all["TF"] == tf_sel].copy()

    # ── 1. Volatilité annualisée ──────────────────────────────────────────────
    st.markdown("#### 1 — Volatilité Annualisée (%) par actif")
    df_vol_all = df_all.dropna(subset=["Vol Ann %"])
    fig_vol = px.bar(
        df_vol_all,
        x="Actif", y="Vol Ann %", color="TF",
        barmode="group", text_auto=".1f",
        labels={"Vol Ann %": "Volatilité annualisée (%)"},
        color_discrete_sequence=_BAR_PALETTE,
        category_orders={"TF": TIMEFRAMES},
    )
    fig_vol.update_layout(height=380, **_LW)
    st_plotly(fig_vol, "vol_bars", num=48)

    # ── 2. Hurst par actif ────────────────────────────────────────────────────
    st.markdown(f"#### 2 — Exposant de Hurst — {tf_sel}")
    df_h = df_vis.dropna(subset=["Hurst"]).sort_values("Hurst")
    if df_h.empty:
        st.info("Données Hurst insuffisantes pour ce timeframe.")
    else:
        fig_h = px.bar(
            df_h, x="Actif", y="Hurst", color="Hurst Interp",
            text_auto=".3f",
            labels={"Hurst": "Exposant de Hurst H"},
            color_discrete_map=_HURST_COLOR,
        )
        fig_h.add_hline(
            y=0.5, line_dash="dash", line_color="rgba(0,0,0,0.4)", line_width=1.5,
            annotation_text="H = 0.5 (marche aléatoire)",
            annotation_position="top right",
        )
        fig_h.update_layout(height=380, **_LW)
        st_plotly(fig_h, "hurst_bars", num=49)

    # ── 3. Scatter Hurst × Autocorrélation ───────────────────────────────────
    st.markdown(f"#### 3 — Scatter Hurst × Autocorrélation — {tf_sel}")
    st.caption(
        "**Axe X** : exposant de Hurst H (H > 0.5 = persistant/tendanciel, H < 0.5 = mean-revertant).  "
        "**Axe Y** : autocorrélation au lag 1 des rendements log (> 0 = momentum, < 0 = retour à la moyenne).  \n"
        "Quadrant **haut-droit** → Trend Following théorique | **bas-gauche** → Mean Reversion théorique.  \n"
        "⬇️ Utilisez le bouton **PNG** ci-dessous pour exporter à haute résolution (2800 px, fond blanc) "
        "pour insertion directe dans le mémoire Word."
    )
    df_map = df_vis.dropna(subset=["Hurst", "Autocorr L1"])
    if df_map.empty:
        st.info("Données insuffisantes pour ce visuel.")
    else:
        fig_map = px.scatter(
            df_map, x="Hurst", y="Autocorr L1",
            text="Actif", color="Famille Prédite",
            color_discrete_map=_FAM_COLOR,
            labels={
                "Hurst":       "Exposant de Hurst H",
                "Autocorr L1": "Autocorrélation Lag 1",
            },
        )
        fig_map.update_traces(textposition="top center", marker_size=14)
        fig_map.add_vline(x=0.5, line_dash="dash", line_color="rgba(0,0,0,0.2)",
                          annotation_text="H=0.5", annotation_position="top left")
        fig_map.add_hline(y=0.0, line_dash="dash", line_color="rgba(0,0,0,0.2)",
                          annotation_text="AC=0")
        fig_map.update_layout(height=440, **_LW)
        st_plotly(fig_map, "trend_map", num=50)

    # ── 4. Saisonnalité mensuelle — Café + Cacao (D1) ────────────────────────
    st.markdown("#### 4 — Saisonnalité Mensuelle — Café et Cacao (D1)")
    st.caption(
        "Rendement log moyen (%) par mois calendaire. "
        "Calculé sur la série journalière complète 2015-2025.  \n"
        "R² = part de variance expliquée par le mois, ANOVA p-val = significativité du signal."
    )
    seas_assets = ["COFFEE", "COCOA"]
    seas_rows: dict[str, list] = {}
    for a in seas_assets:
        key = f"{a}_D1"
        if key in seasonality and seasonality[key].get("monthly") is not None:
            m = seasonality[key]["monthly"].reindex(range(1, 13)).fillna(0)
            seas_rows[a] = m.values

    if seas_rows:
        df_seas = pd.DataFrame(seas_rows, index=_MONTH_NAMES).T
        fig_seas = px.imshow(
            df_seas,
            text_auto=".2f",
            color_continuous_scale="RdYlGn",
            color_continuous_midpoint=0,
            labels={"x": "Mois", "y": "Actif", "color": "Rdt log moy (%)"},
            title="Rendement log moyen mensuel (%) — Café et Cacao",
        )
        fig_seas.update_layout(height=260, **_LW)
        st_plotly(fig_seas, "seas_heatmap", num=51)

        for a in seas_assets:
            key = f"{a}_D1"
            if key in seasonality:
                r2 = seasonality[key]["r2"]
                ap = seasonality[key]["anova_p"]
                if not np.isnan(r2) and not np.isnan(ap):
                    sig = "✅ signal saisonnier significatif (p < 0.05)" if ap < 0.05 else "⚪ non significatif"
                    st.caption(
                        f"**{a}** — R² : {r2*100:.1f}% | ANOVA p-val : {ap:.4f} — {sig}  \n"
                        "_Test F de Fisher (ANOVA one-way) : teste si le rendement moyen varie "
                        "significativement entre les **12 mois calendaires** — saisonnalité globale sur "
                        "l'actif sous-jacent. ≠ du Mann-Whitney (page Hypothèses B) qui compare "
                        "**mois actifs vs mois exclus** par le filtre saisonnier._"
                    )
    else:
        st.info("Données de saisonnalité D1 non disponibles.")

    # ── 5. ADX moyen — toutes TF ──────────────────────────────────────────────
    st.markdown("#### 5 — Force de Tendance ADX(14) par actif")
    df_adx = df_all.dropna(subset=["ADX Moyen"])
    fig_adx = px.bar(
        df_adx, x="Actif", y="ADX Moyen", color="TF",
        barmode="group", text_auto=".1f",
        labels={"ADX Moyen": "ADX(14) moyen"},
        color_discrete_sequence=_BAR_PALETTE,
        category_orders={"TF": TIMEFRAMES},
    )
    fig_adx.add_hline(y=25, line_dash="dash", line_color="rgba(0,0,0,0.3)",
                      annotation_text="ADX=25 (seuil tendance)", annotation_position="top right")
    fig_adx.update_layout(height=360, **_LW)
    st_plotly(fig_adx, "adx_bars", num=52)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — PRÉDICTION VS RÉALITÉ
# ══════════════════════════════════════════════════════════════════════════════
with tab_pred:
    st.markdown(
        "### Prédiction Théorique vs Réalité OOS\n"
        "Pour chaque actif : le régime prédit par l'exposant de Hurst (D1, 2015–2025) "
        "est confronté à la famille de stratégie réellement gagnante en Out-of-Sample.  \n"
        "**Source Hurst** : calcul interne sur prix bruts. "
        "**Source gagnant OOS** : meilleur rendement OOS médian par famille dans `df_kpi` "
        "(à charger depuis l'Accueil)."
    )

    # Règle de prédiction basée sur Hurst seul (seuils du mémoire)
    def _regime_from_hurst(h) -> str:
        if h is None or np.isnan(h):
            return "N/A"
        if h > 0.55:
            return "Tendanciel"
        if h < 0.45:
            return "Mean-Revertant"
        return "Marche Aléatoire"

    def _famille_from_regime(regime: str) -> str:
        return {"Tendanciel": "Trend Following",
                "Mean-Revertant": "Mean Reversion"}.get(regime, "Ambigu")

    # Hurst D1 par actif
    _df_d1 = df_all[df_all["TF"] == "D1"].set_index("Actif")

    # Famille gagnante par actif depuis df_kpi (session_state)
    _df_kpi_pred = st.session_state.get("df_kpi")
    _winners: dict[str, str] = {}
    if _df_kpi_pred is not None and not _df_kpi_pred.empty and "robot" in _df_kpi_pred.columns:
        _dk = _df_kpi_pred.copy()
        _dk["famille"] = _dk["robot"].map(ROBOT_FAMILY).fillna("Autre")
        _ret_col = next((c for c in ("OOS_Return_Med_Pct", "OOS_Score_Med") if c in _dk.columns), None)
        if _ret_col:
            for _ac, _grp in _dk.groupby("actif_clean"):
                _fm = _grp.groupby("famille")[_ret_col].median()
                _winners[_ac] = str(_fm.idxmax()) if not _fm.empty else "N/A"

    # Construction du tableau
    _pred_rows = []
    for _ac in ASSETS:
        _h   = _df_d1.loc[_ac, "Hurst"] if _ac in _df_d1.index else float("nan")
        _reg = _regime_from_hurst(_h)
        _att = _famille_from_regime(_reg)
        _win = _winners.get(_ac, "⚠️ Charger données (Accueil)")
        if "⚠️" in _win or _win == "N/A":
            _accord = "N/A"
        elif _att == _win:
            _accord = "✅ Oui"
        elif _att == "Ambigu":
            _accord = "🟡 Partiel"
        else:
            _accord = "❌ Non"
        _pred_rows.append({
            "Actif":                _CFG_ASSET_LABELS.get(_ac, _ac),
            "Hurst D1":             round(float(_h), 3) if not np.isnan(_h) else None,
            "Régime prédit":        _reg,
            "Famille attendue":     _att,
            "Famille gagnante OOS": _win,
            "Accord":               _accord,
        })

    _df_pred = pd.DataFrame(_pred_rows)

    # ── Tableau interactif ────────────────────────────────────────────────────
    chart_badge(53)
    st.dataframe(
        _df_pred, use_container_width=True, hide_index=True,
        column_config={
            "Hurst D1": st.column_config.NumberColumn("Hurst D1", format="%.3f"),
        },
    )

    # ── Export PNG via Plotly Table (pour insertion Word) ─────────────────────
    st.markdown("##### Export pour le mémoire")
    st.caption("Le bouton ⬇️ PNG ci-dessous exporte le tableau en image haute résolution (fond blanc).")

    _ACCORD_COLORS = {"✅ Oui": "#C8E6C9", "🟡 Partiel": "#FFF9C4",
                      "❌ Non": "#FFCDD2", "N/A": "#EEEEEE"}
    _cell_colors = [
        ["#FFFFFF"] * len(_pred_rows),          # Actif
        ["#FFFFFF"] * len(_pred_rows),          # Hurst
        ["#FFFFFF"] * len(_pred_rows),          # Régime
        ["#E3F2FD"] * len(_pred_rows),          # Attendue
        ["#F3E5F5"] * len(_pred_rows),          # Gagnante
        [_ACCORD_COLORS.get(r["Accord"], "#EEEEEE") for r in _pred_rows],  # Accord
    ]
    fig_tbl = go.Figure(data=[go.Table(
        header=dict(
            values=[f"<b>{c}</b>" for c in _df_pred.columns],
            fill_color="#1565C0",
            font=dict(color="white", size=13),
            align="center", height=35,
        ),
        cells=dict(
            values=[_df_pred[c].astype(str).tolist() for c in _df_pred.columns],
            fill_color=_cell_colors,
            font=dict(color="#212121", size=12),
            align=["left", "center", "center", "center", "center", "center"],
            height=30,
        ),
    )])
    fig_tbl.update_layout(
        margin=dict(l=5, r=5, t=5, b=5),
        paper_bgcolor="white",
    )
    st_plotly(fig_tbl, "pred_vs_reality_tbl",
              filename="prediction_vs_realite", height=280)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — EXPORT CSV
# ══════════════════════════════════════════════════════════════════════════════
with tab_export:
    st.markdown("### Export CSV — un fichier par timeframe")
    st.markdown(
        "Les fichiers contiennent toutes les métriques calculées. "
        "Encoding UTF-8 avec BOM pour compatibilité Excel."
    )

    export_cols = [c for c in [
        "Actif", "TF", "N barres", "Fiabilité", "Période",
        "Vol Ann %", "Hurst", "Hurst Interp",
        "ADF p-val", "Autocorr L1", "Skewness", "Kurtosis",
        "ADX Moyen", "ADX>25 %", "Saison R² %", "Saison ANOVA p",
        "Famille Prédite",
    ] if c in df_all.columns]

    for tf in TIMEFRAMES:
        df_exp = df_all[df_all["TF"] == tf][export_cols]
        if df_exp.empty:
            continue
        csv_bytes = df_exp.to_csv(index=False).encode("utf-8-sig")
        col1, col2 = st.columns([1, 3])
        with col1:
            st.download_button(
                label=f"⬇️ profil_actifs_{tf}.csv",
                data=csv_bytes,
                file_name=f"profil_actifs_{tf}.csv",
                mime="text/csv",
                key=f"dl_{tf}",
            )
        with col2:
            with st.expander(f"Aperçu {tf} ({len(df_exp)} lignes)"):
                st.dataframe(df_exp, use_container_width=True, hide_index=True,
                             column_config=_COL_CFG)
