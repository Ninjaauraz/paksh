# STORY_EVOLUTION_DESIGN.md - how coverage of a story developed over time

**Status: design only. Nothing in this document is implemented.** It answers one question: can Paksh show,
for any story, *when each outlet's coverage appeared and how the picture (which sides, how many outlets)
changed as reporting arrived* - reusing data it already stores, without building a second story-memory
system? Short answer: **yes, with no schema change for the first version**, at negligible cost.

Evidence labels: **MEASURED** = computed from the real `paksh.db` on 2026-09-19 (read-only; the prototype
ran outside the repo); **DERIVED** = follows from the code; **PROPOSED** = a design choice for Sameer to confirm.

---

## 1. What data already exists

| Fact | Where | Measured |
|---|---|---|
| One row per article: `source`, `language`, `title`, `url`, `summary`, `published`, `fetched_at`, `event_id` | `articles` (index on `event_id`; `url` UNIQUE) | 599,590 rows; **170,030 attached to 19,637 stories** (the rest are unclustered) |
| Each article's claimed publication time | `articles.published` | **92.8%** ISO-8601 with `+00:00` (UTC), **7.1%** date-only `YYYYMMDD` (GDELT), **0.1%** free text with no timezone |
| When Paksh fetched it | `articles.fetched_at` (naive UTC, microseconds) | 100% present |
| Outlet -> owner (the "one vote" unit), outlet -> lean | `sources.py` (`OWNER_BY_SOURCE`, `lean_of`) | editorial; never AI |
| The current coverage counts per side | `events.analysis_json -> coverage` | article-derived owner sets equal it for **19,644 of 19,648** stories (99.98%); the 4 that differ have no attached articles |
| Story -> storyline (a saga of events over days) | `storylines.py` -> `_site/data/storylines*.json` | 198 storylines, already exported and rendered (`StorylineTimeline`) |
| Per-story exported JSON | `_site/data/events/<id>.json` | carries `sources[]` with headline, language, lean, owner, url - **but no timestamps**; ~10 KB |

Two existing structures are deliberately **not** used, to avoid a parallel system:

- `event_relationships` / `event_deltas` / `story_memory.py` (an LLM-judged "this story continues that story"
  layer, in shadow mode): 4 and 2 rows. It links *different events*; `storylines.py` already does that
  deterministically and is live. Story Evolution is about *one* story's coverage over time and needs neither.
- `analysis_json.sources[]`: it has no times, and it is rewritten on every re-analysis.

**Membership is not frozen:** 88% of stories have `updated_at != created_at` (articles join, re-counts run).
So the timeline must be *derived from current membership* each export, not stored once.

## 2. What can be derived without schema changes

Everything in the first version. From `articles` (+ `sources.py`) for each story we can compute, per outlet
owner, **the earliest time that owner's coverage appears in Paksh's data**, its lean, how many articles that
owner has published on the story, and the running breadth (owners per side, over time). That yields:
who appeared first, when each side joined, when the story reached 3/5/10 outlets, and how long a Coverage
Gap stayed lopsided.

Measured on all 19,637 stories: **99,769 first-seen points from 170,030 articles** (59% of articles are a new
outlet's first report; the rest are repeat coverage). Median first-to-last outlet span **13.7 h** (p75 32 h,
p90 67 h) - real evolution, not noise. In **9,606** stories a second political side first appears **more than
3 h after** the first side.

## 3. Schema changes that would actually be necessary

| Change | Needed? | Why |
|---|---|---|
| New tables / columns for v1 | **No** | Pure derivation from existing columns |
| New index | **No** | Per-story reads use `idx_articles_event_id`; the bulk export read (all attached articles, joined to events) measured 6.6 s |
| New DB helper | Yes (code only) | `database.get_articles_for_events()` returns `id, source, language, title, url, summary, image_url` and omits `published`/`fetched_at`; add a sibling that returns the two time columns (or extend the column list) |
| `event_snapshots` (append-only: `event_id, taken_at, n_articles, lean_counts_json, summary_sha256`) | **Only for v2** | The *article* history is fully reconstructible, but the history of Paksh's own **summary/framing text** is not: `analysis_json` keeps only the latest. To show "the account changed from X to Y" that must start being recorded now. Optional; separate decision |

## 4. How a timeline is generated (PROPOSED algorithm)

For one story, given its articles and its `region` (needed because `lean_of(source, region)` decides whether
an international outlet votes):

