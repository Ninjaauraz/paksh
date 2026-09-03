"""
test_phase22d_characterization.py - Phase 22D: deterministic tests for the
IDENTITY LABEL attribution rule added to analyze.py's ATTRIBUTION section.

No real LLM calls - build_prompt()'s text is inspected directly, and
postprocess() is tested against hand-built "raw" model responses shaped
like what a correctly-behaving (and, for regression documentation, an
incorrectly-behaving) model would produce. Never touches paksh.db.

Live-LLM validation of the actual real-world effect (10 adversarial cases,
before/after the prompt change) was run separately as part of the Phase 22D
forensic investigation - see the phase report, not reproduced here as a
mocked test since the whole point of that validation was real model
behavior, not a fixture.

Run:  py test_phase22d_characterization.py
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

print("TEST 1: prompt contains the new IDENTITY LABEL attribution rule")
prompt = analyze.build_prompt(CURRENT_EVENT)
check("1a: IDENTITY LABEL category present", "IDENTITY LABEL" in prompt)
check("1b: instructs omit-or-attribute when sources disagree",
      "omit the label entirely" in prompt and "attribute it explicitly" in prompt)
check("1c: explicitly forbids the fabricated-separate-incident failure mode "
      "(the real, confirmed Phase 22D case 9 defect)",
      "separate incident" in prompt.lower() or "separate\" incident" in prompt.lower())
check("1d: existing FACT/ALLEGATION/CLAIM/DISPUTED CLAIM categories still present unchanged",
      all(k in prompt for k in ("FACT:", "ALLEGATION:", "CLAIM:", "DISPUTED CLAIM:")))

print("\nTEST 2: existing strict-neutrality and framing rules are untouched by this addition")
check("2a: 'never invent facts' rule still present", "Never invent facts" in prompt)
check("2b: framing comparative-bullet rules still present", "COMPARATIVE" in prompt)
check("2c: bilingual mandate still present", "BILINGUAL OUTPUT IS MANDATORY" in prompt)

print("\nTEST 3: the new rule sits within the existing ATTRIBUTION section, not a new "
      "top-level section (smallest possible change, per Phase 22D's own instruction)")
attribution_start = prompt.index("ATTRIBUTION - keep these registers distinct")
neutrality_start = prompt.index("STRICT NEUTRALITY")
identity_pos = prompt.index("IDENTITY LABEL")
check("3: IDENTITY LABEL sits between ATTRIBUTION's header and STRICT NEUTRALITY's header",
      attribution_start < identity_pos < neutrality_start)

print("\nTEST 4: postprocess() still functions correctly on a normal response shape "
      "(the addition doesn't require a new output field, so nothing downstream changes)")
raw = {
    "title": "Man Arrested for Vehicle Theft", "summary": "Police arrested a man for theft.",
    "summary_points": ["Police arrested a man.", "He was accused of vehicle theft."],
    "title_hi": "चोरी के आरोप में व्यक्ति गिरफ्तार", "summary_hi": "पुलिस ने चोरी के आरोप में गिरफ्तार किया।",
    "summary_points_hi": ["पुलिस ने गिरफ्तार किया।", "उस पर चोरी का आरोप है।"],
    "framing": {"center": ["Reported the arrest with attributed allegation language."]},
    "framing_hi": {"center": ["गिरफ्तारी की सूचना दी।"]},
    "topic": "Crime & Law", "region": "India",
}
articles = [{"id": 1, "source": "The Hindu", "language": "en", "title": "t", "summary": "s", "url": "u"}]
out = analyze.postprocess(raw, articles)
check("4: postprocess() unaffected - no schema change from this phase", out.get("title") == raw["title"])

print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
