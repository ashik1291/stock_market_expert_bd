"""
DSE & Bangladesh Bank Macro Rates Feed and Dynamic Hurdle Rate Engine.

Ingests and tracks critical central bank macro interest rates:
  - Policy Repo Rate (Bangladesh Bank monetary stance)
  - 91-day, 182-day, 364-day Treasury Bill Yields (Primary risk-free benchmark)
  - Interbank Call Money Rate (Market liquidity strain)
  - General CPI Inflation (Real purchasing power benchmark)
  - Gross Foreign Exchange Reserves (BPM6 standard)

Features:
  - Automated Live Web Scraper with Fallback Resilience (Bangladesh Bank & Economic Media)
  - Dynamic Hurdle Rates & Equity Risk Premium (ERP):
      * Risk-Free Benchmark: 91-Day Treasury Bill Auction Yield (Rf)
      * Earnings Yield: EPS / Price * 100%
      * Equity Risk Premium (ERP): Earnings Yield - Rf
      * Macro Hurdle Verdict: PRIME_SPREAD (ERP >= +5%), COMPETITIVE, UNCOMPETITIVE
"""

from __future__ import annotations

import sys
import re
import json
import sqlite3
import argparse
import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"

MACRO_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS macro_indicators (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,
    indicator   TEXT NOT NULL,
    value       REAL NOT NULL,
    unit        TEXT NOT NULL,
    source      TEXT NOT NULL,
    notes       TEXT,
    created_at  TEXT NOT NULL,
    UNIQUE(date, indicator)
);
CREATE INDEX IF NOT EXISTS idx_macro_date ON macro_indicators(date, indicator);
"""

# Benchmark Macro Reality for Bangladesh Economy (Q4 2026 / FY2026-27 Tight Stance)
CURRENT_MACRO_BENCHMARKS = [
    {
        "indicator": "policy_repo_rate",
        "value": 10.00,
        "unit": "percent",
        "source": "Bangladesh Bank Monetary Policy Statement",
        "notes": "Policy interest rate tightened to curb inflationary pressure"
    },
    {
        "indicator": "t_bill_91d",
        "value": 11.60,
        "unit": "percent",
        "source": "Bangladesh Bank Primary Treasury Auction Cut-off Yield",
        "notes": "Verified risk-free auction cut-off yield as of October 2026"
    },
    {
        "indicator": "t_bill_182d",
        "value": 11.85,
        "unit": "percent",
        "source": "Bangladesh Bank Primary Treasury Auction",
        "notes": "Medium-tenor government sovereign yield"
    },
    {
        "indicator": "t_bill_364d",
        "value": 12.00,
        "unit": "percent",
        "source": "Bangladesh Bank Primary Treasury Auction",
        "notes": "1-year benchmark government paper yield"
    },
    {
        "indicator": "call_money_rate",
        "value": 9.75,
        "unit": "percent",
        "source": "Bangladesh Bank Interbank Money Market",
        "notes": "Weighted average interbank overnight call money rate"
    },
    {
        "indicator": "cpi_inflation",
        "value": 9.92,
        "unit": "percent",
        "source": "Bangladesh Bureau of Statistics (BBS)",
        "notes": "General headline Consumer Price Index YoY"
    },
    {
        "indicator": "fx_reserves_usd_bn",
        "value": 19.82,
        "unit": "billion_usd",
        "source": "Bangladesh Bank BPM6 Gross Reserves",
        "notes": "Gross official foreign exchange reserves under IMF BPM6 definition"
    },
    {
        "indicator": "private_credit_growth_pct",
        "value": 9.85,
        "unit": "percent",
        "source": "Bangladesh Bank Scheduled Commercial Banks Report",
        "notes": "Annual private sector credit growth rate"
    }
]


def init_macro_schema(conn: sqlite3.Connection) -> None:
    """Ensures macro_indicators table and indexes exist."""
    conn.executescript(MACRO_SCHEMA_DDL)
    conn.commit()


BB_BASE = "https://www.bb.org.bd/en/index.php/monetaryactivity/"
BB_SERIES = {
    "bcr_91d": ("bcr_rate", "91 Days BCR: Bangladesh Bank's compounded reference rate from the 91-day T-bill cut-off yield"),
    "dommr_overnight": ("money_market_ref_rate", "Dhaka Overnight Money Market Rate (DOMMR), overnight tenor"),
}


def scrape_live_bangladesh_bank_rates() -> list[tuple[str, str, float, str]]:
    """(indicator, observation_date, value_pct, source_url) rows exactly as Bangladesh Bank publishes them."""
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    headers = {"User-Agent": "Mozilla/5.0 (academic research client)"}
    out = []
    for indicator, (page, _) in BB_SERIES.items():
        url = BB_BASE + page
        try:
            html = requests.get(url, headers=headers, timeout=60, verify=False).text  # nosec B501
        except Exception:
            continue
        if indicator == "bcr_91d":
            rows = re.findall(r'<div class="column">\s*\d+\s*</div>\s*<div class="column">\s*([^<]+?)\s*</div>\s*'
                              r'<div class="column">\s*([\d.]+)%', html)
        else:
            rows, section, day = [], None, None
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
                cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c)).strip()
                         for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
                if any("DOMMR" in c for c in cells):
                    section = "DOMMR"
                elif any(re.fullmatch(r"[A-Z]{3,6} \(%\)", c) for c in cells):
                    section = None
                elif len(cells) == 1 and re.fullmatch(r"\d{1,2} [A-Za-z]+, \d{4}", cells[0]):
                    day = cells[0]
                elif section == "DOMMR" and day and cells and cells[0] == "Overnight" and len(cells) >= 3:
                    rows.append((day, cells[2]))
        for d, v in rows:
            try:
                iso = datetime.datetime.strptime(d.strip(), "%d %B, %Y").date().isoformat()
            except ValueError:
                continue
            out.append((indicator, iso, float(v), url))
    return out


def sync_macro_indicators(
    asof_date: Optional[str] = None,
    live_scrape: bool = True
) -> dict:
    """Store Bangladesh Bank's published rates at their own publication dates. Nothing else is written."""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    init_macro_schema(conn)
    now_utc = datetime.datetime.utcnow().isoformat()
    rows = scrape_live_bangladesh_bank_rates() if live_scrape else []
    if not rows:
        print("[MACRO SCRAPER] Bangladesh Bank pages returned no rates; nothing written.")
    for indicator, d, val, url in rows:
        conn.execute("""
            INSERT INTO macro_indicators (date, indicator, value, unit, source, notes, created_at)
            VALUES (?, ?, ?, 'percent', ?, ?, ?)
            ON CONFLICT(date, indicator) DO UPDATE SET value = excluded.value, source = excluded.source,
                notes = excluded.notes
        """, (d, indicator, val, f"Bangladesh Bank {url}", BB_SERIES[indicator][1], now_utc))
    conn.commit()
    conn.close()
    return {"ok": True, "records_synced": len(rows), "live_scraped": bool(rows),
            "latest": {i: max((r[1] for r in rows if r[0] == i), default=None) for i in BB_SERIES}}


