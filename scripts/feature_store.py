"""
Point-in-time daily feature table for Category A universe.

Table: features_daily
  Primary key (ticker, date)
  Fundamentals joined as latest fundamentals_pit.snapshot_date <= price.date
  Technicals computed from trailing closes ending on date
  score / is_eligible from unified_score.score_features (served model)
"""

from __future__ import annotations

import math
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from unified_score import MODEL_ID, score_features

FEATURES_DDL = """
CREATE TABLE IF NOT EXISTS features_daily (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    sector TEXT,
    close REAL,
    volume REAL,
    pe_ratio REAL,
    debt_equity REAL,
    dividend_yield REAL,
    eps REAL,
    nav REAL,
    rsi_14 REAL,
    sma_20 REAL,
    sma_50 REAL,
    score REAL,
    is_eligible INTEGER,
    model_id TEXT,
    debt_clean INTEGER,
    valuation_mos_positive INTEGER,
    rsi_oversold_triggered INTEGER,
    pit_snapshot_date TEXT,
    pit_tradable_date TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_features_daily_date ON features_daily(date);
CREATE INDEX IF NOT EXISTS idx_features_daily_score ON features_daily(date, score DESC);
"""


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return round(100.0 - 100.0 / (1.0 + rs), 4)


def _sma(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    return round(sum(closes[-period:]) / period, 4)


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(FEATURES_DDL)
    # Backward-compat migration: add pit_tradable_date if missing
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(features_daily)").fetchall()}
        if "pit_tradable_date" not in cols:
            conn.execute("ALTER TABLE features_daily ADD COLUMN pit_tradable_date TEXT")
            conn.commit()
    except Exception:
        pass
    conn.commit()


def latest_price_date(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT MAX(date) FROM prices").fetchone()
    return row[0] if row and row[0] else None


def build_features_for_date(asof: str | None = None, category: str = "A") -> dict:
    """Materialize features_daily for one session. Returns summary stats."""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)

    asof = asof or latest_price_date(conn)
    if not asof:
        conn.close()
        return {"ok": False, "reason": "no prices", "rows": 0}

    tickers = [
        r["ticker"]
        for r in conn.execute(
            "SELECT ticker FROM companies WHERE category = ? ORDER BY ticker",
            (category,),
        )
    ]

    if category:
        conn.execute(
            """
            DELETE FROM features_daily
            WHERE date = ? AND ticker NOT IN (SELECT ticker FROM companies WHERE category = ?)
            """,
            (asof, category),
        )

    upserted = 0
    eligible = 0
    for ticker in tickers:
        px = conn.execute(
            "SELECT close, volume FROM prices WHERE ticker=? AND date=?",
            (ticker, asof),
        ).fetchone()
        if not px or px["close"] is None:
            continue

        company = conn.execute(
            "SELECT sector FROM companies WHERE ticker=?", (ticker,)
        ).fetchone()
        sector = company["sector"] if company else None

        pit = conn.execute(
            """
            SELECT snapshot_date, tradable_date, publication_date, publication_is_estimated,
                   eps, nav, pe_ratio, debt_equity, dividend_yield
            FROM fundamentals_pit
            WHERE ticker=? AND tradable_date <= ? AND publication_date <= ? AND pe_ratio IS NOT NULL
            ORDER BY tradable_date DESC, snapshot_date DESC LIMIT 1
            """,
            (ticker, asof, asof),
        ).fetchone()
        if pit is None:
            pit = conn.execute(
                """
                SELECT snapshot_date, tradable_date, publication_date, publication_is_estimated,
                       eps, nav, pe_ratio, debt_equity, dividend_yield
                FROM fundamentals_pit
                WHERE ticker=? AND tradable_date <= ? AND publication_date <= ?
                ORDER BY tradable_date DESC, snapshot_date DESC LIMIT 1
                """,
                (ticker, asof, asof),
            ).fetchone()
        # Strong PIT assert: snapshot may equal or precede tradable; tradable/publication must be <= asof
        if pit is not None:
            assert pit["tradable_date"] is not None and pit["tradable_date"] <= asof, \
                f"PIT violation {ticker}: tradable_date {pit['tradable_date']} > asof {asof}"
            assert pit["publication_date"] is not None and pit["publication_date"] <= asof, \
                f"PIT violation {ticker}: publication_date {pit['publication_date']} > asof {asof}"
            assert pit["snapshot_date"] <= pit["tradable_date"], \
                f"PIT violation {ticker}: snapshot {pit['snapshot_date']} > tradable {pit['tradable_date']}"

        # Trailing closes for RSI/SMA (need ~60 bars)
        hist = conn.execute(
            """
            SELECT close FROM prices
            WHERE ticker=? AND date<=? AND close IS NOT NULL
            ORDER BY date DESC LIMIT 60
            """,
            (ticker, asof),
        ).fetchall()
        closes = [float(r["close"]) for r in reversed(hist)]

        pe = pit["pe_ratio"] if pit else None
        de = pit["debt_equity"] if pit else None
        div_y = pit["dividend_yield"] if pit else None
        eps = pit["eps"] if pit else None
        nav = pit["nav"] if pit else None
        pit_date = pit["snapshot_date"] if pit else None
        pit_trad = pit["tradable_date"] if pit else None

        rsi = _rsi(closes, 14)
        sma20 = _sma(closes, 20)
        sma50 = _sma(closes, 50)

        pub_est = int(pit["publication_is_estimated"] or 0) if pit else 0
        scored = score_features(
            pe=pe,
            debt_equity=de,
            dividend_yield=div_y,
            rsi_14=rsi,
            sector=sector,
            close=float(px["close"]),
            ticker=ticker,
            asof_date=asof,
            enforce_macro_hurdle=True,
            publication_is_estimated=pub_est,
        )
        if scored["is_eligible"]:
            eligible += 1

        sig = scored["active_signals"]
        conn.execute(
            """
            INSERT OR REPLACE INTO features_daily (
                ticker, date, sector, close, volume,
                pe_ratio, debt_equity, dividend_yield, eps, nav,
                rsi_14, sma_20, sma_50,
                score, is_eligible, model_id,
                debt_clean, valuation_mos_positive, rsi_oversold_triggered,
                pit_snapshot_date, pit_tradable_date
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                ticker,
                asof,
                sector,
                float(px["close"]),
                float(px["volume"]) if px["volume"] is not None else None,
                pe,
                de,
                div_y,
                eps,
                nav,
                rsi,
                sma20,
                sma50,
                scored["score"],
                1 if scored["is_eligible"] else 0,
                MODEL_ID,
                1 if sig["debt_clean"] else 0,
                1 if sig["valuation_mos_positive"] else 0,
                1 if sig["rsi_oversold_triggered"] else 0,
                pit_date,
                pit_trad,
            ),
        )
        upserted += 1

    conn.commit()
    conn.close()
    param_hash = None
    try:
        from model_registry import champion_hash
        param_hash = champion_hash()
    except Exception:
        pass

    return {
        "ok": True,
        "date": asof,
        "rows": upserted,
        "eligible": eligible,
        "model_id": MODEL_ID,
        "parameter_hash": param_hash,
    }


def load_scored_universe(asof: str | None = None) -> list[dict]:
    """Read features_daily for date, sorted by score DESC. Builds if missing."""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    asof = asof or latest_price_date(conn)
    cnt = conn.execute(
        "SELECT COUNT(*) AS n FROM features_daily WHERE date=?", (asof,)
    ).fetchone()["n"]
    conn.close()
    if cnt == 0:
        build_features_for_date(asof)

    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT * FROM features_daily WHERE date=?
        ORDER BY score DESC
        """,
        (asof,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_feature_row(ticker: str, asof: str | None = None) -> dict | None:
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    asof = asof or latest_price_date(conn)
    row = conn.execute(
        "SELECT * FROM features_daily WHERE ticker=? AND date=?",
        (ticker, asof),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


if __name__ == "__main__":
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    summary = build_features_for_date(date_arg)
    print(summary)
    if summary.get("ok"):
        uni = load_scored_universe(summary["date"])
        print(f"top5: {[(u['ticker'], u['score'], u['is_eligible']) for u in uni[:5]]}")
