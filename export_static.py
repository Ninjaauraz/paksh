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
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

from database import (
    init_db, get_all_events, get_blindspot_events, get_topics, get_events_by_ids,
    get_connection,
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

# --- Content-Security-Policy (ENFORCED) ------------------------------------------------------------
# Promoted from Report-Only after live evidence: with ads actually being served, the full strict policy
# produced NO violation for scripts (self-hosted React/app.js, /_vercel/insights), styles, fonts, images,
# Supabase, Formspree or Vercel vitals - the only violations were Google's ad hosts, allowlisted below.
# Those hosts are needed ONLY after a visitor allows advertising (static/app.jsx loadAdSense injects the
# AdSense script after explicit consent; index.html no longer contains it). A static header cannot depend
# on consent, so the allowlist is present for everyone, but nothing is contacted until consent is given.
#   script-src : pagead2.googlesyndication.com (adsbygoogle.js, show_ads_impl), *.adtrafficquality.google
#                (sodar - Google's ad-traffic-quality script). No 'unsafe-inline', no 'unsafe-eval':
#                neither was observed to be required.
#   frame-src  : the ad iframes (googleads.g.doubleclick.net, tpc.googlesyndication.com) and the two
#                helper frames Google opens (*.adtrafficquality.google, www.google.com).
#   connect-src: *.adtrafficquality.google (sodar config), pagead2.googlesyndication.com.
# style-src keeps 'unsafe-inline' because the React app renders inline style attributes.
# default-src 'self' is safe now precisely because every legitimate source is listed explicitly.
CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self' https://pagead2.googlesyndication.com https://*.adtrafficquality.google; "
    "style-src 'self' 'unsafe-inline'; "
    "font-src 'self' data:; "
    "img-src 'self' data: https:; "                        # publisher thumbnails + ad creatives come from many hosts
    "connect-src 'self' https://formspree.io https://vitals.vercel-insights.com "
    "https://zzjsjqqcpyyodatlmcux.supabase.co https://pagead2.googlesyndication.com "
    "https://*.adtrafficquality.google; "
    "frame-src https://googleads.g.doubleclick.net https://tpc.googlesyndication.com "
    "https://*.adtrafficquality.google https://www.google.com; "
    "frame-ancestors 'none'; object-src 'none'; "
    "base-uri 'self'; form-action 'self' https://formspree.io; "
    "manifest-src 'self'; worker-src 'self'"
)
# Phase 35: must match the "ca-pub-..." id in the AdSense loader <script> hardcoded in
# static/index.html (without the "ca-" prefix - ads.txt uses the bare "pub-..." form), and,
# once it goes live, the ADSENSE_CLIENT constant in static/app.jsx. Google's ads.txt crawler
# checks this file at the domain root; without it (or with the wrong id) AdSense can refuse
# to fill ad requests even when everything else is configured correctly.
ADSENSE_PUBLISHER_ID = "pub-3441154254234680"
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


