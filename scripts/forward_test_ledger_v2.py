"""
V2 Hash-Chained Forward Ledger — Phase 3.

- Score source: features_daily / served_v3_ic_weighted
- Full-universe rank log (deduped)
- Mark-to-market every session
- Monthly rebalance + hold buffer: sell only if rank falls outside top 30% eligible
- Fills: next-session OPEN when available, else close*(1+10bps)
- Kill rule active: excess vs EQW < -3% OR max DD < -25% → no new buys
"""

from __future__ import annotations

import json
import sqlite3
import datetime
import hashlib
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"
PORT_DIR = BASE_DIR / "data" / "portfolio"
LEDGER_V2_FILE = PORT_DIR / "forward_test_ledger_v2.json"
FULL_UNIVERSE_LOG = PORT_DIR / "universe_daily_rank_scores.jsonl"
IC_DAILY_LOG = PORT_DIR / "daily_rank_ic.jsonl"
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from unified_score import MODEL_ID, ROUND_TRIP_COST_PCT
from feature_store import build_features_for_date, load_scored_universe
from benchmark_index import equal_weight_category_a_nav
from rank_ic_newey_west import spearman_rank_correlation

FEE_BUY_PCT = 0.00415
FEE_SELL_PCT = 0.00465  # 0.415% broker fee + 0.05% Section 53BBB AIT
SLIPPAGE_PCT = 0.0010
INITIAL_CAPITAL = 1000000.0
TARGET_POSITIONS = 10
SECTOR_MAX = 2
HOLD_TOP_PCT = 0.30  # keep if still in top 30% eligible
REBALANCE_MIN_BARS = 21
KILL_EXCESS_PCT = -3.0
KILL_MAX_DD_PCT = -25.0


def compute_sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _dedupe_jsonl(path: Path, date_key: str = "date") -> None:
    if not path.exists():
        return
    kept = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            d = obj.get(date_key)
            if d:
                kept[d] = obj
    with open(path, "w", encoding="utf-8") as f:
        for d in sorted(kept):
            f.write(json.dumps(kept[d], ensure_ascii=False) + "\n")


def _is_floor_locked(conn: sqlite3.Connection, ticker: str, dt: str) -> bool:
    """True if volume==0 or high==low==close at floor — censored bar (DSE floor-price lock)."""
    row = conn.execute(
        "SELECT open, high, low, close, volume FROM prices WHERE ticker=? AND date=?",
        (ticker, dt),
    ).fetchone()
    if not row:
        return False
    o, hi, lo, cl, vol = row
    try:
        vol0 = vol is None or int(vol or 0) == 0
        hi_f = float(hi) if hi is not None else None
        lo_f = float(lo) if lo is not None else None
        cl_f = float(cl) if cl is not None else None
        # volume==0 OR high==low==close (flat/floor)
        if vol0:
            return True
        if hi_f is not None and lo_f is not None and cl_f is not None:
            if abs(hi_f - lo_f) < 1e-9 and abs(lo_f - cl_f) < 1e-9:
                return True
    except Exception:
        return False
    return False


def _next_open(conn: sqlite3.Connection, ticker: str, after_date: str) -> tuple[str | None, float | None]:
    row = conn.execute(
        """
        SELECT date, open FROM prices
        WHERE ticker=? AND date>? AND open IS NOT NULL AND open>0
        ORDER BY date ASC LIMIT 1
        """,
        (ticker, after_date),
    ).fetchone()
    if not row:
        return None, None
    return row[0], float(row[1])


