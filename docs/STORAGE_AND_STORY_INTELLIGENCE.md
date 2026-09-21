# Storage migration + Story Intelligence — working report

*Started 2026-09-21. Sections are added as each phase completes. Evidence labels: `[MEASURED]` queried from the live system · `[CODE]` read from source · `[PROBED]` a live check.*

---

# PART 0 — Phase 0 architecture audit (nothing was modified)

Baseline: `origin/main` = `HEAD` = `b128d05449`; tree clean except the two pipeline-maintained files (`.pipeline_baseline.json`, `autopush_log.txt`, **never committed**). No pipeline process, no `.pipeline.lock`. Relevant tests pass (7 files, live DB untouched — checked by size + mtime).

## 0.1 Database `[MEASURED]` `[CODE]`

| | |
|---|---|
| Location | `C:\paksh_project\paksh\paksh.db` — 2,379,673,600 bytes (2.38 GB) |
| Sidecars | `paksh.db-wal` (0 B, checkpointed), `paksh.db-shm` (32 KB) |
| Settings | WAL, page 4096 B, 580,975 pages, 0 free pages, `auto_vacuum=0`, `wal_autocheckpoint=1000`, UTF-8; `get_connection()` sets `busy_timeout=30000`, `synchronous=NORMAL` |
| Integrity | `PRAGMA quick_check` = **ok** (72 s) |
| Tables (rows) | `articles` 617,498 · `embeddings` 298,720 · `events` 20,034 · `article_enrichment` 2,218 · `event_relationships` 4 · `event_deltas` 2 |
| Indexes | `idx_articles_unclustered` (partial), `idx_articles_event_id`, `idx_embeddings_created_at`, `idx_events_created_at`, `idx_events_updated_at`, `idx_article_enrichment_*`, three on `event_relationships` |
| Git | `paksh.db`, `-wal`, `-shm`, `-journal` are in `.gitignore` |

**The path is defined in one production place:** `database.py:15  DB_PATH = Path(__file__).parent / "paksh.db"`, opened at exactly one line (`database.py:33`). Every other module reaches the DB through `database.get_connection()`. **Exceptions with their own path constants:** `backup_db.py:55-56` (`DB_PATH`, `BACKUP_DIR`), `offsite_backup.py:60` (`BACKUP_DIR`), `provenance_manifest.py:46`, and the diagnostic script `audit_stage2_hardening_live.py`. Tests monkey-patch `database.DB_PATH` (so they keep working if it stays a module attribute).

