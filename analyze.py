"""
analyze.py
----------
STEP 2 - the brain. Powered by Google Gemini (free tier).

Run with:   python analyze.py

PASS 1 (clustering): handled by cluster.py (embedding-based, cross-lingual),
                     with an LLM grouper kept here as a fallback.
PASS 2 (analysis):   for each event covered by 2+ outlets, produce a neutral,
                     bilingual (English + Hindi) brief, a topic, per-side framing,
                     per-outlet notes, divergence & omissions.

Hardening in this version:
  * Gemini JSON mode + tolerant parser + one retry  -> far fewer parse failures
  * bilingual brief: English neutral brief AND a faithful Hindi translation,
    so a cluster mixing English + Hindi still yields one clean brief in each
  * strict neutrality rules (attribute claims, no invented facts, no side's framing)
  * graceful degradation: if the model fails, still emit the event with correct
    coverage counts + source list (just without the written brief)

Lean is read from sources.py (YOUR config), never guessed by the AI.
The hero image is taken from the source articles (RSS), never invented.
"""

import json
import re
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

# Windows stdout defaults to cp1252 and can't encode Devanagari (Hindi) titles;
# printing one raises UnicodeEncodeError and kills the run. Force UTF-8 output.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from database import (
    init_db, get_unclustered_articles, get_articles_by_ids,
    assign_articles_to_event, insert_event,
    get_event, get_event_articles, update_event, get_recent_events_for_merge,
)
from sources import LEAN_BY_SOURCE, INTERNATIONAL_SOURCES, OWNER_BY_SOURCE
import cluster

# ---- LLM backend for the bilingual summary --------------------------------
# "ollama" = LOCAL text model (default; free, no API key, no bill)
# "gemini" = Google Gemini (needs API key + billing)
# "hybrid" = top LLM_LOCAL_BUDGET events local (free), the rest via Gemini.
# "pool"   = round-robin + fallback across the FREE provider pool (Groq, Cerebras,
#            Gemini, ...) in ai_providers.py. Fastest option; keys go in
#            ai_keys.env. Add providers/keys yourself - no code changes needed.
# Flip with PAKSH_LLM_BACKEND; pick the local model with PAKSH_LLM_MODEL.
LLM_BACKEND = os.environ.get("PAKSH_LLM_BACKEND", "ollama").lower()
OLLAMA_URL  = os.environ.get("OLLAMA_URL", "http://localhost:11434")
# Per-backend models, so hybrid can drive BOTH at once. On a CPU-only / integrated-
# GPU laptop a small local model (llama3.2:3b) keeps the local tier fast.
OLLAMA_MODEL = os.environ.get("PAKSH_LLM_LOCAL_MODEL",
                              os.environ.get("PAKSH_LLM_MODEL", "qwen3.5:4b"))
_gem_default = "gemini-2.5-flash" if LLM_BACKEND == "gemini" else "gemini-2.5-flash-lite"
GEMINI_MODEL = os.environ.get("PAKSH_LLM_GEMINI_MODEL",
                              os.environ.get("PAKSH_LLM_MODEL", _gem_default))
MODEL = GEMINI_MODEL if LLM_BACKEND == "gemini" else OLLAMA_MODEL
# hybrid only: how many top events the free local model takes before Gemini overflow.
LLM_LOCAL_BUDGET = int(os.environ.get("PAKSH_LLM_LOCAL_BUDGET", "8"))

LEAN_ORDER = ["left", "center", "right"]
# Two-tier summarization: the top LLM_EVENT_BUDGET events (ranked by rated
# breadth) get a real neutral LLM summary; everything else up to
# MAX_EVENTS_PER_RUN is published with an instant extractive summary (no model
# call). This decouples "events published" from "slow LLM calls", so a run can
# publish hundreds while only making a few dozen model calls.
LLM_EVENT_BUDGET = int(os.environ.get(
    "PAKSH_LLM_BUDGET", "30" if LLM_BACKEND == "ollama" else "300"))
# How many summaries to run AT ONCE. The summary call is the slow step and (for a
# network backend) is I/O-bound, so a small thread pool cuts wall-clock ~N-fold and
# lets the budget go up cheaply. Local Ollama on CPU is compute-bound -> default 1
# (a GPU user can raise it); Gemini -> 6. Override with PAKSH_LLM_CONCURRENCY.
LLM_CONCURRENCY = int(os.environ.get(
    "PAKSH_LLM_CONCURRENCY", "1" if LLM_BACKEND == "ollama" else "8"))
#   ^ top events that get a full LLM brief + framing. Cheap/fast on Gemini, so we
#     default much higher there; slow on local Ollama, so stay at 30. Override
#     with PAKSH_LLM_BUDGET.
MAX_EVENTS_PER_RUN = 500       # total events published per run (extractive is cheap)
MIN_SOURCES_PER_EVENT = 2
# Cross-cycle merge: fold clusters that continue a recent event INTO that event
# instead of spawning a duplicate. On by default; PAKSH_CROSS_MERGE=0 disables it.
# PAKSH_MERGE_RESUMMARISE=1 re-runs the LLM brief on a merged event (off = cheap
# arithmetic recount only, no model call).
MERGE_ENABLED = os.environ.get("PAKSH_CROSS_MERGE", "1") != "0"
MERGE_RESUMMARISE = os.environ.get("PAKSH_MERGE_RESUMMARISE", "0") == "1"
MIN_RATED_PER_EVENT = 2         # an event needs >=2 RATED outlets (real bias bar);
                                # unrated/syndication outlets add breadth, not events
