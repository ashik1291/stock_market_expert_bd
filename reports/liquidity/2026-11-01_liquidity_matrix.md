# DSE Historical Liquidity & Execution Friction Matrix
**Market Date**: `2026-11-01` | **Methodology**: Corwin-Schultz (2012) OHLCV Spread Proxy | **Brokerage**: `0.415%` one-way

> [!NOTE]
> This report estimates liquidity from historical daily OHLCV trading bars. DSE does not provide public Level-2 order book depth.

## Core Liquidity & Tranche Sizing Guidelines
- **HIGH_LIQUIDITY**: Daily turnover >= ৳15M. Large retail orders (up to ৳1M) executed with negligible slippage (<0.05%).
- **MODERATE_LIQUIDITY**: Daily turnover ৳3M - ৳15M. Retail orders (<৳100k) execute fine as single tranche; larger orders use passive limit.
- **LOW_LIQUIDITY**: Daily turnover < ৳3M. Avoid large market orders; institutional sizes (>৳100k) should split into tranches.

| Ticker | Tier | Price (৳) | 20-Day ADV (Shares) | 20-Day Turnover (৳) | Est. Spread (%) | Safe Max Tranche (Shares) | Safe Max Tranche (৳) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **SQURPHARMA** | **HIGH_LIQUIDITY** | ৳217.90 | 202,910 | ৳44,367,450 | 0.25% | 3,043 sh | **৳663,070** |
| **ROBI** | **HIGH_LIQUIDITY** | ৳29.60 | 619,254 | ৳18,456,400 | 0.10% | 9,288 sh | **৳274,925** |
| **BATBC** | **MODERATE_LIQUIDITY** | ৳201.10 | 60,118 | ৳12,868,500 | 0.25% | 601 sh | **৳120,861** |
| **GP** | **MODERATE_LIQUIDITY** | ৳235.80 | 52,540 | ৳12,540,550 | 0.17% | 525 sh | **৳123,795** |
| **BSRMLTD** | **MODERATE_LIQUIDITY** | ৳94.40 | 80,496 | ৳7,824,000 | 0.11% | 804 sh | **৳75,898** |
| **RENATA** | **LOW_LIQUIDITY** | ৳426.20 | 15,041 | ৳6,647,700 | 0.24% | 75 sh | **৳31,965** |
| **WALTONHIL** | **LOW_LIQUIDITY** | ৳296.64 | 17,438 | ৳5,779,400 | 0.28% | 87 sh | **৳25,808** |
| **OLYMPIC** | **MODERATE_LIQUIDITY** | ৳136.20 | 37,778 | ৳5,247,400 | 1.20% | 377 sh | **৳51,347** |
| **MPETROLEUM** | **LOW_LIQUIDITY** | ৳213.00 | 22,830 | ৳4,744,000 | 0.25% | 114 sh | **৳24,282** |
| **CONFIDCEM** | **MODERATE_LIQUIDITY** | ৳56.20 | 61,764 | ৳3,581,200 | 0.25% | 617 sh | **৳34,675** |
| **PADMAOIL** | **LOW_LIQUIDITY** | ৳197.50 | 14,123 | ৳2,758,150 | 0.25% | 70 sh | **৳13,825** |
| **JAMUNAOIL** | **LOW_LIQUIDITY** | ৳177.40 | 7,956 | ৳1,418,800 | 0.90% | 39 sh | **৳6,919** |

## Order Slippage & Execution Friction Simulation (৳50,000 Order Size)
| Ticker | Participation Rate (%) | One-Way Fee (%) | Half-Spread (%) | Slippage Impact (%) | Total Entry Friction (%) | Round-Trip Break-Even (%) | Execution Plan |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **SQURPHARMA** | 0.11% | 0.415% | 0.12% | **0.01%** | 0.55% | **+1.10%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **ROBI** | 0.27% | 0.415% | 0.05% | **0.03%** | 0.49% | **+0.98%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **BATBC** | 0.41% | 0.415% | 0.12% | **0.04%** | 0.58% | **+1.16%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **GP** | 0.40% | 0.415% | 0.09% | **0.02%** | 0.52% | **+1.05%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **BSRMLTD** | 0.66% | 0.415% | 0.06% | **0.10%** | 0.57% | **+1.13%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **RENATA** | 0.78% | 0.415% | 0.12% | **0.06%** | 0.59% | **+1.18%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **WALTONHIL** | 0.96% | 0.415% | 0.14% | **0.04%** | 0.60% | **+1.19%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **OLYMPIC** | 0.97% | 0.415% | 0.60% | **0.09%** | 1.10% | **+2.21%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **MPETROLEUM** | 1.02% | 0.415% | 0.12% | **0.05%** | 0.59% | **+1.17%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **CONFIDCEM** | 1.44% | 0.415% | 0.12% | **0.10%** | 0.64% | **+1.28%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **PADMAOIL** | 1.79% | 0.415% | 0.12% | **0.05%** | 0.59% | **+1.19%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **JAMUNAOIL** | 3.53% | 0.415% | 0.45% | **0.11%** | 0.97% | **+1.94%** | SPLIT into 2 tranches of ~৳25000.00 each to c... |
