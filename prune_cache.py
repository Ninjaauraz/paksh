"""
prune_cache.py
--------------
Reclaim disk from the embedding CACHE. The `embeddings` table is a pure performance
cache (see cluster.cached_embedder): a vector missing from it is simply recomputed on
the next run, and clustering only ever looks back MERGE_WINDOW_DAYS (5) days -- so any
vector not touched in weeks is dead weight that will never be read again. Deleting it is
non-destructive: it costs, at worst, a one-time re-embed if an old text ever recurs.

It removes cache rows older than --days (default 30, i.e. 6x the merge window for safety),
then VACUUMs so the freed pages actually shrink paksh.db on disk.

Usage:
    py prune_cache.py                # DRY RUN: report what would go, change nothing
    py prune_cache.py --apply        # delete old cache rows + VACUUM
    py prune_cache.py --apply --days 45

VACUUM needs exclusive access and ~the DB's size in free disk. Stop live.py first, and
back up paksh.db (the project's standing habit) before --apply.
"""

import sys
from datetime import datetime, timedelta

from database import get_connection, init_db


def _arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main(apply: bool, days: int) -> None:
    init_db()                       # make sure idx_embeddings_created_at exists
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    conn = get_connection()

    total = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    old = conn.execute(
        "SELECT COUNT(*) FROM embeddings WHERE created_at IS NOT NULL AND created_at < ?",
        (cutoff,),
    ).fetchone()[0]
    null_dated = conn.execute(
        "SELECT COUNT(*) FROM embeddings WHERE created_at IS NULL"
    ).fetchone()[0]
    page = conn.execute("PRAGMA page_size").fetchone()[0]
    pages = conn.execute("PRAGMA page_count").fetchone()[0]
    size_mb = page * pages / 1e6

    print(f"DB size now:            {size_mb:,.0f} MB")
    print(f"Embedding cache rows:   {total:,}")
    print(f"  older than {days}d:      {old:,}   <- would delete")
    print(f"  undated (kept):       {null_dated:,}")

    if not apply:
        print("\nDRY RUN -- nothing deleted. Re-run with --apply to reclaim the space.")
        conn.close()
        return

    print(f"\nDeleting {old:,} cache rows older than {cutoff[:10]} ...")
    conn.execute(
        "DELETE FROM embeddings WHERE created_at IS NOT NULL AND created_at < ?",
        (cutoff,),
    )
    conn.commit()
    print("VACUUM (rewriting the file to reclaim pages; this takes a minute) ...")
    conn.execute("VACUUM")
    conn.close()

    conn = get_connection()
    pages2 = conn.execute("PRAGMA page_count").fetchone()[0]
    conn.close()
    print(f"Done. DB size now: {page * pages2 / 1e6:,.0f} MB "
          f"(reclaimed {(pages - pages2) * page / 1e6:,.0f} MB).")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv, days=int(_arg("--days", "30")))
