# Paksh Editorial CMS - status and contracts

Branch work is incremental: one milestone at a time. This file records what exists, the
contracts later milestones must honour, and what is deliberately NOT done yet.

## Milestone 1 - safety foundation (implemented, tested in a sandbox)

New, isolated, standard-library-only package `editorial/` (Python 3.9+). It imports no
pipeline module, never opens SQLite, never opens a file for writing, never builds,
commits, pushes or contacts a network. No existing file was changed.

| Module | Purpose |
|---|---|
| `editorial/schema.py` | Versioned (`schema_version: 1`) strict-whitelist document schema + validator. Protected-field denylist scan (bias, lean counts, sources, evidence, framing, topic/region, image_url ...). Stable story ids only. Plain-text-only strings. Independent EN/HI. Placement time windows and contradiction detection. |
| `editorial/document.py` | Fail-safe loader (`absent` / `invalid` / `ok`, never raises), duplicate-key and NaN rejection, 1 MB cap, canonical JSON + sha256 document hash. |
| `editorial/resolve.py` | Overlay of display text onto generated rows (adds `row["editorial"]`, never alters generated fields), stale-override fingerprints, placement evaluation with automatic expiry, hide/pin ordering that never injects ineligible stories, orphan / stale / missing-translation audit. |
| `editorial/revisions.py` | Immutable content-addressed `Revision`, hash-chained audit log, truthful `PublishState` ladder (only `PUSHED -> LIVE_CONFIRMED` reaches "live"), optimistic-concurrency `check_base`, idempotent no-op detection, rollback-as-new-revision. |
| `editorial/permissions.py` | Role policy: administrator / editor / read_only, additive, default-deny, role only from a members-table record. Every editor can publish directly. |
| `editorial/gate.py` | The single decision point for preview and publish (permission -> validation -> concurrency -> idempotency). Decides only; performs no action. |
| `editorial/library.py`, `editorial/cli.py` | Read-only story library and CLI (`validate`, `audit`, `library`). Refuses database files. |

Run the tests: `py test_editorial_schema.py`, `py test_editorial_resolve.py`,
`py test_editorial_revisions_permissions.py`.

### Key contracts for later milestones

* **Resolution runs on FULL generated rows** (as returned by `database.get_all_events()` /
  `get_events_by_ids()`), *before* `export_static._lighten()` shortens summaries. Staleness
  fingerprints are taken over that full text (`title`, `title_hi`, `summary`, `summary_hi`).
* **Generated fields are never modified.** The exporter (Milestone 2) must prefer
  `row["editorial"]["display"]` when present and otherwise use the generated field, then run
  the existing `_clean_text` (em/en-dash stripping) on the chosen text.
* **Absent or invalid document == today's behaviour**, byte for byte.
* **Anything that publishes must call `gate.check_publish` first**; if it raises, nothing may
  be built, committed or pushed.
* **"Live" may only be shown after the public URL is observed serving the revision.**
* Adding a document section (homepage, pages, navigation, media) requires a `schema_version`
  bump and an explicit schema extension; unknown sections are rejected today.

### Findings from the repository verification (Milestone 0)

* `export_static.py` and `safe_autopush.py` do **not** take the pipeline lock themselves. Only
  `live.py` (in-process) and the `*_scheduled.bat` files (via `runlocked.py`) do. A manual
  `py export_static.py` is therefore unlocked. The Milestone 6 publisher must take the same
  lock (`runlocked.acquire`).
* `runlocked._pid_alive` shells out to Windows `tasklist` and returns "alive" on any error, so
  on a non-Windows host a stale lock is never reclaimed. Lock tests must run on Windows.
* `export_static.main()` calls `paksh_paths.require_production()` first and cannot run without
  the verified production data directory. This is a safety property: it cannot be run by
  accident from a development checkout.
* `database.update_event()` rewrites the whole `analysis_json`; storing editorial text there
  would be overwritten by re-analysis paths. Editorial data therefore stays separate.
* `homepage.json` is written but not read by the frontend; homepage order comes from
  `feed_rank` in `events.json`. `HomeView` hardcodes its tier sizes.
* Existing test status in the Linux sandbox: `test_export_collapse_guard`, `test_homepage_rank`
  and `test_section_rank` pass. `test_phase30cg_export_lock` needs the Windows path
  `C:/paksh_project/paksh`; `test_og_images` needs `fontTools`; `test_story_page_p1` needs the
  locally-vendored Babel (git-ignored). These are environment limits, not regressions.

### Measuring export duration safely (not yet measured)

A full export cannot run in the development checkout (the production guard refuses it, by
design). To measure without touching production, on the Windows machine: copy a verified
backup of `paksh.db` and a copy of the repo to a scratch directory outside `D:\Paksh_Data`,
create a scratch data directory with its own marker as the status report describes, run
`py export_static.py` there with timing, and discard the copy. Do not run it against
`D:\Paksh_Data`.

## Not implemented yet

Everything beyond the foundation: exporter integration, overrides in story HTML / JSON /
OG / RSS / sitemap, media, homepage modules, pages and navigation, Supabase tables and RLS,
the admin UI, drafts and previews, the publishing worker, scheduling, analytics.