1. **Normalise time** per article (section 5) -> `(t_utc, precision)`.
2. **Identify the outlet**: `owner = OWNER_BY_SOURCE.get(source, source)`, `lean = lean_of(source, region)`.
3. **Sort** by `(t_utc, owner, article_id)` - fully deterministic.
4. **Collapse to first-seen per owner**: the first article of each owner becomes a *point*; later articles from
   that owner only increment that point's `n` (one vote per owner, exactly as the bias bar).
5. **Derive milestones** (section 8) from the ordered points.
6. Emit the compact JSON (section 12). No point is ever dropped for being late, unrated or international -
   they are shown, but flagged as non-voting (`v:false`), so the picture stays honest and the arithmetic
   invariant holds: the per-side owner count at the end of the timeline **must equal** the story's existing
   `coverage` counts (this becomes a hard test; 99.98% already holds on real data).

Prototype cost on real data: **all 19,637 stories in 2.4 s (0.12 ms per story), single core, pure Python.**

## 5. How timestamps are ordered

| Situation | Measured share | Rule |
|---|---|---|
| ISO time with offset | 92.8% | Use it, converted to UTC. `precision = minute` |
| `published` later than `fetched_at` by > 1 h (clock skew, local time mislabelled as UTC) | 2.7% of ISO | Clamp to `fetched_at` (we cannot have seen it later than we fetched it). `precision = clamped`; never used for a "first reported" claim on its own |
| Date only (`YYYYMMDD`, GDELT) | 7.1% | Use that date at 12:00 UTC (clamped to `fetched_at`). `precision = day`. Order **within** a day is unknown, so if the earliest point is day-precision and any minute-precision point falls on the same date, the UI says "earliest reports (dates only)" and does not name a single first outlet |
| Free-text date without timezone | 0.1% | Do **not** guess the timezone (India vs UTC is 5.5 h): use `fetched_at`, `precision = fetched` |
| Published far before the rest of the story (> 30 days before fetch) | 0.4% of articles | Keep as a point, but mark `outlier` and exclude it from the time axis and span (a stray background piece must not stretch a two-day story into a two-month one) |
| Ties | - | `(t_utc, owner name, article id)` |

**Wording matters:** the earliest time is *the earliest claimed publication among the articles Paksh
ingested*, not "who broke the story" - Paksh reads a fixed roster and feeds, and ingest lag has a median of
5.4 h (p95 37 h). The UI must say "earliest report in Paksh's data" and must never present a leaderboard of
"fastest outlets" (an editorial claim Paksh cannot support).

## 6. Duplicate and syndicated articles

Measured inside stories: 10,468 articles (6.2%) repeat an earlier headline exactly - **7,442 by the same
owner** (updates/re-posts) and **3,026 by a different owner** (wire-style syndication). Only **2.4%** of the
first-seen points repeat another owner's headline.

- **Same owner, any number of articles:** collapsed into one point (`n` counts them). This is the vote rule.
- **Same headline, different owner (syndication):** each owner still gets its own point and vote (they are
  separate publishers), but the later point carries `dup:true` so the UI can say "same headline as X". Not
  dropped, not merged.
- **Google News redirect duplicates** (the same story via several redirect URLs from one outlet) fall under the
  same-owner rule. `articles.url` is already UNIQUE, so identical URLs cannot recur.
- **Different-language versions** of one outlet's story are separate articles with the same owner -> one point.

## 7. How source identity is represented

The unit is the **owner**, because that is what votes. Each point carries: `o` (owner display name), `s` (the
masthead of its first article, so "Times of India" shows even if the owner is "Times Group"), `l` (lean:
`left|center|right|international|unrated`), `v` (does it vote in the bar for this story's region - the same
`lean_of(source, region)` decision as the bar), and `n` (articles from that owner). Co-owned mastheads share
one point exactly as they share one vote; the UI can expand "+ Navbharat Times". Lean labels come only from
`sources.py` - the timeline never introduces, infers or changes one.

## 8. How timeline events (milestones) are generated

Deterministic rules over the ordered voting points (non-voting points appear in the axis but never trigger a
milestone):

| Milestone | Rule |
|---|---|
| `first` | Earliest point, only if not ambiguous under the day-precision rule above |
| `side_joined` | First time each of Left / Centre / Right appears after the first; carries `after_h` from the first point |
| `breadth` | The moment distinct voting owners first reach 3, 5, 10, 20 (only those reached) |
| `one_sided_for` | If a Coverage Gap (`L+R >= 4`, smaller side <= 25% of larger - the existing `_gap_qualifies`) exists at the end: hours since the first report during which the smaller side had 0 owners, or "still none" |
| `quiet` | A gap of > 12 h with no new voting owner, then a new one ("coverage resumed") - shows late developments |

