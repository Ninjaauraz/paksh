"""
test_editorial_resolve.py - Milestone 1: how editorial configuration meets generated stories.
Proves: absent/invalid config changes nothing; generated fields are never modified;
overrides survive a fresh generated export; stale/orphan reporting; independent EN/HI;
placement expiry and ordering; the library; and that the editorial package is isolated
from the pipeline (no pipeline imports, no sqlite).

Uses synthetic rows with the real field names, plus - if present - a READ-ONLY sample of the
committed _site/data/events.json to confirm the real row shape works. Never touches a
database, never writes outside a temp directory.

Run:  py test_editorial_resolve.py
"""
import ast
import copy
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from editorial import document as D
from editorial import resolve as R
from editorial import library as L
from editorial import cli as CLI
from editorial.schema import parse_utc

FAILURES = []
ROOT = Path(__file__).parent


def check(label, cond, detail=""):
    print(f"  {label} ... {'OK' if cond else 'FAIL'}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILURES.append(label)


def row(i, **kw):
    r = {"id": i, "title": f"Generated title {i}", "title_hi": f"जनित शीर्षक {i}",
         "summary": f"Generated summary {i}.", "summary_hi": f"जनित सारांश {i}।",
         "summary_points": [f"point {i}"], "topic": "Politics", "region": "India",
         "lean_counts": {"left": 2, "center": 3, "right": 1}, "dominant": "center",
         "blindspot": None, "international": 0, "source_count": 6, "image_url": "",
         "created_at": f"2026-10-0{(i % 9) + 1}T06:00:00", "content_complete": True,
         "evidence_status": "OK", "summary_method": "llm"}
    r.update(kw)
    return r


ROWS = [row(i) for i in range(1, 9)]
NOW = parse_utc("2026-10-10T12:00:00Z")


def loaded(doc):
    return D.load_text(json.dumps(doc, ensure_ascii=False))


def doc_with(stories=None, placements=None):
    return {"schema_version": 1, "stories": stories or {}, "placements": placements or []}


print("1. absent / invalid configuration changes NOTHING")
before = copy.deepcopy(ROWS)
r = R.apply_to_rows(ROWS, D.load_text(None))
check("1a: absent -> every row is the SAME object, report says none", all(a is b for a, b in zip(r.rows, ROWS)) and r.report["status"] == "none")
r = R.apply_to_rows(ROWS, D.load_text("{broken"))
check("1b: malformed -> rows unchanged, report says fallback", all(a is b for a, b in zip(r.rows, ROWS)) and r.report["status"] == "fallback")
r = R.apply_to_rows(ROWS, D.load_text('{"schema_version":1,"stories":{"1":{"lean_counts":{}}}}'))
check("1c: a document that tries to edit protected data -> fallback, rows unchanged", r.report["status"] == "fallback" and ROWS == before)
r = R.apply_to_rows(ROWS, None)
check("1d: no LoadResult at all -> unchanged", r.rows == ROWS)
ev = R.evaluate_placements(ROWS, D.load_text("{broken"), NOW)
check("1e: invalid document yields no placements", ev["scopes"] == {} and ev["status"] == "fallback")
check("1f: the rows list returned is a copy (caller can't corrupt the original list)", R.apply_to_rows(ROWS, None).rows is not ROWS)
check("1g: library on an absent document shows every story as generated",
      all(s["status"] == ["generated"] for s in L.search_stories(ROWS, D.load_text(None), NOW)))

print("2. generated content is never modified")
entry = {"title": {"en": "Editor headline"}, "teaser": {"en": "Editor teaser", "hi": "संपादक सार"}}
entry["base"] = R.make_base(ROWS[2], entry)
doc = doc_with({"3": entry})
before = copy.deepcopy(ROWS)
res = R.apply_to_rows(ROWS, loaded(doc))
check("2a: input rows are not mutated", ROWS == before)
check("2b: only story 3 gained an 'editorial' key", [("editorial" in x) for x in res.rows] == [i == 2 for i in range(8)])
new3 = res.rows[2]
check("2c: every generated field of story 3 is byte-identical", {k: v for k, v in new3.items() if k != "editorial"} == before[2])
check("2d: untouched stories are the same objects", all(res.rows[i] is ROWS[i] for i in range(8) if i != 2))
check("2e: display text carries the override", new3["editorial"]["display"]["title"] == {"en": "Editor headline"})
check("2f: Hindi headline is NOT derived from the English override", "hi" not in new3["editorial"]["display"]["title"])
check("2g: teaser languages are independent", new3["editorial"]["display"]["teaser"] == {"en": "Editor teaser", "hi": "संपादक सार"})
check("2h: protected analytical fields untouched (lean_counts/dominant/summary_points)",
      new3["lean_counts"] == before[2]["lean_counts"] and new3["dominant"] == "center" and new3["summary_points"] == before[2]["summary_points"])
check("2i: the document's own object is not mutated", doc == doc_with({"3": entry}))
check("2j: report lists the applied story and the half-translated title",
      res.report["applied"] == ["3"] and res.report["missing_translation"] == [{"story_id": "3", "field": "title", "missing": "hi"}])
bad = copy.deepcopy(ROWS); bad[0]["editorial"] = {}
try:
    R.apply_to_rows(bad, loaded(doc_with({"1": {"title": {"en": "x"}}})))
    check("2k: a generated row that already has 'editorial' is refused", False)
except ValueError:
    check("2k: a generated row that already has 'editorial' is refused", True)

print("3. overrides survive a fresh generated export; stale is flagged, not dropped")
fresh = [copy.deepcopy(x) for x in ROWS]                       # a re-export: same stories
for x in fresh:
    x["created_at"] = "2026-10-11T00:00:00"                   # unrelated churn
res = R.apply_to_rows(fresh, loaded(doc))
check("3a: override persists across a re-export with unrelated changes", res.rows[2]["editorial"]["display"]["title"]["en"] == "Editor headline" and res.rows[2]["editorial"]["stale"] == [])
fresh[2]["title"] = "Regenerated by the pipeline"
fresh[2]["summary_hi"] = "नया जनित सारांश"
res = R.apply_to_rows(fresh, loaded(doc))
e3 = res.rows[2]["editorial"]
check("3b: generated title changed -> override KEPT and flagged stale", e3["display"]["title"]["en"] == "Editor headline" and "title_en" in e3["stale"])
check("3c: Hindi teaser override is stale because summary_hi changed", "teaser_hi" in e3["stale"])
check("3d: English teaser (generated text unchanged) is not stale", "teaser_en" not in e3["stale"])
check("3e: the new generated title is still present untouched", res.rows[2]["title"] == "Regenerated by the pipeline")
check("3f: report flags the stale override", res.report["stale"] and res.report["stale"][0]["story_id"] == "3")
check("3g: a list-valued generated summary is fingerprinted consistently",
      R.fingerprint(["a", "b"]) == R.fingerprint("a b"))
gone = [x for x in ROWS if x["id"] != 3]
audit = R.audit_references(loaded(doc), gone, existing_ids={"3"}, now=NOW)
check("3h: story no longer publishable -> orphan 'unpublished_or_ineligible', no error",
      [(a["kind"], a["reason"]) for a in audit] == [("orphan_story", "unpublished_or_ineligible")])
audit = R.audit_references(loaded(doc), gone, existing_ids=set(), now=NOW)
check("3i: story deleted or merged -> orphan 'deleted_or_merged'", audit[0]["reason"] == "deleted_or_merged")
audit = R.audit_references(loaded(doc), gone, now=NOW)
check("3j: without a known-id set the reason is honestly 'not_in_current_set'", audit[0]["reason"] == "not_in_current_set")
res = R.apply_to_rows(gone, loaded(doc))
check("3k: an orphan is skipped (no page invented, no crash)", res.report["applied"] == [] and len(res.rows) == 7)

print("4. placements: expiry, ordering, no inventing")
P = lambda i, **kw: dict({"id": i, "scope": "home", "story_id": "1", "action": "pin"}, **kw)
auto = [1, 2, 3, 4, 5, 6]
def order(placements, ids=auto, scope="home", now=NOW):
    ev = R.evaluate_placements(ROWS, loaded(doc_with(placements=placements)), now)
    return R.apply_placements_to_order(ids, ev, scope)
check("4a: no placements -> automated order unchanged", order([])[0] == auto)
check("4b: hide removes the story from that scope only", order([P("h", story_id="2", action="hide")])[0] == [1, 3, 4, 5, 6])
check("4c: hide does not touch other scopes", order([P("h", story_id="2", action="hide")], scope="section:economy")[0] == auto)
check("4d: pin at position 1", order([P("p", story_id="4", position=1)])[0] == [4, 1, 2, 3, 5, 6])
check("4e: pin at position 3", order([P("p", story_id="6", position=3)])[0] == [1, 2, 6, 3, 4, 5])
check("4f: positionless pins go to the top in document order",
      order([P("a", story_id="5"), P("b", story_id="3")])[0] == [5, 3, 1, 2, 4, 6])
check("4g: two positioned pins land on their slots",
      order([P("a", story_id="6", position=1), P("b", story_id="5", position=3)])[0] == [6, 1, 5, 2, 3, 4])
check("4h: a position beyond the end clamps instead of failing", order([P("a", story_id="1", position=100)])[0] == [2, 3, 4, 5, 6, 1])
out, notes = order([P("a", story_id="8", position=1)])
check("4i: pin for a story NOT in the automated candidates is skipped, never injected", out == auto and notes[0]["reason"] == "not_eligible")
out, notes = order([P("a", story_id="99", position=1)])
check("4j: pin for a story that does not exist is an orphan skip", out == auto)
ev = R.evaluate_placements(ROWS, loaded(doc_with(placements=[P("a", story_id="99")])), NOW)
check("4k: ...and the evaluation reports it as orphan", ev["skipped"][0]["reason"] == "orphan")
exp = [P("a", story_id="4", position=1, starts_at="2026-10-10T06:00:00Z", ends_at="2026-10-10T12:00:00Z")]
check("4l: active one second before expiry", order(exp, now=parse_utc("2026-10-10T11:59:59Z"))[0][0] == 4)
check("4m: expired exactly at ends_at -> automated order resumes", order(exp, now=parse_utc("2026-10-10T12:00:00Z"))[0] == auto)
ev = R.evaluate_placements(ROWS, loaded(doc_with(placements=exp)), parse_utc("2026-10-10T13:00:00Z"))
check("4n: expiry is reported as 'expired'", ev["skipped"][0]["reason"] == "expired")
check("4o: not yet started contributes nothing", order(exp, now=parse_utc("2026-10-10T05:00:00Z"))[0] == auto)
check("4p: unknown scope can be refused when the caller knows the valid scopes",
      R.evaluate_placements(ROWS, loaded(doc_with(placements=[P("a", scope="section:nope")])), NOW,
                            known_scopes={"home"})["skipped"][0]["reason"] == "unknown_scope")
check("4q: hidden wins if a hide and a pin are somehow both in force",
      R.apply_placements_to_order([1, 2], {"scopes": {"home": {"hidden": ["1"], "featured": [],
                                  "pinned": [{"story_id": "1", "position": 1}]}}}, "home")[0] == [2])
audit = R.audit_references(loaded(doc_with(placements=exp)), ROWS, now=parse_utc("2026-10-10T13:00:00Z"))
check("4r: expired placements show up as info so editors can tidy", audit[0]["kind"] == "expired_placement")
a, b = order([P("a", story_id="4", position=1)])[0], order([P("a", story_id="4", position=1)])[0]
check("4s: evaluation is deterministic", a == b)

print("5. the read-only library")
d5 = doc_with({"3": entry, "5": {"title": {"en": "Quiet change", "hi": "शांत"}}},
              [P("a", story_id="2"), P("h", story_id="6", action="hide"),
               P("f", story_id="7", action="feature", scope="section:economy")])
lo = loaded(d5)
all_ = L.search_stories(ROWS, lo, NOW)
st = {s["id"]: s["status"] for s in all_}
check("5a: statuses: overridden / pinned / hidden / featured / generated",
      st["3"] == ["overridden"] and st["2"] == ["pinned"] and st["6"] == ["hidden"] and st["7"] == ["featured"] and st["1"] == ["generated"])
check("5b: search by exact id", [s["id"] for s in L.search_stories(ROWS, lo, NOW, story_id=4)] == ["4"])
check("5c: search by generated headline text", [s["id"] for s in L.search_stories(ROWS, lo, NOW, q="generated title 5")] == ["5"])
check("5d: search also finds the EDITORIAL headline", [s["id"] for s in L.search_stories(ROWS, lo, NOW, q="editor headline")] == ["3"])
check("5e: Hindi search works", [s["id"] for s in L.search_stories(ROWS, lo, NOW, q="जनित शीर्षक 2")] == ["2"])
check("5f: filter by status", sorted(s["id"] for s in L.search_stories(ROWS, lo, NOW, status="overridden")) == ["3", "5"])
check("5g: filter by topic (none match another topic)", L.search_stories(ROWS, lo, NOW, topic="Sports") == [])
check("5h: filter by date range", all(s["created_at"][:10] >= "2026-10-05" for s in L.search_stories(ROWS, lo, NOW, date_from="2026-10-05")))
check("5i: limit honoured", len(L.search_stories(ROWS, lo, NOW, limit=3)) == 3)
check("5j: results never expose raw analytical fields", all("lean_counts" not in s and "summary_points" not in s for s in all_))
fresh2 = [copy.deepcopy(x) for x in ROWS]; fresh2[2]["title"] = "changed"
check("5k: a stale override is labelled stale in the library",
      "stale" in {s["id"]: s["status"] for s in L.search_stories(fresh2, lo, NOW)}["3"])

print("6. real row shape (read-only sample of the committed export, if present)")
sample = ROOT / "_site" / "data" / "events.json"
if sample.exists():
    real = json.loads(sample.read_text(encoding="utf-8"))["events"][:40]
    target = real[5]
    e = {"title": {"en": "Sample editorial headline"}, "teaser": {"hi": "नमूना"}}
    e["base"] = R.make_base(target, e)
    out = R.apply_to_rows(real, loaded(doc_with({str(target["id"]): e})))
    keep = {k: v for k, v in out.rows[5].items() if k != "editorial"}
    check("6a: real committed row: generated fields identical after overlay", keep == target)
    check("6b: real row: not stale immediately after saving", out.rows[5]["editorial"]["stale"] == [])
    check("6c: real rows: all other rows are the same objects", all(out.rows[i] is real[i] for i in range(40) if i != 5))
    check("6d: real ids are plain integers that map onto story-id keys", all(str(r["id"]).isdigit() for r in real))
else:
    print("  (no committed _site/data/events.json here: shape check skipped)")

print("7. CLI is read-only and refuses databases")
for bad in ("paksh.db", "x/paksh.db", "backup.sqlite", "d.db-wal"):
    try:
        CLI._refuse_database(bad); check(f"7: refuses {bad}", False)
    except SystemExit:
        check(f"7: refuses {bad}", True)
with tempfile.TemporaryDirectory() as tmp:
    p, ev = os.path.join(tmp, "doc.json"), os.path.join(tmp, "events.json")
    Path(p).write_text(json.dumps(d5, ensure_ascii=False), encoding="utf-8")
    Path(ev).write_text(json.dumps({"events": ROWS}, ensure_ascii=False), encoding="utf-8")
    snap = {f: (os.path.getsize(os.path.join(tmp, f)), Path(tmp, f).read_bytes()) for f in os.listdir(tmp)}
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc1 = CLI.main(["validate", p]); rc2 = CLI.main(["audit", p, "--events", ev]); rc3 = CLI.main(["library", "--events", ev, "--doc", p])
    check("7e: validate/audit/library run and succeed", (rc1, rc2, rc3) == (0, 0, 0), buf.getvalue()[-200:])
    after = {f: (os.path.getsize(os.path.join(tmp, f)), Path(tmp, f).read_bytes()) for f in os.listdir(tmp)}
    check("7f: the CLI created, changed and deleted no files", snap == after)
    Path(p).write_text('{"schema_version":1,"stories":{"1":{"sources":[]}}}', encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        check("7g: validate exits 1 on a protected-field edit", CLI.main(["validate", p]) == 1)

print("8. isolation from the pipeline")
banned = {"database", "export_static", "analyze", "cluster", "ingest", "live", "refresh", "sqlite3",
          "safe_autopush", "runlocked", "subprocess", "socket", "urllib", "requests", "shutil", "os.system"}
violations = []
for f in sorted((ROOT / "editorial").glob("*.py")):
    tree = ast.parse(f.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module.split(".")[0]]
        violations += [f"{f.name}: imports {n}" for n in names if n in banned]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
            mode = ""
            if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                mode = str(node.args[1].value)
            if any(c in mode for c in "wax+"):
                violations.append(f"{f.name}: opens a file for writing")
check("8a: editorial/ imports no pipeline/db/network/process modules and never opens a file for writing", not violations, str(violations))
_std = getattr(sys, "stdlib_module_names", None)   # Python 3.10+; absent on 3.9
if _std is None:
    print("  8b: skipped (needs Python 3.10+ for sys.stdlib_module_names)")
else:
    _imported = set()
    for f in (ROOT / "editorial").glob("*.py"):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                _imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                _imported.add(node.module.split(".")[0])
    check("8b: editorial/ imports only the standard library", _imported <= set(_std) | {"__future__"},
          str(sorted(_imported - set(_std))))

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("=" * 60)
print("ALL EDITORIAL RESOLVE CHECKS PASSED")
