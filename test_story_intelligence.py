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

print("\nTEST 11: pipeline integration is non-fatal and bounded")
import database as _db
_orig = _db.get_connection
_db.get_connection = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk unplugged"))
try:
    out = si.run_cycle_step()
finally:
    _db.get_connection = _orig
check("11a: run_cycle_step swallows any failure and reports it", isinstance(out, dict) and "disk unplugged" in out.get("error", ""))
import subprocess, sys as _sys
import refresh
check("11b: the step is registered as OPTIONAL (after analyze), so it can never stop a cycle",
      any(s == "story_intelligence.py" for _, s, *_a in refresh.OPTIONAL_AFTER_ANALYZE) and all(s != "story_intelligence.py" for _, s in refresh.STEPS))
r_ = subprocess.run([_sys.executable, "-c", "import refresh; refresh.run_optional('x','nonexistent_script_zzz.py')"], capture_output=True, text=True)
check("11c: an optional step that fails does not raise or exit non-zero", r_.returncode == 0 and "continuing without it" in r_.stdout, r_.stdout + r_.stderr)

print("\nTEST 5b: embedding tiers (restatement / paraphrase / distinct content)")
rs = np.random.RandomState(5)
base = rs.randn(1024).astype("float32")
base /= np.linalg.norm(base)


def near(c):                                   # a vector at cosine c from base
    o = rs.randn(1024).astype("float32")
    o -= o.dot(base) * base
    o /= np.linalg.norm(o)
    return (c * base + (1 - c * c) ** .5 * o).astype("float32")


def two(c, t2):
    return si.analyze_story([art(1, "NDTV", "Lane report on the school board vote", published="2026-09-20T08:00:00", vec=base),
                             art(2, "The Hindu", t2, published="2026-09-20T10:00:00", vec=near(c))], owner_of, NAMES)


r92 = roles(two(0.92, "Board vote at the school explained by Priya Sharma"))[2]
r78 = roles(two(0.78, "Board vote at the school explained by Priya Sharma"))[2]
r73 = roles(two(0.73, "Priya Sharma questions 45 parents after the closing vote"))[2]
r73b = roles(two(0.73, "Discussion continues over the decision by trustees"))[2]
r50 = roles(two(0.50, "Something about 45 unrelated things"))[2]
check("5c: cosine >= 0.80 from another publisher = RESTATES_EARLIER_REPORT (DERIVED, target recorded)", r92["role"] == si.DERIVED and r92["reason"] == "RESTATES_EARLIER_REPORT" and r92["target"] == 1)
check("5d: 0.76-0.80 = POSSIBLE_PARAPHRASE, UNCERTAIN", r78["role"] == si.UNCERTAIN and r78["reason"] == "POSSIBLE_PARAPHRASE")
check("5e: same event + figures no earlier report carried = INDEPENDENT / NEW_SPECIFIC_FIGURES", r73["role"] == si.INDEPENDENT and r73["reason"] == "NEW_SPECIFIC_FIGURES")
check("5f: distinct-looking but adding nothing = UNCERTAIN, not INDEPENDENT", r73b["role"] == si.UNCERTAIN)
check("5i: a loosely related piece (cos < 0.70) is never independent, even with numbers", r50["role"] == si.UNCERTAIN and r50["reason"] == "LOOSELY_RELATED")
r_conf = si.analyze_story([art(1, "NDTV", "Thieves steal four paintings from museum", published="2026-09-20T08:00:00", vec=base),
                           art(2, "The Hindu", "Three paintings stolen from museum", published="2026-09-20T10:00:00", vec=near(0.92))], owner_of, NAMES)
check("5l: a restatement that states different figures is not called a restatement", roles(r_conf)[2]["reason"] != "RESTATES_EARLIER_REPORT")
check("5g: Title Case headlines do not fake 'new names'", not [x for x in si._anchors("Google To Pay Million To Settle App Developer Class Action") if not x[0].isdigit()])
check("5h: 'media reports say' is a secondhand cue (ATTRIBUTED_REPETITION)",
      roles(si.analyze_story([art(1, "NDTV", "Army chief quits", published="2026-09-20T08:00:00"),
                              art(2, "The Hindu", "Army chief submits resignation, media reports say", published="2026-09-20T09:00:00")], owner_of, NAMES))[2]["role"] == si.ATTRIBUTED_REPETITION)
check("5k: numbers keep their value through unit suffixes and formatting", si.numbers_in("Pay 260mn") == si.numbers_in("Pay 260 Million") and "75" in si.numbers_in("75th anniversary") and si.numbers_in("$5K") == si.numbers_in("$5,000"))
check("5j: an outlet's own name is not a 'new fact'", "hindu" not in si.analyze_story([art(1, "NDTV", "Fire in Delhi", published="2026-09-20T08:00:00"), art(2, "The Hindu", "Fire in Delhi says The Hindu BusinessLine 7", published="2026-09-20T09:00:00")], owner_of, NAMES)["articles"][1]["evidence"].get("novel_anchors", []))

