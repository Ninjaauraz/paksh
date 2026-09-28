"""phase10_synthesis.py - Phase 10 PROTOTYPE: strong-model routing + evidence-bound
synthesis. NOT wired into production - analyze.py/build_prompt() and
ai_providers.py's PROVIDERS list are both untouched. The "gemini_strong" provider
below is a plain local dict, never inserted into ai_providers.PROVIDERS, so
ai_providers.active_providers() and every existing caller of the real pool sees
EXACTLY the same providers as before this file existed.

Routing (route_synthesis) is deliberately just rule evaluation over the
deterministic Phase 8/9 findings already computed elsewhere in this prototype -
no opaque difficulty scoring, no new heuristic beyond the five conditions the
2026-09-28 Phase 10/11 task specified.
"""
import ai_providers
from consistency_checks import HIGH_RISK_STATUS_VALUES

# Reuses the SAME key as the existing "gemini" entry in ai_providers.PROVIDERS
# (GEMINI_API_KEY) via an explicit key_env override - ai_providers._key_env()
# supports this by design. This dict is never added to ai_providers.PROVIDERS,
# so ai_providers.active_providers() / the real pool are completely unaffected.
GEMINI_STRONG_PROVIDER = {
    "name": "gemini_strong",
    "enabled": True,
    "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
    # UPDATED 2026-09-28: "gemini-2.5-pro" (this file's original choice, verified
    # present in a ListModels call earlier in this session) started returning
    # HTTP 404 "no longer available to new users" during THIS run - confirmed via
    # a direct isolated call, not assumed. Google's own error body names the
    # replacement; switched to it rather than silently falling back to the flash
    # tier. This is exactly the preview/latest-alias volatility risk flagged when
    # gemini-2.5-pro was first proposed as the strong-model candidate.
    "model": "gemini-3.1-pro-preview",
    "key_env": "GEMINI_API_KEY",
    "billed": True,
}



def route_synthesis(pre_synthesis_conflicts, entity_findings, numeric_relationships, evidence_claims):
    """Deterministic, inspectable routing decision.
    pre_synthesis_conflicts: detect_conflicts() output (evidence group vs evidence
        group, i.e. Phase 9's pre-synthesis pairwise pass).
    entity_findings: check_entity_ambiguity() output, evidence vs evidence.
    numeric_relationships: list of classify_numeric_pair() relationship strings
        for evidence-vs-evidence pairs (Phase 9's numeric dimension).
    evidence_claims: flat list of every evidence claim for this story (used for
        conditions D/E, which look at evidence content directly, not conflicts).
    -> {"model": "gemini_strong" | "pool", "reasons": [...]}. Never logs prompts,
    keys, or credentials - reasons are short fixed labels only."""
    reasons = []

    # A. PRE_SYNTHESIS_CONFLICT - a substantive (certainty=="high") conflict
    if any(c.get("certainty") == "high" for c in pre_synthesis_conflicts):
        reasons.append("PRE_SYNTHESIS_CONFLICT")

    # B. ENTITY_AMBIGUITY - any finding at all (both "high" and "unresolved" are
    # substantive per the task's own E1b scoring precedent: either means the
    # system must not silently treat two claims as the same entity)
    if entity_findings:
        reasons.append("ENTITY_AMBIGUITY")

    # C. NUMERIC_CONFLICT - only a genuine CONTRADICTION counts as "substantive";
    # ROUNDING/APPROXIMATION/COMPATIBLE/DIFFERENT_SCOPE/DIFFERENT_TIME/LATER_UPDATE
    # are legitimate, non-conflicting explanations and must not trigger routing
    if any(r == "CONTRADICTION" for r in numeric_relationships):
        reasons.append("NUMERIC_CONFLICT")

    # D. HIGH_RISK_STATUS - any evidence claim carries an explicit office-holder/
    # allegation/legal-status marker
    if any(c.get("status") in HIGH_RISK_STATUS_VALUES for c in evidence_claims):
        reasons.append("HIGH_RISK_STATUS")

    # E. POPULATED_DOMAIN - any evidence claim tags a domain
    if any(c.get("domain") for c in evidence_claims):
        reasons.append("POPULATED_DOMAIN")

    if reasons:
        return {"model": "gemini_strong", "reasons": reasons}
    return {"model": "pool", "reasons": []}


