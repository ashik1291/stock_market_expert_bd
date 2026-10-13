"""
Harvest multi-year audited financial history and quarterly interim EPS for all DSE tickers.
Saves raw JSON and updates SQLite fundamentals and fundamentals_pit tables.
"""

import os
import sys
import json
import time
import datetime
import logging
from pathlib import Path

# Adjust path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scripts.scraper import scrape_fundamentals, save_raw, today_str
from scripts.processor import get_db, parse_fundamentals_row, upsert_company, upsert_fundamentals

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("update_all_fundamentals")

def harvest_fundamentals(tickers: list[str] = None):
    names_path = BASE_DIR / "config" / "company_names.json"
    with open(names_path, encoding="utf-8") as f:
        company_names = json.load(f)

    sectors_path = BASE_DIR / "config" / "sectors.json"
    sectors = {}
    if sectors_path.exists():
        with open(sectors_path, encoding="utf-8") as f:
            sectors = json.load(f)

    # Flatten sector map
    ticker_sector = {}
    for sec, t_list in sectors.items():
        for t in t_list:
            ticker_sector[t] = sec

    target_tickers = tickers or list(company_names.keys())
    log.info(f"Starting fundamentals harvest for {len(target_tickers)} tickers...")

    date_str = today_str()
    raw_path = BASE_DIR / "data" / "raw" / date_str / "fundamentals.json"
    existing_raw = {}
    if raw_path.exists():
        try:
            with open(raw_path, encoding="utf-8") as f:
                existing_raw = json.load(f)
        except Exception:
            existing_raw = {}

    conn = get_db()
    success_count = 0

    for i, ticker in enumerate(target_tickers, 1):
        log.info(f"[{i}/{len(target_tickers)}] Scraping {ticker}...")
        try:
            fund = scrape_fundamentals(ticker)
            if fund and len(fund) > 3:
                existing_raw[ticker] = fund
                parsed = parse_fundamentals_row(ticker, fund)
                sec = ticker_sector.get(ticker, fund.get("sector", "Unknown"))
                cat = fund.get("category", "A")
                upsert_company(conn, ticker, sec, cat, parsed)
                upsert_fundamentals(conn, parsed, fund)
                conn.commit()
                success_count += 1
                log.info(f"  -> Ingested {ticker} successfully (Multi-year: {len(fund.get('multi_year_financials', []))} yrs, Interim: {bool(fund.get('interim_financials'))})")
            else:
                log.warning(f"  -> Empty or sparse data for {ticker}")
        except Exception as e:
            log.error(f"  -> Error processing {ticker}: {e}")

        time.sleep(0.3)

    # Save aggregated raw file
    save_raw("fundamentals", existing_raw, date_str)
    conn.close()

    log.info(f"=== Harvest complete: {success_count}/{len(target_tickers)} tickers updated ===")

if __name__ == "__main__":
    cli_tickers = sys.argv[1:] if len(sys.argv) > 1 else None
    harvest_fundamentals(cli_tickers)
