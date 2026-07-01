"""
TB Quant Dashboard — Lancement MT5
Deux modes partageant les mêmes sélecteurs EA / Symbole / TF / Pli :
  • Optimisations Walk-Forward   → run_batch (grille exhaustive, IS + OOS)
  • Backtests Individuels        → run_representative_passes (1 passe × 3 niveaux)
"""
from __future__ import annotations

import threading
import time

import pandas as pd
import streamlit as st

from core.constants import GLOBAL_CSS
from core.mt5_runner import (
    EA_CONFIG,
    FOLDS,
    SYMBOLS,
    SYMBOLS_HISTORY_WARNING,
    TIMEFRAMES,
    check_environment,
    is_mt5_running,
    job_label,
    job_output_paths,
    run_batch,
)
from core.single_run import (
    OUTPUT_DETAIL,
    detail_htm_path,
    detail_status,
    get_manual_import_instructions,
    run_representative_passes,
)

# ── Config page ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MT5 Lancer — TB Quant",
    page_icon="⚙️",
    layout="wide",
)
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
if "batch" not in st.session_state:
    st.session_state["batch"] = {"running": False, "results": [], "jobs": []}
if "singles_batch" not in st.session_state:
    st.session_state["singles_batch"] = {"running": False, "results": [], "combos": []}

batch   = st.session_state["batch"]
singles = st.session_state["singles_batch"]


# ── Workers ───────────────────────────────────────────────────────────────────

def _wf_worker(state: dict, jobs: list[dict], params: dict) -> None:
    try:
        for update in run_batch(jobs=jobs, deposit=params["deposit"],
                                skip_existing=params["skip_existing"]):
            idx = update["index"]
            while len(state["results"]) <= idx:
                state["results"].append({})
            state["results"][idx] = update
    finally:
        state["running"] = False


def _singles_worker(state: dict, combos: list[dict]) -> None:
    try:
        for update in run_representative_passes(
            combos, output_detail=OUTPUT_DETAIL,
            deposit=100_000.0, min_trades_oos=30, skip_existing=True,
        ):
            idx = update["index"]
            while len(state["results"]) <= idx:
                state["results"].append({})
            state["results"][idx] = update
    finally:
        state["running"] = False


# ── Header ────────────────────────────────────────────────────────────────────
st.title("⚙️ Lancer MT5")
st.markdown(
    "Configure les combinaisons, puis choisit le mode de lancement dans les onglets ci-dessous.  \n"
    "> **MT5 doit être fermé** avant de lancer — il s'ouvre et se ferme automatiquement."
)
st.divider()

# ── Vérification environnement ────────────────────────────────────────────────
env_errors = check_environment()
if env_errors:
    st.error("**Problèmes de configuration détectés :**")
    for e in env_errors:
        st.markdown(f"- {e}")
    st.stop()
else:
    st.success("✅ Environnement MT5 détecté correctement.")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# SÉLECTEURS PARTAGÉS
# ══════════════════════════════════════════════════════════════════════════════
st.subheader("Sélection des combinaisons")
col_ea, col_sym, col_tf, col_fold = st.columns(4)

with col_ea:
    st.markdown("**🤖 Expert Advisors**")
    sel_eas: list[str] = []
    for short, cfg in EA_CONFIG.items():
        if st.checkbox(f"{short} — {cfg['label']}", value=True, key=f"ea_{short}"):
            sel_eas.append(short)

with col_sym:
    st.markdown("**📊 Symboles**")
    sel_syms: list[str] = []
    for mt5_sym, clean in SYMBOLS.items():
        if st.checkbox(clean, value=True, key=f"sym_{mt5_sym}"):
            sel_syms.append(mt5_sym)

with col_tf:
    st.markdown("**⏱ Timeframes**")
    sel_tfs: list[str] = []
    for tf in TIMEFRAMES:
        if st.checkbox(tf, value=True, key=f"tf_{tf}"):
            sel_tfs.append(tf)

with col_fold:
    st.markdown("**📅 Plis Walk-Forward**")
    sel_folds: list[dict] = []
    for fold in FOLDS:
        n        = fold["n"]
        f_from   = fold["from_date"][:4]
        f_fwd    = fold["forward_date"][:4]
        f_to     = fold["to_date"][:4]
        f_is_end = str(int(f_fwd) - 1)
        fold_desc = f"Pli {n} — IS {f_from}–{f_is_end} / OOS {f_fwd}–{f_to}"
        if st.checkbox(fold_desc, value=True, key=f"fold_{n}"):
            sel_folds.append(fold)

