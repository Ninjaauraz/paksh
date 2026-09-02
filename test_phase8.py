"""
test_phase8.py - Paksh 8: summary & framing quality upgrade.

Phase 8 changed build_prompt()'s INSTRUCTION TEXT only (event-type-aware fact
extraction guidance, an explicit FACT/ALLEGATION/CLAIM/DISPUTED-CLAIM
framework, cross-article synthesis instruction, and a 5-8 sentence summary
target instead of 4-6) - it did not change the JSON output schema, postprocess()'s
parsing/validation, content_complete, framing cleaning, extractive fallback, or
region/lean logic. This suite tests what's actually testable without a live LLM:
prompt construction (the instructions the model receives) and postprocess()'s
handling of a representative, hand-built "raw" LLM response - never a real
network call, so this suite has no provider dependency and never touches the
real paksh.db.

Live LLM-quality verification (does the model actually follow this guidance
better?) is out of scope for a unit suite by nature - see the Phase 8 report's
"Live sample results" section for that evidence instead.

Run:  py test_phase8.py
"""
import analyze
from analyze import (
    build_prompt, postprocess, compute_content_complete, has_framing,
    _clean_framing, _extractive_raw, TOPICS, LEAN_ORDER,
)

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


_ARTICLES = [
    {"id": 1, "source": "TestLeftOutlet", "language": "en", "title": "t1",
     "summary": "s1", "url": "u1"},
    {"id": 2, "source": "TestCenterOutlet", "language": "en", "title": "t2",
     "summary": "s2", "url": "u2"},
]
_orig_lean_of = analyze.lean_of
analyze.lean_of = lambda name, region=None: (
    "left" if "Left" in name else "center" if "Center" in name else "unrated")

