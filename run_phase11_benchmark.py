"""run_phase11_benchmark.py - runs factuality_benchmark_phase11.py's cases against
the real Phase 10/11 prototype (phase10_synthesis.py, phase11_verification.py).
Uses REAL LLM calls against the strong-model provider (gemini_strong) for both
synthesis/regeneration and claim re-extraction. Entirely separate harness from
run_benchmark_prototype.py - the original 24-case benchmark is run unmodified,
separately (see run_full_regression_with_retry.py), to confirm no regression.

Run:  py run_phase11_benchmark.py
"""
import time

from claim_extraction import extract_claims, is_model_failure, RATE_LIMIT
from consistency_checks import detect_conflicts
from factuality_benchmark_phase11 import PHASE11_CASES
from numeric_consistency import classify_numeric_pair
from phase10_synthesis import GEMINI_STRONG_PROVIDER, route_synthesis, synthesize
from phase11_verification import (
    check_unhedged_downgrade, check_attribution_loss, decide, diagnose_entity_expansion_omission,
    format_regenerate_feedback, verify_symmetric, PASS, REGENERATE, HOLD,
)

RESULTS = []
REGEN_ATTEMPTS_MADE = 0
DOWNGRADE_FINDING_COUNT = 0
ATTRIBUTION_FINDING_COUNT = 0
DIAGNOSTIC_OMISSION_COUNT = 0
PHASE_OUTCOME_COUNTS = {PASS: 0, REGENERATE: 0, HOLD: 0}
STRONG_MODEL_CALLS = 0   # every real call against GEMINI_STRONG_PROVIDER, extraction or synthesis


