# Source diversity — Phase 2: did the fixes work, and where is diversity still lost?

**Snapshot:** a consistent read-only copy (SQLite backup API) of `paksh.db` taken 2026-09-21 ~01:00 UTC: 611,811 articles, 19,902 events. It has the **same 500 newest published stories** as the first audit; the 721 extra articles are the nightly's ingest. All experiments ran from copies of it; the live database and pipeline were not written to.
**Evidence labels:** `[MEASURED]` queried from the snapshot/logs · `[SANDBOX]` real code run on a snapshot copy · `[CANARY]` real LLM calls on stored articles, no DB · `[PROBED]` a live HTTP request · `[CODE]` read from source.
Companion documents: [SOURCE_UTILIZATION_AUDIT.md](SOURCE_UTILIZATION_AUDIT.md) (phase 1) · [ANI_SOURCE_ANALYSIS.md](ANI_SOURCE_ANALYSIS.md) · [SOURCE_SELECTION_ALGORITHM.md](SOURCE_SELECTION_ALGORITHM.md).

---

## 0. Two things you need to know first

**A. My phase-1 change crashed last night's refresh, and I did not catch it.** `database.select_unclustered_window` called `row.get("fetched_at")`; production rows are `sqlite3.Row`, which has no `.get`. My tests and shadow harness used plain dicts, so they never ran that path. The nightly job (05:52) died at `cluster.py` with `AttributeError` at 06:26 and — because the pipeline stops on the first failure — **did not analyse, export or auto-push**. Nothing half-built was published, but **that night's content refresh did not happen.** Fixed in commit `6162f2c261` with a tolerant accessor and three tests that run the *real* query against an isolated database. Everything in this report was then validated through the real code path (a full sandbox `analyze` cycle, export and API), which would have caught it. The next scheduled run will use the fixed code; to catch up sooner, run the nightly batch by hand.

**B. The biggest source-diversity loss is not where phase 1 looked.** The completeness gate hides **32% of all analysed stories — and 58% of the stories with five or more publishers.** The cause is a prompt-labelling inconsistency, now fixed (§4). This means the flat "3.1 publishers per story" understates what the pipeline produces: publishers per story is 4.08 for published stories but **6.96 for the hidden ones**.

---

## 1. The ten questions

| # | Question | Answer |
|---|---|---|
| 1 | Did the clustering fix solve the registry-order bias? | **Yes.** The share of each registry band's fresh articles reaching clustering went from **40 / 40 / 39 / 34 / 49 / 68%** (rising with registry position) to a flat **45 / 49 / 47 / 48 / 47 / 45%**. The window is 48% international instead of 61%; 133 outlets instead of 114. |
| 2 | Why are publishers/story still ≈ 3.1? | Four reasons, in order of size: (a) **the completeness gate hides the many-publisher stories** (§4); (b) stories are built from what was in the window when they formed — 58% of stories have valid same-story articles that **never entered any window** (the phase-1 bug, only fixable going forward); (c) the same story is **split across events** (22% of stories); (d) many stories genuinely have two publishers (4 of the 25 traced had no same-story article from any other publisher). |
| 3 | Where is diversity lost? | See §3 — a stage-by-stage table with numbers. |
| 4 | Which of the 8 India feeds add value? | **India TV and India.Com are the only evidence-supported candidates**, for a supervised trial. Six should stay off. **All 8 remain disabled.** (§6) |
| 5 | What should happen with ANI? | **Do not ingest it as a publisher.** Treat it as a wire; the useful work is wire-origin *detection*. (ANI_SOURCE_ANALYSIS.md) |
| 6 | webindia123? | **No action.** No feed; 53% of its headlines are copies; 0 of 1,311 articles ever joined a story; not a farm pattern. (§7) |
| 7 | Should the 400-event merge cap remain? | **Yes, for this phase** (as instructed). It is now the next binding constraint — see §8 for the measurement that should decide it. |
| 8 | Did the World-story skew improve? | **Partly, and the two fixes pull in opposite directions.** Stories with **no India outlet at all** fell from **44% to 28%** (two independent experiments) — that part was accidental. But fixing the gate un-hides World stories, which would push the *published* World share up (55% → ≈ 68% of analysed stories) (§9). |
| 9 | Did top-publisher concentration improve? | **Yes.** Top-25 share of publisher slots 60.6% → **49.6%** (real cycle) and 54.7% → 47.1% (shadow); distinct publishers 69 → 88. |
| 10 | Single next engineering change? | **Let late same-story articles join existing stories** — widen the cross-cycle merge candidate set and revisit the diffuse-event keyword guard. Measure first (§8). |

