# DSE Historical Liquidity & Execution Friction Matrix
**Market Date**: `2026-10-29` | **Methodology**: Corwin-Schultz (2012) OHLCV Spread Proxy | **Brokerage**: `0.415%` one-way

> [!NOTE]
> This report estimates liquidity from historical daily OHLCV trading bars. DSE does not provide public Level-2 order book depth.

## Core Liquidity & Tranche Sizing Guidelines
- **HIGH_LIQUIDITY**: Daily turnover >= ৳15M. Large retail orders (up to ৳1M) executed with negligible slippage (<0.05%).
- **MODERATE_LIQUIDITY**: Daily turnover ৳3M - ৳15M. Retail orders (<৳100k) execute fine as single tranche; larger orders use passive limit.
- **LOW_LIQUIDITY**: Daily turnover < ৳3M. Avoid large market orders; institutional sizes (>৳100k) should split into tranches.

| Ticker | Tier | Price (৳) | 20-Day ADV (Shares) | 20-Day Turnover (৳) | Est. Spread (%) | Safe Max Tranche (Shares) | Safe Max Tranche (৳) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **SQURPHARMA** | **HIGH_LIQUIDITY** | ৳218.50 | 208,924 | ৳45,676,400 | 0.35% | 3,133 sh | **৳684,560** |
| **ROBI** | **HIGH_LIQUIDITY** | ৳29.70 | 624,591 | ৳18,621,850 | 1.34% | 9,368 sh | **৳278,230** |
| **GP** | **MODERATE_LIQUIDITY** | ৳237.30 | 51,048 | ৳12,201,200 | 0.47% | 510 sh | **৳121,023** |
| **BATBC** | **MODERATE_LIQUIDITY** | ৳209.10 | 53,988 | ৳11,669,150 | 0.25% | 539 sh | **৳112,705** |
| **BSRMLTD** | **MODERATE_LIQUIDITY** | ৳95.40 | 80,195 | ৳7,794,650 | 1.01% | 801 sh | **৳76,415** |
| **RENATA** | **LOW_LIQUIDITY** | ৳425.90 | 16,150 | ৳7,155,650 | 0.25% | 80 sh | **৳34,072** |
| **WALTONHIL** | **LOW_LIQUIDITY** | ৳299.64 | 17,896 | ৳5,940,150 | 0.25% | 89 sh | **৳26,668** |
| **OLYMPIC** | **MODERATE_LIQUIDITY** | ৳134.90 | 37,699 | ৳5,244,050 | 1.02% | 376 sh | **৳50,722** |
| **MPETROLEUM** | **LOW_LIQUIDITY** | ৳211.50 | 21,406 | ৳4,425,000 | 0.25% | 107 sh | **৳22,630** |
| **CONFIDCEM** | **MODERATE_LIQUIDITY** | ৳57.20 | 61,572 | ৳3,585,750 | 0.50% | 615 sh | **৳35,178** |
| **PADMAOIL** | **LOW_LIQUIDITY** | ৳197.50 | 14,509 | ৳2,834,050 | 0.25% | 72 sh | **৳14,220** |
| **JAMUNAOIL** | **LOW_LIQUIDITY** | ৳178.20 | 7,932 | ৳1,414,000 | 0.70% | 39 sh | **৳6,950** |

## Order Slippage & Execution Friction Simulation (৳50,000 Order Size)
| Ticker | Participation Rate (%) | One-Way Fee (%) | Half-Spread (%) | Slippage Impact (%) | Total Entry Friction (%) | Round-Trip Break-Even (%) | Execution Plan |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **SQURPHARMA** | 0.11% | 0.415% | 0.17% | **0.01%** | 0.60% | **+1.20%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **ROBI** | 0.27% | 0.415% | 0.67% | **0.03%** | 1.11% | **+2.22%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **GP** | 0.41% | 0.415% | 0.23% | **0.02%** | 0.67% | **+1.34%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **BATBC** | 0.44% | 0.415% | 0.12% | **0.04%** | 0.58% | **+1.15%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **BSRMLTD** | 0.65% | 0.415% | 0.51% | **0.10%** | 1.02% | **+2.03%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **RENATA** | 0.72% | 0.415% | 0.12% | **0.06%** | 0.59% | **+1.19%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **WALTONHIL** | 0.93% | 0.415% | 0.12% | **0.04%** | 0.58% | **+1.16%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **OLYMPIC** | 0.98% | 0.415% | 0.51% | **0.09%** | 1.01% | **+2.03%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **MPETROLEUM** | 1.10% | 0.415% | 0.12% | **0.05%** | 0.59% | **+1.17%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **CONFIDCEM** | 1.42% | 0.415% | 0.25% | **0.10%** | 0.76% | **+1.52%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **PADMAOIL** | 1.74% | 0.415% | 0.12% | **0.05%** | 0.59% | **+1.19%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **JAMUNAOIL** | 3.53% | 0.415% | 0.35% | **0.11%** | 0.87% | **+1.74%** | SPLIT into 2 tranches of ~৳25000.00 each to c... |
