# CLAUDE.md — stock_market_expert_bd

Dhaka Stock Exchange (DSE) quantitative research, risk-screening and personal portfolio decision-support system. Purpose is non-commercial: academic/research use and personal decisions only — never describe it as a commercial or institutional data product; keep README's "Data Quality & Limitations" honest when data changes. Single user, real money: every write to the DB or a ledger must be correct, point-in-time and reproducible. When unsure, refuse to write rather than guess.

Authoritative docs: `SPEC.md` (invariants INV-1…INV-8), `README.md`, `.agents/skills/dse-developer/SKILL.md` (dev rules + Data Safety Rules), `.agents/skills/dse-learnings/SKILL.md` (past mistakes — read before touching data writers).

## Stack & layout

- Python 3.10, Windows-first (also Linux/macOS). Use Git Bash or PowerShell; force UTF-8 stdout.
- SQLite WAL `data/processed/dse.db` (~220 MB, gitignored). Committed baseline `data/processed/dse.db.gz` (~41 MB) restored by `scripts/bootstrap.py` / `ready.bat`.
- `main.py` — CLI (`python main.py help`): `alpha`, `scan`, `refresh`, `stock`, `pattern`, `compare`, `check`, `portfolio`, `plan`, `dual`, `buy`, `sell`, `report`, `push-db`, `schedule`, ...
- `scripts/` — ~95 single-purpose scripts, each runnable standalone (import siblings via `sys.path` to `scripts/`).
- `tests/` — unittest suite. `data/knowledge/<TICKER>/` per-ticker JSON (generated). `reports/` generated output.
- Every sqlite connection: `timeout=30.0` + `PRAGMA busy_timeout=30000` (INV-7).

## Core investment logic ("subtractive edge")

1. Screen out toxic names: debt traps, NOCFPS ≤ 0, syndicate pumps (`anti_manipulation_engine.py`), governance failures (`governance_risk_sentinel.py`).
2. Rank survivors by value: Graham number √(22.5·EPS·NAV), dividend yield vs macro hurdle (91-day T-bill + 3.5% ERP, `macro_rate_feed.py`).
3. Halal guard (optional, user-selected `halal_tier` strict/flexible/off in `config/profile.json`; Islamic perspective only — excludes haram and interest-based businesses, no index-membership requirement) (`halal_guard.py`): banks/conventional finance/tobacco blocked sector-first (`unified_score.is_financial_company`); D/E ≤ 0.8 (strict ≤ 0.5). Missing D/E ⇒ `L2_debt_unverified` = BLOCK, never pass. Unknown DSES ⇒ `L5_dses_unverified`.
4. Costs: buy 0.415%, sell 0.465% (incl. 0.05% AIT §53BBB), 10% AIT on dividends, settlement T+2 (Z category T+3). Circuit-locked exits deferred (INV-4).

## Data model — rules that must never break

- **prices**: raw exchange bars only. Corporate-action adjustment happens at read time (`feature_store`, `precision_engine`, `backtester`). Never write adjusted prices, never write bars on calendar-closed days, never store a cached/stale snapshot under today's date (`processor.stale_snapshot_reason`, `snapshot_rejection_reason`).
- **trading_calendar**: source of truth for sessions. `recalibrate_trading_calendar.py` is manual-only and dangerous.
- **fundamentals_pit** (INV-1): `tradable_date ≥ publication_date ≥ snapshot_date`. `publication_is_estimated` must be honest; estimated sources (`bsec_statutory_filing`, `dse_corporate_action`) can never be marked verified. Lags from `constants.STATUTORY_LAG_DAYS` ({1:45, 2:60, 3:45, 4:120, None:120}). PSI date accepted only inside filing window (deadline + `PSI_LATE_FILING_GRACE_DAYS=60`). Rows from `live_scrape` are direct observations. Resolver: `pit_disclosure_resolver.py`.
- **Fiscal year end** is per company (`companies.fiscal_year_end_month`; June ~267, Dec ~127, Mar 2). Use `processor.fiscal_year_end_month / fiscal_quarter_end / fiscal_year_of`, never assume June.
- **corporate_actions**: types limited to cash_dividend, bonus_dividend, split, rights_split, rights. Price-type factor must be 0<f<1. Bonus/split ex-dates come only from an official notice or observed gap (`corporate_action_processor.infer_bonus_ex_date`). No "Historical estimated" plug rows.
- **macro_indicators**: only values stored at their own publication date — Bangladesh Bank `bcr_91d` (91-day BCR) and `dommr_overnight` scraped by `macro_rate_feed.py`, or manual `--update IND VALUE DATE`. Never copy constants forward. Readers take each indicator's latest value ≤ asof (never a later one); `risk_free_source`/`is_stale` expose provenance. INV-2 hurdle (user decision 2026-11-20) = freshest observed of `t_bill_91d` / `bcr_91d` as of the scoring date + 3.5% ERP (`unified_score.equity_hurdle_pct`, `risk_free_rate_pct`); `t_bill_91d_pct` is the T-bill observation only. Never hard-code 11.60/15.10.

