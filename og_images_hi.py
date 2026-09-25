"""og_images_hi.py - Hindi share cards, rendered through a real browser (Chromium via
Playwright) instead of Pillow.

WHY THIS IS A SEPARATE MODULE
------------------------------
og_images.py's Pillow-based renderer draws English glyphs directly and cannot correctly shape
Devanagari (conjuncts and matras need a real text-shaping engine - Pillow has none built in).
Rendering the same design through a browser produces correct shaping for free, because the
browser's own layout/text engine does the work - confirmed during prototyping against real
Hindi headlines.

Playwright/Chromium is a real, fairly heavy dependency (a ~300MB browser download). Isolating
it here means:
  - Importing og_images.py or running export_static.py's default (English) path NEVER imports
    this module and never touches Playwright.
  - export_static.py only imports this module when Hindi card generation is explicitly
    requested (see export_static.py's PAKSH_OG_HINDI flag) - it stays opt-in, not part of the
    routine production export.
  - One browser is launched per BATCH (HindiCardRenderer), reused across every card in that
    batch, never relaunched per image.
  - Any failure - Playwright missing, the Chromium binary not installed, a single page erroring
    - is caught here and treated as "this card is skipped," never raised into the caller. This
    module NEVER falls back to drawing Hindi text through the Pillow renderer instead (that
    would silently ship incorrectly-shaped Devanagari, which is exactly what this module exists
    to avoid).

CURRENT STATUS: tested, working, produces byte-for-byte-correct Devanagari shaping (see
test_og_images.py). NOT currently wired into any live og:image tag - see og_images.py's module
docstring for why (the crawlable story page is English-canonical site-wide today; there is no
Hindi-canonical URL for a Hindi card to attach to). This module generates real, versioned PNGs
so the capability is ready whenever that product decision is made.
"""

import base64
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(ROOT, "static", "fonts")

W, H = 1200, 630

# Same font ROLES og_images.py uses, same real brand files - just handed to a browser instead
# of decoded into a Pillow ImageFont. Base64-inlined so the HTML is fully self-contained (no
# file:// resource loading, no relative-path/CORS surprises inside the headless page).
_FONT_FILES = {
    "deva":       "55xyezN7P8T4e0_CfIJrwdodg9HoYw0i-M9vT-MP.woff2",             # Tiro Devanagari Hindi 400
    "deva_sans":  "XRXH3JCMvG4IDoS9SubXB6W-UX5iehIMBFR2-O_PUkj1.woff2",         # IBM Plex Sans Devanagari 400
    "sans_bold":  "zYXzKVElMYYaJe8bpLHnCwDKr932-G7dytD-Dmu1syxeKYY.woff2",      # IBM Plex Sans 700 (PAKSH latin)
    "mono":       "-F6qfjptAgt5VM-kVkqdyU8n3vAOwlBFgg.woff2",                    # IBM Plex Mono 600 (outlet count)
}
_font_b64_cache = {}


def hindi_available():
    """True if Playwright + a Chromium binary are actually usable in this environment. Never
    raises - callers use this to decide whether to attempt Hindi generation at all."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.executable_path  # touches the install without launching
        return True
    except Exception:
        return False


def _font_b64(role):
    if role not in _font_b64_cache:
        with open(os.path.join(FONTS, _FONT_FILES[role]), "rb") as f:
            _font_b64_cache[role] = base64.b64encode(f.read()).decode("ascii")
    return _font_b64_cache[role]


LEAN_HI = {"left": "वाम", "center": "केंद्र", "right": "दक्षिण"}


def _blocks_html(L, C, R):
    colors = {"left": "#587A91", "center": "#6F6B61", "right": "#A46149"}
    groups = []
    for side, n in (("left", L), ("center", C), ("right", R)):
        if n <= 0:
            continue
        blocks = "".join('<div class="block" style="background:%s"></div>' % colors[side] for _ in range(n))
        groups.append('<div class="group">%s</div>' % blocks)
    total = L + C + R
    label = "%d आउटलेट" % total if total else ""  # "N आउटलेट"
    return '<div class="covrow">%s<span class="covlabel">%s</span></div>' % ("".join(groups), label)


def _card_html(ev, image_data_uri):
    title_hi = ev.get("title_hi") or ev.get("title") or ""
    topic_hi = ev.get("topic_hi") or ev.get("topic") or "समाचार"
    region_hi = "भारत" if (ev.get("region") or "India") == "India" else "विश्व"
    counts = ev.get("lean_counts") or {}
    L, C, R = int(counts.get("left", 0) or 0), int(counts.get("center", 0) or 0), int(counts.get("right", 0) or 0)

    on_dark_bg = "background:#15140F;" if not image_data_uri else ""
    hero = ('<div class="hero" style="background-image:url(%s)"></div><div class="scrim"></div>' % image_data_uri) if image_data_uri else ""

    return """<!DOCTYPE html><html><head><meta charset="UTF-8"/><style>
