"""
Constantes globales : taxonomie des stratégies, symboles, couleurs, groupes d'actifs.
"""
from __future__ import annotations

# ── Ticker Yahoo Finance par symbole MT5 ──────────────────────────────────────
SYMBOL_TO_TICKER: dict[str, str] = {
    # Métaux précieux
    "XAUUSD":   "GC=F",
    "XAGUSD":   "SI=F",
    "XPTUSD":   "PL=F",
    "XPDUSD":   "PA=F",
    "GOLD":     "GC=F",
    "PLATINUM": "PL=F",
    # Énergie
    "USOIL":      "CL=F",
    "UKOIL":      "BZ=F",
    "NATGAS":     "NG=F",
    "BRENT":      "BZ=F",
    "NATURALGAS": "NG=F",
    # Métaux industriels
    "COPPER": "HG=F",
    # Agricole
    "WHEAT":   "ZW=F",
    "CORN":    "ZC=F",
    "SOYBEAN": "ZS=F",
    "COFFEE":  "KC=F",
    "COCOA":   "CC=F",
    # Crypto
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
    "BNBUSD": "BNB-USD",
    # Forex majeurs
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "USDCHF": "USDCHF=X",
    "AUDUSD": "AUDUSD=X",
    "NZDUSD": "NZDUSD=X",
    "USDCAD": "USDCAD=X",
    "EURGBP": "EURGBP=X",
    "EURJPY": "EURJPY=X",
    "GBPJPY": "GBPJPY=X",
    # Indices
    "US30":   "^DJI",
    "US100":  "^NDX",
    "US500":  "^GSPC",
    "GER40":  "^GDAXI",
    "UK100":  "^FTSE",
    "JPN225": "^N225",
    "AUS200": "^AXJO",
}

# ── Groupes d'actifs ──────────────────────────────────────────────────────────
COMMODITY_GROUP: dict[str, list[str]] = {
    "Métaux Précieux":    ["XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD"],
    "Énergie":            ["USOIL", "UKOIL", "NATGAS"],
    "Métaux Industriels": ["COPPER"],
    "Agricole":           ["WHEAT", "CORN", "SOYBEAN"],
    "Crypto":             ["BTCUSD", "ETHUSD", "BNBUSD"],
    "Forex":              ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD",
                           "NZDUSD", "USDCAD", "EURGBP", "EURJPY", "GBPJPY"],
    "Indices":            ["US30", "US100", "US500", "GER40", "UK100", "JPN225"],
}


def get_commodity_group(symbol: str) -> str:
    """Retourne le groupe d'appartenance d'un symbole."""
    for group, symbols in COMMODITY_GROUP.items():
        if symbol.upper() in symbols:
            return group
    return "Autre"


# ── Types de stratégies ───────────────────────────────────────────────────────
STRATEGY_TYPES: list[str] = [
    "Trend-Following",
    "Mean-Reversion",
    "Breakout",
    "Scalping",
    "Grid / Martingale",
    "Pattern Recognition",
    "Multi-Timeframe",
    "Autre",
]

# Mots-clés pour la détection automatique du type depuis le nom de fichier
TYPE_KEYWORDS: dict[str, list[str]] = {
    "Trend-Following":    ["ema", "sma", "ma_", "_ma_", "trend", "adx", "macd",
                           "ichimoku", "ichi", "atr", "channel", "parabolic", "reb_c",
                           "moyennesmobiles", "moyenne"],
    "Mean-Reversion":     ["rsi", "cci", "stoch", "mean", "revert", "bb",
                           "bollinger", "oscil", "keltner", "rsi_", "_rsi",
                           "_mr_", "meanreversion"],
    "Breakout":           ["break", "donchian", "pivot", "support", "resist",
                           "high", "low", "range", "_bk_", "breakout"],
    "Scalping":           ["scalp", "m1", "m5", "tick", "spread", "sniper"],
    "Grid / Martingale":  ["grid", "martin", "hedge", "step", "layer"],
    "Pattern Recognition":["pattern", "candle", "pin", "engulf", "hammer"],
    "Multi-Timeframe":    ["mtf", "multi", "htf"],
}

# ── Couleurs par type ─────────────────────────────────────────────────────────
TYPE_COLOR: dict[str, str] = {
    "Trend-Following":    "#0BB4FF",
    "Mean-Reversion":     "#FF6B6B",
    "Breakout":           "#00E676",
    "Scalping":           "#FFD54F",
    "Grid / Martingale":  "#E040FB",
    "Pattern Recognition":"#FF6D00",
    "Multi-Timeframe":    "#00BCD4",
    "Autre":              "#9AA3B0",
}

# ── Couleurs de régime de marché ──────────────────────────────────────────────
REGIME_COLOR: dict[str, str] = {
    "Forte Tendance": "#00E676",
    "Tendance":       "#0BB4FF",
    "Range":          "#FFD54F",
}

# ── Palette générale ─────────────────────────────────────────────────────────
PALETTE = ["#0BB4FF", "#00E676", "#FF5252", "#FFD54F",
           "#E040FB", "#FF6D00", "#00BCD4", "#76FF03"]

# ── Thème UI ─────────────────────────────────────────────────────────────────
THEME = {
    "bg":      "#0E1117",
    "card":    "#1E2130",
    "accent":  "#0BB4FF",
    "success": "#00E676",
    "danger":  "#FF5252",
    "warning": "#FFD54F",
    "text":    "#FAFAFA",
    "subtext": "#9AA3B0",
}

# ── CSS global injecté dans toutes les pages ─────────────────────────────────
GLOBAL_CSS = """
<style>
    [data-testid="stAppViewContainer"] { background: #0E1117; }
    [data-testid="stSidebar"]          { background: #1E2130; }
    h1  { color: #0BB4FF !important; }
    h2, h3 { color: #FAFAFA !important; }
    .metric-card {
        background: #1E2130; border-radius: 10px;
        padding: 16px 20px; border-left: 4px solid #0BB4FF;
        margin-bottom: 10px;
    }
    .stButton > button {
        background: #0BB4FF; color: #0E1117;
        font-weight: bold; border: none; border-radius: 6px;
    }
    .stButton > button:hover { background: #00E676; color: #0E1117; }
    div[data-testid="metric-container"] {
        background: #1E2130; border-radius: 8px;
        padding: 12px 16px; border: 1px solid #2A2F3E;
    }
</style>
"""

# ── Paramètres Plotly layout réutilisables ───────────────────────────────────
PLOTLY_DARK = dict(
    template      = "plotly_dark",
    paper_bgcolor = "rgba(0,0,0,0)",
    plot_bgcolor  = "rgba(14,17,23,0.6)",
    margin        = dict(l=40, r=40, t=60, b=40),
    font          = dict(family="Inter, Segoe UI, sans-serif", color=THEME["text"]),
    hoverlabel    = dict(bgcolor="#1E2130", font_size=13, bordercolor="#0BB4FF"),
)
