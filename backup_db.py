"""
backup_db.py - Phase 25B-B: a real, scheduled, SQLite-consistent backup of
paksh.db, replacing the prior practice of ad-hoc manual copies made by
individual work sessions before a risky operation.

    py backup_db.py              # take one backup, verify it, apply retention
    py backup_db.py --keep 14    # override retention (default: keep last 14)
    py backup_db.py --no-verify  # skip the post-backup integrity_check (not
                                  # recommended - only for a quick manual run)

WHY sqlite3's native .backup() and not a raw file copy: paksh.db runs in WAL
mode (see database.py's PRAGMA journal_mode=WAL). A plain file copy of
paksh.db alone can miss committed data still sitting in the paksh.db-wal
sidecar file, producing a backup that LOOKS complete but is actually stale or
inconsistent. sqlite3.Connection.backup() is SQLite's own hot-backup API: it
walks the source page-by-page under SQLite's own locking, correctly folding
in the WAL, and produces a single self-contained, immediately-valid database
file - this is the officially recommended way to back up a live SQLite
database, and it is safe to run WHILE other processes are writing paksh.db
(concurrent writers may cause a transient busy-retry inside backup(), which
Python's binding already handles).

No pipeline lock is taken for this reason: unlike a raw copy, backup() does
not need exclusive access to produce a correct result, so coupling it to
.pipeline.lock (see runlocked.py) would only add unnecessary contention with
zero correctness benefit. It is deliberately NOT wired into runlocked.py.

Every backup is:
  1. taken via the native backup() API into backups/paksh_backup_<UTC
     timestamp>.db
  2. immediately checked with PRAGMA integrity_check on the fresh copy
  3. logged (success or failure) to backup_log.txt, matching the project's
     existing refresh_log.txt/reframe_log.txt/autopush_log.txt convention
  4. followed by retention: backups older than --keep runs (default 14) that
     match THIS script's own naming convention are deleted. Pre-existing
     ad-hoc backups (anything not named paksh_backup_<timestamp>.db) are
     NEVER touched by retention - they are a different, unmanaged population
     this script does not own.

A failed or corrupt-on-verify backup is left on disk (for forensic
inspection) but is EXCLUDED from retention's "most recent good backup" count
and clearly marked FAILED in the log, so an operator scanning the log for the
latest restorable backup does not pick a bad one by accident.

See RECOVERY.md for the restore procedure.
"""
import argparse
import datetime
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DB_PATH = ROOT / "paksh.db"
BACKUP_DIR = ROOT / "backups"
LOG_PATH = ROOT / "backup_log.txt"
NAME_PREFIX = "paksh_backup_"
NAME_SUFFIX = ".db"


def _stamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log(line: str):
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{_stamp()}] {line}\n")
    except OSError:
        pass   # logging must never be the reason a backup run fails


def _backup_name(ts: datetime.datetime) -> str:
    return f"{NAME_PREFIX}{ts.strftime('%Y%m%d_%H%M%S')}{NAME_SUFFIX}"


def take_backup() -> Path:
    """Runs sqlite3's native hot-backup API. Returns the path to the new file.
    Raises on failure (caller decides what to do)."""
    BACKUP_DIR.mkdir(exist_ok=True)
    dest = BACKUP_DIR / _backup_name(datetime.datetime.now())
    src_conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=30)
    dst_conn = sqlite3.connect(dest)
    try:
        src_conn.backup(dst_conn)
        # The destination inherits WAL mode from the copied page content, which
        # would otherwise leave empty-but-present -wal/-shm sidecar files next
        # to it. Switch it to a plain rollback journal and checkpoint, so the
        # backup is one clean, self-contained file - simpler to restore (a
        # single file to copy, nothing to remember to bring along) and no
        # different in content, since there was nothing pending in the WAL.
        dst_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        dst_conn.execute("PRAGMA journal_mode=DELETE")
    finally:
        dst_conn.close()
        src_conn.close()
    for sidecar_suffix in ("-wal", "-shm"):
        sidecar = dest.with_name(dest.name + sidecar_suffix)
        if sidecar.exists():
            try:
                sidecar.unlink()
            except OSError:
                pass
    return dest


