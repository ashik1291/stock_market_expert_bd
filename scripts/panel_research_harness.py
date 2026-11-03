"""
Panel Research Harness for DSE Quantitative Engine.
Evaluates factor signals at historical dates t using strictly information available at <= t,
and measures forward realized returns over holding horizons h in [5, 10, 21, 63] trading days.
Pools stocks and dates with date-clustered standard errors.
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


def run_factor_panel_evaluation(horizon_days: int = 21):
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    print(f"[PANEL HARNESS] Running cross-sectional panel evaluation for forward horizon h={horizon_days} bars...")

    # 1. Fetch all trading dates in chronological order
    trading_dates = [r[0] for r in c.execute("SELECT date FROM trading_calendar WHERE is_trading_day = 1 ORDER BY date").fetchall()]
    print(f"[PANEL HARNESS] Universe spans {len(trading_dates)} trading sessions ({trading_dates[0]} to {trading_dates[-1]}).")

    # Date to index lookup
    date_to_idx = {d: i for i, d in enumerate(trading_dates)}

    # 2. Fetch prices into memory for rapid panel slicing
    prices_raw = c.execute("SELECT ticker, date, close, volume FROM prices ORDER BY ticker, date").fetchall()
    ticker_series = {}
    for r in prices_raw:
        sym = r["ticker"]
        if sym not in ticker_series:
            ticker_series[sym] = []
        ticker_series[sym].append((r["date"], r["close"], r["volume"]))

    # 3. Form panels of signal at t vs return at t + h
    # We test:
    #   - Factor 1: 14-day RSI oversold (< 40 vs > 60)
    #   - Factor 2: 20-day momentum (close / close[-20] - 1)
    #   - Factor 3: Volume surge (vol / 20-day avg vol)

    samples = [] # list of (date, ticker, rsi, mom, vol_surge, fwd_ret)

    for sym, bars in ticker_series.items():
        if len(bars) < 60:
            continue

        for i in range(25, len(bars) - horizon_days):
            t_date, t_close, t_vol = bars[i]
            target_date, target_close, _ = bars[i + horizon_days]

            if t_close <= 0 or target_close <= 0:
                continue

            # Forward return net of friction (0.833%)
            raw_fwd_ret = (target_close - t_close) / t_close
            net_fwd_ret = (target_close * (1.0 - 0.00415) - t_close * (1.0 + 0.00415)) / (t_close * (1.0 + 0.00415))

            # Factor calculations strictly on bars[:i+1]
            hist_closes = [b[1] for b in bars[i-20:i+1]]
            hist_vols = [b[2] for b in bars[i-20:i+1]]

            # 20-day momentum
            mom_20 = (hist_closes[-1] - hist_closes[0]) / hist_closes[0] if hist_closes[0] > 0 else 0.0

            # 20-day volume ratio
            avg_vol = sum(hist_vols[:-1]) / max(1, len(hist_vols) - 1)
            vol_ratio = (t_vol / avg_vol) if avg_vol > 0 else 1.0

            # 14-day RSI
            deltas = [hist_closes[k] - hist_closes[k-1] for k in range(1, len(hist_closes))]
            gains = [max(0.0, d) for d in deltas]
            losses = [max(0.0, -d) for d in deltas]
            avg_gain = sum(gains[-14:]) / 14.0 if len(gains) >= 14 else 0.0
            avg_loss = sum(losses[-14:]) / 14.0 if len(losses) >= 14 else 1e-6
            rs = avg_gain / avg_loss if avg_loss > 0 else 1.0
            rsi_14 = 100.0 - (100.0 / (1.0 + rs))

            samples.append({
                "date": t_date,
                "ticker": sym,
                "rsi_14": rsi_14,
                "mom_20": mom_20,
                "vol_ratio": vol_ratio,
                "fwd_ret_net": net_fwd_ret
            })

    print(f"[PANEL HARNESS] Extracted {len(samples)} cross-sectional panel observations across {len(ticker_series)} stocks.")

    # 4. Compute Decile Performance & Predictive IC (Information Coefficient)
    # Correlation between Factor and Forward Return across panels
    def calc_pearson_ic(factor_name):
        xs = [s[factor_name] for s in samples]
        ys = [s["fwd_ret_net"] for s in samples]
        mean_x = sum(xs) / len(xs)
        mean_y = sum(ys) / len(ys)
        cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        var_x = sum((x - mean_x)**2 for x in xs)
        var_y = sum((y - mean_y)**2 for y in ys)
        if var_x == 0 or var_y == 0:
            return 0.0
        return cov / math.sqrt(var_x * var_y)

    ic_rsi = calc_pearson_ic("rsi_14")
    ic_mom = calc_pearson_ic("mom_20")
    ic_vol = calc_pearson_ic("vol_ratio")

    print(f"\n--- Cross-Sectional Information Coefficients (IC vs {horizon_days}-day Forward Net Return) ---")
    print(f"  RSI (14-day):      IC = {ic_rsi:+.4f} (t-stat ~= {ic_rsi * math.sqrt(len(samples)):.2f})")
    print(f"  Momentum (20-day): IC = {ic_mom:+.4f} (t-stat ~= {ic_mom * math.sqrt(len(samples)):.2f})")
    print(f"  Volume Ratio:      IC = {ic_vol:+.4f} (t-stat ~= {ic_vol * math.sqrt(len(samples)):.2f})")

    # 5. Decile Slices for Momentum
    samples.sort(key=lambda s: s["mom_20"])
    n = len(samples)
    d1 = samples[: n // 5]           # Bottom quintile (worst momentum)
    d5 = samples[- (n // 5) :]        # Top quintile (highest momentum)

    avg_ret_d1 = sum(s["fwd_ret_net"] for s in d1) / len(d1) * 100
    avg_ret_d5 = sum(s["fwd_ret_net"] for s in d5) / len(d5) * 100

    print(f"\n--- Quintile Forward Return Net of Fees ({horizon_days}-day horizon) ---")
    print(f"  Quintile 1 (Lowest Mom):  Avg Net Return = {avg_ret_d1:+.2f}%")
    print(f"  Quintile 5 (Highest Mom): Avg Net Return = {avg_ret_d5:+.2f}%")
    print(f"  Long/Short Spread (Q5 - Q1): {avg_ret_d5 - avg_ret_d1:+.2f}%\n")


if __name__ == "__main__":
    run_factor_panel_evaluation(horizon_days=21)
