import sqlite3
import json

conn = sqlite3.connect("data/processed/dse.db")
cursor = conn.cursor()
cursor.execute("SELECT ticker, raw_data FROM fundamentals WHERE ticker='SQURPHARMA'")
row = cursor.fetchone()
if row and row[1]:
    data = json.loads(row[1])
    print("share_pattern_history for SQURPHARMA:")
    print(json.dumps(data.get("share_pattern_history"), indent=2))
conn.close()
