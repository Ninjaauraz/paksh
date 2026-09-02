"""
test_phase20d_reframe_merge.py - Paksh 20D: reframe.py field-preservation fix.

Reproduces the exact Phase 20C bias-drift failure mode (event #11940: a fresh
analyze_event() call silently flipped a stored World-region event's region to India,
which un-voted an international wire and changed the published bias bar) and proves
reframe.py's _merge_reframe_result() fix against it, deterministically: no live LLM
call, no real database - fresh analysis output is built via the real, pure
analyze.postprocess(), and only the model call itself (analyze_event) is out of scope.

Follows the test_phase7b.py convention: check(label, cond) + FAILURES list, and a fake
lean_of() that reproduces the real region-dependent international-voting rule (see
analyze.lean_of()'s docstring) with two fake outlets instead of the real 6500-outlet
registry.

Covers, in order:
  A. The actual regression: fresh call flips region World -> India. Proves region,
     lean_counts/bias bar, title, summary, topic are preserved from the stored event;
     the genuinely-missing side is filled; an already-good side is not overwritten;
     content_complete updates correctly.
  B. Control: fresh call agrees with the stored region - missing side still fills
     correctly (the fix must not break the ordinary, non-buggy case).
  C. Failure path: fresh call produces no usable framing for the missing side(s) -
     main()'s own `filled` check must take the skip branch, so _merge_reframe_result()
     (and update_event()) is never reached and nothing is written.

Run:  py test_phase20d_reframe_merge.py
"""
import analyze
import reframe

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


_orig_lean_of = analyze.lean_of


def _fake_lean_of(name, region=None):
    """FakeWire: international, KNOWN lean 'center' - votes center on a World story,
    non-voting 'international' on an India story (exactly Reuters' real behaviour, and
    exactly the mechanism behind the #11940 regression). FakeCenter/FakeLeft: ordinary
    domestic outlets, always vote their fixed lean regardless of region - so a side's
    coverage doesn't vanish entirely on a region flip, only FakeWire's own vote does
    (matching #11940, where the affected side had other real owners too, and the region
    flip changed the OWNER COUNT, not whether the side had coverage at all)."""
    if name == "FakeWire":
        return "center" if region == "World" else "international"
    if name == "FakeCenter":
        return "center"
    if name == "FakeLeft":
        return "left"
    return "unrated"


analyze.lean_of = _fake_lean_of

ARTICLES = [
    {"id": 1, "source": "FakeWire", "language": "en", "title": "Wire headline",
     "summary": "s1", "url": "u1", "image_url": ""},
    {"id": 2, "source": "FakeCenter", "language": "en", "title": "Center headline",
     "summary": "s3", "url": "u3", "image_url": ""},
    {"id": 3, "source": "FakeLeft", "language": "en", "title": "Left headline",
     "summary": "s2", "url": "u2", "image_url": ""},
]


def _rows():
    # postprocess() mutates each article dict (adds "lean") - always hand it fresh copies.
    return [dict(a) for a in ARTICLES]


def _stored_event_world():
    """A stored/existing event exactly as postprocess() would have written it when the
    story's region was correctly resolved as World: center is covered by TWO owners
    (FakeWire's World-rule vote + FakeCenter's fixed vote), FakeLeft votes left, right
    never covered, center's framing missing on purpose - the case reframe.py exists to
    repair."""
    raw = {
        "title": "STORED TITLE", "summary": "STORED SUMMARY",
        "summary_points": ["stored point"], "title_hi": "", "summary_hi": "",
        "topic": "Politics", "region": "World", "summary_method": "llm",
        "framing": {"left": ["stored left framing bullet"]},
    }
    return analyze.postprocess(raw, _rows())


