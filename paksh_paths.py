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
PRODUCTION_MARKER_NAME = ".paksh-production"
PRODUCTION_MARKER_MAGIC = "paksh-production-data-root"


class DataDirError(RuntimeError):
    """The configured Paksh data location is not usable. Never swallowed by callers: fail loudly."""


def config_file():
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / "Paksh" / CONFIG_NAME if base else None


_NO_ENV = "no_localappdata"          # LOCALAPPDATA itself unavailable - cannot even locate the config file
_UNREADABLE = "config_unreadable"    # config file exists but could not be read (permissions, I/O error, ...)
_NOT_CONFIGURED = "not_configured"   # environment checked fine; genuinely nothing configured here
_CONFIGURED_ENV = "configured_env"   # PAKSH_DATA_DIR env var - explicit, authoritative, PRODUCTION
_CONFIGURED_FILE = "configured_file"  # data_dir.txt - legitimate local/dev configuration
_CONFIGURED = (_CONFIGURED_ENV, _CONFIGURED_FILE)


def _resolve_config():
    """How the configured data directory would be determined, distinguishing FOUR
    things, not two:
      - _CONFIGURED_ENV: PAKSH_DATA_DIR was set explicitly. This is now the
        AUTHORITATIVE, production signal (see require_ready()'s production-marker
        check below) - it is never overridden by LOCALAPPDATA/data_dir.txt, and
        LOCALAPPDATA is not even consulted when it's present.
      - _CONFIGURED_FILE: no env var, but %LOCALAPPDATA%\\Paksh\\data_dir.txt names
        one. Legitimate local/dev configuration - preserved exactly as before.
      - _NOT_CONFIGURED: checked (env var absent, LOCALAPPDATA readable, no config
        file or an empty one) and there's genuinely nothing configured - the normal,
        fine default for a fresh checkout/CI/dev machine.
      - _NO_ENV / _UNREADABLE: could NOT check at all (LOCALAPPDATA itself missing,
        or its config file exists but could not be read). configured_data_dir()
        collapses all three "nothing found" cases to None because most callers only
        care whether something is configured. require_ready() is the one caller
        that must NOT make that collapse: silently treating "could not check" the
        same as "nothing configured" is exactly how a production run can fall back
        to, and silently create, a repo-local paksh.db while a real external
        database sits unused elsewhere (2026-09-22 incident).
      - A SECOND, later incident (2026-09-23) showed LOCALAPPDATA can also resolve
        to a non-empty but WRONG value in one process's environment - readable, but
        pointing somewhere data_dir.txt was never set up, which is genuinely
        indistinguishable from _NOT_CONFIGURED by this function alone. That is
        exactly why production no longer depends on this file-based path at all:
        it must set PAKSH_DATA_DIR explicitly (see live.py, refresh_scheduled.bat,
        reframe_scheduled.bat), which _CONFIGURED_ENV always wins over regardless
        of whatever LOCALAPPDATA happens to resolve to in that process.
    Returns (status, value_or_None)."""
    env_val = (os.environ.get("PAKSH_DATA_DIR") or "").strip()
    if env_val:
        return _CONFIGURED_ENV, env_val
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
            return _CONFIGURED_FILE, line
    return _NOT_CONFIGURED, None


def configured_data_dir():
    """The configured data directory as a Path, or None (= the default in-repo layout).
    See _resolve_config() for the finer-grained status require_ready() actually needs."""
    _, val = _resolve_config()
    return Path(val) if val else None


def production_marker_path(data_dir):
    """Where the production identity marker lives inside a data directory. Its
    presence (with the expected content) is what lets an explicit PAKSH_DATA_DIR
    be trusted as the real production root rather than some other, merely
    non-empty, directory someone pointed the variable at by mistake."""
    return Path(data_dir) / PRODUCTION_MARKER_NAME


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


def _require_production_marker(d):
    """PAKSH_DATA_DIR is the explicit, authoritative production signal - but 'a
    directory was named' is not the same as 'this is really the validated
    production root'. Require a marker file with known content inside it, created
    once (see this module's docstring / the marker created at D:\\Paksh_Data\\
    .paksh-production) by whoever actually set up the production data directory.
    This is what stops a wrong-but-non-empty PAKSH_DATA_DIR from silently passing
    every other check (2026-09-23 incident: a non-empty LOCALAPPDATA resolved
    somewhere data_dir.txt was never set up, which no check before this one could
    tell apart from a legitimately unconfigured machine)."""
    marker = production_marker_path(d)
    if not marker.exists():
        raise DataDirError(
            f"PAKSH_DATA_DIR={d} is set (explicit production mode) but its production "
            f"marker {marker} is missing. An explicit PAKSH_DATA_DIR alone is not enough "
            f"proof this is really the production data root - refusing to guess. Create "
            f"the marker (see paksh_paths.production_marker_path / PRODUCTION_MARKER_MAGIC) "
            f"if {d} really is the validated production data directory.")
    try:
        content = marker.read_text(encoding="utf-8").strip()
    except OSError as e:
        raise DataDirError(f"PAKSH_DATA_DIR={d}'s production marker {marker} could not be "
                            f"read ({e}). Refusing to treat this as validated production.")
    if content != PRODUCTION_MARKER_MAGIC:
        raise DataDirError(
            f"PAKSH_DATA_DIR={d}'s production marker {marker} exists but its content does "
            f"not match what this Paksh version expects. Refusing to treat an unverified "
            f"directory as production.")


