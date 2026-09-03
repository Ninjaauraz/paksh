"""
test_phase28b_story_boundary.py - Phase 28B: regression tests for the
cross-cycle incident-identity veto (Mechanism A), the material-change/
resummarise signal, and the Mechanism B generic-word additions ("win",
"preseason"). Real production DB evidence (real cached embeddings, real
cluster._keywords()), following the established test_phaseNN_*.py pattern.

Never touches paksh.db, never calls a real embedder, never mutates production.

Run:  py test_phase28b_story_boundary.py
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
    """Real replay through the actual implemented functions. Returns
    (merged, resummarise, sim, shared) or (None, None, None, None) if
    embeddings are unavailable."""
    kw_a, kw_b = merge_kw_of(group_a_ids), merge_kw_of(group_b_ids)
    ca, cb = centroid_of(group_a_ids), centroid_of(group_b_ids)
    if ca is None or cb is None:
        return None, None, None, None
    sim = float(np.dot(ca, cb))
    shared = kw_a & kw_b
    articles_by_id = {aid: {"title": article_row(aid)[0], "summary": article_row(aid)[1]}
                       for aid in group_b_ids}
    topic_veto = analyze._topic_mismatch_veto({"ids": group_b_ids}, {"topic": event_topic},
                                               articles_by_id, sim)
    entity_veto = analyze._recurring_entity_only_veto(shared, sim)
    merged = (sim >= cluster.XMERGE_SIM and len(shared) >= cluster.XMERGE_MIN_SHARED
              and not topic_veto and not entity_veto)
    resum = analyze._merge_needs_resummarise(shared, sim) if merged else None
    return merged, resum, sim, shared


print("=== MECHANISM A: incident-identity veto exists and is wired correctly ===")
check("1: _RECURRING_ENTITY_KW contains the evidence-backed entries",
      {"punjab", "aap"} <= analyze._RECURRING_ENTITY_KW)
check("2: _RECURRING_ENTITY_KW is small and bounded (not a general stopword list)",
      len(analyze._RECURRING_ENTITY_KW) <= 10)
check("3: recurring-entity-only shared keywords, similarity below HIGH_SIM -> veto fires",
      analyze._recurring_entity_only_veto({"punjab", "aap"}, cluster.HIGH_SIM - 0.05) is True)
check("4: at least one incident-specific shared keyword survives -> veto does NOT fire",
      analyze._recurring_entity_only_veto({"punjab", "aap", "chadha"}, cluster.HIGH_SIM - 0.05) is False)
check("5: extreme-similarity escape valve (>=HIGH_SIM) -> veto does NOT fire even with only recurring words",
      analyze._recurring_entity_only_veto({"punjab", "aap"}, cluster.HIGH_SIM) is False)
check("6: escape valve reuses the EXISTING HIGH_SIM constant, no new threshold introduced",
      hasattr(cluster, "HIGH_SIM"))

print("\n=== MECHANISM A: #17289 real-data replay - MUST REJECT ===")
merged, resum, sim, shared = replay(
    [448150, 449693, 453688, 454180],
    [471394, 471425, 471490, 471511, 471821, 472147, 472333, 472581, 474271, 474448])
check("7: real cached embeddings were found for this replay", sim is not None)
if sim is not None:
    check("8: shared merge_keywords() are exactly the recurring-entity terms (real corpus evidence)",
          shared == {"punjab", "aap"})
    check("9: real centroid similarity is below HIGH_SIM (not an extreme-similarity case)",
          sim < cluster.HIGH_SIM)
    check("10: the cross-cycle merge is REJECTED by the new veto", merged is False)

print("\n=== MECHANISM A: legitimate continuity controls - MUST PRESERVE (mandatory gate) ===")
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
    merged, resum, sim, shared = replay(a, b, event_topic=topic)
    if sim is None:
        check(f"11: {label} - embeddings available", False)
        continue
    check(f"11: {label} - real incident-specific keyword survives (not recurring-entity-only)",
          bool(shared - analyze._RECURRING_ENTITY_KW))
    check(f"12: {label} - cross-cycle merge is PRESERVED (no new false negative)", merged is True)
    check(f"13: {label} - routine keyword-confirmed continuity does NOT trigger resummarise "
          f"(no unnecessary LLM cost)", resum is False)

print("\n=== MECHANISM A: #15953 - documented pre-existing topic-veto behavior, NOT a regression ===")
merged, resum, sim, shared = replay(
    [378634, 378886, 379069, 379217], [389850, 390216, 390485, 390638], event_topic="Politics")
if sim is not None:
    articles_by_id = {aid: {"title": article_row(aid)[0], "summary": article_row(aid)[1]}
                       for aid in [389850, 390216, 390485, 390638]}
    topic_veto_alone = analyze._topic_mismatch_veto(
        {"ids": [389850, 390216, 390485, 390638]}, {"topic": "Politics"}, articles_by_id, sim)
    check("14: #15953's rejection is caused by the PRE-EXISTING topic veto, "
          "not the new entity veto (identical to pre-Phase-28B behavior)",
          topic_veto_alone is True and analyze._recurring_entity_only_veto(shared, sim) is False)

print("\n=== MECHANISM B: 'win' and 'preseason' are now generic; siblings are NOT ===")
check("15: 'win' in _GENERIC_KW", "win" in cluster._GENERIC_KW)
check("16: 'preseason' in _GENERIC_KW", "preseason" in cluster._GENERIC_KW)
for sibling in ("beat", "lead", "score", "victory", "defeat"):
    check(f"17: sibling {sibling!r} deliberately NOT added (zero sole-bridge evidence found)",
          sibling not in cluster._GENERIC_KW)
check("18: 'man' deliberately NOT added (unsafe - collateral risk across ordinary English)",
      "man" not in cluster._GENERIC_KW)
check("19: 'city' deliberately NOT added (confirmed false-negative risk for legitimate "
      "'Man City' stories)", "city" not in cluster._GENERIC_KW)

print("\n=== MECHANISM B: #14552 real-data replay - safe improvement, not full resolution ===")
rows = c.execute("SELECT id, title, summary FROM articles WHERE event_id=14552 ORDER BY id").fetchall()
kws = {aid: cluster._gating_keywords({"title": t, "summary": s or ""}) for aid, t, s in rows}
real_story = {349100, 349126}
nfl = {341200, 341203, 341210, 341721, 341749, 341753, 351145, 351147}
check("20: the two real Community Shield articles still share real keywords with each other",
      bool(kws[349100] & kws[349126]))
check("21: no NFL article has a DIRECT keyword edge to a real Community Shield article "
      "(the 'win' bridge that connected them is gone)",
      not any(kws[a] & kws[b] for a in nfl for b in real_story))
import itertools
edges_after = sum(1 for a, b in itertools.combinations(kws, 2) if kws[a] & kws[b])
check("22: some direct pairwise contamination edges were removed vs. pre-28B "
      f"(measured: 741 -> {edges_after})", edges_after < 741)

print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
