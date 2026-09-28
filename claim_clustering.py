"""claim_clustering.py - PROTOTYPE, offline-only (2026-09-28). Deterministic claim
clustering: groups evidence claims that represent the SAME underlying proposition
(reported redundantly by multiple sources in different words) into one cluster,
so downstream checks (check_unhedged_downgrade, numeric_consistency) compare
against ONE representative proposition per cluster instead of once per source -
the fix for the "81 omitted-claim findings, mostly redundant sources saying the
same thing differently" problem the 100-story shadow trial exposed.

NOT wired into production. NOT wired into phase11_verification.py yet (Step 9:
isolated prototype only, pending a future live validation run this task
explicitly does not attempt).

SAFETY CONTRACT (the whole point of this file): similar wording is NEVER
sufficient to cluster. Two claims cluster ONLY when they pass ALL of:
  1. same normalized subject (consistency_checks._norm_subject - strips a
     leading article, nothing more; genuinely different subjects, e.g.
     "Police" vs "the suspect", NEVER match)
  2. same predicate family OR identical predicate string (consistency_checks
     ._predicate_family + _VERB_FORM_FAMILIES - the SAME fixed, narrow lexicon
     already validated across 3 prior hardening rounds; nothing new invented
     here)
  3. compatible object (consistency_checks._objects_compatible - exact match or
     substring containment; "theft" vs "fraud" never match)
  4. compatible status: identical explicit status, OR both UNSPECIFIED, OR one
     UNSPECIFIED (silence is compatible with anything, same principle as the
     original F1 fix - it asserts nothing to disagree with). Two DIFFERENT
     explicit statuses in the same STATUS_CONFLICT_PAIRS family (e.g.
     CURRENT_EXPLICIT vs FORMER_EXPLICIT) NEVER cluster - that is a genuine
     disagreement, not the same proposition.
  5. compatible time: if both sides carry an explicit, distinct date-bearing
     time reference that clearly differs (via numeric_consistency's own
     _times_differ), they do NOT cluster - a claim from Monday and a claim from
     Wednesday are a temporal sequence (a possible update), never silently
     merged into "the same claim".
  6. compatible numeric dimension: if both carry a fact_type+value, the
     fact_type must match (a $ amount and a death count never cluster just
     because both are numbers) - the actual VALUES are allowed to differ
     (that is exactly what a cluster is FOR: capturing that N sources report
     slightly different figures for the SAME underlying dimension, so the
     disagreement gets surfaced ONCE per cluster, not swallowed and not
     duplicated N times either).
  7. compatible domain: if both carry a domain tag, it must match (this is
     already a "signal not certainty" dimension per Phase 8's design, so a
     domain mismatch blocks clustering conservatively rather than merging
     across sports).
  8. compatible material attribution: if the claim IS itself an attribution
     claim (predicate in phase11_verification._ATTRIBUTION_PREDICATES) and
     the attributed subject differs AND is not a routine institutional source
     (phase11_verification._is_routine_attributor), the claims do NOT cluster
     - WHO specifically makes a claim is preserved, never silently merged
     into a single generic attributor.

None of this uses fuzzy/embedding/LLM similarity. Implementation uses a
union-find keyed by normalized subject FIRST (cheap bucketing) so the O(n^2)
pairwise compatibility check only ever runs WITHIN same-subject buckets, never
across the whole claim set - see the stress-test results in this session's
report for the measured effect.
"""
from consistency_checks import (
    _norm_subject, _predicate_family, _objects_compatible, _norm_object,
    STATUS_CONFLICT_PAIRS, _VERB_FORM_FAMILIES,
)
from numeric_consistency import _times_differ

try:
    from phase11_verification import _ATTRIBUTION_PREDICATES, _is_routine_attributor
except ImportError:  # pragma: no cover - keeps this module importable standalone
    _ATTRIBUTION_PREDICATES = {"allege", "alleges", "alleged", "accuse", "accused", "accuses",
                                "claim", "claims", "claimed", "report", "reports", "reported"}

    def _is_routine_attributor(subject):
        return False


import re


def _predicate_key(predicate):
    """predicate_family if recognized, else the normalized literal string (so
    two claims with an unrecognized but IDENTICAL predicate can still cluster -
    only DIFFERENT unrecognized predicates stay apart, matching
    consistency_checks._same_claim_key's own fallback behavior exactly)."""
    fam = _predicate_family(predicate)
    return fam if fam else (predicate or "").strip().lower()


def _status_compatible(sa, sb):
    if sa in (None, "UNSPECIFIED") or sb in (None, "UNSPECIFIED"):
        return True
    if sa == sb:
        return True
    return frozenset({sa, sb}) not in STATUS_CONFLICT_PAIRS  # differing but NOT a known
    # antonym pair (e.g. ANNOUNCED_EXPLICIT vs a status from an unrelated family) is not
    # a proven disagreement either - conservative default is to allow clustering only
    # when they are not KNOWN opposites; anything actually unclear falls through to the
    # union-find's cluster-level disagreement reporting rather than blocking the merge
    # outright, since blocking here would just fragment genuinely-redundant claims for
    # no evidenced reason.


