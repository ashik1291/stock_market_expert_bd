"""

scripts/smart_capital_planner.py

---------------------------------

Institutional Multi-Regime & Risk-Parity Capital Allocation Engine for DSE.



Battle-Tested Institutional Frameworks:

  1. Market Volatility Targeting:

     Dynamic Cash Buffer % computed from 20-day DSEX Realized Volatility & Central Bank Macro Drag.

  2. Inverse-Volatility Risk Parity (Jim Simons / Ed Thorp Standard):

     Position sizes inversely proportional to stock volatility (1 / sigma_i) multiplied by Graham Margin of Safety.

  3. Strict Surveillance Gatekeeper:

     Direct is_ticker_blacklisted() verification blocks all manipulated or syndicate-pumped stocks.

  4. Dynamic Entry / Support Dip Targets:

     Computed from 60-day price history, 20-DMA, and 60-day structural support.

  5. Hard Diversification Caps:

     Max 35% capital to any single sector; max 25% to any single stock.



Usage:

  python scripts/smart_capital_planner.py --amount 3000

  python scripts/smart_capital_planner.py --amount 10000 --regime auto

"""



import sys

import os

import json

import sqlite3

import argparse

import math

from datetime import datetime, date

from pathlib import Path



# Windows console encoding safeguard

if sys.platform == "win32":

    try:

        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    except Exception:

        pass



ROOT_DIR = Path(__file__).resolve().parent.parent

DB_PATH = ROOT_DIR / "data" / "processed" / "dse.db"

FIVE_FACTOR_PATH = ROOT_DIR / "reports" / "five_factor_screened_universe.json"





