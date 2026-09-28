"""factuality_benchmark_phase11.py - PHASE11 benchmark cases (2026-09-28), kept
entirely SEPARATE from factuality_benchmark.py's 24 original cases per the task's
explicit instruction ("Do not alter the existing 24 labels/cases... keep them
clearly separated as PHASE11 cases"). All SYNTHETIC (constructed to exercise
Phase 11's new mechanisms), labeled per the same REAL_VERIFIED/REAL_NEGATIVE/
SYNTHETIC convention as the original benchmark.
"""

PHASE11_CASES = [
    {
        "id": "P11_1_appositive_status_drop",
        "category": "asymmetric_downgrade",
        "status": "SYNTHETIC",
        "evidence": [{"source": "Outlet A", "text": "Former Chief Minister Jane Doe criticised the new government's budget on Tuesday."}],
        "bad_synthesis": "Chief Minister Jane Doe criticised the new government's budget on Tuesday.",
        "expect": "DOWNGRADE_FLAGGED",
    },
    {
        "id": "P11_2_semantic_preservation_former",
        "category": "semantic_preservation",
        "status": "SYNTHETIC",
        "evidence": [{"source": "Outlet A", "text": "Former Chief Minister Jane Doe criticised the new government's budget on Tuesday."}],
        "bad_synthesis": "Jane Doe, who previously served as chief minister, criticised the new government's budget on Tuesday.",
        "expect": "PASS",
    },
    {
        "id": "P11_3_allegation_to_established",
        "category": "asymmetric_downgrade",
        "status": "SYNTHETIC",
        "evidence": [{"source": "Outlet A", "text": "Police allege the suspect stole the funds from the charity's accounts."}],
        "bad_synthesis": "The suspect stole the funds from the charity's accounts.",
        "expect": "DOWNGRADE_FLAGGED",
    },
    {
        "id": "P11_4_semantic_preservation_alleged",
        "category": "semantic_preservation",
        "status": "SYNTHETIC",
        "evidence": [{"source": "Outlet A", "text": "Police allege the suspect stole the funds from the charity's accounts."}],
        "bad_synthesis": "The suspect was accused of stealing the funds from the charity's accounts.",
        "expect": "PASS",
    },
    {
        "id": "P11_5_charged_to_neutral_assertion",
        "category": "asymmetric_downgrade",
        "status": "SYNTHETIC",
        "evidence": [{"source": "Outlet A", "text": "The suspect was charged with theft of company funds."}],
        "bad_synthesis": "The suspect stole company funds.",
        "expect": "DOWNGRADE_FLAGGED",
    },
    {
        "id": "P11_6_conservative_synthesis_extra_hedge",
        "category": "conservative_synthesis",
        "status": "SYNTHETIC",
        "evidence": [{"source": "Outlet A", "text": "Police allege the suspect stole the funds from the charity's accounts."}],
        "bad_synthesis": "The suspect is accused of stealing the funds from the charity's accounts, though this has not been proven in court.",
        "expect": "PASS",
    },
    # ---- Attribution-source preservation (added 2026-09-28, after P11_4's diagnosis) ----
    {
        "id": "P11_13_attribution_must_preserve",
        "category": "attribution_preservation",
        "status": "SYNTHETIC",
        "evidence": [{"source": "Outlet A", "text": "An anonymous source claims the minister took bribes from a construction firm."}],
        "bad_synthesis": "The minister took bribes from a construction firm.",
        "expect": "ATTRIBUTION_FLAGGED",
        "why": "The attributor is an anonymous, unverified source - dropping it entirely elevates an unverified tip toward apparent fact. Not a routine institutional authority, so this must be flagged (non-blocking, review-queue) even though the ALLEGED status itself may still be preserved or lost separately (checked by check_unhedged_downgrade, unaffected by this).",
    },
    {
        "id": "P11_14_attribution_safely_drops",
        "category": "attribution_preservation",
        "status": "SYNTHETIC",
        "evidence": [{"source": "Outlet A", "text": "Election officials declared Jane Doe the winner of the mayoral race."}],
        "bad_synthesis": "Jane Doe was declared the winner of the mayoral race.",
        "expect": "NO_ATTRIBUTION_FINDING",
        "why": "Election officials are the sole, routine, uncontested authority for this kind of declaration - genericizing to passive voice loses nothing a reader needs to weigh the claim's credibility.",
    },
    {
        "id": "P11_7_both_unspecified",
        "category": "unspecified_preservation",
        "status": "SYNTHETIC",
        "evidence": [{"source": "Outlet A", "text": "CM Jane Doe inaugurated the new bridge on Tuesday."}],
        "bad_synthesis": "Jane Doe inaugurated the new bridge on Tuesday in her role as Chief Minister.",
        "expect": "PASS",
    },
    {
        "id": "P11_12_entity_strict_no_relaxation",
        "category": "entity_strictness",
        "status": "SYNTHETIC",
        "evidence": [{"source": "Outlet A", "text": "Police allege the suspect stole the funds from the charity's accounts."}],
        "bad_synthesis": "The suspect stole the funds from the charity's accounts.",
        "expect": "DOWNGRADE_FLAGGED",  # same fixture as P11_3 - the finding fires
                                          # because "Police" has no matching synthesis
                                          # claim at all, NOT because Police and
                                          # "suspect" were merged into one subject
        "why": "Confirms detect_conflicts/check_unhedged_downgrade never treat 'Police' and 'the suspect' as the same entity just because their predicates (allege / [implicit]) could share a family - the downgrade fires via the 'no matching claim at all' path, not an incorrect entity merge.",
    },

    # ---- P11_8/9/10: real end-to-end regeneration-loop cases (handled specially
    # by run_phase11_benchmark.py - these need actual synthesize()/verify() cycles,
    # not a pre-authored bad_synthesis, so they carry evidence only). ----
    {
        "id": "P11_8_unresolvable_contradiction_hold",
        "category": "regeneration_loop",
        "status": "SYNTHETIC",
        "evidence": [
            {"source": "Outlet A", "text": "Current Chief Minister Jane Doe inaugurated the new bridge on Tuesday."},
            {"source": "Outlet B", "text": "Former Chief Minister Jane Doe criticised the budget on Wednesday, a week after leaving office."},
        ],
        "expect": "HOLD",
        "why": "The evidence itself is irreconcilable (one source says Jane Doe is CURRENT CM, another says FORMER, with an explicit timeline) - no amount of regeneration can fix a synthesis when the underlying evidence conflicts this directly; must bottom out at HOLD after bounded attempts, not loop forever or silently pick a side.",
    },
    {
        "id": "P11_9_regeneration_converges",
        "category": "regeneration_loop",
        "status": "SYNTHETIC",
        "evidence": [{"source": "Outlet A", "text": "Former Chief Minister Jane Doe criticised the new government's budget on Tuesday."}],
        "seed_bad_draft": "Chief Minister Jane Doe criticised the new government's budget on Tuesday.",
        "expect": "PASS_AFTER_REGENERATE",
        "why": "Seeds the loop with a KNOWN-bad first draft (status dropped) rather than hoping a real model call happens to fail on attempt 1 (non-deterministic) - tests that feeding the specific downgrade finding back to synthesize() as regenerate_feedback produces a corrected second draft that passes verification.",
    },
]
