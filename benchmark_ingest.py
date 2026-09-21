"""
benchmark_ingest.py - measure per-row insert_article() against database.ArticleWriter batching, on a scratch database.

    py benchmark_ingest.py [--dir D:\\Paksh_Data\\pipeline\\state] [--rows 600] [--batches 1,25,100,200,500,1000]

It never touches the real paksh.db: it builds a fresh scratch database under --dir (default: the configured data dir's
pipeline\\state, i.e. the SD card, because that is the medium being measured), fills it with rows sampled from real
recent articles (real title / summary sizes, urls made unique, ~10 % deliberate duplicates), and deletes the scratch
folder afterwards. For every mode it reports rows/s, wall time, commits, longest single transaction (~ how long the write
lock was held), CPU time, database size, and it VERIFIES equivalence against the per-row baseline: same returned ids and
None-for-duplicate sequence, same rows (every column except fetched_at), fetched_at present and non-decreasing.
"""
import argparse
import random
import shutil
import sqlite3
import statistics
import sys
import time
from pathlib import Path

import paksh_paths


def sample_rows(n, seed=5):
    """Real-shaped rows: sizes/text from recent real articles, urls unique per call, ~10 % repeated urls."""
    src = sqlite3.connect(f"file:{paksh_paths.db_path().as_posix()}?mode=ro", uri=True)
    real = src.execute("SELECT source, language, title, summary, image_url, published FROM articles ORDER BY id DESC LIMIT 3000").fetchall()
    src.close()
    rnd = random.Random(seed)
    rows, urls = [], []
    for i in range(n):
        s, lang, t, summ, img, pub = rnd.choice(real)
        if urls and rnd.random() < 0.10:
            url = rnd.choice(urls)                                  # duplicate url -> IntegrityError path
        else:
            url = f"https://bench.example/{seed}/{i}/{rnd.randrange(10**9)}"
            urls.append(url)
        rows.append((s, lang, t, url, summ, img, pub))
    return rows


def fresh_db(root: Path, name):
    import database
    d = root / name
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    database.DB_PATH = d / "bench.db"
    database._db_initialized = False
    database.get_connection().close()                                # the first connect creates the schema (init_db)
    return database, d


def dump(db_path):
    c = sqlite3.connect(db_path)
    rows = c.execute("SELECT id, source, language, title, url, summary, image_url, published, event_id FROM articles ORDER BY id").fetchall()
    fetched = [r[0] for r in c.execute("SELECT fetched_at FROM articles ORDER BY id")]
    size = Path(db_path).stat().st_size
    c.close()
    return rows, fetched, size


def run_mode(root, rows, batch):
    database, d = fresh_db(root, f"mode_{batch}")
    results, txn_times = [], []
    t0, c0 = time.perf_counter(), time.process_time()
    if batch == 0:                                                  # baseline: the existing per-row function
        for r in rows:
            results.append(database.insert_article(*r))
        commits = sum(1 for x in results if x is not None)
    else:
        w = database.ArticleWriter(batch_size=batch)
        orig = w.flush
        state = {"start": None}

        def timed_flush():
            if w._pending:
                a = time.perf_counter()
                orig()
                txn_times.append(time.perf_counter() - (state["start"] or a))
                state["start"] = None
            else:
                orig()
        w.flush = timed_flush
        for r in rows:
            if state["start"] is None:
                state["start"] = time.perf_counter()
            results.append(w.insert(*r))
        w.close()
        commits = w.commits
    wall, cpu = time.perf_counter() - t0, time.process_time() - c0
    dumped, fetched, size = dump(database.DB_PATH)
    return {"batch": batch, "wall_s": wall, "rows_per_s": len(rows) / wall, "commits": commits, "cpu_s": cpu, "db_kb": size // 1024,
            "max_txn_s": max(txn_times) if txn_times else None, "results": results, "rows": dumped, "fetched": fetched}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(paksh_paths.db_path().parent.parent / "pipeline" / "state"))
    ap.add_argument("--rows", type=int, default=600)
    ap.add_argument("--batches", default="1,25,100,200,500,1000")
    a = ap.parse_args()
    root = Path(a.dir) / "_bench_ingest"
    rows = sample_rows(a.rows)
    print(f"scratch dir: {root}   rows: {len(rows)} (unique urls {len({r[3] for r in rows})})")
    out = [run_mode(root, rows, 0)] + [run_mode(root, rows, int(b)) for b in a.batches.split(",")]
    base = out[0]
    print(f"\n{'mode':>10} {'rows/s':>8} {'wall s':>8} {'commits':>8} {'max txn s':>10} {'cpu s':>7} {'db KB':>7}  equivalent")
    ok_all = True
    for r in out:
        same = (r["results"] == base["results"] and r["rows"] == base["rows"] and all(x for x in r["fetched"])
                and r["fetched"] == sorted(r["fetched"]))
        ok_all &= same
        name = "per-row" if r["batch"] == 0 else f"batch {r['batch']}"
        mt = f"{r['max_txn_s']:.2f}" if r["max_txn_s"] is not None else "-"
        print(f"{name:>10} {r['rows_per_s']:>8.1f} {r['wall_s']:>8.1f} {r['commits']:>8} {mt:>10} {r['cpu_s']:>7.2f} {r['db_kb']:>7}  {same}")
    shutil.rmtree(root, ignore_errors=True)
    print("\nALL MODES EQUIVALENT TO PER-ROW" if ok_all else "\nMISMATCH - do not use")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
