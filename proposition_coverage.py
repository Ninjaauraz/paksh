"""proposition_coverage.py - PROTOTYPE, offline-only, $0 (2026-09-28). Tests the
hypothesis that check_unhedged_downgrade's 81 "omission" findings partly reflect
"one obligation per differently-worded source expression" rather than "one
obligation per genuine underlying fact" - see this session's task text for the
full motivating example (three sources phrasing the same El Nino warning
differently).

NOT wired into production. NOT a replacement for check_unhedged_downgrade,
check_attribution_loss, or detect_conflicts - none of those are modified or
reimplemented here. This module only adds a POLICY LAYER on top of their
existing, unmodified findings: instead of asking "does every individual
evidence claim have an exact-status-preserving synthesis match", it asks
"does every underlying PROPOSITION (a cluster of evidence claims that
claim_clustering.py's already-validated 8-stage gate says are the same
underlying fact) have SOME synthesis claim that addresses it, and if so, at
what level of fidelity."

================================================================================
PHASE 1 - WHAT A "PROPOSITION" IS HERE
================================================================================
A proposition is NOT invented as a new data structure. It is exactly a
claim_clustering.py cluster: a group of evidence claims that already passed
that module's 8-stage compatibility gate (subject -> predicate_family ->
object -> status -> time -> numeric_dimension -> domain -> attribution). That
gate already encodes every distinction this task's Phase 1 lists as
must-not-collapse (CURRENT vs FORMER, ALLEGED vs ESTABLISHED, CHARGED vs
CONVICTED, 10 people vs 10%, Monday vs last year, India vs United States,
Police-accused-X vs X-accused-Police) - reusing it here means this module
inherits all 23 of that file's adversarial guarantees for free, rather than
re-deriving weaker versions of the same rules.

The one thing claim_clustering's gate does NOT decide is STATUS compatibility
in the strict sense this module needs: `_status_compatible()` treats "one side
UNSPECIFIED" as compatible (correctly, for clustering evidence claims from
different sources into one proposition - silence isn't disagreement). But
coverage evaluation needs to ask a sharper question about the SYNTHESIS side
specifically: did the synthesis claim that matches this proposition PRESERVE
the material status/hedge, or silently drop it? That is genuinely a different
question from "is this the same proposition" and is evaluated as a separate
dimension below (never by loosening or duplicating the clustering gate).

================================================================================
PHASE 2 - COVERAGE LEVELS
================================================================================
LEVEL 0  NOT_COVERED            - no synthesis claim addresses this proposition
                                   at all (subject/predicate-family/object/
                                   time/domain/fact_type all match nobody in
                                   the synthesis).
LEVEL 1  PARTIALLY_COVERED      - a synthesis claim addresses the proposition's
                                   core subject/predicate/object, but drops a
                                   material dimension: status/hedge, or (for an
                                   attribution claim) the specific non-routine
                                   attributor's identity.
LEVEL 2  COVERED                - a synthesis claim addresses the proposition
                                   and preserves every material dimension this
                                   module can check, with no hedge/epistemic
                                   status in play.
LEVEL 3  COVERED_WITH_HEDGE     - as COVERED, AND the evidence proposition
                                   itself carried an epistemic hedge (ALLEGED/
                                   CLAIMED/PROPOSED) that the synthesis
                                   correctly preserved (not silently dropped
                                   to UNSPECIFIED, not silently escalated to
                                   an established/confirmed antonym).
CONTRADICTED                    - a matching synthesis claim exists but
                                   asserts a status in STATUS_CONFLICT_PAIRS'
                                   antonym relation to the evidence's status.
                                   Reported as its own outcome (not folded into
                                   NOT_COVERED's "nothing addressed this"
                                   meaning, and not COVERED) - this is a
                                   genuine disagreement, which detect_conflicts
                                   already independently catches; this module
                                   never silences it, only labels it distinctly
                                   so "not covered" and "actively contradicted"
                                   are never conflated in the report.
UNDETERMINABLE                  - the proposition (or every candidate
                                   synthesis claim) is missing the subject/
                                   predicate fields needed to evaluate a match
                                   at all - a real data limitation (see
                                   replay_proposition_coverage.py's docstring
                                   for exactly when this fires on the real
                                   40-story data), never guessed past.

Per the task's explicit instruction (Phase 2): lexical/wording similarity
alone is NEVER sufficient for COVERED. Every stage below is the same
structural (subject-key / predicate-family / object-containment / time /
domain / fact_type) machinery already adversarially validated in
claim_clustering.py and consistency_checks.py - nothing here is a new
similarity heuristic.
"""
from consistency_checks import (
    _norm_subject, _objects_compatible, HIGH_RISK_STATUS_VALUES, STATUS_CONFLICT_PAIRS,
)
from claim_clustering import (
    cluster_evidence_claims, _clustering_subject_key, _predicate_key,
    _time_compatible, _domain_compatible, _is_attribution_claim,
)

