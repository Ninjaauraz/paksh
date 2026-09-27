"""
test_topic_region_classification.py - regression test for the 2026-09-27 topic/region
prompt fix in analyze.build_prompt().

BACKGROUND: a read-only 259-event classification benchmark (post-audit validation) found
two recurring LLM classification errors, both summary_method="llm" (never the regex
fallback _guess_topic()/_guess_region(), which is why this fix touches ONLY the prompt
text in build_prompt(), not those functions):
  1. TOPIC: a process/institution keyword (court, FIR, SIT, audit, police, hearing...)
     in the text caused Crime & Law even when the story's substantive subject was
     something else entirely (infrastructure, admin, politics). Confirmed examples:
     "NHAI to upgrade 1033 highway helpline", "Himachal Pradesh Government to Refund
     Fees for Cancelled Recruitment Exams", "Akal Takht issues warning to Punjab CM".
  2. REGION: 'India' assigned on an incidental Indian name/company/place mention with
     no substantive India connection. Confirmed examples: "Afghanistan and Bangladesh
     Announce Asian Games Cricket Squads", "Nepal floods damage China's railway
     project", "Emails show Anthropic CEO's wife sought Epstein investment...".

WHAT THIS SUITE PINS (no LLM call, no network, no paksh.db - same convention as
test_phase41_synthesis_prompt.py): the build_prompt() instruction text itself contains
the PRINCIPLE that should prevent each failure pattern, and nothing else in the prompt
(schema keys, TOPICS list, unrelated instructions) was touched. It intentionally does
NOT assert what a live LLM would output for the fixture cases below - that can only be
verified by actually running a live cycle (see report: reuse the 259-event benchmark
script for that). Faking a classifier to assert output here would test the fake, not
the real prompt - the task explicitly asked not to do that.

Run:  py test_topic_region_classification.py
"""
import analyze
from analyze import build_prompt, TOPICS

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


ARTS = [
    {"source": "The Hindu", "language": "en", "title": "Sample headline",
     "url": "u1", "summary": "Sample summary text.", "image_url": ""},
    {"source": "The Print", "language": "en", "title": "Sample headline, second outlet",
     "url": "u2", "summary": "Sample summary text, second outlet.", "image_url": ""},
]
_orig_lean_of = analyze.lean_of
analyze.lean_of = lambda name, region=None: "left" if name == "The Hindu" else "center"

# The 8 confirmed benchmark fixtures (documentation + what a correct future live cycle
# should produce - NOT asserted here, since that requires an actual LLM call).
FIXTURES = [
    # TOPIC fixtures: institution/process keyword present, substantive subject is not crime/law
    {"title": "NHAI to upgrade 1033 highway helpline with AI and real-time tracking",
     "summary": "The National Highways Authority of India plans to upgrade its 1033 "
                 "helpline to improve emergency response times using AI and real-time "
                 "location tracking on national highways.",
     "expected_topic_not": "Crime & Law", "reason": "infrastructure/tech story, not a crime/legal matter"},
    {"title": "Himachal Pradesh Government to Refund Fees for Cancelled Recruitment Exams",
     "summary": "The Himachal Pradesh government will refund application fees to "
                 "candidates whose HPSSC recruitment exams were cancelled.",
     "expected_topic_not": "Crime & Law", "reason": "administrative refund, not a crime/legal matter"},
    {"title": "Akal Takht issues warning to Punjab CM Bhagwant Mann",
     "summary": "The Akal Takht issued a 10-day ultimatum to Punjab CM Bhagwant Mann "
                 "amid a political and religious controversy.",
     "expected_topic_not": "Crime & Law", "reason": "political/religious controversy, not a crime/legal matter"},
    {"title": "Supreme Court Upholds Bail Cancellation for Nightclub Fire Accused",
     "summary": "The Supreme Court upheld the cancellation of bail for the accused in "
                 "a nightclub fire case, citing the severity of the charges.",
     "expected_topic": "Crime & Law", "reason": "a genuine court/criminal case - the SUBJECT is the case itself"},
    # REGION fixtures: incidental Indian mention vs substantive India connection
    {"title": "Afghanistan and Bangladesh Announce Asian Games Cricket Squads",
     "summary": "Afghanistan and Bangladesh have announced their squads for the Asian "
                 "Games cricket tournament, with both cricket boards naming their captains.",
     "expected_region": "World", "reason": "no India connection at all"},
    {"title": "Nepal floods damage China's railway project, raise concerns",
     "summary": "Flash floods in Nepal have damaged China's Belt and Road railway "
                 "project near the Nepal-China border, raising infrastructure concerns.",
     "expected_region": "World", "reason": "purely Nepal-China, no India party"},
    {"title": "Emails show Anthropic CEO's wife sought Epstein investment for adult business",
     "summary": "Newly revealed emails show the wife of Anthropic's CEO approached "
                 "Jeffrey Epstein seeking investment for an adult entertainment venture.",
     "expected_region": "World", "reason": "entirely a US matter, no India connection"},
    {"title": "India Raises Concerns Over Potential 100% Tariff on Russian Oil",
     "summary": "India has raised concerns with the US over a proposed 100% tariff on "
                 "goods linked to India's imports of Russian oil, amid bilateral trade talks.",
     "expected_region": "India", "reason": "India is a genuine party to the matter, even though the US and Russia are also involved"},
]