def update_macro_indicator(
    indicator: str,
    value: float,
    asof_date: Optional[str] = None,
    unit: str = "percent",
    source: str = "Manual/CLI Operator Update",
    notes: str = ""
) -> dict:
    """
    Allows exact manual or webhook update of a single macro indicator (e.g. after weekly auction).
    """
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    init_macro_schema(conn)

    if not asof_date:
        row = conn.execute("SELECT MAX(date) FROM prices").fetchone()
        asof_date = row[0] if (row and row[0]) else datetime.date.today().isoformat()

    now_utc = datetime.datetime.utcnow().isoformat()
    conn.execute("""
        INSERT INTO macro_indicators (date, indicator, value, unit, source, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date, indicator) DO UPDATE SET
            value = excluded.value,
            unit = excluded.unit,
            source = excluded.source,
            notes = excluded.notes,
            created_at = excluded.created_at
    """, (asof_date, indicator, float(value), unit, source, notes, now_utc))

    conn.commit()
    conn.close()
    return {"ok": True, "indicator": indicator, "value": value, "date": asof_date}


POLICY_DEFAULTS = {"t_bill_91d": 11.60, "policy_repo_rate": 10.00, "cpi_inflation": 9.92, "call_money_rate": 9.75,
                   "fx_reserves_usd_bn": 19.82}
STALE_AFTER_DAYS = 45
RISK_FREE_SERIES = ("t_bill_91d", "bcr_91d")


