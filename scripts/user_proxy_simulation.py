#!/usr/bin/env python3
"""
scripts/user_proxy_simulation.py — Real-World Investor Acceptance & Profit Maximization Engine

Acts as the automated 'dse-user-proxy':
  1. Simulates real-world DSE investor execution across capital sizes (৳1,000, ৳50,000, ৳1,000,000).
  2. Enforces Shariah shield & forensic anti-manipulation blacklist.
  3. Identifies stocks with MAXIMUM PROFIT PROBABILITY (%) using Graham Margin of Safety,
     debt resilience, cash dividend floors, and volatility-adjusted mean reversion.
  4. Formulates exact, actionable trade execution parameters:
       - WHEN TO BUY (Limit Price Range, DSE Session Timing Gate, Max Safe Buy Ceiling)
       - WHEN TO SELL (Break-even net of fees, TP1 +8% to +10%, TP2 +15% to +20%, Hard Stop-Loss -5%,
         and Circuit-Lock Deferred Liquidation)
"""

from __future__ import annotations

import sys
import json
import sqlite3
import argparse
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"
REPORT_DIR = BASE_DIR / "reports" / "user_proxy"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "scripts"))

from scripts.anti_manipulation_engine import is_ticker_blacklisted
from scripts.unified_score import is_shariah_excluded_sector, is_shariah_excluded_company
from scripts.smart_capital_planner import load_candidate_pool, compute_dynamic_stock_metrics, get_market_regime
from scripts.macro_rate_feed import get_latest_macro_rates
from scripts.calibrated_probability_engine import get_calibrated_empirical_probability

# Statutory Fees
FEE_BUY_PCT = 0.00415   # 0.415% (Broker + CDBL + DSE)
FEE_SELL_PCT = 0.00465  # 0.465% (Broker + CDBL + DSE + 0.05% Sec 53BBB AIT)


def calculate_factor_conviction_score(metrics: Dict[str, Any]) -> float:
    """
    Computes fundamental factor conviction score (0-100) based on Graham MoS,
    Debt Solvency, Cash Dividend Yield, and Volatility.
    
    NOTE: This is a MULTI-FACTOR HEURISTIC SCORE, NOT a guaranteed empirical profit probability.
    """
    de = metrics.get("debt_equity")
    if de is None or de > 0.80:
        # FAIL-CLOSED: Missing debt data or excessive leverage in 10-14% rate environment
        return 0.0

    score = 50.0
    mos = metrics.get("mos_pct", 0.0)
    dy = metrics.get("dividend_yield") or 0.0
    vol = metrics.get("volatility_pct", 25.0)

    if mos >= 40.0:
        score += 15.0
    elif mos >= 15.0:
        score += 10.0
    elif mos < 0.0:
        score -= 15.0

    if dy >= 6.0:
        score += 10.0
    elif dy >= 3.0:
        score += 5.0

    if de == 0.0:
        score += 10.0
    elif de <= 0.30:
        score += 5.0

    if vol <= 12.0:
        score += 5.0
    elif vol > 35.0:
        score -= 10.0

    return max(20.0, min(95.0, round(score, 1)))


def calculate_heuristic_conviction_score(metrics: Dict[str, Any]) -> float:
    """Heuristic multi-factor conviction score (0 - 100). NOT a calibrated probability."""
    return calculate_factor_conviction_score(metrics)


def calculate_profit_probability(metrics: Dict[str, Any]) -> float:
    """DEPRECATED alias for heuristic conviction score. NOT a calibrated probability."""
    return calculate_factor_conviction_score(metrics)


