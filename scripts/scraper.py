"""
DSE Scraper — collects price, fundamentals, and news from DSE using bdshare library + multi-source news.
Outputs raw JSON files to data/raw/YYYY-MM-DD/

Data sources:
  Prices / OHLCV  : bdshare library (wraps dse.com.bd + old.dsebd.org with fallback)
  Fundamentals    : bdshare + dse.com.bd company page
  Annual reports  : annual_report_scraper.py (separate module)
  News            : DSE PSI page, TBS News, Daily Star, Financial Express BD, bdnews24
"""

import json
import time
import logging
import datetime
import requests
import re
from pathlib import Path
from bs4 import BeautifulSoup

# ── bdshare import ────────────────────────────────────────────────────────────
try:
    from bdshare import BDShare, get_current_trade_data, get_historical_data
    BDSHARE_OK = True
except ImportError:
    BDSHARE_OK = False
    logging.warning("bdshare not installed. Run: pip install bdshare")

# ── Config ────────────────────────────────────────────────────────────────────

BASE_DIR     = Path(__file__).resolve().parent.parent
RAW_DIR      = BASE_DIR / "data" / "raw"
CONFIG_DIR   = BASE_DIR / "config"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
SESSION = requests.Session()
SESSION.trust_env = False
SESSION.headers.update(HEADERS)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dse_scraper")

# ── News sources — verified URLs and CSS selectors ───────────────────────────

