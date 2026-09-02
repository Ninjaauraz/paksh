"""
test_phase21d_context_retrieval.py - Phase 21D: deterministic unit tests for
the isolated context_retrieval.py module.

No real database, no real embeddings, no LLM calls. Every fixture is a small,
hand-built dict of synthetic events + hand-built centroid vectors, so every
test is fast, reproducible, and independent of paksh.db's actual contents.
Follows the test_phase7b.py/test_phase20d_reframe_merge.py convention:
check(label, cond) + a FAILURES list.

Run:  py test_phase21d_context_retrieval.py
"""
import inspect
import numpy as np

import context_retrieval as cr

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


def _unit(v):
    v = np.array(v, dtype=np.float32)
    return v / np.linalg.norm(v)


# Two orthogonal anchors so we can hand-place vectors at any desired cosine
# similarity to the "current" event's vector, deterministically.
A = _unit([1, 0, 0, 0])
B = _unit([0, 1, 0, 0])


def _at(cos_to_a):
    """A unit vector with cosine similarity ~= cos_to_a to A."""
    s = max(0.0, 1 - cos_to_a ** 2) ** 0.5
    return _unit(cos_to_a * A + s * B)


def ev(id, title, summary, date, topic="Politics", region="World"):
    return {"id": id, "title": title, "summary": summary,
            "created_at": date, "published_at": None,
            "topic": topic, "region": region}


CUR_DATE = "2026-09-02T00:00:00"


print("TEST 1: genuine continuation retrieved")
current = ev(100, "USPS Accused of Secretly Pursuing Trump Mail Voting Plan",
             "A whistleblower has alleged the USPS is secretly proceeding with a mail-voting plan.",
             CUR_DATE, topic="Politics")
prev1 = ev(90, "Whistleblower Alleges USPS Mail Voting System Rushed and Flawed",
           "A whistleblower has claimed the USPS is rapidly implementing an online mail-in voting system.",
           "2026-09-01T00:00:00", topic="Crime & Law")
events_by_id = {100: current, 90: prev1}
centroids = {100: A, 90: _at(0.90)}
out = cr.retrieve_historical_candidates(100, events_by_id, centroids, {},
                                          cosine_threshold=0.80, lexical_min_overlap=2)
check("T1: genuine continuation retrieved", any(c.previous_event_id == 90 for c in out))

print("\nTEST 2: same entity but unrelated -> rejected")
current2 = ev(200, "Trump Announces Drug Pricing Deals with Pharma Companies",
              "President Trump announced agreements with pharmaceutical companies on drug pricing.",
              CUR_DATE)
unrelated_trump = ev(190, "Trump clashes with CNN reporter over coverage",
                      "Former President Trump criticized a CNN reporter during a press event.",
                      "2026-08-20T00:00:00")
events_by_id2 = {200: current2, 190: unrelated_trump}
centroids2 = {200: A, 190: _at(0.85)}   # deliberately high similarity (the "entity trap")
out2 = cr.retrieve_historical_candidates(200, events_by_id2, centroids2, {},
                                           cosine_threshold=0.80, lexical_min_overlap=3)
check("T2: same-entity-only pair rejected despite high similarity",
      not any(c.previous_event_id == 190 for c in out2))

print("\nTEST 3: same topic but unrelated -> rejected")
current3 = ev(300, "UK man on trial for alleged drugging and abuse of wife",
              "A man in the UK is on trial accused of drugging and abusing his wife.", CUR_DATE,
              topic="Crime & Law")
unrelated_crime = ev(290, "Meta faces trial over claims of making social media addictive",
                      "Meta is facing a trial over allegations its platforms are addictive for children.",
                      "2026-08-15T00:00:00", topic="Crime & Law")
events_by_id3 = {300: current3, 290: unrelated_crime}
centroids3 = {300: A, 290: _at(0.55)}
out3 = cr.retrieve_historical_candidates(300, events_by_id3, centroids3, {}, cosine_threshold=0.80)
check("T3: same-topic-unrelated pair rejected (low similarity, no overlap)",
      not any(c.previous_event_id == 290 for c in out3))

print("\nTEST 4: formulaic headline -> rejected via generic-word discount")
current4 = ev(400, "Gold silver prices fall as rate-hike bets rise on oil, yields",
              "Gold and silver prices dropped as rate-hike expectations grew amid oil price moves.",
              CUR_DATE, topic="Economy")
oil_story = ev(390, "Oil Prices Steady Amidst Shifting US-Iran Talks Outlook",
               "Oil prices held steady as markets watched for developments in US-Iran talks.",
               "2026-09-01T00:00:00", topic="Economy")
