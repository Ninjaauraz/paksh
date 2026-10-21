"""Tests: story-source url_kind/publisher_url annotation (export_static) and SectionsHub
consistency (static/app.jsx). Run: py test_phase_source_urls_sections.py"""
import sqlite3
from pathlib import Path

import export_static as ex

F = []


def check(label, cond):
    print(f"  {label} ... {'OK' if cond else 'FAIL'}")
    if not cond:
        F.append(label)


GN = "https://news.google.com/rss/articles/CBMiX"
srcs = [{"source": "A", "url": GN + "1"}, {"source": "B", "url": GN + "2"},
        {"source": "C", "url": "https://c.example/story"}, {"source": "D", "url": GN + "3"}]
ex._annotate_source_urls(srcs, {GN + "1": "https://a.example/real", GN + "3": "https://news.google.com/x"})
check("verified sibling -> publisher_verified + publisher_url",
      srcs[0]["url_kind"] == "publisher_verified" and srcs[0]["publisher_url"] == "https://a.example/real")
check("original url retained as fallback", srcs[0]["url"] == GN + "1")
check("unrecovered wrapper -> google_news_wrapper, no publisher_url",
      srcs[1]["url_kind"] == "google_news_wrapper" and "publisher_url" not in srcs[1])
check("direct url -> direct", srcs[2]["url_kind"] == "direct")
check("a wrapper offered as publisher_url is rejected",
      srcs[3]["url_kind"] == "google_news_wrapper" and "publisher_url" not in srcs[3])
check("attribution untouched", [s["source"] for s in srcs] == ["A", "B", "C", "D"])

c = sqlite3.connect(":memory:")
c.execute("CREATE TABLE article_publisher_url (article_id INTEGER, original_url TEXT, publisher_url TEXT, "
          "status TEXT, domain_consistent INTEGER)")
c.executemany("INSERT INTO article_publisher_url VALUES (?,?,?,?,?)", [
    (1, GN + "1", "https://a.example/1", "VERIFIED_SIBLING", 1),
    (2, GN + "2", "https://b.example/2", "VERIFIED_SIBLING", 0),
    (3, GN + "3", None, "AMBIGUOUS", None),
    (4, GN + "4", "https://d.example/4", "VERIFIED_SIBLING", None),
    (5, GN + "5", "https://e.example/5", "REJECTED_DOMAIN", 0)])
got = ex._load_recovered_urls(c, [{"url": GN + str(i)} for i in range(1, 6)] + [{"url": "https://x.example/"}])
check("only VERIFIED_SIBLING with domain not failed",
      got == {GN + "1": "https://a.example/1", GN + "4": "https://d.example/4"})
check("no connection -> {}", ex._load_recovered_urls(None, srcs) == {})
check("missing table -> {}", ex._load_recovered_urls(sqlite3.connect(":memory:"), srcs) == {})

import contextlib, io
ex._RECOVERY_WARNED = False
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    r1 = ex._load_recovered_urls(None, srcs)
    r2 = ex._load_recovered_urls(sqlite3.connect(":memory:"), srcs)   # table missing
out = buf.getvalue()
check("unavailable enrichment emits an explicit WARNING, once per run",
      out.count("WARNING: publisher-URL recovery unavailable") == 1)
check("unavailable enrichment returns {} (safe fallback)", r1 == {} and r2 == {})
fb = [{"source": "A", "url": GN + "9"}]
ex._annotate_source_urls(fb, r1)
check("fallback keeps original url and wrapper label", fb[0]["url"] == GN + "9" and fb[0]["url_kind"] == "google_news_wrapper" and "publisher_url" not in fb[0])
ex._RECOVERY_WARNED = False

jsx = (Path(__file__).parent / "static" / "app.jsx").read_text(encoding="utf-8")
a = jsx.index("function SectionsHub(")
hub = jsx[a:jsx.index("\n    function ", a)]
check("SectionsHub renders every section (no LEAD_N split)", "LEAD_N" not in hub and "rest=[]" in hub)
check("SectionsHub shows no story counts", "mono text-[11px]" not in hub and "mono text-[10.5px]" not in hub)
b = jsx.index("function SectionPage(")
page = jsx[b:jsx.index("\n    function ", b)]
check("SectionPage heading shows no count", "totalCount" not in page and "mono text-[11px]" not in page)

print("FAILED: " + ", ".join(F) if F else "ALL ASSERTIONS PASSED")
raise SystemExit(1 if F else 0)
