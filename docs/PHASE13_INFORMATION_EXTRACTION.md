# Intelligence Program — Phase 13: Information extraction / Story Intelligence v3

*2026-09-22 · every number below was measured on the live database (D:) and hand-judged by the engineer (Claude) from headline + excerpt — a single rater, small n, no editorial verification of the underlying news. Labelled sets and all intermediate files are kept outside the repository.*

## STATUS: **CONDITIONAL** — proceed to Phase 14 on the parts that measured well; developments stay internal-only.

## Objective

Move from "which articles are in this story?" to "what does each article actually add?", extending the existing Story Intelligence tables rather than creating a parallel model.

## What was discovered (audit of what SI already answers)

| Question | Existing mechanism | Measured quality |
|---|---|---|
| Repeated reporting | `DERIVED` (restates ≥ 0.80 cosine / near-duplicate), `SAME_OWNER` accounting | ≈ 98 % (123 / 125 decidable; Phase 8) |
| Attribution | wire tags, named outlets, secondhand cues, fetched datelines | 0 wrong of 14 decided |
| Independent reporting | `INDEPENDENT` = earliest + new figures; promotion on fetched text OFF | earliest ≈ 85 %; abstains on ~⅓ of articles (≈ 40 % of those are missed restatements) |
| **What each article adds** | *nothing dedicated* — only `novel_anchors` inside some verdicts | **not measured before this phase** |
| Developments | typed headline cues | **47 % precision** (see below) — much worse than the 75 % (n = 12) of Phase 8 |
| Figure changes | `UPDATES` / `CONTRADICTS` on person-count tallies | **65 % precision** at n = 40 (Phase 8: 80 %, n = 12) |
| Chronology | `order_time` with basis, three timestamps kept apart | 0 derivation links point to a later article (1,463 links) |

The larger samples in this phase were unkind to two earlier numbers; that is reported as found.

## What was implemented (minimum required)

1. **`information_delta`** (computed in `analyze_story`, returned per article as `adds`, **not yet persisted**). Decision: an article *adds information* when its highest embedding cosine to any earlier article of the story is below `ADDS_COS = 0.70` (semantic novelty). Figures (new numbers) and entities are reported but do not decide. Without cached vectors it falls back to "a new figure ≥ 10 (not a year) or a new development type" and says so (`basis`). It is a separate axis from independence: a same-publisher follow-up can add information and still be `DERIVED / SAME_OWNER`.
2. **Figure edges (`si-3`)**: two tallies are compared only when their articles are clearly the same event (cosine ≥ 0.75, else ≥ 3 shared tokens without vectors); `death toll rises to six, 11 rescued` now reads 6, not 11.
3. **Development cues tightened**: `SC`/`HC` abbreviations, bare `verdict`, `convicted <descriptor>`, `house arrest`, `denied access/entry/bail…`, roundups/live blogs/`World in Brief`, and generic `raid` descriptors no longer trigger; court cues now need a court action (`Supreme Court strikes down`, `moves Supreme Court`, `grants bail`); lenient baseline widened (`jail`, `protection`, `strikes down`, `extradit`, SC/HC).
4. **`dev_judge.py` — a narrow, veto-only model check — built, measured, NOT adopted, NOT wired** (below).
5. Engine version **`si-3`** so the existing queue reprocesses stories; a latent bug from Phase 11 was found and fixed on the way (two fetched-text regexes had lost their `\b` word boundaries and could never match).

Not implemented: persistence of `adds`; claims beyond person-count tallies; event-time inference; any change to independence classes; an LLM in the pipeline.

## Datasets and methods

* **A. Information added** — 60 fresh stories (seed 2026, excluding all earlier evaluation stories), 637 non-first articles; 130 sampled (half predicted-adds, half predicted-repeat), shown with the 3 most similar earlier headlines. **108 decidable** (22 off-topic/junk/unclear excluded). Judgement: does the article state at least one specific fact/figure/actor/step/angle not in the earlier headlines/excerpts? Rules were selected on the first 67 and checked on the last 41 (hold-out).
* **B. Developments** — 45 random typed candidates from the production table (old rules) and 45 from a fresh in-memory run over the 4,000 processed stories (new rules) = **90 judged**.
* **C. Figures** — 40 random edges from production (old rules) and 40 from a fresh run (new rules).
* **D. LLM veto** — the 90 development candidates through the existing provider pool (Groq `gpt-oss-120b`, Gemini `2.5-flash-lite`).

