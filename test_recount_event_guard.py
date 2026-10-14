"""
test_recount_event_guard.py - recount_event() must not let an extractive replacement
overwrite an existing LLM summary (2026-10-14 incident: events 27193 / 27268).

Everything touching the database is monkeypatched; analyze_event/postprocess are fakes.
Never touches the network or the production database.

Rule under test: protected only when stored summary_method == "llm" AND the new analysis
is "extractive". Missing/unknown stored method is NOT protected.

Run:  py test_recount_event_guard.py
"""
import analyze

FAILURES = []


def check(label, cond):
    print(f"  {label} ... {'OK' if cond else 'FAIL'}")
    if not cond:
        FAILURES.append(label)


ROWS = [{"id": 1}]
written = {}


def run(stored_method, new_method, resummarise=True, analyze_raises=False):
    """Returns the analysis passed to update_event()."""
    written.clear()
    existing = {"title": "OLD TITLE", "summary": "OLD LLM SUMMARY", "summary_method": stored_method}

    analyze.get_event_articles = lambda eid: ROWS
    analyze.get_event = lambda eid: dict(existing)

    def fake_analyze(rows):
        if analyze_raises:
            raise RuntimeError("llm down")
        return {"title": "NEW TITLE", "summary": "NEW SUMMARY", "summary_method": new_method}
    analyze.analyze_event = fake_analyze
    # postprocess(raw, rows) is the "keep existing brief, recount the rest" path: echo raw back
    analyze.postprocess = lambda raw, rows: dict(raw, recounted=True)
    analyze.update_event = lambda eid, a, bump_created=True: written.update(a)
    analyze.recount_event(1, resummarise=resummarise)
    return dict(written)


print("LLM -> extractive: existing brief preserved")
r = run("llm", "extractive")
check("title kept", r.get("title") == "OLD TITLE")
check("summary kept", r.get("summary") == "OLD LLM SUMMARY")
check("still recounted", r.get("recounted") is True)

print("LLM -> LLM: normal resummarisation")
r = run("llm", "llm")
check("new title written", r.get("title") == "NEW TITLE")

print("extractive -> extractive: normal update")
r = run("extractive", "extractive")
check("new title written", r.get("title") == "NEW TITLE")

print("extractive -> LLM: upgrade allowed")
r = run("extractive", "llm")
check("new title written", r.get("title") == "NEW TITLE" and r.get("summary_method") == "llm")

print("unknown stored method (None): not protected, extractive may replace")
r = run(None, "extractive")
check("new title written", r.get("title") == "NEW TITLE")

print("resummarise=False: unchanged (keeps existing, recounts)")
r = run("llm", "extractive", resummarise=False)
check("existing kept", r.get("title") == "OLD TITLE" and r.get("recounted") is True)
r = run("extractive", "llm", resummarise=False)
check("no LLM upgrade attempted", r.get("title") == "OLD TITLE")

print("analyze_event raises: existing kept (pre-existing behaviour)")
r = run("llm", "llm", analyze_raises=True)
check("existing kept", r.get("title") == "OLD TITLE")

print("\nFAILURES:", FAILURES if FAILURES else "none")
raise SystemExit(1 if FAILURES else 0)
