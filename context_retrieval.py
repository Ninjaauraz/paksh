"""
context_retrieval.py - Phase 21D: ISOLATED, EXPERIMENTAL historical-candidate
retrieval module.

NOT IMPORTED BY ANY PRODUCTION CODE PATH. analyze.py, reframe.py, cluster.py,
storylines.py, export_static.py and main.py are all unmodified by this phase
and do not import this file. This module exists so Phase 21D's calibration
experiments and Phase 21E's relationship-judgment work have a single,
testable, read-only implementation of Phase 21C's RETRIEVE stage to build on
- it is not wired into generation.

Read-only: every function here only reads database.py/cluster.py's own read
functions (get_articles_for_events, embeddings_get). Nothing here writes to
paksh.db, the embeddings cache, or any event/article row. No LLM is called
anywhere in this file.

Deterministic: for a fixed database snapshot and fixed parameters, every
function returns identical output on every call (Phase 21D Gate 26). Ties in
similarity are broken by (semantic_similarity, lexical overlap count,
previous_event_id) descending/ascending as documented per function - never by
insertion order or randomness.

Design contract this implements (Phase 21C, Sections 3-7):
  - candidates are OLDER events only (never future, never same event);
  - centroid = unit-normalised mean of member-article bge-m3 vectors, exactly
    storylines.py's own math (re-derived here, not imported, so this module
    has zero runtime dependency on storylines.py's internals changing);
  - topic is NEVER a hard retrieval gate (Phase 21C Section 3.9 / Phase 21B's
    confirmed #17389/#17362 regression);
  - lexical corroboration is REQUIRED, independent of similarity;
  - storyline membership is a signal, never a bypass (Phase 21C Section 6);
  - at most `candidate_budget` candidates are returned.

Every threshold below is a PARAMETER with a clearly-labeled default, not a
hard-coded production constant - Phase 21D's job is to determine, empirically,
which defaults are actually supported by evidence (see the calibration
scripts and PHASE21D_REPORT.md-equivalent chat report, not this file).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np

sys.path.insert(0, r"C:\paksh_project\paksh")
import cluster        # read-only reuse: _keywords/_STOP/_HI_STOP/_GENERIC_KW/_text_of/_emb_key
import database        # read-only reuse: get_articles_for_events/embeddings_get


# --------------------------------------------------------------------------
# time helpers (identical semantics to storylines.py's _ts/_event_date, kept
# local so this module has no import-time dependency on storylines.py)
# --------------------------------------------------------------------------

def _ts(s):
    if not s:
        return None
    x = str(s).replace(" ", "T").replace("Z", "").split("+")[0]
    try:
        return datetime.fromisoformat(x)
    except Exception:
        return None


def event_date(e: dict) -> Optional[datetime]:
    return _ts(e.get("published_at")) or _ts(e.get("created_at"))


# --------------------------------------------------------------------------
# event-centroid construction (Phase 21C Gate 2 / Phase 21D Gate 2)
# --------------------------------------------------------------------------

def build_centroids(events: list[dict]) -> dict[int, np.ndarray]:
    """{event_id: unit-normalised mean-of-member-article-vectors}. Events with
    zero cached member-article vector are simply absent from the result - not
    an error, per Phase 21C Gate 2 ("this is a valid outcome"). Read-only:
    only calls database.get_articles_for_events()/database.embeddings_get()."""
    event_ids = [e["id"] for e in events]
    arts_by_event = database.get_articles_for_events(event_ids)
    ev_keys, all_keys = {}, set()
    for eid, arts in arts_by_event.items():
        keys = [cluster._emb_key(cluster._text_of(a)) for a in arts]
        ev_keys[eid] = keys
        all_keys.update(keys)
    cached = database.embeddings_get(list(all_keys))
    vecs = {}
    for k, b in cached.items():
        try:
            vecs[k] = np.frombuffer(b, dtype=np.float32)
        except Exception:
            pass
    out = {}
    for eid, keys in ev_keys.items():
        arr = [vecs[k] for k in keys if k in vecs]
        if not arr:
            continue
        dim = max(set(v.shape[0] for v in arr), key=[v.shape[0] for v in arr].count)
        arr = [v for v in arr if v.shape[0] == dim]
        if not arr:
            continue
        m = np.mean(np.stack(arr), axis=0)
        n = float(np.linalg.norm(m))
        if n > 0:
            out[eid] = (m / n).astype(np.float32)
    return out


# --------------------------------------------------------------------------
# lexical representation (Phase 21D Gate 8/9/10)
# --------------------------------------------------------------------------

# Reused, never duplicated or modified: cluster.py's own stopword/generic lists.
_STOP = cluster._STOP
_HI_STOP = cluster._HI_STOP
_GENERIC_KW = cluster._GENERIC_KW


def _tokenize(text: str) -> set[str]:
    text = (text or "").lower()
    latin = set(re.findall(r"[a-z][a-z]{2,}", text))
    deva = set(re.findall(r"[\u0900-\u097F]{3,}", text))
    return (latin - _STOP) | (deva - _HI_STOP)


def event_tokens(e: dict, repr_mode: str = "title+200") -> set[str]:
    """repr_mode in {"title", "title+100", "title+200", "title+full"} - Phase
    21D Gate 8's variants. Title is always included; the summary slice length
    is the only thing that varies. Never fabricates tokens from an empty
    summary - an event with no summary simply contributes title tokens only,
    same as any other event under "title" mode."""
    title = e.get("title") or ""
    summary = e.get("summary") or ""
    if repr_mode == "title":
        text = title
    elif repr_mode == "title+100":
        text = f"{title} {summary[:100]}"
    elif repr_mode == "title+200":
        text = f"{title} {summary[:200]}"
    elif repr_mode == "title+full":
        text = f"{title} {summary}"
    else:
        raise ValueError(f"unknown repr_mode {repr_mode!r}")
    return _tokenize(text)


def lexical_overlap(current: dict, candidate: dict, repr_mode: str = "title+200",
                     discount_generic: bool = True) -> tuple[set[str], int]:
    """Returns (shared_terms, corroborating_count). "Discounted" terms (Phase
    21D Gate 9: cluster._GENERIC_KW) are ALWAYS reported in shared_terms for
    diagnostics, but only counted toward corroborating_count when
    discount_generic=False, or when they are NOT in the generic list. This is
    the distinction Gate 9 requires: removed vs discounted, never silently
    both."""
    tc = event_tokens(current, repr_mode)
    tp = event_tokens(candidate, repr_mode)
    shared = tc & tp
    if discount_generic:
        counted = shared - _GENERIC_KW
    else:
        counted = shared
    return shared, len(counted)


def is_thin(e: dict, min_summary_chars: int = 40) -> bool:
    """Phase 21C Gate E's `thin_source` flag. An event is thin if its summary
    is missing or trivially short - never a judgment about topic/quality,
    purely a length signal so Stage 2 can be more conservative (Phase 21C
    Section 20)."""
    return len((e.get("summary") or "").strip()) < min_summary_chars


# --------------------------------------------------------------------------
# candidate object (Phase 21C Gate E / Phase 21D Gate 1)
# --------------------------------------------------------------------------

@dataclass
class Candidate:
    previous_event_id: int
    title: str
    summary: str
    date: Optional[str]
    topic: Optional[str]
    region: Optional[str]
    semantic_similarity: float
    lexical_overlap_terms: list[str] = field(default_factory=list)
    lexical_overlap_count: int = 0
    same_storyline: bool = False
    thin_source: bool = False
    gap_days: Optional[int] = None   # diagnostic only - not part of the Phase 21C
                                      # minimum contract, kept because Section 1's
                                      # exception clause permits a genuinely useful
                                      # diagnostic field


# --------------------------------------------------------------------------
# retrieval (Phase 21C Gates A-K / Phase 21D Gates 3-14, 21-22)
# --------------------------------------------------------------------------

def retrieve_historical_candidates(
    current_event_id: int,
    events_by_id: dict[int, dict],
    centroids: dict[int, np.ndarray],
    storyline_emap: Optional[dict[int, str]] = None,
    *,
    lookback_days: Optional[float] = 56,
    cosine_threshold: float = 0.78,   # Phase 21D.1: 0.80 (storylines.py's inherited SIM)
                                       # measurably under-recalls on the 44-pair benchmark
                                       # (0.73 vs 0.81 at equal-or-better precision) - see the
                                       # Phase 21D.1 report's Gate 4 sweep, not yet hard-locked
    lexical_repr: str = "title+200",
    lexical_min_overlap: int = 4,     # Phase 21D.1: raised from storylines.py's inherited 3 -
                                       # clear precision gain (0.47->0.64 on the 21D benchmark)
                                       # at zero recall cost, confirmed again at n=44
    discount_generic: bool = True,
    storyline_mode: str = "S3",       # "S0" ignore | "S1" tiebreak | "S2" rank boost | "S3" preserve-after-qualify
                                       # Phase 21D.1: S3 is the only mode that measurably changed
                                       # accept/reject on real storyline-linked pairs (S1/S2 only
                                       # affect ordering among already-accepted candidates, not
                                       # acceptance) - S3 recovered 2/15 additional genuine
                                       # storyline-linked relationships at zero added false positives
    storyline_boost: float = 0.03,    # only used by S2; a small, explicit, documented constant - not tuned ML
    candidate_budget: int = 3,
    raw_topn: int = 50,
) -> list[Candidate]:
    """Deterministic. Never mutates anything. Returns <= candidate_budget
    Candidate objects, newest-relationship-first by the combined ranking
    (Phase 21D Gate 22). Ties broken by (semantic_similarity desc,
    lexical_overlap_count desc, previous_event_id asc) - fully deterministic.

    current_event_id must be in events_by_id. If it has no centroid, or no
    OLDER event has a centroid, returns [] - a valid, expected outcome
    (Phase 21C Gate 2), never an error.
    """
    storyline_emap = storyline_emap or {}
    cur = events_by_id.get(current_event_id)
    if cur is None:
        return []
    cur_vec = centroids.get(current_event_id)
    if cur_vec is None:
        return []
    cur_date = event_date(cur)
    if cur_date is None:
        return []

    # Stage: eligibility (Phase 21D Gate 3) - strictly older, has a centroid,
    # within lookback (None = full available history).
    pool = []
    for oid, ovec in centroids.items():
        if oid == current_event_id:
            continue
        oe = events_by_id.get(oid)
        if oe is None:
            continue
        od = event_date(oe)
        if od is None or od >= cur_date:
            continue                      # not genuinely historical - excluded, never guessed
        gap = (cur_date - od).days
        if lookback_days is not None and gap > lookback_days:
            continue
        pool.append((oid, oe, ovec, gap))

    # Stage: raw semantic ranking (Phase 21D Gate 5) - diagnostic-visible cut
    # BEFORE the lexical gate, so a caller can tell "not in top-N by
    # similarity" apart from "similar but lexically unsupported".
    scored = [(float(np.dot(cur_vec, ovec)), oid, oe, gap) for oid, oe, ovec, gap in pool]
    scored.sort(key=lambda t: (-t[0], t[1]))
    top_raw = scored[:raw_topn]

    # Stage: combined gate (Phase 21D Gate 13's "Model D": semantic + lexical
    # + generic-discount + storyline signal).
    accepted = []
    for sim, oid, oe, gap in top_raw:
        if sim < cosine_threshold:
            continue
        shared, count = lexical_overlap(cur, oe, lexical_repr, discount_generic)
        same_story = storyline_emap.get(current_event_id) is not None and \
                     storyline_emap.get(current_event_id) == storyline_emap.get(oid)
        min_overlap = lexical_min_overlap
        if storyline_mode == "S3" and same_story:
            min_overlap = max(0, lexical_min_overlap - 2)   # storyline candidates get an
                                                              # explicit, bounded, documented
                                                              # preservation allowance - never
                                                              # a full bypass (never 0 unless
                                                              # lexical_min_overlap<=2 already)
        if count < min_overlap:
            continue
        rank_score = sim
        if storyline_mode == "S2" and same_story:
            rank_score = sim + storyline_boost
        accepted.append((rank_score, sim, count, oid, oe, shared, gap, same_story))

    if storyline_mode == "S1":
        # tiebreaker only: storyline candidates win ties at equal (sim, count)
        accepted.sort(key=lambda t: (-round(t[0], 6), -t[2], not t[7], t[3]))
    else:
        accepted.sort(key=lambda t: (-round(t[0], 6), -t[2], t[3]))

    out = []
    for rank_score, sim, count, oid, oe, shared, gap, same_story in accepted[:candidate_budget]:
        out.append(Candidate(
            previous_event_id=oid,
            title=oe.get("title") or "",
            summary=oe.get("summary") or "",
            date=(event_date(oe).isoformat() if event_date(oe) else None),
            topic=oe.get("topic"),
            region=oe.get("region"),
            semantic_similarity=round(sim, 4),
            lexical_overlap_terms=sorted(shared),
            lexical_overlap_count=count,
            same_storyline=same_story,
            thin_source=is_thin(oe) or is_thin(cur),
            gap_days=gap,
        ))
    return out
