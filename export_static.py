"""
export_static.py
----------------
Build a fully static version of Paksh into ./_site so it can be hosted free on
GitHub Pages (no server, no database needed at runtime).

It writes the SAME shapes the live API returns, as files the SPA reads when no
live API is present:
    _site/index.html              (the app shell)
    _site/static/...              (styles.css, app.js)
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
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

from database import (
    init_db, get_all_events, get_blindspot_events, get_topics, get_events_by_ids,
)
from sources import SOURCES, coverage_summary, OWNER_BY_SOURCE
# Paksh perf phase 4B: storylines (and its own numpy/cluster imports) is only
# ever used by build() below, not by feed_row()/_lighten()/_importance()/
# _feed_rank()/_civic_mult() - the functions supabase_content.py imports this
# module for. Deferred into build() itself so importing export_static.py (as
# the FastAPI/Supabase-mode process does, transitively) never pays for it.

ROOT = Path(__file__).parent
OUT = ROOT / "_site"
SITE_URL = "https://paksh.news"
SRC_FIELDS = ("id", "name", "language", "region", "website", "ownership", "owner", "lean", "label",
              "confidence", "contested", "review_status", "last_reviewed",
              "rationale", "subscores", "axes")


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

# How many newest events ride in events.json (the payload EVERY visitor downloads on first
# paint). The older tail goes to events-archive.json, fetched lazily only on Search / Topic.
# Feed ranking decays with a 36h/8h half-life, so anything past a few weeks never surfaces on
# the home feed anyway -- 1500 is comfortably more than the feed shows, keeping first paint
# small (a few MB) while the full archive stays one lazy fetch away.
RECENT_FEED_N = 1500

# Per-story social share cards (og_images.py): a 1200x630 PNG carrying the bias bar,
# so a shared story link previews the actual coverage split. Generated only for the
# newest OG_CARD_N events (the ones people actually share); older archived stories fall
# back to their article photo / the global og.png. Cards are deterministic, so an
# unchanged story re-renders to identical bytes and git sees no churn. Set 0 to disable.
OG_CARD_N = RECENT_FEED_N


def _build_og_cards(rows, limit):
    """Render share cards into _site/static/og/<id>.png for the first `limit` feed
    rows (each already carries title/topic/region/lean_counts, so no extra DB hit).
    Returns the set of ids that got a card. NEVER fatal: if Pillow/fontTools aren't
    importable it logs once and returns an empty set, so every story keeps the global
    og.png fallback and the build still succeeds (static-export invariant preserved)."""
    if limit <= 0 or not rows:
        return set()
    try:
        import og_images
    except Exception as e:
        print("  [og] share cards skipped (%s: %s); using global og.png"
              % (e.__class__.__name__, e))
        return set()
    out_dir = OUT / "static" / "og"
    out_dir.mkdir(parents=True, exist_ok=True)
    made, fails, t0 = set(), 0, time.time()
    for r in rows[:limit]:
        try:
            og_images.render_og_card(r, str(out_dir / ("%s.png" % r["id"])))
            made.add(r["id"])
        except Exception as ex:
            fails += 1
            if fails <= 3:
                print("  [og] card failed for %s: %s" % (r.get("id"), ex))
    print("  [og] %d share cards written in %.1fs%s"
          % (len(made), time.time() - t0, (" (%d failed)" % fails) if fails else ""))
    return made


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


FEED_HALF_LIFE_H = 8.0   # front-page feed halves every 8h so breaking news leads


def _age_hours(e, now):
    """Hours since the event's REAL publish time (newest member article), falling back to
    created_at for events analysed before published_at existed. Used for feed recency so
    'x ago' on the card and the story's rank decay from the SAME moment."""
    stamp = e.get("published_at") or e.get("created_at") or ""
    try:
        t = datetime.fromisoformat(stamp.replace("Z", ""))
    except ValueError:
        return 1e9
    return max((now - t).total_seconds() / 3600.0, 0.0)


# --- Civic priority (FRONT-PAGE ordering weight only) -------------------------------
# Indian readers lead with governance/politics/economy and the legal-constitutional beat
# (amendments, court verdicts, major movements), not the sports/entertainment volume that
# dominates a global feed. This is an EDITORIAL ordering weight Sameer chose (2026-08-06):
# a FIXED lookup table + keyword list, never an AI decision. It multiplies feed_rank on the
# home feed ONLY. It NEVER touches a bias-bar / coverage count, the importance score used
# elsewhere, or Sections / Search / Topic pages (those stay newest-first).
CIVIC_TOPIC_WEIGHT = {
    "Politics": 1.6, "Economy": 1.3, "Crime & Law": 1.3, "Environment": 1.1,
    "Science & Tech": 1.0, "Health": 1.0, "Society": 1.0, "International": 0.9,
    "Entertainment": 0.7, "Sports": 0.6,
}
# A headline touching the constitutional / mass-movement beat gets an extra nudge so a big
# amendment or verdict surfaces even against high-volume coverage. English + Hindi (Latin).
CIVIC_KEYWORDS = re.compile(
    r"amendment|ordinance|\bbill\b|parliament|sansad|lok sabha|rajya sabha|"
    r"supreme court|high court|verdict|constitution|reservation|\bquota\b|"
    r"protest|andolan|movement|morcha|bandh|\bcabinet\b|governor|election|"
    r"\bpolicy\b|\bact\b", re.I)


def _civic_mult(e):
    """Front-page-only multiplier: fixed topic weight * a 1.25 nudge when the title hits the
    constitutional / movement keyword list. Purely arithmetic and explainable in one line."""
    w = CIVIC_TOPIC_WEIGHT.get(e.get("topic"), 1.0)
    text = " ".join([e.get("title") or "", e.get("title_hi") or ""])
    if CIVIC_KEYWORDS.search(text):
        w *= 1.25
    return round(w, 3)


