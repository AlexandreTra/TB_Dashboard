"""
Données de marché — CSV locaux (TB-Python/) avec fallback Yahoo Finance.

Priorité : CSV locaux (mêmes prix qu'MT5, hors-ligne, historique complet depuis 2009)
Fallback  : Yahoo Finance si le symbole n'a pas de CSV local.

Indicateurs calculés :
- ADX (Average Directional Index) — force de la tendance
- ATR normalisé — volatilité
- Exposant de Hurst — persistance du mouvement
- Classification du régime : Forte Tendance / Tendance / Range
"""
from __future__ import annotations

import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from core.constants import SYMBOL_TO_TICKER

# ── Chemins des données locales ───────────────────────────────────────────────
_HERE     = Path(__file__).parent.parent          # TB_Dashboard/
_TB_ROOT  = _HERE.parent                          # Travail de bachelor/
_CSV_DIR  = _TB_ROOT / "TB-Python"               # TB-Python/

# Symbole MT5 → code CSV (préfixe des fichiers GC_D1.csv, XBZ_D1.csv, etc.)
_SYMBOL_TO_CODE: dict[str, str] = {
    "GOLD":       "GC",
    "BRENT":      "XBZ",
    "COCOA":      "CC",
    "COFFEE":     "KC",
    "NATURALGAS": "NG",
    "PLATINUM":   "PL",
    # Alias possibles
    "XAUUSD":     "GC",
    "UKOIL":      "XBZ",
    "NATGAS":     "NG",
    "XPTUSD":     "PL",
}

# Timeframe MT5 → suffixe fichier CSV
_TF_TO_SUFFIX: dict[str, str] = {
    "Daily": "D1",
    "D1":    "D1",
    "H4":    "D1",   # pas de H4 dispo → on utilise D1 (régime = concept LF)
    "H1":    "H1",
    "M15":   "M15",
}


# ─────────────────────────────────────────────────────────────────────────────
# Indicateurs techniques
# ─────────────────────────────────────────────────────────────────────────────

def _ema(series: pd.Series, span: int) -> pd.Series:
    """EMA (Wilder smoothing, adjust=False)."""
    return series.ewm(span=span, min_periods=span, adjust=False).mean()


