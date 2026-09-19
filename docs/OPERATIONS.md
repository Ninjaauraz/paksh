# OPERATIONS.md - what watches Paksh, and what to do when it complains

Paksh is a static site published from one Windows PC (see `PAKSH_EXECUTION_STATUS.md`). Nothing
runs on a server, so "monitoring" means: is the PC producing fresh data, is it reaching GitHub/
Vercel, and does the published site look right to a reader.

## What already watches it

| Signal | Tool | Where it shows | Catches |
|---|---|---|---|
| Ingest ran but produced nothing / stale catalogue / commit never pushed | `verify_fresh.py` (`snapshot`, `check`, `deploy-check`) in the scheduled `.bat` chains | `PAKSH_STALE_ALERT.txt` on the Desktop (OneDrive mirrors it to your phone), exit code red in Task Scheduler | dead feeds, failed push (DNS), stuck pipeline |
| A scheduled task never started or crashed | `check_scheduled_health.py`, end of `reframe_scheduled.bat` | `PAKSH_SCHEDULE_ALERT.txt` | machine asleep at 00:30/05:30/07:30 |
| Two jobs writing `paksh.db` at once | `runlocked.py` interlock | `refresh_log.txt` / `reframe_log.txt` ("SKIPPED ... still running") | overlap between `live.py` and scheduled jobs |
| DB copy exists and is intact | `backup_db.py --keep 5` at the end of `reframe_scheduled.bat` (added 2026-09-19) | `backup_log.txt`; a failed backup turns the job's exit code red | data loss (same-disk only - see below) |
| DB copy exists OFF this machine, encrypted | `offsite_backup.py --run` (only once its config file exists; see `docs/BACKUP_AND_RESTORE.md`) | `reframe_log.txt`; a failed upload turns the job's exit code red | disk loss, theft, ransomware |
| **Published site alive and fresh, from outside the PC** | `site_watch.py` via `.github/workflows/site-watch.yml`, every 3h | GitHub emails the repo owner when a run fails | PC off/offline, deploy stuck, empty/broken data, sitemap gone |

Run any check by hand: `py site_watch.py`, `py verify_fresh.py check`, `py check_scheduled_health.py`.

Public freshness marker: `https://paksh.news/data/freshness.json` -> `built_at` (last deployed build),
`newest_event_at` (newest story), `event_count`. All times are UTC.

## Failure classes -> first action

| Alert | Likely cause | First action |
|---|---|---|
| `STALE BUILD` (site_watch) | PC off, no network, push failing, pipeline hung | Check the PC is on; read the tail of `autopush_log.txt` and `refresh_log.txt`; `py verify_fresh.py deploy-check` |
| `STALE NEWS` | feeds returned nothing / ingest failing | `py ingest.py` by hand and read the errors |
| `PUSH FAILED ... LOCAL ONLY` in `autopush_log.txt` | DNS/network outage at push time | Re-run `py safe_autopush.py nightly` once the network is back (nothing is lost; the commit is local) |
| `SKIPPED ... 'live' still running` | `live.py` holds the lock | Expected; only a problem if it repeats and the site goes stale |
| `BACKUP FAILED` | disk full / DB locked | Free disk (C: is ~95% full), then `py backup_db.py --keep 5` |
| `OFFSITE BACKUP FAILED` | credentials/network/bucket problem | `py offsite_backup.py --check`; see `docs/BACKUP_AND_RESTORE.md` |

## Known gaps (deliberately not built)

- **Off-machine backup is built but not yet active.** `offsite_backup.py` (encrypted, verified, restore-tested)
  needs one manual step from Sameer - a bucket + credentials file, see `docs/BACKUP_AND_RESTORE.md`. Until
  then `backups/` protects against corruption but NOT disk loss. About 10 GB of old unmanaged
  `paksh.db.bak*` / `paksh.db.pre_phase*` files sit in the project root; nothing deletes them automatically.
- **Single publisher.** One PC ingests, analyses, exports and pushes. If it is down the site keeps
  serving the last build (it does not break); `site_watch.py` will report it as stale.
- **No error reporting from readers' browsers.** Client-side JS errors are not collected. Vercel Web
  Analytics (consent-gated, cookieless) is the only browser-side signal.
