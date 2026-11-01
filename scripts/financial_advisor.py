"""
scripts/financial_advisor.py
----------------------------
Chief Quantitative Financial Advisor for Bangladesh Stock Market (DSE).

Unifies All 4 Institutional Pillars:
  1. Macro Economic & Market Volatility Radar (DSEX 20-DMA, Volatility Target, T-Bill Hurdle)
  2. Portfolio Health Sentinel (Break-even tracking, Trailing Stop-Loss, Dividend Receivables)
  3. Event-Driven Catalyst Alpha (Dividend run-up cycles & pre-record accumulation)
  4. Inverse-Volatility Risk Parity Capital Allocation (Dynamic whole-share budgeting)
  5. Forensic Surveillance Guard (Zero-tolerance on syndicate manipulation & toxic debt)

Usage:
  python scripts/financial_advisor.py [--amount 3000]
"""

import sys
import os
import json
import sqlite3
import datetime
import argparse
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from smart_capital_planner import get_market_regime, generate_smart_plan
from portfolio_sentinel import audit_portfolio_sentinel
from event_driven_alpha_engine import scan_dividend_catalysts
from anti_manipulation_engine import run_surveillance_scan

REPORTS_DIR = ROOT_DIR / "reports" / "advisory"


def generate_advisor_dossier(budget_amount: float = 3000.0) -> dict:
    """Compiles the full institutional financial advisory dossier."""
    regime = get_market_regime()
    sentinel = audit_portfolio_sentinel()
    catalysts = scan_dividend_catalysts()
    plan = generate_smart_plan(amount=budget_amount)
    alerts = run_surveillance_scan()

    critical_blacklist = [a for a in alerts if a["risk_level"] == "CRITICAL"]
    high_alerts = [a for a in alerts if a["risk_level"] == "HIGH"]

    dossier = {
        "as_of_date": regime["as_of_date"],
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "regime": regime,
        "sentinel": sentinel,
        "catalysts": catalysts[:5],
        "allocation_plan": plan,
        "critical_blacklist": critical_blacklist,
        "high_alerts": high_alerts[:8]
    }

    # Generate bilingual markdown reports
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = regime["as_of_date"]
    bn_path = REPORTS_DIR / f"{date_str}_financial_advisory_bn.md"

    bn_lines = [
        f"# 🏛️ ডিএসই প্রাতিষ্ঠানিক প্রধান আর্থিক উপদেষ্টা (Chief Financial Advisor) ডসিয়ার",
        f"**মূল্যায়ন তারিখ**: `{date_str}` | **প্রস্তুতির সময়**: `{dossier['generated_at']}`",
        f"**সার্বিক কোয়ান্ট স্ট্যাটাস**: `ঝুঁকি নিয়ন্ত্রণ ও মূলধন সুরক্ষা অগ্রাধিকার` | **ম্যাক্রো হার্ডল রেট**: **{regime['macro_hurdle']}%**\n",
        "---",
        "## 🧭 ১. ম্যাক্রো আবহাওয়া ও বাজার ঝুঁকি রাডার (Macro Radar)",
        f"- **ডিএসইএক্স সূচক (DSEX)**: `{regime['dsex']}` (২০-দিনের মুভিং এভারেজ: `{regime['dma_20']}`)",
        f"- **বাজারের বর্তমান অবস্থা**: `{regime['regime']}` — {regime['desc_bn']}",
        f"- **DSEX ২০-দিনের বার্ষিক ভলাটিলিটি**: **{regime['dsex_vol_pct']}%** (স্বাভাবিক ১২% বেঞ্চমার্কের চেয়ে উচ্চ ঝুঁকি)",
        f"- **বাংলাদেশ ব্যাংক ৯১-দিনের টি-বিল**: **{regime['t_bill_rate']}%** | ইকুইটি হার্ডল রেট: **{regime['macro_hurdle']}%**",
        f"- **গাণিতিক ক্যাশ বাফার টার্গেট**: **{regime['cash_buffer_pct']}%** লিকুইড ক্যাশ সংরক্ষণ করার নির্দেশ।\n",
        "---",
        "## 🛡️ ২. আপনার ব্যক্তিগত পোর্টফোলিও ও সেন্টিনেল নিরীক্ষা (Portfolio Health)",
        f"- **মোট অ্যাকাউন্ট মূল্য (Net Worth)**: **৳{sentinel['total_net_worth']:,.2f}**",
        f"- **শেয়ারের বর্তমান বাজারমূল্য**: ৳{sentinel['current_value_equities']:,.2f} (P&L: ৳{sentinel['equities_pnl_bdt']:,.2f} বা `{sentinel['equities_pnl_pct']:+.2f}%`)",
        f"- **মিউচুয়াল ফান্ড ডিফেন্সিভ অ্যাঙ্কর**: ৳{sentinel['mutual_funds_val']:,.2f} (Shanta Amana Shariah Fund)",
        f"- **উপলব্ধ ক্যাশ ব্যালেন্স**: ৳{sentinel['available_cash']:,.2f} | **১০% ক্যাশ ঘাটতি**: ⚠️ **৳{sentinel['cash_deficit']:,.2f}**",
        f"- **আসন্ন নিশ্চিত ক্যাশ ডিভিডেন্ড প্রাপ্যতা**: 💰 **৳{sentinel['total_dividends_receivable']:,.2f}** (নভেম্বর ২০২৬)\n",
        "### 📌 পোর্টফোলিও শেয়ারের অ্যাকশন সামারি:",
        "| কোম্পানি | শেয়ার | লাইভ দর | ব্রেক-ইভেন | P&L % | টার্গেট (+৩০%) | স্টপ-লস (-১০%) | উপদেষ্টা অ্যাকশন নির্দেশিকা |",
        "|---|---|---|---|---|---|---|---|"
    ]

    for h in sentinel["holdings"]:
        bn_lines.append(
            f"| **{h['ticker']}** | {h['shares']} | ৳{h['live_price']:.1f} | ৳{h['break_even_price']:.1f} | "
            f"**{h['pnl_pct']:+.1f}%** | ৳{h['target_price']:.1f} | ৳{h['stop_price']:.1f} | **{h['action']}** ({h['action_desc_bn']}) |"
        )

    bn_lines.extend([
        "\n---",
        "## 🎯 ৩. ইভেন্ট-ড্রাইভেন ডিভিডেন্ড ক্যাটালিস্ট ও প্রফিট উইন্ডো (Upcoming Catalysts)",
        "| কোম্পানি | খাত | লাইভ দর | ক্যাশ ডিভিডেন্ড | ইল্ড % | রেকর্ড ডেট | বাকি দিন | কৌশল ও সুপারিশ |",
        "|---|---|---|---|---|---|---|---|"
    ])

    for c in dossier["catalysts"]:
        bn_lines.append(
            f"| **{c['ticker']}** | {c['sector']} | ৳{c['price']:.1f} | ৳{c['cash_dividend_bdt']:.2f} | "
            f"**{c['dividend_yield_pct']}%** | `{c['record_date']}` | {c['days_to_record']} দিন | **{c['strategy_mode']}** ({c['mode_desc_bn']}) |"
        )

    bn_lines.extend([
        "\n---",
        f"## 💰 ৪. নতুন ৳{budget_amount:,.2f} মূলধনের স্মার্ট রিস্ক-প্যারিটি বণ্টন (Capital Allocation)",
        f"- **প্রস্তাবিত ক্যাশ সংরক্ষণ (Hold in Brokerage)**: **৳{plan['suggested_cash_reserve']:,.2f} ({plan['cash_reserve_pct']}%)**",
        f"- **সক্রিয় প্রথম কিস্তি ক্রয় বাজেট (Limit Orders)**: **৳{plan['immediate_tranche_budget']:,.2f}**\n",
        "| কোম্পানি | খাত | বর্তমান দর | লিমিট বাই টার্গেট | শেয়ার সংখ্যা | বরাদ্দকৃত অর্থ | গাণিতিক নির্বাচনের ভিত্তি |",
        "|---|---|---|---|---|---|---|"
    ])

    for a in plan["allocations"]:
        bn_lines.append(
            f"| **{a['ticker']}** | {a['sector']} | ৳{a['current_price']:.1f} | **৳{a['target_limit_price']:.1f}** | "
            f"**{a['exact_shares']} টি** | ৳{a['estimated_outlay']:.1f} | {a['rationale']} |"
        )

    bn_lines.extend([
        "\n---",
        "## ⛔ ৫. আজকের ফরেনসিক ব্ল্যাকলিস্ট (DO NOT BUY — মূলধন ক্ষয়ের ফাঁদ)",
        "| Ticker | ঝুঁকি স্কোর | সতর্কতার ধরন | বিবরণ |",
        "|---|---|---|---|"
    ])

    for b in critical_blacklist:
        bn_lines.append(f"| **{b['ticker']}** | `{b['risk_score']}/১০০` | **{b['alert_type']}** | {b['description']} |")
    if not critical_blacklist:
        bn_lines.append("> আজ কোনো স্টকে সংকটজনক ব্ল্যাকলিস্ট নেই।")

    with open(bn_path, "w", encoding="utf-8") as f:
        f.write("\n".join(bn_lines))

    return dossier


