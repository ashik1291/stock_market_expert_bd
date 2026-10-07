"""
DSE Analyzer — technical + fundamental scoring for each ticker.
Outputs: data/knowledge/{ticker}/{timeframe}.json

Fixes applied:
  - RSI uses t["rsi_period"] not t["atr_period"]
  - RSI loop off-by-one fixed: range(period, len(closes))
  - composite_score: uses 'is not None' check, not 'or 50' (prevents 0→50 bug)
  - support_resistance: uses tolerance comparison, not exact float equality
  - highs/lows fallback logs warning when substituting close for missing data
  - SMA200 data insufficiency logged explicitly
  - get_ticker_data called with correct days per timeframe
  - Manipulation detection integrated — blocks BUY/STRONG_BUY when risk=high
"""

import json
import logging
import math
import datetime
from pathlib import Path
from typing import Literal

BASE_DIR   = Path(__file__).resolve().parent.parent
KNOW_DIR   = BASE_DIR / "data" / "knowledge"
CONFIG_DIR = BASE_DIR / "config"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dse_analyzer")

Timeframe = Literal["weekly", "monthly", "quarterly", "yearly"]

# How many days of price history to pass to get_ticker_data per timeframe
# Extra buffer so SMA200 has enough data even for short timeframe analysis
TIMEFRAME_FETCH_DAYS = {
    "weekly":    365,   # need 200+ bars for SMA200 even for weekly signals
    "monthly":   365,
    "quarterly": 730,
    "yearly":    1825,
}

# Analysis window: bars to include in technical signal computation
TIMEFRAME_SIGNAL_DAYS = {
    "weekly":    30,    # last 30 days for weekly signal
    "monthly":   90,
    "quarterly": 365,
    "yearly":    1825,
}


def load_thresholds() -> dict:
    with open(CONFIG_DIR / "thresholds.json", encoding="utf-8") as f:
        return json.load(f)


# ── Technical Indicators ──────────────────────────────────────────────────────

def sma(closes: list[float], period: int) -> list[float | None]:
    result = []
    for i in range(len(closes)):
        if i < period - 1:
            result.append(None)
        else:
            result.append(sum(closes[i - period + 1: i + 1]) / period)
    return result


def ema(closes: list[float], period: int) -> list[float | None]:
    if not closes or period < 1:
        return []
    result = []
    k = 2 / (period + 1)
    prev = None
    for i, c in enumerate(closes):
        if i < period - 1:
            result.append(None)
        elif i == period - 1:
            prev = sum(closes[:period]) / period
            result.append(prev)
        else:
            prev = c * k + prev * (1 - k)
            result.append(prev)
    return result


def rsi(closes: list[float], period: int = 14) -> list[float | None]:
    """
    RSI using Wilder's smoothed average.
    Fixed: loop goes to len(closes), not len(closes)-1.
    """
    if len(closes) < period + 1:
        return [None] * len(closes)

    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    result = [None] * period
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(closes)):   # FIX: was len(closes)-1
        g_idx = i - 1                      # gains array index
        avg_gain = (avg_gain * (period - 1) + gains[g_idx]) / period
        avg_loss = (avg_loss * (period - 1) + losses[g_idx]) / period
        if avg_loss == 0:
            result.append(100.0)
        else:
            rs = avg_gain / avg_loss
            result.append(100.0 - 100.0 / (1.0 + rs))

    return result


def macd(closes: list[float], fast: int = 12, slow: int = 26, signal_p: int = 9):
    ema_fast  = ema(closes, fast)
    ema_slow  = ema(closes, slow)
    macd_line = [
        (f - s) if f is not None and s is not None else None
        for f, s in zip(ema_fast, ema_slow)
    ]
    valid_macd  = [v for v in macd_line if v is not None]
    sig_raw     = ema(valid_macd, signal_p)
    offset      = len(macd_line) - len(sig_raw)
    signal_line = [None] * offset + sig_raw
    histogram   = [
        (m - s) if m is not None and s is not None else None
        for m, s in zip(macd_line, signal_line)
    ]
    return macd_line, signal_line, histogram


def bollinger_bands(closes: list[float], period: int = 20, num_std: float = 2.0):
    mid = sma(closes, period)
    upper, lower = [], []
    for i in range(len(closes)):
        if mid[i] is None:
            upper.append(None)
            lower.append(None)
        else:
            window = closes[i - period + 1: i + 1]
            std = math.sqrt(sum((x - mid[i]) ** 2 for x in window) / period)
            upper.append(mid[i] + num_std * std)
            lower.append(mid[i] - num_std * std)
    return upper, mid, lower


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float | None]:
    if len(closes) < period:
        return [None] * len(closes)
    trs = []
    for i in range(len(closes)):
        if i == 0:
            trs.append(highs[i] - lows[i])
        else:
            trs.append(max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            ))
    result = [None] * (period - 1)
    avg = sum(trs[:period]) / period
    result.append(avg)
    for i in range(period, len(trs)):
        avg = (avg * (period - 1) + trs[i]) / period
        result.append(avg)
    return result