try:
    PROMPT = build_prompt(ARTS)
    NP = " ".join(PROMPT.split())  # the prompt hard-wraps its lines

    print("=== A: TOPIC instruction now separates PROCESS from SUBJECT ===")
    check("1: explicit PROCESS IS NOT SUBJECT principle is present",
          "PROCESS IS NOT SUBJECT" in NP)
    check("2: the process/institution keywords the benchmark flagged are named",
          "FIR" in NP and "SIT/CBI/ED" in NP and "audit" in NP and "hearing" in NP
          and "complaint" in NP and "legal challenge" in NP)
    check("3: the guard is conditional on the crime/legal matter being the SUBSTANCE",
          "Crime & Law ONLY when the crime or legal matter IS what the story is "
          "substantively about" in NP)
    check("4: worked counter-examples name the SAME categories the benchmark found "
          "(infra/admin/politics), matching the confirmed failure patterns",
          "a court permitting a port project" in NP
          and "a government refunding exam fees" in NP
          and "a religious body warning a politician" in NP)
    check("5: Crime & Law's own definition now distinguishes subject from mechanism",
          "as the story's own subject, not merely its reporting mechanism" in NP)
    check("6: genuine crime/legal classification is NOT weakened - 'courts, police, "
          "crime' still the definition, MAIN-subject rule still present",
          "Crime & Law = courts, police, crime as the story's own subject" in NP
          and "Choose the single best fit by the story's MAIN subject, not an "
              "incidental mention" in NP)

    print("=== B: REGION instruction now requires a SUBSTANTIVE India connection ===")
    check("7: explicit SUBSTANTIVELY central requirement",
          "SUBSTANTIVELY central to the story" in NP)
    check("8: incidental mention is explicitly excluded",
          "not merely because an Indian person, company or place is mentioned in "
          "passing" in NP)
    check("9: a story mainly about OTHER countries stays World even with a brief "
          "Indian detail - matches the Afghanistan/Nepal-China/Anthropic patterns",
          "stays 'World' even if an Indian name or detail appears briefly within it" in NP)
    check("10: India-as-genuine-party is explicitly preserved (not over-corrected)",
          "India-US trade talks, India-China border developments" in NP
          and "when India's stake is the story" in NP)

    print("=== C: nothing else in the classification schema changed ===")
    check("11: TOPICS list itself is untouched (still the original 10 values)",
          TOPICS == ["Politics", "Economy", "International", "Sports", "Crime & Law",
                     "Science & Tech", "Health", "Entertainment", "Environment", "Society"])
    check("12: the {TOPICS} placeholder still substitutes into the prompt",
          all(t in PROMPT for t in TOPICS))
    check("13: unrelated schema keys (title/summary/framing/bilingual) are untouched",
          '"title": "neutral English headline' in NP
          and "BILINGUAL OUTPUT IS MANDATORY" in NP
          and '"framing": {' in PROMPT)

    print("\n=== D: benchmark fixtures (documentation only - NOT asserted; a live LLM "
          "call is required to verify actual output, see final report) ===")
    for fx in FIXTURES:
        want = fx.get("expected_topic") or fx.get("expected_region") \
            or f"not {fx.get('expected_topic_not')}"
        print(f"  [{want}] {fx['title']}  ({fx['reason']})")
finally:
    analyze.lean_of = _orig_lean_of


print(f"\n{'=' * 60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
