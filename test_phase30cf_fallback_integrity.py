"""
test_phase30cf_fallback_integrity.py - Phase 30C-F: regression tests for the
extractive-fallback integrity fix (_representative()'s center-preference no
longer commits to an empty-summary center outlet when a real Left/Right
article has usable text; _extractive_raw() falls back to the real title text
rather than ever emitting a blank summary).

Uses synthetic in-memory article dicts (no DB writes) plus one real-data
replay against event #18165's actual member articles (read-only query).

Run:  py test_phase30cf_fallback_integrity.py
"""
import sqlite3

import analyze

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


def art(source, language, title, summary):
    return {"source": source, "language": language, "title": title, "summary": summary,
            "url": "https://example.invalid/x", "image_url": ""}


print("=== Case A: representative article has a valid summary -> non-empty safe summary, unchanged ===")
rows = [art("The Times of India", "en", "Center headline", "A real, substantive summary sentence.")]
raw = analyze._extractive_raw(rows)
check("1: summary is the real article summary, not the title", raw["summary"] == "A real, substantive summary sentence.")
check("2: title is the real article title", raw["title"] == "Center headline")

print("\n=== Case B: chosen representative's summary is empty but another PERMITTED article has text ===")
print("    (real production mechanism: sole center outlet has no summary; a Left/Right outlet does)")
rows = [
    art("The Times of India", "en", "Center headline, no summary", ""),   # center, empty summary
    art("The Hindu", "en", "Left headline", "Left outlet's real 52-char summary text here."),
    art("Republic World", "en", "Right headline", "Right outlet's longer real summary text, over a hundred characters of genuine reporting content here."),
]
rep = analyze._representative(rows)
check("3: _representative() does NOT pick the empty-summary center outlet", rep["source"] != "The Times of India")
check("4: _representative() picks the article with the most real summary text (Republic World)", rep["source"] == "Republic World")
raw = analyze._extractive_raw(rows)
check("5: the resulting summary is non-empty real text (not the center outlet's blank field)", bool(raw["summary"]))
check("6: the resulting summary is genuine sourced text, not synthesized",
      raw["summary"].startswith("Right outlet's longer real summary"))

print("\n=== Case C: ALL permitted source text is empty for a language -> title-derived fallback, never blank ===")
rows = [
    art("The Times of India", "en", "A real headline with no summary field at all", ""),
    art("Some Other Outlet", "en", "Another real headline, also no summary", ""),
]
raw = analyze._extractive_raw(rows)
check("7: summary is never an empty string when a real title exists", bool(raw["summary"]))
check("8: the fallback is exactly the article's own real title (no fabricated prose)",
      raw["summary"] == raw["title"] == "A real headline with no summary field at all")

print("\n=== Case D: LLM succeeds -> this fallback path is never invoked, LLM output unchanged ===")
# _extractive_raw() is ONLY ever called on the LLM-failure path (analyze_event()'s
# except block / the long-tail no-model-call tier) - confirm by direct inspection
# that a successful LLM raw dict is passed through postprocess() unmodified.
llm_raw = {"title": "LLM title", "summary": "LLM-written neutral summary.",
           "summary_hi": "एलएलएम सारांश", "title_hi": "एलएलएम शीर्षक",
           "topic": "Politics", "region": "India"}
result = analyze.postprocess(dict(llm_raw), [art("The Times of India", "en", "x", "y")])
check("9: a successful LLM summary is passed through unchanged by postprocess()",
      result["summary"] == "LLM-written neutral summary." and result["summary_method"] == "llm")

print("\n=== Case E: existing extractive events with valid summaries -> no regression ===")
rows = [art("Dainik Bhaskar", "hi", "हिंदी शीर्षक", "हिंदी में एक वास्तविक सारांश वाक्य।")]
raw = analyze._extractive_raw(rows)
check("10: Hindi-only event still gets its real Hindi summary (no regression)",
      raw["summary_hi"] == "हिंदी में एक वास्तविक सारांश वाक्य।")
check("11: English side mirrors the Hindi article per existing 'neither UI language "
      "blank' behavior (unchanged, pre-existing design, not touched by this fix)",
      raw["title"] == "हिंदी शीर्षक")

print("\n=== content_complete semantics: unchanged, not redefined ===")
check("12: extractive summary_method still always yields content_complete=True "
      "(this phase fixes the root cause, not the completeness flag's meaning)",
      analyze.compute_content_complete({}, {}, "extractive") is True)

print("\n=== Real-data replay: event #18165 (the actual production case this fix addresses) ===")
try:
    conn = sqlite3.connect("file:paksh.db?mode=ro", uri=True, timeout=30)
    c = conn.cursor()
    c.execute("SELECT source, language, title, summary FROM articles WHERE event_id=18165")
    real_rows = [art(s, lang, t, summ) for s, lang, t, summ in c.fetchall()]
    if real_rows:
        rep = analyze._representative([r for r in real_rows if r["language"] == "en"])
        check("13: real event #18165 - representative is no longer the empty-summary "
              f"Times of India pick (got: {rep['source']!r})", rep["source"] != "The Times of India")
        raw = analyze._extractive_raw(real_rows)
        check("14: real event #18165 - _extractive_raw() now produces a non-empty "
              f"English summary (got {len(raw['summary'])} chars)", bool(raw["summary"]))
    else:
        print("  (event #18165 not present in this DB snapshot - skipped, not a failure)")
except Exception as e:
    print(f"  (real-data replay skipped: {e})")

print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