# ── Avertissements ────────────────────────────────────────────────────────────
if any(f["n"] <= 2 for f in sel_folds):
    warned = [s for s in sel_syms if s in SYMBOLS_HISTORY_WARNING]
    if warned:
        st.warning(
            f"⚠️ **Historique potentiellement insuffisant** pour "
            f"{', '.join(SYMBOLS[s] for s in warned)} "
            "sur les plis 1 et 2 (IC Markets peut ne pas remonter à 2015)."
        )

# ── Capital ───────────────────────────────────────────────────────────────────
deposit = float(st.number_input(
    "💰 Capital de départ ($)",
    value=100_000, min_value=1_000, step=10_000,
    help="Deposit initial en USD. Levier 1:1 dans tous les runs.",
))

st.divider()

# ── Matrices de combinaisons ──────────────────────────────────────────────────
wf_jobs = [
    {"ea": ea, "symbol": sym, "tf": tf, "fold": fold}
    for ea   in sel_eas
    for sym  in sel_syms
    for tf   in sel_tfs
    for fold in sel_folds
]

# Pour les backtests individuels : pli.n au lieu de dict fold
single_combos = [
    {"robot": ea, "actif_tb": sym, "tf": tf, "pli": fold["n"]}
    for ea   in sel_eas
    for sym  in sel_syms
    for tf   in sel_tfs
    for fold in sel_folds
]

# ── Métriques globales ────────────────────────────────────────────────────────
if not sel_eas or not sel_syms or not sel_tfs or not sel_folds:
    st.warning("⚠️ Sélectionnez au moins un EA, un symbole, un TF et un pli.")
    st.stop()

def _wf_done(j: dict) -> bool:
    is_dest, _ = job_output_paths(j["ea"], j["symbol"], j["tf"], j["fold"]["n"])
    return is_dest.exists() and is_dest.stat().st_size > 5_000

_status_singles = detail_status(single_combos, OUTPUT_DETAIL)
_n_wf           = len(wf_jobs)
_n_wf_done      = sum(1 for j in wf_jobs if _wf_done(j))
_n_singles      = len(_status_singles)                                   # combos × 3
_n_singles_done = sum(1 for v in _status_singles.values() if v == "done")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Combinaisons WF",         _n_wf,
          help="1 run WF = IS + OOS sur toute la grille de paramètres")
c2.metric("IS WF déjà générés",      _n_wf_done)
c3.metric("Runs individuels (3/combo)", _n_singles,
          help="Meilleure + Médiane + Pire passe OOS par combinaison")
c4.metric("Individuels générés",     _n_singles_done)

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# ONGLETS DE LANCEMENT
# ══════════════════════════════════════════════════════════════════════════════
tab_wf, tab_singles = st.tabs([
    "🔄 Optimisations Walk-Forward",
    "📋 Backtests Individuels",
])


