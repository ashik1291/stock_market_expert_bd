---
name: dse-analyzer
description: >
  Runs technical + fundamental + sentiment + manipulation analysis for DSE tickers at a given timeframe.
  Outputs scored signals to data/knowledge/{ticker}/{timeframe}.json.
  Supports: weekly, monthly, quarterly, yearly timeframes.
---

# dse-analyzer

Analyzes DSE stocks using technical indicators, fundamental ratios, news sentiment, and 6-factor manipulation checks.

## When to use

- After `dse-processor` runs
- Agent needs to assess a specific ticker or sector
- Before generating recommendations

## Usage

### Single ticker, single timeframe
```powershell
python c:\Users\BS01671\Documents\stock_market\scripts\analyzer.py SQURPHARMA weekly
python c:\Users\BS01671\Documents\stock_market\scripts\analyzer.py BRACBANK quarterly
```

### All tickers, one timeframe
```powershell
python c:\Users\BS01671\Documents\stock_market\scripts\analyzer.py all weekly
python c:\Users\BS01671\Documents\stock_market\scripts\analyzer.py all monthly
python c:\Users\BS01671\Documents\stock_market\scripts\analyzer.py all quarterly
python c:\Users\BS01671\Documents\stock_market\scripts\analyzer.py all yearly
```

## What it computes

