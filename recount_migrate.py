"""
recount_migrate.py - bring EXISTING events' bias bars up to the CURRENT rules.

When the rules that drive the bias bar change - e.g. moving foreign wires to the
non-voting "international" tier, or relabelling an outlet's lean - events already
in paksh.db keep their OLD bars until they are re-derived. This script walks every
event and recomputes its coverage / bias bar / sources straight from its member
articles using today's lean_of(), while PRESERVING the written brief and leaving
created_at untouched (so the feed order doesn't move). It makes NO model calls.

(That is complementary to backfill.py, which upgrades extractive events to real
LLM briefs. This one only re-counts; it never rewrites a summary.)

    python recount_migrate.py                  # DRY RUN: report what would change
    python recount_migrate.py --apply          # recompute every event's bar
    python recount_migrate.py --days 30        # limit to recent events
    python recount_migrate.py --apply --prune  # delete events that drop below the
                                               #   2-rated-outlet gate after recount

BACK UP paksh.db before running with --apply.
"""
import argparse

import database
import analyze

_PRESERVE = ("title", "summary", "summary_points", "title_hi", "summary_hi",
             "summary_points_hi", "framing", "framing_hi", "topic", "region",
             "summary_method")


def _counts(a):
    lc = database.lean_counts_from(a)
    intl = a.get("coverage", {}).get("international", {}).get("count", 0)
    return lc, sum(lc.values()), intl


def main():
    ap = argparse.ArgumentParser(description="Recount existing events to current bias rules.")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--prune", action="store_true",
                    help="delete events that fall below the 2-rated-outlet gate after recount")
    ap.add_argument("--days", type=int, default=None, help="limit to events from the last N days")
    ap.add_argument("--redetect-region", action="store_true",
                    help="DIAGNOSTIC ONLY, DO NOT USE WITH --apply: re-derives each event's "
                         "region from _guess_region()'s keyword fallback instead of the region "
                         "the LLM actually assigned at analysis time. That fallback is far "
                         "weaker than a live classification (verified: it wrongly reclassifies "
                         "thousands of genuinely-foreign stories as India) and exists only to "
                         "cover the rare case a live LLM call omits the field - it was never "
                         "meant to re-judge an already-analysed corpus. For the real "
                         "international-voting regression check, do NOT pass this flag: the "
                         "default preserves each event's original (LLM-decided) region and only "
                         "recomputes voting eligibility against it, which is the actual, safe "
                         "test of the new rule in isolation.")
    args = ap.parse_args()

    database.init_db()
    ids = database.get_event_ids(days=args.days)
    print("\n%d event(s) to scan%s"
          % (len(ids), (" (last %d days)" % args.days) if args.days else " (all)"))

    preserve = tuple(k for k in _PRESERVE if not (args.redetect_region and k == "region"))

    scanned = changed = below = pruned = shown = region_flipped = 0
    for eid in ids:
        old = database.get_event(eid)
        if not old:
            continue
        rows = database.get_event_articles(eid)
        if not rows:
            continue
        scanned += 1
        old_lc, old_sum, old_intl = _counts(old)
        old_region = old.get("region")

        raw = {k: old.get(k) for k in preserve}
        new = analyze.postprocess(raw, rows)              # arithmetic recount, brief preserved
        new_lc, new_sum, new_intl = _counts(new)
        new_region = new.get("region")

        bar_changed = (new_lc != old_lc) or (new_intl != old_intl)
        region_changed = args.redetect_region and (new_region != old_region)
        if bar_changed:
            changed += 1
        if region_changed:
            region_flipped += 1
        if new_sum < 2:
            below += 1

        if (bar_changed or region_changed) and shown < 15:
            shown += 1
            flag = "   [< 2 rated -> below gate]" if new_sum < 2 else ""
            reg = ("   region: %s -> %s" % (old_region, new_region)) if region_changed else ""
            print("  #%s %s" % (eid, (old.get("title") or "")[:48]))
            print("     L/C/R %s +intl%d  ->  %s +intl%d%s%s"
                  % (dict(old_lc), old_intl, dict(new_lc), new_intl, flag, reg))

        if args.apply:
            if args.prune and new_sum < 2:
                database.delete_event(eid)
                pruned += 1
            else:
                database.update_event(eid, new, bump_created=False)

    print("\n" + "=" * 48)
    print("  scanned ............ %d" % scanned)
    print("  bias bars changed .. %d" % changed)
    if args.redetect_region:
        print("  region reclassified  %d" % region_flipped)
    print("  below 2-rated gate . %d%s"
          % (below, ("  (use --prune to delete)" if not args.prune else "  -> pruned %d" % pruned)))
    if args.apply:
        print("\nAPPLIED. Briefs + created_at preserved. Next: python export_static.py\n")
    else:
        print("\nDRY RUN - nothing written. Back up paksh.db, then re-run with --apply.\n")


if __name__ == "__main__":
    main()