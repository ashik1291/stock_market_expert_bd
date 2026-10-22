"""
DSE Auditor Footnote, PSI & Legal Risk Parser.
Scans DSE disclosures, company PSI announcements, and annual reports for:
  1. Auditor Opinion: Qualified Opinion, Adverse Opinion, Disclaimer, Going Concern.
  2. Emphasis of Matter: Disputed NBR tax demands, customs claims, unpaid staff funds.
  3. Regulatory Probes: BSEC investigation, inquiry committee, CCG non-compliance.
  4. Financial Distress: Overdue loan interest, defaulted L/C, negative working capital.

Outputs table: `auditor_risk_flags` in data/processed/dse.db.
"""

import sys
import re
import json
import sqlite3
import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = BASE_DIR / "data" / "processed" / "dse.db"

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Critical Red Flags (Instant Rejection)
CRITICAL_FLAGS = [
    (r"\bqualified opinion\b", "QUALIFIED_AUDIT_OPINION", "Auditor refused clean sign-off"),
    (r"\badverse opinion\b", "ADVERSE_AUDIT_OPINION", "Financial statements materially misleading"),
    (r"\bdisclaimer of opinion\b", "DISCLAIMER_OF_OPINION", "Auditor unable to verify accounts"),
    (r"\bgoing concern\b.*?\buncertainty\b", "GOING_CONCERN_RISK", "Company may shut down in 12 months"),
    (r"\bmaterial uncertainty\b", "GOING_CONCERN_RISK", "Severe doubts on business continuity"),
    (r"\bdefaul(t|ted|ter)\b.*?\b(loan|bank|cib)\b", "LOAN_DEFAULT", "Bank loan classified / default"),
]

# Warning Flags (Valuation Penalty / Downgrade)
WARNING_FLAGS = [
    (r"\bdispute(d)?\b.*?\b(tax|nbr|vat|customs)\b", "TAX_DISPUTE", "Pending large tax/customs demand"),
    (r"\bnbr\b.*?\bdemand\b", "TAX_DISPUTE", "NBR tax demand under dispute"),
    (r"\bemphasis of matter\b", "EMPHASIS_OF_MATTER", "Auditor flagged specific operational risk"),
    (r"\bbsec\b.*?\b(probe|inquir\w*|investigat\w*|fine\w*|penalt\w*|manipulat\w*)\b", "REGULATORY_PROBE", "BSEC regulatory enforcement / probe"),
    (r"\b(fine|penalty|penalised|penalized)\b.*?\b(manipulation|rules violation|bsec)\b", "REGULATORY_PROBE", "Penalty for securities rules violation"),
    (r"\bunpaid\b.*?\b(pf|provident|gratuity|wppf)\b", "UNPAID_STAFF_FUND", "Company failing to fund staff liability"),
    (r"\barrear\b.*?\b(gas|electricity|power|rent)\b", "UTILITY_ARREARS", "Utility bills unpaid"),
]


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS auditor_risk_flags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            risk_level TEXT NOT NULL, -- CRITICAL, WARNING, CLEAN
            flag_code TEXT NOT NULL,
            description TEXT,
            source_text TEXT,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ticker, flag_code, date)
        )
    """)
    conn.commit()
    conn.close()


def scan_news_and_disclosures():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Load company aliases for ticker resolution
    company_aliases = {
        "RAHIMAFOOD": ["rahima food", "rahima"],
        "LOVELLO": ["lovello", "taufika foods"],
        "SEAPHL": ["sea pearl", "seapearl"],
        "NAVANAPHARM": ["navana pharma", "navana"],
        "RACE": ["race management", "bangladesh race"],
    }
    try:
        config_path = BASE_DIR / "config" / "company_names.json"
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                c_names = json.load(f)
                for tick, name in c_names.items():
                    if tick not in company_aliases:
                        company_aliases[tick] = []
                    clean = re.sub(r"\b(ltd|limited|plc|bd|bangladesh)\b", "", name.lower()).strip()
                    if len(clean) >= 3:
                        company_aliases[tick].append(clean)
                    company_aliases[tick].append(name.lower().strip())
                    company_aliases[tick].append(tick.lower())
    except Exception:
        pass

    # Fetch news headlines
    news_items = conn.execute("""
        SELECT ticker, headline, date FROM news
    """).fetchall()

    flagged_records = []

    for item in news_items:
        t = item["ticker"]
        dt = item["date"] or datetime.date.today().isoformat()
        full_text = str(item["headline"] or "").lower()

        # If ticker is missing, try to resolve via company aliases
        if not t:
            for tick, aliases in company_aliases.items():
                for a in aliases:
                    if re.search(r"\b" + re.escape(a) + r"\b", full_text):
                        t = tick
                        break
                if t:
                    break

        if not t:
            t = "MARKET_WIDE"

        # Check critical flags
        for pattern, code, desc in CRITICAL_FLAGS:
            if re.search(pattern, full_text):
                flagged_records.append((t, dt, "CRITICAL", code, desc, item["headline"]))
                break

        # Check warning flags
        for pattern, code, desc in WARNING_FLAGS:
            if re.search(pattern, full_text):
                flagged_records.append((t, dt, "WARNING", code, desc, item["headline"]))
                break

    # Insert into database
    c = conn.cursor()
    inserted = 0
    for rec in flagged_records:
        try:
            c.execute("""
                INSERT OR IGNORE INTO auditor_risk_flags (ticker, date, risk_level, flag_code, description, source_text)
                VALUES (?, ?, ?, ?, ?, ?)
            """, rec)
            if c.rowcount > 0:
                inserted += 1
        except Exception:
            pass

    conn.commit()

    # Summary
    critical_count = conn.execute("SELECT count(DISTINCT ticker) FROM auditor_risk_flags WHERE risk_level='CRITICAL'").fetchone()[0]
    warning_count  = conn.execute("SELECT count(DISTINCT ticker) FROM auditor_risk_flags WHERE risk_level='WARNING'").fetchone()[0]
    conn.close()

    print("=" * 80)
    print("📋 DSE AUDITOR FOOTNOTE & REGULATORY RISK AUDIT")
    print("=" * 80)
    print(f"Scanned News & PSI Disclosures: {len(news_items):,} records")
    print(f"Flagged Critical Risks: {critical_count} Companies (Instant Rejection)")
    print(f"Flagged Warnings: {warning_count} Companies (Valuation Haircut)")
    print(f"New Database Flags Inserted: {inserted}")
    print("=" * 80)


if __name__ == "__main__":
    scan_news_and_disclosures()
