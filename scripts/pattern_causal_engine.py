"""
DSE Pattern DNA, Causal Attribution & Worth-vs-Greed Engine

Provides deep quantitative pattern analysis, multi-interval cycle decomposition,
causal macroeconomic attribution (the "WHY" behind historical rises/falls),
and intrinsic worth vs market greed disparity checks.

Capabilities:
  1. Worth vs Greed Disparity Analyzer:
     - Intrinsic Fair Value (Graham / Tangible Book / DCF proxy) vs Current Price.
     - Greed Index (0-100): Volume velocity, overextension from 50/200 EMA, retail FOMO.
     - State Classification: UNDERVALUED_FEAR (Optimal Buy), FAIR_VALUE, 
       SPECULATIVE_GREED (Trap/Do Not Buy), OVERVALUED_EUPHORIA (Sell/Exit).
  2. Per-Company Pattern DNA & Multi-Interval Cycles:
     - Weekly (5D), Monthly (21D), Quarterly (63D), Half-Yearly (126D), Yearly (252D).
     - Peak-to-trough cycle duration, average rally amplitude %, median correction depth %.
     - Wave Phase Detection: ACCUMULATION_TROUGH, MARKUP_RALLY, DISTRIBUTION_TOP, MARKDOWN_DROP.
  3. Causal Attribution Framework (The "WHY"):
     - Country / Political condition (regime shifts, protests, stability vs unrest)
     - Economic & Monetary policy (interest rate hikes, repo rate, dollar/LC crunch, inflation)
     - Law & Order / Regulatory (BSEC floor price imposition/removal, margin loan rules, fraud probes)
     - Sector & International shocks (gas/power tariffs, raw material import costs, global commodities)
"""

import sqlite3
import json
import logging
import math
import statistics
from pathlib import Path
from datetime import datetime, timedelta

BASE_DIR   = Path(__file__).resolve().parent.parent
PROC_DIR   = BASE_DIR / "data" / "processed"
KNOW_DIR   = BASE_DIR / "data" / "knowledge"
REPORT_DIR = BASE_DIR / "reports"
DB_PATH    = PROC_DIR / "dse.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pattern_causal_engine")

# ── Macro-Causal Historical Timeline for Bangladesh Capital Markets ───────────
CAUSAL_HISTORICAL_EVENTS = [
    {
        "start": "2022-07-28", "end": "2024-01-18",
        "category": "REGULATORY_LAW_AND_ORDER",
        "event_name": "BSEC Floor Price Regime",
        "description": "Floor prices imposed on all stocks to stop free-fall. Artificially froze liquidity, trapped institutional capital, volume dried up to historic lows.",
        "market_impact": "LIQUIDITY_FREEZE",
        "direction": "BEARISH_STAGNATION"
    },
    {
        "start": "2024-01-18", "end": "2024-03-31",
        "category": "REGULATORY_LAW_AND_ORDER",
        "event_name": "Phased Floor Price Removal & Price Discovery",
        "description": "BSEC lifted floor prices in waves. Triggered sharp 1,000+ point DSEX correction as artificial valuations collapsed to fair market levels.",
        "market_impact": "SHARP_DELEVERAGING",
        "direction": "HIGH_VOLATILITY_DROP"
    },
    {
        "start": "2023-07-01", "end": "2024-05-08",
        "category": "ECONOMIC_MONETARY",
        "event_name": "SMART Interest Rate & Lending Cap Removal",
        "description": "Bangladesh Bank replaced fixed 9% lending cap with SMART rate, later moving to pure market-based repo tightening (repo hiked to 8.5%-10.0%). Corporate borrowing cost surged from 9% to 14-16%.",
        "market_impact": "DEBT_BURDEN_SHOCK",
        "direction": "PENALIZED_LEVERAGED_COMPANIES"
    },
    {
        "start": "2024-06-01", "end": "2024-08-05",
        "category": "POLITICAL_COUNTRY_CONDITION",
        "event_name": "Political Turmoil & National Student Revolution",
        "description": "Mass protests, nationwide curfews, internet blackouts, supply chain shutdowns leading to resignation of government on Aug 5.",
        "market_impact": "SYSTEMIC_DISRUPTION",
        "direction": "PANIC_SELLOFF_THEN_RELIEF_RALLY"
    },
    {
        "start": "2024-08-06", "end": "2024-09-15",
        "category": "POLITICAL_REGULATORY",
        "event_name": "Interim Government Formation & Anti-Corruption Drive",
        "description": "Interim government established under Dr. Yunus. BSEC leadership replaced, investigation task force formed against financial market manipulators and money laundering.",
        "market_impact": "POST_CRISIS_HOPE_RALLY",
        "direction": "SHARP_RELIEF_RALLY"
    },
    {
        "start": "2024-09-16", "end": "2025-06-30",
        "category": "ECONOMIC_MONETARY_BANKING",
        "event_name": "Banking NPL Revelations & Aggressive Monetary Tightening",
        "description": "True extent of banking non-performing loans exposed by Bangladesh Bank. Liquidity squeeze in weak banks, high 12-14% treasury bill yields drew liquidity away from stock market.",
        "market_impact": "TIGHT_LIQUIDITY_AND_FLIGHT_TO_SAFETY",
        "direction": "POLARIZED_MARKET"
    },
    {
        "start": "2025-07-01", "end": "2026-10-06",
        "category": "SECTOR_MACRO_RECOVERY",
        "event_name": "Economic Normalization & Moat Flight",
        "description": "FX reserves stabilized with IMF/World Bank assistance. Remittance surge. Selective institutional accumulation into debt-free cash cows with high dividend yields (Square, GP, Olympic, Padma Oil).",
        "market_impact": "SELECTIVE_FUNDAMENTAL_ACCUMULATION",
        "direction": "DIVIDEND_VALUE_OUTPERFORMANCE"
    }
]


