# DSE Historical Liquidity & Execution Friction Matrix
**Market Date**: `2026-11-02` | **Methodology**: Corwin-Schultz (2012) OHLCV Spread Proxy | **Brokerage**: `0.415%` one-way

> [!NOTE]
> This report estimates liquidity from historical daily OHLCV trading bars. DSE does not provide public Level-2 order book depth.

## Core Liquidity & Tranche Sizing Guidelines
- **HIGH_LIQUIDITY**: Daily turnover >= ৳15M. Large retail orders (up to ৳1M) executed with negligible slippage (<0.05%).
- **MODERATE_LIQUIDITY**: Daily turnover ৳3M - ৳15M. Retail orders (<৳100k) execute fine as single tranche; larger orders use passive limit.
- **LOW_LIQUIDITY**: Daily turnover < ৳3M. Avoid large market orders; institutional sizes (>৳100k) should split into tranches.

| Ticker | Tier | Price (৳) | 20-Day ADV (Shares) | 20-Day Turnover (৳) | Est. Spread (%) | Safe Max Tranche (Shares) | Safe Max Tranche (৳) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **SQURPHARMA** | **HIGH_LIQUIDITY** | ৳217.40 | 189,998 | ৳41,547,650 | 0.25% | 2,849 sh | **৳619,373** |
| **ROBI** | **HIGH_LIQUIDITY** | ৳29.60 | 562,305 | ৳16,752,100 | 0.49% | 8,434 sh | **৳249,646** |
| **BATBC** | **MODERATE_LIQUIDITY** | ৳197.00 | 60,018 | ৳12,774,400 | 0.25% | 600 sh | **৳118,200** |
| **GP** | **MODERATE_LIQUIDITY** | ৳235.40 | 49,798 | ৳11,877,750 | 0.37% | 497 sh | **৳116,994** |
| **BSRMLTD** | **MODERATE_LIQUIDITY** | ৳94.90 | 79,439 | ৳7,724,400 | 1.64% | 794 sh | **৳75,351** |
| **RENATA** | **LOW_LIQUIDITY** | ৳425.00 | 14,318 | ৳6,323,050 | 0.22% | 71 sh | **৳30,175** |
| **WALTONHIL** | **LOW_LIQUIDITY** | ৳326.50 | 15,429 | ৳5,101,400 | 0.25% | 77 sh | **৳25,140** |
| **OLYMPIC** | **MODERATE_LIQUIDITY** | ৳135.50 | 35,635 | ৳4,942,250 | 0.54% | 356 sh | **৳48,238** |
| **MPETROLEUM** | **LOW_LIQUIDITY** | ৳211.90 | 21,923 | ৳4,557,800 | 0.10% | 109 sh | **৳23,097** |
| **CONFIDCEM** | **MODERATE_LIQUIDITY** | ৳56.00 | 57,505 | ৳3,328,750 | 0.47% | 575 sh | **৳32,200** |
| **PADMAOIL** | **LOW_LIQUIDITY** | ৳196.70 | 13,555 | ৳2,645,550 | 0.25% | 67 sh | **৳13,179** |
| **JAMUNAOIL** | **LOW_LIQUIDITY** | ৳177.10 | 7,663 | ৳1,366,450 | 0.10% | 38 sh | **৳6,730** |

## Order Slippage & Execution Friction Simulation (৳50,000 Order Size)
| Ticker | Participation Rate (%) | One-Way Fee (%) | Half-Spread (%) | Slippage Impact (%) | Total Entry Friction (%) | Round-Trip Break-Even (%) | Execution Plan |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **SQURPHARMA** | 0.12% | 0.415% | 0.12% | **0.01%** | 0.55% | **+1.10%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **ROBI** | 0.30% | 0.415% | 0.24% | **0.03%** | 0.69% | **+1.37%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **BATBC** | 0.42% | 0.415% | 0.12% | **0.04%** | 0.58% | **+1.16%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **GP** | 0.43% | 0.415% | 0.18% | **0.02%** | 0.62% | **+1.25%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **BSRMLTD** | 0.66% | 0.415% | 0.82% | **0.10%** | 1.33% | **+2.67%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **RENATA** | 0.82% | 0.415% | 0.11% | **0.05%** | 0.58% | **+1.15%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **WALTONHIL** | 0.99% | 0.415% | 0.12% | **0.04%** | 0.58% | **+1.17%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **OLYMPIC** | 1.03% | 0.415% | 0.27% | **0.09%** | 0.78% | **+1.55%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **MPETROLEUM** | 1.07% | 0.415% | 0.05% | **0.04%** | 0.51% | **+1.02%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **CONFIDCEM** | 1.55% | 0.415% | 0.23% | **0.10%** | 0.76% | **+1.51%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **PADMAOIL** | 1.87% | 0.415% | 0.12% | **0.05%** | 0.59% | **+1.18%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **JAMUNAOIL** | 3.68% | 0.415% | 0.05% | **0.10%** | 0.57% | **+1.13%** | SPLIT into 2 tranches of ~৳25000.00 each to c... |
