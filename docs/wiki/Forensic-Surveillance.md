# 🛡️ Forensic Surveillance & Anti-Manipulation Engine

Emerging frontier equity markets frequently experience syndicate-driven manipulation, pump-and-dump operations, and artificial liquidity traps.

---

## 🔍 Forensic Anomaly Detection

The `scripts/anti_manipulation_engine.py` module runs statistical surveillance across all listed instruments:

### 1. Volume Anomaly Ratio (VAR)
Tracks sudden, abnormal volume spikes decoupled from regular trading history:

$$
\text{Volume Anomaly Ratio (VAR)} = \frac{\text{Volume}_t}{\frac{1}{20}\sum_{i=1}^{20} \text{Volume}_{t-i}}
$$

### 2. Junk Trap Condition
A stock is flagged as a high-risk speculative trap if volume spikes without fundamental cash flow justification:

$$
\text{Junk Trap Condition} = (\text{VAR} \ge 3.0) \land (\Delta P \ge 0.075) \land (\text{NOCFPS} \le 0)
$$

Where:
* $\Delta P \ge 0.075$: Price jumped $+7.5\%$ or more in a single session.
* $\text{NOCFPS} \le 0$: Net Operating Cash Flow Per Share is negative or zero.

Tickers meeting this condition are immediately blacklisted via `is_ticker_blacklisted(ticker, asof_date)`.

---

## 🚫 Shariah & High-Debt Trap Filtering

Under the Halal Guard (INV-3):
1. **Absolute Sector Exclusions**: Commercial Banking, Insurance, Leasing / Non-Bank Financial Institutions, Alcohol, Tobacco, Gambling, and Conventional Debt Instruments.
2. **Balance Sheet Health**:
   * Debt-to-Equity Ratio $\le 0.80$
   * Cash Flow from Operations $> 0$
   * Interest-bearing debt expense scrutinized against 12%–14% prevailing bank lending rates.
