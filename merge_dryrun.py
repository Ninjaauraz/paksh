"""
DRY RUN for the cross-cycle clustering merge.

Shows which NEW clusters (this cycle's unclustered articles) WOULD fold into a
RECENT existing event, and which would become brand-new events - and writes
NOTHING. Run it against a copy of paksh.db to tune PAKSH_XMERGE_SIM before we wire
the merge into the live pipeline.

    python merge_dryrun.py                 # uses your real embeddings (Ollama/Gemini)
    python merge_dryrun.py --sim 0.70      # try a stricter threshold
    python merge_dryrun.py --days 7        # widen the look-back window
    python merge_dryrun.py --lexical       # offline preview (English-only, rough)

Read carefully: a good merge continues the SAME story (e.g. a new batch of World
Cup articles -> the existing World Cup event). A bad merge collapses two DIFFERENT
stories. Raise --sim until the bad ones disappear; lower it if real continuations
are being missed.
"""
import argparse

import database
import cluster
from ingest import is_junk


def _dominant_lang(arts):
    langs = [a["language"] for a in arts]
    return max(set(langs), key=langs.count) if langs else "en"


def events_as_clusters(events, embedder):
    """Turn each recent event into a cluster-shaped dict (centroid + keywords + lang)
    so it can be compared against this cycle's new clusters."""
    out = []
    for e in events:
        arts = e["articles"]
        centroid = cluster.cluster_centroid(
            [cluster._text_of(a) for a in arts], embedder)
        if centroid is None:
            continue
        out.append({
            **e,
            "centroid": centroid,
            "keywords": cluster.merge_keywords(arts),
            "lang": _dominant_lang(arts),
        })
    return out


def main():
    ap = argparse.ArgumentParser(description="Dry-run the cross-cycle merge (no writes).")
    ap.add_argument("--days", type=int, default=cluster.MERGE_WINDOW_DAYS,
                    help="look-back window for existing events")
    ap.add_argument("--sim", type=float, default=cluster.XMERGE_SIM,
                    help="centroid similarity threshold to merge")
    ap.add_argument("--lexical", action="store_true",
                    help="offline English-only embedder (rough preview, no Ollama)")
    args = ap.parse_args()

    database.init_db()
    embedder = cluster.lexical_embedder if args.lexical else None

    arts = [a for a in database.get_unclustered_articles() if not is_junk(a.get("title", ""))]
    print("\n%d unclustered articles this cycle" % len(arts))
    if len(arts) < 2:
        print("Not enough new articles to cluster - run `python ingest.py` first.\n")
        return

    new = cluster.cluster_with_details(arts, embedder)
    print("%d new clusters formed" % len(new))

    events = database.get_recent_events_for_merge(days=args.days)
    print("%d existing events in the last %d days" % (len(events), args.days))
    if not events:
        print("No recent events to merge into - every new cluster would be a new event.\n")
        return
    evc = events_as_clusters(events, embedder)

    matches = cluster.match_clusters_to_events(new, evc, sim=args.sim)
    by_cluster = {id(m["cluster"]): m for m in matches}

    print("\n================ %d PROPOSED MERGES  (sim >= %.2f) ================\n"
          % (len(matches), args.sim))
    for m in sorted(matches, key=lambda x: -x["sim"]):
        c, e = m["cluster"], m["event"]
        print("[sim %.3f]  new cluster (%d outlets): \"%s\""
              % (m["sim"], c["source_count"], c["sample_title"][:64]))
        print("      folds into  -> event #%s: \"%s\"" % (e["event_id"], e["title"][:64]))
        print("      shared keywords: %s\n" % (sorted(m["shared"])[:8] or "(high-similarity match)"))

    new_events = [c for c in new
                  if id(c) not in by_cluster and c["source_count"] >= cluster.MIN_SOURCES]
    singles = [c for c in new
               if id(c) not in by_cluster and c["source_count"] < cluster.MIN_SOURCES]

    print("================ SUMMARY ================")
    print("  %3d clusters fold into existing events  (de-duplication)" % len(matches))
    print("  %3d clusters become NEW events          (2+ outlets, no match)" % len(new_events))
    print("  %3d singletons wait for next cycle       (1 outlet, no match)" % len(singles))
    print("\nDRY RUN - nothing was written. Tune --sim until the merges look right,\n"
          "then we flip this into the live pipeline.\n")


if __name__ == "__main__":
    main()