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
from core.constants import GLOBAL_CSS
from core.ui_helpers import st_plotly
from core.mt5_runner import FOLDS

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
tab_heat, tab_family, tab_detail = st.tabs([
    "🗺️ Heatmap Excédent",
    "👨‍👩‍👧 Par Famille",
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
            fig.update_layout(height=400, margin=dict(l=10, r=10, t=50, b=10))
            st_plotly(fig, "hm_no_bh")
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
            fig.update_layout(height=400, margin=dict(l=10, r=10, t=60, b=10))
            st_plotly(fig, f"hm_bh_{fold_n}")

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
# TAB 2 — PAR FAMILLE
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
            fig_fam.update_layout(height=420, margin=dict(l=20, r=20, t=60, b=20))
            st_plotly(fig_fam, "bh_fam_bar")

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
            fig_act.update_layout(height=420, margin=dict(l=20, r=20, t=60, b=20))
            st_plotly(fig_act, "bh_actif_bar")

        # ── Taux de sur-performance ───────────────────────────────────────────
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
        fig_dj.update_layout(
            barmode="group", height=340,
            title="DJUBS — Rendement et MaxDD par fenêtre OOS",
            yaxis_title="%",
            margin=dict(l=20, r=20, t=60, b=20),
        )
        st_plotly(fig_dj, "dj_ref_bar")
    else:
        st.info("ℹ️ Données DJUBS non disponibles — vérifiez `TB-MT5/Bloomberg_Commodity_Index.csv`.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — TABLEAU DÉTAILLÉ
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