def feed_row(e, story_map, now, homepage_score=None):
    """Shape one event for events.json / events-archive.json (and, since Phase 1.75,
    main.py's live /api/events-archive) - lightened payload + importance + feed_rank +
    storyline_id. Module-level (not a build()-local closure) specifically so main.py can
    import and call the exact same function rather than re-deriving these fields.

    `homepage_score`, if given (a float from homepage_rank.homepage_rank_story()'s
    "score"), becomes feed_rank directly - the deterministic, explainable, multi-signal
    homepage ranking (recency + coverage velocity + publisher breadth + independent
    origins + developments + India relevance; see homepage_rank.py) now used for the
    front page. When absent (events outside the ranked candidate pool - e.g. the
    archive tail, which never reaches the home feed anyway), falls back to the
    original breadth*recency*civic-weight formula so every event still gets SOME
    ordering value and this stays backward compatible for any caller (main.py) that
    doesn't pass one."""
    d = _lighten(e)
    d["importance"] = _importance(e, now)   # existing field; untouched, used elsewhere
    if homepage_score is not None:
        d["feed_rank"] = round(homepage_score, 4)
    else:
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
    # Provenance (production hardening): who wrote this analysis, who holds the rights, and what it
    # was built from. The summary/framing text is Paksh's own synthesis; the outlets whose
    # reporting it compares are the CITED inputs, not co-authors. Capped so a 60-outlet story does
    # not bloat every page; the full outlet list is already in the crawlable body below.
    ld["author"] = {"@type": "Organization", "name": "Paksh", "url": SITE_URL + "/"}
    ld["copyrightHolder"] = {"@type": "Organization", "name": "Redstocks Technology LLP"}
    _pub = str(ld.get("datePublished") or "")[:4]
    if _pub.isdigit():
        ld["copyrightYear"] = int(_pub)
    _based = []
    for _s in (ev.get("sources") or []):
        _u = (_s or {}).get("url") or ""
        if _u.startswith(("http://", "https://")) and len(_based) < 8:
            _based.append({"@type": "NewsArticle", "url": _u,
                           "headline": str(_s.get("headline") or "")[:110],
                           "publisher": {"@type": "Organization", "name": str(_s.get("source") or "")}})
    if _based:
        ld["isBasedOn"] = _based
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


def _page_meta_html(shell, title, description, canonical_url, noindex=False):
    """Phase 40B: the metadata-only sibling of _story_html(), for routes that need their
    OWN <title>/description/canonical/OG so they stop inheriting the homepage's (the
    verified Phase 40A canonical-conflict). Unlike _story_html() this does NOT touch
    #root's content - these pages' actual content legitimately stays client-rendered
    (that's a content/architecture question for a later phase, not this one); only the
    metadata a crawler reads before/without running JS changes. No NewsArticle JSON-LD
    is added (these aren't articles) and no marketing copy is invented - description is
    either reused verbatim or a straight template substitution of the existing sentence."""
    esc = lambda x: _html.escape(str(x or ""), quote=True)
    rep = [
        ("<title>Paksh: Every side of India's news</title>",
         "<title>%s</title>" % esc(title)),
        ('<meta name="description" content="Paksh compares how India\'s media, left, centre and right, covers each story, side by side, in English and Hindi."/>',
         '<meta name="description" content="%s"/>' % esc(description)),
        ('<link rel="canonical" href="%s/"/>' % SITE_URL,
         ('<link rel="canonical" href="%s"/>' % canonical_url) if canonical_url else ""),
        ('<meta property="og:title" content="Paksh: Every side of India\'s news"/>',
         '<meta property="og:title" content="%s"/>' % esc(title)),
        ('<meta property="og:description" content="Compare how India\'s media, left, centre and right, covers each story, side by side, in English and Hindi."/>',
         '<meta property="og:description" content="%s"/>' % esc(description)),
        ('<meta property="og:url" content="%s/"/>' % SITE_URL,
         ('<meta property="og:url" content="%s"/>' % canonical_url) if canonical_url else ""),
        ('<meta name="twitter:title" content="Paksh: Every side of India\'s news"/>',
         '<meta name="twitter:title" content="%s"/>' % esc(title)),
        ('<meta name="twitter:description" content="Compare how India\'s media, left, centre and right, covers each story, side by side, in English and Hindi."/>',
         '<meta name="twitter:description" content="%s"/>' % esc(description)),
    ]
    if noindex:
        rep.append(('<meta name="robots" content="index, follow"/>',
                    '<meta name="robots" content="noindex, follow"/>'))
    for a, b in rep:
        shell = shell.replace(a, b, 1)
    return shell


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


class ExportCollapseError(RuntimeError):
    """Raised when a fresh export would publish drastically fewer events than the
    site currently live on disk - a second, independent guard against exactly the
    failure mode that let a wrong (e.g. repo-local, forked) database silently
    overwrite a healthy _site (2026-09-22/23 incidents: export_static.py itself was
    never at fault, it faithfully exported whatever database.py handed it - this
    guard assumes THAT could happen again despite the path-resolution fix, and
    catches the symptom directly, independent of whatever caused it). Never
    compares against a hard-coded expected count - only against whatever the
    CURRENT live _site already has, so it stays correct as the real corpus grows
    or shrinks over time."""


