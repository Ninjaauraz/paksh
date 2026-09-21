# Intelligence Program — Phases 16–20: decisions and consolidation

*2026-09-22 · measured on the live database (D:). Hand judgement by the engineer (Claude), single rater. Nothing in this page is public.*

## Phase 16 — independent-information engine: **NOT BUILT (PASS as "already exists")**

A *reporting event* (root article + the members that restate it) **is** an information unit; `independence` on it says whether its origin
looks independent, derived or attributed. `story_evolution.py` already lists them with publishers, adds-information and provenance. A new
engine would duplicate this and add a version, queue integration and a second thing to keep consistent.

Measured over the 4,000 processed stories (stats from the current production rows, mostly engine `si-1`/`si-2` until the queue drains `si-3`):
of 1,981 stories with ≥ 3 publishers, **1,579 (80 %) show ≤ 1 independent origin**, 394 show 2–3, 8 show 4+; the median of
independent origins ÷ publishers is 0.25.

**Caution (must travel with the number):** this is a *lower bound*. About one third of articles are `UNCERTAIN` (never promoted to
`INDEPENDENT`; that promotion stays OFF), and Paksh only sees headline + excerpt. So it must never be shown as "only N independent
sources"; the truthful reading is "Paksh could confirm N independent origins from the text it holds".

## Phase 17 — coverage-gap intelligence: **BLOCKED for per-outlet statements; nothing built**

Test: 40 random stories (≥ 5 articles), for each the articles fetched within ± 2 days by publishers **not** in the story, compared with the
story's centroid (cached bge-m3 vectors).
**11 of 40 stories (27.5 %)** have same-topic coverage (cosine ≥ 0.80) by a non-member publisher sitting in a *different* event (event
fragmentation), e.g. NPR and AP on the Buffett story (0.93), CNN and the Telegraph on the Los Angeles helicopter crash (0.88). A naive
"not covered by X" would therefore be wrong in more than a quarter of stories, from fragmentation alone.

The remaining false-gap rate (articles Paksh never fetched) cannot be measured without visiting publishers' sites, which is out of bounds, and
Paksh's eligibility ceiling for Google News items is known. So an absence claim cannot be validated, and clustering, quotas and the merge
cap must not be changed for this. Existing side-level "blindspot / one-sided" detection stays as it is: it counts distinct outlets by lean and
is stated as arithmetic.

If ever built, the only permitted wording is an observation about the corpus — `NOT_OBSERVED_BY_PAKSH: no article from <outlet> was found in
Paksh's corpus for this story` — never "missing", "ignored", "silent" or "avoided", and it must be suppressed whenever a same-topic article
from that outlet exists in any event (the 27.5 % case above).

## Phases 18 and 19 — reader UI and graph search: **BLOCKED (not built)**

Gate 18 required Phases 13–17 to pass. They did not: developments 47 % precision, adds-information 0.80 (± 8), 40 % of stories are broad
topic clusters where evolution is not meaningful, coverage gaps blocked. Adding to the protected frontend (`app.jsx`, static export,
`export_static.py` split markers) would expose experimental intelligence before it is evaluated. Graph search (19) needs stable edges; the only
edge types that measured well (figure updates/contradictions, repeat/derived) are few and person-count-only, so a search over them would return
almost nothing useful and invite over-reading.

## Phase 20 — consolidation

One conceptual graph, **no second store**. Mapping:

| Concept | Where it lives | Status |
|---|---|---|
| Story | `events` | production |
| Article, publisher, owner | `articles`, `sources.py` (one vote per owner) | production |
| Original URL / publisher URL | `articles.url` (never overwritten) / `article_publisher_url` (`pu-1`) | additive provenance |
| Reporting event (information unit) | `si_reporting_events`, `si_reporting_event_articles` | internal |
| Independence, derived, attributed, uncertain | role + reason on those rows | internal, engine `si-3` |
| Adds information | computed per article in `analyze_story` (`adds`), not persisted | internal |
| Development | `si_developments` | internal, **low confidence** |
| Claim (figure) + attribution | `si_claims` (+ `attribution` in memory) | internal |
| Contradiction / update | `si_relationships` | internal, 87.5 % |
| Fetched-text evidence | `si_evidence`, `article_publisher_url` | bounded, robots-honouring |
| Story Evolution / claim graph | `story_evolution.py` (on demand) | internal |
| Work queue, versioning | `si_queue`, `si_control`, `ENGINE_VERSION` | production, non-fatal |

Retire nothing. Not to be added: an `information_units` table, a claim table beyond `si_claims`, a public API.

## Suite

Full suite after Phase 15: **52 test files, 0 failures.**
