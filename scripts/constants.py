"""
scripts/constants.py — Canonical Institutional Quantitative Constants & Fee Manifest

Defines system-wide statutory trading frictions, macroeconomic benchmarks,
and microstructural parameters enforcing SPEC.md invariants.
"""

# ------------------------------------------------------------------------------
# 1. Frontier Microstructure Trading Frictions (INV-4)
# ------------------------------------------------------------------------------
# Statutory Buy Commission: Broker (0.40%) + CDBL (0.015%) = 0.415%
FEE_BUY_PCT: float = 0.00415

# Statutory Sell Commission: Broker (0.40%) + CDBL (0.015%) + Govt AIT Section 53BBB (0.05%) = 0.465%
FEE_SELL_PCT: float = 0.00465

# Exact Combined Round-Trip Commission Friction: 0.415% + 0.465% = 0.880%
FEE_ROUNDTRIP_PCT: float = 0.00880

# Exact Break-Even Multiplier: (1 + 0.00415) / (1 - 0.00465) = ~1.008856
BREAK_EVEN_MULTIPLIER: float = (1.0 + FEE_BUY_PCT) / (1.0 - FEE_SELL_PCT)

# Default Market Impact Slippage (basis points)
DEFAULT_SLIPPAGE_BPS: float = 10.0


# ------------------------------------------------------------------------------
# 2. Central Bank Macroeconomic Hurdles (INV-2)
# ------------------------------------------------------------------------------
# Minimum Institutional Risk-Free Benchmark: 91-Day Bangladesh Bank T-Bill Auction Rate
BENCHMARK_91D_TBILL_PCT: float = 11.60

# Minimum Required Equity Risk Premium (ERP)
MIN_EQUITY_RISK_PREMIUM_PCT: float = 3.50

# Minimum Absolute Equity Hurdle Rate (T-Bill + ERP)
MIN_EQUITY_HURDLE_PCT: float = BENCHMARK_91D_TBILL_PCT + MIN_EQUITY_RISK_PREMIUM_PCT  # 15.10%


# ------------------------------------------------------------------------------
# 3. Solvency & Shariah Thresholds (INV-3)
# ------------------------------------------------------------------------------
MAX_DEBT_TO_EQUITY: float = 0.80
MAX_STRICT_DEBT_TO_EQUITY: float = 0.50
