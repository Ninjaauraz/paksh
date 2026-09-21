# Intelligence Program — Phase 12: Publisher-URL recovery + provenance hardening · 12B: off-machine backup & storage audit

*2026-09-22 · `[MEASURED]` live database · `[CODE]` source · `[PROBED]` live system.*

## STATUS: **PASS** (12) · **CONDITIONAL** (12B: audit done, no off-machine target configured — needs your credentials)

## What was discovered

**How `news.google.com` URLs enter the database** `[CODE]` `[MEASURED]`: 112 feeds in `feeds.py` are Google News *search* RSS queries (`site:<publisher>`), read by `ingest.py` via feedparser and stored through `normalize_entry` with `url = canonical_url(entry.link)`. The RSS item carries exactly: the wrapper `<link>`, a `<guid>` that is the same opaque id, `<source url="https://thewire.in">` (the publisher's **home page only**), and a description that repeats the wrapper link. There is **no article URL anywhere in the feed**. GDELT articles already carry real URLs. Corpus now: **407,329 wrapper articles (66 %)**.

**Offline decoding is impossible** `[MEASURED]`: in 1,500 sampled wrapper ids (500 recent, 500 mid, 500 older) **100 %** are the new opaque `CBMi…AU_yqL…` format — no URL can be read from the id. (Nothing was fetched, unwrapped or redirected; the constraint list stands.)

**The one legitimate source of a real URL** is the *same article arriving a second time through a direct feed or GDELT* — real URL, same publisher, identical headline, same time. Exact normalised-title match with the same `source` gives 15–17k candidates (4 %), concentrated in publishers that have both feed types (Al Jazeera 40 % of its wrapper articles, Japan Times 60 %, Hindu BusinessLine 40 % …). Fuzzy matching adds almost nothing (Al Jazeera's unmatched wrapper articles have best token-Jaccard < 0.3: the direct feed simply does not contain them).

## What was implemented

`publisher_url.py` (method `pu-1`) + additive table **`article_publisher_url`** (article_id, original_url, publisher_url, status, method, matched_article_id, confidence, time_gap_s, domain_consistent, verified_at, method_version). `articles.url` is never touched. Recovery needs **all** of: same publisher · identical normalised headline of ≥ 4 words · published/first-seen within 72 h (**6 h** if that headline is shared by several different URLs) · exactly one distinct candidate URL (else `AMBIGUOUS`, nothing used) · candidate host belongs to that publisher in the source registry when the registry knows the host (else `REJECTED_DOMAIN`). No row is written for an unrecovered article ("no sibling yet" is not a fact; a sibling can arrive later). Nightly hook: `si_queue.run_cycle` calls `recover_recent(days=3)`, non-fatal.

**Evidence integration** (justified by measurement, below): `get_evidence` uses the stored URL when fetchable, otherwise a `VERIFIED_SIBLING` publisher URL, **never a wrapper**; `si_evidence` now records `url` (the one fetched), `url_source` (`ORIGINAL` | `PUBLISHER_URL`) and `original_url`. The story input signature includes verified publisher URLs, and a newly verified URL re-queues the story (`EVIDENCE_UPDATED`).

**12B (audit + two small safeguards):** `paksh_paths.storage_status()` / `py paksh_paths.py --check` (filesystem, removable, free space, guard state, stale-repo-copy warning; exits 1 when the configured data location is unusable); `backup_db.py` now **refuses to start a backup that cannot fit** (needs DB × 1.2 + 1 GB free) before writing anything.

## What was NOT implemented

No decoding, unwrapping, browser, cookie or third-party service (all prohibited); no fuzzy title matching (adds ~nothing, adds false-mapping risk); no permanent "not recoverable" markers; no upload of any data off-machine (no target is configured); no change to clustering, sources, quotas, lean or publication.

## Dataset and evaluation method

Recovery run **read-only over all 407,329 wrapper articles**, then a **5,000-article write canary** (2,500 recent + 2,500 older, random), then the full 17,255-row backfill. Correctness was checked three ways: (1) automatic invariants over every recovered row; (2) an independent signal — the URL slug vs the headline (median token overlap 0.90; the low-overlap English cases are FT/Atlantic opaque ids or editorial slugs); (3) **manual inspection of 68 pairs** chosen to be the riskiest (short headlines ≤ 6 words, gaps > 6 h, low slug overlap).

## Results

| Measure | Result |
|---|---|
| Coverage (recovered / wrapper articles) | **17,255 / 407,329 = 4.24 %** (recent 5.4 %, older 2.9 %); canary 227 / 5,000 = 4.5 % |
| `AMBIGUOUS` (deliberately unused) | 122 |
| `REJECTED_DOMAIN` | 0 (every verified URL is on a host the registry attributes to that same publisher: 100 % domain-consistent) |
| Unresolved | 389,952 (95.7 %) — correct: no legitimate source exists |
| **Verified accuracy / false recovery** | **0 wrong of 68 manually inspected risky pairs** (95 % upper bound ≈ 4 %); structural guards make same-publisher / same-headline / ≤ 72 h the only path |
| Original URLs preserved | 0 mismatches between `original_url` and `articles.url` |
| Recovered URL that is itself a wrapper | 0 |
| Duplicate risk | 2 recovered URLs shared by two wrapper rows in the 5,000 canary (two wrapper rows of one article) |
| Time gap | ≤ 1 h 12,468 · ≤ 24 h 4,706 · ≤ 72 h 86 |
| Same story as the sibling | 11,844 same story · **5,416 different story** (see below) |
| Runtime / storage | 8.7 s for all 407k articles; table ≈ 3–4 MB (DB +9.6 MB incl. WAL) |
| **Evidence eligibility** (210 evaluation stories) | planned fetch targets 725: 170 direct-URL, 555 wrapper, **40 recoverable → eligible targets 170 → 210 (+23.5 %)**; 87 % → 80 % of targets remain unfetchable |
| Live evidence canary (40 stories, budget 30) | 30 fetches, 13 used a `PUBLISHER_URL` (10 usable, 2 blocked, 1 failed); 5 evidence-driven verdict corrections now in the production table, 1 of them from the Phase 11 canary (2 `INDEPENDENT`→`ATTRIBUTED`, 1 `UNCERTAIN`→`ATTRIBUTED`, 2 `UNCERTAIN`→`DERIVED/FETCHED_SHARED_TEXT`) |

**Side finding (data quality, not acted on):** 5,416 recovered pairs put the *same article* into **two different stories** (wrapper row in one, direct row in another) and ~11.8k are the same article twice inside one story (same owner, so the bias bar is unaffected). Clustering is out of scope for this program; the finding is recorded for a future clustering-quality phase.

**Interpretation.** Recovery is accurate but small: 4 % of the corpus, +23 % more fetchable evidence targets, no effect on the 80 % of wrapper targets. The eligibility ceiling identified in Phase 11 **cannot be lifted by legitimate metadata**; the program proceeds on the directly accessible subset.

## 12B — backup and storage audit `[CODE]` `[PROBED]`

| Question | Finding |
|---|---|
| Local backups | `backup_db.py` (SQLite `backup()` API, integrity_check + row sanity, strict-name retention, keep 5) runs at the end of `reframe_scheduled.bat` (07:30). Verified twice on D: (2.27 GB, ~6 min). Nightly refresh (05:30) takes none. |
| Off-machine | `offsite_backup.py` is complete: S3-compatible (Cloudflare R2 / Backblaze B2 / AWS), zlib + **AES-256-GCM** chunked with per-chunk authentication, scrypt key from `BACKUP_PASSPHRASE`, config refused inside the repo, `--check` (tiny test object), `--run` (upload + verify + retention KEEP=7), `--restore-test` (download → decrypt → `integrity_check` → compare counts → delete temp), `--restore KEY --to …`. **It is wired but inert: `%LOCALAPPDATA%\Paksh\offsite_backup.env` does not exist**, so the scheduled job skips it. `--check` exits cleanly with the four setup steps. **Nothing was uploaded anywhere.** |
| Credentials needed | a bucket + bucket-scoped API token + a 20+ character passphrase kept in a password manager (lost passphrase = unrecoverable, by design). Owner action. |
| Restore procedure | `RECOVERY.md` and `docs/BACKUP_AND_RESTORE.md`; the D: location note was added in Phase 10. |
| D: facts | **exFAT, Removable, Healthy**, USB "Generic xD/SD/M.S." reader, 238 GB, 77 GB free (was 101 GB: backups + archive), no journaling. |
| Startup / scheduler dependence | Tasks are Interactive, `StartWhenAvailable`, no network requirement. If the card is absent at 05:30 the first `get_connection()` raises `DataDirError`, `refresh.py` exits non-zero, `&& safe_autopush.py` does not run: nothing is published from nothing. |
| Could anything fall back to C:? | No: `C:\paksh_project\paksh\paksh.db` does not exist (renamed `.migration_backup`), the data-dir file is honoured by every entry point that opens the DB (all go through `database.get_connection`), `PAKSH_ALLOW_NEW_DB=1` is the only override. Tests (`test_paksh_paths.py`) prove the failure is loud and creates nothing. `py paksh_paths.py --check` now reports this and warns if a stale repo copy ever appears. |
| Remaining risk | the single copy of everything is on a non-journaled removable card in the same machine; only an off-machine target closes that. **Decision for you: choose R2 or B2 and create the bucket + token + passphrase.** |

## Files, database, tests, rollback

* **Files:** new `publisher_url.py`, `test_publisher_url.py`, this doc; changed `evidence_retrieval.py`, `si_queue.py`, `story_intelligence.py` (signature `extra`), `paksh_paths.py`, `backup_db.py`, `test_paksh_paths.py`.
* **Database:** additive `article_publisher_url` (17,377 rows) and two additive columns on `si_evidence` (`url_source`, `original_url`). No existing table altered destructively.
* **Tests:** new `test_publisher_url.py` (24 checks); full suite **50/50** (was 49).
* **Regressions:** none observed; metadata-only Story Intelligence unchanged; `_site` untouched.
* **Rollback:** `DROP TABLE article_publisher_url` (evidence then falls back to direct URLs only); `evidence --disable`; revert the commit.

## Gate decision

**PASS.** Provenance behaviour understood, recovery accuracy measured, no dangerous mappings found, originals preserved, evidence integration safe and modestly useful, backup situation documented, tests passing. The limitation (4 % recoverable) is documented and Phase 13 continues on the subset of directly accessible evidence — which is a small part of what Phase 13 needs anyway, since most of its signals come from headlines, timestamps and figures.
