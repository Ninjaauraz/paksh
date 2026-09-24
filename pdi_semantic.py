"""
pdi_semantic.py - PDI's OPTIONAL passage-level semantic scoring.

WHY THIS EXISTS (see the two real Substack shadow experiments' findings): the
deterministic Jaccard relevance in pdi.py's associate_candidate() compares a small,
fixed event-profile token set against the candidate's ENTIRE body text. As body text
grows (Experiment B: RSS <description> -> full <content:encoded>), Jaccard's
denominator (the union of both token sets) grows with it, so relevance systematically
COLLAPSES for longer, genuinely on-topic documents - "more content" made real
candidates score worse, not better (confirmed: mean relevance 0.0471 -> 0.0074).
Jaccard-over-whole-document is structurally the wrong tool for a long discourse
passage; it is not a threshold-tuning problem.

WHAT THIS MODULE DOES: embeds the event's own compact representation (title +
summary - NOT the full article) once, embeds a BOUNDED set of short passages from the
candidate (not the whole document - see split_into_passages()), and returns the
MAX cosine similarity across those passages. Max-pooling over passages is what fixes
the length-dilution problem structurally: a single genuinely relevant paragraph in an
otherwise-unrelated 20,000-character newsletter issue is what should count, not the
whole document's average topic drift. This directly targets the adversarial cases a
whole-document metric cannot: "long article with sparse event references", "event
named only in the title", "event discussed only in the body".

WHY OLLAMA/bge-m3 AND NOT A NEW DEPENDENCY: cluster.py already embeds every Paksh
article through LOCAL Ollama bge-m3 (see cluster.py's own _ollama_embed_batch) - this
is existing, already-required Paksh infrastructure (CLAUDE.md: "Ollama running
locally... Must be running for embed/cluster/analyze/consolidate"), not a new
capability. This module deliberately does NOT import cluster.py (PDI stays isolated
from the production pipeline per its own architecture invariant) - it talks to the
same Ollama HTTP endpoint directly, with its own tiny, independent client using only
`requests` (already a PDI dependency, see pdi_providers.py) and `numpy` (already a
transitive dependency via cluster.py's own requirements).

NON-FATAL BY DESIGN: unlike cluster.py's _ollama_embed_batch (which deliberately
RAISES so a broken embedding backend loudly stops the production pipeline), every
function here CATCHES its own failures and returns None. PDI must never fail or block
on this being unavailable (Part 23) - see pdi.associate_candidate()'s semantic_score
parameter, which is None by default and produces IDENTICAL behavior to the
pre-existing deterministic-only association logic when this module can't reach
Ollama, has no model pulled, or isn't installed in a given environment. This is the
literal "deterministic fallback" required when semantic infrastructure is
unavailable - not a separate code path that might drift from the real one, but the
same functions simply receiving None instead of a float.

EMBEDDINGS ARE NEVER PERSISTED: nothing in this module writes to any database. Vectors
live only for the duration of one pdi.run_pdi_for_event() call, in memory, and are
discarded when it returns - consistent with Candidate.body_text's own "ephemeral,
never persisted raw" contract.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

SEMANTIC_MODEL = os.environ.get("PDI_SEMANTIC_MODEL", "bge-m3")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EMBED_TIMEOUT_S = 60   # non-fatal on purpose - a genuinely unreachable Ollama must
                       # still fall back eventually (Part 23), but this is a real
                       # computation-time budget, not a liveness check. Raised from
                       # 15s -> 30s -> 60s across direct measurement: a single
                       # candidate's ~40 passages took 19.6s; a real multi-candidate
                       # event (2-3 kept candidates x up to 45 passages each) can
                       # exceed 100 texts in one batched call, extrapolating past 60s
                       # of real Ollama compute time on this machine. A shorter
                       # timeout was directly observed silently discarding calls that
                       # would have succeeded a few seconds later, defeating the
                       # MAX_PASSAGES_PER_CANDIDATE fix above. Still bounded and
                       # non-fatal - a genuinely stuck/unreachable Ollama still fails
                       # closed after 60s, not indefinitely, and this is small next to
                       # real per-event discovery time (~45-100s, see pdi_providers.py's
                       # DISCOVERY LATENCY FINDING).

MAX_PASSAGES_PER_CANDIDATE = 45     # bounded, passage-level - never the whole document.
                                     # Raised from 6 (discovery calibration finding):
                                     # split_into_passages() STOPS CHUNKING once this
                                     # count is reached, so passages 7+ were never even
                                     # created, not merely unscored - a real relevant
                                     # paragraph past roughly the first 1800 characters
                                     # of body_text had structurally zero chance of being
                                     # embedded, regardless of scoring logic. An
                                     # intermediate value of 30 was tried and directly
                                     # measured against a real long article: it covered
                                     # only 8,499 of the 12,000-char body_text cap (see
                                     # pdi_providers.py's SUBSTACK_BODY_TEXT_CHAR_CAP),
                                     # missing a real target passage sitting at
                                     # character 10,320 by a real margin - not a
                                     # hypothetical gap. 45 x ~283 measured real
                                     # chars/passage covers the full 12,000-char cap
                                     # with headroom, while remaining a firm, explicit,
                                     # disclosed bound (Part 18), not "the whole
                                     # document."
MAX_PASSAGE_CHARS = 500
SENTENCES_PER_PASSAGE = 3

_SENT_SPLIT_RX = re.compile(r"(?<=[.!?])\s+|\n+")

_availability_cache = {"available": False}


def _embed_batch(texts):
    """POST a batch to Ollama's /api/embed (same endpoint/payload shape as
    cluster.py's _ollama_embed_batch). Returns a list[list[float]] aligned 1:1 with
    `texts`, or None on ANY failure - never raises past this boundary."""
    if not texts:
        return []
    try:
        payload = json.dumps({"model": SEMANTIC_MODEL, "input": texts}).encode("utf-8")
        req = urllib.request.Request(
            OLLAMA_URL + "/api/embed", data=payload,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=EMBED_TIMEOUT_S) as r:
            data = json.loads(r.read().decode("utf-8"))
        vecs = data.get("embeddings") or []
        if len(vecs) != len(texts):
            return None
        return vecs
    except Exception:   # noqa: BLE001 - unreachable/misconfigured Ollama must never
        return None      # propagate into a PDI run (Part 23); caller falls back.


def is_available():
    """Cheap reachability probe, cached only on SUCCESS (a confirmed-reachable Ollama
    is assumed to stay reachable for the rest of the process, avoiding a repeated
    probe before every event's scoring). A FAILED probe is deliberately NOT cached
    permanently - re-probed on the next call instead. This asymmetry is evidence-
    driven, not speculative: a real 12-story shadow run (final hardening pass) hit a
    single transient probe failure at the very first event and, under the old
    permanently-cache-both-outcomes design, silently ran the ENTIRE remaining 11-event
    run in deterministic-only fallback even though Ollama was independently confirmed
    reachable again moments later - one bad probe poisoned a run that otherwise had
    nothing wrong with its semantic backend. Since is_available()/score_candidates()
    are called once per EVENT (never per candidate), the cost of re-probing after a
    failure is bounded (at most one extra ~EMBED_TIMEOUT_S-bounded call per event, not
    per candidate) and is far cheaper than silently discarding semantic scoring for
    an entire run's remaining events over a single transient hiccup."""
    if _availability_cache["available"]:
        return True
    _availability_cache["available"] = _embed_batch(["ping"]) is not None
    return _availability_cache["available"]


def reset_availability_cache():
    """Test-only: forces the next is_available()/score_candidates() call to re-probe
    rather than reuse a cached result from an earlier test in the same process."""
    _availability_cache["available"] = False


def cosine_similarity(a, b):
    import numpy as np
    va, vb = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    na, nb = float(np.linalg.norm(va)), float(np.linalg.norm(vb))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def split_into_passages(text, max_passages=MAX_PASSAGES_PER_CANDIDATE,
                        max_chars=MAX_PASSAGE_CHARS, sentences_per_passage=SENTENCES_PER_PASSAGE):
    """Bounded, deterministic passage chunking - groups a few sentences at a time,
    capped in both count and length, so a 20,000-character article costs the same
    embedding budget as a 500-character one. This is what lets a single relevant
    paragraph register regardless of how much surrounding text is irrelevant (the
    structural fix for Jaccard's whole-document dilution - see module docstring)."""
    text = (text or "").strip()
    if not text:
        return []
    sentences = [s.strip() for s in _SENT_SPLIT_RX.split(text) if s.strip()]
    if not sentences:
        return [text[:max_chars]]
    passages, cur = [], []
    for s in sentences:
        cur.append(s)
        if len(cur) >= sentences_per_passage:
            passages.append(" ".join(cur)[:max_chars])
            cur = []
        if len(passages) >= max_passages:
            break
    if cur and len(passages) < max_passages:
        passages.append(" ".join(cur)[:max_chars])
    return passages[:max_passages]


MAX_RELEVANT_PASSAGES = 2      # bounded passage SET, not top-1 alone - see docstring
RELEVANT_PASSAGE_MARGIN = 0.05  # a runner-up passage counts as "also relevant" only
                                # within this much of the best score


def score_candidates(event_text, candidates_with_text):
    """The ONE entry point pdi.py's orchestration calls, ONCE per PDI run (not once
    per candidate - Part 12's "computational/network implications" answer): embeds
    the event representation once, embeds every kept candidate's passages in a SINGLE
    additional batched request, and returns
    {candidate_key: {"score": max_similarity, "passages": [passage_text, ...]}}.

    WHY A BOUNDED PASSAGE *SET*, NOT JUST THE TOP-1 PASSAGE (hardening-pass Part 9):
    audited adversarially against real documents - a genuinely relevant discussion
    can span two adjacent passages after sentence-grouped chunking (e.g. the setup
    sentence and its follow-through land in different 3-sentence groups), and top-1
    alone would silently drop the second half. Taking every passage within
    RELEVANT_PASSAGE_MARGIN of the single best score (capped at MAX_RELEVANT_PASSAGES)
    recovers that adjacent context while remaining bounded and while still excluding
    the rest of a long, mostly-irrelevant document - it costs NO extra Ollama calls,
    since per-passage similarities are already computed for the max-pooling itself.
    downstream (pdi.py's extract_observations) receives only this bounded passage
    set, never the full document - this is what keeps unrelated material in the same
    long document (e.g. a weekly digest's OTHER, unrelated court items) from
    contaminating observation extraction for a correctly-matched candidate.

    `candidates_with_text` is a list of (candidate_key, text) pairs - the caller
    decides what `candidate_key` is (pdi.py uses provider_item_id) and what `text` to
    score (title + body_text). Returns {} (not None) when semantic scoring is
    unavailable for this run, so callers can use a single `.get(key)` -> None check
    uniformly rather than branching on the whole dict being absent."""
    if not candidates_with_text:
        return {}
    if not is_available():
        return {}
    event_vec_batch = _embed_batch([event_text])
    if event_vec_batch is None:
        return {}
    event_vec = event_vec_batch[0]

    flat_texts, spans = [], []   # spans[i] = (key, start, end) into flat_texts
    for key, text in candidates_with_text:
        passages = split_into_passages(text)
        if not passages:
            continue
        start = len(flat_texts)
        flat_texts.extend(passages)
        spans.append((key, start, len(flat_texts)))
    if not flat_texts:
        return {}

    passage_vecs = _embed_batch(flat_texts)
    if passage_vecs is None:
        return {}

    results = {}
    for key, start, end in spans:
        sims = [(cosine_similarity(event_vec, passage_vecs[i]), flat_texts[i]) for i in range(start, end)]
        if not sims:
            continue
        sims.sort(key=lambda pair: -pair[0])
        top_score = sims[0][0]
        relevant_passages = [text for score, text in sims if score >= top_score - RELEVANT_PASSAGE_MARGIN]
        results[key] = {"score": top_score, "passages": relevant_passages[:MAX_RELEVANT_PASSAGES]}
    return results
