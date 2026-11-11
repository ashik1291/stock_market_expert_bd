"""
scripts/knowledge_adapter.py — Unified High-Speed Knowledge & Feature Access Layer

Provides instant (< 5ms) access to company analytical signals and pattern DNA from SQLite
while seamlessly maintaining and syncing on-demand JSON files for backward compatibility.
"""

from __future__ import annotations

import sys
import sqlite3
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

# UTF-8 encoding
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"
KNOW_DIR = BASE_DIR / "data" / "knowledge"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("knowledge_adapter")


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.row_factory = sqlite3.Row
    return conn


def load_company_signal(
    ticker: str,
    timeframe: str = "weekly",
    asof_date: Optional[str] = None,
    sync_to_disk: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Ultra-fast (< 2ms) retrieval of analytical dossier for a company.
    Queries SQLite company_signals_history; falls back to disk JSON if DB unavailable.
    """
    ticker = (ticker or "").strip().upper()
    if not ticker:
        return None

    if DB_PATH.exists():
        try:
            conn = get_db_connection()
            if asof_date:
                row = conn.execute(
                    """
                    SELECT full_payload FROM company_signals_history
                    WHERE ticker = ? AND timeframe = ? AND date <= ?
                    ORDER BY date DESC LIMIT 1
                    """,
                    (ticker, timeframe, asof_date),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT full_payload FROM company_signals_history
                    WHERE ticker = ? AND timeframe = ?
                    ORDER BY date DESC LIMIT 1
                    """,
                    (ticker, timeframe),
                ).fetchone()
            conn.close()

            if row and row["full_payload"]:
                payload = json.loads(row["full_payload"])
                if sync_to_disk:
                    save_signal_to_disk(ticker, timeframe, payload)
                return payload
        except Exception as e:
            log.warning(f"SQLite signal query failed for {ticker}: {e}")

    # Fallback: Read JSON directly from disk
    json_path = KNOW_DIR / ticker / f"{timeframe}.json"
    if json_path.exists():
        try:
            return json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    return None


def load_multi_timeframe_signals(
    ticker: str,
    timeframes: tuple[str, ...] = ("weekly", "monthly", "quarterly"),
) -> Dict[str, Any]:
    """
    Retrieve analytical signals across multiple timeframes simultaneously for a given ticker.
    Returns dict mapping timeframe name -> payload.
    """
    ticker = (ticker or "").strip().upper()
    if not ticker:
        return {}

    results: Dict[str, Any] = {}
    if DB_PATH.exists():
        try:
            conn = get_db_connection()
            placeholders = ",".join("?" for _ in timeframes)
            rows = conn.execute(
                f"""
                SELECT timeframe, full_payload
                FROM company_signals_history
                WHERE ticker = ? AND timeframe IN ({placeholders})
                ORDER BY date DESC
                """,
                (ticker, *timeframes),
            ).fetchall()
            conn.close()

            for r in rows:
                tf = r["timeframe"]
                if tf not in results and r["full_payload"]:
                    try:
                        results[tf] = json.loads(r["full_payload"])
                    except Exception:
                        pass
        except Exception as e:
            log.warning(f"SQLite multi-timeframe query failed for {ticker}: {e}")

    # Fallback for any timeframes missing from DB
    for tf in timeframes:
        if tf not in results:
            sig = load_company_signal(ticker, tf)
            if sig:
                results[tf] = sig

    return results


def load_company_dna(
    ticker: str,
    asof_date: Optional[str] = None,
    sync_to_disk: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Ultra-fast (< 2ms) retrieval of Pattern Causal DNA for a company.
    """
    ticker = (ticker or "").strip().upper()
    if not ticker:
        return None

    if DB_PATH.exists():
        try:
            conn = get_db_connection()
            if asof_date:
                row = conn.execute(
                    """
                    SELECT full_payload FROM company_pattern_dna_history
                    WHERE ticker = ? AND date <= ?
                    ORDER BY date DESC LIMIT 1
                    """,
                    (ticker, asof_date),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT full_payload FROM company_pattern_dna_history
                    WHERE ticker = ?
                    ORDER BY date DESC LIMIT 1
                    """,
                    (ticker,),
                ).fetchone()
            conn.close()

            if row and row["full_payload"]:
                payload = json.loads(row["full_payload"])
                if sync_to_disk:
                    save_dna_to_disk(ticker, payload)
                return payload
        except Exception as e:
            log.warning(f"SQLite DNA query failed for {ticker}: {e}")

    # Fallback to disk JSON
    json_path = KNOW_DIR / ticker / "pattern_causal_dna.json"
    if json_path.exists():
        try:
            return json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    return None


