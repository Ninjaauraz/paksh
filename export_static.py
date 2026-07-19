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

import html as _html
import json
import shutil
from datetime import datetime
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
    # summaries arrive as a string, a list of points, or None - normalise first
    if isinstance(text, (list, tuple)):
        text = " ".join(str(x) for x in text)
    text = (text or "").strip()
    if len(text) <= LEAD_SNIPPET:
        return text
    return text[:LEAD_SNIPPET].rsplit(" ", 1)[0].rstrip(",.;:") + "\u2026"


def _deem(v):
    """Strip em/en dashes (a machine-writing tell) from displayed prose."""
    if isinstance(v, str):
        return v.replace("\u2014", "-").replace("\u2013", "-")
    if isinstance(v, list):
        return [_deem(i) for i in v]
    if isinstance(v, dict):
        return {k: _deem(i) for k, i in v.items()}
    return v


_TEXT_FIELDS = ("title", "title_hi", "summary", "summary_hi", "summary_points",
                "summary_points_hi", "framing", "framing_hi", "lead")


def _clean_text(e):
    e = dict(e)
    for f in _TEXT_FIELDS:
        if f in e:
            e[f] = _deem(e[f])
    return e


def _lighten(e):
    """A list-feed row: keep every field a card / search / ranking needs, but trim the
    long summary to a snippet and drop the bullet points - both are shown only in the
    detail view, which loads the full per-event file. Shrinks events.json several-fold
    so the page stays fast (and the payload small) as the catalogue grows."""
    e = _clean_text(e)
    e["summary"] = _snippet(e.get("summary"))
    e["summary_hi"] = _snippet(e.get("summary_hi"))
    e.pop("summary_points", None)
    e.pop("summary_points_hi", None)
    return e


IMPORTANCE_HALF_LIFE_H = 36.0   # home-feed score halves every 36h -> fresh leads, old fades


def _importance(e, now):
    """Home-feed importance score. Purely arithmetic and explainable in one sentence:
    a story ranks higher the more distinct outlets across left/centre/right cover it,
    with the score halving every 36h so timely stories lead and old ones fade.

        importance = breadth * lean_multiplier * recency_decay
          breadth         = distinct RATED + international outlets (L+C+R+intl);
                            the unrated GDELT long-tail is excluded so syndication
                            can't inflate importance.
          lean_multiplier = 1 + 0.5*(distinct L/C/R leans - 1)   # 1/1.5/2.0
          recency_decay   = 0.5 ** (age_hours / IMPORTANCE_HALF_LIFE_H)

    No LLM, no editorial weighting, no topic favouritism. It only READS the coverage
    counts computed elsewhere - it never changes the bias-bar / coverage numbers.

    DEFERRED (deliberate, recorded decision): a coverage-velocity term (outlets per
    hour) was considered and left out. It would need per-article publish times, which
    arrive noisy/unreliable from RSS feeds (see the staleness diagnostic), and we don't
    want front-page ordering resting on data we don't trust. Recency decay stands in for
    timeliness. Revisit only if we add a trusted per-event first-seen timestamp."""
    lc = e.get("lean_counts") or {}
    rated = sum(lc.get(s, 0) for s in ("left", "center", "right"))
    breadth = rated + (e.get("international", 0) or 0)
    leans = sum(1 for s in ("left", "center", "right") if lc.get(s, 0) > 0)
    lean_mult = (1 + 0.5 * (leans - 1)) if leans else 1.0
    try:
        t = datetime.fromisoformat((e.get("created_at") or "").replace("Z", ""))
        age_h = max((now - t).total_seconds() / 3600.0, 0.0)
    except ValueError:
        age_h = 1e9
    decay = 0.5 ** (age_h / IMPORTANCE_HALF_LIFE_H)
    return round(breadth * lean_mult * decay, 4)


GAP_HALF_LIFE_H = 72.0   # within-column recency nudge so lopsided columns don't freeze


