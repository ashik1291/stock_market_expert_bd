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
2. **Database Verification & Decompression**: Checks `data/processed/dse.db`.
   - If missing or unpulled Git LFS pointer (<10KB), auto-decompresses `data/processed/dse.db.gz` (29MB) into `dse.db`.
   - Fallback: triggers `git lfs pull` or `scripts/rebuild_database.py`.
3. **Configurations**: Verifies `config/` registries and local user profile/portfolio templates.
4. **Live Market Sync & Missed Date Backfill (`live_market_sync.py`)**:
   - Compares the uncompressed DB max date against the live exchange trading calendar (Asia/Dhaka).
   - Detects any missed intermediate trading sessions and backfills historical OHLCV bars across tracked equities.
   - Scrapes live market prices across the entire universe (~395 instruments), DSE PSI corporate disclosures, and index statistics.
   - Syncs central bank macro interest rates (91-Day T-bill, repo, equity hurdle).
   - Refreshes Wilder's RSI, rolling factor ICs, and directional rise/fall predictions.
5. **Readiness Dashboard**: Confirms 100% operational readiness and outputs a live mark-to-market status report saved to `reports/readiness/latest_live_readiness.md` for both CLI users and AI agents.
