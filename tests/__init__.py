# tests/__init__.py
"""
Test Suite Self-Healing Bootstrap Guard (INV-8).
Ensures that if tests are executed on a fresh clone (e.g. GitHub Actions runner)
where dse.db and portfolio.json are omitted from git due to .gitignore,
they are immediately and automatically materialized from dse.db.gz and portfolio.template.json.
"""

import gzip
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PROC_DIR = BASE_DIR / "data" / "processed"
DB_PATH = PROC_DIR / "dse.db"
DB_GZ_PATH = PROC_DIR / "dse.db.gz"

PORT_DIR = BASE_DIR / "data" / "portfolio"
PORT_FILE = PORT_DIR / "portfolio.json"
PORT_TMPL = PORT_DIR / "portfolio.template.json"

USER_DIR = BASE_DIR / "data" / "users" / "default_user"
PROF_FILE = USER_DIR / "profile.json"
PROF_TMPL = BASE_DIR / "data" / "users" / "profile.template.json"

def ensure_test_environment():
    """Restores database and user templates if missing."""
    PROC_DIR.mkdir(parents=True, exist_ok=True)
    if (not DB_PATH.exists() or DB_PATH.stat().st_size < 10000) and DB_GZ_PATH.exists():
        with gzip.open(DB_GZ_PATH, "rb") as f_in, open(DB_PATH, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

    PORT_DIR.mkdir(parents=True, exist_ok=True)
    if not PORT_FILE.exists() and PORT_TMPL.exists():
        shutil.copyfile(PORT_TMPL, PORT_FILE)

    USER_DIR.mkdir(parents=True, exist_ok=True)
    if not PROF_FILE.exists() and PROF_TMPL.exists():
        shutil.copyfile(PROF_TMPL, PROF_FILE)

ensure_test_environment()

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from _isolation import real_data_fingerprint as _fp  # noqa: E402

# Compared by tests/test_zzz_real_data_untouched.py, which discover runs last.
REAL_DATA_FINGERPRINT_AT_START = _fp()
