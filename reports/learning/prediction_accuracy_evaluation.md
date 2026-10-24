# DSE Phase-2 Learning Audit (Net Excess vs EQW)
**Audit Timestamp:** 2026-10-25 01:22:15
**Model:** `frozen_epoch2_pit_v2`
**Label:** `net_excess_vs_eqw_h21_minus_0.833pct`

---
## 1. Performance
- Evaluated closed calls: **146**
- Hit rate (net excess sign): **60.3%** CI [52.2% – 67.9%]
- Mean net excess: **0.0%**
- Round-trip cost charged: **0.833%**
- Horizon: **21** trading bars
- Brier: **0.2292**

## 2. Factor Weights (Beta[2,2] prior @ 50%, floor 0)
| Factor | Weight |
|---|---|
| debt_npl_weight | 0.815 |
| valuation_mos_weight | 0.815 |
| rsi_momentum_weight | 1.094 |
| smart_money_weight | 0.815 |

## 3. Recent Mistakes

- `MPETROLEUM` 2026-10-06 RISE: Flat/down drift: Closed at ৳205.0 (-0.1%)
- `LHB` 2026-10-06 RISE: Flat/down drift: Closed at ৳52.0 (-0.38%)
- `OLYMPIC` 2026-10-06 RISE: Flat/down drift: Closed at ৳141.0 (-0.98%)
- `RELIANCINS` 2026-10-06 RISE: Stopped out: Low ৳88.7 breached stop ৳97.15 (Drawdown -12.35%)
- `AAMRANET` 2026-10-06 RISE: Stopped out: Low ৳17.9 breached stop ৳17.95 (Drawdown -4.28%)
- `WALTONHIL` 2026-10-06 RISE: Flat/down drift: Closed at ৳329.8 (-0.57%)
- `ACIFORMULA` 2026-10-06 FALL: Bearish call failed: Price rallied +7.09% above entry
- `ARAMITCEM` 2026-10-06 FALL: Bearish call failed: Price rallied +7.34% above entry

## 4. Wins
- `JAMUNAOIL` 2026-10-06: net_excess=None%
- `PADMAOIL` 2026-10-06: net_excess=None%
- `GP` 2026-10-06: net_excess=None%
- `SQURPHARMA` 2026-10-06: net_excess=None%
- `GENEXIL` 2026-10-06: net_excess=None%
- `PREMIERCEM` 2026-10-06: net_excess=None%

---
Epoch-1 archive: `data/learning/prediction_ledger_epoch1_invalid.json` (do not train).