print("\nTEST 13: Phase 13 - information delta, tighter developments, same-event figures")
rs13 = np.random.RandomState(13)
b13 = rs13.randn(1024).astype("float32")
b13 /= np.linalg.norm(b13)


def near13(c):
    o = rs13.randn(1024).astype("float32")
    o -= o.dot(b13) * b13
    o /= np.linalg.norm(o)
    return (c * b13 + (1 - c * c) ** .5 * o).astype("float32")


def delta_of(cos2, t2="Something else entirely about it"):
    r = si.analyze_story([art(1, "NDTV", "Fire at chemical plant, rescue on", published="2026-09-20T08:00:00", vec=b13),
                          art(2, "The Hindu", t2, published="2026-09-20T10:00:00", vec=near13(cos2))], owner_of, NAMES)
    return r["articles"][1]["adds"], r["articles"][0]["adds"]


d_hi, first = delta_of(0.90, "Blaze at chemical plant as rescue continues")
d_lo, _ = delta_of(0.55, "Owner of the plant questioned by police over safety lapses")
check("13a: the first article of a story has no 'adds' verdict (basis first_in_story)", first["adds_information"] is None and first["first_in_story"])
check("13b: a restatement (high similarity to an earlier article) does NOT add information", d_hi["adds_information"] is False and d_hi["basis"] == "embedding")
check("13c: distinct content (similarity < ADDS_COS) DOES add information, and the similarity is recorded", d_lo["adds_information"] is True and d_lo["max_similarity_to_earlier"] < si.ADDS_COS)
r_nv = si.analyze_story([art(1, "NDTV", "Fire at chemical plant", published="2026-09-20T08:00:00"),
                         art(2, "The Hindu", "Fire at chemical plant leaves 25 workers injured", published="2026-09-20T10:00:00")], owner_of, NAMES)["articles"][1]["adds"]
check("13d: without vectors it falls back to figures/developments and says so", r_nv["basis"] == "figures_and_developments_no_vectors" and r_nv["adds_information"] is True)
r_own = si.analyze_story([art(1, "NDTV", "Fire at chemical plant, rescue on", published="2026-09-20T08:00:00", vec=b13),
                          art(2, "NDTV", "Owner of the plant questioned by police over safety lapses", published="2026-09-20T10:00:00", vec=near13(0.5))], owner_of, NAMES)["articles"][1]
check("13e: information and independence are different axes: a same-publisher follow-up can add information and still be DERIVED/SAME_OWNER",
      r_own["adds"]["adds_information"] is True and r_own["reason"] == "SAME_OWNER")
cues = lambda t: si.find_dev_cues({"title": t})
check("13f: descriptors and abbreviations are not developments ('convicted war criminal', 'SC-HC traffic', 'Seahawks HC', 'house arrest claim')",
      not cues("Funeral of convicted war criminal Mladic") and not cues("SC-HC traffic plan for summit") and not cues("Seahawks HC gives update") and not cues("Iqra claims house arrest"))
check("13g: real steps still are ('convicted of', 'Supreme Court strikes down', 'arrested', 'moves Supreme Court')",
      "COURT_OR_LEGAL_ORDER" in cues("Man convicted of fraud") and "COURT_OR_LEGAL_ORDER" in cues("Supreme Court strikes down rules") and "ARREST" in cues("Man arrested in Delhi")
      and "COURT_OR_LEGAL_ORDER" in cues("Mamata moves Supreme Court against EC decision"))
check("13h: 'denied access' is not an official denial; roundups and live blogs never trigger", not cues("Journalists were denied access to the White House") and not cues("World in Brief: court rejects postal voting rules")
      and not cues("India News Live Updates: two MLCs arrested"))
check("13i: 'death toll rises to six, 11 rescued' reads 6 deaths, not 11", si.extract_claims({"title": "Delhi building collapse: Death toll rises to six, 11 rescued", "summary": ""})[0]["value"] == 6.0)
fig_hi = si.analyze_story([art(1, "NDTV", "10 killed in fire at chemical plant in Gujarat", published="2026-09-20T08:00:00", fetched="2026-09-20T18:00:00", vec=b13),
                           art(2, "The Hindu", "14 killed in fire at chemical plant in Gujarat", published="2026-09-20T14:00:00", fetched="2026-09-20T18:00:00", vec=near13(0.9))], owner_of, NAMES)