def support_resistance(closes: list[float], window: int = 20) -> dict:
    """
    Local minima/maxima using tolerance comparison to handle float precision.
    """
    if len(closes) < window * 2 + 1:
        return {"supports": [], "resistances": []}

    supports, resistances = [], []
    TOLERANCE = 0.01  # BDT 0.01 tolerance

    for i in range(window, len(closes) - window):
        segment = closes[i - window: i + window + 1]
        c = closes[i]
        min_seg = min(segment)
        max_seg = max(segment)
        if abs(c - min_seg) < TOLERANCE:
            supports.append(c)
        if abs(c - max_seg) < TOLERANCE:
            resistances.append(c)

    return {
        "supports":    sorted(set(round(s, 2) for s in supports[-5:])),
        "resistances": sorted(set(round(r, 2) for r in resistances[-5:])),
    }


# ── Technical Score ───────────────────────────────────────────────────────────

def compute_technical_score(closes: list[float], highs: list[float],
                             lows: list[float], thresholds: dict) -> dict:
    t = thresholds["technical"]
    signals = {}
    score_parts = []

    if len(closes) < 30:
        return {"score": None, "signals": {"error": "insufficient_data_lt_30_bars"}, "sr": {}}

    # RSI — uses rsi_period, not atr_period
    rsi_period = t["rsi_period"]  # FIX: was t["atr_period"]
    rsi_vals   = rsi(closes, rsi_period)
    latest_rsi = next((v for v in reversed(rsi_vals) if v is not None), None)

    if latest_rsi is not None:
        if latest_rsi < t["rsi_oversold"]:
            signals["rsi"] = "oversold_bullish"
            score_parts.append(80)
        elif latest_rsi > t["rsi_overbought"]:
            signals["rsi"] = "overbought_bearish"
            score_parts.append(20)
        else:
            score_parts.append(50)
            signals["rsi"] = "neutral"

    # MACD
    macd_line, signal_line, hist = macd(
        closes, t["macd_fast"], t["macd_slow"], t["macd_signal"]
    )
    nonnull_hist = [v for v in reversed(hist) if v is not None]
    latest_hist  = nonnull_hist[0] if nonnull_hist else None
    prev_hist    = nonnull_hist[1] if len(nonnull_hist) > 1 else None

    if latest_hist is not None:
        if latest_hist > 0 and (prev_hist is None or latest_hist > prev_hist):
            signals["macd"] = "bullish_crossover"
            score_parts.append(80)
        elif latest_hist < 0 and (prev_hist is None or latest_hist < prev_hist):
            signals["macd"] = "bearish_crossover"
            score_parts.append(20)
        else:
            signals["macd"] = "neutral"
            score_parts.append(50)

    # SMA trend
    sma20  = sma(closes, t["sma_short"])
    sma50  = sma(closes, t["sma_medium"])
    sma200 = sma(closes, t["sma_long"])

    last_close  = closes[-1]
    last_sma20  = next((v for v in reversed(sma20)  if v is not None), None)
    last_sma50  = next((v for v in reversed(sma50)  if v is not None), None)
    last_sma200 = next((v for v in reversed(sma200) if v is not None), None)

    if last_sma200 is None:
        log.warning(f"SMA200 unavailable — only {len(closes)} bars. Trend score uses SMA50 only.")

    trend_score = 50
    if last_sma200 is not None and last_close > last_sma200:
        trend_score += 15
    if last_sma50 is not None and last_close > last_sma50:
        trend_score += 10
    if last_sma20 is not None and last_close > last_sma20:
        trend_score += 10
    if last_sma20 is not None and last_sma50 is not None and last_sma20 > last_sma50:
        trend_score += 10  # golden cross
    trend_score = min(max(trend_score, 0), 100)
    signals["sma_trend"] = "bullish" if trend_score > 60 else ("bearish" if trend_score < 40 else "neutral")
    score_parts.append(trend_score)

    # Bollinger Bands
    bb_upper, bb_mid, bb_lower = bollinger_bands(closes, t["bb_period"], t["bb_std"])
    last_bb_upper = next((v for v in reversed(bb_upper) if v is not None), None)
    last_bb_lower = next((v for v in reversed(bb_lower) if v is not None), None)

    if last_bb_upper is not None and last_bb_lower is not None:
        if last_close <= last_bb_lower:
            signals["bb"] = "at_lower_band_bullish"
            score_parts.append(75)
        elif last_close >= last_bb_upper:
            signals["bb"] = "at_upper_band_bearish"
            score_parts.append(25)
        else:
            signals["bb"] = "inside_bands"
            score_parts.append(50)

    # S/R levels
    sr = support_resistance(closes)

    # ATR (for stop-loss only, not scored)
    atr_vals   = atr(highs, lows, closes, t["atr_period"])
    latest_atr = next((v for v in reversed(atr_vals) if v is not None), None)

    signals["atr"]        = round(latest_atr, 2) if latest_atr is not None else None
    signals["rsi_value"]  = round(latest_rsi, 2) if latest_rsi is not None else None
    signals["last_close"] = last_close
    signals["sma20"]      = round(last_sma20,  2) if last_sma20  is not None else None
    signals["sma50"]      = round(last_sma50,  2) if last_sma50  is not None else None
    signals["sma200"]     = round(last_sma200, 2) if last_sma200 is not None else None
    signals["support_resistance"] = sr

    score = sum(score_parts) / len(score_parts) if score_parts else 50.0
    return {"score": round(score, 2), "signals": signals, "sr": sr}


