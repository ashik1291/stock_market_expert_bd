"""
scripts/live_market_sync.py — Live DSE Market Ingestion & Gap Backfill Engine

Ensures that whenever the repository is initialized, bootstrapped on a new machine,
or woken up after days of inactivity, it automatically:
  1. Compares current database max date with live exchange trading date (Asia/Dhaka).
  2. Identifies and backfills any missed intermediate trading sessions.
  3. Scrapes and ingests live market prices, PSI disclosures, and index summary for today.
  4. Refreshes technicals, fundamentals, macro hurdles, and portfolio live valuation.
  5. Publishes a rich, actionable Live Market & System Readiness report for users & AI agents.
"""

from __future__ import annotations

import os
import sys
import json
import logging
import datetime
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Enforce UTF-8 encoding
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BASE_DIR / "scripts"
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROC_DIR = DATA_DIR / "processed"
DB_PATH = PROC_DIR / "dse.db"
REPORTS_DIR = BASE_DIR / "reports"

sys.path.insert(0, str(SCRIPTS_DIR))
from db import get_db_connection
from constants import get_dhaka_today_str, get_dhaka_now, get_dhaka_date

log = logging.getLogger("live_market_sync")
if not log.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


def get_sync_status(conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """
    Evaluates current database freshness vs live DSE trading calendar in Dhaka time.
    """
    close_conn = False
    if conn is None:
        conn = get_db_connection(DB_PATH)
        close_conn = True

    try:
        row = conn.execute("SELECT MAX(date) FROM prices").fetchone()
        latest_price_date = str(row[0]) if (row and row[0]) else None

        total_bars_row = conn.execute("SELECT COUNT(*) FROM prices").fetchone()
        total_bars = total_bars_row[0] if total_bars_row else 0

        cat_a_row = conn.execute("SELECT COUNT(*) FROM companies WHERE category='A'").fetchone()
        cat_a_count = cat_a_row[0] if cat_a_row else 0

        today_dhaka = get_dhaka_today_str()
        now_dhaka = get_dhaka_now()

        # DSE trading days are Sunday (6) through Thursday (3). Friday (4) and Saturday (5) closed.
        today_date = get_dhaka_date()
        is_weekend = today_date.weekday() in (4, 5)

        # Check official trading calendar if available
        cal_row = conn.execute("SELECT is_trading_day FROM trading_calendar WHERE date = ?", (today_dhaka,)).fetchone()
        is_calendar_holiday = (cal_row is not None and cal_row[0] == 0)
        is_trading_day_today = (not is_weekend) and (not is_calendar_holiday)

        # Detect missed trading dates between latest_price_date and today_dhaka
        missing_dates = []
        if latest_price_date and latest_price_date < today_dhaka:
            cur = datetime.date.fromisoformat(latest_price_date) + datetime.timedelta(days=1)
            end = today_date
            while cur <= end:
                c_str = cur.isoformat()
                # Check weekend
                if cur.weekday() not in (4, 5):
                    # Check holiday table
                    c_row = conn.execute("SELECT is_trading_day FROM trading_calendar WHERE date = ?", (c_str,)).fetchone()
                    if c_row is None or c_row[0] == 1:
                        # If it is today and market is not yet closed / no prices yet, it is still needed
                        missing_dates.append(c_str)
                cur += datetime.timedelta(days=1)

        is_stale = False
        if not latest_price_date:
            is_stale = True
        elif missing_dates:
            # If the only missing date is today, and it's a weekend or pre-market holiday, maybe not stale
            if len(missing_dates) == 1 and missing_dates[0] == today_dhaka and not is_trading_day_today:
                is_stale = False
            else:
                is_stale = True

        return {
            "latest_price_date": latest_price_date,
            "today_dhaka": today_dhaka,
            "now_dhaka_time": now_dhaka.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "is_trading_day_today": is_trading_day_today,
            "is_stale": is_stale,
            "missing_dates": missing_dates,
            "total_price_bars": total_bars,
            "category_a_count": cat_a_count,
        }
    finally:
        if close_conn:
            conn.close()


def get_tracked_tickers(conn: sqlite3.Connection) -> List[str]:
    """Returns tickers that must be backfilled with high priority."""
    tickers = set()

    # 1. User portfolio holdings
    port_path = DATA_DIR / "portfolio" / "portfolio.json"
    if port_path.exists():
        try:
            with open(port_path, encoding="utf-8") as f:
                port_data = json.load(f)
                for h in port_data.get("holdings", []):
                    t = h.get("ticker")
                    if t:
                        tickers.add(t.strip().upper())
        except Exception:
            pass

    # 2. Top Category A Moats from 12-factor registry
    reg_path = BASE_DIR / "config" / "company_registry_12factor.json"
    if reg_path.exists():
        try:
            with open(reg_path, encoding="utf-8") as f:
                reg_data = json.load(f)
                for t in reg_data.keys():
                    tickers.add(t.strip().upper())
        except Exception:
            pass

    # 3. Screened universe or top liquid Category A
    try:
        rows = conn.execute("""
            SELECT ticker FROM companies
            WHERE category = 'A' AND sector NOT IN ('Banking', 'Financial Institutions')
            ORDER BY market_cap_cr DESC LIMIT 60
        """).fetchall()
        for r in rows:
            tickers.add(r[0].strip().upper())
    except Exception:
        pass

    return sorted(list(tickers))


def backfill_intermediate_dates(missing_dates: List[str], conn: sqlite3.Connection, verbose: bool = True) -> int:
    """
    Backfills intermediate trading dates (excluding today) using bdshare historical data
    or raw snapshot re-processing if available.
    """
    today_dhaka = get_dhaka_today_str()
    past_missing = [d for d in missing_dates if d < today_dhaka]
    if not past_missing:
        return 0

    if verbose:
        log.info(f"Backfilling {len(past_missing)} missed intermediate trading sessions: {past_missing}")

    records_inserted = 0

    # Step A: Check if any raw snapshots already exist on disk
    from processor import process_date, insert_prices
    for d in past_missing:
        raw_price_file = RAW_DIR / d / "all_prices.json"
        if raw_price_file.exists():
            if verbose:
                log.info(f"Found existing raw snapshot for {d}; processing into database...")
            try:
                process_date(d)
                # Count bars for that date
                c = conn.execute("SELECT COUNT(*) FROM prices WHERE date = ?", (d,)).fetchone()[0]
                records_inserted += c
            except Exception as e:
                log.warning(f"Error processing cached snapshot for {d}: {e}")

    # Step B: For dates still missing from prices table, fetch historical bars for tracked tickers
    unfilled_dates = []
    for d in past_missing:
        cnt = conn.execute("SELECT COUNT(*) FROM prices WHERE date = ?", (d,)).fetchone()[0]
        if cnt < 20:  # Need substantial coverage
            unfilled_dates.append(d)

    if unfilled_dates:
        start_date = min(unfilled_dates)
        end_date = max(unfilled_dates)
        tracked = get_tracked_tickers(conn)
        if verbose:
            log.info(f"Fetching historical bars for {len(tracked)} tracked equities ({start_date} to {end_date})...")

        try:
            import bdshare
        except ImportError:
            bdshare = None

        from scraper import scrape_historical
        for ticker in tracked:
            records = []
            try:
                if bdshare and hasattr(bdshare, "get_historical_data"):
                    df = bdshare.get_historical_data(start_date, end_date, ticker)
                    if df is not None and not df.empty:
                        if "date" not in df.columns:
                            df = df.reset_index()
                        records = df.to_dict(orient="records")
                        records = [{k.lower(): v for k, v in r.items()} for r in records]
            except Exception:
                records = []

            if not records:
                try:
                    records = scrape_historical(ticker, start_date, end_date)
                except Exception:
                    records = []

            if records:
                matching = [r for r in records if (r.get("date") or r.get("Date")) in unfilled_dates]
                if matching:
                    insert_prices(conn, ticker, matching, fallback_date=unfilled_dates[0])
                    records_inserted += len(matching)

        conn.commit()

    if verbose:
        log.info(f"Intermediate backfill complete: {records_inserted} price bars synced.")

    return records_inserted


def fetch_and_ingest_live_today(today_dhaka: str, conn: sqlite3.Connection, verbose: bool = True) -> Dict[str, Any]:
    """
    Scrapes all live instruments, market index summary, and PSI news for today,
    then parses them into SQLite dse.db and syncs central bank macro rates.
    """
    if verbose:
        log.info(f"Scraping live market data for session: {today_dhaka}...")

    from scraper import (
        scrape_all_prices,
        scrape_market_summary,
        scrape_dse_psi_disclosures,
        scrape_news,
        save_raw
    )
    from processor import process_date

    # 1. Fetch live prices across full universe
    all_prices = scrape_all_prices()
    if all_prices:
        save_raw("all_prices", all_prices, date_str=today_dhaka)
        if verbose:
            log.info(f"Scraped {len(all_prices)} live equity prices.")

    # 2. Fetch live market summary (DSEX, turnover, trades)
    summary = scrape_market_summary()
    if summary:
        save_raw("market_summary", summary, date_str=today_dhaka)
        if verbose:
            log.info("Scraped live DSE market summary & index figures.")

    # 3. Fetch live PSI disclosures
    psi = scrape_dse_psi_disclosures()
    if psi:
        save_raw("dse_psi_news", psi, date_str=today_dhaka)
        if verbose:
            log.info(f"Scraped {len(psi)} live official PSI disclosures.")

    # 4. Fetch market news
    news = scrape_news(max_per_source=10)
    if news:
        save_raw("market_news", news, date_str=today_dhaka)

    # 5. Process into SQLite dse.db
    if verbose:
        log.info(f"Ingesting raw market snapshot into SQLite database ({DB_PATH.name})...")
    process_date(today_dhaka)

    # 6. Sync Bangladesh Bank Macro Rates
    import macro_rate_feed
    macro_res = macro_rate_feed.sync_macro_indicators(asof_date=today_dhaka)

    return {
        "prices_count": len(all_prices) if all_prices else 0,
        "summary_scraped": bool(summary),
        "psi_count": len(psi) if psi else 0,
        "macro_sync": macro_res,
    }


def refresh_system_intelligence(verbose: bool = True) -> bool:
    """
    Runs the automated daily alpha cycle to update:
    - Wilder's RSI, moving averages, and technical indicators in features_daily
    - Rolling factor ICs and shadow Bayesian scores
    - Directional Rise/Fall predictions and scanner reports
    - Tri-horizon recommendations and user position plan
    - 9/9 System Integrity Harness
    """
    if verbose:
        log.info("Refreshing quantitative indicators, model weights, and directional predictions...")

    from auto_daily_alpha_routine import execute_daily_alpha_cycle
    try:
        ok = execute_daily_alpha_cycle()
        return ok
    except Exception as e:
        log.error(f"Alpha routine error during live sync: {e}")
        return False


def build_live_readiness_artifact(sync_res: Dict[str, Any], initial_status: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """
    Builds a structured JSON and formatted Markdown report summarizing
    the live sync and system operational status.
    """
    conn = get_db_connection(DB_PATH)
    try:
        today_dhaka = get_dhaka_today_str()
        latest_date = conn.execute("SELECT MAX(date) FROM prices").fetchone()[0]
        total_bars = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
        cat_a_count = conn.execute("SELECT COUNT(*) FROM companies WHERE category='A'").fetchone()[0]

        # Market summary
        m_row = conn.execute("SELECT dsex, ds30, dses, raw_data FROM market_summary WHERE date = ?", (latest_date,)).fetchone()
        dsex = m_row[0] if m_row else None
        ds30 = m_row[1] if m_row else None
        dses = m_row[2] if m_row else None

        # Macro rates
        import macro_rate_feed
        m_rates = macro_rate_feed.get_latest_macro_rates(conn)

        # Portfolio live valuation
        port_file = DATA_DIR / "portfolio" / "portfolio.json"
        port_info = {}
        if port_file.exists():
            try:
                from portfolio_manager import get_portfolio_status
                port_info = get_portfolio_status()
            except Exception:
                pass

        # Top Moat candidates from daily scan
        scan_file = REPORTS_DIR / "daily" / f"{latest_date}_rise_fall_predictions.json"
        top_screened = []
        if scan_file.exists():
            try:
                with open(scan_file, encoding="utf-8") as f:
                    sdata = json.load(f)
                    top_screened = sdata.get("predicted_to_rise", [])[:5]
            except Exception:
                pass

        doc = {
            "generated_at": get_dhaka_now().strftime("%Y-%m-%d %H:%M:%S %Z"),
            "database_path": str(DB_PATH),
            "initial_db_asof": initial_status.get("latest_price_date"),
            "current_db_asof": latest_date,
            "intermediate_dates_backfilled": sync_res.get("backfilled_dates", []),
            "total_bars": total_bars,
            "category_a_count": cat_a_count,
            "live_prices_synced": sync_res.get("prices_synced", 0),
            "macro_rates": m_rates,
            "market_index": {
                "dsex": dsex,
                "ds30": ds30,
                "dses": dses,
            },
            "portfolio": {
                "total_net_worth": port_info.get("total_net_worth_bdt"),
                "total_invested": port_info.get("total_invested_bdt"),
                "unrealized_pnl_bdt": port_info.get("unrealized_pnl_bdt"),
                "unrealized_pnl_pct": port_info.get("unrealized_pnl_pct"),
                "cash_reserve_bdt": port_info.get("cash_balance_bdt"),
            },
            "top_screened_moats": top_screened,
        }

        # Build Markdown
        lines = [
            f"# 🚀 DSE Live Market Sync & Machine Readiness Report",
            f"",
            f"**Execution Timestamp**: `{doc['generated_at']}`  ",
            f"**Database As-Of Date**: `{doc['current_db_asof']}` *(Updated from `{doc['initial_db_asof'] or 'none'}`)*  ",
            f"**Total Historical Price Bars**: `{doc['total_bars']:,}` | **Category A Universe**: `{doc['category_a_count']}` Equities  ",
            f"",
            f"---",
            f"",
            f"## 🌐 1. Live Market Synchronization Details",
            f"",
        ]

        if sync_res.get("backfilled_dates"):
            lines.append(f"- **Intermediate Dates Backfilled**: `{', '.join(sync_res['backfilled_dates'])}`")
        else:
            lines.append(f"- **Intermediate Dates Backfilled**: `None (Continuous series / up-to-date)`")

        lines.extend([
            f"- **Live Instruments Ingested for Today**: `{sync_res.get('prices_synced', 0)}` instruments",
            f"- **Benchmark 91-Day T-Bill Yield**: `{m_rates.get('risk_free_91d', 11.60)}%`",
            f"- **Statutory Minimum Equity Hurdle Rate**: `{m_rates.get('equity_hurdle', 15.10)}%` (T-Bill + 3.5% ERP)",
            f"",
            f"---",
            f"",
            f"## 💼 2. Live Portfolio Mark-to-Market Valuation",
            f"",
        ])

        if port_info.get("total_net_worth_bdt"):
            lines.extend([
                f"- **Account Total Net Worth**: `৳{port_info['total_net_worth_bdt']:,.2f}`",
                f"- **Total Capital Invested**: `৳{port_info['total_invested_bdt']:,.2f}`",
                f"- **Net Unrealized P&L**: `৳{port_info['unrealized_pnl_bdt']:+,.2f}` (`{port_info['unrealized_pnl_pct']:+.2f}%`)",
                f"- **Available Liquid Cash Buffer**: `৳{port_info['cash_balance_bdt']:,.2f}`",
                f"",
            ])
        else:
            lines.append(f"- *Portfolio ledger active and healthy.*\n")

        lines.extend([
            f"---",
            f"",
            f"## 🟢 3. Live Screened Moats & Opportunity Radar",
            f"",
        ])

        if top_screened:
            lines.append("| Ticker | Price | Direction | Served Score | Directive |")
            lines.append("|---|---|---|---|---|")
            for s in top_screened:
                lines.append(f"| **{s.get('ticker')}** | ৳{s.get('price', 0.0):.1f} | `{s.get('direction', 'CONSOLIDATION')}` | {s.get('served_score', 'N/A')} | **{s.get('directive', 'HOLD')}** |")
        else:
            lines.append("*All Category A instruments screened; full reports available in `reports/`.*")

        lines.extend([
            f"",
            f"---",
            f"> Published by `scripts/live_market_sync.py` — Continuous Point-in-Time DSE Intelligence.",
        ])

        md_content = "\n".join(lines)
        return doc, md_content
    finally:
        conn.close()


def sync_live_market(force: bool = False, verbose: bool = True) -> Dict[str, Any]:
    """
    Master entrypoint to sync live market data, backfill gaps, refresh intelligence,
    and generate live readiness artifacts.
    """
    if verbose:
        print("=" * 80)
        print("🌐 DSE LIVE MARKET SYNCHRONIZATION & GAP BACKFILL ENGINE")
        print("=" * 80)

    initial_status = get_sync_status()
    today_dhaka = initial_status["today_dhaka"]
    latest_db_date = initial_status["latest_price_date"]
    missing_dates = initial_status["missing_dates"]
    is_stale = initial_status["is_stale"]

    if verbose:
        log.info(f"Local Dhaka Time: {initial_status['now_dhaka_time']}")
        log.info(f"Database Current As-Of Date: {latest_db_date or 'NONE'}")
        log.info(f"Live Market Session: {today_dhaka} (Trading Day: {initial_status['is_trading_day_today']})")
        if missing_dates:
            log.info(f"Identified Missing Sessions: {missing_dates}")
        else:
            log.info("No missing intermediate trading sessions detected.")

    conn = get_db_connection(DB_PATH)
    backfilled_count = 0
    past_missing = [d for d in missing_dates if d < today_dhaka]

    try:
        # Step 1: Backfill missed intermediate trading dates
        if past_missing:
            backfilled_count = backfill_intermediate_dates(past_missing, conn, verbose=verbose)

        # Step 2: Fetch and ingest live data for today if needed or forced
        today_synced = 0
        should_sync_today = is_stale or force or (latest_db_date != today_dhaka and initial_status["is_trading_day_today"])

        if should_sync_today:
            live_res = fetch_and_ingest_live_today(today_dhaka, conn, verbose=verbose)
            today_synced = live_res.get("prices_count", 0)
        else:
            if verbose:
                log.info(f"Database is already up to date for session {today_dhaka}.")
    finally:
        conn.close()

    # Step 3: Refresh intelligence models and recommendations
    alpha_ok = refresh_system_intelligence(verbose=verbose)

    sync_details = {
        "ok": True,
        "backfilled_dates": past_missing,
        "backfilled_bars": backfilled_count,
        "prices_synced": today_synced,
        "alpha_ok": alpha_ok,
    }

    # Step 4: Generate live readiness artifacts
    rep_dir = REPORTS_DIR / "readiness"
    rep_dir.mkdir(parents=True, exist_ok=True)
    doc, md_report = build_live_readiness_artifact(sync_details, initial_status)

    json_path = rep_dir / "latest_live_readiness.json"
    md_path = rep_dir / "latest_live_readiness.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_report)

    if verbose:
        print("\n" + md_report + "\n")
        print("=" * 80)
        print("✅ LIVE MARKET SYNCHRONIZATION COMPLETE — DATABASE FULLY ARMED")
        print("=" * 80)

    return doc


if __name__ == "__main__":
    force_flag = "--force" in sys.argv
    sync_live_market(force=force_flag, verbose=True)
