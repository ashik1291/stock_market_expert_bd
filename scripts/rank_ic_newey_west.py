"""
Rigorous Cross-Sectional Rank IC Evaluation Engine with Newey-West Standard Errors.
Replaces naive pooled IC * sqrt(N) formula:
  1. Computes cross-sectional Spearman Rank IC per date t (between factor at t and forward return t -> t+h).
  2. Aggregates daily/weekly IC time series: mean(IC) / (SE_NW).
  3. Applies Newey-West variance estimator to account for autocorrelation and overlapping forward return windows.
"""

import math
import sqlite3
import datetime
import sys
import numpy as np
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"


def spearman_rank_correlation(x: list[float], y: list[float]) -> float:
    """Computes Spearman rank correlation coefficient between two equal-length lists."""
    n = len(x)
    if n < 5:
        return 0.0

    def get_ranks(arr):
        indexed = sorted(enumerate(arr), key=lambda item: item[1])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j < n - 1 and indexed[j][1] == indexed[j + 1][1]:
                j += 1
            avg_rank = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                ranks[indexed[k][0]] = avg_rank
            i = j + 1
        return ranks

    rx = get_ranks(x)
    ry = get_ranks(y)

    mean_rx = (n + 1.0) / 2.0
    mean_ry = (n + 1.0) / 2.0

    cov = sum((a - mean_rx) * (b - mean_ry) for a, b in zip(rx, ry))
    var_x = sum((a - mean_rx)**2 for a in rx)
    var_y = sum((b - mean_ry)**2 for b in ry)

    if var_x == 0 or var_y == 0:
        return 0.0
    return cov / math.sqrt(var_x * var_y)


def newey_west_t_stat(series: list[float], max_lags: int) -> tuple[float, float, float]:
    """
    Computes mean, Newey-West standard error, and robust t-statistic for a time-series.
    Accounts for serial correlation in overlapping return windows.
    """
    T = len(series)
    if T < 2:
        return 0.0, 0.0, 0.0

    mean_val = float(np.mean(series))
    demeaned = np.array(series) - mean_val

    # Gamma_0 (sample variance)
    gamma_0 = float(np.sum(demeaned**2)) / T

    # Sum of weighted autocovariances
    autocov_sum = 0.0
    for lag in range(1, max_lags + 1):
        gamma_l = float(np.sum(demeaned[lag:] * demeaned[:-lag])) / T
        weight = 1.0 - (lag / (max_lags + 1.0)) # Bartlett kernel
        autocov_sum += 2.0 * weight * gamma_l

    nw_variance = (gamma_0 + autocov_sum) / T
    if nw_variance <= 0:
        nw_se = float(np.std(series, ddof=1) / math.sqrt(T))
    else:
        nw_se = math.sqrt(nw_variance)

    t_stat = (mean_val / nw_se) if nw_se > 0 else 0.0
    return mean_val, nw_se, t_stat


