"""
paksh_paths.py - where Paksh's PERSISTENT data (the SQLite database and its backups) lives.

DEFAULT = TODAY'S LAYOUT: `<repo>/paksh.db` and `<repo>/backups/`. Importing or committing this module changes
nothing by itself. A machine opts in to another location with ONE local setting that is never committed:

    1. environment variable PAKSH_DATA_DIR, or
    2. the first non-comment line of  %LOCALAPPDATA%\\Paksh\\data_dir.txt   (e.g.  D:\\Paksh_Data)

(A file is the reliable channel: Task Scheduler jobs and already-open terminals do not see a freshly `setx`'d variable -
the same reason offsite_backup keeps its settings in %LOCALAPPDATA%\\Paksh\\offsite_backup.env.)

When a data directory is configured the layout inside it is

    <data dir>/database/paksh.db         the live database (its -wal/-shm sidecars sit beside it)
    <data dir>/backups/daily/            backup_db.py output (paksh_backup_<timestamp>.db)
    <data dir>/backups/archive/          one-off / pre-migration backups

Safety rule (the reason this is a module and not a constant): if a data directory IS configured but the database file is
not there - the card is unplugged, it came back under another drive letter, the folder was moved - the process STOPS with
a clear error. It must never fall back to `<repo>/paksh.db` (that would fork the data into two databases) and sqlite3 must
never be allowed to silently create a fresh empty database at the configured path (the pipeline would then ingest into,
analyse and PUBLISH from an empty corpus). Set PAKSH_ALLOW_NEW_DB=1 to deliberately create a new database.

Small files that must keep working when the data drive is absent stay in the repo: `.pipeline.lock`, the *_log.txt files,
`.pipeline_baseline.json`, secrets.
"""
import os
from pathlib import Path

ROOT = Path(__file__).parent
CONFIG_NAME = "data_dir.txt"
DB_NAME = "paksh.db"


class DataDirError(RuntimeError):
    """The configured Paksh data location is not usable. Never swallowed by callers: fail loudly."""


def config_file():
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / "Paksh" / CONFIG_NAME if base else None


_NO_ENV = "no_localappdata"          # LOCALAPPDATA itself unavailable - cannot even locate the config file
_UNREADABLE = "config_unreadable"    # config file exists but could not be read (permissions, I/O error, ...)
_NOT_CONFIGURED = "not_configured"   # environment checked fine; genuinely nothing configured here
_CONFIGURED = "configured"           # a data dir value was found (env var or config file)


def _resolve_config():
    """How the configured data directory would be determined, distinguishing
    'checked and there's genuinely nothing configured' (_NOT_CONFIGURED - the normal,
    fine default for a fresh checkout/CI/dev machine) from 'could not check at all'
    (_NO_ENV / _UNREADABLE). configured_data_dir() collapses all three "nothing found"
    cases to None because most callers only care whether something is configured.
    require_ready() is the one caller that must NOT make that collapse: silently
    treating "could not check" the same as "nothing configured" is exactly how a
    production run can fall back to, and silently create, a repo-local paksh.db while
    a real external database sits unused elsewhere (2026-09-22 incident - both of one
    day's live.py cycles forked into a fresh repo-local paksh.db this way). Returns
    (status, value_or_None)."""
    env_val = (os.environ.get("PAKSH_DATA_DIR") or "").strip()
    if env_val:
        return _CONFIGURED, env_val
    cf = config_file()
    if cf is None:
        return _NO_ENV, None
    if not cf.exists():
        return _NOT_CONFIGURED, None
    try:
        text = cf.read_text(encoding="utf-8-sig")
    except OSError:
        return _UNREADABLE, None
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return _CONFIGURED, line
    return _NOT_CONFIGURED, None


def configured_data_dir():
    """The configured data directory as a Path, or None (= the default in-repo layout).
    See _resolve_config() for the finer-grained status require_ready() actually needs."""
    _, val = _resolve_config()
    return Path(val) if val else None


def db_path(data_dir=None):
    d = configured_data_dir() if data_dir is None else data_dir
    return (Path(d) / "database" / DB_NAME) if d else (ROOT / DB_NAME)


def backup_dir(data_dir=None):
    d = configured_data_dir() if data_dir is None else data_dir
    return (Path(d) / "backups" / "daily") if d else (ROOT / "backups")


def archive_dir(data_dir=None):
    d = configured_data_dir() if data_dir is None else data_dir
    return (Path(d) / "backups" / "archive") if d else (ROOT / "backups")


def describe():
    status, val = _resolve_config()
    d = Path(val) if val else None
    return {"configured": d is not None, "data_dir": str(d) if d else None, "db_path": str(db_path()),
            "backup_dir": str(backup_dir()), "config_file": str(config_file()) if config_file() else None,
            "config_resolution": status}


