"""
Synchronizes audited loanStatus (shortTerm, longTerm debt) and dividendHistory
from DSE Next.js SSR into data/processed/dse.db fundamentals table.
"""

import sqlite3
import urllib.request
import re
import json
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dse_debt_sync")


def sync_debt_and_dividends():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    rows = conn.execute("SELECT ticker, raw_data FROM fundamentals").fetchall()
    log.info(f"Syncing audited loan and dividend history for {len(rows)} companies...")

    updated_count = 0
    for ticker, raw_json in rows:
        try:
            req = urllib.request.Request(
                f"https://www.dse.com.bd/company/{ticker}",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            html = urllib.request.urlopen(req, timeout=10).read().decode("utf-8")
            chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*"((?:\\.|[^"\\])*)"\]\)', html)
            combined = ""
            for c in chunks:
                try:
                    combined += bytes(c, "utf-8").decode("unicode_escape", errors="ignore")
                except Exception:
                    combined += c

            # Parse loanStatus
            idx_loan = combined.find('"loanStatus"')
            st_loan, lt_loan = 0.0, 0.0
            if idx_loan != -1:
                loan_chunk = combined[idx_loan:idx_loan+140]
                st_m = re.search(r'"shortTerm"\s*:\s*([\d\.]+)', loan_chunk)
                lt_m = re.search(r'"longTerm"\s*:\s*([\d\.]+)', loan_chunk)
                st_loan = float(st_m.group(1)) if st_m else 0.0
                lt_loan = float(lt_m.group(1)) if lt_m else 0.0

            # Parse dividendHistory
            div_history = []
            div_matches = re.findall(r'\{"year":(\d{4}),"cash":([\d\.]+),"stock":([\d\.]+),"yieldPct":([\d\.]+)', combined)
            for ym, cm, sm, ym_pct in div_matches:
                div_history.append({
                    "year": int(ym),
                    "cash": float(cm),
                    "stock": float(sm),
                    "yield_pct": float(ym_pct)
                })

            raw_dict = json.loads(raw_json) if raw_json else {}
            raw_dict["short_term_loan_mn"] = st_loan
            raw_dict["long_term_loan_mn"] = lt_loan
            raw_dict["total_loan_mn"] = st_loan + lt_loan
            raw_dict["dividend_history"] = div_history

            # Compute empirical D/E
            nav_val = float(raw_dict.get("nav") or raw_dict.get("book_value") or 0.0)
            puc_val = float(raw_dict.get("paid_up_capital") or 0.0)
            de_ratio = None
            if nav_val > 0 and puc_val > 0:
                eq_mn = (puc_val / 10.0 * nav_val) / 1e6
                if eq_mn > 0:
                    raw_dict["equity_mn"] = round(eq_mn, 2)
                    de_ratio = round((st_loan + lt_loan) / eq_mn, 3)
                    raw_dict["debt_equity"] = de_ratio
                    raw_dict["long_term_debt_equity"] = round(lt_loan / eq_mn, 3)

            # Update DB
            conn.execute("""
                UPDATE fundamentals
                SET debt_equity = ?, raw_data = ?
                WHERE ticker = ?
            """, (de_ratio, json.dumps(raw_dict, ensure_ascii=False), ticker))
            updated_count += 1
            log.info(f"Updated {ticker}: D/E={de_ratio}, Divs={len(div_history)}")
        except Exception as e:
            log.warning(f"Failed to sync {ticker}: {e}")

    conn.commit()
    conn.close()
    log.info(f"Successfully synchronized {updated_count} companies with audited debt & dividend records.")


if __name__ == "__main__":
    sync_debt_and_dividends()
