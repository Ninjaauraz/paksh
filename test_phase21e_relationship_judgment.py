"""
test_phase21e_relationship_judgment.py - Phase 21E: deterministic, MOCKED
tests for relationship_judgment.py's parser/acceptance/selection contract.

No real LLM calls anywhere in this file - every judge_relationships() call
below passes a hand-built generate_fn returning a fixed string, so every test
is fast, free, and fully reproducible. Real-LLM validation lives in a
separate, explicitly-labeled harness (audit_21e_real_llm_validation.py, run
once as part of the Phase 21E report, not part of this regression suite).

Follows the test_phase20d_reframe_merge.py / test_phase21d_context_retrieval.py
convention: check(label, cond) + a FAILURES list.

Run:  py test_phase21e_relationship_judgment.py
"""
import json

import relationship_judgment as rj

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


def cand(pid, title="prev title", summary="prev summary", date="2026-08-01T00:00:00",
         topic="Politics", region="World", sim=0.85, kw=None, count=4, storyline=False,
         thin=False, gap=10):
    return rj.JudgeCandidate(
        previous_event_id=pid, previous_title=title, previous_summary=summary,
        previous_date=date, previous_topic=topic, previous_region=region,
        semantic_similarity=sim, lexical_overlap_terms=kw or [], lexical_overlap_count=count,
        same_storyline=storyline, thin_source=thin, gap_days=gap,
    )


def mock(payload):
    def _gen(prompt):
        return json.dumps(payload)
    return _gen


CURRENT = {"title": "Current event", "summary": "Something happened.",
           "date": "2026-09-01T00:00:00", "topic": "Politics", "region": "World"}


print("PARSER TESTS (1-14)")

print("\nTEST 1: valid R1 parses and is accepted")
r = rj.judge_relationships(CURRENT, [cand(100)], mock({"judgments": [
    {"previous_event_id": 100, "related": True, "relationship_type": "R1",
     "confidence": "high", "shared_anchor": "test campaign X", "evidence": ["a", "b"]}]}))
check("T1: R1 parsed, valid, accepted", r[100].relationship_type == "R1" and rj.accept(r[100]))

print("TEST 2: valid R2 parses")
r = rj.judge_relationships(CURRENT, [cand(101)], mock({"judgments": [
    {"previous_event_id": 101, "related": True, "relationship_type": "R2",
     "confidence": "high", "shared_anchor": "test ruling Y", "evidence": ["x"]}]}))
check("T2: R2 parsed and accepted", r[101].relationship_type == "R2" and rj.accept(r[101]))

print("TEST 3: valid R3 parses")
r = rj.judge_relationships(CURRENT, [cand(102)], mock({"judgments": [
    {"previous_event_id": 102, "related": True, "relationship_type": "R3",
     "confidence": "high", "shared_anchor": "test dispute Z", "evidence": ["x"]}]}))
check("T3: R3 parsed and accepted", r[102].relationship_type == "R3" and rj.accept(r[102]))

print("TEST 4: valid R4 parses (but medium confidence must NOT auto-accept)")
r = rj.judge_relationships(CURRENT, [cand(103)], mock({"judgments": [
    {"previous_event_id": 103, "related": True, "relationship_type": "R4",
     "confidence": "medium", "shared_anchor": "test agreement W", "evidence": ["x"]}]}))
check("T4: R4 medium-confidence parses validly but is REJECTED by the acceptance policy",
      r[103].raw_valid and not rj.accept(r[103]))

print("TEST 5: N1 parses as rejection")
r = rj.judge_relationships(CURRENT, [cand(104)], mock({"judgments": [
    {"previous_event_id": 104, "related": False, "relationship_type": "N1",
     "confidence": "high", "evidence": ["topic only"]}]}))
check("T5: N1 rejected", not rj.accept(r[104]))

print("TEST 6: N2 parses as rejection")
r = rj.judge_relationships(CURRENT, [cand(105)], mock({"judgments": [
    {"previous_event_id": 105, "related": False, "relationship_type": "N2",
     "confidence": "high", "evidence": ["same actor, different event"]}]}))
