"""og_images.py - Paksh share cards ("OG images"): per-story cards (Concept A: full-bleed
hero image, top+bottom vignette, brand wordmark, discrete coverage blocks) and the root/brand
card. Static export only: this runs at BUILD time (from export_static.py) and writes plain
.png files - no server, no runtime, no external request from the browser.

Design is versioned (OG_VERSION below): every card lives under static/og/<OG_VERSION>/, so a
visual redesign (like this one) gets a brand-new URL and can't be served stale by a social
platform's own OG-image cache. Bump OG_VERSION, not the individual filenames, when the design
next changes.

Three renderers, one shared visual language:
  - render_story_card()   - Concept A, Pillow-based, English. Composites the story's real hero
    image (fetched here, quality-gated - see MIN_IMG_W/H) when one exists and passes the
    quality floor; otherwise draws the no-image variant (solid ink background + a faint brand
    motif) - same wordmark/kicker/headline/coverage-block positions either way, so a reader
    never sees a "degraded fallback," just a card without a photo.
  - render_root_card()    - the brand-only card for the root URL (also reused as the global
    story fallback for anything outside the OG_CARD_N window - see export_static.py).
  - render_story_card_hi()- Hindi, in og_images_hi.py: Pillow has no complex-text shaper for
    Devanagari (conjuncts/matras render wrong), so Hindi cards go through a real browser
    instead. Kept in a separate module and only imported when actually used, so the Chromium
    dependency never touches the default (English-only) export path. See that module's own
    docstring for the isolation contract.

Graceful by design: any per-card failure (bad/unreachable image, missing dependency) falls
back to the no-image design rather than raising - export_static.py's build must never fail
because one photo timed out.
"""

import io
import os
import re
import unicodedata
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(ROOT, "static", "fonts")

# Bump this - and only this - when the card DESIGN changes. export_static.py builds every
# public path (story cards, root card, RSS enclosures) from this constant, so a new version
# automatically gets a brand-new URL and can never be served stale from a platform's OG cache.
OG_VERSION = "v2"

# Canvas + brand tokens (the same hexes the live site uses - static/app.jsx / static/styles.css).
W, H = 1200, 630
MARGIN = 56
PAPER = "#F4F1EA"
INK = "#15140F"
FAINT = "#8A8371"
LABEL = "#6B675C"
LINE = "#D8D3C6"
OFFWHITE = "#FBFAF6"
KICKER_ON_IMG = "#C9C2B3"
LABEL_ON_IMG = "#B9B3A3"
# Bias pill colours - the same PILL_COLOR values as the client's BiasPill (static/app.jsx).
LEFT = "#587A91"
CENTER = "#6F6B61"
RIGHT = "#A46149"

# A hero image below this floor would need more than ~2x upscaling to fill a 1200x630 card -
# visibly blurry. Deliberately simple (one dimension check, no aspect-ratio/content heuristics):
# the audit's own worst real example (a 140x112 production image) fails this by a wide margin,
# which is the bar this is meant to clear, not a computer-vision quality system.
MIN_IMG_W, MIN_IMG_H = 600, 315
IMAGE_FETCH_TIMEOUT_S = 6
IMAGE_MAX_BYTES = 12 * 1024 * 1024  # 12MB safety cap - a hero photo is never legitimately bigger

# Brand woff2 files (latin subsets) -> the roles the card needs.
_FONT_FILES = {
    "serif_bold": "vEFI2_tTDB4M7-auWDN0ahZJW1gb8tc.woff2",              # Source Serif 4 700
    "sans_bold":  "zYXzKVElMYYaJe8bpLHnCwDKr932-G7dytD-Dmu1syxeKYY.woff2",       # IBM Plex Sans 600/700
    "mono":       "-F6qfjptAgt5VM-kVkqdyU8n3vAOwlBFgg.woff2",           # IBM Plex Mono 600
}

# The पक्ष glyph cluster contains a real conjunct (क्ष = क + ् + ष) that needs complex text
# shaping to render correctly. Pillow's default text layout has no shaper for this (confirmed:
# PIL.features.check("raqm") is False in this environment, and drawing पक्ष as plain glyphs
# produced missing-glyph boxes, not the correct ligature) - so the wordmark's Devanagari part is
# NOT drawn as text here at all. It's a pre-rendered, correctly-shaped bitmap (generated once,
# via a real browser - see scripts/gen_wordmark_asset.py - the same reason og_images_hi.py
# exists for full Hindi headlines), recoloured per-card through its own alpha channel exactly
# like the coverage blocks below reuse a mask. This keeps the routine English export path 100%
# Chromium-free: the bitmap is a committed static asset, regenerated only if the glyph itself
# ever needs to change.
WORDMARK_DEVA_ASSET = os.path.join(ROOT, "static", "og-assets", "wordmark-deva.png")
_wordmark_glyph_cache = {}


