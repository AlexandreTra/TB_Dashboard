"""
Fonctions d'analyse sur le df_kpi Walk-Forward.
Transformations pandas pures — aucun import Streamlit.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from config_analyse import ROBOT_FAMILY, OOS_WINDOWS

# ── Chemins externes ───────────────────────────────────────────────────────────
_HERE   = Path(__file__).parent.parent   # TB_Dashboard/
_TB_MT5 = _HERE.parent / "TB-MT5"       # Travail de bachelor/TB-MT5/

# Actif clean → symbole dans dates_rolls.csv
_ACTIF_TO_TB: dict[str, str] = {
    "GOLD":       "GOLD.TB",
    "BRENT":      "BRENT.TB",
    "COCOA":      "COCOA.TB",
    "COFFEE":     "COFFEE.TB",
    "NATURALGAS": "NATURALGAS.TB",
    "PLATINUM":   "PLATINUM.TB",
}


def _load_roll_dates(actif_clean: str) -> set[pd.Timestamp]:
    """Charge les dates de roll depuis TB-MT5/dates_rolls.csv pour un actif."""
    tb_sym = _ACTIF_TO_TB.get(actif_clean.upper(), "")
    if not tb_sym:
        return set()
    csv_path = _TB_MT5 / "dates_rolls.csv"
    if not csv_path.exists():
        return set()
    try:
        df = pd.read_csv(csv_path, header=None, names=["symbol", "date"])
        dates = df.loc[df["symbol"] == tb_sym, "date"]
        return set(pd.to_datetime(dates, format="%Y.%m.%d", errors="coerce").dropna())
    except Exception:
        return set()


def add_family_column(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute la colonne 'famille' (Trend Following / Mean Reversion / Breakout)."""
    out = df.copy()
    out["famille"] = out["robot"].map(ROBOT_FAMILY).fillna("Autre")
    return out


def family_kpi_table(
    df: pd.DataFrame,
    assets: list[str] | None = None,
    metrics: list[str] | None = None,
) -> pd.DataFrame:
    """
    KPI médians par famille, filtré optionnellement sur une liste d'actifs.
    Retourne une ligne par famille.
    """
    if "famille" not in df.columns:
        df = add_family_column(df)
    if assets:
        df = df[df["actif_clean"].isin(assets)]

    default_metrics = [
        "OOS_Return_Med_Pct", "OOS_Pct_Prof", "WFE_Pct",
        "OOS_Sharpe_Med", "OOS_DD_Med", "OOS_PF_Med",
    ]
    cols = metrics if metrics else [c for c in default_metrics if c in df.columns]

    return (
        df.groupby("famille")[cols]
        .median()
        .round(2)
        .reset_index()
    )


def pairwise_family_comparison(
    df: pd.DataFrame,
    family_a: str,
    family_b: str,
    assets: list[str],
    metric: str = "OOS_Sharpe_Med",
) -> dict:
    """
    Compare deux familles sur un groupe d'actifs via la médiane du metric.

    Returns
    -------
    dict avec : family_a, family_b, metric, val_a, val_b, delta, winner, confirmed
    confirmed=True signifie que family_a > family_b.
    """
    if "famille" not in df.columns:
        df = add_family_column(df)

    sub = df[df["actif_clean"].isin(assets)]

    def _med(family: str) -> float:
        vals = sub[sub["famille"] == family][metric].dropna()
        return float(vals.median()) if len(vals) > 0 else float("nan")

    val_a = _med(family_a)
    val_b = _med(family_b)
    delta = val_a - val_b

    return {
        "family_a":  family_a,
        "family_b":  family_b,
        "metric":    metric,
        "val_a":     round(val_a, 3) if not np.isnan(val_a) else None,
        "val_b":     round(val_b, 3) if not np.isnan(val_b) else None,
        "delta":     round(delta, 3) if not np.isnan(delta) else None,
        "winner":    family_a if delta > 0 else family_b,
        "confirmed": bool(delta > 0),
    }


def buyhold_oos_returns(
    actif_clean: str,
    oos_windows: dict[int, tuple[str, str]] = OOS_WINDOWS,
) -> dict[int, dict | None]:
    """
    Rendement Buy&Hold et MaxDD pour chaque pli OOS.

    Source : CSV D1 local TB-Python/ (même série que les backtests MT5).
    Les dates de roll sont neutralisées (rendement mis à 0) via TB-MT5/dates_rolls.csv
    pour éviter que les sauts artificiels de contrat faussent le B&H, notamment sur NG.
    Si le CSV de rolls est absent, retombe sur la formule simple Close_fin/Close_début
    et marque la valeur comme non fiable.

    Returns
    -------
    dict pli_n -> {
        "rdt":           float  — rendement % sur la fenêtre OOS
        "max_dd":        float  — MaxDD % sur la fenêtre OOS
        "roll_adjusted": bool   — True si les dates de roll ont été appliquées
    } | None si données insuffisantes
    """
    from core.market_data import _load_local_ohlc

    df = _load_local_ohlc(actif_clean, timeframe="Daily")
    if df.empty:
        return {n: None for n in oos_windows}

    roll_dates    = _load_roll_dates(actif_clean)
    roll_adjusted = len(roll_dates) > 0

    results: dict[int, dict | None] = {}
    for fold_n, (start, end) in oos_windows.items():
        try:
            window = df.loc[start:end].copy()
            if len(window) < 5:
                results[fold_n] = None
                continue

            if roll_adjusted:
                # Rendements journaliers, jours de roll neutralisés à 0
                daily_ret = window["Close"].pct_change().fillna(0.0)
                daily_ret.loc[window.index.isin(roll_dates)] = 0.0
                cum = (1.0 + daily_ret).cumprod()
            else:
                # Fallback : série continue brute (peut contenir des sauts de roll)
                cum = window["Close"] / window["Close"].iloc[0]

            total_ret = (cum.iloc[-1] - 1.0) * 100.0

            # Max Drawdown sur la série cumulée
            roll_max = cum.cummax()
            max_dd   = float(((cum - roll_max) / roll_max * 100.0).min())

            results[fold_n] = {
                "rdt":           round(float(total_ret), 2),
                "max_dd":        round(max_dd, 2),
                "roll_adjusted": roll_adjusted,
            }
        except Exception:
            results[fold_n] = None

    return results


