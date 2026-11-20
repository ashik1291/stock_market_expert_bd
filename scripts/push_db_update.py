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
SNAP_TMP = PROC_DIR / "dse.db.push_snapshot.tmp"
GZ_PREV = PROC_DIR / "dse.db.gz.prev.tmp"

sys.path.insert(0, str(BASE_DIR / "scripts"))


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

    # Never publish a baseline that fails the data invariants: every fresh clone would inherit it.
    gate = subprocess.run([sys.executable, str(BASE_DIR / "scripts" / "integrity_harness.py"), "--data-gate"], cwd=str(BASE_DIR))
    if gate.returncode != 0:
        log("❌ Data integrity gate failed; dse.db.gz NOT regenerated.")
        return False

    # Backup API gives a transactionally consistent copy even if another process writes meanwhile.
    log("Snapshotting database and compressing (gzip level 9)...")
    try:
        if SNAP_TMP.exists():
            SNAP_TMP.unlink()
        src = sqlite3.connect(DB_PATH, timeout=30.0)
        src.execute("PRAGMA busy_timeout = 30000;")
        dst = sqlite3.connect(SNAP_TMP)
        src.backup(dst)
        src.close()
        dst.execute("PRAGMA journal_mode = DELETE;")
        ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
        from db_guards import missing_data_guards
        missing = missing_data_guards(dst)
        dst.close()
        if ok != "ok" or missing:
            log(f"❌ Snapshot invalid (integrity={ok}, missing guards={missing}); dse.db.gz NOT regenerated.")
            return False
        with open(SNAP_TMP, "rb") as f_in, open(GZ_TMP, "wb") as raw, \
                gzip.GzipFile(filename="dse.db", mode="wb", compresslevel=9, fileobj=raw, mtime=0) as f_out:
            shutil.copyfileobj(f_in, f_out)
        with gzip.open(GZ_TMP, "rb") as f_test:
            if not f_test.read(100).startswith(b"SQLite format 3"):
                raise ValueError("compressed archive does not hold a SQLite database")
        if GZ_PATH.exists():
            os.replace(GZ_PATH, GZ_PREV)
        os.replace(GZ_TMP, GZ_PATH)
    except Exception as e:
        log(f"❌ Snapshot/compression failed: {e}")
        if GZ_TMP.exists():
            GZ_TMP.unlink()
        return False
    finally:
        if SNAP_TMP.exists():
            SNAP_TMP.unlink()

    gz_size_mb = GZ_PATH.stat().st_size / (1024 * 1024)
    compression_ratio = (1.0 - (GZ_PATH.stat().st_size / (raw_size_mb * 1024 * 1024))) * 100
    log(f"Compressed Archive: {gz_size_mb:.2f} MB (Saved {compression_ratio:.1f}% space)")

    log("Running Spec Conformance Guard (INV-1 through INV-8) on the rebuilt archive...")
    if subprocess.run([sys.executable, str(BASE_DIR / "scripts" / "spec_guard.py")], cwd=str(BASE_DIR)).returncode != 0:
        if GZ_PREV.exists():
            os.replace(GZ_PREV, GZ_PATH)
        log("❌ Spec Conformance Guard failed; previous dse.db.gz restored, nothing committed.")
        return False
    if GZ_PREV.exists():
        GZ_PREV.unlink()

    # Step 5: Check Git Status
    log("Checking Git status for dse.db.gz...")
    git_status = subprocess.run(["git", "status", "--porcelain", str(GZ_PATH)], cwd=str(BASE_DIR), capture_output=True, text=True)
    
    if not git_status.stdout.strip():
        log("ℹ️ No changes detected: dse.db.gz is already identical to Git HEAD.")
        return True

    if dry_run:
        log(f"🏁 [DRY-RUN] dse.db.gz successfully rebuilt ({gz_size_mb:.2f} MB). Skipping Git commit & push.")
        return True

    branch = subprocess.run(["git", "branch", "--show-current"], cwd=str(BASE_DIR), capture_output=True, text=True).stdout.strip()
    if branch != "master":
        log(f"❌ On branch '{branch}', not master; archive rebuilt but not committed.")
        return False

    # Step 6: Commit and Push to GitHub
    commit_msg = f"chore(data): refresh master database baseline archive (as of {max_date}, {total_bars:,} bars)"
    log(f"Staging and committing: '{commit_msg}'...")
    
    try:
        subprocess.run(["git", "add", str(GZ_PATH)], cwd=str(BASE_DIR), check=True)
        subprocess.run(["git", "config", "user.name", "Ashikur Rahman Bhuiyan"], cwd=str(BASE_DIR), check=True)
        subprocess.run(["git", "config", "user.email", "ashik1291@yahoo.com"], cwd=str(BASE_DIR), check=True)
        subprocess.run(["git", "commit", "-m", commit_msg, "--", str(GZ_PATH)], cwd=str(BASE_DIR), check=True)
        
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
