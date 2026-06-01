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
from google import genai
from google.genai import types
from dotenv import load_dotenv

from database import (
    init_db, get_unclustered_articles, get_articles_by_ids,
    assign_articles_to_event, insert_event,
)
from sources import LEAN_BY_SOURCE
import cluster

load_dotenv()

MODEL = "gemini-2.5-flash"
LEAN_ORDER = ["left", "center", "right"]
MAX_EVENTS_PER_RUN = 8
MIN_SOURCES_PER_EVENT = 2
MAX_ARTICLES_PER_EVENT = 12     # cap tokens per event
SUMMARY_TRUNC = 300             # chars of each article summary fed to the model

TOPICS = ["Politics", "Economy", "International", "Sports", "Crime & Law",
          "Science & Tech", "Health", "Entertainment", "Environment", "Society"]

# Guard client creation so the module can be imported (and unit-tested) without
# a key; only the live calls need GEMINI_API_KEY.
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"]) if os.environ.get("GEMINI_API_KEY") else None


# ------------------------------ model calls ------------------------------

def _call(prompt: str) -> str:
    if client is None:
        raise RuntimeError("GEMINI_API_KEY not set")
    return client.models.generate_content(model=MODEL, contents=prompt).text


def _call_json(prompt: str, retries: int = 1):
    """Call Gemini in JSON mode and return parsed data. Retries once, then raises."""
    if client is None:
        raise RuntimeError("GEMINI_API_KEY not set")

    # gemini-2.5-flash "thinks" before answering by default, which can consume the
    # whole output budget and return an EMPTY body (no summary). Turn thinking off
    # and give the answer plenty of room.
    cfg_kwargs = dict(response_mime_type="application/json",
                      temperature=0.2, max_output_tokens=8192)
    try:
        cfg = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_budget=0), **cfg_kwargs)
    except Exception:
        cfg = types.GenerateContentConfig(**cfg_kwargs)   # older SDK: no thinking_config

    last = None
    for _ in range(retries + 1):
        try:
            text = client.models.generate_content(model=MODEL, contents=prompt, config=cfg).text
            return _extract_json(text)
        except Exception as e:
            last = e
    raise ValueError(f"model/JSON failure: {last}")


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
    return LEAN_BY_SOURCE.get(name, "center")


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
        data = _extract_json(_call(prompt))
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
        f'OUTLET: {a["source"]}  [lean: {a["lean"]}, language: {a["language"]}]\n'
        f'HEADLINE: {a["title"]}\nSUMMARY: {(a["summary"] or "(none)")[:SUMMARY_TRUNC]}'
        for a in articles[:MAX_ARTICLES_PER_EVENT]
    ]
    sides_present = sorted({a["lean"] for a in articles}, key=LEAN_ORDER.index)
    sides_spec = ", ".join(
        f'"{s}": "1-2 sentences on how {s}-leaning outlets framed it"'
        for s in sides_present)

    return f"""You are a neutral media-analysis engine for "Paksh", a news
transparency tool for India. Below is coverage of ONE event from several Indian
outlets (English and Hindi), each tagged with a GIVEN political lean - never
change those labels.

Write so a reader sees every side fairly. STRICT RULES:
- Use ONLY facts present in the text below. Never invent facts, quotes, numbers or names.
- The neutral title/summary/points must NOT adopt any side's framing or loaded words.
- Attribute contested claims ("the government said", "critics say") instead of stating them as fact.
- If outlets conflict, state the disagreement neutrally rather than picking a winner.
- Write the neutral brief in ENGLISH, then give a faithful, natural HINDI translation of it.

Return ONLY a JSON object with these keys:
{{
  "title": "neutral English title",
  "summary": "one neutral English sentence",
  "summary_points": ["3-6 short neutral English points"],
  "title_hi": "Hindi translation of the title",
  "summary_hi": "Hindi translation of the summary",
  "summary_points_hi": ["Hindi translations of the points, same order"],
  "topic": "exactly one of {TOPICS}",
  "sources": [
    {{"source": "exact outlet name", "headline": "that outlet's headline",
      "framing": "one line on how this outlet framed it",
      "tone": "supportive|neutral|critical|mixed",
      "notable_language": ["loaded or notable words, if any"]}}
  ],
  "sides": {{ {sides_spec} }},
  "divergence": "2-3 sentences on how coverage differs across the spectrum",
  "omissions": "what some outlets leave out"
}}

COVERAGE:
{(chr(10) + "---" + chr(10)).join(blocks)}
"""