def compute_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calcule l'ADX (Average Directional Index) sur données OHLC.

    Algorithme de Wilder :
    1. True Range (TR)
    2. Positive / Negative Directional Movement (+DM, -DM)
    3. Lissage exponentiel → +DI, -DI
    4. DX = |+DI - -DI| / (+DI + -DI) × 100
    5. ADX = EMA(DX)
    """
    h = df["High"].astype(float)
    l = df["Low"].astype(float)
    c = df["Close"].astype(float)

    tr = pd.concat(
        [h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1
    ).max(axis=1)

    up   = h - h.shift(1)
    down = l.shift(1) - l
    pdm  = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    mdm  = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)

    atr = _ema(tr, period)
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi = 100 * _ema(pdm, period) / atr.replace(0, np.nan)
        mdi = 100 * _ema(mdm, period) / atr.replace(0, np.nan)
        dx  = ((pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)) * 100

    return _ema(dx, period)


def compute_hurst(series: pd.Series, max_lag: int = 30) -> float:
    """
    Calcule l'exposant de Hurst par la méthode des R/S (Range Scaled).

    H > 0.55  → Tendanciel   : favorable au Trend-Following
    H ≈ 0.50  → Marche aléatoire
    H < 0.45  → Mean-revertant : favorable à la Mean-Reversion
    """
    s = series.dropna().values.astype(float)
    n = len(s)
    if n < max_lag * 2:
        return 0.5

    lags = range(2, min(max_lag, n // 2))
    tau  = [np.std(s[lag:] - s[:-lag]) for lag in lags]

    valid = [(lag, t) for lag, t in zip(lags, tau) if t > 0]
    if len(valid) < 4:
        return 0.5

    xs, ys = zip(*valid)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        coef = np.polyfit(np.log(xs), np.log(ys), 1)
    return float(np.clip(coef[0], 0.0, 1.0))


def _classify_regime(adx: float) -> str:
    if adx >= 40:
        return "Forte Tendance"
    if adx >= 25:
        return "Tendance"
    return "Range"


# ─────────────────────────────────────────────────────────────────────────────
# Chargement CSV local
# ─────────────────────────────────────────────────────────────────────────────

def _load_local_ohlc(symbol: str, timeframe: str = "Daily") -> pd.DataFrame:
    """
    Charge les données OHLC depuis un CSV local TB-Python/.

    Format attendu (colonnes par position) :
        Date | Open | High | Low | Close | Volume
    Date format : MM/DD/YY  (ex: 01/23/26)

    Returns
    -------
    DataFrame avec index DatetimeIndex et colonnes Open/High/Low/Close,
    trié chronologiquement. DataFrame vide si le fichier est introuvable.
    """
    code = _SYMBOL_TO_CODE.get(symbol.upper())
    if code is None:
        return pd.DataFrame()

    suffix   = _TF_TO_SUFFIX.get(timeframe, "D1")
    csv_path = _CSV_DIR / f"{code}_{suffix}.csv"

    if not csv_path.exists():
        return pd.DataFrame()

    try:
        # Lire en ignorant les noms de colonnes (ils changent selon le code)
        raw = pd.read_csv(
            csv_path,
            header=0,
            usecols=[0, 1, 2, 3, 4],        # Date, Open, High, Low, Close
            names=["Date", "Open", "High", "Low", "Close"],
            skiprows=1,                       # sauter la ligne d'en-tête
            dtype=str,
        )

        raw["Date"]  = pd.to_datetime(raw["Date"], format="%m/%d/%y", errors="coerce")
        raw = raw.dropna(subset=["Date"])
        for col in ("Open", "High", "Low", "Close"):
            raw[col] = pd.to_numeric(raw[col], errors="coerce")
        raw = raw.dropna(subset=["Open", "Close"])
        raw = raw.set_index("Date").sort_index()
        return raw

    except Exception:
        return pd.DataFrame()


def available_local_symbols() -> list[str]:
    """Retourne les symboles pour lesquels un CSV D1 local est disponible."""
    return [
        sym for sym, code in _SYMBOL_TO_CODE.items()
        if (_CSV_DIR / f"{code}_D1.csv").exists()
        and sym == sym.upper()  # éliminer les alias
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Enrichissement (commun CSV local et Yahoo Finance)
# ─────────────────────────────────────────────────────────────────────────────

def _enrich_daily(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Calcule ADX, ATR, rendements journaliers et agrège en mensuel.
    Entrée  : DataFrame OHLC journalier avec index DatetimeIndex.
    Sortie  : DataFrame mensuel avec tous les indicateurs de régime.
    """
    raw = raw.copy()
    raw["Return"] = raw["Close"].pct_change()
    raw["ADX"]    = compute_adx(raw)
    raw["ATR"]    = (raw["High"] - raw["Low"]) / raw["Close"].replace(0, np.nan) * 100

    monthly: pd.DataFrame = raw.resample("MS").agg(
        Open       =("Open",   "first"),
        High       =("High",   "max"),
        Low        =("Low",    "min"),
        Close      =("Close",  "last"),
        ADX        =("ADX",    "mean"),
        ATR_pct    =("ATR",    "mean"),
        Volatility =("Return", "std"),
    ).dropna(subset=["Open"])

    monthly["Direction_pct"]  = (monthly["Close"] - monthly["Open"]) / monthly["Open"] * 100
    monthly["Amplitude_pct"]  = (monthly["High"]  - monthly["Low"])  / monthly["Open"] * 100
    monthly["Volatility_pct"] = monthly["Volatility"] * np.sqrt(21) * 100
    monthly.drop(columns=["Volatility"], inplace=True)

    monthly["Regime"]     = monthly["ADX"].apply(_classify_regime)
    monthly["Trend_Bias"] = monthly["Direction_pct"].apply(
        lambda x: "Haussier" if x > 0 else "Baissier"
    )

    # Hurst glissant sur 90 jours
    closes = raw["Close"].dropna()
    hurst_vals: dict[pd.Timestamp, float] = {}
    for month_ts in monthly.index:
        window = closes.loc[month_ts - pd.Timedelta(days=90): month_ts]
        hurst_vals[month_ts] = compute_hurst(window, max_lag=20)
    monthly["Hurst"] = pd.Series(hurst_vals)

    return monthly


