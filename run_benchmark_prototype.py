"""run_benchmark_prototype.py - HARDENED v2 (2026-09-28, round 2) benchmark harness.
Runs the evidence-bound v2 claim extractor + consistency_checks + numeric_consistency
against factuality_benchmark.py's cases. Reports the explicit outcome taxonomy
(section 10) plus grounding/status-distribution metrics section 10 also requires:
claims emitted, claims rejected for missing/non-verbatim evidence_quote, claims with
UNSPECIFIED vs explicit status, entity-linking unresolved cases.

MODEL_FAILURE is never counted as a false negative anywhere in this file.

Uses claim_extraction.get_benchmark_provider() (paid Gemini, isolated from
production's own Groq usage - unchanged from the v1 hardening pass).

Run:  py run_benchmark_prototype.py
"""
from collections import Counter

from claim_extraction import extract_claims, get_benchmark_provider, get_groq_provider, is_model_failure, is_grounded
from consistency_checks import detect_conflicts, check_entity_ambiguity
from evidence_assembly import group_independent, group_summary
from evidence_quality import classify as quality_classify
from factuality_benchmark import CASES
from numeric_consistency import classify_numeric_pair, CONTRADICTION as NC_CONTRADICTION

TRUE_POSITIVE = "TRUE_POSITIVE"
FALSE_POSITIVE = "FALSE_POSITIVE"
FALSE_NEGATIVE = "FALSE_NEGATIVE"
TRUE_NEGATIVE = "TRUE_NEGATIVE"
MODEL_FAILURE = "MODEL_FAILURE"
EXTRACTION_FAILURE = "EXTRACTION_FAILURE"
UNRESOLVED = "UNRESOLVED"

OUTCOMES = []
# section 10's grounding/status distribution counters, aggregated across every real
# extraction call made during this run (not per-case - a whole-run picture of how
# often the model tried to assert something ungrounded)
GROUNDING_STATS = {"claims_emitted": 0, "missing_quote": 0, "quote_not_verbatim": 0,
                    "unspecified_status": 0, "explicit_status": 0}

_VERDICT_TO_CONFLICT_TYPE = {
    "temporal_error": "status_conflict",
    "entity_confusion": "status_conflict",
    "status_conflict": "status_conflict",
    "domain_error": "domain_conflict",
}


def record(case_id, outcome, detail):
    OUTCOMES.append((case_id, outcome, detail))
    print(f"  [{outcome}] {case_id}: {detail}")


def _tally_claims(claims):
    GROUNDING_STATS["claims_emitted"] += len(claims)
    for c in claims:
        if c.get("status") == "UNSPECIFIED":
            GROUNDING_STATS["unspecified_status"] += 1
        else:
            GROUNDING_STATS["explicit_status"] += 1


def _extract_all(items, provider):
    """-> (list_of_claim_lists, failure_or_None). Aggregates rejection stats into
    GROUNDING_STATS as a side effect (every real extraction call counts, whether
    or not the case ultimately scores)."""
    claim_lists = []
    for it in items:
        claims, status, stats = extract_claims(it["text"], source=it["source"], provider=provider)
        GROUNDING_STATS["missing_quote"] += stats["missing_quote"]
        GROUNDING_STATS["quote_not_verbatim"] += stats["quote_not_verbatim"]
        if is_model_failure(status):
            return None, status
        _tally_claims(claims)
        claim_lists.append(claims)
    return claim_lists, None


