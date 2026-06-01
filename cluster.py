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
from dotenv import load_dotenv
load_dotenv()
import hashlib
import numpy as np

EMBED_MODEL = "gemini-embedding-001"   # multilingual; "text-embedding-004" also works

# Cosine-similarity thresholds. These depend on the embedding model and will
# need a little tuning against real output - preview with `python cluster.py`.
JOIN_THRESHOLD = 0.80    # min similarity to join an existing cluster (raised: Gemini embeddings run high)
MERGE_THRESHOLD = 0.82   # min similarity between two clusters to merge them (raised to match)
DUP_THRESHOLD = 0.93     # at/above this, two same-outlet items are duplicates
MIN_SOURCES = 2          # a cluster needs this many distinct outlets to be an event


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


def cluster_vectors(vecs, join=JOIN_THRESHOLD, merge=MERGE_THRESHOLD):
    """Leader clustering + centroid merge. vecs must be unit-normalised (n, d).
    Returns a list of index-lists."""
    clusters = []  # each: {"members": [int], "centroid": vec}
    for i in range(len(vecs)):
        v = vecs[i]
        best, best_sim = -1, -1.0
        for ci, c in enumerate(clusters):
            sim = float(np.dot(v, c["centroid"]))
            if sim > best_sim:
                best_sim, best = sim, ci
        if best >= 0 and best_sim >= join:
            c = clusters[best]
            c["members"].append(i)
            c["centroid"] = _recentroid(vecs, c["members"])
        else:
            clusters.append({"members": [i], "centroid": v})

    # merge pass: fold together clusters whose centroids are very close
    changed = True
    while changed and len(clusters) > 1:
        changed = False
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                if float(np.dot(clusters[i]["centroid"], clusters[j]["centroid"])) >= merge:
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
    out = []
    for group in cluster_vectors(vecs):
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