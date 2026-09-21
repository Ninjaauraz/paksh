# Source utilization & publish-quality audit

**Question:** Paksh has 6,000+ sources in its database but publishes stories from a small set of them. Why, and what should change?

**Snapshot:** read-only, 2026-09-21 ~00:20 UTC, against `paksh.db` (611,090 articles, 19,902 events). Nothing was written to the live database and the live pipeline was not touched.
**Evidence labels:** `[MEASURED]` = queried from the DB/logs · `[SHADOW]` = old-vs-new code run in memory on the same snapshot (the live DB is never written) · `[CODE]` = read from source.
**Reproduce:** `py audit_source_utilization.py` (read-only) prints sections 1–3 below.

---

## 0. The answer in one page

**"6,000+ sources" is not what the pipeline actually reads.** The 6,534-entry *verified registry* is a lookup table used to label domains that show up in GDELT. It is not a list of feeds Paksh polls.
The pipeline reads **124 curated outlets over RSS** (113 of their 178 feed URLs are Google-News bridges) and a thin, unreliable GDELT tail.

| | Registry | Ever produced an article | Produced one in the last 7 days |
|---|---:|---:|---:|
| Curated India outlets (RSS) | 69 | 67 | 67 |
| Curated international outlets (RSS) | 55 | 55 | 55 |
| Verified-registry India outlets (vote) | 100 | 11 | 5 |
| Verified-registry foreign outlets (no vote) | 6,434 | 222 | 8 |
| Unknown GDELT domains | – | 2,349 | 95 |
| **Verified-registry entries that never produced a single article** | **6,301 of 6,534** | | |

The 124 curated outlets supply **91.4%** of all 611,090 articles. Of the 6,534 verified entries, **4,583 are tagged with a language Paksh does not ingest** (only English and Hindi are), and 95 of the 100 India entries are `confidence: low`.

**But the concentration in published stories is mostly a bug, not a shortage of sources.** Even among the 124 curated outlets, the pipeline was throwing away most of what it ingested — and throwing away the *India* outlets first.

> **Root cause #1 (confirmed, high severity):** every pipeline run hands clustering only the **newest 3,000** un-grouped articles. Ingest visits outlets one after another, so the outlets visited **last** always hold the newest timestamps and fill the window. `database.get_unclustered_articles` claimed to be "balanced across outlets", but its per-outlet cap only limits the biggest outlets; the cut-off still falls on whoever was ingested last.
> The cap was saturated in **35 of 35** logged runs. Outlets at the start of the registry (The Hindu, The Indian Express, Mint, The Wire, Scroll.in…) reached clustering **32%** of the time; the international outlets at the end reached it **86–87%**. The Indian Express: **13%**.

Visible symptoms in the 500 newest published stories: **57% are World stories** (286 vs 214 India) for an India-focused product; the most frequent publishers are Reuters, Channel News Asia and the Sydney Morning Herald; **65% of stories have exactly 2 publishers**; only **4%** cover all three sides.

### What was changed (all in the working tree, nothing deployed)

| # | Change | File |
|---|---|---|
| F1 | **Fair clustering window** — every outlet gets an equal share, 72-hour recency bound, bounded reserve for vetted non-voting outlets | `database.py` |
| F2 | **Prompt source picker** — independent reports first, then richness, regional spread, ideological guarantee (kept), freshness, credibility | `source_selection.py` (new), `analyze.py` |
| F3 | **GDELT resilience** — overload page is a failure not "0 articles"; stop the stage after 3 straight failures | `gdelt_source.py` |
| F4 | **Syndication-farm blocklist +42 domains**, found by measurement | `gdelt_source.py` |
| — | Read-only audit tool + 49 new regression checks | `audit_source_utilization.py`, `test_source_utilization.py` |

### Measured effect `[SHADOW]` — same snapshot, same clustering engine, only the window rule differs

