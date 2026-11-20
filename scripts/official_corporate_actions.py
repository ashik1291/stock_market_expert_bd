"""
Corporate actions from official DSE announcements (disclosures table, see dse_disclosures.py).

  dividend declarations   cash % and stock % of face value, period, declared record date
  record-date suspensions "trading ... will remain suspended on record date i.e., DD.MM.YYYY" — the
                          exchange's own confirmation of every entitlement date
  BSEC consent/rejection  stock dividends that need consent get their own record date, or none

Cash per share = cash % x face value. BSEC fixed a uniform Tk 10 face value for listed securities
(verified on a sample of company pages), so FACE_VALUE_BDT = 10.

Only announcements in the DSE archive window (Nov 2024 onwards) are covered; older rows are left as they are.
Rows that a portfolio dividend credit already references are never moved or deleted.

Usage: python scripts/official_corporate_actions.py [--apply]
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dse_disclosures import DB_PATH, group_filings, parse_date  # noqa: E402

FACE_VALUE_BDT = 10.0
SOURCE = "dse_disclosure"
DATE_WORDS = (r"(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+\d{4}|[A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"
              r"|\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4}|\d{1,2}-[A-Za-z]{3}-\d{4})")
SUSPENSION_RX = re.compile(r"suspended\s+on\s+record\s+date\s+i\.?\s*e\.?,?\s*" + DATE_WORDS, re.I)
CASH_RX = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*(?:final\s+|interim\s+)?cash|cash\s+dividend\s+(?:of\s+)?(\d+(?:\.\d+)?)\s*%", re.I)
STOCK_RX = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*(?:final\s+|interim\s+)?(?:stock|bonus)|(?:stock|bonus)\s+dividend\s+(?:of\s+)?(\d+(?:\.\d+)?)\s*%", re.I)
RECORD_RX = re.compile(r"record\s+date(?:\s+of\s+the\s+fund)?\s*(?:[:\-]|is|will\s+be|on)\s*" + DATE_WORDS, re.I)
PERIOD_RX = re.compile(r"for\s+the\s+(?:year|period|half[\s\-]year|financial\s+year)\s+end(?:ed|ing)\s+(?:on\s+)?" + DATE_WORDS, re.I)

SCHEMA = """
CREATE TABLE IF NOT EXISTS corporate_action_corrections (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker        TEXT NOT NULL,
    record_date   TEXT,
    action_type   TEXT,
    change        TEXT NOT NULL,
    old_value     TEXT,
    new_value     TEXT,
    evidence      TEXT,
    corrected_at  TEXT NOT NULL
);
"""


def to_date(text: str) -> str | None:
    t = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text.strip().rstrip(".,"))
    t = re.sub(r"\s+", " ", t)
    for fmt in ("%d %B %Y", "%d %B, %Y", "%d %b %Y", "%d %b, %Y", "%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%d-%b-%Y"):
        try:
            return datetime.datetime.strptime(t, fmt).date().isoformat()
        except ValueError:
            pass
    return parse_date(t)


def _pct(rx: re.Pattern, text: str) -> float:
    m = rx.search(text)
    return float(m.group(1) or m.group(2)) if m else 0.0


def parse_declaration(f: dict) -> dict | None:
    head = re.split(r"The Company has also reported|The Fund has reported|as against", f["text"], 1)[0]
    if not re.search(r"recommended|declared|approved", head, re.I):
        return None
    if re.search(r"\bno\s+dividend\b", head, re.I):
        return {"cash_pct": 0.0, "stock_pct": 0.0}
    cash, stock = _pct(CASH_RX, head), _pct(STOCK_RX, head)
    if cash <= 0 and stock <= 0:
        return None
    rec = RECORD_RX.search(f["text"])
    per = PERIOD_RX.search(head)
    return {"cash_pct": cash, "stock_pct": stock, "record_date": to_date(rec.group(1)) if rec else None,
            "period_end": to_date(per.group(1)) if per else None,
            "interim": bool(re.search(r"interim", head + " " + f["summary"], re.I)),
            "public_only": bool(re.search(r"excluding\s+sponsors|other\s+than\s+sponsors|only\s+for\s+general\s+shareholders|"
                                          r"public\s+shareholders\s+only|sponsors?\s+(?:and|&|and/or)\s+directors?[^.]{0,120}"
                                          r"not\s+be\s+entitled", f["text"], re.I))}


def load_announcements(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    rows = [dict(zip(("id", "code", "type", "published_date", "published_time", "summary", "body"), r)) for r in
            conn.execute("SELECT id, code, type, published_date, published_time, summary, body FROM disclosures")]
    by_code: dict[str, list[dict]] = {}
    for f in group_filings(rows):
        by_code.setdefault(f["code"], []).append(f)
    for v in by_code.values():
        v.sort(key=lambda f: f["published_date"])
    return by_code


def official_events(anns: list[dict]) -> list[dict]:
    """Entitlement events (cash / stock) with the record date the exchange confirmed."""
    suspensions = sorted({to_date(m.group(1)) for f in anns
                          if not re.search(r"for\s+(?:EGM|AGM\s+only)", f["text"], re.I)
                          for m in SUSPENSION_RX.finditer(f["text"]) if to_date(m.group(1))})
    events = []
    for f in anns:
        if (not re.search(r"dividend", f["summary"], re.I) or re.search(r"disburse|subsidiar", f["summary"], re.I)
                or re.search(r"declared\s+by\s+a\s+subsidiary|a\s+subsidiary\s+company\s+of", f["text"], re.I)):
            continue
        d = parse_declaration(f)
        if not d or (d["cash_pct"] <= 0 and d["stock_pct"] <= 0):
            continue
        pub = f["published_date"]
        horizon = (datetime.date.fromisoformat(pub) + datetime.timedelta(days=240)).isoformat()
        later = [a for a in anns if pub <= a["published_date"] <= horizon and a is not f]

        def confirm(declared: str | None, after: str) -> tuple[str | None, str]:
            window = [s for s in suspensions if after <= s <= horizon]
            if declared and declared in window:
                return declared, "declared+suspension"
            if declared:
                near = [s for s in window if 0 <= (datetime.date.fromisoformat(s) - datetime.date.fromisoformat(declared)).days <= 10]
                if near:
                    return near[0], "suspension (shifted)"
                return declared, "declared (no suspension notice)"
            return (window[0], "suspension") if window else (None, "unresolved")

        ids = f["ids"]
        if d["cash_pct"] > 0:
            date, how = confirm(d["record_date"], pub)
            events.append({"type": "cash_dividend", "pct": d["cash_pct"], "record_date": date, "how": how,
                           "published": pub, "ids": ids, "period_end": d["period_end"], "public_only": d["public_only"],
                           "interim": d["interim"]})
        if d["stock_pct"] > 0:
            rejected = any(re.search(r"reject", a["text"], re.I) and re.search(r"stock", a["text"], re.I) for a in later)
            if rejected:
                events.append({"type": "bonus_dividend", "pct": d["stock_pct"], "record_date": None, "how": "BSEC rejected",
                               "published": pub, "ids": ids, "period_end": d["period_end"]})
                continue
            consent = [a for a in later if re.search(r"consent|approv", a["text"], re.I) and re.search(r"stock|bonus", a["text"], re.I)
                       and RECORD_RX.search(a["text"])]
            separate = any(re.search(r"separate\s+record\s+date|solely\s+as\s+the\s+record\s+date\s+for\s+the\s+cash|"
                                     r"applicable\s+for\s+entitlement\s+of\s+cash\s+dividend\s+only|not\s+obtained\s+approval|"
                                     r"yet\s+to\s+receive\s+approval|subject\s+to\s+(?:the\s+)?(?:prior\s+)?approval", a["text"], re.I)
                           for a in [f] + later)
            if consent:
                c = consent[0]
                date, how = confirm(to_date(RECORD_RX.search(c["text"]).group(1)), c["published_date"])
                how, ids = "BSEC consent: " + how, ids + c["ids"]
            elif separate:
                date, how = None, "awaiting BSEC consent"
            else:
                date, how = confirm(d["record_date"], pub)
            events.append({"type": "bonus_dividend", "pct": d["stock_pct"], "record_date": date, "how": how,
                           "published": pub, "ids": ids, "period_end": d["period_end"]})
    return events


HISTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS company_dividend_history (
    code         TEXT NOT NULL,
    fiscal_year  INTEGER NOT NULL,
    cash_pct     REAL,
    stock_pct    REAL,
    face_value   REAL,
    source_url   TEXT NOT NULL,
    fetched_at   TEXT NOT NULL,
    PRIMARY KEY (code, fiscal_year)
);
"""