def run_status_or_domain_case(case, provider):
    cid = case["id"]
    print(f"\n=== {cid} ({case['category']}) check_type={case.get('check_type')} ===")
    evidence = case.get("evidence")
    if not evidence:
        record(cid, UNRESOLVED, "no `evidence` field - not runnable")
        return
    evidence_claim_lists, failure = _extract_all(evidence, provider)
    if failure:
        record(cid, MODEL_FAILURE, f"evidence extraction failed: {failure}")
        return

    # V2_1: single-evidence, no-marker case - the direct regression test for the F1
    # bug. There is nothing to compare against (only one evidence item), so what
    # actually matters is whether the extracted claim's status is UNSPECIFIED, not
    # a hallucinated CURRENT_EXPLICIT/FORMER_EXPLICIT.
    if len(evidence) == 1 and not case.get("bad_synthesis"):
        claims = evidence_claim_lists[0]
        role_claims = [c for c in claims if c.get("fact_type") == "office_holder"]
        if not role_claims:
            record(cid, EXTRACTION_FAILURE, f"no office_holder claim extracted at all - claims={claims}")
            return
        bad = [c for c in role_claims if c.get("status") != "UNSPECIFIED"]
        if bad:
            record(cid, FALSE_POSITIVE, f"expected UNSPECIFIED status (no marker in text), model asserted: {[(c['status'], c['evidence_quote']) for c in bad]}")
        else:
            record(cid, TRUE_NEGATIVE, f"correctly UNSPECIFIED: {[(c['status'], c['evidence_quote']) for c in role_claims]}")
        return

    synth_claims = []
    bad_synth = case.get("bad_synthesis")
    if bad_synth:
        synth_claims, status, stats = extract_claims(bad_synth, source="SYNTHESIS", provider=provider)
        GROUNDING_STATS["missing_quote"] += stats["missing_quote"]
        GROUNDING_STATS["quote_not_verbatim"] += stats["quote_not_verbatim"]
        if is_model_failure(status):
            record(cid, MODEL_FAILURE, f"synthesis extraction failed: {status}")
            return
        _tally_claims(synth_claims)

    conflicts = []
    for i in range(len(evidence_claim_lists)):
        for j in range(i + 1, len(evidence_claim_lists)):
            conflicts += detect_conflicts(evidence_claim_lists[i], evidence_claim_lists[j])
        if synth_claims:
            conflicts += detect_conflicts(evidence_claim_lists[i], synth_claims)

    expects_flag = case["expected_verdict"].startswith("FLAG")
    verdict_suffix = case["expected_verdict"].split(":", 1)[1] if ":" in case["expected_verdict"] else None
    wanted_type = _VERDICT_TO_CONFLICT_TYPE.get(verdict_suffix)

    if expects_flag:
        got_flag = any(c["type"] == wanted_type for c in conflicts) if wanted_type else bool(conflicts)
    else:
        got_flag = bool(conflicts)

    if expects_flag and got_flag:
        record(cid, TRUE_POSITIVE, f"conflicts={conflicts}")
    elif expects_flag and not got_flag:
        record(cid, FALSE_NEGATIVE, f"expected a flag, found none. evidence={evidence_claim_lists} synth={synth_claims}")
    elif not expects_flag and not got_flag:
        record(cid, TRUE_NEGATIVE, f"no conflicts found, as expected. claims={evidence_claim_lists}")
    else:
        record(cid, FALSE_POSITIVE, f"expected NO_FLAG, got conflicts={conflicts}")


def run_entity_case(case, provider):
    cid = case["id"]
    print(f"\n=== {cid} ({case['category']}) check_type=entity ===")
    evidence = case.get("evidence")
    evidence_claim_lists, failure = _extract_all(evidence, provider)
    if failure:
        record(cid, MODEL_FAILURE, f"evidence extraction failed: {failure}")
        return
    synth_claims = []
    bad_synth = case.get("bad_synthesis")
    if bad_synth:
        synth_claims, status, stats = extract_claims(bad_synth, source="SYNTHESIS", provider=provider)
        GROUNDING_STATS["missing_quote"] += stats["missing_quote"]
        GROUNDING_STATS["quote_not_verbatim"] += stats["quote_not_verbatim"]
        if is_model_failure(status):
            record(cid, MODEL_FAILURE, f"synthesis extraction failed: {status}")
            return
        _tally_claims(synth_claims)

    findings = []
    pools = evidence_claim_lists + ([synth_claims] if synth_claims else [])
    for i in range(len(pools)):
        for j in range(i + 1, len(pools)):
            findings += check_entity_ambiguity(pools[i], pools[j])

    if "expected_entity_outcome" in case:
        # V2_9: both sides state the SAME expansion -> expect NO finding at all
        ok = (len(findings) == 0) == (case["expected_entity_outcome"] == "NO_AMBIGUITY")
        record(cid, TRUE_NEGATIVE if ok else FALSE_POSITIVE, f"findings={findings}")
        return

    # E1b: per the v2 success criterion, EITHER a "high" (evidence states
    # different expansions) or "unresolved" (evidence doesn't establish enough to
    # link OR separate) finding counts as the system correctly NOT silently
    # merging two different acronym referents - only a complete absence of any
    # finding (silent merge) is the real failure this case exists to catch.
    expects_flag = case["expected_verdict"].startswith("FLAG")
    got_flag = len(findings) > 0
    if expects_flag and got_flag:
        record(cid, TRUE_POSITIVE, f"findings={findings} (certainty={[f['certainty'] for f in findings]})")
    elif expects_flag and not got_flag:
        record(cid, FALSE_NEGATIVE, f"expected an entity_ambiguity finding, found none. claims={pools}")
    else:
        record(cid, TRUE_NEGATIVE if not got_flag else FALSE_POSITIVE, f"findings={findings}")


def run_grounding_case(case):
    """Pure-function check of the deterministic grounding invariant itself - no
    LLM call, no cost, exercises is_grounded() directly against a hand-fabricated
    ungrounded quote."""
    cid = case["id"]
    print(f"\n=== {cid} ({case['category']}) check_type=grounding (pure function, no LLM) ===")
    grounded = is_grounded(case["fabricated_evidence_quote"], case["source_text"])
    ok = grounded == case["expected_grounded"]
    record(cid, TRUE_POSITIVE if ok else FALSE_NEGATIVE,
           f"expected_grounded={case['expected_grounded']} got_grounded={grounded} "
           f"(the invariant correctly {'rejected' if not grounded else 'accepted'} the fabricated quote)")


