# Manual maintenance tools

These scripts are **not** part of the automatic pipeline (ingest → cluster → analyze →
export). You run them **by hand, occasionally**, when you need them. In VS Code they're
nested under this file in the Explorer to keep the project root tidy.

Always run from the project root (`C:\paksh_project\paksh`) with `py <script>`.
Most default to a **safe dry run** and only change data when you add `--apply`.

| tool | what it does | how to run |
|------|--------------|-----------|
| `consolidate.py` | Merges duplicate events that are really the same story. **Destructive.** | `py consolidate.py` (dry run) → `py consolidate.py --apply` |
| `cleanup.py` | Removes junk / grab-bag events. Only unambiguous junk — it will not delete legitimate popular stories. | `py cleanup.py` |
| `prune_cache.py` | DB housekeeping so `paksh.db` doesn't re-bloat. Run periodically. | `py prune_cache.py` |
| `recount_migrate.py` | Recomputes every bias bar to the current counting rules (distinct outlets per lean). | `py recount_migrate.py` (dry run) → `py recount_migrate.py --apply` |
| `audit.py` | Editorial audit report of the lean labels in `sources.py`; writes `audit.html`. | `py audit.py` |
| `calibrate.py` | Prints recommended clustering thresholds for the current data. Advisory — you then edit the numbers in `cluster.py` by hand. | `py calibrate.py` |
| `stats.py` | Prints corpus statistics (article / event counts, coverage). | `py stats.py` |

## Safe clean-rebuild order (from CLAUDE.md)

After destructive changes, run in this order:

```
back up paksh.db  →  py cleanup.py  →  py consolidate.py --apply
→  py recount_migrate.py --apply  →  py export_static.py  →  push
```

Remember: lean labels are **editorial** (assigned in `sources.py`) and the bias bar counts
**distinct outlets per lean** — never let any tool change those rules.
