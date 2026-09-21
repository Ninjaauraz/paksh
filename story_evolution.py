"""
story_evolution.py - Intelligence Program Phase 14: an INTERNAL, auditable "Story Evolution" object per story.
No UI, no publication, no new tables: it assembles what Story Intelligence already derives (recomputed on demand with the current engine, so
it can never disagree with the engine version in use) plus provenance (original URL, recovered publisher URL, evidence source).

    py story_evolution.py --event 22148            # readable summary
    py story_evolution.py --event 22148 --json     # the full object
    py story_evolution.py --sample 12 --seed 3     # a random sample of recent stories, readable

It answers, with evidence pointers and stated limits:
  * What was the earliest report in Paksh's corpus (and on what time basis)?      -> first_report
  * What information appeared later?                                             -> later_information (articles that add information)
  * Which reports were independent / which repeated earlier material?            -> independent_reports / repeated_reports
  * Which figures changed or disagree?                                           -> figure_changes
  * Which developments were newly observed?                                      -> developments (INTERNAL, low confidence)
  * Which relationships are uncertain?                                           -> uncertain
  * What evidence supports each item?                                            -> every item carries article ids + provenance
Times: `published_at` (the publisher's claim, raw), `first_seen_at` (when Paksh fetched it), `order_time` + `order_basis` (what the
ordering used), `event_time` is ALWAYS null (never inferred). Nothing here says anything is true.
"""
import json
import sys

import story_intelligence as si

RELIABILITY = {
    "reporting_events": "measured ~98% (repeats), attribution 0 wrong of 14, independence conservative (abstains on ~1/3)",
    "adds_information": "measured accuracy 0.80, precision 0.82 (n=108, one rater)",
    "figure_changes": "measured precision 0.875 (n=40)",
    "developments": "INTERNAL ONLY: measured precision 0.47 (n=45); 0.57 when >=2 publishers report it",
}


# What a claim group is allowed to say. It records who reported a figure and how it was attributed; it never says the figure is true.
CLAIM_LANGUAGE = {
    "SINGLE_REPORTING_EVENT": "reported in one reporting event (every article shares the same origin as far as Paksh can tell)",
    "MULTIPLE_REPORTING_EVENTS": "reported in more than one reporting event; this is not confirmation - the reports may share an unseen source",
}


def build_claim_graph(res, ref):
    """On-demand claim view over one story's analysis: one node per (measure, value) with its supporting articles, reporting events, publishers and
    HOW each report attributes it; edges = the engine's UPDATES / CONTRADICTS. Only person-count tallies are edged (see story_intelligence)."""
    A = {a["id"]: a for a in res["articles"]}
    groups = {}
    for c in res["claims"]:
        groups.setdefault((c["key"], c["value"]), []).append(c)
    nodes = []
    for (key, value), cs in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        arts = sorted({c["article_id"] for c in cs}, key=lambda i: (A[i]["order_time"], i))
        roots = sorted({c["reporting_event_root"] for c in cs}, key=str)
        by_att = {}
        for c in cs:
            by_att.setdefault(c["attribution"], []).append(c["article_id"])
        nodes.append({
            "measure": key, "value": value,
            "articles": [ref(A[i]) for i in arts[:6]], "article_count": len(arts),
            "reporting_events": len(roots), "publishers": sorted({A[i]["owner"] for i in arts}),
            "attribution": {k: sorted(set(v)) for k, v in sorted(by_att.items())},
            "first_reported_order_time": A[arts[0]]["order_time"],
            "reading": CLAIM_LANGUAGE["MULTIPLE_REPORTING_EVENTS" if len(roots) > 1 else "SINGLE_REPORTING_EVENT"],
            "unattributed_only": set(by_att) == {"PUBLISHER_ASSERTION"},
        })
    edges = []
    for r in res["relationships"]:
        if r[0] in ("UPDATES", "CONTRADICTS"):
            ev = r[6]
            edges.append({"kind": r[0], "measure": ev["key"], "from_value": ev["earlier"]["value"], "to_value": ev["later"]["value"], "confidence": r[5]})
    return {"nodes": nodes, "edges": edges,
            "note": "a node records who reported a figure and how it was attributed; no node is marked confirmed, and PUBLISHER_ASSERTION means the text names no source"}