def _feed_rank(e, now):
    """FRONT-PAGE ordering only. The SAME breadth*lean signal as _importance, but with a
    much shorter 8h half-life so the feed always leads with what's current: breadth orders
    stories of similar age, while age actively decays rank so a day-old high-coverage story
    no longer buries an hour-old breaking one. Age is measured from the real publish time
    (see _age_hours). This is feed-ONLY - _importance (used elsewhere) is untouched - and it
    only READS coverage counts, never changing any bias-bar / coverage number. The civic
    weight is applied separately in _row so this stays pure breadth*recency."""
    lc = e.get("lean_counts") or {}
    rated = sum(lc.get(s, 0) for s in ("left", "center", "right"))
    breadth = rated + (e.get("international", 0) or 0)
    leans = sum(1 for s in ("left", "center", "right") if lc.get(s, 0) > 0)
    lean_mult = (1 + 0.5 * (leans - 1)) if leans else 1.0
    decay = 0.5 ** (_age_hours(e, now) / FEED_HALF_LIFE_H)
    return round(breadth * lean_mult * decay, 4)


def feed_row(e, story_map, now):
    """Shape one event for events.json / events-archive.json (and, since Phase 1.75,
    main.py's live /api/events-archive) - lightened payload + importance + feed_rank +
    storyline_id. Module-level (not a build()-local closure) specifically so main.py can
    import and call the exact same function rather than re-deriving these fields."""
    d = _lighten(e)
    d["importance"] = _importance(e, now)   # existing field; untouched, used elsewhere
    # front-page order = pure breadth*recency, then the civic weight so India-first
    # (politics / economy / courts / movements) leads. Both factors are explainable and
    # never touch a bias count. Sections/Search/Topic ignore this and stay newest-first.
    d["feed_rank"] = round(_feed_rank(e, now) * _civic_mult(e), 4)
    sid = story_map.get(e["id"])
    if sid:
        d["storyline_id"] = sid
    return d


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


def _group_by_owner(names):
    """Group masthead names by their owning group, preserving first-seen order.
    Returns an ordered {owner: [names]} so co-owned papers render together and the
    reader can see why they count as one vote. Outlets with no shared owner map to
    their own name, so they stay their own group of one."""
    from collections import OrderedDict
    groups = OrderedDict()
    for n in names:
        o = OWNER_BY_SOURCE.get(n, n)
        groups.setdefault(o, []).append(n)
    return groups


