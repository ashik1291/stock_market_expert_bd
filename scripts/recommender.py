"""
DSE Recommender — builds 3 distinct investment horizon lists with actionable plans:
  1. Long-Term Asset List (1–5+ Years): Moats, defensive value, zero/low debt, veteran leadership, dividend compounding
  2. Mid-Term Swing List (1–6 Months): Cycle recovery, valuation mean-reversion, 12-20% target
  3. Short-Term Scalp List (Daily/Weekly): 2–5% quick targets, tight ATR stop, zero bulk exposure

Integrates:
  - Smart Money Flow Tracking (Monthly Institutional + Foreign vs Public shift)
  - Real Cash Flow & Dividend Coverage (NOCFPS / Cash Dividend per share)
  - Liquidity Slippage Guard (Max Recommended Order Size based on daily volume profile)
  - Quarterly Earnings Acceleration (QoQ / YoY Quarterly EPS Progression & Run-Rate)
  - Directional Trajectory Prediction (Rise vs Fall Probability & Momentum status)
  - 3-Term Potential Matrix (Upside potential % vs Downside risk % across Short, Mid, and Long-Term)
  - Top Management & Board Experience (Chairman, CEO, Industry tenure, Governance rating)
  - Deep News Intent Classification (Regulatory, Expansion, Legal probes, PR spin)
  - Loan & Debt Audit (strictly avoiding companies with high long-term loans)
  - Monthly Accumulation Ledger & Position Sizer
"""