check("T6: N2 rejected", not rj.accept(r[105]))

print("TEST 7: A1 parses as rejection")
r = rj.judge_relationships(CURRENT, [cand(106)], mock({"judgments": [
    {"previous_event_id": 106, "related": False, "relationship_type": "A1",
     "confidence": "low", "evidence": []}]}))
check("T7: A1 rejected, empty evidence allowed for a rejection", not rj.accept(r[106]))

print("TEST 8: malformed JSON fails closed")
def bad_gen(p): return "not json at all {{{"
r = rj.judge_relationships(CURRENT, [cand(107)], bad_gen)
check("T8: malformed JSON -> fail-closed rejection, not an exception",
      not r[107].raw_valid and not rj.accept(r[107]))

print("TEST 9: missing fields fail closed")
r = rj.judge_relationships(CURRENT, [cand(108)], mock({"judgments": [
    {"previous_event_id": 108, "related": True}]}))  # no relationship_type/confidence/evidence
check("T9: missing fields -> fail-closed rejection", not r[108].raw_valid and not rj.accept(r[108]))

print("TEST 10: invalid relationship_type fails closed")
r = rj.judge_relationships(CURRENT, [cand(109)], mock({"judgments": [
    {"previous_event_id": 109, "related": True, "relationship_type": "R5",
     "confidence": "high", "evidence": ["x"]}]}))
check("T10: invalid enum value -> fail-closed rejection", not r[109].raw_valid)

print("TEST 11: invalid confidence fails closed")
r = rj.judge_relationships(CURRENT, [cand(110)], mock({"judgments": [
    {"previous_event_id": 110, "related": True, "relationship_type": "R1",
     "confidence": "very-high", "evidence": ["x"]}]}))
check("T11: invalid confidence value -> fail-closed rejection", not r[110].raw_valid)

print("TEST 12: contradictory related/relationship_type fails closed")
r = rj.judge_relationships(CURRENT, [cand(111)], mock({"judgments": [
    {"previous_event_id": 111, "related": True, "relationship_type": "N1",
     "confidence": "high", "evidence": ["x"]}]}))
check("T12: related=True with a rejection-type label -> fail-closed",
      not r[111].raw_valid)

print("TEST 13: extra unexpected fields are tolerated (not a failure)")
r = rj.judge_relationships(CURRENT, [cand(112)], mock({"judgments": [
    {"previous_event_id": 112, "related": True, "relationship_type": "R1",
     "confidence": "high", "shared_anchor": "test anchor", "evidence": ["x"],
     "some_extra_field": "ignored"}]}))
check("T13: unexpected extra field does not break parsing", r[112].raw_valid)

print("TEST 14: model output wrapped in markdown fences still parses")
def fenced_gen(p):
    return "```json\n" + json.dumps({"judgments": [
        {"previous_event_id": 113, "related": True, "relationship_type": "R1",
         "confidence": "high", "shared_anchor": "test anchor", "evidence": ["x"]}]}) + "\n```"
r = rj.judge_relationships(CURRENT, [cand(113)], fenced_gen)
check("T14: markdown-fenced JSON is tolerated", r[113].raw_valid and rj.accept(r[113]))

print("\nMULTI-CANDIDATE / SELECTION TESTS (15-20)")

print("TEST 15: one candidate")
r = rj.judge_relationships(CURRENT, [cand(200)], mock({"judgments": [
    {"previous_event_id": 200, "related": True, "relationship_type": "R1",
     "confidence": "high", "shared_anchor": "test anchor", "evidence": ["x"]}]}))
check("T15: single-candidate call works", 200 in r and rj.accept(r[200]))

print("TEST 16: three candidates, judged independently, no contamination")
def three_gen(p):
    return json.dumps({"judgments": [
        {"previous_event_id": 301, "related": True, "relationship_type": "R1",
         "confidence": "high", "shared_anchor": "test anchor", "evidence": ["strong match"]},
        {"previous_event_id": 302, "related": False, "relationship_type": "N2",
         "confidence": "high", "evidence": ["same actor only"]},
        {"previous_event_id": 303, "related": False, "relationship_type": "A1",
         "confidence": "low", "evidence": ["insufficient text"]},
    ]})
