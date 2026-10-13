"""
DSE Annual Report Scraper — downloads and parses audited financial data from DSE disclosures.

Sources:
  - DSE company financial data page: dse.com.bd/company_financial_data.php?instrument=TICKER
  - DSE disclosure/PSI page per company
  - Company's own investor relations page (if configured)
  - BSEC filing search: sec.gov.bd (manual navigation — noted as limitation)

Output: data/raw/annual_reports/{TICKER}/{YEAR}/
  - financial_summary.json  ← parsed key figures
  - report.pdf              ← downloaded PDF (if available)
  - parsed_tables.json      ← tables extracted from PDF via pdfplumber
"""

import json
import logging
import datetime
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

try:
    import pdfplumber
    PDFPLUMBER_OK = True
except ImportError:
    PDFPLUMBER_OK = False

BASE_DIR   = Path(__file__).resolve().parent.parent
RAW_DIR    = BASE_DIR / "data" / "raw" / "annual_reports"
CONFIG_DIR = BASE_DIR / "config"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
SESSION = requests.Session()
SESSION.trust_env = False
SESSION.headers.update(HEADERS)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("annual_report_scraper")


# ── Helpers ───────────────────────────────────────────────────────────────────

def http_get(url: str, retries: int = 3, delay: float = 2.0) -> requests.Response | None:
    for attempt in range(retries):
        try:
            resp = SESSION.get(url, timeout=30)
            resp.raise_for_status()
            return resp
        except Exception as e:
            log.warning(f"Attempt {attempt+1} failed [{url}]: {e}")
            time.sleep(delay * (attempt + 1))
    return None


def save_json(path: Path, data: dict | list):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _to_float(v) -> float | None:
    try:
        return float(str(v).replace(",", "").replace("৳", "").replace("Tk", "").strip())
    except Exception:
        return None


# ── DSE Financial Data Page ───────────────────────────────────────────────────

def scrape_dse_financial_data(ticker: str) -> dict:
    """
    Fetch structured financial data from DSE company page.
    URL: https://www.dse.com.bd/company_financial_data.php?instrument=TICKER
    Returns dict of financial figures.
    """
    url  = f"https://www.dse.com.bd/company_financial_data.php?instrument={ticker}"
    resp = http_get(url)
    if not resp:
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")
    data = {"ticker": ticker, "source": "dse_financial_data_page"}

    # Parse all tables — extract label:value pairs
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["th", "td"])
            if len(cells) == 2:
                key = cells[0].get_text(strip=True)
                val = cells[1].get_text(strip=True)
                if key and val:
                    norm_key = key.lower().replace(" ", "_").replace("/", "_")
                    data[norm_key] = val
            elif len(cells) > 2:
                # Multi-year table — capture years as separate records
                headers = [c.get_text(strip=True) for c in cells]
                if any(re.search(r"20\d{2}", h) for h in headers):
                    data[f"_multi_year_headers"] = headers

    log.info(f"DSE financial data {ticker}: {len(data)} fields")
    return data


# ── DSE Disclosure / PSI Links ────────────────────────────────────────────────

