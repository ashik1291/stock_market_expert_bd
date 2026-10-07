"""
DSE Manipulation Detector — flags stocks with manipulation risk signals.

Checks:
  1. Volume/price divergence (price up >5% on below-avg volume)
  2. Serial-trading fingerprint (extreme high/low range on low volume)
  3. Circuit-breaker streak (upper limit 10% for 3+ consecutive days)
  4. Sponsor holding decline (needs historical fundamentals)
  5. Price surge with zero/no news
  6. Abnormal volume spike (>3x 30-day average)

Returns manipulation_risk: 'low' / 'medium' / 'high'
  high → block STRONG_BUY / BUY signal in recommender
"""

import logging
import datetime
from pathlib import Path
import json

BASE_DIR   = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"

log = logging.getLogger("manipulation_detector")


def load_thresholds() -> dict:
    with open(CONFIG_DIR / "thresholds.json", encoding="utf-8") as f:
        return json.load(f)


# ── Individual checks ─────────────────────────────────────────────────────────

def check_volume_price_divergence(prices: list[dict], thresholds: dict) -> dict:
    """
    Bullish divergence red flag: price up but volume below 30-day average.
    Strong price move with no volume conviction = suspicious.
    """
    cfg = thresholds["manipulation"]
    if len(prices) < 30:
        return {"flag": False, "detail": "insufficient_data"}

    recent  = prices[-1]
    past_30 = prices[-30:]

    avg_volume = sum(p.get("volume") or 0 for p in past_30) / max(len(past_30), 1)
    last_vol   = recent.get("volume") or 0
    last_chg   = _to_float(recent.get("change_pct")) or 0

    price_moved_up  = last_chg >= cfg["price_move_no_news_pct"]
    volume_low      = avg_volume > 0 and last_vol < avg_volume * 0.5

    flagged = price_moved_up and volume_low
    return {
        "flag":        flagged,
        "price_chg":   last_chg,
        "last_volume": last_vol,
        "avg_volume":  round(avg_volume, 0),
        "detail":      "price_up_low_volume" if flagged else "ok",
    }


def check_volume_spike(prices: list[dict], thresholds: dict) -> dict:
    """
    Volume spike >3x 30-day average without corresponding fundamental news = red flag.
    """
    cfg = thresholds["manipulation"]
    if len(prices) < 30:
        return {"flag": False, "detail": "insufficient_data"}

    past_30  = prices[-31:-1]  # exclude today
    today_p  = prices[-1]

    avg_vol  = sum(p.get("volume") or 0 for p in past_30) / max(len(past_30), 1)
    today_v  = today_p.get("volume") or 0

    spike_ratio = today_v / avg_vol if avg_vol > 0 else 0
    threshold   = cfg["volume_spike_vs_avg_pct"] / 100

    flagged = spike_ratio > threshold
    return {
        "flag":         flagged,
        "spike_ratio":  round(spike_ratio, 2),
        "avg_volume":   round(avg_vol, 0),
        "today_volume": today_v,
        "detail":       f"volume_{round(spike_ratio,1)}x_avg" if flagged else "ok",
    }


def check_serial_trading_fingerprint(prices: list[dict], thresholds: dict) -> dict:
    """
    Detects days with extreme high/low spread but low volume — hallmark of
    serial/wash trading used to manipulate prices on DSE.
    Checks last 5 days; flags if 3+ such days exist.
    """
    cfg = thresholds["manipulation"]
    range_threshold = cfg["price_range_spike_pct"] / 100.0
    suspicious_days = 0

    recent = prices[-10:] if len(prices) >= 10 else prices
    avg_vol = sum(p.get("volume") or 0 for p in recent) / max(len(recent), 1)

    for p in recent[-5:]:
        high  = _to_float(p.get("high"))
        low   = _to_float(p.get("low"))
        close = _to_float(p.get("close"))
        vol   = p.get("volume") or 0

        if high and low and close and close > 0:
            spread_pct = (high - low) / close
            if spread_pct > range_threshold and vol < avg_vol * 0.4:
                suspicious_days += 1

    flagged = suspicious_days >= 3
    return {
        "flag":            flagged,
        "suspicious_days": suspicious_days,
        "detail":          f"{suspicious_days}_high_spread_low_volume_days" if flagged else "ok",
    }


def check_circuit_breaker_streak(prices: list[dict], thresholds: dict) -> dict:
    """
    DSE imposes 10% upper/lower circuit breaker daily limit.
    Hitting upper limit 3+ consecutive days = artificial pump signal.
    """
    cfg     = thresholds["manipulation"]
    streak  = cfg["circuit_breaker_consecutive_days"]
    recent  = prices[-streak:] if len(prices) >= streak else prices
    hits    = 0

    for p in recent:
        chg_pct = abs(_to_float(p.get("change_pct")) or 0)
        if chg_pct >= 9.5:  # DSE 10% circuit — use 9.5% to catch near-limit
            hits += 1

    flagged = hits >= streak
    return {
        "flag":           flagged,
        "circuit_hits":   hits,
        "detail":         f"circuit_breaker_{hits}_days" if flagged else "ok",
    }