try:
    from phase11_verification import _is_routine_attributor
except ImportError:  # pragma: no cover - standalone-import fallback, same as claim_clustering.py
    def _is_routine_attributor(subject):
        return False

NOT_COVERED = "NOT_COVERED"
PARTIALLY_COVERED = "PARTIALLY_COVERED"
COVERED = "COVERED"
COVERED_WITH_HEDGE = "COVERED_WITH_HEDGE"
CONTRADICTED = "CONTRADICTED"
UNDETERMINABLE = "UNDETERMINABLE"

# Phase 5: a small, fixed set of statuses that are themselves an epistemic hedge
# (not merely "high risk" - HIGH_RISK_STATUS_VALUES also includes CURRENT/FORMER/
# etc, which are matters of fact, not hedges). Preserving a hedge correctly is
# COVERED_WITH_HEDGE (Level 3); silently dropping it to UNSPECIFIED is
# PARTIALLY_COVERED (Level 1, same as any other status loss); silently
# escalating it to the matching ESTABLISHED/CONFIRMED antonym is CONTRADICTED,
# not COVERED - "X allegedly happened" must never register as covering
# "X happened" (Phase 2's explicit example).
HEDGE_STATUS_VALUES = {"ALLEGED_EXPLICIT", "CLAIMED_EXPLICIT", "PROPOSED_EXPLICIT"}


def _proposition_identity_match(member, synth_claim, generic_epistemic_sources=False):
    """True if synth_claim addresses the SAME underlying proposition as
    `member`, deliberately IGNORING status (status/hedge preservation is what
    coverage level measures, not what identity matching gates on - conflating
    the two would make it impossible to ever detect a downgrade, since a
    status-losing synthesis claim would just fail to match at all). Reuses
    exactly the non-status stages of claim_clustering's 8-stage gate: subject
    (with its routine-attributor / opt-in generic-epistemic exceptions),
    predicate family, object compatibility, time compatibility, numeric
    dimension (fact_type), domain. No new matching logic is introduced here."""
    if _clustering_subject_key(member, generic_epistemic_sources) != _clustering_subject_key(synth_claim, generic_epistemic_sources):
        return False
    if _predicate_key(member.get("predicate")) != _predicate_key(synth_claim.get("predicate")):
        return False
    if not _objects_compatible(member.get("object"), synth_claim.get("object")):
        return False
    if not _time_compatible(member, synth_claim):
        return False
    fa, fb = member.get("fact_type"), synth_claim.get("fact_type")
    if fa and fb and fa != fb:
        return False
    if not _domain_compatible(member, synth_claim):
        return False
    return True


def _status_relationship(evidence_status, synth_status):
    """-> 'preserved' | 'dropped' | 'contradicted' | 'not_material'."""
    if evidence_status in (None, "UNSPECIFIED"):
        return "not_material"
    if synth_status in (None, "UNSPECIFIED"):
        return "dropped"
    if synth_status == evidence_status:
        return "preserved"
    if frozenset({evidence_status, synth_status}) in STATUS_CONFLICT_PAIRS:
        return "contradicted"
    return "preserved"  # differing but not a known antonym pair - same conservative
    # default as claim_clustering._status_compatible: not a proven disagreement


def _evaluate_member_against_synthesis(member, synthesis_claims, generic_epistemic_sources):
    """-> (coverage_level, matched_claims, missing_dimensions, reason) for ONE
    evidence claim against the full synthesis claim pool."""
    matches = [s for s in synthesis_claims if _proposition_identity_match(member, s, generic_epistemic_sources)]
    if not matches:
        missing = []
        if _is_attribution_claim(member) and not _is_routine_attributor(member.get("subject")):
            missing.append("attribution")
        return NOT_COVERED, [], missing, (
            "no synthesis claim shares this proposition's subject/predicate-family/"
            "object/time/domain/fact_type"
        )

    ev_status = member.get("status")
    is_hedge = ev_status in HEDGE_STATUS_VALUES
    is_high_risk = ev_status in HIGH_RISK_STATUS_VALUES

    # Prefer a match that PRESERVES status if any exists; else report on the
    # best (least-lossy) available match - never silently pick a losing match
    # when a preserving one is available.
    rels = [(_status_relationship(ev_status, s.get("status")), s) for s in matches]
    if any(r == "preserved" for r, _ in rels):
        rel, best = next((r, s) for r, s in rels if r == "preserved")
    elif any(r == "contradicted" for r, _ in rels):
        rel, best = next((r, s) for r, s in rels if r == "contradicted")
    else:
        rel, best = rels[0]

    if rel == "contradicted":
        return CONTRADICTED, matches, ["status"], (
            f"synthesis claim asserts {best.get('status')} but evidence states {ev_status} "
            f"for the same proposition"
        )
    if rel == "dropped" and is_high_risk:
        missing = ["status"]
        return PARTIALLY_COVERED, matches, missing, (
            f"a synthesis claim addresses this proposition but drops its {ev_status} status/hedge"
        )
    # rel == "preserved" or (rel == "dropped" and not is_high_risk) or "not_material"
    if is_hedge and rel == "preserved":
        return COVERED_WITH_HEDGE, matches, [], (
            f"synthesis claim preserves the {ev_status} hedge for this proposition"
        )
    return COVERED, matches, [], "a synthesis claim addresses this proposition with no material dimension lost"