NEWS_SOURCES = [
    {
        "name": "DSE_News",
        "url": "https://www.dse.com.bd/news",
        "type": "links",
        "selector": "h2 a, h3 a, a[href*='/news/'], .card a",
        "base_url": "https://www.dse.com.bd",
    },
    {
        "name": "TBS_News",
        "url": "https://www.tbsnews.net/economy/stocks",
        "type": "links",
        "selector": "h3.title a, h2.title a, .card-title a, a[href*='/stocks/']",
        "base_url": "https://www.tbsnews.net",
    },
    {
        "name": "Daily_Star",
        "url": "https://www.thedailystar.net/business",
        "type": "links",
        "selector": "h3 a, h2 a, .card-title a, .title a",
        "base_url": "https://www.thedailystar.net",
    },
    {
        "name": "Financial_Express",
        "url": "https://www.thefinancialexpress.com.bd/stock",
        "type": "links",
        "selector": "article h2 a, h3.entry-title a, .post-title a",
        "base_url": "https://www.thefinancialexpress.com.bd",
    },
    {
        "name": "bdnews24_Business",
        "url": "https://bdnews24.com/business",
        "type": "links",
        "selector": "h1 a, h2 a, .entry-title a",
        "base_url": "https://bdnews24.com",
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def today_str() -> str:
    return datetime.date.today().isoformat()


def save_raw(category: str, data: dict | list, date_str: str = None):
    date_str = date_str or today_str()
    out_dir = RAW_DIR / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{category}.json"
    if not data and out_file.exists():
        log.warning(f"Empty data received for {category}; preserving existing {out_file}")
        return
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info(f"Saved {out_file}")


def http_get(url: str, retries: int = 3, delay: float = 2.0) -> requests.Response | None:
    for attempt in range(retries):
        try:
            resp = SESSION.get(url, timeout=20)
            resp.raise_for_status()
            return resp
        except Exception as e:
            log.warning(f"Attempt {attempt+1} failed [{url}]: {e}")
            time.sleep(delay * (attempt + 1))
    log.error(f"All retries failed: {url}")
    return None


def load_config(name: str) -> dict:
    with open(CONFIG_DIR / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def get_company_name(ticker: str, names: dict) -> str:
    return names.get(ticker, ticker)


# ── Market Summary ────────────────────────────────────────────────────────────

def scrape_market_summary() -> dict:
    """Fetch DSEX / DS30 / DSES via bdshare. Falls back to HTTP scrape."""
    if BDSHARE_OK:
        try:
            with BDShare() as bd:
                summary = bd.get_market_summary()
                if isinstance(summary, dict):
                    return summary
                # DataFrame returned
                return summary.to_dict(orient="records") if hasattr(summary, "to_dict") else {}
        except Exception as e:
            log.warning(f"bdshare market summary failed: {e}. Falling back to scrape.")

    # HTTP fallback — DSE main page index table
    resp = http_get("https://www.dse.com.bd/")
    if not resp:
        return {}
    soup = BeautifulSoup(resp.text, "html.parser")
    result = {}
    try:
        for row in soup.select("table tr"):
            cols = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cols) >= 4 and any(k in cols[0].upper() for k in ["DSEX", "DS30", "DSES"]):
                result[cols[0]] = {"value": cols[1], "change": cols[2], "change_pct": cols[3]}
    except Exception as e:
        log.warning(f"Market summary scrape failed: {e}")
    return result


# ── All Share Prices ──────────────────────────────────────────────────────────

def scrape_all_prices() -> list[dict]:
    """
    Fetch live prices for all DSE instruments via bdshare.
    Returns list of dicts with: ticker, category, close, high, low, open, volume, value, change, change_pct.
    """
    if BDSHARE_OK:
        try:
            df = get_current_trade_data()
            if df is not None and not df.empty:
                records = df.to_dict(orient="records")
                log.info(f"bdshare: fetched {len(records)} live prices")
                return records
        except Exception as e:
            log.warning(f"bdshare get_current_trade_data failed: {e}. Falling back to scrape.")

    # HTTP fallback — DSE price scroll page
    resp = http_get("https://www.dse.com.bd/latest_share_price_scroll_by_value.php")
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    prices = []
    for row in soup.select("table tbody tr"):
        cols = [td.get_text(strip=True) for td in row.find_all("td")]
        if len(cols) < 9:
            continue
        try:
            prices.append({
                "ticker":     cols[1].strip(),
                "category":   cols[2].strip(),
                "close":      _to_float(cols[3]),
                "high":       _to_float(cols[4]),
                "low":        _to_float(cols[5]),
                "open":       _to_float(cols[6]),
                "change":     _to_float(cols[7]),
                "change_pct": _to_float(cols[8].replace("%", "")),
                "volume":     _to_int(cols[9]) if len(cols) > 9 else None,
                "value":      _to_float(cols[10]) if len(cols) > 10 else None,
            })
        except Exception as e:
            log.debug(f"Price row parse error: {e}")
    log.info(f"Scraped {len(prices)} prices via HTTP fallback")
    return prices


# ── Historical OHLCV ──────────────────────────────────────────────────────────

def scrape_historical(ticker: str, from_date: str, to_date: str) -> list[dict]:
    """
    Fetch historical OHLCV via bdshare. Falls back to dse.com.bd AJAX endpoint.
    from_date / to_date: 'YYYY-MM-DD'
    """
    if BDSHARE_OK:
        try:
            df = get_historical_data(from_date, to_date, ticker)
            if df is not None and not df.empty:
                if "date" not in df.columns:
                    df = df.reset_index()
                records = df.to_dict(orient="records")
                # Normalize column names to lowercase
                records = [{k.lower(): v for k, v in r.items()} for r in records]
                log.info(f"bdshare: {len(records)} historical records for {ticker}")
                return records
        except Exception as e:
            log.warning(f"bdshare historical failed for {ticker}: {e}. Falling back.")

    # HTTP fallback
    url = (
        f"https://www.dse.com.bd/ajax_get_instrument_price.php"
        f"?instrument={ticker}&start={from_date}&end={to_date}"
    )
    resp = http_get(url)
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    records = []
    for row in soup.select("table tbody tr"):
        cols = [td.get_text(strip=True) for td in row.find_all("td")]
        if len(cols) < 7:
            continue
        try:
            records.append({
                "date":   cols[0],
                "open":   _to_float(cols[1]),
                "high":   _to_float(cols[2]),
                "low":    _to_float(cols[3]),
                "close":  _to_float(cols[4]),
                "volume": _to_int(cols[5]),
                "value":  _to_float(cols[6]),
            })
        except Exception as e:
            log.debug(f"Historical row parse error {ticker}: {e}")
    log.info(f"HTTP fallback: {len(records)} historical records for {ticker}")
    return records


# ── Company Fundamentals ──────────────────────────────────────────────────────

def scrape_fundamentals(ticker: str) -> dict:
    """
    Scrape fundamentals from modern DSE company page:
      URL: https://www.dse.com.bd/company/{ticker}
    Extracts P/E, EPS, NAV, Market Cap, shareholding patterns (sponsor, govt, inst, public),
    paid-up capital, free-float directly from Next.js server components state.
    Falls back to legacy displayCompany.php if needed.
    """
    data = {"ticker": ticker}

    # 1. Primary: Modern DSE URL (Next.js SSR)
    url = f"https://www.dse.com.bd/company/{ticker}"
    resp = http_get(url)
    if resp and resp.status_code == 200:
        html = resp.text
        chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*"((?:\\.|[^"\\])*)"\]\)', html)
        if chunks:
            combined = ""
            for c in chunks:
                try:
                    combined += bytes(c, "utf-8").decode("unicode_escape", errors="ignore")
                except Exception:
                    combined += c
        else:
            combined = html

        # Exact company profile block (name, sector, category)
        profile_match = re.search(
            rf'"{ticker}","name":"([^"]+)","sector":"([^"]+)","board":"([^"]+)","category":"([^"]+)"',
            combined
        )
        if profile_match:
            data["name"] = profile_match.group(1)
            data["sector"] = profile_match.group(2)
            data["board"] = profile_match.group(3)
            data["category"] = profile_match.group(4)

        field_patterns = {
            "price": r'"price"\s*:\s*([\d\.]+)',
            "market_cap": r'"marketCap"\s*:\s*([\d\.]+)',
            "pe": r'"pe"\s*:\s*([\d\.]+)',
            "eps": r'"eps"\s*:\s*([\d\.]+)',
            "nav": r'"nav"\s*:\s*([\d\.]+)',
            "book_value": r'"bookValue"\s*:\s*([\d\.]+)',
            "dividend_yield": r'"dividendYield"\s*:\s*([\d\.]+)',
            "free_float_pct": r'"freeFloat"\s*:\s*([\d\.]+)',
            "paid_up_capital": r'"paidUpCapital"\s*:\s*([\d\.]+)',
            "authorized_capital": r'"authorizedCapital"\s*:\s*([\d\.]+)',
        }
        for field, pat in field_patterns.items():
            found = re.findall(pat, combined)
            if found:
                data[field] = found[0]

        # Category fallback
        if "category" not in data:
            cat_match = re.findall(r'"category"\s*:\s*"([A-Z])"', combined)
            if cat_match:
                data["category"] = cat_match[0]

        # Shareholding patterns
        sp_matches = re.findall(r'"sponsor"\s*:\s*([\d\.]+)', combined)
        if sp_matches:
            data["sponsor_director_holding_pct"] = sp_matches[-1]

        inst_matches = re.findall(r'"institution"\s*:\s*([\d\.]+)', combined)
        if inst_matches:
            data["institutional_holding_pct"] = inst_matches[-1]

        pub_matches = re.findall(r'"public"\s*:\s*([\d\.]+)', combined)
        if pub_matches:
            data["public_holding_pct"] = pub_matches[-1]

        govt_matches = re.findall(r'"government"\s*:\s*([\d\.]+)', combined)
        if govt_matches:
            data["govt_holding_pct"] = govt_matches[-1]

        # Shareholding pattern history for manipulation tracking
        sp_hist = re.search(r'"sharePattern"\s*:\s*(\[.*?\])(?:,"dividendHistory"|,"creditRating")', combined)
        if sp_hist:
            try:
                data["share_pattern_history"] = json.loads(sp_hist.group(1))
            except Exception:
                pass

        # Loan Status (Short-Term and Long-Term Debt in Millions BDT)
        idx_loan = combined.find('"loanStatus"')
        st_loan, lt_loan = 0.0, 0.0
        if idx_loan != -1:
            loan_chunk = combined[idx_loan:idx_loan+140]
            st_m = re.search(r'"shortTerm"\s*:\s*([\d\.]+)', loan_chunk)
            lt_m = re.search(r'"longTerm"\s*:\s*([\d\.]+)', loan_chunk)
            st_loan = float(st_m.group(1)) if st_m else 0.0
            lt_loan = float(lt_m.group(1)) if lt_m else 0.0
            data["short_term_loan_mn"] = st_loan
            data["long_term_loan_mn"] = lt_loan
            data["total_loan_mn"] = st_loan + lt_loan

        # Dividend History (Multi-year cash dividend track record)
        div_history = []
        div_matches = re.findall(r'\{"year":(\d{4}),"cash":([\d\.]+),"stock":([\d\.]+),"yieldPct":([\d\.]+)', combined)
        for ym, cm, sm, ym_pct in div_matches:
            div_history.append({
                "year": int(ym),
                "cash": float(cm),
                "stock": float(sm),
                "yield_pct": float(ym_pct)
            })
        if div_history:
            data["dividend_history"] = div_history

        # Multi-Year Financials (Historical Audited EPS, NAV, Profit, PE)
        m_my = re.search(r'"multiYearFinancials"\s*:\s*(\[.*?\])\s*,\s*"interimFinancials"', combined)
        if m_my:
            try:
                data["multi_year_financials"] = json.loads(m_my.group(1))
            except Exception as e:
                log.debug(f"multiYearFinancials json parse error {ticker}: {e}")

        # Interim Financials (Quarterly EPS Q1, Q2, Q3)
        m_int = re.search(r'"interimFinancials"\s*:\s*(\{.*?\})\s*,\s*"peTrend"', combined)
        if m_int:
            try:
                data["interim_financials"] = json.loads(m_int.group(1))
            except Exception as e:
                log.debug(f"interimFinancials json parse error {ticker}: {e}")

        # Calculate empirical Debt/Equity and Long-Term Debt/Equity
        nav_val = _to_float(data.get("nav") or data.get("book_value"))
        puc_val = _to_float(data.get("paid_up_capital"))
        if nav_val and puc_val and nav_val > 0 and puc_val > 0:
            num_shares = puc_val / 10.0
            equity_mn = (num_shares * nav_val) / 1e6
            if equity_mn > 0:
                data["equity_mn"] = round(equity_mn, 2)
                data["debt_equity"] = round((st_loan + lt_loan) / equity_mn, 3)
                data["long_term_debt_equity"] = round(lt_loan / equity_mn, 3)

        if len(data) > 5:
            log.info(f"Modern DSE scrape success: {ticker} ({len(data)} fields)")
            return data

    # 2. Fallback: Legacy displayCompany.php endpoint
    log.warning(f"Falling back to legacy DSE scraper for {ticker}...")
    leg_resp = http_get(f"https://www.dse.com.bd/displayCompany.php?name={ticker}")
    if leg_resp:
        soup = BeautifulSoup(leg_resp.text, "html.parser")
        try:
            for row in soup.select("table.table-bordered tr"):
                cells = row.find_all(["th", "td"])
                if len(cells) == 2:
                    key = (cells[0].get_text(strip=True)
                           .lower()
                           .replace(" ", "_")
                           .replace("/", "_")
                           .replace("(", "")
                           .replace(")", ""))
                    val = cells[1].get_text(strip=True)
                    data[key] = val
        except Exception as e:
            log.warning(f"Legacy fundamentals parse error {ticker}: {e}")

    log.info(f"Fundamentals {ticker}: {len(data)} fields")
    return data