---

## 2. Method

* **Same snapshot, two code trees.** OLD = `git archive` of the pre-fix commit `96fad1cf33`; NEW = the working tree. Each ran **one real `analyze.main()` cycle** on its own copy of the snapshot (extractive mode, `PAKSH_LLM_BUDGET=0`, real Cloudflare embeddings, real cross-cycle merge, real event inserts). Clustering is otherwise identical.
* **Four different things are counted separately** — never raw article count:

| Concept | Definition used | Example |
|---|---|---|
| **Article** | one stored row | 3 rows |
| **Publisher** | distinct `source` name | The Tribune, The Wire |
| **Domain** | registrable domain of the article URL (registry domain for Google-News-bridged links) | tribuneindia.com |
| **Family** | distinct **owner** (`OWNER_BY_SOURCE`) — co-owned mastheads collapse | Times Group |
| **Independent reporting event** | articles merged when they share an owner, or (within one lean) have ≥ 75% headline overlap — the wire-copy proxy | one AP story under six mastheads |

  ANI → Publisher A → Publisher B is one reporting event with three articles and two publishers. Because wire datelines are not stored (ANI_SOURCE_ANALYSIS.md §3), a "wire-aware" variant of the count is **identical** to the headline-based one here (0.0% of articles carry a dateline) — that is a finding, not a measurement of "no wires".

---

## 3. Where diversity is lost — the same 500 stories

`[MEASURED]` on the 500 newest published stories (2026-09-18 → 09-20).

### 3.1 Per-story composition

| | mean | median | p25 | p75 | max |
|---|---:|---:|---:|---:|---:|
| Articles in the story | 4.69 | 2 | 2 | 4 | 63 |
| Publishers | 3.33 | 2 | 2 | 3 | 52 |
| Domains | 3.32 | 2 | 2 | 3 | 52 |
| Publisher families | 3.28 | 2 | 2 | 3 | 51 |
| Independent reporting events | 3.08 | 2 | 2 | 3 | 39 |
| Articles sent to the prompt — old picker | 3.76 | 2 | 2 | 4 | 12 |
| Articles sent to the prompt — new picker | 2.93 | 2 | 2 | 3 | 12 |
| Articles displayed to users | 4.69 | 2 | 2 | 4 | 63 |

Stories by publisher count: **2 → 325 (65%)**, 3 → 71, 4 → 45, 5 → 18, 6 → 8, 7 → 6, 8+ → 27.

### 3.2 Stage-by-stage

| Stage | What is lost | Measured |
|---|---|---|
| **Picker: collapsed as duplicates** | copies of one report (same owner / ≥ 75% headline overlap) | 1.61 per story; only **0.07** duplicates remain in the new picker's output |
| **Picker: rejected for quality** | reports cut by the 12-slot cap | **0.18 per story**, only in the 27 stories with more than 12 reports |
| **Picker: rejected for redundancy** | same as "collapsed" — the same articles, counted once | – |
| **Picker: rejected because of lean constraints** | none — the per-lean guarantee only *adds* | **0**; 0 of 76 test stories omit a covered voting side, old or new |
| **Story page** | nothing — every article is listed | 4.69 = 4.69 |
| **Completeness gate** | stories with a covered side lacking framing | **32.3% of analysed stories hidden; 57.8% of those with ≥ 5 publishers** (§4) |
| **Never joined: never embedded** | same-story articles, from publishers **not** in the story, that never entered a clustering window | **57.6% of stories**, **+64.6%** publisher slots |
| **Never joined: split across events** | same-story articles attached to a *different* event | **22.2%** of stories, +32.7% |
| **Never joined: embedded orphans** | passed the merge gate but were never merged (merge cap / window / vetoes) | 20.4% of stories, **+8.7%** |
| **Never joined: keyword gate** | similarity ≥ 0.66 but too few shared keywords | 44.6% of stories, +85% (mixed precision — see 3.3) |
| Near-miss band 0.55–0.66 | topical neighbours, almost all a different story | ignore |

