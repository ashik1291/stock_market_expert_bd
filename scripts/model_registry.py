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
# Hard floor on live (non-backfilled) daily IC observations, regardless of registry config.
MIN_PROMOTION_PERIODS = 200
STATIC_SCORE_MODES = {"frozen_epoch2_pit_formula", "equal_weight_heuristic", "cross_sectional_rank_v1"}
CROSS_SECTIONAL_FACTORS = {
    "div": lambda r: r.get("dividend_yield"),
    "value": lambda r: (100.0 / r["pe_ratio"]) if r.get("pe_ratio") and r["pe_ratio"] > 0 else None,
    "rsi": lambda r: -r["rsi_14"] if r.get("rsi_14") is not None else None,
}
CA_PRICE_EVENTS = ("bonus_dividend", "split", "rights_split", "rights", "cash_bonus_adjustment")


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
    chall_bayes = {
        "model_id": "shadow_bayesian_adaptive_v1",
        "score": "bayesian_adaptive_v1",
        "gates": ["debt_le_1_nonbank", "pe_0_25"],
        "factors": ["div", "value", "rsi", "debt"],
        "weights_source": "model_weights.json",
    }
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "trial_count": 53,  # Accounting for exploratory trials evaluated (Holm gate deflation)
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
            },
            {
                "model_id": chall_bayes["model_id"],
                "parameter_hash": _param_hash(chall_bayes),
                "params": chall_bayes,
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
        reg = json.load(f)

    # Ensure shadow_bayesian_adaptive_v1 challenger is registered
    chall_ids = {c.get("model_id") for c in reg.get("challengers", [])}
    if "shadow_bayesian_adaptive_v1" not in chall_ids:
        chall_bayes = {
            "model_id": "shadow_bayesian_adaptive_v1",
            "score": "bayesian_adaptive_v1",
            "gates": ["debt_le_1_nonbank", "pe_0_25"],
            "factors": ["div", "value", "rsi", "debt"],
            "weights_source": "model_weights.json",
        }
        reg.setdefault("challengers", []).append({
            "model_id": chall_bayes["model_id"],
            "parameter_hash": _param_hash(chall_bayes),
            "params": chall_bayes,
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "role": "challenger",
            "status": "SHADOW",
        })
        save_registry(reg)

    return reg


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


def freeze_champion_content(reason: str) -> dict:
    """Record the current scoring content hash as the champion's frozen content (a governance event)."""
    from unified_score import compute_model_content_hash, SCORING_SOURCE_FILES
    if not reason or not reason.strip():
        raise ValueError("a reason is required to freeze champion content")
    reg = load_registry()
    champ = reg["champion"]
    new_hash = compute_model_content_hash()
    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "model_id": champ["model_id"],
        "previous_content_hash": champ.get("frozen_content_hash"),
        "content_hash": new_hash,
        "files": list(SCORING_SOURCE_FILES),
        "reason": reason.strip(),
    }
    champ["frozen_content_hash"] = new_hash
    champ["frozen_content_at"] = entry["at"]
    reg["freeze_log"] = list(reg.get("freeze_log") or []) + [entry]
    save_registry(reg)
    return entry