## Official data layer (Tier 1, research-grade)

- `dse_disclosures.py` — immutable archive of every DSE announcement (`disclosures`, from `dse.com.bd/api/live/news`, history from Nov 2024) → parsed filings (`disclosure_financials`: period end, discrete-quarter EPS, NAV, YTD NOCFPS, first publication) → `reconcile_pit` makes `fundamentals_pit` agree: observed publication dates (`publication_source='dse_disclosure'`, never re-dated by processor/resolver/migration), filed values, missing filed periods, company FYE; every change logged in `pit_corrections`. `cash_flow_ops` = annual NOCFPS only.
- `official_corporate_actions.py` — dividends/bonus/rights from official declarations, record dates confirmed by the exchange's suspension notices, BSEC consent/rejection for stock dividends, subsidiary notices skipped; `company_dividend_history` (official per-FY %) audits pre-archive rows; untagged placeholders superseded only with evidence. Rows referenced by `portfolio_dividend_credits` are never moved/deleted. Log: `corporate_action_corrections`. Face value is Tk 10 (BSEC uniform; verified).
- `instrument_master.py` — `instruments` (type/board/status with evidence) + `category_history` (A/B/N/Z intervals from DSE "Category Change" notices); `universe_asof()` / `category_asof()` for survivorship- and look-ahead-safe research universes. SME-board tickers are not served by any reachable DSE feed after 2026-01-22 (marked inactive, not invented).
- `index_membership.py` — DSEX/DS30 snapshots captured daily (stored only on change); DSES has no API (import with `import DSES DATE --source URL` if ever wanted); the halal guard does not use index membership.
- `bank_asset_quality.py` — bank NPL/CAR only with period, publication date and source URL (no structured official feed exists). Unsourced NPLs were removed from `config/company_registry_12factor.json`; banks are detected by sector and scored neutral/"unverified" without a sourced row.
- Provenance (Tier 2, `provenance.py`): every price writer must stamp `prices.source`/`ingest_id` (`stamp_prices` / `stamp_unattributed` + `new_ingest` with the raw payload hash in `ingest_log`); the data gate fails on unattributed bars. `archive_verified_on` = bar identical to DSE's official day-end archive (repair, daily reconcile, `archive_crosscheck.py`; archive reachable only from Dec 2024). `quality_flags` marks imputed values. `corporate_actions.source` is derived from writer markers (`classify_corporate_action_sources`). `data_quality_daily` gets a row on each gate run. `dataset_release.py` = values-only fingerprint (stored in every forward-ledger block) + versioned CSV export; data card at `docs/DATA_CARD.md` — keep it in sync with data changes.
- Tier 3 (model inputs/research): `feature_store` universe = equities trading on asof in point-in-time category (`category_history`, earliest known before Nov 2024; delisted names kept); P/E = close / latest published annual EPS; dividend yield = official cash dividends with record date in the trailing year / close; D/E field-wise; split/rights/bonus all adjust prices; `traded_value_20d` stored (research only). `companies.category` follows DSE's official live category (`instrument_master`); never default a missing category to "A". Backtests without explicit tickers use `instrument_master.liquidity_schedule` (monthly PIT top-N by traded value). Challenger `challenger_xsection_rank_v1` (whole-universe percentile ranks of div/value/rsi, no macro-hurdle gate) is shadow-scored; promotion only via 200 live periods + Holm + `--approve`. Research scripts: `research_feature_inputs_eval.py`, `research_factor_ic.py`, `research_universe_bias_eval.py` (reports in `reports/research/`, summary `docs/RESEARCH_NOTES.md`).
- Readers must take each field from its own latest published PIT row (official filings carry EPS/NAV/NOCFPS but not D/E or P/E).
- Never parse DSE/BB text with shell heredocs containing regex backslashes — write a `.py` file.
- **DB write guards**: SQLite triggers in `scripts/db_guards.py` (`install_data_guards`) enforce the above inside the DB; installed by `processor.get_db`, `bootstrap`, `rebuild_database`. Don't drop them.
- **Data gate**: `python scripts/integrity_harness.py --data-gate` — critical checks (guards installed, no closed-day bars, latest session real & covered, PIT ordering/flags, clean corporate actions, portfolio ledger balanced, full-horizon labels, champion frozen) + warnings (coverage, shadow IC, macro freshness >45d). Failure blocks all downstream ledger/label/learning writes.

## Daily flows

