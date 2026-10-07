---
name: dse-scraper
description: >
  Scrapes DSE market data: all share prices, historical OHLCV, company fundamentals,
  and news. Writes raw JSON to data/raw/YYYY-MM-DD/. Call before dse-processor.
  Modes: full (prices + fundamentals + history + news) or price (prices only, faster).
---

# dse-scraper

Runs the high-speed DSE data scraper for Bangladesh Stock Exchange using modern Next.js parsing, `bdshare`, and multi-source financial journalism.

## When to use

- Master knowledge refresh workflow → run this first
- Daily price update needed (4:00 PM BDT) → run with mode=price
- Full sector universe refresh → run with mode=full
- Specific ticker analysis → pass ticker symbols directly

## Prerequisites

```powershell
pip install requests beautifulsoup4 lxml pandas bdshare pdfplumber
```

## Usage

### Full universe scrape (all sector tickers)
```powershell
python c:\Users\BS01671\Documents\stock_market\scripts\scraper.py full
```

### Price-only scrape (daily close, under 5 seconds)
```powershell
python c:\Users\BS01671\Documents\stock_market\scripts\scraper.py price
```

### Specific tickers only
```powershell
python c:\Users\BS01671\Documents\stock_market\scripts\scraper.py SQURPHARMA PUBALIBANK GP BATBC
```

## Output Location

```
data/raw/YYYY-MM-DD/
  market_summary.json     ← DSEX, DS30, DSES index values
  all_prices.json         ← All 395 listed share prices today
  fundamentals.json       ← Per-ticker: EPS, P/E, NAV, Market Cap, Free Float, Sponsor %
  historical_prices.json  ← Full daily OHLCV trading bars with timestamp index
  news.json               ← Per-ticker matched news articles
  market_news.json        ← Macro & sector news headlines (TBS, Daily Star, FE, DSE)
```

## Verification & Guardrails

1. Scrapes `https://www.dse.com.bd/company/{TICKER}` via Next.js React Server Components (`self.__next_f.push`).
2. Extracts live 20-field company dictionary.
3. Automatically calls `df.reset_index()` on historical data so dates are preserved.
4. Gathers news once globally, then filters in memory to avoid rate-limiting.
