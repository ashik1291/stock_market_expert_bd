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
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from constants import STATUTORY_LAG_DAYS  # noqa: E402

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
    tradable_date     TEXT,
    filing_type       TEXT,
    publication_is_estimated INTEGER DEFAULT 0,
    publication_source TEXT,
    ingest_id         TEXT,
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
CREATE INDEX IF NOT EXISTS idx_pit_publication_date   ON fundamentals_pit(publication_date);
CREATE INDEX IF NOT EXISTS idx_pit_tradable_date      ON fundamentals_pit(tradable_date);
CREATE INDEX IF NOT EXISTS idx_fundamentals_ticker    ON fundamentals(ticker);
CREATE INDEX IF NOT EXISTS idx_news_ticker_date       ON news(ticker, date);
CREATE INDEX IF NOT EXISTS idx_recommendations_ticker ON recommendations(ticker);
CREATE INDEX IF NOT EXISTS idx_pit_composite ON fundamentals_pit(ticker, tradable_date, publication_date);
CREATE INDEX IF NOT EXISTS idx_pit_verified ON fundamentals_pit(publication_is_estimated, tradable_date);
CREATE INDEX IF NOT EXISTS idx_corp_actions_composite ON corporate_actions(ticker, action_type, record_date);
"""


def _next_trading_day_for_migration(conn: sqlite3.Connection, iso_date: str) -> str:
    """Nearest trading day on or after iso_date via trading_calendar, fallback Mon-Fri."""
    try:
        row = conn.execute(
            "SELECT date FROM trading_calendar WHERE date >= ? AND is_trading_day = 1 ORDER BY date ASC LIMIT 1",
            (iso_date,),
        ).fetchone()
        if row and row[0]:
            return str(row[0])
    except Exception:
        pass
    try:
        d = datetime.date.fromisoformat(iso_date[:10])
        for _ in range(7):
            d += datetime.timedelta(days=1)
            # Sunday-Thursday is DSE trading week; Friday (4) and Saturday (5) are closed
            if d.weekday() not in (4, 5):
                return d.isoformat()
        return d.isoformat()
    except Exception:
        return iso_date


def get_db() -> sqlite3.Connection:
    PROC_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.row_factory = sqlite3.Row
    # Ensure new PIT columns exist before creating indexes that reference them
    try:
        existing = {r[1] for r in conn.execute("PRAGMA table_info(fundamentals_pit)").fetchall()} if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fundamentals_pit'").fetchone() else set()
        if existing:
            for col, typ in [("tradable_date", "TEXT"), ("filing_type", "TEXT"),
                             ("publication_is_estimated", "INTEGER DEFAULT 0"),
                             ("publication_source", "TEXT"), ("ingest_id", "TEXT")]:
                if col not in existing:
                    conn.execute(f"ALTER TABLE fundamentals_pit ADD COLUMN {col} {typ}")
            conn.commit()
    except Exception:
        pass
    conn.executescript(DDL)
    # Idempotent indexes (DDL may have already created them)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pit_publication_date ON fundamentals_pit(publication_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pit_tradable_date    ON fundamentals_pit(tradable_date)")
        conn.commit()
    except Exception:
        pass
    from db_guards import install_data_guards
    install_data_guards(conn)
    # Backfill legacy rows where disclosure-lag columns are NULL/placeholder:
    # publication_source IS NULL means row predates PIT lag model; recompute
    # annual (Q4) -> snapshot+75d next trading day; interim (Q1-3) -> +45d next trading day
    # tradable = next trading day after publication_date
    try:
        legacy = conn.execute(
            "SELECT id, snapshot_date, fiscal_quarter FROM fundamentals_pit "
            "WHERE publication_source IS NULL"
        ).fetchall()
        if legacy:
            for r in legacy:
                rid, snap, fq = r[0], r[1], r[2]
                # snap may be malformed (e.g. 2015.3-06-30); skip if not ISO
                try:
                    base = datetime.date.fromisoformat(str(snap)[:10])
                except Exception:
                    continue
                lag = STATUTORY_LAG_DAYS.get(fq, STATUTORY_LAG_DAYS[4])
                filing = "annual" if (fq == 4 or fq is None) else "interim"
                pub_raw = (base + datetime.timedelta(days=lag)).isoformat()
                pub = _next_trading_day_for_migration(conn, pub_raw)
                trad = _next_trading_day_for_migration(
                    conn, (datetime.date.fromisoformat(pub) + datetime.timedelta(days=1)).isoformat()
                )
                conn.execute(
                    "UPDATE fundamentals_pit SET publication_date=?, tradable_date=?, "
                    "filing_type=COALESCE(filing_type, ?), publication_is_estimated=1, "
                    "publication_source='estimated' WHERE id=?",
                    (pub, trad, filing, rid),
                )
            conn.commit()
        # Any remaining rows with tradable_date still NULL but publication_date set
        # (e.g. rows inserted with old tradable=pub backfill) -> push tradable to next trading day after pub
        remaining = conn.execute(
            "SELECT id, publication_date FROM fundamentals_pit WHERE tradable_date IS NULL AND publication_date IS NOT NULL"
        ).fetchall()
        for r in remaining:
            rid, pub = r[0], r[1]
            try:
                trad = _next_trading_day_for_migration(
                    conn, (datetime.date.fromisoformat(str(pub)[:10]) + datetime.timedelta(days=1)).isoformat()
                )
            except Exception:
                trad = pub
            conn.execute("UPDATE fundamentals_pit SET tradable_date=? WHERE id=?", (trad, rid))
        if remaining:
            conn.commit()
        # Legacy tradable == snapshot rows that should have lag but publication_source already set to estimated
        # with pub==snapshot (first backfill was naive). Fix those too.
        # CRITICAL FIX: Live scrapes (where snap is not a fiscal quarter end) are already public on snap date!
        naive = conn.execute(
            "SELECT id, snapshot_date, publication_date, tradable_date, fiscal_quarter "
            "FROM fundamentals_pit WHERE publication_source='estimated' "
            "AND publication_date = snapshot_date"
        ).fetchall()
        for r in naive:
            rid, snap, _, _, fq = r[0], r[1], r[2], r[3], r[4]
            try:
                base = datetime.date.fromisoformat(str(snap)[:10])
            except Exception:
                continue
            is_quarter_end = any(str(snap).strip().endswith(qe) for qe in ("-03-31", "-06-30", "-09-30", "-12-31"))
            if not is_quarter_end:
                pub = base.isoformat()
                trad = _next_trading_day_for_migration(
                    conn, (base + datetime.timedelta(days=1)).isoformat()
                )
                conn.execute(
                    "UPDATE fundamentals_pit SET publication_date=?, tradable_date=?, publication_source='live_scrape', publication_is_estimated=0 WHERE id=?",
                    (pub, trad, rid),
                )
            else:
                lag = STATUTORY_LAG_DAYS.get(fq, STATUTORY_LAG_DAYS[4])
                pub_raw = (base + datetime.timedelta(days=lag)).isoformat()
                pub = _next_trading_day_for_migration(conn, pub_raw)
                trad = _next_trading_day_for_migration(
                    conn, (datetime.date.fromisoformat(pub) + datetime.timedelta(days=1)).isoformat()
                )
                conn.execute(
                    "UPDATE fundamentals_pit SET publication_date=?, tradable_date=? WHERE id=?",
                    (pub, trad, rid),
                )
        if naive:
            conn.commit()
    except Exception:
        pass
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


def _detect_fiscal_period(raw: dict) -> tuple[int, int] | None:
    """Latest audited fiscal year from multi_year_financials, or None when the payload names no period."""
    my = raw.get("multi_year_financials")
    if isinstance(my, list) and my:
        try:
            return int(float(my[-1].get("year"))), 4
        except (TypeError, ValueError):
            pass
    return None


def latest_ended_quarter(observed_date: str, fye_month: int) -> tuple[int, int]:
    """(fiscal_year, quarter) of the last fiscal quarter that ended on or before observed_date."""
    d = datetime.date.fromisoformat(observed_date)
    y, m = d.year, d.month
    while True:
        if (m - fye_month) % 3 == 0 and _month_end(y, m) <= observed_date:
            end = _month_end(y, m)
            return fiscal_year_of(end, fye_month), 4 - ((fye_month - m) % 12) // 3
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)


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
        "govt_pct":       ["govt_holding_pct", "govt_%", "government_holding_pct", "government_holding"],
        "institutional_pct": ["institutional_holding_pct", "institutional_%", "institute_holding_pct", "institutional_pct"],
        "public_pct":     ["public_holding_pct", "public_%", "public_pct"],
        "revenue_cr":     ["revenue", "net_revenue", "turnover", "total_revenue", "net_sales"],
        "net_profit_cr":  ["net_profit", "profit_after_tax", "pat", "net_income"],
        "cash_flow_ops":  ["cash_flow_from_operations", "cfo", "operating_cash_flow", "nocfps"],
    }

    result = {"ticker": ticker}

    # Normalize all raw keys once
    raw_norm = {_normalize_key(k): v for k, v in raw.items()}

    for canonical, aliases in field_map.items():
        for alias in aliases:
            if alias in raw_norm:
                result[canonical] = _to_float(raw_norm[alias])
                break

    # Fallback profit from multi_year_financials (profit in mn -> / 10 for Cr)
    if result.get("net_profit_cr") is None:
        my = raw.get("multi_year_financials", [])
        if my and isinstance(my, list):
            latest_my = my[-1]
            p = latest_my.get("profit") or latest_my.get("profitForYear")
            if p:
                result["net_profit_cr"] = round(float(p) / 10.0, 2)

    # Fallback cash_flow_ops from NOCFPS if present
    if result.get("cash_flow_ops") is None:
        nocf = raw.get("nocfps") or raw_norm.get("nocfps")
        if nocf is not None:
            result["cash_flow_ops"] = _to_float(nocf)

    if "name" in raw_norm and raw_norm["name"]:
        result["name"] = str(raw_norm["name"]).strip()
    elif "name" in raw and raw["name"]:
        result["name"] = str(raw["name"]).strip()

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
            (ticker, name, sector, category, market_cap_cr, sponsor_holding_pct, govt_holding_pct, institutional_pct, public_holding_pct, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker) DO UPDATE SET
            name                = COALESCE(excluded.name, companies.name),
            sector              = COALESCE(excluded.sector, companies.sector),
            category            = COALESCE(excluded.category, companies.category),
            market_cap_cr       = COALESCE(excluded.market_cap_cr, companies.market_cap_cr),
            sponsor_holding_pct = COALESCE(excluded.sponsor_holding_pct, companies.sponsor_holding_pct),
            govt_holding_pct    = COALESCE(excluded.govt_holding_pct, companies.govt_holding_pct),
            institutional_pct   = COALESCE(excluded.institutional_pct, companies.institutional_pct),
            public_holding_pct  = COALESCE(excluded.public_holding_pct, companies.public_holding_pct),
            updated_at          = excluded.updated_at
    """, (
        ticker,
        parsed.get("name"),
        sector,
        category,
        parsed.get("market_cap_cr"),
        parsed.get("sponsor_pct"),
        parsed.get("govt_pct"),
        parsed.get("institutional_pct"),
        parsed.get("public_pct"),
        datetime.datetime.utcnow().isoformat(),
    ))