def _story_html(shell, ev, og_ids=None):
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
    # Social preview image, best -> fallback: the branded per-story share card (the
    # bias bar, generated by og_images.py for the recent feed) -> the story's own
    # article photo -> the global og.png. So a shared link previews the coverage split.
    if og_ids and sid in og_ids:
        img = "%s/static/og/%s.png" % (SITE_URL, sid)
    else:
        img = ev.get("image_url") or (SITE_URL + "/static/og.png")
        if img.startswith("/"):
            img = SITE_URL + img
    esc = lambda x: _html.escape(str(x or ""), quote=True)

    rep = [
        ("<title>Paksh: Every side of India's news</title>",
         "<title>%s | Paksh</title>" % esc(headline)),
        ('<meta name="description" content="Paksh compares how India\'s media, left, centre and right, covers each story, side by side, in English and Hindi."/>',
         '<meta name="description" content="%s"/>' % esc(desc)),
        ('<link rel="canonical" href="%s/"/>' % SITE_URL,
         '<link rel="canonical" href="%s"/>' % url),
        ('<meta property="og:type" content="website"/>',
         '<meta property="og:type" content="article"/>'),
        ('<meta property="og:title" content="Paksh: Every side of India\'s news"/>',
         '<meta property="og:title" content="%s"/>' % esc(headline)),
        ('<meta property="og:description" content="Compare how India\'s media, left, centre and right, covers each story, side by side, in English and Hindi."/>',
         '<meta property="og:description" content="%s"/>' % esc(desc)),
        ('<meta property="og:url" content="%s/"/>' % SITE_URL,
         '<meta property="og:url" content="%s"/>' % url),
        ('<meta property="og:image" content="%s/static/og.png"/>' % SITE_URL,
         '<meta property="og:image" content="%s"/>' % esc(img)),
        ('<meta name="twitter:title" content="Paksh: Every side of India\'s news"/>',
         '<meta name="twitter:title" content="%s"/>' % esc(headline)),
        ('<meta name="twitter:description" content="Compare how India\'s media, left, centre and right, covers each story, side by side, in English and Hindi."/>',
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
          "datePublished": ev.get("published_at") or ev.get("created_at"),
          "dateModified": ev.get("created_at"),
          "inLanguage": ev.get("lang", "en"),
          "publisher": {"@type": "Organization", "name": "Paksh",
                        "logo": {"@type": "ImageObject", "url": SITE_URL + "/static/apple-touch-icon.png"}},
          "isAccessibleForFree": True}
    # SECURITY: json.dumps does NOT escape < > &, so a story title/summary containing the
    # literal "</script>" (an adversarial or spoofed ingested source could craft one) would
    # close this <script> block and inject arbitrary JS into every reader's page. Escape the
    # HTML-significant characters as JSON \uXXXX (still valid JSON-LD) to make breakout
    # impossible. \u2028/\u2029 are escaped too (defensive, harmless in JSON-LD).
    _jsonld = (json.dumps(ld, ensure_ascii=False)
               .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
               .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))
    shell = shell.replace("</head>",
                          '<script type="application/ld+json">%s</script>\n</head>' % _jsonld, 1)

    # crawlable body in place of the skeleton
    e2 = lambda x: _html.escape(str(x or ""))
    rows = []
    for key, label in (("left", "Left"), ("center", "Centre"),
                       ("right", "Right"), ("international", "International")):
        block = cov.get(key, {}) or {}
        c = block.get("count", 0)
        if not c:
            continue
        names = block.get("sources", []) or []
        # ONE VOTE PER OWNER: group co-owned mastheads so the crawlable HTML shows
        # both papers but makes clear they count once (matches the app + the bar).
        # International is not a vote, so it is never grouped.
        if key == "international":
            head = "%s (%d)" % (label, c)
            listing = e2(", ".join(names))
        else:
            groups = _group_by_owner(names)
            parts = []
            for owner, members in groups.items():
                if len(members) > 1:
                    parts.append("%s <em>(%s &mdash; 1 vote)</em>"
                                 % (e2(" · ".join(members)), e2(owner)))
                else:
                    parts.append(e2(members[0]))
            listing = ", ".join(parts)
            head = ("%s (%d)" % (label, c) if c == len(names)
                    else "%s (%d votes, %d outlets)" % (label, c, len(names)))
        rows.append("<li><strong>%s:</strong> %s</li>" % (head, listing))
    bias_html = ('<ul style="margin:0;padding-left:1.1em;font-size:14px;line-height:1.7">%s</ul>'
                 % "".join(rows)) if rows else ""

    # A static, crawlable bias PILL whose segment sizes are the REAL distinct-owner counts
    # (flex-grow = count; never hardcoded) - same solid-fill, no-hatch, no-percentage language
    # as the client's BiasPill (static/app.jsx, PILL_COLOR), not the retired textured bar.
    # React replaces this with the interactive pill on load; crawlers / no-JS readers see this.
    _pill_color = {"left": "#587A91", "center": "#6F6B61", "right": "#A46149"}
    _bcounts = {k: (cov.get(k, {}) or {}).get("count", 0) for k in ("left", "center", "right")}
    _present = [k for k in ("left", "center", "right") if _bcounts[k] > 0]
    if _present:
        segs = "".join(
            '<div style="flex-grow:%d;flex-basis:0;background:%s"></div>' % (_bcounts[k], _pill_color[k])
            for k in _present
        )
        bar_html = (
            '<div style="display:flex;width:100%%;overflow:hidden;height:8px;border-radius:999px;'
            'background:#D8D3C6;margin-bottom:6px">%s</div>'
            '<div style="font:500 10px/1 \'IBM Plex Mono\',monospace;letter-spacing:.04em;'
            'color:#8A8371;margin:0 0 20px">L %d C %d R %d</div>'
        ) % (segs, _bcounts["left"], _bcounts["center"], _bcounts["right"])
    else:
        bar_html = ""

    body = (
        '<main style="max-width:44rem;margin:0 auto;padding:88px 1.25rem 48px;'
        'font-family:\'Source Serif 4\',Georgia,serif;color:#3A372F">'
        '<p style="font:500 11px/1.4 \'IBM Plex Mono\',monospace;letter-spacing:.14em;'
        'text-transform:uppercase;color:#8A8371;margin:0">%s &middot; %s</p>'
        '<h1 style="font:600 32px/1.16 \'Source Serif 4\',Georgia,serif;letter-spacing:-.014em;'
        'margin:.35em 0 .55em;color:#15140F">%s</h1>'
        '<p style="font:400 17px/1.66 \'Source Serif 4\',Georgia,serif;color:#26241E">%s</p>'
        '<h2 style="font:600 12px/1.3 \'IBM Plex Sans\',system-ui,sans-serif;letter-spacing:.14em;'
        'text-transform:uppercase;margin:2em 0 .9em;color:#15140F">How outlets across the spectrum covered it</h2>'
        '%s%s'
        '<p style="margin-top:1.6em;font:500 13px/1.4 \'IBM Plex Sans\',system-ui,sans-serif">'
        '<a href="%s/" style="color:#15140F">More balanced coverage on Paksh &rarr;</a></p>'
        '</main>'
    ) % (e2(ev.get("topic") or ""), e2(ev.get("region") or "India"),
         e2(headline), e2(summ), bar_html, bias_html, SITE_URL)
    head, rest = shell.split('<div id="root">', 1)
    _, tail = rest.split('<script src="/static/app.js"></script>', 1)
    return head + '<div id="root">' + body + '</div>\n<script src="/static/app.js"></script>' + tail


def _precompile_jsx():
    """Compile static/app.jsx (JSX) to _site/static/app.js (plain React.createElement JS)
    with the vendored Babel UMD, so the browser never downloads or runs Babel. Fails LOUDLY
    if node or the vendored babel is missing, or the transform errors - a broken build must
    never be published."""
    import subprocess
    babel = ROOT / "vendor" / "babel.min.js"
    src = ROOT / "static" / "app.jsx"
    out = OUT / "static" / "app.js"
    if not babel.exists():
        raise SystemExit("[export] missing vendor/babel.min.js - run:\n"
                         "  curl -sL https://unpkg.com/@babel/standalone@7.24.7/babel.min.js -o vendor/babel.min.js")
    node_script = (
        "const B=require(process.argv[1]);const fs=require('fs');"
        "const code=B.transform(fs.readFileSync(process.argv[2],'utf8'),{presets:['react'],compact:false}).code;"
        "fs.writeFileSync(process.argv[3],code);"
    )
    try:
        r = subprocess.run(["node", "-e", node_script, str(babel), str(src), str(out)],
                           capture_output=True, text=True)
    except FileNotFoundError:
        raise SystemExit("[export] node not found on PATH - required to precompile app.jsx -> app.js")
    if r.returncode != 0:
        raise SystemExit("[export] JSX precompile failed:\n" + (r.stderr or r.stdout))
    # ship app.js only: drop the JSX source that copytree placed in the output
    jsx_copy = OUT / "static" / "app.jsx"
    if jsx_copy.exists():
        jsx_copy.unlink()
    print(f"  precompiled app.jsx -> app.js ({out.stat().st_size} bytes)")


