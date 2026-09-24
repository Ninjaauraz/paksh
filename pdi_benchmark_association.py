"""
pdi_benchmark_association.py - the REAL association gold set (association-fix pass,
Part 10/11). NOT a pass/fail test - a REPORT, in the same spirit as the original
version of this file ("Do not change thresholds merely to make the benchmark pass").

WHY THIS VERSION EXISTS: the original 8-case synthetic benchmark (A-H, kept below
unchanged) measured 25% accuracy against the pre-fix associate_candidate(). The two
real Substack shadow experiments then measured the SAME pre-fix implementation
against genuine live discourse and found something worse: 0% DIRECT_EVENT/
RELATED_CONTEXT across 12 real stories, PLUS a distinct false-positive mechanism (the
same few generic Substack posts recurring as "BACKGROUND" matches across several
mutually unrelated real stories - root cause B in the association-fix report). This
version extends the gold set with the required adversarial cases (I-O) AND the exact
real recurring candidates from those experiments, so the fix is validated against
genuine failure modes, not only hand-picked synthetic ones.

Every case is run TWICE:
  DET-only  - semantic_score=None (the literal fallback path when Ollama/bge-m3 is
              unavailable - see pdi_semantic.py). Pure lexical + entity specificity.
  HYBRID    - a REAL passage-level semantic score from pdi_semantic.py (genuine
              Ollama/bge-m3 calls, not a mock), when the backend is reachable in this
              environment. If it isn't, the HYBRID column reports SKIPPED, honestly,
              rather than a fabricated number - this file must not fail or lie just
              because Ollama isn't running wherever it's executed.

Run:  py pdi_benchmark_association.py
"""
from datetime import datetime, timedelta

import pdi
import pdi_semantic as ps

NOW = datetime(2026, 9, 24, 12, 0, 0)


def event_with_breadth(id_, title, breadth=8, topic="Economy", region="India"):
    e = {"id": id_, "title": title, "title_hi": "", "summary": "s", "summary_hi": "",
         "topic": topic, "region": region, "framing": {}}
    third = breadth // 3
    e["lean_counts"] = {"left": third, "center": breadth - 2 * third, "right": third}
    e["international"] = 0
    return e


def cand(title, body, provider="reddit", pid="c1", h_ago=2.0, language="en"):
    return pdi.Candidate(
        provider=provider, provider_item_id=pid, url=f"https://example.com/{pid}",
        canonical_url="", title=title, author="a",
        published_at=(NOW - timedelta(hours=h_ago)).isoformat(), language=language,
        discovery_query="q", discovery_rank=0, content_hash="", body_text=body,
    )


def profile_for(title, summary="s", topic="Economy", region="India", entities=None):
    event = event_with_breadth(1, title, topic=topic, region=region)
    event["summary"] = summary
    entities = entities if entities is not None else pdi._extract_entities(title)
    return pdi.DiscourseProfile(event_id=1, title=title, summary=summary, topic=topic,
                                region=region, core_entities=entities)


RBI_EVENT = event_with_breadth(500, "RBI Cuts Repo Rate by 25 Basis Points to Boost Slowing Growth")
RBI_EVENT["summary"] = ("The Reserve Bank of India's Monetary Policy Committee cut the benchmark repo "
                        "rate by 25 basis points, aiming to boost slowing economic growth.")
RBI_PROFILE = pdi.build_discourse_profile(RBI_EVENT, article_languages=["en", "en", "hi"])

