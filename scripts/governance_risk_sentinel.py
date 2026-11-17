"""
scripts/governance_risk_sentinel.py — Institutional Governance, Political Exposure & Legal Risk Sentinel
Evaluates non-financial tail risks: sponsor arrests, court receivership proceedings,
bank account freezes, money laundering probes, and BSEC/regulatory scrutiny.
"""

from __future__ import annotations

import sys
import json
import sqlite3
import argparse
import datetime
from pathlib import Path

# Enforce UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"

# Institutional Curated Knowledge Base for Top DSE Groups & Conglomerates
KNOWN_GOVERNANCE_PROFILES = {
    "BXPHARMA": {
        "political_exposure_score": 75.0,
        "legal_risk_tier": "HIGH",
        "sponsor_legal_issues": 1,
        "receivership_court_petition": 1,
        "bank_accounts_frozen": 0,
        "bsec_investigation": 1,
        "regulatory_sanctions_count": 2,
        "flags": [
            "PROMOTER_LEGAL_CUSTODY: Key promoter/vice-chairman in legal custody facing state corruption cases.",
            "RECEIVERSHIP_LITIGATION: High Court petition/rulings regarding appointment of receiver over Beximco Group assets.",
            "BANKING_CREDIT_REVIEW: Major domestic commercial lenders reviewing conglomerate credit exposures under central bank directives."
        ],
        "notes": "Operationally profitable with low debt (D/E: 0.13) and UK/US export assets, but carries severe conglomerate contagion and legal governance overhang."
    },
    "BEXIMCO": {
        "political_exposure_score": 95.0,
        "legal_risk_tier": "CRITICAL",
        "sponsor_legal_issues": 1,
        "receivership_court_petition": 1,
        "bank_accounts_frozen": 1,
        "bsec_investigation": 1,
        "regulatory_sanctions_count": 5,
        "flags": [
            "CONGLOMERATE_RECEIVERSHIP: Central bank appointed administrator/receiver following High Court orders.",
            "FACTORY_WORKER_UNREST: Intermittent worker salary disputes and road blockades at Gazipur industrial facilities.",
            "FINANCIAL_CRIME_PROBE: CID and BSEC financial crime task force investigating stock market manipulation and bond issuances."
        ],
        "notes": "Parent holding company facing acute structural insolvency and state receivership. STRICTLY AVOID."
    },
    "SQURPHARMA": {
        "political_exposure_score": 10.0,
        "legal_risk_tier": "LOW",
        "sponsor_legal_issues": 0,
        "receivership_court_petition": 0,
        "bank_accounts_frozen": 0,
        "bsec_investigation": 0,
        "regulatory_sanctions_count": 0,
        "flags": [
            "PRISTINE_GOVERNANCE: Professional non-family executive management with 50+ year clean audit track record.",
            "NET_CASH_BALANCE_SHEET: Zero long-term debt; sovereign regulatory compliance."
        ],
        "notes": "Gold standard corporate governance on DSE. Prime institutional allocation moat."
    },
    "GP": {
        "political_exposure_score": 15.0,
        "legal_risk_tier": "LOW",
        "sponsor_legal_issues": 0,
        "receivership_court_petition": 0,
        "bank_accounts_frozen": 0,
        "bsec_investigation": 0,
        "regulatory_sanctions_count": 1,
        "flags": [
            "MULTINATIONAL_PARENTAGE: Telenor ASA (Norway) majority control ensures OECD-level anti-corruption compliance.",
            "BTRC_REGULATORY_FRICTION: Periodic telecom audit claim disputes under ADR / Supreme Court arbitration."
        ],
        "notes": "Exceptional governance standards with minor sovereign telecom tax friction."
    },
    "RENATA": {
        "political_exposure_score": 10.0,
        "legal_risk_tier": "LOW",
        "sponsor_legal_issues": 0,
        "receivership_court_petition": 0,
        "bank_accounts_frozen": 0,
        "bsec_investigation": 0,
        "regulatory_sanctions_count": 0,
        "flags": [
            "INDEPENDENT_TRUST_GOVERNANCE: Core shareholder Sajida Foundation ensures social-enterprise governance purity.",
            "NO_POLITICAL_PATRONAGE: Non-aligned pharmaceutical innovator."
        ],
        "notes": "Top-tier ethical governance. High institutional confidence."
    },
    "ORIONPHARM": {
        "political_exposure_score": 80.0,
        "legal_risk_tier": "HIGH",
        "sponsor_legal_issues": 1,
        "receivership_court_petition": 0,
        "bank_accounts_frozen": 1,
        "bsec_investigation": 1,
        "regulatory_sanctions_count": 2,
        "flags": [
            "POLITICAL_PATRONAGE_SCRUTINY: Conglomerate sponsors investigated for past power-sector capacity payments and contracts.",
            "BSEC_FINANCIAL_AUDIT: Financial statements and related-party asset transfers under regulatory review."
        ],
        "notes": "Elevated promoter political exposure and related-party financial risks."
    },
    "OLYMPIC": {
        "political_exposure_score": 15.0,
        "legal_risk_tier": "LOW",
        "sponsor_legal_issues": 0,
        "receivership_court_petition": 0,
        "bank_accounts_frozen": 0,
        "bsec_investigation": 0,
        "regulatory_sanctions_count": 0,
        "flags": [
            "MULTINATIONAL_ALLIANCE: Board oversight with foreign institutional fund representation.",
            "CASH_GENERATION_MOAT: Debt-free FMCG leader with zero politically exposed loans."
        ],
        "notes": "Sound governance, clean legal record, stable FMCG cash flows."
    },
    "JAMUNAOIL": {
        "political_exposure_score": 20.0,
        "legal_risk_tier": "LOW",
        "sponsor_legal_issues": 0,
        "receivership_court_petition": 0,
        "bank_accounts_frozen": 0,
        "bsec_investigation": 0,
        "regulatory_sanctions_count": 0,
        "flags": [
            "SOVEREIGN_GOVT_MOAT: 60.08% Government of Bangladesh owned (BPC subsidiary).",
            "STATUTORY_MONOPOLY: Vital national energy infrastructure; immune to promoter fraud or receivership."
        ],
        "notes": "Sovereign government shield protects from private sponsor defaults."
    },
    "WALTONHIL": {
        "political_exposure_score": 30.0,
        "legal_risk_tier": "MEDIUM",
        "sponsor_legal_issues": 0,
        "receivership_court_petition": 0,
        "bank_accounts_frozen": 0,
        "bsec_investigation": 0,
        "regulatory_sanctions_count": 1,
        "flags": [
            "CONCENTRATED_SPONSOR_HOLDING: Sponsors own 71.1% equity; public float limited.",
            "DOMESTIC_CREDIT_UTILIZATION: Large working capital bank loans under high interest rate monitoring."
        ],
        "notes": "Strong industrial moat and clean promoter track record, with moderate leverage monitoring."
    }
}


