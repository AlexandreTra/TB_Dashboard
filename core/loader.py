"""
Chargement récursif des résultats Walk-Forward.

Structure attendue :
    OUTPUT_BASE/<EA_Label>/<Symbol>/<TF>/fold<N>/<stem>_IS.xml
                                                  <stem>_OOS.xml

Exporte :
    scan_result_pairs()  — liste toutes les paires IS/OOS trouvées
    build_kpi_table()    — KPI agrégés, une ligne par (robot, actif, tf, pli)
    load_combo_df()      — passes IS+OOS jointes pour une combinaison (deep dive)
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from core.parser import parse_mt5_xml
from core.mt5_runner import EA_CONFIG, FOLDS, OUTPUT_BASE, SYMBOLS, job_output_paths

# ── Tables de correspondance ──────────────────────────────────────────────────

# Nom de dossier → code court  (ex: "ATR_Breakout" → "ATR")
_LABEL_TO_SHORT: dict[str, str] = {
    cfg["label"].replace(" ", "_"): short
    for short, cfg in EA_CONFIG.items()
}

# Métadonnées par pli (fenêtres IS et OOS pour affichage)
_FOLD_META: dict[int, dict] = {
    f["n"]: {
        "pli_is":  f"{f['from_date'][:4]}–{int(f['forward_date'][:4]) - 1}",
        "pli_oos": f"{f['forward_date'][:4]}–{f['to_date'][:4]}",
    }
    for f in FOLDS
}

# Colonnes MT5 à extraire dans le fichier IS (après normalisation parser)
_IS_METRIC_COLS: list[tuple[str, str]] = [
    ("Back Result",     "IS_Score_Med"),   # OnTester() personnalisé IS
    ("Sharpe Ratio",    "IS_Sharpe_Med"),
    ("Equity DD %",     "IS_DD_Med"),
    ("Profit Factor",   "IS_PF_Med"),
    ("Recovery Factor", "IS_RF_Med"),
]

# Colonnes MT5 à extraire dans le fichier OOS
_OOS_METRIC_COLS: list[tuple[str, str]] = [
    ("Forward Result",  "OOS_Score_Med"),  # OnTester() personnalisé OOS
    ("Back Result",     "IS_Score_OOS_Med"), # score IS re-évalué dans le fichier OOS (cohérence)
    ("Sharpe Ratio",    "OOS_Sharpe_Med"),
    ("Equity DD %",     "OOS_DD_Med"),
    ("Profit Factor",   "OOS_PF_Med"),
    ("Recovery Factor", "OOS_RF_Med"),
]


# ── Helpers internes ──────────────────────────────────────────────────────────

def _parse_path_meta(is_path: Path, output_base: Path) -> dict | None:
    """
    Extrait robot, actif, tf, pli depuis le chemin du fichier IS.
    Chemin : <output_base>/<EA_Label>/<Symbol>/<TF>/fold<N>/<fichier>_IS.xml
    """
    try:
        parts = is_path.relative_to(output_base).parts
        if len(parts) != 5:
            return None
        ea_label_raw, symbol, tf, fold_dir, _ = parts
        m = re.match(r"fold(\d+)$", fold_dir)
        if not m:
            return None
        pli = int(m.group(1))
        if pli not in _FOLD_META:
            return None
        robot = _LABEL_TO_SHORT.get(ea_label_raw)
        if robot is None:
            return None
        return {
            "robot":       robot,
            "robot_label": EA_CONFIG[robot]["label"],
            "actif":       symbol,
            "actif_clean": SYMBOLS.get(symbol, symbol.replace(".TB", "")),
            "timeframe":   tf,
            "pli":         pli,
            **_FOLD_META[pli],
        }
    except Exception:
        return None


def _load_xml(path: Path, min_trades: int) -> pd.DataFrame:
    """Parse un fichier XML MT5 et filtre sur le nombre minimum de trades."""
    df = parse_mt5_xml(path.read_bytes(), path.name)
    if df.empty:
        return pd.DataFrame()
    if "Trades" in df.columns:
        df = df[df["Trades"] >= min_trades].reset_index(drop=True)
    return df


def _safe_median(s: pd.Series) -> float | None:
    v = s.dropna()
    return float(v.median()) if len(v) > 0 else None


# ── API publique ──────────────────────────────────────────────────────────────

def scan_result_pairs(
    output_base: Path = OUTPUT_BASE,
) -> list[tuple[Path, Path | None, dict]]:
    """
    Scanne récursivement output_base.

    Returns
    -------
    list of (is_path, oos_path_or_None, meta_dict)
    """
    if not output_base.exists():
        return []
    result = []
    for is_path in sorted(output_base.rglob("*_IS.xml")):
        meta = _parse_path_meta(is_path, output_base)
        if meta is None:
            continue
        stem = is_path.name[:-7]        # retire "_IS.xml"
        oos_path = is_path.parent / f"{stem}_OOS.xml"
        result.append((is_path, oos_path if oos_path.exists() else None, meta))
    return result


def build_kpi_table(
    output_base: Path = OUTPUT_BASE,
    min_trades: int = 30,
    capital: float = 100_000.0,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Construit le tableau KPI — une ligne par (robot, actif, tf, pli).

    Returns
    -------
    (df_kpi, warnings)
    """
    pairs = scan_result_pairs(output_base)
    warnings: list[str] = []
    rows: list[dict] = []

    for is_path, oos_path, meta in pairs:
        row: dict = {**meta}

        # ── IS ───────────────────────────────────────────────────────────────
        df_is = _load_xml(is_path, min_trades)
        if df_is.empty:
            warnings.append(
                f"IS vide / < {min_trades} trades : "
                f"{meta['robot']}_{meta['actif_clean']}_{meta['timeframe']}_fold{meta['pli']}"
            )
            continue

        row["Nb_Passes_IS"] = len(df_is)
        if "Profit" in df_is.columns:
            p = df_is["Profit"].fillna(0.0)
            row["IS_Return_Med_Pct"]  = float(p.median() / capital * 100)
            row["IS_Return_Best_Pct"] = float(p.max()    / capital * 100)
            row["IS_Pct_Prof"]        = float((p > 0).mean() * 100)
            row["IS_Sum_Profit"]      = float(p.sum())

        for mt5_col, out_col in _IS_METRIC_COLS:
            row[out_col] = _safe_median(df_is[mt5_col]) if mt5_col in df_is.columns else None

        # ── OOS ──────────────────────────────────────────────────────────────
        if oos_path is None:
            warnings.append(
                f"OOS manquant : "
                f"{meta['robot']}_{meta['actif_clean']}_{meta['timeframe']}_fold{meta['pli']}"
            )
            rows.append(row)
            continue

        df_oos = _load_xml(oos_path, min_trades)
        if df_oos.empty:
            warnings.append(f"OOS vide : {oos_path.stem}")
            rows.append(row)
            continue

        row["Nb_Passes_OOS"] = len(df_oos)
        if "Profit" in df_oos.columns:
            p = df_oos["Profit"].fillna(0.0)
            row["OOS_Return_Med_Pct"]  = float(p.median() / capital * 100)
            row["OOS_Return_Best_Pct"] = float(p.max()    / capital * 100)
            row["OOS_Pct_Prof"]        = float((p > 0).mean() * 100)
            row["OOS_Sum_Profit"]      = float(p.sum())

            # WFE = Σ(OOS profit) / Σ(IS profit) × 100
            is_sum = row.get("IS_Sum_Profit", 0.0)
            row["WFE_Pct"] = (row["OOS_Sum_Profit"] / is_sum * 100) if is_sum != 0 else None

        for mt5_col, out_col in _OOS_METRIC_COLS:
            row[out_col] = _safe_median(df_oos[mt5_col]) if mt5_col in df_oos.columns else None

        rows.append(row)

    if not rows:
        return pd.DataFrame(), warnings

    df = pd.DataFrame(rows).sort_values(
        ["robot", "actif", "timeframe", "pli"]
    ).reset_index(drop=True)
    return df, warnings