def storage_status(path=None):
    """Read-only health report for the configured data location (Phase 12B): what it is, whether it is removable, how full,
    and whether anything could silently fall back to the repository copy. Never creates anything."""
    import shutil
    status, val = _resolve_config()
    d = Path(val) if val else None
    db = db_path()
    out = {"configured": d is not None, "config_resolution": status,
           "config_could_not_be_determined": status in (_NO_ENV, _UNREADABLE),
           "data_dir": str(d) if d else None, "db_path": str(db), "data_dir_exists": bool(d and Path(d).exists()) if d else True,
           "db_exists": db.exists(), "db_bytes": db.stat().st_size if db.exists() else None,
           "repo_db_present": (ROOT / DB_NAME).exists(), "filesystem": None, "removable": None, "free_bytes": None}
    root = os.path.splitdrive(str(d if d else ROOT))[0] + "\\"
    try:
        out["free_bytes"] = shutil.disk_usage(str(d) if d and Path(d).exists() else str(ROOT)).free
    except OSError:
        pass
    try:
        import ctypes
        k = ctypes.windll.kernel32
        out["removable"] = k.GetDriveTypeW(root) == 2                       # DRIVE_REMOVABLE
        fs = ctypes.create_unicode_buffer(32)
        if k.GetVolumeInformationW(root, None, 0, None, None, None, fs, 32):
            out["filesystem"] = fs.value
    except Exception:
        pass
    # The guard (require_ready) stops every process when a configured location is unavailable. The one situation in which a fallback
    # could be mistaken for the live database is a stale copy of paksh.db sitting next to the code while a data dir is configured.
    out["guard_active"] = d is not None
    out["ambiguous_repo_copy"] = bool(d is not None and out["repo_db_present"])
    return out


def _same(a, b):
    return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))


def require_ready(path=None):
    """Raise DataDirError if:
      (a) an external data directory IS configured and the database `path` names is
          missing (the original guard - card unplugged, drive letter changed), or
      (b) whether one is configured cannot be determined AT ALL - LOCALAPPDATA is
          unavailable in this process's environment, or its config file exists but
          could not be read. Silently treating (b) the same as "nothing configured"
          is exactly how a production run falls back to, and sqlite3 silently
          CREATES, a repo-local paksh.db while the real external database sits
          untouched elsewhere - forking production data with no error at all
          (2026-09-22 incident: both of one day's live.py cycles did exactly this).
    Does nothing when PAKSH_ALLOW_NEW_DB=1 (the explicit, deliberate opt-in for a
    fresh local/dev/test run with no external storage configured), when the
    environment genuinely has nothing configured (today's normal in-repo layout -
    case (b) above is NOT this), or when `path` is not the configured database
    (tests/temp DBs point database.DB_PATH elsewhere)."""
    if os.environ.get("PAKSH_ALLOW_NEW_DB") == "1":
        return
    status, val = _resolve_config()
    if status in (_NO_ENV, _UNREADABLE):
        raise DataDirError(
            f"Cannot determine whether an external Paksh data directory is configured "
            f"({status}): %LOCALAPPDATA%\\Paksh\\{CONFIG_NAME} could not be checked. "
            f"Refusing to guess - silently defaulting here is exactly how a production "
            f"run can fork into a repo-local paksh.db while the real database sits "
            f"untouched. Set PAKSH_ALLOW_NEW_DB=1 if this is deliberately a fresh local "
            f"run with no external storage configured.")
    if status == _NOT_CONFIGURED:
        return
    d = Path(val)
    target = db_path(d)
    if path is not None and not _same(path, target):
        return
    if not d.exists():
        raise DataDirError(
            f"Paksh data directory {d} is configured (from {'PAKSH_DATA_DIR' if os.environ.get('PAKSH_DATA_DIR') else config_file()}) "
            f"but does not exist. Is the SD card / drive connected, and does it still have the same drive letter? "
            f"Refusing to fall back to another database or to create an empty one.")
    if not target.exists():
        raise DataDirError(
            f"Paksh data directory {d} exists but the database {target} is missing. Refusing to create an empty database. "
            f"Restore it from {backup_dir(d)}, or set PAKSH_ALLOW_NEW_DB=1 to create a new one on purpose.")


if __name__ == "__main__":
    import json
    import sys
    if "--check" in sys.argv:
        st = storage_status()
        print(json.dumps(st, indent=1))
        bad = (st["configured"] and not (st["data_dir_exists"] and st["db_exists"])) or st["ambiguous_repo_copy"] \
            or st["config_could_not_be_determined"]
        sys.exit(1 if bad else 0)
    print(json.dumps(describe(), indent=1))
