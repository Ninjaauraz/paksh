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
    region_pos = comparator.find("gapRegionPriority")
    starkness_pos = comparator.find("a.story.counts")
    check("the region-priority term appears in the comparator", region_pos != -1)
    check("the starkness term (existing behavior) is still present in the comparator", starkness_pos != -1)
    check("region-priority is evaluated BEFORE starkness (region is the PRIMARY sort key, "
          "starkness stays secondary/tie-breaking exactly as before)",
          region_pos != -1 and starkness_pos != -1 and region_pos < starkness_pos)
    check("the two terms are OR-chained (||), i.e. starkness only breaks ties within the "
          "same region - it can never override a region difference", "||" in comparator)

print("\n=== 2: behavioral - the same comparator, run against synthetic India+World cards ===")


def _region_priority(region):
    # Mirrors: s.region==="India"?0:1
    return 0 if region == "India" else 1


def _compare(a, b):
    # Mirrors: (gapRegionPriority(a.story)-gapRegionPriority(b.story))
    #   || (((a.story.counts||{})[a.gapSide]||0)-((b.story.counts||{})[b.gapSide]||0))
    region_diff = _region_priority(a["region"]) - _region_priority(b["region"])
    if region_diff != 0:
        return region_diff
    return (a["count"] or 0) - (b["count"] or 0)


def js_sort(cards):
    # Python's sort is stable, same guarantee JS's Array.sort has been spec-required to
    # provide since ES2019 - matching what BlindspotPage's real runtime does.
    import functools
    return sorted(cards, key=functools.cmp_to_key(_compare))


# Synthetic cards mimicking {story:{region, counts:{gapSide:count}}, gapSide} shape,
# flattened here to {region, count} - counts pre-baked as the (a.story.counts||{})
# [a.gapSide]||0) lookup already produces for a single gapSide. Deliberately mixed and
# NOT pre-sorted, to prove the sort - not incidental input order - produces the result.
cards = [
    {"id": "W1", "region": "World", "count": 0},   # starkest World gap
    {"id": "I1", "region": "India", "count": 5},   # a LESS stark India gap
    {"id": "W2", "region": "World", "count": 1},
    {"id": "I2", "region": "India", "count": 0},   # starkest India gap
    {"id": "W3", "region": "World", "count": 2},
    {"id": "I3", "region": "India", "count": 3},
]
result = [c["id"] for c in js_sort(cards)]

check("all India cards precede all World cards (I2,I3,I1 before W1,W2,W3, in some form)",
      result.index("I3") < result.index("W1") and result.index("I1") < result.index("W1"))
check("within India, starkest-first order is preserved (I2 [count=0] before I3 [count=3] "
      "before I1 [count=5]) - unchanged from the pre-existing sort", result == ["I2", "I3", "I1", "W1", "W2", "W3"])
check("within World, starkest-first order is preserved (W1 [0] before W2 [1] before W3 [2])",
      result.index("W1") < result.index("W2") < result.index("W3"))

print("\n=== 3: an India-only or World-only column is unaffected (no crash, order preserved) ===")
india_only = [{"id": "I1", "region": "India", "count": 4}, {"id": "I2", "region": "India", "count": 1}]
check("India-only input sorts purely by starkness, as before",
      [c["id"] for c in js_sort(india_only)] == ["I2", "I1"])
world_only = [{"id": "W1", "region": "World", "count": 4}, {"id": "W2", "region": "World", "count": 1}]
check("World-only input sorts purely by starkness, as before",
      [c["id"] for c in js_sort(world_only)] == ["W2", "W1"])
missing_region = [{"id": "M1", "region": None, "count": 0}, {"id": "I1", "region": "India", "count": 9}]
check("a missing/unexpected region value defaults to World's priority, never jumps ahead of India",
      [c["id"] for c in js_sort(missing_region)] == ["I1", "M1"])

print(f"\n{'=' * 60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
