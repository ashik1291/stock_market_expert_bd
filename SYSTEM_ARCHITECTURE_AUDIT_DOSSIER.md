# 🛡️ DSE Automated Quantitative Intelligence Engine
## Rigorous System Architecture, Empirical Audit & Epistemic Autopsy Dossier

**Audit Status**: Post-Peer-Review Revision  
**Auditor Score**: **6.5 / 10** (Methodologically disciplined engineering, verified risk heuristics, zero tradable alpha net of friction)  
**System Version**: `v2.3-Epistemic-Truth`  
**Git Baseline Commit**: `3dfc8ce`  
**Forward Registration Timestamp**: `2026-10-11T16:30:00+06:00` (Official Epoch 2 Registration)  
**Primary Mandate**: *Complete epistemic transparency, zero lookahead claims, net-of-cost friction accounting, and rigorous period-based statistics.*

---

## 1. Epistemic Autopsy: Debunked Claims & Leaks Identified

### 1.1 The Complete Backtest Deconstruction
The system has formally discarded three major statistical illusions:

1. **The +576% 14-Year Alpha Illusion**:
   - Cause: Static 2026 fundamental records joined with historical unadjusted 2012–2025 prices.
   - Reality: Under leak-free point-in-time data and 0.833% friction, the factor portfolio underperformed a 1,000-draw random null portfolio ($p = 0.865$).
2. **The "Tradable RSI Alpha" Illusion (Net-of-Cost Test)**:
   - While cross-sectional Rank IC showed a gross statistical tilt ($t = +7.22$ gross), real-world portfolio simulation revealed that a 14-day rebalanced top-decile portfolio has **90.9% cycle turnover**.
   - After applying DSE's 1.033% round-trip friction (0.833% broker/exchange fees + 0.20% slippage), the net annualized return drops to **+1.63%**, underperforming the equal-weighted benchmark by **-15.47% per year ($t = -3.12$)**.
   - **Conclusion**: Single-factor technical anomalies on DSE are completely consumed by transaction friction.
3. **The 14-Year Debt-Gate Validation Leak**:
   - The reported statistic ("reduces crash frequency by 1.16x–1.97x, $p < 0.01$") was audited and found to have used static 2026 `fundamentals.debt_equity` applied retroactively to 2012–2026 prices. 
   - Because the 14-year Mendeley archive contains only daily OHLCV and DSEX prices (no quarterly balance sheet filing dates from 2012–2025), **no valid 14-year point-in-time fundamental backtest exists**.
   - The debt filter ($\text{Debt/Equity} \ge 1.0$) is retained strictly as an unvalidated defensive heuristic, not an empirically proven 14-year alpha driver.

### 1.2 Retracted Claims
- **"66.4% Win Rate" / "+2.23% Net Expectancy"**: Retracted. Contradicted by net-of-cost backtests.
- **"Brier Score 0.2439 (Sharp)"**: Retracted. Base rate is ~0.223; a score of 0.2439 is uninformative.
- **"Beta(12, 8) Dynamic Calibration"**: Retracted. Shrunk toward an arbitrary 60% prior.
- **"Valuation 8.0/10"**: Downgraded to **4.0 / 10**. Sector fair P/E multiples (6.5, 7.5, 10, 12, 14, 15) are hand-crafted heuristic rules of thumb, not empirically validated parameter estimates.

---

## 2. Realistic System Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                        LAYER 1: DATA INGESTION                         │
│  - 14-Year Mendeley Price Archive (2012–2026, OHLCV Only)              │
│  - Modern Point-In-Time Fundamentals (2026 Verified Snapshots Only)    │
│  - Trading Calendar & Fail-Closed Integrity Audits                     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                  LAYER 2: DEFENSIVE RISK HEURISTICS                    │
│  - Unvalidated Solvency Gate: Debt/Equity < 1.0                        │
│  - Unvalidated Bank Asset Quality Gate: NPL < 6.0%                     │
│  - Automated Auditor Footnote & PSI Regulatory Parser                  │
│  - Mandatory Round-Trip Friction: 0.833% fees + 0.20% slippage         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│              LAYER 3: HEURISTIC VALUATION & SCREENING                  │
│  - Graham Defensive Product Ceiling: (P/E) * (P/NAV) <= 22.5           │
│  - Graham Ceiling: sqrt(22.5 * EPS * NAV)                              │
│  - Cash Dividend Flow Requirement: NOCFPS >= DPS                       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│             LAYER 4: STATISTICAL ALPHA REALITY                         │
│  - Factor Net-of-Cost Deflation: High turnover destroys raw IC alpha   │
│  - Multiple Hypothesis Counter: 6 strategy variants logged             │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│               LAYER 5: PROSPECTIVE FORWARD TEST (EPOCH 2)              │
│  - Registered: 2026-10-11T16:30:00 (Epoch 1 marked as Discarded Leak)  │
│  - Benchmark: Equal-Weighted Total Return Universe                     │
│  - SHA-256 Hash Chained Execution Ledger                               │
│  - Independent Period Power Requirement: T = 44 periods (~2.5 years)   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Forward-Testing Epistemic Realism

