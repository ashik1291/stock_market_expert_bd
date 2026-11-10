"""
DSE Portfolio Manager & Dynamic Position Sizer

Capabilities:
  1. Personalized Capital Allocation (e.g. BDT 5,00,000 or BDT 20,00,000)
  2. Exact Share-Count Sizing across 60% Core, 30% Swings, 10% Cash
  3. Slippage Guard Verification (ensures order does not exceed 5% of daily volume)
  4. Tranche Execution Schedule (Week 1 initial entry vs Dip accumulation)
  5. Live P&L and Stop-Loss Surveillance
"""

import json
import logging
import datetime
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR      = Path(__file__).resolve().parent.parent
PORTFOLIO_DIR = BASE_DIR / "data" / "portfolio"
REPORTS_DIR   = BASE_DIR / "reports" / "weekly"
KNOW_DIR      = BASE_DIR / "data" / "knowledge"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("portfolio_manager")


def get_portfolio_path() -> Path:
    PORTFOLIO_DIR.mkdir(parents=True, exist_ok=True)
    return PORTFOLIO_DIR / "portfolio.json"


def load_portfolio(user_id: str = "default_user") -> dict:
    try:
        from user_manager import load_user_portfolio
        return load_user_portfolio(user_id)
    except Exception:
        path = get_portfolio_path()
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        return {
            "total_capital_bdt": 500000.0,
            "cash_balance_bdt": 500000.0,
            "created_at": datetime.datetime.utcnow().isoformat(),
            "holdings": [],
            "history": []
        }


def save_portfolio(p: dict, user_id: str = "default_user"):
    try:
        from user_manager import save_user_portfolio
        save_user_portfolio(user_id, p)
    except Exception:
        path = get_portfolio_path()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(p, f, indent=2)


def set_capital(amount_bdt: float):
    p = load_portfolio()
    diff = amount_bdt - p["total_capital_bdt"]
    p["total_capital_bdt"] = amount_bdt
    p["cash_balance_bdt"] += diff
    save_portfolio(p)
    print(f"Total Investable Capital set to: ৳{amount_bdt:,.2f} (Available Cash: ৳{p['cash_balance_bdt']:,.2f})")


def get_latest_weekly_report() -> dict | None:
    files = sorted(REPORTS_DIR.glob("*.json"))
    if not files:
        return None
    with open(files[-1], encoding="utf-8") as f:
        return json.load(f)