def fetch_dividend_history(conn: sqlite3.Connection, tickers: list[str], pause: float = 0.3) -> dict:
    """Official per-fiscal-year cash/stock dividend % and face value from each DSE company page."""
    import time
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    conn.executescript(HISTORY_SCHEMA)
    stats = {"companies": 0, "years": 0, "failed": [], "face_value_not_10": []}
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    for t in tickers:
        url = f"https://www.dse.com.bd/company/{t}"
        try:
            html = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (academic research client)"}, timeout=60,
                                verify=False).text  # nosec B501
            chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*"((?:\\.|[^"\\])*)"\]\)', html)
            comb = "".join(json.loads('"' + c + '"') for c in chunks)
            hist = json.loads(re.search(r'"dividendHistory":(\[.*?\])', comb).group(1))
            fv = re.search(r'"faceValue":([\d.]+)', comb)
        except Exception:
            stats["failed"].append(t)
            continue
        face = float(fv.group(1)) if fv else None
        if face is not None and face != FACE_VALUE_BDT:
            stats["face_value_not_10"].append((t, face))
        for h in hist:
            conn.execute("""INSERT OR REPLACE INTO company_dividend_history
                            (code, fiscal_year, cash_pct, stock_pct, face_value, source_url, fetched_at) VALUES (?,?,?,?,?,?,?)""",
                         (t, int(h["year"]), float(h.get("cash") or 0), float(h.get("stock") or 0), face, url, now))
            stats["years"] += 1
        stats["companies"] += 1
        conn.commit()
        time.sleep(pause)
    return stats


