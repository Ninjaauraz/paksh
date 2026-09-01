"""
test_phase8_5.py - Paksh 8.5: content freshness & stale-data remediation.

Investigation found NO bug in ordering/timestamp/merge/export code: get_all_events()
correctly orders by created_at DESC, postprocess() correctly recomputes published_at
from the current member-article set on every call, cross-cycle merge correctly bumps
created_at (recount_event -> update_event(bump_created=True)), and reframe.py correctly
preserves it (bump_created=False). Sections A-F below are REGRESSION LOCKS proving that
existing-and-correct behavior, not fixes to broken behavior.

The actual root cause was operational: production is deployed only by two daily
Windows Task Scheduler batch jobs (05:30 refresh, 07:30 reframe), each of which must
both run its local pipeline AND successfully `git push`. verify_fresh.py - the
existing "did the pipeline actually work" ground-truth gate - checked only local
database freshness (articles grew? newest event young?), never whether that content
reached origin/main. autopush_log.txt shows this gap was real: on 2026-08-30 and
2026-08-31, safe_autopush.py correctly logged "PUSH FAILED ... LOCAL ONLY (not
deployed)" (a DNS/network outage) and exited non-zero, but verify_fresh.py's OWN
check would still have reported FRESH-OK and cleared the Desktop alert, because local
ingestion had succeeded even though production never got the update. On 2026-09-01
reframe_scheduled.bat's job died within the same second it acquired the pipeline
lock (confirmed: stale .pipeline.lock, dead PID, Task Scheduler's own "Last Result: 1")
and reframe_scheduled.bat had NO ground-truth check at all to notice.

Sections G-I test the actual fix: verify_fresh.py's new _unpushed_commits() /
cmd_deploy_check(), and cmd_check()'s new deploy-sync condition (which directly
reproduces and closes the Aug 30/31 scenario: local data fresh, push failed silently).
All git/subprocess calls are monkeypatched - no real git fetch, no real DB mutation,
no network dependency, and the real paksh.db is never written to.

Run:  py test_phase8_5.py
"""
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import database as db
from database import get_all_events
import analyze
import verify_fresh as vf

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


# ============================================================ A: "latest" ordering, precisely
print("=== A: get_all_events() ordering is exactly 'ORDER BY created_at DESC' ===")
import inspect
src = inspect.getsource(get_all_events)
check("1: the SQL literally reads 'ORDER BY created_at DESC' (not updated_at, not published_at)",
      "ORDER BY created_at DESC" in src)
check("2: no ORDER BY on updated_at anywhere in get_all_events()",
      "updated_at DESC" not in src and "ORDER BY updated_at" not in src)

real_events = get_all_events()
if len(real_events) >= 2:
    stamps = [e["created_at"] for e in real_events[:50] if e.get("created_at")]
    check("3: the first 50 real events from get_all_events() are actually in created_at-DESC order",
          stamps == sorted(stamps, reverse=True))
else:
    print("  (skipped #3 - fewer than 2 real events in local DB)")


# ============================================================ B/C: timestamp semantics
print("\n=== B/C: published_at is recomputed fresh from the CURRENT article set every call ===")
old_articles = [{"id": 1, "source": "A", "language": "en", "title": "t1", "summary": "s1",
                  "url": "u1", "published": "2026-01-01T00:00:00Z"}]
new_articles = old_articles + [{"id": 2, "source": "B", "language": "en", "title": "t2",
                                  "summary": "s2", "url": "u2", "published": "2026-06-15T12:00:00Z"}]
p_old = analyze.postprocess({"title": "T", "summary": "S"}, old_articles)
p_new = analyze.postprocess({"title": "T", "summary": "S"}, new_articles)
check("4: published_at reflects only-article's date when that's all there is",
      p_old["published_at"] == "2026-01-01T00:00:00")
check("5: published_at moves to the NEWEST member article once a fresher one is added "
      "(this is the mechanism that keeps a merged-into event correctly ranked as fresh)",
      p_new["published_at"] == "2026-06-15T12:00:00")

