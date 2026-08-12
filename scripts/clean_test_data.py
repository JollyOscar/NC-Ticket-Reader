import sqlite3
from pathlib import Path

db = Path(__file__).parent.parent / "data" / "prototype.db"
conn = sqlite3.connect(db)
n = conn.execute(
    "SELECT COUNT(*) FROM tickets WHERE review_status IN ('needs_review','auto_ready')"
).fetchone()[0]
conn.execute("DELETE FROM tickets WHERE review_status IN ('needs_review','auto_ready')")
conn.commit()
remaining = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
conn.close()
print(f"Deleted {n} unreviewed records. Remaining: {remaining}")