FULL_ARCHIVE_FROM_YEAR = 2025


def supersede_placeholders(conn: sqlite3.Connection, apply: bool = False) -> dict:
    """
    From the first full calendar year of the disclosure archive, an untagged placeholder ('estimated date' with no
    fiscal year) is superseded by any official row of the same type in the same calendar year. Such placeholders were
    either duplicates of that dividend or carried a later fiscal year's amount (look-ahead).
    """
    conn.executescript(SCHEMA)
    credited = {(r[0], r[1], r[2]) for r in conn.execute(
        "SELECT ticker, record_date, action_type FROM portfolio_dividend_credits")}
    rows = conn.execute(f"""
        SELECT p.id, p.ticker, p.record_date, p.action_type, p.cash_amount, p.notes, MIN(o.record_date)
        FROM corporate_actions p JOIN corporate_actions o
          ON o.ticker = p.ticker AND o.action_type = p.action_type AND substr(o.record_date, 1, 4) = substr(p.record_date, 1, 4)
         AND o.notes LIKE '%{SOURCE}%'
        WHERE lower(p.notes) LIKE '%estimated%' AND p.notes NOT LIKE '%FY%' AND p.notes NOT LIKE '%{SOURCE}%'
          AND CAST(substr(p.record_date, 1, 4) AS INTEGER) >= ?
        GROUP BY p.id""", (FULL_ARCHIVE_FROM_YEAR,)).fetchall()
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    done = [r for r in rows if (r[1], r[2], r[3]) not in credited]
    if apply:
        conn.executemany("DELETE FROM corporate_actions WHERE id = ?", [(r[0],) for r in done])
        conn.executemany("""INSERT INTO corporate_action_corrections
                            (ticker, record_date, action_type, change, old_value, new_value, evidence, corrected_at)
                            VALUES (?,?,?,?,?,?,?,?)""",
                         [(r[1], r[2], r[3], f"deleted (untagged placeholder; official {r[3]} on {r[6]} in the same year)",
                           json.dumps({"cash": r[4], "notes": r[5]}), None, "official row in archive year", now) for r in done])
        conn.commit()
    return {"placeholders_superseded": len(done)}


def _row_fiscal_year(notes: str, record_date: str, fye: int) -> int:
    m = re.search(r"FY\s*(\d{4})", notes or "")
    if m:
        return int(m.group(1))
    d = datetime.date.fromisoformat(record_date) - datetime.timedelta(days=20)
    end_this_year = datetime.date(d.year, fye, 1)
    return d.year if (d.year, d.month) >= (end_this_year.year, end_this_year.month) else d.year - 1


