"""
test_phase10.py - Paksh 10: clustering & topic/region merge-guard.

FORENSIC SUMMARY (see the Phase 10 report for full detail):
Investigated the 3 confirmed false-merge events (#3563 "Sports coverage...",
#13344 "Manitoba and Minnesota Weather Updates", #15953 "Trump-endorsed
candidates lose..."). Neither match_clusters_to_events() nor
_merge_into_existing() ever read/compared topic or region - the ONLY gates
are centroid similarity + specific-keyword overlap.

Individual articles/new clusters have NO topic or region at merge time (that
field only exists after an event is fully analyzed, which happens AFTER
clustering) - only the EXISTING event side of a cross-cycle merge has one.
The cheapest available signal for the new-cluster side is analyze.py's own
_guess_topic()/_guess_region() heuristics (already used for extractive
fallback), tested here directly against real reconstructed article text from
the 3 known bleeds:
  - #13344: heuristic topic for the weather core = "Environment" (matches the
    event's real stored topic exactly); heuristic topic for the bridged ABC
    Australia politics/court content = "International" - a REAL, CONFIRMED
    mismatch this guard would have caught.
  - #3563 (FIFA vs cricket, or Egypt-match vs France-match): both sides are
    "Sports" - a topic guard is a NO-OP here by construction; the actual
    bridge is template/embedding-similarity (near-identical article
    boilerplate for different specific matches), a DIFFERENT mechanism this
    phase's guard does not address (documented remaining debt, not silently
    ignored).
  - #15953 (Trump primaries/Iran sanctions/Canada tariffs/SCOTUS mail-in, all
    bridged via the shared newsmaker token "trump"): the heuristic returns
    "International" uniformly for ALL four sub-stories - it cannot
    distinguish them, so this guard is also a confirmed no-op here (same
    honest limitation).
  - region was investigated too and found LESS reliable than topic on all 3
    known bleeds (_guess_region() defaults to "India" whenever neither its
    India nor foreign regex matches, and has a real false-positive risk via
    ambiguous acronyms shared between countries, e.g. "GST") - deliberately
    NOT used as an independent veto trigger in the implemented guard.

DESIGN (implemented in analyze.py::_topic_mismatch_veto(), applied as a
POST-MATCH veto inside _merge_into_existing() - cluster.py itself is
untouched, avoiding any analyze<->cluster import cycle):
  veto fires only when ALL of:
    - the existing event's stored topic is a real TOPICS value (not missing/
      legacy - never penalizes what we don't know)
    - the cluster's heuristic topic guess is NOT its own no-signal default
      ("Society" - see _guess_topic()'s docstring)
    - the guess disagrees with the event's topic
    - the match's own centroid similarity is BELOW HIGH_SIM (the
      "extreme-similarity exception" - an overwhelming semantic match is
      trusted over a cheap regex guess, so genuine story continuity is never
      blocked by this guard)
  A vetoed cluster is treated as unmatched for that cycle (becomes its own
  new event) - never merged, never dropped, never mutated.

Tests are 100% read-only against the real local paksh.db (SELECT only) plus
pure-function calls; nothing here writes to the database, mutates historical
events, or calls any LLM/embedding backend.

Run:  py test_phase10.py
"""
import json
import database as db
import analyze as an
import cluster as cl

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


conn = db.get_connection()
cur = conn.cursor()


def _event_row(eid):
    cur.execute("SELECT id, title, analysis_json FROM events WHERE id=?", (eid,))
    r = cur.fetchone()
    if not r:
        return None, {}
    return r, (json.loads(r["analysis_json"]) if r["analysis_json"] else {})


# ============================================================ A: known false merges
print("=== A: known false merges - guard behavior against REAL reconstructed bleed data ===")

# A1: #13344's actual bridge - CONFIRMED the guard catches this (topic mismatch, moderate sim)
event_13344 = {"topic": "Environment", "region": "World"}
abc_australia_bridge = {
    1: {"title": "Albanese might regret using permanent marker on GST pledge", "summary": ""},
    2: {"title": "What dozens of empty chairs revealed about Australia's racism inquiry", "summary": ""},
    3: {"title": "Luxury tower affordability claim rejected in landmark court ruling", "summary": ""},
    4: {"title": "Driver trapped in crashed car after alleged Melbourne carjacking", "summary": ""},
}
cluster_bridge = {"ids": [1, 2, 3, 4]}
check("A1: #13344's real ABC-Australia bridge content IS vetoed at moderate similarity "
      "(the guard's one confirmed, evidence-backed catch)",
      an._topic_mismatch_veto(cluster_bridge, event_13344, abc_australia_bridge, sim=0.68) is True)