def _wordmark_glyph_mask(height_px):
    """The पक्ष bitmap's alpha channel, resized (LANCZOS) to height_px tall, aspect preserved -
    ready to use as a paste mask so the glyph can be recoloured (white on a photo, ink on the
    paper-toned root card) without ever redrawing the shape itself."""
    if height_px not in _wordmark_glyph_cache:
        from PIL import Image
        src = Image.open(WORDMARK_DEVA_ASSET)
        w = int(round(src.width * (height_px / src.height)))
        resized = src.resize((w, height_px), Image.LANCZOS)
        _wordmark_glyph_cache[height_px] = resized.split()[-1]  # alpha channel only
    return _wordmark_glyph_cache[height_px]

_ttf_bytes = {}   # role -> decompressed TTF bytes (woff2 -> ttf, once)
_font_cache = {}  # (role, size) -> ImageFont


def _ttf(role):
    if role not in _ttf_bytes:
        from fontTools.ttLib import TTFont  # needs brotli for woff2
        src = os.path.join(FONTS, _FONT_FILES[role])
        f = TTFont(src)
        f.flavor = None
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
    s = unicodedata.normalize("NFC", str(s or "")).strip()
    swaps = {"‘": "'", "’": "'", "“": '"', "”": '"',
             "–": "-", "…": "..."}
    s = "".join(swaps.get(ch, ch) for ch in s)
    return " ".join(s.split())


def _wrap(draw, text, font, max_w, max_lines):
    """Greedy word-wrap to max_w; clamp to max_lines with an ellipsis on the last line only
    if there was genuinely more text left over (never truncates a headline that already fit)."""
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
    used_words = sum(len(l.split(" ")) for l in lines)
    if len(lines) == max_lines and used_words < len(words):
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > max_w:
            last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
        lines[-1] = (last + "…") if last else last
    return lines


def _headline_layout(headline):
    """Fixed type scale with exactly two rungs (per the approved spec - never shrink below the
    second): 52px/~980px for the normal (<=2-line) case, 42px/~1040px if that would overflow a
    3-line cap. Returns (font_role_size, max_w, line_height, lines)."""
    from PIL import Image, ImageDraw
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    f52 = _font("serif_bold", 52)
    lines = _wrap(probe, headline, f52, 980, 3)
    if len(lines) <= 2 or not any(l.endswith("…") for l in lines):
        # Re-wrap at the real 2-line budget for the common case (3-line probe above was only to
        # decide WHICH scale to commit to).
        lines2 = _wrap(probe, headline, f52, 980, 2)
        if " ".join(lines2).rstrip("…") == headline or not lines2[-1].endswith("…"):
            return f52, 980, 64, lines2
    f42 = _font("serif_bold", 42)
    lines42 = _wrap(probe, headline, f42, 1040, 3)
    return f42, 1040, 52, lines42


def _fetch_image(url):
    """Downloads url with a short timeout and a hard byte cap. Returns raw bytes or None on any
    failure - network errors, timeouts, oversized responses, and non-2xx statuses are all
    treated as "no usable image" rather than raised, per this module's fail-open contract."""
    if not url or not re.match(r"^https?://", url):
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (PakshOGBot)"})
        with urllib.request.urlopen(req, timeout=IMAGE_FETCH_TIMEOUT_S) as resp:
            data = resp.read(IMAGE_MAX_BYTES + 1)
            if len(data) > IMAGE_MAX_BYTES:
                return None
            return data
    except Exception:
        return None


def _open_and_qualify(image_bytes):
    """Bytes -> a quality-checked, EXIF-corrected RGB PIL Image, or None if it fails the
    minimum-dimension floor or simply won't decode. No aspect-ratio/content heuristics -
    deliberately just the one deterministic check (see MIN_IMG_W/H above)."""
    if not image_bytes:
        return None
    try:
        from PIL import Image, ImageOps
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img)  # real photos are often EXIF-rotated; Pillow won't auto-apply it
        img = img.convert("RGB")
    except Exception:
        return None
    if img.width < MIN_IMG_W or img.height < MIN_IMG_H:
        return None
    return img