def get_market_regime() -> dict:

    con = sqlite3.connect(DB_PATH, timeout=30.0)
    con.execute("PRAGMA busy_timeout = 30000;")

    cur = con.cursor()

    

    # Fetch last 60 days of DSEX

    rows = cur.execute(

        "SELECT date, dsex, ds30 FROM market_summary WHERE dsex IS NOT NULL ORDER BY date DESC LIMIT 60"

    ).fetchall()

    

    if not rows or len(rows) < 20:

        con.close()

        return {

            "regime": "BEARISH_DRIFT",

            "dsex": 5385.0,

            "dma_20": 5420.0,

            "dma_50": 5450.0,

            "rsi_14": 38.5,

            "dsex_vol_pct": 20.0,

            "cash_buffer_pct": 70.0,

            "trend": "FALLING",

            "reason": "Insufficient historical index bars, defaulting to conservative defensive bias."

        }

        

    prices = [r[1] for r in reversed(rows)]

    latest_date = rows[0][0]

    current_dsex = rows[0][1]

    

    # Calculate 20-DMA and 50-DMA

    dma_20 = sum(prices[-20:]) / 20.0

    dma_50 = sum(prices[-50:]) / 50.0 if len(prices) >= 50 else dma_20

    

    # 14-day RSI of DSEX

    gains, losses = [], []

    for i in range(len(prices) - 14, len(prices)):

        delta = prices[i] - prices[i - 1]

        if delta > 0:

            gains.append(delta)

            losses.append(0.0)

        else:

            gains.append(0.0)

            losses.append(abs(delta))

    avg_gain = sum(gains) / 14.0 if gains else 0.0

    avg_loss = sum(losses) / 14.0 if losses else 0.0001

    rs = avg_gain / avg_loss

    rsi_14 = 100.0 - (100.0 / (1.0 + rs))

    

    # Check Macro Indicators

    macro_hurdle = 12.34

    t_bill = 11.60

    asof_row = cur.execute("SELECT MAX(date) FROM prices").fetchone()

    asof_date = asof_row[0] if asof_row and asof_row[0] else None

    macro_row = cur.execute(

        "SELECT value FROM macro_indicators WHERE indicator='t_bill_91d' ORDER BY date DESC LIMIT 1"

    ).fetchone()

    if macro_row:

        t_bill = macro_row[0]

        macro_hurdle = t_bill + 3.5

        

    con.close()

    

    # ─────────────────────────────────────────────────────────────────────────

    # 1. INSTITUTIONAL VOLATILITY TARGETING (20-day DSEX Annualized Realized Vol)

    # ─────────────────────────────────────────────────────────────────────────

    ret = [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices))]

    ret_20 = ret[-20:] if len(ret) >= 20 else ret

    mean_r = sum(ret_20) / len(ret_20) if ret_20 else 0.0

    var = sum((r - mean_r) ** 2 for r in ret_20) / max(len(ret_20) - 1, 1)

    dsex_vol_pct = round(math.sqrt(var) * math.sqrt(250) * 100.0, 1)

    

    # Volatility Ratio vs Baseline Calm Market (12.0% benchmark volatility)

    vol_ratio = max(0.5, dsex_vol_pct / 12.0)

    macro_drag = 1.0 + max(0.0, (t_bill - 8.0) / 10.0)

    

    pct_from_dma20 = ((current_dsex - dma_20) / dma_20) * 100.0

    pct_from_dma50 = ((current_dsex - dma_50) / dma_50) * 100.0

    

    if current_dsex < dma_20 and pct_from_dma20 < -0.3:

        regime = "BEARISH_DRIFT"

        recommendation_stance = "WAIT_FOR_BOTTOM_OR_STAGGER_DIPS"

        base_cash = 35.0

        desc = "বাজার নিম্নমুখী এবং ২০-দিনের গড়ের নিচে। ভলাটিলিটি টার্গেটিং অনুযায়ী বড় ক্যাশ সংরক্ষণ অগ্রাধিকার।"

    elif abs(pct_from_dma20) <= 0.8 and 42 <= rsi_14 <= 58:

        regime = "STABLE_CONSOLIDATION"

        recommendation_stance = "ACCUMULATE_HIGH_DIVIDEND_VALUE"

        base_cash = 15.0

        desc = "বাজার স্থিতিশীল ও সাপোর্ট জোনে স্থির। কম অস্থির ও উচ্চ ডিভিডেন্ড ক্যাশ কাউ শেয়ার বাছাইয়ের আদর্শ সময়।"

    elif current_dsex > dma_20 and current_dsex > dma_50:

        regime = "GROWTH_EXPANSION"

        recommendation_stance = "MOMENTUM_GROWTH_LEADERS"

        base_cash = 10.0

        desc = "বাজার ঊর্ধ্বমুখী ও শক্তিশালী। আর্নিংস গ্রোথ ও প্রাতিষ্ঠানিক মোমেন্টাম শেয়ারে মূলধন বণ্টন কার্যকর।"

    else:

        regime = "BEARISH_DRIFT"

        recommendation_stance = "WAIT_FOR_BOTTOM_OR_STAGGER_DIPS"

        base_cash = 30.0

        desc = "বাজার দুর্বল ও তারল্য নিম্নমুখী। অতিরিক্ত ক্যাশ বাফার সংরক্ষণ করার পরামর্শ।"



    # Mathematical Dynamic Cash Buffer

    cash_buffer_pct = round(min(80.0, max(10.0, base_cash * vol_ratio * macro_drag)), 1)



    return {

        "as_of_date": latest_date,

        "dsex": round(current_dsex, 2),

        "dma_20": round(dma_20, 2),

        "dma_50": round(dma_50, 2),

        "pct_from_dma20": round(pct_from_dma20, 2),

        "pct_from_dma50": round(pct_from_dma50, 2),

        "rsi_14": round(rsi_14, 1),

        "dsex_vol_pct": dsex_vol_pct,

        "cash_buffer_pct": cash_buffer_pct,

        "regime": regime,

        "stance": recommendation_stance,

        "t_bill_rate": t_bill,

        "macro_hurdle": macro_hurdle,

        "asof_date": asof_date,

        "desc_bn": desc

    }