def verify_backup(path: Path) -> tuple[bool, str]:
    """Opens the fresh backup read-only and runs PRAGMA integrity_check plus a
    minimal application-level sanity check (the tables Paksh actually reads
    exist and are non-empty where a live DB would never be empty)."""
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
        c = conn.cursor()
        result = c.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            return False, f"integrity_check returned: {result}"
        events = c.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        articles = c.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        if events == 0 or articles == 0:
            return False, f"suspiciously empty (events={events}, articles={articles})"
        conn.close()
        return True, f"ok (events={events}, articles={articles})"
    except Exception as e:
        return False, f"verify raised: {e}"


_GOOD_BACKUP_RE = re.compile(r"^" + re.escape(NAME_PREFIX) + r"\d{8}_\d{6}" + re.escape(NAME_SUFFIX) + r"$")


def apply_retention(keep: int):
    """Deletes backups OLDER than the newest `keep`, matching ONLY this
    script's own successful-backup naming convention (exactly
    paksh_backup_YYYYMMDD_HHMMSS.db - a plain glob of "paksh_backup_*.db"
    would also match a paksh_backup_<ts>.FAILED.db marker, which must never
    be silently deleted by retention; a strict regex avoids that). Any other
    file in backups/ (e.g. the pre-existing ad-hoc
    paksh_pre_recount_migrate_...db, or a .FAILED.db marker) is a different,
    unmanaged population and is never touched here."""
    ours = sorted(
        (p for p in BACKUP_DIR.iterdir() if p.is_file() and _GOOD_BACKUP_RE.match(p.name)),
        key=lambda p: p.name, reverse=True,   # timestamp is in the filename -> lexicographic = chronological
    )
    for old in ours[keep:]:
        try:
            old.unlink()
            _log(f"retention: removed {old.name}")
        except OSError as e:
            _log(f"retention: could not remove {old.name}: {e}")


def main():
    ap = argparse.ArgumentParser(description="Take a verified, SQLite-consistent backup of paksh.db.")
    ap.add_argument("--keep", type=int, default=14,
                     help="how many of THIS script's own backups to retain (default 14)")
    ap.add_argument("--no-verify", action="store_true", help="skip the post-backup integrity check")
    args = ap.parse_args()

    if not DB_PATH.exists():
        _log(f"BACKUP FAILED - {DB_PATH} does not exist.")
        sys.exit(1)

    started = datetime.datetime.now()
    try:
        dest = take_backup()
    except Exception as e:
        _log(f"BACKUP FAILED - backup() raised: {e}")
        sys.exit(1)

    size_mb = dest.stat().st_size / (1024 * 1024)
    elapsed = (datetime.datetime.now() - started).total_seconds()

    if args.no_verify:
        _log(f"BACKUP OK (unverified) - {dest.name} ({size_mb:.0f} MB, {elapsed:.0f}s)")
    else:
        ok, detail = verify_backup(dest)
        if ok:
            _log(f"BACKUP OK - {dest.name} ({size_mb:.0f} MB, {elapsed:.0f}s) - verify: {detail}")
        else:
            # Leave the bad file on disk for forensic inspection, but rename it so
            # retention's glob (which only matches the exact good-backup pattern)
            # and any human scanning backups/ for "the latest restorable copy"
            # never mistake it for a valid one.
            failed_path = dest.with_name(dest.name.replace(NAME_SUFFIX, ".FAILED" + NAME_SUFFIX))
            try:
                dest.rename(failed_path)
            except OSError:
                failed_path = dest
            _log(f"BACKUP FAILED VERIFICATION - {failed_path.name} - {detail}")
            sys.exit(1)

    apply_retention(args.keep)
    sys.exit(0)


if __name__ == "__main__":
    main()
