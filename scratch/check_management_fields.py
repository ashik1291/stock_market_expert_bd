import urllib.request
import re
import json

tickers = ["SQURPHARMA", "BATBC", "CITYBANK", "JAMUNAOIL"]

for t in tickers:
    try:
        req = urllib.request.Request(f"https://www.dse.com.bd/company/{t}", headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=10).read().decode("utf-8")
        chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*"((?:\\.|[^"\\])*)"\]\)', html)
        combined = ""
        for c in chunks:
            try:
                combined += bytes(c, "utf-8").decode("unicode_escape", errors="ignore")
            except Exception:
                combined += c

        print(f"\n=== {t} ===")
        # Look for management / directors / secretary / website / email
        for pattern in ["website", "contact", "director", "management", "chairman", "managingDirector", "companySecretary", "auditor", "headOffice"]:
            m = re.findall(rf'"{pattern}"\s*:\s*([^,\}}]+|\{{.*?\}})', combined)
            if m:
                print(f"  {pattern} -> {m[:2]}")
    except Exception as e:
        print(f"Error {t}: {e}")
