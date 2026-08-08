"""
cluster.py - STEP 1.5: group articles that report the SAME event.

Approach (the robust, standard one):
  1. turn each article (title + summary) into a vector with a MULTILINGUAL
     embedding model, so an English article and a Hindi article about the same
     event land near each other in vector space;
  2. cluster by cosine similarity (leader clustering + a centroid-merge pass);
  3. drop same-outlet near-duplicates (e.g. one outlet posting via two feeds);
  4. keep only clusters covered by 2+ distinct outlets - those become events.

The embedding backend is pluggable (set PAKSH_BACKEND):
  * "ollama"     - LOCAL multilingual bge-m3 via Ollama (default; free, no API key)
  * "cloudflare" - the SAME bge-m3 on Cloudflare Workers AI (GPU-hosted, free tier);
                   opt-in faster embeddings. Verify first: `py cluster.py --verify-cf`
  * "gemini"     - Google Gemini embeddings (multilingual, needs API key + billing)
  * lexical_embedder - offline hashing fallback (WITHIN one language only; dev use)
  * or inject your own (the tests pass a deterministic stub)

This module only groups. Summarising each group is Step 2 (analyze.py).
Run `python cluster.py` to preview grouping locally without spending a cent.
"""

import os
import re
import sys
import json
import hashlib
import urllib.request
import urllib.error
import numpy as np

# Windows consoles default stdout to cp1252, which cannot encode Devanagari (Hindi)
# titles - printing one raises UnicodeEncodeError and kills the run. Force UTF-8 so
# bilingual titles print safely whether output goes to a console or a captured file.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Load GEMINI_API_KEY from a local .env so `python cluster.py` works on its own
# (ingest.py / analyze.py already do this; without it the preview can't embed).
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ---- embedding backend ------------------------------------------------------
# "ollama"     = LOCAL, multilingual bge-m3, no API key, no bill (default).
# "cloudflare" = the SAME bge-m3 on Cloudflare Workers AI (GPU-hosted, free tier).
#                Shares the bge-m3 cache namespace + thresholds below (same model =
#                same vector geometry), so it's a drop-in. VERIFY compatibility on
#                your data FIRST with `py cluster.py --verify-cf` before switching a
#                live corpus. Creds go in ai_keys.env (CLOUDFLARE_ACCOUNT_ID / _API_TOKEN).
# "gemini"     = Google Gemini embeddings (needs API key + billing).
# Flip with the PAKSH_BACKEND env var, or just edit the default below.
BACKEND = os.environ.get("PAKSH_BACKEND", "ollama").lower()
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# Cosine-similarity thresholds DEPEND ON THE MODEL. bge-m3's scale runs lower than
# Gemini's, so the two backends carry different defaults. After your first real run,
# fine-tune with `python calibrate.py` (it prints recommended numbers for your data).
if BACKEND == "gemini":
    EMBED_MODEL    = os.environ.get("PAKSH_EMBED_MODEL", "gemini-embedding-001")
    JOIN_THRESHOLD = 0.80    # min similarity to join a cluster (must ALSO share 2 keywords, unless very similar)
    MERGE_THRESHOLD= 0.82    # min similarity between two clusters to merge
    HIGH_SIM       = 0.90    # at/above this, trust the embedding alone (cross-lingual same-event pairs)
    STRONG_SIM     = 0.88    # at/above this, ONE shared keyword is enough (recall for reworded headlines)
    DUP_THRESHOLD  = 0.93    # at/above this, two same-outlet items are duplicates
else:  # ollama OR cloudflare - same bge-m3 model, so same cache namespace + thresholds
    EMBED_MODEL    = os.environ.get("PAKSH_EMBED_MODEL", "bge-m3")
    # Calibrated for bge-m3 on real Paksh data via `py calibrate.py` (2026-06).
    JOIN_THRESHOLD = 0.61
    MERGE_THRESHOLD= 0.64
    HIGH_SIM       = 0.79
    STRONG_SIM     = 0.79    # raised from 0.72: a single GENERIC shared word (e.g.
                             # "fire") must now clear ~the median same-story score
                             # before it can glue two different same-type events.
    DUP_THRESHOLD  = 0.90

