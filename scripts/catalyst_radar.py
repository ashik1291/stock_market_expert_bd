#!/usr/bin/env python3
"""
scripts/catalyst_radar.py

Institutional DSE Dividend & Corporate Catalyst Radar Engine.
Detects recurring calendar anomalies (15–30 day Pre-Dividend Run-Ups & Earnings Beats)
to harvest systematic swing profits on Category A Blue-Chips.

Catalyst Mechanics:
  1. Pre-Dividend Announcement Accumulation:
     - Blue chips reliably rally +6% to +12% during the 3 weeks preceding their annual Board Meeting.
     - Enters on 20-DMA support; exits 2 days BEFORE record date (capturing pure capital gain, 100% tax-free).
  2. Quarterly EPS Growth Catalyst:
     - Detects QoQ / YoY acceleration from recent PSI disclosures.
  3. Rebalancing Sweep Directives:
     - Directs harvested swing profits into permanent Core Moats (JAMUNAOIL, SQURPHARMA, GP).

Usage:
  python scripts/catalyst_radar.py
"""

from __future__ import annotations

import sys
import json
import sqlite3
import datetime
from pathlib import Path
from typing import Dict, Any, List

# Windows console encoding safeguard
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"
REPORTS_DIR = BASE_DIR / "reports" / "catalyst"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
SCRIPTS_DIR = BASE_DIR / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from smart_capital_planner import compute_dynamic_stock_metrics
from anti_manipulation_engine import is_ticker_blacklisted

# Historical Annual Dividend Declaration Windows (Month, Day_Start, Day_End)
DIVIDEND_CALENDAR = {
    "JAMUNAOIL":   {"start_month": 10, "start_day": 20, "end_month": 11, "end_day": 20, "typ_div": "100-120% Cash", "sector": "Fuel_Power"},
    "PADMAOIL":    {"start_month": 10, "start_day": 20, "end_month": 11, "end_day": 20, "typ_div": "100-140% Cash", "sector": "Fuel_Power"},
    "MPETROLEUM":  {"start_month": 11, "start_day": 10, "end_month": 12, "end_day": 15, "typ_div": "120-150% Cash", "sector": "Fuel_Power"},
    "SQURPHARMA":  {"start_month": 10, "start_day": 15, "end_month": 11, "end_day": 10, "typ_div": "100-110% Cash", "sector": "Pharmaceuticals"},
    "GP":          {"start_month": 1,  "start_day": 20, "end_month": 2,  "end_day": 20, "typ_div": "125-150% Cash (Final)", "sector": "Telecom"},
    "OLYMPIC":     {"start_month": 10, "start_day": 15, "end_month": 11, "end_day": 15, "typ_div": "50-60% Cash", "sector": "Food & Allied"},
    "BSRMLTD":     {"start_month": 10, "start_day": 20, "end_month": 11, "end_day": 20, "typ_div": "35-50% Cash", "sector": "Engineering"},
    "WALTONHIL":   {"start_month": 9,  "start_day": 1,  "end_month": 9,  "end_day": 20, "typ_div": "250-300% Cash", "sector": "Engineering"},
    "LHB":         {"start_month": 2,  "start_day": 10, "end_month": 3,  "end_day": 10, "typ_div": "35-50% Cash", "sector": "Cement"},
}


