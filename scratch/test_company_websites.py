import urllib.request
import re
from bs4 import BeautifulSoup

def test_fetch_website(url):
    try:
        if not url.startswith("http"):
            url = "https://" + url
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        resp = urllib.request.urlopen(req, timeout=8)
        html = resp.read().decode("utf-8", errors="ignore")
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.string.strip() if soup.title else "No title"
        links = [a.get("href") for a in soup.find_all("a") if a.get("href")]
        mgmt_links = [l for l in links if any(k in l.lower() for k in ["board", "director", "management", "leadership", "about"])]
        return {"status": "ok", "title": title, "mgmt_links": mgmt_links[:5]}
    except Exception as e:
        return {"status": "error", "error": str(e)}

print("Square:", test_fetch_website("www.squarepharma.com.bd"))
print("City Bank:", test_fetch_website("www.thecitybank.com"))
print("Jamuna Oil:", test_fetch_website("www.jamunaoil.gov.bd"))