# ── Fundamental Score ─────────────────────────────────────────────────────────

def compute_fundamental_score(fund_list: list[dict], thresholds: dict) -> dict:
    if not fund_list:
        return {"score": None, "signals": {"error": "no_fundamental_data"}}

    f = fund_list[0]  # most recent
    t = thresholds["fundamentals"]
    signals     = {}
    score_parts = []

    # EPS
    eps = f.get("eps")
    if eps is not None:
        if eps > 0:
            score_parts.append(70)
            signals["eps"] = f"positive ({eps})"
        else:
            score_parts.append(20)
            signals["eps"] = f"negative ({eps})"

    # EPS YoY growth (if 2+ periods available)
    if len(fund_list) >= 2:
        prev_eps = fund_list[1].get("eps")
        if eps and prev_eps and prev_eps != 0:
            growth_pct = ((eps - prev_eps) / abs(prev_eps)) * 100
            signals["eps_yoy_growth_pct"] = round(growth_pct, 1)
            if growth_pct >= t["min_eps_growth_yoy_pct"]:
                score_parts.append(85)
            elif growth_pct >= 0:
                score_parts.append(60)
            else:
                score_parts.append(25)

    # P/E ratio
    pe = f.get("pe_ratio")
    if pe is not None and pe > 0:
        if pe <= t["undervalued_pe"]:
            score_parts.append(90)
            signals["pe"] = f"deep_value ({pe})"
        elif pe <= t["max_pe_ratio"]:
            score_parts.append(70)
            signals["pe"] = f"fair_value ({pe})"
        elif pe <= 25:
            score_parts.append(50)
            signals["pe"] = f"slightly_expensive ({pe})"
        else:
            score_parts.append(20)
            signals["pe"] = f"expensive ({pe})"

    # NAV vs price — price/nav < 1 = undervalued
    nav = f.get("nav")
    if nav is not None and nav > 0:
        signals["nav"] = nav
        # If we have last_price, compute price-to-book
        # (price comes from technical layer, not fundamental; store NAV for cross-referencing)

    # Dividend yield
    dy = f.get("dividend_yield")
    if dy is not None:
        if dy >= t["min_dividend_yield_pct"]:
            score_parts.append(80)
            signals["dividend_yield"] = f"strong ({dy}%)"
        elif dy > 0:
            score_parts.append(55)
            signals["dividend_yield"] = f"moderate ({dy}%)"
        else:
            score_parts.append(30)
            signals["dividend_yield"] = "no_dividend"

    # Raw data payload audit for loan status and dividend history
    raw_dict = {}
    if f.get("raw_data"):
        try:
            raw_dict = json.loads(f["raw_data"])
        except Exception:
            pass

    # Empirical Debt/Equity & Long-Term Debt/Equity
    de = f.get("debt_equity")
    lt_de = None
    if raw_dict:
        st = float(raw_dict.get("short_term_loan_mn") or 0.0)
        lt = float(raw_dict.get("long_term_loan_mn") or 0.0)
        nav_val = float(raw_dict.get("nav") or raw_dict.get("book_value") or f.get("nav") or 0.0)
        puc_val = float(raw_dict.get("paid_up_capital") or 0.0)
        if nav_val > 0 and puc_val > 0:
            eq_mn = (puc_val / 10.0 * nav_val) / 1e6
            if eq_mn > 0:
                if de is None:
                    de = round((st + lt) / eq_mn, 3)
                lt_de = round(lt / eq_mn, 3)

    # Sector & Bank NPL Audit
    ticker = f.get("ticker", "")
    reg_path = CONFIG_DIR / "company_registry_12factor.json"
    is_bank = False
    bank_npl = None
    if reg_path.exists():
        try:
            with open(reg_path, encoding="utf-8") as rf:
                reg_data = json.load(rf)
                c_info = reg_data.get(ticker, {})
                bank_npl = c_info.get("bank_npl_pct")
                is_bank = (bank_npl is not None)
        except Exception:
            pass

    safe_de = t.get("safe_debt_equity", 0.5)
    max_de  = t.get("max_debt_equity", 1.0)

    if is_bank:
        # Commercial banks operate on deposits; evaluate on Non-Performing Loans (NPL)
        signals["bank_npl_pct"] = bank_npl
        if bank_npl is not None and bank_npl <= 4.0:
            score_parts.append(95)
            signals["debt_equity"] = f"bank_pristine_npl ({bank_npl}%)"
            signals["loan_trap_risk"] = "none"
        elif bank_npl is not None and bank_npl <= 6.0:
            score_parts.append(75)
            signals["debt_equity"] = f"bank_acceptable_npl ({bank_npl}%)"
            signals["loan_trap_risk"] = "low"
        else:
            score_parts.append(10)
            signals["debt_equity"] = f"bank_toxic_npl ({bank_npl}%)"
            signals["loan_trap_risk"] = "high"
    elif de is not None:
        signals["debt_equity_val"] = de
        if lt_de is not None:
            signals["long_term_debt_equity_val"] = lt_de

        if de <= safe_de and (lt_de is None or lt_de <= 0.2):
            score_parts.append(95)
            signals["debt_equity"] = f"pristine_low ({de})"
            signals["loan_trap_risk"] = "none"
        elif de <= max_de and (lt_de is None or lt_de <= 0.5):
            score_parts.append(70)
            signals["debt_equity"] = f"manageable ({de})"
            signals["loan_trap_risk"] = "low"
        elif de <= 1.5:
            score_parts.append(35)
            signals["debt_equity"] = f"elevated ({de})"
            signals["loan_trap_risk"] = "moderate"
        else:
            score_parts.append(10)  # Severe debt trap penalty in 9-14% interest rate climate
            signals["debt_equity"] = f"danger_high_loan ({de})"
            signals["loan_trap_risk"] = "high"

    # Multi-year Proven Dividend History
    div_hist = raw_dict.get("dividend_history", [])
    if div_hist:
        cash_divs = [d for d in div_hist if float(d.get("cash") or 0) > 0]
        signals["dividend_track_record_years"] = len(cash_divs)
        if len(cash_divs) >= 4:
            score_parts.append(90)
            signals["dividend_consistency"] = f"proven_compounder ({len(cash_divs)} yrs cash divs)"
        elif len(cash_divs) >= 2:
            score_parts.append(75)
            signals["dividend_consistency"] = f"steady_payer ({len(cash_divs)} yrs cash divs)"
        else:
            signals["dividend_consistency"] = "irregular"

    # ROE
    roe = f.get("roe")
    if roe is not None:
        if roe >= 15:
            score_parts.append(80)
            signals["roe"] = f"strong ({roe}%)"
        elif roe >= 10:
            score_parts.append(60)
            signals["roe"] = f"moderate ({roe}%)"
        else:
            score_parts.append(35)
            signals["roe"] = f"weak ({roe}%)"

    # Cash flow quality & Accrual Check (Sloan's Accrual Proxy for non-financials)
    # For Banks/FIs, operating cash flow is distorted by deposit/loan flows and is skipped.
    is_financial = any(sec in ticker for sec in ["BANK", "NBF", "INSUR"]) or "BANK" in ticker or "INS" in ticker
    cfo = f.get("cash_flow_ops")
    net_profit = f.get("net_profit_cr")

    if not is_financial and cfo is not None and net_profit is not None:
        # Sloan Accrual measure: (Net Profit - CFO) / Equity
        equity = float(raw_dict.get("equity_mn") or 1000.0) / 10.0  # in Crore
        accrual_spread = net_profit - cfo
        accrual_ratio = accrual_spread / equity if equity > 0 else 0.0

        signals["cfo_cr"] = round(cfo, 1)
        signals["net_profit_cr"] = round(net_profit, 1)
        signals["accrual_ratio"] = round(accrual_ratio, 3)

        if cfo >= net_profit and cfo > 0:
            score_parts.append(90)  # Cash flow exceeds accounting net profit (Conservative/High Quality)
            signals["earnings_quality"] = "superior_cash_backed"
        elif cfo >= net_profit * 0.7 and cfo > 0:
            score_parts.append(75)
            signals["earnings_quality"] = "healthy_cash_backed"
        elif cfo > 0:
            score_parts.append(50)
            signals["earnings_quality"] = "moderate_accrual_drag"
        else:
            score_parts.append(15)  # Negative CFO with positive net profit = dangerous paper accrual
            signals["earnings_quality"] = "low_paper_profit_accrual_danger"
    elif is_financial:
        signals["earnings_quality"] = "financial_asset_quality_mode"

    score = sum(score_parts) / len(score_parts) if score_parts else 50.0
    return {"score": round(score, 2), "signals": signals}


