import sqlite3
conn = sqlite3.connect("data/prototype.db")
conn.row_factory = sqlite3.Row
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables:", [t[0] for t in tables])
for t in tables:
    cols = conn.execute(f"PRAGMA table_info({t[0]})").fetchall()
    print(f"\n{t[0]} columns:")
    for c in cols:
        print(f"  {c[1]} ({c[2]})")
    count = conn.execute(f"SELECT COUNT(*) FROM {t[0]}").fetchone()[0]
    print(f"  -> {count} rows")
    if count > 0 and count <= 30:
        rows = conn.execute(f"SELECT * FROM {t[0]}").fetchall()
        for r in rows:
            # Print key fields
            d = dict(r)
            img = d.get("image_path", "")
            tid = d.get("ticket_id", "")
            rid = d.get("id", "")
            status = d.get("review_status", "")
            print(f"    id={rid} ticket_id={tid} status={status} image={img}")
conn.close()