def _time_compatible(a, b):
    diff = _times_differ(a, b)
    return diff is not True  # True = explicitly, genuinely different times -> incompatible


def _domain_compatible(a, b):
    da, db = a.get("domain"), b.get("domain")
    if da and db:
        return da == db
    return True


# Local extension over phase11_verification._ATTRIBUTION_PREDICATES (allege/
# accuse/claim/report only), added here rather than editing that already-
# validated constant: the task's own routine-attribution examples ("police
# CONFIRMED the death toll", "election officials DECLARED X the winner") use
# verbs that set never covered, and neither did "say"/"state"/etc. (needed for
# the generic-epistemic-source extension below). Folds in the SAME
# ATTRIBUTION_VERB word-form family already added to consistency_checks.py
# (single source of truth for that lexicon, not duplicated) plus confirm/
# declare. Scoped to claim_clustering.py's own subject-key exception only -
# does not change check_attribution_loss's behavior at all.
_CLUSTERING_ATTRIBUTION_PREDICATES = (
    _ATTRIBUTION_PREDICATES
    | {"confirm", "confirms", "confirmed", "declare", "declares", "declared"}
    | set().union(*_VERB_FORM_FAMILIES.get("ATTRIBUTION_VERB", ()))
)


def _is_attribution_claim(c):
    pred = (c.get("predicate") or "").strip().lower()
    words = set(re.findall(r"[a-z]+", pred))
    return bool(words & _CLUSTERING_ATTRIBUTION_PREDICATES)


def _attribution_compatible(a, b, generic_epistemic_sources=False):
    """Stage 8. MUST use the exact same subject-equivalence classes as stage 1
    (_clustering_subject_key) - an earlier version of this function used raw
    _norm_subject() independently, which meant it didn't know about the
    generic-epistemic exception stage 1 could grant, so it re-blocked pairs
    stage 1 had already correctly allowed (caught by this file's own
    adversarial test P before being trusted). Kept as its own named stage,
    per the task's 8-stage design, rather than collapsed into stage 1, but now
    genuinely consistent with it instead of duplicating its logic with a
    stale copy."""
    if not (_is_attribution_claim(a) and _is_attribution_claim(b)):
        return True
    return _clustering_subject_key(a, generic_epistemic_sources) == _clustering_subject_key(b, generic_epistemic_sources)


def _clustering_subject_key(c, generic_epistemic_sources=False):
    """Normalized subject for clustering purposes - identical to _norm_subject()
    EXCEPT for narrow, explicit exceptions:
      - an attribution-verb claim whose subject is a routine institutional
        attributor (police, officials, courts, ...) is mapped to a single
        canonical bucket - VALIDATED, part of the default behavior.
      - (OPT-IN ONLY, generic_epistemic_sources=True) an attribution-verb
        claim whose subject is a generic epistemic-source noun (scientists,
        a report, a survey, ...) - see the PROPOSED extension note above
        cluster_evidence_claims. NOT part of default behavior.
    Every non-attribution claim, and every attribution claim with a non-
    routine/non-generic subject, is completely unaffected by either."""
    if _is_attribution_claim(c) and _is_routine_attributor(c.get("subject")):
        return "\0ROUTINE_ATTRIBUTOR\0"
    generic_key = _generic_epistemic_key(c, generic_epistemic_sources)
    if generic_key:
        return generic_key
    return _norm_subject(c.get("subject"))


def claims_compatible(a, b, generic_epistemic_sources=False):
    """The 8-stage compatibility gate. All 8 must pass. Returns (bool, failed_stage_or_None).
    generic_epistemic_sources: opt-in, see the PROPOSED extension note above
    cluster_evidence_claims - False (the default) reproduces the exact,
    fully-adversarially-validated behavior; True is unvalidated against live
    data and offered only for the offline replay's incremental-effect
    measurement."""
    if _clustering_subject_key(a, generic_epistemic_sources) != _clustering_subject_key(b, generic_epistemic_sources):
        return False, "subject"
    if _predicate_key(a.get("predicate")) != _predicate_key(b.get("predicate")):
        return False, "predicate_family"
    if not _objects_compatible(a.get("object"), b.get("object")):
        return False, "object"
    if not _status_compatible(a.get("status"), b.get("status")):
        return False, "status"
    if not _time_compatible(a, b):
        return False, "time"
    fa, fb = a.get("fact_type"), b.get("fact_type")
    if fa and fb and fa != fb:
        return False, "numeric_dimension"
    if not _domain_compatible(a, b):
        return False, "domain"
    if not _attribution_compatible(a, b, generic_epistemic_sources):
        return False, "attribution"
    return True, None


