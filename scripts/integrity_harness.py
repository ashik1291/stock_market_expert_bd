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


def _check(name: str, ok: bool, detail: str) -> dict:
    return {"check": name, "status": "PASS" if ok else "FAIL", "detail": detail}


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
    res = run_integrity()
    sys.exit(res["exit_code"])
