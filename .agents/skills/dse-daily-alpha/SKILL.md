---
name: dse-daily-alpha
description: >
  Automatically executes background statistical alpha improvements, empirical Bayes weight calibration,
  hash-chained forward ledger tracking, and daily prediction refinement. Triggered whenever user asks
  for daily predictions, stock recommendations, portfolio audits, or types 'alpha', 'alpha update', or 'learn'.
---

# dse-daily-alpha

Continuous empirical learning and statistical alpha refinement engine for DSE.

## Trigger Words
- **`alpha`** or **`alpha update`**
- **`learn`** or **`learn from mistakes`**
- "update alpha", "recalibrate weights", "accuracy"

## Core Principle

Never guess. Never rely on uncalibrated technical indicators or lookahead bias.
Every daily user interaction triggers background synchronization to advance empirical evidence:
1. Ingest daily prices into point-in-time database.
2. Advance V2 Hash-Chained Forward Ledger (`data/portfolio/forward_test_ledger_v2.json`) to track true out-of-sample forward alpha.
3. Log full-universe cross-sectional factor rankings (`data/portfolio/universe_daily_rank_scores.jsonl`).
4. Execute Reinforcement Learning audit (`scripts/reinforcement_learning_engine.py`) to recalibrate indicator weights against actual market outcomes via Empirical Bayes shrinkage.
5. Generate fresh daily rise/fall predictions filtering out debt traps (`D/E > 1.0`).

## Execution Command

Run the master routine:
```powershell
python c:\Users\BS01671\Documents\stock_market\scripts\auto_daily_alpha_routine.py
```

## Background Rules for the Agent

1. **Autonomous Silent Sync on ANY User Interaction**:
   - The user NEVER needs to remember manual schedules or trigger words.
   - On the FIRST interaction of any day (or whenever the user speaks), silently execute:
     `python scripts/check_daily_sync.py`
   - If market close has passed (after 3:30 PM BST, Sun–Thu) and today's session has not been ingested, it will pull closing prices, scrape news, step the forward ledger, and tune weights automatically.
   - If fundamentals data is older than 7 days, it will harvest multi-year & quarterly updates automatically.
   - Do this SILENTLY in the background without complaining or asking permission, then immediately fulfill whatever the user actually asked.
2. When user asks for recommendations or portfolio decisions:
   - Present recommendations strictly grounded in the latest processed database.
   - Follow the 3-option multi-sector comparative rule, timing gate ("Wait vs Buy Now"), and budget stretch buffer (+৳100 to +৳500).
3. Always report measured accuracy and Brier calibration score if asked.
4. Keep user constraints active: 100% Halal/Shariah, zero banks, zero high-debt traps, 4-tranche deployment.
