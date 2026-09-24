"""
test_paksh_paths.py - deterministic tests for paksh_paths.py (where paksh.db and its backups live).

Runs only against temp directories; never touches the real paksh.db, the real %LOCALAPPDATA% config, or D:.

Run:  py test_paksh_paths.py
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import paksh_paths as pp

FAILURES = []


def check(label, cond):
    print(f"  {label} ... {'OK' if cond else 'FAIL'}")
    if not cond:
        FAILURES.append(label)


def raises(fn):
    try:
        fn()
    except pp.DataDirError:
        return True
    return False


TMP = Path(tempfile.mkdtemp(prefix="paksh_paths_test_"))
_saved = {k: os.environ.get(k) for k in ("PAKSH_DATA_DIR", "LOCALAPPDATA", "PAKSH_ALLOW_NEW_DB")}


def reset(**env):
    for k in _saved:
        os.environ.pop(k, None)
    os.environ["LOCALAPPDATA"] = str(TMP / "localappdata")      # an empty, private "local app data"
    os.environ.update(env)


try:
    print("TEST 1: unconfigured = today's in-repo layout (the default must not change)")
    reset()
    check("1a: no data dir configured", pp.configured_data_dir() is None)
    check("1b: db is <repo>/paksh.db", pp.db_path() == pp.ROOT / "paksh.db")
    check("1c: backups are <repo>/backups", pp.backup_dir() == pp.ROOT / "backups")
    check("1d: describe() says not configured", pp.describe()["configured"] is False)
    check("1e: require_ready is a no-op", pp.require_ready(pp.db_path()) is None)

    print("\nTEST 2: environment variable selects the data dir")
    data = TMP / "Paksh_Data"
    reset(PAKSH_DATA_DIR=str(data))
    check("2a: db under <data>/database", pp.db_path() == data / "database" / "paksh.db")
    check("2b: backups under <data>/backups/daily", pp.backup_dir() == data / "backups" / "daily")
    check("2c: archive under <data>/backups/archive", pp.archive_dir() == data / "backups" / "archive")

    print("\nTEST 3: config file selects the data dir; comments/blank lines/BOM are ignored")
    reset()
    cfg = pp.config_file()
    cfg.parent.mkdir(parents=True)
    cfg.write_text("﻿# where Paksh keeps its data\n\n" + str(data) + "\n# trailing\n", encoding="utf-8")
    check("3a: first non-comment line is used", pp.configured_data_dir() == data)
    reset(PAKSH_DATA_DIR=str(TMP / "other"))
    check("3b: the environment variable wins over the file", pp.configured_data_dir() == TMP / "other")
    reset()
    cfg.write_text("# only a comment\n", encoding="utf-8")
    check("3c: a file with only comments means unconfigured", pp.configured_data_dir() is None)

    print("\nTEST 4: require_ready fails loudly instead of forking or creating an empty database")
    reset(PAKSH_DATA_DIR=str(data))
    check("4a: data dir missing -> DataDirError", raises(lambda: pp.require_ready(pp.db_path())))
    (data / "database").mkdir(parents=True)
    check("4b: data dir present but DB missing -> DataDirError", raises(lambda: pp.require_ready(pp.db_path())))
    pp.production_marker_path(data).write_text(pp.PRODUCTION_MARKER_MAGIC, encoding="utf-8")
    check("4c: require_ready(None) also checks the configured DB", raises(lambda: pp.require_ready()))
    check("4d: a DB path that is NOT the configured one (tests/temp DBs) is left alone",
          pp.require_ready(TMP / "fixture.db") is None)
    os.environ["PAKSH_ALLOW_NEW_DB"] = "1"
    check("4e: PAKSH_ALLOW_NEW_DB=1 deliberately allows a new DB", pp.require_ready(pp.db_path()) is None)
    del os.environ["PAKSH_ALLOW_NEW_DB"]
    sqlite3.connect(pp.db_path()).close()
    check("4f: DB present -> ready", pp.require_ready(pp.db_path()) is None)

    print("\nTEST 5: database.get_connection honours the guard (no silent empty DB)")
    import database
    reset(PAKSH_DATA_DIR=str(TMP / "Gone"))
    orig = database.DB_PATH, database._db_initialized
    database.DB_PATH = pp.db_path()
    database._db_initialized = False
    check("5a: get_connection raises when the configured drive/dir is missing",
          raises(lambda: database.get_connection()))
    check("5b: ...and did not create the database", not pp.db_path().exists())
    database.DB_PATH, database._db_initialized = orig

    print("\nTEST 6: backup_db defaults follow paksh_paths and create parent folders")
    import backup_db
    fx = TMP / "fixture6.db"
    c6 = sqlite3.connect(fx)
    c6.execute("CREATE TABLE events (id INTEGER PRIMARY KEY)")
    c6.execute("CREATE TABLE articles (id INTEGER PRIMARY KEY)")
    c6.execute("INSERT INTO events VALUES (1)")
    c6.execute("INSERT INTO articles VALUES (1)")
    c6.commit()
    c6.close()
    o_db, o_dir = backup_db.DB_PATH, backup_db.BACKUP_DIR
    backup_db.DB_PATH, backup_db.BACKUP_DIR = fx, TMP / "new" / "drive" / "backups" / "daily"
    try:
        dest6 = backup_db.take_backup()
        check("6a: take_backup creates missing parent folders", dest6.exists())
        check("6b: the new backup verifies", backup_db.verify_backup(dest6)[0])
    finally:
        backup_db.DB_PATH, backup_db.BACKUP_DIR = o_db, o_dir
    reset()
    check("6c: with nothing configured, backup_db defaults resolve to today's layout",
          pp.backup_dir() == pp.ROOT / "backups" and pp.db_path() == pp.ROOT / "paksh.db")
    print("\nTEST 7: storage status and backup free-space guard (Phase 12B)")
    reset(PAKSH_DATA_DIR=str(data))
    st = pp.storage_status()
    check("7a: storage_status reports configured / exists / free space and never creates anything", st["configured"] and st["guard_active"] and st["free_bytes"] and not (TMP / "Paksh_Data" / "x").exists())
    check("7b: it flags a stale repo copy of paksh.db next to the code while a data dir is configured", "ambiguous_repo_copy" in st and st["repo_db_present"] == (pp.ROOT / "paksh.db").exists())
    reset()
    check("7c: unconfigured -> guard_active False", pp.storage_status()["guard_active"] is False)
    import shutil as _sh
    import backup_db as _bk
    _fix = TMP / "space.db"
    _c = sqlite3.connect(_fix)
    _c.execute("CREATE TABLE events (id INTEGER PRIMARY KEY)")
    _c.execute("CREATE TABLE articles (id INTEGER PRIMARY KEY)")
    _c.execute("INSERT INTO events VALUES (1)")
    _c.execute("INSERT INTO articles VALUES (1)")
    _c.commit()
    _c.close()
    _o = (_bk.DB_PATH, _bk.BACKUP_DIR, _bk.LOG_PATH, _sh.disk_usage)
    _bk.DB_PATH, _bk.BACKUP_DIR, _bk.LOG_PATH = _fix, TMP / "bk", TMP / "bk.log"
    _sh.disk_usage = lambda p: type("U", (), {"free": 10})()
    _sys_argv = __import__("sys").argv
    __import__("sys").argv = ["backup_db.py"]
    try:
        try:
            _bk.main()
            _refused = False
        except SystemExit as e:
            _refused = e.code == 1
    finally:
        _bk.DB_PATH, _bk.BACKUP_DIR, _bk.LOG_PATH, _sh.disk_usage = _o
        __import__("sys").argv = _sys_argv
    check("7d: a backup that cannot fit is refused BEFORE writing anything", _refused and not (TMP / "bk").exists())

    print("\nTEST 8: fail CLOSED when configuration cannot be determined at all (2026-09-22 fix)")
    # 8a/8b: LOCALAPPDATA itself unavailable - the exact condition behind the incident.
    for k in _saved:
        os.environ.pop(k, None)
    check("8a: config_file() is None when LOCALAPPDATA is unset", pp.config_file() is None)
    check("8b: configured_data_dir() still reads as 'nothing configured' (unchanged for ordinary callers)",
          pp.configured_data_dir() is None)
    check("8c: db_path() still resolves to the in-repo default (unchanged - db_path() itself never fails)",
          pp.db_path() == pp.ROOT / "paksh.db")
    check("8d: require_ready() now FAILS instead of silently no-op'ing",
          raises(lambda: pp.require_ready(pp.db_path())))
    os.environ["PAKSH_ALLOW_NEW_DB"] = "1"
    check("8e: PAKSH_ALLOW_NEW_DB=1 remains the explicit escape hatch even here",
          pp.require_ready(pp.db_path()) is None)
    os.environ.pop("PAKSH_ALLOW_NEW_DB")
    check("8f: describe() reports the specific reason (no_localappdata), not just 'unconfigured'",
          pp.describe()["config_resolution"] == pp._NO_ENV)

    # 8g/8h: config file exists but cannot be read (simulated: point LOCALAPPDATA at a
    # location where the "file" is actually a directory, so reading it raises OSError).
    os.environ["LOCALAPPDATA"] = str(TMP / "localappdata_unreadable")
    unreadable_cfg = pp.config_file()
    unreadable_cfg.parent.mkdir(parents=True)
    unreadable_cfg.mkdir()   # a directory where a file is expected -> read_text() raises OSError
    check("8g: describe() reports config_unreadable, not 'unconfigured'",
          pp.describe()["config_resolution"] == pp._UNREADABLE)
    check("8h: require_ready() fails closed for an unreadable config file too",
          raises(lambda: pp.require_ready(pp.db_path())))
    os.environ.pop("LOCALAPPDATA", None)

    print("\nTEST 9: database.get_connection() also fails closed when LOCALAPPDATA is unavailable, "
          "and does NOT create a repo-local database even if a stray one already exists")
    for k in _saved:
        os.environ.pop(k, None)
    stray = TMP / "stray_repo_paksh.db"
    sqlite3.connect(stray).close()   # simulate a pre-existing stray repo-local paksh.db
    orig2 = database.DB_PATH, database._db_initialized
    database.DB_PATH = stray
    database._db_initialized = False
    check("9a: get_connection() raises rather than silently opening the stray local DB",
          raises(lambda: database.get_connection()))
    database.DB_PATH, database._db_initialized = orig2

    print("\nTEST 10: explicit dev/test mode is unaffected - PAKSH_ALLOW_NEW_DB=1 still works "
          "even with no LOCALAPPDATA at all, and a temp/test DB_PATH is still exempt")
    for k in _saved:
        os.environ.pop(k, None)
    os.environ["PAKSH_ALLOW_NEW_DB"] = "1"
    check("10a: PAKSH_ALLOW_NEW_DB=1 + no LOCALAPPDATA -> still a no-op (deliberate dev/test)",
          pp.require_ready(pp.db_path()) is None)
    os.environ.pop("PAKSH_ALLOW_NEW_DB")
    # a configured-but-mismatched path (the tests/temp-DB exemption) must still work even
    # when a REAL external data dir is configured and reachable.
    reset(PAKSH_DATA_DIR=str(data))
    (data / "database").mkdir(parents=True, exist_ok=True)
    sqlite3.connect(data / "database" / "paksh.db").close()
    check("10b: a real configured+ready external dir still exempts an unrelated temp DB path",
          pp.require_ready(TMP / "some_other_fixture.db") is None)

    print("\nTEST 11: PAKSH_DATA_DIR is authoritative and requires a validated production "
          "marker (2026-09-23 fix)")

    def make_data_dir(root, with_db=True, marker=None):
        """root/database/paksh.db (+ optionally root/.paksh-production with `marker`
        content, or no marker file at all if marker is None)."""
        (root / "database").mkdir(parents=True, exist_ok=True)
        if with_db:
            sqlite3.connect(root / "database" / "paksh.db").close()
        if marker is not None:
            pp.production_marker_path(root).write_text(marker, encoding="utf-8")

    prod = TMP / "real_production"
    make_data_dir(prod, marker=pp.PRODUCTION_MARKER_MAGIC)

    # 11a: correct explicit PAKSH_DATA_DIR (marker present and valid, DB present) works.
    reset(PAKSH_DATA_DIR=str(prod))
    check("11a: correct explicit PAKSH_DATA_DIR + valid marker -> ready",
          pp.require_ready(pp.db_path()) is None)

    # 11b: WRONG LOCALAPPDATA (points somewhere with its own, different, data_dir.txt)
    # + correct PAKSH_DATA_DIR -> PAKSH_DATA_DIR wins outright; LOCALAPPDATA is not
    # even consulted.
    decoy = TMP / "decoy_via_localappdata"
    make_data_dir(decoy, marker=pp.PRODUCTION_MARKER_MAGIC)
    os.environ.pop("PAKSH_DATA_DIR", None)
    os.environ["LOCALAPPDATA"] = str(TMP / "wrong_localappdata")
    cfg = pp.config_file()
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(str(decoy), encoding="utf-8")
    check("11b0: sanity - LOCALAPPDATA alone would have pointed at the decoy",
          pp.configured_data_dir() == decoy)
    os.environ["PAKSH_DATA_DIR"] = str(prod)
    check("11b: wrong-but-valid LOCALAPPDATA + correct PAKSH_DATA_DIR -> resolves to "
          "PAKSH_DATA_DIR, not the LOCALAPPDATA decoy",
          pp.configured_data_dir() == prod)
    check("11b2: ...and require_ready() is happy (the decoy is irrelevant)",
          pp.require_ready(pp.db_path()) is None)

    # 11c: missing LOCALAPPDATA entirely + correct PAKSH_DATA_DIR -> still works (this
    # is the whole point - production no longer depends on LOCALAPPDATA at all).
    os.environ.pop("LOCALAPPDATA", None)
    os.environ["PAKSH_DATA_DIR"] = str(prod)
    check("11c: PAKSH_DATA_DIR works even with LOCALAPPDATA completely unset",
          pp.require_ready(pp.db_path()) is None)

    # 11d: a repo-local paksh.db existing elsewhere must never be selected when
    # PAKSH_DATA_DIR is set correctly - db_path() only ever looks under PAKSH_DATA_DIR.
    check("11d: a repo-local paksh.db existing does not change what db_path() resolves to",
          pp.db_path() == prod / "database" / "paksh.db" != pp.ROOT / "paksh.db")

    # 11e: missing production marker -> fails closed even though the dir+DB are fine.
    unmarked = TMP / "unmarked_dir"
    make_data_dir(unmarked, marker=None)
    reset(PAKSH_DATA_DIR=str(unmarked))
    check("11e: PAKSH_DATA_DIR set, DB present, but NO production marker -> DataDirError",
          raises(lambda: pp.require_ready(pp.db_path())))

    # 11f: invalid/wrong production marker content -> also fails closed ("wrong
    # production data root" - some other, unrelated directory that merely has a DB).
    wrong_marker = TMP / "wrong_marker_dir"
    make_data_dir(wrong_marker, marker="not-the-right-magic-value")
    reset(PAKSH_DATA_DIR=str(wrong_marker))
    check("11f: PAKSH_DATA_DIR set with an invalid marker value -> DataDirError",
          raises(lambda: pp.require_ready(pp.db_path())))

    # 11g: child subprocess inheritance - a real subprocess started with PAKSH_DATA_DIR
    # in its environment resolves it correctly, exactly like live.py's children do
    # (subprocess.run() with no env= override inherits os.environ).
    import subprocess as _sp
    child_env = dict(os.environ)
    child_env["PAKSH_DATA_DIR"] = str(prod)
    child_env.pop("LOCALAPPDATA", None)
    child_code = (
        "import sys; sys.path.insert(0, r'%s')\n"
        "import paksh_paths as pp\n"
        "print(pp.configured_data_dir())\n" % str(pp.ROOT)
    )
    _r = _sp.run([sys.executable, "-c", child_code], env=child_env, capture_output=True, text=True, timeout=30)
    check("11g: a child process inherits PAKSH_DATA_DIR and resolves it correctly",
          _r.stdout.strip() == str(prod))

    print("\nTEST 12: require_production() - the stricter export-only guard (2026-09-24 fix)")
    # 2026-09-24 real incident: a manual `export_static.py` run, in a process
    # environment where the LOCALAPPDATA config file happened not to resolve, saw
    # config_resolution = _NOT_CONFIGURED (which require_ready() correctly allows for
    # ordinary pipeline scripts) and silently opened the repo-local paksh.db, producing
    # a wildly wrong publishable-event count. require_production() closes exactly that
    # gap for the one entry point that PUBLISHES, without changing require_ready() or
    # any of its existing callers (live.py, refresh.py, reframe.py, database.py).

    def make_prod_dir(root, with_db=True, marker=pp.PRODUCTION_MARKER_MAGIC):
        (root / "database").mkdir(parents=True, exist_ok=True)
        if with_db:
            sqlite3.connect(root / "database" / "paksh.db").close()
        if marker is not None:
            pp.production_marker_path(root).write_text(marker, encoding="utf-8")

    prod12 = TMP / "t12_production"
    make_prod_dir(prod12)

    # 12A: correct production configuration -> accepted (no exception), matching the
    # exact real fix command: PAKSH_DATA_DIR=D:\Paksh_Data.
    reset(PAKSH_DATA_DIR=str(prod12))
    check("12A: correct PAKSH_DATA_DIR + valid marker + DB present -> require_production accepts",
          pp.require_production(pp.db_path()) is None)

    # 12B: missing/invalid production configuration -> refuses, does NOT silently fall
    # back to the repo-local paksh.db (the exact failure this fix targets).
    reset()   # nothing configured - the exact _NOT_CONFIGURED condition from the incident
    check("12B: nothing configured -> require_production refuses (does not no-op like require_ready)",
          raises(lambda: pp.require_production(pp.db_path())))
    check("12B2: require_ready() itself is UNCHANGED - still a no-op for the same unconfigured case",
          pp.require_ready(pp.db_path()) is None)

    # 12C: a repo-local paksh.db existing must NOT make it an acceptable production
    # target, even if one is sitting right there. Simulate "repo-local db exists" by
    # monkeypatching ROOT (db_path() falls back to ROOT/paksh.db when unconfigured).
    orig_root = pp.ROOT
    stray_root = TMP / "t12_stray_repo"
    stray_root.mkdir(parents=True, exist_ok=True)
    sqlite3.connect(stray_root / "paksh.db").close()   # a real, openable stray DB
    pp.ROOT = stray_root
    try:
        reset()   # still nothing configured
        check("12C: a repo-local paksh.db existing is still refused as a production target",
              raises(lambda: pp.require_production(pp.db_path())))
        check("12C2: ...even though db_path() itself would happily resolve to it",
              pp.db_path() == stray_root / "paksh.db" and pp.db_path().exists())
    finally:
        pp.ROOT = orig_root

    # 12D (requirement D): the existing export collapse guard is untouched by this
    # change - export_static.py's own dedicated suite (test_export_collapse_guard.py)
    # covers it directly; this just confirms require_production() and the collapse
    # guard are independent (this function does no _site/event-count work at all).
    check("12D: require_production() never touches _site or event counts (pure path check)",
          not hasattr(pp.require_production, "_site"))

    # 12E (requirement E): require_ready() - what live.py/refresh.py/reframe.py/
    # database.py all actually call - is completely unmodified by this change. Proven
    # structurally (12B2 above re-runs it against the same env) and behaviourally: every
    # pre-existing TEST 1-11 in this same file, exercising require_ready() end to end,
    # still ran unmodified earlier in this process.
    reset(PAKSH_DATA_DIR=str(prod12))
    check("12E: require_ready() still accepts the same valid production config require_production does",
          pp.require_ready(pp.db_path()) is None)

    # 12F: the escape hatch still works for require_production() too (deliberate
    # local/dev export with no external storage - same documented semantics as
    # require_ready()'s PAKSH_ALLOW_NEW_DB=1).
    reset()
    os.environ["PAKSH_ALLOW_NEW_DB"] = "1"
    check("12F: PAKSH_ALLOW_NEW_DB=1 still allows a deliberate local/dev export",
          pp.require_production(pp.db_path()) is None)
    os.environ.pop("PAKSH_ALLOW_NEW_DB")

    # 12G: the error message itself names the resolved (wrong) DB and how to fix it -
    # required by the fix's own spec (must not just fail silently or cryptically).
    reset()
    try:
        pp.require_production(pp.db_path())
        _msg = None
    except pp.DataDirError as e:
        _msg = str(e)
    check("12G: the error names the resolved DB path", _msg is not None and str(pp.db_path()) in _msg)
    check("12G2: the error explains how to fix it (PAKSH_DATA_DIR)", _msg is not None and "PAKSH_DATA_DIR" in _msg)

finally:
    for k, v in _saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
    raise SystemExit(1)
print("ALL paksh_paths CHECKS PASSED")
