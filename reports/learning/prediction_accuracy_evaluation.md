# DSE Phase-2 Learning Audit (Net Excess vs EQW)
**Audit Timestamp:** 2026-11-08 16:27:34
**Model:** `frozen_epoch2_pit_v2`
**Label:** `net_excess_vs_eqw_h21_minus_0.88pct`

---
## 1. Performance
- Evaluated closed calls: **0**
- Active Pending Forward Predictions: **269**
- Forward Validation Status: **ACCUMULATING_OOS_EVIDENCE**
- Long (RISE) Hit Rate: **INSUFFICIENT_DATA** (0 / 0 profitable long calls)
- Risk Avoidance (FALL) Rate: **INSUFFICIENT_DATA**
- Combined System Accuracy: **INSUFFICIENT_DATA (Pending horizon)** CI INSUFFICIENT_DATA
- Mean net excess: **INSUFFICIENT_DATA**
- Round-trip cost charged: **0.88%**
- Horizon: **21** trading bars
- Brier Calibration Score: **INSUFFICIENT_DATA**

## 2. Factor Weights (Beta[2,2] prior @ 50%, floor 0)
| Factor | Weight |
|---|---|
| debt_npl_weight | 1.0 |
| valuation_mos_weight | 1.0 |
| rsi_momentum_weight | 1.0 |
| smart_money_weight | 1.0 |

## 3. Recent Mistakes

> No evaluated losses yet (ledger fresh after Epoch-1 archive).

## 4. Wins

---
Epoch-1 archive: `data/learning/prediction_ledger_epoch1_invalid.json` (do not train).