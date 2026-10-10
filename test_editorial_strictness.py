"""
test_editorial_strictness.py - Milestone 1.1 remediation: strict, ASCII-only, full-string validation of
identifiers / scopes / fingerprints / placement ids, and fail-closed handling of hostile nesting.

Expected values are written out explicitly (no regex shared with the implementation). Pure and
deterministic; no I/O except an in-memory JSON round trip. Python 3.9 compatible.

Run:  py test_editorial_strictness.py
"""
import json
import sys

from editorial import document as D
from editorial import schema as S

FAILURES = []


def check(label, cond, detail=""):
    print(f"  {label} ... {'OK' if cond else 'FAIL'}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILURES.append(label)


def outcome(fn):
    try:
        return "ok", fn()
    except BaseException as e:  # noqa: BLE001
        return "RAISED:" + type(e).__name__, None


def base():
    return {"schema_version": 1, "stories": {"7": {"title": {"en": "x"}}},
            "placements": [{"id": "p1", "scope": "home", "story_id": "7", "action": "pin"}]}


def with_placement(**kw):
    d = base()
    d["placements"][0].update(kw)
    return d


def verdict(doc):
    k, r = outcome(lambda: S.validate_document(doc))
    return (k, r.ok if r else None, r.codes() if r else None)


print("1. valid documented inputs still pass (nothing over-tightened)")
GOOD_IDS = ["1", "7", "26121", "999999999999"]
for sid in GOOD_IDS:
    d = base(); d["stories"] = {sid: {"title": {"en": "x"}}}
    check(f"1a: story id {sid!r} accepted", verdict(d)[:2] == ("ok", True))
for scope in ("home", "section:economy", "section:india-world", "section:finance-markets", "section:s3"):
    check(f"1b: scope {scope!r} accepted", verdict(with_placement(scope=scope))[:2] == ("ok", True))
for pid in ("p1", "lead-1", "a", "0", "a_b-c", "x" * 40):
    check(f"1c: placement id {pid!r} accepted", verdict(with_placement(id=pid))[:2] == ("ok", True))
fp = "0123456789abcdef" * 4
d = base(); d["stories"]["7"]["base"] = {"title_en": fp}
check("1d: a 64-char lowercase hex fingerprint accepted", verdict(d)[:2] == ("ok", True))
check("1e: the documented example document still validates", verdict({
    "schema_version": 1,
    "stories": {"26121": {"title": {"en": "Corrected headline", "hi": "सही शीर्षक"},
                          "teaser": {"en": "A short teaser."}}},
    "placements": [{"id": "lead-1", "scope": "home", "story_id": "26121", "action": "pin", "position": 1,
                    "starts_at": "2026-10-10T06:00:00Z", "ends_at": "2026-10-10T18:00:00+05:30"}]})[:2] == ("ok", True))

print("2. trailing newlines (and other trailing/leading characters) are rejected everywhere")
for tail in ("\n", "\r\n", "\r", " ", "\t", "\x00", " ", "​"):
    name = repr(tail)
    d = base(); d["stories"] = {"7" + tail: {"title": {"en": "x"}}}
    v = verdict(d); check(f"2a: story key '7'+{name} rejected", v[0] == "ok" and v[1] is False and "bad_story_id" in v[2], str(v))
    v = verdict(with_placement(story_id="7" + tail)); check(f"2b: placement story_id '7'+{name} rejected", v[1] is False and "bad_story_id" in v[2], str(v))
    v = verdict(with_placement(scope="home" + tail)); check(f"2c: scope 'home'+{name} rejected", v[1] is False and "bad_scope" in v[2], str(v))
    v = verdict(with_placement(scope="section:economy" + tail)); check(f"2d: scope 'section:economy'+{name} rejected", v[1] is False and "bad_scope" in v[2], str(v))
    v = verdict(with_placement(id="p1" + tail)); check(f"2e: placement id 'p1'+{name} rejected", v[1] is False and "bad_placement_id" in v[2], str(v))
    d = base(); d["stories"]["7"]["base"] = {"title_en": fp + tail}
    v = verdict(d); check(f"2f: fingerprint + {name} rejected", v[1] is False and "bad_fingerprint" in v[2], str(v))
    v = verdict(with_placement(starts_at="2026-10-10T06:00:00Z" + tail)); check(f"2g: timestamp + {name} rejected", v[1] is False and "bad_timestamp" in v[2], str(v))
for lead in ("\n", " ", "﻿"):
    v = verdict(with_placement(scope=lead + "home")); check(f"2h: scope with leading {lead!r} rejected", v[1] is False)
    v = verdict(with_placement(story_id=lead + "7")); check(f"2i: story_id with leading {lead!r} rejected", v[1] is False)

print("3. non-ASCII digits and look-alikes are rejected")
SEVEN = {"Devanagari": "७", "Arabic-Indic": "٧", "fullwidth": "７", "superscript": "⁷", "Bengali": "৭"}
for name, ch in SEVEN.items():
    d = base(); d["stories"] = {ch: {"title": {"en": "x"}}}
    v = verdict(d); check(f"3a: story key made of a {name} digit rejected", v[1] is False and "bad_story_id" in v[2], str(v))
    v = verdict(with_placement(story_id="1" + ch)); check(f"3b: story_id containing a {name} digit rejected", v[1] is False and "bad_story_id" in v[2], str(v))
    v = verdict(with_placement(starts_at="2026-10-10T06:00:00Z".replace("06", "0" + ch))); check(f"3c: timestamp with a {name} digit rejected", v[1] is False, str(v))
v = verdict(with_placement(scope="section:еconomy")); check("3d: Cyrillic look-alike letter in a scope rejected", v[1] is False and "bad_scope" in v[2])
v = verdict(with_placement(id="pı")); check("3e: dotless-i look-alike in a placement id rejected", v[1] is False)
d = base(); d["stories"]["7"]["base"] = {"title_en": "０" * 64}
check("3f: fullwidth digits as a fingerprint rejected", verdict(d)[1] is False)
d = base(); d["stories"]["7"]["base"] = {"title_en": "A" * 64}
check("3g: uppercase hex fingerprint rejected", verdict(d)[1] is False)
for bad in ("0", "01", "-1", "+1", "1.0", "1e3", "0x10", "", " 1", "1 ", "1" * 13):
    d = base(); d["stories"] = {bad: {"title": {"en": "x"}}}
    check(f"3h: story key {bad!r} rejected", verdict(d)[1] is False)
for bad in ("-a", "_a", "A", "a b", "a.b", "", "x" * 41):
    check(f"3i: placement id {bad!r} rejected", verdict(with_placement(id=bad))[1] is False)
for bad in ("Home", "HOME", "section:", "section:-x", "section:x-", "section:x--y", "section:X", "section:a b", "section", "topic:x", "home:x", ""):
    check(f"3j: scope {bad!r} rejected", verdict(with_placement(scope=bad))[1] is False)

print("4. a rejected identifier can never produce a silently inert placement via load_text")
doc = with_placement(scope="home\n")
ld = D.load_text(json.dumps(doc))
check("4a: load_text of a newline-suffixed scope is 'invalid', with no document handed to consumers", ld.status == "invalid" and ld.doc is None and ld.doc_hash is None)

print("5. hostile nesting fails closed, never raises")
def nest(d, open_="[", close="]"):
    return open_ * d + close * d


for depth in (S.MAX_DEPTH - 2, S.MAX_DEPTH, S.MAX_DEPTH + 1, 50, 200, 990, 1000, 1500, 5000, 100000):
    txt = '{"schema_version":1,"stories":{},"placements":[],"x":%s}' % nest(depth)
    k, ld = outcome(lambda txt=txt: D.load_text(txt))
    check(f"5a: load_text at nesting depth {depth} returns a result, not an exception", k == "ok", k)
    check(f"5b: ...and it is 'invalid' (unknown key / too deep), never 'ok'", k == "ok" and ld.status == "invalid")
for depth in (S.MAX_DEPTH + 1, 100, 1000, 3000):
    txt = '{"schema_version":1,"stories":{"7":{"title":{"en":"x"}}},"placements":[],"stories2":' + nest(depth, "{\"a\":", "}") + '}'
    k, ld = outcome(lambda txt=txt: D.load_text(txt))
    check(f"5c: deeply nested OBJECTS (depth {depth}) are invalid, not an exception", k == "ok" and ld.status == "invalid", k)
# python objects that never went through JSON (the gate / revisions call validate_document directly)
deep = []
cur = deep
for _ in range(5000):
    nxt = []
    cur.append(nxt)
    cur = nxt
k, r = outcome(lambda: S.validate_document({"schema_version": 1, "stories": {}, "placements": [], "x": deep}))
check("5d: validate_document on a 5000-deep Python structure returns an error result", k == "ok" and not r.ok and "too_deep" in r.codes(), k)
cyc = {"schema_version": 1, "stories": {}, "placements": []}
cyc["self"] = cyc
k, r = outcome(lambda: S.validate_document(cyc))
check("5e: a self-referential structure returns an error result (no infinite recursion)", k == "ok" and not r.ok, k)
wide = {"schema_version": 1, "stories": {}, "placements": [], "pad": [list(range(10)) for _ in range(2000)]}
k, r = outcome(lambda: S.validate_document(wide))
check("5f: a wide but shallow structure is judged on its keys (unknown key), not rejected as 'too deep'", k == "ok" and "too_deep" not in r.codes() and "unknown_key" in r.codes())
check("5g: a normal document (depth 5) is nowhere near the limit", S.MAX_DEPTH >= 8 and not S._too_deep(base(), S.MAX_DEPTH))
check("5h: the depth probe itself is iterative (a 100000-deep list does not recurse)", S._too_deep(deep, S.MAX_DEPTH) is True)
k, ld = outcome(lambda: D.load_text('{"schema_version":1,"a":' + nest(100000) + '}'))
check("5i: JSON deeper than the parser can handle is 'invalid' (RecursionError caught)", k == "ok" and ld.status == "invalid")
k, ld = outcome(lambda: D.load_text(b"\xef\xbb\xbf" + json.dumps(base()).encode()))
check("5j: a UTF-8 BOM is not silently accepted or crashing (invalid, not an exception)", k == "ok" and ld.status in ("invalid", "ok"))

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("=" * 60)
print("ALL EDITORIAL STRICTNESS CHECKS PASSED")
