"""consistency_checks.py - Phase 8/9 PROTOTYPE: deterministic temporal/entity/domain
consistency checks over STRUCTURED claims (claim_extraction.py's output), plus
cross-source contradiction detection. Pure functions, no I/O, no LLM calls here -
the one LLM call already happened in claim_extraction.py; everything below is plain
lookup over its output, which is what makes this deterministic and auditable.

`detect_conflicts()` is deliberately the SAME function used in two places (this is
the point, not an accident):
  - Phase 9: evidence-group claims vs evidence-group claims (pre-synthesis, called
    from a benchmark/prototype harness or the real pipeline before synthesis)
  - Phase 11: evidence claims vs synthesis claims (post-synthesis verification)
One deterministic core, two call sites, no duplicated conflict logic.
"""
import re

# Fixed, small status-contradiction lexicon - the same 9 pairs as v1, renamed to the
# v2 EXPLICIT-only vocabulary (claim_extraction.STATUS_VOCAB). Each pair is
# (status_a, status_b): asserting one when evidence establishes the other, for the
# SAME (subject, predicate), is a conflict. UNSPECIFIED is deliberately in NO pair -
# see the UNSPECIFIED guard in detect_conflicts() below, the direct fix for the v1
# F1 false positive (a claim with no explicit marker must never be treated as if it
# asserted the opposite of another claim's explicit marker).
STATUS_CONFLICT_PAIRS = {
    frozenset({"CURRENT_EXPLICIT", "FORMER_EXPLICIT"}),
    frozenset({"INCOMING_EXPLICIT", "CURRENT_EXPLICIT"}),
    frozenset({"RESIGNED_EXPLICIT", "SERVING_EXPLICIT"}),
    frozenset({"ANNOUNCED_EXPLICIT", "OCCURRED_EXPLICIT"}),
    frozenset({"PROPOSED_EXPLICIT", "CONFIRMED_EXPLICIT"}),
    frozenset({"ALLEGED_EXPLICIT", "ESTABLISHED_EXPLICIT"}),
    frozenset({"CLAIMED_EXPLICIT", "ESTABLISHED_EXPLICIT"}),
    frozenset({"CHARGED_EXPLICIT", "CONVICTED_EXPLICIT"}),
    frozenset({"INJURED_EXPLICIT", "KILLED_EXPLICIT"}),
    # APPOINTED/ELECTED still intentionally excluded (see v1 rationale, unchanged):
    # compatible, not a real antonym pair.
}

# Phase 10/11 (2026-09-28): the "office-holder / allegation / legal-status families"
# the routing/verification tasks scope HIGH_RISK_STATUS and the asymmetric downgrade
# check to - deliberately excludes EVENT_TIMING (ANNOUNCED/OCCURRED/PROPOSED/
# CONFIRMED) and INJURY_DEATH, which those tasks did not name. Single canonical
# definition, imported by phase10_synthesis.py and phase11_verification.py so the
# two phases can never drift apart on what counts as "high-risk".
HIGH_RISK_STATUS_VALUES = {
    "CURRENT_EXPLICIT", "FORMER_EXPLICIT", "INCOMING_EXPLICIT",
    "RESIGNED_EXPLICIT", "SERVING_EXPLICIT",
    "ALLEGED_EXPLICIT", "CLAIMED_EXPLICIT", "ESTABLISHED_EXPLICIT",
    "CHARGED_EXPLICIT", "CONVICTED_EXPLICIT",
}

# Small, fixed domain-keyword lexicon sized to the demonstrated failure mode
# (rugby/cricket) plus the other clearly high-risk sports/field pairs the user
# named - NOT an exhaustive ontology, per the user's own instruction.
DOMAIN_KEYWORDS = {
    # NOTE: "test match"/"test" deliberately excluded from cricket's set - it is
    # genuinely overloaded across sports ("rugby test", "cricket Test match") and
    # a naive substring lexicon collided on it during this audit's own benchmark
    # run (a real rugby story falsely registered as ambiguous rugby+cricket).
    # Cricket's remaining terms below have no such cross-sport collision.
    "cricket": {"wicket", "over", "overs", "innings", "lbw", "boundary", "century",
                "ipl", "batter", "batsman", "bowler", "odi", "t20"},
    "rugby": {"try", "tries", "scrum", "lineout", "conversion", "tackle",
              "rugby union", "rugby league", "rugby test", "springboks", "all blacks", "flyhalf"},
    "football": {"goal", "penalty kick", "offside", "striker", "midfielder",
                 "epl", "la liga", "premier league", "hat-trick"},
    "american_football": {"touchdown", "quarterback", "nfl", "field goal", "down",
                           "end zone", "interception"},
}


