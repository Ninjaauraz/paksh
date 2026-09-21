"""
audit_source_utilization.py - READ-ONLY measurements behind docs/SOURCE_UTILIZATION_AUDIT.md.

Opens paksh.db with mode=ro (it can never write), so it is safe to run while live.py / the nightly job are running.
Use it before and after a change to see whether the pipeline uses more of the registry:

    py audit_source_utilization.py                 # all three sections
    py audit_source_utilization.py --stories 500   # size of the 'last N published stories' sample
    py audit_source_utilization.py --db path.db    # audit a copy / backup instead

  1. utilization  - registry outlets vs outlets that actually produced articles (7/30/90 days), by class
  2. admission    - per outlet class and registry position: how many recent articles ever reached clustering
                    (had an embedding) and how many ended up in a story. The old window starved early outlets.
  3. stories      - diversity of the N newest published stories: publishers/story, concentration, India share,
                    sides covered, World-vs-India split
  4. gate         - how many analysed stories the completeness gate hides, by publisher count and region, and the
                    World share created vs published (the retry-label fix should drive World hidden toward 0)
"""
import argparse
import collections as C
import json
import sqlite3
import statistics as st
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
import paksh_paths                        # noqa: E402
import sources as S                       # noqa: E402
import source_selection as SS             # noqa: E402

S._load_verified_registry()
CUR = {s["name"]: s for s in S.SOURCES}
VER = S.VERIFIED_BY_NAME
INFO = SS.SourceInfo()


def klass(name):
    if name in CUR:
        return "curated-intl" if CUR[name].get("region") == "International" else "curated-india"
    if name in VER:
        return "verified-india(vote)" if VER[name].get("vote") else "verified-foreign"
    return "unrated-domain"


def connect(path):
    c = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True, timeout=60)
    c.execute("PRAGMA query_only=1")
    c.row_factory = sqlite3.Row
    return c


def section_utilization(c):
    now = datetime.utcnow()
    cut = {d: (now - timedelta(days=d)).isoformat() for d in (7, 30, 90)}
    rows = c.execute("SELECT source, COUNT(*) n, SUM(fetched_at>=?) d7, SUM(fetched_at>=?) d30, SUM(fetched_at>=?) d90 "
                     "FROM articles GROUP BY source", (cut[7], cut[30], cut[90])).fetchall()
    reg = {"curated-india": sum(1 for s in CUR.values() if s.get("region") != "International"),
           "curated-intl": sum(1 for s in CUR.values() if s.get("region") == "International"),
           "verified-india(vote)": sum(1 for v in VER.values() if v.get("vote")),
           "verified-foreign": sum(1 for v in VER.values() if not v.get("vote")), "unrated-domain": "-"}
    T = C.defaultdict(C.Counter)
    for r in rows:
        k = klass(r["source"])
        T[k]["ever"] += 1
        T[k]["art"] += r["n"]
        for d in (7, 30, 90):
            if r[f"d{d}"]:
                T[k][f"s{d}"] += 1
                T[k][f"a{d}"] += r[f"d{d}"]
    print("\n== 1. UTILIZATION: registry outlets vs outlets that produced articles ==")
    print(f"{'class':<22}{'registry':>9}{'ever':>7}{'90d':>7}{'30d':>7}{'7d':>6}{'articles':>10}{'art 7d':>9}")
    for k in ("curated-india", "curated-intl", "verified-india(vote)", "verified-foreign", "unrated-domain"):
        t = T[k]
        print(f"{k:<22}{str(reg[k]):>9}{t['ever']:>7}{t['s90']:>7}{t['s30']:>7}{t['s7']:>6}{t['art']:>10}{t['a7']:>9}")
    seen = {r["source"] for r in rows}
    print(f"verified-registry outlets that never produced an article: {sum(1 for n in VER if n not in seen)} of {len(VER)}")


def section_admission(c, since):
    import cluster
    rows = c.execute("SELECT id, source, title, summary, event_id FROM articles WHERE fetched_at>=? AND length(published)>8", (since,)).fetchall()
    keys = [cluster._emb_key(cluster._text_of(dict(r))) for r in rows]
    have = set()
    for i in range(0, len(keys), 900):
        ch = keys[i:i + 900]
        for r in c.execute("SELECT key FROM embeddings WHERE key IN (%s)" % ",".join("?" * len(ch)), ch):
            have.add(r["key"])
    order = {s["name"]: i for i, s in enumerate(S.SOURCES)}
    per = C.defaultdict(lambda: [0, 0, 0])
    for r, k in zip(rows, keys):
        p = per[r["source"]]
        p[0] += 1
        p[1] += k in have
        p[2] += r["event_id"] is not None
    print(f"\n== 2. ADMISSION to clustering, RSS articles fetched since {since[:10]} ({len(rows)}) ==")
    kl = C.defaultdict(lambda: [0, 0, 0])
    for s, v in per.items():
        for i in range(3):
            kl[klass(s)][i] += v[i]
    for k, v in kl.items():
        print(f"  {k:<22} articles {v[0]:>6}   reached clustering {100*v[1]/v[0]:5.1f}%   in a story {100*v[2]/v[0]:5.1f}%")
    print("  by position in the curated registry (= ingest order; the old window favoured the LAST outlets):")
    pos = sorted(((order[s], v) for s, v in per.items() if s in order), key=lambda x: x[0])
    for lo, hi in ((0, 20), (20, 40), (40, 60), (60, 80), (80, 100), (100, 124)):
        sel = [v for p, v in pos if lo <= p < hi]
        n = sum(v[0] for v in sel)
        if n:
            print(f"    registry #{lo:>3}-{hi-1:<3} articles {n:>6}   reached clustering {100*sum(v[1] for v in sel)/n:5.1f}%   in a story {100*sum(v[2] for v in sel)/n:5.1f}%")


