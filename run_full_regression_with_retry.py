"""run_full_regression_with_retry.py - bounded retry-with-wait orchestration around
run_benchmark_prototype.py's existing per-case functions. Does NOT modify any case
definition/label - imports factuality_benchmark.CASES unchanged and calls the same
run_status_or_domain_case/run_numeric_case/run_entity_case/run_grounding_case
functions run_benchmark_prototype.py already defines, just wraps each case attempt
in a bounded retry loop (Groq's small 60s TPM window recovers quickly, unlike a
monthly billing cap) and reports exactly which cases remain blocked if retries are
exhausted - never silently drops a case, never counts MODEL_FAILURE as TP/TN/FP/FN.

Run:  py run_full_regression_with_retry.py
"""
import time

import claim_extraction
import run_benchmark_prototype as base
from factuality_benchmark import CASES

MAX_ROUNDS = 4
WAIT_BETWEEN_ROUNDS_S = 65  # Groq's TPM budget is a 60s sliding window




def run_with_retry():
    provider = claim_extraction.get_groq_provider()
    print(f"Forcing provider=groq for this run (Gemini hard-blocked by monthly spend cap - confirmed via a direct isolated call, not assumed).")

    pending = [c for c in CASES if c.get("check_type")]
    round_num = 0
    while pending and round_num < MAX_ROUNDS:
        round_num += 1
        print(f"\n{'#' * 70}\nROUND {round_num}: {len(pending)} case(s) to attempt\n{'#' * 70}")
        still_pending = []
        for case in pending:
            ct = case["check_type"]
            cid = case["id"]
            before_len = len(base.OUTCOMES)
            if ct == "numeric":
                base.run_numeric_case(case, provider)
            elif ct == "entity":
                base.run_entity_case(case, provider)
            elif ct == "grounding":
                base.run_grounding_case(case)
            elif ct in ("status", "domain"):
                base.run_status_or_domain_case(case, provider)
            # the just-appended entry (index before_len) is THIS attempt's result -
            # never scan from the start of OUTCOMES, which could return a stale
            # result from an earlier retry round for the same case id
            if len(base.OUTCOMES) > before_len:
                _, outcome, detail = base.OUTCOMES[before_len]
            else:
                outcome, detail = None, None
            if outcome == base.MODEL_FAILURE and detail and "RATE_LIMIT" in detail:
                still_pending.append(case)
        pending = still_pending
        if pending and round_num < MAX_ROUNDS:
            print(f"\n{len(pending)} case(s) hit RATE_LIMIT this round: {[c['id'] for c in pending]}")
            print(f"Waiting {WAIT_BETWEEN_ROUNDS_S}s for Groq's TPM window to clear before retry round {round_num + 1}...")
            time.sleep(WAIT_BETWEEN_ROUNDS_S)

    base.run_real_syndication_case()
    base.run_real_thin_evidence_case()

    # De-duplicate OUTCOMES: keep only the LAST recorded outcome per case id (a
    # case retried across rounds appears multiple times; the final round's result
    # is authoritative, earlier RATE_LIMIT attempts must not be double-counted)
    final = {}
    for cid, outcome, detail in base.OUTCOMES:
        final[cid] = (outcome, detail)

    print(f"\n{'=' * 70}\nFINAL RAW COUNTS (deduplicated across retry rounds, n={len(final)})")
    from collections import Counter
    counts = Counter(o for o, _ in final.values())
    for k in (base.TRUE_POSITIVE, base.TRUE_NEGATIVE, base.FALSE_POSITIVE, base.FALSE_NEGATIVE,
              base.MODEL_FAILURE, base.EXTRACTION_FAILURE, base.UNRESOLVED):
        print(f"  {k}: {counts.get(k, 0)}")

    still_blocked = [cid for cid, (o, d) in final.items() if o == base.MODEL_FAILURE]
    if still_blocked:
        print(f"\nSTILL BLOCKED after {round_num} round(s) (rate-limited every attempt): {still_blocked}")
    else:
        print(f"\nNo cases remain blocked - all {len(final)} cases resolved to a real outcome.")

    return final


if __name__ == "__main__":
    run_with_retry()
