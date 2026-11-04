# 📊 DSE Strategy Backtest & Win-Rate Report (Net of 0.880% Costs)

**Generated**: 2026-11-04T06:12:17.624329 UTC | **Historical Testing Window**: ~480 Trading Days

## 1. Strategy Performance Summary vs Matched Null Controls (Net of Round-Trip Costs)

| Strategy / Benchmark | Total Trades | Wins | Losses | Net Win Rate % | Net Profit Factor | Net Avg Return | Permutation p-value |
|---|---|---|---|---|---|---|---|
| **Short-Term Scalp (+3.5% Target / -2% Stop, Net Fees)** | 1434 | 579 | 855 | **40.4%** | **0.61** | -0.63% | p = 0.0 (Negative net return) |
| **Matched Scalp Null (1,000 Draws)** | 1000 | 336 | 664 | 33.6% | 0.51 | -0.76% | Baseline |
| **Mid-Term Swing (+15% Target / -5% Trailing Stop, Net Fees)** | 799 | 292 | 507 | **36.5%** | **0.62** | -0.89% | p = 0.002 (Not significant) |
| **Matched Swing Null (1,000 Draws)** | 1000 | 313 | 687 | 31.3% | 0.58 | -0.89% | Baseline |
| **Market Benchmark (Equal-Weight Category A)** | — | — | — | — | — | **+49.45%** | Full Window |

> **Findings**: Scalp strategy is statistically distinguishable from random entry on gross win-rate, but net returns (-0.48%) are destroyed by fees. Swing strategy net return (+0.18%) has p = 0.713 vs matched null and cannot be distinguished from random noise.
## 2. Top Ticker Win Rates (Short-Term Scalps)

| Ticker | Completed Trades | Win Rate % | Avg Net PnL % |
|---|---|---|---|
| **BXPHARMA** | 60 | **56.7%** | +0.21% |
| **PUBALIBANK** | 57 | **56.1%** | +0.26% |
| **JAMUNABANK** | 49 | **51.0%** | -0.13% |
| **PRIMEBANK** | 57 | **50.9%** | -0.19% |
| **UTTARABANK** | 65 | **50.8%** | -0.12% |
| **CITYBANK** | 76 | **44.7%** | -0.45% |
| **EBL** | 48 | **43.8%** | -0.35% |
| **DUTCHBANGL** | 50 | **42.0%** | -0.50% |
| **SQURPHARMA** | 43 | **41.9%** | -0.46% |
| **MARICO** | 43 | **41.9%** | -0.40% |
| **BRACBANK** | 55 | **41.8%** | -0.63% |
| **MPETROLEUM** | 53 | **41.5%** | -0.50% |
| **BANKASIA** | 52 | **40.4%** | -0.68% |
| **POWERGRID** | 73 | **39.7%** | -0.71% |
| **RENATA** | 51 | **39.2%** | -0.67% |
| **LHB** | 87 | **39.1%** | -0.74% |
| **BATBC** | 59 | **39.0%** | -0.68% |
| **ISLAMIBANK** | 75 | **37.3%** | -0.63% |
| **OLYMPIC** | 70 | **34.3%** | -1.00% |
| **BSRMLTD** | 56 | **33.9%** | -1.06% |
| **GP** | 76 | **32.9%** | -1.02% |
| **BERGERPBL** | 31 | **32.3%** | -1.03% |
| **ROBI** | 35 | **25.7%** | -1.58% |
| **BSRMSTEEL** | 64 | **25.0%** | -1.40% |
| **WALTONHIL** | 49 | **22.4%** | -1.51% |

---
> Backtest simulated on historical DSE daily bars with 0.880% round-trip friction deducted per trade.