EXPORT_MIN_RETENTION_FRACTION = 0.5   # a legitimate day's cleanup/consolidation never
                                       # halves the publishable set in one run; a
                                       # forked or empty database does


def _count_event_files(site_dir: Path) -> int:
    events_dir = site_dir / "data" / "events"
    if not events_dir.is_dir():
        return 0
    return sum(1 for _ in events_dir.glob("*.json"))


def _check_export_plausible(new_count: int, final_dir: Path):
    """Compare this build's publishable-event count against the count already on
    disk in the LIVE _site (final_dir) - which is untouched until _publish_build()
    runs, so it always holds exactly the previous successful export's own output.
    Raises ExportCollapseError, and does nothing else, if that would be an abnormal
    collapse. Skipped entirely when there is nothing yet to compare against (a
    fresh checkout / first-ever build)."""
    previous_count = _count_event_files(final_dir)
    if previous_count == 0:
        return
    if new_count < previous_count * EXPORT_MIN_RETENTION_FRACTION:
        raise ExportCollapseError(
            f"export produced {new_count} publishable events, down from {previous_count} "
            f"currently live ({new_count / previous_count:.0%} of the previous count) - "
            f"a bigger drop than any legitimate single run should cause. This is exactly "
            f"the shape of a database-path failure (e.g. a forked/empty repo-local "
            f"paksh.db instead of the real one), not normal content churn. Aborting BEFORE "
            f"touching the live _site. If this collapse is genuinely intended (e.g. a "
            f"deliberate mass cleanup), rerun with PAKSH_ALLOW_EXPORT_COLLAPSE=1.")


