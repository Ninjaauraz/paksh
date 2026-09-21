# Source selection — how Paksh decides which articles a story is built from

*Companion to [SOURCE_UTILIZATION_AUDIT.md](SOURCE_UTILIZATION_AUDIT.md), which has the evidence for why each rule exists.*

Paksh chooses articles at **three separate points**. They are easy to confuse, so each is described on its own.
Nothing here decides any outlet's lean, and nothing here touches the bias-bar arithmetic (one vote per owner, from the
outlet labels in `sources.py`).

```
ingest (RSS + GDELT)  ->  [1] the clustering WINDOW  ->  clusters  ->  events  ->  [2] the PROMPT PICK  ->  summary
                                                                          \-> [3] the story page lists ALL of the event's articles
```

## 1. The clustering window — which ingested articles get considered at all

**Where:** `database.get_unclustered_articles()` → `select_unclustered_window()` → `_fair_take()`.

Every pipeline run hands clustering at most **3,000** un-grouped articles. There are usually far more waiting (about 9,000 from
the last day alone), so *which* 3,000 decides which outlets can ever appear in a story.

**The rule, in plain English**

1. **Only recent articles.** Anything fetched more than **72 hours** ago is left out. Old news must never become a "new" story.
2. **Rated outlets first.** Outlets in the registry (`LEAN_BY_SOURCE`) claim the window before anyone else, because only they can
   form a story (a story needs at least two rated outlets).
3. **A small reserve for vetted outlets that don't vote.** Up to **10%** of the window is held for outlets that are in the editor-verified
   foreign registry but carry no vote. They add regional breadth and can never create a story on their own. If they don't use the
   reserve, it goes back to the rated outlets — **never** to unknown domains.
4. **Unknown long-tail domains** get only what is left over (as before).
5. **Inside every tier, every outlet gets an equal share.** Round 1 takes each outlet's newest article, round 2 its second newest, and so
   on (at most 60 per outlet). When the cap lands in the middle of a round, the fresher articles win.

**Why it changed.** The old rule took "the newest 3,000, at most 60 per outlet". Ingest visits outlets one after another, so the outlets
visited *last* always carry the newest timestamps and won the window every time. Measured over the last 7 days, outlets at the start of the
registry (The Hindu, The Indian Express, Mint, The Wire, Scroll…) reached clustering **32%** of the time; outlets at the end
(the international outlets) **87%**. The Indian Express: 13%.

## 2. The prompt pick — which of a story's articles the summary model reads

**Where:** `source_selection.select_sources()`, called from `analyze.build_prompt()`.

A story can have dozens of articles; the model reads at most **12**. Only articles that already belong to the story are ever chosen —
this step can't add an outlet or change a label.

**Step 1 — collapse copies into independent reports.** Within one lean, articles are treated as one report if they come from the
**same owner**, or their headlines are **near-identical** (word overlap ≥ 75%; a wire story republished under many mastheads).
The 75% line was checked against real clusters: every same-lean pair between 75% and 85% was the same AP story re-headlined.
Articles from *different* leans are never merged — each side keeps its own voice, so a side that only has a syndicated copy is still heard.
International outlets are kept apart by their *underlying* lean, because on a World story they vote on it.

**Step 2 — pick the richest copy of each report.**

**Step 3 — fill the 12 slots, in this order of priority:**

| # | Priority | How it is applied |
|---|---|---|
| 1 | **Independent reporting** | one article per independent report; copies are dropped |
| 2 | **Factual richness** | score weight 55%: longer real excerpt beats a bare headline |
| 3 | **Regional diversity** | +0.30 bonus for the first outlet from a home region not yet in the pick |
| 4 | **Ideological diversity** | the existing guarantee, kept: up to **2 reports from every lean** that covered the story are picked *first* (3 for the international tier: one per possible side) |
| 5 | **Freshness** | score weight 25%: newer beats older within the story |
| 6 | **Publisher credibility** | score weight 20%: reviewed registry outlets beat provisional / low-confidence ones |

Rated outlets always fill before the unrated long tail. There is **no quota beyond the per-lean guarantee**: if the coverage is lopsided, so is
the pick. It is deterministic — the same articles always give the same pick.

## 3. The story page — all of the story's articles

The "Who covered it" list shows **every** article in the event, not just the prompt's 12. The bias bar counts **distinct owners**
from all of them. Neither is affected by step 2.

## What this does not do

* It does not add publishers. Widening the set of outlets that *exist* in the pipeline (more feeds) is an editorial decision — see the audit.
* It does not detect syndication perfectly: two independent outlets that happen to write a near-identical headline are treated as one report
  *for the prompt only*. They still both appear on the story page and both still count in the bias bar.
* Regional diversity beyond India cannot improve until more non-India outlets are actually ingested (audit §7).

## Tuning knobs (all in code, none in the database)

| Setting | Value | File |
|---|---|---|
| window size / per-outlet cap | 3,000 / 60 | `database.get_unclustered_articles` |
| window recency bound | 72 h | `database.WINDOW_MAX_AGE_HOURS` |
| reserve for vetted non-voting outlets | 10% | `database.WINDOW_TAIL_SHARE` |
| prompt size / guaranteed per lean | 12 / 2 | `analyze.MAX_ARTICLES_PER_EVENT` |
| "same report" headline overlap | 0.75 | `source_selection.SIM_SAME_REPORT` |
| score weights (richness / freshness / credibility) | 0.55 / 0.25 / 0.20 | `source_selection.W_*` |
