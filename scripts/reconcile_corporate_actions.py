"""
scripts/reconcile_corporate_actions.py — Remove invented corporate-action dates and price plugs.

* Price-affecting actions (bonus / split) that do not come from an official DSE notice or PSI
  are re-dated to the observed ex-date gap (corporate_action_processor.infer_bonus_ex_date),
  or deleted when no unambiguous gap exists.
* Plug rows that only existed to paper over gaps in the price history
  (MUTUAL_FUND_NAV_DISCOVERY, *_resumption, cash_bonus_adjustment) are deleted.
* Cash dividends with estimated dates stay (they do not alter prices) and are labelled.

Run after scripts/repair_price_history.py so gaps are measured on raw exchange bars.

Usage:
  python scripts/reconcile_corporate_actions.py            # dry run
  python scripts/reconcile_corporate_actions.py --apply
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

from db import get_db_connection  # noqa: E402
from corporate_action_processor import infer_bonus_ex_date  # noqa: E402

DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"
PLUG_TYPES = ("MUTUAL_FUND_NAV_DISCOVERY", "trading_resumption", "dividend_resumption", "cash_bonus_adjustment")
PRICE_TYPES = ("bonus_dividend", "split", "rights_split")
OFFICIAL_MARKERS = ("Real DSE Record Date", "Official DSE PSI")


def _is_official(notes: str | None) -> bool:
    return any(m in (notes or "") for m in OFFICIAL_MARKERS)


def _same_year_cash(conn, ticker: str, record_date: str, notes: str | None) -> float:
    """Cash per share declared alongside the bonus (same 'FYxxxx' tag, else same record date)."""
    m = re.search(r"FY(\d{4})", notes or "")
    if m:
        row = conn.execute(
            "SELECT cash_amount FROM corporate_actions WHERE ticker = ? AND action_type = 'cash_dividend' AND notes LIKE ?",
            (ticker, f"%FY{m.group(1)}%"),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT cash_amount FROM corporate_actions WHERE ticker = ? AND action_type = 'cash_dividend' AND record_date = ?",
            (ticker, record_date),
        ).fetchone()
    return float(row[0]) if row and row[0] else 0.0


def reconcile(apply: bool) -> dict:
    conn = get_db_connection(DB_PATH)
    stats = Counter()
    moved, dropped = [], []
    try:
        ph = ",".join("?" * len(PLUG_TYPES))
        plugs = conn.execute(f"SELECT id, ticker, record_date, action_type FROM corporate_actions WHERE action_type IN ({ph})",
                             PLUG_TYPES).fetchall()
        stats["plug_rows_deleted"] = len(plugs)
        if apply:
            conn.execute(f"DELETE FROM corporate_actions WHERE action_type IN ({ph})", PLUG_TYPES)

        ph = ",".join("?" * len(PRICE_TYPES))
        rows = conn.execute(f"""
            SELECT id, ticker, record_date, action_type, adjustment_factor, notes
            FROM corporate_actions WHERE action_type IN ({ph})
        """, PRICE_TYPES).fetchall()
        # Pass 1: decide every row. Official and price-confirmed rows own their (ticker, date, type) key.
        decisions = []
        owners = {}
        for cid, t, rd, at, fac, notes in rows:
            if _is_official(notes):
                stats["official_kept"] += 1
                owners[(t, rd, at)] = cid
                continue
            fy_m = re.search(r"FY(\d{4})", notes or "")
            ex = infer_bonus_ex_date(conn, t, float(fac or 0), rd, cash_per_share=_same_year_cash(conn, t, rd, notes),
                                     fiscal_year=int(fy_m.group(1)) if fy_m else None)
            if ex == rd:
                stats["date_confirmed"] += 1
                owners[(t, rd, at)] = cid
            decisions.append((cid, t, rd, at, fac, notes, ex))

        # Pass 2: unverifiable rows go first, so a verified row can move onto the key they held.
        for cid, t, rd, at, fac, notes, ex in decisions:
            if ex is None:
                stats["unverifiable_deleted"] += 1
                dropped.append((t, rd, at, fac))
                if apply:
                    conn.execute("DELETE FROM corporate_actions WHERE id = ?", (cid,))
        for cid, t, rd, at, fac, notes, ex in decisions:
            if ex is None or ex == rd:
                continue
            key = (t, ex, at)
            if key in owners:
                stats["duplicate_of_existing_deleted"] += 1
                if apply:
                    conn.execute("DELETE FROM corporate_actions WHERE id = ?", (cid,))
                continue
            owners[key] = cid
            stats["redated_to_observed_ex_date"] += 1
            moved.append((t, rd, ex, fac))
            if apply:
                conn.execute(
                    "UPDATE corporate_actions SET record_date = ?, notes = ? WHERE id = ?",
                    (ex, f"{(notes or '').replace(' (Historical estimated)', '')} (ex-date inferred from price gap; was {rd})", cid),
                )

        est = conn.execute("""
            SELECT COUNT(*) FROM corporate_actions WHERE action_type = 'cash_dividend'
              AND notes NOT LIKE '%Real DSE Record Date%' AND notes NOT LIKE '%Official DSE PSI%'
              AND notes NOT LIKE '%estimated date%'
        """).fetchone()[0]
        stats["cash_dividends_labelled_estimated"] = est
        if apply:
            conn.execute("""
                UPDATE corporate_actions SET notes = notes || ' (estimated date)'
                WHERE action_type = 'cash_dividend'
                  AND notes NOT LIKE '%Real DSE Record Date%' AND notes NOT LIKE '%Official DSE PSI%'
                  AND notes NOT LIKE '%estimated date%'
            """)
            conn.commit()
        else:
            conn.rollback()
    finally:
        conn.close()
    return {"applied": apply, **stats, "redated_sample": moved[:15], "deleted_sample": dropped[:15]}


if __name__ == "__main__":
    print(json.dumps(reconcile("--apply" in sys.argv), indent=2, default=str))
