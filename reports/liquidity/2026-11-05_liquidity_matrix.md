# DSE Historical Liquidity & Execution Friction Matrix
**Market Date**: `2026-11-05` | **Methodology**: Corwin-Schultz (2012) OHLCV Spread Proxy | **Brokerage**: `0.415%` one-way

> [!NOTE]
> This report estimates liquidity from historical daily OHLCV trading bars. DSE does not provide public Level-2 order book depth.

## Core Liquidity & Tranche Sizing Guidelines
- **HIGH_LIQUIDITY**: Daily turnover >= ৳15M. Large retail orders (up to ৳1M) executed with negligible slippage (<0.05%).
- **MODERATE_LIQUIDITY**: Daily turnover ৳3M - ৳15M. Retail orders (<৳100k) execute fine as single tranche; larger orders use passive limit.
- **LOW_LIQUIDITY**: Daily turnover < ৳3M. Avoid large market orders; institutional sizes (>৳100k) should split into tranches.

| Ticker | Tier | Price (৳) | 20-Day ADV (Shares) | 20-Day Turnover (৳) | Est. Spread (%) | Safe Max Tranche (Shares) | Safe Max Tranche (৳) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **SQURPHARMA** | **HIGH_LIQUIDITY** | ৳217.00 | 196,255 | ৳42,847,100 | 0.25% | 2,943 sh | **৳638,631** |
| **ROBI** | **HIGH_LIQUIDITY** | ৳29.20 | 524,879 | ৳15,582,450 | 0.27% | 7,873 sh | **৳229,892** |
| **BATBC** | **MODERATE_LIQUIDITY** | ৳191.00 | 73,710 | ৳15,196,250 | 1.79% | 737 sh | **৳140,767** |
| **GP** | **MODERATE_LIQUIDITY** | ৳229.00 | 51,347 | ৳12,168,850 | 0.57% | 513 sh | **৳117,477** |
| **BSRMLTD** | **MODERATE_LIQUIDITY** | ৳94.60 | 85,276 | ৳8,264,900 | 0.10% | 852 sh | **৳80,599** |
| **MPETROLEUM** | **MODERATE_LIQUIDITY** | ৳213.90 | 33,713 | ৳7,102,000 | 0.32% | 337 sh | **৳72,084** |
| **RENATA** | **LOW_LIQUIDITY** | ৳418.30 | 14,582 | ৳6,401,500 | 0.10% | 72 sh | **৳30,118** |
| **OLYMPIC** | **MODERATE_LIQUIDITY** | ৳134.90 | 40,190 | ৳5,531,250 | 0.25% | 401 sh | **৳54,095** |
| **WALTONHIL** | **LOW_LIQUIDITY** | ৳316.10 | 13,702 | ৳4,484,950 | 0.80% | 68 sh | **৳21,495** |
| **PADMAOIL** | **LOW_LIQUIDITY** | ৳199.00 | 17,412 | ৳3,414,850 | 0.16% | 87 sh | **৳17,313** |
| **CONFIDCEM** | **MODERATE_LIQUIDITY** | ৳57.70 | 58,105 | ৳3,329,800 | 2.46% | 581 sh | **৳33,524** |
| **JAMUNAOIL** | **LOW_LIQUIDITY** | ৳178.90 | 7,411 | ৳1,321,100 | 0.25% | 37 sh | **৳6,619** |

## Order Slippage & Execution Friction Simulation (৳50,000 Order Size)
| Ticker | Participation Rate (%) | One-Way Fee (%) | Half-Spread (%) | Slippage Impact (%) | Total Entry Friction (%) | Round-Trip Break-Even (%) | Execution Plan |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **SQURPHARMA** | 0.12% | 0.415% | 0.12% | **0.01%** | 0.55% | **+1.10%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **ROBI** | 0.33% | 0.415% | 0.14% | **0.03%** | 0.58% | **+1.16%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **BATBC** | 0.35% | 0.415% | 0.90% | **0.05%** | 1.36% | **+2.72%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **GP** | 0.42% | 0.415% | 0.28% | **0.03%** | 0.73% | **+1.46%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **BSRMLTD** | 0.62% | 0.415% | 0.05% | **0.10%** | 0.56% | **+1.13%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **MPETROLEUM** | 0.69% | 0.415% | 0.16% | **0.04%** | 0.61% | **+1.22%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **RENATA** | 0.82% | 0.415% | 0.05% | **0.05%** | 0.51% | **+1.03%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **OLYMPIC** | 0.92% | 0.415% | 0.12% | **0.08%** | 0.62% | **+1.25%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **WALTONHIL** | 1.15% | 0.415% | 0.40% | **0.05%** | 0.87% | **+1.74%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **PADMAOIL** | 1.44% | 0.415% | 0.08% | **0.04%** | 0.54% | **+1.07%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **CONFIDCEM** | 1.49% | 0.415% | 1.23% | **0.13%** | 1.77% | **+3.54%** | SINGLE_TRANCHE (Retail order < ৳100k; safe ex... |
| **JAMUNAOIL** | 3.77% | 0.415% | 0.12% | **0.12%** | 0.66% | **+1.32%** | SPLIT into 2 tranches of ~৳25000.00 each to c... |
