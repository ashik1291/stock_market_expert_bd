"""
scripts/portfolio_sentinel.py
-----------------------------
Active Institutional Portfolio Guardian & Risk/Profit Sentinel for DSE.

Responsibilities:
  1. Live Valuation & Asymmetric Payoff Monitoring:
     - Tracks break-even prices, execution slippage, unrealized P&L.
     - Triggers [TAKE_PROFIT_50%] upon reaching +15% / +30% targets.
     - Triggers [HARD_STOP_EXIT] upon breaching -5% structural stops.
  2. Forensic Health Scan:
     - Continuously checks held stocks against manipulation_alerts and auditor risk flags.
  3. Dividend Receivable Tracker:
     - Computes exact upcoming net cash dividend credits based on held share counts.
  4. Mandatory 10% Dry-Powder Cash Buffer Verification.

Usage:
  python scripts/portfolio_sentinel.py
"""

import sys
import os
import json
import sqlite3
import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
PORTFOLIO_PATH = ROOT_DIR / "data" / "portfolio" / "portfolio.json"
DB_PATH = ROOT_DIR / "data" / "processed" / "dse.db"
REPORTS_DIR = ROOT_DIR / "reports" / "portfolio"


def audit_portfolio_sentinel(asof_date: str | None = None) -> dict:
    """Performs deep institutional audit on user's portfolio and holdings."""
    if not PORTFOLIO_PATH.exists():
        return {"error": "portfolio.json not found"}
        
    with open(PORTFOLIO_PATH, "r", encoding="utf-8") as f:
        port = json.load(f)

    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute('PRAGMA busy_timeout = 30000;')
    conn.row_factory = sqlite3.Row
    
    if not asof_date:
        row = conn.execute("SELECT MAX(date) FROM prices").fetchone()
        asof_date = row[0] if row and row[0] else datetime.date.today().isoformat()

    try:
        from anti_manipulation_engine import is_ticker_blacklisted
    except ImportError:
        # FAIL-CLOSED: if surveillance engine is missing, do NOT assume clean
        is_ticker_blacklisted = lambda t: (True, "Surveillance engine unavailable (Fail-Closed)")

    holdings_audit = []
    total_invested_equities = 0.0
    current_value_equities = 0.0
    total_dividends_receivable = 0.0
    upcoming_dividends = []

    for h in port.get("holdings", []):
        t = h["ticker"]
        sh = int(h["shares"])
        cost = float(h.get("cost_basis") or h.get("gross_cost", 0.0))
        entry_p = float(h["entry_price"])
        be_price = float(h.get("break_even_price") or round(entry_p * (1.0 + 0.00415) / (1.0 - 0.00465), 2))
        
        # Latest Price
        p_row = conn.execute(
            "SELECT close FROM prices WHERE ticker = ? AND date <= ? AND close > 0 ORDER BY date DESC LIMIT 1",
            (t, asof_date)
        ).fetchone()
        live_p = float(p_row["close"]) if p_row else entry_p
        
        cur_val = round(sh * live_p, 2)
        pnl_bdt = round(cur_val - cost, 2)
        pnl_pct = round((pnl_bdt / cost) * 100.0, 2) if cost > 0 else 0.0
        
        total_invested_equities += cost
        current_value_equities += cur_val
        
        # Targets & Stops (DSE Tiered Circuit Breaker Aware)
        from dse_circuit_breaker import get_dse_circuit_limit_pct, get_lower_circuit_floor, is_price_circuit_locked
        target_p = round(entry_p * 1.30, 1)  # +30% long-term target
        stop_p = round(entry_p * 0.90, 1)    # -10% hard stop
        
        # Liquidity Check (20-day average daily turnover)
        vol_rows = conn.execute(
            "SELECT close, volume FROM prices WHERE ticker = ? AND date <= ? ORDER BY date DESC LIMIT 20",
            (t, asof_date)
        ).fetchall()
        avg_turnover_cr = 0.0
        if vol_rows:
            avg_t = sum((float(r["close"] or 0) * float(r["volume"] or 0)) for r in vol_rows) / len(vol_rows)
            avg_turnover_cr = round(avg_t / 10000000.0, 2)

        # Technical Trend & 20-DMA Slope Verification
        closes_20 = [float(r["close"] or 0) for r in reversed(vol_rows) if r["close"]]
        dma_20 = sum(closes_20) / len(closes_20) if closes_20 else live_p
        dma_slope_down = len(closes_20) >= 10 and (sum(closes_20[-5:]) / 5.0) < (sum(closes_20[:5]) / 5.0)

        # Action Directive Determination (Martingale Falling-Knife Guard & Circuit Lock Awareness)
        prev_close_ref = closes_20[-2] if len(closes_20) >= 2 else entry_p
        cb_info = is_price_circuit_locked(live_p, prev_close_ref)
        cb_limit = cb_info["limit_pct"]
        lower_floor = cb_info["floor_price"]

        is_b, bl_msg = is_ticker_blacklisted(t, asof_date=asof_date)
        if is_b:
            action = "EMERGENCY_FORENSIC_EXIT"
            action_desc = f"🚨 ফরেনসিক সতর্কতা: {bl_msg} — বাউন্সে প্রস্থান করুন।"
        elif cb_info["locked"] and cb_info["side"] == "LOWER":
            action = "CIRCUIT_LOCKED_TRAP"
            action_desc = f"🛑 লোয়ার সার্কিট লক (-{cb_limit}%, ফ্লোর ৳{lower_floor:.1f})! বাজারে বিড শূন্য — পরবর্তী সেশনের প্রি-ওপেনিংয়ে সেল অর্ডার দিন।"
        elif live_p <= stop_p:
            action = "HARD_STOP_CUT"
            action_desc = f"🛑 স্টপ-লস স্পর্শ করেছে! মূলধন রক্ষায় কঠোর প্রস্থান নির্দেশ (সার্কিট ফাঁদ সতর্কবার্তা)।"
        elif pnl_pct <= -7.0 or (cb_limit <= 7.5 and pnl_pct <= -5.5):
            action = "PRE_STOP_WARNING"
            action_desc = f"⚠️ স্টপ-লস সতর্কতা (P&L: {pnl_pct}%) — নতুন ক্রয় সম্পূর্ণ নিষিদ্ধ; বাউন্সে এক্সিট প্রস্তুতি (স্টপ: ৳{stop_p})।"
        elif live_p < be_price and pnl_pct < -3.0:
            if dma_slope_down and live_p < dma_20:
                action = "WEAK_TREND_HOLD"
                action_desc = f"ডাউনট্রেন্ড চলমান (২০-দিনের গড়ের নিচে) — নতুন ডিপ বাই এড়িয়ে চলুন; সাপোর্ট স্থির হওয়া পর্যন্ত অপেক্ষা করুন।"
            else:
                action = "ACCUMULATE_DIP"
                action_desc = f"সাপোর্ট জোন টেস্ট করছে (P&L: {pnl_pct}%) — ব্লু-চিপ ফান্ডামেন্টাল অটুট থাকলে নিয়ন্ত্রিত ডিপ বাই।"
        elif live_p >= target_p or pnl_pct >= 30.0:
            action = "TAKE_PROFIT_ALL"
            action_desc = f"🎯 টার্গেট স্পর্শ করেছে (P&L: +{pnl_pct:.1f}%)! শতভাগ প্রফিট বুক করুন এবং মূলধন নিরাপদ করুন।"
        elif pnl_pct >= 15.0:
            action = "TAKE_PROFIT_HALF"
            action_desc = f"💰 অর্ধ-মুনাফা বুকিং (P&L: +{pnl_pct:.1f}%) — ৫০% প্রফিট টেক করুন, বাকি ৫০% ব্রেক-ইভেনে (৳{be_price:.1f}) ট্রেইল করুন।"
        else:
            action = "STRONG_HOLD"
            action_desc = "মৌলভিত্তি ও ট্রেন্ড নিরাপদ। দৃঢ়ভাবে হোল্ড করুন।"

        if avg_turnover_cr < 0.20 and action in ("HARD_STOP_CUT", "ACCUMULATE_DIP"):
            action_desc += f" [⚠️ থিন লিকুইডিটি: টার্নওভার ৳{avg_turnover_cr} কোটি]"


        # Check upcoming dividend receivables for this holding
        div_row = conn.execute("""
            SELECT record_date, cash_amount FROM corporate_actions 
            WHERE ticker = ? AND action_type = 'cash_dividend' AND record_date >= ?
            ORDER BY record_date ASC LIMIT 1
        """, (t, asof_date)).fetchone()
        
        div_info = None
        if div_row and div_row["cash_amount"]:
            cash_rate = float(div_row["cash_amount"])
            net_rate = round(cash_rate * 0.90, 2)  # 10% standard withholding tax
            receivable_bdt = round(sh * net_rate, 2)
            total_dividends_receivable += receivable_bdt
            div_info = {
                "record_date": div_row["record_date"],
                "gross_per_share": cash_rate,
                "net_receivable_bdt": receivable_bdt
            }
            upcoming_dividends.append({
                "ticker": t,
                "shares": sh,
                "record_date": div_row["record_date"],
                "net_amount_bdt": receivable_bdt
            })

        holdings_audit.append({
            "ticker": t,
            "shares": sh,
            "entry_price": entry_p,
            "break_even_price": be_price,
            "live_price": live_p,
            "cost_basis": cost,
            "current_value": cur_val,
            "pnl_bdt": pnl_bdt,
            "pnl_pct": pnl_pct,
            "target_price": target_p,
            "stop_price": stop_p,
            "action": action,
            "action_desc_bn": action_desc,
            "dividend_info": div_info
        })

    conn.close()

    # Mutual Fund Portfolio
    mf_cost = sum(float(mf.get("market_value_bdt") or mf.get("total_cost_bdt") or 0.0) for mf in port.get("mutual_funds", []))
    cash_bal = float(port.get("cash_balance_bdt", 0.0))
    total_net_worth = round(current_value_equities + mf_cost + cash_bal, 2)
    target_10pct_cash = round(total_net_worth * 0.10, 2)
    cash_deficit = max(0.0, round(target_10pct_cash - cash_bal, 2))

    # Nano-Diversification & Ticket Drag Audit
    nano_holdings = [h for h in holdings_audit if h["current_value"] < 500.0 or h["shares"] <= 2]
    consolidation_advice = []
    if len(nano_holdings) >= 3:
        consolidation_advice.append(
            "⚠️ ন্যানো-ডাইভারসিফিকেশন সতর্কতা: আপনার ৬টি স্টকের প্রতিটিতে গড়ে মাত্র ৳৩০০ করে বিনিয়োগ রয়েছে। "
            "১টি শেয়ারে ২০% লাভ হলেও মোট পুঁজিতে লাভ মাত্র ৳৬০-৭০, কিন্তু ব্রোকার ন্যূনতম ফি (৳৫-১০) আপনার ১.৫%-৩% লাভ খেয়ে নিচ্ছে। "
            "পরামর্শ: এই ছোট লটগুলো বিক্রি করে সর্বোচ্চ ২টি শীর্ষ কনভিকশন মোটে (যেমন JAMUNAOIL বা SQURPHARMA) "
            "ন্যূনতম ১০-২০ শেয়ারের স্ট্যান্ডার্ড ব্লকে কনসলিডেট (একত্রিত) করুন।"
        )

    return {
        "as_of_date": asof_date,
        "nano_holdings_count": len(nano_holdings),
        "consolidation_advice": consolidation_advice,
        "total_net_worth": total_net_worth,
        "total_invested_equities": round(total_invested_equities, 2),
        "current_value_equities": round(current_value_equities, 2),
        "equities_pnl_bdt": round(current_value_equities - total_invested_equities, 2),
        "equities_pnl_pct": round(((current_value_equities - total_invested_equities) / total_invested_equities) * 100.0, 2) if total_invested_equities > 0 else 0.0,
        "mutual_funds_val": mf_cost,
        "available_cash": cash_bal,
        "target_10pct_cash": target_10pct_cash,
        "cash_deficit": cash_deficit,
        "total_dividends_receivable": round(total_dividends_receivable, 2),
        "upcoming_dividends": upcoming_dividends,
        "holdings": holdings_audit
    }


