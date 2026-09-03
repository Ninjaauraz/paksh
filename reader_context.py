"""
reader_context.py - Phase 21G: converts story_memory's internal
VerifiedContext into the minimal, reader-facing "story_context" object
consumed by export_static.py and, from there, the story page.

This is the ONE canonical integration boundary between Story Memory and the
reader experience (directive Section 14: "Do NOT duplicate relationship-
selection logic in UI code. Do NOT independently query event_relationships
from multiple places."). export_static.py calls build_story_context() and
nothing else ever touches event_relationships/event_deltas for reader-facing
purposes.

Deliberately narrow: internal fields (relationship_type code, confidence,
evidence, judge_version, Stage-1 similarity/lexical counts, raw snapshot
lean_counts/summary_points/topic/region/fingerprint) all stop here and are
never present in the returned dict. Only what a reader-facing page actually
needs crosses this boundary.

Read-only: calls only story_memory.get_verified_context() (itself read-only,
no LLM, no mutation - see its own Test 13/15-style static guarantee).
"""

from __future__ import annotations

from typing import Optional

import story_memory as sm

# Short, fixed, hand-written editorial labels - never the raw R1/R2/R3/R4 code,
# never a confidence score. Deliberately NOT varied/templated per instance: these
# are categorical chrome (the same kind of fixed short label as "Left/Centre/
# Right" or the Storyline header "How this developed"), not generated prose -
# the genuinely dynamic, non-repetitive content is delta_text, generated
# separately per relationship by context_narration.py.
_RELATIONSHIP_LABEL = {
    "R1": {"en": "Continues an earlier story", "hi": "पहले की घटना की अगली कड़ी"},
    "R2": {"en": "A response to an earlier development", "hi": "पहले के घटनाक्रम पर प्रतिक्रिया"},
    "R3": {"en": "An escalation of an earlier dispute", "hi": "पहले के विवाद में वृद्धि"},
    "R4": {"en": "Background to this story", "hi": "इस खबर की पृष्ठभूमि"},
}


def _shape(item) -> Optional[dict]:
    """Converts one story_memory.VerifiedContext into the lean reader dict,
    or None if it isn't safe/complete enough to show (Section 21's required
    test list: unknown relationship_type, missing/empty snapshot title)."""
    label = _RELATIONSHIP_LABEL.get(item.relationship_type)
    title = (item.historical_observation or {}).get("title")
    if label is None or not title or not str(title).strip():
        return None
    out = {
        "relationship_label": label,
        "historical_event": {
            "id": item.previous_event_id,
            "title": title,
            "date": item.historical_event_date,
        },
    }
    delta = item.delta or {}
    delta_text = delta.get("delta_text")
    if delta_text and not delta.get("stale") and str(delta_text).strip():
        out["delta_text"] = delta_text
    return out


def build_story_context(conn, event_id: int, max_hops: int = 2) -> Optional[dict]:
    """Returns a lean dict, or None if there is nothing safe/meaningful to
    show. Fails closed on every invalid shape (Section 21's required test
    list): no verified relationship, invalidated/superseded (never returned
    by get_verified_context in the first place), missing/incomplete
    historical snapshot, unknown relationship_type, malformed data.

    Only ONE verified relationship is surfaced - Section 9's "do not create
    an infinite chronology". A fuller chronological chain is Storyline's job
    (broad, similarity-based, already on the page); this block is the one
    verified, specific connection, not a second timeline. Among multiple
    candidates, one carrying a valid delta ("what changed") is preferred -
    real validation against #17464 (this session) surfaced two genuine
    relationships, and picking by recency alone would have silently shown
    the thinner one and hidden a validated, more informative delta. Ties
    (or no delta anywhere) fall back to get_verified_context's own order
    (closest hop, most-recently-decided first).
    """
    try:
        items = sm.get_verified_context(conn, event_id, max_hops=max_hops)
    except Exception:
        return None  # fail closed - a story page must never break because this failed

    shaped = [s for s in (_shape(i) for i in items) if s is not None]
    if not shaped:
        return None
    for s in shaped:
        if "delta_text" in s:
            return s
    return shaped[0]
