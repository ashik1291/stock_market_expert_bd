"""
Factor IC research on the corrected, survivorship-free point-in-time universe (Tier 3).

For every stored features_daily date: Spearman IC of each raw factor against forward 5- and 21-session returns
across the whole point-in-time universe (not only eligible names), excluding names with a price-affecting corporate
action inside the window. Newey-West t-statistics with lag = horizon - 1 account for overlapping windows.
Research output only — the frozen champion is not changed by this script.

Writes reports/research/factor_ic_pit.json.
Usage: python scripts/research_factor_ic.py
"""

from __future__ import annotations

import json
import math
import sqlite3
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model_registry import CA_PRICE_EVENTS  # noqa: E402
from rank_ic_newey_west import newey_west_t_stat, spearman_rank_correlation  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"
OUT = BASE_DIR / "reports" / "research" / "factor_ic_pit.json"
HORIZONS = (5, 21)
FACTORS = {
    "earnings_yield": lambda r: 100.0 / r["pe_ratio"] if r["pe_ratio"] and r["pe_ratio"] > 0 else None,
    "dividend_yield": lambda r: r["dividend_yield"],
    "neg_debt_equity": lambda r: -r["debt_equity"] if r["debt_equity"] is not None else None,
    "neg_rsi_14": lambda r: -r["rsi_14"] if r["rsi_14"] is not None else None,
    "log_traded_value_20d": lambda r: math.log(r["traded_value_20d"]) if r["traded_value_20d"] and r["traded_value_20d"] > 0 else None,
    "champion_score": lambda r: r["score"] if r["is_eligible"] else None,
}


def main():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    dates = [r[0] for r in conn.execute("SELECT DISTINCT date FROM features_daily ORDER BY date")]
    sessions = [r[0] for r in conn.execute("""SELECT DISTINCT p.date FROM prices p JOIN trading_calendar t
                                               ON t.date = p.date AND t.is_trading_day = 1 WHERE p.date >= ? ORDER BY p.date""",
                                            (dates[0],))]
    pos = {d: i for i, d in enumerate(sessions)}
    ph = ",".join("?" * len(CA_PRICE_EVENTS))
    out = {"dates": [dates[0], dates[-1], len(dates)], "universe": "point-in-time category A equities (features_daily)",
           "factors": {}}
    series = {(f, h): [] for f in FACTORS for h in HORIZONS}
    breadth = []
    for d in dates:
        rows = conn.execute("SELECT * FROM features_daily WHERE date = ?", (d,)).fetchall()
        base = {r["ticker"]: r["close"] for r in rows}
        breadth.append(len(rows))
        for h in HORIZONS:
            i = pos.get(d)
            if i is None or i + h >= len(sessions):
                continue
            nd = sessions[i + h]
            excluded = {r[0] for r in conn.execute(
                f"SELECT DISTINCT ticker FROM corporate_actions WHERE record_date > ? AND record_date <= ? AND action_type IN ({ph})",
                (d, nd, *CA_PRICE_EVENTS))}
            fwd = dict(conn.execute("SELECT ticker, close FROM prices WHERE date = ?", (nd,)).fetchall())
            rets = {t: fwd[t] / c - 1.0 for t, c in base.items() if t not in excluded and c and fwd.get(t)}
            live = [r["score"] for r in rows if r["is_eligible"]]
            floor = (min(live) - 1.0) if live else None
            for f, fn in FACTORS.items():
                if f == "champion_score":
                    pairs = [(r["score"] if r["is_eligible"] else floor, rets[r["ticker"]]) for r in rows
                             if r["ticker"] in rets and floor is not None]
                else:
                    pairs = [(fn(r), rets[r["ticker"]]) for r in rows if r["ticker"] in rets and fn(r) is not None]
                if len(pairs) >= 15:
                    xs, ys = zip(*pairs)
                    series[(f, h)].append(spearman_rank_correlation(list(xs), list(ys)))
    for f in FACTORS:
        out["factors"][f] = {}
        for h in HORIZONS:
            s = [x for x in series[(f, h)] if x is not None and not math.isnan(x)]
            if len(s) < 10:
                out["factors"][f][h] = {"n": len(s)}
                continue
            nw = newey_west_t_stat(s, max(h - 1, 1))
            out["factors"][f][h] = {"n": len(s), "mean_ic": round(statistics.mean(s), 5),
                                    "newey_west_t": round(nw[2], 3),
                                    "hit_rate": round(sum(1 for x in s if x > 0) / len(s), 3)}
    out["mean_universe_per_day"] = round(statistics.mean(breadth), 1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