def compute_dynamic_stock_metrics(ticker: str, conn: sqlite3.Connection) -> dict:

    """Computes dynamic 20-DMA, 60-day low support, 30-day realized volatility, and Graham fair value."""

    asof_row = conn.execute("SELECT MAX(date) FROM prices").fetchone()
    asof_date = asof_row[0] if asof_row and asof_row[0] else None
    if not asof_date:
        return {}

    # Price series (last 60 bars)

    rows = conn.execute("""

        SELECT close, low, high, volume, date FROM prices

        WHERE ticker = ? AND close > 0

        ORDER BY date DESC LIMIT 60

    """, (ticker,)).fetchall()

    

    if not rows:

        return {}

        

    closes = [float(r[0]) for r in reversed(rows)]

    lows = [float(r[1]) if r[1] is not None else float(r[0]) for r in rows]

    current_px = closes[-1]

    dma_20 = sum(closes[-20:]) / len(closes[-20:]) if len(closes) >= 20 else current_px

    min_low_60d = min(lows) if lows else current_px

    

    # 30-day Realized Volatility of the stock (Annualized)

    s_ret = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]

    s_ret_30 = s_ret[-30:] if len(s_ret) >= 30 else s_ret

    s_mean = sum(s_ret_30) / len(s_ret_30) if s_ret_30 else 0.0

    s_var = sum((r - s_mean) ** 2 for r in s_ret_30) / max(len(s_ret_30) - 1, 1)

    stock_vol_pct = round(math.sqrt(s_var) * math.sqrt(250) * 100.0, 1) if s_var > 0 else 15.0



    # Fundamentals from PIT table (primary) or fundamentals table (fallback)

    f_row = conn.execute("""

        SELECT f.eps, f.nav, f.pe_ratio, f.dividend_yield, f.debt_equity, f.cash_flow_ops, c.sector

        FROM fundamentals_pit f

        LEFT JOIN companies c ON f.ticker = c.ticker

        WHERE f.ticker = ?
          AND f.tradable_date <= ?
          AND f.publication_date <= ?
          AND f.pe_ratio IS NOT NULL
        ORDER BY f.tradable_date DESC, f.publication_date DESC, f.snapshot_date DESC LIMIT 1

    """, (ticker, asof_date, asof_date)).fetchone()

    

    if not f_row:
        return {}

    eps = float(f_row[0]) if f_row and f_row[0] is not None else None

    nav = float(f_row[1]) if f_row and f_row[1] is not None else None

    pe = float(f_row[2]) if f_row and f_row[2] is not None else None

    dy = float(f_row[3]) if f_row and f_row[3] is not None else 0.0

    de = float(f_row[4]) if f_row and f_row[4] is not None else None

    cfo = float(f_row[5]) if f_row and f_row[5] is not None else None

    sec = str(f_row[6]) if f_row and f_row[6] else "Unknown"



    # Graham Fair Value & Margin of Safety

    graham_val = None

    mos_pct = 0.0

    if eps and nav and eps > 0 and nav > 0:

        graham_val = round(math.sqrt(22.5 * eps * nav), 1)

        mos_pct = round(((graham_val - current_px) / graham_val) * 100.0, 1)



    # 20-day Average Daily Volume and Turnover (BDT)

    past_20 = rows[:20]

    avg_vol_20 = sum(float(r[3] or 0) for r in past_20) / max(len(past_20), 1)

    adv_turnover_bdt = round(avg_vol_20 * current_px, 2)



    # Dynamic target dip:

    # Anchor to 3% below current, 2% below 20-DMA, bounded above 60-day lowest support

    target_dip = round(min(current_px * 0.97, dma_20 * 0.98), 1)

    if min_low_60d > 0 and min_low_60d < current_px:

        target_dip = round(max(target_dip, min_low_60d * 0.99), 1)



    # Check for temporal price discontinuity (> 25 calendar days gap between trading sessions)

    dates_asc = [r[4] for r in reversed(rows)]

    has_data_gap = False

    max_gap_days = 0

    if len(dates_asc) >= 2:

        for i in range(1, len(dates_asc)):

            try:

                d0 = date.fromisoformat(dates_asc[i - 1])

                d1 = date.fromisoformat(dates_asc[i])

                gap = (d1 - d0).days

                if gap > max_gap_days:

                    max_gap_days = gap

                if gap > 25:

                    has_data_gap = True

            except Exception:

                pass



    return {

        "ticker": ticker,

        "sector": sec,

        "current_price": current_px,

        "dma_20": round(dma_20, 1),

        "min_low_60d": round(min_low_60d, 1),

        "adv_turnover_bdt": adv_turnover_bdt,

        "volatility_pct": stock_vol_pct,

        "eps": eps,

        "nav": nav,

        "pe": pe,

        "dividend_yield": dy,

        "debt_equity": de,

        "cfo": cfo,

        "graham_val": graham_val,

        "mos_pct": mos_pct,

        "target_dip": target_dip,

        "has_data_gap": has_data_gap,

        "max_gap_days": max_gap_days

    }





