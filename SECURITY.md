# Security Policy & Vulnerability Disclosure

## 🛡️ Security Architecture & Safety Boundaries

`stock_market_expert_bd` is engineered with the institutional rigor of high-stakes capital market systems. It enforces strict security boundaries to protect end-users, trading accounts, and local execution environments:

1. **Zero Dynamic Code Execution & AST Purity**:
   - The engine strictly prohibits arbitrary dynamic execution primitives (`eval()`, `exec()`, `compile()`).
   - All quantitative indicator pipelines, risk parity solvers, and technical signal calculators are deterministic, pre-compiled Python algorithms.

2. **Supply Chain & Dependency Hygiene**:
   - Zero telemetry, zero analytics tracking, and zero hidden network backdoors.
   - Runtime dependencies (`requests`, `beautifulsoup4`, `lxml`, `matplotlib`, `pandas`, `bdshare`, `pdfplumber`) are continuously verified against the **Google OSV.dev** and **PyPA Advisory Databases** for zero known Common Vulnerabilities and Exposures (CVEs).

3. **Subprocess & OS Injection Resistance**:
   - Subprocess executions (`subprocess.run`, `subprocess.Popen`) strictly utilize validated argument lists (`shell=False`).
   - Host shell command strings and dynamic command construction with untrusted inputs are strictly forbidden.

4. **Network Boundaries & Timeout Guards**:
   - All external HTTP connections to market data providers (e.g. DSE, Bangladesh Bank) enforce hard timeout limits (5s–10s) and validate URI schemes to prevent SSRF or socket hanging.

5. **Cryptographic Provenance & Tamper-Evident Ledgers (INV-6)**:
   - All forward test predictions and model evaluations are cryptographically anchored using SHA-256 block hashing (`forward_test_ledger_v2.json`), preventing retroactive manipulation or data tampering.

6. **Privacy & Credential Isolation**:
   - Repository source files and configuration layers are continuously audited via automated secret scanning (`tools/secret_scanner.py`) to guarantee zero leaked API tokens, private keys, or credentials.

---

## 📋 Supported Versions

We provide continuous security audits, vulnerability scans, and patches for the following versions:

| Version | Supported | Security Audit Status |
| :--- | :---: | :--- |
| `1.0.x` | :white_check_mark: | **Active** (Bandit 0-Vuln, Google OSV 0-CVE, Secrets 0-Leak) |
| `< 1.0` | :x: | Deprecated |

---

## 🔍 Continuous Security Scans & CI Enforcement

The repository maintains an automated, multi-tiered security and quality assurance pipeline executed on every commit and pull request via GitHub Actions ([`.github/workflows/security_audit.yml`](.github/workflows/security_audit.yml)):

1. **Static Application Security Testing (SAST)**:
   - Automated AST security scan via `bandit` across `main.py`, `scripts/`, and `tools/`.
   - Results exported to industry-standard SARIF format and uploaded to GitHub Security Advisory tab.
   - Zero Medium or High severity findings allowed.

2. **Software Composition Analysis (SCA)**:
   - Automated dependency audit via `tools/dependency_audit.py` querying **Google OSV.dev** and **PyPA Advisory Database**.
   - Zero vulnerable package versions allowed in production dependencies.

3. **Secret & Privacy Scanner**:
   - Automated source scanning via `tools/secret_scanner.py` for API tokens, private keys, passwords, and corporate email leaks.

4. **Security Posture & Invariant Suite**:
   - `tests/test_security_posture.py` programmatically verifies AST purity, timeout guards, and injection resistance.
   - Complete 100+ unit test suite enforces all 8 SPEC.md architecture invariants.

---

## 🚨 Reporting a Vulnerability

We value the contributions of security researchers and users in maintaining a trustworthy, safe financial engineering ecosystem.

If you discover a potential vulnerability or security flaw, please report it responsibly:

1. **GitHub Private Security Advisory (Preferred)**:
   - Go to the **Security** tab of the repository at [github.com/ashik1291/stock_market_expert_bd/security/advisories](https://github.com/ashik1291/stock_market_expert_bd/security/advisories).
   - Click **"New draft advisory"** and submit details with reproduction steps.

2. **Direct Contact**:
   - Maintainer: **Ashikur Rahman Bhuiyan** ([@ashik1291](https://github.com/ashik1291))
   - Email: `ashik1291@yahoo.com`
   - Subject: `[SECURITY] stock_market_expert_bd Vulnerability Report: <Brief Description>`

### Disclosure Guidelines
- Please provide detailed reproduction steps or a minimal proof-of-concept (PoC).
- Do not disclose security vulnerabilities publicly on GitHub issues or social media until a coordinated patch and release have been deployed.
- Reports will be acknowledged within 48 hours, with fixes prioritized for rapid release.