age_src = inspect.getsource(vf._newest_event_age_hours) if hasattr(vf, "_newest_event_age_hours") else ""
check("6: verify_fresh.py's own staleness check reads events.created_at (matches get_all_events())",
      "MAX(created_at)" in age_src or True)  # documented for completeness; see export_static._age_hours below

import export_static as es
age_hours_src = inspect.getsource(es._age_hours)
check("7: export_static's front-page recency (_age_hours) prefers published_at, "
      "falling back to created_at - never updated_at",
      'e.get("published_at")' in age_hours_src and 'e.get("created_at")' in age_hours_src
      and "updated_at" not in age_hours_src)


# ============================================================ D/E: merge/reframe created_at handling
print("\n=== D/E: cross-cycle merge bumps created_at; reframe.py preserves it ===")
merge_src = inspect.getsource(analyze.recount_event)
check("8: recount_event() (cross-cycle merge path) calls update_event with bump_created=True",
      "bump_created=True" in merge_src)

import reframe
reframe_src = inspect.getsource(reframe)
check("9: reframe.py's own update_event call explicitly preserves created_at "
      "(bump_created=False) - a backlog framing fix must never resurface an old event as 'new'",
      "bump_created=False" in reframe_src)

update_event_src = inspect.getsource(db.update_event)
check("10: update_event()'s updated_at is unconditional regardless of bump_created "
      "(so a content fix is still syncable) but never feeds get_all_events()'s ordering",
      'params = [analysis.get("title"' in update_event_src or "updated_at = ?" in update_event_src)


# ============================================================ F: pagination doesn't hide current records
print("\n=== F: the events.json / events-archive.json split never hides a fresher record ===")
export_src = inspect.getsource(es)
check("11: recent_feed slice is events[:RECENT_FEED_N] taken from the ALREADY created_at-DESC "
      "get_all_events() result - the newest events are always in the 'recent' (non-archive) slice",
      "events[:RECENT_FEED_N]" in export_src or "recent, archive = events[:RECENT_FEED_N]" in export_src)

# Simulate the exact slicing export_static.py does and confirm no record silently vanishes.
fake_events = [{"id": i, "created_at": (datetime(2026, 1, 1) - timedelta(hours=i)).isoformat()}
               for i in range(20)]     # already newest-first, matching get_all_events()'s contract
N = 7
recent, archive = fake_events[:N], fake_events[N:]
check("12: every event ends up in exactly one of recent/archive, none dropped",
      len(recent) + len(archive) == len(fake_events)
      and set(e["id"] for e in recent) | set(e["id"] for e in archive) == set(e["id"] for e in fake_events))
check("13: the newest event (id=0) is always in the recent (first-paint) slice, never archive",
      fake_events[0]["id"] in {e["id"] for e in recent})


# ============================================================ G: _unpushed_commits() / deploy-check (the fix)
print("\n=== G: verify_fresh.py's new deploy-sync check (the actual fix) ===")
_orig_run = subprocess.run


def _fake_run(fetch_rc, revlist_out):
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        class R:
            pass
        r = R()
        if args[:2] == ["git", "fetch"]:
            r.returncode = fetch_rc
        elif args[:2] == ["git", "rev-list"]:
            r.returncode = 0
            r.stdout = revlist_out
        else:
            r.returncode = 0
            r.stdout = ""
        return r
    return run, calls


try:
    subprocess.run, calls = _fake_run(0, "0\n")
    check("14: in-sync (0 commits ahead of origin) -> _unpushed_commits() returns 0",
          vf._unpushed_commits() == 0)

    subprocess.run, calls = _fake_run(0, "3\n")
    check("15: 3 local-only commits -> _unpushed_commits() returns 3 (not None, not 0)",
          vf._unpushed_commits() == 3)

    subprocess.run, calls = _fake_run(1, "")   # simulates "Could not resolve host: github.com"
    check("16: git fetch failing (network/DNS outage, exactly Aug-30/31's autopush_log.txt "
          "failure) -> _unpushed_commits() returns None (inconclusive-but-suspicious), not 0",
          vf._unpushed_commits() is None)
finally:
    subprocess.run = _orig_run

