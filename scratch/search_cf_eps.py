import urllib.request
import re
import json

req = urllib.request.Request("https://www.dse.com.bd/company/SQURPHARMA", headers={"User-Agent": "Mozilla/5.0"})
html = urllib.request.urlopen(req, timeout=10).read().decode("utf-8")
chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*"((?:\\.|[^"\\])*)"\]\)', html)
combined = ""
for c in chunks:
    try:
        combined += bytes(c, "utf-8").decode("unicode_escape", errors="ignore")
    except Exception:
        combined += c

print("Searching for quarterly, cfo, cashFlow, nocfps...")
for key in ["nocfps", "cashFlow", "cfo", "quarter", "q1", "q2", "q3", "eps", "financialPerformance"]:
    matches = re.findall(rf'"{key}"\s*:\s*([^,\}}]+|\{{.*?\}}|\[.*?\])', combined)
    if matches:
        print(f"  Found {key} -> {matches[:3]}")

idx = combined.find('nocfps')
if idx != -1:
    print("\nnocfps surrounding:", combined[idx-100:idx+300])
else:
    idx = combined.find('NOCFPS')
    if idx != -1:
        print("\nNOCFPS surrounding:", combined[idx-100:idx+300])
