"""
DSE Macro Sentiment & Crisis Impact Engine

Analyzes market-wide and sector-specific news headlines and disclosures across 4 dimensions:
  1. Political (unrest, stability, policy continuity, elections, protests)
  2. Macroeconomic (interest rates, SMART, inflation, FX reserves, dollar/LC crunch)
  3. Regulatory (BSEC floor price, circuit breakers, margin loans, spot investigations)
  4. Sector Crises & Catalysts (gas shortage, power tariff, clinker duty, bank NPLs)

Calculates:
  - Systemic Market Bias score (-100 to +100)
  - Sector Risk Adjustments (e.g. Gas Shortage -> Textile/Ceramic penalty)
  - Ticker-Specific Catalyst / Risk flags
"""

import json
import logging
import sqlite3
import datetime
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent
PROC_DIR   = BASE_DIR / "data" / "processed"
CONFIG_DIR = BASE_DIR / "config"
DB_PATH    = PROC_DIR / "dse.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("macro_sentiment_engine")

# ── Macro & Sector Impact Lexicon ─────────────────────────────────────────────

MACRO_TAXONOMY = {
    "political": {
        "negative": [
            "unrest", "strike", "hartal", "blockade", "clash", "protest",
            "instability", "violence", "curfew", "boycott", "sanction"
        ],
        "positive": [
            "stability", "peaceful", "continuity", "transition complete",
            "accord", "reform accepted", "bilateral agreement"
        ],
        "weight": 1.2
    },
    "macroeconomic": {
        "negative": [
            "dollar crisis", "lc opening", "lc restriction", "fx reserve decline",
            "inflation rise", "interest rate hike", "repo rate increase",
            "liquidity crunch", "credit squeeze", "imf condition", "devaluation"
        ],
        "positive": [
            "remittance surge", "reserve increase", "inflation eases",
            "interest rate cut", "liquidity surplus", "export growth",
            "foreign aid", "fdi inflow", "imf loan released"
        ],
        "weight": 1.5
    },
    "regulatory": {
        "negative": [
            "probe", "investigation", "penalty", "fine", "fraud", "bsec action",
            "trading halt", "circuit breaker cut", "floor price imposed",
            "demoted to z", "sponsor breach", "unauthorized trade", "spot inspection"
        ],
        "positive": [
            "bsec approved", "restoring confidence", "market reform",
            "floor price lifted", "margin loan relaxed", "surveillance upgrade",
            "category upgrade", "governance reward"
        ],
        "weight": 1.3
    },
    "sector_crises": {
        "Textile": {
            "negative": ["gas shortage", "yarn price", "rmg export decline", "worker unrest", "power disruption"],
            "positive": ["eu duty-free", "order surge", "cotton price drop", "apparel growth"]
        },
        "Banking": {
            "negative": ["npl rise", "default loan", "provision shortfall", "merger crisis", "bad debt", "scam"],
            "positive": ["loan recovery", "car compliant", "nim expansion", "record profit", "dividend approved"]
        },
        "Pharmaceuticals": {
            "negative": ["raw material import cost", "trips waiver expiry", "price cap", "counterfeit probe"],
            "positive": ["fda approval", "who prequalification", "export expansion", "new patent", "api production"]
        },
        "Cement": {
            "negative": ["clinker import cost", "freight surge", "construction slowdown", "infrastructure budget cut"],
            "positive": ["mega project demand", "volume growth", "clinker tariff cut"]
        },
        "Fuel_Power": {
            "negative": ["unpaid subsidy", "fuel price hike", "gas crisis", "capacity charge cut", "power outage"],
            "positive": ["ppa extension", "tariff revision", "lng import boost", "subsidies cleared"]
        },
        "Engineering": {
            "negative": ["scrap iron cost", "dollar crunch", "steel demand drop", "import hurdle"],
            "positive": ["infrastructure boom", "rebar demand", "order book strong"]
        },
        "Food_Beverage": {
            "negative": ["raw material inflation", "sugar import duty", "tax hike", "smuggling"],
            "positive": ["consumption surge", "festive sales", "margin expansion"]
        }
    }
}


def get_db():
    return sqlite3.connect(DB_PATH)


def load_news(days: int = 14) -> list[dict]:
    conn = get_db()
    since = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    rows = conn.execute(
        "SELECT ticker, date, headline, source FROM news WHERE date >= ? ORDER BY date DESC",
        (since,)
    ).fetchall()
    conn.close()
    return [{"ticker": r[0], "date": r[1], "headline": r[2], "source": r[3]} for r in rows]


