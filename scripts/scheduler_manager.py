#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stock_market_expert_bd — Universal Cross-Platform Scheduler & Automation Manager

Manages recurring automation jobs across all environments:
  - Linux/macOS: Native crontab or systemd timers
  - Windows: Windows Task Scheduler (via PowerShell / schtasks)
  - Docker / Cloud Containers: In-process background daemon with Asia/Dhaka time awareness

Usage:
  python scripts/scheduler_manager.py install     # Auto-install scheduled jobs for current OS
  python scripts/scheduler_manager.py status      # Check active schedule status
  python scripts/scheduler_manager.py uninstall   # Remove installed jobs
  python scripts/scheduler_manager.py crontab     # Print resolved crontab block
  python scripts/scheduler_manager.py daemon      # Run in-process container daemon (continuous)
"""

import sys
import os
import time
import subprocess
import datetime
import platform
from pathlib import Path

# Safe UTF-8 encoding
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BASE_DIR / "scripts"
LOGS_DIR = BASE_DIR / "logs" / "cron"
CRON_TEMPLATE = BASE_DIR / "cron" / "crontab.txt"


def ensure_logs_dir():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def get_python_executable() -> str:
    """Returns absolute path to python executable, favoring virtual environments."""
    if os.environ.get("VIRTUAL_ENV"):
        venv_py = Path(os.environ["VIRTUAL_ENV"])
        candidate = venv_py / "Scripts" / "python.exe" if platform.system() == "Windows" else venv_py / "bin" / "python"
        if candidate.exists():
            return str(candidate)

    # Check local venv
    for vname in (".venv", "venv", "env"):
        cand = BASE_DIR / vname / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")
        if cand.exists():
            return str(cand)

    return sys.executable


def get_crontab_block() -> str:
    """Generates crontab text with resolved absolute paths."""
    py = get_python_executable()
    repo = str(BASE_DIR).replace("\\", "/")
    logs = str(LOGS_DIR).replace("\\", "/")
    
    block = f"""# >>> DSE QUANTITATIVE ENGINE CRON JOBS >>>
# Timezone: Asia/Dhaka (BST: UTC+6) | Trading Days: Sunday (0) to Thursday (4)
CRON_TZ=Asia/Dhaka
SHELL=/bin/bash

# 1. Post-Market Daily Alpha & Learning Cycle (Sun-Thu at 15:30 BST / 09:30 UTC)
30 15 * * 0-4 cd "{repo}" && "{py}" scripts/auto_daily_alpha_routine.py >> "{logs}/daily_alpha.log" 2>&1

# 2. Master Daily Pipeline & Position Plan (Sun-Thu at 16:15 BST / 10:15 UTC)
15 16 * * 0-4 cd "{repo}" && "{py}" scripts/run_daily_pipeline.py --skip-scrape >> "{logs}/daily_pipeline.log" 2>&1

# 3. Weekly Deep Knowledge Refresh (Every Thursday at 18:00 BST / 12:00 UTC)
00 18 * * 4 cd "{repo}" && "{py}" scripts/analyzer.py category_a weekly >> "{logs}/weekly_refresh.log" 2>&1

# 4. Weekly Compressed DB Backup & Sync (Every Thursday at 19:00 BST / 13:00 UTC)
00 19 * * 4 cd "{repo}" && "{py}" scripts/push_db_update.py >> "{logs}/push_db.log" 2>&1

# 5. Midday Market Pulse Check (Sun-Thu at 11:30 and 13:30 BST during active trading)
30 11,13 * * 0-4 cd "{repo}" && "{py}" scripts/check_daily_sync.py >> "{logs}/midday_sync.log" 2>&1
# <<< DSE QUANTITATIVE ENGINE CRON JOBS <<<"""
    return block


def cmd_install():
    ensure_logs_dir()
    os_name = platform.system()
    print("=" * 80)
    print(f"🔧 INSTALLING SCHEDULED AUTOMATION JOBS ({os_name})")
    print("=" * 80)
    print(f"  • Repository: {BASE_DIR}")
    print(f"  • Python:     {get_python_executable()}")
    print(f"  • Logs:       {LOGS_DIR}\n")

    if os_name == "Windows":
        ps_script = SCRIPTS_DIR / "setup_scheduled_tasks.ps1"
        cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ps_script), "-Action", "Install"]
        res = subprocess.run(cmd)
        if res.returncode == 0:
            print("\n✅ SUCCESS: Windows Task Scheduler jobs created successfully!")
        else:
            print(f"\n⚠️ Warning: PowerShell returned code {res.returncode}. You may need Administrator privileges.")
    else:
        # Linux / macOS
        sh_script = SCRIPTS_DIR / "setup_cron.sh"
        if sh_script.exists():
            subprocess.run(["chmod", "+x", str(sh_script)], check=False)
            res = subprocess.run(["bash", str(sh_script), "install"])
            if res.returncode == 0:
                print("\n✅ SUCCESS: Crontab successfully updated!")
            else:
                print(f"\n⚠️ Warning: setup_cron.sh returned code {res.returncode}")
        else:
            print("⚠️ setup_cron.sh not found.")


