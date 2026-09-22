"""
test_export_collapse_guard.py - Phase 21-fix (2026-09-23): deterministic tests for
export_static.py's second, independent guard against publishing a collapsed site -
the safety net that catches exactly the 9242 -> 400 event shape a database-path
failure produces, regardless of what caused it.

Fast and isolated: only exercises _count_event_files() / _check_export_plausible()
against throwaway temp directories with empty placeholder .json files. Never runs
the real (slow) export_static.main() build - that real, end-to-end reproduction
was done once by hand (see the Phase 21-fix implementation report) using real
databases; these tests pin the guard's own logic permanently and fast.

Run:  py test_export_collapse_guard.py
"""
import os
import tempfile
from pathlib import Path

import export_static as ex

FAILURES = []


def check(label, cond, detail=""):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILURES.append(label)


def make_site(n_events, root=None):
    root = Path(root) if root else Path(tempfile.mkdtemp(prefix="paksh_export_guard_"))
    events_dir = root / "data" / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    for i in range(n_events):
        (events_dir / f"{i}.json").write_text("{}", encoding="utf-8")
    return root


def _raises(fn):
    try:
        fn()
    except ex.ExportCollapseError:
        return True
    return False


print("=== _count_event_files ===")
check("c1: counts .json files under data/events", ex._count_event_files(make_site(9242)) == 9242)
check("c2: a site with no data/events dir at all counts as 0",
      ex._count_event_files(Path(tempfile.mkdtemp(prefix="paksh_export_guard_empty_"))) == 0)
check("c3: an existing but empty events dir counts as 0", ex._count_event_files(make_site(0)) == 0)

print("\n=== 8. catastrophic export contraction is caught ===")
good = make_site(9242)
check("8a: 9242 -> 400 (the actual historical shape) is caught",
      _raises(lambda: ex._check_export_plausible(400, good)))
check("8b: a small, normal day's drop (9242 -> 9170) is NOT flagged",
      not _raises(lambda: ex._check_export_plausible(9170, good)))
check("8c: growth is never flagged", not _raises(lambda: ex._check_export_plausible(9300, good)))
check("8d: exactly at the retention fraction boundary is NOT flagged (>=, not <)",
      not _raises(lambda: ex._check_export_plausible(
          int(9242 * ex.EXPORT_MIN_RETENTION_FRACTION), good)))
check("8e: one below the boundary IS flagged",
      _raises(lambda: ex._check_export_plausible(
          int(9242 * ex.EXPORT_MIN_RETENTION_FRACTION) - 1, good)))
check("8f: a fresh checkout with no previous site (0 previous) never blocks the first build",
      not _raises(lambda: ex._check_export_plausible(5, make_site(0))))
check("8g: the check never references a hard-coded expected count - it is purely "
      "relative to whatever the current site has",
      ex.EXPORT_MIN_RETENTION_FRACTION < 1 and not hasattr(ex, "_EXPECTED_EVENT_COUNT"))

print("\n=== 9. a failed export leaves the existing site untouched ===")
final_dir = make_site(9242)
snapshot = sorted(p.name for p in (final_dir / "data" / "events").glob("*.json"))
try:
    ex._check_export_plausible(400, final_dir)
    raised = False
except ex.ExportCollapseError:
    raised = True
after = sorted(p.name for p in (final_dir / "data" / "events").glob("*.json"))
check("9a: the guard function itself never writes to final_dir", raised and snapshot == after)
check("9b: PAKSH_ALLOW_EXPORT_COLLAPSE is the documented override, and main() checks it "
      "(present in export_static.py's source, not just this test)",
      "PAKSH_ALLOW_EXPORT_COLLAPSE" in open("export_static.py", encoding="utf-8").read())

print(f"\n{'=' * 60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL EXPORT COLLAPSE GUARD CHECKS PASSED")