# ─────────────────────────────────────────────────────────────────────────────
# Fonction principale
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_and_enrich(symbol: str, start: str, end: str) -> pd.DataFrame:
    """
    Charge les données OHLC (CSV local en priorité, Yahoo Finance en fallback)
    et calcule tous les indicateurs de régime de marché.

    Produit un DataFrame **mensuel** avec :
    - Open, High, Low, Close
    - ADX              : force de la tendance (14 périodes)
    - ATR_pct          : ATR normalisé (%)
    - Volatility_pct   : volatilité mensuelle annualisée (%)
    - Direction_pct    : variation Open→Close du mois (%)
    - Amplitude_pct    : High-Low normalisé (%)
    - Hurst            : exposant de Hurst (fenêtre 90 j glissante)
    - Regime           : Forte Tendance / Tendance / Range
    - Trend_Bias       : Haussier / Baissier

    Parameters
    ----------
    symbol : str — symbole MT5 (ex: "GOLD", "BRENT")
    start  : str — date début "YYYY-MM-DD"
    end    : str — date fin   "YYYY-MM-DD"
    """
    # ── 1. Essai CSV local ───────────────────────────────────────────────────
    raw = _load_local_ohlc(symbol, timeframe="Daily")

    if not raw.empty:
        # Filtrer sur la plage demandée (avec buffer de 90j pour le warmup Hurst)
        t_start = pd.to_datetime(start) - pd.Timedelta(days=90)
        t_end   = pd.to_datetime(end)
        raw = raw.loc[t_start:t_end]

        if not raw.empty:
            monthly = _enrich_daily(raw)
            # Restreindre à la plage demandée (après warmup)
            monthly = monthly.loc[pd.to_datetime(start):]
            return monthly

    # ── 2. Fallback Yahoo Finance ────────────────────────────────────────────
    try:
        import yfinance as yf
    except ImportError:
        st.error("yfinance non installé. Exécutez : pip install yfinance")
        return pd.DataFrame()

    ticker = SYMBOL_TO_TICKER.get(symbol.upper(), symbol)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            raw_yf = yf.download(
                ticker, start=start, end=end,
                interval="1d", progress=False, auto_adjust=True,
            )
    except Exception as exc:
        st.warning(f"Impossible de télécharger {ticker} ({symbol}) : {exc}")
        return pd.DataFrame()

    if raw_yf.empty:
        st.warning(f"Aucune donnée pour {ticker} ({symbol}).")
        return pd.DataFrame()

    if isinstance(raw_yf.columns, pd.MultiIndex):
        raw_yf.columns = raw_yf.columns.get_level_values(0)

    raw_yf.index = pd.to_datetime(raw_yf.index)
    raw_yf = raw_yf[["Open", "High", "Low", "Close"]].dropna()

    return _enrich_daily(raw_yf)


# ─────────────────────────────────────────────────────────────────────────────
# Utilitaires d'analyse de régime
# ─────────────────────────────────────────────────────────────────────────────

def regime_stats(df_market: pd.DataFrame) -> pd.DataFrame:
    """Statistiques descriptives du régime de marché sur la période complète."""
    if df_market.empty or "Regime" not in df_market.columns:
        return pd.DataFrame()

    total = len(df_market)
    rows = []
    for regime, grp in df_market.groupby("Regime"):
        rows.append({
            "Régime":           regime,
            "Nb mois":          len(grp),
            "% du temps":       round(len(grp) / total * 100, 1),
            "ADX moyen":        round(grp["ADX"].mean(), 1),
            "Direction% moyen": round(grp["Direction_pct"].mean(), 2),
            "Volatilité% moy":  round(grp["Volatility_pct"].mean(), 2),
        })
    return pd.DataFrame(rows).sort_values("Nb mois", ascending=False)


def hurst_interpretation(h: float) -> tuple[str, str]:
    """Retourne (label, couleur) pour un exposant de Hurst donné."""
    if h > 0.55:
        return "Tendanciel (H>{:.2f})".format(h), "#00E676"
    if h < 0.45:
        return "Mean-revertant (H<{:.2f})".format(h), "#FF5252"
    return "Aléatoire (H≈{:.2f})".format(h), "#FFD54F"