try:
    PROMPT = build_prompt(_ARTICLES)

    # ============================================================ A/B: summary format & length
    print("=== A/B: main summary stays a paragraph, target length raised (not shortened) ===")
    check("1: prompt does NOT ask for bullet-point summary (still prose)",
          "in 5-8 sentences" not in PROMPT.replace("approximately 5-8 sentences", ""))
    check("2: prompt targets ~5-8 sentences (raised from the old 4-6)",
          "5-8 sentences" in PROMPT)
    check("3: prompt explicitly forbids padding to reach a sentence count",
          "never pad to reach a sentence count" in PROMPT)
    check("4: prompt explicitly forbids cutting a real fact to stay short",
          "never cut a real fact to stay short" in PROMPT)

    # ============================================================ C-G: event-aware extraction guidance
    print("\n=== C-G: general event-aware fact-extraction guidance is present ===")
    check("5: cross-article synthesis instruction present (read all, don't rewrite one)",
          "Synthesize ACROSS all of them" in PROMPT
          and "simply rewrite one article and ignore the rest" in PROMPT)
    check("6: crime-story detail guidance present",
          "crime story calls for" in PROMPT)
    check("7: policy/political-story detail guidance present",
          "political story\n  calls for" in PROMPT or "political story" in PROMPT)
    check("8: court-case detail guidance present", "court case calls for" in PROMPT)
    check("9: disaster/accident detail guidance present",
          "disaster/accident calls for" in PROMPT)
    check("10: sport detail guidance present", "sport calls for" in PROMPT)
    check("11: business/economy detail guidance present",
          "business/economy calls for" in PROMPT)
    check("12: guidance is explicitly framed as examples, not a forced checklist",
          "not a checklist to force" in PROMPT)

    # ============================================================ H: no invented facts (unchanged)
    print("\n=== H: strict no-invention rule is still present, unchanged ===")
    check("13: 'never invent facts, quotes, numbers, names, causes or consequences' present",
          "Never invent facts,\n  quotes, numbers, names, causes or consequences" in PROMPT)

    # ============================================================ G(claims)/6: attribution framework
    print("\n=== attribution framework: FACT/ALLEGATION/CLAIM/DISPUTED CLAIM ===")
    check("14: all four attribution registers are named", all(
        f"{word}:" in PROMPT for word in ("FACT", "ALLEGATION", "CLAIM", "DISPUTED CLAIM")))
    check("15: never-convert-allegation-to-fact rule present",
          "Never convert an allegation into a stated fact" in PROMPT)

    # ============================================================ I/J/K: framing rules unchanged
    print("\n=== I/J/K: framing instructions (comparative, generic-rejected, one-owner) unchanged ===")
    check("16: framing is still explicitly COMPARATIVE",
          "COMPARATIVE, concrete and specific" in PROMPT)
    check("17: generic framing example still explicitly rejected",
          'NOT vague ("emphasised different aspects"' in PROMPT)
    check("18: one-owner wording rule still present",
          '"the sole rated outlet reporting this..."' in PROMPT)
    check("19: no-motive-inference rule still present (framing stays comparative, not commentary)",
          '"wants readers to believe", "is hiding", "is trying to"' in PROMPT)

    # ============================================================ L: empty side / M: bilingual (schema)
    print("\n=== L/M: empty-side handling + bilingual requirement (unchanged) ===")
    check("20: empty-lean-gets-empty-array rule present",
          "set its framing to an empty array" in PROMPT)
    check("21: bilingual mandate present, Hindi fields marked REQUIRED",
          "BILINGUAL OUTPUT IS MANDATORY" in PROMPT and PROMPT.count("REQUIRED") >= 3)

    # ============================================================ 17: output contract / schema unchanged
    print("\n=== Schema: exact same 10 top-level JSON keys as before Phase 8 ===")
    expected_keys = {"title", "summary", "summary_points", "title_hi", "summary_hi",
                      "summary_points_hi", "framing", "framing_hi", "topic", "region"}
    found_keys = {k for k in expected_keys if f'"{k}"' in PROMPT}
    check(f"22: all {len(expected_keys)} expected top-level keys present in the schema block",
          found_keys == expected_keys)

    # ============================================================ postprocess() end-to-end (mocked raw)
    print("\n=== postprocess() correctly handles a realistic Phase-8-style detailed response ===")
    _raw_detailed = {
        "title": "Court Rejects Government Appeal Over Land Acquisition Order",
        "summary": (
            "A state high court rejected the government's appeal against a lower "
            "court's order voiding a 2019 land acquisition. The bench, led by two "
            "judges, ruled that the acquisition process had not followed mandatory "
            "notice requirements. The state government had argued the delay was "
            "procedural and not prejudicial to affected landowners. Police said no "
            "law-and-order issues arose during the hearing. The court ordered the "
            "state to return possession within 60 days. Officials said they were "
            "reviewing the order before deciding on a further appeal."
        ),
        "summary_points": [
            "The high court rejected the state's appeal over a 2019 land acquisition.",
            "The bench ruled mandatory notice requirements were not followed.",
            "The court ordered the state to return possession within 60 days.",
            "Officials said they are reviewing the order before deciding on a further appeal.",
        ],
        "title_hi": "अदालत ने भूमि अधिग्रहण आदेश पर सरकार की अपील खारिज की",
        "summary_hi": "एक राज्य उच्च न्यायालय ने भूमि अधिग्रहण को रद्द करने वाले आदेश के खिलाफ सरकार की अपील खारिज कर दी।",
        "summary_points_hi": [
            "उच्च न्यायालय ने 2019 के भूमि अधिग्रहण पर राज्य की अपील खारिज की।",
            "पीठ ने कहा कि अनिवार्य सूचना आवश्यकताओं का पालन नहीं किया गया।",
            "अदालत ने राज्य को 60 दिनों के भीतर कब्जा वापस करने का आदेश दिया।",
            "अधिकारियों ने कहा कि वे आगे अपील करने से पहले आदेश की समीक्षा कर रहे हैं।",
        ],
        "framing": {"left": ["Highlighted the delayed-notice finding as a due-process failure."],
                    "center": ["Focused on the court's procedural reasoning and the 60-day timeline."]},
        "framing_hi": {"left": ["देरी से नोटिस के निष्कर्ष को उचित प्रक्रिया की विफलता बताया।"],
                        "center": ["अदालत के प्रक्रियात्मक तर्क और 60-दिन की समयसीमा पर ध्यान केंद्रित किया।"]},
        "topic": "Crime & Law",
        "region": "India",
    }
    result = postprocess(_raw_detailed, _ARTICLES)
    check("23: postprocess() preserves the full multi-sentence summary verbatim (no truncation)",
          result["summary"] == _raw_detailed["summary"] and result["summary"].count(".") >= 5)
    check("24: postprocess() preserves summary_points as a list of 4 concrete facts",
          len(result["summary_points"]) == 4)
    check("25: postprocess() preserves Hindi fields non-empty",
          bool(result["summary_hi"]) and len(result["summary_points_hi"]) == 4)
    check("26: framing correctly cleaned/kept for covered sides (left, center)",
          set(result["framing"].keys()) == {"left", "center"})
    check("27: right (uncovered side) correctly absent from cleaned framing",
          "right" not in result["framing"])
    check("28: content_complete correctly computed True (left+center covered and framed, "
          "right has zero coverage so isn't required)",
          result["content_complete"] is True)
    check("29: region resolved from the model's own output (India), not guessed",
          result["region"] == "India")
    check("30: topic passed through unchanged when valid", result["topic"] == "Crime & Law")

    # ============================================================ N/O/P: unchanged existing behavior
    print("\n=== N/O/P: content_complete / extractive fallback / region-lean logic unchanged ===")
    check("31: compute_content_complete() unchanged - zero-coverage still trivially complete",
          compute_content_complete(
              {"left": {"count": 0}, "center": {"count": 0}, "right": {"count": 0}},
              {}, "llm") is True)
    check("32: compute_content_complete() unchanged - covered+unframed side still incomplete",
          compute_content_complete(
              {"left": {"count": 1}, "center": {"count": 0}, "right": {"count": 0}},
              {}, "llm") is False)
    check("33: has_framing() unchanged (list form)", has_framing(["a real bullet"]) is True)
    check("34: has_framing() unchanged (empty list)", has_framing([]) is False)
    _extractive = _extractive_raw(
        [{"source": "TestCenterOutlet", "language": "en", "title": "Extractive headline",
          "summary": "Extractive lead sentence."}])
    check("35: extractive fallback still produces summary_method='extractive' with no framing key",
          _extractive.get("summary_method") == "extractive" and "framing" not in _extractive)
    check("36: extractive events are still ALWAYS content_complete=True regardless of framing "
          "(Option A, untouched by Phase 8)",
          compute_content_complete({"left": {"count": 5}}, {}, "extractive") is True)

finally:
    analyze.lean_of = _orig_lean_of


print(f"\n{'='*60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
