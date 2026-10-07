import urllib.request
import re
import json

tickers = [
    "SQURPHARMA", "JAMUNAOIL", "MPETROLEUM", "PADMAOIL", 
    "BSRMSTEEL", "LHB", "BATBC", "GP", "PUBALIBANK", 
    "CITYBANK", "EBL", "DUTCHBANGL", "OLYMPIC", "UPGDCL"
]

results = []
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

        # Loan Status
        idx_loan = combined.find('"loanStatus"')
        st_loan, lt_loan = 0.0, 0.0
        if idx_loan != -1:
            loan_chunk = combined[idx_loan:idx_loan+120]
            st_m = re.search(r'"shortTerm"\s*:\s*([\d\.]+)', loan_chunk)
            lt_m = re.search(r'"longTerm"\s*:\s*([\d\.]+)', loan_chunk)
            st_loan = float(st_m.group(1)) if st_m else 0.0
            lt_loan = float(lt_m.group(1)) if lt_m else 0.0

        # Dividend History
        div_history = []
        div_matches = re.findall(r'\{"year":(\d{4}),"cash":([\d\.]+),"stock":([\d\.]+),"yieldPct":([\d\.]+)', combined)
        for ym, cm, sm, ym_pct in div_matches:
            div_history.append({
                "year": int(ym),
                "cash": float(cm),
                "stock": float(sm),
                "yield_pct": float(ym_pct)
            })

        nav_m = re.search(r'"nav"\s*:\s*"([\d\.]+)"', combined)
        nav = float(nav_m.group(1)) if nav_m else 0.0

        puc_m = re.search(r'"paidUpCapital"\s*:\s*([\d\.]+)', combined)
        puc = float(puc_m.group(1)) if puc_m else 0.0

        num_shares = puc / 10.0 if puc else 0.0
        equity_mn = (num_shares * nav) / 1e6 if num_shares and nav else 0.0

        tot_loan = st_loan + lt_loan
        de_ratio = round(tot_loan / equity_mn, 3) if equity_mn > 0 else None
        lt_de_ratio = round(lt_loan / equity_mn, 3) if equity_mn > 0 else None

        results.append({
            "ticker": t,
            "equity_cr": round(equity_mn / 10.0, 1),
            "st_loan_cr": round(st_loan / 10.0, 1),
            "lt_loan_cr": round(lt_loan / 10.0, 1),
            "total_de": de_ratio,
            "lt_de": lt_de_ratio,
            "dividend_count": len(div_history),
            "div_history": div_history[:4]
        })
    except Exception as e:
        results.append({"ticker": t, "error": str(e)})

print(json.dumps(results, indent=2))
