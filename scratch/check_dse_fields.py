import urllib.request
import re
import json

for ticker in ["SQURPHARMA", "BSRMSTEEL", "BATBC"]:
    req = urllib.request.Request(f"https://www.dse.com.bd/company/{ticker}", headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req).read().decode("utf-8")
    chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*"((?:\\.|[^"\\])*)"\]\)', html)
    combined = ""
    for c in chunks:
        try:
            combined += bytes(c, "utf-8").decode("unicode_escape", errors="ignore")
        except Exception:
            combined += c

    print(f"\n=== {ticker} ===")
    loan_match = re.search(r'"loanStatus"\s*:\s*(\{.*?\})', combined)
    if loan_match:
        print("loanStatus:", loan_match.group(1))
    else:
        print("loanStatus: Not found")

    div_match = re.search(r'"dividendHistory"\s*:\s*(\[.*?\])', combined)
    if div_match:
        print("dividendHistory:", div_match.group(1)[:150])
    else:
        print("dividendHistory: Not found")
