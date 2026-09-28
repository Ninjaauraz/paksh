"""phase11_verification.py - Phase 11 PROTOTYPE: post-synthesis verification.
NOT wired into production.

Two genuinely different checks, matching the 2026-09-28 Phase 10/11 task's own
distinction:

  11a (verify_symmetric): re-extracts claims from the SYNTHESIS text with the same
      evidence-bound extractor, then runs the SAME deterministic machinery already
      built (detect_conflicts / check_entity_ambiguity / classify_numeric_pair)
      between evidence claims and synthesis claims. Catches EXPLICIT-vs-opposite-
      EXPLICIT contradictions - "evidence says FORMER, synthesis says CURRENT".

  11b (check_unhedged_downgrade): a NEW, deliberately asymmetric check with two
      directions that mean different things:
        - DOWNGRADE: evidence is EXPLICIT (high-risk family), synthesis's matching
          claim is UNSPECIFIED or missing -> synthesis silently dropped a real
          hedge (the F1b pattern).
        - UNSUPPORTED_ADDITION: evidence is UNSPECIFIED or has no matching claim,
          synthesis's claim is EXPLICIT -> synthesis invented an unsupported
          status. This direction MUST live here, not in detect_conflicts(): a
          symmetric conflict check can never catch it by construction (an
          UNSPECIFIED claim never conflicts with anything - that guard is what
          fixed the original F1 false positive, and weakening it to catch this
          case here would silently reopen that exact bug for every other
          UNSPECIFIED evidence claim in the corpus). Both directions reuse
          consistency_checks' predicate-family matching (Fix 1), so "previously
          served as chief minister" correctly matches a "holds the role of"
          evidence claim without literal wording, and "was accused of"
          correctly matches an "allege" claim.

No production mutation anywhere in this file. No second publication-state system:
the HOLD outcome maps onto a documented (not-yet-applied) extension of
database.py's compute_evidence_status() enum - see CONTRADICTED_UNRESOLVED's
docstring below for exactly what would need to change there, which this
prototype does not touch.

  11c (check_attribution_loss): a THIRD, separate, non-blocking check added
      2026-09-28 after P11_4 surfaced a genuinely different question from status
      preservation - the synthesis passively dropped WHO was making an
      allegation ("Police allege" -> "was accused of"), while the ALLEGED status
      itself matched correctly. Diagnosis (recorded in full in this session):
      attribution-source loss is not an epistemic-status problem and must never
      be conflated with check_unhedged_downgrade - it is only worth flagging
      (as a review-queue signal, never REGENERATE/HOLD) when the dropped
      attributor is NOT a routine, uncontested institutional authority (police,
      courts, election officials, doctors, etc. performing their ordinary
      function) - i.e. when it could plausibly be an interested party or an
      unverified/anonymous source, where losing the identity materially changes
      how a reader should weigh the claim. A fixed, small keyword lexicon
      (_ROUTINE_INSTITUTIONAL_ATTRIBUTORS), same size/character as
      consistency_checks.DOMAIN_KEYWORDS - NOT a semantic classifier, NOT
      broadened entity matching (the underlying action claim's subject/object
      matching is completely untouched by this), NOT weakened subject matching.
"""
import re

from claim_extraction import extract_claims, is_model_failure
from consistency_checks import detect_conflicts, check_entity_ambiguity, _same_claim_key, _norm_subject, HIGH_RISK_STATUS_VALUES
from numeric_consistency import classify_numeric_pair, CONTRADICTION as NC_CONTRADICTION

# Fixed, small lexicon of routine institutional attributors - subjects performing
# their ordinary, uncontested function are safely genericizable; anyone/anything
# NOT on this list defaults to "must preserve" (the safe direction - an unknown
# attributor is treated as potentially interested/unverified, never assumed
# neutral). Sized to the worked examples in this session's diagnosis, not an
# exhaustive ontology of every possible neutral authority.
_ROUTINE_INSTITUTIONAL_ATTRIBUTORS = {
    "police", "court", "courts", "judge", "officials", "authorities",
    "doctors", "election commission", "election officials", "government",
}


def _is_routine_attributor(subject):
    s = _norm_subject(subject)
    return any(s == a or s.startswith(a + " ") or a in s.split() for a in _ROUTINE_INSTITUTIONAL_ATTRIBUTORS)


_ATTRIBUTION_PREDICATES = {"allege", "alleges", "alleged", "accuse", "accused", "accuses",
                            "claim", "claims", "claimed", "report", "reports", "reported"}