MIN_SHARED  = 2          # shared keywords needed to join a cluster's seed (1 coincidence isn't enough)
MIN_SOURCES = 2          # a cluster needs this many distinct outlets to be an event

# --- cross-cycle merge: fold a new cluster into a RECENT existing event ----------
# Deliberately conservative: a wrong merge (two unrelated stories) is worse than a
# duplicate, so the bar sits ABOVE the within-batch join threshold. All env-tunable.
MERGE_WINDOW_DAYS = int(os.environ.get("PAKSH_MERGE_WINDOW_DAYS", "5"))
XMERGE_MIN_SHARED = int(os.environ.get("PAKSH_XMERGE_MIN_SHARED", "2"))
# diffuse-event guard: required shared keywords scale with the event's breadth, so a
# polluted grab-bag event (huge keyword union) needs proportionally more specific
# overlap. 1 extra shared keyword required per this many event keywords.
XMERGE_KW_PER_SHARE = int(os.environ.get("PAKSH_MERGE_KW_PER_SHARE", "25"))
XMERGE_MIN_FRAC = float(os.environ.get("PAKSH_MERGE_MIN_FRAC", "0.22"))
XMERGE_MAX_EVENT_KW = int(os.environ.get("PAKSH_MERGE_MAX_EVENT_KW", "140"))
if BACKEND == "gemini":
    XMERGE_SIM = float(os.environ.get("PAKSH_XMERGE_SIM", "0.84"))
else:
    XMERGE_SIM = float(os.environ.get("PAKSH_XMERGE_SIM", "0.66"))

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

# Words that survive _keywords but are far too common to justify merging two stories
# across cycles on their own (this is also what stops ICC vs FIFA "world cup" over-merge).
_GENERIC_KW = set((
    "world cup india indian government report reports new news today over after amid "
    "first second third police court case cases minister ministers official officials "
    "state national people public party leader leaders meeting plan plans says said "
    "year years day days top big set launch launches reported announces announced "
    # journalism / format / roundup / date-time words that leak from bulletins & pages
    "bulletin bulletins edition editions page pages newspaper newspapers headlines "
    "roundup daily weekly update updates live read latest breaking jun jul june july "
    "thu fri mon tue wed sat sun "
    # generic sport / scoreboard words (sport-SPECIFIC tokens like cricket/fifa/icc kept)
    "match matches final finals clash league series scores results trophy fixtures "
    "commentary referees lineup preview intent squad "
    # company suffixes / market-page / horoscope-page tokens that leak from junk
    "ltd pvt inc corp limited premarket movers gallery video coverage overview "
    "numerology astrological calendar predictions"
).split()) | set((
    "भारत सरकार पुलिस मामला खबर देश राज्य खबरें ख़बरें बुलेटिन बजे सुबह रात "
    "जून जुलाई समाचार ताजा मुख्य पढ़ें"
).split())

# Distinctive outlet/masthead tokens that leak into titles & bylines and falsely
# satisfy the keyword gate (e.g. event #2987 absorbing unrelated "deccan chronicle"
# stories). ONLY tokens that are essentially never real content words are listed -
# content-bearing masthead words (india, kashmir, punjab, wire, republic, times,
# express, hindu, standard, guardian, france...) are deliberately NOT stripped.
_OUTLET_KW = set((
    "ndtv scroll opindia swarajya bhaskar jagran ujala navbharat aaj tak zee satya "
    "lallantop lallant lall newslaundry caravan quint livelaw tfipost khabar lahariya "
    "hindustan deccan chronicle herald telegraph firstpost jansatta news18 patrika "
    "reuters bloomberg jazeera welle deutsche eastmojo mojo mathrubhumi prabhat dunia "
    "kesari haribhoomi bhoomi hari tribune dainik pioneer"
).split())


# ------------------------------ embedders ------------------------------

def _emb_key(text):
    """Cache key for a text under the current embedding model."""
    return hashlib.sha256((EMBED_MODEL + "\n" + (text or "")).encode("utf-8")).hexdigest()


def _embed_via_api(texts):
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


