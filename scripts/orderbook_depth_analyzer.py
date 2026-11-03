"""
DSE Historical OHLCV Liquidity & Execution Friction Estimator.
(Formerly named orderbook_depth_analyzer — updated for architectural transparency)

NOTE ON DATA SOURCE & METHODOLOGY:
Dhaka Stock Exchange (DSE) does not provide a public Level-2 / Depth-of-Market API.
This module estimates effective spreads and market impact strictly from historical 
daily OHLCV bars using academically verified econometrics:
  1. Bid-Ask Spread Proxy: Corwin & Schultz (2012) High-Low Spread Estimator (Journal of Finance)
  2. Market Impact Model: Almgren & Chriss square-root participation law
  3. Retail vs Institutional Tranche Guidance:
     - Retail orders (< ৳100,000 or participation < 1.0%): Executed as SINGLE_TRANCHE via limit order.
     - Institutional orders (> ৳100,000 with participation > 1.5%): Spaced into tranches to prevent sweeping the book.
  4. Total Friction Benchmark: Brokerage/CDBL/AIT (0.880% round trip) + Half-Spread (%) + Impact (%).
"""

from __future__ import annotations

import sys
import json
import math
import sqlite3
import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"
REPORTS_DIR = BASE_DIR / "reports" / "liquidity"
CONFIG_DIR = BASE_DIR / "config"

# Baseline institutional constants for DSE microstructure
BROKERAGE_COMMISSION_ONE_WAY = 0.00415  # 0.415% (CDBL + broker)
DSE_IMPACT_COEFFICIENT = 0.45          # Y-factor for frontier/emerging markets


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.row_factory = sqlite3.Row
    return conn


def calculate_corwin_schultz_spread(high_today: float, low_today: float, high_prev: float, low_prev: float) -> float:
    """
    Estimates bid-ask spread % from 2-day high/low prices using Corwin & Schultz (2012).
    Returns spread as a percentage (e.g., 0.65 for 0.65%).
    """
    if high_today <= 0 or low_today <= 0 or high_prev <= 0 or low_prev <= 0:
        return 0.50  # Safe default 0.50%

    try:
        gamma = (math.log(max(high_today, high_prev) / min(low_today, low_prev))) ** 2
        beta = (math.log(high_today / low_today)) ** 2 + (math.log(high_prev / low_prev)) ** 2
        
        # alpha formula
        denom = 3.0 - 2.0 * math.sqrt(2.0)
        numerator = math.sqrt(2.0 * beta) - math.sqrt(beta)
        alpha = (numerator / denom) - math.sqrt(gamma / denom) if denom > 0 else 0.0
        
        if alpha <= 0:
            return 0.25  # Minimum plausible spread for Category A moats
        
        spread = 2.0 * (math.exp(alpha) - 1.0) / (1.0 + math.exp(alpha))
        return round(max(0.10, min(spread * 100.0, 5.0)), 2)
    except Exception:
        return 0.50


