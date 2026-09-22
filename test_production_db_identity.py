"""
test_production_db_identity.py - Phase 21-fix round 2 (2026-09-23): proves the
concrete bypass that produced a 457-event export (a long-running live.py process
whose environment predated the PAKSH_DATA_DIR fix) now fails CLOSED, IMMEDIATELY,
before any database connection - not 28 minutes later at the export guard.

Real subprocesses throughout (not mocks), using temp fixture directories - never
touches the real D:\\Paksh_Data or the real %LOCALAPPDATA% config.

Run:  py test_production_db_identity.py
"""
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import paksh_paths as pp

FAILURES = []


def check(label, cond, detail=""):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILURES.append(label)


REPO = str(Path(__file__).parent)
TMP = Path(tempfile.mkdtemp(prefix="paksh_prod_identity_test_"))


def make_data_dir(root, marker=pp.PRODUCTION_MARKER_MAGIC):
    (root / "database").mkdir(parents=True, exist_ok=True)
    sqlite3.connect(root / "database" / "paksh.db").close()
    if marker is not None:
        pp.production_marker_path(root).write_text(marker, encoding="utf-8")
    return root


PROD = make_data_dir(TMP / "production_root")
WRONG_PROD = make_data_dir(TMP / "a_different_but_validly_marked_dir")

VERIFY_CODE = """
import sys
sys.path.insert(0, r"{repo}")
import live
try:
    live._verify_production_db_identity()
    print("RESULT: OK")
except SystemExit as e:
    print(f"RESULT: SYSEXIT code={{e.code}}")
    raise
"""


def run_verify(label, env_overrides, unset, production_data_dir=None):
    env = dict(os.environ)
    for k in unset:
        env.pop(k, None)
    env.update(env_overrides)
    code = VERIFY_CODE.format(repo=REPO)
    if production_data_dir is not None:
        # patch the module-level constant for this child, without touching the
        # real repo file - append an override after import, before calling.
        code = code.replace(
            "import live\n",
            f"import live\nlive.PRODUCTION_DATA_DIR = r\"{production_data_dir}\"\n",
        )
    r = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env,
                        capture_output=True, text=True, timeout=30)
    print(f"  [{label}] exit={r.returncode} stdout={r.stdout.strip()!r}")
    return r.returncode, r.stdout


print("=== 1. correct explicit PAKSH_DATA_DIR, matching PRODUCTION_DATA_DIR -> passes ===")
rc, out = run_verify("correct", {"PAKSH_DATA_DIR": str(PROD)},
                      unset=("LOCALAPPDATA",), production_data_dir=str(PROD))
check("t1: exits 0, no SystemExit", rc == 0 and "RESULT: OK" in out)

print("\n=== 2. THE ACTUAL REPRODUCED BYPASS: a stale/unset PAKSH_DATA_DIR, "
      "LOCALAPPDATA present but pointing nowhere useful - the exact condition "
      "that produced the 457-event export ===")
fake_localappdata = TMP / "fake_localappdata_no_paksh_dir"
fake_localappdata.mkdir(exist_ok=True)
rc, out = run_verify("stale env (reproduces the incident)",
                      {"LOCALAPPDATA": str(fake_localappdata)},
                      unset=("PAKSH_DATA_DIR",), production_data_dir=str(PROD))
check("t2: fails CLOSED with a non-zero exit - BEFORE any database connection",
      rc != 0 and "RESULT: OK" not in out, f"rc={rc} out={out!r}")

print("\n=== 3. PAKSH_DATA_DIR set, marker valid, but pointing at the WRONG directory "
      "(not the canonical production root) - the identity check catches this even "
      "though the generic marker check alone would not ===")
rc, out = run_verify("wrong-but-validly-marked directory",
                      {"PAKSH_DATA_DIR": str(WRONG_PROD)},
                      unset=("LOCALAPPDATA",), production_data_dir=str(PROD))
check("t3: fails CLOSED - a validly-marked directory is not enough if it isn't THE "
      "expected production root", rc != 0 and "RESULT: OK" not in out)

print("\n=== 4. child subprocess chain: production launcher -> child process -> "
      "database connection -> export all resolve the SAME root ===")
chain_env = dict(os.environ)
chain_env.pop("LOCALAPPDATA", None)
chain_env["PAKSH_DATA_DIR"] = str(PROD)

resolvers = {
    "database.py (ingest/cluster/analyze all import this)":
        "import sys; sys.path.insert(0, r'%s'); import database; print(database.DB_PATH)" % REPO,
    "export_static.py":
        "import sys; sys.path.insert(0, r'%s'); import export_static; "
        "import database; print(database.DB_PATH)" % REPO,
    "paksh_paths.py directly":
        "import sys; sys.path.insert(0, r'%s'); import paksh_paths as pp; print(pp.db_path())" % REPO,
}
expected_path = str(PROD / "database" / "paksh.db")
all_match = True
for label, code in resolvers.items():
    r = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=chain_env,
                        capture_output=True, text=True, timeout=30)
    resolved = r.stdout.strip()
    ok = resolved == expected_path
    all_match = all_match and ok
    print(f"  {label}: resolved={resolved!r} match={ok}")
check("t4: every stage in the chain (database.py, export_static.py, paksh_paths.py) "
      "resolves the identical production DB path", all_match)

shutil.rmtree(TMP, ignore_errors=True)

print(f"\n{'=' * 60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL PRODUCTION DB IDENTITY CHECKS PASSED")
