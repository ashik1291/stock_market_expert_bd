"""
scripts/db_guards.py — Write-time data guards stored inside dse.db as SQLite triggers.

Triggers live in the database file, so they hold for every writer: pipeline scripts, one-off
scripts and ad-hoc SQL typed by a person or an LLM agent. Each guard blocks one class of
corruption that was found in the 2026-11-20 audit:

  prices             bars on calendar-closed days (replayed holiday snapshots), non-positive or
                     inverted OHLC
  corporate_actions  plug rows used to paper over price gaps, price-affecting actions with an
                     invented date, factors outside (0, 1]
  fundamentals_pit   publication/tradable dates out of order, conservative-estimate sources
                     labelled as verified, fiscal periods that have not ended yet

The integrity harness fails if any guard is missing. Never drop these triggers to make a write
succeed; fix the data or the calendar instead.
"""

from __future__ import annotations

import sqlite3

ALLOWED_ACTION_TYPES = ("cash_dividend", "bonus_dividend", "split", "rights_split", "rights")
PRICE_ACTION_TYPES = ("bonus_dividend", "split", "rights_split")
ESTIMATED_ONLY_SOURCES = ("bsec_statutory_filing", "dse_corporate_action", "estimated")


def _in(values: tuple) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


GUARDS = {
    "guard_prices_insert": f"""
        CREATE TRIGGER IF NOT EXISTS guard_prices_insert BEFORE INSERT ON prices
        BEGIN
            SELECT RAISE(ABORT, 'guard: price bar on a trading_calendar closed day')
            WHERE EXISTS (SELECT 1 FROM trading_calendar WHERE date = NEW.date AND is_trading_day = 0);
            SELECT RAISE(ABORT, 'guard: non-positive close')
            WHERE NEW.close IS NULL OR NEW.close <= 0;
            SELECT RAISE(ABORT, 'guard: high below low')
            WHERE NEW.high IS NOT NULL AND NEW.low IS NOT NULL AND NEW.high < NEW.low;
        END
    """,
    "guard_prices_update": f"""
        CREATE TRIGGER IF NOT EXISTS guard_prices_update BEFORE UPDATE ON prices
        BEGIN
            SELECT RAISE(ABORT, 'guard: non-positive close')
            WHERE NEW.close IS NULL OR NEW.close <= 0;
            SELECT RAISE(ABORT, 'guard: high below low')
            WHERE NEW.high IS NOT NULL AND NEW.low IS NOT NULL AND NEW.high < NEW.low;
        END
    """,
    **{
        f"guard_corporate_actions_{op.lower()}": f"""
        CREATE TRIGGER IF NOT EXISTS guard_corporate_actions_{op.lower()} BEFORE {op} ON corporate_actions
        BEGIN
            SELECT RAISE(ABORT, 'guard: corporate action type not allowed (no plug rows)')
            WHERE NEW.action_type NOT IN {_in(ALLOWED_ACTION_TYPES)};
            SELECT RAISE(ABORT, 'guard: price-affecting action needs 0 < adjustment_factor < 1')
            WHERE NEW.action_type IN {_in(PRICE_ACTION_TYPES)}
              AND NOT (NEW.adjustment_factor > 0 AND NEW.adjustment_factor < 1);
            SELECT RAISE(ABORT, 'guard: price-affecting action with an invented date')
            WHERE NEW.action_type IN {_in(PRICE_ACTION_TYPES)}
              AND COALESCE(NEW.notes, '') LIKE '%Historical estimated%';
        END
    """ for op in ("INSERT", "UPDATE")
    },
    **{
        f"guard_fundamentals_pit_{op.lower()}": f"""
        CREATE TRIGGER IF NOT EXISTS guard_fundamentals_pit_{op.lower()} BEFORE {op} ON fundamentals_pit
        BEGIN
            SELECT RAISE(ABORT, 'guard: publication_date before snapshot_date')
            WHERE NEW.publication_date IS NOT NULL AND NEW.publication_date < NEW.snapshot_date;
            SELECT RAISE(ABORT, 'guard: tradable_date before publication_date')
            WHERE NEW.tradable_date IS NOT NULL AND NEW.publication_date IS NOT NULL
              AND NEW.tradable_date < NEW.publication_date;
            SELECT RAISE(ABORT, 'guard: estimated publication source cannot be marked verified')
            WHERE NEW.publication_source IN {_in(ESTIMATED_ONLY_SOURCES)}
              AND COALESCE(NEW.publication_is_estimated, 0) = 0;
        END
    """ for op in ("INSERT", "UPDATE")
    },
    **{
        f"guard_fundamentals_pit_period_{op.lower()}": f"""
        CREATE TRIGGER IF NOT EXISTS guard_fundamentals_pit_period_{op.lower()} BEFORE {op} ON fundamentals_pit
        BEGIN
            SELECT RAISE(ABORT, 'guard: fiscal period has not ended yet')
            WHERE NEW.snapshot_date > date('now', 'localtime');
        END
    """ for op in ("INSERT", "UPDATE")
    },
    # A row deleted with logged evidence must not be recreated by a legacy writer; official rows may still land.
    "guard_corporate_actions_tombstone": """
        CREATE TRIGGER IF NOT EXISTS guard_corporate_actions_tombstone BEFORE INSERT ON corporate_actions
        BEGIN
            SELECT RAISE(IGNORE)
            WHERE COALESCE(NEW.notes, '') NOT LIKE '%dse_disclosure%'
              AND EXISTS (SELECT 1 FROM corporate_action_corrections t
                          WHERE t.ticker = NEW.ticker AND t.record_date = NEW.record_date
                            AND t.action_type = NEW.action_type AND t.change LIKE 'deleted%');
        END
    """,
    # Rows sourced from official DSE filings are only ever rewritten by the official reconcilers.
    "guard_corporate_actions_official_lock": """
        CREATE TRIGGER IF NOT EXISTS guard_corporate_actions_official_lock BEFORE UPDATE ON corporate_actions
        BEGIN
            SELECT RAISE(IGNORE)
            WHERE COALESCE(OLD.notes, '') LIKE '%dse_disclosure%' AND COALESCE(NEW.notes, '') NOT LIKE '%dse_disclosure%';
        END
    """,
    "guard_corporate_actions_verified_lock": """
        CREATE TRIGGER IF NOT EXISTS guard_corporate_actions_verified_lock BEFORE UPDATE ON corporate_actions
        BEGIN
            SELECT RAISE(IGNORE)
            WHERE COALESCE(OLD.notes, '') LIKE '%verified against official DSE dividend history%'
              AND COALESCE(NEW.notes, '') NOT LIKE '%verified against official DSE dividend history%';
        END
    """,
    "guard_fundamentals_pit_official_lock": """
        CREATE TRIGGER IF NOT EXISTS guard_fundamentals_pit_official_lock BEFORE UPDATE ON fundamentals_pit
        BEGIN
            SELECT RAISE(IGNORE)
            WHERE OLD.publication_source = 'dse_disclosure' AND COALESCE(NEW.publication_source, '') != 'dse_disclosure';
        END
    """,
}

