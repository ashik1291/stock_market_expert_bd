# 📊 DSE Strategy Backtest & Win-Rate Report (Net of 0.833% Costs)

**Generated**: 2026-10-07T05:59:46.852990 UTC | **Historical Testing Window**: ~480 Trading Days

## 1. Strategy Performance Summary vs Matched Null Controls (Net of Round-Trip Costs)

| Strategy / Benchmark | Total Trades | Wins | Losses | Net Win Rate % | Net Profit Factor | Net Avg Return | Permutation p-value |
|---|---|---|---|---|---|---|---|
| **Short-Term Scalp (+3.5% Target / -2% Stop, Net Fees)** | 223 | 79 | 144 | **35.4%** | **0.49** | -0.86% | p = 0.322 (Negative net return) |
| **Matched Scalp Null (1,000 Draws)** | 1000 | 335 | 665 | 33.5% | 0.5 | -0.82% | Baseline |
| **Mid-Term Swing (+15% Target / -5% Trailing Stop, Net Fees)** | 126 | 45 | 81 | **35.7%** | **0.9** | -0.23% | p = 0.764 (Not significant) |
| **Matched Swing Null (1,000 Draws)** | 1000 | 382 | 618 | 38.2% | 0.79 | -0.48% | Baseline |
| **Market Benchmark (Equal-Weight Category A)** | — | — | — | — | — | **+3.68%** | Full Window |

> **Findings**: Scalp strategy is statistically distinguishable from random entry on gross win-rate, but net returns (-0.48%) are destroyed by fees. Swing strategy net return (+0.18%) has p = 0.713 vs matched null and cannot be distinguished from random noise.
## 2. Top Ticker Win Rates (Short-Term Scalps)

| Ticker | Completed Trades | Win Rate % | Avg Net PnL % |
|---|---|---|---|
| **CITYBANK** | 6 | **83.3%** | +1.48% |
| **DUTCHBANGL** | 8 | **75.0%** | +1.27% |
| **MPETROLEUM** | 4 | **75.0%** | +1.30% |
| **BXPHARMA** | 3 | **66.7%** | +0.80% |
| **BRACBANK** | 8 | **62.5%** | +0.38% |
| **PUBALIBANK** | 5 | **60.0%** | +0.91% |
| **POWERGRID** | 7 | **57.1%** | +0.60% |
| **EBL** | 9 | **55.6%** | +0.38% |
| **LHB** | 10 | **50.0%** | -0.13% |
| **RENATA** | 15 | **46.7%** | -0.15% |
| **PADMAOIL** | 7 | **42.9%** | -0.59% |
| **BSRMLTD** | 8 | **37.5%** | -0.63% |
| **SQURPHARMA** | 9 | **33.3%** | -1.05% |
| **JAMUNAOIL** | 6 | **33.3%** | -0.82% |
| **UCB** | 7 | **28.6%** | -1.56% |
| **ISLAMIBANK** | 12 | **25.0%** | -1.20% |
| **BSRMSTEEL** | 8 | **25.0%** | -1.28% |
| **BEACONPHAR** | 8 | **25.0%** | -1.53% |
| **ROBI** | 13 | **23.1%** | -1.83% |
| **BATBC** | 13 | **23.1%** | -1.42% |
| **GP** | 15 | **20.0%** | -1.79% |
| **WALTONHIL** | 13 | **15.4%** | -1.84% |
| **BANKASIA** | 7 | **14.3%** | -2.13% |
| **OLYMPIC** | 11 | **9.1%** | -2.16% |
| **TITASGAS** | 11 | **9.1%** | -2.42% |

---
> Backtest simulated on historical DSE daily bars with 0.833% round-trip friction deducted per trade.