# ── News Scraper ──────────────────────────────────────────────────────────────

def scrape_news(ticker: str = None, max_per_source: int = 15) -> list[dict]:
    """
    Scrapes all NEWS_SOURCES. Matches articles by ticker or company full name.
    Deduplicates by headline.
    """
    company_names = {}
    try:
        company_names = load_config("company_names")
    except Exception:
        pass

    company_name = get_company_name(ticker, company_names).lower() if ticker else ""
    ticker_lower = ticker.lower() if ticker else ""

    def is_relevant(title: str) -> bool:
        if not ticker:
            return True
        t = title.lower()
        return ticker_lower in t or (company_name and company_name in t)

    articles = []
    seen_headlines = set()

    for src in NEWS_SOURCES:
        try:
            resp = http_get(src["url"])
            if not resp:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")

            if src["type"] == "table":
                rows = soup.select(src["row_selector"])
                for row in rows[:max_per_source]:
                    cols = [td.get_text(strip=True) for td in row.find_all("td")]
                    if len(cols) <= max(src["title_col"], src["date_col"]):
                        continue
                    title = cols[src["title_col"]]
                    if not title or not is_relevant(title):
                        continue
                    if title in seen_headlines:
                        continue
                    seen_headlines.add(title)
                    link_tag = row.find("a")
                    url_val = ""
                    if link_tag and link_tag.get("href"):
                        url_val = link_tag["href"]
                        if url_val.startswith("/"):
                            url_val = "https://www.dse.com.bd" + url_val
                    articles.append({
                        "source":  src["name"],
                        "title":   title,
                        "url":     url_val,
                        "date":    cols[src["date_col"]] if src["date_col"] < len(cols) else today_str(),
                        "ticker":  ticker or "",
                    })

            elif src["type"] == "links":
                for tag in soup.select(src["selector"])[:max_per_source]:
                    title = tag.get_text(strip=True)
                    if not title or not is_relevant(title):
                        continue
                    if title in seen_headlines:
                        continue
                    seen_headlines.add(title)
                    href = tag.get("href", "")
                    if href.startswith("/"):
                        href = src.get("base_url", "") + href
                    articles.append({
                        "source":  src["name"],
                        "title":   title,
                        "url":     href,
                        "date":    today_str(),
                        "ticker":  ticker or "",
                    })

        except Exception as e:
            log.warning(f"News source {src['name']} failed: {e}")

    log.info(f"News scraped: {len(articles)} articles (ticker={ticker})")
    return articles


