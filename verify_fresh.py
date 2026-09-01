#!/usr/bin/env python3
"""
verify_fresh.py - ground-truth health gate for the scheduled pipeline.

Exit 0 is not proof a run worked - the outage proved that (a task that did
nothing still "succeeded"). This checks the DATA, not the exit code:

  snapshot : record how many articles exist right now (call BEFORE the run)
  check    : after the run, FAIL LOUDLY if EITHER:
             (a) the run ingested nothing AND the catalogue's newest event is
                 stale (older than --max-age-hours), or
             (b) local git history is ahead of origin/main - i.e. a commit
                 exists locally that never reached GitHub, so Vercel never
                 saw it. This catches the case a pure DB check misses: local
                 ingestion succeeded (articles grew, newest event is fresh)
                 but safe_autopush.py's push itself failed (network/DNS
                 outage - see autopush_log.txt's "PUSH FAILED ... LOCAL ONLY
                 (not deployed)" entries), which otherwise reports FRESH-OK
                 and clears the alert while production stays on the last
                 successfully deployed snapshot. A git-unreachable network is
                 itself inconclusive-but-suspicious and is also treated as a
                 failure here, since it's the same condition that causes a
                 push to fail.

"Fail loudly" = non-zero exit (Task Scheduler shows RED) + a clear log line +
PAKSH_STALE_ALERT.txt dropped on the Desktop (OneDrive mirrors it to your
phone) + a best-effort balloon toast. A healthy check clears any stale alert.

Read-only on paksh.db (SELECT + a tiny json sidecar) and on git (fetch +
rev-list only - never pushes, commits, or alters any ref). Never touches events.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
BASELINE = ROOT / ".pipeline_baseline.json"
ALERT_NAME = "PAKSH_STALE_ALERT.txt"


def _articles():
    from database import get_connection, init_db
    init_db()
    c = get_connection()
    n = c.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    c.close()
    return n


def _newest_event_age_hours():
    from database import get_connection, init_db
    init_db()
    c = get_connection()
    v = c.execute("SELECT MAX(created_at) FROM events").fetchone()[0]
    c.close()
    if not v:
        return None
    t = datetime.fromisoformat(v.replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).total_seconds() / 3600.0


def _unpushed_commits():
    """None if we can't tell (git/network unavailable - treated as suspicious by the
    caller, since that's the same condition that fails a push); otherwise the count
    of local HEAD commits not yet on origin/main. 0 means fully in sync."""
    try:
        fetch = subprocess.run(["git", "fetch", "origin", "main"], cwd=str(ROOT),
                                capture_output=True, text=True, timeout=30)
        if fetch.returncode != 0:
            return None
        out = subprocess.run(["git", "rev-list", "--count", "origin/main..HEAD"],
                              cwd=str(ROOT), capture_output=True, text=True, timeout=15)
        if out.returncode != 0:
            return None
        return int(out.stdout.strip())
    except Exception:
        return None


def _desktop_dirs():
    home = os.environ.get("USERPROFILE", str(Path.home()))
    cands = [Path(home) / "OneDrive" / "Desktop", Path(home) / "Desktop"]
    return [p for p in cands if p.is_dir()] or [ROOT]


def _stamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _write_alert(msg):
    body = (f"[{_stamp()}] PAKSH PIPELINE ALERT\n\n{msg}\n\n"
            f"See refresh_log.txt in C:\\paksh_project\\paksh.\n")
    for d in _desktop_dirs():
        try:
            (d / ALERT_NAME).write_text(body, encoding="utf-8")
        except OSError:
            pass
    # best-effort balloon; never affects exit code
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command",
            "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
            "$n=New-Object System.Windows.Forms.NotifyIcon;"
            "$n.Icon=[System.Drawing.SystemIcons]::Warning;$n.Visible=$true;"
            "$n.ShowBalloonTip(10000,'Paksh pipeline',"
            "'Ingest stalled - catalogue is stale. See Desktop alert.',"
            "[System.Windows.Forms.ToolTipIcon]::Warning);Start-Sleep 12;$n.Dispose()"],
            timeout=25, capture_output=True)
    except Exception:
        pass


def _clear_alert():
    for d in _desktop_dirs():
        f = d / ALERT_NAME
        if f.exists():
            try:
                f.unlink()
            except OSError:
                pass


def cmd_snapshot():
    n = _articles()
    BASELINE.write_text(json.dumps({"articles": n, "at": _stamp()}), encoding="utf-8")
    print(f"[verify] snapshot: {n} articles at {_stamp()}")
    return 0


def cmd_deploy_check():
    """Deploy-sync-only gate, for callers like reframe_scheduled.bat that don't ingest
    (so the article-growth/staleness half of cmd_check doesn't apply to them - see its
    docstring) but still commit+push and need the same "did it actually reach origin"
    ground truth. Same fail-loud alerting as cmd_check; no article/event DB checks."""
    unpushed = _unpushed_commits()
    if unpushed is None or unpushed > 0:
        reason = ("could not reach origin (git fetch failed - likely the same network "
                   "outage that would also fail a push)" if unpushed is None else
                   f"{unpushed} local commit(s) never reached origin/main")
        msg = f"This run's commit never reached production: {reason}."
        print(f"[verify] DEPLOY-FAIL: {msg}")
        _write_alert(msg)
        return 1
    print("[verify] DEPLOY-OK: local HEAD is in sync with origin/main.")
    _clear_alert()
    return 0


def cmd_check(max_age):
    cur = _articles()
    base = None
    if BASELINE.exists():
        try:
            base = json.loads(BASELINE.read_text(encoding="utf-8")).get("articles")
        except Exception:
            base = None
    grew = (base is not None) and (cur > base)
    age = _newest_event_age_hours()
    stale = (age is None) or (age > max_age)
    delta = "unknown" if base is None else f"+{cur - base}"
    agestr = "unknown" if age is None else f"{age:.1f}h"

    if (not grew) and stale:                      # the user's exact condition
        msg = (f"Ingest did NOT grow the catalogue (articles {base} -> {cur}, {delta}) "
               f"AND newest event is {agestr} old (> {max_age:.0f}h). Pipeline likely broken.")
        print(f"[verify] STALE-FAIL: {msg}")
        _write_alert(msg)
        return 1

    unpushed = _unpushed_commits()
    if unpushed is None or unpushed > 0:
        reason = ("could not reach origin (git fetch failed - likely the same network "
                   "outage that would also fail a push)" if unpushed is None else
                   f"{unpushed} local commit(s) never reached origin/main")
        msg = (f"Local data looks fresh (articles {base} -> {cur}, {delta}; newest event "
               f"{agestr} old) but it never reached production: {reason}. "
               f"Vercel is still serving the last commit that DID push.")
        print(f"[verify] DEPLOY-FAIL: {msg}")
        _write_alert(msg)
        return 1

    print(f"[verify] FRESH-OK: articles {base} -> {cur} ({delta}); "
          f"newest event {agestr} old (grew={grew}, stale={stale}); in sync with origin/main.")
    _clear_alert()
    return 0


def main():
    ap = argparse.ArgumentParser(description="Ground-truth freshness gate for the Paksh pipeline.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("snapshot")
    ck = sub.add_parser("check")
    ck.add_argument("--max-age-hours", type=float, default=36.0)
    sub.add_parser("deploy-check")
    args = ap.parse_args()
    if args.cmd == "snapshot":
        sys.exit(cmd_snapshot())
    elif args.cmd == "deploy-check":
        sys.exit(cmd_deploy_check())
    else:
        sys.exit(cmd_check(args.max_age_hours))


if __name__ == "__main__":
    main()