def _cross_sectional_scores(rows: list[dict], params: dict) -> dict:
    """
    Whole-universe score: mean percentile rank of the declared factors among names passing the Shariah-sector,
    price and debt gates (D/E <= max_debt_equity for non-banks; missing D/E is gated). No macro-hurdle gate.
    """
    from unified_score import is_shariah_excluded_company
    max_de = float(params.get("max_debt_equity", 1.0))
    passed = [r for r in rows if (r.get("close") or 0) > 0
              and not is_shariah_excluded_company(r.get("sector"), ticker=r.get("ticker"))
              and r.get("debt_equity") is not None and float(r["debt_equity"]) <= max_de]
    pct = {}
    for f in params.get("factors", list(CROSS_SECTIONAL_FACTORS)):
        vals = sorted((CROSS_SECTIONAL_FACTORS[f](r), r["ticker"]) for r in passed if CROSS_SECTIONAL_FACTORS[f](r) is not None)
        n = len(vals)
        for i, (_, t) in enumerate(vals):
            pct.setdefault(t, []).append((i + 0.5) / n)
    need = int(params.get("min_factors", 2))
    scores = {r["ticker"]: None for r in rows}
    for t, ps in pct.items():
        if len(ps) >= need:
            scores[t] = round(sum(ps) / len(ps), 6)
    return scores


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
    elif score_mode == "bayesian_adaptive_v1":
        try:
            from reinforcement_learning_engine import load_weights
            raw_w = load_weights()
            # Map empirical Bayes learned factor weights into scoring weights
            fw = {
                "div": float(raw_w.get("smart_money_weight", 1.0)),
                "value": float(raw_w.get("valuation_mos_weight", 1.0)),
                "debt": float(raw_w.get("debt_npl_weight", 0.0)),
                "rsi": float(raw_w.get("rsi_momentum_weight", 0.0)),
            }
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
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    if asof is None:
        asof = latest_price_date(conn)
    conn.close()
    if not asof:
        return {"ok": False, "reason": "no asof"}

    build_features_for_date(asof)
    # Raw feature rows (not pre-scored) — re-score per model
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM features_daily WHERE date=?", (asof,)
    ).fetchall()]
    conn.close()

    models = [reg["champion"]] + list(reg.get("challengers", []))
    entry = {
        "date": asof,
        "forward_date": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "champion_id": reg["champion"]["model_id"],
        "closes": {r["ticker"]: r.get("close") for r in rows if r.get("close")},
        "scores_universe": "full",
        "models": {},
    }
    for m in models:
        scores = {}
        if (m.get("params") or {}).get("score") == "cross_sectional_rank_v1":
            scores = _cross_sectional_scores(rows, m["params"])
        for r in rows if not scores else []:
            sc = _score_with_params(r, m.get("params") or {})
            scores[r["ticker"]] = float(sc["score"]) if sc["is_eligible"] else None
        ranked = sorted(((t, v) for t, v in scores.items() if v is not None), key=lambda x: x[1], reverse=True)
        entry["models"][m["model_id"]] = {
            "parameter_hash": m["parameter_hash"],
            "role": m.get("role"),
            "rank_ic": None,
            "n": 0,
            "eligible": len(ranked),
            "scores": scores,
            "top5": [{"ticker": t, "score": v} for t, v in ranked[:5]],
        }

    with open(SHADOW_IC_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    _dedupe_shadow()
    resolved = resolve_shadow_ic()
    print(f"[SHADOW] asof={asof} scored; resolved {resolved} pending forward IC entries")
    return {"ok": True, "entry": {k: v for k, v in entry.items() if k != "closes"}}


def _next_session(conn: sqlite3.Connection, d: str) -> str | None:
    row = conn.execute("""
        SELECT MIN(p.date) FROM prices p
        JOIN trading_calendar t ON t.date = p.date AND t.is_trading_day = 1
        WHERE p.date > ?
    """, (d,)).fetchone()
    return row[0] if row and row[0] else None


def _forward_ic(conn: sqlite3.Connection, d: str, nd: str, scores: dict, closes: dict) -> tuple[float | None, int]:
    """
    1-session forward Spearman IC over the whole scored universe: eligible names by score, gated
    (None) names tied below every eligible name, so the IC measures selection, not just ordering
    within a handful of picks. Tickers with a price-altering corporate action in [d, nd] are excluded.
    """
    live = [v for v in scores.values() if v is not None]
    if not live:
        return None, 0
    floor = min(live) - 1.0
    scores = {t: (v if v is not None else floor) for t, v in scores.items()}
    ph = ",".join("?" * len(CA_PRICE_EVENTS))
    excluded = {r[0] for r in conn.execute(
        f"SELECT DISTINCT ticker FROM corporate_actions WHERE record_date BETWEEN ? AND ? AND action_type IN ({ph})",
        (d, nd, *CA_PRICE_EVENTS),
    )}
    fwd = {r[0]: r[1] for r in conn.execute("SELECT ticker, close FROM prices WHERE date = ?", (nd,))}
    base = {r[0]: r[1] for r in conn.execute("SELECT ticker, close FROM prices WHERE date = ?", (d,))}
    xs, ys = [], []
    for t, sc in scores.items():
        c0, c1 = base.get(t) or closes.get(t), fwd.get(t)
        if t in excluded or not c0 or not c1 or float(c0) <= 0:
            continue
        xs.append(float(sc))
        ys.append(float(c1) / float(c0) - 1.0)
    if len(xs) < 15:
        return None, len(xs)
    return round(spearman_rank_correlation(xs, ys), 4), len(xs)


def _rescore_static(conn: sqlite3.Connection, d: str, model: dict) -> tuple[dict, dict] | None:
    """Re-score a past date from stored PIT features; only valid for models whose parameters never change."""
    if (model.get("params") or {}).get("score") not in STATIC_SCORE_MODES:
        return None
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM features_daily WHERE date = ?", (d,))]
    conn.row_factory = None
    if model["params"].get("score") == "cross_sectional_rank_v1":
        return _cross_sectional_scores(rows, model["params"]), {r["ticker"]: r.get("close") for r in rows if r.get("close")}
    scores = {}
    for r in rows:
        sc = _score_with_params(r, model.get("params") or {})
        scores[r["ticker"]] = float(sc["score"]) if sc["is_eligible"] else None
    closes = {r["ticker"]: r.get("close") for r in rows if r.get("close")}
    return scores, closes


def resolve_shadow_ic(backfill: bool = True) -> int:
    """
    Fill forward IC for every logged date whose next trading session now has prices.
    With backfill=True, also create entries for features_daily dates never logged, re-scored
    for static-parameter models only and flagged backfilled (excluded from promotion).
    """
    reg = load_registry()
    models = [reg["champion"]] + list(reg.get("challengers", []))
    entries = {}
    if SHADOW_IC_LOG.exists():
        for line in SHADOW_IC_LOG.read_text(encoding="utf-8").splitlines():
            if line.strip():
                o = json.loads(line)
                entries[o["date"]] = o

    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    resolved = 0
    try:
        if backfill:
            for (d,) in conn.execute("""
                SELECT DISTINCT f.date FROM features_daily f
                JOIN trading_calendar t ON t.date = f.date AND t.is_trading_day = 1
            """).fetchall():
                if d not in entries:
                    entries[d] = {"date": d, "forward_date": None, "backfilled": True,
                                  "champion_id": reg["champion"]["model_id"], "models": {}}

        for d, e in sorted(entries.items()):
            nd = _next_session(conn, d)
            if not nd:
                continue
            changed = False
            for m in models:
                mid = m["model_id"]
                me = e["models"].setdefault(mid, {"parameter_hash": m["parameter_hash"], "role": m.get("role"),
                                                  "rank_ic": None, "n": 0})
                if me.get("rank_ic") is not None:
                    continue
                # Entries logged before scores covered the whole universe are rescored when possible.
                if me.get("scores") and e.get("closes") and e.get("scores_universe") == "full":
                    ic, n = _forward_ic(conn, d, nd, me["scores"], e["closes"])
                else:
                    rs = _rescore_static(conn, d, m)
                    if rs is None:
                        me["backfill_skipped"] = "adaptive_params_would_leak_future"
                        continue
                    ic, n = _forward_ic(conn, d, nd, rs[0], rs[1])
                    me["backfilled"] = True
                me["rank_ic"], me["n"] = ic, n
                changed = True
            if changed or e.get("forward_date") != nd:
                e["forward_date"] = nd
                resolved += 1
    finally:
        conn.close()

    with open(SHADOW_IC_LOG, "w", encoding="utf-8") as f:
        for d in sorted(entries):
            f.write(json.dumps(entries[d], ensure_ascii=False) + "\n")
    return resolved


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


def _load_shadow_ic_series(model_id: str, live_only: bool = True) -> dict:
    """date -> IC. live_only drops backfilled observations, which never count toward promotion."""
    if not SHADOW_IC_LOG.exists():
        return {}
    series = {}
    for line in SHADOW_IC_LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        m = (o.get("models") or {}).get(model_id) or {}
        if m.get("rank_ic") is None:
            continue
        if live_only and (o.get("backfilled") or m.get("backfilled")):
            continue
        series[o["date"]] = float(m["rank_ic"])
    return series


def holm_critical(alpha: float, m: int, rank: int) -> float:
    """Holm step-down critical alpha for hypothesis of rank (1=most significant)."""
    return alpha / max(1, (m - rank + 1))


def _one_sided_p(t: float) -> float:
    """P(Z >= t) under the standard normal (Newey-West t is asymptotically normal)."""
    return 0.5 * math.erfc(t / math.sqrt(2.0))


def promote_challenger(challenger_id: str | None = None, force: bool = False, approve: bool = False) -> dict:
    """
    Evaluate challengers against the champion on date-aligned live daily IC:
      1. >= max(registry required_periods, MIN_PROMOTION_PERIODS) shared live observations
      2. Newey-West t on (challenger_ic - champion_ic), one-sided p-value
      3. Holm step-down over m = max(trial_count, candidates) hypotheses; stops at first failure
    The registry is changed only when approve=True (a human decision); otherwise this is a dry run.
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

    required = max(int(reg.get("required_periods", REQUIRED_PERIODS)), MIN_PROMOTION_PERIODS)
    alpha = float(reg.get("holm_alpha", ALPHA_FAMILY))
    m_trials = max(1, int(reg.get("trial_count", 0)), len(candidates))

    champ_ic = _load_shadow_ic_series(champ["model_id"])
    decisions = []
    scored = []
    for c in candidates:
        c_ic = _load_shadow_ic_series(c["model_id"])
        dates = sorted(set(champ_ic) & set(c_ic))
        n = len(dates)
        if n < required and not force:
            decisions.append({
                "model_id": c["model_id"],
                "promoted": False,
                "reason": f"need>={required} live IC periods, have {n}",
            })
            continue
        if n < 3:
            decisions.append({"model_id": c["model_id"], "promoted": False, "reason": f"only {n} periods"})
            continue
        diff = [c_ic[d] - champ_ic[d] for d in dates]
        mean_d, se, t = newey_west_t_stat(diff, max_lags=max(1, int(math.ceil(DEFAULT_HORIZON_BARS / 5))))
        scored.append({
            "challenger": c,
            "n": n,
            "mean_excess_ic": mean_d,
            "t_nw": t,
            "p_one_sided": _one_sided_p(t),
            "champ_mean": sum(champ_ic[d] for d in dates) / n,
            "chall_mean": sum(c_ic[d] for d in dates) / n,
        })

    scored.sort(key=lambda x: x["p_one_sided"])
    promoted = None
    rejecting = True
    for rank_i, sc in enumerate(scored, start=1):
        crit = holm_critical(alpha, m_trials, rank_i)
        ok = rejecting and sc["mean_excess_ic"] > 0 and sc["p_one_sided"] <= crit
        if force:
            ok = sc["mean_excess_ic"] > 0
        if not ok:
            rejecting = False
        decisions.append({
            "model_id": sc["challenger"]["model_id"],
            "promoted": False,
            "passes_gate": ok,
            "n": sc["n"],
            "mean_excess_ic": round(sc["mean_excess_ic"], 4),
            "t_nw": round(sc["t_nw"], 3),
            "p_one_sided": round(sc["p_one_sided"], 6),
            "holm_alpha_crit": round(crit, 6),
            "z_crit_holm": round(_norm_isf(crit), 3),
            "holm_rank": rank_i,
            "m_trials": m_trials,
            "champ_mean_ic": round(sc["champ_mean"], 4),
            "chall_mean_ic": round(sc["chall_mean"], 4),
            "reason": "PASS" if ok else "fail_holm_or_sign",
        })
        if ok and promoted is None:
            promoted = sc

    if promoted and not approve:
        return {"ok": False, "promoted": None, "pending_approval": promoted["challenger"]["model_id"],
                "decisions": decisions,
                "reason": "gate passed; rerun with 'promote <id> --approve' to change the champion"}

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
        for dcs in decisions:
            if dcs["model_id"] == new_champ["model_id"]:
                dcs["promoted"] = True
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
    """Inverse survival function of the standard normal."""
    from statistics import NormalDist
    if p <= 0 or p >= 1:
        return float("inf") if p <= 0 else float("-inf")
    return NormalDist().inv_cdf(1.0 - p)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "shadow"
    if cmd == "init":
        print(json.dumps(load_registry(), indent=2))
    elif cmd == "shadow":
        print(json.dumps(shadow_score_universe(), indent=2, default=str)[:2000])
    elif cmd == "promote":
        args = [x for x in sys.argv[2:] if not x.startswith("--")]
        cid = args[0] if args else None
        print(json.dumps(promote_challenger(cid, approve="--approve" in sys.argv), indent=2))
    elif cmd == "freeze":
        reason = " ".join(x for x in sys.argv[2:] if x != "--reason")
        print(json.dumps(freeze_champion_content(reason), indent=2))
    elif cmd == "resolve":
        print(json.dumps({"resolved": resolve_shadow_ic()}, indent=2))
    else:
        print("usage: model_registry.py [init|shadow|resolve|promote [id] [--approve]|freeze --reason <text>]")
