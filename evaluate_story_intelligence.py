"""
evaluate_story_intelligence.py - reproducible evaluation harness for story_intelligence.py.

Read-only: it opens the database (mode=ro), runs the pure engine in memory and writes nothing to the database.

    py evaluate_story_intelligence.py sample --n 150 --seed 7 --out eval_sample.json
        Stratified random sample of recent stories (by size), runs the engine, saves the sample + every judgement item.
    py evaluate_story_intelligence.py items  --sample eval_sample.json --kind derived --start 0 --count 25
        Prints compact review items (kind: derived | independent | uncertain | development | figure | story).
    py evaluate_story_intelligence.py score  --sample eval_sample.json --labels eval_labels.json
        Computes precision figures from a labels file {"<item_id>": "ok" | "wrong" | "unclear"}.

Ground truth here is INSPECTION of headline + excerpt (that is all Paksh stores - there is no article body), done by
whoever fills the labels file; it is not editorial verification of the underlying news. Unclear items are reported
separately and excluded from precision (never counted as correct).
"""
import argparse
import json
import random
import sqlite3
import time

import paksh_paths
import story_intelligence as si
from sources import OWNER_BY_SOURCE

SIZE_STRATA = [("2-3", 2, 3, 30), ("4-6", 4, 6, 40), ("7-12", 7, 12, 40), ("13+", 13, 10**6, 40)]   # target share of n=150


def _conn():
    c = sqlite3.connect(f"file:{paksh_paths.db_path().as_posix()}?mode=ro", uri=True, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def sample(n, seed, days, out, exclude=None):
    c = _conn()
    since = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - days * 86400))
    ids = [r[0] for r in c.execute("SELECT id FROM events WHERE is_demo=0 AND created_at>=?", (since,))]
    if exclude:                                        # hold-out mode: never reuse stories the engine was tuned on
        skip = set(json.loads(open(exclude, encoding="utf-8").read())["events"])
        ids = [i for i in ids if i not in skip]
    rows = si._load_rows(c, ids)
    rnd = random.Random(seed)
    chosen = []
    for name, lo, hi, share in SIZE_STRATA:
        pool = sorted(e for e, rs in rows.items() if lo <= len(rs) <= hi)
        k = max(1, round(n * share / 150))
        chosen += rnd.sample(pool, min(k, len(pool)))
    sub = {e: rows[e] for e in chosen}
    si._attach_vectors(sub)
    owner_of = lambda x: OWNER_BY_SOURCE.get(x, x)
    names = si._publisher_names()
    t0 = time.time()
    results = {e: si.analyze_story(rs, owner_of, names) for e, rs in sub.items()}
    secs = time.time() - t0
    items, titles = [], {}
    for e, res in results.items():
        titles.update({(e, a["id"]): a for a in res["articles"]})
    for e, res in results.items():
        by = {a["id"]: a for a in res["articles"]}
        for a in res["articles"]:
            kind = {"DERIVED": "derived", "ATTRIBUTED_REPETITION": "derived", "INDEPENDENT": "independent", "UNCERTAIN": "uncertain"}[a["role"]]
            items.append({"id": f"{kind}:{e}:{a['id']}", "kind": kind, "event_id": e, "article_id": a["id"]})
        for d in res["developments"]:
            items.append({"id": f"development:{e}:{d['dev_key']}", "kind": "development", "event_id": e, "dev_key": d["dev_key"]})
        for i, r in enumerate(res["relationships"]):
            if r[0] in ("UPDATES", "CONTRADICTS"):
                items.append({"id": f"figure:{e}:{r[0]}:{r[2]}:{r[4]}", "kind": "figure", "event_id": e, "rel": r[0], "src": r[2], "dst": r[4]})
    Path = __import__("pathlib").Path
    Path(out).write_text(json.dumps({"seed": seed, "days": days, "events": chosen, "engine_version": si.ENGINE_VERSION,
                                     "engine_seconds": round(secs, 2), "results": {str(e): r for e, r in results.items()},
                                     "items": items}, ensure_ascii=False, default=str), encoding="utf-8")
    tot = {k: 0 for k in si.CLASSES}
    for r in results.values():
        for k, v in r["stats"]["role_counts"].items():
            tot[k] += v
    print(f"sampled {len(chosen)} stories, {sum(len(r['articles']) for r in results.values())} articles; engine {secs:.2f}s "
          f"({secs / max(1, len(chosen)) * 1000:.1f} ms/story, 0 LLM calls); roles {tot}; items to inspect: {len(items)}")


