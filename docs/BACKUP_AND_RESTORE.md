# BACKUP_AND_RESTORE.md - protecting paksh.db

`paksh.db` (about 2.3 GB, ~600k articles, ~19.6k stories, months of history) is the one thing a copied
website cannot reproduce, and it lives on one disk. This describes the two backup layers, the one setup
step that needs your accounts, retention, and how to restore.

## The two layers

| Layer | Tool | Where | Protects against | Does NOT protect against |
|---|---|---|---|---|
| 1. Local rolling | `backup_db.py --keep 5` (daily, end of `reframe_scheduled.bat`) | `backups/` on this PC | corruption, a bad migration, an accidental delete | disk failure, theft, fire, ransomware on this PC |
| 2. **Off-machine, encrypted** | `offsite_backup.py --run` (same daily job, only once configured) | S3-compatible object storage (Cloudflare R2 or Backblaze B2 recommended) | everything layer 1 does not | loss of the passphrase (by design) |

Layer 2 copies the **newest verified layer-1 backup** (taken with SQLite's online-backup API, so it is
consistent even while other jobs write). It is compressed (gzip), then encrypted on this machine with
AES-256-GCM before any byte is uploaded; the provider only stores ciphertext.

## Status

- Layer 1: **scheduled** (added 2026-09-19).
- Layer 2: **implemented and tested, NOT active** - it needs your storage account. Until you complete the
  manual step below nothing is uploaded and the scheduled job simply skips it.

## The one manual step (needs your accounts)

1. **Create a bucket** - Cloudflare R2 (10 GB free, no egress fee; a 2.3 GB DB compresses to ~1.3 GB per
   copy) or Backblaze B2 (about $6 per TB-month). Create an **API token limited to that one bucket** with
   read + write (never an account-wide key).
2. **Create the config file** `%LOCALAPPDATA%\Paksh\offsite_backup.env` (that is
   `C:\Users\<you>\AppData\Local\Paksh\offsite_backup.env`). It must be **outside the repository**; the tool
   refuses a config inside it. Contents:
   ```
   S3_ENDPOINT=https://<accountid>.r2.cloudflarestorage.com
   S3_BUCKET=paksh-backups
   S3_REGION=auto
   S3_ACCESS_KEY_ID=<token access key id>
   S3_SECRET_ACCESS_KEY=<token secret>
   BACKUP_PASSPHRASE=<a long random passphrase, 20+ characters>
   KEEP=7
   ```
   For Backblaze B2 use `S3_ENDPOINT=https://s3.<region>.backblazeb2.com` and that region (e.g. `us-west-004`).
3. **Save a copy of `BACKUP_PASSPHRASE` in your password manager.** If it is lost the backups cannot be
   decrypted by anyone, including you. There is no recovery path; that is what makes them private.
4. **Verify, in this order:**
   ```
   py offsite_backup.py --check          # config + key + a 32-byte test object; uploads no data
   py offsite_backup.py --run            # first real upload (~1.3 GB)
   py offsite_backup.py --restore-test   # downloads it back, decrypts, integrity_check, compares counts
   ```
   `--restore-test` must print `restore-test PASSED ... integrity=ok events=N/N articles=M/M`.

From then on the 07:30 job uploads automatically (`if exist` on the config file), and a failed upload turns
that job's exit code red like every other check.

## Retention

- **Local:** newest 5 (`backup_db.py --keep 5`, ~11.5 GB). C: is ~95% full; do not raise this.
- **Off-machine:** newest `KEEP` (default **7**) - about 9 GB at today's size, inside R2's 10 GB free tier.
  Only objects named `paksh_YYYYMMDD_HHMMSS.db.gz.enc` are ever deleted, and never the one just uploaded.
  At R2 rates one extra GB costs about $0.015/month, so raising `KEEP` is cheap if the DB stays this size.
- Not automated: monthly/yearly archives and the ~10 GB of old unmanaged `paksh.db.bak*` /
  `paksh.db.pre_phase*` files in the project root (archive them off-machine yourself if you want them).

## Restoring

**Never restore over the live `paksh.db`.** Restore to a new file, inspect it, then swap deliberately.

1. Stop `live.py` and any scheduled job (they write `paksh.db`).
2. `py offsite_backup.py --list` - pick the object (newest is last).
3. `py offsite_backup.py --restore paksh_20260919_151656.db.gz.enc --to D:\restore\paksh.db`
   It downloads, decrypts, decompresses, runs `PRAGMA integrity_check` and compares the row counts recorded
   at upload time. It refuses to overwrite an existing file.
4. Move the current `paksh.db*` (including `-wal`/`-shm`) aside, copy the restored file in as `paksh.db`, and run
   `py export_static.py` to confirm the site builds.
5. **Restoring on a new PC:** install Python + `pip install -r requirements.txt`, get the repo, recreate the
   config file (you need the same `BACKUP_PASSPHRASE` and a token that can read the bucket), then step 2-3.

Local layer only (no off-machine copy needed): stop the jobs, copy the chosen `backups\paksh_backup_*.db`
over `paksh.db` and delete `paksh.db-wal` / `paksh.db-shm`.

## What was tested (2026-09-19, no real credentials, nothing uploaded anywhere)

- `test_offsite_backup.py` (32 checks): request signing reproduces AWS's two published SigV4 test vectors;
  encryption round-trips, rejects a wrong passphrase, a flipped bit, truncation, appended data and reordered
  chunks, and hides the plaintext; a full backup -> upload -> retention -> restore-test cycle against an
  in-process fake S3 that re-verifies every signature and payload hash; wrong credentials, a tampered object
  and a wrong passphrase all fail loudly and leave no temp files; the config file is refused inside the repo;
  the scheduled step is conditional.
- **Real-size trial** against a local fake S3: the real 2.32 GB backup -> 1.29 GB encrypted (56%) in 45 s;
  ciphertext has no SQLite header; restore-test **PASSED** in 55 s with `integrity_check = ok` and counts
  matching exactly (19,652 events, 599,590 articles).
- **Not tested** (needs your account): the real R2/B2 endpoint, real network upload speed, and the
  first scheduled run. Signing is standard AWS SigV4 and R2/B2 both implement it, but run `--check` first.

## Security notes

- Credentials and the passphrase live only in the config file (or environment variables), outside git; the
  tool never prints them. `ai_keys.env`-style files are already gitignored; this one is not even in the repo.
- Cloud-account 2FA should be on. The bucket token should be scoped to the one bucket.
- Metadata stored in the clear: object size and the events/articles row counts (used to verify a restore).
- A compromised PC can also read the config file, so this defends against loss and provider access, not
  against an attacker already on this machine.