def _fill_price(conn: sqlite3.Connection, ticker: str, signal_date: str, close_px: float, side: str) -> dict:
    """Prefer next open; fallback close +/- slippage. Floor-lock / volume==0 -> SKIP (NaN)."""
    # Bangladesh microstructure: floor-price lock (volume==0 or high==low==close) — not tradable.
    # Censor the fill and the caller must defer: caller that receives fill_source FLOOR_LOCKED
    # must treat it as NaN/SKIP_REBALANCE rather than filling at a phantom NEXT_OPEN.
    try:
        nxt = conn.execute(
            "SELECT date FROM prices WHERE ticker=? AND date>? ORDER BY date ASC LIMIT 1",
            (ticker, signal_date),
        ).fetchone()
        if nxt and _is_floor_locked(conn, ticker, nxt[0]):
            return {"price": None, "fill_date": nxt[0], "fill_source": "FLOOR_LOCKED_SKIP", "floor_locked": True}
        # also check signal bar itself locked (e.g., attempted sell into floor)
        if _is_floor_locked(conn, ticker, signal_date):
            return {"price": None, "fill_date": signal_date, "fill_source": "FLOOR_LOCKED_SKIP", "floor_locked": True}
    except Exception:
        pass
    # Adaptive Liquidity-Tier Slippage Model
    try:
        row = conn.execute(
            "SELECT AVG(close * volume) FROM prices WHERE ticker=? AND date<=? ORDER BY date DESC LIMIT 20",
            (ticker, signal_date)
        ).fetchone()
        avg_turnover = float(row[0]) if (row and row[0] is not None) else 5000000.0
        if avg_turnover >= 50000000.0:
            effective_slip = 0.0020  # 0.2% for high liquidity (>= 5 Cr)
        elif avg_turnover >= 10000000.0:
            effective_slip = 0.0040  # 0.4% for mid-tier (>= 1 Cr)
        elif avg_turnover >= 2000000.0:
            effective_slip = 0.0080  # 0.8% for retail float (>= 20 Lakh)
        else:
            effective_slip = 0.0150  # 1.5% for illiquid / thin book
    except Exception:
        effective_slip = SLIPPAGE_PCT

    od, op = _next_open(conn, ticker, signal_date)
    if op is not None:
        px = round(op * (1.0 + effective_slip if side == "buy" else 1.0 - effective_slip), 2)
        return {"price": px, "fill_date": od, "fill_source": "NEXT_OPEN"}
    slip = 1.0 + effective_slip if side == "buy" else 1.0 - effective_slip
    return {
        "price": round(close_px * slip, 2),
        "fill_date": signal_date,
        "fill_source": "CLOSE_PROXY",
    }


def _mark_to_market(
    conn: sqlite3.Connection,
    positions: list,
    cash: float,
    asof: str,
    prev_asof: str | None = None,
) -> tuple[float, list, float]:
    updated = []
    equity = 0.0

    # Credit risk-free Central Bank 91-day T-Bill interest (11.60% annualized) on uninvested cash buffer
    if prev_asof and cash > 0 and asof > prev_asof:
        bars = _trading_bars_between(conn, prev_asof, asof)
        if bars > 0:
            tbill_yield = round(cash * (0.1160 / 250.0) * bars, 2)
            cash = round(cash + tbill_yield, 2)

    for p in positions:
        row = conn.execute(
            "SELECT close FROM prices WHERE ticker=? AND date=?",
            (p["ticker"], asof),
        ).fetchone()
        px = float(row[0]) if row and row[0] is not None else p.get("last_mark_price") or p["execution_price"]
        mtm = round(px * p["shares"], 2)
        np = dict(p)
        
        # Credit cash dividends distributed between last mark date and today (idempotent)
        start_d = p.get("last_mark_date") or p.get("entry_date") or asof
        div_rows = conn.execute("""
            SELECT record_date, cash_amount FROM corporate_actions
            WHERE ticker = ? AND action_type = 'cash_dividend'
              AND record_date > ? AND record_date <= ?
              AND cash_amount IS NOT NULL AND cash_amount > 0
        """, (p["ticker"], start_d, asof)).fetchall()
        for rec_d, c_amt in div_rows:
            net_div = round(p["shares"] * float(c_amt) * 0.90, 2)  # 10% AIT tax deduction
            cash = round(cash + net_div, 2)
            np["total_dividends_credited"] = round(np.get("total_dividends_credited", 0.0) + net_div, 2)

        np["last_mark_price"] = px
        np["last_mark_date"] = asof
        np["mark_equity"] = mtm
        updated.append(np)
        equity += mtm
    return round(cash + equity, 2), updated, cash


def _eligible_ranked(scored: list[dict]) -> list[dict]:
    elig = [r for r in scored if r.get("is_eligible") and r.get("passes_macro", True)]
    elig.sort(key=lambda x: float(x.get("score") or -999), reverse=True)
    return elig


