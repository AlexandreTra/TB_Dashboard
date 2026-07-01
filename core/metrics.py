"""
Calcul de toutes les métriques quantitatives :
AHPR, GHPR, WFE, test de significativité, sensibilité paramétrique.
"""
from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st
from scipy import stats


# ─────────────────────────────────────────────────────────────────────────────
# Métriques de base par pass
# ─────────────────────────────────────────────────────────────────────────────

def add_base_metrics(df: pd.DataFrame, capital: float) -> pd.DataFrame:
    """
    Enrichit le DataFrame brut MT5 avec les métriques financières fondamentales.

    Métriques ajoutées
    ------------------
    - Back Profit       : profit backtest absolu ($)
    - Final Balance     : capital final forward ($)
    - Forward Return %  : rendement forward en %
    - Back Return %     : rendement backtest en %
    - AHPR              : rendement arithmétique moyen par trade (>1 = rentable)
    - GHPR              : rendement géométrique moyen par trade (>1 = rentable en compound)
    """
    df = df.copy()
    safe_trades = df["Trades"].clip(lower=1)

    df["Back Profit"]      = df["Back Result"] - capital
    df["Final Balance"]    = capital + df["Profit"]
    df["Forward Return %"] = df["Profit"]      / capital * 100
    df["Back Return %"]    = df["Back Profit"] / capital * 100

    # AHPR = 1 + (rendement total / nb_trades)  — biais arithmétique
    df["AHPR"] = 1 + (df["Profit"] / capital) / safe_trades

    # GHPR = (capital_final / capital_initial)^(1/nb_trades)  — capitalisation réelle
    ratio = (df["Final Balance"] / capital).clip(lower=1e-12)
    df["GHPR"] = ratio ** (1.0 / safe_trades)
    df["GHPR"] = df["GHPR"].replace([np.inf, -np.inf], np.nan)

    return df


# ─────────────────────────────────────────────────────────────────────────────
# Walk-Forward Efficiency + significativité statistique
# ─────────────────────────────────────────────────────────────────────────────