# How many embed batches to send Ollama at once. Batches are independent, so
# running several concurrently overlaps their compute/IO and cuts wall-clock time
# on a backlog - WITHOUT changing a single vector (identical bge-m3 output, just
# computed in parallel, so it's safe to enable mid-run). For a real speed-up let
# Ollama serve them in parallel too: set OLLAMA_NUM_PARALLEL (e.g. 4) and restart
# Ollama. On a single CPU core, keep this low; a GPU / many cores can go higher.
EMBED_CONCURRENCY = max(1, int(os.environ.get("PAKSH_EMBED_CONCURRENCY", "4")))
EMBED_BATCH = max(1, int(os.environ.get("PAKSH_EMBED_BATCH", "64")))


def _ollama_embed_batch(batch):
    """Embed ONE batch of texts via Ollama. Returns a list of float32 vectors."""
    payload = json.dumps({"model": EMBED_MODEL, "input": batch}).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL + "/api/embed", data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise RuntimeError(
            "Could not reach Ollama at " + OLLAMA_URL + ". Is it running?\n"
            "  1. Install/open Ollama (https://ollama.com/download)\n"
            "  2. Run once:  ollama pull " + EMBED_MODEL + "\n"
            "Original error: " + str(e)) from None
    vecs = data.get("embeddings") or []
    if len(vecs) != len(batch):
        raise RuntimeError(
            "Ollama returned %d vectors for %d inputs. Did you run "
            "`ollama pull %s`?  Server said: %s"
            % (len(vecs), len(batch), EMBED_MODEL, str(data)[:200]))
    return [np.asarray(v, dtype=np.float32) for v in vecs]


def _embed_via_ollama(texts):
    """LOCAL multilingual embeddings from Ollama (bge-m3 by default). No API key,
    no per-call cost. Needs the Ollama app running and `ollama pull bge-m3` once.
    Batches are sent CONCURRENTLY (PAKSH_EMBED_CONCURRENCY) to cut wall-clock time
    on a backlog; results are re-assembled IN ORDER so vectors still line up 1:1
    with `texts`."""
    texts = list(texts)
    if not texts:
        return []
    B = EMBED_BATCH
    batches = [texts[k:k + B] for k in range(0, len(texts), B)]
    out = []
    if EMBED_CONCURRENCY > 1 and len(batches) > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=EMBED_CONCURRENCY) as ex:
            results = list(ex.map(_ollama_embed_batch, batches))  # order preserved
        done = 0
        for res in results:
            out.extend(res)
            done += len(res)
            if len(texts) > B:
                print("    embedded %d/%d  (Ollama %s x%d)"
                      % (done, len(texts), EMBED_MODEL, EMBED_CONCURRENCY), flush=True)
    else:
        for k, batch in enumerate(batches):
            out.extend(_ollama_embed_batch(batch))
            if len(texts) > B:
                print("    embedded %d/%d  (Ollama %s)"
                      % (min((k + 1) * B, len(texts)), len(texts), EMBED_MODEL), flush=True)
    return out


# ---- Cloudflare Workers AI (opt-in: same bge-m3, GPU-hosted) -----------------
CF_EMBED_MODEL = os.environ.get("PAKSH_CF_EMBED_MODEL", "@cf/baai/bge-m3")
EMBED_CF_BATCH = max(1, int(os.environ.get("PAKSH_CF_EMBED_BATCH", "100")))
_UA_CF = "paksh/1.0 (+https://paksh.news)"


def _cf_creds():
    """Cloudflare account id + API token from env / ai_keys.env. Loads ai_keys.env
    lazily (via ai_providers) so cluster.py never depends on it unless CF is used."""
    if not os.environ.get("CLOUDFLARE_ACCOUNT_ID") or not os.environ.get("CLOUDFLARE_API_TOKEN"):
        try:
            import ai_providers  # noqa: F401  (importing it loads ai_keys.env into os.environ)
        except Exception:
            pass
    return os.environ.get("CLOUDFLARE_ACCOUNT_ID"), os.environ.get("CLOUDFLARE_API_TOKEN")


