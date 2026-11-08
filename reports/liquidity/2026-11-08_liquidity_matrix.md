# DSE Historical Liquidity & Execution Friction Matrix
**Market Date**: `2026-11-08` | **Methodology**: Corwin-Schultz (2012) OHLCV Spread Proxy | **Brokerage**: `0.415%` one-way

> [!NOTE]
> This report estimates liquidity from historical daily OHLCV trading bars. DSE does not provide public Level-2 order book depth.

## Core Liquidity & Tranche Sizing Guidelines
- **HIGH_LIQUIDITY**: Daily turnover >= ৳15M. Large retail orders (up to ৳1M) executed with negligible slippage (<0.05%).
- **MODERATE_LIQUIDITY**: Daily turnover ৳3M - ৳15M. Retail orders (<৳100k) execute fine as single tranche; larger orders use passive limit.
- **LOW_LIQUIDITY**: Daily turnover < ৳3M. Avoid large market orders; institutional sizes (>৳100k) should split into tranches.

| Ticker | Tier | Price (৳) | 20-Day ADV (Shares) | 20-Day Turnover (৳) | Est. Spread (%) | Safe Max Tranche (Shares) | Safe Max Tranche (৳) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **SQURPHARMA** | **HIGH_LIQUIDITY** | ৳218.50 | 199,907 | ৳43,654,250 | 0.25% | 2,998 sh | **৳655,063** |
| **ROBI** | **HIGH_LIQUIDITY** | ৳29.90 | 547,653 | ৳16,256,600 | 0.18% | 8,214 sh | **৳245,599** |
| **BATBC** | **MODERATE_LIQUIDITY** | ৳186.00 | 79,322 | ৳16,184,250 | 0.83% | 793 sh | **৳147,498** |
| **GP** | **MODERATE_LIQUIDITY** | ৳224.80 | 58,746 | ৳13,817,650 | 0.25% | 587 sh | **৳131,958** |
| **RENATA** | **LOW_LIQUIDITY** | ৳420.00 | 20,270 | ৳8,785,700 | 0.25% | 101 sh | **৳42,420** |
| **MPETROLEUM** | **MODERATE_LIQUIDITY** | ৳217.90 | 38,729 | ৳8,201,500 | 0.25% | 387 sh | **৳84,327** |
| **BSRMLTD** | **MODERATE_LIQUIDITY** | ৳94.90 | 78,591 | ৳7,556,850 | 0.43% | 785 sh | **৳74,496** |
| **OLYMPIC** | **MODERATE_LIQUIDITY** | ৳134.70 | 38,428 | ৳5,267,750 | 1.10% | 384 sh | **৳51,725** |
| **WALTONHIL** | **LOW_LIQUIDITY** | ৳333.10 | 15,228 | ৳4,988,450 | 0.25% | 76 sh | **৳25,316** |
| **PADMAOIL** | **LOW_LIQUIDITY** | ৳197.70 | 21,785 | ৳4,288,700 | 0.10% | 108 sh | **৳21,352** |
| **CONFIDCEM** | **MODERATE_LIQUIDITY** | ৳57.30 | 59,157 | ৳3,386,600 | 1.28% | 591 sh | **৳33,864** |
| **JAMUNAOIL** | **LOW_LIQUIDITY** | ৳179.00 | 8,530 | ৳1,521,600 | 0.10% | 42 sh | **৳7,518** |

## Order Slippage & Execution Friction Simulation (৳50,000 Order Size)
| Ticker | Participation Rate (%) | One-Way Fee (%) | Half-Spread (%) | Slippage Impact (%) | Total Entry Friction (%) | Round-Trip Break-Even (%) | Execution Plan |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **SQURPHARMA** | 0.11% | 0.415% | 0.12% | **0.01%** | 0.55% | **+1.10%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **ROBI** | 0.30% | 0.415% | 0.09% | **0.03%** | 0.54% | **+1.07%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **BATBC** | 0.34% | 0.415% | 0.41% | **0.05%** | 0.88% | **+1.77%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **GP** | 0.38% | 0.415% | 0.12% | **0.03%** | 0.57% | **+1.14%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **RENATA** | 0.59% | 0.415% | 0.12% | **0.04%** | 0.58% | **+1.16%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **MPETROLEUM** | 0.59% | 0.415% | 0.12% | **0.03%** | 0.57% | **+1.15%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **BSRMLTD** | 0.67% | 0.415% | 0.21% | **0.09%** | 0.72% | **+1.45%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **OLYMPIC** | 0.96% | 0.415% | 0.55% | **0.08%** | 1.05% | **+2.10%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **WALTONHIL** | 0.98% | 0.415% | 0.12% | **0.06%** | 0.60% | **+1.20%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **PADMAOIL** | 1.16% | 0.415% | 0.05% | **0.04%** | 0.51% | **+1.01%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **CONFIDCEM** | 1.47% | 0.415% | 0.64% | **0.13%** | 1.18% | **+2.36%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **JAMUNAOIL** | 3.27% | 0.415% | 0.05% | **0.12%** | 0.58% | **+1.16%** | SPLIT into 2 tranches of ~৳25000.00 each to c... |
