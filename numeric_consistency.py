"""numeric_consistency.py - PROTOTYPE v2 (2026-09-28 hardening round 2): numeric-value
consistency as a SEPARATE dimension from subject/predicate string equality. Pure
functions, no I/O, no LLM calls - plain deterministic lookup over
claim_extraction.py's v2 schema (fact_type/value/qualifier/home_value/away_value/
time_type/time_text).

Two real production values anchor the rounding tolerance: the real Sensex benchmark
case (1,677 points reported by most outlets, 1,700 by Times of India as a plain
rounding of the same real-world figure) must classify as ROUNDING, not CONTRADICTION.

v2 changes from the first hardening pass (both were real bugs found in that run):
  - time comparison now uses the structured time_type/time_text fields instead of a
    single free-text `time` string - "Monday" and "as of Monday" (RELATIVE_DATE vs
    TIME_DESCRIPTOR referring to the same day) no longer compare as different times
    just because their raw strings differ.
  - SCORE/match_result claims now compare home_value/away_value as a pair instead of
    a single collapsed `value`, so "3-1" vs "3-2" is a detectable contradiction
    instead of being silently reduced to "3 vs 3".
"""

CONTRADICTION = "CONTRADICTION"
ROUNDING = "ROUNDING"
APPROXIMATION = "APPROXIMATION"
DIFFERENT_SCOPE = "DIFFERENT_SCOPE"
DIFFERENT_TIME = "DIFFERENT_TIME"
LATER_UPDATE = "LATER_UPDATE"
COMPATIBLE = "COMPATIBLE"
UNRESOLVED = "UNRESOLVED"

ROUNDING_RELATIVE_TOLERANCE = 0.03
ROUNDING_LOOSE_TOLERANCE = 0.10

# Fix 4 (2026-09-28, Phase-13 gate) - PROPOSED, not yet validated beyond the dataset
# cited below; needs more real examples before being trusted as final.
#
# Calibration dataset actually used (real production events, read-only DB query,
# 400 randomly sampled multi-article events; not fabricated):
#   - Sensex fall (event 7148, already used as the original anchor): 1,677 vs 1,700
#     points -> 1.35% relative diff, 1,700 is a round number -> ROUNDING (unchanged,
#     already correct under the general relative-tolerance path below).
#   - Maharashtra drought (event 24339): "74% of the state" vs "75% of state" -> a
#     REAL percentage pair, 1 point / 1.33% relative diff, unambiguously the same
#     underlying figure reported by different outlets.
#   - Cyprus ferry capsize (event 16747), a real multi-outlet DEVELOPING disaster:
#     passenger count reported as 260 / 267 / 270 across different outlets (up to
#     3.7% relative diff) - correctly resolves as ROUNDING already, no change
#     needed. Death toll reported as 7 / 8 (12.5% relative diff, NOT close) -
#     correctly falls through to CONTRADICTION under the existing general-number
#     path: a >10% swing in a death toll is a real signal worth surfacing, not
#     something to suppress, even in a live/developing story. This pair is kept
#     as a deliberate NEGATIVE calibration check: the fix below must NOT touch
#     non-percentage fact_types, and 7-vs-8 confirms it doesn't.
#   - Karnataka land-plot rule (event 10443), "68 seconds" (event 15716), "34
#     minutes" (event 3644): identical values repeated verbatim across outlets -
#     trivial exact-match confirmations, included for completeness.
#
# Reasoning for singling out "percentage" specifically: the one real percentage
# pair found (74 vs 75) is small and already passes under the general 3%/10%
# logic - it does NOT by itself justify a special rule. What does: percentage
# figures in news reporting are very commonly independent survey/estimate
# outputs (polls, drought-coverage surveys, approval ratings) where a few points
# of difference is expected measurement/sampling variance, not a factual dispute
# about a single true number - unlike a death toll or a monetary amount, which
# describe one real, in-principle-exact quantity. This is INFERRED domain
# reasoning about how percentages get reported, not something the single real
# data point alone proves; it is deliberately conservative (a flat point
# threshold, not a large relative one) so it does not swallow genuinely large
# swings the way a purely relative tolerance would at the low end of the 0-100
# range. PERCENTAGE_POINT_TOLERANCE=5 is picked to comfortably cover both real
# cases on hand (74-75 and, from the earlier prototype run, a synthetic 52-54)
# without being wide enough to wave through something like 45% vs 60%.
PERCENTAGE_POINT_TOLERANCE = 5.0
# starts at 10, not 1 - see the v1 hardening note: a magnitude-1/step-1 tier makes
# n % 1 == 0 true for every integer, misclassifying an exact small contradiction
# (e.g. a match score of 3 vs 2) as "rounding".
ROUNDING_ROUND_NUMBER_STEP = {10: 5, 100: 50, 1000: 100, 10000: 500}

# Date-bearing time types that can participate in a time-difference comparison.
# SOURCE_DESCRIPTOR ("the latest poll") and UNSPECIFIED never do - they are not
# dates at all, fixing the v1 bug where "latest poll" was treated as a timestamp.
_DATE_BEARING = {"EXPLICIT_DATE", "RELATIVE_DATE", "TIME_DESCRIPTOR"}
_DESCRIPTOR_PREFIXES = ("as of ", "by ", "on ", "since ", "from ", "as at ")


def _is_round_number(n):
    if n == 0 or n != int(n):
        return False
    n = abs(int(n))
    for magnitude, step in sorted(ROUNDING_ROUND_NUMBER_STEP.items(), reverse=True):
        if n >= magnitude and n % step == 0:
            return True
    return False


