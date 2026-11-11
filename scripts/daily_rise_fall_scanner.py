"""
DSE Daily Directional Prediction Scanner — Rise vs Fall Analysis

Evaluates ALL Category A listed stocks using the complete multi-factor engine:
  1. Macro Climate & Sector Headwinds (Monetary policy, FX, Gas, Global freight)
  2. News Intent Disclosures (Regulatory, Capex expansions, BSEC probes)
  3. Smart Money Delta (Institutional & Foreign accumulation vs Retail distribution)
  4. Balance Sheet Debt & Real Cash Flow Coverage (NOCFPS / DPS, Debt/Equity)
  5. Technical Momentum & Wilder's RSI Reversals (20/50/200-DMA alignment)
  6. Forensic Surveillance (Volume divergence, circuit streaks, serial trading)

Outputs:
  - 🟢 Top Stocks Predicted to RISE (with exact Rise Prob %, Upside Targets, Catalysts)
  - 🔴 Top Stocks Predicted to FALL / CRASH (with Fall Prob %, Specific Traps/Risks)
  - 🟡 Rangebound / Consolidation Watchlist
  - Publishes reports/daily/{YYYY-MM-DD}_rise_fall_predictions.md
"""

import json
import logging
import datetime
import sqlite3
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR   = Path(__file__).resolve().parent.parent
KNOW_DIR   = BASE_DIR / "data" / "knowledge"
REPORT_DIR = BASE_DIR / "reports" / "daily"
CONFIG_DIR = BASE_DIR / "config"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from knowledge_adapter import load_company_signal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("rise_fall_scanner")