def load_stock_series(ticker: str) -> list[dict]:
    """Loads complete chronological price series for a ticker from SQLite."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT date, open, high, low, close, volume
        FROM prices
        WHERE ticker = ?
        ORDER BY date ASC
    """, (ticker,)).fetchall()
    conn.close()

    series = []
    for r in rows:
        series.append({
            "date":   r[0],
            "open":   float(r[1]) if r[1] is not None else float(r[4] or 0),
            "high":   float(r[2]) if r[2] is not None else float(r[4] or 0),
            "low":    float(r[3]) if r[3] is not None else float(r[4] or 0),
            "close":  float(r[4]) if r[4] is not None else 0.0,
            "volume": float(r[5]) if r[5] is not None else 0.0
        })
    return series


def calculate_ema(prices: list[float], period: int) -> list[float]:
    """Calculates Exponential Moving Average series."""
    if not prices or len(prices) < period:
        return [prices[-1]] * len(prices) if prices else []
    
    k = 2.0 / (period + 1.0)
    ema = [sum(prices[:period]) / period]
    for p in prices[period:]:
        ema.append(p * k + ema[-1] * (1.0 - k))
    
    pad = [ema[0]] * (period - 1)
    return pad + ema


def calculate_rsi(prices: list[float], period: int = 14) -> float:
    """Calculates current 14-period RSI."""
    if len(prices) < period + 1:
        return 50.0
    gains = []
    losses = []
    for i in range(1, len(prices)):
        chg = prices[i] - prices[i - 1]
        if chg > 0:
            gains.append(chg)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(chg))
    
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


# ── 1. WORTH VS MARKET GREED DISPARITY ANALYZER ──────────────────────────────