def get_db():
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def evaluate_governance_risk(ticker: str, persist: bool = True) -> dict:
    ticker = ticker.strip().upper()
    assessment_date = datetime.date.today().isoformat()

    # Check curated profile
    if ticker in KNOWN_GOVERNANCE_PROFILES:
        prof = KNOWN_GOVERNANCE_PROFILES[ticker]
        pol_score = prof["political_exposure_score"]
        tier = prof["legal_risk_tier"]
        flags = list(prof["flags"])
        notes = prof["notes"]
        sponsor_legal = prof["sponsor_legal_issues"]
        receivership = prof["receivership_court_petition"]
        frozen = prof["bank_accounts_frozen"]
        bsec_probe = prof["bsec_investigation"]
        sanctions = prof["regulatory_sanctions_count"]
    else:
        # Dynamic Heuristic Scanner from News & Disclosures
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT headline, date FROM news
            WHERE ticker = ? OR headline LIKE ?
            ORDER BY date DESC LIMIT 20
            """,
            (ticker, f"%{ticker}%")
        )
        news_rows = cur.fetchall()
        conn.close()

        pol_score = 15.0
        tier = "LOW"
        flags = []
        sponsor_legal = 0
        receivership = 0
        frozen = 0
        bsec_probe = 0
        sanctions = 0

        keywords_critical = ["receivership", "arrest", "money laundering", "freeze", "insolvency", "scam"]
        keywords_high = ["bsec probe", "investigation", "court", "probe", "fraud", "default", "manipulation"]

        for n in news_rows:
            h = n["headline"].lower()
            if any(k in h for k in keywords_critical):
                pol_score = max(pol_score, 85.0)
                tier = "CRITICAL"
                flags.append(f"LEGAL_ALERT [{n['date']}]: {n['headline']}")
                if "receivership" in h:
                    receivership = 1
                if "freeze" in h:
                    frozen = 1
                if "arrest" in h:
                    sponsor_legal = 1
            elif any(k in h for k in keywords_high):
                pol_score = max(pol_score, 50.0)
                if tier != "CRITICAL":
                    tier = "HIGH"
                flags.append(f"REGULATORY_NOTICE [{n['date']}]: {n['headline']}")
                bsec_probe = 1

        if not flags:
            flags.append("STANDARD_GOVERNANCE: No active court receivership or BSEC enforcement notices found.")
            notes = "Standard regulatory compliance track record based on public DSE disclosures."
        else:
            notes = f"Scanned {len(flags)} regulatory or legal warning flags from recent public disclosures."

    result = {
        "ticker": ticker,
        "assessment_date": assessment_date,
        "political_exposure_score": pol_score,
        "legal_risk_tier": tier,
        "sponsor_legal_issues": sponsor_legal,
        "receivership_court_petition": receivership,
        "bank_accounts_frozen": frozen,
        "bsec_investigation": bsec_probe,
        "regulatory_sanctions_count": sanctions,
        "active_flags": flags,
        "governance_notes": notes,
    }

    if persist and DB_PATH.exists():
        try:
            conn = get_db()
            conn.execute(
                """
                INSERT OR REPLACE INTO governance_risk_audit
                (ticker, assessment_date, political_exposure_score, legal_risk_tier,
                 sponsor_legal_issues, receivership_court_petition, bank_accounts_frozen,
                 bsec_investigation, regulatory_sanctions_count, active_flags, governance_notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ticker, assessment_date, pol_score, tier,
                    sponsor_legal, receivership, frozen, bsec_probe,
                    sanctions, json.dumps(flags), notes
                )
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Warning: Failed to persist governance audit: {e}", file=sys.stderr)

    return result