"Candidate" counts use the pipeline's **own** merge gate (similarity ≥ 0.66 and its keyword rule) applied to every article in the ±2/+5-day window of each story, embedded for the purpose. They are an **upper bound**: passing the gate is necessary, not sufficient.

### 3.3 Manual trace of 25 representative stories

Chosen to cover every cause (7 with never-embedded candidates, 5 split-across-events, 4 embedded orphans, 3 keyword-gate-only, 4 with two publishers and no candidates, 2 with ≥ 8 publishers). Each candidate list was read by eye.

* **Never-embedded candidates at similarity ≥ 0.80 were the same story every time** (e.g. story 22092, the Tata Trusts dispute — The Times of India, The New Indian Express, Mathrubhumi English, The Indian Express, 22 publishers in all; story 22085, LPG Aadhaar rule — Business Standard, Telangana Today at 0.90). They are overwhelmingly **early-registry India outlets and the international wires** the old window starved. Below ≈ 0.75 the candidates were increasingly the same *topic*, not the same story (story 3: Iran money flows; story 15: generic "Viksit Bharat").
* **Fragmentation is real:** 16 of the 25 have gate-passing articles attached to a *different* event, and in most of them the top candidates read as the same story (e.g. 22304 "Merz vows to continue reforms" and the event holding CBS and SCMP at 0.94; 22291, whose "AI Force" coverage from SCMP, DW, the NYT and the Telegraph sits in event 22036). The phase-1 event-vs-event test found only 3% because it demanded agreement between whole events; an article-vs-event test finds 22%.
* **The keyword gate blocks exact duplicates in big events:** story 21870 (26 publishers) rejects "Trump bars CNN, MS NOW and Politico" from DW and TIME at similarity **0.91–0.92**, because the diffuse-event guard scales the required shared keywords with the event's breadth. Deliberate and conservative — and a candidate for a measured change, not a quick fix.
* **Four two-publisher stories (22330, 22327, 22326, 22325) had no same-story candidate at all** — the weak matches were other topics (childcare costs, an "affordability agenda" piece). Two publishers is the honest answer for them.

So the question "why are valid independent sources excluded?" has a specific answer: **mostly because they never reached a clustering window (fixed), and secondarily because a story that already exists cannot easily absorb them (§8).**

---

## 4. The completeness gate — the largest loss, and its fix

`[MEASURED]` 3,011 analysed stories (≥ 2 voting outlets, LLM briefs) created in the last 14 days:

| Publishers in the story | Hidden by the gate |
|---|---:|
| 2 | 15.8% |
| 3 | 35.4% |
| 4–5 | 47.5% |
| 6–8 | 60.8% |
| 9–12 | 63.2% |
| 13+ | 52.7% |

* By sides covered: **1 side → 2% hidden · 2 sides → 50% · 3 sides → 61%.** The gate hides the multi-sided stories Paksh exists to show.
* By region: **India 14% · World 42%.** Hidden stories do not clear on their own: the 09-07 → 09-11 cohorts are still 26–43% hidden in the snapshot.
* The pipeline's own logs agree: **only 25.8% of 747 LLM briefs are complete on the first pass; the retry rescues 59.7% of the rest; 29.9% end up hidden.**

**Cause `[MEASURED]`.** Of the sides with no framing, **80% are sides held only by international-tier outlets** in World stories, and **39.9% of such sides** end up with no framing (vs 8–13% where an India outlet is present). On a World story an international outlet with a known lean votes on it (`analyze.lean_of(name, region)`), and the retry prompt already reports the corrected owner counts — but the `OUTLET:` block still labelled every such outlet "international wire", so the model had a covered side and no outlet it could attribute to it, and wrote nothing for it.

**Fix (`analyze.py`).**
1. On the retry (region known), label each outlet with `lean_of(name, region)` — the lean the arithmetic will count. First attempts and India stories are byte-for-byte unchanged.
2. The retry keeps the region it was prompted with. Without this, the label fix raised World→India re-classifications on the retry from 1 to 5 of 45 (an India-classified World story has no voting side and can never publish).