@font-face{{font-family:'Tiro Devanagari Hindi';src:url(data:font/woff2;base64,{deva}) format('woff2');}}
@font-face{{font-family:'IBM Plex Sans Devanagari';src:url(data:font/woff2;base64,{deva_sans}) format('woff2');}}
@font-face{{font-family:'IBM Plex Sans';font-weight:700;src:url(data:font/woff2;base64,{sans_bold}) format('woff2');}}
@font-face{{font-family:'IBM Plex Mono';font-weight:600;src:url(data:font/woff2;base64,{mono}) format('woff2');}}
*{{margin:0;padding:0;box-sizing:border-box;}}
html,body{{width:1200px;height:630px;overflow:hidden;{bg}}}
.card{{width:1200px;height:630px;position:relative;font-family:'IBM Plex Sans Devanagari',sans-serif;}}
.hero{{position:absolute;inset:0;background-size:cover;background-position:center 30%;}}
.scrim{{position:absolute;inset:0;background:linear-gradient(180deg,rgba(10,10,8,.55) 0%,rgba(10,10,8,.16) 15%,rgba(10,10,8,.07) 32%,rgba(10,10,8,.85) 70%,rgba(10,10,8,.96) 100%);}}
.top{{position:absolute;top:44px;left:56px;right:56px;display:flex;justify-content:space-between;align-items:baseline;}}
.wordmark{{display:flex;align-items:baseline;gap:10px;}}
.deva-logo{{font-family:'Tiro Devanagari Hindi',serif;font-size:32px;color:#F4F1EA;}}
.lat-logo{{font-family:'IBM Plex Sans',sans-serif;font-weight:700;font-size:24px;letter-spacing:.24em;color:#F4F1EA;}}
.domain{{font-family:'IBM Plex Sans',sans-serif;font-weight:700;font-size:17px;color:#F4F1EA;}}
.bottom{{position:absolute;left:56px;right:56px;bottom:44px;}}
.kicker{{font-size:16px;color:#C9C2B3;margin-bottom:16px;display:block;}}
.hl{{font-family:'Tiro Devanagari Hindi',serif;font-weight:400;font-size:48px;line-height:1.36;color:#FBFAF6;max-width:1030px;}}
.covrow{{margin-top:22px;display:flex;align-items:center;gap:16px;}}
.group{{display:flex;gap:4px;margin-right:14px;}}
.block{{width:14px;height:26px;border-radius:3px;}}
.covlabel{{font-size:15px;color:#B9B3A3;}}
</style></head><body><div class="card">
{hero}
<div class="top"><div class="wordmark"><span class="deva-logo">पक्ष</span><span class="lat-logo">PAKSH</span></div><div class="domain">paksh.news</div></div>
<div class="bottom"><span class="kicker">{topic} &nbsp;·&nbsp; {region}</span><div class="hl">{title}</div>{blocks}</div>
</div></body></html>""".format(
        deva=_font_b64("deva"), deva_sans=_font_b64("deva_sans"), sans_bold=_font_b64("sans_bold"), mono=_font_b64("mono"),
        bg=on_dark_bg, hero=hero, topic=topic_hi, region=region_hi, title=title_hi,
        blocks=_blocks_html(L, C, R),
    )


class HindiCardRenderer:
    """Context manager around ONE reused Chromium instance for a whole batch of cards - opens
    once, renders every card requested, closes once. Never raises: if the browser can't even
    start, __enter__ leaves this renderer in a disabled state and .render() just returns None
    for everything, so a caller can always do `with HindiCardRenderer() as r: ... r.render(...)`
    without a separate availability check first."""

    def __enter__(self):
        self._ok = False
        try:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch()
            self._page = self._browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
            self._ok = True
        except Exception:
            self._pw = None
            self._browser = None
            self._page = None
        return self

    def render(self, ev, out_path, image_data_uri=None):
        """Renders one Hindi card. Returns out_path on success, None on any failure (never
        raises) - a failed Hindi card is simply skipped by the caller, same fail-open contract
        as the English renderer's image handling."""
        if not self._ok:
            return None
        try:
            html = _card_html(ev, image_data_uri)
            self._page.set_content(html, wait_until="load")
            self._page.wait_for_timeout(60)  # let @font-face swap in before the screenshot
            os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
            self._page.screenshot(path=out_path, clip={"x": 0, "y": 0, "width": W, "height": H})
            return out_path
        except Exception:
            return None

    def __exit__(self, exc_type, exc, tb):
        for obj in (getattr(self, "_browser", None),):
            try:
                if obj:
                    obj.close()
            except Exception:
                pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        return False