def print_governance_report(ticker: str):
    res = evaluate_governance_risk(ticker, persist=True)

    tier_icon = {
        "LOW": "🟢 LOW RISK",
        "MEDIUM": "🟡 MODERATE RISK",
        "HIGH": "🟠 HIGH RISK (EXPOSURE WARNING)",
        "CRITICAL": "🔴 CRITICAL RISK (STRICT AVOID)"
    }.get(res["legal_risk_tier"], res["legal_risk_tier"])

    print("=" * 85)
    print(f"⚖️ INSTITUTIONAL GOVERNANCE & LEGAL RISK AUDIT: {res['ticker']}")
    print("=" * 85)
    print(f"  * Assessment Date       : {res['assessment_date']}")
    print(f"  * Legal Risk Status     : {tier_icon}")
    print(f"  * Political Exposure    : {res['political_exposure_score']}/100")
    print(f"  * Promoter Legal Issues : {'⚠️ ACTIVE' if res['sponsor_legal_issues'] else '✓ None Reported'}")
    print(f"  * Court Receivership    : {'🚨 FILED / ACTIVE' if res['receivership_court_petition'] else '✓ None'}")
    print(f"  * Accounts Frozen       : {'🚨 ACTIVE' if res['bank_accounts_frozen'] else '✓ Normal Banking Access'}")
    print(f"  * BSEC Investigations   : {'⚠️ ACTIVE PROBE' if res['bsec_investigation'] else '✓ In Good Standing'}")
    print("-" * 85)
    print("📜 ACTIVE GOVERNANCE & FORENSIC FLAGS:")
    for f in res["active_flags"]:
        print(f"  • {f}")
    print("-" * 85)
    print(f"💡 Institutional Verdict:")
    print(f"   {res['governance_notes']}")
    print("=" * 85)


def list_high_risk_governance():
    print("=" * 85)
    print("🚨 HIGH & CRITICAL GOVERNANCE RISK STOCKS (DSE FORENSIC SURVEILLANCE)")
    print("=" * 85)
    print(f"{'Ticker':<12} {'Risk Tier':<15} {'Pol Score':<11} {'Receivership':<14} {'Sponsor Issues':<16} {'Notes'}")
    print("-" * 85)
    high_risk_list = []
    for t in sorted(KNOWN_GOVERNANCE_PROFILES.keys()):
        prof = KNOWN_GOVERNANCE_PROFILES[t]
        if prof["legal_risk_tier"] in ("HIGH", "CRITICAL"):
            print(f"{t:<12} {prof['legal_risk_tier']:<15} {prof['political_exposure_score']:<11} {'YES' if prof['receivership_court_petition'] else 'NO':<14} {'YES' if prof['sponsor_legal_issues'] else 'NO':<16} {prof['notes'][:30]}...")
            high_risk_list.append({"ticker": t, **prof})
    print("=" * 85)
    return high_risk_list


def main():
    parser = argparse.ArgumentParser(description="DSE Governance, Political Exposure & Legal Risk Sentinel")
    parser.add_argument("ticker", nargs="?", default="BXPHARMA", help="Stock ticker symbol (e.g. BXPHARMA, SQURPHARMA, BEXIMCO)")
    parser.add_argument("--high-risk", action="store_true", help="List all tracked high and critical governance risk stocks")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args()

    if args.high_risk:
        list_high_risk_governance()
    else:
        if args.json:
            res = evaluate_governance_risk(args.ticker, persist=True)
            print(json.dumps(res, indent=2))
        else:
            print_governance_report(args.ticker)


if __name__ == "__main__":
    main()
