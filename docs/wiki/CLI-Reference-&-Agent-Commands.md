# 💻 CLI Reference & AI Agent Commands

The system supports both standard command-line execution and zero-friction single-word AI agent prompts.

---

## ⚡ Single-Word Agent Quick Triggers

When pair programming with AI agents (Antigravity, Claude Code, Cursor, Codex), use these minimalist single-word instructions:

| Trigger | Engine Action |
| :--- | :--- |
| `ready` | Runs self-healing bootstrap, checks packages, restores database, verifies invariants. |
| `predict` | Executes daily directional rise/fall scanner with latest Bayesian factor weights. |
| `recommend` | Runs the tri-horizon multi-factor screener and generates top 10 ranked stock picks. |
| `plan 10000` | Generates a 3-tier tranches allocation plan for a specific capital sum (e.g., ৳10,000). |
| `audit` | Runs the institutional quantitative audit and verifies all 8 invariants. |
| `alpha` | Advances forward test ledger and recalibrates empirical Bayes factor weights. |
| `climate` | Generates liquidity matrix, volume anomaly surveillance, and macroeconomic report. |
| `check TICKER` | Runs deep-dive 12-factor analysis for an individual ticker (e.g., `check SQURPHARMA`). |

---

## 🖥️ Command-Line Interface (`main.py`)

All commands can also be run natively via terminal:

```bash
# 1. System Self-Healing & Health Check
python main.py ready

# 2. Daily Market-Wide Price Prediction
python main.py predict

# 3. Weekly Top Stock Recommendations
python main.py recommend

# 4. Individual Stock Deep-Dive
python main.py analyze SQURPHARMA

# 5. Capital Deployment & Portfolio Allocation
python main.py plan 10000

# 6. Run System Conformance Guard
python main.py audit

# 7. Update Point-in-Time Disclosures
python main.py pit-resolve
```