def _build_tailwind():
    """Compile only the Tailwind utilities the app actually uses to a static
    _site/static/tailwind.css with the vendored standalone CLI (it scans static/app.jsx +
    index.html), replacing the runtime cdn.tailwindcss.com script. Fails LOUDLY if the CLI
    is missing or the build errors, so an unstyled site is never published."""
    import os
    import subprocess
    cli = ROOT / "vendor" / ("tailwindcss.exe" if os.name == "nt" else "tailwindcss")
    cfg = ROOT / "tailwind.config.js"
    inp = ROOT / "tailwind.input.css"
    out = OUT / "static" / "tailwind.css"
    if not cli.exists():
        raise SystemExit("[export] missing vendor/tailwindcss (standalone CLI). Download v3:\n"
                         "  https://github.com/tailwindlabs/tailwindcss/releases -> vendor/tailwindcss.exe")
    try:
        r = subprocess.run([str(cli), "-c", str(cfg), "-i", str(inp), "-o", str(out), "--minify"],
                           cwd=str(ROOT), capture_output=True, text=True)
    except FileNotFoundError:
        raise SystemExit("[export] could not run the Tailwind CLI at " + str(cli))
    if r.returncode != 0:
        raise SystemExit("[export] Tailwind build failed:\n" + (r.stderr or r.stdout))
    print(f"  built tailwind.css ({out.stat().st_size} bytes)")



# Function words to ignore when mining trending terms - purely structural, no editorial
# judgement. English + Hindi, plus a few news-generic words that aren't topics.
_STOP_EN = set((
    "the a an and or of to in on for at by with from as is are was were be been being this "
    "that these those it its his her their our your my we you they he she but not no yes will "
    "would can could may might must shall have has had do does did over after before under "
    "about into out up down off new says say said amid per via report reports reported against "
    "between during while than then them us who whom which what when where why how all any some "
    "more most other such only own same so also just now today day week year first second two "
    "three india indian re ll ve amid set gets get near back top big call calls launch launched "
    "held face made plan plans seeks calls meet meets visit slams hits sets faces urges").split())
_STOP_HI = set((
    "के की का में से को है हैं था थे थी पर और या भी एक यह वह इस उस कि जो ने हो कर लिए साथ तक ही अब "
    "तो नहीं क्या जब तब कोई सब बाद पहले बीच दौरान होगा होगी गया गई गए रहे रही रहा हुई हुए हुआ लेकिन "
    "तथा एवं वाले वाली वाला अपने अपनी उनके उनकी इनके पास ओर बारे कहा भारत भारतीय पर बना रहा रही "
    "करने खिलाफ आरोप उपाय रूप शामिल जिसमें द्वारा होने कारण लॉन्च किया ध्यान केंद्रित बनाने शुरू "
    "उठाए सवाल दिया लिया करते करता करती").split())

# High-signal event types worth surfacing as a trend even as a single word (the user's
# "earthquake / protests / crackdown / election" case). Generic words (kill/attack/claim)
# stay OUT - proper nouns carry those stories instead.
_EVENT_EN = set((
    "earthquake quake aftershock flood floods flooding cyclone landslide drought heatwave "
    "wildfire tsunami avalanche protest protests protesters strike shutdown bandh election "
    "elections poll polls bypoll crackdown ceasefire verdict judgment budget referendum coup "
    "sanctions tariffs recession inflation layoffs merger ban boycott blackout outage pandemic "
    "outbreak curfew riots scam fraud").split())
_EVENT_HI = set((
    "भूकंप बाढ़ चक्रवात भूस्खलन सूखा प्रदर्शन विरोध हड़ताल चुनाव मतदान कार्रवाई युद्धविराम फैसला "
    "बजट प्रतिबंध महामारी कर्फ्यू दंगा घोटाला हिमस्खलन").split())
# Common English words used to reject sentence-initial capitals and generic terms when mining
# proper nouns: the stopwords plus frequent news nouns/verbs. A capitalised word here is NOT
# treated as a name (so "Building collapses..." doesn't make "Building" trend).
_COMMON_EN = _STOP_EN | set((
    "building buildings people person multiple several many few over after before during while "
    "amid following man woman men women boy girl child killed kills kill dead death dies died "
    "injured found arrest arrested held case cases report reports reported claim claims alleged "
    "alleges government minister ministry official officials police court hearing meeting event "
    "events group launch launches launched plan plans seeks meet meets visit visits addresses "
    "slams hits sets faces urges announces announced approves approved passes passed clears "
    "cleared gets actor actress star president chief head leader bomb blast fire shooting attack "
    "security army forces restaurant hotel city state country nation world live update latest "
    "video watch photos sparks spark near across among huge major minor big small top "
    "january february march april june july august september october november december husband "
    "wife bail grants grant leaves leave gets get amid over sees seen backs back set").split())


