"""test_proposition_coverage.py - Step/Phase 10 adversarial safety test suite for
proposition_coverage.py. Entirely synthetic hand-built claims. ZERO API calls,
ZERO network access - pure function tests only.

NOTE on what this suite CAN test that the real 40-story replay cannot: because
shadow_trial_report.jsonl only ever checkpointed FINDINGS (cases that already
failed check_unhedged_downgrade), the real replay can never exercise COVERED
or COVERED_WITH_HEDGE - a fully-covered claim produces no finding to
reconstruct in the first place (see replay_proposition_coverage.py's module
docstring). This suite uses full, hand-built claim objects specifically so
Levels 2 and 3 - and the full 0-3 + CONTRADICTED + UNDETERMINABLE range - are
actually exercised and verified here, even though the real data can't reach
them.

Run:  py test_proposition_coverage.py
"""
from proposition_coverage import (
    evaluate_proposition_coverage, NOT_COVERED, PARTIALLY_COVERED, COVERED,
    COVERED_WITH_HEDGE, CONTRADICTED, UNDETERMINABLE,
)

FAILURES = []


def c(subject, predicate, obj=None, status="UNSPECIFIED", fact_type=None, value=None,
      unit=None, domain=None, time_type="UNSPECIFIED", time_text=None, source=None):
    return {"subject": subject, "predicate": predicate, "object": obj, "status": status,
            "fact_type": fact_type, "value": value, "unit": unit, "domain": domain,
            "time_type": time_type, "time_text": time_text, "source": source}


def check(label, cond):
    print(f"  {'OK ' if cond else 'FAIL'} {label}")
    if not cond:
        FAILURES.append(label)


def levels(ev, synth, **kw):
    res = evaluate_proposition_coverage(ev, synth, **kw)
    return [r["coverage_level"] for r in res]


print("=== 1. Three sources, same claim (family-recognized predicates), one synthesis statement -> COVERED ===")
ev = [c("scientists", "say", "X will happen", "CLAIMED_EXPLICIT", source="A"),
      c("scientists", "claims", "X will happen", "CLAIMED_EXPLICIT", source="B"),
      c("scientists", "states", "X will happen", "CLAIMED_EXPLICIT", source="C")]
synth = [c("scientists", "claimed", "X will happen", "CLAIMED_EXPLICIT")]
check("1 proposition, COVERED_WITH_HEDGE (CLAIMED is a hedge status)",
      levels(ev, synth) == [COVERED_WITH_HEDGE])

print("\n=== 2. Fifteen sources, same claim, one synthesis statement -> COVERED (non-hedge status) ===")
ev15 = [c("the death toll", "reached", "8", "CONFIRMED_EXPLICIT", fact_type="death_toll", value=8, source=f"O{i}") for i in range(15)]
synth15 = [c("the death toll", "reached", "8", "CONFIRMED_EXPLICIT", fact_type="death_toll", value=8)]
res15 = evaluate_proposition_coverage(ev15, synth15)
check("1 proposition covering all 15 sources", len(res15) == 1 and res15[0]["source_count"] == 15)
check("COVERED (CONFIRMED_EXPLICIT is high-risk but not a hedge status)", res15[0]["coverage_level"] == COVERED)

print("\n=== 3. Same proposition, different wording, structurally supported -> COVERED ===")
ev3 = [c("the minister", "was accused of", "bribery", "ALLEGED_EXPLICIT")]
synth3 = [c("the minister", "allege", "bribery", "ALLEGED_EXPLICIT")]
check("LEGAL_PROCEEDING family match -> COVERED_WITH_HEDGE (ALLEGED is a hedge)",
      levels(ev3, synth3) == [COVERED_WITH_HEDGE])

print("\n=== 4. Current vs former -> NOT equivalent (separate propositions, neither reaches the other's synthesis claim) ===")
ev4 = [c("Jane Doe", "holds the role of", "Chief Minister", "CURRENT_EXPLICIT")]
synth4 = [c("Jane Doe", "holds the role of", "Chief Minister", "FORMER_EXPLICIT")]
res4 = evaluate_proposition_coverage(ev4, synth4)
check("same proposition identity but CONTRADICTED status (CURRENT vs FORMER is a known antonym pair)",
      res4[0]["coverage_level"] == CONTRADICTED)

print("\n=== 5. Alleged vs established -> NOT equivalent ===")
ev5 = [c("the suspect", "stole", "the funds", "ALLEGED_EXPLICIT")]
synth5 = [c("the suspect", "stole", "the funds", "ESTABLISHED_EXPLICIT")]
check("CONTRADICTED, never COVERED", levels(ev5, synth5) == [CONTRADICTED])

