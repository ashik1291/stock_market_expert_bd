"""
DSE Precision Quantitative Engine

Four Core Institutional Modules:
  1. Smart Money Flow Tracking (Monthly Shareholding Delta: Institute + Foreign vs Public)
  2. Free Cash Flow & Real Dividend Coverage (NOCFPS / Cash Dividend per share)
  3. Liquidity Slippage Guard (Max Recommended Order Size based on daily volume profile)
  4. Quarterly Earnings Acceleration (QoQ / YoY Quarterly EPS Progression & Run-Rate)
"""

import json
import logging
import sqlite3
import re
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent
PROC_DIR   = BASE_DIR / "data" / "processed"
CONFIG_DIR = BASE_DIR / "config"
DB_PATH    = PROC_DIR / "dse.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("precision_engine")


# ── 1. Smart Money Flow Tracking ──────────────────────────────────────────────

def compute_smart_money_flow(raw_data: dict) -> dict:
    """
    Analyzes monthly shareholding shifts between Sponsor, Institute, Foreign, and Public.
    Smart Money = Institutional + Foreign.
    """
    pattern_hist = raw_data.get("share_pattern_history") or []
    if len(pattern_hist) < 2:
        return {
            "status": "INSUFFICIENT_HISTORY",
            "smart_money_delta_pct": 0.0,
            "public_delta_pct": 0.0,
            "classification": "NEUTRAL_HOLDING",
            "conviction_bonus": 0.0,
            "signal": "No monthly delta available"
        }

    # Latest vs Previous month
    latest = pattern_hist[-1].get("pattern", {})
    prev   = pattern_hist[-2].get("pattern", {})

    inst_latest  = float(latest.get("institution") or 0.0)
    inst_prev    = float(prev.get("institution") or 0.0)
    for_latest   = float(latest.get("foreign") or 0.0)
    for_prev     = float(prev.get("foreign") or 0.0)
    pub_latest   = float(latest.get("public") or 0.0)
    pub_prev     = float(prev.get("public") or 0.0)
    spon_latest  = float(latest.get("sponsor") or 0.0)
    spon_prev    = float(prev.get("sponsor") or 0.0)

    delta_inst  = round(inst_latest - inst_prev, 2)
    delta_for   = round(for_latest - for_prev, 2)
    delta_pub   = round(pub_latest - pub_prev, 2)
    delta_spon  = round(spon_latest - spon_prev, 2)

    delta_smart = round(delta_inst + delta_for, 2)

    # Classification
    if delta_smart >= 0.25 and delta_pub <= 0.0:
        classification = "INSTITUTIONAL_ACCUMULATION"
        signal_text = f"Smart money accumulated +{delta_smart}% (Institutes: {delta_inst}%, Foreign: {delta_for}%) while retail decreased {delta_pub}%"
        bonus = +15.0
    elif delta_pub >= 1.0 and delta_smart < 0:
        classification = "RETAIL_DISTRIBUTION_TRAP"
        signal_text = f"Retail surged +{delta_pub}% while smart money dumped {delta_smart}%"
        bonus = -20.0
    elif delta_spon <= -2.0:
        classification = "SPONSOR_EXIT_DUMP"
        signal_text = f"Sponsors offloaded {delta_spon}% of company shares"
        bonus = -25.0
    else:
        classification = "STABLE_HOLDINGS"
        signal_text = f"Holding shift: Smart money {delta_smart:+}%, Retail {delta_pub:+}%"
        bonus = 0.0

    return {
        "status":                "ACTIVE",
        "latest_date":           pattern_hist[-1].get("date"),
        "smart_money_delta_pct": delta_smart,
        "institutional_pct":     inst_latest,
        "foreign_pct":           for_latest,
        "sponsor_pct":           spon_latest,
        "public_pct":            pub_latest,
        "public_delta_pct":      delta_pub,
        "classification":        classification,
        "conviction_bonus":      bonus,
        "signal":                signal_text
    }


# ── 2. Free Cash Flow & Real Dividend Coverage ────────────────────────────────

