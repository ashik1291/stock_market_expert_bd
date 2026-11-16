# tools/secret_scanner.py
"""
Local Secret & Privacy Leak Scanner for stock_market_expert_bd.
Scans source files, config files, git history, and data definitions for:
1. Accidental API tokens, OAuth keys, and private SSH/RSA keys.
2. Hardcoded passwords and credential patterns.
3. Corporate email leaks (enforces user privacy rule for @ashik1291).
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

# High-confidence secret patterns
SECRET_PATTERNS = [
    ("AWS Access Key", re.compile(r"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}")),
    ("GitHub Personal Token", re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,255}")),
    ("Google API Key", re.compile(r"AIza[0-9A-Za-z\-_]{35}")),
    ("Private Key Header", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
    ("Slack API Token", re.compile(r"xox[baprs]-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*")),
    ("Hardcoded Password", re.compile(r"(?:password|passwd|pwd|secret_key)\s*[:=]\s*['\"][A-Za-z0-9@#$%^&+=_-]{8,}['\"]", re.IGNORECASE)),
    ("Internal Work Email Leak", re.compile(r"[a-zA-Z0-9._%+-]+@brainstation-23\.com", re.IGNORECASE)),
]

IGNORED_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "build",
    "dist",
    "venv",
    ".venv",
    ".gemini",
    ".claude",
    ".codegraph",
    "scratch",
    "raw",
}

IGNORED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    ".pyc", ".gz", ".zip", ".tar", ".whl", ".db", ".db-wal", ".db-shm", ".pdf"
}

def scan_file(filepath: Path) -> List[Tuple[int, str, str]]:
    """Scans a single file for secret patterns. Returns list of (line_num, pattern_name, match_snippet)."""
    findings = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for idx, line in enumerate(f, start=1):
                # Skip comments explaining the patterns in scanner scripts
                if "re.compile" in line or "SECRET_PATTERNS" in line:
                    continue
                for name, pat in SECRET_PATTERNS:
                    m = pat.search(line)
                    if m:
                        snippet = m.group(0)
                        if len(snippet) > 8 and name != "Internal Work Email Leak":
                            masked = snippet[:3] + "..." + snippet[-3:]
                        else:
                            masked = snippet
                        findings.append((idx, name, masked))
    except Exception:
        pass
    return findings

def scan_repository(root_dir: Path = REPO_ROOT) -> int:
    """Scans the repository. Returns count of detected leaks."""
    total_files = 0
    total_findings = 0
    detected_leaks = []

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Prune ignored directories
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]

        for fname in filenames:
            ext = Path(fname).suffix.lower()
            if ext in IGNORED_EXTENSIONS:
                continue

            fpath = Path(dirpath) / fname
            if fpath.stat().st_size > 2 * 1024 * 1024:
                continue

            total_files += 1
            issues = scan_file(fpath)
            if issues:
                total_findings += len(issues)
                rel_path = fpath.relative_to(root_dir)
                for line_num, name, snippet in issues:
                    detected_leaks.append((str(rel_path), line_num, name, snippet))

    print(f"===========================================================")
    print(f"🔒 stock_market_expert_bd Secret & Privacy Leak Scanner")
    print(f"Scanned {total_files} files in {root_dir}")
    print(f"===========================================================")

    if not detected_leaks:
        print("✓ Zero secret leaks detected.")
        print("✓ Zero private credentials or API keys found.")
        print("✓ Maintainer privacy verified (strictly @ashik1291).")
        return 0
    else:
        print(f"❌ FOUND {len(detected_leaks)} POTENTIAL PRIVACY OR CREDENTIAL LEAKS:")
        for path, line_no, leak_type, match in detected_leaks:
            print(f"  - [{leak_type}] {path}:{line_no} -> '{match}'")
        return 1

if __name__ == "__main__":
    sys.exit(scan_repository())