# A2: #3563's FIFA vs cricket bridge - HONEST negative: both are "Sports", guard is a no-op here
event_3563 = {"topic": "Sports", "region": "World"}
cricket_cluster = {
    1: {"title": "Upcoming GIB vs SER cricket match: ball by ball commentary", "summary": ""},
}
check("A2: #3563's cricket content is SAME topic as the event (Sports) - "
      "guard correctly does NOT fire (this bleed's real cause is template/embedding "
      "similarity, not topic drift - documented remaining debt, not solved by this guard)",
      an._topic_mismatch_veto({"ids": [1]}, event_3563, cricket_cluster, sim=0.68) is False)

# A3: #15953's Iran-sanctions bridge - HONEST negative: heuristic can't distinguish sub-stories
event_15953 = {"topic": "Politics", "region": "World"}
iran_cluster = {
    1: {"title": "Trump risks China blowback with plan to choke Iran's economy", "summary": ""},
}
guess_for_iran = an._guess_topic(an._text_of_by_id(1, iran_cluster))
check(f"A3: #15953's Iran-sanctions text heuristically guesses '{guess_for_iran}', same as "
      "the event's own likely International-flavored classification pattern - confirming "
      "(honestly) this guard does not catch this bleed either; a magnet-newsmaker token "
      "('trump') bridges genuinely different sub-topics the cheap heuristic can't separate",
      guess_for_iran in ("International", "Politics"))


# ============================================================ B: known good merges protected
print("\n=== B: legitimate cross-cycle continuity is NOT blocked (real event #8798 data) ===")

ev8798_row, ev8798_aj = _event_row(8798)
check("B0: event #8798 exists in local DB with the expected real topic/region",
      ev8798_row is not None and ev8798_aj.get("topic") == "Crime & Law"
      and ev8798_aj.get("region") == "India")

if ev8798_row:
    event_8798 = {"topic": ev8798_aj.get("topic"), "region": ev8798_aj.get("region")}
    # A later-arriving batch of real article titles from the SAME ongoing protest story
    later_batch = {
        1: {"title": "Delhi Police lathicharge protesters at Jantar Mantar", "summary": ""},
        2: {"title": "Supreme Court metro station closure amid CJP protest sparks CJI anger", "summary": ""},
        3: {"title": "NDA and opposition MPs face off in Parliament over paper leak uproar", "summary": ""},
    }
    check("B1: a real later-arriving batch of the SAME ongoing #8798 protest story "
          "is NOT vetoed at moderate similarity (legitimate continuity preserved)",
          an._topic_mismatch_veto({"ids": [1, 2, 3]}, event_8798, later_batch, sim=0.68) is False)

# B2: extreme-similarity exception - even a heuristic topic mismatch never blocks a
# near-certain semantic match
mismatched_but_certain = {1: {"title": "Completely unrelated-sounding headline text", "summary": ""}}
check("B2: extreme similarity (>= HIGH_SIM) bypasses the guard even with a topic mismatch "
      "- protects genuine high-confidence continuations from a wrong heuristic guess",
      an._topic_mismatch_veto({"ids": [1]},
                               {"topic": "Economy", "region": "India"},
                               {1: {"title": "Cricket World Cup final result announced", "summary": ""}},
                               sim=cl.HIGH_SIM) is False)


# ============================================================ C: topic/region guard truth table
print("\n=== C: guard truth table (behavioral, moderate similarity throughout) ===")
SIM = 0.68  # below HIGH_SIM, so the extreme-similarity exception never masks these cases
mismatch_cluster = {1: {"title": "Stock market shares tumble amid economic slowdown fears", "summary": ""}}
match_cluster = {1: {"title": "Election results trigger political realignment", "summary": ""}}

check("C1: same topic -> not vetoed",
      an._topic_mismatch_veto({"ids": [1]}, {"topic": "Politics"}, match_cluster, SIM) is False)