- `scripts/auto_daily_alpha_routine.py` (`main.py alpha`): scrape → `processor.py` → `repair_price_history.py --recent 5` (reconcile with official DSE day-end archive) → `dse_disclosures.py daily` → `official_corporate_actions.py --apply` → `instrument_master.py` → `index_membership.py capture` → macro → corporate actions/dividends → auditor footnotes → anti-manipulation → **data gate (exit 1 on fail)** → forward ledger → multi-horizon evaluator → RL weights → factor IC calibrator → shadow scoring → promotion check → analyzer → scanner → screeners → recommender → retention → integrity harness.
- `scripts/run_daily_pipeline.py` (`run_daily.bat`, `--skip-scrape`): similar ingestion + reconcile + data gate, then corporate actions, MF NAV sync, `portfolio_manager.py status`, `portfolio_sentinel.py`, reports.
- Both must be idempotent: a second run on the same day changes nothing but `updated_at` timestamps. Holiday runs write nothing new.
- Price repair tools: `repair_price_history.py --start/--end [--apply] [--tickers]` (bdshare archive, 180-day chunks), `live_market_sync.py` coverage-gap backfill (`backfill_attempts` table, retry 7d).

## Model, alpha & forward test

- Frozen champion `frozen_epoch2_pit_v2` (label hash `acf502bc65914c48`, weights div=1 value=1 debt=0 rsi=0). Content hash (`unified_score.compute_model_content_hash`) covers `CANONICAL_SERVED_PARAMS` + LF-normalised `unified_score.py` + `feature_store.py`. Any edit to those files fails INV-5 (`spec_guard.py`) until `python scripts/model_registry.py freeze --reason "..."`. Don't change scoring casually.
- Challengers (`shadow_v3_ic_weighted`, `challenger_equal_weight_v2`, `shadow_bayesian_adaptive_v1`) are shadow-scored daily on the full universe. IC = selection IC (gated names tied below all eligible), excludes CA events in window, base = DB close. Promotion: ≥200 live periods (`MIN_PROMOTION_PERIODS`), Holm step-down over one-sided Newey-West p-values, and explicit `model_registry.py promote <id> --approve`. Backfilled IC is research-only.
- Forward ledger `data/portfolio/forward_test_ledger_v2.json` (INV-6): SHA-256 hash chain, 6 names, 40% cash floor, 21-bar rebalance; safety mode only sells ineligible names; buys capped by cash; blocks carry `model_content_hash`. Never edit past blocks.
- Predictions `data/learning/prediction_ledger.json`: one batch per session (`daily_rise_fall_scanner.py`); labelled by `multi_horizon_evaluator.py` only after the full declared horizon; non-trading dates → `INVALID_NON_TRADING_DAY`. RL weights (`reinforcement_learning_engine.py`) deterministic shrinkage, n ≥ 15 else 1.0.

## User portfolio

- Ledgers: `data/users/default_user/portfolio.json` and `data/portfolio/portfolio.json` (kept in sync by `portfolio_manager` / `user_manager.save_user_portfolio`).
- `total_capital_bdt` = **invested amount only** = share cost basis + mutual fund cost (not deposits). Derived on save; `reconcile_ledger` checks it.
- Record trades only via `main.py buy/sell` (`record_buy/record_sell`); `bought_at` preserved on top-ups. Dividends entitled by settlement date (`entitled_shares`), credited to cash, never to capital.
- HWM updated only on the live ledger, against mark-to-market net worth.
- Mutual fund (Shanta Amanah Shariah Fund): `mutual_fund_tracker.py` (no args = online fetch, or `<nav> <date>` manual). Online parse must match the fund name; moves >10% rejected (`nav_is_plausible`); no NAV ⇒ write nothing.

## Testing

- Run all: `python -m unittest discover -s tests -t .` (~164 tests, ~2–3 min). Regression set for audit fixes: `tests/test_p0_fixes.py`.
- Tests must never touch real data: use `tests/_isolation.py` (`temp_db_copy()`, `isolated_learning_files()`), inject portfolios instead of loading the real one. `tests/test_zzz_real_data_untouched.py` fails if protected files/tables changed.
- To validate daily writers end-to-end, copy the repo + DB (SQLite backup API) into a scratch dir and run the routine twice; compare outputs.

## Working rules

- Validate impact before edits (callers of shared helpers like `processor`, `feature_store`, `unified_score`, `portfolio_manager`); smallest diff; no narrating comments.
- Don't write Python files via shell heredocs containing backslashes (`\b`, `\n` got corrupted before) — use the editor tools.
- Before any bulk data repair: back up (`*.pre_<name>.bak`, gitignored), dry-run first, then `--apply`; rerun the data gate after.
- `push_db_update.py` / `main.py push-db [--dry-run]`: data gate → backup-API snapshot (integrity_check + guards present) → deterministic gzip (mtime=0) → spec guard (rolls back previous archive on fail) → commits **only** `dse.db.gz` on master and pushes. Unchanged DB ⇒ no-op. Never commit a DB that fails the gate.
- `bootstrap.py` restores `dse.db` from the archive only when the local DB is missing/corrupt (drops stale `-wal/-shm`, atomic replace). A `git pull` never overwrites an existing local DB.
- Known open gaps: bank NPL/CAR empty until sourced; pre-Nov-2024 publication dates/record dates are estimates; SME board unserved after 2026-01-22; ACI/APEXFOOT/IDLC pre-archive prices not un-scaled; `feature_store` adjusts only bonus (not split/rights) and filters by today's category — Tier 3, needs a champion re-freeze; forward-ledger genesis has no external anchor.