# ---- Evidence-bound synthesis prompt -----------------------------------------------
# Verbatim status-preservation rule from the Phase 10/11 task, with the semantic-
# preservation clarification folded in (matches claim_extraction.py's own v2
# semantic-recognition update - same principle applied one level up, to prose
# instead of structured extraction).
_STATUS_RULE = """Never write former, current, alleged, confirmed, incoming, appointed, elected,
resigned, serving, charged, convicted, proposed, established, etc. about a person,
event, or claim unless the supplied evidence contains an equivalent status assertion
for that exact subject.

If the evidence is silent on status, write the sentence without adding a status claim.

Preserve evidence-supported qualifications semantically even when the wording
changes - e.g. evidence saying "former Chief Minister" may be written as "previously
served as chief minister" and this still counts as preserving the qualification, not
dropping it. The test is whether the MEANING survives, not whether the same word is
reused.

Do not resolve conflicting evidence using outside knowledge. If the supplied evidence
remains unresolved, preserve the uncertainty (state both positions with attribution,
do not silently pick one)."""

_SYNTHESIS_PROMPT = """You write a single neutral synthesis paragraph from the evidence
below. Use ONLY what the evidence states.

{status_rule}

EVIDENCE (each item is a real, verbatim-grounded claim extracted from a real source):
{evidence_block}

{conflict_block}
Write one neutral synthesis paragraph (3-5 sentences) covering what the evidence
establishes. Do not add outlet-by-outlet narration ("Outlet A says... Outlet B
says...") - write one coherent account.
"""


def _format_evidence_block(evidence_claims):
    lines = []
    for c in evidence_claims:
        prov = c.get("provenance", {})
        lines.append(f"- [{prov.get('source', 'unknown')}] \"{c.get('evidence_quote', '')}\"")
    return "\n".join(lines)


def _format_conflict_block(pre_synthesis_conflicts, numeric_relationships_detail):
    if not pre_synthesis_conflicts and not numeric_relationships_detail:
        return ""
    lines = ["KNOWN EVIDENCE CONFLICTS (resolve only using the evidence above, or preserve both positions with attribution):"]
    for c in pre_synthesis_conflicts:
        lines.append(f"- {c.get('type')}: {c.get('reason')}")
    for r in numeric_relationships_detail:
        if r.get("relationship") == "CONTRADICTION":
            lines.append(f"- numeric_contradiction: {r['claim_a'].get('evidence_quote')!r} vs {r['claim_b'].get('evidence_quote')!r}")
    return "\n".join(lines) + "\n"


def synthesize(evidence_claims, route, pre_synthesis_conflicts=None, numeric_relationships_detail=None,
               regenerate_feedback=None, provider_override=None):
    """route: route_synthesis()'s return value. When route["model"]=="gemini_strong",
    this actually calls the strong model (the new capability under test). When
    route["model"]=="pool", this prototype does NOT call the real production pool
    dispatch (that logic lives in analyze.py and is out of scope/untouched) -
    it returns a note saying so, so callers/tests can distinguish "would use the
    existing pool" from an actual generation, without this file reimplementing or
    touching analyze.py's dispatch.
    regenerate_feedback: optional str - a specific prior verification finding to
    correct, appended to the prompt for a REGENERATE attempt (Phase 11's policy;
    never a bare "try again").
    -> (text, status) where status is "ok" or a claim_extraction-style failure
    code, or "NOT_EXERCISED:pool_path" for the non-strong route."""
    if route["model"] != "gemini_strong":
        return None, "NOT_EXERCISED:pool_path"
    provider = provider_override or GEMINI_STRONG_PROVIDER
    evidence_block = _format_evidence_block(evidence_claims)
    conflict_block = _format_conflict_block(pre_synthesis_conflicts or [], numeric_relationships_detail or [])
    prompt = _SYNTHESIS_PROMPT.format(status_rule=_STATUS_RULE, evidence_block=evidence_block, conflict_block=conflict_block)
    if regenerate_feedback:
        prompt += f"\n\nA PRIOR DRAFT HAD THIS SPECIFIC PROBLEM - fix it using only the evidence above:\n{regenerate_feedback}\n"
    try:
        text = ai_providers.chat_with_provider(provider, prompt, as_json=False)
    except Exception as e:
        from claim_extraction import _classify_exception
        return None, _classify_exception(e)
    return text.strip(), "ok"
