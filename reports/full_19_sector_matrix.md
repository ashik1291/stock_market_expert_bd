# 🏢 Complete 19-Sector Empirical Performance & Confidence Matrix

### 🏢 Sector Performance & Empirical Confidence Matrix (Ranked by System Confidence)

Empirical breakdown dynamically queried across all **396 listed companies** in `data/processed/dse.db`, sorted descending by **System Confidence**.

> 💡 **What Decides System Confidence?**  
> System Confidence (20% to 70%) is determined by 4 objective criteria:  
> 1. **Data Transparency & PIT Coverage**: % of companies with audited statutory point-in-time financial filings.  
> 2. **Macro Hurdle Feasibility**: Ability of sector leaders to beat the 11.60% sovereign T-Bill yield ($P/E \le 6.62$).  
> 3. **Operating Cash-Flow Health**: Real positive cash generation (NOCFPS > 0) vs debt-funded dividends.  
> 4. **Forensic Integrity**: Freedom from syndicate pump-and-dump manipulation (e.g., Insurance heavily penalized at 35%).

| Sector | Co. Count | PIT Coverage | Passing 15.10% Macro Hurdle (P/E $\le 6.62$) | Avg Div Yield | System Confidence | Quantitative Assessment & Structural Realities |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Fuel Power** | 23 | 65.2% | **4 (17.4%)**<br/>`JAMUNAOIL, LINDEBD, MPETROLEUM`, etc. | **4.84%** | **70% (HIGH)** | **Top Risk-Adjusted Sector**. Sovereign marketing monopolies (`JAMUNAOIL`, `PADMAOIL`, `MPETROLEUM`) trade at P/E 3.0–3.4 with 8.5%–10% cash yields and zero debt. *Risk*: Chronic receivables from public agencies. |
| **Cement** | 7 | 100.0% | **1 (14.3%)**<br/>`CONFIDCEM` | **1.77%** | **65% (MODERATE-HIGH)** | Multinationals (`LHB`, `HEIDELBCEM`) trade at rich multiples (P/E 12–58) that fail hurdle requirements. `CONFIDCEM` offers deep cyclical value at low multiple. |
| **Pharmaceuticals** | 34 | 52.9% | **1 (2.9%)**<br/>`ACMELAB` | **2.10%** | **60% (MODERATE)** | **Quality Moats vs Macro Hurdle Conflict**. Blue-chips (`SQURPHARMA` P/E 8.05, `RENATA` P/E 22.9) fail the strict 15.10% macro hurdle simply due to high rates, despite having Bangladesh's highest corporate governance. |
| **Telecom** | 3 | 66.7% | **0 (0.0%)** | **5.56%** | **60% (MODERATE)** | High cash-generating oligopoly (`GP`, `ROBI`). Robust dividend yields (5.56%), but rich valuations keep them in defensive hold zone. |
| **Engineering** | 42 | 38.1% | **3 (7.1%)**<br/>`BSRMLTD, BSRMSTEEL, WMSHIPYARD` | **2.31%** | **58% (MODERATE)** | High sensitivity to imported steel scrap and currency depreciation. Deep value in steel leaders (`BSRMLTD`, `BSRMSTEEL`), while forensic shield successfully filters speculative low-cap junk (`NAVANACNG`, `ANWARGALV`). |
| **Food Beverage** | 21 | 28.6% | **1 (4.8%)**<br/>`BATBC` | **1.85%** | **55% (Bipolar)** | Bipolar: `BATBC` and `OLYMPIC` have world-class cash generation, while distressed debt zombies are filtered out by debt-trap gates. |
| **IT** | 11 | 72.7% | **0 (0.0%)** | **1.77%** | **55% (MODERATE)** | High ROE software and connectivity providers (`GP` vendors, `AAMRANET`), but zero stocks beat the 15.10% hurdle. Evaluated as defensive holds rather than value buys. |
| **Banking** | 36 | 47.2% | **15 (41.7%)**<br/>`BANKASIA, CITYBANK, DHAKABANK`, etc. | **5.24%** | **50% (Gen) / 0% (Halal) (Selective Value (NPL < 6%))** | Highest earnings yield on DSE (P/E 2.8–4.5, yields 5%–13%). 15 of 36 pass 15.10% macro hurdle. *Halal Mode*: Excluded from portfolio. *Regular Mode*: Selective capital deployment strictly limited to pristine banks (NPL < 6.0%, e.g. `CITYBANK`, `UTTARABANK`, `MTB`, `PUBALIBANK`). Distressed/toxic-NPL banks hard-blocked. |
| **Textile** | 58 | 37.9% | **5 (8.6%)**<br/>`ENVOYTEX, KTL, MALEKSPIN`, etc. | **3.46%** | **48% (LOW-MID)** | Severe structural headwinds (gas rationing, export margin compression). Operating cash flows are volatile; system frequently flags yellow liquidity warnings. |
| **Miscellaneous** | 15 | 26.7% | **0 (0.0%)** | **2.01%** | **40% (LOW)** | True diversified conglomerates and industrial leaders (`BEXIMCO`, `BERGERPBL`). |
| **Insurance** | 59 | 30.5% | **1 (1.7%)**<br/>`RELIANCINS` | **3.18%** | **35% (MANIPULATION ZONE)** | **Highest Manipulation Zone in DSE**. Negative operating cash flows, opaque reserves, and syndicate pump activity. The system assigns near-zero capital. |
| **Financial Institutions** | 23 | 17.4% | **0 (0.0%)** | **3.71%** | **35% (DISTRESSED)** | Severe balance-sheet distress across legacy NBFIs. Zero stocks pass hurdle; excluded by Halal Guard. |
| **Ceramic** | 5 | 20.0% | **0 (0.0%)** | **1.19%** | **35% (LOW LIQUIDITY)** | Energy-intensive tile and tableware manufacturing hurt by natural gas supply rationing. |
| **Services RealEstate** | 4 | 25.0% | **0 (0.0%)** | **2.43%** | **35% (LOW LIQUIDITY)** | Small-cap real estate developers and service firms. Low institutional liquidity. |
| **Tannery** | 6 | 16.7% | **0 (0.0%)** | **1.19%** | **30% (LOW LIQUIDITY)** | Export leather manufacturers facing compliance challenges. Low liquidity. |
| **Paper Printing** | 6 | 0.0% | **0 (0.0%)** | **0.00%** | **25% (DATA SPARSE)** | Paper packaging and print converters with thin margins and high debt. |
| **Travel Leisure** | 5 | 0.0% | **0 (0.0%)** | **0.00%** | **25% (DATA SPARSE)** | Hotel and tourism operators with cyclical occupancy. Zero pass hurdle. |
| **Mutual Funds** | 35 | 2.9% | **0 (0.0%)** | **7.32%** | **20% (EXCLUDED)** | Closed-end mutual funds trading at deep discounts to NAV. 100% excluded under Halal Guard. |
| **Jute** | 3 | 0.0% | **0 (0.0%)** | **0.00%** | **20% (UNINVESTABLE)** | Legacy state and private jute mills with distressed balance sheets. |
