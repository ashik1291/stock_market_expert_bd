# Research Notes — corrected, survivorship-free data (2026-11-20)

All results use the Tier 1/2 data (official DSE filings and corporate actions, archive-verified prices) and the
Tier 3 point-in-time universe. Period: 206 feature dates, 2025-04-30 → 2026-11-19. Re-run the scripts to reproduce.

## 1. Feature-input corrections (`scripts/research_feature_inputs_eval.py`)

v1 = stored scrape P/E and yield, today's category list, bonus-only price adjustment.
v2 = P/E from close and published annual EPS, trailing-year official dividend yield, field-wise PIT D/E, point-in-time
category, all price actions adjusted.

On tickers common to both, eligible sets and selection IC are **identical** at 1, 5 and 21 sessions (the 15.10% macro
hurdle is the binding gate), so the champion's behaviour did not change; its inputs are now correct. The champion was
re-frozen with this evidence (`model_registry.json → freeze_log`).

## 2. Category data bug

`companies.category` listed 375 "A" companies; DSE's official feed lists 161 A, 66 B, 133 Z equities. The scraper
defaulted missing categories to "A", so "Category A" screens admitted Z-category names (e.g. ISLAMIBANK, POWERGRID).
Corrected for 180 companies; categories now follow the exchange feed daily, with history in `category_history`.

## 3. Universe bias in backtests (`scripts/research_universe_bias_eval.py`, institutional backtest from 2023-01-01)

| Universe | Net return | Sharpe | Max DD | Trades | Win rate | Profit factor |
|---|---|---|---|---|---|---|
| Today's large caps, fixed for all history (old) | 36.8% | 1.11 | −12.4% | 32 | 34.4% | 1.04 |
| Point-in-time monthly liquidity universe (new) | 34.9% | 1.87 | −10.1% | 11 | 27.3% | 0.32 |

The survivor list made the trading signals look profitable (PF 1.04); without hindsight they lose (PF 0.32). Return is
mostly dividends, cash yield and holding, not signal skill.

## 4. Factor IC on the point-in-time universe (`scripts/research_factor_ic.py`, Newey-West t)

| Factor | 5-session IC (t) | 21-session IC (t) |
|---|---|---|
| Dividend yield | 0.058 (3.8) | 0.084 (2.9) |
| Earnings yield | 0.056 (2.9) | 0.070 (1.8) |
| Inverse RSI-14 | 0.054 (2.7) | 0.022 (0.6) |
| Inverse D/E | 0.010 (0.5) | 0.036 (1.8) |
| Log traded value (20d) | −0.049 (−3.0) | −0.114 (−3.5) |
| Champion score (selection IC) | 0.011 (1.0) | 0.020 (0.9) |

The individual factors are significant, but the champion's gates leave ~5 eligible names a day and discard most of the
cross-sectional signal. Liquidity is strongly negative (illiquidity premium) — not tradable without cost modelling.

## 5. Challenger registered

`challenger_xsection_rank_v1`: equal-weight percentile ranks of dividend yield, earnings yield and inverse RSI across
the whole point-in-time universe; Shariah-sector, price and debt gates kept; no macro-hurdle gate (~40 names/day).
Backfilled 1-session selection IC (research only, not counted for promotion): 0.0181 vs champion 0.0094 on 204 common
dates. Because it was specified after seeing this data, only its **live** shadow record counts: promotion requires 200
live periods, Holm step-down over all 53 registered trials, and explicit `--approve`.