def evaluate_user_investment_plan(capital_bdt: float = 50000.0, top_n: int = 3) -> Dict[str, Any]:
    """Evaluates the market from an investor proxy viewpoint and produces actionable buy/sell plans."""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")

    # 1. Macro & Market Climate
    latest_date = conn.execute("SELECT MAX(date) FROM prices").fetchone()[0]
    macro_rates = get_latest_macro_rates()
    regime = get_market_regime()

    # 2. Candidate Universe Scan
    raw_candidates = load_candidate_pool()
    scored_candidates = []

    for ticker in raw_candidates:
        # Check forensic blacklist
        is_blocked, reason = is_ticker_blacklisted(ticker, asof_date=latest_date)
        if is_blocked:
            continue

        metrics = compute_dynamic_stock_metrics(ticker, conn)
        if not metrics or not metrics.get("current_price"):
            continue

        # Check Shariah / Customization compliance based on active profile
        user_tier = "flexible"
        try:
            from profile import load_profile
            user_tier = load_profile().get("halal_tier", "flexible")
        except Exception:
            pass

        sector = metrics.get("sector", "")
        if user_tier in ("strict", "flexible") and is_shariah_excluded_company(sector, ticker=ticker):
            continue
        max_de = 0.50 if user_tier == "strict" else (0.80 if user_tier == "flexible" else 1.00)
        if metrics.get("debt_equity") is not None and metrics["debt_equity"] > max_de:
            continue

        # Compute Factor Conviction Index (Heuristic 0-100) & Calibrated Empirical Win Rate
        conviction = calculate_factor_conviction_score(metrics)
        mos = metrics.get("mos_pct", 0.0)
        de = metrics.get("debt_equity")
        dy = metrics.get("dividend_yield") or 0.0
        ey = (100.0 / metrics["pe_ratio"]) if metrics.get("pe_ratio") and metrics["pe_ratio"] > 0 else 0.0
        passes_macro = (ey >= macro_rates.get("equity_hurdle_rate_pct", 15.1))
        rsi = metrics.get("rsi_14", 50.0)

        emp_data = get_calibrated_empirical_probability(
            mos_pct=mos,
            debt_equity=de,
            passes_macro=passes_macro,
            rsi_14=rsi,
        )

        cur_px = metrics["current_price"]
        limit_px = metrics.get("target_dip") or round(cur_px * 0.98, 1)

        # Execution pricing
        break_even_px = round(limit_px * (1.0 + FEE_BUY_PCT) / (1.0 - FEE_SELL_PCT), 2)
        tp1_px = round(limit_px * 1.09, 2)  # +9% profit target
        tp2_px = round(limit_px * 1.18, 2)  # +18% swing runner
        sl_px = round(limit_px * 0.95, 2)   # -5% hard stop

        risk_reward = round((tp1_px - limit_px) / max(0.01, (limit_px - sl_px)), 2)

        scored_candidates.append({
            "ticker": ticker,
            "sector": sector,
            "current_price": cur_px,
            "limit_entry": limit_px,
            "break_even": break_even_px,
            "tp1": tp1_px,
            "tp2": tp2_px,
            "stop_loss": sl_px,
            "risk_reward": risk_reward,
            "conviction_score": conviction,
            "heuristic_conviction_score": conviction,
            "empirical_prob": emp_data.get("empirical_probability_pct"),
            "empirical_prob_status": emp_data.get("status"),
            "empirical_prob_ci": emp_data.get("confidence_interval_95"),
            "profit_probability": conviction,  # Backward compatibility
            "graham_val": metrics.get("graham_val", 0.0),
            "mos_pct": metrics.get("mos_pct", 0.0),
            "dividend_yield": metrics.get("dividend_yield") or 0.0,
            "debt_equity": metrics.get("debt_equity") or 0.0,
            "volatility_pct": metrics.get("volatility_pct", 0.0),
        })

    conn.close()

    # Sort candidates by Conviction Score DESC, then MoS DESC
    scored_candidates.sort(key=lambda x: (x["conviction_score"], x["mos_pct"]), reverse=True)
    
    # Enforce sector cap: Max 2 stocks per industry sector
    top_picks = []
    sector_counts: Dict[str, int] = {}
    for candidate in scored_candidates:
        sec = candidate["sector"]
        if sector_counts.get(sec, 0) < 2:
            top_picks.append(candidate)
            sector_counts[sec] = sector_counts.get(sec, 0) + 1
            if len(top_picks) >= top_n:
                break

    # Calculate allocation for budget
    # Reserve 20% defensive cash buffer in bearish regime
    cash_buffer_pct = 0.20 if regime.get("regime") == "BEARISH_DRIFT" else 0.10
    investable_capital = capital_bdt * (1.0 - cash_buffer_pct)
    per_stock_budget = investable_capital / max(1, len(top_picks))

    allocations = []
    for pick in top_picks:
        shares = max(1, int(per_stock_budget // pick["limit_entry"]))
        actual_outlay = round(shares * pick["limit_entry"], 2)
        allocations.append({
            **pick,
            "shares": shares,
            "outlay_bdt": actual_outlay,
        })

    return {
        "asof_date": latest_date,
        "capital_bdt": capital_bdt,
        "investable_bdt": investable_capital,
        "cash_buffer_bdt": capital_bdt * cash_buffer_pct,
        "regime": regime,
        "macro": macro_rates,
        "top_picks": allocations,
    }


def format_user_proxy_report(result: Dict[str, Any]) -> str:
    """Formats the User Proxy simulation report in crisp Bengali with English financial terms."""
    lines = []
    lines.append("=" * 80)
    lines.append(f"👤 USER PROXY INVESTMENT SIMULATION & PROFIT MAXIMIZATION ENGINE")
    lines.append(f"📅 As-of Date: {result['asof_date']} | Total Capital: ৳{result['capital_bdt']:,.2f}")
    lines.append("=" * 80)

    reg = result["regime"]
    macro = result["macro"]
    lines.append(f"📊 Market Regime: [{reg.get('regime', 'UNKNOWN')}] | DSEX: {reg.get('dsex', 0.0):.2f} (20-DMA: {reg.get('dma_20', 0.0):.2f})")
    lines.append(f"🏦 Bangladesh Bank T-Bill (Rf): {macro.get('t_bill_91d_pct', 11.6):.2f}% | Minimum Equity Hurdle: {macro.get('equity_hurdle_rate_pct', 15.1):.2f}%")
    lines.append(f"🛡️ Defensive Cash Buffer: ৳{result['cash_buffer_bdt']:,.2f} | Actionable Equity Tranche: ৳{result['investable_bdt']:,.2f}")
    lines.append("-" * 80)

    lines.append(f"\n🎯 সর্বোচ্চ ফান্ডামেন্টাল কনভিকশন (Fundamental Conviction Score) নির্বাচিত স্টক:")
    lines.append(f"⚠️ [বিজ্ঞপ্তি: কনভিকশন স্কোর মাল্টি-ফ্যাক্টর র‍্যাংকিং (০-১০০); কাল্পনিক প্রফিট গ্যারান্টি নয়। ক্যালিব্রেটেড উইন-রেট N>=30 হলে প্রদর্শিত হবে]")
    lines.append(f"{'Ticker':<10} {'Price':<8} {'Buy Limit':<10} {'Conviction':<11} {'Empirical Win':<16} {'BreakEven':<10} {'Target(TP1)':<12} {'R:R':<5}")
    lines.append("-" * 80)

    for p in result["top_picks"]:
        emp_str = f"{p['empirical_prob']:.1f}%" if p.get('empirical_prob') is not None else "INSUFFICIENT_N"
        lines.append(
            f"{p['ticker']:<10} ৳{p['current_price']:<7.1f} ৳{p['limit_entry']:<9.1f} {p['conviction_score']:>6.1f}/100 {emp_str:>16} ৳{p['break_even']:<9.2f} ৳{p['tp1']:<11.2f} {p['risk_reward']:>4.1f}x"
        )
    lines.append("=" * 80)

    lines.append("\n📋 সুনির্দিষ্ট ট্রেড প্ল্যান ও নির্দেশিকা (WHEN TO BUY & WHEN TO SELL):")
    for i, p in enumerate(result["top_picks"], 1):
        emp_str = f"{p['empirical_prob']:.1f}% [95% CI: {p.get('empirical_prob_ci', [0,0])[0]}% - {p.get('empirical_prob_ci', [0,0])[1]}%]" if p.get('empirical_prob') is not None else "INSUFFICIENT_DATA (N < 30)"
        lines.append(f"\n[{i}] {p['ticker']} ({p['sector']}) — কনভিকশন: {p['conviction_score']}/100 | ওওএস ক্যালিব্রেটেড উইন রেট: {emp_str}")
        lines.append(f"  ├─ মৌলিক ভিত্তি: Graham MoS: +{p['mos_pct']:.1f}% | Dividend Yield: {p['dividend_yield']:.2f}% | Debt/Equity: {p['debt_equity']:.2f}")
        lines.append(f"  ├─ বরাদ্দ: {p['shares']} শেয়ার (মোট খরচ: ৳{p['outlay_bdt']:,.2f})")
        lines.append(f"  ├─ 🟢 কখন কিনবেন (WHEN TO BUY):")
        lines.append(f"  │    • Entry Range: ৳{p['limit_entry']:.1f} থেকে ৳{p['current_price']:.1f}-এর মধ্যে Limit Order বসান।")
        lines.append(f"  │    • Timing Gate: সকাল ১০:০০–১০:৩০ এর ওপেনিং গ্যাপ-আপে তাড়াহুড়ো করে কিনবেন না। বেলা ১১:৩০ থেকে ১:০০ টার মধ্যে ডিপে কিনুন।")
        lines.append(f"  │    • Buy Friction: ০.৪১৫% ব্রোকারেজ ফি অন্তর্ভুক্ত।")
        lines.append(f"  └─ 🔴 কখন বিক্রি করবেন (WHEN TO SELL):")
        lines.append(f"       • Break-even Point: ৳{p['break_even']:.2f} (ট্রেডিং ফি ০.৪১৫% Buy + ০.৪৬৫% Sell সহ আসল ফেরত)।")
        lines.append(f"       • Take-Profit 1 (TP1): ৳{p['tp1']:.2f} (+9.0% লাভে ৫০% শেয়ার বিক্রি করে প্রফিট লক করুন)।")
        lines.append(f"       • Take-Profit 2 (TP2): ৳{p['tp2']:.2f} (+18.0% লাভে বাকি শেয়ার ছেড়ে দিন বা Trailing Stop ধরুন)।")
        lines.append(f"       • Hard Stop-Loss (SL): ৳{p['stop_loss']:.2f} (-5.0% এ নেমে গেলে সাথে সাথে এক্সিট)।")
        lines.append(f"       • সার্কিট ব্রেকার রুল: লোয়ার সার্কিট (-10% বা -3%) লক থাকলে জিরো বিডে পেনিক সেল করবেন না; পরবর্তী লিকুইড সেশনে বের হোন।")

    lines.append("\n" + "=" * 80)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="User Proxy Investment Simulation & Profit Maximizer")
    parser.add_argument("--amount", type=float, default=50000.0, help="Capital amount in BDT (e.g. 1000, 50000, 1000000)")
    parser.add_argument("--top", type=int, default=3, help="Number of top candidates to present (default 3)")
    args = parser.parse_args()

    result = evaluate_user_investment_plan(capital_bdt=args.amount, top_n=args.top)
    report_text = format_user_proxy_report(result)
    print(report_text)

    # Save markdown report
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    md_file = REPORT_DIR / f"{today_str}_user_proxy_simulation.md"
    md_file.write_text(report_text, encoding="utf-8")
    print(f"\n💾 Simulation report saved to: {md_file}")


if __name__ == "__main__":
    main()