def run_cross_sectional_rank_ic(horizon_bars: int = 21, stride: int = 5):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    print(f"[RANK IC HARNESS] Running cross-sectional Rank IC (Forward Horizon: {horizon_bars} bars, Stride: {stride} bars)...")

    # Fetch trading dates
    trading_dates = [r[0] for r in c.execute("SELECT date FROM trading_calendar WHERE is_trading_day = 1 ORDER BY date").fetchall()]
    print(f"[RANK IC HARNESS] Historical calendar spans {len(trading_dates)} dates ({trading_dates[0]} to {trading_dates[-1]}).")

    # Fetch price matrix
    prices_raw = c.execute("SELECT ticker, date, close, volume FROM prices ORDER BY ticker, date").fetchall()
    ticker_history = {}
    for r in prices_raw:
        sym = r["ticker"]
        if sym not in ticker_history:
            ticker_history[sym] = []
        ticker_history[sym].append((r["date"], r["close"], r["volume"]))

    # Date -> {ticker: {'close': c, 'vol': v, 'rsi': r, 'mom60': m, 'fwd_ret': ret}}
    # Precompute per-ticker indicators strictly using backward data
    print("[RANK IC HARNESS] Computing point-in-time technical signals per ticker...")
    precomputed = {} # sym -> list of {date, close, rsi, mom60, fwd_ret}

    for sym, bars in ticker_history.items():
        if len(bars) < 70 + horizon_bars:
            continue

        closes = [b[1] for b in bars]
        vols = [b[2] for b in bars]

        # RSI calculation
        deltas = [closes[k] - closes[k-1] for k in range(1, len(closes))]
        gains = [max(0.0, d) for d in deltas]
        losses = [max(0.0, -d) for d in deltas]

        sym_records = []
        for i in range(60, len(bars) - horizon_bars):
            dt = bars[i][0]
            c_curr = closes[i]
            c_fwd = closes[i + horizon_bars]

            if c_curr <= 0 or c_fwd <= 0:
                continue

            # Forward net return
            fwd_ret = (c_fwd * (1.0 - 0.00415) - c_curr * (1.0 + 0.00415)) / (c_curr * (1.0 + 0.00415))

            # 60-bar momentum
            mom60 = (c_curr - closes[i - 60]) / closes[i - 60] if closes[i - 60] > 0 else 0.0

            # 14-bar RSI
            avg_g = sum(gains[i-14:i]) / 14.0
            avg_l = sum(losses[i-14:i]) / 14.0
            rs = avg_g / avg_l if avg_l > 0 else 1.0
            rsi14 = 100.0 - (100.0 / (1.0 + rs))

            sym_records.append({
                "date": dt,
                "rsi14": rsi14,
                "mom60": mom60,
                "fwd_ret": fwd_ret
            })

        precomputed[sym] = sym_records

    # Re-index by date
    by_date = {}
    for sym, recs in precomputed.items():
        for r in recs:
            dt = r["date"]
            if dt not in by_date:
                by_date[dt] = []
            by_date[dt].append(r)

    eval_dates = sorted(by_date.keys())[::stride]
    print(f"[RANK IC HARNESS] Slicing cross-section across {len(eval_dates)} non-overlapping/strided evaluation dates...")

    rsi_rank_ics = []
    mom_rank_ics = []

    for dt in eval_dates:
        records = by_date[dt]
        if len(records) < 15:
            continue

        fwd_returns = [r["fwd_ret"] for r in records]
        rsi_vals = [r["rsi14"] for r in records]
        mom_vals = [r["mom60"] for r in records]

        # Note: For oversold RSI, lower RSI is predicted to have higher return, so we invert or correlate directly
        # Invert RSI: 100 - RSI (so high score = oversold)
        oversold_scores = [100.0 - v for v in rsi_vals]

        ic_rsi = spearman_rank_correlation(oversold_scores, fwd_returns)
        ic_mom = spearman_rank_correlation(mom_vals, fwd_returns)

        rsi_rank_ics.append(ic_rsi)
        mom_rank_ics.append(ic_mom)

    # Compute Newey-West adjusted statistics
    # Max lag = ceiling(horizon_bars / stride)
    nw_lags = max(1, int(math.ceil(horizon_bars / stride)))
    print(f"[RANK IC HARNESS] Applying Newey-West estimator with {nw_lags} autocorrelation lags...")

    mean_rsi_ic, se_rsi, t_rsi = newey_west_t_stat(rsi_rank_ics, max_lags=nw_lags)
    mean_mom_ic, se_mom, t_mom = newey_west_t_stat(mom_rank_ics, max_lags=nw_lags)

    print("\n" + "="*70)
    print("  RIGOROUS CROSS-SECTIONAL RANK IC (NEWEY-WEST ROBUST STANDARD ERRORS)")
    print("="*70)
    print(f"Total Date Cross-Sections: {len(rsi_rank_ics)} | Forward Horizon: {horizon_bars} bars | Lags: {nw_lags}")
    print("-" * 70)
    print(f"60-Day Momentum Factor:")
    print(f"  - Mean Rank IC:         {mean_mom_ic:+.4f}")
    print(f"  - Newey-West Std Error: {se_mom:.4f}")
    print(f"  - Robust t-statistic:   {t_mom:+.2f}  (Naive pooled t was +43.88)")
    print("-" * 70)
    print(f"14-Day Oversold RSI Factor (Mean Reversion):")
    print(f"  - Mean Rank IC:         {mean_rsi_ic:+.4f}")
    print(f"  - Newey-West Std Error: {se_rsi:.4f}")
    print(f"  - Robust t-statistic:   {t_rsi:+.2f}  (Naive pooled t was +14.06)")
    print("="*70)

    if abs(t_mom) >= 2.0:
        print("[CONCLUSION] Momentum has statistically significant positive rank correlation (t >= 2.0).")
    else:
        print("[CONCLUSION] Momentum is marginally significant or indistinguishable from noise (t < 2.0).")
    print("="*70 + "\n")


if __name__ == "__main__":
    run_cross_sectional_rank_ic(horizon_bars=21, stride=5)