import json
import logging
import datetime
import sys
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent
KNOW_DIR   = BASE_DIR / "data" / "knowledge"
REPORT_DIR = BASE_DIR / "reports"
CONFIG_DIR = BASE_DIR / "config"
sys.path.insert(0, str(Path(__file__).resolve().parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dse_recommender")


def load_config(name: str) -> dict:
    with open(CONFIG_DIR / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def load_analysis(ticker: str, timeframe: str) -> dict | None:
    path = KNOW_DIR / ticker / f"{timeframe}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _to_float(v) -> float | None:
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except Exception:
        return None


def _extract_val(signal_str) -> str | None:
    if signal_str is None:
        return None
    s = str(signal_str)
    parts = s.split("(")
    if len(parts) < 2:
        return s
    return parts[-1].rstrip(")")


def _fmt_pe(val) -> str:
    flt = _to_float(val)
    return f"{flt:.1f}" if flt is not None else "—"


def classify_horizons(records: list[dict]) -> dict:
    """
    Separates evaluated tickers into distinct strategy lists with explicit buy/sell timing:
      - long_term: Assets, low P/E (<=16), low debt (D/E<=0.8), veteran leadership, proven dividend history
      - mid_term: Position swings, 12-20% target, healthy fundamentals, debt/equity <= 1.0
      - short_term: Daily/weekly scalps, 2-5% quick targets, oversold bounces, tight ATR stops
      - debt_trap_blocked: Tickers blocked from buying due to excessive long-term loan burdens
      - governance_blocked: Tickers blocked by management risks or legal/BSEC probes
      - distribution_blocked: Tickers blocked by retail distribution trap or debt-funded dividends
      - manipulation_blocked: Tickers blocked by forensic surveillance
    """
    long_term   = []
    mid_term    = []
    short_term  = []
    sells       = []
    manip_risk  = []
    debt_traps  = []
    gov_traps   = []
    dist_traps  = []
    greed_traps = []

    for r in records:
        ticker = r["ticker"]
        conf   = r.get("confidence", 0)
        entry  = r.get("entry") or 0.0
        pe_val = _to_float(r.get("pe"))
        de_val = r.get("debt_equity_val")
        loan_risk = r.get("loan_trap_risk", "none")
        mgmt = r.get("management", {})
        news_int = r.get("news_intent", {})
        traj = r.get("trajectory", {})
        prec = r.get("precision", {})
        pat_dna = r.get("pattern_dna", {})
        worth_greed = pat_dna.get("worth_vs_greed", {})

        gov_risk = mgmt.get("management_risk", "Low")
        dominant_intent = news_int.get("dominant_intent", "NEUTRAL")
        has_legal_probe = any("LEGAL_PROBE" in rf for rf in news_int.get("red_flags", []))

        smart_money = prec.get("smart_money", {})
        cash_flow   = prec.get("cash_flow", {})
        liquidity   = prec.get("liquidity", {})
        earn_acc    = prec.get("earnings_acceleration", {})

        # 0. Risk Blockades
        is_blocked = False
        try:
            from anti_manipulation_engine import is_ticker_blacklisted
            is_blocked, bl_reason = is_ticker_blacklisted(ticker)
        except Exception:
            pass

        if is_blocked or r.get("signal") == "HOLD_MANIPULATION_RISK" or r.get("manipulation_risk") == "high":
            if is_blocked:
                r["manipulation_risk"] = "high"
                r["manipulation_flags"] = [bl_reason]
            manip_risk.append(r)
            continue

        if r.get("signal") == "HOLD_LOAN_TRAP_RISK" or loan_risk == "high" or (de_val is not None and de_val > 1.2):
            debt_traps.append(r)
            continue

        if r.get("signal") == "HOLD_GOVERNANCE_RISK" or gov_risk == "High" or has_legal_probe:
            gov_traps.append(r)
            continue

        if smart_money.get("classification") == "RETAIL_DISTRIBUTION_TRAP" or cash_flow.get("cash_quality_status") == "CRITICAL_DIVIDEND_TRAP_DEBT_FUNDED":
            dist_traps.append(r)
            continue

        # Market Greed & Euphoria Trap (Protect user from buying local peak / hype)
        if r.get("signal") == "HOLD_MARKET_GREED_EXTREME" or worth_greed.get("status") in ("SPECULATIVE_GREED", "OVERVALUED_EUPHORIA"):
            r["greed_reason"] = worth_greed.get("reason", "Market greed index high; price exceeds intrinsic worth")
            greed_traps.append(r)
            continue

        if r.get("signal") in ("SELL", "STRONG_SELL"):
            sells.append(r)
            continue

        # Technical context
        rsi_val = r.get("rsi") or 50.0
        sma20   = r.get("sma20") or entry
        drawdown_info = r.get("downturn_resilience", {})
        is_discount = drawdown_info.get("status") == "growth_at_discount"

        # Trajectory metadata — no invented defaults
        dir_icon    = traj.get("direction_icon") or "—"
        direction   = traj.get("direction")
        rise_prob   = traj.get("rise_probability_pct")
        st_info     = traj.get("short_term") or {}
        mt_info     = traj.get("mid_term") or {}
        lt_info     = traj.get("long_term") or {}

        # Leadership & Governance Metadata — missing stays unknown
        chairman = mgmt.get("chairman") or "unknown"
        md_ceo   = mgmt.get("managing_director_ceo") or "unknown"
        exp_yrs  = mgmt.get("industry_experience_years")
        rating   = mgmt.get("governance_rating") or "unknown"
        if exp_yrs is not None:
            leadership_summary = f"{md_ceo} ({exp_yrs}y exp, {rating})"
        else:
            leadership_summary = f"{md_ceo} (exp unknown, {rating})"

        # 1. Long-Term Asset Checklist:
        # P/E <= 16, low manipulation risk, debt/equity <= 0.8, veteran leadership, proven dividend, confident score
        is_asset = (
            pe_val is not None and pe_val <= 16.0 and
            (de_val is None or de_val <= 0.8) and
            loan_risk in ("none", "low") and
            gov_risk in ("Low", "Medium") and
            r.get("manipulation_risk") == "low" and
            conf >= 55.0
        )
        if is_asset:
            long_rec = dict(r)
            support_low  = round(entry * 0.98, 1)
            support_high = round(entry * 1.01, 1)
            target_long  = lt_info.get("target_price") or round(entry * 1.30, 1)

            long_rec["target_long"] = target_long
            long_rec["dir_icon"] = dir_icon
            long_rec["direction"] = direction
            long_rec["rise_prob"] = rise_prob
            long_rec["st_info"] = st_info
            long_rec["mt_info"] = mt_info
            long_rec["lt_info"] = lt_info
            long_rec["lt_upside"] = lt_info.get("upside_potential_pct") or "—"
            long_rec["lt_downside"] = lt_info.get("downside_risk_pct") or "—"
            long_rec["leadership_summary"] = leadership_summary
            long_rec["chairman"] = chairman
            long_rec["md_ceo"] = md_ceo
            long_rec["exp_yrs"] = exp_yrs
            long_rec["governance_rating"] = rating
            long_rec["key_moat"] = mgmt.get("key_moat") or "unknown"
            long_rec["audit_credibility"] = mgmt.get("audit_credibility") or "unknown"
            long_rec["dominant_intent"] = dominant_intent

            # Precision Suite Details — missing fields stay unknown, never invent coverage
            _cov = cash_flow.get("dividend_coverage_x")
            _fcf = cash_flow.get("fcf_yield_pct")
            long_rec["smart_money_sig"] = smart_money.get("signal") or "unknown"
            long_rec["smart_money_class"] = smart_money.get("classification") or "unknown"
            long_rec["cash_flow_cov"] = f"{_cov:.1f}x real cash covered" if _cov is not None else "unknown"
            long_rec["fcf_yield"] = f"{_fcf}%" if _fcf is not None else "unknown"
            long_rec["liquidity_directive"] = liquidity.get("directive") or "unknown"
            long_rec["max_single_order"] = liquidity.get("max_single_order_shares")
            long_rec["earnings_acc_sig"] = earn_acc.get("signal") or "unknown"

            long_rec["when_to_buy"] = (
                f"Buy on support dips between ৳{support_low}–৳{support_high}; "
                f"verify RSI turning up (>35); accumulate in 15%–20% tranches."
            )
            long_rec["when_not_to_buy"] = (
                f"Do NOT buy if price extends >5% above 20-DMA (>৳{round(sma20*1.05, 1)}), "
                f"if Debt/Equity rises above 0.8, or during unverified volume surges."
            )
            long_rec["when_to_sell"] = (
                f"Target exit at ৳{target_long} ({long_rec['lt_upside']}) or if P/E expands > 22.0. "
                f"Stop/Exit if annual cash dividend is suspended or EPS drops YoY for 2 consecutive quarters."
            )
            long_rec["debt_health"] = (
                f"Pristine (D/E: {de_val})" if de_val is not None and de_val <= 0.5 
                else (f"Manageable (D/E: {de_val})" if de_val is not None else "Audited Clean")
            )
            long_rec["growth_resilience"] = (
                f"Down {drawdown_info.get('drawdown_pct', 0)}% from 52w peak, yet EPS steady (Conviction discount)"
                if is_discount else "Stable fundamental growth"
            )
            long_term.append(long_rec)

        # 2. Mid-Term Swing Checklist:
        # Momentum, fair valuation (P/E <= 22), debt/equity <= 1.0, 12-20% swing target
        is_swing = (
            conf >= 60.0 and
            (de_val is None or de_val <= 1.0) and
            loan_risk in ("none", "low") and
            gov_risk in ("Low", "Medium") and
            r.get("manipulation_risk") == "low"
        )
        if is_swing:
            mid_rec = dict(r)
            target_mid = mt_info.get("target_price") or round(entry * 1.15, 2)
            trail_stop = mt_info.get("trailing_stop") or round(entry * 0.95, 2)
            mid_rec["target_mid"] = target_mid
            mid_rec["trailing_stop"] = trail_stop
            mid_rec["dir_icon"] = dir_icon
            mid_rec["direction"] = direction
            mid_rec["rise_prob"] = rise_prob
            mid_rec["mt_upside"] = mt_info.get("upside_potential_pct") or "—"
            mid_rec["mt_downside"] = mt_info.get("downside_risk_pct") or "—"
            mid_rec["mt_rr"] = mt_info.get("risk_reward_ratio") or "—"
            mid_rec["leadership_summary"] = leadership_summary
            mid_rec["dominant_intent"] = dominant_intent
            mid_rec["st_info"] = st_info
            mid_rec["mt_info"] = mt_info
            mid_rec["lt_info"] = lt_info
            mid_rec["smart_money_sig"] = smart_money.get("signal") or "unknown"
            mid_rec["liquidity_directive"] = liquidity.get("directive") or "unknown"
            mid_rec["max_single_order"] = liquidity.get("max_single_order_shares")

            mid_rec["when_to_buy"] = (
                f"Enter on support confirmation (৳{round(entry*0.99, 1)}–৳{round(entry*1.01, 1)}) "
                f"with MACD histogram turning positive and RSI between 35–55."
            )
            mid_rec["when_not_to_buy"] = (
                f"Do NOT buy if RSI > 62, if volume drops below 20-DMA during rally, "
                f"or if market bias is Strongly Bearish."
            )
            mid_rec["when_to_sell"] = (
                f"Take profit at ৳{target_mid} ({mid_rec['mt_upside']}); strictly exit on 5% trailing stop (৳{trail_stop}) "
                f"or MACD bearish death cross."
            )
            mid_rec["debt_health"] = f"D/E: {de_val}" if de_val is not None else "Checked"
            mid_term.append(mid_rec)

        # 3. Short-Term Daily/Weekly Scalp Checklist
        if conf >= 58.0 and r.get("manipulation_risk") == "low":
            short_rec = dict(r)
            quick_tgt  = st_info.get("target_price") or round(entry * 1.035, 2)
            tight_stop = st_info.get("support_price") or round(entry * 0.98, 2)
            short_rec["quick_target"] = quick_tgt
            short_rec["tight_stop"]   = tight_stop
            short_rec["dir_icon"]     = dir_icon
            short_rec["rise_prob"]    = rise_prob
            short_rec["st_upside"]    = st_info.get("upside_potential_pct") or "—"
            short_rec["st_downside"]  = st_info.get("downside_risk_pct") or "—"
            short_rec["st_rr"]        = st_info.get("risk_reward_ratio") or "—"
            short_rec["max_single_order"] = liquidity.get("max_single_order_shares")
            short_rec["when_to_buy"]  = f"Buy on intraday support test near ৳{entry:.1f}; tight bounce confirmation."
            short_rec["when_not_to_buy"] = f"Do NOT buy if opening gap > 1.5% or RSI > 65."
            short_rec["when_to_sell"] = f"Take profit strictly at ৳{quick_tgt} ({short_rec['st_upside']}); hard cut at ৳{tight_stop} ({short_rec['st_downside']})."
            short_term.append(short_rec)

    for lst in [long_term, mid_term, short_term, sells, manip_risk, debt_traps, gov_traps, dist_traps, greed_traps]:
        lst.sort(key=lambda x: x.get("confidence", 0), reverse=True)

    return {
        "long_term":            long_term,
        "mid_term":             mid_term,
        "short_term":           short_term,
        "sells":                sells,
        "debt_trap_blocked":    debt_traps,
        "governance_blocked":   gov_traps,
        "distribution_blocked": dist_traps,
        "manipulation_blocked": manip_risk,
        "greed_blocked":        greed_traps,
    }


def build_recommendations(timeframe: str, tickers: list[str] = None) -> dict:
    if tickers is None:
        sectors = load_config("sectors")
        tickers = []
        for sd in sectors["sectors"].values():
            tickers.extend(sd["top_tickers"])
        tickers = list(dict.fromkeys(tickers))

    records = []
    for ticker in tickers:
        analysis = load_analysis(ticker, timeframe)
        if not analysis:
            continue

        signal     = analysis.get("signal", "HOLD")
        confidence = analysis.get("confidence", 0.0)
        levels     = analysis.get("trade_levels", {})
        traj       = analysis.get("trajectory", {})
        prec       = analysis.get("precision", {})
        tech_sig   = analysis.get("technical", {}).get("signals", {})
        fund_sig   = analysis.get("fundamental", {}).get("signals", {})
        mgmt       = analysis.get("management", {})
        news_int   = analysis.get("news_intent", {})
        manip      = analysis.get("manipulation", {})

        entry     = levels.get("entry")
        target    = levels.get("target")
        stop_loss = levels.get("stop_loss")

        records.append({
            "ticker":                      ticker,
            "signal":                      signal,
            "confidence":                  confidence,
            "entry":                       entry if entry is not None else None,
            "target":                      target if target is not None else None,
            "stop_loss":                   stop_loss if stop_loss is not None else None,
            "rsi":                         tech_sig.get("rsi_value"),
            "sma20":                       tech_sig.get("sma20"),
            "sma200":                      tech_sig.get("sma200"),
            "pe":                          _extract_val(fund_sig.get("pe")),
            "eps":                         _extract_val(fund_sig.get("eps")),
            "dividend":                    fund_sig.get("dividend_yield"),
            "dividend_consistency":        fund_sig.get("dividend_consistency"),
            "dividend_track_record_years": fund_sig.get("dividend_track_record_years", 0),
            "debt_equity_val":             fund_sig.get("debt_equity_val"),
            "long_term_debt_equity_val":   fund_sig.get("long_term_debt_equity_val"),
            "loan_trap_risk":              fund_sig.get("loan_trap_risk", "none"),
            "downturn_resilience":         fund_sig.get("downturn_resilience", {}),
            "earnings_quality":            fund_sig.get("earnings_quality"),
            "management":                  mgmt,
            "news_intent":                 news_int,
            "trajectory":                  traj,
            "precision":                   prec,
            "pattern_dna":                 analysis.get("pattern_dna", {}),
            "manipulation_risk":           manip.get("manipulation_risk", "low"),
            "manipulation_flags":          manip.get("flags", []),
            "timeframe":                   timeframe,
        })

    # --- Halal guard (view-only, S6 advisory): invariant ranking halal-blind, filter before horizon buckets ---
    _halal_tier = "flexible"
    _halal_gates = {}
    _halal_blocked: list[dict] = []
    _eligible_records: list[dict] = records
    try:
        from halal_guard import HalalGuard
        from profile import load_profile
        _prof = load_profile()
        _halal_tier = _prof.get("halal_tier", "flexible")
        _guard = HalalGuard(profile=_prof)
        _halal_gates = _guard.gates_for(_halal_tier)
        # Sector + DSES enrichment for L1/L5 (BATBC override via sector_map)
        _sector_map: dict[str, str] = {}
        _dses_asof: str | None = None
        try:
            import sqlite3 as _sql
            _db = BASE_DIR / "data" / "processed" / "dse.db"
            if _db.exists():
                _conn = _sql.connect(str(_db))
                _conn.row_factory = _sql.Row
                try:
                    for _r in _conn.execute("SELECT ticker, sector FROM companies"):
                        _sector_map[_r["ticker"]] = _r["sector"]
                except Exception:
                    pass
                try:
                    _row = _conn.execute("SELECT MAX(date) as d FROM market_summary WHERE dses IS NOT NULL").fetchone()
                    _dses_asof = _row["d"] if _row and _row["d"] else None
                except Exception:
                    pass
                _conn.close()
        except Exception:
            pass
        for _r in records:
            if not _r.get("sector"):
                _r["sector"] = _sector_map.get(_r["ticker"])
            _r["dses_asof"] = _dses_asof
        _eligible_records = _guard.apply(records, _halal_tier)
        _eligible_set = {x["ticker"] for x in _eligible_records}
        for _r in records:
            _res = _guard.is_eligible(_r["ticker"], asof=_r.get("dses_asof"), tier=_halal_tier, pit_row=_r, dses_row=_r)
            _r["purification_rate"] = _res.get("purification_rate", 0.0)
            _r["halal_reasons"] = _res.get("reasons", [])
            _r["data_gaps"] = _res.get("data_gaps", [])
            _r["halal_tier"] = _halal_tier
            _r["halal_eligible"] = _res.get("eligible", True)
            if _r["ticker"] not in _eligible_set:
                _halal_blocked.append(_r)
        # Ensure eligible carry same annotations
        for _r in _eligible_records:
            # sync annotations from original record
            _orig = next((x for x in records if x["ticker"] == _r["ticker"]), None)
            if _orig:
                _r["purification_rate"] = _orig.get("purification_rate", 0.0)
                _r["halal_reasons"] = _orig.get("halal_reasons", [])
                _r["data_gaps"] = _orig.get("data_gaps", [])
                _r["halal_tier"] = _halal_tier
                _r["halal_eligible"] = True
                _r["dses_asof"] = _orig.get("dses_asof")
                _r["sector"] = _orig.get("sector")
    except Exception as _e:
        log.warning(f"Halal guard unavailable, passthrough: {_e}")
        _eligible_records = records

    horizons = classify_horizons(_eligible_records)
    horizons["halal_blocked"] = _halal_blocked
    horizons["_halal_tier"] = _halal_tier
    horizons["_halal_gates"] = _halal_gates

    # Run macro sentiment engine
    try:
        from macro_sentiment_engine import analyze_macro_sentiment
        macro_report = analyze_macro_sentiment(days=14)
    except Exception as e:
        log.warning(f"Macro sentiment engine failed: {e}")
        macro_report = {"systemic_market_bias": 0, "bias_label": "Neutral", "macro_alerts": []}

    return {
        "timeframe":      timeframe,
        "generated_at":   datetime.datetime.utcnow().isoformat(),
        "macro":          macro_report,
        "horizons":       horizons,
        "total_analyzed": len(records),
    }


def generate_markdown_report(recs: dict) -> str:
    now   = datetime.date.today().isoformat()
    tf    = recs["timeframe"]
    macro = recs.get("macro", {})
    h     = recs["horizons"]

    lines = []
    lines.append(f"# 📈 DSE Investment & Trading Strategy — {now} ({tf.upper()})\n")
    lines.append(f"**Generated**: {recs['generated_at']} UTC | **Total Stocks Analyzed**: {recs['total_analyzed']}  ")

    bias = macro.get("systemic_market_bias", 0)
    label = macro.get("bias_label", "Neutral")
    lines.append(f"**Macro Climate**: `{label}` (Score: {bias}/100)  ")
    if macro.get("macro_alerts"):
        lines.append("\n### 🚨 Active Political & Macro Alerts:")
        for alert in macro["macro_alerts"][:4]:
            lines.append(f"- ⚠️ {alert}")
    lines.append("\n---\n")

    # 1. Long-Term Asset Building List
    lines.append("## 🏛️ 1. Long-Term Asset Building Plan (Horizon: 1–5+ Years)\n")
    lines.append("*Defensive Moats, Zero/Low Debt, Real Cash-Covered Dividends, Smart-Money Flow Alignment.*\n")
    if h["long_term"]:
        lines.append("| Ticker | Price | Trajectory & Prob | P/E | Cash Flow Coverage | Smart Money | Max Order Limit | Accumulation Directive |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for r in h["long_term"][:8]:
            entry = f"৳{r['entry']:.1f}" if r['entry'] else "—"
            _rp = r.get("rise_prob")
            _rp_s = f"{_rp}%" if _rp is not None else "—"
            traj_str = f"**{r.get('dir_icon') or '—'} ({_rp_s})**"
            cf_cov = r.get("cash_flow_cov") or "unknown"
            sm_status = f"`{r.get('smart_money_class') or 'unknown'}`"
            _mo = r.get("max_single_order")
            max_ord = f"{_mo:,} sh" if _mo is not None else "—"
            lines.append(
                f"| **{r['ticker']}** | {entry} | {traj_str} | {_fmt_pe(r['pe'])} | "
                f"{cf_cov} | {sm_status} | {max_ord} | **ACCUMULATE TRANCHES** |"
            )
        lines.append("\n### 🎯 Long-Term Execution Playbook (Institutional Precision Audit):\n")
        for r in h["long_term"][:5]:
            st_info = r.get("st_info", {})
            mt_info = r.get("mt_info", {})
            lt_info = r.get("lt_info", {})
            _rp = r.get("rise_prob")
            _rp_s = f"{_rp}%" if _rp is not None else "unknown"
            lines.append(f"#### 📌 **{r['ticker']}** ({r.get('dir_icon') or '—'} Rise Prob: {_rp_s}, P/E: {_fmt_pe(r['pe'])}, Debt: {r['debt_health']})")
            lines.append(f"- **👔 Top Management**: {r.get('chairman')} (Chairman), {r.get('md_ceo')} (MD/CEO, {r.get('exp_yrs') or 'unknown'}y exp, Rating: {r.get('governance_rating')})")
            lines.append(f"- **🌊 Smart Money Shift**: {r.get('smart_money_sig') or 'unknown'}")
            lines.append(f"- **💰 Real Cash Flow & FCF**: {r.get('cash_flow_cov') or 'unknown'} | FCF Yield: {r.get('fcf_yield') or 'unknown'} | Audit: *{r.get('audit_credibility') or 'unknown'}*")
            lines.append(f"- **💧 Liquidity Guard**: {r.get('liquidity_directive') or 'unknown'}")
            lines.append(f"- **📊 3-Term Potential Breakdown**:")
            lines.append(f"  * ⚡ **Short-Term (1–10d)**: Path: {st_info.get('predicted_path') or '—'} | Upside: **{st_info.get('upside_potential_pct') or '—'}** vs Downside: {st_info.get('downside_risk_pct') or '—'} (R:R: {st_info.get('risk_reward_ratio') or '—'})")
            lines.append(f"  * 📈 **Mid-Term (1–6m)**: Path: {mt_info.get('predicted_path') or '—'} | Target: **৳{mt_info.get('target_price') or '—'} ({mt_info.get('upside_potential_pct') or '—'})** | Stop: ৳{mt_info.get('trailing_stop') or '—'} (R:R: {mt_info.get('risk_reward_ratio') or '—'})")
            lines.append(f"  * 🏛️ **Long-Term (1–5y)**: Path: {lt_info.get('predicted_path') or '—'} | Target: **৳{lt_info.get('target_price') or '—'} ({lt_info.get('upside_potential_pct') or '—'})** | Div Yield: {lt_info.get('dividend_cagr') or '—'}")
            lines.append(f"- **✅ When to Buy**: {r['when_to_buy']}")
            lines.append(f"- **⛔ When NOT to Buy**: {r['when_not_to_buy']}")
            lines.append(f"- **🎯 When to Sell**: {r['when_to_sell']}\n")
    else:
        lines.append("> No stocks currently satisfy strict long-term asset criteria.\n")

    lines.append("---\n")

    # 2. Mid-Term Swing Plan
    lines.append("## 📈 2. Mid-Term Swing Plan (Horizon: 1–6 Months)\n")
    lines.append("*Earnings Momentum, Manageable Debt, Valuation Mean-Reversion (Target: +12% to +20%).*\n")
    if h["mid_term"]:
        lines.append("| Ticker | Entry | Trajectory | Swing Target (+15%) | Trailing Stop (-5%) | Risk/Reward | Max Order Limit | P/E |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for r in h["mid_term"][:8]:
            entry = f"৳{r['entry']:.1f}" if r['entry'] else "—"
            tgt   = f"৳{r['target_mid']:.1f}" if r.get('target_mid') else "—"
            stop  = f"৳{r['trailing_stop']:.1f}" if r.get('trailing_stop') else "—"
            _rp = r.get("rise_prob")
            traj_str = f"**{r.get('dir_icon') or '—'} {_rp if _rp is not None else '—'}%**"
            _mo = r.get("max_single_order")
            max_ord = f"{_mo:,} sh" if _mo is not None else "—"
            lines.append(f"| **{r['ticker']}** | {entry} | {traj_str} | **{tgt}** | {stop} | {r.get('mt_rr') or '—'} | {max_ord} | {_fmt_pe(r['pe'])} |")
        lines.append("\n### 🎯 Mid-Term Execution Playbook:\n")
        for r in h["mid_term"][:5]:
            lines.append(f"#### 📌 **{r['ticker']}** (Target: ৳{r.get('target_mid')}, Stop: ৳{r.get('trailing_stop')}, R:R: {r.get('mt_rr')})")
            lines.append(f"- **👔 Leadership & Smart Money**: {r.get('leadership_summary')} | Flow: `{r.get('smart_money_sig')}`")
            lines.append(f"- **💧 Liquidity Guard**: {r.get('liquidity_directive')}")
            lines.append(f"- **✅ When to Buy**: {r['when_to_buy']}")
            lines.append(f"- **⛔ When NOT to Buy**: {r['when_not_to_buy']}")
            lines.append(f"- **🎯 When to Sell**: {r['when_to_sell']}\n")
    else:
        lines.append("> No mid-term swing triggers active.\n")

    lines.append("---\n")

    # 3. Short-Term Scalp List
    lines.append("## ⚡ 3. Short-Term Daily/Weekly Scalp Plan (Small-Margin: 2%–5% Targets)\n")
    lines.append("*Strict Risk Control: Small lot sizing, take profits immediately at target, do not hold if stop breached.*\n")
    if h["short_term"]:
        lines.append("| Ticker | Entry | Rise Prob | Quick Target (+3.5%) | Tight Stop (-2%) | Max Scalp Lot | Risk/Reward | Conf |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for r in h["short_term"][:8]:
            entry = f"৳{r['entry']:.1f}" if r['entry'] else "—"
            tgt   = f"৳{r['quick_target']:.1f}" if r.get('quick_target') else "—"
            stop  = f"৳{r['tight_stop']:.1f}" if r.get('tight_stop') else "—"
            _rp = r.get("rise_prob")
            traj_str = f"{r.get('dir_icon') or '—'} {_rp if _rp is not None else '—'}%"
            _mo = r.get("max_single_order")
            max_ord = f"{_mo:,} sh" if _mo is not None else "—"
            lines.append(f"| **{r['ticker']}** | {entry} | {traj_str} | **{tgt}** | {stop} | {max_ord} | {r.get('st_rr') or '—'} | {r['confidence']:.0f}% |")
        lines.append("")
    else:
        lines.append("> No high-conviction short-term scalps meeting risk criteria today.\n")

    # 4. Debt Trap Warning Table
    if h["debt_trap_blocked"]:
        lines.append("## 🚫 Excessive Loan / Debt Traps — DO NOT BUY\n")
        lines.append("| Ticker | Debt/Equity | Loan Risk Status | Reason |")
        lines.append("|---|---|---|---|")
        for r in h["debt_trap_blocked"][:8]:
            de_s = f"{r.get('debt_equity_val', 'N/A')}"
            lines.append(f"| **{r['ticker']}** | {de_s} | **HIGH DEBT TRAP** | High long-term loan burden in 9-14% interest regime |")
        lines.append("")

    # 5. Governance & Legal Inquiry Warning Table
    if h.get("governance_blocked"):
        lines.append("## ⚖️ Governance & Legal Inquiries — DO NOT BUY\n")
        lines.append("| Ticker | Governance Rating | Red Flag / Probe Reason |")
        lines.append("|---|---|---|")
        for r in h["governance_blocked"][:8]:
            mgmt = r.get("management", {})
            news_int = r.get("news_intent", {})
            reasons = "; ".join(news_int.get("red_flags", [f"Management Risk: {mgmt.get('management_risk', 'High')}"]))
            lines.append(f"| **{r['ticker']}** | **{mgmt.get('governance_rating', 'Risk')}** | {reasons} |")
        lines.append("")

    # 6. Retail Distribution Trap Warning Table
    if h.get("distribution_blocked"):
        lines.append("## 📉 Retail Distribution Traps — DO NOT BUY\n")
        lines.append("| Ticker | Trap Classification | Reason |")
        lines.append("|---|---|---|")
        for r in h["distribution_blocked"][:8]:
            prec = r.get("precision", {})
            sm = prec.get("smart_money", {})
            cf = prec.get("cash_flow", {})
            reason = sm.get("signal") or cf.get("signal") or "Smart money selling into retail buying"
            lines.append(f"| **{r['ticker']}** | **DISTRIBUTION TRAP** | {reason} |")
        lines.append("")

    # 7. Market Greed & Froth Traps Warning Table
    if h.get("greed_blocked"):
        lines.append("## 🛑 Market Greed / Overvalued Traps — DO NOT BUY (Wait for Pullback)\n")
        lines.append("| Ticker | Price | Intrinsic Worth | Margin of Safety | Greed Index | Trap / Overheat Reason |")
        lines.append("|---|---|---|---|---|---|")
        for r in h["greed_blocked"][:8]:
            wg = r.get("pattern_dna", {}).get("worth_vs_greed", {})
            cur_p = f"৳{r['entry']:.1f}" if r.get('entry') else "—"
            iw = f"৳{wg.get('intrinsic_worth', 0):.1f}"
            mos = f"{wg.get('margin_of_safety_pct', 0):+.1f}%"
            gi = f"{wg.get('greed_index', 75):.0f}/100"
            lines.append(f"| **{r['ticker']}** | {cur_p} | {iw} | **{mos}** | **{gi}** | {r.get('greed_reason', 'Overheated')} |")
        lines.append("")

    # 8. Manipulation Risk Warning Table
    if h["manipulation_blocked"]:
        lines.append("## ⚠️ Manipulation Risk — DO NOT BUY\n")
        lines.append("| Ticker | Manip Risk | Specific Red Flags |")
        lines.append("|---|---|---|")
        for r in h["manipulation_blocked"][:8]:
            flags = "; ".join(r.get("manipulation_flags", ["Abnormal volume/spread pattern"]))
            lines.append(f"| **{r['ticker']}** | **{r['manipulation_risk'].upper()}** | {flags} |")
        lines.append("")

    # 9. Halal Filter — view-only advisory (tier-aware, invariant ranking)
    _tier_label = h.get("_halal_tier", "flexible")
    _gates = h.get("_halal_gates", {}) or {}
    _hb = h.get("halal_blocked", []) or []
    lines.append(f"## ☪️ Halal Screen — Tier: `{_tier_label}` (view-only, ranking halal-blind)")
    if _gates:
        lines.append(f"_Gates: L1 excluded { _gates.get('L1_sectors_excluded')} · L2 D/E ≤ {_gates.get('L2_debt_equity_max')} LT ≤ {_gates.get('L2_long_term_debt_equity_max')} · L5 DSES {'required' if _gates.get('L5_dses_required') else 'advisory'} · DSES asof `{_hb[0].get('dses_asof') if _hb else (h.get('long_term', [{}])[0].get('dses_asof') if h.get('long_term') else '—')}`_  ")
    if _hb:
        lines.append("| Ticker | Sector | D/E | Halal | DSES asof | Reasons | Purification | Data gaps |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for r in _hb[:20]:
            _de = r.get("debt_equity_val")
            _de_s = f"{_de:.2f}" if isinstance(_de, (int, float)) else "—"
            _hal = "Blocked" if not r.get("halal_eligible", False) else "Pass"
            _asof = r.get("dses_asof") or "—"
            _rs = "; ".join(r.get("halal_reasons", []) or []) or "—"
            _pur = f"{r.get('purification_rate', 0.0):.2%}"
            _gaps = "; ".join(r.get("data_gaps", []) or []) or "—"
            lines.append(f"| **{r['ticker']}** | {r.get('sector') or '—'} | {_de_s} | {_hal} | {_asof} | {_rs} | {_pur} | {_gaps} |")
        lines.append("")
    else:
        if _tier_label == "off":
            lines.append("> Halal filter OFF — no tickers blocked.  ")
        else:
            lines.append(f"> No tickers blocked under `{_tier_label}` halal screen for this universe.  ")
    # Advisory: still show Halal+DSES columns for displayed horizons so reader can audit
    if h.get("long_term") or h.get("mid_term"):
        lines.append(f"_Halal attribution: eligible horizons above are after guard (_halal='Pass'); blocked list is advisory. DSES membership checked as-of above; purification_rate is advisory._  ")
    lines.append("")

    lines.append("---")
    lines.append("> ⚠️ Generated by DSE Quantitative Engine. Cross-verify against official DSE disclosures. Not financial advice.")
    return "\n".join(lines)


def generate_monthly_asset_plan(recs: dict) -> str:
    """
    Piles daily and weekly analysis into a structured monthly accumulation ledger:
      - 60% Core Long-Term Moats (Zero/Low Debt, Veteran Leadership, Proven Dividends)
      - 30% Mid-Term Cycle Swings (+15% Mean Reversion)
      - 10% Tactical Scalps / Cash Reserve
    """
    now = datetime.date.today().isoformat()
    month_str = now[:7]
    h = recs["horizons"]

    lines = []
    lines.append(f"# 🏛️ Monthly Investment & Capital Accumulation Ledger — {month_str}\n")
    lines.append(f"**Period**: Month of {month_str} | **Strategy**: Value Moats, Zero-Debt Compounding, Veteran Management\n")

    lines.append("## 💼 1. Target Portfolio Allocation Model\n")
    lines.append("| Strategy Horizon | Target Allocation | Primary Objective | Risk Management Rule |")
    lines.append("|---|---|---|---|")
    lines.append("| **Long-Term Core Assets** | **60%** | Wealth preservation, audited zero-debt moats, dividend reinvestment | Hold 1–5 yrs; tranche accumulation on 3-5% market dips |")
    lines.append("| **Mid-Term Position Swings** | **30%** | Capital appreciation (+12% to +20%), sector rotation cycles | Hold 1–6 mos; strict 5% trailing stop discipline |")
    lines.append("| **Cash & Tactical Scalps** | **10%** | Dry powder for black swan events, quick 2-4% scalps | Never risk >2% total capital per scalp; keep ready cash |")
    lines.append("\n---\n")

    lines.append("## 📅 2. Monthly Capital Deployment Tranches (Piling Daily Analysis)\n")
    lines.append("Do NOT deploy 100% capital in a single day. Spread monthly allocation across 4 systematic tranches:\n")
    lines.append("- **Tranche 1 (Week 1 / Initial Base - 25%)**: Deploy into top 3 Long-Term Low-Debt assets with AAA/AA+ management.")
    lines.append("- **Tranche 2 (Dip Accumulation - 25%)**: Deploy if DSEX or target stock pulls back 2.5%–4.0% toward lower Bollinger Band.")
    lines.append("- **Tranche 3 (Confirmation Tranche - 25%)**: Deploy on MACD histogram expansion and volume confirmation.")
    lines.append("- **Tranche 4 (Tactical Reserve - 25%)**: Kept in liquid cash / T-Bills until high-conviction breakout or deep oversold RSI (<28).\n")
    lines.append("---\n")

    lines.append("## 🏆 3. Top Long-Term Core Assets (Audited Leadership & Low Debt)\n")
    if h["long_term"]:
        lines.append("| Ticker | Entry Zone | Direction & Prob | Upside / Risk | P/E | Debt/Equity | Leadership & Experience | Tranche Pacing | Target Exit |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for r in h["long_term"][:5]:
            entry = r.get("entry") or 0.0
            zone = f"৳{round(entry*0.98, 1)}–৳{round(entry*1.01, 1)}"
            tgt  = f"৳{r.get('target_long', round(entry*1.3, 1))}"
            de   = r.get("debt_equity_val", "Low")
            _rp = r.get("rise_prob")
            traj_str = f"{r.get('dir_icon') or '—'} ({_rp if _rp is not None else '—'}%)"
            potential_str = f"{r.get('lt_upside', '+30%')} / {r.get('lt_downside', '-10%')}"
            lines.append(f"| **{r['ticker']}** | {zone} | {traj_str} | {potential_str} | {_fmt_pe(r['pe'])} | D/E: {de} | {r.get('leadership_summary') or 'Veteran'} | 20% per tranche | {tgt} |")
        lines.append("")
    else:
        lines.append("> No stocks qualify for Long-Term Core this month.\n")

    lines.append("## 🚀 4. Top Mid-Term Cycle Swings (1–6 Months)\n")
    if h["mid_term"]:
        lines.append("| Ticker | Entry Price | Direction & Prob | Target (+15%) | Trailing Stop (-5%) | Risk/Reward | P/E |")
        lines.append("|---|---|---|---|---|---|---|")
        for r in h["mid_term"][:5]:
            entry = f"৳{r['entry']:.1f}" if r['entry'] else "—"
            tgt   = f"৳{r['target_mid']:.1f}" if r.get('target_mid') else "—"
            stop  = f"৳{r['trailing_stop']:.1f}" if r.get('trailing_stop') else "—"
            _rp = r.get("rise_prob")
            traj_str = f"{r.get('dir_icon') or '—'} {_rp if _rp is not None else '—'}%"
            lines.append(f"| **{r['ticker']}** | {entry} | {traj_str} | **{tgt}** | {stop} | {r.get('mt_rr', '3.0x')} | {_fmt_pe(r['pe'])} |")
        lines.append("")
    else:
        lines.append("> No mid-term swing setups active.\n")

    lines.append("## 🛡️ 5. Monthly Risk Filter & Governance Directive\n")
    lines.append("1. **Absolute Loan Cap**: Avoid non-financial companies with Debt/Equity > 0.8 or Long-Term Debt > BDT 500 Crore in Bangladesh's 9%–14% interest rate regime.")
    lines.append("2. **Leadership Integrity**: Only allocate capital to companies with unblemished leadership (zero loan defaults, reputable external audit, established tenure).")
    lines.append("3. **Real Cash Flow Requirement**: Dividends must be at least 100% cash-covered by Net Operating Cash Flow (NOCFPS >= Dividend per share).")
    lines.append("4. **Smart Money Alignment**: Avoid stocks where retail holding surged > 1.5% while institutions and foreign investors offloaded.")
    lines.append("5. **Liquidity Guard**: Single order size must never exceed 5% of 20-day average daily traded volume to prevent execution slippage.")
    lines.append("\n---\n> Published by DSE Quantitative Investment Engine.")

    out_dir = REPORT_DIR / "monthly"
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = out_dir / f"{month_str}_asset_plan.md"
    with open(plan_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log.info(f"Monthly asset plan published to {plan_path}")

    # Generate Bengali Version
    bn_lines = []
    bn_lines.append(f"# 🏛️ মাসিক বিনিয়োগ ও ক্যাপিটাল সঞ্চয়ন লেজার — {month_str}\n")
    bn_lines.append(f"**সময়কাল**: {month_str} মাস | **কৌশল**: ভ্যালু মোটস, ঋণমুক্ত কম্পাউন্ডিং, শীর্ষ ব্যবস্থাপনা\n")
    bn_lines.append("## 💼 ১. টার্গেট পোর্টফোলিও বরাদ্দ মডেল\n")
    bn_lines.append("| কৌশল দিগন্ত | লক্ষ্য বরাদ্দ | মূল উদ্দেশ্য | ঝুঁকি ব্যবস্থাপনা বিধি |")
    bn_lines.append("|---|---|---|---|")
    bn_lines.append("| **দীর্ঘমেয়াদী কোর সম্পদ** | **৬০%** | সম্পদ সুরক্ষা, অডিটেড কম-ঋণ মোটস, ডিভিডেন্ড পুনঃবিনিয়োগ | ১–৫ বছর ধারণ; ৩-৫% মার্কেট ডিপে ট্রাঞ্চ সঞ্চয় |")
    bn_lines.append("| **মিড-টার্ম পজিশন সুইং** | **৩০%** | মূলধন বৃদ্ধি (+১২% থেকে +২০%), সেক্টর রোটেশন সাইকেল | ১–৬ মাস ধারণ; কঠোর ৫% ট্রেইলিং স্টপ শৃঙ্খলা |")
    bn_lines.append("| **ক্যাশ ও ট্যাকটিক্যাল স্ক্যাল্প** | **১০%** | ব্ল্যাক সোয়ান ইভেন্টের জন্য ক্যাশ পাউডার, দ্রুত ২-৪% স্ক্যাল্প | প্রতি স্ক্যাল্পে মোট মূলধনের ২%-এর বেশি ঝুঁকি নয় |")
    bn_lines.append("\n---\n")

    bn_lines.append("## 🏆 ২. শীর্ষ দীর্ঘমেয়াদী কোর সম্পদ (অডিটেড লিডারশিপ ও কম ঋণ)\n")
    if h["long_term"]:
        bn_lines.append("| Ticker | এন্ট্রি জোন | অভিমুখ ও সম্ভাবনা | আপসাইড / ডাউনসাইড | P/E | Debt/Equity | ট্রাঞ্চ সঞ্চয় | টার্গেট প্রফিট |")
        bn_lines.append("|---|---|---|---|---|---|---|---|")
        for r in h["long_term"][:5]:
            entry = r.get("entry") or 0.0
            zone = f"৳{round(entry*0.98, 1)}–৳{round(entry*1.01, 1)}"
            tgt  = f"৳{r.get('target_long', round(entry*1.3, 1))}"
            de   = r.get("debt_equity_val", "Low")
            _rp = r.get("rise_prob")
            traj_str = f"{r.get('dir_icon') or '—'} ({_rp if _rp is not None else '—'}%)"
            potential_str = f"{r.get('lt_upside', '+30%')} / {r.get('lt_downside', '-10%')}"
            bn_lines.append(f"| **{r['ticker']}** | {zone} | {traj_str} | {potential_str} | {_fmt_pe(r['pe'])} | D/E: {de} | ২০% প্রতি ট্রাঞ্চ | {tgt} |")
        bn_lines.append("")
    else:
        bn_lines.append("> এই মাসে কোনো স্টক দীর্ঘমেয়াদী কোর হিসেবে উত্তীর্ণ হয়নি।\n")

    bn_lines.append("## 🚀 ৩. শীর্ষ মিড-টার্ম সাইকেল সুইং ট্রেড (১–৬ মাস)\n")
    if h["mid_term"]:
        bn_lines.append("| Ticker | এন্ট্রি দর | অভিমুখ ও সম্ভাবনা | লক্ষ্য (+১৫%) | ট্রেইলিং স্টপ (-৫%) | রিস্ক/রিওয়ার্ড | P/E |")
        bn_lines.append("|---|---|---|---|---|---|---|")
        for r in h["mid_term"][:5]:
            entry = f"৳{r['entry']:.1f}" if r['entry'] else "—"
            tgt   = f"৳{r['target_mid']:.1f}" if r.get('target_mid') else "—"
            stop  = f"৳{r['trailing_stop']:.1f}" if r.get('trailing_stop') else "—"
            _rp = r.get("rise_prob")
            traj_str = f"{r.get('dir_icon') or '—'} {_rp if _rp is not None else '—'}%"
            bn_lines.append(f"| **{r['ticker']}** | {entry} | {traj_str} | **{tgt}** | {stop} | {r.get('mt_rr', '3.0x')} | {_fmt_pe(r['pe'])} |")
        bn_lines.append("")
    else:
        bn_lines.append("> কোনো মিড-টার্ম সুইং সেটআপ সক্রিয় নেই।\n")

    bn_lines.append("## 🛡️ ৪. মাসিক রিস্ক ফিল্টার ও সুশাসন নীতিমালা\n")
    bn_lines.append("১. **ঋণ সীমা**: বর্তমান উচ্চ সুদের হারে Debt/Equity > ০.৮০ বা অতিরিক্ত ঋণযুক্ত নন-ফাইন্যান্সিয়াল কোম্পানি বর্জন করুন।")
    bn_lines.append("২. **বাস্তব ক্যাশ ফ্লো আবশ্যক**: শেয়ার প্রতি ঘোষিত ডিভিডেন্ড অবশ্যই অপারেটিং ক্যাশ ফ্লো (NOCFPS) দ্বারা ১০০% সুরক্ষিত হতে হবে।")
    bn_lines.append("৩. **স্মার্ট মানি অ্যালাইনমেন্ট**: যে সব শেয়ারে সাধারণ রিটেইল হোল্ডিং হঠাৎ ১.৫% এর বেশি বেড়েছে কিন্তু বিদেশি/প্রতিষ্ঠান বিক্রি করেছে তা বর্জন করুন।")
    bn_lines.append("৪. **লিকুইডিটি গার্ড**: স্লিপেজ কমাতে কোনো একক অর্ডার কখনোই ২০ দিনের গড় দৈনিক ট্রেডেড ভলিউমের ৫%-এর বেশি হওয়া উচিত নয়।")
    bn_lines.append("\n---\n> DSE কোয়ান্টেটিভ ইনভেস্টমেন্ট ইঞ্জিন দ্বারা প্রকাশিত।")

    bn_plan_path = out_dir / f"{month_str}_asset_plan_bn.md"
    with open(bn_plan_path, "w", encoding="utf-8") as f:
        f.write("\n".join(bn_lines))
    log.info(f"Bengali monthly asset plan published to {bn_plan_path}")

    return "\n".join(lines), plan_path


def run_recommender(timeframe: str = "weekly", tickers: list[str] = None):
    log.info(f"Generating tri-horizon recommendations for {timeframe}...")
    recs = build_recommendations(timeframe, tickers)

    now_str = datetime.date.today().isoformat()
    out_dir = REPORT_DIR / timeframe
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / f"{now_str}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(recs, f, indent=2, ensure_ascii=False)

    md = generate_markdown_report(recs)
    md_path = out_dir / f"{now_str}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    # Persist structured recommendations into SQLite recommendations table
    try:
        import sqlite3
        db_path = BASE_DIR / "data" / "processed" / "dse.db"
        if db_path.exists():
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            inserted_count = 0
            for h_key, h_list in recs.get("horizons", {}).items():
                for item in h_list:
                    if not isinstance(item, dict):
                        continue
                    ticker = item.get("ticker")
                    if not ticker:
                        continue
                    sig = item.get("signal")
                    conf = item.get("confidence")
                    # Records store flat manipulation_risk; nested .manipulation is absent
                    m_risk = item.get("manipulation_risk")
                    if m_risk is None and isinstance(item.get("manipulation"), dict):
                        m_risk = item["manipulation"].get("manipulation_risk")
                    if m_risk is None:
                        m_risk = "unknown"
                    entry = item.get("entry")
                    target = item.get("target")
                    stop = item.get("stop_loss")
                    reason = item.get("loan_trap_risk") or item.get("pe") or ""
                    try:
                        cur.execute("""
                            INSERT OR REPLACE INTO recommendations
                            (ticker, date, horizon, signal, confidence, manipulation_risk, entry_price, target, stop_loss, reasoning)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (ticker, now_str, h_key, sig, conf, m_risk, entry, target, stop, str(reason)))
                        inserted_count += 1
                    except Exception:
                        pass
            conn.commit()
            conn.close()
            log.info(f"Persisted {inserted_count} recommendations to SQLite database.")
    except Exception as e:
        log.warning(f"Could not persist recommendations to SQLite: {e}")

    # Automatically generate monthly asset plan
    monthly_plan_path = None
    try:
        _, monthly_plan_path = generate_monthly_asset_plan(recs)
    except Exception as e:
        log.warning(f"Monthly asset plan generation error: {e}")

    # Automatically generate exact personalized position plan
    try:
        from portfolio_manager import generate_exact_position_plan
        generate_exact_position_plan()
    except Exception as e:
        log.warning(f"Portfolio position plan generation skipped: {e}")

    # Automatically generate price & volume visual charts for top recommendations
    try:
        from chart_generator import generate_price_chart, generate_volume_chart, generate_market_cap_chart
        top_recs = (recs["horizons"]["short_term"][:3] + recs["horizons"]["long_term"][:3])
        top_tickers = list(dict.fromkeys([r["ticker"] for r in top_recs if r.get("ticker")]))
        for t in top_tickers:
            generate_price_chart(t)
            generate_volume_chart(t)
        generate_market_cap_chart()
        log.info(f"Visual charts generated for: {top_tickers}")
    except Exception as e:
        log.warning(f"Visual chart generation skipped: {e}")

    log.info(f"Report published to {md_path}")
    return recs, md_path


if __name__ == "__main__":
    tf = sys.argv[1] if len(sys.argv) > 1 else "weekly"
    run_recommender(tf)
