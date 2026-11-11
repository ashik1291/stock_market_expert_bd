"""
scripts/seed_signal_velocity.py — Historical Signal Seeder & Temporal Velocity Engine

Populates `company_signals_history` across past active trading sessions using verified
point-in-time records from `features_daily` and historical prices.
Enables real-time calculation of signal momentum (dS/dt) and acceleration (d^2S/dt^2).
"""

from __future__ import annotations

import sys
import sqlite3
import datetime
import json
import logging
from pathlib import Path
from typing import Dict, Any, List

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("seed_signal_velocity")


def seed_historical_signals(limit_dates: int = 10) -> Dict[str, Any]:
    """
    Backfills historical daily/weekly signals into `company_signals_history`
    for up to `limit_dates` historical trading sessions from `features_daily`.
    """
    if not DB_PATH.exists():
        log.error("Database not found")
        return {"status": "error", "message": "DB not found"}

    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get recent trading dates from features_daily
    date_rows = cur.execute(
        """
        SELECT DISTINCT date
        FROM features_daily
        ORDER BY date DESC
        LIMIT ?
        """,
        (limit_dates,),
    ).fetchall()

    hist_dates = [r["date"] for r in date_rows]
    log.info(f"Targeting {len(hist_dates)} trading sessions for signal history seed: {hist_dates}")

    inserted_total = 0
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    for dt in reversed(hist_dates):
        # Fetch features for this date
        feat_rows = cur.execute(
            """
            SELECT fd.*, c.category, c.name as company_name
            FROM features_daily fd
            LEFT JOIN companies c ON fd.ticker = c.ticker
            WHERE fd.date = ?
            """,
            (dt,),
        ).fetchall()

        batch = []
        for r in feat_rows:
            ticker = r["ticker"]
            score = float(r["score"]) if r["score"] is not None else 0.0
            is_elig = bool(r["is_eligible"])
            signal_type = "BUY" if (score >= 60.0 and is_elig) else ("HOLD" if is_elig else "AVOID")

            close_px = float(r["close"]) if r["close"] else None
            stop_loss = round(close_px * 0.95, 2) if close_px else None
            target_px = round(close_px * 1.10, 2) if close_px else None

            # Check if record already exists
            existing = cur.execute(
                "SELECT 1 FROM company_signals_history WHERE ticker = ? AND date = ? AND timeframe = 'weekly'",
                (ticker, dt),
            ).fetchone()
            if existing:
                continue

            compact_payload = json.dumps({
                "ticker": ticker,
                "date": dt,
                "score": score,
                "signal": signal_type,
                "close": close_px,
                "is_eligible": is_elig,
                "seeded": True,
            })

            batch.append((
                dt, ticker, "weekly", "short", now_iso, dt,
                r["model_id"] or "served_v3_ic_weighted",
                score,
                signal_type,
                min(max(score, 10.0), 95.0),
                close_px, stop_loss, target_px,
                r["rsi_14"], r["pe_ratio"], r["debt_equity"],
                50.0, 50.0, 50.0, 50.0, score,
                "low", 0, 0,
                compact_payload
            ))

        if batch:
            cur.executemany(
                """
                INSERT OR REPLACE INTO company_signals_history (
                    date, ticker, timeframe, horizon, analyzed_at, asof_price_date,
                    served_model_id, served_model_score, signal, confidence,
                    entry_price, stop_loss, target_price, rsi_14, pe_ratio, debt_equity,
                    technical_score, fundamental_score, sentiment_score, governance_score,
                    composite_score, manipulation_risk, manipulation_score, block_buy,
                    full_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                batch,
            )
            inserted_total += len(batch)
            log.info(f"Seeded {len(batch)} signals for date={dt}")

    conn.commit()
    conn.close()

    log.info(f"Signal seed complete. Total seeded: {inserted_total} records.")
    return {"status": "success", "dates_processed": len(hist_dates), "inserted_records": inserted_total}


def calculate_velocity_for_ticker(ticker: str, lookback_bars: int = 5) -> Dict[str, Any]:
    """
    Computes signal velocity (dS/dt) and acceleration (d^2S/dt^2) across past bars.
    """
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT date, served_model_score, composite_score, confidence
        FROM company_signals_history
        WHERE ticker = ? AND timeframe = 'weekly'
        ORDER BY date DESC
        LIMIT ?
        """,
        (ticker.strip().upper(), lookback_bars * 2 + 1),
    ).fetchall()
    conn.close()

    if not rows or len(rows) < 2:
        return {
            "ticker": ticker,
            "status": "INSUFFICIENT_HISTORY",
            "bars_found": len(rows),
            "velocity": 0.0,
            "acceleration": 0.0,
            "momentum_regime": "NEUTRAL",
        }

    scores = [
        float(r["served_model_score"] if r["served_model_score"] is not None else (r["composite_score"] or 0.0))
        for r in rows
    ]
    dates = [r["date"] for r in rows]

    current_score = scores[0]
    lookback_idx = min(lookback_bars, len(scores) - 1)
    past_score = scores[lookback_idx]

    delta_s = current_score - past_score
    velocity = round(delta_s / max(lookback_idx, 1), 3)

    # Acceleration: compare velocity over first half vs second half
    accel = 0.0
    if len(scores) >= 5:
        mid_idx = lookback_idx // 2
        v1 = (scores[0] - scores[mid_idx]) / max(mid_idx, 1)
        v2 = (scores[mid_idx] - scores[lookback_idx]) / max(lookback_idx - mid_idx, 1)
        accel = round(v1 - v2, 3)

    regime = "STEADY"
    if velocity >= 1.5:
        regime = "SURGING_ACCELERATION" if accel > 0 else "DECELERATING_GAIN"
    elif velocity <= -1.5:
        regime = "FALLING_COLLAPSE" if accel < 0 else "DECELERATING_DROP"

    return {
        "ticker": ticker,
        "status": "OK",
        "asof_date": dates[0],
        "past_date": dates[lookback_idx],
        "current_score": current_score,
        "past_score": past_score,
        "velocity": velocity,
        "acceleration": accel,
        "momentum_regime": regime,
    }


if __name__ == "__main__":
    res = seed_historical_signals(limit_dates=10)
    print("Seed result:", res)

    # Test sample tickers
    for test_t in ["GP", "SQURPHARMA", "BATBC"]:
        vel = calculate_velocity_for_ticker(test_t, lookback_bars=5)
        print(f"Velocity for {test_t}:", vel)
