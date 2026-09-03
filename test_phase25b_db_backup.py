"""
test_phase25b_db_backup.py - Phase 25B-B: deterministic tests for
backup_db.py's take_backup()/verify_backup()/apply_retention() logic.

Runs entirely against a tiny synthetic SQLite fixture in a temp directory -
NEVER touches the real paksh.db (1.7GB) or the real backups/ directory. The
real end-to-end drill (real backup of the real DB, restored to a disposable
copy, verified via database.py) was performed manually as part of Phase
25B-B's validation and is documented in the phase report, not repeated here
as a fast unit test since running a real ~1.7GB backup on every test run
would be far too slow for a regression suite.

Run:  py test_phase25b_db_backup.py
"""
import shutil
import sqlite3
import tempfile
from pathlib import Path

import backup_db

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


TMP = Path(tempfile.mkdtemp(prefix="paksh_backup_test_"))
try:
    fixture_db = TMP / "fixture.db"
    conn = sqlite3.connect(fixture_db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, title TEXT)")
    conn.execute("CREATE TABLE articles (id INTEGER PRIMARY KEY, event_id INTEGER)")
    conn.execute("INSERT INTO events VALUES (1, 'test event')")
    conn.execute("INSERT INTO articles VALUES (1, 1)")
    conn.commit()
    conn.close()

    orig_db, orig_dir, orig_log = backup_db.DB_PATH, backup_db.BACKUP_DIR, backup_db.LOG_PATH
    backup_db.DB_PATH = fixture_db
    backup_db.BACKUP_DIR = TMP / "backups"
    backup_db.LOG_PATH = TMP / "backup_log.txt"

    print("TEST 1: take_backup() produces a clean, single-file, verifiable copy")
    dest = backup_db.take_backup()
    check("1a: backup file exists", dest.exists())
    check("1b: no -wal/-shm sidecar left behind", not dest.with_name(dest.name + "-wal").exists()
          and not dest.with_name(dest.name + "-shm").exists())
    ok, detail = backup_db.verify_backup(dest)
    check("1c: verify_backup() passes on a genuinely good backup", ok)
    print(f"     detail: {detail}")

    print("\nTEST 2: verify_backup() correctly FAILS on a corrupt file")
    corrupt = TMP / "corrupt.db"
    corrupt.write_bytes(b"this is not a sqlite database")
    ok2, detail2 = backup_db.verify_backup(corrupt)
    check("2: verify_backup() returns False for a non-database file", ok2 is False)

    print("\nTEST 3: verify_backup() correctly FAILS on a suspiciously-empty database "
          "(schema present, zero rows - the 'silently backed up nothing' failure mode)")
    empty_db = TMP / "empty.db"
    ec = sqlite3.connect(empty_db)
    ec.execute("CREATE TABLE events (id INTEGER PRIMARY KEY)")
    ec.execute("CREATE TABLE articles (id INTEGER PRIMARY KEY)")
    ec.commit()
    ec.close()
    ok3, detail3 = backup_db.verify_backup(empty_db)
    check("3: verify_backup() returns False for an empty-but-valid database", ok3 is False)

    print("\nTEST 4: apply_retention() keeps only the newest N of THIS script's own backups, "
          "and never touches a differently-named (unmanaged/ad-hoc) file")
    dest.unlink()   # remove TEST 1's own backup first - test 4 wants exact control over
                     # exactly which files are present, not TEST 1's leftover real one
    for i in range(5):
        f = backup_db.BACKUP_DIR / f"paksh_backup_2026010{i+1}_000000.db"
        f.write_text("x")
    adhoc = backup_db.BACKUP_DIR / "paksh_pre_something_ad_hoc.db"
    adhoc.write_text("do not touch me")
    failed_marker = backup_db.BACKUP_DIR / "paksh_backup_20260106_000000.FAILED.db"
    failed_marker.write_text("a failed-verification backup")
    backup_db.apply_retention(keep=2)
    remaining = sorted(p.name for p in backup_db.BACKUP_DIR.glob("paksh_backup_*.db"))
    check("4a: exactly 2 of the 5 managed backups remain (the 2 newest by name/timestamp)",
          len([n for n in remaining if not n.endswith("FAILED.db")]) == 2)
    check("4b: the 2 remaining are the chronologically newest",
          "paksh_backup_20260105_000000.db" in remaining and "paksh_backup_20260104_000000.db" in remaining)
    check("4c: the unmanaged ad-hoc file was never touched", adhoc.exists())
    check("4d: a .FAILED.db backup is a different name pattern and untouched by this glob "
          "(retention only manages successfully-named backups; failed ones are left for "
          "forensic inspection, matching backup_db.py's own documented behavior)",
          failed_marker.exists())

    backup_db.DB_PATH, backup_db.BACKUP_DIR, backup_db.LOG_PATH = orig_db, orig_dir, orig_log

finally:
    shutil.rmtree(TMP, ignore_errors=True)

print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