def check_attribution_loss(evidence_claims, synthesis_claims):
    """-> list of {type: "attribution_loss", category: "attribution_loss",
    certainty: "requires_context", evidence_claim, reason}. Fires ONLY when:
      (a) an evidence claim's predicate is an attribution verb (allege/accuse/
          claim/report - a small fixed set, not the full LEGAL_PROCEEDING family,
          since this check is specifically about WHO says something, not what
          status the underlying action carries - that is check_unhedged_downgrade's
          job, unchanged and unaffected by this function);
      (b) that claim's subject is NOT a routine institutional attributor;
      (c) no synthesis claim shares that exact subject (normalized) at all -
          i.e. the specific attributor vanished entirely, not merely reworded.
    Never touches decide()'s REGENERATE/HOLD path directly - callers fold this
    into the same list as verify_symmetric's findings, which decide() already
    filters by certainty=="high" only."""
    findings = []
    for e in evidence_claims:
        pred = (e.get("predicate") or "").strip().lower()
        words = set(re.findall(r"[a-z]+", pred))
        if not (words & _ATTRIBUTION_PREDICATES):
            continue
        if _is_routine_attributor(e.get("subject")):
            continue
        subj_norm = _norm_subject(e.get("subject"))
        if any(_norm_subject(s.get("subject")) == subj_norm for s in synthesis_claims):
            continue  # the attributor still appears somewhere in the synthesis
        findings.append({
            "type": "attribution_loss", "category": "attribution_loss", "certainty": "requires_context",
            "evidence_claim": e, "synthesis_claim": None,
            "reason": f"evidence attributes this claim to '{e.get('subject')}' (not a routine institutional "
                      f"source) but the synthesis drops this attribution entirely",
        })
    return findings

PASS = "PASS"
REGENERATE = "REGENERATE"
HOLD = "HOLD"

MAX_REGENERATE_ATTEMPTS = 2

# CONTRADICTED_UNRESOLVED: the HOLD-outcome label this prototype uses internally.
# Mapping onto the REAL evidence-status enum (analyze.py::compute_evidence_status,
# consumed by database.py::_is_publishable), documented but NOT applied here:
#   database._is_publishable() currently reads:
#     e.get("evidence_status") not in ("NEEDS_REVIEW", "INSUFFICIENT_EVIDENCE")
#   i.e. it is a DENYLIST, not an allowlist - any value other than those two
#   literal strings is currently treated as publishable. Introducing
#   CONTRADICTED_UNRESOLVED as a new evidence_status value therefore REQUIRES a
#   one-line change to that denylist (add "CONTRADICTED_UNRESOLVED" to the tuple)
#   before this could safely gate anything in production - without that change,
#   a CONTRADICTED_UNRESOLVED story would be silently published anyway. This is a
#   real, precise, required future change to database.py, explicitly NOT made by
#   this prototype (database.py is out of scope for Phase 10/11's prototype task).
CONTRADICTED_UNRESOLVED = "CONTRADICTED_UNRESOLVED"


def verify_symmetric(evidence_claims, synthesis_text, provider=None):
    """11a. -> (findings, status). status is one of claim_extraction's outcome
    codes (SUCCESS_WITH_CLAIMS/SUCCESS_EMPTY/TIMEOUT/RATE_LIMIT/API_ERROR/
    INVALID_RESPONSE/NO_PROVIDER) for the SYNTHESIS extraction call - a model
    failure here means verification itself is unreliable, which the caller must
    route to HOLD (see decide()), never silently treat as "no findings"."""
    synth_claims, status, _stats = extract_claims(synthesis_text, source="SYNTHESIS", provider=provider)
    if is_model_failure(status):
        return [], status, []   # always a 3-tuple - a prior 2-tuple-on-failure bug
                                 # crashed any caller that unpacks 3 values on the
                                 # exact path (a real failure) where that matters most
    findings = []
    for f in detect_conflicts(evidence_claims, synth_claims):
        category = "domain_mismatch" if f["type"] == "domain_conflict" else "contradiction"
        findings.append({**f, "category": category})
    for f in check_entity_ambiguity(evidence_claims, synth_claims):
        findings.append({**f, "category": "entity_mismatch"})
    for a in evidence_claims:
        if a.get("fact_type") is None:
            continue
        for b in synth_claims:
            if b.get("fact_type") != a.get("fact_type"):
                continue
            rel = classify_numeric_pair(a, b)
            if rel == NC_CONTRADICTION:
                findings.append({"type": "numeric_conflict", "category": "numeric_contradiction",
                                  "claim_a": a, "claim_b": b, "certainty": "high",
                                  "reason": f"evidence value {a.get('value') or (a.get('home_value'), a.get('away_value'))} "
                                            f"vs synthesis value {b.get('value') or (b.get('home_value'), b.get('away_value'))}"})
    return findings, status, synth_claims