def _rows_for(conn, event_id):
    rows = si._load_rows(conn, [event_id]).get(event_id, [])
    if rows:
        try:
            si._attach_vectors({event_id: rows})
        except Exception:
            pass
    return rows


def build_story_evolution(conn, event_id, owner_of=None, evidence=None, publisher_urls=None):
    """-> dict (see module docstring). Never raises for a story with < 2 articles: returns {'available': False, ...}."""
    if owner_of is None:
        from sources import OWNER_BY_SOURCE
        owner_of = lambda n: OWNER_BY_SOURCE.get(n, n)
    rows = _rows_for(conn, event_id)
    ev_row = conn.execute("SELECT id, title FROM events WHERE id=?", (event_id,)).fetchone()
    if not ev_row or len(rows) < 2:
        return {"available": False, "event_id": event_id, "reason": "story not found or fewer than 2 articles"}
    if evidence is None:
        import evidence_retrieval as er
        evidence = {}
        for r in rows:
            t = er.usable_text(er.cache_get(conn, r["id"]))
            if t:
                evidence[r["id"]] = t
    if publisher_urls is None:
        import publisher_url as pu
        publisher_urls = pu.lookup(conn, [r["id"] for r in rows if (r.get("url") or "").startswith(pu.WRAPPER_PREFIX)])
    res = si.analyze_story(rows, owner_of, si._publisher_names(), evidence=evidence)
    urls = {r["id"]: r.get("url") for r in rows}
    A = {a["id"]: a for a in res["articles"]}

    def ref(a):
        aid = a["id"]
        return {"article_id": aid, "publisher": a["source"], "owner": a["owner"], "headline": a["title"],
                "published_at": a["published"], "first_seen_at": a["fetched_at"], "order_time": a["order_time"], "order_basis": a["order_basis"],
                "event_time": None, "original_url": urls.get(aid), "publisher_url": publisher_urls.get(aid),
                "evidence_source": a.get("evidence_source", "METADATA")}

    order = [a["id"] for a in res["articles"]]
    first = A[order[0]]
    weak = first["order_basis"] != "published"
    first_report = {**ref(first), "role": first["role"], "reason": first["reason"],
                    "note": "earliest in Paksh's corpus by " + ("its publish time" if not weak else "a weaker basis (" + first["order_basis"] + ")")
                            + "; not necessarily the first report anywhere"}
    independent = [{**ref(a), "reason": a["reason"], "confidence": a["confidence"], "adds": a["adds"]}
                   for a in res["articles"] if a["role"] == si.INDEPENDENT]
    later = [{**ref(a), "role": a["role"], "reason": a["reason"], "max_similarity_to_earlier": a["adds"]["max_similarity_to_earlier"],
              "new_figures": a["adds"]["figures"], "basis": a["adds"]["basis"]}
             for a in res["articles"] if a["adds"]["adds_information"]]
    repeated = {}
    for a in res["articles"]:
        if a["role"] in (si.DERIVED, si.ATTRIBUTED_REPETITION) and a["reason"] != "SAME_OWNER":
            key = a["target"] if a["target"] is not None else "external:" + str(a["external"])
            repeated.setdefault(str(key), []).append({"article_id": a["id"], "publisher": a["source"], "reason": a["reason"], "confidence": a["confidence"],
                                                      "evidence_source": a.get("evidence_source", "METADATA")})
    same_publisher = [a["id"] for a in res["articles"] if a["reason"] == "SAME_OWNER"]
    uncertain = {}
    for a in res["articles"]:
        if a["role"] == si.UNCERTAIN:
            uncertain.setdefault(a["reason"], []).append(a["id"])
    developments = [{"type": d["type"], "trigger": ref(A[d["trigger_article_id"]]), "description": d["description"], "confidence": d["confidence"],
                     "corroborating_publishers": d["corroborating_owners"], "reliability": "internal_low_confidence" if d["type"] != "FIGURE_UPDATE" else "see figure_changes"}
                    for d in res["developments"] if d["type"] != "FIGURE_UPDATE"]
    figures = []
    for r in res["relationships"]:
        if r[0] in ("UPDATES", "CONTRADICTS"):
            ev = r[6]
            figures.append({"kind": r[0], "measure": ev["key"], "earlier": ev["earlier"], "later": ev["later"], "confidence": r[5],
                            "order_ambiguous": ev.get("order_ambiguous"), "note": ev.get("note"),
                            "articles": [ref(A[i]) for i in (ev["earlier"]["article_ids"][:1] + ev["later"]["article_ids"][:1])]})
    timeline = []
    for a in res["articles"]:
        timeline.append({"kind": "report", "article_id": a["id"], "publisher": a["source"], "role": a["role"], "adds_information": a["adds"]["adds_information"],
                         "published_at": a["published"], "first_seen_at": a["fetched_at"], "order_time": a["order_time"], "order_basis": a["order_basis"], "event_time": None})
    for d in developments:
        timeline.append({"kind": "development", "type": d["type"], "article_id": d["trigger"]["article_id"], "published_at": d["trigger"]["published_at"],
                         "first_seen_at": d["trigger"]["first_seen_at"], "order_time": d["trigger"]["order_time"], "order_basis": d["trigger"]["order_basis"],
                         "event_time": None, "reliability": d["reliability"]})
    for f in figures:
        a2 = f["articles"][-1]
        timeline.append({"kind": "figure_change", "figure_kind": f["kind"], "measure": f["measure"], "article_id": a2["article_id"], "published_at": a2["published_at"],
                         "first_seen_at": a2["first_seen_at"], "order_time": a2["order_time"], "order_basis": a2["order_basis"], "event_time": None})
    timeline.sort(key=lambda t: (t["order_time"], {"report": 0, "development": 1, "figure_change": 2}[t["kind"]], t.get("article_id", 0)))
    events = [{"root_article_id": e["root_article_id"], "independence": e["independence"], "reason": e["reason"], "confidence": e["confidence"],
               "articles": len(e["members"]), "publishers": sorted({A[m]["source"] for m in e["members"]}), "origin_outside_corpus": e["origin_external"],
               "first_order_time": e["first_order_time"]} for e in res["reporting_events"]]
    st = res["stats"]
    non_first = [a for a in res["articles"] if not a["adds"]["first_in_story"]]
    sims = [a["adds"]["max_similarity_to_earlier"] for a in non_first if a["adds"]["max_similarity_to_earlier"] is not None]
    n_sim = max(1, len(sims))
    shape = {"restatement_share": round(sum(1 for x in sims if x >= si.ADDS_COS) / n_sim, 2), "adds_share": round(sum(1 for x in sims if x < si.ADDS_COS) / n_sim, 2),
             "loosely_related_share": round(sum(1 for a in non_first if a["reason"] == "LOOSELY_RELATED") / max(1, len(non_first)), 2)}
    # A hint, not a verdict: an EVENT story is mostly the same facts re-reported; a TOPIC cluster is mostly different pieces on one theme
    # (features, previews, gossip), where 'adds information' means 'another angle', not 'a new fact about one event'.
    shape["hint"] = "narrow_event" if shape["adds_share"] < 0.45 else "broad_topic_cluster"
    shape["caution"] = ("evolution is only meaningful for a narrow event; many articles here are different pieces on a theme"
                        if shape["hint"] == "broad_topic_cluster" or shape["loosely_related_share"] >= 0.3 else None)
    return {
        "available": True, "schema": "story-evolution-internal-1", "engine_version": si.ENGINE_VERSION, "event_id": event_id, "title": ev_row["title"],
        "summary": {"articles": st["articles"], "distinct_publishers": st["distinct_owners"], "reporting_events": st["reporting_events"],
                    "independent_origins": st["independent_events"], "articles_adding_information": len(later), "developments_internal": len(developments),
                    "figure_changes": len(figures), "uncertain_articles": sum(len(v) for v in uncertain.values()),
                    "evidence_articles_used": st["evidence_used"]},
        "shape": shape,
        "first_report": first_report, "independent_reports": independent, "later_information": later,
        "repeated_reports": repeated, "same_publisher_articles": same_publisher, "reporting_events": events, "uncertain": uncertain,
        "developments": developments, "figure_changes": figures, "claim_graph": build_claim_graph(res, ref), "timeline": timeline,
        "reliability": RELIABILITY,
        "limits": ["headline + excerpt level (plus a short fetched lede for a few articles): independence cannot be established from this text alone",
                   "event_time is never inferred; order uses the publisher's published time unless order_basis says otherwise",
                   "'adds information' means the text contains something earlier articles' text did not; it is not a statement of truth",
                   "developments are internal and low-confidence; figure changes say reports differ, not which is right"],
    }


