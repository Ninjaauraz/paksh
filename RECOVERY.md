# Paksh — Database Recovery Runbook

Practical steps only. For the full reasoning behind the backup design, see
the docstring at the top of `backup_db.py`.

## How do I know the DB is damaged?

- Any pipeline script (`refresh.py`, `analyze.py`, `export_static.py`, ...)
  fails with a SQLite error mentioning "malformed", "corrupt", or "disk
  image" — not a normal `sqlite3.OperationalError: database is locked`
  (that's just contention, not corruption; it resolves on its own).
- Run a direct check:
  ```
  py -c "import sqlite3; print(sqlite3.connect('file:paksh.db?mode=ro', uri=True).execute('PRAGMA integrity_check').fetchone())"
  ```
  Anything other than `('ok',)` means real corruption.

## Where is the latest valid backup?

```
py -c "
import pathlib
p = sorted(pathlib.Path('backups').glob('paksh_backup_*.db'), reverse=True)
print(p[0] if p else 'no managed backups found')
"
```
This lists only backups `backup_db.py` itself created and verified (name
prefix `paksh_backup_`). A file ending in `.FAILED.db` failed its own
integrity check when it was taken — never restore from one of those; look at
the next-newest good one instead. `backup_log.txt` has the full history,
including which runs succeeded/failed and why.

Older, unmanaged ad-hoc backups (files like `paksh.db.pre_phase24b_backup`
in the repo root, or `backups/paksh_pre_recount_migrate_*.db`) still exist
from before this mechanism was built. They were never verified by this
script but can be used as a last resort if every managed backup is also
unusable — check them the same way (Step 1 below) before trusting one.

## How do I restore it?

**Never overwrite `paksh.db` directly without first validating the backup on
a disposable copy** — see the next section. Once validated:

1. Stop anything currently running against the DB (any `live.py` you started
   manually; the scheduled Task Scheduler jobs will simply skip via the
   pipeline lock if `runlocked.py` is in a valid state, but if the lock file
   looks stuck, see `runlocked.py`'s stale-lock reclaim — it self-heals once
   the holder's PID is confirmed dead, no manual deletion needed in the
   normal case).
2. Move the damaged file aside rather than deleting it (in case forensic
   inspection is useful later):
   ```
   move paksh.db paksh.db.corrupt_<date>
   ```
3. Copy the chosen backup into place:
   ```
   copy backups\paksh_backup_<timestamp>.db paksh.db
   ```
4. Continue to validation below before resuming the pipeline.

## How do I validate it (before AND after restoring)?

Copy the candidate backup to a **disposable** path outside the repo first —
never validate by pointing production tools at a file you haven't confirmed
yet:

```
copy backups\paksh_backup_<timestamp>.db %TEMP%\restore_check.db
py -c "
import sqlite3
c = sqlite3.connect('file:%TEMP%/restore_check.db?mode=ro', uri=True)
print(c.execute('PRAGMA integrity_check').fetchone())
print('events:', c.execute('SELECT COUNT(*) FROM events').fetchone()[0])
print('articles:', c.execute('SELECT COUNT(*) FROM articles').fetchone()[0])
"
```
Expect `('ok',)` and non-zero, plausible counts (compare against the numbers
in `backup_log.txt` for that backup's own run). Once satisfied, perform the
copy-into-place in the previous section, then re-run the same check against
the now-live `paksh.db` to confirm the copy itself wasn't corrupted in
transit.

## How do I safely restart the pipeline?

- Confirm `.pipeline.lock` doesn't exist (or, if it does, that the PID it
  names is not actually running — `runlocked.py`'s own stale-lock logic
  handles this automatically the next time any job tries to acquire it, so
  in the ordinary case you don't need to touch the lock file at all).
- Restart `live.py` manually if that's how you normally run it, or simply
  wait for the next scheduled Task Scheduler run (`Paksh  refresh` 00:30,
  `Paksh nightly refresh` 05:30, `Paksh reframe` 07:30).
- Watch the first cycle's output (or `refresh_log.txt`/`reframe_log.txt`)
  to confirm it completes normally against the restored DB.

## What data may be lost?

Everything ingested/generated between the backup's timestamp and the moment
of damage. `backup_log.txt` records exactly when each backup was taken and
its counts at that time, so you can state precisely how much was lost (e.g.
"restored from the 06:00 backup; anything ingested between 06:00 and the
crash is gone and will re-appear naturally once the next ingest cycle
re-pulls current articles — only the analysis/clustering work already done
on that window's older articles by cluster.py/analyze.py is truly lost").

## How do I verify production after recovery?

1. `py -c "import sqlite3; print(sqlite3.connect('file:paksh.db?mode=ro', uri=True).execute('PRAGMA integrity_check').fetchone())"` → `('ok',)`
2. Run one manual `py export_static.py` and confirm it completes without error.
3. Spot-check the live site (`paksh.vercel.app`) still loads the homepage and
   a known story after the next scheduled/manual deploy.
4. Confirm the pipeline resumes producing new content on its normal cadence
   (new events appearing, `backup_log.txt`/`refresh_log.txt` advancing).

## Backup schedule and retention (current state)

`backup_db.py` is implemented, tested, and produces verified backups into
`backups/paksh_backup_<UTC timestamp>.db`, retaining the most recent 14 of
its own backups by default (`--keep N` to override) and never touching any
pre-existing ad-hoc backup file.

**It is not yet wired into Windows Task Scheduler.** Phase 25B intentionally
stopped short of registering a new scheduled task autonomously (see the
Phase 25B final report's note on this). To schedule it, add one line to an
existing scheduled job or register a new one manually, e.g. via the same
mechanism already used for `Paksh  refresh` / `Paksh nightly refresh` /
`Paksh reframe`:

```
schtasks /create /tn "Paksh backup" /tr "cmd /c cd /d C:\paksh_project\paksh && py backup_db.py >> backup_log.txt 2>&1" /sc daily /st 04:45
```
(04:45 is chosen only as an example — before the 05:30 nightly refresh, so a
backup exists from before each day's mutating run. Adjust as preferred.)

## What this backup mechanism does NOT protect against

All managed and ad-hoc backups currently live on the **same physical disk**
as `paksh.db`. None of this protects against disk/hardware failure, theft,
or the machine itself being lost — only against logical corruption,
accidental deletion, or a bad migration/cleanup run. An off-machine copy
(cloud storage, another device) is a real gap; deliberately out of scope for
this phase (see the Phase 25B final report).