def _requires_safety_rebalance(positions: list[dict], elig: list[dict]) -> bool:
    """Force next-session safety cleanup for positions no longer eligible."""
    eligible_tickers = {str(row.get("ticker")) for row in elig}
    return any(str(position.get("ticker")) not in eligible_tickers for position in positions)


def _top_pct_tickers(elig: list[dict], pct: float) -> set[str]:
    if not elig:
        return set()
    k = max(1, int(math_ceil(len(elig) * pct)))
    return {r["ticker"] for r in elig[:k]}


def math_ceil(x: float) -> int:
    import math
    return int(math.ceil(x))


def _trading_bars_between(conn: sqlite3.Connection, d0: str, d1: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) FROM trading_calendar
        WHERE date > ? AND date <= ? AND is_trading_day=1
        """,
        (d0, d1),
    ).fetchone()
    if row and row[0]:
        return int(row[0])
    # fallback distinct price dates
    row = conn.execute(
        "SELECT COUNT(DISTINCT date) FROM prices WHERE date > ? AND date <= ?",
        (d0, d1),
    ).fetchone()
    return int(row[0] or 0)


def _should_rebalance(conn: sqlite3.Connection, b_data: dict, asof: str) -> bool:
    last = b_data.get("last_rebalance_date")
    if not last:
        return True
    return _trading_bars_between(conn, last, asof) >= REBALANCE_MIN_BARS


def _compute_max_dd(nav_history: list[float]) -> float:
    if not nav_history:
        return 0.0
    peak = nav_history[0]
    max_dd = 0.0
    for n in nav_history:
        peak = max(peak, n)
        if peak > 0:
            dd = (n - peak) / peak * 100.0
            max_dd = min(max_dd, dd)
    return round(max_dd, 2)


def _daily_ic(conn: sqlite3.Connection, asof: str, scored: list[dict]) -> dict | None:
    """IC of today's score vs next-session return (1-bar) when next date exists."""
    next_dates = conn.execute(
        "SELECT DISTINCT date FROM prices WHERE date > ? ORDER BY date ASC LIMIT 1",
        (asof,),
    ).fetchone()
    if not next_dates:
        return None
    d1 = next_dates[0]
    scores, rets = [], []
    for r in scored:
        if not r.get("is_eligible"):
            continue
        t = r["ticker"]
        px0 = r.get("close")
        px1 = conn.execute(
            "SELECT close FROM prices WHERE ticker=? AND date=?", (t, d1)
        ).fetchone()
        if px0 and px1 and px1[0] and float(px0) > 0:
            scores.append(float(r["score"]))
            div_row = conn.execute("""
                SELECT cash_amount FROM corporate_actions
                WHERE ticker=? AND action_type='cash_dividend' AND record_date=?
            """, (t, d1)).fetchone()
            div_val = float(div_row[0]) if (div_row and div_row[0]) else 0.0
            adj_px1 = float(px1[0]) + div_val
            rets.append(adj_px1 / float(px0) - 1.0)
    if len(scores) < 15:
        return None
    ic = spearman_rank_correlation(scores, rets)
    return {
        "date": asof,
        "forward_date": d1,
        "n": len(scores),
        "rank_ic": round(ic, 4),
        "model_id": MODEL_ID,
    }


