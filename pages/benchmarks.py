"""
Benchmarks — Stratégies vs Buy&Hold par actif et vs DJUBS (indice global).

B&H par actif  : CSV D1 TB-Python/ (même série que MT5), rendements journaliers
                 chaînés avec neutralisation des dates de roll (TB-MT5/dates_rolls.csv).
                 MaxDD calculé sur la série cumulée roll-ajustée.

DJUBS          : Bloomberg Commodity Index Excess Return ($DJUBS), rééchantillonné
                 M15→D1 depuis TB-MT5/Bloomberg_Commodity_Index.csv.
                 Benchmark global diversifié, NE PAS mélanger avec les excédents
                 par actif (deux lectures différentes).
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config_analyse import (
    ALL_ASSETS, ASSET_LABELS, FAMILY_COLORS, OOS_LABELS, OOS_WINDOWS,
)
from core.analyse_metrics import add_family_column, bloomberg_oos_returns, buyhold_oos_returns
from core.constants import GLOBAL_CSS, PLOTLY_DARK
from core.market_data import _load_local_ohlc
from core.mt5_runner import EA_CONFIG, FOLDS
from core.single_run import OUTPUT_DETAIL, load_detail_trades
from core.ui_helpers import chart_badge, st_plotly

_FOLD_LABELS = {f["n"]: f"Pli {f['n']}" for f in FOLDS}
_FOLD_OOS    = {f["n"]: f"Pli {f['n']} ({f['forward_date'][:4]}–{f['to_date'][:4]})" for f in FOLDS}
_ALL_FOLDS   = sorted(OOS_WINDOWS.keys())

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Benchmarks vs B&H", page_icon="📊", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
st.title("📊 Benchmarks — Stratégies vs Buy & Hold")
st.markdown(
    "Comparaison des rendements médians OOS de chaque stratégie "
    "avec le Buy&Hold passif de l'actif sous-jacent, pour chaque pli OOS.  \n"
    "*Source B&H : cours D1 TB-Python (mêmes données que l'optimisation MT5), "
    "rendements journaliers chaînés avec neutralisation des dates de roll.*"
)

# ── Guard ─────────────────────────────────────────────────────────────────────
df_kpi: pd.DataFrame | None = st.session_state.get("df_kpi")
if df_kpi is None or df_kpi.empty or "robot" not in df_kpi.columns:
    st.warning("⚠️ Aucune donnée. Retournez à l'**Accueil** et chargez les résultats.")
    st.stop()

df_k = add_family_column(df_kpi)

# ── Calcul Buy&Hold par actif ─────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def _compute_all_buyhold() -> dict[str, dict[int, dict | None]]:
    """Pré-calcule rendement + MaxDD B&H pour tous les actifs et tous les plis."""
    return {a: buyhold_oos_returns(a) for a in ALL_ASSETS}


# ── Calcul DJUBS ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def _compute_bloomberg() -> dict[int, dict | None]:
    """Rendement + MaxDD du DJUBS Excess Return sur chaque fenêtre OOS."""
    return bloomberg_oos_returns()


with st.spinner("Calcul des rendements Buy&Hold et DJUBS…"):
    bh_data  = _compute_all_buyhold()
    dj_data  = _compute_bloomberg()

# ── Construction de la table comparée ─────────────────────────────────────────
ret_col = "OOS_Return_Med_Pct"


def _bh_field(bh_data: dict, actif: str, pli: int, field: str):
    """Extrait un champ du dict B&H pour un actif/pli donné, ou None."""
    entry = (bh_data.get(actif) or {}).get(pli)
    return entry.get(field) if entry else None


def _build_comparison(df: pd.DataFrame) -> pd.DataFrame:
    """
    Retourne une ligne par (robot_label, actif_clean, pli, famille) avec :
    - Rdt OOS % (méd)  : rendement médian OOS de la stratégie
    - Rdt B&H %        : rendement B&H roll-ajusté
    - MaxDD B&H %      : max drawdown du B&H sur la même fenêtre
    - Excédent %       : stratégie − B&H
    - B&H Roll-Adj     : True si les dates de roll ont été appliquées
    """
    if ret_col not in df.columns:
        return pd.DataFrame()

    rows = []
    for (robot_lbl, actif, pli), grp in df.groupby(["robot_label", "actif_clean", "pli"]):
        strat_ret = grp[ret_col].median()
        bh_rdt    = _bh_field(bh_data, actif, pli, "rdt")
        bh_dd     = _bh_field(bh_data, actif, pli, "max_dd")
        bh_ok     = _bh_field(bh_data, actif, pli, "roll_adjusted")
        excess    = (
            float(strat_ret) - bh_rdt
            if bh_rdt is not None and not pd.isna(strat_ret)
            else None
        )
        famille = grp["famille"].iloc[0] if "famille" in grp.columns else "Autre"
        rows.append({
            "Stratégie":       robot_lbl,
            "Actif":           actif,
            "Pli":             pli,
            "Famille":         famille,
            "Rdt OOS % (méd)": round(float(strat_ret), 2) if not pd.isna(strat_ret) else None,
            "Rdt B&H %":       round(float(bh_rdt), 2)    if bh_rdt  is not None else None,
            "MaxDD B&H %":     round(float(bh_dd),  2)    if bh_dd   is not None else None,
            "Excédent %":      round(float(excess),  2)   if excess  is not None else None,
            "B&H Roll-Adj":    bool(bh_ok)                if bh_ok   is not None else False,
        })
    return pd.DataFrame(rows)


df_comp = _build_comparison(df_k)

if df_comp.empty:
    st.warning("Données insuffisantes — vérifiez que `OOS_Return_Med_Pct` est bien calculé.")
    st.stop()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_heat, tab_abs, tab_family, tab_equity, tab_detail = st.tabs([
    "🗺️ Heatmap Excédent",
    "📊 Rdt Absolu",
    "👨‍👩‍👧 Par Famille",
    "📈 Courbes Équité",
    "📋 Tableau Détaillé",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — HEATMAP Excédent de rendement
# ══════════════════════════════════════════════════════════════════════════════
with tab_heat:
    st.markdown("### Excédent de Rendement OOS vs Buy&Hold (%)")
    st.markdown(
        "Une valeur positive signifie que la stratégie a sur-performé le Buy&Hold passif.  \n"
        "Chaque heatmap correspond à un pli OOS indépendant."
    )

    sel_folds = st.multiselect(
        "Plis OOS",
        options=_ALL_FOLDS,
        default=_ALL_FOLDS,
        format_func=lambda n: _FOLD_OOS.get(n, f"Pli {n}"),
        key="bh_folds",
    )

    df_h = df_comp[df_comp["Pli"].isin(sel_folds)].copy()
    df_h["Actif Label"] = df_h["Actif"].map(ASSET_LABELS).fillna(df_h["Actif"])

    if df_h["Excédent %"].isna().all():
        st.info(
            "ℹ️ Aucune donnée B&H disponible — vérifiez les CSV D1 dans `TB-Python/`.  \n"
            "Le tableau ci-dessous affiche les rendements stratégies sans comparaison."
        )
        pivot = (
            df_h.groupby(["Stratégie", "Actif Label"])["Rdt OOS % (méd)"]
            .mean().round(2).unstack("Actif Label")
        )
        if not pivot.empty:
            fig = px.imshow(
                pivot, text_auto=".1f", color_continuous_scale="RdYlGn",
                color_continuous_midpoint=0,
                labels={"x": "Actif", "y": "Stratégie", "color": "Rdt OOS % méd"},
                title="Rendement OOS % (médian, sans B&H)",
            )
            fig.update_layout(**PLOTLY_DARK)
            fig.update_layout(height=400, margin=dict(l=10, r=10, t=50, b=10))
            st_plotly(fig, "hm_no_bh", num=36)
    else:
        for fold_n in sel_folds:
            df_fold = df_h[df_h["Pli"] == fold_n]
            if df_fold.empty:
                continue

            pivot = (
                df_fold.groupby(["Stratégie", "Actif Label"])["Excédent %"]
                .mean().round(2).unstack("Actif Label")
            )
            if pivot.empty:
                continue

            fig = px.imshow(
                pivot, text_auto=".1f",
                color_continuous_scale="RdYlGn",
                color_continuous_midpoint=0,
                labels={"x": "Actif", "y": "Stratégie", "color": "Excédent %"},
                title=_FOLD_OOS.get(fold_n, f"Pli {fold_n}"),
            )
            fig.update_layout(**PLOTLY_DARK)
            fig.update_layout(height=400, margin=dict(l=10, r=10, t=60, b=10))
            st_plotly(fig, f"hm_bh_{fold_n}", num=36)

            # B&H de référence pour ce pli (rendement + MaxDD)
            bh_vals = []
            for a in ALL_ASSETS:
                rdt = _bh_field(bh_data, a, fold_n, "rdt")
                dd  = _bh_field(bh_data, a, fold_n, "max_dd")
                ok  = _bh_field(bh_data, a, fold_n, "roll_adjusted")
                if rdt is not None:
                    flag = "" if ok else " ⚠️"
                    dd_str = f", DD {dd:.1f}%" if dd is not None else ""
                    bh_vals.append(f"**{ASSET_LABELS.get(a, a)}** : {rdt:.1f}%{dd_str}{flag}")
            if bh_vals:
                st.caption("B&H de référence — " + " | ".join(bh_vals))


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — RDT ABSOLU stratégie vs B&H
# ══════════════════════════════════════════════════════════════════════════════
with tab_abs:
    st.markdown("### Rendement OOS médian vs Buy&Hold — valeurs absolues par actif")
    st.markdown(
        "Chaque cluster = un actif. "
        "La barre **grise** est le Buy&Hold passif (moyenne des 3 plis OOS). "
        "Les barres colorées sont le rendement OOS **médian** de chaque famille de stratégies "
        "(tous plis confondus)."
    )

    df_abs = df_comp.copy()
    df_abs["Actif Label"] = df_abs["Actif"].map(ASSET_LABELS).fillna(df_abs["Actif"])

    _has_bh = df_abs["Rdt B&H %"].notna().any()

    # B&H moyen par actif (moyenne des plis disponibles)
    bh_by_actif = (
        df_abs.groupby("Actif Label")["Rdt B&H %"]
        .mean().round(2).reset_index()
        .rename(columns={"Rdt B&H %": "Rdt B&H"})
        .dropna(subset=["Rdt B&H"])
    )

    # Rendement OOS médian par actif × famille (tous plis confondus)
    strat_by_fam = (
        df_abs.groupby(["Actif Label", "Famille"])["Rdt OOS % (méd)"]
        .median().round(2).reset_index()
    )

    # Ordre des actifs trié par B&H décroissant
    if _has_bh and not bh_by_actif.empty:
        _actif_order = bh_by_actif.sort_values("Rdt B&H", ascending=False)["Actif Label"].tolist()
    else:
        _actif_order = sorted(df_abs["Actif Label"].unique().tolist())

    fig_abs = go.Figure()

    # Barre grise = Buy & Hold de référence
    if _has_bh and not bh_by_actif.empty:
        fig_abs.add_bar(
            name="Buy & Hold",
            x=bh_by_actif["Actif Label"],
            y=bh_by_actif["Rdt B&H"],
            marker_color="#9E9E9E",
            opacity=0.75,
            text=bh_by_actif["Rdt B&H"].apply(lambda v: f"{v:+.1f}%"),
            textposition="outside",
        )

    # Une barre par famille de stratégies
    for _fam in strat_by_fam["Famille"].unique():
        _df_fam = strat_by_fam[strat_by_fam["Famille"] == _fam]
        fig_abs.add_bar(
            name=_fam,
            x=_df_fam["Actif Label"],
            y=_df_fam["Rdt OOS % (méd)"],
            marker_color=FAMILY_COLORS.get(_fam, "#AAAAAA"),
            opacity=0.88,
            text=_df_fam["Rdt OOS % (méd)"].apply(lambda v: f"{v:+.1f}%"),
            textposition="outside",
        )

    fig_abs.add_hline(
        y=0, line_dash="dash",
        line_color="rgba(255,255,255,0.40)", line_width=1,
    )
    fig_abs.update_layout(**PLOTLY_DARK)
    fig_abs.update_layout(
        barmode="group",
        height=520,
        xaxis=dict(title="Actif", categoryorder="array", categoryarray=_actif_order),
        yaxis_title="Rendement OOS % (médian des plis)",
        legend=dict(orientation="h", y=1.10),
        margin=dict(l=20, r=20, t=10, b=20),
    )
    st_plotly(fig_abs, "bh_abs_bar", num=37)

    if not _has_bh:
        st.info("ℹ️ Données B&H non disponibles — seuls les rendements stratégies sont affichés.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — PAR FAMILLE
# ══════════════════════════════════════════════════════════════════════════════
with tab_family:
    st.markdown("### Excédent vs B&H par famille de stratégies")

    df_fam = df_comp.copy()
    df_fam["Pli Label"]  = df_fam["Pli"].map(_FOLD_OOS)
    df_fam["Actif Label"] = df_fam["Actif"].map(ASSET_LABELS).fillna(df_fam["Actif"])

    if df_fam["Excédent %"].isna().all():
        st.info("ℹ️ Données B&H non disponibles — colonne Excédent % vide.")
    else:
        # ── Bar groupé : famille × pli ────────────────────────────────────────
        df_agg_fam = (
            df_fam.groupby(["Famille", "Pli Label"])["Excédent %"]
            .median().round(2).reset_index()
            .dropna(subset=["Excédent %"])
        )

        if not df_agg_fam.empty:
            fig_fam = px.bar(
                df_agg_fam,
                x="Pli Label", y="Excédent %", color="Famille",
                barmode="group", color_discrete_map=FAMILY_COLORS,
                text_auto=".1f",
                labels={"Pli Label": "Pli OOS", "Excédent %": "Excédent vs B&H (%)"},
                title="Excédent médian vs Buy&Hold — par famille et par pli",
            )
            fig_fam.add_hline(
                y=0, line_dash="dash",
                line_color="rgba(255,255,255,0.4)", line_width=1,
            )
            fig_fam.update_layout(**PLOTLY_DARK)
            fig_fam.update_layout(height=420, margin=dict(l=20, r=20, t=60, b=20))
            st_plotly(fig_fam, "bh_fam_bar", num=38)

        # ── Bar groupé : famille × actif ──────────────────────────────────────
        st.markdown("#### Excédent médian par famille × actif (tous plis confondus)")
        df_agg_actif = (
            df_fam.groupby(["Famille", "Actif Label"])["Excédent %"]
            .median().round(2).reset_index().dropna(subset=["Excédent %"])
        )
        if not df_agg_actif.empty:
            fig_act = px.bar(
                df_agg_actif,
                x="Actif Label", y="Excédent %", color="Famille",
                barmode="group", color_discrete_map=FAMILY_COLORS,
                text_auto=".1f",
                labels={"Actif Label": "Actif", "Excédent %": "Excédent vs B&H (%)"},
                title="Excédent médian vs Buy&Hold — par actif (moyenne des plis)",
            )
            fig_act.add_hline(
                y=0, line_dash="dash",
                line_color="rgba(255,255,255,0.4)", line_width=1,
            )
            fig_act.update_layout(**PLOTLY_DARK)
            fig_act.update_layout(height=420, margin=dict(l=20, r=20, t=60, b=20))
            st_plotly(fig_act, "bh_actif_bar", num=39)

        # ── Taux de sur-performance ───────────────────────────────────────────
        chart_badge(40)
        st.markdown("#### Taux de sur-performance vs B&H par famille")
        df_beat = df_fam.dropna(subset=["Excédent %"])
        if not df_beat.empty:
            beat_rate = (
                df_beat.groupby("Famille")
                .apply(lambda g: (g["Excédent %"] > 0).sum() / len(g) * 100)
                .round(1).reset_index()
                .rename(columns={0: "% cas Strat > B&H"})
            )
            st.dataframe(
                beat_rate,
                hide_index=True, use_container_width=False,
                column_config={
                    "% cas Strat > B&H": st.column_config.NumberColumn(
                        "% cas Strat > B&H", format="%.1f %%"
                    )
                },
            )

    # ── Référence globale DJUBS ───────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        "#### Référence globale — DJUBS (Bloomberg Commodity Index Excess Return)  \n"
        "<small>*Inclut le rendement de roll des futures, exclut le retour sur "
        "collatéral (T-Bills). Version Excess Return, ex DJ-UBS Commodity Index "
        "(renommé Bloomberg Commodity Index en 2014). Source : TB-MT5/Bloomberg_Commodity_Index.csv, "
        "rééchantillonné M15→D1.*</small>",
        unsafe_allow_html=True,
    )

    dj_rows = [
        {
            "Pli OOS":    _FOLD_OOS.get(n, f"Pli {n}"),
            "Rdt DJUBS %": (dj_data.get(n) or {}).get("rdt"),
            "MaxDD DJUBS %": (dj_data.get(n) or {}).get("max_dd"),
        }
        for n in _ALL_FOLDS
    ]
    df_dj = pd.DataFrame(dj_rows).dropna(subset=["Rdt DJUBS %"])

    if not df_dj.empty:
        # Graphique double métrique : rendement et MaxDD par pli
        fig_dj = go.Figure()
        fig_dj.add_bar(
            x=df_dj["Pli OOS"], y=df_dj["Rdt DJUBS %"],
            name="Rdt DJUBS %",
            marker_color="#7EC8E3",
            text=df_dj["Rdt DJUBS %"].apply(lambda v: f"{v:+.1f}%"),
            textposition="outside",
        )
        fig_dj.add_bar(
            x=df_dj["Pli OOS"], y=df_dj["MaxDD DJUBS %"],
            name="MaxDD DJUBS %",
            marker_color="#E07B54",
            text=df_dj["MaxDD DJUBS %"].apply(lambda v: f"{v:.1f}%"),
            textposition="outside",
        )
        fig_dj.add_hline(y=0, line_dash="dash",
                         line_color="rgba(255,255,255,0.3)", line_width=1)
        fig_dj.update_layout(**PLOTLY_DARK)
        fig_dj.update_layout(
            barmode="group", height=340,
            title="DJUBS — Rendement et MaxDD par fenêtre OOS",
            yaxis_title="%",
            margin=dict(l=20, r=20, t=60, b=20),
        )
        st_plotly(fig_dj, "dj_ref_bar", num=41)
    else:
        st.info("ℹ️ Données DJUBS non disponibles — vérifiez `TB-MT5/Bloomberg_Commodity_Index.csv`.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — COURBES D'ÉQUITÉ OOS
# ══════════════════════════════════════════════════════════════════════════════
with tab_equity:
    st.markdown("### Courbes d'Équité OOS — Stratégie vs Buy & Hold")
    st.markdown(
        "Sélectionnez une combinaison pour afficher l'évolution du capital en Out-of-Sample "
        "superposée au Buy&Hold de l'actif sur la même fenêtre.  \n"
        "⚠️ Nécessite les backtests individuels générés via **⚙️ Lancer MT5 → Backtests Individuels**."
    )

    _eq_c1, _eq_c2, _eq_c3, _eq_c4, _eq_c5 = st.columns(5)
    with _eq_c1:
        _eq_robot = st.selectbox(
            "Robot", list(EA_CONFIG.keys()),
            format_func=lambda r: EA_CONFIG[r]["label"], key="eq_robot",
        )
    with _eq_c2:
        _eq_actif = st.selectbox(
            "Actif", ALL_ASSETS,
            format_func=lambda a: ASSET_LABELS.get(a, a), key="eq_actif",
        )
    with _eq_c3:
        _eq_tf = st.selectbox("TF", ["H1", "H4", "D1"], key="eq_tf")
    with _eq_c4:
        _eq_pli = st.selectbox(
            "Pli OOS", [1, 2, 3],
            format_func=lambda n: _FOLD_OOS.get(n, f"Pli {n}"), key="eq_pli",
        )
    with _eq_c5:
        _eq_pass = st.selectbox(
            "Passe", ["best", "median", "worst"],
            format_func=lambda p: {"best": "Meilleure", "median": "Médiane", "worst": "Pire"}[p],
            key="eq_pass",
        )

    _eq_oos_s, _eq_oos_e = OOS_WINDOWS.get(_eq_pli, (None, None))

    with st.spinner("Chargement du journal de trades…"):
        _df_eq = load_detail_trades(
            _eq_robot, _eq_actif, _eq_tf, _eq_pli, _eq_pass,
            oos_start=_eq_oos_s,
        )

    if _df_eq.empty or "Time" not in _df_eq.columns:
        st.info(
            "Aucun journal disponible pour cette combinaison. "
            "Générez les backtests via **⚙️ Lancer MT5**."
        )
    else:
        # ── Courbe équité stratégie ───────────────────────────────────────────
        if "Balance" in _df_eq.columns and _df_eq["Balance"].notna().sum() > 5:
            _eq_s = _df_eq.dropna(subset=["Balance"]).set_index("Time")["Balance"].sort_index()
            _initial_cap = float(_eq_s.iloc[0])
        else:
            _initial_cap = 100_000.0
            _df_eq_s = _df_eq.dropna(subset=["Profit"]).sort_values("Time")
            _eq_s = (_initial_cap + _df_eq_s.set_index("Time")["Profit"].cumsum())

        # ── Courbe B&H sur même fenêtre ───────────────────────────────────────
        _eq_bh = None
        try:
            _price_d = _load_local_ohlc(_eq_actif, "Daily")
            if not _price_d.empty:
                if _eq_oos_s:
                    _price_d = _price_d[_eq_oos_s:]
                if _eq_oos_e:
                    _price_d = _price_d[:_eq_oos_e]
                if not _price_d.empty:
                    _p0 = float(_price_d["Close"].iloc[0])
                    _eq_bh = _initial_cap * (_price_d["Close"] / _p0)
        except Exception:
            _eq_bh = None

        # ── Graphique ─────────────────────────────────────────────────────────
        _pass_lbl = {"best": "Meilleure", "median": "Médiane", "worst": "Pire"}.get(_eq_pass, _eq_pass)
        fig_eq = go.Figure()
        fig_eq.add_scatter(
            x=_eq_s.index, y=_eq_s.values,
            name=f"{EA_CONFIG[_eq_robot]['label']} — {_pass_lbl} passe",
            line=dict(color="#4FC3F7", width=2),
            hovertemplate="Date : %{x|%Y-%m-%d}<br>Capital : $%{y:,.0f}<extra></extra>",
        )
        if _eq_bh is not None:
            fig_eq.add_scatter(
                x=_eq_bh.index, y=_eq_bh.values,
                name=f"Buy & Hold — {ASSET_LABELS.get(_eq_actif, _eq_actif)}",
                line=dict(color="#9E9E9E", width=1.5, dash="dash"),
                hovertemplate="Date : %{x|%Y-%m-%d}<br>B&H : $%{y:,.0f}<extra></extra>",
            )
        fig_eq.add_hline(
            y=_initial_cap, line_dash="dot",
            line_color="rgba(255,255,255,0.3)", line_width=1,
            annotation_text=f"Capital initial ${_initial_cap:,.0f}",
            annotation_position="right",
        )
        _eq_title = (
            f"{EA_CONFIG[_eq_robot]['label']} / {ASSET_LABELS.get(_eq_actif, _eq_actif)} / "
            f"{_eq_tf} / {_FOLD_OOS.get(_eq_pli, f'Pli {_eq_pli}')} — {_pass_lbl} passe"
        )
        fig_eq.update_layout(**PLOTLY_DARK)
        fig_eq.update_layout(
            height=480,
            title=_eq_title,
            yaxis_title="Capital ($)",
            xaxis_title="Date OOS",
            legend=dict(orientation="h", y=1.10),
            margin=dict(l=20, r=80, t=60, b=20),
        )
        _eq_key = f"eq_{_eq_robot}_{_eq_actif}_{_eq_tf}_{_eq_pli}_{_eq_pass}"
        st_plotly(fig_eq, _eq_key, filename=_eq_title, num=42)

        # ── Métriques rapides ─────────────────────────────────────────────────
        _eq_final = float(_eq_s.iloc[-1])
        _eq_ret   = (_eq_final - _initial_cap) / _initial_cap * 100
        _eq_peak  = float(_eq_s.cummax().iloc[-1])
        _eq_dd    = float((((_eq_s - _eq_s.cummax()) / _eq_s.cummax()) * 100).min())
        _mc1, _mc2, _mc3, _mc4 = st.columns(4)
        _mc1.metric("Capital initial",  f"${_initial_cap:,.0f}")
        _mc2.metric("Capital final",    f"${_eq_final:,.0f}", delta=f"{_eq_ret:+.1f}%")
        _mc3.metric("MaxDD Stratégie",  f"{_eq_dd:.1f}%")
        if _eq_bh is not None:
            _bh_ret = (float(_eq_bh.iloc[-1]) - _initial_cap) / _initial_cap * 100
            _mc4.metric("Rdt B&H",
                        f"{_bh_ret:+.1f}%",
                        delta=f"Écart strat {_eq_ret - _bh_ret:+.1f}%")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — TABLEAU DÉTAILLÉ
# ══════════════════════════════════════════════════════════════════════════════
with tab_detail:
    st.markdown("### Tableau Détaillé")
    st.markdown("Une ligne = stratégie × actif × pli OOS.")

    df_show = df_comp.copy()
    df_show["Pli OOS"] = df_show["Pli"].map(_FOLD_OOS)
    df_show["Actif"]   = df_show["Actif"].map(ASSET_LABELS).fillna(df_show["Actif"])

    # Indicateur visuel pour B&H non roll-ajusté
    df_show["B&H Fiable"] = df_show["B&H Roll-Adj"].map(lambda v: "✅" if v else "⚠️")

    # Filtres rapides
    c1, c2 = st.columns(2)
    with c1:
        sel_s = st.multiselect(
            "Stratégies", df_show["Stratégie"].unique(),
            default=list(df_show["Stratégie"].unique()), key="bh_strat",
        )
    with c2:
        sel_a = st.multiselect(
            "Actifs", df_show["Actif"].unique(),
            default=list(df_show["Actif"].unique()), key="bh_actif",
        )

    df_show = df_show[df_show["Stratégie"].isin(sel_s) & df_show["Actif"].isin(sel_a)]

    cols_order = [
        "Stratégie", "Famille", "Actif", "Pli OOS",
        "Rdt OOS % (méd)", "Rdt B&H %", "MaxDD B&H %", "Excédent %", "B&H Fiable",
    ]
    df_show = df_show[[c for c in cols_order if c in df_show.columns]].sort_values(
        ["Actif", "Pli OOS", "Excédent %"], ascending=[True, True, False]
    )

    st.dataframe(
        df_show, use_container_width=True, hide_index=True, height=600,
        column_config={
            "Rdt OOS % (méd)": st.column_config.NumberColumn("Rdt OOS % (méd)", format="%.2f %%"),
            "Rdt B&H %":       st.column_config.NumberColumn("Rdt B&H %",        format="%.2f %%"),
            "MaxDD B&H %":     st.column_config.NumberColumn("MaxDD B&H %",       format="%.2f %%"),
            "Excédent %":      st.column_config.NumberColumn("Excédent %",        format="%+.2f %%"),
            "B&H Fiable":      st.column_config.TextColumn("Roll-Adj"),
        },
    )

    # ── B&H de référence avec MaxDD ───────────────────────────────────────────
    st.markdown("#### Rendements Buy&Hold de référence (roll-ajusté)")
    bh_rows = []
    for actif in ALL_ASSETS:
        for fold_n in _ALL_FOLDS:
            rdt = _bh_field(bh_data, actif, fold_n, "rdt")
            dd  = _bh_field(bh_data, actif, fold_n, "max_dd")
            ok  = _bh_field(bh_data, actif, fold_n, "roll_adjusted")
            if rdt is not None:
                bh_rows.append({
                    "Actif":       ASSET_LABELS.get(actif, actif),
                    "Pli OOS":     _FOLD_OOS.get(fold_n, f"Pli {fold_n}"),
                    "Rdt B&H %":   rdt,
                    "MaxDD B&H %": dd,
                    "Roll-Ajusté": "✅" if ok else "⚠️",
                })

    if bh_rows:
        df_bh = pd.DataFrame(bh_rows)
        st.dataframe(
            df_bh, use_container_width=True, hide_index=True,
            column_config={
                "Rdt B&H %":   st.column_config.NumberColumn("Rdt B&H %",   format="%.2f %%"),
                "MaxDD B&H %": st.column_config.NumberColumn("MaxDD B&H %", format="%.2f %%"),
                "Roll-Ajusté": st.column_config.TextColumn("Roll-Ajusté"),
            },
        )
    else:
        st.info("ℹ️ Aucun CSV D1 local trouvé dans `TB-Python/` — rendements B&H non disponibles.")

    # ── DJUBS de référence ────────────────────────────────────────────────────
    st.markdown(
        "#### Benchmark global — DJUBS (Excess Return)  \n"
        "<small>*Roll yield inclus, sans collatéral T-Bill. "
        "⚠️ Données avant le 2009-06-18 exclues (anomalie d'échelle dans le fichier source).*</small>",
        unsafe_allow_html=True,
    )
    dj_detail_rows = [
        {
            "Pli OOS":     _FOLD_OOS.get(n, f"Pli {n}"),
            "Rdt DJUBS %": (dj_data.get(n) or {}).get("rdt"),
            "MaxDD DJUBS %": (dj_data.get(n) or {}).get("max_dd"),
        }
        for n in _ALL_FOLDS
        if dj_data.get(n) is not None
    ]
    if dj_detail_rows:
        df_dj_detail = pd.DataFrame(dj_detail_rows)
        st.dataframe(
            df_dj_detail, use_container_width=False, hide_index=True,
            column_config={
                "Rdt DJUBS %":   st.column_config.NumberColumn("Rdt DJUBS %",   format="%.2f %%"),
                "MaxDD DJUBS %": st.column_config.NumberColumn("MaxDD DJUBS %", format="%.2f %%"),
            },
        )
    else:
        st.info("ℹ️ Données DJUBS non disponibles — vérifiez `TB-MT5/Bloomberg_Commodity_Index.csv`.")
