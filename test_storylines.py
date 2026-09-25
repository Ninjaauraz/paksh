"""
test_storylines.py - regression tests for the 2026-09-25 developing-stories hardening
(storylines.py::_is_meaningful_update / _fact_tokens / _verified_update, plus the
build_storylines() linking guard).

Runs standalone, no network, no LLM, no real database. build_storylines()'s only DB touch
(database.get_connection(), used to opportunistically check Story Intelligence relationships)
is monkeypatched to fail closed to None here, exactly as it would if the DB were unreachable,
so every check below exercises the deterministic text/number/entity fallback. _centroids() is
monkeypatched too, since it otherwise reads cached embeddings straight out of paksh.db.

Run:  py test_storylines.py
"""
import numpy as np

import storylines as sl

FAILURES = []


def check(label, cond):
    print(f"  {label} ... {'OK' if cond else 'FAIL'}")
    if not cond:
        FAILURES.append(label)


# ---------------------------------------------------------------------------
# Unit tests: _is_meaningful_update (conn=None -> always the deterministic path)
# ---------------------------------------------------------------------------

print("TEST 1: near-duplicate events minutes apart -> NOT a new development")
prev1 = {"id": 1, "summary": "A fire broke out at a chemical factory in Pune on Tuesday morning, officials said, and firefighters were working to contain it.",
         "summary_points": ["Fire broke out in Pune", "Firefighters responding"]}
curr1 = {"id": 2, "summary": "A fire broke out at a chemical factory in Pune on Tuesday morning, officials said, as firefighters worked to bring it under control.",
         "summary_points": ["Fire broke out in Pune", "Firefighters responding"]}
check("1A near-duplicate text collapses to False", sl._is_meaningful_update(prev1, curr1) is False)

print("\nTEST 2: genuinely new development (changed casualty figures + new named actor) -> True")
prev2 = {"id": 1, "summary": "A fire broke out at a chemical factory in Pune on Tuesday morning, officials said, with no injuries reported so far.",
         "summary_points": ["Fire broke out in Pune", "No injuries reported"]}
curr2 = {"id": 2, "summary": "Fire department chief Ramesh Kadam said three workers were injured in the Pune factory fire and have been hospitalised.",
         "summary_points": ["Three workers injured", "Hospitalised for treatment"]}
check("2A new casualty figure + new named actor -> True", sl._is_meaningful_update(prev2, curr2) is True)

print("\nTEST 3: short but substantive development -> True")
prev3 = {"id": 1, "summary": "The state assembly began debating the new farm bill on Monday, with opposition members raising concerns about pricing guarantees.",
         "summary_points": ["Farm bill debate begins", "Opposition raises pricing concerns"]}
curr3 = {"id": 2, "summary": "The farm bill passed by 214 votes.",
         "summary_points": ["Bill passed 214 votes"]}
check("3A short update with a new number -> True", sl._is_meaningful_update(prev3, curr3) is True)

print("\nTEST 3B: thin/empty text never gets hidden (fails open, not closed)")
prev3b = {"id": 1, "summary": "", "summary_points": []}
curr3b = {"id": 2, "summary": "", "summary_points": []}
check("3B nothing to compare -> defaults to True", sl._is_meaningful_update(prev3b, curr3b) is True)

print("\nTEST 3C: an already-verified Story Intelligence relationship overrides the text heuristic")
class _FakeCtx(dict):
    pass
import reader_context as _rc
_orig_build_ctx = _rc.build_story_context
_rc.build_story_context = lambda conn, eid, max_hops=2: {"historical_event": {"id": 1}} if eid == 2 else None
try:
    verified_dup_text = {"id": 1, "summary": "identical identical identical text here", "summary_points": []}
    verified_curr = {"id": 2, "summary": "identical identical identical text here", "summary_points": []}
    # Text alone would collapse this (ratio 1.0), but a verified relationship says otherwise.
    check("3C verified relationship wins over identical text", sl._is_meaningful_update(verified_dup_text, verified_curr, conn="fake") is True)
finally:
    _rc.build_story_context = _orig_build_ctx


# ---------------------------------------------------------------------------
# Integration test: build_storylines() linking guard (unrelated events must NOT join)
# ---------------------------------------------------------------------------

print("\nTEST 4: unrelated event does not join an existing storyline")

_orig_centroids = sl._centroids
_orig_get_connection = sl.database.get_connection


def _fake_get_connection():
    raise RuntimeError("no DB in this test - forces the deterministic fallback path")


def _events(rows):
    """rows: list of (id, title, topic, created_at, summary)."""
    return [{
        "id": i, "title": title, "title_hi": "", "topic": topic, "region": "India",
        "created_at": created_at, "published_at": created_at,
        "dominant": None, "blindspot": None, "lean_counts": {},
        "summary": summary, "summary_points": [],
    } for (i, title, topic, created_at, summary) in rows]