def infer_domain(text):
    """Best-effort domain tag from raw text via keyword membership - used only to
    cross-check a claim's own `domain` field against what the SURROUNDING evidence
    text actually says, catching a case where claim extraction mislabeled a claim's
    domain despite correct source text. Returns None if no domain's keywords appear."""
    if not text:
        return None
    low = text.lower()
    hits = {dom: sum(1 for kw in kws if kw in low) for dom, kws in DOMAIN_KEYWORDS.items()}
    hits = {d: n for d, n in hits.items() if n > 0}
    if not hits:
        return None
    return max(hits, key=hits.get)


_LEADING_ARTICLE = re.compile(r"^(the|a|an)\s+")


def _norm_subject(s):
    """Lowercase/strip PLUS a leading English article stripped ("the suspect" ==
    "suspect"). Found 2026-09-28 during Phase 10/11 gate work: P11_4 still failed
    after the predicate-morphology fix because the extractor legitimately produced
    "the suspect" for evidence and "suspect" for the synthesis of the SAME entity -
    ordinary article variation, not a different subject. Narrow and deterministic
    (three fixed words), same principle as the verb-form fix above - does NOT make
    two genuinely different entities equal (stripping an article from "Police"
    changes nothing; it never becomes equal to "suspect")."""
    return _LEADING_ARTICLE.sub("", (s or "").strip().lower())


# ---- Fix 1 (2026-09-28, Phase-13 gate): deterministic predicate-family layer -------
# V2_5 (explicit CHARGED vs explicit CONVICTED, same person, same charge) failed
# because "was charged with" and "was convicted of" are different strings, so exact
# predicate equality never even compared their statuses. A small, fixed keyword->
# family map - NOT an embedding/semantic-similarity model - sized to exactly the
# predicate space that STATUS_CONFLICT_PAIRS cares about (the families a status
# pair could plausibly attach to). A predicate that matches no family falls back to
# exact-string comparison, so this only ever WIDENS matching for the predicates it
# recognizes; it never loosens anything else.
_PREDICATE_FAMILY_KEYWORDS = {
    "OFFICE_HOLDING": ("holds the role of", "is the", "serves as", "was sworn in as", "is chief", "is president", "is prime minister"),
    "LEGAL_PROCEEDING": ("charged with", "charges of", "faces charges", "accused of", "allege", "alleged",
                          "convicted of", "found guilty of", "pleaded guilty", "sentenced for"),
    "INJURY_DEATH": ("was killed", "were killed", "died", "was injured", "were injured", "was hurt", "was wounded"),
    "APPOINTMENT_RESIGNATION": ("was appointed", "was resigned", "resigned as", "stepped down", "was elected", "sworn in"),
    "EVENT_TIMING": ("was announced", "announced", "occurred", "took place", "was proposed", "proposed", "was confirmed", "confirmed"),
}


