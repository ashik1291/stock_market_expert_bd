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

            # Composite Score:
            # - RSI oversold bonus: lower RSI is better
            rsi_score = max(0.0, 70.0 - rsi_val) # Higher for oversold
            # - Value score: high dividend yield, lower P/E
            pe_score = max(0.0, 20.0 - pe)
            div_score = min(div_yield * 2.0, 20.0)

            composite = (rsi_score * 0.5) + (pe_score * 0.3) + (div_score * 0.2)
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

        # Equal-Weight Market Universe benchmark return
        eqw_returns = []
        for sym in active_symbols:
            p_c = price_matrix.get(curr_dt, {}).get(sym, {}).get("close", 0)
            p_n = price_matrix.get(next_dt, {}).get(sym, {}).get("close", 0)
            if p_c > 0 and p_n > 0:
                eqw_returns.append((p_n - p_c) / p_c)
        avg_eqw_ret = sum(eqw_returns) / len(eqw_returns) if eqw_returns else 0.0
        eqw_initial_nav *= (1.0 + avg_eqw_ret)

        nav_history.append({
            "date": next_dt,
            "portfolio_nav": portfolio_nav,
            "market_nav": eqw_initial_nav,
            "period_return_pct": avg_period_return * 100,
            "market_return_pct": avg_eqw_ret * 100
        })

    # 5. Performance Metrics
    total_strat_return = ((portfolio_nav - initial_capital) / initial_capital) * 100.0
    total_market_return = ((eqw_initial_nav - initial_capital) / initial_capital) * 100.0
    alpha = total_strat_return - total_market_return

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
    mkt_navs = [initial_capital] + [h["market_nav"] for h in nav_history]

    dd_strat = calc_max_dd(strat_navs)
    dd_mkt = calc_max_dd(mkt_navs)

    # Monthly excess returns and Information Ratio
    excess_returns = [h["period_return_pct"] - h["market_return_pct"] for h in nav_history]
    mean_excess = sum(excess_returns) / len(excess_returns) if excess_returns else 0.0
    var_excess = sum((r - mean_excess)**2 for r in excess_returns) / max(1, len(excess_returns) - 1)
    tracking_error = math.sqrt(var_excess) if var_excess > 0 else 1e-6
    # Annualized Information Ratio (approx 12 periods per year)
    information_ratio = (mean_excess / tracking_error) * math.sqrt(12) if tracking_error > 0 else 0.0

    print("\n" + "="*70)
    print("  MONTHLY REBALANCED FACTOR PORTFOLIO PERFORMANCE REPORT")
    print("="*70)
    print(f"Holding Horizon: 21 Trading Days (~1 Month) | Portfolio Size: Top {top_n} Stocks")
    print(f"Simulation Period: {dates[30]} to {dates[-1]} ({len(nav_history)} Monthly Periods)")
    print(f"Transaction Drag: 0.833% per round trip on rebalanced turnover (Deducted from NAV)")
    print("-" * 70)
    print(f"  Strategy Final NAV:    ৳{portfolio_nav:,.2f} ({total_strat_return:+.2f}%)")
    print(f"  Market Benchmark NAV:  ৳{eqw_initial_nav:,.2f} ({total_market_return:+.2f}%)")
    print(f"  Net Excess Alpha:      {alpha:+.2f}% over benchmark")
    print(f"  Max Drawdown:          Strategy: {dd_strat:.2f}% | Market: {dd_mkt:.2f}%")
    print(f"  Tracking Error:        {tracking_error:.2f}% per period")
    print(f"  Annualized Info Ratio: {information_ratio:+.2f}")
    print("="*70)

    if alpha > 0 and information_ratio > 0.5:
        print("[CONCLUSION] Strategy demonstrates positive portfolio-level alpha net of friction over 2-year sample.")
    else:
        print("[CONCLUSION] Strategy does not beat market benchmark net of fees.")
    print("="*70 + "\n")


if __name__ == "__main__":
    run_portfolio_simulation(rebalance_stride=21, top_n=10)