# ── Orchestration ─────────────────────────────────────────────────────────────

def run_full_scrape(tickers: list[str] = None, historical_years: int = 5):
    """
    Full scrape: market summary + all prices + per-ticker fundamentals + historical + news.
    If tickers=None, loads all sector tickers from config.
    """
    date_str = today_str()
    log.info(f"=== Full scrape start: {date_str} ===")

    sectors = load_config("sectors")

    if tickers is None:
        tickers = []
        for sd in sectors["sectors"].values():
            tickers.extend(sd["top_tickers"])
        tickers = list(dict.fromkeys(tickers))

    # Market summary
    save_raw("market_summary", scrape_market_summary(), date_str)

    # All live prices
    save_raw("all_prices", scrape_all_prices(), date_str)

    # Per-ticker: fundamentals + historical + news
    fundamentals = {}
    historical   = {}
    news         = {}

    to_date   = date_str
    from_date = (datetime.date.today() - datetime.timedelta(days=365 * historical_years)).isoformat()

    # Scrape all news sources once globally, then filter per ticker in memory
    log.info("Fetching market-wide and sector news...")
    all_scraped_news = scrape_news(ticker=None, max_per_source=30)
    save_raw("market_news", all_scraped_news, date_str)

    company_names = {}
    try:
        company_names = load_config("company_names")
    except Exception:
        pass

    for i, ticker in enumerate(tickers):
        log.info(f"[{i+1}/{len(tickers)}] Processing {ticker}...")
        fundamentals[ticker] = scrape_fundamentals(ticker)
        historical[ticker]   = scrape_historical(ticker, from_date, to_date)
        
        # Filter news for this ticker in memory
        c_name = get_company_name(ticker, company_names).lower()
        t_code = ticker.lower()
        news[ticker] = [
            n for n in all_scraped_news
            if t_code in n["title"].lower() or (c_name and c_name in n["title"].lower())
        ]
        time.sleep(0.5)

    save_raw("fundamentals", fundamentals, date_str)
    save_raw("historical_prices", historical, date_str)
    save_raw("news", news, date_str)

    log.info(f"=== Full scrape complete: {date_str} ===")
    return date_str


def run_price_only_scrape():
    """Daily price & macro news refresh."""
    date_str = today_str()
    save_raw("market_summary", scrape_market_summary(), date_str)
    save_raw("all_prices", scrape_all_prices(), date_str)
    try:
        # Scrape global macro news headlines daily
        news_articles = scrape_all_news()
        save_raw("market_news", news_articles, date_str)
    except Exception as e:
        log.warning(f"Daily news scrape skipped: {e}")
    log.info(f"Price & news scrape done: {date_str}")
    return date_str


# ── Utils ─────────────────────────────────────────────────────────────────────

def _to_float(s) -> float | None:
    try:
        return float(str(s).replace(",", "").replace("%", "").strip())
    except Exception:
        return None


def _to_int(s) -> int | None:
    try:
        return int(str(s).replace(",", "").strip())
    except Exception:
        return None


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    if mode == "price":
        run_price_only_scrape()
    elif mode == "full":
        run_full_scrape()
    else:
        run_full_scrape(tickers=sys.argv[1:])