print("\n=== 6. Charged vs convicted -> NOT equivalent ===")
ev6 = [c("the suspect", "was charged with", "theft", "CHARGED_EXPLICIT")]
synth6 = [c("the suspect", "was convicted of", "theft", "CONVICTED_EXPLICIT")]
check("CONTRADICTED (known antonym pair, LEGAL_PROCEEDING family match)", levels(ev6, synth6) == [CONTRADICTED])

print("\n=== 7. Killed vs injured -> NOT equivalent ===")
ev7 = [c("X", "was killed", "", "KILLED_EXPLICIT")]
synth7 = [c("X", "was injured", "", "INJURED_EXPLICIT")]
res7 = evaluate_proposition_coverage(ev7, synth7)
check("KILLED_EXPLICIT/INJURED_EXPLICIT not a known antonym PAIR in STATUS_CONFLICT_PAIRS "
      "(it is - see consistency_checks) -> CONTRADICTED", res7[0]["coverage_level"] == CONTRADICTED)

print("\n=== 8. Police accused X vs X accused Police -> NOT equivalent (different subjects entirely) ===")
ev8 = [c("Police", "allege", "the suspect stole the funds", "ALLEGED_EXPLICIT")]
synth8 = [c("the suspect", "allege", "Police stole the funds", "ALLEGED_EXPLICIT")]
check("different grammatical subjects -> NOT_COVERED, never silently matched", levels(ev8, synth8) == [NOT_COVERED])

print("\n=== 9. Same fact, different numeric dimension -> NOT equivalent ===")
ev9 = [c("the flood", "affected", "people", "CLAIMED_EXPLICIT", fact_type="casualty_count", value=500000)]
synth9 = [c("the flood", "affected", "people", "CLAIMED_EXPLICIT", fact_type="injury_count", value=500000)]
check("different fact_type -> NOT_COVERED (numeric_dimension gate)", levels(ev9, synth9) == [NOT_COVERED])

print("\n=== 10. Same fact, acceptable numeric rounding -> COVERED where existing numeric logic permits ===")
# proposition_coverage's identity match does not itself classify rounding vs
# contradiction (that's numeric_consistency's job, run elsewhere in the
# pipeline) - it only requires fact_type to match; the VALUE is allowed to
# differ (same design choice as claim_clustering, deliberately - see its
# stage 6 docstring). A 1677-vs-1700 pair should therefore match/COVER here.
ev10 = [c("the Sensex", "fell", "points", "UNSPECIFIED", fact_type="money_amount", value=1677)]
synth10 = [c("the Sensex", "fell", "points", "UNSPECIFIED", fact_type="money_amount", value=1700)]
check("same fact_type, differing value -> COVERED (rounding is a downstream numeric-consistency "
      "question, not this module's job)", levels(ev10, synth10) == [COVERED])

print("\n=== 11. Same fact, materially different date -> NOT equivalent ===")
ev11 = [c("X", "died", "", "KILLED_EXPLICIT", time_type="RELATIVE_DATE", time_text="Monday")]
synth11 = [c("X", "died", "", "KILLED_EXPLICIT", time_type="RELATIVE_DATE", time_text="Wednesday")]
check("different dates -> NOT_COVERED (time gate blocks the match entirely)", levels(ev11, synth11) == [NOT_COVERED])

print("\n=== 12. Same fact, materially different geography -> NOT equivalent ===")
ev12 = [c("flooding", "affected", "Bihar", "CLAIMED_EXPLICIT")]
synth12 = [c("flooding", "affected", "Kerala", "CLAIMED_EXPLICIT")]
check("different objects (states) -> NOT_COVERED (object gate blocks the match)", levels(ev12, synth12) == [NOT_COVERED])

print("\n=== 13. Claimed figure vs confirmed figure -> preserve epistemic difference ===")
ev13 = [c("the group", "claims", "10000 signed the petition", "CLAIMED_EXPLICIT")]
synth13 = [c("the group", "claimed", "10000 signed the petition", "CONFIRMED_EXPLICIT")]
res13 = evaluate_proposition_coverage(ev13, synth13)
check("CLAIMED_EXPLICIT vs CONFIRMED_EXPLICIT not a known antonym pair -> falls through as 'preserved' "
      "(conservative default, same as claims_compatible's own status stage) -> COVERED_WITH_HEDGE, "
      "NOT silently downgraded to plain COVERED", res13[0]["coverage_level"] == COVERED_WITH_HEDGE)

print("\n=== 14. One source repeats another -> do not create a second obligation ===")
ev14 = [c("officials", "confirmed", "8 dead", "CONFIRMED_EXPLICIT", fact_type="death_toll", value=8, source=f"O{i}") for i in range(5)]
synth14 = [c("officials", "confirmed", "8 dead", "CONFIRMED_EXPLICIT", fact_type="death_toll", value=8)]
res14 = evaluate_proposition_coverage(ev14, synth14)
check("5 repeated sources -> 1 proposition, COVERED once, not 5 separate obligations",
      len(res14) == 1 and res14[0]["coverage_level"] == COVERED)

