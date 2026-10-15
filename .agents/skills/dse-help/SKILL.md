---
name: dse-help
description: >
  Displays the quick command menu and available instructions for the DSE Stock Analysis System.
  Trigger when user types 'help', 'commands', 'menu', 'options', 'how to use', or minimal words like
  'refresh', 'audit', 'climate', 'predict', 'best', 'plan', 'alpha', 'check'.
---

# dse-help

Quick cheat-sheet of instructions for the user to trigger DSE analysis workflows.

## When to trigger
- User says "help", "menu", "commands", "what can you do", "options"
- User types minimal trigger words: "refresh", "audit", "climate", "predict", "best", "plan", "alpha", "check [TICKER]"
- User forgets what phrases or commands to give

## Response Template to Display

```markdown
# 📈 DSE System Commands Menu

### ⚡ Minimal 1-Word Fast Triggers
| Command | Action |
| :--- | :--- |
| **`ready`** | Bootstrap dependencies, verify DB integrity, self-heal, and ready system on this machine |
| **`refresh`** | Full end-to-end data pipeline refresh (scraper + processor + footnotes + alpha) |
| **`audit`** | Audit active portfolio holdings, live P&L, cost basis, cash reserve |
| **`climate`** | Market climate, interest rates, inflation, macro systemic risk |
| **`predict`** | Daily directional rise/fall scanner with probability % |
| **`best`** | 12-Factor Buffett value screener for Top 2 compounders per sector |
| **`plan`** | Monthly asset accumulation plan & safe buy ceilings for ৳2,000 budget |
| **`alpha`** | Daily statistical alpha update, forward ledger logging & Bayesian calibration |
| **`check [TICKER]`** | Deep fundamental + technical + debt audit of a single ticker |

Choose what you want to do and type the phrase or word in chat:

### 🏆 1. Master Rankings & Sector Matrix
- **`Best 2 per sector`** or **`Buffett screener`** or **`12 factor check`**
  *(Runs the 12-factor Graham/Buffett value screener across all 80 Category A stocks; outputs the Top 2 best-of-breed compounders per sector)*
- **`Top 10 overall`** or **`Best stocks`**
  *(Displays the master top 10 Category A stocks across all sectors mapped for all 3 purposes)*
- **`Sector matrix`** or **`Show 5 sectors`**
  *(Runs 5 core sectors × 10 Category A stocks matrix with exact Scalp, Swing, and Asset plans)*

### ⚡ 2. Daily Trading & Directional Rise/Fall Predictions
- **`Daily rise and fall`** or **`Predict rise or fall`**
  *(Audits all 80 Category A stocks across macro news, smart money flows, and debt traps; outputs exact Rise vs Fall lists with % probabilities)*
- **`Daily trade signals`** or **`What should I buy today?`**
  *(Runs anti-manipulation checks, outputs quick buy list with Entry, +3.5% Target, -2.0% Stop-loss)*
- **`Daily update`** or **`Update prices`**
  *(Quickly scrapes today's closing prices and volumes into database)*
- **`Check manipulation on [TICKER]`** *(e.g., `Check manipulation on ORION`)*
  *(Immediate fraud check: volume divergence, circuit breaker locks, serial trading, sponsor exits)*

### 📊 3. Visual Charts & Technical Analysis
- **`Analyze chart of [TICKER]`** *(e.g., `Analyze chart of SQURPHARMA`)*
  *(Generates Price chart with Bollinger/MAs/RSI and Volume Profile with spike alerts)*
- **`Show chart [TICKER]`**
  *(Generates and displays direct links to saved PNG charts in `reports/charts/`)*
- **`Compare market cap`**
  *(Displays horizontal comparison chart of top 15 listed DSE companies)*

### 🔬 4. Empirical Backtesting, Learning & Mistake Diagnostics
- **`Learn from mistakes`** or **`Prediction accuracy`** or **`RL audit`**
  *(Compares past daily, weekly, and monthly predictions against real outcomes, displays empirical win-rate, mistake autopsies, and adaptive indicator weights)*
- **`Run backtest`** or **`Check win rates`**
  *(Tests trading strategies over 479 historical days; shows profit factor, win rates, and average holding times)*

### 🧬 5. Pattern DNA, Multi-Interval Cycles & Causal "WHY" Engine
- **`Pattern of [TICKER]`** or **`Why did [TICKER] rise or fall`** *(e.g., `Pattern of SQURPHARMA`, `Why did GP drop`)*
  *(Multi-interval wave analysis [Weekly, Monthly, Quarterly, Half-Yearly, Yearly], historical cycle amplitude & duration, seasonal win-rate months, and historical macro/political causal event attribution)*
- **`Worth vs greed [TICKER]`** *(e.g., `Worth vs greed ACMELAB`)*
  *(Compares Intrinsic Graham/Asset Worth vs Market Greed Index [0–100]; prevents buying euphoric tops and detects depressed fear accumulation)*

### 🌍 5. Macro Sentiment & Crisis Monitor
- **`Macro sentiment`** or **`Market climate`**
  *(Scans Bangladesh economic/financial news and international commodity/war shocks for systemic risk score)*

### 📅 6. Weekly Planning, Monthly Ledger & Long-Term Assets
- **`Weekly buy plan`** or **`Generate weekly plan`**
  *(Generates complete tri-horizon markdown report with actionable scalp, swing, and asset tables)*
- **`Monthly asset plan`** or **`Monthly accumulation ledger`**
  *(Opens 4-tranche capital accumulation ledger with 60% core, 30% swing, 10% cash allocation)*
- **`Check debt on [TICKER]`** *(e.g., `Check debt on SQURPHARMA`)*
  *(Immediate audit of short-term and long-term bank loans, empirical Debt/Equity, and interest rate sensitivity)*
### 💼 7. Personalized Portfolio & Exact Position Sizer
- **`Calculate position plan for [AMOUNT]`** *(e.g., `Calculate position plan for 500000`)*
  *(Calculates exact share counts, tranche 1 costs, and slippage limits for 60% Core, 30% Swings, 10% Cash)*
- **`Record buy [TICKER] [SHARES] [PRICE]`** *(e.g., `Record buy SQURPHARMA 114 217.6`)*
  *(Logs executed purchase, updates cost basis, and tracks cash balance in local ledger)*
- **`Portfolio status`** or **`Show my portfolio`**
  *(Displays active positions, entry cost basis, unrealized P&L, and stop-loss breach proximity)*

### 🔄 8. Full Universe Refresh
- **`Full refresh`** or **`Expand full universe`**
  *(Runs complete multi-step pipeline across all 80+ listed companies in 10 sectors)*

### 💻 9. Master MVP CLI Commands (Terminal Direct)
- `python main.py status` — Complete health dashboard, macro climate & portfolio summary
- `python main.py best2` — Runs 12-factor Graham/Buffett screener for Best 2 per sector
- `python main.py scan` — Runs daily directional Rise vs Fall predictions scanner
- `python main.py refresh` — Runs full automated refresh pipeline end-to-end
- `python main.py portfolio` — Displays live portfolio ledger (Mutual Funds + Stocks)
- `python main.py plan [BDT]` — Generates 4-tranche capital deployment schedule
- `python main.py report` — Displays latest executive investment strategy report
```
