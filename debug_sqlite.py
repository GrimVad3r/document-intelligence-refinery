import sqlite3
import os

DB_PATH = ".refinery/facts.db"

print(f"DB exists: {os.path.exists(DB_PATH)}")
print(f"DB path: {os.path.abspath(DB_PATH)}")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Check tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cur.fetchall()
print("Tables:", tables)

# Check document IDs
cur.execute("SELECT DISTINCT document_id FROM extracted_facts;")
doc_ids = cur.fetchall()
print("Document IDs:", doc_ids)

# Run your query
cur.execute("""
SELECT table_id, page_number, row_index, col_index, column_header, value_text
FROM extracted_facts
WHERE document_id=?
LIMIT 15
""", ("company_profile",))

rows = cur.fetchall()
print(f"Rows returned: {len(rows)}")

for r in rows:
    print(r)

conn.close()