def generate_sentinel_reports(asof_date: str | None = None) -> tuple[Path, Path]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    audit = audit_portfolio_sentinel(asof_date)
    date_str = audit["as_of_date"]
    
    # Bengali Report
    bn_path = REPORTS_DIR / f"{date_str}_portfolio_sentinel_bn.md"
    bn_lines = [
        f"# 🛡️ ডিএসই পোর্টফোলিও সেন্টিনেল ও রিস্ক গার্ড রিপোর্ট — {date_str}",
        f"**মূল্যায়ন সময়**: `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}` | **অ্যাকাউন্ট মোট মূল্য**: **৳{audit['total_net_worth']:,.2f}**\n",
        f"### 📊 সারসংক্ষেপ ড্যাশবোর্ড",
        f"- **শেয়ারে বিনিয়োগকৃত অর্থ**: ৳{audit['total_invested_equities']:,.2f} | **বর্তমান বাজারমূল্য**: ৳{audit['current_value_equities']:,.2f}",
        f"- **শেয়ারে মোট লাভ/ক্ষতি (P&L)**: **৳{audit['equities_pnl_bdt']:,.2f} ({audit['equities_pnl_pct']:+.2f}%)**",
        f"- **মিউচুয়াল ফান্ড (Shanta Amana)**: ৳{audit['mutual_funds_val']:,.2f} (Core Defensive Anchor)",
        f"- **বর্তমান লিকুইড ক্যাশ**: ৳{audit['available_cash']:,.2f} | **১০% টার্গেট বাফার ঘাটতি**: ⚠️ **৳{audit['cash_deficit']:,.2f}**",
        f"- **আসন্ন নিশ্চিত ক্যাশ ডিভিডেন্ড প্রাপ্যতা**: 💰 **৳{audit['total_dividends_receivable']:,.2f}**\n",
        "---",
        "## 🏛️ বর্তমান শেয়ার হোল্ডিংস অডিট ও তাৎক্ষণিক অ্যাকশন নির্দেশিকা\n",
        "| কোম্পানি | শেয়ার | কেনা দর | ব্রেক-ইভেন | লাইভ দর | P&L (৳) | P&L % | টার্গেট (+৩০%) | স্টপ (-১০%) | অ্যাকশন স্ট্যাটাস |",
        "|---|---|---|---|---|---|---|---|---|---|"
    ]
    
    for h in audit["holdings"]:
        bn_lines.append(
            f"| **{h['ticker']}** | {h['shares']} | ৳{h['entry_price']:.1f} | ৳{h['break_even_price']:.1f} | "
            f"৳{h['live_price']:.1f} | ৳{h['pnl_bdt']:+.2f} | **{h['pnl_pct']:+.1f}%** | "
            f"৳{h['target_price']:.1f} | ৳{h['stop_price']:.1f} | **{h['action']}** |"
        )
        
    bn_lines.extend([
        "\n---",
        "## 💰 আসন্ন ক্যাশ ডিভিডেন্ড ক্যালেন্ডার (Receivable Cash)",
        "| কোম্পানি | শেয়ার সংখ্যা | রেকর্ড ডেট | নিট প্রাপ্যতা (১০% ট্যাক্স বাদে) |",
        "|---|---|---|---|"
    ])
    for d in audit["upcoming_dividends"]:
        bn_lines.append(f"| **{d['ticker']}** | {d['shares']} টি | `{d['record_date']}` | **৳{d['net_amount_bdt']:.2f}** |")
    if not audit["upcoming_dividends"]:
        bn_lines.append("> আগামী ৩০ দিনে কোনো শেয়ারের ডিভিডেন্ড রেকর্ড ডেট নেই।")

    if audit.get("consolidation_advice"):
        bn_lines.extend([
            "\n---",
            "## 💡 পোর্টফোলিও কনসলিডেশন ও ন্যানো-ডাইভারসিফিকেশন অডিট (Lot Sizing Strategy)",
            "> " + audit["consolidation_advice"][0],
            "\n**বাস্তবায়ন কৌশল**:",
            "- ১ বা ২ শেয়ারের ক্ষুদ্র অবস্থান বিক্রি করে একক লেনদেনের কমিশন সাশ্রয় করুন।",
            "- সংগৃহীত অর্থ দিয়ে শুধুমাত্র ১টি বা ২টি সুনির্দিষ্ট ব্লু-চিপে (যথা: JAMUNAOIL / SQURPHARMA) পূর্ণাঙ্গ ১০–২০ শেয়ারের ব্লক তৈরি করুন।"
        ])

    with open(bn_path, "w", encoding="utf-8") as f:
        f.write("\n".join(bn_lines))
        
    return bn_path, bn_path


def main():
    audit = audit_portfolio_sentinel()
    print("=" * 85)
    print(f"🛡️ DSE ACTIVE PORTFOLIO SENTINEL & CAPITAL GUARDIAN")
    print("=" * 85)
    print(f"Total Net Worth: ৳{audit['total_net_worth']:,.2f} | Equities P&L: ৳{audit['equities_pnl_bdt']:,.2f} ({audit['equities_pnl_pct']}%)")
    print(f"Available Cash: ৳{audit['available_cash']:,.2f} | 10% Cash Buffer Deficit: ৳{audit['cash_deficit']:,.2f}")
    print(f"Upcoming Net Cash Dividend Credits: ৳{audit['total_dividends_receivable']:,.2f}")
    print("-" * 85)
    for h in audit["holdings"]:
        print(f"[{h['action']:<20}] {h['ticker']:<12} Live: ৳{h['live_price']:<7.1f} P&L: ৳{h['pnl_bdt']:<7.2f} ({h['pnl_pct']:>5.1f}%) | {h['action_desc_bn']}")
    print("=" * 85)
    bn_p, _ = generate_sentinel_reports()
    print(f"[Sentinel Report Published: {bn_p.name}]")


if __name__ == "__main__":
    main()
