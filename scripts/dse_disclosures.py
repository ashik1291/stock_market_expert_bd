"""
Official DSE disclosure archive and financial-filing parser.

Source: https://www.dse.com.bd/api/live/news (the exchange's own announcement feed; history starts
around Nov 2024 — older announcements are no longer served by DSE).

Tables
  disclosures            every announcement row exactly as published (immutable; id = DSE id)
  disclosure_financials  one row per financial filing parsed from the announcement text:
                         period end, quarter, EPS (discrete period), NAV per share, NOCFPS (year-to-date),
                         first publication date/time and the DSE ids it was parsed from

Usage
  python scripts/dse_disclosures.py backfill [--from 2024-01-01] [--tickers A B]
  python scripts/dse_disclosures.py daily [--days 10]
  python scripts/dse_disclosures.py parse
"""

from __future__ import annotations

import argparse
import calendar
import datetime
import hashlib
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

import requests
import urllib3

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"
API = "https://www.dse.com.bd/api/live/news"
HEADERS = {"User-Agent": "Mozilla/5.0 (academic research client)"}
ARCHIVE_START = "2024-01-01"
API_ROW_CAP = 500

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SCHEMA = """
CREATE TABLE IF NOT EXISTS disclosures (
    id             TEXT PRIMARY KEY,
    code           TEXT NOT NULL,
    type           TEXT,
    published_date TEXT NOT NULL,
    published_time TEXT,
    filed_at       TEXT,
    summary        TEXT,
    body           TEXT,
    body_sha256    TEXT NOT NULL,
    source_url     TEXT NOT NULL,
    fetched_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_disclosures_code_date ON disclosures(code, published_date);
CREATE TABLE IF NOT EXISTS disclosure_financials (
    code           TEXT NOT NULL,
    period_end     TEXT NOT NULL,
    kind           TEXT NOT NULL CHECK (kind IN ('interim', 'annual')),
    quarter        INTEGER NOT NULL,
    published_date TEXT NOT NULL,
    published_time TEXT,
    eps            REAL,
    nav            REAL,
    nocfps         REAL,
    basis          TEXT,
    disclosure_ids TEXT NOT NULL,
    parsed_at      TEXT NOT NULL,
    PRIMARY KEY (code, period_end, kind, published_date)
);
"""

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
MONTHS["sept"] = 9

NUM = r"(\(?\s*-?\s*[\d,]*\.?\d+\s*\)?)"
BASIS = r"(Consolidated|Solo|Separate|Standalone|Stand-alone)?\s*"
SPAN = r"([A-Za-z]+)(?:[,\s]+(\d{4}))?\s*(?:-|to)\s*([A-Za-z]+)[,\s]+(\d{4})"
DATE = r"([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}[\s.\-/][A-Za-z]+[\s.\-/,]+\d{4}|\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4})"


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def _num(s: str) -> float | None:
    s = s.strip()
    neg = s.startswith("(") or "-" in s
    try:
        v = float(re.sub(r"[^\d.]", "", s))
    except ValueError:
        return None
    return -v if neg else v


def _month(name: str) -> int | None:
    return MONTHS.get(name.strip().lower().rstrip("."))


def _month_end(y: int, m: int) -> str:
    return f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"


def parse_date(text: str) -> str | None:
    t = text.strip().rstrip(".,")
    m = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", t)
    if m and _month(m.group(1)):
        return datetime.date(int(m.group(3)), _month(m.group(1)), int(m.group(2))).isoformat()
    m = re.fullmatch(r"(\d{1,2})[\s.\-/]([A-Za-z]+)[\s.\-/,]+(\d{4})", t)
    if m and _month(m.group(2)):
        return datetime.date(int(m.group(3)), _month(m.group(2)), int(m.group(1))).isoformat()
    m = re.fullmatch(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})", t)
    if m:
        return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    return None


def _published(row: dict) -> str | None:
    try:
        return datetime.datetime.strptime(row["date"].strip(), "%d %b %Y").date().isoformat()
    except (KeyError, ValueError):
        return None


def _span(groups) -> tuple[str, int] | None:
    """(period_end, months) from 'July-September 2026' / 'July 2025-March 2026' style spans."""
    m1, y1, m2, y2 = groups
    a, b = _month(m1), _month(m2)
    if not a or not b:
        return None
    y2 = int(y2)
    y1 = int(y1) if y1 else (y2 if a <= b else y2 - 1)
    months = (y2 * 12 + b) - (y1 * 12 + a) + 1
    return _month_end(y2, b), months


