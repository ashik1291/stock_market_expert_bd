"""
Before/after evaluation of feature-input corrections (Tier 3) on identical dates and forward returns.

v1 = features_daily as currently stored in the live DB (stored P/E and yield from the latest scrape row, today's
category list, bonus-only price adjustment). v2 = features rebuilt on a private copy with the corrected
feature_store (P/E = close / published annual EPS, trailing-year official cash-dividend yield, field-wise PIT D/E,
point-in-time category and survivorship-free universe, all price-affecting actions adjusted).

Selection IC per date and horizon follows model_registry._forward_ic (gated names tied below every eligible name,
corporate-action windows excluded). Reported: mean IC, t-stat, hit rate, on each version's own universe and on the
tickers common to both. Writes reports/research/feature_inputs_v1_vs_v2.json.

Usage: python scripts/research_feature_inputs_eval.py
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import statistics
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import feature_store as fs  # noqa: E402
from model_registry import CA_PRICE_EVENTS  # noqa: E402
from rank_ic_newey_west import spearman_rank_correlation  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"
OUT = BASE_DIR / "reports" / "research" / "feature_inputs_v1_vs_v2.json"
HORIZONS = (1, 5, 21)


def scores_for(conn, d):
    return {t: (s if e else None) for t, s, e in conn.execute(
        "SELECT ticker, score, is_eligible FROM features_daily WHERE date = ?", (d,))}


def forward_ic(conn, sessions, i, scores, h, restrict=None):
    if i + h >= len(sessions):
        return None
    d, nd = sessions[i], sessions[i + h]
    sc = {t: v for t, v in scores.items() if restrict is None or t in restrict}
    live = [v for v in sc.values() if v is not None]
    if not live:
        return None
    floor = min(live) - 1.0
    ph = ",".join("?" * len(CA_PRICE_EVENTS))
    excluded = {r[0] for r in conn.execute(
        f"SELECT DISTINCT ticker FROM corporate_actions WHERE record_date BETWEEN ? AND ? AND action_type IN ({ph})",
        (d, nd, *CA_PRICE_EVENTS))}
    base = dict(conn.execute("SELECT ticker, close FROM prices WHERE date = ?", (d,)).fetchall())
    fwd = dict(conn.execute("SELECT ticker, close FROM prices WHERE date = ?", (nd,)).fetchall())
    xs, ys = [], []
    for t, v in sc.items():
        c0, c1 = base.get(t), fwd.get(t)
        if t in excluded or not c0 or not c1 or c0 <= 0:
            continue
        xs.append(v if v is not None else floor)
        ys.append(c1 / c0 - 1.0)
    return spearman_rank_correlation(xs, ys) if len(xs) >= 15 else None


def summarize(ics):
    ics = [x for x in ics if x is not None and not math.isnan(x)]
    if len(ics) < 3:
        return {"n": len(ics)}
    m, sd = statistics.mean(ics), statistics.stdev(ics)
    return {"n": len(ics), "mean_ic": round(m, 5), "t_stat": round(m / (sd / math.sqrt(len(ics))), 3) if sd else None,
            "hit_rate": round(sum(1 for x in ics if x > 0) / len(ics), 3)}


def main():
    live = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    dates = [r[0] for r in live.execute("SELECT DISTINCT date FROM features_daily ORDER BY date")]
    v1 = {d: scores_for(live, d) for d in dates}
    tmp = os.path.join(tempfile.mkdtemp(prefix="feat_eval_"), "dse.db")
    dst = sqlite3.connect(tmp)
    live.backup(dst)
    dst.close()
    live.close()
    fs.DB_PATH = Path(tmp)
    for d in dates:
        fs.build_features_for_date(d)
    conn = sqlite3.connect(tmp)
    v2 = {d: scores_for(conn, d) for d in dates}
    sessions = [r[0] for r in conn.execute(
        "SELECT DISTINCT p.date FROM prices p JOIN trading_calendar t ON t.date = p.date AND t.is_trading_day = 1 "
        "WHERE p.date >= ? ORDER BY p.date", (dates[0],))]
    pos = {d: i for i, d in enumerate(sessions)}
    report = {"dates": [dates[0], dates[-1], len(dates)], "horizons": {}}
    for h in HORIZONS:
        res = {"v1_own": [], "v2_own": [], "v1_common": [], "v2_common": []}
        for d in dates:
            if d not in pos:
                continue
            common = set(v1[d]) & set(v2[d])
            res["v1_own"].append(forward_ic(conn, sessions, pos[d], v1[d], h))
            res["v2_own"].append(forward_ic(conn, sessions, pos[d], v2[d], h))
            res["v1_common"].append(forward_ic(conn, sessions, pos[d], v1[d], h, common))
            res["v2_common"].append(forward_ic(conn, sessions, pos[d], v2[d], h, common))
        report["horizons"][h] = {k: summarize(v) for k, v in res.items()}
    report["eligible_per_day"] = {"v1": round(statistics.mean(sum(1 for v in v1[d].values() if v is not None) for d in dates), 2),
                                  "v2": round(statistics.mean(sum(1 for v in v2[d].values() if v is not None) for d in dates), 2)}
    report["universe_per_day"] = {"v1": round(statistics.mean(len(v1[d]) for d in dates), 1),
                                  "v2": round(statistics.mean(len(v2[d]) for d in dates), 1)}
    conn.close()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