| | Before | After |
|---|---:|---:|
| Distinct outlets in the clustering window | 114 | 133 |
| Stories that qualify from one run | 111 | **157 (+41%)** |
| India outlets' share of publisher slots in stories | 37.5% | **56.6%** |
| Bias-bar votes per story (distinct owners) | 1.14 | **1.76** |
| … right / left / centre votes (totals) | 25 / 21 / 80 | **86 / 40 / 150** |
| Stories covering ≥ 2 sides | 26.1% | **39.5%** |
| Top-25 publishers' share of slots | 54.7% | **47.1%** |
| Publishers per story (mean) | 3.10 | 3.13 |

Publishers-per-story barely moves and **regional diversity beyond India does not improve** (§7). Those limits are real and are stated in §10.

---

## 1. Phase 1 — ingestion and the registry

### 1.1 Registry composition `[CODE]`/`[MEASURED]`

| | Count |
|---|---:|
| Curated outlets (`sources.SOURCES`) | 124 (106 English, 18 Hindi) |
| … India / Regional | 69 (48 + 21) |
| … International (non-voting wires) | 55 |
| … leans (curated) | 20 left · 86 centre · 18 right |
| … review status | 61 reviewed · 63 provisional |
| RSS feed URLs (`feeds.py`) | 178, of which **113 are Google-News bridges** |
| Verified registry (`verified_registry.py`) | 6,534 |
| … India, votes | 100 (3 high · 2 medium · **95 low** confidence; 25 en · 19 hi · **56 other language**) |
| … foreign, no vote | 6,434 |
| … language | **4,583 other** · 1,928 en · 23 hi |
| … lean (verified) | 3,082 left · 2,482 right · 970 centre |
| … region | Latin America 1,960 · W. Europe 1,506 · N. America 1,157 · Asia 648 · E. Europe 579 · Africa 343 · Middle East 252 · Pacific 89 |
| Resolvable domains (`DOMAIN_TO_SOURCE`) | 6,659 |
| Verified entries sharing a registrable domain | 945 in 88 groups |
| Effective India voters (curated India + verified India) | ≈ 169 |

There is **no publisher table** in the database: publishers are the text in `articles.source`. `[CODE]`

### 1.2 Who actually produces articles `[MEASURED]`

`articles` holds 611,090 rows fetched between 2026-06-14 and 2026-09-21; 2,704 distinct `source` values.

| Class | Registry | Ever | 90 d | 30 d | 7 d | Articles | Last 30 d | Last 7 d |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| curated-india | 69 | 67 | 67 | 67 | 67 | 379,149 | 118,770 | 32,040 |
| curated-intl | 55 | 55 | 55 | 55 | 55 | 179,491 | 100,011 | 28,757 |
| verified-india (vote) | 100 | 11 | 11 | 10 | 5 | 1,128 | 480 | 26 |
| verified-foreign | 6,434 | 222 | 222 | 145 | 8 | 666 | 289 | 10 |
| unknown domain | – | 2,349 | 2,349 | 746 | 95 | 50,658 | 7,461 | 410 |

```
articles by class (share of 611,090)
curated-india  ████████████████████████████████████████████████████████████ 62.0%
curated-intl   █████████████████████████████████ 29.4%
unknown domain █████ 8.3%
verified-*     ▏ 0.3%
```

Only **2 of the 124 curated outlets never produced an article** (Daily Thanthi, Divya Bhaskar — both Google-News-bridged feeds).

### 1.3 Feeds: which fail, which are stale `[MEASURED]` from `refresh_log.txt`

* 6,307 logged feed fetches: **4,781 (75.8%) returned items**, 1,526 (24.2%) returned none; 1,364 were "no entries" (unreadable).
* The direct feeds of **The Hindu, The Indian Express, The Economist, The Times of India, BBC News, The Guardian, Mint, NDTV** fail most often — those outlets still produce articles through their Google-News bridge feed.
* **7 of 181 feed URLs never returned an item** in the logged runs: The Financial Express (direct), The Statesman (direct), The Caravan (direct + bridge), CBC News (world), Daily Thanthi (bridge), Divya Bhaskar (bridge).
* RSS is steady: **113–119 outlets a day** over the last week.