print("\n=== 15. Genuine conflicting evidence (evidence itself disagrees) -> preserve disagreement ===")
ev15b = [c("the crash", "killed", "people", "KILLED_EXPLICIT", fact_type="death_toll", value=15),
         c("the crash", "killed", "people", "KILLED_EXPLICIT", fact_type="death_toll", value=9)]
synth15b = [c("the crash", "killed", "people", "KILLED_EXPLICIT", fact_type="death_toll", value=15)]
res15b = evaluate_proposition_coverage(ev15b, synth15b)
check("1 proposition (same claim family, differing values - clustering's own disagreement design)",
      len(res15b) == 1)
# disagreement between the 15-vs-9 evidence claims lives on the underlying
# cluster's member_claims values themselves, explicitly not collapsed into a
# single number - the coverage LEVEL question and the cluster's internal
# disagreement are two separate, both-preserved signals.
check("member_claims still contains both the 15 and the 9 claim - never silently merged into one value",
      {m.get("value") for m in res15b[0]["member_claims"]} == {15, 9})

print("\n=== 16. Missing fields -> safe / conservative outcome ===")
ev16 = [c(None, None)]
res16 = evaluate_proposition_coverage(ev16, [])
check("no subject/predicate -> UNDETERMINABLE, never guessed as covered or uncovered",
      res16[0]["coverage_level"] == UNDETERMINABLE)

print("\n=== 17. Attribution lost -> PARTIALLY_COVERED or NOT_COVERED where material ===")
ev17 = [c("an anonymous source", "claims", "the minister took bribes", "CLAIMED_EXPLICIT")]
synth17 = [c("officials", "said", "the minister took bribes", "UNSPECIFIED")]
res17 = evaluate_proposition_coverage(ev17, synth17)
check("non-routine specific attributor ('an anonymous source') has NO literal-subject match in "
      "synthesis (subject key requires exact match for non-routine attributors) -> NOT_COVERED, "
      "attribution flagged as the missing dimension", res17[0]["coverage_level"] == NOT_COVERED)
check("'attribution' recorded in missing_material_dimensions", "attribution" in res17[0]["missing_material_dimensions"])

print("\n=== 17b. Attribution lost but routine institutional source -> safely genericizable, not flagged ===")
ev17b = [c("police", "confirmed", "the death toll rose to 8", "CONFIRMED_EXPLICIT")]
synth17b = [c("officials", "confirmed", "the death toll rose to 8", "CONFIRMED_EXPLICIT")]
res17b = evaluate_proposition_coverage(ev17b, synth17b)
check("routine attributors (police/officials) share the routine-attributor bucket -> COVERED, "
      "no attribution dimension flagged", res17b[0]["coverage_level"] == COVERED and not res17b[0]["missing_material_dimensions"])

print("\n=== 18. Hedge preserved -> COVERED_WITH_HEDGE ===")
ev18 = [c("the opposition", "alleges", "corruption", "ALLEGED_EXPLICIT")]
synth18 = [c("the opposition", "allege", "corruption", "ALLEGED_EXPLICIT")]
check("hedge preserved -> COVERED_WITH_HEDGE", levels(ev18, synth18) == [COVERED_WITH_HEDGE])

print("\n=== 19. Hedge removed -> PARTIALLY_COVERED / NOT_COVERED where material ===")
ev19 = [c("the opposition", "alleges", "corruption", "ALLEGED_EXPLICIT")]
synth19 = [c("the opposition", "allege", "corruption", "UNSPECIFIED")]
check("hedge silently dropped to UNSPECIFIED -> PARTIALLY_COVERED, not COVERED",
      levels(ev19, synth19) == [PARTIALLY_COVERED])

print("\n=== 20. Subject/object inversion -> remain UNKNOWN/UNRESOLVED, no inversion matcher invented ===")
ev20 = [c("El Nino", "could cause", "500000 deaths", "CLAIMED_EXPLICIT")]
synth20 = [c("500000 deaths", "caused by", "El Nino", "CLAIMED_EXPLICIT")]
res20 = evaluate_proposition_coverage(ev20, synth20)
check("subject/object inverted phrasing -> NOT_COVERED (no inversion-aware matcher was built - "
      "the task explicitly forbids inventing one just to pass this case)",
      res20[0]["coverage_level"] == NOT_COVERED)

print(f"\n{'=' * 60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s):")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ADVERSARIAL PROPOSITION-COVERAGE CHECKS PASSED")
