# DSE Historical Liquidity & Execution Friction Matrix
**Market Date**: `2026-10-28` | **Methodology**: Corwin-Schultz (2012) OHLCV Spread Proxy | **Brokerage**: `0.415%` one-way

> [!NOTE]
> This report estimates liquidity from historical daily OHLCV trading bars. DSE does not provide public Level-2 order book depth.

## Core Liquidity & Tranche Sizing Guidelines
- **HIGH_LIQUIDITY**: Daily turnover >= ৳15M. Large retail orders (up to ৳1M) executed with negligible slippage (<0.05%).
- **MODERATE_LIQUIDITY**: Daily turnover ৳3M - ৳15M. Retail orders (<৳100k) execute fine as single tranche; larger orders use passive limit.
- **LOW_LIQUIDITY**: Daily turnover < ৳3M. Avoid large market orders; institutional sizes (>৳100k) should split into tranches.

| Ticker | Tier | Price (৳) | 20-Day ADV (Shares) | 20-Day Turnover (৳) | Est. Spread (%) | Safe Max Tranche (Shares) | Safe Max Tranche (৳) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **SQURPHARMA** | **HIGH_LIQUIDITY** | ৳218.80 | 209,782 | ৳45,853,800 | 0.24% | 3,146 sh | **৳688,345** |
| **ROBI** | **HIGH_LIQUIDITY** | ৳29.90 | 615,478 | ৳18,357,150 | 0.38% | 9,232 sh | **৳276,037** |
| **GP** | **MODERATE_LIQUIDITY** | ৳238.00 | 49,197 | ৳11,769,150 | 0.25% | 491 sh | **৳116,858** |
| **BATBC** | **MODERATE_LIQUIDITY** | ৳220.00 | 40,126 | ৳8,820,650 | 0.10% | 401 sh | **৳88,220** |
| **BSRMLTD** | **MODERATE_LIQUIDITY** | ৳96.80 | 79,104 | ৳7,688,300 | 1.01% | 791 sh | **৳76,569** |
| **RENATA** | **LOW_LIQUIDITY** | ৳430.30 | 15,205 | ৳6,760,950 | 0.25% | 76 sh | **৳32,703** |
| **WALTONHIL** | **LOW_LIQUIDITY** | ৳298.64 | 18,805 | ৳6,251,050 | 0.39% | 94 sh | **৳28,072** |
| **OLYMPIC** | **MODERATE_LIQUIDITY** | ৳136.40 | 37,564 | ৳5,238,650 | 1.92% | 375 sh | **৳51,150** |
| **MPETROLEUM** | **LOW_LIQUIDITY** | ৳208.20 | 21,116 | ৳4,356,950 | 0.56% | 105 sh | **৳21,861** |
| **CONFIDCEM** | **MODERATE_LIQUIDITY** | ৳57.40 | 60,966 | ৳3,562,050 | 0.25% | 609 sh | **৳34,957** |
| **PADMAOIL** | **LOW_LIQUIDITY** | ৳194.70 | 14,433 | ৳2,818,000 | 0.22% | 72 sh | **৳14,018** |
| **JAMUNAOIL** | **LOW_LIQUIDITY** | ৳178.60 | 7,885 | ৳1,405,150 | 1.25% | 39 sh | **৳6,965** |

## Order Slippage & Execution Friction Simulation (৳50,000 Order Size)
| Ticker | Participation Rate (%) | One-Way Fee (%) | Half-Spread (%) | Slippage Impact (%) | Total Entry Friction (%) | Round-Trip Break-Even (%) | Execution Plan |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **SQURPHARMA** | 0.11% | 0.415% | 0.12% | **0.01%** | 0.55% | **+1.09%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **ROBI** | 0.27% | 0.415% | 0.19% | **0.03%** | 0.63% | **+1.26%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **GP** | 0.43% | 0.415% | 0.12% | **0.02%** | 0.56% | **+1.12%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **BATBC** | 0.57% | 0.415% | 0.05% | **0.04%** | 0.50% | **+1.00%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **BSRMLTD** | 0.65% | 0.415% | 0.51% | **0.10%** | 1.02% | **+2.03%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **RENATA** | 0.76% | 0.415% | 0.12% | **0.06%** | 0.60% | **+1.19%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **WALTONHIL** | 0.89% | 0.415% | 0.20% | **0.04%** | 0.65% | **+1.30%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **OLYMPIC** | 0.97% | 0.415% | 0.96% | **0.09%** | 1.46% | **+2.92%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **MPETROLEUM** | 1.14% | 0.415% | 0.28% | **0.05%** | 0.74% | **+1.48%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **CONFIDCEM** | 1.43% | 0.415% | 0.12% | **0.10%** | 0.64% | **+1.27%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **PADMAOIL** | 1.77% | 0.415% | 0.11% | **0.06%** | 0.58% | **+1.16%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **JAMUNAOIL** | 3.54% | 0.415% | 0.62% | **0.11%** | 1.15% | **+2.30%** | SPLIT into 2 tranches of ~৳25000.00 each to c... |
