import urllib.request
import re

req = urllib.request.Request("https://www.dse.com.bd/company/SQURPHARMA", headers={"User-Agent": "Mozilla/5.0"})
html = urllib.request.urlopen(req, timeout=10).read().decode("utf-8")
chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*"((?:\\.|[^"\\])*)"\]\)', html)
combined = ""
for c in chunks:
    try:
        combined += bytes(c, "utf-8").decode("unicode_escape", errors="ignore")
    except Exception:
        combined += c

idx = combined.find('"loanStatus"')
print("loanStatus slice:", combined[idx:idx+200])

idx2 = combined.find('"dividendHistory"')
print("dividendHistory slice:", combined[idx2:idx2+300])
