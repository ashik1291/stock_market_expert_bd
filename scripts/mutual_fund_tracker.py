"""
scripts/mutual_fund_tracker.py
------------------------------
Tracks, stores, and updates Net Asset Value (NAV) and Redemption Prices for
Open-End Mutual Funds (e.g. Shanta Amanah Shariah Fund).

Features:
1. SQLite persistence in data/processed/dse.db (table: open_end_mutual_funds).
2. Live scraping / fetching from Shanta Asset Management disclosures.
3. Synchronizes user portfolio (data/portfolio/portfolio.json) with mark-to-market NAV.
"""

from __future__ import annotations

import sys
import json
import sqlite3
import datetime
import urllib.request
import re
from pathlib import Path
from typing import Optional, Dict, Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"
PORTFOLIO_DIR = BASE_DIR / "data" / "portfolio"


def init_db(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS open_end_mutual_funds (
            fund_name TEXT NOT NULL,
            asof_date TEXT NOT NULL,
            nav_sale REAL,
            nav_redemption REAL,
            repurchase_price REAL,
            asset_manager TEXT,
            source TEXT,
            updated_at TEXT,
            PRIMARY KEY (fund_name, asof_date)
        )
    """)
    conn.commit()


MAX_NAV_MOVE_PCT = 10.0


def fetch_shanta_nav_online(fund_name: str = "Shanta Amanah Shariah Fund") -> Optional[Dict[str, float]]:
    """
    Reads the NAV the AMC homepage shows for `fund_name` ("NAV <value> <fund name>" in the rendered
    text). The page carries no NAV date, so the fetch date is used and the source says so.
    Returns None when the exact pattern is absent: no number near the name is ever guessed.
    """
    url = "https://www.shanta-aml.com/"
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    name = r"\s+".join(re.escape(w) for w in fund_name.split())
    match = re.search(r"NAV\s+(\d{1,3}\.\d{2,4})\s+" + name + r"\b", text, re.IGNORECASE)
    if not match:
        return None
    price = float(match.group(1))
    return {"nav_sale": price, "nav_redemption": price, "asof_date": datetime.date.today().isoformat()}


def nav_is_plausible(fund_name: str, nav: float) -> bool:
    """An open-end fund NAV cannot move more than MAX_NAV_MOVE_PCT between updates; a bigger jump is a parse error."""
    last = get_latest_nav_from_db(fund_name)
    if not last or not last.get("nav_redemption"):
        return True
    return abs(nav / float(last["nav_redemption"]) - 1.0) * 100.0 <= MAX_NAV_MOVE_PCT


def record_nav_to_db(
    fund_name: str,
    asof_date: str,
    nav_redemption: float,
    nav_sale: Optional[float] = None,
    asset_manager: str = "Shanta Asset Management Limited",
    source: str = "verified_feed"
):
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    init_db(conn)
    if nav_sale is None:
        nav_sale = nav_redemption

    conn.execute("""
        INSERT INTO open_end_mutual_funds
        (fund_name, asof_date, nav_sale, nav_redemption, repurchase_price, asset_manager, source, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(fund_name, asof_date) DO UPDATE SET
            nav_sale = excluded.nav_sale,
            nav_redemption = excluded.nav_redemption,
            repurchase_price = excluded.repurchase_price,
            updated_at = excluded.updated_at
    """, (
        fund_name,
        asof_date,
        nav_sale,
        nav_redemption,
        nav_redemption,
        asset_manager,
        source,
        datetime.datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()


def get_latest_nav_from_db(fund_name: str) -> Optional[Dict[str, Any]]:
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    init_db(conn)
    row = conn.execute("""
        SELECT fund_name, asof_date, nav_sale, nav_redemption, repurchase_price, asset_manager, source, updated_at
        FROM open_end_mutual_funds
        WHERE fund_name = ?
        ORDER BY asof_date DESC LIMIT 1
    """, (fund_name,)).fetchone()
    conn.close()

    if row:
        return {
            "fund_name": row[0],
            "asof_date": row[1],
            "nav_sale": row[2],
            "nav_redemption": row[3],
            "repurchase_price": row[4],
            "asset_manager": row[5],
            "source": row[6],
            "updated_at": row[7]
        }
    return None


def sync_portfolio_mutual_fund_nav(
    fund_name: str = "Shanta Amana Shariah Fund",
    latest_redemption_px: Optional[float] = None,
    asof_date: Optional[str] = None,
    target_files: Optional[list] = None,
) -> Dict[str, Any]:
    """
    Updates portfolio ledgers with the latest mark-to-market redemption price of `fund_name`.
    Price sources, in order: explicit argument (recorded as manual_entry), online AMC fetch,
    latest stored NAV. With none available nothing is written: a guessed NAV is never used.
    """
    if target_files is None:
        target_files = []
        if (PORTFOLIO_DIR / "portfolio.json").exists():
            target_files.append(PORTFOLIO_DIR / "portfolio.json")
        users_dir = BASE_DIR / "data" / "users"
        if users_dir.exists():
            for u_port in users_dir.glob("*/portfolio.json"):
                target_files.append(u_port)

    if not target_files:
        return {"status": "error", "message": "no portfolio.json files found"}

    if latest_redemption_px is not None:
        if not asof_date:
            return {"status": "error", "message": "an explicit NAV needs its asof_date"}
        record_nav_to_db(fund_name, asof_date, float(latest_redemption_px), source="manual_entry")
    else:
        online_nav = fetch_shanta_nav_online(fund_name.replace("Amana ", "Amanah "))
        if online_nav and not nav_is_plausible(fund_name, online_nav["nav_redemption"]):
            print(f"[MF] Rejected implausible online NAV {online_nav['nav_redemption']} for {fund_name}")
            online_nav = None
        if online_nav:
            latest_redemption_px = online_nav["nav_redemption"]
            asof_date = online_nav["asof_date"]
            record_nav_to_db(fund_name, asof_date, latest_redemption_px, source="shanta_aml_website (NAV shown on fetch date)")
        else:
            db_nav = get_latest_nav_from_db(fund_name)
            if not (db_nav and db_nav["nav_redemption"]):
                return {"status": "no_nav", "fund_name": fund_name,
                        "message": "no NAV online or stored; ledgers left unchanged"}
            latest_redemption_px = db_nav["nav_redemption"]
            asof_date = db_nav["asof_date"]

    last_summary = {}
    for portfolio_file in target_files:
        try:
            with open(portfolio_file, "r", encoding="utf-8") as f:
                port = json.load(f)

            mf_list = port.get("mutual_funds", [])
            updated = False
            total_mf_market_val = 0.0
            total_mf_cost = 0.0

            for mf in mf_list:
                if fund_name.lower() in mf.get("fund_name", "").lower():
                    units = float(mf.get("units", 0))
                    cost = float(mf.get("total_cost_bdt", 0))
                    mkt_val = round(units * latest_redemption_px, 2)
                    pnl_bdt = round(mkt_val - cost, 2)
                    pnl_pct = round((pnl_bdt / cost) * 100.0, 2) if cost > 0 else 0.0

                    mf["redemption_price_bdt"] = latest_redemption_px
                    mf["market_value_bdt"] = mkt_val
                    mf["unrealized_pnl_bdt"] = pnl_bdt
                    mf["unrealized_pnl_pct"] = pnl_pct
                    mf["asof_date"] = asof_date
                    updated = True

                total_mf_market_val += float(mf.get("market_value_bdt", 0.0))
                total_mf_cost += float(mf.get("total_cost_bdt", 0.0))

            if not updated:
                continue  # this ledger does not hold the fund; never price another fund with its NAV

            # Update summary in portfolio
            summary = port.get("summary", {})
            eq_val = float(summary.get("equities_market_value_bdt", 0.0))
            cash = float(port.get("cash_balance_bdt", 0.0))
            tot_val = round(eq_val + total_mf_market_val + cash, 2)
            tot_cost = float(summary.get("total_cost_basis_bdt", port.get("total_capital_bdt", 0.0)))
            tot_pnl = round(tot_val - tot_cost, 2)
            tot_pnl_pct = round((tot_pnl / tot_cost) * 100.0, 2) if tot_cost > 0 else 0.0

            summary["mutual_fund_market_value_bdt"] = total_mf_market_val
            summary["mutual_fund_weight_pct"] = round((total_mf_market_val / tot_val) * 100.0, 2) if tot_val > 0 else 0.0
            summary["equities_weight_pct"] = round((eq_val / tot_val) * 100.0, 2) if tot_val > 0 else 0.0
            summary["total_market_value_bdt"] = tot_val
            summary["total_unrealized_pnl_bdt"] = tot_pnl
            summary["total_unrealized_pnl_pct"] = tot_pnl_pct

            port["updated_at"] = datetime.datetime.now().isoformat()

            with open(portfolio_file, "w", encoding="utf-8") as f:
                json.dump(port, f, indent=2)

            last_summary = {
                "portfolio_file": str(portfolio_file),
                "redemption_price_bdt": latest_redemption_px,
                "market_value_bdt": total_mf_market_val,
                "total_portfolio_net_worth": tot_val
            }
        except Exception as e:
            pass

    return {
        "status": "success",
        "fund_name": fund_name,
        "asof_date": asof_date,
        "redemption_price_bdt": latest_redemption_px,
        "files_updated": len(target_files),
        "latest_summary": last_summary
    }


if __name__ == "__main__":
    # Manual entry: python scripts/mutual_fund_tracker.py <redemption_nav> <YYYY-MM-DD>
    # No arguments: online fetch, else the latest stored NAV; nothing is written when neither exists.
    if len(sys.argv) > 1:
        if len(sys.argv) < 3:
            sys.exit("usage: mutual_fund_tracker.py [<redemption_nav> <asof YYYY-MM-DD>]")
        res = sync_portfolio_mutual_fund_nav(latest_redemption_px=float(sys.argv[1]), asof_date=sys.argv[2])
    else:
        res = sync_portfolio_mutual_fund_nav()
    print(json.dumps(res, indent=2))
