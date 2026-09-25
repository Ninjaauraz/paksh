"""Link separate EVENTS into one STORYLINE — a saga tracked across days.

An *event* is Paksh's per-moment cluster of articles about one happening. A *storyline*
is a thread of events that keep developing the same story over time — a bill introduced,
debated, passed, then challenged; an attack, the investigation, the arrests, the verdict.

HOW WE LINK (all derived, never touches the arithmetic bias bar):
  * an event's vector = the normalised MEAN of its member articles' bge-m3 vectors, read
    straight from the embedding cache in paksh.db (the SAME vectors used to cluster the
    articles in the first place). No new embedding calls, no Ollama needed at build time.
  * two events join a storyline when they are (a) the same TOPIC, (b) within a rolling
    WINDOW of days, (c) cosine-similar at/above SIM, AND (d) share at least one
    discriminating keyword in their titles (a guard against merging unrelated stories).
  * connected components of that graph, with >= MIN_EVENTS members, become storylines.

Output is pure JSON (emitted by export_static): a storylines index + a per-event
storyline id, so the Story page can show "how this developed" and a Storyline page can
show the whole thread. Nothing here writes to the events table.

Tunables via env: PAKSH_STORYLINE_LOOKBACK / _WINDOW / _SIM.
Standalone:  py storylines.py        # prints how many sagas were found + their sizes
"""

import os
import re
import json
import difflib
from datetime import datetime, timedelta

import numpy as np

import database
import cluster  # reuse the exact embedding-key + keyword logic used for clustering

LOOKBACK_DAYS = int(os.environ.get("PAKSH_STORYLINE_LOOKBACK", "45"))
WINDOW_DAYS   = int(os.environ.get("PAKSH_STORYLINE_WINDOW", "14"))
SIM           = float(os.environ.get("PAKSH_STORYLINE_SIM", "0.80"))
MIN_EVENTS    = int(os.environ.get("PAKSH_STORYLINE_MIN", "2"))
# A shared TOPIC + one keyword is not enough — "Parliament"/"India" chain unrelated stories into
# one blob. Require several shared discriminating title words AND a high cosine, so only events
# that are really the same saga link. MAX_EVENTS is a safety net: a "storyline" bigger than this
# is topic-drift, not a saga, so we drop it rather than publish a false thread.
MIN_SHARED_KW = int(os.environ.get("PAKSH_STORYLINE_KW", "3"))
MAX_EVENTS    = int(os.environ.get("PAKSH_STORYLINE_MAX", "25"))

# 2026-09-25 developing-stories hardening: a later event can pass the linking test above (same
# saga) yet just re-report facts an earlier entry already carries — e.g. three outlets covering
# the same statement minutes apart. DUP_TEXT_SIM controls the deterministic fallback below; raise
# it to collapse fewer entries, lower it to collapse more.
DUP_TEXT_SIM = float(os.environ.get("PAKSH_STORYLINE_DUP_SIM", "0.86"))
_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_PROPER_RE = re.compile(r"\b[A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]{2,})*\b")


def _ts(s):
    if not s:
        return None
    x = str(s).replace(" ", "T").replace("Z", "").split("+")[0]
    try:
        return datetime.fromisoformat(x)
    except Exception:
        return None


def _event_date(e):
    # Real publish time of the newest source article when we have it, else pipeline time.
    return _ts(e.get("published_at")) or _ts(e.get("created_at"))


