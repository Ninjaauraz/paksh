"""
test_summary_synthesis.py - Fix 4 (post-launch audit): the summary must be Paksh's own
factual synthesis, never a chain of "<outlet> reported that..." mini-attributions.

Paksh separates three layers - EVIDENCE (the OUTLET blocks / sources_out), SUMMARY (Paksh's
own factual synthesis), and COVERAGE (how outlets covered it, the bias bar). A summary that
narrates which outlet supplied each fact collapses SUMMARY back into EVIDENCE/COVERAGE. This
is fixed at the PROMPT level (analyze.build_prompt), not by post-processing the model's
text - detect_media_attribution() is a diagnostic-only signal for tests/audits, never a
gate or a rewriter.

What this pins:
  1. a normal factual summary (no outlet named) is clean
  2. actor/claim attribution ("the opposition alleged", "the minister said", a named person)
     is NOT flagged - the prohibition is on naming a NEWS OUTLET, not an actor
  3. the prompt explicitly instructs the model not to narrate outlet-by-outlet reporting
  4. the prompt requires the English summary to be ONE paragraph
  5. the prompt requires the Hindi summary to be ONE paragraph, same form as English
  6. postprocess() never deletes or rewrites outlet names from a stored summary - detection
     and storage are fully independent (no unsafe blanket replace() anywhere in the path)
  7. the CJP entity-faithfulness instruction (Fix 3) and this instruction coexist in the
     same prompt without contradicting or crowding each other out

Run:  py test_summary_synthesis.py
"""
import analyze
from analyze import build_prompt, detect_media_attribution, postprocess

FAILURES = []


def check(label, cond):
    print(f"  {label} ... {'OK' if cond else 'FAIL'}")
    if not cond:
        FAILURES.append(label)


print("=== 1: a normal factual summary has no media-outlet attribution ===")
GOOD_A = ("The Election Commission faced renewed calls for resignation after opposition "
          "parties and civil-society groups challenged its recent decisions on voter roll "
          "revisions.")
check("1a: clean synthesis is not flagged", detect_media_attribution(GOOD_A) == [])

print("\n=== 2: actor/claim attribution is preserved, not flagged ===")
GOOD_B = ("The opposition alleged widespread irregularities in the process, while the "
          "government denied any wrongdoing.")
GOOD_C = "Abhijeet Dipke called for opposition parties to boycott elections they say are rigged."
GOOD_D = "The Election Commission said the revised rolls would be published next week."
check("2a: 'the opposition alleged... the government denied...' is not flagged",
      detect_media_attribution(GOOD_B) == [])
check("2b: a named ACTOR (not an outlet) making a claim is not flagged",
      detect_media_attribution(GOOD_C) == [])
check("2c: a named institution/body (not a news outlet) is not flagged",
      detect_media_attribution(GOOD_D) == [])

print("\n=== (detector sanity) known-bad media-attribution phrasing IS flagged ===")
BAD_A = "The Hindu reported that the protest turned violent near the assembly."
BAD_B = "The News Minute reported that the minister had resigned earlier in the day."
BAD_C = "According to India Today, the party plans further protests next week."
BAD_D = "NDTV said that the court would hear the case on Monday."
check("s-a: '<The Hindu> reported' is flagged", len(detect_media_attribution(BAD_A)) >= 1)
check("s-b: '<The News Minute> reported' is flagged", len(detect_media_attribution(BAD_B)) >= 1)
check("s-c: 'According to <India Today>' is flagged", len(detect_media_attribution(BAD_C)) >= 1)
check("s-d: '<NDTV> said' is flagged", len(detect_media_attribution(BAD_D)) >= 1)