def section_stories(c, n_stories):
    out = []
    for r in c.execute("SELECT id, created_at, analysis_json FROM events WHERE COALESCE(is_demo,0)=0 ORDER BY created_at DESC"):
        aj = json.loads(r["analysis_json"])
        cov = aj.get("coverage") or {}
        voting = sum((cov.get(s) or {}).get("count", 0) for s in ("left", "center", "right"))
        if voting < 2 or aj.get("content_complete") is False:       # the same rule as database.get_all_events()
            continue
        names = sorted({s["source"] for s in aj.get("sources") or []})
        out.append({"names": names, "owners": len({S.OWNER_BY_SOURCE.get(n, n) for n in names}), "region": aj.get("region"),
                    "leans": {k: (cov.get(k) or {}).get("count", 0) for k in ("left", "center", "right")}, "at": r["created_at"]})
        if len(out) >= n_stories:
            break
    N = len(out)
    print(f"\n== 3. STORIES: the {N} newest published ({out[-1]['at'][:10]} .. {out[0]['at'][:10]}) ==")
    pubs = [len(e["names"]) for e in out]
    inc = C.Counter(n for e in out for n in e["names"])
    tot = sum(inc.values())
    print(f"  publishers/story mean {st.mean(pubs):.2f}, median {st.median(pubs):g}; exactly 2 publishers: {100*sum(1 for p in pubs if p == 2)/N:.0f}%; >=5: {100*sum(1 for p in pubs if p >= 5)/N:.0f}%")
    print(f"  distinct publishers used: {len(inc)}; top10 {100*sum(v for _, v in inc.most_common(10))/tot:.1f}%  top25 {100*sum(v for _, v in inc.most_common(25))/tot:.1f}%  top50 {100*sum(v for _, v in inc.most_common(50))/tot:.1f}% of publisher slots")
    reg = C.Counter(INFO.region(n) or "unrated" for e in out for n in e["names"])
    rt = sum(reg.values())
    print("  home region of publisher slots:", {k: f"{100*v/rt:.1f}%" for k, v in reg.most_common()})
    sides = C.Counter(sum(1 for v in e["leans"].values() if v) for e in out)
    print(f"  sides covered per story: {dict(sorted(sides.items()))}; voting owners/story {st.mean(sum(e['leans'].values()) for e in out):.2f}")
    print(f"  India vs World stories: {dict(C.Counter(e['region'] for e in out))}")
    print("  most frequent publishers:", ", ".join(f"{n} {100*v/N:.0f}%" for n, v in inc.most_common(8)))


def section_gate(c, days):
    def has(v):
        return (isinstance(v, list) and any(str(x).strip() for x in v)) or (isinstance(v, str) and v.strip() != "")
    rows = []
    for r in c.execute("SELECT analysis_json FROM events WHERE COALESCE(is_demo,0)=0 AND created_at>=date('now', ?)", (f"-{days} day",)):
        aj = json.loads(r["analysis_json"])
        cov = aj.get("coverage") or {}
        if sum((cov.get(s) or {}).get("count", 0) for s in ("left", "center", "right")) < 2 or aj.get("summary_method") != "llm":
            continue
        pubs = len({s["source"] for s in aj.get("sources") or []})
        covered = [s for s in ("left", "center", "right") if (cov.get(s) or {}).get("count", 0) >= 1]
        rows.append({"hidden": aj.get("content_complete") is False, "pubs": pubs, "region": aj.get("region"), "sides": len(covered)})
    n = len(rows)
    if not n:
        print()
        print("== 4. GATE: no LLM-analysed stories in the window")
        return
    hid = [r for r in rows if r["hidden"]]
    print()
    print(f"== 4. COMPLETENESS GATE: LLM-analysed stories (>=2 voting outlets) created in the last {days} days: {n} ==")
    print(f"  hidden: {len(hid)} ({100*len(hid)/n:.1f}%)   mean publishers: published {st.mean(r['pubs'] for r in rows if not r['hidden']):.2f} | hidden {st.mean(r['pubs'] for r in hid) if hid else 0:.2f}")
    for lo, hi in ((2, 2), (3, 3), (4, 5), (6, 8), (9, 12), (13, 999)):
        x = [r for r in rows if lo <= r["pubs"] <= hi]
        if x:
            print(f"    {lo:>2}-{hi:<3} publishers: {len(x):>5} stories, hidden {100*sum(r['hidden'] for r in x)/len(x):5.1f}%")
    for reg in ("India", "World"):
        x = [r for r in rows if r["region"] == reg]
        if x:
            print(f"  region {reg:<5}: {len(x):>5} stories, hidden {100*sum(r['hidden'] for r in x)/len(x):5.1f}%")
    pub = [r for r in rows if not r["hidden"]]
    print(f"  World share: created {100*sum(1 for r in rows if r['region']=='World')/n:.1f}% -> published {100*sum(1 for r in pub if r['region']=='World')/max(1,len(pub)):.1f}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(paksh_paths.db_path()))
    ap.add_argument("--stories", type=int, default=500)
    ap.add_argument("--since", default=None, help="admission window start (ISO date); default: 7 days ago")
    ap.add_argument("--gate-days", type=int, default=14, help="days of stories for the completeness-gate section")
    a = ap.parse_args()
    conn = connect(a.db)
    section_utilization(conn)
    section_admission(conn, a.since or (datetime.utcnow() - timedelta(days=7)).isoformat())
    section_stories(conn, a.stories)
    section_gate(conn, a.gate_days)