def _publish_build(build_dir: Path, final_dir: Path):
    """Swap a finished build into place. Windows can't atomically replace a directory in
    one call the way POSIX rename can (os.replace refuses when the destination is a
    directory), so this uses the standard two-rename dance: move the old site aside, move
    the new one in, then discard the old one. The window where `_site` doesn't exist at
    all is one directory rename (milliseconds), not the minutes a full rebuild takes.

    Auto-rollback hardening (2026-09-24 incident): a PERSISTENT failure on the second
    rename used to leave `final_dir` (_site) missing indefinitely - the old build sat
    safely at `old_dir` (_site.old) as a "manual fallback", but nothing ever restored it
    automatically, and production stayed broken until a human noticed. Real incident: a
    stale http.server holding a handle on _site caused exactly this second rename to fail
    after the first had already succeeded, and a routine git commit made minutes later
    faithfully captured (and pushed) the resulting "_site deleted" state. If the second
    rename fails now, the first rename is undone (old_dir -> final_dir) before re-raising,
    so a contended/interrupted swap degrades to "still serving the previous build", never
    to "no _site at all" - `build_dir` (the new, unpublished build) is left untouched
    either way, so a retried publish can still pick it up. Cleanup of `old_dir` at the very
    end stays best-effort only (a lingering .old directory is harmless and must never be
    reported as an export failure once the swap itself has already succeeded)."""
    old_dir = final_dir.parent / (final_dir.name + ".old")
    _rmtree_safe(old_dir)                      # leftover from a previous interrupted swap
    moved_old_away = False
    if final_dir.exists():
        _rename_safe(final_dir, old_dir)
        moved_old_away = True
    try:
        # Phase 30C-G: THIS rename follows immediately after writing thousands of fresh
        # files (1500+ OG-card PNGs alone in a real run) - a safe, isolated repro
        # (test_phase30cg_export_lock.py) reproduced a real WinError 5 "Access is
        # denied" on this exact call 1/5 times at that file volume (0/20 at trivial
        # volume), using the default retry budget (5 x 0.5s = 2.5s total) - consistent
        # with a transient Windows sharing-violation (most likely real-time antivirus/
        # indexing scanning the just-written batch) outlasting that short a window,
        # not a deterministic bug in the rename itself. A longer bounded retry here
        # ONLY (build_dir was JUST written; old_dir above is the already-settled
        # previous build and doesn't need this) gives that lock time to clear
        # naturally.
        _rename_safe(build_dir, final_dir, attempts=20, delay=1.0)
    except OSError:
        if moved_old_away:
            # Restore the previous, known-good site rather than leaving `_site` missing.
            # If THIS rename also fails, that new exception propagates instead (chained
            # via __context__) - a double failure needs a human either way, but we still
            # try, since "still trying" costs nothing here.
            _rename_safe(old_dir, final_dir, attempts=20, delay=1.0)
        raise
    # Best-effort only past this point: the swap itself already succeeded (the new
    # _site is live), so a failure to clean up the now-unneeded old copy must never be
    # reported as an export failure.
    try:
        _rmtree_safe(old_dir)
    except OSError:
        pass


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

        # Deterministic homepage ranking (deferred import - same reason storylines is
        # deferred just above: keep a plain `import export_static` cheap for callers
        # like supabase_content.py that only want feed_row()/_lighten()/etc, and avoid
        # a circular import - homepage_rank imports CIVIC_KEYWORDS/CIVIC_TOPIC_WEIGHT
        # back from this module). Scored over `recent` only - ranking only matters for
        # stories that could plausibly reach the home feed; the archive tail keeps the
        # cheap fallback feed_rank in feed_row() and is never shown as a ranked feed.
        homepage_scores, homepage_sections = {}, {}
        try:
            import homepage_rank
            _hp_conn = get_connection()
            _hp_ids = [e["id"] for e in recent]
            _hp_si = homepage_rank.fetch_si_signals(_hp_conn, _hp_ids)
            _hp_vel = homepage_rank.fetch_velocity_signals(_hp_conn, _hp_ids, _now)
            _hp_conn.close()
            _hp_ranked = []
            for e in recent:
                r = homepage_rank.homepage_rank_story(e, _hp_si[e["id"]], _hp_vel[e["id"]], _now)
                r["momentum"] = homepage_rank.momentum_score(e, _hp_si[e["id"]], _hp_vel[e["id"]], _now)
                r["event"] = e
                homepage_scores[e["id"]] = r["score"]
                _hp_ranked.append(r)
            homepage_sections = homepage_rank.select_homepage_sections(_hp_ranked)
            print(f"  homepage: ranked {len(recent)} candidates -> sections "
                  f"{', '.join(f'{k}({len(v)})' for k, v in homepage_sections.items())}")
        except Exception as _e:
            print(f"  homepage: ranking skipped ({_e}); feed_rank falls back to breadth*recency")

        recent_rows = [feed_row(e, story_map, _now, homepage_scores.get(e["id"])) for e in recent]
        write_json(OUT / "data" / "events.json", {"events": recent_rows})
        if homepage_sections:
            write_json(OUT / "data" / "homepage.json", {
                "generated_at": _now.isoformat(),
                "sections": {
                    name: [{"id": r["event"]["id"], "score": r["score"], "momentum": r["momentum"]}
                           for r in rows]
                    for name, rows in homepage_sections.items()
                },
            })
        # Editorial section taxonomy (India, Politics & Policy, Economy, Finance & Markets,
        # Defence & Security, Technology, India & World, World, Society, Health, Science &
        # Space, Sports, Culture & Entertainment) - a reader-facing NAVIGATION layer, entirely
        # separate from the raw per-event `topic` field that still drives /topic/<name> below
        # (untouched) and from homepage_sections above (layout zones, not subjects). Reuses the
        # exact si_map/vel_map/recent already computed for homepage ranking just above - no
        # second DB pass, and section_rank.py itself reuses homepage_rank's breadth/independence/
        # velocity/dev/freshness/india formula rather than reimplementing it. Additive only: a
        # failure here never touches events.json/homepage.json/the topic pages already written.
        # Phase (regression fix): section MEMBERSHIP (the full classified library a reader
        # can browse) is a different question from section RANKING (which stories lead) -
        # select_all_sections_full() returns both. story_ids stays the top-N ranked/
        # diversified list (drives the lead + secondary editorial area, unchanged from
        # before); all_story_ids is the FULL pool, uncapped, newest-first (drives the
        # section's "show more" library, same completeness TopicPage's own /topic/<name>
        # pages already give readers - see static/app.jsx's SectionPage).
        if homepage_sections:
            try:
                import section_rank
                _section_data = section_rank.select_all_sections_full(recent, _hp_si, _hp_vel, _now)
                sections_payload = {
                    "generated_at": _now.isoformat(),
                    "sections": [
                        {
                            "key": key,
                            "slug": key.replace("_", "-"),
                            "label": data["label"],
                            "lead_id": data["lead"]["event"]["id"],
                            "story_ids": [r["event"]["id"] for r in data["top_stories"]],
                            "all_story_ids": [r["event"]["id"] for r in data["all_stories"]],
                        }
                        for key, data in _section_data.items()
                    ],
                }
                write_json(OUT / "data" / "sections.json", sections_payload)
                print(f"  sections: {len(sections_payload['sections'])} of {len(section_rank.SECTIONS)} "
                      f"editorial sections qualified "
                      f"({', '.join(s['key'] + '(' + str(len(s['story_ids'])) + '/' + str(len(s['all_story_ids'])) + ')' for s in sections_payload['sections'])})")
            except Exception as _e:
                print(f"  sections: skipped ({_e})")
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
        _COL_N = 40   # the SMALL list that ships in blindspots.json (loaded on every page for the
                      # homepage teasers). The Coverage Gaps page itself loads the COMPLETE ranked
                      # list from blindspots-all.json (below) - before that file existed the page
                      # could show at most 40 per column while its own header counted every gap
                      # (e.g. "314"), and the per-language filter then trimmed each column further.
        _ALL_CAP = 1000   # sanity ceiling on the complete list only (never reached today)
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
        # The complete, identically-ranked list, fetched lazily by the Coverage Gaps page only.
        write_json(OUT / "data" / "blindspots-all.json", {
            "left_heavier": [r for _, r in buckets["left"][:_ALL_CAP]],
            "right_heavier": [r for _, r in buckets["right"][:_ALL_CAP]],
            "aggregate": {"total": agg["left_heavier"] + agg["right_heavier"],
                          "left_heavier": agg["left_heavier"], "right_heavier": agg["right_heavier"]},
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

        # 3b) Phase 40B: self-canonical HTML for topic + section hub pages, so they stop
        # inheriting the homepage's canonical (the verified Phase 40A conflict: these were
        # in the sitemap AND declaring themselves a duplicate of "/" at the same time).
        # Content stays client-rendered exactly as before (in scope: metadata/canonical
        # only, not a content/SSR change) - _page_meta_html() only rewrites <title>/
        # description/canonical/OG, never #root. File names use the SAME percent-encoding
        # as the sitemap/router already use for topic URLs (urllib.parse.quote), so the
        # Vercel route below matches byte-for-byte with no decode/re-encode ambiguity.
        from urllib.parse import quote as _quote
        topic_names_sorted = sorted({e.get("topic") for e in events if e.get("topic")})
        _DESC = "Paksh compares how India's media, left, centre and right, covers each story, side by side, in English and Hindi."
        for name in topic_names_sorted:
            enc = _quote(name, safe="")
            tp = OUT / "topic" / f"{enc}.html"
            tp.parent.mkdir(parents=True, exist_ok=True)
            tp.write_text(_page_meta_html(
                shell,
                title="%s | Paksh" % name,
                description="Paksh compares how India's media, left, centre and right, covers %s news, side by side, in English and Hindi." % name,
                canonical_url="%s/topic/%s" % (SITE_URL, enc),
            ), encoding="utf-8")
        # Phase 40B: titles match the CLIENT's own title effect for each route exactly
        # (static/app.jsx's document.title useEffect) - /about's own nav label is
        # "Method", not "About", so the static and post-hydration titles agree instead
        # of a crawler and a real visitor seeing two different titles for the same URL.
        _section_pages = [
            ("topics", "Sections | Paksh"),
            # Regression fix: /all-topics restores the raw-topic hub + Follow Topic as a
            # reachable page now that /topics itself shows the new editorial taxonomy - same
            # self-canonical treatment as every other fixed hub page here.
            ("all-topics", "All Topics | Paksh"),
            ("blindspot", "Coverage Gaps | Paksh"),
            ("about", "Method | Paksh"),
            ("sources", "Sources | Paksh"),
            ("support", "Support | Paksh"),
        ]
        for slug, title in _section_pages:
            (OUT / f"{slug}.html").write_text(_page_meta_html(
                shell, title=title, description=_DESC,
                canonical_url="%s/%s" % (SITE_URL, slug),
            ), encoding="utf-8")

        # Editorial section hub pages (/section/<slug>) - same self-canonical treatment as the
        # topic pages just above, for the same Phase 40B reason (an unlisted route otherwise
        # falls through to the SPA shell and inherits the HOMEPAGE's own canonical/title, which
        # is exactly the duplicate-canonical bug Phase 40B fixed for topics/section-hub pages;
        # skipping this here would quietly reintroduce that bug for 13 new URLs). The registry
        # (section_rank.SECTIONS) is a small, fixed, versioned set - same shape as _section_pages
        # above - so every slug always gets a file even if that section has no qualifying
        # stories today (SectionPage/section_rank already handle an empty section gracefully,
        # same as an empty/typo'd topic does).
        _editorial_section_slugs = []
        try:
            import section_rank as _sr
            for _key, _spec in _sr.SECTIONS.items():
                _slug = _key.replace("_", "-")
                _editorial_section_slugs.append((_slug, _spec["label"]))
                _sp = OUT / "section" / f"{_slug}.html"
                _sp.parent.mkdir(parents=True, exist_ok=True)
                _sp.write_text(_page_meta_html(
                    shell,
                    title="%s | Paksh" % _spec["label"],
                    description="Paksh's %s coverage, ranked and compared across India's media, left, centre and right." % _spec["label"],
                    canonical_url="%s/section/%s" % (SITE_URL, _slug),
                ), encoding="utf-8")
        except Exception as _e:
            print(f"  section pages: skipped ({_e})")

        # 3c) Phase 40B: a real 404 for invalid/deleted story ids (Phase 40A: a nonexistent
        # or deleted /story/<id> was returning HTTP 200 with the homepage's OWN indexable
        # title/canonical/robots - a soft-404). This file is only ever reached via the new
        # vercel.json rule below, which fires exactly when the pre-rendered story file
        # lookup for that id has already failed - never for a valid story.
        (OUT / "404.html").write_text(_page_meta_html(
            shell,
            title="Story not found | Paksh",
            description="This story doesn't exist or is no longer available on Paksh.",
            canonical_url=None,
            noindex=True,
        ), encoding="utf-8")

        # 4) Vercel routing. IMPORTANT: we use the legacy `routes` array, NOT cleanUrls+rewrites.
        #    The modern `{cleanUrls:true, rewrites:[/(.*)->/index.html]}` combo SILENTLY FAILS on
        #    Vercel: cleanUrls shadows the catch-all rewrite, so every path without a real file
        #    (/about, /sources, /search, /topic/X, /topics, /blindspot) returned a hard 404 on
        #    refresh / shared link / crawler, while headers still applied (that's how we diagnosed
        #    it). `routes` + an explicit `filesystem` handle is the battle-tested SPA fallback:
        #    real files win first, then the shell renders every in-app route. `routes` is mutually
        #    exclusive with cleanUrls/rewrites/headers/trailingSlash, so headers live here too.
        #    Verify after deploy:  curl -I https://paksh.vercel.app/about   -> HTTP/2 200
        # Content-Security-Policy: see CSP_POLICY at the top of this file (enforced, not report-only).
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
            "Content-Security-Policy": CSP_POLICY,
        }
        # Phase 40B: every OTHER host this Vercel project answers on must redirect to the
        # one canonical public origin (SITE_URL) instead of independently serving the same
        # content at 200 - Phase 40A verified all of these return 200 today with no
        # redirect, so Google can (and does) crawl/index duplicates of every page across
        # multiple hosts. Exact allowlist, not a negative/regex match, on purpose: a
        # mismatched negative pattern here could redirect SITE_URL to itself in a loop,
        # which an explicit "these specific other hosts" list cannot do.
        _ALT_HOSTS = [
            "www.paksh.news",
            "paksh.vercel.app",
            "paksh-ninjaaurazs-projects.vercel.app",
            "paksh-git-main-ninjaaurazs-projects.vercel.app",
        ]
        _topic_routes = [
            {"src": "/topic/%s/?$" % re.escape(_quote(name, safe="")),
             "dest": "/topic/%s.html" % _quote(name, safe=""), "check": True}
            for name in topic_names_sorted
        ]
        _section_routes = [
            {"src": "/%s/?$" % slug, "dest": "/%s.html" % slug, "check": True}
            for slug, _ in _section_pages
        ]
        _editorial_section_routes = [
            {"src": "/section/%s/?$" % re.escape(slug),
             "dest": "/section/%s.html" % slug, "check": True}
            for slug, _ in _editorial_section_slugs
        ]
        write_json(OUT / "vercel.json", {
            "routes": [
                # 0) canonical-domain enforcement: any request arriving on a non-canonical
                #    host (an old/alias Vercel domain) gets a real 308 to the same path on
                #    SITE_URL, before anything else runs. Requests already on SITE_URL never
                #    match this rule (host not in the list) and fall straight through.
                {"src": "/(.*)", "has": [{"type": "host", "value": {"inc": _ALT_HOSTS}}],
                 "status": 308, "headers": {"Location": SITE_URL + "/$1"}},
                # 1) security headers on every response, then keep routing
                {"src": "/(.*)", "headers": _sec_headers, "continue": True},
                # 1b) caching (production hardening): everything was max-age=0/must-revalidate, so a
                #     returning reader re-checked ~8 font files and React on every page view. Font
                #     filenames are content-hashed by their source (a changed font = a new name), so
                #     they are safe to cache for a year. The pinned React builds are not hashed, so a
                #     day (never immutable). app.js / tailwind.css / data stay revalidated so every
                #     deploy and every pipeline refresh is picked up immediately.
                {"src": "/static/fonts/(.*)",
                 "headers": {"Cache-Control": "public, max-age=31536000, immutable"}, "continue": True},
                {"src": "/static/vendor/(.*)",
                 "headers": {"Cache-Control": "public, max-age=86400"}, "continue": True},
                # 2) serve any real file: /index.html, /static/*, /data/*, /story/<id>.html,
                #    robots.txt, sitemap.xml, favicons, og.png ...
                {"handle": "filesystem"},
                # 3) pretty story URLs -> the pre-rendered crawlable page. check:true means
                #    Vercel falls through to the NEXT route (3b, a real 404) instead of the
                #    SPA shell when the event has no pre-rendered HTML.
                {"src": "/story/([^/]+)/?$", "dest": "/story/$1.html", "check": True},
                # 3b) Phase 40B: an invalid/deleted story id reaches here (3's check:true
                #     found no matching file) -> a REAL HTTP 404 with its own noindex page,
                #     not the homepage shell at 200 (the verified Phase 40A soft-404).
                {"src": "/story/([^/]+)/?$", "status": 404, "dest": "/404.html"},
                # 3c) Phase 40B: topic pages get their own self-canonical file (one exact
                #     rule per known topic name, using the same percent-encoding as the
                #     sitemap/router - no regex-vs-request encoding ambiguity possible).
                #     An unlisted/typo'd topic name matches none of these and falls through
                #     to the SPA shell exactly as before (unchanged for that case).
                *_topic_routes,
                # 3d) Phase 40B: the fixed set of section/hub pages, same self-canonical
                #     pattern as topics above.
                *_section_routes,
                # 3e) the 13-section editorial taxonomy (/section/<slug>) - same self-canonical
                #     pattern, additive, does not touch 3c/3d above.
                *_editorial_section_routes,
                # 4) keep the (absent) API 404 so the SPA's static-mode probe stays a fast 404
                {"src": "/api/(.*)", "status": 404},
                # 5) SPA fallback: every other in-app route renders the shell (History API + SEO)
                {"src": "/(.*)", "dest": "/index.html"},
            ],
        })

        # 5) robots + sitemap (homepage + every story)
        # Phase 40B: Disallow the private/utility routes (Phase 40A: none of these had ANY
        # indexation policy - no robots.txt rule, no noindex, nothing stopping a crawl).
        # /search is deliberately NOT here - it's handled by a client-side noindex,follow
        # (see app.jsx) instead of a crawl block, so Google can still follow the real story
        # links a search-results view contains; a private/account page has no such content
        # worth crawling into, so blocking the crawl entirely is the stronger, correct tool.
        _DISALLOW = ["/login", "/account", "/saved", "/lens", "/settings", "/my-paksh"]
        (OUT / "robots.txt").write_text(
            "User-agent: *\nAllow: /\n" + "".join("Disallow: %s\n" % p for p in _DISALLOW)
            + "\nSitemap: %s/sitemap.xml\nRSS: %s/rss.xml\n"
            % (SITE_URL, SITE_URL), encoding="utf-8")
        # Phase 35: ads.txt as a REAL file. Without one on disk, Vercel's SPA fallback (route 5
        # above) was serving index.html - real HTML, status 200 - for GET /ads.txt, which is not
        # a valid ads.txt to Google's crawler (it wants a plain-text seller list, not a webpage)
        # and can keep AdSense from authorizing/filling ads on this domain at all. The
        # "f08c47fec0942fa0" TAG-ID is Google's own public, non-secret certification authority id
        # used in every publisher's ads.txt line, not anything specific to this account.
        (OUT / "ads.txt").write_text(
            "google.com, %s, DIRECT, f08c47fec0942fa0\n" % ADSENSE_PUBLISHER_ID, encoding="utf-8")
        rows = ['  <url><loc>%s/</loc><changefreq>hourly</changefreq><priority>1.0</priority></url>' % SITE_URL]
        # section + info pages (now that routing serves them; previously they 404'd AND were
        # missing here, so they were invisible to search). Topic pages are strong SEO surfaces
        # ("Politics, every side") -> one entry per distinct topic present.
        section_paths = ["/topics", "/all-topics", "/blindspot", "/about", "/sources", "/support"]
        topic_names = sorted({e.get("topic") for e in events if e.get("topic")})
        from urllib.parse import quote
        for p in section_paths:
            rows.append('  <url><loc>%s%s</loc><changefreq>daily</changefreq><priority>0.6</priority></url>' % (SITE_URL, p))
        for name in topic_names:
            rows.append('  <url><loc>%s/topic/%s</loc><changefreq>daily</changefreq><priority>0.6</priority></url>'
                        % (SITE_URL, quote(name, safe="")))
        # Editorial section pages - same treatment as topic pages just above, one entry per
        # slug in the fixed registry (each already has its own self-canonical HTML, written
        # in the routing block above).
        for _slug, _label in _editorial_section_slugs:
            rows.append('  <url><loc>%s/section/%s</loc><changefreq>daily</changefreq><priority>0.6</priority></url>'
                        % (SITE_URL, _slug))
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

    if os.environ.get("PAKSH_ALLOW_EXPORT_COLLAPSE") != "1":
        try:
            _check_export_plausible(len(events), final_dir)
        except ExportCollapseError as e:
            print(f"  ! EXPORT ABORTED: {e}")
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