cands3 = [cand(301), cand(302), cand(303)]
r = rj.judge_relationships(CURRENT, cands3, three_gen)
check("T16: three candidates each get their own independent, correct verdict",
      rj.accept(r[301]) and not rj.accept(r[302]) and not rj.accept(r[303]))

print("TEST 17: candidate-order reversal in the model's response is handled correctly")
def reversed_gen(p):
    return json.dumps({"judgments": [
        {"previous_event_id": 303, "related": False, "relationship_type": "A1",
         "confidence": "low", "evidence": []},
        {"previous_event_id": 301, "related": True, "relationship_type": "R1",
         "confidence": "high", "shared_anchor": "test anchor", "evidence": ["x"]},
        {"previous_event_id": 302, "related": False, "relationship_type": "N2",
         "confidence": "high", "evidence": ["x"]},
    ]})
r = rj.judge_relationships(CURRENT, cands3, reversed_gen)
check("T17: response order doesn't matter - matched by previous_event_id, not position",
      rj.accept(r[301]) and not rj.accept(r[302]) and not rj.accept(r[303]))

print("TEST 18: a duplicate id in the model response doesn't crash (last one wins deterministically)")
def dup_gen(p):
    return json.dumps({"judgments": [
        {"previous_event_id": 301, "related": False, "relationship_type": "A1",
         "confidence": "low", "evidence": []},
        {"previous_event_id": 301, "related": True, "relationship_type": "R1",
         "confidence": "high", "evidence": ["x"]},
    ]})
r = rj.judge_relationships(CURRENT, [cand(301)], dup_gen)
check("T18: duplicate-id response is handled without raising", 301 in r)

print("TEST 19: no candidates -> no LLM call, empty result")
called = {"n": 0}
def counting_gen(p):
    called["n"] += 1
    return json.dumps({"judgments": []})
r = rj.judge_relationships(CURRENT, [], counting_gen)
check("T19: zero candidates never triggers an LLM call and returns {}",
      r == {} and called["n"] == 0)

print("TEST 20: LLM call failure (exception) fails every candidate closed, not silently accepted")
def raising_gen(p):
    raise RuntimeError("simulated network failure")
r = rj.judge_relationships(CURRENT, [cand(400), cand(401)], raising_gen)
check("T20: an LLM exception rejects every pending candidate, never crashes the caller",
      not r[400].raw_valid and not r[401].raw_valid and
      not rj.accept(r[400]) and not rj.accept(r[401]))

print("\nCONTEXT SELECTION TESTS (21-24)")

print("TEST 21: max-2 context selection enforced even with 3 accepted candidates")
c1, c2, c3 = cand(501, date="2026-07-01", gap=60), cand(502, date="2026-08-01", gap=30), cand(503, date="2026-08-15", gap=15)
results21 = {
    501: rj.JudgeResult(501, True, "R4", "high", ["x"]),
    502: rj.JudgeResult(502, True, "R3", "high", ["y"]),
    503: rj.JudgeResult(503, True, "R1", "high", ["z"]),
}
sel = rj.select_context(CURRENT, [c1, c2, c3], results21, max_context=2)
check("T21: at most 2 predecessors are ever selected, even with 3 valid accepts", len(sel) <= 2)

print("TEST 22: chronological ordering (earliest first)")
check("T22: selected predecessors are in chronological (earliest-first) order",
      [c.previous_date for c, r in sel] == sorted(c.previous_date for c, r in sel))

print("TEST 23: rejected candidates never appear in the selection")
results23 = {
    501: rj.JudgeResult(501, True, "R1", "high", ["x"]),
    502: rj.JudgeResult(502, False, "N2", "high", ["same actor"]),
}
sel23 = rj.select_context(CURRENT, [c1, c2], results23, max_context=2)
check("T23: an N2-rejected candidate never enters the verified selection",
      502 not in [c.previous_event_id for c, r in sel23])

