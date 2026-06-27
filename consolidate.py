"""
ONE-TIME consolidation of DUPLICATE events already sitting in paksh.db.

The cross-cycle merge (in analyze.py) stops NEW fragmentation, but it does not
touch the duplicate events created BEFORE it was switched on - e.g. several
separate 'Venezuela earthquake', 'India vs Ireland T20I', or 'Muharram procession'
events. This script finds those, groups the fragments of one story together, and
fuses each group into a single event:

  * the richest fragment SURVIVES (a real LLM brief beats an extractive one, then
    most rated outlets, then most recent),
  * every other fragment's articles are reassigned to the survivor,
  * the survivor is recounted (coverage / bias bar / sources rebuilt, made recent),
  * the now-empty duplicate event rows are deleted.

DRY RUN BY DEFAULT - it prints what it WOULD merge and writes NOTHING.
Add --apply to actually perform the merges, and BACK UP paksh.db first:

    copy paksh.db paksh.db.bak
    python consolidate.py                 # preview only (no writes)
    python consolidate.py --days 7        # widen the look-back window
    python consolidate.py --sim 0.70      # stricter (fewer, safer merges)
    python consolidate.py --apply         # perform the merges shown above
"""
import argparse

import database
import cluster
import analyze


def _dominant_lang(arts):
    langs = [a["language"] for a in arts]
    return max(set(langs), key=langs.count) if langs else "en"


def _as_clusters(events):
    """Give each event a centroid + keyword set + language for matching."""
    out = []
    for e in events:
        centroid = cluster.cluster_centroid([cluster._text_of(a) for a in e["articles"]])
        if centroid is None:
            continue
        out.append({**e, "centroid": centroid,
                    "keywords": cluster.merge_keywords(e["articles"]),
                    "lang": _dominant_lang(e["articles"])})
    return out


def _pick_survivor(group):
    """Richest fragment wins: LLM brief > extractive, then rated breadth, then recency."""
    return max(group, key=lambda e: (e.get("summary_method") == "llm",
                                     e.get("source_count", 0),
                                     e.get("created_at", "")))


def main():
    ap = argparse.ArgumentParser(description="Fuse duplicate events (dry-run unless --apply).")
    ap.add_argument("--days", type=int, default=max(7, cluster.MERGE_WINDOW_DAYS),
                    help="look-back window of events to consider")
    ap.add_argument("--sim", type=float, default=cluster.XMERGE_SIM,
                    help="centroid similarity threshold to treat two events as one")
    ap.add_argument("--apply", action="store_true",
                    help="actually perform the merges (default is a dry run)")
    args = ap.parse_args()

    database.init_db()
    events = database.get_recent_events_for_merge(days=args.days, limit=1500)
    print("\n%d recent events in the last %d days" % (len(events), args.days))
    if len(events) < 2:
        print("Nothing to consolidate.\n")
        return

    evc = _as_clusters(events)
    groups = cluster.find_duplicate_event_groups(evc, sim=args.sim)
    groups.sort(key=len, reverse=True)
    absorbed = sum(len(g) - 1 for g in groups)

    print("%d duplicate group(s) found; %d event(s) would be absorbed.\n"
          % (len(groups), absorbed))
    for g in groups:
        surv = _pick_survivor(g)
        others = [e for e in g if e is not surv]
        tag = "LLM" if surv.get("summary_method") == "llm" else "ext"
        print("SURVIVOR #%s  [%d src, %s]  \"%s\""
              % (surv["event_id"], surv.get("source_count", 0), tag, surv["title"][:64]))
        for e in others:
            shared = sorted(surv["keywords"] & e["keywords"])[:6]
            print("    <- #%s  \"%s\"   shared: %s"
                  % (e["event_id"], e["title"][:58], shared or "(cross-lingual)"))
        print()

        if args.apply:
            for e in others:
                ids = [r["id"] for r in database.get_event_articles(e["event_id"])]
                database.assign_articles_to_event(ids, surv["event_id"])
                database.delete_event(e["event_id"])
            analyze.recount_event(surv["event_id"])

    if args.apply:
        print("APPLIED: fused %d duplicate(s) into %d survivor(s).  Next: python export_static.py\n"
              % (absorbed, len(groups)))
    else:
        print("DRY RUN - nothing written.  Back up paksh.db, then re-run with --apply.\n")


if __name__ == "__main__":
    main()