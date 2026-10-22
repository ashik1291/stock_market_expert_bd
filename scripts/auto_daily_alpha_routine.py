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

    # Step 2: Audit Footnotes & Regulatory Disclosures
    run_step("3. Parse Auditor Disclosures & Regulatory Risk Flags", "auditor_footnote_parser.py", [])

    # Step 3: Advance V2 Hash-Chained Forward Ledger
    run_step("4. Advance V2 Hash-Chained Forward Ledger & Log Full Universe", "forward_test_ledger_v2.py", [])

    # Step 4: Run Reinforcement Learning Engine to learn from past mistakes
    run_step("5. Calibrate Empirical Bayes Weights & Evaluate Accuracy", "reinforcement_learning_engine.py", ["evaluate"])

    # Step 5: Refresh Knowledge Base via Analyzer for active universe
    run_step("6. Update Scoring & Knowledge Base (analyzer.py all weekly)", "analyzer.py", ["all", "weekly"])

    # Step 6: Run Daily Directional Scanner with latest learned weights
    run_step("7. Scan Daily Directional Rise/Fall with Moat & Debt Gates", "daily_rise_fall_scanner.py", ["weekly"])

    # Step 7: Update structured recommendations in SQLite DB
    run_step("8. Refresh Tri-Horizon Recommendations & Position Plan", "recommender.py", ["weekly"])

    print("\n" + "=" * 80)
    print("✅ AUTO-ALPHA CYCLE COMPLETE: SYSTEM LEARNED & FACTOR LOGS ADVANCED")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    execute_daily_alpha_cycle()
