"""og_images.py - per-story social share cards ("OG images") with the bias bar.

Why this exists
---------------
When a Paksh story link is shared on WhatsApp / X / Facebook / LinkedIn, the
preview shown is the page's og:image. Until now every story shared the SAME
global og.png. This module draws a per-story 1200x630 PNG card carrying the
story's headline and its SIGNATURE bias bar (real distinct-outlet L/C/R counts),
so a shared link previews the actual coverage split - the whole product, in one
image, before anyone even clicks.

Design invariants kept
-----------------------
- The bias bar segment sizes come STRAIGHT from the real counts (never a
  hardcoded ratio), same as the site. Solid-fill rounded pill, matching the
  client's BiasPill exactly (static/app.jsx, PILL_COLOR) - no hatch, no rule
  texture, no percentage, no "n =".
- Static export only: this runs at BUILD time (from export_static.py) and writes
  plain .png files. No server, no runtime, no external request.
- Cards are ENGLISH. The crawlable /story/<id> page is English-canonical (its
  <title>/OG/JSON-LD are English), so an English card is consistent with the page
  a link-preview bot actually reads. (Hindi cards would need a complex-text shaper
  Pillow lacks here; that's a separate future upgrade.)
- Fonts are the site's own brand woff2 files, converted to TTF IN MEMORY - nothing
  new is written into static/ or served to browsers.
- Output is deterministic (no timestamps): an unchanged story re-renders to
  identical bytes, so git sees no diff and content cycles don't churn.

Graceful by design: if Pillow/fontTools aren't importable, render_og_card raises
ImportError once; export_static.py catches it and simply keeps the global og.png
fallback rather than failing the build.
"""

import io
import os
import unicodedata

ROOT = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(ROOT, "static", "fonts")

# Canvas + brand tokens (light "paper" theme - the same hexes the site uses).
W, H = 1200, 630
MARGIN = 64
PAPER = "#F4F1EA"
INK = "#15140F"
FAINT = "#8A8371"
LABEL = "#6B675C"
LINE = "#D8D3C6"
TRACK = "#EAE6DB"
GAP = "#F4F1EA"
# Bias pill colours - the same PILL_COLOR values as the client's BiasPill
# (static/app.jsx) and _story_html()'s crawlable pill.
LEFT = "#587A91"
CENTER = "#6F6B61"
RIGHT = "#A46149"

# Brand woff2 files (latin subsets) -> the four roles the card needs.
_FONT_FILES = {
    "serif_bold": "vEFI2_tTDB4M7-auWDN0ahZJW1gb8tc.woff2",              # Source Serif 4 700
    "serif_reg":  "vEFH2_tTDB4M7-auWDN0ahZJW1ge6NmXq2ZbF8zBfb98SUr6aX0.woff2",  # Source Serif 4 400
    "sans_bold":  "zYXzKVElMYYaJe8bpLHnCwDKr932-G7dytD-Dmu1syxeKYY.woff2",       # IBM Plex Sans 600/700
    "mono":       "-F6qfjptAgt5VM-kVkqdyU8n3vAOwlBFgg.woff2",           # IBM Plex Mono 600
}

_ttf_bytes = {}   # role -> decompressed TTF bytes (woff2 -> ttf, once)
_font_cache = {}  # (role, size) -> ImageFont


def _ttf(role):
    """Return TTF bytes for a role, converting the brand woff2 in memory (cached)."""
    if role not in _ttf_bytes:
        from fontTools.ttLib import TTFont  # needs brotli for woff2
        src = os.path.join(FONTS, _FONT_FILES[role])
        f = TTFont(src)
        f.flavor = None                     # woff2 -> plain sfnt (ttf)
        buf = io.BytesIO()
        f.save(buf)
        _ttf_bytes[role] = buf.getvalue()
    return _ttf_bytes[role]


def _font(role, size):
    key = (role, size)
    if key not in _font_cache:
        from PIL import ImageFont
        _font_cache[key] = ImageFont.truetype(io.BytesIO(_ttf(role)), size)
    return _font_cache[key]


def _clean(s):
    """Normalise a headline to what the latin font subset can draw: collapse
    whitespace and swap a few glyphs that may be outside the subset."""
    s = unicodedata.normalize("NFC", str(s or "")).strip()
    swaps = {"‘": "'", "’": "'", "“": '"', "”": '"',
             "–": "-", "—": "—", "…": "...", " ": " "}
    s = "".join(swaps.get(ch, ch) for ch in s)
    return " ".join(s.split())


