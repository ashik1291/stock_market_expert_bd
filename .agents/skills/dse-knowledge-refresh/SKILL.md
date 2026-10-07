---
name: dse-knowledge-refresh
description: >
  Orchestrates full knowledge base refresh: scraper → processor → annual reports →
  macro sentiment → charts → analyzer → tri-horizon recommender → sector matrix.
  Triggered by agent on demand or on weekly schedule. This is the master refresh workflow.
---

# dse-knowledge-refresh

Master workflow: refreshes the full DSE knowledge base and generates tri-horizon execution plans.

## When to use

- Weekly scheduled refresh (Saturdays before market open)
- Agent receives "refresh knowledge base" or "full refresh" or "expand full universe"
- Before generating master recommendation reports

## Full Refresh Sequence

Run these commands in order:

### Step 1 — Full Market Scrape
```powershell
python c:\Users\BS01671\Documents\stock_market\scripts\scraper.py full
```
Expected: Fetches live prices for all 395 instruments, plus Next.js fundamentals and historical bars across all sectors.

### Step 2 — Database Processing
```powershell
python c:\Users\BS01671\Documents\stock_market\scripts\processor.py
```
Expected: Populates `data/processed/dse.db` with price snapshots, historical bars, fundamentals, and deduplicated news.

### Step 3 — Audited Debt & Multi-Year Dividend Sync
```powershell
python c:\Users\BS01671\Documents\stock_market\scripts\update_debt_and_dividends.py
```
Expected: Extracts live `loanStatus` (`shortTerm`, `longTerm` debt) and 5-year `dividendHistory` directly from DSE Next.js stream. Calculates empirical Debt/Equity ratios to block corporate debt traps in 9%–14% interest rate climate.

### Step 4 — Macro Sentiment & Crisis Filter
```powershell
python c:\Users\BS01671\Documents\stock_market\scripts\macro_sentiment_engine.py
```
Expected: Computes systemic market bias (-100 to +100), filters out irrelevant foreign noise, and sets sector risk adjustments.

### Step 5 — Technical & Fundamental Analysis
```powershell
python c:\Users\BS01671\Documents\stock_market\scripts\analyzer.py all weekly
```
Expected: Generates scored signals, Wilder's RSI, moving averages, support/resistance, debt-burden penalty, downturn resilience tagging, and 6-factor manipulation checks in `data/knowledge/{ticker}/weekly.json`.

### Step 6 — Tri-Horizon Recommender, Monthly Ledger & Visual Charts
```powershell
python c:\Users\BS01671\Documents\stock_market\scripts\recommender.py weekly
```
Expected: Publishes:
- `reports/weekly/{today}.md` (Actionable buy/don't buy/sell rules for scalps, swings, and assets)
- `reports/monthly/{YYYY-MM}_asset_plan.md` (4-Tranche Capital Accumulation Ledger)
- Automatically saves dual-panel Price, Volume, and Market Cap charts in `reports/charts/`.

### Step 7 — 5-Sector Matrix Evaluation
```powershell
python c:\Users\BS01671\Documents\stock_market\scripts\sector_matrix_evaluator.py
```
Expected: Generates 5 core sectors × 10 Category A stocks matrix in `reports/sector_matrix_evaluation.md`.

### Step 8 — Backtest & Win-Rate Verification
```powershell
python c:\Users\BS01671\Documents\stock_market\scripts\backtester.py
```
Expected: Verifies trade expectancy and publishes win rates in `reports/backtest_summary.md`.

### Step 9 — Daily Directional Rise vs Fall Scanner
```powershell
python c:\Users\BS01671\Documents\stock_market\scripts\daily_rise_fall_scanner.py weekly
```
Expected: Audits all 80 Category A stocks across macro news, smart money flows, and debt traps; publishes `reports/daily/{today}_rise_fall_predictions.md` sorting stocks into High-Conviction Rise vs Severe Fall Risk.

### Step 10 — 12-Factor Buffett Value & Sector Best 2 Screener
```powershell
python c:\Users\BS01671\Documents\stock_market\scripts\buffett_value_screener.py
```
Expected: Evaluates all 80 Category A stocks across 12 strict Graham/Buffett criteria (worth/fair value, 20y age + ongoing growth, moat, governance, YoY EPS, reinvestment/reserves, P/NAV sanity, institutional share, bank NPL, contrarian fear trigger, dual engine); extracts the Top 2 best-of-breed compounders per sector to `reports/buffett_sector_best2_report.md` and `.json`.

## Quick Price-Only Refresh (Daily at 4:00 PM BDT)

```powershell
python c:\Users\BS01671\Documents\stock_market\scripts\scraper.py price
python c:\Users\BS01671\Documents\stock_market\scripts\processor.py
python c:\Users\BS01671\Documents\stock_market\scripts\buffett_value_screener.py
python c:\Users\BS01671\Documents\stock_market\scripts\recommender.py weekly
```