# ---- Predicate-morphology fix (2026-09-28, Phase 10/11 gate) ----------------------
# P11_4/P11_6 failed because the extractor legitimately produced "stole" for evidence
# and "stealing" for the synthesis of the SAME fact - ordinary grammatical variation,
# not paraphrase. This is a SEPARATE, narrower mechanism from _PREDICATE_FAMILY_KEYWORDS
# above: a fixed table of surface forms for exactly 8 named verb lemmas (steal, accuse,
# charge, convict, serve, elect, appoint, resign), matched by WHOLE WORD (regex word
# tokens, set-intersection) so "elect" cannot accidentally match inside "electric" or
# similar - not a stemmer, not fuzzy matching, just an explicit enumerated form list.
# Purely additive: it only ever WIDENS which predicates resolve to a family; nothing
# that previously resolved via the phrase-keyword path above is affected.
_VERB_FORM_FAMILIES = {
    "LEGAL_PROCEEDING": (
        {"steal", "steals", "stole", "stolen", "stealing"},
        {"accuse", "accuses", "accused", "accusing"},
        {"charge", "charges", "charged", "charging"},
        {"convict", "convicts", "convicted", "convicting"},
    ),
    "APPOINTMENT_RESIGNATION": (
        {"serve", "serves", "served", "serving"},
        {"elect", "elects", "elected", "electing"},
        {"appoint", "appoints", "appointed", "appointing"},
        {"resign", "resigns", "resigned", "resigning"},
    ),
    # ATTRIBUTION_VERB (2026-09-28, offline claim-clustering task): the shadow
    # trial's dominant redundancy pattern was "scientists SAY X" / "a report
    # STATES X" / "a survey INDICATES X" / "the group CLAIMS X" - the same
    # underlying attributed proposition, worded with different but functionally
    # interchangeable attribution verbs. Neither "say" nor "claim" (nor their
    # relatives) were in any existing family, so two claims differing only by
    # this verb choice never matched. Same fixed-word-list mechanism as every
    # other family above - explicitly enumerated forms, no stemmer, no fuzzy
    # matching. Deliberately excludes verbs already carrying their OWN status
    # meaning (allege/accuse/charge stay in LEGAL_PROCEEDING, not merged here)
    # so this family only covers genuinely neutral, interchangeable attribution.
    "ATTRIBUTION_VERB": (
        {"say", "says", "said", "saying"},
        {"state", "states", "stated", "stating"},
        {"report", "reports", "reported", "reporting"},
        {"indicate", "indicates", "indicated", "indicating"},
        {"note", "notes", "noted", "noting"},
        {"add", "adds", "added", "adding"},
        {"assert", "asserts", "asserted", "asserting"},
        {"claim", "claims", "claimed", "claiming"},
    ),
}


def _predicate_family(predicate):
    p = (predicate or "").strip().lower()
    for family, keywords in _PREDICATE_FAMILY_KEYWORDS.items():
        if any(kw in p for kw in keywords):
            return family
    words = set(re.findall(r"[a-z]+", p))
    for family, form_groups in _VERB_FORM_FAMILIES.items():
        for forms in form_groups:
            if words & forms:
                return family
    return None


def _norm_object(s):
    """Lowercased, stripped, trailing punctuation removed - deterministic, not
    fuzzy. Used only for the substring-containment check below."""
    return re.sub(r"[.,;:!?]+$", "", (s or "").strip().lower())


def _objects_compatible(a, b):
    """True if the two (already-normalized) object strings are compatible enough
    to be considered "about the same thing" for family-matched claims: exact
    match, one is empty/missing (nothing to disagree about), or one is a
    substring of the other (e.g. "theft" vs "theft from the charity's accounts").
    Deliberately conservative - this is what keeps "charged with theft" from
    being linked to "charged with fraud" just because both are LEGAL_PROCEEDING."""
    oa, ob = _norm_object(a), _norm_object(b)
    if not oa or not ob:
        return True
    return oa == ob or oa in ob or ob in oa


def _same_claim_key(a, b):
    """Two claims are "the same claim" (comparable for conflict purposes) if:
      - subjects match exactly (normalized) - subject equality is NEVER relaxed,
        that is the dangerous direction (linking different real people/entities);
      - AND EITHER predicates match exactly (original, unchanged behavior) OR
        both predicates resolve to the SAME non-null family AND their objects are
        compatible (Fix 1 - the new, additive path)."""
    if _norm_subject(a.get("subject")) != _norm_subject(b.get("subject")):
        return False
    pa, pb = (a.get("predicate") or "").strip().lower(), (b.get("predicate") or "").strip().lower()
    if pa == pb:
        return True
    fam_a, fam_b = _predicate_family(pa), _predicate_family(pb)
    return fam_a is not None and fam_a == fam_b and _objects_compatible(a.get("object"), b.get("object"))