# =====================================================================================
# Original 8 synthetic cases (A-H) - kept exactly as they were before the fix, so this
# file still shows the historical 25% baseline alongside the new numbers.
# =====================================================================================
CASES = [
    ("A. exact event wording", RBI_PROFILE, cand(
        "RBI cuts repo rate by 25 basis points to boost slowing growth",
        "The Reserve Bank of India cut the repo rate by 25 basis points to boost slowing growth.",
        h_ago=1), pdi.ASSOCIATION_DIRECT_EVENT),

    ("B. strong paraphrase, little lexical overlap", RBI_PROFILE, cand(
        "Central bank slashes borrowing costs in bid to revive a sluggish economy",
        "The monetary authority lowered its benchmark lending price, hoping to jump-start a "
        "flagging domestic output picture that has worried policymakers for months.",
        h_ago=2), pdi.ASSOCIATION_DIRECT_EVENT),

    ("C. same topic, different event", RBI_PROFILE, cand(
        "Federal Reserve holds interest rates steady amid inflation concerns",
        "The US Federal Reserve kept its benchmark interest rate unchanged today, citing "
        "persistent inflation concerns across the American economy.",
        h_ago=3), pdi.ASSOCIATION_UNRELATED),

    ("D. old contextual article", RBI_PROFILE, cand(
        "RBI's historical rate cut cycle since 2019 explained",
        "The RBI has cut the repo rate multiple times since 2019 as part of a broader "
        "monetary easing cycle affecting growth and inflation over several years.",
        h_ago=24 * 200), pdi.ASSOCIATION_RELATED_CONTEXT),

    ("E. generic commentary", RBI_PROFILE, cand(
        "Why central banks matter for everyday people",
        "Central banks around the world influence everyday life through interest rates, "
        "inflation control, and monetary policy in ways most people never think about.",
        h_ago=5), pdi.ASSOCIATION_BACKGROUND),

    ("F. same entities, wrong event", RBI_PROFILE, cand(
        "RBI governor inaugurates new regional office building in Mumbai",
        "The RBI governor today inaugurated a new regional office building in Mumbai, "
        "highlighting the central bank's expansion plans for the region.",
        h_ago=2), pdi.ASSOCIATION_BACKGROUND),

    ("G. direct event, different terminology", RBI_PROFILE, cand(
        "Reserve Bank of India trims key lending rate to spur economic activity",
        "The Reserve Bank of India trimmed its key lending rate today in a move aimed at "
        "spurring broader economic activity across the country.",
        h_ago=1.5), pdi.ASSOCIATION_DIRECT_EVENT),

    ("H. regional-language (Hindi) equivalent", RBI_PROFILE, cand(
        "आरबीआई ने रेपो दर में 25 आधार अंकों की कटौती की",
        "रिज़र्व बैंक ऑफ इंडिया ने आर्थिक वृद्धि को बढ़ावा देने के लिए रेपो दर में 25 आधार अंकों की कटौती की।",
        h_ago=1, language="hi"), pdi.ASSOCIATION_DIRECT_EVENT),
]

# =====================================================================================
# Required additional adversarial cases (association-fix pass, Part 11: I/J/K/N/O) and
# the required real-value stress test (M: the same generic article recurring across
# several unrelated events). L (multilingual) is exercised structurally by H above and
# by a second, harder multilingual paraphrase case here.
# =====================================================================================
_kyiv_profile = profile_for("India offers to help resolve Russia-Ukraine conflict during Kyiv visit",
                            "Indian External Affairs Minister S. Jaishankar visited Kyiv and met with "
                            "Ukrainian President Volodymyr Zelensky.", topic="Politics")
CASES.append(("I. long-form article, sparse event references (REAL: the Russia-sanctions Substack "
              "candidate from the shadow experiment)", _kyiv_profile, cand(
    "#362 The Powers and Limits of Charismatic Authority",
    "Global Policy Watch: Charisma Ka Karishma. There are two scenes from Hindi cinema that I go back to "
    "when I think about charisma. Weber's typology of authority remains a useful lens for modern populism. "
    "This week also saw the Sanctioning Russia Act of 2026 move forward in the US Congress, which would "
    "penalize countries continuing to import Russian oil - a live concern for India's own diplomatic "
    "balancing act between Moscow and Kyiv as it looks for a mediating role. Meanwhile domestic politics "
    "saw its own charismatic-authority dynamics play out in state elections.",
    h_ago=24 * 3), pdi.ASSOCIATION_RELATED_CONTEXT))

_karnataka_profile = profile_for("Karnataka launches plan to cut salt intake by 30 percent by 2030",
                                 "The Karnataka health department announced a new public health "
                                 "initiative targeting sodium consumption.", topic="Health")
CASES.append(("J. event named only in the title", _karnataka_profile, cand(
    "Karnataka's new salt reduction plan, explained",
    "A quick breakdown of what the scheme covers and how it compares to similar programs in other "
    "states, and what public health researchers make of the approach so far.",
    h_ago=48), pdi.ASSOCIATION_DIRECT_EVENT))
