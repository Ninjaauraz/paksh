"""
test_paksh_paths.py - deterministic tests for paksh_paths.py (where paksh.db and its backups live).

Runs only against temp directories; never touches the real paksh.db, the real %LOCALAPPDATA% config, or D:.

Run:  py test_paksh_paths.py
"""
import os
import sqlite3
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