print("TEST 24: no accepted candidates -> empty selection (valid, successful outcome)")
results24 = {501: rj.JudgeResult(501, False, "A1", "low", [])}
sel24 = rj.select_context(CURRENT, [c1], results24, max_context=2)
check("T24: zero accepted candidates produces an empty (not error) selection", sel24 == [])

print("\nDETERMINISM TEST (25)")
sel_a = rj.select_context(CURRENT, [c1, c2, c3], results21, max_context=2)
sel_b = rj.select_context(CURRENT, [c1, c2, c3], results21, max_context=2)
check("T25: select_context is deterministic across repeated calls with identical input",
      [c.previous_event_id for c, r in sel_a] == [c.previous_event_id for c, r in sel_b])

print("\nTEST 26: entity-pair adversarial fixture - prompt contains the explicit "
      "anti-entity-overlap rule, and a correctly-labeled N2 response for the real "
      "#11371/#8807-shaped pair is rejected by the acceptance policy")
prompt_text = rj.build_judgment_prompt(CURRENT, [cand(600)])
check("T26a: the judgment prompt explicitly warns against entity-overlap-as-evidence",
      "recurring public figure" in prompt_text and "N2" in prompt_text)
canary_current = {"title": "Parliamentary panel seeks Meta apology; Rahul Gandhi criticizes PM Modi",
                   "summary": "A parliamentary panel demanded an apology from Meta over a video "
                              "removal, while Rahul Gandhi separately criticized PM Modi.",
                   "date": "2026-08-06", "topic": "Politics", "region": "India"}
canary_cand = cand(8807, title="Rahul Gandhi Accuses PM Modi of Being 'Most Anti-Youth'",
                    summary="Opposition leader Rahul Gandhi accused PM Modi of being the most "
                             "anti-youth prime minister, following a crackdown on protesters.",
                    date="2026-07-25", topic="Politics", region="India", sim=0.920, count=5)
r = rj.judge_relationships(canary_current, [canary_cand], mock({"judgments": [
    {"previous_event_id": 8807, "related": False, "relationship_type": "N2", "confidence": "high",
     "evidence": ["Both mention Rahul Gandhi and PM Modi, but the current event concerns a Meta "
                  "apology row while the candidate concerns a separate anti-youth accusation"]}]}))
check("T26b: a correctly-labeled N2 verdict on the real canary shape is rejected by accept()",
      not rj.accept(r[8807]))

print("\nPHASE 21E.1 REGRESSION-DOCUMENTATION TESTS (27-31)")
print("A shared_anchor prompt refinement was tried and empirically caused 5 real false "
      "acceptances (see the Phase 21E.1 report) - it was REVERTED, not shipped. These tests "
      "document the REVERTED module's actual, current, weaker-than-hoped-for guarantee: "
      "rejection of the canary now depends entirely on the model choosing medium/low "
      "confidence, not on any structural parser check. That gap is a known, carried-forward "
      "limitation for Phase 21F to be aware of, not something this test suite can silently "
      "paper over.")

print("\nTEST 27: reproduces the ACTUAL real Gemini output that caused the false acceptance "
      "this phase found - the reverted module has no mechanism to catch this on its own")
real_bad_output = {"judgments": [
    {"previous_event_id": 8807, "related": True, "relationship_type": "R3", "confidence": "high",
     "evidence": ["CURRENT EVENT states Rahul Gandhi said students require an apology from PM Modi.",
                  "CANDIDATE A states Rahul Gandhi accused PM Modi of being the 'most anti-youth' PM.",
                  "Both texts describe Rahul Gandhi criticizing PM Modi's actions towards students."]}]}
r = rj.judge_relationships(canary_current, [canary_cand], mock(real_bad_output))
check("T27: CONFIRMED LIMITATION - the reverted parser has no structural check that would "
      "catch this specific real false-acceptance shape; it is accepted exactly as the real "
      "model output was. This is documented, not silently fixed.",
      rj.accept(r[8807]))

print("TEST 28: medium-confidence R1/R3/R4 are all rejected (the ONE mechanism that DID work "
      "in the real validation - the confidence gate)")
