"""
Lecture et validation des exports XML MetaTrader 5 (résultats d'optimisation Walk-Forward).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

import pandas as pd
import streamlit as st

from core.constants import STRATEGY_TYPES, TYPE_KEYWORDS

# Namespace XML MetaTrader
_NS = {"ss": "urn:schemas-microsoft-com:office:spreadsheet"}

# Liste de tous les symboles connus, triés du plus long au plus court
# (pour éviter que "US30" match avant "US300", etc.)
_KNOWN_SYMBOLS: list[str] = sorted([
    "XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD",
    "USOIL", "UKOIL", "NATGAS", "COPPER",
    "WHEAT", "CORN", "SOYBEAN",
    "BTCUSD", "ETHUSD", "BNBUSD",
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
    "AUDUSD", "NZDUSD", "USDCAD", "EURGBP",
    "EURJPY", "GBPJPY", "EURCHF", "AUDCAD",
    "US30", "US100", "US500", "SPX500",
    "NAS100", "GER40", "UK100", "JPN225", "AUS200",
    # Matières premières IC Markets (noms courts dans les fichiers FT_*)
    "NATURALGAS", "PLATINUM", "COFFEE", "COCOA", "BRENT", "GOLD",
], key=len, reverse=True)

# Colonnes obligatoires dans le XML
_REQUIRED_COLS = ["Back Result", "Profit", "Trades"]


# ─────────────────────────────────────────────────────────────────────────────
# Parsing XML
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def parse_mt5_xml(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """
    Parse un export XML d'optimisation Walk-Forward MetaTrader 5.

    Gère les cellules sparse (attribut ss:Index), les valeurs nulles et
    la conversion numérique automatique.

    Parameters
    ----------
    file_bytes : bytes
        Contenu brut du fichier XML.
    filename : str
        Nom du fichier (pour les messages d'erreur).

    Returns
    -------
    pd.DataFrame
        Toutes les colonnes du XML avec conversion numérique automatique.
        DataFrame vide en cas d'erreur.
    """
    try:
        root = ET.fromstring(file_bytes)
    except ET.ParseError as exc:
        st.error(f"[{filename}] Fichier XML invalide : {exc}")
        return pd.DataFrame()
    except Exception as exc:
        st.error(f"[{filename}] Erreur inattendue à la lecture : {exc}")
        return pd.DataFrame()

    all_rows = root.findall(".//ss:Row", _NS)
    if not all_rows:
        st.warning(f"[{filename}] Aucune ligne trouvée dans le XML.")
        return pd.DataFrame()

    # ── Extraction des en-têtes ──────────────────────────────────────────────
    headers: list[str] = []
    for cell in all_rows[0].findall("ss:Cell", _NS):
        node = cell.find("ss:Data", _NS)
        headers.append(node.text.strip() if node is not None and node.text else "")

    if not headers:
        st.warning(f"[{filename}] Aucun en-tête détecté.")
        return pd.DataFrame()

    # ── Extraction des données (gestion des cellules sparse) ─────────────────
    records: list[list[Any]] = []
    for row in all_rows[1:]:
        row_arr = [None] * len(headers)
        col_i = 0
        for cell in row.findall("ss:Cell", _NS):
            # ss:Index indique la position absolue de la cellule (sparse)
            idx_attr = cell.get(f"{{{_NS['ss']}}}Index")
            if idx_attr is not None:
                col_i = int(idx_attr) - 1
            node = cell.find("ss:Data", _NS)
            if col_i < len(headers):
                row_arr[col_i] = node.text if node is not None else None
            col_i += 1
        records.append(row_arr)

    df = pd.DataFrame(records, columns=headers)
    # Conversion numérique colonne par colonne : si toute la colonne se convertit → numérique,
    # sinon on garde les valeurs d'origine (équivalent de l'ancien errors='ignore' déprécié).
    def _to_numeric(col: pd.Series) -> pd.Series:
        try:
            return pd.to_numeric(col)
        except (ValueError, TypeError):
            return col

    df = df.apply(_to_numeric)

    # ── Normalisation du format ──────────────────────────────────────────────
    # Le batch MT5 génère le XML principal (colonne "Result") tandis que
    # l'export Walk-Forward GUI génère "Back Result".
    # On unifie ici pour que le reste du pipeline ne voie qu'un seul format.
    if "Back Result" not in df.columns and "Result" in df.columns:
        df = df.rename(columns={"Result": "Back Result"})

    return df


# ─────────────────────────────────────────────────────────────────────────────
# Détection automatique
# ─────────────────────────────────────────────────────────────────────────────

def detect_symbol(filename: str) -> str:
    """
    Détecte le symbole de trading depuis le nom du fichier XML.

    Recherche dans une liste de symboles connus (du plus long au plus court
    pour éviter les faux positifs). Retourne "INCONNU" si rien n'est trouvé.
    """
    upper = filename.upper()
    for sym in _KNOWN_SYMBOLS:
        if sym in upper:
            return sym
    return "INCONNU"


def guess_strategy_type(filename: str) -> str:
    """
    Heuristique de détection du type de stratégie depuis le nom du fichier.

    Compare le nom (en minuscules) contre les mots-clés définis dans
    core.constants.TYPE_KEYWORDS. Retourne "Autre" si aucun match.
    """
    lower = filename.lower()
    for stype, keywords in TYPE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return stype
    return "Autre"


# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_columns(df: pd.DataFrame) -> tuple[bool, list[str]]:
    """
    Vérifie que les colonnes obligatoires sont présentes.

    Returns
    -------
    (is_valid, missing_columns)
    """
    missing = [c for c in _REQUIRED_COLS if c not in df.columns]
    return (len(missing) == 0), missing


def get_param_columns(df: pd.DataFrame) -> list[str]:
    """
    Retourne les colonnes correspondant aux paramètres de l'EA
    (colonnes dont le nom commence par 'Inp').
    """
    return [c for c in df.columns if str(c).startswith("Inp")]
