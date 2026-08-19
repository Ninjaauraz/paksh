import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# import WITHOUT a key -> analyze.client is None, proving import/unit-test works offline
os.environ.pop("GEMINI_API_KEY", None)
import analyze

# ---- 1) tolerant JSON parser ----
cases = [
    ('```json\n{"a": 1, "b": [1,2,3]}\n```', {"a": 1, "b": [1, 2, 3]}),
    ('{"a": 1, "b": [1, 2,],}', {"a": 1, "b": [1, 2]}),                 # trailing commas
    ('Sure! Here is the JSON:\n{"x": "y"}\nHope that helps.', {"x": "y"}),  # prose-wrapped
    ('{"ok": true}', {"ok": True}),
]
for raw, want in cases:
    got = analyze._extract_json(raw)
    assert got == want, f"parser failed on {raw!r}: got {got}"
print("JSON parser: fences / trailing commas / prose-wrap all recovered ... OK")

# ---- 2) postprocess (full, healthy model output) ----
articles = [
    {"id": 1, "source": "The Hindu",      "language": "en", "title": "EN headline one",
     "url": "https://x/1", "image_url": "https://img/1.jpg", "summary": "s1"},
    {"id": 2, "source": "OpIndia", "language": "en", "title": "EN headline two",
     "url": "https://x/2", "image_url": "",                   "summary": "s2"},
    {"id": 3, "source": "Amar Ujala",     "language": "hi", "title": "हिंदी शीर्षक तीन",
     "url": "https://x/3", "image_url": "",                   "summary": "s3"},
]
raw = {
    "title": "Neutral title", "summary": "One neutral sentence.",
    "summary_points": ["point one", "point two"],
    "title_hi": "तटस्थ शीर्षक", "summary_hi": "एक तटस्थ वाक्य।",
    "summary_points_hi": ["बिंदु एक", "बिंदु दो"],
    "topic": "Politics",
    # per-side framing is now a LIST of bullet points (Ground-News style)
    "framing": {"left": ["left bullet a", "left bullet b"],
                "center": ["center bullet"], "right": ["right bullet"]},
    "framing_hi": {"left": ["वाम बिंदु"], "center": ["केंद्र बिंदु"], "right": ["दक्षिण बिंदु"]},
}
out = analyze.postprocess(raw, articles)
cov = out["coverage"]

# lean comes from sources.py: Hindu=left, OpIndia=right, Amar Ujala=center
assert (cov["left"]["count"], cov["center"]["count"], cov["right"]["count"]) == (1, 1, 1), cov
assert cov["left"]["sources"] == ["The Hindu"] and cov["right"]["sources"] == ["OpIndia"]
# MIN_SIDE_OWNERS=1: each side has exactly one owner, which is now ENOUGH to keep a
# synthesised summary (the one-source-summaries change) - it is no longer silently
# dropped. The UI's own deterministic "sole rated outlet" guardrail (not tested here,
# it lives in app.jsx and reads coverage[side].count===1) is what stops this from
# reading as a whole side's consensus, independent of whatever the model wrote.
assert out["framing"] == raw["framing"], out["framing"]
assert out["framing_hi"] == raw["framing_hi"], out["framing_hi"]
assert out["total_sources"] == 3 and out["degraded"] is False
assert out["image_url"] == "https://img/1.jpg"                 # first article with an image

byname = {s["source"]: s for s in out["sources"]}
assert byname["The Hindu"]["lean"] == "left" and byname["OpIndia"]["lean"] == "right"   # case-insensitive match
assert byname["Amar Ujala"]["lean"] == "center" and byname["Amar Ujala"]["headline"] == "हिंदी शीर्षक तीन"
assert out["title_hi"] == "तटस्थ शीर्षक" and out["summary_points_hi"] == ["बिंदु एक", "बिंदु दो"]
print("postprocess (healthy): coverage from our config, bilingual fields, "
      "per-side framing gated by unique-coverage threshold, hero image ... OK")