events_by_id4 = {400: current4, 390: oil_story}
centroids4 = {400: A, 390: _at(0.92)}   # the real corpus showed 0.88-0.94 for this exact pattern
out4 = cr.retrieve_historical_candidates(400, events_by_id4, centroids4, {},
                                           cosine_threshold=0.80, lexical_min_overlap=3,
                                           discount_generic=True)
check("T4: formulaic 'oil/gold prices' pair rejected once generic tokens are discounted",
      not any(c.previous_event_id == 390 for c in out4))

print("\nTEST 5: cross-topic genuine relationship retrieved")
current5 = ev(500, "Iran offers return to ceasefire if US complies",
              "Iran has stated its readiness to return to a ceasefire agreement with the United States.",
              CUR_DATE, topic="International")
prev5 = ev(490, "Iran President Signals Readiness for Talks if US Returns to Deal",
           "Iran's president has stated readiness for talks if the United States returns to the deal.",
           "2026-09-01T12:00:00", topic="Politics")   # DIFFERENT topic on purpose
events_by_id5 = {500: current5, 490: prev5}
centroids5 = {500: A, 490: _at(0.81)}
out5 = cr.retrieve_historical_candidates(500, events_by_id5, centroids5, {},
                                           cosine_threshold=0.80, lexical_min_overlap=2)
check("T5: genuine cross-topic relationship retrieved (topic is not a hard gate)",
      any(c.previous_event_id == 490 for c in out5))

print("\nTEST 6: >14-day genuine relationship retrieved")
current6 = ev(600, "US-Iran tensions continue over Strait of Hormuz", "Tensions continue.", CUR_DATE,
              topic="International")
prev6 = ev(590, "US Strikes Iran After Tanker Attacks in Strait of Hormuz",
           "The US struck Iran following tanker attacks in the Strait of Hormuz region.",
           "2026-07-15T00:00:00", topic="International")   # 49 days earlier
events_by_id6 = {600: current6, 590: prev6}
centroids6 = {600: A, 590: _at(0.78)}
out6 = cr.retrieve_historical_candidates(600, events_by_id6, centroids6, {},
                                           lookback_days=56, cosine_threshold=0.75, lexical_min_overlap=1)
check("T6: >14-day (49-day) genuine relationship retrieved within a 56-day lookback",
      any(c.previous_event_id == 590 for c in out6))

print("\nTEST 7: no-history event returns empty")
current7 = ev(700, "A brand new isolated story", "Nothing precedes this.", CUR_DATE)
out7 = cr.retrieve_historical_candidates(700, {700: current7}, {700: A}, {})
check("T7: no eligible history -> empty candidate list (valid, not an error)", out7 == [])

print("\nTEST 8: thin candidate flagged")
current8 = ev(800, "Couple dies in Spain hot tub incident; children find bodies",
              "A couple was found dead in a hot tub in Spain; their children discovered the bodies.",
              CUR_DATE, topic="Crime & Law")
thin_prev = ev(790, "Couple Found Dead in Spanish Jacuzzi; Foul Play Ruled Out", "",
               "2026-09-01T00:00:00", topic="Crime & Law")
events_by_id8 = {800: current8, 790: thin_prev}
centroids8 = {800: A, 790: _at(0.87)}
out8 = cr.retrieve_historical_candidates(800, events_by_id8, centroids8, {},
                                           cosine_threshold=0.80, lexical_min_overlap=1)
match8 = [c for c in out8 if c.previous_event_id == 790]
check("T8: thin (empty-summary) candidate is retrieved AND flagged thin_source=True",
      len(match8) == 1 and match8[0].thin_source is True)

print("\nTEST 9: empty summary produces no fabricated lexical overlap")
shared, count = cr.lexical_overlap(
    {"title": "Zebras roam savanna plains freely", "summary": ""},
    {"title": "Distant galaxies observed through orbiting telescope", "summary": ""},
)
check("T9: two events with empty summaries and disjoint titles share zero terms",
      shared == set() and count == 0)

print("\nTEST 10: current event cannot retrieve itself")
current10 = ev(1000, "Self-referential test event", "Some summary text here.", CUR_DATE)
out10 = cr.retrieve_historical_candidates(1000, {1000: current10}, {1000: A}, {},
                                            cosine_threshold=0.0, lexical_min_overlap=0)
check("T10: current_event_id never appears among its own candidates",
      not any(c.previous_event_id == 1000 for c in out10))

print("\nTEST 11: future event cannot be retrieved")
current11 = ev(1100, "Current dated event", "Some text about a current development.", CUR_DATE)
future = ev(1101, "A future dated event", "Some text about a current development.",
            "2026-09-05T00:00:00")   # AFTER current