def _gap_parts(e):
    """Symmetric Left<->Right coverage gap from the SAME distinct-outlet counts the bias
    bar uses. Returns (score, direction, L, C, R). score = (L-R)^2/(L+R) grows with both
    magnitude and skew; centre / international / unrated never enter the gap. Direction is
    just whichever of L/R is larger. Purely descriptive - no judgement about any outlet."""
    lc = e.get("lean_counts") or {}
    L, C, R = lc.get("left", 0), lc.get("center", 0), lc.get("right", 0)
    score = ((L - R) ** 2) / (L + R) if (L + R) else 0.0
    direction = "left" if L > R else ("right" if R > L else "even")
    return score, direction, L, C, R


def _gap_qualifies(L, R):
    """A real, lopsided L<->R story: enough coverage AND the smaller side <=25% of larger."""
    lo, hi = min(L, R), max(L, R)
    return (L + R) >= 4 and lo <= 0.25 * hi


def _story_html(shell, ev):
    """The app shell rewritten for ONE story: its own title / description / OG /
    canonical / NewsArticle JSON-LD, and the loading skeleton in #root replaced by
    real HTML (headline + summary + bias breakdown) that crawlers see before JS runs.
    React still boots and replaces it with the full interactive view."""
    sid = ev["id"]
    url = "%s/story/%s" % (SITE_URL, sid)
    headline = (ev.get("title") or "Paksh story").strip()
    summ = ev.get("summary")
    if isinstance(summ, (list, tuple)):
        summ = " ".join(str(x) for x in summ)
    summ = (summ or "").strip()
    desc = summ[:300] or "How India's outlets across the spectrum covered this story."
    img = ev.get("image_url") or (SITE_URL + "/static/og.png")
    if img.startswith("/"):
        img = SITE_URL + img
    esc = lambda x: _html.escape(str(x or ""), quote=True)

    rep = [
        ("<title>Paksh \u2014 Every side of India's news</title>",
         "<title>%s \u2014 Paksh</title>" % esc(headline)),
        ('<meta name="description" content="Paksh compares how India\'s media - left, centre and right - covers each story, side by side, in English and Hindi."/>',
         '<meta name="description" content="%s"/>' % esc(desc)),
        ('<link rel="canonical" href="%s/"/>' % SITE_URL,
         '<link rel="canonical" href="%s"/>' % url),
        ('<meta property="og:type" content="website"/>',
         '<meta property="og:type" content="article"/>'),
        ('<meta property="og:title" content="Paksh \u2014 Every side of India\'s news"/>',
         '<meta property="og:title" content="%s"/>' % esc(headline)),
        ('<meta property="og:description" content="Compare how India\'s media \u2014 left, centre and right \u2014 covers each story, side by side, in English and Hindi."/>',
         '<meta property="og:description" content="%s"/>' % esc(desc)),
        ('<meta property="og:url" content="%s/"/>' % SITE_URL,
         '<meta property="og:url" content="%s"/>' % url),
        ('<meta property="og:image" content="%s/static/og.png"/>' % SITE_URL,
         '<meta property="og:image" content="%s"/>' % esc(img)),
        ('<meta name="twitter:title" content="Paksh \u2014 Every side of India\'s news"/>',
         '<meta name="twitter:title" content="%s"/>' % esc(headline)),
        ('<meta name="twitter:description" content="Compare how India\'s media \u2014 left, centre and right \u2014 covers each story, side by side, in English and Hindi."/>',
         '<meta name="twitter:description" content="%s"/>' % esc(desc)),
        ('<meta name="twitter:image" content="%s/static/og.png"/>' % SITE_URL,
         '<meta name="twitter:image" content="%s"/>' % esc(img)),
    ]
    for a, b in rep:
        shell = shell.replace(a, b, 1)

    cov = ev.get("coverage", {}) or {}
    ld = {"@context": "https://schema.org", "@type": "NewsArticle",
          "headline": headline[:110], "description": desc, "url": url,
          "mainEntityOfPage": url, "image": [img] if img else [],
          "datePublished": ev.get("created_at"), "dateModified": ev.get("created_at"),
          "inLanguage": ev.get("lang", "en"),
          "publisher": {"@type": "Organization", "name": "Paksh",
                        "logo": {"@type": "ImageObject", "url": SITE_URL + "/static/apple-touch-icon.png"}},
          "isAccessibleForFree": True}
    shell = shell.replace("</head>",
                          '<script type="application/ld+json">%s</script>\n</head>'
                          % json.dumps(ld, ensure_ascii=False), 1)

    # crawlable body in place of the skeleton
    e2 = lambda x: _html.escape(str(x or ""))
    rows = []
    for key, label in (("left", "Left"), ("center", "Centre"),
                       ("right", "Right"), ("international", "International")):
        block = cov.get(key, {}) or {}
        c = block.get("count", 0)
        if c:
            rows.append("<li><strong>%s (%d):</strong> %s</li>"
                        % (label, c, e2(", ".join(block.get("sources", []) or []))))
    bias_html = ("<ul>%s</ul>" % "".join(rows)) if rows else ""
    body = (
        '<main style="max-width:46rem;margin:0 auto;padding:84px 1.25rem 40px">'
        '<p style="font:600 12px/1.4 monospace;letter-spacing:.08em;text-transform:uppercase;color:#6B655C">%s &middot; %s</p>'
        '<h1 style="font:700 30px/1.25 system-ui;margin:.3em 0 .5em;color:#1B1A18">%s</h1>'
        '<p style="font:400 17px/1.6 system-ui;color:#46423B">%s</p>'
        '<h2 style="font:600 16px/1.3 system-ui;margin:1.6em 0 .4em;color:#1B1A18">How outlets across the spectrum covered it</h2>'
        '%s'
        '<p style="margin-top:1.4em"><a href="%s/">More balanced coverage on Paksh &rarr;</a></p>'
        '</main>'
    ) % (e2(ev.get("topic") or ""), e2(ev.get("region") or "India"),
         e2(headline), e2(summ), bias_html, SITE_URL)
    head, rest = shell.split('<div id="root">', 1)
    _, tail = rest.split('<script type="text/babel" src="/static/app.jsx"></script>', 1)
    return head + '<div id="root">' + body + '</div>\n<script type="text/babel" src="/static/app.jsx"></script>' + tail



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
    _now = datetime.utcnow()

    def _row(e):
        d = _lighten(e)
        d["importance"] = _importance(e, _now)   # NEW field; existing fields untouched
        return d

    write_json(OUT / "data" / "events.json", {"events": [_row(e) for e in events]})

    # Coverage Gaps (symmetric blindspots): the SAME formula surfaces both directions.
    # Each column is ranked by gap * recency so the lopsided lists stay fresh instead of
    # freezing for weeks. The honest aggregate (pool sizes) is disclosed for the Method page.
    _COL_N = 40   # data headroom per direction; the UI shows 15 per column AFTER the
                  # per-language filter, so each language gets a full, equal-length column
    buckets = {"left": [], "right": []}
    agg = {"left_heavier": 0, "right_heavier": 0}
    for e in events:
        score, direction, L, C, R = _gap_parts(e)
        if direction == "even" or not _gap_qualifies(L, R):
            continue
        agg["left_heavier" if direction == "left" else "right_heavier"] += 1
        try:
            t = datetime.fromisoformat((e.get("created_at") or "").replace("Z", ""))
            age_h = max((_now - t).total_seconds() / 3600.0, 0.0)
        except ValueError:
            age_h = 1e9
        rank = score * (0.5 ** (age_h / GAP_HALF_LIFE_H))
        row = _row(e)
        row["gap_score"] = round(score, 3)
        buckets[direction].append((rank, row))
    for k in buckets:
        buckets[k].sort(key=lambda x: x[0], reverse=True)
    left_col = [r for _, r in buckets["left"][:_COL_N]]
    right_col = [r for _, r in buckets["right"][:_COL_N]]
    left_outlets = sum(1 for s in SOURCES if s.get("lean") == "left" and s.get("region") != "International")
    right_outlets = sum(1 for s in SOURCES if s.get("lean") == "right" and s.get("region") != "International")
    write_json(OUT / "data" / "blindspots.json", {
        "events": left_col + right_col,          # union, kept for detail lookups / back-compat
        "left_heavier": left_col,
        "right_heavier": right_col,
        "aggregate": {
            "total": agg["left_heavier"] + agg["right_heavier"],
            "left_heavier": agg["left_heavier"], "right_heavier": agg["right_heavier"],
            "left_outlets": left_outlets, "right_outlets": right_outlets,
            "shown": _COL_N,
        },
    })
    write_json(OUT / "data" / "topics.json", {"topics": get_topics()})
    write_json(OUT / "data" / "sources.json", {
        "sources": [{k: s.get(k) for k in SRC_FIELDS} for s in SOURCES],
        "summary": coverage_summary(),
    })

    # freshness signal: newest event date + build time, written INTO the site so a
    # silent pipeline stall is visible (py stats.py --freshness, or GET /data/freshness.json).
    # events come back newest-first, so events[0] is the newest published story.
    newest_event = events[0].get("created_at") if events else ""
    write_json(OUT / "data" / "freshness.json", {
        "newest_event_at": newest_event or "",
        "built_at": datetime.utcnow().isoformat(),
        "event_count": len(events),
    })

    # 3) one file per event: detail JSON + a pre-rendered, crawlable HTML page
    story_urls = []
    for e in events:
        full = get_event(e["id"])
        if full is None:
            continue
        full = _clean_text(full)
        write_json(OUT / "data" / "events" / f"{e['id']}.json", full)
        sp = OUT / "story" / f"{e['id']}.html"
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(_story_html(shell, full), encoding="utf-8")
        story_urls.append((f"{SITE_URL}/story/{e['id']}", full.get("created_at")))

    # 4) Vercel: clean URLs + SPA fallback. Real files (story/, data/, static/) always
    #    win over the rewrite, so only unknown paths (/about, /topic/X) hit the SPA.
    write_json(OUT / "vercel.json", {
        "cleanUrls": True, "trailingSlash": False,
        "rewrites": [{"source": "/(.*)", "destination": "/index.html"}],
        "headers": [{
            "source": "/(.*)",
            "headers": [
                {"key": "X-Content-Type-Options", "value": "nosniff"},
                {"key": "X-Frame-Options", "value": "SAMEORIGIN"},
                {"key": "Referrer-Policy", "value": "strict-origin-when-cross-origin"},
                {"key": "Permissions-Policy",
                 "value": "camera=(), microphone=(), geolocation=(), browsing-topics=()"},
                {"key": "Strict-Transport-Security",
                 "value": "max-age=63072000; includeSubDomains; preload"},
                {"key": "Content-Security-Policy",
                 "value": "frame-ancestors 'self'; object-src 'none'; base-uri 'self'"},
            ],
        }],
    })

    # 5) robots + sitemap (homepage + every story)
    (OUT / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % SITE_URL, encoding="utf-8")
    rows = ['  <url><loc>%s/</loc><changefreq>hourly</changefreq><priority>1.0</priority></url>' % SITE_URL]
    for u, ts in story_urls:
        lm = "<lastmod>%s</lastmod>" % ts[:10] if ts else ""
        rows.append('  <url><loc>%s</loc>%s<changefreq>daily</changefreq><priority>0.7</priority></url>' % (u, lm))
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(rows) + "\n</urlset>\n", encoding="utf-8")

    print(f"Built static site in {OUT}")
    print(f"  events: {len(events)}  |  one-sided: {len(get_blindspot_events())}  "
          f"|  sources: {len(SOURCES)}")
    print("Preview:  python -m http.server -d _site 8080  ->  http://localhost:8080")


if __name__ == "__main__":
    main()