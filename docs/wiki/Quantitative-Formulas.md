# 📐 Proven Quantitative Formulas & Mathematical Standards

The platform integrates classical quantitative valuation models adapted specifically for frontier emerging market microstructure.

---

### 1. Benjamin Graham Fair Value & Margin of Safety

To determine whether an equity is undervalued relative to underlying tangible assets and normalized earnings:

$$
\text{Graham Fair Value } (V) = \sqrt{22.5 \times \text{EPS} \times \text{NAV}}
$$

$$
\text{Margin of Safety (MoS)} = \frac{V - P_{\text{live}}}{P_{\text{live}}}
$$

* **Benchmark Requirement**: A stock must present a Margin of Safety $\ge +0.25$ (+25%) to qualify for core capital allocation.

---

### 2. Central Bank Macro Hurdle & Equity Risk Premium (ERP)

In a high-interest-rate environment, equities must compensate investors for equity risk above risk-free government paper:

$$
\text{Earnings Yield } (E/P) = \frac{\text{EPS}}{P_{\text{live}}}
$$

$$
\text{Equity Risk Premium (ERP)} = \text{Earnings Yield} - R_{\text{91d T-Bill}} \ge 0.035
$$

* With the Bangladesh Bank 91-Day Treasury Bill auction yield at **11.60%**, the non-negotiable minimum equity hurdle rate is **15.10%** (+350 bps ERP spread). Any company with an earnings yield lower than this threshold (P/E $> 6.62$) is disqualified.

---

### 3. Frontier Microstructure Realism & Statutory Fees

All backtesting and paper trading engines enforce statutory DSE transaction friction:

$$
\text{Total Buy Cost} = P \times \text{Shares} \times (1 + \text{Fee}_{\text{buy}}), \quad \text{Fee}_{\text{buy}} = 0.00415
$$

$$
\text{Net Sell Proceeds} = P \times \text{Shares} \times (1 - \text{Fee}_{\text{sell}}), \quad \text{Fee}_{\text{sell}} = 0.00465
$$

* **Fee Breakdown**: Brokerage (0.40%), exchange clearing (0.015%), and Government Section 53BBB Advance Income Tax (0.05%).
* **Circuit Lock Guard**: If an instrument locks at its lower circuit limit (-10% or -3%) with zero bids, exits are deferred to prevent illusory backtest liquidity.

---

### 4. Inverse-Volatility Risk Parity Allocation

Position sizes are inversely scaled according to 20-day realized volatility ($\sigma_i$) and weighted by Graham Margin of Safety:

$$
w_i^* = \frac{\frac{1}{\sigma_i} \times \max(0.1, \text{MoS}_i)}{\sum_{j=1}^N \left(\frac{1}{\sigma_j} \times \max(0.1, \text{MoS}_j)\right)}
$$

$$
\text{Defensive Cash Buffer} = \min\left(0.40, \max\left(0.10, \frac{\sigma_{\text{DSEX}}}{0.15} \times 0.20\right)\right)
$$
