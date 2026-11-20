"""Test isolation helpers: tests must never mutate the real database or the user's ledgers."""

import contextlib
import hashlib
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REAL_DB = ROOT / "data" / "processed" / "dse.db"

# Files whose content must be identical before and after the whole suite.
PROTECTED_FILES = [
    ROOT / "data" / "users" / "default_user" / "portfolio.json",
    ROOT / "data" / "portfolio" / "portfolio.json",
    ROOT / "data" / "portfolio" / "forward_test_ledger_v2.json",
    ROOT / "data" / "learning" / "model_registry.json",
    ROOT / "data" / "learning" / "prediction_ledger.json",
]
# Tables whose (row count, max key) must be identical before and after the suite.
PROTECTED_TABLES = {
    "prices": "MAX(date)",
    "corporate_actions": "MAX(record_date)",
    "fundamentals_pit": "MAX(tradable_date)",
    "trading_calendar": "SUM(is_trading_day)",
    "portfolio_dividend_credits": "MAX(id)",
}


def real_data_fingerprint() -> dict:
    fp = {}
    for p in PROTECTED_FILES:
        fp[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
    if REAL_DB.exists():
        conn = sqlite3.connect(f"file:{REAL_DB}?mode=ro", uri=True)
        try:
            for t, agg in PROTECTED_TABLES.items():
                try:
                    fp[f"db:{t}"] = conn.execute(f"SELECT COUNT(*), {agg} FROM {t}").fetchone()
                except sqlite3.Error:
                    fp[f"db:{t}"] = None
        finally:
            conn.close()
    return fp


@contextlib.contextmanager
def temp_db_copy():
    """Yield the path of a consistent private copy of dse.db (SQLite backup API, WAL-safe)."""
    tmp = tempfile.mkdtemp(prefix="dse_test_db_")
    dst_path = os.path.join(tmp, "dse.db")
    src = sqlite3.connect(f"file:{REAL_DB}?mode=ro", uri=True)
    dst = sqlite3.connect(dst_path)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    try:
        yield Path(dst_path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@contextlib.contextmanager
def isolated_learning_files():
    """Point the evaluator and learning engine at private copies of the prediction ledger and weights."""
    import multi_horizon_evaluator as mh
    import reinforcement_learning_engine as rl
    tmp = Path(tempfile.mkdtemp(prefix="dse_test_learning_"))
    learn = ROOT / "data" / "learning"
    for name in ("prediction_ledger.json", "model_weights.json", "phase2_meta.json", "prediction_ledger_epoch1_invalid.json"):
        if (learn / name).exists():
            shutil.copyfile(learn / name, tmp / name)
    saved = {(mod, attr): getattr(mod, attr) for mod, attr in
             [(mh, "LEDGER_PATH"), (mh, "WEIGHTS_PATH"), (rl, "LEDGER_PATH"), (rl, "WEIGHTS_PATH"),
              (rl, "META_PATH"), (rl, "ARCHIVE_PATH")]}
    for (mod, attr), path in saved.items():
        setattr(mod, attr, tmp / Path(path).name)
    try:
        yield tmp
    finally:
        for (mod, attr), path in saved.items():
            setattr(mod, attr, path)
        shutil.rmtree(tmp, ignore_errors=True)
