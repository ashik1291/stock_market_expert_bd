import sqlite3
import pandas as pd
import numpy as np

conn = sqlite3.connect("data/processed/dse.db", timeout=30.0)
conn.execute("PRAGMA busy_timeout = 30000;")
query = """
SELECT ticker, date, close 
FROM prices 
WHERE ticker IN ('SQURPHARMA', 'GP', 'JAMUNAOIL', 'BSRMLTD', 'LHB', 'OLYMPIC')
  AND date >= '2020-01-01'
ORDER BY date ASC
"""
prices = pd.read_sql(query, conn)

# Also fetch DSEX
dsex_df = pd.read_sql("SELECT date, dsex FROM market_summary WHERE date >= '2020-01-01' AND dsex IS NOT NULL ORDER BY date ASC", conn)
conn.close()

p_pivot = prices.pivot(index="date", columns="ticker", values="close").dropna()
common_dates = p_pivot.index

# 1. 6-Pillar Buy-and-Hold
start_prices = p_pivot.iloc[0]
bh_shares = 10000.0 / 6.0 / start_prices
bh_wealth = (p_pivot * bh_shares).sum(axis=1)

# 2. 6-Pillar Monthly Rebalanced (with 0.20% monthly rebalance friction)
daily_ret = p_pivot.pct_change().dropna()
cur_w = 10000.0
last_m = None
rebal_series = [10000.0]

for d in daily_ret.index:
    r = daily_ret.loc[d].mean()
    cur_w *= (1.0 + r)
    if d[:7] != last_m:
        cur_w *= (1.0 - 0.002)  # 0.20% friction on rebalance turnover
        last_m = d[:7]
    rebal_series.append(cur_w)

rebal_wealth = pd.Series(rebal_series, index=p_pivot.index)

# 3. DSEX Index Benchmark
dsex_aligned = dsex_df.set_index("date")["dsex"].reindex(p_pivot.index).ffill()
dsex_wealth = (dsex_aligned / dsex_aligned.iloc[0]) * 10000.0

years = len(p_pivot) / 245.0
bh_cagr = ((bh_wealth.iloc[-1] / 10000.0) ** (1.0 / years) - 1.0) * 100.0
rebal_cagr = ((rebal_wealth.iloc[-1] / 10000.0) ** (1.0 / years) - 1.0) * 100.0
dsex_cagr = ((dsex_wealth.iloc[-1] / 10000.0) ** (1.0 / years) - 1.0) * 100.0

print("=" * 80)
print(f"BENCHMARK DECOMPOSITION AUDIT (2020-01-01 to 2026-10-19 | {years:.2f} Years):")
print("=" * 80)
print(f"1. 6-Pillar Buy-and-Hold:           CAGR = {bh_cagr:+.2f}% | Final = Tk {bh_wealth.iloc[-1]:,.2f}")
print(f"2. 6-Pillar Monthly Rebalanced:     CAGR = {rebal_cagr:+.2f}% | Final = Tk {rebal_wealth.iloc[-1]:,.2f}")
print(f"3. DSEX Market Index Benchmark:     CAGR = {dsex_cagr:+.2f}% | Final = Tk {dsex_wealth.iloc[-1]:,.2f}")
print("-" * 80)
print(f"Rebalanced vs Buy-and-Hold Alpha:   {rebal_cagr - bh_cagr:+.2f}%/yr (Turnover friction drag)")
print(f"6-Pillar Basket vs DSEX Alpha:      {bh_cagr - dsex_cagr:+.2f}%/yr (Quality moat selection premium)")
print("=" * 80)
