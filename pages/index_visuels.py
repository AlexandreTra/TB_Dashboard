"""
🗂️ Index des Visualisations — Table des matières complète du dashboard.

Permet de rechercher un tableau ou graphique par son numéro, son type,
sa page, ou un mot-clé dans sa description.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.constants import GLOBAL_CSS

st.set_page_config(page_title="Index des Visualisations", page_icon="🗂️", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
st.title("🗂️ Index des Visualisations")
st.markdown(
    "Table des matières complète de tous les tableaux et graphiques du dashboard.  \n"
    "Recherchez par **numéro**, **mot-clé**, **page** ou **type** pour retrouver rapidement une visualisation."
)
st.info(
    "**Téléchargement des graphiques et tableaux :**  \n"
    "Chaque graphique du dashboard possède un bouton **⬇️ PNG** (juste en dessous). "
    "Le fichier exporté utilise automatiquement un **fond blanc, thème clair** — idéal pour Word/PowerPoint.  \n"
    "Les tableaux ont un bouton **⬇️ CSV** équivalent.  \n"
    "Utilisez cet index pour identifier le numéro et la page, puis naviguez via la sidebar pour télécharger."
)

# ── Données ───────────────────────────────────────────────────────────────────
_DATA: list[dict] = [
    # ── PAGE 1 — Accueil ─────────────────────────────────────────────────────
    {"#": 1, "Page": "🏠 Accueil", "Onglet": "—", "Sous-onglet": "—",
     "Type": "Tableau", "Sous-type": "Pivot",
     "Description": "% passes profitables OOS par stratégie × pli",
     "Métriques": "OOS_Pct_Prof", "Filtres": "Aucun",
     "Prérequis": "Données chargées"},

    # ── PAGE 2 — Vue Globale ─────────────────────────────────────────────────
    {"#": 2, "Page": "🌐 Vue Globale", "Onglet": "Tableau Screening", "Sous-onglet": "—",
     "Type": "Tableau", "Sous-type": "Filtrable",
     "Description": "Screening complet : 1 ligne = stratégie × actif × TF × pli avec Score, Rdt IS/OOS, WFE%, Sharpe, DD%",
     "Métriques": "Score OOS, Rdt IS/OOS, WFE%, Sharpe, DD%", "Filtres": "Stratégies, Actifs, TF, Plis (sidebar)",
     "Prérequis": "Données chargées"},
    {"#": 3, "Page": "🌐 Vue Globale", "Onglet": "Tableau Screening", "Sous-onglet": "—",
     "Type": "Tableau", "Sous-type": "Agrégé",
     "Description": "Vue consolidée : moyenne des 3 plis par (Stratégie × Actif × TF)",
     "Métriques": "Rdt OOS, % Prof, WFE%, Sharpe, DD%", "Filtres": "Idem sidebar",
     "Prérequis": "Données chargées"},
    {"#": 4, "Page": "🌐 Vue Globale", "Onglet": "Tableau Screening", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Bar groupé",
     "Description": "Vue d'ensemble : % combinaisons avec Rdt OOS > 0 et % avec majorité passes prof (> 50 %), par actif — toutes stratégies confondues",
     "Métriques": "% combos Rdt>0, % combos PctProf>50%", "Filtres": "Idem sidebar",
     "Prérequis": "Données chargées"},
    {"#": 5, "Page": "🌐 Vue Globale", "Onglet": "Heatmap", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Heatmap",
     "Description": "Heatmap Stratégie × Actif — TF H1 (métrique choisie en sidebar)",
     "Métriques": "Score / Rdt / WFE% / Sharpe / DD% (sélectable)", "Filtres": "Sidebar + sélecteur métrique",
     "Prérequis": "Données chargées"},
    {"#": 6, "Page": "🌐 Vue Globale", "Onglet": "Heatmap", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Heatmap",
     "Description": "Heatmap Stratégie × Actif — TF H4",
     "Métriques": "Idem #5", "Filtres": "Idem #5",
     "Prérequis": "Données chargées"},
    {"#": 7, "Page": "🌐 Vue Globale", "Onglet": "Heatmap", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Heatmap",
     "Description": "Heatmap Stratégie × Actif — TF D1",
     "Métriques": "Idem #5", "Filtres": "Idem #5",
     "Prérequis": "Données chargées"},
    {"#": 8, "Page": "🌐 Vue Globale", "Onglet": "IS vs OOS", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Bar groupé",
     "Description": "Rendement médian IS vs OOS par stratégie × TF (sur-optimisation si IS >>> OOS)",
     "Métriques": "Rdt IS % méd, Rdt OOS % méd", "Filtres": "Sidebar",
     "Prérequis": "Données chargées"},
    {"#": 9, "Page": "🌐 Vue Globale", "Onglet": "IS vs OOS", "Sous-onglet": "—",
     "Type": "Tableau", "Sous-type": "Pivot",
     "Description": "WFE % par stratégie × TF (moyenne des plis et actifs sélectionnés)",
     "Métriques": "WFE%", "Filtres": "Sidebar",
     "Prérequis": "Données chargées"},
    {"#": 10, "Page": "🌐 Vue Globale", "Onglet": "IS vs OOS", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Scatter",
     "Description": "Scatter IS vs OOS : chaque point = 1 combinaison, ligne diagonale IS = OOS",
     "Métriques": "Rdt IS % vs Rdt OOS %", "Filtres": "Sidebar",
     "Prérequis": "Données chargées"},

    # ── PAGE 3 — Benchmarks ─────────────────────────────────────────────────
    {"#": 36, "Page": "📊 Benchmarks", "Onglet": "Heatmap Excédent", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Heatmap (×3 plis)",
     "Description": "Excédent Stratégie − B&H (%) par stratégie × actif, une heatmap par pli OOS",
     "Métriques": "Excédent %", "Filtres": "Sélecteur plis",
     "Prérequis": "Données + CSV D1"},
    {"#": 37, "Page": "📊 Benchmarks", "Onglet": "Rdt Absolu", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Bar groupé",
     "Description": "Rendement OOS absolu vs B&H par actif : barre grise = B&H, barres colorées = chaque famille",
     "Métriques": "Rdt OOS % médian, Rdt B&H %", "Filtres": "Aucun",
     "Prérequis": "Données + CSV D1"},
    {"#": 38, "Page": "📊 Benchmarks", "Onglet": "Par Famille", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Bar groupé",
     "Description": "Excédent médian vs B&H par famille × pli OOS",
     "Métriques": "Excédent %", "Filtres": "Aucun",
     "Prérequis": "Données + CSV D1"},
    {"#": 39, "Page": "📊 Benchmarks", "Onglet": "Par Famille", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Bar groupé",
     "Description": "Excédent médian vs B&H par famille × actif (tous plis)",
     "Métriques": "Excédent %", "Filtres": "Aucun",
     "Prérequis": "Données + CSV D1"},
    {"#": 40, "Page": "📊 Benchmarks", "Onglet": "Par Famille", "Sous-onglet": "—",
     "Type": "Tableau", "Sous-type": "Résumé",
     "Description": "Taux de sur-performance vs B&H par famille (% cas Strat > B&H)",
     "Métriques": "% sur-perf", "Filtres": "Aucun",
     "Prérequis": "Données + CSV D1"},
    {"#": 41, "Page": "📊 Benchmarks", "Onglet": "Par Famille", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Bar groupé",
     "Description": "DJUBS Bloomberg Commodity Index — Rendement et MaxDD par fenêtre OOS",
     "Métriques": "Rdt %, MaxDD %", "Filtres": "Aucun",
     "Prérequis": "CSV Bloomberg_Commodity_Index.csv"},
    {"#": 42, "Page": "📊 Benchmarks", "Onglet": "Courbes Équité", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Ligne",
     "Description": "Courbe d'équité OOS cumulée stratégie vs Buy&Hold sur la même fenêtre (sélecteur robot × actif × TF × pli × passe)",
     "Métriques": "Capital ($) dans le temps, MaxDD, écart vs B&H", "Filtres": "5 sélecteurs",
     "Prérequis": "⚠️ Backtests individuels MT5"},
    {"#": 43, "Page": "📊 Benchmarks", "Onglet": "Tableau Détaillé", "Sous-onglet": "—",
     "Type": "Tableau", "Sous-type": "Filtrable",
     "Description": "Détail stratégie × actif × pli : Rdt OOS, Rdt B&H, MaxDD B&H, Excédent",
     "Métriques": "Rdt OOS %, Rdt B&H %, MaxDD B&H %, Excédent %", "Filtres": "Sélecteur stratégie, actif",
     "Prérequis": "Données + CSV D1"},
    {"#": 44, "Page": "📊 Benchmarks", "Onglet": "Tableau Détaillé", "Sous-onglet": "—",
     "Type": "Tableau", "Sous-type": "Référence",
     "Description": "Rendements B&H de référence par actif × pli (roll-ajusté)",
     "Métriques": "Rdt B&H %, MaxDD B&H %", "Filtres": "Aucun",
     "Prérequis": "CSV D1"},
    {"#": 45, "Page": "📊 Benchmarks", "Onglet": "Tableau Détaillé", "Sous-onglet": "—",
     "Type": "Tableau", "Sous-type": "Référence",
     "Description": "Benchmark DJUBS par fenêtre OOS",
     "Métriques": "Rdt DJUBS %, MaxDD DJUBS %", "Filtres": "Aucun",
     "Prérequis": "CSV Bloomberg"},

    # ── PAGE 7 — Profil des Actifs ───────────────────────────────────────────
    {"#": 46, "Page": "🧬 Profil des Actifs", "Onglet": "Tableaux Récap", "Sous-onglet": "H1 / H4 / D1",
     "Type": "Tableau", "Sous-type": "Métriques complètes",
     "Description": "Tableau récap par TF : Vol, Hurst, ADF, Autocorr, Skew, Kurt, ADX, Saisonnalité, Famille Prédite",
     "Métriques": "Toutes métriques statistiques", "Filtres": "Sélecteur TF (sous-onglet)",
     "Prérequis": "CSV M15 TB-MT5"},
    {"#": 47, "Page": "🧬 Profil des Actifs", "Onglet": "Comparaison Inter-TF", "Sous-onglet": "—",
     "Type": "Tableau", "Sous-type": "Pivot (×3)",
     "Description": "Stabilité inter-TF : Hurst, Autocorr L1, Vol Ann% comparés H1 vs H4 vs D1 pour chaque actif",
     "Métriques": "Hurst, Autocorr L1, Vol Ann%", "Filtres": "Aucun",
     "Prérequis": "CSV M15 TB-MT5"},
    {"#": 48, "Page": "🧬 Profil des Actifs", "Onglet": "Visualisations", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Bar groupé",
     "Description": "Volatilité annualisée (%) par actif, pour les 3 TF superposés",
     "Métriques": "Vol Ann %", "Filtres": "Sélecteur TF de référence",
     "Prérequis": "CSV M15 TB-MT5"},
    {"#": 49, "Page": "🧬 Profil des Actifs", "Onglet": "Visualisations", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Bar",
     "Description": "Exposant de Hurst par actif (coloré par interprétation)",
     "Métriques": "H", "Filtres": "Sélecteur TF de référence",
     "Prérequis": "CSV M15 TB-MT5"},
    {"#": 50, "Page": "🧬 Profil des Actifs", "Onglet": "Visualisations", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Scatter",
     "Description": "Scatter Hurst × Autocorrélation : 1 point par actif, lignes H=0.5 et AC=0 — carte Trend/MR",
     "Métriques": "H (X) vs Autocorr L1 (Y)", "Filtres": "Sélecteur TF de référence",
     "Prérequis": "CSV M15 TB-MT5"},
    {"#": 51, "Page": "🧬 Profil des Actifs", "Onglet": "Visualisations", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Heatmap",
     "Description": "Saisonnalité mensuelle : rendement log moyen (%) par mois — Café et Cacao (D1)",
     "Métriques": "Rdt log % mensuel", "Filtres": "Aucun",
     "Prérequis": "CSV M15 TB-MT5"},
    {"#": 52, "Page": "🧬 Profil des Actifs", "Onglet": "Visualisations", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Bar groupé",
     "Description": "ADX(14) moyen par actif pour les 3 TF (seuil 25 en référence)",
     "Métriques": "ADX moyen", "Filtres": "Aucun",
     "Prérequis": "CSV M15 TB-MT5"},
    {"#": 53, "Page": "🧬 Profil des Actifs", "Onglet": "Prédiction vs Réalité", "Sous-onglet": "—",
     "Type": "Tableau", "Sous-type": "Comparatif + Export PNG",
     "Description": "Par actif : Hurst D1 → régime prédit → famille attendue vs famille réellement gagnante OOS → accord ✅/❌/🟡",
     "Métriques": "Hurst, régime, famille attendue, famille gagnante OOS", "Filtres": "Aucun",
     "Prérequis": "CSV M15 + données chargées"},

    # ── PAGE 8 — Hypothèses A ────────────────────────────────────────────────
    {"#": 54, "Page": "🔬 Hypothèses", "Onglet": "A — Trend / Énergie", "Sous-onglet": "—",
     "Type": "Tableau", "Sous-type": "KPI",
     "Description": "KPI par famille sur BRENT + NATURALGAS uniquement : Rdt, % Prof, WFE%, Sharpe, DD%",
     "Métriques": "Rdt, % Prof, WFE%, Sharpe, DD%", "Filtres": "Aucun",
     "Prérequis": "Données chargées"},
    {"#": 55, "Page": "🔬 Hypothèses", "Onglet": "A — Trend / Énergie", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Bar groupé",
     "Description": "Comparaison famille × actif (Brent/GazNat) par métrique sélectionnée",
     "Métriques": "Sélectable", "Filtres": "Sélecteur métrique",
     "Prérequis": "Données chargées"},
    {"#": 56, "Page": "🔬 Hypothèses", "Onglet": "A — Trend / Énergie", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Boxplot",
     "Description": "Distribution de la métrique par famille × pli (facettes Brent / GazNat)",
     "Métriques": "Sélectable", "Filtres": "Sélecteur métrique",
     "Prérequis": "Données chargées"},

    # ── PAGE 8 — Hypothèses B ────────────────────────────────────────────────
    {"#": 57, "Page": "🔬 Hypothèses", "Onglet": "B — Filtre Saisonnier", "Sous-onglet": "Performance MR/ZS",
     "Type": "Graphique", "Sous-type": "Bar groupé",
     "Description": "Performance OOS par pli — MR & ZS sur Café et Cacao (métrique sélectable)",
     "Métriques": "Score, Rdt, DD%, Sharpe, WFE% (sélectable)", "Filtres": "Sélecteur TF, métrique",
     "Prérequis": "Données chargées"},
    {"#": 58, "Page": "🔬 Hypothèses", "Onglet": "B — Filtre Saisonnier", "Sous-onglet": "Performance MR/ZS",
     "Type": "Tableau", "Sous-type": "KPI",
     "Description": "KPI résumé par combinaison robot × actif × TF × pli",
     "Métriques": "Score, Rdt, DD%, Sharpe, WFE%, N passes", "Filtres": "Aucun",
     "Prérequis": "Données chargées"},
    {"#": 59, "Page": "🔬 Hypothèses", "Onglet": "B — Filtre Saisonnier", "Sous-onglet": "Performance MR/ZS",
     "Type": "Tableau + Scatter", "Sous-type": "Expanders (×N combos)",
     "Description": "Top N passes par combo (expander) : tableau + score vs drawdown",
     "Métriques": "OOS_Score, MaxDD, Profit, Trades", "Filtres": "Slider Top N",
     "Prérequis": "Données chargées"},
    {"#": 60, "Page": "🔬 Hypothèses", "Onglet": "B — Filtre Saisonnier", "Sous-onglet": "Saisonnalité",
     "Type": "Graphique", "Sous-type": "Bar groupé",
     "Description": "Rendement log mensuel moyen Café et Cacao 2015–2025 (côte à côte)",
     "Métriques": "Rdt log % mensuel", "Filtres": "Aucun",
     "Prérequis": "CSV D1 TB-Python"},
    {"#": 61, "Page": "🔬 Hypothèses", "Onglet": "B — Filtre Saisonnier", "Sous-onglet": "Saisonnalité",
     "Type": "Tableau", "Sous-type": "Statistiques (×2)",
     "Description": "Statistiques mensuelles Café et Cacao : N obs, moy, médiane, écart-type, % positif",
     "Métriques": "Stats mensuelles", "Filtres": "Aucun",
     "Prérequis": "CSV D1 TB-Python"},
    {"#": 62, "Page": "🔬 Hypothèses", "Onglet": "B — Filtre Saisonnier", "Sous-onglet": "Saisonnalité",
     "Type": "Graphique", "Sous-type": "Boxplot (×2, expander)",
     "Description": "Distribution mensuelle détaillée Café et Cacao (dans expander)",
     "Métriques": "Rdt log % mensuel", "Filtres": "Aucun",
     "Prérequis": "CSV D1 TB-Python"},
    {"#": 63, "Page": "🔬 Hypothèses", "Onglet": "B — Filtre Saisonnier", "Sous-onglet": "Stabilité Temporelle",
     "Type": "Graphique", "Sous-type": "Heatmap (×2)",
     "Description": "Rdt log mensuel moyen par pli OOS — Café puis Cacao (lignes = plis, colonnes = mois)",
     "Métriques": "Rdt % mensuel", "Filtres": "Aucun",
     "Prérequis": "CSV D1 TB-Python"},
    {"#": 64, "Page": "🔬 Hypothèses", "Onglet": "B — Filtre Saisonnier", "Sous-onglet": "Stabilité Temporelle",
     "Type": "Tableau", "Sous-type": "Corrélation",
     "Description": "Corrélation de Spearman des rangs mensuels entre plis (stabilité du signal saisonnier)",
     "Métriques": "Rho, p-value, ✅/⚪ stable", "Filtres": "Aucun",
     "Prérequis": "CSV D1 TB-Python"},
    {"#": 65, "Page": "🔬 Hypothèses", "Onglet": "B — Filtre Saisonnier", "Sous-onglet": "Synthèse & Test",
     "Type": "Graphique", "Sous-type": "Histogramme (×2)",
     "Description": "Distribution mois actifs vs exclus — Café puis Cacao (Mann-Whitney + Welch t-test)",
     "Métriques": "Rdt log % mensuel", "Filtres": "Sélecteur mois actifs",
     "Prérequis": "CSV D1 TB-Python"},
    {"#": 66, "Page": "🔬 Hypothèses", "Onglet": "B — Filtre Saisonnier", "Sous-onglet": "Journaux de Trades",
     "Type": "Tableau", "Sous-type": "Couverture",
     "Description": "Couverture des journaux : ✅/🔲 par combinaison robot × actif × TF × pli × passe",
     "Métriques": "Statut best/median/worst", "Filtres": "Aucun",
     "Prérequis": "⚠️ Backtests individuels MT5"},
    {"#": 67, "Page": "🔬 Hypothèses", "Onglet": "B — Filtre Saisonnier", "Sous-onglet": "Journaux de Trades",
     "Type": "Graphique", "Sous-type": "Bar groupé",
     "Description": "Nombre de trades par mois calendaire (Meilleure / Médiane / Pire passe)",
     "Métriques": "N trades", "Filtres": "Sélecteur famille, actif, TF",
     "Prérequis": "⚠️ Backtests individuels MT5"},
    {"#": 68, "Page": "🔬 Hypothèses", "Onglet": "B — Filtre Saisonnier", "Sous-onglet": "Journaux de Trades",
     "Type": "Tableau", "Sous-type": "Récapitulatif mensuel",
     "Description": "Récap P&L agrégé par mois : N trades, PnL moy ($), P&L total, taux gain %",
     "Métriques": "$", "Filtres": "Sélecteur famille, actif, TF",
     "Prérequis": "⚠️ Backtests individuels MT5"},
    {"#": 69, "Page": "🔬 Hypothèses", "Onglet": "B — Filtre Saisonnier", "Sous-onglet": "Journaux de Trades",
     "Type": "Graphique", "Sous-type": "Heatmap",
     "Description": "Rendement % par trade normalisé (Profit / (Balance−Profit) × 100) — Café / Cacao × Mois",
     "Métriques": "Rdt % par trade (normalisé compound)", "Filtres": "Sélecteur famille, actif, TF",
     "Prérequis": "⚠️ Backtests individuels MT5"},
    {"#": 70, "Page": "🔬 Hypothèses", "Onglet": "B — Filtre Saisonnier", "Sous-onglet": "Journaux de Trades",
     "Type": "Graphique", "Sous-type": "Heatmap",
     "Description": "P&L moyen par trade ($) — Mois × Pli OOS",
     "Métriques": "$ par trade", "Filtres": "Idem #69",
     "Prérequis": "⚠️ Backtests individuels MT5"},
    {"#": 71, "Page": "🔬 Hypothèses", "Onglet": "B — Filtre Saisonnier", "Sous-onglet": "Journaux de Trades",
     "Type": "Graphique", "Sous-type": "Histogramme",
     "Description": "Distribution du P&L par trade — mois actifs vs exclus (test statistique sur trades réels)",
     "Métriques": "$ par trade", "Filtres": "Sélecteur mois actifs (partagé avec tab Synthèse)",
     "Prérequis": "⚠️ Backtests individuels MT5"},
    {"#": 72, "Page": "🔬 Hypothèses", "Onglet": "B — Filtre Saisonnier", "Sous-onglet": "Journaux de Trades",
     "Type": "Graphique", "Sous-type": "Bar",
     "Description": "MaxDD estimé par mois calendaire (depuis equity cumulée par trade)",
     "Métriques": "MaxDD %", "Filtres": "Idem #69",
     "Prérequis": "⚠️ Backtests individuels MT5"},

    # ── PAGE 8 — Hypothèses C ────────────────────────────────────────────────
    {"#": 73, "Page": "🔬 Hypothèses", "Onglet": "C — Mean Rev / Métaux", "Sous-onglet": "—",
     "Type": "Tableau", "Sous-type": "KPI",
     "Description": "KPI par famille sur GOLD + PLATINUM uniquement : Rdt, % Prof, WFE%, Sharpe, DD%",
     "Métriques": "Rdt, % Prof, WFE%, Sharpe, DD%", "Filtres": "Aucun",
     "Prérequis": "Données chargées"},
    {"#": 74, "Page": "🔬 Hypothèses", "Onglet": "C — Mean Rev / Métaux", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Bar groupé",
     "Description": "MR vs Trend Following par pli et par actif (Or / Platine)",
     "Métriques": "Sélectable", "Filtres": "Sélecteur métrique",
     "Prérequis": "Données chargées"},
    {"#": 75, "Page": "🔬 Hypothèses", "Onglet": "C — Mean Rev / Métaux", "Sous-onglet": "—",
     "Type": "Tableau", "Sous-type": "Comparatif",
     "Description": "Récap par pli avec delta MR − Trend Following et famille gagnante",
     "Métriques": "Δ métrique, vainqueur", "Filtres": "Aucun",
     "Prérequis": "Données chargées"},

    # ── PAGE 9 — Journaux de Trades ─────────────────────────────────────────
    {"#": 76, "Page": "📋 Journaux", "Onglet": "Mensuel", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Heatmap",
     "Description": "P&L moyen par trade ($) — Actif × Mois calendaire",
     "Métriques": "$ par trade", "Filtres": "Sidebar",
     "Prérequis": "⚠️ Backtests individuels MT5"},
    {"#": 77, "Page": "📋 Journaux", "Onglet": "Mensuel", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Heatmap",
     "Description": "P&L moyen par trade ($) — Famille de stratégie × Mois calendaire",
     "Métriques": "$ par trade", "Filtres": "Sidebar",
     "Prérequis": "⚠️ Backtests individuels MT5"},
    {"#": 78, "Page": "📋 Journaux", "Onglet": "Mensuel", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Bar",
     "Description": "P&L moyen par mois calendaire (couleur interactive : actif / famille / classe d'actif)",
     "Métriques": "$ moyen", "Filtres": "Sélecteur couleur",
     "Prérequis": "⚠️ Backtests individuels MT5"},
    {"#": 79, "Page": "📋 Journaux", "Onglet": "Mensuel", "Sous-onglet": "—",
     "Type": "Tableau", "Sous-type": "Récapitulatif",
     "Description": "Récap Actif × Mois : N trades, P&L moy, P&L total, Win%",
     "Métriques": "$", "Filtres": "Sidebar",
     "Prérequis": "⚠️ Backtests individuels MT5"},
    {"#": 80, "Page": "📋 Journaux", "Onglet": "Comparaison", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Bar horizontal",
     "Description": "Top 20 robot × actif — P&L total OOS (classement)",
     "Métriques": "$ total", "Filtres": "Aucun",
     "Prérequis": "⚠️ Backtests individuels MT5"},
    {"#": 81, "Page": "📋 Journaux", "Onglet": "Comparaison", "Sous-onglet": "—",
     "Type": "Tableau", "Sous-type": "Ranking",
     "Description": "Ranking robot × actif : P&L total, moy, N trades, Win%",
     "Métriques": "$", "Filtres": "Aucun",
     "Prérequis": "⚠️ Backtests individuels MT5"},
    {"#": 82, "Page": "📋 Journaux", "Onglet": "Comparaison", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Heatmap",
     "Description": "P&L moyen par trade ($) — Robot × Actif",
     "Métriques": "$ par trade", "Filtres": "Aucun",
     "Prérequis": "⚠️ Backtests individuels MT5"},
    {"#": 83, "Page": "📋 Journaux", "Onglet": "Comparaison", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Bar",
     "Description": "Écart Meilleure vs Pire passe par actif (robustesse de la sélection)",
     "Métriques": "Δ $ entre best et worst", "Filtres": "Aucun",
     "Prérequis": "⚠️ Backtests individuels MT5"},
    {"#": 84, "Page": "📋 Journaux", "Onglet": "Comparaison", "Sous-onglet": "—",
     "Type": "Graphique", "Sous-type": "Ligne",
     "Description": "Dérive temporelle — P&L moyen par pli OOS par famille de stratégie",
     "Métriques": "$ moyen par trade par pli", "Filtres": "Aucun",
     "Prérequis": "⚠️ Backtests individuels MT5"},
]

_df = pd.DataFrame(_DATA)

# ── Mapping page label → fichier Streamlit ───────────────────────────────────
_PAGE_FILE: dict[str, str] = {
    "🏠 Accueil":           "pages/accueil.py",
    "🌐 Vue Globale":       "pages/vue_globale.py",
    "📊 Benchmarks":        "pages/benchmarks.py",
    "🧬 Profil des Actifs": "pages/profil_actifs.py",
    "📋 Journaux":          "pages/journaux.py",
    "🔬 Hypothèses":        "pages/hypotheses.py",
}

# ── Filtres ───────────────────────────────────────────────────────────────────
st.markdown("---")
col_f1, col_f2, col_f3, col_f4 = st.columns([2, 2, 1, 1])

with col_f1:
    _search = st.text_input(
        "🔍 Recherche par mot-clé",
        placeholder="ex : heatmap, saisonnalité, hurst, équité…",
        key="idx_search",
    )
with col_f2:
    _pages = ["Toutes"] + sorted(_df["Page"].unique().tolist())
    _sel_page = st.selectbox("Page", _pages, key="idx_page")
with col_f3:
    _types = ["Tous"] + sorted(_df["Type"].unique().tolist())
    _sel_type = st.selectbox("Type", _types, key="idx_type")
with col_f4:
    _req_filter = st.selectbox(
        "Prérequis",
        ["Tous", "Sans prérequis spéciaux", "⚠️ Backtests MT5 requis"],
        key="idx_req",
    )

# Numéro direct
_num_input = st.number_input(
    "🔢 Aller directement au numéro",
    min_value=0, max_value=int(_df["#"].max()), value=0, step=1,
    help="Entrez 0 pour ignorer. Met en surbrillance la ligne correspondante.",
    key="idx_num",
)

# ── Application des filtres ───────────────────────────────────────────────────
_mask = pd.Series([True] * len(_df))

if _num_input > 0:
    _mask &= _df["#"] == _num_input

if _search.strip():
    _kw = _search.strip().lower()
    _mask &= (
        _df["Description"].str.lower().str.contains(_kw, na=False) |
        _df["Métriques"].str.lower().str.contains(_kw, na=False) |
        _df["Onglet"].str.lower().str.contains(_kw, na=False) |
        _df["Sous-onglet"].str.lower().str.contains(_kw, na=False) |
        _df["Sous-type"].str.lower().str.contains(_kw, na=False)
    )

if _sel_page != "Toutes":
    _mask &= _df["Page"] == _sel_page

if _sel_type != "Tous":
    _mask &= _df["Type"].str.contains(_sel_type, na=False)

if _req_filter == "Sans prérequis spéciaux":
    _mask &= ~_df["Prérequis"].str.contains("⚠️", na=False)
elif _req_filter == "⚠️ Backtests MT5 requis":
    _mask &= _df["Prérequis"].str.contains("⚠️ Backtests", na=False)

_df_filtered = _df[_mask].reset_index(drop=True)

# ── Résultats ─────────────────────────────────────────────────────────────────
n_total    = len(_df)
n_filtered = len(_df_filtered)

st.markdown(f"**{n_filtered} / {n_total} visualisations** correspondant aux filtres.")

if _df_filtered.empty:
    st.info("Aucun résultat. Modifiez les filtres.")
else:
    st.caption("👆 Cliquez sur une ligne pour accéder directement à la visualisation.")

    _event = st.dataframe(
        _df_filtered,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        height=min(50 + n_filtered * 38, 700),
        column_config={
            "#":           st.column_config.NumberColumn("#", width="small"),
            "Page":        st.column_config.TextColumn("Page", width="medium"),
            "Onglet":      st.column_config.TextColumn("Onglet", width="medium"),
            "Sous-onglet": st.column_config.TextColumn("Sous-onglet", width="medium"),
            "Type":        st.column_config.TextColumn("Type", width="small"),
            "Sous-type":   st.column_config.TextColumn("Sous-type", width="small"),
            "Description": st.column_config.TextColumn("Description", width="large"),
            "Métriques":   st.column_config.TextColumn("Métriques", width="medium"),
            "Filtres":     st.column_config.TextColumn("Filtres", width="medium"),
            "Prérequis":   st.column_config.TextColumn("Prérequis", width="medium"),
        },
        key="idx_table",
    )

    # ── Navigation sur sélection de ligne ────────────────────────────────────
    _sel_rows = _event.selection.rows if _event and _event.selection else []
    if _sel_rows:
        _r = _df_filtered.iloc[_sel_rows[0]]
        _pg_file = _PAGE_FILE.get(_r["Page"])
        _loc_str = f"Onglet **{_r['Onglet']}**"
        if _r["Sous-onglet"] != "—":
            _loc_str += f" → sous-onglet **{_r['Sous-onglet']}**"

        st.markdown("---")
        st.markdown(
            f"**#{int(_r['#'])} — {_r['Description']}**  \n"
            f"📍 {_r['Page']} · {_loc_str}"
        )
        if _r["Prérequis"].startswith("⚠️"):
            st.warning(f"Prérequis : {_r['Prérequis']}")

        if _pg_file:
            st.page_link(
                _pg_file,
                label=f"→ Ouvrir : {_r['Page']}",
                use_container_width=False,
            )

    # ── Bouton CSV ────────────────────────────────────────────────────────────
    from datetime import datetime as _dt
    _csv_bytes = _df_filtered.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="⬇️ CSV — exporter cette sélection",
        data=_csv_bytes,
        file_name=f"index_visuels_{_dt.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
        key="dl_index_csv",
    )

# ── Statistiques rapides ───────────────────────────────────────────────────────
st.markdown("---")
st.markdown("#### Répartition globale")
_c1, _c2, _c3, _c4 = st.columns(4)
_c1.metric("Total visualisations", n_total)
_c2.metric("Graphiques", int((_df["Type"].str.contains("Graphique")).sum()))
_c3.metric("Tableaux", int((_df["Type"].str.contains("Tableau")).sum()))
_c4.metric("⚠️ Backtests requis", int(_df["Prérequis"].str.contains("⚠️ Backtests").sum()))
