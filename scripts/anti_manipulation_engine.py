"""
DSE Comprehensive Market Surveillance & Anti-Manipulation Engine.
Surveillance & Forensic Anomaly Detection for DSE:
  1. Volume Spike Anomaly (Volume >= 3.0x - 5.0x 20-day SMA)
  2. Speculative Junk Pump (Price surge on negative EPS or P/E > 50x)
  3. Low Free-Float & Low Sponsor Syndicate Corner (< 30% Sponsor + Low MCap)
  4. Upper Circuit Breaker Clamping (Consecutive near-limit price locks)
  5. Regulatory Enforcement & BSEC Penalty Flags (from auditor_risk_flags)

Generates:
  - Database Table: `manipulation_alerts` in data/processed/dse.db
  - English Report: reports/surveillance/YYYY-MM-DD_manipulation_alerts.md
  - Bengali Report: reports/surveillance/YYYY-MM-DD_manipulation_alerts_bn.md
  - Blacklist API: is_ticker_blacklisted(ticker) -> (is_blocked, reason)
"""

from __future__ import annotations

import sys
import json
import sqlite3
import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"
REPORTS_DIR = BASE_DIR / "reports" / "surveillance"

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def init_db(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS manipulation_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            risk_level TEXT NOT NULL, -- CRITICAL, HIGH, MEDIUM, LOW
            alert_type TEXT NOT NULL,
            risk_score INTEGER NOT NULL,
            volume_spike_ratio REAL,
            price_change_pct REAL,
            description TEXT,
            details_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ticker, date, alert_type)
        )
    """)
    conn.commit()


def run_surveillance_scan(asof_date: str | None = None) -> list[dict]:
    """Scans all tickers for volume anomalies, syndicate corners, and speculative pumps."""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    # Determine asof_date
    if not asof_date:
        row = conn.execute("SELECT MAX(date) as max_date FROM prices").fetchone()
        asof_date = row["max_date"] if row and row["max_date"] else datetime.date.today().isoformat()

    # Pre-fetch regulatory flags from auditor_risk_flags
    reg_flags: dict[str, list[dict]] = {}
    try:
        rows = conn.execute("SELECT ticker, risk_level, flag_code, description FROM auditor_risk_flags").fetchall()
        for r in rows:
            t = r["ticker"]
            if t not in reg_flags:
                reg_flags[t] = []
            reg_flags[t].append(dict(r))
    except Exception:
        pass

    # Fetch company profiles
    comp_map: dict[str, dict] = {}
    for c in conn.execute("SELECT ticker, name, sector, category, sponsor_holding_pct, market_cap_cr FROM companies"):
        comp_map[c["ticker"]] = dict(c)

    # Fetch latest fundamental snapshot for each ticker across all PIT historical dates
    fund_map: dict[str, dict] = {}
    query_pit = """
        SELECT f.ticker, f.eps, f.pe_ratio, f.nav 
        FROM fundamentals_pit f
        JOIN (
            SELECT ticker, MAX(snapshot_date) AS max_date
            FROM fundamentals_pit
            WHERE tradable_date <= ? AND publication_date <= ?
            GROUP BY ticker
        ) latest ON f.ticker = latest.ticker AND f.snapshot_date = latest.max_date
    """
    for f in conn.execute(query_pit, (asof_date, asof_date)):
        fund_map[f["ticker"]] = dict(f)

    # Fetch prices for active date
    active_prices = conn.execute(
        "SELECT ticker, open, high, low, close, volume FROM prices WHERE date = ?",
        (asof_date,)
    ).fetchall()

    alerts: list[dict] = []

    for p in active_prices:
        ticker = p["ticker"]
        close = float(p["close"] or 0.0)
        volume = float(p["volume"] or 0.0)
        if close <= 0:
            continue

        comp = comp_map.get(ticker, {})
        fund = fund_map.get(ticker, {})
        category = comp.get("category", "A")
        sponsor_pct = float(comp.get("sponsor_holding_pct") or 0.0)
        eps = float(fund.get("eps") or 0.0)
        pe = float(fund.get("pe_ratio") or 0.0)

        # Historical 20-day SMA Volume & previous close
        hist_rows = conn.execute("""
            SELECT close, volume 
            FROM prices 
            WHERE ticker = ? AND date < ? 
            ORDER BY date DESC LIMIT 20
        """, (ticker, asof_date)).fetchall()

        if not hist_rows or len(hist_rows) < 5:
            continue

        prev_close = float(hist_rows[0]["close"] or close)
        avg_vol_20 = sum(float(r["volume"] or 0.0) for r in hist_rows) / len(hist_rows)
        price_change_pct = round(((close - prev_close) / prev_close) * 100.0, 2) if prev_close > 0 else 0.0
        spike_ratio = round(volume / avg_vol_20, 2) if avg_vol_20 > 0 else 1.0

        # Forensic Tests
        flags = []
        score = 0

        # 1. Adaptive Volume Spike Anomaly (Tiered by Baseline Liquidity)
        # Large liquidity (avg > 500k): 2.5x is abnormal, 4.0x is extreme
        # Mid liquidity (50k - 500k):   3.0x is abnormal, 5.0x is extreme
        # Illiquid (< 50k):             requires absolute volume > 25,000 to prevent false micro-lot triggers
        if avg_vol_20 >= 500000:
            if spike_ratio >= 4.0:
                flags.append(("EXTREME_VOLUME_SPIKE", f"Large-cap volume is {spike_ratio:.1f}x 20-day average ({int(volume):,} vs {int(avg_vol_20):,})", 30))
            elif spike_ratio >= 2.5:
                flags.append(("ABNORMAL_VOLUME_SURGE", f"Large-cap volume is {spike_ratio:.1f}x 20-day average ({int(volume):,} vs {int(avg_vol_20):,})", 20))
        elif avg_vol_20 >= 50000:
            if spike_ratio >= 5.0:
                flags.append(("EXTREME_VOLUME_SPIKE", f"Mid-tier volume is {spike_ratio:.1f}x 20-day average ({int(volume):,} vs {int(avg_vol_20):,})", 30))
            elif spike_ratio >= 3.0:
                flags.append(("ABNORMAL_VOLUME_SURGE", f"Mid-tier volume is {spike_ratio:.1f}x 20-day average ({int(volume):,} vs {int(avg_vol_20):,})", 20))
        else:
            if spike_ratio >= 6.0 and volume >= 25000:
                flags.append(("EXTREME_VOLUME_SPIKE", f"Low-float spike is {spike_ratio:.1f}x 20-day average ({int(volume):,} vs {int(avg_vol_20):,})", 30))
            elif spike_ratio >= 4.0 and volume >= 20000:
                flags.append(("ABNORMAL_VOLUME_SURGE", f"Low-float surge is {spike_ratio:.1f}x 20-day average ({int(volume):,} vs {int(avg_vol_20):,})", 20))

        # 2. Speculative Junk Pump without Earnings (Distinguish tracked Negative EPS from Untracked)
        has_fund_record = ticker in fund_map
        if price_change_pct >= 4.0:
            if has_fund_record:
                if eps <= 0 or pe > 50 or category == "Z":
                    junk_reason = "Negative EPS" if eps <= 0 else (f"Extreme P/E ({pe:.1f}x)" if pe > 50 else "Z-Category Junk")
                    flags.append(("SPECULATIVE_JUNK_PUMP", f"Price up +{price_change_pct}% with poor fundamentals ({junk_reason})", 35))
            else:
                # Untracked instrument surging without fundamental disclosures
                if category == "Z" or price_change_pct >= 6.0:
                    flags.append(("SPECULATIVE_JUNK_PUMP", f"Price up +{price_change_pct}% on untracked / high-risk security without verified earnings", 35))

        # 3. Syndicate Low-Float Corner
        if sponsor_pct > 0 and sponsor_pct < 30.0 and price_change_pct >= 3.5 and spike_ratio >= 2.0:
            flags.append(("LOW_SPONSOR_SYNDICATE_CORNER", f"Promoters hold only {sponsor_pct:.1f}% (< 30% legal threshold) during price run-up", 25))

        # 3b. Extreme Low Free-Float Corner Trap (Public float < 10%)
        govt_pct = float(comp.get("govt_holding_pct") or 0.0)
        promoter_lock = sponsor_pct + govt_pct
        if promoter_lock >= 90.0 and price_change_pct >= 4.0 and spike_ratio >= 2.0:
            free_float = round(100.0 - promoter_lock, 1)
            flags.append(("EXTREME_LOW_FLOAT_CORNER", f"Public free float is only {free_float}% (< 10%) during abnormal price run-up", 25))

        # 4. Upper Circuit Breaker Clamping (Tiered BSEC limits)
        from dse_circuit_breaker import get_dse_circuit_limit_pct
        circuit_limit = get_dse_circuit_limit_pct(prev_close)
        if price_change_pct >= (circuit_limit - 0.4):
            # Check if previous day also had high gain
            prev_prev = float(hist_rows[1]["close"] or prev_close) if len(hist_rows) > 1 else prev_close
            prev_tier = get_dse_circuit_limit_pct(prev_prev)
            prev_chg = ((prev_close - prev_prev) / prev_prev) * 100.0 if prev_prev > 0 else 0.0
            if prev_chg >= (prev_tier - 0.5):
                flags.append(("CIRCUIT_BREAKER_CLAMP", f"Consecutive upper circuit limit locks (+{prev_chg:.1f}%, +{price_change_pct:.1f}%)", 40))

        # 5. Regulatory Probe & Disclosures
        if ticker in reg_flags:
            for rf in reg_flags[ticker]:
                desc_lower = str(rf.get("description") or "").lower()
                code = str(rf.get("flag_code") or "")
                if rf.get("risk_level") == "CRITICAL" or code == "QUALIFIED_AUDIT_OPINION" or code == "LOAN_DEFAULT":
                    flags.append(("REGULATORY_CRITICAL", f"Critical Auditor/Legal Risk: {rf['description']}", 50))
                elif code == "REGULATORY_PROBE" or "manipulat" in desc_lower or "fine" in desc_lower:
                    flags.append(("REGULATORY_PROBE", f"BSEC Regulatory Enforcement / Probe: {rf['description']}", 45))
                else:
                    flags.append(("REGULATORY_WARNING", f"Regulatory Disclosure: {rf['description']}", 25))

        if not flags:
            continue

        total_score = min(sum(f[2] for f in flags), 100)
        risk_level = "CRITICAL" if total_score >= 50 else ("HIGH" if total_score >= 35 else "MEDIUM")

        primary_alert = flags[0][0]
        desc = " | ".join(f[1] for f in flags)

        alert_item = {
            "ticker": ticker,
            "date": asof_date,
            "risk_level": risk_level,
            "alert_type": primary_alert,
            "risk_score": total_score,
            "volume_spike_ratio": spike_ratio,
            "price_change_pct": price_change_pct,
            "description": desc,
            "flags": [f[0] for f in flags],
            "details_json": json.dumps({"eps": eps, "pe": pe, "category": category, "sponsor_pct": sponsor_pct, "flags": flags})
        }

        alerts.append(alert_item)

        # Store in database
        try:
            conn.execute("""
                INSERT OR REPLACE INTO manipulation_alerts 
                (ticker, date, risk_level, alert_type, risk_score, volume_spike_ratio, price_change_pct, description, details_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ticker, asof_date, risk_level, primary_alert, total_score,
                spike_ratio, price_change_pct, desc, alert_item["details_json"]
            ))
        except Exception as e:
            print(f"⚠️ Failed to insert alert for {ticker}: {e}")

    conn.commit()
    conn.close()

    # Rank: CRITICAL first, highest score, highest volume spike
    alerts.sort(key=lambda x: (x["risk_level"] == "CRITICAL", x["risk_level"] == "HIGH", x["risk_score"], x["volume_spike_ratio"]), reverse=True)
    return alerts


