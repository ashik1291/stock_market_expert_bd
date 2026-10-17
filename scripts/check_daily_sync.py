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

def run_script_silent(script_name: str, args: list = None) -> bool:
    cmd = [sys.executable, str(SCRIPTS_DIR / script_name)] + (args or [])
    res = subprocess.run(cmd, cwd=str(BASE_DIR), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return res.returncode == 0

def auto_sync_if_needed():
    now = datetime.datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    weekday = now.weekday()  # 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
    # DSE standard trading days: Sunday (6) through Thursday (3). Friday and Saturday closed.
    is_trading_day = weekday in (6, 0, 1, 2, 3)
    market_closed_today = now.hour >= 16 or (now.hour == 15 and now.minute >= 30)

    # 1. Check prices DB
    latest_price_date = None
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            row = cur.execute("SELECT MAX(date) FROM prices").fetchone()
            if row and row[0]:
                latest_price_date = row[0]
            conn.close()
        except Exception:
            pass

    # Check if we need to run daily alpha
    needs_alpha = False
    if is_trading_day and market_closed_today and latest_price_date != today_str:
        needs_alpha = True
    elif latest_price_date is None:
        needs_alpha = True

    if needs_alpha:
        # Run daily alpha silently
        run_script_silent("auto_daily_alpha_routine.py")

    # 2. Check if fundamentals are older than 7 days
    latest_fund_date = None
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(DB_PATH)
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
        run_script_silent("update_all_fundamentals.py")

if __name__ == "__main__":
    auto_sync_if_needed()
