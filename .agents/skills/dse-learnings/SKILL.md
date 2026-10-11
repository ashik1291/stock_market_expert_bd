---
name: dse-learnings
description: >
  Repository of operational lessons, verified endpoints, data extraction quirks,
  and anti-manipulation heuristics learned while developing and running the DSE system.
  Consult this skill before modifying scrapers, parsers, or analysis logic.
---

# dse-learnings

Knowledge base of real-world lessons, verified endpoints, and operational guardrails for the Bangladesh Stock Exchange (DSE) automated agent.

---

## 1. Verified DSE Endpoints & Architecture (Updated October 2026)

### Company Profile & Fundamentals
- **Current Canonical URL**: `https://www.dse.com.bd/company/{TICKER}`  
  *(Example: `https://www.dse.com.bd/company/PUBALIBANK`)*
- **Architecture**: Next.js App Router (SSR with React Server Components).
- **Extraction Mechanism**:
  - The page does **NOT** render standard HTML `<table>` elements for financials.
  - Data is serialized into JavaScript script chunks: `self.__next_f.push([1, "..."])`.
  - Scraper extracts chunks, decodes unicode escape sequences, and regex parses the company profile object:
    `rf'"{TICKER}","name":"([^"]+)","sector":"([^"]+)","board":"([^"]+)","category":"([^"]+)"'`
  - Metrics available directly: `marketCap`, `pe`, `eps`, `nav`, `bookValue`, `dividendYield`, `freeFloat`, `paidUpCapital`, `authorizedCapital`, `sharePattern` history (sponsor, govt, institution, public).
- **Legacy Fallback**: `https://www.dse.com.bd/displayCompany.php?name={TICKER}` (retained only as backup).

### Price & Market Data
- **Live Trading**: Use `bdshare.get_current_trade_data()` (pulls live trading table for all 395+ instruments).
- **Historical OHLCV**: Use `bdshare.get_historical_data(from_date, to_date, ticker)`.
  - **CRITICAL RULE**: Must call `df.reset_index()` before converting to dict, otherwise the `'date'` column in the index is lost, causing all rows to be overwritten with the fallback date!
- **Index Values (DSEX/DS30/DSES)**: Use `bdshare.get_market_summary()`.

---

## 2. Lessons Learned & Avoided Pitfalls