# ---- 2b) _clean_framing: list/string normalisation + unique-coverage threshold ----
cov2 = {"left": {"count": 3}, "center": {"count": 1}, "right": {"count": 2}}
cf = analyze._clean_framing(
    {"left": ["a", " b ", "", 5], "center": ["one-owner side, now kept"], "right": "legacy string"},
    cov2)
# MIN_SIDE_OWNERS=1: a one-owner side (center) is now KEPT, not dropped; a zero-owner
# side still would be (tested next).
assert cf == {"left": ["a", "b"], "center": ["one-owner side, now kept"], "right": ["legacy string"]}, cf
cov3 = {"left": {"count": 3}, "center": {"count": 0}, "right": {"count": 2}}
cf3 = analyze._clean_framing({"left": ["a"], "center": ["should be dropped, zero owners"], "right": ["b"]}, cov3)
assert cf3 == {"left": ["a"], "right": ["b"]}, cf3   # zero-owner side still dropped
assert analyze.has_framing(["", "  "]) is False and analyze.has_framing(["x"]) is True
assert analyze.has_framing("") is False and analyze.has_framing("y") is True
print("_clean_framing: bullets kept, one-owner side now kept, zero-owner side still dropped, "
      "legacy string wrapped ... OK")

# ---- 2c) international voting: eligibility comes from a FINAL region, not the reverse ----
# Reuters is a curated INTERNATIONAL-tier outlet with a known underlying lean (center).
assert analyze.lean_of("Reuters") == "international"          # no region passed -> safe default
assert analyze.lean_of("Reuters", "India") == "international"  # India story: never votes
assert analyze.lean_of("Reuters", "World") == "center"         # World story: votes its own lean
# An India-rated outlet's lean never changes with region - only the INTERNATIONAL tier does.
assert analyze.lean_of("The Hindu", "India") == "left" and analyze.lean_of("The Hindu", "World") == "left"
print("lean_of: international outlets vote only on World stories, India-tier outlets unaffected ... OK")

# ---- 2d) postprocess: region is decided from raw classification only, before coverage ----
world_articles = [
    {"id": 1, "source": "Reuters", "language": "en", "title": "Foreign headline",
     "url": "https://x/10", "image_url": "", "summary": "s"},
]
world_raw = {"title": "T", "summary": "S", "region": "World"}
out_world = analyze.postprocess(world_raw, world_articles)
# Reuters now votes CENTRE on this explicitly-World story - not the non-voting "international" tier.
assert out_world["coverage"]["center"]["count"] == 1, out_world["coverage"]
assert out_world["coverage"]["international"]["count"] == 0, out_world["coverage"]
assert out_world["region"] == "World"
india_raw = {"title": "T", "summary": "S", "region": "India"}
out_india = analyze.postprocess(india_raw, world_articles)
# Same outlet, same articles, only the story's OWN region differs -> Reuters stays non-voting.
assert out_india["coverage"]["center"]["count"] == 0, out_india["coverage"]
assert out_india["coverage"]["international"]["count"] == 1, out_india["coverage"]
print("postprocess: voting eligibility follows the story's own region, region never follows "
      "coverage composition ... OK")

# ---- 3) topic validation ----
assert analyze.postprocess({**raw, "topic": "Nonsense"}, articles)["topic"] == "Society"
print("postprocess: invalid topic coerced to 'Society' ... OK")

# ---- 4) graceful degradation (model produced nothing) ----
deg = analyze.postprocess({}, articles)
assert deg["degraded"] is True
assert deg["title"] == "EN headline one"                       # falls back to an article headline
assert (deg["coverage"]["left"]["count"], deg["coverage"]["center"]["count"],
        deg["coverage"]["right"]["count"]) == (1, 1, 1)        # bias bar still works
assert deg["summary"] == "" and deg["summary_points"] == []
print("postprocess (degraded): event still emits bias bar + sources, no fabricated text ... OK")

print("\nALL ASSERTIONS PASSED")