def get_disclosure_links(ticker: str, max_links: int = 10) -> list[dict]:
    """
    Scrapes disclosure/PSI announcements for a ticker from DSE.
    Returns list of {date, title, url} dicts.
    """
    url  = f"https://www.dse.com.bd/displayCompany.php?name={ticker}"
    resp = http_get(url)
    if not resp:
        return []

    soup  = BeautifulSoup(resp.text, "html.parser")
    links = []

    # DSE disclosure links appear in tables on company page
    for row in soup.select("table.table tbody tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        title_cell = cells[1] if len(cells) > 1 else cells[0]
        link_tag   = title_cell.find("a")
        date_cell  = cells[0]

        title = title_cell.get_text(strip=True)
        date  = date_cell.get_text(strip=True)
        href  = ""

        if link_tag and link_tag.get("href"):
            href = link_tag["href"]
            if href.startswith("/"):
                href = "https://www.dse.com.bd" + href

        if title and any(kw in title.lower() for kw in
                         ["annual report", "financial statement", "quarterly", "dividend", "eps"]):
            links.append({"date": date, "title": title, "url": href})
            if len(links) >= max_links:
                break

    log.info(f"Found {len(links)} disclosure links for {ticker}")
    return links


# ── PDF Download ──────────────────────────────────────────────────────────────

def download_pdf(url: str, save_path: Path) -> bool:
    """Download a PDF from url. Returns True on success."""
    if not url or not url.lower().endswith(".pdf"):
        return False

    resp = http_get(url)
    if not resp:
        return False

    content_type = resp.headers.get("Content-Type", "")
    if "pdf" not in content_type.lower() and not url.endswith(".pdf"):
        log.warning(f"URL does not appear to be a PDF: {url}")
        return False

    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(resp.content)
    log.info(f"Downloaded PDF: {save_path}")
    return True


# ── PDF Parser ────────────────────────────────────────────────────────────────

def parse_pdf_financials(pdf_path: Path) -> dict:
    """
    Extract key financial tables from annual report PDF using pdfplumber.
    Looks for income statement, balance sheet, and cash flow tables.
    Returns dict of extracted figures.
    """
    if not PDFPLUMBER_OK:
        log.warning("pdfplumber not installed. Cannot parse PDFs. Run: pip install pdfplumber")
        return {}

    if not pdf_path.exists():
        return {}

    extracted = {"source": str(pdf_path), "tables": []}

    # Keywords to find relevant pages
    target_keywords = [
        "revenue", "profit", "eps", "earnings per share",
        "net asset", "nav", "dividend", "total assets",
        "shareholders equity", "retained earnings",
        "cash flow from operation",
    ]

    # Financial patterns
    money_pattern = re.compile(r"[\d,]+\.?\d*")

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page_num, page in enumerate(pdf.pages[:80]):  # limit to 80 pages
                text = page.extract_text() or ""
                text_lower = text.lower()

                if not any(kw in text_lower for kw in target_keywords):
                    continue

                # Extract tables from this page
                tables = page.extract_tables()
                for table in tables:
                    if not table or len(table) < 2:
                        continue

                    # Convert table to clean dict
                    headers = [str(h).strip() if h else "" for h in table[0]]
                    table_data = []
                    for row in table[1:]:
                        if not row:
                            continue
                        row_dict = {}
                        for i, cell in enumerate(row):
                            key = headers[i] if i < len(headers) else f"col_{i}"
                            row_dict[key] = str(cell).strip() if cell else ""
                        table_data.append(row_dict)

                    if table_data:
                        extracted["tables"].append({
                            "page": page_num + 1,
                            "rows": table_data[:50],  # cap at 50 rows
                        })

                # Also parse key figures from text directly
                for line in text.split("\n"):
                    line_lower = line.lower()
                    for kw in target_keywords:
                        if kw in line_lower:
                            nums = money_pattern.findall(line)
                            if nums:
                                clean_kw = kw.replace(" ", "_")
                                extracted[clean_kw] = nums[-1]  # last number on line

        log.info(f"PDF parsed: {len(extracted['tables'])} tables from {pdf_path.name}")
    except Exception as e:
        log.error(f"PDF parse error {pdf_path}: {e}")

    return extracted


# ── Key Figure Extractor ──────────────────────────────────────────────────────

def extract_key_figures(parsed: dict) -> dict:
    """
    Flatten parsed PDF data into canonical financial metrics.
    """
    figures = {}

    # Direct text extractions
    field_map = {
        "revenue":             ["revenue", "net_sales", "total_revenue", "turnover"],
        "net_profit":          ["profit", "net_income", "profit_after_tax"],
        "eps":                 ["earnings_per_share", "eps"],
        "nav_per_share":       ["net_asset", "nav", "book_value_per_share"],
        "cash_flow_from_operation": ["cash_flow_from_operation", "operating_cash"],
        "total_assets":        ["total_assets"],
        "shareholders_equity": ["shareholders_equity", "equity"],
    }

    for canonical, aliases in field_map.items():
        for alias in aliases:
            if alias in parsed and parsed[alias]:
                val = str(parsed[alias]).replace(",", "")
                try:
                    figures[canonical] = float(val)
                    break
                except Exception:
                    pass

    # Try to extract from tables
    for table_entry in parsed.get("tables", []):
        for row in table_entry.get("rows", []):
            for cell_key, cell_val in row.items():
                ck_lower = cell_key.lower()
                for canonical, aliases in field_map.items():
                    if canonical in figures:
                        continue
                    for alias in aliases:
                        if alias in ck_lower:
                            val = str(cell_val).replace(",", "")
                            try:
                                figures[canonical] = float(val)
                            except Exception:
                                pass

    return figures


# ── Orchestration ─────────────────────────────────────────────────────────────

def process_ticker(ticker: str, year: int = None) -> dict:
    """
    Full annual report processing for one ticker.
    1. Fetch DSE financial data page
    2. Get disclosure links
    3. Download PDF if found
    4. Parse PDF for key figures
    5. Save output to data/raw/annual_reports/{ticker}/{year}/
    """
    year = year or datetime.date.today().year
    out_dir = RAW_DIR / ticker / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "ticker": ticker,
        "year":   year,
        "status": "started",
    }

    # Step 1 — DSE financial data page
    fin_data = scrape_dse_financial_data(ticker)
    if fin_data:
        save_json(out_dir / "dse_financial_data.json", fin_data)
        result["dse_page"] = "ok"

    # Step 2 — Disclosure links
    disclosures = get_disclosure_links(ticker)
    save_json(out_dir / "disclosures.json", disclosures)
    result["disclosures_found"] = len(disclosures)

    # Step 3 — Download first PDF annual report found
    pdf_path   = out_dir / "report.pdf"
    pdf_parsed = {}
    for disc in disclosures:
        url = disc.get("url", "")
        if url.endswith(".pdf"):
            if download_pdf(url, pdf_path):
                pdf_parsed = parse_pdf_financials(pdf_path)
                break
    else:
        # No direct PDF link — try DSE's direct report endpoint
        direct_url = f"https://www.dse.com.bd/company_report.php?instrument={ticker}&report_type=annual&year={year}"
        if download_pdf(direct_url, pdf_path):
            pdf_parsed = parse_pdf_financials(pdf_path)

    if pdf_parsed:
        save_json(out_dir / "parsed_tables.json", pdf_parsed)
        key_figures = extract_key_figures(pdf_parsed)
        save_json(out_dir / "financial_summary.json", key_figures)
        result["pdf_parsed"] = "ok"
        result["key_figures"] = key_figures
    else:
        # Fallback — use DSE page data as summary
        from scripts.processor import parse_fundamentals_row
        parsed = parse_fundamentals_row(ticker, fin_data)
        save_json(out_dir / "financial_summary.json", parsed)
        result["pdf_parsed"] = "no_pdf_found_used_dse_page"
        result["key_figures"] = parsed

    result["status"] = "complete"
    log.info(f"Annual report processing complete: {ticker} {year}")
    return result


def process_all(tickers: list[str], year: int = None):
    """Process annual reports for all tickers."""
    results = []
    for i, ticker in enumerate(tickers):
        log.info(f"[{i+1}/{len(tickers)}] Annual report: {ticker}")
        try:
            res = process_ticker(ticker, year)
            results.append(res)
        except Exception as e:
            log.error(f"Annual report failed {ticker}: {e}")
            results.append({"ticker": ticker, "status": f"error: {e}"})
        time.sleep(2)
    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: annual_report_scraper.py <ticker|all> [year]")
        sys.exit(1)

    ticker_arg = sys.argv[1]
    year_arg   = int(sys.argv[2]) if len(sys.argv) > 2 else None

    if ticker_arg == "all":
        with open(CONFIG_DIR / "sectors.json") as f:
            sectors = json.load(f)
        tickers = []
        for sd in sectors["sectors"].values():
            tickers.extend(sd["top_tickers"])
        tickers = list(dict.fromkeys(tickers))
        results = process_all(tickers, year_arg)
        print(json.dumps([{"ticker": r["ticker"], "status": r["status"]} for r in results], indent=2))
    else:
        result = process_ticker(ticker_arg, year_arg)
        print(json.dumps(result, indent=2))
