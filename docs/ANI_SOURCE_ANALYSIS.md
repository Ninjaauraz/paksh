# ANI (Asian News International) — how it fits Paksh's source ecosystem

*Investigation only. No ingestion, blocklist or registry change was made. Snapshot: 2026-09-21 00:55 UTC (611,811 articles), read-only.*
*Part of [SOURCE_DIVERSITY_PHASE2.md](SOURCE_DIVERSITY_PHASE2.md). Evidence labels: `[MEASURED]` from the DB · `[PROBED]` one live HTTP probe · `[CODE]` read from source.*

## Recommendation (evidence below)

**Do not ingest ANI as an ordinary publisher.** Treat it — if at all — as a **wire / source-of-origin**, not as an independent voice.

1. Direct ANI ingestion would **mostly duplicate** reporting Paksh already receives through other outlets (≥ 45% of ANI's headlines already appear from other outlets).
2. ANI has **no lean label**, so it could never vote; it would only inflate "outlets covering this story" with a copy.
3. There is **no discoverable feed**, so the only route would be the rate-limited GDELT tail Paksh already has.
4. What *would* add independent reporting is **detecting** wire origin so copies collapse into one reporting event. Today that is impossible because the datelines are not stored (§3). That is the piece worth building, not an ANI feed.

## 1. Is direct ANI content available? `[PROBED]` `[MEASURED]`

* **No feed.** `aninews.in` returned no items at any of six standard paths (`/feed`, `/rss`, `/rss.xml`, `/feed.xml`, `/rssfeed`, `/rss/latest`); no `<link rel="alternate">` feed was advertised.
* ANI is **not in the curated roster and not in the verified registry** (`aninews.in` is absent from `DOMAIN_TO_SOURCE`).
* It reaches the database only as an **unknown GDELT domain**: **2,188 articles** between 2026-06-23 and 2026-09-20 (≈ 24 a day — a small fraction of ANI's real output), of which **15 (0.7%) were ever attached to a story**. In the last 5 days there are 10 rows, all from 09-20, because GDELT delivered nothing from 09-12 to 09-19.

## 2. How often does ANI-originated reporting already appear through other publishers? `[MEASURED]`

Method: normalise each headline and key it on its first 12 words (robust to a trailing outlet name), across every article ever stored. This **under-counts**: it misses re-headlined copies, and ANI itself is sampled sparsely.

| | |
|---|---:|
| Distinct ANI headlines | 2,186 |
| … that also appear from **at least one other outlet** | **981 (44.9%)** |
| … from exactly 1 / 2 / 3 / 4 / 5+ other outlets | 599 / 200 / 61 / 49 / 72 |

Curated outlets that carry ANI-identical headlines, and how much of *their* output that is:

| Outlet | ANI-identical headlines | Share of the outlet's headlines |
|---|---:|---:|
| The Tribune | 166 | 1.7% |
| The Wire | 55 | 1.5% |
| Republic World | 43 | 0.7% |
| The Hindu | 33 | 0.2% |
| The Hindu BusinessLine | 18 | 0.4% |
| The Print | 14 | 0.2% |
| The Economic Times | 8 | 0.1% |

So ANI copy is already inside Paksh, mostly via a few outlets. The per-outlet shares are lower bounds because only ~24 of ANI's articles a day are visible.

## 3. Can Paksh identify ANI-originated reporting today? **No.** `[MEASURED]`

* Across **228,670** articles from the last 30 days, a wire dateline or credit is present in **36** (`PTI` 21, `IANS` 14, `AFP` 1, **`ANI` 0**) — **0.02%**. Almost all of them are Telangana Today.
* Why: stored text is only the feed's short excerpt (≤ 600 characters). **12.0%** of articles have no excerpt beyond the headline (5.2% inside published stories), Google-News-bridged titles have the outlet suffix stripped at ingest, and datelines like "New Delhi [India], Sept 20 (ANI):" live in the article body Paksh never stores.
* `source_enrichment.py` already fetches page metadata for thin excerpts, but only for the ≤ 12 articles that reach an LLM prompt and it stores only a description, not a credit line.

## 4. Ordinary publisher or wire? — how each Paksh mechanism treats a copy `[CODE]`

| Mechanism | What it does with an ANI-style copy |
|---|---|
| `cluster._dedupe_same_outlet` | removes repeats **from one outlet** only; copies across outlets pass through |
| Owner grouping (`OWNER_BY_SOURCE`) | collapses **co-owned mastheads** (e.g. Times Group); ANI copies at unrelated outlets are separate owners |
| Bias bar | **one vote per owner** — each outlet that ran the copy votes on its own lean. That is a deliberate editorial semantic (an outlet's decision to run a wire story is its own), so it is **not** changed here |
| `source_selection.select_sources` (prompt only) | collapses copies with ≥ 75% headline overlap within one lean into one report; nothing wire-aware |
| Story page | lists every article |

An ANI feed would therefore add an **unrated, non-voting** row whose content is ≥ 45% duplicated elsewhere. It would raise "outlets covering" without adding an independent voice or a lean.

## 5. Would direct ingestion increase independent reporting? — No, on the evidence

* ~45%+ of its headlines are already present; the remainder are either stories others also carry later, or ANI exclusives whose downstream copies would then arrive as *more* duplicates.
* Being unrated it cannot create a story (needs ≥ 2 rated outlets) and cannot move the bar.
* The 15 ANI articles that ever joined a story is the practical upper bound of today's value.

## 6. What is worth building instead (proposal, not implemented)

**Wire-origin detection** so that *N copies of one wire item* count as *one reporting event* everywhere (prompt selection, and — if Sameer wants — a "syndicated" marker on the story page). It needs one new signal: the credit/dateline. Cheapest route to test first: extend `source_enrichment` to capture the first ~200 characters of body text (or the `og:description` / byline metadata) for the outlets that carry the most wire copy (The Tribune, The Wire, Republic World), then measure how much headline-overlap dedup already catches versus what a dateline adds. A one-off measurement on ~500 articles would decide whether it is worth a permanent field.

## Decision needed from Sameer

* Is ANI a **publisher** (own lean, own vote) or a **wire** (origin only, never votes)? The evidence favours *wire*.
* Should copies that different outlets choose to run count as separate bar votes, as they do today? (Unchanged in this phase.)