def detect_conflicts(claims_a, claims_b):
    """claims_a, claims_b: lists of claim dicts (claim_extraction.py's schema).
    -> list of conflict dicts: {type, claim_a, claim_b, reason, certainty}. Pure
    lookup, no LLM call - the semantic normalization already happened when the
    claims were extracted. type is one of: status_conflict | domain_conflict.

    certainty distinguishes two different strengths of signal (2026-09-28
    hardening, section 6): status_conflict findings are "high" - they come from a
    fixed, deliberately narrow antonym lexicon (STATUS_CONFLICT_PAIRS), so a hit
    means the SAME (subject, predicate) was given two genuinely incompatible
    status words. domain_conflict findings are "requires_context" - a keyword-
    lexicon domain mismatch is a real signal worth surfacing (this is what caught
    the rugby/cricket case) but is not by itself proof of an error: a story can
    legitimately span two domains (a cricketer who also plays rugby, a mixed
    sports roundup), so this must route to human/strong-model review rather than
    an automatic hard block. Callers that need a binary pass/fail should filter
    on certainty=="high" for auto-action and treat "requires_context" hits as a
    review queue, not a rejection."""
    conflicts = []
    for a in claims_a:
        for b in claims_b:
            if not _same_claim_key(a, b):
                continue
            sa, sb = a.get("status"), b.get("status")
            # UNSPECIFIED guard (v2 hardening, direct fix for the F1 false positive):
            # a claim with no explicit marker carries no assertion about status at
            # all, so it can NEVER conflict with another claim's explicit status -
            # "silence" is not the opposite of "current", it is simply unknown.
            if sa and sb and sa != "UNSPECIFIED" and sb != "UNSPECIFIED" and sa != sb \
                    and frozenset({sa, sb}) in STATUS_CONFLICT_PAIRS:
                conflicts.append({"type": "status_conflict", "claim_a": a, "claim_b": b, "certainty": "high",
                                   "reason": f"{sa} vs {sb} for the same ({a.get('subject')}, {a.get('predicate')})"})
            da, db = a.get("domain"), b.get("domain")
            if da and db and da != db:
                conflicts.append({"type": "domain_conflict", "claim_a": a, "claim_b": b, "certainty": "requires_context",
                                   "reason": f"domain '{da}' vs '{db}' for the same claim - signal, not automatic contradiction"})
    return conflicts


# ---- entity ambiguity (v2 hardening, section 7) ------------------------------------
# Deliberately conservative: this NEVER uses background knowledge to decide whether
# two claims sharing an acronym/short name are the same real-world entity or not.
# It only uses what each claim's OWN evidence_expansion says. Three outcomes:
#   - both sides have a stated expansion and they MATCH -> same entity, no finding
#   - both sides have a stated expansion and they DIFFER -> genuine, high-certainty
#     entity_conflict (the evidence itself establishes these are different things)
#   - either side is missing an expansion -> UNRESOLVED: the claims share a short
#     name but nothing in evidence links or separates them - per the success
#     criterion, this must be reported as unresolved, never silently merged or
#     silently ignored.
_ACRONYM_RE = None


def _short_name_tokens(claim):
    """Bare acronym-like tokens (all-caps, 2-6 letters) appearing in a claim's
    subject/object/evidence_quote - used only to notice that two claims MENTION
    the same short string, never to assert they mean the same thing."""
    import re as _re
    text = " ".join(str(claim.get(k) or "") for k in ("subject", "object", "evidence_quote"))
    return set(_re.findall(r"\b[A-Z]{2,6}\b", text))


def _norm_expansion(s):
    """entity_expansion normalization for comparison: strip a trailing parenthetical
    (e.g. "(CJP)") plus the usual case/whitespace normalization. Deterministic
    string cleanup, not fuzzy matching."""
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s or "").strip()
    return _norm_subject(s)


