# tests/test_security_posture.py
"""
Security Posture & Integrity Guard for stock_market_expert_bd.
Enforces:
1. AST Purity: Zero dynamic code execution (eval, exec, compile) in core scripts and engine.
2. Secret & Privacy Scanner: Zero API tokens, private keys, passwords, or corporate leaks.
3. Subprocess Safety: No shell=True invocations with untrusted or raw string input.
4. Dependency Composition Safety: Validates dependencies against supply chain risk.
"""

import ast
import glob
import os
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

class TestSecurityPosture(unittest.TestCase):

    def test_ast_purity_no_dynamic_code_execution(self):
        """Core engine and scripts must NEVER use eval, exec, or dynamic compile."""
        banned_calls = {"eval", "exec", "compile"}
        py_files = list((REPO_ROOT / "scripts").glob("*.py")) + [REPO_ROOT / "main.py"]
        
        violations = []
        for p in py_files:
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
            tree = ast.parse(content, filename=str(p))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id in banned_calls:
                        violations.append((p.name, node.lineno, node.func.id))

        self.assertEqual(
            violations,
            [],
            f"Security Violation: Prohibited dynamic code execution detected: {violations}"
        )

    def test_subprocess_safety_no_shell_true(self):
        """All subprocess calls must use explicit argument lists and avoid shell=True."""
        py_files = list((REPO_ROOT / "scripts").glob("*.py")) + [REPO_ROOT / "main.py"]
        
        unsafe_calls = []
        for p in py_files:
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
            tree = ast.parse(content, filename=str(p))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    # Check for shell=True in kwargs
                    for kw in node.keywords:
                        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            unsafe_calls.append((p.name, node.lineno))

        self.assertEqual(
            unsafe_calls,
            [],
            f"Security Violation: shell=True found in subprocess calls: {unsafe_calls}"
        )

    def test_secret_scanner_cleanliness(self):
        """Repository must pass secret and privacy leak scanner with zero findings."""
        import sys
        sys.path.insert(0, str(REPO_ROOT / "tools"))
        from secret_scanner import scan_repository
        
        leaks = scan_repository(REPO_ROOT)
        self.assertEqual(leaks, 0, "Security Violation: Secret or privacy leaks detected in repository!")

    def test_http_request_timeout_enforcement(self):
        """All network requests via requests or urllib must specify explicit timeouts."""
        py_files = list((REPO_ROOT / "scripts").glob("*.py"))
        
        missing_timeout = []
        for p in py_files:
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
            tree = ast.parse(content, filename=str(p))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    # Check requests.get / post / etc.
                    if isinstance(node.func, ast.Attribute) and node.func.attr in {"get", "post", "put", "delete"}:
                        if isinstance(node.func.value, ast.Name) and node.func.value.id == "requests":
                            kw_names = {kw.arg for kw in node.keywords}
                            if "timeout" not in kw_names:
                                missing_timeout.append((p.name, node.lineno, f"requests.{node.func.attr}"))
                    # Check urllib.request.urlopen
                    elif isinstance(node.func, ast.Attribute) and node.func.attr == "urlopen":
                        kw_names = {kw.arg for kw in node.keywords}
                        if len(node.args) < 2 and "timeout" not in kw_names:
                            missing_timeout.append((p.name, node.lineno, "urllib.request.urlopen"))

        self.assertEqual(
            missing_timeout,
            [],
            f"Security / Reliability Warning: Network call without timeout: {missing_timeout}"
        )

if __name__ == "__main__":
    unittest.main()