**Canary `[CANARY]`** — the real `analyze_event` (first pass → retry → postprocess) on the same 55 stored stories, real LLM pool, no DB access:

| | OLD | NEW |
|---|---:|---:|
| Publishable end-to-end (complete **and** ≥ 2 voting outlets) | 40 / 55 | **55 / 55** |
| hidden-World (30) | 19 | **30** |
| complete-World (15, guard against regressions) | 11 | **15** |
| hidden-India (10) | 10 | 10 |
| Retry rescue rate | 22 of 37 (59%) | **35 of 35** |
| World→India re-classifications | 1 | 1 |
| Zero-voting outcomes | 0 | 0 |

The OLD arm's 59% rescue rate reproduces the production log's 59.7%, which is the check that the canary is representative. 15 stories improved, **0 regressed**. An attribution arm (new picker, *old* label) scored 13/30 and 10/15 — no better than OLD — so **the gain is the label fix, not the picker.**

**Live confirmation.** The scheduled reframe job (07:30 on 2026-09-21) runs on this code. Read from the database while it runs, 79 previously-hidden stories had been re-analysed: **77 are now complete (97%)** — World 55 of 57, India 22 of 22; two failures (`PLACEHOLDER_SOURCE_CONTENT`, `UNUSABLE_FRAMING`). The 09-18 reframe run (old code) completed about a third (60 of 293 on the first pass, 41 of 233 rescued on the retry). The job was still running when this was written.

*Limits:* n = 55 with a stochastic model at one moment; the first pass is unchanged (about two thirds of World stories still need the retry, because the text-only region guess recognises only 43% of them), so LLM cost per World story is unchanged, not reduced.

---

## 5. Did the clustering fix work? `[SANDBOX]`

One real `analyze` cycle per tree, same snapshot:

| | OLD code | NEW code | |
|---|---:|---:|---:|
| Window: outlets present | 114 | **133** | |
| Window: India / international articles | 1,153 / 1,828 | **1,539 / 1,432** | |
| Clusters folded into existing stories | 123 | 146 | +19% |
| **Publisher-slots added to existing stories** | 150 | **233** | **+55%** |
| Existing stories grown | 86 | 108 | +26% |
| **New stories created** | 61 | **82** | **+34%** |

**Admission by registry position** `[MEASURED]` (share of the fresh, ≤ 72 h articles each band has that reach clustering):

| Registry position | Outlets | OLD | NEW |
|---|---:|---:|---:|
| #0–19 (The Hindu, Indian Express, Mint, The Wire…) | 20 | 40.1% | 45.0% |
| #20–39 | 20 | 40.0% | 49.2% |
| #40–59 | 20 | 38.8% | 46.7% |
| #60–79 | 20 | 34.4% | 48.3% |
| #80–99 | 20 | 49.3% | 46.9% |
| #100–123 (international) | 24 | 68.3% | 45.2% |

*Remaining constraint:* capacity. 18,916 rows are fresh and 6,366 fit the per-outlet cap, but the 3,000-article window admits about 47% of them each run; the rest wait for the next run or age out at 72 h.

### 5.1 New stories from one cycle — publisher composition

| | OLD | NEW |
|---|---:|---:|
| Stories | 61 | 82 |
| Publishers / story — mean, median, p25, p75 | 2.70, 2, 2, 2 | 2.76, 2, 2, **3** |
| Domains / story · families / story | 2.70 · 2.67 | 2.76 · 2.73 |
| Independent reporting events / story | 2.33 | **2.50** |
| Articles / story | 3.44 | 3.35 |
| Stories with ≥ 3 publishers | 23.0% | 25.6% |
| Distinct publishers used | 69 | **88** |
| Top-10 / top-25 / top-50 share of slots | 30.9 / 60.6 / 88.5% | **23.5 / 49.6 / 79.2%** |
| Voting owners / story | 2.02 | **2.32** |
| Votes left / centre / right (totals) | 27 / 76 / 20 | **39 / 111 / 40** |
| Stories covering ≥ 2 sides · all 3 sides | 45.9% · 4.9% | 47.6% · **7.3%** |
| India share of publisher slots | 46.7% | **55.3%** |
| US · UK · Europe · Middle East · East Asia | 18.8 · 12.7 · 3.6 · 4.9 · 4.9% | 18.1 · 12.8 · 4.0 · 2.2 · 3.5% |
| Africa · Latin America | 0 · 0% | 0 · 0% |
| Other | 8.5% | 4.0% |