def _observations_asof(conn: sqlite3.Connection, asof_date: str) -> dict:
    """{indicator: (value, observation_date)} — each indicator's own latest observation on or before asof_date."""
    rows = conn.execute("""
        SELECT m.indicator, m.value, m.date FROM macro_indicators m
        JOIN (SELECT indicator, MAX(date) AS d FROM macro_indicators WHERE date <= ? GROUP BY indicator) last
          ON last.indicator = m.indicator AND last.d = m.date
    """, (asof_date,)).fetchall()
    return {r[0]: (float(r[1]), r[2]) for r in rows}


def get_macro_rates_for_date(asof_date: str, conn: Optional[sqlite3.Connection] = None) -> dict:
    """
    Point-in-time macro rates: each indicator's latest observation on or before asof_date (never a later one).
    An indicator with no observation falls back to its policy default and is reported as such.
    """
    should_close = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        conn.execute("PRAGMA busy_timeout = 30000;")
        should_close = True
    init_macro_schema(conn)
    obs = _observations_asof(conn, asof_date)
    if should_close:
        conn.close()

    def val(ind):
        return obs[ind][0] if ind in obs else POLICY_DEFAULTS.get(ind)

    # Risk-free rate follows Bangladesh Bank: the freshest 91-day observation (T-bill cut-off yield or 91-day BCR).
    rf_series = max((i for i in RISK_FREE_SERIES if i in obs), key=lambda i: obs[i][1], default=None)
    rf_rate = obs[rf_series][0] if rf_series else POLICY_DEFAULTS["t_bill_91d"]
    rf_date = obs[rf_series][1] if rf_series else None
    inflation = val("cpi_inflation")
    min_equity_risk_premium = 3.50
    try:
        staleness_days = (datetime.date.fromisoformat(asof_date[:10]) - datetime.date.fromisoformat(rf_date)).days if rf_date else None
    except ValueError:
        staleness_days = None
    return {
        "as_of_date": max((d for _, d in obs.values()), default=asof_date),
        "risk_free_rate_pct": rf_rate,
        "risk_free_source": f"{rf_series} observed {rf_date}" if rf_date else "policy default (no observation)",
        "staleness_days": staleness_days,
        "is_stale": staleness_days is None or staleness_days > STALE_AFTER_DAYS,
        "t_bill_91d_pct": val("t_bill_91d"),
        "t_bill_182d_pct": val("t_bill_182d") or round(rf_rate + 0.25, 2),
        "t_bill_364d_pct": val("t_bill_364d") or round(rf_rate + 0.40, 2),
        "bcr_91d_pct": obs["bcr_91d"][0] if "bcr_91d" in obs else None,
        "bcr_91d_observed": obs["bcr_91d"][1] if "bcr_91d" in obs else None,
        "dommr_overnight_pct": obs["dommr_overnight"][0] if "dommr_overnight" in obs else None,
        "policy_repo_rate_pct": val("policy_repo_rate"),
        "cpi_inflation_pct": inflation,
        "real_interest_rate_pct": round(rf_rate - inflation, 2),
        "call_money_rate_pct": val("call_money_rate"),
        "min_equity_risk_premium_pct": min_equity_risk_premium,
        "equity_hurdle_rate_pct": round(rf_rate + min_equity_risk_premium, 2),
        "fx_reserves_usd_bn": val("fx_reserves_usd_bn"),
    }


def get_latest_macro_rates(conn: Optional[sqlite3.Connection] = None) -> dict:
    """Macro rates as of today (each indicator's latest observation)."""
    return get_macro_rates_for_date(datetime.date.today().isoformat(), conn=conn)