def _pick(matches: list[tuple[str, ...]]) -> tuple[str, ...] | None:
    """Prefer consolidated figures, then unlabelled ones, then solo/separate."""
    for pref in ("consolidated", ""):
        for m in matches:
            if (m[0] or "").lower() == pref:
                return m
    return matches[0] if matches else None


def parse_interim(text: str, quarter: int) -> dict | None:
    eps_rx = re.compile(BASIS + r"EPS\s+(?:was|were|is)\s+Tk\.?\s*" + NUM + r"\s+(?:for\s+)?(?:the\s+period\s+(?:of\s+)?)?" + SPAN, re.I)
    discrete = []
    for m in eps_rx.finditer(text):
        sp = _span(m.groups()[2:6])
        if sp and sp[1] == 3:
            discrete.append((m.group(1), _num(m.group(2)), sp[0]))
    pick = _pick(discrete)
    if pick and pick[1] is not None:
        basis, eps, period_end = pick
    else:
        # Only a year-to-date figure was filed: the period is still exact, and for Q1 year-to-date is the quarter.
        ytd = []
        for m in eps_rx.finditer(text):
            sp = _span(m.groups()[2:6])
            if sp and sp[1] == 3 * quarter:
                ytd.append((m.group(1), _num(m.group(2)), sp[0]))
        if not ytd:
            # The filing's own period is the latest date it names; earlier ones are comparatives.
            dates = [parse_date(m.group(1)) for m in re.finditer(r"(?:period\s+ended|as\s+on)\s+" + DATE, text, re.I)]
            d = max((x for x in dates if x), default=None)
            first = re.search(BASIS + r"EPS\s+(?:was|were|is)\s+Tk\.?\s*" + NUM, text, re.I)
            if not d or not first:
                return None
            ytd = [(first.group(1), _num(first.group(2)), _month_end(int(d[:4]), int(d[5:7])))]
        basis, eps, period_end = _pick(ytd)
        if quarter != 1:
            eps = None
    nav = None
    nav_rx = re.compile(BASIS + r"NAV(?:PS|\s+per\s+share)?(?:\s*\([^)]*\))?\s+(?:was|were|is)\s+Tk\.?\s*" + NUM
                        + r"\s+as\s+(?:on|at)\s+" + DATE, re.I)
    navs = [(m.group(1), _num(m.group(2))) for m in nav_rx.finditer(text) if parse_date(m.group(3)) and
            parse_date(m.group(3))[:7] == period_end[:7]]
    nav_pick = _pick([n for n in navs if (n[0] or "").lower() == (basis or "").lower()] or navs)
    if nav_pick:
        nav = nav_pick[1]
    nocfps = None
    noc_rx = re.compile(BASIS + r"NOCFPS\s+(?:was|were|is)\s+Tk\.?\s*" + NUM + r"\s+for\s+" + SPAN, re.I)
    nocs = [(m.group(1), _num(m.group(2))) for m in noc_rx.finditer(text)
            if (_span(m.groups()[2:6]) or ("", 0))[0] == period_end]
    noc_pick = _pick([n for n in nocs if (n[0] or "").lower() == (basis or "").lower()] or nocs)
    if noc_pick:
        nocfps = noc_pick[1]
    return {"kind": "interim", "quarter": quarter, "period_end": period_end, "eps": eps, "nav": nav,
            "nocfps": nocfps, "basis": (basis or "reported").lower()}


def parse_annual(text: str) -> dict | None:
    m = re.search(r"reported\s+(.*?)\s+for\s+the\s+(?:year|period)\s+ended\s+(?:on\s+)?" + DATE, text, re.I | re.S)
    if not m:
        return None
    period = parse_date(m.group(2))
    if not period:
        return None
    seg = m.group(1)
    out = {"kind": "annual", "quarter": 4, "period_end": _month_end(int(period[:4]), int(period[5:7]))}
    found = False
    for key, rx in (("eps", r"EPS"), ("nav", r"NAV(?:PS|\s+per\s+share)?"), ("nocfps", r"NOCFPS")):
        vals = [(g.group(1), _num(g.group(2))) for g in
                re.finditer(BASIS + rx + r"\s+of\s+Tk\.?\s*" + NUM, seg, re.I)]
        pick = _pick(vals)
        out[key] = pick[1] if pick else None
        found = found or pick is not None
        if key == "eps":
            out["basis"] = ((pick[0] if pick else None) or "reported").lower()
    return out if found and out["eps"] is not None else None


