"""
Paramètres méthodologiques pour l'analyse des résultats Walk-Forward.
Fichier de configuration pure — aucun import Streamlit.
"""
from __future__ import annotations
from core.mt5_runner import FOLDS

# ── Familles de stratégies ────────────────────────────────────────────────────
ROBOT_FAMILY: dict[str, str] = {
    "ATR":  "Breakout",
    "BK":   "Breakout",
    "MR":   "Mean Reversion",
    "MA":   "Trend Following",
    "TEMA": "Trend Following",
    "ZS":   "Mean Reversion",
}

FAMILY_COLORS: dict[str, str] = {
    "Trend Following": "#4FC3F7",
    "Mean Reversion":  "#FF8A65",
    "Breakout":        "#81C784",
}

FAMILY_ORDER = ["Trend Following", "Mean Reversion", "Breakout"]

# ── Groupes d'actifs ──────────────────────────────────────────────────────────
# Noms "propres" = valeurs de la colonne actif_clean dans df_kpi
ENERGY_ASSETS = ["BRENT", "NATURALGAS"]
AGRI_ASSETS   = ["COFFEE", "COCOA"]
METAL_ASSETS  = ["GOLD", "PLATINUM"]

ALL_ASSETS = ENERGY_ASSETS + METAL_ASSETS + AGRI_ASSETS

ASSET_GROUP: dict[str, str] = {
    "BRENT":      "Énergie",
    "NATURALGAS": "Énergie",
    "COFFEE":     "Agricole",
    "COCOA":      "Agricole",
    "GOLD":       "Métaux",
    "PLATINUM":   "Métaux",
}

ASSET_LABELS: dict[str, str] = {
    "BRENT":      "Brent",
    "NATURALGAS": "Gaz Naturel",
    "COFFEE":     "Café",
    "COCOA":      "Cacao",
    "GOLD":       "Or",
    "PLATINUM":   "Platine",
}

# ── Fenêtres OOS par pli ──────────────────────────────────────────────────────
# forward_date → début OOS ; to_date → fin OOS
# Format des dates FOLDS : "YYYY.MM.DD" → converti en "YYYY-MM-DD"
OOS_WINDOWS: dict[int, tuple[str, str]] = {
    f["n"]: (
        f["forward_date"].replace(".", "-"),
        f["to_date"].replace(".", "-"),
    )
    for f in FOLDS
}

OOS_LABELS: dict[int, str] = {
    1: "Pli 1 (2020–2021)",
    2: "Pli 2 (2022–2023)",
    3: "Pli 3 (2024–2025)",
}

# ── Fenêtres de crise (Hypothèse C) ──────────────────────────────────────────
# Non applicables directement sans courbes d'equity par passe.
# Documentées ici pour référence et utilisation future.
CRISIS_WINDOWS: list[tuple[str, str, str]] = [
    ("2020-02-01", "2020-06-30", "COVID-19"),
    ("2022-02-01", "2022-12-31", "Choc énergie/inflation"),
]

# ── Seuils ────────────────────────────────────────────────────────────────────
MIN_TRADES_THRESHOLD    = 30
PHASE2_SELECTION_METRIC = "OOS_Sharpe_Med"
PHASE2_TOP_N            = 5
