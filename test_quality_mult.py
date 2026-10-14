"""V2 ranking: extractive/unknown methods are demoted by EXTRACTIVE_MULT; llm is untouched; order among llm unchanged."""
from datetime import datetime
import homepage_rank as hr
F = []
def check(l, c):
    print(f"  {l} ... {'OK' if c else 'FAIL'}")
    if not c: F.append(l)
now = datetime(2026, 10, 14, 6, 0)
ev = lambda m: {"id": 1, "region": "India", "title": "x", "summary_method": m, "lean_counts": {"left": 2, "center": 3, "right": 1},
                "international": 0, "created_at": "2026-10-14T05:50:00", "published_at": "2026-10-14T05:50:00"}
si, vel = {"independent_count": 2}, {"owners_recent": 4}
llm = hr.homepage_rank_story(ev("llm"), si, vel, now)["score"]
ext = hr.homepage_rank_story(ev("extractive"), si, vel, now)["score"]
unk = hr.homepage_rank_story(ev(None), si, vel, now)["score"]
check("llm multiplier is 1.0", hr.quality_mult(ev("llm")) == 1.0)
check("extractive multiplier is 0.7", hr.quality_mult(ev("extractive")) == hr.EXTRACTIVE_MULT == 0.7)
check("unknown method treated as extractive", hr.quality_mult({}) == 0.7 and abs(unk - ext) < 1e-9)
check("extractive score = 0.7 x llm score", abs(ext - 0.7 * llm) < 1e-4)
check("momentum also demoted", abs(hr.momentum_score(ev("extractive"), si, vel, now) - 0.7 * hr.momentum_score(ev("llm"), si, vel, now)) < 1e-4)
check("never zeroed (demote, not remove)", ext > 0)
# export_static fallback path uses the SAME shared multiplier (deferred import; no circularity)
try:
    import os
    os.environ.setdefault("PAKSH_ALLOW_NEW_DB", "1")
    import export_static as ex
    row = lambda m: ex.feed_row({"id": 1, "summary_method": m, "lean_counts": {"left": 1, "center": 1, "right": 1}, "international": 0,
                                 "created_at": "2026-10-14T05:00:00", "published_at": "2026-10-14T05:00:00", "topic": "Politics",
                                 "title": "t", "region": "India"}, {}, now)["feed_rank"]
    check("export_static fallback applies quality_mult (ratio 0.7)", abs(row("extractive") / row("llm") - 0.7) < 0.01)
    check("homepage_rank keeps export_static's CIVIC_KEYWORDS (no circular-import fallback)", hr.CIVIC_KEYWORDS is ex.CIVIC_KEYWORDS)
except Exception as e:
    check("export_static importable for fallback check (%s)" % type(e).__name__, False)
print("FAILURES:", F or "none"); raise SystemExit(1 if F else 0)
