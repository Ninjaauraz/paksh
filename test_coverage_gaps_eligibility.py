"""
test_coverage_gaps_eligibility.py - regression test for the 2026-09-27 Coverage Gaps
eligibility broadening in export_static._gap_qualifies().

BACKGROUND: a read-only production-corpus comparison found the original 25% (~4:1)
eligibility rule excluded most breadth>=8 asymmetric stories (the current top-50 had
ZERO breadth>=8 stories) while the qualifying pool was already dominated by low-breadth,
non-ideological noise regardless of ratio. The approved fix broadens the ratio gate from
25% to 50% (~2:1), keeping L+R>=4 unchanged. See the Coverage Gaps eligibility decision
report for the full corpus analysis - this test only pins the resulting BEHAVIOR of
_gap_qualifies(), not the source text.

Run:  py test_coverage_gaps_eligibility.py
"""
from export_static import _gap_qualifies

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


print("=== behavior of _gap_qualifies(L, R) at the new ~2:1 (50%) eligibility ===")

check("1: 10L/4R qualifies (4 <= 0.50*10)",
      _gap_qualifies(10, 4) is True)

check("2: 4L/0R qualifies (a complete one-sided split still passes the ratio gate)",
      _gap_qualifies(4, 0) is True)

check("3: 5L/5R does NOT qualify (equal sides - no skew at all)",
      _gap_qualifies(5, 5) is False)

check("4: 3L/9R qualifies (3 <= 0.50*9, direction-symmetric - minority can be either side)",
      _gap_qualifies(3, 9) is True)

check("5a: total below 4 does NOT qualify even with a complete split (3L/0R)",
      _gap_qualifies(3, 0) is False)
check("5b: total below 4 does NOT qualify even with a complete split (2L/0R)",
      _gap_qualifies(2, 0) is False)

print("\n=== the actual 2:1 boundary, established with integer inputs ===")
check("6a: 4L/2R qualifies - EXACTLY 2:1 (2 <= 0.50*4), the boundary is inclusive",
      _gap_qualifies(4, 2) is True)
check("6b: 3L/2R does NOT qualify - just OUTSIDE the boundary (1.5:1, milder than 2:1; "
      "2 <= 0.50*3=1.5 is false)",
      _gap_qualifies(3, 2) is False)

print("\n=== nothing that qualified under the old 25% rule stopped qualifying (25% ⊂ 50%) ===")
check("7: 8L/2R still qualifies (was already 4:1 under the old rule, still qualifies now)",
      _gap_qualifies(8, 2) is True)

print(f"\n{'=' * 60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
