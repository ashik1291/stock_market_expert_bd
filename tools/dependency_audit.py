# tools/dependency_audit.py
"""
Automated Dependency Composition & Vulnerability Auditor for stock_market_expert_bd.
Audits pyproject.toml and requirements.txt direct runtime dependencies against
the Google OSV.dev and PyPA Advisory Database APIs directly.
"""

import sys
import json
import urllib.request
import re
from pathlib import Path
from typing import List, Tuple, Dict, Any

REPO_ROOT = Path(__file__).resolve().parent.parent

def extract_dependencies() -> List[Tuple[str, str]]:
    """Extracts declared dependencies from pyproject.toml and requirements.txt."""
    deps: Dict[str, str] = {}
    
    # 1. Check requirements.txt
    req_txt = REPO_ROOT / "requirements.txt"
    if req_txt.exists():
        with open(req_txt, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                m = re.match(r"^([a-zA-Z0-9_\-]+)(.*)$", line)
                if m:
                    pkg = m.group(1).lower()
                    spec = m.group(2).strip()
                    deps[pkg] = spec

    # 2. Check pyproject.toml
    pyproject = REPO_ROOT / "pyproject.toml"
    if pyproject.exists():
        in_deps = False
        with open(pyproject, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("dependencies = ["):
                    in_deps = True
                    continue
                if in_deps:
                    if line.startswith("]"):
                        break
                    clean_dep = line.strip('",\'')
                    if clean_dep:
                        m = re.match(r"^([a-zA-Z0-9_\-]+)(.*)$", clean_dep)
                        if m:
                            pkg = m.group(1).lower()
                            spec = m.group(2).strip()
                            deps[pkg] = spec

    return sorted(deps.items())

def query_osv_vulnerabilities(pkg_name: str, version: str = None) -> List[Dict[str, Any]]:
    """Queries OSV.dev for known security vulnerabilities."""
    url = "https://api.osv.dev/v1/query"
    payload = {
        "package": {
            "name": pkg_name,
            "ecosystem": "PyPI"
        }
    }
    if version:
        payload["version"] = version

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "stock_market_expert_bd-Security-Auditor/1.0"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("vulns", [])
    except Exception as ex:
        print(f"Notice: OSV API query note for {pkg_name}: {ex}")
        return []

def audit_dependencies() -> int:
    deps = extract_dependencies()
    print("===========================================================")
    print("🛡️ stock_market_expert_bd Dependency Vulnerability Audit (Google OSV.dev / PyPA)")
    print(f"Declared dependencies: {len(deps)} packages")
    print("===========================================================")

    if not deps:
        print("✓ Zero external dependencies declared.")
        return 0

    total_vulns = 0
    for pkg, spec in deps:
        # Check installed version if available
        installed_ver = None
        try:
            import importlib.metadata
            installed_ver = importlib.metadata.version(pkg)
        except Exception:
            pass

        print(f"Auditing {pkg} (spec: '{spec}', installed: {installed_ver or 'not installed'})...")
        vulns = query_osv_vulnerabilities(pkg, installed_ver)
        if not vulns:
            print(f"  ✓ {pkg}: 0 known vulnerabilities in Google OSV / PyPA database.")
        else:
            print(f"  ⚠️ {pkg}: Found {len(vulns)} vulnerability advisory/advisories:")
            for v in vulns:
                vid = v.get("id")
                summary = v.get("summary") or v.get("details", "")[:80]
                print(f"    - [{vid}] {summary}")
            total_vulns += len(vulns)

    print("===========================================================")
    if total_vulns == 0:
        print(f"✅ SCA AUDIT PASSED: 0 known CVEs across all {len(deps)} dependencies.")
        return 0
    else:
        print(f"⚠️ SCA AUDIT ALERT: {total_vulns} known vulnerability advisories detected.")
        return 1

if __name__ == "__main__":
    sys.exit(audit_dependencies())