def compute_cash_flow_and_dividend_coverage(raw_data: dict, news_text: str = "") -> dict:
    """
    Evaluates real cash backing behind reported EPS and cash dividend payouts.
    Extracts NOCFPS (Net Operating Cash Flow Per Share) and computes coverage.
    """
    eps = float(raw_data.get("eps") or 0.0)
    price = float(raw_data.get("price") or 1.0)
    nav = float(raw_data.get("nav") or 1.0)

    # Search for NOCFPS in raw_data or disclosures
    nocfps = None
    if "nocfps" in raw_data:
        try:
            nocfps = float(raw_data["nocfps"])
        except Exception:
            pass

    if nocfps is None and news_text:
        m = re.search(r'NOCFPS\s+was\s+Tk\.?\s*([\d\.\-]+)', news_text, re.IGNORECASE)
        if m:
            try:
                nocfps = float(m.group(1))
            except Exception:
                pass

    # If not explicitly in text, estimate conservative operational cash conversion from EPS
    # Bluechip pharma/monopoly historical avg CFO/EPS is ~0.85
    cfo_estimated = False
    if nocfps is None:
        nocfps = round(eps * 0.85, 2)
        cfo_estimated = True

    # Cash Dividend per share
    div_hist = raw_data.get("dividend_history") or []
    latest_div_pct = 0.0
    if div_hist and isinstance(div_hist, list):
        latest_div_pct = float(div_hist[0].get("cash") or 0.0)

    face_value = float(raw_data.get("faceValue") or 10.0)
    dividend_per_share = round((latest_div_pct / 100.0) * face_value, 2)

    # Coverage ratio = NOCFPS / DPS
    if dividend_per_share > 0:
        coverage_ratio = round(nocfps / dividend_per_share, 2)
    else:
        coverage_ratio = 5.0 if nocfps > 0 else 0.0

    # Real Free Cash Flow Yield = NOCFPS / Price
    fcf_yield = round((nocfps / price) * 100, 2) if price > 0 else 0.0

    # Risk evaluation
    if nocfps < 0 and dividend_per_share > 0:
        status = "CRITICAL_DIVIDEND_TRAP_DEBT_FUNDED"
        signal_text = f"Operating Cash Flow is NEGATIVE (Tk {nocfps}), but declared Tk {dividend_per_share} dividend (Funded by bank debt)"
        bonus = -30.0
    elif coverage_ratio >= 1.2:
        status = "PRISTINE_REAL_CASH_COVERAGE"
        signal_text = f"Dividend is {round(coverage_ratio*100)}% cash-covered by real operations (NOCFPS: Tk {nocfps} vs DPS: Tk {dividend_per_share})"
        bonus = +15.0
    elif coverage_ratio >= 0.8:
        status = "ADEQUATE_CASH_COVERAGE"
        signal_text = f"Dividend is {round(coverage_ratio*100)}% cash-covered by operations"
        bonus = +5.0
    else:
        status = "TIGHT_CASH_COVERAGE"
        signal_text = f"Cash flow covers only {round(coverage_ratio*100)}% of dividend payout"
        bonus = -10.0

    return {
        "nocfps":                nocfps,
        "is_estimated":          cfo_estimated,
        "dividend_per_share":    dividend_per_share,
        "dividend_coverage_x":   coverage_ratio,
        "fcf_yield_pct":         fcf_yield,
        "cash_quality_status":   status,
        "conviction_bonus":      bonus,
        "signal":                signal_text
    }


# ── 3. Liquidity Depth & Slippage Guard ───────────────────────────────────────

def compute_liquidity_depth_guard(prices: list[dict], price: float) -> dict:
    """
    Computes traded liquidity volume profile and determines
    Max Non-Slippage Order Size so orders don't move price against the user.
    """
    if not prices:
        return {
            "liquidity_rating": "ILLIQUID",
            "max_single_order_shares": 500,
            "max_daily_accumulation_shares": 1500,
            "max_order_bdt": 50000,
            "slippage_risk": "HIGH"
        }

    past_20 = prices[-20:]
    avg_vol = sum(p.get("volume") or 0 for p in past_20) / max(len(past_20), 1)
    daily_turnover_bdt = avg_vol * price

    # Institutional standard: A single market order should NOT exceed 5% of daily volume
    # Total daily accumulation should NOT exceed 15% of daily volume
    # Eliminate artificial 100/300 share floors that force excessive participation on thin counters
    safe_order_shares = max(1, int(avg_vol * 0.05))
    safe_daily_shares = max(1, int(avg_vol * 0.15))
    max_single_order  = min(safe_order_shares, 50000)
    max_daily_accum   = min(safe_daily_shares, 150000)
    max_order_bdt     = round(max_single_order * price, 0)

    if daily_turnover_bdt >= 50000000:  # > 5 Crore BDT daily
        rating = "DEEP_INSTITUTIONAL_LIQUIDITY"
        risk = "VERY_LOW"
    elif daily_turnover_bdt >= 15000000:  # 1.5 - 5 Crore BDT
        rating = "HEALTHY_LIQUIDITY"
        risk = "LOW"
    elif daily_turnover_bdt >= 3000000:   # 30 Lakh - 1.5 Crore BDT
        rating = "MODERATE_LIQUIDITY"
        risk = "MEDIUM"
    else:
        rating = "THIN_RETAIL_LIQUIDITY"
        risk = "HIGH"

    return {
        "avg_daily_volume":              int(avg_vol),
        "daily_turnover_bdt_cr":         round(daily_turnover_bdt / 1e7, 2),
        "liquidity_rating":              rating,
        "slippage_risk":                 risk,
        "max_single_order_shares":       max_single_order,
        "max_daily_accumulation_shares": max_daily_accum,
        "max_order_bdt":                 max_order_bdt,
        "directive":                     f"Max single order: {max_single_order:,} shares (Tk {max_order_bdt:,.0f}) to prevent >1% execution slippage"
    }


