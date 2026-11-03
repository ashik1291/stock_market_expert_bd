"""
Benchmark helpers for Epoch 2:
  1. Official DSEX from market_summary (not prices.ticker='DSEX' — that table is empty)
  2. Equal-weighted total-return proxy from Category A closes (cash dividends not yet PIT)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"


def get_dsex_level(conn: sqlite3.Connection | None = None, date: str | None = None) -> tuple[str | None, float | None]:
    """Return (date, dsex) from market_summary. Prefer exact date, else latest <= date."""
    own = conn is None
    if own:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        conn.execute("PRAGMA busy_timeout = 30000;")
    try:
        if date:
            row = conn.execute(
                "SELECT date, dsex FROM market_summary WHERE date = ? AND dsex IS NOT NULL",
                (date,),
            ).fetchone()
            if row:
                return row[0], float(row[1])
            row = conn.execute(
                """
                SELECT date, dsex FROM market_summary
                WHERE date <= ? AND dsex IS NOT NULL
                ORDER BY date DESC LIMIT 1
                """,
                (date,),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT date, dsex FROM market_summary
                WHERE dsex IS NOT NULL
                ORDER BY date DESC LIMIT 1
                """
            ).fetchone()
        if not row:
            return None, None
        return row[0], float(row[1])
    finally:
        if own:
            conn.close()


def dsex_return_pct(baseline_date: str, asof_date: str | None = None) -> dict:
    """Percent change in market_summary.dsex between baseline and asof."""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    try:
        b_date, b_lvl = get_dsex_level(conn, baseline_date)
        a_date, a_lvl = get_dsex_level(conn, asof_date)
        if b_lvl is None or a_lvl is None or b_lvl == 0:
            return {
                "ok": False,
                "baseline_date": b_date,
                "asof_date": a_date,
                "baseline": b_lvl,
                "asof": a_lvl,
                "return_pct": None,
                "source": "market_summary.dsex",
            }
        ret = round(((a_lvl - b_lvl) / b_lvl) * 100.0, 4)
        return {
            "ok": True,
            "baseline_date": b_date,
            "asof_date": a_date,
            "baseline": b_lvl,
            "asof": a_lvl,
            "return_pct": ret,
            "source": "market_summary.dsex",
        }
    finally:
        conn.close()