CASES.append(("K. event mentioned only in the body, not the title", _karnataka_profile, cand(
    "Field notes from the health beat",
    "A few things caught my eye this month. First, hospital staffing shortages continue in several "
    "districts. Second, and this is the one worth watching, Karnataka just launched a genuinely "
    "ambitious plan to cut population salt intake by 30 percent by 2030, one of the more concrete "
    "state-level public health targets I've seen in years. Third, vaccine cold-chain logistics remain "
    "a persistent headache nationwide.",
    h_ago=24 * 5), pdi.ASSOCIATION_DIRECT_EVENT))

_naxal_profile = profile_for("NIA Court Convicts 10 in 2013 Jhiram Valley Naxal Attack Case",
                             "A National Investigation Agency special court has convicted all 10 "
                             "accused in the 2013 Jhiram Valley Naxal attack case.", topic="Crime & Law")
CASES.append(("M1. REAL recurring generic post, event #1 (Naxal conviction) - the exact "
              "India Judiciary Watch digest misapplied as BACKGROUND in the shadow experiment",
              _naxal_profile, cand(
    "India Judiciary Watch: Weekly Digest (7th-12th September 2026)",
    "Between 7th and 12th September, the Supreme Court and several High Courts dealt with a wide "
    "spread of matters spanning environmental deadlines, press freedom, and protest-related litigation.",
    h_ago=24 * 8), pdi.ASSOCIATION_UNRELATED))

_nandigram_profile = profile_for("Nandigram Bypoll: Congress Candidate Arrested After Mamata's Support",
                                 "In Nandigram, West Bengal, Congress candidate Milan Pradhan was "
                                 "arrested hours after Mamata Banerjee's support.", topic="Politics")
_oil_profile = profile_for("India's Crude Oil Price Surges Amid Global Supply Concerns",
                           "India's crude oil import price has reached a five-month high, reportedly "
                           "hitting $131 per barrel.", topic="Economy")
_dengue_profile = profile_for("Dr. Reddy's to distribute Takeda's dengue vaccine in India from 2027",
                              "Dr. Reddy's Laboratories has partnered with Takeda to distribute a "
                              "dengue vaccine in India.", topic="Health")
_gdp_debate_post = cand(
    "#360 Grossly Debated Parameter",
    "On the GDP Debate and India's Semicon 2.0. This issue covers the ongoing dispute over how India "
    "measures GDP growth and the second phase of the semiconductor manufacturing incentive.",
    h_ago=24 * 17)
CASES.append(("M2. REAL recurring generic post, event #2 (Nandigram bypoll) - the exact candidate "
              "that attached itself as BACKGROUND to 4 mutually unrelated real stories",
              _nandigram_profile, _gdp_debate_post, pdi.ASSOCIATION_UNRELATED))
CASES.append(("M3. REAL recurring generic post, event #3 (crude oil price surge)",
              _oil_profile, _gdp_debate_post, pdi.ASSOCIATION_UNRELATED))
CASES.append(("M4. REAL recurring generic post, event #4 (dengue vaccine)",
              _dengue_profile, _gdp_debate_post, pdi.ASSOCIATION_UNRELATED))

_inflation_profile = profile_for("Food Inflation May Increase Due to High Prices",
                                 "Food inflation is projected to rise further due to elevated prices "
                                 "of essential food items.", topic="Economy")
CASES.append(("N. specialist analysis adding an implication, not repeating the event", _inflation_profile, cand(
    "What sticky food inflation means for rate policy",
    "If food price pressure persists into next quarter, the central bank's room to cut rates further "
    "will likely narrow considerably, since food carries a heavy weight in the consumer price index "
    "used for policy decisions.",
    h_ago=24 * 2), pdi.ASSOCIATION_RELATED_CONTEXT))

CASES.append(("O. breaking news, sparse context (published same day)", _naxal_profile, cand(
    "BREAKING: convictions in Jhiram Valley case",
    "Just in: an NIA special court has convicted all 10 accused in the long-running 2013 Jhiram "
    "Valley Naxal attack case. More details as we get them.",
    h_ago=0.5), pdi.ASSOCIATION_DIRECT_EVENT))

