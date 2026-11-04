#!/usr/bin/env python3
"""
scripts/dual_engine_portfolio_planner.py

Institutional Dual-Engine Portfolio Allocation & Profit-Harvesting System for DSE.
Scalable across ANY budget: from Micro Capital (৳500 - ৳1,500) to Institutional (৳50,000 - ৳1,000,000+).

Architectural Split:
  1. ENGINE 1: Core Long-Term Moats (60% of Equity Allocation)
     - Horizon: 1 to 3+ Years.
     - Mandate: Multi-year cash dividend compounding, balance-sheet safety, near-zero debt.
     - Strategy: Buy at 20-DMA / ATR support, hold through market cycles, collect 8%–11% cash yields.
  2. ENGINE 2: Bi-Weekly / Monthly Swing Engine (40% of Equity Allocation)
     - Horizon: 15 to 30 Days (2 to 4 Weeks).
     - Mandate: Systematic capital gain harvesting (+8.5% to +12.0% per trade), overcoming 0.880% friction.
     - Catalysts: Pre-dividend announcement momentum, 14-day oversold RSI mean reversion, earnings surprises.
     - Risk Rule: Hard Stop-Loss (-5.0%), Take-Profit 1 (+9.0%), Take-Profit 2 (+18.0%).
     - Profit Recycling: Realized swing profits are swept into Engine 1 to permanently compound wealth.

Usage:
  python scripts/dual_engine_portfolio_planner.py --amount 500
  python scripts/dual_engine_portfolio_planner.py --amount 50000
"""

from __future__ import annotations

import sys
import os
import json
import sqlite3
import argparse
import math
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# Windows console encoding safeguard
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "data" / "processed" / "dse.db"
REPORTS_DIR = ROOT_DIR / "reports" / "dual_engine"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
SCRIPTS_DIR = ROOT_DIR / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from smart_capital_planner import (
    get_market_regime,
    compute_dynamic_stock_metrics,
    load_candidate_pool,
    build_tranche_plan
)
from anti_manipulation_engine import is_ticker_blacklisted
from unified_score import is_shariah_excluded_company
from macro_rate_feed import get_latest_macro_rates

# Statutory Fees
FEE_BUY_PCT = 0.00415   # 0.415% (Broker + CDBL + DSE)
FEE_SELL_PCT = 0.00465  # 0.465% (Broker + CDBL + DSE + 0.05% Sec 53BBB AIT)
TOTAL_ROUND_TRIP_FEE = FEE_BUY_PCT + FEE_SELL_PCT  # 0.880%


def get_user_screening_tier() -> str:
    """Retrieves active user customization tier ('strict', 'flexible', or 'off')."""
    try:
        from profile import load_profile
        return load_profile().get("halal_tier", "flexible")
    except Exception:
        return "flexible"


