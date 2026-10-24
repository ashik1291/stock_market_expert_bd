"""
Phase 4 champion/challenger registry.

- Every model variant gets parameter_hash + role (champion|challenger|retired)
- Challengers shadow-score same universe; IC logged daily alongside champion
- Promote only via promote_challenger() after pre-registered periods + Holm gate
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LEARN_DIR = BASE_DIR / "data" / "learning"
PORT_DIR = BASE_DIR / "data" / "portfolio"
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"
REGISTRY_PATH = LEARN_DIR / "model_registry.json"
SHADOW_IC_LOG = PORT_DIR / "shadow_model_ic.jsonl"
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from unified_score import MODEL_ID, score_features, DEFAULT_HORIZON_BARS
from rank_ic_newey_west import spearman_rank_correlation, newey_west_t_stat

# Pre-registered promotion gate (Epoch 2 power math: ~44 periods @ 14d; use 21-bar IC stride)
REQUIRED_PERIODS = 12  # minimum independent IC observations before promote attempt
ALPHA_FAMILY = 0.05    # family-wise error rate for Holm


def _param_hash(payload: dict) -> str:
    if "canonical_spec" in payload:
        return hashlib.sha256(str(payload["canonical_spec"]).encode("utf-8")).hexdigest()[:16]
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _default_registry() -> dict:
    champ_params = {
        "model_id": MODEL_ID,
        "canonical_spec": "pit_dividend_pe_rsi_sector_capped_v2",
        "score": "frozen_epoch2_pit_formula",
        "gates": ["debt_le_1_nonbank", "pe_0_25"],
        "factors": ["div", "value", "debt", "rsi"],
        "factor_weights": {"div": 1.0, "value": 1.0, "debt": 0.0, "rsi": 0.0},
    }
    # Shadow challengers
    chall_ic = {
        "model_id": "shadow_v3_ic_weighted",
        "score": "ic_weighted_v3",
        "gates": ["debt_le_1_nonbank", "pe_0_25"],
        "factors": ["div", "value", "rsi", "debt"],
        "ic_weight_source": "factor_ic_weights.json",
    }
    chall_eq = {
        "model_id": "challenger_equal_weight_v2",
        "score": "equal_weight_heuristic",
        "gates": ["debt_le_1_nonbank", "pe_0_25"],
        "factors": ["div", "value", "rsi", "debt"],
        "factor_weights": {"div": 1.0, "value": 1.0, "rsi": 1.0, "debt": 1.0},
    }
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "trial_count": 52,  # Accounting for all 52 exploratory trials evaluated (Holm gate deflation)
        "required_periods": REQUIRED_PERIODS,
        "holm_alpha": ALPHA_FAMILY,
        "champion": {
            "model_id": champ_params["model_id"],
            "parameter_hash": _param_hash(champ_params),
            "params": champ_params,
            "promoted_at": "2026-10-11T10:39:34.252678+00:00",
            "role": "champion",
        },
        "challengers": [
            {
                "model_id": chall_ic["model_id"],
                "parameter_hash": _param_hash(chall_ic),
                "params": chall_ic,
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "role": "challenger",
                "status": "SHADOW",
            },
            {
                "model_id": chall_eq["model_id"],
                "parameter_hash": _param_hash(chall_eq),
                "params": chall_eq,
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "role": "challenger",
                "status": "SHADOW",
            }
        ],
        "retired": [],
        "promotion_log": [],
    }


def load_registry() -> dict:
    LEARN_DIR.mkdir(parents=True, exist_ok=True)
    if not REGISTRY_PATH.exists():
        reg = _default_registry()
        save_registry(reg)
        return reg
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_registry(reg: dict) -> None:
    LEARN_DIR.mkdir(parents=True, exist_ok=True)
    reg["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(reg, f, indent=2)


def register_challenger(model_id: str, params: dict) -> dict:
    """Register new challenger. Increments trial_count (Holm deflation)."""
    reg = load_registry()
    params = dict(params)
    params["model_id"] = model_id
    entry = {
        "model_id": model_id,
        "parameter_hash": _param_hash(params),
        "params": params,
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "role": "challenger",
        "status": "SHADOW",
    }
    # Replace same model_id if re-registered
    reg["challengers"] = [c for c in reg.get("challengers", []) if c["model_id"] != model_id]
    reg["challengers"].append(entry)
    reg["trial_count"] = int(reg.get("trial_count", 0)) + 1
    save_registry(reg)
    return entry


def champion_hash() -> str:
    return load_registry()["champion"]["parameter_hash"]


def _score_with_params(row: dict, params: dict) -> dict:
    fw = None
    score_mode = params.get("score")
    if score_mode == "frozen_epoch2_pit_formula":
        fw = params.get("factor_weights")
    elif score_mode == "equal_weight_heuristic":
        fw = params.get("factor_weights") or {"div": 1.0, "value": 1.0, "rsi": 1.0, "debt": 1.0}
    elif score_mode == "ic_weighted_v3":
        try:
            from factor_ic_calibrator import load_ic_weights
            fw = load_ic_weights()
        except Exception:
            fw = None
    else:
        fw = params.get("factor_weights")
    return score_features(
        pe=row.get("pe_ratio"),
        debt_equity=row.get("debt_equity"),
        dividend_yield=row.get("dividend_yield"),
        rsi_14=row.get("rsi_14"),
        sector=row.get("sector"),
        close=row.get("close"),
        factor_weights=fw,
    )


def shadow_score_universe(asof: str | None = None) -> dict:
    """
    Score full features_daily universe under champion + each challenger.
    Log 1-bar forward Rank IC when next session exists.
    """
    from feature_store import build_features_for_date, load_scored_universe, latest_price_date

    PORT_DIR.mkdir(parents=True, exist_ok=True)
    reg = load_registry()
    conn = sqlite3.connect(DB_PATH)
    if asof is None:
        asof = latest_price_date(conn)
    conn.close()
    if not asof:
        return {"ok": False, "reason": "no asof"}

    build_features_for_date(asof)
    # Raw feature rows (not pre-scored) — re-score per model
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM features_daily WHERE date=?", (asof,)
    ).fetchall()]
    next_d = conn.execute(
        "SELECT MIN(date) FROM prices WHERE date > ?", (asof,)
    ).fetchone()[0]

    models = [reg["champion"]] + list(reg.get("challengers", []))
    results = {}

    for m in models:
        mid = m["model_id"]
        scored = []
        for r in rows:
            s = _score_with_params(r, m.get("params") or {})
            scored.append({
                "ticker": r["ticker"],
                "score": s["score"],
                "is_eligible": s["is_eligible"],
                "close": r.get("close"),
            })
        ic = None
        n = 0
        if next_d:
            xs, ys = [], []
            for s in scored:
                if not s["is_eligible"]:
                    continue
                px1 = conn.execute(
                    "SELECT close FROM prices WHERE ticker=? AND date=?",
                    (s["ticker"], next_d),
                ).fetchone()
                if s["close"] and px1 and px1[0] and float(s["close"]) > 0:
                    xs.append(float(s["score"]))
                    ys.append(float(px1[0]) / float(s["close"]) - 1.0)
            n = len(xs)
            if n >= 15:
                ic = round(spearman_rank_correlation(xs, ys), 4)
        results[mid] = {
            "parameter_hash": m["parameter_hash"],
            "role": m.get("role"),
            "ic": ic,
            "n": n,
            "eligible": sum(1 for s in scored if s["is_eligible"]),
            "top5": sorted(
                [s for s in scored if s["is_eligible"]],
                key=lambda x: x["score"],
                reverse=True,
            )[:5],
        }

    conn.close()
    entry = {
        "date": asof,
        "forward_date": next_d,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "champion_id": reg["champion"]["model_id"],
        "models": {
            mid: {
                "parameter_hash": v["parameter_hash"],
                "role": v["role"],
                "rank_ic": v["ic"],
                "n": v["n"],
                "eligible": v["eligible"],
                "top5": [{"ticker": t["ticker"], "score": t["score"]} for t in v["top5"]],
            }
            for mid, v in results.items()
        },
    }
    with open(SHADOW_IC_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    # dedupe by date
    _dedupe_shadow()
    print(f"[SHADOW] asof={asof} forward={next_d}")
    for mid, v in results.items():
        print(f"  {v['role']}: {mid} ic={v['ic']} n={v['n']} hash={v['parameter_hash']}")
    return {"ok": True, "entry": entry}


def _dedupe_shadow() -> None:
    if not SHADOW_IC_LOG.exists():
        return
    kept = {}
    for line in SHADOW_IC_LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get("date"):
            kept[o["date"]] = o
    with open(SHADOW_IC_LOG, "w", encoding="utf-8") as f:
        for d in sorted(kept):
            f.write(json.dumps(kept[d], ensure_ascii=False) + "\n")


def _load_shadow_ic_series(model_id: str) -> list[float]:
    if not SHADOW_IC_LOG.exists():
        return []
    series = []
    for line in SHADOW_IC_LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        m = (o.get("models") or {}).get(model_id) or {}
        if m.get("rank_ic") is not None:
            series.append(float(m["rank_ic"]))
    return series


def holm_critical(alpha: float, m: int, rank: int) -> float:
    """Holm step-down critical alpha for hypothesis of rank (1=most significant)."""
    return alpha / max(1, (m - rank + 1))


def promote_challenger(challenger_id: str | None = None, force: bool = False) -> dict:
    """
    Promote challenger if:
      1. >= REQUIRED_PERIODS IC observations for both
      2. challenger mean IC > champion mean IC
      3. Newey-West t on (challenger_ic - champion_ic) exceeds Holm-adjusted threshold
         among active trial_count hypotheses
    """
    reg = load_registry()
    champ = reg["champion"]
    challengers = reg.get("challengers") or []
    if not challengers:
        return {"ok": False, "reason": "no challengers"}

    if challenger_id:
        chall = next((c for c in challengers if c["model_id"] == challenger_id), None)
        if not chall:
            return {"ok": False, "reason": f"challenger {challenger_id} not found"}
        candidates = [chall]
    else:
        candidates = [c for c in challengers if c.get("status") == "SHADOW"]

    required = int(reg.get("required_periods", REQUIRED_PERIODS))
    alpha = float(reg.get("holm_alpha", ALPHA_FAMILY))
    m_trials = max(1, int(reg.get("trial_count", len(candidates))))

    champ_ic = _load_shadow_ic_series(champ["model_id"])
    decisions = []

    # Score each candidate by excess IC t-stat for Holm ordering
    scored = []
    for c in candidates:
        c_ic = _load_shadow_ic_series(c["model_id"])
        n = min(len(champ_ic), len(c_ic))
        if n < required and not force:
            decisions.append({
                "model_id": c["model_id"],
                "promoted": False,
                "reason": f"need>={required} IC periods, have {n}",
            })
            continue
        # Align last n
        diff = [c_ic[-n + i] - champ_ic[-n + i] for i in range(n)]
        mean_d, se, t = newey_west_t_stat(diff, max_lags=max(1, int(math.ceil(DEFAULT_HORIZON_BARS / 5))))
        scored.append({
            "challenger": c,
            "n": n,
            "mean_excess_ic": mean_d,
            "t_nw": t,
            "champ_mean": sum(champ_ic[-n:]) / n,
            "chall_mean": sum(c_ic[-n:]) / n,
        })

    # Holm: sort by |t| descending
    scored.sort(key=lambda x: abs(x["t_nw"]), reverse=True)
    promoted = None
    for rank_i, s in enumerate(scored, start=1):
        crit = holm_critical(alpha, m_trials, rank_i)
        # one-sided: challenger better → t>0; approx z crit for alpha
        # use normal approx: t > Φ^{-1}(1-crit)
        z_crit = _norm_isf(crit)
        ok = s["mean_excess_ic"] > 0 and s["t_nw"] > z_crit
        if force:
            ok = s["mean_excess_ic"] > 0
        decision = {
            "model_id": s["challenger"]["model_id"],
            "promoted": ok,
            "n": s["n"],
            "mean_excess_ic": round(s["mean_excess_ic"], 4),
            "t_nw": round(s["t_nw"], 3),
            "z_crit_holm": round(z_crit, 3),
            "holm_rank": rank_i,
            "m_trials": m_trials,
            "champ_mean_ic": round(s["champ_mean"], 4),
            "chall_mean_ic": round(s["chall_mean"], 4),
            "reason": "PASS" if ok else "fail_holm_or_sign",
        }
        decisions.append(decision)
        if ok and promoted is None:
            promoted = s

    if promoted:
        old_champ = reg["champion"]
        new_champ = dict(promoted["challenger"])
        new_champ["role"] = "champion"
        new_champ["promoted_at"] = datetime.now(timezone.utc).isoformat()
        new_champ.pop("status", None)
        old_champ["role"] = "retired"
        old_champ["retired_at"] = new_champ["promoted_at"]
        reg["retired"] = list(reg.get("retired") or []) + [old_champ]
        reg["champion"] = new_champ
        reg["challengers"] = [
            c for c in challengers if c["model_id"] != new_champ["model_id"]
        ]
        reg["promotion_log"] = list(reg.get("promotion_log") or []) + [{
            "at": new_champ["promoted_at"],
            "from": old_champ["model_id"],
            "to": new_champ["model_id"],
            "decision": decisions,
        }]
        save_registry(reg)
        print(f"[PROMOTE] {old_champ['model_id']} -> {new_champ['model_id']}")
        return {"ok": True, "promoted": new_champ["model_id"], "decisions": decisions}

    return {"ok": False, "promoted": None, "decisions": decisions}


def _norm_isf(p: float) -> float:
    """Inverse survival function approx for standard normal (Acklam)."""
    if p <= 0 or p >= 1:
        return 3.0
    # rough: for small p use erfcinv-like approximation
    # common critical values
    table = {
        0.05: 1.64485,
        0.025: 1.95996,
        0.01: 2.32635,
        0.005: 2.57583,
        0.001: 3.09023,
    }
    best = 1.96
    best_dp = 999.0
    for k, v in table.items():
        if abs(k - p) < best_dp:
            best_dp = abs(k - p)
            best = v
    # interpolate in log space for holm-adjusted alphas
    if p < 0.001:
        return 3.1 + math.log10(0.001 / p) * 0.5
    if p > 0.05:
        return 1.64 * (0.05 / p) ** 0.2
    return best


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "shadow"
    if cmd == "init":
        print(json.dumps(load_registry(), indent=2))
    elif cmd == "shadow":
        print(json.dumps(shadow_score_universe(), indent=2, default=str)[:2000])
    elif cmd == "promote":
        cid = sys.argv[2] if len(sys.argv) > 2 else None
        print(json.dumps(promote_challenger(cid), indent=2))
    else:
        print("usage: model_registry.py [init|shadow|promote]")
