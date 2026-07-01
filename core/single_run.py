"""
core/single_run.py
Lancement de passes individuelles MT5 (Optimization=0) pour obtenir les
journaux de trades complets avec date, P&L et balance par trade.

Flux par combinaison (robot × actif × tf × pli) :
  1. Charger l'OOS XML existant via load_combo_df
  2. Sélectionner 3 passes représentatives : meilleure / médiane / pire
     (parmi les passes filtrées sur OOS_Trades >= min_trades)
  3. Extraire les paramètres Inp* de la passe sélectionnée
  4. Générer un .set avec ces paramètres fixés (flags d'optimisation → N)
  5. Générer un INI Optimization=0 sur la fenêtre OOS + warmup
  6. Lancer MT5 en mode backtest individuel (ShutdownTerminal=1)
  7. Parser le rapport XML détaillé → DataFrame de trades datés
  8. Sauvegarder dans Résultats_Detail/<robot>/<actif>/<tf>/fold<n>/
"""
from __future__ import annotations

import html.parser as _html_parser
import shutil
import time as _time
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import pandas as pd

from core.loader import load_combo_df
from core.mt5_runner import (
    EA_CONFIG,
    FOLDS,
    MT5_DATA,
    MT5_EXE,
    MT5_FILES,
    MT5_PROFILES_TESTER,
    OUTPUT_BASE,
    SET_SOURCE_DIR,
    SYMBOLS,
    launch_and_wait,
)

# ── Chemins ───────────────────────────────────────────────────────────────────
OUTPUT_DETAIL: Path = OUTPUT_BASE.parent / "Résultats_Detail"

# ── Constantes ────────────────────────────────────────────────────────────────
_PASS_LABELS = ("best", "median", "worst")
_FOLD_BY_N: dict[int, dict] = {f["n"]: f for f in FOLDS}
_TRADE_KW   = {"time", "profit", "volume", "price", "balance"}


# ── Parser HTML (stdlib uniquement — MT5 produit .htm pour Optimization=0) ────
class _HtmlTableExtractor(_html_parser.HTMLParser):
    """Extrait toutes les tables d'un fichier HTML avec le parser standard."""
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._tbl:  list[list[str]] | None = None
        self._row:  list[str]       | None = None
        self._cell: list[str]       | None = None

    def handle_starttag(self, tag: str, attrs: list) -> None:
        t = tag.lower()
        if t == "table":
            self._tbl = []
        elif t == "tr" and self._tbl is not None:
            self._row = []
        elif t in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t == "table":
            if self._tbl:
                self.tables.append(self._tbl)
            self._tbl = self._row = self._cell = None
        elif t == "tr" and self._tbl is not None:
            if self._row and any(c.strip() for c in self._row):
                self._tbl.append(self._row)
            self._row = self._cell = None
        elif t in ("td", "th") and self._row is not None:
            if self._cell is not None:
                self._row.append("".join(self._cell).strip())
            self._cell = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


_FR_EN: dict[str, str] = {
    "heure":                "Time",
    "heure d'ouverture":    "Time",
    "prix":                 "Price",
    "solde":                "Balance",
    "opération":            "Deal",
    "operation":            "Deal",
    "symbole":              "Symbol",
    "echange":              "Swap",
    "échange":              "Swap",
    "commentaire":          "Comment",
}
# Mots-clés pour détecter la bonne ligne d'en-tête (anglais + français)
_HDR_KW = {"time", "profit", "volume", "price", "balance",
            "heure", "solde", "prix"}