# Income year is July-June by law except banks, insurers, financial institutions and
# multinational subsidiaries. Used only when the company's own interim period ends are unknown.
FISCAL_YEAR_END_OVERRIDES = {"RECKITTBEN": 12, "UNILEVERCL": 12}
CALENDAR_YEAR_SECTORS = {"Banking", "Insurance", "Financial Institutions"}


def _month_end(year: int, month: int) -> str:
    import calendar
    return f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"


def fiscal_year_end_month(conn: sqlite3.Connection, ticker: str, raw: dict | None = None) -> int:
    """
    Fiscal year-end month for ticker. Derived from the company's own Q1 period end
    (FYE = Q1 end - 3 months) when the scraped payload has it, and persisted on companies.
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(companies)")}
    if "fiscal_year_end_month" not in cols:
        conn.execute("ALTER TABLE companies ADD COLUMN fiscal_year_end_month INTEGER")
    q1 = (((raw or {}).get("interim_financials") or {}).get("periodEnds") or {}).get("q1")
    if q1 and len(str(q1)) >= 6 and str(q1)[4:6].isdigit():
        month = (int(str(q1)[4:6]) - 4) % 12 + 1
        conn.execute("UPDATE companies SET fiscal_year_end_month = ? WHERE ticker = ?", (month, ticker))
        return month
    row = conn.execute("SELECT fiscal_year_end_month, sector FROM companies WHERE ticker = ?", (ticker,)).fetchone()
    if row and row[0]:
        return int(row[0])
    if ticker in FISCAL_YEAR_END_OVERRIDES:
        return FISCAL_YEAR_END_OVERRIDES[ticker]
    sector = (row[1] if row else None) or (raw or {}).get("sector")
    return 12 if sector in CALENDAR_YEAR_SECTORS else 6


def fiscal_quarter_end(fy: int, q: int, fye_month: int) -> str:
    """Quarter-end date of quarter q of the fiscal year that ends in calendar year fy."""
    months_back = 3 * (4 - q)
    total = fy * 12 + (fye_month - 1) - months_back
    return _month_end(total // 12, total % 12 + 1)


def fiscal_year_of(period_end: str, fye_month: int) -> int:
    """Fiscal year label (calendar year in which the fiscal year ends) for a period-end date."""
    y, m = int(period_end[:4]), int(period_end[5:7])
    return y if m <= fye_month else y + 1


def upsert_fundamentals(conn: sqlite3.Connection, parsed: dict, raw: dict, observed_date: str | None = None):
    observed_date = observed_date or datetime.date.today().isoformat()
    fye_month = fiscal_year_end_month(conn, parsed["ticker"], raw)
    period = _detect_fiscal_period(raw)
    if period and fiscal_quarter_end(period[0], period[1], fye_month) > observed_date:
        period = None
    year, quarter = period or latest_ended_quarter(observed_date, fye_month)
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

    # PIT helper — nearest trading day on or after dt (via trading_calendar)
    def _next_trading_day(conn: sqlite3.Connection, iso_date: str) -> str:
        try:
            row = conn.execute(
                "SELECT date FROM trading_calendar WHERE date >= ? AND is_trading_day = 1 ORDER BY date ASC LIMIT 1",
                (iso_date,),
            ).fetchone()
            if row and row[0]:
                return str(row[0])
        except Exception:
            pass
        # Holiday/weekend fallback: step forward at most 7 days
        try:
            d = datetime.date.fromisoformat(iso_date)
            for _ in range(7):
                d += datetime.timedelta(days=1)
                # Sunday-Thursday is DSE trading week; Friday (4) and Saturday (5) are closed
                if d.weekday() not in (4, 5):
                    return d.isoformat()
            return d.isoformat()
        except Exception:
            return iso_date

    def _psi_publication_date(raw: dict) -> str | None:
        """Return explicit PSI/disclosure timestamp if present, else None."""
        for key in ("publication_date", "disclosure_date", "psi_date", "announcement_date", "filing_date"):
            v = raw.get(key)
            if isinstance(v, str) and len(v) >= 10 and v[:4].isdigit():
                # normalize to YYYY-MM-DD
                return v[:10]
        return None

    # Also record immutable Point-in-Time snapshot into fundamentals_pit
    # snapshot_date = fiscal period end; publication_date/tradable_date = when tradable
    import hashlib
    import uuid as _uuid
    raw_str = json.dumps(raw, sort_keys=True)
    hash_val = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()[:16]
    ingest_id = _uuid.uuid4().hex[:12]
    # A company-page snapshot that names no ended fiscal period is not a filing: no PIT row.
    if period:
        pit_snapshot = fiscal_quarter_end(year, quarter, fye_month)
        psi_pub = _psi_publication_date(raw)
        if psi_pub and psi_pub < pit_snapshot:
            psi_pub = None  # a release cannot precede its own period end
        if psi_pub:
            pub_date_raw = psi_pub
            pub_is_est = 0
            pub_source = "psi"
        else:
            lag_days = STATUTORY_LAG_DAYS.get(quarter, STATUTORY_LAG_DAYS[4])
            try:
                base = datetime.date.fromisoformat(pit_snapshot)
                pub_date_raw = (base + datetime.timedelta(days=lag_days)).isoformat()
            except Exception:
                pub_date_raw = pit_snapshot
            pub_is_est = 1
            pub_source = "estimated"
        publication_date = _next_trading_day(conn, pub_date_raw)
        tradable_date = _next_trading_day(conn, (datetime.date.fromisoformat(publication_date) + datetime.timedelta(days=1)).isoformat())
        filing_type = "annual" if quarter == 4 else "interim"
        conn.execute("""
            INSERT INTO fundamentals_pit
                (ticker, snapshot_date, publication_date, tradable_date, filing_type,
                 publication_is_estimated, publication_source, ingest_id,
                 fiscal_year, fiscal_quarter,
                 eps, nav, pe_ratio, debt_equity, dividend_yield, roe, roa,
                 current_ratio, revenue_cr, net_profit_cr, cash_flow_ops, source_hash, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(ticker, snapshot_date) DO UPDATE SET
                publication_date         = excluded.publication_date,
                tradable_date            = excluded.tradable_date,
                filing_type              = excluded.filing_type,
                publication_is_estimated = excluded.publication_is_estimated,
                publication_source       = excluded.publication_source,
                ingest_id                = excluded.ingest_id,
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
            WHERE COALESCE(fundamentals_pit.publication_source, '') != 'dse_disclosure'
        """, (
            parsed["ticker"], pit_snapshot, publication_date, tradable_date, filing_type,
            pub_is_est, pub_source, ingest_id,
            year, quarter,
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
            try:
                my_year = int(float(str(my_year).strip()))
            except Exception:
                continue
            if my_year < 1990 or my_year > 2050:
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

            # Ingest into fundamentals_pit (snapshot_date at fiscal year end, disclosure-lag publication/tradable)
            my_snap = fiscal_quarter_end(my_year, 4, fye_month)
            if my_snap > observed_date:
                continue
            my_psi = _psi_publication_date(my_item)
            if my_psi and my_psi < my_snap:
                my_psi = None
            my_pub_raw = my_psi or (datetime.date.fromisoformat(my_snap) + datetime.timedelta(days=STATUTORY_LAG_DAYS[4])).isoformat()
            my_pub = _next_trading_day(conn, my_pub_raw)
            my_trad = _next_trading_day(conn, (datetime.date.fromisoformat(my_pub) + datetime.timedelta(days=1)).isoformat())
            my_pub_is_est = 0 if my_psi else 1
            my_pub_src = "psi" if my_psi else "estimated"
            my_ingest = _uuid.uuid4().hex[:12]
            conn.execute("""
                INSERT INTO fundamentals_pit
                    (ticker, snapshot_date, publication_date, tradable_date, filing_type,
                     publication_is_estimated, publication_source, ingest_id,
                     fiscal_year, fiscal_quarter,
                     eps, nav, pe_ratio, dividend_yield, net_profit_cr, source_hash, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(ticker, snapshot_date) DO UPDATE SET
                    publication_date         = excluded.publication_date,
                    tradable_date            = excluded.tradable_date,
                    filing_type              = excluded.filing_type,
                    publication_is_estimated = excluded.publication_is_estimated,
                    publication_source       = excluded.publication_source,
                    ingest_id                = excluded.ingest_id,
                    eps           = COALESCE(excluded.eps, fundamentals_pit.eps),
                    nav           = COALESCE(excluded.nav, fundamentals_pit.nav),
                    pe_ratio      = COALESCE(excluded.pe_ratio, fundamentals_pit.pe_ratio),
                    dividend_yield= COALESCE(excluded.dividend_yield, fundamentals_pit.dividend_yield),
                    net_profit_cr = COALESCE(excluded.net_profit_cr, fundamentals_pit.net_profit_cr),
                    source_hash   = excluded.source_hash
                WHERE COALESCE(fundamentals_pit.publication_source, '') != 'dse_disclosure'
            """, (
                parsed["ticker"], my_snap, my_pub, my_trad, "annual",
                my_pub_is_est, my_pub_src, my_ingest,
                my_year, 4,
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
                        snap_date = _month_end(pyear, pmonth)
                        if snap_date > observed_date:
                            continue
                        q_num = int(qk[1])
                        fiscal_yr = fiscal_year_of(snap_date, fye_month)
                        int_raw_str = json.dumps({"metric": metric_name, "period": pend_str, "eps": q_eps}, ensure_ascii=False)
                        int_hash = hashlib.sha256(int_raw_str.encode("utf-8")).hexdigest()[:16]
                        # Interim: pub = disclosure or snap + 45d (next trading day), tradable = next trading day after pub
                        int_disc = _psi_publication_date(interim) or _psi_publication_date(row)
                        if int_disc and int_disc < snap_date:
                            int_disc = None
                        if int_disc:
                            int_pub_raw = int_disc
                            int_pub_is_est = 0
                            int_pub_src = "psi"
                        else:
                            try:
                                int_pub_raw = (datetime.date.fromisoformat(snap_date) + datetime.timedelta(days=STATUTORY_LAG_DAYS.get(q_num, 45))).isoformat()
                            except Exception:
                                int_pub_raw = snap_date
                            int_pub_is_est = 1
                            int_pub_src = "estimated"
                        int_pub = _next_trading_day(conn, int_pub_raw)
                        int_trad = _next_trading_day(conn, (datetime.date.fromisoformat(int_pub) + datetime.timedelta(days=1)).isoformat())
                        int_ingest = _uuid.uuid4().hex[:12]

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
                                (ticker, snapshot_date, publication_date, tradable_date, filing_type,
                                 publication_is_estimated, publication_source, ingest_id,
                                 fiscal_year, fiscal_quarter,
                                 eps, source_hash, created_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                            ON CONFLICT(ticker, snapshot_date) DO UPDATE SET
                                publication_date         = excluded.publication_date,
                                tradable_date            = excluded.tradable_date,
                                filing_type              = excluded.filing_type,
                                publication_is_estimated = excluded.publication_is_estimated,
                                publication_source       = excluded.publication_source,
                                ingest_id                = excluded.ingest_id,
                                eps         = excluded.eps,
                                fiscal_year = excluded.fiscal_year,
                                fiscal_quarter = excluded.fiscal_quarter,
                                source_hash = excluded.source_hash
                            WHERE COALESCE(fundamentals_pit.publication_source, '') != 'dse_disclosure'
                        """, (
                            parsed["ticker"], snap_date, int_pub, int_trad, "interim",
                            int_pub_is_est, int_pub_src, int_ingest,
                            fiscal_yr, q_num,
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
        vol_val   = _to_int(rec.get("volume")) or 0
        val_val   = _to_float(rec.get("value")) or 0.0

        if high_val is not None and low_val is not None and high_val < low_val:
            log.warning(f"Data error {ticker} {date_val}: high({high_val}) < low({low_val}). Skipping.")
            continue

        # prices stores raw traded bars; corporate-action adjustment is applied at read time
        # (feature_store, precision_engine, backtester) so it must not be baked in here.
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

    idx_dsex = extract_index("DSEX")
    idx_ds30 = extract_index("DS30")
    idx_dses = extract_index("DSES")

    # Guard against DSE scraped table column shift (Market Cap > 50,000 leaking into DSEX)
    if idx_dsex is not None and idx_dsex > 50000.0:
        idx_dsex = extract_index("DSES")
        idx_dses = extract_index("DS30")
        idx_ds30 = extract_index("DGEN")

    # Sanity bounds & continuity check on DSEX (3,000 to 10,000 plausible band)
    if idx_dsex is not None:
        if idx_dsex < 3000.0 or idx_dsex > 10000.0:
            log.warning(f"DSEX level {idx_dsex} outside plausible band [3000, 10000] on {date_str}!")
        prev_dsex = conn.execute("SELECT dsex FROM market_summary WHERE dsex IS NOT NULL AND date < ? ORDER BY date DESC LIMIT 1", (date_str,)).fetchone()
        if prev_dsex and prev_dsex[0]:
            pct_chg = abs(idx_dsex - prev_dsex[0]) / prev_dsex[0]
            if pct_chg > 0.10:  # >10% move breaches exchange daily circuit limit
                log.warning(f"DSEX single-day jump {pct_chg:.1%} breaches 10% circuit limit between {date_str} and prior session!")

    conn.execute("""
        INSERT OR REPLACE INTO market_summary (date, dsex, ds30, dses, raw_data)
        VALUES (?,?,?,?,?)
    """, (
        date_str,
        idx_dsex,
        idx_ds30,
        idx_dses,
        json.dumps(raw, ensure_ascii=False),
    ))


# ── Orchestration ─────────────────────────────────────────────────────────────


def _infer_instrument_sector(ticker: str, ticker_sector: dict) -> str:
    t = ticker.upper()
    if t.endswith("MF") or "1STMF" in t or "IMF" in t:
        return "Mutual Funds"
    if "BOND" in t or t.startswith("TB") or "SUKUK" in t:
        return "Bonds"
    if t.endswith("BANK") or t in ("ABBANK", "ALARABANK", "BANKASIA", "BRACBANK", "CITYBANK", "DHAKABANK", "DUTCHBANGL", "EBL", "EXIMBANK", "FIRSTSBANK", "IFIC", "ISLAMIBANK", "JAMUNABANK", "MERCANBANK", "MIDASFIN", "MTB", "NBL", "NCCBANK", "NRBBANK", "ONEBANKLTD", "PREMIERBAN", "PRIMEBANK", "PUBALIBANK", "RUPALIBANK", "SBACBANK", "SIBL", "SOUTHEASTB", "STANDBANKL", "TRUSTBANK", "UFSBANK", "UNIONBANK", "UTTARABANK"):
        return "Banking"
    if t.endswith("INS") or "INSUR" in t:
        return "Insurance"
    if t.endswith("TEX") or "SPINN" in t or "TEXTILE" in t or "COT" in t or "SYNTH" in t or "KNIT" in t:
        return "Textile"
    if t.endswith("PHARMA") or "PHARM" in t or "CHEM" in t or "LAB" in t:
        return "Pharmaceuticals"
    if t.endswith("CEM") or "CEMENT" in t:
        return "Cement"
    if "POWER" in t or "GEN" in t or "OIL" in t or "GAS" in t or "PETRO" in t:
        return "Fuel_Power"
    if "FOOD" in t or "FEED" in t or "AGRO" in t or "SUGAR" in t or "TEA" in t:
        return "Food_Beverage"
    if "TEL" in t or "NET" in t or "TECH" in t or "SYS" in t or "INFO" in t:
        return "IT"
    if "ENG" in t or "STEEL" in t or "AUTO" in t or "ALUM" in t:
        return "Engineering"
    if ticker in ticker_sector:
        return ticker_sector[ticker]
    return "Miscellaneous"


def _ensure_company_master_record(conn: sqlite3.Connection, ticker: str, rec: dict, ticker_sector: dict):
    existing = conn.execute("SELECT ticker FROM companies WHERE ticker=?", (ticker,)).fetchone()
    if not existing:
        sec = _infer_instrument_sector(ticker, ticker_sector)
        cat = str(rec.get("category") or "").strip() or None
        name = str(rec.get("name") or ticker).strip()
        conn.execute("""
            INSERT OR IGNORE INTO companies (ticker, name, sector, category, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (ticker, name, sec, cat, datetime.datetime.utcnow().isoformat()))

STALE_SNAPSHOT_MATCH_RATIO = 0.9


def stale_snapshot_reason(conn: sqlite3.Connection, date_str: str, records: list) -> str | None:
    """
    Non-None when a full-market snapshot repeats the previous stored session bar-for-bar
    (feeds and caches replay the last session on holidays), i.e. no real session happened.
    """
    prev = conn.execute("SELECT MAX(date) FROM prices WHERE date < ?", (date_str,)).fetchone()[0]
    if prev:
        prev_bars = {r[0]: (r[1], r[2]) for r in conn.execute(
            "SELECT ticker, close, volume FROM prices WHERE date = ?", (prev,))}
        same = total = 0
        for rec in records:
            t = str(rec.get("ticker") or rec.get("symbol") or rec.get("code") or "").strip()
            if t not in prev_bars:
                continue
            total += 1
            close = _to_float(rec.get("close") or rec.get("ltp"))
            vol = _to_int(rec.get("volume")) or 0
            pc, pv = prev_bars[t]
            if close is not None and pc is not None and abs(close - pc) < 1e-9 and vol == (pv or 0):
                same += 1
        if total >= 50 and same / total >= STALE_SNAPSHOT_MATCH_RATIO:
            return f"stale snapshot: {same}/{total} bars identical to previous session {prev}"
    return None


def snapshot_rejection_reason(conn: sqlite3.Connection, date_str: str, records: list) -> str | None:
    """
    Reason to refuse a live snapshot for date_str, or None to accept it. A fresh snapshot on a day
    the calendar marks closed is accepted and the calendar corrected: only a real session prints new bars.
    """
    stale = stale_snapshot_reason(conn, date_str, records)
    if stale:
        return stale
    cal = conn.execute("SELECT is_trading_day FROM trading_calendar WHERE date = ?", (date_str,)).fetchone()
    if cal is not None and cal[0] == 0:
        log.warning(f"{date_str} is marked closed in trading_calendar but has fresh prints; marking it a trading day.")
        conn.execute("""UPDATE trading_calendar SET is_trading_day = 1, session_type = 'makeup_session',
                        notes = 'Corrected: fresh exchange prints observed' WHERE date = ?""", (date_str,))
    elif cal is None:
        conn.execute("""INSERT OR IGNORE INTO trading_calendar (date, is_trading_day, session_type, notes)
                        VALUES (?, 1, 'regular', 'Added from observed exchange prints')""", (date_str,))
    return None


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
    if isinstance(all_prices, list) and all_prices:
        reject = snapshot_rejection_reason(conn, date_str, all_prices)
        if reject:
            log.error(f"Refusing price snapshot for {date_str}: {reject}")
            all_prices = []
    if all_prices:
        if isinstance(all_prices, list):
            for rec in all_prices:
                ticker = str(rec.get("ticker") or rec.get("symbol") or rec.get("code") or "").strip()
                if not ticker:
                    continue
                insert_prices(conn, ticker, [rec], date_str)
                _ensure_company_master_record(conn, ticker, rec, ticker_sector)
        from provenance import new_ingest, stamp_unattributed
        raw_path = RAW_DIR / date_str / "all_prices.json"
        if conn.execute("SELECT 1 FROM prices WHERE source IS NULL LIMIT 1").fetchone():
            stamp_unattributed(conn, new_ingest(conn, "dse_live_snapshot", str(raw_path), raw=raw_path), "dse_live_snapshot", date_str)
        conn.commit()
        log.info(f"Inserted {len(all_prices) if isinstance(all_prices, list) else '?'} price snapshots")

    # Historical prices per ticker
    historical = load_raw("historical_prices", date_str)
    if historical:
        for ticker, records in historical.items():
            insert_prices(conn, ticker, records, date_str)
        from provenance import new_ingest, stamp_unattributed
        raw_path = RAW_DIR / date_str / "historical_prices.json"
        if conn.execute("SELECT 1 FROM prices WHERE source IS NULL LIMIT 1").fetchone():
            stamp_unattributed(conn, new_ingest(conn, "dse_historical_scrape", str(raw_path), raw=raw_path), "dse_historical_scrape")
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
                c = str(rec.get("category") or "").strip()
                if t and c:
                    cat_map[t] = c

        for ticker, raw_fund in fundamentals.items():
            parsed = parse_fundamentals_row(ticker, raw_fund)
            sector = ticker_sector.get(ticker, "Unknown")
            category = cat_map.get(ticker)
            upsert_company(conn, ticker, sector, category, parsed)
            upsert_fundamentals(conn, parsed, raw_fund, date_str)
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

    # Official DSE PSI Disclosures & Corporate Actions
    psi_news = load_raw("dse_psi_news", date_str)
    if psi_news:
        try:
            import corporate_action_processor
            res = corporate_action_processor.parse_and_record_dse_psi(psi_news, conn=conn)
            log.info(f"DSE PSI Disclosures parsed: {res.get('total_parsed', 0)} corporate actions updated")
        except Exception as e:
            log.warning(f"Failed to parse DSE PSI disclosures in processor: {e}")

    conn.close()
    log.info(f"=== Processing complete: {date_str} ===")


def get_ticker_data(ticker: str, days: int = 365) -> dict:
    """
    Fetch all stored data for a ticker.
    Anchor lookback to latest price date in DB (not wall-clock today).
    Pass calendar days covering SMA200+: weekly/monthly~400, yearly~2000.
    """
    conn = get_db()
    asof_row = conn.execute(
        "SELECT MAX(date) FROM prices WHERE ticker=?", (ticker,)
    ).fetchone()
    asof = asof_row[0] if asof_row and asof_row[0] else datetime.date.today().isoformat()
    try:
        asof_d = datetime.date.fromisoformat(asof[:10])
    except Exception:
        asof_d = datetime.date.today()
    since = (asof_d - datetime.timedelta(days=days)).isoformat()

    prices = conn.execute(
        "SELECT * FROM prices WHERE ticker=? AND date>=? ORDER BY date ASC",
        (ticker, since)
    ).fetchall()

    # Query Point-in-Time fundamentals published and tradable by asof date
    pit_fundamentals = conn.execute(
        """
        SELECT * FROM fundamentals_pit
        WHERE ticker=? AND tradable_date <= ? AND publication_date <= ?
        ORDER BY tradable_date DESC, snapshot_date DESC LIMIT 12
        """,
        (ticker, asof, asof)
    ).fetchall()
    fundamentals = pit_fundamentals if pit_fundamentals else conn.execute(
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
