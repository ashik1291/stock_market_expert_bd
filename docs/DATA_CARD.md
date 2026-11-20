# Data Card — DSE Research Dataset (`stock_market_expert_bd`)

**Purpose:** academic and research use, and personal decision support. Not a commercial data product; no warranty.
**Market:** Dhaka Stock Exchange (DSE), Bangladesh. **Unit of observation:** instrument × trading session; company × fiscal period.
**Snapshot described:** latest session 2026-11-19 (figures below were measured on 2026-11-20).

## 1. Sources

| Source | What it provides | Access |
|---|---|---|
| DSE live market feed (`dse.com.bd/api/live/*`, bdshare) | Daily OHLCV snapshot, instrument type/board/category, index constituents (DSEX, DS30) | Public website / API |
| DSE official day-end archive (bdshare `get_historical_data`) | Official end-of-day bars; reachable from Dec 2024 only | Public |
| DSE announcement archive (`/api/live/news`) | Every company announcement since 2024-11-20: financial results (EPS, NAV, NOCFPS), dividend declarations, record-date and suspension notices, BSEC consents, category changes | Public |
| DSE company pages (`/company/<code>`) | Per-fiscal-year dividend history (cash %, stock %) for 2021+, face value, multi-year financials (original and restated) | Public |
| Bangladesh Bank (`bb.org.bd`) | 91-day BCR (compounded T-bill reference rate), DOMMR overnight money-market rate | Public |
| Manual entries | 91-day T-bill cut-off yield, repo rate, CPI (`macro_rate_feed.py --update`), bank NPL/CAR (`bank_asset_quality.py`, source URL mandatory) | Cited documents |

## 2. Tables

| Table | Rows | Content |
|---|---|---|
| `prices` | 1,172,374 (484 instruments, 2012-10-01 → 2026-11-19) | Raw, **unadjusted** daily bars. Corporate-action adjustment is applied at read time. Columns `source`, `ingest_id`, `archive_verified_on`, `quality_flags` record provenance |
| `trading_calendar` | 3,653 sessions | Exchange calendar, incl. make-up sessions |
| `instruments` | 484 | Type (384 equity, 36 mutual fund, 55 govt bond, 9 corporate bond), board, first/last trade, status (active/inactive) with evidence |
| `category_history` | 566 intervals | DSE category (A/B/N/Z) per ticker; exact from 2024-11-20 |
| `index_membership` | DSEX 319, DS30 30 | Point-in-time constituents, captured from 2026-11-19 |
| `fundamentals_pit` | 3,574 filings, 330 companies | EPS, NAV, NOCFPS, D/E etc. keyed by fiscal period end, with `publication_date` and `tradable_date` |
| `disclosures` / `disclosure_financials` | 25,000+ announcements / 2,452 parsed filings | Raw official announcements (immutable) and the financial figures parsed from them |
| `corporate_actions` | ~1,030 | Cash dividends, bonus issues, rights (`source` column gives origin) |
| `company_dividend_history` | 1,954 company-years, 395 companies | DSE's official per-fiscal-year dividend % (2021+) |
| `macro_indicators` | — | Each value stored at its own publication date |
| `bank_asset_quality` | 0 | Sourced bank NPL/CAR only |
| Audit: `pit_corrections`, `corporate_action_corrections`, `archive_crosscheck(_diffs)`, `ingest_log`, `data_quality_daily` | — | Every correction with its evidence, every ingest with the SHA-256 of its raw payload, cross-check results, daily quality metrics |

## 3. Point-in-time rules

- A fundamental value is usable only when `publication_date ≤ asof` and `tradable_date ≤ asof`; `tradable_date` is the first session after publication.
- `publication_is_estimated = 0` means the publication date was **observed** (DSE announcement, or a live observation). **74%** of all PIT rows and **99.4%** of filings for periods since Sep 2024 are observed; older dates are conservative statutory-deadline estimates (never earlier than the legal deadline).
- Values are the **first published** figures (original, not restated). Interim EPS is the discrete quarter; interim NOCFPS (year-to-date) is kept only in `disclosure_financials`; `cash_flow_ops` holds annual NOCFPS.
- Fiscal periods are per company (fiscal-year-end month verified against annual and Q1 filings).
- Read each field from its own latest published row: official filings carry EPS/NAV/NOCFPS but not D/E or P/E.

## 4. Corporate actions

- Since Nov 2024: from official dividend declarations; record dates confirmed by the exchange's "suspended on record date" notices (holiday shifts included); stock dividends dated by BSEC consent notices, BSEC rejections excluded; subsidiary dividends excluded; rights adjusted with the theoretical ex-rights factor from the cum-rights close.
- Cash per share = declared % × face value (Tk 10; BSEC uniform face value, verified on company pages).
- Before Nov 2024: rows from company-page notices and dated price-gap inference for bonuses; amounts audited against the official dividend history where it covers the year (2021+). **450 cash rows carry estimated record dates** (`source = 'estimated_placeholder'`) — use their dates with care.

## 5. Verification

- `archive_crosscheck`: every stored session the official day-end archive serves (2024-11-20 → 2026-11-19, **479 sessions**) compared bar-by-bar: **212,673 bars compared, 212,673 identical (100.000%), 0 mismatches**. Matching bars carry `archive_verified_on`. Not comparable: SME-board stocks plus SALVO and BNIPLC (absent from the archive; ~20 bars/session until Jan 2026, from the live feed) and 3 untraded perpetual bonds listed in the archive with zero volume. Re-run with `scripts/archive_crosscheck.py --report`.
- The last 5 sessions are re-reconciled with the official archive every day.
- Integrity gate (`scripts/integrity_harness.py --data-gate`) blocks downstream writes on critical failures; database triggers reject closed-day bars, invalid price actions, out-of-order PIT dates, unended fiscal periods, re-creation of rows deleted with evidence and non-official overwrites of official rows.

## 6. Known limitations

- Bars before Dec 2024 cannot be re-verified against an official source (DSE no longer serves that history); they are labelled `legacy_pre_provenance`.
- SME-board stocks are not served by any reachable DSE feed after 2026-01-22 (marked inactive, not filled).
- 3 tickers (ACI, APEXFOOT, IDLC) carry unadjusted pre-archive history.
- 431 zero volumes were imputed from missing values (`quality_flags` contains `volume_imputed`); 21 bars have no open price (`open_missing`).
- Categories before 2024-11-20 and index membership before 2026-11-19 are unknown.
- Bank NPL/CAR have no structured official feed; empty until imported from cited documents.
- 91-day T-bill cut-off yield, repo and CPI are manual entries (last 2025-01-01); Bangladesh Bank's BCR and DOMMR are captured daily.

## 7. Versions and citation

- `python scripts/dataset_release.py release` writes `data/releases/dse-<session>-<fingerprint>/` (gzipped CSV per table, `manifest.json` with row counts, SHA-256 per file, schemas, git commit). The fingerprint covers values only, so re-verification does not change the version.
- Every forward-test ledger block records the `dataset_fingerprint` of the data it was computed on.
- Cite as: *DSE Research Dataset, version `dse-<session>-<fingerprint>`, built with stock_market_expert_bd (public DSE and Bangladesh Bank sources).*