def is_bangladesh_or_macro_relevant(headline: str) -> bool:
    """
    Filters news strictly for:
      1. Bangladesh domestic economic, financial, regulatory, and systemic governance news.
      2. Globally impactful macro events: wars, crude oil/LNG, shipping freight (Red Sea),
         global interest rates (US Fed), commodity prices (clinker, cotton, scrap, sugar),
         and multilateral agencies (IMF, World Bank, ADB).
      3. Rejects foreign domestic municipal/political noise (e.g. protests in Delhi/Mumbai).
    """
    h = headline.lower()

    # Foreign domestic noise patterns (reject unless explicitly linked to BD or cross-border trade)
    foreign_domestic_noise = [
        "delhi", "mumbai", "modi govt", "karnataka", "punjab", "bjp",
        "congress party", "lok sabha", "kolkata police", "islamabad local"
    ]
    if any(w in h for w in foreign_domestic_noise):
        if not any(k in h for k in ["bangladesh", "dhaka", "export", "import", "trade", "border", "transit", "gas", "power"]):
            return False

    # Check for direct relevance
    relevant_terms = [
        # Domestic
        "bangladesh", "dhaka", "chattogram", "ctg", "dse", "bsec", "bangladesh bank",
        "nbr", "taka", "bdt", "port", "garment", "textile", "pharma", "bank",
        "inflation", "reserve", "power", "gas", "plc", "ltd", "interim govt", "adviser",
        # International Macro & Crisis Impact
        "crude oil", "brent", "fuel price", "lng", "shipping", "freight", "red sea",
        "suez", "middle east war", "russia", "ukraine", "imf", "world bank", "adb",
        "us fed", "interest rate", "dollar index", "remittance", "rmg export", "tariff",
        "cotton", "clinker", "scrap iron", "fertilizer", "fdi"
    ]
    return any(k in h for k in relevant_terms)


def analyze_macro_sentiment(days: int = 14) -> dict:
    """
    Evaluates news across Political, Macroeconomic, Regulatory, and Sector-specific vectors.
    Filters out irrelevant foreign domestic news.
    """
    raw_news = load_news(days=days)
    news_items = [n for n in raw_news if is_bangladesh_or_macro_relevant(n["headline"])]

    if not news_items:
        return {
            "systemic_market_bias": 0,
            "bias_label": "Neutral / No Recent News",
            "macro_alerts": [],
            "sector_adjustments": {},
            "ticker_news_catalysts": {}
        }

    political_score = 0
    macro_score = 0
    regulatory_score = 0
    sector_scores = {sec: 0 for sec in MACRO_TAXONOMY["sector_crises"]}
    alerts = []
    ticker_catalysts = {}

    for item in news_items:
        text = item["headline"].lower()
        ticker = item.get("ticker", "")

        # 1. Political check
        for kw in MACRO_TAXONOMY["political"]["negative"]:
            if kw in text:
                political_score -= 15
                alerts.append(f"POLITICAL RISK: '{item['headline']}' ({item['source']})")
        for kw in MACRO_TAXONOMY["political"]["positive"]:
            if kw in text:
                political_score += 10

        # 2. Macroeconomic check
        for kw in MACRO_TAXONOMY["macroeconomic"]["negative"]:
            if kw in text:
                macro_score -= 20
                alerts.append(f"MACRO HEADWIND: '{item['headline']}' ({item['source']})")
        for kw in MACRO_TAXONOMY["macroeconomic"]["positive"]:
            if kw in text:
                macro_score += 15

        # 3. Regulatory check
        for kw in MACRO_TAXONOMY["regulatory"]["negative"]:
            if kw in text:
                regulatory_score -= 15
                alerts.append(f"REGULATORY SURVEILLANCE: '{item['headline']}' ({item['source']})")
        for kw in MACRO_TAXONOMY["regulatory"]["positive"]:
            if kw in text:
                regulatory_score += 12

        # 4. Sector crisis check
        for sector, kw_dict in MACRO_TAXONOMY["sector_crises"].items():
            for kw in kw_dict["negative"]:
                if kw in text:
                    sector_scores[sector] -= 10
                    alerts.append(f"{sector.upper()} CRISIS: '{item['headline']}'")
            for kw in kw_dict["positive"]:
                if kw in text:
                    sector_scores[sector] += 10

        # 5. Ticker catalyst
        if ticker:
            if ticker not in ticker_catalysts:
                ticker_catalysts[ticker] = []
            ticker_catalysts[ticker].append(item["headline"])

    # Aggregate weighted market bias
    raw_bias = (
        political_score * MACRO_TAXONOMY["political"]["weight"] +
        macro_score * MACRO_TAXONOMY["macroeconomic"]["weight"] +
        regulatory_score * MACRO_TAXONOMY["regulatory"]["weight"]
    )
    # Normalize between -100 and +100
    norm_bias = max(-100, min(100, round(raw_bias, 1)))

    if norm_bias >= 25:
        label = "Bullish Macro Climate"
    elif norm_bias <= -25:
        label = "High Macro/Crisis Caution"
    else:
        label = "Neutral / Mixed Climate"

    # Clamp sector adjustments between -25 and +25
    clamped_sectors = {k: max(-25, min(25, v)) for k, v in sector_scores.items()}

    return {
        "systemic_market_bias": norm_bias,
        "bias_label": label,
        "total_news_analyzed": len(news_items),
        "macro_alerts": list(dict.fromkeys(alerts))[:10],  # dedupe top 10
        "sector_adjustments": clamped_sectors,
        "ticker_news_catalysts": ticker_catalysts
    }


if __name__ == "__main__":
    report = analyze_macro_sentiment()
    print("=== DSE MACRO SENTIMENT REPORT ===")
    print("Market Bias Score:", report["systemic_market_bias"], f"({report['bias_label']})")
    print("Sector Adjustments:", json.dumps(report["sector_adjustments"], indent=2))
    print("Top Alerts:", len(report["macro_alerts"]))
    for a in report["macro_alerts"][:5]:
        print("  *", a)