def _relative_diff(a, b):
    hi = max(abs(a), abs(b))
    return abs(a - b) / hi if hi else 0.0


def _numeric_relationship(a, b):
    rel = _relative_diff(a, b)
    round_involved = _is_round_number(a) or _is_round_number(b)
    if round_involved and rel <= ROUNDING_LOOSE_TOLERANCE:
        return ROUNDING
    if rel <= ROUNDING_RELATIVE_TOLERANCE:
        return APPROXIMATION
    return None


def _normalize_time_text(time_type, text):
    """Strip a TIME_DESCRIPTOR's qualifier prefix so 'as of Monday' normalizes to
    the same reference as a RELATIVE_DATE 'Monday'. Returns lowercase, stripped
    text, or None if there's nothing date-bearing to compare."""
    if time_type not in _DATE_BEARING or not text:
        return None
    t = text.strip().lower()
    if time_type == "TIME_DESCRIPTOR":
        for prefix in _DESCRIPTOR_PREFIXES:
            if t.startswith(prefix):
                t = t[len(prefix):].strip()
                break
    return t or None


def _times_differ(claim_a, claim_b):
    """-> True (differ), False (same reference), or None (not comparable - at
    least one side isn't date-bearing, so no time-based classification applies)."""
    ta = _normalize_time_text(claim_a.get("time_type"), claim_a.get("time_text"))
    tb = _normalize_time_text(claim_b.get("time_type"), claim_b.get("time_text"))
    if ta is None or tb is None:
        return None
    return ta != tb


_SCOPE_QUALIFIERS = {"confirmed", "missing", "feared", "estimated", "at least",
                      "up to", "so far", "presumed", "reported", "unaccounted",
                      "approximately", "more than"}


def _qualifier_of(claim):
    q = (claim.get("qualifier") or "").strip().lower()
    return q if q in _SCOPE_QUALIFIERS else None


def _classify_score_pair(claim_a, claim_b):
    """SCORE/match_result claims use home_value/away_value instead of value -
    compares both components; a mismatch in EITHER is a contradiction (small
    integers, so the round-number/rounding heuristic never applies - a sports
    score is always an exact count, never a rounded estimate)."""
    ha, aa = claim_a.get("home_value"), claim_a.get("away_value")
    hb, ab = claim_b.get("home_value"), claim_b.get("away_value")
    if ha is None or aa is None or hb is None or ab is None:
        return UNRESOLVED
    if ha == hb and aa == ab:
        return COMPATIBLE
    return CONTRADICTION


def classify_numeric_pair(claim_a, claim_b):
    """claim_a, claim_b: v2 claim dicts. -> one of the module-level constants.
    No model call, no background knowledge - insufficient explicit context means
    UNRESOLVED, not a guess (section 4)."""
    if claim_a.get("fact_type") != claim_b.get("fact_type"):
        return COMPATIBLE   # different quantities entirely - both can be true

    if claim_a.get("fact_type") in ("score", "match_result") or \
            claim_a.get("home_value") is not None or claim_b.get("home_value") is not None:
        return _classify_score_pair(claim_a, claim_b)

    if claim_a.get("value") is None or claim_b.get("value") is None:
        return UNRESOLVED
    a, b = claim_a["value"], claim_b["value"]
    if a == b:
        return COMPATIBLE

    # Fix 2 (2026-09-28, Phase-13 gate): TIME is checked BEFORE qualifier/scope.
    # N3 regressed because claim_a's qualifier="confirmed" (legitimate, ordinary
    # reporting language - "officials confirmed 4 dead") got read as a SCOPE hedge
    # before the genuinely explicit time difference (Monday -> Wednesday) was ever
    # considered, misclassifying a real update as a scope mismatch. "confirmed" is
    # overloaded: it can mean "as opposed to unconfirmed/estimated" (a real scope
    # distinction, e.g. N2's "at least 12" vs "confirmed 8") OR it can be ordinary
    # attribution language that says nothing about scope at all. When two explicit,
    # DIFFERENT time references are present, that is the stronger, less ambiguous
    # signal and must be evaluated first.
    diff_time = _times_differ(claim_a, claim_b)
    if diff_time is True:
        return LATER_UPDATE if _relative_diff(a, b) > ROUNDING_RELATIVE_TOLERANCE else DIFFERENT_TIME
    if diff_time is None and (claim_a.get("time_type") not in (None, "UNSPECIFIED", "SOURCE_DESCRIPTOR") or
                               claim_b.get("time_type") not in (None, "UNSPECIFIED", "SOURCE_DESCRIPTOR")):
        # one side is date-bearing, the other isn't/is a source descriptor -
        # can't establish whether they're the same moment
        return UNRESOLVED

    qa, qb = _qualifier_of(claim_a), _qualifier_of(claim_b)
    if (qa or qb) and qa != qb:
        return DIFFERENT_SCOPE   # e.g. "at least 12" vs "confirmed 8", same/no time difference

    if claim_a.get("fact_type") == "percentage" and abs(a - b) <= PERCENTAGE_POINT_TOLERANCE:
        return APPROXIMATION   # Fix 4 - see PERCENTAGE_POINT_TOLERANCE's calibration note above

    rel = _numeric_relationship(a, b)
    if rel is not None:
        return rel
    return CONTRADICTION


def check_all_numeric(claims_a, claims_b):
    out = []
    for a in claims_a:
        if a.get("fact_type") is None:
            continue
        for b in claims_b:
            if b.get("fact_type") is None:
                continue
            out.append({"claim_a": a, "claim_b": b, "relationship": classify_numeric_pair(a, b)})
    return out
