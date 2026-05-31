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
    "sources": [
        {"source": "the hindu", "headline": "Hindu head", "framing": "f-left",
         "tone": "critical", "notable_language": ["sweeping"]},          # lowercase name
        {"source": "OpIndia", "headline": "OI head", "framing": "f-right",
         "tone": "supportive", "notable_language": []},
        # Amar Ujala intentionally omitted by the model
    ],
    "sides": {"left": "left framing", "center": "center framing", "right": "right framing"},
    "divergence": "they differ", "omissions": "some omit X",
}
out = analyze.postprocess(raw, articles)
cov = out["coverage"]

# lean comes from sources.py: Hindu=left, OpIndia=right, Amar Ujala=center
assert (cov["left"]["count"], cov["center"]["count"], cov["right"]["count"]) == (1, 1, 1), cov
assert cov["left"]["sources"] == ["The Hindu"] and cov["right"]["sources"] == ["OpIndia"]
assert cov["center"]["framing"] == "center framing"
assert out["total_sources"] == 3 and out["degraded"] is False
assert out["image_url"] == "https://img/1.jpg"                 # first article with an image

byname = {s["source"]: s for s in out["sources"]}
assert byname["The Hindu"]["framing"] == "f-left" and byname["The Hindu"]["tone"] == "critical"   # case-insensitive match
assert byname["Amar Ujala"]["framing"] == "" and byname["Amar Ujala"]["headline"] == "हिंदी शीर्षक तीन"  # omitted -> safe defaults
assert out["title_hi"] == "तटस्थ शीर्षक" and out["summary_points_hi"] == ["बिंदु एक", "बिंदु दो"]
print("postprocess (healthy): coverage from our config, bilingual fields, "
      "case-insensitive source match, hero image ... OK")

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