def _wrap(draw, text, font, max_w, max_lines):
    """Greedy word-wrap to max_w; clamp to max_lines with an ellipsis."""
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
        if len(lines) == max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    # If we ran out of room, ellipsise the last line to fit.
    if len(lines) == max_lines:
        used = sum(len(l.split(" ")) for l in lines)
        if used < len(words):
            last = lines[-1]
            while last and draw.textlength(last + "…", font=font) > max_w:
                last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
            lines[-1] = (last + "…") if last else last
    return lines


def _spaced(s, n=1):
    """Fake letter-spacing for the mono kicker (Pillow has no tracking)."""
    return (" " * n).join(list(s))


def render_og_card(ev, out_path):
    """Render one story's share card to out_path (PNG). ev is an event dict with
    at least: title, topic, region, and per-lean counts via lean_counts or
    coverage[side].count."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)

    x0, x1 = MARGIN, W - MARGIN
    content_w = x1 - x0

    # --- header: wordmark + kicker + rule ---
    d.text((x0, 52), "Paksh", font=_font("sans_bold", 34), fill=INK)
    kick = _spaced("EVERY SIDE OF INDIA'S NEWS")
    kf = _font("mono", 15)
    d.text((x1 - d.textlength(kick, font=kf), 64), kick, font=kf, fill=FAINT)
    d.line([(x0, 110), (x1, 110)], fill=LINE, width=1)

    # --- topic . region kicker ---
    topic = (ev.get("topic") or "News").upper()
    region = (ev.get("region") or "India").upper()
    d.text((x0, 150), _spaced(f"{topic}  ·  {region}"),
           font=_font("mono", 17), fill=FAINT)

    # --- headline (Source Serif bold, wrapped) ---
    headline = _clean(ev.get("title") or "Paksh story")
    hf = _font("serif_bold", 54)
    lines = _wrap(d, headline, hf, content_w, 4)
    y = 196
    for ln in lines:
        d.text((x0, y), ln, font=hf, fill=INK)
        y += 64

    # --- bias bar block, anchored to the bottom ---
    counts = ev.get("lean_counts") or {}
    if not counts:
        cov = ev.get("coverage") or {}
        counts = {k: (cov.get(k, {}) or {}).get("count", 0)
                  for k in ("left", "center", "right")}
    L = int(counts.get("left", 0) or 0)
    C = int(counts.get("center", 0) or 0)
    R = int(counts.get("right", 0) or 0)

    bar_h = 26
    bar_y = 480
    # mono count label above the bar - no "n =", the three counts already say it
    lab = f"LEFT {L}   ·   CENTRE {C}   ·   RIGHT {R}"
    d.text((x0, bar_y - 34), lab, font=_font("mono", 19), fill=LABEL)

    # solid-fill rounded pill - draw the segmented bar flat, then clip it through a
    # rounded-rectangle mask, the same effect as the client's `overflow:hidden` +
    # `border-radius:999` on BiasPill. Track colour shows through wherever a side
    # is absent (0 count), so absence still reads as an even gap, not a void.
    present = [(k, v, col) for k, v, col in
               (("left", L, LEFT), ("center", C, CENTER), ("right", R, RIGHT)) if v > 0]
    total = sum(v for _, v, _ in present) or 1
    bar_w = x1 - x0
    flat = Image.new("RGB", (bar_w, bar_h), TRACK)
    fd = ImageDraw.Draw(flat)
    cx = 0
    for i, (k, v, col) in enumerate(present):
        # last segment fills to the edge so rounding never leaves a sliver
        seg_w = bar_w - cx if i == len(present) - 1 else max(1, round(bar_w * v / total))
        fd.rectangle([cx, 0, cx + seg_w, bar_h], fill=col)
        cx += seg_w
    mask = Image.new("L", (bar_w, bar_h), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, bar_w, bar_h], radius=bar_h // 2, fill=255)
    img.paste(flat, (x0, bar_y), mask)

    # caption under the bar
    cap = "Distinct outlets on each side that covered this story · one publisher = one vote"
    d.text((x0, bar_y + bar_h + 16), cap, font=_font("mono", 15), fill=FAINT)

    # --- footer wordmark ---
    d.text((x0, H - 52), "paksh.news", font=_font("sans_bold", 22), fill=INK)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return out_path


def _sample():
    """Standalone preview: render the first few live events from _site to /scratch."""
    import json
    ev_path = os.path.join(ROOT, "_site", "data", "events.json")
    events = json.load(open(ev_path, encoding="utf-8")).get("events", [])
    out_dir = os.path.join(ROOT, "_og_preview")
    os.makedirs(out_dir, exist_ok=True)
    made = []
    for e in events[:4]:
        p = os.path.join(out_dir, f"{e['id']}.png")
        render_og_card(e, p)
        made.append(p)
        print("  wrote", p, "(%d bytes)" % os.path.getsize(p))
    return made


if __name__ == "__main__":
    _sample()
