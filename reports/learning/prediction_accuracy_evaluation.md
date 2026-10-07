# 🔬 DSE Empirical Bayes Online Calibration & Expectancy Audit
**Audit Timestamp:** 2026-10-07 11:37:48 | **Calibration Engine:** Empirical Bayes Shrinkage & Expectancy

---
## 1. Statistical Performance, Expectancy & Probability Calibration
- **Evaluated Closed Calls**: **125**
- **Empirical Win Rate**: **66.4%** *(Wilson 95% Confidence Interval: [57.7% – 74.1%])*
- **Brier Calibration Score**: **0.2439** *(Benchmark: 0.25 is uninformative coin toss, <0.20 is sharp)*
- **Average Win**: **+8.3%** | **Average Loss**: **-7.29%**
- **Round-Trip Friction (Brokerage 0.8% + CDBL 0.03%)**: **-0.83%**
- **Net Mathematical Trade Expectancy**: **+2.23% per trade**
- **Successful Calls**: **83** | **Mistakes / Stopped Out**: **42**

### Reliability Calibration Table
| Confidence Bin | Prediction Count | Mean Predicted Prob % | Observed Actual Hit Rate % | Calibration Status |
|---|---|---|---|---|
| **65-80%** | 90 | 70.0% | **71.1%** | ✅ Well-Calibrated |
| **80-100%** | 35 | 85.0% | **54.3%** | ⚠️ Overconfident |

---
## 2. Empirical Bayes Calibrated Indicator Weights (Shrinkage Prior: Beta[12, 8])
Weights shrunk toward conservative prior (60% baseline) to prevent small-sample overfitting:

| Factor / Indicator | Dynamic Weight | Calibration Method | Bounded Range |
|---|---|---|---|
| **Bank Asset Quality & NPL Filter** | **0.94x** | Empirical Bayes Shrinkage | [0.60x – 1.40x] |
| **Valuation & Margin of Safety** | **0.94x** | Empirical Bayes Shrinkage | [0.60x – 1.40x] |
| **Smart Money Delta** | **0.94x** | Empirical Bayes Shrinkage | [0.60x – 1.40x] |
| **Corporate Governance (AAA/AA)** | **1.10x** | Empirical Bayes Shrinkage | [0.60x – 1.40x] |
| **MACD Trend Structure** | **1.00x** | Baseline Baseline | [0.80x – 1.20x] |
| **RSI Momentum Oversold** | **1.09x** | Downweighted on bear false-breaks | [0.50x – 1.00x] |
| **Systemic Macro Bias** | **1.00x** | Macro risk adjustment | [0.80x – 1.20x] |

---
## 3. Mistake Log & Root-Cause Diagnostics (Learning from Errors)

Recent false predictions identified and heuristics integrated into system guardrails:

### ❌ AAMRANET — 2025-12-10 (RISE Call)
- **Predicted**: RISE (85.0%) @ ৳18.0
- **Realized Performance**: Realized Return: **-11.11%** (Max Drawdown: **-12.78%**)
- **Diagnosis / Mistake Reason**: `Stopped out: Low ৳15.7 breached stop ৳17.46 (Drawdown -12.78%)`
- **Corrective Heuristic**: Downweighted isolated technical indicators without smart money confirmation.

### ❌ AAMRANET — 2026-02-15 (RISE Call)
- **Predicted**: RISE (85.0%) @ ৳17.8
- **Realized Performance**: Realized Return: **-8.99%** (Max Drawdown: **-15.73%**)
- **Diagnosis / Mistake Reason**: `Stopped out: Low ৳15.0 breached stop ৳17.27 (Drawdown -15.73%)`
- **Corrective Heuristic**: Downweighted isolated technical indicators without smart money confirmation.

### ❌ AAMRANET — 2026-08-02 (RISE Call)
- **Predicted**: RISE (85.0%) @ ৳21.4
- **Realized Performance**: Realized Return: **-15.42%** (Max Drawdown: **-20.56%**)
- **Diagnosis / Mistake Reason**: `Stopped out: Low ৳17.0 breached stop ৳20.76 (Drawdown -20.56%)`
- **Corrective Heuristic**: Downweighted isolated technical indicators without smart money confirmation.

### ❌ AAMRATECH — 2026-05-10 (FALL Call)
- **Predicted**: FALL (70.0%) @ ৳11.8
- **Realized Performance**: Realized Return: **29.66%** (Max Drawdown: **-0.85%**)
- **Diagnosis / Mistake Reason**: `Bearish call failed: Price rallied +33.9% above entry`
- **Corrective Heuristic**: Downweighted isolated technical indicators without smart money confirmation.

### ❌ ACI — 2025-10-15 (FALL Call)
- **Predicted**: FALL (70.0%) @ ৳167.9
- **Realized Performance**: Realized Return: **4.88%** (Max Drawdown: **-1.67%**)
- **Diagnosis / Mistake Reason**: `Bearish call failed: Price rallied +11.32% above entry`
- **Corrective Heuristic**: Downweighted isolated technical indicators without smart money confirmation.

### ❌ ACI — 2025-12-10 (FALL Call)
- **Predicted**: FALL (70.0%) @ ৳189.5
- **Realized Performance**: Realized Return: **9.13%** (Max Drawdown: **-0.21%**)
- **Diagnosis / Mistake Reason**: `Bearish call failed: Price rallied +13.98% above entry`
- **Corrective Heuristic**: Downweighted isolated technical indicators without smart money confirmation.

### ❌ ACIFORMULA — 2025-12-10 (FALL Call)
- **Predicted**: FALL (70.0%) @ ৳128.8
- **Realized Performance**: Realized Return: **1.63%** (Max Drawdown: **-2.95%**)
- **Diagnosis / Mistake Reason**: `Bearish call failed: Price rallied +7.84% above entry`
- **Corrective Heuristic**: Downweighted isolated technical indicators without smart money confirmation.

### ❌ ACIFORMULA — 2026-05-10 (FALL Call)
- **Predicted**: FALL (70.0%) @ ৳140.1
- **Realized Performance**: Realized Return: **6.42%** (Max Drawdown: **-1.71%**)
- **Diagnosis / Mistake Reason**: `Bearish call failed: Price rallied +6.64% above entry`
- **Corrective Heuristic**: Downweighted isolated technical indicators without smart money confirmation.

---

## 4. Top Successful High-Confidence Calls

- 🟢 **AAMRANET** (2025-10-15): Predicted **RISE** @ ৳19.0 $ightarrow$ Max Gain: **+12.63%** (Target Achieved).
- 🟢 **AAMRANET** (2026-05-10): Predicted **RISE** @ ৳15.9 $ightarrow$ Max Gain: **+27.67%** (Target Achieved).
- 🟢 **AAMRATECH** (2025-10-15): Predicted **FALL** @ ৳12.4 $ightarrow$ Max Gain: **+6.45%** (Target Achieved).
- 🟢 **AAMRATECH** (2025-12-10): Predicted **FALL** @ ৳11.7 $ightarrow$ Max Gain: **+6.84%** (Target Achieved).
- 🟢 **AAMRATECH** (2026-02-15): Predicted **FALL** @ ৳12.5 $ightarrow$ Max Gain: **+27.2%** (Target Achieved).
- 🟢 **AAMRATECH** (2026-08-02): Predicted **FALL** @ ৳21.5 $ightarrow$ Max Gain: **+12.09%** (Target Achieved).