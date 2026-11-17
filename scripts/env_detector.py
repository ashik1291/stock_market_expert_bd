"""
scripts/env_detector.py — Universal Cross-Platform Environment & Shell Detector
Detects operating system, terminal shell, python environment, encoding, and DB health.
Prints platform-tailored commands so any user on Windows, macOS, or Linux runs scripts effortlessly.
"""

import os
import sys
import shutil
import sqlite3
import platform
from pathlib import Path

# Enforce UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"


def detect_shell():
    """Detects active shell environment (PowerShell, Bash, Zsh, cmd)."""
    # 1. Environment variable indicators
    if os.environ.get("PSModulePath") or os.environ.get("POWERSHELL_DISTRIBUTION_CHANNEL"):
        return "PowerShell"
    if "pwsh" in os.environ.get("SHELL", "").lower():
        return "PowerShell Core"
    shell_env = os.environ.get("SHELL", "")
    if "zsh" in shell_env:
        return "Zsh (macOS / Linux)"
    if "bash" in shell_env:
        return "Bash"
    if os.environ.get("WT_SESSION"):
        return "Windows Terminal"
    if sys.platform == "win32":
        return "CMD / PowerShell"
    return "Unix Shell"


def get_system_diagnosis():
    os_name = platform.system()
    os_release = platform.release()
    arch = platform.machine()
    py_ver = sys.version.split()[0]
    py_exec = sys.executable
    shell = detect_shell()
    encoding = sys.stdout.encoding or "unknown"
    git_path = shutil.which("git")
    git_lfs_path = shutil.which("git-lfs")

    # DB status
    db_ok = False
    company_count = 0
    price_count = 0
    latest_date = None
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=5.0)
            cur = conn.cursor()
            company_count = cur.execute("SELECT count(*) FROM companies").fetchone()[0]
            price_count = cur.execute("SELECT count(*) FROM prices").fetchone()[0]
            latest_date = cur.execute("SELECT max(date) FROM prices").fetchone()[0]
            conn.close()
            db_ok = True
        except Exception:
            db_ok = False

    return {
        "os": os_name,
        "release": os_release,
        "arch": arch,
        "python_version": py_ver,
        "python_executable": py_exec,
        "shell": shell,
        "stdout_encoding": encoding,
        "git_available": bool(git_path),
        "git_lfs_available": bool(git_lfs_path),
        "database_exists": DB_PATH.exists(),
        "database_healthy": db_ok,
        "company_count": company_count,
        "price_count": price_count,
        "latest_pricing_date": latest_date,
    }


def print_env_report():
    diag = get_system_diagnosis()
    os_icon = "🪟" if diag["os"] == "Windows" else ("🍎" if diag["os"] == "Darwin" else "🐧")

    print("=" * 80)
    print(f"{os_icon} MULTI-OS & SHELL RUNTIME DIAGNOSTIC DASHBOARD")
    print("=" * 80)
    print(f"  * Operating System : {diag['os']} ({diag['release']} | {diag['arch']})")
    print(f"  * Detected Shell   : {diag['shell']}")
    print(f"  * Python Runtime   : Python {diag['python_version']} ({diag['python_executable']})")
    print(f"  * Terminal Encoding: {diag['stdout_encoding']} (UTF-8 Compatible: {'YES' if 'utf' in diag['stdout_encoding'].lower() else 'Fallback Mode'})")
    print(f"  * Tooling Found    : Git: {'✓ Installed' if diag['git_available'] else '✗ Missing'} | Git LFS: {'✓ Installed' if diag['git_lfs_available'] else '✗ Missing'}")

    db_str = "✅ ONLINE & AUDITED" if diag["database_healthy"] else "❌ NOT FOUND / CORRUPTED"
    print(f"  * SQLite Database  : {db_str}")
    if diag["database_healthy"]:
        print(f"                       ({diag['company_count']} companies | {diag['price_count']:,} bars | Latest: {diag['latest_pricing_date']})")
    print("-" * 80)

    print("🚀 RECOMMENDED 100% CROSS-PLATFORM COMMANDS FOR YOUR SYSTEM:")
    print("-" * 80)

    if diag["os"] == "Windows":
        print("  [Windows 1-Click / Terminal Options]")
        print("    1. Using Universal CLI runner:")
        print("       python main.py stock ACMELAB")
        print("       python main.py status")
        print("       python main.py scan")
        print("    2. Using PowerShell wrapper:")
        print("       .\\run.ps1 stock ACMELAB")
        print("       .\\ready.ps1")
        print("    3. Using Command Prompt batch:")
        print("       run.bat stock ACMELAB")
        print("       ready.bat")
    else:  # Linux / macOS
        print("  [Linux / macOS Terminal Options]")
        print("    1. Using Universal CLI runner:")
        print("       python3 main.py stock ACMELAB")
        print("       python3 main.py status")
        print("       python3 main.py scan")
        print("    2. Using Shell wrapper:")
        print("       ./run.sh stock ACMELAB")
        print("       ./ready.sh")

    print("-" * 80)
    print("💡 TIP: Avoid typing raw inline 'python -c \"...\"' in terminals.")
    print("   Always use 'python main.py <command>' or 'python scripts/query_stock.py <TICKER>'.")
    print("   They use safe SQL parameter binding, handle UTF-8, and work identically on any OS!")
    print("=" * 80)


if __name__ == "__main__":
    print_env_report()