### 1.4 GDELT — the only path for the other 6,000 `[MEASURED]`

GDELT-style rows (date-only `published`, empty summary) are 86,364 of 611,090 articles, and **11.7%** of last-30-day articles have an empty summary.

| Day | GDELT rows | Outlets |
|---|---:|---:|
| 2026-08-31 | 1,425 | 182 |
| 09-01 | 379 | 119 |
| 09-03 | 1,888 | 272 |
| 09-04 | 2,231 | 277 |
| 09-08 | 1,150 | 211 |
| 09-09 → 09-11 | 440 / 301 / 389 | 30 / 35 / 31 |
| **09-12 → 09-19** | **0 (eight days)** | – |
| 09-20 | 953 | 133 |

From the pipeline log (38 GDELT stages): 11 finished with **"0 new articles"**; of **514 queries**, only **158 (31%)** returned articles, **126 (25%)** were refused with HTTP 429 and **167 (32%)** failed on DNS/network; **589** back-off retries. The median stage added **155** new articles (a healthy stage could add up to 4,000: 16 queries × 250). One failed live cycle burned **2,045 s** in retry back-offs.
`[CODE]` Each query is capped at GDELT's 250 records, and a non-JSON overload page used to be returned as an empty list, so an overloaded stage looked like "GDELT had nothing".

---

## 2. Phase 1 — tracing the pipeline

### 2.1 Stage funnel `[MEASURED]` on the 2026-09-21 snapshot, old rules

| Stage | In | Out | Removed, and why |
|---|---:|---:|---|
| Ingest (RSS 124 outlets + GDELT) | – | 11,264 RSS rows since 09-20 | junk titles, horoscopes, tag pages dropped *before* insert (`ingest.is_junk`); GDELT non-en/hi dropped; farm domains dropped |
| Un-grouped backlog | 429,756 | – | rows whose `event_id` is NULL (about 70% of everything ever ingested) |
| **Clustering window** | 429,756 | **3,000** | the cap: the **newest 3,000** (≤ 60 per outlet), rated outlets first → **114 distinct outlets**, international 61% of admitted articles |
| Embedding | 3,000 | 3,000 | new texts embedded (Cloudflare bge-m3); cached ones reused |
| Clustering (leader + centroid merge, keyword gate) | 3,000 | **2,218 clusters** | same-outlet near-duplicates removed (`_dedupe_same_outlet`) |
| Qualification (≥ 2 rated outlets) | 2,218 | **111** | single-outlet / all-unrated clusters |
| Cross-cycle merge | – | – | new clusters folded into events from the last 5 days, but only the **400 newest events** are candidates |
| Budget | 111 | ≤ 500 / run | top 300 by voting breadth get an LLM brief, the rest an extractive one |
| Publication gate | – | – | `content_complete` (every covered side must have framing) and ≥ 2 voting outlets |

Across the last week (60,704 RSS articles): **61.1%** reached clustering and only **23.1%** ended up in a story.

### 2.2 Admission by outlet `[MEASURED]`

| Group | Articles (since 09-14) | Reached clustering | In a story |
|---|---:|---:|---:|
| curated India | 31,858 | **44.0%** | 15.3% |
| curated international | 28,846 | **80.1%** | 31.6% |

```
share of an outlet's articles that reached clustering, by position in the registry (= ingest order)
registry #  0-19   ██████████████ 31.7%     The Hindu · Indian Express · Mint · Wire · Scroll …
registry # 20-39   █████████████████ 37.9%
registry # 40-59   ███████████████████████ 51.8%
registry # 60-79   ███████████████████████████████ 68.5%
registry # 80-99   ██████████████████████████████████████ 84.3%
registry #100-123  ███████████████████████████████████████ 87.1%     Politico · Evening Standard · Sydney Morning Herald …
```

