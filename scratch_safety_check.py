import sqlite3
import database
import source_enrichment as se

conn = database.get_connection()
rows = conn.execute("SELECT id, source, language, title, url, summary FROM articles ORDER BY fetched_at DESC LIMIT 30").fetchall()
before = {r["id"]: r["summary"] for r in rows}
conn.close()

# call the real function against real article dicts (network calls will actually
# happen for eligible ones - this populates the NEW article_enrichment cache table
# only, per design; articles/events must stay untouched)
for r in rows:
    a = dict(r)
    _ = se.get_combined_summary_for_article(a)

conn2 = database.get_connection()
after_rows = conn2.execute("SELECT id, summary FROM articles WHERE id IN ({})".format(
    ",".join(str(r["id"]) for r in rows))).fetchall()
after = {r["id"]: r["summary"] for r in after_rows}
conn2.close()

mismatches = [aid for aid in before if before[aid] != after.get(aid)]
print(f"checked {len(before)} real articles.summary rows")
print(f"mismatches after enrichment calls: {len(mismatches)}")
if mismatches:
    print("FAIL - articles.summary was mutated:", mismatches)
else:
    print("PASS - articles.summary byte-for-byte unchanged for every row")

# also confirm events/event_relationships untouched
conn3 = sqlite3.connect("paksh.db")
print("event_relationships rows:", conn3.execute("SELECT COUNT(*) FROM event_relationships").fetchone()[0], "(expect 4, unchanged)")
print("events count:", conn3.execute("SELECT COUNT(*) FROM events").fetchone()[0])
print("article_enrichment rows now:", conn3.execute("SELECT COUNT(*) FROM article_enrichment").fetchone()[0])
conn3.close()
