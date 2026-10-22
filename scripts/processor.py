"""
DSE Processor — cleans raw scraped data, computes derived metrics, writes to SQLite DB.
DB: data/processed/dse.db

Fixes applied:
  - Key normalization includes '/' → '_' to match DSE field names like 'p/e', 'd/e'
  - News table has UNIQUE(ticker, date, headline) to prevent duplicates
  - Fundamentals get fiscal year/quarter from raw data when available, not just today
  - get_ticker_data accepts days param passed by analyzer
  - category stored from scraped data, not hardcoded 'A'
"""

import json
import logging
import sqlite3
import datetime
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent
RAW_DIR    = BASE_DIR / "data" / "raw"
PROC_DIR   = BASE_DIR / "data" / "processed"
CONFIG_DIR = BASE_DIR / "config"
DB_PATH    = PROC_DIR / "dse.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dse_processor")


# ── DB Setup ──────────────────────────────────────────────────────────────────

DDL = """
CREATE TABLE IF NOT EXISTS companies (
    ticker              TEXT PRIMARY KEY,
    name                TEXT,
    sector              TEXT,
    category            TEXT,
    market_cap_cr       REAL,
    sponsor_holding_pct REAL,
    govt_holding_pct    REAL,
    institutional_pct   REAL,
    public_holding_pct  REAL,
    free_float_pct      REAL,
    updated_at          TEXT
);

CREATE TABLE IF NOT EXISTS prices (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT NOT NULL,
    date        TEXT NOT NULL,
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    volume      INTEGER,
    value       REAL,
    change      REAL,
    change_pct  REAL,
    UNIQUE(ticker, date)
);

CREATE TABLE IF NOT EXISTS fundamentals (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker         TEXT NOT NULL,
    year           INTEGER,
    quarter        INTEGER,
    eps            REAL,
    nav            REAL,
    pe_ratio       REAL,
    debt_equity    REAL,
    dividend_yield REAL,
    roe            REAL,
    roa            REAL,
    current_ratio  REAL,
    revenue_cr     REAL,
    net_profit_cr  REAL,
    cash_flow_ops  REAL,
    raw_data       TEXT,
    updated_at     TEXT,
    UNIQUE(ticker, year, quarter)
);

CREATE TABLE IF NOT EXISTS news (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT,
    date            TEXT,
    headline        TEXT,
    source          TEXT,
    url             TEXT,
    sentiment_score REAL,
    updated_at      TEXT,
    UNIQUE(ticker, date, headline)
);

CREATE TABLE IF NOT EXISTS market_summary (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    date     TEXT UNIQUE,
    dsex     REAL,
    ds30     REAL,
    dses     REAL,
    raw_data TEXT
);

CREATE TABLE IF NOT EXISTS recommendations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker            TEXT,
    date              TEXT,
    horizon           TEXT,
    signal            TEXT,
    confidence        REAL,
    manipulation_risk TEXT,
    entry_price       REAL,
    target            REAL,
    stop_loss         REAL,
    reasoning         TEXT,
    UNIQUE(ticker, date, horizon)
);

CREATE TABLE IF NOT EXISTS fundamentals_pit (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker            TEXT NOT NULL,
    snapshot_date     TEXT NOT NULL,
    publication_date  TEXT,
    fiscal_year       INTEGER,
    fiscal_quarter    INTEGER,
    eps               REAL,
    nav               REAL,
    pe_ratio          REAL,
    debt_equity       REAL,
    dividend_yield    REAL,
    roe               REAL,
    roa               REAL,
    current_ratio     REAL,
    revenue_cr        REAL,
    net_profit_cr     REAL,
    cash_flow_ops     REAL,
    source_hash       TEXT,
    created_at        TEXT,
    UNIQUE(ticker, snapshot_date)
);

CREATE TABLE IF NOT EXISTS trading_calendar (
    date            TEXT PRIMARY KEY,
    is_trading_day  INTEGER NOT NULL,
    session_type    TEXT NOT NULL,
    total_volume    INTEGER,
    total_trades    INTEGER,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS corporate_actions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker            TEXT NOT NULL,
    record_date       TEXT NOT NULL,
    action_type       TEXT NOT NULL,
    ratio             REAL NOT NULL,
    cash_amount       REAL,
    adjustment_factor REAL NOT NULL,
    notes             TEXT,
    UNIQUE(ticker, record_date, action_type)
);

CREATE TABLE IF NOT EXISTS database_audit_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_timestamp     TEXT NOT NULL,
    check_name          TEXT NOT NULL,
    status              TEXT NOT NULL,
    violation_count     INTEGER NOT NULL,
    total_checked       INTEGER NOT NULL,
    details             TEXT
);

CREATE INDEX IF NOT EXISTS idx_prices_ticker_date     ON prices(ticker, date);
CREATE INDEX IF NOT EXISTS idx_pit_ticker_snapshot    ON fundamentals_pit(ticker, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_fundamentals_ticker    ON fundamentals(ticker);
CREATE INDEX IF NOT EXISTS idx_news_ticker_date       ON news(ticker, date);
CREATE INDEX IF NOT EXISTS idx_recommendations_ticker ON recommendations(ticker);
"""


