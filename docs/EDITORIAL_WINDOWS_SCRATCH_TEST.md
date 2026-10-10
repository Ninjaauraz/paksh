# Windows scratch-export test procedure (Editorial CMS, pre-Milestone 2)

**Status: prepared and reviewed on Linux; NEVER RUN on Windows.** Nothing in this document, and none of
`tools/editorial_scratch/`, has been executed against a real Paksh database, a real `_site`, or the
Windows publishing machine. Read this, review the scripts, and run it only when you explicitly approve.

**Purpose:** build a *scratch* copy of the site from a *copy* of a database backup, in a folder that is
separate from production, to (a) measure export time and memory, (b) get a baseline output tree for
Milestone 2's "absent configuration changes nothing" comparison, and (c) show that the procedure cannot
touch production.

**It does not publish, deploy, commit, push, or run the pipeline.** It runs the *unmodified*
`export_static.main()` from the scratch copy of the code.

---

## 0. What is verified, and how (read this before trusting anything below)

Three levels are used throughout:

* **Code-verified**: confirmed by reading the repository code or the CPython source, no execution needed.
* **Linux-tested**: exercised by `test_editorial_scratch_tools.py` (and the editorial suites) on Linux, in temp
  folders. Windows *rules* are simulated there with `ntpath` (marked `[win-lexical]`): that tests the parsing
  and decision logic for Windows path syntax and Windows-shaped subprocess events, **not** a Windows filesystem
  or kernel.
* **Windows-unverified**: cannot be checked on Linux. `test_editorial_scratch_windows.py` was written to check
  these on the Windows machine, but **it has not been run on Windows**.

