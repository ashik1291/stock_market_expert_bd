---
name: dse-processor
description: >
  Processes raw scraped DSE data for a given date: cleans, parses fundamentals,
  and writes to SQLite DB at data/processed/dse.db. Run after dse-scraper.
---

# dse-processor

Cleans raw DSE scraped data and loads it into the normalized SQLite knowledge database (`dse.db`).

## When to use

- After `dse-scraper` completes successfully
- To reprocess a past date's raw data

## Usage

### Process today's data
```powershell
python c:\Users\BS01671\Documents\stock_market\scripts\processor.py
```

### Process a specific date
```powershell
python c:\Users\BS01671\Documents\stock_market\scripts\processor.py 2026-10-05
```

## What it does

1. Reads `data/raw/YYYY-MM-DD/*.json`
2. Key normalization: replaces `/` and spaces with `_` (e.g. `p/e` → `p_e`).
3. Auto-detects fiscal period using authoritative `multiYearFinancials` with strict sanity bounds (`2015 <= year <= current_year + 1`).
4. Enforces deduplication:
   - `UNIQUE(ticker, date)` on prices.
   - `UNIQUE(ticker, date, headline)` on news articles.
   - `UNIQUE(ticker, year, quarter)` on fundamentals.
   - `UNIQUE(ticker, snapshot_date)` on Point-in-Time fundamentals.
5. Ingests cash flow from operations (`cash_flow_ops`) for earnings quality scoring.
6. Ingests 8-year audited multi-year financials (`multiYearFinancials`) and live quarterly EPS (`interimFinancials` Q1, Q2, Q3).
7. Upserts into `data/processed/dse.db` tables:
   - `companies` — ticker, name, sector, category, market cap, sponsor holding %
   - `prices` — ticker, date, open, high, low, close, volume, turnover value
   - `fundamentals` — eps, nav, pe_ratio, debt_equity, dividend_yield, roe, cash_flow_ops, net_profit_cr (multi-year & quarterly)
   - `fundamentals_pit` — immutable Point-in-Time snapshots with SHA-256 source hashes
   - `news` — ticker, date, headline, source, url
   - `market_summary` — DSEX, DS30, DSES, total turnover

## DB Location

```
data/processed/dse.db
```

## Verification

Run quick row count check:
```powershell
python -c "import sqlite3; conn = sqlite3.connect('data/processed/dse.db'); print('Prices:', conn.execute('SELECT COUNT(*) FROM prices').fetchone()[0], '| Companies:', conn.execute('SELECT COUNT(*) FROM companies').fetchone()[0])"
```
