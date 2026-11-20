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
        if "traded_value_20d" not in cols:
            conn.execute("ALTER TABLE features_daily ADD COLUMN traded_value_20d REAL")
            conn.commit()
    except Exception:
        pass
    conn.commit()


def latest_price_date(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT MAX(date) FROM prices").fetchone()
    return row[0] if row and row[0] else None


CONSERVATIVE_PIT_SOURCES = ("bsec_statutory_filing", "dse_corporate_action")
PRICE_ACTION_TYPES = ("bonus_dividend", "split", "rights_split")
TTM_DAYS = 365


def universe_asof(conn: sqlite3.Connection, asof: str, category: str | None) -> list[tuple[str, str | None]]:
    """
    (ticker, sector) of equities that printed a bar on asof and were in `category` on that date.
    Category is point-in-time from category_history; before its first interval the earliest known category is used.
    Names that later stopped trading stay in historical universes (no survivorship filter).
    """
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if not {"instruments", "category_history"} <= have:
        return [(r[0], r[1]) for r in conn.execute(
            "SELECT ticker, sector FROM companies WHERE category = ? ORDER BY ticker", (category,))]
    rows = conn.execute("""
        SELECT p.ticker, COALESCE(c.sector, i.sector),
               (SELECT h.category FROM category_history h WHERE h.ticker = p.ticker AND h.valid_from <= p.date
                  AND (h.valid_to IS NULL OR h.valid_to > p.date) ORDER BY h.valid_from DESC LIMIT 1),
               (SELECT h.category FROM category_history h WHERE h.ticker = p.ticker ORDER BY h.valid_from LIMIT 1),
               c.category
        FROM prices p JOIN instruments i ON i.ticker = p.ticker AND i.instrument_type = 'equity'
        LEFT JOIN companies c ON c.ticker = p.ticker
        WHERE p.date = ? ORDER BY p.ticker""", (asof,)).fetchall()
    return [(t, sec) for t, sec, cat_pit, cat_first, cat_now in rows
            if not category or (cat_pit or cat_first or cat_now) == category]


def fundamentals_asof(conn: sqlite3.Connection, ticker: str, asof: str, close: float) -> dict:
    """
    Each input from its own latest published source as of asof: annual EPS/NAV, D/E, P/E = close / annual EPS,
    dividend yield = official cash dividends with record date in the trailing year / close.
    """
    ann = conn.execute("""
        SELECT snapshot_date, tradable_date, publication_date, publication_is_estimated, publication_source, eps, nav
        FROM fundamentals_pit
        WHERE ticker = ? AND filing_type = 'annual' AND eps IS NOT NULL AND tradable_date <= ? AND publication_date <= ?
        ORDER BY tradable_date DESC, snapshot_date DESC LIMIT 1""", (ticker, asof, asof)).fetchone()
    de = conn.execute("""
        SELECT debt_equity FROM fundamentals_pit
        WHERE ticker = ? AND debt_equity IS NOT NULL AND tradable_date <= ? AND publication_date <= ?
        ORDER BY tradable_date DESC, snapshot_date DESC LIMIT 1""", (ticker, asof, asof)).fetchone()
    import datetime as _dt
    start = (_dt.date.fromisoformat(asof) - _dt.timedelta(days=TTM_DAYS)).isoformat()
    cash = conn.execute("""
        SELECT COALESCE(SUM(cash_amount), 0) FROM corporate_actions
        WHERE ticker = ? AND action_type = 'cash_dividend' AND record_date > ? AND record_date <= ?""",
                        (ticker, start, asof)).fetchone()[0]
    eps = ann["eps"] if ann else None
    return {
        "row": ann,
        "eps": eps,
        "nav": ann["nav"] if ann else None,
        "pe": round(close / eps, 4) if (eps is not None and eps > 0 and close > 0) else None,
        "debt_equity": de[0] if de else None,
        "dividend_yield": round(100.0 * cash / close, 4) if close > 0 else None,
    }


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

    members = universe_asof(conn, asof, category)
    tickers = [t for t, _ in members]
    sector_of = dict(members)

    if category:
        conn.execute(f"DELETE FROM features_daily WHERE date = ? AND ticker NOT IN ({','.join('?' * len(tickers)) or 'NULL'})",
                     (asof, *tickers))

    upserted = 0
    eligible = 0
    for ticker in tickers:
        px = conn.execute(
            "SELECT close, volume FROM prices WHERE ticker=? AND date=?",
            (ticker, asof),
        ).fetchone()
        if not px or px["close"] is None:
            continue

        sector = sector_of.get(ticker)
        fa = fundamentals_asof(conn, ticker, asof, float(px["close"]))
        pit = fa["row"]
        # Strong PIT assert: snapshot may equal or precede tradable; tradable/publication must be <= asof
        if pit is not None:
            assert pit["tradable_date"] is not None and pit["tradable_date"] <= asof, \
                f"PIT violation {ticker}: tradable_date {pit['tradable_date']} > asof {asof}"
            assert pit["publication_date"] is not None and pit["publication_date"] <= asof, \
                f"PIT violation {ticker}: publication_date {pit['publication_date']} > asof {asof}"
            assert pit["snapshot_date"] <= pit["tradable_date"], \
                f"PIT violation {ticker}: snapshot {pit['snapshot_date']} > tradable {pit['tradable_date']}"

        # Trailing closes for RSI/SMA (need ~60 bars, backward-adjusted for bonus splits)
        hist = conn.execute(
            """
            SELECT date, close FROM prices
            WHERE ticker=? AND date<=? AND close IS NOT NULL
            ORDER BY date DESC LIMIT 60
            """,
            (ticker, asof),
        ).fetchall()
        if hist:
            hist_rev = list(reversed(hist))
            earliest_dt = hist_rev[0]["date"]
            ca_rows = conn.execute(
                """
                SELECT record_date, adjustment_factor FROM corporate_actions
                WHERE ticker=? AND action_type IN ('bonus_dividend', 'split', 'rights_split')
                  AND record_date > ? AND record_date <= ?
                  AND adjustment_factor IS NOT NULL AND adjustment_factor > 0
                ORDER BY record_date ASC
                """,
                (ticker, earliest_dt, asof),
            ).fetchall()
            if ca_rows:
                closes = []
                for r in hist_rev:
                    d, bar_px = r["date"], float(r["close"])
                    adj = 1.0
                    for rec_d, fac in ca_rows:
                        if d < rec_d:
                            adj *= float(fac)
                    closes.append(round(bar_px * adj, 2))
            else:
                closes = [float(r["close"]) for r in hist_rev]
        else:
            closes = []

        pe = fa["pe"]
        de = fa["debt_equity"]
        div_y = fa["dividend_yield"]
        eps = fa["eps"]
        nav = fa["nav"]
        tv = conn.execute("""SELECT AVG(value) FROM (SELECT value FROM prices WHERE ticker = ? AND date <= ? AND value IS NOT NULL
                             ORDER BY date DESC LIMIT 20)""", (ticker, asof)).fetchone()[0]
        pit_date = pit["snapshot_date"] if pit else None
        pit_trad = pit["tradable_date"] if pit else None

        rsi = _rsi(closes, 14)
        sma20 = _sma(closes, 20)
        sma50 = _sma(closes, 50)

        # Statutory-deadline and board-declaration estimates are latest-possible dates (never early),
        # so only other estimates carry look-ahead risk under the strict PIT gate.
        pub_est = 0
        if pit and int(pit["publication_is_estimated"] or 0) == 1:
            pub_est = 0 if pit["publication_source"] in CONSERVATIVE_PIT_SOURCES else 1
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
            strict_verified_pit=True,
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
                pit_snapshot_date, pit_tradable_date, traded_value_20d
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                tv,
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
