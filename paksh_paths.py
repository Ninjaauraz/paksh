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


def _read_config_file(path):
    try:
        for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line
    except OSError:
        pass
    return None


def configured_data_dir():
    """The configured data directory as a Path, or None (= the default in-repo layout)."""
    val = (os.environ.get("PAKSH_DATA_DIR") or "").strip()
    if not val:
        cf = config_file()
        val = _read_config_file(cf) if cf else None
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
    d = configured_data_dir()
    return {"configured": d is not None, "data_dir": str(d) if d else None, "db_path": str(db_path()),
            "backup_dir": str(backup_dir()), "config_file": str(config_file()) if config_file() else None}


def storage_status(path=None):
    """Read-only health report for the configured data location (Phase 12B): what it is, whether it is removable, how full,
    and whether anything could silently fall back to the repository copy. Never creates anything."""
    import shutil
    d = configured_data_dir()
    db = db_path()
    out = {"configured": d is not None, "data_dir": str(d) if d else None, "db_path": str(db), "data_dir_exists": bool(d and Path(d).exists()) if d else True,
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
    """Raise DataDirError if a data directory is configured and the database that `path` names is missing.
    Does nothing when no data directory is configured, or when `path` is not the configured database (tests point
    database.DB_PATH at a temp file), or when PAKSH_ALLOW_NEW_DB=1."""
    d = configured_data_dir()
    if d is None or os.environ.get("PAKSH_ALLOW_NEW_DB") == "1":
        return
    target = db_path(d)
    if path is not None and not _same(path, target):
        return
    if not Path(d).exists():
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
        bad = (st["configured"] and not (st["data_dir_exists"] and st["db_exists"])) or st["ambiguous_repo_copy"]
        sys.exit(1 if bad else 0)
    print(json.dumps(describe(), indent=1))
