"""shadow_trial.py - Phase 13 PROTOTYPE: the 100-story shadow trial. READ-ONLY
against the production DB (opened with PRAGMA query_only=1, same discipline as
every other script in this audit). Writes results ONLY to a local JSON/JSONL
report file - never to _site, never to the DB, never via live.py.

Scope decision, stated explicitly rather than assumed: evidence input for the new
pipeline is each event's member articles' TITLES (the same text every benchmark
case in this audit has used as "evidence"), not live-fetched full article bodies.
Phase 1 of this audit measured that 66% of article URLs are unfetchable Google
News wrappers - live-fetching full text for 100 stories' worth of articles is a
separate, much larger undertaking (and a separate cost/time budget) than what
this trial is built to test: the claim-extraction/consistency/synthesis/
verification layer (Phases 7-11), not the evidence-acquisition layer (Phase 2-6)
in isolation. This mirrors the input basis used in every earlier benchmark round.

For each sampled story:
  1. CURRENT: read the already-published summary/framing straight from
     analysis_json (production's real output - read-only, never regenerated).
  2. NEW PIPELINE: gather member-article claims via claim_extraction (evidence-
     bound), run consistency_checks/numeric_consistency (Phase 8/9) for
     pre-synthesis conflicts, route via phase10_synthesis.route_synthesis, run
     synthesis (strong model only when routed there, otherwise the standard
     "gemini" pool provider - matching the actual cost-aware design intent, not
     blanket strong-model use), then phase11_verification (symmetric +
     unhedged_downgrade + attribution_loss) with bounded regeneration.
  3. Compare: does the NEW pipeline's verification find anything CURRENT
     production's published text doesn't already avoid? Record structured
     findings for both.

Checkpointed: writes one JSON line per completed story to the report file
immediately, so an interruption (rate limit, crash) loses no completed work -
resume by skipping story ids already present in the report file.
"""
import json
import os
import time

import database
import claim_extraction
from claim_extraction import extract_claims, is_model_failure, RATE_LIMIT
from consistency_checks import detect_conflicts, check_entity_ambiguity
from evidence_assembly import group_independent, group_summary
from numeric_consistency import classify_numeric_pair, CONTRADICTION as NC_CONTRADICTION
from phase10_synthesis import GEMINI_STRONG_PROVIDER, route_synthesis, synthesize
from phase11_verification import (
    check_unhedged_downgrade, check_attribution_loss, decide, format_regenerate_feedback,
    verify_symmetric, PASS, REGENERATE, HOLD,
)

REPORT_PATH = os.path.join(os.path.dirname(__file__), "shadow_trial_report.jsonl")
SAMPLE_PATH = os.path.join(os.path.dirname(__file__), "shadow_trial_sample.json")

POOL_PROVIDER = None  # resolved lazily to the standard "gemini" provider, matching cost-aware design intent
MAX_TRANSIENT_RETRIES = 2
RETRY_WAIT_S = 20


def _pool_provider():
    global POOL_PROVIDER
    if POOL_PROVIDER is None:
        POOL_PROVIDER = claim_extraction.get_paid_provider() or claim_extraction.get_groq_provider()
    return POOL_PROVIDER


def _with_retry(fn, *args, **kwargs):
    for attempt in range(MAX_TRANSIENT_RETRIES + 1):
        result = fn(*args, **kwargs)
        status = result[1] if isinstance(result, tuple) and len(result) > 1 else None
        if status != RATE_LIMIT or attempt == MAX_TRANSIENT_RETRIES:
            return result
        time.sleep(RETRY_WAIT_S)
    return result


