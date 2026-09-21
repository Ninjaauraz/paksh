# Intelligence Program — Phase 15: Claim and evidence graph

*2026-09-22 · hand-judged by the engineer (Claude) from headline + excerpt; single rater; n = 38 decidable claims.*

## STATUS: **CONDITIONAL** — a small, honest claim view was built inside Story Evolution; it is not a general claim extractor.

## Decision

Paksh already extracts *quantity* claims (deaths, injured, arrested, missing, plus money / percentages), stores them in `si_claims`, and
compares person-count tallies (`UPDATES` / `CONTRADICTS`). A free-text "claim" model (who did what) would need an LLM and a truth-adjacent
judgement; measured deterministic insufficiency does not yet justify that. So this phase adds only the missing dimension: **who says it,
and how it is attributed.**

## What was implemented

* `claim_attribution()` in `story_intelligence.py` — a deterministic taxonomy: `POLICE`, `MILITARY`, `HEALTH_AUTHORITY_OR_MEDICS`,
  `EMERGENCY_SERVICES`, `STATE_MEDIA`, `INTERNATIONAL_BODY`, `OFFICIAL`, `DOCUMENT_OR_STUDY`, `SOURCES_OR_MEDIA_REPORT`, `NAMED_PARTY`
  (an actor named in "X says…"), and `PUBLISHER_ASSERTION` (**no source named in the text**). Every claim now carries `attribution` and
  `attribution_cue`. Nothing here says a figure is true.
* `build_claim_graph()` in `story_evolution.py`, on demand: one node per (measure, value) with supporting articles, distinct reporting events,
  publishers, attribution per type, first-reported time; edges = the engine's UPDATES / CONTRADICTS. Wording is fixed: several reporting
  events is "**not confirmation** — the reports may share an unseen source". No node is ever labelled confirmed or verified.
* No new tables, no LLM, no persistence (the `si-3` engine tables are unchanged).

## Measured (n = 38 decidable of 40 random person-count claims; 2 Hindi items cut off and excluded)

| Outcome | Count |
|---|---|
| Correct | 34 (89 %) |
| Coarse but not wrong (police reported as `NAMED_PARTY`, e.g. "OPP", "CPD") | 2 |
| Wrong before fixes: fire department read as medics; trailing "…3 missing: Police \| India News" missed | 2 — **both fixed** (`EMERGENCY_SERVICES`; site suffix allowed) |

87 % of claims are `PUBLISHER_ASSERTION` (headlines rarely name a source), so the graph mostly says "the publisher states it"; among the
7 non-default attributions in the sample 4 were exactly right, 2 coarse, 1 wrong (fixed). n is small (±8 points).

## Real example (event 22334)

`deaths 3` (Afghanistan says, Al Jazeera and 5 others, 3 reporting events) vs `deaths 28` (militants killed, reported by Pakistan-side
coverage): the graph shows a `CONTRADICTS` edge with each side's attribution. It says they differ and who reported which — not which is right.

## Known limits

Headline/excerpt only; person-count tallies only; a named speaker is not resolved to a type ("Ukraine says" is `NAMED_PARTY`); Hindi
attribution cues are not covered; the graph cannot tell if two attributed reports share one source.

## Gate

Useful internally for audit and for later phases; not for public display. Rollback: revert the commit.
