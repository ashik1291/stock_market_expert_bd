"""
Phase 3: rolling cross-sectional Rank IC → EMA factor weights (floor at 0).

Factors (eligible names only):
  div   = dividend_yield
  value = max(0, 18 - pe)
  rsi   = 100 - rsi_14   (oversold high)
  debt  = 1.0 if debt_equity<=0.5 else 0.0

Weights shrunk toward 0 via EMA of IC; negative EMA → weight 0 (factor off).
Writes: data/learning/factor_ic_weights.json
"""

from __future__ import annotations

import json
import math
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"
LEARN_DIR = BASE_DIR / "data" / "learning"
OUT_PATH = LEARN_DIR / "factor_ic_weights.json"
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from rank_ic_newey_west import spearman_rank_correlation, newey_west_t_stat
from feature_store import build_features_for_date, ensure_schema
from unified_score import DEFAULT_HORIZON_BARS, ROUND_TRIP_COST_PCT

EMA_HALFLIFE_PERIODS = 6  # ~6 IC observations (~monthly cadence with stride)
MIN_CROSS_SECTION = 15
DEFAULT_LOOKBACK_DATES = 40
DEFAULT_STRIDE = 5


def _ema(series: list[float], half_life: int) -> float:
    if not series:
        return 0.0
    alpha = 1.0 - math.exp(-math.log(2) / max(half_life, 1))
    s = series[0]
    for x in series[1:]:
        s = alpha * x + (1.0 - alpha) * s
    return s


def _trading_dates(conn: sqlite3.Connection, n: int) -> list[str]:
    rows = conn.execute(
        """
        SELECT date FROM trading_calendar
        WHERE is_trading_day = 1 AND date <= (SELECT MAX(date) FROM prices)
        ORDER BY date DESC LIMIT ?
        """,
        (n * 3,),
    ).fetchall()
    dates = [r[0] for r in rows]
    dates.reverse()
    # Fallback from prices if calendar thin
    if len(dates) < n:
        dates = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT date FROM prices ORDER BY date DESC LIMIT ?",
                (n * 2,),
            )
        ]
        dates.reverse()
    return dates


def _fwd_return(conn: sqlite3.Connection, ticker: str, d0: str, horizon: int) -> float | None:
    rows = conn.execute(
        """
        SELECT date, close FROM prices
        WHERE ticker=? AND date>=? AND close IS NOT NULL
        ORDER BY date ASC LIMIT ?
        """,
        (ticker, d0, horizon + 1),
    ).fetchall()
    if len(rows) < horizon + 1:
        return None
    d_start = rows[0][0]
    c0 = float(rows[0][1])
    d_end = rows[horizon][0]
    c1 = float(rows[horizon][1])
    if c0 <= 0:
        return None

    # Total return: adjust for corporate actions (dividends and bonus shares) between d_start and d_end
    try:
        ca_rows = conn.execute(
            """
            SELECT action_type, ratio, cash_amount, adjustment_factor
            FROM corporate_actions
            WHERE ticker=? AND record_date > ? AND record_date <= ?
            """,
            (ticker, d_start, d_end),
        ).fetchall()
        bonus_multiplier = 1.0
        cash_div_total = 0.0
        for ca in ca_rows:
            act = str(ca[0]).lower()
            ratio = float(ca[1] or 0.0)
            cash_amt = float(ca[2] or 0.0)
            adj = float(ca[3] or 1.0)
            if "bonus" in act or "split" in act:
                if ratio > 0:
                    bonus_multiplier *= (1.0 + ratio)
                elif 0 < adj < 1.0:
                    bonus_multiplier *= (1.0 / adj)
            if "cash" in act or cash_amt > 0:
                net_cash = cash_amt * 0.90 if cash_amt > 0 else (c0 * ratio * 0.90 if ratio > 0 else 0.0)
                cash_div_total += net_cash

        end_val = (c1 * bonus_multiplier) + cash_div_total
        gross = (end_val / c0) - 1.0
    except Exception:
        gross = (c1 / c0) - 1.0

    return gross - (ROUND_TRIP_COST_PCT / 100.0)