Publishers per story is flat for a structural reason: the fix widens *which stories form and how many outlets they hold at creation*, but a story's late arrivals need the merge (§8), and the many-publisher stories are then hidden by the gate (§4) until that is fixed too. **Regional diversity beyond India did not change** and cannot until non-India outlets are ingested (§10).

*Snapshot note:* the earlier shadow (first audit snapshot, fresh clusters only) reported 111 → 157 stories, India share 37.5% → 56.6%, top-25 share 54.7% → 47.1%. That snapshot is 721 articles older; the direction and size agree with the real cycle above.

---

## 6. The eight candidate India feeds `[PROBED]` `[MEASURED]`

**All eight remain disabled; `feeds.py` is untouched.** Method: each feed fetched once; its items embedded in memory and compared with every article in the snapshot from 09-16 onward. "Duplicate" = headline overlap ≥ 75% or embedding similarity ≥ 0.92 with **another outlet's** article. "Unique value" = for each item, how many *other* publishers already cover it (≥ 3 = well-covered, 1–2 = thin, 0 = uncovered). Limits: one poll per feed (volume is the span its items cover, not a long-run rate); the feed items are newer than most of the snapshot.

| OUTLET | FEED HEALTH | ARTICLE VOLUME | ORIGINALITY | DUPLICATION | QUALITY | LEAN CONFIDENCE | UNIQUE VALUE | RECOMMENDATION |
|---|---|---|---|---|---|---|---|---|
| **India TV** | healthy: 50 items, newest 0.2 h, all dated | 50 items over 19.7 h (≈ 2.5/h) | no wire credits found | 8% (4 headline, 2 embedding) | excerpts 225 chars, all ≥ 100; images 50/50; 40 India / 10 World | **right / high** | 32 well-covered, 10 thin, 8 uncovered; would join **23** published stories; fills 0 gaps¹ | **Candidate for a supervised trial** — best evidence |
| **India.Com** | healthy: 20 items, newest 7.6 h | 20 over 7.0 h (≈ 2.9/h) | no wire credits found | **0%** | excerpts 165, all ≥ 100; no images; 19 India / 1 World | **right / high** | 16 well-covered, 2 thin, 2 uncovered; joins **14** stories; fills 0¹ | **Candidate for a trial** (second) |
| IBC 24 | healthy: 60 items, newest 5.8 h | 60 over 9.3 h (≈ 6.5/h) | – | 3% | excerpts 95 chars (only 11 of 60 ≥ 100); no images; Hindi, Chhattisgarh/MP local | left / **low** | 24 uncovered, 25 thin, 11 well; joins 16 | **Hold** — low-confidence lean; value is local news that cannot form a story alone (needs ≥ 2 rated outlets) |
| DD India | 10 items, newest 14.8 h | 10 over 3.2 h | – | **40%** (4 of 10) | excerpts 481; no images | left / **low** | joins 3 | **Do not enable** — high duplication; a *left* label on a state broadcaster is doubtful and needs editorial review |
| Dainik Navajyoti | 35 items, newest 12.4 h, **dates span 3.3 years** (stale/misdated entries) | unreliable | – | 0% | excerpts 268; images 35/35; Hindi, Rajasthan local | right / low | 25 of 35 uncovered; joins 3 | **Do not enable now** |
| Navabharat | 4 items | 4 over 1.2 h | – | 0% | **all four have empty excerpts** | left / low | joins 0 | **Not viable** |
| Sanmarg | **1 item** | – | – | – | – | left / low | joins 0 | **Not viable** |
| GNN | stale: newest 61 h, span 27 days | 10 items | – | 0% | excerpts 317 | right / low | uncovered 10 | **Reject** — stale |

¹ "Fills a coverage gap" could not be tested: the gap stories in the snapshot date from 09-18 → 09-20 and the feed items from 09-21.

Enabling India TV or India.Com would add a **high-confidence right-leaning voice** to stories that are mostly already covered (right is the thinnest lean: 190 / 1,173 / 240 left / centre / right votes in the 500-story sample). That is a lean-composition decision for Sameer, not a numbers decision. *Note:* India TV's feed URL contains an opaque path segment (`…/v3/en/gp7naGtJSQrs9oi/rss/topstory`) advertised on its own homepage; if it rotates the feed would silently stop.

