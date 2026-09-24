"""
test_phase30cg_export_lock.py - Phase 30C-G: regression tests for the
static-export atomic-swap hardening (_publish_build()/_rename_safe() in
export_static.py). Uses a throwaway fixture directory tree under the repo
root (cleaned up on exit, never touches the real _site/_site.old/paksh.db).

Run:  py test_phase30cg_export_lock.py
"""
import shutil
import time
from pathlib import Path
from unittest import mock

import export_static as es

FAILURES = []
FIXTURE_ROOT = Path("C:/paksh_project/paksh/_phase30cg_test_fixture")


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


def fresh_fixture():
    if FIXTURE_ROOT.exists():
        shutil.rmtree(FIXTURE_ROOT)
    FIXTURE_ROOT.mkdir()
    final = FIXTURE_ROOT / "site"
    building = FIXTURE_ROOT / "site.building"
    return final, building


def make_build(building, n_files=10, tag="build"):
    if building.exists():
        shutil.rmtree(building)
    building.mkdir()
    (building / "index.html").write_text(tag, encoding="utf-8")
    (building / "data").mkdir()
    for j in range(n_files):
        (building / "data" / f"{j}.json").write_text("{}", encoding="utf-8")


print("=== 1: tiny fixture export + atomic swap succeeds ===")
final, building = fresh_fixture()
make_build(building, tag="v1")
es._publish_build(building, final)
check("1: final_dir now exists with the new build's content", (final / "index.html").read_text() == "v1")
check("2: build_dir no longer exists at its original location (renamed away)", not building.exists())

print("\n=== 2: repeated swaps (matching the real nightly cadence) ===")
ok_count = 0
for i in range(10):
    make_build(building, tag=f"v{i+2}")
    es._publish_build(building, final)
    if (final / "index.html").read_text() == f"v{i+2}":
        ok_count += 1
check("3: 10 repeated swaps all succeed and each leaves the CORRECT latest content",
      ok_count == 10)

print("\n=== 3: simulated PERSISTENT failure - atomicity must be preserved ===")
make_build(building, tag="good_new_build")
# final currently holds "v11" (the last successful swap above) - a real known-good site.
prior_good_content = (final / "index.html").read_text()

real_rename = Path.rename
call_count = {"n": 0}


def always_fail_rename(self, target):
    # only intercept the build_dir -> final_dir call specifically (identified by
    # the source path), so old_dir's own rename (final -> old) still proceeds normally
    if self.name == building.name:
        call_count["n"] += 1
        raise PermissionError("[WinError 5] Access is denied (simulated, permanent)")
    return real_rename(self, target)


raised = False
with mock.patch.object(Path, "rename", always_fail_rename):
    t0 = time.monotonic()
    try:
        es._publish_build(building, final)
    except PermissionError:
        raised = True
    elapsed = time.monotonic() - t0

check("4: a PERSISTENT lock still raises (never silently 'succeeds')", raised)
check("5: the retry budget was actually exercised (20 attempts, per the Phase 30C-G "
      f"hardening) - observed {call_count['n']} attempt(s)", call_count["n"] == 20)
check("6: the retries were bounded, not instant and not unbounded "
      f"(elapsed {elapsed:.1f}s for 20 x ~1.0s delay)", 15.0 <= elapsed <= 30.0)

old_dir = final.parent / (final.name + ".old")
# 2026-09-24 auto-rollback hardening: a persistent second-rename failure used to leave
# final_dir permanently MISSING with the last-known-good build stranded at old_dir as a
# "manual fallback" (this is exactly what happened in production - see _publish_build's
# docstring). It must now be auto-restored INTO final_dir instead, so a contended/
# interrupted swap degrades to "still serving the previous build", never to "_site is
# just gone".
check("7: final_dir was AUTO-RESTORED to the last known-good build after the persistent "
      "failure - production is never left with _site missing",
      final.exists() and (final / "index.html").read_text() == prior_good_content)
check("8: the new (unpublished) build is still intact at its own directory - nothing "
      "was destroyed on either side of the failed swap",
      building.exists() and (building / "index.html").read_text() == "good_new_build")
check("9: old_dir no longer exists after the auto-restore (it was renamed BACK into "
      "final_dir, not left behind as a second copy)", not old_dir.exists())

print("\n=== 4: recovery after the persistent failure (what a retried publish sees) ===")
# final_dir now holds the RESTORED last-known-good build (test 7) - a subsequent,
# unmocked _publish_build() call with the same pending build_dir should swap it in
# normally, exactly as if the earlier failure had never happened.
es._publish_build(building, final)
check("10: a subsequent successful run recovers cleanly - final_dir holds the build "
      "that was stuck in _site.building", (final / "index.html").read_text() == "good_new_build")

print("\n=== 5: _rename_safe() retry parameters are actually wired as intended ===")
import inspect
src = inspect.getsource(es._publish_build)
check("11: _publish_build() calls _rename_safe(build_dir, final_dir, ...) with the "
      "hardened attempts=20, delay=1.0 (not the old bare-default 5x0.5s call)",
      "attempts=20" in src and "delay=1.0" in src)

print("\n=== 6: successful cleanup failure of _site.old must NEVER fail the publish ===")
# The swap itself (build_dir -> final_dir) already succeeded here - a failure to remove
# the now-unneeded old copy is cosmetic (a lingering .old dir is harmless) and must not
# be reported as an export failure.
make_build(building, tag="v_cleanup_test")
with mock.patch.object(es, "_rmtree_safe", side_effect=[None, OSError("simulated: old_dir cleanup failed")]):
    cleanup_raised = False
    try:
        es._publish_build(building, final)
    except OSError:
        cleanup_raised = True
check("12: a failure cleaning up _site.old does not raise - the successful swap is what "
      "matters, not best-effort cleanup", not cleanup_raised)
check("13: the swap itself still went through despite the cleanup failure",
      (final / "index.html").read_text() == "v_cleanup_test")

print("\n=== 7: a DOUBLE failure (both the swap-in AND the restore-back) must not be "
      "silently swallowed ===")
make_build(building, tag="double_failure_build")
prior_before_double = (final / "index.html").read_text()


def always_fail_both(self, target):
    if self.name in (building.name, old_dir.name):
        raise PermissionError(f"[WinError 5] simulated permanent failure on {self.name}")
    return real_rename(self, target)


double_raised = False
with mock.patch.object(Path, "rename", always_fail_both):
    t0 = time.monotonic()
    try:
        es._publish_build(building, final)
    except PermissionError:
        double_raised = True
    elapsed2 = time.monotonic() - t0
check("14: a double failure (swap-in fails, restore-back also fails) still raises rather "
      "than silently reporting success", double_raised)
check("15: neither side was fabricated or corrupted by the double failure - build_dir "
      "still holds the pending build", (building / "index.html").read_text() == "double_failure_build")

shutil.rmtree(FIXTURE_ROOT, ignore_errors=True)

print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