def _cover_crop(img, w, h, anchor_y=0.30):
    """Resize+crop img to exactly (w, h), CSS `background-size:cover` semantics, anchored
    toward the upper-middle (anchor_y, 0=top 1=bottom) rather than dead-center - news photos
    usually place faces/subjects in the upper half; a naive center-crop clips heads."""
    src_ratio = img.width / img.height
    dst_ratio = w / h
    if src_ratio > dst_ratio:
        new_h = h
        new_w = int(round(h * src_ratio))
    else:
        new_w = w
        new_h = int(round(w / src_ratio))
    img = img.resize((new_w, new_h))
    x0 = (new_w - w) // 2
    y0 = int(round((new_h - h) * anchor_y))
    y0 = max(0, min(y0, new_h - h))
    return img.crop((x0, y0, x0 + w, y0 + h))


def _apply_vignette(img):
    """Composites the approved combined top+bottom scrim onto img (must already be W x H).
    Confirmed necessary against real production photos during prototyping: a bottom-only scrim
    left the wordmark illegible against bright/light top-of-frame content (a pale signboard, a
    light studio backdrop) in 2 of 4 real test images. Stops values match the tested prototype
    exactly: 0.55 at the very top fading to 0.07 by 32%, then rising to 0.96 at the bottom."""
    from PIL import Image
    stops = [(0.00, 0.55), (0.15, 0.16), (0.32, 0.07), (0.70, 0.85), (1.00, 0.96)]
    grad = Image.new("L", (1, H))
    gi = 0
    for y in range(H):
        t = y / (H - 1)
        while gi < len(stops) - 2 and t > stops[gi + 1][0]:
            gi += 1
        (t0, a0), (t1, a1) = stops[gi], stops[gi + 1]
        frac = 0 if t1 == t0 else (t - t0) / (t1 - t0)
        a = a0 + (a1 - a0) * frac
        grad.putpixel((0, y), int(round(a * 255)))
    grad = grad.resize((W, H))
    overlay = Image.new("RGB", (W, H), (10, 10, 8))
    img.paste(overlay, (0, 0), grad)
    return img


def _draw_wordmark(img, d, x, y, on_dark):
    """पक्ष + PAKSH, exactly the real footer lockup (static/app.jsx:1034 - text-xl/text-[15px]/
    gap-1.5/tracking-[0.24em]), scaled 1.6x for this canvas: deva glyph 32px tall, lat 24px,
    ~10px gap. Not a new logo - the same ratio the live site already ships. The पक्ष glyph is
    pasted from the pre-shaped bitmap (see WORDMARK_DEVA_ASSET above), not drawn as text.
    Returns the wordmark's total width."""
    from PIL import Image
    color = OFFWHITE if on_dark else INK
    mask = _wordmark_glyph_mask(32)
    solid = Image.new("RGB", mask.size, color)
    img.paste(solid, (x, y), mask)
    lat_f = _font("sans_bold", 24)
    lat_x = x + mask.width + 10
    # baseline-align: nudge the (shorter-looking) latin word down slightly to sit on the same
    # visual baseline as the taller Devanagari glyph.
    d.text((lat_x, y + 7), "PAKSH", font=lat_f, fill=color)
    return (lat_x + d.textlength("PAKSH", font=lat_f)) - x


def _draw_coverage_blocks(img, d, x, y, counts, on_dark):
    """Discrete "one publisher = one vote" blocks, grouped by lean with a visible gap between
    groups (never a continuous bar) - 14x26px per block, 3px radius, 4px gap within a group,
    14px between groups. A zero-count lean simply contributes no blocks (confirmed clean in
    testing, e.g. a centre-only story: no placeholder, no "0", the group is just absent)."""
    from PIL import Image, ImageDraw
    L, C, R = counts
    cx = x
    for count, col in ((L, LEFT), (C, CENTER), (R, RIGHT)):
        for i in range(count):
            block = Image.new("RGB", (14, 26), col)
            mask = Image.new("L", (14, 26), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, 14, 26], radius=3, fill=255)
            img.paste(block, (int(cx), y), mask)
            cx += 14 + 4
        if count:
            cx += 14 - 4  # undo the last block's trailing within-group 4px gap, add the real 14px between-group gap
    total = L + C + R
    label_color = LABEL_ON_IMG if on_dark else LABEL
    if total:
        d.text((cx + 4, y + 5), "%d OUTLET%s" % (total, "" if total == 1 else "S"),
               font=_font("mono", 14), fill=label_color)


