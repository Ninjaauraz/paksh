"""
test_phase30a_incident_identity.py - Phase 30A: regression tests for the
second cross-cycle incident-identity veto (_generic_procedural_only_veto()),
which generalizes Phase 28B's _recurring_entity_only_veto() from a single
evidenced vocabulary class (recurring political/geographic entities) to a
second, independently evidenced class (generic legal/judicial-procedure
words). Real production DB evidence (real cached embeddings, real
cluster._keywords()), following the established test_phaseNN_*.py pattern.

Never touches paksh.db, never calls a real embedder, never mutates production.

Run:  py test_phase30a_incident_identity.py
"""
import sqlite3
import numpy as np

import cluster
import analyze

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


conn = sqlite3.connect("file:paksh.db?mode=ro", uri=True, timeout=30)
c = conn.cursor()


def article_row(aid):
    return c.execute("SELECT title, summary, language FROM articles WHERE id=?", (aid,)).fetchone()


def get_vec(aid):
    title, summary, _ = article_row(aid)
    text = cluster._text_of({"title": title, "summary": summary or ""})
    key = cluster._emb_key(text)
    r = c.execute("SELECT vec FROM embeddings WHERE key=?", (key,)).fetchone()
    if not r:
        return None
    v = np.frombuffer(r[0], dtype=np.float32).astype(float)
    n = np.linalg.norm(v)
    return v / n if n else v


def merge_kw_of(ids):
    arts = []
    for aid in ids:
        t, s, _ = article_row(aid)
        arts.append({"title": t, "summary": s or ""})
    return cluster.merge_keywords(arts)


def centroid_of(ids):
    vecs = [v for v in (get_vec(aid) for aid in ids) if v is not None]
    if not vecs:
        return None
    ctr = np.mean(vecs, axis=0)
    return ctr / np.linalg.norm(ctr)


def replay(group_a_ids, group_b_ids, event_topic="Politics"):
    """Real replay through the actual implemented functions (both vetoes),
    mirroring _merge_into_existing()'s decision order. Returns a dict, or
    None if embeddings are unavailable."""
    kw_a, kw_b = merge_kw_of(group_a_ids), merge_kw_of(group_b_ids)
    ca, cb = centroid_of(group_a_ids), centroid_of(group_b_ids)
    if ca is None or cb is None:
        return None
    sim = float(np.dot(ca, cb))
    shared = kw_a & kw_b
    articles_by_id = {aid: {"title": article_row(aid)[0], "summary": article_row(aid)[1]}
                       for aid in group_b_ids}
    topic_veto = analyze._topic_mismatch_veto({"ids": group_b_ids}, {"topic": event_topic},
                                               articles_by_id, sim)
    entity_veto = analyze._recurring_entity_only_veto(shared, sim)
    procedural_veto = analyze._generic_procedural_only_veto(shared, sim)
    base_gate = sim >= cluster.XMERGE_SIM and len(shared) >= cluster.XMERGE_MIN_SHARED
    merged = base_gate and not topic_veto and not entity_veto and not procedural_veto
    return {"sim": sim, "shared": shared, "topic_veto": topic_veto,
            "entity_veto": entity_veto, "procedural_veto": procedural_veto, "merged": merged}


print("=== Phase 30A: new veto exists and is wired correctly ===")
check("1: _PROCEDURAL_OVERLAP_KW contains the evidence-backed entries",
      {"seeks", "response", "plea", "against", "conduct", "take", "law", "students"}
      <= analyze._PROCEDURAL_OVERLAP_KW)
check("2: _PROCEDURAL_OVERLAP_KW is small and bounded (not a general stopword list)",
      len(analyze._PROCEDURAL_OVERLAP_KW) <= 15)
check("3: _RECURRING_ENTITY_KW now also carries 'telangana' (outlet-leak evidence)",
      "telangana" in analyze._RECURRING_ENTITY_KW)
check("4: _RECURRING_ENTITY_KW remains small and bounded",
      len(analyze._RECURRING_ENTITY_KW) <= 10)
check("5: pure procedural-only overlap, similarity below HIGH_SIM -> veto fires",
      analyze._generic_procedural_only_veto({"seeks", "response", "plea"}, cluster.HIGH_SIM - 0.05) is True)
check("6: at least one incident-specific shared keyword survives -> veto does NOT fire",
      analyze._generic_procedural_only_veto({"seeks", "response", "cjp"}, cluster.HIGH_SIM - 0.05) is False)
check("7: extreme-similarity escape valve (>=HIGH_SIM) -> veto does NOT fire even with only procedural words",
      analyze._generic_procedural_only_veto({"seeks", "response"}, cluster.HIGH_SIM) is False)
check("8: escape valve reuses the EXISTING HIGH_SIM constant, no new threshold introduced",
      hasattr(cluster, "HIGH_SIM"))
check("9: _recurring_entity_only_veto() itself is untouched (Phase 28B behavior preserved)",
      analyze._recurring_entity_only_veto({"punjab", "aap"}, cluster.HIGH_SIM - 0.05) is True)

print("\n=== #16667 C->A real-data replay - MUST REJECT (Phase 29C: legacy, pre-28B) ===")
r = replay([426973, 427641],
           [448000, 448684, 448767, 448900, 448951, 449013, 449584, 449702, 449815],
           event_topic="Crime & Law")