events_by_id11 = {1100: current11, 1101: future}
centroids11 = {1100: A, 1101: A}   # identical vector - would trivially pass every gate if allowed
out11 = cr.retrieve_historical_candidates(1100, events_by_id11, centroids11, {},
                                            cosine_threshold=0.0, lexical_min_overlap=0)
check("T11: an event dated AFTER the current event is never returned, even at similarity 1.0",
      out11 == [])

print("\nTEST 12: storyline membership cannot bypass the lexical/semantic gates")
current12 = ev(1200, "Kangaroos gather near watering hole at dusk", "Marsupials seen grazing quietly.",
                CUR_DATE)
weak_prev = ev(1190, "Distant galaxies photographed by orbiting observatory",
               "Astronomers released new deep-space imagery this week.", "2026-09-01T00:00:00")
events_by_id12 = {1200: current12, 1190: weak_prev}
centroids12 = {1200: A, 1190: _at(0.85)}   # high similarity, but zero lexical overlap
storyline_emap12 = {1200: "sl-x", 1190: "sl-x"}   # SAME storyline
out12_s2 = cr.retrieve_historical_candidates(1200, events_by_id12, centroids12, storyline_emap12,
                                               cosine_threshold=0.80, lexical_min_overlap=3,
                                               storyline_mode="S2")
check("T12a: S2 (rank boost) does not let a zero-overlap storyline pair through",
      not any(c.previous_event_id == 1190 for c in out12_s2))
out12_s3 = cr.retrieve_historical_candidates(1200, events_by_id12, centroids12, storyline_emap12,
                                               cosine_threshold=0.80, lexical_min_overlap=3,
                                               storyline_mode="S3")
check("T12b: S3 (bounded preservation allowance) still rejects a ZERO-overlap storyline pair "
      "(allowance reduces the bar by 2, from 3 to 1, it does not remove it)",
      not any(c.previous_event_id == 1190 for c in out12_s3))

print("\nTEST 13: top-3 candidate limit enforced")
current13 = ev(1300, "Barcelona Agrees Deal to Sign Multiple Players",
               "Barcelona completed several transfer deals this transfer window for new players.", CUR_DATE,
               topic="Sports")
many_prev = {}
centroids13 = {1300: A}
for i in range(10):
    eid = 1290 - i
    many_prev[eid] = ev(eid, f"Barcelona Agrees Deal to Sign Player Number {i}",
                         "Barcelona completed a transfer deal for a new player this transfer window.",
                         "2026-09-01T00:00:00", topic="Sports")
    centroids13[eid] = _at(0.85)
events_by_id13 = {1300: current13, **many_prev}
out13 = cr.retrieve_historical_candidates(1300, events_by_id13, centroids13, {},
                                            cosine_threshold=0.80, lexical_min_overlap=2,
                                            candidate_budget=3, raw_topn=50)
check("T13: 10 qualifying candidates exist, but at most 3 are returned",
      len(out13) <= 3)

print("\nTEST 14: deterministic tie-breaking")
current14 = ev(1400, "Barcelona Agrees Deal to Sign Multiple Players",
               "Barcelona completed several transfer deals this transfer window for new players.", CUR_DATE,
               topic="Sports")
tie_a = ev(1391, "Barcelona Agrees Deal to Sign Player Alpha",
           "Barcelona completed a transfer deal for a new player this transfer window.",
           "2026-09-01T00:00:00", topic="Sports")
tie_b = ev(1392, "Barcelona Agrees Deal to Sign Player Beta",
           "Barcelona completed a transfer deal for a new player this transfer window.",
           "2026-09-01T00:00:00", topic="Sports")
events_by_id14 = {1400: current14, 1391: tie_a, 1392: tie_b}
centroids14 = {1400: A, 1391: _at(0.85), 1392: _at(0.85)}   # identical similarity by construction
out14a = cr.retrieve_historical_candidates(1400, events_by_id14, centroids14, {},
                                             cosine_threshold=0.80, lexical_min_overlap=2)
out14b = cr.retrieve_historical_candidates(1400, events_by_id14, centroids14, {},
                                             cosine_threshold=0.80, lexical_min_overlap=2)
order_a = [c.previous_event_id for c in out14a]
order_b = [c.previous_event_id for c in out14b]
check("T14: identical inputs produce identical candidate order across repeated calls",
      order_a == order_b and order_a == sorted(order_a))

print("\nTEST 15: no mutation of database (static source-level guarantee)")
src = inspect.getsource(cr)
forbidden = ["INSERT INTO", "UPDATE events", "UPDATE articles", "DELETE FROM",
             "insert_event(", "update_event(", "assign_articles_to_event(",
             "delete_event(", "conn.commit()"]
hits = [f for f in forbidden if f in src]
check("T15: context_retrieval.py contains no write/mutation call of any kind",
      hits == [])

