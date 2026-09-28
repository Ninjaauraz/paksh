"""test_materiality_audit.py - adversarial + regression tests for
materiality_audit.py. Pure function tests plus one integration regression
check against the real 40-story data (frozen numbers, not re-derived from
belief - if these ever change, it means the underlying data or logic changed,
which is exactly what a regression test should catch). ZERO API calls, ZERO
network access.

Run:  py test_materiality_audit.py
"""
from materiality_audit import (
    classify_materiality, _title_matches_subject, build_audit_dataset,
    M1, M2, M3, M4, M5, UNKNOWN, OFFICE_HOLDING_STATUSES, LEGAL_ALLEGATION_STATUSES,
)
from consistency_checks import HIGH_RISK_STATUS_VALUES

FAILURES = []


def check(label, cond):
    print(f"  {'OK ' if cond else 'FAIL'} {label}")
    if not cond:
        FAILURES.append(label)


print("=== Structural: family split exactly reproduces HIGH_RISK_STATUS_VALUES ===")
check("OFFICE_HOLDING | LEGAL_ALLEGATION == consistency_checks.HIGH_RISK_STATUS_VALUES",
      OFFICE_HOLDING_STATUSES | LEGAL_ALLEGATION_STATUSES == HIGH_RISK_STATUS_VALUES)
check("the two families are disjoint", not (OFFICE_HOLDING_STATUSES & LEGAL_ALLEGATION_STATUSES))

print("\n=== _title_matches_subject ===")
check("exact substring match", _title_matches_subject("Ro Khanna", "US Lawmaker Ro Khanna Reports Detention") is True)
check("no match at all", _title_matches_subject("the doctor", "Bihar Floods: Rivers Exceed Danger Levels") is False)
check("multi-word subject, majority token overlap -> match",
      _title_matches_subject("West Bengal BJP government", "West Bengal BJP government presents maiden budget") is True)
check("short (<4 char) subject 'CJP' never matches via the substring/token path, even when the "
      "title literally contains it verbatim - by design, so a bare 3-letter acronym can never "
      "inflate materiality via a coincidental short-string hit",
      _title_matches_subject("CJP", "CJP held a rally today in the city") is False)
check("empty subject -> False, never crashes", _title_matches_subject("", "Some title") is False)
check("empty title -> False, never crashes", _title_matches_subject("Ro Khanna", "") is False)
check("None subject -> False, never crashes", _title_matches_subject(None, "Some title") is False)

print("\n=== classify_materiality: OFFICE_HOLDING family ===")
lvl, reason = classify_materiality("Jane Doe", "CURRENT_EXPLICIT", "holds the role of", "Jane Doe Becomes Chief Minister")
check("title-matched office-holding -> M1", lvl == M1)
lvl, reason = classify_materiality("a district official", "FORMER_EXPLICIT", "holds the role of", "Bihar Floods: Rivers Exceed Danger Levels")
check("non-title-matched office-holding -> M3 (never demoted below M3)", lvl == M3)

print("\n=== classify_materiality: LEGAL_ALLEGATION family ===")
lvl, reason = classify_materiality("the minister", "ALLEGED_EXPLICIT", "was accused of", "Minister Faces Bribery Allegations")
check("title-matched legal/allegation -> M2", lvl == M2)
lvl, reason = classify_materiality("a local shopkeeper", "CHARGED_EXPLICIT", "was charged with", "National Budget Announced for Fiscal Year")
check("non-title-matched legal/allegation -> M3 (never demoted below M3)", lvl == M3)

print("\n=== classify_materiality: missing data -> UNKNOWN, never guessed ===")
lvl, reason = classify_materiality(None, "CURRENT_EXPLICIT", "holds", "Some title")
check("missing subject -> UNKNOWN", lvl == UNKNOWN)
lvl, reason = classify_materiality("X", None, "holds", "Some title")
check("missing status -> UNKNOWN", lvl == UNKNOWN)
lvl, reason = classify_materiality("X", "OCCURRED_EXPLICIT", "took place", "X Event Occurs")
check("status outside the office-holding/legal-allegation family map -> UNKNOWN, not guessed into M1-M3", lvl == UNKNOWN)

print("\n=== classify_materiality never produces M4 or M5 (assigned only by the caller) ===")
never_m4_m5 = True
for status in HIGH_RISK_STATUS_VALUES:
    for title_matched_subject, title in (("X", "Story About X"), ("Y", "Unrelated Title")):
        lvl, _ = classify_materiality(title_matched_subject, status, "predicate", title)
        if lvl in (M4, M5):
            never_m4_m5 = False
check("classify_materiality never returns M4/M5 across all 10 HIGH_RISK_STATUS_VALUES x match/no-match", never_m4_m5)

print("\n=== Regression: real 40-story data produces the exact, already-verified distribution ===")
records = build_audit_dataset()
check("exactly 82 records (81 omit + 1 drop)", len(records) == 82)
from collections import Counter
dist = Counter(r["materiality"] for r in records)
check("distribution matches the measured run: M1=18 M2=24 M3=37 M5=3 M4=0 UNKNOWN=0",
      dist.get(M1, 0) == 18 and dist.get(M2, 0) == 24 and dist.get(M3, 0) == 37
      and dist.get(M5, 0) == 3 and dist.get(M4, 0) == 0 and dist.get(UNKNOWN, 0) == 0)
check("every record carries explicit CAPTURED/DERIVED_OFFLINE/MISSING field_sources",
      all(set(r["field_sources"].values()) <= {"CAPTURED", "DERIVED_OFFLINE"} or
          any("MISSING" in v for v in r["field_sources"].values()) for r in records))

print(f"\n{'=' * 60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s):")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL MATERIALITY AUDIT CHECKS PASSED")