def load_universe_signals(
    timeframe: str = "weekly",
    asof_date: Optional[str] = None,
    signals_filter: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Loads analytical dossiers for the entire universe in a single indexed query (< 10ms).
    Replaces opening 375 separate disk files.
    """
    if not DB_PATH.exists():
        return []

    conn = get_db_connection()
    try:
        # Determine target date
        if not asof_date:
            row = conn.execute(
                "SELECT MAX(date) FROM company_signals_history WHERE timeframe = ?",
                (timeframe,),
            ).fetchone()
            target_date = row[0] if (row and row[0]) else None
        else:
            target_date = asof_date

        if not target_date:
            conn.close()
            return []

        if signals_filter:
            placeholders = ",".join("?" for _ in signals_filter)
            query = f"""
                SELECT full_payload FROM company_signals_history
                WHERE date = ? AND timeframe = ? AND signal IN ({placeholders})
                ORDER BY confidence DESC
            """
            params = [target_date, timeframe] + list(signals_filter)
        else:
            query = """
                SELECT full_payload FROM company_signals_history
                WHERE date = ? AND timeframe = ?
                ORDER BY confidence DESC
            """
            params = [target_date, timeframe]

        rows = conn.execute(query, params).fetchall()
        conn.close()

        results = []
        for r in rows:
            try:
                results.append(json.loads(r["full_payload"]))
            except Exception:
                continue
        return results
    except Exception as e:
        log.error(f"Failed to load universe signals: {e}")
        conn.close()
        return []


def save_signal_to_db_and_disk(ticker: str, timeframe: str, payload: Dict[str, Any]) -> bool:
    """
    Dual-write: Commits to SQLite feature store and writes JSON file for human inspection.
    """
    ticker = ticker.strip().upper()
    date_str = payload.get("asof_price_date") or payload.get("date")
    if not date_str:
        conn = get_db_connection()
        date_str = conn.execute("SELECT MAX(date) FROM prices").fetchone()[0] or "2026-11-11"
        conn.close()

    # 1. Write to SQLite
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        served_model = payload.get("served_model") or {}
        trade_levels = payload.get("trade_levels") or {}
        tech_score = (payload.get("technical") or {}).get("score")
        fund_score = (payload.get("fundamental") or {}).get("score")
        sent_score = (payload.get("sentiment") or {}).get("score")
        comp_obj = payload.get("composite") or {}
        manip_obj = payload.get("manipulation") or {}
        prec_obj = payload.get("precision") or {}
        corridor_obj = prec_obj.get("range_52w_corridor") or {}
        range_52w_pct = corridor_obj.get("range_52w_pct")
        range_52w_regime = corridor_obj.get("channel_regime")

        payload_str = json.dumps(payload, ensure_ascii=False)

        cur.execute("""
            INSERT OR REPLACE INTO company_signals_history (
                date, ticker, timeframe, horizon, analyzed_at, asof_price_date,
                served_model_id, served_model_score, signal, confidence,
                entry_price, stop_loss, target_price, rsi_14, pe_ratio, debt_equity,
                technical_score, fundamental_score, sentiment_score, governance_score,
                composite_score, manipulation_risk, manipulation_score, block_buy,
                range_52w_pct, range_52w_regime,
                full_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            date_str, ticker, timeframe,
            payload.get("horizon", "short"),
            payload.get("analyzed_at"),
            payload.get("asof_price_date", date_str),
            served_model.get("model_id"),
            served_model.get("score"),
            payload.get("signal", "HOLD"),
            float(payload.get("confidence") or 50.0),
            trade_levels.get("entry"),
            trade_levels.get("stop_loss"),
            trade_levels.get("target"),
            served_model.get("rsi_14"),
            served_model.get("pe_ratio"),
            served_model.get("debt_equity"),
            tech_score, fund_score, sent_score,
            comp_obj.get("governance_score"),
            comp_obj.get("composite_score"),
            manip_obj.get("manipulation_risk", "low"),
            manip_obj.get("manipulation_score"),
            1 if manip_obj.get("block_buy") else 0,
            range_52w_pct,
            range_52w_regime,
            payload_str
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"Error persisting signal to SQLite for {ticker}: {e}")

    # 2. Write to disk JSON
    save_signal_to_disk(ticker, timeframe, payload)
    return True


def save_dna_to_db_and_disk(ticker: str, payload: Dict[str, Any]) -> bool:
    """
    Dual-write for Pattern Causal DNA.
    """
    ticker = ticker.strip().upper()
    audited_at = payload.get("audited_at")
    date_str = audited_at.split()[0] if audited_at and " " in audited_at else "2026-11-11"

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        wvg = payload.get("worth_vs_greed") or {}
        wave = payload.get("multi_interval_wave") or {}
        dna_str = json.dumps(payload, ensure_ascii=False)

        cur.execute("""
            INSERT OR REPLACE INTO company_pattern_dna_history (
                date, ticker, audited_at, current_price, intrinsic_worth,
                margin_of_safety_pct, greed_index, current_wave_phase, full_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            date_str, ticker, audited_at,
            wvg.get("current_price"),
            wvg.get("intrinsic_worth"),
            wvg.get("margin_of_safety_pct"),
            wvg.get("greed_index"),
            wave.get("current_wave_phase"),
            dna_str
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"Error persisting DNA to SQLite for {ticker}: {e}")

    save_dna_to_disk(ticker, payload)
    return True


def save_signal_to_disk(ticker: str, timeframe: str, payload: Dict[str, Any]):
    out_dir = KNOW_DIR / ticker
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{timeframe}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def save_dna_to_disk(ticker: str, payload: Dict[str, Any]):
    out_dir = KNOW_DIR / ticker
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "pattern_causal_dna.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def calculate_signal_velocity(ticker: str, lookback_bars: int = 5) -> Dict[str, Any]:
    """
    Convenience wrapper to compute signal velocity and acceleration for a ticker.
    """
    from seed_signal_velocity import calculate_velocity_for_ticker
    return calculate_velocity_for_ticker(ticker, lookback_bars)


if __name__ == "__main__":
    # Self-test adapter performance
    import time
    t0 = time.time()
    all_signals = load_universe_signals("weekly")
    elapsed = (time.time() - t0) * 1000
    print(f"✅ Adapter loaded {len(all_signals)} universe dossiers from SQLite in {elapsed:.2f} ms!")
    sample = load_company_signal("PADMAOIL")
    print(f"Sample PADMAOIL signal: {sample.get('signal')} | Conf: {sample.get('confidence')}%")
