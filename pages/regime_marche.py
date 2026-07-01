"""
🌊 Régime de Marché — ADX, Hurst, Performance conditionnée au régime.
3 onglets : ADX & Régime / Hurst & Volatilité / Impact sur les Stratégies.
Chargement automatique depuis les CSV locaux au démarrage de la page.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.charts import (
    fig_adx_timeline,
    fig_adx_vs_ghpr,
    fig_hurst_bar,
    fig_regime_performance,
)
from core.constants import GLOBAL_CSS, REGIME_COLOR, THEME, TYPE_COLOR
from core.ui_helpers import st_plotly
from core.market_data import (
    available_local_symbols,
    fetch_and_enrich,
    hurst_interpretation,
    regime_stats,
)

st.set_page_config(page_title="Régime de Marché", page_icon="🌊", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
st.title("🌊 Régime de Marché — Pourquoi ça marche (ou pas) ?")
st.markdown(
    "Analyse des **caractéristiques intrinsèques** de chaque matière première "
    "(persistance, force de tendance) et leur impact sur la performance des stratégies."
)

# ── Guard ─────────────────────────────────────────────────────────────────────
if st.session_state.get("df_master") is None:
    st.warning("⚠️ Aucune donnée. Retournez à l'**Accueil**.")
    st.stop()

_df_kpi_check = st.session_state.get("df_kpi")
if _df_kpi_check is not None and "robot" in _df_kpi_check.columns:
    st.info(
        "⏳ Cette page sera mise à jour prochainement pour la nouvelle structure Walk-Forward.  \n"
        "Consultez la page **Vue Globale** pour l'analyse complète."
    )
    st.stop()

df_m = st.session_state["df_master"]
df_k = st.session_state["df_kpi"]
market_cache: dict = st.session_state.get("market_cache") or {}

# ── Sidebar ────────────────────────────────────────────────────────────────────
symbols_dispo = sorted(df_m["Symbole"].unique().tolist())
_local_syms   = available_local_symbols()

with st.sidebar:
    st.header("🔧 Configuration")
    sel_symbols = st.multiselect("Symboles", symbols_dispo, default=symbols_dispo)

    st.divider()
    st.markdown("**Source des données :**")
    for sym in sel_symbols:
        icon = "📁" if sym in _local_syms else "🌐"
        src  = "CSV local" if sym in _local_syms else "Yahoo Finance"
        st.caption(f"{icon} {sym} → {src}")

    st.divider()
    if st.button("🔄 Forcer le rechargement", use_container_width=True,
                 help="Vide le cache et retélécharge toutes les données."):
        for sym in sel_symbols:
            market_cache.pop(sym, None)
        st.session_state["market_cache"] = market_cache
        st.rerun()

# ── Auto-chargement au démarrage ──────────────────────────────────────────────
to_load = [s for s in sel_symbols if s not in market_cache or market_cache.get(s, pd.DataFrame()).empty]
if to_load:
    _msg = "Lecture des CSV locaux…" if all(s in _local_syms for s in to_load) else "Chargement données marché…"
    with st.spinner(_msg):
        for sym in to_load:
            rows      = df_m[df_m["Symbole"] == sym]
            start     = rows["Date_Start"].min() if "Date_Start" in rows.columns else "2010-01-01"
            end       = rows["Date_End"].max()   if "Date_End"   in rows.columns else "2026-01-01"
            start_ext = str((pd.Timestamp(start) - pd.Timedelta(days=120)).date())
            market_cache[sym] = fetch_and_enrich(sym, start_ext, end)
        st.session_state["market_cache"] = market_cache

loaded = [s for s in sel_symbols if not market_cache.get(s, pd.DataFrame()).empty]
if not loaded:
    st.error("Aucune donnée de marché disponible. Vérifiez les fichiers CSV dans TB-Python/.")
    st.stop()

# ── TABS ──────────────────────────────────────────────────────────────────────
tab_adx, tab_hurst, tab_impact = st.tabs([
    "📈 ADX & Régime",
    "🌀 Hurst & Volatilité",
    "🔗 Impact sur les Stratégies",
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — ADX & RÉGIME
# ═══════════════════════════════════════════════════════════════════════════════
with tab_adx:
    st.subheader("📊 Distribution du Temps par Régime")
    st.caption("Quel pourcentage du temps chaque actif passe-t-il en tendance forte / tendance / range ?")

    # Résumé des régimes par symbole
    regime_rows = []
    for sym in loaded:
        df_mkt = market_cache[sym]
        if df_mkt.empty or "Regime" not in df_mkt.columns:
            continue
        total = len(df_mkt)
        for regime, grp in df_mkt.groupby("Regime"):
            regime_rows.append({
                "Symbole": sym,
                "Régime": regime,
                "% du temps": round(len(grp) / total * 100, 1),
            })

    if regime_rows:
        df_regimes = pd.DataFrame(regime_rows)
        fig_reg = px.bar(
            df_regimes, x="Symbole", y="% du temps", color="Régime",
            barmode="stack",
            color_discrete_map={
                "Forte Tendance": REGIME_COLOR.get("Forte Tendance", "#00E676"),
                "Tendance":       REGIME_COLOR.get("Tendance",       "#FFD54F"),
                "Range":          REGIME_COLOR.get("Range",          "#FF5252"),
            },
            title="Distribution des régimes par actif",
        )
        fig_reg.update_layout(height=380)
        st_plotly(fig_reg, "reg_dist_bar")

    st.divider()

    # ADX timeline par symbole sélectionné
    st.subheader("📈 Évolution de l'ADX dans le Temps")
    sym_adx = st.selectbox("Symbole", loaded, key="adx_sym")
    df_mkt  = market_cache[sym_adx]
    if not df_mkt.empty:
        st_plotly(fig_adx_timeline(df_mkt, sym_adx), f"adx_timeline_{sym_adx}")
        st.caption(
            f"ADX < 25 = Range | ADX 25-40 = Tendance | ADX > 40 = Forte Tendance  "
            f"— ADX moyen : **{df_mkt['ADX'].mean():.1f}**"
        )

        st.divider()

        # Stats régime
        st.subheader("📋 Statistiques de Régime")
        rs = regime_stats(df_mkt)
        if not rs.empty:
            st.dataframe(rs, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — HURST & VOLATILITÉ
# ═══════════════════════════════════════════════════════════════════════════════
with tab_hurst:
    # Hurst bar chart
    hurst_dict = {}
    for sym in loaded:
        df_mkt = market_cache[sym]
        if not df_mkt.empty and "Hurst" in df_mkt.columns:
            hurst_dict[sym] = df_mkt["Hurst"].mean()

    if hurst_dict:
        st.subheader("🌀 Exposant de Hurst par Actif")
        st.markdown("""