def _trending(events, now):
    """Descriptive, ARITHMETIC trending TOPICS - never a curated cause. From RECENT event
    TITLES it mines named entities (capitalised runs / acronyms in English) plus a curated
    set of high-signal event types (earthquake, floods, election, protest...), then ranks by
    how much a term spiked vs the prior 24-72h window (lift). Generic verbs/nouns are
    excluded, so the list reads like real topics a reader browses, not filler. Split by
    region into national (India) and international (World). Bilingual (EN + HI).
    Returns {national:{en:[...],hi:[...]}, international:{en:[...],hi:[...]}}."""
    import re, math
    from collections import defaultdict
    WORD = re.compile(r"[A-Za-z][A-Za-z&'.-]*")
    HTOK = re.compile(r"[ऀ-ॿ]+")

    def _age(e):
        try:
            t = datetime.fromisoformat((e.get("created_at") or "").replace("Z", ""))
        except ValueError:
            return 1e9
        return max((now - t).total_seconds() / 3600.0, 0.0)

    def _proper(w):
        # A name: an all-caps acronym (US, UN, BJP, NEET, GST) or a capitalised word whose
        # lowercase isn't a common / sentence-initial word.
        if w.isupper() and 2 <= len(w) <= 6:
            return True
        return w[0].isupper() and len(w) > 2 and w.lower() not in _COMMON_EN

    def terms_en(title):
        low = (title or "").lower()
        out = []
        for kw in _EVENT_EN:
            if re.search(r"\b" + re.escape(kw) + r"\b", low):
                out.append((kw, kw))
        words = WORD.findall(title or "")
        i, nA = 0, len(words)
        while i < nA:
            if _proper(words[i]):
                phrase = [words[i]]; j = i + 1
                while j < nA:
                    if _proper(words[j]):
                        phrase.append(words[j]); j += 1
                    elif words[j].lower() in ("and", "of", "&") and j + 1 < nA and _proper(words[j + 1]):
                        phrase.append(words[j]); phrase.append(words[j + 1]); j += 2
                    else:
                        break
                disp = " ".join(phrase)
                out.append((disp.lower(), disp))       # (norm for counting, display keeps case)
                i = j
            else:
                i += 1
        return out

    def terms_hi(title):
        text = (title or "").replace("।", " ").replace("॥", " ")
        toks = [w for w in HTOK.findall(text) if len(w) > 2 and w not in _STOP_HI]
        out = [(w, w) for w in toks if w in _EVENT_HI]
        for i in range(len(toks) - 1):                # entities show up as bigrams in Devanagari
            g = toks[i] + " " + toks[i + 1]
            out.append((g, g))
        return out

    def rank(subset, field, extract):
        rec_ev, pri, disp = defaultdict(set), defaultdict(int), {}
        rec_total = pri_total = 0
        for e in subset:
            age = _age(e)
            if age <= 24:
                rec_total += 1
                for norm, d in extract(str(e.get(field) or "")):
                    rec_ev[norm].add(e["id"]); disp.setdefault(norm, d)
            elif age <= 72:
                pri_total += 1
                for norm, d in extract(str(e.get(field) or "")):
                    pri[norm] += 1
        rec_total, pri_total = max(rec_total, 1), max(pri_total, 1)
        rows = []
        for norm, ids in rec_ev.items():
            n = len(ids)
            if n < 2:                                  # real cluster, not a one-off
                continue
            recent_rate = n / rec_total
            prior_rate = (pri.get(norm, 0) + 0.5) / (pri_total + 1)
            lift = recent_rate / prior_rate            # spike vs the prior window
            if lift < 1.15:
                continue
            multi = 1.4 if " " in norm else 1.0        # prefer multi-word entities
            score = n * math.log(1.0 + lift) * multi
            rows.append((norm, n, score, sorted(ids)))
        rows.sort(key=lambda r: -r[2])
        picked, seen = [], set()
        for norm, n, score, ids in rows:
            if len(picked) >= 15:
                break
            ws = set(norm.split())
            if ws & seen:                              # collapse overlapping terms
                continue
            picked.append({"term": disp.get(norm, norm), "count": n, "event_ids": ids[:80]})
            seen |= ws
        return picked

    def block(subset):
        return {"en": rank(subset, "title", terms_en),
                "hi": rank(subset, "title_hi", terms_hi)}

    natl = [e for e in events if (e.get("region") or "India") != "World"]
    intl = [e for e in events if (e.get("region") or "India") == "World"]
    return {"national": block(natl), "international": block(intl)}