def evaluate_worth_vs_greed(ticker: str, series: list[dict], fundamentals: dict) -> dict:
    """
    Evaluates whether the stock is fundamentally worth buying vs market greed/froth.
    Computes:
      - Intrinsic Fair Value (Graham / Asset / Cash Proxy)
      - Margin of Safety %
      - Market Greed Index (0–100)
      - Worth-vs-Greed Action Recommendation
    """
    if not series:
        return {"status": "NO_DATA"}

    current_price = series[-1]["close"]
    closes = [s["close"] for s in series]
    volumes = [s["volume"] for s in series]

    # Fundamental parameters
    eps = fundamentals.get("eps") or 0.0
    nav = fundamentals.get("nav") or 0.0
    pe  = fundamentals.get("pe") or 0.0
    div_yield = fundamentals.get("dividend_yield") or 0.0
    debt_equity = fundamentals.get("debt_equity") or 0.0

    # 1. Valuation & Intrinsic Worth Calculation
    # A) Benjamin Graham Defensive Price Ceiling (P/E <= 15 and P/B <= 1.5)
    graham_ceiling = math.sqrt(22.5 * eps * nav) if (eps > 0 and nav > 0) else 0.0

    # B) Benjamin Graham Growth Valuation Formula: V = [EPS * (8.5 + 2g) * 4.4] / Y
    # g = 6.0% (conservative long-term earnings growth rate)
    # Y = 12.0% (Bangladesh 10-year Treasury / risk-free benchmark yield)
    g_rate = 6.0
    y_yield = 12.0
    graham_growth_multiplier = (8.5 + 2.0 * g_rate) * (4.4 / y_yield)  # ~7.52x EPS
    graham_growth_value = round(eps * max(graham_growth_multiplier, 8.0), 2) if eps > 0 else 0.0

    # C) Graham Product Test: (P/E) * (P/BV) <= 22.5
    pe_val = (current_price / eps) if eps > 0 else 999.0
    pb_val = (current_price / nav) if nav > 0 else 999.0
    graham_product = round(pe_val * pb_val, 1)
    passes_graham_product = (graham_product <= 22.5)

    # Blended Intrinsic Worth:
    # High-ROE compounders (Square, GP) have asset-light models where Graham Ceiling understates value.
    # We blend defensive asset ceiling with normalized growth earnings value.
    roe_est = (eps / nav * 100.0) if nav > 0 else 0.0
    if roe_est >= 20.0 and eps > 0:
        # High ROE compounder: weighted 65% on earnings power / 35% on asset ceiling
        intrinsic_worth = round((graham_growth_value * 0.65) + ((graham_ceiling or graham_growth_value) * 0.35), 2)
    elif eps > 0 and graham_ceiling > 0:
        # Standard industrial / asset-heavy: 50% growth / 50% asset ceiling
        intrinsic_worth = round((graham_growth_value * 0.50) + (graham_ceiling * 0.50), 2)
    elif eps > 0:
        intrinsic_worth = round(graham_growth_value, 2)
    elif nav > 0:
        intrinsic_worth = round(nav * 0.8, 2)
    else:
        intrinsic_worth = round(current_price * 0.5, 2)

    margin_of_safety_pct = round(((intrinsic_worth - current_price) / current_price) * 100.0, 1) if current_price > 0 else 0.0

    # 2. Overextension & Momentum Froth Index (0 to 100)
    # Collinearity fix: Separates technical trend extension from volume turnover and retail dispersion.
    rsi = calculate_rsi(closes, period=14)
    ema50 = calculate_ema(closes, 50)[-1] if len(closes) >= 50 else current_price
    ema200 = calculate_ema(closes, 200)[-1] if len(closes) >= 200 else current_price

    price_to_ema50_pct = ((current_price - ema50) / ema50) * 100.0 if ema50 > 0 else 0.0
    price_to_ema200_pct = ((current_price - ema200) / ema200) * 100.0 if ema200 > 0 else 0.0

    # Volume velocity: 10-day volume vs 60-day baseline
    recent_vol = sum(volumes[-10:]) / 10.0 if len(volumes) >= 10 else 1.0
    base_vol = statistics.median(volumes[-60:]) if len(volumes) >= 60 else (recent_vol or 1.0)
    volume_ratio = recent_vol / (base_vol if base_vol > 0 else 1.0)

    # Price Intraday Volatility / Dispersion Proxy (High-Low range expansion)
    recent_highs = [s["high"] for s in series[-10:]]
    recent_lows  = [s["low"] for s in series[-10:]]
    intraday_range_pct = (sum((h - l) / (c or 1.0) for h, l, c in zip(recent_highs, recent_lows, closes[-10:])) / 10.0) * 100.0 if len(closes) >= 10 else 2.0

    # Orthogonal Froth Score Calculation (0 to 100):
    # Component A: Trend Extension from 50-EMA (0 to 30 pts)
    froth_trend = 0.0
    if price_to_ema50_pct > 20:
        froth_trend = 30.0
    elif price_to_ema50_pct > 10:
        froth_trend = 20.0
    elif price_to_ema50_pct > 0:
        froth_trend = 10.0

    # Component B: Volume Velocity Surge (0 to 35 pts)
    froth_volume = 0.0
    if volume_ratio > 3.0:
        froth_volume = 35.0
    elif volume_ratio > 1.8:
        froth_volume = 25.0
    elif volume_ratio > 1.2:
        froth_volume = 15.0
    else:
        froth_volume = 5.0

    # Component C: Intraday Churn & Volatility Spread (0 to 35 pts)
    froth_dispersion = 0.0
    if intraday_range_pct > 5.0:
        froth_dispersion = 35.0
    elif intraday_range_pct > 3.5:
        froth_dispersion = 25.0
    elif intraday_range_pct > 2.0:
        froth_dispersion = 15.0
    else:
        froth_dispersion = 5.0

    greed_score = round(froth_trend + froth_volume + froth_dispersion, 1)

    # Price-vs-Earnings Merit Verification (Did price rise on real EPS merit or pure speculative hype?)
    if price_to_ema50_pct > 15.0 and eps <= 0:
        merit_status = "SPECULATIVE_JUNK_PUMP"
        merit_reason = "Price is surging aggressively without positive EPS backing. Pure speculative risk."
    elif price_to_ema50_pct > 15.0 and pe > 25.0:
        merit_status = "SPECULATIVE_MULTIPLE_EXPANSION"
        merit_reason = f"Price extended {price_to_ema50_pct:.1f}% above 50-EMA with high P/E ({pe:.1f}). Rising on hype/greed, not fundamental earnings."
    elif eps > 0 and pe <= 16.0:
        merit_status = "EARNINGS_BACKED_MERIT"
        merit_reason = f"Price supported by solid earnings (EPS: ৳{eps:.2f}, P/E: {pe:.1f}). Growth is fundamentally justified."
    else:
        merit_status = "NEUTRAL_MERIT"
        merit_reason = "Valuation is within normal historical ranges."

    # Capital Pacing & Timing Directives (When to Buy vs When to Wait)
    entry_floor = round(current_price * 0.98, 1)
    entry_ceil  = round(current_price * 1.01, 1)
    chase_limit = round(current_price * 1.025, 1)
    weekly_tgt  = round(current_price * 1.035, 1)
    monthly_tgt = round(current_price * 1.15, 1)
    long_tgt    = round(current_price * 1.30, 1)

    timing_directives = {
        "optimal_entry_corridor": f"৳{entry_floor} – ৳{entry_ceil}",
        "chase_cutoff_price":     chase_limit,
        "when_to_wait":           f"If price opens or rises above ৳{chase_limit}, DO NOT HOP IN. Wait 2–5 trading sessions for dip back to ৳{entry_floor}.",
        "weekly_target_short":    weekly_tgt,
        "monthly_target_swing":   monthly_tgt,
        "long_term_target_asset": long_tgt,
        "capital_pacing_rule":    "Deploy maximum 25%–30% of target budget on Day 1. Reserve remaining 70% for systematic pullbacks over the next 2–4 weeks."
    }

    # Classification
    if margin_of_safety_pct >= 15.0 and greed_score <= 45.0:
        status = "UNDERVALUED_FEAR"  # Golden accumulation window
        worth_decision = "HIGH_CONVICTION_BUY"
        reason = f"High Margin of Safety (+{margin_of_safety_pct}%) with depressed market greed ({greed_score}/100) and {merit_status}. Ideal entry."
    elif margin_of_safety_pct >= 0.0 and greed_score <= 60.0:
        status = "FAIR_VALUE_ACCUMULATION"
        worth_decision = "ACCUMULATE_ON_DIPS"
        reason = f"Solid intrinsic worth backing (MoS: +{margin_of_safety_pct}%) with balanced market sentiment."
    elif margin_of_safety_pct < -25.0 and greed_score >= 70.0:
        status = "OVERVALUED_EUPHORIA"
        worth_decision = "SELL_TAKE_PROFIT"
        reason = f"Price is {abs(margin_of_safety_pct)}% above intrinsic worth while market greed is euphoric ({greed_score}/100). Danger of sharp mean reversion."
    elif greed_score >= 75.0 or merit_status == "SPECULATIVE_JUNK_PUMP":
        status = "SPECULATIVE_GREED"
        worth_decision = "DO_NOT_BUY_WAIT_FOR_PULLBACK"
        reason = f"Extreme short-term greed ({greed_score}/100) or speculative pump without earnings merit. Risk of buying at local peak."
    elif margin_of_safety_pct < -30.0:
        status = "CHRONIC_OVERVALUATION"
        worth_decision = "AVOID"
        reason = f"Fundamental value severely lags stock price (MoS: {margin_of_safety_pct}%)."
    else:
        status = "NEUTRAL"
        worth_decision = "HOLD"
        reason = "Trading in neutral fair-value corridor."

    return {
        "current_price":         current_price,
        "intrinsic_worth":       intrinsic_worth,
        "margin_of_safety_pct":  margin_of_safety_pct,
        "extension_froth_score": greed_score,
        "greed_index":           greed_score,
        "rsi_14":                round(rsi, 1),
        "price_vs_ema50_pct":   round(price_to_ema50_pct, 1),
        "price_vs_ema200_pct":  round(price_to_ema200_pct, 1),
        "merit_status":         merit_status,
        "merit_reason":         merit_reason,
        "timing_directives":    timing_directives,
        "status":               status,
        "worth_decision":       worth_decision,
        "reason":               reason
    }