def compute_wfe(group: pd.DataFrame) -> dict[str, Any]:
    """
    Calcule la Walk-Forward Efficiency et teste sa significativité.

    WFE = Σ(forward_profit) / Σ(back_profit) × 100

    Test statistique : t-test unilatéral sur les profits forward.
    H₀ : μ(forward_profit) = 0
    H₁ : μ(forward_profit) > 0
    → Si p < 0.05 et t > 0 : les profits forward sont significativement positifs.

    Returns
    -------
    dict avec : wfe, t_stat, p_value, significant, degrad_mean, degrad_std,
                total_forward, total_back, nb_passes_positives
    """
    bp = group["Back Profit"].values.astype(float)
    fp = group["Profit"].values.astype(float)

    total_bp = bp.sum()
    total_fp = fp.sum()
    wfe = (total_fp / total_bp * 100) if total_bp > 0 else np.nan

    # t-test unilatéral (one-sample, one-tailed)
    if len(fp) >= 3:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            t_stat, p_val_2sided = stats.ttest_1samp(fp, popmean=0.0)
        p_val      = p_val_2sided / 2  # one-tailed
        significant = (t_stat > 0) and (p_val < 0.05)
    else:
        t_stat, p_val, significant = np.nan, np.nan, False

    # Rapport de dégradation par pass individuel
    with np.errstate(divide="ignore", invalid="ignore"):
        degrad = np.where(bp != 0, fp / bp, np.nan)

    return {
        "wfe":               wfe,
        "t_stat":            float(t_stat) if not np.isnan(t_stat) else np.nan,
        "p_value":           float(p_val)  if not np.isnan(p_val)  else np.nan,
        "significant":       significant,
        "degrad_mean":       float(np.nanmean(degrad)),
        "degrad_std":        float(np.nanstd(degrad)),
        "total_forward":     float(total_fp),
        "total_back":        float(total_bp),
        "nb_passes_positives": int((fp > 0).sum()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Table KPI agrégée
# ─────────────────────────────────────────────────────────────────────────────

def build_kpi_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Construit la table KPI résumée groupée par (Stratégie, Symbole, Type).

    Métriques calculées pour chaque groupe
    ---------------------------------------
    - Nb Passes
    - Survie GHPR>1 (%)     : % de passes avec GHPR > 1.0
    - WFE (%)               : Walk-Forward Efficiency
    - Significatif          : résultat du test t (✅/❌)
    - p-value               : p-value du test t
    - GHPR Moyen
    - AHPR Moyen
    - Forward Return % Moy
    - Sharpe / DD / PF / RF : si présents dans le DataFrame
    """
    optional_cols = {
        "Sharpe Ratio":    "Sharpe Moyen",
        "Equity DD %":     "Max DD Moyen (%)",
        "Profit Factor":   "Profit Factor Moyen",
        "Recovery Factor": "Recovery Factor Moyen",
    }

    group_cols = ["Stratégie", "Symbole", "Type"]
    if "Timeframe" in df.columns:
        group_cols.append("Timeframe")

    rows: list[dict] = []
    for keys, g in df.groupby(group_cols):
        n = len(g)
        if n == 0:
            continue

        # Décomposer les clés selon le nombre de colonnes de groupby
        if len(group_cols) == 4:
            strat, sym, stype, tf = keys
        else:
            strat, sym, stype = keys
            tf = None

        wfe_d  = compute_wfe(g)
        survie = (g["GHPR"] > 1.0).sum() / n * 100

        row: dict = {
            "Stratégie":            strat,
            "Symbole":              sym,
            "Type":                 stype,
            **({"Timeframe": tf} if tf is not None else {}),
            "Nb Passes":            n,
            "Survie GHPR>1 (%)":    round(survie, 1),
            "WFE (%)":              round(wfe_d["wfe"], 1) if not np.isnan(wfe_d["wfe"]) else None,
            "Significatif":         "✅" if wfe_d["significant"] else "❌",
            "p-value":              round(wfe_d["p_value"], 4) if not np.isnan(wfe_d["p_value"]) else None,
            "t-stat":               round(wfe_d["t_stat"], 3)  if not np.isnan(wfe_d["t_stat"])  else None,
            "GHPR Moyen":           round(g["GHPR"].mean(), 5),
            "AHPR Moyen":           round(g["AHPR"].mean(), 5),
            "Forward Return % Moy": round(g["Forward Return %"].mean(), 2),
            "Degrad. Moy (fwd/back)": round(wfe_d["degrad_mean"], 3),
            "Passes Profitables":   wfe_d["nb_passes_positives"],
        }
        for src, dst in optional_cols.items():
            if src in g.columns:
                row[dst] = round(g[src].mean(), 2)

        rows.append(row)

    if not rows:
        return pd.DataFrame()

    return (
        pd.DataFrame(rows)
        .sort_values(["Survie GHPR>1 (%)", "GHPR Moyen"], ascending=[False, False])
        .reset_index(drop=True)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Analyse de sensibilité paramétrique
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def param_sensitivity(
    df: pd.DataFrame,
    param_col: str,
    metric: str = "GHPR",
    bins: int = 10,
) -> pd.DataFrame:
    """
    Pour un paramètre donné, calcule la métrique moyenne par tranche de valeur.

    Permet de visualiser si la stratégie est robuste (courbe plate)
    ou sur-ajustée (pic isolé dans l'espace des paramètres).

    Returns
    -------
    DataFrame avec colonnes : Tranche, Tranche_str, Moyenne, Ecart-type, N
    """
    tmp = df[[param_col, metric]].dropna()
    if tmp.empty or tmp[param_col].nunique() < 2:
        return pd.DataFrame()

    tmp = tmp.copy()
    tmp["bin"] = pd.cut(tmp[param_col], bins=bins)
    agg = (
        tmp.groupby("bin", observed=True)[metric]
        .agg(Moyenne="mean", Ecart_type="std", N="count")
        .reset_index()
        .rename(columns={"bin": "Tranche", "Ecart_type": "Ecart-type"})
    )
    agg["Tranche_str"] = agg["Tranche"].astype(str)
    return agg


@st.cache_data(show_spinner=False)
def param_importance(
    df: pd.DataFrame,
    param_cols: list[str],
    metric: str = "GHPR",
) -> pd.DataFrame:
    """
    Calcule l'importance de chaque paramètre via la corrélation de Spearman
    avec la métrique cible.

    La corrélation de Spearman est non-paramétrique et tolère les
    distributions non-gaussiennes typiques des espaces de paramètres.

    Returns
    -------
    DataFrame trié par importance absolue décroissante :
    Paramètre | Corrélation (Spearman) | p-value | Significatif
    """
    results: list[dict] = []
    for col in param_cols:
        tmp = df[[col, metric]].dropna()
        if tmp.empty or tmp[col].nunique() < 3:
            continue
        rho, p = stats.spearmanr(tmp[col], tmp[metric])
        results.append({
            "Paramètre":              col,
            "Corrélation (Spearman)": round(float(rho), 3),
            "p-value":                round(float(p), 4),
            "Significatif":           "✅" if p < 0.05 else "❌",
        })

    if not results:
        return pd.DataFrame()

    return (
        pd.DataFrame(results)
        .sort_values("Corrélation (Spearman)", key=abs, ascending=False)
        .reset_index(drop=True)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Corrélation croisée type × symbole
# ─────────────────────────────────────────────────────────────────────────────

def cross_analysis_pivot(
    df_kpi: pd.DataFrame,
    metric: str = "GHPR Moyen",
) -> pd.DataFrame:
    """
    Construit le pivot Type × Symbole pour la heatmap d'analyse croisée.

    Returns
    -------
    DataFrame avec Type en index et Symbole en colonnes.
    """
    if metric not in df_kpi.columns:
        return pd.DataFrame()
    return df_kpi.pivot_table(
        index="Type", columns="Symbole", values=metric, aggfunc="mean"
    )
