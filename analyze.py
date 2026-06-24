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
import urllib.request
import urllib.error

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from database import (
    init_db, get_unclustered_articles, get_articles_by_ids,
    assign_articles_to_event, insert_event,
)
from sources import LEAN_BY_SOURCE
import cluster

# ---- LLM backend for the bilingual summary --------------------------------
# "ollama" = LOCAL text model (default; free, no API key, no bill)
# "gemini" = Google Gemini (needs API key + billing)
# Flip with PAKSH_LLM_BACKEND; pick the local model with PAKSH_LLM_MODEL.
LLM_BACKEND = os.environ.get("PAKSH_LLM_BACKEND", "ollama").lower()
OLLAMA_URL  = os.environ.get("OLLAMA_URL", "http://localhost:11434")
if LLM_BACKEND == "gemini":
    MODEL = os.environ.get("PAKSH_LLM_MODEL", "gemini-2.5-flash")
else:
    MODEL = os.environ.get("PAKSH_LLM_MODEL", "qwen3.5:4b")

LEAN_ORDER = ["left", "center", "right"]
# Two-tier summarization: the top LLM_EVENT_BUDGET events (ranked by rated
# breadth) get a real neutral LLM summary; everything else up to
# MAX_EVENTS_PER_RUN is published with an instant extractive summary (no model
# call). This decouples "events published" from "slow LLM calls", so a run can
# publish hundreds while only making a few dozen model calls.
LLM_EVENT_BUDGET = 30          # top events that get a full LLM brief (raise on Gemini)
MAX_EVENTS_PER_RUN = 500       # total events published per run (extractive is cheap)
MIN_SOURCES_PER_EVENT = 2
MIN_RATED_PER_EVENT = 2         # an event needs >=2 RATED outlets (real bias bar);
                                # unrated/syndication outlets add breadth, not events
MAX_ARTICLES_PER_EVENT = 12     # cap tokens per event
SUMMARY_TRUNC = 300             # chars of each article summary fed to the model

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
    body = {"model": MODEL, "prompt": prompt + "\n\n/no_think", "stream": False,
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
            "  Open the Ollama app, then run once:  ollama pull " + MODEL + "\n"
            "Original error: " + str(e)) from None


def _gemini_generate(prompt: str, as_json: bool) -> str:
    from google import genai
    from google.genai import types
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    client = genai.Client(api_key=key)
    if not as_json:
        return client.models.generate_content(model=MODEL, contents=prompt).text
    # gemini-2.5-flash "thinks" by default and can spend the whole budget; disable it.
    cfg_kwargs = dict(response_mime_type="application/json",
                      temperature=0.2, max_output_tokens=8192)
    try:
        cfg = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_budget=0), **cfg_kwargs)
    except Exception:
        cfg = types.GenerateContentConfig(**cfg_kwargs)
    return client.models.generate_content(model=MODEL, contents=prompt, config=cfg).text


def _generate(prompt: str, as_json: bool) -> str:
    if LLM_BACKEND == "ollama":
        return _ollama_generate(prompt, as_json)
    return _gemini_generate(prompt, as_json)


def _generate_text(prompt: str) -> str:
    return _generate(prompt, as_json=False)


def _call_json(prompt: str, retries: int = 1):
    """Generate JSON via the active backend, tolerant-parse it, retry once.
    If the backend itself is unreachable, raise immediately so the caller can
    fall back to an extractive summary rather than retry a dead server."""
    last = None
    for _ in range(retries + 1):
        try:
            return _extract_json(_generate(prompt, as_json=True))
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

def build_prompt(articles) -> str:
    blocks = [
        f'OUTLET: {a["source"]}  [language: {a["language"]}]\n'
        f'HEADLINE: {a["title"]}\nSUMMARY: {(a["summary"] or "(none)")[:SUMMARY_TRUNC]}'
        for a in articles[:MAX_ARTICLES_PER_EVENT]
    ]
    return f"""You are a neutral news engine for "Paksh", a media-transparency
tool for India. Below is coverage of ONE event from several Indian outlets
(English and Hindi). Write a single neutral account that a reader of any
political leaning would find fair.

STRICT RULES:
- Use ONLY facts present in the text below. Never invent facts, quotes, numbers or names.
- The title and summary must NOT adopt any outlet's framing or loaded words.
- Attribute contested claims ("the government said", "critics say") instead of stating them as fact.
- If outlets conflict, state the disagreement neutrally rather than picking a winner.
- Write in ENGLISH, then give a faithful, natural HINDI translation.

Return ONLY a JSON object with these keys:
{{
  "title": "neutral English headline, max ~12 words",
  "summary": "2-3 neutral English sentences summarizing what happened",
  "summary_points": ["3-5 short neutral English points"],
  "title_hi": "Hindi translation of the title",
  "summary_hi": "Hindi translation of the summary",
  "summary_points_hi": ["Hindi translations of the points, same order"],
  "topic": "exactly one of {TOPICS}"
}}

COVERAGE:
{(chr(10) + "---" + chr(10)).join(blocks)}
"""