# ── 2. PER-COMPANY PATTERN DNA & MULTI-INTERVAL CYCLES ───────────────────────

def extract_multi_interval_patterns(series: list[dict]) -> dict:
    """
    Decomposes price series across 5 investment intervals:
      - Weekly (5 trading days)
      - Monthly (21 trading days)
      - Quarterly (63 trading days)
      - Half-Yearly (126 trading days)
      - Yearly (252 trading days)
    Calculates swing amplitude, trough-to-peak waves, and current wave cycle phase.
    """
    if len(series) < 30:
        return {"status": "INSUFFICIENT_HISTORY"}

    closes = [s["close"] for s in series]
    highs = [s["high"] for s in series]
    lows = [s["low"] for s in series]
    dates = [s["date"] for s in series]
    n = len(closes)

    # 1. Multi-Interval Returns & Volatility
    intervals = {
        "weekly_5d":       5,
        "monthly_21d":     21,
        "quarterly_63d":   63,
        "half_yearly_126d": 126,
        "yearly_252d":     252
    }

    interval_stats = {}
    current_px = closes[-1]

    for label, bars in intervals.items():
        if n > bars:
            past_px = closes[-bars - 1]
            high_in_range = max(highs[-bars:])
            low_in_range = min(lows[-bars:])
            ret_pct = round(((current_px - past_px) / past_px) * 100.0, 2)
            range_vol_pct = round(((high_in_range - low_in_range) / low_in_range) * 100.0, 2) if low_in_range > 0 else 0.0
            interval_stats[label] = {
                "return_pct": ret_pct,
                "high": high_in_range,
                "low": low_in_range,
                "range_volatility_pct": range_vol_pct
            }
        else:
            interval_stats[label] = None

    # 2. Cycle Wave Detection (Peak-to-Trough Analysis)
    # Detect local minima and maxima using rolling window of 15 bars
    win = 15
    local_peaks = []
    local_troughs = []

    for i in range(win, n - win):
        sub_highs = highs[i - win: i + win + 1]
        sub_lows  = lows[i - win: i + win + 1]
        if highs[i] == max(sub_highs):
            local_peaks.append({"idx": i, "date": dates[i], "price": highs[i]})
        if lows[i] == min(sub_lows):
            local_troughs.append({"idx": i, "date": dates[i], "price": lows[i]})

    # Average rally amplitude (trough to subsequent peak)
    rally_gains = []
    correction_drops = []
    cycle_days = []

    for t in local_troughs:
        # find closest next peak
        next_peaks = [p for p in local_peaks if p["idx"] > t["idx"]]
        if next_peaks and t["price"] > 0:
            p = next_peaks[0]
            gain = ((p["price"] - t["price"]) / t["price"]) * 100.0
            days = p["idx"] - t["idx"]
            if gain > 3.0:
                rally_gains.append(gain)
                cycle_days.append(days)

    for p in local_peaks:
        # find closest next trough
        next_troughs = [t for t in local_troughs if t["idx"] > p["idx"]]
        if next_troughs and p["price"] > 0:
            t = next_troughs[0]
            drop = ((t["price"] - p["price"]) / p["price"]) * 100.0
            if drop < -3.0:
                correction_drops.append(drop)

    median_rally = round(statistics.median(rally_gains), 1) if rally_gains else 12.5
    median_correction = round(statistics.median(correction_drops), 1) if correction_drops else -9.0
    avg_cycle_bars = round(statistics.mean(cycle_days), 0) if cycle_days else 35.0

    # 3. Current Wave Phase
    last_trough = local_troughs[-1] if local_troughs else None
    last_peak = local_peaks[-1] if local_peaks else None

    if last_trough and last_peak:
        if last_trough["idx"] > last_peak["idx"]:
            # Most recent pivot was a trough -> In Markup / Recovery phase
            gain_from_trough = ((current_px - last_trough["price"]) / last_trough["price"]) * 100.0
            if gain_from_trough <= 4.0:
                phase = "ACCUMULATION_TROUGH"
                phase_guidance = "Near local cyclical trough base. Maximum reward/risk entry point."
            elif gain_from_trough < median_rally * 0.7:
                phase = "MARKUP_RALLY_MID"
                phase_guidance = f"Midway through rally wave (+{gain_from_trough:.1f}% from base, historical target ~+{median_rally}%)."
            else:
                phase = "LATE_MARKUP"
                phase_guidance = f"Approaching historical rally limit (+{gain_from_trough:.1f}% vs median +{median_rally}%). Tighten stop."
        else:
            # Most recent pivot was a peak -> In Markdown / Pullback phase
            drop_from_peak = ((current_px - last_peak["price"]) / last_peak["price"]) * 100.0
            if abs(drop_from_peak) >= abs(median_correction) * 0.8:
                phase = "BOTTOMING_SUPPORT"
                phase_guidance = f"Drop ({drop_from_peak:.1f}%) matches historical correction depth ({median_correction}%). Prepare to accumulate."
            else:
                phase = "MARKDOWN_PULLBACK"
                phase_guidance = f"Ongoing pullback from peak ({drop_from_peak:.1f}%). Wait for stabilizing base."
    else:
        phase = "INDETERMINATE"
        phase_guidance = "Consolidating in long-term channel."

    # 4. Monthly Seasonality (Which calendar months have highest win rate)
    month_returns = {m: [] for m in range(1, 13)}
    for i in range(21, n, 21):
        dt = datetime.strptime(dates[i], "%Y-%m-%d")
        pct = ((closes[i] - closes[i - 21]) / closes[i - 21]) * 100.0
        month_returns[dt.month].append(pct)

    best_months = []
    for m, rets in month_returns.items():
        if rets:
            win_rate = len([r for r in rets if r > 0]) / len(rets)
            avg_ret = statistics.mean(rets)
            month_name = datetime(2026, m, 1).strftime("%b")
            best_months.append({"month": month_name, "avg_return": round(avg_ret, 1), "win_rate": round(win_rate * 100, 0)})

    best_months.sort(key=lambda x: x["avg_return"], reverse=True)

    return {
        "intervals":          interval_stats,
        "wave_metrics": {
            "median_rally_gain_pct":      median_rally,
            "median_correction_drop_pct": median_correction,
            "avg_wave_duration_bars":     avg_cycle_bars
        },
        "current_wave_phase": phase,
        "phase_guidance":     phase_guidance,
        "top_seasonal_months": best_months[:3],
        "weak_seasonal_months": best_months[-2:] if len(best_months) >= 2 else []
    }


