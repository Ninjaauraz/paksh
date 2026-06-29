"""
export_static.py
----------------
Build a fully static version of Paksh into ./_site so it can be hosted free on
GitHub Pages (no server, no database needed at runtime).

It writes the SAME shapes the live API returns, as files the SPA reads when no
live API is present:
    _site/index.html              (the app shell)
    _site/static/...              (style.css, app.js)
    _site/data/events.json        == /api/events
    _site/data/blindspots.json    == /api/blindspots
    _site/data/topics.json        == /api/topics
    _site/data/sources.json       == /api/sources
    _site/data/events/<id>.json   == /api/events/<id>

Run AFTER ingest.py + analyze.py (so the database has events):
    python ingest.py && python analyze.py && python export_static.py

You can also run it after `python seed_demo.py` to preview the static build
locally:
    python -m http.server -d _site 8080   ->  http://localhost:8080
"""

import json
import shutil
from pathlib import Path

from database import (
    init_db, get_all_events, get_blindspot_events, get_topics, get_event,
)
from sources import SOURCES, coverage_summary

ROOT = Path(__file__).parent
OUT = ROOT / "_site"
SITE_URL = "https://paksh.vercel.app"
SRC_FIELDS = ("id", "name", "language", "region", "website", "ownership", "lean", "label",
              "confidence", "contested", "review_status", "last_reviewed",
              "rationale", "subscores")


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


LEAD_SNIPPET = 240   # the card lead is clamped to ~3 lines; the full text lives in
                     # the per-event detail file, so the list feed only needs a taste.


def _snippet(text):
    text = (text or "").strip()
    if len(text) <= LEAD_SNIPPET:
        return text
    return text[:LEAD_SNIPPET].rsplit(" ", 1)[0].rstrip(",.;:") + "\u2026"


def _lighten(e):
    """A list-feed row: keep every field a card / search / ranking needs, but trim the
    long summary to a snippet and drop the bullet points - both are shown only in the
    detail view, which loads the full per-event file. Shrinks events.json several-fold
    so the page stays fast (and the payload small) as the catalogue grows."""
    e = dict(e)
    e["summary"] = _snippet(e.get("summary"))
    e["summary_hi"] = _snippet(e.get("summary_hi"))
    e.pop("summary_points", None)
    e.pop("summary_points_hi", None)
    return e


def main():
    init_db()

    # fresh output dir
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    # 1) the app shell + assets
    shutil.copytree(ROOT / "static", OUT / "static")
    # the served shell: inject the real domain so canonical / OG / sitemap all agree.
    # Flip SITE_URL (above) when you cut over to paksh.news - nothing else to edit.
    host = SITE_URL.split("://", 1)[-1].rstrip("/")
    shell = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    shell = shell.replace("https://paksh.vercel.app", SITE_URL).replace("paksh.vercel.app", host)
    (OUT / "index.html").write_text(shell, encoding="utf-8")

    # 2) the data the SPA reads (mirrors the API exactly)
    events = get_all_events()
    write_json(OUT / "data" / "events.json", {"events": [_lighten(e) for e in events]})
    write_json(OUT / "data" / "blindspots.json",
               {"events": [_lighten(e) for e in get_blindspot_events()]})
    write_json(OUT / "data" / "topics.json", {"topics": get_topics()})
    write_json(OUT / "data" / "sources.json", {
        "sources": [{k: s.get(k) for k in SRC_FIELDS} for s in SOURCES],
        "summary": coverage_summary(),
    })

    # launch hygiene: let crawlers in and point them at the sitemap
    (OUT / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % SITE_URL, encoding="utf-8")
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        '  <url><loc>%s/</loc><changefreq>hourly</changefreq><priority>1.0</priority></url>\n'
        '</urlset>\n' % SITE_URL, encoding="utf-8")

    # 3) one file per event for the detail view
    for e in events:
        full = get_event(e["id"])
        if full is not None:
            write_json(OUT / "data" / "events" / f"{e['id']}.json", full)

    print(f"Built static site in {OUT}")
    print(f"  events: {len(events)}  |  one-sided: {len(get_blindspot_events())}  "
          f"|  sources: {len(SOURCES)}")
    print("Preview:  python -m http.server -d _site 8080  ->  http://localhost:8080")


if __name__ == "__main__":
    main()