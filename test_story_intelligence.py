"""
test_story_intelligence.py - deterministic tests for story_intelligence.py (independence, developments, chronology,
claims, persistence idempotency) and story_graph.py (the ten programmatic questions).

Uses synthetic stories in a temp SQLite file; never touches paksh.db or the embedding model. Run:  py test_story_intelligence.py
"""
import sqlite3
import tempfile
from pathlib import Path

import numpy as np

import story_intelligence as si

FAILURES = []


def check(label, cond, extra=""):
    print(f"  {label} ... {'OK' if cond else 'FAIL'} {extra if not cond else ''}")
    if not cond:
        FAILURES.append(label)


def art(i, source, title, summary="", published="", fetched="2026-09-20T12:00:00", lang="en", vec=None):
    return {"id": i, "source": source, "language": lang, "title": title, "summary": summary, "published": published,
            "fetched_at": fetched, "vec": vec}


OWN = {"Times of India": "Times Group", "Navbharat Times": "Times Group"}
owner_of = lambda n: OWN.get(n, n)
NAMES = ["The Hindu", "Times of India", "NDTV", "Reuters", "Hindustan Times", "Indian Express"]


def roles(res):
    return {a["id"]: a for a in res["articles"]}


print("TEST 1: time parsing keeps claims and never invents precision")
check("1a: ISO with time", si.parse_time("2026-09-20T16:23:23") == (si.datetime(2026, 9, 20, 16, 23, 23), "time"))
check("1b: compact date only", si.parse_time("20260920") == (si.datetime(2026, 9, 20), "date"))
check("1c: timezone converted to UTC", si.parse_time("2026-09-20T10:00:00+05:30")[0] == si.datetime(2026, 9, 20, 4, 30))
check("1d: garbage -> (None, None)", si.parse_time("last tuesday-ish") == (None, None))
t, basis = si.order_time("2026-09-21T09:00:00", "2026-09-20T12:00:00")
check("1e: a publish time in the future of the fetch is not believed", basis == "fetched" and t == si.datetime(2026, 9, 20, 12, 0))
t, basis = si.order_time("2026-09-20T08:00:00", "2026-09-20T12:00:00")
check("1f: a sane publish time is used", basis == "published")

print("\nTEST 2: same owner is one voice; a different publisher alone proves nothing")
res = si.analyze_story([
    art(1, "NDTV", "Bridge collapses in Patna, rescue on", published="2026-09-20T08:00:00"),
    art(2, "Times of India", "Patna bridge collapse: rescue operation underway", published="2026-09-20T09:00:00"),
    art(3, "Navbharat Times", "पटना में पुल गिरा", published="2026-09-20T09:30:00", lang="hi"),
], owner_of, NAMES)
r = roles(res)
check("2a: earliest article is INDEPENDENT (earliest in corpus)", r[1]["role"] == si.INDEPENDENT and r[1]["reason"] == "EARLIEST_IN_CORPUS")
check("2b: same owner (Times) later article is DERIVED / SAME_OWNER", r[3]["role"] == si.DERIVED and r[3]["reason"] == "SAME_OWNER" and r[3]["target"] == 2)
check("2c: a distinct publisher with no new facts is UNCERTAIN, not INDEPENDENT", r[2]["role"] == si.UNCERTAIN, str(r[2]))
check("2d: article 1's reporting event exists and roots at the earliest", res["reporting_events"][0]["root_article_id"] == 1)

print("\nTEST 3: attribution")
res = si.analyze_story([
    art(1, "NDTV", "Minister resigns over scam, says party", published="2026-09-20T08:00:00"),
    art(2, "Hindustan Times", "Minister resigns over scam (PTI)", published="2026-09-20T09:00:00"),
    art(3, "Indian Express", "Minister quits, according to NDTV", published="2026-09-20T09:05:00"),
    art(4, "The Hindu", "Minister resigns - PTI", published="2026-09-20T10:00:00"),
], owner_of, NAMES)
r = roles(res)
check("3a: '(PTI)' tag -> ATTRIBUTED_REPETITION to external PTI", r[2]["role"] == si.ATTRIBUTED_REPETITION and r[2]["external"] == "PTI")
check("3b: 'according to NDTV' -> ATTRIBUTED_REPETITION pointing at the NDTV article", r[3]["role"] == si.ATTRIBUTED_REPETITION and r[3]["target"] == 1)
check("3c: the two PTI-tagged reports share ONE reporting event", r[2]["reporting_event_root"] == r[4]["reporting_event_root"])
check("3d: an article never attributes to its own outlet", not si.find_attribution(art(9, "NDTV", "x, reports NDTV"), NAMES))

