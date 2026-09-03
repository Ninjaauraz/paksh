"""
test_phase23b_evidence_bound.py - Phase 23B: deterministic tests for the
"no unsupported historical/background/superlative claims" rule added to
analyze.py's STRICT NEUTRALITY section.

No real LLM calls - build_prompt()'s text is inspected directly for the
required prompt-level guarantees. Live-LLM adversarial validation (10 real
cases, source-supported vs unsupported superlatives, #8662 regression) was
run separately as part of the Phase 23B forensic investigation - see the
phase report, not reproduced here as a mocked test since the whole point of
that validation was real model behavior, not a fixture.

Run:  py test_phase23b_evidence_bound.py
"""
import analyze

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


CURRENT_EVENT = [
    {"id": 1, "source": "The Hindu", "language": "en", "title": "t1", "summary": "s1", "url": "u1"},
]

prompt = analyze.build_prompt(CURRENT_EVENT)

print("TEST 1: unsupported 'first' - prompt bans it")
check("1: 'first' listed among banned superlatives", '"first"' in prompt)

print("\nTEST 2: unsupported 'historic'/'unprecedented' - prompt bans it")
check("2a: 'historic' listed", '"historic"' in prompt)
check("2b: 'unprecedented' listed", '"unprecedented"' in prompt)

print("\nTEST 3: unsupported 'largest'/'record' - prompt bans it")
check("3a: 'largest' listed", '"largest"' in prompt)
check("3b: 'record' listed", '"record"' in prompt)

print("\nTEST 4: source-supported superlative carve-out is present (must be retained)")
check("4: explicit carve-out for coverage-stated superlatives",
      "report it attributed" in prompt and "like any other claim" in prompt)

print("\nTEST 5: the carve-out is conditioned on the coverage itself making the claim")
check("5: carve-out tied to the coverage, not general knowledge",
      "If the coverage itself makes such a claim" in prompt)

print("\nTEST 6: ordinary synthesis is explicitly still allowed (Section 4 'crucial' guard)")
check("6a: combining facts across sources still allowed",
      "combining facts" in prompt)
check("6b: chronology / paraphrase / comparing emphasis still allowed",
      "chronology" in prompt and "paraphrase" in prompt and "comparing emphasis" in prompt)

print("\nTEST 7: attribution taxonomy (FACT/ALLEGATION/CLAIM/DISPUTED CLAIM/IDENTITY LABEL) "
      "still present unchanged - new rule sits in STRICT NEUTRALITY, not a new register")
check("7a: all attribution categories intact",
      all(k in prompt for k in ("FACT:", "ALLEGATION:", "CLAIM:", "DISPUTED CLAIM:", "IDENTITY LABEL:")))
neutrality_start = prompt.index("STRICT NEUTRALITY")
attribution_start = prompt.index("ATTRIBUTION - keep these registers distinct")
new_rule_pos = prompt.index("Do not add historical, background, or superlative")
check("7b: new rule sits inside STRICT NEUTRALITY, after ATTRIBUTION",
      attribution_start < neutrality_start < new_rule_pos)

print("\nTEST 8: bilingual mandate untouched (rule applies to both languages, no separate HI carve-out needed)")
check("8: bilingual mandate still present", "BILINGUAL OUTPUT IS MANDATORY" in prompt)

print("\nTEST 9: Phase 22D IDENTITY LABEL rule untouched by this addition (no regression)")
check("9a: IDENTITY LABEL category text intact",
      "omit the label entirely" in prompt and "attribute it explicitly" in prompt)
check("9b: separate-incident fabrication ban intact",
      "separate incident" in prompt.lower() or "separate\" incident" in prompt.lower())

print("\nTEST 10: postprocess() still functions correctly on a normal response shape "
      "(the addition doesn't require a new output field, so nothing downstream changes)")
raw = {
    "title": "State Sees Largest Protest in a Decade, Officials Say",
    "summary": "Officials described the demonstration as the largest in the state in a decade.",
    "summary_points": ["Officials called it the largest protest in a decade.",
                        "The claim was attributed to officials, not stated as fact."],
    "title_hi": "अधिकारियों के अनुसार दशक का सबसे बड़ा विरोध प्रदर्शन",
    "summary_hi": "अधिकारियों ने प्रदर्शन को दशक का सबसे बड़ा बताया।",
    "summary_points_hi": ["अधिकारियों ने इसे दशक का सबसे बड़ा प्रदर्शन बताया।",
                           "यह दावा अधिकारियों को बताया गया, तथ्य के रूप में नहीं।"],
    "framing": {"center": ["Reported officials' characterization as an attributed claim."]},
    "framing_hi": {"center": ["अधिकारियों के दावे को उद्धृत के रूप में रिपोर्ट किया।"]},
    "topic": "Society", "region": "India",
}
articles = [{"id": 1, "source": "The Hindu", "language": "en", "title": "t", "summary": "s", "url": "u"}]
out = analyze.postprocess(raw, articles)
check("10: postprocess() unaffected - no schema change from this phase", out.get("title") == raw["title"])

print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