def get_db() -> sqlite3.Connection:
    PROC_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(DDL)
    conn.commit()
    return conn


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_raw(category: str, date_str: str) -> dict | list | None:
    path = RAW_DIR / date_str / f"{category}.json"
    if not path.exists():
        log.warning(f"Raw file not found: {path}")
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_config(name: str) -> dict:
    with open(CONFIG_DIR / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


# ── Parsers ───────────────────────────────────────────────────────────────────

def _to_float(val) -> float | None:
    try:
        return float(str(val).replace(",", "").replace("%", "").replace("৳", "").strip())
    except Exception:
        return None


def _to_int(val) -> int | None:
    try:
        return int(str(val).replace(",", "").strip())
    except Exception:
        return None


def _normalize_key(k: str) -> str:
    """Normalize scraped field key: lowercase, spaces→_, slashes→_, strip parens."""
    return (
        k.lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("(", "")
        .replace(")", "")
        .strip("_")
    )


def _detect_fiscal_period(raw: dict) -> tuple[int, int]:
    """
    Extract year/quarter from raw scraped data.
    Authoritative source: multi_year_financials[-1]['year']
    Falls back to current year/quarter with strict sanity bounds (2015 <= year <= current_year + 1).
    """
    import re
    today = datetime.date.today()
    default_year = today.year
    default_q = (today.month - 1) // 3 + 1

    # Authoritative: latest audited year from multi_year_financials
    my = raw.get("multi_year_financials")
    if isinstance(my, list) and my:
        latest = my[-1].get("year")
        if latest and 2015 <= int(latest) <= default_year + 1:
            return int(latest), 4

    for k, v in raw.items():
        if not isinstance(v, str):
            continue
        # Pattern: exact 4-digit year bounded by word boundaries
        year_match = re.search(r"\b20([1-3]\d)\b", v)
        if year_match:
            cand_year = int("20" + year_match.group(1))
            if 2015 <= cand_year <= default_year + 1:
                q_match = re.search(r"Q([1-4])", v, re.I)
                if q_match:
                    return cand_year, int(q_match.group(1))
                # Fiscal year end month → Q4
                month_map = {
                    "jan": 2, "feb": 2, "mar": 4, "apr": 1, "may": 1, "jun": 4,
                    "jul": 1, "aug": 2, "sep": 3, "oct": 2, "nov": 3, "dec": 4,
                }
                for mon, q in month_map.items():
                    if mon in v.lower():
                        return cand_year, q
                return cand_year, default_q

    return default_year, default_q


def parse_fundamentals_row(ticker: str, raw: dict) -> dict:
    """Map scraped field names → canonical schema fields."""
    field_map = {
        "eps":            ["eps", "earning_per_share", "earning_per_share_tk", "eps_tk"],
        "nav":            ["nav", "net_asset_value_per_share", "book_value", "nav_per_share"],
        "pe_ratio":       ["pe", "p_e", "pe_ratio", "price_eps", "p_e_ratio"],
        "dividend_yield": ["dividend_yield", "yield", "dividend_%", "dividend_percent"],
        "debt_equity":    ["debt_equity", "d_e_ratio", "debt_to_equity", "leverage_ratio"],
        "roe":            ["roe", "return_on_equity", "return_on_equity_%"],
        "roa":            ["roa", "return_on_asset", "return_on_assets_%"],
        "current_ratio":  ["current_ratio", "cr", "liquidity_ratio"],
        "market_cap_cr":  ["market_cap", "market_capitalisation", "market_cap_cr", "market_cap_bdt_cr"],
        "sponsor_pct":    ["sponsor_director_holding_pct", "sponsor_%", "sponsor_holding"],
        "revenue_cr":     ["revenue", "net_revenue", "turnover", "total_revenue", "net_sales"],
        "net_profit_cr":  ["net_profit", "profit_after_tax", "pat", "net_income"],
        "cash_flow_ops":  ["cash_flow_from_operations", "cfo", "operating_cash_flow"],
    }

    result = {"ticker": ticker}

    # Normalize all raw keys once
    raw_norm = {_normalize_key(k): v for k, v in raw.items()}

    for canonical, aliases in field_map.items():
        for alias in aliases:
            if alias in raw_norm:
                result[canonical] = _to_float(raw_norm[alias])
                break

    # Empirical Debt/Equity fallback calculation from audited loanStatus + equity
    if result.get("debt_equity") is None:
        st = _to_float(raw_norm.get("short_term_loan_mn")) or 0.0
        lt = _to_float(raw_norm.get("long_term_loan_mn")) or 0.0
        tot_loan = st + lt
        nav = result.get("nav")
        puc = _to_float(raw_norm.get("paid_up_capital"))
        if nav and puc and nav > 0 and puc > 0:
            equity_mn = (puc / 10.0 * nav) / 1e6
            if equity_mn > 0:
                result["debt_equity"] = round(tot_loan / equity_mn, 3)

    return result


# ── Writers ───────────────────────────────────────────────────────────────────

def upsert_company(conn: sqlite3.Connection, ticker: str, sector: str,
                   category: str, parsed: dict):
    conn.execute("""
        INSERT INTO companies
            (ticker, sector, category, market_cap_cr, sponsor_holding_pct, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker) DO UPDATE SET
            sector              = excluded.sector,
            category            = excluded.category,
            market_cap_cr       = excluded.market_cap_cr,
            sponsor_holding_pct = excluded.sponsor_holding_pct,
            updated_at          = excluded.updated_at
    """, (
        ticker,
        sector,
        category,
        parsed.get("market_cap_cr"),
        parsed.get("sponsor_pct"),
        datetime.datetime.utcnow().isoformat(),
    ))


def upsert_fundamentals(conn: sqlite3.Connection, parsed: dict, raw: dict):
    year, quarter = _detect_fiscal_period(raw)
    conn.execute("""
        INSERT INTO fundamentals
            (ticker, year, quarter, eps, nav, pe_ratio, debt_equity,
             dividend_yield, roe, roa, current_ratio, revenue_cr,
             net_profit_cr, cash_flow_ops, raw_data, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(ticker, year, quarter) DO UPDATE SET
            eps           = excluded.eps,
            nav           = excluded.nav,
            pe_ratio      = excluded.pe_ratio,
            debt_equity   = excluded.debt_equity,
            dividend_yield = excluded.dividend_yield,
            roe           = excluded.roe,
            roa           = excluded.roa,
            current_ratio = excluded.current_ratio,
            revenue_cr    = excluded.revenue_cr,
            net_profit_cr = excluded.net_profit_cr,
            cash_flow_ops = excluded.cash_flow_ops,
            raw_data      = excluded.raw_data,
            updated_at    = excluded.updated_at
    """, (
        parsed["ticker"], year, quarter,
        parsed.get("eps"), parsed.get("nav"), parsed.get("pe_ratio"),
        parsed.get("debt_equity"), parsed.get("dividend_yield"),
        parsed.get("roe"), parsed.get("roa"), parsed.get("current_ratio"),
        parsed.get("revenue_cr"), parsed.get("net_profit_cr"),
        parsed.get("cash_flow_ops"),
        json.dumps(raw, ensure_ascii=False), datetime.datetime.utcnow().isoformat(),
    ))

    # Also record immutable Point-in-Time snapshot into fundamentals_pit
    today_str = datetime.date.today().isoformat()
    import hashlib
    raw_str = json.dumps(raw, sort_keys=True)
    hash_val = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()[:16]
    conn.execute("""
        INSERT INTO fundamentals_pit
            (ticker, snapshot_date, publication_date, fiscal_year, fiscal_quarter,
             eps, nav, pe_ratio, debt_equity, dividend_yield, roe, roa,
             current_ratio, revenue_cr, net_profit_cr, cash_flow_ops, source_hash, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(ticker, snapshot_date) DO UPDATE SET
            eps           = excluded.eps,
            nav           = excluded.nav,
            pe_ratio      = excluded.pe_ratio,
            debt_equity   = excluded.debt_equity,
            dividend_yield= excluded.dividend_yield,
            roe           = excluded.roe,
            roa           = excluded.roa,
            current_ratio = excluded.current_ratio,
            revenue_cr    = excluded.revenue_cr,
            net_profit_cr = excluded.net_profit_cr,
            cash_flow_ops = excluded.cash_flow_ops,
            source_hash   = excluded.source_hash
    """, (
        parsed["ticker"], today_str, today_str, year, quarter,
        parsed.get("eps"), parsed.get("nav"), parsed.get("pe_ratio"),
        parsed.get("debt_equity"), parsed.get("dividend_yield"),
        parsed.get("roe"), parsed.get("roa"), parsed.get("current_ratio"),
        parsed.get("revenue_cr"), parsed.get("net_profit_cr"),
        parsed.get("cash_flow_ops"),
        hash_val, datetime.datetime.utcnow().isoformat(),
    ))

    # ── Ingest Multi-Year Audited Financials if available ──
    multi_year = raw.get("multi_year_financials")
    if isinstance(multi_year, list):
        for my_item in multi_year:
            my_year = my_item.get("year")
            if not my_year:
                continue
            my_eps = _to_float(my_item.get("epsBasic") or my_item.get("eps"))
            my_nav = _to_float(my_item.get("nav"))
            my_pe = _to_float(my_item.get("pe"))
            my_div_yield = _to_float(my_item.get("dividendYield"))
            my_profit = _to_float(my_item.get("profit"))
            profit_cr = round(my_profit / 10.0, 2) if my_profit is not None else None
            my_raw_str = json.dumps(my_item, ensure_ascii=False)
            my_hash = hashlib.sha256(my_raw_str.encode("utf-8")).hexdigest()[:16]

            # Ingest into fundamentals table (quarter 4 = full year audited)
            conn.execute("""
                INSERT INTO fundamentals
                    (ticker, year, quarter, eps, nav, pe_ratio, dividend_yield,
                     net_profit_cr, raw_data, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(ticker, year, quarter) DO UPDATE SET
                    eps           = COALESCE(excluded.eps, fundamentals.eps),
                    nav           = COALESCE(excluded.nav, fundamentals.nav),
                    pe_ratio      = COALESCE(excluded.pe_ratio, fundamentals.pe_ratio),
                    dividend_yield= COALESCE(excluded.dividend_yield, fundamentals.dividend_yield),
                    net_profit_cr = COALESCE(excluded.net_profit_cr, fundamentals.net_profit_cr),
                    updated_at    = excluded.updated_at
            """, (
                parsed["ticker"], my_year, 4,
                my_eps, my_nav, my_pe, my_div_yield, profit_cr,
                my_raw_str, datetime.datetime.utcnow().isoformat()
            ))

            # Ingest into fundamentals_pit (snapshot_date at fiscal year end)
            my_snap = f"{my_year}-06-30"
            conn.execute("""
                INSERT INTO fundamentals_pit
                    (ticker, snapshot_date, publication_date, fiscal_year, fiscal_quarter,
                     eps, nav, pe_ratio, dividend_yield, net_profit_cr, source_hash, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(ticker, snapshot_date) DO UPDATE SET
                    eps           = COALESCE(excluded.eps, fundamentals_pit.eps),
                    nav           = COALESCE(excluded.nav, fundamentals_pit.nav),
                    pe_ratio      = COALESCE(excluded.pe_ratio, fundamentals_pit.pe_ratio),
                    dividend_yield= COALESCE(excluded.dividend_yield, fundamentals_pit.dividend_yield),
                    net_profit_cr = COALESCE(excluded.net_profit_cr, fundamentals_pit.net_profit_cr),
                    source_hash   = excluded.source_hash
            """, (
                parsed["ticker"], my_snap, my_snap, my_year, 4,
                my_eps, my_nav, my_pe, my_div_yield, profit_cr,
                my_hash, datetime.datetime.utcnow().isoformat()
            ))

    # ── Ingest Interim Quarterly Financials if available ──
    interim = raw.get("interim_financials")
    if isinstance(interim, dict):
        period_ends = interim.get("periodEnds", {})
        for row in interim.get("rows", []):
            metric_name = row.get("metric", "")
            if "Earnings Per Share" in metric_name and "Diluted" not in metric_name:
                for qk in ["q1", "q2", "q3"]:
                    q_eps = _to_float(row.get(qk))
                    pend = period_ends.get(qk)
                    if q_eps is not None and pend and len(str(pend)) >= 6:
                        pend_str = str(pend)
                        pyear = int(pend_str[:4])
                        pmonth = int(pend_str[4:6])
                        last_day = 31 if pmonth in [1, 3, 5, 7, 8, 10, 12] else (28 if pmonth == 2 else 30)
                        snap_date = f"{pyear}-{pmonth:02d}-{last_day:02d}"
                        q_num = int(qk[1])
                        fiscal_yr = pyear if pmonth <= 6 else pyear + 1
                        int_raw_str = json.dumps({"metric": metric_name, "period": pend_str, "eps": q_eps}, ensure_ascii=False)
                        int_hash = hashlib.sha256(int_raw_str.encode("utf-8")).hexdigest()[:16]

                        conn.execute("""
                            INSERT INTO fundamentals
                                (ticker, year, quarter, eps, raw_data, updated_at)
                            VALUES (?,?,?,?,?,?)
                            ON CONFLICT(ticker, year, quarter) DO UPDATE SET
                                eps        = excluded.eps,
                                updated_at = excluded.updated_at
                        """, (
                            parsed["ticker"], fiscal_yr, q_num,
                            q_eps, int_raw_str, datetime.datetime.utcnow().isoformat()
                        ))

                        conn.execute("""
                            INSERT INTO fundamentals_pit
                                (ticker, snapshot_date, publication_date, fiscal_year, fiscal_quarter,
                                 eps, source_hash, created_at)
                            VALUES (?,?,?,?,?,?,?,?)
                            ON CONFLICT(ticker, snapshot_date) DO UPDATE SET
                                eps         = excluded.eps,
                                fiscal_year = excluded.fiscal_year,
                                fiscal_quarter = excluded.fiscal_quarter,
                                source_hash = excluded.source_hash
                        """, (
                            parsed["ticker"], snap_date, snap_date, fiscal_yr, q_num,
                            q_eps, int_hash, datetime.datetime.utcnow().isoformat()
                        ))


def insert_prices(conn: sqlite3.Connection, ticker: str, records: list[dict],
                  fallback_date: str):
    for rec in records:
        # Accept 'date', 'Date', or fallback
        date_val = rec.get("date") or rec.get("Date") or fallback_date
        close_val = _to_float(rec.get("close") or rec.get("ltp") or
                               rec.get("last_price") or rec.get("closeprice"))
        if close_val is None:
            continue
        high_val  = _to_float(rec.get("high") or rec.get("highprice") or close_val)
        low_val   = _to_float(rec.get("low") or rec.get("lowprice") or close_val)
        open_val  = _to_float(rec.get("open") or rec.get("openprice") or close_val)
        vol_val   = _to_int(rec.get("volume") or rec.get("ycp") or 0)
        val_val   = _to_float(rec.get("value") or rec.get("trade") or 0)

        if high_val is not None and low_val is not None and high_val < low_val:
            log.warning(f"Data error {ticker} {date_val}: high({high_val}) < low({low_val}). Skipping.")
            continue

        # Check for corporate action factor adjustments (splits/bonus dividends)
        adj_factor = 1.0
        ca_row = conn.execute("""
            SELECT adjustment_factor FROM corporate_actions
            WHERE ticker = ? AND record_date > ? AND adjustment_factor IS NOT NULL
        """, (ticker, date_val)).fetchone()
        if ca_row and ca_row[0] and ca_row[0] > 0:
            adj_factor = float(ca_row[0])
            open_val = round(open_val * adj_factor, 2)
            high_val = round(high_val * adj_factor, 2)
            low_val = round(low_val * adj_factor, 2)
            close_val = round(close_val * adj_factor, 2)

        conn.execute("""
            INSERT OR IGNORE INTO prices
                (ticker, date, open, high, low, close, volume, value)
            VALUES (?,?,?,?,?,?,?,?)
        """, (ticker, date_val, open_val, high_val, low_val, close_val, vol_val, val_val))


def insert_news_items(conn: sqlite3.Connection, ticker: str, articles: list[dict]):
    for art in articles:
        headline = art.get("title") or art.get("headline") or ""
        if not headline:
            continue
        conn.execute("""
            INSERT OR IGNORE INTO news
                (ticker, date, headline, source, url, updated_at)
            VALUES (?,?,?,?,?,?)
        """, (
            ticker,
            art.get("date", datetime.date.today().isoformat()),
            headline,
            art.get("source", ""),
            art.get("url", ""),
            datetime.datetime.utcnow().isoformat(),
        ))


def insert_market_summary(conn: sqlite3.Connection, date_str: str, raw):
    def extract_index(key: str) -> float | None:
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    for k, v in item.items():
                        if key.lower() in str(k).lower():
                            return _to_float(v)
        elif isinstance(raw, dict):
            for k, v in raw.items():
                if key.lower() in str(k).lower():
                    if isinstance(v, dict):
                        return _to_float(v.get("value") or v.get("close") or v.get("index"))
                    return _to_float(v)
        return None

    conn.execute("""
        INSERT OR REPLACE INTO market_summary (date, dsex, ds30, dses, raw_data)
        VALUES (?,?,?,?,?)
    """, (
        date_str,
        extract_index("DSEX"),
        extract_index("DS30"),
        extract_index("DSES"),
        json.dumps(raw, ensure_ascii=False),
    ))


# ── Orchestration ─────────────────────────────────────────────────────────────

def process_date(date_str: str = None):
    if date_str is None:
        date_str = datetime.date.today().isoformat()

    log.info(f"=== Processing {date_str} ===")
    conn = get_db()
    sectors = load_config("sectors")

    # Build ticker → sector map
    ticker_sector = {}
    for sector, sdata in sectors["sectors"].items():
        for t in sdata["top_tickers"]:
            ticker_sector[t] = sector

    # Market summary
    summary = load_raw("market_summary", date_str)
    if summary:
        insert_market_summary(conn, date_str, summary)
        conn.commit()

    # All prices (today snapshot) — read category from price data itself
    all_prices = load_raw("all_prices", date_str)
    if all_prices:
        if isinstance(all_prices, list):
            for rec in all_prices:
                ticker = str(rec.get("ticker") or rec.get("symbol") or rec.get("code") or "").strip()
                if not ticker:
                    continue
                insert_prices(conn, ticker, [rec], date_str)
        conn.commit()
        log.info(f"Inserted {len(all_prices) if isinstance(all_prices, list) else '?'} price snapshots")

    # Historical prices per ticker
    historical = load_raw("historical_prices", date_str)
    if historical:
        for ticker, records in historical.items():
            insert_prices(conn, ticker, records, date_str)
        conn.commit()
        log.info("Historical prices inserted")

    # Fundamentals per ticker
    fundamentals = load_raw("fundamentals", date_str)
    if fundamentals:
        # Build category map from all_prices data
        cat_map = {}
        if isinstance(all_prices, list):
            for rec in all_prices:
                t = str(rec.get("ticker") or rec.get("symbol") or "").strip()
                c = str(rec.get("category") or "A").strip()
                if t:
                    cat_map[t] = c

        for ticker, raw_fund in fundamentals.items():
            parsed = parse_fundamentals_row(ticker, raw_fund)
            sector = ticker_sector.get(ticker, "Unknown")
            category = cat_map.get(ticker, "A")
            upsert_company(conn, ticker, sector, category, parsed)
            upsert_fundamentals(conn, parsed, raw_fund)
        conn.commit()
        log.info(f"Fundamentals inserted for {len(fundamentals)} tickers")

    # News — per ticker
    news_data = load_raw("news", date_str)
    if news_data:
        for ticker, articles in news_data.items():
            insert_news_items(conn, ticker, articles)
        conn.commit()

    # News — market-wide
    market_news = load_raw("market_news", date_str)
    if market_news:
        insert_news_items(conn, "", market_news)
        conn.commit()
        log.info("Market news inserted")

    conn.close()
    log.info(f"=== Processing complete: {date_str} ===")


def get_ticker_data(ticker: str, days: int = 365) -> dict:
    """
    Fetch all stored data for a ticker.
    Pass days matching the analysis horizon:
      weekly=30, monthly=90, quarterly=365, yearly=1825
    """
    conn = get_db()
    since = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()

    prices = conn.execute(
        "SELECT * FROM prices WHERE ticker=? AND date>=? ORDER BY date ASC",
        (ticker, since)
    ).fetchall()

    fundamentals = conn.execute(
        "SELECT * FROM fundamentals WHERE ticker=? ORDER BY year DESC, quarter DESC LIMIT 12",
        (ticker,)
    ).fetchall()

    news = conn.execute(
        "SELECT * FROM news WHERE ticker=? ORDER BY date DESC LIMIT 30",
        (ticker,)
    ).fetchall()

    company = conn.execute(
        "SELECT * FROM companies WHERE ticker=?", (ticker,)
    ).fetchone()

    conn.close()
    return {
        "ticker":       ticker,
        "company":      dict(company) if company else {},
        "prices":       [dict(r) for r in prices],
        "fundamentals": [dict(r) for r in fundamentals],
        "news":         [dict(r) for r in news],
    }


def load_sectors() -> dict:
    return load_config("sectors")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    process_date(sys.argv[1] if len(sys.argv) > 1 else None)