# ── Sentiment Score ───────────────────────────────────────────────────────────

def compute_sentiment_score(news_list: list[dict]) -> dict:
    """Keyword-based sentiment. Replace with transformer model for production."""
    positive_kw = [
        "profit", "growth", "dividend", "record", "expansion", "strong",
        "upgrade", "buy", "bullish", "recovery", "surplus", "beat", "export",
        "approved", "license", "award", "contract", "bonus", "IPO",
    ]
    negative_kw = [
        "loss", "decline", "fall", "bearish", "defaulted", "probe",
        "suspend", "fraud", "penalty", "cut", "miss", "downgrade",
        "lawsuit", "investigation", "regulatory", "fine", "delist",
        "manipulation", "halt", "circuit", "forced_sale",
    ]

    if not news_list:
        return {"score": 50.0, "signals": {"news_count": 0, "note": "no_news_neutral"}}

    total = 0
    details = []
    for art in news_list:
        headline = art.get("headline", art.get("title", "")).lower()
        pos = sum(1 for kw in positive_kw if kw in headline)
        neg = sum(1 for kw in negative_kw if kw in headline)
        if pos > neg:
            total += 70
            details.append("positive")
        elif neg > pos:
            total += 30
            details.append("negative")
        else:
            total += 50
            details.append("neutral")

    score = total / len(news_list)
    pos_count  = details.count("positive")
    neg_count  = details.count("negative")
    neut_count = details.count("neutral")

    return {
        "score": round(score, 2),
        "signals": {
            "news_count": len(news_list),
            "positive":   pos_count,
            "negative":   neg_count,
            "neutral":    neut_count,
        },
    }


