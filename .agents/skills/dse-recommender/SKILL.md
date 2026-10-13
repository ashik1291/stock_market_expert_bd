---
name: dse-recommender
description: >
  Reads analysis from data/knowledge/, ranks stocks by signal and confidence,
  and generates buy/sell/hold plans for short, mid, and long-term horizons.
  Outputs markdown + JSON reports to reports/{timeframe}/
---

# dse-recommender

Generates ranked tri-horizon investment and trading plans for DSE stocks with anti-manipulation safeguards and automated chart generation.

## When to use

- After `dse-analyzer` completes for the desired timeframe
- User asks for "buy recommendations", "weekly plan", "what should I buy today", "top 10"
- Scheduled daily/weekly report generation

## Usage

### Generate weekly tri-horizon plan
```powershell
python c:\Users\BS01671\Documents\stock_market\scripts\recommender.py weekly
```

### Generate monthly or quarterly plan
```powershell
python c:\Users\BS01671\Documents\stock_market\scripts\recommender.py monthly
python c:\Users\BS01671\Documents\stock_market\scripts\recommender.py quarterly
```

### Evaluate 5 Sectors x 10 Stocks Matrix
```powershell
python c:\Users\BS01671\Documents\stock_market\scripts\sector_matrix_evaluator.py
```

### Run 12-Factor Buffett Value & Sector Best 2 Screener
```powershell
python c:\Users\BS01671\Documents\stock_market\scripts\buffett_value_screener.py
```

## Output Locations

```
reports/
  buffett_sector_best2_report.md ← 12-Factor Buffett Analysis & Best 2 per Sector
  buffett_sector_best2_report.json ← Machine-readable 12-factor score data
  weekly/YYYY-MM-DD.md          ← Tri-horizon execution plan
  weekly/YYYY-MM-DD.json        ← Machine-readable data
  monthly/YYYY-MM_asset_plan.md ← Monthly Capital Accumulation Ledger (4 Tranches)
  sector_matrix_evaluation.md   ← 5 Sectors × 10 Category A stocks matrix
  charts/
    price/{TICKER}_price.png
    volume/{TICKER}_volume.png
    market_cap/top_15_market_cap.png
```

## Report Structure

```markdown
# 📈 DSE Investment & Trading Strategy — YYYY-MM-DD

**Macro Climate**: Bias score (-100 to +100) + Active Logistics & Policy Alerts

## 🏛️ 1. Long-Term Asset Building Plan (Horizon: 1–5+ Years)
- Ticker, Price, P/E (<16), Debt Burden (Audited D/E ≤ 0.8), Proven Dividend (Multi-year cash), Downturn Resilience
- Actionable Decision Playbook:
  - ✅ **When to Buy**: Support dip range, RSI turning up, tranche sizing.
  - ⛔ **When NOT to Buy**: Extended >5% above 20-DMA, rising debt, circuit spikes.
  - 🎯 **When to Sell**: Valuation target (+30%), dividend suspension, or earnings drop.

## 📈 2. Mid-Term Swing Plan (Horizon: 1–6 Months)
- Exact Entry, Target (+15%), Trailing Stop (-5%), P/E, Conf %, Debt Status.
- Explicit When to Buy, When NOT to Buy, and When to Sell directives.

## ⚡ 3. Short-Term Scalp Plan (Small-Margin: 2%–5% Targets)
- Exact Entry Price, Quick Target (+3.5%), Tight Stop (-2.0%), Conf %, RSI bounce.

## 🚫 Excessive Loan / Debt Traps — DO NOT BUY
- Blocked tickers with high debt/equity (>1.2) or heavy long-term borrowing.

## 🛑 Market Greed / Overvalued Traps — DO NOT BUY (Wait for Pullback)
- Blocked tickers where price exceeds Graham intrinsic worth and Greed Index > 70/100.

## ⚠️ Manipulation Risk — DO NOT BUY
- Blocked pump-and-dump tickers with specific red flags.
```

## Risk Guidance per Horizon

| Horizon | Max Position Size | Stop-Loss Style | Profit Target |
|---|---|---|---|
| **Short (Daily/Weekly)** | 5–10% of portfolio | Strict -2.0% hard stop | +2.5% to +5.0% (take profit immediately) |
| **Mid (1–6 Months)** | 10–20% | Trailing stop -5.0% | +12% to +20% |
| **Long (1–5+ Years)** | 15–30% (Tranches) | Structural breach / NAV drop | Wealth accumulation & dividend compounding |

---

## ⚖️ Mandatory Unbiased Multi-Option Comparative Protocol

When making recommendations (portfolio-specific or general):
1. **Never Recommend a Single Stock in Isolation**: Avoid anchoring on one metric (e.g. state-owned deep-value cash cows like `JAMUNAOIL`).
2. **Multi-Sector Cross Comparison**: Always surface and rank at least 3–4 distinct candidates across separate sectors (e.g., Pharma, Industrial/Steel, Cement, Energy, Telecom).
3. **Objective Trade-Off Transparency**:
   - Compare Cheapness (P/E, P/NAV) vs Quality/Compounding (ROE, Private Management, Innovation).
   - Explicitly highlight hidden flaws/vulnerabilities of every candidate (e.g., government margin control, interest rate reliance, cyclical scrap import dependency).
4. **Exact Budget Fit**: Provide whole share counts, total outlay, and remaining cash reserve matched strictly to user budget (e.g., ৳1,000, ৳2,000, ৳50,000).
5. **Timing Gate & Pullback Probability ("Wait vs Buy Now")**:
   - Check technical extension (distance from 20-DMA support, RSI level, weekly market trend).
   - If overextended or risk of short-term dip is high, explicitly tell the user: **"DO NOT BUY TODAY. Wait for next week / wait for dip"**.
   - Quantify pullback probability (% chance) and give the target safe dip price (e.g., "Wait for dip to ৳YYY").
6. **Budget Stretch Buffer (+৳100 to +৳500 Buffer Analysis)**:
   - **Base Allocation**: Provide best whole-share execution strictly within user's exact budget.
   - **Stretch Suggestion**: If adding a small buffer (+৳100, +৳200, or +৳500) unlocks a higher-tier compounder or prevents dead idle cash from buying an extra share, explicitly advise: *"Add +৳XXX to unlock [TICKER] / buy N shares"*.
   - **Zero Buffer Rule**: If the best stock fits cleanly into the budget without dead cash, state: *"Zero budget increase needed."*

