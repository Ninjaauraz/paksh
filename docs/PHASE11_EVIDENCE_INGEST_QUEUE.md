# Phase 11 — Evidence Retrieval v2 · SD-card ingestion batching · Story Intelligence reprocessing queue

*2026-09-22. Evidence labels: `[MEASURED]` queried/benchmarked · `[CODE]` read from source · `[CANARY]` real pages, real network.*

---

## 11A — Audit findings (before any change) `[CODE]` `[MEASURED]`

| # | Question | Finding |
|---|---|---|
| 1 | How is article text obtained? | RSS `summary` (feedparser) and GDELT `title`; mean ≈ 100 chars, 21 % empty. **No article body is stored anywhere.** |
| 2 | Fields for evidence retrieval | `articles.url`, `title`, `summary`, `published`, `fetched_at`, `source`; cached bge-m3 vectors. |
| 3 | URL canonicalisation | `ingest.canonical_url()` strips tracking params at ingest; nothing resolves redirects afterwards. |
| 4 | Redirect handling | Only in `source_enrichment.py` (`requests` follows redirects; hop count checked *afterwards*, no per-hop validation). |
| 5 | Existing HTML fetching | **Yes, one module:** `source_enrichment.py` (Phase 22C) — fetches only `og:description` / meta description, for thin summaries, direct URLs only. |
| 6-8 | User-agent / timeouts / retries | UA `Mozilla/5.0 (compatible; PakshBot/1.0; +https://paksh.news)`; 8 s timeout; no retries; 1 s per-host delay; 3 MB cap; failure cool-down 30 days. |
| 9 | robots.txt | Yes (`urllib.robotparser`, per-process cache without TTL; a 5xx is treated as "allowed"). |
| 10-11 | Content extraction / stored content | **None for body text.** `article_enrichment` holds meta descriptions only (2,218 rows: 1,551 accepted, 408 failed, 259 rejected; top failure `http_403`). |
| 12 | Bodies elsewhere? | No. |
| 13 | Caching | `article_enrichment` (per article, versioned, failure cool-down) — reused as the pattern. |
| — | **Key discovery** | **`news.google.com` redirect wrappers are 66 % of all articles (407,329 of 617,498) and 80 % of articles in recent stories** (20,580 of 25,731). They are not fetchable without decoding/calling Google's service, which is deliberately not attempted. Only ~23 % of articles have a direct publisher URL. `source_enrichment.py` also skips them. |
| — | Libraries | `requests` and `charset_normalizer` present; **no bs4 / lxml / trafilatura** → a small stdlib extractor was written instead of adding a dependency. |
| 14-15 | Ingest writes | `ingest.py` and `gdelt_source.py` call `database.insert_article()` **once per row**, and each call = `get_connection()` (open + 3 PRAGMAs) + INSERT + commit + close. |
| 16-17 | What can be batched / depends on immediate visibility | Nothing reads inserted rows inside the run (dedup is an in-memory `seen` set + the UNIQUE(url) constraint on the same connection); `count_articles()` runs after the loop. Batchable. |
| 18-20 | Where Story Intelligence decided "needs processing"; versions; queue | `process_events()` picked the 200 most-recently-updated stories and skipped those whose `si_story_state.input_sig` was unchanged; version = `ENGINE_VERSION` in `si_story_state`; **no queue table existed.** |

---

## Part A — SD-card ingestion batching

**Change.** `database.ArticleWriter` (additive; `insert_article()` untouched) — one lazily-opened connection, commit every **200** rows and at the end of every feed / GDELT query (so the write lock is never held across a network wait). Same INSERT and columns, `fetched_at` stamped per row at call time, any `IntegrityError` returns `None`, ids and "new" counts identical; on a non-integrity error the rows already inserted are committed before it propagates (what the per-row loop had already persisted). `ingest.py` and `gdelt_source.py` use it.

**Benchmark** (`benchmark_ingest.py`, on D:, rows sampled from real recent articles, ~10 % duplicate URLs) `[MEASURED]`:

| mode | rows/s | wall (600 rows) | commits | longest transaction | equivalent to per-row |
|---|---|---|---|---|---|
| per-row `insert_article` | **9.7** | 61.6 s | 538 | — | (baseline) |
| batch 1 | 842 | 0.7 s | 538 | 0.20 s | ✔ |
| batch 25 | 2,886 | 0.2 s | 22 | 0.03 s | ✔ |
| batch 100 | 3,198 | 0.2 s | 6 | 0.03 s | ✔ |
| **batch 200 (chosen)** | **3,696** | 0.2 s | 3 | 0.03 s | ✔ |
| batch 500 | 3,459 | 0.2 s | 2 | 0.04 s | ✔ |
| batch 1000 | 3,382 | 0.2 s | 1 | 0.04 s | ✔ |

Real-size check (a 2.4 GB, 620k-row copy of the live DB on the SD card): **per-row 115 ms/row (8.7 rows/s) vs batch-200 7,315 rows/s** (3,080 rows in 0.4 s, 14 commits) ≈ **840× faster**. Throughput plateaus from batch 100; 200 keeps every lock under ~0.05 s, bounds the crash window to ≤ 200 rows (re-served by the feeds next cycle, duplicates ignored) and adds no memory of note (CPU 7.7 s → 0.0 s). A recent 4,000-article cycle that would have cost ≈ 8 min of SD-card commits now costs ≈ 1 s. Every mode was verified equal to the baseline (returned-id / `None` sequence, all columns except `fetched_at`, `fetched_at` present and non-decreasing). Tests: `test_ingest_batching.py` (boundaries, visibility to another connection, crash, failure, both real callers).

---

## Part B — Evidence retrieval v2

**Architecture.** metadata verdict (unchanged) → `needs_evidence()` per article (deterministic, reason logged) → budgeted fetch of the article's **own direct URL** → 2,000-char lede extraction → cache → deterministic re-evaluation → verdict + provenance; anything still ambiguous stays `UNCERTAIN`. **No LLM.**

**Trigger rules** (`story_intelligence.needs_evidence`, `plan_evidence`): `FETCH` only for (a) `UNCERTAIN` with `POSSIBLE_PARAPHRASE` / `NO_POSITIVE_EVIDENCE` (`uncertain_needs_text`), (b) `INDEPENDENT`/`NEW_SPECIFIC_FIGURES` (`verify_potential_independent_report`), (c) the story's earliest article (`verify_earliest_is_not_a_wire_copy`) — and only in stories with ≥ 3 distinct publishers; the nearest earlier article is added as comparison partner. `NO_FETCH` with a reason for `SAME_OWNER`, already-resolved/attributed, `LOOSELY_RELATED`, cross-language, too few publishers. A different publisher / headline / URL is never a trigger. Not implemented (documented): fetching for developments and figure edges (v2 does not consume text for them).

**Fetch policy** (`evidence_retrieval.py`): own direct http(s) URL only (news.google.com, `javascript:`/`data:`/`file:`/`ftp:`, userinfo URLs rejected); **manual redirect loop validating every hop** (public addresses only, no https→http downgrade, ≤ 4); robots.txt honoured with a 24 h cache (**unreadable = do not fetch**); PakshBot UA (same as `source_enrichment`); connect 5 s / read 8 s / **15 s total**; 1.5 MB cap; no retries; 1.5 s per host; 401/402/403/451, bot interstitials and paywall markers recorded as **blocked and never bypassed**; no login, no browser, no cookies. **Budgets** (`FetchBudget`): per cycle 30 fetches / 150 s / 20 MB (production setting `evidence_max_fetches = 30`), **6 per story**.

**Extraction:** stdlib `html.parser`; JSON-LD `articleBody` preferred, else `<article>`/`<main>` paragraphs; nav, ads, consent/cookie banners, related links, scripts, subscription promos dropped; ≤ 2,000 chars; live blogs / ticker pages rejected (`not_article`); UTF-8-safe decoding. No raw HTML stored.

**Cache** (`si_evidence`, own table, own migration): status, extraction status, HTTP status, title, text, content hash, extractor version, `expires_at`, error class, attempts, last error. TTL: ok 30 d, transient failure 3 d, blocked/gone 30 d. **A failed re-fetch never overwrites good text**; a fresh failure is not retried; nothing is fetched twice inside its TTL. Storage: 66 rows / 87 KB of text after the canaries.