r = rj.judge_relationships(CURRENT, [cand(703), cand(704), cand(705)], mock({"judgments": [
    {"previous_event_id": 703, "related": True, "relationship_type": "R1",
     "confidence": "medium", "evidence": ["x"]},
    {"previous_event_id": 704, "related": True, "relationship_type": "R3",
     "confidence": "medium", "evidence": ["x"]},
    {"previous_event_id": 705, "related": True, "relationship_type": "R4",
     "confidence": "medium", "evidence": ["x"]},
]}))
check("T28: medium-confidence R1 rejected", r[703].raw_valid and not rj.accept(r[703]))
check("T28: medium-confidence R3 rejected", r[704].raw_valid and not rj.accept(r[704]))
check("T28: medium-confidence R4 rejected", r[705].raw_valid and not rj.accept(r[705]))

print("TEST 29: high-confidence N1/N2/A1 are all rejected regardless of confidence "
      "(rejection is never about confidence, only about relationship_type)")
r = rj.judge_relationships(CURRENT, [cand(706), cand(707), cand(708)], mock({"judgments": [
    {"previous_event_id": 706, "related": False, "relationship_type": "N1",
     "confidence": "high", "evidence": ["x"]},
    {"previous_event_id": 707, "related": False, "relationship_type": "N2",
     "confidence": "high", "evidence": ["x"]},
    {"previous_event_id": 708, "related": False, "relationship_type": "A1",
     "confidence": "high", "evidence": ["x"]},
]}))
check("T29: high-confidence N1/N2/A1 all remain rejected",
      not rj.accept(r[706]) and not rj.accept(r[707]) and not rj.accept(r[708]))

print("TEST 30: a strong genuine candidate and a false-but-high-confidence distractor in the "
      "SAME call are both processed independently - contamination-free, but this also proves "
      "the distractor is NOT independently caught (matches T27's documented limitation)")
def mixed_gen(p):
    return json.dumps({"judgments": [
        {"previous_event_id": 800, "related": True, "relationship_type": "R1",
         "confidence": "high", "evidence": ["genuinely strong match"]},
        {"previous_event_id": 801, "related": True, "relationship_type": "R3",
         "confidence": "high", "evidence": ["topic/entity overlap dressed up as a relationship"]},
    ]})
r = rj.judge_relationships(CURRENT, [cand(800), cand(801)], mixed_gen)
check("T30: genuine candidate accepted", rj.accept(r[800]))
check("T30: a high-confidence FALSE candidate next to it is ALSO accepted - confirms "
      "independence (no contamination either way) but also confirms the parser alone cannot "
      "distinguish them; only the model's own confidence choice can, and it is not reliable",
      rj.accept(r[801]))

print("TEST 31: repeat-call type instability is tolerated by design (accept() only cares "
      "about confidence+type-category, not exact repeatability) - documents this explicitly")
r1 = rj.judge_relationships(CURRENT, [cand(900)], mock({"judgments": [
    {"previous_event_id": 900, "related": True, "relationship_type": "R3",
     "confidence": "medium", "evidence": ["x"]}]}))
r2 = rj.judge_relationships(CURRENT, [cand(900)], mock({"judgments": [
    {"previous_event_id": 900, "related": True, "relationship_type": "R4",
     "confidence": "medium", "evidence": ["x"]}]}))
check("T31: R3-vs-R4 instability across repeat calls is a real, observed pattern (see the "
      "Phase 21E.1 report's repeat-call consistency section) - both remain correctly rejected "
      "at medium confidence regardless of which exact subtype the model picks",
      not rj.accept(r1[900]) and not rj.accept(r2[900]))

print("\nGATE AA2 TESTS (32-36) - overnight Stage-2 hardening: deterministic evidence-")
print("specificity backstop, tested against REAL event text (not synthetic fixtures)")