def _cf_embed_batch(batch):
    """Embed ONE batch via Cloudflare Workers AI @cf/baai/bge-m3. float32 vectors."""
    acct, token = _cf_creds()
    if not acct or not token:
        raise RuntimeError(
            "Cloudflare embeddings need CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN "
            "in ai_keys.env (see ai_keys.example.env).")
    url = "https://api.cloudflare.com/client/v4/accounts/%s/ai/run/%s" % (acct, CF_EMBED_MODEL)
    payload = json.dumps({"text": list(batch)}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "User-Agent": _UA_CF})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        raise RuntimeError("Cloudflare AI HTTP %s: %s" % (e.code, detail)) from None
    if not data.get("success", True):
        raise RuntimeError("Cloudflare AI error: " + str(data.get("errors") or data)[:200])
    res = data.get("result", {}) or {}
    vecs = res.get("data") or res.get("response") or res.get("embeddings") or []
    if len(vecs) != len(batch):
        raise RuntimeError("Cloudflare returned %d vectors for %d inputs: %s"
                           % (len(vecs), len(batch), str(data)[:200]))
    return [np.asarray(v, dtype=np.float32) for v in vecs]


_cf_fell_back = False  # so we only warn once per run


def _cf_or_ollama_batch(batch):
    """Try Cloudflare; on ANY failure (quota/402, rate-limit/429, network) fall back
    to LOCAL Ollama for this batch. Safe because both are bge-m3 and produce the same
    vectors (verified cross-backend cosine ~1.0), so a mixed run stays consistent."""
    global _cf_fell_back
    try:
        return _cf_embed_batch(batch)
    except Exception as e:
        if not _cf_fell_back:
            print("    (Cloudflare unavailable: %s -> falling back to local Ollama)"
                  % str(e)[:90], flush=True)
            _cf_fell_back = True
        return _ollama_embed_batch(batch)


def _embed_via_cloudflare(texts):
    """OPT-IN: embeddings from Cloudflare Workers AI - the SAME bge-m3 model as local
    Ollama, GPU-hosted (free tier). Network-bound, so batches are sent concurrently.
    Falls back to Ollama per-batch if CF errors or hits its daily quota, so a run
    never breaks. Confirm CF matches Ollama with `py cluster.py --verify-cf` first."""
    texts = list(texts)
    if not texts:
        return []
    B = EMBED_CF_BATCH
    batches = [texts[k:k + B] for k in range(0, len(texts), B)]
    out = []
    if EMBED_CONCURRENCY > 1 and len(batches) > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=EMBED_CONCURRENCY) as ex:
            for res in ex.map(_cf_or_ollama_batch, batches):     # order preserved
                out.extend(res)
                if len(texts) > B:
                    print("    embedded %d/%d  (Cloudflare bge-m3 x%d)"
                          % (len(out), len(texts), EMBED_CONCURRENCY), flush=True)
    else:
        for k, batch in enumerate(batches):
            out.extend(_cf_or_ollama_batch(batch))
            if len(texts) > B:
                print("    embedded %d/%d  (Cloudflare bge-m3)"
                      % (min((k + 1) * B, len(texts)), len(texts)), flush=True)
    return out