def _parse_mt5_htm(htm_path: Path) -> pd.DataFrame:
    """
    Parse le rapport HTML d'un backtest individuel MT5 (Optimization=0).

    MT5 en français produit un seul <table> avec deux sections :
      - «Ordres»       : sans colonne Profit
      - «Transactions» : avec Heure / Profit / Solde / …

    Le parser scanne TOUTES les lignes de TOUTES les tables pour trouver
    la ligne d'en-tête qui contient «Profit», puis lit les lignes suivantes.
    """
    content: str | None = None
    for enc in ("utf-16", "utf-16-le", "utf-8-sig", "utf-8", "cp1252"):
        try:
            content = htm_path.read_text(encoding=enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if content is None:
        return pd.DataFrame()

    extractor = _HtmlTableExtractor()
    try:
        extractor.feed(content)
    except Exception:
        return pd.DataFrame()

    # Chercher la ligne d'en-tête avec le meilleur score de mots-clés,
    # en exigeant que "profit" soit présent.
    best_tbl:   list[list[str]] | None = None
    best_idx:   int = 0
    best_score: int = 0

    for rows in extractor.tables:
        for i, row in enumerate(rows):
            lc = {c.strip().lower() for c in row}
            score = len(lc & _HDR_KW)
            if score > best_score and "profit" in lc:
                best_score = score
                best_tbl   = rows
                best_idx   = i

    if best_score < 2 or best_tbl is None:
        return pd.DataFrame()

    headers = best_tbl[best_idx]
    records = [r + [""] * max(0, len(headers) - len(r))
               for r in best_tbl[best_idx + 1:]]
    df = pd.DataFrame(records, columns=headers)

    # Normalisation des noms de colonnes (français → anglais + casse)
    rename: dict[str, str] = {}
    for col in df.columns:
        cl = str(col).strip().lower()
        if cl in _FR_EN:
            rename[col] = _FR_EN[cl]
        else:
            for tgt in ("Time", "Profit", "Balance", "Volume", "Price",
                        "Type", "Commission", "Swap", "Deal", "Comment",
                        "Direction", "Symbol"):
                if cl == tgt.lower():
                    rename[col] = tgt
                    break
    df = df.rename(columns=rename)

    # Parsing des dates
    if "Time" in df.columns:
        df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
        df = df.dropna(subset=["Time"]).reset_index(drop=True)

    # Parsing numérique — MT5 utilise l'espace comme séparateur de milliers
    for col in ("Profit", "Balance", "Commission", "Swap", "Volume", "Price"):
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                .str.replace(" ", "", regex=False)  # espace fine insécable
                .str.replace("\xa0",   "", regex=False)  # espace insécable
                .str.replace(" ",      "", regex=False)  # espace ordinaire
                .pipe(pd.to_numeric, errors="coerce")
            )

    # Filtrage : ne garder que les clôtures de positions
    if "Direction" in df.columns:
        # Section Transactions MT5 FR : Direction = "in" (ouverture) | "out" (clôture)
        df = df[df["Direction"].astype(str).str.lower() == "out"].reset_index(drop=True)
    elif "Type" in df.columns:
        keep = {"buy", "sell", "buy stop", "sell stop", "buy limit", "sell limit"}
        df = df[df["Type"].astype(str).str.lower().isin(keep)].reset_index(drop=True)

    if "Profit" in df.columns:
        df = df[df["Profit"].notna()].reset_index(drop=True)

    return df


# ══════════════════════════════════════════════════════════════════════════════
# Sélection des passes représentatives
# ══════════════════════════════════════════════════════════════════════════════