def cmd_status():
    os_name = platform.system()
    print("=" * 80)
    print(f"📋 DSE AUTOMATION SCHEDULE STATUS ({os_name})")
    print("=" * 80)

    if os_name == "Windows":
        ps_script = SCRIPTS_DIR / "setup_scheduled_tasks.ps1"
        subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ps_script), "-Action", "Show"])
    else:
        try:
            res = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            if "DSE QUANTITATIVE ENGINE" in res.stdout:
                print("✅ DSE Crontab jobs are ACTIVE in current user crontab:\n")
                lines = [l for l in res.stdout.splitlines() if "DSE" in l or "scripts/" in l]
                for l in lines:
                    print(f"   {l}")
            else:
                print("ℹ️ No active DSE crontab jobs found for current user.")
                print("   Run 'python scripts/scheduler_manager.py install' to set them up.")
        except Exception as e:
            print(f"⚠️ Unable to query crontab: {e}")


def cmd_uninstall():
    os_name = platform.system()
    print("=" * 80)
    print(f"🗑️ UNINSTALLING SCHEDULED AUTOMATION JOBS ({os_name})")
    print("=" * 80)

    if os_name == "Windows":
        ps_script = SCRIPTS_DIR / "setup_scheduled_tasks.ps1"
        subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ps_script), "-Action", "Uninstall"])
    else:
        sh_script = SCRIPTS_DIR / "setup_cron.sh"
        if sh_script.exists():
            subprocess.run(["bash", str(sh_script), "uninstall"])
        else:
            print("⚠️ setup_cron.sh not found.")


def get_dhaka_now() -> datetime.datetime:
    """Returns current datetime in Asia/Dhaka (UTC+6)."""
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    dhaka_tz = datetime.timezone(datetime.timedelta(hours=6))
    return utc_now.astimezone(dhaka_tz)


def cmd_daemon():
    """
    Continuous in-process scheduling daemon.
    Ideal for Docker containers or background cloud jobs where crontab is not available.
    """
    ensure_logs_dir()
    print("=" * 80)
    print("🤖 DSE AUTOMATION IN-PROCESS DAEMON STARTED")
    print("   Timezone: Asia/Dhaka (UTC+6)")
    print("   Press Ctrl+C to terminate.")
    print("=" * 80)

    executed_today = set()
    current_day = None

    while True:
        try:
            now = get_dhaka_now()
            today_str = now.strftime("%Y-%m-%d")
            weekday = now.weekday()  # 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
            # Bangladesh trading days: Sunday (6) through Thursday (3)
            is_trading_day = weekday in (6, 0, 1, 2, 3)

            if current_day != today_str:
                current_day = today_str
                executed_today.clear()
                print(f"\n[DAEMON] New day: {today_str} (Weekday={weekday}, TradingDay={is_trading_day})")

            hh_mm = now.strftime("%H:%M")

            # 1. Daily Alpha Cycle (Sun-Thu at 15:30)
            if is_trading_day and hh_mm == "15:30" and "daily_alpha" not in executed_today:
                print(f"[DAEMON] ⏰ Triggering Daily Alpha Cycle at {now.isoformat()}...")
                executed_today.add("daily_alpha")
                subprocess.run([get_python_executable(), str(SCRIPTS_DIR / "auto_daily_alpha_routine.py")])

            # 2. Master Pipeline (Sun-Thu at 16:15)
            if is_trading_day and hh_mm == "16:15" and "daily_pipeline" not in executed_today:
                print(f"[DAEMON] ⏰ Triggering Master Daily Pipeline at {now.isoformat()}...")
                executed_today.add("daily_pipeline")
                subprocess.run([get_python_executable(), str(SCRIPTS_DIR / "run_daily_pipeline.py"), "--skip-scrape"])

            # 3. Weekly Deep Refresh (Every Thursday at 18:00)
            if weekday == 3 and hh_mm == "18:00" and "weekly_refresh" not in executed_today:
                print(f"[DAEMON] ⏰ Triggering Weekly Knowledge Refresh at {now.isoformat()}...")
                executed_today.add("weekly_refresh")
                subprocess.run([get_python_executable(), str(SCRIPTS_DIR / "analyzer.py"), "category_a", "weekly"])
                subprocess.run([get_python_executable(), str(SCRIPTS_DIR / "push_db_update.py")])

            # Sleep 30 seconds before next check
            time.sleep(30)
        except KeyboardInterrupt:
            print("\n[DAEMON] Daemon stopped by user.")
            break
        except Exception as e:
            print(f"[DAEMON] ⚠️ Error in daemon loop: {e}")
            time.sleep(30)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    action = sys.argv[1].lower()
    if action in ("install", "setup", "init"):
        cmd_install()
    elif action in ("status", "check", "info"):
        cmd_status()
    elif action in ("uninstall", "remove", "delete"):
        cmd_uninstall()
    elif action in ("crontab", "template", "show"):
        print(get_crontab_block())
    elif action in ("daemon", "run-daemon", "server"):
        cmd_daemon()
    else:
        print(f"Unknown action: {action}. Use: install, status, uninstall, crontab, daemon.")


if __name__ == "__main__":
    main()