Milestone text is generated in the frontend from these structured records (English + Hindi templates, same
pattern as the existing `STR` strings) - not by an LLM, so it cannot invent anything.

## 9. How this interacts with the existing story pages

- `StoryPage` already shows: headline, summary, bias bar + legend, Coverage Gap row, "Who covered it" outlet
  list (`#arts`), and, when a story belongs to a storyline, `StorylineTimeline` (a *cross-story* timeline).
  Story Evolution adds one **within-story** section, "How coverage developed", between the legend/gap row and
  "Who covered it". It is the same idea one level down and reuses `BIAS` colours and the `StorylineTimeline`
  visual language, so the page reads as one system.
- **Coverage Gap tie-in (the differentiator):** the existing gap row says "5 Left, 7 Centre, no Right
  coverage yet". With the timeline it can say "no Right coverage 31 hours after the first report" or "Right
  joined after 19 hours". No new data, just the timeline read against the existing gap definition.
- **Storyline page:** each episode (event) row can show its own span and side-joins; the storyline's overall
  span is the union. Optional, later.
- **Static pre-rendered HTML** (`_story_html`): PROPOSED to add the one-sentence summary ("First reported by
  X (Centre); Left joined 4 h later and Right after 19 h; 12 outlets in 31 h.") to the crawlable body - text
  only, no new JSON-LD. Unchanged: `dateModified`, canonical, OG.
- Nothing here touches publication gating, `content_complete`, the bias arithmetic or the Coverage Gap
  *definition* (it only reads them).

## 10. Computational cost (MEASURED)

| Step | Time |
|---|---|
| Bulk read: all attached articles joined to non-demo events (170,030 rows) | 6.6 s |
| Derive timelines for all 19,637 stories | 2.4 s (0.12 ms each) |
| Per-story payload | avg **390 B**, median 3 points, p90 13, p99 26, max 58 points (4.4 KB) |
| If every story carried it | 7.7 MB total; only the 8,654 exported stories matter (~3.4 MB across 8,654 files, +~4% each, compresses well) |

Export today already takes ~7-8 minutes (og cards dominate); this adds under 10 seconds.

## 11. Caching strategy

**None needed for v1.** The function is deterministic and cheap; recomputing every export is simpler and
cannot go stale. Two properties matter more than a cache:

- **Byte-stable output:** the deterministic tie-break means a story whose article set did not change
  produces an identical timeline, so `safe_autopush`'s git diffs stay small (only stories that gained
  articles change).
- **Do not put it in `events.json`.** The home feed is loaded on every page; the timeline goes only in the
  per-story file, fetched when a story is opened (browser caching per file already works: `/data/events/<id>.json`).

If export time ever matters, memoise on `(event_id, hash of sorted (article_id, published, fetched_at))`.

## 12. API shape (static JSON - there is no server)

Added to `/data/events/<id>.json` as one new key; absent when the story has fewer than 2 owners:

```json
"timeline": {
  "v": 1,
  "start": "2026-09-18T05:00Z", "end": "2026-09-19T12:30Z", "span_h": 31.5,
  "points": [
    {"t": "2026-09-18T05:00Z", "o": "The Print", "s": "ThePrint", "l": "center", "v": true, "n": 3, "p": "m"},
    {"t": "2026-09-18T09:12Z", "o": "The Hindu Group", "s": "The Hindu", "l": "left", "v": true, "n": 1, "p": "m", "dup": true},
    {"t": "2026-09-18T23:40Z", "o": "Republic World", "s": "Republic World", "l": "right", "v": true, "n": 2, "p": "m"}
  ],
  "milestones": [
    {"k": "first", "o": "The Print", "l": "center"},
    {"k": "side_joined", "l": "left", "after_h": 4.2},
    {"k": "side_joined", "l": "right", "after_h": 18.7},
    {"k": "breadth", "n": 5, "after_h": 9.0},
    {"k": "one_sided_for", "side": "right", "hours": 18.7}
  ]
}
```
`p`: `m` minute, `d` day-only, `c` clamped (clock skew), `f` fetched-time fallback. Keys are short because the
file is fetched per story; the JSON is UTF-8, no HTML.

## 13. Frontend representation (PROPOSED)

- **Section "How coverage developed" / "कवरेज कैसे बढ़ा"**, between the bar legend/gap row and "Who covered it".
- **One-line summary first** (always visible): the milestone sentence, e.g. "Earliest report in Paksh's data:
  The Print (Centre). Left joined 4 h later, Right after 19 h. 12 outlets in 31 h."