print("\nTEST 4: near-duplicate text is DERIVED; embeddings drive cross-language / same-language copies")
v = np.random.RandomState(1).randn(1024).astype("float32")
v2 = v + np.random.RandomState(2).randn(1024).astype("float32") * 0.01
res = si.analyze_story([
    art(1, "NDTV", "Owaisi open to alliance with like-minded parties in UP", published="2026-09-20T08:00:00", vec=v),
    art(2, "Hindustan Times", "Owaisi open to alliance with like minded parties in UP", published="2026-09-20T09:00:00", vec=v2),
], owner_of, NAMES)
check("4a: near-identical headline from another owner is DERIVED", roles(res)[2]["role"] == si.DERIVED and roles(res)[2]["reason"] == "NEAR_DUPLICATE_TEXT")
check("4b: ... and grouped into the same reporting event", len(res["reporting_events"]) == 1)
res = si.analyze_story([
    art(1, "NDTV", "Owaisi open to alliance in UP", published="2026-09-20T08:00:00", vec=v),
    art(2, "Jansatta", "ओवैसी ने गठबंधन का दिया न्योता", published="2026-09-20T09:00:00", lang="hi", vec=np.random.RandomState(9).randn(1024).astype("float32")),
], owner_of, NAMES)
check("4c: first Hindi article with no textual basis is UNCERTAIN (never guessed INDEPENDENT)", roles(res)[2]["role"] == si.UNCERTAIN)

print("\nTEST 5: independence needs positive evidence (new facts)")
res = si.analyze_story([
    art(1, "NDTV", "Fire at Delhi factory, rescue on", published="2026-09-20T08:00:00"),
    art(2, "The Hindu", "Fire at Delhi factory: 12 workers trapped, owner Rajesh Gupta questioned", published="2026-09-20T10:00:00"),
], owner_of, NAMES)
check("5a: without vectors, a report adding several new facts is INDEPENDENT (text-only, low confidence)",
      roles(res)[2]["role"] == si.INDEPENDENT and roles(res)[2]["reason"] == "ADDS_NEW_FACTS_TEXT_ONLY" and roles(res)[2]["confidence"] <= 0.4)
check("5b: corroboration edge is worded as independent reporting, not truth",
      any(x[0] == "INDEPENDENT_CORROBORATION" and "does not establish" in str(x[6]) for x in res["relationships"]))

print("\nTEST 6: developments need a typed cue that no earlier article carried")
res = si.analyze_story([
    art(1, "NDTV", "Explosion at chemical plant, rescue under way", published="2026-09-20T08:00:00"),
    art(2, "The Hindu", "Explosion at chemical plant: more coverage and reactions", published="2026-09-20T09:00:00"),
    art(3, "Indian Express", "Plant owner arrested after chemical plant blast", published="2026-09-20T11:00:00"),
    art(4, "Hindustan Times", "Owner of chemical plant arrested; FIR registered", published="2026-09-20T12:00:00"),
], owner_of, NAMES)
types = {d["type"]: d for d in res["developments"]}
check("6a: 'arrested' is a development (ARREST) triggered by the first article carrying it", "ARREST" in types and types["ARREST"]["trigger_article_id"] == 3)
check("6b: corroboration by a second owner raises confidence", types["ARREST"]["corroborating_owners"] == 2 and types["ARREST"]["confidence"] > 0.45)
check("6c: 'more coverage' is NOT a development", not any("coverage" in d["description"] and d["type"] not in ("ARREST", "INVESTIGATION_LAUNCHED") for d in res["developments"]))
check("6d: the initial event itself (explosion/rescue) is not a development", all(d["trigger_article_id"] != 1 for d in res["developments"]))
res0 = si.analyze_story([
    art(1, "NDTV", "Man arrested for theft", published="2026-09-20T08:00:00"),
    art(2, "The Hindu", "Theft accused arrested by police", published="2026-09-20T09:00:00"),
], owner_of, NAMES)
check("6e: a cue already present when the story began is baseline, not a change", not any(d["type"] == "ARREST" for d in res0["developments"]))
check("6f: event_time is never inferred (NULL) and the three other timestamps stay separate",
      all(d["event_time"] is None and d["published_at"] and d["first_seen_at"] for d in res["developments"]))

