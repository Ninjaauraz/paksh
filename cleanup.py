"""
cleanup.py - remove ONLY unambiguous junk events from the published catalogue.

Deletes an event only when it is clearly not a single real story:

  * GRAB-BAGS   - more distinct outlets than any real story has (> --max-outlets).
  * DUMPS       - an implausible article pile, usually one outlet filing hundreds
                  of items that clustered together (> --max-articles).
  * GENERIC     - placeholder / refusal headlines ("No new coverage provided for
                  analysis", "Multiple outlets cover diverse events").
  * --ids       - specific event ids you want gone after eyeballing them.

IMPORTANT: this does NOT try to guess "diffuse" events from keyword spread. A
popular story covered by 20+ outlets across Hindi and English naturally has a huge
keyword union, so that test deleted real headline events (fires, match results,
resignations). Keyword spread is intentionally NOT used here. For a polluted event
with an ordinary outlet count (e.g. an old over-merged one), eyeball it and pass
its id with --ids.

    python cleanup.py                       # DRY RUN: list what would be removed
    python cleanup.py --apply               # delete them
    python cleanup.py --ids 2343,3522       # also/only remove these specific ids
    python cleanup.py --apply --recycle     # also free their articles to re-cluster

BACK UP paksh.db before running with --apply.
"""
import argparse

import database
import analyze


def _scan(max_outlets, max_articles, manual_ids):
    flagged = []
    for eid in database.get_event_ids():
        e = database.get_event(eid)
        if not e:
            continue
        srcs = e.get("sources", []) or []
        outlets = len({s["source"] for s in srcs})
        articles = len(srcs)
        title = e.get("title", "") or ""
        reasons = []
        if eid in manual_ids:
            reasons.append("manual")
        if outlets > max_outlets:
            reasons.append("%d outlets" % outlets)
        if articles > max_articles:
            reasons.append("%d articles" % articles)
        if analyze._looks_generic(title):
            reasons.append("generic headline")
        if reasons:
            flagged.append({"id": eid, "outlets": outlets, "articles": articles,
                            "title": title, "why": ", ".join(reasons)})
    return flagged


def main():
    ap = argparse.ArgumentParser(description="Remove grab-bag / dump / generic events from the site.")
    ap.add_argument("--apply", action="store_true", help="delete the flagged events (default: dry run)")
    ap.add_argument("--recycle", action="store_true",
                    help="also free deleted events' articles (event_id -> NULL) to re-cluster")
    ap.add_argument("--ids", default="", help="comma-separated event ids to also remove")
    ap.add_argument("--max-outlets", type=int, default=60)
    ap.add_argument("--max-articles", type=int, default=300)
    args = ap.parse_args()

    manual_ids = {int(x) for x in args.ids.replace(",", " ").split() if x.strip().isdigit()}

    database.init_db()
    flagged = _scan(args.max_outlets, args.max_articles, manual_ids)
    flagged.sort(key=lambda f: -f["articles"])

    print("\n%d event(s) flagged for removal\n" % len(flagged))
    for f in flagged:
        print("  #%-6s %3d outlets / %5d articles  [%s]" % (f["id"], f["outlets"], f["articles"], f["why"]))
        print("           %s" % f["title"][:78])

    if not flagged:
        print("Nothing to clean.\n")
        return

    if args.apply:
        for f in flagged:
            if args.recycle:
                database.release_event_articles(f["id"])
            database.delete_event(f["id"])
        print("\nDELETED %d event(s)%s. Next: python export_static.py\n"
              % (len(flagged), " and freed their articles" if args.recycle else ""))
    else:
        print("\nDRY RUN - nothing deleted. Back up paksh.db, then re-run with --apply.\n")


if __name__ == "__main__":
    main()