def check_sponsor_exit(fundamentals: list[dict], thresholds: dict) -> dict:
    """
    Sponsor holding dropped significantly quarter-over-quarter without disclosure.
    Insider selling ahead of price decline = red flag.
    """
    cfg = thresholds["manipulation"]
    alert_drop = cfg["sponsor_drop_alert_pct"]

    if len(fundamentals) < 2:
        return {"flag": False, "detail": "insufficient_fundamental_history"}

    # Most recent first
    latest = fundamentals[0]
    prev   = fundamentals[1]

    latest_hold = _to_float(latest.get("sponsor_holding_pct"))
    prev_hold   = _to_float(prev.get("sponsor_holding_pct"))

    if latest_hold is None or prev_hold is None:
        return {"flag": False, "detail": "sponsor_holding_not_available"}

    drop = prev_hold - latest_hold
    flagged = drop >= alert_drop

    return {
        "flag":     flagged,
        "prev":     prev_hold,
        "current":  latest_hold,
        "drop":     round(drop, 2),
        "detail":   f"sponsor_holding_dropped_{round(drop,1)}pct" if flagged else "ok",
    }


def check_price_surge_no_news(prices: list[dict], news: list[dict], thresholds: dict) -> dict:
    """
    Price moved >5% in last 3 days but zero recent news found = manipulation alert.
    Legitimate moves are usually accompanied by PSI (price-sensitive info).
    """
    cfg = thresholds["manipulation"]
    if len(prices) < 4:
        return {"flag": False, "detail": "insufficient_data"}

    cutoff = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()
    recent_prices = [p for p in prices[-5:] if (p.get("date") or "") >= cutoff]
    recent_news   = [n for n in news if (n.get("date") or "") >= cutoff]

    if not recent_prices:
        return {"flag": False, "detail": "no_recent_prices"}

    opens  = [_to_float(p.get("open") or p.get("close")) for p in recent_prices]
    closes = [_to_float(p.get("close")) for p in recent_prices]
    opens  = [v for v in opens if v]
    closes = [v for v in closes if v]

    if not opens or not closes:
        return {"flag": False, "detail": "no_valid_price_data"}

    price_change_pct = ((closes[-1] - opens[0]) / opens[0]) * 100 if opens[0] else 0
    big_move  = abs(price_change_pct) >= cfg["price_move_no_news_pct"]
    no_news   = len(recent_news) == 0

    flagged = big_move and no_news
    return {
        "flag":              flagged,
        "price_change_3d":   round(price_change_pct, 2),
        "news_count_3d":     len(recent_news),
        "detail":            f"price_{round(price_change_pct,1)}pct_zero_news" if flagged else "ok",
    }


# ── Composite Manipulation Score ──────────────────────────────────────────────

def compute_manipulation_score(prices: list[dict], fundamentals: list[dict],
                                news: list[dict], thresholds: dict) -> dict:
    """
    Runs all checks. Returns:
      manipulation_risk: 'low' / 'medium' / 'high'
      manipulation_score: 0–100 (higher = riskier)
      flags: dict of triggered checks
      block_buy: bool — True if high risk, recommend blocking BUY signal
    """
    t = thresholds

    checks = {
        "volume_price_divergence": check_volume_price_divergence(prices, t),
        "volume_spike":            check_volume_spike(prices, t),
        "serial_trading":          check_serial_trading_fingerprint(prices, t),
        "circuit_breaker":         check_circuit_breaker_streak(prices, t),
        "sponsor_exit":            check_sponsor_exit(fundamentals, t),
        "price_surge_no_news":     check_price_surge_no_news(prices, news, t),
    }

    # Weighted scoring — circuit breaker and sponsor exit are highest weight
    weights = {
        "volume_price_divergence": 10,
        "volume_spike":            15,
        "serial_trading":          20,
        "circuit_breaker":         25,
        "sponsor_exit":            20,
        "price_surge_no_news":     10,
    }

    score = 0
    triggered_flags = []
    for check_name, result in checks.items():
        if result.get("flag"):
            score += weights[check_name]
            triggered_flags.append(f"{check_name}: {result.get('detail','')}")

    block_threshold = t["manipulation"]["high_manipulation_score_block_buy"]

    if score >= block_threshold:
        risk = "high"
    elif score >= 30:
        risk = "medium"
    else:
        risk = "low"

    return {
        "manipulation_score": score,
        "manipulation_risk":  risk,
        "block_buy":          risk == "high",
        "flags":              triggered_flags,
        "checks":             checks,
    }


# ── Utils ─────────────────────────────────────────────────────────────────────

def _to_float(v) -> float | None:
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except Exception:
        return None