def _rebalance(
    conn: sqlite3.Connection,
    positions: list,
    cash: float,
    elig: list[dict],
    asof: str,
    killed: bool,
    safety_only: bool = False,
) -> tuple[list, float, list]:
    """Hold-buffer rebalance. Returns (positions, cash, trade_log)."""
    trades = []
    if killed and not safety_only:
        return positions, cash, [{"action": "SKIP_REBALANCE", "reason": "STRATEGY_KILLED"}]

    keep_set = _top_pct_tickers(elig, HOLD_TOP_PCT)
    score_map = {r["ticker"]: r for r in elig}

    # Sell names outside top 30%
    kept = []
    for p in positions:
        if p["ticker"] in keep_set:
            kept.append(p)
            continue
        close_px = float(score_map.get(p["ticker"], {}).get("close") or p.get("last_mark_price") or p["execution_price"])
        fill = _fill_price(conn, p["ticker"], asof, close_px, "sell")
        # Floor-lock / volume==0 censor: skip fill — censored bar, not NEXT_OPEN.
        # Emit SKIP rather than a phantom fill; position stays held until liquidity returns.
        if fill.get("floor_locked") or fill.get("price") is None:
            trades.append({
                "action": "SKIP_REBALANCE",
                "ticker": p["ticker"],
                "reason": "FLOOR_LOCKED_CENSORED",
                **fill,
            })
            kept.append(p)
            continue
        gross_sell = p["shares"] * fill["price"]
        sell_comm = max(round(gross_sell * FEE_SELL_PCT, 2), 5.0) if gross_sell > 0 else 0.0
        proceeds = round(gross_sell - sell_comm, 2)
        cash = round(cash + proceeds, 2)
        trades.append({
            "action": "SELL",
            "ticker": p["ticker"],
            "shares": p["shares"],
            "reason": "OUTSIDE_TOP_30PCT",
            **fill,
            "proceeds": proceeds,
        })

    if safety_only:
        return kept, cash, trades

    # Sector counts among kept
    sector_counts = {}
    for p in kept:
        sector_counts[p.get("sector") or "Unknown"] = sector_counts.get(p.get("sector") or "Unknown", 0) + 1

    held = {p["ticker"] for p in kept}
    target_alloc = INITIAL_CAPITAL / TARGET_POSITIONS

    for cand in elig:
        if len(kept) >= TARGET_POSITIONS:
            break
        t = cand["ticker"]
        if t in held:
            continue
        try:
            from anti_manipulation_engine import is_ticker_blacklisted
            is_b, b_reason = is_ticker_blacklisted(t, asof_date=asof)
            if is_b:
                trades.append({"action": "SKIP_REBALANCE", "ticker": t, "reason": f"BLACKLISTED_{b_reason}"})
                continue
        except Exception:
            trades.append({"action": "SKIP_REBALANCE", "ticker": t, "reason": "BLACKLIST_CHECK_ERROR_FAIL_CLOSED"})
            continue
        sec = cand.get("sector") or "Unknown"
        if sector_counts.get(sec, 0) >= SECTOR_MAX:
            continue
        close_px = float(cand["close"])
        fill = _fill_price(conn, t, asof, close_px, "buy")
        # Floor-lock censor on entry: do not fill; emit skip (NaN) not NEXT_OPEN.
        if fill.get("floor_locked") or fill.get("price") is None:
            trades.append({"action": "SKIP_REBALANCE", "ticker": t, "reason": "FLOOR_LOCKED_CENSORED", **fill})
            continue
        eff = fill["price"] * (1.0 + FEE_BUY_PCT)
        shares = int(target_alloc / eff) if eff > 0 else 0
        gross_buy = shares * fill["price"]
        buy_comm = max(round(gross_buy * FEE_BUY_PCT, 2), 5.0) if gross_buy > 0 else 0.0
        cost = round(gross_buy + buy_comm, 2)
        if shares <= 0 or cost > cash:
            continue
        cash = round(cash - cost, 2)
        kept.append({
            "ticker": t,
            "sector": sec,
            "entry_date": fill["fill_date"],
            "signal_date": asof,
            "execution_price": fill["price"],
            "fill_source": fill["fill_source"],
            "shares": shares,
            "invested_equity": round(shares * fill["price"], 2),
            "buy_fee_deducted": round(shares * fill["price"] * FEE_BUY_PCT, 2),
            "pe": cand.get("pe_ratio"),
            "yield": cand.get("dividend_yield"),
            "entry_score": cand.get("score"),
            "model_id": MODEL_ID,
        })
        held.add(t)
        sector_counts[sec] = sector_counts.get(sec, 0) + 1
        trades.append({
            "action": "BUY",
            "ticker": t,
            "shares": shares,
            "reason": "TOP_RANK_FILL",
            **fill,
            "cost": cost,
        })

    return kept, cash, trades