Who can hold the DB open: the scheduled jobs (`refresh_scheduled.bat` 05:30, `reframe_scheduled.bat` 07:30), `live.py` (manual), and `main.py` (staging API, not running). All the pipeline writers take `.pipeline.lock` through `runlocked.py`; `backup_db.py` deliberately does not (SQLite's hot-backup API needs no exclusivity).

## 0.2 Backups `[MEASURED]` `[CODE]`

* `backup_db.py` — SQLite `backup()` API (safe with concurrent writers), then `PRAGMA integrity_check` + a non-empty sanity check; **not compressed**; retention keeps the newest N of *its own* `paksh_backup_YYYYMMDD_HHMMSS.db` (the batch passes `--keep 5`); failed copies are renamed `.FAILED.db` and never pruned; foreign files are never touched. `BACKUP_DIR.mkdir(exist_ok=True)` has **no `parents=True`**. Logs to `backup_log.txt`.
* **Only one caller:** the tail of `reframe_scheduled.bat` (07:30). The nightly does not back up. `offsite_backup.py --run` is wired but inert (no credentials file yet).
* **C: also holds ≈ 21 GB of non-live data:** `backups/` 11 GB (5 daily copies ≈ 2.3 GB each + `paksh_pre_recount_migrate…` 1.7 GB) and **seven ad-hoc `paksh.db.bak*` / `pre_phase*_backup` files in the repo root, ≈ 10.6 GB**, from earlier migrations.

## 0.3 Pipeline path map `[CODE]`

```
ingest.py / gdelt_source.py ──► paksh.db (articles) ──► cluster.py ──► analyze.py (cluster+merge+LLM) ──► paksh.db (events)
                                                                                            │
                                            export_static.py ──► _site/ ──► safe_autopush.py (git add _site; plain `git push`)
```
| Stays on **C:** | Reason |
|---|---|
| source code, `_site/`, `.git` | small; git/Vercel workflow; not "persistent data" |
| `.pipeline.lock`, `refresh_log.txt`, `reframe_log.txt`, `autopush_log.txt`, `backup_log.txt`, `.pipeline_baseline.json` | tiny; the lock on a removable card would cause spurious failures if the card sleeps; other scripts (`verify_fresh`, schedule-health) read these relative to the repo |
| `ai_keys.env`, `%LOCALAPPDATA%\Paksh\*` | secrets/config must not sit on a removable card |
| **Moves to D:** | `paksh.db` (+ WAL/SHM sidecars follow it), `backups/` (daily), the old ad-hoc `.bak*` files (archive) |

## 0.4 Scheduler `[PROBED]`

| Task | Runs | Action | State |
|---|---|---|---|
| `Paksh nightly refresh` | 05:30 | `C:\paksh_project\paksh\refresh_scheduled.bat` → `refresh.py --gdelt && safe_autopush.py nightly`, then `verify_fresh`, schedule-health | **active** (Interactive, visible console) |
| `Paksh reframe` | 07:30 | `reframe_scheduled.bat` → `reframe.py --apply --limit 300`, `export_static.py`, `safe_autopush.py reframe`, **`backup_db.py --keep 5`**, off-machine (inert), deploy check, schedule-health | **active** |
| `Paksh  refresh` (two spaces) | 00:30 | `C:\Users\ambuj\Downloads\refresh_scheduled.bat` → `cd` to *Downloads*, `py refresh.py` (**no such file there**: it logs "can't open file" and exits 0) | **stale, harmless no-op** — not touched |

No separate backup or autopush task exists; both are steps inside the two batches. **`safe_autopush.py` runs a plain `git push`, so every local commit on `main` is published at the next nightly/reframe.**

## 0.5 The volume for the new location `[PROBED]`

**`D:` is an exFAT volume on a removable USB SD-card reader** (238 GB, 101.7 GB free, healthy, not read-only, MBR) that **already holds unrelated data** (`DCIM`, `EVENT`, a hidden `_DB`, `MISC`, GoPro files). Consequences:
* exFAT has no 4 GB file limit → a 2.4 GB database and its backups are fine.
* exFAT is **not journaled**: card removal, a sleeping reader or power loss can corrupt file-system structures, not just an open transaction.
* Only `D:\Paksh_Data\` will be created or written. Nothing else on the card is touched.
* An SD card is primary working storage here, **not** a disaster-recovery copy. An independent off-machine backup remains desirable (`offsite_backup.py` is ready, waiting for credentials).

## 0.6 Story / event schema `[MEASURED]` `[CODE]`

* **"Story" = `events` row**; `events.id` is the canonical, stable story ID (never re-numbered; merges add articles, never change ids). Columns: `id, title, summary, divergence, omissions, analysis_json, is_demo, created_at, updated_at, reframe_last_attempt_at, reframe_last_failure_class`.
* `analysis_json` keys: `title, title_hi, summary, summary_hi, summary_points, framing, framing_hi, topic, region, published_at, image_url, sources[], coverage{left,center,right,international,unrated}, total_sources, content_complete, degraded, summary_method`. `sources[]` rows: `source, owner, lean, language, url, headline` (all articles, **not** just the prompt's 12).
* `articles`: `id, source, language, title, url (UNIQUE), summary, image_url, published, fetched_at, event_id`. **Text available per article is small:** mean excerpt **100 characters** (5.9% empty); only 2.8% have an accepted page-metadata description (`article_enrichment`). `published`: 96% ISO, the rest date-only/free text; 2.7% of ISO values are later than `fetched_at` (clock skew).
* Story size (events created in the last 14 days): 2 articles → 1,319 · 3 → 561 · 4 → 313 · 5 → 193 · 6 → 111 · 7 → 100 · 8 → 54 · 9 → 50 · 10 → 57 · 11 → 32 · **12+ → 582**.
* Embeddings: `embeddings(key = sha256(model + text), vec BLOB float32[1024])`, shared cache, keyed by article text (`cluster._emb_key(cluster._text_of(article))`).
* Existing relationships: `event_relationships` (R1–R4 between **events**, frozen snapshot of the earlier event, judge-versioned, partial-unique "one accepted per pair") and `event_deltas` — **4 and 2 rows**.

## 0.7 Where each decision is made today `[CODE]`

| Decision | Where |
|---|---|
| Story membership | `cluster.py` (leader clustering + keyword gate) → `analyze._merge_into_existing` → `cluster.match_clusters_to_events` (centroid ≥ 0.66 + keyword rule, 5-day window, newest 400 events) → `database.assign_articles_to_event` |
| Source selection (prompt) | `source_selection.select_sources` from `analyze.build_prompt` |
| Lean | `sources.py` labels → `analyze.lean_of(name, region)`; bar = one vote per owner in `analyze.postprocess` |
| Framing / completeness | LLM in `analyze.analyze_event` (+ one retry) → `compute_content_complete` |
| Publication | `database.get_all_events` (≥ 2 voting outlets, `content_complete is not False`) |
| Provenance | `analysis_json.sources[]` (article → outlet → owner → lean → URL) |

## 0.8 Retrieval — what exists `[CODE]`

* **`context_retrieval.py`** (319 lines, deterministic, read-only, no LLM): *event → older events*. Builds unit-normalised **event centroids** from cached member-article vectors, keeps strictly-older events inside a look-back (56 d), ranks by cosine (≥ 0.78, top-50) and requires **lexical corroboration** (≥ 4 shared non-generic terms; storyline members get a bounded allowance), returns ≤ 3 `Candidate`s with deterministic tie-breaks. Topic is never a gate.
* **`relationship_judgment.py`** (Stage 2, one bounded LLM call per event, ≤ 3 candidates; labels R1–R4 / N1 / N2 / A1, "insufficient evidence" is a rejection) → **`story_memory.py`** (isolated additive schema `event_relationships` / `event_deltas`, frozen snapshots, judge-version supersession) → **`context_narration.py`** (delta text) → **`reader_context.py`** (the *only* reader boundary; called non-fatally from `export_static.py:1019`).
* **Is it production-active?** Retrieval and judgment are **not imported by any pipeline step** (they run via `replay_story_memory.py`, which needs `--persist` to write). Only the *read* side (`reader_context`) runs at every export, and it serves 4 relationships.
* `storylines.py` (196 lines) builds "sagas" at export time from the same embedding cache (222 sagas covering 612 events) — a similarity grouping, separate from verified story memory.
* **What this gives Story Intelligence:** a proven **RETRIEVE → JUDGE → UPDATE** shape and conventions (isolated module, own idempotent migration, read-only retrieval, deterministic ties, judge-version supersession, frozen snapshots, non-fatal reader boundary), and reusable primitives (`build_centroids`, `event_tokens`, `lexical_overlap`, `_tokenize`).
* **What it does not do** (the gap): it never looks *inside* a story. It cannot say which articles are independent reports, what changed over time, or where figures disagree.

## 0.9 Minimal schema changes for Story Intelligence

Reuse, do not duplicate: story identity = `events.id`; article membership = `articles.event_id`; *between-story* relations stay in `event_relationships`. Add only what is new *within* a story, as an **isolated, additive** migration owned by one module (the `story_memory.py` pattern — never woven into `database.init_db()`):

| Table | Purpose |
|---|---|
| `si_reporting_events` | one row per independent act of reporting in a story (root article, independence class, confidence, first-published / first-detected times) |
| `si_reporting_event_articles` | membership: which articles are the same reporting event, and each article's role (`INDEPENDENT` / `DERIVED` / `ATTRIBUTED_REPETITION` / `UNCERTAIN`), what it derives from, evidence |
| `si_developments` | material changes in a story: type, description, `event_time` (nullable) / `published_at` / `detected_at`, confidence |
| `si_claims` | quantitative claims (counts / amounts) attributed to reporting events — the only claim type reliable enough from short excerpts |
| `si_relationships` | within-story edges: `SAME_REPORTING_EVENT`, `DERIVED_FROM`, `NEW_DEVELOPMENT`, `UPDATES`, `INDEPENDENT_CORROBORATION`, `CONTRADICTS` (+ evidence, confidence, version) |

## 0.10 Risks

1. **Removable exFAT card as the primary DB store** (removal / sleep / power loss / drive-letter change; USB latency). Mitigations: existence-guarded path (never silently create an empty DB), throughput measured before committing, WAL checkpoint + verified backups, C: copy retained through one production cycle, off-machine backup documented.
2. **Autopush publishes every local commit** → all code committed here must be inert until activated locally.
3. **~100-character excerpts** bound what independence / claims can honestly be claimed → `UNCERTAIN` is a first-class outcome; nothing is claimed as "verified true".
4. **Stories mutate** (merges add articles) → derived rows must be versioned/idempotent, keep `detected_at` stable, and never rewrite original article data.
5. **Runtime and failure isolation** → bounded work per cycle, non-fatal step, no LLM in v1 so no cost/rate-limit coupling.

## 0.11 Rollback

* **Storage:** delete `%LOCALAPPDATA%\Paksh\data_dir.txt` → code falls back to `C:\paksh_project\paksh\paksh.db`. The C: database is renamed (not deleted) to `paksh.db.migration_backup` and kept through one production cycle; if data was written on D: since, copy the D: file back first (`py backup_db.py` on D: first, then copy).
* **Intelligence layer:** additive tables; disable the pipeline step (revert its commit) and the tables are simply ignored; drop with `DROP TABLE si_*`.

## 0.12 Implementation order

1. `paksh_paths.py` + wiring (inert until configured) → verify → 2. copy DB with SQLite backup API under the pipeline lock, verify, activate → 3. relocate backups (verified before any C: removal) → 4. Story Intelligence: schema → pure derivation (independence, developments, chronology, claims, relationships) → persistence → graph read API → 5. evaluation sample + manual inspection → 6. non-fatal pipeline integration → 7. UI contract (no UI).

---

# PART 1 — Storage migration (Phase 1) — DONE and verified

*Executed 2026-09-21 19:00–19:56 IST, under the existing pipeline lock (`runlocked`), with nothing else running.*

## 1.1 What was done

| Step | Result |
|---|---|
| Folder structure | `D:\Paksh_Data\{database, backups\daily, backups\archive, pipeline\logs, pipeline\state}` + `README.txt`. Nothing else on the card was touched (it holds unrelated GoPro/camera data). |
| Path handling | New `paksh_paths.py` is the single resolver; `database.py`, `backup_db.py`, `offsite_backup.py`, `provenance_manifest.py`, `audit_source_utilization.py`, `audit_stage2_hardening_live.py`, `test_phase24b_reader_fixes.py` use it. **The committed code is inert**: default layout unchanged (`<repo>/paksh.db`, `<repo>/backups`). |
| Activation | One machine-local, never-committed file: `%LOCALAPPDATA%\Paksh\data_dir.txt` = `D:\Paksh_Data`. **Rollback = delete that file.** |
| DB copy | SQLite `backup()` API from a read-only source connection (never a file drag) into `paksh.db.copying`, verified, then atomically renamed to `D:\Paksh_Data\database\paksh.db`. 297 s copy. |
| Old C: DB | **Kept**: renamed `paksh.db.migration_backup` (2,379,673,600 B), not deleted, not committed (`.gitignore` `paksh.db*`). Keep it until at least one successful production cycle has used D:. |
| Backups | `backup_db.py` now writes to `D:\Paksh_Data\backups\daily\` (creates parents); retention unchanged (`--keep 5` from `reframe_scheduled.bat`). |

## 1.2 Verification (all measured)

| Check | Result |
|---|---|
| `PRAGMA integrity_check` on the D: copy | **ok** (590 s on the SD card) |
| Tables / schema | 6 tables; `sqlite_master` (types, names, SQL) **identical** to the source |
| Row counts | every table **identical** to the source (events 20,034 · articles 617,498 …), `count_diffs = {}` |
| Source unchanged during the copy | size + mtime identical before and after; re-checked again immediately before activation |
| App-level connection | fresh interpreter, config only: `database.DB_PATH = D:\Paksh_Data\database\paksh.db`; `get_connection()` → events 20,034 / articles 617,498; `journal_mode = wal`; `get_all_events()` = 9,242 |
| Read/write | created, inserted, read back, deleted, dropped a probe table |
| Card-missing guard | `PAKSH_DATA_DIR=D:\Paksh_Data_DOES_NOT_EXIST` → `DataDirError`, exit 1, **no empty DB created** |
| After the rename | a second probe still reads D: (20,034 / 617,498); `C:\...\paksh.db` no longer exists, so anything still pointing at C: fails loudly instead of forking the data |
| Backup path | `backup_db.py --keep 5` → `BACKUP OK paksh_backup_20260921_191632.db (2269 MB, 375 s) verify: ok (events=20034, articles=617498)` |
| Old backups relocated | 13 files (5 daily, 1 pre-recount, 7 ad-hoc) copied to D: and **sha256-verified against the C: originals** (all equal). Only then were the 12 duplicates removed from C: — **19.3 GB freed** (C: free 32.6 → 50.2 GB). Kept on C: on purpose: `paksh.db.migration_backup` and the newest managed backup `paksh_backup_20260921_082556.db`. |
| Secrets / DB files in git | none: `git diff --cached` was scanned for keys, `*.db`, `.env`, the baseline file and `_site` before each commit |
| Tests | `test_paksh_paths.py` (new), `test_phase25b_db_backup.py`, `test_offsite_backup.py`, `test_phase42_provenance.py`, `test_source_utilization.py`, full suite (see PART 6) |

## 1.3 The SD card is slower — measured, not assumed

Benchmark (same shape as `database.insert_article`: open, PRAGMAs, insert, commit, close):

| | C: (internal) | D: (SD via USB reader) |
|---|---|---|
| per-row insert with its own connection | **12 ms** | **250–270 ms** (about 20× slower) |
| sequential write | — | 24 MB/s |
| 20,000 rows in one transaction + checkpoint | — | 1.7 s |
| `integrity_check` of the 2.4 GB DB | (72 s `quick_check`) | 590 s |

Consequence: ingest, which commits **one row per connection**, will be slower on D:. Recent cycles added 1,125–9,751 articles, so roughly **+5 to +40 min per cycle** in the worst case (bulk paths are unaffected). This is not a correctness problem and did not trip the gate (which asked for consistency and safety), but it is a real operating cost, listed under risks with the fix (reuse one connection / batch commits in `ingest`, about a day of work; it changes ingestion code, so it was deliberately **not** done here). Story Intelligence is unaffected: 4,000 stories persisted on D: in 89.5 s.

## 1.4 Honest limits

* **D: is primary working storage, not disaster recovery.** exFAT is not journaled; removing or sleeping the reader, or a power loss, while a job runs can corrupt the volume. Both the database and its backups now sit on **this one machine**. An independent **off-machine** backup is still needed: `offsite_backup.py` is complete but needs a bucket and a credentials file (owner action).
* The pipeline lock, logs, `.pipeline_baseline.json`, `ai_keys.env` and `_site/` intentionally stay on C:.
* **Known silent failure (documented, not changed; it does not block this work):** if the network or Cloudflare embeddings are down, `analyze.py` produces 0 clusters and the cycle exits 0 (seen 2026-09-21). Any monitoring should alert on "0 clusters", not on the exit code.
* The stale `Paksh  refresh` (00:30, Downloads copy) task is a harmless no-op that logs "can't open file". It was **not** touched (the active scheduler is the two tasks in PART 0.4); disable it only after you confirm in Task Scheduler that nothing depends on it.

## 1.5 Rollback

1. Delete `%LOCALAPPDATA%\Paksh\data_dir.txt` → the code uses `C:\paksh_project\paksh\paksh.db` again.
2. If nothing has run since activation: rename `paksh.db.migration_backup` (and its `-wal/-shm`) back to `paksh.db`.
3. If jobs have run on D: since, first copy the D: database back (`backup_db.py` writes a verified copy; restore per `RECOVERY.md`), otherwise C: is missing those days.

---

# PART 2 — Story Intelligence v1: model and algorithm

## 2.1 The data model (minimal, additive, one isolated module)

Six tables, created by `story_intelligence.init_si_schema()` (never by `database.init_db()`), keyed by the existing `events.id` / `articles.id`: **no new ID space, no change to `events` or `articles`**.

| Concept | Where it lives |
|---|---|
| **Article** (one page a publisher published) | `articles` (existing) |
| **Publisher / owner / lean** | `sources.py` (existing, editorial): never touched, never inferred |
| **Story** | `events` (existing) |
| **Reporting event** (one independent act of reporting; several articles can repeat it) | `si_reporting_events` (root article, class, confidence, reason, external origin) |
| Article ↔ reporting event, role, what it derives from, evidence | `si_reporting_event_articles` |
| **Development** (a typed change) | `si_developments` (`event_time` NULL unless stated · `published_at` · `first_seen_at` · `detected_at`) |
| **Claim** (a quantity a report states) | `si_claims` |
| **Relationships** (`SAME_REPORTING_EVENT`, `DERIVED_FROM`, `INDEPENDENT_CORROBORATION`, `NEW_DEVELOPMENT`, `UPDATES`, `CONTRADICTS`) | `si_relationships` (story↔story links stay in the existing `event_relationships`) |
| Idempotency state | `si_story_state` (input signature + engine version) |

Evidence is stored as JSON on every row (similarity, matched cue, novel figures, order basis). Nothing is a claim of truth.

## 2.2 Retrieve → Judge → Update (reuse, not rebuild)

* **Retrieve:** Phase 21's between-story retrieval (`context_retrieval`) is unchanged; it is where between-story links come from (`event_relationships`, exposed by `StoryGraph.related_stories()`). The gap was *inside* a story, so the new retrieval is "the cached-embedding nearest earlier article **of the same story**", bounded by `MAX_ARTICLES = 80` per story: **never O(N²) over the corpus**, and **no LLM per pair** (there is no LLM in v1 at all).
* **Judge:** rules with explicit thresholds (below). **Update:** one transaction per story, upsert on natural keys, `detected_at` preserved, rows of articles that left a story removed, and the story skipped entirely when its input signature is unchanged.

## 2.3 Independence (each article versus the **earlier** articles of its story)

First matching test wins. Classes: `INDEPENDENT`, `DERIVED`, `ATTRIBUTED_REPETITION`, `UNCERTAIN`.

| # | Test | Class · reason | Notes |
|---|---|---|---|
| 1 | Names an outlet that is in the story (`according to NDTV`) | ATTRIBUTED_REPETITION · `ATTRIBUTED_TO_OUTLET_IN_STORY` | edge to that article |
| 2 | Names an outlet not in the story, or a wire tag (`(PTI)`, `- ANI`, `Reuters`…) | ATTRIBUTED_REPETITION · `…NOT_IN_STORY` / `WIRE_ATTRIBUTION` | all articles citing the same external origin form **one** reporting event |
| 3 | Secondhand cue (`media reports say`, `reportedly`, `sources said`) | ATTRIBUTED_REPETITION · `SECONDHAND_CUE` | |
| 4 | Same **owner** as an earlier article | DERIVED · `SAME_OWNER` | **voice accounting only** ("one vote per owner"): means *no additional voice*, **not** "copied" (`evidence.kind = voice_accounting`) |
| 5 | Near-duplicate text (token Jaccard ≥ 0.70 or cosine ≥ 0.965; cross-language ≥ 0.96) | DERIVED · `NEAR_DUPLICATE_TEXT` | skipped if the two state different figures |
| 6 | Same language, cosine ≥ **0.80**, figures not in conflict | DERIVED · `RESTATES_EARLIER_REPORT` | same facts restated; copied vs re-reported cannot be told from headlines |
| 7 | First article of the story | INDEPENDENT · `EARLIEST_IN_CORPUS` (conf ≤ 0.5) | means "no earlier report in Paksh to derive from" |
| 8 | No earlier article in this language | UNCERTAIN · `CROSS_LANGUAGE_NO_TEXTUAL_BASIS` | never guessed |
| 9 | cosine 0.76–0.80 | UNCERTAIN · `POSSIBLE_PARAPHRASE` | |
| 10 | cosine ≥ 0.70 **and** a numeric fact no earlier report carried | INDEPENDENT · `NEW_SPECIFIC_FIGURES` (0.5–0.65) | numbers are canonicalised (`Four` = `4`, `$5K` = `$5,000`, `260mn` = `260 Million`, Devanagari digits) so formatting never looks like a new fact |
| 11 | cosine ≥ 0.70, nothing new | UNCERTAIN · `NO_POSITIVE_EVIDENCE` | a different publisher alone proves nothing |
| 12 | cosine < 0.70 | UNCERTAIN · `LOOSELY_RELATED` | a feature / angle / related piece, never "independent" |

Outlet names inside headlines are stripped before deciding what is "new". Title-Case headlines contribute numbers only (capitalisation carries no information there). Reporting events are the connected components of these links; an event's class is its root's class.

**Explicit non-claims** (encoded in the vocabulary and asserted by tests): a different publisher ≠ independent · "independently reported" ≠ verified true · `CONTRADICTS` ≠ false · more coverage ≠ a development. Nothing here touches lean labels or the bias bar.

## 2.4 Developments

A development is a **strict, typed cue in the headline** (arrest, resignation/removal, court/legal order, investigation launched, official denial/clarification, formal policy decision, resolution/restoration, escalation/curfew/riot; extensible via `register_development_type`) that **no earlier article carried even in a lenient form** (`held` counts as an arrest already reported; `SC` = `Supreme Court`; `banning` = `bans`), that the story did not begin with, from an article clearly about the same event (cosine ≥ 0.75 to an earlier article), and that is not an opinion piece, question or hypothetical (`Opinion |`, `?`, `calls for`, `could`, `if`…). Plus **`FIGURE_UPDATE`** when a person-count tally (deaths / injured / arrested / missing) rises with a clear order. Confidence rises with the number of distinct owners carrying the cue (0.45 → 0.9). "More coverage" cannot be emitted by construction.

## 2.5 Chronology

`published_at` = the publisher's claim (raw string preserved) · `first_seen_at` = the article's `fetched_at` · `detected_at` = when the row was first derived (never rewritten) · `event_time` = **always NULL in v1** (never inferred). Ordering uses the publish time if it is a full time and not later than the fetch time (+10 min); a date-only claim is `published_date`; a claim from the future (2.7 % clock skew) falls back to `fetched`. `order_basis` is stored, and derivations between two articles whose order is ambiguous (date-only on the same day, or < 60 s apart) carry `order_ambiguous` and lower confidence. The result does not depend on input order (tested).

## 2.6 Figures

Every quantity is stored as a claim, but **only person-count tallies are compared** (deaths / injured / arrested / missing): the first `%` or `₹` in a headline rarely refers to the same measure across reports (`18 %` vs `17.5 %` is rounding; `Rs 72 cr` vs `Rs 86 cr` is a time series). Values are grouped, one edge per discrepancy: `UPDATES` (rising, clear order) or `CONTRADICTS` ("two reports state different figures; this does not say which is right"); values within 5 % of each other above 100 are treated as rounding.

---

# PART 3 — The internal story graph (Phase 7)

`story_graph.StoryGraph(conn, event_id)` is read-only, answers empty (never an error) for a story that has not been analysed, and every answer carries confidence + evidence. Verified on live data (story 22148, "Deadly bombing at Pakistan police mosque…").

| # | Question | Method | Live example |
|---|---|---|---|
| 1 | Which reports are independent? | `independent_reports()` | Washington Post (`EARLIEST_IN_CORPUS`, 0.5) and Gulf News (`NEW_SPECIFIC_FIGURES`, 0.55) |
| 2 | Which merely repeat or derive from others? | `derived_reports()` | role, reason, target, evidence per article |
| 3 | What does this article derive from? | `derives_from(article_id)` | in-story article, or an external origin such as `PTI` |
| 4 | Which report came first, on what basis? | `earliest_report()` | states the order basis and "not necessarily the first report anywhere" |
| 5 | What changed over time? | `developments()` | `FIGURE_UPDATE deaths 21 → 31` |
| 6 | Where do figures update or disagree? | `figure_changes()` | `UPDATES` / `CONTRADICTS` with supporting article ids |
| 7 | Which developments are single-source vs corroborated? | `development_corroboration()` | split by number of distinct owners |
| 8 | Which other stories is this related to? | `related_stories()` | reads the existing `event_relationships` |
| 9 | What is the chronology? | `timeline()` | reports + developments, with `published_at` / `first_seen_at` / `detected_at` / `event_time` kept separate |
| 10 | Provenance of an article? | `provenance(article_id)` | article → publisher → owner → lean → reporting event → external origin |

`summary()` counts **independent origins separately from articles** (on a scratch copy of real stories, one 45-article story had 15 reporting events, 2 independent and 13 uncertain), which is the number the future UI should lead with.

---

# PART 4 — Evaluation (Phase 8)

**Method (and what it is not).** Sample: stratified random draw of recent stories (last 30 days) by size, seeded and reproducible (`evaluate_story_intelligence.py`). **Tuning set:** 150 stories / 1,879 articles (seed 7). **Hold-out:** 60 different stories / 704 articles (seed 99, drawn *excluding* the tuning stories), judged on the **frozen** engine. Ground truth is **inspection by the engineer (Claude) of headline + excerpt**, the only text Paksh stores; it is not editorial verification of the underlying news and is not an independent second rater. Items whose visible text could not settle the question are counted **unclear** and excluded from precision (never counted as correct). Sample sizes per category are small (single or double digits for some), so treat percentages as indications, not measurements.

## 4.1 Results on the frozen engine

| Judgement | Tuning set (inspected → ok / wrong / unclear) | Hold-out (ok / wrong / unclear) |
|---|---|---|
| `DERIVED / RESTATES_EARLIER_REPORT` (cos ≥ 0.80) is really a restatement | 88 → 84 / 1 / 3 (**98.8 %** of decidable) | 26 → 25 / 1 / 0 (**96 %**) |
| `DERIVED / NEAR_DUPLICATE_TEXT` | 10 → 10 / 0 / 0 | 6 → 6 / 0 / 0 |
| `ATTRIBUTED_REPETITION` (wire / named / secondhand cue) | 16 → 13 / 0 / 3 | 4 → 1 / 0 / 3 |
| `INDEPENDENT / NEW_SPECIFIC_FIGURES` adds figures no earlier report had | 50 → 41 / 2 / 7 (**95 %**; both errors fixed afterwards by number canonicalisation) | 10 → 3 / 0 / 7 |
| `INDEPENDENT / EARLIEST_IN_CORPUS` is a genuine first report of the event | 22 → 18 / 3 / 1 (**86 %**) | 14 → 10 / 2 / 2 (**83 %**) |
| `UNCERTAIN` is a *correct abstention* (not a restatement or clear independent report) | 26 → 14 / 11 / 1 (**56 %**) | 24 → 14 / 10 / 0 (**58 %**) |
| Developments (after tightening) | 8 → 6 / 2 / 0 (**75 %**) | 4 → 3 / 0 / 1 |
| Figure edges (`UPDATES` / `CONTRADICTS`) | 10 → 8 / 2 / 0 (**80 %**) | 4 → 2 / 0 / 2 |

Reading the table honestly:

* **Where it is trustworthy:** `DERIVED` by restatement or near-duplicate text (≈ 98 %: 123 of 125 decidable, 130 inspected) and the attribution classes (no wrong calls in 14 decided).
* **Where it deliberately abstains:** roughly **40 % of `UNCERTAIN` articles were actually restatements** the engine declined to call (false negatives), and 14 of the 60 `NEW_SPECIFIC_FIGURES` calls (7 in each set) could not be checked because the new figure sat in an excerpt too long to show in the review. This is the price of "a sparse, accurate graph beats a dense one". Independence *cannot* be established from ~100-character excerpts, which is why `INDEPENDENT` is reserved for "earliest in corpus" and "adds new figures", and never claims "verified".
* **`SAME_OWNER`** (the largest DERIVED bucket, 39 % of articles) is accounting, not derivation: in 16 inspected, only about 4 were rewrites of the same publisher's earlier piece; the other 12 were separate pieces by one publisher. It says "no additional voice", which is exactly the one-vote-per-owner rule.
* **Developments and figures are the weakest parts** (n small, 75–80 %): first rules gave 46 % precision (22 ok / 26 wrong of 48 decidable), so they were tightened (typed cues only, lenient baseline, opinion/hypothetical filters, same-event check, no `%`/money comparison); recall dropped from 52 to 8 developments per 150 stories. A wrong or missing development is cheaper than an invented one.

## 4.2 The other requested measures

| Measure | Result |
|---|---|
| Retrieval | The within-story scan is exhaustive over ≤ 80 earlier articles, so candidate **recall = 100 % by construction**; precision of the *chosen* nearest article is the restatement precision above (≈ 98 %). Between-story retrieval (`context_retrieval`) is reused unchanged and was **not re-measured** here (see the Phase 21D report). |
| Same-story accuracy | Not a clustering evaluation. Of 21 `LOOSELY_RELATED` articles inspected, about 5 were plainly a *different event* placed in the story (grab-bag members: e.g. a Montreal ID-fraud case inside a Toronto story, Taiwan and Gaza items inside a Nepal-flood story). `LOOSELY_RELATED` is 18 % of articles, so an order-of-magnitude estimate is **~4 % of articles are mis-clustered**. The engine never lets such articles create "independent" or "development" rows (cos gates), but clustering is unchanged and out of scope. |
| Chronology | 94.8 % of articles ordered by a full publish time, 5.2 % by a date-only claim, 0 needed the fetch-time fallback in these samples; **0 of 1,463 derivation links point to a later article**; 38 (2.6 %) are flagged `order_ambiguous` and carry reduced confidence; order is independent of input order (tested). |
| False-relationship rate | content `DERIVED_FROM`/attribution edges ≈ 2 % (2 wrong of 139 decidable) · developments ≈ 18 % (2 of 11 decidable) · figure edges ≈ 17 % (2 of 12 decidable). Small n for the last two. |
| Cost / LLM calls | **0 LLM calls per story** (deterministic; no API key, no rate limit). |
| Runtime | engine ≈ **5.6 ms/story** in memory; end-to-end on the live SD-card DB **22 ms/story** (4,000 stories, incl. loading vectors and persisting, 89.5 s). A 200-story cycle step takes ~2 s. |
| Density | tuning set: 1.2 independent origins per story (of 5.5 reporting events, 12.5 articles) — sparse on purpose. |

## 4.3 What the live backfill produced

`py story_intelligence.py --recent 30 --limit 4000 --persist` (under the pipeline lock, on `D:`): 4,000 stories → 14,805 reporting events, 31,039 article rows (independent 4,560 · derived 16,228 · attributed 135 · uncertain 10,116), 160 developments, 2,063 claims, 33,314 relationships. Re-running was a no-op (idempotent). Nothing in `events`, `articles`, `_site` or the published bias bar was touched.

---

# PART 5 — Production integration (Phase 9)

* `refresh.py` gains **`OPTIONAL_AFTER_ANALYZE`** and `run_optional()`: after `analyze.py`, run `story_intelligence.py --cycle`. `run_optional` catches every failure and timeout (600 s) and **continues**; the step itself is bounded (`limit=200` newest-updated stories, `budget_s=180`), prints a one-line summary, and **always exits 0**. `run_cycle_step()` returns `{"error": …}` instead of raising. Graceful degradation is tested (`TEST 11`): a dead DB connection cannot stop a cycle. The step never touches `_site`, never publishes, and the site is byte-identical with or without it.
* It runs inside the existing `runlocked` window of the nightly job (same DB, same lock): no new lock, no new process class.
* Activation cost: nothing to configure; the schema is created on first run (`CREATE TABLE IF NOT EXISTS`).
* **Disable:** revert the `refresh.py` commit (or empty `OPTIONAL_AFTER_ANALYZE`); the `si_*` tables are ignored by everything else and can be dropped (`DROP TABLE si_*`).
* Backlog: each cycle handles the 200 most recently updated stories whose input changed; the first 30 days were backfilled above.

---

# PART 6 — UI technical contract for a future "Story Evolution" view (Phase 10 — contract only, no UI built)

**Export (proposed, not implemented):** one small static file per analysed story, `/data/story-intel/<event_id>.json`, written by a new non-fatal `export_story_intel()` beside `reader_context` in `export_static.py` (absolute path, same rule as every other `/data/` fetch; **the pre-rendered story HTML, JSON-LD and SEO stay untouched**), fetched lazily by the story page only when the section is opened. 404 or absent ⇒ the section is simply not rendered.

```json
{ "schema": 1, "engine_version": "si-1", "event_id": 22148, "generated_at": "2026-09-21T19:58:39Z",
  "summary": { "articles": 2, "reporting_events": 2, "independent_origins": 2, "uncertain_events": 0, "developments": 1, "figure_disagreements": 0 },
  "sources": [ { "article_id": 604496, "publisher": "The Washington Post", "role": "INDEPENDENT", "reason": "EARLIEST_IN_CORPUS",
                 "confidence": 0.5, "derives_from": null, "external_origin": null,
                 "published_at": "2026-09-19T00:45:15+00:00", "first_seen_at": "2026-09-20T16:06:44", "order_basis": "published", "url": "https://…" } ],
  "timeline": [ { "kind": "report", "article_id": 604496, "published_at": "…", "first_seen_at": "…" },
                { "kind": "development", "type": "FIGURE_UPDATE", "text": "deaths: 21 → 31", "confidence": 0.7, "corroborating_owners": 1,
                  "published_at": "…", "event_time": null } ],
  "figures": [ { "key": "deaths", "kind": "UPDATES", "earlier": { "value": 21, "article_ids": [604496] }, "later": { "value": 31, "article_ids": [607395] } } ] }
```

**Behaviour rules the UI must follow**

1. **Lead with independent origins, not article counts** ("2 independent reports, 13 unclear, 45 articles"). Never label anything "verified", "confirmed", "true" or "false"; the only permitted words are those in the vocabulary table.
2. **Show uncertainty as a first-class state**: `UNCERTAIN` is rendered as "not enough information to say", never hidden, never coloured like independent.
3. **Time honesty**: three separate labels — "published" (the outlet's claim), "first seen by Paksh", and (only when non-null) "event time". Never show a derived date as if it were an event date. `order_basis ≠ published` or `order_ambiguous` ⇒ show "order approximate".
4. **Figures**: show both values and their sources, wording "reports differ: 2 vs 3" — never "wrong".
5. **Developments** appear only if `confidence ≥ 0.6` or `corroborating_owners ≥ 2` in the default view; the rest behind "show all". Cap the default list (≤ 8 items) and paginate.
6. **Bias bar is untouched.** This section has no lean colouring and never feeds the arithmetic bar (one vote per owner is still decided only by `sources.py` + `analyze.postprocess`).
7. **Bilingual:** labels come from the app's existing EN/HI string table (one entry per reason/type below); article titles reuse the existing per-language fields; the export carries no free-form English prose the UI must translate except `development.text`, which the export should render from a template per type in both languages.
8. **Empty / partial / stale:** absent file ⇒ no section; `schema` or `engine_version` unknown ⇒ no section (forward compatible); a story updated after `generated_at` ⇒ show "as of <time>".
9. **Performance & layout:** file ≤ ~20 KB per story (≤ 80 articles); no layout shift (reserve height, skeleton); works at 375 px width with no horizontal scroll; keyboard and screen-reader order follows chronology; no colour-only encoding of roles (icon + text).
10. **Never client-side derive intelligence.** The browser only renders the file.

| Vocabulary (EN) | Key |
|---|---|
| "First report Paksh saw" | `INDEPENDENT` + `EARLIEST_IN_CORPUS` |
| "Adds new figures" | `INDEPENDENT` + `NEW_SPECIFIC_FIGURES` |
| "Repeats an earlier report" | `DERIVED` + `RESTATES_EARLIER_REPORT` / `NEAR_DUPLICATE_TEXT` |
| "Same publisher group" | `DERIVED` + `SAME_OWNER` |
| "Reported via <origin>" | `ATTRIBUTED_REPETITION` |
| "Can't tell if independent" | `UNCERTAIN` (any reason) |
| "Reports differ on figures" | `CONTRADICTS` |
| "Figure changed" | `UPDATES` / `FIGURE_UPDATE` |

---

# PART 7 — Risks, limits, next step

1. **SD-card storage** (biggest): not journaled, removable, ~20× slower on single-row ingest, same machine as the database. Needs (a) off-machine backup credentials, (b) an ingest change to commit in batches, (c) a rule not to remove/sleep the card during runs. The guard makes a missing card fail loudly instead of publishing from an empty DB.
2. **Independence is bounded by the text Paksh stores** (mean excerpt ≈ 100 characters, no article body). `UNCERTAIN` is the honest answer for about one article in three, and about 40 % of those are false abstentions. Fetching article bodies for a bounded set of stories would raise both precision and recall and is the natural v2 (with the fair-use / robots questions that implies, an editorial decision).
3. **Developments and figures are the least reliable outputs** (n ≈ 12–14 inspected per set); keep them out of any public UI until re-measured on a larger sample or with an LLM judge behind a strict evidence rule.
4. **Clustering grab-bags** (~4 % of articles) are unchanged; a follow-up could use `LOOSELY_RELATED` as a membership-quality signal.
5. **Autopush**: `paksh_paths.py` and the `refresh.py` step are committed on `main`; the next nightly run will push them. Both are inert for the website.
6. **Not done by design:** no new RSS/ANI/dormant feeds, no quota or merge-cap changes, no clustering rewrite, no lean labels touched, no vector DB / Redis / microservice, no new frontend.

**Recommended next step:** owner decisions on (1) an off-machine backup target, then (2) whether to spend LLM budget on a bounded, evidence-gated judge for the `UNCERTAIN` band, and (3) the Story Evolution UI against the contract above.