_GUARD_TABLES = {
    "guard_corporate_actions_official_lock": ("corporate_actions",),
    "guard_corporate_actions_verified_lock": ("corporate_actions",),
    "guard_fundamentals_pit_official_lock": ("fundamentals_pit",),
    "guard_corporate_actions_tombstone": ("corporate_actions", "corporate_action_corrections"),
    "guard_prices_insert": ("prices", "trading_calendar"),
    "guard_prices_update": ("prices",),
    "guard_corporate_actions_insert": ("corporate_actions",),
    "guard_corporate_actions_update": ("corporate_actions",),
    "guard_fundamentals_pit_insert": ("fundamentals_pit",),
    "guard_fundamentals_pit_update": ("fundamentals_pit",),
    "guard_fundamentals_pit_period_insert": ("fundamentals_pit",),
    "guard_fundamentals_pit_period_update": ("fundamentals_pit",),
}


def install_data_guards(conn: sqlite3.Connection) -> list[str]:
    """Create every guard whose tables exist. Idempotent. Returns names installed or already present."""
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if "corporate_actions" in tables and "corporate_action_corrections" not in tables:
        from official_corporate_actions import SCHEMA as CORRECTIONS_SCHEMA
        conn.executescript(CORRECTIONS_SCHEMA)
        tables.add("corporate_action_corrections")
    done = []
    for name, ddl in GUARDS.items():
        if all(t in tables for t in _GUARD_TABLES[name]):
            conn.execute(ddl)
            done.append(name)
    conn.commit()
    return done


def missing_data_guards(conn: sqlite3.Connection) -> list[str]:
    present = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
    return [n for n in GUARDS if n not in present]


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from db import get_db_connection
    c = get_db_connection()
    print("installed:", install_data_guards(c))
    print("missing:", missing_data_guards(c))
    c.close()