**Evidence-aware verdicts** (`_apply_evidence`): a dateline or explicit citation in the fetched lede (`City, Aug 31 (PTI)`, `according to Reuters`, `- PTI`) → `ATTRIBUTED_REPETITION / FETCHED_ATTRIBUTION`; ≥ 12 shared verbatim words **outside quotation marks** with an earlier fetched article → `DERIVED / FETCHED_SHARED_TEXT`. Photo credits (`(AP: Name)`, `(AP Photo)`) are **not** attribution; two outlets quoting the same statement are **not** derived from each other. Provenance stored: `evidence_source` (`METADATA` | `FETCHED_ARTICLE`), `metadata_role` / `metadata_reason` (the v1 verdict is kept beside the new one, never erased), `evidence_version`. **With no evidence the verdicts are identical to si-1: 0 differences over 1,879 articles.** Promotion of `UNCERTAIN` → `INDEPENDENT` on fetched text was built, measured and **left OFF** (below).

### Canary results `[CANARY]`

*Round 1 (the 210 evaluation stories, scratch copy of real data, real network):* 170 fetches planned-eligible (88 stories). Defects found and fixed before anything reached production: **NAT64** — this network resolves every public host as `64:ff9b::…`, which the private-address guard wrongly refused (71 of 170 fetches, 42 %); markup inside JSON-LD bodies; live-blog / ticker pages; subscription promo text passing as article text; mojibake for UTF-8 pages without a charset header; and photo credits / quoted statements producing wrong verdicts.

*Round 2 (frozen logic, promotion off, same 210 stories)* — V1 metadata-only vs V2 metadata + fetched:

| Measure | Result |
|---|---|
| Stories / articles | 210 / 2,583 |
| Fetches (budget 200, 6 per story) | 170 (all the eligible planned ones) in 226 s, 196 HTTP requests, 52.8 MB |
| HTTP success | 131 / 170 = 77 % (30 × 403 **not bypassed**, 3 robots unreadable, 4 too large, 1 × 404, 1 too many redirects) |
| Extraction success | 111 / 170 = **65 %** usable (12 empty / JS-rendered, 5 short, 3 live-blog) |
| Cache hit rate | 0 % on the first pass by construction; second pass in the tests/queue = 100 % (no refetch) |
| **UNCERTAIN reduction** | **852 → 852 (0)** |
| Verdict changes | **3**, all *removals of false independence*: `INDEPENDENT` → `ATTRIBUTED_REPETITION` (PTI dateline) and 2 × `INDEPENDENT` → `DERIVED / FETCHED_SHARED_TEXT` (identical PTI/IANS text in two outlets). All 3 inspected: correct. |
| False independence | 246 → 243 `INDEPENDENT`; **−3 wrong, +0 new** |
| Derived / attribution precision | 3 / 3 correct on the changed items; 0 wrong |
| Development / figure precision | unchanged (v2 does not use text for them) |
| UNCERTAIN articles that had usable text | 58; 38 of them with another fetched article in the same story; **none resolved** by shared text / attribution |

*Why promotion is OFF.* In round 1 (promotion on) 14 `UNCERTAIN` articles became `INDEPENDENT` on "no shared text + own quote/figures": 3 were clearly wrong (a stock-ticker page, a live blog, an explainer), 7 could not be verified, and only ~4 looked right, while the same round produced wrong `ATTRIBUTED` calls from photo credits. By the brief's rule — *fewer UNCERTAIN with more false independence is worse* — it is disabled (`ALLOW_EVIDENCE_INDEPENDENCE = False`); the code path remains, covered by a test, for a future evidence-gated judge.

*Production canary (D:, live database, evidence enabled with `--max-fetches 40`):* 60 stories → 36 fetches (25 usable, 3 × 403, 1 timeout, 1 redirect loop, 4 empty, 1 short, 1 not-article), 9.3 MB, 172 s; **1 verdict change** (an Euronews `INDEPENDENT` that cites the Associated Press in its lede → `ATTRIBUTED_REPETITION`, correct). Of 540 planned fetch targets in the live plan, **472 (87 %) were `news.google.com` links and could not be fetched** — the real ceiling of this approach.