def _centroids(events):
    """{event_id: unit vector} built ONLY from cached article embeddings (no new calls).
    Events with no cached member vector are omitted (they simply can't be linked)."""
    ev_keys, all_keys = {}, set()
    arts_by_event = database.get_articles_for_events([e["id"] for e in events])
    for e in events:
        arts = arts_by_event.get(e["id"], [])
        keys = [cluster._emb_key(cluster._text_of(a)) for a in arts]
        ev_keys[e["id"]] = keys
        all_keys.update(keys)
    cached = database.embeddings_get(list(all_keys))            # {key: raw bytes}
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
        # guard against any stray vector of a different dimension (mixed backends)
        dim = max(set(v.shape[0] for v in arr), key=[v.shape[0] for v in arr].count)
        arr = [v for v in arr if v.shape[0] == dim]
        if not arr:
            continue
        m = np.mean(np.stack(arr), axis=0)
        n = float(np.linalg.norm(m))
        if n > 0:
            out[eid] = (m / n).astype(np.float32)
    return out


def _kwset(title):
    try:
        return set(cluster._keywords({"title": title or "", "summary": ""}))
    except Exception:
        return set()


def _fact_tokens(text):
    """Cheap, deterministic signal of "what this text actually claims": the numbers in it
    (casualty/death/injury counts, dates, amounts, ...) and its proper-noun phrases (named
    actors, places, organisations). No LLM, no embeddings — plain regex over already-generated
    summary text."""
    text = text or ""
    return set(_NUM_RE.findall(text)), set(_PROPER_RE.findall(text))


def _verified_update(conn, prev_id, curr_id):
    """True if Story Intelligence (si_queue.py) has ALREADY verified — offline, no call made
    here — that curr_id relates back to prev_id specifically. None means nothing verified yet
    (SI coverage is partial), so the caller should fall back to the deterministic text check.
    Reuses reader_context.build_story_context(), the one sanctioned read boundary onto that
    data (see reader_context.py's own module docstring); that function is itself no-LLM and
    fails closed to None on any error, so this never raises and never calls a model."""
    if conn is None:
        return None
    try:
        import reader_context
        ctx = reader_context.build_story_context(conn, curr_id)
    except Exception:
        return None
    if not ctx:
        return None
    return True if (ctx.get("historical_event") or {}).get("id") == prev_id else None


def _is_meaningful_update(prev_event, curr_event, conn=None):
    """Does curr_event (the next entry after prev_event in the same storyline) carry
    genuinely new information, or does it just re-report what prev_event already said?

    Deliberately biased toward True (treat it as a real development) whenever the evidence is
    thin: the failure mode we're fixing is near-duplicate re-reports crowding the timeline, not
    a shortage of entries, so nothing here should ever suppress an update it isn't confident is
    a duplicate. New figures or a newly-named actor/place always win regardless of overall text
    similarity; only near-identical text WITH no new figures/names is collapsed.
    """
    verified = _verified_update(conn, prev_event.get("id"), curr_event.get("id"))
    if verified is not None:
        return verified
    prev_text = " ".join([prev_event.get("summary") or ""] + list(prev_event.get("summary_points") or []))
    curr_text = " ".join([curr_event.get("summary") or ""] + list(curr_event.get("summary_points") or []))
    if not prev_text.strip() or not curr_text.strip():
        return True   # nothing usable to compare against — don't hide it
    prev_nums, prev_names = _fact_tokens(prev_text)
    curr_nums, curr_names = _fact_tokens(curr_text)
    if (curr_nums - prev_nums) or (curr_names - prev_names):
        return True   # new figures or a new named actor/location -> genuine development
    ratio = difflib.SequenceMatcher(None, prev_text, curr_text).ratio()
    return ratio < DUP_TEXT_SIM   # near-identical text, nothing new -> re-report, collapse