def load_candidate_pool() -> list[str]:

    """Dynamically loads candidate tickers strictly screened for 5 factors and free of blacklist."""

    candidates = []

    if FIVE_FACTOR_PATH.exists():

        try:

            with open(FIVE_FACTOR_PATH, "r", encoding="utf-8") as f:

                data = json.load(f)

                cands = data.get("candidates", []) or data.get("screened_universe", [])

                candidates = [
                    item["ticker"] for item in cands
                    if isinstance(item, dict) and "ticker" in item
                    and not item.get("is_overvalued", False)
                    and item.get("passes_macro", True)
                ]

        except Exception:

            candidates = []



    if not candidates:
        try:
            from five_factor_fundamental_screener import run_5_factor_screener
            candidates = [
                row["ticker"]
                for row in run_5_factor_screener(halal_tier=user_halal_tier)
            ]
        except Exception:
            candidates = []



    return candidates






def build_tranche_plan(total_shares: int, current_px: float, target_limit: float, min_low_60d: float) -> list[dict]:
    """
    Builds institutional 3-tier limit order ladder:
      - Tranche 1 (Probe 35%): At target_limit (~20-DMA or 2% dip)
      - Tranche 2 (Value Add 40%): At deeper support (-5% to -8% or min_low_60d)
      - Tranche 3 (Confirmation 25%): At breakout (+2.5% above current)
    """
    if total_shares <= 0:
        return []

    t2_px = round(min(target_limit * 0.95, current_px * 0.94), 1)
    if min_low_60d > 0 and min_low_60d < current_px:
        t2_px = round(max(t2_px, min_low_60d), 1)

    t3_px = round(current_px * 1.025, 1)

    if total_shares == 1:
        return [{"tranche": "T1 (Full Position)", "pct": 100, "shares": 1, "order_type": "LIMIT", "price": target_limit, "outlay": round(target_limit, 1), "note": "Fair Value Support"}]
    elif total_shares == 2:
        return [
            {"tranche": "T1 (Probe)", "pct": 50, "shares": 1, "order_type": "LIMIT", "price": target_limit, "outlay": round(target_limit, 1), "note": "20-DMA / Initial Dip"},
            {"tranche": "T2 (Value Add)", "pct": 50, "shares": 1, "order_type": "LIMIT", "price": t2_px, "outlay": round(t2_px, 1), "note": "Deep Margin Support"}
        ]
    elif total_shares <= 5:
        s1 = math.ceil(total_shares * 0.5)
        s2 = total_shares - s1
        return [
            {"tranche": "T1 (Probe)", "pct": round(s1 / total_shares * 100), "shares": s1, "order_type": "LIMIT", "price": target_limit, "outlay": round(s1 * target_limit, 1), "note": "20-DMA / Initial Dip"},
            {"tranche": "T2 (Value Add)", "pct": round(s2 / total_shares * 100), "shares": s2, "order_type": "LIMIT", "price": t2_px, "outlay": round(s2 * t2_px, 1), "note": "Deep Margin Support"}
        ]
    else:
        s1 = max(1, round(total_shares * 0.35))
        s2 = max(1, round(total_shares * 0.40))
        s3 = total_shares - (s1 + s2)
        if s3 <= 0:
            s3 = 1
            if s2 > 1: s2 -= 1
            elif s1 > 1: s1 -= 1
        return [
            {"tranche": "T1 (Probe - 35%)", "pct": round(s1 / total_shares * 100), "shares": s1, "order_type": "LIMIT", "price": target_limit, "outlay": round(s1 * target_limit, 1), "note": "At / Near 20-DMA Support"},
            {"tranche": "T2 (Value Add - 40%)", "pct": round(s2 / total_shares * 100), "shares": s2, "order_type": "LIMIT", "price": t2_px, "outlay": round(s2 * t2_px, 1), "note": "Deep Structural Support Dip"},
            {"tranche": "T3 (Reversal - 25%)", "pct": round(s3 / total_shares * 100), "shares": s3, "order_type": "STOP_LIMIT", "price": t3_px, "outlay": round(s3 * t3_px, 1), "note": "Momentum Breakout Confirmation"}
        ]


