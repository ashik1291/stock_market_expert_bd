"""
scripts/db_knowledge_schema.py — Create SQLite Feature Store Tables

Creates:
  1. company_signals_history: Time-series multi-factor analytical signals, technicals, fundamentals, manipulation flags.
  2. company_pattern_dna_history: Valuation sanity, multi-interval waves, causal attributions.
Includes indexes for ultra-fast queries (< 10ms).
"""

from __future__ import annotations

import sys
import sqlite3
import logging
from pathlib import Path

# UTF-8 encoding
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "dse.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("db_knowledge_schema")


def init_knowledge_schema() -> bool:
    if not DB_PATH.exists():
        log.error(f"Database not found at {DB_PATH}")
        return False

    log.info(f"Opening database: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    cur = conn.cursor()

    log.info("Creating company_signals_history table and indexes...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS company_signals_history (
            date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            timeframe TEXT NOT NULL DEFAULT 'weekly',
            horizon TEXT DEFAULT 'short',
            analyzed_at TEXT,
            asof_price_date TEXT,
            served_model_id TEXT,
            served_model_score REAL,
            signal TEXT NOT NULL,
            confidence REAL NOT NULL,
            entry_price REAL,
            stop_loss REAL,
            target_price REAL,
            rsi_14 REAL,
            pe_ratio REAL,
            debt_equity REAL,
            technical_score REAL,
            fundamental_score REAL,
            sentiment_score REAL,
            governance_score REAL,
            composite_score REAL,
            manipulation_risk TEXT DEFAULT 'low',
            manipulation_score REAL,
            block_buy INTEGER DEFAULT 0,
            range_52w_pct REAL,
            range_52w_regime TEXT,
            full_payload TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (date, ticker, timeframe)
        )
    """)

    # High-speed indexes for screening, filtering, and time-series backtests
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sig_ticker_date ON company_signals_history(ticker, date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sig_date_signal ON company_signals_history(date, signal)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sig_date_conf ON company_signals_history(date, confidence DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sig_date_pe_rsi ON company_signals_history(date, pe_ratio, rsi_14)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sig_range_52w ON company_signals_history(date, range_52w_pct)")

    log.info("Creating company_pattern_dna_history table and indexes...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS company_pattern_dna_history (
            date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            audited_at TEXT,
            current_price REAL,
            intrinsic_worth REAL,
            margin_of_safety_pct REAL,
            greed_index REAL,
            current_wave_phase TEXT,
            full_payload TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (date, ticker)
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_dna_ticker_date ON company_pattern_dna_history(ticker, date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_dna_date_mos ON company_pattern_dna_history(date, margin_of_safety_pct DESC)")

    log.info("Creating governance_risk_audit table and indexes...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS governance_risk_audit (
            ticker TEXT NOT NULL,
            assessment_date TEXT NOT NULL,
            political_exposure_score REAL DEFAULT 0.0,
            legal_risk_tier TEXT DEFAULT 'LOW',
            sponsor_legal_issues INTEGER DEFAULT 0,
            receivership_court_petition INTEGER DEFAULT 0,
            bank_accounts_frozen INTEGER DEFAULT 0,
            bsec_investigation INTEGER DEFAULT 0,
            regulatory_sanctions_count INTEGER DEFAULT 0,
            active_flags TEXT,
            governance_notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ticker, assessment_date)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_gov_ticker ON governance_risk_audit(ticker)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_gov_tier ON governance_risk_audit(legal_risk_tier)")

    log.info("Creating revenue_segment_breakdown table and indexes...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS revenue_segment_breakdown (
            ticker TEXT NOT NULL,
            fiscal_year INTEGER NOT NULL,
            total_revenue_cr REAL,
            domestic_revenue_cr REAL,
            export_revenue_cr REAL,
            export_share_pct REAL,
            us_fda_approved INTEGER DEFAULT 0,
            uk_mhra_approved INTEGER DEFAULT 0,
            who_gmp_approved INTEGER DEFAULT 1,
            tga_australia_approved INTEGER DEFAULT 0,
            export_destinations_count INTEGER DEFAULT 0,
            top_export_markets TEXT,
            currency_sensitivity_score REAL DEFAULT 0.0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ticker, fiscal_year)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rev_ticker_yr ON revenue_segment_breakdown(ticker, fiscal_year)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rev_export_share ON revenue_segment_breakdown(export_share_pct DESC)")

    conn.commit()
    conn.close()
    log.info("✅ SQLite Knowledge Feature Store tables and indexes initialized successfully.")
    return True


if __name__ == "__main__":
    ok = init_knowledge_schema()
    sys.exit(0 if ok else 1)
