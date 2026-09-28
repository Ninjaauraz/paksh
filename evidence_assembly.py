"""evidence_assembly.py - Phase 6 PROTOTYPE: syndication/near-duplicate detection and
multi-source evidence grouping. Pure functions, no I/O, no network calls, no DB writes.
NOT wired into production.

Purpose: so that N outlets running the identical wire-copy story count as ONE
independent evidence unit, not N independent confirmations (the user's explicit Phase
6 requirement). Exact duplicates use si_evidence's existing content_hash (already
computed today, just unused for this); near-duplicates (reworded lede, same wire
body) use a deterministic 5-word-shingle Jaccard comparison - no new dependency, zero
marginal cost, fully auditable. The 0.6 threshold below is PROPOSED and must be
checked against real syndicated/non-syndicated pairs before being trusted as final.
"""
import re

from evidence_quality import TIER_RANK, FAILED

SHINGLE_K = 5
SYNDICATION_THRESHOLD = 0.6


def _shingles(text, k=SHINGLE_K):
    words = re.sub(r"[^\w\s]", " ", (text or "").lower()).split()
    if len(words) < k:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i:i + k]) for i in range(len(words) - k + 1)}


def jaccard(set_a, set_b):
    if not set_a or not set_b:
        return 0.0
    union = len(set_a | set_b)
    return len(set_a & set_b) / union if union else 0.0


def is_syndicated(text_a, text_b, threshold=SYNDICATION_THRESHOLD):
    """True if two extracted article bodies look like the same underlying wire
    copy (near-identical text), regardless of which outlet ran it."""
    if not text_a or not text_b:
        return False
    return jaccard(_shingles(text_a), _shingles(text_b)) >= threshold


def group_independent(articles):
    """articles: list of dicts, each at least {source, text, tier, content_hash?}.
    -> list of GROUPS (each a list of the articles in it), representing INDEPENDENT
    evidence units - members of a group are the same underlying report, syndicated
    or a near-verbatim rewrite of it. Groups are ordered best-tier-first; within a
    group, members are ordered best-tier-first so group[0] is the representative."""
    groups = []
    for a in articles:
        placed = False
        for g in groups:
            rep = g[0]
            if rep.get("content_hash") and a.get("content_hash") and rep["content_hash"] == a["content_hash"]:
                g.append(a)
                placed = True
                break
            if is_syndicated(rep.get("text", ""), a.get("text", "")):
                g.append(a)
                placed = True
                break
        if not placed:
            groups.append([a])
    for g in groups:
        g.sort(key=lambda x: TIER_RANK.get(x.get("tier", FAILED), 9))
    groups.sort(key=lambda g: TIER_RANK.get(g[0].get("tier", FAILED), 9))
    return groups


def group_summary(groups):
    """[{outlets: [...], group_size: n, tier: best_tier, representative_source}]
    - the shape carried forward into claim extraction, so a claim's provenance
    always says how many outlets actually ran this exact report, not just which
    outlet the representative text came from."""
    out = []
    for g in groups:
        out.append({
            "outlets": [a.get("source") for a in g],
            "group_size": len(g),
            "tier": g[0].get("tier"),
            "representative_source": g[0].get("source"),
            "representative_text": g[0].get("text"),
        })
    return out
