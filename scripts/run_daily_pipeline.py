#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSE Quantitative Intelligence Engine — 1-Click Master Daily Pipeline Runner

Automates the complete institutional quantitative cycle in optimal sequence:
  1. Macro Rate Sync (91-day Bangladesh Bank T-bill yield hurdle)
  2. DSE Daily Price Scrape (Graceful handling of market sessions / holidays)
  3. Raw Data Processor (Normalizes price bars & volume into dse.db)
  4. Anti-Manipulation Engine (Full-market 395-ticker forensic surveillance)
  5. 5-Factor Fundamental Screener (NOCFPS, Debt, Margin of Safety, ROE, Governance)
  6. Daily Directional Scanner (Rise/Fall predictions with English & Bengali reports)
  7. Tri-Horizon Recommender (Weekly institutional asset plans + visual charts)
  8. Monthly Rebalance & Tactical Cash Buffer Check (10% liquid reserve enforcement)
  9. Portfolio Audit & Status (Break-even tracking, stop-loss / target buffers)
 10. System Integrity Harness (9/9 regression & leakage guard verification)

Usage:
  python scripts/run_daily_pipeline.py [--skip-scrape]
"""

import sys
import os
import subprocess
import datetime
import logging
from pathlib import Path

# Safe Windows stdout encoding reconfiguration
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("daily_pipeline")


def run_step(step_num: int, title: str, cmd: list[str], allow_fail: bool = False) -> bool:
    log.info(f"==> Step {step_num}: {title}...")
    start_t = datetime.datetime.now()
    try:
        res = subprocess.run(
            [sys.executable] + cmd,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        duration = (datetime.datetime.now() - start_t).total_seconds()
        if res.returncode == 0:
            log.info(f"    [SUCCESS] Step {step_num} finished in {duration:.1f}s")
            return True
        else:
            if allow_fail:
                log.warning(f"    [WARNING] Step {step_num} returned code {res.returncode} (allowed to continue).")
                if res.stderr:
                    log.warning(f"    Error detail: {res.stderr.strip()[:200]}")
                return True
            else:
                log.error(f"    [FAILED] Step {step_num} failed with code {res.returncode}")
                if res.stderr:
                    log.error(f"    {res.stderr.strip()[:300]}")
                return False
    except Exception as e:
        log.error(f"    [EXCEPTION] Step {step_num} exception: {e}")
        return allow_fail


def main():
    print("=" * 80)
    print(">> DSE QUANTITATIVE ENGINE -- INSTITUTIONAL DAILY PIPELINE RUNNER")
    print(f"Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S BST')}")
    print("=" * 80)

    skip_scrape = "--skip-scrape" in sys.argv

    steps = [
        # (title, cmd, allow_fail)
        ("Synchronizing Macro Benchmark Yields (T-bill & Inflation)", ["scripts/macro_rate_feed.py", "--sync"], True),
    ]

    if not skip_scrape:
        steps.append(
            ("Scraping DSE Daily Prices", ["scripts/scraper.py", "price"], True)
        )
        steps.append(
            ("Processing Raw Scraped Data into SQLite", ["scripts/processor.py"], True)
        )

    steps.extend([
        ("Running Anti-Manipulation Surveillance Engine (395 Tickers)", ["scripts/anti_manipulation_engine.py"], False),
        ("Running 5-Factor Fundamental Screener", ["scripts/five_factor_fundamental_screener.py"], False),
        ("Generating Daily Directional Rise/Fall Predictions (Bilingual)", ["scripts/daily_rise_fall_scanner.py", "weekly"], False),
        ("Scanning Corporate Action & Dividend Catalysts (Bilingual)", ["scripts/event_driven_alpha_engine.py"], False),
        ("Generating Tri-Horizon Recommendations & Visual Charts (Bilingual)", ["scripts/recommender.py", "weekly"], False),
        ("Calculating Monthly Rebalancing & 10% Cash Reserve Plan", ["scripts/monthly_rebalance_engine.py", "2000"], False),
        ("Processing Corporate Actions & Disbursing Cash Dividends", ["scripts/corporate_action_processor.py"], False),
        ("Advancing Forward Test Ledger & Factor Logs", ["scripts/forward_test_ledger_v2.py"], False),
        ("Syncing Open-End Mutual Fund NAV & Valuation", ["scripts/mutual_fund_tracker.py"], True),
        ("Auditing Real Portfolio Positions & Break-even Levels", ["scripts/portfolio_manager.py", "status"], False),
        ("Executing Real-Time Portfolio Sentinel Valuation & Guards", ["scripts/portfolio_sentinel.py"], False),
        ("Publishing Chief Financial Advisor Executive Dossier", ["scripts/financial_advisor.py"], False),
        ("Executing Integrity Harness & Leakage Verification", ["scripts/integrity_harness.py"], False),
    ])

    passed_count = 0
    total_steps = len(steps)

    for i, (title, cmd, allow_fail) in enumerate(steps, 1):
        ok = run_step(i, title, cmd, allow_fail)
        if ok:
            passed_count += 1
        else:
            log.error(f"[X] Pipeline halted at step {i}: {title}")
            sys.exit(1)

    print("\n" + "=" * 80)
    print(f"[DONE] PIPELINE COMPLETED SUCCESSFULLY: {passed_count}/{total_steps} stages executed.")
    print("All daily prediction and recommendation reports updated in English & Bengali:")
    print("  - reports/daily/*_rise_fall_predictions_bn.md")
    print("  - reports/catalysts/*_dividend_catalysts_bn.md")
    print("  - reports/weekly/*_bn.md")
    print("  - reports/monthly/*_opportunistic_plan_bn.md")
    print("  - reports/portfolio/*_portfolio_sentinel_bn.md")
    print("  - reports/advisory/*_financial_advisory_bn.md")
    print("  - data/portfolio/current_position_plan_bn.md")
    print("=" * 80)


if __name__ == "__main__":
    main()