---

## 7. webindia123.com `[MEASURED]` `[PROBED]`

* No discoverable feed (six standard paths tried); not in the registry; reaches the DB only as an unknown GDELT domain: **1,311 articles** (2026-06-24 → 09-20), **0 ever attached to a story**, 2 in the last five days.
* **53.2%** of its 1,309 distinct headlines also appear from other outlets (The Tribune 110, Republic World 20, The Wire 16) → an aggregator/republisher, but 47% of its headlines are not seen elsewhere, so it does **not** fit the farm pattern (which is ≥ 15 headlines shared across ≥ 3 unrated domains).
* Topics in the sample are political; regional value not demonstrated.
* **Recommendation, independent of ANI:** no action — neither enable nor block. It costs nothing where it is (unrated, non-voting, cannot create a story). Revisit only if a feed appears.

---

## 8. Merge cap: kept at 400 (as instructed)

`get_recent_events_for_merge(limit=400)` reaches back ≈ 1.4 days of the 5-day window (1,444 events). **Unchanged.** The decision to raise it should rest on a controlled measurement, because it changes what merges into already-published stories and would confound the window/picker/label results measured here.

What the data says: orphan articles from new publishers pass the merge gate for **18% of stories inside the cap and 23% outside**, worth **+8–9%** publisher slots — small next to the 64.6% that was lost to the window bug, which is why the window fix had to come first. **After the window fix the cap becomes the binding constraint**, because late arrivals from previously-starved outlets can only attach to stories in the newest 400 events.
Proposed measurement (next phase): on the same snapshot, run the NEW cycle with the cap at 400 and at ~1,500 and compare publishers added per grown story, veto counts and false merges (manually audited on 25 stories). Only then change it.

---

## 9. The World-story skew `[MEASURED]` `[SANDBOX]`

* **Live 500:** 286 World (57%) vs 214 India. Across all 3,011 analysed stories: **64.6% World created → 55.2% published** (the gate hides 42% of World, 14% of India).
* A classifier-independent measure — **stories with no India outlet at all**:

| | OLD | NEW |
|---|---:|---:|
| Shadow (first audit snapshot) | 44.1% | **28.0%** |
| Real cycle (this snapshot) | 44.3% | **28.0%** |
| Live published 500 (before) | 41.0% | – |

  About **16 points (a third)** of the international-only skew was the registry-order bug. The remaining 28% is structural: global stories that no India outlet in the registry covered.
* The extractive sandbox classifies region by text, which recognises only 43% of World stories, so the World-*label* share is not comparable with the live LLM-labelled 57% (sandbox: 26% vs 28%, unchanged).
* **The fixes pull in opposite directions.** The window fix reduces international-only stories; the gate fix un-hides World stories. If World hidden falls to 0 and India hidden stays at 14%, the published World share of analysed stories would move from 55.2% to **≈ 68%**. Both are corrections — but the second raises World prominence. No quota was added (per instruction). If India-first prominence is wanted, that is a *ranking* decision for Sameer.

**Categories (topic labels).** Live, LLM-labelled, published vs created (14 days): Crime & Law 23.0% vs 25.0% · Politics 22.0% vs 20.5% · Economy 19.5% vs 16.8% · Society 14.6% vs 14.4% · Sports 10.1% vs 10.9% · Entertainment 3.4% vs 4.1% · Environment 2.8% vs 2.9% · Science & Tech 1.9% vs 2.3% · International 1.4% vs 1.8% · Health 1.3% vs 1.4%. The gate hides Entertainment, Science & Tech and International most (44–45%). In the extractive sandbox new stories (text-guess labels, so indicative only) Sports went 0 → 3, Science & Tech 1 → 4, Economy 3 → 5, Crime & Law 6 → 12 with the fair window — a broader outlet mix reaches more categories.

---

## 10. Regional and leaning distribution after the fix

See §5.1 (real cycle). Africa and Latin America stay at 0%: Paksh's fed outlets are the 124 curated ones; the verified registry's African (343) and Latin American (1,960) entries are lookup rows, mostly in languages Paksh does not ingest, reached only through a GDELT stage that is largely rate-limited (§11). The 10% window reserve for vetted non-voting outlets is ready for them but can only help once they are ingested.

