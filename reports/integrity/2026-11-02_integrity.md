# Integrity Harness — 2026-11-02T15:04:31.557524
**Result**: PASS (0 failures)

| Check | Status | Detail |
|---|---|---|
| `ledger_asof_matches_prices` | **PASS** | ledger_asof=2026-11-02 latest_price=2026-11-02 |
| `ledger_strategy_status_present` | **PASS** | status=ACTIVE |
| `thresholds_weights_sum_1` | **PASS** | sum=1.0 |
| `served_weights_match_frozen_hash` | **PASS** | model=frozen_epoch2_pit_v2 hash=acf502bc65914c48 weights={'div': 1.0, 'value': 1.0, 'debt': 0.0, 'rsi': 0.0} |
| `shadow_ic_weights_nonnegative` | **PASS** | weights={'div': 1.4, 'value': 0.0, 'rsi': 1.4, 'debt': 0.0} |
| `rank_log_full_universe` | **PASS** | ranks=118 features=118 date=2026-11-02 |
| `registry_champion` | **PASS** | id=frozen_epoch2_pit_v2 hash=acf502bc65914c48 |
| `no_fake_base_rate_66_4` | **PASS** | clean |
| `data_freshness` | **PASS** | fresh (latest=2026-11-02, expected=2026-11-02, lag=0 sessions) |