def postprocess(raw, articles) -> dict:
    """Turn the model's (parsed) output + the articles into the stored event.
    Pure function - no network - so it is unit-testable. The neutral brief comes
    from the model; the bias breakdown is pure arithmetic on OUR fixed lean
    labels (no AI decides bias)."""
    raw = raw or {}
    for a in articles:
        a["lean"] = lean_of(a["source"])
    hero = next((a.get("image_url") for a in articles if a.get("image_url")), "")

    # source list: outlet, its fixed lean, language, link, and its own headline
    sources_out = []
    for a in articles:
        sources_out.append({
            "source": a["source"], "lean": a["lean"], "language": a["language"],
            "url": a["url"], "headline": a["title"],
        })

    # coverage = how many outlets of each lean covered it (arithmetic, not AI)
    coverage_out = {}
    for side in LEAN_ORDER:
        names = [s["source"] for s in sources_out if s["lean"] == side]
        coverage_out[side] = {"count": len(names), "sources": names}
    # unrated outlets (GDELT long tail): counted for breadth, never for lean
    unrated_names = [s["source"] for s in sources_out if s["lean"] == "unrated"]
    coverage_out["unrated"] = {"count": len(unrated_names), "sources": unrated_names}

    topic = raw.get("topic", "Society")
    if topic not in TOPICS:
        topic = "Society"

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
        "topic": topic,
        "image_url": hero,
        "sources": sources_out,
        "coverage": coverage_out,
        "total_sources": len(sources_out),
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
                     "rainfall", "pollution", "flood", "cyclone", "weather", "मानसून",
                     "बारिश", "जलवायु", "बाढ़", "मौसम"]),
    ("Crime & Law", ["court", "supreme court", "high court", " fir", "arrest", "murder",
                     " rape", "police", " jail", "verdict", "accused", " probe", " cbi",
                     " ed ", "convict", "अदालत", "कोर्ट", "गिरफ्तार", "हत्या",
                     "बलात्कार", "पुलिस", "जेल", "आरोपी"]),
    ("International", [" us ", "u.s.", "iran", "israel", "pakistan", "china", "russia",
                       "ukraine", "trump", "gaza", "hormuz", "foreign", "bangladesh",
                       "nepal", "अमेरिका", "ईरान", "इजरायल", "पाकिस्तान", "चीन", "रूस",
                       "ट्रंप"]),
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


def _guess_topic(text: str) -> str:
    """Best-effort topic from keywords - so extractive events still sort into the
    right subsection instead of all landing in 'Society'."""
    t = text or ""
    for topic, rx in _TOPIC_RE:
        if rx.search(t):
            return topic
    return "Society"


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


def analyze_event(articles) -> dict:
    """Never raises. Tries the LLM for a neutral bilingual brief; if the model is
    unavailable or returns nothing usable, falls back to an extractive headline
    so the event still renders (coverage + bias bar are unaffected either way)."""
    try:
        raw = _call_json(build_prompt(articles))
        if not (raw.get("title") or raw.get("summary")):
            raise ValueError("empty model output")
    except Exception as e:
        print(f"    summary -> extractive fallback ({e})")
        raw = _extractive_raw(articles)
    return postprocess(raw, articles)


# ------------------------------ entrypoint ------------------------------

def main():
    if LLM_BACKEND == "ollama":
        print("\n=== Paksh analysis (LOCAL via Ollama: %s) ===" % MODEL)
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

    llm_n = ext_n = 0
    for rank, ids in enumerate(budget):
        rows = get_articles_by_ids(ids)
        if rank < LLM_EVENT_BUDGET:
            names = ", ".join(sorted({r["source"] for r in rows}))
            print(f"  [LLM] [{rank + 1}/{n_llm}] {names[:70]} ...")
            try:
                analysis = analyze_event(rows)            # LLM, extractive fallback inside
            except Exception as e:
                print(f"    skipped ({e})")
                continue
        else:
            analysis = postprocess(_extractive_raw(rows), rows)   # instant, no model call

        event_id = insert_event(analysis, is_demo=False)
        assign_articles_to_event(ids, event_id)
        if analysis.get("summary_method") == "extractive":
            ext_n += 1
        else:
            llm_n += 1
        if rank < LLM_EVENT_BUDGET:
            c = analysis["coverage"]
            print(f"    -> [{analysis['topic']}] {analysis['title'][:58]}  "
                  f"(L:{c['left']['count']} C:{c['center']['count']} R:{c['right']['count']})")

    print("-" * 40)
    print(f"Published {llm_n + ext_n} event(s): {llm_n} LLM brief(s), "
          f"{ext_n} extractive.")
    print("\nNext:  python export_static.py\n")


if __name__ == "__main__":
    main()