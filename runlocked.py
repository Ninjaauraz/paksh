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


def acquire(label: str) -> bool:
    """Try to take the lock for `label` (identified as OUR pid). Returns True if
    acquired (caller now owns it and must call release()), False if another live
    job already holds it - caller should defer/skip, never proceed. Reclaims a
    stale lock (dead PID) automatically, same as the CLI path below."""
    if LOCK.exists():
        held = _read_lock()
        if held and _pid_alive(held[1]):
            print(f"[{_stamp()}] runlocked: SKIPPED '{label}' - '{held[0]}' still "
                  f"running (pid {held[1]}, since {held[2]}). "
                  f"Refusing to write paksh.db concurrently.")
            return False
        print(f"[{_stamp()}] runlocked: reclaiming stale lock "
              f"(previous holder {held[1] if held else '?'} not alive).")

    LOCK.write_text(f"{label}\n{os.getpid()}\n{_stamp()}\n", encoding="utf-8")
    print(f"[{_stamp()}] runlocked: acquired lock for '{label}' (pid {os.getpid()}).")
    return True


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
