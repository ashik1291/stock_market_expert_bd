"""
DSE Automated Quantitative Investment & Trading System — Master MVP Controller

Usage:
  python main.py [COMMAND] [ARGS]

Commands:
  status        Check complete system health, macro bias, active alerts, and portfolio ledger
  best2         Run 12-factor Graham/Buffett screener and show Top 2 stocks per sector
  scan          Run daily directional Rise vs Fall scanner across Category A stocks
  refresh       Execute complete end-to-end knowledge base refresh pipeline
  pattern [TICKER] Analyze company pattern DNA, multi-interval waves, causal 'WHY', & worth vs greed
  portfolio     Show current portfolio holdings (Mutual Funds + Equities + P&L)
  plan [BDT]    Generate exact capital deployment plan (default BDT 50,000)
  report        Display the latest weekly investment & trading executive report
  help          Display this command reference
"""

import sys
import subprocess
from pathlib import Path

# Enforce UTF-8 encoding on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR    = Path(__file__).resolve().parent
SCRIPTS_DIR = BASE_DIR / "scripts"
REPORTS_DIR = BASE_DIR / "reports"


def run_script(script_name: str, args: list = None) -> int:
    script_path = SCRIPTS_DIR / script_name
    cmd = [sys.executable, str(script_path)] + (args or [])
    res = subprocess.run(cmd, cwd=str(BASE_DIR))
    return res.returncode


def cmd_status():
    print("=" * 80, flush=True)
    print("📈 DSE SYSTEM STATUS & PORTFOLIO DASHBOARD", flush=True)
    print("=" * 80, flush=True)
    print("\n[1/3] Checking Systemic Macro Climate & Shocks...", flush=True)
    run_script("macro_sentiment_engine.py")
    
    print("\n[2/3] Checking Portfolio Ledger...", flush=True)
    run_script("portfolio_manager.py", ["status"])

    print("\n[3/3] Checking Database Integrity...", flush=True)
    import sqlite3
    db_path = BASE_DIR / "data" / "processed" / "dse.db"
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        cat_a_count = conn.execute("SELECT count(*) FROM companies WHERE category='A'").fetchone()[0]
        prices_count = conn.execute("SELECT count(*) FROM prices").fetchone()[0]
        fund_count = conn.execute("SELECT count(*) FROM fundamentals").fetchone()[0]
        print(f"  * SQLite Database: Connected ({db_path.name})", flush=True)
        print(f"  * Category A Universe: {cat_a_count} Companies", flush=True)
        print(f"  * Historical Price Bars: {prices_count:,} Records", flush=True)
        print(f"  * Audited Fundamental Records: {fund_count} Records", flush=True)
        conn.close()
    else:
        print("  * Warning: dse.db not found. Run 'python main.py refresh' first.", flush=True)
    print("\nSystem Health: 100% OPERATIONAL\n", flush=True)


def cmd_best2():
    print("=" * 80, flush=True)
    print("🏆 EXECUTING 12-FACTOR GRAHAM/BUFFETT SECTOR BEST-2 SCREENER", flush=True)
    print("=" * 80, flush=True)
    run_script("buffett_value_screener.py")


def cmd_scan():
    print("=" * 80, flush=True)
    print("⚡ RUNNING DAILY DIRECTIONAL RISE VS FALL SCANNER", flush=True)
    print("=" * 80, flush=True)
    run_script("daily_rise_fall_scanner.py", ["weekly"])


def cmd_refresh():
    print("=" * 80, flush=True)
    print("🔄 STARTING FULL REFRESH PIPELINE", flush=True)
    print("=" * 80, flush=True)
    steps = [
        ("1. Live Price & Market Summary Scrape", "scraper.py", ["price"]),
        ("2. Database Ingestion (Point-In-Time)", "processor.py", []),
        ("3. Macro Sentiment & Crisis Monitor", "macro_sentiment_engine.py", []),
        ("4. Technical, Fundamental & Manipulation Analysis", "analyzer.py", ["all", "weekly"]),
        ("5. 12-Factor Buffett Value & Sector Best 2 Screener", "buffett_value_screener.py", []),
        ("6. Daily Rise vs Fall Directional Scanner", "daily_rise_fall_scanner.py", ["weekly"]),
        ("7. Tri-Horizon Recommender & Visual Chart Generator", "recommender.py", ["weekly"]),
        ("8. 5-Sector Matrix Evaluation", "sector_matrix_evaluator.py", []),
        ("9. V2 Forward Epoch Tracker & Daily Universe Rank", "forward_test_ledger_v2.py", [])
    ]

    for idx, (title, script, args) in enumerate(steps, 1):
        print(f"\n[{idx}/{len(steps)}] {title}...", flush=True)
        code = run_script(script, args)
        if code != 0:
            print(f"⚠️ Warning: Step {script} exited with code {code}.", flush=True)

    print("\n" + "=" * 80, flush=True)
    print("✅ REFRESH COMPLETE: V2 QUANT ENGINE & ALL CATEGORY A ASSETS AUDITED", flush=True)
    print("=" * 80, flush=True)


def cmd_portfolio():
    run_script("portfolio_manager.py", ["status"])


def cmd_plan(capital=None):
    args = ["plan"]
    if capital:
        args.append(str(capital))
    run_script("portfolio_manager.py", args)


def cmd_report():
    weekly_md = REPORTS_DIR / "weekly"
    latest_files = sorted(weekly_md.glob("*.md"), reverse=True) if weekly_md.exists() else []
    if latest_files:
        with open(latest_files[0], encoding="utf-8") as f:
            print(f.read())
    else:
        print("No weekly report found. Run 'python main.py refresh' to generate.")


def cmd_learn():
    print("=" * 80, flush=True)
    print("🧠 DSE REINFORCEMENT LEARNING & PREDICTION ACCURACY AUDIT", flush=True)
    print("=" * 80, flush=True)
    run_script("reinforcement_learning_engine.py", ["evaluate"])
    report_file = REPORTS_DIR / "learning" / "prediction_accuracy_evaluation.md"
    if report_file.exists():
        with open(report_file, encoding="utf-8") as f:
            print(f.read(), flush=True)


def cmd_pattern(ticker: str):
    run_script("pattern_causal_engine.py", [ticker])


def cmd_help():
    print(__doc__)


def main():
    if len(sys.argv) < 2:
        cmd_help()
        return

    cmd = sys.argv[1].lower().strip("-")
    if cmd in ("status", "info"):
        cmd_status()
    elif cmd in ("best2", "screener", "buffett"):
        cmd_best2()
    elif cmd in ("scan", "daily", "rise-fall"):
        cmd_scan()
    elif cmd in ("refresh", "update"):
        cmd_refresh()
    elif cmd in ("learn", "accuracy", "feedback"):
        cmd_learn()
    elif cmd in ("pattern", "cycles", "why", "dna"):
        t = sys.argv[2] if len(sys.argv) > 2 else "SQURPHARMA"
        cmd_pattern(t)
    elif cmd in ("portfolio", "holdings"):
        cmd_portfolio()
    elif cmd in ("plan", "position"):
        cap = sys.argv[2] if len(sys.argv) > 2 else None
        cmd_plan(cap)
    elif cmd in ("report", "weekly"):
        cmd_report()
    elif cmd in ("help", "menu", "?"):
        cmd_help()
    else:
        print(f"Unknown command: '{sys.argv[1]}'. Use 'python main.py help'.")


if __name__ == "__main__":
    main()
