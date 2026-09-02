"""
context_narration.py - Phase 21F (overnight): ISOLATED delta generation for
Paksh's Story Memory - "what materially changed between the historical
observation and the current Event."

NOT IMPORTED BY ANY PRODUCTION CODE PATH. analyze.py, reframe.py,
export_static.py are all unmodified and do not import this file.

Architecture boundary (directive Section 19, this session):
  SUMMARY (analyze.py, untouched by this module): what happened in the
    current Event. This module NEVER rewrites or touches summary text.
  HISTORICAL CONTEXT (story_memory.get_verified_context, already built):
    which verified prior events relate to this one, and how (relationship
    type + frozen snapshot) - purely a read, no LLM.
  DELTA (this module, the one new LLM-touching capability): what materially
    changed between the FROZEN historical observation and the CURRENT
    event. Never another summary, never a generic recap, never invented
    chronology or causality. If the two texts don't support a real,
    checkable delta, this module produces NOTHING rather than pad one out -
    identical fail-closed discipline to relationship_judgment.py's A1.
  L/C/R (analyze.py's existing framing, untouched by this module): what the
    coverage corpus foregrounds. Never conflated with delta.

Read-only with respect to paksh.db by itself: generate_delta() takes plain
dicts/strings and returns text; persisting a delta (story_memory.py's
event_deltas table) is the caller's separate, explicit decision.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, r"C:\paksh_project\paksh")
import analyze   # read-only reuse: _gemini_generate - same call path Stage 2 already uses


@dataclass
class DeltaResult:
    delta_text: Optional[str]
    generated: bool           # False if the model declined (insufficient basis) or output was rejected
    reject_reason: Optional[str] = None


_RELATIONSHIP_FRAME = {
    "R1": "continues the same developing story as",
    "R2": "is a documented response to",
    "R3": "materially escalates the situation described in",
    "R4": "is explained by necessary background from",
}


def build_delta_prompt(current_event: dict, historical_observation: dict, relationship_type: str) -> str:
    frame = _RELATIONSHIP_FRAME.get(relationship_type, "relates to")
    return f"""You are writing ONE short delta statement for Paksh, a news-transparency
platform. A delta answers exactly one question: "what materially changed between
the EARLIER event below and the CURRENT event below?" - nothing else.

HARD RULES:
1. Use ONLY the text supplied below. Never use outside knowledge about these
   people, organizations, or events. If the supplied text doesn't say it, it
   doesn't count.
2. Do NOT summarize either event on its own - a reader already has both
   summaries. Name only what is DIFFERENT, NEW, or CHANGED between them (a
   number that moved, a status that changed, an action that was taken since,
   a claim that was confirmed or contradicted).
3. Never invent a cause, a chronology, or a connection stronger than the text
   supports, even though the CURRENT event {frame} the EARLIER event (a
   verified relationship - do not treat this label as license to invent
   detail beyond what the two texts actually say).
4. If the two texts do not actually support a specific, checkable delta
   (e.g. the earlier text is too thin, or the current event doesn't clearly
   build on a specific detail from it), respond with exactly the single word
   NONE - do not pad out a vague statement. NONE is a correct, safe, common
   answer, not a failure.
5. One or two sentences maximum. Plain language, no hedging filler ("it
   appears that", "reports suggest").

EARLIER EVENT (verified {relationship_type}):
  title: {historical_observation.get('title', '')}
  summary: {historical_observation.get('summary', '') or '(no summary available)'}

CURRENT EVENT:
  title: {current_event.get('title', '')}
  summary: {current_event.get('summary', '') or '(no summary available)'}

Respond with ONLY the delta sentence(s), or ONLY the word NONE. No labels, no
markdown, no commentary.
"""


def _looks_like_a_summary(text: str, current_summary: str) -> bool:
    """Cheap guard against Rule 2 violations: if the delta text is near-
    identical to the current event's own summary, it isn't a delta, it's a
    restatement. Not a semantic check - a last, mechanical backstop."""
    a = set(re.findall(r"[a-z]{4,}", text.lower()))
    b = set(re.findall(r"[a-z]{4,}", (current_summary or "").lower()))
    if not a or not b:
        return False
    overlap = len(a & b) / len(a)
    return overlap > 0.8 and len(a) >= 6


def generate_delta(current_event: dict, historical_observation: dict, relationship_type: str,
                    generate_fn=None) -> DeltaResult:
    """generate_fn(prompt: str) -> str. Defaults to a real Gemini call via
    analyze._gemini_generate (as_json=False - this is prose, not JSON), the
    same call path Stage 2 already uses. Pass a mock generate_fn for
    deterministic tests."""
    prompt = build_delta_prompt(current_event, historical_observation, relationship_type)
    if generate_fn is None:
        generate_fn = lambda p: analyze._gemini_generate(p, as_json=False)
    try:
        raw = (generate_fn(prompt) or "").strip()
    except Exception as e:
        return DeltaResult(delta_text=None, generated=False, reject_reason=f"LLM call failed: {e}")

    if not raw or raw.strip().upper() == "NONE":
        return DeltaResult(delta_text=None, generated=False, reject_reason="model declined (NONE)")
    if len(raw) > 600:
        return DeltaResult(delta_text=None, generated=False, reject_reason="response too long, likely not a delta")
    if _looks_like_a_summary(raw, current_event.get("summary", "")):
        return DeltaResult(delta_text=None, generated=False,
                            reject_reason="response is a near-restatement of the current summary, not a delta")
    return DeltaResult(delta_text=raw, generated=True)