Lowest admission: The Indian Express 13%, The Wire 19%, Mint 21%, The Pioneer 22%, Swarajya 23%, Scroll.in 23%, Zee News (Hindi) 26%, Navbharat Times 26%, Republic World 27%, The Hindu 30%. Highest: Politico 95%, Evening Standard 95%, Sydney Morning Herald 95%, The Atlantic 94%.

### 2.3 One published story, end to end — event 22107 `[MEASURED]`

*"Folkestone hotel fire treated as suspicious; dozens evacuate"* — World, Crime & Law, LLM brief, `content_complete` true, created 2026-09-20 16:52.

| Stage | What happened |
|---|---|
| Ingest 16:07–16:10 | 6 articles, all via **Google-News bridge** feeds of 4 curated international outlets: Sky News ×2, The Independent ×2, Daily Mirror, Metro (UK). Excerpts of 74–121 characters. |
| Window | all 6 were inside the newest-3,000 and had embeddings (every one of these outlets sits in the "late" half of the registry). |
| Clustering | one cluster, 4 distinct outlets (same-outlet duplicates kept: different headlines). |
| Qualification | 4 rated outlets ≥ 2 → qualified. |
| Region | classified **World** by the model, so the four UK outlets **vote** on their underlying lean: **left 2** (Mirror, Independent) · **centre 2** (Sky, Metro) · right 0 → *Coverage Gap: right*. |
| Prompt (old picker) | all 6 (fewer than 12), in database order. |
| Prompt (new picker) | Independent + Mirror share a headline and lean → one report; Sky's two articles are one owner → one report; Metro separate → picks a left-lean and a centre-lean outlet. |
| Story page | lists all 6 articles under 4 outlets. |

This story surfaced a real risk in the first version of the new picker (it merged copies across the *hidden* underlying leans of international outlets); fixed and tested (`B16`–`B19`), and checked across all 76 shadow stories: **0 stories omit a covered voting side under either region classification, old or new**.

### 2.4 The ranking algorithm, exactly `[CODE]`

There is no popularity ranking of outlets. The signals that exist:

1. **Window:** `fetched_at` recency; rated-before-unrated (`LEAN_BY_SOURCE`); ≤ 60 per outlet; cap 3,000. *(changed — F1)*
2. **Clustering** (`cluster.py`, bge-m3 thresholds): join ≥ 0.61 + ≥ 2 shared seed keywords (or ≥ 0.79 with 1), merge ≥ 0.64, cross-language ≥ 0.79; same-outlet duplicates ≥ 0.90 dropped.
3. **Qualification:** ≥ 2 distinct *rated* outlets (`MIN_RATED_PER_EVENT`); international outlets count as rated but do not vote.
4. **Ranking for the LLM budget:** (distinct voting outlets, distinct rated outlets, cluster size), descending. India-first because only India outlets vote.
5. **Cross-cycle merge:** centroid ≥ 0.66, keyword gate scaling with event breadth, topic/entity/procedural vetoes, 5-day window, newest 400 events.
6. **Prompt pick:** ≤ 12 articles, ≥ 2 per covered lean, then rated-first. *(changed — F2)*
7. **Bias bar:** one vote per **owner** per side, from fixed lean labels. No AI, no weighting. *(untouched)*

---

## 3. Phase 2 — root causes

### Confirmed

