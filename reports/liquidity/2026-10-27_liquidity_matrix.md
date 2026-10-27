# DSE Historical Liquidity & Execution Friction Matrix
**Market Date**: `2026-10-27` | **Methodology**: Corwin-Schultz (2012) OHLCV Spread Proxy | **Brokerage**: `0.415%` one-way

> [!NOTE]
> This report estimates liquidity from historical daily OHLCV trading bars. DSE does not provide public Level-2 order book depth.

## Core Liquidity & Tranche Sizing Guidelines
- **HIGH_LIQUIDITY**: Daily turnover >= ৳15M. Large retail orders (up to ৳1M) executed with negligible slippage (<0.05%).
- **MODERATE_LIQUIDITY**: Daily turnover ৳3M - ৳15M. Retail orders (<৳100k) execute fine as single tranche; larger orders use passive limit.
- **LOW_LIQUIDITY**: Daily turnover < ৳3M. Avoid large market orders; institutional sizes (>৳100k) should split into tranches.

| Ticker | Tier | Price (৳) | 20-Day ADV (Shares) | 20-Day Turnover (৳) | Est. Spread (%) | Safe Max Tranche (Shares) | Safe Max Tranche (৳) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **SQURPHARMA** | **HIGH_LIQUIDITY** | ৳218.80 | 209,965 | ৳45,879,350 | 0.38% | 3,149 sh | **৳689,001** |
| **ROBI** | **HIGH_LIQUIDITY** | ৳29.70 | 588,252 | ৳17,553,650 | 0.25% | 8,823 sh | **৳262,043** |
| **GP** | **MODERATE_LIQUIDITY** | ৳237.60 | 47,960 | ৳11,486,350 | 0.25% | 479 sh | **৳113,810** |
| **BATBC** | **MODERATE_LIQUIDITY** | ৳217.60 | 39,894 | ৳8,787,000 | 0.15% | 398 sh | **৳86,605** |
| **BSRMLTD** | **MODERATE_LIQUIDITY** | ৳96.00 | 78,310 | ৳7,609,800 | 1.01% | 783 sh | **৳75,168** |
| **WALTONHIL** | **LOW_LIQUIDITY** | ৳298.18 | 20,791 | ৳6,929,500 | 0.35% | 103 sh | **৳30,713** |
| **RENATA** | **LOW_LIQUIDITY** | ৳439.40 | 14,517 | ৳6,471,400 | 0.25% | 72 sh | **৳31,637** |
| **OLYMPIC** | **MODERATE_LIQUIDITY** | ৳134.40 | 37,570 | ৳5,249,750 | 2.58% | 375 sh | **৳50,400** |
| **MPETROLEUM** | **LOW_LIQUIDITY** | ৳207.70 | 21,319 | ৳4,395,650 | 0.21% | 106 sh | **৳22,016** |
| **CONFIDCEM** | **MODERATE_LIQUIDITY** | ৳57.20 | 61,531 | ৳3,606,200 | 0.10% | 615 sh | **৳35,178** |
| **PADMAOIL** | **LOW_LIQUIDITY** | ৳194.90 | 14,449 | ৳2,820,650 | 0.25% | 72 sh | **৳14,033** |
| **JAMUNAOIL** | **LOW_LIQUIDITY** | ৳177.00 | 8,157 | ৳1,453,250 | 1.22% | 40 sh | **৳7,080** |

## Order Slippage & Execution Friction Simulation (৳50,000 Order Size)
| Ticker | Participation Rate (%) | One-Way Fee (%) | Half-Spread (%) | Slippage Impact (%) | Total Entry Friction (%) | Round-Trip Break-Even (%) | Execution Plan |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **SQURPHARMA** | 0.11% | 0.415% | 0.19% | **0.01%** | 0.61% | **+1.23%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **ROBI** | 0.29% | 0.415% | 0.12% | **0.04%** | 0.58% | **+1.15%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **GP** | 0.44% | 0.415% | 0.12% | **0.02%** | 0.56% | **+1.12%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **BATBC** | 0.57% | 0.415% | 0.07% | **0.03%** | 0.52% | **+1.05%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **BSRMLTD** | 0.66% | 0.415% | 0.51% | **0.10%** | 1.02% | **+2.03%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **WALTONHIL** | 0.80% | 0.415% | 0.17% | **0.04%** | 0.63% | **+1.26%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **RENATA** | 0.78% | 0.415% | 0.12% | **0.05%** | 0.59% | **+1.19%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **OLYMPIC** | 0.99% | 0.415% | 1.29% | **0.08%** | 1.79% | **+3.58%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **MPETROLEUM** | 1.13% | 0.415% | 0.10% | **0.05%** | 0.57% | **+1.13%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **CONFIDCEM** | 1.42% | 0.415% | 0.05% | **0.11%** | 0.57% | **+1.15%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **PADMAOIL** | 1.77% | 0.415% | 0.12% | **0.06%** | 0.60% | **+1.20%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **JAMUNAOIL** | 3.46% | 0.415% | 0.61% | **0.11%** | 1.13% | **+2.26%** | SPLIT into 2 tranches of ~৳25000.00 each to c... |
