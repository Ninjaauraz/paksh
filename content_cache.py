"""
content_cache.py - Paksh 2.7: in-process, single-flight TTL cache for the
homepage's expensive content reads (/api/events, /api/blindspots).

WHY THIS EXISTS
----------------
Phases 2.1-2.6 proved the Supabase-backed /api/events and /api/blindspots
routes are CORRECT but EXPENSIVE: each request pulls several MB through
PostgREST and is vulnerable to the `anon` role's 3-second statement_timeout
under concurrent load (see the 2.3-2.6 reports - narrowing the SELECT clause
helped but did not solve concurrency on its own). The remaining fix is
architectural, not another retry or payload trim: stop repeating the
expensive read on every request.

SCOPE - deliberately narrow
-----------------------------
Only get_events()/get_blindspots() are cached here - the two routes Phase 2.3
identified as both expensive AND on the homepage's critical path. topics/
sources/storylines were measured (Phase 2.1-2.5) at 0.2-0.5s with tiny
payloads (159B-207KB) - caching them would add complexity for no measurable
benefit, so they are deliberately left alone. events-archive is explicitly
NOT on the critical path (Phase 2.3 traced app.jsx's actual fetch pattern)
and is out of this phase's scope by instruction.

WHY IN-PROCESS, NOT REDIS
----------------------------
main.py runs as a single `uvicorn main:app` process - confirmed by every
process listing taken across Phases 2.3-2.6 (no --workers flag anywhere in
this repo, no Procfile, no multi-process config). A plain dict + a lock
living in this one process's memory is sufficient and correct for that
deployment shape; a distributed cache would solve a scaling problem this
deployment does not have, and the brief explicitly asks for the smallest
reliable change.

FRESHNESS POLICY
------------------
There is no existing signal to hook cache invalidation to: sync_to_supabase.py
(the only thing that ever changes Supabase's content) is a standalone,
manually-invoked script - confirmed by grepping live.py/refresh.py for any
reference to it (none exists). SQLite's own ingestion cycle (live.py,
CYCLE_MIN=12 by default, or --every 180 *minutes* per CLAUDE.md's documented
production invocation) is even less frequent than that from Supabase's point
of view, since someone has to run the sync separately. A blind TTL is
therefore the correct mechanism here, not a gap - not "the safest available
option" as a consolation, but genuinely appropriate given no better signal
exists. CACHE_TTL_SECONDS=180 (3 minutes) is comfortably shorter than any
plausible real content-refresh cadence, while still cutting Supabase read
*frequency* by 1-2 orders of magnitude under real homepage traffic.

SINGLE-FLIGHT
---------------
A per-key threading.Lock ensures that when N concurrent requests find an
expired/missing cache entry, exactly ONE of them runs the expensive builder;
the other N-1 block on the same lock and then read what the first one just
built - never N independent Supabase fetches. This is the direct fix for the
"20 concurrent requests = 20 concurrent Supabase reads" failure mode Phases
2.3-2.6 measured.

ATOMICITY / FAILURE BEHAVIOR
-------------------------------
A builder's result is only installed into the cache after it returns AND
passes a basic completeness check. If the builder raises (Supabase down,
timed out, etc.) or returns something that fails the completeness check, the
PREVIOUS valid entry (if any) is left untouched and is what gets served - a
failed refresh never overwrites a good cache with a bad one, and a caller
never sees a half-built result. If there is no previous entry to fall back
to, the original exception propagates unchanged (so main.py's existing
`except sb.SupabaseUnavailable: pass -> SQLite fallback` keeps working
exactly as before - this module does not change that contract).
"""
import threading
import time

CACHE_TTL_SECONDS = 180  # see "FRESHNESS POLICY" above


class _Entry:
    __slots__ = ("value", "built_at")

    def __init__(self, value, built_at):
        self.value = value
        self.built_at = built_at


_store: dict = {}
_locks: dict = {}
_locks_guard = threading.Lock()


def _lock_for(key):
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _locks[key] = lock
        return lock


def _default_is_complete(value):
    """A minimal, deliberately conservative sanity check: the two cached
    shapes are always {"events": [...]}, and an empty list is not a
    plausible result for either route on this corpus - reject it rather
    than cache/serve an accidentally-empty response."""
    return isinstance(value, dict) and isinstance(value.get("events"), list) and len(value["events"]) > 0


def get_or_build(key: str, builder, ttl: float = CACHE_TTL_SECONDS, is_complete=_default_is_complete,
                  unavailable_exc: type = RuntimeError):
    """Returns (value, status). status is one of:
      "hit"                       - fresh entry, no lock taken
      "hit-after-wait"            - another thread built it while we waited for the lock
      "built"                     - this call built it
      "hit-stale-refresh-failed"  - builder raised; served the previous valid entry instead
      "hit-stale-incomplete"      - builder returned incomplete data; served the previous entry

    Raises whatever the builder raised if there is no previous valid entry to
    fall back to (preserves main.py's existing SupabaseUnavailable contract).
    If the builder instead SUCCEEDS but returns incomplete data and there is
    no prior entry either, raises `unavailable_exc` (callers should pass the
    same exception type their caller already catches for "Supabase isn't
    giving us something usable" - e.g. sb.SupabaseUnavailable - so this rare
    edge case still falls through to the existing SQLite fallback instead of
    surfacing as an unhandled 500).
    """
    entry = _store.get(key)
    now = time.time()
    if entry is not None and (now - entry.built_at) < ttl:
        return entry.value, "hit"

    lock = _lock_for(key)
    with lock:
        # Re-check: another thread may have just finished building while we
        # were waiting for the lock - this is the single-flight guarantee.
        entry = _store.get(key)
        now = time.time()
        if entry is not None and (now - entry.built_at) < ttl:
            return entry.value, "hit-after-wait"

        try:
            value = builder()
        except Exception:
            if entry is not None:
                return entry.value, "hit-stale-refresh-failed"
            raise

        if not is_complete(value):
            if entry is not None:
                return entry.value, "hit-stale-incomplete"
            raise unavailable_exc(f"content_cache: build for {key!r} returned incomplete data "
                                   f"and no prior cache exists to fall back to")

        _store[key] = _Entry(value, now)
        return value, "built"


def invalidate(key: str = None):
    """Manual invalidation hook - not wired to anything automatic (see the
    module docstring's FRESHNESS POLICY: no ingestion signal exists to hook
    into without inventing one). Exists for tests and for a future phase if
    an explicit signal is ever added."""
    if key is None:
        _store.clear()
    else:
        _store.pop(key, None)


def warm(key: str, builder, is_complete=_default_is_complete):
    """Best-effort, non-blocking startup warm. Never raises - a failed warm
    just means the first real request populates the cache lazily instead,
    via the normal single-flight path in get_or_build()."""
    def _run():
        try:
            get_or_build(key, builder, is_complete=is_complete)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True, name=f"content_cache-warm-{key}").start()


def debug_state():
    """Read-only introspection for tests - never used by request handlers."""
    now = time.time()
    return {
        k: {"age_s": round(now - v.built_at, 2), "n_events": len(v.value.get("events", []))}
        for k, v in _store.items()
    }
