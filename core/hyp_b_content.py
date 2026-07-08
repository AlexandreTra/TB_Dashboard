"""
Contenu de l'onglet Hypothèse B — Filtre Saisonnier.
Appelé depuis 6_Hypotheses.py via render(df_kpi_raw).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import scipy.stats as sp_stats
import streamlit as st

from config_analyse import OOS_LABELS, OOS_WINDOWS
from core.constants import PLOTLY_DARK, THEME
from core.ui_helpers import chart_badge, st_plotly
from core.loader import load_combo_df
from core.market_data import _load_local_ohlc
from core.single_run import OUTPUT_DETAIL, detail_status, load_all_detail_trades

# ── Constantes ────────────────────────────────────────────────────────────────
_MR_ROBOTS: dict[str, str] = {
    "MR": "Mean Reversion",
    "ZS": "Z-Score",
}
_AGRI_ASSETS: dict[str, str] = {
    "COFFEE": "COFFEE.TB",
    "COCOA":  "COCOA.TB",
}
_AGRI_LABELS: dict[str, str] = {
    "COFFEE": "Café",
    "COCOA":  "Cacao",
}
_MONTH_NAMES = [
    "Jan", "Fév", "Mar", "Avr", "Mai", "Jun",
    "Jul", "Aoû", "Sep", "Oct", "Nov", "Déc",
]
_DEFAULT_ACTIVE_MONTHS: list[int] = [1, 2, 3, 10, 11, 12]
_ROBOT_COLOR: dict[str, str] = {
    "MR": "#FF8A65",
    "ZS": "#CE93D8",
}


# ── Fonctions cachées (niveau module pour que le cache survive entre reruns) ──

@st.cache_data(ttl=3_600, show_spinner=False)
def _top_passes(robot: str, actif_tb: str, tf: str, pli: int, n: int = 10) -> pd.DataFrame:
    df = load_combo_df(robot=robot, actif=actif_tb, tf=tf, pli=pli)
    if df.empty or "OOS_Score" not in df.columns:
        return pd.DataFrame()
    top = df.nlargest(n, "OOS_Score").reset_index(drop=True)
    top.insert(0, "Rang", range(1, len(top) + 1))
    return top


@st.cache_data(ttl=86_400, show_spinner=False)
def _monthly_returns(actif_clean: str) -> pd.DataFrame:
    daily = _load_local_ohlc(actif_clean, timeframe="Daily")
    if daily.empty:
        return pd.DataFrame()
    daily = daily.loc["2015-01-01":"2025-12-31"].copy()
    daily["log_ret"] = np.log(daily["Close"] / daily["Close"].shift(1))
    daily = daily.dropna(subset=["log_ret"])
    if daily.empty:
        return pd.DataFrame()
    monthly = daily["log_ret"].resample("MS").sum().reset_index()
    monthly.columns = ["date", "log_ret"]
    monthly["ret_pct"]    = monthly["log_ret"] * 100
    monthly["year"]       = monthly["date"].dt.year
    monthly["month"]      = monthly["date"].dt.month
    monthly["month_name"] = monthly["month"].apply(lambda m: _MONTH_NAMES[m - 1])
    monthly["actif"]      = actif_clean
    return monthly


@st.cache_data(ttl=86_400, show_spinner=False)
def _monthly_stats(actif_clean: str) -> pd.DataFrame:
    df = _monthly_returns(actif_clean)
    if df.empty:
        return pd.DataFrame()
    rows = []
    for m in range(1, 13):
        sub = df[df["month"] == m]["ret_pct"].dropna()
        if sub.empty:
            continue
        rows.append({
            "Mois":         _MONTH_NAMES[m - 1],
            "N obs":        int(len(sub)),
            "Rdt moy %":    round(float(sub.mean()), 2),
            "Médiane %":    round(float(sub.median()), 2),
            "Écart-type %": round(float(sub.std()), 2),
            "% positif":    round(float((sub > 0).mean() * 100), 1),
        })
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════
# Point d'entrée principal
# ══════════════════════════════════════════════════════════════════════════════

def render(df_kpi_raw: pd.DataFrame) -> None:
    """Affiche le contenu complet de l'onglet Hypothèse B."""

    st.markdown(
        """
        > *Un filtre saisonnier réduit le Max Drawdown des stratégies Mean Reversion
        > sur Café et Cacao en excluant les mois calendaires structurellement défavorables.*

        | | |
        |---|---|
        | **Robots analysés** | MR *(EA_MeanReversion_Roll)* et ZS *(EA_ZScore_Roll)* |
        | **Actifs** | Café (COFFEE.TB) et Cacao (COCOA.TB) |
        | **Source performance** | Top N passes OOS par combinaison robot × actif × TF × pli |
        | **Source saisonnalité** | Rendements journaliers D1 TB-Python 2015–2025 |

        > ⚠️ **Limite** : les journaux de trades individuels ne sont pas disponibles dans les
        > exports XML d'optimisation MT5. L'analyse saisonnière porte sur l'actif sous-jacent
        > comme proxy. L'EA `EA_MeanReversion_Saison_Roll` fournira la comparaison empirique directe.
        """
    )

    # Filtrage sur robots MR/ZS et actifs agricoles
    df_k = df_kpi_raw[
        df_kpi_raw["robot"].isin(_MR_ROBOTS) &
        df_kpi_raw["actif_clean"].isin(_AGRI_ASSETS)
    ].copy()
    df_k["robot_label"] = df_k["robot"].map(_MR_ROBOTS)

    # ── Paramètres locaux (dans la page, pas la sidebar) ──────────────────────
    _pc1, _pc2, _pc3 = st.columns([2, 2, 4])
    with _pc1:
        sel_tf = st.selectbox(
            "Timeframe",
            ["H1", "H4", "D1"],
            index=0,
            key="hyp_b_tf",
            help="D1 ne produit aucun trade pour MR/ZS sur ces actifs.",
        )
    with _pc2:
        top_n = st.slider("Top N passes OOS", 5, 20, 10, key="hyp_b_topn")

    st.divider()

    # ── Sous-onglets ──────────────────────────────────────────────────────────
    tab_perf, tab_seas, tab_heat, tab_synth, tab_trades = st.tabs([
        "📊 Performance MR / ZS",
        "📅 Saisonnalité des Sous-Jacents",
        "🗺️ Stabilité Temporelle",
        "🔬 Synthèse & Test Statistique",
        "🎯 Journaux de Trades",
    ])

    # ══════════════════════════════════════════════════════════════════════════
    # SOUS-ONGLET 1 — PERFORMANCE
    # ══════════════════════════════════════════════════════════════════════════
    with tab_perf:
        st.markdown(
            f"### Performance OOS — MR & ZS sur Café et Cacao ({sel_tf})\n"
            "Médianes calculées sur l'ensemble des passes (source : `df_kpi`). "
            f"Section **Top {top_n} passes** : détail passe par passe via `load_combo_df`."
        )

        if df_k.empty:
            st.warning("Aucune donnée MR/ZS disponible pour les actifs agricoles.")
        else:
            tf_data = df_k[df_k["timeframe"] == sel_tf].copy()
            if tf_data.empty:
                st.info(f"Aucune donnée pour le timeframe {sel_tf}.")
            else:
                tf_data["Pli OOS"] = tf_data["pli"].map(OOS_LABELS)
                tf_data["Actif"]   = tf_data["actif_clean"].map(_AGRI_LABELS)

                _m_avail = {
                    k: v for k, v in {
                        "OOS_Score_Med":      "Score OOS",
                        "OOS_Return_Med_Pct": "Rdt OOS %",
                        "OOS_DD_Med":         "MaxDD % OOS",
                        "OOS_Sharpe_Med":     "Sharpe OOS",
                        "OOS_PF_Med":         "Profit Factor OOS",
                        "WFE_Pct":            "WFE %",
                    }.items()
                    if k in tf_data.columns
                }

                col_left, col_right = st.columns([3, 1])
                with col_right:
                    met_sel = st.selectbox(
                        "Métrique",
                        list(_m_avail.keys()),
                        format_func=_m_avail.get,
                        key="hyp_b_met",
                    )
                with col_left:
                    fig_ov = px.bar(
                        tf_data.dropna(subset=[met_sel]),
                        x="Pli OOS", y=met_sel, color="robot_label",
                        facet_col="Actif", barmode="group",
                        color_discrete_map={
                            "Mean Reversion": _ROBOT_COLOR["MR"],
                            "Z-Score":        _ROBOT_COLOR["ZS"],
                        },
                        text_auto=".2f",
                        labels={met_sel: _m_avail.get(met_sel, met_sel), "robot_label": "Robot"},
                        title=f"{_m_avail.get(met_sel, met_sel)} par pli — Café et Cacao",
                    )
                    fig_ov.update_layout(height=380, **PLOTLY_DARK)
                    st_plotly(fig_ov, "hyp_b_ov_bar", num=57)

                chart_badge(58)
                disp_cols = [c for c in [
                    "robot_label", "Actif", "Pli OOS",
                    "OOS_Score_Med", "OOS_Return_Med_Pct", "OOS_DD_Med",
                    "OOS_Sharpe_Med", "WFE_Pct", "Nb_Passes_OOS",
                ] if c in tf_data.columns]
                st.dataframe(
                    tf_data[disp_cols].rename(columns={
                        "robot_label":        "Robot",
                        "OOS_Score_Med":      "Score OOS",
                        "OOS_Return_Med_Pct": "Rdt OOS %",
                        "OOS_DD_Med":         "MaxDD %",
                        "OOS_Sharpe_Med":     "Sharpe",
                        "WFE_Pct":            "WFE %",
                        "Nb_Passes_OOS":      "N passes",
                    }),
                    use_container_width=True, hide_index=True,
                )

            st.markdown(f"#### Top {top_n} passes OOS par combinaison ({sel_tf})")
            _pass_cols = [
                "Rang", "Pass", "OOS_Score", "OOS_Profit", "OOS_Trades",
                "OOS_Sharpe", "OOS_DD_Pct", "OOS_Return_Pct", "WFE_pass",
            ]
            _pass_labels = {
                "Rang": "#", "Pass": "Passe", "OOS_Score": "Score OOS",
                "OOS_Profit": "Profit ($)", "OOS_Trades": "Trades",
                "OOS_Sharpe": "Sharpe", "OOS_DD_Pct": "MaxDD %",
                "OOS_Return_Pct": "Rdt %", "WFE_pass": "WFE",
            }
            for robot in _MR_ROBOTS:
                for actif_clean, actif_tb in _AGRI_ASSETS.items():
                    with st.expander(
                        f"**{_MR_ROBOTS[robot]}** — {_AGRI_LABELS[actif_clean]}",
                        expanded=False,
                    ):
                        fold_tabs = st.tabs([OOS_LABELS.get(n, f"Pli {n}") for n in [1, 2, 3]])
                        for i, pli in enumerate([1, 2, 3]):
                            with fold_tabs[i]:
                                df_top = _top_passes(robot, actif_tb, sel_tf, pli, top_n)
                                if df_top.empty:
                                    st.info("Données non disponibles.")
                                    continue
                                show_cols = [c for c in _pass_cols if c in df_top.columns]
                                st.dataframe(
                                    df_top[show_cols].rename(columns=_pass_labels),
                                    use_container_width=True, hide_index=True,
                                    column_config={
                                        "Score OOS":  st.column_config.NumberColumn(format="%.4f"),
                                        "Profit ($)": st.column_config.NumberColumn(format="$%.0f"),
                                        "Sharpe":     st.column_config.NumberColumn(format="%.3f"),
                                        "MaxDD %":    st.column_config.NumberColumn(format="%.2f %%"),
                                        "Rdt %":      st.column_config.NumberColumn(format="%.2f %%"),
                                        "WFE":        st.column_config.NumberColumn(format="%.3f"),
                                    },
                                )
                                if "OOS_Score" in df_top.columns and "OOS_DD_Pct" in df_top.columns:
                                    fig_sc = px.scatter(
                                        df_top,
                                        x="OOS_DD_Pct", y="OOS_Score",
                                        size=[8] * len(df_top),
                                        hover_data=["Pass", "OOS_Profit", "OOS_Trades"],
                                        labels={"OOS_DD_Pct": "MaxDD % OOS", "OOS_Score": "Score OOS"},
                                        title=f"Score vs Drawdown — Top {top_n} passes",
                                        color_discrete_sequence=[_ROBOT_COLOR[robot]],
                                    )
                                    fig_sc.update_layout(height=300, **PLOTLY_DARK)
                                    st_plotly(fig_sc, f"sc_{robot}_{actif_clean}_{pli}", num=59)

    # ══════════════════════════════════════════════════════════════════════════
    # SOUS-ONGLET 2 — SAISONNALITÉ
    # ══════════════════════════════════════════════════════════════════════════
    with tab_seas:
        st.markdown(
            "### Saisonnalité mensuelle de Café et Cacao (2015–2025)\n"
            "Source : rendements log journaliers D1 TB-Python, agrégés par mois calendaire."
        )

        monthly_all: dict[str, pd.DataFrame] = {}
        stats_all:   dict[str, pd.DataFrame] = {}
        for ac in _AGRI_ASSETS:
            m = _monthly_returns(ac)
            s = _monthly_stats(ac)
            if not m.empty:
                monthly_all[ac] = m
            if not s.empty:
                stats_all[ac] = s

        if not monthly_all:
            st.error("Données de marché non disponibles — vérifiez les fichiers TB-Python D1.")
        else:
            df_seas_combined = pd.concat(monthly_all.values(), ignore_index=True)
            df_seas_agg = (
                df_seas_combined.groupby(["actif", "month", "month_name"])["ret_pct"]
                .mean().reset_index()
            )
            df_seas_agg["Actif"]      = df_seas_agg["actif"].map(_AGRI_LABELS)
            df_seas_agg["month_name"] = pd.Categorical(
                df_seas_agg["month_name"], categories=_MONTH_NAMES, ordered=True
            )
            df_seas_agg = df_seas_agg.sort_values("month")

            fig_seas = px.bar(
                df_seas_agg,
                x="month_name", y="ret_pct", color="Actif",
                barmode="group", text_auto=".2f",
                labels={"month_name": "Mois", "ret_pct": "Rdt log moy %"},
                color_discrete_map={"Café": "#FF8A65", "Cacao": "#CE93D8"},
                title="Rendement log mensuel moyen — Café et Cacao (2015–2025)",
            )
            fig_seas.add_hline(y=0, line_dash="dash",
                               line_color="rgba(255,255,255,0.3)", line_width=1)
            fig_seas.update_layout(height=400, **PLOTLY_DARK)
            st_plotly(fig_seas, "seas_bar_compare", num=60)

            st.markdown("#### Statistiques mensuelles détaillées")
            chart_badge(61)
            col_cof, col_coc = st.columns(2)
            for col_w, ac in zip([col_cof, col_coc], _AGRI_ASSETS):
                with col_w:
                    st.markdown(f"**{_AGRI_LABELS[ac]}**")
                    if ac in stats_all:
                        st.dataframe(
                            stats_all[ac],
                            use_container_width=True, hide_index=True,
                            column_config={
                                "Rdt moy %":    st.column_config.NumberColumn(format="%.2f %%"),
                                "Médiane %":    st.column_config.NumberColumn(format="%.2f %%"),
                                "Écart-type %": st.column_config.NumberColumn(format="%.2f %%"),
                                "% positif":    st.column_config.NumberColumn(format="%.1f %%"),
                            },
                        )
                    else:
                        st.info("Données non disponibles.")

            with st.expander("Voir les box plots détaillés", expanded=False):
                for ac in _AGRI_ASSETS:
                    if ac not in monthly_all:
                        continue
                    df_m = monthly_all[ac].copy()
                    df_m["month_name"] = pd.Categorical(
                        df_m["month_name"], categories=_MONTH_NAMES, ordered=True
                    )
                    fig_box = px.box(
                        df_m.sort_values("month"),
                        x="month_name", y="ret_pct", points="all",
                        labels={"month_name": "Mois", "ret_pct": "Rdt log mensuel %"},
                        title=f"Distribution mensuelle — {_AGRI_LABELS[ac]}",
                        color_discrete_sequence=[
                            _ROBOT_COLOR["MR"] if ac == "COFFEE" else _ROBOT_COLOR["ZS"]
                        ],
                    )
                    fig_box.add_hline(y=0, line_dash="dash",
                                      line_color="rgba(255,255,255,0.3)", line_width=1)
                    fig_box.update_layout(height=380, **PLOTLY_DARK)
                    st_plotly(fig_box, f"box_{ac}", num=62)

    # ══════════════════════════════════════════════════════════════════════════
    # SOUS-ONGLET 3 — HEATMAP STABILITÉ
    # ══════════════════════════════════════════════════════════════════════════
    with tab_heat:
        st.markdown(
            "### Stabilité Temporelle de la Saisonnalité\n"
            "Rendement log mensuel moyen par période OOS. "
            "Si le schéma est stable, les mois bons/mauvais sont cohérents sur les 3 plis."
        )
        _pli_labels = {
            1: "Pli 1 (2020–2021)",
            2: "Pli 2 (2022–2023)",
            3: "Pli 3 (2024–2025)",
        }
        # Utilise monthly_all chargé dans tab_seas — si ce tab est rendu en premier,
        # on le recharge localement.
        _heat_monthly: dict[str, pd.DataFrame] = {}
        for ac in _AGRI_ASSETS:
            _r = _monthly_returns(ac)
            if not _r.empty:
                _heat_monthly[ac] = _r

        for ac in _AGRI_ASSETS:
            if ac not in _heat_monthly:
                continue
            df_full = _heat_monthly[ac].copy()
            fold_rows = []
            for pli, (start, end) in OOS_WINDOWS.items():
                mask = (df_full["date"] >= start) & (df_full["date"] <= end)
                sub  = df_full[mask].copy()
                sub["pli"] = pli
                fold_rows.append(sub)
            if not fold_rows:
                continue
            df_pli = pd.concat(fold_rows, ignore_index=True)
            pivot = (
                df_pli.groupby(["pli", "month"])["ret_pct"]
                .mean().unstack(level="month").reindex(columns=range(1, 13))
            )
            pivot.columns = _MONTH_NAMES
            pivot.index   = [_pli_labels.get(p, f"Pli {p}") for p in pivot.index]

            st.markdown(f"#### {_AGRI_LABELS[ac]}")
            fig_hm = go.Figure(data=go.Heatmap(
                z=pivot.values,
                x=_MONTH_NAMES, y=list(pivot.index),
                colorscale="RdYlGn", zmid=0,
                text=[[f"{v:.2f}%" if not np.isnan(v) else "" for v in row]
                      for row in pivot.values],
                texttemplate="%{text}",
                colorbar=dict(title="Rdt %", tickformat=".1f"),
                hovertemplate="Mois : %{x}<br>Pli : %{y}<br>Rdt : %{z:.2f}%<extra></extra>",
            ))
            fig_hm.update_layout(
                height=280,
                title=f"Rdt log moyen mensuel (%) — {_AGRI_LABELS[ac]} par pli OOS",
                **PLOTLY_DARK,
            )
            st_plotly(fig_hm, f"hm_{ac}", num=63)

            if pivot.shape[0] >= 2:
                corr_pairs = []
                pli_keys = list(pivot.index)
                for i in range(len(pli_keys)):
                    for j in range(i + 1, len(pli_keys)):
                        row_i = pivot.iloc[i].dropna()
                        row_j = pivot.iloc[j].dropna()
                        common = row_i.index.intersection(row_j.index)
                        if len(common) >= 6:
                            rho, pval = sp_stats.spearmanr(row_i[common], row_j[common])
                            corr_pairs.append({
                                "Paires":   f"{pli_keys[i]} ↔ {pli_keys[j]}",
                                "Rho rang": round(float(rho), 3),
                                "p-val":    round(float(pval), 4),
                                "Stable":   "✅" if float(pval) < 0.05 else "⚪",
                            })
                if corr_pairs:
                    st.caption("Corrélation de Spearman des rangs mensuels entre plis")
                    st.dataframe(pd.DataFrame(corr_pairs),
                                 use_container_width=False, hide_index=True)
            st.markdown("---")

    # ══════════════════════════════════════════════════════════════════════════
    # SOUS-ONGLET 4 — SYNTHÈSE & TEST STATISTIQUE
    # ══════════════════════════════════════════════════════════════════════════
    with tab_synth:
        st.markdown(
            "### Simulation du Filtre Saisonnier\n"
            "Sélectionner les mois **actifs** (inclus dans la stratégie). "
            "Les tests comparent la distribution des rendements entre mois actifs et mois exclus.  \n\n"
            "> **Tests utilisés ici** : Mann-Whitney U (non-paramétrique) + Welch t-test.  \n"
            "> **Ce qu'ils testent** : *les mois sélectionnés comme actifs ont-ils un rendement "
            "significativement différent des mois exclus ?* — comparaison de **deux groupes définis "
            "par le filtre saisonnier**, pas de saisonnalité calendaire globale.  \n"
            "> ≠ de l'**ANOVA** (page Profil des Actifs) qui teste si les 12 mois calendaires "
            "ont des rendements différents entre eux, sans notion de filtre."
        )
        _synth_monthly: dict[str, pd.DataFrame] = {}
        for ac in _AGRI_ASSETS:
            _r = _monthly_returns(ac)
            if not _r.empty:
                _synth_monthly[ac] = _r

        active_sel = st.multiselect(
            "Mois actifs (filtre saisonnier)",
            options=list(range(1, 13)),
            default=_DEFAULT_ACTIVE_MONTHS,
            format_func=lambda m: _MONTH_NAMES[m - 1],
            key="hyp_b_months",
        )
        excluded = [m for m in range(1, 13) if m not in active_sel]

        if not active_sel or not excluded:
            st.info("Sélectionnez au moins un mois actif et laissez au moins un mois exclu.")
        else:
            for ac in _AGRI_ASSETS:
                if ac not in _synth_monthly:
                    continue
                df_m = _synth_monthly[ac].copy()
                grp_act = df_m[df_m["month"].isin(active_sel)]["ret_pct"].dropna()
                grp_exc = df_m[df_m["month"].isin(excluded)]["ret_pct"].dropna()

                st.markdown(f"#### {_AGRI_LABELS[ac]}")
                if len(grp_act) < 3 or len(grp_exc) < 3:
                    st.warning("Échantillons trop petits.")
                    continue

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Mois actifs — Rdt moy", f"{grp_act.mean():.2f} %",
                          delta=f"N={len(grp_act)}")
                c2.metric("Mois exclus — Rdt moy", f"{grp_exc.mean():.2f} %",
                          delta=f"N={len(grp_exc)}")
                c3.metric("Mois actifs — % positif", f"{(grp_act > 0).mean() * 100:.1f} %")
                c4.metric("Mois exclus — % positif", f"{(grp_exc > 0).mean() * 100:.1f} %")

                stat, pval   = sp_stats.mannwhitneyu(grp_act.values, grp_exc.values,
                                                      alternative="two-sided")
                t_stat, t_pval = sp_stats.ttest_ind(grp_act.values, grp_exc.values,
                                                     equal_var=False)

                df_dist = pd.concat([
                    pd.DataFrame({"ret_pct": grp_act.values, "Groupe": "Actifs"}),
                    pd.DataFrame({"ret_pct": grp_exc.values, "Groupe": "Exclus"}),
                ])
                fig_dist = px.histogram(
                    df_dist, x="ret_pct", color="Groupe",
                    barmode="overlay", nbins=30, opacity=0.7,
                    labels={"ret_pct": "Rendement mensuel log %"},
                    color_discrete_map={"Actifs": THEME["success"], "Exclus": THEME["danger"]},
                    title=f"Distribution des rendements — {_AGRI_LABELS[ac]}",
                )
                fig_dist.add_vline(x=float(grp_act.mean()), line_dash="dash",
                                   line_color=THEME["success"], line_width=1.5,
                                   annotation_text=f"Moy. actifs ({grp_act.mean():.2f}%)",
                                   annotation_position="top right")
                fig_dist.add_vline(x=float(grp_exc.mean()), line_dash="dash",
                                   line_color=THEME["danger"], line_width=1.5,
                                   annotation_text=f"Moy. exclus ({grp_exc.mean():.2f}%)",
                                   annotation_position="top left")
                fig_dist.update_layout(height=360, **PLOTLY_DARK)
                st_plotly(fig_dist, f"dist_{ac}", num=65)

                mois_act_str = ", ".join(_MONTH_NAMES[m - 1] for m in sorted(active_sel))
                mois_exc_str = ", ".join(_MONTH_NAMES[m - 1] for m in sorted(excluded))
                sig = pval < 0.05
                v_fn = st.success if sig else st.warning
                v_fn(
                    f"**{'✅' if sig else '⚪'} {_AGRI_LABELS[ac]}**\n\n"
                    f"- **Mois actifs** ({mois_act_str}) : {grp_act.mean():.2f}% "
                    f"(N={len(grp_act)}, {(grp_act > 0).mean() * 100:.1f}% positifs)\n"
                    f"- **Mois exclus** ({mois_exc_str}) : {grp_exc.mean():.2f}% "
                    f"(N={len(grp_exc)}, {(grp_exc > 0).mean() * 100:.1f}% positifs)\n"
                    f"- **Écart** : {grp_act.mean() - grp_exc.mean():+.2f}% en faveur des mois actifs\n"
                    f"- **Mann-Whitney U** : stat={stat:.1f}, p={pval:.4f} → "
                    f"{'significatif' if sig else 'non significatif'}\n"
                    f"- **Welch t-test** : t={t_stat:.3f}, p={t_pval:.4f}"
                )
                st.markdown("---")

            st.markdown(
                "#### Interprétation pour l'Hypothèse B\n"
                "Un filtre éliminant les mois exclus réduira mécaniquement le drawdown si ces "
                "mois génèrent des mouvements adverses systématiques pour les stratégies MR.\n\n"
                "**Vérification directe** : `EA_MeanReversion_Saison_Roll` optimise le même signal "
                "avec un bitmask `InpActiveMonths`. La comparaison de son MaxDD OOS vs "
                "`EA_MeanReversion_Roll` constituera le test définitif de l'Hypothèse B."
            )

    # ══════════════════════════════════════════════════════════════════════════
    # SOUS-ONGLET 5 — JOURNAUX DE TRADES
    # ══════════════════════════════════════════════════════════════════════════
    with tab_trades:
        st.markdown("### Journaux de Trades — Meilleure / Médiane / Pire passe")
        st.markdown(
            "Analyse des backtests MT5 individuels (`Optimization=0`) — 3 passes "
            "représentatives (meilleure, médiane, pire) par combinaison robot × actif × pli."
        )

        _tf_opts  = ["Toutes (H1 + H4 + D1)", "H1", "H4", "D1"]
        _sel_tf_t = st.selectbox(
            "Timeframe (journaux)",
            _tf_opts,
            index=_tf_opts.index(sel_tf) if sel_tf in _tf_opts else 1,
            key="t_tf",
            help="Choisir un TF ou agréger tous les timeframes ensemble.",
        )
        _tfs_t = ["H1", "H4", "D1"] if _sel_tf_t == "Toutes (H1 + H4 + D1)" else [_sel_tf_t]

        _detail_combos = [
            {"robot": robot, "actif_tb": actif_tb, "tf": tf, "pli": pli}
            for robot    in _MR_ROBOTS
            for actif_tb in _AGRI_ASSETS.values()
            for tf       in _tfs_t
            for pli      in [1, 2, 3]
        ]
        _status_map   = detail_status(_detail_combos, OUTPUT_DETAIL)
        _n_done       = sum(1 for v in _status_map.values() if v == "done")
        _n_total_runs = len(_status_map)

        c1, c2, c3 = st.columns(3)
        c1.metric("Runs totaux",  _n_total_runs)
        c2.metric("Générés",      _n_done)
        c3.metric("Manquants",    _n_total_runs - _n_done)

        with st.expander("📋 Couverture des journaux", expanded=(_n_done < _n_total_runs)):
            status_rows = []
            for actif_tb in _AGRI_ASSETS.values():
                actif_clean = actif_tb.replace(".TB", "")
                for robot in _MR_ROBOTS:
                    for tf in _tfs_t:
                        for pli in [1, 2, 3]:
                            row = {
                                "Robot": _MR_ROBOTS[robot],
                                "Actif": _AGRI_LABELS[actif_clean],
                                "TF":    tf,
                                "Pli":   OOS_LABELS.get(pli, f"Pli {pli}"),
                            }
                            for lbl in ("best", "median", "worst"):
                                key    = f"{robot}/{actif_clean}/{tf}/fold{pli}/{lbl}"
                                status = _status_map.get(key, "missing")
                                row[lbl.capitalize()] = "✅" if status == "done" else "🔲"
                            status_rows.append(row)
            st.dataframe(pd.DataFrame(status_rows),
                         use_container_width=True, hide_index=True)

        if _n_done == 0:
            st.info(
                "Aucun journal disponible. Rendez-vous dans **⚙️ Lancer MT5 → "
                "Backtests Individuels** pour générer les rapports XML. "
                "Les onglets **Saisonnalité** et **Synthèse** restent accessibles "
                "avec les données de prix en proxy."
            )
            return

        st.divider()
        st.markdown("## Analyse des Journaux de Trades")
        with st.spinner("Chargement des journaux…"):
            df_trades = load_all_detail_trades(_detail_combos, OUTPUT_DETAIL)

        if df_trades.empty or "Time" not in df_trades.columns or "Profit" not in df_trades.columns:
            st.warning("Aucun trade parsé — vérifiez le format des rapports XML.")
            return

        df_trades["month"]      = df_trades["Time"].dt.month
        df_trades["month_name"] = df_trades["month"].apply(lambda m: _MONTH_NAMES[m - 1])
        df_trades["month_name"] = pd.Categorical(
            df_trades["month_name"], categories=_MONTH_NAMES, ordered=True
        )
        df_trades["pli_label"] = df_trades["pli"].map(OOS_LABELS)
        df_trades["win"]       = (df_trades["Profit"] > 0).astype(int)
        # Rendement % par trade : normalise le compound (Profit / capital_avant × 100)
        if "Balance" in df_trades.columns:
            _cap_before = df_trades["Balance"] - df_trades["Profit"]
            df_trades["ret_pct"] = np.where(
                _cap_before > 0,
                df_trades["Profit"] / _cap_before * 100,
                np.nan,
            )
        else:
            df_trades["ret_pct"] = df_trades["Profit"] / 100_000 * 100
        df_trades["Actif"]     = df_trades["actif_clean"].map(_AGRI_LABELS)
        df_trades["Robot"]     = df_trades["robot"].map(_MR_ROBOTS)
        df_trades["Passe"]     = df_trades["pass_label"].map(
            {"best": "Meilleure", "median": "Médiane", "worst": "Pire"}
        )
        _pass_colors = {
            "Meilleure": THEME["success"],
            "Médiane":   "#FFD54F",
            "Pire":      THEME["danger"],
        }

        ca, cb = st.columns(2)
        with ca:
            _sel_robot_t = st.selectbox(
                "Famille",
                ["Toutes (MR & ZS)"] + list(_MR_ROBOTS.values()),
                key="t_robot",
            )
        with cb:
            _sel_actif_t = st.selectbox(
                "Actif",
                ["Tous (Café + Cacao)", "Café", "Cacao"],
                key="t_actif",
            )

        df_t = df_trades.copy()
        if _sel_robot_t not in ("Toutes (MR & ZS)",):
            df_t = df_t[df_t["Robot"] == _sel_robot_t]
        if _sel_actif_t not in ("Tous (Café + Cacao)",):
            df_t = df_t[df_t["Actif"] == _sel_actif_t]

        if df_t.empty:
            st.info("Aucun trade pour cette sélection.")
            return

        # 1 — Histogramme nombre de trades par mois
        st.markdown("#### 1 — Distribution du Nombre de Trades par Mois")
        monthly_count = (
            df_t.groupby(["month_name", "Passe"]).size().reset_index(name="Nb trades")
        )
        fig_cnt = px.bar(
            monthly_count, x="month_name", y="Nb trades", color="Passe",
            barmode="group", color_discrete_map=_pass_colors,
            labels={"month_name": "Mois"},
            title="Nombre de trades par mois calendaire",
        )
        fig_cnt.update_layout(height=380, **PLOTLY_DARK)
        st_plotly(fig_cnt, "t_cnt", num=67)

        # 2 — Tableau récap
        st.markdown("#### 2 — Tableau Récapitulatif par Mois")
        monthly_stats_t = (
            df_t.groupby("month")
            .agg(Nb_trades=("Profit", "count"), PnL_moy=("Profit", "mean"),
                 PnL_total=("Profit", "sum"), Taux_win=("win", "mean"))
            .reset_index()
        )
        monthly_stats_t["Mois"]          = monthly_stats_t["month"].apply(
            lambda m: _MONTH_NAMES[m - 1]
        )
        monthly_stats_t["PnL moy ($)"]   = monthly_stats_t["PnL_moy"].round(0)
        monthly_stats_t["P&L total ($)"] = monthly_stats_t["PnL_total"].round(0)
        monthly_stats_t["Taux gain %"]   = (monthly_stats_t["Taux_win"] * 100).round(1)
        monthly_stats_t["N trades"]      = monthly_stats_t["Nb_trades"]
        st.dataframe(
            monthly_stats_t[["Mois", "N trades", "PnL moy ($)", "P&L total ($)", "Taux gain %"]],
            use_container_width=True, hide_index=True,
            column_config={
                "PnL moy ($)":   st.column_config.NumberColumn(format="$%.0f"),
                "P&L total ($)": st.column_config.NumberColumn(format="$%.0f"),
                "Taux gain %":   st.column_config.NumberColumn(format="%.1f %%"),
            },
        )

        # 2b — Heatmap PnL moyen par actif × mois
        st.markdown("#### 2b — Heatmap P&L moyen par trade — Café / Cacao × Mois")
        st.caption(f"Timeframe : {_sel_tf_t} — famille : {_sel_robot_t} — couleur = P&L moyen par trade ($)")

        _df_t2 = df_trades.copy()
        if _sel_robot_t not in ("Toutes (MR & ZS)",):
            _df_t2 = _df_t2[_df_t2["Robot"] == _sel_robot_t]

        _hm_rows = []
        _use_pct = "ret_pct" in _df_t2.columns
        _val_col = "ret_pct" if _use_pct else "Profit"
        for _ac, _lbl in [("COFFEE", "Café"), ("COCOA", "Cacao")]:
            _df_ac = _df_t2[_df_t2["actif_clean"] == _ac]
            for _m in range(1, 13):
                _sub = _df_ac[_df_ac["month"] == _m][_val_col].dropna()
                _val = float(_sub.mean()) if len(_sub) > 0 else float("nan")
                _lbl_cell = (
                    f"{_val:.3f}%\n(N={len(_sub)})" if (len(_sub) > 0 and _use_pct)
                    else f"${_val:.0f}\n(N={len(_sub)})" if len(_sub) > 0
                    else ""
                )
                _hm_rows.append({
                    "Actif": _lbl,
                    "month": _m,
                    "val":   _val,
                    "label": _lbl_cell,
                })
        _df_hm = pd.DataFrame(_hm_rows)

        if not _df_hm["val"].notna().any():
            st.info("Aucun trade disponible pour cette sélection.")
        else:
            _pivot_hm = (
                _df_hm.pivot(index="Actif", columns="month", values="val")
                .reindex(columns=range(1, 13))
            )
            _pivot_lbl = (
                _df_hm.pivot(index="Actif", columns="month", values="label")
                .reindex(columns=range(1, 13))
                .fillna("")
            )
            _pivot_hm.columns  = _MONTH_NAMES
            _pivot_lbl.columns = _MONTH_NAMES

            _zmid = 0.0
            _zmax = _pivot_hm.abs().max().max()
            _cb_title = "Rdt % moy/trade" if _use_pct else "P&L moy ($)"
            _hover_fmt = "%.3f%%" if _use_pct else "$%.0f"
            fig_hm2b = go.Figure(data=go.Heatmap(
                z=_pivot_hm.values,
                x=_MONTH_NAMES,
                y=list(_pivot_hm.index),
                colorscale="RdYlGn",
                zmid=_zmid,
                zmin=-_zmax, zmax=_zmax,
                text=_pivot_lbl.values,
                texttemplate="%{text}",
                textfont=dict(size=11),
                colorbar=dict(title=_cb_title),
                hovertemplate=f"Mois : %{{x}}<br>Actif : %{{y}}<br>{_cb_title} : {_hover_fmt}<extra></extra>",
            ))
            fig_hm2b.update_layout(**{
                **PLOTLY_DARK,
                "height": 220,
                "margin": dict(l=10, r=10, t=10, b=10),
            })
            st_plotly(fig_hm2b, "t_actif_month_hm", num=69)

        # 3 — Heatmap P&L par mois × pli
        st.markdown("#### 3 — Heatmap P&L Moyen par Mois × Pli OOS")
        hm_data = (
            df_t.groupby(["month", "pli"])["Profit"]
            .mean().unstack(level="pli").reindex(columns=[1, 2, 3])
        )
        hm_data.index   = [_MONTH_NAMES[m - 1] for m in hm_data.index]
        hm_data.columns = [OOS_LABELS.get(c, f"Pli {c}") for c in hm_data.columns]
        fig_hm_t = go.Figure(data=go.Heatmap(
            z=hm_data.values.T,
            x=list(hm_data.index), y=list(hm_data.columns),
            colorscale="RdYlGn", zmid=0,
            text=[[f"${v:.0f}" if not np.isnan(v) else "" for v in row]
                  for row in hm_data.values.T],
            texttemplate="%{text}",
            colorbar=dict(title="P&L moy ($)", tickformat="$.0f"),
            hovertemplate="Mois : %{x}<br>Pli : %{y}<br>P&L : $%{z:.0f}<extra></extra>",
        ))
        fig_hm_t.update_layout(height=300,
                               title="P&L moyen par trade ($) — mois × pli OOS",
                               **PLOTLY_DARK)
        st_plotly(fig_hm_t, "t_heatmap", num=70)

        # 4 — Test statistique sur trades réels
        st.markdown("#### 4 — Test Statistique sur Trades Réels")
        _active_m = st.session_state.get("hyp_b_months", _DEFAULT_ACTIVE_MONTHS)
        _excl_m   = [m for m in range(1, 13) if m not in _active_m]
        grp_act_t = df_t[df_t["month"].isin(_active_m)]["Profit"].dropna()
        grp_exc_t = df_t[df_t["month"].isin(_excl_m)]["Profit"].dropna()

        if len(grp_act_t) < 5 or len(grp_exc_t) < 5:
            st.warning("Échantillons trop petits (< 5 trades par groupe).")
        else:
            stat_t, pval_t     = sp_stats.mannwhitneyu(
                grp_act_t.values, grp_exc_t.values, alternative="two-sided"
            )
            t_stat_t, t_pval_t = sp_stats.ttest_ind(
                grp_act_t.values, grp_exc_t.values, equal_var=False
            )
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Mois actifs — P&L moy", f"${grp_act_t.mean():.0f}",
                      delta=f"N={len(grp_act_t)} trades")
            c2.metric("Mois exclus — P&L moy", f"${grp_exc_t.mean():.0f}",
                      delta=f"N={len(grp_exc_t)} trades")
            c3.metric("Taux gain — actifs",
                      f"{(grp_act_t > 0).mean() * 100:.1f} %")
            c4.metric("Taux gain — exclus",
                      f"{(grp_exc_t > 0).mean() * 100:.1f} %")

            df_dist_t = pd.concat([
                pd.DataFrame({"Profit": grp_act_t.values, "Groupe": "Actifs"}),
                pd.DataFrame({"Profit": grp_exc_t.values, "Groupe": "Exclus"}),
            ])
            fig_dist_t = px.histogram(
                df_dist_t, x="Profit", color="Groupe",
                barmode="overlay", nbins=40, opacity=0.7,
                color_discrete_map={"Actifs": THEME["success"], "Exclus": THEME["danger"]},
                labels={"Profit": "P&L par trade ($)"},
                title="Distribution du P&L par trade — mois actifs vs exclus",
            )
            fig_dist_t.update_layout(height=360, **PLOTLY_DARK)
            st_plotly(fig_dist_t, "t_dist", num=71)

            sig_t = pval_t < 0.05
            delta_t = grp_act_t.mean() - grp_exc_t.mean()
            (st.success if sig_t else st.warning)(
                f"**{'✅' if sig_t else '⚪'} Test P&L réels (N={len(df_t)} trades)**\n\n"
                f"- Mois actifs : **${grp_act_t.mean():.0f}** moy, "
                f"{(grp_act_t > 0).mean() * 100:.1f}% gagnants\n"
                f"- Mois exclus : **${grp_exc_t.mean():.0f}** moy, "
                f"{(grp_exc_t > 0).mean() * 100:.1f}% gagnants\n"
                f"- Écart : ${delta_t:+.0f}/trade\n"
                f"- Mann-Whitney : p={pval_t:.4f} → "
                f"{'**significatif**' if sig_t else '**non significatif**'}\n"
                f"- Welch t-test : p={t_pval_t:.4f}\n\n"
                f"> {_n_done}/{_n_total_runs} passes générées"
            )

            # MaxDD par mois depuis equity par trade
            st.markdown("##### MaxDD estimé par mois")
            dd_rows = []
            for m in range(1, 13):
                sub_m = df_t[df_t["month"] == m].sort_values("Time")
                if sub_m.empty:
                    continue
                if "Balance" in sub_m.columns and sub_m["Balance"].notna().sum() > 2:
                    eq = sub_m["Balance"].dropna().values
                else:
                    eq = 100_000 + sub_m["Profit"].fillna(0).cumsum().values
                roll_max = np.maximum.accumulate(eq)
                dd = ((eq - roll_max) / roll_max * 100).min() if roll_max.max() > 0 else 0.0
                dd_rows.append({
                    "Mois":     _MONTH_NAMES[m - 1],
                    "MaxDD %":  round(float(dd), 2),
                    "N trades": int(len(sub_m)),
                })
            if dd_rows:
                df_dd = pd.DataFrame(dd_rows)
                fig_dd = px.bar(
                    df_dd, x="Mois", y="MaxDD %",
                    color="MaxDD %", color_continuous_scale="RdYlGn_r",
                    text_auto=".2f",
                    title="MaxDD estimé par mois calendaire",
                )
                fig_dd.update_layout(height=360, **PLOTLY_DARK)
                st_plotly(fig_dd, "t_dd_month", num=72)
