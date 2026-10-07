# 📊 DSE Strategy Backtest & Win-Rate Report (Net of 0.833% Costs)

**Generated**: 2026-10-07T06:36:20.574661 UTC | **Historical Testing Window**: ~480 Trading Days

## 1. Strategy Performance Summary vs Matched Null Controls (Net of Round-Trip Costs)

| Strategy / Benchmark | Total Trades | Wins | Losses | Net Win Rate % | Net Profit Factor | Net Avg Return | Permutation p-value |
|---|---|---|---|---|---|---|---|
| **Short-Term Scalp (+3.5% Target / -2% Stop, Net Fees)** | 1507 | 575 | 932 | **38.2%** | **0.58** | -0.70% | p = 0.01 (Negative net return) |
| **Matched Scalp Null (1,000 Draws)** | 1000 | 354 | 646 | 35.4% | 0.57 | -0.66% | Baseline |
| **Mid-Term Swing (+15% Target / -5% Trailing Stop, Net Fees)** | 845 | 313 | 532 | **37.0%** | **0.61** | -0.92% | p = 0.0 (Not significant) |
| **Matched Swing Null (1,000 Draws)** | 1000 | 307 | 693 | 30.7% | 0.62 | -0.82% | Baseline |
| **Market Benchmark (Equal-Weight Category A)** | — | — | — | — | — | **+56.24%** | Full Window |

> **Findings**: Scalp strategy is statistically distinguishable from random entry on gross win-rate, but net returns (-0.48%) are destroyed by fees. Swing strategy net return (+0.18%) has p = 0.713 vs matched null and cannot be distinguished from random noise.
## 2. Top Ticker Win Rates (Short-Term Scalps)

| Ticker | Completed Trades | Win Rate % | Avg Net PnL % |
|---|---|---|---|
| **BXPHARMA** | 60 | **56.7%** | +0.26% |
| **PUBALIBANK** | 57 | **56.1%** | +0.31% |
| **PADMAOIL** | 52 | **46.2%** | -0.25% |
| **CITYBANK** | 76 | **46.1%** | -0.40% |
| **EBL** | 48 | **43.8%** | -0.30% |
| **DUTCHBANGL** | 50 | **42.0%** | -0.45% |
| **SQURPHARMA** | 43 | **41.9%** | -0.41% |
| **BRACBANK** | 55 | **41.8%** | -0.58% |
| **MPETROLEUM** | 53 | **41.5%** | -0.45% |
| **BATBC** | 57 | **40.4%** | -0.55% |
| **BANKASIA** | 52 | **40.4%** | -0.63% |
| **POWERGRID** | 73 | **39.7%** | -0.66% |
| **LHB** | 86 | **39.5%** | -0.67% |
| **RENATA** | 51 | **39.2%** | -0.63% |
| **JAMUNAOIL** | 67 | **38.8%** | -0.56% |
| **ISLAMIBANK** | 74 | **37.8%** | -0.55% |
| **OLYMPIC** | 70 | **34.3%** | -0.95% |
| **GP** | 76 | **34.2%** | -0.97% |
| **BSRMLTD** | 56 | **33.9%** | -1.01% |
| **BEACONPHAR** | 60 | **31.7%** | -1.10% |
| **UCB** | 67 | **29.9%** | -1.15% |
| **ROBI** | 34 | **26.5%** | -1.49% |
| **TITASGAS** | 78 | **25.6%** | -1.43% |
| **BSRMSTEEL** | 64 | **25.0%** | -1.35% |
| **WALTONHIL** | 48 | **22.9%** | -1.43% |

---
> Backtest simulated on historical DSE daily bars with 0.833% round-trip friction deducted per trade.