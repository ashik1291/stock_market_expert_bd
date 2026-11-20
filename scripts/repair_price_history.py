"""
scripts/repair_price_history.py — Reconcile the prices table against the DSE day-end archive.

Fetches raw day-end bars (bdshare / DSE archive) for every ticker in the window and:
  * inserts bars missing from the database,
  * overwrites bars whose OHLCV differs from the exchange record (e.g. bars that were
    scaled by a future corporate-action factor at insert time, or volume filled from ycp),
  * reports database-only bars (no exchange record) without touching them.

Usage:
  python scripts/repair_price_history.py --start 2024-10-01 --end 2026-11-19          # dry run
  python scripts/repair_price_history.py --start 2024-10-01 --end 2026-11-19 --apply
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

from db import get_db_connection  # noqa: E402
from provenance import mark_archive_verified, new_ingest, stamp_prices  # noqa: E402

DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"
REPORT_PATH = BASE_DIR / "reports" / "integrity" / "price_repair_report.json"
CHUNK_DAYS = 180
ARCHIVE_SOURCE = "dse_day_end_archive"
PRICE_TOL = 0.005

logging.getLogger("bdshare").setLevel(logging.CRITICAL)
log = logging.getLogger("repair_price_history")


def _f(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v


def normalize_source_row(date_str: str, row: dict) -> dict | None:
    close = _f(row.get("close"))
    if close is None or close <= 0:
        return None
    o, h, l = _f(row.get("open")), _f(row.get("high")), _f(row.get("low"))
    # The archive reports 0 for open/high/low on no-trade days; the bar is flat at close.
    o = o if o and o > 0 else close
    h = h if h and h > 0 else close
    l = l if l and l > 0 else close
    if h < l:
        return None
    vol = row.get("volume")
    val = _f(row.get("value"))
    return {
        "date": date_str,
        "open": round(o, 4), "high": round(h, 4), "low": round(l, 4), "close": round(close, 4),
        "volume": int(vol) if vol is not None else 0,
        "value": val if val is not None else 0.0,
    }


def fetch_source(ticker: str, start: str, end: str) -> dict[str, dict]:
    from bdshare import get_historical_data
    out: dict[str, dict] = {}
    cur = datetime.date.fromisoformat(start)
    stop = datetime.date.fromisoformat(end)
    errors, chunks = [], 0
    while cur <= stop:
        chunk_end = min(cur + datetime.timedelta(days=CHUNK_DAYS - 1), stop)
        chunks += 1
        try:
            df = get_historical_data(cur.isoformat(), chunk_end.isoformat(), ticker)
        except Exception as e:
            # A chunk before listing or during suspension has no archive rows; only total failure is fatal.
            errors.append(f"{cur}..{chunk_end}: {str(e)[:120]}")
            df = None
        if df is not None and not df.empty:
            for idx, r in df.iterrows():
                d = str(idx)[:10]
                rec = normalize_source_row(d, {k.lower(): v for k, v in r.items()})
                if rec:
                    out[d] = rec
        cur = chunk_end + datetime.timedelta(days=1)
    if errors and len(errors) == chunks:
        raise RuntimeError(f"{ticker}: every chunk failed; first: {errors[0]}")
    return out


def bar_differs(db_row: tuple, src: dict) -> str | None:
    o, h, l, c, v = db_row
    if c is None or abs(c - src["close"]) > PRICE_TOL:
        return "close"
    for name, dbv in (("open", o), ("high", h), ("low", l)):
        if dbv is None or abs(dbv - src[name]) > PRICE_TOL:
            return name
    if v is None or v != src["volume"]:
        return "volume"
    return None


def universe(conn, start: str, end: str) -> list[str]:
    lo = (datetime.date.fromisoformat(start) - datetime.timedelta(days=120)).isoformat()
    rows = conn.execute(
        "SELECT DISTINCT ticker FROM prices WHERE date >= ? AND date <= ?", (lo, end)
    ).fetchall()
    return sorted({r[0] for r in rows})


def run(start: str, end: str, apply: bool, tickers: list[str] | None) -> dict:
    conn = get_db_connection(DB_PATH)
    try:
        names = tickers or universe(conn, start, end)
        inserts, updates, matched = [], [], []
        reasons = Counter()
        db_only = defaultdict(list)
        source_dates = Counter()
        failures = {}

        for i, t in enumerate(names, 1):
            try:
                src = fetch_source(t, start, end)
            except RuntimeError as e:
                failures[t] = str(e)
                continue
            db_rows = {
                r[0]: r[1:] for r in conn.execute(
                    "SELECT date, open, high, low, close, volume FROM prices "
                    "WHERE ticker = ? AND date BETWEEN ? AND ?", (t, start, end)
                )
            }
            if not src:
                failures[t] = "no source rows"
                continue
            for d, rec in src.items():
                source_dates[d] += 1
                if d not in db_rows:
                    inserts.append((t, rec))
                else:
                    why = bar_differs(db_rows[d], rec)
                    if why:
                        reasons[why] += 1
                        updates.append((t, rec))
                    else:
                        matched.append((t, d))
            src_min = min(src)
            for d in db_rows:
                if d not in src and d >= src_min:
                    db_only[d].append(t)
            if i % 50 == 0:
                print(f"  ... {i}/{len(names)} tickers, {len(inserts)} inserts, {len(updates)} updates", flush=True)

        cal = {r[0]: r[1] for r in conn.execute(
            "SELECT date, is_trading_day FROM trading_calendar WHERE date BETWEEN ? AND ?", (start, end)
        )}
        non_calendar_source_dates = {d: n for d, n in source_dates.items() if cal.get(d) != 1}
        # The write guard rejects bars on calendar-closed days; fix the calendar first, then rerun.
        closed = {d for d, v in cal.items() if v == 0}
        inserts = [(t, r) for t, r in inserts if r["date"] not in closed]
        updates = [(t, r) for t, r in updates if r["date"] not in closed]

        if apply:
            with conn:
                for t, r in inserts:
                    conn.execute(
                        "INSERT OR IGNORE INTO prices (ticker, date, open, high, low, close, volume, value) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        (t, r["date"], r["open"], r["high"], r["low"], r["close"], r["volume"], r["value"]),
                    )
                for t, r in updates:
                    conn.execute(
                        "UPDATE prices SET open=?, high=?, low=?, close=?, volume=?, value=? "
                        "WHERE ticker=? AND date=?",
                        (r["open"], r["high"], r["low"], r["close"], r["volume"], r["value"], t, r["date"]),
                    )
                today = datetime.date.today().isoformat()
                if inserts or updates:
                    iid = new_ingest(conn, ARCHIVE_SOURCE, f"bdshare get_historical_data {start}..{end}")
                    stamp_prices(conn, iid, ARCHIVE_SOURCE, [(t, r["date"]) for t, r in inserts + updates], verified_on=today)
                mark_archive_verified(conn, matched, today)

        report = {
            "window": [start, end],
            "applied": apply,
            "tickers_checked": len(names),
            "inserted": len(inserts),
            "updated": len(updates),
            "update_reasons": dict(reasons),
            "db_only_bars": {d: len(v) for d, v in sorted(db_only.items())},
            "source_dates_not_trading_in_calendar": non_calendar_source_dates,
            "fetch_failures": failures,
        }
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report
    finally:
        conn.close()


def fetch_day_end_all(date_str: str) -> dict[str, dict]:
    """Official DSE day-end bars for every instrument on one date (one archive request)."""
    from bdshare import get_historical_data
    try:
        df = get_historical_data(date_str, date_str, "All Instrument")
    except Exception:
        return {}
    out = {}
    if df is None or df.empty:
        return out
    for idx, r in df.iterrows():
        row = {k.lower(): v for k, v in r.items()}
        if str(idx)[:10] != date_str:
            continue
        rec = normalize_source_row(date_str, row)
        sym = str(row.get("symbol") or "").strip()
        if rec and sym:
            out[sym] = rec
    return out


def reconcile_recent_sessions(conn, sessions: int = 5, apply: bool = True) -> dict:
    """
    Daily post-close step: make the last `sessions` trading days match the official day-end archive.
    Live snapshots carry no open price and can freeze an intraday print, so the archive is the
    record of truth. Sessions the archive does not have yet are left for the next run.
    """
    dates = [r[0] for r in conn.execute("""
        SELECT date FROM trading_calendar WHERE is_trading_day = 1
          AND date <= (SELECT MAX(date) FROM prices) ORDER BY date DESC LIMIT ?
    """, (sessions,))]
    report = {"sessions": {}, "inserted": 0, "updated": 0}
    # Keep the tracked universe stable: the archive also lists SME/debt instruments never stored here.
    tracked = {r[0] for r in conn.execute("SELECT ticker FROM companies")}
    tracked |= {r[0] for r in conn.execute("""
        SELECT DISTINCT ticker FROM prices WHERE date >= (
            SELECT MIN(date) FROM (SELECT DISTINCT date FROM prices ORDER BY date DESC LIMIT 30))
    """)}
    for d in sorted(dates):
        src = {t: r for t, r in fetch_day_end_all(d).items() if t in tracked}
        if len(src) < 50:
            report["sessions"][d] = "archive not available yet"
            continue
        db = {r[0]: r[1:] for r in conn.execute(
            "SELECT ticker, open, high, low, close, volume FROM prices WHERE date = ?", (d,))}
        ins = [(t, r) for t, r in src.items() if t not in db]
        upd = [(t, r) for t, r in src.items() if t in db and bar_differs(db[t], r)]
        same = [(t, d) for t, r in src.items() if t in db and not bar_differs(db[t], r)]
        if apply:
            with conn:
                for t, r in ins:
                    conn.execute("INSERT OR IGNORE INTO prices (ticker, date, open, high, low, close, volume, value) "
                                 "VALUES (?,?,?,?,?,?,?,?)",
                                 (t, d, r["open"], r["high"], r["low"], r["close"], r["volume"], r["value"]))
                for t, r in upd:
                    conn.execute("UPDATE prices SET open=?, high=?, low=?, close=?, volume=?, value=? WHERE ticker=? AND date=?",
                                 (r["open"], r["high"], r["low"], r["close"], r["volume"], r["value"], t, d))
                today = datetime.date.today().isoformat()
                if ins or upd:
                    iid = new_ingest(conn, ARCHIVE_SOURCE, f"bdshare get_historical_data {d} All Instrument", raw=src)
                    stamp_prices(conn, iid, ARCHIVE_SOURCE, [(t, d) for t, _ in ins + upd], verified_on=today)
                mark_archive_verified(conn, same, today)
        report["sessions"][d] = {"archive_bars": len(src), "inserted": len(ins), "updated": len(upd)}
        report["inserted"] += len(ins)
        report["updated"] += len(upd)
    return report


def _on_tick(px: float, tol: float = 1e-6) -> bool:
    return abs(round(px * 10) - px * 10) < tol


def unscale_pre_archive(conn, start: str, end: str, apply: bool) -> dict:
    """
    Bars older than the exchange archive's reach that were scaled by a corporate-action factor at
    insert time. For each ticker the off-tick run [first, last] is divided by the factor (or product
    of factors) from corporate_actions that puts >= 90% of those bars back on the Tk 0.10 tick and
    makes the run join the first later on-tick bar within 3%. Unprovable tickers are reported only.
    """
    from itertools import combinations
    fixed, unresolved = {}, {}
    tickers = [r[0] for r in conn.execute("""
        SELECT DISTINCT p.ticker FROM prices p JOIN companies c ON c.ticker = p.ticker
        WHERE p.date BETWEEN ? AND ? AND p.close >= 10
    """, (start, end))]
    for t in tickers:
        bars = conn.execute("SELECT date, open, high, low, close FROM prices WHERE ticker = ? AND date BETWEEN ? AND ? ORDER BY date",
                            (t, start, end)).fetchall()
        off = [b for b in bars if b[4] and not _on_tick(b[4])]
        if not off:
            continue
        first, last = off[0][0], off[-1][0]
        run = [b for b in bars if first <= b[0] <= last]
        facs = sorted({round(float(r[0]), 6) for r in conn.execute(
            "SELECT adjustment_factor FROM corporate_actions WHERE ticker = ? AND record_date > ? AND adjustment_factor > 0 AND adjustment_factor < 1",
            (t, first))})
        nxt = conn.execute("SELECT close FROM prices WHERE ticker = ? AND date > ? ORDER BY date LIMIT 1", (t, last)).fetchone()
        trials = set()
        for k in range(1, min(3, len(facs)) + 1):
            for combo in combinations(facs, k):
                f = 1.0
                for x in combo:
                    f *= x
                trials.add(f)
        # Standard DSE bonus ratios, for factors whose corporate-action row no longer exists.
        trials |= {1.0 / (1.0 + i * 0.005) for i in range(1, 201)}
        best = None
        for f in sorted(trials):
            if True:
                ok = sum(1 for b in run if _on_tick(b[4] / f, tol=0.002)) / len(run)
                joins = bool(nxt and nxt[0]) and abs((run[-1][4] / f) / nxt[0] - 1.0) <= 0.03
                if ok >= 0.9 and joins and (best is None or ok > best[1]):
                    best = (f, ok)
        if not best:
            unresolved[t] = {"off_tick_bars": len(off), "window": [first, last], "known_factors": facs}
            continue
        f = best[0]
        fixed[t] = {"factor": round(f, 6), "bars": len(run), "on_tick_after": round(best[1], 3), "window": [first, last]}
        if apply:
            for d, o, h, l, c in run:
                conn.execute("UPDATE prices SET open=?, high=?, low=?, close=? WHERE ticker=? AND date=?",
                             tuple(round(v / f, 2) if v else v for v in (o, h, l, c)) + (t, d))
    if apply:
        conn.commit()
    return {"fixed": fixed, "unresolved": unresolved}


def main():
    if "--recent" in sys.argv:
        sessions = int(sys.argv[sys.argv.index("--recent") + 1]) if len(sys.argv) > sys.argv.index("--recent") + 1 else 5
        conn = get_db_connection(DB_PATH)
        try:
            print(json.dumps(reconcile_recent_sessions(conn, sessions=sessions), indent=2))
        finally:
            conn.close()
        return
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--tickers", nargs="*")
    a = ap.parse_args()
    rep = run(a.start, a.end, a.apply, [t.upper() for t in a.tickers] if a.tickers else None)
    summary = {k: v for k, v in rep.items() if k not in ("db_only_bars", "fetch_failures")}
    summary["db_only_dates"] = len(rep["db_only_bars"])
    summary["fetch_failure_count"] = len(rep["fetch_failures"])
    print(json.dumps(summary, indent=2))
    print(f"Full report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