# ── 3. CAUSAL ATTRIBUTION (THE "WHY") ────────────────────────────────────────

def analyze_causal_attributions(ticker: str, series: list[dict]) -> list[dict]:
    """
    Correlates company historical price swings to macro/political/regulatory
    historical events to uncover the causal 'WHY' behind past moves.
    """
    if len(series) < 60:
        return []

    dates = [s["date"] for s in series]
    date_to_px = {s["date"]: s["close"] for s in series}
    min_date = dates[0]
    max_date = dates[-1]

    causal_impacts = []

    for event in CAUSAL_HISTORICAL_EVENTS:
        ev_start = event["start"]
        ev_end   = event["end"]

        # Check if event overlaps with data
        if ev_end < min_date or ev_start > max_date:
            continue

        # Find closest valid dates in series
        valid_start = [d for d in dates if d >= ev_start]
        valid_end   = [d for d in dates if d <= ev_end]

        if not valid_start or not valid_end:
            continue

        p_start_date = valid_start[0]
        p_end_date   = valid_end[-1]

        if p_start_date >= p_end_date:
            continue

        px_start = date_to_px[p_start_date]
        px_end   = date_to_px[p_end_date]

        # Calculate performance during this historical event period
        perf_pct = round(((px_end - px_start) / px_start) * 100.0, 2) if px_start > 0 else 0.0

        # Behavioral response of this specific stock
        if perf_pct > 15.0:
            behavior = "STRONG_RESILIENCE_OR_BENEFICIARY"
        elif perf_pct > 0.0:
            behavior = "DEFENSIVE_STABILITY"
        elif perf_pct > -15.0:
            behavior = "MODERATE_CYCLICAL_DROP"
        else:
            behavior = "SEVERE_VULNERABILITY"

        causal_impacts.append({
            "event_name":     event["event_name"],
            "category":       event["category"],
            "period":         f"{p_start_date} to {p_end_date}",
            "stock_move_pct": perf_pct,
            "behavior":       behavior,
            "root_cause_why": event["description"],
            "market_impact":  event["market_impact"]
        })

    return causal_impacts