print("\nTEST 32: Gate AA2 is a THIN-EVIDENCE backstop, not a semantic-fabrication detector -")
print("  documents its real, honest boundary rather than overclaiming what it catches.")
print("  Live validation (2026-09-03, real Gemini calls against real event #5058/#3817 text)")
print("  showed the actual pre-hardening false accept came from the model INVENTING its own")
print("  connective language (\"directly follows\") around genuinely distinct numbers (12% vs")
print("  \"sharp decline\") - Gate AA2's mechanical token-count check cannot detect a FABRICATED")
print("  causal claim built on real, distinct-looking words; only the prompt rules (Hard Rule 8")
print("  + the worked counter-example, both verified live below) catch that specific shape.")
print("  What Gate AA2 DOES reliably catch: evidence that is purely a restatement of the shared")
print("  subject with no other content at all - the thinnest, most mechanical false-accept shape.")
gold_current = ("Gold and Silver Prices Decline Amid Global Economic Cues",
                "Gold prices have fallen below $4,000 per ounce, with a significant monthly "
                "decline of 12% in June, the largest since 2008.")
gold_candidate = ("Gold and Silver Prices Fluctuate Amid Global and Domestic Factors",
                   "Gold and silver prices have seen significant fluctuations, with some "
                   "reports indicating a sharp decline and others noting a rise.")
thin_evidence = [
    "Both mention gold and silver prices.",
    "Both events concern gold and silver.",
]
check("T32: Gate AA2 vetoes genuinely thin evidence (pure shared-subject restatement)",
      not rj._evidence_is_specific(thin_evidence, " ".join(gold_current), " ".join(gold_candidate)))

print("\nTEST 33: a genuine positive (Nepal floods, real event text: death toll 788 -> 939, "
      "same disaster) clears Gate AA2 easily - the backstop never blocks real evidence")
flood_current = ("Nepal Floods: Rescue Efforts Hampered by Terrain, Death Toll Rises",
                  "Rescue operations in Nepal are facing significant challenges as the death "
                  "toll from recent floods has risen to at least 939.")
flood_candidate = ("Nepal Floods Cause Widespread Devastation, Death Toll Rises",
                    "Flash floods in Nepal have resulted in at least 788 deaths, with over "
                    "2,500 people reported missing.")
flood_evidence = [
    "CURRENT EVENT states the death toll has risen to at least 939.",
    "CANDIDATE A states the death toll has risen to at least 788.",
]
check("T33: Gate AA2 does not veto genuine evidence citing a real numeric progression",
      rj._evidence_is_specific(flood_evidence, " ".join(flood_current), " ".join(flood_candidate)))

print("\nTEST 34: reproduces the ACTUAL real post-hardening Gemini output for #5058/#3817 "
      "(2026-09-03 live validation, 5/5 repeat runs) - the model now correctly answers N1 and "
      "cites Hard Rule 8 by name; accept() correctly rejects it via the relationship_type gate "
      "alone (this pins the corrected live behavior as a regression fixture, it does not test "
      "Gate AA2 specifically - see T32's documented boundary)")
real_post_fix_output = {"judgments": [
    {"previous_event_id": 90581, "related": False, "relationship_type": "N1", "confidence": "high",
     "evidence": ["CURRENT EVENT describes a specific 12% monthly decline in gold in June and a "
                  "Rs 1,701 drop in domestic futures.",
                  "CANDIDATE A describes 'significant fluctuations' with 'some reports indicating "
                  "a sharp decline and others noting a rise', which is vague and internally "
                  "conflicting.",
                  "The text in CANDIDATE A does not explicitly state that the 'sharp decline' "
                  "mentioned is the same specific 12% decline reported in the CURRENT EVENT."]}]}
r = rj.judge_relationships(
    {"title": gold_current[0], "summary": gold_current[1], "date": "2026-07-02",
     "topic": "Economy", "region": "India"},
    [cand(90581, title=gold_candidate[0], summary=gold_candidate[1], topic="Economy", region="India")],
    mock(real_post_fix_output))
check("T34: corrected live behavior (N1) is rejected end-to-end",
      not rj.accept(r[90581], current_text=" ".join(gold_current), candidate_text=" ".join(gold_candidate)))