---

## 11. GDELT after the fix `[PROBED]`

One controlled stage of the **current** `gdelt_source` against the live API — all 16 queries, sequential, insertion captured in memory (no database writes), 2026-09-21 07:25–07:48 IST.

| | Before (pipeline log, 38 stages) | After (this stage) |
|---|---:|---:|
| Queries answered | 43% (221 of 514) | **75% (12 of 16)** |
| … of which returned articles | 31% | 12 of 16 |
| HTTP 429 (rate limited) | 24.5% | **25% (4 of 16)** |
| DNS / network failure | 32.5% | **0%** |
| Articles returned by answered queries | – | 847 |
| Dropped at ingest (junk, language, syndication farm) | – | 220 (26%) |
| Already in the database | – | 509 (60%) |
| **New and useful** | median 155 new per stage | **116 (13.7% of returned)** — 65 rated outlets, 9 vetted foreign, 42 unknown domains |
| Wall time | up to 2,045 s in back-offs when failing | 1,360 s (≈ 85 s a query) |

**Read this honestly.** It is *not* a like-for-like comparison. The DNS failures in the log were this PC being offline; today the network was up, so the higher success rate is not evidence for the code. The 429 rate is unchanged — GDELT's throttling is external, and every query paid 10 / 17 / 35 s back-offs. The **circuit breaker was never triggered** (no three failures in a row), so its behaviour in the wild is unit-tested only; the overload-page and farm-blocklist changes are likewise correct but were not exercised by this run. What the numbers do show: a healthy stage costs ≈ 23 minutes, and only **≈ 1 in 7** returned articles is new — of which about half come from unknown domains.

**Before** (pipeline log, 38 stages): 514 queries — 31% returned articles, 25% HTTP 429, 32% DNS/network, 589 back-off retries, median stage added 155 new articles, 11 stages added none, one failed cycle spent 2,045 s in back-offs. **Not attempted:** a new ingestion architecture; GDELT's rate limiting is external. If the long tail matters, budget a second source.

---

## 12. Regression checks `[SANDBOX]`

On the NEW code's sandbox after one real cycle, versus the snapshot:

| Check | Result |
|---|---|
| Every existing story id still exists; no article moved or detached | **PASS** (0 of 19,902 missing; 0 of 182,051 moved) |
| New story ids continue the sequence | **PASS** (22331 → 22412) |
| Attribution: every listed source URL maps to a database article of that outlet | **PASS** (190 stories, 0 mismatches) |
| **Lean calculation:** one vote per owner, fixed labels, story region reproduces every stored count | **PASS** (0 differ) |
| Coverage Gap methodology (`compute_blindspot`, `dominant_lean`, `lean_counts_from`) is byte-identical to the pre-fix code | **PASS** ×3; 13 of 190 touched/new stories carry a gap |
| **No covered side disappeared** from any merge-grown story | **PASS** (0) |
| Completeness guarantee: `compute_content_complete` untouched; the canary shows no regression | **PASS** (0 of 55 worse) |
| Export builds; 62/62 new stories have pages with canonical URL, NewsArticle JSON-LD and a sitemap entry; static checks | **PASS** (30/30) |
| Developing Stories (`storylines.json`, 197 sagas) and Coverage Gaps (`blindspots.json`, 316) exported | **PASS** |
| API: `/health`, `/api/events`, `/events/{id}` (new + existing), `/blindspots`, `/storylines`, `/topics`, `/sources`, `/search`, unknown id → 404, POST/PUT/DELETE/PATCH refused | **PASS** (15/15) |
| Frontend | not touched in this phase, so mobile rendering is unaffected |
| Three further checks that "failed" (1–2 changed titles, 24–31% of extractive new stories below 2 voting outlets) | **identical under the OLD code** (1 title; 31% vs 24%; 69% vs 76% publishable) — pre-existing behaviour, not regressions: extractive stories use the text-only region guess, and a merge with very high similarity re-summarises |

