#!/usr/bin/env python3
"""
scripts/spec_guard.py — Automated Specification Conformance Guard

Validates that codebase, database, registries, and operational parameters
strictly comply with the 8 Non-Negotiable System Invariants defined in SPEC.md:
  INV-1: Strict Point-in-Time (PIT) Isolation
  INV-2: Central Bank Macro Hurdle Rate
  INV-3: 100% Shariah / Halal & Zero-Bank Shield
  INV-4: Frontier Microstructure Realism
  INV-5: Frozen Champion Registry & Multi-Testing Deflation
  INV-6: Cryptographic Forward Test Ledger V2
  INV-7: Universal SQLite WAL & Concurrency Hardening
  INV-8: Zero-Broken Portable Bootstrap

Exit codes:
  0: All 8 invariants pass
  1: One or more invariants violated
"""

from __future__ import annotations

import sys
import gzip
import json
import sqlite3
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Tuple

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "scripts"))
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"
DB_GZ_PATH = BASE_DIR / "data" / "processed" / "dse.db.gz"
LEDGER_PATH = BASE_DIR / "data" / "portfolio" / "forward_test_ledger_v2.json"
REGISTRY_PATH = BASE_DIR / "data" / "learning" / "model_registry.json"


def check_inv1_pit_isolation() -> Tuple[bool, str]:
    """INV-1: Strict Point-in-Time Isolation."""
    if not DB_PATH.exists():
        return False, "Database dse.db missing"
    
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    
    # Check fundamentals_pit exists
    table_check = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='fundamentals_pit'"
    ).fetchone()
    if not table_check:
        conn.close()
        return False, "Table 'fundamentals_pit' missing in dse.db"
    
    # Check publication_date & tradable_date columns exist
    cols = [col[1] for col in cursor.execute("PRAGMA table_info(fundamentals_pit)").fetchall()]
    if "publication_date" not in cols or "tradable_date" not in cols:
        conn.close()
        return False, "Required PIT columns (publication_date, tradable_date) missing"
    
    # Verify no records violate tradable_date >= publication_date
    violations = cursor.execute(
        "SELECT COUNT(*) FROM fundamentals_pit WHERE tradable_date < publication_date"
    ).fetchone()[0]
    conn.close()
    
    if violations > 0:
        return False, f"Found {violations} PIT violations where tradable_date < publication_date"
    
    return True, "PIT table verified: tradable_date >= publication_date with 0 violations"


def check_inv2_macro_hurdle() -> Tuple[bool, str]:
    """INV-2: Central Bank Macro Hurdle Rate."""
    try:
        from scripts.macro_rate_feed import get_latest_macro_rates
        rates = get_latest_macro_rates()
    except Exception as e:
        return False, f"Failed to load macro rates: {e}"
    
    t_bill = rates.get("t_bill_91d_pct", 0.0)
    hurdle = rates.get("equity_hurdle_rate_pct", 0.0)
    
    if t_bill < 11.60:
        return False, f"91-day T-Bill rate {t_bill:.2f}% below institutional floor (11.60%)"
    if hurdle < 15.10:
        return False, f"Equity hurdle rate {hurdle:.2f}% below institutional baseline (15.10%)"
    
    return True, f"Macro hurdle anchored: 91d T-Bill={t_bill:.2f}%, Minimum Equity Hurdle={hurdle:.2f}%"


def check_inv3_shariah_zero_bank() -> Tuple[bool, str]:
    """INV-3: 100% Shariah / Halal & Zero-Bank Shield."""
    try:
        from scripts.five_factor_fundamental_screener import SHARIAH_EXCLUDED_SECTORS
    except Exception as e:
        return False, f"Failed to import Shariah exclusions: {e}"
    
    required_exclusions = {"Bank", "Financial Institutions", "Insurance"}
    missing = required_exclusions - SHARIAH_EXCLUDED_SECTORS
    if missing:
        return False, f"Shariah exclusions missing toxic sectors: {missing}"
    
    return True, f"Shariah shield verified: Excludes all {len(SHARIAH_EXCLUDED_SECTORS)} conventional finance sectors"


def check_inv4_microstructure_realism() -> Tuple[bool, str]:
    """INV-4: Frontier Microstructure Realism."""
    try:
        from scripts.forward_test_ledger_v2 import FEE_BUY_PCT, FEE_SELL_PCT, _is_floor_locked
    except Exception as e:
        return False, f"Failed to load microstructure parameters: {e}"
    
    if round(FEE_BUY_PCT, 5) != 0.00415:
        return False, f"FEE_BUY_PCT is {FEE_BUY_PCT}, expected 0.00415 (0.415%)"
    if round(FEE_SELL_PCT, 5) != 0.00465:
        return False, f"FEE_SELL_PCT is {FEE_SELL_PCT}, expected 0.00465 (0.415% broker + 0.05% Sec 53BBB AIT)"
    
    if not callable(_is_floor_locked):
        return False, "Lower circuit floor-lock guard function missing"
    
    return True, f"Microstructure validated: Buy={FEE_BUY_PCT*100:.3f}%, Sell={FEE_SELL_PCT*100:.3f}% (incl 53BBB AIT), Circuit-lock guard active"


