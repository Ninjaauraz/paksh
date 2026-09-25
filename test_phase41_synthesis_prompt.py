"""
test_phase41_synthesis_prompt.py - Paksh 41.4: evidence-bounded story synthesis.

Phase 41.4 rewrote ONLY the synthesis instructions inside analyze.build_prompt() and
dropped `summary_points` / `summary_points_hi` from the schema the model is asked for.
Nothing else changed: attribution registers, neutrality core, framing block, bilingual
rule, topic/region, postprocess(), content_complete, publication gating.

What this suite pins (no LLM call, no network, no paksh.db - articles carry no "id", so
build_prompt's optional enrichment lookup returns immediately):
  A. The new synthesis contract is in the prompt (no length target; thin-input rule;
     never describe what the coverage "lacks"; grounded context/significance; no
     interpretive filler; names/details exactly as given; conflicts without naming outlets).
  B. Every strength the audit wanted preserved is still there, and the FRAMING block is
     byte-for-byte what it was before this phase (hash pinned).
  C. The schema asks for the 8 keys, not summary_points/_hi.
  D. Downstream tolerance: a model response WITHOUT summary_points still postprocesses,
     is never marked degraded, keeps content_complete semantics, and legacy stored
     summary_points pass through untouched; the feed/backfill/export helpers accept the
     absent field.

Run:  py test_phase41_synthesis_prompt.py
"""
import hashlib

