"""
🔬 Sensibilité des Paramètres — Robustesse vs Sur-Ajustement
3 onglets : Sensibilité / Cartographie 2D / Données
"""
import pandas as pd
import plotly.express as px
import streamlit as st
from scipy import stats as _stats

from core.charts import (
    fig_parallel_coords,
    fig_param_importance,
    fig_param_sensitivity,
)
from core.constants import GLOBAL_CSS
from core.ui_helpers import st_plotly
from core.metrics import param_importance, param_sensitivity
from core.parser import get_param_columns

st.set_page_config(page_title="Sensibilité Paramètres", page_icon="🔬", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
st.title("🔬 Sensibilité des Paramètres")
st.markdown(
    "Un système robuste a des performances **stables** sur une plage large de paramètres. "
    "Un pic isolé dans l'espace des paramètres est le signe d'un **sur-ajustement**."
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

param_cols_all = get_param_columns(df_m)
if not param_cols_all:
    st.info(
        "Aucune colonne de paramètre détectée (colonnes commençant par 'Inp').\n\n"
        "Assurez-vous que votre export XML MetaTrader contient bien les paramètres de l'EA."
    )
    st.stop()

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🔧 Options")
    strats_dispo  = sorted(df_m["Stratégie"].unique().tolist())
    sel_strat     = st.selectbox("Stratégie à analyser", strats_dispo)
    top_n         = st.slider("Top N passes", 10, 1000, 200, 10)
    metric_choice = st.selectbox(
        "Métrique cible",
        ["GHPR", "Forward Return %", "Profit Factor", "Recovery Factor", "Sharpe Ratio"],
    )
    n_bins = st.slider("Nombre de tranches (bins)", 5, 30, 10, 1)

# ── Filtrage ──────────────────────────────────────────────────────────────────
df_strat = (
    df_m[df_m["Stratégie"] == sel_strat]
    .sort_values("Back Profit", ascending=False)
    .head(top_n)
    .reset_index(drop=True)
)

param_cols = get_param_columns(df_strat)
metric_ok  = metric_choice in df_strat.columns

if df_strat.empty:
    st.warning("Aucune donnée pour cette stratégie.")
    st.stop()

# ── Header stratégie ───────────────────────────────────────────────────────────
stype  = df_strat["Type"].iloc[0]    if "Type"      in df_strat.columns else "?"
symbol = df_strat["Symbole"].iloc[0] if "Symbole"   in df_strat.columns else "?"
tf     = df_strat["Timeframe"].iloc[0] if "Timeframe" in df_strat.columns else ""

st.markdown(
    f"<div style='background:#1E2130;padding:14px 20px;border-radius:8px;"
    f"border-left:4px solid #0BB4FF;margin-bottom:20px;'>"
    f"<b style='font-size:18px;'>{sel_strat}</b><br>"
    f"<span style='color:#9AA3B0;'>{stype} | {symbol}"
    f"{' | ' + tf if tf else ''} | {len(df_strat):,} passes | "
    f"GHPR moy: <b style='color:#00E676;'>{df_strat['GHPR'].mean():.5f}</b></span></div>",
    unsafe_allow_html=True,
)

# ── Helper applymap/map ────────────────────────────────────────────────────────
_map_method = "map" if hasattr(pd.DataFrame().style, "map") and callable(getattr(pd.DataFrame().style, "map")) else "applymap"

# ── TABS ──────────────────────────────────────────────────────────────────────
tab_sens, tab_2d, tab_data = st.tabs([
    "📊 Sensibilité",
    "🗺️ Cartographie 2D",
    "📋 Données",
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — SENSIBILITÉ
# ═══════════════════════════════════════════════════════════════════════════════
with tab_sens:
    st.subheader("📊 Importance des Paramètres")
    st.markdown(
        "Classement par **corrélation de Spearman** entre la valeur du paramètre et la métrique cible.  \n"
        "Un paramètre avec une forte corrélation influence significativement la performance."
    )

    if metric_ok and param_cols:
        df_imp = param_importance(df_strat, param_cols, metric=metric_choice)
        if not df_imp.empty:
            col_table, col_bar = st.columns([1, 2])
            with col_table:
                def _color_sig_imp(val):
                    return "color: #00E676" if val == "✅" else "color: #FF5252"
                styled_imp = getattr(df_imp.style, _map_method)(_color_sig_imp, subset=["Significatif"])
                st.dataframe(styled_imp, use_container_width=True, height=350)
            with col_bar:
                st_plotly(fig_param_importance(df_imp), "sens_param_importance")
        else:
            st.info("Pas assez de données pour calculer l'importance.")
    else:
        st.info(f"Métrique '{metric_choice}' absente du fichier XML.")

    st.divider()

    st.subheader("📉 Sensibilité par Paramètre")
    st.markdown("""
- **Courbe plate** → paramètre robuste : la performance ne dépend pas fortement de sa valeur.
- **Pic isolé** → sur-ajustement : la stratégie n'est performante que sur une valeur très précise.
""")

    if not param_cols:
        st.info("Aucun paramètre disponible.")
    else:
        metric_to_use = metric_choice if metric_ok else "GHPR"
        if not metric_ok:
            st.warning(f"Métrique '{metric_choice}' absente — utilisation de GHPR.")

        pairs   = list(zip(param_cols[0::2], param_cols[1::2]))
        odd_one = [param_cols[-1]] if len(param_cols) % 2 != 0 else []

        for p1, p2 in pairs:
            c1, c2 = st.columns(2)
            for col, param in [(c1, p1), (c2, p2)]:
                df_agg = param_sensitivity(df_strat, param, metric=metric_to_use, bins=n_bins)
                with col:
                    if not df_agg.empty:
                        st_plotly(
                            fig_param_sensitivity(df_agg, param, metric_to_use),
                            f"sens_{param}",
                        )
                    else:
                        st.caption(f"Pas assez de valeurs distinctes pour {param}.")

        for param in odd_one:
            df_agg = param_sensitivity(df_strat, param, metric=metric_to_use, bins=n_bins)
            if not df_agg.empty:
                st_plotly(
                    fig_param_sensitivity(df_agg, param, metric_to_use),
                    f"sens_{param}_odd",
                )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — CARTOGRAPHIE 2D
# ═══════════════════════════════════════════════════════════════════════════════
with tab_2d:
    st.subheader("🧵 Coordonnées Parallèles")
    st.markdown("""
Chaque **ligne** = une passe d'optimisation. La couleur indique le GHPR (rouge = mauvais, vert = bon).

**Comment lire :** cliquez et faites glisser sur un axe pour sélectionner une plage.
Les lignes restantes = sous-espace optimal des paramètres.
""")
    if param_cols and "GHPR" in df_strat.columns:
        sel_params = param_cols
        if len(param_cols) > 8:
            sel_params = st.multiselect(
                "Paramètres à afficher (max 8 recommandé)",
                param_cols, default=param_cols[:6],
            )
        if sel_params:
            st_plotly(
                fig_parallel_coords(df_strat, sel_params, metric="GHPR"),
                "sens_parallel_coords",
            )

    st.divider()

    st.subheader("🎯 Interaction entre Deux Paramètres")
    st.markdown("Une zone large et homogène = robustesse. Un ilôt isolé = stratégie fragile.")

    if len(param_cols) >= 2:
        c1, c2, c3 = st.columns(3)
        with c1:
            px_param = st.selectbox("Paramètre axe X", param_cols, index=0, key="px")
        with c2:
            py_param = st.selectbox("Paramètre axe Y", param_cols,
                                    index=min(1, len(param_cols) - 1), key="py")
        with c3:
            _avail_metrics = [m for m in ["GHPR", "Forward Return %", "Profit Factor"]
                              if m in df_strat.columns]
            color_m = st.selectbox("Colorier par", _avail_metrics, key="cm") if _avail_metrics else None

        if color_m:
            df_2d = df_strat[[px_param, py_param, color_m]].dropna()
            if not df_2d.empty and px_param != py_param:
                fig_2d = px.density_heatmap(
                    df_2d, x=px_param, y=py_param,
                    z=color_m, histfunc="avg",
                    color_continuous_scale="RdYlGn",
                    nbinsx=15, nbinsy=15,
                    template="plotly_dark",
                    title=f"Performance moyenne ({color_m}) : {px_param} × {py_param}",
                )
                fig_2d.update_layout(paper_bgcolor="rgba(0,0,0,0)")
                st_plotly(fig_2d, "sens_2d_heatmap")
            else:
                st.info("Sélectionnez deux paramètres différents.")
    else:
        st.info("Au moins 2 paramètres requis pour la cartographie 2D.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — DONNÉES
# ═══════════════════════════════════════════════════════════════════════════════
with tab_data:
    st.subheader("📋 Données brutes des passes")
    cols_to_show = ["Pass", "Profit", "Back Result", "Trades", "GHPR", "AHPR",
                    "Forward Return %", "Back Return %"] + param_cols
    cols_present = [c for c in cols_to_show if c in df_strat.columns]
    st.dataframe(
        df_strat[cols_present].sort_values("GHPR", ascending=False),
        use_container_width=True,
        height=500,
    )
    st.caption(f"**{len(df_strat):,}** passes affichées (Top {top_n} par Back Profit).")
