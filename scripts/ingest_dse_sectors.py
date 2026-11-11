"""
scripts/ingest_dse_sectors.py — Ingest Official DSE Sectors from Live DSE API

Resolves the 173 "Miscellaneous" sector bucket into official granular DSE sectors.
Keeps backward-compatible sector naming matching config/sectors.json.
"""

import sys
import sqlite3
import requests
import logging
from pathlib import Path

# Fix UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ingest_sectors")

# Backward-compatible DSE API -> Standard System Sector Name
# Matches config/sectors.json & existing conventions
DSE_SECTOR_MAP = {
    "Bank": "Banking",
    "PharmaChem": "Pharmaceuticals",
    "Telecom": "Telecom",
    "IT": "IT",
    "Cement": "Cement",
    "FuelPower": "Fuel_Power",
    "FoodAllied": "Food_Beverage",
    "Engineering": "Engineering",
    "Textile": "Textile",
    "Insurance": "Insurance",
    "Financial In": "Financial Institutions",
    "MutFund": "Mutual Funds",
    "Tannery": "Tannery",
    "Ceramic": "Ceramic",
    "PaperPrint": "Paper_Printing",
    "Jute": "Jute",
    "TravelLeisur": "Travel_Leisure",
    "ServRealEst": "Services_RealEstate",
    "CorpBond": "Corporate_Bond",
    "Debenture": "Debenture",
    "TBond": "Treasury_Bond",
    "Misc": "Miscellaneous",
}


def ingest_official_sectors(dry_run: bool = False) -> dict:
    if not DB_PATH.exists():
        log.error(f"Database not found at {DB_PATH}")
        return {"ok": False, "error": "Database not found"}

    log.info("Fetching official company sectors from DSE live API...")
    url = "https://dsebd.org/api/live/companies"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("rows", [])
        log.info(f"Retrieved {len(rows)} instruments from DSE live API.")
    except Exception as e:
        log.error(f"Failed to fetch DSE live companies API: {e}")
        return {"ok": False, "error": str(e)}

    # Map ticker -> standard sector
    api_map = {}
    for r in rows:
        code = r.get("code")
        raw_sector = r.get("sector")
        if code and raw_sector:
            api_map[code.strip().upper()] = DSE_SECTOR_MAP.get(raw_sector, raw_sector)

    # Special manual override for known aliases if missing from API
    if "GREENINS" not in api_map:
        api_map["GREENINS"] = "Insurance"

    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    cur = conn.cursor()

    db_companies = cur.execute("SELECT ticker, sector FROM companies").fetchall()
    log.info(f"Existing companies in database: {len(db_companies)}")

    updated_count = 0
    unchanged_count = 0
    not_found_count = 0

    reclassifications = []

    for ticker, old_sector in db_companies:
        new_sector = api_map.get(ticker)
        if not new_sector:
            not_found_count += 1
            continue

        if old_sector != new_sector:
            updated_count += 1
            reclassifications.append((ticker, old_sector, new_sector))
            if not dry_run:
                cur.execute("UPDATE companies SET sector = ? WHERE ticker = ?", (new_sector, ticker))
        else:
            unchanged_count += 1

    if not dry_run:
        conn.commit()
        log.info(f"Committed {updated_count} sector updates to SQLite database.")

    # Fetch new sector breakdown
    new_breakdown = cur.execute(
        "SELECT sector, COUNT(*) FROM companies GROUP BY sector ORDER BY COUNT(*) DESC"
    ).fetchall()
    conn.close()

    print("\n" + "=" * 80)
    print("🏢 DSE SECTOR RECLASSIFICATION AUDIT REPORT")
    print("=" * 80)
    print(f"Total Companies in DB: {len(db_companies)}")
    print(f"Sectors Updated:       {updated_count}")
    print(f"Already Accurate:      {unchanged_count}")
    print(f"Not Found in API:      {not_found_count}")
    print("-" * 80)
    print("New Sector Breakdown:")
    for sec, count in new_breakdown:
        print(f"  * {sec:<24}: {count:>3} companies")
    print("=" * 80 + "\n")

    return {
        "ok": True,
        "updated": updated_count,
        "unchanged": unchanged_count,
        "breakdown": dict(new_breakdown),
    }


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    res = ingest_official_sectors(dry_run=dry)
    sys.exit(0 if res.get("ok") else 1)