def build_storylines(events):
    """events = database.get_all_events() rows. Returns (storylines_list, event_id->storyline_id).
    storylines_list is newest-development first; each carries its events sorted oldest->newest."""
    now = datetime.utcnow()
    recent = []
    for e in events:
        d = _event_date(e)
        if d and (now - d).days <= LOOKBACK_DAYS:
            recent.append(e)
    if not recent:
        return [], {}

    cents = _centroids(recent)
    recent = [e for e in recent if e["id"] in cents]
    if len(recent) < MIN_EVENTS:
        return [], {}

    dt = {e["id"]: _event_date(e) for e in recent}
    kw = {e["id"]: _kwset(e.get("title")) for e in recent}

    parent = {e["id"]: e["id"] for e in recent}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Only compare events in the SAME topic; within a topic, sort by time so the window
    # check can break early. This keeps the pass near-linear even on a busy corpus.
    by_topic = {}
    for e in recent:
        by_topic.setdefault(e.get("topic") or "General", []).append(e)

    for group in by_topic.values():
        group.sort(key=lambda e: dt[e["id"]])
        n = len(group)
        for i in range(n):
            ei = group[i]["id"]; vi = cents[ei]
            for j in range(i + 1, n):
                ej = group[j]["id"]
                gap = (dt[ej] - dt[ei]).days
                if gap > WINDOW_DAYS:
                    break                              # sorted -> everything after is farther
                if len(kw[ei] & kw[ej]) < MIN_SHARED_KW:
                    continue                           # need several shared discriminating words
                if float(np.dot(vi, cents[ej])) >= SIM:
                    union(ei, ej)

    comps = {}
    for e in recent:
        comps.setdefault(find(e["id"]), []).append(e)

    # One connection, reused for every storyline's duplicate check below (read-only; see
    # _verified_update). Best-effort: if the DB isn't reachable for some reason, every check
    # just falls back to the deterministic text heuristic instead of failing the whole export.
    try:
        conn = database.get_connection()
    except Exception:
        conn = None

    storylines, emap = [], {}
    try:
        for members in comps.values():
            if len(members) < MIN_EVENTS or len(members) > MAX_EVENTS:
                continue                               # too few = not a thread; too many = topic-drift
            members.sort(key=lambda e: dt[e["id"]])
            sid = "sl-" + str(min(m["id"] for m in members))
            ev_list = []
            last_kept = members[0]                      # the saga's own opening entry is never "a duplicate"
            for idx, m in enumerate(members):
                is_update = True if idx == 0 else _is_meaningful_update(last_kept, m, conn)
                if is_update:
                    last_kept = m
                ev_list.append({
                    "id": m["id"], "title": m["title"], "title_hi": m.get("title_hi", ""),
                    "date": (dt[m["id"]].isoformat() if dt[m["id"]] else None),
                    "topic": m.get("topic"), "dominant": m.get("dominant"),
                    "blindspot": m.get("blindspot"), "lean_counts": m.get("lean_counts", {}),
                    # False = this entry re-reports facts an earlier entry already carries; the
                    # frontend keeps it in the thread's total but doesn't surface it as its own
                    # "update" row. See storylines.py::_is_meaningful_update.
                    "is_update": is_update,
                })
            latest = members[-1]
            n_updates = sum(1 for ev in ev_list if ev["is_update"])
            storylines.append({
                "id": sid,
                "title": latest["title"], "title_hi": latest.get("title_hi", ""),
                "topic": latest.get("topic"), "region": latest.get("region", "India"),
                "n_events": len(members), "n_updates": n_updates,
                "start": ev_list[0]["date"], "end": ev_list[-1]["date"], "updated_at": ev_list[-1]["date"],
                "events": ev_list,
            })
            for m in members:
                emap[m["id"]] = sid
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    storylines.sort(key=lambda s: s.get("updated_at") or "", reverse=True)
    return storylines, emap


def main():
    database.init_db()
    events = database.get_all_events()
    storylines, emap = build_storylines(events)
    print(f"[storylines] {len(events)} events -> {len(storylines)} storylines "
          f"covering {len(emap)} events (lookback={LOOKBACK_DAYS}d, window={WINDOW_DAYS}d, sim={SIM})")
    for s in storylines[:15]:
        print(f"  · {s['n_events']:2d} events · {s['topic']:<14} · {s['start'][:10]}→{s['end'][:10]} · {s['title'][:70]}")


if __name__ == "__main__":
    main()