MAX_ARTICLES_PER_EVENT = 12     # cap tokens per event
SUMMARY_TRUNC = 300             # chars of each article summary fed to the model
# Backfill safety: when ON, a new event is dated to its NEWEST member article's publish
# date instead of "now", so a run over weeks-old backlog doesn't shove stale stories to
# the top of the created_at-DESC homepage as if they were breaking news. OFF by default
# -> the live pipeline is unchanged and genuinely fresh events still get "now". Turn ON
# only for historical backfill runs:  $env:PAKSH_BACKDATE="1"
BACKDATE = os.environ.get("PAKSH_BACKDATE", "0") == "1"

TOPICS = ["Politics", "Economy", "International", "Sports", "Crime & Law",
          "Science & Tech", "Health", "Entertainment", "Environment", "Society"]


# ------------------------------ model calls ------------------------------

def _strip_think(text: str) -> str:
    """Remove any <think>...</think> reasoning a thinking model leaks into output."""
    if not text:
        return text
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I)
    text = re.sub(r"^.*?</think>", "", text, flags=re.S | re.I)   # stray closing tag
    return text.strip()


def _ollama_generate(prompt: str, as_json: bool) -> str:
    # qwen3.x "thinks" before answering, which (under JSON mode) returns an EMPTY
    # body. Belt-and-suspenders: think:false (API switch) + /no_think (Qwen prompt
    # switch) + strip any <think> that still leaks.
    body = {"model": OLLAMA_MODEL, "prompt": prompt + "\n\n/no_think", "stream": False,
            "think": False,
            "options": {"temperature": 0.2, "num_predict": 1500}}
    if as_json:
        body["format"] = "json"          # force valid JSON out of the local model
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL + "/api/generate", data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return _strip_think(json.loads(r.read().decode("utf-8")).get("response", ""))
    except urllib.error.URLError as e:
        raise RuntimeError(
            "Could not reach Ollama at " + OLLAMA_URL + ". Is it running?\n"
            "  Open the Ollama app, then run once:  ollama pull " + OLLAMA_MODEL + "\n"
            "Original error: " + str(e)) from None