class _UnionFind:
    def __init__(self, n):
        self.parent = list(range(n))

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x, y):
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self.parent[ry] = rx


# ---- PROPOSED, opt-in extension (NOT the default, NOT independently validated
# against live data) -----------------------------------------------------------
# Offline replay of the real 40-story shadow-trial data found the DOMINANT
# redundancy pattern is NOT "same subject, different predicate wording" (which
# the core 8-stage gate already handles) but "different GENERIC epistemic-
# source noun for the same underlying attributed claim" - "scientists say X" /
# "a report states X" / "a survey indicates X" / "the group claims X" /
# "researchers found X". These are different literal subjects that the core
# gate correctly and conservatively keeps separate (exactly as designed - "US"
# vs "IDF" must never merge just because both attribute something).
#
# This is a genuinely different, narrower category than a named institutional
# authority (police/court/officials) or a specific named/interested party
# (a rival's lawyer, the opposition) - it is a small, closed set of GENERIC,
# non-specific epistemic-source nouns that carry essentially no identifiable
# reference of their own (unlike "Police" or "the opposition party", "a
# report"/"scientists"/"a survey" name no one in particular). Proposed as an
# OPT-IN extension (cluster_evidence_claims(claims, generic_epistemic_sources=
# True)) precisely because treating it as safe-by-default has NOT been
# validated against live extraction - it is offered here, adversarially
# tested against synthetic cases only, for a FUTURE small paid validation run
# to confirm or reject, not adopted as the default behavior.
_GENERIC_EPISTEMIC_SOURCES = {"scientists", "researchers", "experts", "analysts",
                               "report", "study", "survey", "group"}
# NOTE: bare of articles deliberately - _norm_subject() already strips a
# leading "the"/"a"/"an" before this set is ever checked, so "a report" and
# "the report" both normalize to "report" first. Listing the article-inclusive
# forms here (as an earlier version of this file did) would never match and
# silently disable this extension entirely - caught by test P below.


def _generic_epistemic_key(c, enabled):
    if enabled and _is_attribution_claim(c) and _norm_subject(c.get("subject")) in _GENERIC_EPISTEMIC_SOURCES:
        return "\0GENERIC_EPISTEMIC_SOURCE\0"
    return None


def cluster_evidence_claims(claims, generic_epistemic_sources=False):
    """claims: list of claim dicts (may include an optional 'claim_id' /
    'group_id' / 'provenance' - preserved on output, never required).
    -> list of cluster dicts: {members: [claim indices into `claims`],
    member_claims: [...], representative: claim, source_count: int,
    disagreement: [...] (numeric or status divergence found within the
    cluster, if any), reason}.

    Bucketed by normalized subject FIRST (O(n) dict build) so the O(k^2)
    pairwise compatibility check only ever runs within same-subject buckets of
    size k, never across the full claim set - see this session's stress-test
    numbers for the measured effect versus the naive O(n^2) approach."""
    n = len(claims)
    if n == 0:
        return []
    uf = _UnionFind(n)
    buckets = {}
    for i, c in enumerate(claims):
        buckets.setdefault(_clustering_subject_key(c, generic_epistemic_sources), []).append(i)

    comparisons = 0
    for idxs in buckets.values():
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                comparisons += 1
                i, j = idxs[a], idxs[b]
                ok, _ = claims_compatible(claims[i], claims[j], generic_epistemic_sources)
                if ok:
                    uf.union(i, j)

    groups = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)

    clusters = []
    for member_idxs in groups.values():
        member_claims = [claims[i] for i in member_idxs]
        # representative: prefer the one with an explicit status, else the first
        rep = next((c for c in member_claims if c.get("status") not in (None, "UNSPECIFIED")), member_claims[0])
        sources = {c.get("provenance", {}).get("source") or c.get("source") for c in member_claims}
        sources.discard(None)
        disagreement = []
        statuses = {c.get("status") for c in member_claims if c.get("status") not in (None, "UNSPECIFIED")}
        if len(statuses) > 1:
            disagreement.append({"type": "status_variation", "values": sorted(statuses)})
        values = [(c.get("value"), c.get("unit")) for c in member_claims if c.get("value") is not None]
        distinct_values = {v for v, _ in values}
        if len(distinct_values) > 1:
            disagreement.append({"type": "numeric_variation", "values": sorted(distinct_values)})
        clusters.append({
            "members": member_idxs,
            "member_claims": member_claims,
            "representative": rep,
            "source_count": len(sources) or len(member_claims),
            "claim_count": len(member_claims),
            "disagreement": disagreement,
            "reason": f"{len(member_claims)} claim(s) from {len(sources) or len(member_claims)} source(s), "
                      f"same subject/predicate-family/object/status-compatible/time-compatible",
        })
    clusters.sort(key=lambda c: -c["claim_count"])
    return clusters, comparisons