def check_entity_ambiguity(claims_a, claims_b):
    """-> list of {type: "entity_ambiguity", claim_a, claim_b, certainty, reason,
    occurrence_count}. AT MOST ONE finding per distinct acronym, never one per
    claim-pair.

    Bug found 2026-09-28 during the 100-story shadow trial: the original version
    of this function created a separate finding for EVERY (claim_a, claim_b) pair
    that happened to share an acronym token. A real story mentioning "US" (or
    "FIFA", "BRICS", "OTT"...) across many claims - completely normal for a
    multi-source story - produced 50-100+ duplicate findings for the exact same
    non-issue, swamping every genuine signal and making nearly every multi-source
    real story HOLD. None of the hand-crafted benchmark cases (always 1-2 claims
    per side) could have surfaced this - it only appears at real scale, which is
    exactly what a shadow trial exists to catch.

    Fix: build a document-wide acronym -> {stated expansions} map ACROSS BOTH
    claim lists first. An acronym with exactly one distinct stated expansion
    anywhere in the document is RESOLVED (no finding at all, regardless of how
    many claims mention it - if "US" is expanded once, every other bare mention
    is understood). An acronym with zero expansions anywhere produces exactly
    ONE "unresolved" finding (not one per occurrence). An acronym with 2+
    DIFFERING expansions produces exactly ONE "high"-certainty finding (this is
    the genuine CJP-collision case this function was built to catch - still
    caught, just not duplicated per pair)."""
    all_claims = claims_a + claims_b
    expansions_by_token = {}
    occurrences_by_token = {}
    unexpanded_count_by_token = {}
    representative_by_token = {}
    for c in all_claims:
        for tok in _short_name_tokens(c):
            occurrences_by_token[tok] = occurrences_by_token.get(tok, 0) + 1
            representative_by_token.setdefault(tok, c)
            exp = c.get("entity_expansion")
            if exp:
                expansions_by_token.setdefault(tok, {})[_norm_expansion(exp)] = exp
            else:
                unexpanded_count_by_token[tok] = unexpanded_count_by_token.get(tok, 0) + 1

    tokens_a = set().union(*(_short_name_tokens(c) for c in claims_a)) if claims_a else set()
    tokens_b = set().union(*(_short_name_tokens(c) for c in claims_b)) if claims_b else set()
    shared_tokens = tokens_a & tokens_b

    findings = []
    for tok in sorted(shared_tokens):
        exps = expansions_by_token.get(tok, {})
        if len(exps) >= 2:
            findings.append({"type": "entity_ambiguity", "claim_a": representative_by_token[tok], "claim_b": None,
                              "certainty": "high", "occurrence_count": occurrences_by_token[tok],
                              "reason": f"short name '{tok}' has {occurrences_by_token[tok]} mention(s) across "
                                        f"the evidence but DIFFERENT stated expansions: {sorted(exps.values())}"})
        elif len(exps) == 1 and unexpanded_count_by_token.get(tok, 0) == 0:
            # EVERY mention of this token carries the (same) stated expansion -
            # fully resolved, no finding. Strict on purpose: a single stated
            # expansion does NOT resolve OTHER, unexpanded mentions of the same
            # acronym (that is the exact asymmetric CJP case this function
            # exists to catch - one source's expansion never silently vouches
            # for a different, unexpanded mention elsewhere).
            continue
        else:
            # 0 expansions anywhere, OR a stated expansion exists but at least
            # one mention still lacks it (or disagrees) - unresolved, deduped
            # to ONE finding regardless of how many claims mention this token.
            findings.append({"type": "entity_ambiguity", "claim_a": representative_by_token[tok], "claim_b": None,
                              "certainty": "unresolved", "occurrence_count": occurrences_by_token[tok],
                              "reason": f"short name '{tok}' has {occurrences_by_token[tok]} mention(s) across "
                                        f"the evidence; not every mention has a stated expansion - cannot link "
                                        f"or separate without guessing"})
    return findings


def check_claim_against_text(claim, text):
    """Cross-check a single claim's `domain` field against the raw text it should
    have come from (defense against a claim-extraction mislabel, independent of
    detect_conflicts' evidence-vs-evidence/synthesis check). -> conflict dict or
    None."""
    if not claim.get("domain"):
        return None
    inferred = infer_domain(text)
    if inferred and inferred != claim["domain"]:
        return {"type": "domain_conflict", "claim_a": claim, "claim_b": {"domain": inferred}, "certainty": "requires_context",
                "reason": f"claim tagged domain='{claim['domain']}' but source text reads as '{inferred}'"}
    return None


def check_all_against_text(claims, text):
    return [c for c in (check_claim_against_text(cl, text) for cl in claims) if c]