def _no_image_background(motif_seed=0):
    """The approved no-image treatment: solid Paksh ink, plus a faint (14% opacity) watermark
    of the same block-grid motif used on the root card - same visual family, not a different
    template. Deterministic: motif_seed picks a fixed pattern, no randomness (this module's
    determinism guarantee - unchanged story -> byte-identical card - would break otherwise)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (W, H), INK)
    patterns = [
        [LEFT, CENTER, CENTER, RIGHT],
        [CENTER, LEFT, RIGHT, CENTER],
        [RIGHT, CENTER, LEFT],
        [CENTER, RIGHT],
    ]
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    top, right = 0, W - MARGIN
    for row in patterns:
        cx = right - len(row) * (22 + 8)
        for col in row:
            r, g, b = tuple(int(col.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
            od.rounded_rectangle([cx, top, cx + 22, top + 46], radius=5, fill=(r, g, b, 36))
            cx += 22 + 8
        top += 46 + 10
    img.paste(Image.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, 0)), overlay).convert("RGB"), (0, 0),
              overlay.split()[-1])
    return img


def _kicker_text(topic, region):
    return "%s   ·   %s" % ((topic or "News").upper(), (region or "India").upper())


def _fetch_and_qualify(image_url):
    """Fetch + quality-check in one call - the unit of work that's safe to run concurrently
    across many stories (pure network I/O + a cheap in-memory decode), used by both the
    single-story path below and render_story_cards_batch's thread pool."""
    return _open_and_qualify(_fetch_image(image_url))


_UNSET = object()  # sentinel: distinguishes "caller didn't pass photo, fetch it yourself" (the
                    # default) from "caller passed photo=None, meaning fetch already happened
                    # and failed/was skipped - use the no-image design, don't fetch again."


def render_story_card(ev, out_path, photo=_UNSET):
    """Renders one story's Concept A share card. ev needs: id, title, topic, region,
    lean_counts (or coverage[side].count), and optionally image_url. Always writes a valid PNG
    to out_path - falls back to the no-image design on any image problem, never raises for a
    bad photo. Returns out_path.

    `photo` lets a caller pass an already-fetched, already-quality-checked PIL Image (or
    None if that fetch failed/was skipped) - see render_story_cards_batch, which fetches every
    story's image CONCURRENTLY first (fetching is I/O-bound and dominates single-story timing
    at ~1-1.6s each; sequential fetching of a real 1500-story batch would add many extra minutes
    to the export). Leave `photo` unset to have this function fetch synchronously itself (fine
    for a single story / tests, not for a real batch)."""
    from PIL import Image, ImageDraw

    counts = ev.get("lean_counts") or {}
    if not counts:
        cov = ev.get("coverage") or {}
        counts = {k: (cov.get(k, {}) or {}).get("count", 0) for k in ("left", "center", "right")}
    L, C, R = (int(counts.get("left", 0) or 0), int(counts.get("center", 0) or 0),
               int(counts.get("right", 0) or 0))

    if photo is _UNSET:
        photo = _fetch_and_qualify(ev.get("image_url")) if ev.get("image_url") else None

    if photo is not None:
        img = _cover_crop(photo, W, H, anchor_y=0.30)
        img = _apply_vignette(img)
        on_dark = True
    else:
        img = _no_image_background()
        on_dark = True  # ink background - same light-text treatment as the vignetted photo case

    d = ImageDraw.Draw(img)
    _draw_wordmark(img, d, MARGIN, 44, on_dark)
    domain_f = _font("sans_bold", 17)
    d.text((W - MARGIN - d.textlength("paksh.news", font=domain_f), 44), "paksh.news",
           font=domain_f, fill=(OFFWHITE if on_dark else INK))

    headline = _clean(ev.get("title") or "Paksh story")
    hf, max_w, line_h, lines = _headline_layout(headline)

    kicker = _kicker_text(ev.get("topic"), ev.get("region"))
    kicker_f = _font("mono", 15)
    block_h = 24 + len(lines) * line_h + 24 + 26 + 12  # kicker + headline block + gap + blocks row + breathing room
    bottom_y = H - 44 - block_h + 24
    d.text((MARGIN, bottom_y), kicker, font=kicker_f, fill=(KICKER_ON_IMG if on_dark else LABEL))

    y = bottom_y + 24
    for ln in lines:
        d.text((MARGIN, y), ln, font=hf, fill=(OFFWHITE if on_dark else INK))
        y += line_h

    _draw_coverage_blocks(img, d, MARGIN, y + 12, (L, C, R), on_dark)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return out_path