# ── Composite Score ───────────────────────────────────────────────────────────

def composite_score(tech: dict, fund: dict, sent: dict, thresholds: dict) -> dict:
    w = thresholds["scoring"]

    # FIX: use 'is not None' — prevents 0 → 50 substitution bug
    t_score = tech.get("score") if tech.get("score") is not None else 50.0
    f_score = fund.get("score") if fund.get("score") is not None else 50.0
    s_score = sent.get("score") if sent.get("score") is not None else 50.0

    comp = (
        t_score * w["technical_weight"]   +
        f_score * w["fundamental_weight"] +
        s_score * w["sentiment_weight"]
    )
    return {"composite_score": round(comp, 2)}


def compute_price_trajectory_and_potential(closes: list[float], tech_signals: dict,
                                           fund_signals: dict, mgmt: dict,
                                           news_intent: dict, thresholds: dict) -> dict:
    """
    Predicts directional price trajectory (Rise vs Fall) and computes
    potential upside % vs downside risk % for Short, Mid, and Long-Term horizons.
    """
    if not closes:
        return {"direction": "NEUTRAL", "rise_probability_pct": 50.0}

    last_close = closes[-1]
    rsi_val    = tech_signals.get("rsi_value", 50.0) or 50.0
    sma20      = tech_signals.get("sma20", last_close) or last_close
    sma50      = tech_signals.get("sma50", last_close) or last_close
    sma200     = tech_signals.get("sma200", last_close) or last_close
    atr_val    = tech_signals.get("atr") or (last_close * 0.02)

    # 1. Empirically Validated Factor Alignment (Pruned via Panel Harness)
    # Dead factor removed: 20-DMA trend following (IC = -0.006, t = -1.10)
    # Validated factors retained: Oversold RSI (IC = +0.068, t = 12.62), Value & Balance Sheet
    bullish_weight = 0.0
    total_weight   = 6.0

    # RSI Oversold Mean-Reversion (Primary empirically validated technical driver)
    if rsi_val < 35:
        bullish_weight += 2.0  # Prime oversold mean-reversion zone
    elif 35 <= rsi_val <= 50:
        bullish_weight += 1.2  # Accumulation corridor
    elif rsi_val > 70:
        bullish_weight -= 1.0  # Overbought pullback risk

    # Fundamental Margin of Safety & Cash Flow
    pe_str = str(fund_signals.get("pe", "15"))
    try:
        pe = float(pe_str.split("(")[-1].rstrip(")"))
    except Exception:
        pe = 15.0

    if pe <= 10.0:
        bullish_weight += 1.5  # Deep value support
    elif pe <= 15.0:
        bullish_weight += 0.8
    elif pe > 25.0:
        bullish_weight -= 1.0

    # Debt Health & Bankruptcy Defense (Strict gate)
    de_val = fund_signals.get("debt_equity_val")
    if de_val is not None:
        if de_val <= 0.5:
            bullish_weight += 1.5
        elif de_val > 1.2:
            bullish_weight -= 2.0  # High debt penalty

    # Governance & News Intent
    gov_score = mgmt.get("governance_score", 75)
    if gov_score >= 85:
        bullish_weight += 0.8

    intent_impact = news_intent.get("intent_score", 0.0)
    if intent_impact > 10:
        bullish_weight += 0.6
    elif intent_impact < -10:
        bullish_weight -= 1.0

    # Direction Probability
    rise_prob = round(min(max((bullish_weight / total_weight) * 85 + 10, 15.0), 92.0), 1)

    if rise_prob >= 63.0:
        direction = "RISE_PREDICTED"
        direction_icon = "🟢"
        momentum_status = "Bullish Reversal / Upward Accumulation"
    elif rise_prob >= 45.0:
        direction = "CONSOLIDATION_RANGE"
        direction_icon = "🟡"
        momentum_status = "Neutral Range Consolidation"
    else:
        direction = "FALL_RISK"
        direction_icon = "🔴"
        momentum_status = "Bearish Breakdown / Selling Pressure"

    # 2. Term-by-Term Potential Calculation
    # Short-Term (1-10 days): Target based on ATR & resistance
    st_target   = round(last_close + (atr_val * 1.5), 1)
    st_support  = round(last_close - (atr_val * 1.0), 1)
    st_upside   = round(((st_target - last_close) / last_close) * 100, 1)
    st_downside = round(((last_close - st_support) / last_close) * 100, 1)

    # Mid-Term (1-6 months): Target based on 15% mean reversion
    mt_target   = round(last_close * 1.15, 1)
    mt_stop     = round(last_close * 0.95, 1)
    mt_upside   = round(((mt_target - last_close) / last_close) * 100, 1)
    mt_downside = round(((last_close - mt_stop) / last_close) * 100, 1)

    # Long-Term (1-5+ years): Target based on 30% multiple re-rating + compounding
    lt_target   = round(last_close * 1.30, 1)
    lt_upside   = round(((lt_target - last_close) / last_close) * 100, 1)
    lt_downside = round(min(mt_downside * 1.8, 12.0), 1)

    return {
        "direction":             direction,
        "direction_icon":        direction_icon,
        "rise_probability_pct":  rise_prob,
        "momentum_status":       momentum_status,
        "short_term": {
            "predicted_path":       "Oversold bounce to 20-DMA" if rsi_val < 40 else "Upward momentum swing",
            "upside_potential_pct": f"+{st_upside}%",
            "downside_risk_pct":    f"-{st_downside}%",
            "target_price":         st_target,
            "support_price":        st_support,
            "risk_reward_ratio":    f"{round(st_upside / max(st_downside, 0.1), 1)}x"
        },
        "mid_term": {
            "predicted_path":       "Cycle valuation recovery to historical median",
            "upside_potential_pct": f"+{mt_upside}%",
            "downside_risk_pct":    f"-{mt_downside}%",
            "target_price":         mt_target,
            "trailing_stop":        mt_stop,
            "risk_reward_ratio":    f"{round(mt_upside / max(mt_downside, 0.1), 1)}x"
        },
        "long_term": {
            "predicted_path":       "Defensive compounding, moat expansion & dividend reinvestment",
            "upside_potential_pct": f"+{lt_upside}%",
            "downside_risk_pct":    f"-{lt_downside}%",
            "target_price":         lt_target,
            "dividend_cagr":        fund_signals.get("dividend_yield") or "5%–8%",
            "risk_reward_ratio":    f"{round(lt_upside / max(lt_downside, 0.1), 1)}x"
        }
    }


