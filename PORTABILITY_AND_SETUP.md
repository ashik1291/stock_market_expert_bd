# 🌐 stock_market_expert_bd: Multi-Device Portability & Instant Setup Guide

This guide explains how to push this repository from your current machine and set it up instantly on any other device (Windows, Linux, or macOS) with zero hassle.

---

## ⚡ The Single Magic Word: `ready`

On any new device, you only need to run or type one word: **`ready`**.

The system will automatically:
1. Install all required Python dependencies from `requirements.txt`.
2. Verify SQLite database integrity (auto-decompresses `dse.db.gz` if database is unpulled or fresh).
3. Verify all configuration registries and portfolio ledgers.
4. Run daily heartbeat sync (`check_daily_sync.py`) to pull any closing market sessions.
5. Print a complete system health and readiness dashboard.

---

## 📤 Step 1: Pushing from Your Current Machine

Before moving to another device, ensure all your local changes are pushed to your remote Git repository (e.g. GitHub, GitLab, or private server):

```bash
# If remote is not added yet:
git remote add origin <YOUR_GITHUB_OR_GITLAB_URL>

# Push master branch (including Git LFS pointers):
git push -u origin master
```

> **Note on Large Files**: Large binary files (`*.db` and `*.zip`) are tracked via **Git LFS** and defined in `.gitattributes`. Additionally, a compressed 29MB fallback (`data/processed/dse.db.gz`) is stored in standard Git so cloning works even on machines without Git LFS!

---

## 📥 Step 2: Fetching / Cloning on a New Machine

On the new device:

```bash
# Clone the repository
git clone <YOUR_GITHUB_OR_GITLAB_URL>
cd stock_market_expert_bd
```

*(If you already have the repository on that device, just pull the latest changes)*:
```bash
git pull origin master
```

---

## 🚀 Step 3: Triggering `ready` (Pick Any Method)

Choose whichever method is easiest on your new device:

### Option A: In Antigravity Agent Chat (Easiest)
Simply type the single word into the chat window:
```
ready
```
*The agent will run `scripts/bootstrap.py`, self-heal any missing components, and confirm when the system is 100% armed.*

### Option B: Windows 1-Click
- Double-click **`ready.bat`** (in Command Prompt)
- OR run in PowerShell:
```powershell
.\ready.ps1
```

### Option C: Linux / macOS 1-Click
```bash
chmod +x ready.sh
./ready.sh
```

### Option D: Cross-Platform Python CLI
```bash
python main.py ready
```

---

## 🛠️ What `ready` Does Behind the Scenes

```
                                [TRIGGER: 'ready']
                                        │
                    ┌───────────────────┴───────────────────┐
                    ▼                                       ▼
        [1. Check Dependencies]                 [2. Verify SQLite DB]
      Inspects installed packages.            Checks data/processed/dse.db.
    If missing, automatically runs:         If missing or LFS pointer (<10KB):
     pip install -r requirements.txt         Auto-decompresses dse.db.gz (29MB)
                    │                                       │
                    └───────────────────┬───────────────────┘
                                        ▼
                            [3. Configuration Check]
                         Verifies config/ & portfolio.json
                                        │
                                        ▼
                           [4. Silent Daily Sync]
                     Executes scripts/check_daily_sync.py
                     (Pulls latest close & steps ledger)
                                        │
                                        ▼
                         [5. SYSTEM 100% OPERATIONAL]
```

---

## 📋 Daily Operational Cheat-Sheet

Once `ready` is executed, the system is permanently autonomous:

| Need | Action / Command |
| :--- | :--- |
| **System Status & Portfolio** | Type `status` or run `python main.py status` |
| **Daily Prediction Radar** | Type `predict` or run `python main.py scan` |
| **Daily 3:30 PM Alpha Run** | Type `alpha` or run `python main.py alpha` |
| **Buffett Sector Screener** | Type `best` or run `python main.py best2` |
| **Monthly Deployment Plan** | Type `plan 2000` or run `python main.py plan 2000` |
| **Full 11-Step Refresh** | Type `refresh` or run `python main.py refresh` |
| **Setup Cron / Scheduled Jobs** | Type `schedule install` or run `python main.py schedule install` |

---

## ⏰ Step 4: Production Server Deployment & Automated Cron / Scheduled Jobs

When deploying this repository to a dedicated Linux server, cloud VM, Windows server, or Docker container, you can arm all recurring market automations with a single command.

### 🐧 Linux / macOS Servers (Crontab / Systemd)
```bash
# 1. Automatic installation into crontab:
python main.py schedule install
# or:
bash scripts/setup_cron.sh install

# 2. Inspect active crontab:
python main.py schedule status

# 3. For modern systemd servers (timers):
bash scripts/setup_cron.sh systemd
```

### 🪟 Windows Servers (Task Scheduler)
```powershell
# In PowerShell:
python main.py schedule install
# or:
powershell -ExecutionPolicy Bypass -File .\scripts\setup_scheduled_tasks.ps1 -Action Install
```

### 🐳 Docker / Headless Cloud Containers (Continuous Daemon)
If running inside a Docker container, Kubernetes pod, or cloud instance where crontab is unavailable:
```bash
# Runs an in-process, timezone-aware (Asia/Dhaka UTC+6) scheduling daemon:
python main.py schedule daemon
```

### 🕒 Automated Trading Schedule (Asia/Dhaka UTC+6):
- **15:30 BST (Sun–Thu)**: Post-market closing price ingestion, Bangladesh Bank hurdle sync, forward ledger advance, Empirical Bayes calibration, and daily rise/fall scan (`auto_daily_alpha_routine.py`).
- **16:15 BST (Sun–Thu)**: Master pipeline execution, forensic filtration, portfolio audit, and English + Bengali position plans (`run_daily_pipeline.py`).
- **18:00 BST (Thursday)**: Comprehensive weekly multi-factor knowledge base refresh and 52-week corridor updates (`analyzer.py category_a weekly`).
- **19:00 BST (Thursday)**: Master database baseline compression and Git sync (`push_db_update.py`).
- **11:30 & 13:30 BST (Sun–Thu)**: Midday market heartbeat and price synchronization.