def render_root_card(out_path, tagline="News, with context."):
    """The root/brand card: wordmark, one short line, paksh.news, the abstract block motif.
    No story data - this is also reused as the global fallback og:image for any story outside
    the recent-card window (see export_static.py), so it must never reference a specific
    event."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)

    wm_y = H // 2 - 130
    _draw_wordmark_large(img, d, MARGIN + 20, wm_y)

    tag_f = _font("serif_bold", 36)
    d.text((MARGIN + 20, wm_y + 90), _clean(tagline), font=tag_f, fill=INK)

    _draw_motif(img, W - MARGIN - 4 * 22 - 3 * 8, 40)

    domain_f = _font("sans_bold", 19)
    d.text((MARGIN + 20, H - 90), "paksh.news", font=domain_f, fill=INK)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return out_path


OG_FETCH_WORKERS = 8  # bounded thread pool for the network-fetch step only - compositing
                       # itself stays single-threaded (it's fast, ~0.1-0.3s/card; fetching a
                       # remote photo is what dominates single-story timing at ~1-1.6s each).


def render_story_cards_batch(rows, out_dir, workers=OG_FETCH_WORKERS):
    """Renders Concept A cards for every row, fetching all their hero images CONCURRENTLY
    first (a bounded ThreadPoolExecutor - this is I/O-bound network fetching, not CPU work, so
    a plain thread pool is enough; no new dependency, stdlib concurrent.futures only) and then
    compositing each card sequentially. This is the path export_static.py actually calls for
    the real (up to OG_CARD_N) story batch - render_story_card() alone is for single-story use
    (tests, the standalone _sample() preview) where the extra machinery isn't worth it.

    Rows with no image_url skip the fetch step entirely (no network call, straight to the
    no-image design). Returns the set of ids that got a card written (mirrors the old
    _build_og_cards() contract in export_static.py: every row gets SOME card, image-based or
    not, so this set is really just "which ids were processed," not "which ids got a photo")."""
    from concurrent.futures import ThreadPoolExecutor

    urls = {r["id"]: r.get("image_url") for r in rows if r.get("image_url")}
    photos = {}
    if urls:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(_fetch_and_qualify, url): eid for eid, url in urls.items()}
            for fut in futures:
                eid = futures[fut]
                try:
                    photos[eid] = fut.result()
                except Exception:
                    photos[eid] = None

    made = set()
    for r in rows:
        try:
            out_path = os.path.join(out_dir, "%s.png" % r["id"])
            render_story_card(r, out_path, photo=photos.get(r["id"]))
            made.add(r["id"])
        except Exception:
            pass  # never let one bad row fail the whole batch
    return made


def _draw_wordmark_large(img, d, x, y):
    """Same wordmark lockup as _draw_wordmark, scaled up further for the root card's larger,
    centred brand statement (deva glyph 92px tall / lat 32px, same ratio family). Same
    pre-shaped-bitmap approach as _draw_wordmark - see WORDMARK_DEVA_ASSET above."""
    from PIL import Image
    mask = _wordmark_glyph_mask(92)
    solid = Image.new("RGB", mask.size, INK)
    img.paste(solid, (x, y), mask)
    lat_f = _font("sans_bold", 32)
    lat_x = x + mask.width + 16
    d.text((lat_x, y + 34), "PAKSH", font=lat_f, fill=INK)


def _draw_motif(img, x, y):
    """The decorative, story-agnostic block-grid used on the root/no-image cards - NOT derived
    from any real event's counts (this is the one place these blocks are purely ornamental)."""
    from PIL import Image, ImageDraw
    pattern = [
        [LEFT, CENTER, CENTER, RIGHT],
        [CENTER, LEFT, RIGHT, CENTER],
        [RIGHT, CENTER, LEFT],
    ]
    d = ImageDraw.Draw(img)
    top = y
    for row in pattern:
        cx = x
        for col in row:
            block = Image.new("RGB", (22, 46), col)
            mask = Image.new("L", (22, 46), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, 22, 46], radius=5, fill=255)
            img.paste(block, (int(cx), top), mask)
            cx += 22 + 8
        top += 46 + 10


def _sample():
    """Standalone preview: render a few live events + the root card into ./_og_preview."""
    import json
    ev_path = os.path.join(ROOT, "_site", "data", "events.json")
    events = json.load(open(ev_path, encoding="utf-8")).get("events", [])
    out_dir = os.path.join(ROOT, "_og_preview")
    os.makedirs(out_dir, exist_ok=True)
    made = []
    for e in events[:4]:
        p = os.path.join(out_dir, "%s.png" % e["id"])
        render_story_card(e, p)
        made.append(p)
        print("  wrote", p, "(%d bytes)" % os.path.getsize(p))
    rp = os.path.join(out_dir, "root.png")
    render_root_card(rp)
    print("  wrote", rp, "(%d bytes)" % os.path.getsize(rp))
    return made


if __name__ == "__main__":
    _sample()