| Property | Level |
|---|---|
| `PAKSH_DATA_DIR` wins over `data_dir.txt`; `ROOT`, `_site`, `_site.building`, `_site.old` derive from the script's folder; `main()` calls `require_production()` then `init_db()` (which writes) | Code-verified |
| Backups made by `backup_db.py` use SQLite's backup API plus a WAL checkpoint, so one file is a complete database | Code-verified |
| On Windows the `subprocess.Popen` audit event carries a *flattened command-line string* and `executable=None` for `subprocess.run(["node", ...])`; on POSIX it carries a list | Code-verified (CPython 3.13 `subprocess.py`, both branches) |
| The export spawns only `node` (JSX) and the vendored Tailwind CLI | Code-verified (`export_static.py`) |
| Refusals in `init`/preflight/launcher gating; production-path validation; baseline validation; three-state manifest compare; link detection with real symlinks; cleanup refusals; thread-safe hook; hook enforcement with POSIX events | Linux-tested |
| Windows path syntax (drive letters, case, `\\?\`, `\\.\`, `//?/`, local `\\localhost\D$` admin-share aliases, `..`), Windows-shaped subprocess events, the doc's own example path against the real depth check | Linux-tested, `[win-lexical]` only |
| The self-test's own decisions: controls, specific-reason refusals, redirected-temp gate, decoy-based "nothing deleted through a link", `walk_nolinks`/`safe_rmtree`/`remove_link_only` with symlinks and a simulated junction (a real directory presenting the reparse attribute) | Linux-tested (simulation) |
| Junction / reparse-point detection on real NTFS; `cleanup` refusing a root that contains a junction; 8.3 short names; `subst` drives; real `\\localhost\C$` shares | **Windows-unverified** |
| The real Windows `subprocess` audit-event stream as seen by the installed hook; `node` allowed and `cmd /c` refused | **Windows-unverified** |
| `psapi` peak-memory reading; UTF-8 output under a cp1252 pipe; PowerShell and `typeperf` snippets; Process Monitor filters | **Windows-unverified** |
| Python 3.9 *runtime* behaviour | **Windows-unverified** (3.9 grammar was only syntax-checked; suites ran on 3.11, 3.12, 3.13) |

**Run `py test_editorial_scratch_windows.py` first** (section 2). It is safe (temp folder only, plus one `subst`
mapping that it removes) and checks the Windows-unverified rows above. If it fails, stop and report.

How to read its result:

* **Exit 0**: every check ran and passed (optional skips, such as "no node" or "8.3 names disabled", are listed).
* **Exit 1**: at least one check FAILED. Send the whole output.
* **Exit 3, "INCOMPLETE"**: a *required* section could not run: either `%TEMP%` (or an ancestor) is a junction,
  symlink or other reparse point, or a junction could not be created. **This is not a pass.** The output prints the
  redirect it found. Rerun with `py test_editorial_scratch_windows.py --base <ordinary folder on a normal local drive>`.
  The junction/cleanup checks refuse to run under a redirected base because a cleanup refusal would then come from the
  redirected ancestor, not from the junction under test.
* Link targets are kept in a separate *decoy* folder next to the work folder, and the self-test's own cleanup removes
  links with `os.rmdir`/`os.unlink` (never `rmdir /s`, never `shutil.rmtree`, never `ignore_errors`) and then checks
  that every decoy file still exists before deleting the decoy. If cleanup cannot finish it prints the leftover paths.
  Remove a leftover junction with `rmdir <path>` (no `/s`) first.
* The logic of the self-test (its controls, specific-reason assertions and cleanup decisions) is itself tested on
  Linux by `test_editorial_scratch_windows_logic.py`, with POSIX symlinks as stand-ins. That is **Linux-tested
  simulation**, not proof of real NTFS junction behaviour.

---

## 1. How the existing guard and `PAKSH_DATA_DIR` interact (read this first)

Code-verified in `paksh_paths.py`, `database.py`, `export_static.py`:

1. `database.DB_PATH` is resolved **once, at import**, by `paksh_paths.db_path()`.
2. `paksh_paths._resolve_config()` checks the `PAKSH_DATA_DIR` environment variable **first**. If set, it wins and
   `%LOCALAPPDATA%\Paksh\data_dir.txt` is not consulted. If unset, `data_dir.txt` (if it exists) decides; if that is
   absent too the database is `<repo>\paksh.db`.
3. `export_static.main()` calls `paksh_paths.require_production()`, which refuses unless a data directory is
   configured **and** it contains the marker file `.paksh-production` with the magic string. The marker's text is in
   committed code, so a scratch folder can legitimately carry one.
4. `main()` then calls `init_db()`, which **writes** to the database it opened (index/migration statements). On the
   wrong database that is a production write. This is why path control matters more than anything else here.
5. `ROOT = Path(__file__).parent`; `_site`, `_site.building` and `_site.old` are all derived from it. A code copy in
   a scratch folder therefore builds entirely inside that folder.

Consequences:

* The marker **proves nothing about isolation.** `scratch_prepare.py init` writes one into the scratch data folder
  only so the real, unmodified guard accepts it. Isolation comes from the launcher's assertions: a fresh interpreter
  must report that `paksh_paths.db_path()` **and** `database.DB_PATH` resolve to the scratch database, inside the
  scratch root, imported from the scratch repo, not under any protected path.
* You must **type the resolved database path** (`--confirm-db-path`). The launcher accepts it if it names *the same
  file* as the resolved path after case, slash and symlink normalisation (so `e:/.../PAKSH.DB` also matches); it is
  **not** a byte-for-byte comparison. The point is that you read the path and see it is under the scratch root.
* The launcher sets `PAKSH_DATA_DIR` itself and *refuses* if the variable is already set in your shell to anything
  else. It also refuses if `PAKSH_ALLOW_NEW_DB` or `PAKSH_ALLOW_EXPORT_COLLAPSE` is set (both weaken production
  guards).
* No production code is modified, wrapped or bypassed.

---

## 2. Prerequisites (check before starting)

Open a **new** PowerShell window used only for this test. Do not reuse the window you use for `live.py`.

```powershell
py -V                      # must be Python 3.9 or newer
node -v                    # must print a version (app.jsx is precompiled with node)
Test-Path C:\paksh_project\paksh\vendor\babel.min.js          # git-ignored; must exist in the production working tree
Test-Path C:\paksh_project\paksh\vendor\tailwindcss.exe
if ($env:PAKSH_DATA_DIR)  { throw "PAKSH_DATA_DIR is set in this shell: open a new window" }
if ($env:PAKSH_ALLOW_NEW_DB -or $env:PAKSH_ALLOW_EXPORT_COLLAPSE) { throw "a guard-weakening variable is set" }
if ($env:PYTHONPATH)      { throw "PYTHONPATH is set: unset it for this test" }
```

The scripts live on the feature branch. **Do not switch the production repo to that branch.** Get them into a
separate folder (a separate `git clone`, a downloaded ZIP of the branch, or copy `tools\editorial_scratch\`, the two
`test_editorial_scratch_*.py` files and the `editorial\` folder):

```powershell
$Tools = "E:\paksh_review\tools\editorial_scratch"        # wherever you placed the scripts
cd E:\paksh_review
py test_editorial_scratch_windows.py                        # the Windows self-test: send back the full output
```

**Disk space.** The formula is **backup file size + 2 x the production `_site` size + 1 GB headroom**
(`_site` is built next to the previous output and swapped). It is enforced in code:

* `init` measures the production `_site` (read only), and **refuses** if the scratch drive has less free space than
  the full formula, printing the figures.
* The layout records `2 x _site + 1 GB` as `required_free_bytes` (the backup is already copied by then) and
  **preflight refuses** below that. `--min-free-gb` can raise this requirement, never lower it.

Estimate yourself first:

```powershell
$siteBytes = (Get-ChildItem C:\paksh_project\paksh\_site -Recurse -File | Measure-Object Length -Sum).Sum
"production _site (read only) = {0:N0} MB" -f ($siteBytes/1MB)
Get-PSDrive E | Select-Object Used,Free
```

---

## 3. Layout (separate from production)

```
E:\paksh_scratch\editorial_test\run1\       <- the scratch root (>= 3 folder levels below the drive; not under production)
    repo\      code copy: NO .git, NO _site, NO secrets, NO databases, NO locks, NO links; WITH vendor\ build tools
    data\      database\paksh.db  (a COPY of a backup)  +  .paksh-production marker
    logs\      baseline_counts.json, run-*.log, run-*.guard.log, run-*.metrics.json
    tools\     these scripts (the only place the launcher will run from)
    tmp\       temp files (the launcher redirects TEMP here)
    scratch_layout.json, SCRATCH_ROOT.txt       sentinel files
```

The scratch root must be at least **3 folder levels below the drive** (`E:\a\b\c`). The earlier draft used a 2-level
example that the code itself refused; this one is checked by a test against the real depth function.

Protected paths (never written, never read by the export): `D:\Paksh_Data` (database, backups, marker),
`C:\paksh_project\paksh` (repo, `_site`, `.pipeline.lock`), plus any extra root `init` discovers (below).

---

## 4. Prepare the isolated copy

Take a production manifest **before** `init`, so the final comparison covers `init`'s reads too. This one is not
bound to a scratch root (none exists yet) and is only for the final comparison; the launcher will not accept it.

```powershell
$Scratch  = "E:\paksh_scratch\editorial_test\run1"
$ProdData = "D:\Paksh_Data"
$ProdRepo = "C:\paksh_project\paksh"

# pick a COMPLETE backup FILE (never the live database, never a -wal/-shm file)
Get-ChildItem "$ProdData\backups\daily" | Sort-Object LastWriteTime -Descending | Select-Object -First 5 Name,Length,LastWriteTime
$Backup = "$ProdData\backups\daily\<the file you chose>"      # not modified in the last several minutes

py "$Tools\scratch_manifest.py" snapshot --out "E:\paksh_scratch\before_init.json" `
   --production-data-dir $ProdData --production-repo $ProdRepo --hash-db

py "$Tools\scratch_prepare.py" init --scratch-root $Scratch --source-repo $ProdRepo `
   --backup-file $Backup --production-data-dir $ProdData --production-repo $ProdRepo
```

What `init` does and refuses (enforced in code; Linux-tested on synthetic data):

* **Validates the production paths instead of trusting them**, so a typo cannot make the deny-list, overlap checks
  and manifests protect the wrong place. `--production-data-dir` must exist, carry the genuine `.paksh-production`
  marker and contain `database\paksh.db`; `--production-repo` must be a git work tree containing `export_static.py`;
  and if the repo has `live.py`, its `PRODUCTION_DATA_DIR` must be the same folder you named (cross-check).
  Extra protected roots are added automatically: the folder named by `%LOCALAPPDATA%\Paksh\data_dir.txt`, an
  already-set `PAKSH_DATA_DIR`, and the source repo. They are printed and stored in the layout.
* Reads the source repo and the backup file **read-only**; writes only inside `--scratch-root`.
* Refuses a scratch root that is shallow (< 3 folder levels), non-empty, inside or containing any protected path,
  your home folder, or inside a git work tree (a `.git` in any ancestor).
* **Refuses symlinks, junctions and other reparse points**: in the scratch root or any existing ancestor, in the
  source repo (outside excluded folders such as `.git`, `_site`), and for the backup file itself.
* Refuses a backup file that *is* the live database or one of its `-wal`/`-shm`/`-journal` sidecars, or that is
  inside the scratch root; checks the size did not change while copying.
* Copies code excluding `.git`, `_site*`, databases, `*.bak*`, `.env*`, `ai_keys.env`, key/credential files
  (`*.pem`, `*.key`, `*.pfx`, `*.p12`, `id_rsa*`, `.netrc`, `credentials*`, ...), `.pipeline.lock`, logs, `signals`,
  `backups`, `archive`. **File names only are matched: file contents are not scanned.** Requires
  `vendor\babel.min.js` and `vendor\tailwindcss(.exe)` and copies them.
* Opens the copy with SQLite `mode=ro&immutable=1`, runs `PRAGMA integrity_check` (must be `ok`), requires an
  `events` table, writes `logs\baseline_counts.json`. A corrupt or incomplete backup is a clear refusal and the
  half-built root is removed (if the folder existed and was empty, only what `init` created is removed).
* Writes the production marker into `data\` (section 1: not proof of isolation).

### Record the baseline

```powershell
Get-Content "$Scratch\logs\baseline_counts.json"
```
Keep this: integrity result, tables, `events`/`articles` counts, backup name/size/time, protected roots, the
measured production `_site` size. The scratch site reflects the *backup's* age, not the live site.

---

## 5. Preflight and plan (nothing runs yet)

```powershell
py "$Scratch\tools\scratch_preflight.py"
py "$Scratch\tools\scratch_export.py"          # PLAN ONLY: no --run
```

The plan prints `RESOLVED DATABASE : ...` and the protected roots. **Stop and read them.** The database path must begin
with your scratch root. If it names `D:\Paksh_Data` or the production repo, do not continue and report it.

Preflight refuses (any one stops everything): not inside `<root>\tools`; layout paths outside the root or overlapping a
protected root; the scratch root inside a git work tree; a protected production path that no longer carries the
marker / `export_static.py` (typo, unmounted drive, edited layout); **any symlink/junction/reparse point inside the
scratch tree**; a `.git` or any secret/credential/database/lock name in the scratch repo; missing `vendor` tools or
`node` (or `node` resolving into a protected path); `PAKSH_DATA_DIR` preset to something else; `PAKSH_ALLOW_*` set; a
`PYTHONPATH`/`sys.path` entry inside a protected path; missing marker; unreadable scratch database; a pre-existing
`_site*` (unless `--allow-existing-output`); less free disk than the figure computed at init; and **any
disagreement** between what `paksh_paths.db_path()` / `database.DB_PATH` resolve to (fresh interpreter, scratch repo
first on the path) and the scratch database, or the real `require_production()` guard refusing.

---

## 6. Start the external observers (before the run)

The audit hook cannot see child processes (`node`, `tailwindcss.exe`). Observe them at the OS level.

**Process Monitor (Sysinternals), mandatory for the first run (Windows-unverified filter details):**

1. Run as administrator. Stop capture, clear, then set filters (Include):
   `Path` *begins with* `D:\Paksh_Data` ; `Path` *begins with* `C:\paksh_project\paksh`
   (add every protected root printed by `init`).
2. Do **not** filter by process: you want to see *anything*, including antivirus and Explorer, then judge.
3. Start capture only **after** `init` finished (init legitimately *reads* the production repo and the backup file).
4. After the run, open *Tools > File Summary* and *Tools > Process Tree*. Look for operations by `python.exe`, `node.exe`
   or `tailwindcss*.exe` of type `WriteFile`, `SetEndOfFileInformationFile`, `SetRenameInformationFile`,
   `SetDispositionInformationFile`, or `CreateFile` whose *Detail* shows write/delete access.
   **Expected: none** on protected paths from those three processes. Reads by your own tools are noise; writes by
   `python.exe` to production are a stop-and-report event. Save the log to `$Scratch\procmon-run1.pml`.

**Memory of child processes (optional):**
`typeperf "\Process(node)\Working Set - Peak" "\Process(tailwindcss)\Working Set - Peak" -si 2 -o E:\paksh_scratch\children.csv`
(instance names vary, e.g. `node#1`; check `typeperf -q Process` if empty). Untested.

---

## 7. Pause production, take the BASELINE manifest, then run

Pause (owner action): stop `live.py`, and disable or wait out the scheduled refresh/reframe tasks for the window.
Confirm `C:\paksh_project\paksh\.pipeline.lock` does not exist.

The launcher requires a **bound, hashed baseline** taken after `init` and just before the run:

```powershell
py "$Tools\scratch_manifest.py" snapshot --out "E:\paksh_scratch\before.json" `
   --production-data-dir $ProdData --production-repo $ProdRepo --scratch-root $Scratch --hash-db

# first run, "full" variant. Replace the path after --confirm-db-path with what the PLAN printed.
py "$Scratch\tools\scratch_export.py" --run --tag full `
   --confirm-db-path "E:\paksh_scratch\editorial_test\run1\data\database\paksh.db" `
   --before-manifest "E:\paksh_scratch\before.json"
```

**What makes a manifest an acceptable baseline** (checked in code, `scratch_manifest.validate_baseline`; it is more than
"a recent file"): it parses; it is a current-version `production-baseline`; it names the **same production data dir and
repo** as the scratch layout; it is **bound** to this scratch root and its token (`--scratch-root`); it is recent by
its **own embedded timestamp** (12 h, not in the future); it shows an existing production database **with a SHA-256**
(use `--hash-db`; `--accept-unhashed-baseline` accepts a weaker one and says so) and a populated `_site`; its git state
is readable (`git_head` and the status digest not "unavailable"); and no pipeline lock existed. It does **not** prove the
production state is still unchanged now; that is what the AFTER comparison is for.

The launcher then: sets `PAKSH_DATA_DIR` for its own process; points `TEMP` and bytecode at the scratch root; `chdir`s
into the scratch repo; makes stdout/stderr UTF-8-safe; installs the audit hook; imports `export_static` and checks it came
from the scratch repo with `ROOT` and `database.DB_PATH` equal to the scratch paths; runs `export_static.main()`; writes
`logs\run-<tag>-<time>.log`, `.guard.log`, `.metrics.json`.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | export completed, no guard violation, and the run is a **valid benchmark** for its variant |
| 1 | preflight failed, the export raised or exited non-zero, or the guard recorded a violation |
| 2 | not a prepared scratch root / run from the wrong place |
| 3 | a required confirmation or baseline is missing or unacceptable (nothing ran) |
| 4 | export completed but is **not a valid benchmark** (exit code 4): see `benchmark_invalid_reasons` in the metrics |
| 97 | the audit-hook guard killed the process on a violation (reason in `.guard.log`) |

---

## 8. Measurements

From `logs\run-*.metrics.json` and `.log`:

| Measure | Where | Caveat |
|---|---|---|
| Elapsed time | `wall_seconds` | includes external image fetches, node, Tailwind **and the audit-hook overhead** (path canonicalisation per file/db event; tens of microseconds each on Linux, expect more on Windows) |
| CPU time | `cpu_seconds_this_process` | the Python process only |
| Peak memory | `peak_working_set_bytes_this_process` | Python process only (`psapi`, Windows-unverified); **excludes `node` / Tailwind children** |
| Output file count and size | `output_site.files` / `.bytes` | scratch `_site` |
| Stage timings | `+NNN.Ns` prefix on each line of the `.log` | only stages that print give boundaries: `storylines:`, `homepage:`, `sections:`, `[og] n/m share cards written in …`, `rss:`, `Built static site` |
| **Share-card outcome** | `og_cards.status` | `complete` / `partial` / `skipped` / `failed` / `disabled` / `unknown`, taken from the exporter's own `[og]` lines |
| **Benchmark validity** | `benchmark_valid`, `benchmark_invalid_reasons` | `false` (and exit code 4) if cards were skipped (e.g. missing `fontTools`), partial, failed, or of unknown outcome; so a partial export cannot be mistaken for a complete benchmark |
| Network | `guard.outbound_connections` | hosts contacted (publisher image CDNs), recorded, not blocked |
| Subprocesses | `guard.subprocesses` | expected: `node -e …`, the vendored Tailwind CLI |

`og_cards.status = complete` means every card was **rendered**. The exporter swallows per-image fetch failures silently
(a card falls back to the no-image design), so it does not mean every publisher photo was fetched.

Repeat **twice more** (warm cache). A repeat run uses `--allow-existing-output` (the exporter's own swap replaces the
previous scratch `_site`): `... --run --tag full2 --allow-existing-output ...`. Take a fresh bound baseline if more than
12 hours have passed.

### Separating external image fetching from local work

The existing code supports exactly one lever: `export_static.OG_CARD_N` ("Set 0 to disable"). The launcher's
`--variant no-og-cards` sets that module constant to `0` **in memory** before `main()`; no exporter file changes.

```powershell
py "$Scratch\tools\scratch_export.py" --run --tag nocards --variant no-og-cards --allow-existing-output `
   --confirm-db-path "<resolved path>" --before-manifest "E:\paksh_scratch\before.json"
```

For this variant the share-card step must read `disabled`; otherwise the run is marked not valid. `full` minus
`no-og-cards` = the cost of share cards (about 497 external image fetches plus rendering, per the committed feed).
**Fetch time cannot be separated from rendering time without changing the exporter**, and no flag was added to do that.
Do not compare `no-og-cards` output with `full` output; use it for timing only.

---

## 9. Prove isolation

1. **After manifest and comparisons** (production still paused). Compare **both** baselines against it:
   ```powershell
   py "$Tools\scratch_manifest.py" snapshot --out "E:\paksh_scratch\after.json" --production-data-dir $ProdData --production-repo $ProdRepo --scratch-root $Scratch --hash-db
   py "$Tools\scratch_manifest.py" compare "E:\paksh_scratch\before_init.json" "E:\paksh_scratch\after.json"
   py "$Tools\scratch_manifest.py" compare "E:\paksh_scratch\before.json" "E:\paksh_scratch\after.json"
   ```
   The result has **three states**:
   * `UNCHANGED` (exit 0): every protected item matches **and every item could actually be checked**.
   * `CHANGED` (exit 1): at least one protected item differs.
   * `INCONCLUSIVE` (exit 3): nothing differs, but something could not be determined: **git unavailable or failing**
     (the repo state is then unverified), an unreadable file, mismatched or missing `--hash-db`, or a pipeline lock
     present. It is **never reported as unchanged**, and is not proof that production is unchanged; fix the cause (for
     example `git config --global --add safe.directory ...`) and re-run the snapshots.

   It compares: database size/mtime/SHA-256 and `-wal`/`-shm`/`-journal` presence; the marker; the backups tree; the
   production `_site` (file count, bytes, newest mtime, digest of every path+size+mtime); `_site.building` / `_site.old`
   existence; `.pipeline.lock`; git `HEAD` and a digest of `git status --porcelain` (run with `--no-optional-locks` so
   the check itself cannot write the index).
2. **Guard log:** `logs\run-*.guard.log` contains no `VIOLATION` line; metrics show `violations: []`; exit code not 97.
3. **Process Monitor:** no write/delete/rename by `python.exe`, `node.exe` or `tailwindcss*.exe` on protected paths.
4. **Output is where expected:** `Test-Path "$Scratch\repo\_site\index.html"` is true; `_site\data\freshness.json` shows
   the *scratch copy's* event count (compare with `baseline_counts.json`).
5. **No git exposure:** `Get-ChildItem $Scratch\repo -Force -Recurse -Filter .git` returns nothing.

Send back for review: the Windows self-test output, `baseline_counts.json`, every `run-*.metrics.json` and `.guard.log`,
all manifests and both compare outputs, the Process Monitor summary, and the first and last 40 lines of each `.log`.

---

## 10. Cleanup and recovery

Cleanup removes **only** a folder that has the sentinel file, a layout naming that same folder, no overlap with any
protected root (including the extra roots recorded at init), no unknown contents, **and no symlink, junction or other
reparse point anywhere inside it**, and whose own path does not pass through one. It requires you to retype the exact
path. If a link is found it refuses *before deleting anything* and tells you which one.

```powershell
Write-Host "About to delete: $Scratch"
Get-Content "$Scratch\scratch_layout.json" | Select-String scratch_root     # confirm it is the scratch folder
py "$Scratch\tools\scratch_prepare.py" cleanup --scratch-root $Scratch --confirm-path $Scratch
```

* **If cleanup refuses because of a junction:** remove the junction itself (never its target) with
  `cmd /c rmdir "<the junction path>"` **without `/s`**, then re-run cleanup. Check the target folder is intact first.
* **Recovery after a failed `init`:** `init` removes what it created; if the folder pre-existed empty it stays. If a
  crash left a partial root, `cleanup` refuses it (no sentinel); delete it by hand only after printing and checking the
  path, and only if it contains nothing but what `init` created.
* **After a violation (exit 97):** the scratch tree may be half-built. Keep the logs, run the Windows self-test and the
  production manifest comparison, then clean up and start again with a new root; do not retry with a weakened policy.

Copy anything you want to keep (logs, manifests) out first. Delete `E:\paksh_scratch\*.json` yourself when no longer
needed. Re-enable `live.py` and the scheduled tasks afterwards.

---

## 11. Forbidden commands and unsafe configurations

Never, during this test:

* `py export_static.py`, `py refresh.py`, `py live.py`, `py safe_autopush.py`, `py reframe.py --apply`, `py cleanup.py`,
  `py consolidate.py`, `py recount_migrate.py`, `py backfill*.py`, `py backup_db.py` from the production repo folder.
* Anything with `PAKSH_DATA_DIR` set to `D:\Paksh_Data` or unset, or run from `C:\paksh_project\paksh`.
* `PAKSH_ALLOW_NEW_DB=1` or `PAKSH_ALLOW_EXPORT_COLLAPSE=1` (they weaken production guards; the tools refuse them).
* Adding a `.git` folder or a remote to the scratch repo; putting the scratch root inside any repository; copying
  `ai_keys.env`, `.env`, `offsite_backup.env`, `data_dir.txt` or any credential file into it.
* Pointing `--backup-file` at `paksh.db` or a `-wal`/`-shm` file; pointing `--scratch-root` inside production; creating
  junctions or symlinks inside the scratch root or the source repo.
* Running the launcher from anywhere except `<scratch_root>\tools`; editing `scratch_layout.json` by hand.
* Switching the production repo to the feature branch, or pulling into it.
* Running with `live.py` or a scheduled task active and then treating manifest differences as a scratch-test fault.
* Retrying after a guard violation (exit 97) with a weakened policy.

---

## 12. What each safeguard does and does NOT protect

| Safeguard | Protects against | Does NOT protect against |
|---|---|---|
| Separate scratch repo + data dirs (`init`) | The export's derived paths (`_site`, `_site.building`, database) landing in production | A human running another command in the production repo |
| Production-path validation at `init` (marker, live DB, git repo, `live.py` cross-check, extra roots) | A typo making every other check protect the wrong folder | A production layout that is wrong **and** self-consistent (e.g. a second, marked copy named by mistake); it cannot know which folder is "really" production beyond these cross-checks |
| `init` refusals (roots, backups, links, ancestors' `.git`, disk) | Bad roots, live-DB-as-backup, link tricks, missing tools, corrupt backups, secrets/`.git` being copied | Secrets *inside* ordinary files (names only are matched); a symlink *race* between check and copy |
| Preflight incl. fresh-interpreter path resolution | Wrong `PAKSH_DATA_DIR`, `data_dir.txt` surprises, imports from production, weakened-guard variables, `node` from a protected path | A change made *between* preflight and run (the launcher re-asserts `ROOT`/`DB_PATH` after import) |
| Typed `--confirm-db-path` | A launcher run on autopilot | A human who types the path without reading it |
| Validated baseline manifest | Running with a stale, unbound, unhashed or irrelevant baseline | It is a snapshot, not a guarantee about the future |
| Existing `require_production()` guard (unmodified) | Running with no/wrong data directory | Isolation: it accepts any directory carrying the marker, including the scratch one |
| Python audit hook (`scratch_guard.py`), thread-safe, hard exit 97 | Python-level reads/writes touching a protected path or writing outside scratch, forbidden/unknown subprocesses, protected paths in command lines (any slash/case/`\\?\`/local-admin-share/`..` spelling), imports from production; cannot be swallowed by `except` | **Child-process file activity** (`node`, Tailwind); operations that raise no audit event (e.g. `os.stat`, native/ctypes/WinAPI calls); anything before the hook is installed; aliases it cannot know: a **custom-named network share** of a protected folder, a `subst`/mapped drive where `realpath` does not resolve it, 8.3 names for paths that do not exist yet; it adds per-event overhead to timings |
| Subprocess allowlist | Unexpected programs (git, powershell, cmd, python); a different program in the vendor folder (the Tailwind CLI is allowed by **exact path**) | What `node` or Tailwind then do |
| Before/after manifests (three-state) | Detecting a change to the database, `_site`, locks, git state between two instants; refusing to call an unverifiable state "unchanged" | A write that restores identical size/mtime (use `--hash-db`); changes by *other* programs during the window; the exact time or actor |
| Link/junction/reparse refusals | Following or deleting through a link in the scratch root, the source tree, the backup, or ancestors | **Windows-unverified:** detection of real junctions relies on the reparse attribute (`test_editorial_scratch_windows.py`); OneDrive placeholder files are also reparse points and will be refused |
| Process Monitor | OS-level view of **all** processes, including children | Mistakes in filter setup; manual; not exercised here |
| Pausing `live.py`/schedules | False alarms in the manifest compare | Does not itself protect anything |

---

## 13. Known unverified items and test inventory

* **Windows-unverified** (see section 0): real junction/reparse behaviour, 8.3 and `subst` aliasing, real `\\localhost\C$`,
  the real Windows `subprocess` event stream in the installed hook, `psapi`, cp1252-pipe output, PowerShell/`typeperf`/Process
  Monitor details, Python 3.9 runtime. Run `test_editorial_scratch_windows.py` first.
* The audit hook's tolerance of the real export is unknown: a legitimate write outside the scratch root (for example into a
  library cache) stops the run with exit 97. That is by design (fail closed); report the guard-log line rather than loosening
  the policy.
* Whether Pillow/`fontTools` are installed (otherwise the run ends with exit code 4 and `og_cards.status = skipped`).
* Real export duration and memory: no number exists yet.
* Section 3 of the Windows self-test (path normalisation on real paths, `subst`, 8.3 names) has controls that no Linux test can
  exercise (they need Windows case-insensitivity and `subst`); they are unverified until run on Windows.
* Linux test suites (run from the repo root): `test_editorial_scratch_tools.py`, `test_editorial_scratch_windows_logic.py`,
  `test_editorial_strictness.py`,
  `test_editorial_timestamps.py`, `test_editorial_schema.py`, `test_editorial_resolve.py`,
  `test_editorial_revisions_permissions.py`.