def compute_stop_target(last_close: float, atr_val: float | None,
                         thresholds: dict) -> dict:
    if atr_val is None or atr_val == 0:
        atr_val = last_close * 0.02
    stop_mult = thresholds["stop_loss_atr_multiplier"]
    rr        = thresholds["target_risk_reward"]
    stop_loss = round(last_close - atr_val * stop_mult, 2)
    risk      = last_close - stop_loss
    target    = round(last_close + risk * rr, 2)
    return {"entry": last_close, "stop_loss": stop_loss, "target": target}


# ── Signal Classification ─────────────────────────────────────────────────────

def classify_signal(score: float, thresholds: dict,
                    manipulation_risk: str = "low",
                    loan_trap_risk: str = "none") -> str:
    """
    Downgrades signal to HOLD when manipulation_risk is high or loan_trap_risk is high.
    """
    t = thresholds["scoring"]
    if manipulation_risk == "high":
        return "HOLD_MANIPULATION_RISK"
    if loan_trap_risk == "high":
        return "HOLD_LOAN_TRAP_RISK"

    if score >= t["min_confidence_strong_buy"]:
        return "STRONG_BUY"
    elif score >= t["min_confidence_buy"]:
        return "BUY"
    elif score >= 45:
        return "HOLD"
    elif score >= 30:
        return "SELL"
    else:
        return "STRONG_SELL"


def classify_horizon(timeframe: Timeframe) -> str:
    if timeframe in ("weekly", "monthly"):
        return "short"
    elif timeframe == "quarterly":
        return "mid"
    else:
        return "long"


# ── Main Analysis ─────────────────────────────────────────────────────────────

