import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pathlib import Path
import database
database.DB_PATH = Path("/tmp/paksh_ingest_test.db")
if database.DB_PATH.exists():
    database.DB_PATH.unlink()
database.init_db()

import ingest
HERE = os.path.dirname(os.path.abspath(__file__))
en = {"id": "the_hindu", "name": "The Hindu", "language": "en", "lean": "left"}
hi = {"id": "amar_ujala", "name": "Amar Ujala", "language": "hi", "lean": "center"}

seen = set()
n_en, c_en = ingest.ingest_feed(os.path.join(HERE, "en_fixture.xml"), en, seen)
n_hi, c_hi = ingest.ingest_feed(os.path.join(HERE, "hi_fixture.xml"), hi, seen)
n_re, c_re = ingest.ingest_feed(os.path.join(HERE, "en_fixture.xml"), en, set())  # fresh run

print(f"English feed : {n_en} new / {c_en} considered   (expect 2 new, in-run dup dropped)")
print(f"Hindi feed   : {n_hi} new / {c_hi} considered   (expect 2 new)")
print(f"Re-ingest EN : {n_re} new / {c_re} considered   (expect 0 new, DB-level dedupe)")

assert n_en == 2 and c_en == 3, "in-run URL dedupe failed"
assert n_hi == 2, "hindi ingest failed"
assert n_re == 0, "cross-run DB dedupe failed"

print("\nStored rows:")
conn = database.get_connection()
for r in conn.execute("SELECT source, language, title, url, image_url, published FROM articles ORDER BY id"):
    print(f"  [{r['language']}] {r['source']}")
    print(f"      title : {r['title']}")
    print(f"      url   : {r['url']}")
    print(f"      image : {r['image_url'] or '(none)'}")
    print(f"      date  : {r['published']}")
conn.close()
print("\nALL ASSERTIONS PASSED")
