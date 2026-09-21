# Intelligence Program — Phase 14: Story Evolution (internal)

*2026-09-22 · measured on the live database; hand inspection by the engineer (Claude), single rater, small n.*

## STATUS: **CONDITIONAL** — built and internal-only; meaningful for narrow events, not for broad topic clusters.

## What it is

`story_evolution.py` assembles, **on demand and with no new tables**, one auditable object per story from what Story Intelligence already
derives (recomputed with the current engine, so it can never disagree with the engine version in use):

`first_report`, `independent_reports`, `later_information` (articles that add information), `repeated_reports`, `same_publisher_articles`,
`reporting_events`, `uncertain`, `developments` (flagged low-confidence), `figure_changes`, `claim_graph` (Phase 15), a `timeline`, `shape`,
`reliability` and `limits`. Every item carries article ids and provenance: `published_at` (publisher claim), `first_seen_at` (when Paksh
fetched it), `order_time` + `order_basis`, `event_time` (**always null, never inferred**), `original_url` (as stored), `publisher_url`
(recovered, separate field, never replaces the original) and `evidence_source`.

```
py story_evolution.py --event 22334          # readable
py story_evolution.py --event 22334 --json   # full object
py story_evolution.py --sample 12 --seed 3   # random recent stories
```

## Measured

| Question | Result |
|---|---|
| Chronology | 0 of 1,463 derivation links point to a later article; timeline is non-decreasing by `order_time` (tested) |
| First report | "earliest in Paksh's corpus", with its time basis and the sentence "not necessarily the first report anywhere" |
| Inspection of 8 random stories | Repeats and independent origins read correctly in every case; "adds information" was plausible in most; 3 of 8 were not events but topic clusters |
| Shape | ~40 % of stories are **broad topic clusters** (many different pieces on one theme). There, "adds information" means "another angle", not "a new fact". The object says so through `shape.hint` / `shape.caution` |

## Gate reasoning

* Usable internally: first report, repeated / independent classes, figure changes (87.5 %), adds-information (0.80).
* Not fit to show readers: developments (47 %), and anything on broad-topic stories.
* No LLM, no new tables, no database growth, no scheduled cost (computed only when asked, ~10 ms per story).

## Files, tests, rollback

`story_evolution.py`, `test_story_evolution.py` (chronology, provenance, publisher-URL separation, unavailable case, shape, claim graph).
Rollback: delete the module; nothing else imports it.