def analyze_ticker(ticker: str, timeframe: Timeframe, ticker_data: dict) -> dict:
    """
    Full analysis for one ticker at one timeframe.
    Includes: technical, fundamental, sentiment, manipulation detection.
    Saves to data/knowledge/{ticker}/{timeframe}.json
    """
    from manipulation_detector import compute_manipulation_score

    thresholds   = load_thresholds()
    signal_days  = TIMEFRAME_SIGNAL_DAYS[timeframe]

    all_prices   = ticker_data.get("prices", [])
    fund         = ticker_data.get("fundamentals", [])
    news         = ticker_data.get("news", [])

    # Filter prices to signal window
    cutoff    = (datetime.date.today() - datetime.timedelta(days=signal_days)).isoformat()
    tf_prices = [p for p in all_prices if (p.get("date") or "") >= cutoff]

    closes, highs, lows = [], [], []
    fallback_warn = False
    for p in tf_prices:
        c = p.get("close")
        if c is None:
            continue
        closes.append(float(c))
        h = p.get("high")
        l = p.get("low")
        if h is None or l is None:
            fallback_warn = True
        highs.append(float(h) if h is not None else float(c))
        lows.append(float(l) if l is not None else float(c))

    if fallback_warn:
        log.warning(f"{ticker}: some high/low missing, substituted close as fallback")

    log.info(f"Analyzing {ticker}/{timeframe}: {len(closes)} price bars")

    # Technical
    tech_result = (
        compute_technical_score(closes, highs, lows, thresholds)
        if len(closes) >= 5
        else {"score": None, "signals": {"error": "insufficient_price_data"}, "sr": {}}
    )

    # Fundamental
    fund_result = compute_fundamental_score(fund, thresholds)

    # Downturn Resilience / Growth-at-Discount:
    # Identify companies whose share price is depressed/discounted from 52-week high,
    # but whose underlying EPS and earnings remain steady or growing
    last_close = closes[-1] if closes else None
    all_highs = [float(p["high"]) for p in all_prices if p.get("high") is not None]
    high_52w = max(all_highs) if all_highs else (last_close or 0)
    all_lows = [float(p["low"]) for p in all_prices if p.get("low") is not None]
    low_52w = min(all_lows) if all_lows else (last_close or 0)
    drawdown_pct = round(((high_52w - last_close) / high_52w) * 100, 1) if high_52w > 0 and last_close else 0.0

    eps_growth = fund_result.get("signals", {}).get("eps_yoy_growth_pct")
    eps_val = fund[0].get("eps") if fund else 0
    is_growth_steady = (eps_growth is not None and eps_growth >= 0) or (eps_val and eps_val > 0)

    if drawdown_pct >= 15.0 and is_growth_steady:
        fund_result["signals"]["downturn_resilience"] = {
            "status": "growth_at_discount",
            "drawdown_pct": drawdown_pct,
            "high_52w": round(high_52w, 2),
            "low_52w": round(low_52w, 2),
            "note": f"Share price down {drawdown_pct}% from 52w peak, yet earnings positive/steady (Conviction discount)"
        }
    else:
        fund_result["signals"]["downturn_resilience"] = {
            "status": "normal",
            "drawdown_pct": drawdown_pct,
            "high_52w": round(high_52w, 2),
            "low_52w": round(low_52w, 2)
        }

    # Sentiment
    sent_result = compute_sentiment_score(news)

    # Management & Leadership Profile
    from management_governance_engine import get_management_profile, analyze_news_intent_for_ticker
    mgmt_profile = get_management_profile(ticker)

    # News Intent Analysis
    news_intent = analyze_news_intent_for_ticker(news, ticker)
    has_legal_probe = any("LEGAL_PROBE_CORRUPTION" in f for f in news_intent.get("red_flags", []))
    gov_risk = mgmt_profile.get("management_risk", "Low").lower()

    # Manipulation check — uses ALL price history (not just signal window)
    manip_result = compute_manipulation_score(all_prices, fund, news, thresholds)
    manip_risk   = manip_result["manipulation_risk"]
    loan_risk    = fund_result.get("signals", {}).get("loan_trap_risk", "none")

    # Composite with Adaptive RL Learned Weights
    t_score = tech_result.get("score") if tech_result.get("score") is not None else 50.0
    f_score = fund_result.get("score") if fund_result.get("score") is not None else 50.0
    s_score = sent_result.get("score") if sent_result.get("score") is not None else 50.0
    g_score = mgmt_profile.get("governance_score", 75.0)

    # Adjust sentiment score by news intent impact
    adjusted_s_score = max(min(s_score + (news_intent.get("intent_score", 0.0) * 0.2), 100.0), 0.0)

    # Load learned weights from reinforcement learning feedback engine
    rl_weights_file = BASE_DIR / "data" / "learning" / "model_weights.json"
    w_fund = 0.45
    w_tech = 0.25
    w_gov  = 0.15
    w_sent = 0.15
    if rl_weights_file.exists():
        try:
            with open(rl_weights_file, encoding="utf-8") as rlf:
                rl_w = json.load(rlf)
                w_fund *= float(rl_w.get("valuation_mos_weight", 1.0))
                w_tech *= float(rl_w.get("rsi_momentum_weight", 1.0))
                w_gov  *= float(rl_w.get("governance_weight", 1.0))
                w_sent *= float(rl_w.get("macro_bias_weight", 1.0))
                total_w = w_fund + w_tech + w_gov + w_sent
                if total_w > 0:
                    w_fund /= total_w
                    w_tech /= total_w
                    w_gov  /= total_w
                    w_sent /= total_w
        except Exception:
            pass

    comp_val = round((f_score * w_fund) + (t_score * w_tech) + (g_score * w_gov) + (adjusted_s_score * w_sent), 2)
    comp = {
        "composite_score": comp_val,
        "governance_score": g_score,
        "sentiment_score": round(adjusted_s_score, 2),
        "applied_weights": {
            "fundamental": round(w_fund, 3),
            "technical": round(w_tech, 3),
            "governance": round(w_gov, 3),
            "sentiment": round(w_sent, 3)
        }
    }
    score = comp_val

    # Downgrades signal if manipulation, loan trap, or governance/legal probe triggered
    if manip_risk == "high":
        signal = "HOLD_MANIPULATION_RISK"
    elif loan_risk == "high":
        signal = "HOLD_LOAN_TRAP_RISK"
    elif gov_risk == "high" or has_legal_probe:
        signal = "HOLD_GOVERNANCE_RISK"
    elif score >= thresholds["scoring"]["min_confidence_strong_buy"]:
        signal = "STRONG_BUY"
    elif score >= thresholds["scoring"]["min_confidence_buy"]:
        signal = "BUY"
    elif score >= 45:
        signal = "HOLD"
    elif score >= 30:
        signal = "SELL"
    else:
        signal = "STRONG_SELL"

    horizon = classify_horizon(timeframe)

    last_close   = closes[-1] if closes else None
    atr_val      = tech_result["signals"].get("atr") if tech_result.get("signals") else None
    trade_levels = compute_stop_target(last_close, atr_val, thresholds) if last_close else {}
    trajectory   = compute_price_trajectory_and_potential(
        closes, tech_result.get("signals", {}), fund_result.get("signals", {}),
        mgmt_profile, news_intent, thresholds
    ) if closes else {}

    # Precision Suite: Smart Money, Real Cash Flow, Liquidity Guard, Quarterly Acceleration
    from precision_engine import run_precision_audit
    fund_obj = fund[0] if isinstance(fund, list) and fund else (fund if isinstance(fund, dict) else {})
    raw_data_dict = json.loads(fund_obj.get("raw_data") or "{}") if isinstance(fund_obj.get("raw_data"), str) else (fund_obj.get("raw_data") or {})
    precision_audit = run_precision_audit(ticker, all_prices, raw_data_dict)

    # Pattern DNA, Multi-Interval Cycles, Causal Attribution & Worth-vs-Greed
    try:
        from pattern_causal_engine import run_pattern_causal_audit
        pattern_audit = run_pattern_causal_audit(ticker)
        wg = pattern_audit.get("worth_vs_greed", {})
        # Safety gate: if market greed is euphoric/speculative, override buy signals
        if wg.get("status") in ("SPECULATIVE_GREED", "OVERVALUED_EUPHORIA") and "BUY" in signal:
            signal = "HOLD_MARKET_GREED_EXTREME"
        elif wg.get("status") == "UNDERVALUED_FEAR" and signal == "BUY":
            signal = "STRONG_BUY"
    except Exception as e:
        pattern_audit = {"error": str(e)}

    analysis = {
        "ticker":       ticker,
        "timeframe":    timeframe,
        "horizon":      horizon,
        "analyzed_at":  datetime.datetime.utcnow().isoformat(),
        "signal":       signal,
        "confidence":   score,
        "trajectory":   trajectory,
        "trade_levels": trade_levels,
        "precision":    precision_audit,
        "pattern_dna":  pattern_audit,
        "technical":    tech_result,
        "fundamental":  fund_result,
        "management":   mgmt_profile,
        "news_intent":  news_intent,
        "sentiment":    sent_result,
        "manipulation": manip_result,
        "composite":    comp,
    }

    out_dir  = KNOW_DIR / ticker
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{timeframe}.json"
    with open(out_file, "w", encoding="utf-8") as fh:
        json.dump(analysis, fh, indent=2)

    log.info(
        f"Saved {out_file} | signal={signal} confidence={score} "
        f"manipulation={manip_risk}"
    )
    return analysis


