"""
test_phase25b_schedule_alert.py - Phase 25B-C: deterministic tests for
check_scheduled_health.py's evaluate() (pure, no PowerShell/Task Scheduler
I/O) and a real end-to-end test of the alert write/clear mechanism it shares
with verify_fresh.py (against a dedicated TEST alert filename, never the
real PAKSH_STALE_ALERT.txt/PAKSH_SCHEDULE_ALERT.txt names, so this can never
mask or clobber a real, currently-active production alert).

Run:  py test_phase25b_schedule_alert.py
"""
from datetime import datetime, timedelta

import check_scheduled_health as csh
import verify_fresh

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


print("TEST 1: evaluate() - all three tasks ran on time today, all succeeded -> no problems")
now = datetime(2026, 9, 3, 9, 0, 0)   # 09:00, past all three scheduled times + grace
info = {
    "Paksh  refresh":         {"last_run": datetime(2026, 9, 3, 0, 30, 5), "last_result": 0},
    "Paksh nightly refresh":  {"last_run": datetime(2026, 9, 3, 5, 30, 2), "last_result": 0},
    "Paksh reframe":          {"last_run": datetime(2026, 9, 3, 7, 30, 1), "last_result": 0},
}
problems = csh.evaluate(now, info, grace_hours=1.5)
check("1: no problems when everything ran on time and succeeded", problems == [])

print("\nTEST 2: evaluate() - a task's last run was YESTERDAY (missed run, class A)")
info2 = dict(info)
info2["Paksh nightly refresh"] = {"last_run": datetime(2026, 9, 2, 5, 30, 0), "last_result": 0}
problems2 = csh.evaluate(now, info2, grace_hours=1.5)
check("2a: exactly one problem reported", len(problems2) == 1)
check("2b: the problem names the right task and says MISSED",
      "Paksh nightly refresh" in problems2[0] and "MISSED" in problems2[0])

print("\nTEST 3: evaluate() - a task ran today but with a non-zero result (failed run, class B)")
info3 = dict(info)
info3["Paksh  refresh"] = {"last_run": datetime(2026, 9, 3, 0, 30, 5), "last_result": 1}
problems3 = csh.evaluate(now, info3, grace_hours=1.5)
check("3a: exactly one problem reported", len(problems3) == 1)
check("3b: the problem names the right task and says RAN BUT FAILED, distinct from MISSED",
      "Paksh  refresh" in problems3[0] and "RAN BUT FAILED" in problems3[0]
      and "MISSED" not in problems3[0])

print("\nTEST 4: evaluate() - not yet due (before scheduled time + grace) -> no false alarm")
early_now = datetime(2026, 9, 3, 1, 0, 0)   # 01:00 - nightly refresh (05:30) and reframe (07:30) not due yet
info4 = {
    "Paksh  refresh":         {"last_run": datetime(2026, 9, 3, 0, 30, 5), "last_result": 0},
    "Paksh nightly refresh":  {"last_run": datetime(2026, 9, 2, 5, 30, 2), "last_result": 0},   # yesterday, but not due yet
    "Paksh reframe":          {"last_run": datetime(2026, 9, 2, 7, 30, 1), "last_result": 0},    # yesterday, but not due yet
}
problems4 = csh.evaluate(early_now, info4, grace_hours=1.5)
check("4: no false 'missed' alarm before a task's own grace window has elapsed", problems4 == [])

print("\nTEST 5: evaluate() - a task missing from Task Scheduler entirely")
info5 = dict(info)
del info5["Paksh reframe"]
problems5 = csh.evaluate(now, info5, grace_hours=1.5)
check("5: reports the task as not found", any("Paksh reframe" in p and "not found" in p for p in problems5))

print("\nTEST 6: real end-to-end alert write + clear, using a dedicated TEST alert name "
      "(never the real PAKSH_STALE_ALERT.txt / PAKSH_SCHEDULE_ALERT.txt)")
TEST_ALERT = "PAKSH_TEST_ALERT_DO_NOT_USE_IN_PRODUCTION.txt"
verify_fresh._clear_alert(alert_name=TEST_ALERT)   # start clean regardless of prior state
dirs_before = [d for d in verify_fresh._desktop_dirs()]
check("6a: at least one Desktop-equivalent directory is writable on this machine", len(dirs_before) > 0)
verify_fresh._write_alert("phase 25b-c test alert - safe to ignore/delete", alert_name=TEST_ALERT,
                           title="Paksh test", balloon_text="")
found = [d / TEST_ALERT for d in dirs_before if (d / TEST_ALERT).exists()]
check("6b: alert file was actually written to at least one Desktop-equivalent dir", len(found) > 0)
if found:
    content = found[0].read_text(encoding="utf-8")
    check("6c: alert file contains our message", "phase 25b-c test alert" in content)
verify_fresh._clear_alert(alert_name=TEST_ALERT)
still_there = [d / TEST_ALERT for d in dirs_before if (d / TEST_ALERT).exists()]
check("6d: alert file removed after clear", still_there == [])

print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
