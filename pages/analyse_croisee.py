"""
🔥 Analyse Croisée — Type × Actif × Timeframe
3 onglets : Heatmaps / Comparaisons / Carte Globale
"""
import pandas as pd
import plotly.express as px
import streamlit as st

from core.charts import (
    fig_heatmap_cross,
    fig_perf_map,
    fig_radar_symbols,
    fig_type_bar,
)
from core.constants import (
    COMMODITY_GROUP,
    GLOBAL_CSS,
    TYPE_COLOR,
    get_commodity_group,
)
from core.ui_helpers import st_plotly
from core.metrics import cross_analysis_pivot

st.set_page_config(page_title="Analyse Croisée", page_icon="🔥", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
st.title("🔥 Analyse Croisée — Type × Actif × Timeframe")
st.markdown("*Quelle famille algorithmique fonctionne le mieux sur quel actif et quel horizon ?*")

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
df_k = st.session_state["df_kpi"].copy()
df_k["Groupe"] = df_k["Symbole"].apply(get_commodity_group)
df_m = df_m.copy()
df_m["Groupe"] = df_m["Symbole"].apply(get_commodity_group)

TF_ORDER = ["M15", "H1", "H4", "Daily"]

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🔧 Options")
    metric_choice = st.selectbox(
        "Métrique principale",
        ["GHPR Moyen", "WFE (%)", "Survie GHPR>1 (%)", "Forward Return % Moy"],
    )
    top_n   = st.slider("Top N passes", 10, 1000, 150, 10)
    tf_dispo = ["Tous"] + sorted(df_m["Timeframe"].unique().tolist()) if "Timeframe" in df_m.columns else ["Tous"]
    sel_tf  = st.selectbox("Filtrer Timeframe", tf_dispo)

# ── Filtrage ──────────────────────────────────────────────────────────────────
df_m_f = df_m.copy()
if sel_tf != "Tous" and "Timeframe" in df_m_f.columns:
    df_m_f = df_m_f[df_m_f["Timeframe"] == sel_tf]

df_k_f = df_k.copy()
if sel_tf != "Tous" and "Timeframe" in df_k_f.columns:
    df_k_f = df_k_f[df_k_f["Timeframe"] == sel_tf]

metric_available = metric_choice in df_k_f.columns

# ── TABS ──────────────────────────────────────────────────────────────────────
tab_heat, tab_comp, tab_global = st.tabs([
    "🗺️ Heatmaps",
    "📊 Comparaisons",
    "🎯 Carte Globale",
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — HEATMAPS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_heat:
    # Heatmap Type × Symbole
    st.subheader(f"🗺️ {metric_choice} — Type × Symbole")
    st.markdown("Chaque cellule = valeur moyenne de la métrique pour cette combinaison.")
    if metric_available and not df_k_f.empty:
        pivot = cross_analysis_pivot(df_k_f, metric_choice)
        if not pivot.empty:
            st_plotly(
                fig_heatmap_cross(pivot, metric_choice, f"{metric_choice} — Type × Symbole"),
                "cross_hm_type_sym",
            )
        else:
            st.info("Pas assez de combinaisons pour la heatmap.")
    else:
        st.info(f"Métrique '{metric_choice}' non disponible.")

    st.divider()

    # Heatmap Type × Timeframe
    if "Timeframe" in df_k_f.columns and df_k_f["Timeframe"].nunique() > 1:
        st.subheader(f"⏱️ {metric_choice} — Type × Timeframe")
        st.markdown("Identifie si une famille de stratégie performe mieux sur certains horizons temporels.")
        tf_pivot = df_k_f.pivot_table(
            index="Type", columns="Timeframe",
            values=metric_choice, aggfunc="mean",
        )
        tf_order_present = [t for t in TF_ORDER if t in tf_pivot.columns]
        tf_pivot = tf_pivot[tf_order_present + [c for c in tf_pivot.columns if c not in tf_order_present]]
        if not tf_pivot.empty:
            st_plotly(
                fig_heatmap_cross(tf_pivot, metric_choice, f"{metric_choice} — Type × Timeframe"),
                "cross_hm_type_tf",
            )

    st.divider()

    # Heatmap Survie Type × Symbole
    st.subheader("🧬 Survie GHPR>1 (%) — Type × Symbole")
    st.markdown("Proportion de passes rentables en capitalisation composée, par combinaison.")
    if "Survie GHPR>1 (%)" in df_k_f.columns and not df_k_f.empty:
        survie_pivot = df_k_f.pivot_table(
            index="Type", columns="Symbole",
            values="Survie GHPR>1 (%)", aggfunc="mean",
        )
        if not survie_pivot.empty:
            st_plotly(
                fig_heatmap_cross(survie_pivot, "Survie GHPR>1 (%)", "Taux de Survie — Type × Symbole"),
                "cross_hm_survie",
            )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — COMPARAISONS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_comp:
    # Comparaison par Type
    st.subheader("📊 Quelle Famille de Stratégies Domine ?")
    col1, col2 = st.columns(2)
    with col1:
        st.caption("**GHPR Moyen par Type** — Un GHPR > 1.005 est significatif.")
        st_plotly(
            fig_type_bar(df_k_f, "GHPR Moyen", "GHPR Moyen par Type"),
            "comp_ghpr_type",
        )
    with col2:
        if "WFE (%)" in df_k_f.columns:
            st.caption("**WFE Moyen par Type** — WFE élevée = faible dégradation.")
            st_plotly(
                fig_type_bar(df_k_f, "WFE (%)", "WFE Moyen par Type"),
                "comp_wfe_type",
            )

    st.divider()

    # Comparaison par Symbole (bar horizontal)
    st.subheader("📦 Classement des Actifs")
    if "Symbole" in df_k_f.columns and not df_k_f.empty:
        agg_sym = (
            df_k_f.groupby("Symbole")
            .agg(GHPR=("GHPR Moyen", "mean"), WFE=("WFE (%)", "mean"))
            .reset_index()
            .sort_values("GHPR", ascending=False)
        )
        col_a, col_b = st.columns(2)
        with col_a:
            fig_sym = px.bar(
                agg_sym, x="GHPR", y="Symbole", orientation="h",
                color="GHPR", color_continuous_scale="RdYlGn",
                title="GHPR Moyen par Actif", text_auto=".5f",
            )
            fig_sym.add_vline(x=1.0, line_dash="dash", line_color="red", opacity=0.7)
            fig_sym.update_layout(coloraxis_showscale=False, height=320)
            st_plotly(fig_sym, "comp_sym_ghpr")
        with col_b:
            fig_wfe = px.bar(
                agg_sym.sort_values("WFE", ascending=False),
                x="WFE", y="Symbole", orientation="h",
                color="WFE", color_continuous_scale="RdYlGn",
                title="WFE Moyen par Actif (%)", text_auto=".1f",
            )
            fig_wfe.add_vline(x=50, line_dash="dash", line_color="orange", opacity=0.7)
            fig_wfe.update_layout(coloraxis_showscale=False, height=320)
            st_plotly(fig_wfe, "comp_sym_wfe")

    st.divider()

    # Performance par Groupe
    st.subheader("📦 Performance par Groupe d'Actifs")
    if "Groupe" in df_k_f.columns and not df_k_f.empty:
        grp_agg = (
            df_k_f.groupby(["Groupe", "Type"])
            .agg(
                GHPR_moy   =("GHPR Moyen",       "mean"),
                WFE_moy    =("WFE (%)",           "mean"),
                Survie_moy =("Survie GHPR>1 (%)", "mean"),
                N          =("Stratégie",          "count"),
            )
            .reset_index()
            .round(3)
            .sort_values("GHPR_moy", ascending=False)
        )
        st.dataframe(
            grp_agg,
            use_container_width=True,
            column_config={
                "GHPR_moy":   st.column_config.NumberColumn("GHPR Moyen", format="%.5f"),
                "WFE_moy":    st.column_config.NumberColumn("WFE %",      format="%.1f"),
                "Survie_moy": st.column_config.NumberColumn("Survie %",   format="%.1f"),
            },
        )

    st.divider()

    with st.expander("📋 Données brutes"):
        cols = [c for c in [
            "Stratégie", "Symbole", "Groupe", "Type", "Timeframe",
            "GHPR Moyen", "WFE (%)", "Survie GHPR>1 (%)",
            "Significatif", "Forward Return % Moy", "Nb Passes",
        ] if c in df_k_f.columns]
        st.dataframe(
            df_k_f[cols].sort_values("GHPR Moyen", ascending=False),
            use_container_width=True,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — CARTE GLOBALE
# ═══════════════════════════════════════════════════════════════════════════════
with tab_global:
    st.subheader("🎯 Carte Globale de Performance")
    st.markdown("""
| Zone | Interprétation |
|---|---|
| **Haut-droite** (WFE > 50 %, GHPR > 1) | ✅ Robuste et rentable — candidat live |
| **Haut-gauche** (WFE < 50 %, GHPR > 1) | ⚠️ Rentable mais sur-ajusté |
| **Bas-droite** (WFE > 50 %, GHPR < 1)  | 🔄 Robuste mais non rentable |
| **Bas-gauche** | ❌ À éliminer |
""")
    if not df_k_f.empty:
        st_plotly(fig_perf_map(df_k_f), "global_perf_map")

    st.divider()

    # Radar multi-symboles
    st.subheader("🕸️ Profil Multi-Métriques par Symbole")
    st.caption("Comparez la forme du profil de performance entre actifs.")
    symbols_dispo = df_k_f["Symbole"].unique().tolist()
    if symbols_dispo:
        sel_symbols = st.multiselect(
            "Sélectionnez les symboles", symbols_dispo,
            default=symbols_dispo[:min(5, len(symbols_dispo))],
            key="radar_croisee",
        )
        radar_metrics = [m for m in ["GHPR Moyen", "Survie GHPR>1 (%)", "WFE (%)"] if m in df_k_f.columns]
        if sel_symbols and len(radar_metrics) >= 2:
            st_plotly(
                fig_radar_symbols(df_k_f, sel_symbols, radar_metrics),
                "global_radar",
            )
