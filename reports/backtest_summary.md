# 📊 DSE Strategy Backtest & Win-Rate Report (Net of 0.833% Costs)

**Generated**: 2026-10-07T05:05:38.590241 UTC | **Historical Testing Window**: ~480 Trading Days

## 1. Strategy Performance Summary vs Matched Null Controls (Net of Round-Trip Costs)

| Strategy / Benchmark | Total Trades | Wins | Losses | Net Win Rate % | Net Profit Factor | Net Avg Return | Permutation p-value |
|---|---|---|---|---|---|---|---|
| **Short-Term Scalp (+3.5% Target / -2% Stop, Net Fees)** | 207 | 85 | 122 | **41.1%** | **0.67** | -0.48% | p = 0.012 (Negative net return) |
| **Matched Scalp Null (1,000 Draws)** | 1000 | 335 | 665 | 33.5% | 0.5 | -0.82% | Baseline |
| **Mid-Term Swing (+15% Target / -5% Trailing Stop, Net Fees)** | 125 | 47 | 78 | **37.6%** | **1.09** | +0.18% | p = 0.608 (Not significant) |
| **Matched Swing Null (1,000 Draws)** | 1000 | 382 | 618 | 38.2% | 0.79 | -0.48% | Baseline |
| **Market Benchmark (Equal-Weight Category A)** | — | — | — | — | — | **+3.68%** | Full Window |

> **Findings**: Scalp strategy is statistically distinguishable from random entry on gross win-rate, but net returns (-0.48%) are destroyed by fees. Swing strategy net return (+0.18%) has p = 0.713 vs matched null and cannot be distinguished from random noise.
## 2. Top Ticker Win Rates (Short-Term Scalps)

| Ticker | Completed Trades | Win Rate % | Avg Net PnL % |
|---|---|---|---|
| **BXPHARMA** | 3 | **100.0%** | +2.67% |
| **MPETROLEUM** | 4 | **75.0%** | +1.61% |
| **DUTCHBANGL** | 7 | **71.4%** | +1.10% |
| **PUBALIBANK** | 6 | **66.7%** | +1.30% |
| **CITYBANK** | 6 | **66.7%** | +1.25% |
| **BRACBANK** | 7 | **57.1%** | -0.03% |
| **POWERGRID** | 7 | **57.1%** | +0.60% |
| **PADMAOIL** | 7 | **57.1%** | -0.36% |
| **LHB** | 9 | **55.6%** | +0.02% |
| **EBL** | 8 | **50.0%** | +0.42% |
| **BSRMLTD** | 7 | **42.9%** | -0.66% |
| **BEACONPHAR** | 7 | **42.9%** | -0.47% |
| **UCB** | 7 | **42.9%** | -0.35% |
| **JAMUNAOIL** | 5 | **40.0%** | -0.74% |
| **RENATA** | 13 | **38.5%** | -0.40% |
| **SQURPHARMA** | 9 | **33.3%** | -0.78% |
| **WALTONHIL** | 12 | **33.3%** | -1.17% |
| **TITASGAS** | 9 | **33.3%** | -0.85% |
| **GP** | 13 | **30.8%** | -1.02% |
| **ROBI** | 10 | **30.0%** | -0.91% |
| **BATBC** | 18 | **27.8%** | -1.16% |
| **ISLAMIBANK** | 13 | **23.1%** | -1.17% |
| **OLYMPIC** | 9 | **22.2%** | -1.88% |
| **BANKASIA** | 5 | **20.0%** | -1.57% |
| **BSRMSTEEL** | 6 | **16.7%** | -1.65% |

---
> Backtest simulated on historical DSE daily bars with 0.833% round-trip friction deducted per trade.