def load_combo_df(
    robot: str,
    actif: str,
    tf: str,
    pli: int,
    output_base: Path = OUTPUT_BASE,
    min_trades: int = 30,
    capital: float = 100_000.0,
) -> pd.DataFrame:
    """
    Charge les passes IS+OOS jointes pour une combinaison spécifique.
    Utilisé pour le deep dive (plateau, distribution, sensibilité paramétrique).

    Returns
    -------
    DataFrame avec une ligne par passe IS, colonnes IS_* et OOS_* jointes sur Pass.
    """
    is_dest, oos_dest = job_output_paths(robot, actif, tf, pli, output_base)
    if not is_dest.exists():
        return pd.DataFrame()

    df_is = _load_xml(is_dest, min_trades)
    if df_is.empty:
        return pd.DataFrame()

    # Renommage IS
    is_rename = {
        "Back Result":     "IS_Score",
        "Profit":          "IS_Profit",
        "Trades":          "IS_Trades",
        "Profit Factor":   "IS_PF",
        "Recovery Factor": "IS_RF",
        "Sharpe Ratio":    "IS_Sharpe",
        "Equity DD %":     "IS_DD_Pct",
        "Custom":          "IS_Custom",
    }
    df_is = df_is.rename(columns={k: v for k, v in is_rename.items() if k in df_is.columns})

    # Jointure OOS
    if oos_dest.exists():
        df_oos = _load_xml(oos_dest, min_trades)
        if not df_oos.empty and "Pass" in df_oos.columns and "Pass" in df_is.columns:
            oos_rename = {
                "Forward Result":  "OOS_Score",
                "Profit":          "OOS_Profit",
                "Trades":          "OOS_Trades",
                "Profit Factor":   "OOS_PF",
                "Recovery Factor": "OOS_RF",
                "Sharpe Ratio":    "OOS_Sharpe",
                "Equity DD %":     "OOS_DD_Pct",
                "Custom":          "OOS_Custom",
            }
            df_oos = df_oos.rename(
                columns={k: v for k, v in oos_rename.items() if k in df_oos.columns}
            )
            oos_keep = ["Pass"] + [v for v in oos_rename.values() if v in df_oos.columns]
            df = df_is.merge(df_oos[oos_keep], on="Pass", how="left")
        else:
            df = df_is.copy()
    else:
        df = df_is.copy()

    # Métriques dérivées
    if "IS_Profit" in df.columns:
        df["IS_Return_Pct"] = df["IS_Profit"] / capital * 100
    if "OOS_Profit" in df.columns:
        df["OOS_Return_Pct"] = df["OOS_Profit"] / capital * 100
        if "IS_Profit" in df.columns:
            df["WFE_pass"] = (
                df["OOS_Profit"] / df["IS_Profit"].replace(0, float("nan"))
            )

    # Métadonnées
    for k, v in {
        "robot":       robot,
        "robot_label": EA_CONFIG[robot]["label"],
        "actif":       actif,
        "actif_clean": SYMBOLS.get(actif, actif.replace(".TB", "")),
        "timeframe":   tf,
        "pli":         pli,
        **_FOLD_META.get(pli, {}),
    }.items():
        df[k] = v

    return df
