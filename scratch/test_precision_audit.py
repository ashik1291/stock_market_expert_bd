import sqlite3
import json
import sys
sys.path.insert(0, ".")
from scripts.precision_engine import run_precision_audit

conn = sqlite3.connect("data/processed/dse.db")
cursor = conn.cursor()
cursor.execute("SELECT raw_data FROM fundamentals WHERE ticker='SQURPHARMA'")
row = cursor.fetchone()
raw_data = json.loads(row[0]) if row and row[0] else {}

cursor.execute("SELECT date, open, high, low, close, volume FROM prices WHERE ticker='SQURPHARMA' ORDER BY date ASC")
prices = [{"date": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]} for r in cursor.fetchall()]
conn.close()

result = run_precision_audit("SQURPHARMA", prices, raw_data)
print(json.dumps(result, indent=2))