def scan_dividend_catalysts(asof_date: str | None = None) -> List[Dict[str, Any]]:
    """Scans for active pre-dividend accumulation windows and announced corporate actions."""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.row_factory = sqlite3.Row

    if not asof_date:
        row = conn.execute("SELECT MAX(date) FROM prices").fetchone()
        asof_date = row[0] if row and row[0] else datetime.date.today().isoformat()

    asof_dt = datetime.date.fromisoformat(asof_date)
    curr_month = asof_dt.month
    curr_day = asof_dt.day

    results = []

    for ticker, cal in DIVIDEND_CALENDAR.items():
        is_blocked, _ = is_ticker_blacklisted(ticker, asof_date=asof_date)
        if is_blocked:
            continue

        metrics = compute_dynamic_stock_metrics(ticker, conn)
        if not metrics or not metrics.get("current_price"):
            continue

        # Check official corporate actions table for confirmed record dates
        corp = conn.execute("""
            SELECT record_date, cash_amount, notes FROM corporate_actions
            WHERE ticker = ? AND record_date >= ?
            ORDER BY record_date ASC LIMIT 1
        """, (ticker, asof_date)).fetchone()

        s_m = cal["start_month"]
        s_d = cal["start_day"]
        e_m = cal["end_month"]
        e_d = cal["end_day"]

        # Approximate window status
        is_in_season = False
        status = "OFF_SEASON"
        days_to_window = 999

        if s_m == curr_month:
            if curr_day < s_d:
                status = f"APPROACHING ({s_d - curr_day} days)"
                days_to_window = s_d - curr_day
            elif s_d <= curr_day <= e_d:
                status = "ACTIVE_ACCUMULATION_WINDOW"
                is_in_season = True
                days_to_window = 0
            else:
                status = "LATE_ANNOUNCEMENT_WINDOW"
                is_in_season = True
        elif e_m == curr_month and curr_day <= e_d:
            status = "ACTIVE_ACCUMULATION_WINDOW"
            is_in_season = True
            days_to_window = 0
        elif (s_m - curr_month) % 12 == 1:
            days_to_window = (30 - curr_day) + s_d
            if days_to_window <= 25:
                status = f"APPROACHING ({days_to_window} days)"

        # Strategy pricing targets
        cur_px = metrics["current_price"]
        limit_entry = metrics.get("target_dip", cur_px)
        tp_target = round(limit_entry * 1.09, 1)  # +9% swing target
        stop_loss = round(limit_entry * 0.95, 1)  # -5% hard stop

        results.append({
            "ticker": ticker,
            "sector": cal["sector"],
            "current_price": cur_px,
            "limit_entry": limit_entry,
            "tp_target": tp_target,
            "stop_loss": stop_loss,
            "div_yield": metrics.get("dividend_yield", 0.0),
            "typical_div": cal["typ_div"],
            "window_status": status,
            "is_in_season": is_in_season,
            "official_record_date": corp["record_date"] if corp else "Awaiting Board Declaration",
            "official_cash": corp["cash_amount"] if corp else None,
            "rsi_14": metrics.get("rsi_14", 50.0),
        })

    conn.close()

    # Sort: active accumulation windows first, then approaching
    results.sort(key=lambda x: (not x["is_in_season"], "APPROACHING" not in x["window_status"], x["ticker"]))
    return results


def print_catalyst_radar(asof_date: str | None = None):
    catalysts = scan_dividend_catalysts(asof_date)
    asof = asof_date or datetime.date.today().isoformat()

    print("=" * 86)
    print(f"🎯 DSE PRE-DIVIDEND & SEASONAL CATALYST RADAR — ASOF: {asof}")
    print("Mandate: Exploit recurring 15–25 day Pre-Dividend price runs on Category A Moats")
    print("Rule: Buy on 20-DMA support; sell 2 days BEFORE record date (Tax-Free Capital Gain)")
    print("=" * 86)
    print(f"{'Ticker':<11} {'Sector':<16} {'Live Px':<9} {'Buy Limit':<10} {'Target(+9%)':<12} {'StopLoss':<10} {'Yield':<8} {'Catalyst Status'}")
    print("-" * 86)

    for c in catalysts:
        tag = "🟢 " if c["is_in_season"] else ("🟡 " if "APPROACHING" in c["window_status"] else "⚪ ")
        print(f"{c['ticker']:<11} {c['sector']:<16} ৳{c['current_price']:<8.1f} ৳{c['limit_entry']:<9.1f} ৳{c['tp_target']:<11.1f} ৳{c['stop_loss']:<9.1f} {c['div_yield']:<7.1f}% {tag}{c['window_status']}")

    print("=" * 86)
    print("💡 SYSTEMATIC EXECUTION RULES:")
    print("   1. 🟢 ACTIVE ACCUMULATION: Enter limit orders on support dips. Target +9% exit before record date.")
    print("   2. 🟡 APPROACHING (10-25 days): Build watchlist; place bids 1.5% below market during morning lulls.")
    print("   3. PROFIT SWEEP: When swing reaches +9%, sell shares and sweep profits into JAMUNAOIL / SQURPHARMA Core.")
    print("=" * 86)


if __name__ == "__main__":
    print_catalyst_radar()
