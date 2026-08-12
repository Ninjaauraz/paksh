# archive/ — obsolete one-off scripts

These are **dead** early-development / one-time-migration scripts. Nothing imports them
and nothing in the pipeline, scheduled tasks, or `CLAUDE.md` calls them. They were moved
here on 2026-08-12 to declutter the project root. They are kept (not deleted) only as
history — you should not need to run any of them again.

Note: some of these `os.chdir()` to an old `Downloads\paksh_project` path from before the
project moved to `C:\paksh_project`, so they won't even run as-is anymore.

| file | what it was |
|------|-------------|
| `rewrite_app.py`, `rewrite_app_2.py`, `rewrite_app_3.py` | one-time rewrites of `static/index.html` / `app.jsx` during the initial front-end setup |
| `update.py`, `extract.py` | one-off HTML surgery on `static/index.html` (early setup; point at the old Downloads path) |
| `merge_dryrun.py` | early event-merge dry run, superseded by `consolidate.py` |
| `migrate_published.py` | one-time DB migration that added the "published" flag; already applied |

Active tools that look similar but are **still used** stayed in the project root:
`consolidate.py` (event merging), `calibrate.py` (re-tune clustering thresholds),
`seed_demo.py` (demo/preview seed), `recount_migrate.py`, `cleanup.py`, `prune_cache.py`.