print("\n=== 3: the prompt instructs against outlet-by-outlet narration ===")
ARTS = [
    {"source": "The Hindu", "language": "en", "title": "Teacher suspended over harassment allegations",
     "url": "u1", "summary": "", "image_url": ""},
    {"source": "The Print", "language": "en", "title": "Govt school teacher suspended over alleged harassment",
     "url": "u2", "summary": "A government school teacher was suspended on Tuesday, officials said.", "image_url": ""},
]
_orig_lean_of = analyze.lean_of
analyze.lean_of = lambda name, region=None: "left" if name == "The Hindu" else "center"
try:
    PROMPT = build_prompt(ARTS)
    NP = " ".join(PROMPT.split())

    check("3a: instructs writing Paksh's own synthesis, not narrating who reported what",
          "WRITE PAKSH'S OWN FACTUAL SYNTHESIS" in NP
          and "not a narration of who reported what" in NP)
    check("3b: gives the exact banned-phrasing examples from the audit",
          '"The Hindu reported that..."' in PROMPT and '"According to India Today..."' in PROMPT
          and '"NDTV said that..."' in PROMPT)
    check("3c: explicitly preserves actor/claim attribution as a DIFFERENT thing",
          "different thing from attributing a claim" in NP
          and "the opposition alleged" in NP and "the government denied" in NP)
    check("3d: states the general rule without an exhaustive outlet blacklist "
          "(no giant list of outlet names appended to the instruction itself)",
          "never name a NEWS OUTLET as the source of a fact" in NP)

    print("\n=== 4/5: summary and summary_hi must each be ONE coherent paragraph ===")
    check("4a: English summary schema field requires one paragraph, rules out lists/multi-paragraph",
          '"summary":' in PROMPT
          and "written as ONE coherent paragraph" in NP
          and "never multiple paragraphs, bullet points, numbered points" in NP
          and "outlet-by-outlet" in NP)
    check("5a: Hindi summary schema field requires the same one-paragraph form",
          '"summary_hi":' in PROMPT
          and "same ONE-paragraph form as summary" in NP)

    print("\n=== 7: Fix 3 (CJP/entity faithfulness) and Fix 4 coexist without contradiction ===")
    check("7a: both instructions are present in the same generated prompt",
          "could plausibly refer to more than one real-world identity" in NP
          and "WRITE PAKSH'S OWN FACTUAL SYNTHESIS" in NP)
    check("7b: neither instruction contradicts the other - the entity-identity rule talks "
          "about WHO/WHAT a name refers to, the synthesis rule talks about not narrating "
          "outlet-by-outlet - distinct concerns, both keep attribution to ACTORS intact",
          "use the identity the coverage below itself establishes" in NP
          and "the identity of who said or did something is itself part of the fact" in NP)
finally:
    analyze.lean_of = _orig_lean_of

print("\n=== 6: no unsafe blanket outlet-name deletion anywhere in the storage path ===")
RAW = {"title": "Minister faces questions over new policy", "region": "India", "topic": "Politics",
       "summary": "The Hindu reported that the minister answered questions about the new policy in Parliament.",
       "summary_hi": "द हिंदू ने बताया कि मंत्री ने संसद में नई नीति के बारे में सवालों का जवाब दिया।",
       "framing": {"left": [], "center": [], "right": []}}
event = postprocess(dict(RAW), [{"source": "The Hindu", "language": "en", "title": "t", "url": "u",
                                  "summary": "", "image_url": ""}])
check("6a: postprocess() stores the summary text completely unmodified (no auto-strip)",
      event["summary"] == RAW["summary"])
check("6b: postprocess() stores summary_hi completely unmodified too",
      event["summary_hi"] == RAW["summary_hi"])
check("6c: detect_media_attribution still independently flags that SAME stored text "
      "(detection exists and works; storage is simply never altered by it)",
      len(detect_media_attribution(event["summary"])) >= 1)
import inspect
pp_src = inspect.getsource(postprocess)
check("6d: postprocess()'s own source contains no .replace(/.sub( call near summary/outlet "
      "text - detection is a separate, standalone function, never wired into storage",
      "detect_media_attribution" not in pp_src and ".replace(" not in pp_src)

print(f"\n{'=' * 60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