def bloomberg_oos_returns(
    oos_windows: dict[int, tuple[str, str]] = OOS_WINDOWS,
) -> dict[int, dict | None]:
    """
    Rendement et MaxDD du Bloomberg Commodity Index (DJUBS) pour chaque pli OOS.

    Source : TB-MT5/Bloomberg_Commodity_Index.csv (M15 intraday).
    Rééchantillonné en D1 : dernière clôture du jour (tri Date+Time ascendant, last()).
    Données avant le 2009-06-18 exclues (anomalie d'échelle dans le fichier source,
    niveau ~10x trop élevé sur les 2 premières semaines).

    Index version : DJUBS = Bloomberg Commodity Index Excess Return (ex DJ-UBS Commodity
    Index, renommé en 2014). Inclut le rendement de roll des futures mais exclut le
    retour sur collatéral (T-Bills). Version la plus directement comparable à une
    stratégie futures — à citer ainsi dans le rapport.

    Returns
    -------
    dict pli_n -> {"rdt": float, "max_dd": float} | None
    """
    csv_path = _TB_MT5 / "Bloomberg_Commodity_Index.csv"
    if not csv_path.exists():
        return {n: None for n in oos_windows}

    try:
        raw = pd.read_csv(csv_path)
        raw["Date"]  = pd.to_datetime(raw["Date"],  format="%m/%d/%y", errors="coerce")
        raw["Close"] = pd.to_numeric(raw["$DJUBS.Default Close"],       errors="coerce")
        raw = raw.dropna(subset=["Date", "Close"])

        # Exclure les données aberrantes antérieures au 2009-06-18
        raw = raw[raw["Date"] >= pd.Timestamp("2009-06-18")]

        # Rééchantillonnage M15 → D1 : dernière clôture du jour
        # Tri ascendant sur Date puis Time (format HH:MM, tri alphanumérique correct)
        raw = raw.sort_values(["Date", "Time"], ascending=True)
        daily = (
            raw.groupby("Date")["Close"]
            .last()
            .reset_index()
            .rename(columns={"Date": "Date", "Close": "Close"})
        )
        daily = daily.set_index("Date").sort_index()

    except Exception:
        return {n: None for n in oos_windows}

    results: dict[int, dict | None] = {}
    for fold_n, (start, end) in oos_windows.items():
        try:
            window = daily.loc[start:end]
            if len(window) < 5:
                results[fold_n] = None
                continue

            rdt = (window["Close"].iloc[-1] / window["Close"].iloc[0] - 1.0) * 100.0

            cum      = window["Close"] / window["Close"].iloc[0]
            roll_max = cum.cummax()
            max_dd   = float(((cum - roll_max) / roll_max * 100.0).min())

            results[fold_n] = {
                "rdt":    round(float(rdt), 2),
                "max_dd": round(max_dd, 2),
            }
        except Exception:
            results[fold_n] = None

    return results


def per_fold_family_comparison(
    df: pd.DataFrame,
    family_a: str,
    family_b: str,
    assets: list[str],
    metric: str = "OOS_Sharpe_Med",
) -> pd.DataFrame:
    """
    Comparaison famille_a vs famille_b par actif et par pli.
    Utile pour observer l'effet des crises pli par pli.

    Returns
    -------
    DataFrame avec colonnes : actif_clean, pli, val_a, val_b, delta, winner
    """
    if "famille" not in df.columns:
        df = add_family_column(df)

    sub = df[df["actif_clean"].isin(assets) & df["famille"].isin([family_a, family_b])]

    rows = []
    for (actif, pli), grp in sub.groupby(["actif_clean", "pli"]):
        va = grp[grp["famille"] == family_a][metric].median()
        vb = grp[grp["famille"] == family_b][metric].median()
        d  = va - vb
        rows.append({
            "actif_clean": actif,
            "pli":         pli,
            f"{family_a}": round(float(va), 3) if not np.isnan(va) else None,
            f"{family_b}": round(float(vb), 3) if not np.isnan(vb) else None,
            "delta":       round(float(d), 3)  if not np.isnan(d)  else None,
            "winner":      family_a if d > 0 else family_b,
        })

    return pd.DataFrame(rows).sort_values(["actif_clean", "pli"])
