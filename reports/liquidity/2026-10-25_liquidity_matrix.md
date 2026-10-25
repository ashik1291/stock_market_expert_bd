# DSE Historical Liquidity & Execution Friction Matrix
**Market Date**: `2026-10-25` | **Methodology**: Corwin-Schultz (2012) OHLCV Spread Proxy | **Brokerage**: `0.415%` one-way

> [!NOTE]
> This report estimates liquidity from historical daily OHLCV trading bars. DSE does not provide public Level-2 order book depth.

## Core Liquidity & Tranche Sizing Guidelines
- **HIGH_LIQUIDITY**: Daily turnover >= ৳15M. Large retail orders (up to ৳1M) executed with negligible slippage (<0.05%).
- **MODERATE_LIQUIDITY**: Daily turnover ৳3M - ৳15M. Retail orders (<৳100k) execute fine as single tranche; larger orders use passive limit.
- **LOW_LIQUIDITY**: Daily turnover < ৳3M. Avoid large market orders; institutional sizes (>৳100k) should split into tranches.

| Ticker | Tier | Price (৳) | 20-Day ADV (Shares) | 20-Day Turnover (৳) | Est. Spread (%) | Safe Max Tranche (Shares) | Safe Max Tranche (৳) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **SQURPHARMA** | **HIGH_LIQUIDITY** | ৳218.90 | 241,480 | ৳52,691,650 | 0.46% | 3,622 sh | **৳792,856** |
| **ROBI** | **HIGH_LIQUIDITY** | ৳30.00 | 589,977 | ৳17,634,950 | 0.25% | 8,849 sh | **৳265,470** |
| **GP** | **MODERATE_LIQUIDITY** | ৳238.10 | 47,032 | ৳11,295,150 | 0.11% | 470 sh | **৳111,907** |
| **BATBC** | **MODERATE_LIQUIDITY** | ৳217.30 | 44,699 | ৳9,910,000 | 0.10% | 446 sh | **৳96,916** |
| **RENATA** | **LOW_LIQUIDITY** | ৳446.30 | 18,487 | ৳8,280,600 | 0.69% | 92 sh | **৳41,060** |
| **WALTONHIL** | **LOW_LIQUIDITY** | ৳299.27 | 23,475 | ৳7,874,600 | 0.25% | 117 sh | **৳35,015** |
| **BSRMLTD** | **MODERATE_LIQUIDITY** | ৳94.30 | 74,616 | ৳7,257,050 | 0.48% | 746 sh | **৳70,348** |
| **OLYMPIC** | **MODERATE_LIQUIDITY** | ৳135.30 | 40,207 | ৳5,662,250 | 0.25% | 402 sh | **৳54,391** |
| **MPETROLEUM** | **LOW_LIQUIDITY** | ৳208.60 | 20,637 | ৳4,242,350 | 0.74% | 103 sh | **৳21,486** |
| **CONFIDCEM** | **MODERATE_LIQUIDITY** | ৳57.50 | 71,356 | ৳4,221,300 | 0.42% | 713 sh | **৳40,998** |
| **PADMAOIL** | **LOW_LIQUIDITY** | ৳194.50 | 14,703 | ৳2,867,950 | 0.60% | 73 sh | **৳14,198** |
| **JAMUNAOIL** | **LOW_LIQUIDITY** | ৳178.70 | 8,051 | ৳1,435,550 | 0.70% | 40 sh | **৳7,148** |

## Order Slippage & Execution Friction Simulation (৳50,000 Order Size)
| Ticker | Participation Rate (%) | One-Way Fee (%) | Half-Spread (%) | Slippage Impact (%) | Total Entry Friction (%) | Round-Trip Break-Even (%) | Execution Plan |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **SQURPHARMA** | 0.09% | 0.415% | 0.23% | **0.01%** | 0.66% | **+1.31%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **ROBI** | 0.28% | 0.415% | 0.12% | **0.04%** | 0.58% | **+1.15%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **GP** | 0.44% | 0.415% | 0.06% | **0.02%** | 0.49% | **+0.98%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **BATBC** | 0.52% | 0.415% | 0.05% | **0.04%** | 0.50% | **+1.00%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **RENATA** | 0.61% | 0.415% | 0.34% | **0.05%** | 0.81% | **+1.61%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **WALTONHIL** | 0.71% | 0.415% | 0.12% | **0.04%** | 0.58% | **+1.16%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **BSRMLTD** | 0.71% | 0.415% | 0.24% | **0.10%** | 0.75% | **+1.50%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **OLYMPIC** | 0.92% | 0.415% | 0.12% | **0.07%** | 0.61% | **+1.23%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **MPETROLEUM** | 1.16% | 0.415% | 0.37% | **0.05%** | 0.84% | **+1.67%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **CONFIDCEM** | 1.22% | 0.415% | 0.21% | **0.12%** | 0.74% | **+1.48%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **PADMAOIL** | 1.75% | 0.415% | 0.30% | **0.07%** | 0.78% | **+1.56%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **JAMUNAOIL** | 3.46% | 0.415% | 0.35% | **0.10%** | 0.87% | **+1.73%** | SPLIT into 2 tranches of ~৳25000.00 each to c... |