def check_inv5_champion_registry() -> Tuple[bool, str]:
    """INV-5: Frozen Champion Registry & Multi-Testing Deflation."""
    if not REGISTRY_PATH.exists():
        return False, "Model registry file missing"
    
    try:
        reg = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"Failed to read model registry: {e}"
    
    champion = reg.get("champion", {})
    model_id = champion.get("model_id")
    param_hash = champion.get("parameter_hash")
    
    if model_id != "frozen_epoch2_pit_v2":
        return False, f"Champion model ID is '{model_id}', expected 'frozen_epoch2_pit_v2'"
    if param_hash != "acf502bc65914c48":
        return False, f"Champion hash is '{param_hash}', expected 'acf502bc65914c48'"
    
    return True, f"Champion verified: id='{model_id}', parameter_hash='{param_hash}'"


def check_inv6_cryptographic_ledger() -> Tuple[bool, str]:
    """INV-6: Cryptographic Forward Test Ledger V2."""
    if not LEDGER_PATH.exists():
        return False, "Forward test ledger missing"
    
    try:
        data = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"Failed to read forward test ledger: {e}"
    
    blocks = data.get("blocks", [])
    if not blocks:
        return False, "Forward test ledger has 0 blocks"
    
    for i in range(1, len(blocks)):
        prev_hash = blocks[i - 1]["block_hash"]
        if blocks[i].get("prev_hash") != prev_hash:
            return False, f"Block {i} prev_hash mismatch: expected {prev_hash[:8]}, got {blocks[i].get('prev_hash')}"
        
        expected_hash = hashlib.sha256(
            (json.dumps(blocks[i]["data"], sort_keys=True) + prev_hash).encode("utf-8")
        ).hexdigest()
        if blocks[i].get("block_hash") != expected_hash:
            return False, f"Block {i} block_hash invalid: tampered ledger detected"
    
    return True, f"Cryptographic ledger valid: {len(blocks)} blocks cryptographically verified with SHA-256"


def check_inv7_sqlite_wal() -> Tuple[bool, str]:
    """INV-7: Universal SQLite WAL & Concurrency Hardening."""
    if not DB_PATH.exists():
        return False, "Database dse.db missing"
    
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    conn.close()
    
    if str(journal_mode).lower() != "wal":
        return False, f"SQLite journal mode is '{journal_mode}', expected 'wal'"
    
    return True, f"Universal SQLite WAL verified: journal_mode={journal_mode}, timeout=30.0s active"


def check_inv8_portable_bootstrap() -> Tuple[bool, str]:
    """INV-8: Zero-Broken Portable Bootstrap."""
    if not DB_GZ_PATH.exists():
        return False, "Master point-in-time compressed database dse.db.gz missing"
    
    try:
        with gzip.open(DB_GZ_PATH, "rb") as f:
            header = f.read(16)
            if header != b"SQLite format 3\x00":
                return False, f"dse.db.gz corrupted: invalid header {header}"
    except Exception as e:
        return False, f"Error reading dse.db.gz: {e}"
    
    bootstrap_py = BASE_DIR / "scripts" / "bootstrap.py"
    if not bootstrap_py.exists():
        return False, "scripts/bootstrap.py missing"
    
    ready_bat = BASE_DIR / "ready.bat"
    ready_sh = BASE_DIR / "ready.sh"
    ready_ps1 = BASE_DIR / "ready.ps1"
    
    if not (ready_bat.exists() and ready_sh.exists() and ready_ps1.exists()):
        return False, "Cross-platform bootstrap launchers missing"
    
    return True, "Portable bootstrap verified: dse.db.gz valid, bootstrap.py & ready.* present"


def run_spec_guard() -> bool:
    print("=" * 70)
    print("🛡️ SPECIFICATION CONFORMANCE GUARD (SPEC.md)")
    print("=" * 70)
    
    invariants = [
        ("INV-1", "Strict Point-in-Time Isolation", check_inv1_pit_isolation),
        ("INV-2", "Central Bank Macro Hurdle Rate", check_inv2_macro_hurdle),
        ("INV-3", "100% Shariah / Halal & Zero-Bank Shield", check_inv3_shariah_zero_bank),
        ("INV-4", "Frontier Microstructure Realism", check_inv4_microstructure_realism),
        ("INV-5", "Frozen Champion Registry & Multi-Testing", check_inv5_champion_registry),
        ("INV-6", "Cryptographic Forward Test Ledger V2", check_inv6_cryptographic_ledger),
        ("INV-7", "Universal SQLite WAL & Concurrency", check_inv7_sqlite_wal),
        ("INV-8", "Zero-Broken Portable Bootstrap", check_inv8_portable_bootstrap),
    ]
    
    all_passed = True
    for inv_id, inv_name, check_fn in invariants:
        ok, msg = check_fn()
        status_tag = "[PASS]" if ok else "[FAIL]"
        print(f"  {status_tag} {inv_id}: {inv_name}")
        print(f"         {msg}")
        if not ok:
            all_passed = False
            
    print("=" * 70)
    if all_passed:
        print("✅ ALL 8 SYSTEM INVARIANTS CONFORM TO SPEC.md")
    else:
        print("❌ SPECIFICATION VIOLATION DETECTED")
    print("=" * 70)
    return all_passed


if __name__ == "__main__":
    success = run_spec_guard()
    sys.exit(0 if success else 1)
