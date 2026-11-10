"""
stock_market_expert_bd — Portable Bootstrap & Self-Healing Engine.
Executed when user triggers 'ready' on any machine.
Checks dependencies, database integrity, Git LFS pointers, and runs self-healing recovery.
"""

import os
import sys
import gzip
import shutil
import sqlite3
import subprocess
from pathlib import Path

# Fix Windows stdout encoding
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
PROC_DIR = BASE_DIR / "data" / "processed"
DB_PATH = PROC_DIR / "dse.db"
DB_GZ_PATH = PROC_DIR / "dse.db.gz"
REQ_PATH = BASE_DIR / "requirements.txt"
SCRIPTS_DIR = BASE_DIR / "scripts"

def log(msg: str):
    print(f"[READY] {msg}", flush=True)

def check_dependencies():
    log("Checking Python dependencies...")
    required = ["requests", "bs4", "lxml", "matplotlib", "pandas", "bdshare", "pdfplumber"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        log(f"Missing packages detected: {missing}. Installing from requirements.txt...")
        cmd = [sys.executable, "-m", "pip", "install", "-r", str(REQ_PATH)]
        res = subprocess.run(cmd)
        if res.returncode != 0:
            log("Warning: Pip install encountered issues. Proceeding...")
        else:
            log("Dependencies successfully installed.")
    else:
        log("All Python dependencies verified.")

def verify_and_restore_database():
    log("Verifying SQLite database integrity...")
    PROC_DIR.mkdir(parents=True, exist_ok=True)

    needs_restore = False
    if not DB_PATH.exists():
        log(f"{DB_PATH.name} not found.")
        needs_restore = True
    elif DB_PATH.stat().st_size < 10000:
        # Likely an unpulled Git LFS pointer file
        with open(DB_PATH, "rb") as f:
            header = f.read(100)
            if b"oid sha256" in header or b"version https://git-lfs" in header:
                log("Detected Git LFS pointer instead of binary database.")
                needs_restore = True

    if not needs_restore:
        # Check SQLite readability
        try:
            conn = sqlite3.connect(DB_PATH, timeout=30.0)
            conn.execute("PRAGMA busy_timeout = 30000;")
            cur = conn.cursor()
            p_count = cur.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
            f_count = cur.execute("SELECT COUNT(*) FROM fundamentals").fetchone()[0]
            conn.close()
            log(f"Database valid. Found {p_count:,} price bars, {f_count} fundamental records.")
            return True
        except Exception as e:
            log(f"Database corrupted or unreadable ({e}). Triggering restore...")
            needs_restore = True

    # Restoration Attempt 1: Decompress dse.db.gz
    if DB_GZ_PATH.exists() and DB_GZ_PATH.stat().st_size > 10000:
        log(f"Restoring database from compressed archive ({DB_GZ_PATH.name})...")
        try:
            with gzip.open(DB_GZ_PATH, "rb") as f_in, open(DB_PATH, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            log("Database successfully decompressed and restored.")
            return True
        except Exception as e:
            log(f"Gzip restore failed: {e}")

    # Restoration Attempt 2: Git LFS pull
    log("Attempting Git LFS pull...")
    try:
        subprocess.run(["git", "lfs", "pull"], cwd=str(BASE_DIR), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if DB_PATH.exists() and DB_PATH.stat().st_size > 1000000:
            log("Git LFS pull successful.")
            return True
    except Exception:
        pass

    # Restoration Attempt 3: Deterministic rebuild from raw snapshots
    log("Rebuilding database from raw snapshots using rebuild_database.py...")
    try:
        cmd = [sys.executable, str(SCRIPTS_DIR / "rebuild_database.py")]
        res = subprocess.run(cmd, cwd=str(BASE_DIR))
        if res.returncode == 0:
            log("Database rebuild complete.")
            return True
    except Exception as e:
        log(f"Rebuild failed: {e}")

    return False

def verify_configs():
    log("Verifying configuration registries...")
    configs = ["sectors.json", "thresholds.json", "company_names.json", "company_leadership.json", "company_registry_12factor.json"]
    for c in configs:
        p = BASE_DIR / "config" / c
        if not p.exists():
            log(f"Warning: Config file {c} missing.")
    log("Configs verified.")


def verify_user_templates():
    log("Verifying user profile and portfolio templates...")
    port_dir = BASE_DIR / "data" / "portfolio"
    port_dir.mkdir(parents=True, exist_ok=True)
    port_file = port_dir / "portfolio.json"
    port_tmpl = port_dir / "portfolio.template.json"

    if not port_file.exists() and port_tmpl.exists():
        shutil.copyfile(port_tmpl, port_file)
        log("Initialized clean local portfolio.json from template.")

    user_dir = BASE_DIR / "data" / "users" / "default_user"
    user_dir.mkdir(parents=True, exist_ok=True)
    prof_file = user_dir / "profile.json"
    prof_tmpl = BASE_DIR / "data" / "users" / "profile.template.json"

    if not prof_file.exists() and prof_tmpl.exists():
        shutil.copyfile(prof_tmpl, prof_file)
        log("Initialized clean local profile.json from template.")

    cfg_file = BASE_DIR / "config" / "profile.json"
    cfg_tmpl = BASE_DIR / "config" / "profile.template.json"
    if not cfg_file.exists() and cfg_tmpl.exists():
        shutil.copyfile(cfg_tmpl, cfg_file)
        log("Initialized clean local config/profile.json from template.")

    # Check and configure user preference if not set
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        from user_manager import prompt_user_customization
        prof = prompt_user_customization(force_prompt=False)
        tier = prof.get("halal_tier", "off")
        log(f"Customization preference active: {tier.upper()} stock mode.")
    except Exception as e:
        log(f"Preference check note: {e}")

def run_bootstrap():
    print("=" * 80)
    print("🚀 stock_market_expert_bd — PORTABLE MACHINE BOOTSTRAP ('READY')")
    print("=" * 80)

    # 1. Check Python dependencies
    check_dependencies()

    # 2. Check/Restore database
    db_ok = verify_and_restore_database()

    # 3. Verify configs & user templates
    verify_configs()
    verify_user_templates()
    try:
        subprocess.run(["git", "config", "core.hooksPath", ".githooks"], cwd=str(BASE_DIR), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    # 4. Live Market Sync & Missed Date Ingestion
    log("Synchronizing live market prices & backfilling missed dates...")
    try:
        sys.path.insert(0, str(SCRIPTS_DIR))
        from live_market_sync import sync_live_market
        sync_live_market(verbose=True)
    except Exception as e:
        log(f"Live market sync note: {e}")

    print("\n" + "=" * 80)
    if db_ok:
        print("✅ SYSTEM STATUS: FULLY ARMED & READY ON THIS MACHINE")
    else:
        print("⚠️ SYSTEM STATUS: READY WITH BASIC DEFAULTS (Run 'python main.py refresh' to populate)")
    print("=" * 80)
    print("\nQuick Commands Available:")
    print("  * 'python main.py status'    -> System status & portfolio audit")
    print("  * 'python main.py config'    -> Configure stock universe preferences (Regular vs Halal)")
    print("  * 'python main.py alpha'     -> Run daily statistical alpha cycle")
    print("  * 'python main.py scan'      -> Directional Rise/Fall predictions")
    print("  * 'python main.py best2'     -> 12-factor Graham/Buffett screener")
    print("  * 'python main.py plan 2000' -> Capital deployment plan\n")

if __name__ == "__main__":
    run_bootstrap()