# ── 4. COMPLETE COMPANY PATTERN & WORTH AUDIT ────────────────────────────────

def run_pattern_causal_audit(ticker: str) -> dict:
    """
    Runs full comprehensive audit:
      1. Worth vs Greed Disparity
      2. Multi-Interval Patterns & Wave Cycles
      3. Causal Historical Attribution
      4. Forward Actionable Plan
    """
    series = load_stock_series(ticker)
    if not series:
        return {"error": f"No price series found for {ticker}"}

    # Load fundamentals
    conn = sqlite3.connect(DB_PATH)
    f_row = conn.execute("""
        SELECT pe_ratio, eps, nav, dividend_yield, debt_equity
        FROM fundamentals WHERE ticker = ?
        ORDER BY year DESC, quarter DESC LIMIT 1
    """, (ticker,)).fetchone()
    conn.close()

    fund = {}
    if f_row:
        fund = {
            "pe":             float(f_row[0]) if f_row[0] is not None else None,
            "eps":            float(f_row[1]) if f_row[1] is not None else None,
            "nav":            float(f_row[2]) if f_row[2] is not None else None,
            "dividend_yield": float(f_row[3]) if f_row[3] is not None else None,
            "debt_equity":    float(f_row[4]) if f_row[4] is not None else None
        }

    worth_greed   = evaluate_worth_vs_greed(ticker, series, fund)
    try:
        from anti_manipulation_engine import is_ticker_blacklisted
        series_asof = series[-1]["date"] if series else None
        is_blocked, bl_msg = is_ticker_blacklisted(ticker, asof_date=series_asof)
        worth_greed["is_blacklisted"] = is_blocked
        worth_greed["blacklist_reason"] = bl_msg if is_blocked else None
        if is_blocked:
            worth_greed["disparity_label"] = f"CRITICAL_MANIPULATION_RISK: {bl_msg}"
    except Exception as e:
        log.warning(f"Could not check blacklist for {ticker}: {e}")

    wave_patterns = extract_multi_interval_patterns(series)
    causal_why    = analyze_causal_attributions(ticker, series)

    # Save to knowledge directory
    out_dir = KNOW_DIR / ticker
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "pattern_causal_dna.json"

    result = {
        "ticker":              ticker,
        "audited_at":          datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "worth_vs_greed":      worth_greed,
        "multi_interval_wave": wave_patterns,
        "causal_attributions": causal_why
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    return result


def audit_portfolio_and_top_picks() -> dict:
    """Runs the audit across core portfolio stocks and sector leaders."""
    core_tickers = ["SQURPHARMA", "GP", "ACMELAB", "JAMUNAOIL", "PADMAOIL", "BRACBANK", "OLYMPIC", "BATBC", "BEXIMCO", "ORIONPHARM"]
    results = {}
    for t in core_tickers:
        try:
            results[t] = run_pattern_causal_audit(t)
        except Exception as e:
            log.warning(f"Error auditing {t}: {e}")
    return results


if __name__ == "__main__":
    import sys
    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else "SQURPHARMA"
    audit = run_pattern_causal_audit(ticker)
    print(json.dumps(audit, indent=2))
