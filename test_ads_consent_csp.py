"""
test_ads_consent_csp.py - advertising must be consent-gated, and the CSP must be enforced.

Background: static/index.html used to contain a hard-coded Google AdSense <script> that ran for every
visitor before any consent, contradicting the privacy policy. The loader now lives in static/app.jsx
(loadAdSense), is reachable only after the visitor's own advertising choice ("paksh-consent-ads" ==
"granted"), and the Content-Security-Policy is enforced with the AdSense hosts explicitly allowlisted.

This is a STATIC regression test (no browser, no DB, no network). The behavioural checks - no Google
request before consent, ads load after consent, withdrawal reloads, no CSP violations across the app,
blocked foreign script/frame - were run in a real browser against a sandbox build and are recorded in
PAKSH_EXECUTION_STATUS.md.

Run:  py test_ads_consent_csp.py
"""
import re
from pathlib import Path

import export_static

ROOT = Path(__file__).parent
FAILURES = []


def check(label, cond):
    print(f"  {label} ... {'OK' if cond else 'FAIL'}")
    if not cond:
        FAILURES.append(label)


HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
JSX = (ROOT / "static" / "app.jsx").read_text(encoding="utf-8")
EXPORT = (ROOT / "export_static.py").read_text(encoding="utf-8")
CSP = export_static.CSP_POLICY


def directive(name):
    m = re.search(r"(?:^|;\s*)" + re.escape(name) + r"\s+([^;]*)", CSP)
    return (m.group(1).split() if m else [])


print("=== no advertising script in the static shell ===")
check("1: static/index.html contains no AdSense / Google ad host at all",
      not re.search(r"googlesyndication|adsbygoogle|doubleclick|pagead|adtrafficquality", HTML, re.I))
shell = export_static._story_html(HTML, {"id": 1, "title": "T", "summary": "S", "created_at": "2026-09-19T00:00:00",
                                         "coverage": {}, "sources": []})
check("2: a generated story page inherits no ad tag either",
      not re.search(r"googlesyndication|adsbygoogle|doubleclick|pagead", shell, re.I))

print("\n=== the loader is reachable only through the advertising consent ===")
check("3: the AdSense host appears in app.jsx exactly once (inside loadAdSense)",
      len(re.findall(r"pagead2\.googlesyndication\.com", JSX)) == 1)
body = JSX[JSX.index("const loadAdSense = () => {"):JSX.index("// track(name, props)")]
check("4: loadAdSense is a single-run injector (guarded by window.__pakshAds)", "window.__pakshAds" in body)
calls = [m.start() for m in re.finditer(r"loadAdSense\(\)", JSX)]
guarded = [c for c in calls if 'adsConsent==="granted"' in JSX[max(0, c - 60):c]]
check("5: loadAdSense() is called from exactly one place, directly behind adsConsent===\"granted\"",
      len(calls) == 1 and len(guarded) == 1)
check("6: ad consent is its own key, not the analytics key",
      'localStorage.getItem("paksh-consent-ads")' in JSX and 'setItem("paksh-consent-ads"' in JSX)
check("7: ad consent defaults to undecided (never pre-selected)",
      re.search(r'getItem\("paksh-consent-ads"\) \|\| ""', JSX) is not None)
check("8: analytics consent is never consulted to load ads",
      "consentState()" not in body and 'consent==="granted") loadAdSense' not in JSX)
check("9: withdrawing ad consent after load reloads the page (an ad script cannot be unloaded)",
      "window.location.reload()" in JSX and "wasLoaded" in JSX)
check("10: the banner asks the ad question separately, with equal-weight accept and decline",
      "onChooseAds(\"denied\")" in JSX and "onChooseAds(\"granted\")" in JSX)
check("11: Settings and Privacy expose an advertising toggle",
      "setAdsConsent && row(" in JSX and "setAdsConsent && (" in JSX)
check("12: every new consent string exists in Hindi as well as English",
      all(re.search(k + r':"[^"]*[ऀ-ॿ]', JSX) for k in ("adText", "allowAds", "noAds", "adsS", "adSub", "adH", "ads")))

print("\n=== CSP is enforced and explicit ===")
check("13: exporter no longer ships a Report-Only policy", "Content-Security-Policy-Report-Only" not in EXPORT)
check("14: the ENFORCED header is the full policy", '"Content-Security-Policy": CSP_POLICY' in EXPORT)
check("15: default-src 'self'", directive("default-src") == ["'self'"])
check("16: script-src has no 'unsafe-inline' and no 'unsafe-eval'",
      not {"'unsafe-inline'", "'unsafe-eval'", "*", "https:", "data:"} & set(directive("script-src")))
check("17: script-src allows exactly self + the two Google ad script hosts",
      set(directive("script-src")) == {"'self'", "https://pagead2.googlesyndication.com", "https://*.adtrafficquality.google"})
check("18: frame-src lists the ad frames explicitly (no wildcard-all, not 'none')",
      {"https://googleads.g.doubleclick.net", "https://tpc.googlesyndication.com", "https://www.google.com"} <= set(directive("frame-src"))
      and "*" not in directive("frame-src") and "'none'" not in directive("frame-src"))
check("19: connect-src keeps Supabase / Formspree / Vercel vitals and adds Google's sodar host",
      {"https://formspree.io", "https://vitals.vercel-insights.com", "https://zzjsjqqcpyyodatlmcux.supabase.co",
       "https://*.adtrafficquality.google"} <= set(directive("connect-src")))
check("20: structural protections intact (frame-ancestors none, object-src none, base-uri self, form-action)",
      directive("frame-ancestors") == ["'none'"] and directive("object-src") == ["'none'"]
      and directive("base-uri") == ["'self'"] and "https://formspree.io" in directive("form-action"))
check("21: the policy is one line of valid directives (no stray newline/quote)",
      "\n" not in CSP and CSP.count("'") % 2 == 0)

print(f"\n{'=' * 60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
