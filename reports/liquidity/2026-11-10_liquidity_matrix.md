# DSE Historical Liquidity & Execution Friction Matrix
**Market Date**: `2026-11-10` | **Methodology**: Corwin-Schultz (2012) OHLCV Spread Proxy | **Brokerage**: `0.415%` one-way

> [!NOTE]
> This report estimates liquidity from historical daily OHLCV trading bars. DSE does not provide public Level-2 order book depth.

## Core Liquidity & Tranche Sizing Guidelines
- **HIGH_LIQUIDITY**: Daily turnover >= ৳15M. Large retail orders (up to ৳1M) executed with negligible slippage (<0.05%).
- **MODERATE_LIQUIDITY**: Daily turnover ৳3M - ৳15M. Retail orders (<৳100k) execute fine as single tranche; larger orders use passive limit.
- **LOW_LIQUIDITY**: Daily turnover < ৳3M. Avoid large market orders; institutional sizes (>৳100k) should split into tranches.

| Ticker | Tier | Price (৳) | 20-Day ADV (Shares) | 20-Day Turnover (৳) | Est. Spread (%) | Safe Max Tranche (Shares) | Safe Max Tranche (৳) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **SQURPHARMA** | **HIGH_LIQUIDITY** | ৳219.10 | 211,940 | ৳46,296,850 | 0.37% | 3,179 sh | **৳696,519** |
| **ROBI** | **HIGH_LIQUIDITY** | ৳30.30 | 616,153 | ৳18,329,550 | 3.33% | 9,242 sh | **৳280,033** |
| **BATBC** | **MODERATE_LIQUIDITY** | ৳187.30 | 89,077 | ৳17,941,100 | 2.88% | 890 sh | **৳166,697** |
| **GP** | **MODERATE_LIQUIDITY** | ৳223.20 | 70,372 | ৳16,388,000 | 1.03% | 703 sh | **৳156,910** |
| **MPETROLEUM** | **MODERATE_LIQUIDITY** | ৳217.20 | 45,444 | ৳9,679,700 | 1.15% | 454 sh | **৳98,609** |
| **RENATA** | **LOW_LIQUIDITY** | ৳422.60 | 21,289 | ৳9,171,350 | 1.46% | 106 sh | **৳44,796** |
| **BSRMLTD** | **MODERATE_LIQUIDITY** | ৳96.00 | 77,824 | ৳7,459,500 | 2.10% | 778 sh | **৳74,688** |
| **OLYMPIC** | **MODERATE_LIQUIDITY** | ৳133.30 | 39,144 | ৳5,334,950 | 1.42% | 391 sh | **৳52,120** |
| **PADMAOIL** | **MODERATE_LIQUIDITY** | ৳196.60 | 25,988 | ৳5,117,000 | 1.47% | 259 sh | **৳50,919** |
| **WALTONHIL** | **LOW_LIQUIDITY** | ৳328.10 | 15,458 | ৳5,061,500 | 2.57% | 77 sh | **৳25,264** |
| **JAMUNAOIL** | **LOW_LIQUIDITY** | ৳169.50 | 24,469 | ৳4,198,100 | 5.00% | 122 sh | **৳20,679** |
| **CONFIDCEM** | **MODERATE_LIQUIDITY** | ৳58.10 | 70,721 | ৳4,048,100 | 3.12% | 707 sh | **৳41,077** |

## Order Slippage & Execution Friction Simulation (৳50,000 Order Size)
| Ticker | Participation Rate (%) | One-Way Fee (%) | Half-Spread (%) | Slippage Impact (%) | Total Entry Friction (%) | Round-Trip Break-Even (%) | Execution Plan |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **SQURPHARMA** | 0.11% | 0.415% | 0.18% | **0.01%** | 0.61% | **+1.22%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **ROBI** | 0.27% | 0.415% | 1.67% | **0.04%** | 2.12% | **+4.23%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **BATBC** | 0.30% | 0.415% | 1.44% | **0.06%** | 1.91% | **+3.82%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **GP** | 0.32% | 0.415% | 0.52% | **0.03%** | 0.96% | **+1.91%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **MPETROLEUM** | 0.51% | 0.415% | 0.57% | **0.03%** | 1.02% | **+2.05%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **RENATA** | 0.55% | 0.415% | 0.73% | **0.04%** | 1.19% | **+2.38%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **BSRMLTD** | 0.67% | 0.415% | 1.05% | **0.09%** | 1.56% | **+3.11%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **OLYMPIC** | 0.96% | 0.415% | 0.71% | **0.08%** | 1.20% | **+2.41%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **PADMAOIL** | 0.98% | 0.415% | 0.73% | **0.04%** | 1.19% | **+2.38%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **WALTONHIL** | 0.98% | 0.415% | 1.28% | **0.07%** | 1.77% | **+3.53%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **JAMUNAOIL** | 1.20% | 0.415% | 2.50% | **0.10%** | 3.01% | **+6.02%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **CONFIDCEM** | 1.22% | 0.415% | 1.56% | **0.12%** | 2.10% | **+4.19%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