**Interpretation.** Evidence retrieval works, is safe and bounded, and removes a small number of false-independence calls (about 1 per 60–70 stories examined). It does **not** reduce `UNCERTAIN`, because verbatim copying between outlets is rare (wire copies are the exception) and independence cannot be shown from the first 2,000 characters of two pages. The binding constraint is not the extractor or the rules but **eligibility: 66–80 % of articles have no fetchable URL.**

**Would an LLM judge be justified?** Not on these measurements. The class "adequate evidence exists (two fetched, comparable texts), deterministic rules cannot resolve it" is real (38 articles in 210 stories) but (a) a judge would still only compare two rewrites of shared sources, so "independent" remains unprovable, (b) it is small, (c) it needs its own precision study. **Proposal only, not implemented:** trigger = `UNCERTAIN` article with a fetched partner and no shared text; input = both ledes + headlines, no URLs; output = `SAME_REPORT / DIFFERENT_REPORTING / CANNOT_TELL` + quoted evidence; hard rule "CANNOT_TELL is the default; independence only with a quoted sentence-level difference"; est. 1 call per qualifying article ≈ 5–20 per night at ~1.5k tokens ≈ well under $0.05/night; failure = keep the metadata verdict; evaluation = blind labelling of ≥ 100 pairs vs the deterministic baseline, with false-independence as the veto metric. Recommended **only after** the eligibility ceiling is addressed.

---

## Part C — Reprocessing queue (`si_queue.py`)

**Schema:** `si_queue(event_id PK, status, reason, priority, enqueued_at, engine_version, requested_sig, started_at, finished_at, attempts, last_error, next_attempt_at, outcome, updated_at)` and `si_control(key, value)` (flags `paused`, `evidence_enabled`, `evidence_max_fetches`).

**States:** `QUEUED → PROCESSING → PROCESSED`; failure → `RETRY` (next attempt after 15 · 30 · 60 · 120 min, cap 24 h) → after 5 attempts `FAILED` (manual `retry`). A `PROCESSING` row older than 30 min (crashed run) is recovered to `QUEUED` (`STALE_RECOVERED`). `PROCESSED` rows are the audit trail (pruned after 14 days). Rows and `si_*` data of stories removed by consolidation are pruned.

