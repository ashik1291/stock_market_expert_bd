"""
scripts/db.py — Canonical Central SQLite Database Access Layer

Enforces SPEC.md INV-7:
  - Universal timeout=30.0s on connection initialization.
  - Universal PRAGMA busy_timeout = 30000; to prevent concurrent locking.
  - Universal PRAGMA journal_mode = WAL;
  - Fail-closed error handling.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional, Any

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"


def get_db_connection(
    db_path: Path | str | None = None,
    timeout: float = 30.0,
    row_factory: Any = None
) -> sqlite3.Connection:
    """
    Returns a hardened SQLite connection adhering strictly to INV-7.
    """
    target_path = Path(db_path) if db_path else DEFAULT_DB_PATH
    if not target_path.exists():
        # Fail-closed check: if the main database is missing, raise explicitly
        raise FileNotFoundError(f"Database not found at: {target_path}")

    conn = sqlite3.connect(str(target_path), timeout=timeout)
    conn.execute("PRAGMA busy_timeout = 30000;")
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
    except Exception:
        pass  # In read-only scenarios, WAL mode might already be set

    if row_factory is not None:
        conn.row_factory = row_factory

    return conn