# ─────────────────────────────────────────────────────────────────────────────
# ONGLET 1 — OPTIMISATIONS WALK-FORWARD
# ─────────────────────────────────────────────────────────────────────────────
with tab_wf:
    st.markdown(
        "**Mode :** optimisation exhaustive IS puis forward OOS sur la grille de paramètres.  \n"
        f"**{_n_wf}** combinaisons sélectionnées · **{_n_wf_done}** IS déjà présents."
    )

    with st.expander(f"📋 Liste des {_n_wf} combinaisons", expanded=(_n_wf <= 18)):
        for j in wf_jobs:
            lbl = job_label(j["ea"], j["symbol"], j["tf"], j["fold"]["n"])
            is_dest, fwd_dest = job_output_paths(j["ea"], j["symbol"], j["tf"], j["fold"]["n"])
            is_ok  = is_dest.exists()  and is_dest.stat().st_size  > 5_000
            fwd_ok = fwd_dest.exists() and fwd_dest.stat().st_size > 1_000
            icon = "✅" if (is_ok and fwd_ok) else ("🔶" if is_ok else "🔲")
            st.markdown(f"{icon} `{lbl}`")

    skip_wf = st.checkbox(
        f"Passer les {_n_wf_done} job(s) dont l'IS existe déjà",
        value=True, key="skip_wf",
    )
    n_wf_to_run = (_n_wf - _n_wf_done) if skip_wf else _n_wf

    if batch["running"]:
        st.warning("⏳ Optimisation en cours — MT5 tourne en arrière-plan.")
        if st.button("⛔ Arrêter après le run en cours", type="secondary", key="stop_wf"):
            batch["running"] = False
    else:
        mt5_open = is_mt5_running()
        if mt5_open:
            st.warning("⚠️ **MT5 est ouvert.** Fermez-le avant de lancer.")
        if st.button(
            f"🚀 Lancer {n_wf_to_run} optimisation(s) WF",
            type="primary", use_container_width=True,
            disabled=(_n_wf == 0 or mt5_open),
            key="launch_wf",
        ):
            batch["running"] = True
            batch["results"] = []
            batch["jobs"]    = list(wf_jobs)
            threading.Thread(
                target=_wf_worker,
                args=(batch, list(wf_jobs),
                      {"deposit": deposit, "skip_existing": skip_wf}),
                daemon=True,
            ).start()
            st.rerun()

    # Progression WF
    if batch["results"] or batch["running"]:
        st.divider()
        _done_wf  = sum(1 for r in batch["results"] if r.get("status") == "done")
        _skip_wf_ = sum(1 for r in batch["results"] if r.get("status") == "skipped")
        _err_wf   = sum(1 for r in batch["results"] if r.get("status") == "error")
        _tot_wf   = len(batch["jobs"])
        if _tot_wf:
            st.progress(
                (_done_wf + _skip_wf_ + _err_wf) / _tot_wf,
                text=f"{_done_wf + _skip_wf_ + _err_wf}/{_tot_wf} — "
                     f"{_done_wf} OK · {_skip_wf_} passés · {_err_wf} erreur(s)",
            )
        for i, job in enumerate(batch["jobs"]):
            lbl = job_label(job["ea"], job["symbol"], job["tf"], job["fold"]["n"])
            if i < len(batch["results"]):
                r = batch["results"][i]
                s = r.get("status")
                if s == "done":
                    st.success(f"✅ `{lbl}` — IS {'✓' if r.get('is_ok') else '✗'} · OOS {'✓' if r.get('fwd_ok') else '✗'}")
                elif s == "skipped":
                    st.markdown(f"<span style='color:#9AA3B0'>⏭ `{lbl}`</span>",
                                unsafe_allow_html=True)
                elif s == "error":
                    st.error(f"❌ `{lbl}`" + (f" — {r.get('detail','')}" if r.get("detail") else ""))
                elif s == "running":
                    st.info(f"⏳ `{lbl}` — en cours…")
            elif batch["running"]:
                st.markdown(f"<span style='color:#FAFAFA'>⏸ `{lbl}`</span>",
                            unsafe_allow_html=True)
        if batch["running"]:
            time.sleep(3)
            st.rerun()
        elif batch["results"] and _err_wf == 0:
            st.balloons()
            st.success(
                f"🎉 Terminé ! {_done_wf} généré(s), {_skip_wf_} passé(s).  \n"
                "👈 Allez sur **Accueil** pour recharger les résultats."
            )
        elif _err_wf > 0:
            st.warning(f"{_done_wf} OK · {_skip_wf_} passés · {_err_wf} erreur(s).")