def calibrate_factor_ic(
    lookback_dates: int = DEFAULT_LOOKBACK_DATES,
    stride: int = DEFAULT_STRIDE,
    horizon: int = DEFAULT_HORIZON_BARS,
    backfill: bool = True,
) -> dict:
    LEARN_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)

    all_dates = _trading_dates(conn, lookback_dates + horizon + 5)
    # Need room for forward horizon — drop last `horizon` dates as IC anchors
    if len(all_dates) <= horizon + 5:
        conn.close()
        result = {
            "ok": False,
            "reason": "insufficient trading dates",
            "weights": {"div": 1.0, "value": 1.0, "rsi": 1.0, "debt": 1.0},
        }
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        return result

    anchor_pool = all_dates[: -horizon]
    eval_dates = anchor_pool[::stride][-lookback_dates:]

    ic_series = {"div": [], "value": [], "rsi": [], "debt": []}
    ic_by_date = []

    for dt in eval_dates:
        cnt = conn.execute(
            "SELECT COUNT(*) AS n FROM features_daily WHERE date=?", (dt,)
        ).fetchone()["n"]
        if cnt == 0 and backfill:
            conn.close()
            build_features_for_date(dt)
            conn = sqlite3.connect(DB_PATH, timeout=30.0)
            conn.execute("PRAGMA busy_timeout = 30000;")
            conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """
            SELECT ticker, pe_ratio, debt_equity, dividend_yield, rsi_14, is_eligible
            FROM features_daily WHERE date=? AND is_eligible=1
            """,
            (dt,),
        ).fetchall()
        if len(rows) < MIN_CROSS_SECTION:
            continue

        cross_data = []
        for r in rows:
            fwd = _fwd_return(conn, r["ticker"], dt, horizon)
            if fwd is None:
                continue
            pe = float(r["pe_ratio"]) if r["pe_ratio"] is not None and float(r["pe_ratio"]) > 0 else None
            de = float(r["debt_equity"]) if r["debt_equity"] is not None and float(r["debt_equity"]) >= 0 else None
            div = float(r["dividend_yield"] or 0.0)
            rsi = float(r["rsi_14"]) if r["rsi_14"] is not None else None
            cross_data.append({
                "ticker": r["ticker"],
                "fwd": fwd,
                "div": div,
                "pe": pe,
                "de": de,
                "rsi": rsi,
            })

        if len(cross_data) < MIN_CROSS_SECTION:
            continue

        rets_all = [c["fwd"] for c in cross_data]
        day_ics = {}

        # 1. Dividend Factor (div_yield)
        div_vals = [c["div"] for c in cross_data]
        day_ics["div"] = round(spearman_rank_correlation(div_vals, rets_all), 4)

        # 2. Value Factor (-pe for valid PE > 0, avoiding 0.0 top rank inversion)
        valid_pe = [( -c["pe"], c["fwd"] ) for c in cross_data if c["pe"] is not None]
        if len(valid_pe) >= MIN_CROSS_SECTION:
            day_ics["value"] = round(spearman_rank_correlation([v[0] for v in valid_pe], [v[1] for v in valid_pe]), 4)
        else:
            day_ics["value"] = 0.0

        # 3. RSI Momentum/Reversion (100 - RSI)
        valid_rsi = [( (100.0 - c["rsi"]), c["fwd"] ) for c in cross_data if c["rsi"] is not None]
        if len(valid_rsi) >= MIN_CROSS_SECTION:
            day_ics["rsi"] = round(spearman_rank_correlation([v[0] for v in valid_rsi], [v[1] for v in valid_rsi]), 4)
        else:
            day_ics["rsi"] = 0.0

        # 4. Debt Factor (-debt_equity for valid non-financials, avoiding bank 0.0 inversion)
        valid_debt = [( -c["de"], c["fwd"] ) for c in cross_data if c["de"] is not None]
        if len(valid_debt) >= MIN_CROSS_SECTION:
            day_ics["debt"] = round(spearman_rank_correlation([v[0] for v in valid_debt], [v[1] for v in valid_debt]), 4)
        else:
            day_ics["debt"] = 0.0

        for name in ic_series:
            ic_series[name].append(day_ics[name])
        ic_by_date.append({"date": dt, "n": len(cross_data), "ics": day_ics})

    nw_lags = max(1, int(math.ceil(horizon / stride)))
    stats = {}
    weights = {}
    for name, series in ic_series.items():
        if len(series) < 3:
            weights[name] = 1.0  # insufficient → neutral prior
            stats[name] = {"n": len(series), "ema_ic": 0.0, "mean_ic": 0.0, "t_nw": 0.0}
            continue
        mean_ic, se, t_nw = newey_west_t_stat(series, max_lags=nw_lags)
        ema_ic = _ema(series, EMA_HALFLIFE_PERIODS)
        # Floor at 0: negative predictive factor shut off
        w = max(0.0, ema_ic)
        # Scale so typical IC~0.03 → weight ~1.0; cap 1.4
        w_scaled = min(1.4, w / 0.03) if w > 0 else 0.0
        weights[name] = round(w_scaled, 4)
        stats[name] = {
            "n": len(series),
            "ema_ic": round(ema_ic, 4),
            "mean_ic": round(mean_ic, 4),
            "se_nw": round(se, 4),
            "t_nw": round(t_nw, 3),
            "weight": weights[name],
        }

    # If all zero (cold start), fall back to equal 1.0
    if sum(weights.values()) == 0:
        weights = {k: 1.0 for k in weights}

    result = {
        "ok": True,
        "horizon_bars": horizon,
        "stride": stride,
        "eval_dates": len(ic_by_date),
        "ema_halflife_periods": EMA_HALFLIFE_PERIODS,
        "weights": weights,
        "stats": stats,
        "recent_ics": ic_by_date[-8:],
        "model_note": "weights = max(0, EMA_IC)/0.03 capped 1.4; shrink toward 0",
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    conn.close()
    print(f"[FACTOR IC] dates={result['eval_dates']} weights={weights}")
    for k, s in stats.items():
        print(f"  {k}: ema_ic={s.get('ema_ic')} t_nw={s.get('t_nw')} w={s.get('weight')}")
    return result


def load_ic_weights() -> dict:
    if OUT_PATH.exists():
        try:
            data = json.loads(OUT_PATH.read_text(encoding="utf-8"))
            w = data.get("weights") or {}
            if w:
                return {
                    "div": float(w.get("div", 1.0)),
                    "value": float(w.get("value", 1.0)),
                    "rsi": float(w.get("rsi", 1.0)),
                    "debt": float(w.get("debt", 1.0)),
                }
        except Exception:
            pass
    return {"div": 1.0, "value": 1.0, "rsi": 1.0, "debt": 1.0}


if __name__ == "__main__":
    # CLI: optional lookback
    lb = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOOKBACK_DATES
    calibrate_factor_ic(lookback_dates=lb)