def devtypes(titles):
    arts_ = [art(i + 1, f"Outlet{i}", ti, published=f"2026-09-20T{8 + i:02d}:00:00") for i, ti in enumerate(titles)]
    return {d["type"] for d in si.analyze_story(arts_, owner_of, NAMES)["developments"]}
check("6h: opinion / hypothetical / question headlines never trigger", devtypes(["Fire at plant", "Opinion | Owner must be arrested", "Could owner be arrested?", "Calls for ban on plant"]) == set())
check("6i: 'held' already reported means a later 'arrested' is not a new development", "ARREST" not in devtypes(["Blast at plant", "Accused held in plant blast", "Owner arrested over plant blast"]))
check("6j: 'SC' and 'Supreme Court' are the same cue", "COURT_OR_LEGAL_ORDER" not in devtypes(["SC grants panel more time", "Supreme Court refuses extension for panel"]))
check("6k: \"won't\" is not a result", not devtypes(["Party meets", "Leader says party won't give up fight"]))
check("6l: 'banning' counts as the ban that a later 'bans' repeats", "POLICY_OR_FORMAL_DECISION" not in devtypes(["Trump says he is banning outlets", "Trump bans major outlets from White House"]))
si.register_development_type("TEST_TYPE", [r"\bzzzcue\b"])
res = si.analyze_story([art(1, "NDTV", "A story", published="2026-09-20T08:00:00"), art(2, "The Hindu", "A story zzzcue", published="2026-09-20T09:00:00")], owner_of, NAMES)
check("6g: the taxonomy is extensible", any(d["type"] == "TEST_TYPE" for d in res["developments"]))
del si.DEVELOPMENT_TYPES["TEST_TYPE"]

print("\nTEST 7: claims - updates vs contradictions")
res = si.analyze_story([
    art(1, "NDTV", "12 killed as bus falls into gorge in Uttarakhand", published="2026-09-20T08:00:00", fetched="2026-09-20T18:00:00"),
    art(2, "The Hindu", "18 killed as bus falls into gorge in Uttarakhand", published="2026-09-20T14:00:00", fetched="2026-09-20T18:00:00"),
], owner_of, NAMES)
kinds = [x[0] for x in res["relationships"]]
check("7a: a rising toll with clear order is an UPDATE + FIGURE_UPDATE development", "UPDATES" in kinds and any(d["type"] == "FIGURE_UPDATE" for d in res["developments"]))
res = si.analyze_story([
    art(1, "NDTV", "12 killed as bus falls into gorge in Uttarakhand", published="20260920", fetched="2026-09-20T12:00:00"),
    art(2, "The Hindu", "18 killed as bus falls into gorge in Uttarakhand", published="20260920", fetched="2026-09-20T12:30:00"),
], owner_of, NAMES)
check("7b: differing tolls with ambiguous order are CONTRADICTS (lower confidence), not 'wrong'",
      any(x[0] == "CONTRADICTS" and x[5] <= 0.45 for x in res["relationships"]))
check("7c: number words and Hindi are parsed", si.extract_claims(art(1, "x", "Five killed in blast"))[0]["value"] == 5.0
      and si.extract_claims(art(1, "x", "हादसे में 7 लोगों की मौत"))[0]["value"] == 7.0)
check("7d: percent / money figures are stored as claims but never compared (no invented contradictions)",
      not any(x[0] in ("CONTRADICTS", "UPDATES") for x in si.analyze_story([
          art(1, "NDTV", "Turnout at 60% in phase one of polling", published="2026-09-20T08:00:00", fetched="2026-09-20T18:00:00"),
          art(2, "The Hindu", "Turnout at 55% in phase one of polling", published="2026-09-20T14:00:00", fetched="2026-09-20T18:00:00")], owner_of, NAMES)["relationships"]))