print("\nTEST 16 (Phase 21D.1): S3 storyline mode recovers a genuine storyline-linked "
      "relationship that S0 misses, without opening the same event to an unrelated candidate")
current16 = ev(1600, "Two More Air India Flight Pilots Fail Drug Screening",
               "Two additional pilots employed by the flight crew have tested non-negative in drug screenings.",
               CUR_DATE, topic="Crime & Law")
weak_link_prev = ev(1590, "Air India Flight Turbulence Incident: Pilot Under Scrutiny",
                     "An Air India flight crew faced scrutiny after severe turbulence injured passengers.",
                     "2026-08-20T00:00:00", topic="Crime & Law")
events_by_id16 = {1600: current16, 1590: weak_link_prev}
centroids16 = {1600: A, 1590: _at(0.80)}   # passes semantic bar, but thin lexical overlap
storyline_emap16 = {1600: "sl-y", 1590: "sl-y"}
out16_s0 = cr.retrieve_historical_candidates(1600, events_by_id16, centroids16, storyline_emap16,
                                               cosine_threshold=0.78, lexical_min_overlap=4,
                                               storyline_mode="S0")
out16_s3 = cr.retrieve_historical_candidates(1600, events_by_id16, centroids16, storyline_emap16,
                                               cosine_threshold=0.78, lexical_min_overlap=4,
                                               storyline_mode="S3")
_, weak_count = cr.lexical_overlap(current16, weak_link_prev, "title+200", True)
check("T16 setup sanity: this pair's lexical overlap sits below the plain min_overlap=4 bar",
      weak_count < 4)
check("T16a: S0 (ignore storyline) misses this genuine storyline-linked relationship",
      not any(c.previous_event_id == 1590 for c in out16_s0))
check("T16b: S3 (bounded storyline allowance) recovers it",
      any(c.previous_event_id == 1590 for c in out16_s3))

print("\nTEST 17 (Phase 21D.1): KNOWN, DOCUMENTED, UNRESOLVED false positive - the real "
      "#11371/#8807 'recurring political sparring' pair (sim=0.920, lex=5) STILL PASSES at "
      "the current recommended defaults. This is a canary, not a fix: it exists so that if a "
      "future change to the lexical/generic-word gate silently starts rejecting this pair, "
      "that improvement is visible and intentional, not an untracked side effect. See the "
      "Phase 21D.1 report's Gate 22 finding: recurring political-opponent headline pairs are "
      "not yet guarded against, the same way the oil/gold commodity-vocabulary pattern is.")
current17 = ev(1700, "Parliamentary panel seeks Meta apology; Rahul Gandhi criticizes PM Modi",
               "A parliamentary panel demanded an apology from Meta, while Rahul Gandhi criticized PM Modi separately.",
               CUR_DATE, topic="Politics")
unrelated_sparring = ev(1690, "Rahul Gandhi Accuses PM Modi of Being 'Most Anti-Youth'",
                          "Opposition leader Rahul Gandhi accused PM Modi of being the most anti-youth prime minister.",
                          "2026-08-08T00:00:00", topic="Politics")
events_by_id17 = {1700: current17, 1690: unrelated_sparring}
centroids17 = {1700: A, 1690: _at(0.92)}   # the real pair's actual observed similarity
out17 = cr.retrieve_historical_candidates(1700, events_by_id17, centroids17, {1700: "sl-z", 1690: "sl-z"},
                                            cosine_threshold=0.78, lexical_min_overlap=4,
                                            storyline_mode="S3")
check("T17: documents (does not fix) the known recurring-entity-pair false positive at "
      "current default parameters",
      any(c.previous_event_id == 1690 for c in out17))

print("\nTEST 18 (Phase 21D.1): candidate budget still enforced under S3")
current18 = ev(1800, "Barcelona Agrees Deal to Sign Multiple Players",
               "Barcelona completed several transfer deals this transfer window for new players.", CUR_DATE,
               topic="Sports")
many18 = {}
centroids18 = {1800: A}
storyline18 = {1800: "sl-w"}
for i in range(10):
    eid = 1790 - i
    many18[eid] = ev(eid, f"Barcelona Agrees Deal to Sign Player Number {i}",
                      "Barcelona completed a transfer deal for a new player this transfer window.",
                      "2026-09-01T00:00:00", topic="Sports")
    centroids18[eid] = _at(0.85)
    storyline18[eid] = "sl-w"
events_by_id18 = {1800: current18, **many18}
out18 = cr.retrieve_historical_candidates(1800, events_by_id18, centroids18, storyline18,
                                            cosine_threshold=0.78, lexical_min_overlap=2,
                                            storyline_mode="S3", candidate_budget=3)
check("T18: budget of 3 is still enforced even when every candidate shares the current event's storyline",
      len(out18) <= 3)

print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
