"""
test_phase25b_live_resilience.py - Phase 25B-D: deterministic tests for
live.py's durable logging, log redaction, bounded log rotation, and crash
resilience (an ordinary exception inside one cycle must not kill the
always-on loop, but KeyboardInterrupt must still stop it cleanly).

Never runs a real cycle (refresh.py/backfill.py/export_static.py/_deploy are
all mocked, exactly like test_phase25b_pipeline_interlock.py), never touches
the real live_log.txt (LOG_PATH is monkeypatched to a temp file for every
test and restored afterward).

Run:  py test_phase25b_live_resilience.py
"""
import os
import sys
import tempfile

import live
import runlocked

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


print("TEST 1: _redact() scrubs a secret-like key/token pattern")
scrubbed = live._redact("request failed for url with api_key=AbCdEf123456ghijklMNOP and that's the whole message")
check("1a: the secret value itself is gone", "AbCdEf123456ghijklMNOP" not in scrubbed)
check("1b: a redaction marker is present", "<redacted>" in scrubbed)
check("1c: unrelated text around it survives", "request failed for url" in scrubbed and "whole message" in scrubbed)

print("\nTEST 2: _log() writes a timestamped line to the log file AND prints")
tmp_log = tempfile.mktemp(suffix=".txt")
orig_log_path = live.LOG_PATH
live.LOG_PATH = tmp_log
try:
    live._log("hello from a test")
    check("2a: log file was created", os.path.exists(tmp_log))
    content = open(tmp_log, encoding="utf-8").read()
    check("2b: log file contains our message", "hello from a test" in content)
    check("2c: log line is timestamped ([YYYY-MM-DD HH:MM:SS] prefix)",
          content.strip().startswith("[") and "]" in content)

    print("\nTEST 3: a secret-like message passed to _log() is redacted on disk")
    live._log("token=SuperSecretValue123456789 leaked in an error")
    content2 = open(tmp_log, encoding="utf-8").read()
    check("3: the raw secret never reaches the log file", "SuperSecretValue123456789" not in content2)

    print("\nTEST 4: bounded log - _rotate_if_large() truncates instead of growing forever")
    with open(tmp_log, "w", encoding="utf-8") as f:
        for i in range(5000):
            f.write(f"line {i}\n")
    orig_max = live.LOG_MAX_BYTES
    live.LOG_MAX_BYTES = 1000   # force rotation on a small file for a fast, deterministic test
    size_before = os.path.getsize(tmp_log)
    live._rotate_if_large()
    size_after = os.path.getsize(tmp_log)
    check("4a: file shrank after rotation", size_after < size_before)
    remaining = open(tmp_log, encoding="utf-8").read()
    check("4b: the most RECENT content survived rotation (not the oldest)", "line 4999" in remaining)
    check("4c: old content was dropped", "line 0\n" not in remaining)
    live.LOG_MAX_BYTES = orig_max
finally:
    live.LOG_PATH = orig_log_path
    try:
        os.remove(tmp_log)
    except OSError:
        pass

print("\nTEST 5: main() survives an ordinary exception inside cycle() and continues "
      "(does not propagate, does not crash the process)")
tmp_log2 = tempfile.mktemp(suffix=".txt")
live.LOG_PATH = tmp_log2
orig_cycle, orig_argv = live.cycle, sys.argv
try:
    def exploding_cycle(deploy, backfill_n):
        raise RuntimeError("simulated ordinary cycle failure - not a real bug")
    live.cycle = exploding_cycle
    sys.argv = ["live.py", "--once"]   # --once so main() returns after one iteration either way
    raised = False
    try:
        live.main()
    except Exception:
        raised = True
    check("5a: main() did NOT propagate the exception out", not raised)
    log_content = open(tmp_log2, encoding="utf-8").read()
    check("5b: the exception was logged with a traceback", "RuntimeError" in log_content
          and "simulated ordinary cycle failure" in log_content)
    check("5c: the log explicitly says the loop is continuing, not stopping",
          "logging and continuing" in log_content)
finally:
    live.cycle, sys.argv = orig_cycle, orig_argv
    live.LOG_PATH = orig_log_path
    try:
        os.remove(tmp_log2)
    except OSError:
        pass

print("\nTEST 6: KeyboardInterrupt still stops the loop cleanly (not swallowed by the "
      "new per-cycle Exception handler, since KeyboardInterrupt is a BaseException)")
tmp_log3 = tempfile.mktemp(suffix=".txt")
live.LOG_PATH = tmp_log3
call_count = {"n": 0}
try:
    def interrupting_cycle(deploy, backfill_n):
        call_count["n"] += 1
        raise KeyboardInterrupt()
    live.cycle = interrupting_cycle
    sys.argv = ["live.py"]   # no --once - if KeyboardInterrupt were swallowed, this would loop forever
    live.main()   # must return (via the outer except KeyboardInterrupt), not hang, not raise
    check("6a: main() returned normally after KeyboardInterrupt (did not hang, did not raise)", True)
    check("6b: cycle() was only invoked once - the loop actually stopped, "
          "it did not swallow KeyboardInterrupt and keep looping", call_count["n"] == 1)
finally:
    live.cycle, sys.argv = orig_cycle, orig_argv
    live.LOG_PATH = orig_log_path
    try:
        os.remove(tmp_log3)
    except OSError:
        pass

print("\nTEST 7: an exploding cycle does not leak the pipeline lock "
      "(cycle()'s own try/finally around runlocked already guarantees this - confirms "
      "the 25B-D wrapper doesn't change that)")
if runlocked.LOCK.exists():
    runlocked.LOCK.unlink()
tmp_log4 = tempfile.mktemp(suffix=".txt")
live.LOG_PATH = tmp_log4
try:
    def exploding_after_acquire(deploy, backfill_n):
        if not runlocked.acquire("live"):
            return
        try:
            raise RuntimeError("boom mid-cycle, after the lock was acquired")
        finally:
            runlocked.release()
    live.cycle = exploding_after_acquire
    sys.argv = ["live.py", "--once"]
    live.main()
    check("7: lock file does not exist after the exception (release() still ran)",
          not runlocked.LOCK.exists())
finally:
    live.cycle, sys.argv = orig_cycle, orig_argv
    live.LOG_PATH = orig_log_path
    if runlocked.LOCK.exists():
        runlocked.LOCK.unlink()
    try:
        os.remove(tmp_log4)
    except OSError:
        pass

print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