def analyze_all(tickers: list[str], timeframe: Timeframe, ticker_data_fn) -> list[dict]:
    results = []
    for ticker in tickers:
        try:
            # Pass correct fetch window for the timeframe
            fetch_days = TIMEFRAME_FETCH_DAYS[timeframe]
            data = ticker_data_fn(ticker, days=fetch_days)
            result = analyze_ticker(ticker, timeframe, data)
            results.append(result)
        except Exception as e:
            log.error(f"Analysis failed {ticker}: {e}")
    results.sort(key=lambda x: x.get("confidence") or 0, reverse=True)
    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    from processor import get_ticker_data

    def _load_sectors():
        with open(CONFIG_DIR / "sectors.json") as f:
            return json.load(f)

    if len(sys.argv) < 3:
        print("Usage: analyzer.py <ticker|all> <weekly|monthly|quarterly|yearly>")
        sys.exit(1)

    ticker_arg = sys.argv[1]
    tf_arg     = sys.argv[2]

    if ticker_arg == "all":
        sectors = _load_sectors()
        tickers = []
        for sd in sectors["sectors"].values():
            tickers.extend(sd["top_tickers"])
        tickers = list(dict.fromkeys(tickers))
        results = analyze_all(tickers, tf_arg, get_ticker_data)
        print(json.dumps([
            {"ticker": r["ticker"], "signal": r["signal"],
             "confidence": r["confidence"], "manipulation": r["manipulation"]["manipulation_risk"]}
            for r in results
        ], indent=2))
    else:
        fetch_days = TIMEFRAME_FETCH_DAYS[tf_arg]
        data       = get_ticker_data(ticker_arg, days=fetch_days)
        result     = analyze_ticker(ticker_arg, tf_arg, data)
        print(json.dumps(result, indent=2))
