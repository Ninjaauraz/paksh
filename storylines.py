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
import json
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

    storylines, emap = [], {}
    for members in comps.values():
        if len(members) < MIN_EVENTS or len(members) > MAX_EVENTS:
            continue                                   # too few = not a thread; too many = topic-drift
        members.sort(key=lambda e: dt[e["id"]])
        sid = "sl-" + str(min(m["id"] for m in members))
        ev_list = [{
            "id": m["id"], "title": m["title"], "title_hi": m.get("title_hi", ""),
            "date": (dt[m["id"]].isoformat() if dt[m["id"]] else None),
            "topic": m.get("topic"), "dominant": m.get("dominant"),
            "blindspot": m.get("blindspot"), "lean_counts": m.get("lean_counts", {}),
        } for m in members]
        latest = members[-1]
        storylines.append({
            "id": sid,
            "title": latest["title"], "title_hi": latest.get("title_hi", ""),
            "topic": latest.get("topic"), "region": latest.get("region", "India"),
            "n_events": len(members),
            "start": ev_list[0]["date"], "end": ev_list[-1]["date"], "updated_at": ev_list[-1]["date"],
            "events": ev_list,
        })
        for m in members:
            emap[m["id"]] = sid

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