def audit_with_history(conn: sqlite3.Connection, apply: bool = False) -> dict:
    """Check non-official cash dividend rows against the official per-fiscal-year dividend history."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from processor import fiscal_year_end_month  # noqa: E402
    conn.executescript(SCHEMA + HISTORY_SCHEMA)
    hist = {(r[0], r[1]): (r[2], r[3]) for r in conn.execute(
        "SELECT code, fiscal_year, cash_pct, stock_pct FROM company_dividend_history")}
    covered = {c for c, _ in hist}
    years = {y for _, y in hist}
    credited = {(r[0], r[1], r[2]) for r in conn.execute(
        "SELECT ticker, record_date, action_type FROM portfolio_dividend_credits")}
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    stats = {"checked": 0, "consistent": 0, "late_filer_consistent": 0, "amount_corrected": 0,
             "placeholder_deleted_no_dividend": 0, "duplicate_deleted": 0, "conflicts_reported": []}
    log = []
    rows = conn.execute("""SELECT id, ticker, record_date, cash_amount, notes FROM corporate_actions
                           WHERE action_type = 'cash_dividend' AND COALESCE(notes, '') NOT LIKE ?
                           ORDER BY ticker, record_date""", (f"%{SOURCE}%",)).fetchall()
    by_fy: dict[tuple, list] = {}
    for rid, t, rd, cash, notes in rows:
        if t not in covered or (t, rd, "cash_dividend") in credited:
            continue
        estimated = "estimated" in (notes or "").lower()
        if estimated and not re.search(r"FY\s*\d{4}", notes or ""):
            # A placeholder date carries no fiscal year; mapping it to one would be a guess.
            stats["estimated_untagged_left_flagged"] = stats.get("estimated_untagged_left_flagged", 0) + 1
            continue
        fy = _row_fiscal_year(notes, rd, fiscal_year_end_month(conn, t))
        if fy not in years or (t, fy) not in hist:
            continue
        stats["checked"] += 1
        pct = round((cash or 0) / FACE_VALUE_BDT * 100, 4)
        want = hist[(t, fy)][0]
        prev, nxt = hist.get((t, fy - 1), (None,))[0], hist.get((t, fy + 1), (None,))[0]
        by_fy.setdefault((t, fy), []).append((rid, rd, estimated, notes, abs(pct - want) < 1e-6))
        if abs(pct - want) < 1e-6:
            stats["consistent"] += 1
            continue
        if not estimated and prev is not None and abs(pct - prev) < 1e-6:
            stats["late_filer_consistent"] += 1
            continue
        if want == 0 and estimated:
            stats["placeholder_deleted_no_dividend"] += 1
            log.append((t, rd, "cash_dividend", f"deleted (official history: no cash dividend for FY{fy})", notes, None, "dividendHistory"))
            if apply:
                conn.execute("DELETE FROM corporate_actions WHERE id = ?", (rid,))
            by_fy[(t, fy)].pop()
            continue
        if want > 0 and (estimated or (nxt is not None and abs(pct - nxt) < 1e-6)):
            stats["amount_corrected"] += 1
            by_fy[(t, fy)][-1] = (*by_fy[(t, fy)][-1][:4], True)
            new_cash = round(want / 100.0 * FACE_VALUE_BDT, 4)
            log.append((t, rd, "cash_dividend", f"amount set to official FY{fy} {want:g}%", str(cash), str(new_cash), "dividendHistory"))
            if apply:
                conn.execute("UPDATE corporate_actions SET cash_amount = ?, notes = ? WHERE id = ?",
                             (new_cash, f"{(notes or '').strip()} | amount verified against official DSE dividend history FY{fy} ({want:g}%)", rid))
            continue
        stats["conflicts_reported"].append((t, rd, fy, pct, want))
    for (t, fy), lst in by_fy.items():
        if len(lst) < 2:
            continue
        keep = next((r for r in lst if not r[2] and r[4]), None)
        if keep is None:
            continue
        for r in lst:
            if r is keep:
                continue
            stats["duplicate_deleted"] += 1
            log.append((t, r[1], "cash_dividend", f"deleted (duplicate of {keep[1]} for FY{fy})", r[3], None, "dividendHistory"))
            if apply:
                conn.execute("DELETE FROM corporate_actions WHERE id = ?", (r[0],))
    if apply:
        conn.executemany("""INSERT INTO corporate_action_corrections
                            (ticker, record_date, action_type, change, old_value, new_value, evidence, corrected_at)
                            VALUES (?,?,?,?,?,?,?,?)""", [(*row, now) for row in log])
        conn.commit()
    stats["conflicts_count"] = len(stats["conflicts_reported"])
    stats["conflicts_reported"] = stats["conflicts_reported"][:25]
    return stats


RIGHTS_RATIO_RX = re.compile(r"(\d+)\s*:\s*(\d+)\s+Rights?\s+Share", re.I)
RIGHTS_PRICE_RX = re.compile(r"issue\s+price\s+of\s+(?:BDT|Tk\.?)\s*([\d,]+(?:\.\d+)?)", re.I)


def rights_events(conn: sqlite3.Connection, code: str, anns: list[dict]) -> list[dict]:
    """Rights entitlements: record date from the exchange's suspension notice, ratio and latest issue price from the filings."""
    out = []
    for f in anns:
        if not re.search(r"entitlement\s+of\s+rights?\s+share", f["text"], re.I):
            continue
        m = SUSPENSION_RX.search(f["text"])
        rd = to_date(m.group(1)) if m else None
        if not rd or any(e["record_date"] == rd for e in out):
            continue
        terms = [a for a in anns if a["published_date"] <= rd and RIGHTS_RATIO_RX.search(a["text"])
                 and RIGHTS_PRICE_RX.search(a["text"])]
        if not terms:
            out.append({"type": "rights_split", "record_date": None, "how": "terms not found", "published": f["published_date"],
                        "ids": f["ids"]})
            continue
        t = terms[-1]
        n, big_n = (int(x) for x in RIGHTS_RATIO_RX.search(t["text"]).groups())
        price = float(RIGHTS_PRICE_RX.findall(t["text"])[-1].replace(",", ""))
        cum = conn.execute("SELECT close FROM prices WHERE ticker = ? AND date < ? ORDER BY date DESC LIMIT 1", (code, rd)).fetchone()
        if not cum or not cum[0] or price >= cum[0]:
            out.append({"type": "rights_split", "record_date": None, "how": "no cum price or rights not in the money",
                        "published": f["published_date"], "ids": f["ids"]})
            continue
        factor = (big_n * cum[0] + n * price) / ((big_n + n) * cum[0])
        out.append({"type": "rights_split", "record_date": rd, "how": "suspension notice", "published": f["published_date"],
                    "ids": t["ids"] + f["ids"], "ratio": n / big_n, "factor": factor, "pct": 100.0 * n / big_n,
                    "issue_price": price, "cum_close": cum[0], "terms": f"{n}:{big_n} at Tk {price:g}", "period_end": None})
    return out


