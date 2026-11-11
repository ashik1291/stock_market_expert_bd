"""
stock_market_expert_bd — GitHub Wiki Sync Engine.
Pushes all Markdown documentation from docs/wiki/ to the repository wiki.
Target: https://github.com/ashik1291/stock_market_expert_bd.wiki.git
"""

import os
import sys
import shutil
import tempfile
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
WIKI_DIR = BASE_DIR / "docs" / "wiki"
WIKI_REMOTE = "https://github.com/ashik1291/stock_market_expert_bd.wiki.git"

def sync_wiki():
    if not WIKI_DIR.exists():
        print(f"Error: {WIKI_DIR} does not exist.")
        sys.exit(1)

    print(f"Reading wiki source documents from: {WIKI_DIR}")
    files = list(WIKI_DIR.glob("*.md"))
    print(f"Found {len(files)} wiki pages: {[f.name for f in files]}")

    with tempfile.TemporaryDirectory() as td:
        print("Cloning GitHub wiki repository...")
        res = subprocess.run(["git", "clone", WIKI_REMOTE, td], capture_output=True, text=True)
        
        if res.returncode != 0:
            print("\n⚠️ Note: The GitHub Wiki repository has not been initialized yet on GitHub.")
            print("To initialize it (one-time setup):")
            print("  1. Go to https://github.com/ashik1291/stock_market_expert_bd/wiki")
            print("  2. Click 'Create the first page' and save it.")
            print("  3. Re-run: python scripts/sync_wiki.py\n")
            return False

        # Copy all wiki files to temp directory
        for f in files:
            shutil.copyfile(f, Path(td) / f.name)

        # Commit and push
        subprocess.run(["git", "add", "."], cwd=td)
        status = subprocess.run(["git", "status", "--porcelain"], cwd=td, capture_output=True, text=True)
        if not status.stdout.strip():
            print("Wiki is already up to date with latest documentation.")
            return True

        subprocess.run(["git", "config", "user.name", "Ashikur Rahman Bhuiyan"], cwd=td)
        subprocess.run(["git", "config", "user.email", "ashik1291@yahoo.com"], cwd=td)
        subprocess.run(["git", "commit", "-m", "docs(wiki): update quantitative documentation and sector matrix"], cwd=td)
        
        push_res = subprocess.run(["git", "push", "origin", "master"], cwd=td, capture_output=True, text=True)
        if push_res.returncode == 0:
            print("✅ Wiki successfully updated on GitHub!")
            return True
        else:
            print(f"Push failed: {push_res.stderr}")
            return False

if __name__ == "__main__":
    sync_wiki()