# ── 4. Quarterly Earnings Acceleration ────────────────────────────────────────

def compute_quarterly_earnings_acceleration(raw_data: dict) -> dict:
    """
    Parses quarterly performance progression (Q1, Q2, Q3) to detect
    earnings breakouts or margin deceleration.
    """
    q1 = None
    q2 = None
    q3 = None
    nine = None

    # Search raw_data
    for k, v in raw_data.items():
        if k.lower() == "q1" and isinstance(v, (int, float)):
            q1 = float(v)
        elif k.lower() == "q2" and isinstance(v, (int, float)):
            q2 = float(v)
        elif k.lower() == "q3" and isinstance(v, (int, float)):
            q3 = float(v)

    # If missing, parse from raw text chunks
    raw_str = json.dumps(raw_data)
    if q1 is None:
        m = re.search(r'"Earnings Per Share \(EPS\) Basic".*?"q1":([\d\.\-]+)', raw_str)
        if m:
            try:
                q1 = float(m.group(1))
            except Exception:
                pass
    if q2 is None:
        m = re.search(r'"Earnings Per Share \(EPS\) Basic".*?"q2":([\d\.\-]+)', raw_str)
        if m:
            try:
                q2 = float(m.group(1))
            except Exception:
                pass
    if q3 is None:
        m = re.search(r'"Earnings Per Share \(EPS\) Basic".*?"q3":([\d\.\-]+)', raw_str)
        if m:
            try:
                q3 = float(m.group(1))
            except Exception:
                pass

    if q1 is None:
        return {
            "status": "INSUFFICIENT_QUARTERLY_DATA",
            "acceleration_status": "NORMAL_STABLE",
            "bonus": 0.0,
            "signal": "Standard annual EPS trajectory"
        }

    quarters = [q for q in [q1, q2, q3] if q is not None]
    if len(quarters) >= 2:
        qoq_growth = round(((quarters[-1] - quarters[-2]) / max(abs(quarters[-2]), 0.1)) * 100, 1)
    else:
        qoq_growth = 0.0

    if len(quarters) == 3 and q3 > q2 > q1:
        status = "ACCELERATING_EARNINGS_BREAKOUT"
        signal = f"EPS expanding sequentially each quarter: Q1 Tk {q1} -> Q2 Tk {q2} -> Q3 Tk {q3} (Strong Breakout)"
        bonus = +15.0
    elif qoq_growth >= 15.0:
        status = "SEQUENTIAL_EXPANSION"
        signal = f"Quarterly EPS grew +{qoq_growth}% QoQ (Tk {quarters[-2]} -> Tk {quarters[-1]})"
        bonus = +10.0
    elif qoq_growth <= -20.0:
        status = "MARGIN_COMPRESSION_WARNING"
        signal = f"Quarterly EPS dropped {qoq_growth}% QoQ (Tk {quarters[-2]} -> Tk {quarters[-1]})"
        bonus = -15.0
    else:
        status = "STABLE_QUARTERLY_RUNRATE"
        signal = f"Quarterly EPS steady around Tk {quarters[-1]} (QoQ: {qoq_growth:+0.1f}%)"
        bonus = 0.0

    return {
        "status":              status,
        "q1_eps":              q1,
        "q2_eps":              q2,
        "q3_eps":              q3,
        "qoq_growth_pct":      qoq_growth,
        "acceleration_status": status,
        "conviction_bonus":    bonus,
        "signal":              signal
    }


# ── Full Precision Suite Runner ───────────────────────────────────────────────

def run_precision_audit(ticker: str, prices: list[dict], raw_data: dict, news_text: str = "") -> dict:
    """Runs all 4 institutional precision engines for a company."""
    smart_money = compute_smart_money_flow(raw_data)
    cash_flow   = compute_cash_flow_and_dividend_coverage(raw_data, news_text)
    liquidity   = compute_liquidity_depth_guard(prices, float(raw_data.get("price") or 1.0))
    earnings_acc = compute_quarterly_earnings_acceleration(raw_data)

    total_precision_bonus = (
        smart_money.get("conviction_bonus", 0.0) +
        cash_flow.get("conviction_bonus", 0.0) +
        earnings_acc.get("conviction_bonus", 0.0)
    )

    return {
        "ticker":                ticker,
        "smart_money":           smart_money,
        "cash_flow":             cash_flow,
        "liquidity":             liquidity,
        "earnings_acceleration": earnings_acc,
        "total_precision_bonus": total_precision_bonus
    }
