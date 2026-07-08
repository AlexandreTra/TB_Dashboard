"""
Vue Globale — Screening des 6 stratégies × 6 actifs × 3 TF × 3 plis.

Tab 1 : Tableau de screening complet (filtrable)
Tab 2 : Heatmap Robot × Actif (par TF)
Tab 3 : Comparaison IS vs OOS
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.constants import GLOBAL_CSS, PLOTLY_DARK
from core.mt5_runner import EA_CONFIG, FOLDS, TIMEFRAMES
from core.ui_helpers import chart_badge, st_plotly

# ── Constantes ────────────────────────────────────────────────────────────────
_TF_ORDER     = ["H1", "H4", "D1"]
_FOLD_LABELS  = {f["n"]: f"Pli {f['n']}" for f in FOLDS}
_ROBOT_ORDER  = list(EA_CONFIG.keys())
_ROBOT_LABELS = {k: v["label"] for k, v in EA_CONFIG.items()}


def _wfe_color(val):
    try:
        if pd.isna(val):
            return "background-color: #555"
        v = float(val)
    except (TypeError, ValueError):
        return ""
    if v >= 80:
        return "background-color: #1B5E20; color: white"
    if v >= 50:
        return "background-color: #F9A825; color: black"
    return "background-color: #B71C1C; color: white"


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Vue Globale", page_icon="🌐", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
st.title("🌐 Vue Globale")
st.markdown(
    "Screening de toutes les combinaisons "
    "**6 stratégies × 6 actifs × 3 timeframes × 3 plis Walk-Forward**."
)

# ── Guard ─────────────────────────────────────────────────────────────────────
df_kpi: pd.DataFrame | None = st.session_state.get("df_kpi")
if df_kpi is None or df_kpi.empty:
    st.warning("⚠️ Aucune donnée. Retournez à l'**Accueil** et cliquez **Charger les Résultats**.")
    st.stop()

if "robot" not in df_kpi.columns:
    st.error("Format de données obsolète. Revenez à l'**Accueil** et rechargez.")
    st.stop()

# ── Sidebar — Filtres ─────────────────────────────────────────────────────────
st.sidebar.header("Filtres")

all_robots = sorted(
    df_kpi["robot"].unique(),
    key=lambda r: _ROBOT_ORDER.index(r) if r in _ROBOT_ORDER else 99,
)
sel_robots = st.sidebar.multiselect(
    "Stratégies",
    options=all_robots,
    default=all_robots,
    format_func=lambda r: _ROBOT_LABELS.get(r, r),
)

all_actifs = sorted(df_kpi["actif_clean"].unique())
sel_actifs = st.sidebar.multiselect("Actifs", options=all_actifs, default=all_actifs)

sel_tfs = st.sidebar.multiselect(
    "Timeframes",
    options=_TF_ORDER,
    default=[tf for tf in _TF_ORDER if tf in df_kpi["timeframe"].unique()],
)

all_plis = sorted(df_kpi["pli"].unique())
sel_plis = st.sidebar.multiselect(
    "Plis",
    options=all_plis,
    default=all_plis,
    format_func=lambda n: _FOLD_LABELS.get(n, f"Pli {n}"),
)

_HEATMAP_METRICS = {
    "Score OOS (médian)":        "OOS_Score_Med",
    "Rdt OOS % (médian)":        "OOS_Return_Med_Pct",
    "% Passes Profitables OOS":  "OOS_Pct_Prof",
    "WFE %":                     "WFE_Pct",
    "Sharpe OOS (médian)":       "OOS_Sharpe_Med",
    "DD% OOS (médian)":          "OOS_DD_Med",
}
heatmap_label = st.sidebar.selectbox("Métrique heatmap", list(_HEATMAP_METRICS.keys()), index=0)
heatmap_col   = _HEATMAP_METRICS[heatmap_label]

# ── Filtrage ──────────────────────────────────────────────────────────────────
mask = (
    df_kpi["robot"].isin(sel_robots) &
    df_kpi["actif_clean"].isin(sel_actifs) &
    df_kpi["timeframe"].isin(sel_tfs) &
    df_kpi["pli"].isin(sel_plis)
)
df_f = df_kpi[mask].copy()

if df_f.empty:
    st.warning("Aucun résultat pour cette sélection.")
    st.stop()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📋 Tableau Screening", "🗺️ Heatmap", "📊 IS vs OOS"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — TABLEAU SCREENING
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    _n_loaded = len(df_f)
    st.markdown(f"**{_n_loaded} combinaisons affichées** — une ligne = stratégie × actif × TF × pli.")
    # ── Note sur le comptage (288 dans le mémoire vs affiché ici) ────────────
    # 288 = 6 robots × 6 actifs × 3 TF × 3 plis (324 max) − 36 combos D1 exclus
    # pour MR et ZS (aucun trade généré en D1 sur ces actifs = 2×6×1×3 = 36).
    # Le nombre affiché ici peut être inférieur car il ne compte que les fichiers
    # XML effectivement chargés ET ayant passé le filtre min_trades (≥30 trades).
    with st.expander("ℹ️ Pourquoi ce nombre diffère du mémoire (288 combinaisons évaluées) ?"):
        st.markdown(
            """