def require_ready(path=None):
    """Raise DataDirError if:
      (a) an external data directory IS configured and the database `path` names is
          missing (the original guard - card unplugged, drive letter changed), or
      (b) whether one is configured cannot be determined AT ALL - LOCALAPPDATA is
          unavailable in this process's environment, or its config file exists but
          could not be read (2026-09-22 incident), or
      (c) PAKSH_DATA_DIR is set (explicit production mode) but its production
          marker is missing or invalid (2026-09-23 incident - a non-empty but
          WRONG LOCALAPPDATA got treated as "legitimately unconfigured", which
          (b) alone cannot catch; explicit PAKSH_DATA_DIR + a validated marker is
          the fix that no longer depends on LOCALAPPDATA at all for production).
    Does nothing when PAKSH_ALLOW_NEW_DB=1 (the explicit, deliberate opt-in for a
    fresh local/dev/test run with no external storage configured), when the
    environment genuinely has nothing configured via the LOCALAPPDATA/file path
    (today's normal in-repo layout - cases (b)/(c) above are NOT this), or when
    `path` is not the configured database (tests/temp DBs point database.DB_PATH
    elsewhere)."""
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
    if status == _CONFIGURED_ENV:
        _require_production_marker(d)
    if not target.exists():
        raise DataDirError(
            f"Paksh data directory {d} exists but the database {target} is missing. Refusing to create an empty database. "
            f"Restore it from {backup_dir(d)}, or set PAKSH_ALLOW_NEW_DB=1 to create a new one on purpose.")


def require_production(path=None):
    """Stricter than require_ready(), for entry points that PUBLISH (export_static.py) -
    where silently falling back to the repo-local paksh.db must be IMPOSSIBLE, not just
    unlikely. 2026-09-24 incident: a manual export run, in a process environment where
    the LOCALAPPDATA config file happened not to resolve, saw config_resolution =
    _NOT_CONFIGURED - which require_ready() correctly treats as "a legitimately
    unconfigured dev machine" and allows. For most pipeline scripts that's the right,
    dev-friendly default. An export that PUBLISHES cannot take that risk: it must have
    positive, verified proof of the real production data directory, never "nothing said
    otherwise". So this function additionally:
      - treats _NOT_CONFIGURED as a FAILURE (require_ready() does not - that is the one
        deliberate difference between the two functions);
      - requires the .paksh-production marker unconditionally, whether the directory was
        found via PAKSH_DATA_DIR or via data_dir.txt (require_ready() only checks the
        marker for the PAKSH_DATA_DIR/_CONFIGURED_ENV case).
    Raises DataDirError naming the expected production DB, the DB that would actually be
    opened, and how to set PAKSH_DATA_DIR. Does nothing when PAKSH_ALLOW_NEW_DB=1 - the
    same documented escape hatch require_ready() already uses for "deliberately a fresh
    local/dev/test export with no external storage configured"."""
    if os.environ.get("PAKSH_ALLOW_NEW_DB") == "1":
        return
    resolved = path if path is not None else db_path()
    status, val = _resolve_config()
    if status not in _CONFIGURED:
        raise DataDirError(
            f"Refusing to export: no production data directory is configured in this "
            f"process (config_resolution={status}). A publishing export must never "
            f"silently fall back to the repo-local database.\n"
            f"  expected production DB: database/{DB_NAME} under an explicitly configured "
            f"production data directory\n"
            f"  resolved DB (what this run would actually open): {resolved}\n"
            f"  fix: set PAKSH_DATA_DIR to the real production data directory in THIS "
            f"shell before exporting, e.g. (PowerShell) "
            f"$env:PAKSH_DATA_DIR=\"D:\\Paksh_Data\"\n"
            f"  (or set PAKSH_ALLOW_NEW_DB=1 if this is a deliberate local/dev export "
            f"with no external storage configured)")
    d = Path(val)
    if not d.exists():
        raise DataDirError(f"Refusing to export: configured data directory {d} does not exist. "
                            f"Is the drive connected?")
    _require_production_marker(d)          # required here regardless of how `d` was found
    target = db_path(d)
    if not target.exists():
        raise DataDirError(f"Refusing to export: configured data directory {d} exists but its "
                            f"database {target} is missing.")
    if not _same(resolved, target):
        raise DataDirError(
            f"Refusing to export: this process would open a database that does not match "
            f"the verified production database.\n"
            f"  expected production DB: {target}\n"
            f"  resolved DB (what this run would actually open): {resolved}\n"
            f"  fix: set PAKSH_DATA_DIR=\"{d}\" before exporting so the whole process "
            f"resolves the same database throughout.")


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
