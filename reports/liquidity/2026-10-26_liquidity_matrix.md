# DSE Historical Liquidity & Execution Friction Matrix
**Market Date**: `2026-10-26` | **Methodology**: Corwin-Schultz (2012) OHLCV Spread Proxy | **Brokerage**: `0.415%` one-way

> [!NOTE]
> This report estimates liquidity from historical daily OHLCV trading bars. DSE does not provide public Level-2 order book depth.

## Core Liquidity & Tranche Sizing Guidelines
- **HIGH_LIQUIDITY**: Daily turnover >= ৳15M. Large retail orders (up to ৳1M) executed with negligible slippage (<0.05%).
- **MODERATE_LIQUIDITY**: Daily turnover ৳3M - ৳15M. Retail orders (<৳100k) execute fine as single tranche; larger orders use passive limit.
- **LOW_LIQUIDITY**: Daily turnover < ৳3M. Avoid large market orders; institutional sizes (>৳100k) should split into tranches.

| Ticker | Tier | Price (৳) | 20-Day ADV (Shares) | 20-Day Turnover (৳) | Est. Spread (%) | Safe Max Tranche (Shares) | Safe Max Tranche (৳) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **SQURPHARMA** | **HIGH_LIQUIDITY** | ৳218.80 | 210,198 | ৳45,894,800 | 0.27% | 3,152 sh | **৳689,658** |
| **ROBI** | **HIGH_LIQUIDITY** | ৳29.80 | 608,405 | ৳18,179,950 | 1.13% | 9,126 sh | **৳271,955** |
| **GP** | **MODERATE_LIQUIDITY** | ৳237.70 | 46,308 | ৳11,105,950 | 0.25% | 463 sh | **৳110,055** |
| **BATBC** | **MODERATE_LIQUIDITY** | ৳217.30 | 42,353 | ৳9,354,050 | 0.10% | 423 sh | **৳91,918** |
| **WALTONHIL** | **LOW_LIQUIDITY** | ৳298.64 | 22,612 | ৳7,563,350 | 0.25% | 113 sh | **৳33,746** |
| **BSRMLTD** | **MODERATE_LIQUIDITY** | ৳95.90 | 76,213 | ৳7,408,900 | 1.77% | 762 sh | **৳73,076** |
| **RENATA** | **LOW_LIQUIDITY** | ৳443.80 | 13,496 | ৳6,024,250 | 0.57% | 67 sh | **৳29,735** |
| **OLYMPIC** | **MODERATE_LIQUIDITY** | ৳134.00 | 40,279 | ৳5,648,500 | 1.41% | 402 sh | **৳53,868** |
| **MPETROLEUM** | **LOW_LIQUIDITY** | ৳208.20 | 21,498 | ৳4,428,150 | 0.17% | 107 sh | **৳22,277** |
| **CONFIDCEM** | **MODERATE_LIQUIDITY** | ৳57.00 | 65,551 | ৳3,854,650 | 0.11% | 655 sh | **৳37,335** |
| **PADMAOIL** | **LOW_LIQUIDITY** | ৳195.00 | 14,792 | ৳2,884,900 | 0.21% | 73 sh | **৳14,235** |
| **JAMUNAOIL** | **LOW_LIQUIDITY** | ৳177.30 | 8,212 | ৳1,463,600 | 0.92% | 41 sh | **৳7,269** |

## Order Slippage & Execution Friction Simulation (৳50,000 Order Size)
| Ticker | Participation Rate (%) | One-Way Fee (%) | Half-Spread (%) | Slippage Impact (%) | Total Entry Friction (%) | Round-Trip Break-Even (%) | Execution Plan |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **SQURPHARMA** | 0.11% | 0.415% | 0.14% | **0.01%** | 0.56% | **+1.12%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **ROBI** | 0.28% | 0.415% | 0.56% | **0.04%** | 1.02% | **+2.03%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **GP** | 0.45% | 0.415% | 0.12% | **0.02%** | 0.56% | **+1.12%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **BATBC** | 0.54% | 0.415% | 0.05% | **0.04%** | 0.50% | **+1.00%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **WALTONHIL** | 0.74% | 0.415% | 0.12% | **0.04%** | 0.58% | **+1.15%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **BSRMLTD** | 0.68% | 0.415% | 0.89% | **0.10%** | 1.40% | **+2.79%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **RENATA** | 0.83% | 0.415% | 0.28% | **0.05%** | 0.75% | **+1.51%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **OLYMPIC** | 0.93% | 0.415% | 0.70% | **0.08%** | 1.20% | **+2.40%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **MPETROLEUM** | 1.12% | 0.415% | 0.09% | **0.05%** | 0.55% | **+1.10%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **CONFIDCEM** | 1.34% | 0.415% | 0.06% | **0.12%** | 0.59% | **+1.17%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **PADMAOIL** | 1.73% | 0.415% | 0.10% | **0.07%** | 0.58% | **+1.17%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **JAMUNAOIL** | 3.43% | 0.415% | 0.46% | **0.10%** | 0.98% | **+1.96%** | SPLIT into 2 tranches of ~৳25000.00 each to c... |
