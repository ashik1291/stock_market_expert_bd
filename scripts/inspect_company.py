import requests
import re
import json

def parse_dse_company_page(html: str, ticker: str) -> dict:
    data = {"ticker": ticker}

    # Match all self.__next_f.push calls
    chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*"((?:\\.|[^"\\])*)"\]\)', html)
    if chunks:
        combined = ""
        for c in chunks:
            try:
                combined += bytes(c, 'utf-8').decode('unicode_escape', errors='ignore')
            except Exception:
                combined += c
    else:
        combined = html

    # Exact company profile block
    comp_profile = re.search(
        r'\{"id":\d+,"name":"([^"]+)","sector":"([^"]+)","board":"([^"]+)","category":"([^"]+)"',
        combined
    )
    if comp_profile:
        data["name"] = comp_profile.group(1)
        data["sector"] = comp_profile.group(2)
        data["board"] = comp_profile.group(3)
        data["category"] = comp_profile.group(4)

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

    # If category or sector not matched yet, fallback
    if "category" not in data:
        cat_match = re.findall(r'"category"\s*:\s*"([A-Z])"', combined)
        if cat_match:
            data["category"] = cat_match[0]

    # Extract shareholding pattern: sponsor, government, institution, foreign, public
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

    # Historical sharePattern for manipulation tracking
    share_pattern_match = re.search(r'"sharePattern"\s*:\s*(\[.*?\])(?:,"dividendHistory"|,"creditRating")', combined)
    if share_pattern_match:
        try:
            data["share_pattern_history"] = json.loads(share_pattern_match.group(1))
        except Exception:
            pass

    return data

if __name__ == '__main__':
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36'
    }
    r = requests.get('https://www.dse.com.bd/company/PUBALIBANK', headers=headers, timeout=15)
    res = parse_dse_company_page(r.text, 'PUBALIBANK')
    print('EXTRACTED DATA FROM LIVE URL:')
    print(json.dumps(res, indent=2))