def init_or_update_v2_forward_ledger(force_reinit: bool = False):
    PORT_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.row_factory = sqlite3.Row

    now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
    feat_summary = build_features_for_date()
    latest_date = feat_summary.get("date")
    if not latest_date:
        latest_date = conn.execute("SELECT MAX(date) FROM prices").fetchone()[0]

    if LEDGER_V2_FILE.exists() and not force_reinit:
        with open(LEDGER_V2_FILE, encoding="utf-8") as f:
            ledger = json.load(f)
        for i in range(1, len(ledger.get("blocks", []))):
            prev_b = ledger["blocks"][i - 1]
            curr_b = ledger["blocks"][i]
            expected = compute_sha256(json.dumps(prev_b["data"], sort_keys=True) + prev_b["prev_hash"])
            if curr_b["prev_hash"] != expected:
                raise ValueError(f"FATAL: Ledger Hash Chain Broken at Block {i}!")
    else:
        genesis_data = {
            "epoch": "EPOCH-2-LIVE-PROSPECTIVE-2026",
            "registered_at": now_utc,
            "model_id": MODEL_ID,
            "initial_cash": INITIAL_CAPITAL,
            "current_cash": INITIAL_CAPITAL,
            "portfolio_nav": INITIAL_CAPITAL,
            "benchmark": "EQUAL_WEIGHTED_CATEGORY_A_PRICE",
            "nav_history": [INITIAL_CAPITAL],
            "strategy_status": "ACTIVE",
            "rules": {
                "hold_buffer_top_pct": HOLD_TOP_PCT * 100,
                "rebalance_min_bars": REBALANCE_MIN_BARS,
                "execution_fill": "NEXT_SESSION_OPEN_PLUS_10BPS",
                "round_trip_fee_pct": ROUND_TRIP_COST_PCT,
                "kill_excess_pct": KILL_EXCESS_PCT,
                "kill_max_dd_pct": KILL_MAX_DD_PCT,
            },
            "positions": [],
            "last_rebalance_date": None,
        }
        gh = compute_sha256(json.dumps(genesis_data, sort_keys=True) + "GENESIS")
        ledger = {
            "genesis_hash": gh,
            "blocks": [{"block_index": 0, "timestamp": now_utc, "prev_hash": "GENESIS", "data": genesis_data, "block_hash": gh}],
        }

    latest_block = ledger["blocks"][-1]
    b_data = dict(latest_block["data"])
    scored = load_scored_universe(latest_date)
    elig = _eligible_ranked(scored)

    # Full universe log
    log_rows = [
        {
            "ticker": r["ticker"],
            "sector": r.get("sector"),
            "price": r.get("close"),
            "pe": r.get("pe_ratio"),
            "de": r.get("debt_equity"),
            "yield": r.get("dividend_yield"),
            "rsi_14": r.get("rsi_14"),
            "score": r.get("score"),
            "is_eligible": bool(r.get("is_eligible")),
        }
        for r in scored
    ]
    with open(FULL_UNIVERSE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "date": latest_date,
            "timestamp": now_utc,
            "model_id": MODEL_ID,
            "universe_size": len(log_rows),
            "eligible_count": len(elig),
            "ranks": log_rows,
            "top_20": log_rows[:20],
        }, ensure_ascii=False) + "\n")
    _dedupe_jsonl(FULL_UNIVERSE_LOG)

    # Daily IC (1-bar forward when available)
    ic_row = _daily_ic(conn, latest_date, scored)
    if ic_row:
        with open(IC_DAILY_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(ic_row) + "\n")
        _dedupe_jsonl(IC_DAILY_LOG)

    positions = list(b_data.get("positions") or [])
    cash = float(b_data.get("current_cash", INITIAL_CAPITAL))
    nav_history = list(b_data.get("nav_history") or [INITIAL_CAPITAL])
    status = b_data.get("strategy_status", "ACTIVE")

    # Kill check vs EQW from genesis/registration baseline
    baseline = (b_data.get("registered_at") or "")[:10] or (positions[0]["entry_date"] if positions else latest_date)
    if positions and positions[0].get("entry_date"):
        baseline = min(baseline, positions[0]["entry_date"]) if baseline else positions[0]["entry_date"]
    # Prefer first position entry as capital deploy date
    deploy = b_data.get("last_rebalance_date") or (positions[0].get("entry_date") if positions else baseline)

    nav, positions, cash = _mark_to_market(conn, positions, cash, latest_date, prev_asof=b_data.get("asof_price_date"))
    if not nav_history or nav_history[-1] != nav:
        nav_history.append(nav)
    max_dd = _compute_max_dd(nav_history)

    eqw = equal_weight_category_a_nav(deploy or latest_date, latest_date)
    eqw_ret = eqw.get("return_pct") if eqw.get("ok") else 0.0
    strat_ret = round(((nav - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100, 2)
    excess = round(strat_ret - (eqw_ret or 0.0), 2)

    killed = status == "KILLED"
    kill_reason = b_data.get("kill_reason")
    if not killed:
        if excess < KILL_EXCESS_PCT:
            killed = True
            kill_reason = f"excess {excess}% < {KILL_EXCESS_PCT}%"
        elif max_dd < KILL_MAX_DD_PCT:
            killed = True
            kill_reason = f"max_dd {max_dd}% < {KILL_MAX_DD_PCT}%"
    if killed:
        status = "KILLED"

    trades = []
    rebalanced = False
    safety_rebalance = _requires_safety_rebalance(positions, elig)
    if not positions and not killed:
        # Initial open via rebalance logic
        positions, cash, trades = _rebalance(conn, [], cash, elig, latest_date, False)
        rebalanced = True
        b_data["last_rebalance_date"] = latest_date
        nav, positions, cash = _mark_to_market(conn, positions, cash, latest_date)
        print(f"[EPOCH 2] Opened {len(positions)} positions asof={latest_date}")
    elif (safety_rebalance or _should_rebalance(conn, b_data, latest_date)) and (
        safety_rebalance or b_data.get("asof_price_date") != latest_date
    ):
        positions, cash, trades = _rebalance(
            conn,
            positions,
            cash,
            elig,
            latest_date,
            killed and not safety_rebalance,
            safety_only=safety_rebalance,
        )
        rebalanced = True
        b_data["last_rebalance_date"] = latest_date
        nav, positions, cash = _mark_to_market(conn, positions, cash, latest_date)
        reason = "SAFETY_CLEANUP" if safety_rebalance else "SCHEDULED"
        print(f"[EPOCH 2] Rebalance asof={latest_date} reason={reason} trades={len(trades)} killed={killed}")

    # Skip duplicate block same asof with no change
    if b_data.get("asof_price_date") == latest_date and not rebalanced and not force_reinit:
        if abs(float(b_data.get("portfolio_nav", 0)) - nav) < 0.02 and b_data.get("model_id") == MODEL_ID:
            print(f"[EPOCH 2] Already current asof={latest_date} NAV={nav:,.2f} status={status}")
            conn.close()
            return

    new_data = dict(b_data)
    new_data.update({
        "positions": positions,
        "current_cash": cash,
        "portfolio_nav": nav,
        "asof_price_date": latest_date,
        "model_id": MODEL_ID,
        "updated_at": now_utc,
        "feature_build": feat_summary,
        "nav_history": nav_history[-500:],
        "max_drawdown_pct": max_dd,
        "strat_return_pct": strat_ret,
        "eqw_return_pct": eqw_ret,
        "excess_vs_eqw_pct": excess,
        "strategy_status": status,
        "kill_reason": kill_reason,
        "last_trades": trades,
        "daily_ic": ic_row,
        "eligible_count": len(elig),
    })
    if rebalanced:
        new_data["last_rebalance_date"] = latest_date

    prev_hash = latest_block["block_hash"]
    new_block = {
        "block_index": len(ledger["blocks"]),
        "timestamp": now_utc,
        "prev_hash": prev_hash,
        "data": new_data,
        "block_hash": compute_sha256(json.dumps(new_data, sort_keys=True) + prev_hash),
    }
    ledger["blocks"].append(new_block)
    with open(LEDGER_V2_FILE, "w", encoding="utf-8") as f:
        json.dump(ledger, f, indent=2)

    print(
        f"[EPOCH 2] Block {new_block['block_index']} asof={latest_date} "
        f"NAV={nav:,.2f} excess={excess:+.2f}% dd={max_dd}% status={status} "
        f"ic={ic_row.get('rank_ic') if ic_row else 'n/a'}"
    )
    if killed:
        print(f"[EPOCH 2] KILL ACTIVE: {kill_reason}")
    conn.close()


if __name__ == "__main__":
    init_or_update_v2_forward_ledger()