def reconcile(conn: sqlite3.Connection, apply: bool = False, window_days: int = 120) -> dict:
    conn.executescript(SCHEMA)
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    known = {r[0] for r in conn.execute("SELECT ticker FROM companies")}
    credited = {(r[0], r[1], r[2]) for r in conn.execute(
        "SELECT ticker, record_date, action_type FROM portfolio_dividend_credits")}
    stats = {"events": 0, "confirmed": 0, "unresolved": [], "inserted": 0, "updated": 0, "deleted_duplicates": 0,
             "kept_credited_conflicts": [], "rejected_or_pending": 0}
    log = []
    today = datetime.date.today().isoformat()
    for code, anns in load_announcements(conn).items():
        if code not in known:
            continue
        events = official_events(anns) + rights_events(conn, code, anns)
        latest = {}
        for e in sorted(events, key=lambda e: e["published"]):
            latest[(e["type"], e["record_date"] or f"none-{e['published']}")] = e  # a revision supersedes
        events = list(latest.values())
        official_dates = {t: sorted(e["record_date"] for e in events if e["type"] == t and e["record_date"])
                          for t in ("cash_dividend", "bonus_dividend", "rights_split")}

        def closest(t: str, d: str) -> str | None:
            dd = datetime.date.fromisoformat(d)
            return min(official_dates[t], key=lambda x: abs((datetime.date.fromisoformat(x) - dd).days), default=None)

        for e in events:
            stats["events"] += 1
            if e["record_date"] is None:
                if e["how"] in ("BSEC rejected", "awaiting BSEC consent"):
                    stats["rejected_or_pending"] += 1
                else:
                    stats["unresolved"].append((code, e["type"], e["published"]))
                continue
            if e["record_date"] > today:
                continue
            stats["confirmed"] += 1
            rd, typ, pct = e["record_date"], e["type"], e["pct"]
            if typ == "cash_dividend":
                ratio, cash, factor = 0.0, round(pct / 100.0 * FACE_VALUE_BDT, 4), 1.0
            elif typ == "rights_split":
                ratio, cash, factor = e["ratio"], 0.0, e["factor"]
            else:
                ratio, cash, factor = pct / 100.0, 0.0, 1.0 / (1.0 + pct / 100.0)
            label = (f"rights {e['terms']} (theoretical ex-rights factor from cum close Tk {e['cum_close']:g})"
                     if typ == "rights_split" else f"{pct:g}% {'cash' if typ == 'cash_dividend' else 'stock'} dividend")
            notes = (f"{label}"
                     f"{' (interim)' if e.get('interim') else ''}{' (public shareholders only)' if e.get('public_only') else ''}"
                     f" for period ended {e['period_end'] or 'n/a'}; official DSE record date {rd} [{e['how']}];"
                     f" source {SOURCE} ids {json.dumps(e['ids'])}")
            evidence = json.dumps(e["ids"])
            lo = (datetime.date.fromisoformat(rd) - datetime.timedelta(days=window_days)).isoformat()
            hi = (datetime.date.fromisoformat(rd) + datetime.timedelta(days=window_days)).isoformat()
            near = conn.execute("""SELECT id, record_date, ratio, cash_amount, adjustment_factor, notes FROM corporate_actions
                                   WHERE ticker = ? AND action_type = ? AND record_date BETWEEN ? AND ?""",
                                (code, typ, lo, hi)).fetchall()
            exact = [r for r in near if r[1] == rd]
            others = [r for r in near if r[1] != rd and SOURCE not in (r[5] or "")
                      and r[1] not in official_dates[typ] and closest(typ, r[1]) == rd]
            for r in others:
                if (code, r[1], typ) in credited:
                    stats["kept_credited_conflicts"].append((code, typ, r[1], rd))
                    continue
                stats["deleted_duplicates"] += 1
                log.append((code, r[1], typ, "deleted (superseded by official record date)",
                            json.dumps({"ratio": r[2], "cash": r[3], "factor": r[4], "notes": r[5]}), rd, evidence))
                if apply:
                    conn.execute("DELETE FROM corporate_actions WHERE id = ?", (r[0],))
            if exact:
                r = exact[0]
                same = abs((r[2] or 0) - ratio) < 1e-9 and abs((r[3] or 0) - cash) < 1e-6 and abs((r[4] or 0) - factor) < 1e-9
                if not same or SOURCE not in (r[5] or ""):
                    stats["updated"] += 1
                    log.append((code, rd, typ, "updated to official values",
                                json.dumps({"ratio": r[2], "cash": r[3], "factor": r[4]}),
                                json.dumps({"ratio": ratio, "cash": cash, "factor": factor}), evidence))
                    if apply:
                        conn.execute("""UPDATE corporate_actions SET ratio = ?, cash_amount = ?, adjustment_factor = ?, notes = ?
                                        WHERE id = ?""", (ratio, cash, factor, notes, r[0]))
            else:
                stats["inserted"] += 1
                log.append((code, rd, typ, "inserted", None, json.dumps({"ratio": ratio, "cash": cash, "factor": factor}), evidence))
                if apply:
                    conn.execute("""INSERT INTO corporate_actions (ticker, record_date, action_type, ratio, cash_amount,
                                    adjustment_factor, notes) VALUES (?,?,?,?,?,?,?)""",
                                 (code, rd, typ, ratio, cash, factor, notes))
    if apply:
        conn.executemany("""INSERT INTO corporate_action_corrections
                            (ticker, record_date, action_type, change, old_value, new_value, evidence, corrected_at)
                            VALUES (?,?,?,?,?,?,?,?)""", [(*row, now) for row in log])
        conn.commit()
    stats["unresolved_count"] = len(stats["unresolved"])
    stats["changes_logged"] = len(log)
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--fetch-history", action="store_true", help="refresh official per-year dividend history first")
    args = ap.parse_args()
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    if args.fetch_history:
        print(json.dumps(fetch_dividend_history(conn, [r[0] for r in conn.execute("SELECT ticker FROM companies ORDER BY ticker")])))
    res = reconcile(conn, apply=args.apply)
    res["unresolved"] = res["unresolved"][:30]
    res["history_audit"] = audit_with_history(conn, apply=args.apply)
    res["placeholders"] = supersede_placeholders(conn, apply=args.apply)
    if args.apply:
        from provenance import classify_corporate_action_sources
        classify_corporate_action_sources(conn)
        conn.commit()
    print(json.dumps(res, indent=1))
    conn.close()


if __name__ == "__main__":
    main()
