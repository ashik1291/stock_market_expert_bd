"""
Instrument master and point-in-time category history (survivorship- and look-ahead-safe universes).

  instruments          every ticker that ever printed a bar: type/board from the DSE live feed (or the name
                       pattern for instruments no longer listed there), first/last observed trade, status + evidence
  category_history     DSE category (A/B/N/Z) intervals: today's official category walked back through DSE's
                       "Category Change" notices (exact from the disclosure archive start, Nov 2024)

universe_asof(conn, date) returns the tickers that were tradable equities on `date`, from observed trading only,
so research never filters the past with today's company list or today's category.

Usage: python scripts/instrument_master.py
"""

from __future__ import annotations

import datetime
import json
import re
import sqlite3
import sys
from pathlib import Path

import requests
import urllib3

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"
SNAPSHOT_API = "https://www.dse.com.bd/api/live/snapshot"
ACTIVE_WITHIN_SESSIONS = 10
EQUITY_TYPES = ("equity",)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SCHEMA = """
CREATE TABLE IF NOT EXISTS instruments (
    ticker          TEXT PRIMARY KEY,
    instrument_type TEXT NOT NULL,
    board           TEXT,
    sector          TEXT,
    category        TEXT,
    first_trade     TEXT,
    last_trade      TEXT,
    n_bars          INTEGER,
    status          TEXT NOT NULL,
    status_evidence TEXT,
    type_source     TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS category_history (
    ticker      TEXT NOT NULL,
    category    TEXT NOT NULL,
    valid_from  TEXT NOT NULL,
    valid_to    TEXT,
    from_exact  INTEGER NOT NULL,
    evidence    TEXT NOT NULL,
    PRIMARY KEY (ticker, valid_from)
);
"""

LIVE_TYPES = {"EQ": "equity", "MF": "mutual_fund", "GOVDBT": "govt_bond", "CB": "corporate_bond", "DB": "debenture"}
CHANGE_RX = re.compile(r"placed\s+in\s+'?([ABNZ])'?\s+category\s+from\s+(?:the\s+)?existing\s+'?([ABNZ])'?\s+category\s+"
                       r"with\s+effect\s+from\s+(?:today,?\s+i\.?\s*e\.?,?\s*)?([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4})", re.I)


