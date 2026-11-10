"""
stock_market_expert_bd — Autonomous DSE Quantitative Engine & AI Financial Intelligence System

Usage:
  python main.py [COMMAND] [ARGS]
  stock_market_expert_bd [COMMAND] [ARGS]

Commands:
  ready         Bootstrap dependencies, verify database integrity, and ready system on this machine
  sync          Synchronize live market prices, backfill missed dates, and refresh readiness
  status        Check complete system health, macro bias, active alerts, and portfolio ledger
  config        Configure stock universe screening preference (Regular Stock vs Halal)
  best2         Run 12-factor Graham/Buffett screener and show Top 2 stocks per sector
  scan          Run daily directional Rise vs Fall scanner across Category A stocks
  refresh       Execute complete end-to-end knowledge base refresh pipeline
  alpha         Execute automated statistical alpha routine, ledger advance & Bayesian calibration
  pattern [TICKER] Analyze company pattern DNA, multi-interval waves, causal 'WHY', & worth vs greed
  check         Run unified daily portfolio audit & seasonal catalyst check in 5 seconds
  portfolio     Show current portfolio holdings (Mutual Funds + Equities + P&L)
  plan [BDT]    Generate exact capital deployment plan (default BDT 50,000)
  dual [BDT]    Generate dual-engine allocation: 60% Long-Term Core + 40% Bi-Weekly Swings
  radar         Run pre-dividend seasonal catalyst radar (15-25 day swings)
  buy [TICKER] [SHS] [PX]  Record a manual stock purchase into portfolio ledger
  sell [TICKER] [SHS] [PX] Record a manual stock sale & calculate realized net P&L
  proxy [BDT]   Run user proxy simulation: max profit probability, entry zone & exit rules
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

    print("\n[3/3] Auditing System Conformance, Freshness & Integrity...", flush=True)
    import sqlite3
    from scripts.db import get_db_connection
    from scripts.integrity_harness import run_integrity
    from scripts.spec_guard import run_spec_guard
    
    db_path = BASE_DIR / "data" / "processed" / "dse.db"
    if not db_path.exists():
        print("  * ❌ CRITICAL: dse.db not found. Run 'python main.py ready' to restore.", flush=True)
        print("\nSystem Status: ❌ CRITICAL (Database Missing)\n", flush=True)
        return

    conn = get_db_connection(db_path, timeout=30.0)
    cat_a_count = conn.execute("SELECT count(*) FROM companies WHERE category='A'").fetchone()[0]
    prices_count = conn.execute("SELECT count(*) FROM prices").fetchone()[0]
    fund_count = conn.execute("SELECT count(*) FROM fundamentals").fetchone()[0]
    pit_count = conn.execute("SELECT count(*) FROM fundamentals_pit").fetchone()[0]
    pit_verified_count = conn.execute("SELECT count(*) FROM fundamentals_pit WHERE publication_is_estimated = 0").fetchone()[0]
    pit_coverage_pct = round((pit_verified_count / pit_count * 100.0), 1) if pit_count > 0 else 0.0
    latest_price = conn.execute("SELECT MAX(date) FROM prices").fetchone()[0]
    conn.close()

    print(f"  * SQLite Database: Hardened WAL Connected ({db_path.name})", flush=True)
    print(f"  * Category A Universe: {cat_a_count} Companies | Historical Bars: {prices_count:,}", flush=True)
    print(f"  * Point-in-Time Fundamentals: {pit_count} Records ({pit_verified_count} Verified Live, {pit_count - pit_verified_count} Research-Only Estimated | Coverage: {pit_coverage_pct}%)", flush=True)
    print(f"  * Latest As-of Pricing: {latest_price}", flush=True)

    # Real Programmatic Conformance & Integrity Verification
    spec_ok = run_spec_guard()
    integrity_res = run_integrity()
    integrity_ok = integrity_res.get("ok", False) and integrity_res.get("fail_count", 1) == 0

    if spec_ok and integrity_ok:
        print(f"\nSystem Status: ✅ OPERATIONAL RESEARCH ENGINE & RISK FILTER (SPEC: 8/8 PASS | Integrity: 9/9 PASS | As-of: {latest_price})", flush=True)
        print("  * System Classification: Institutional Risk Screening & Research Framework (~52/100)", flush=True)
        print("  * Advisory Warning: Non-autonomous capital allocator; forward trial calibration active.\n", flush=True)
    else:
        print(f"\nSystem Status: ⚠️ DEGRADED / ATTENTION REQUIRED (Spec: {'PASS' if spec_ok else 'FAIL'}, Integrity: {'PASS' if integrity_ok else 'FAIL'})\n", flush=True)


def cmd_best2():
    print("=" * 80, flush=True)
    print("🏆 EXECUTING 12-FACTOR GRAHAM/BUFFETT SECTOR BEST-2 SCREENER", flush=True)
    print("=" * 80, flush=True)
    run_script("buffett_value_screener.py")


def cmd_scan():
    print("=" * 80, flush=True)
    print("🔮 RUNNING DIRECTIONAL RISE VS FALL SCANNER (CATEGORY A UNIVERSE)", flush=True)
    print("=" * 80, flush=True)
    run_script("daily_rise_fall_scanner.py", ["weekly"])


def cmd_refresh():
    print("=" * 80, flush=True)
    print("🔄 EXECUTING COMPREHENSIVE KNOWLEDGE BASE REFRESH PIPELINE", flush=True)
    print("=" * 80, flush=True)
    print("Triggering master refresh orchestrator (Scrape -> Process -> Sentiments -> Unified)...")
    run_script("knowledge_refresh.py")


def cmd_alpha():
    print("=" * 80, flush=True)
    print("⚡ EXECUTING DAILY STATISTICAL ALPHA ROUTINE & BAYESIAN CALIBRATION", flush=True)
    print("=" * 80, flush=True)
    run_script("auto_daily_alpha_routine.py")


def cmd_learn():
    print("=" * 80, flush=True)
    print("📊 EVALUATING PREDICTION ACCURACY & STATISTICAL LEDGER ADVANCEMENT", flush=True)
    print("=" * 80, flush=True)
    run_script("evaluate_accuracy_simple.py")


def cmd_portfolio():
    print("=" * 80, flush=True)
    print("💼 EXAMINING PORTFOLIO HOLDINGS & REAL-TIME PERFORMANCE", flush=True)
    print("=" * 80, flush=True)
    run_script("portfolio_manager.py", ["status"])
    print("\n" + "=" * 80, flush=True)
    print("🛡️ RUNNING ACTIVE RISK & PROFIT SENTINEL AUDIT", flush=True)
    print("=" * 80, flush=True)
    run_script("portfolio_sentinel.py")


def cmd_plan(capital=None):
    print("=" * 80, flush=True)
    print("🎯 GENERATING TARGET POSITION ALLOCATION PLAN (3-TIER TRANCHE LADDER)", flush=True)
    print("=" * 80, flush=True)
    args = ["--amount", str(capital)] if capital else []
    run_script("smart_capital_planner.py", args)


def cmd_check():
    print("=" * 80, flush=True)
    print("🔎 EXECUTING UNIFIED DAILY PORTFOLIO & CATALYST ACTION AUDIT", flush=True)
    print("=" * 80, flush=True)
    run_script("portfolio_sentinel.py")
    print("\n" + "=" * 80, flush=True)
    run_script("catalyst_radar.py")
    print("=" * 80, flush=True)
    print("✅ AUDIT COMPLETE: Review Active Stop-Losses, Take-Profits & Catalyst Windows above.", flush=True)
    print("=" * 80, flush=True)


def cmd_radar():
    print("=" * 80, flush=True)
    print("🎯 EXECUTING PRE-DIVIDEND & SEASONAL CATALYST RADAR", flush=True)
    print("=" * 80, flush=True)
    run_script("catalyst_radar.py")


def cmd_buy(ticker: str, shares: str, price: str):
    print("=" * 80, flush=True)
    print(f"💼 RECORDING BUY: {shares} shares of {ticker.upper()} @ ৳{price}", flush=True)
    print("=" * 80, flush=True)
    run_script("portfolio_manager.py", ["buy", ticker, str(shares), str(price)])


def cmd_sell(ticker: str, shares: str, price: str):
    print("=" * 80, flush=True)
    print(f"💼 RECORDING SELL: {shares} shares of {ticker.upper()} @ ৳{price}", flush=True)
    print("=" * 80, flush=True)
    run_script("portfolio_manager.py", ["sell", ticker, str(shares), str(price)])


def cmd_dual(capital=None):
    print("=" * 80, flush=True)
    print("🏛️ EXECUTING DUAL-ENGINE PORTFOLIO ALLOCATOR (CORE + BI-WEEKLY SWINGS)", flush=True)
    print("=" * 80, flush=True)
    args = ["--amount", str(capital)] if capital else []
    run_script("dual_engine_portfolio_planner.py", args)


def cmd_proxy(capital=None):
    print("=" * 80, flush=True)
    print("🤖 EXECUTING USER PROXY SIMULATION (MAX PROFIT PROBABILITY ENGINE)", flush=True)
    print("=" * 80, flush=True)
    args = ["--amount", str(capital)] if capital else []
    run_script("user_proxy_simulation.py", args)


def cmd_report():
    print("=" * 80, flush=True)
    print("📑 GENERATING / DISPLAYING LATEST EXECUTIVE RECOMMENDATION REPORT", flush=True)
    print("=" * 80, flush=True)
    # Check if a report file exists, if not generate one
    rep_files = list(REPORTS_DIR.glob("**/*.md"))
    if rep_files:
        latest_rep = max(rep_files, key=lambda p: p.stat().st_mtime)
        print(f"\nDisplaying Latest Report: {latest_rep.name}\n" + "-" * 80)
        try:
            with open(latest_rep, encoding="utf-8") as f:
                print(f.read())
        except Exception as e:
            print(f"Could not read report: {e}")
    else:
        print("No prior reports found. Generating fresh report...")
        run_script("generate_reports.py")


def cmd_pattern(ticker: str):
    run_script("pattern_causal_engine.py", [ticker])


def cmd_ready():
    run_script("bootstrap.py")


def cmd_sync():
    run_script("live_market_sync.py")


def cmd_config():
    sys.path.insert(0, str(SCRIPTS_DIR))
    from user_manager import prompt_user_customization
    prof = prompt_user_customization(force_prompt=True)
    print(f"[CONFIG] Active screening mode: {prof.get('halal_tier', 'off').upper()} stock mode.")


def cmd_help():
    print(__doc__)


def main():
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        from user_manager import prompt_user_customization
        prompt_user_customization(force_prompt=False)
    except Exception:
        pass

    if len(sys.argv) < 2:
        cmd_help()
        return

    cmd = sys.argv[1].lower().strip("-")
    if cmd in ("ready", "bootstrap", "setup", "init"):
        cmd_ready()
    elif cmd in ("sync", "live", "catchup"):
        cmd_sync()
    elif cmd in ("status", "info"):
        cmd_status()
    elif cmd in ("config", "preference", "preferences", "custom"):
        cmd_config()
    elif cmd in ("best2", "screener", "buffett"):
        cmd_best2()
    elif cmd in ("scan", "daily", "rise-fall"):
        cmd_scan()
    elif cmd in ("refresh", "update"):
        cmd_refresh()
    elif cmd in ("alpha", "daily-alpha"):
        cmd_alpha()
    elif cmd in ("learn", "accuracy", "feedback"):
        cmd_learn()
    elif cmd in ("pattern", "cycles", "why", "dna"):
        t = sys.argv[2] if len(sys.argv) > 2 else "SQURPHARMA"
        cmd_pattern(t)
    elif cmd in ("check", "audit", "daily", "daily-check", "review"):
        cmd_check()
    elif cmd in ("portfolio", "holdings"):
        cmd_portfolio()
    elif cmd in ("proxy", "simulate", "user-proxy"):
        cap = sys.argv[2] if len(sys.argv) > 2 else None
        cmd_proxy(cap)
    elif cmd in ("plan", "position"):
        cap = sys.argv[2] if len(sys.argv) > 2 else None
        cmd_plan(cap)
    elif cmd in ("dual", "dual-engine", "core-satellite", "swings"):
        cap = sys.argv[2] if len(sys.argv) > 2 else None
        cmd_dual(cap)
    elif cmd in ("radar", "catalyst", "catalysts", "season"):
        cmd_radar()
    elif cmd == "buy" and len(sys.argv) >= 5:
        cmd_buy(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "sell" and len(sys.argv) >= 5:
        cmd_sell(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd in ("report", "weekly"):
        cmd_report()
    elif cmd in ("help", "menu", "?"):
        cmd_help()
    else:
        print(f"Unknown command: '{sys.argv[1]}'. Use 'python main.py help'.")


if __name__ == "__main__":
    main()