def calculate_equity_risk_premium(
    eps: float,
    price: float,
    rf_rate: Optional[float] = None
) -> dict:
    """
    Calculates Earnings Yield, Equity Risk Premium (ERP), and Macro Hurdle Verdict.
    """
    if rf_rate is None:
        rates = get_latest_macro_rates()
        rf_rate = rates["risk_free_rate_pct"]

    if price <= 0 or eps <= 0:
        return {
            "earnings_yield_pct": 0.0,
            "risk_free_rate_pct": rf_rate,
            "equity_risk_premium_pct": round(-rf_rate, 2),
            "passes_macro_hurdle": False,
            "verdict": "UNCOMPETITIVE (Negative Earnings Yield)"
        }

    earnings_yield = round((eps / price) * 100.0, 2)
    erp = round(earnings_yield - rf_rate, 2)

    MIN_EQUITY_RISK_PREMIUM_PCT = 3.50

    if erp >= 5.0:
        verdict = f"PRIME_MACRO_SPREAD (+{erp:.1f}% above T-Bills)"
        passes = True
    elif erp >= MIN_EQUITY_RISK_PREMIUM_PCT:
        verdict = f"COMPETITIVE (+{erp:.1f}% above T-Bills — Meets Hurdle)"
        passes = True
    elif erp >= 0.0:
        verdict = f"SUB_PAR_SPREAD (+{erp:.1f}% above T-Bills — Fails Minimum 3.5% Equity Risk Premium)"
        passes = False
    else:
        verdict = f"UNCOMPETITIVE ({erp:.1f}% below T-Bills — Risk Uncompensated)"
        passes = False

    return {
        "earnings_yield_pct": earnings_yield,
        "risk_free_rate_pct": rf_rate,
        "equity_risk_premium_pct": erp,
        "passes_macro_hurdle": passes,
        "verdict": verdict
    }


def macro_hurdle_ok(earnings_yield: float, risk_free_rate: float | None = None) -> tuple[bool, float]:
    """
    Central macro hurdle validation enforcing SPEC.md INV-2:
    earnings_yield >= observed Bangladesh Bank 91-day risk-free rate + 3.50% ERP
    """
    if earnings_yield <= 0:
        return False, 0.0
    if risk_free_rate is None:
        rf = float(get_latest_macro_rates()["risk_free_rate_pct"])
    else:
        rf = float(risk_free_rate)
    erp = round(earnings_yield - rf, 2)
    return (erp >= 3.50, erp)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bangladesh Bank Macro Rates Feed & Scraper")
    parser.add_argument("--sync", action="store_true", help="Sync latest macro rates with live scraper")
    parser.add_argument("--update", nargs=3, metavar=("INDICATOR", "VALUE", "DATE"),
                        help="Record an observed value with its observation date (e.g. --update t_bill_91d 8.84 2026-11-18)")
    args = parser.parse_args()

    if args.update:
        ind, val, obs_date = args.update[0], float(args.update[1]), args.update[2]
        datetime.date.fromisoformat(obs_date)
        res = update_macro_indicator(ind, val, asof_date=obs_date)
        print(f"[MACRO FEED] Updated: {res}")
    else:
        res = sync_macro_indicators(live_scrape=True)
        print(f"[MACRO FEED] Ingestion: {res}")

    rates = get_latest_macro_rates()
    print("\n" + "=" * 80)
    print(f"🏦 BANGLADESH BANK MACRO RATES DASHBOARD — As of {rates['as_of_date']}")
    print("=" * 80)
    print(f"  * Risk-Free 91-Day T-Bill:     {rates['risk_free_rate_pct']:.2f}%")
    print(f"  * 364-Day T-Bill Yield:        {rates['t_bill_364d_pct']:.2f}%")
    print(f"  * Policy Repo Rate:            {rates['policy_repo_rate_pct']:.2f}%")
    print(f"  * General CPI Inflation:       {rates['cpi_inflation_pct']:.2f}%")
    print(f"  * Real Interest Rate:          {rates['real_interest_rate_pct']:+.2f}%")
    print(f"  * Interbank Call Money Rate:   {rates['call_money_rate_pct']:.2f}%")
    print(f"  * Minimum Equity Hurdle Rate:  {rates['equity_hurdle_rate_pct']:.2f}% (T-Bill + 3.5% ERP)")
    print("=" * 80)

    # Test cases:
    # 1. JAMUNAOIL: Price 179.4, EPS 58.7
    jamuna_erp = calculate_equity_risk_premium(58.7, 179.4, rates["risk_free_rate_pct"])
    print(f"\n📊 JAMUNAOIL Macro Hurdle: Earnings Yield {jamuna_erp['earnings_yield_pct']}% | ERP: {jamuna_erp['equity_risk_premium_pct']:+}% | {jamuna_erp['verdict']}")

    # 2. High PE Stock: Price 200.0, EPS 8.0 (PE 25.0)
    pe25_erp = calculate_equity_risk_premium(8.0, 200.0, rates["risk_free_rate_pct"])
    print(f"📊 PE 25.0 Stock Macro Hurdle: Earnings Yield {pe25_erp['earnings_yield_pct']}% | ERP: {pe25_erp['equity_risk_premium_pct']:+}% | {pe25_erp['verdict']}")