def print_advisor_cli(dossier: dict):
    r = dossier["regime"]
    s = dossier["sentinel"]
    p = dossier["allocation_plan"]
    
    print("\n" + "="*85)
    print("🏛️ DSE QUANTITATIVE CHIEF FINANCIAL ADVISOR — EXECUTIVE BRIEF")
    print("="*85)
    print(f"📅 As-of Date: {r['as_of_date']} | DSEX: {r['dsex']} | 20-DMA: {r['dma_20']} | Market Volatility: {r['dsex_vol_pct']}%")
    print(f"🏦 BB 91-Day T-Bill: {r['t_bill_rate']}% | Min Equity Hurdle: {r['macro_hurdle']}% | Stance: [{r['regime']}]")
    print("-" * 85)
    print(f"💼 PORTFOLIO HEALTH: Total Net Worth: ৳{s['total_net_worth']:,.2f} | Equities P&L: ৳{s['equities_pnl_bdt']:,.2f} ({s['equities_pnl_pct']}%)")
    print(f"   Available Cash: ৳{s['available_cash']:,.2f} | Target 10% Deficit: ৳{s['cash_deficit']:,.2f} | Dividends Incoming: ৳{s['total_dividends_receivable']:,.2f}")
    print("-" * 85)
    print("🎯 ACTIVE CORPORATE ACTION CATALYSTS (Top 3 Upcoming Opportunities):")
    for c in dossier["catalysts"][:3]:
        print(f"   * {c['ticker']:<11} Div: ৳{c['cash_dividend_bdt']:<6.2f} (Yield: {c['dividend_yield_pct']:>5.2f}%) | Record: {c['record_date']} ({c['days_to_record']}d) -> {c['strategy_mode']}")
    print("-" * 85)
    print(f"💰 FRESH CAPITAL ALLOCATION (Budget: ৳{p['invested_capital_input']:,.2f}):")
    print(f"   * Reserve Cash in Brokerage: ৳{p['suggested_cash_reserve']:,.2f} ({p['cash_reserve_pct']}%)")
    print(f"   * Active Tranche Allocation: ৳{p['immediate_tranche_budget']:,.2f}")
    for a in p["allocations"]:
        print(f"     -> {a['ticker']:<11} Limit Target: ৳{a['target_limit_price']:<6.1f} | Shares: {a['exact_shares']:<4} | Outlay: ৳{a['estimated_outlay']:<7.1f} | {a['sector']}")
    print("-" * 85)
    print(f"🚨 CRITICAL SURVEILLANCE BLACKLIST: {len(dossier['critical_blacklist'])} stocks blocked (Do not touch!)")
    print("="*85 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Chief Financial Advisor")
    parser.add_argument("--amount", type=float, default=3000.0, help="New investment capital amount in BDT")
    args = parser.parse_args()

    dossier = generate_advisor_dossier(args.amount)
    print_advisor_cli(dossier)
    date_str = dossier["as_of_date"]
    print(f"[Executive Dossier Published: reports/advisory/{date_str}_financial_advisory_bn.md]")


if __name__ == "__main__":
    main()
