"""factuality_benchmark.py - PAKSH FACTUALITY BENCHMARK (Phase 12 of the Evidence
Acquisition + Factuality System audit). Read-only: reads real events/articles from
the production DB to freeze their evidence into fixtures; writes nothing back.

WHAT THIS FILE IS RIGHT NOW: a frozen set of benchmark CASES (real evidence + the
correct verdict a factuality checker should reach), not yet a pass/fail test suite -
Phases 2-11's evidence-acquisition/claim-extraction/consistency-check/verification
code is still in the design stage (see the audit conversation), so there is nothing
running to grade against for configurations B/C/D yet. This file is the fixture those
phases will be graded against once a prototype exists. Configuration A (today's
production pipeline, which has NO deterministic checks and NO verification pass -
confirmed absent by reading analyze.py/reframe.py) is checked against real published
output where a case has one.

Every case is labeled with its evidentiary status:
  REAL_VERIFIED   - a real Paksh event/article set, inspected directly; the expected
                    verdict is grounded in what the evidence actually says.
  REAL_NEGATIVE   - a real Paksh event that LOOKS like the user-reported failure
                    category by entity name alone, but on inspection is NOT an error:
                    included specifically to test that a checker does not produce a
                    FALSE POSITIVE against well-corroborated evidence.
  SYNTHETIC       - constructed evidence (not a real published Paksh story) used to
                    exercise a category no real corpus example was found for. Never
                    presented as something Paksh got wrong; it is a stress-test input.

Two categories in the user's requested list (Mamata Banerjee/Suvendu Adhikari CM
case; Australia rugby/cricket domain case) were reported by the user as CONFIRMED
Paksh failures. On investigation: the CM case is REAL_NEGATIVE (see case F1 below -
multiple independent major outlets corroborate the "CM Suvendu Adhikari" framing,
which is outside this assistant's knowledge-cutoff to independently contradict), and
no rugby/cricket-domain-confusion event was found anywhere in the corpus by keyword
search (so C2 below is SYNTHETIC, not a real incident). Per the user's own decision,
both anecdotes are being replaced with verifiable-signature cases as the benchmark
core, while remaining open to slotting in real story IDs if located later.

Run:  py factuality_benchmark.py     (prints each case + today's production status
      where checkable; does not fail the run - there is nothing to assert pass/fail
      against yet for the not-yet-built checker phases)
"""
import sqlite3
from pathlib import Path

DB_PATH = r"D:\Paksh_Data\database\paksh.db"


def _conn():
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA query_only = 1;")  # read-only: this file must never write to production
    con.row_factory = sqlite3.Row
    return con


def _event(conn, eid):
    r = conn.execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()
    return dict(r) if r else None


def _articles(conn, eid):
    return [dict(r) for r in conn.execute(
        "SELECT source, title, url FROM articles WHERE event_id=?", (eid,)).fetchall()]


# =====================================================================================
# BENCHMARK CASES
# =====================================================================================

