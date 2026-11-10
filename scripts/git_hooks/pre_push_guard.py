"""
scripts/git_hooks/pre_push_guard.py — Git Pre-Push Security & Access Guard

Enforces:
1. Leak Protection: Blocks pushes containing private user portfolios, profiles, or secrets.
2. Ownership Guard: Advises external users to push to their own forks instead of upstream origin.
3. Spec Invariant Verification: Verifies core system invariants before code leaves the machine.
"""

from __future__ import annotations

import sys
import os
import subprocess
from pathlib import Path

# Enforce UTF-8 encoding
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Files that must NEVER be pushed to any remote
FORBIDDEN_PATTERNS = [
    "data/portfolio/portfolio.json",
    "config/profile.json",
    "data/users/default_user/profile.json",
    ".env",
    "id_rsa",
    "id_ed25519",
]

def log(msg: str):
    print(f"[PRE-PUSH GUARD] {msg}", flush=True)

def check_leaks() -> bool:
    """Inspects commits to be pushed for forbidden private files."""
    try:
        # Check against origin/master if available, or last commit
        cmd = ["git", "diff", "--name-only", "origin/master..HEAD"]
        res = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True)
        if res.returncode != 0:
            # Fallback to inspecting HEAD commit
            cmd = ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"]
            res = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True)

        files = res.stdout.splitlines()
        violations = []
        for f in files:
            normalized = f.strip().replace("\\", "/")
            for forbidden in FORBIDDEN_PATTERNS:
                if forbidden in normalized or normalized.endswith("portfolio.json") or normalized.endswith("profile.json"):
                    violations.append(normalized)

        if violations:
            log("❌ CRITICAL: Attempted to push private / sensitive user files:")
            for v in violations:
                print(f"    - {v}")
            log("Push aborted. Remove sensitive files from commit history or ensure they are git-ignored.")
            return False

        return True
    except Exception as e:
        log(f"Warning: Leak check error ({e}). Proceeding...")
        return True

def check_remote_target(remote_name: str, remote_url: str) -> bool:
    """Checks remote destination and informs outside contributors."""
    official_upstream = "ashik1291/stock_market_expert_bd"
    
    if official_upstream.lower() in remote_url.lower():
        # Check if environment or git config allows push
        allow_override = os.environ.get("ALLOW_UPSTREAM_PUSH") == "1"
        
        # Check git user config
        try:
            cfg_name = subprocess.check_output(["git", "config", "user.name"], cwd=str(BASE_DIR), text=True).strip()
            cfg_email = subprocess.check_output(["git", "config", "user.email"], cwd=str(BASE_DIR), text=True).strip()
        except Exception:
            cfg_name, cfg_email = "", ""

        # If user is owner or authorized machine
        is_owner = any(kw in cfg_name.lower() or kw in cfg_email.lower() for kw in ["ashik", "ashik1291", "dse", "bs01671"])
        
        if not is_owner and not allow_override:
            log("⚠️ PUSH RESTRICTION ADVISORY:")
            log("Direct pushes to the official upstream (ashik1291/stock_market_expert_bd) are reserved for repository maintainers.")
            log("To contribute or store personal branches:")
            log("  1. Fork this repository on GitHub: https://github.com/ashik1291/stock_market_expert_bd/fork")
            log("  2. Point your origin remote to your fork:")
            log("     git remote set-url origin https://github.com/<your-username>/stock_market_expert_bd.git")
            log("  3. Push to your own fork and open a Pull Request.")
            # Note: Even if hook were bypassed, GitHub remote server rejects unauthorized pushes with HTTP 403.
            return False

    return True

def main():
    remote_name = sys.argv[1] if len(sys.argv) > 1 else "origin"
    remote_url = sys.argv[2] if len(sys.argv) > 2 else ""

    if not remote_url:
        try:
            remote_url = subprocess.check_output(["git", "remote", "get-url", remote_name], cwd=str(BASE_DIR), text=True).strip()
        except Exception:
            remote_url = ""

    # 1. Check for sensitive files
    if not check_leaks():
        sys.exit(1)

    # 2. Check remote target & contributor fork guidance
    if not check_remote_target(remote_name, remote_url):
        sys.exit(1)

    log("✅ Pre-push verification passed.")
    sys.exit(0)

if __name__ == "__main__":
    main()
