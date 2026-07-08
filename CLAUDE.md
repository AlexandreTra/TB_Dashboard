# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Lancement

```bash
python lancer.py          # ouvre le navigateur automatiquement sur localhost:8501
streamlit run Accueil.py  # alternative directe
```

`lancer.py` est un wrapper qui appelle `streamlit run Accueil.py` et ouvre le navigateur après 4 secondes. `Accueil.py` est le point d'entrée Streamlit réel.

## Architecture générale

Application Streamlit multi-pages utilisant `st.navigation()` (déclaré dans `Accueil.py`). Les pages sont dans `pages/`, les modules partagés dans `core/`.

### Flux de données principal

```
Résultats_FT/<EA>/<Symbole>/<TF>/fold<N>/*_IS.xml + *_OOS.xml
        ↓ core/loader.py (scan_result_pairs + build_kpi_table)
        ↓ core/parser.py (parse_mt5_xml — XML Excel Microsoft Office)
  st.session_state["df_kpi"]   ← toutes les pages lisent d'ici
  st.session_state["df_master"]
```

Le chargement se déclenche depuis `pages/accueil.py` (bouton « Charger les Résultats »). Toutes les autres pages commencent par un guard `if st.session_state.get("df_kpi") is None: st.stop()`.

### Chemins de données — `config.py`

Tous les chemins de données sont centralisés dans `config.py` (racine du projet) :

```python
DATA_DIR        = PROJECT_ROOT / "data"
TB_PYTHON_DIR   = DATA_DIR / "TB-Python"    # CSV OHLC
TB_MT5_DIR      = DATA_DIR / "TB-MT5"       # rolls, Bloomberg
RESULTS_FT_DIR  = DATA_DIR / "Résultats_FT" # XML Walk-Forward
```

- `core/market_data.py` : utilise `TB_PYTHON_DIR` (CSV D1/H1), fallback Yahoo Finance.
- `core/analyse_metrics.py` : utilise `TB_MT5_DIR` (dates_rolls.csv, Bloomberg_Commodity_Index.csv).
- `pages/profil_actifs.py` : utilise `TB_MT5_DIR` (*_M15_MT5.csv).
- `core/mt5_runner.py` : `OUTPUT_BASE = RESULTS_FT_DIR`. Les chemins MT5_EXE et MT5_DATA restent absolus (Windows uniquement, inutiles pour consulter le dashboard).

Sur la machine de développement, `data/` contient des **junctions Windows** qui pointent vers les dossiers originaux (`Travail de bachelor/TB-Python`, etc.) sans copier les données.

### Réutilisation UI

`core/ui_helpers.py` exporte deux helpers utilisés partout :
- `st_plotly(fig, key, filename, height)` — affiche un graphique Plotly + bouton ⬇️ PNG fond blanc (via kaleido).
- `st_df(df, key, filename)` — affiche un DataFrame + bouton ⬇️ CSV.

Tous les graphiques utilisent `PLOTLY_DARK` de `core/constants.py` pour le layout (template sombre, fond transparent). Le PNG exporté utilise `_WHITE_LAYOUT` défini dans `ui_helpers.py` (fond blanc).

### Configuration métier

`config_analyse.py` centralise : familles de stratégies (`ROBOT_FAMILY`), groupes d'actifs, fenêtres OOS (`OOS_WINDOWS`), labels FR. Ne contient aucun chemin.

`core/mt5_runner.py` centralise : chemins MT5, configuration des 6 EAs (`EA_CONFIG`), symboles (`SYMBOLS`), plis Walk-Forward (`FOLDS`), et fonctions de lancement MT5. Ce fichier est aussi importé par `loader.py` uniquement pour `OUTPUT_BASE`, `EA_CONFIG`, `FOLDS`, `SYMBOLS`.

### Pages actives (dans la navigation)

| Fichier | Rôle |
|---|---|
| `pages/accueil.py` | Chargement des données, métriques globales |
| `pages/vue_globale.py` | Tableau screening + heatmaps IS/OOS par TF |
| `pages/benchmarks.py` | Comparaison stratégies vs Buy & Hold, courbes d'équité |
| `pages/profil_actifs.py` | Statistiques intrinsèques des actifs (Hurst, ADX, saisonnalité) |
| `pages/journaux.py` | Journaux de trades individuels (nécessite `Résultats_Detail/`) |
| `pages/hypotheses.py` | Tests des 3 hypothèses du TB (A=Trend/Énergie, B=Filtre saisonnier, C=MR/Métaux) |
| `pages/index_visuels.py` | Index recherchable de toutes les visualisations |
| `pages/mt5_lancer.py` | Interface pour relancer des optimisations MT5 (Windows uniquement) |

Pages présentes dans `pages/` mais **retirées de la navigation** (structure ancienne, incompatible Walk-Forward) : `analyse_croisee.py`, `regime_marche.py`, `sensibilite.py`, `export.py`.

### Hypothèse B (saisonnalité)

`core/hyp_b_content.py` contient tout le contenu de l'onglet B de `pages/hypotheses.py`. Le contenu est appelé via `hyp_b_content.render(tab_b)`. Ce split existe car le fichier `hypotheses.py` devenait trop long.