_LEVEL_RANK = {NOT_COVERED: 0, CONTRADICTED: 0, UNDETERMINABLE: 0,
               PARTIALLY_COVERED: 1, COVERED: 2, COVERED_WITH_HEDGE: 3}


def evaluate_proposition_coverage(evidence_claims, synthesis_claims, generic_epistemic_sources=False):
    """Phase 3's suggested API. evidence_claims: flat list of evidence claim
    dicts (claim_extraction.py v2 schema, or the same shape reconstructed from
    reason strings - see replay_proposition_coverage.py for that path).
    synthesis_claims: flat list of synthesis claim dicts, same schema.

    -> list of proposition coverage-result dicts:
      {proposition_id, coverage_level, matched_synthesis_claims,
       unmatched_evidence_members, missing_material_dimensions, reason,
       source_count, member_claims, provenance, confidence}

    Step 1: cluster evidence_claims into propositions via claim_clustering's
    own, already-validated cluster_evidence_claims() - never a separate/
    duplicated grouping mechanism.
    Step 2: for each proposition (cluster), evaluate every member claim
    against the synthesis pool, and take the proposition's overall coverage
    level as the BEST (least-lossy) level achieved by ANY member - this is
    the direct operationalization of "one obligation per proposition, not per
    source expression": if ANY of the N differently-worded source claims in
    this cluster is addressed by the synthesis, the proposition as a whole is
    covered at that level; a member NOT individually matched is recorded in
    unmatched_evidence_members but does not by itself downgrade a proposition
    that another member's match already covers - it is redundant with the
    covering member specifically because clustering already established they
    are the same underlying fact."""
    if not evidence_claims:
        return []
    clusters, _comparisons = cluster_evidence_claims(evidence_claims, generic_epistemic_sources)
    results = []
    for pid, cluster in enumerate(clusters):
        members = cluster["member_claims"]
        determinable_members = [m for m in members if m.get("subject") and m.get("predicate")]
        if not determinable_members:
            results.append({
                "proposition_id": pid, "coverage_level": UNDETERMINABLE,
                "matched_synthesis_claims": [], "unmatched_evidence_members": members,
                "missing_material_dimensions": [], "source_count": cluster["source_count"],
                "member_claims": members, "provenance": "MISSING", "confidence": "undeterminable",
                "reason": "no member claim carries both subject and predicate - cannot evaluate a match",
            })
            continue

        per_member = [(m, *_evaluate_member_against_synthesis(m, synthesis_claims, generic_epistemic_sources))
                      for m in determinable_members]
        best_level = max((lvl for _, lvl, *_ in per_member), key=lambda l: _LEVEL_RANK[l])
        best_entries = [e for e in per_member if e[1] == best_level]
        _, _, matched, missing_dims, reason = best_entries[0]
        unmatched = [m for m, lvl, matched_c, _, _ in per_member if not matched_c]
        # a CONTRADICTED finding anywhere must never be silently outranked by a
        # different member's COVERED match - both are real, independent signals
        # about the same proposition, so surface CONTRADICTED explicitly if present
        contradicted_entries = [e for e in per_member if e[1] == CONTRADICTED]

        results.append({
            "proposition_id": pid,
            "coverage_level": best_level,
            "matched_synthesis_claims": matched,
            "unmatched_evidence_members": unmatched,
            "missing_material_dimensions": missing_dims,
            "also_contradicted": bool(contradicted_entries) and best_level != CONTRADICTED,
            "source_count": cluster["source_count"],
            "member_claims": members,
            "provenance": "DERIVED_OFFLINE",
            "confidence": "structural",
            "reason": reason,
        })
    return results
