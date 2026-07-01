"""
TB Quant Dashboard — Page d'accueil et chargement des données.
"""
import json
import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from core.constants import GLOBAL_CSS
from core.loader import build_kpi_table, scan_result_pairs
from core.mt5_runner import OUTPUT_BASE

st.set_page_config(
    page_title="TB Quant Dashboard",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# ── Cache disque ──────────────────────────────────────────────────────────────
_CACHE_DIR    = Path(__file__).parent.parent / "_cache"
_CACHE_KPI    = _CACHE_DIR / "df_kpi_v2.parquet"
_CACHE_PARAMS = _CACHE_DIR / "params_v2.json"


def _cache_valid(capital: float, min_trades: int) -> bool:
    if not (_CACHE_KPI.exists() and _CACHE_PARAMS.exists()):
        return False
    try:
        p = json.loads(_CACHE_PARAMS.read_text(encoding="utf-8"))
        return p.get("capital") == capital and p.get("min_trades") == min_trades
    except Exception:
        return False


def _save_cache(df_kpi: pd.DataFrame, capital: float, min_trades: int) -> str:
    _CACHE_DIR.mkdir(exist_ok=True)
    df_kpi.to_parquet(str(_CACHE_KPI), index=False)
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    _CACHE_PARAMS.write_text(
        json.dumps({"capital": capital, "min_trades": min_trades, "_saved_at": ts},
                   ensure_ascii=False),
        encoding="utf-8",
    )
    return ts


def _load_cache() -> tuple[pd.DataFrame, str]:
    df = pd.read_parquet(str(_CACHE_KPI))
    p  = json.loads(_CACHE_PARAMS.read_text(encoding="utf-8"))
    return df, p.get("_saved_at", "")


def _show_summary(df_kpi: pd.DataFrame) -> None:
    st.divider()
    st.subheader("Résumé du jeu de données")

    n_robots = df_kpi["robot"].nunique()
    n_actifs = df_kpi["actif"].nunique()
    n_tf     = df_kpi["timeframe"].nunique()
    n_plis   = df_kpi["pli"].nunique()

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Stratégies",   n_robots)
    m2.metric("Actifs",       n_actifs)
    m3.metric("Timeframes",   n_tf)
    m4.metric("Plis WF",      n_plis)
    m5.metric("Combinaisons", len(df_kpi))

    if "OOS_Pct_Prof" in df_kpi.columns:
        st.markdown("#### % passes profitables OOS par stratégie × pli")
        pivot = (
            df_kpi.groupby(["robot_label", "pli"])["OOS_Pct_Prof"]
            .mean().round(1).unstack("pli")
            .rename(columns=lambda n: f"Pli {n}")
        )
        col_cfg = {c: st.column_config.NumberColumn(c, format="%.1f %%") for c in pivot.columns}
        st.dataframe(pivot, use_container_width=True, column_config=col_cfg)

    st.info("👈 Naviguez dans le menu à gauche pour analyser les résultats.")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE
# ══════════════════════════════════════════════════════════════════════════════
st.title("🔬 TB Quant Dashboard")
st.markdown(
    "**Analyse comparative des stratégies algorithmiques sur les Matières Premières**  \n"
    "*Travail de Bachelor — HEG Genève 2026*"
)

# ── Dictionnaire des métriques ────────────────────────────────────────────────
with st.expander("📚 Dictionnaire des métriques — Comment lire ce dashboard ?"):
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("""
**WFE (Walk-Forward Efficiency)**
Ratio `Σ Profit OOS / Σ Profit IS × 100`.
- ≥ 80 % → stratégie robuste
- 50–80 % → dégradation modérée, acceptable
- < 50 % → probable sur-optimisation

**% Passes Profitables OOS**
Part des paramétrisations testées qui dégagent un profit positif hors-échantillon.
Un bon système reste profitable sur une large plage de paramètres.

**Rdt Médian OOS %**
Rendement médian (sur capital) de toutes les passes OOS.
La médiane est robuste aux valeurs extrêmes du balayage paramétrique.
        """)
    with col_b:
        st.markdown("""
**Exposant de Hurst (H)**
Mesure la persistance de la série de prix.
- `H > 0.55` → tendanciel → favorable au Trend-Following
- `H ≈ 0.50` → marche aléatoire
- `H < 0.45` → mean-revertant → favorable à la Mean-Reversion

**ADX (Average Directional Index)**
Force de la tendance courante.
- `ADX < 25` → Range  |  `ADX 25–40` → Tendance  |  `ADX > 40` → Forte tendance

**Plis Walk-Forward (IS / OOS)**
3 plis glissants couvrant 2015–2025 avec ~2 ans d'OOS chacun.
IS = In-Sample (optimisation). OOS = Out-of-Sample (validation).
        """)

st.divider()

# ── Session state ─────────────────────────────────────────────────────────────
for key in ["df_kpi", "df_master", "market_cache"]:
    if key not in st.session_state:
        st.session_state[key] = None

# ── Paramètres ────────────────────────────────────────────────────────────────
st.subheader("⚙️ Paramètres de chargement")
col_cap, col_min = st.columns(2)
with col_cap:
    capital = float(st.number_input(
        "💰 Capital initial ($)",
        value=100_000.0, min_value=1_000.0, step=10_000.0, format="%.0f",
        help="Dépôt MT5 utilisé lors des optimisations (100 000 $ par défaut).",
    ))
with col_min:
    min_trades = int(st.number_input(
        "🔢 Trades minimum par passe",
        value=30, min_value=1, step=5,
        help="Les passes avec moins de trades sont exclues.",
    ))

st.divider()

# ── Rechargement automatique depuis le cache ──────────────────────────────────
_cache_saved_at: str = ""
if st.session_state["df_kpi"] is None and _cache_valid(capital, min_trades):
    try:
        _dk, _saved_at = _load_cache()
        st.session_state["df_kpi"]       = _dk
        st.session_state["df_master"]    = _dk
        st.session_state["market_cache"] = {}
        _cache_saved_at = _saved_at
    except Exception:
        pass

# ── Scan préliminaire ─────────────────────────────────────────────────────────
st.subheader("📁 Fichiers Walk-Forward détectés")
pairs = scan_result_pairs(OUTPUT_BASE)
n_oos = sum(1 for _, oos, _ in pairs if oos is not None)

if pairs:
    st.info(
        f"📂 **{len(pairs)}** fichier(s) IS détecté(s) dans `Résultats_FT/`"
        + (f" — **{n_oos}** avec OOS associé." if n_oos < len(pairs) else ".")
    )
else:
    st.warning(
        f"Aucun fichier XML dans `{OUTPUT_BASE}`.  \n"
        "Lancez d'abord les optimisations depuis **⚙️ Lancer MT5** (menu à gauche)."
    )

# ── Boutons ───────────────────────────────────────────────────────────────────
col_launch, col_clear = st.columns([4, 1])
with col_launch:
    btn_label = "🔄 Recharger" if _cache_saved_at else "🚀 Charger les Résultats"
    launch = st.button(btn_label, type="primary", use_container_width=True,
                       disabled=len(pairs) == 0)
with col_clear:
    if _CACHE_KPI.exists():
        if st.button("🗑️ Effacer cache", use_container_width=True):
            import shutil
            shutil.rmtree(str(_CACHE_DIR), ignore_errors=True)
            st.session_state["df_kpi"]    = None
            st.session_state["df_master"] = None
            st.rerun()

# ── Si pas de bouton cliqué ───────────────────────────────────────────────────
if not launch:
    if st.session_state["df_kpi"] is not None:
        src = (f"cache disque ({_cache_saved_at.replace('T', ' ')})"
               if _cache_saved_at else "session en cours")
        st.success(f"✅ {len(st.session_state['df_kpi'])} combinaisons chargées depuis {src}.")
        _show_summary(st.session_state["df_kpi"])
    st.stop()

# ── Chargement (bouton cliqué) ────────────────────────────────────────────────
with st.spinner("Lecture des fichiers XML et calcul des KPI…"):
    df_kpi, warns = build_kpi_table(
        output_base=OUTPUT_BASE,
        min_trades=min_trades,
        capital=capital,
    )

for w in warns:
    st.warning(w)

if df_kpi.empty:
    st.error(
        "❌ Aucun résultat valide.  \n"
        "Vérifiez la structure : `Résultats_FT/<EA>/<Symbole>/<TF>/fold<N>/*_IS.xml`"
    )
    st.stop()

st.session_state["df_kpi"]       = df_kpi
st.session_state["df_master"]    = df_kpi
st.session_state["market_cache"] = {}

try:
    _save_cache(df_kpi, capital, min_trades)
except Exception as e:
    st.warning(f"⚠️ Cache non sauvegardé : {e}")

st.success(f"✅ **{len(df_kpi)}** combinaisons chargées.")
_show_summary(df_kpi)
