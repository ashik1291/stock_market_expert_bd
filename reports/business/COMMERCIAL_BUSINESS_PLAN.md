# 💼 stock_market_expert_bd — Commercial Business Plan & Institutional Offering

**Document Version**: 1.0.0  
**Effective Date**: November 2026  
**Market Scope**: Bangladesh Capital Markets (Dhaka Stock Exchange - DSE & Chittagong Stock Exchange - CSE)  
**System Engine**: `stock_market_expert_bd` (Autonomous Quantitative Engine & AI Financial Advisory)

---

## 1. Executive Summary

`stock_market_expert_bd` is the first autonomous, institutional-grade quantitative finance and algorithmic portfolio management platform built specifically for the idiosyncratic realities of the Bangladesh equity market.

While conventional retail retail participants and retail brokerages rely on social media rumors, speculative syndicate groups, and lagging subjective analysis, `stock_market_expert_bd` operates with algorithmic rigor:
- **Strict Point-in-Time (PIT) Data Integrity**: Zero lookahead bias across 14+ years of audited financial statements.
- **The Subtractive Edge**: Eliminates the 90% worst stocks on the exchange (unfunded debt traps, negative operating cash flows, promoter share pledge crises, and regulatory probe entities).
- **Macro Economic Risk-Free Dynamic Hurdle**: Automatically recalibrates hurdle rates against the Bangladesh Bank 91-day Treasury Bill cut-off yield (**11.60%**), ensuring capital is never allocated to equities that cannot beat sovereign risk-free return.
- **Forensic Anti-Manipulation Engine**: Detects volume anomaly ratios (VAR $\ge 3.0\times$), retail distribution traps, and syndicate pump patterns before retail capital is trapped.
- **Shariah / Halal Verification**: Integrated multi-tier Halal guard tracking core business purity, debt/equity thresholds ($\le 30\%$), and dividend purification rates.

---

## 2. Market Opportunity & Sizing (TAM / SAM / SOM)

### 2.1 Macro Backdrop (Bangladesh Capital Market)
- **Total Listed Equities & Funds**: ~395 tickers on the Dhaka Stock Exchange.
- **Total Beneficiary Owner (BO) Accounts**: ~2.5 million registered accounts across Bangladesh and Non-Resident Bangladeshi (NRB) diaspora.
- **Active Institutional Asset Managers**: 50+ merchant banks, 35+ asset management companies (AMCs), and hundreds of family offices seeking automated risk surveillance.
- **High-Interest Rate Environment**: With BB policy repo rate at 10.00% and T-Bills yielding 11.60%–12.00%, passive buy-and-hold equity strategies are severely penalized. Only disciplined, cash-flow-backed quantitative stock selection generates positive alpha.

### 2.2 Addressable Market
- **Total Addressable Market (TAM)**: $45M USD / year (All active retail traders, NRBs, domestic financial institutions, and family offices).
- **Serviceable Addressable Market (SAM)**: $12M USD / year (~250,000 active retail accounts trading monthly + 200 family offices and boutique investment houses).
- **Serviceable Obtainable Market (SOM)**: $1.8M USD / year within 24 months (capturing 2% of active retail traders and 30 institutional advisory clients).

---

## 3. Product Offerings & Monetization Model

`stock_market_expert_bd` monetizes through three distinct, scalable revenue streams:

### Stream 1: B2C Premium Advisory & Retail Quant Terminal (SaaS)
- **Tier 1: Free / Freemium Community Tier**:
  - Access to weekly DSE macro climate report, market rise/fall overview, and basic stock search.
- **Tier 2: Pro Quant Trader (BDT 1,500 / month | BDT 15,000 / year)**:
  - Daily Directional Rise/Fall predictions with confidence probabilities.
  - Full Graham Value & 5-Factor Moat screener.
  - Event-Driven Dividend Capture & Seasonality alerts.
  - Circuit Breaker Floor Price warning notifications.