check("10: real cached embeddings were found for this replay", r is not None)
if r:
    check("11: shared merge_keywords() are the real corpus evidence (procedural-only)",
          r["shared"] == {"plea", "response", "seeks"})
    check("12: real centroid similarity is below HIGH_SIM", r["sim"] < cluster.HIGH_SIM)
    check("13: the recurring-entity veto does NOT catch this (different vocabulary class)",
          r["entity_veto"] is False)
    check("14: the new procedural veto DOES catch this", r["procedural_veto"] is True)
    check("15: the cross-cycle merge is REJECTED", r["merged"] is False)

print("\n=== #16667 A->B real-data replay - MUST REJECT (Phase 29C: the live, post-28B failure) ===")
r = replay([441706, 448000, 448684, 448767, 448900, 448951, 449013, 449584, 449702, 449815,
            452779, 452882, 452887, 453693, 454339, 454377, 454541, 459493, 459627, 459634,
            459781, 459905, 459911, 459912, 459914, 467432, 471911],
           [479009, 479021, 479090, 479667, 479762, 479916],
           event_topic="Crime & Law")
check("16: real cached embeddings were found for this replay", r is not None)
if r:
    check("17: shared merge_keywords() are the real corpus evidence",
          r["shared"] == {"against", "conduct", "law", "students", "take", "telangana"})
    check("18: real centroid similarity is below HIGH_SIM", r["sim"] < cluster.HIGH_SIM)
    check("19: the recurring-entity veto does NOT catch this on its own "
          "(this is the confirmed Phase 29C gap - 'telangana' alone isn't enough pre-30A "
          "since 'law'/'students'/'conduct'/'against'/'take' still survive)",
          r["entity_veto"] is False)
    check("20: the new procedural veto DOES catch this - THE REQUIRED FIX", r["procedural_veto"] is True)
    check("21: the cross-cycle merge is REJECTED - this is the merge that was "
          "ACTUALLY EXECUTED IN PRODUCTION by the deployed Phase 28B code (Phase 29C)",
          r["merged"] is False)

print("\n=== #17289 A->B real-data replay - MUST REMAIN REJECTED (Phase 28B, unaffected) ===")
r = replay([448150, 449693, 453688, 454180],
           [471394, 471425, 471490, 471511, 471821, 472147, 472333, 472581, 474271, 474448],
           event_topic="Politics")
check("22: real cached embeddings were found for this replay", r is not None)
if r:
    check("23: shared merge_keywords() are exactly the recurring-entity terms",
          r["shared"] == {"punjab", "aap"})
    check("24: rejected by the EXISTING entity veto, not the new one (no regression in cause)",
          r["entity_veto"] is True)
    check("25: the cross-cycle merge remains REJECTED", r["merged"] is False)

print("\n=== Legitimate continuity controls - MUST PRESERVE (mandatory gate, Phase 28B's own set) ===")
CONTROLS = [
    ("8672 (CJP fast)", [152051, 155001], [157575, 159940, 159941, 161099], "Politics"),
    ("8907 (NC protests)", [157996, 160631, 160642, 160759, 161047], [161407, 161466], "Politics"),
    ("8555 (Parliament march)", [152564, 152713, 152931, 152934], [155180, 155193, 155303, 155352], "Politics"),
    ("8808 (Parliament session)", [156038, 156490, 156796, 157119], [161419, 161463], "Politics"),
    ("16558 (stock market)", [422866, 423475], [426980, 427512], "Economy"),
    ("8016 (Hindi/multilingual - Wangchuk)", [137406, 138090, 138235, 138283],
     [141532, 141574, 141588, 141589], "Politics"),
]
for label, a, b, topic in CONTROLS:
    r = replay(a, b, event_topic=topic)
    if r is None:
        check(f"26: {label} - embeddings available", False)
        continue
    check(f"26: {label} - real incident-specific keyword survives both stoplists",
          bool(r["shared"] - analyze._RECURRING_ENTITY_KW - analyze._PROCEDURAL_OVERLAP_KW))
    check(f"27: {label} - not vetoed by the new procedural check", r["procedural_veto"] is False)
    check(f"28: {label} - cross-cycle merge is PRESERVED (no new false negative)", r["merged"] is True)

print("\n=== #14939 (real 'Law Students Protest BCI Chief... NALSAR' story) - "
      "stress test for 'law'/'students' in _PROCEDURAL_OVERLAP_KW ===")
c.execute("SELECT id, fetched_at FROM articles WHERE event_id=14939 ORDER BY fetched_at")
rows = c.fetchall()
if rows:
    days = sorted({fa[:10] for _, fa in rows})
    day0 = days[0]
    early = [aid for aid, fa in rows if fa[:10] == day0]
    later = [aid for aid, fa in rows if fa[:10] != day0]
    r = replay(early, later, event_topic="Crime & Law") if early and later else None
    if r is None:
        check("29: #14939 embeddings/day-split available", False)
    else:
        check("29: a real continuing 'law students' story still shares 'law' and/or 'students' "
              "cross-cycle (the exact word(s) this fixture is protecting)",
              bool(r["shared"] & {"law", "students"}))
        check("30: it is NOT vetoed - other genuine identity evidence (bci/nalsar/chief/etc.) "
              "survives even after removing 'law'/'students'", r["procedural_veto"] is False)
        check("31: the cross-cycle merge is PRESERVED", r["merged"] is True)
else:
    print("  (event #14939 not present in this DB snapshot - skipped, not a failure)")

print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