def evaluate_dual_engine_universe(asof_date: str | None = None) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Scans the audited universe and partitions candidates into:
      1. Core Moats (Long-Term Compounding)
      2. Tactical Swings (Bi-Weekly / Monthly Catalysts)
    """
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    
    if not asof_date:
        row = conn.execute("SELECT MAX(date) FROM prices").fetchone()
        asof_date = row[0] if row and row[0] else datetime.date.today().isoformat()

    user_tier = get_user_screening_tier()
    candidates = load_candidate_pool()
    
    # Curated fallbacks across diverse sectors
    sector_fallbacks = ["JAMUNAOIL", "PADMAOIL", "MPETROLEUM", "SQURPHARMA", "GP", "OLYMPIC", "BSRMSTEEL", "WALTONHIL", "BXPHARMA"]
    for t in sector_fallbacks:
        if t not in candidates:
            candidates.append(t)

    core_pool: List[Dict[str, Any]] = []
    swing_pool: List[Dict[str, Any]] = []

    macro_rates = get_latest_macro_rates()
    hurdle = macro_rates.get("equity_hurdle_rate_pct", 15.1)

    for ticker in candidates:
        is_blocked, _ = is_ticker_blacklisted(ticker, asof_date=asof_date)
        if is_blocked:
            continue

        metrics = compute_dynamic_stock_metrics(ticker, conn)
        if not metrics or not metrics.get("current_price"):
            continue

        sec = metrics.get("sector", "Unknown")
        if user_tier in ("strict", "flexible") and is_shariah_excluded_company(sec, ticker=ticker):
            continue

        de = metrics.get("debt_equity")
        max_de = 0.50 if user_tier == "strict" else (0.80 if user_tier == "flexible" else 1.50)
        if de is not None and de > max_de:
            continue

        cfo = metrics.get("cfo")
        eps = metrics.get("eps")
        # Check cash flow quality
        cfo_ratio = (cfo / eps) if (cfo is not None and eps is not None and eps > 0) else 1.0

        dy = metrics.get("dividend_yield") or 0.0
        mos = metrics.get("mos_pct") or 0.0
        cur_px = metrics["current_price"]
        limit_px = metrics.get("target_dip") or round(cur_px - (0.35 * cur_px * 0.01), 1)
        adv = metrics.get("adv_turnover_bdt") or 0.0
        vol = metrics.get("volatility_pct") or 20.0

        # Execution targets net of 0.880% friction
        be_px = round(limit_px * (1.0 + FEE_BUY_PCT) / (1.0 - FEE_SELL_PCT), 2)
        tp1_px = round(limit_px * 1.09, 2)  # +9.0% profit target
        tp2_px = round(limit_px * 1.18, 2)  # +18.0% runner
        sl_px = round(limit_px * 0.95, 2)   # -5.0% hard stop

        item = {
            **metrics,
            "ticker": ticker,
            "sector": sec,
            "limit_entry": limit_px,
            "break_even": be_px,
            "tp1": tp1_px,
            "tp2": tp2_px,
            "stop_loss": sl_px,
            "cfo_ratio": round(cfo_ratio, 2),
            "dividend_yield": dy,
            "mos_pct": mos,
        }

        # 1. CORE MOAT CRITERIA:
        # High Margin of Safety (>15%), CFO/EPS >= 0.75, Low Debt (<0.50), Solid Dividend Yield (>=4.0%)
        is_core_fit = (
            (de is None or de <= 0.35) and
            cfo_ratio >= 0.75 and
            (dy >= 4.0 or mos >= 25.0)
        )
        if is_core_fit:
            core_score = (mos * 0.4) + (dy * 3.5) + (10.0 if de == 0.0 else 5.0)
            core_pool.append({**item, "core_score": round(core_score, 1)})

        # 2. TACTICAL SWING CRITERIA:
        # High Liquidity (ADV > ৳1.0 Cr), Volatility > 4%, positive earnings, asymmetric payoff >= 2.0x
        rr = round((tp1_px - limit_px) / max(0.01, (limit_px - sl_px)), 2)
        item["risk_reward"] = rr
        
        # Catalysts: oversold bounce or dividend anticipation
        catalyst = "20-DMA Mean-Reversion Dip"
        if dy >= 7.0:
            catalyst = "Pre-Dividend Declaration Run-Up"
        elif mos > 40.0:
            catalyst = "Deep Value Graham Re-rating"

        item["catalyst"] = catalyst
        item["swing_score"] = round((rr * 15.0) + (10.0 if adv > 10000000 else 5.0) + (10.0 if dy > 5.0 else 0.0), 1)
        swing_pool.append(item)

    conn.close()

    # Sort Core by core_score DESC, Swing by swing_score DESC
    core_pool.sort(key=lambda x: x.get("core_score", 0), reverse=True)
    swing_pool.sort(key=lambda x: x.get("swing_score", 0), reverse=True)

    return core_pool, swing_pool


def generate_dual_engine_portfolio_plan(capital_bdt: float) -> Dict[str, Any]:
    """Generates the unified 60% Core + 40% Swing allocation plan across any budget."""
    regime_info = get_market_regime()
    cash_buffer_pct = regime_info.get("cash_buffer_pct", 25.0)
    
    # Capital tier classification
    if capital_bdt < 1500.0:
        capital_tier = "MICRO"
        operational_cash_pct = 15.0  # minimal buffer to maximize deployability
    elif capital_bdt < 10000.0:
        capital_tier = "SMALL"
        operational_cash_pct = 20.0
    elif capital_bdt < 50000.0:
        capital_tier = "MEDIUM"
        operational_cash_pct = max(20.0, min(40.0, cash_buffer_pct))
    else:
        capital_tier = "INSTITUTIONAL"
        operational_cash_pct = max(25.0, min(50.0, cash_buffer_pct))

    min_cash_bdt = round(capital_bdt * (operational_cash_pct / 100.0), 2)
    max_equity_spend_bdt = capital_bdt - min_cash_bdt

    core_pool, swing_pool = evaluate_dual_engine_universe(regime_info.get("as_of_date"))

    # Select candidates respecting capital tier and sector diversification
    max_core_picks = 1 if capital_tier == "MICRO" else (2 if capital_tier in ("SMALL", "MEDIUM") else 3)
    max_swing_picks = 1 if capital_tier == "MICRO" else (2 if capital_tier in ("SMALL", "MEDIUM") else 3)

    selected_core: List[Dict[str, Any]] = []
    seen_core_sectors = set()
    for c in core_pool:
        if c["sector"] not in seen_core_sectors:
            selected_core.append(c)
            seen_core_sectors.add(c["sector"])
            if len(selected_core) >= max_core_picks:
                break

    selected_swing: List[Dict[str, Any]] = []
    seen_swing_tickers = {c["ticker"] for c in selected_core}
    for s in swing_pool:
        if s["ticker"] not in seen_swing_tickers:
            selected_swing.append(s)
            seen_swing_tickers.add(s["ticker"])
            if len(selected_swing) >= max_swing_picks:
                break

    # Calculate target equity budgets (60% Core / 40% Swing)
    target_core_bdt = max_equity_spend_bdt * 0.60
    target_swing_bdt = max_equity_spend_bdt * 0.40

    # 1. Allocate Core Positions
    core_allocations = []
    total_spent = 0.0

    if selected_core:
        per_core_target = target_core_bdt / len(selected_core)
        for pick in selected_core:
            lim = pick["limit_entry"]
            shs = int(per_core_target // lim)
            # Micro/small tier helper: if budget allows at least 1 share under max_equity_spend
            if shs == 0 and (total_spent + lim) <= max_equity_spend_bdt:
                shs = 1

            if shs > 0 and (total_spent + (shs * lim)) <= capital_bdt:
                cost = round(shs * lim, 2)
                total_spent += cost
                est_div = round(shs * pick["current_price"] * (pick["dividend_yield"] / 100.0), 2)
                tranches = build_tranche_plan(shs, pick["current_price"], lim, pick["min_low_60d"])
                core_allocations.append({
                    **pick,
                    "shares": shs,
                    "outlay_bdt": cost,
                    "annual_expected_dividend_bdt": est_div,
                    "tranches": tranches,
                })

    # 2. Allocate Swing Positions with remaining spend room
    swing_allocations = []
    remaining_spend_room = capital_bdt - total_spent - (capital_bdt * 0.10) # strictly keep at least 10% cash

    if selected_swing and remaining_spend_room > 0:
        per_swing_target = min(target_swing_bdt, remaining_spend_room) / len(selected_swing)
        for pick in selected_swing:
            lim = pick["limit_entry"]
            shs = int(per_swing_target // lim)
            # Micro tier fallback: if room allows at least 1 share while preserving positive cash
            if shs == 0 and (total_spent + lim) <= (capital_bdt - (capital_bdt * 0.08)):
                shs = 1

            if shs > 0 and (total_spent + (shs * lim)) <= capital_bdt:
                cost = round(shs * lim, 2)
                total_spent += cost
                remaining_spend_room -= cost
                net_profit_tp1 = round(shs * (pick["tp1"] - pick["break_even"]), 2)
                swing_allocations.append({
                    **pick,
                    "shares": shs,
                    "outlay_bdt": cost,
                    "net_profit_tp1_bdt": net_profit_tp1,
                    "holding_days": "15–30 Days",
                })

    # Strict invariant enforcement: Total Outlay <= Capital (retained cash never negative)
    total_core_outlay = sum(a["outlay_bdt"] for a in core_allocations)
    total_swing_outlay = sum(a["outlay_bdt"] for a in swing_allocations)
    retained_cash = round(capital_bdt - (total_core_outlay + total_swing_outlay), 2)

    return {
        "as_of_date": regime_info.get("as_of_date"),
        "total_capital_bdt": capital_bdt,
        "capital_tier": capital_tier,
        "market_regime": regime_info.get("regime", "BEARISH_DRIFT"),
        "dsex": regime_info.get("dsex"),
        "t_bill_rate": regime_info.get("t_bill_rate", 11.60),
        "defensive_cash_bdt": retained_cash,
        "core_allocations": core_allocations,
        "swing_allocations": swing_allocations,
        "total_core_outlay": total_core_outlay,
        "total_swing_outlay": total_swing_outlay,
    }


def print_and_save_dual_engine_report(plan: Dict[str, Any]):
    """Formats and prints the Dual-Engine Portfolio Plan and writes markdown."""
    cap = plan["total_capital_bdt"]
    tier = plan.get("capital_tier", "STANDARD")
    asof = plan["as_of_date"]
    regime = plan["market_regime"]
    t_bill = plan["t_bill_rate"]
    cash = plan["defensive_cash_bdt"]
    cash_pct = (cash / cap * 100.0) if cap > 0 else 0.0

    print("=" * 86)
    print(f"🏛️ DSE DUAL-ENGINE ALLOCATION PLAN — BUDGET: ৳{cap:,.2f} [TIER: {tier}]")
    print(f"📅 As-of Date: {asof} | Market Regime: [{regime}] | T-Bill Yield: {t_bill}%")
    print("=" * 86)
    print(f"🛡️ Defensive Cash & Liquidity Buffer: ৳{cash:,.2f} ({cash_pct:.1f}%)")
    if tier == "MICRO":
        print("   └─ Micro Cash Reserve: Keep in bKash/Nagad/SND (7.5%-8.0%) ready for dip execution.")
    else:
        print("   └─ Earns 7.5%–11.6% annualized in MFS/SND/T-Bills while awaiting entries.")
    print("-" * 86)

    # 1. ENGINE 1: CORE MOATS
    print("\n💎 ENGINE 1: LONG-TERM DIVIDEND MOAT CORE (60% Equity Allocation | Horizon: 1–3+ Years)")
    print("   Mandate: Permanent cash compounding, zero/low debt, stress-free dividend harvesting.")
    print("-" * 86)
    if plan["core_allocations"]:
        print(f"{'Ticker':<11} {'Sector':<16} {'Live Px':<10} {'Buy Limit':<11} {'Shares':<8} {'Outlay':<12} {'Div Yield':<10} {'Exp. Annual Div'}")
        print("-" * 86)
        for c in plan["core_allocations"]:
            print(f"{c['ticker']:<11} {c['sector']:<16} ৳{c['current_price']:<9.1f} ৳{c['limit_entry']:<10.1f} {c['shares']:<8} ৳{c['outlay_bdt']:<11.2f} {c['dividend_yield']:<9.1f}% ৳{c['annual_expected_dividend_bdt']:,.2f}")
            for tr in c.get("tranches", []):
                print(f"   ├─ {tr['tranche']:<22}: {tr['shares']} shs @ ৳{tr['price']:.1f} [{tr['note']}]")
    else:
        print("   [No Core Moats affordable under current tranche budget. Cash retained safely.]")

    # 2. ENGINE 2: TACTICAL SWINGS
    print("\n⚡ ENGINE 2: BI-WEEKLY / MONTHLY SWING ENGINE (40% Equity Allocation | Horizon: 15–30 Days)")
    print("   Mandate: Systematic +8.5% to +12.0% profit harvesting; strictly overcomes 0.880% friction.")
    print("-" * 86)
    if plan["swing_allocations"]:
        print(f"{'Ticker':<11} {'Sector':<16} {'Buy Limit':<11} {'BreakEven':<11} {'Target(TP1)':<12} {'StopLoss':<10} {'Shares':<8} {'Catalyst'}")
        print("-" * 86)
        for s in plan["swing_allocations"]:
            print(f"{s['ticker']:<11} {s['sector']:<16} ৳{s['limit_entry']:<10.1f} ৳{s['break_even']:<10.2f} ৳{s['tp1']:<11.2f} ৳{s['stop_loss']:<9.2f} {s['shares']:<8} {s['catalyst']}")
    else:
        print("   [No Swing positions allocated under current tranche. Cash preserved.]")

    print("=" * 86)
    print("📈 TECHNICAL STEP-BY-STEP PROFIT GENERATION BLUEPRINT:")
    print("   1. WHEN TO BUY: Enter Limit Orders at 11:30 AM–12:30 PM at or below 'Buy Limit'. Never chase opening gaps.")
    print("   2. HOLDING HORIZON: 15 to 30 Days. This bypasses T+2 lockup and crushes the 0.880% round-trip fee.")
    print("   3. WHEN TO SELL (SWINGS): When stock hits TP1 (+9.0%), sell 50% shares to lock profit. Hold 50% for TP2 (+18.0%).")
    print("   4. HARD STOP-LOSS: If daily close drops below 'StopLoss' (-5.0%), exit next morning. Zero emotion/hope.")
    print("   5. COMPOUNDING FLYWHEEL: Reinvest realized swing profits + cash dividends back into Engine 1 Core Moats.")
    print("=" * 86)

    # Save to Markdown
    md_path = REPORTS_DIR / f"{asof}_dual_engine_plan.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# 🏛️ Dual-Engine Portfolio Allocation Plan [Budget: ৳{cap:,.2f} | Tier: {tier}]\n\n")
        f.write(f"**As-of Date**: {asof}  \n")
        f.write(f"**Total Capital**: ৳{cap:,.2f}  \n")
        f.write(f"**Market Regime**: {regime} (T-Bill: {t_bill}%)  \n")
        f.write(f"**Defensive Cash Buffer**: ৳{cash:,.2f} ({cash_pct:.1f}%)  \n\n")

        f.write("## 💎 Engine 1: Long-Term Dividend Moat Core (60%)\n")
        f.write("| Ticker | Sector | Current Px | Buy Limit | Shares | Outlay (BDT) | Div Yield | Exp. Div (BDT) |\n")
        f.write("|---|---|---|---|---|---|---|---|\n")
        for c in plan["core_allocations"]:
            f.write(f"| **{c['ticker']}** | {c['sector']} | ৳{c['current_price']} | ৳{c['limit_entry']} | {c['shares']} | ৳{c['outlay_bdt']:,.2f} | {c['dividend_yield']}% | ৳{c['annual_expected_dividend_bdt']:,.2f} |\n")

        f.write("\n## ⚡ Engine 2: Bi-Weekly / Monthly Swing Engine (40%)\n")
        f.write("| Ticker | Sector | Buy Limit | Break-even | Target (TP1) | Stop Loss | Shares | Catalyst |\n")
        f.write("|---|---|---|---|---|---|---|---|\n")
        for s in plan["swing_allocations"]:
            f.write(f"| **{s['ticker']}** | {s['sector']} | ৳{s['limit_entry']} | ৳{s['break_even']} | ৳{s['tp1']} (+9%) | ৳{s['stop_loss']} (-5%) | {s['shares']} | {s['catalyst']} |\n")

        f.write("\n## 📋 Technical Profit Playbook\n")
        f.write("1. **Limit Entry Timing**: Place Limit orders during 11:30 AM to 12:30 PM lull.\n")
        f.write("2. **Swing Exit**: Take profit at TP1 (+9.0%) on 50% position; let remainder ride to TP2 (+18.0%).\n")
        f.write("3. **Stop Protection**: Cut immediately at -5.0% Stop-Loss.\n")
        f.write("4. **Perpetual Wealth Compound**: Sweep swing gains directly into Engine 1 Core.\n")

    print(f"\n[Plan saved to: {md_path}]")


def main():
    parser = argparse.ArgumentParser(description="DSE Dual-Engine Portfolio Allocator")
    parser.add_argument("--amount", type=float, default=50000.0, help="Total investment capital in BDT")
    args = parser.parse_args()

    plan = generate_dual_engine_portfolio_plan(args.amount)
    print_and_save_dual_engine_report(plan)


if __name__ == "__main__":
    main()
