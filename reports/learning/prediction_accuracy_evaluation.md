# DSE Phase-2 Learning Audit (Net Excess vs EQW)
**Audit Timestamp:** 2026-11-02 09:55:36
**Model:** `frozen_epoch2_pit_v2`
**Label:** `net_excess_vs_eqw_h21_minus_0.833pct`

---
## 1. Performance
- Evaluated closed calls: **146**
- Hit rate (net excess sign): **13.7%** CI [0.0% – 2.6%]
- Mean net excess: **0.0%**
- Round-trip cost charged: **0.833%**
- Horizon: **21** trading bars
- Brier: **0.4075**

## 2. Factor Weights (Beta[2,2] prior @ 50%, floor 0)
| Factor | Weight |
|---|---|
| debt_npl_weight | 0.705 |
| valuation_mos_weight | 0.705 |
| rsi_momentum_weight | 1.094 |
| smart_money_weight | 0.705 |

## 3. Recent Mistakes

- `JAMUNAOIL` 2026-10-06 RISE: None
- `PADMAOIL` 2026-10-06 RISE: None
- `MPETROLEUM` 2026-10-06 RISE: Flat/down drift: Closed at ৳205.0 (-0.1%)
- `GP` 2026-10-06 RISE: None
- `LHB` 2026-10-06 RISE: Flat/down drift: Closed at ৳52.0 (-0.38%)
- `OLYMPIC` 2026-10-06 RISE: Flat/down drift: Closed at ৳141.0 (-0.98%)
- `RELIANCINS` 2026-10-06 RISE: Stopped out: Low ৳88.7 breached stop ৳97.15 (Drawdown -12.35%)
- `SQURPHARMA` 2026-10-06 RISE: None

## 4. Wins
- `RENATA` 2026-10-07: net_excess=None%
- `SQURPHARMA` 2026-10-11: net_excess=None%
- `JAMUNAOIL` 2026-10-11: net_excess=None%
- `RELIANCINS` 2026-10-12: net_excess=None%
- `AAMRANET` 2026-10-12: net_excess=None%
- `MPETROLEUM` 2026-10-13: net_excess=None%

---
Epoch-1 archive: `data/learning/prediction_ledger_epoch1_invalid.json` (do not train).