import analyze
from analyze import build_prompt, postprocess

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


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
    NP = " ".join(PROMPT.split())          # the prompt hard-wraps its lines

    print("=== A: the new synthesis contract is in the prompt ===")
    check("1: no fixed sentence/length target (5-8 gone, 'no target length' present)",
          "5-8" not in PROMPT and "There is no target length and no fixed number of sentences" in NP)
    check("2: depth follows evidence in BOTH directions (short for headlines, full for rich detail)",
          "Headlines alone support a short account" in NP
          and "use it, so that a reader comes away understanding the event" in NP)
    check("3: thin-material rule present",
          "THIN MATERIAL" in NP and "state only what is directly stated there and stop" in NP)
    check("4: never describe what the coverage lacks (with the banned phrasings named)",
          "NEVER DESCRIBE WHAT THE COVERAGE LACKS" in NP
          and "details were not provided" in NP and "it is unclear from the reports" in NP)
    check("5: absence may be stated only when a source itself says so, attributed",
          "only when a source in the coverage itself says so" in NP)
    check("6: chronology/context only when the supplied material states it",
          "include background, earlier developments or chronology when the supplied material itself states them" in NP
          and "Do not add background from your own knowledge" in NP)
    check("7: significance only when the reporting says so, attributed",
          "say why the story matters only when the reporting itself says so" in NP)
    check("8: interpretive filler is ruled out (highlights/underscores/signals/aims to...)",
          "NO INTERPRETIVE FILLER" in NP and '"highlights"' in NP and '"underscores"' in NP
          and '"aims to"' in NP)
    check("9: names/details exactly as the coverage gives them (no first names/company names from memory)",
          "USE THE COVERAGE'S OWN WORDS FOR NAMES AND DETAILS" in NP
          and "from your own knowledge" in NP)
    check("10: concrete details (dates, amounts, names, counts) must be kept",
          "never drop a name, figure or date that is there" in NP)
    check("11: conflicts are described by claim, never by naming the publications",
          "never by naming the publications that reported each version" in NP)
    check("12: schema summary line: no padding / no commentary / no statement about what coverage lacks",
          "no padding, no interpretive commentary, no statement about what the coverage does not say, no publication named" in NP)

    print("\n=== B: strengths preserved; framing block untouched ===")
    check("13: all five attribution registers still named", all(
        f"{w}:" in PROMPT for w in ("FACT", "ALLEGATION", "CLAIM", "DISPUTED CLAIM", "IDENTITY LABEL")))
    check("14: never-convert-allegation, no-invention and no-verdict rules still present",
          "Never convert an allegation into a stated fact" in NP
          and "Never invent facts, quotes, numbers, names, causes or consequences" in NP
          and "Give NO verdict on who is right" in NP)
    check("15: still forbids naming publications and forced cross-lean differences",
          "must NOT name individual publications" in NP
          and "Do NOT manufacture a difference that is not in the text" in NP)
    check("16: story-type adaptation guidance still present (crime/court/sport/business...)",
          all(k in NP for k in ("a crime story calls for", "a court case calls for", "sport calls for",
                                "business/economy calls for", "not a checklist to force")))
    fr_a = PROMPT.index("FRAMING - a per-side BULLET SUMMARY")
    fr_b = PROMPT.index("BILINGUAL OUTPUT IS MANDATORY")
    framing_hash = hashlib.sha256(PROMPT[fr_a:fr_b].encode("utf-8")).hexdigest()
    check("17: FRAMING block is byte-identical to the pre-Phase-41.4 prompt (sha256 pinned)",
          framing_hash == "af7d1411d473b62d8d3cbb3c3c3f8d957470ccf59e1f0a50261a63f03ce945cb")
    check("18: bilingual mandate still marks the Hindi title/summary/framing REQUIRED",
          "BILINGUAL OUTPUT IS MANDATORY" in PROMPT and PROMPT.count("REQUIRED") >= 3
          and "(title_hi, summary_hi, and each side of framing_hi)" in NP)

    print("\n=== C: schema ===")
    keys = {"title", "summary", "title_hi", "summary_hi", "framing", "framing_hi", "topic", "region"}
    check("19: the 8 keys are all requested", all(f'"{k}"' in PROMPT for k in keys))
    check("20: summary_points / summary_points_hi are NOT requested anywhere in the prompt",
          "summary_points" not in PROMPT)
    check("21: counts line and coverage blocks still rendered",
          "LEFT: 1 owner(s) - CENTRE: 1 owner(s) - RIGHT: 0 owner(s)" in PROMPT
          and "OUTLET: The Hindu" in PROMPT and "OUTLET: The Print" in PROMPT)

    print("\n=== D: downstream tolerance for a response without summary_points ===")
    new_raw = {
        "title": "Ramban Teacher Suspended After Harassment Allegation",
        "summary": "A government school teacher in Ramban has been suspended after an allegation of harassment by a student.",
        "title_hi": "रामबन में शिक्षक निलंबित", "summary_hi": "रामबन के एक सरकारी स्कूल के शिक्षक को निलंबित किया गया है।",
        "framing": {"left": ["Led with the suspension."], "center": ["Led with the allegation."]},
        "framing_hi": {"left": ["निलंबन को प्रमुखता दी।"], "center": ["आरोप को प्रमुखता दी।"]},
        "topic": "Crime & Law", "region": "India",
    }
    res = postprocess(dict(new_raw), [dict(a) for a in ARTS])
    check("22: postprocess() accepts the new shape; summary_points/_hi are stored as empty lists",
          res["summary_points"] == [] and res["summary_points_hi"] == [])
    check("23: an event with a title+summary and no points is NOT degraded", res["degraded"] is False)
    check("24: framing, Hindi, topic, region and summary pass through unchanged",
          res["summary"] == new_raw["summary"] and res["summary_hi"] == new_raw["summary_hi"]
          and res["topic"] == "Crime & Law" and res["region"] == "India"
          and set(res["framing"]) == {"left", "center"})
    check("25: content_complete is still decided ONLY by framing (True here: left+center framed)",
          res["content_complete"] is True)
    no_frame = dict(new_raw); no_frame["framing"] = {"left": ["x"]}
    check("26: content_complete still False when a covered side lacks framing (semantics unchanged)",
          postprocess(no_frame, [dict(a) for a in ARTS])["content_complete"] is False)
    legacy = dict(new_raw); legacy["summary_points"] = ["stored point"]; legacy["summary_points_hi"] = ["संग्रहीत बिंदु"]
    lres = postprocess(legacy, [dict(a) for a in ARTS])
    check("27: legacy stored summary_points / _hi still pass through verbatim",
          lres["summary_points"] == ["stored point"] and lres["summary_points_hi"] == ["संग्रहीत बिंदु"])
    check("28: degraded still means 'no title, no summary and no points'",
          postprocess({}, [dict(a) for a in ARTS])["degraded"] is True)

    import export_static
    row = export_static._lighten(dict(res))
    check("29: export_static._lighten() (feed row) accepts an event with no points",
          "summary_points" not in row and "summary_points_hi" not in row and row["summary"])
    import backfill_hindi
    check("30: backfill_hindi._needs_hi() / _prompt() handle an event with no points",
          backfill_hindi._needs_hi({"title": "T", "title_hi": "", "summary": "S", "summary_hi": ""}) is True
          and backfill_hindi._needs_hi(dict(res)) is False
          and backfill_hindi._prompt(dict(res)))
    ex = analyze._extractive_raw([dict(a) for a in ARTS])
    check("31: the extractive fallback is unchanged (still 'extractive', still no framing key)",
          ex.get("summary_method") == "extractive" and "framing" not in ex)

    print("=== E: general entity-faithfulness instruction (post-launch CJP audit) ===")
    check("32a: instruction present - don't substitute a more familiar identity from "
          "background knowledge for an ambiguous acronym/organization/person/place",
          "could plausibly refer to more than one real-world identity" in NP
          and "never substitute a different, more familiar identity from your own general "
              "knowledge" in NP)
    check("32b: instruction tells the model to preserve ambiguity rather than guess "
          "when the evidence doesn't establish which identity is meant",
          "keep the reference as given rather than guessing" in NP)
    check("32d: the instruction lives in the STRICT NEUTRALITY / summary section, not "
          "inside the pinned FRAMING block",
          PROMPT.index("could plausibly refer to more than one real-world identity") < fr_a)
    check("32c: the instruction is general - no acronym dictionary, no story-specific "
          "mapping, no mention of any specific organization name",
          "Cockroach" not in PROMPT and "Citizens for Justice and Peace" not in PROMPT
          and "CJP" not in PROMPT)
finally:
    analyze.lean_of = _orig_lean_of


print(f"\n{'=' * 60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