def group_filings(rows: list[dict]) -> list[dict]:
    """Join an announcement and its '(cont.)' parts: same code, date and summary, in DSE id order."""
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault((r["code"], r["published_date"], r["summary"]), []).append(r)
    out = []
    for (code, pub, summary), parts in groups.items():
        parts.sort(key=lambda r: (bool(re.match(r"\s*\(\s*cont", r.get("body") or "", re.I)),
                                  int(re.sub(r"\D", "", r["id"]) or 0)))
        out.append({"code": code, "published_date": pub, "published_time": min((p.get("published_time") or "") for p in parts),
                    "summary": summary or "", "type": parts[0].get("type") or "",
                    "text": " ".join(p.get("body") or "" for p in parts), "ids": [p["id"] for p in parts]})
    return out


def parse_filing(f: dict) -> dict | None:
    text = f["text"]
    q = re.search(r"\(Q([1-3])\s*(?:Un-?\s*audited|Audited)?\)|\bQ([1-3])\s+Financials", text + " " + f["summary"], re.I)
    if q:
        return parse_interim(text, int(q.group(1) or q.group(2)))
    if re.search(r"for\s+the\s+(?:year|period)\s+ended", text, re.I) and re.search(r"EPS\s+of\s+Tk", text, re.I):
        return parse_annual(text)
    return None


def fetch(params: dict, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            r = requests.get(API, params=params, headers=HEADERS, timeout=60, verify=False)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError):
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    return {}