| Date | Issue / Mistake | Root Cause | Permanent Solution |
|---|---|---|---|
| **2026-10-05** | Scraper looked for `<table>` tags on company page | DSE migrated to modern Next.js frontend; HTML tables no longer exist | Parse `self.__next_f.push` Next.js state via `scripts/scraper.py` |
| **2026-10-05** | News scrape was called inside the ticker loop (600 requests) | Looping over 100 tickers calling 6 news sites caused rate-limiting | Fetch news **once globally** upfront (`all_scraped_news`), then filter per ticker in memory |
| **2026-10-05** | Zero score in technicals defaulted to 50 | Using `score or 50` treated 0 (bearish) as falsy | Always use `score if score is not None else 50` |
| **2026-10-05** | Wilder's RSI calculation missed last bar | Loop stopped at `len(closes) - 1` | Corrected loop bound to `range(period, len(closes))` |
| **2026-10-05** | Historical dates missing in DB insertion | `df.to_dict()` drops index unless `reset_index()` is called | Added `if 'date' not in df.columns: df = df.reset_index()` |
| **2026-10-05** | Pump-and-dump junk stocks rated as BUY | Relying purely on technical momentum without manipulation surveillance | Implemented `manipulation_detector.py` with 6 surveillance checks. High risk forces `HOLD_MANIPULATION_RISK` |
| **2026-10-05** | Bengali Rupee sign ৳ failed in Matplotlib charts | Default Windows Arial font lacks glyph 2547 | Use ASCII `BDT` or `Tk.` in chart titles and labels |
| **2026-10-05** | Foreign domestic noise distorted macro sentiment | General Indian municipal news appeared in feed | Added strict relevance filter in `macro_sentiment_engine.py` keeping only BD domestic and global commodity/war shocks |
| **2026-10-05** | Naive RSI oversold triggers produced 0.88 profit factor | Catching falling knives in downtrends | Optimized in `backtester.py`: require momentum bounce (`RSI[t] > RSI[t-1]` & MACD turn) boosting profit factor to 1.40 |
| **2026-10-05** | Ticker symbols mismatched DSE codes | E.g. `GP` vs `GRAMEENPHONE`, `LHB` vs `LHBL` | Replaced all ticker codes in `sectors.json` with verified live DSE symbols |
| **2026-10-05** | Hidden debt burden in high interest rate climate | Companies with large long-term loans suffer extreme profit compression in BD's 9-14% rate regime | Extracted DSE `loanStatus` (`shortTerm`, `longTerm`); compute empirical Debt/Equity; disqualify D/E > 1.0 from Long-Term Moats |
| **2026-10-05** | Single-year dividend yield illusion | Cyclical peak dividends lured investors into declining firms | Extracted multi-year `dividendHistory`; require 3+ consecutive years of cash dividends |
| **2026-10-05** | Fear of price drawdowns caused missing quality assets | Confusing market price depression with fundamental decline | Added Downturn Resilience heuristic: price down >15% from 52w high with positive/growing EPS is a prime accumulation buy |
| **2026-10-06** | Bank loan ratio flagged false alarms on pristine banks | Commercial banks hold borrowed deposits as core business; manufacturing D/E > 1.2 is invalid for banks | Audited Non-Performing Loans (NPL < 6.0%) separated as sole solvency metric for commercial banks in `buffett_value_screener.py` |
| **2026-10-06** | Debt-laden companies crashed in high interest rate regime | 12-14% corporate lending rates erode profits for highly leveraged firms | Empirical D/E > 1.2 screen achieved 100% accuracy in predicting falls (Crown Cement, Premier Cement, Genex, Runner) |
| **2026-10-06** | Scalp trades faded into the afternoon bell | In compressed turnover sessions (<BDT 600 Cr), liquidity dries up after 12:30 PM | Morning spike limit orders enforced for daily/weekly scalps rather than holding to closing bell |
| **2026-10-06** | Chasing momentum led to buying overvalued peaks | Technical momentum overextended past fundamental fair value | Built `pattern_causal_engine.py`: Intrinsic Worth vs Market Greed Index (0-100) hard-blocks buys when Greed > 70 |

---

## 3. Bangladesh Market Specific Rules

1. **Category A Priority**: Only trade and accumulate Category A stocks. Never buy Category B or Z for investment.
2. **Sponsor Holding Minimum**: Bangladesh Bank / BSEC guideline is ≥30% sponsor holding. Sponsor drops ≥5% indicate insider selling.
3. **Earnings Quality**: In Bangladesh, paper profits are common. Cross-verify net profit against Operating Cash Flow (`CFO / Net Profit ≥ 0.5`).
4. **Avoid Long-Term Loan Traps**: In a 9%–14% interest rate regime, companies with `Debt/Equity > 1.0` or heavy long-term loans face aggressive margin erosion. Only accumulate companies with `Debt/Equity ≤ 0.8` (or zero long-term loans like Square Pharma, Jamuna Oil, Meghna Petroleum, Padma Oil).
5. **Proven Dividend Track Record**: Demand a multi-year cash dividend history (≥3 consecutive years of cash payouts). Reject companies relying exclusively on bonus/stock dividends to dilute capital.
6. **Downturn Resilience (Growth at Discount)**: When a market-wide bear phase drives a bluechip's price down 15%–35% from its 52-week high, but its EPS, revenue, and operating cash flow remain steady or growing, this is a prime tranche accumulation setup, NOT a breakdown.
7. **Circuit Breakers**: DSE daily limit is 10%. A stock hitting upper circuit 3 days in a row without major disclosure is a pump target, not a buy.
8. **No Bulk Buying in Short-Term**: Never enter with large blocks in low-depth DSE stocks. Target 2–5% quick gains with tight ATR stops.
9. **Tri-Horizon Execution & Monthly Ledger**:
   - **⚡ Short-Term Scalps (1–10 Days)**: +3.5% quick target, -2.0% tight stop, small lot sizing, exit immediately upon hitting target.
   - **📈 Mid-Term Swings (1–6 Months)**: +15.0% target, -5.0% trailing stop, capitalizes on earnings recovery.
   - **🏛️ Long-Term Assets (1–5+ Years)**: Category A, P/E < 15, low debt (D/E ≤ 0.8), multi-year cash dividends, monthly 4-tranche accumulation on dips.