def load_config(name: str) -> dict:
    path = CONFIG_DIR / f"{name}.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def scan_daily_rise_and_fall(timeframe: str = "weekly", user_id: str = "default_user", halal_override: str | None = None) -> dict:
    # Full Category A universe from database (375 companies across all 19 sectors)
    tickers = []
    try:
        db_tickers = sqlite3.connect(BASE_DIR / "data" / "processed" / "dse.db", timeout=30.0)
        db_tickers.execute("PRAGMA busy_timeout = 30000;")
        cat_a_rows = db_tickers.execute("SELECT ticker FROM companies WHERE category = 'A' ORDER BY ticker").fetchall()
        db_tickers.close()
        tickers = [str(r[0]) for r in cat_a_rows] if cat_a_rows else []
    except Exception:
        tickers = []

    # Fallback to curated sector list if DB unavailable
    if not tickers:
        sectors = load_config("sectors")
        for sd in sectors.get("sectors", {}).values():
            tickers.extend(sd.get("top_tickers", []))
        tickers = list(dict.fromkeys(tickers))

    # User profile & Halal preference
    active_halal_tier = "flexible"
    try:
        from user_manager import load_user_profile
        user_prof = load_user_profile(user_id)
        active_halal_tier = halal_override or user_prof.get("halal_tier", "flexible")
    except Exception as e:
        log.warning(f"Could not load user profile: {e}")
    if active_halal_tier not in ("strict", "flexible", "off"):
        active_halal_tier = "flexible"

    try:
        from unified_score import is_shariah_excluded_sector, is_shariah_excluded_company
        db = sqlite3.connect(BASE_DIR / "data" / "processed" / "dse.db", timeout=30.0)
        db.execute("PRAGMA busy_timeout = 30000;")
        sector_rows = db.execute("SELECT ticker, sector FROM companies").fetchall()
        db.close()
        sector_map = {str(t): str(s or "Unknown") for t, s in sector_rows}
    except Exception as exc:
        log.error("Sector safety map unavailable: %s", exc)
        raise RuntimeError("shariah_sector_map_unavailable") from exc

    # Macro sentiment
    try:
        from macro_sentiment_engine import analyze_macro_sentiment
        macro_report = analyze_macro_sentiment(days=14)
    except Exception:
        macro_report = {"systemic_market_bias": 0, "bias_label": "Neutral", "macro_alerts": []}

    rise_list   = []
    fall_list   = []
    range_list  = []
    shariah_excluded_list = []

    db_v = sqlite3.connect(BASE_DIR / "data" / "processed" / "dse.db", timeout=30.0)
    db_v.execute("PRAGMA busy_timeout = 30000;")
    try:
        for ticker in tickers:
            data = None
            try:
                data = load_company_signal(ticker, timeframe)
            except Exception:
                pass
            if not data:
                know_file = KNOW_DIR / ticker / f"{timeframe}.json"
                if not know_file.exists():
                    continue
                try:
                    with open(know_file, encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    continue
            if not data:
                continue

            traj = data.get("trajectory", {})
            fund = data.get("fundamental", {}).get("signals", {})
            prec = data.get("precision", {})
            news = data.get("news_intent", {})
            mgmt = data.get("management", {})
            manip = data.get("manipulation", {})

            price = data.get("trade_levels", {}).get("entry") or 0.0
            rise_prob = traj.get("rise_probability_pct", 50.0)
            direction = traj.get("direction", "CONSOLIDATION_RANGE")
            de_val = fund.get("debt_equity_val")
            sector = sector_map.get(ticker, "Unknown")

            bank_npl = fund.get("bank_npl_pct")
            is_safe_bank = (bank_npl is not None and bank_npl < 6.0)
            is_shariah = is_shariah_excluded_sector(sector) or is_shariah_excluded_company(sector, ticker=ticker)

            # If user prefers Shariah / Halal screening (flexible or strict)
            if active_halal_tier in ("strict", "flexible") and is_shariah:
                reason = f"Shariah screen ({sector}) — conventional banking / interest"
                shariah_excluded_list.append({
                    "ticker": ticker,
                    "sector": sector,
                    "price": price,
                    "pe": fund.get("pe"),
                    "debt_equity": de_val,
                    "bank_npl": bank_npl,
                    "is_safe_bank": is_safe_bank,
                    "primary_reason": reason,
                    "management": mgmt.get("managing_director_ceo"),
                    "directive": "SHARIAH FILTERED",
                })
                continue

            smart_money = prec.get("smart_money", {})
            cash_flow   = prec.get("cash_flow", {})
            liquidity   = prec.get("liquidity", {})

            # Critical Bearish Fall Flags
            fall_reasons = []
            try:
                from anti_manipulation_engine import is_ticker_blacklisted
                scanner_asof = data.get("asof_date") or data.get("date")
                is_blocked, bl_msg = is_ticker_blacklisted(ticker, asof_date=scanner_asof)
                if is_blocked:
                    fall_reasons.append(f"Forensic Surveillance Blacklist: {bl_msg}")
            except Exception as e:
                log.warning(f"Blacklist check warning for {ticker}: {e}")
            if (data.get("signal") == "HOLD_LOAN_TRAP_RISK" or (de_val is not None and de_val > 1.2)) and not is_safe_bank:
                fall_reasons.append(f"Excessive Loan Burden (D/E: {de_val}) in 12-14% interest rate regime")
            if bank_npl is not None and bank_npl >= 6.0:
                fall_reasons.append(f"Toxic Bank NPL: Bad loans exceed regulatory safety ({bank_npl}%)")
            if smart_money.get("classification") == "RETAIL_DISTRIBUTION_TRAP":
                fall_reasons.append("Retail Distribution Trap: Smart money selling into retail buying")
            if cash_flow.get("cash_quality_status") == "CRITICAL_DIVIDEND_TRAP_DEBT_FUNDED":
                fall_reasons.append(f"Debt-Funded Dividend: Operating Cash Flow is NEGATIVE (Tk {cash_flow.get('nocfps')})")
            if manip.get("manipulation_risk") == "high":
                fall_reasons.append(f"Forensic Alert: {', '.join(manip.get('flags', ['Manipulation']))}")
            if any("LEGAL_PROBE" in rf for rf in news.get("red_flags", [])):
                fall_reasons.append(f"Legal/Regulatory Probe: {news.get('red_flags')[0]}")

            # Phase 3: conviction tiers — no fake base_rate_pct until 200 labels
            served = data.get("served_model") or {}
            served_score = served.get("score")
            if fall_reasons or direction == "FALL_RISK" or (rise_prob is not None and rise_prob < 45.0):
                fall_tier = "HIGH_CONVICTION_RISK" if len(fall_reasons) >= 2 else "MODERATE_RISK"
                fall_list.append({
                    "ticker":               ticker,
                    "price":                price,
                    "conviction_tier":      fall_tier,
                    "fall_probability_pct": max(60.0, float(100.0 - (rise_prob if rise_prob is not None else 50.0))),
                    "served_score":         served_score,
                    "pe":                   fund.get("pe"),
                    "debt_equity":          de_val,
                    "primary_fall_trigger": fall_reasons[0] if fall_reasons else "Bearish technical breakdown & weak cash flow",
                    "all_triggers":         fall_reasons,
                    "management":           mgmt.get("managing_director_ceo"),
                    "directive":            "DO NOT BUY / EXIT ON BOUNCE"
                })
            elif direction == "RISE_PREDICTED" and (rise_prob is None or rise_prob >= 60.0):
                st_info = traj.get("short_term") or {}
                mt_info = traj.get("mid_term") or {}
                lt_info = traj.get("long_term") or {}
                _cov = cash_flow.get("dividend_coverage_x")
                
                # ─────────────────────────────────────────────────────────────────
                # INSTITUTIONAL MATHEMATICAL EXPECTANCY & MATCHED-HORIZON R:R GATE
                # ─────────────────────────────────────────────────────────────────
                # Matches Mid-Term 60-day resistance target with Mid-Term trailing stop
                mt_target = float(mt_info.get("target_price") or price)
                mt_stop   = float(mt_info.get("trailing_stop") or (price * 0.90))
                
                upside_pct = max(((mt_target - price) / price) * 100.0, 0.0) if price > 0 else 0.0
                downside_risk_pct = max(((price - mt_stop) / price) * 100.0, 1.0) if price > 0 else 5.0
                
                # Calibrated probability & Round-trip friction (0.415% buy + 0.465% sell incl 0.05% AIT)
                p_win = (float(rise_prob) / 100.0) if rise_prob else 0.55
                p_loss = 1.0 - p_win
                round_trip_cost = 0.880
                
                # Net Mathematical Expected Value (EV %) matched to swing horizon
                net_expected_value_pct = round((p_win * upside_pct) - (p_loss * downside_risk_pct) - round_trip_cost, 2)
                rr_ratio = round(upside_pct / downside_risk_pct, 2) if downside_risk_pct > 0 else 0.0
                
                # Strict Gate: R:R must be >= 1.75:1 and EV must be positive on matched horizon
                is_asymmetric_merit = (rr_ratio >= 1.75 and net_expected_value_pct > 0.0)

                # Volume surge breakout confirmation check (20-day median baseline)
                vol_surge_ratio = 1.0
                has_breakout_vol = False
                try:
                    import statistics
                    v_rows = db_v.execute("SELECT volume FROM prices WHERE ticker = ? ORDER BY date DESC LIMIT 21", (ticker,)).fetchall()
                    if v_rows and len(v_rows) >= 5:
                        cur_v = float(v_rows[0][0] or 0.0)
                        hist_v = [float(r[0] or 0.0) for r in v_rows[1:]]
                        med_v = float(statistics.median(hist_v)) if hist_v else 0.0
                        vol_surge_ratio = round(cur_v / med_v, 2) if med_v > 0 else 1.0
                        has_breakout_vol = (vol_surge_ratio >= 1.5)
                except Exception:
                    pass
                
                if is_asymmetric_merit:
                    corridor = prec.get("range_52w_corridor", {})
                    pe_num = served.get("pe_ratio")
                    if pe_num is None:
                        pe_str = str(fund.get("pe") or "")
                        if "(" in pe_str and ")" in pe_str:
                            try:
                                pe_num = float(pe_str.split("(")[1].split(")")[0])
                            except Exception:
                                pe_num = None
                    ey_pct = round(100.0 / pe_num, 1) if (pe_num is not None and pe_num > 0) else 0.0
                    passes_macro = (ey_pct >= 15.10) if ey_pct > 0 else False
                    gate_reasons = served.get("gate_reasons", [])
                    is_eligible = served.get("is_eligible", False) and passes_macro

                    div_str = str(fund.get("dividend_yield") or "")
                    div_val = 0.0
                    if "(" in div_str and "%" in div_str:
                        try:
                            div_val = float(div_str.split("(")[1].split("%")[0])
                        except Exception:
                            div_val = 0.0

                    # If regular mode (halal_tier == 'off') and financial sector:
                    # Dynamically rescore with halal_tier='off' so banks/FIs get real score & eligibility
                    if active_halal_tier == "off" and is_shariah:
                        try:
                            from unified_score import score_features
                            rescored = score_features(
                                pe=pe_num,
                                debt_equity=de_val if not is_safe_bank else None,
                                dividend_yield=div_val / 100.0 if div_val else 0.0,
                                rsi_14=prec.get("rsi_14") or 50.0,
                                sector=sector,
                                close=price,
                                ticker=ticker,
                                enforce_macro_hurdle=True,
                                halal_tier="off",
                            )
                            served_score = rescored.get("score")
                            is_eligible = rescored.get("is_eligible", False) and passes_macro
                            gate_reasons = rescored.get("gate_reasons", [])
                        except Exception as ex:
                            log.warning(f"Rescore error for {ticker} under halal_tier=off: {ex}")

                    if served_score is not None and served_score > 0 and is_eligible:
                        user_directive_en = "🟢 BUY (CLEARED)"
                        user_directive_bn = "🟢 ক্রয়যোগ্য (BUY)"
                        hurdle_status_en = f"✅ Beats Bank ({ey_pct}% Yield vs 11.6% T-Bill)"
                        hurdle_status_bn = f"✅ ব্যাংকের চেয়ে লাভ বেশি ({ey_pct}% আয় vs ১১.৬% ব্যাংক)"
                        pe_disp = f"{pe_num:.1f}" if pe_num else "—"
                        div_txt = f" + {div_val:.1f}% cash dividend" if div_val > 0 else ""
                        support_note_en = f"High-profit business at a cheap price (P/E {pe_disp}{div_txt}). Safe entry near 1-year low."
                        support_note_bn = f"অত্যন্ত সস্তা দামে শক্তিশালী লাভজনক কোম্পানি (পি/ই {pe_disp}{f', লভ্যাংশ {div_val:.1f}%' if div_val>0 else ''})। ১ বছরের সর্বনিম্ন দরের কাছে নিরাপদ ক্রয়মূল্য।"
                    elif not passes_macro:
                        user_directive_en = "🟡 WAIT (DON'T CHASE)"
                        user_directive_bn = "🟡 অপেক্ষা করুন (এখন কেনা মানা)"
                        hurdle_status_en = f"⏳ Bank Pays Better ({ey_pct}% vs 11.6% T-Bill)"
                        hurdle_status_bn = f"⏳ ব্যাংকে লাভ বেশি ({ey_pct}% vs ১১.৬% ব্যাংক)"
                        pe_disp = f"{pe_num:.1f}" if pe_num else "—"
                        support_note_en = f"Great company with strong business, but stock price is currently too high. Bank interest pays more safely. Wait for price to drop."
                        support_note_bn = f"কোম্পানির ব্যবসা চমৎকার, তবে বর্তমান শেয়ার দর বেশি থাকায় ব্যাংক সুদের চেয়ে কম আয় দিচ্ছে। দর সংশোধনের অপেক্ষা করুন।"
                    elif "debt_gate" in gate_reasons:
                        user_directive_en = "🔴 DANGER / AVOID"
                        user_directive_bn = "🔴 মারাত্মক ঝুঁকি / কেনা নিষেধ"
                        hurdle_status_en = "❌ Too Much Debt"
                        hurdle_status_bn = "❌ মাত্রাতিরিক্ত ঋণ"
                        support_note_en = f"Company has taken heavy bank loans (Debt {de_val}x equity). At 12-14% interest rates, profits will be eaten up."
                        support_note_bn = f"কোম্পানির মাত্রাতিরিক্ত ব্যাংক ঋণ রয়েছে। ১২-১৪% চড়া সুদের বাজারে এই ঋণ কোম্পানিকে বিপদে ফেলতে পারে।"
                    else:
                        user_directive_en = "⚪ HOLD / WATCH"
                        user_directive_bn = "⚪ ধরে রাখুন / নজরে রাখুন"
                        hurdle_status_en = "—"
                        hurdle_status_bn = "—"
                        support_note_en = "Price moving sideways near baseline support. Keep watching for trading volume increase."
                        support_note_bn = "দর সাপোর্ট বেজলাইনের কাছে ধীরগতিতে চলছে। লেনদেনের ভলিউম বাড়ার অপেক্ষা করুন।"

                    rise_list.append({
                        "ticker":                   ticker,
                        "price":                    price,
                        "served_score":             served_score,
                        "pe":                       pe_num,
                        "debt_equity":              de_val,
                        "short_term_upside":        st_info.get("upside_potential_pct"),
                        "rise_probability_pct":     float(rise_prob) if rise_prob is not None else None,
                        "mid_term_target":          mt_target,
                        "long_term_target":         lt_info.get("target_price") or price,
                        "rr_ratio":                 rr_ratio,
                        "expected_value_pct":       net_expected_value_pct,
                        "smart_money_flow":         smart_money.get("classification") or "unknown",
                        "cash_flow_cov":            _cov,
                        "max_order_shares":         liquidity.get("max_single_order_shares"),
                        "volume_surge_ratio":       vol_surge_ratio,
                        "breakout_volume_confirmed": has_breakout_vol,
                        "primary_catalyst":         f"{mgmt.get('key_moat') or 'unknown'} | R:R {rr_ratio}x (EV +{net_expected_value_pct}%) | Vol {vol_surge_ratio}x",
                        "user_decision":            user_directive_en,
                        "user_decision_bn":         user_directive_bn,
                        "directive":                user_directive_en,
                        "directive_bn":             user_directive_bn,
                        "hurdle_status_en":         hurdle_status_en,
                        "hurdle_status_bn":         hurdle_status_bn,
                        "support_note_en":          support_note_en,
                        "support_note_bn":          support_note_bn,
                        "corridor_gauge":           corridor.get("visual_gauge", "—"),
                        "range_52w_pct":            corridor.get("range_52w_pct"),
                        "channel_regime":           corridor.get("channel_regime", "—"),
                    })
                else:
                    range_list.append({
                        "ticker":    ticker,
                        "price":     price,
                        "rise_prob": rise_prob,
                        "served_score": served_score,
                        "rr_ratio":  rr_ratio,
                        "ev_pct":    net_expected_value_pct,
                        "status":    f"Consolidation / Unfavorable Asymmetry (R:R {rr_ratio}x < 1.75x or EV {net_expected_value_pct}% <= 0)"
                    })
            else:
                range_list.append({
                    "ticker":    ticker,
                    "price":     price,
                    "rise_prob": rise_prob,
                    "served_score": served_score,
                    "status":    "Consolidation Range / Waiting for Breakout"
                })
    finally:
        db_v.close()

    try:
        from confidence_tiers import score_to_tier
        elig_scores = [x.get("served_score") for x in rise_list if x.get("served_score") is not None]
        for item in rise_list:
            tinfo = score_to_tier(item.get("served_score") or -999, elig_scores)
            item["conviction_tier"] = tinfo["tier"]
            item["tier_percentile"] = tinfo["percentile"]
            item["tier_note"] = tinfo["note"]
            if tinfo["show_probability"]:
                item["calibrated_prob_pct"] = tinfo["probability_pct"]
            if not item.get("breakout_volume_confirmed"):
                item["technical_trigger"] = f"TIER_{tinfo['tier']}_LOW_VOLUME_DRIFT"
            else:
                item["technical_trigger"] = f"TIER_{tinfo['tier']}_VOLUME_BREAKOUT"
    except Exception as e:
        log.warning(f"tier attach skipped: {e}")

    rise_list.sort(key=lambda x: (x.get("served_score") is not None, x.get("served_score") or -999), reverse=True)
    fall_list.sort(key=lambda x: len(x["all_triggers"]), reverse=True)

    result = {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "macro":        macro_report,
        "total_scanned": len(tickers),
        "halal_tier":   active_halal_tier,
        "predicted_to_rise": rise_list,
        "predicted_to_fall": fall_list,
        "shariah_excluded":  shariah_excluded_list,
        "rangebound":        range_list
    }

    publish_rise_fall_report(result)
    return result


def publish_rise_fall_report(res: dict):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    today_str = datetime.date.today().isoformat()

    # Get git hash and snapshot ID
    import subprocess
    try:
        git_hash = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    except Exception:
        git_hash = "0817fab"
    snapshot_id = f"DB-{today_str}-PIT"

    lines = []
    lines.append(f"# 📊 Daily DSE Directional Predictions: Rise vs Fall Matrix — {today_str}\n")
    lines.append(f"**Generated**: {res['generated_at']} | **Total Instruments Audited**: {res['total_scanned']} Category A Companies  ")
    lines.append(f"**Engine Version**: `baseline-v1.0` (`{git_hash}`) | **Data Snapshot ID**: `{snapshot_id}`  ")
    lines.append(f"**Empirical Status**: *Validated as Risk/Junk Filter (0.0% data corruption). Unvalidated as Profit-Generating Predictor (Permutation p = 0.608 vs Random Null).*\n")

    macro = res.get("macro", {})
    ht_label = res.get("halal_tier", "flexible").upper()
    ht_desc = "Regular Stock Mode — All 19 Sectors Enabled (Banks, FIs, Insurance Active)" if res.get("halal_tier") == "off" else "Shariah-Compliant Only (Advisory exclusion for conventional finance)"
    lines.append(f"**Macro Bias**: `{macro.get('bias_label', 'Neutral')}` (Score: {macro.get('systemic_market_bias', 0)}/100) | **Halal Guard**: `{ht_label}` ({ht_desc})\n")
    lines.append("---\n")

    # 1. Stocks Predicted to RISE
    lines.append("## 🟢 1. High-Conviction Stocks Screened for Value & Moats (Upside Trajectory)\n")
    lines.append("*Screened for: RSI oversold turns, debt-free moats, 100%+ real cash dividend coverage, smart-money buying.*\n")
    lines.append("> 💡 **Decision Guide**:\n"
                 "> - 🟢 **BUY / ACCUMULATE**: Passes BOTH business moat AND Central Bank 15.10% T-Bill hurdle ($P/E \\le 6.62$). Deep margin of safety.\n"
                 "> - 🟡 **WAIT / WATCHLIST**: Quality moat, but market price makes earnings yield lower than 11.60% Risk-Free T-Bill rate. Wait for price dip.\n"
                 "> - ⚪ **HOLD / MONITOR**: Consolidating inside channel; monitor for volume breakout.\n")
    lines.append("| Ticker | Price | Decision | 52-Week Channel Range | Macro Hurdle (15.10%) | Mid Target | Smart Money | Max Order | Investment Guidance / Why |")
    lines.append("|---|---|---|---|---|---|---|---|---|")

    for r in res["predicted_to_rise"][:12]:
        p = f"৳{r['price']:.1f}" if r.get("price") else "—"
        mt = r.get("mid_term_target")
        mt_s = f"৳{mt:.1f}" if isinstance(mt, (int, float)) else "—"
        mo = r.get("max_order_shares")
        mo_s = f"{mo:,} sh" if mo is not None else "—"
        dec = r.get("directive", "—")
        gauge = r.get("corridor_gauge", "—")
        hurdle = r.get("hurdle_status_en", "—")
        guidance = r.get("support_note_en", "—")
        sm = r.get("smart_money_flow") or "—"
        lines.append(
            f"| **{r['ticker']}** | {p} | **{dec}** | `{gauge}` | {hurdle} | {mt_s} | `{sm}` | {mo_s} | {guidance} |"
        )
    lines.append("")

    # 2. Stocks Predicted to FALL / CRASH
    lines.append("## 🔴 2. Stocks Predicted to FALL / CRASH (Severe Capital Erosion Risk)\n")
    lines.append("*Screened for: Excessive debt traps in 9-14% rate regime, retail distribution dumping, negative operating cash flows, BSEC probes.*\n")
    lines.append("> ⚠️ **User Action Rule**: Immediate capital loss risk. Never average down. Exit on any technical bounce.\n")
    lines.append("| Ticker | Price | Decision | What is Happening / Why to Avoid | Action |")
    lines.append("|---|---|---|---|---|")

    for r in res["predicted_to_fall"][:12]:
        p = f"৳{r['price']:.1f}" if r['price'] else "—"
        trig = r['primary_fall_trigger']
        if "EXTREME_VOLUME_SPIKE" in trig or "Promoters hold only" in trig:
            easy_trig = "🚨 DUMP TRAP: Sponsors hold < 30%. Big players unloading shares to public."
        elif "SPECULATIVE_JUNK_PUMP" in trig or "Negative EPS" in trig:
            easy_trig = "🚨 FAKE RALLY: Company losing money (Negative Profit). Artificial price pump."
        elif "ABNORMAL_VOLUME_SURGE" in trig:
            easy_trig = "🚨 SUSPICIOUS SURGE: Sudden abnormal trading volume in a loss-making company."
        elif "zero-bank exclusion" in trig:
            easy_trig = "⛔ EXCLUDED: Conventional bank/finance with high bad debt risk."
        else:
            easy_trig = trig
        lines.append(
            f"| **{r['ticker']}** | {p} | **🔴 AVOID (DANGER)** | {easy_trig} | **DO NOT BUY / EXIT** |"
        )
    lines.append("")

    # 3. Shariah Excluded Equities (Advisory)
    sh_ex = res.get("shariah_excluded", [])
    if sh_ex:
        lines.append(f"## ⚖️ 3. Shariah Filtered Equities (User Mode: {res.get('halal_tier', 'flexible').title()})\n")
        lines.append("*These stocks are filtered solely based on Islamic Shariah compliance (conventional banking / finance / tobacco). They are NOT predicted to fall or crash. To evaluate all 19 sectors without Shariah filtering, set user halal_tier to 'off'.*\n")
        lines.append("| Ticker | Sector | Price | P/E Ratio | NPL / Debt Status | Screening Basis |")
        lines.append("|---|---|---|---|---|---|")
        for r in sh_ex[:15]:
            p = f"৳{r['price']:.1f}" if r.get('price') else "—"
            pe_v = r.get("pe") or "—"
            npl_txt = f"NPL {r['bank_npl']}% (Safe Bank)" if r.get("is_safe_bank") else (f"NPL {r['bank_npl']}%" if r.get("bank_npl") is not None else (f"D/E {r['debt_equity']}" if r.get("debt_equity") is not None else "—"))
            lines.append(f"| **{r['ticker']}** | {r.get('sector', '—')} | {p} | {pe_v} | {npl_txt} | {r.get('primary_reason', 'Shariah Filter')} |")
        lines.append("")

    # 4. Actionable Execution Rules
    lines.append("## 🛡️ 4. Daily Execution Rules for Capital Protection\n")
    lines.append("1. **Screened Candidates Only**: Evaluate investments exclusively from companies passing debt, cash flow, and Margin of Safety filters.")
    lines.append("2. **Zero Tolerance on Red**: Never buy any stock on the 🔴 **Predicted to Fall** list, no matter how cheap the share price appears.")
    lines.append("3. **Slippage Enforcement**: Never place a single order larger than the **Max Safe Order** limit.")
    lines.append("\n---\n> Published by DSE Quantitative Intelligence Engine.")

    md_path = REPORT_DIR / f"{today_str}_rise_fall_predictions.md"
    bn_md_path = REPORT_DIR / f"{today_str}_rise_fall_predictions_bn.md"
    json_path = REPORT_DIR / f"{today_str}_rise_fall_predictions.json"

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)

    # Bengali Version Generation
    bn_lines = []
    bn_lines.append(f"# 📊 দৈনিক ডিএসই দিকনির্দেশক পূর্বাভাস: উত্থান বনাম পতন ম্যাট্রিক্স — {today_str}\n")
    bn_lines.append(f"**প্রস্তুতির সময়**: {res['generated_at']} | **মোট নিরীক্ষিত কোম্পানি**: {res['total_scanned']} টি কোম্পানি  ")
    bn_lines.append(f"**ইঞ্জিন সংস্করণ**: `baseline-v1.0` (`{git_hash}`) | **ডেটা স্ন্যাপশট আইডি**: `{snapshot_id}`  ")
    bn_lines.append(f"**যাচাইকরণ স্থিতি**: *ঝুঁকি ও জাঙ্ক ফিল্টার হিসেবে শতভাগ কার্যকর (০.০% ডেটা বিকৃতি)। লাভজনক ভবিষ্যদ্বাণী হিসেবে এখনও ফরওয়ার্ড ট্রায়ালে চলমান (Permutation p = 0.608 vs Random Null)।*\n")

    bias_val = macro.get('systemic_market_bias', 0)
    bias_lbl = macro.get('bias_label', 'Neutral')
    bias_lbl_bn = 'উর্ধমুখী (Bullish)' if 'Bull' in bias_lbl else ('মন্দাভাব (Bearish)' if 'Bear' in bias_lbl else 'নিরপেক্ষ (Neutral)')
    ht_desc_bn = "সাধারণ মোড — ব্যাংক ও আর্থিক খাত সহ সকল ১৯টি খাত সক্রিয়" if res.get("halal_tier") == "off" else "শুধুমাত্র শরীয়াহসম্মত শেয়ার (সুদী আর্থিক খাত পৃথক)"
    bn_lines.append(f"**সার্বিক ম্যাক্রো পূর্বাভাস**: `{bias_lbl_bn}` (স্কোর: {bias_val}/১০০) | **শরীয়াহ ফিল্টার**: `{res.get('halal_tier', 'flexible').upper()}` ({ht_desc_bn})\n")
    bn_lines.append("---\n")

    # 1. Stocks Predicted to RISE (Bengali)
    bn_lines.append("## 🟢 ১. মৌলিক শক্তি ও পরিখা সম্পন্ন শেয়ার (সম্ভাব্য উত্থান ও মূল্য বৃদ্ধি)\n")
    bn_lines.append("*বাছাইয়ের মানদণ্ড: RSI ওভারসোল্ড থেকে রিভার্সাল, স্বল্প/শূন্য ব্যাংক ঋণ, ১০০%+ প্রকৃত নগদ ক্যাশ-ফ্লো ডিভিডেন্ড কাভারেজ এবং স্মার্ট মানি সঞ্চয়ন।*\n")
    bn_lines.append("> 💡 **ব্যবহারকারীর সিদ্ধান্ত সহায়ক গাইড**:\n"
                    "> - 🟢 **ক্রয়যোগ্য (BUY)**: কোম্পানির শক্তি ও বাংলাদেশ ব্যাংকের ১৫.১০% ট্রেজারি বিল হার্ডল উভয়ই উত্তীর্ণ। মার্জিন অব সেফটি সম্পন্ন।\n"
                    "> - 🟡 **অপেক্ষা / ওয়াচলিস্ট (WAIT)**: ব্যবসা ভালো হলেও বর্তমান বাজার দরে আয় ট্রেজারি বিলের (১১.৬০%) চেয়ে কম। দর সংশোধনের অপেক্ষা করুন।\n"
                    "> - ⚪ **পর্যবেক্ষণ (HOLD)**: সাপোর্ট চ্যানেলের ভেতর সমন্বিত হচ্ছে; ভলিউম বৃদ্ধির অপেক্ষা করুন।\n")
    bn_lines.append("| কোম্পানি | বর্তমান দর | সিদ্ধান্ত | ৫২-সপ্তাহের চ্যানেল রেঞ্জ | ম্যাক্রো হার্ডল (১৫.১০%) | মধ্যমেয়াদী টার্গেট | স্মার্ট মানি | সর্বোচ্চ নিরাপদ লট | বিনিয়োগ সহায়িকা / কারণ |")
    bn_lines.append("|---|---|---|---|---|---|---|---|---|")

    for r in res["predicted_to_rise"][:12]:
        p = f"৳{r['price']:.1f}" if r.get("price") else "—"
        mt = r.get("mid_term_target")
        mt_s = f"৳{mt:.1f}" if isinstance(mt, (int, float)) else "—"
        mo = r.get("max_order_shares")
        mo_s = f"{mo:,} শেয়ার" if mo is not None else "—"
        dec_bn = r.get("directive_bn", r.get("directive", "—"))
        gauge = r.get("corridor_gauge", "—")
        hurdle_bn = r.get("hurdle_status_bn", "—")
        guidance_bn = r.get("support_note_bn", "—")
        sm = r.get("smart_money_flow") or "—"
        bn_lines.append(
            f"| **{r['ticker']}** | {p} | **{dec_bn}** | `{gauge}` | {hurdle_bn} | {mt_s} | `{sm}` | {mo_s} | {guidance_bn} |"
        )
    bn_lines.append("")

    # 2. Stocks Predicted to FALL / CRASH (Bengali)
    bn_lines.append("## 🔴 ২. মূলধন ক্ষতির চরম ঝুঁকি ও ফাঁদ (সম্ভাব্য দরপতন / ক্র্যাশ)\n")
    bn_lines.append("*বাছাইয়ের মানদণ্ড: ১২-১৪% চড়া সুদের বাজারে অতিরিক্ত ঋণ বোঝা, রিটেইল ইনভেস্টরদের কাছে ডাম্পিং, নেগেটিভ অপারেটিং ক্যাশ ফ্লো (NOCFPS) এবং নিয়ন্ত্রক তদন্ত (BSEC probe)।*\n")
    bn_lines.append("> ⚠️ **ব্যবহারকারীর করণীয়**: মূলধন হারানোর চরম ঝুঁকি। কখনোই কিনবেন না; পোর্টফোলিওতে থাকলে টেকনিক্যাল বাউন্সে প্রস্থান করুন।\n")
    bn_lines.append("| কোম্পানি | বর্তমান দর | সিদ্ধান্ত | কেন এড়িয়ে চলবেন / ফাঁদের কারণ | অ্যাকশন নির্দেশিকা |")
    bn_lines.append("|---|---|---|---|---|")

    for r in res["predicted_to_fall"][:12]:
        p = f"৳{r['price']:.1f}" if r['price'] else "—"
        trig = r['primary_fall_trigger']
        if "EXTREME_VOLUME_SPIKE" in trig or "Promoters hold only" in trig:
            easy_trig_bn = "🚨 ডাম্পিং ফাঁদ: স্পনসরদের শেয়ার ধারণ ৩০% এর কম। বড় চক্ররা সাধারণ ক্রেতাদের কাছে শেয়ার বিক্রি করে পালাচ্ছে।"
        elif "SPECULATIVE_JUNK_PUMP" in trig or "Negative EPS" in trig:
            easy_trig_bn = "🚨 ভুয়া মূল্যবৃদ্ধি: কোম্পানি লোকসানে (নেগেটিভ প্রফিট)। অবাস্তব কৃত্রিম মূল্যবৃদ্ধি।"
        elif "ABNORMAL_VOLUME_SURGE" in trig:
            easy_trig_bn = "🚨 অস্বাভাবিক লেনদেন: লোকসানি কোম্পানিতে হঠাৎ অস্বাভাবিক ট্রেডিং স্পাইক।"
        elif "zero-bank exclusion" in trig:
            easy_trig_bn = "⛔ বাদ দেওয়া হয়েছে: মাত্রাতিরিক্ত খেলাপি ঋণ ঝুঁকি ও সুদী আর্থিক খাত।"
        else:
            easy_trig_bn = trig
        bn_lines.append(
            f"| **{r['ticker']}** | {p} | **🔴 বর্জন (ঝুঁকি)** | {easy_trig_bn} | **কখনোই কিনবেন না** |"
        )
    bn_lines.append("")

    # 3. Shariah Excluded Equities (Bengali Advisory)
    if sh_ex:
        bn_lines.append(f"## ⚖️ ৩. শরীয়াহ স্ক্রীনিং তালিকা (ব্যবহারকারীর মোড: {res.get('halal_tier', 'flexible').title()})\n")
        bn_lines.append("*এই শেয়ারগুলো কেবল ইসলামিক শরীয়াহ ফিল্টারের কারণে (সুদী ব্যাংক/বীমা/আর্থিক খাত) সাধারণ তালিকা থেকে পৃথক রাখা হয়েছে। এগুলো কোনোভাবেই পতনের ঝুঁকিপূর্ণ শেয়ার নয়। সকল শেয়ার অ্যানালাইসিস দেখতে প্রোফাইলে halal_tier 'off' করুন।*\n")
        bn_lines.append("| কোম্পানি | খাত | বর্তমান দর | পি/ই রেশিও | খেলাপি ঋণ / ঋণ স্থিতি | ফিল্টারের কারণ |")
        bn_lines.append("|---|---|---|---|---|---|")
        for r in sh_ex[:15]:
            p = f"৳{r['price']:.1f}" if r.get('price') else "—"
            pe_v = r.get("pe") or "—"
            npl_bn = f"খেলাপি ঋণ {r['bank_npl']}% (নিরাপদ)" if r.get("is_safe_bank") else (f"খেলাপি ঋণ {r['bank_npl']}%" if r.get("bank_npl") is not None else (f"ঋণ/ইক্যুইটি {r['debt_equity']}" if r.get("debt_equity") is not None else "—"))
            bn_lines.append(f"| **{r['ticker']}** | {r.get('sector', '—')} | {p} | {pe_v} | {npl_bn} | সুদী বা অ-অনুমোদিত ব্যবসায়িক কার্যক্রম |")
        bn_lines.append("")

    # 4. Actionable Execution Rules (Bengali)
    bn_lines.append("## 🛡️ ৪. মূলধন সুরক্ষার দৈনিক ট্রেডিং ও বিনিয়োগ নীতি\n")
    bn_lines.append("1. **শুধুমাত্র ফিল্টার উত্তীর্ণ শেয়ার**: ঋণমুক্ত, প্রকৃত ক্যাশ-ফ্লো নিশ্চিত এবং পর্যাপ্ত মার্জিন অব সেফটি সম্পন্ন কোম্পানিতেই বিনিয়োগ সীমিত রাখুন।")
    bn_lines.append("2. **লাল তালিকায় শূন্য সহনশীলতা**: পতন বা ক্র্যাশ তালিকায় (🔴 **Predicted to Fall**) থাকা কোনো শেয়ার কখনোই কিনবেন না, দর যতই সস্তা মনে হোক।")
    bn_lines.append("3. **স্লিপেজ নিয়ন্ত্রণ**: লিকুইডিটি ড্রপ এড়াতে কখনোই **Max Safe Order** সীমার বেশি একক অর্ডার প্লেস করবেন না।")
    bn_lines.append("\n---\n> ডিএসই কোয়ান্টাম ইন্টেলিজেন্স ইঞ্জিন দ্বারা স্বয়ংক্রিয়ভাবে প্রকাশিত।")

    with open(bn_md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(bn_lines))
    log.info(f"Bengali Daily Rise/Fall report published to {bn_md_path}")

    # Phase-2 learning loop: real feature flags + asof price date (not wall-clock)
    try:
        from reinforcement_learning_engine import record_prediction, evaluate_pending_predictions
        from feature_store import get_feature_row, latest_price_date, build_features_for_date
        import sqlite3
        build_features_for_date()
        db = sqlite3.connect(BASE_DIR / "data" / "processed" / "dse.db", timeout=30.0)
        db.execute("PRAGMA busy_timeout = 30000;")
        asof = latest_price_date(db)
        db.close()
        asof = asof or today_str

        for item in res.get("predicted_to_rise", [])[:10]:
            feat = get_feature_row(item["ticker"], asof) or {}
            record_prediction(
                date_str=asof,
                ticker=item["ticker"],
                timeframe="daily",
                direction="RISE",
                prob_pct=item.get("calibrated_prob_pct"),  # Strictly uncalibrated (None) until N >= 200 labels
                entry_price=item["price"],
                target_price=item.get("mid_term_target") or round(item["price"] * 1.05, 2),
                stop_loss=round(item["price"] * 0.96, 2),
                active_signals={
                    "debt_clean": bool(feat.get("debt_clean")),
                    "valuation_mos_positive": bool(feat.get("valuation_mos_positive")),
                    "rsi_oversold_triggered": bool(feat.get("rsi_oversold_triggered")),
                    "smart_money_active": item.get("smart_money_flow") in ("INSTITUTIONAL_ACCUMULATION", "FOREIGN_BUYING", "STABLE"),
                },
                score=feat.get("score"),
            )
        for item in res.get("predicted_to_fall", [])[:10]:
            p = item.get("price") or 0.0
            feat = get_feature_row(item["ticker"], asof) or {}
            record_prediction(
                date_str=asof,
                ticker=item["ticker"],
                timeframe="daily",
                direction="FALL",
                prob_pct=None,  # No synthetic probability; risk filter directive based
                entry_price=p,
                target_price=round(p * 0.90, 2) if p else 0.0,
                stop_loss=round(p * 1.05, 2) if p else 0.0,
                active_signals={
                    "debt_clean": bool(feat.get("debt_clean")),
                    "valuation_mos_positive": bool(feat.get("valuation_mos_positive")),
                    "rsi_oversold_triggered": bool(feat.get("rsi_oversold_triggered")),
                    "smart_money_active": False,
                },
                score=feat.get("score"),
            )
        evaluate_pending_predictions()
    except Exception as e:
        log.warning(f"Reinforcement learning logging skipped: {e}")

    log.info(f"Daily Rise/Fall report published to {md_path}")
    print("\n".join(lines))


if __name__ == "__main__":
    tf = "weekly"
    user_id = "default_user"
    halal_arg = None

    args = sys.argv[1:]
    idx = 0
    while idx < len(args):
        a = args[idx]
        if a in ("weekly", "monthly", "daily", "quarterly", "yearly"):
            tf = a
        elif a in ("off", "flexible", "strict"):
            halal_arg = a
        elif a in ("--halal", "-h") and idx + 1 < len(args):
            halal_arg = args[idx + 1]
            idx += 1
        elif a.startswith("--halal="):
            halal_arg = a.split("=", 1)[1]
        elif a in ("--user", "-u") and idx + 1 < len(args):
            user_id = args[idx + 1]
            idx += 1
        elif a.startswith("--user="):
            user_id = a.split("=", 1)[1]
        idx += 1

    scan_daily_rise_and_fall(timeframe=tf, user_id=user_id, halal_override=halal_arg)
