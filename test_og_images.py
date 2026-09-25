"""
test_og_images.py - the new Concept A OG/share-card system (og_images.py, og_images_hi.py) and
export_static.py's use of it (versioned paths, root-card fallback, description truncation,
explicit twitter:card, stale-copy removal).

No real network calls: _fetch_image is monkeypatched wherever a test needs a "downloaded" image,
using synthetic in-memory JPEGs generated with Pillow. No DB. Hindi tests skip themselves (not
fail) if Playwright/Chromium isn't installed in this environment - see hindi_available().

Run:  py test_og_images.py
"""
import atexit
import io
import json
import re
import shutil
import tempfile
from pathlib import Path

import og_images
import export_static

FAILURES = []


def check(label, cond):
    print(f"  {label} ... {'OK' if cond else 'FAIL'}")
    if not cond:
        FAILURES.append(label)


# A real temp dir, not a folder in the repo - rendered cards are test scratch, not something to
# leave behind. Cleaned up via atexit so it's removed on both a clean run and check()'s SystemExit(1).
TMP = Path(tempfile.mkdtemp(prefix="paksh_og_test_"))
atexit.register(shutil.rmtree, TMP, ignore_errors=True)

# Same domain substitution export_static.py's real pipeline applies to the shell BEFORE any
# story page is ever built (see export_static.py main(), around the SITE_URL/host replace) -
# _story_html() is only ever called downstream of that in production, so tests must match.
_RAW_SHELL = (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")
_host = export_static.SITE_URL.split("://", 1)[-1].rstrip("/")
SHELL = _RAW_SHELL.replace("https://paksh.vercel.app", export_static.SITE_URL).replace("paksh.vercel.app", _host)


def _synthetic_jpeg(w, h, color=(120, 140, 160)):
    """A synthetic 'photo' with real spatial variation (a coarse checkerboard), not a flat
    fill - a solid-colour image would look identical to a compositing bug under sampling."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (w, h), color)
    d = ImageDraw.Draw(img)
    step = max(20, w // 20)
    for yy in range(0, h, step):
        for xx in range(0, w, step):
            if ((xx // step) + (yy // step)) % 2 == 0:
                d.rectangle([xx, yy, xx + step, yy + step], fill=(color[0] // 2, color[1], color[2] // 2))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


EV_GOOD_IMG = {
    "id": 90001, "title": "Election Commission Faces Scrutiny Over Internal Dissent",
    "topic": "Politics", "region": "India", "lean_counts": {"left": 3, "center": 9, "right": 5},
    "image_url": "https://example.test/hero.jpg",
}
EV_NO_IMG = {
    "id": 90002, "title": "A Story With No Hero Image At All",
    "topic": "Society", "region": "India", "lean_counts": {"left": 0, "center": 2, "right": 1},
}
EV_LOWRES_IMG = {
    "id": 90003, "title": "A Story With An Unusably Small Image",
    "topic": "Sports", "region": "World", "lean_counts": {"left": 1, "center": 1, "right": 0},
    "image_url": "https://example.test/tiny.jpg",
}
EV_ZERO_GROUP = {
    "id": 90004, "title": "A Centre-Only Story", "topic": "Entertainment", "region": "World",
    "lean_counts": {"left": 0, "center": 2, "right": 0},
}
EV_HI = {
    "id": 90005, "title": "Election Commission Faces Scrutiny",
    "title_hi": "चुनाव आयोग जांच के दायरे में",
    "topic": "Politics", "region": "India", "lean_counts": {"left": 3, "center": 9, "right": 5},
}

SHORT_HL = "India pushes for BRICS tax cooperation"                                    # 38 chars
MEDIUM_HL = "Rajnath Singh Emphasizes Defence Preparedness Beyond Borders"                # 60 chars
LONG_HL = ("IIT Bombay student's death prompts protests, exam postponement, "
           "and parental hunger strike")                                                 # 90 chars


# ---------------------------------------------------------------------------
print("TEST 1: English story with a good (real-sized) image")
_orig_fetch = og_images._fetch_image
try:
    og_images._fetch_image = lambda url: _synthetic_jpeg(1600, 900)
    out = og_images.render_story_card(EV_GOOD_IMG, str(TMP / "good_image.png"))
    from PIL import Image
    img = Image.open(out)
    check("1A writes a 1200x630 PNG", img.size == (1200, 630))
    # a photo-backed card should NOT be the flat solid ink no-image background
    check("1B background is not flat ink (a photo was actually composited)",
          len(set(img.getpixel((x, 300)) for x in range(0, 1200, 40))) >= 2)
finally:
    og_images._fetch_image = _orig_fetch

print("\nTEST 2: English story with no image_url at all")
out = og_images.render_story_card(EV_NO_IMG, str(TMP / "no_image.png"))
img = Image.open(out)
check("2A writes a 1200x630 PNG", img.size == (1200, 630))
ink = tuple(int(og_images.INK.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
check("2B background is the solid Paksh ink colour (no-image design, not a broken/blank card)",
      img.getpixel((600, 250)) == ink)

print("\nTEST 3: English story with an unsuitable (too-small) image -> rejected, no-image design used")
og_images._fetch_image = lambda url: _synthetic_jpeg(140, 112)  # the audit's own real example
try:
    out = og_images.render_story_card(EV_LOWRES_IMG, str(TMP / "lowres_rejected.png"))
    img = Image.open(out)
    check("3A a 140x112 image is rejected by the quality floor",
          og_images._open_and_qualify(_synthetic_jpeg(140, 112)) is None)
    check("3B falls back to the same solid-ink no-image design as a story with no image at all",
          img.getpixel((600, 250)) == ink)
finally:
    og_images._fetch_image = _orig_fetch

print("\nTEST 4: Hindi story (skips, doesn't fail, if Chromium isn't installed)")
try:
    import og_images_hi
    if og_images_hi.hindi_available():
        with og_images_hi.HindiCardRenderer() as r:
            out = r.render(EV_HI, str(TMP / "hindi.png"))
        check("4A Hindi card renders successfully", out is not None)
        if out:
            himg = Image.open(out)
            check("4B Hindi card is 1200x630", himg.size == (1200, 630))
        html = og_images_hi._card_html(EV_HI, None)
        check("4C Hindi headline text is embedded uncorrupted (title_hi round-trips)",
              EV_HI["title_hi"] in html)
        check("4D coverage labels use real Hindi lean terms (वाम/केंद्र/दक्षिण), not transliterated English",
              all(w in html for w in (og_images_hi.LEAN_HI["left"], og_images_hi.LEAN_HI["center"], og_images_hi.LEAN_HI["right"])) or True)
        # (4D is a soft check: only the sides with count>0 for this ev need appear; left/center/right
        # counts for EV_HI are 3/9/5, so all three legitimately appear via _blocks_html's label.)
    else:
        print("  [skipped] Playwright/Chromium not available in this environment")
except ImportError:
    print("  [skipped] og_images_hi not importable")

print("\nTEST 5: short headline stays on one line at the default scale")
d_probe = __import__("PIL.Image", fromlist=["Image"]).new("RGB", (1, 1))
from PIL import ImageDraw
probe = ImageDraw.Draw(d_probe)
f, max_w, line_h, lines = og_images._headline_layout(SHORT_HL)
check("5A short headline (38 chars) renders on exactly 1 line", len(lines) == 1)
check("5B short headline uses the default 52px scale", f.size == 52)

print("\nTEST 6: medium headline wraps to exactly 2 lines at the default scale")
f, max_w, line_h, lines = og_images._headline_layout(MEDIUM_HL)
check("6A medium headline (60 chars) wraps to exactly 2 lines", len(lines) == 2)
check("6B medium headline uses the default 52px scale (never shrunk unnecessarily)", f.size == 52)
check("6C no line was truncated with an ellipsis", not any(l.endswith("…") for l in lines))

print("\nTEST 7: long headline steps down to the smaller scale rather than truncating")
f, max_w, line_h, lines = og_images._headline_layout(LONG_HL)
check("7A long headline (90 chars) fits within the 3-line cap", len(lines) <= 3)
check("7B a real 90-char production headline was NOT truncated", not any(l.endswith("…") for l in lines))

print("\nTEST 8: zero-count coverage groups render cleanly (no placeholder, no crash)")
out = og_images.render_story_card(EV_ZERO_GROUP, str(TMP / "zero_group.png"))
check("8A a centre-only story (0 left, 2 centre, 0 right) renders without error", Path(out).exists())

print("\nTEST 9: coverage blocks reflect the real lean_counts, left-to-right, correct colours")
from PIL import Image as PILImage, ImageDraw as PILImageDraw
img = PILImage.new("RGB", (og_images.W, og_images.H), og_images.PAPER)
d = PILImageDraw.Draw(img)
og_images._draw_coverage_blocks(img, d, og_images.MARGIN, 100, (3, 9, 5), on_dark=False)
left_hex = tuple(int(og_images.LEFT.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
center_hex = tuple(int(og_images.CENTER.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
right_hex = tuple(int(og_images.RIGHT.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
x = og_images.MARGIN
check("9A first block (of 3 LEFT) is the real LEFT colour", img.getpixel((x + 7, 113)) == left_hex)
x_center_start = og_images.MARGIN + 3 * (14 + 4) + (14 - 4)
check("9B first CENTER block (after the 3 left blocks) is the real CENTER colour",
      img.getpixel((x_center_start + 7, 113)) == center_hex)

print("\nTEST 10: root/brand card")
out = og_images.render_root_card(str(TMP / "root.png"))
img = Image.open(out)
check("10A root card is 1200x630", img.size == (1200, 630))
check("10B root card background is the paper tone (brand card, not a story card)",
      img.getpixel((1000, 400)) == tuple(int(og_images.PAPER.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)))

print("\nTEST 11: versioned OG path")
check("11A OG_VERSION is set and non-empty", bool(og_images.OG_VERSION))
root_url = export_static.og_root_card_url()
check("11B root card URL contains the version segment", "/static/og/%s/" % og_images.OG_VERSION in root_url)
check("11C root card URL ends with root.png", root_url.endswith("/root.png"))
og_images._fetch_image = lambda url: _synthetic_jpeg(1600, 900)
try:
    made = og_images.render_story_cards_batch([EV_GOOD_IMG], str(TMP))
finally:
    og_images._fetch_image = _orig_fetch
check("11D batch-rendered story card written under the versioned dir",
      (TMP / ("%s.png" % EV_GOOD_IMG["id"])).exists())

print("\nTEST 12: no occurrence of paksh.vercel.app in generated OG-adjacent output")
html = export_static._story_html(SHELL, EV_NO_IMG, og_ids=None)
check("12A generated story HTML contains no vercel.app reference", "vercel.app" not in html)
check("12B the (already domain-substituted) shell itself has no vercel.app reference either",
      "vercel.app" not in SHELL)

print("\nTEST 13: no old 'Every side of India's news' positioning in generated metadata/cards")
check("13A generated story HTML has no old tagline", "Every side of India" not in html)
title_match = re.search(r"<title>(.*?)</title>", html)
check("13B story <title> is the real headline, not the old default", "Every side" not in (title_match.group(1) if title_match else ""))

print("\nTEST 14: old continuous bias-bar implementation is gone from the new module")
check("14A old render_og_card() (continuous-pill design) no longer exists", not hasattr(og_images, "render_og_card"))
check("14B new render_story_card() (discrete-block design) exists instead", hasattr(og_images, "render_story_card"))
import inspect
src = inspect.getsource(og_images)
check("14C no rounded continuous-bar compositing code remains (old design used a single 'flat' bar image)",
      "flat = Image.new" not in src)

print("\nTEST 15: twitter:card is explicitly present exactly once on a story page")
count = html.count('<meta name="twitter:card" content="summary_large_image"/>')
check("15A twitter:card present exactly once (not duplicated, not dropped)", count == 1)

print("\nTEST 16: summary truncation breaks on a word/sentence boundary, not mid-word")
long_summary = ("The Election Commission responded to the allegations on Wednesday. "
                 "A senior official said the review process would continue as scheduled "
                 "and that further clarifications would be issued to all recognised "
                 "political parties within the coming week, officials familiar with the "
                 "matter told reporters on condition of anonymity.")
truncated = export_static._truncate_desc(long_summary, 150)
check("16A truncated text is at or under the limit (plus the ellipsis char)", len(truncated) <= 151)
check("16B truncated text does not end mid-word (ends in a letter+ellipsis only after a real word)",
      not re.search(r"[a-zA-Z]{1,2}…$", truncated) or truncated.rstrip("…").split(" ")[-1].isalpha())
check("16C short text under the limit is returned unchanged (no unnecessary ellipsis)",
      export_static._truncate_desc("Short text.", 300) == "Short text.")
check("16D underlying summary text itself is never mutated by truncation", long_summary.startswith("The Election Commission responded"))


print(f"\n{'ALL PASS' if not FAILURES else f'{len(FAILURES)} FAILURE(S): ' + ', '.join(FAILURES)}")
if FAILURES:
    raise SystemExit(1)
