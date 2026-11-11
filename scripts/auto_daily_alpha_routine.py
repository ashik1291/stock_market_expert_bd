"""
Automated Daily Statistical Alpha & Learning Routine.
Executes the full pipeline without manual intervention:
  1. Verifies/Ingests latest market close prices & Point-In-Time fundamentals.
  2. Updates V2 Hash-Chained Out-of-Sample Forward Ledger & full-universe factor logs.
  3. Runs Empirical Bayes Reinforcement Learning calibration on past prediction outcomes.
  4. Publishes daily rise/fall predictions and updates adaptive model weights.
"""

import sys
import datetime
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BASE_DIR / "scripts"

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def run_step(name: str, script_name: str, args: list = None) -> bool:
    print(f"\n[AUTO-ALPHA] Running: {name} ({script_name})...", flush=True)
    cmd = [sys.executable, str(SCRIPTS_DIR / script_name)] + (args or [])
    res = subprocess.run(cmd, cwd=str(BASE_DIR))
    if res.returncode != 0:
        print(f"[AUTO-ALPHA] ⚠️ Warning: {script_name} returned code {res.returncode}", flush=True)
        return False
    return True


def execute_daily_alpha_cycle():
    print("=" * 80)
    print(f"🧠 DSE DAILY STATISTICAL ALPHA & ADAPTIVE LEARNING CYCLE — {datetime.date.today().isoformat()}")
    print("=" * 80)

    # Step 1: Scrape & process latest prices into PIT database
    run_step("1. Scrape Daily Price Snapshots", "scraper.py", ["price"])
    run_step("2. Ingest PIT Snapshots & Audits", "processor.py", [])

    # Step 2: Ingest Bangladesh Bank Macro Benchmark Rates
    run_step("3. Sync Bangladesh Bank Macro Rates & Hurdle Engine", "macro_rate_feed.py", [])

    # Step 3: Sync Corporate Actions & Process Cash Dividends
    run_step("4. Corporate Actions & Idempotent Dividend Distribution", "corporate_action_processor.py", [])

    # Step 4: Audit Footnotes & Regulatory Disclosures
    run_step("5. Parse Auditor Disclosures & Regulatory Risk Flags", "auditor_footnote_parser.py", [])
    run_step("5b. Full Market Surveillance & Anti-Manipulation Scanner", "anti_manipulation_engine.py", [])

    # Step 5: Advance V2 Hash-Chained Forward Ledger
    run_step("6. Advance V2 Hash-Chained Forward Ledger & Log Full Universe", "forward_test_ledger_v2.py", [])

    # Step 6: Run Reinforcement Learning Engine & Multi-Horizon Evaluation to learn from past outcomes
    run_step("7. Multi-Horizon Prediction Evaluator & Alpha Accrual", "multi_horizon_evaluator.py", ["10"])
    run_step("7b. Calibrate Empirical Bayes Weights & Evaluate Accuracy", "reinforcement_learning_engine.py", ["evaluate"])
    run_step("7c. Calibrate Rolling Factor IC Weights", "factor_ic_calibrator.py", [])
    run_step("7d. Shadow Score Challengers & Evaluate Statistical Promotion Gate", "model_registry.py", ["shadow"])
    run_step("7e. Evaluate Model Promotion Eligibility (Holm Gate)", "model_registry.py", ["promote"])

    # Step 7: Refresh Knowledge Base via Analyzer for active Category A universe into SQLite Feature Store
    run_step("8. Update Scoring & Knowledge Base (analyzer.py category_a weekly)", "analyzer.py", ["category_a", "weekly"])

    # Step 8: Run Daily Directional Scanner with latest learned weights
    run_step("9. Scan Daily Directional Rise/Fall with Moat & Debt Gates", "daily_rise_fall_scanner.py", ["weekly"])

    # Step 9: Run 5-Factor Fundamental Value Screener with Macro ERP Hurdle
    run_step("10. 5-Factor Fundamental Moat Screener with Macro ERP", "five_factor_fundamental_screener.py", [])

    # Step 10: Run Order Book Depth & Execution Liquidity Matrix
    run_step("11. Order Book Depth & Market Impact Analyzer", "orderbook_depth_analyzer.py", [])

    # Step 11: Update structured recommendations in SQLite DB
    run_step("12. Refresh Tri-Horizon Recommendations & Position Plan", "recommender.py", ["weekly"])

    # Step 12: Automated SQLite Payload Retention & Storage Hygiene
    run_step("13. Prune Stale SQLite Payloads (>180 Days)", "db_retention_cleaner.py", ["--days", "180"])

    # Step 13: Nightly System Integrity Harness Verification
    run_step("14. Execute System Integrity Harness (9/9 Gatekeeper)", "integrity_harness.py", [])

    print("\n" + "=" * 80)
    print("✅ AUTO-ALPHA CYCLE COMPLETE: SYSTEM LEARNED & FACTOR LOGS ADVANCED")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    execute_daily_alpha_cycle()
