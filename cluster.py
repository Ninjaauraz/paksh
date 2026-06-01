"""
cluster.py - STEP 1.5: group articles that report the SAME event.

Approach (the robust, standard one):
  1. turn each article (title + summary) into a vector with a MULTILINGUAL
     embedding model, so an English article and a Hindi article about the same
     event land near each other in vector space;
  2. cluster by cosine similarity (leader clustering + a centroid-merge pass);
  3. drop same-outlet near-duplicates (e.g. one outlet posting via two feeds);
  4. keep only clusters covered by 2+ distinct outlets - those become events.

The embedding backend is pluggable:
  * default_embedder  - Google Gemini embeddings (multilingual, needs API key)
  * lexical_embedder  - offline hashing fallback (WITHIN one language only)
  * or inject your own (the tests pass a deterministic stub)

This module only groups. Summarising each group is Step 2 (analyze.py).
Run `python cluster.py` to preview grouping without spending analysis calls.
"""

import os
import re
import hashlib
import numpy as np

EMBED_MODEL = "gemini-embedding-001"   # multilingual; "text-embedding-004" also works

# Cosine-similarity thresholds. These depend on the embedding model and will
# need a little tuning against real output - preview with `python cluster.py`.
JOIN_THRESHOLD = 0.84    # min similarity to join a cluster (must ALSO share keywords, unless very similar)
MERGE_THRESHOLD = 0.86   # min similarity between two clusters to merge (must ALSO share keywords, unless very similar)
HIGH_SIM = 0.90          # at/above this, trust the embedding alone (lets cross-lingual same-event pairs group)
MIN_SHARED = 2           # this many shared keywords needed to join a cluster's seed (1 coincidence isn't enough)
DUP_THRESHOLD = 0.93     # at/above this, two same-outlet items are duplicates
MIN_SOURCES = 2          # a cluster needs this many distinct outlets to be an event

# Generic words too common to count as a discriminating "keyword" - including the
# India-politics vocabulary that otherwise glues unrelated stories together.
_STOP = set("the a an and or of to in on for with at by from as is are was were be been "
            "new latest update updates news live video watch photos pics today day after "
            "over into out up down off amid says said will may can not no get how why what "
            "india indian govt government centre center delhi mumbai police minister party "
            "modi congress bjp court supreme year report deal plan talks ban case big top "
            "first set hit crore lakh rupees rupee explained official "
            # outlet names (Google News appends them to titles) - never a real keyword
            "zee jagran bhaskar lallantop aajtak aaj tak republic swarajya opindia satya "
            "ndtv hindu hindustan express mint scroll wire navbharat amar ujala times".split())
_HI_STOP = set("में की के का और से पर को है कि भी एक यह वह तक ने हैं था थे लिए मोदी कांग्रेस भाजपा".split())


# ------------------------------ embedders ------------------------------

def default_embedder(texts):
    """Google Gemini multilingual embeddings. Batched. Returns list of vectors."""
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    vectors, B = [], 100
    for k in range(0, len(texts), B):
        batch = texts[k:k + B]
        try:
            resp = client.models.embed_content(
                model=EMBED_MODEL, contents=batch,
                config=types.EmbedContentConfig(task_type="CLUSTERING"))
        except Exception:
            resp = client.models.embed_content(model=EMBED_MODEL, contents=batch)
        vectors.extend(e.values for e in resp.embeddings)
    return vectors


def lexical_embedder(texts, dim=512):
    """Offline fallback: hashed bag of word uni/bi-grams. Works WITHIN a single
    language only (it cannot bridge English<->Hindi). Useful for dev/testing."""
    M = np.zeros((len(texts), dim), dtype=float)
    for r, t in enumerate(texts):
        toks = re.findall(r"\w+", (t or "").lower())
        grams = toks + [f"{toks[i]}_{toks[i+1]}" for i in range(len(toks) - 1)]
        for g in grams:
            h = int(hashlib.md5(g.encode("utf-8")).hexdigest(), 16) % dim
            M[r, h] += 1.0
    return M


# ------------------------------ maths ------------------------------