def render(o):
    if not o.get("available"):
        return f"story {o.get('event_id')}: not available ({o.get('reason')})"
    s = o["summary"]
    L = [f"STORY {o['event_id']}: {o['title'][:100]}",
         f"  {s['articles']} articles / {s['distinct_publishers']} publishers -> {s['reporting_events']} reporting events, {s['independent_origins']} independent origin(s), "
         f"{s['articles_adding_information']} article(s) add information, {s['figure_changes']} figure change(s), {s['developments_internal']} internal development(s), "
         f"{s['uncertain_articles']} uncertain"]
    f = o["first_report"]
    sh = o["shape"]
    L.append(f"  SHAPE         {sh['hint']} (adds {sh['adds_share']}, restates {sh['restatement_share']}, loosely related {sh['loosely_related_share']})" + (f"  !! {sh['caution']}" if sh["caution"] else ""))
    L.append(f"  FIRST REPORT  [{f['publisher']}] {f['headline'][:90]}  ({(f['published_at'] or '')[:16]}, basis {f['order_basis']}; role {f['role']}/{f['reason']})")
    for i in o["independent_reports"][:4]:
        if i["article_id"] != f["article_id"]:
            L.append(f"  INDEPENDENT   [{i['publisher']}] {i['headline'][:80]}  ({i['reason']}, {i['confidence']})")
    for x in o["later_information"][:5]:
        L.append(f"  ADDS          [{x['publisher']}] {x['headline'][:80]}  (sim {x['max_similarity_to_earlier']}, {x['role']}/{x['reason']}" + (f", figures {x['new_figures']}" if x["new_figures"] else "") + ")")
    for k, v in list(o["repeated_reports"].items())[:3]:
        L.append(f"  REPEATED      {len(v)} report(s) repeat {k}: " + ", ".join(f"{r['publisher']}({r['reason']})" for r in v[:4]))
    for fc in o["figure_changes"][:4]:
        L.append(f"  FIGURES       {fc['kind']} {fc['measure']}: {fc['earlier']['value']:g} -> {fc['later']['value']:g}  ({fc['articles'][0]['publisher']} -> {fc['articles'][-1]['publisher']})")
    for d in o["developments"][:4]:
        L.append(f"  DEVELOPMENT*  {d['type']} [{d['trigger']['publisher']}] {d['trigger']['headline'][:70]}  ({d['corroborating_publishers']} publisher(s); *internal, low confidence)")
    for n in o["claim_graph"]["nodes"][:5]:
        att = ",".join(n["attribution"])
        L.append(f"  CLAIM         {n['measure']} {n['value']:g}: {n['article_count']} article(s), {n['reporting_events']} reporting event(s), {len(n['publishers'])} publisher(s); attribution {att}")
    if o["uncertain"]:
        L.append("  UNCERTAIN     " + ", ".join(f"{k}: {len(v)}" for k, v in o["uncertain"].items()))
    return "\n".join(L)


def main(argv):
    import argparse
    import random
    import database
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", type=int)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--sample", type=int)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--min-articles", type=int, default=6)
    a = ap.parse_args(argv)
    conn = database.get_connection()
    ids = [a.event] if a.event else []
    if a.sample:
        cand = [r[0] for r in conn.execute("SELECT event_id FROM si_story_state WHERE n_articles >= ? ORDER BY event_id DESC LIMIT 800", (a.min_articles,))]
        random.Random(a.seed).shuffle(cand)
        ids = cand[:a.sample]
    for eid in ids:
        o = build_story_evolution(conn, eid)
        print(json.dumps(o, indent=1, default=str, ensure_ascii=False) if a.json else render(o))
        print()
    conn.close()


if __name__ == "__main__":
    main(sys.argv[1:])
