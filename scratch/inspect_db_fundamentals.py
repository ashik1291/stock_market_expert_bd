import sqlite3
import json

conn = sqlite3.connect("data/processed/dse.db")
cursor = conn.cursor()
cursor.execute("SELECT ticker, raw_data FROM fundamentals WHERE ticker='SQURPHARMA'")
row = cursor.fetchone()
if row and row[1]:
    data = json.loads(row[1])
    print("Keys in SQURPHARMA raw_data:")
    for k in sorted(data.keys()):
        val = data[k]
        if isinstance(val, (dict, list)):
            print(f"  {k}: {type(val)} with {len(val)} items")
        else:
            print(f"  {k}: {val}")
conn.close()