def verify_cf(n=12):
    """Confirm Cloudflare bge-m3 vectors match local Ollama bge-m3 closely enough to
    share ONE clustering space. Embeds the same English+Hindi samples via both and
    reports (a) cross-backend self-cosine (want ~1.0) and (b) how well the pairwise
    geometry agrees (want |Δcos| small). Run this BEFORE switching a live corpus."""
    samples = [
        "India's central bank holds interest rates steady amid inflation concerns.",
        "The Supreme Court issued a landmark ruling on privacy rights.",
        "Monsoon rains flood several districts in Kerala.",
        "Parliament passed the new data protection bill after a long debate.",
        "भारत ने अंतरराष्ट्रीय व्यापार समझौते पर हस्ताक्षर किए।",
        "दिल्ली में वायु प्रदूषण गंभीर स्तर पर पहुंच गया।",
        "A major cricket tournament final drew record television viewership.",
        "A technology company unveiled a new artificial intelligence model.",
        "Farmers protested over crop prices in several northern states.",
        "Global oil prices rose after major producers announced supply cuts.",
        "शेयर बाज़ार में तेज़ गिरावट दर्ज की गई।",
        "Heavy snowfall disrupted flights across the capital region.",
    ][:n]

    def cos(a, b):
        d = (np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
        return float(np.dot(a, b) / d)

    print("Verifying Cloudflare bge-m3 against local Ollama bge-m3 (%d samples)...\n" % len(samples))
    ol = _embed_via_ollama(samples)
    cf = _cf_embed_batch(samples)   # PURE Cloudflare (no fallback), so the check is honest
    self_cos = [cos(ol[i], cf[i]) for i in range(len(samples))]
    diffs = [abs(cos(ol[i], ol[j]) - cos(cf[i], cf[j]))
             for i in range(len(samples)) for j in range(i + 1, len(samples))]
    mn, avg = min(self_cos), sum(self_cos) / len(self_cos)
    mx_pair, avg_pair = max(diffs), sum(diffs) / len(diffs)
    print("  dims: Ollama=%d  Cloudflare=%d" % (len(ol[0]), len(cf[0])))
    print("  cross-backend self-cosine : min=%.4f  avg=%.4f   (want ~1.0)" % (mn, avg))
    print("  pairwise geometry |Δcos|  : max=%.4f  avg=%.4f   (want < ~0.03)" % (mx_pair, avg_pair))
    ok = (mn >= 0.98 and mx_pair <= 0.05)
    print("\n  VERDICT: " + (
        "SAFE - Cloudflare shares Ollama's bge-m3 space. You can set PAKSH_BACKEND=cloudflare."
        if ok else
        "MISMATCH - do NOT switch on the existing corpus; the vectors differ enough to hurt clustering."))
    return ok


def _raw_embedder():
    """The active backend's raw (uncached) embedder."""
    if BACKEND == "ollama":
        return _embed_via_ollama
    if BACKEND == "cloudflare":
        return _embed_via_cloudflare
    return _embed_via_api


def cached_embedder(texts, raw_embedder=_embed_via_api):
    """Embed `texts`, reusing vectors already stored in paksh.db so each article is
    only ever sent to the embedding API ONCE. Only genuinely new texts cost a call;
    everything seen in a previous run is loaded from the cache. If the cache is
    unavailable for any reason, it transparently embeds everything."""
    if not texts:
        return []
    keys = [_emb_key(t) for t in texts]
    try:
        import database
        cached_bytes = database.embeddings_get(keys)
    except Exception:
        cached_bytes = {}
    cache = {k: np.frombuffer(b, dtype=np.float32).copy() for k, b in cached_bytes.items()}

    miss_idx, seen = [], set()
    for i, k in enumerate(keys):
        if k not in cache and k not in seen:
            miss_idx.append(i)
            seen.add(k)

    if miss_idx:
        new_vecs = raw_embedder([texts[i] for i in miss_idx])
        store = {}
        for i, v in zip(miss_idx, new_vecs):
            arr = np.asarray(v, dtype=np.float32)
            cache[keys[i]] = arr
            store[keys[i]] = arr.tobytes()
        try:
            import database
            database.embeddings_put(store)
        except Exception:
            pass

    return [cache[k] for k in keys]


def default_embedder(texts):
    """Active backend's embeddings WITH a persistent DB cache (re-runs don't
    re-embed). bge-m3 locally by default; Gemini if PAKSH_BACKEND=gemini."""
    return cached_embedder(texts, _raw_embedder())


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


def cluster_vectors(vecs, join=None, merge=None, kw=None, langs=None):
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
    if join is None:
        join = JOIN_THRESHOLD
    if merge is None:
        merge = MERGE_THRESHOLD
    clusters = []  # each: {"members":[int], "centroid":vec, "seedkw":set, "seedlang":str|None}

    def shared(i, c):
        return 0 if kw is None else len(kw[i] & c["seedkw"])

    def eligible(i, c, sim):
        if sim < join:
            return False
        same_lang = (langs is None) or (langs[i] == c["seedlang"])
        n = shared(i, c)
        if same_lang:
            if kw is None:
                return True
            if n >= MIN_SHARED:
                return True
            if n >= 1:   # one shared keyword is enough IF strongly similar to the cluster's SEED (drift-proof)
                seed_sim = float(np.dot(vecs[i], vecs[c["members"][0]]))
                return seed_sim >= STRONG_SIM
            return False
        return sim >= HIGH_SIM or n >= MIN_SHARED   # cross-language: similarity OR a shared name

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
                n = 0 if kw is None else len(clusters[i]["seedkw"] & clusters[j]["seedkw"])
                if same_lang:
                    ok = kw is None or n >= MIN_SHARED
                else:
                    ok = csim >= HIGH_SIM or n >= MIN_SHARED
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
        seen_titles = set()
        for i in idxs:
            norm_title = re.sub(r"\s+", " ", (articles[i].get("title") or "").strip().lower())
            if norm_title and norm_title in seen_titles:
                continue   # exact same headline from this outlet -> drop the repeat
            if all(float(np.dot(vecs[i], vecs[j])) < DUP_THRESHOLD for j in chosen):
                chosen.append(i)
                seen_titles.add(norm_title)
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
        _klangs = [langs[i] for i in kept]
        out.append({
            "ids": [r["id"] for r in rows],
            "size": len(rows),
            "source_count": len({r["source"] for r in rows}),
            "sources": sorted({r["source"] for r in rows}),
            "languages": sorted({r["language"] for r in rows}),
            "sample_title": rows[0]["title"] if rows else "",
            "centroid": _recentroid(vecs, kept) if kept else None,
            "keywords": ((set().union(*[kw[i] for i in kept]) if kept else set())
                         - _GENERIC_KW - _OUTLET_KW),
            "lang": (max(set(_klangs), key=_klangs.count) if _klangs else "en"),
        })
    out.sort(key=lambda d: (-d["source_count"], -d["size"]))
    return out


def cluster_articles(articles, embedder=None):
    """Drop-in for analyze.py's old PASS1: returns id-lists for clusters covered
    by MIN_SOURCES+ distinct outlets."""
    return [d["ids"] for d in cluster_with_details(articles, embedder)
            if d["source_count"] >= MIN_SOURCES]


# ------------------------- cross-cycle merge primitives -------------------------

def find_duplicate_event_groups(events, sim=None, min_shared=None, hi_sim=None,
                               kw_per_share=None, min_frac=None):
    """Union-find over recent events: group events that are the SAME story fragmented
    across cycles (e.g. several 'Venezuela earthquake' events). Same conservative gate
    as the cross-cycle merge, but the diffuse guard scales by the LARGER of the two
    keyword sets so a polluted magnet event can't drag focused events into it.
    `events` are dicts with 'centroid' (unit vec), 'keywords' (set), 'lang'.
    Returns a list of groups (each a list of >=2 event dicts)."""
    sim = XMERGE_SIM if sim is None else sim
    min_shared = XMERGE_MIN_SHARED if min_shared is None else min_shared
    hi = HIGH_SIM if hi_sim is None else hi_sim
    min_frac = XMERGE_MIN_FRAC if min_frac is None else min_frac
    n = len(events)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(n):
        ci = events[i].get("centroid")
        if ci is None:
            continue
        ki, li = events[i].get("keywords", set()), events[i].get("lang")
        for j in range(i + 1, n):
            cj = events[j].get("centroid")
            if cj is None:
                continue
            s = float(np.dot(ci, cj))
            if s < sim:
                continue
            kj = events[j].get("keywords", set())
            shared = ki & kj
            frac = len(shared) / max(len(ki), len(kj), 1)
            same = (li == events[j].get("lang"))
            # real duplicates share a real fraction of the larger set; a focused event
            # whose words merely all sit inside a grab-bag scores a tiny fraction.
            ok = (len(shared) >= min_shared and frac >= min_frac)
            if not same and not ok:
                ok = (s >= hi and len(shared) >= min_shared)
            if ok:
                union(i, j)

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(events[i])
    return [g for g in groups.values() if len(g) > 1]


def cluster_centroid(texts, embedder=None):
    """Unit centroid of the (cached) embeddings of `texts`. Used to give an EXISTING
    event a vector from its member articles - free for text already embedded."""
    texts = list(texts)
    if not texts:
        return None
    embedder = embedder or default_embedder
    vecs = _normalize(embedder(texts))
    vecs = np.asarray(vecs, dtype=float)
    return _recentroid(vecs, list(range(len(vecs))))


def merge_keywords(articles):
    """Union of discriminating keywords across an event's/cluster's articles, with
    the too-generic terms removed - so a merge can only be gated on a SPECIFIC token."""
    kw = set()
    for a in articles:
        kw |= _keywords(a)
    return kw - _GENERIC_KW - _OUTLET_KW


def match_clusters_to_events(clusters, events, sim=None, min_shared=None, hi_sim=None,
                            kw_per_share=None):
    """For each NEW cluster, pick the single best RECENT event to fold it into - or
    nothing. Conservative: centroid cosine >= `sim` AND a keyword gate (>= min_shared
    specific shared words, or very-high similarity with >=1 shared / cross-lingual).
    Inputs are dicts carrying 'centroid' (unit vec), 'keywords' (set), 'lang'.
    Returns [{'cluster', 'event', 'sim', 'shared'}], one entry per matched cluster."""
    sim = XMERGE_SIM if sim is None else sim
    min_shared = XMERGE_MIN_SHARED if min_shared is None else min_shared
    hi = HIGH_SIM if hi_sim is None else hi_sim
    kps = XMERGE_KW_PER_SHARE if kw_per_share is None else kw_per_share
    matches = []
    for c in clusters:
        cc = c.get("centroid")
        if cc is None:
            continue
        ckw, clang = c.get("keywords", set()), c.get("lang")
        best, best_sim, best_shared = None, -1.0, set()
        for e in events:
            ec = e.get("centroid")
            if ec is None:
                continue
            s = float(np.dot(cc, ec))
            if s < sim:
                continue
            e_kw = e.get("keywords", set())
            shared = ckw & e_kw
            same_lang = (clang == e.get("lang"))
            need = max(min_shared, (len(e_kw) + kps - 1) // kps) if kps else min_shared
            if same_lang:
                ok = len(shared) >= need
            else:
                ok = (s >= hi) or (len(shared) >= need)
            if ok and s > best_sim:
                best, best_sim, best_shared = e, s, shared
        if best is not None:
            matches.append({"cluster": c, "event": best, "sim": best_sim, "shared": best_shared})
    return matches


def main():
    import sys
    if "--verify-cf" in sys.argv:
        verify_cf()
        return
    from database import init_db, get_unclustered_articles
    from ingest import is_junk
    init_db()
    articles = [a for a in get_unclustered_articles() if not is_junk(a.get("title", ""))]
    print("\n%d unclustered articles (after junk filter)" % len(articles))
    if len(articles) < 2:
        print("Not enough yet - run `python ingest.py` first.\n")
        return
    use_lex = "--lexical" in sys.argv
    if use_lex:
        print("Backend: OFFLINE lexical embedder (within-language only, rough preview).")
    else:
        print("Backend: %s  (model: %s)" % (BACKEND.upper(), EMBED_MODEL))
        if BACKEND == "ollama":
            print("  -> embeddings run locally via Ollama; first run is slow, then cached.")
    try:
        details = cluster_with_details(articles, lexical_embedder if use_lex else None)
    except RuntimeError as e:
        print("\n" + str(e) + "\n")
        return
    multi = [d for d in details if d["source_count"] >= MIN_SOURCES]
    print("\n%d clusters, %d with %d+ outlets (marked *):\n"
          % (len(details), len(multi), MIN_SOURCES))
    for d in details:
        flag = "*" if d["source_count"] >= MIN_SOURCES else " "
        print(" %s [%d outlets · %d art · %s] %s"
              % (flag, d["source_count"], d["size"],
                 "/".join(d["languages"]), d["sample_title"][:78]))
    print("\n* = becomes an event. If grouping looks loose or sparse, tune the "
          "thresholds with `python calibrate.py`.\n")


if __name__ == "__main__":
    main()