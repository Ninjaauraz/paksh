"""evidence_quality.py - Phase 4 PROTOTYPE (Evidence Acquisition + Factuality System
audit): deterministic evidence-quality classification. Pure functions, no I/O, no
DB writes. NOT wired into production - reuses evidence_retrieval.py's existing
extraction fields/method tags rather than inventing a parallel scheme.

Thresholds below are PROPOSED, informed by the live retrieval probe run during this
audit (32 real production URLs: genuine full articles measured 2,156-7,663 chars once
the old 2000-char cap was removed) - they are not yet validated at scale and should be
checked against the Phase 12 benchmark / Phase 13 shadow trial before being treated as
final.
"""

FULL = "FULL"
MAJORITY = "MAJORITY"
PARTIAL = "PARTIAL"
METADATA_ONLY = "METADATA_ONLY"
FAILED = "FAILED"

TIER_RANK = {FULL: 0, MAJORITY: 1, PARTIAL: 2, METADATA_ONLY: 3, FAILED: 4}

JSONLD_MIN_CHARS = 400          # a JSON-LD articleBody is publisher-declared complete;
                                 # this floor only guards against an accidentally-tiny stub
MAJORITY_MIN_CHARS = 1200       # DOM-scraped body with no "this is complete" signal from
                                 # the publisher - probe showed real articles run 2k-7.6k
PARTIAL_MIN_CHARS = 200         # matches evidence_retrieval.py's existing MIN_USABLE_TEXT


def classify(evidence_row):
    """evidence_row: a dict shaped like an si_evidence row - keys: status
    (ok|blocked|failed|skipped), extraction_status (ok|short|empty|failed|not_article|
    None), text, method. Pass None for an article with no fetch attempt at all (e.g. a
    GDELT-only article: metadata was never even attempted to be enriched).
    -> one of FULL / MAJORITY / PARTIAL / METADATA_ONLY / FAILED."""
    if evidence_row is None:
        return METADATA_ONLY
    if evidence_row.get("status") != "ok":
        return FAILED                              # a real attempted fetch that did not succeed
    extraction_status = evidence_row.get("extraction_status")
    if extraction_status in ("empty", "not_article", None):
        return METADATA_ONLY
    text = evidence_row.get("text") or ""
    length = len(text)
    method = evidence_row.get("method") or ""
    if extraction_status == "short":
        return PARTIAL if length >= PARTIAL_MIN_CHARS else METADATA_ONLY
    # extraction_status == "ok"
    if method.startswith("json-ld:articleBody") and length >= JSONLD_MIN_CHARS:
        return FULL
    if method.startswith("dom:article-paragraphs") and length >= MAJORITY_MIN_CHARS:
        return MAJORITY
    if length >= PARTIAL_MIN_CHARS:
        return PARTIAL
    return METADATA_ONLY


def context_slice(text, max_chars=2000):
    """Bounded slice for the LLM PROMPT only (Phase 2.1). Storage keeps the full
    extracted text; this is the one deliberate, visible truncation point - never
    silent inside the extractor itself."""
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    sp = cut.rfind(" ")
    return cut[:sp] if sp > 0 else cut


def best_tier(rows):
    """rows: iterable of evidence_row dicts (or None). -> the single best tier
    present, or FAILED if the list is empty."""
    tiers = [classify(r) for r in rows] or [FAILED]
    return min(tiers, key=lambda t: TIER_RANK[t])
