"""
runlocked.py - mutual exclusion for pipeline jobs that WRITE paksh.db.

The nightly refresh (05:30) and the reframe batch (07:30) must never write the
SQLite file at the same time. Time-spacing alone is not a guarantee - a slow
GDELT or Ollama night can overrun past 07:30. This wrapper enforces a hard
interlock with a PID lock file (.pipeline.lock):

  * before running, a job tries to acquire the lock;
  * if another job already holds it AND that PID is still alive, this exits
    IMMEDIATELY (code 0) with a logged notice - it does NOT run concurrently;
  * a stale lock (holder crashed) is detected via PID liveness and reclaimed;
  * the lock is always released when the job finishes (try/finally).

Usage (as a CLI wrapper around a subprocess, from a .bat):
    py runlocked.py <label> -- <command> [args...]
Example:
    py runlocked.py refresh -- py refresh.py --gdelt
    py runlocked.py reframe -- py reframe.py --apply --top-tier --limit 300

Usage (as a library, Phase 25B-A - live.py holds the SAME lock for the
duration of one in-process cycle rather than shelling out to this CLI):
    import runlocked
    if runlocked.acquire("live"):
        try:
            ...do the cycle's DB-writing work...
        finally:
            runlocked.release()
    else:
        ...defer this cycle, another job holds the lock...

acquire()/release() are exactly the same acquire/release main() uses below -
this is a pure extraction, not a second lock implementation. The CLI's
messages/exit codes are unchanged.
"""
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
LOCK = ROOT / ".pipeline.lock"


def _stamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _pid_alive(pid: int) -> bool:
    """True if a process with this PID is currently running (Windows tasklist).
    On any uncertainty we return True, so we never steal a lock we're unsure about
    (better a skipped run than two concurrent writers)."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, timeout=15).stdout
        return str(pid) in out
    except Exception:
        return True


def _read_lock():
    try:
        parts = LOCK.read_text(encoding="utf-8").splitlines()
        return parts[0], int(parts[1]), parts[2]        # label, pid, started
    except Exception:
        return None


def _try_create(label: str) -> bool:
    """Atomically create the lock file (O_CREAT|O_EXCL): exactly one contender can
    succeed, closing the check-then-write race of the previous implementation."""
    try:
        fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    try:
        os.write(fd, f"{label}\n{os.getpid()}\n{_stamp()}\n".encode("utf-8"))
    finally:
        os.close(fd)
    return True


def _reclaim_stale(label: str, stale_pid: int) -> bool:
    """Replace a provably stale lock. Only the holder of the exclusive .reclaim guard
    may do it; it re-reads the lock under the guard and proceeds only if it is still
    the SAME dead holder. Then it removes it and does the normal exclusive create, so
    even a non-guard contender grabbing the free slot first just means we lose."""
    guard = LOCK.with_name(LOCK.name + ".reclaim")
    try:
        gfd = os.open(str(guard), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    try:
        again = _read_lock()
        if again is None or again[1] != stale_pid or _pid_alive(again[1]):
            return False
        try:
            os.unlink(str(LOCK))
        except FileNotFoundError:
            pass
        return _try_create(label)
    finally:
        os.close(gfd)
        try:
            os.unlink(str(guard))
        except OSError:
            pass


def acquire(label: str) -> bool:
    """Try to take the lock for `label` (identified as OUR pid). Returns True if
    acquired (caller now owns it and must call release()), False if another live
    job already holds it - caller should defer/skip, never proceed.

    Atomic: creation uses O_EXCL, so two simultaneous callers can never both win.
    A stale lock (holder PID dead) is reclaimed only by the holder of an exclusive
    .reclaim guard file, which re-verifies the same dead holder before replacing it;
    the loser of any race simply reports 'held'. An unreadable or half-written lock
    file is treated as HELD (never reclaimed on uncertainty)."""
    for _attempt in range(2):
        if _try_create(label):
            print(f"[{_stamp()}] runlocked: acquired lock for '{label}' (pid {os.getpid()}).")
            return True
        held = _read_lock()
        if held is None or _pid_alive(held[1]):
            who = (f"'{held[0]}' still running (pid {held[1]}, since {held[2]})"
                   if held else "an unreadable lock file is present")
            print(f"[{_stamp()}] runlocked: SKIPPED '{label}' - {who}. "
                  f"Refusing to write paksh.db concurrently.")
            return False
        # stale: holder is provably dead. Reclaim under an exclusive guard file so two
        # contenders can never both delete-and-recreate (the ABA race of a bare unlink).
        if _reclaim_stale(label, held[1]):
            print(f"[{_stamp()}] runlocked: reclaimed stale lock (previous holder {held[1]} not alive) "
                  f"and acquired it for '{label}' (pid {os.getpid()}).")
            return True
    print(f"[{_stamp()}] runlocked: SKIPPED '{label}' - lock contended; will retry later.")
    return False


def release():
    """Release the lock, but only if it's still ours (matches main()'s own
    try/finally safety - never remove a lock some other pid has since taken)."""
    held = _read_lock()
    if held and held[1] == os.getpid():
        try:
            LOCK.unlink()
        except OSError:
            pass


def main():
    if "--" not in sys.argv:
        print("usage: py runlocked.py <label> -- <command...>")
        sys.exit(2)
    sep = sys.argv.index("--")
    label = " ".join(sys.argv[1:sep]) or "job"
    cmd = sys.argv[sep + 1:]
    if not cmd:
        print("runlocked: no command given")
        sys.exit(2)

    if not acquire(label):
        sys.exit(0)
    print(f"  Running: {' '.join(cmd)}")

    # --- run, always release ---
    try:
        rc = subprocess.run(cmd).returncode
        print(f"[{_stamp()}] runlocked: '{label}' finished (exit {rc}).")
        sys.exit(rc)
    finally:
        release()


if __name__ == "__main__":
    main()