10. **Directional Trajectory & 3-Term Potential Matrix**:
   - Directional Prediction must never be guesswork. Compute empirical Rise Probability % from 7 multi-timeframe indicators: RSI oversold recovery, SMA20/50/200 structure, fundamental valuation gap (P/E < 12), balance-sheet debt health (D/E ≤ 0.5), veteran management tenure, and news intent.
   - For every stock, evaluate the 3-Term Potential: Short-Term (1–10d) +3.5% vs -2.0% (R:R ≥ 1.5x), Mid-Term (1–6m) +15% vs -5% (R:R ≥ 3.0x), and Long-Term (1–5y) +30% to +60% with 5%–8% dividend yield.
   - Strictly prohibit long-term or mid-term accumulation on tickers flagged as 🔴 `FALL_RISK`.
11. **Institutional Smart Money vs Retail Distribution**:
   - Always track monthly shareholding shifts. When $\Delta \text{Institute} + \Delta \text{Foreign} > 0$ and $\Delta \text{Retail} < 0$, that is Institutional Accumulation (+15 pts conviction).
   - If retail holding spikes by $>1.0\%$ while smart money dumps, flag as `RETAIL_DISTRIBUTION_TRAP` (-20 pts penalty) and block buying regardless of low P/E.
12. **Free Cash Flow Coverage & Slippage Guards**:
   - Paper profits lie; real cash flow does not. Demand real cash dividend coverage ($\text{NOCFPS} \ge \text{DPS}$). Never buy a dividend stock whose Operating Cash Flow is negative (Debt-funded dividend trap).
   - Enforce Max Single Order Size $\le 5\%$ of 20-day average daily traded volume to prevent $>1\%$ execution slippage.
13. **12-Factor Buffett Value & Sector Best-2 Architecture (`scripts/buffett_value_screener.py`)**:
   - **C1: Intrinsic Worth & Margin of Safety**: Composite Graham number $\sqrt{22.5 \times EPS \times NAV}$ & Sector P/E multiple fair value. Buy only if Margin of Safety $\ge 0\%$.
   - **C2: Business Age $\ge 20$ Years + Ongoing Growth**: Founded $\le 2006$. Disqualify companies $< 20$ yrs. If growth is flat/negative, IGNORE/REJECT. If ongoing, choose it.
   - **C3: Sector Best 2 Selector**: Screen all Category A stocks per sector; extract exactly the Top 2 best-of-breed companies.
   - **C4: Future Moat & Structural Support**: Essential sector demand, state fuel monopolies, pharmaceutical therapies, digital data expansion.
   - **C5: Top Management & Sponsor Integrity**: Board tenure $\ge 20-35$ yrs, AAA/AA governance, zero CIB loan defaults, pristine audit credibility (`config/company_leadership.json`).
   - **C6: Steady YoY EPS Growth**: Multi-year positive sequential earnings compounding ($EPS > 0, ROE \ge 10\%$). Reject flat or negative earnings.
   - **C7: Reinvestment & Reserve Cushion**: Payout ratio $25\%-75\%$ retains profits to reinvest into operations. Reserve per share ($NAV - 10$) must be positive, ideally $NAV \ge 2\times$ face value ($NAV \ge 20.0$ BDT).
   - **C8: P/NAV Sanity Check**: Benchmark $P/NAV \le 2.5x$. If $P/NAV > 3.5x$ and $ROE < 15\%$, flag as `SUSPICIOUS_BUBBLE_TRAP` (high price with hollow net assets). If $ROE \ge 25\%$, premium is justified.
   - **C9: Shareholding Distribution & Institutional Trust**: Sponsor+Govt $\ge 30\%$, Institutional $\ge 15\%$, Public Float $\le 50\%$.
   - **C10: Bank NPL Filter**: For banks, NPL must be $< 6.0\%$ with high provisioning. Reject toxic banks (Islami Bank NPL 28%, UCB NPL 12.5%). Approve clean private banks (Pubali 2.9%, BRAC 3.4%, EBL 3.5%, City 3.8%, DBBL 4.1%).
   - **C11: Buffett Contrarian Fear/Greed Accumulation**: Identify quality compounders in a $10\%-30\%$ drawdown from 52w peak during broader market pessimism. Accumulate in staggered tranches.
   - **C12: Dual Engine Total Return**: Dividend Yield $\%$ + Realistic Capital Gain Upside $\% \ge 15\%-25\%+$ per year.