### 3.1 Statistical Power & Time Horizon Math
- The assumption that "7,900 monthly stock-pairs yields $t > 2.0$ in 60 days" has been discarded. Cross-sectional stock returns on the same day share market shocks and return overlap.
- Independent units of observation are **time periods ($T$)**, not stock-pairs.
- Assuming a true factor $IC \approx 0.03$ and per-period $sd(IC) \approx 0.10$:
  $$T_{\text{required}} = \left(\frac{2.0 \times 0.10}{0.03}\right)^2 \approx 44 \text{ independent periods}$$
  - At a **14-day rebalance horizon**: $44 \times 14 = 616 \text{ trading days} \approx \mathbf{2.5 \text{ years}}$.
  - At a **63-day rebalance horizon**: $44 \times 63 = 2,772 \text{ trading days} \approx \mathbf{11 \text{ years}}$.
- **Conclusion**: Statistically proving out-of-sample alpha cannot be accelerated into weeks. Epoch 2 must run for a minimum of 2.5 years before claiming statistical significance.

### 3.2 Total-Return Benchmark Alignment
- DSEX is a price-only index. Measuring portfolio total return (inclusive of 6%–10% dividend yields) against DSEX introduces mechanical dividend drift.
- Epoch 2 now benchmarks against an **Equal-Weighted Total Return Index** constructed from the active DSE universe with cash dividend reinvestment.

### 3.3 Epoch Registry & Trial Deflation
- **Epoch 0 (2012–2026 Backtest)**: Discarded (Lookahead bias in fundamentals).
- **Epoch 1 (2026-10-07 Forward Ledger)**: Discarded (Retroactive registration, fee mismatch, price index benchmark).
- **Epoch 2 (2026-10-11T16:30:00 Live Freeze)**: Active out-of-sample forward trial.
- **Multiple Hypothesis Testing Count**: **6 strategy variants** tested to date. Any future $t$-stat must be deflated using Bonferroni / Holm-Bonferroni corrections.

---

## 4. Realistic System Scorecard

| Area | Score | Status & Evidence |
|---|---|---|
| **Data Engineering & Audit Architecture** | **7.5 / 10** | Immutable PIT schema, fail-closed DB audits, clean separation of historical OHLCV from modern PIT. |
| **Risk-Gate Evidence** | **4.0 / 10** | Unvalidated on true historical PIT data. Retained as defensive rule of thumb. |
| **Valuation Screener** | **4.0 / 10** | Heuristic multiples (Graham Product $\le 22.5$). No empirical parameter validation. |
| **Statistical Alpha** | **3.5 / 10** | No tradable alpha net of 1.03% friction. High turnover kills raw factor predictive power. |
| **Forward-Test Design** | **6.5 / 10** | Hash-chained execution, next-open fills, total-return benchmark, period-based power math. |
| **Overall System Rating** | **6.5 / 10** | **Rigorous, methodologically sound software with zero confirmed alpha.** |

---

## 5. What the System Is Useful For Today

1. **Capital Preservation**: Eliminating obvious corporate bankruptcies, loan default disasters, and illiquid trap stocks.
2. **Execution Realism**: Preventing users from losing money in day-trading scalps and illiquid limit locks.
3. **Patience & Governance**: Enforcing 5-year multi-pillar accumulation in audited, zero-debt cash generators (e.g. SQURPHARMA, JAMUNAOIL, GP) rather than gambling on speculative momentum pumps.
4. **Paper Forward Testing**: Tracking whether disciplined value accumulation beats the total-return market over a multi-year horizon without risking real capital prematurely.


---

## 6. Institutional Quantitative Audit & Epistemic Verdict (November 2026)

