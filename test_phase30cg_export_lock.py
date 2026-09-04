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
check("7: the FIRST rename (final -> old) still happened before the failure, so the "
      "last known-good build is preserved at _site.old, not lost",
      old_dir.exists() and (old_dir / "index.html").read_text() == prior_good_content)
check("8: the new (unpublished) build is still intact at its own directory - nothing "
      "was destroyed on either side of the failed swap",
      building.exists() and (building / "index.html").read_text() == "good_new_build")
check("9: final_dir itself is the one that's now temporarily MISSING (the documented "
      "'one rename, milliseconds' window) - not corrupted, not half-written",
      not final.exists())

print("\n=== 4: recovery from _site.old (what an operator/next run actually sees) ===")
# A real next run's _publish_build() call starts by _rmtree_safe(old_dir) then moving
# final_dir aside again - but since final_dir is currently MISSING (not present) after
# the simulated persistent failure above, a recovery run should cleanly re-publish the
# pending build without needing old_dir at all, and old_dir's last-known-good copy
# remains a safe manual fallback throughout.
es._publish_build(building, final)
check("10: a subsequent successful run recovers cleanly - final_dir holds the build "
      "that was stuck in _site.building", (final / "index.html").read_text() == "good_new_build")

print("\n=== 5: _rename_safe() retry parameters are actually wired as intended ===")
import inspect
src = inspect.getsource(es._publish_build)
check("11: _publish_build() calls _rename_safe(build_dir, final_dir, ...) with the "
      "hardened attempts=20, delay=1.0 (not the old bare-default 5x0.5s call)",
      "attempts=20" in src and "delay=1.0" in src)

shutil.rmtree(FIXTURE_ROOT, ignore_errors=True)

print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