def equal_weight_category_a_nav(
    start_date: str,
    end_date: str | None = None,
    initial_nav: float = 100.0,
) -> dict:
    """
    Equal-weight daily-rebalanced Category A Total Return Index (includes PIT net cash dividends).
    Uses close-to-close mean cross-sectional return plus cash dividend distributions each session.
    ADV illiquid filter: stocks with rolling 20d median daily value < BDT 300k are excluded
    from the EQW cross-section (mirrors net_of_cost factor filter). Price-only note preserved.
    """
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.row_factory = sqlite3.Row
    try:
        end = end_date or conn.execute("SELECT MAX(date) FROM prices").fetchone()[0]
        dates = [
            r[0]
            for r in conn.execute(
                """
                SELECT DISTINCT p.date FROM prices p
                JOIN companies c ON c.ticker = p.ticker
                WHERE c.category = 'A' AND p.date >= ? AND p.date <= ?
                  AND p.close IS NOT NULL AND p.close > 0
                ORDER BY p.date
                """,
                (start_date, end),
            ).fetchall()
        ]
        if len(dates) < 2:
            return {"ok": False, "reason": "insufficient dates", "nav_series": []}

        # ---- ADV illiquid filter (rolling 20d median value < 300k) — per-session eligible set ----
        # Mirrors net_of_cost_factor_backtest.py:51 rolling 20d median daily value < 300000.
        ADV_THRESHOLD = 300000.0
        adv_excluded: set[str] = set()

        # Pre-fetch all PIT cash dividends in window (net of 10% statutory AIT)
        div_rows = conn.execute("""
            SELECT ticker, record_date, cash_amount FROM corporate_actions
            WHERE action_type = 'cash_dividend' AND record_date >= ? AND record_date <= ?
              AND cash_amount IS NOT NULL AND cash_amount > 0
        """, (start_date, end)).fetchall()
        div_lookup = {(str(r[0]), str(r[1])): float(r[2]) * 0.90 for r in div_rows}

        # Portable: fetch close*volume history and compute medians in Python.
        val_history: dict[str, list[tuple[str, float]]] = {}
        for r in conn.execute(
            """
            SELECT p.ticker, p.date, (p.close * COALESCE(p.volume,0)) AS val
            FROM prices p JOIN companies c ON c.ticker=p.ticker
            WHERE c.category='A' AND p.date >= ? AND p.date <= ? AND p.close>0
            ORDER BY p.ticker, p.date
            """,
            (start_date, end),
        ).fetchall():
            val_history.setdefault(str(r[0]), []).append((str(r[1]), float(r[2] or 0.0)))

        # Per-session median lookup: for each date, tickers whose 20d trailing median < threshold
        # are excluded that session. Build map date -> excluded set, then session-level filter below.
        date_excluded: dict[str, set[str]] = {d: set() for d in dates}
        for tkr, series in val_history.items():
            series.sort(key=lambda x: x[0])
            vals = [v for _, v in series]
            dts  = [d for d, _ in series]
            for i, d in enumerate(dts):
                window = vals[max(0, i - 19): i + 1]
                if len(window) >= 10:  # require at least 10 bars for median
                    sv = sorted(window)
                    n = len(sv)
                    med = (sv[n // 2] if n % 2 else (sv[n // 2 - 1] + sv[n // 2]) / 2.0)
                    if med < ADV_THRESHOLD and med > 0:
                        if d in date_excluded:
                            date_excluded[d].add(tkr)
                        adv_excluded.add(tkr)
        _adv_filter_note = (
            f"ADV filter applied: rolling 20d median value < {int(ADV_THRESHOLD):,} excluded per session "
            f"({len(adv_excluded)} tickers ever excluded)."
        )

        nav = float(initial_nav)
        series = [{"date": dates[0], "nav": nav, "daily_ret_pct": 0.0}]
        prev_closes: dict[str, float] = {}

        # Seed prev with first date (after ADV filter that session)
        bad0 = date_excluded.get(dates[0], set())
        for r in conn.execute(
            """
            SELECT p.ticker, p.close FROM prices p
            JOIN companies c ON c.ticker = p.ticker
            WHERE c.category = 'A' AND p.date = ? AND p.close > 0
            """,
            (dates[0],),
        ):
            t = str(r["ticker"])
            if t in bad0:
                continue
            prev_closes[t] = float(r["close"])

        for dt in dates[1:]:
            rows = conn.execute(
                """
                SELECT p.ticker, p.close FROM prices p
                JOIN companies c ON c.ticker = p.ticker
                WHERE c.category = 'A' AND p.date = ? AND p.close > 0
                """,
                (dt,),
            ).fetchall()
            bad = date_excluded.get(dt, set())
            rets = []
            curr = {}
            for r in rows:
                t = str(r["ticker"])
                if t in bad:
                    continue
                px = float(r["close"])
                curr[t] = px
                if t in prev_closes and prev_closes[t] > 0:
                    c_div = div_lookup.get((t, dt), 0.0)
                    rets.append(((px + c_div) / prev_closes[t]) - 1.0)
            day_ret = sum(rets) / len(rets) if rets else 0.0
            nav *= 1.0 + day_ret
            series.append({"date": dt, "nav": round(nav, 6), "daily_ret_pct": round(day_ret * 100, 4)})
            prev_closes = curr

        start_nav = series[0]["nav"]
        end_nav = series[-1]["nav"]
        return {
            "ok": True,
            "source": "equal_weight_category_a_total_return",
            "benchmark_type": "TOTAL_RETURN_NET_DIVIDENDS",
            "start_date": series[0]["date"],
            "end_date": series[-1]["date"],
            "start_nav": start_nav,
            "end_nav": round(end_nav, 6),
            "return_pct": round(((end_nav - start_nav) / start_nav) * 100.0, 4),
            "sessions": len(series),
            "nav_series": series,
            "adv_filter": {
                "threshold_bdt": int(ADV_THRESHOLD),
                "rolling_window": 20,
                "stat": "median_daily_value",
                "ever_excluded_ticker_count": len(adv_excluded),
                "note": _adv_filter_note,
            },
        }
    finally:
        conn.close()


if __name__ == "__main__":
    d = get_dsex_level()
    print(f"DSEX latest: date={d[0]} level={d[1]}")
    eqw = equal_weight_category_a_nav("2026-10-01")
    print(
        f"EQW Cat-A: ok={eqw.get('ok')} {eqw.get('start_date')}->{eqw.get('end_date')} "
        f"ret={eqw.get('return_pct')}%"
    )