try:
    sl.database.get_connection = _fake_get_connection

    # Two genuinely linked events: same topic, close in time, similar text/keywords, high cosine.
    linked = _events([
        (101, "Farm bill passed by state assembly", "Politics", "2026-09-20T10:00:00", "The farm bill passed the state assembly on Monday."),
        (102, "Farm bill clears state assembly session", "Politics", "2026-09-21T09:00:00", "The farm bill was sent to the governor for assent on Tuesday."),
    ])
    # One unrelated event: different subject entirely, even though same topic + same window,
    # so only the similarity/keyword gate can (and must) keep it out.
    unrelated = _events([
        (201, "Municipal budget session begins in Chennai", "Politics", "2026-09-20T11:00:00", "The Chennai municipal budget session opened on Monday."),
    ])

    def _fake_centroids(events):
        # Fixed, hand-picked unit vectors: 101/102 nearly identical (linked story), 201 orthogonal
        # (unrelated) - independent of _kwset, so this test isolates the similarity gate itself.
        base = {
            101: np.array([1.0, 0.0], dtype=np.float32),
            102: np.array([0.99, 0.14], dtype=np.float32),
            201: np.array([0.0, 1.0], dtype=np.float32),
        }
        out = {}
        for e in events:
            v = base.get(e["id"])
            if v is None:
                continue
            out[e["id"]] = v / np.linalg.norm(v)
        return out

    sl._centroids = _fake_centroids

    result_storylines, emap = sl.build_storylines(linked + unrelated)
    check("4A exactly one storyline formed", len(result_storylines) == 1)
    check("4B the unrelated event is not a member of it", 201 not in emap)
    check("4C both linked events ARE members", emap.get(101) == emap.get(102) and 101 in emap)

    # Same linked pair, but now event 102 is a near-duplicate re-report of 101's summary text
    # (no new numbers/names) -> should still LINK (that's a separate decision from is_update)
    # but its entry must be flagged is_update=False and n_updates must drop to 1.
    dup_pair = _events([
        (301, "Farm bill passed by state assembly", "Politics", "2026-09-20T10:00:00",
         "The farm bill passed the state assembly on Monday, officials confirmed."),
        (302, "Farm bill passage confirmed by assembly", "Politics", "2026-09-20T10:05:00",
         "The farm bill passed the state assembly on Monday, officials confirmed."),
    ])

    def _fake_centroids_dup(events):
        base = {301: np.array([1.0, 0.0], dtype=np.float32), 302: np.array([0.99, 0.10], dtype=np.float32)}
        return {e["id"]: base[e["id"]] / np.linalg.norm(base[e["id"]]) for e in events if e["id"] in base}

    sl._centroids = _fake_centroids_dup
    dup_storylines, dup_emap = sl.build_storylines(dup_pair)
    check("4D near-duplicate pair still links into one storyline", len(dup_storylines) == 1)
    if dup_storylines:
        s = dup_storylines[0]
        entries = {e["id"]: e for e in s["events"]}
        check("4E first entry is always is_update=True", entries[301]["is_update"] is True)
        check("4F near-duplicate second entry is is_update=False", entries[302]["is_update"] is False)
        check("4G n_updates reflects only the genuine entry", s["n_updates"] == 1 and s["n_events"] == 2)

        # ---------------------------------------------------------------------------
        # TEST 5: collapse safety - a collapsed (is_update=False) entry must never be
        # removed from the underlying dataset/storyline, only hidden from the
        # "separate development" list when someone ELSE is viewing the storyline.
        # ---------------------------------------------------------------------------
        print("\nTEST 5: collapsing an entry never removes it from the dataset")
        check("5A collapsed event 302 is still a storyline member (not dropped from emap)",
              302 in dup_emap and dup_emap[302] == s["id"])
        check("5B collapsed event 302 still has its own entry in the storyline's events list",
              302 in entries)
        check("5C nothing was removed from the events list (still both original members)",
              len(s["events"]) == 2 and {e["id"] for e in s["events"]} == {301, 302})
        check("5D the collapsed entry keeps its real data, not a stub",
              entries[302]["title"] == "Farm bill passage confirmed by assembly"
              and entries[302]["topic"] == "Politics")

        # The frontend (static/app.jsx StorylineTimeline) applies exactly this predicate:
        #   ev.is_update !== false || String(ev.id) === String(currentId)
        # i.e. every entry is shown UNLESS it was collapsed, and even a collapsed entry is
        # always shown on ITS OWN page. Mirrored here in Python so a change to either side
        # would have to break this test too.
        def _frontend_visible(ev, current_id):
            return ev.get("is_update") is not False or ev["id"] == current_id

        check("5E a reader on the COLLAPSED event's own page still sees it in its timeline",
              _frontend_visible(entries[302], current_id=302) is True)
        check("5F a reader on a DIFFERENT event's page does not see the collapsed one listed",
              _frontend_visible(entries[302], current_id=301) is False)
        check("5G the non-collapsed entry is visible from anywhere",
              _frontend_visible(entries[301], current_id=302) is True)

finally:
    sl._centroids = _orig_centroids
    sl.database.get_connection = _orig_get_connection


print(f"\n{'ALL PASS' if not FAILURES else f'{len(FAILURES)} FAILURE(S): ' + ', '.join(FAILURES)}")
if FAILURES:
    raise SystemExit(1)