| # | Cause | Evidence | Files | Severity | Fix |
|---|---|---|---|---|---|
| **C1** | **Window ordering bias.** "Newest 3,000" decided by `fetched_at`; ingest order makes late-registry outlets the newest. | 35/35 runs at exactly 3,000; admission 31.7% → 87.1% by registry position; India 44% vs international 80%; 57% of published stories are World | `database.py` | **High** | **Fixed (F1)** |
| **C2** | **GDELT tail starvation.** 429 rate limiting, DNS failures, a silent-empty overload path, 250-record cap, and back-off storms that stall the cycle. | 31% of queries succeed; 8 days at zero; 2,045 s failed stage | `gdelt_source.py` | Medium (tail cannot vote or create stories, but it is the *only* route to the other registry entries) | **Partly fixed (F3)**: failure is now visible and bounded. Rate limiting itself is external. |
| **C3** | **The other 6,301 registry entries have no ingestion path.** They are lookup data, not feeds. Of the 100 India ones, 56 are in languages Paksh doesn't ingest; 95 have low-confidence leans. | 6,301/6,534 never produced an article | `feeds.py` | Medium — but **editorial**, not a defect | **Not changed.** Feed probe (§9) gives Sameer the facts. |
| **C4** | **Prompt picker ignored independence.** Took 2 per lean in database order; a wire story under 6 mastheads spent 6 slots. | 1.18 duplicate copies per prompt (old) vs 0.07 (new) `[SHADOW]` | `analyze.py` | Medium (story quality, not publisher count) | **Fixed (F2)** |
| **C5** | **Syndication farms missing from the blocklist.** 42 more domains republish identical headlines: ~3,100 articles = ~19% of unrated GDELT flow, all fake breadth. | 348 headlines shared by ≥ 3 unrated domains in 45 days | `gdelt_source.py` | Medium | **Fixed (F4)** |
| **C6** | **Merge-candidate cap.** The merge window is 5 days = 1,444 events, but only the newest 400 (~1.4 days) are candidates. | Orphan articles that pass the merge gate exist for 18% of stories inside the cap and 23% outside; +8–9% publisher slots available | `database.get_recent_events_for_merge` (limit=400) | Low | **Not changed** (see §10). |
| **C7** | **`MIN_RATED_PER_EVENT = 2` + fragmentation of coverage.** 65% of stories have exactly 2 publishers. | mostly a consequence of C1: 43.8% of recent orphans were never embedded | `analyze.py` | Low (working as designed) | improved indirectly by F1 |

### Investigated and ruled out

| Hypothesis | Verdict | Evidence |
|---|---|---|
| Stale RSS feeds | **No** | 122 of 124 curated outlets produced articles in the last 7 days; 113–119 outlets/day |
| Inactive publishers | **Only in the registry lookup**, not among the fed outlets | §1.2 |
| Aggressive de-duplication | **No** | only same-outlet near-duplicates are dropped (`_dedupe_same_outlet`) |
| Clustering collapse / fragmentation | **No** | same event split across stories: 16 of 500 stories (3.2%) `[MEASURED]`; merging them would raise the best member's 8.3 publishers to 10.7 — a small pool |
| Authority weighting | **No such signal exists** in selection or ranking `[CODE]` |
| Language filtering | **Real but by design** | 4,583/6,534 registry entries are non-en/hi; GDELT drops them |
| Domain-normalisation bugs / aliasing | **No** | unique domains/story (3.32) ≈ publishers/story (3.33); owners/story 3.28 |
| Export-stage truncation | **No** | the story page lists every article; `events.json` cap (1,500) trims the feed, not a story's sources |
| API serialisation limits | **No** | the static export has no API path for this |

---

## 4. Phase 3 — quality analysis of the last 500 published stories `[MEASURED]`

Sample: the 500 newest published stories, 2026-09-18 → 09-20 (published = not demo, ≥ 2 voting outlets, `content_complete` not false).

**Publisher concentration**

| | Share of publisher slots |
|---|---:|
| Top 10 publishers | 21.5% |
| Top 25 | 42.8% |
| Top 50 | 69.3% |
| Top 100 | 99.4% (109 publishers used in total) |

```
Reuters              █████████ 9%      Aaj Tak                ████████ 8%
The Economic Times   █████████ 9%      Channel News Asia      ███████ 7%
Deccan Herald        ████████ 8%       The Hindu BusinessLine ██████ 6%
Dainik Jagran        ████████ 8%       Sydney Morning Herald  ██████ 6%
(share of stories that include the outlet)
```

99.8% of slots are curated outlets; only **4 stories** contain a non-curated outlet.