def check_unhedged_downgrade(evidence_claims, synthesis_claims):
    """11b. -> list of {type: "unhedged_downgrade"|"unsupported_addition",
    evidence_claim, synthesis_claim, category, reason}. See module docstring for
    why the two directions are both here and mean different things."""
    findings = []
    for e in evidence_claims:
        if e.get("status") not in HIGH_RISK_STATUS_VALUES:
            continue
        matches = [s for s in synthesis_claims if _same_claim_key(e, s)]
        if not matches or all(s.get("status") == "UNSPECIFIED" for s in matches):
            findings.append({
                "type": "unhedged_downgrade", "category": "unsupported_status",
                "evidence_claim": e, "synthesis_claim": (matches[0] if matches else None),
                "reason": f"evidence explicitly states {e['status']} for "
                          f"({e.get('subject')}, {e.get('predicate')}) but synthesis "
                          + ("drops the qualification" if matches else "omits this claim entirely"),
            })
    for s in synthesis_claims:
        if s.get("status") not in HIGH_RISK_STATUS_VALUES:
            continue
        matches = [e for e in evidence_claims if _same_claim_key(s, e)]
        if not matches or all(e.get("status") == "UNSPECIFIED" for e in matches):
            findings.append({
                "type": "unsupported_addition", "category": "unsupported_status",
                "evidence_claim": (matches[0] if matches else None), "synthesis_claim": s,
                "reason": f"synthesis asserts {s['status']} for ({s.get('subject')}, {s.get('predicate')}) "
                          f"but no evidence supports this status",
            })
    return findings


# ---- V2_9 extraction-consistency diagnostic (explicitly NOT a fix) -----------------
def diagnose_entity_expansion_omission(claims, source_text):
    """Instrumentation only, per the task's explicit instruction: measure whether
    the model reliably captures an explicit acronym expansion it had available,
    WITHOUT trying to fix or paper over it (that would be a second, undeclared
    extraction path competing with the LLM extractor). For each claim mentioning
    a bare acronym-like token, checks whether the SOURCE TEXT contains an
    explicit "X (ABBR)" or "ABBR (X)" pattern the model could have captured, and
    whether it actually did.
    -> list of {field: "entity_expansion", claim, evidence_contains_expansion,
    extracted_value, omitted: bool} - diagnostic dicts, never a factuality
    finding, never fed into decide()."""
    import re
    diagnostics = []
    expansion_pattern = re.compile(r"([A-Z][A-Za-z .]{2,60})\s*\(([A-Z]{2,6})\)|([A-Z]{2,6})\s*,?\s*short for\s+([A-Z][A-Za-z .]{2,60})", re.I)
    has_expansion_in_text = bool(expansion_pattern.search(source_text or ""))
    for c in claims:
        toks = set(__import__("re").findall(r"\b[A-Z]{2,6}\b", " ".join(str(c.get(k) or "") for k in ("subject", "object"))))
        if not toks:
            continue
        extracted = c.get("entity_expansion")
        diagnostics.append({
            "field": "entity_expansion", "claim_subject": c.get("subject"),
            "evidence_contains_expansion": has_expansion_in_text,
            "extracted_value": extracted,
            "omitted": bool(has_expansion_in_text and not extracted),
        })
    return diagnostics


def decide(symmetric_findings, downgrade_findings, symmetric_status, regenerate_attempt=0):
    """Deterministic decision function - PASS / REGENERATE / HOLD.

    PASS: no substantive findings. A domain_mismatch with certainty=="requires_context"
    ALONE does not block PASS (per Phase 8's original design: a domain signal
    routes to review, it is not itself proof of an error) - only "high"-certainty
    findings (contradiction/entity_mismatch-high/numeric_contradiction/
    unhedged_downgrade/unsupported_addition) are substantive.

    REGENERATE: a substantive, specific, evidence-groundable finding exists AND
    fewer than MAX_REGENERATE_ATTEMPTS have been made.

    HOLD: verification itself failed (symmetric extraction hit a model failure -
    we cannot claim "PASS" when we couldn't actually check), OR a "high"-
    certainty entity_ambiguity exists (the evidence ITSELF states conflicting
    entity identities - not fixable by regenerating the synthesis, needs
    evidence-level resolution), OR regeneration attempts are exhausted and
    substantive findings remain."""
    if is_model_failure(symmetric_status):
        return HOLD, "model_extraction_failure: could not verify the synthesis at all"

    substantive = [f for f in symmetric_findings if f.get("certainty", "high") == "high"] + downgrade_findings
    entity_high = [f for f in symmetric_findings if f.get("category") == "entity_mismatch" and f.get("certainty") == "high"]

    if entity_high:
        return HOLD, f"unresolved entity ambiguity in evidence itself: {[f['reason'] for f in entity_high]}"
    if not substantive:
        return PASS, "no substantive findings"
    if regenerate_attempt < MAX_REGENERATE_ATTEMPTS:
        return REGENERATE, f"{len(substantive)} substantive finding(s), attempt {regenerate_attempt + 1}/{MAX_REGENERATE_ATTEMPTS}"
    return HOLD, f"{len(substantive)} substantive finding(s) remain after {MAX_REGENERATE_ATTEMPTS} regeneration attempts"


def format_regenerate_feedback(substantive_findings):
    """Turns findings into a specific corrective instruction for phase10_synthesis.
    synthesize()'s regenerate_feedback param - never a bare 'try again' (task's
    explicit requirement)."""
    lines = []
    for f in substantive_findings[:5]:
        lines.append(f"- {f.get('category', f.get('type'))}: {f.get('reason')}")
    return "\n".join(lines)