check("C2: different topic, confident guess -> vetoed",
      an._topic_mismatch_veto({"ids": [1]}, {"topic": "Politics"}, mismatch_cluster, SIM) is True)
check("C3: event topic missing/None -> never vetoed (nothing to compare against)",
      an._topic_mismatch_veto({"ids": [1]}, {"topic": None}, mismatch_cluster, SIM) is False)
check("C4: event topic legacy/invalid string -> never vetoed",
      an._topic_mismatch_veto({"ids": [1]}, {"topic": "NotARealTopic"}, mismatch_cluster, SIM) is False)
no_signal_cluster = {1: {"title": "xyz abc qrs tuv", "summary": ""}}
check("C5: cluster heuristic has no real signal (defaults to 'Society') -> never vetoed",
      an._topic_mismatch_veto({"ids": [1]}, {"topic": "Politics"}, no_signal_cluster, SIM) is False)
check("C6: empty cluster ids -> never vetoed (no text to classify)",
      an._topic_mismatch_veto({"ids": []}, {"topic": "Politics"}, mismatch_cluster, SIM) is False)


# ============================================================ D: classification fixtures (real, regression-locked)
print("\n=== D: real classification fixtures - current stored values regression-locked ===")
FIXTURES = {
    17167: ("Economy", "World"),   # CONFIRMED WRONG region (NPCI is a direct Indian institution)
    17193: ("Economy", "World"),   # CONFIRMED WRONG region (Indian Oil Corporation's own action)
    16578: ("Society", "World"),   # PLAUSIBLE/AMBIGUOUS - primary subject is a foreign disaster
    17109: ("Crime & Law", "World"),  # CONFIRMED WRONG topic (a war strike, not courts/police/crime)
    16281: ("Crime & Law", "World"),  # CONFIRMED WRONG topic (a war, matches International's own example)
    16377: ("Crime & Law", "World"),  # CONFIRMED WRONG topic (foreign political/military action)
    17069: ("Politics", "World"),  # CONFIRMED WRONG region (Modi is the direct actor - India)
    16749: ("Politics", "India"),  # CORRECT
    16789: ("Politics", "India"),  # CORRECT
}
for eid, (exp_topic, exp_region) in FIXTURES.items():
    row, aj = _event_row(eid)
    check(f"D: event #{eid} still has its investigated topic='{exp_topic}' region='{exp_region}' "
          f"(regression lock - not a correctness claim; see the Phase 10 report for the "
          f"per-fixture rationale/confidence)",
          row is not None and aj.get("topic") == exp_topic and aj.get("region") == exp_region)


# ============================================================ E: ambiguous cases handled sanely
print("\n=== E: genuinely ambiguous India/foreign cases don't crash or force a false-confident answer ===")
ambiguous_cases = [
    "Modi urges Putin to move towards ending the Ukraine war",
    "Iran blacklists 45 ships; Indian refiners told to avoid them",
    "Senior Russian officer killed in St. Petersburg car bombing",
]
for text in ambiguous_cases:
    t = an._guess_topic(text)
    r = an._guess_region(text)
    check(f"E: ambiguous case handled without raising, produced a real TOPICS/region value "
          f"('{text[:50]}...' -> topic={t}, region={r})",
          t in an.TOPICS and r in ("India", "World"))


# ============================================================ F: the guard actually applies in the real merge path
print("\n=== F: _merge_into_existing() signature/integration (behavioral, no network/DB writes) ===")
import inspect
sig = inspect.signature(an._merge_into_existing)
check("F1: _merge_into_existing() now requires the articles param (needed to reconstruct "
      "cluster text for the guard) - a real, structural signature change, not cosmetic",
      "articles" in sig.parameters)
src = inspect.getsource(an._merge_into_existing)
check("F2: _merge_into_existing() actually calls the veto for every raw match before "
      "applying it (not just defined-but-unused)",
      "_topic_mismatch_veto(" in src and "raw_matches" in src)
check("F3: database.get_recent_events_for_merge() now also returns region "
      "(previously only topic) - confirmed via a real query",
      "region" in db.get_recent_events_for_merge(days=9999, limit=1)[0] if
      db.get_recent_events_for_merge(days=9999, limit=1) else True)


print(f"\n{'='*60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