### 6.1 Official Product Identity & Boundary
- **Official Identity**: **"Bangladesh DSE Quantitative Research, Risk Screening, and Portfolio Decision-Support System"**
- **Core Purpose**: Rigorous data collection, corporate governance screening, solvency and debt-trap elimination, transaction friction modeling, and multi-year paper forward validation.
- **Negative Boundary**: The system is **NOT** an autonomous profit generator, an algorithmic trading robot, or a certified financial advisor. In accordance with epistemic rigor, no algorithm can guarantee trading profits on the Dhaka Stock Exchange.

### 6.2 87-Period Purged Walk-Forward Evaluation (Frozen Model Proof)
Under leak-free purged walk-forward cross-validation (87 independent folds, realistic 0.880% round-trip trading friction, next-session open fills, cash dividend accounting, and central bank macro hurdles):
- **Annualized Net Alpha**: **-9.27% p.a.** vs DSE Equal-Weight Total Return
- **Newey-West $t$-Statistic**: **-1.23** (Statistically indistinguishable from null; net negative after costs)
- **95% Confidence Interval**: **[-1.888%, +0.429%]**
- **Maximum Drawdown**: **25.28%**
- **Regime Robustness**: Outperformed in only 1 of 5 macroeconomic regimes
- **Promotion Gate Conformance**: **0 / 6 Gates Passed**
- **Institutional Verdict**: **REJECTED**. The current quantitative value/yield model does not demonstrate statistically verified excess returns over the market baseline after full trading costs. It operates as a defensive capital preservation screener, not an alpha generator.

### 6.3 Phase 0 Remediation: Eradication of False Precision
1. **Zero Cash Flow Fabrication (`scripts/precision_engine.py`)**:
   - Removed fallback heuristic multiplying EPS by 0.85 to invent NOCFPS. Missing cash flow now strictly outputs `UNKNOWN_CASH_FLOW_DATA_DEFICIT` with zero score bonus.
   - Removed arbitrary 5.0x dividend coverage fallback when DPS is zero.
2. **Zero Management Profile Invention (`scripts/management_governance_engine.py`)**:
   - Eradicated default assumptions (20 years experience, Grade A rating, Low Risk) for unvetted companies. Unregistered management returns `UNRATED`, `HIGH_DATA_DEFICIT`, and zero governance bonus.
3. **Zero Fabricated Probabilities (`scripts/analyzer.py`, `scripts/user_proxy_simulation.py`)**:
   - Replaced hand-crafted 15%–75% probability formulas with `heuristic_momentum_bias` (0–100 score).
   - Removed `profit_probability` across user proxies, standardizing on `heuristic_conviction_score`.
   - Mandated $N \ge 30$ sample threshold in `calibrated_probability_engine.py`. Bins below threshold strictly output `INSUFFICIENT_DATA`.

### 6.4 Phase 2 Remediation: Canonical Model Path Unification
- **Single Model Pipeline**: Eliminated the split between `analyzer.py` composite scoring and the frozen registry model (`unified_score.py`).
- **Ineligibility Gating**: When the canonical served model flags a ticker as ineligible (macro hurdle deficit, debt gate, Shariah exclusion, unverified PIT), `analyzer.py` automatically downgrades the signal to `HOLD_INELIGIBLE_DEFICIT`.
- **Recommender Alignment**: `scripts/recommender.py` strictly blocks any ticker marked `HOLD_INELIGIBLE_DEFICIT` from appearing on Buy or Accumulation lists.
- **PIT Data Pipeline**: `scripts/processor.py` (`get_ticker_data`) now queries point-in-time fundamentals (`fundamentals_pit`) with strict tradable and publication date bounds.

### 6.5 Phase 3 Remediation: Clean Forward Ledger Epoch
- **Contamination Quarantine**: Quarantined 283 legacy records (137 historical bootstrap and 146 pre-Phase-2 evaluated records with null returns) into `data/learning/prediction_ledger_legacy_quarantine.json`.
- **Pure Out-of-Sample Ledger**: Maintained 208 active forward predictions recorded between October 15 and November 03, 2026. All are cleanly pending their 21-bar horizon without lookahead leaks or missing outcome zero-padding.
- **Neutral Prior Weights**: Reset factor weights in `data/learning/model_weights.json` to neutral Bayesian priors ($	ext{Beta}[2,2]$ centered at 1.0x).

### 6.6 Phase 5 Remediation: Universal Security Master Coverage
- Expanded `companies` table from 141 records to all **396 instruments** present on DSE.
- Integrated automatic ticker classification in `scripts/processor.py` ensuring every traded asset is mapped to an appropriate sector and instrument class (Equities, Mutual Funds, Bonds).