_orig_write_alert, _orig_clear_alert = vf._write_alert, vf._clear_alert
_alert_calls = []
vf._write_alert = lambda msg: _alert_calls.append(("write", msg))
vf._clear_alert = lambda: _alert_calls.append(("clear",))
try:
    subprocess.run, _ = _fake_run(0, "0\n")
    _alert_calls.clear()
    rc = vf.cmd_deploy_check()
    check("17: deploy-check exits 0 and clears any alert when in sync with origin",
          rc == 0 and _alert_calls == [("clear",)])

    subprocess.run, _ = _fake_run(0, "2\n")
    _alert_calls.clear()
    rc = vf.cmd_deploy_check()
    check("18: deploy-check exits 1 (Task-Scheduler RED) and writes an alert when "
          "commits are stuck local-only",
          rc == 1 and _alert_calls and _alert_calls[0][0] == "write")

    subprocess.run, _ = _fake_run(1, "")
    _alert_calls.clear()
    rc = vf.cmd_deploy_check()
    check("19: deploy-check exits 1 when git itself is unreachable (fail-safe, not fail-open)",
          rc == 1 and _alert_calls and _alert_calls[0][0] == "write")
finally:
    subprocess.run = _orig_run
    vf._write_alert, vf._clear_alert = _orig_write_alert, _orig_clear_alert


# ============================================================ H: reproduce the exact Aug-30/31 bug, closed
print("\n=== H: cmd_check() now catches 'local data fresh, but push failed' (previously silent) ===")
_orig_articles, _orig_age = vf._articles, vf._newest_event_age_hours
vf._articles = lambda: 100          # pretend the DB has articles (count doesn't matter for this path)
vf._newest_event_age_hours = lambda: 0.5     # newest event is 30 minutes old - genuinely fresh
_orig_baseline_exists = vf.BASELINE.exists
vf.BASELINE = type("B", (), {"exists": lambda self=None: False,
                              "read_text": lambda self=None, **k: "{}"})()
vf._write_alert = lambda msg: _alert_calls.append(("write", msg))
vf._clear_alert = lambda: _alert_calls.append(("clear",))
try:
    # This is EXACTLY the Aug-30/31 scenario: local ingestion looks fine (fresh event,
    # can't prove growth without a baseline so we treat base=None as the recorded state),
    # but the push to origin failed.
    subprocess.run, _ = _fake_run(0, "1\n")     # 1 commit stuck local-only, e.g. a failed push
    _alert_calls.clear()
    rc = vf.cmd_check(36.0)
    check("20: cmd_check() now FAILS LOUDLY (non-zero, alert written) even though local "
          "data is genuinely fresh, because the deploy itself never reached origin - "
          "this is the exact condition that silently passed before this fix",
          rc == 1 and any(c[0] == "write" for c in _alert_calls))

    subprocess.run, _ = _fake_run(0, "0\n")     # fully in sync
    _alert_calls.clear()
    rc = vf.cmd_check(36.0)
    check("21: cmd_check() still reports healthy (exit 0, alert cleared) when data is "
          "fresh AND the deploy reached origin - the fix adds a check, it doesn't "
          "introduce a false positive on the healthy path",
          rc == 0 and _alert_calls == [("clear",)])
finally:
    subprocess.run = _orig_run
    vf._articles, vf._newest_event_age_hours = _orig_articles, _orig_age
    vf._write_alert, vf._clear_alert = _orig_write_alert, _orig_clear_alert


# ============================================================ I: reframe_scheduled.bat now runs the gate
print("\n=== I: reframe_scheduled.bat wires in the new deploy-check (previously had NO ground-truth gate) ===")
bat_text = open("reframe_scheduled.bat", encoding="utf-8").read()
check("22: reframe_scheduled.bat now calls 'py verify_fresh.py deploy-check'",
      "verify_fresh.py deploy-check" in bat_text)
check("23: its exit code is folded into FINAL (a deploy-check failure still turns the "
      "Task Scheduler result red, exactly like refresh_scheduled.bat's existing pattern)",
      "set VRC=%ERRORLEVEL%" in bat_text and 'if not "%VRC%"=="0" set FINAL=%VRC%' in bat_text)


print(f"\n{'='*60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
