"""
Automatisation des optimisations Walk-Forward MetaTrader 5.

Génère les fichiers INI depuis les .set de référence (OneDrive Paramètrage_EA),
copie les .set vers MQL5\\Profiles\\Tester\\, lance terminal64.exe en mode batch
séquentiel et classe les XML dans OUTPUT_BASE/<EA>/<Symbol>/<TF>/fold<N>/.

Enums MT5 utilisés (vérifiés sur doc officielle) :
  Optimization=1          → Slow Complete (grille exhaustive)
  Model=2                 → Open prices only
  ForwardMode=4           → Custom date
  OptimizationCriterion=6 → Custom / OnTester()
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterator

from config import PROJECT_ROOT, RESULTS_FT_DIR

# ── Disponibilité MT5 ─────────────────────────────────────────────────────────
MT5_AVAILABLE: bool = sys.platform == "win32"


def _detect_mt5_data() -> Path | None:
    """Détecte automatiquement le dossier AppData de MetaTrader 5.

    Le dossier est nommé avec un hash MD5 qui dépend du broker — il varie
    d'une machine à l'autre. On prend le premier dossier contenant MQL5/.
    """
    base = Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal"
    if not base.exists():
        return None
    for candidate in sorted(base.iterdir()):
        if candidate.is_dir() and (candidate / "MQL5").exists():
            return candidate
    return None


if MT5_AVAILABLE:
    MT5_EXE  = Path(r"C:\Program Files\MetaTrader 5\terminal64.exe")
    MT5_DATA = _detect_mt5_data()
    MT5_PROFILES_TESTER = MT5_DATA / "MQL5" / "Profiles" / "Tester" if MT5_DATA else None
    MT5_FILES            = MT5_DATA / "MQL5" / "Files"               if MT5_DATA else None

    # SET_SOURCE_DIR : dossier contenant les fichiers .set d'optimisation.
    # Priorité : variable d'env TB_SET_DIR > data/Paramètrage_EA/ dans le projet.
    _env_set = os.environ.get("TB_SET_DIR")
    SET_SOURCE_DIR = (
        Path(_env_set) if _env_set
        else PROJECT_ROOT / "data" / "Paramètrage_EA"
    )
else:
    MT5_EXE = MT5_DATA = MT5_PROFILES_TESTER = MT5_FILES = SET_SOURCE_DIR = None  # type: ignore[assignment]

# ── Dossiers projet ───────────────────────────────────────────────────────────
OUTPUT_BASE = RESULTS_FT_DIR

# ── Configuration des EAs ─────────────────────────────────────────────────────
EA_CONFIG: dict[str, dict] = {
    "ATR": {
        "ex5":   r"TB\EA_ATRBreakout_Roll.ex5",
        "set":   "EA_ATR_BREAKOUT_FILTER.set",
        "label": "ATR Breakout",
    },
    "BK": {
        "ex5":   r"TB\EA_Breakout_Roll.ex5",
        "set":   "EA_BREAKOUT_FILTER.set",
        "label": "Breakout",
    },
    "MR": {
        "ex5":   r"TB\EA_MeanReversion_Roll.ex5",
        "set":   "EA_MEANREVERSION_FILTER.set",
        "label": "Mean Reversion",
    },
    "MA": {
        "ex5":   r"TB\EA_MoyennesMobiles_Roll.ex5",
        "set":   "EA_MA_FILTER.set",
        "label": "Moyennes Mobiles",
    },
    "TEMA": {
        "ex5":   r"TB\EA_TripleEMA_Roll.ex5",
        "set":   "EA_TRIPLE_MA_FILTER.set",
        "label": "Triple EMA",
    },
    "ZS": {
        "ex5":   r"TB\EA_ZScore_Roll.ex5",
        "set":   "EA_ZSCORE_FILTER.set",
        "label": "Z-Score",
    },
}

# ── Symboles (suffixe .TB obligatoire) ────────────────────────────────────────
SYMBOLS: dict[str, str] = {
    "BRENT.TB":      "BRENT",
    "NATURALGAS.TB": "NATURALGAS",
    "GOLD.TB":       "GOLD",
    "PLATINUM.TB":   "PLATINUM",
    "COFFEE.TB":     "COFFEE",
    "COCOA.TB":      "COCOA",
}

# Symboles dont l'historique IC Markets peut ne pas remonter à 2015
SYMBOLS_HISTORY_WARNING: set[str] = {"GOLD.TB", "PLATINUM.TB"}

# ── Timeframes ────────────────────────────────────────────────────────────────
TIMEFRAMES: list[str] = ["H1", "H4", "D1"]

# ── Plis Walk-Forward glissants ───────────────────────────────────────────────
# IS = [from_date, forward_date[  ;  OOS = [forward_date, to_date]
FOLDS: list[dict] = [
    {"n": 1, "from_date": "2015.01.01", "to_date": "2021.12.31", "forward_date": "2020.01.01"},
    {"n": 2, "from_date": "2017.01.01", "to_date": "2023.12.31", "forward_date": "2022.01.01"},
    {"n": 3, "from_date": "2019.01.01", "to_date": "2025.12.31", "forward_date": "2024.01.01"},
]


# ── Helpers publics ───────────────────────────────────────────────────────────

def job_label(ea_short: str, symbol_mt5: str, timeframe: str, fold_n: int) -> str:
    sym_clean = SYMBOLS.get(symbol_mt5, symbol_mt5.replace(".TB", ""))
    return f"{ea_short}_{sym_clean}_{timeframe}_fold{fold_n}"


def job_output_paths(
    ea_short: str,
    symbol_mt5: str,
    timeframe: str,
    fold_n: int,
    output_base: Path = OUTPUT_BASE,
) -> tuple[Path, Path]:
    """Retourne (is_dest, fwd_dest) pour un job donné."""
    ea_label  = EA_CONFIG[ea_short]["label"].replace(" ", "_")
    sym_clean = SYMBOLS.get(symbol_mt5, symbol_mt5.replace(".TB", ""))
    out_dir   = output_base / ea_label / symbol_mt5 / timeframe / f"fold{fold_n}"
    stem      = f"{ea_short}_{sym_clean}_{timeframe}_fold{fold_n}"
    return out_dir / f"{stem}_IS.xml", out_dir / f"{stem}_OOS.xml"


# ── Validation et copie des .set ──────────────────────────────────────────────

def _read_set_text(ea_short: str) -> str:
    raw = (SET_SOURCE_DIR / EA_CONFIG[ea_short]["set"]).read_bytes()
    if raw[:2] == b"\xff\xfe":
        return raw.decode("utf-16-le")
    return raw.decode("utf-8", errors="replace")


def validate_set_has_optim_params(ea_short: str) -> bool:
    """Vérifie qu'au moins un paramètre a le flag d'optimisation actif (||Y)."""
    return any(
        line.rstrip().endswith("||Y")
        for line in _read_set_text(ea_short).splitlines()
    )


def copy_set_to_tester(ea_short: str) -> None:
    """Copie le .set depuis OneDrive vers MQL5\\Profiles\\Tester\\."""
    src = SET_SOURCE_DIR / EA_CONFIG[ea_short]["set"]
    MT5_PROFILES_TESTER.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(MT5_PROFILES_TESTER / EA_CONFIG[ea_short]["set"]))


# ── Génération de l'INI tester ────────────────────────────────────────────────

def generate_tester_ini(
    ea_short: str,
    symbol_mt5: str,
    timeframe: str,
    fold: dict,
    deposit: float = 100_000.0,
) -> tuple[Path, Path, Path]:
    """
    Génère un fichier INI pour le Strategy Tester MT5.

    Returns
    -------
    (ini_path, tmp_is_xml, tmp_fwd_xml)
        Chemins des fichiers temporaires dans MT5_FILES.
    """
    ea        = EA_CONFIG[ea_short]
    sym_clean = SYMBOLS.get(symbol_mt5, symbol_mt5.replace(".TB", ""))
    fold_n    = fold["n"]

    temp_stem   = f"_batch_{ea_short}_{sym_clean}_{timeframe}_fold{fold_n}"
    tmp_is_xml  = MT5_FILES / f"{temp_stem}.xml"
    tmp_fwd_xml = MT5_FILES / f"{temp_stem}.forward.xml"

    # Report= est relatif à MT5_DATA ; MT5 ajoute l'extension .xml/.forward.xml
    report_rel = rf"MQL5\Files\{temp_stem}"

    ini_content = (
        f"; Généré automatiquement par TB Quant Dashboard\n"
        f"[Tester]\n"
        f"Expert={ea['ex5']}\n"
        f"ExpertParameters={ea['set']}\n"
        f"Symbol={symbol_mt5}\n"
        f"Period={timeframe}\n"
        f"FromDate={fold['from_date']}\n"
        f"ToDate={fold['to_date']}\n"
        f"ForwardMode=4\n"
        f"ForwardDate={fold['forward_date']}\n"
        f"Optimization=1\n"
        f"OptimizationCriterion=6\n"
        f"Model=2\n"
        f"Deposit={deposit:.0f}\n"
        f"Currency=USD\n"
        f"Leverage=1\n"
        f"ExecutionMode=0\n"
        f"Visual=0\n"
        f"ReplaceReport=1\n"
        f"ShutdownTerminal=1\n"
        f"Report={report_rel}\n"
    )

    MT5_FILES.mkdir(parents=True, exist_ok=True)
    ini_path = MT5_FILES / "_batch_temp.ini"
    ini_path.write_text(ini_content, encoding="utf-16")
    return ini_path, tmp_is_xml, tmp_fwd_xml


# ── Lancement MT5 ─────────────────────────────────────────────────────────────

def _kill(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except Exception:
            proc.kill()


def launch_and_wait(
    ini_path: Path,
    tmp_is_xml: Path,
    tmp_fwd_xml: Path,
    timeout_s: int = 7200,
    poll_interval_s: int = 15,
    post_exit_wait_s: int = 15,
) -> tuple[Path | None, Path | None]:
    """
    Lance terminal64.exe /config:ini_path et attend la fin.

    Avec ShutdownTerminal=1, MT5 se ferme lui-même après l'optimisation.
    On attend simplement la sortie du process, puis on collecte les XML.

    Pour les backtests individuels courts (Optimization=0), utiliser
    poll_interval_s=3 et post_exit_wait_s=3 pour réduire le overhead.

    Returns
    -------
    (is_xml, fwd_xml) — None si le fichier n'a pas été produit ou est trop petit.
    """
    if not MT5_AVAILABLE:
        raise RuntimeError("Le lancement MT5 n'est disponible que sur Windows.")

    for p in (tmp_is_xml, tmp_fwd_xml):
        if p.exists():
            p.unlink()

    si = subprocess.STARTUPINFO()
    si.dwFlags     = subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 6  # SW_MINIMIZE

    proc = subprocess.Popen(
        [str(MT5_EXE), f"/config:{ini_path}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        startupinfo=si,
    )

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if proc.poll() is not None:
            time.sleep(post_exit_wait_s)
            break
        time.sleep(poll_interval_s)
    else:
        _kill(proc)

    is_path  = tmp_is_xml  if (tmp_is_xml.exists()  and tmp_is_xml.stat().st_size  > 5_000) else None
    fwd_path = tmp_fwd_xml if (tmp_fwd_xml.exists() and tmp_fwd_xml.stat().st_size > 1_000) else None
    return is_path, fwd_path


# ── Runner batch ──────────────────────────────────────────────────────────────

def run_batch(
    jobs: list[dict],
    deposit: float = 100_000.0,
    output_base: Path = OUTPUT_BASE,
    skip_existing: bool = True,
) -> Iterator[dict]:
    """
    Exécute les jobs Walk-Forward séquentiellement.

    Chaque job : {"ea": str, "symbol": str, "tf": str, "fold": dict}

    Yield des dicts de progression :
        status  : "running" | "done" | "skipped" | "error"
        index   : position dans la liste
        total   : nombre total de jobs
        label   : identifiant lisible du job
        is_ok   : bool (only if status=="done")
        fwd_ok  : bool (only if status=="done")
        detail  : str  (only if status=="error")
    """
    total = len(jobs)

    for i, job in enumerate(jobs):
        ea, sym, tf, fold = job["ea"], job["symbol"], job["tf"], job["fold"]
        fold_n = fold["n"]
        lbl    = job_label(ea, sym, tf, fold_n)
        is_dest, fwd_dest = job_output_paths(ea, sym, tf, fold_n, output_base)

        if skip_existing and is_dest.exists() and is_dest.stat().st_size > 5_000:
            yield {"status": "skipped", "index": i, "total": total, "label": lbl}
            continue

        yield {"status": "running", "index": i, "total": total, "label": lbl}

        ini_path: Path | None = None
        tmp_is:   Path | None = None
        tmp_fwd:  Path | None = None
        try:
            if not validate_set_has_optim_params(ea):
                yield {
                    "status": "error", "index": i, "total": total, "label": lbl,
                    "detail": f"Aucun paramètre avec flag Y dans {EA_CONFIG[ea]['set']}",
                }
                continue

            copy_set_to_tester(ea)
            is_dest.parent.mkdir(parents=True, exist_ok=True)

            ini_path, tmp_is, tmp_fwd = generate_tester_ini(
                ea_short=ea, symbol_mt5=sym, timeframe=tf, fold=fold, deposit=deposit,
            )

            is_path, fwd_path = launch_and_wait(ini_path, tmp_is, tmp_fwd)

            if is_path:
                shutil.move(str(is_path), str(is_dest))
            if fwd_path:
                shutil.move(str(fwd_path), str(fwd_dest))

            if is_path or fwd_path:
                yield {
                    "status": "done", "index": i, "total": total, "label": lbl,
                    "is_ok": is_path is not None, "fwd_ok": fwd_path is not None,
                }
            else:
                yield {
                    "status": "error", "index": i, "total": total, "label": lbl,
                    "detail": "Aucun XML produit (timeout ou crash MT5)",
                }

        except Exception as exc:
            yield {
                "status": "error", "index": i, "total": total, "label": lbl,
                "detail": str(exc),
            }
        finally:
            if ini_path is not None and ini_path.exists():
                ini_path.unlink(missing_ok=True)
            # Nettoyer les fichiers temp non déplacés (trop petits ou non produits)
            for leftover in filter(None, (tmp_is, tmp_fwd)):
                if leftover.exists():
                    leftover.unlink(missing_ok=True)


# ── Vérification de l'environnement ──────────────────────────────────────────

def is_mt5_running() -> bool:
    """Retourne True si terminal64.exe tourne déjà."""
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq terminal64.exe", "/NH"],
        capture_output=True, text=True,
    )
    return "terminal64.exe" in result.stdout


def check_environment() -> list[str]:
    """Retourne une liste d'erreurs de configuration (vide = tout OK)."""
    if not MT5_AVAILABLE:
        return ["Cette fonctionnalité n'est disponible que sur Windows."]
    errors: list[str] = []
    if not MT5_EXE.exists():
        errors.append(f"terminal64.exe introuvable : {MT5_EXE}")
    if MT5_DATA is None:
        errors.append("Aucun dossier MetaTrader 5 trouvé dans AppData\\Roaming\\MetaQuotes\\Terminal\\")
    elif not MT5_DATA.exists():
        errors.append(f"Dossier données MT5 introuvable : {MT5_DATA}")
    if not SET_SOURCE_DIR.exists():
        errors.append(f"Dossier Paramètrage_EA introuvable : {SET_SOURCE_DIR}")
    for short, cfg in EA_CONFIG.items():
        sp = SET_SOURCE_DIR / cfg["set"]
        if not sp.exists():
            errors.append(f"Fichier .set manquant pour {short} : {sp.name}")
        ex5 = MT5_DATA / "MQL5" / "Experts" / cfg["ex5"]
        if not ex5.exists():
            errors.append(f"Expert .ex5 introuvable pour {short} : {cfg['ex5']}")
    return errors