def run_numeric_case(case, provider):
    cid = case["id"]
    print(f"\n=== {cid} ({case['category']}) check_type=numeric ===")
    evidence = case.get("evidence")
    if not evidence or len(evidence) != 2:
        record(cid, UNRESOLVED, "numeric case needs exactly 2 evidence items")
        return
    claim_lists, failure = _extract_all(evidence, provider)
    if failure:
        record(cid, MODEL_FAILURE, f"extraction failed: {failure}")
        return
    a_claims, b_claims = claim_lists
    a_numeric = [c for c in a_claims if c.get("fact_type") and
                 (c.get("value") is not None or c.get("home_value") is not None)]
    b_numeric = [c for c in b_claims if c.get("fact_type") and
                 (c.get("value") is not None or c.get("home_value") is not None)]
    if not a_numeric or not b_numeric:
        record(cid, EXTRACTION_FAILURE, f"model returned no numeric claims for this pair. a={a_claims} b={b_claims}")
        return
    best = None
    for a in a_numeric:
        for b in b_numeric:
            if a["fact_type"] == b["fact_type"]:
                best = (a, b)
                break
        if best:
            break
    if not best:
        record(cid, EXTRACTION_FAILURE, f"no matching fact_type pair extracted. a={a_numeric} b={b_numeric}")
        return
    relationship = classify_numeric_pair(*best)
    expected = case["expected_numeric_relationship"]
    if expected == "NOT_CONTRADICTION":
        ok = relationship != NC_CONTRADICTION
        outcome = TRUE_NEGATIVE if ok else FALSE_POSITIVE
    else:
        ok = relationship == expected
        outcome = TRUE_POSITIVE if ok else FALSE_NEGATIVE
    record(cid, outcome, f"expected={expected} got={relationship} claims=({best[0]},{best[1]})")


def run_real_syndication_case():
    cid = "S1_syndication_real"
    print(f"\n=== {cid} (syndication_dedup) ===")
    articles = [
        {"source": "Reuters", "text": "Ireland manager thanks prime minister for support ahead of Israel fixtures", "tier": "PARTIAL"},
        {"source": "Channel News Asia", "text": "Ireland manager thanks prime minister for support ahead of Israel fixtures", "tier": "PARTIAL"},
        {"source": "The Globe and Mail", "text": "Protests and heated comments as Ireland and Israel prepare for soccer doubleheader", "tier": "PARTIAL"},
        {"source": "Daily Mirror", "text": "Irish government called out as Israel row escalates ahead of Nations League match", "tier": "PARTIAL"},
    ]
    summary = group_summary(group_independent(articles))
    ok = any(g["group_size"] == 2 for g in summary)
    record(cid, TRUE_POSITIVE if ok else FALSE_NEGATIVE, f"groups={summary}")


def run_real_thin_evidence_case():
    cid = "T1_thin_evidence_real"
    print(f"\n=== {cid} (thin_evidence) ===")
    tier = quality_classify(None)
    ok = tier == "METADATA_ONLY"
    record(cid, TRUE_POSITIVE if ok else FALSE_NEGATIVE, f"tier={tier}")


def main():
    provider = get_benchmark_provider()
    groq = get_groq_provider()
    is_paid = bool(provider and provider.get("billed"))
    print(f"Benchmark provider: {provider.get('name') if provider else None} (paid={is_paid}); Groq available separately: {groq is not None}")

    for case in CASES:
        ct = case.get("check_type")
        if ct == "numeric":
            run_numeric_case(case, provider)
        elif ct == "entity":
            run_entity_case(case, provider)
        elif ct == "grounding":
            run_grounding_case(case)
        elif ct in ("status", "domain"):
            run_status_or_domain_case(case, provider)
    run_real_syndication_case()
    run_real_thin_evidence_case()

    print(f"\n{'=' * 70}\nRAW COUNTS (no statistical accuracy claimed from this sample size)")
    counts = Counter(o for _, o, _ in OUTCOMES)
    for k in (TRUE_POSITIVE, TRUE_NEGATIVE, FALSE_POSITIVE, FALSE_NEGATIVE, MODEL_FAILURE, EXTRACTION_FAILURE, UNRESOLVED):
        print(f"  {k}: {counts.get(k, 0)}")

    print(f"\n{'=' * 70}\nGROUNDING / STATUS DISTRIBUTION (section 10)")
    for k, v in GROUNDING_STATS.items():
        print(f"  {k}: {v}")

    print(f"\n{'=' * 70}\nEXIT CRITERION: F1 (real negative control) result")
    f1 = next((o for cid, o, _ in OUTCOMES if cid == "F1_office_holder_negative_control"), None)
    print(f"  F1_office_holder_negative_control -> {f1} "
          f"({'PASS - no unsupported fact was asserted' if f1 == TRUE_NEGATIVE else 'FAIL - see detail above'})")
    v2_1 = next((o for cid, o, _ in OUTCOMES if cid == "V2_1_cm_no_marker_synthetic"), None)
    print(f"  V2_1_cm_no_marker_synthetic (isolated regression of the same pattern) -> {v2_1} "
          f"({'PASS' if v2_1 == TRUE_NEGATIVE else 'FAIL'})")


if __name__ == "__main__":
    main()