def is_ticker_blacklisted(
    ticker: str,
    asof_date: str | None = None,
    lookback_days: int = 45
) -> tuple[bool, str]:
    """
    Direct Guard API: Returns (True, Reason) if ticker is flagged as CRITICAL or HIGH manipulation risk.
    Point-in-Time Aware: Takes optional asof_date to eliminate lookahead bias in historical evaluations.
    Decay Window: Flags decay after lookback_days (default 45 days) unless refreshed by surveillance.
    Fail-Closed Standard: Any database or query exception returns (True, Reason) to protect capital.
    """
    try:
        try:
            from scripts.db import get_db_connection
            conn = get_db_connection(DB_PATH, timeout=30.0, row_factory=sqlite3.Row)
        except Exception:
            conn = sqlite3.connect(DB_PATH, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout = 30000;")

        if not asof_date:
            row = conn.execute("SELECT MAX(date) FROM prices").fetchone()
            asof_date = row[0] if (row and row[0]) else datetime.date.today().isoformat()

        query = """
            SELECT risk_level, alert_type, description, date 
            FROM manipulation_alerts 
            WHERE ticker = ? 
              AND risk_level IN ('CRITICAL', 'HIGH')
              AND date <= ?
              AND date >= date(?, '-' || ? || ' days')
            ORDER BY date DESC LIMIT 1
        """
        row = conn.execute(query, (ticker, asof_date, asof_date, str(lookback_days))).fetchone()
        conn.close()

        if row:
            desc = row["description"] or ""
            return True, f"Blocked by Forensic Surveillance [{row['risk_level']}: {row['alert_type']} on {row['date']} — {desc}]"
        return False, "Clean"
    except Exception as e:
        # FAIL-CLOSED: In case of database error or surveillance failure, reject the ticker
        return True, f"Blocked by Forensic Surveillance [FAIL-CLOSED ERROR: {e}]"

def generate_surveillance_reports(asof_date: str | None = None) -> tuple[Path, Path]:
    """Generates comprehensive English and Bengali surveillance reports."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    alerts = run_surveillance_scan(asof_date)
    date_str = alerts[0]["date"] if alerts else (asof_date or datetime.date.today().isoformat())

    criticals = [a for a in alerts if a["risk_level"] == "CRITICAL"]
    highs = [a for a in alerts if a["risk_level"] == "HIGH"]
    mediums = [a for a in alerts if a["risk_level"] == "MEDIUM"]

    # 1. English Report
    en_lines = [
        f"# 🚨 DSE Market Surveillance & Forensic Anti-Manipulation Report",
        f"**Market Date**: `{date_str}` | **Generated**: `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        f"**Surveillance Scope**: Full 395 Tickers | Volume Anomaly, Syndicate Corners, Speculative Pumps\n",
        f"### 🛡️ Executive Summary",
        f"- **Critical Risk Alerts (Instant Blacklist)**: **{len(criticals)} Companies**",
        f"- **High Forensic Alerts (Strict Retail Caution)**: **{len(highs)} Companies**",
        f"- **Medium Surveillance Flags**: **{len(mediums)} Companies**\n",
        "---",
        "## ⛔ 1. Critical Blacklist (DO NOT BUY — Capital Destruction Risk)",
        "| Ticker | Risk Score | Alert Type | Volume Spike | Price Move | Forensic Evidence |",
        "|---|---|---|---|---|---|"
    ]
    for a in criticals:
        en_lines.append(
            f"| **{a['ticker']}** | `{a['risk_score']}/100` | **{a['alert_type']}** | "
            f"**{a['volume_spike_ratio']:.1f}x** | {a['price_change_pct']:+.1f}% | {a['description']} |"
        )
    if not criticals:
        en_lines.append("> No tickers triggered critical blacklist thresholds today.\n")

    en_lines.extend([
        "\n---",
        "## ⚠️ 2. High Forensic Alerts (Suspected Syndicate Activity)",
        "| Ticker | Risk Score | Alert Type | Volume Spike | Price Move | Forensic Evidence |",
        "|---|---|---|---|---|---|"
    ])
    for a in highs[:15]:
        en_lines.append(
            f"| **{a['ticker']}** | `{a['risk_score']}/100` | **{a['alert_type']}** | "
            f"**{a['volume_spike_ratio']:.1f}x** | {a['price_change_pct']:+.1f}% | {a['description']} |"
        )

    en_lines.extend([
        "\n---",
        "## 🔬 Forensic Methodology & Safeguard Rules",
        "1. **Volume Anomaly Ratio (VAR)**: Daily volume >= 3.0x 20-day SMA without material news indicates synthetic retail crowding.",
        "2. **Speculative Junk Filter**: Price moves > 4.0% on negative earnings or Z-category classification indicate syndicate pump-and-dump.",
        "3. **Sponsor Skin-in-the-game**: Promoters holding < 30% are legally vulnerable to hostile syndicates and sudden dump exits.",
        "4. **Circuit Breaker Lock**: Multiple consecutive upper circuit limits indicate supply cornering.",
        "\n> Published by DSE Quantitative Forensic Surveillance Engine."
    ])

    en_path = REPORTS_DIR / f"{date_str}_manipulation_alerts.md"
    with open(en_path, "w", encoding="utf-8") as f:
        f.write("\n".join(en_lines))

    # 2. Bengali Report
    bn_lines = [
        f"# 🚨 DSE মার্কেট সার্ভেইল্যান্স ও অ্যান্টি-ম্যানিপুলেশন সতর্কবার্তা রিপোর্ট",
        f"**বাজার তারিখ**: `{date_str}` | **তৈরির সময়**: `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        f"**নজরদারির আওতা**: ৩৯৫টি পূর্ণ স্টক ইউনিভার্স | ভলিউম স্পাইক অ্যানোমালি, সিন্ডিকেট কর্নার ও পাম্প-অ্যান্ড-ডাম্প নজরদারি\n",
        f"### 🛡️ নজরদারি সারসংক্ষেপ",
        f"- **সংকটজনক ঝুঁকি (তাত্ক্ষণিক ব্ল্যাকলিস্ট - ভুলেও কিনবেন না)**: **{len(criticals)}টি কোম্পানি**",
        f"- **উচ্চ ফরেনসিক সতর্কতা (সিন্ডিকেট তৎপরতা সন্দেহ)**: **{len(highs)}টি কোম্পানি**",
        f"- **মাঝারি নজরদারি ফ্ল্যাগ**: **{len(mediums)}টি কোম্পানি**\n",
        "---",
        "## ⛔ ১. সংকটজনক ব্ল্যাকলিস্ট (DO NOT BUY — মূলধন ক্ষয়ের সর্বোচ্চ ঝুঁকি)",
        "| Ticker | ঝুঁকি স্কোর | সতর্কতার ধরন | ভলিউম স্পাইক | দর পরিবর্তন | ফরেনসিক প্রমাণাদি |",
        "|---|---|---|---|---|---|"
    ]
    for a in criticals:
        bn_lines.append(
            f"| **{a['ticker']}** | `{a['risk_score']}/১০০` | **{a['alert_type']}** | "
            f"**{a['volume_spike_ratio']:.1f}x** | {a['price_change_pct']:+.1f}% | {a['description']} |"
        )
    if not criticals:
        bn_lines.append("> আজ কোনো স্টকে সংকটজনক ব্ল্যাকলিস্টের শর্ত প্রযোজ্য হয়নি।\n")

    bn_lines.extend([
        "\n---",
        "## ⚠️ ২. উচ্চ ফরেনসিক সতর্কতা (সিন্ডিকেট কৃত্রিম পাম্প সন্দেহ)",
        "| Ticker | ঝুঁকি স্কোর | সতর্কতার ধরন | ভলিউম স্পাইক | দর পরিবর্তন | ফরেনসিক প্রমাণাদি |",
        "|---|---|---|---|---|---|"
    ])
    for a in highs[:15]:
        bn_lines.append(
            f"| **{a['ticker']}** | `{a['risk_score']}/১০০` | **{a['alert_type']}** | "
            f"**{a['volume_spike_ratio']:.1f}x** | {a['price_change_pct']:+.1f}% | {a['description']} |"
        )

    bn_lines.extend([
        "\n---",
        "## 🔬 ফরেনসিক নজরদারির ৪টি মূলনীতি",
        "১. **ভলিউম অ্যানোমালি রেশিও (VAR)**: কোনো সংবাদ ছাড়াই ২০ দিনের গড়ের চেয়ে ৩ গুণের বেশি ভলিউম বৃদ্ধি কৃত্রিম পাম্পের লক্ষণ।",
        "২. **জাঙ্ক ও লোকসানি স্টক ফিল্টার**: নেতিবাচক ইপিএস বা 'Z' ক্যাটাগরির স্টকে হঠাৎ দরবৃদ্ধি খাঁটি সিন্ডিকেট জুয়া।",
        "৩. **স্পন্সর হোল্ডিং গার্ড**: যেসব কোম্পানিতে স্পন্সরদের মালিকানা ৩০%-এর কম, সেখানে সিন্ডিকেট সহজে শেয়ার কুক্ষিগত করে সাধারণ বিনিয়োগকারীদের ফাঁসায়।",
        "৪. **সার্কিট ব্রেকার লক**: টানা কয়েকদিন আপার সার্কিটে কৃত্রিম বায়ার রেখে সাপ্লাই আটকে রাখা কারসাজির প্রধান কৌশল।",
        "\n> DSE কোয়ান্টেটিভ ফরেনসিক সার্ভেইল্যান্স ইঞ্জিন দ্বারা প্রস্তুতকৃত।"
    ])

    bn_path = REPORTS_DIR / f"{date_str}_manipulation_alerts_bn.md"
    with open(bn_path, "w", encoding="utf-8") as f:
        f.write("\n".join(bn_lines))

    return en_path, bn_path


def main():
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    alerts = run_surveillance_scan(date_arg)
    print("=" * 80)
    print(f"🚨 DSE FORENSIC ANTI-MANIPULATION SURVEILLANCE DASHBOARD")
    print("=" * 80)
    print(f"Total Tickers Scanned: 395 | Active Alerts Triggered: {len(alerts)}")
    crit_count = len([a for a in alerts if a["risk_level"] == "CRITICAL"])
    high_count = len([a for a in alerts if a["risk_level"] == "HIGH"])
    print(f"Critical Blacklist (DO NOT BUY): {crit_count} | High Risk Alerts: {high_count}")
    print("-" * 80)
    for a in alerts[:12]:
        print(f"  [{a['risk_level']:<8}] {a['ticker']:<12} Score: {a['risk_score']:<3} VolSpike: {a['volume_spike_ratio']:>4.1f}x | {a['alert_type']:<26} | {a['description'][:45]}...")
    print("-" * 80)
    en_p, bn_p = generate_surveillance_reports(date_arg)
    print(f"[Reports Published: {en_p.name} & {bn_p.name}]")
    print("=" * 80)


if __name__ == "__main__":
    main()
