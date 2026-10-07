---
name: dse-report
description: >
  Reads recommendation reports from reports/ and presents them to the user in a clear,
  formatted way. Also summarizes market conditions and sector performance.
  Use after dse-recommender generates a report.
---

# dse-report

Presents DSE tri-horizon investment and trading reports to the user in clean, actionable format.

## When to use

- User asks "show me the report", "what's the latest plan", "show weekly recommendations", "top 10"
- After `dse-recommender` runs
- User wants to review the 5-sector matrix or charts

## Files to Read

- Sector Best 2 & 12-Factor Buffett Value Report: `c:\Users\BS01671\Documents\stock_market\reports\buffett_sector_best2_report.md`
- Daily Rise vs Fall Predictions: `c:\Users\BS01671\Documents\stock_market\reports\daily\{today}_rise_fall_predictions.md`
- Tri-Horizon Weekly Plan: `c:\Users\BS01671\Documents\stock_market\reports\weekly\{today}.md`
- Monthly Capital Accumulation Ledger: `c:\Users\BS01671\Documents\stock_market\reports\monthly\{YYYY-MM}_asset_plan.md`
- Exact Portfolio Position Plan: `c:\Users\BS01671\Documents\stock_market\data\portfolio\current_position_plan.md`
- 5-Sector Matrix Evaluation: `c:\Users\BS01671\Documents\stock_market\reports\sector_matrix_evaluation.md`
- Strategy Backtest Summary: `c:\Users\BS01671\Documents\stock_market\reports\backtest_summary.md`
- Charts: `c:\Users\BS01671\Documents\stock_market\reports\charts\`

## How to Present to User

1. **Macro Climate & Active Alerts**: Report systemic risk score (-100 to +100) and logistics/policy alerts.
2. **🏆 Sector Best 2 Compounders**: Present the Top 2 verified stocks per sector with Price, Graham Fair Value, Margin of Safety %, P/NAV, and Core Moats from `buffett_sector_best2_report.md`.
3. **Directional Predictions**: Present 🟢 **Stocks Predicted to RISE** (Rise Prob ≥80%) vs 🔴 **Stocks Predicted to FALL** (Severe debt/distribution traps).
4. **⚡ Short-Term Scalp Table**: Lead with exact Entry, Quick Target (+3.5%), Tight Stop (-2.0%), and small lot sizing.
5. **📈 Mid-Term Swing Table**: Present position trades (+15.0% target, -5.0% trailing stop, Risk/Reward ≥3.0x).
6. **🏛️ Long-Term Asset Building Table**: Present defensive moats with P/E < 15, low debt (D/E ≤ 0.8), veteran leadership, and 100%+ real cash dividend coverage.
7. **Precision Audit Highlights**: Display Smart Money Delta, Real Cash Flow (NOCFPS / DPS), and Max Safe Order limits.
8. **⚠️ Risk Blocks**: Highlight excessive debt traps, retail distribution traps, and manipulation flags blocked from buying.
8. **Charts**: Provide clickable file links to relevant price and volume PNG charts.
9. Always append: "Empirically validated on DSE historical data. Not financial advice."
