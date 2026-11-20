"""
Survivorship / look-ahead bias check for the backtester universe (Tier 3).

Runs the institutional backtest twice with identical parameters:
  biased = the old universe: today's Category A ranked by today's market cap (fixed list for all history)
  pit    = the point-in-time monthly liquidity universe (instrument_master.liquidity_schedule)
and writes reports/research/universe_bias_eval.json with both results side by side.

Usage: python scripts/research_universe_bias_eval.py [--start 2023-01-01]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backtester as bt  # noqa: E402
from unified_score import is_shariah_excluded_company  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
OUT = BASE_DIR / "reports" / "research" / "universe_bias_eval.json"
KEYS = ("net_return_pct", "total_dividends_bdt", "max_drawdown_pct", "annualized_sharpe_ratio", "total_trades", "wins",
        "losses", "win_rate_pct", "profit_factor")


def biased_universe(conn) -> list[str]:
    rows = conn.execute("""SELECT ticker, sector FROM companies WHERE category = 'A' AND ticker NOT LIKE '%BOND%'
                           ORDER BY market_cap_cr DESC""").fetchall()
    return [t for t, sec in rows if not is_shariah_excluded_company(sec, ticker=t)][:20]


def pick(res: dict) -> dict:
    flat = dict(res)
    for k in ("metrics", "summary", "performance"):
        if isinstance(res.get(k), dict):
            flat.update(res[k])
    return {k: flat.get(k) for k in KEYS if k in flat} or {k: v for k, v in flat.items() if not isinstance(v, (list, dict))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2023-01-01")
    args = ap.parse_args()
    conn = sqlite3.connect(f"file:{bt.DB_PATH}?mode=ro", uri=True)
    biased = biased_universe(conn)
    conn.close()
    out = {"start": args.start, "biased_universe": biased}
    out["biased"] = pick(bt.simulate_institutional_backtest(start_date=args.start, tickers=biased, halal_tier="flexible"))
    out["point_in_time"] = pick(bt.simulate_institutional_backtest(start_date=args.start, tickers=None, halal_tier="flexible"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
