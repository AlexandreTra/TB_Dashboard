"""
📝 Narrative & Export — Génération automatique d'interprétations et export CSV/Excel.

Produit des textes d'analyse académique réutilisables directement dans le TB.
"""
from __future__ import annotations

import io
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

from core.constants import GLOBAL_CSS, THEME
from core.market_data import hurst_interpretation

st.set_page_config(page_title="Narrative & Export", page_icon="📝", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
st.title("📝 Narrative Automatique & Export")
st.markdown(
    "Génération d'**interprétations académiques** basées sur les données analysées. "
    "Ces textes sont conçus pour être intégrés directement dans votre Travail de Bachelor."
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

df_m         = st.session_state["df_master"]
df_k         = st.session_state["df_kpi"]
market_cache = st.session_state.get("market_cache") or {}


# ─────────────────────────────────────────────────────────────────────────────
# Fonctions de génération de narrative
# ─────────────────────────────────────────────────────────────────────────────

def _wfe_label(wfe: float | None) -> str:
    if wfe is None or np.isnan(wfe):
        return "non calculable"
    if wfe >= 80:
        return f"excellente ({wfe:.1f}%)"
    if wfe >= 50:
        return f"acceptable ({wfe:.1f}%)"
    return f"faible ({wfe:.1f}%), indiquant un probable sur-ajustement"


def _ghpr_label(ghpr: float) -> str:
    if ghpr >= 1.005:
        return f"solide ({ghpr:.5f}), supérieur au seuil de rentabilité"
    if ghpr > 1.0:
        return f"marginalement positif ({ghpr:.5f})"
    return f"inférieur à 1.0 ({ghpr:.5f}), indiquant une destruction de capital en capitalisation"


def _sig_label(sig: str, p: float | None) -> str:
    if sig == "✅":
        return f"statistiquement significatifs (p={p:.4f} < 0.05)"
    p_str = f"p={p:.4f}" if p is not None and not np.isnan(p) else "p=N/A"
    return f"non statistiquement significatifs ({p_str} ≥ 0.05)"


def generate_strategy_narrative(row: pd.Series, df_market: pd.DataFrame | None = None) -> str:
    """
    Génère un paragraphe d'analyse académique pour une stratégie donnée.
    """
    strat   = row.get("Stratégie", "—")
    sym     = row.get("Symbole", "—")
    stype   = row.get("Type", "—")
    n       = int(row.get("Nb Passes", 0))
    survie  = row.get("Survie GHPR>1 (%)", 0)
    wfe     = row.get("WFE (%)")
    ghpr    = row.get("GHPR Moyen", 1.0)
    sig     = row.get("Significatif", "❌")
    p_val   = row.get("p-value")
    fwd_ret = row.get("Forward Return % Moy", 0)
    dd      = row.get("Max DD Moyen (%)")

    # Bloc marché
    market_block = ""
    if df_market is not None and not df_market.empty:
        h_mean    = df_market["Hurst"].dropna().mean() if "Hurst" in df_market.columns else None
        adx_mean  = df_market["ADX"].dropna().mean()   if "ADX"   in df_market.columns else None
        dominant  = df_market["Regime"].mode()[0]       if "Regime" in df_market.columns else "N/A"

        h_label = ""
        if h_mean is not None:
            label, _ = hurst_interpretation(h_mean)
            h_label = (
                f"L'exposant de Hurst moyen du marché {sym} sur la période est de **{h_mean:.3f}** "
                f"({label}). "
            )

        adx_label = ""
        if adx_mean is not None:
            adx_label = (
                f"L'ADX mensuel moyen est de **{adx_mean:.1f}**, "
                f"avec un régime dominant **{dominant}**. "
            )

        # Cohérence type × Hurst
        coherence = ""
        if h_mean is not None:
            if stype == "Trend-Following" and h_mean > 0.55:
                coherence = (
                    "Cette configuration est **favorable au Trend-Following** : "
                    "la persistance du marché crée des tendances exploitables. "
                )
            elif stype == "Trend-Following" and h_mean < 0.50:
                coherence = (
                    "La nature **mean-revertante** de ce marché (H<0.5) "
                    "est structurellement défavorable aux stratégies Trend-Following. "
                )
            elif stype == "Mean-Reversion" and h_mean < 0.45:
                coherence = (
                    "Ce marché **mean-revertant** (H<0.45) est "
                    "structurellement favorable aux stratégies Mean-Reversion. "
                )
            elif stype == "Mean-Reversion" and h_mean > 0.55:
                coherence = (
                    "La persistance de ce marché (H>0.55) est "
                    "**défavorable aux stratégies Mean-Reversion**, qui s'attendent à des retours à la moyenne. "
                )

        market_block = f"\n\n{h_label}{adx_label}{coherence}"

    # Construction du texte
    dd_str = f" Le drawdown maximum cumulé moyen est de **{dd:.2f}%**." if dd else ""

    narrative = (
        f"### {strat} ({stype} sur {sym})\n\n"
        f"L'analyse porte sur **{n} passes** d'optimisation Walk-Forward. "
        f"Le taux de survie (passes avec GHPR > 1.0) est de **{survie:.1f}%**, "
        f"ce qui signifie que {survie:.0f}% des configurations testées restent rentables "
        f"en capitalisation composée sur la période de test aveugle.\n\n"
        f"La Walk-Forward Efficiency est {_wfe_label(wfe)}. "
        f"Le GHPR moyen est {_ghpr_label(ghpr)}. "
        f"Le rendement forward moyen par rapport au capital est de **{fwd_ret:.2f}%**."
        f"{dd_str}\n\n"
        f"Les profits forward sont {_sig_label(sig, p_val)}. "
        + (
            "Ce résultat renforce la validité de la stratégie en dehors des données d'entraînement."
            if sig == "✅"
            else "La prudence est de mise avant tout déploiement en conditions réelles."
        )
        + market_block
    )
    return narrative


def generate_global_narrative(df_k: pd.DataFrame, market_cache: dict) -> str:
    """Génère un résumé global de toutes les stratégies analysées."""
    n_strats  = df_k["Stratégie"].nunique() if "Stratégie" in df_k.columns else len(df_k)
    n_symbols = df_k["Symbole"].nunique()   if "Symbole" in df_k.columns else 0
    ghpr_all  = df_k["GHPR Moyen"].dropna()
    wfe_all   = df_k["WFE (%)"].dropna()
    sig_all   = (df_k["Significatif"] == "✅").sum() if "Significatif" in df_k.columns else 0

    best_strat = df_k.loc[df_k["GHPR Moyen"].idxmax()] if not ghpr_all.empty else None
    worst_strat = df_k.loc[df_k["GHPR Moyen"].idxmin()] if not ghpr_all.empty else None

    best_str  = (
        f"La stratégie la plus performante est **{best_strat['Stratégie']}** "
        f"(GHPR={best_strat['GHPR Moyen']:.5f}). "
        if best_strat is not None else ""
    )
    worst_str = (
        f"La moins performante est **{worst_strat['Stratégie']}** "
        f"(GHPR={worst_strat['GHPR Moyen']:.5f})."
        if worst_strat is not None else ""
    )

    # Type dominant
    if "Type" in df_k.columns and "GHPR Moyen" in df_k.columns:
        type_perf = df_k.groupby("Type")["GHPR Moyen"].mean().sort_values(ascending=False)
        best_type = type_perf.index[0] if len(type_perf) > 0 else "N/A"
        best_type_ghpr = type_perf.iloc[0] if len(type_perf) > 0 else 0
        type_block = (
            f"Par famille de stratégie, les **{best_type}** affichent le GHPR moyen le plus élevé "
            f"({best_type_ghpr:.5f}) sur l'ensemble des actifs analysés. "
        )
    else:
        type_block = ""

    return (
        f"## Synthèse Globale de l'Analyse\n\n"
        f"Cette étude porte sur **{n_strats} stratégies algorithmiques** "
        f"réparties sur **{n_symbols} actifs** (principalement des matières premières). "
        f"L'analyse repose sur {len(df_k)} combinaisons stratégie/symbole testées "
        f"par walk-forward optimization sous MetaTrader 5.\n\n"
        f"{type_block}"
        f"{best_str}{worst_str}\n\n"
        f"Le GHPR moyen global est de **{ghpr_all.mean():.5f}** "
        f"(médiane : {ghpr_all.median():.5f}). "
        f"La WFE médiane est de **{wfe_all.median():.1f}%** "
        f"({sig_all}/{len(df_k)} stratégies présentent des profits forward "
        f"statistiquement significatifs à p < 0.05).\n\n"
        f"Ces résultats indiquent que "
        + (
            "la majorité des stratégies testées parvient à générer des profits reproductibles "
            "hors de l'échantillon d'entraînement."
            if ghpr_all.mean() > 1.001
            else "les stratégies testées présentent en moyenne une faible robustesse hors-échantillon, "
                 "suggérant un besoin de révision méthodologique ou de diversification."
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
# Interface
# ─────────────────────────────────────────────────────────────────────────────

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🔧 Options")
    include_market = st.checkbox(
        "Intégrer les données de marché dans la narrative",
        value=True,
        help="Requiert que les données Yahoo Finance aient été téléchargées (page Régime de Marché).",
    )
    lang_fr = st.checkbox("Texte en français", value=True)

# ── Résumé Global ─────────────────────────────────────────────────────────────
st.subheader("🌐 Synthèse Globale")
global_text = generate_global_narrative(df_k, market_cache)
st.markdown(global_text)

# Bouton de copie
with st.expander("📋 Texte brut (copier/coller dans votre TB)"):
    st.code(global_text, language="markdown")

st.divider()

# ── Narrative par stratégie ────────────────────────────────────────────────────
st.subheader("📄 Analyse Détaillée par Stratégie")

for _, row in df_k.iterrows():
    sym       = row.get("Symbole", "")
    df_market = market_cache.get(sym, pd.DataFrame()) if include_market else None

    with st.expander(
        f"{'✅' if row.get('Significatif') == '✅' else '⚠️'} "
        f"{row.get('Stratégie', '—')} | {row.get('Type', '—')} | {sym} "
        f"| GHPR={row.get('GHPR Moyen', 0):.5f} | WFE={row.get('WFE (%)', 0):.1f}%"
    ):
        narrative = generate_strategy_narrative(row, df_market)
        st.markdown(narrative)
        st.code(narrative, language="markdown")

st.divider()

# ── Export ─────────────────────────────────────────────────────────────────────
st.subheader("💾 Export des Données")
st.markdown("Exportez les tableaux pour vos annexes de TB ou votre modèle Excel.")

col_e1, col_e2, col_e3 = st.columns(3)

with col_e1:
    # Export KPI CSV
    csv_kpi = df_k.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="📊 KPI Table (CSV)",
        data=csv_kpi,
        file_name=f"TB_KPI_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
        use_container_width=True,
    )

with col_e2:
    # Export données brutes CSV
    csv_raw = df_m.drop(columns=["Equity"] if "Equity" in df_m.columns else []).to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="🗄️ Données brutes (CSV)",
        data=csv_raw,
        file_name=f"TB_Raw_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
        use_container_width=True,
    )

with col_e3:
    # Export Excel multi-onglets
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_k.to_excel(writer, sheet_name="KPI", index=False)
        df_m.drop(
            columns=[c for c in df_m.columns if c == "Equity"], errors="ignore"
        ).to_excel(writer, sheet_name="Données Brutes", index=False)

        # Feuille régimes de marché
        regime_rows = []
        for sym, df_mkt in market_cache.items():
            if not isinstance(df_mkt, pd.DataFrame) or df_mkt.empty:
                continue
            df_mkt_export = df_mkt.copy().reset_index()
            df_mkt_export.insert(0, "Symbole", sym)
            regime_rows.append(df_mkt_export)
        if regime_rows:
            pd.concat(regime_rows).to_excel(writer, sheet_name="Régimes Marché", index=False)

        # Feuille narrative
        narrative_data = []
        for _, row in df_k.iterrows():
            sym    = row.get("Symbole", "")
            df_mkt = market_cache.get(sym, pd.DataFrame()) if include_market else None
            text   = generate_strategy_narrative(row, df_mkt)
            narrative_data.append({
                "Stratégie": row.get("Stratégie"),
                "Symbole":   sym,
                "Type":      row.get("Type"),
                "Narrative": text,
            })
        pd.DataFrame(narrative_data).to_excel(writer, sheet_name="Narratives", index=False)

    st.download_button(
        label="📑 Rapport complet (Excel)",
        data=buffer.getvalue(),
        file_name=f"TB_Rapport_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

st.divider()

# ── Aide méthodologique ───────────────────────────────────────────────────────
st.subheader("📚 Notes Méthodologiques")
st.markdown("""
#### Cadre d'analyse

Ce dashboard applique un cadre d'analyse en trois niveaux :

1. **Niveau stratégie** *(Vue Globale)*
   - Walk-Forward Efficiency (WFE) pour mesurer la reproductibilité hors-échantillon
   - GHPR pour évaluer la rentabilité en capitalisation composée
   - Test t unilatéral pour la significativité statistique des profits forward

2. **Niveau comparatif** *(Analyse Croisée)*
   - Heatmap Type × Symbole pour identifier les affinités structurelles
   - Carte de performance WFE% vs GHPR pour la sélection de stratégies

3. **Niveau causal** *(Régime de Marché)*
   - Exposant de Hurst pour caractériser la nature intrinsèque de chaque marché
   - ADX pour quantifier la force de tendance
   - Corrélation Spearman Hurst → GHPR par type de stratégie

#### Limites de l'analyse

- Les passes d'optimisation MT5 ne fournissent pas de dates individuelles.
  Le régime de marché est donc affecté à la **période globale de test** déclarée à l'import.
- L'exposant de Hurst est calculé sur des fenêtres glissantes de 90 jours.
  Pour des périodes courtes (< 2 ans), la fiabilité de l'estimation est réduite.
- La significativité statistique (test t) suppose une distribution approximativement normale
  des profits forward, hypothèse à vérifier pour les stratégies à distribution asymétrique.

#### Références

- Sharpe, W. F. (1994). *The Sharpe Ratio*. The Journal of Portfolio Management.
- Hurst, H. E. (1951). *Long-term storage capacity of reservoirs*. ASCE Transactions.
- Pardo, R. (2008). *The Evaluation and Optimization of Trading Strategies*. Wiley.
- Lopez de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley.
""")