def select_representative_passes(
    robot: str,
    actif_tb: str,
    tf: str,
    pli: int,
    score_col: str = "OOS_Score",
    min_trades_oos: int = 30,
) -> dict[str, pd.Series | None]:
    """
    Sélectionne meilleure / médiane / pire passe OOS depuis le XML existant.

    Returns
    -------
    dict {"best": Series | None, "median": Series | None, "worst": Series | None}
    Chaque Series a les colonnes Pass, OOS_Score, OOS_Trades et tous les Inp*.
    """
    # min_trades=0 : on gère le filtre nous-mêmes via min_trades_oos
    df = load_combo_df(robot=robot, actif=actif_tb, tf=tf, pli=pli, min_trades=0)
    if df.empty or score_col not in df.columns:
        return {lbl: None for lbl in _PASS_LABELS}

    # Filtrer : score valide + trades OOS suffisants
    mask = df[score_col].notna()
    if "OOS_Trades" in df.columns:
        mask &= df["OOS_Trades"] >= min_trades_oos
    df_f = df[mask].sort_values(score_col, ascending=False).reset_index(drop=True)

    # Fallback progressif : si le filtre min_trades est trop restrictif
    # (stratégie peu active sur D1, actif peu liquide, etc.), on relâche.
    if df_f.empty and "OOS_Trades" in df.columns:
        for fallback in (5, 1, 0):
            mask2 = df[score_col].notna()
            if fallback > 0:
                mask2 &= df["OOS_Trades"] >= fallback
            df_f = df[mask2].sort_values(score_col, ascending=False).reset_index(drop=True)
            if not df_f.empty:
                break

    if df_f.empty:
        return {lbl: None for lbl in _PASS_LABELS}

    n = len(df_f)
    return {
        "best":   df_f.iloc[0],
        "median": df_f.iloc[n // 2],
        "worst":  df_f.iloc[-1],
    }


# ══════════════════════════════════════════════════════════════════════════════
# Génération du .set file avec paramètres fixés
# ══════════════════════════════════════════════════════════════════════════════

def _read_set_bytes(ea_short: str) -> bytes:
    return (SET_SOURCE_DIR / EA_CONFIG[ea_short]["set"]).read_bytes()


def _param_values_from_row(row: pd.Series) -> dict[str, Any]:
    """Extrait les colonnes Inp* d'une passe comme dict paramètre → valeur."""
    return {
        col: row[col]
        for col in row.index
        if str(col).startswith("Inp") and pd.notna(row[col])
    }


def _fmt_val(val: Any) -> str:
    """Formate une valeur numérique pour le .set (entier si pas de décimale)."""
    try:
        f = float(val)
        return str(int(f)) if f == int(f) else str(f)
    except (TypeError, ValueError):
        return str(val)


def _build_fixed_set(ea_short: str, param_values: dict[str, Any]) -> bytes:
    """
    Génère le contenu du .set file avec paramètres fixés (tous les ||Y → ||N,
    valeurs remplacées pour les paramètres présents dans param_values).

    Retourne le contenu encodé en UTF-16 LE avec BOM.
    """
    raw = _read_set_bytes(ea_short)
    if raw[:2] == b"\xff\xfe":
        text = raw[2:].decode("utf-16-le")
    else:
        text = raw.decode("utf-8", errors="replace")

    lines_out: list[str] = []
    for line in text.splitlines():
        stripped = line.rstrip()
        # Ligne de paramètre MT5 : Name=value||...||Y ou ||N
        if "=" in stripped and "||" in stripped:
            name, rest = stripped.split("=", 1)
            name = name.strip()
            parts = rest.split("||")
            # Remplacer la valeur si le param est dans notre dict
            if name in param_values:
                parts[0] = _fmt_val(param_values[name])
            # Désactiver l'optimisation sur toutes les lignes
            parts[-1] = "N"
            line = f"{name}={'||'.join(parts)}"
        lines_out.append(line)

    content = "\r\n".join(lines_out)
    # UTF-16 LE avec BOM (format attendu par MT5)
    return b"\xff\xfe" + content.encode("utf-16-le")


# ══════════════════════════════════════════════════════════════════════════════
# Chemins de sortie
# ══════════════════════════════════════════════════════════════════════════════

def _detail_stem(robot: str, actif_clean: str, tf: str, pli: int, pass_label: str) -> str:
    return f"{robot}_{actif_clean}_{tf}_fold{pli}_{pass_label}"


def detail_csv_path(robot, actif_clean, tf, pli, pass_label, output_detail=OUTPUT_DETAIL) -> Path:
    folder = output_detail / robot / actif_clean / tf / f"fold{pli}"
    return folder / f"{_detail_stem(robot, actif_clean, tf, pli, pass_label)}.csv"


def detail_htm_path(robot, actif_clean, tf, pli, pass_label, output_detail=OUTPUT_DETAIL) -> Path:
    """Chemin attendu pour un rapport HTML placé manuellement."""
    folder = output_detail / robot / actif_clean / tf / f"fold{pli}"
    return folder / f"{_detail_stem(robot, actif_clean, tf, pli, pass_label)}.htm"


def _detail_found(robot, actif_clean, tf, pli, pass_label, output_detail) -> Path | None:
    """Retourne le chemin du fichier de données (CSV ou HTM) s'il existe."""
    csv = detail_csv_path(robot, actif_clean, tf, pli, pass_label, output_detail)
    if csv.exists() and csv.stat().st_size > 50:
        return csv
    htm = detail_htm_path(robot, actif_clean, tf, pli, pass_label, output_detail)
    if htm.exists() and htm.stat().st_size > 2_000:
        return htm
    return None


def detail_status(
    combos: list[dict],
    output_detail: Path = OUTPUT_DETAIL,
) -> dict[str, str]:
    """
    Retourne "done" si un CSV (généré automatiquement) ou un HTM
    (placé manuellement) existe pour chaque (robot/actif/tf/pli/label).
    """
    status: dict[str, str] = {}
    for c in combos:
        actif_clean = SYMBOLS.get(c["actif_tb"], c["actif_tb"].replace(".TB", ""))
        for lbl in _PASS_LABELS:
            key = f"{c['robot']}/{actif_clean}/{c['tf']}/fold{c['pli']}/{lbl}"
            found = _detail_found(c["robot"], actif_clean, c["tf"], c["pli"], lbl, output_detail)
            status[key] = "done" if found is not None else "missing"
    return status


# ══════════════════════════════════════════════════════════════════════════════
# Génération de l'INI single-run
# ══════════════════════════════════════════════════════════════════════════════

_WARMUP_DAYS: dict[str, int] = {"D1": 200, "H4": 90, "H1": 60}


def _generate_single_ini(
    ea_short: str,
    symbol_mt5: str,
    tf: str,
    fold: dict,
    temp_stem: str,
    deposit: float = 100_000.0,
    warmup_days: int | None = None,
) -> tuple[Path, Path]:
    """
    Génère un INI MT5 pour un backtest individuel (Optimization=0).

    Fenêtre : [OOS_start - warmup_days, OOS_end]
    ForwardMode=0 — les trades couvrent tout le run, on filtrera sur OOS_start.

    Returns
    -------
    (ini_path, tmp_xml_path)
    """
    ea = EA_CONFIG[ea_short]
    if warmup_days is None:
        warmup_days = _WARMUP_DAYS.get(tf, 180)
    oos_start = pd.Timestamp(fold["forward_date"].replace(".", "-"))
    from_ts   = oos_start - pd.Timedelta(days=warmup_days)
    from_date = from_ts.strftime("%Y.%m.%d")
    to_date   = fold["to_date"]

    # Chemin RELATIF à MT5_DATA — même format que WF batch (Optimization=1) qui fonctionne.
    # MT5 ignore les chemins absolus pour Report= ; il ajoute .htm pour Optimization=0.
    report_rel = rf"MQL5\Files\{temp_stem}"
    tmp_htm    = MT5_FILES / f"{temp_stem}.htm"

    ini_content = (
        f"; Généré automatiquement — passe individuelle\n"
        f"[Tester]\n"
        f"Expert={ea['ex5']}\n"
        f"ExpertParameters={ea['set']}\n"
        f"Symbol={symbol_mt5}\n"
        f"Period={tf}\n"
        f"FromDate={from_date}\n"
        f"ToDate={to_date}\n"
        f"ForwardMode=0\n"
        f"Optimization=0\n"
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

    ini_path = MT5_FILES / "_single_temp.ini"
    MT5_FILES.mkdir(parents=True, exist_ok=True)
    ini_path.write_text(ini_content, encoding="utf-16")
    return ini_path, tmp_htm




# ══════════════════════════════════════════════════════════════════════════════
# Recherche du fichier produit par MT5 (chemin et extension variables)
# ══════════════════════════════════════════════════════════════════════════════

def _find_mt5_report(stem: str, since_ts: float) -> tuple[Path | None, str]:
    """
    Cherche le fichier rapport produit par MT5 après un single-run.

    MT5 peut écrire dans MT5_FILES, MT5_DATA/Tester/ ou MT5_DATA/reports/,
    avec l'extension .htm, .html ou .xml selon la version.

    Returns (path_found | None, diagnostic_message)
    """
    # 1 — Chemin canonique (.htm, .html, .xml)
    for ext in (".htm", ".html", ".xml"):
        p = MT5_FILES / f"{stem}{ext}"
        if p.exists() and p.stat().st_size > 1_000:
            return p, ""

    # 2 — Scan large : tout fichier récent dans les répertoires MT5
    recent: list[Path] = []
    scan_dirs = [
        MT5_FILES,
        MT5_DATA / "Tester",
        MT5_DATA / "reports",
        MT5_DATA / "MQL5" / "Logs",
        MT5_DATA,
    ]
    for d in scan_dirs:
        if not d.exists():
            continue
        try:
            for p in d.rglob("*"):
                if not p.is_file():
                    continue
                if p.suffix.lower() not in (".htm", ".html", ".xml"):
                    continue
                try:
                    st = p.stat()
                    if st.st_mtime >= since_ts and st.st_size > 1_000:
                        recent.append(p)
                except OSError:
                    pass
        except Exception:
            pass

    # Préférer les fichiers dont le nom contient le stem
    for p in sorted(recent, key=lambda x: x.stat().st_mtime, reverse=True):
        if stem in p.name:
            return p, f"trouvé à {p}"

    # Sinon retourner le plus récent
    if recent:
        best = max(recent, key=lambda x: x.stat().st_mtime)
        return best, f"nom inattendu — trouvé à {best}"

    # 3 — Diagnostic : lister tous les nouveaux fichiers dans MT5_FILES
    new_any: list[str] = []
    if MT5_FILES.exists():
        for p in MT5_FILES.iterdir():
            try:
                if p.stat().st_mtime >= since_ts:
                    new_any.append(f"{p.name}({p.stat().st_size}o)")
            except OSError:
                pass
    diag = (
        f"MT5 n'a produit aucun rapport .htm/.xml. "
        f"Nouveaux fichiers dans MQL5/Files : {new_any or 'aucun'}. "
        f"Vérifiez que MT5 est bien fermé et que l'EA compile."
    )
    return None, diag


# ══════════════════════════════════════════════════════════════════════════════
# Instructions pour import manuel
# ══════════════════════════════════════════════════════════════════════════════

def get_manual_import_instructions(
    combos: list[dict],
    output_detail: Path = OUTPUT_DETAIL,
    min_trades_oos: int = 30,
) -> list[dict]:
    """
    Pour chaque combo manquant, retourne les paramètres exacts à utiliser
    dans MT5 Strategy Tester pour générer le rapport manuellement.

    Chaque dict contient : robot, actif_tb, tf, pli, pass_label,
    from_date, to_date, params (dict Inp*→valeur), out_path (où déposer le .htm)
    """
    instructions = []
    for c in combos:
        robot       = c["robot"]
        actif_tb    = c["actif_tb"]
        actif_clean = SYMBOLS.get(actif_tb, actif_tb.replace(".TB", ""))
        tf          = c["tf"]
        pli         = c["pli"]
        fold        = _FOLD_BY_N.get(pli, {})

        reps = select_representative_passes(robot, actif_tb, tf, pli, min_trades_oos=min_trades_oos)

        for lbl in _PASS_LABELS:
            found = _detail_found(robot, actif_clean, tf, pli, lbl, output_detail)
            if found is not None:
                continue  # déjà disponible

            pass_row = reps.get(lbl)
            if pass_row is None:
                continue

            param_values = _param_values_from_row(pass_row)
            out_htm = detail_htm_path(robot, actif_clean, tf, pli, lbl, output_detail)

            instructions.append({
                "robot":      robot,
                "actif_tb":   actif_tb,
                "tf":         tf,
                "pli":        pli,
                "pass_label": lbl,
                "from_date":  fold.get("forward_date", ""),
                "to_date":    fold.get("to_date", ""),
                "params":     param_values,
                "out_path":   out_htm,
            })
    return instructions


# ══════════════════════════════════════════════════════════════════════════════
# Chargement des trades déjà générés
# ══════════════════════════════════════════════════════════════════════════════

def load_detail_trades(
    robot: str,
    actif_clean: str,
    tf: str,
    pli: int,
    pass_label: str,
    output_detail: Path = OUTPUT_DETAIL,
    oos_start: str | None = None,
) -> pd.DataFrame:
    found = _detail_found(robot, actif_clean, tf, pli, pass_label, output_detail)
    if found is None:
        return pd.DataFrame()

    try:
        if found.suffix.lower() in (".htm", ".html"):
            df = _parse_mt5_htm(found)
        else:
            df = pd.read_csv(str(found), parse_dates=["Time"])
    except Exception:
        return pd.DataFrame()

    if oos_start and "Time" in df.columns:
        df = df[df["Time"] >= pd.Timestamp(oos_start)].reset_index(drop=True)
    return df


def load_all_detail_trades(
    combos: list[dict],
    output_detail: Path = OUTPUT_DETAIL,
) -> pd.DataFrame:
    """
    Charge et concatène tous les journaux disponibles pour une liste de combos.

    Chaque combo : {"robot": str, "actif_tb": str, "tf": str, "pli": int}

    Colonnes ajoutées : robot, actif_clean, tf, pli, pass_label, oos_start.
    """
    dfs: list[pd.DataFrame] = []
    for c in combos:
        robot      = c["robot"]
        actif_clean = SYMBOLS.get(c["actif_tb"], c["actif_tb"].replace(".TB", ""))
        tf         = c["tf"]
        pli        = c["pli"]
        fold       = _FOLD_BY_N.get(pli, {})
        oos_start  = fold.get("forward_date", "").replace(".", "-") or None

        for lbl in _PASS_LABELS:
            df = load_detail_trades(robot, actif_clean, tf, pli, lbl,
                                    output_detail, oos_start)
            if df.empty:
                continue
            df["robot"]       = robot
            df["actif_clean"] = actif_clean
            df["tf"]          = tf
            df["pli"]         = pli
            df["pass_label"]  = lbl
            df["oos_start"]   = oos_start
            dfs.append(df)

    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# Runner batch (générateur — même pattern que mt5_runner.run_batch)
# ══════════════════════════════════════════════════════════════════════════════

def run_representative_passes(
    combos: list[dict],
    output_detail: Path = OUTPUT_DETAIL,
    deposit: float = 100_000.0,
    min_trades_oos: int = 30,
    skip_existing: bool = True,
) -> Iterator[dict]:
    """
    Lance les backtests individuels pour les passes représentatives de chaque combo.

    Chaque combo : {"robot": str, "actif_tb": str, "tf": str, "pli": int}

    Yield dict :
        status  : "running" | "done" | "skipped" | "error"
        label   : "robot/actif/tf/foldN/pass_label"
        detail  : message complémentaire
        total   : nombre total de runs
        index   : index du run courant (0-based)
    """
    # Développer combos × pass_labels → liste plate de runs
    runs: list[dict] = []
    for c in combos:
        actif_clean = SYMBOLS.get(c["actif_tb"], c["actif_tb"].replace(".TB", ""))
        for lbl in _PASS_LABELS:
            runs.append({
                "robot":       c["robot"],
                "actif_tb":    c["actif_tb"],
                "actif_clean": actif_clean,
                "tf":          c["tf"],
                "pli":         c["pli"],
                "pass_label":  lbl,
            })

    total = len(runs)

    for idx, run in enumerate(runs):
        robot      = run["robot"]
        actif_tb   = run["actif_tb"]
        actif_clean= run["actif_clean"]
        tf         = run["tf"]
        pli        = run["pli"]
        pass_label = run["pass_label"]
        fold       = _FOLD_BY_N.get(pli)
        label      = f"{robot}/{actif_clean}/{tf}/fold{pli}/{pass_label}"

        out_csv = detail_csv_path(robot, actif_clean, tf, pli, pass_label, output_detail)

        # ── Skip si déjà présent ──────────────────────────────────────────────
        if skip_existing and out_csv.exists() and out_csv.stat().st_size > 50:
            yield {"status": "skipped", "label": label, "detail": "déjà disponible",
                   "index": idx, "total": total}
            continue

        if fold is None:
            yield {"status": "error", "label": label, "detail": f"Pli {pli} inconnu",
                   "index": idx, "total": total}
            continue

        # ── Sélectionner la passe ─────────────────────────────────────────────
        reps = select_representative_passes(
            robot, actif_tb, tf, pli, min_trades_oos=min_trades_oos
        )
        pass_row = reps.get(pass_label)

        if pass_row is None:
            yield {"status": "skipped", "label": label,
                   "detail": "pas de données WF OOS disponibles (XML manquant ou aucune passe valide)",
                   "index": idx, "total": total}
            continue

        param_values = _param_values_from_row(pass_row)
        if not param_values:
            yield {"status": "error", "label": label, "detail": "aucun paramètre Inp*",
                   "index": idx, "total": total}
            continue

        yield {"status": "running", "label": label, "detail": "",
               "index": idx, "total": total}

        ini_path:  Path | None = None
        tmp_htm:   Path | None = None
        dummy_fwd: Path | None = None
        start_ts   = _time.time()
        try:
            # 1 — Écrire le .set avec paramètres fixés
            set_bytes = _build_fixed_set(robot, param_values)
            set_dest  = MT5_PROFILES_TESTER / EA_CONFIG[robot]["set"]
            MT5_PROFILES_TESTER.mkdir(parents=True, exist_ok=True)
            set_dest.write_bytes(set_bytes)

            # 2 — Générer l'INI single-run
            temp_stem = f"_single_{robot}_{actif_clean}_{tf}_fold{pli}_{pass_label}"
            ini_path, tmp_htm = _generate_single_ini(
                robot, actif_tb, tf, fold, temp_stem, deposit
            )
            dummy_fwd = MT5_FILES / f"{temp_stem}.forward.xml"

            # 3 — Lancer MT5 et attendre la fin
            # poll_interval_s=3 et post_exit_wait_s=3 : single runs courts,
            # pas besoin des 15s de marge conçus pour les optimisations WF multi-heures
            launch_and_wait(ini_path, tmp_htm, dummy_fwd,
                            timeout_s=1_800, poll_interval_s=3, post_exit_wait_s=3)

            # 4 — Trouver le fichier produit (extension et chemin variables selon la version MT5)
            result_file, diag = _find_mt5_report(temp_stem, start_ts)

            if result_file is None:
                yield {"status": "error", "label": label,
                       "detail": diag,
                       "index": idx, "total": total}
                continue

            # 5 — Parser (HTML pour Optimization=0)
            df_trades = _parse_mt5_htm(result_file)

            # 6 — Sauvegarder en CSV (même si 0 trades : stratégie inactive sur ce combo)
            out_csv.parent.mkdir(parents=True, exist_ok=True)
            df_trades.to_csv(str(out_csv), index=False)

            n_tr = len(df_trades)
            yield {"status": "done", "label": label,
                   "detail": f"{n_tr} trade(s) → {out_csv.name}" if n_tr else "0 trade (stratégie inactive sur ce combo)",
                   "index": idx, "total": total}

        except Exception as exc:
            yield {"status": "error", "label": label, "detail": str(exc),
                   "index": idx, "total": total}

        finally:
            for leftover in (ini_path, tmp_htm, dummy_fwd):
                if leftover is not None and leftover.exists():
                    leftover.unlink(missing_ok=True)