CASES = [

    # ---- 1. Current/former office-holder (temporal-office) --------------------------
    {
        "id": "F1_office_holder_negative_control",
        "category": "current_vs_former_office_holder",
        "status": "REAL_NEGATIVE",
        "event_ids": [5405, 7676],
        "note": ("7+ independent outlets (Indian Express, Telegraph India, Pioneer, "
                 "Hindustan Times, Mint, The Hindu, Telangana Today) consistently call "
                 "Suvendu Adhikari 'West Bengal CM' across two separate clusters, with "
                 "Mamata Banerjee consistently framed as opposition/TMC in the SAME "
                 "articles. This is internally consistent, multi-source evidence, not a "
                 "detectable contradiction."),
        "check_type": "status",
        "evidence": [   # real headlines from events 5405/7676, pulled verbatim from the DB
            {"source": "The Indian Express", "text": "Won't use you for political interests: CM Suvendu Adhikari to West Bengal Civil Service officers"},
            {"source": "The Telegraph (India)", "text": "Bengal CM Suvendu Adhikari points lynch finger at 'moulobadis' in Baruipur"},
            {"source": "Republic World", "text": "Security Tightens Outside Mamata's Residence Ahead Of Her Baruipur Visit After Minor Girl's Rape, Murder"},
        ],
        "expected_verdict": "NO_FLAG",
        "why": ("A Phase-8 checker must NOT flag this: every source agrees, so there is "
                "no evidence-vs-evidence or evidence-vs-synthesis mismatch to detect. "
                "Flagging it would require overriding multi-source evidence with the "
                "checker's own background knowledge - exactly the failure mode Non-"
                "Negotiable Principle #2 forbids. This case exists to catch a checker "
                "that is too trigger-happy on entity+role co-occurrence alone."),
    },
    {
        "id": "F1b_office_holder_synthetic_positive",
        "category": "current_vs_former_office_holder",
        "status": "SYNTHETIC",
        "check_type": "status",
        "note": "Constructed to exercise the FORMER-labeled-as-CURRENT failure directly.",
        "evidence": [
            {"source": "Outlet A", "text": "Former Chief Minister Jane Doe, who left office "
             "in March after her party lost the state election, criticised the new "
             "government's budget on Tuesday."},
            {"source": "Outlet B", "text": "Ex-CM Jane Doe said the budget ignored rural "
             "healthcare, days after the new Chief Minister John Roe was sworn in."},
        ],
        "bad_synthesis": "Chief Minister Jane Doe criticised the new government's budget on Tuesday.",
        "expected_verdict": "FLAG:temporal_error",
        "why": ("Both evidence items explicitly use FORMER/EX- markers and name a "
                "DIFFERENT current office-holder (John Roe). The synthesis drops the "
                "FORMER marker and asserts CURRENT status for Jane Doe - a direct "
                "contradiction of what every source states, not an inference gap."),
    },

    # ---- 2. Domain confusion (rugby/cricket etc.) ------------------------------------
    {
        "id": "C1_domain_real_negative_control",
        "category": "domain_consistency",
        "status": "REAL_NEGATIVE",
        "check_type": "domain",
        "event_ids": [24446],
        "evidence": [   # real Reuters/AP text for story 24446, pulled verbatim from the DB
            {"source": "Reuters", "text": "Australia is set to play a one-off rugby test match against the new-look Springboks in Perth."},
            {"source": "Associated Press", "text": "Australia takes on the new-look Springboks in one-off rugby test in Perth."},
        ],
        "note": ("Real story: 'Australia faces Springboks in one-off rugby test'. "
                 "Evidence (Reuters, AP) uses rugby-only terms (test series, Springboks). "
                 "No cricket terms present anywhere in the real evidence or synthesis."),
        "expected_verdict": "NO_FLAG",
    },
    {
        "id": "C2_domain_synthetic_positive",
        "category": "domain_consistency",
        "status": "SYNTHETIC",
        "check_type": "domain",
        "note": ("No real rugby/cricket confusion event was found in the corpus by "
                 "keyword search across all events. This case reuses story 24446's REAL "
                 "evidence text but pairs it with a FABRICATED bad synthesis to test the "
                 "domain-consistency checker specifically."),
        "evidence": [
            {"source": "Reuters", "text": "Australia is set to play a one-off rugby test "
             "match against the new-look Springboks in Perth."},
            {"source": "Associated Press", "text": "Australia takes on the new-look "
             "Springboks in one-off rugby test in Perth."},
        ],
        "bad_synthesis": ("Australia will face the Springboks in a one-off cricket test "
                          "in Perth, with both sides looking to post a strong first innings."),
        "expected_verdict": "FLAG:domain_error",
        "why": ("Every evidence item uses rugby-domain terms (test match, Springboks-as-"
                "rugby-team) with zero cricket terms. The synthesis introduces 'innings' "
                "(cricket-only vocabulary) unsupported by any source - the domain-keyword "
                "lexicon catches this without needing to know the sport 'for real'."),
    },

    # ---- 3. Entity disambiguation (acronym collision) --------------------------------
    {
        "id": "E1_cjp_negative_control",
        "category": "entity_disambiguation",
        "status": "REAL_NEGATIVE",
        "event_ids": [4418, 8131, 8327],
        "note": ("'CJP' in this corpus consistently resolves to 'Cockroach Janta Party' "
                 "(a real satirical NEET-protest movement) across every real event found "
                 "by search. No second, conflicting real-world referent for 'CJP' was "
                 "found actually confused in the corpus."),
        "expected_verdict": "NO_FLAG",
    },
    {
        "id": "E1b_acronym_collision_synthetic",
        "category": "entity_disambiguation",
        "status": "SYNTHETIC",
        "check_type": "entity",   # routed to check_entity_ambiguity() (v2) instead of detect_conflicts()
        "note": "CJP is also a common abbreviation for 'Chief Justice of Pakistan' in South Asian reporting - constructed to test that a checker resolves the acronym from context rather than pattern-matching the letters alone.",
        "evidence": [
            {"source": "Outlet A", "text": "The Cockroach Janta Party (CJP) continued its "
             "sit-in at Jantar Mantar over the NEET paper leak."},
            {"source": "Outlet B", "text": "CJP Yahya Afridi swore in two new judges to the "
             "Supreme Court of Pakistan on Monday."},
        ],
        "bad_synthesis": "CJP announced new appointments while continuing protests over the NEET paper leak.",
        "expected_verdict": "FLAG:entity_confusion",
        "why": ("The two evidence items refer to unrelated real-world entities that share "
                "an acronym; the synthesis conflates them into one actor doing both "
                "things. A checker keying only on the string 'CJP' would miss this - it "
                "requires the claim-extraction step to carry enough context (organization "
                "type, country) to tell them apart."),
    },

    # ---- 4. Attribution --------------------------------------------------------------
    {
        "id": "A1_attribution_real",
        "category": "attribution",
        "status": "REAL_VERIFIED",
        "event_ids": [8255],
        "note": ("Real story (Vande Mataram bill). Framing text already correctly "
                 "attributes claims per lean ('Left-leaning outlets highlight...', "
                 "'Right-leaning outlets emphasize...') rather than stating them as bare "
                 "fact - this is EXISTING correct behavior, not a gap."),
        "expected_verdict": "NO_FLAG",
        "why": "Included as a positive real-world example of attribution done right, to anchor the benchmark's baseline rather than only testing failure cases.",
    },

    # ---- 5/6. Numbers and dates --------------------------------------------------------
    {
        "id": "N1_numbers_real_consistent",
        "category": "numeric_consistency",
        "status": "REAL_VERIFIED",
        "event_ids": [7148],
        "note": ("Real story (Sensex fall). Independent outlets (Deccan Herald, The "
                 "Pioneer, Reuters via Times of India's rounding) report '1,677 points' / "
                 "'Rs 8.96 lakh crore' consistently; Times of India's '1,700 points' is a "
                 "legitimate rounding of the same figure, not a contradiction."),
        "expected_verdict": "NO_FLAG",
        "why": "Tests that a numeric-consistency checker tolerates rounding (1,677 vs ~1,700) rather than flagging every non-identical number as a conflict.",
    },
    {
        "id": "N1b_same_outlet_duplicate_rows",
        "category": "numeric_consistency / evidence_dedup",
        "status": "REAL_VERIFIED",
        "event_ids": [7148],
        "note": ("The Pioneer's article on this same story appears as multiple near-"
                 "identical rows in `articles` with cosmetic differences (spacing around "
                 "punctuation: '1,677' vs '1 , 677') - a real ingestion-side artifact, "
                 "distinct from cross-outlet syndication (see S1 below)."),
        "expected_verdict": "DEDUP:same_outlet_variant",
        "why": "This is exactly the kind of near-duplicate the Phase 6 shingle-based dedup needs to collapse before claim extraction, so 3 near-identical Pioneer rows don't get treated as 3 corroborating sources.",
    },

    # ---- 8. Legal allegation vs established fact -------------------------------------
    {
        "id": "L1_allegation_real",
        "category": "allegation_vs_established",
        "status": "REAL_VERIFIED",
        "event_ids": [24300, 24247],
        "note": ("Real events: 'Wisconsin Frat Leaders Arrested in Alleged Hazing "
                 "Incident' (explicit 'Alleged' in the real published title) and 'Former "
                 "TMC Leader Ajit Maity Arrested on Extortion Charges' (charged, not "
                 "convicted, in the real published title)."),
        "expected_verdict": "NO_FLAG_if_synthesis_preserves_hedge",
        "why": ("A checker should verify the SYNTHESIS text (not checked here - would "
                "need the full analysis_json body) preserves 'alleged'/'charged' language "
                "rather than dropping it to assert guilt as established fact. Flagged as "
                "a template case: pull the real synthesis text at benchmark-run time and "
                "check the hedge survived."),
    },

    # ---- 9. Multi-source contradiction (numeric dimension - 2026-09-28 hardening) ----
    # These use numeric_consistency.classify_numeric_pair(), not detect_conflicts() -
    # each carries expected_numeric_relationship + check_type="numeric" instead of
    # expected_verdict, so the harness knows which check to apply.
    {
        "id": "N2_death_toll_scope_synthetic",
        "category": "cross_source_contradiction",
        "status": "SYNTHETIC",
        "check_type": "numeric",
        "note": ("Refines the first prototype pass's X1 case: 'at least 12' and "
                 "'confirmed 8' are NOT a clean contradiction in real journalism "
                 "convention - a confirmed subset can coexist with a broader "
                 "'at least' estimate. Expected outcome changed from FLAG to "
                 "DIFFERENT_SCOPE accordingly - this is a refinement of the original "
                 "case, not a weakened test."),
        "evidence": [
            {"source": "Outlet A", "text": "The bridge collapse killed at least 12 people, officials said Monday."},
            {"source": "Outlet B", "text": "Local officials confirmed 8 deaths in the bridge collapse as of Monday."},
        ],
        "expected_numeric_relationship": "DIFFERENT_SCOPE",
    },
    {
        "id": "N2b_death_toll_clean_contradiction_synthetic",
        "category": "cross_source_contradiction",
        "status": "SYNTHETIC",
        "check_type": "numeric",
        "note": "No scope hedge words on either side, same attribution type, no time markers - a genuine, unhedged numeric contradiction.",
        "evidence": [
            {"source": "Outlet A", "text": "The train crash killed 15 people, police said."},
            {"source": "Outlet B", "text": "The train crash killed 9 people, police said."},
        ],
        "expected_numeric_relationship": "CONTRADICTION",
    },
    {
        "id": "N3_numeric_update_synthetic",
        "category": "numeric_update",
        "status": "SYNTHETIC",
        "check_type": "numeric",
        "note": "Explicit different days attached to different toll figures - a later report updating an earlier one, not a same-moment contradiction.",
        "evidence": [
            {"source": "Outlet A", "text": "4 people were confirmed dead in the flooding as of Monday."},
            {"source": "Outlet B", "text": "The death toll from the flooding rose to 8 by Wednesday, officials said."},
        ],
        "expected_numeric_relationship": "LATER_UPDATE",
    },
    {
        "id": "N4_percentage_close_synthetic",
        "category": "percentage",
        "status": "SYNTHETIC",
        "check_type": "numeric",
        "note": "Two close percentage figures, no time/scope markers - should not escalate to CONTRADICTION either way.",
        "evidence": [
            {"source": "Outlet A", "text": "The candidate leads with 52% support in the latest poll."},
            {"source": "Outlet B", "text": "The latest poll shows the candidate leading with 54% support."},
        ],
        "expected_numeric_relationship": "NOT_CONTRADICTION",  # accepts ROUNDING or APPROXIMATION - see report's fuzzy-boundary note
    },
    {
        "id": "N5_monetary_contradiction_synthetic",
        "category": "monetary_amount",
        "status": "SYNTHETIC",
        "check_type": "numeric",
        "note": "Materially different fraud totals, no hedge/time markers - a genuine contradiction.",
        "evidence": [
            {"source": "Outlet A", "text": "Investigators say the fraud involved $2 million in stolen funds."},
            {"source": "Outlet B", "text": "The fraud totaled $8 million, according to investigators."},
        ],
        "expected_numeric_relationship": "CONTRADICTION",
    },
    {
        "id": "N6_score_result_synthetic",
        "category": "score_result",
        "status": "SYNTHETIC",
        "check_type": "numeric",
        "note": ("A close, small-integer score difference - tests that the fixed "
                 "'numbers below 10 are never treated as round' rule prevents this "
                 "from being waved through as rounding."),
        "evidence": [
            {"source": "Outlet A", "text": "Team A won the match 3-1."},
            {"source": "Outlet B", "text": "Team A won the match 3-2."},
        ],
        "expected_numeric_relationship": "CONTRADICTION",
    },
    {
        "id": "N7_attribution_vs_established_synthetic",
        "category": "allegation_vs_established",
        "status": "SYNTHETIC",
        "check_type": "status",
        "note": "Reuses the existing STATUS_CONFLICT_PAIRS mechanism (ALLEGED vs ESTABLISHED) rather than the numeric dimension - tests that a synthesis dropping an attribution hedge is still caught.",
        "evidence": [
            {"source": "Outlet A", "text": "Police allege the suspect stole the funds from the charity's accounts."},
        ],
        "bad_synthesis": "The suspect stole the funds from the charity's accounts.",
        "expected_verdict": "FLAG:status_conflict",
    },

    # ---- v2 hardening (2026-09-28) additions - section 9's required new cases --------
    {
        "id": "V2_1_cm_no_marker_synthetic",
        "category": "current_vs_former_office_holder",
        "status": "SYNTHETIC",
        "check_type": "status",
        "note": ("Isolates the EXACT pattern that caused the F1 real-evidence false "
                 "positive ('CM Suvendu Adhikari', no former/ex-/current marker at "
                 "all) as its own clean regression case, independent of the real "
                 "corpus text, so this specific failure mode has a minimal, always-"
                 "available test."),
        "evidence": [
            {"source": "Outlet A", "text": "CM Jane Doe inaugurated the new bridge on Tuesday."},
        ],
        "expected_verdict": "NO_FLAG",  # single evidence item, nothing to conflict with -
                                         # the real assertion under test is UNSPECIFIED status,
                                         # checked directly on the extracted claim by the harness
    },
    {
        "id": "V2_2_explicit_former_synthetic",
        "category": "current_vs_former_office_holder",
        "status": "SYNTHETIC",
        "check_type": "status",
        "note": "A clean explicit-former case with an explicit-current counterpart - the positive control this category needs alongside V2_1's negative control.",
        "evidence": [
            {"source": "Outlet A", "text": "Former CM Jane Doe criticised the budget on Tuesday."},
            {"source": "Outlet B", "text": "Current CM John Roe defended the budget the same day."},
        ],
        "expected_verdict": "NO_FLAG",  # different people (Jane Doe vs John Roe) - no conflict expected;
                                         # exercises that FORMER_EXPLICIT/CURRENT_EXPLICIT on DIFFERENT
                                         # subjects does not falsely cross-flag
    },
    {
        "id": "V2_3_explicit_current_vs_former_synthetic",
        "category": "current_vs_former_office_holder",
        "status": "SYNTHETIC",
        "check_type": "status",
        "note": "Same person, explicit current in one source, explicit former in another - a genuine, cleanly-marked conflict.",
        "evidence": [
            {"source": "Outlet A", "text": "Current CM Jane Doe inaugurated the new bridge on Tuesday."},
            {"source": "Outlet B", "text": "Former CM Jane Doe criticised the budget on Wednesday."},
        ],
        "expected_verdict": "FLAG:status_conflict",
    },
    {
        "id": "V2_4_explicit_allegation_synthetic",
        "category": "allegation_vs_established",
        "status": "SYNTHETIC",
        "check_type": "status",
        "note": "Explicit ALLEGED marker vs explicit CHARGED marker for the same subject - both are hedge language, testing that two DIFFERENT hedge strengths on the same fact are not incorrectly treated as agreeing OR as a false conflict (ALLEGED/CHARGED is not in STATUS_CONFLICT_PAIRS - they are compatible, not opposites).",
        "evidence": [
            {"source": "Outlet A", "text": "Police allege the suspect stole company funds."},
            {"source": "Outlet B", "text": "The suspect was later charged with theft."},
        ],
        "expected_verdict": "NO_FLAG",  # ALLEGED_EXPLICIT and CHARGED_EXPLICIT are compatible
                                         # (an allegation preceding a formal charge is normal
                                         # case progression, not a contradiction)
    },
    {
        "id": "V2_5_explicit_conviction_synthetic",
        "category": "allegation_vs_established",
        "status": "SYNTHETIC",
        "check_type": "status",
        "note": "Explicit CHARGED vs explicit CONVICTED for the same subject and same charge - CHARGED/CONVICTED IS in STATUS_CONFLICT_PAIRS, so asserting someone is still merely charged when another source says convicted is a genuine status conflict (unless time-sequenced, which this deliberately does not state).",
        "evidence": [
            {"source": "Outlet A", "text": "The suspect was charged with theft last month."},
            {"source": "Outlet B", "text": "The suspect was convicted of theft, the court confirmed."},
        ],
        "expected_verdict": "FLAG:status_conflict",
    },
    {
        "id": "V2_6_score_synthetic",
        "category": "score_result",
        "status": "SYNTHETIC",
        "check_type": "numeric",
        "note": "Duplicate of N6 by design (section 9 explicitly lists '3-1 vs 3-2 score' as a required case) - kept as its own id for direct traceability to the hardening task's own list, testing the v2 compound home_value/away_value schema specifically.",
        "evidence": [
            {"source": "Outlet A", "text": "Team A won the match 3-1."},
            {"source": "Outlet B", "text": "Team A won the match 3-2."},
        ],
        "expected_numeric_relationship": "CONTRADICTION",
    },
    {
        "id": "V2_7_at_least_death_toll_synthetic",
        "category": "cross_source_contradiction",
        "status": "SYNTHETIC",
        "check_type": "numeric",
        "note": "Duplicate of N2 by design (section 9 explicitly lists 'death toll with at least' as a required case) - kept as its own id for direct traceability.",
        "evidence": [
            {"source": "Outlet A", "text": "The bridge collapse killed at least 12 people, officials said Monday."},
            {"source": "Outlet B", "text": "Local officials confirmed 8 deaths in the bridge collapse as of Monday."},
        ],
        "expected_numeric_relationship": "DIFFERENT_SCOPE",
    },
    {
        "id": "V2_8_same_day_different_phrasing_synthetic",
        "category": "numeric_update",
        "status": "SYNTHETIC",
        "check_type": "numeric",
        "note": "Section 9's explicit 'same-day Monday vs as of Monday' case - same value, same actual day, different phrasing. Must resolve COMPATIBLE, not DIFFERENT_TIME/LATER_UPDATE, per section 5's normalization requirement.",
        "evidence": [
            {"source": "Outlet A", "text": "4 people were confirmed dead in the flooding on Monday."},
            {"source": "Outlet B", "text": "The death toll from the flooding stood at 4 as of Monday, officials said."},
        ],
        "expected_numeric_relationship": "NOT_CONTRADICTION",  # same value (4=4) -> COMPATIBLE regardless of phrasing
    },
    {
        "id": "V2_9_acronym_expanded_entity_synthetic",
        "category": "entity_disambiguation",
        "status": "SYNTHETIC",
        "check_type": "entity",
        "note": "Section 9's explicit 'acronym/expanded entity' case - here BOTH sources state the SAME expansion for the acronym, so this should resolve as a matched entity (no finding), the counterpart to E1b's mismatched-expansion case.",
        "evidence": [
            {"source": "Outlet A", "text": "The Cockroach Janta Party (CJP) held a rally at Jantar Mantar."},
            {"source": "Outlet B", "text": "CJP, short for the Cockroach Janta Party, announced a new march date."},
        ],
        "expected_entity_outcome": "NO_AMBIGUITY",  # both sides agree on the expansion - same entity, not flagged
    },
    {
        "id": "V2_10_unsupported_claim_no_span_synthetic",
        "category": "grounding_invariant",
        "status": "SYNTHETIC",
        "check_type": "grounding",
        "note": ("Tests the hard deterministic grounding invariant directly (section "
                 "4): a hand-constructed claim whose evidence_quote does NOT appear "
                 "verbatim in the source text must be rejected by "
                 "claim_extraction.is_grounded() - this is checked as a pure "
                 "function, no LLM call needed, since the invariant is deterministic "
                 "by construction."),
        "source_text": "CM Suvendu Adhikari inaugurated the new bridge on Tuesday.",
        "fabricated_evidence_quote": "Former Chief Minister Suvendu Adhikari, who lost the previous election",
        "expected_grounded": False,
    },

    # ---- 10. Thin-evidence story -------------------------------------------------------
    {
        "id": "T1_thin_evidence_real",
        "category": "thin_evidence",
        "status": "REAL_VERIFIED",
        "event_ids": [24446, 24445],
        "note": ("Real stories, both with exactly 2 rated outlets (total<=3), already "
                 "surfaced to readers via the 'Early coverage' signal shipped in the "
                 "Story Page P1 change earlier in this session."),
        "expected_verdict": "LOW_CONFIDENCE_TIER",
        "why": "Confirms the thin-evidence signal already exists at the UI layer; Phase 4's evidence-quality model should independently reach the same low-confidence conclusion from the underlying source count.",
    },

    # ---- 11. Syndicated duplicate reporting -------------------------------------------
    {
        "id": "S1_syndication_real",
        "category": "syndication_dedup",
        "status": "REAL_VERIFIED",
        "event_ids": [23379],
        "note": ("Real story (Ireland-Israel soccer). 'Reuters' and 'Channel News Asia' "
                 "both carry the IDENTICAL headline 'Ireland manager thanks prime "
                 "minister for support ahead of Israel fixtures' - a wire-copy story run "
                 "by two independently-owned outlets."),
        "expected_verdict": "COLLAPSE:1_independent_group_of_2",
        "why": "Tests that these count as ONE independent evidence group (one vote), not two independent confirmations, per Phase 6's explicit requirement.",
    },

    # ---- 12. International/domestic classification edge cases ------------------------
    {
        "id": "I1_region_edge_real",
        "category": "international_domestic_boundary",
        "status": "REAL_VERIFIED",
        "event_ids": [24374, 24246],
        "note": ("Real events: 'India warns Pakistan of terror consequences at UN' and "
                 "'India and Australia Discuss Bilateral Investment Treaty' - both "
                 "genuinely bilateral, testing the India-vs-World region boundary the "
                 "prior classification-accuracy audit (Task 4 of this session) already "
                 "fixed via the 'substantively central' region principle."),
        "expected_verdict": "REGION:India (bilateral India-led action, not incidental mention)",
        "why": "Anchors the region boundary with real examples rather than only the synthetic incidental-mention cases used in test_topic_region_classification.py.",
    },
]


def print_case(c):
    print(f"[{c['status']}] {c['id']}  ({c['category']})")
    print(f"    expected: {c['expected_verdict']}")
    if c.get("note"):
        print(f"    note: {c['note']}")
    print()


def run():
    conn = _conn()
    try:
        for c in CASES:
            print_case(c)
            for eid in c.get("event_ids", []):
                ev = _event(conn, eid)
                if ev:
                    print(f"      event {eid}: {ev['title']}")
                else:
                    print(f"      event {eid}: NOT FOUND (may have been consolidated/removed since this case was written)")
            print()
    finally:
        conn.close()
    print(f"{len(CASES)} benchmark cases loaded "
          f"({sum(1 for c in CASES if c['status']=='REAL_VERIFIED')} REAL_VERIFIED, "
          f"{sum(1 for c in CASES if c['status']=='REAL_NEGATIVE')} REAL_NEGATIVE, "
          f"{sum(1 for c in CASES if c['status']=='SYNTHETIC')} SYNTHETIC).")
    print("No pass/fail assertions yet - Phases 2-11's checker code does not exist as "
          "runnable prototype code. This file is the fixture it will be graded against.")


if __name__ == "__main__":
    run()