# =====================================================================================
# Case P/N-real: the EXACT real event 18569 / India Judiciary Watch pairing from the
# real 12-story shadow experiment (hardening-pass Finding F) - a broad weekly digest
# that scored semantic=0.626 (barely above SEM_RELATED_MIN=0.62) and was promoted to
# RELATED_CONTEXT/SELECTED, but does not substantively discuss the specific event; its
# winning passage was a generic "wide spread of matters" summary sentence, and
# extraction pulled observations about a completely different, unrelated court matter
# from elsewhere in the same digest. This is the direct regression test for the
# corroboration-margin fix (Part 11) and the passage-localization fix (Finding F).
# =====================================================================================
_sc_judge_profile = profile_for("Supreme Court Judge Criticizes Police Action Against Protesters",
                                "A Supreme Court judge expressed strong disapproval of police actions "
                                "against protesters.", topic="Crime & Law")
CASES.append(("P. REAL broad weekly digest, marginal semantic score, no event-specific corroboration "
              "(the exact event 18569 / India Judiciary Watch pairing)", _sc_judge_profile, cand(
    "India Judiciary Watch: Weekly Digest Of Key Legal Developments (07th September - 12th September, 2026)",
    "Between 7th and 12th September, the Supreme Court and several High Courts dealt with a wide spread "
    "of matters spanning environmental deadlines, press freedom, and protest-related litigation. The "
    "Supreme Court rejected the Centre's request for a six-month extension on the Aravalli Hills expert "
    "panel report, setting a 30th November deadline instead, and asked UP Police why an X account's "
    "information was needed in the road-rage FIR against journalist Abhishek Upadhyay.",
    h_ago=24 * 8), pdi.ASSOCIATION_BACKGROUND))


def main():
    semantic_available = ps.is_available()
    print(f"pdi_semantic backend available in this environment: {semantic_available}\n")
    print(f"{'case':<95} {'expected':<16} {'DET-only':<10} {'HYBRID':<10}")
    print("-" * 135)
    n_det_ok = n_hyb_ok = n_hyb_run = 0
    per_class_det = {}
    for row in CASES:
        label, profile, c, expected = row
        det = pdi.associate_candidate(c, profile, NOW)
        det_ok = det.association == expected
        n_det_ok += det_ok
        per_class_det.setdefault(expected, [0, 0])
        per_class_det[expected][1] += 1
        per_class_det[expected][0] += det_ok

        if semantic_available:
            event_text = f"{profile.title}. {profile.summary}"
            cand_text = f"{c.title}. {c.body_text}"
            result = ps.score_candidates(event_text, [("x", cand_text)]).get("x")
            sem = result["score"] if result else None
            passage = " ".join(result["passages"]) if result and result["passages"] else None
            hyb = pdi.associate_candidate(c, profile, NOW, semantic_score=sem, relevant_passage=passage)
            hyb_ok = hyb.association == expected
            n_hyb_ok += hyb_ok
            n_hyb_run += 1
            hyb_str = ("OK" if hyb_ok else "MISS") + f" ({hyb.association})"
            if hyb.quality_status == pdi.QUALITY_SELECTED:
                obs = pdi.extract_observations(hyb)
                print(f"    [SELECTED] passage={passage[:150]!r}" if passage else "    [SELECTED] (no passage - whole document used)")
                for o in obs:
                    print(f"      -> [{o.observation_type}] {o.text!r}")
        else:
            hyb_str = "SKIPPED"

        print(f"{label[:95]:<95} {expected:<16} "
              f"{('OK' if det_ok else 'MISS') + ' (' + det.association + ')':<24} {hyb_str}")

    print("-" * 135)
    print(f"\nDET-only accuracy (deterministic fallback path): {n_det_ok}/{len(CASES)} "
          f"({100*n_det_ok/len(CASES):.0f}%)")
    print("DET-only accuracy by expected class:")
    for cls, (c, n) in per_class_det.items():
        print(f"  {cls:<16} {c}/{n}")
    if n_hyb_run:
        print(f"\nHYBRID accuracy (real Ollama/bge-m3 semantic scoring): {n_hyb_ok}/{n_hyb_run} "
              f"({100*n_hyb_ok/n_hyb_run:.0f}%)")
    else:
        print("\nHYBRID accuracy: SKIPPED entirely (pdi_semantic backend not reachable in this "
              "environment) - this is the honest 'semantic infrastructure unavailable' case; "
              "DET-only numbers above are what production would fall back to.")


if __name__ == "__main__":
    main()