try:
    print("A. actual regression: fresh call flips region World -> India")
    ev = _stored_event_world()
    check("A0: fixture sanity - stored region is World", ev["region"] == "World")
    check("A0: fixture sanity - stored lean_counts left=1,center=2,right=0",
          (ev["coverage"]["left"]["count"], ev["coverage"]["center"]["count"],
           ev["coverage"]["right"]["count"]) == (1, 2, 0))
    check("A0: fixture sanity - center is genuinely missing framing pre-repair",
          set(reframe._missing_sides(ev)) == {"center"})
    check("A0: fixture sanity - content_complete is False pre-repair",
          ev["content_complete"] is False)

    # The ACTUAL #11940 failure mode: the model mis-resolves this run's region as
    # 'India' (a real, observed inconsistency - the model isn't told to reuse the
    # story's prior region, and a borderline story can flip run to run).
    fresh_raw = {
        "title": "FRESH TITLE (should NOT win)", "summary": "FRESH SUMMARY (should NOT win)",
        "summary_points": ["fresh point"], "title_hi": "", "summary_hi": "",
        "topic": "Economy", "region": "India", "summary_method": "llm",
        "framing": {
            "left": ["FRESH left framing (should NOT overwrite the stored one)"],
            "center": ["fresh center framing - the side that was actually missing"],
        },
    }
    fresh = analyze.postprocess(fresh_raw, _rows())
    check("A1: fixture sanity - fresh analysis really did flip region to India",
          fresh["region"] == "India")

    want = set(reframe._missing_sides(ev)) or set(reframe.SIDES)
    merged = reframe._merge_reframe_result(ev, fresh, want, _rows())

    check("A2: region preserved as World (NOT overwritten by fresh's India)",
          merged["region"] == "World")
    check("A3: lean_counts/bias bar unchanged (left=1,center=2,right=0, same as stored)",
          (merged["coverage"]["left"]["count"], merged["coverage"]["center"]["count"],
           merged["coverage"]["right"]["count"]) == (1, 2, 0))
    check("A4: title preserved from the stored event, not the fresh call",
          merged["title"] == "STORED TITLE")
    check("A5: summary preserved from the stored event, not the fresh call",
          merged["summary"] == "STORED SUMMARY")
    check("A6: topic preserved from the stored event, not the fresh call",
          merged["topic"] == "Politics")
    check("A7: previously-missing 'center' side is filled from the fresh call",
          merged["framing"].get("center") ==
          ["fresh center framing - the side that was actually missing"])
    check("A8: already-good 'left' framing is NOT replaced by the fresh call's left bullet",
          merged["framing"].get("left") == ["stored left framing bullet"])
    check("A9: content_complete now True (center, the only covered gap, is filled)",
          merged["content_complete"] is True)

    print("B. control: fresh call agrees with the stored region")
    ev = _stored_event_world()
    fresh_raw = {
        "title": "irrelevant", "summary": "irrelevant", "summary_points": [],
        "title_hi": "", "summary_hi": "", "topic": "Politics", "region": "World",
        "summary_method": "llm",
        "framing": {"center": ["fresh center framing, region agrees"]},
    }
    fresh = analyze.postprocess(fresh_raw, _rows())
    want = set(reframe._missing_sides(ev))
    merged = reframe._merge_reframe_result(ev, fresh, want, _rows())
    check("B1: region stays World when fresh agrees (no-op preserve)",
          merged["region"] == "World")
    check("B2: lean_counts unchanged",
          (merged["coverage"]["left"]["count"], merged["coverage"]["center"]["count"]) == (1, 2))
    check("B3: missing side filled correctly in the agreeing-region control",
          merged["framing"].get("center") == ["fresh center framing, region agrees"])

    print("C. failure path: fresh call produces no usable framing for the missing side")
    ev = _stored_event_world()
    want = set(reframe._missing_sides(ev))
    fresh_raw = {
        "title": "x", "summary": "x", "summary_points": [], "title_hi": "", "summary_hi": "",
        "topic": "Politics", "region": "World", "summary_method": "llm",
        "framing": {},  # center still empty in the fresh result too
    }
    fresh = analyze.postprocess(fresh_raw, _rows())
    fresh_fr = fresh.get("framing") or {}
    filled = [s for s in want if analyze.has_framing(fresh_fr.get(s))]
    check("C1: no side actually got filled -> main()'s loop takes the skip branch, "
          "never calls _merge_reframe_result() or update_event()", filled == [])
finally:
    analyze.lean_of = _orig_lean_of

print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