# ─────────────────────────────────────────────────────────────────────────────
# ONGLET 2 — BACKTESTS INDIVIDUELS
# ─────────────────────────────────────────────────────────────────────────────
with tab_singles:
    st.markdown(
        "**Mode :** backtest unique (`Optimization=0`) pour les **3 passes représentatives** "
        "de chaque combinaison — meilleure, médiane et pire passe OOS (par score OnTester).  \n"
        "Produit un rapport `.htm` avec les trades un par un, analysable dans **📋 Journaux de Trades**."
    )

    # ── Grille de statut ──────────────────────────────────────────────────────
    _ASSET_LABELS = {
        "BRENT":      "Brent",
        "NATURALGAS": "Gaz Naturel",
        "GOLD":       "Or",
        "PLATINUM":   "Platine",
        "COFFEE":     "Café",
        "COCOA":      "Cacao",
    }
    _ROBOT_LABELS = {k: v["label"] for k, v in EA_CONFIG.items()}

    status_rows = []
    for ea in sel_eas:
        for sym in sel_syms:
            actif_clean = sym.replace(".TB", "")
            done_c = sum(
                1 for tf in sel_tfs
                for fold in sel_folds
                for lbl in ("best", "median", "worst")
                if _status_singles.get(f"{ea}/{actif_clean}/{tf}/fold{fold['n']}/{lbl}") == "done"
            )
            total_c = len(sel_tfs) * len(sel_folds) * 3
            if done_c == total_c:
                icon = "✅"
            elif done_c == 0:
                icon = "🔲"
            else:
                icon = f"🔄 {done_c}/{total_c}"
            status_rows.append({
                "Robot":  _ROBOT_LABELS.get(ea, ea),
                "Actif":  _ASSET_LABELS.get(actif_clean, actif_clean),
                "État":   icon,
            })

    with st.expander(
        f"📋 Grille de statut — {_n_singles} runs "
        f"({len(sel_eas)}×{len(sel_syms)}×{len(sel_tfs)}×{len(sel_folds)} combos × 3 passes)",
        expanded=True,
    ):
        if status_rows:
            df_st = pd.DataFrame(status_rows)
            try:
                df_pivot = df_st.pivot(index="Robot", columns="Actif", values="État")
                st.dataframe(df_pivot, use_container_width=True)
            except Exception:
                st.dataframe(df_st, use_container_width=True, hide_index=True)

    _n_to_gen = _n_singles - _n_singles_done
    _t_min    = max(1, _n_to_gen) * 1.5 / 60
    _t_max    = max(1, _n_to_gen) * 3   / 60

    ci1, ci2, ci3 = st.columns(3)
    ci1.metric("Runs total",      _n_singles)
    ci2.metric("Déjà générés",    _n_singles_done)
    ci3.metric("Durée estimée",   f"{_t_min:.0f}–{_t_max:.0f} min",
               help="~1.5–3 min par run selon la machine")

    skip_singles = st.checkbox(
        f"Passer les {_n_singles_done} run(s) déjà générés",
        value=True, key="skip_singles",
    )
    n_singles_to_run = _n_to_gen if skip_singles else _n_singles

    if singles["running"]:
        st.warning("⏳ Génération en cours — MT5 tourne en arrière-plan.")
        if st.button("⛔ Arrêter après le run en cours", type="secondary", key="stop_singles"):
            singles["running"] = False
    else:
        mt5_open_s = is_mt5_running()
        if mt5_open_s:
            st.warning("⚠️ **MT5 est ouvert.** Fermez-le avant de lancer.")
        if st.button(
            f"🚀 Générer {n_singles_to_run} backtest(s) individuel(s)",
            type="primary", use_container_width=True,
            disabled=(n_singles_to_run == 0 or mt5_open_s),
            key="launch_singles",
        ):
            singles["running"] = True
            singles["results"] = []
            singles["combos"]  = list(single_combos)
            threading.Thread(
                target=_singles_worker,
                args=(singles, list(single_combos)),
                daemon=True,
            ).start()
            st.rerun()

    # ── Progression ───────────────────────────────────────────────────────────
    if singles["results"] or singles["running"]:
        st.divider()
        _done_s  = sum(1 for r in singles["results"] if r.get("status") == "done")
        _skip_s  = sum(1 for r in singles["results"] if r.get("status") == "skipped")
        _err_s   = sum(1 for r in singles["results"] if r.get("status") == "error")
        _proc_s  = _done_s + _skip_s + _err_s
        _tot_s   = len(singles["combos"]) * 3
        if _tot_s:
            st.progress(
                _proc_s / _tot_s,
                text=f"{_proc_s}/{_tot_s} — {_done_s} OK · {_skip_s} passés · {_err_s} erreur(s)",
            )
        _recent = singles["results"][-30:]
        col_a, col_b = st.columns(2)
        for i, r in enumerate(_recent):
            s, lbl, det = r.get("status", ""), r.get("label", ""), r.get("detail", "")
            tgt = col_a if i % 2 == 0 else col_b
            if s == "done":
                tgt.success(f"✅ `{lbl}`")
            elif s == "skipped":
                tgt.markdown(
                    f"<span style='color:#9AA3B0;font-size:0.85em'>⏭ {lbl}</span>",
                    unsafe_allow_html=True,
                )
            elif s == "error":
                tgt.error(f"❌ `{lbl}`" + (f" — {det}" if det else ""))
            elif s == "running":
                tgt.info(f"⏳ `{lbl}` — en cours…")
        if singles["running"]:
            time.sleep(3)
            st.rerun()
        elif singles["results"] and _err_s == 0:
            st.balloons()
            st.success(
                f"🎉 Terminé ! {_done_s} générés, {_skip_s} passés.  \n"
                "👈 Analysez les trades dans **📋 Journaux de Trades**."
            )
        elif _err_s > 0:
            st.warning(f"{_done_s} OK · {_skip_s} passés · {_err_s} erreur(s).")