def _normalize(M):
    M = np.asarray(M, dtype=float)
    norms = np.linalg.norm(M, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return M / norms


def _text_of(a):
    return f"{a.get('title', '')}. {(a.get('summary') or '')}".strip()


def _keywords(a):
    """Discriminating tokens from the TITLE (+ a little summary): names, acronyms,
    distinctive words. NOT bare numbers (years/prices/counts cause false matches).
    Used as a hard gate so unrelated stories can't merge on a coincidental token."""
    text = f"{a.get('title','')} {(a.get('summary') or '')[:80]}".lower()
    latin = set(re.findall(r"[a-z][a-z]{2,}", text))        # words / acronyms, len >= 3, letters only
    deva  = set(re.findall(r"[\u0900-\u097F]{3,}", text))    # Hindi words, len >= 3
    return (latin - _STOP) | (deva - _HI_STOP)


def cluster_vectors(vecs, join=JOIN_THRESHOLD, merge=MERGE_THRESHOLD, kw=None, langs=None):
    """Leader clustering + centroid merge, with a keyword gate. vecs unit-normalised.
    Joining rule (when kw is given):
      * SAME language as the cluster's seed -> must share >= MIN_SHARED seed keywords.
      * DIFFERENT language -> may join on similarity >= HIGH_SIM alone (the only way an
        English and a Hindi article about the same event can pair, since they share no
        script). This keeps cross-lingual recall WITHOUT letting unrelated same-language
        articles blob together (Hindi embeddings sit very close, so same-language pairs
        must always prove a real keyword overlap).
    Gating on the seed (not the growing union) stops one cluster swallowing everything.
    Returns a list of index-lists."""
    clusters = []  # each: {"members":[int], "centroid":vec, "seedkw":set, "seedlang":str|None}

    def kw_hit(i, c):
        return kw is not None and len(kw[i] & c["seedkw"]) >= MIN_SHARED

    def eligible(i, c, sim):
        if sim < join:
            return False
        same_lang = (langs is None) or (langs[i] == c["seedlang"])
        if same_lang:
            return kw is None or kw_hit(i, c)
        return sim >= HIGH_SIM or kw_hit(i, c)   # cross-language: similarity OR a shared name

    for i in range(len(vecs)):
        v = vecs[i]
        best, best_sim = -1, -1.0
        for ci, c in enumerate(clusters):
            sim = float(np.dot(v, c["centroid"]))
            if eligible(i, c, sim) and sim > best_sim:
                best_sim, best = sim, ci
        if best >= 0:
            c = clusters[best]
            c["members"].append(i)
            c["centroid"] = _recentroid(vecs, c["members"])
        else:
            clusters.append({"members": [i], "centroid": v,
                             "seedkw": (kw[i] if kw is not None else set()),
                             "seedlang": (langs[i] if langs is not None else None)})

    # merge pass: same-language clusters must share keywords; cross-language may merge on similarity
    changed = True
    while changed and len(clusters) > 1:
        changed = False
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                csim = float(np.dot(clusters[i]["centroid"], clusters[j]["centroid"]))
                if csim < merge:
                    continue
                same_lang = (langs is None) or (clusters[i]["seedlang"] == clusters[j]["seedlang"])
                share = kw is None or len(clusters[i]["seedkw"] & clusters[j]["seedkw"]) >= MIN_SHARED
                ok = share if same_lang else (csim >= HIGH_SIM or share)
                if ok:
                    clusters[i]["members"].extend(clusters[j]["members"])
                    clusters[i]["centroid"] = _recentroid(vecs, clusters[i]["members"])
                    del clusters[j]
                    changed = True
                    break
            if changed:
                break
    return [sorted(c["members"]) for c in clusters]


def _recentroid(vecs, members):
    m = vecs[members].mean(axis=0)
    n = np.linalg.norm(m) or 1.0
    return m / n


def _dedupe_same_outlet(indices, vecs, articles):
    """Within one cluster, if the SAME outlet appears with near-identical items,
    keep only the richest (longest summary)."""
    by_src = {}
    for i in indices:
        by_src.setdefault(articles[i]["source"], []).append(i)
    kept = []
    for _src, idxs in by_src.items():
        idxs = sorted(idxs, key=lambda i: len(articles[i].get("summary") or ""), reverse=True)
        chosen = []
        for i in idxs:
            if all(float(np.dot(vecs[i], vecs[j])) < DUP_THRESHOLD for j in chosen):
                chosen.append(i)
        kept.extend(chosen)
    return sorted(kept)


# ------------------------------ public API ------------------------------

def cluster_with_details(articles, embedder=None):
    """Return every cluster (including singletons) with metadata, for inspection."""
    if not articles:
        return []
    embedder = embedder or default_embedder
    vecs = _normalize(embedder([_text_of(a) for a in articles]))
    kw = [_keywords(a) for a in articles]
    langs = [a.get("language", "en") for a in articles]
    out = []
    for group in cluster_vectors(vecs, kw=kw, langs=langs):
        kept = _dedupe_same_outlet(group, vecs, articles)
        rows = [articles[i] for i in kept]
        out.append({
            "ids": [r["id"] for r in rows],
            "size": len(rows),
            "source_count": len({r["source"] for r in rows}),
            "sources": sorted({r["source"] for r in rows}),
            "languages": sorted({r["language"] for r in rows}),
            "sample_title": rows[0]["title"] if rows else "",
        })
    out.sort(key=lambda d: (-d["source_count"], -d["size"]))
    return out


def cluster_articles(articles, embedder=None):
    """Drop-in for analyze.py's old PASS1: returns id-lists for clusters covered
    by MIN_SOURCES+ distinct outlets."""
    return [d["ids"] for d in cluster_with_details(articles, embedder)
            if d["source_count"] >= MIN_SOURCES]


def main():
    import sys
    from database import init_db, get_unclustered_articles
    init_db()
    articles = get_unclustered_articles()
    print(f"\n{len(articles)} unclustered articles")
    if len(articles) < 2:
        print("Not enough yet - run `python ingest.py` first.\n")
        return
    use_lex = "--lexical" in sys.argv
    if use_lex:
        print("Using OFFLINE lexical embedder (within-language only).")
    details = cluster_with_details(articles, lexical_embedder if use_lex else None)
    multi = [d for d in details if d["source_count"] >= MIN_SOURCES]
    print(f"{len(details)} clusters, {len(multi)} with {MIN_SOURCES}+ outlets "
          f"(marked *):\n")
    for d in details:
        flag = "*" if d["source_count"] >= MIN_SOURCES else " "
        print(f" {flag} [{d['source_count']} outlets · {d['size']} art · "
              f"{'/'.join(d['languages'])}] {d['sample_title'][:78]}")
    print("\n* = becomes an event. If grouping looks loose/over-merged, tune "
          "JOIN_THRESHOLD / MERGE_THRESHOLD in cluster.py.\n")


if __name__ == "__main__":
    main()