**Existing suite:** **44 / 44 test files pass** — the 43 existing files plus `test_source_utilization.py` (59 checks) — run from a sandbox copy of the latest working tree against a copy of the snapshot database. No existing test was changed. The 59 checks include the real `sqlite3.Row` query path on an isolated database (A20–A22), region-aware outlet labels (C5–C8) and the retry region pin (C9–C11).

---

## 13. Remaining limitations

* The canary is 55 stories at one moment with a stochastic model; the first-pass completion rate (≈ 1 in 3) is unchanged, so a World story still costs two LLM calls.
* The sandbox cycles are **extractive** (no LLM), so the completeness gate is exercised only by the canary, not by the cycle comparison.
* "After" on the *same 500-story sample* cannot exist before deployment; the comparable "after" is the sandbox cycle on the same snapshot.
* Independent-report counting is a proxy (owner + ≥ 75% headline overlap); wire origin is invisible today.
* One poll per candidate feed; "fills a gap" untestable across dates.
* The window's 3,000-article capacity admits ≈ 47% of fresh articles per run.

## 14. PRE-PUSH DECISION

**READY TO PUSH** — the local commits not yet on GitHub (`git log origin/main..HEAD` — eight at the time of writing, from `0594fac948`, the fair window, onward). Push the source and docs; do not push anything from `_site` as part of this.

Checked against the pre-push rule:

| Requirement | Status |
|---|---|
| Tests pass | **44/44 files** (59 new checks) |
| Sandbox comparison completed | **Yes** — old vs new code, one real cycle each, same snapshot; plus export, API and 13 regression checks |
| No regression in story completeness | **Yes** — canary 40/55 → 55/55 publishable, 0 worse; and the live reframe run now shows **77 of 79 repaired stories complete (97%)**, against about a third repaired on 09-18 |
| No regression in Coverage Gaps | **Yes** — methodology byte-identical; 316 gaps exported |
| No regression in lean calculation | **Yes** — every stored count reproduces from labels + owners + region |
| Source-selection behaviour understood | **Yes** — §3–§5; documented in SOURCE_SELECTION_ALGORITHM.md |
| The 8 India feeds remain disabled | **Yes** — `feeds.py` unchanged; evidence supports only India TV and India.Com as trial candidates |
| Merge cap unchanged | **Yes** — 400 |
| Frontend / API architecture / registry / clustering engine | **Untouched** |

**What "ready" does and does not mean.** A push only publishes source to GitHub. It does not change the live site (Vercel serves the generated `_site`). The pipeline on this PC already runs this code, because it executes from the working tree — that is how the crash reached last night's run, and it is why the live reframe job is exercising the fix right now.

**Accept these knowingly:**
1. **The published World share will rise** as hidden World stories are repaired (55% → ≈ 68% of analysed stories) while the window fix lowers international-only stories (44% → 28%). No quota was added. If India-first prominence is wanted, that is a ranking decision.
2. **A World story still costs two LLM calls** — the first pass fails about two times in three; only the retry now succeeds.
3. **The repaired backlog will surface as older stories** (reframe preserves each story's original date; ≈ 300 a day).
4. The 2026-09-21 nightly did not refresh content (my bug, fixed).

**Do not push while `reframe` is running.** The reframe batch ends with `safe_autopush.py`, which pushes `_site`; two pushes at once can conflict. Wait for `.pipeline.lock` to clear (the job started 07:30 and takes ≈ 2½ h).

**Verify after pushing / after the next cycle**

```
git log origin/main --oneline -7
```
```
py audit_source_utilization.py
```
Expect: admission by registry position flat (≈ 45–49% in every band), the completeness-gate section's hidden rate falling from ≈ 30%, World hidden falling toward 0, and the World share of published stories rising.

```
Select-String -Path refresh_log.txt -Pattern "GDELT queries|Retry:|Published|failed" | Select-Object -Last 12
```
Expect **no** `cluster.py failed`, and `Retry: … first-pass complete … N retried (N rescued, 0 not rescued …)`.

```
py test_source_utilization.py
```
To catch up the missed 2026-09-21 refresh sooner, run the *Paksh nightly* task from Task Scheduler (or `refresh_scheduled.bat`) once the reframe job has finished.

**Rollback:** revert the relevant commit and re-run the pipeline. The label/region change is `e8ab2462e7` (revert restores the old prompt behaviour), the window is `0594fac948` + `6162f2c261`.