def _gemini_generate(prompt: str, as_json: bool) -> str:
    from google import genai
    from google.genai import types
    import time
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    client = genai.Client(api_key=key)
    cfg = None
    if as_json:
        # gemini-2.5-flash "thinks" by default and can spend the whole budget; disable it.
        cfg_kwargs = dict(response_mime_type="application/json",
                          temperature=0.2, max_output_tokens=8192)
        try:
            cfg = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0), **cfg_kwargs)
        except Exception:
            cfg = types.GenerateContentConfig(**cfg_kwargs)
    # under concurrency a few calls may hit a transient 429/503 - back off and retry
    for attempt in range(3):
        try:
            if cfg is None:
                return client.models.generate_content(model=GEMINI_MODEL, contents=prompt).text
            return client.models.generate_content(model=GEMINI_MODEL, contents=prompt, config=cfg).text
        except Exception as e:
            transient = any(k in str(e) for k in
                            ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE"))
            if transient and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise


def _generate(prompt: str, as_json: bool, backend=None) -> str:
    backend = backend or LLM_BACKEND
    if backend == "ollama":
        return _ollama_generate(prompt, as_json)
    if backend == "pool":
        # Round-robin + fallback across the free provider pool (Groq, Cerebras,
        # Gemini, ...). See ai_providers.py; keys live in ai_keys.env.
        from ai_providers import pool_generate
        return pool_generate(prompt, as_json)
    return _gemini_generate(prompt, as_json)


def _generate_text(prompt: str, backend=None) -> str:
    return _generate(prompt, as_json=False, backend=backend)


def _call_json(prompt: str, retries: int = 1, backend=None):
    """Generate JSON via the active backend, tolerant-parse it, retry once.
    If the backend itself is unreachable, raise immediately so the caller can
    fall back to an extractive summary rather than retry a dead server."""
    last = None
    for _ in range(retries + 1):
        try:
            return _extract_json(_generate(prompt, as_json=True, backend=backend))
        except RuntimeError:
            raise
        except Exception as e:
            last = e
    raise ValueError("model/JSON failure: %s" % last)


def _repair_json(t: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", t)   # drop trailing commas


def _extract_json(text: str):
    """Tolerant parse: handle code fences, surrounding prose, trailing commas."""
    if not text:
        raise ValueError("empty response")
    t = text.strip()
    t = re.sub(r"^```(?:json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    start = min((i for i in (t.find("{"), t.find("[")) if i != -1), default=-1)
    end = max(t.rfind("}"), t.rfind("]"))
    if start != -1 and end != -1 and end > start:
        t = t[start:end + 1]
    return json.loads(_repair_json(t))


def lean_of(name):
    # Foreign wires (Reuters, AP, BBC, Guardian, Al Jazeera, ...) add coverage and
    # framing, but their lean is set on their HOME-market spectrum, not India's, so
    # they sit in a non-voting "international" tier and never move the India bias bar.
    if name in INTERNATIONAL_SOURCES:
        return "international"
    # Unknown outlets (e.g. the GDELT long tail) are UNRATED: they add coverage
    # and clustering density but never vote in the Left/Centre/Right bias bar.
    return LEAN_BY_SOURCE.get(name, "unrated")


# ------------------------------ clustering (PASS 1) ------------------------------

def _cluster_articles_llm(articles):
    """Fallback grouper: ask the LLM to group. Used only if embeddings fail."""
    if len(articles) < 2:
        return []
    lines = [f'ID {a["id"]} | {a["source"]} ({a["language"]}) | {a["title"]} | {(a["summary"] or "")[:160]}'
             for a in articles]
    prompt = f"""You are grouping news articles that report THE SAME real-world event.

Articles from different Indian outlets, English and Hindi. Group ONLY those clearly
about the same specific event. A group is only worth keeping if it has articles from
2+ different outlets. Leave ungroupable articles out.

Return ONLY valid JSON: {{"clusters": [{{"article_ids": [1,2]}}]}}

Articles:
{chr(10).join(lines)}
"""
    try:
        data = _extract_json(_generate_text(prompt))
    except Exception as e:
        print(f"    clustering parse error: {e}")
        return []
    clusters, valid = [], {a["id"] for a in articles}
    for c in data.get("clusters", []):
        ids = [i for i in c.get("article_ids", []) if i in valid]
        rows = [a for a in articles if a["id"] in ids]
        if len(ids) >= 2 and len({a["source"] for a in rows}) >= MIN_SOURCES_PER_EVENT:
            clusters.append(ids)
    return clusters


def cluster_articles(articles):
    """Group same-event articles. Embedding-based first (robust + cross-lingual
    via cluster.py); falls back to the LLM grouper only if embeddings error out."""
    if len(articles) < 2:
        return []
    try:
        return cluster.cluster_articles(articles)
    except Exception as e:
        print(f"    embedding clustering unavailable ({e}); using LLM fallback")
        return _cluster_articles_llm(articles)


# ------------------------------ analysis (PASS 2) ------------------------------

_GENERIC_TITLE = re.compile(
    r"(no new coverage|provided for analysis|no coverage provided|nothing to analyse|"
    r"multiple\s+(\w+\s+){0,2}(outlets?|incidents?|events?|reports?|stories|articles?)|"
    r"diverse\s+(events?|topics?|news|stories)|various\s+(incidents?|events?|topics?)|"
    r"daily\s+(news\s+)?(roundup|digest|wrap|update))", re.I)


def _looks_generic(title) -> bool:
    """True for placeholder/refusal headlines a model emits for an empty or mixed
    cluster ('No new coverage provided for analysis', 'Multiple outlets cover diverse
    events') - we reject these so a real article headline is used instead."""
    t = (title or "").strip()
    return bool(t) and bool(_GENERIC_TITLE.search(t))


def build_prompt(articles) -> str:
    _LEANWORD = {"left": "left-leaning", "center": "centrist",
                 "right": "right-leaning", "unrated": "unrated",
                 "international": "international wire"}
    # Balance the budget across leans: guarantee up to MIN_PER_LEAN articles from EACH
    # covered lean before filling the rest rated-first, so a side whose articles sort
    # past the cap is never dropped from the prompt (which would leave the model with
    # no framing for a side the coverage list still shows).
    MIN_PER_LEAN = 2
    by_lean = {}
    for a in articles:
        by_lean.setdefault(lean_of(a["source"]), []).append(a)
    picked, seen = [], set()
    for lean in ("left", "center", "right", "international", "unrated"):
        for a in by_lean.get(lean, [])[:MIN_PER_LEAN]:
            if id(a) not in seen and len(picked) < MAX_ARTICLES_PER_EVENT:
                picked.append(a); seen.add(id(a))
    rest = sorted((a for a in articles if id(a) not in seen),
                  key=lambda a: lean_of(a["source"]) == "unrated")
    for a in rest:
        if len(picked) >= MAX_ARTICLES_PER_EVENT:
            break
        picked.append(a); seen.add(id(a))
    blocks = [
        f'OUTLET: {a["source"]}  [lean: {_LEANWORD[lean_of(a["source"])]}, language: {a["language"]}]\n'
        f'HEADLINE: {a["title"]}\nSUMMARY: {(a["summary"] or "(none)")[:SUMMARY_TRUNC]}'
        for a in picked
    ]
    return f"""You are a neutral news engine for "Paksh", a media-transparency
tool for India. Below is coverage of ONE event from several Indian outlets
(English and Hindi), each tagged with its editorially-assigned political lean.
Produce (1) a DIRECT, substantive neutral account, and (2) a CONCRETE, attributed
description of how each side is framing the story.

WRITE WITH SUBSTANCE, NOT HEDGING:
- State plainly what actually happened. Lead with the concrete facts: who did what,
  when, where, and the specific numbers, names, claims and decisions in the coverage.
- Strip filler, PR language and empty hedging ("sources say", "it is believed",
  "in a significant development"). Strip jargon; use plain words.
- Do NOT pad with vague abstractions ("various developments", "the situation
  continues to evolve"). Every sentence must carry a specific fact.

STRICT NEUTRALITY - never cross these:
- Use ONLY facts and claims present in the coverage below. Never invent facts,
  quotes, numbers, names, causes or consequences.
- Describe ONLY what the coverage says. Do NOT add downstream consequences ("this
  could lead to X"), motives the outlets did not state, or any praise or blame the
  outlets did not themselves make.
- Give NO verdict on who is right and do NOT fact-check. Purely descriptive.
- Attribute every contested claim to who makes it ("the government said", "the
  opposition alleged", "police claimed") rather than stating it as fact.
- If outlets conflict, state the disagreement neutrally; do not pick a winner.
- The neutral title and summary must not adopt any outlet's loaded words or framing,
  and must NOT name individual publications - describe the event, not who reported it.

FRAMING - a per-side BULLET SUMMARY (like Ground News), concrete and specific:
- For EACH lean, write 3-5 SHORT bullet points describing how that side's outlets
  COLLECTIVELY cover the story: the specific claims, angles, numbers, names and emphases
  they lead with, stress or repeat. Each bullet is ONE crisp point WITH the detail cited.
- Model the substance (not the length) on:
    "Framed the funding row as a national-security concern, stressing the foreign-donation angle."
    "Repeated the opposition's demand for a court-monitored audit."
  NOT vague ("emphasised different aspects", "focused on the situation").
- Refer to each side COLLECTIVELY ("...outlets"). Never name, quote or single out any
  publication by name in a bullet.
- Draw ONLY on the headlines/summaries below; never invent a position, number, quote,
  cause or consequence. Attribute contested claims to who makes them.
- If a side's coverage just tracks the neutral facts with no distinct frame, say so in a
  SINGLE bullet (e.g. "Largely reported the events without a distinct frame"). Do NOT
  manufacture a difference that is not in the text.
- If a lean has no outlet in the coverage, set its framing to an empty array [].

BILINGUAL OUTPUT IS MANDATORY. Write ENGLISH first, then a faithful, natural HINDI
(Devanagari) translation of EVERY field. The Hindi fields (title_hi, summary_hi,
summary_points_hi, and each side of framing_hi) are REQUIRED and must NEVER be empty,
omitted or left in English - always provide the Hindi translation. A response missing
any Hindi field, or with an English value in a _hi field, is INVALID.

Return ONLY a JSON object with these keys:
{{
  "title": "neutral English headline IN ENGLISH ONLY (never Hindi/Devanagari), max ~12 words, no loaded words, no publication named",
  "summary": "a direct neutral account IN ENGLISH ONLY, in 4-6 sentences: exactly what happened, the specific facts and figures, the key attributed claims, and the concrete context - no filler, no hedging, no publication named",
  "summary_points": ["4-6 short, specific neutral points IN ENGLISH ONLY, each a concrete fact"],
  "title_hi": "REQUIRED - Hindi (Devanagari) translation of the title, never empty, Hindi script only",
  "summary_hi": "REQUIRED - Hindi (Devanagari) translation of the summary, never empty, Hindi script only",
  "summary_points_hi": ["REQUIRED - Hindi (Devanagari) translations of the points, same order, never empty, Hindi script only"],
  "framing": {{
    "left": ["IN ENGLISH ONLY (never Hindi/Devanagari) - 3-5 short bullet points on how left-leaning outlets collectively cover it; each a concrete claim/number/emphasis, no outlet named; [] if no left outlet"],
    "center": ["IN ENGLISH ONLY - 3-5 short bullets on how centrist coverage collectively frames it, same rules; [] if none"],
    "right": ["IN ENGLISH ONLY - 3-5 short bullets on how right-leaning outlets collectively frame it, same rules; [] if none"]
  }},
  "framing_hi": {{ "left": ["IN HINDI/DEVANAGARI ONLY (never English) - same points as framing.left, same order"], "center": ["Hindi/Devanagari only, same as framing.center"], "right": ["Hindi/Devanagari only, same as framing.right"] }},
  "topic": "exactly one of {TOPICS}. International = events occurring mainly outside India (foreign politics, wars, foreign disasters). Environment = climate, weather, pollution, natural disasters inside India. Crime & Law = courts, police, crime. Choose the single best fit by the story's MAIN subject, not an incidental mention.",
  "region": "India or World - 'India' if the story is primarily about India or has a direct India angle (Indian people, government, economy, society, courts, prices, sport teams); 'World' if it is mainly about events in other countries"
}}

COVERAGE:
{(chr(10) + "---" + chr(10)).join(blocks)}
"""


# A side needs at least this many DISTINCT OWNERS (the same "unique coverage" the bias bar
# counts) before we synthesise its bullet summary. Below it, the UI shows "Not enough unique
# coverage to create a summary" for that side - so a lone outlet never stands in for a whole
# wing, and a genuine blindspot reads as one. Editorial knob: raise/lower to taste.
MIN_SIDE_OWNERS = 2

def _clean_framing(raw_framing, coverage):
    """Normalise per-side framing to a LIST of clean bullet points, and keep a side ONLY
    when it has enough unique coverage (>= MIN_SIDE_OWNERS distinct owners). This stops the
    model fabricating a side's framing out of nothing and stops one outlet speaking for a
    whole wing. Accepts either a list of bullets (preferred) or a legacy string (wrapped)."""
    fr = raw_framing if isinstance(raw_framing, dict) else {}
    out = {}
    for side in LEAN_ORDER:
        if coverage.get(side, {}).get("count", 0) < MIN_SIDE_OWNERS:
            continue
        val = fr.get(side)
        if isinstance(val, list):
            bullets = [b.strip() for b in val if isinstance(b, str) and b.strip()]
        elif isinstance(val, str):
            bullets = [val.strip()] if val.strip() else []
        else:
            bullets = []
        bullets = [b[:400] for b in bullets][:6]   # cap bullet length + count
        if bullets:
            out[side] = bullets
    return out


def has_framing(value) -> bool:
    """True if a per-side framing value carries real text. Tolerates BOTH the current
    list-of-bullets shape and the legacy single-string shape, so every consumer
    (reframe/audit/stats) can test emptiness without crashing on the other shape."""
    if isinstance(value, list):
        return any(isinstance(x, str) and x.strip() for x in value)
    return bool(isinstance(value, str) and value.strip())


def postprocess(raw, articles) -> dict:
    """Turn the model's (parsed) output + the articles into the stored event.
    Pure function - no network - so it is unit-testable. The neutral brief comes
    from the model; the bias breakdown is pure arithmetic on OUR fixed lean
    labels (no AI decides bias)."""
    raw = raw or {}
    for a in articles:
        a["lean"] = lean_of(a["source"])
    hero = next((a.get("image_url") for a in articles if a.get("image_url")), "")

    # source list: outlet, its OWNER, fixed lean, language, link, and its headline.
    # `owner` lets the UI group co-owned mastheads (Times of India + Navbharat Times)
    # and show WHY they count as one vote.
    sources_out = []
    for a in articles:
        sources_out.append({
            "source": a["source"], "owner": OWNER_BY_SOURCE.get(a["source"], a["source"]),
            "lean": a["lean"], "language": a["language"],
            "url": a["url"], "headline": a["title"],
        })

    # coverage = ONE VOTE PER OWNER on each side. Co-owned mastheads (e.g. The Times
    # of India + Navbharat Times, both Times Group) count ONCE, never per masthead
    # and never per article. `count` is the vote (distinct OWNERS); `sources` keeps
    # every distinct masthead for display, and `owners` is the distinct owner list.
    # AI decides nothing here - this is pure arithmetic on OUR fixed lean + owner labels.
    coverage_out = {}
    for side in LEAN_ORDER:
        names = sorted({s["source"] for s in sources_out if s["lean"] == side})
        owners = sorted({OWNER_BY_SOURCE.get(n, n) for n in names})
        coverage_out[side] = {"count": len(owners), "sources": names, "owners": owners}
    # foreign wires: counted for breadth + shown as international coverage, never voting
    intl_names = sorted({s["source"] for s in sources_out if s["lean"] == "international"})
    coverage_out["international"] = {"count": len(intl_names), "sources": intl_names}
    # unrated outlets (GDELT long tail): counted for breadth, never for lean
    unrated_names = sorted({s["source"] for s in sources_out if s["lean"] == "unrated"})
    coverage_out["unrated"] = {"count": len(unrated_names), "sources": unrated_names}

    topic = raw.get("topic", "Society")
    if topic not in TOPICS:
        topic = "Society"

    region = raw.get("region")
    blob = " ".join([raw.get("title", ""), raw.get("summary", "")]
                    + [a.get("title", "") for a in articles])
    if region not in ("India", "World"):
        region = _guess_region(blob)
    # Keep WORLD news out of the National feed, WITHOUT yanking real India stories
    # out of it. India-first rule: any clear India angle in the text -> stays
    # "India" (this protects India-Pakistan/China stories, Bollywood, cricket,
    # Indian people/places abroad). Otherwise flip to "World" only when foreign
    # coverage actually DOMINATES - i.e. international-tier outlets are at least as
    # many as the Indian voting outlets (or it is foreign-outlet-only). Gating the
    # text signal by composition is what gives high precision: a story Indian media
    # covers heavily stays National even if it mentions a foreign country.
    has_india = bool(_INDIA_RE.search(blob))
    india_votes = sum(coverage_out[s]["count"] for s in LEAN_ORDER)
    intl_n = coverage_out["international"]["count"]
    foreign_dominant = (india_votes == 0 and intl_n > 0) or (intl_n >= max(1, india_votes))
    if not has_india and foreign_dominant and (_FOREIGN_RE.search(blob) or india_votes == 0):
        region = "World"

    points = raw.get("summary_points") or []
    degraded = not (raw.get("title") or raw.get("summary") or points)
    title = raw.get("title") or (articles[0]["title"] if articles else "Untitled event")

    return {
        "title": title,
        "summary": raw.get("summary", ""),
        "summary_points": points,
        "title_hi": raw.get("title_hi", ""),
        "summary_hi": raw.get("summary_hi", ""),
        "summary_points_hi": raw.get("summary_points_hi", []) or [],
        "framing": _clean_framing(raw.get("framing"), coverage_out),
        "framing_hi": _clean_framing(raw.get("framing_hi"), coverage_out),
        "topic": topic,
        "region": region,
        # Real-world publish time = the NEWEST member-article's publish date (RSS gives a
        # true timestamp; GDELT only a date). This is what the feed shows as "x ago" so the
        # label reflects when the NEWS happened, not when our pipeline last touched it. None
        # when nothing parses; every consumer falls back to created_at. Never affects bias.
        "published_at": _event_created_at(articles),
        "image_url": hero,
        "sources": sources_out,
        "coverage": coverage_out,
        "total_sources": len({s["source"] for s in sources_out}),
        "degraded": degraded,
        "summary_method": raw.get("summary_method", "llm"),
    }


def _first_sentences(text, n=2):
    """First n sentences of a blurb (handles the Hindi danda ।)."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return ""
    parts = re.split(r"(?<=[.!?।])\s+", t)
    return " ".join(parts[:n]).strip()


_TOPIC_HINTS = [
    ("Sports", ["cricket", "fifa", "world cup", "odi", "test match", "t20", "ipl",
                "football", "wicket", "batsman", "bowler", "tournament", "league",
                "olympic", "badminton", "tennis", "athletics", "medal", "tri-series",
                "innings", "fifty", "century", "ball", "क्रिकेट", "मैच", "वर्ल्ड कप",
                "फुटबॉल", "विकेट", "ओलंपिक", "फिफा", "रन", "शतक"]),
    ("Entertainment", ["film ", "movie", "actor", "actress", "bollywood", "box office",
                       " review", "trailer", "cinema", "फिल्म", "अभिनेता", "बॉलीवुड",
                       "मूवी", "रिव्यू"]),
    ("Economy", ["stock", "market", "sensex", "nifty", " ipo", "rupee", " gdp",
                 "inflation", " rbi", " sebi", "crore", "tariff", "trade deal",
                 "oil price", " gold", "silver", "investor", "economy", "शेयर",
                 "बाजार", "रुपया", "महंगाई", "सोना", "चांदी", "निवेश", "अर्थव्यवस्था",
                 "आईपीओ"]),
    ("Science & Tech", ["artificial intelligence", " ai ", "spacex", "satellite",
                        "smartphone", "iphone", "android", " chip", "software",
                        "startup", " 6g", " 5g", "तकनीक", "सैटेलाइट", "स्मार्टफोन"]),
    ("Health", ["hospital", "disease", "virus", " flu", "covid", "cancer", "vaccine",
                "nipah", "outbreak", "अस्पताल", "बीमारी", "वायरस", "स्वास्थ्य", "कैंसर"]),
    ("Environment", ["monsoon", "climate", "el niño", "el nino", "heatwave",
                     "rainfall", "pollution", "flood", "cyclone", "weather", "drought",
                     "wildfire", "landslide", "avalanche", "glacier", "emission",
                     "मानसून", "बारिश", "जलवायु", "बाढ़", "मौसम", "प्रदूषण", "भूस्खलन"]),
    ("Crime & Law", ["court", "supreme court", "high court", " fir", "arrest", "murder",
                     " rape", "police", " jail", "verdict", "accused", " probe", " cbi",
                     " ed ", "convict", "अदालत", "कोर्ट", "गिरफ्तार", "हत्या",
                     "बलात्कार", "पुलिस", "जेल", "आरोपी"]),
    ("International", [" us ", "u.s.", "iran", "israel", "pakistan", "china", "russia",
                       "ukraine", "trump", "putin", "zelensky", "gaza", "hamas", "hormuz",
                       "foreign", "bangladesh", "nepal", "sri lanka", "maldives", "bhutan",
                       "myanmar", "afghanistan", "taliban", "syria", "lebanon", "yemen",
                       "turkey", "türkiye", "qatar", "saudi", "dubai", "uae", "egypt",
                       "venezuela", "brazil", "mexico", "canada", "australia", "japan",
                       "korea", "taiwan", "france", "germany", "italy", "spain", "britain",
                       " uk ", "u.k.", "london", "washington", "europe", "european union",
                       " eu ", "nato", "united nations", " un ", "palestine", "ceasefire",
                       "अमेरिका", "ईरान", "इजरायल", "पाकिस्तान", "चीन", "रूस", "ट्रंप",
                       "यूक्रेन", "अफ़ग़ानिस्तान", "बांग्लादेश", "श्रीलंका", "फ़िलिस्तीन"]),
    ("Politics", [" bjp", "congress", " tmc", "modi", "election", " mla", " mp ",
                  "parliament", "minister", " cm ", "party", " poll", " vote",
                  "rajya sabha", "lok sabha", "चुनाव", "मोदी", "कांग्रेस", "भाजपा",
                  "विधायक", "सांसद", "सरकार"]),
]


# Whole-word matching, so 'iran' can't fire inside 'aspirant' or 'us' inside 'campus'.
_TOPIC_RE = [
    (topic, re.compile(r"(?<!\w)(?:" + "|".join(re.escape(k.strip()) for k in kws) + r")(?!\w)", re.I))
    for topic, kws in _TOPIC_HINTS
]


# Tie-break order when two topics score equally. Foreign + specific topics beat
# generic ones (a "Modi visits Iran" headline reads as International, not Politics).
_TOPIC_PRIORITY = {"International": 9, "Sports": 8, "Entertainment": 7, "Health": 6,
                   "Science & Tech": 5, "Crime & Law": 4, "Economy": 3,
                   "Environment": 2, "Politics": 1}

def _guess_topic(text: str) -> str:
    """Best-effort topic from keywords. Scores every topic by how many distinct
    keyword hits it has and picks the strongest, breaking ties by priority - so a
    story that merely mentions 'market' in passing does not get filed under Economy."""
    t = text or ""
    scores = {}
    for topic, rx in _TOPIC_RE:
        n = len(rx.findall(t))
        if n:
            scores[topic] = n
    if not scores:
        return "Society"
    return max(scores, key=lambda k: (scores[k], _TOPIC_PRIORITY.get(k, 0)))


_INDIA_RE = re.compile(
    r"\b(india|indian|delhi|mumbai|kolkata|chennai|bengaluru|bangalore|hyderabad|"
    r"pune|ahmedabad|jaipur|lucknow|patna|bhopal|nagpur|surat|indore|kanpur|noida|"
    r"gurugram|gurgaon|modi|rahul gandhi|kejriwal|amit shah|\bbjp\b|congress party|"
    r"\brss\b|lok sabha|rajya sabha|nirmala sitharaman|supreme court of india|"
    r"\brbi\b|sensex|nifty|rupee|\bgst\b|aadhaar|\bupi\b|isro|\bcbi\b|"
    r"uttar pradesh|maharashtra|\bbihar\b|west bengal|tamil nadu|karnataka|kerala|"
    r"gujarat|rajasthan|punjab|haryana|telangana|odisha|assam|jharkhand|chhattisgarh|"
    r"uttarakhand|himachal|kashmir|ayodhya|amarnath|"
    r"andhra|arunachal|manipur|meghalaya|mizoram|nagaland|sikkim|tripura|\bgoa\b|"
    r"ladakh|puducherry|new delhi|enforcement directorate|\bdri\b|\bnia\b|\bsebi\b|"
    r"adani|ambani|reliance|tata|infosys|\biit\b|\baiims\b|"
    r"visakhapatnam|vizag|vijayawada|agra|varanasi|amritsar|chandigarh|kochi|"
    r"coimbatore|madurai|guwahati|bhubaneswar|ranchi|raipur|dehradun|srinagar|"
    r"thiruvananthapuram|taj mahal|\bganga\b|himalaya)\b"
    r"|भारत|दिल्ली|मुंबई|मोदी|संसद|कांग्रेस|भाजपा|रुपय|उत्तर प्रदेश|बिहार|कश्मीर",
    re.IGNORECASE)
_FOREIGN_RE = re.compile(
    r"\b(united states|u\.s\.|america|washington|white house|trump|biden|iran|israel|"
    r"gaza|palestine|hamas|russia|ukraine|putin|zelensky|china|beijing|taiwan|pakistan|"
    r"islamabad|afghanistan|taliban|syria|lebanon|yemen|turkey|türkiye|saudi|qatar|"
    r"dubai|\buae\b|egypt|venezuela|brazil|mexico|canada|australia|japan|tokyo|korea|"
    r"france|paris|germany|berlin|italy|spain|britain|\buk\b|london|europe|"
    r"european union|\beu\b|nato|united nations|"
    r"thailand|vietnam|indonesia|malaysia|philippines|singapore|greenland|denmark|"
    r"sweden|norway|finland|poland|greece|netherlands|belgium|switzerland|argentina|"
    r"nigeria|kenya|ethiopia|south africa|kyiv|moscow|\bgaza\b|west bank)\b",
    re.IGNORECASE)


def _guess_region(text: str) -> str:
    """India vs World. India-relevant stories (including India + a foreign country,
    e.g. an India-US trade deal) count as India; only stories with no India angle and
    a clear foreign focus are World. Defaults to India for this India-first platform."""
    t = text or ""
    if _INDIA_RE.search(t):
        return "India"
    if _FOREIGN_RE.search(t):
        return "World"
    return "India"


def _representative(rows):
    """Pick the most usable article: prefer a center outlet (least framing),
    then whichever has the most summary text to quote."""
    if not rows:
        return None
    center = [r for r in rows if lean_of(r["source"]) == "center"]
    return max(center or rows, key=lambda r: len(r.get("summary") or ""))


def _extractive_raw(articles):
    """Build a `raw`-shaped dict WITHOUT an LLM: use a real representative
    headline + lead sentence per language. Honest (a genuine outlet headline,
    attributed via the source list) and guarantees every card is readable. Used
    for the long-tail tier and as the fallback when the LLM is unavailable."""
    en = [a for a in articles if a.get("language") == "en"]
    hi = [a for a in articles if a.get("language") == "hi"]
    en_rep, hi_rep = _representative(en), _representative(hi)
    base = en_rep or hi_rep or articles[0]
    topic_text = " ".join(a.get("title", "") for a in articles)
    # mirror across languages when one side is absent, so neither UI language is blank
    en_title = (en_rep or base).get("title", "")
    hi_title = (hi_rep or base).get("title", "")
    en_sum = _first_sentences((en_rep or base).get("summary") or "")
    hi_sum = _first_sentences((hi_rep or base).get("summary") or "")
    return {
        "title": en_title,
        "summary": en_sum,
        "summary_points": [],
        "title_hi": hi_title,
        "summary_hi": hi_sum,
        "summary_points_hi": [],
        "topic": _guess_topic(topic_text),
        "summary_method": "extractive",
    }


def _run_summaries(rows_list, workers, backend=None):
    """Summarise several article-groups and return analyses IN THE SAME ORDER.
    For a network backend a thread pool runs the slow LLM calls concurrently; each
    group still falls back to an extractive summary on failure, so one bad call
    never sinks the batch."""
    def one(rows):
        try:
            return analyze_event(rows, backend=backend)      # self-falls-back inside
        except Exception:
            return postprocess(_extractive_raw(rows), rows)
    if workers > 1 and len(rows_list) > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as ex:
            return list(ex.map(one, rows_list))              # ex.map preserves order
    return [one(r) for r in rows_list]


def analyze_event(articles, backend=None) -> dict:
    """Never raises. Tries the LLM for a neutral bilingual brief; if the model is
    unavailable or returns nothing usable, falls back to an extractive headline
    so the event still renders (coverage + bias bar are unaffected either way)."""
    try:
        raw = _call_json(build_prompt(articles), backend=backend)
        if not (raw.get("title") or raw.get("summary")):
            raise ValueError("empty model output")
        if _looks_generic(raw.get("title", "")):
            raise ValueError("generic placeholder title")
    except Exception as e:
        print(f"    summary -> extractive fallback ({e})")
        raw = _extractive_raw(articles)
    return postprocess(raw, articles)


# ------------------------------ entrypoint ------------------------------

def recount_event(event_id, resummarise=False):
    """Re-derive a merged event's coverage/bias/sources from its (now larger) member
    set. Cheap arithmetic by default (reuses postprocess); optional LLM re-summary."""
    rows = get_event_articles(event_id)
    if not rows:
        return
    analysis = None
    if resummarise:
        try:
            analysis = analyze_event(rows)
        except Exception:
            analysis = None
    if analysis is None:                      # keep the existing brief, recount the rest
        existing = get_event(event_id) or {}
        raw = {k: existing.get(k) for k in (
            "title", "summary", "summary_points", "title_hi", "summary_hi",
            "summary_points_hi", "framing", "framing_hi", "topic", "region",
            "summary_method")}
        analysis = postprocess(raw, rows)
    update_event(event_id, analysis, bump_created=True)


def _merge_into_existing(details):
    """Fold each new cluster that continues a RECENT event into that event (assign its
    articles + recount), and return the id-lists of the UNMATCHED clusters (>=2 outlets)
    so they go on to become new events through the normal path."""
    if not details:
        return []
    events = get_recent_events_for_merge(days=cluster.MERGE_WINDOW_DAYS)
    ev_clusters = []
    for e in events:
        arts = e["articles"]
        centroid = cluster.cluster_centroid([cluster._text_of(x) for x in arts])
        if centroid is None:
            continue
        kw = cluster.merge_keywords(arts)
        if len(kw) > cluster.XMERGE_MAX_EVENT_KW or e.get("source_count", 0) > 60:
            continue                                  # grab-bag / over-merged: never a merge target
        langs = [x["language"] for x in arts]
        ev_clusters.append({**e, "centroid": centroid, "keywords": kw,
                            "lang": max(set(langs), key=langs.count) if langs else "en"})
    matches = cluster.match_clusters_to_events(details, ev_clusters) if ev_clusters else []
    matched = {id(m["cluster"]) for m in matches}
    for m in matches:
        assign_articles_to_event(m["cluster"]["ids"], m["event"]["event_id"])
        recount_event(m["event"]["event_id"], resummarise=MERGE_RESUMMARISE)
    if matches:
        print(f"Cross-cycle merge: folded {len(matches)} continuing cluster(s) "
              f"into existing events (no duplicates created).")
    return [d["ids"] for d in details
            if id(d) not in matched and d["source_count"] >= MIN_SOURCES_PER_EVENT]


def _event_created_at(rows):
    """The newest member-article publish date, as a naive-UTC ISO string, for backfill
    runs. Parses ISO-8601 (RSS) and YYYYMMDD (GDELT); clamps to now so a backdated event
    can never sort ahead of live ones; returns None if nothing parses (caller then falls
    back to now). Never raises."""
    best = None
    now = datetime.now(timezone.utc)
    for r in rows:
        raw = (r.get("published") or "").strip()
        if not raw:
            continue
        dt = None
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            if re.fullmatch(r"\d{8}", raw):                # GDELT seendate: YYYYMMDD
                try:
                    dt = datetime(int(raw[:4]), int(raw[4:6]), int(raw[6:8]), tzinfo=timezone.utc)
                except ValueError:
                    dt = None
        if dt is None:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt > now:                                       # bad/future feed date
            dt = now
        if best is None or dt > best:
            best = dt
    if best is None:
        return None
    return best.astimezone(timezone.utc).replace(tzinfo=None).isoformat()


def main():
    if LLM_BACKEND == "ollama":
        print("\n=== Paksh analysis (LOCAL via Ollama: %s) ===" % MODEL)
    elif LLM_BACKEND == "pool":
        try:
            from ai_providers import active_providers
            names = ", ".join(p["name"] for p in active_providers()) or "NONE - add a key to ai_keys.env"
        except Exception as e:
            names = f"(pool error: {e})"
        print("\n=== Paksh analysis (provider POOL: %s) ===" % names)
    else:
        print("\n=== Paksh analysis (Gemini: %s) ===" % MODEL)
    init_db()
    from ingest import is_junk
    articles = get_unclustered_articles()
    before = len(articles)
    articles = [a for a in articles if not is_junk(a.get("title", ""))]
    dropped = before - len(articles)
    print(f"Found {len(articles)} un-grouped articles."
          + (f" (skipped {dropped} horoscope/recipe/tag pages)" if dropped else ""))
    if len(articles) < 2:
        print("Not enough articles yet. Run `python ingest.py` first.\n")
        return

    print("Clustering (embeddings) ...")
    if MERGE_ENABLED:
        try:
            details = cluster.cluster_with_details(articles)
        except Exception as e:
            print(f"    embedding clustering unavailable ({e}); using LLM fallback")
            details = None
        clusters = (_merge_into_existing(details) if details is not None
                    else _cluster_articles_llm(articles))
    else:
        clusters = cluster_articles(articles)

    # Quality gate: an event needs >=2 RATED outlets so its bias bar is a real
    # comparison. Unrated outlets (the GDELT long tail, syndication farms like
    # iHeart subdomains or the World News Network) add breadth but cannot create
    # an event on their own -> this drops all-unrated / content-farm junk clusters
    # and stops them from eating the per-run summary budget.
    src_by_id = {a["id"]: a["source"] for a in articles}

    def _rated_count(ids):
        return len({src_by_id.get(i) for i in ids
                    if lean_of(src_by_id.get(i, "")) != "unrated"})

    qualified = [ids for ids in clusters if _rated_count(ids) >= MIN_RATED_PER_EVENT]
    # rank by rated breadth first, then total breadth, so well-rated India stories
    # win the budget over syndication-inflated ones
    qualified.sort(key=lambda ids: (_rated_count(ids), len(ids)), reverse=True)
    print(f"Found {len(clusters)} multi-outlet cluster(s); "
          f"{len(qualified)} have >={MIN_RATED_PER_EVENT} rated outlets.")
    if not qualified:
        print("No events with enough rated coverage yet. Ingest more and retry.\n")
        return

    budget = qualified[:MAX_EVENTS_PER_RUN]
    n_llm = min(LLM_EVENT_BUDGET, len(budget))
    print(f"Publishing {len(budget)} event(s): top {n_llm} via {LLM_BACKEND} "
          f"summary, {len(budget) - n_llm} extractive (no model call).\n")

    rows_by_rank = [get_articles_by_ids(ids) for ids in budget]
    # the slow part: summarise the top n_llm events
    if LLM_BACKEND == "hybrid":
        nloc = min(LLM_LOCAL_BUDGET, n_llm)
        print(f"  Summarising {nloc} locally (Ollama: {OLLAMA_MODEL}) + "
              f"{n_llm - nloc} via Gemini ({GEMINI_MODEL}, {LLM_CONCURRENCY} workers) ...")
        llm_analyses = (_run_summaries(rows_by_rank[:nloc], 1, backend="ollama")
                        + _run_summaries(rows_by_rank[nloc:n_llm], LLM_CONCURRENCY, backend="gemini"))
    else:
        if n_llm and LLM_CONCURRENCY > 1:
            print(f"  Summarising top {n_llm} with {LLM_CONCURRENCY} concurrent workers ...")
        llm_analyses = _run_summaries(rows_by_rank[:n_llm], LLM_CONCURRENCY)

    llm_n = ext_n = 0
    for rank, ids in enumerate(budget):
        rows = rows_by_rank[rank]
        if rank < n_llm:
            analysis = llm_analyses[rank]                 # precomputed (maybe in parallel)
        else:
            analysis = postprocess(_extractive_raw(rows), rows)   # instant, no model call

        created = _event_created_at(rows) if BACKDATE else None
        event_id = insert_event(analysis, is_demo=False, created_at=created)  # serial + ordered
        assign_articles_to_event(ids, event_id)
        if analysis.get("summary_method") == "extractive":
            ext_n += 1
        else:
            llm_n += 1
        if rank < n_llm:
            c = analysis["coverage"]
            print(f"  [{rank + 1}/{n_llm}] [{analysis['topic']}] {analysis['title'][:54]}  "
                  f"(L:{c['left']['count']} C:{c['center']['count']} R:{c['right']['count']})")

    print("-" * 40)
    print(f"Published {llm_n + ext_n} event(s): {llm_n} LLM brief(s), "
          f"{ext_n} extractive.")
    print("\nNext:  python export_static.py\n")


if __name__ == "__main__":
    main()