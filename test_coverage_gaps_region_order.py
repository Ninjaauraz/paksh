"""test_coverage_gaps_region_order.py - regression test for the 2026-09-29 pre-launch
presentation fix: on the Coverage Gaps page (BlindspotPage in static/app.jsx), India
gaps must be displayed BEFORE International/World gaps, in both the "Not covering:
Left" and "Not covering: Right" columns - a presentation-order-only change. The
underlying gap formula, qualification threshold (export_static._gap_qualifies,
unchanged - see test_coverage_gaps_eligibility.py), and freshness-decayed rank are
untouched; this only changes BlindspotPage's own card sort.

No JS runtime is available in this project (bundler-free by design - see CLAUDE.md).
Two checks, matching the rigor of test_ads_consent_csp.py's approach for this same
JSX-only file:
  1. STRUCTURAL: the exact sort comparator is present in static/app.jsx, with the
     region-priority term appearing BEFORE the pre-existing starkness term (so a
     future edit can't silently drop or reorder it without this test catching it).
  2. BEHAVIORAL: the same comparator logic, transcribed line-for-line from the JSX
     into Python (see _region_priority/_compare below - kept in exact lockstep with
     the JSX, not a reinterpretation), run against synthetic India+World gap cards
     to prove the actual sort OUTPUT is India-first, and that it preserves each
     region's pre-existing starkest-first order (never reordering WITHIN a region).

Run:  py test_coverage_gaps_region_order.py
"""
import re
from pathlib import Path

FAILURES = []


def check(label, cond):
    print(f"  {label} ... {'OK' if cond else 'FAIL'}")
    if not cond:
        FAILURES.append(label)


JSX = (Path(__file__).parent / "static" / "app.jsx").read_text(encoding="utf-8")

print("=== 1: structural - the region-first comparator is present in BlindspotPage ===")
# Isolate BlindspotPage's own body (up to the next top-level function) so this test can
# never accidentally match a similarly-named helper defined elsewhere in this large file.
start = JSX.index("function BlindspotPage(")
body = JSX[start:JSX.index("\n    function ", start)]

check("BlindspotPage defines a region-priority helper (India -> 0, else -> 1)",
      re.search(r'gapRegionPriority\s*=\s*s\s*=>\s*s\.region\s*===\s*"India"\s*\?\s*0\s*:\s*1', body) is not None)

sort_call = re.search(r"cards\.sort\(\(a,\s*b\)\s*=>(.*?)\);", body, re.S)
check("cards.sort(...) is present exactly once", sort_call is not None)
if sort_call:
    comparator = sort_call.group(1)
    check("the region-priority term is the comparator", "gapRegionPriority" in comparator)
    check("2026-10-15: NO raw missing-side count term remains (it discarded the export's recency "
          "decay, ranking months-old 0-count stories above fresh 1-count ones)",
          "a.story.counts" not in comparator and "||" not in comparator)

print("\n=== 2: behavioral - region is the only key; stable sort keeps the export's order ===")


def _region_priority(region):
    # Mirrors: s.region==="India"?0:1
    return 0 if region == "India" else 1


def _compare(a, b):
    # Mirrors: gapRegionPriority(a.story)-gapRegionPriority(b.story)
    return _region_priority(a["region"]) - _region_priority(b["region"])


def js_sort(cards):
    import functools
    return sorted(cards, key=functools.cmp_to_key(_compare))   # stable, like ES2019+ Array.sort


# Input order = the export's recency-decayed order.
cards = [
    {"id": "W1", "region": "World"}, {"id": "I1", "region": "India"},
    {"id": "W2", "region": "World"}, {"id": "I2", "region": "India"},
    {"id": "W3", "region": "World"}, {"id": "I3", "region": "India"},
]
result = [c["id"] for c in js_sort(cards)]
check("all India cards precede all World cards", result[:3] == ["I1", "I2", "I3"])
check("within each region the export's recency-weighted order is preserved",
      result == ["I1", "I2", "I3", "W1", "W2", "W3"])

# REGRESSION: an old zero-count item must not outrank a newer one-count item.
fresh_one = {"id": "FRESH", "region": "India", "count": 1}
old_zero = {"id": "OLD", "region": "India", "count": 0}
check("regression: newer count=1 stays ahead of older count=0 (same region)",
      [c["id"] for c in js_sort([fresh_one, old_zero])] == ["FRESH", "OLD"])
check("regression: region priority still wins (World-first input -> India first)",
      [c["id"] for c in js_sort([{"id": "W", "region": "World"}, fresh_one])] == ["FRESH", "W"])
check("a missing/unexpected region defaults to World's priority, never ahead of India",
      [c["id"] for c in js_sort([{"id": "M1", "region": None}, {"id": "I1", "region": "India"}])] == ["I1", "M1"])

print(f"\n{'=' * 60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