def _short(s, n):
    s = " ".join(str(s or "").split())
    return s[:n] + ("…" if len(s) > n else "")


def items(sample_path, kind, start, count, width=110):
    d = json.loads(open(sample_path, encoding="utf-8").read())
    its = [i for i in d["items"] if i["kind"] == kind][start:start + count]
    c = _conn()
    for it in its:
        res = d["results"][str(it["event_id"])]
        by = {a["id"]: a for a in res["articles"]}
        ex = {r["id"]: r["summary"] for r in c.execute("SELECT id, summary FROM articles WHERE event_id=?", (it["event_id"],))}
        def line(aid):
            a = by[aid]
            e = _short(ex.get(aid), 60)
            return f"[{a['source'][:16]}|{(a['published'] or '')[:16]}] {_short(a['title'], width)}" + (f" ::{e}" if e and e not in a["title"] else "")
        if kind in ("derived", "independent", "uncertain"):
            a = by[it["article_id"]]
            print(f"# {it['id']}  {a['role']}/{a['reason']} c={a['confidence']}")
            print("   ART", line(a["id"]))
            if a["target"]:
                print("   SRC", line(a["target"]))
            elif a["external"]:
                print("   EXT", a["external"])
            elif kind == "independent":
                firsts = [x for x in res["articles"] if x["order_time"] < a["order_time"]][:2]
                for f in firsts:
                    print("   PRE", line(f["id"]))
        elif kind == "development":
            dv = next(x for x in res["developments"] if x["dev_key"] == it["dev_key"])
            print(f"# {it['id']}  {dv['type']} c={dv['confidence']} owners={dv['corroborating_owners']}")
            print("   TRG", line(dv["trigger_article_id"]))
            for f in [x for x in res["articles"] if x["order_time"] < by[dv["trigger_article_id"]]["order_time"]][:2]:
                print("   PRE", line(f["id"]))
        elif kind == "figure":
            print(f"# {it['id']}")
            print("   A", line(int(it["src"].split(":")[0])), " / claim", it["src"].split(":")[1])
            print("   B", line(int(it["dst"].split(":")[0])))


def score(sample_path, labels_path):
    d = json.loads(open(sample_path, encoding="utf-8").read())
    lab = json.loads(open(labels_path, encoding="utf-8").read())
    out = {}
    for kind in ("derived", "independent", "uncertain", "development", "figure"):
        ks = [i["id"] for i in d["items"] if i["kind"] == kind and i["id"] in lab]
        ok = sum(1 for k in ks if lab[k] == "ok")
        wrong = sum(1 for k in ks if lab[k] == "wrong")
        unclear = len(ks) - ok - wrong
        out[kind] = {"labelled": len(ks), "ok": ok, "wrong": wrong, "unclear": unclear,
                     "precision_excl_unclear": round(ok / (ok + wrong), 3) if ok + wrong else None,
                     "population": sum(1 for i in d["items"] if i["kind"] == kind)}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("sample")
    a.add_argument("--n", type=int, default=150)
    a.add_argument("--seed", type=int, default=7)
    a.add_argument("--days", type=int, default=30)
    a.add_argument("--out", default="eval_sample.json")
    a.add_argument("--exclude-sample", default=None, help="a previous sample file whose stories must not be re-drawn (hold-out)")
    b = sp.add_parser("items")
    b.add_argument("--sample", required=True)
    b.add_argument("--kind", required=True)
    b.add_argument("--start", type=int, default=0)
    b.add_argument("--count", type=int, default=25)
    c = sp.add_parser("score")
    c.add_argument("--sample", required=True)
    c.add_argument("--labels", required=True)
    args = ap.parse_args()
    if args.cmd == "sample":
        sample(args.n, args.seed, args.days, args.out, args.exclude_sample)
    elif args.cmd == "items":
        items(args.sample, args.kind, args.start, args.count)
    else:
        score(args.sample, args.labels)
