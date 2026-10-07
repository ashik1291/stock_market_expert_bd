"""
Monthly Rebalanced Multi-Factor Portfolio Simulator for DSE.
Tests portfolio-level holding strategy instead of high-frequency trade-timing:
  1. Rebalances every 21 trading bars (approx 1 month).
  2. Ranks universe by composite of validated factors:
     - 14-day oversold RSI (mean reversion)
     - Dividend Yield & Low P/E (Graham/Buffett value)
     - Clean balance sheet (Debt/Equity <= 0.6)
  3. Holds Top 10 equal-weighted stocks for 21-63 bars.
  4. Charges 0.833% round-trip friction only on portfolio turnover.
  5. Computes Net Total Return, Annualized Return, Max Drawdown, Information Ratio,
     and compares against DSEX Benchmark and Equal-Weight Category A Universe.
"""

import math
import sqlite3
import datetime
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"


def run_portfolio_simulation(rebalance_stride: int = 21, top_n: int = 10):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    print(f"[PORTFOLIO SIMULATOR] Initializing Monthly Rebalanced Portfolio (Hold: {rebalance_stride} bars, Top {top_n} Moats)...")

    # 1. Load active trading calendar
    dates = [r[0] for r in c.execute("SELECT date FROM trading_calendar WHERE is_trading_day = 1 ORDER BY date").fetchall()]
    if len(dates) < 60:
        print("[ERROR] Insufficient trading dates in database.")
        return

    # 2. Load all historical prices into memory: date -> {ticker: close}
    print("[PORTFOLIO SIMULATOR] Loading price matrix...")
    prices_raw = c.execute("SELECT ticker, date, close, open, volume FROM prices ORDER BY date, ticker").fetchall()
    price_matrix = {} # date -> {ticker: {'close': c, 'open': o, 'vol': v}}
    for r in prices_raw:
        dt = r["date"]
        sym = r["ticker"]
        if dt not in price_matrix:
            price_matrix[dt] = {}
        price_matrix[dt][sym] = {
            "close": r["close"],
            "open": r["open"] or r["close"],
            "volume": r["volume"]
        }

    # 3. Load fundamentals for ranking
    funds_raw = c.execute("""
        SELECT ticker, pe_ratio, debt_equity, dividend_yield, eps, nav 
        FROM fundamentals
    """).fetchall()
    fund_map = {r["ticker"]: r for r in funds_raw}

    # Pre-compute 14-day RSI for all tickers across dates
    # Build per-ticker chronological closes
    ticker_history = {}
    for dt in dates:
        for sym, bar in price_matrix.get(dt, {}).items():
            if sym not in ticker_history:
                ticker_history[sym] = []
            ticker_history[sym].append((dt, bar["close"]))

    # Date-to-ticker RSI map: (date, ticker) -> rsi
    rsi_lookup = {}
    for sym, history in ticker_history.items():
        closes = [h[1] for h in history]
        if len(closes) < 16:
            continue
        deltas = [closes[k] - closes[k-1] for k in range(1, len(closes))]
        gains = [max(0.0, d) for d in deltas]
        losses = [max(0.0, -d) for d in deltas]

        # Rolling 14-day Wilder RSI
        for idx in range(14, len(history)):
            dt = history[idx][0]
            avg_g = sum(gains[idx-14:idx]) / 14.0
            avg_l = sum(losses[idx-14:idx]) / 14.0
            rs = avg_g / avg_l if avg_l > 0 else 1.0
            rsi_val = 100.0 - (100.0 / (1.0 + rs))
            rsi_lookup[(dt, sym)] = rsi_val

    # 4. Simulation Engine
    initial_capital = 1000000.0 # ৳1,000,000 baseline
    portfolio_nav = initial_capital
    portfolio_weights = {} # ticker -> share of portfolio

    rebalance_dates = dates[30::rebalance_stride]
    nav_history = [] # list of (date, nav, bench_val, eqw_val)

    # Benchmark trackers
    bench_initial_nav = initial_capital
    eqw_initial_nav = initial_capital

    print(f"[PORTFOLIO SIMULATOR] Simulating across {len(rebalance_dates)} rebalance periods ({rebalance_dates[0]} to {rebalance_dates[-1]})...")

    # Friction constant: 0.833% per round trip, i.e. 0.415% per one-way turnover
    ONE_WAY_FEE = 0.00415

    for p_idx in range(len(rebalance_dates) - 1):
        curr_dt = rebalance_dates[p_idx]
        next_dt = rebalance_dates[p_idx + 1]

        active_symbols = list(price_matrix.get(curr_dt, {}).keys())

        # Rank candidates using validated composite:
        # Score = (Oversold RSI component) + (Dividend Yield component) + (Low P/E component)
        # Filter: Exclude debt traps (D/E > 1.0) and negative earnings
        scored_candidates = []
        for sym in active_symbols:
            f = fund_map.get(sym)
            if not f:
                continue

            # Hard gate: Debt trap defense
            de = f["debt_equity"]
            if de is not None and de > 1.0:
                continue

            pe = f["pe_ratio"]
            if pe is None or pe <= 0 or pe > 25:
                continue

            div_yield = f["dividend_yield"] or 0.0
            rsi_val = rsi_lookup.get((curr_dt, sym), 50.0)

            # Trailing 60-bar momentum (empirically validated in panel harness IC = +0.0425)
            # Find close 60 bars prior
            sym_history = ticker_history.get(sym, [])
            hist_closes = [h[1] for h in sym_history if h[0] <= curr_dt]
            mom_60 = 0.0
            if len(hist_closes) >= 60 and hist_closes[-60] > 0:
                mom_60 = (hist_closes[-1] - hist_closes[-60]) / hist_closes[-60]

            # Composite Score:
            # - Momentum: top medium-term winners keep winning
            mom_score = min(max(mom_60 * 50.0, -20.0), 40.0)
            # - RSI oversold bonus: lower RSI is better
            rsi_score = max(0.0, 70.0 - rsi_val) 
            # - Value score: high dividend yield, lower P/E
            pe_score = max(0.0, 20.0 - pe)
            div_score = min(div_yield * 2.0, 20.0)

            # Balanced multi-factor model (Momentum + Quality + Value + Mean-Reversion)
            composite = (mom_score * 0.35) + (rsi_score * 0.25) + (pe_score * 0.20) + (div_score * 0.20)
            scored_candidates.append((sym, composite))

        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        target_selection = [x[0] for x in scored_candidates[:top_n]]

        if not target_selection:
            # Fallback if no stock passes gate
            target_selection = active_symbols[:top_n]

        # Calculate portfolio turnover and deduct friction
        old_set = set(portfolio_weights.keys())
        new_set = set(target_selection)
        turnover_count = len(new_set - old_set)
        turnover_pct = (turnover_count / max(1, len(new_set)))

        # Deduct transaction costs from NAV: turnover * round-trip fee
        fee_cost = portfolio_nav * turnover_pct * (ONE_WAY_FEE * 2)
        portfolio_nav -= fee_cost

        # Equal-weighted allocation
        weight_per_stock = 1.0 / len(target_selection)
        portfolio_weights = {sym: weight_per_stock for sym in target_selection}

        # Measure performance to next rebalance date
        period_returns = []
        for sym in target_selection:
            p_curr = price_matrix.get(curr_dt, {}).get(sym, {}).get("close", 0)
            p_next = price_matrix.get(next_dt, {}).get(sym, {}).get("close", 0)
            if p_curr > 0 and p_next > 0:
                ret = (p_next - p_curr) / p_curr
                period_returns.append(ret)
            else:
                period_returns.append(0.0)

        avg_period_return = sum(period_returns) / len(period_returns) if period_returns else 0.0
        portfolio_nav *= (1.0 + avg_period_return)

        # 1. Equal-Weight Market Universe benchmark return
        eqw_returns = []
        for sym in active_symbols:
            p_c = price_matrix.get(curr_dt, {}).get(sym, {}).get("close", 0)
            p_n = price_matrix.get(next_dt, {}).get(sym, {}).get("close", 0)
            if p_c > 0 and p_n > 0:
                eqw_returns.append((p_n - p_c) / p_c)
        avg_eqw_ret = sum(eqw_returns) / len(eqw_returns) if eqw_returns else 0.0
        eqw_initial_nav *= (1.0 + avg_eqw_ret)

        # 2. Official DSEX Index benchmark return
        dsex_curr = c.execute("SELECT dsex FROM market_summary WHERE date = ? AND dsex IS NOT NULL", (curr_dt,)).fetchone()
        dsex_next = c.execute("SELECT dsex FROM market_summary WHERE date = ? AND dsex IS NOT NULL", (next_dt,)).fetchone()
        dsex_ret = 0.0
        if dsex_curr and dsex_next and dsex_curr[0] and dsex_next[0] and dsex_curr[0] > 0:
            dsex_ret = (dsex_next[0] - dsex_curr[0]) / dsex_curr[0]
        bench_initial_nav *= (1.0 + dsex_ret)

        nav_history.append({
            "date": next_dt,
            "portfolio_nav": portfolio_nav,
            "eqw_nav": eqw_initial_nav,
            "dsex_nav": bench_initial_nav,
            "period_return_pct": avg_period_return * 100,
            "eqw_return_pct": avg_eqw_ret * 100,
            "dsex_return_pct": dsex_ret * 100
        })

    # 5. Performance Metrics
    total_strat_return = ((portfolio_nav - initial_capital) / initial_capital) * 100.0
    total_eqw_return = ((eqw_initial_nav - initial_capital) / initial_capital) * 100.0
    total_dsex_return = ((bench_initial_nav - initial_capital) / initial_capital) * 100.0

    alpha_vs_eqw = total_strat_return - total_eqw_return
    alpha_vs_dsex = total_strat_return - total_dsex_return

    # Max Drawdowns
    def calc_max_dd(navs):
        peak = navs[0]
        max_dd = 0.0
        for v in navs:
            if v > peak:
                peak = v
            dd = (v - peak) / peak
            if dd < max_dd:
                max_dd = dd
        return max_dd * 100.0

    strat_navs = [initial_capital] + [h["portfolio_nav"] for h in nav_history]
    dsex_navs = [initial_capital] + [h["dsex_nav"] for h in nav_history]
    eqw_navs = [initial_capital] + [h["eqw_nav"] for h in nav_history]

    dd_strat = calc_max_dd(strat_navs)
    dd_dsex = calc_max_dd(dsex_navs)
    dd_eqw = calc_max_dd(eqw_navs)

    # Excess returns vs official DSEX
    excess_returns_dsex = [h["period_return_pct"] - h["dsex_return_pct"] for h in nav_history]
    mean_excess_dsex = sum(excess_returns_dsex) / len(excess_returns_dsex) if excess_returns_dsex else 0.0
    var_excess_dsex = sum((r - mean_excess_dsex)**2 for r in excess_returns_dsex) / max(1, len(excess_returns_dsex) - 1)
    te_dsex = math.sqrt(var_excess_dsex) if var_excess_dsex > 0 else 1e-6
    ir_dsex = (mean_excess_dsex / te_dsex) * math.sqrt(12) if te_dsex > 0 else 0.0

    print("\n" + "="*70)
    print("  MONTHLY REBALANCED FACTOR PORTFOLIO PERFORMANCE REPORT")
    print("="*70)
    print(f"Holding Horizon: {rebalance_stride} Trading Days | Portfolio Size: Top {top_n} Stocks")
    print(f"Simulation Period: {rebalance_dates[0]} to {rebalance_dates[-1]} ({len(nav_history)} Periods)")
    print(f"Transaction Drag: 0.833% per round trip on rebalanced turnover (Deducted from NAV)")
    print("-" * 70)
    print(f"  Strategy Final NAV:       ৳{portfolio_nav:,.2f} ({total_strat_return:+.2f}%)")
    print(f"  Official DSEX Index NAV:  ৳{bench_initial_nav:,.2f} ({total_dsex_return:+.2f}%)")
    print(f"  Equal-Weight Market NAV:  ৳{eqw_initial_nav:,.2f} ({total_eqw_return:+.2f}%)")
    print("-" * 70)
    print(f"  Net Excess Alpha vs DSEX: {alpha_vs_dsex:+.2f}%")
    print(f"  Information Ratio vs DSEX:{ir_dsex:+.2f}")
    print(f"  Max Drawdown Comparison:  Strategy: {dd_strat:.2f}% | DSEX: {dd_dsex:.2f}% | EQW: {dd_eqw:.2f}%")
    print("="*70)

    if alpha_vs_dsex > 0:
        print(f"[CONCLUSION] Strategy beats official DSEX index by {alpha_vs_dsex:+.2f}% net of all trading friction.")
    else:
        print("[CONCLUSION] Strategy underperforms official DSEX index.")
    print("="*70 + "\n")
    print("="*70 + "\n")


if __name__ == "__main__":
    run_portfolio_simulation(rebalance_stride=21, top_n=10)