- **Desktop:** a horizontal time axis (linear, from the first report), one dot per owner coloured by lean
  (existing `BIAS` colours, with the lean also spelled out so it is not colour-only), plus a small stepped
  area of cumulative Left/Centre/Right owner counts. Hover/focus a dot -> outlet, masthead, time, lean.
  Clicking scrolls to that outlet in `#arts`.
- **Mobile (protected layout):** the one-line summary plus a **collapsed** disclosure ("Show timeline") that
  expands to a vertical list: `+0h The Print · Centre`, `+4h The Hindu · Left`, ... No horizontal chart, no
  new fixed elements. Default-collapsed on mobile, default-open on desktop is PROPOSED; Sameer to confirm.
- **Day-precision stories** show dates instead of times; outliers are shown separately as "earlier background
  report", off the axis.
- **Accessibility:** semantic ordered list as the primary representation, chart marked decorative with the
  list as its text alternative; Hindi strings for every label; `prefers-reduced-motion` respected (no animation
  needed anyway).
- **Hidden entirely** when the story has fewer than 2 owners.
- **Honest labelling:** a one-line note "Times are when outlets say they published; Paksh only sees the
  outlets it tracks." (link to Methodology). No per-outlet speed rankings anywhere.

## 14. Invariants (all preserved)

The bar stays arithmetic (distinct owners per lean, one vote per owner); lean labels stay editorial; no
new AI step (milestone text is template-generated); the site stays a static export; data paths stay
absolute (`/data/events/<id>.json`); English + Hindi; no schema change; publication gating,
`content_complete` and the Coverage Gap definition are read, never changed.

## 15. Risks and how the design contains them

| Risk | Containment |
|---|---|
| Timestamps are claims, not truth (live blogs re-stamp; feeds differ) | Precision flags; "earliest report in Paksh's data" wording; no rankings |
| A clustering mistake merges an old, unrelated article | `outlier` rule (>30 days) keeps it off the axis; the existing clustering guards are unchanged |
| GDELT day-only dates make "first" ambiguous | Explicit ambiguity rule (section 5); never name a single first outlet in that case |
| Implying causation ("Right ignored it for 19 h") | Neutral phrasing ("Right coverage joined after 19 h"); the existing Coverage Gap note ("a count, not a judgement") is shown alongside |
| Timeline disagrees with the bar | Hard test: per-side owners at timeline end == story `coverage` (99.98% today; the 4 exceptions have no articles and get no timeline) |
| Mobile clutter | Collapsed-by-default disclosure; no chart on mobile |

## 16. Validation plan

1. **Unit tests** on a pure `derive_timeline(articles, region)`: skew clamp, date-only, tz-less text, ties,
   same-owner collapse, cross-owner duplicate flag, outlier, determinism (shuffle input -> identical output),
   empty / single-owner -> no timeline.
2. **Invariant test on real data (read-only):** for every story, per-side owner sets from the timeline equal
   `analysis_json.coverage` (expect the same 99.98%; investigate any new difference).
3. **Export test** in the sandbox: `events/<id>.json` gains `timeline`; `events.json` does not; total added
   bytes within budget; two consecutive exports byte-identical for unchanged stories.
4. **Browser checks** (desktop + 375 px, EN + HI): section appears/hides correctly, list order matches JSON,
   click-to-scroll, no overflow, no console errors, no CSP violations.

## 17. Suggested order of work (when approved)

| Step | Scope | Rough size |
|---|---|---|
| E1 | `derive_timeline()` + DB helper + per-story JSON + tests (sections 4-8, 12, 16.1-16.3) | ~1 day |
| E2 | Story page section, EN/HI strings, mobile disclosure, one-line summary in the pre-rendered HTML | ~1-2 days |
| E3 | Gap tie-in wording; storyline episode spans | ~0.5 day |
| E4 (optional, separate decision) | `event_snapshots` so the *summary/framing* history also accrues from now on | ~1 day + a schema change |

## 18. Decisions needed from Sameer before E1

1. Mobile default: collapsed disclosure (proposed) or always visible?
2. Wording: "Earliest report in Paksh's data" (proposed) - acceptable, or different?
3. Show non-voting international/unrated outlets on the axis (proposed: yes, visibly greyed) or hide them?
4. Start recording summary/framing snapshots now (E4) even if the UI comes later? It is the only part where
   waiting loses history that cannot be reconstructed.