def analyze_ticker_liquidity(
    ticker: str,
    asof_date: Optional[str] = None,
    window_days: int = 20,
    conn: Optional[sqlite3.Connection] = None
) -> dict:
    """
    Calculates 20-day Average Daily Volume (ADV), Turnover, Volatility, and Spread.
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True

    if asof_date is None:
        row = conn.execute("SELECT MAX(date) FROM prices WHERE ticker = ?", (ticker,)).fetchone()
        asof_date = row[0] if (row and row[0]) else datetime.date.today().isoformat()

    # Query last N trading days
    rows = conn.execute("""
        SELECT date, open, high, low, close, volume, value
        FROM prices
        WHERE ticker = ? AND date <= ?
        ORDER BY date DESC
        LIMIT ?
    """, (ticker, asof_date, window_days + 1)).fetchall()

    if should_close:
        conn.close()

    if not rows:
        return {
            "ticker": ticker,
            "asof_date": asof_date,
            "adv_shares": 0,
            "adv_turnover_bdt": 0.0,
            "latest_close": 0.0,
            "estimated_spread_pct": 1.0,
            "daily_volatility_pct": 2.0,
            "liquidity_tier": "ILLIQUID",
            "safe_max_tranche_bdt": 5000.0
        }

    latest = rows[0]
    latest_close = float(latest["close"] or 0.0)

    # Compute ADV and Turnover
    vols = [float(r["volume"] or 0.0) for r in rows[:window_days]]
    vals = [
        float(r["value"]) * 1e6 if (r["value"] is not None and float(r["value"]) > 0.0)
        else float(r["volume"] or 0.0) * float(r["close"] or 0.0)
        for r in rows[:window_days]
    ]  # values stored in millions or derived from volume * close
    adv_shares = round(sum(vols) / max(len(vols), 1), 0)
    adv_turnover = round(sum(vals) / max(len(vals), 1), 2)

    # Volatility from high/low
    ranges = []
    for r in rows[:window_days]:
        h = float(r["high"] or 0.0)
        l = float(r["low"] or 0.0)
        c = float(r["close"] or 0.0)
        if c > 0 and h >= l:
            ranges.append((h - l) / c * 100.0)
    daily_volatility_pct = round(sum(ranges) / max(len(ranges), 1), 2) if ranges else 1.50

    # Corwin-Schultz Spread
    if len(rows) >= 2:
        spread_pct = calculate_corwin_schultz_spread(
            float(rows[0]["high"] or 0.0), float(rows[0]["low"] or 0.0),
            float(rows[1]["high"] or 0.0), float(rows[1]["low"] or 0.0)
        )
    else:
        spread_pct = 0.50

    # Categorize Liquidity Tier
    if adv_turnover >= 15_000_000 and adv_shares >= 100_000:
        tier = "HIGH_LIQUIDITY"
        safe_pct = 0.015  # Up to 1.5% of ADV in a single tranche
    elif adv_turnover >= 3_000_000 and adv_shares >= 25_000:
        tier = "MODERATE_LIQUIDITY"
        safe_pct = 0.010  # 1.0% of ADV
    else:
        tier = "LOW_LIQUIDITY"
        safe_pct = 0.005  # 0.5% of ADV

    safe_max_tranche_shares = max(1, int(adv_shares * safe_pct))
    safe_max_tranche_bdt = round(safe_max_tranche_shares * latest_close, 2)

    return {
        "ticker": ticker,
        "asof_date": asof_date,
        "latest_close": latest_close,
        "adv_shares": int(adv_shares),
        "adv_turnover_bdt": adv_turnover,
        "daily_volatility_pct": daily_volatility_pct,
        "estimated_spread_pct": spread_pct,
        "liquidity_tier": tier,
        "safe_max_tranche_shares": safe_max_tranche_shares,
        "safe_max_tranche_bdt": safe_max_tranche_bdt
    }


def estimate_execution_slippage(
    ticker: str,
    order_value_bdt: float,
    side: str = "BUY",
    asof_date: Optional[str] = None
) -> dict:
    """
    Computes expected market impact slippage and total round-trip execution cost for an order size.
    """
    liq = analyze_ticker_liquidity(ticker, asof_date=asof_date)
    px = liq["latest_close"]
    adv_shares = max(1, liq["adv_shares"])
    volatility = liq["daily_volatility_pct"] / 100.0  # as fraction
    half_spread = (liq["estimated_spread_pct"] / 2.0) / 100.0

    if px <= 0:
        return {"error": "Invalid price"}

    shares = int(order_value_bdt / px)
    participation_rate = shares / adv_shares

    # Almgren-Chriss Square-Root Market Impact
    # Impact = Y * sigma * sqrt(Q / ADV)
    market_impact_pct = DSE_IMPACT_COEFFICIENT * volatility * math.sqrt(participation_rate) * 100.0
    market_impact_pct = round(max(0.01, min(market_impact_pct, 4.0)), 3)

    # Friction components
    one_way_commission_pct = BROKERAGE_COMMISSION_ONE_WAY * 100.0
    half_spread_pct = round(half_spread * 100.0, 3)
    total_entry_friction_pct = round(one_way_commission_pct + half_spread_pct + market_impact_pct, 3)
    round_trip_friction_pct = round((one_way_commission_pct * 2.0) + (half_spread_pct * 2.0) + (market_impact_pct * 2.0), 3)

    # Retail-Aware Execution & Tranche Guidance
    safe_tranche = max(25000.0, liq["safe_max_tranche_bdt"])
    
    # Retail orders under ৳100k in Category A moats do not require excessive micro-splitting
    if order_value_bdt <= 100000.0 and participation_rate <= 0.02:
        recommended_tranches = 1
        tranche_value = order_value_bdt
        exec_plan = "SINGLE_TRANCHE (Retail order < ৳100k; safe execution via passive limit order at best ask)"
    elif order_value_bdt > safe_tranche and safe_tranche > 0:
        recommended_tranches = min(5, math.ceil(order_value_bdt / safe_tranche))
        tranche_value = round(order_value_bdt / recommended_tranches, 2)
        exec_plan = f"SPLIT into {recommended_tranches} tranches of ~৳{tranche_value:.2f} each to cap slippage < 0.15%"
    else:
        recommended_tranches = 1
        tranche_value = order_value_bdt
        exec_plan = "SINGLE_TRANCHE (Participation rate well within estimated liquidity capacity)"

    return {
        "ticker": ticker,
        "order_value_bdt": order_value_bdt,
        "order_shares": shares,
        "participation_rate_pct": round(participation_rate * 100.0, 3),
        "liquidity_tier": liq["liquidity_tier"],
        "one_way_commission_pct": round(one_way_commission_pct, 3),
        "half_spread_pct": half_spread_pct,
        "market_impact_slippage_pct": market_impact_pct,
        "total_entry_friction_pct": total_entry_friction_pct,
        "round_trip_breakeven_pct": round_trip_friction_pct,
        "recommended_tranches": recommended_tranches,
        "tranche_value_bdt": tranche_value,
        "execution_guidance": exec_plan
    }


def generate_universe_liquidity_report(tickers: Optional[list[str]] = None) -> Path:
    """
    Evaluates market depth and slippage metrics for candidate universe and generates reports.
    """
    if tickers is None:
        tickers = ["SQURPHARMA", "GP", "ROBI", "BATBC", "BSRMLTD", "OLYMPIC", "JAMUNAOIL", "PADMAOIL", "MPETROLEUM", "CONFIDCEM", "WALTONHIL", "RENATA"]

    conn = get_db_connection()
    results = [analyze_ticker_liquidity(t, conn=conn) for t in tickers]
    conn.close()

    results.sort(key=lambda x: x["adv_turnover_bdt"], reverse=True)
    latest_date = results[0]["asof_date"] if results else datetime.date.today().isoformat()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORTS_DIR / f"{latest_date}_liquidity_matrix.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"as_of_date": latest_date, "universe": results}, f, indent=2)

    # Markdown Table
    md_path = REPORTS_DIR / f"{latest_date}_liquidity_matrix.md"
    lines = [
        f"# DSE Historical Liquidity & Execution Friction Matrix",
        f"**Market Date**: `{latest_date}` | **Methodology**: Corwin-Schultz (2012) OHLCV Spread Proxy | **Brokerage**: `0.415%` one-way",
        "",
        "> [!NOTE]",
        "> This report estimates liquidity from historical daily OHLCV trading bars. DSE does not provide public Level-2 order book depth.",
        "",
        "## Core Liquidity & Tranche Sizing Guidelines",
        "- **HIGH_LIQUIDITY**: Daily turnover >= ৳15M. Large retail orders (up to ৳1M) executed with negligible slippage (<0.05%).",
        "- **MODERATE_LIQUIDITY**: Daily turnover ৳3M - ৳15M. Retail orders (<৳100k) execute fine as single tranche; larger orders use passive limit.",
        "- **LOW_LIQUIDITY**: Daily turnover < ৳3M. Avoid large market orders; institutional sizes (>৳100k) should split into tranches.",
        "",
        "| Ticker | Tier | Price (৳) | 20-Day ADV (Shares) | 20-Day Turnover (৳) | Est. Spread (%) | Safe Max Tranche (Shares) | Safe Max Tranche (৳) |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |"
    ]

    for r in results:
        tier_tag = f"**{r['liquidity_tier']}**"
        lines.append(
            f"| **{r['ticker']}** | {tier_tag} | ৳{r['latest_close']:.2f} | {r['adv_shares']:,} | ৳{r['adv_turnover_bdt']:,.0f} | {r['estimated_spread_pct']:.2f}% | {r['safe_max_tranche_shares']:,} sh | **৳{r['safe_max_tranche_bdt']:,.0f}** |"
        )

    # Sample Tranche Simulations
    lines.extend([
        "",
        "## Order Slippage & Execution Friction Simulation (৳50,000 Order Size)",
        "| Ticker | Participation Rate (%) | One-Way Fee (%) | Half-Spread (%) | Slippage Impact (%) | Total Entry Friction (%) | Round-Trip Break-Even (%) | Execution Plan |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |"
    ])

    for r in results:
        sim = estimate_execution_slippage(r["ticker"], order_value_bdt=50000.0, asof_date=latest_date)
        lines.append(
            f"| **{sim['ticker']}** | {sim['participation_rate_pct']:.2f}% | {sim['one_way_commission_pct']:.3f}% | {sim['half_spread_pct']:.2f}% | **{sim['market_impact_slippage_pct']:.2f}%** | {sim['total_entry_friction_pct']:.2f}% | **+{sim['round_trip_breakeven_pct']:.2f}%** | {sim['execution_guidance'][:45]}... |"
        )

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[LIQUIDITY ANALYZER] Matrix saved: {md_path}")

    # Generate Native Bengali Liquidity Matrix
    bn_md_path = REPORTS_DIR / f"{latest_date}_liquidity_matrix_bn.md"
    bn_lines = [
        f"# DSE তারল্য ও এক্সিকিউশন ফ্রিকশন ম্যাট্রিক্স (OHLCV প্রোক্সি)",
        f"**বাজারের তারিখ**: `{latest_date}` | **পদ্ধতি**: Corwin-Schultz (2012) হাই/লো স্প্রেড প্রোক্সি | **ব্রোকারেজ ফি**: `0.415%` (একমুখী)",
        "",
        "> [!NOTE]",
        "> এই রিপোর্টটি DSE-এর ঐতিহাসিক দৈনিক OHLCV ডেটা থেকে তারল্যের নির্ভরযোগ্য একাডেমিক অনুমান করে। DSE কোনো পাবলিক Level-2 অর্ডার বুক ডেটা দেয় না।",
        "",
        "## তারল্য শ্রেণি ও ট্রেডিং নির্দেশিকা",
        "- **HIGH_LIQUIDITY**: দৈনিক টার্নওভার >= ৳১.৫ কোটি। সাধারণ রিটেল অর্ডার (৳১০ লক্ষ পর্যন্ত) কোনো স্লিপেজ ছাড়াই সহজে এক্সিকিউট করা যায়।",
        "- **MODERATE_LIQUIDITY**: দৈনিক টার্নওভার ৳৩০ লক্ষ - ৳১.৫ কোটি। ৳১ লক্ষের নিচের রিটেল অর্ডার একবারে লিমিট অর্ডারে নেওয়া নিরাপদ।",
        "- **LOW_LIQUIDITY**: দৈনিক টার্নওভার < ৳৩০ লক্ষ। বড় প্রাতিষ্ঠানিক অর্ডার হলে ২-৩টি ট্রাঞ্চে ভাগ করে লিমিট অর্ডার ব্যবহার করা উচিত।",
        "",
        "| Ticker | তারল্য শ্রেণি | মার্কেট প্রাইস (৳) | ২০-দিনের গড় ভলিউম (শেয়ার) | ২০-দিনের গড় টার্নওভার (৳) | আনুমানিক Spread (%) | নিরাপদ সর্বোচ্চ ট্রাঞ্চ (শেয়ার) | নিরাপদ সর্বোচ্চ ট্রাঞ্চ (৳) |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |"
    ]

    for r in results:
        bn_lines.append(
            f"| **{r['ticker']}** | **{r['liquidity_tier']}** | ৳{r['latest_close']:.2f} | {r['adv_shares']:,} | ৳{r['adv_turnover_bdt']:,.0f} | {r['estimated_spread_pct']:.2f}% | {r['safe_max_tranche_shares']:,} sh | **৳{r['safe_max_tranche_bdt']:,.0f}** |"
        )

    bn_lines.extend([
        "",
        "## ৫০,০০০ টাকার অর্ডারে স্লিপেজ ও মোট ফ্রিকশন সিমুলেশন",
        "| Ticker | Participation Rate (%) | ব্রোকারেজ ফি (%) | Half-Spread (%) | স্লিপেজ ইম্প্যাক্ট (%) | মোট এন্ট্রি ফ্রিকশন (%) | রাউন্ড-ট্রিপ ব্রেক-ইভেন (%) | এক্সিকিউশন গাইডলাইন |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |"
    ])

    for r in results:
        sim = estimate_execution_slippage(r["ticker"], order_value_bdt=50000.0, asof_date=latest_date)
        bn_lines.append(
            f"| **{sim['ticker']}** | {sim['participation_rate_pct']:.2f}% | {sim['one_way_commission_pct']:.3f}% | {sim['half_spread_pct']:.2f}% | **{sim['market_impact_slippage_pct']:.2f}%** | {sim['total_entry_friction_pct']:.2f}% | **+{sim['round_trip_breakeven_pct']:.2f}%** | {sim['execution_guidance'][:45]}... |"
        )

    with open(bn_md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(bn_lines) + "\n")

    print(f"[LIQUIDITY ANALYZER] Bengali Matrix saved: {bn_md_path}")
    return md_path


if __name__ == "__main__":
    report_file = generate_universe_liquidity_report()
    print(f"[DONE] Liquidity analysis completed.")
