# DSE Historical Liquidity & Execution Friction Matrix
**Market Date**: `2026-11-03` | **Methodology**: Corwin-Schultz (2012) OHLCV Spread Proxy | **Brokerage**: `0.415%` one-way

> [!NOTE]
> This report estimates liquidity from historical daily OHLCV trading bars. DSE does not provide public Level-2 order book depth.

## Core Liquidity & Tranche Sizing Guidelines
- **HIGH_LIQUIDITY**: Daily turnover >= ৳15M. Large retail orders (up to ৳1M) executed with negligible slippage (<0.05%).
- **MODERATE_LIQUIDITY**: Daily turnover ৳3M - ৳15M. Retail orders (<৳100k) execute fine as single tranche; larger orders use passive limit.
- **LOW_LIQUIDITY**: Daily turnover < ৳3M. Avoid large market orders; institutional sizes (>৳100k) should split into tranches.

| Ticker | Tier | Price (৳) | 20-Day ADV (Shares) | 20-Day Turnover (৳) | Est. Spread (%) | Safe Max Tranche (Shares) | Safe Max Tranche (৳) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **SQURPHARMA** | **HIGH_LIQUIDITY** | ৳215.60 | 196,415 | ৳42,891,250 | 0.25% | 2,946 sh | **৳635,158** |
| **ROBI** | **HIGH_LIQUIDITY** | ৳29.00 | 572,398 | ৳17,021,500 | 0.18% | 8,585 sh | **৳248,965** |
| **BATBC** | **MODERATE_LIQUIDITY** | ৳188.90 | 71,168 | ৳14,813,750 | 0.25% | 711 sh | **৳134,308** |
| **GP** | **MODERATE_LIQUIDITY** | ৳229.00 | 52,012 | ৳12,365,350 | 0.25% | 520 sh | **৳119,080** |
| **BSRMLTD** | **MODERATE_LIQUIDITY** | ৳92.10 | 83,356 | ৳8,083,550 | 0.25% | 833 sh | **৳76,719** |
| **MPETROLEUM** | **MODERATE_LIQUIDITY** | ৳213.90 | 31,996 | ৳6,717,750 | 0.10% | 319 sh | **৳68,234** |
| **RENATA** | **LOW_LIQUIDITY** | ৳419.90 | 14,677 | ৳6,458,900 | 0.25% | 73 sh | **৳30,653** |
| **OLYMPIC** | **MODERATE_LIQUIDITY** | ৳136.90 | 42,898 | ৳5,917,200 | 0.37% | 428 sh | **৳58,593** |
| **WALTONHIL** | **LOW_LIQUIDITY** | ৳319.40 | 15,004 | ৳4,943,550 | 0.25% | 75 sh | **৳23,955** |
| **CONFIDCEM** | **MODERATE_LIQUIDITY** | ৳55.00 | 58,249 | ৳3,350,100 | 0.32% | 582 sh | **৳32,010** |
| **PADMAOIL** | **LOW_LIQUIDITY** | ৳198.50 | 16,462 | ৳3,222,350 | 0.25% | 82 sh | **৳16,277** |
| **JAMUNAOIL** | **LOW_LIQUIDITY** | ৳176.60 | 7,891 | ৳1,406,600 | 0.10% | 39 sh | **৳6,887** |

## Order Slippage & Execution Friction Simulation (৳50,000 Order Size)
| Ticker | Participation Rate (%) | One-Way Fee (%) | Half-Spread (%) | Slippage Impact (%) | Total Entry Friction (%) | Round-Trip Break-Even (%) | Execution Plan |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **SQURPHARMA** | 0.12% | 0.415% | 0.12% | **0.01%** | 0.55% | **+1.10%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **ROBI** | 0.30% | 0.415% | 0.09% | **0.03%** | 0.53% | **+1.06%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **BATBC** | 0.37% | 0.415% | 0.12% | **0.05%** | 0.59% | **+1.17%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **GP** | 0.42% | 0.415% | 0.12% | **0.03%** | 0.57% | **+1.13%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **BSRMLTD** | 0.65% | 0.415% | 0.12% | **0.10%** | 0.64% | **+1.28%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **MPETROLEUM** | 0.73% | 0.415% | 0.05% | **0.04%** | 0.50% | **+1.01%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **RENATA** | 0.81% | 0.415% | 0.12% | **0.05%** | 0.59% | **+1.18%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **OLYMPIC** | 0.85% | 0.415% | 0.18% | **0.08%** | 0.68% | **+1.37%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **WALTONHIL** | 1.04% | 0.415% | 0.12% | **0.05%** | 0.59% | **+1.18%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **CONFIDCEM** | 1.56% | 0.415% | 0.16% | **0.12%** | 0.69% | **+1.38%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **PADMAOIL** | 1.52% | 0.415% | 0.12% | **0.05%** | 0.59% | **+1.17%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **JAMUNAOIL** | 3.59% | 0.415% | 0.05% | **0.12%** | 0.58% | **+1.17%** | SPLIT into 2 tranches of ~৳25000.00 each to c... |