**Per story**

| | mean | median | p10 | p90 | max |
|---|---:|---:|---:|---:|---:|
| articles | 4.69 | 2 | 2 | 9 | 63 |
| publishers | 3.33 | 2 | 2 | 5 | 52 |
| owners | 3.28 | 2 | 2 | 5 | 51 |
| unique domains | 3.32 | 2 | 2 | 5 | 52 |
| independent reports | 3.01 | 2 | 2 | 5 | 34 |

Publishers per story: **2 → 325 stories (65%)**, 3–4 → 116, 5–7 → 32, 8–11 → 9, 12+ → 18.
Duplicate copies (same owner or near-identical headline): **35.8%** of all article slots (proxy: same owner, or headline overlap ≥ 75% within one lean).

**Regional diversity** (home country of the publisher; descriptive, not a lean label)

| Region | Share of publisher slots | Stories with ≥ 1 outlet |
|---|---:|---:|
| India | 50.7% | 59% |
| US | 16.1% | 26% |
| UK | 10.9% | 21% |
| East Asia | 4.8% | 12% |
| Europe | 3.2% | 7% |
| Middle East | 3.2% | 9% |
| Africa | **0%** | **0%** |
| Latin America | **0%** | **0%** |

**Ideological diversity** (Paksh's existing labels, one vote per owner): left 190 · centre 1,173 · right 240 votes; **279 stories cover one side, 201 two, 20 all three (4%)**.
**India vs World:** 286 World, 214 India. Topics: Politics 123, Crime & Law 111, Economy 78, Sports 66, Society 58, Entertainment 21, Environment 16, Health 11, International 11, Science & Tech 5.

**Original-reporting diversity:** see the per-story table above; 0.0% of stories contain an unrated outlet (the GDELT tail was offline for eight of the ten days).

**Missed coverage** (offline experiment, embedding cache only): since 09-16 there are 27,246 curated articles that never joined any story, and only **43.8%** have an embedding — the rest were never considered. For **20.4%** of the 500 stories there is at least one orphan article from a *new* publisher that passes the pipeline's own merge gate (+143 publisher slots, +9%).

---

## 5. Phase 4/5 — what was implemented

Full plain-English description: [SOURCE_SELECTION_ALGORITHM.md](SOURCE_SELECTION_ALGORITHM.md).

* **F1 — `database.py`.** `_fair_take` (round-robin by recency rank, per-outlet equal share), `select_unclustered_window` (recency bound 72 h, rated → vetted-reserve 10% → unknown domains), `get_unclustered_articles` keeps its signature and pushes the recency bound into the SQL range scan.
  *Two flaws found by measuring my own first version and fixed:* fair sharing handed outlets with only stale rows their full quota (164 stale India-voter rows, 300 stale foreign rows) → recency bound; the vetted reserve leaked 290 slots of slack to unknown domains → unused reserve returns to rated outlets first.
* **F2 — `source_selection.py`.** Independent-report grouping, richness/freshness/credibility score, regional bonus, per-lean guarantee kept (3 slots for the international tier so each possible World-story side is heard).
  *Two flaws found and fixed:* a long-excerpt unrated blog outscored a rated headline (rated-before-unrated is now a strict tier); merging headlines across the hidden underlying leans of international outlets (§2.3).
* **F3/F4 — `gdelt_source.py`.** A non-JSON reply is a failed query and is retried; 3 consecutive failures stop the stage (logs the queries not attempted); per-stage "queries ok/failed" summary; 42 farm domains added. **Not added:** `aninews.in` (ANI, a real wire agency) and `webindia123.com` (aggregator) — whether they count is an editorial call.

Untouched: clustering, thresholds, lean labels and methodology, Coverage Gap methodology, bias arithmetic, `content_complete`, story IDs, the export, the API.

---

## 6. Phase 6 — before / after `[SHADOW]`

Method: one read-only snapshot (429,756 un-grouped articles). The **old** window is the previous algorithm reproduced exactly; the **new** window is `database.select_unclustered_window` itself. 1,955 + 335 + 73 missing article texts were embedded in memory with the pipeline's own Cloudflare bge-m3 (nothing stored). Both windows are clustered by the unchanged `cluster.cluster_with_details` and qualified/ranked exactly like `analyze.main`. Cross-cycle merging is not simulated (the same for both arms), so these are *fresh-run* stories, not accumulated ones — the live 500-story sample above has more publishers per story (3.33) because stories accumulate articles over several runs.

**Window**

| | Before | After |
|---|---:|---:|
| Articles | 3,000 | 3,000 |
| curated international | 1,828 | 1,432 |
| curated India | 1,153 | **1,539** |
| verified India | 19 | 19 |
| verified foreign | 0 | 10 |
| Distinct outlets | 114 | **133** |

**Stories that would form**

| Metric | Before | After | Δ |
|---|---:|---:|---:|
| Stories (qualified clusters, top-500 budget) | 111 | 157 | **+41%** |
| Publishers / story | 3.10 | 3.13 | +0.03 |
| Owners / story | 3.07 | 3.11 | +0.04 |
| Unique domains / story | 3.09 | 3.13 | +0.04 |
| Independent reports / story | 2.84 | 2.96 | +0.12 |
| Duplicate copies / story | 1.01 | 0.77 | −0.24 |
| Stories with ≥ 3 publishers | 34.2% | 37.6% | +3.4 pt |
| Distinct publishers used | 85 | 97 | +12 |
| Top-10 share of slots | 25.9% | 22.4% | −3.5 pt |
| Top-25 share | 54.7% | 47.1% | −7.6 pt |
| Top-50 share | 83.7% | 75.8% | −8.0 pt |
| **India share of publisher slots** | 37.5% | **56.6%** | **+19.1 pt** |
| Bias votes / story (distinct owners) | 1.14 | 1.76 | **+0.62** |
| Left / centre / right votes (totals) | 21 / 80 / 25 | 40 / 150 / 86 | +19 / +70 / +61 |
| Stories covering ≥ 2 sides | 26.1% | 39.5% | +13.4 pt |
| Stories covering all 3 sides | 4.5% | 7.0% | +2.5 pt |
| Home regions / story | 1.79 | 1.66 | −0.14 |

Home-region slots — before: India 37.5 · US 25.3 · UK 13.7 · Other 9.3 · East Asia 5.2 · Middle East 4.7 · Europe 4.4; after: India **56.6** · US 18.1 · UK 10.8 · Europe 4.7 · Other 4.1 · East Asia 3.5 · Middle East 2.2. Most frequent publishers before: Bloomberg 10%, The Hindu 9%, Reuters 9%, Al Jazeera 8%, USA Today 8%; after: Republic World 10%, The Pioneer 8%, The Telegraph (India) 8%, Hindustan Times 7%, BBC News 7%.

**Prompt picker** (76 stories with ≥ 3 articles, identical clusters, only the pick differs)

| | Old | New |
|---|---:|---:|
| Articles picked | 5.11 | 4.13 |
| Distinct owners in the pick | 4.11 | 4.13 |
| Independent reports in the pick | 3.92 | 4.07 |
| **Duplicate copies in the pick** | **1.18** | **0.07** |
| Home regions in the pick | 1.96 | 1.95 |
| Mean excerpt richness (0–1) | 0.34 | 0.35 |
| Mean credibility (0–1) | 0.92 | 0.92 |
| Stories where a covered voting side is missing from the pick | 0 | 0 |

**What this does and does not show.** The window fix is the large effect: it moves the pipeline toward the India outlets the product exists for, adds 41% more stories from the same articles, and produces more voting outlets per story and more multi-sided stories. The picker fix mainly removes redundant prompt text (−1 article per prompt) while keeping owner diversity level; it does not add outlets. Publishers-per-story and regional spread are essentially flat.

---

## 7. Regional diversity: what these fixes cannot do

Africa and Latin America are at 0% and stay there: Paksh's *fed* outlets are 124 curated outlets, almost all India/US/UK/Europe/East Asia. The verified registry has 343 African and 1,960 Latin American entries, but they are lookup rows, mostly in languages Paksh does not ingest, and GDELT reached only 222 of the 6,434 foreign entries — 8 in the last week. The 10% window reserve is ready for them but cannot help until they are ingested. Fixing that is an editorial + feed decision (§9), not a code defect.

---

## 8. Regression testing

* **New:** `test_source_utilization.py` — 49 checks, offline, no real DB access: window fairness, recency bound, reserve and slack, ordering, public signature, copy collapse, side guarantee, World-story handling, determinism, `build_prompt` still counts owners from *all* articles, GDELT failure handling, blocklist.
* **Full suite:** all 44 `test_*.py` files (43 existing + the new one) run in a **sandbox** — a copy of the working tree plus a copy of the 2026-09-19 verified DB backup; the live DB was never opened for writing — **44/44 pass**.
* No existing test was changed; none pinned the old window.
* **Not run against a real deploy:** the static export and story pages are not touched by this change; nothing here is live until the next pipeline cycle. Verify after it runs with `py audit_source_utilization.py` (compare section 2: admission should be flat across registry positions, and section 3 should show a lower World share).

---

## 9. Proposals for Sameer (editorial — none enabled)

1. **Feeds for verified India outlets.** 38 English/Hindi verified-India outlets have never produced an article. A polite probe (one request each) found a working feed with items in the last 7 days for only **8**: India.Com (20 items), India TV (50), IBC 24 (60), DD India (10), Dainik Navajyoti (30), Navabharat (4), Sanmarg (1), GNN (2). 19 have no discoverable feed, 7 sites were unreachable, 4 have a feed with no items in the last 7 days. Their leans are `confidence: low` — turning them on puts low-confidence voters on the bias bar more often, so this is a labelling decision first.
2. **ANI (`aninews.in`) and `webindia123.com`.** Real wire agency / aggregator that many farm copies come from. Should they be ingested, rated or blocked?
3. **Five curated feeds that never return items:** The Financial Express and The Statesman (direct), The Caravan, CBC News (world), Daily Thanthi, Divya Bhaskar. Replace or drop.
4. **Merge cap (C6).** Raising `get_recent_events_for_merge(limit=400)` to cover the 5-day window would let late articles join older stories (+8–9% publisher slots) but changes what merges into already-published stories. Worth a separate, measured change.
5. **GDELT.** The pipeline can only be polite; rate limiting is on GDELT's side. If the long tail matters, budget a second source.

---

## 10. Limitations and recommendation on pruning

**Limitations**
* The before/after is a shadow of one run on one snapshot (fresh clusters only, no cross-cycle merge). It shows direction and size of the *window* effect; the live effect accumulates over cycles. Verify after deploy.
* "Independent report" is a proxy (same owner, or ≥ 75% headline overlap within one lean). Two independent outlets with near-identical headlines count as one for the *prompt*; both remain on the story page and in the bias bar.
* Region is the outlet's home country (descriptive), assigned by a small table for the 55 international outlets.
* GDELT is offline/rate-limited from this machine; its real contribution can't be tested here.
* Regional diversity beyond India is unchanged (§7).

**Should historical publishers be pruned? — No, not from the registry.**
* The 6,301 unused verified entries cost nothing at run time (the registry is lazy-loaded, ~0.2 s only when needed) and are the domain→outlet/lean lookup GDELT depends on. Deleting them removes the ability to label a domain the day it does show up.
* Do **not** delete the 2,349 unknown domains' articles wholesale either; `prune_cache.py` already exists for DB size, and it is the right tool if the 2.3 GB database needs trimming.
* What *is* worth pruning or replacing is **feeds** that never return items (§9.3) and, after Sameer's review, obviously non-news domains.
