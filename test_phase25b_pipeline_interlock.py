"""
test_phase25b_pipeline_interlock.py - Phase 25B-A: deterministic tests for the
shared .pipeline.lock interlock between live.py and the scheduled Task
Scheduler jobs (refresh_scheduled.bat/reframe_scheduled.bat, both wrapped in
runlocked.py).

Two layers are tested:
1. runlocked.acquire()/release() - the actual lock decision logic, exercised
   directly against the real (but currently-free) .pipeline.lock path with
   _pid_alive mocked, so no real second process or timing race is needed.
2. live.cycle()'s control flow - that it acquires before doing any DB-writing
   work, defers (does nothing) when the lock is held, and always releases via
   try/finally regardless of how the cycle body exits. _run/_deploy and the
   lock itself are all mocked here so this never triggers a real pipeline run,
   a real git operation, or real lock-file contention with a live process.

Never touches paksh.db, never calls an LLM, never runs the real refresh.py.

Run:  py test_phase25b_pipeline_interlock.py
"""
import os

import live
import runlocked

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


print("TEST 1: runlocked.acquire() basic acquire/skip/reclaim (real lock path, mocked liveness)")
if runlocked.LOCK.exists():
    runlocked.LOCK.unlink()
ok = runlocked.acquire("t1")
check("1a: acquire succeeds when no lock exists", ok is True)
check("1b: lock file now exists", runlocked.LOCK.exists())

orig_alive = runlocked._pid_alive
runlocked._pid_alive = lambda pid: True
before = runlocked.LOCK.read_text(encoding="utf-8")
ok2 = runlocked.acquire("t2-should-skip")
after = runlocked.LOCK.read_text(encoding="utf-8")
check("1c: acquire returns False when a live pid holds it", ok2 is False)
check("1d: lock content is untouched by a skipped acquire", before == after)

runlocked._pid_alive = lambda pid: False
ok3 = runlocked.acquire("t3-reclaim")
check("1e: acquire reclaims a stale (dead-pid) lock -> True", ok3 is True)
runlocked._pid_alive = orig_alive
runlocked.release()
check("1f: lock file removed after release()", not runlocked.LOCK.exists())


print("\nTEST 2: live.cycle() acquires the lock before any DB-writing work, "
      "and never calls _run at all when the lock is held")
calls = []
orig_run, orig_deploy, orig_acquire, orig_release = live._run, live._deploy, runlocked.acquire, runlocked.release
live._run = lambda args: calls.append(("_run", tuple(args))) or 0
live._deploy = lambda: calls.append(("_deploy",))
runlocked.acquire = lambda label: (calls.append(("acquire", label)), False)[1]
runlocked.release = lambda: calls.append(("release",))

live.cycle(deploy=True, backfill_n=10)
check("2a: acquire was attempted", ("acquire", "live") in calls)
check("2b: no _run/_deploy call happened when the lock was held",
      not any(c[0] in ("_run", "_deploy") for c in calls))
check("2c: release() was NOT called when acquire itself returned False "
      "(we never held the lock, so there is nothing to release)",
      ("release",) not in calls)

print("\nTEST 3: live.cycle() runs the full sequence and releases when the lock is free "
      "and every step succeeds")
calls.clear()
runlocked.acquire = lambda label: (calls.append(("acquire", label)), True)[1]
live.cycle(deploy=True, backfill_n=10)
check("3a: refresh.py --gdelt was run", ("_run", ("refresh.py", "--gdelt")) in calls)
check("3b: backfill.py was run (backfill_n>0)",
      any(c[0] == "_run" and c[1][0] == "backfill.py" for c in calls))
check("3c: export_static.py was run after backfill", ("_run", ("export_static.py",)) in calls)
check("3d: _deploy() was called (deploy=True)", ("_deploy",) in calls)
check("3e: release() was called exactly once", calls.count(("release",)) == 1)
check("3f: release happens after the deploy call (correct ordering)",
      calls.index(("_deploy",)) < calls.index(("release",)))

print("\nTEST 4: a failed refresh.py still releases the lock (try/finally), "
      "and skips backfill/export/deploy for that cycle")
calls.clear()
run_results = {"refresh.py": 1}   # simulate refresh.py --gdelt failing (non-zero exit)
def fake_run(args):
    calls.append(("_run", tuple(args)))
    return run_results.get(args[0], 0)
live._run = fake_run
live.cycle(deploy=True, backfill_n=10)
check("4a: refresh.py was attempted", ("_run", ("refresh.py", "--gdelt")) in calls)
check("4b: backfill/export were NOT attempted after a refresh failure",
      not any(c[0] == "_run" and c[1][0] in ("backfill.py", "export_static.py") for c in calls))
check("4c: _deploy() was NOT called after a refresh failure", ("_deploy",) not in calls)
check("4d: release() was still called despite the failure (try/finally holds)",
      ("release",) in calls)

live._run, live._deploy, runlocked.acquire, runlocked.release = orig_run, orig_deploy, orig_acquire, orig_release
if runlocked.LOCK.exists():
    runlocked.LOCK.unlink()

print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