fig_lo = si.analyze_story([art(1, "NDTV", "10 killed in fire at chemical plant in Gujarat", published="2026-09-20T08:00:00", fetched="2026-09-20T18:00:00", vec=b13),
                           art(2, "The Hindu", "14 killed in fire at chemical plant in Gujarat", published="2026-09-20T14:00:00", fetched="2026-09-20T18:00:00", vec=near13(0.4))], owner_of, NAMES)
check("13j: tallies are compared only when the two articles are clearly the same event (cos >= FIGURE_SAME_EVENT_COS)",
      any(x[0] == "UPDATES" for x in fig_hi["relationships"]) and not any(x[0] in ("UPDATES", "CONTRADICTS") for x in fig_lo["relationships"]))
check("13k: the engine version records these rule changes", si.ENGINE_VERSION == "si-3")

print("\nTEST 12: evidence-aware evaluation (fetched article text)")
LEDE_A = ("The chemical plant on the outskirts of the city caught fire early on Monday morning and rescue teams were rushed to the spot "
          "where dozens of workers were reportedly trapped inside the burning building while the district administration sealed the area.")
LEDE_B = ("Officials said the blaze started in a storage unit and spread quickly to neighbouring sheds, and a senior fire officer told reporters "
          "that “we found the second floor completely gutted and the stairwell blocked by melted equipment overnight” during the search.")


def three(evid):
    stories = [art(1, "NDTV", "Fire at chemical plant, rescue on", published="2026-09-20T08:00:00", vec=base),
               art(2, "The Hindu", "Blaze at chemical unit, workers trapped", published="2026-09-20T09:00:00", vec=near(0.78)),
               art(3, "Indian Express", "Chemical plant fire: rescue teams at spot", published="2026-09-20T10:00:00", vec=near(0.78))]
    return si.analyze_story(stories, owner_of, NAMES, evidence=evid)


plain = three(None)
check("12a: evidence=None and evidence={} give exactly the metadata-only verdicts",
      [(a["role"], a["reason"], a["confidence"]) for a in plain["articles"]] == [(a["role"], a["reason"], a["confidence"]) for a in three({})["articles"]]
      and all(a["evidence_source"] == "METADATA" for a in plain["articles"]))
r_ = roles(three({1: LEDE_A, 2: LEDE_A}))
check("12b: verbatim shared passages with an earlier fetched article = DERIVED / FETCHED_SHARED_TEXT, provenance FETCHED_ARTICLE",
      r_[2]["role"] == si.DERIVED and r_[2]["reason"] == "FETCHED_SHARED_TEXT" and r_[2]["target"] == 1 and r_[2]["evidence_source"] == "FETCHED_ARTICLE")
check("12c: the metadata verdict is kept beside the new one", r_[2]["metadata_role"] == plain["articles"][1]["role"] and "metadata_verdict" in r_[2]["evidence"])
r_ = roles(three({3: "NEW DELHI (PTI) " + LEDE_A}))
check("12d: a dateline in the fetched text = ATTRIBUTED_REPETITION / FETCHED_ATTRIBUTION with the external origin", r_[3]["role"] == si.ATTRIBUTED_REPETITION and r_[3]["reason"] == "FETCHED_ATTRIBUTION" and r_[3]["external"] == "PTI")
si.ALLOW_EVIDENCE_INDEPENDENCE = True
r_ = roles(three({1: LEDE_A, 2: LEDE_B}))
si.ALLOW_EVIDENCE_INDEPENDENCE = False
check("12e: two fetched texts with no shared passage and text of its own (a long quote) may PROMOTE an UNCERTAIN article", r_[2]["role"] == si.INDEPENDENT
      and r_[2]["reason"] == "FETCHED_DISTINCT_REPORTING" and r_[2]["confidence"] <= 0.5 and r_[2]["metadata_role"] == si.UNCERTAIN)
r_ = roles(three({2: LEDE_B}))
check("12f: ...but never with only ONE fetched text (nothing to compare with)", r_[2]["role"] == plain["articles"][1]["role"] and r_[2]["evidence_source"] == "METADATA")
r_ = roles(three({1: LEDE_A, 2: LEDE_A.replace("dozens", "several")}))
check("12g: a near-copy still counts as shared text (>= a 12-word verbatim run), not as independent", r_[2]["role"] == si.DERIVED)
r_ = roles(three({1: LEDE_A, 2: LEDE_B}))
check("12h: promotion to INDEPENDENT is OFF by default (the canary showed false independence) and only the flag changes that", si.ALLOW_EVIDENCE_INDEPENDENCE is False and r_[2]["role"] == plain["articles"][1]["role"])
PHOTO = "A student searches for her school bag at the school in Nepal. (AP: Niranjan Shrestha) A teacher saved about 1,600 students in Nepal at a school that has now been completely swept away by the flood waters that came down the valley."
check("12p: a photo credit '(AP: Name)' / '(AP Photo)' is NOT attribution of the article", not si.find_attribution_fetched(PHOTO, "ABC Australia", NAMES)
      and not si.find_attribution_fetched("FILE - Designer poses. (AP Photo/Thibault Camus) The eight-month exhibition was scheduled to open in May.", "CNA", NAMES))