res = si.analyze_story([
    art(1, "NDTV", "3 killed including gunman in shooting at mall", published="2026-09-20T08:00:00", fetched="2026-09-20T18:00:00"),
    art(2, "The Hindu", "2 killed in shooting at mall, suspect dead", published="2026-09-20T08:30:00", fetched="2026-09-20T18:00:00"),
    art(3, "Indian Express", "2 killed in shooting at mall, suspect also dead", published="2026-09-20T09:00:00", fetched="2026-09-20T18:00:00"),
    art(4, "Hindustan Times", "2 killed as gunman opens fire at mall", published="2026-09-20T09:30:00", fetched="2026-09-20T18:00:00")], owner_of, NAMES)
_c = [x for x in res["relationships"] if x[0] == "CONTRADICTS"]
check("7e: one discrepancy = one edge (not one per article pair)", len(_c) == 1, str([x[0] for x in res["relationships"]]))
check("7f: the edge records the supporting articles and says it does not decide which figure is right",
      len(_c) == 1 and _c[0][6]["later"]["article_ids"] == [2, 3, 4] and "does not say which" in _c[0][6]["note"])

print("\nTEST 8: chronology ordering is stable and skew-safe")
res = si.analyze_story([
    art(1, "NDTV", "Event A", published="2026-09-25T08:00:00", fetched="2026-09-20T09:00:00"),      # publish claim from the future
    art(2, "The Hindu", "Event A again", published="2026-09-20T10:00:00", fetched="2026-09-20T10:05:00"),
], owner_of, NAMES)
a = roles(res)
check("8a: the skewed article is ordered by its fetch time and the basis says so", a[1]["order_basis"] == "fetched" and res["articles"][0]["id"] == 1)
check("8b: the raw publish claim is preserved untouched", a[1]["published"] == "2026-09-25T08:00:00")
r1 = si.analyze_story([art(2, "B", "x y z", published="2026-09-20T10:00:00"), art(1, "A", "x y z w", published="2026-09-20T10:00:00")], owner_of, NAMES)
r2 = si.analyze_story([art(1, "A", "x y z w", published="2026-09-20T10:00:00"), art(2, "B", "x y z", published="2026-09-20T10:00:00")], owner_of, NAMES)
check("8c: result does not depend on input order (deterministic)", r1 == r2)

print("\nTEST 9: persistence - idempotent, versioned, detected_at never rewritten, bounded")
tmp = Path(tempfile.mkdtemp(prefix="si_test_")) / "t.db"
conn = sqlite3.connect(tmp)
conn.row_factory = sqlite3.Row
si.init_si_schema(conn)
si.init_si_schema(conn)      # idempotent
story = [art(1, "NDTV", "Fire at plant, rescue on", published="2026-09-20T08:00:00"),
         art(2, "The Hindu", "Fire at plant: owner Rajesh Gupta arrested, 4 killed", published="2026-09-20T10:00:00")]
res = si.analyze_story(story, owner_of, NAMES)
sig = si.input_signature(story)
si.persist_story(conn, 7, res, sig, now="2026-09-20T12:00:00")
first = {t: conn.execute(f"SELECT COUNT(*) FROM {t} WHERE event_id=7").fetchone()[0] for t in si.SI_TABLES}
det1 = conn.execute("SELECT detected_at FROM si_reporting_events WHERE event_id=7").fetchone()[0]
si.persist_story(conn, 7, res, sig, now="2026-09-21T12:00:00")
second = {t: conn.execute(f"SELECT COUNT(*) FROM {t} WHERE event_id=7").fetchone()[0] for t in si.SI_TABLES}
det2 = conn.execute("SELECT detected_at, updated_at FROM si_reporting_events WHERE event_id=7").fetchone()
check("9a: re-running writes no duplicates", first == second, f"{first} vs {second}")
check("9b: detected_at is preserved, updated_at moves", det1 == det2[0] == "2026-09-20T12:00:00" and det2[1] == "2026-09-21T12:00:00")
check("9c: the input signature is stable for the same story and changes when membership changes",
      sig == si.input_signature(list(reversed(story))) and sig != si.input_signature(story[:1]))
