"""
test_story_evolution.py - the internal Story Evolution object (story_evolution.py) and its claim graph. Synthetic stories, in-memory SQLite,
no embedding model, no network, never touches paksh.db.   Run: py test_story_evolution.py
"""
import sqlite3

import story_evolution as se
import story_intelligence as si

FAILURES = []


def check(label, cond, extra=""):
    print(f"  {label} ... {'OK' if cond else 'FAIL'} {extra if not cond else ''}")
    if not cond:
        FAILURES.append(label)


def art(i, source, title, published, url=None, summary=""):
    return {"id": i, "source": source, "language": "en", "title": title, "summary": summary, "published": published,
            "fetched_at": "2026-09-20T18:00:00", "vec": None, "url": url or f"https://example.com/{i}"}


NAMES = ["The Hindu", "NDTV", "Reuters", "Hindustan Times", "Indian Express"]
own = lambda n: n
ROWS = [art(1, "NDTV", "Mosque blast kills 21 in Pakistan, police say", "2026-09-20T08:00:00"),
        art(2, "The Hindu", "Pakistan mosque bombing: death toll rises to 31", "2026-09-20T12:00:00", url="https://news.google.com/rss/articles/CBMiXYZ"),
        art(3, "Reuters", "Bomb at Pakistan mosque kills 31, officials say", "2026-09-20T13:00:00"),
        art(4, "Indian Express", "Pakistan mosque attack: what we know", "2026-09-20T14:00:00")]


def conn_with(rows):
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, title TEXT)")
    c.execute("INSERT INTO events VALUES (1, 'Pakistan mosque blast')")
    return c


def build(rows, publisher_urls=None):
    orig = se._rows_for
    se._rows_for = lambda conn, eid: [dict(r) for r in rows]
    try:
        return se.build_story_evolution(conn_with(rows), 1, owner_of=own, evidence={}, publisher_urls=publisher_urls or {})
    finally:
        se._rows_for = orig


print("TEST 1: the object")
o = build(ROWS)
check("1a: available, internal schema, engine version recorded", o["available"] and o["schema"] == "story-evolution-internal-1" and o["engine_version"] == si.ENGINE_VERSION)
check("1b: the first report is the earliest by publish time and says it is only the earliest in Paksh's corpus",
      o["first_report"]["article_id"] == 1 and "not necessarily the first report anywhere" in o["first_report"]["note"])
tl = [t["order_time"] for t in o["timeline"]]
check("1c: the timeline is in non-decreasing order_time", tl == sorted(tl))
check("1d: event_time is never inferred, anywhere", all(t["event_time"] is None for t in o["timeline"]) and o["first_report"]["event_time"] is None)
check("1e: every report carries provenance (published_at, first_seen_at, order_basis, original_url, publisher_url, evidence_source)",
      all(k in o["first_report"] for k in ("published_at", "first_seen_at", "order_basis", "original_url", "publisher_url", "evidence_source")))
W = [dict(ROWS[0], url="https://news.google.com/rss/articles/CBMiABC")] + ROWS[1:]
o2 = build(W, {1: "https://ndtv.com/real-story"})
check("1f/1g: a recovered publisher URL sits beside the stored (Google News) URL and never replaces it",
      o2["first_report"]["original_url"] == "https://news.google.com/rss/articles/CBMiABC" and o2["first_report"]["publisher_url"] == "https://ndtv.com/real-story")
check("1h: fewer than two articles -> unavailable, no exception", not build(ROWS[:1])["available"])
check("1i: shape carries a hint and a caution slot; limits are stated", o["shape"]["hint"] in ("narrow_event", "broad_topic_cluster") and len(o["limits"]) >= 3)

print("\nTEST 2: claim graph - who reported a figure and how, never 'confirmed'")
g = o["claim_graph"]
nodes = {(n["measure"], n["value"]): n for n in g["nodes"]}
check("2a: one node per (measure, value)", ("deaths", 21.0) in nodes and ("deaths", 31.0) in nodes)
n31 = nodes[("deaths", 31.0)]
check("2b: the node lists its supporting articles, publishers and reporting-event count", n31["article_count"] == 2 and len(n31["publishers"]) == 2 and n31["reporting_events"] >= 1)
check("2c: attribution is kept per type: Reuters 'officials say' is OFFICIAL, the un-sourced headline is PUBLISHER_ASSERTION",
      n31["attribution"].get("OFFICIAL") == [3] and n31["attribution"].get("PUBLISHER_ASSERTION") == [2])
check("2d: the first figure is attributed to police", nodes[("deaths", 21.0)]["attribution"] == {"POLICE": [1]})
txt = " ".join(n["reading"] for n in g["nodes"]).lower()
check("2f: the reading text never claims confirmation or truth", "confirmed" not in txt and "verified" not in txt and "true" not in txt)
multi = [n for n in g["nodes"] if n["reporting_events"] > 1]
check("2g: multiple reporting events is described as 'not confirmation'", all("not confirmation" in n["reading"] for n in multi))
check("2h: an all-unattributed node is flagged", nodes[("deaths", 21.0)]["unattributed_only"] is False)

print("\nTEST 3: attribution taxonomy")
ca = lambda t: si.claim_attribution(t)["type"]
check("3a: police / medics / state media / military / document / official / fire dept",
      ca("Blast kills 5, police say") == "POLICE" and ca("Strike kills 9, medics say") == "HEALTH_AUTHORITY_OR_MEDICS" and ca("21 killed, state media says") == "STATE_MEDIA"
      and ca("4 killed in strike, Pentagon says") == "MILITARY" and ca("A study finds 12 deaths") == "DOCUMENT_OR_STUDY" and ca("Toll hits 40: officials") == "OFFICIAL"
      and ca("Blaze kills 3, Fire Department said") == "EMERGENCY_SERVICES")
check("3b: a trailing source survives a site suffix", ca("Family jumps into river, 3 missing: Police | India News") == "POLICE")
check("3c: a named speaker is kept as such", si.claim_attribution("Afghanistan says three killed in air attacks")["type"] == "NAMED_PARTY")
check("3d: no named source -> PUBLISHER_ASSERTION (the publisher states it), not 'official'", ca("Fuel tanker explosion leaves 11 dead") == "PUBLISHER_ASSERTION")

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
    raise SystemExit(1)
print("ALL story_evolution CHECKS PASSED")
