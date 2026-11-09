# DSE Historical Liquidity & Execution Friction Matrix
**Market Date**: `2026-11-09` | **Methodology**: Corwin-Schultz (2012) OHLCV Spread Proxy | **Brokerage**: `0.415%` one-way

> [!NOTE]
> This report estimates liquidity from historical daily OHLCV trading bars. DSE does not provide public Level-2 order book depth.

## Core Liquidity & Tranche Sizing Guidelines
- **HIGH_LIQUIDITY**: Daily turnover >= ৳15M. Large retail orders (up to ৳1M) executed with negligible slippage (<0.05%).
- **MODERATE_LIQUIDITY**: Daily turnover ৳3M - ৳15M. Retail orders (<৳100k) execute fine as single tranche; larger orders use passive limit.
- **LOW_LIQUIDITY**: Daily turnover < ৳3M. Avoid large market orders; institutional sizes (>৳100k) should split into tranches.

| Ticker | Tier | Price (৳) | 20-Day ADV (Shares) | 20-Day Turnover (৳) | Est. Spread (%) | Safe Max Tranche (Shares) | Safe Max Tranche (৳) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **SQURPHARMA** | **HIGH_LIQUIDITY** | ৳219.10 | 203,696 | ৳44,490,650 | 0.10% | 3,055 sh | **৳669,350** |
| **BATBC** | **MODERATE_LIQUIDITY** | ৳187.30 | 83,523 | ৳16,911,500 | 1.24% | 835 sh | **৳156,396** |
| **ROBI** | **HIGH_LIQUIDITY** | ৳30.30 | 563,889 | ৳16,755,200 | 0.25% | 8,458 sh | **৳256,277** |
| **GP** | **MODERATE_LIQUIDITY** | ৳223.20 | 63,956 | ৳14,957,050 | 0.25% | 639 sh | **৳142,625** |
| **MPETROLEUM** | **MODERATE_LIQUIDITY** | ৳217.20 | 41,381 | ৳8,796,500 | 0.37% | 413 sh | **৳89,704** |
| **RENATA** | **LOW_LIQUIDITY** | ৳422.60 | 19,903 | ৳8,584,350 | 1.22% | 99 sh | **৳41,837** |
| **BSRMLTD** | **MODERATE_LIQUIDITY** | ৳96.00 | 75,793 | ৳7,266,950 | 1.34% | 757 sh | **৳72,672** |
| **OLYMPIC** | **MODERATE_LIQUIDITY** | ৳133.30 | 37,293 | ৳5,089,400 | 0.25% | 372 sh | **৳49,588** |
| **WALTONHIL** | **LOW_LIQUIDITY** | ৳328.10 | 15,034 | ৳4,922,300 | 1.46% | 75 sh | **৳24,608** |
| **PADMAOIL** | **LOW_LIQUIDITY** | ৳196.60 | 23,730 | ৳4,672,350 | 0.91% | 118 sh | **৳23,199** |
| **CONFIDCEM** | **MODERATE_LIQUIDITY** | ৳58.10 | 64,026 | ৳3,662,750 | 2.01% | 640 sh | **৳37,184** |
| **JAMUNAOIL** | **LOW_LIQUIDITY** | ৳169.50 | 16,019 | ৳2,774,150 | 0.25% | 80 sh | **৳13,560** |

## Order Slippage & Execution Friction Simulation (৳50,000 Order Size)
| Ticker | Participation Rate (%) | One-Way Fee (%) | Half-Spread (%) | Slippage Impact (%) | Total Entry Friction (%) | Round-Trip Break-Even (%) | Execution Plan |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **SQURPHARMA** | 0.11% | 0.415% | 0.05% | **0.01%** | 0.48% | **+0.95%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **BATBC** | 0.32% | 0.415% | 0.62% | **0.05%** | 1.09% | **+2.18%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **ROBI** | 0.29% | 0.415% | 0.12% | **0.03%** | 0.57% | **+1.15%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **GP** | 0.35% | 0.415% | 0.12% | **0.03%** | 0.57% | **+1.14%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **MPETROLEUM** | 0.56% | 0.415% | 0.18% | **0.03%** | 0.63% | **+1.27%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **RENATA** | 0.59% | 0.415% | 0.61% | **0.04%** | 1.07% | **+2.14%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **BSRMLTD** | 0.69% | 0.415% | 0.67% | **0.10%** | 1.18% | **+2.36%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **OLYMPIC** | 1.01% | 0.415% | 0.12% | **0.08%** | 0.62% | **+1.24%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **WALTONHIL** | 1.01% | 0.415% | 0.73% | **0.06%** | 1.21% | **+2.42%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **PADMAOIL** | 1.07% | 0.415% | 0.46% | **0.04%** | 0.91% | **+1.82%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **CONFIDCEM** | 1.34% | 0.415% | 1.00% | **0.12%** | 1.54% | **+3.09%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **JAMUNAOIL** | 1.83% | 0.415% | 0.12% | **0.10%** | 0.64% | **+1.28%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