**H > 0.55** → Marché tendanciel → favorable au **Trend-Following**
**H ≈ 0.50** → Marche aléatoire
**H < 0.45** → Marché mean-revertant → favorable à la **Mean-Reversion**
""")
        st_plotly(fig_hurst_bar(hurst_dict), "hurst_bar_all")

        st.divider()

        # Métriques individuelles
        cols_h = st.columns(min(len(hurst_dict), 3))
        for i, (sym, h_val) in enumerate(sorted(hurst_dict.items())):
            label, color = hurst_interpretation(h_val)
            with cols_h[i % len(cols_h)]:
                st.metric(sym, f"H = {h_val:.3f}")
                st.markdown(
                    f"<span style='color:{color};font-size:12px;'>{label}</span>",
                    unsafe_allow_html=True,
                )

    st.divider()

    # Volatilité comparée
    st.subheader("📊 Volatilité Mensuelle Annualisée")
    st.caption("Actifs les plus volatils = risque plus élevé mais aussi plus d'opportunités.")
    vol_rows = []
    for sym in loaded:
        df_mkt = market_cache[sym]
        if not df_mkt.empty and "Volatility_pct" in df_mkt.columns:
            vol_rows.append({"Symbole": sym, "Volatilité (%)": df_mkt["Volatility_pct"].mean()})

    if vol_rows:
        df_vol = pd.DataFrame(vol_rows).sort_values("Volatilité (%)", ascending=False)
        fig_vol = px.bar(
            df_vol, x="Symbole", y="Volatilité (%)",
            color="Volatilité (%)", color_continuous_scale="RdYlGn_r",
            title="Volatilité moyenne annualisée par actif (%)",
            text_auto=".1f",
        )
        fig_vol.update_layout(coloraxis_showscale=False, height=350)
        st_plotly(fig_vol, "reg_vol_bar")

    st.divider()

    # ATR comparé
    atr_rows = []
    for sym in loaded:
        df_mkt = market_cache[sym]
        if not df_mkt.empty and "ATR_pct" in df_mkt.columns:
            atr_rows.append({"Symbole": sym, "ATR (%)": df_mkt["ATR_pct"].mean()})

    if atr_rows:
        df_atr = pd.DataFrame(atr_rows).sort_values("ATR (%)", ascending=False)
        fig_atr = px.bar(
            df_atr, x="Symbole", y="ATR (%)",
            color="ATR (%)", color_continuous_scale="Blues",
            title="ATR normalisé moyen par actif (%)",
            text_auto=".2f",
        )
        fig_atr.update_layout(coloraxis_showscale=False, height=320)
        st_plotly(fig_atr, "reg_atr_bar")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — IMPACT SUR LES STRATÉGIES
# ═══════════════════════════════════════════════════════════════════════════════
with tab_impact:
    st.subheader("🔗 Impact du Régime sur la Performance")
    st.markdown(
        "La stratégie performe-t-elle mieux en tendance ou en range ? "
        "La corrélation ADX–GHPR révèle l'adéquation EA/actif."
    )

    sym_impact = st.selectbox("Symbole à analyser", loaded, key="impact_sym")
    df_mkt_imp = market_cache[sym_impact]
    df_sym_m   = df_m[df_m["Symbole"] == sym_impact]

    if not df_mkt_imp.empty and not df_sym_m.empty:
        # Performance par régime
        st.subheader(f"📊 Performance par Régime — {sym_impact}")
        try:
            st_plotly(
                fig_regime_performance(df_sym_m, df_mkt_imp, sym_impact),
                f"reg_perf_{sym_impact}",
            )
        except Exception as e:
            st.warning(f"Impossible d'afficher la performance par régime : {e}")

        st.divider()

        # ADX vs GHPR scatter
        st.subheader(f"🎯 ADX vs GHPR — {sym_impact}")
        st.caption(
            "Corrélation positive : la stratégie est un Trend-Follower. "
            "Corrélation négative : la stratégie est Mean-Reversion."
        )
        df_sym_k = df_k[df_k["Symbole"] == sym_impact].copy()
        if not df_sym_k.empty and "GHPR Moyen" in df_sym_k.columns:
            df_sym_renamed = df_sym_k.rename(columns={"GHPR Moyen": "GHPR"})
            try:
                st_plotly(
                    fig_adx_vs_ghpr(df_sym_renamed, sym_impact),
                    f"adx_ghpr_{sym_impact}",
                )
            except Exception as e:
                st.warning(f"Impossible d'afficher le scatter ADX vs GHPR : {e}")

        st.divider()

        # Métriques clés pour ce symbole
        col1, col2, col3, col4 = st.columns(4)
        h_val = hurst_dict.get(sym_impact, 0.5)
        label, color = hurst_interpretation(h_val)
        col1.metric("Hurst", f"{h_val:.3f}")
        col2.metric("ADX moyen", f"{df_mkt_imp['ADX'].mean():.1f}")
        if "Volatility_pct" in df_mkt_imp.columns:
            col3.metric("Volatilité moy.", f"{df_mkt_imp['Volatility_pct'].mean():.1f} %")
        if "GHPR Moyen" in df_sym_k.columns:
            col4.metric("GHPR moyen (strats)", f"{df_sym_k['GHPR Moyen'].mean():.5f}")

    else:
        st.info("Données insuffisantes pour cette analyse.")
