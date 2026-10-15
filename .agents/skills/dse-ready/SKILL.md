---
name: dse-ready
description: >
  Single-word self-healing machine bootstrap engine.
  Triggered when user types 'ready', 'setup', 'bootstrap', or 'init' on a new or existing machine.
  Installs missing dependencies, verifies database integrity (decompresses dse.db.gz if needed),
  checks Git LFS pointers, runs daily heartbeat sync, and validates full system readiness.
---

# dse-ready

One-word bootstrap & self-healing engine for the DSE Quantitative System across different devices.

## Trigger Words
- **`ready`**
- **`setup`**
- **`bootstrap`**
- **`init`**

## Execution Commands

### From Agent Chat:
Typing `ready` executes the bootstrap protocol:
```powershell
python scripts/bootstrap.py
```

### From CLI / Terminal:
- **Windows (Double-Click / CMD)**: `ready.bat`
- **Windows PowerShell**: `.\ready.ps1` or `python main.py ready`
- **Linux / macOS**: `./ready.sh` or `python3 main.py ready`

## What It Automatically Checks & Self-Heals:
1. **Python Dependencies**: Verifies packages from `requirements.txt` (`requests`, `beautifulsoup4`, `lxml`, `matplotlib`, `pandas`, `bdshare`, `pdfplumber`). Auto-installs if missing.
2. **Database Verification**: Checks `data/processed/dse.db`.
   - If missing or unpulled Git LFS pointer (<10KB), auto-decompresses `data/processed/dse.db.gz` (29MB) into `dse.db`.
   - Fallback: triggers `git lfs pull` or `scripts/rebuild_database.py`.
3. **Configurations**: Verifies `config/` registries and portfolios.
4. **Heartbeat Sync**: Executes `check_daily_sync.py` to ingest any pending market close sessions.
5. **Readiness Dashboard**: Confirms 100% operational readiness.