def store_rows(conn: sqlite3.Connection, rows: list[dict], source_url: str) -> int:
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    n = 0
    for r in rows:
        pub = _published(r)
        code = (r.get("code") or "").strip().upper()
        if not pub or not code or not r.get("id"):
            continue
        body = r.get("body") or ""
        cur = conn.execute("""INSERT OR IGNORE INTO disclosures
            (id, code, type, published_date, published_time, filed_at, summary, body, body_sha256, source_url, fetched_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                           (str(r["id"]), code, r.get("type"), pub, r.get("time"), r.get("filedAt"), r.get("summary"),
                            body, hashlib.sha256(body.encode("utf-8")).hexdigest(), source_url, now))
        n += cur.rowcount
    conn.commit()
    return n


def backfill(conn: sqlite3.Connection, tickers: list[str], start: str, end: str, pause: float = 0.4) -> dict:
    stats = {"tickers": 0, "new_rows": 0, "truncated": [], "failed": []}
    for t in tickers:
        try:
            d = fetch({"code": t, "from": start, "to": end})
        except Exception:
            stats["failed"].append(t)
            continue
        rows = [r for r in d.get("rows", []) if (r.get("code") or "").upper() == t]
        if d.get("truncated") or len(d.get("rows", [])) >= API_ROW_CAP:
            stats["truncated"].append(t)
        stats["new_rows"] += store_rows(conn, rows, f"{API}?code={t}&from={start}&to={end}")
        stats["tickers"] += 1
        time.sleep(pause)
    return stats


def daily(conn: sqlite3.Connection, days: int = 10) -> dict:
    """Pull every announcement of the last `days` calendar days, one day per request, splitting by company if capped."""
    today = datetime.date.today()
    stats = {"days": 0, "new_rows": 0, "split_days": []}
    tickers = None
    for k in range(days, -1, -1):
        d = (today - datetime.timedelta(days=k)).isoformat()
        res = fetch({"from": d, "to": d})
        if res.get("truncated") or len(res.get("rows", [])) >= API_ROW_CAP:
            stats["split_days"].append(d)
            tickers = tickers or [r[0] for r in conn.execute("SELECT ticker FROM companies ORDER BY ticker")]
            stats["new_rows"] += backfill(conn, tickers, d, d, pause=0.2)["new_rows"]
        else:
            stats["new_rows"] += store_rows(conn, res.get("rows", []), f"{API}?from={d}&to={d}")
        stats["days"] += 1
    return stats


def parse_all(conn: sqlite3.Connection) -> dict:
    rows = [dict(zip(("id", "code", "type", "published_date", "published_time", "summary", "body"), r)) for r in
            conn.execute("SELECT id, code, type, published_date, published_time, summary, body FROM disclosures")]
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    stats = {"filings": 0, "parsed": 0}
    conn.execute("DELETE FROM disclosure_financials")
    for f in group_filings(rows):
        if not re.search(r"EPS", f["text"]):
            continue
        stats["filings"] += 1
        p = parse_filing(f)
        if not p or p["period_end"] > f["published_date"]:
            continue
        conn.execute("""INSERT OR REPLACE INTO disclosure_financials
            (code, period_end, kind, quarter, published_date, published_time, eps, nav, nocfps, basis, disclosure_ids, parsed_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (f["code"], p["period_end"], p["kind"], p["quarter"], f["published_date"], f["published_time"],
                      p["eps"], p["nav"], p["nocfps"], p["basis"], json.dumps(f["ids"]), now))
        stats["parsed"] += 1
    conn.commit()
    return stats


CORRECTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS pit_corrections (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker         TEXT NOT NULL,
    snapshot_date  TEXT NOT NULL,
    field          TEXT NOT NULL,
    old_value      TEXT,
    new_value      TEXT,
    source         TEXT NOT NULL,
    evidence       TEXT,
    corrected_at   TEXT NOT NULL
);
"""
OFFICIAL_SOURCE = "dse_disclosure"
VALUE_FIELDS = (("eps", "eps"), ("nav", "nav"), ("nocfps", "cash_flow_ops"))


def annual_value(f: dict, key: str):
    """cash_flow_ops holds annual NOCFPS; interim filings report it year-to-date, so it stays in disclosure_financials."""
    return None if key == "nocfps" and f["kind"] != "annual" else f[key]


def _next_session_after(conn: sqlite3.Connection, iso: str) -> str | None:
    row = conn.execute("SELECT MIN(date) FROM trading_calendar WHERE date > ? AND is_trading_day = 1", (iso,)).fetchone()
    return row[0] if row else None


def first_filings(conn: sqlite3.Connection) -> list[dict]:
    """Earliest publication of each (company, period): the date and values the market first saw."""
    cols = ("code", "period_end", "kind", "quarter", "published_date", "published_time", "eps", "nav", "nocfps", "disclosure_ids")
    rows = conn.execute(f"""
        SELECT {', '.join('f.' + c for c in cols)} FROM disclosure_financials f
        JOIN companies c ON c.ticker = f.code
        ORDER BY f.code, f.period_end, f.published_date, f.kind = 'interim'""").fetchall()
    first = {}
    for r in rows:
        first.setdefault((r[0], r[1]), dict(zip(cols, r)))
    return list(first.values())


def reconcile_pit(conn: sqlite3.Connection, apply: bool = False) -> dict:
    """
    Make fundamentals_pit agree with the official filings: observed publication dates, filed values,
    fiscal labels, the company's fiscal year end, and rows for filed periods that were missing.
    Every changed value is written to pit_corrections.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from processor import fiscal_year_of  # noqa: E402
    conn.executescript(CORRECTIONS_SCHEMA)
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    filings = first_filings(conn)
    stats = {"filings": len(filings), "dated": 0, "inserted": 0, "value_corrections": 0, "value_fills": 0,
             "fye_corrections": [], "no_session": 0}
    log = []

    fye_from_annual = {}
    for f in filings:
        if f["kind"] == "annual":
            fye_from_annual[f["code"]] = int(f["period_end"][5:7])
    for code, m in fye_from_annual.items():
        cur = conn.execute("SELECT fiscal_year_end_month FROM companies WHERE ticker = ?", (code,)).fetchone()
        if cur and cur[0] != m:
            stats["fye_corrections"].append((code, cur[0], m))
            log.append((code, "", "companies.fiscal_year_end_month", cur[0], m, "annual filing period end"))
            if apply:
                conn.execute("UPDATE companies SET fiscal_year_end_month = ? WHERE ticker = ?", (m, code))

    for f in filings:
        code, pend = f["code"], f["period_end"]
        fye = fye_from_annual.get(code) or (conn.execute(
            "SELECT fiscal_year_end_month FROM companies WHERE ticker = ?", (code,)).fetchone() or [None])[0] or 6
        pub = f["published_date"]
        trad = _next_session_after(conn, pub)
        if not trad:
            stats["no_session"] += 1
            continue
        evidence = f"DSE ids {f['disclosure_ids']} published {pub} {f['published_time'] or ''}".strip()
        filing_type = "annual" if f["kind"] == "annual" else "interim"
        fy = fiscal_year_of(pend, fye)
        row = conn.execute("""SELECT id, publication_date, publication_source, eps, nav, cash_flow_ops
                              FROM fundamentals_pit WHERE ticker = ? AND snapshot_date = ?
                                AND COALESCE(publication_source, '') != 'live_scrape'""", (code, pend)).fetchone()
        if row is None and conn.execute("SELECT 1 FROM fundamentals_pit WHERE ticker = ? AND snapshot_date = ?",
                                        (code, pend)).fetchone():
            stats["live_scrape_collisions"] = stats.get("live_scrape_collisions", 0) + 1
            continue
        if row is None:
            stats["inserted"] += 1
            log.append((code, pend, "row", None, "inserted", evidence))
            if apply:
                conn.execute("""INSERT INTO fundamentals_pit
                    (ticker, snapshot_date, publication_date, tradable_date, filing_type, publication_is_estimated,
                     publication_source, ingest_id, fiscal_year, fiscal_quarter, eps, nav, cash_flow_ops, source_hash, created_at)
                    VALUES (?,?,?,?,?,0,?,?,?,?,?,?,?,?,?)""",
                             (code, pend, pub, trad, filing_type, OFFICIAL_SOURCE, "disc-" + json.loads(f["disclosure_ids"])[0],
                              fy, f["quarter"], f["eps"], f["nav"], annual_value(f, "nocfps"),
                              hashlib.sha256(evidence.encode()).hexdigest()[:16], now))
            continue
        pid, old_pub, old_src = row[0], row[1], row[2]
        stored = {"eps": row[3], "nav": row[4], "cash_flow_ops": row[5]}
        sets = {"publication_date": pub, "tradable_date": trad, "publication_source": OFFICIAL_SOURCE,
                "publication_is_estimated": 0, "filing_type": filing_type, "fiscal_year": fy, "fiscal_quarter": f["quarter"]}
        if (old_pub, old_src) != (pub, OFFICIAL_SOURCE):
            stats["dated"] += 1
            log.append((code, pend, "publication_date", f"{old_pub} ({old_src})", pub, evidence))
        for src_key, col in VALUE_FIELDS:
            new = annual_value(f, src_key)
            if new is None:
                continue
            old = stored[col]
            if old is None:
                stats["value_fills"] += 1
            elif abs(float(old) - new) > 0.005:
                stats["value_corrections"] += 1
            else:
                continue
            sets[col] = new
            log.append((code, pend, col, old, new, evidence))
        if apply:
            conn.execute(f"UPDATE fundamentals_pit SET {', '.join(k + ' = ?' for k in sets)} WHERE id = ?",
                         (*sets.values(), pid))
    backed = {(f["code"], f["period_end"]) for f in filings}
    orphans = [r for r in conn.execute("""SELECT id, ticker, snapshot_date FROM fundamentals_pit
                                          WHERE publication_source = ?""", (OFFICIAL_SOURCE,)) if (r[1], r[2]) not in backed]
    stats["orphans_removed"] = len(orphans)
    for pid, t, s in orphans:
        log.append((t, s, "row", OFFICIAL_SOURCE, "deleted (no backing filing after re-parse)", ""))
        if apply:
            conn.execute("DELETE FROM fundamentals_pit WHERE id = ?", (pid,))
    if apply:
        conn.executemany("""INSERT INTO pit_corrections (ticker, snapshot_date, field, old_value, new_value, source, evidence, corrected_at)
                            VALUES (?,?,?,?,?,?,?,?)""",
                         [(c, s, fld, None if o is None else str(o), None if n is None else str(n), OFFICIAL_SOURCE, ev, now)
                          for c, s, fld, o, n, ev in log])
        conn.commit()
    stats["fye_corrections"] = len(stats["fye_corrections"])
    stats["changes_logged"] = len(log)
    return stats


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    ensure_schema(conn)
    return conn


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backfill")
    b.add_argument("--from", dest="start", default=ARCHIVE_START)
    b.add_argument("--tickers", nargs="*")
    d = sub.add_parser("daily")
    d.add_argument("--days", type=int, default=10)
    sub.add_parser("parse")
    r = sub.add_parser("reconcile")
    r.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    conn = connect()
    if args.cmd == "backfill":
        tickers = [t.upper() for t in args.tickers] if args.tickers else \
            [r[0] for r in conn.execute("SELECT ticker FROM companies ORDER BY ticker")]
        res = backfill(conn, tickers, args.start, datetime.date.today().isoformat())
        print(json.dumps({**res, "parse": parse_all(conn)}, indent=1))
    elif args.cmd == "daily":
        print(json.dumps({**daily(conn, args.days), "parse": parse_all(conn),
                          "reconcile": reconcile_pit(conn, apply=True)}, indent=1))
    elif args.cmd == "reconcile":
        print(json.dumps(reconcile_pit(conn, apply=args.apply), indent=1))
    else:
        print(json.dumps(parse_all(conn), indent=1))
    ok = not (args.cmd == "backfill" and res["failed"])
    conn.close()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