def _rfc822(iso):
    """ISO timestamp -> RFC-822 date for RSS <pubDate> (e.g. 'Sun, 09 Aug 2026 16:41:00 +0000')."""
    from email.utils import format_datetime
    from datetime import timezone
    try:
        dt = datetime.fromisoformat((iso or "").replace("Z", "").replace(" ", "T"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return format_datetime(dt)
    except (ValueError, TypeError):
        return format_datetime(datetime.now(timezone.utc))


def _rss_slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "news"


def _rss_xml(title, channel_link, self_url, rows, limit):
    """Build one RSS 2.0 feed. Each item carries the headline, the neutral summary,
    and the arithmetic bias line (Left · Centre · Right · n) - Paksh's whole point,
    right in the feed - plus the branded share card as an <enclosure> image. Static:
    written once at build time, no server."""
    from email.utils import format_datetime
    from datetime import timezone
    esc = lambda x: _html.escape(str(x or ""), quote=True)
    items = []
    for r in rows[:limit]:
        sid = r["id"]
        su = "%s/story/%s" % (SITE_URL, sid)
        c = r.get("lean_counts") or {}
        L, C, R = int(c.get("left", 0)), int(c.get("center", 0)), int(c.get("right", 0))
        summ = r.get("summary") or ""
        if isinstance(summ, (list, tuple)):
            summ = " ".join(str(x) for x in summ)
        desc = ("%s Coverage: Left %d · Centre %d · Right %d."
                % (summ.strip(), L, C, R)).strip()
        items.append(
            "<item>"
            "<title>%s</title>"
            "<link>%s</link>"
            "<guid isPermaLink=\"true\">%s</guid>"
            "<pubDate>%s</pubDate>"
            "<category>%s</category>"
            "<description><![CDATA[%s]]></description>"
            "<enclosure url=\"%s/static/og/%s.png\" type=\"image/png\" length=\"0\"/>"
            "</item>"
            % (esc(r.get("title")), su, su, _rfc822(r.get("published_at") or r.get("created_at")),
               esc(r.get("topic") or "News"), desc.replace("]]>", "]]&gt;"), SITE_URL, sid))
    now = format_datetime(datetime.now(timezone.utc))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n<channel>\n'
        "<title>%s</title>\n<link>%s</link>\n"
        '<atom:link href="%s" rel="self" type="application/rss+xml"/>\n'
        "<description>Compare how India's media, left, centre and right, "
        "covers each story, side by side.</description>\n"
        "<language>en</language>\n<lastBuildDate>%s</lastBuildDate>\n<ttl>60</ttl>\n"
        "%s\n</channel>\n</rss>\n"
        % (esc(title), esc(channel_link), esc(self_url), now, "\n".join(items)))


def _rmtree_safe(path: Path, attempts: int = 5, delay: float = 0.5):
    """shutil.rmtree, retrying briefly on Windows file-lock errors (a lingering handle
    from a dev server, or antivirus scanning a just-written file) instead of failing
    outright. No-op if the path doesn't exist."""
    if not path.exists():
        return
    last_err = None
    for _ in range(attempts):
        try:
            shutil.rmtree(path)
            return
        except OSError as e:
            last_err = e
            time.sleep(delay)
    raise last_err


def _rename_safe(src: Path, dst: Path, attempts: int = 5, delay: float = 0.5):
    """Path.rename, with the same short retry as _rmtree_safe (same Windows lock risk)."""
    last_err = None
    for _ in range(attempts):
        try:
            src.rename(dst)
            return
        except OSError as e:
            last_err = e
            time.sleep(delay)
    raise last_err


def _publish_build(build_dir: Path, final_dir: Path):
    """Swap a finished build into place. Windows can't atomically replace a directory in
    one call the way POSIX rename can (os.replace refuses when the destination is a
    directory), so this uses the standard two-rename dance: move the old site aside, move
    the new one in, then discard the old one. The window where `_site` doesn't exist at
    all is one directory rename (milliseconds), not the minutes a full rebuild takes."""
    old_dir = final_dir.parent / (final_dir.name + ".old")
    _rmtree_safe(old_dir)                      # leftover from a previous interrupted swap
    if final_dir.exists():
        _rename_safe(final_dir, old_dir)
    _rename_safe(build_dir, final_dir)
    _rmtree_safe(old_dir)                       # best-effort; a lingering .old dir is harmless


def main():
    init_db()

    # Build into a scratch directory, never the live `_site`, so a failure at ANY stage
    # below (Tailwind CLI, JSX precompile, a bad event row, anything) leaves the last
    # known-good `_site` completely untouched. Only a build that finishes clean gets
    # swapped into place, at the very end.
    global OUT
    final_dir = OUT
    build_dir = ROOT / "_site.building"
    _rmtree_safe(build_dir)          # clear a leftover scratch dir from a previous crash
    build_dir.mkdir(parents=True)
    OUT = build_dir

    try:
        # 1) the app shell + assets
        shutil.copytree(ROOT / "static", OUT / "static")
        _precompile_jsx()   # static/app.jsx -> _site/static/app.js (no Babel shipped to browser)
        _build_tailwind()   # -> _site/static/tailwind.css (no cdn.tailwindcss.com at runtime)
        # the served shell: inject the real domain so canonical / OG / sitemap all agree.
        # Flip SITE_URL (above) when you cut over to paksh.news - nothing else to edit.
        host = SITE_URL.split("://", 1)[-1].rstrip("/")
        shell = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        shell = shell.replace("https://paksh.vercel.app", SITE_URL).replace("paksh.vercel.app", host)
        (OUT / "index.html").write_text(shell, encoding="utf-8")

        # 2) the data the SPA reads (mirrors the API exactly)
        events = get_all_events()
        _now = datetime.utcnow()

        # Storylines: stitch separate events into sagas tracked across days (derived only; never
        # touches a bias count). story_map: event_id -> storyline_id; story_by_id: the full thread.
        storylines, story_map, story_by_id = [], {}, {}
        try:
            from storylines import build_storylines
        except Exception:                   # storyline linking is non-fatal: the site builds without it
            build_storylines = None
        if build_storylines is not None:
            try:
                storylines, story_map = build_storylines(events)
                story_by_id = {s["id"]: s for s in storylines}
                print(f"  storylines: {len(storylines)} sagas covering {len(story_map)} events")
            except Exception as _e:
                print(f"  storylines: skipped ({_e})")

        # Split the feed payload so first paint isn't a 12+ MB download that grows forever.
        # get_all_events() is newest-first, so events[:N] is the recent feed everyone loads up
        # front; the older tail goes to events-archive.json, which the SPA fetches LAZILY only
        # when someone opens Search / a Topic (see app.jsx). Same row shape in both, so search /
        # topic cards render identically -- nothing is lost, it just arrives on demand. Every
        # story also keeps its own /data/events/<id>.json + pre-rendered HTML (SEO untouched).
        recent, archive = events[:RECENT_FEED_N], events[RECENT_FEED_N:]
        recent_rows = [feed_row(e, story_map, _now) for e in recent]
        write_json(OUT / "data" / "events.json", {"events": recent_rows})
        write_json(OUT / "data" / "events-archive.json", {"events": [feed_row(e, story_map, _now) for e in archive]})
        # Storylines: a LEAN index (no per-event payload) that every visitor can afford, plus one
        # full file per saga (with its dated events) fetched only when a Storyline page is opened.
        _sl_index = [{k: s.get(k) for k in ("id","title","title_hi","topic","region","n_events","start","end","updated_at")} for s in storylines]
        write_json(OUT / "data" / "storylines.json", {"storylines": _sl_index})
        for s in storylines:
            write_json(OUT / "data" / "storylines" / f"{s['id']}.json", s)

        # per-story social share cards (bias bar). og_ids = the stories that got one, so
        # _story_html can point og:image at the card and everything else falls back cleanly.
        og_ids = _build_og_cards(recent_rows, OG_CARD_N)

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
            row = feed_row(e, story_map, _now)
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
        # Paksh 7B (overnight hardening): batched via get_events_by_ids() instead of
        # calling get_event() once per event in this loop - measured 324.85s -> 1.28s
        # (253x) over the full 13,814-event corpus, zero output differences. Same N+1
        # pattern already fixed in reframe.py::_collect() (Phase 7B F3); this loop runs
        # on every export_static.py build (every scheduled refresh), so it was the
        # larger real-world cost of the two.
        full_by_id = get_events_by_ids([e["id"] for e in events])

        # Phase 21G: verified Story Memory context (a SEPARATE mechanism from Storyline
        # above - Storyline is broad similarity-based grouping; this is a Stage-2-VERIFIED
        # relationship to one specific prior event, with a frozen historical snapshot). Same
        # non-fatal degradation pattern as storylines: an import or runtime failure here
        # must never break the export - the site builds without it, exactly like storylines.
        # Read-only, no LLM calls, one connection reused across the whole loop (matching this
        # loop's own batching philosophy above).
        build_story_context, sm_conn = None, None
        try:
            from reader_context import build_story_context
            import database as _database
            sm_conn = _database.get_connection()
        except Exception:
            build_story_context = None
        story_urls = []
        for e in events:
            full = full_by_id.get(e["id"])
            if full is None:
                continue
            full = _clean_text(full)
            # attach the saga thread this story belongs to (if any), so the Story page can show
            # "how this developed" without another fetch. Small payload (<=25 short entries).
            _sid = story_map.get(e["id"])
            if _sid and _sid in story_by_id:
                full["storyline"] = story_by_id[_sid]
            if build_story_context is not None:
                try:
                    sc = build_story_context(sm_conn, e["id"])
                    if sc:
                        full["story_context"] = sc
                except Exception:
                    pass  # non-fatal - see comment above
            write_json(OUT / "data" / "events" / f"{e['id']}.json", full)
            sp = OUT / "story" / f"{e['id']}.html"
            sp.parent.mkdir(parents=True, exist_ok=True)
            sp.write_text(_story_html(shell, full, og_ids), encoding="utf-8")
            story_urls.append((f"{SITE_URL}/story/{e['id']}", full.get("created_at")))
        if sm_conn is not None:
            sm_conn.close()

        # 4) Vercel routing. IMPORTANT: we use the legacy `routes` array, NOT cleanUrls+rewrites.
        #    The modern `{cleanUrls:true, rewrites:[/(.*)->/index.html]}` combo SILENTLY FAILS on
        #    Vercel: cleanUrls shadows the catch-all rewrite, so every path without a real file
        #    (/about, /sources, /search, /topic/X, /topics, /blindspot) returned a hard 404 on
        #    refresh / shared link / crawler, while headers still applied (that's how we diagnosed
        #    it). `routes` + an explicit `filesystem` handle is the battle-tested SPA fallback:
        #    real files win first, then the shell renders every in-app route. `routes` is mutually
        #    exclusive with cleanUrls/rewrites/headers/trailingSlash, so headers live here too.
        #    Verify after deploy:  curl -I https://paksh.vercel.app/about   -> HTTP/2 200
        # --- Content-Security-Policy ---------------------------------------------------------
        # Rolled out SAFELY. `Content-Security-Policy` (ENFORCING) carries only the STRUCTURAL
        # directives that cannot break resource loading: no clickjacking (frame-ancestors none +
        # X-Frame-Options DENY), no plugins (object-src none), no <base> hijack (base-uri self),
        # no form hijack (form-action). The full resource policy (script/style/img/font/connect)
        # ships as `Content-Security-Policy-Report-Only` FIRST so we can watch the live console for
        # violations and fix any missed source BEFORE it can white-screen the site. Once a clean
        # deploy shows no report-only violations, copy _CSP_STRICT into the enforcing header.
        # (Enabled by self-hosting React + moving the theme script to a file, so script-src='self'.)
        # ENFORCING: NO default-src here on purpose. default-src 'self' would fall through to
        # style-src and block the app's (heavy) inline styles -> broken/blank page. Only the
        # STRUCTURAL directives that don't govern resource loading are enforced; the full
        # resource policy (which sets style-src 'unsafe-inline' etc.) rides in Report-Only until
        # verified, then gets promoted.
        _CSP_ENFORCE = ("frame-ancestors 'none'; object-src 'none'; "
                        "base-uri 'self'; form-action 'self' https://formspree.io")
        _CSP_STRICT = (
            "default-src 'self'; "
            "script-src 'self'; "                                    # self-hosted React + app.js + /_vercel/insights
            "style-src 'self' 'unsafe-inline'; "                     # React inline styles + self-hosted fonts.css
            "font-src 'self' data:; "                                # fonts are self-hosted (fetch_fonts.py)
            "img-src 'self' data: https:; "                          # publisher thumbnails come from many domains
            # Supabase Auth (GoTrue) + PostgREST for accounts / Reading Lens / Saved (direct REST,
            # no SDK). Publishable anon key only; RLS guards every table. Formspree = contact form.
            "connect-src 'self' https://formspree.io https://vitals.vercel-insights.com https://zzjsjqqcpyyodatlmcux.supabase.co; "
            "frame-ancestors 'none'; frame-src 'none'; object-src 'none'; "
            "base-uri 'self'; form-action 'self' https://formspree.io; "
            "manifest-src 'self'; worker-src 'self'"
        )
        _sec_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": ("camera=(), microphone=(), geolocation=(), browsing-topics=(), "
                                   "payment=(), usb=(), magnetometer=(), gyroscope=(), interest-cohort=()"),
            "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
            "Cross-Origin-Opener-Policy": "same-origin",
            "X-Permitted-Cross-Domain-Policies": "none",
            "X-DNS-Prefetch-Control": "off",
            "Content-Security-Policy": _CSP_ENFORCE,
            "Content-Security-Policy-Report-Only": _CSP_STRICT,
        }
        write_json(OUT / "vercel.json", {
            "routes": [
                # 1) security headers on every response, then keep routing
                {"src": "/(.*)", "headers": _sec_headers, "continue": True},
                # 2) serve any real file: /index.html, /static/*, /data/*, /story/<id>.html,
                #    robots.txt, sitemap.xml, favicons, og.png ...
                {"handle": "filesystem"},
                # 3) pretty story URLs -> the pre-rendered crawlable page
                {"src": "/story/([^/]+)/?$", "dest": "/story/$1.html"},
                # 4) keep the (absent) API 404 so the SPA's static-mode probe stays a fast 404
                {"src": "/api/(.*)", "status": 404},
                # 5) SPA fallback: every other in-app route renders the shell (History API + SEO)
                {"src": "/(.*)", "dest": "/index.html"},
            ],
        })

        # 5) robots + sitemap (homepage + every story)
        (OUT / "robots.txt").write_text(
            "User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\nRSS: %s/rss.xml\n"
            % (SITE_URL, SITE_URL), encoding="utf-8")
        rows = ['  <url><loc>%s/</loc><changefreq>hourly</changefreq><priority>1.0</priority></url>' % SITE_URL]
        # section + info pages (now that routing serves them; previously they 404'd AND were
        # missing here, so they were invisible to search). Topic pages are strong SEO surfaces
        # ("Politics, every side") -> one entry per distinct topic present.
        section_paths = ["/topics", "/blindspot", "/about", "/sources", "/support"]
        topic_names = sorted({e.get("topic") for e in events if e.get("topic")})
        from urllib.parse import quote
        for p in section_paths:
            rows.append('  <url><loc>%s%s</loc><changefreq>daily</changefreq><priority>0.6</priority></url>' % (SITE_URL, p))
        for name in topic_names:
            rows.append('  <url><loc>%s/topic/%s</loc><changefreq>daily</changefreq><priority>0.6</priority></url>'
                        % (SITE_URL, quote(name, safe="")))
        for u, ts in story_urls:
            lm = "<lastmod>%s</lastmod>" % ts[:10] if ts else ""
            rows.append('  <url><loc>%s</loc>%s<changefreq>daily</changefreq><priority>0.7</priority></url>' % (u, lm))
        (OUT / "sitemap.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(rows) + "\n</urlset>\n", encoding="utf-8")

        # 6) RSS feeds (static). A main feed of the newest stories, plus one per topic so a
        # reader can subscribe to just Politics / Economy / etc. recent_rows is newest-first
        # and already carries title/summary/topic/lean_counts, so no extra work. Each feed
        # item shows the bias line and the share card, so even a feed reader sees the split.
        from urllib.parse import quote as _q
        (OUT / "rss.xml").write_text(
            _rss_xml("Paksh: Every side of India's news",
                     SITE_URL + "/", SITE_URL + "/rss.xml", recent_rows, 60),
            encoding="utf-8")
        rss_dir = OUT / "rss"
        rss_dir.mkdir(parents=True, exist_ok=True)
        by_topic = {}
        for r in recent_rows:
            tp = r.get("topic")
            if tp:
                by_topic.setdefault(tp, []).append(r)
        for tp, trows in by_topic.items():
            (rss_dir / ("%s.xml" % _rss_slug(tp))).write_text(
                _rss_xml("Paksh: %s" % tp, "%s/topic/%s" % (SITE_URL, _q(tp, safe="")),
                         "%s/rss/%s.xml" % (SITE_URL, _rss_slug(tp)), trows, 40),
                encoding="utf-8")
        print("  rss: /rss.xml + %d topic feeds" % len(by_topic))
    except BaseException:
        # the build failed (or was interrupted) - never touch the live _site; just
        # clean up the scratch dir and let the original error/exit-code propagate.
        OUT = final_dir
        _rmtree_safe(build_dir)
        raise

    OUT = final_dir
    _publish_build(build_dir, OUT)

    print(f"Built static site in {OUT}")
    print(f"  events: {len(events)}  |  one-sided: {len(get_blindspot_events())}  "
          f"|  sources: {len(SOURCES)}")
    print("Preview:  python -m http.server -d _site 8080  ->  http://localhost:8080")


if __name__ == "__main__":
    main()