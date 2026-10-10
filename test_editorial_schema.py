"""
test_editorial_schema.py - Milestone 1: the editorial document schema, protected-field
enforcement and the fail-safe loader. Pure and isolated: no database, no network, no
production paths, nothing written outside a throwaway temp directory.

Run:  py test_editorial_schema.py
"""
import copy
import json
import os
import sys
import tempfile

from editorial import document as D
from editorial import schema as S

FAILURES = []


def check(label, cond, detail=""):
    print(f"  {label} ... {'OK' if cond else 'FAIL'}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILURES.append(label)


def good():
    return {
        "schema_version": 1,
        "stories": {
            "26121": {"title": {"en": "Corrected headline", "hi": "सही शीर्षक"},
                      "teaser": {"en": "A short teaser."}},
        },
        "placements": [
            {"id": "lead-1", "scope": "home", "story_id": "26121", "action": "pin", "position": 1,
             "starts_at": "2026-10-10T06:00:00Z", "ends_at": "2026-10-10T18:00:00+05:30"},
            {"id": "hide-1", "scope": "section:economy", "story_id": "26122", "action": "hide"},
        ],
    }


def codes(doc):
    return S.validate_document(doc).codes()


print("1. valid documents")
check("1a: a representative document validates", S.validate_document(good()).ok)
check("1b: the empty document validates", S.validate_document(S.empty_document()).ok)
check("1c: validation does not mutate its input", (lambda d: (S.validate_document(d), d == good())[1])(good()))

print("2. structure is a strict whitelist")
d = good(); d["homepage"] = {}
check("2a: unknown top-level section rejected (future sections need a schema bump)", "unknown_key" in codes(d))
d = good(); d["stories"]["26121"]["colour"] = "red"
check("2b: unknown story field rejected", "unknown_key" in codes(d))
d = good(); d["placements"][0]["css"] = "x"
check("2c: unknown placement field rejected", "unknown_key" in codes(d))
d = good(); del d["schema_version"]
check("2d: missing schema_version rejected", "missing_version" in codes(d))
d = good(); d["schema_version"] = 2
check("2e: a newer version is refused, not guessed at", "unsupported_version" in codes(d))
d = good(); d["schema_version"] = True
check("2f: boolean is not a version", "missing_version" in codes(d))
check("2g: a non-object document is rejected", S.validate_document([]).errors[0]["code"] == "type")

print("3. protected analytical fields can never be edited")
for key in ("lean_counts", "dominant", "blindspot", "sources", "coverage", "framing", "evidence_status",
            "summary_method", "analysis_json", "bias", "ownership", "international", "topic", "region",
            "image_url", "summary_points", "total_sources"):
    d = good(); d["stories"]["26121"][key] = {"left": 99} if key == "lean_counts" else "x"
    c = codes(d)
    check(f"3: '{key}' rejected as protected", "protected_field" in c, str(c))
d = good(); d["stories"]["26121"]["title"]["lean_counts"] = 1
check("3a: protected key nested inside a text object is still caught", "protected_field" in codes(d))
d = good(); d["placements"][0]["lean_override"] = "right"
check("3b: protected PREFIX (lean_*) caught in placements", "protected_field" in codes(d))
d = good(); d["stories"]["26121"]["Evidence_Gate"] = 1
check("3c: protected prefix is case-insensitive", "protected_field" in codes(d))
d = good(); d["x"] = [{"sources": []}]
check("3d: protected key hidden inside a list is caught", "protected_field" in codes(d))
check("3e: placement 'id' (a legitimate key) is NOT mistaken for a protected field",
      "protected_field" not in codes(good()))

print("4. stable ids only")
for bad in ("0", "007", "-5", "12.5", "abc", "", "1" * 13, "Headline of the day"):
    d = good(); d["stories"] = {bad: {"title": {"en": "x"}}}
    check(f"4: story key {bad!r} rejected", "bad_story_id" in codes(d))
for bad in (26121, "headline", "", None, 3.5):
    d = good(); d["placements"][0]["story_id"] = bad
    check(f"4: placement story_id {bad!r} rejected", "bad_story_id" in codes(d))

print("5. text is plain, bounded, per-language")
def story(**t):
    d = good(); d["stories"]["26121"] = t; return d
check("5a: markup rejected", "markup" in codes(story(title={"en": "<b>hi</b>"})))
check("5b: script-ish angle brackets rejected", "markup" in codes(story(teaser={"en": "a<script>x"})))
check("5c: empty string rejected", "empty_text" in codes(story(title={"en": ""})))
check("5d: whitespace-only rejected", "empty_text" in codes(story(title={"en": "   "})))
check("5e: surrounding whitespace rejected", "surrounding_whitespace" in codes(story(title={"en": " x "})))
check("5f: over-long title rejected", "too_long" in codes(story(title={"en": "x" * 201})))
check("5g: title at the limit accepted", S.validate_document(story(title={"en": "x" * 200})).ok)
check("5h: newline in a title rejected", "control_character" in codes(story(title={"en": "a\nb"})))
check("5i: newline allowed in intro text", S.validate_document(story(intro={"en": "a\nb"})).ok)
check("5j: bidi override char rejected", "control_character" in codes(story(title={"en": "a‮b"})))
check("5k: zero-width space rejected", "control_character" in codes(story(title={"en": "a​b"})))
check("5l: Devanagari with ZWJ/ZWNJ accepted (needed for conjuncts)",
      S.validate_document(story(title={"hi": "क्‍ष और क‌ा"})).ok)
check("5m: unknown language rejected", "unknown_key" in codes(story(title={"fr": "x"})))
check("5n: a text field with no language rejected", "empty_override" in codes(story(title={})))
check("5o: a story with no editable field rejected", "empty_override" in codes(story()))
check("5p: non-string text rejected", "type" in codes(story(title={"en": 5})))
r = S.validate_document(story(title={"en": "a — b"}))
check("5q: an em dash is a WARNING (exporter strips it), not an error", r.ok and any(w["code"] == "dash" for w in r.warnings))
r = S.validate_document(story(title={"en": "Only English"}))
check("5r: English-only override warns that Hindi keeps generated text (never auto-translated)",
      r.ok and any(w["code"] == "missing_translation" for w in r.warnings))
d = story(title={"en": "x"}); d["stories"]["26121"]["base"] = {"title_en": "zz"}
check("5s: malformed fingerprint rejected", "bad_fingerprint" in codes(d))
d = story(title={"en": "x"}); d["stories"]["26121"]["base"] = {"teaser_hi": "a" * 64}
r = S.validate_document(d)
check("5t: fingerprint for a non-overridden field warns", r.ok and any(w["code"] == "orphan_base" for w in r.warnings))
r = S.validate_document(story(title={"en": "x"}))
check("5u: override without a fingerprint warns (staleness undetectable)", any(w["code"] == "missing_base" for w in r.warnings))

print("6. placements and time windows")
def pl(**kw):
    d = good(); d["placements"] = [dict({"id": "p1", "scope": "home", "story_id": "26121", "action": "pin"}, **kw)]; return d
check("6a: bad scope rejected", "bad_scope" in codes(pl(scope="topic:x")))
check("6b: scope 'section:india-world' accepted", S.validate_document(pl(scope="section:india-world")).ok)
check("6c: bad action rejected", "bad_action" in codes(pl(action="delete")))
check("6d: position 0 rejected", "bad_position" in codes(pl(position=0)))
check("6e: position 101 rejected", "bad_position" in codes(pl(position=101)))
check("6f: boolean position rejected", "bad_position" in codes(pl(position=True)))
check("6g: hide with a position rejected", "position_not_allowed" in codes(pl(action="hide", position=1)))
check("6h: timestamp without offset rejected", "bad_timestamp" in codes(pl(starts_at="2026-10-10T06:00:00")))
check("6i: impossible date rejected", "bad_timestamp" in codes(pl(starts_at="2026-02-30T00:00:00Z")))
check("6j: ends before starts rejected",
      "bad_window" in codes(pl(starts_at="2026-10-10T06:00:00Z", ends_at="2026-10-10T05:00:00Z")))
check("6k: ends equal to starts rejected",
      "bad_window" in codes(pl(starts_at="2026-10-10T06:00:00Z", ends_at="2026-10-10T06:00:00Z")))
check("6l: offset timestamps normalise to UTC",
      S.parse_utc("2026-10-10T11:30:00+05:30") == S.parse_utc("2026-10-10T06:00:00Z"))
d = good(); d["placements"].append(dict(d["placements"][0]))
check("6m: duplicate placement id rejected", "duplicate_id" in codes(d))
d = good(); d["placements"] = [
    {"id": "a", "scope": "home", "story_id": "5", "action": "pin"},
    {"id": "b", "scope": "home", "story_id": "5", "action": "hide"}]
check("6n: pin and hide on the same story/scope at the same time is contradictory", "contradictory_placements" in codes(d))
d["placements"][0].update(starts_at="2026-10-10T00:00:00Z", ends_at="2026-10-10T01:00:00Z")
d["placements"][1].update(starts_at="2026-10-10T01:00:00Z")
check("6o: back-to-back (non-overlapping) windows are allowed", S.validate_document(d).ok)
d = good(); d["placements"] = [
    {"id": "a", "scope": "home", "story_id": "5", "action": "pin"},
    {"id": "b", "scope": "home", "story_id": "5", "action": "pin"}]
check("6p: duplicate simultaneous pin rejected", "duplicate_placement" in codes(d))
d = good(); d["placements"] = [
    {"id": "a", "scope": "home", "story_id": "5", "action": "hide"},
    {"id": "b", "scope": "section:economy", "story_id": "5", "action": "pin"}]
check("6q: hiding in one scope while pinning in another is fine", S.validate_document(d).ok)
d = good(); d["stories"] = {str(i): {"title": {"en": "x"}} for i in range(1, 1002)}
check("6r: more than the story cap rejected", "too_many" in codes(d))

print("7. loader fails safe and never raises")
check("7a: None -> absent", D.load_text(None).status == "absent")
check("7b: missing file -> absent (normal, not an error)", D.load_file("/no/such/editorial.json").status == "absent")
check("7c: malformed JSON -> invalid", D.load_text("{nope").status == "invalid")
check("7d: duplicate JSON keys -> invalid", D.load_text('{"schema_version":1,"schema_version":1}').status == "invalid")
check("7e: NaN -> invalid", D.load_text('{"schema_version":NaN}').status == "invalid")
check("7f: deeply nested JSON -> invalid, not a crash", D.load_text("[" * 100000 + "]" * 100000).status == "invalid")
check("7g: oversize -> invalid", D.load_text(" " * (D.MAX_BYTES + 10)).status == "invalid")
check("7h: bad UTF-8 -> invalid", D.load_text(b"\xff\xfe\x00").status == "invalid")
check("7i: schema-invalid -> invalid with the codes", D.load_text('{"schema_version":1,"bogus":1}').status == "invalid")
ok = D.load_text(json.dumps(good()))
check("7j: valid -> ok with a hash and the document", ok.ok and len(ok.doc_hash) == 64 and ok.doc["schema_version"] == 1)
a = D.load_text(json.dumps(good(), indent=4)); b = D.load_text(json.dumps(good(), separators=(",", ":")))
check("7k: hash depends on content, not formatting", a.doc_hash == b.doc_hash)
g2 = good(); g2["stories"]["26121"]["title"]["en"] = "Other"
check("7l: any content change changes the hash", D.document_hash(g2) != D.document_hash(good()))
with tempfile.TemporaryDirectory() as tmp:
    p = os.path.join(tmp, "e.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(good(), f, ensure_ascii=False)
    check("7m: load_file reads a valid document", D.load_file(p).ok)
    check("7n: a directory path is invalid, not a crash", D.load_file(tmp).status == "invalid")

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("=" * 60)
print("ALL EDITORIAL SCHEMA CHECKS PASSED")