print("\nTEST 35: accept() end-to-end - the genuine Nepal floods positive is still accepted "
      "when current_text/candidate_text are supplied")
r = rj.judge_relationships(
    {"title": flood_current[0], "summary": flood_current[1], "date": "2026-09-01",
     "topic": "World", "region": "World"},
    [cand(916001, title=flood_candidate[0], summary=flood_candidate[1], topic="World", region="World")],
    mock({"judgments": [{"previous_event_id": 916001, "related": True, "relationship_type": "R1",
                          "confidence": "high", "evidence": flood_evidence}]}))
check("T35: genuine positive still accepted end-to-end with real text supplied",
      rj.accept(r[916001], current_text=" ".join(flood_current), candidate_text=" ".join(flood_candidate)))

print("\nTEST 36: prompt contains both new hardening rules (recurring market/commodity "
      "reports, recurring adversarial political exchanges) and the worked counter-example")
prompt = rj.build_judgment_prompt(CURRENT, [cand(1)])
check("T36a: recurring market/commodity rule present", "RECURRING MARKET" in prompt)
check("T36b: recurring political-exchange rule present", "RECURRING ADVERSARIAL" in prompt)
check("T36c: worked counter-example present", "WORKED COUNTER-EXAMPLE" in prompt)

print("\nTEST 37: Gate AA4 - reproduces the ACTUAL real post-hardening Gemini output for "
      "#12833/#17453 and #15445/#17453 (2026-09-03 shadow replay against real, unseen recent "
      "events surfaced these as false accepts even AFTER Hard Rule 8 was broadened to name "
      "this exact 'recurring macro-narrative, new specific trigger each time' shape - prompt "
      "refinement alone did not generalize across topics). Gate AA4 (previously Politics-only) "
      "is generalized to Economy too and correctly vetoes both, structurally, regardless of "
      "the model's own confidence")
market_current = ("Middle East Conflict Fuels Global Market Sell-off and Inflation Fears",
                   "Global bond markets experienced a sell-off as tensions in the Middle East "
                   "escalated following new strikes in the region.")
market_candidate = ("Global Markets React to Rising Oil Prices and Geopolitical Tensions",
                     "Global stock markets experienced declines as elevated crude oil prices "
                     "weighed on investor sentiment amid Middle East tensions.")
real_market_false_accept = {"judgments": [
    {"previous_event_id": 128331, "related": True, "relationship_type": "R3", "confidence": "high",
     "evidence": ["Both events link Middle East tensions/conflict to rising oil prices and "
                  "global market reactions including inflation fears and sell-offs.",
                  "CURRENT EVENT indicates a further escalation of the conflict and its "
                  "market impact."]}]}
r = rj.judge_relationships(
    {"title": market_current[0], "summary": market_current[1], "date": "2026-09-02",
     "topic": "Economy", "region": "World"},
    [cand(128331, title=market_candidate[0], summary=market_candidate[1], topic="Economy", region="World")],
    mock(real_market_false_accept))
check("T37a: without Gate AA4 (no topics supplied), this real shape is accepted (documents "
      "the pre-Gate-AA4 gap, matches T27's documentation pattern)",
      rj.accept(r[128331], current_text=" ".join(market_current), candidate_text=" ".join(market_candidate)))
check("T37b: Gate AA4 (Economy/Economy, R3, same_storyline=False) vetoes it",
      not rj.accept(r[128331], current_text=" ".join(market_current), candidate_text=" ".join(market_candidate),
                     current_topic="Economy", candidate_topic="Economy", same_storyline=False))
check("T37c: Gate AA4 does not block the SAME shape when same_storyline=True corroborates it",
      rj.accept(r[128331], current_text=" ".join(market_current), candidate_text=" ".join(market_candidate),
                current_topic="Economy", candidate_topic="Economy", same_storyline=True))
check("T37d: Gate AA4 does not touch a different topic pair (e.g. World/International)",
      rj.accept(r[128331], current_text=" ".join(market_current), candidate_text=" ".join(market_candidate),
                current_topic="World", candidate_topic="World", same_storyline=False))

print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