## Results

**A. "Adds information"** (P = precision, R = recall on the label *adds*):

| Predictor | n | P | R | accuracy |
|---|---|---|---|---|
| v1 — any new figure or development | 108 | 0.61 | 0.69 | 0.67 |
| cosine < 0.80 | 108 | 0.58 | 0.90 | 0.67 |
| cosine < 0.75 | 108 | 0.73 | 0.83 | 0.79 |
| **cosine < 0.70 (chosen)** | **108** | **0.82** | **0.69** | **0.80** |
| … same rule, hold-out only | 41 | 0.80 | 0.63 | 0.76 |

Semantic novelty beats figure novelty by 13 accuracy points; small integers, list numbers and reformatted figures were the false positives. The residual ~20 % error is the fuzzy boundary of "what counts as new" (an emotional farewell vs a memo; a Hindi translation of an English report), not a data gap a rule can close. **Confidence ±8 points (n = 108, one rater).**

**B. Developments (typed cues)** — old rules **19 / 45 = 42 %**, new rules **21 / 45 = 47 %**; typed candidates fell 104 → 75 across 4,000 stories. Failures: the thing was already reported under other words (`cancelled` / `called off`, `rejects` / `denies`), a cue used as a descriptor, tangents in grab-bag stories, roundups. Corroborated by ≥ 2 publishers: 6 / 8 (new rules), 16 / 28 pooled = 57 %; single-publisher 41 %. Cosine gating did **not** help (0.42–0.47 at every band), so the errors are semantic, not "wrong event".

**C. Figure edges** — old rules **26 / 40 = 65 %** (errors: two tallies of *different* events in one story, `11 rescued` read as deaths, aggregates); new rules **35 / 40 = 87.5 %**; edge count 107 → 42. (Recall not measurable: no ground-truth list of all tally changes.)

**D. LLM veto on developments** (≈ 80 provider calls, 100 s, cached; 5 invalid answers correctly fell back to "keep"):

| Rule | kept / 90 | precision | recall |
|---|---|---|---|
| deterministic only | 90 | 0.44 | 1.00 |
| + LLM veto | 37 | **0.62** | 0.57 |
| new rules only: deterministic → + veto | 45 → 18 | 0.47 → **0.72** | 1.00 → 0.62 |
| veto + ≥ 2 publishers | 11 | 0.73 | 0.20 |

The veto helps (+18 to +25 points) but **no variant reaches a level fit for public display (≥ 85 %)**, it discards 40 % of the developments I judged real, adds a provider dependency and non-determinism, and is small-n (±13 points). **Not adopted.** Kept inert (validated JSON, a quote-from-headline requirement, a named-earlier-headline requirement, `CANNOT_TELL` default, failures keep the candidate, cache by prompt hash) so a future phase can revisit it against a larger labelled set.

**Other gate measures.** Runtime: engine 5–7 ms per story; full 4,000-story dry run with vectors 23 s. Database growth: none (no new tables; `adds` not persisted); the `si-3` bump re-queues the ~4,000 processed stories, drained 200/night by the existing queue. Reproducibility: deterministic (same input → same output; tested). Regressions: 51 test files (below); clustering, lean, source selection, bias bar, export untouched.

## Gate decision (what Phase 14 may use)

| Signal | Use in Phase 14 |
|---|---|
| Reporting events, repeat / derived / attributed / independent classes | **yes** |
| `adds_information` (semantic novelty) | **yes**, internal, with `max_similarity_to_earlier` shown |
| Figure edges (87.5 %) | **yes**, internal, with both values and sources |
| Developments (47 %; 57 % when ≥ 2 publishers) | **internal only, flagged low-confidence; never public** |
| Model judgement | none |

## Files, tests, rollback

* Changed `story_intelligence.py` (`information_delta`, cues, figure gate, `si-3`); new `dev_judge.py`, `test_dev_judge.py`; `test_story_intelligence.py` TEST 13 (11 checks); this doc.
* Tests: full suite 52 files, 0 failures (run after the Phase 15 changes).
* Rollback: revert the commit; the queue re-derives rows under the previous engine on the next reprocess (`si_control` pause available).