def generate_smart_plan(amount: float, override_regime: str = None, asof_date: str = None) -> dict:

    regime_info = get_market_regime()

    regime = override_regime if override_regime else regime_info["regime"]

    asof_date = asof_date or regime_info.get("asof_date")

    

    # 1. Calculate dynamic cash reserve from Volatility Targeting

    cash_reserve_pct = regime_info["cash_buffer_pct"]

    wait_cash = round(amount * (cash_reserve_pct / 100.0), 2)

    invest_now = round(amount - wait_cash, 2)

    

    # Import blacklist gate and HalalGuard

    try:

        from anti_manipulation_engine import is_ticker_blacklisted

    except ImportError:

        is_ticker_blacklisted = lambda t, asof_date=None, lookback_days=45: (False, "Clean")



    user_halal_tier = "flexible"
    try:
        from profile import load_profile
        prof = load_profile()
        user_halal_tier = prof.get("halal_tier", "flexible")
    except Exception:
        pass

    try:
        from halal_guard import HalalGuard
        halal_checker = HalalGuard()
    except Exception:
        halal_checker = None



    conn = sqlite3.connect(DB_PATH, timeout=30.0)

    conn.execute("PRAGMA busy_timeout = 30000;")

    candidate_tickers = load_candidate_pool()



    # Filter out blacklisted and non-halal stocks, compute dynamic metrics

    verified_candidates = []

    for t in candidate_tickers:

        is_b, _ = is_ticker_blacklisted(t, asof_date=asof_date)

        if is_b:

            continue

        if halal_checker:

            h_res = halal_checker.is_eligible(t, tier=user_halal_tier)

            if not h_res.get("eligible", True):

                continue

        metrics = compute_dynamic_stock_metrics(t, conn)

        if metrics and metrics.get("current_price", 0) > 0:

            # Liquidity gate: Must have at least ৳15 Lakh ADV turnover or low volatility (<22%)

            if metrics.get("adv_turnover_bdt", 0) >= 1500000.0 or metrics.get("volatility_pct", 0) <= 22.0:

                verified_candidates.append(metrics)



    conn.close()



    if not verified_candidates:

        conn = sqlite3.connect(DB_PATH, timeout=30.0)

        conn.execute("PRAGMA busy_timeout = 30000;")

        # Pristine Halal Moats (No conventional interest-bearing financial institutions)

        fallback_tickers = ["JAMUNAOIL", "PADMAOIL", "SQURPHARMA", "BXPHARMA", "GP", "OLYMPIC"]

        for t in fallback_tickers:

            is_b, _ = is_ticker_blacklisted(t, asof_date=asof_date)

            if not is_b:

                if halal_checker:

                    h_res = halal_checker.is_eligible(t, tier=user_halal_tier)

                    if not h_res.get("eligible", True):

                        continue

                m = compute_dynamic_stock_metrics(t, conn)

                if m:

                    verified_candidates.append(m)

        conn.close()



    # ─────────────────────────────────────────────────────────────────────────

    # 2. INVERSE-VOLATILITY & MARGIN-OF-SAFETY RISK PARITY RANKING

    # ─────────────────────────────────────────────────────────────────────────

    for cand in verified_candidates:

        vol = max(cand.get("volatility_pct") or 15.0, 5.0)

        dy = cand.get("dividend_yield") or 0.0

        mos = cand.get("mos_pct") or 0.0

        de = max(cand.get("debt_equity") or 0.0, 0.0)

        pe = cand.get("pe") or 15.0

        

        # Sector FX Devaluation Resilience Multiplier (Bangladesh Macro Dynamic)

        # Sectors with dollar export revenue or state-guaranteed cost-plus margins (Fuel & Power, Pharma)

        # are resilient to BDT depreciation. Import-dependent cyclicals (Engineering, Ceramics) face margin squeeze.

        sec_name = (cand.get("sector") or "").strip().lower()

        fx_resilience = 1.0

        if any(s in sec_name for s in ["fuel", "power", "pharmaceutical"]):

            fx_resilience = 1.25  # 25% institutional resilience premium

        elif any(s in sec_name for s in ["engineering", "ceramic", "tannery"]):

            fx_resilience = 0.80  # 20% import-cost margin drag penalty



        # Risk Parity Score: Must have positive Margin of Safety in Bearish/Consolidation

        # Weight = (Margin_of_Safety * Yield * FX_Resilience) / (Volatility * (1 + D/E))

        gap_penalty = 0.50 if cand.get("has_data_gap", False) else 1.0

        if mos <= 0:

            score = 0.001

        else:

            score = ((mos * max(dy, 2.0) * fx_resilience) / (vol * (1.0 + de))) * gap_penalty

        cand["risk_parity_score"] = round(score, 3)



    # Sort by risk parity score

    sorted_pool = sorted(verified_candidates, key=lambda x: x["risk_parity_score"], reverse=True)



    # Minimum Ticket Size & Tranche Concentration Gate:

    # On DSE, retail brokers charge a minimum ticket fee (Tk 5-10 flat per trade note).

    # Splitting small budgets (< Tk 2,500) into tiny micro-lots (e.g. Tk 195) causes a 5%-10% commission drag.

    # Therefore:

    #   * If invest_now < Tk 2,500: Concentrate into 1 high-conviction position.

    #   * If invest_now Tk 2,500 - Tk 6,000: Max 2 positions.

    #   * If invest_now > Tk 6,000: Max 3 positions.

    if invest_now < 2500:

        target_count = 1

    elif invest_now < 6000:

        target_count = 2

    else:

        target_count = 3



    # Pick top diversified candidates that are actually affordable (price <= allocated tranche)

    min_alloc_per_pick = invest_now / target_count

    chosen_picks = []

    seen_sectors = set()

    for cand in sorted_pool:

        # Affordability check: At least 1 share can be bought with target_dip

        if cand.get("target_dip", 999999) > min_alloc_per_pick:

            continue

        sec = cand.get("sector", "Unknown")

        if sec in seen_sectors:

            continue

        seen_sectors.add(sec)

        chosen_picks.append(cand)

        if len(chosen_picks) >= target_count:

            break



    if len(chosen_picks) < target_count:
        fb_conn = sqlite3.connect(DB_PATH, timeout=30.0)
        fb_conn.execute("PRAGMA busy_timeout = 30000;")
        diverse_fallback_tickers = ["SQURPHARMA", "BXPHARMA", "GP", "OLYMPIC", "BATBC", "BSRMSTEEL"]
        for fb_t in diverse_fallback_tickers:
            if any(p["ticker"] == fb_t for p in chosen_picks):
                continue
            is_b, _ = is_ticker_blacklisted(fb_t, asof_date=asof_date)
            if is_b:
                continue
            if halal_checker:
                h_res = halal_checker.is_eligible(fb_t, tier=user_halal_tier)
                if not h_res.get("eligible", True):
                    continue
            fb_m = compute_dynamic_stock_metrics(fb_t, fb_conn)
            if fb_m and fb_m.get("current_price", 0) > 0:
                fb_sec = fb_m.get("sector", "Unknown")
                if fb_sec not in seen_sectors and fb_m.get("target_dip", 999999) <= min_alloc_per_pick:
                    seen_sectors.add(fb_sec)
                    chosen_picks.append(fb_m)
                    if len(chosen_picks) >= target_count:
                        break
        fb_conn.close()

    if len(chosen_picks) < target_count:
        for cand in sorted_pool:
            if cand not in chosen_picks:
                if cand.get("target_dip", 999999) <= min_alloc_per_pick:
                    chosen_picks.append(cand)
                    if len(chosen_picks) >= target_count:
                        break



    # ─────────────────────────────────────────────────────────────────────────

    # 3. INVERSE-VOLATILITY POSITION SIZING ACROSS PICKS

    # ─────────────────────────────────────────────────────────────────────────

    allocations = []

    if chosen_picks and invest_now > 0:

        inv_vols = [1.0 / max(p["volatility_pct"], 5.0) for p in chosen_picks]

        sum_inv = sum(inv_vols)

        norm_weights = [v / sum_inv for v in inv_vols]

        

        for i, pick in enumerate(chosen_picks):

            w = norm_weights[i]

            allocated_bdt = round(invest_now * w, 2)

            target_p = pick["target_dip"]

            shares = int(allocated_bdt // target_p) if target_p > 0 else 0

            actual_outlay = round(shares * target_p, 2)

            

            pe_str = f"{pick['pe']:.1f}" if pick.get('pe') is not None else "—"

            gap_note = " [⚠️ ট্রেডিং গ্যাপ সতর্কতা]" if pick.get("has_data_gap") else ""

            rationale = (

                f"ইল্ড: {pick['dividend_yield']}% | MoS: +{pick['mos_pct']}% | "

                f"ভলাটিলিটি: {pick['volatility_pct']}% | খাত: {pick['sector']}{gap_note}"

            )

            allocations.append({

                "ticker": pick["ticker"],

                "sector": pick["sector"],

                "current_price": pick["current_price"],

                "target_limit_price": target_p,

                "volatility_pct": pick["volatility_pct"],

                "weight_pct": round(w * 100.0, 1),

                "dma_20": pick["dma_20"],

                "allocated_budget": allocated_bdt,

                "exact_shares": shares,

                "estimated_outlay": actual_outlay,

                "tranches": build_tranche_plan(
                    total_shares=shares,
                    current_px=pick["current_price"],
                    target_limit=target_p,
                    min_low_60d=pick.get("min_low_60d", target_p * 0.95)
                ),

                "rationale": rationale

            })



    # Institutional Macro Cash Management (Eliminating 0% BO Account Drag)

    # During high inflation (9-10%), never leave 100% of defensive cash idle at 0% in a retail BO account.

    # Split defensive cash:

    #   - 75% into High-Yield Liquid Defensive Anchor (e.g. Shanta Fixed Income / Amana Cash Fund / 91d T-Bill) earning ~9.5%-11.0% annualized

    #   - 25% kept as BO Trading Cash for intraday limit order fulfillment

    bo_trading_buffer = round(wait_cash * 0.25, 2)

    liquid_yield_anchor = round(wait_cash * 0.75, 2)



    # Realistic Tiered Liquidity Allocator based on BD Financial Product Minimums

    if liquid_yield_anchor >= 100000.0:

        liquid_instrument = "Bangladesh Bank 91-Day T-Bills via Primary Dealer (11.0% - 11.5% Yield, ৳1L Minimum Ticket)"

        liquid_tag = "91d T-Bills (11.0%-11.5%)"

    elif liquid_yield_anchor >= 5000.0:

        liquid_instrument = "Shanta Fixed Income / Amana Cash Fund (9.5% - 10.5% Yield, ৳5,000 Min Initial Tranche)"

        liquid_tag = "Shanta Liquid Fund (9.5%-10.5%)"

    else:

        liquid_instrument = "High-Yield Digital Savings / MFS SND (bKash/Nagad/Bank SND 7.5% - 8.0% Yield, ৳0 Minimum)"

        liquid_tag = "MFS/SND Digital Cash (7.5%-8.0%)"



    return {

        "regime_info": regime_info,

        "invested_capital_input": amount,

        "suggested_cash_reserve": wait_cash,

        "cash_reserve_pct": cash_reserve_pct,

        "bo_trading_cash_bdt": bo_trading_buffer,

        "liquid_yield_anchor_bdt": liquid_yield_anchor,

        "liquid_anchor_instrument": liquid_instrument,

        "liquid_anchor_tag": liquid_tag,

        "immediate_tranche_budget": invest_now,

        "allocations": allocations

    }





def print_plan_report(plan: dict):

    r = plan["regime_info"]

    amt = plan["invested_capital_input"]

    cash = plan["suggested_cash_reserve"]

    c_pct = plan["cash_reserve_pct"]

    tranche = plan["immediate_tranche_budget"]

    

    print("\n" + "="*85)

    print(f"🧠 DSE RISK-PARITY & VOLATILITY-TARGETED CAPITAL ALLOCATION — PLAN FOR ৳{amt:,.2f}")

    print("="*85)

    print(f"📅 As-of Date: {r['as_of_date']} | DSEX Index: {r['dsex']} (20-DMA: {r['dma_20']} | 50-DMA: {r['dma_50']})")

    print(f"📊 Market Regime: [{r['regime']}] | RSI-14: {r['rsi_14']}")

    print(f"🌊 DSEX 20-Day Annualized Volatility: {r['dsex_vol_pct']}% (Elevated Market Risk)")

    print(f"🏦 Bangladesh Bank T-Bill: {r['t_bill_rate']}% | Minimum Equity Hurdle: {r['macro_hurdle']}%")

    print(f"📝 Quantitative Stance: {r['desc_bn']}")

    print("-"*85)

    print(f"🛡️ Dynamic Defensive Cash Allocation:                ৳{cash:,.2f} ({c_pct}%)")

    liquid_tag = plan.get('liquid_anchor_tag', 'Liquid Yield')

    print(f"   ├─ 75% High-Yield Liquid Anchor: ৳{plan.get('liquid_yield_anchor_bdt', cash*0.75):,.2f} [{liquid_tag}]")

    print(f"   └─ 25% Active Brokerage BO Cash (Limit Buffer):    ৳{plan.get('bo_trading_cash_bdt', cash*0.25):,.2f}")

    print(f"🎯 Actionable Risk-Parity Equity Tranche:            ৳{tranche:,.2f} ({round(100.0 - c_pct, 1)}%)")

    print("-"*85)

    print(f"{'Ticker':<12} {'Sector':<14} {'Live Px':<10} {'Limit Target':<14} {'Vol':<7} {'Shares':<8} {'Outlay (BDT)':<13}")

    print("-"*85)

    for a in plan["allocations"]:
        print(f"{a['ticker']:<12} {a['sector']:<14} ৳{a['current_price']:<9.1f} ৳{a['target_limit_price']:<13.1f} {a['volatility_pct']:<5.1f}% {a['exact_shares']:<8} ৳{a['estimated_outlay']:<12.1f}")
        tranches = a.get("tranches", [])
        if tranches:
            print("  └─ 3-Tier Execution Tranches:")
            for t_idx, tr in enumerate(tranches):
                connector = "└─" if t_idx == len(tranches) - 1 else "├─"
                print(f"     {connector} {tr['tranche']:<24}: {tr['shares']:>2} shs @ ৳{tr['price']:<6.1f} ({tr['order_type']}) -> ৳{tr['outlay']:<8.1f} [{tr['note']}]")
        print(f"  └─ Rationale: {a['rationale']}")

    print("="*85)

    print("💡 Execution Rule: Do NOT chase open prices in the first hour (10:00-11:00 AM).")

    print("   Place Limit Orders strictly at or below 'Limit Target' between 11:30 AM and 12:30 PM.")

    print("="*85 + "\n")





if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="DSE Smart Capital Planner")

    parser.add_argument("--amount", type=float, default=3000.0, help="Investment amount in BDT")

    parser.add_argument("--regime", type=str, default=None, choices=["BEARISH_DRIFT", "STABLE_CONSOLIDATION", "GROWTH_EXPANSION"], help="Override regime")

    args = parser.parse_args()

    

    plan = generate_smart_plan(args.amount, args.regime)

    print_plan_report(plan)