**Comptage théorique vs données chargées :**

| | Valeur | Explication |
|---|---|---|
| Maximum théorique | **324** | 6 robots × 6 actifs × 3 TF × 3 plis |
| Évalué dans le mémoire | **288** | −36 : MR et ZS exclus du D1 (aucun trade généré) |
| Affiché ici | **{}** | Fichiers XML présents × filtre min_trades ≥ {} trades |

**Causes de l'écart entre 288 et la valeur affichée :**
1. Seules les combinaisons avec un fichier XML dans `Résultats_FT/` sont comptées.
2. Le filtre *Trades minimum par passe* (réglé à l'Accueil) exclut les combinaisons inactives.
3. Les combos D1 pour MR et ZS sont inclus dans le chargement mais produisent souvent 0 trade → exclus par le filtre.
            """.format(_n_loaded, st.session_state.get("_min_trades_last", 30))
        )

    display_map = {
        "robot_label":         "Stratégie",
        "actif_clean":         "Actif",
        "timeframe":           "TF",
        "pli":                 "Pli",
        "pli_is":              "IS",
        "pli_oos":             "OOS",
        "Nb_Passes_IS":        "Passes IS",
        "IS_Score_Med":        "Score IS méd",
        "IS_Pct_Prof":         "% Prof IS",
        "IS_Return_Med_Pct":   "Rdt IS % méd",
        "Nb_Passes_OOS":       "Passes OOS",
        "OOS_Score_Med":       "Score OOS méd",
        "OOS_Pct_Prof":        "% Prof OOS",
        "OOS_Return_Med_Pct":  "Rdt OOS % méd",
        "WFE_Pct":             "WFE %",
        "OOS_Sharpe_Med":      "Sharpe OOS",
        "OOS_DD_Med":          "DD% OOS",
    }
    cols_present = [c for c in display_map if c in df_f.columns]
    df_disp = df_f[cols_present].rename(columns=display_map).copy()

    col_cfg: dict = {}
    pct_fmt_cols = {"% Prof IS", "% Prof OOS", "WFE %"}
    ret_fmt_cols = {"Rdt IS % méd", "Rdt OOS % méd"}
    for dst in df_disp.columns:
        if dst in pct_fmt_cols:
            col_cfg[dst] = st.column_config.NumberColumn(dst, format="%.1f %%")
        elif dst in ret_fmt_cols:
            col_cfg[dst] = st.column_config.NumberColumn(dst, format="%.2f %%")
        elif dst in {"Sharpe OOS", "DD% OOS"}:
            col_cfg[dst] = st.column_config.NumberColumn(dst, format="%.2f")

    chart_badge(2)
    st.dataframe(df_disp, use_container_width=True, height=600, column_config=col_cfg)

    # Vue consolidée sur les plis
    agg_cols = [c for c in ["OOS_Return_Med_Pct", "OOS_Pct_Prof", "WFE_Pct",
                             "OOS_Sharpe_Med", "OOS_DD_Med"] if c in df_f.columns]
    if agg_cols:
        chart_badge(3)
        st.markdown("#### Vue consolidée — Moyenne des plis par (Stratégie × Actif × TF)")
        df_cons = (
            df_f.groupby(["robot_label", "actif_clean", "timeframe"])[agg_cols]
            .mean().round(2).reset_index()
            .rename(columns={
                "robot_label":        "Stratégie",
                "actif_clean":        "Actif",
                "timeframe":          "TF",
                "OOS_Return_Med_Pct": "Rdt OOS % méd",
                "OOS_Pct_Prof":       "% Prof OOS",
                "WFE_Pct":            "WFE %",
                "OOS_Sharpe_Med":     "Sharpe OOS",
                "OOS_DD_Med":         "DD% OOS",
            })
        )
        st.dataframe(df_cons, use_container_width=True, height=380)

    # ── Vue d'ensemble : profitabilité par actif, toutes familles confondues ──
    _has_rdt  = "OOS_Return_Med_Pct" in df_f.columns
    _has_prof = "OOS_Pct_Prof" in df_f.columns
    if _has_rdt or _has_prof:
        st.markdown("#### Vue d'ensemble — Profitabilité par actif *(toutes stratégies × TF × plis)*")
        st.caption(
            "Barre bleue : % de combinaisons avec un rendement OOS médian positif.  "
            "Barre verte : % de combinaisons où la majorité des passes OOS sont profitables (>50 %).  "
            "Pointillé = seuil 50 %."
        )

        _agg_parts: dict = {}
        if _has_rdt:
            _agg_parts["rdt_pos"]  = ("OOS_Return_Med_Pct", lambda s: (s > 0).mean() * 100)
        if _has_prof:
            _agg_parts["pct_prof"] = ("OOS_Pct_Prof",       lambda s: (s > 50).mean() * 100)

        _agg = (
            df_f.groupby("actif_clean")
            .agg(**_agg_parts)
            .reset_index()
            .sort_values(next(iter(_agg_parts)), ascending=False)
        )

        fig_ov = go.Figure()
        if "rdt_pos" in _agg.columns:
            fig_ov.add_bar(
                name="Rdt OOS méd > 0 %",
                x=_agg["actif_clean"],
                y=_agg["rdt_pos"].round(1),
                marker_color="#4FC3F7",
                opacity=0.88,
                text=(_agg["rdt_pos"].round(0).astype(int).astype(str) + " %"),
                textposition="outside",
            )
        if "pct_prof" in _agg.columns:
            fig_ov.add_bar(
                name="Majorité passes prof (> 50 %)",
                x=_agg["actif_clean"],
                y=_agg["pct_prof"].round(1),
                marker_color="#81C784",
                opacity=0.88,
                text=(_agg["pct_prof"].round(0).astype(int).astype(str) + " %"),
                textposition="outside",
            )
        fig_ov.add_hline(
            y=50,
            line_dash="dash",
            line_color="rgba(255,255,255,0.45)",
            line_width=1,
            annotation_text="50 %",
            annotation_position="top right",
            annotation_font_color="rgba(255,255,255,0.55)",
        )
        fig_ov.update_layout(**PLOTLY_DARK)
        fig_ov.update_layout(
            barmode="group",
            height=420,
            yaxis=dict(title="% des combinaisons", range=[0, 115]),
            xaxis_title="Actif",
            margin=dict(l=20, r=80, t=10, b=20),
            legend=dict(orientation="h", y=1.08),
        )
        st_plotly(fig_ov, "vg_actif_profitable", num=4)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — HEATMAP Robot × Actif
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown(f"### Heatmap — {heatmap_label}")
    st.markdown("Une heatmap par timeframe. Lignes = Stratégies, Colonnes = Actifs. Valeur = moyenne des plis sélectionnés.")

    _TF_CHART_NUMS = {"H1": 5, "H4": 6, "D1": 7}
    tfs_avail = [tf for tf in _TF_ORDER if tf in df_f["timeframe"].unique()]
    if not tfs_avail:
        st.warning("Aucun timeframe dans la sélection.")
    elif heatmap_col not in df_f.columns:
        st.warning(f"Colonne `{heatmap_col}` non disponible.")
    else:
        for tf in tfs_avail:
            df_tf = df_f[df_f["timeframe"] == tf]
            if df_tf.empty:
                continue

            pivot = (
                df_tf.groupby(["robot_label", "actif_clean"])[heatmap_col]
                .mean()
                .unstack("actif_clean")
            )
            # Ordonner les lignes
            rl_order = [_ROBOT_LABELS[r] for r in _ROBOT_ORDER if _ROBOT_LABELS[r] in pivot.index]
            pivot = pivot.reindex(rl_order)

            colorscale = "RdYlGn_r" if heatmap_col == "OOS_DD_Med" else "RdYlGn"
            midpoint   = 0.0 if "Return" in heatmap_col or "WFE" in heatmap_col else None

            fig = px.imshow(
                pivot,
                color_continuous_scale=colorscale,
                color_continuous_midpoint=midpoint,
                text_auto=".1f",
                title=f"TF : {tf}  —  {heatmap_label}",
                labels={"x": "Actif", "y": "Stratégie", "color": heatmap_label},
                aspect="auto",
            )
            fig.update_layout(**PLOTLY_DARK)
            fig.update_layout(height=320, margin=dict(l=10, r=10, t=50, b=10))
            fig.update_traces(textfont_size=12)
            st_plotly(fig, f"hm_{tf}", num=_TF_CHART_NUMS.get(tf))


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — IS vs OOS
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    is_col  = "IS_Return_Med_Pct"
    oos_col = "OOS_Return_Med_Pct"

    if is_col not in df_f.columns or oos_col not in df_f.columns:
        st.warning("Colonnes IS/OOS non disponibles dans les données chargées.")
    else:
        st.markdown("### Rendement médian IS vs OOS par stratégie")
        st.markdown(
            "Un bon système conserve des performances proches en OOS. "
            "IS >>> OOS = signal de sur-optimisation."
        )

        # ── Bar chart groupé par stratégie × TF ──────────────────────────────
        df_bar = (
            df_f.groupby(["robot_label", "timeframe"])[[is_col, oos_col]]
            .mean().round(2).reset_index()
        )
        df_bar["label"] = df_bar["robot_label"] + " / " + df_bar["timeframe"]
        df_bar = df_bar.sort_values(oos_col, ascending=False)

        fig_bar = go.Figure()
        fig_bar.add_bar(
            name="Rdt IS % méd", x=df_bar["label"], y=df_bar[is_col],
            marker_color="#4FC3F7", opacity=0.8,
        )
        fig_bar.add_bar(
            name="Rdt OOS % méd", x=df_bar["label"], y=df_bar[oos_col],
            marker_color="#81C784", opacity=0.9,
        )
        fig_bar.update_layout(**PLOTLY_DARK)
        fig_bar.update_layout(
            barmode="group", height=460,
            xaxis_tickangle=-40, yaxis_title="Rendement Médian (%)",
            legend=dict(orientation="h", y=1.08),
            margin=dict(l=20, r=20, t=20, b=130),
        )
        st_plotly(fig_bar, "isoos_bar", num=8)

        # ── WFE table ─────────────────────────────────────────────────────────
        if "WFE_Pct" in df_f.columns:
            chart_badge(9)
            st.markdown("#### WFE % par (Stratégie × TF) — moyenne des plis et actifs")
            df_wfe = (
                df_f.groupby(["robot_label", "timeframe"])["WFE_Pct"]
                .mean().round(1).unstack("timeframe")
                .reindex(columns=[tf for tf in _TF_ORDER if tf in df_f["timeframe"].unique()])
            )
            rl_order = [_ROBOT_LABELS[r] for r in _ROBOT_ORDER if _ROBOT_LABELS[r] in df_wfe.index]
            df_wfe   = df_wfe.reindex(rl_order)
            # Affichage simple sans Styler pour éviter les problèmes de compatibilité
            st.dataframe(
                df_wfe.rename(columns=lambda c: f"{c}"),
                use_container_width=True,
                column_config={
                    c: st.column_config.NumberColumn(c, format="%.1f %%")
                    for c in df_wfe.columns
                },
            )

        # ── Scatter IS vs OOS ─────────────────────────────────────────────────
        st.markdown("#### Scatter IS vs OOS — chaque point = 1 combinaison")
        hover_cols = ["actif_clean", "pli"]
        if "WFE_Pct" in df_f.columns:
            hover_cols.append("WFE_Pct")

        fig_sc = px.scatter(
            df_f,
            x=is_col, y=oos_col,
            color="robot_label", symbol="timeframe",
            hover_data=hover_cols,
            labels={
                is_col:        "Rdt IS % (médian)",
                oos_col:       "Rdt OOS % (médian)",
                "robot_label": "Stratégie",
            },
        )
        # Ligne IS = OOS
        all_vals = pd.concat([df_f[is_col], df_f[oos_col]]).dropna()
        if len(all_vals) > 0:
            lo, hi = float(all_vals.min()), float(all_vals.max())
            if lo < hi:
                fig_sc.add_shape(
                    type="line", x0=lo, y0=lo, x1=hi, y1=hi,
                    line=dict(color="rgba(255,255,255,0.4)", dash="dash", width=1),
                )
        fig_sc.update_layout(**PLOTLY_DARK)
        fig_sc.update_layout(height=480, margin=dict(l=20, r=20, t=20, b=20))
        st_plotly(fig_sc, "isoos_scatter", num=10)