- **Tier 3: Elite Wealth Builder (BDT 4,500 / month | BDT 45,000 / year)**:
  - Personalized dynamic portfolio rebalancing with exact share count execution plans.
  - Real-Time Portfolio Sentinel mark-to-market auditing with automated take-profit (+15% / +30%) and stop-loss directives.
  - Halal / Shariah purification calculator and institutional debt health metrics.

### Stream 2: B2B Institutional Terminal & Quantitative Data Feeds (API & Licensing)
- **Target**: Merchant banks, brokerage houses (TREC holders), mutual fund managers, and family offices.
- **Pricing**: BDT 150,000 – BDT 500,000 / year per organization.
- **Deliverables**:
  - Point-in-Time (PIT) normalized fundamental database (`fundamentals_pit`).
  - Automated Anti-Manipulation & Regulatory Probe API (`is_ticker_blacklisted`).
  - Orderbook Depth, Corwin-Schultz Bid-Ask Spread, and Tranche Execution Slippage algorithms.
  - Daily white-labeled Chief Financial Advisor Executive Dossier.

### Stream 3: High-Net-Worth Individual (HNWI) & Family Office Discretionary Advisory
- **Target**: Portfolios exceeding BDT 5,000,000 (~$40k+ USD).
- **Model**: Fixed annual retainer + 10%–15% performance fee on verified alpha above the 91-day T-Bill risk-free hurdle rate.
- **Value**: Turnkey execution of inverse-volatility risk parity asset allocation, dividend capture rotation, and capital preservation.

---

## 4. Competitive Moat & Unfair Advantages

| Capability | Retail Rumor / Social Media | Conventional Broker Research | `stock_market_expert_bd` |
|---|---|---|---|
| **Data Integrity** | None (Speculation) | Subjective quarterly PDF notes | **Strict Point-in-Time (PIT) SQLite database** |
| **Lookahead Bias** | High | Unchecked | **Zero (Cryptographically validated)** |
| **Syndicate Pump Protection** | Victim to pump-and-dump | Rarely warns clients | **Automated VAR & BSEC probe blacklist** |
| **Macro Hurdle Accounting** | Ignored | Ignored | **Dynamic 11.60% 91d T-Bill hurdle + ERP** |
| **Execution Sizing** | Random lump sums | Generic recommendations | **Orderbook depth participation & tranche limits** |
| **Exit Discipline** | Panic selling at bottom | No explicit sell stops | **Automated Sentinel (+15%/+30% TP, hard stops)** |
| **Halal Screening** | Rough industry guessing | Missing | **AAOIFI compliant + debt purification rate** |

---

## 5. Technology Stack & Operational Cost Structure

- **Core Engine**: Python 3.10+, SQLite3 with WAL mode, Pandas, NumPy, BeautifulSoup4, LXML, Matplotlib.
- **Server Footprint**: Ultra-lightweight. Zero GPU requirement; runs on standard commodity VPS ($15–$30/month) or local developer laptops with full offline self-healing capability (`ready.bat`).
- **Gross Margins**: Estimated **92% - 95%** gross margin on software and advisory subscriptions due to near-zero marginal computational cost.
- **Failover Redundancy**: 4-layer scraper failover (`bdshare` $\rightarrow$ Next.js JSON API $\rightarrow$ legacy HTML table $\rightarrow$ cached raw payload) ensuring 99.9% data continuity regardless of DSE portal maintenance.

---

## 6. Regulatory & Compliance Roadmap (BSEC / DSE)

- **Software / Tooling Classification**: Platform operates primarily as a quantitative decision-support tool and algorithmic analytics engine, exempt from mandatory portfolio management licensing when sold as software.
- **Advisory Compliance**: For managed advisory services, formal registration under Bangladesh Securities and Exchange Commission (Research Analyst) Regulations or partnership with licensed TREC holders / merchant banks.
- **Ethical & Anti-Manipulation Mandate**: Platform actively assists market stability by refusing to issue buy signals on illiquid syndicate targets and alerting users to manipulative distribution patterns.