def _date(text: str) -> str | None:
    t = text.strip().rstrip(".,")
    for fmt in ("%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(t, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def fetch_live_instruments() -> tuple[dict, str]:
    d = requests.get(SNAPSHOT_API, headers={"User-Agent": "Mozilla/5.0 (academic research client)"}, timeout=60, verify=False).json()
    rows = d["prices"]["rows"]
    sess = d["prices"].get("session")
    session = sess.get("sessionDate") if isinstance(sess, dict) else None
    if not session:
        raise ValueError("DSE live feed returned no sessionDate; refusing to date the instrument snapshot")
    return {r[0]: {"category": r[11], "board": r[12], "sector": r[13], "type": LIVE_TYPES.get(r[14], r[14].lower())}
            for r in rows}, session


def _pattern_type(ticker: str) -> str:
    if re.fullmatch(r"TB\d+Y\d{4}", ticker):
        return "govt_bond"
    if ticker.endswith(("PBOND", "BOND")):
        return "corporate_bond"
    if re.search(r"MF$|MF\d$|UNIT", ticker):
        return "mutual_fund"
    return "equity"


def build_instruments(conn: sqlite3.Connection, live: dict, live_session: str) -> dict:
    conn.executescript(SCHEMA)
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    sessions = [r[0] for r in conn.execute(
        "SELECT date FROM trading_calendar WHERE is_trading_day = 1 AND date <= (SELECT MAX(date) FROM prices) ORDER BY date DESC LIMIT ?",
        (ACTIVE_WITHIN_SESSIONS,))]
    active_cut = sessions[-1] if sessions else None
    sectors = dict(conn.execute("SELECT ticker, sector FROM companies"))
    stats = {"instruments": 0, "active": 0, "inactive": 0, "by_type": {}}
    for t, first, last, n in conn.execute("SELECT ticker, MIN(date), MAX(date), COUNT(*) FROM prices GROUP BY ticker"):
        info = live.get(t)
        itype = info["type"] if info else _pattern_type(t)
        src = "dse_live_snapshot" if info else "ticker_pattern"
        if last >= active_cut:
            status, ev = "active", f"traded within the last {ACTIVE_WITHIN_SESSIONS} sessions"
        else:
            status = "inactive"
            ev = f"no exchange bar since {last}; {'listed' if info else 'not listed'} in DSE live feed of {live_session}"
        conn.execute("""INSERT OR REPLACE INTO instruments (ticker, instrument_type, board, sector, category, first_trade,
                        last_trade, n_bars, status, status_evidence, type_source, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (t, itype, info["board"] if info else None, sectors.get(t) or (info or {}).get("sector"),
                      info["category"] if info else None, first, last, n, status, ev, src, now))
        stats["instruments"] += 1
        stats[status] += 1
        stats["by_type"][itype] = stats["by_type"].get(itype, 0) + 1
    # companies.category follows the exchange's own category (the scraper used to default missing values to "A").
    stats["company_category_corrected"] = conn.execute("""
        UPDATE companies SET category = (SELECT i.category FROM instruments i WHERE i.ticker = companies.ticker)
        WHERE EXISTS (SELECT 1 FROM instruments i WHERE i.ticker = companies.ticker AND i.category IS NOT NULL
                      AND i.type_source = 'dse_live_snapshot' AND i.category != COALESCE(companies.category, ''))""").rowcount
    conn.commit()
    return stats


def build_category_history(conn: sqlite3.Connection, live: dict, live_session: str) -> dict:
    """Walk today's category back through the official change notices."""
    conn.executescript(SCHEMA)
    changes: dict[str, list] = {}
    archive_start = conn.execute("SELECT MIN(published_date) FROM disclosures").fetchone()[0]
    disregard = {r[0] for r in conn.execute(
        "SELECT code FROM disclosures WHERE summary LIKE '%disregard%categor%'")}
    cancelled = {}
    for code, pub in conn.execute("SELECT code, published_date FROM disclosures WHERE summary LIKE '%Category status remains unchanged%'"):
        cancelled.setdefault(code, []).append(pub)
    for code, pub, body, did in conn.execute(
            "SELECT code, published_date, body, id FROM disclosures WHERE summary LIKE '%Category Change%' ORDER BY published_date"):
        m = CHANGE_RX.search(body or "")
        eff = _date(m.group(3)) if m else None
        if not m or not eff:
            continue
        if any(0 <= (datetime.date.fromisoformat(c) - datetime.date.fromisoformat(pub)).days <= 10 for c in cancelled.get(code, [])):
            continue
        changes.setdefault(code, []).append({"to": m.group(1).upper(), "from": m.group(2).upper(), "eff": eff,
                                             "id": did, "pub": pub})
    conn.execute("DELETE FROM category_history")
    stats = {"tickers": 0, "changes_applied": 0, "chain_breaks": [], "disregard_notices": sorted(disregard)}
    for t, info in live.items():
        if info["type"] not in EQUITY_TYPES + ("mutual_fund",):
            continue
        evs = sorted(changes.get(t, []), key=lambda e: (e["eff"], e["pub"]))
        future = [e for e in evs if e["eff"] > live_session]
        evs = [e for e in evs if e["eff"] <= live_session]
        cur, valid_to = info["category"], (future[0]["eff"] if future else None)
        rows = [(t, e["to"], e["eff"], future[i + 1]["eff"] if i + 1 < len(future) else None, 1,
                 f"DSE id {e['id']} (published {e['pub']}, effective after the live feed date)") for i, e in enumerate(future)]
        for e in reversed(evs):
            if e["to"] != cur:
                stats["chain_breaks"].append((t, e["eff"], e["to"], cur))
            rows.append((t, e["to"], e["eff"], valid_to, 1, f"DSE id {e['id']} (published {e['pub']})"))
            valid_to, cur = e["eff"], e["from"]
            stats["changes_applied"] += 1
        rows.append((t, cur, archive_start, valid_to, 0,
                     f"category before the first archived change; exact only from {archive_start}"
                     if evs else f"unchanged since disclosure archive start {archive_start} (live feed {live_session})"))
        conn.executemany("""INSERT OR REPLACE INTO category_history (ticker, category, valid_from, valid_to, from_exact, evidence)
                            VALUES (?,?,?,?,?,?)""", rows)
        stats["tickers"] += 1
    conn.commit()
    stats["chain_breaks_count"] = len(stats["chain_breaks"])
    return stats


def category_asof(conn: sqlite3.Connection, ticker: str, date: str) -> str | None:
    row = conn.execute("""SELECT category FROM category_history WHERE ticker = ? AND valid_from <= ?
                          AND (valid_to IS NULL OR valid_to > ?) ORDER BY valid_from DESC LIMIT 1""",
                       (ticker, date, date)).fetchone()
    return row[0] if row else None


def universe_asof(conn: sqlite3.Connection, date: str, types: tuple = EQUITY_TYPES, lookback_sessions: int = 20) -> list[str]:
    """Tickers of the given types that printed a bar in the `lookback_sessions` sessions up to `date`."""
    start = conn.execute("""SELECT MIN(date) FROM (SELECT date FROM trading_calendar WHERE is_trading_day = 1 AND date <= ?
                            ORDER BY date DESC LIMIT ?)""", (date, lookback_sessions)).fetchone()[0]
    ph = ",".join("?" * len(types))
    return [r[0] for r in conn.execute(f"""
        SELECT DISTINCT p.ticker FROM prices p JOIN instruments i ON i.ticker = p.ticker
        WHERE p.date BETWEEN ? AND ? AND i.instrument_type IN ({ph}) ORDER BY p.ticker""", (start, date, *types))]


def liquidity_schedule(conn: sqlite3.Connection, start: str, end: str, top_n: int = 20, lookback_sessions: int = 60,
                       exclude=None) -> list[tuple[str, frozenset]]:
    """
    Monthly point-in-time universe: on the first session of each month, the `top_n` equities by average traded value
    over the previous `lookback_sessions` sessions, using only data up to that session (no survivorship, no look-ahead).
    `exclude(ticker)` drops names (e.g. a Shariah screen) before ranking.
    """
    firsts = [r[0] for r in conn.execute("""
        SELECT MIN(date) FROM trading_calendar WHERE is_trading_day = 1 AND date BETWEEN ? AND ?
        GROUP BY substr(date, 1, 7) ORDER BY 1""", (start, end))]
    sched = []
    for d in firsts:
        lo = conn.execute("""SELECT MIN(date) FROM (SELECT date FROM trading_calendar WHERE is_trading_day = 1 AND date < ?
                             ORDER BY date DESC LIMIT ?)""", (d, lookback_sessions)).fetchone()[0]
        if not lo:
            continue
        rows = conn.execute("""
            SELECT p.ticker, AVG(COALESCE(p.value, 0)) AS v FROM prices p
            JOIN instruments i ON i.ticker = p.ticker AND i.instrument_type = 'equity'
            WHERE p.date >= ? AND p.date < ? GROUP BY p.ticker ORDER BY v DESC""", (lo, d)).fetchall()
        picked = [t for t, _ in rows if not (exclude and exclude(t))][:top_n]
        sched.append((d, frozenset(picked)))
    return sched


def member_on(schedule: list[tuple[str, frozenset]], date: str) -> frozenset:
    import bisect
    i = bisect.bisect_right([d for d, _ in schedule], date) - 1
    return schedule[i][1] if i >= 0 else frozenset()


def main():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    live, session = fetch_live_instruments()
    out = {"instruments": build_instruments(conn, live, session),
           "category_history": build_category_history(conn, live, session)}
    out["category_history"]["chain_breaks"] = out["category_history"]["chain_breaks"][:20]
    print(json.dumps(out, indent=1))
    conn.close()
    sys.exit(0)


if __name__ == "__main__":
    main()
