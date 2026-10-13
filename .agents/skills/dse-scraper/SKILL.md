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
  fundamentals.json       ← Per-ticker: EPS, P/E, NAV, Market Cap, Free Float, multiYearFinancials (8 yrs), interimFinancials (Q1-Q3)
  historical_prices.json  ← Full daily OHLCV trading bars with timestamp index
  news.json               ← Per-ticker matched news articles
  market_news.json        ← Macro & sector news headlines (TBS, Daily Star, FE, DSE)
```

## Verification & Guardrails

1. Scrapes `https://www.dse.com.bd/company/{TICKER}` via Next.js React Server Components (`self.__next_f.push`).
2. Extracts live 29-field company profile, 8-year audited history (`multiYearFinancials`), and live quarterly interim EPS (`interimFinancials`).
3. Uses `SESSION.trust_env = False` across all HTTP sessions to bypass dead Windows sandbox proxies.
4. Empty-file guard prevents overwriting valid stored data with empty lists on network timeout.
5. Automatically calls `df.reset_index()` on historical data so dates are preserved.
6. Gathers news once globally, then filters in memory to avoid rate-limiting.
