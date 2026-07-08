"""
Chemins de données centralisés — toujours relatifs à la racine du projet.

Structure attendue après téléchargement des données :

    TB_Dashboard/
    ├── config.py
    ├── data/
    │   ├── TB-Python/        (données OHLC CSV)
    │   ├── TB-MT5/           (exports MT5 : rolls, Bloomberg)
    │   ├── Résultats_FT/     (XML Walk-Forward — 16 GB, à télécharger séparément)
    │   └── Résultats_Detail/ (journaux de trades individuels)
    └── ...

Pour modifier le chemin racine des données, changez DATA_DIR ci-dessous.
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent

DATA_DIR           = PROJECT_ROOT / "data"
TB_PYTHON_DIR      = DATA_DIR / "TB-Python"
TB_MT5_DIR         = DATA_DIR / "TB-MT5"
RESULTS_FT_DIR     = DATA_DIR / "Résultats_FT"
RESULTS_DETAIL_DIR = DATA_DIR / "Résultats_Detail"