### Technical Indicators
| Indicator | Purpose |
|-----------|---------|
| RSI (14)  | Overbought/oversold detection (Wilder's smoothed) |
| MACD (12/26/9) | Trend momentum & crossovers |
| SMA 20/50/200 | Trend direction and golden/death crosses |
| Bollinger Bands (20, 2σ) | Volatility and breakout bounds |
| ATR (14)  | Volatility-based stop-loss sizing |
| Support/Resistance | Swing highs/lows with price tolerance |

### Fundamental Scoring (Bangladesh-specific)
| Metric | Weight Signal |
|--------|--------------|
| EPS > 0 | Positive 70pts |
| EPS YoY Growth ≥ 10% | Strong growth 85pts |
| P/E ≤ 10 | Deep value 90pts |
| P/E ≤ 15 | Fair value 70pts |
| Multi-year Cash Dividends (≥3 yrs) | Proven compounder 90pts |
| Dividend yield ≥ 5% | Income signal 80pts |
| D/E ≤ 0.5 (Audited pristine) | Low loan burden 95pts |
| D/E > 1.2 (Loan trap) | Severe penalty 10pts (Signal capped at HOLD_LOAN_TRAP_RISK) |
| Downturn Resilience | Share price down >15% from 52w peak while EPS steady/growing (High-conviction value discount) |
| ROE ≥ 15% | High capital return 80pts |
| CFO / Net Profit ≥ 0.8 | Cash-backed earnings 80pts |

### Manipulation Detection (Surveillance & Anti-Spoofing)
| Check | Trigger Condition |
|-------|-------------------|
| Volume-Price Divergence | Price up ≥5% on <50% 30-day average volume |
| Volume Spike | Volume >300% 30-day average without news |
| Serial Trading Fingerprint | Daily spread >10% with thin volume (3+ days) |
| Circuit Breaker Streak | Upper limit (10%) hit 3+ consecutive days |
| Sponsor Holding Exit | Sponsor holding drops ≥5% quarter-over-quarter |
| Price Surge Without News | 3-day price move ≥5% with zero news/disclosures |

### Management Governance & News Intent
| Metric | Weight Signal |
|--------|--------------|
| AAA / AA+ Governance (MNC/Pioneer) | 90–95pts (PwC/KPMG audits, unblemished debt) |
| Executive Tenure ≥ 25 yrs | Veteran industry leadership bonus |
| High Management Risk | Severe penalty 30pts (Signal capped at HOLD_GOVERNANCE_RISK) |
| News Intent: Legal Probe / BSEC Fine | Red-flag trigger (-25pts, caps signal at HOLD_GOVERNANCE_RISK) |
| News Intent: Expansion / Export Order | Fundamental bullish catalyst (+15pts) |

### Directional Trajectory & 3-Term Potential Matrix
- **Directional Prediction**: Computes `RISE_PREDICTED` (🟢), `CONSOLIDATION_RANGE` (🟡), or `FALL_RISK` (🔴) with explicit Rise Probability % based on multi-indicator & valuation alignment.
- **Short-Term Potential (1–10d)**: Expected bounce path, Upside % vs Downside % with Risk/Reward ratio.
- **Mid-Term Potential (1–6m)**: Mean-reversion swing target (+15%), 5% trailing stop, Risk/Reward ratio.
- **Long-Term Potential (1–5y)**: Earnings compounding target (+30%), expected dividend CAGR.

### 12-Factor Buffett Value Evaluation (`scripts/buffett_value_screener.py`)
1. **Intrinsic Worth**: $\sqrt{22.5 \times EPS \times NAV}$ & Sector P/E multiple fair value. Margin of Safety $\ge 0\%$.
2. **Business Age $\ge 20$ Yrs & Ongoing Growth**: Founded $\le 2006$. Disqualify $<20$ yrs. If growth is reduced/negative, IGNORE/REJECT.
3. **Sector Best 2 Selector**: Selects Top 2 best-of-breed compounders per sector.
4. **Future Moat & Support**: Essential demand, sovereign monopoly, patent generics, digital adoption.
5. **Top Management Integrity**: Executive tenure $\ge 20$ yrs, AAA/AA governance, zero CIB defaults.
6. **YoY EPS Compounding**: Multi-year steady EPS growth rate ($ROE \ge 10\%$). Reject flat/declining earnings.
7. **Reinvestment & Reserves**: Payout ratio $25\%-75\%$ retains profits. Reserve per share ($NAV - 10$) $> 0$, $NAV \ge 20$ BDT.
8. **P/NAV Sanity Check**: Benchmark $P/NAV \le 2.5x$. If $P/NAV > 3.5x$ and $ROE < 15\% \rightarrow$ `SUSPICIOUS_BUBBLE_TRAP`.
9. **Shareholding Distribution**: Sponsor+Govt $\ge 30\%$, Institutional $\ge 15\%$, Public Float $\le 50\%$.
10. **Bank NPL Filter**: For banks, NPL must be $< 6.0\%$. Disqualify bad debt banks.
11. **Buffett Contrarian Dip Trigger**: $10\%-30\%$ drawdown from 52w peak in high-quality asset $\rightarrow$ Tranche buy on fear.
12. **Dual Engine Total Return**: Dividend Yield $\%$ + Capital Upside $\% \ge 15\%-25\%+$ per annum.

## Output Format

```json
{
  "ticker": "SQURPHARMA",
  "timeframe": "weekly",
  "horizon": "short",
  "signal": "STRONG_BUY",
  "confidence": 78.5,
  "trade_levels": {
    "entry": 245.50,
    "target": 271.00,
    "stop_loss": 232.00
  },
  "technical": { "score": 80.2, "signals": { "rsi": "oversold_bullish", ... } },
  "fundamental": { "score": 75.0, "signals": { "pe": "fair_value (13.2)", ... } },
  "sentiment": { "score": 65.0 },
  "manipulation": {
    "manipulation_score": 0,
    "manipulation_risk": "low",
    "block_buy": false,
    "flags": []
  }
}
```

## Signal Legend

| Signal | Confidence | Action |
|--------|-----------|--------|
| STRONG_BUY | ≥ 75% | High conviction buy (manipulation risk LOW) |
| BUY | 60–74% | Buy with normal position (manipulation risk LOW) |
| HOLD | 45–59% | No new position |
| HOLD_MANIPULATION_RISK | Any | High manipulation risk flagged — DO NOT BUY |
| SELL | 30–44% | Reduce or exit |
| STRONG_SELL | < 30% | Exit immediately |

## Agent Instructions

After analysis, recommend timeframes based on investor horizon:
- Short-term (weekly/monthly) → trading signals with entry/stop/target
- Mid-term (quarterly) → position trades, hold 1–6 months
- Long-term (yearly) → accumulation candidates, hold 6m–3yr
Always verify that `HOLD_MANIPULATION_RISK` stocks are isolated and highlighted to prevent capital loss.
