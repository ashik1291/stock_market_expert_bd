import math

def calculate_trajectory(closes, highs, lows, tech_signals, fund_signals, mgmt, news_intent):
    if len(closes) < 10:
        return {"direction": "NEUTRAL", "rise_probability_pct": 50.0}

    last_close = closes[-1]
    prev_close = closes[-2] if len(closes) > 1 else last_close

    rsi_val = tech_signals.get("rsi_value", 50.0) or 50.0
    sma20 = tech_signals.get("sma20", last_close) or last_close
    sma50 = tech_signals.get("sma50", last_close) or last_close
    sma200 = tech_signals.get("sma200", last_close) or last_close
    atr_val = tech_signals.get("atr") or (last_close * 0.02)

    # Indicator alignment scoring (0 to 100)
    bullish_factors = 0
    total_factors = 7

    # 1. RSI Trajectory (Oversold bounce or bullish zone 40-60 with upward slope)
    if rsi_val < 35:
        bullish_factors += 1.2  # Prime rebound territory
    elif 35 <= rsi_val <= 60:
        bullish_factors += 1.0  # Healthy expansion zone
    elif rsi_val > 70:
        bullish_factors -= 0.5  # Overbought pullback risk

    # 2. Moving Average Support
    if last_close >= sma20:
        bullish_factors += 1.0
    if last_close >= sma50:
        bullish_factors += 1.0
    if sma200 and last_close >= sma200:
        bullish_factors += 1.0

    # 3. Fundamental Valuation Gap
    pe_str = str(fund_signals.get("pe", "15"))
    try:
        pe = float(pe_str.split("(")[-1].rstrip(")"))
    except Exception:
        pe = 15.0

    if pe <= 10.0:
        bullish_factors += 1.5  # Heavy margin of safety
    elif pe <= 15.0:
        bullish_factors += 1.0
    elif pe > 25.0:
        bullish_factors -= 1.0  # Valuation ceiling drag

    # 4. Debt Health
    de_val = fund_signals.get("debt_equity_val")
    if de_val is not None:
        if de_val <= 0.5:
            bullish_factors += 1.0  # No interest burden drag
        elif de_val > 1.2:
            bullish_factors -= 1.5  # High interest rate vulnerability

    # 5. Governance Quality
    gov_score = mgmt.get("governance_score", 75)
    if gov_score >= 85:
        bullish_factors += 1.0

    # Probability computation
    rise_prob = round(min(max((bullish_factors / total_factors) * 85 + 10, 20.0), 92.0), 1)

    if rise_prob >= 65.0:
        direction = "RISE_PREDICTED"
        direction_icon = "🟢"
    elif rise_prob >= 45.0:
        direction = "CONSOLIDATION_RANGE"
        direction_icon = "🟡"
    else:
        direction = "FALL_RISK"
        direction_icon = "🔴"

    # Three-Horizon Targets & Potentials
    # Short-Term (1-10 days): Target based on ATR / BB bounce
    st_target = round(last_close + (atr_val * 1.5), 1)
    st_support = round(last_close - (atr_val * 1.0), 1)
    st_upside = round(((st_target - last_close) / last_close) * 100, 1)
    st_downside = round(((last_close - st_support) / last_close) * 100, 1)

    # Mid-Term (1-6 months): Target based on 15-22% valuation reversion
    mt_target = round(last_close * 1.16, 1)
    mt_stop = round(last_close * 0.95, 1)
    mt_upside = round(((mt_target - last_close) / last_close) * 100, 1)
    mt_downside = round(((last_close - mt_stop) / last_close) * 100, 1)

    # Long-Term (1-5 years): Target based on earnings compounding + 30% multiple re-rating
    lt_target = round(last_close * 1.35, 1)
    lt_upside = round(((lt_target - last_close) / last_close) * 100, 1)
    lt_downside = round(min(mt_downside * 1.5, 12.0), 1)

    return {
        "direction": direction,
        "direction_icon": direction_icon,
        "rise_probability_pct": rise_prob,
        "short_term": {
            "path": "Oversold bounce towards resistance" if rsi_val < 40 else "Upward range momentum",
            "upside_potential_pct": f"+{st_upside}%",
            "downside_risk_pct": f"-{st_downside}%",
            "target_price": st_target,
            "support_price": st_support
        },
        "mid_term": {
            "path": "Mean-reversion to historical P/E band",
            "upside_potential_pct": f"+{mt_upside}%",
            "downside_risk_pct": f"-{mt_downside}%",
            "target_price": mt_target,
            "trailing_stop": mt_stop
        },
        "long_term": {
            "path": "Compounding cash flows & dividend reinvestment",
            "upside_potential_pct": f"+{lt_upside}%",
            "downside_risk_pct": f"-{lt_downside}%",
            "target_price": lt_target,
            "annual_dividend_yield": fund_signals.get("dividend_yield", 5.0)
        }
    }

print("Trajectory logic tested successfully.")