check("12q: a dateline / explicit citation IS attribution", si.find_attribution_fetched("New Delhi, Aug 31 (PTI) Stocks fell on Monday.", "Pioneer", NAMES)[0]["name"] == "PTI"
      and si.find_attribution_fetched("The minister resigned, according to Reuters, after a long row.", "X", NAMES)[0]["name"] == "Reuters")
STMT = "“After much reflection and discussion with all those involved in this exhibition we have decided together to cancel the project and I am deeply sorry”"
r_ = roles(three({1: "The designer announced on Monday that " + STMT + " ending months of debate about the show in the city.",
                  2: "Officials confirmed the decision late on Monday evening, adding that " + STMT + " and that the museum would issue its own statement soon."}))
check("12r: two outlets quoting the same statement are NOT derived from each other (quoted spans are ignored)", r_[2]["reason"] != "FETCHED_SHARED_TEXT")
r_ = roles(si.analyze_story([art(1, "Times of India", "Fire at plant", published="2026-09-20T08:00:00"), art(2, "Navbharat Times", "Fire at plant again", published="2026-09-20T09:00:00")],
                            owner_of, NAMES, evidence={1: LEDE_A, 2: LEDE_B}))
check("12i: SAME_OWNER stays voice accounting whatever the text says", r_[2]["reason"] == "SAME_OWNER" and r_[2]["evidence_source"] == "METADATA")
check("12j: the evidence hash changes the story signature (evidence arriving re-queues the story) and is stable",
      si.input_signature(story, {1: LEDE_A}) != si.input_signature(story) and si.input_signature(story, {1: LEDE_A}) == si.input_signature(story, {1: LEDE_A})
      and si.input_signature(story, {1: LEDE_A}) != si.input_signature(story, {1: LEDE_B}))
ctx = {"distinct_owners": 4, "earliest_id": 1}
A = lambda role, reason, i=2: {"id": i, "role": role, "reason": reason}
check("12k: needs_evidence: UNCERTAIN paraphrase / no-positive-evidence -> FETCH", si.needs_evidence(A("UNCERTAIN", "POSSIBLE_PARAPHRASE"), ctx)[0] == "FETCH" and si.needs_evidence(A("UNCERTAIN", "NO_POSITIVE_EVIDENCE"), ctx)[0] == "FETCH")
check("12l: needs_evidence: a potential independent report and the earliest article -> FETCH", si.needs_evidence(A("INDEPENDENT", "NEW_SPECIFIC_FIGURES"), ctx)[0] == "FETCH" and si.needs_evidence(A("INDEPENDENT", "EARLIEST_IN_CORPUS", 1), ctx)[0] == "FETCH")
check("12m: needs_evidence: already resolved / owner accounting / loose / cross-language -> NO_FETCH with a reason",
      all(si.needs_evidence(A(r, why), ctx)[0] == "NO_FETCH" and si.needs_evidence(A(r, why), ctx)[1] for r, why in
          [("DERIVED", "RESTATES_EARLIER_REPORT"), ("DERIVED", "SAME_OWNER"), ("ATTRIBUTED_REPETITION", "WIRE_ATTRIBUTION"), ("UNCERTAIN", "LOOSELY_RELATED"), ("UNCERTAIN", "CROSS_LANGUAGE_NO_TEXTUAL_BASIS")]))
check("12n: needs_evidence: a story with too few publishers is not worth the fetch; a different publisher alone is never a trigger",
      si.needs_evidence(A("UNCERTAIN", "NO_POSITIVE_EVIDENCE"), {"distinct_owners": 2, "earliest_id": 1}) == ("NO_FETCH", "too_few_publishers_to_matter")
      and si.needs_evidence(A("INDEPENDENT", "SOMETHING_ELSE"), ctx)[0] == "NO_FETCH")
plan, dec = si.plan_evidence(three(None), {})
check("12o: plan_evidence lists triggered articles (and their comparison partner) and logs every decision by reason", isinstance(plan, list) and sum(dec.values()) == 3
      and all(k.split(":")[0] in ("FETCH", "NO_FETCH") for k in dec))

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
    raise SystemExit(1)
print("ALL story_intelligence CHECKS PASSED")