res3 = si.analyze_story(story[:1] + [art(3, "Reuters", "Fire at plant (PTI)", published="2026-09-20T11:00:00")], owner_of, NAMES)
si.persist_story(conn, 7, res3, "sig2", now="2026-09-22T12:00:00")
check("9d: an article that left the story has its rows removed", conn.execute("SELECT COUNT(*) FROM si_reporting_event_articles WHERE event_id=7 AND article_id=2").fetchone()[0] == 0)
check("9e: rows for a surviving article keep their original detected_at",
      conn.execute("SELECT detected_at FROM si_reporting_event_articles WHERE event_id=7 AND article_id=1").fetchone()[0] == "2026-09-20T12:00:00")
big = [art(i, f"Outlet{i}", f"story about topic number {i} alpha beta", published=f"2026-09-20T{(i % 23):02d}:00:00") for i in range(1, 300)]
check("9f: work per story is bounded (MAX_ARTICLES)", len(si.analyze_story(big, owner_of, NAMES)["articles"]) == si.MAX_ARTICLES)

print("\nTEST 10: the graph read API answers the ten questions")
import story_graph as sg
conn.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, title TEXT, analysis_json TEXT, is_demo INTEGER DEFAULT 0)")
import story_memory
story_memory.init_story_memory_schema(conn)
conn.execute("CREATE TABLE IF NOT EXISTS articles (id INTEGER PRIMARY KEY, event_id INTEGER, source TEXT, title TEXT)")
conn.execute("DELETE FROM articles")
for _i, _s in ((1, "NDTV"), (2, "The Hindu"), (3, "Hindustan Times")):
    conn.execute("INSERT INTO articles VALUES (?,?,?,?)", (_i, 7, _s, "t%d" % _i))
conn.execute("INSERT OR REPLACE INTO events (id, title) VALUES (7, 'Fire at plant')")
conn.commit()
si.persist_story(conn, 7, si.analyze_story([art(1, "NDTV", "12 killed as bus falls into gorge", published="2026-09-20T08:00:00", fetched="2026-09-20T18:00:00"),
                                             art(2, "The Hindu", "18 killed as bus falls into gorge, driver arrested", published="2026-09-20T14:00:00", fetched="2026-09-20T18:00:00"),
                                             art(3, "Hindustan Times", "18 killed as bus falls into gorge (PTI)", published="2026-09-20T15:00:00", fetched="2026-09-20T18:00:00")], owner_of, NAMES),
                 "s", now="2026-09-20T16:00:00")
g = sg.StoryGraph(conn, 7)
check("Q1 independent reports", isinstance(g.independent_reports(), list))
check("Q2 derived/repeated reports", isinstance(g.derived_reports(), list) and any(x["article_id"] == 3 for x in g.derived_reports()))
check("Q3 what an article derives from", g.derives_from(3)["external"] == "PTI")
check("Q4 earliest report", g.earliest_report()["article_id"] == 1)
check("Q5 developments", any(d["type"] == "ARREST" for d in g.developments()))
check("Q6 figure disagreements/updates", any(x["rel_type"] == "UPDATES" for x in g.figure_changes()))
check("Q7 single-source vs corroborated developments", set(g.development_corroboration()) >= {"single_source", "corroborated"})
check("Q8 related stories via event_relationships", g.related_stories() == [])
tl = g.timeline()
check("Q9 timeline keeps the timestamps distinct", tl and all({"published_at", "first_seen_at", "detected_at"} <= set(x) for x in tl))
prov = g.provenance(3)
check("Q10 provenance path article -> outlet -> reporting event -> origin", prov["source"] == "Hindustan Times" and prov["origin_external"] == "PTI")
check("summary counts independent origins separately from articles", g.summary()["articles"] == 3 and g.summary()["independent_origins"] >= 1)
conn.close()

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
    raise SystemExit(1)
print("ALL story_intelligence CHECKS PASSED")
