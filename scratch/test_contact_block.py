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

idx = combined.find('squarepharma.com.bd')
with open("scratch/website_block.txt", "w", encoding="utf-8") as f:
    f.write(combined[idx-200:idx+600])

print("Written surroundings of squarepharma.com.bd")
