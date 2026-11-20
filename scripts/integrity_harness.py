"""
Phase 4 nightly integrity harness. Fail-closed exit codes:
  0 = all checks pass
  1 = one or more FAIL
  2 = harness error (DB missing etc.)
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"
PORT_DIR = BASE_DIR / "data" / "portfolio"
LEARN_DIR = BASE_DIR / "data" / "learning"
REPORT_DIR = BASE_DIR / "reports" / "integrity"
LEDGER = PORT_DIR / "forward_test_ledger_v2.json"
RANK_LOG = PORT_DIR / "universe_daily_rank_scores.jsonl"
THRESHOLDS = BASE_DIR / "config" / "thresholds.json"
IC_WEIGHTS = LEARN_DIR / "factor_ic_weights.json"
REGISTRY = LEARN_DIR / "model_registry.json"
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

# Fake defaults that must NOT appear as invented "good" values in latest reports
FORBIDDEN_REPORT_DEFAULTS = [
    "base_rate_pct\": 66.4",
    "base_rate_pct\":66.4",
]


def _check(name: str, ok: bool, detail: str, critical: bool = True) -> dict:
    status = "PASS" if ok else ("FAIL" if critical else "WARN")
    return {"check": name, "status": status, "detail": detail, "critical": critical}


USER_LEDGER = BASE_DIR / "data" / "users" / "default_user" / "portfolio.json"
PREDICTION_LEDGER = LEARN_DIR / "prediction_ledger.json"
SHADOW_IC_LOG = PORT_DIR / "shadow_model_ic.jsonl"


def run_data_checks(conn: sqlite3.Connection) -> list[dict]:
    """Data-state invariants established by the 2026-11-20 audit. Critical failures gate the daily runs."""
    checks = []

    def guarded(name, fn, critical=True):
        try:
            ok, detail = fn()
        except Exception as e:  # a check that cannot run is a failure, never a silent pass
            ok, detail = False, f"check error: {e}"
        checks.append(_check(name, ok, detail, critical))

    def write_guards():
        from db_guards import missing_data_guards
        missing = missing_data_guards(conn)
        return not missing, f"missing={missing}" if missing else "all write guards installed"
    guarded("write_guards_installed", write_guards)

    def closed_day_bars():
        n = conn.execute("""SELECT COUNT(*) FROM prices p JOIN trading_calendar t
                            ON t.date = p.date AND t.is_trading_day = 0""").fetchone()[0]
        return n == 0, f"{n} bars on calendar-closed days"
    guarded("no_bars_on_closed_days", closed_day_bars)

    def latest_session():
        from processor import stale_snapshot_reason
        from live_market_sync import find_coverage_gaps
        last = conn.execute("SELECT MAX(date) FROM prices").fetchone()[0]
        recs = [{"ticker": t, "close": c, "volume": v} for t, c, v in conn.execute(
            "SELECT ticker, close, volume FROM prices WHERE date = ?", (last,))]
        stale = stale_snapshot_reason(conn, last, recs)
        nxt = (datetime.fromisoformat(last).date().toordinal() + 1)
        _, threshold = find_coverage_gaps(conn, datetime.fromordinal(nxt).date().isoformat())
        ok = stale is None and len(recs) >= threshold
        return ok, f"{last}: {len(recs)} tickers (min {threshold}){'; ' + stale if stale else ''}"
    guarded("latest_session_real_and_covered", latest_session)

    def coverage_history():
        from live_market_sync import COVERAGE_LOOKBACK_DAYS, COVERAGE_MIN_RATIO
        today = datetime.now().date().isoformat()
        rows = conn.execute("""
            SELECT t.date, COUNT(DISTINCT p.ticker) FROM trading_calendar t
            LEFT JOIN prices p ON p.date = t.date
            WHERE t.is_trading_day = 1 AND t.date >= date(?, ?) AND t.date < ?
            GROUP BY t.date
        """, (today, f"-{COVERAGE_LOOKBACK_DAYS} days", today)).fetchall()
        counts = sorted(c for _, c in rows if c > 0)
        if len(counts) < 10:
            return False, "not enough sessions to judge coverage"
        thr = int(counts[int(0.9 * (len(counts) - 1))] * COVERAGE_MIN_RATIO)
        gaps = [d for d, c in rows if c < thr]
        return not gaps, f"{len(gaps)} under-covered sessions (min {thr}){': ' + ', '.join(gaps[:8]) if gaps else ''}"
    guarded("price_coverage_history", coverage_history, critical=False)

    def pit_integrity():
        order = conn.execute("""SELECT COUNT(*) FROM fundamentals_pit WHERE publication_date < snapshot_date
                                OR tradable_date < publication_date""").fetchone()[0]
        dishonest = conn.execute("""SELECT COUNT(*) FROM fundamentals_pit
            WHERE publication_source IN ('bsec_statutory_filing', 'dse_corporate_action', 'estimated')
              AND COALESCE(publication_is_estimated, 0) = 0""").fetchone()[0]
        future = conn.execute("""SELECT COUNT(*) FROM fundamentals_pit
            WHERE snapshot_date > date('now', 'localtime')""").fetchone()[0]
        return (order == 0 and dishonest == 0 and future == 0,
                f"order_violations={order} estimated_marked_verified={dishonest} unended_periods={future}")
    guarded("pit_dates_ordered_and_flags_honest", pit_integrity)

    def price_provenance():
        cols = {r[1] for r in conn.execute("PRAGMA table_info(prices)")}
        if "source" not in cols:
            return False, "prices.source column missing (run scripts/provenance.py backfill)"
        n = conn.execute("SELECT COUNT(*) FROM prices WHERE source IS NULL").fetchone()[0]
        return n == 0, f"{n} price bars without a recorded source"
    guarded("price_rows_attributed", price_provenance)

    def corporate_actions():
        plugs = conn.execute("""SELECT COUNT(*) FROM corporate_actions WHERE action_type NOT IN
            ('cash_dividend', 'bonus_dividend', 'split', 'rights_split', 'rights')""").fetchone()[0]
        invented = conn.execute("""SELECT COUNT(*) FROM corporate_actions
            WHERE action_type IN ('bonus_dividend', 'split', 'rights_split')
              AND (notes LIKE '%Historical estimated%' OR NOT (adjustment_factor > 0 AND adjustment_factor < 1))""").fetchone()[0]
        return plugs == 0 and invented == 0, f"plug_rows={plugs} invalid_price_actions={invented}"
    guarded("corporate_actions_clean", corporate_actions)

    def ledger():
        if not USER_LEDGER.exists():
            return True, "no local user ledger"
        import portfolio_manager as pm
        p = json.loads(USER_LEDGER.read_text(encoding="utf-8"))
        recon = pm.reconcile_ledger(p)
        nw = pm.compute_mark_to_market_net_worth(p, conn)
        hwm = float(p.get("high_water_mark_bdt") or nw)
        hwm_ok = hwm <= max(nw, 1.0) * 1.5
        undated = [h.get("ticker") for h in p.get("holdings", []) if not h.get("bought_at")]
        ok = recon["ok"] and hwm_ok and not undated
        return ok, (f"invested={recon['recorded']} expected={recon['expected']} hwm={hwm} nw={nw}"
                    f"{' undated=' + str(undated) if undated else ''}")
    guarded("portfolio_ledger_consistent", ledger)

    def labels():
        if not PREDICTION_LEDGER.exists():
            return True, "no prediction ledger"
        items = json.loads(PREDICTION_LEDGER.read_text(encoding="utf-8"))
        bad = [i.get("prediction_id") for i in items if i.get("status") == "EVALUATED"
               and i.get("horizon_bars") and int(i.get("horizon_bars_used") or 0) < int(i["horizon_bars"])]
        return not bad, f"{len(bad)} labels scored on a partial horizon"
    guarded("prediction_labels_full_horizon", labels)

    def shadow_ic():
        if not SHADOW_IC_LOG.exists():
            return False, "shadow IC log missing"
        last = conn.execute("SELECT MAX(date) FROM prices").fetchone()[0]
        stuck = []
        for line in SHADOW_IC_LOG.read_text(encoding="utf-8").splitlines():
            if line.strip():
                o = json.loads(line)
                if o.get("date", "") < last and not o.get("forward_date"):
                    stuck.append(o["date"])
        return not stuck, f"{len(stuck)} past dates without forward IC{': ' + ', '.join(stuck[:5]) if stuck else ''}"
    guarded("shadow_ic_resolving", shadow_ic, critical=False)

    def macro_fresh():
        # Only the risk-free rate feeds a decision (hurdle, cash yield, benchmarks); repo/CPI are informational.
        from macro_rate_feed import get_macro_rates_for_date
        last = conn.execute("SELECT MAX(date) FROM prices").fetchone()[0]
        r = get_macro_rates_for_date(last, conn=conn)
        return not r["is_stale"], f"risk-free {r['risk_free_rate_pct']}% ({r['risk_free_source']}), {r['staleness_days']} days old"
    guarded("macro_rates_observed_recently", macro_fresh, critical=False)

    def champion():
        from spec_guard import check_inv5_champion_registry
        return check_inv5_champion_registry()
    guarded("champion_content_frozen", champion)

    return checks


def run_data_gate() -> int:
    """Exit code for pipelines: 1 when a critical data check fails, so no downstream write runs on bad data."""
    if not DB_PATH.exists():
        print("[DATA-GATE] FAIL dse.db missing")
        return 2
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    try:
        checks = run_data_checks(conn)
        from data_quality import record
        record(conn, checks)
    finally:
        conn.close()
    fails = [c for c in checks if c["status"] == "FAIL"]
    print(f"[DATA-GATE] {'PASS' if not fails else 'FAIL'} critical_fails={len(fails)}")
    for c in checks:
        print(f"  [{c['status']}] {c['check']}: {c['detail']}")
    return 1 if fails else 0


def run_integrity() -> dict:
    checks = []
    if not DB_PATH.exists():
        return {"ok": False, "exit_code": 2, "checks": [_check("db_exists", False, "dse.db missing")]}

    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    latest_price = conn.execute("SELECT MAX(date) FROM prices").fetchone()[0]

    # 1. Ledger asof matches latest price date
    if LEDGER.exists():
        led = json.loads(LEDGER.read_text(encoding="utf-8"))
        asof = (led.get("blocks") or [{}])[-1].get("data", {}).get("asof_price_date")
        checks.append(_check(
            "ledger_asof_matches_prices",
            asof == latest_price,
            f"ledger_asof={asof} latest_price={latest_price}",
        ))
        status = (led.get("blocks") or [{}])[-1].get("data", {}).get("strategy_status")
        checks.append(_check(
            "ledger_strategy_status_present",
            status in ("ACTIVE", "KILLED"),
            f"status={status}",
        ))
    else:
        checks.append(_check("ledger_exists", False, "forward_test_ledger_v2.json missing"))

    # 2. Config scoring weights sum ~1
    if THRESHOLDS.exists():
        th = json.loads(THRESHOLDS.read_text(encoding="utf-8"))
        sc = th.get("scoring", {})
        s = float(sc.get("fundamental_weight", 0)) + float(sc.get("technical_weight", 0)) + float(sc.get("sentiment_weight", 0))
        checks.append(_check("thresholds_weights_sum_1", abs(s - 1.0) < 1e-6, f"sum={s}"))
    else:
        checks.append(_check("thresholds_exists", False, "missing"))

    # 3. Served Model Parameter Hash & Frozen Weights Integrity
    try:
        from unified_score import MODEL_ID as SERVED_MODEL_ID, FROZEN_PARAMETER_HASH, load_factor_weights
        from model_registry import load_registry as load_model_registry
        reg = load_model_registry()
        champ = reg.get("champion") or {}
        served_weights = load_factor_weights()
        
        hash_matches_frozen = (champ.get("parameter_hash") == FROZEN_PARAMETER_HASH == "acf502bc65914c48")
        id_matches_champion = (SERVED_MODEL_ID == champ.get("model_id") == "frozen_epoch2_pit_v2")
        rsi_zeroed = (served_weights.get("rsi", 0.0) == 0.0)
        debt_zeroed = (served_weights.get("debt", 0.0) == 0.0)
        fund_active = (served_weights.get("div", 0.0) > 0.0 and served_weights.get("value", 0.0) > 0.0)
        
        ok_served = hash_matches_frozen and id_matches_champion and rsi_zeroed and debt_zeroed and fund_active
        detail_msg = f"model={SERVED_MODEL_ID} hash={FROZEN_PARAMETER_HASH} weights={served_weights}"
        checks.append(_check("served_weights_match_frozen_hash", ok_served, detail_msg))
    except Exception as e:
        checks.append(_check("served_weights_match_frozen_hash", False, f"Exception: {e}"))

    # Shadow IC factor weights check (informational for offline calibrator)
    if IC_WEIGHTS.exists():
        ic = json.loads(IC_WEIGHTS.read_text(encoding="utf-8"))
        w = ic.get("weights") or {}
        ok_nn = all(float(v) >= 0 for v in w.values()) if w else False
        checks.append(_check("shadow_ic_weights_nonnegative", ok_nn, f"weights={w}"))
    else:
        checks.append(_check("shadow_ic_weights_exists", False, "factor_ic_weights.json missing"))

    # 4. Rank log full universe for latest date
    if RANK_LOG.exists():
        last = None
        for line in RANK_LOG.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    last = json.loads(line)
                except Exception:
                    pass
        if last and last.get("date") == latest_price:
            ranks = last.get("ranks") or []
            feat_n = conn.execute(
                "SELECT COUNT(*) FROM features_daily WHERE date=?", (latest_price,)
            ).fetchone()[0]
            # Allow small mismatch if some tickers lack prices that day
            ok_full = len(ranks) >= max(1, int(0.9 * feat_n)) if feat_n else len(ranks) > 0
            checks.append(_check(
                "rank_log_full_universe",
                ok_full and "ranks" in last,
                f"ranks={len(ranks)} features={feat_n} date={last.get('date')}",
            ))
        else:
            checks.append(_check(
                "rank_log_latest_date",
                False,
                f"last_rank_date={(last or {}).get('date')} latest_price={latest_price}",
            ))
    else:
        checks.append(_check("rank_log_exists", False, "missing"))

    # 5. Model registry champion present
    if REGISTRY.exists():
        reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
        champ = reg.get("champion") or {}
        checks.append(_check(
            "registry_champion",
            bool(champ.get("parameter_hash") and champ.get("model_id")),
            f"id={champ.get('model_id')} hash={champ.get('parameter_hash')}",
        ))
    else:
        checks.append(_check("registry_exists", False, "model_registry.json missing — run model_registry.py init"))

    # 6. No leaked fake base_rate in latest daily rise/fall json
    daily_dir = BASE_DIR / "reports" / "daily"
    leak = False
    leak_file = None
    if daily_dir.exists():
        files = sorted(daily_dir.glob("*_rise_fall_predictions.json"), reverse=True)
        if files:
            txt = files[0].read_text(encoding="utf-8")
            for needle in FORBIDDEN_REPORT_DEFAULTS:
                if needle in txt:
                    leak = True
                    leak_file = files[0].name
                    break
            # Also flag explicit 66.4 base_rate field
            try:
                obj = json.loads(txt)
                for item in (obj.get("predicted_to_rise") or []) + (obj.get("predicted_to_fall") or []):
                    if abs(float(item.get("base_rate_pct") or 0) - 66.4) < 1e-6:
                        leak = True
                        leak_file = files[0].name
            except Exception:
                pass
    checks.append(_check(
        "no_fake_base_rate_66_4",
        not leak,
        f"file={leak_file}" if leak else "clean",
    ))

    # 7. Freshness gate status (informational soft — fail if >1 session stale)
    try:
        from data_freshness import check_freshness
        st = check_freshness()
        checks.append(_check("data_freshness", st.get("ok", False), st.get("reason", "")))
    except Exception as e:
        checks.append(_check("data_freshness", False, str(e)))

    checks.extend(run_data_checks(conn))

    conn.close()

    fails = [c for c in checks if c["status"] == "FAIL"]
    result = {
        "ok": len(fails) == 0,
        "exit_code": 0 if len(fails) == 0 else 1,
        "checked_at": datetime.now().isoformat(),
        "latest_price_date": latest_price,
        "fail_count": len(fails),
        "checks": checks,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / f"{datetime.now().date().isoformat()}_integrity.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    md = REPORT_DIR / f"{datetime.now().date().isoformat()}_integrity.md"
    lines = [
        f"# Integrity Harness — {result['checked_at']}",
        f"**Result**: {'PASS' if result['ok'] else 'FAIL'} ({result['fail_count']} failures)",
        "",
        "| Check | Status | Detail |",
        "|---|---|---|",
    ]
    for c in checks:
        lines.append(f"| `{c['check']}` | **{c['status']}** | {c['detail']} |")
    md.write_text("\n".join(lines), encoding="utf-8")

    print(f"[INTEGRITY] {'PASS' if result['ok'] else 'FAIL'} fails={result['fail_count']}")
    for c in checks:
        print(f"  [{c['status']}] {c['check']}: {c['detail']}")
    return result


if __name__ == "__main__":
    if "--data-gate" in sys.argv:
        sys.exit(run_data_gate())
    res = run_integrity()
    sys.exit(res["exit_code"])