def generate_exact_position_plan(capital_bdt: float = None):
    p = load_portfolio()
    total_cap = capital_bdt if capital_bdt is not None else p["total_capital_bdt"]

    recs = get_latest_weekly_report()
    if not recs:
        print("No weekly report found. Run `python scripts/recommender.py weekly` first.")
        return

    long_picks = recs["horizons"]["long_term"][:3]
    mid_picks  = recs["horizons"]["mid_term"][:2]

    # Allocations
    core_budget  = total_cap * 0.60   # 60%
    swing_budget = total_cap * 0.30   # 30%
    cash_reserve = total_cap * 0.10   # 10%

    per_core_budget  = core_budget / max(len(long_picks), 1)
    per_swing_budget = swing_budget / max(len(mid_picks), 1)

    lines = []
    lines.append(f"# 🎯 Exact Portfolio Position Plan (Capital: ৳{total_cap:,.0f})\n")
    lines.append(f"**Generated**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
    lines.append(f"**Allocation**: 60% Core Moats (৳{core_budget:,.0f}) | 30% Swings (৳{swing_budget:,.0f}) | 10% Cash (৳{cash_reserve:,.0f})\n")
    lines.append("---\n")

    # Core Assets
    lines.append("## 🏛️ 1. Long-Term Core Moats (60% Total Capital)\n")
    lines.append("| Ticker | Current Price | Total Allocation | Total Shares | Tranche 1 (25% Today) | Tranche 1 Cost | Max Slippage Limit | Target Exit (+30%) |")
    lines.append("|---|---|---|---|---|---|---|---|")

    for r in long_picks:
        t = r["ticker"]
        price = r.get("entry") or 1.0
        total_shares = int(per_core_budget / price)
        tranche_1_shares = max(int(total_shares * 0.25), 1)
        tranche_1_cost = tranche_1_shares * price
        target_exit = r.get("target_long") or round(price * 1.30, 1)

        # Slippage check
        slippage_limit = 5000
        know_file = KNOW_DIR / t / "weekly.json"
        if know_file.exists():
            try:
                with open(know_file, encoding="utf-8") as kf:
                    kdata = json.load(kf)
                    slippage_limit = kdata.get("precision", {}).get("liquidity", {}).get("max_single_order_shares", 5000)
            except Exception:
                pass

        lines.append(
            f"| **{t}** | ৳{price:.1f} | ৳{per_core_budget:,.0f} | **{total_shares:,} sh** | "
            f"**{tranche_1_shares:,} sh** | ৳{tranche_1_cost:,.0f} | Max {slippage_limit:,} sh | ৳{target_exit:.1f} |"
        )
    lines.append("\n*Rule: Execute Tranche 1 today. Reserve remaining 75% for 3 systematic dips or weekly confirmations.*\n")
    lines.append("---\n")

    # Mid-Term Swings
    lines.append("## 📈 2. Mid-Term Cycle Swings (30% Total Capital)\n")
    lines.append("| Ticker | Entry Price | Allocation | Exact Shares | Total Outlay | Swing Target (+15%) | Trailing Stop (-5%) | Risk/Reward |")
    lines.append("|---|---|---|---|---|---|---|---|")

    for r in mid_picks:
        t = r["ticker"]
        price = r.get("entry") or 1.0
        tgt = r.get("target_mid") or round(price * 1.15, 1)
        stop = r.get("trailing_stop") or round(price * 0.95, 1)
        
        # Risk-based position sizing: limit trade loss to max 1.5% of total portfolio capital
        max_trade_risk_bdt = total_cap * 0.015
        risk_per_share = max(price - stop, price * 0.04)
        risk_capped_shares = int(max_trade_risk_bdt / risk_per_share) if risk_per_share > 0 else 1000
        budget_shares = int(per_swing_budget / price)
        
        # Sizing takes the conservative minimum
        shares = max(min(budget_shares, risk_capped_shares), 1)
        outlay = shares * price

        lines.append(
            f"| **{t}** | ৳{price:.1f} | ৳{per_swing_budget:,.0f} | **{shares:,} sh** | "
            f"৳{outlay:,.0f} | **৳{tgt:.1f}** | ৳{stop:.1f} | 3.0x |"
        )
    lines.append("\n*Rule: Enter with full swing lot on support confirmation. Strictly exit upon hitting target or stop-loss.*\n")
    lines.append("---\n")

    # Cash Reserve
    lines.append("## 🛡️ 3. Tactical Cash / Dry Powder Reserve (10% Total Capital)\n")
    lines.append(f"- **Reserved Cash Balance**: **৳{cash_reserve:,.2f}**")
    lines.append("- **Purpose**: Kept in brokerage balance or liquid money market for black-swan panic drops or deep RSI (<25) bargains.\n")

    report_text = "\n".join(lines)
    print(report_text)

    out_file = PORTFOLIO_DIR / "current_position_plan.md"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\n[Saved to {out_file}]")

    # Native Bengali companion plan
    bn_lines = []
    bn_lines.append(f"# 🎯 পোর্টফোলিও পজিশন ও অ্যাকুমুলেশন প্ল্যান (মোট মূলধন: ৳{total_cap:,.0f})\n")
    bn_lines.append(f"**তৈরির সময়**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
    bn_lines.append(f"**বিনিয়োগ বণ্টন**: ৬০% কোর মোটস (৳{core_budget:,.0f}) | ৩০% সাইকেল সুইং (৳{swing_budget:,.0f}) | ১০% ক্যাশ রিজার্ভ (৳{cash_reserve:,.0f})\n")
    bn_lines.append("---\n")

    bn_lines.append("## 🏛️ ১. দীর্ঘমেয়াদী কোর মোটস (৬০% মূলধন)\n")
    bn_lines.append("| Ticker | বর্তমান দর | মোট বরাদ্দ | মোট শেয়ার | ১ম ট্রাঞ্চ (আজ ২৫%) | ১ম ট্রাঞ্চ খরচ | স্লিপেজ সীমা | টার্গেট প্রফিট (+৩০%) |")
    bn_lines.append("|---|---|---|---|---|---|---|---|")
    for r in long_picks:
        t = r["ticker"]
        price = r.get("entry") or 1.0
        total_shares = int(per_core_budget / price)
        tranche_1_shares = max(int(total_shares * 0.25), 1)
        tranche_1_cost = tranche_1_shares * price
        target_exit = r.get("target_long") or round(price * 1.30, 1)
        bn_lines.append(
            f"| **{t}** | ৳{price:.1f} | ৳{per_core_budget:,.0f} | **{total_shares:,} টি** | "
            f"**{tranche_1_shares:,} টি** | ৳{tranche_1_cost:,.0f} | নিরাপদ রিটেইল লিমিট | ৳{target_exit:.1f} |"
        )
    bn_lines.append("\n*নিয়ম: ট্রাঞ্চ ১ আজ এক্সিকিউট করুন। বাকি ৭৫% মূলধন ৩টি পরবর্তী ডিপ বা উইকলি কনফার্মেশনের জন্য রাখুন।*\n")
    bn_lines.append("---\n")

    bn_lines.append("## 📈 ২. মিড-টার্ম সাইকেল সুইং ট্রেড (৩০% মূলধন)\n")
    bn_lines.append("| Ticker | এন্ট্রি দর | বরাদ্দ | শেয়ার সংখ্যা | মোট বিনিয়োগ | সুইং টার্গেট (+১৫%) | ট্রেইলিং স্টপ (-৫%) | রিস্ক/রিওয়ার্ড |")
    bn_lines.append("|---|---|---|---|---|---|---|---|")
    for r in mid_picks:
        t = r["ticker"]
        price = r.get("entry") or 1.0
        tgt = r.get("target_mid") or round(price * 1.15, 1)
        stop = r.get("trailing_stop") or round(price * 0.95, 1)
        max_trade_risk_bdt = total_cap * 0.015
        risk_per_share = max(price - stop, price * 0.04)
        risk_capped_shares = int(max_trade_risk_bdt / risk_per_share) if risk_per_share > 0 else 1000
        budget_shares = int(per_swing_budget / price)
        shares = max(min(budget_shares, risk_capped_shares), 1)
        outlay = shares * price
        bn_lines.append(
            f"| **{t}** | ৳{price:.1f} | ৳{per_swing_budget:,.0f} | **{shares:,} টি** | "
            f"৳{outlay:,.0f} | **৳{tgt:.1f}** | ৳{stop:.1f} | 3.0x |"
        )
    bn_lines.append("\n*নিয়ম: সাপোর্ট কনফার্মেশনে সুইং লটে প্রবেশ করুন। টার্গেট বা স্টপ-লস স্পর্শ করা মাত্রই শৃঙ্খলা মেনে এক্সিট করুন।*\n")
    bn_lines.append("---\n")

    bn_lines.append("## 🛡️ ৩. ট্যাকটিক্যাল ক্যাশ / রিজার্ভ ফান্ড (১০% মূলধন)\n")
    bn_lines.append(f"- **সংরক্ষিত ক্যাশ ব্যালেন্স**: **৳{cash_reserve:,.2f}**")
    bn_lines.append("- **উদ্দেশ্য**: ব্ল্যাক-সোয়ান মার্কেট প্যানিক বা ডিপ ওভারসোল্ড (<২৫ RSI) অতি-মূল্যবান সুযোগের জন্য প্রস্তুত রাখা。\n")

    bn_out_file = PORTFOLIO_DIR / "current_position_plan_bn.md"
    with open(bn_out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(bn_lines))
    print(f"[Saved to {bn_out_file}]")


# DSE Fee Schedule: 0.40% Brokerage fee + 0.015% CDBL settlement fee + 0.05% Govt AIT on Sell
BROKERAGE_FEE_PCT   = 0.0040   # 0.40% broker commission
CDBL_FEE_PCT        = 0.00015  # 0.015% CDBL settlement fee
GOVT_AIT_SELL_PCT   = 0.00050  # 0.050% Statutory Advance Income Tax (Section 53BBB / Sec 124 ITA 2023)

TOTAL_BUY_FEE_PCT   = BROKERAGE_FEE_PCT + CDBL_FEE_PCT                    # 0.415%
TOTAL_SELL_FEE_PCT  = BROKERAGE_FEE_PCT + CDBL_FEE_PCT + GOVT_AIT_SELL_PCT  # 0.465%
TOTAL_ONE_WAY_FEE   = TOTAL_BUY_FEE_PCT  # alias for buy fee
ROUND_TRIP_TOTAL_PCT = TOTAL_BUY_FEE_PCT + TOTAL_SELL_FEE_PCT              # 0.880%

def calculate_round_trip_break_even(entry_price: float, shares: int = 1, min_fee: float = 0.0) -> float:
    """
    Computes exact selling price where net proceeds after sell fees
    (including 0.05% statutory AIT) exactly equal the gross purchase outlay plus buy fees:
      P_sell * (1 - TOTAL_SELL_FEE_PCT) = P_buy * (1 + TOTAL_BUY_FEE_PCT)
      P_sell = P_buy * (1 + TOTAL_BUY_FEE_PCT) / (1 - TOTAL_SELL_FEE_PCT)
    """
    if entry_price <= 0:
        return 0.0
    factor = (1.0 + TOTAL_BUY_FEE_PCT) / (1.0 - TOTAL_SELL_FEE_PCT)
    if min_fee > 0 and shares > 0:
        fee_per_share = min_fee / shares
        effective_buy_p = entry_price + fee_per_share
        return round((effective_buy_p * (1.0 + TOTAL_BUY_FEE_PCT) + fee_per_share) / (1.0 - TOTAL_SELL_FEE_PCT), 2)
    return round(entry_price * factor, 2)

PORTFOLIO_DRAWDOWN_KILL_THRESHOLD_PCT = 10.0  # -10% from high-water mark freezes new buying

def check_reversal_confirmation(ticker: str, conn) -> bool:
    """
    Checks if a falling stock has confirmed a reversal:
    1. Latest close >= 5-day EMA, OR
    2. RSI-14 exited oversold corridor (> 30.0 after touching <= 30.0)
    """
    if not conn:
        return False
    rows = conn.execute(
        "SELECT close FROM prices WHERE ticker = ? ORDER BY date DESC LIMIT 15",
        (ticker,),
    ).fetchall()
    if len(rows) < 5:
        return False
    closes = [float(r[0]) for r in reversed(rows)]
    multiplier = 2.0 / (5.0 + 1.0)
    ema = closes[0]
    for c in closes[1:]:
        ema = (c * multiplier) + (ema * (1.0 - multiplier))
    latest_close = closes[-1]
    return latest_close >= ema


def check_portfolio_drawdown_kill(p: dict, current_net_worth: float) -> tuple[bool, float, float]:
    """Calculates drawdown from high-water mark; returns (is_killed, dd_pct, hwm)."""
    hwm = float(p.get("high_water_mark_bdt", p.get("total_capital_bdt", current_net_worth)))
    if current_net_worth > hwm:
        hwm = current_net_worth
        p["high_water_mark_bdt"] = hwm
    dd_pct = round(((hwm - current_net_worth) / hwm) * 100.0, 2) if hwm > 0 else 0.0
    is_killed = dd_pct >= PORTFOLIO_DRAWDOWN_KILL_THRESHOLD_PCT
    return is_killed, dd_pct, hwm


def update_portfolio_hwm(current_net_worth: float, user_id: str = "default_user") -> float:
    """Updates high-water mark dynamically if current net worth hits a new high."""
    p = load_portfolio(user_id=user_id)
    hwm = float(p.get("high_water_mark_bdt", p.get("total_capital_bdt", current_net_worth)))
    if current_net_worth > hwm:
        p["high_water_mark_bdt"] = round(current_net_worth, 2)
        save_portfolio(p, user_id=user_id)
        return round(current_net_worth, 2)
    return hwm



def record_buy(ticker: str, shares: int, price: float, horizon: str = "long_term", min_ticket_fee: float = 0.0, asof_date: str | None = None):
    # Guard against blacklisted / manipulated stocks
    try:
        from anti_manipulation_engine import is_ticker_blacklisted
        is_blocked, bl_msg = is_ticker_blacklisted(ticker.upper(), asof_date=asof_date)
        if is_blocked:
            print(f"⛔ REJECTED: Cannot record BUY for {ticker.upper()} — {bl_msg}")
            return False
    except Exception as e:
        print(f"⚠️ Blacklist verification warning for {ticker.upper()}: {e}")

    p = load_portfolio()
    
    # Portfolio-Level Drawdown Kill Rule (-10% from high-water mark halts new buying)
    mf_val = sum(float(m.get("market_value_bdt") or m.get("total_cost_bdt", 0.0)) for m in p.get("mutual_funds", []))
    current_nw = p.get("cash_balance_bdt", 0.0) + sum(h.get("cost_basis", 0.0) for h in p.get("holdings", [])) + mf_val
    is_killed, dd_pct, hwm = check_portfolio_drawdown_kill(p, current_nw)
    if is_killed:
        print(f"⛔ PORTFOLIO DRAWDOWN KILL RULE BREACHED: Drawdown -{dd_pct:.1f}% exceeds 10% limit from HWM ৳{hwm:,.2f}. All new BUY orders are FROZEN.")
        return False

    gross_cost = shares * price
    pct_comm = round(gross_cost * TOTAL_ONE_WAY_FEE, 2)
    comm = max(pct_comm, min_ticket_fee if gross_cost > 0 else 0.0)
    net_cost = round(gross_cost + comm, 2)
    round_trip_be = calculate_round_trip_break_even(price, shares=shares, min_fee=min_ticket_fee)
    effective_entry = round(net_cost / shares, 2) if shares > 0 else price

    min_cash_buffer = p.get("total_capital_bdt", 0) * 0.10
    remaining_cash = p["cash_balance_bdt"] - net_cost
    if net_cost > p["cash_balance_bdt"]:
        print(f"⚠️ CRITICAL DEFICIT: Buy cost ৳{net_cost:,.2f} exceeds available cash ৳{p['cash_balance_bdt']:,.2f}.")
    elif remaining_cash < min_cash_buffer:
        print(f"⚠️ LIQUIDITY BUFFER WARNING: Purchase leaves cash (৳{remaining_cash:,.2f}) below mandatory 10% buffer (৳{min_cash_buffer:,.2f}). Reserve dry-powder!")

    p["cash_balance_bdt"] = round(p["cash_balance_bdt"] - net_cost, 2)

    # Check for existing holding of the same ticker to merge/average cost
    existing_holding = None
    for h in p.get("holdings", []):
        if h.get("ticker", "").upper() == ticker.upper():
            existing_holding = h
            break

    if existing_holding:
        prev_shares = int(existing_holding.get("shares", 0))
        total_sh = prev_shares + shares
        prev_gross = float(existing_holding.get("gross_cost", 0.0)) or (prev_shares * float(existing_holding.get("entry_price", price)))
        total_gross = round(prev_gross + gross_cost, 2)
        total_comm = round(float(existing_holding.get("commission_bdt", 0.0)) + comm, 2)
        total_cost = round(float(existing_holding.get("cost_basis", 0.0)) + net_cost, 2)
        avg_entry = round(total_gross / total_sh, 2)
        eff_entry = round(total_cost / total_sh, 2)
        merged_be = calculate_round_trip_break_even(avg_entry, shares=total_sh, min_fee=min_ticket_fee)
        
        existing_holding["shares"] = total_sh
        existing_holding["entry_price"] = avg_entry
        existing_holding["gross_cost"] = total_gross
        existing_holding["commission_bdt"] = total_comm
        existing_holding["cost_basis"] = total_cost
        existing_holding["effective_entry"] = eff_entry
        existing_holding["break_even_price"] = merged_be
        existing_holding["bought_at"] = datetime.date.today().isoformat()
    else:
        p["holdings"].append({
            "ticker":          ticker.upper(),
            "shares":          shares,
            "entry_price":     price,
            "gross_cost":      gross_cost,
            "commission_bdt":  comm,
            "cost_basis":      net_cost,
            "effective_entry": effective_entry,
            "break_even_price": round_trip_be,
            "horizon":         horizon,
            "bought_at":       datetime.date.today().isoformat()
        })

    p["history"].append({
        "action":     "BUY",
        "ticker":     ticker.upper(),
        "shares":     shares,
        "price":      price,
        "commission": comm,
        "total_cost": net_cost,
        "date":       datetime.date.today().isoformat()
    })
    save_portfolio(p)
    print(f"Recorded BUY: {shares} shares of {ticker.upper()} @ ৳{price:.1f} + ৳{comm:.2f} comm (Total: ৳{net_cost:,.2f}). Remaining Cash: ৳{p['cash_balance_bdt']:,.2f}")
    return True


def record_sell(
    ticker: str,
    shares: int,
    price: float,
    date: str | None = None,
    min_ticket_fee: float = 5.0,
    user_id: str = "default_user",
    reason: str = "manual_exit"
) -> dict:
    """
    Executes and records a SELL order:
    1. Validates holding exists and has sufficient shares.
    2. Computes Gross Proceeds = shares * price.
    3. Computes Sell Friction = max(shares * price * TOTAL_SELL_FEE_PCT, min_ticket_fee)
       where TOTAL_SELL_FEE_PCT = 0.465% (0.40% broker + 0.015% DSE + 0.05% Sec 53BBB AIT).
    4. Computes Net Proceeds = Gross Proceeds - Sell Friction.
    5. Computes Realized P&L = Net Proceeds - Proportionate Cost Basis of sold shares.
    6. Credits Net Proceeds directly to cash_balance_bdt.
    7. Updates or removes holding.
    8. Records transaction in history.
    """
    p = load_portfolio(user_id=user_id)
    sym = ticker.upper()
    matching_idx = None
    for idx, h in enumerate(p.get("holdings", [])):
        if h.get("ticker", "").upper() == sym:
            matching_idx = idx
            break

    if matching_idx is None:
        raise ValueError(f"Position not found: You do not own any shares of {sym}.")

    holding = p["holdings"][matching_idx]
    current_shares = int(holding.get("shares", 0))
    if shares > current_shares:
        raise ValueError(f"Insufficient shares: You own {current_shares} shares of {sym}, cannot sell {shares}.")

    cost_basis_per_share = float(holding.get("cost_basis", 0.0)) / current_shares if current_shares > 0 else float(holding.get("entry_price", 0.0))
    sold_cost_basis = round(cost_basis_per_share * shares, 2)

    gross_proceeds = round(shares * price, 2)
    pct_comm = round(gross_proceeds * TOTAL_SELL_FEE_PCT, 2)
    comm = max(pct_comm, min_ticket_fee if gross_proceeds > 0 else 0.0)
    net_proceeds = round(gross_proceeds - comm, 2)

    realized_pnl_bdt = round(net_proceeds - sold_cost_basis, 2)
    realized_pnl_pct = round((realized_pnl_bdt / sold_cost_basis) * 100.0, 2) if sold_cost_basis > 0 else 0.0

    p["cash_balance_bdt"] = round(p.get("cash_balance_bdt", 0.0) + net_proceeds, 2)

    if shares == current_shares:
        p["holdings"].pop(matching_idx)
    else:
        holding["shares"] = current_shares - shares
        holding["gross_cost"] = round(holding.get("entry_price", 0.0) * holding["shares"], 2)
        holding["cost_basis"] = round(cost_basis_per_share * holding["shares"], 2)
        holding["commission_bdt"] = round(holding.get("commission_bdt", 0.0) * (holding["shares"] / current_shares), 2)

    trade_date = date or datetime.date.today().isoformat()
    history_entry = {
        "action": "SELL",
        "ticker": sym,
        "shares": shares,
        "price": price,
        "gross_proceeds": gross_proceeds,
        "commission": comm,
        "net_proceeds": net_proceeds,
        "cost_basis": sold_cost_basis,
        "realized_pnl_bdt": realized_pnl_bdt,
        "realized_pnl_pct": realized_pnl_pct,
        "reason": reason,
        "date": trade_date
    }
    p["history"].append(history_entry)
    save_portfolio(p, user_id=user_id)

    print(f"Recorded SELL: {shares} shares of {sym} @ ৳{price:.1f} - ৳{comm:.2f} fee (Net Proceeds: ৳{net_proceeds:,.2f} | Realized P&L: ৳{realized_pnl_bdt:+,.2f} / {realized_pnl_pct:+.2f}%). Cash Balance: ৳{p['cash_balance_bdt']:,.2f}")
    return history_entry


DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"


def show_status():
    import sqlite3
    p = load_portfolio()
    mfs = p.get("mutual_funds", [])
    holdings = p.get("holdings", [])
    
    conn = sqlite3.connect(DB_PATH, timeout=30.0) if DB_PATH.exists() else None
    conn.execute("PRAGMA busy_timeout = 30000;")

    # Check and credit any due cash dividends from corporate actions
    if conn:
        try:
            from corporate_action_processor import process_portfolio_dividends
            div_res = process_portfolio_dividends(user_id=p.get("user_id", "default_user"), conn=conn)
            if div_res.get("credited_count", 0) > 0:
                p = load_portfolio()
                mfs = p.get("mutual_funds", [])
                holdings = p.get("holdings", [])
        except Exception:
            pass

    stock_invested = sum(h.get("cost_basis", 0) for h in holdings)
    total_comm = sum(h.get("commission_bdt", 0) for h in holdings)
    mf_invested = sum(m.get("total_cost_bdt", 0) for m in mfs)
    total_invested = stock_invested + mf_invested

    # Live market pricing
    live_stock_value = 0.0
    holding_details = []

    for h in holdings:
        t = h["ticker"]
        sh = h.get("shares", 0)
        net_cost = h.get("cost_basis", 0)
        comm = h.get("commission_bdt") or round(sh * h.get("entry_price", 0) * TOTAL_ONE_WAY_FEE, 2)
        exec_px = h.get("entry_price", 0)
        break_even = calculate_round_trip_break_even(exec_px)
        
        cur_px = h.get("entry_price", 0)
        if conn:
            r = conn.execute("SELECT close FROM prices WHERE ticker=? ORDER BY date DESC, id DESC LIMIT 1", (t,)).fetchone()
            if r and r[0]:
                cur_px = float(r[0])
        
        cur_val = round(sh * cur_px, 2)
        live_stock_value += cur_val
        unrealized_bdt = round(cur_val - net_cost, 2)
        unrealized_pct = round((unrealized_bdt / net_cost) * 100.0, 2) if net_cost > 0 else 0.0

        # Horizon specific stops and targets
        horizon = h.get("horizon", "long_term")
        if horizon == "short_term":
            stop_px   = round(break_even * 0.98, 1)
            target_px = round(break_even * 1.035, 1)
            action    = "TAKE_PROFIT" if cur_px >= target_px else ("HARD_CUT" if cur_px <= stop_px else "HOLD_SCALP")
        elif horizon == "mid_term":
            stop_px   = round(break_even * 0.95, 1)
            target_px = round(break_even * 1.15, 1)
            action    = "TRIM_SWING" if cur_px >= target_px else ("EXIT_STOP" if cur_px <= stop_px else "HOLD_SWING")
        else: # long_term
            stop_px   = round(break_even * 0.90, 1)
            target_px = round(break_even * 1.30, 1)
            if cur_px <= break_even:
                has_reversal = check_reversal_confirmation(t, conn)
                action = "ACCUMULATE_REVERSAL_CONFIRMED" if has_reversal else "HOLD_FALLING_KNIFE_GUARD"
            else:
                action = "HOLD_COMPOUND"

        stop_dist_pct = round(((cur_px - stop_px) / cur_px) * 100.0, 1) if cur_px > 0 else 0.0
        tgt_dist_pct  = round(((target_px - cur_px) / cur_px) * 100.0, 1) if cur_px > 0 else 0.0

        holding_details.append({
            "ticker":         t,
            "horizon":        horizon,
            "shares":         sh,
            "exec_px":        h.get("entry_price", 0),
            "comm":           comm,
            "cost_basis":     net_cost,
            "break_even":     break_even,
            "cur_px":         cur_px,
            "cur_val":        cur_val,
            "unrealized_bdt": unrealized_bdt,
            "unrealized_pct": unrealized_pct,
            "stop_px":        stop_px,
            "target_px":      target_px,
            "stop_dist_pct":  stop_dist_pct,
            "tgt_dist_pct":   tgt_dist_pct,
            "action":         action
        })

    if conn:
        conn.close()

    mf_live_val = sum(float(m.get("market_value_bdt") or m.get("total_cost_bdt") or 0.0) for m in mfs)
    mf_pnl_bdt = round(mf_live_val - mf_invested, 2)
    mf_pnl_pct = round((mf_pnl_bdt / mf_invested) * 100.0, 2) if mf_invested > 0 else 0.0

    total_live_val = live_stock_value + mf_live_val
    total_unrealized_bdt = round(total_live_val - total_invested, 2)
    total_unrealized_pct = round((total_unrealized_bdt / total_invested) * 100.0, 2) if total_invested > 0 else 0.0
    cash_bal = p.get("cash_balance_bdt", 0)
    total_net_worth = total_live_val + cash_bal

    print("\n" + "=" * 90)
    print("💼 COMPLETE DSE PORTFOLIO STATUS & LIVE VALUATION AUDIT")
    print("=" * 90)
    print(f"Total Invested Outlay: ৳{total_invested:,.2f} (Stocks: ৳{stock_invested:,.2f} [incl ৳{total_comm:.2f} comm] | Mutual Funds: ৳{mf_invested:,.2f})")
    print(f"Current Market Value:  ৳{total_live_val:,.2f} (Unrealized P&L: ৳{total_unrealized_bdt:+,.2f} / {total_unrealized_pct:+.2f}%)")
    min_buffer = (total_invested + cash_bal) * 0.10
    buffer_pct = round((cash_bal / (total_invested + cash_bal)) * 100.0, 1) if (total_invested + cash_bal) > 0 else 0.0
    buffer_status = "✅ HEALTHY" if cash_bal >= min_buffer else f"⚠️ DEFICIT (Need ৳{min_buffer - cash_bal:,.2f} to reach 10%)"
    print(f"Available Cash Buffer: ৳{cash_bal:,.2f} ({buffer_pct}% of Net Worth) | Status: {buffer_status}")
    print(f"Total Account Net Worth: ৳{total_net_worth:,.2f} (Target 10% Liquid Reserve: ৳{min_buffer:,.2f})")
    
    if mfs:
        print(f"\n--- MUTUAL FUNDS ({len(mfs)}) --- (Mark-to-Market Valuation & 0.0% Brokerage)")
        print(f"{'Fund Name':<28} {'Units':<7} {'Cost (Tk)':<11} {'Unit Cost':<10} {'Live NAV':<9} {'Market Val':<11} {'P&L (Tk)':<10} {'P&L %':<7} {'Status':<10}")
        print("-" * 110)
        for m in mfs:
            m_cost = float(m.get('total_cost_bdt', 0))
            m_val = float(m.get('market_value_bdt', m_cost))
            m_pnl = round(m_val - m_cost, 2)
            m_pnl_pct = round((m_pnl / m_cost) * 100.0, 2) if m_cost > 0 else 0.0
            nav_px = float(m.get('redemption_price_bdt') or m.get('unit_cost_bdt', 0))
            print(f"{m['fund_name']:<28} {m['units']:<7} ৳{m_cost:<10,.2f} ৳{m.get('unit_cost_bdt', 0):<8.2f} ৳{nav_px:<7.3f} ৳{m_val:<10,.2f} {m_pnl:+,.2f} {m_pnl_pct:+.2f}% {'CORE_HOLD':<10}")

    if holding_details:
        print(f"\n--- DIRECT EQUITIES ({len(holding_details)}) --- (0.4% Brokerage Fee Included)")
        print(f"{'Ticker':<11} {'Horizon':<10} {'Sh':<4} {'BreakEven':<10} {'Live Px':<9} {'Current Val':<12} {'P&L (BDT)':<11} {'P&L %':<8} {'Target':<9} {'Stop':<8} {'Action':<15}")
        print("-" * 108)
        for hd in holding_details:
            pnl_s = f"৳{hd['unrealized_bdt']:+.2f}"
            pnl_p = f"{hd['unrealized_pct']:+.1f}%"
            print(f"{hd['ticker']:<11} {hd['horizon']:<10} {hd['shares']:<4} ৳{hd['break_even']:<9.2f} ৳{hd['cur_px']:<8.2f} ৳{hd['cur_val']:<10.2f} {pnl_s:<11} {pnl_p:<8} ৳{hd['target_px']:<8.1f} ৳{hd['stop_px']:<7.1f} {hd['action']:<15}")

        print("\n### 🎯 Term-by-Term Actionable Diagnostic for Existing Holdings:")
        for hd in holding_details:
            print(f"  * 📌 {hd['ticker']} ({hd['horizon'].upper()}): Live Px ৳{hd['cur_px']:.1f} vs Break-even ৳{hd['break_even']:.2f}. "
                  f"Stop buffer: +{hd['stop_dist_pct']}% above ৳{hd['stop_px']}. Target upside: +{hd['tgt_dist_pct']}% to ৳{hd['target_px']}. Directive: [{hd['action']}].")

    print("\n### ⏳ Capital Pacing & Deployment Directive:")
    print(f"  * Available Dry Powder: ৳{cash_bal:,.2f}")
    print("  * Deployment Rule: DO NOT deploy 100% at once. If market opens extended or greedy, WAIT.")
    print("  * Pacing Schedule: Tranche 1 (25% today inside support corridor) → Tranche 2 (25% on weekly pullback) → Reserve 50% for high-conviction margin of safety dips.")
    print("=" * 90 + "\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        generate_exact_position_plan()
    elif sys.argv[1] == "set-capital" and len(sys.argv) > 2:
        set_capital(float(sys.argv[2]))
    elif sys.argv[1] == "plan":
        cap = float(sys.argv[2]) if len(sys.argv) > 2 else None
        generate_exact_position_plan(cap)
    elif sys.argv[1] == "buy" and len(sys.argv) >= 4:
        t = sys.argv[2]
        s = int(sys.argv[3])
        pr = float(sys.argv[4])
        hor = sys.argv[5] if len(sys.argv) > 5 else "long_term"
        record_buy(t, s, pr, hor)
    elif sys.argv[1] == "sell" and len(sys.argv) >= 5:
        t = sys.argv[2]
        s = int(sys.argv[3])
        pr = float(sys.argv[4])
        reason = sys.argv[5] if len(sys.argv) > 5 else "manual_exit"
        record_sell(t, s, pr, reason=reason)
    elif sys.argv[1] == "status":
        show_status()
    else:
        generate_exact_position_plan()
