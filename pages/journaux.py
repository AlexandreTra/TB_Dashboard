"""
Journaux de Trades — Analyse mensuelle et comparaison croisée.

Les journaux sont générés depuis ⚙️ Lancer MT5 → Backtests Individuels.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config_analyse import FAMILY_COLORS, OOS_LABELS
from core.constants import GLOBAL_CSS, PLOTLY_DARK
from core.ui_helpers import chart_badge, st_plotly
from core.mt5_runner import EA_CONFIG, SYMBOLS
from core.single_run import OUTPUT_DETAIL, detail_status, load_all_detail_trades

st.set_page_config(page_title="Journaux de Trades", page_icon="📋", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# ── Constantes ────────────────────────────────────────────────────────────────
_ROBOT_LABELS = {k: v["label"] for k, v in EA_CONFIG.items()}
_ROBOT_FAMILY = {
    "ATR":  "Breakout",
    "BK":   "Breakout",
    "MA":   "Trend Following",
    "TEMA": "Trend Following",
    "MR":   "Mean Reversion",
    "ZS":   "Mean Reversion",
}
_ASSET_LABELS = {
    "BRENT":      "Brent",
    "NATURALGAS": "Gaz Naturel",
    "GOLD":       "Or",
    "PLATINUM":   "Platine",
    "COFFEE":     "Café",
    "COCOA":      "Cacao",
}
_ASSET_FAMILY = {
    "BRENT":      "Énergie",
    "NATURALGAS": "Énergie",
    "GOLD":       "Métaux",
    "PLATINUM":   "Métaux",
    "COFFEE":     "Agricole",
    "COCOA":      "Agricole",
}
_MONTH_NAMES = [
    "Jan", "Fév", "Mar", "Avr", "Mai", "Jun",
    "Jul", "Aoû", "Sep", "Oct", "Nov", "Déc",
]
_ALL_ROBOTS = list(EA_CONFIG.keys())
_ALL_ASSETS = [s.replace(".TB", "") for s in SYMBOLS]

# ── Guard ─────────────────────────────────────────────────────────────────────
if st.session_state.get("df_kpi") is None:
    st.warning("⚠️ Aucune donnée chargée. Retournez à l'**Accueil**.")
    st.stop()

# ── Header ────────────────────────────────────────────────────────────────────
st.title("📋 Journaux de Trades")
st.markdown(
    "Analyse mensuelle et comparative des trades issue des backtests individuels.  \n"
    "Pour générer les journaux : **⚙️ Lancer MT5** → onglet **Backtests Individuels**."
)

# ── Sélecteurs d'analyse ──────────────────────────────────────────────────────
with st.expander("🔧 Filtres", expanded=True):
    _c1, _c2, _c3 = st.columns(3)
    with _c1:
        sel_robots = st.multiselect(
            "Robots", _ALL_ROBOTS, default=_ALL_ROBOTS,
            format_func=lambda r: _ROBOT_LABELS[r], key="jrnl_robots",
        )
    with _c2:
        sel_assets = st.multiselect(
            "Actifs", _ALL_ASSETS, default=_ALL_ASSETS,
            format_func=lambda a: _ASSET_LABELS.get(a, a), key="jrnl_assets",
        )
    with _c3:
        sel_tf = st.selectbox("Timeframe", ["H1", "H4"], key="jrnl_tf")

# ── Statut des données disponibles ───────────────────────────────────────────
_combos = [
    {"robot": r, "actif_tb": f"{a}.TB", "tf": sel_tf, "pli": p}
    for r in sel_robots for a in sel_assets for p in [1, 2, 3]
]
_status = detail_status(_combos, OUTPUT_DETAIL)
_n_done = sum(1 for v in _status.values() if v == "done")
_n_total = len(_status)

c1, c2, c3 = st.columns(3)
c1.metric("Runs disponibles", _n_done)
c2.metric("Runs manquants",   _n_total - _n_done)
c3.metric("Couverture",
          f"{_n_done / _n_total * 100:.0f} %" if _n_total else "—")

if _n_done == 0:
    st.info(
        "⏳ Aucun journal disponible pour cette sélection.  \n"
        "Allez dans **⚙️ Lancer MT5 → Backtests Individuels** pour les générer."
    )
    st.stop()

st.divider()

# ── Chargement des trades ─────────────────────────────────────────────────────
with st.spinner("Chargement des journaux…"):
    df_raw = load_all_detail_trades(_combos, OUTPUT_DETAIL)

if df_raw.empty or "Time" not in df_raw.columns or "Profit" not in df_raw.columns:
    st.warning("Aucun trade parsé — vérifiez les fichiers XML dans `Résultats_Detail/`.")
    st.stop()

# Colonnes dérivées
df_raw["month"]      = df_raw["Time"].dt.month
df_raw["month_name"] = df_raw["month"].apply(lambda m: _MONTH_NAMES[m - 1])
df_raw["month_name"] = pd.Categorical(df_raw["month_name"], categories=_MONTH_NAMES, ordered=True)
df_raw["pli_label"]  = df_raw["pli"].map(OOS_LABELS)
df_raw["win"]        = (df_raw["Profit"] > 0).astype(int)
df_raw["Actif"]      = df_raw["actif_clean"].map(_ASSET_LABELS)
df_raw["Classe"]     = df_raw["actif_clean"].map(_ASSET_FAMILY)
df_raw["Robot"]      = df_raw["robot"].map(_ROBOT_LABELS)
df_raw["Famille"]    = df_raw["robot"].map(_ROBOT_FAMILY)
df_raw["Passe"]      = df_raw["pass_label"].map(
    {"best": "Meilleure", "median": "Médiane", "worst": "Pire"}
)

st.caption(
    f"**{len(df_raw):,} trades** chargés · "
    f"{df_raw['robot'].nunique()} robots · "
    f"{df_raw['actif_clean'].nunique()} actifs · {sel_tf}"
)

# ══════════════════════════════════════════════════════════════════════════════
# ONGLETS D'ANALYSE
# ══════════════════════════════════════════════════════════════════════════════
tab_mensuel, tab_cross = st.tabs([
    "📅 Analyse Mensuelle",
    "🔀 Comparaison Croisée",
])

# ── Filtres fins (communs aux deux onglets) ───────────────────────────────────
_fa, _fb = st.columns(2)
with _fa:
    _fam_sel = st.multiselect(
        "Famille de stratégie",
        sorted(df_raw["Famille"].dropna().unique()),
        default=sorted(df_raw["Famille"].dropna().unique()),
        key="jrnl_fam",
    )
with _fb:
    _cls_sel = st.multiselect(
        "Classe d'actif",
        sorted(df_raw["Classe"].dropna().unique()),
        default=sorted(df_raw["Classe"].dropna().unique()),
        key="jrnl_cls",
    )

df = df_raw.copy()
if _fam_sel:
    df = df[df["Famille"].isin(_fam_sel)]
if _cls_sel:
    df = df[df["Classe"].isin(_cls_sel)]

if df.empty:
    st.info("Aucun trade pour cette combinaison de filtres.")
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
with tab_mensuel:
    st.markdown("#### Heatmap P&L moyen par actif × mois")
    hm1 = (
        df.groupby(["actif_clean", "month"])["Profit"]
        .mean().unstack("month").reindex(columns=range(1, 13))
    )
    hm1.index   = [_ASSET_LABELS.get(i, i) for i in hm1.index]
    hm1.columns = _MONTH_NAMES
    fig_hm1 = go.Figure(data=go.Heatmap(
        z=hm1.values, x=_MONTH_NAMES, y=list(hm1.index),
        colorscale="RdYlGn", zmid=0,
        text=[[f"${v:.0f}" if not np.isnan(v) else "" for v in row] for row in hm1.values],
        texttemplate="%{text}",
        colorbar=dict(title="P&L moy ($)", tickformat="$.0f"),
        hovertemplate="%{y} · %{x} : $%{z:.0f}<extra></extra>",
    ))
    fig_hm1.update_layout(
        height=max(280, len(hm1) * 45 + 80),
        title="P&L moyen par trade — actif × mois calendaire",
        **PLOTLY_DARK,
    )
    st_plotly(fig_hm1, "jrnl_hm1", num=76)

    st.markdown("#### Heatmap P&L moyen par famille de stratégie × mois")
    hm2 = (
        df.groupby(["Famille", "month"])["Profit"]
        .mean().unstack("month").reindex(columns=range(1, 13))
    )
    hm2.columns = _MONTH_NAMES
    fig_hm2 = go.Figure(data=go.Heatmap(
        z=hm2.values, x=_MONTH_NAMES, y=list(hm2.index),
        colorscale="RdYlGn", zmid=0,
        text=[[f"${v:.0f}" if not np.isnan(v) else "" for v in row] for row in hm2.values],
        texttemplate="%{text}",
        colorbar=dict(title="P&L moy ($)", tickformat="$.0f"),
        hovertemplate="%{y} · %{x} : $%{z:.0f}<extra></extra>",
    ))
    fig_hm2.update_layout(
        height=260, title="P&L moyen par trade — famille × mois", **PLOTLY_DARK,
    )
    st_plotly(fig_hm2, "jrnl_hm2", num=77)

    st.markdown("#### Distribution mensuelle interactive")
    _color_by = st.radio(
        "Couleur par :", ["Actif", "Famille", "Classe"],
        horizontal=True, key="jrnl_color",
    )
    monthly_bar = (
        df.groupby(["month_name", _color_by])["Profit"]
        .mean().reset_index().rename(columns={"Profit": "P&L moy ($)"})
    )
    fig_bar = px.bar(
        monthly_bar, x="month_name", y="P&L moy ($)", color=_color_by,
        barmode="group",
        color_discrete_map=FAMILY_COLORS if _color_by == "Famille" else None,
        labels={"month_name": "Mois"},
        title=f"P&L moyen par mois — par {_color_by.lower()}",
    )
    fig_bar.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.3)", line_width=1)
    fig_bar.update_layout(height=420, **PLOTLY_DARK)
    st_plotly(fig_bar, "jrnl_bar", num=78)

    chart_badge(79)
    st.markdown("#### Tableau récapitulatif par actif × mois")
    tbl = (
        df.groupby(["Actif", "month"])
        .agg(N=("Profit", "count"), PnL_moy=("Profit", "mean"),
             PnL_tot=("Profit", "sum"), Win=("win", "mean"))
        .reset_index()
    )
    tbl["Mois"]       = tbl["month"].apply(lambda m: _MONTH_NAMES[m - 1])
    tbl["Win %"]      = (tbl["Win"] * 100).round(1)
    tbl["P&L moy"]    = tbl["PnL_moy"].round(0)
    tbl["P&L total"]  = tbl["PnL_tot"].round(0)
    st.dataframe(
        tbl[["Actif", "Mois", "N", "P&L moy", "P&L total", "Win %"]],
        use_container_width=True, hide_index=True,
        column_config={
            "P&L moy":   st.column_config.NumberColumn(format="$%.0f"),
            "P&L total": st.column_config.NumberColumn(format="$%.0f"),
            "Win %":     st.column_config.NumberColumn(format="%.1f %%"),
        },
    )


# ══════════════════════════════════════════════════════════════════════════════
with tab_cross:
    st.markdown("#### Classement robot × actif par P&L total OOS")
    rank = (
        df.groupby(["Robot", "Actif"])
        .agg(PnL=("Profit", "sum"), N=("Profit", "count"), Win=("win", "mean"), Moy=("Profit", "mean"))
        .reset_index().sort_values("PnL", ascending=False)
    )
    rank["Win %"] = (rank["Win"] * 100).round(1)
    rank["Rang"]  = range(1, len(rank) + 1)
    fig_rank = px.bar(
        rank.head(20), x="PnL", y="Robot", color="Actif",
        orientation="h", text_auto=".0f",
        labels={"PnL": "P&L total ($)", "Robot": ""},
        title="Top 20 robot × actif — P&L total (toutes passes et plis OOS)",
    )
    fig_rank.update_layout(height=500, **PLOTLY_DARK)
    st_plotly(fig_rank, "cross_rank", num=80)

    chart_badge(81)
    st.dataframe(
        rank[["Rang", "Robot", "Actif", "PnL", "Moy", "N", "Win %"]]
        .rename(columns={"PnL": "P&L total ($)", "Moy": "P&L moy ($)", "N": "N trades"}),
        use_container_width=True, hide_index=True,
        column_config={
            "P&L total ($)": st.column_config.NumberColumn(format="$%.0f"),
            "P&L moy ($)":   st.column_config.NumberColumn(format="$%.0f"),
            "Win %":         st.column_config.NumberColumn(format="%.1f %%"),
        },
    )

    st.markdown("#### Heatmap P&L moyen par trade — robot × actif")
    hm3 = df.groupby(["Robot", "actif_clean"])["Profit"].mean().unstack("actif_clean")
    hm3.columns = [_ASSET_LABELS.get(c, c) for c in hm3.columns]
    fig_hm3 = go.Figure(data=go.Heatmap(
        z=hm3.values, x=list(hm3.columns), y=list(hm3.index),
        colorscale="RdYlGn", zmid=0,
        text=[[f"${v:.0f}" if not np.isnan(v) else "" for v in row] for row in hm3.values],
        texttemplate="%{text}",
        colorbar=dict(title="P&L moy ($)", tickformat="$.0f"),
    ))
    fig_hm3.update_layout(
        height=max(280, len(hm3) * 50 + 80),
        title="P&L moyen par trade — robot × actif",
        **PLOTLY_DARK,
    )
    st_plotly(fig_hm3, "cross_hm", num=82)

    st.markdown("#### Robustesse — écart Meilleure vs Pire passe par actif")
    sp = (
        df[df["Passe"].isin(["Meilleure", "Pire"])]
        .groupby(["Actif", "Passe"])["Profit"].mean()
        .unstack("Passe").reset_index()
    )
    if "Meilleure" in sp.columns and "Pire" in sp.columns:
        sp["Écart ($)"] = (sp["Meilleure"] - sp["Pire"]).round(0)
        fig_sp = px.bar(
            sp.sort_values("Écart ($)", ascending=False),
            x="Actif", y="Écart ($)", color="Écart ($)",
            color_continuous_scale="RdYlGn", text_auto=".0f",
            title="Écart P&L moy (Meilleure − Pire passe) — robustesse par actif",
        )
        fig_sp.update_layout(height=360, **PLOTLY_DARK)
        st_plotly(fig_sp, "cross_spread", num=83)

    st.markdown("#### Dérive temporelle — P&L moyen par pli OOS")
    pli_df = (
        df.groupby(["pli", "Famille"])["Profit"]
        .mean().reset_index().rename(columns={"Profit": "P&L moy ($)"})
    )
    pli_df["Pli OOS"] = pli_df["pli"].map(OOS_LABELS)
    fig_pli = px.line(
        pli_df, x="Pli OOS", y="P&L moy ($)", color="Famille",
        markers=True, color_discrete_map=FAMILY_COLORS,
        title="Évolution du P&L moyen par pli OOS — par famille",
    )
    fig_pli.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.3)", line_width=1)
    fig_pli.update_layout(height=360, **PLOTLY_DARK)
    st_plotly(fig_pli, "cross_pli", num=84)