**Triggers** (cheap prefilter in SQL, confirmed by the input signature at processing time): `NEW` (no state) · `MEMBERSHIP_CHANGED` (article count differs: new article, merge, split) · `STORY_UPDATED` (`events.updated_at` > last verified) · `ENGINE_VERSION` (state made by another engine) · `EVIDENCE_UPDATED` (new evidence for the story's articles) · `EVIDENCE_PENDING` (evidence is on and the story has not been planned under the current logic) · manual. A story already queued/processing/retrying is never queued twice; an unchanged signature is recorded as outcome `unchanged` and `computed_at` moves forward, so nothing re-queues in a loop.

**Priority** (deterministic, engineering only — no topic, politics or outlet): recency (≤ 24 h 300, ≤ 72 h 200, ≤ 7 d 100) + 50 if articles joined + 30 evidence updated + 5 per distinct publisher (max 10) + 40 if currently published + 30 if it had unresolved `UNCERTAIN` articles. Ties: `enqueued_at`, `event_id`.

**Engine version handling:** `ENGINE_VERSION = si-2`; the input signature includes the engine version and (when present) an evidence hash. The 4,000 existing `si-1` stories are re-queued as `ENGINE_VERSION` and drained by the normal budget (metadata-only results are identical, so this is harmless bookkeeping).

**CLI** (under the existing `story_intelligence.py`; write commands take the existing pipeline lock via `runlocked`): `queue --status|--list`, `enqueue --event N | --recent N | --scan | --engine-version`, `process --limit N [--evidence|--no-evidence]`, `retry --limit N`, `pause`, `resume`, `inspect --event N`, `evidence --enable|--disable|--max-fetches N`.

**Cycle** (`refresh.py` optional step → `story_intelligence.py --cycle` → `si_queue.run_cycle`): scan (≤ 400 candidates) → process ≤ 200 stories within 180 s → evidence only if enabled, ≤ 30 fetches / 150 s. Budget exhausted → stop cleanly, return unstarted claims to `QUEUED` untouched, never mark unfinished work processed, never reset the queue. Non-fatal (`run_cycle` never raises; `run_optional` swallows any failure/timeout).

**Measured on the live SD-card DB:** 200 stories processed in 9.1 s (metadata-only); a full production-shaped cycle with evidence on: scan 400 → claimed 200 → 165 processed + 13 unchanged + 22 returned to the queue at the 180 s budget, 30 fetches, 9.5 MB, 3 min 4 s wall, exit 0.

---

## Testing

New: `test_ingest_batching.py` (18 checks), `test_evidence_retrieval.py` (URL policy, robots, HTTP statuses, size cap, timeout, bot interstitial, redirect safety incl. loopback/private/javascript/downgrade/chain, extraction, NAT64 address guard, live blog, markup, encoding, paywall promo, cache hit/expiry/stale/failure retention/no duplicate fetch, budgets), `test_si_queue.py` (enqueue/dedupe/priority/processing/success/failure/retry/backoff/stale/engine-version/evidence trigger/bounded/paused/prune/idempotency/evidence in queue with fake pages/pipeline hook), `test_story_intelligence.py` TEST 5b and 12 (metadata-only unchanged, shared text, attribution, quoted statement, photo credit, promotion off by default, provenance, signature, trigger decisions). **Full suite: 49/49** (was 46). Regression: metadata-only verdicts identical to the frozen si-1 sample (0 / 1,879); no change to clustering, lean, source selection, publication, bias bar, export or `_site` (no file under `_site/` changed).

## Production state after this phase

* Ingestion batching: **in the working tree and committed** — the next nightly run uses it.
* Queue: **active** through the nightly's optional step (metadata processing, non-fatal).
* Evidence retrieval: **enabled, tightly bounded** (`evidence_enabled=1`, 30 fetches / 150 s per cycle). Reversible in one command: `py story_intelligence.py evidence --disable` (queue keeps working metadata-only). Promotion to `INDEPENDENT` stays off.
* Live numbers: queue `PROCESSED 225 · QUEUED 762`; `si_story_state` si-2 300 / si-1 3,700 (draining); `si_evidence` 66 rows, 87 KB of text; database +1 MB since the SI backfill (2.407 GB).

## Risks and limits

1. **Eligibility ceiling** (the important one): 66 % of the corpus (80 % of recent stories) are Google News redirect links that are not fetched by design; evidence can only ever help the remaining ~20–25 %.
2. **Extraction limits:** 65 % usable; JS-rendered pages, paywalls and bot protection (HTTP 403 ≈ 18 %) are skipped, not bypassed. Only the lede (≤ 2,000 chars) is kept.
3. **Copyright / fair use:** internal analysis only, ≤ 2,000 chars per article, no HTML, nothing published or shown; still an editorial/legal call for Sameer before raising limits or exposing text.
4. **robots / access:** robots.txt honoured (unreadable = no fetch); no login, no paywall or bot-check circumvention; PakshBot identifies itself.
5. **Network dependency:** all evidence work is optional and non-fatal; the existing silent network-outage behaviour of `analyze.py` (0 clusters, exit 0) is unchanged and undocumented-fix.
6. **Database growth:** evidence ≤ 2 KB/article, bounded by 30 fetches/night ≈ < 100 KB/night; queue rows small; backlog of older stories (~16k) will keep being enqueued 400/night and drained at 200/night (older stories last).
7. **SD card:** unchanged risk — removable exFAT, not journaled, same machine; batching removes most SD write pressure but off-machine backup is still open (`offsite_backup.py` needs credentials).
8. **Queue backlog:** 762 queued now; the ENGINE_VERSION drain finishes in ~20 nights at 200/night (raise `limit` if desired).

## Recommended Phase 12 (only what the measurements justify)

1. **Not the LLM judge yet.** The deterministic evidence pass resolved 0 of 852 `UNCERTAIN` articles; a judge would face the same "independence is unprovable" ceiling on the same small eligible slice.
2. **Address eligibility:** a decision for Sameer on resolving Google News links (publisher URL via the RSS `source` element or the article page Google serves) — it decides whether evidence can ever matter at scale; low-risk options first (measure how many `<source>` URLs the feeds already carry).
3. Off-machine backup credentials (still the largest operational risk).
4. Only then: a Story Evolution UI against the contract in `STORAGE_AND_STORY_INTELLIGENCE.md` PART 6, leading with `independent origins`, without developments/figures until re-measured.
