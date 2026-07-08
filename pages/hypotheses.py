"""
Tests des Hypothèses de Recherche

Hypothèse A : le Trend Following sur-performe sur l'énergie (Brent, Gaz Naturel)
Hypothèse B : filtre saisonnier réduit le MaxDD sur l'agricole — À venir
Hypothèse C : Mean Reversion bat Trend Following sur Or et Platine (hors crises)
              Limite : exclusion des crises impossible sans courbes d'equity par passe.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from config_analyse import (
    ENERGY_ASSETS, METAL_ASSETS, FAMILY_COLORS, OOS_LABELS,
)
from core.analyse_metrics import (
    add_family_column,
    family_kpi_table,
    pairwise_family_comparison,
    per_fold_family_comparison,
)
from core.constants import GLOBAL_CSS, PLOTLY_DARK
from core.hyp_b_content import render as _render_hyp_b
from core.ui_helpers import chart_badge, st_plotly
from core.mt5_runner import FOLDS

_FOLD_OOS = {f["n"]: f"Pli {f['n']} OOS {f['forward_date'][:4]}–{f['to_date'][:4]}" for f in FOLDS}
_CRISIS_FOLDS = {1: "COVID-19 (2020)", 2: "Choc infla. (2022)", 3: "—"}

_METRIC_LABELS = {
    "OOS_Sharpe_Med":    "Sharpe OOS (médian)",
    "OOS_Return_Med_Pct":"Rendement OOS % (médian)",
    "OOS_Pct_Prof":      "% Passes Profitables OOS",
    "WFE_Pct":           "WFE %",
    "OOS_DD_Med":        "Max DD% OOS (médian)",
}

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Hypothèses", page_icon="🔬", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
st.title("🔬 Tests des Hypothèses de Recherche")

# ── Guard ─────────────────────────────────────────────────────────────────────
df_kpi: pd.DataFrame | None = st.session_state.get("df_kpi")
if df_kpi is None or df_kpi.empty or "robot" not in df_kpi.columns:
    st.warning("⚠️ Aucune donnée. Retournez à l'**Accueil** et chargez les résultats.")
    st.stop()

df_k = add_family_column(df_kpi)

tab_a, tab_b, tab_c = st.tabs([
    "📈 Hypothèse A — Trend sur l'Énergie",
    "🌿 Hypothèse B — Filtre Saisonnier",
    "🥇 Hypothèse C — Mean Rev sur Métaux",
])


# ══════════════════════════════════════════════════════════════════════════════
# HYPOTHÈSE A
# ══════════════════════════════════════════════════════════════════════════════
with tab_a:
    st.markdown("### Hypothèse A")
    st.markdown(
        "> *Le Trend Following sur-performe les autres familles algorithmiques "
        "sur les actifs Brent et Gaz Naturel.*"
    )

    met_a = st.selectbox(
        "Métrique",
        list(_METRIC_LABELS.keys()),
        format_func=_METRIC_LABELS.get,
        key="met_a",
    )

    df_e = df_k[df_k["actif_clean"].isin(ENERGY_ASSETS)].copy()

    if df_e.empty or met_a not in df_e.columns:
        st.warning("Données insuffisantes pour cette analyse.")
    else:
        # ── Tableau familles ──────────────────────────────────────────────────
        cols_tbl = [c for c in ["OOS_Return_Med_Pct","OOS_Pct_Prof","WFE_Pct","OOS_Sharpe_Med","OOS_DD_Med"] if c in df_e.columns]
        tbl = family_kpi_table(df_e, metrics=cols_tbl).rename(columns={
            "famille": "Famille", "OOS_Return_Med_Pct": "Rdt OOS % méd",
            "OOS_Pct_Prof": "% Prof OOS", "WFE_Pct": "WFE %",
            "OOS_Sharpe_Med": "Sharpe OOS", "OOS_DD_Med": "DD% OOS",
        })
        chart_badge(54)
        st.dataframe(tbl, use_container_width=True, hide_index=True)

        v = pairwise_family_comparison(df_e, "Trend Following", "Mean Reversion", ENERGY_ASSETS, met_a)

        if v["val_a"] is not None and v["val_b"] is not None:
            c1, c2, c3 = st.columns(3)
            c1.metric("Trend Following", f"{v['val_a']:.3f}")
            c2.metric("Mean Reversion",  f"{v['val_b']:.3f}")
            c3.metric("Delta TF − MR",   f"{v['delta']:+.3f}",
                      delta_color="normal" if v["confirmed"] else "inverse")

        # ── Bar comparatif par famille × actif ───────────────────────────────
        st.markdown("#### Médiane par famille et par actif")
        df_bar_a = (
            df_e.groupby(["famille", "actif_clean"])[met_a]
            .median().round(3).reset_index()
        )
        fig_a = px.bar(
            df_bar_a, x="actif_clean", y=met_a, color="famille",
            barmode="group", color_discrete_map=FAMILY_COLORS,
            labels={"actif_clean": "Actif", "famille": "Famille", met_a: _METRIC_LABELS.get(met_a, met_a)},
            text_auto=".2f",
        )
        fig_a.update_layout(**PLOTLY_DARK)
        fig_a.update_layout(height=380, margin=dict(l=20, r=20, t=20, b=20))
        st_plotly(fig_a, "hyp_a_bar", num=55)

        # ── Boxplot par pli ───────────────────────────────────────────────────
        st.markdown("#### Distribution par pli")
        df_e["Pli"] = df_e["pli"].map(_FOLD_OOS)
        fig_box_a = px.box(
            df_e, x="famille", y=met_a, color="famille",
            facet_col="Pli", facet_col_wrap=3,
            color_discrete_map=FAMILY_COLORS,
            labels={"famille": "Famille", met_a: _METRIC_LABELS.get(met_a, met_a)},
            points="outliers",
        )
        fig_box_a.update_layout(**PLOTLY_DARK)
        fig_box_a.update_layout(
            height=380, margin=dict(l=20, r=20, t=50, b=20),
            showlegend=False,
        )
        st_plotly(fig_box_a, "hyp_a_box", num=56)


# ══════════════════════════════════════════════════════════════════════════════
# HYPOTHÈSE C
# ══════════════════════════════════════════════════════════════════════════════
with tab_c:
    st.markdown("### Hypothèse C")
    st.markdown(
        "> *Sur Or et Platine, le Mean Reversion bat le Trend Following "
        "en performance ajustée au risque, hors périodes de crise systémique.*"
    )
    st.caption(
        "⚠️ **Limite** : l'exclusion des fenêtres de crise nécessite les courbes d'equity "
        "datées par passe (non disponibles dans les exports XML d'optimisation MT5). "
        "L'analyse porte sur les plis OOS complets. Le détail par pli permet d'observer "
        "l'impact des crises **indirectement** — Pli 1 couvre 2020–2021 (COVID), "
        "Pli 2 couvre 2022–2023 (choc énergie/inflation)."
    )

    met_c = st.selectbox(
        "Métrique",
        list(_METRIC_LABELS.keys()),
        format_func=_METRIC_LABELS.get,
        key="met_c",
    )

    df_m = df_k[df_k["actif_clean"].isin(METAL_ASSETS)].copy()

    if df_m.empty or met_c not in df_m.columns:
        st.warning("Données insuffisantes pour cette analyse.")
    else:
        # ── Tableau familles ──────────────────────────────────────────────────
        cols_tbl_c = [c for c in ["OOS_Return_Med_Pct","OOS_Pct_Prof","WFE_Pct","OOS_Sharpe_Med","OOS_DD_Med"] if c in df_m.columns]
        tbl_c = family_kpi_table(df_m, metrics=cols_tbl_c).rename(columns={
            "famille": "Famille", "OOS_Return_Med_Pct": "Rdt OOS % méd",
            "OOS_Pct_Prof": "% Prof OOS", "WFE_Pct": "WFE %",
            "OOS_Sharpe_Med": "Sharpe OOS", "OOS_DD_Med": "DD% OOS",
        })
        chart_badge(73)
        st.dataframe(tbl_c, use_container_width=True, hide_index=True)

        v_c = pairwise_family_comparison(df_m, "Mean Reversion", "Trend Following", METAL_ASSETS, met_c)

        if v_c["val_a"] is not None and v_c["val_b"] is not None:
            c1, c2, c3 = st.columns(3)
            c1.metric("Mean Reversion",  f"{v_c['val_a']:.3f}")
            c2.metric("Trend Following", f"{v_c['val_b']:.3f}")
            c3.metric("Delta MR − TF",   f"{v_c['delta']:+.3f}",
                      delta_color="normal" if v_c["confirmed"] else "inverse")

        # ── Détail par pli ────────────────────────────────────────────────────
        st.markdown("#### Comparaison par pli — effet des crises (indirect)")
        st.markdown(
            "| Pli | Fenêtre OOS | Événement |\n"
            "|-----|-------------|----------|\n"
            "| 1 | 2020–2021 | **COVID-19** |\n"
            "| 2 | 2022–2023 | **Choc énergie/inflation** |\n"
            "| 3 | 2024–2025 | — |\n"
        )

        df_pli = per_fold_family_comparison(
            df_m, "Mean Reversion", "Trend Following", METAL_ASSETS, met_c
        )
        if not df_pli.empty:
            df_pli["Pli OOS"] = df_pli["pli"].map(OOS_LABELS)
            df_pli["actif_label"] = df_pli["actif_clean"].map(
                {"GOLD": "Or", "PLATINUM": "Platine"}
            )

            fig_pli = px.bar(
                df_pli.rename(columns={
                    "Mean Reversion": "MR",
                    "Trend Following": "TF",
                }),
                x="Pli OOS",
                y=["MR", "TF"],
                barmode="group",
                facet_col="actif_label",
                color_discrete_map={"MR": FAMILY_COLORS["Mean Reversion"], "TF": FAMILY_COLORS["Trend Following"]},
                labels={"value": _METRIC_LABELS.get(met_c, met_c), "variable": "Famille"},
                title=f"{_METRIC_LABELS.get(met_c, met_c)} — Or et Platine par pli",
            )
            fig_pli.update_layout(**PLOTLY_DARK)
            fig_pli.update_layout(height=420, margin=dict(l=20, r=20, t=60, b=20))
            st_plotly(fig_pli, "hyp_c_pli", num=74)

            # Tableau recap avec delta
            chart_badge(75)
            st.dataframe(
                df_pli[["actif_label", "Pli OOS", "Mean Reversion", "Trend Following", "delta", "winner"]]
                .rename(columns={
                    "actif_label": "Actif",
                    "Mean Reversion": "MR",
                    "Trend Following": "TF",
                    "delta": "Δ MR−TF",
                    "winner": "Gagnant",
                }),
                use_container_width=True, hide_index=True,
            )


# ══════════════════════════════════════════════════════════════════════════════
# HYPOTHÈSE B — À VENIR
# ══════════════════════════════════════════════════════════════════════════════
with tab_b:
    st.markdown("### Hypothèse B — Filtre Saisonnier (Agricole)")
    _render_hyp_b(df_k)
