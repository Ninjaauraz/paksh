"""
check_scheduled_health.py - Phase 25B-C: missed-run and failed-run detection
for the three Windows Task Scheduler jobs (failure classes A and B from the
Phase 25A audit - "task never started" and "task ran and failed", which are
NOT the same thing and must be told apart).

verify_fresh.py already alerts well on two OTHER classes: C (push/deploy
never reached origin - deploy-check) and D (freshness - check). Neither of
those can detect a task that never ran at all, because both are code INSIDE
a scheduled job's own chain - if the chain never starts (machine asleep,
Task Scheduler didn't fire), nothing inside it ever runs to notice. This
script is the one thing in the pipeline whose job is to notice from the
OUTSIDE, using Task Scheduler's own recorded LastRunTime/LastTaskResult as
ground truth (not a separately-invented timer) for all three Paksh tasks.

Usage:
    py check_scheduled_health.py                # check, alert/clear, exit 0/1
    py check_scheduled_health.py --grace-hours 2 # override the missed-run grace window

Wired in (unconditionally, regardless of the rest of the chain's success -
same pattern reframe_scheduled.bat already uses for verify_fresh.py deploy-
check) at the end of reframe_scheduled.bat, the last of the three daily
jobs (07:30), so one run each day checks whether all three actually
happened. This does NOT invent a new always-on timer/daemon - it rides the
existing schedule, per the phase's own instruction not to add a fragile
separate SLA clock.

Alerts via verify_fresh.py's existing Desktop-alert + best-effort balloon
mechanism (own alert file, PAKSH_SCHEDULE_ALERT.txt, so it never collides
with or overwrites verify_fresh.py's own PAKSH_STALE_ALERT.txt - both can be
visible at once if both conditions are true). Auto-clears when all three
tasks are healthy again, same recovery pattern as verify_fresh.py.

Natural spam bound: this only runs once a day (chained off the 07:30 job),
so there is no separate cooldown/dedupe state to maintain - the schedule
itself is the rate limit.
"""
import argparse
import subprocess
import sys
from datetime import datetime, timedelta

import verify_fresh

ALERT_NAME = "PAKSH_SCHEDULE_ALERT.txt"

# name -> expected time-of-day (hour, minute), matching the real Task
# Scheduler configuration (Phase 25A confirmed these via Get-ScheduledTask).
TASKS = {
    "Paksh  refresh": (0, 30),
    "Paksh nightly refresh": (5, 30),
    "Paksh reframe": (7, 30),
}


def _task_info():
    """Returns {name: {"last_run": datetime|None, "last_result": int|None}} via
    PowerShell, the same read-only Get-ScheduledTaskInfo already used (read-
    only) during the Phase 25A audit. Returns {} on any failure - a checker
    that can't reach Task Scheduler must not crash the calling .bat chain."""
    try:
        names = ",".join(f"'{n}'" for n in TASKS)
        ps = (
            f"Get-ScheduledTask | Where-Object {{ @({names}) -contains $_.TaskName }} | "
            "Get-ScheduledTaskInfo | ForEach-Object { "
            "\"$($_.TaskName)|$($_.LastRunTime.ToString('o'))|$($_.LastTaskResult)\" }"
        )
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                              capture_output=True, text=True, timeout=30)
        info = {}
        for line in (out.stdout or "").splitlines():
            line = line.strip()
            if not line or "|" not in line:
                continue
            parts = line.split("|")
            if len(parts) != 3:
                continue
            name, last_run_s, result_s = parts
            try:
                last_run = datetime.fromisoformat(last_run_s) if last_run_s else None
            except ValueError:
                last_run = None
            try:
                result = int(result_s)
            except ValueError:
                result = None
            info[name] = {"last_run": last_run, "last_result": result}
        return info
    except Exception:
        return {}


def evaluate(now: datetime, info: dict, grace_hours: float):
    """Pure function (no I/O) so this is unit-testable without mocking
    subprocess/PowerShell. Returns a list of problem strings, empty if
    everything looks healthy."""
    problems = []
    for name, (hh, mm) in TASKS.items():
        scheduled_today = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        due_by = scheduled_today + timedelta(hours=grace_hours)
        entry = info.get(name)
        if entry is None:
            problems.append(f"'{name}': not found in Task Scheduler at all (was it removed?).")
            continue
        last_run = entry["last_run"]
        if now < due_by:
            continue   # not due yet today - nothing to judge
        if last_run is None or last_run.date() < now.date():
            problems.append(
                f"'{name}': MISSED - scheduled for {hh:02d}:{mm:02d}, grace window ended "
                f"{due_by.strftime('%H:%M')}, but it has not run today "
                f"(last run: {last_run.strftime('%Y-%m-%d %H:%M') if last_run else 'never recorded'})."
            )
        elif entry["last_result"] not in (0, None):
            problems.append(
                f"'{name}': RAN BUT FAILED today at {last_run.strftime('%H:%M')} "
                f"(Task Scheduler result code {entry['last_result']}). Check its log file."
            )
    return problems


def main():
    ap = argparse.ArgumentParser(description="Detect a Paksh scheduled task that never ran, or ran and failed.")
    ap.add_argument("--grace-hours", type=float, default=1.5,
                     help="how long past its scheduled time a task may be before it's flagged missed (default 1.5h)")
    args = ap.parse_args()

    now = datetime.now()
    info = _task_info()
    if not info:
        print("[schedule] could not read Task Scheduler state (PowerShell/Get-ScheduledTask "
              "unavailable) - skipping this check, not treating it as a failure.")
        sys.exit(0)

    problems = evaluate(now, info, args.grace_hours)
    if problems:
        msg = "One or more scheduled Paksh jobs did not run on time or failed:\n\n" + "\n".join(
            f"  - {p}" for p in problems)
        print(f"[schedule] SCHEDULE-FAIL:\n{msg}")
        verify_fresh._write_alert(
            msg, alert_name=ALERT_NAME, title="Paksh schedule",
            balloon_text="A scheduled Paksh job was missed or failed. See Desktop alert.")
        sys.exit(1)

    print("[schedule] SCHEDULE-OK: all three scheduled jobs ran on time today.")
    verify_fresh._clear_alert(alert_name=ALERT_NAME)
    sys.exit(0)


if __name__ == "__main__":
    main()
