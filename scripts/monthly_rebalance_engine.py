"""
DSE Monthly Capital Deployment & Rebalance Engine.
Calculates the optimal share allocation for the user's monthly BDT 2,000 budget
across the 6 Halal Core Pillars (SQURPHARMA, GP, JAMUNAOIL, BSRMLTD, LHB, OLYMPIC)
and Shanta Amana Shariah Fund, targeting underweight pillars first.
"""

import sys
import json
import sqlite3
import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PORTFOLIO_DIR = BASE_DIR / "data" / "portfolio"
PORTFOLIO_PATH = PORTFOLIO_DIR / "portfolio.json"
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Target weights for the 6-pillar equity basket (Total: 100%)
TARGET_WEIGHTS = {
    "SQURPHARMA": 0.35,  # 35% Healthcare Moat
    "GP":         0.20,  # 20% Telecom Monopolistic Cash Cow
    "JAMUNAOIL":  0.15,  # 15% Sovereign Fuel Distribution & High Dividend
    "BSRMLTD":    0.10,  # 10% Infrastructure Steel Leader
    "LHB":        0.10,  # 10% Clinker Self-Sufficient Cement
    "OLYMPIC":    0.10,  # 10% Packaged Consumer Goods
}

COMMISSION_RATE = 0.00415  # 0.415% CDBL + Broker fee


def calculate_monthly_deployment(budget_bdt: float = 2000.0) -> dict:
    if not PORTFOLIO_PATH.exists():
        raise FileNotFoundError("portfolio.json not found")

    with open(PORTFOLIO_PATH, encoding="utf-8") as f:
        p = json.load(f)

    # 1. Fetch live closing prices from SQLite
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    live_prices = {}
    for ticker in TARGET_WEIGHTS.keys():
        row = cur.execute(
            "SELECT close FROM prices WHERE ticker = ? ORDER BY date DESC LIMIT 1",
            (ticker,)
        ).fetchone()
        live_prices[ticker] = float(row[0]) if row and row[0] else 100.0
    conn.close()

    # 2. Audit current equity holdings
    current_shares = {t: 0 for t in TARGET_WEIGHTS}
    current_equity_values = {t: 0.0 for t in TARGET_WEIGHTS}
    for h in p.get("holdings", []):
        t = h.get("ticker")
        if t in current_shares:
            sh = h.get("shares", 0)
            current_shares[t] += sh
            current_equity_values[t] += sh * live_prices[t]

    total_current_equity = sum(current_equity_values.values())
    target_post_equity = total_current_equity + budget_bdt

    # 3. Find allocation gap per pillar
    gaps = {}
    for t, target_pct in TARGET_WEIGHTS.items():
        ideal_val = target_post_equity * target_pct
        current_val = current_equity_values[t]
        gaps[t] = max(0.0, ideal_val - current_val)

    # Sort pillars by largest deficit
    sorted_by_gap = sorted(gaps.items(), key=lambda x: x[1], reverse=True)

    # 4. Fill basket iteratively within budget
    allocated_shares = {t: 0 for t in TARGET_WEIGHTS}
    remaining_budget = budget_bdt

    # Prioritize underweight pillars
    for t, _ in sorted_by_gap:
        px = live_prices[t]
        cost_per_sh = px * (1.0 + COMMISSION_RATE)
        # Allocate shares up to the pillar's gap or remaining budget
        max_sh_possible = int(remaining_budget / cost_per_sh)
        needed_sh = int(gaps[t] / cost_per_sh)
        buy_sh = min(max_sh_possible, max(1, needed_sh)) if max_sh_possible > 0 else 0
        if buy_sh > 0 and (buy_sh * cost_per_sh) <= remaining_budget:
            allocated_shares[t] += buy_sh
            remaining_budget -= (buy_sh * cost_per_sh)

    # If any budget remains, allocate to highest-conviction undervalued pillar
    for t, _ in sorted_by_gap:
        px = live_prices[t]
        cost_per_sh = px * (1.0 + COMMISSION_RATE)
        if remaining_budget >= cost_per_sh:
            extra = int(remaining_budget / cost_per_sh)
            allocated_shares[t] += extra
            remaining_budget -= (extra * cost_per_sh)

    # 5. Format results
    total_spent = budget_bdt - remaining_budget
    lines = []
    lines.append(f"# 💰 Monthly Halal Rebalance Plan (Budget: ৳{budget_bdt:,.2f})")
    lines.append(f"**Generated**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | **Execution Corridor**: Month-End Tranche\n")
    lines.append("| Pillar Ticker | Current Sh | Added Sh | LTP (৳) | Gross Cost (৳) | Comm (৳) | Total Outlay (৳) | Post Share Count |")
    lines.append("|---|---|---|---|---|---|---|---|")

    summary_items = []
    for t in TARGET_WEIGHTS:
        sh = allocated_shares[t]
        if sh > 0:
            px = live_prices[t]
            gross = round(sh * px, 2)
            comm = round(gross * COMMISSION_RATE, 2)
            tot = round(gross + comm, 2)
            post_sh = current_shares[t] + sh
            lines.append(f"| **{t}** | {current_shares[t]} sh | **+{sh} sh** | ৳{px:.2f} | ৳{gross:,.2f} | ৳{comm:.2f} | **৳{tot:,.2f}** | {post_sh} sh |")
            summary_items.append({"ticker": t, "shares": sh, "price": px, "total": tot})

    lines.append(f"\n**Total Deployment Outlay**: **৳{total_spent:,.2f}** | **Surplus Cash Retained**: **৳{remaining_budget:,.2f}**\n")
    lines.append("> 🛡️ **Execution Directive**: Place limit orders strictly inside 3-tick spread. Never market-order thin depth.")

    md_report = "\n".join(lines)
    return {
        "budget_bdt": budget_bdt,
        "total_spent_bdt": round(total_spent, 2),
        "surplus_cash_bdt": round(remaining_budget, 2),
        "allocations": summary_items,
        "report_markdown": md_report
    }


if __name__ == "__main__":
    budget = float(sys.argv[1]) if len(sys.argv) > 1 else 2000.0
    res = calculate_monthly_deployment(budget)
    print(res["report_markdown"])
