# TB Quant Dashboard

Dashboard Streamlit développé dans le cadre d'un Travail de Bachelor à la HEG Genève.  
Il présente les résultats d'une optimisation Walk-Forward de 6 stratégies algorithmiques sur 6 matières premières (Brent, Gaz Naturel, Or, Platine, Café, Cacao).

---

## Installation

### Prérequis

- Python 3.11 ou supérieur (testé sur 3.14)
- Git

### 1. Cloner le dépôt

```bash
git clone https://github.com/AlexandreTra/TB_Dashboard.git
cd TB_Dashboard
```

### 2. Créer un environnement virtuel et installer les dépendances

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Télécharger les données

Les données sont hébergées séparément (trop volumineuses pour GitHub).

**Lien OneDrive :** [Télécharger data/](https://hessoit-my.sharepoint.com/:f:/g/personal/alexandr_traber_hes-so_ch/IgB3XhV6keV4Tql3r-kdOt9LAQw2wcg_Ju4SHYzTA2PzWso?e=xrjXfn)

Décompresser le dossier `data/` à la racine du projet :

```
TB_Dashboard/
├── data/
│   ├── TB-Python/          (données OHLC CSV — ~63 Mo)
│   ├── TB-MT5/             (exports MT5 : rolls, Bloomberg — ~91 Mo)
│   ├── Résultats_FT/       (résultats Walk-Forward XML — ~16 Go)
│   └── Résultats_Detail/   (journaux de trades individuels — ~10 Mo)
```

> Le dashboard fonctionne sans `Résultats_Detail/` (seule la page Journaux sera vide).  
> Il fonctionne sans `Résultats_FT/` mais ne chargera aucun résultat.

### 4. Lancer le dashboard

```bash
python lancer.py
```

Le navigateur s'ouvre automatiquement sur `http://localhost:8501`.  
Alternative : `streamlit run Accueil.py`

---

## Structure du projet

```
TB_Dashboard/
├── Accueil.py            Point d'entrée Streamlit (navigation)
├── lancer.py             Lance Streamlit + ouvre le navigateur
├── config.py             Chemins de données (relatifs au projet)
├── config_analyse.py     Configuration métier (familles EA, fenêtres OOS)
├── requirements.txt
├── EAs/                  Code source MQL5 des 6 Expert Advisors
│   ├── EA_ATRBreakout_Roll.mq5
│   ├── EA_Breakout_Roll.mq5
│   ├── EA_MeanReversion_Roll.mq5
│   ├── EA_MoyennesMobiles_Roll.mq5
│   ├── EA_TripleEMA_Roll.mq5
│   └── EA_ZScore_Roll.mq5
├── pages/
│   ├── accueil.py        Chargement des données, métriques globales
│   ├── vue_globale.py    Screening + heatmaps IS/OOS par TF
│   ├── benchmarks.py     Stratégies vs Buy & Hold, courbes d'équité
│   ├── profil_actifs.py  Statistiques actifs (Hurst, ADX, saisonnalité)
│   ├── journaux.py       Journaux de trades individuels
│   ├── hypotheses.py     Tests des 3 hypothèses du TB (A / B / C)
│   ├── index_visuels.py  Index recherchable de toutes les visualisations
│   └── mt5_lancer.py     Relancer des optimisations MT5 (Windows uniquement)
└── core/
    ├── loader.py          Scan + parsing des XML Walk-Forward
    ├── parser.py          Lecture XML Excel Microsoft Office (MT5)
    ├── market_data.py     Chargement CSV OHLC + indicateurs (ADX, Hurst)
    ├── analyse_metrics.py KPI Walk-Forward, Buy & Hold, Bloomberg
    ├── hyp_b_content.py   Contenu de l'onglet Hypothèse B
    ├── constants.py       Thème Plotly, CSS global
    ├── ui_helpers.py      Helpers Streamlit (graphiques, exports, badges #N)
    └── mt5_runner.py      Automatisation MetaTrader 5 (Windows uniquement)
```

---

## Compatibilité

| Fonctionnalité | Windows | macOS / Linux |
|---|---|---|
| Consulter le dashboard | ✅ | ✅ |
| Exporter PNG / CSV | ✅ | ✅ |
| Page **Lancer MT5** | ✅ (MT5 requis) | ❌ (affiche un message) |

---

## Relancer les optimisations MT5 (auteur uniquement)

La page **Lancer MT5** est réservée à l'auteur. Elle nécessite MetaTrader 5 installé sur Windows.

Le chemin vers les fichiers `.set` d'optimisation est détecté dans cet ordre :
1. Variable d'environnement `TB_SET_DIR` (chemin absolu vers le dossier Paramètrage_EA)
2. `data/Paramètrage_EA/` dans le projet

Exemple `.env.local` (jamais versionné) :
```
TB_SET_DIR=C:\chemin\vers\Paramètrage_EA
```

Le dossier MetaTrader 5 dans `AppData` est détecté automatiquement.

---

## Index des visualisations

Chaque graphique et tableau du dashboard porte un badge `#N` permettant de le retrouver dans la page **Index des visuels** (84 visualisations numérotées, filtrables par page et type).
