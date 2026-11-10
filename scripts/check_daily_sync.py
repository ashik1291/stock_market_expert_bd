"""
Autonomous Daily Synchronization & Heartbeat Checker.
Runs silently in the background on the first interaction of each day.
Checks:
  1. Has today's (or latest trading day's) price & news data been ingested?
  2. Has the forward ledger stepped for the latest date?
  3. Has a fundamentals refresh happened within the last 7 days?
If stale, executes the required pipeline steps silently.
"""

import sys
import json
import sqlite3
import datetime
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BASE_DIR / "scripts"
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"

def run_script_silent(script_name: str, args: list = None, async_proc: bool = False) -> bool:
    cmd = [sys.executable, str(SCRIPTS_DIR / script_name)] + (args or [])
    if async_proc:
        try:
            subprocess.Popen(cmd, cwd=str(BASE_DIR), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            return False
    try:
        res = subprocess.run(cmd, cwd=str(BASE_DIR), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45.0)
        return res.returncode == 0
    except Exception:
        return False

def auto_sync_if_needed():
    # 1. Live market synchronization & gap backfilling
    try:
        sys.path.insert(0, str(SCRIPTS_DIR))
        from live_market_sync import get_sync_status, sync_live_market
        status = get_sync_status()
        if status.get("is_stale"):
            sync_live_market(verbose=False)
    except Exception as e:
        pass

    # 2. Check if fundamentals are older than 7 days
    latest_fund_date = None
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(DB_PATH, timeout=30.0)
            conn.execute("PRAGMA busy_timeout = 30000;")
            cur = conn.cursor()
            row = cur.execute("SELECT MAX(snapshot_date) FROM fundamentals_pit").fetchone()
            if row and row[0]:
                latest_fund_date = row[0]
            conn.close()
        except Exception:
            pass

    needs_fund_harvest = False
    if latest_fund_date:
        try:
            d = datetime.date.fromisoformat(latest_fund_date[:10])
            if (datetime.date.today() - d).days >= 7:
                needs_fund_harvest = True
        except Exception:
            pass
    else:
        needs_fund_harvest = True

    if needs_fund_harvest:
        run_script_silent("update_all_fundamentals.py", async_proc=True)

    # 3. Check if month-end rebalance plan needs generation (runs between 28th and last day of month)
    today = datetime.date.today()
    if today.day >= 28:
        rebalance_report_dir = BASE_DIR / "reports" / "monthly"
        rebalance_report_dir.mkdir(parents=True, exist_ok=True)
        month_order_file = rebalance_report_dir / f"{today.strftime('%Y-%m')}_rebalance_order.md"
        # Generate if not created today
        if not month_order_file.exists():
            try:
                from monthly_rebalance_engine import calculate_monthly_deployment
                res = calculate_monthly_deployment(2000.0)
                with open(month_order_file, "w", encoding="utf-8") as f:
                    f.write(res["report_markdown"])
            except Exception:
                pass

if __name__ == "__main__":
    auto_sync_if_needed()