def already_done_ids():
    done = set()
    if os.path.exists(REPORT_PATH):
        with open(REPORT_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        done.add(json.loads(line)["event_id"])
                    except Exception:
                        continue
    return done


def gather_evidence_claims(event, provider):
    """-> (independent_groups_summary, flat_claims, per_group_claims). Uses
    article TITLES as evidence text (see module docstring's scope decision)."""
    articles = event.get("sources") or []
    art_dicts = [{"source": a.get("source") or a.get("owner") or "unknown", "text": a.get("headline") or a.get("title") or "", "tier": "PARTIAL"}
                 for a in articles if (a.get("headline") or a.get("title"))]
    if not art_dicts:
        return [], [], []
    groups = group_independent(art_dicts)
    summary = group_summary(groups)
    per_group_claims = []
    flat_claims = []
    for g in summary:
        claims, status, _stats = _with_retry(extract_claims, g["representative_text"], source=g["representative_source"], provider=provider)
        if is_model_failure(status):
            per_group_claims.append((status, []))
            continue
        for c in claims:
            c["group_size"] = g["group_size"]
        per_group_claims.append((status, claims))
        flat_claims.extend(claims)
    return summary, flat_claims, per_group_claims


def run_one_story(event_id, provider):
    events_by_id = database.get_events_by_ids([event_id])
    if event_id not in events_by_id:
        return {"event_id": event_id, "error": "not_found"}
    event = events_by_id[event_id]
    result = {
        "event_id": event_id,
        "title": event.get("title"),
        "topic": event.get("topic"),
        "region": event.get("region"),
        "source_count": len(event.get("sources") or []),
    }

    # --- CURRENT (production's already-published output, read-only) ---
    result["current_summary"] = (event.get("summary") or "")[:500]
    result["current_evidence_status"] = event.get("evidence_status")

    # --- NEW PIPELINE ---
    group_summary_list, flat_claims, per_group_claims = gather_evidence_claims(event, _pool_provider())
    model_failures = [s for s, _ in per_group_claims if is_model_failure(s)]
    result["evidence_groups"] = len(group_summary_list)
    result["evidence_model_failures"] = len(model_failures)
    if not flat_claims:
        result["new_pipeline"] = "NO_CLAIMS_EXTRACTED"
        return result

    # Phase 9: pre-synthesis pairwise checks across independent groups
    pre_conflicts = []
    numeric_rels = []
    claims_lists = [c for _, c in per_group_claims if c]
    for i in range(len(claims_lists)):
        for j in range(i + 1, len(claims_lists)):
            pre_conflicts += detect_conflicts(claims_lists[i], claims_lists[j])
            pre_conflicts += [{"type": "entity_ambiguity", **f} for f in check_entity_ambiguity(claims_lists[i], claims_lists[j])]
            for a in claims_lists[i]:
                if a.get("fact_type") is None:
                    continue
                for b in claims_lists[j]:
                    if b.get("fact_type") != a.get("fact_type"):
                        continue
                    rel = classify_numeric_pair(a, b)
                    numeric_rels.append(rel)
                    if rel == NC_CONTRADICTION:
                        pre_conflicts.append({"type": "numeric_conflict", "certainty": "high"})

    route = route_synthesis(pre_conflicts, [f for f in pre_conflicts if f.get("type") == "entity_ambiguity"], numeric_rels, flat_claims)
    result["route"] = route

    # synthesize() only actually calls out when route["model"]=="gemini_strong" (see
    # phase10_synthesis's own gate) - for the shadow trial we still need SOME
    # synthesis text to verify against on the pool path too, for comparability, so
    # we always pass a route whose model field says "gemini_strong" (that string
    # only tells synthesize() whether to proceed, not which provider - the actual
    # provider is chosen right here, honoring the REAL routing decision in `route`)
    synth_provider = GEMINI_STRONG_PROVIDER if route["model"] == "gemini_strong" else _pool_provider()
    text, status = _with_retry(synthesize, flat_claims, {"model": "gemini_strong", "reasons": route["reasons"] or ["SHADOW_TRIAL_POOL_PATH"]},
                                pre_synthesis_conflicts=pre_conflicts, provider_override=synth_provider)
    if is_model_failure(status):
        result["new_pipeline"] = f"MODEL_FAILURE:{status}"
        return result
    result["new_synthesis"] = text[:500]

    outcome, reason, findings_summary = None, None, []
    regen_count = 0
    feedback = None
    for attempt in range(3):
        if attempt > 0:
            regen_count += 1
            gen_text, gen_status = _with_retry(synthesize, flat_claims, {"model": "gemini_strong", "reasons": ["REGEN"]},
                                                pre_synthesis_conflicts=pre_conflicts, regenerate_feedback=feedback, provider_override=synth_provider)
            if is_model_failure(gen_status):
                outcome, reason = HOLD, f"model_failure_during_regen:{gen_status}"
                break
            text = gen_text
        sym_findings, sym_status, synth_claims = _with_retry(verify_symmetric, flat_claims, text, provider=_pool_provider())
        if is_model_failure(sym_status):
            outcome, reason = HOLD, f"model_failure_during_verify:{sym_status}"
            break
        downgrade = check_unhedged_downgrade(flat_claims, synth_claims)
        attribution = check_attribution_loss(flat_claims, synth_claims)
        all_findings = sym_findings + attribution
        findings_summary = [f.get("reason") for f in all_findings + downgrade]
        outcome, reason = decide(all_findings, downgrade, sym_status, regenerate_attempt=attempt)
        if outcome != REGENERATE:
            break
        feedback = format_regenerate_feedback(all_findings + downgrade)

    result["new_pipeline_outcome"] = outcome
    result["new_pipeline_reason"] = reason
    result["new_pipeline_findings"] = findings_summary
    result["regeneration_attempts"] = regen_count
    return result


def run_trial(sample_ids, limit=None):
    done = already_done_ids()
    todo = [i for i in sample_ids if i not in done]
    if limit:
        todo = todo[:limit]
    print(f"{len(done)} already done, {len(todo)} to process this invocation")
    provider = _pool_provider()
    print(f"pool provider: {provider.get('name') if provider else None}")
    for idx, eid in enumerate(todo):
        print(f"[{idx + 1}/{len(todo)}] story {eid}...", end=" ", flush=True)
        try:
            result = run_one_story(eid, provider)
        except Exception as e:
            result = {"event_id": eid, "error": f"{type(e).__name__}:{e}"}
        with open(REPORT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
        print(result.get("new_pipeline_outcome") or result.get("new_pipeline") or result.get("error"))


if __name__ == "__main__":
    with open(SAMPLE_PATH, encoding="utf-8") as f:
        sample = json.load(f)
    run_trial([s["id"] for s in sample])