14. **Reinforcement Learning Feedback Loop & Mistake Diagnostics (`scripts/reinforcement_learning_engine.py`)**:
   - **Immutable Prediction Ledger**: Logs every daily, weekly, and monthly directional call into `data/learning/prediction_ledger.json`.
   - **Empirical Resolution**: Evaluates pending calls against subsequent real DSE closing bars in `prices` table.
   - **Reward/Penalty Policy Gradient**:
     * Target reached / confirmed trend: $+1.0$ reward $\rightarrow$ scales up active indicator weights by $(1 + \alpha)$.
     * Stop-loss hit / wrong direction: $-1.0$ penalty $\rightarrow$ scales down faulty indicator weights by $(1 - \beta)$.
   - **Adaptive Weights**: Bank NPL (2.0x), Margin of Safety (2.0x), and Smart Money Delta (2.0x) rewarded for high predictive win-rates; isolated RSI oversold bounces downweighted (0.4x) to avoid falling knives.
   - **Mistake Diagnostics Report**: Publishes root-cause failure autopsies to `reports/learning/prediction_accuracy_evaluation.md`.

15. **Quantitative Epistemic Autopsy & Reviewer Lessons (October 2026 Audit)**:
    - **Backtest Lookahead Deconstruction**: Naive backtests using modern fundamentals joined to historical prices create massive phantom alpha (+576%). Under strict point-in-time rules and 0.833% friction, factor models underperform random 1,000-draw nulls ($p = 0.865$).
    - **Friction Completely Kills High-Turnover Technical Alpha**: Tested 14-day RSI oversold decile (2020–2026, 112 periods). Rebalance turnover is 90.9% per cycle. Round-trip friction (1.033% fee + slippage) consumes all gross edge ($t_{\text{gross}} = +0.26$), yielding **-15.47% net annualized return vs benchmark ($t = -3.12$)**. Single-factor technical anomalies are dead net of costs.
    - **Fundamental Data Provenance Boundary**: The Mendeley 14-year archive has daily OHLCV prices, but NO historical quarterly balance sheet filing dates from 2012–2025. Claiming 14-year fundamental backtests leaks future financial health. D/E < 1.0 and P/E multiples are textbook defensive screening heuristics, evaluated strictly forward.
    - **Independent Period Power Math**: Statistical power requires independent time periods ($T$), not stock-pairs. For 80% power at $IC = 0.03$ and $sd(IC) = 0.10$, requires $T \approx 87$ independent periods (**4.8 years** at 14d rebalance; **22 years** at 63d). True alpha validation cannot be rushed.
    - **Append-Only Immutable Ledger (Epoch 2)**: The forward paper test (`forward_test_ledger_v2.json`) is strictly append-only, sealed with live UTC system timestamps, benchmarks against an Equal-Weighted Total Return Universe, and tracks 52 deflated trial configurations.
    - **The Subtractive Edge**: The true role of the engine is not predicting short-term prices, but **eliminating the 90% worst stocks** on DSE (debt traps, zombie firms, retail pumps) and enforcing disciplined 5-year accumulation in zero-debt, cash-generating moats.

---

## 4. Visual Chart Capabilities
- Generated automatically into `reports/charts/`:
  - `price/{TICKER}_price.png`: Price line, SMA 20/50/200, Bollinger Bands (20, 2σ), and RSI (14) subplot.
  - `volume/{TICKER}_volume.png`: Color-coded daily volume, 30-day volume MA, and volume spike alerts (>2.5x MA).
  - `market_cap/top_15_market_cap.png`: Horizontal comparison of top market cap leaders.

---

## 5. How to Update This Skill

When a new URL changes, an endpoint fails, or a regulatory rule is updated:
1. Append the incident and solution to Section 2 (Lessons Learned table).
2. Update the verified endpoint in Section 1.
3. Keep scrapers, analyzers, and recommenders synchronized with these rules.