def postprocess(raw, articles) -> dict:
    """Turn the model's (parsed) output + the articles into the stored event.
    Pure function - no network - so it is unit-testable. Resilient to missing
    fields: coverage counts always come from OUR lean config, not the model."""
    raw = raw or {}
    for a in articles:
        a["lean"] = lean_of(a["source"])
    hero = next((a.get("image_url") for a in articles if a.get("image_url")), "")

    # case-insensitive map of the model's per-outlet notes
    msrc = {}
    for s in raw.get("sources", []) or []:
        key = (s.get("source") or "").strip().lower()
        if key:
            msrc[key] = s

    sources_out = []
    for a in articles:
        m = msrc.get(a["source"].strip().lower(), {})
        sources_out.append({
            "source": a["source"], "lean": a["lean"], "language": a["language"],
            "url": a["url"], "headline": m.get("headline") or a["title"],
            "framing": m.get("framing", ""), "tone": m.get("tone", "neutral"),
            "notable_language": m.get("notable_language", []) or [],
        })

    sides_raw = raw.get("sides", {}) or {}
    coverage_out = {}
    for side in LEAN_ORDER:
        names = [s["source"] for s in sources_out if s["lean"] == side]
        coverage_out[side] = {"count": len(names), "sources": names,
                              "framing": sides_raw.get(side, "")}

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
        "divergence": raw.get("divergence", ""),
        "omissions": raw.get("omissions", ""),
        "degraded": degraded,
    }


def analyze_event(articles) -> dict:
    """Never raises: on model/JSON failure, returns a coverage-only event."""
    try:
        raw = _call_json(build_prompt(articles))
    except Exception as e:
        print(f"    analysis fell back to coverage-only ({e})")
        raw = {}
    return postprocess(raw, articles)


# ------------------------------ entrypoint ------------------------------

def main():
    print("\n=== Paksh analysis (Gemini free tier) ===")
    init_db()
    articles = get_unclustered_articles()
    print(f"Found {len(articles)} un-grouped articles.")
    if len(articles) < 2:
        print("Not enough articles yet. Run `python ingest.py` first.\n")
        return

    print("Clustering (embeddings) ...")
    clusters = cluster_articles(articles)
    print(f"Found {len(clusters)} multi-source event(s).")
    if not clusters:
        print("No events covered by 2+ outlets. Ingest more and retry.\n")
        return

    analyzed = 0
    for ids in clusters[:MAX_EVENTS_PER_RUN]:
        rows = get_articles_by_ids(ids)
        names = ", ".join(sorted({r["source"] for r in rows}))
        print(f"  Analysing [{names}] ...")
        try:
            analysis = analyze_event(rows)
        except Exception as e:
            print(f"    skipped ({e})")
            continue
        event_id = insert_event(analysis, is_demo=False)
        assign_articles_to_event(ids, event_id)
        analyzed += 1
        c = analysis["coverage"]
        flag = " (coverage-only)" if analysis.get("degraded") else ""
        print(f"    ✓ [{analysis['topic']}] {analysis['title']}{flag}  "
              f"(L:{c['left']['count']} C:{c['center']['count']} R:{c['right']['count']})")

    print("-" * 40)
    print(f"Analysed and saved {analyzed} event(s).")
    print("\nNext:  refresh http://localhost:8000\n")


if __name__ == "__main__":
    main()