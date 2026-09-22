"""
gdelt_gate.py - Phase 21C: one cross-process pacing gate for every GDELT request.

WHY THIS EXISTS (not just a bigger SLEEP, not .pipeline.lock)
---------------------------------------------------------------
Phase 21B's clean, isolated canary (single process, no overlap, production's own
6s spacing + 8/16/32s backoff) still got 429'd on 9 of 10 requests. That rules out
"just increase one process's internal delay" as sufficient, and confirms the gap
Phase 21A already flagged: nothing stops two invocations of the GDELT client - two
processes, or the same process an hour apart - from acting as if they own the whole
quota. `.pipeline.lock` (runlocked.py) cannot be reused for this: it is mutual
exclusion for whoever is writing paksh.db, held for a whole ~30 min cycle, and two
GDELT calls that never overlap in time sail straight through it untouched - which is
exactly the case that broke the canary. This module answers a different, narrower
question: "in real wall-clock time, when did any Paksh process last talk to GDELT?" -
and enforces a minimum gap since then, for every caller, without anyone needing to
remember to ask.

MECHANISM
---------
Two small files outside the git repo, under %LOCALAPPDATA%\\Paksh\\ (overridable via
PAKSH_STATE_DIR, e.g. for tests):

  gdelt_gate.lock  - 1 byte, sole purpose is Windows-safe cross-process locking via
                     the standard-library `msvcrt` module (no new dependency).
  gdelt_gate.json  - {"last_request_utc": "<ISO8601>"}, the actual reservation.

wait_for_slot() does the following, with steps 2-5 inside the lock and the HTTP
request itself always made by the caller AFTER this returns (never inside the lock -
a slow GDELT response must never block any other process):

  1. acquire the lock file (bounded retry loop; never blocks forever)
  2. read gdelt_gate.json - missing, corrupt, or a timestamp implausibly in the
     future (clock moved backwards) is treated as "no prior request", logged once,
     and the file is rewritten clean rather than trusted
  3. compute earliest_allowed = last_request_utc + MIN_INTERVAL_SECONDS
  4. sleep the remainder, if any, WHILE HOLDING THE LOCK (so a second process can't
     reserve an earlier slot while we wait - this is what makes spacing exact
     instead of racy)
  5. reserve: persist "last_request_utc = now" (atomic replace)
  6. release the lock
  7. return the seconds actually waited, for logging

Any failure anywhere in this (can't create the state dir, can't acquire the lock in
time, disk error) is caught and treated as "proceed without pacing this once" - a
gate malfunction must never become a new way to hang ingestion permanently.

CONFIGURATION
--------------
GDELT_MIN_INTERVAL_SECONDS (env var), default 15. This is a deliberately
conservative PAKSH-SIDE safety setting chosen from Phase 21B's measured behavior,
NOT a claim about GDELT's real quota. Change it with an environment variable; no
code edit needed.
"""
import json
import os
import time
from datetime import datetime, timedelta, timezone

try:
    import msvcrt
except ImportError:                        # pragma: no cover - Windows-only project
    msvcrt = None

MIN_INTERVAL_SECONDS = float(os.environ.get("GDELT_MIN_INTERVAL_SECONDS", "15"))
_FUTURE_TOLERANCE_S = 5.0     # clock-skew slack before a future timestamp counts as corrupt
_LOCK_TIMEOUT_S = 90.0        # give up waiting for the lock rather than block forever
_LOCK_POLL_S = 0.1


def _state_dir():
    base = os.environ.get("PAKSH_STATE_DIR") or os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Paksh")
    os.makedirs(base, exist_ok=True)
    return base


def _lock_path():
    return os.path.join(_state_dir(), "gdelt_gate.lock")


def _state_path():
    return os.path.join(_state_dir(), "gdelt_gate.json")


def _now_utc():
    return datetime.now(timezone.utc)


def _acquire(fh):
    start = time.monotonic()
    while True:
        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            if time.monotonic() - start > _LOCK_TIMEOUT_S:
                raise TimeoutError(
                    f"gdelt_gate: could not acquire the lock within {_LOCK_TIMEOUT_S:.0f}s")
            time.sleep(_LOCK_POLL_S)


def _release(fh):
    fh.seek(0)
    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)


def _read_last_request():
    """A tz-aware UTC datetime, or None if there is no USABLE prior reservation -
    missing file, corrupt JSON, unparsable timestamp, or a timestamp implausibly in
    the future (the persisted clock moved backwards since it was written). Never
    raises: any of those conditions is logged and treated as 'start clean'."""
    path = _state_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        ts = datetime.fromisoformat(data["last_request_utc"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"  ! gdelt_gate: corrupt state file ({type(e).__name__}: {e}); resetting.")
        return None
    now = _now_utc()
    if ts > now + timedelta(seconds=_FUTURE_TOLERANCE_S):
        print(f"  ! gdelt_gate: persisted timestamp {ts.isoformat()} is in the future "
              f"(system clock moved backwards?); resetting.")
        return None
    return ts


def _write_last_request(ts):
    path = _state_path()
    tmp = path + f".tmp{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"last_request_utc": ts.isoformat()}, f)
    os.replace(tmp, path)          # atomic same-volume replace on Windows


def _wait_for_slot_impl(interval, pid, context):
    lock_path = _lock_path()
    if not os.path.exists(lock_path):
        with open(lock_path, "wb") as f:
            f.write(b"\0")         # msvcrt needs >=1 byte to lock
    with open(lock_path, "r+b") as fh:
        _acquire(fh)
        try:
            last = _read_last_request()
            now = _now_utc()
            waited = 0.0
            if last is not None:
                earliest = last + timedelta(seconds=interval)
                if now < earliest:
                    waited = (earliest - now).total_seconds()
                    time.sleep(waited)
                    now = _now_utc()
            _write_last_request(now)
        finally:
            _release(fh)
    if waited > 0.05:
        tag = f" query={context!r}" if context else ""
        print(f"    GDELT gate: pid={pid} wait={waited:.1f}s reserved_at={now.isoformat()}{tag}")
    return waited


def wait_for_slot(min_interval=None, context=None):
    """Block, if needed, until this process may send the next GDELT request, then
    reserve that slot. Call this immediately before EVERY GDELT HTTP attempt (the
    first try and every retry) and never hold anything from this call across the
    request itself. Returns the seconds actually waited (0.0 if none, including if
    the gate itself failed - a gate malfunction must never block ingestion)."""
    interval = MIN_INTERVAL_SECONDS if min_interval is None else min_interval
    pid = os.getpid()
    if msvcrt is None:
        return 0.0
    try:
        return _wait_for_slot_impl(interval, pid, context)
    except Exception as e:                 # the gate must never be a new point of failure
        print(f"  ! gdelt_gate: unavailable ({type(e).__name__}: {e}); "
              f"proceeding without pacing this once.")
        return 0.0