def record(cid, ok, detail):
    RESULTS.append((cid, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {cid}: {detail}")


RETRY_WAIT_S = 20
MAX_TRANSIENT_RETRIES = 2   # bounded - never an unbounded/infinite retry loop


def _extract(text, source, provider):
    global STRONG_MODEL_CALLS
    for attempt in range(MAX_TRANSIENT_RETRIES + 1):
        STRONG_MODEL_CALLS += 1
        claims, status, stats = extract_claims(text, source=source, provider=provider)
        if status != RATE_LIMIT or attempt == MAX_TRANSIENT_RETRIES:
            return claims, status, stats
        print(f"    (transient RATE_LIMIT, bounded retry {attempt + 1}/{MAX_TRANSIENT_RETRIES} after {RETRY_WAIT_S}s)")
        time.sleep(RETRY_WAIT_S)


def _verify(ev_claims, text, provider):
    global STRONG_MODEL_CALLS
    for attempt in range(MAX_TRANSIENT_RETRIES + 1):
        STRONG_MODEL_CALLS += 1
        findings, status, synth_claims = verify_symmetric(ev_claims, text, provider=provider)
        if status != RATE_LIMIT or attempt == MAX_TRANSIENT_RETRIES:
            return findings, status, synth_claims
        print(f"    (transient RATE_LIMIT, bounded retry {attempt + 1}/{MAX_TRANSIENT_RETRIES} after {RETRY_WAIT_S}s)")
        time.sleep(RETRY_WAIT_S)


def _synthesize(ev_claims, route, **kw):
    global STRONG_MODEL_CALLS
    for attempt in range(MAX_TRANSIENT_RETRIES + 1):
        STRONG_MODEL_CALLS += 1
        text, status = synthesize(ev_claims, route, **kw)
        if status != RATE_LIMIT or attempt == MAX_TRANSIENT_RETRIES:
            return text, status
        print(f"    (transient RATE_LIMIT, bounded retry {attempt + 1}/{MAX_TRANSIENT_RETRIES} after {RETRY_WAIT_S}s)")
        time.sleep(RETRY_WAIT_S)


def _combined_findings(ev_claims, sym_findings, synth_claims):
    """Folds check_attribution_loss's output into the SAME list decide() already
    filters by certainty=="high" only - attribution_loss findings carry
    certainty="requires_context" so they never trigger REGENERATE/HOLD on their
    own, exactly like a domain_conflict signal."""
    global ATTRIBUTION_FINDING_COUNT
    attribution_findings = check_attribution_loss(ev_claims, synth_claims)
    ATTRIBUTION_FINDING_COUNT += len(attribution_findings)
    return sym_findings + attribution_findings


def run_verification_case(case):
    global DOWNGRADE_FINDING_COUNT
    cid = case["id"]
    print(f"\n=== {cid} ({case['category']}) ===")
    evidence = case["evidence"]
    ev_claims = []
    for e in evidence:
        claims, status, _stats = _extract(e["text"], e["source"], GEMINI_STRONG_PROVIDER)
        if is_model_failure(status):
            record(cid, False, f"MODEL_FAILURE extracting evidence: {status}")
            return
        ev_claims.extend(claims)

    sym_findings, sym_status, synth_claims = _verify(ev_claims, case["bad_synthesis"], GEMINI_STRONG_PROVIDER)
    if is_model_failure(sym_status):
        record(cid, False, f"MODEL_FAILURE extracting synthesis: {sym_status}")
        return
    downgrade_findings = check_unhedged_downgrade(ev_claims, synth_claims)
    DOWNGRADE_FINDING_COUNT += len(downgrade_findings)
    all_findings = _combined_findings(ev_claims, sym_findings, synth_claims)
    outcome, reason = decide(all_findings, downgrade_findings, sym_status)
    PHASE_OUTCOME_COUNTS[outcome] += 1

    expect = case["expect"]
    if expect == "PASS":
        ok = outcome == PASS
    elif expect == "DOWNGRADE_FLAGGED":
        ok = bool(downgrade_findings) and outcome in (REGENERATE, HOLD)
    elif expect == "NO_ATTRIBUTION_FINDING":
        ok = not any(f["type"] == "attribution_loss" for f in all_findings)
    elif expect == "ATTRIBUTION_FLAGGED":
        ok = any(f["type"] == "attribution_loss" for f in all_findings)
    else:
        ok = False
    record(cid, ok, f"outcome={outcome} ({reason}) downgrade={[f['reason'] for f in downgrade_findings]} "
                     f"attribution={[f['reason'] for f in all_findings if f['type']=='attribution_loss']} "
                     f"symmetric={[f.get('reason') for f in sym_findings]}")


def run_regeneration_loop_unresolvable(case):
    """P11_8/10: real evidence-level contradiction, real synthesize() + verify()
    cycle, bounded to MAX_REGENERATE_ATTEMPTS, must bottom out at HOLD."""
    global REGEN_ATTEMPTS_MADE
    cid = case["id"]
    print(f"\n=== {cid} ({case['category']}) - REAL regeneration loop ===")
    per_source = []
    for e in case["evidence"]:
        claims, status, _stats = _extract(e["text"], e["source"], GEMINI_STRONG_PROVIDER)
        if is_model_failure(status):
            record(cid, False, f"MODEL_FAILURE extracting evidence: {status}")
            return
        per_source.append(claims)
    ev_claims = [c for claims in per_source for c in claims]
    pre_conflicts = detect_conflicts(per_source[0], per_source[1]) if len(per_source) > 1 else []
    route = route_synthesis(pre_conflicts, [], [], ev_claims)
    print(f"    route: {route}")

    feedback = None
    outcome = None
    for attempt in range(3):
        text, status = _synthesize(ev_claims, route, pre_synthesis_conflicts=pre_conflicts, regenerate_feedback=feedback, provider_override=GEMINI_STRONG_PROVIDER)
        if is_model_failure(status):
            record(cid, False, f"MODEL_FAILURE during synthesis: {status}")
            return
        sym_findings, sym_status, synth_claims = _verify(ev_claims, text, GEMINI_STRONG_PROVIDER)
        if is_model_failure(sym_status):
            record(cid, False, f"MODEL_FAILURE during verification: {sym_status}")
            return
        downgrade_findings = check_unhedged_downgrade(ev_claims, synth_claims)
        all_findings = _combined_findings(ev_claims, sym_findings, synth_claims)
        outcome, reason = decide(all_findings, downgrade_findings, sym_status, regenerate_attempt=attempt)
        PHASE_OUTCOME_COUNTS[outcome] = PHASE_OUTCOME_COUNTS.get(outcome, 0) + 1
        print(f"    attempt {attempt}: outcome={outcome} ({reason}) draft={text[:150]!r}")
        if outcome != REGENERATE:
            break
        REGEN_ATTEMPTS_MADE += 1
        feedback = format_regenerate_feedback(all_findings + downgrade_findings)

    ok = outcome == case["expect"]
    record(cid, ok, f"final outcome={outcome}, expected={case['expect']}")


def run_regeneration_converges(case):
    """P11_9: seeded with a KNOWN-bad first draft (deterministic, not hoping a
    real call fails), then a REAL regenerate call with specific feedback."""
    global REGEN_ATTEMPTS_MADE
    cid = case["id"]
    print(f"\n=== {cid} ({case['category']}) - REAL regeneration-converges ===")
    ev_claims = []
    for e in case["evidence"]:
        claims, status, _stats = _extract(e["text"], e["source"], GEMINI_STRONG_PROVIDER)
        if is_model_failure(status):
            record(cid, False, f"MODEL_FAILURE extracting evidence: {status}")
            return
        ev_claims.extend(claims)

    bad_draft = case["seed_bad_draft"]
    sym_findings, sym_status, synth_claims = _verify(ev_claims, bad_draft, GEMINI_STRONG_PROVIDER)
    if is_model_failure(sym_status):
        record(cid, False, f"MODEL_FAILURE verifying seed draft: {sym_status}")
        return
    downgrade_findings = check_unhedged_downgrade(ev_claims, synth_claims)
    all_findings = _combined_findings(ev_claims, sym_findings, synth_claims)
    outcome, reason = decide(all_findings, downgrade_findings, sym_status, regenerate_attempt=0)
    PHASE_OUTCOME_COUNTS[outcome] += 1
    print(f"    seeded first draft -> outcome={outcome} ({reason})")
    if outcome != REGENERATE:
        record(cid, False, f"seed draft did not produce REGENERATE as expected (got {outcome}) - test setup issue, not a mechanism failure")
        return
    REGEN_ATTEMPTS_MADE += 1
    feedback = format_regenerate_feedback(all_findings + downgrade_findings)
    route = {"model": "gemini_strong", "reasons": ["TEST_SEEDED"]}
    text, status = _synthesize(ev_claims, route, regenerate_feedback=feedback, provider_override=GEMINI_STRONG_PROVIDER)
    if is_model_failure(status):
        record(cid, False, f"MODEL_FAILURE during regeneration: {status}")
        return
    sym_findings2, sym_status2, synth_claims2 = _verify(ev_claims, text, GEMINI_STRONG_PROVIDER)
    if is_model_failure(sym_status2):
        record(cid, False, f"MODEL_FAILURE verifying regenerated draft: {sym_status2}")
        return
    downgrade2 = check_unhedged_downgrade(ev_claims, synth_claims2)
    all_findings2 = _combined_findings(ev_claims, sym_findings2, synth_claims2)
    outcome2, reason2 = decide(all_findings2, downgrade2, sym_status2, regenerate_attempt=1)
    PHASE_OUTCOME_COUNTS[outcome2] = PHASE_OUTCOME_COUNTS.get(outcome2, 0) + 1
    print(f"    regenerated draft ({text[:300]!r}) -> outcome={outcome2} ({reason2}) "
          f"findings={[f.get('reason') for f in all_findings2]} downgrade={[f.get('reason') for f in downgrade2]}")
    record(cid, outcome2 == PASS, f"regenerated outcome={outcome2}, expected PASS")


def run_diagnostic_case():
    global DIAGNOSTIC_OMISSION_COUNT
    cid = "P11_11_extraction_omission_diagnostic"
    print(f"\n=== {cid} (diagnostic) ===")
    text = "The Cockroach Janta Party (CJP) held a rally at Jantar Mantar."
    claims, status, _stats = _extract(text, "Outlet A", GEMINI_STRONG_PROVIDER)
    if is_model_failure(status):
        record(cid, False, f"MODEL_FAILURE: {status}")
        return
    diagnostics = diagnose_entity_expansion_omission(claims, text)
    DIAGNOSTIC_OMISSION_COUNT += sum(1 for d in diagnostics if d["omitted"])
    print(f"    diagnostics: {diagnostics}")
    ok = all("omitted" in d and "evidence_contains_expansion" in d for d in diagnostics)
    record(cid, ok, f"produced {len(diagnostics)} diagnostic(s), well-formed={ok}")


def main():
    for case in PHASE11_CASES:
        cat = case["category"]
        if cat == "regeneration_loop":
            if "seed_bad_draft" in case:
                run_regeneration_converges(case)
            else:
                run_regeneration_loop_unresolvable(case)
        else:
            run_verification_case(case)
    run_diagnostic_case()

    print(f"\n{'=' * 70}")
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"{passed}/{len(RESULTS)} PHASE11 checks matched expectations.")
    for cid, ok, detail in RESULTS:
        if not ok:
            print(f"  DID NOT MATCH: {cid} - {detail}")
    print(f"\nPHASE 11 metrics:")
    print(f"  asymmetric downgrade/addition findings across all cases: {DOWNGRADE_FINDING_COUNT}")
    print(f"  attribution_loss findings across all cases: {ATTRIBUTION_FINDING_COUNT}")
    print(f"  extraction-omission diagnostics flagged: {DIAGNOSTIC_OMISSION_COUNT}")
    print(f"  regeneration attempts made: {REGEN_ATTEMPTS_MADE}")
    print(f"  strong-model calls made: {STRONG_MODEL_CALLS}")
    print(f"  PASS/REGENERATE/HOLD outcome counts: {PHASE_OUTCOME_COUNTS}")


if __name__ == "__main__":
    main()
