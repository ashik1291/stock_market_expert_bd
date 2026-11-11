"""
scripts/push_db_update.py — Master Database Baseline Updater & Git Sync

Compresses the active SQLite database (data/processed/dse.db) into data/processed/dse.db.gz,
verifies integrity and system invariants, and pushes the refreshed monthly baseline to GitHub.

Usage:
    python scripts/push_db_update.py [--dry-run]
    python main.py push-db
"""

import os
import sys
import gzip
import shutil
import sqlite3
import argparse
import subprocess
from pathlib import Path

# Enforce UTF-8 encoding on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
PROC_DIR = BASE_DIR / "data" / "processed"
DB_PATH = PROC_DIR / "dse.db"
GZ_PATH = PROC_DIR / "dse.db.gz"
GZ_TMP = PROC_DIR / "dse.db.gz.tmp"


def log(msg: str):
    print(f"[DB-PUSH] {msg}", flush=True)


def push_db_update(dry_run: bool = False) -> bool:
    print("=" * 80)
    print("📦 DSE MASTER DATABASE BASELINE COMPRESSION & GIT SYNC")
    print("=" * 80)

    # Step 1: Health check on active SQLite DB
    if not DB_PATH.exists():
        log(f"❌ Error: Active database not found at {DB_PATH}")
        return False

    log("Auditing active SQLite database...")
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        cur = conn.cursor()
        max_date = cur.execute("SELECT MAX(date) FROM prices").fetchone()[0]
        total_bars = cur.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
        total_co = cur.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        total_pit = cur.execute("SELECT COUNT(*) FROM fundamentals_pit").fetchone()[0]
        conn.close()
    except Exception as e:
        log(f"❌ Database read failed: {e}")
        return False

    raw_size_mb = DB_PATH.stat().st_size / (1024 * 1024)
    log(f"Active DB Size: {raw_size_mb:.2f} MB")
    log(f"Latest Price Date: {max_date}")
    log(f"Total Price Bars: {total_bars:,}")
    log(f"Listed Companies: {total_co}")
    log(f"Verified PIT Disclosures: {total_pit:,}")

    # Step 2: Optimal Gzip Compression
    log("Compressing active database into dse.db.gz (gzip level 9)...")
    try:
        with open(DB_PATH, "rb") as f_in, gzip.open(GZ_TMP, "wb", compresslevel=9) as f_out:
            shutil.copyfileobj(f_in, f_out)
        
        # Atomic rename
        if GZ_PATH.exists():
            GZ_PATH.unlink()
        GZ_TMP.rename(GZ_PATH)
    except Exception as e:
        log(f"❌ Compression failed: {e}")
        if GZ_TMP.exists():
            GZ_TMP.unlink()
        return False

    gz_size_mb = GZ_PATH.stat().st_size / (1024 * 1024)
    compression_ratio = (1.0 - (GZ_PATH.stat().st_size / DB_PATH.stat().st_size)) * 100
    log(f"Compressed Archive: {gz_size_mb:.2f} MB (Saved {compression_ratio:.1f}% space)")

    # Step 3: Verify compressed archive integrity
    log("Verifying compressed archive integrity...")
    try:
        with gzip.open(GZ_PATH, "rb") as f_test:
            header = f_test.read(100)
            if not header.startswith(b"SQLite format 3"):
                log("❌ Header check failed: Not a valid SQLite database header.")
                return False
        log("✅ Archive integrity verified (valid SQLite format 3).")
    except Exception as e:
        log(f"❌ Archive verification failed: {e}")
        return False

    # Step 4: Run SPEC invariants guard
    log("Running Spec Conformance Guard (INV-1 through INV-8)...")
    res_guard = subprocess.run([sys.executable, str(BASE_DIR / "scripts" / "spec_guard.py")], cwd=str(BASE_DIR))
    if res_guard.returncode != 0:
        log("❌ Spec Conformance Guard failed. Aborting push to prevent broken state.")
        return False

    # Step 5: Check Git Status
    log("Checking Git status for dse.db.gz...")
    git_status = subprocess.run(["git", "status", "--porcelain", str(GZ_PATH)], cwd=str(BASE_DIR), capture_output=True, text=True)
    
    if not git_status.stdout.strip():
        log("ℹ️ No changes detected: dse.db.gz is already identical to Git HEAD.")
        return True

    if dry_run:
        log(f"🏁 [DRY-RUN] dse.db.gz successfully rebuilt ({gz_size_mb:.2f} MB). Skipping Git commit & push.")
        return True

    # Step 6: Commit and Push to GitHub
    commit_msg = f"chore(data): refresh master database baseline archive (as of {max_date}, {total_bars:,} bars)"
    log(f"Staging and committing: '{commit_msg}'...")
    
    try:
        subprocess.run(["git", "add", str(GZ_PATH)], cwd=str(BASE_DIR), check=True)
        subprocess.run(["git", "config", "user.name", "Ashikur Rahman Bhuiyan"], cwd=str(BASE_DIR), check=True)
        subprocess.run(["git", "config", "user.email", "ashik1291@yahoo.com"], cwd=str(BASE_DIR), check=True)
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=str(BASE_DIR), check=True)
        
        log("Pushing to origin/master...")
        push_res = subprocess.run(["git", "push", "origin", "master"], cwd=str(BASE_DIR), capture_output=True, text=True)
        if push_res.returncode == 0:
            print("=" * 80)
            log(f"✅ SUCCESS: Master database archive successfully updated and pushed to GitHub!")
            log(f"   Baseline Date: {max_date} | Size: {gz_size_mb:.2f} MB | Total Bars: {total_bars:,}")
            print("=" * 80)
            return True
        else:
            log(f"❌ Git push failed: {push_res.stderr}")
            return False
    except Exception as e:
        log(f"❌ Git operation failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Compress and push latest DSE master database baseline.")
    parser.add_argument("--dry-run", action="store_true", help="Compress and verify without committing or pushing.")
    args = parser.parse_args()

    success = push_db_update(dry_run=args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
