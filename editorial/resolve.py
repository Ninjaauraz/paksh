"""editorial/resolve.py - the interface between editorial configuration and generated stories.

INPUT  : generated story rows (plain dicts, as returned by database.get_all_events() /
         get_events_by_ids(), BEFORE export_static._lighten shortens summaries) and a
         LoadResult from editorial.document.
OUTPUT : NEW row objects carrying an extra `editorial` key, plus a report. Generated
         fields are never modified or removed: the exporter (Milestone 2) will choose
         the display value from `row["editorial"]["display"]` when present and fall
         back to the untouched generated field otherwise.

Guarantees (each is pinned by tests):
  * If there is no usable editorial document (absent / invalid / not ok), every row is
    returned UNCHANGED (same objects) and the report says why. The public site's
    behaviour is then exactly today's generated behaviour.
  * Input rows and the document are never mutated.
  * An override is kept even when the generated text underneath it changes; it is
    flagged `stale` so the editor is warned. It is never silently dropped or rewritten.
  * A story the document mentions but the current publishable set lacks is an ORPHAN:
    reported, skipped, never an error and never invented into a page.
  * Time is injected (`now`), never read from the clock here.
"""
from __future__ import annotations

import hashlib

from .schema import LANGS, TEXT_FIELDS, parse_utc

# Which generated field each fingerprintable override is compared against.
GENERATED_SOURCE = {
    "title_en": "title",
    "title_hi": "title_hi",
    "teaser_en": "summary",
    "teaser_hi": "summary_hi",
}


def _as_text(v):
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return " ".join(str(x) for x in v)
    return str(v)


def fingerprint(text):
    return hashlib.sha256(_as_text(text).encode("utf-8")).hexdigest()


def generated_fingerprint(row, base_key):
    return fingerprint(row.get(GENERATED_SOURCE[base_key]))


def make_base(row, entry):
    """Fingerprints an editor tool should store when saving `entry` against `row`."""
    out = {}
    for f in ("title", "teaser"):
        for lang in LANGS:
            key = "%s_%s" % (f, lang)
            if isinstance(entry.get(f), dict) and lang in entry[f]:
                out[key] = generated_fingerprint(row, key)
    return out


class ApplyResult:
    def __init__(self, rows, report):
        self.rows = rows
        self.report = report


def _fallback(rows, loaded):
    return ApplyResult(list(rows), {
        "status": "fallback" if loaded is not None and loaded.status == "invalid" else "none",
        "reason": getattr(loaded, "reason", "") or "no editorial document",
        "applied": [], "stale": [], "missing_translation": [],
    })


def apply_to_rows(rows, loaded):
    if loaded is None or not loaded.ok:
        return _fallback(rows, loaded)
    stories = loaded.doc.get("stories", {})
    out, applied, stale, half = [], [], [], []
    for row in rows:
        sid = str(row.get("id"))
        entry = stories.get(sid)
        if entry is None:
            out.append(row)
            continue
        if "editorial" in row:
            raise ValueError("generated row %s already has an 'editorial' key" % sid)
        display, stale_fields = {}, []
        for f in TEXT_FIELDS:
            if f in entry:
                display[f] = {lang: entry[f][lang] for lang in LANGS if lang in entry[f]}
                if len(display[f]) == 1:
                    half.append({"story_id": sid, "field": f,
                                 "missing": [l for l in LANGS if l not in display[f]][0]})
        base = entry.get("base", {})
        for key, want in base.items():
            f, lang = key.split("_")
            if f in entry and lang in entry[f] and generated_fingerprint(row, key) != want:
                stale_fields.append(key)
        new = dict(row)
        new["editorial"] = {"display": display, "stale": sorted(stale_fields),
                            "doc_hash": loaded.doc_hash}
        out.append(new)
        applied.append(sid)
        if stale_fields:
            stale.append({"story_id": sid, "fields": sorted(stale_fields)})
    return ApplyResult(out, {"status": "applied", "reason": "", "applied": applied,
                             "stale": stale, "missing_translation": half})


def evaluate_placements(rows, loaded, now, known_scopes=None):
    """Which placements are in force at `now`, and which were skipped and why.

    Expiry is automatic and total: a placement outside [starts_at, ends_at) contributes
    nothing, so the automated order resumes with no cleanup step."""
    empty = {"status": "none", "scopes": {}, "skipped": []}
    if loaded is None or not loaded.ok:
        empty["status"] = "fallback" if loaded is not None and loaded.status == "invalid" else "none"
        return empty
    present = {str(r.get("id")) for r in rows}
    scopes, skipped = {}, []
    for p in loaded.doc.get("placements", []):
        info = {"placement_id": p["id"], "story_id": p["story_id"], "scope": p["scope"]}
        if known_scopes is not None and p["scope"] not in known_scopes:
            skipped.append(dict(info, reason="unknown_scope"))
            continue
        if "starts_at" in p and now < parse_utc(p["starts_at"]):
            skipped.append(dict(info, reason="not_started"))
            continue
        if "ends_at" in p and now >= parse_utc(p["ends_at"]):
            skipped.append(dict(info, reason="expired"))
            continue
        if p["story_id"] not in present:
            skipped.append(dict(info, reason="orphan"))
            continue
        sc = scopes.setdefault(p["scope"], {"pinned": [], "featured": [], "hidden": []})
        if p["action"] == "hide":
            sc["hidden"].append(p["story_id"])
        elif p["action"] == "pin":
            sc["pinned"].append({"story_id": p["story_id"], "position": p.get("position")})
        else:
            sc["featured"].append({"story_id": p["story_id"], "position": p.get("position")})
    return {"status": "applied", "scopes": scopes, "skipped": skipped}


def apply_placements_to_order(ordered, evaluation, scope):
    """Apply hides and pins to an AUTOMATED ordering of ids for one scope.

    Pure and conservative: it only removes hidden ids and moves ids that are already in
    the automated candidate list. A pin for an id that is not eligible in this scope is
    skipped (reported), never injected - no story is invented into a module."""
    sc = evaluation.get("scopes", {}).get(scope)
    if not sc:
        return list(ordered), []
    notes = []
    hidden = set(sc["hidden"])
    by_id = {str(x): x for x in ordered}
    pins = []
    for n, p in enumerate(sc["pinned"]):
        sid = p["story_id"]
        if sid in hidden:
            notes.append({"story_id": sid, "reason": "hidden_wins"})
        elif sid not in by_id:
            notes.append({"story_id": sid, "reason": "not_eligible"})
        elif all(sid != q[2] for q in pins):
            pins.append([p["position"], n, sid])
    pinned_ids = {q[2] for q in pins}
    result = [x for x in ordered if str(x) not in hidden and str(x) not in pinned_ids]
    # positionless pins go to the top in document order; positioned pins land on their slot
    top = 0
    for q in sorted((q for q in pins if q[0] is None), key=lambda q: q[1]):
        top += 1
        q[0] = top
    for pos, _, sid in sorted(pins, key=lambda q: (q[0], q[1])):
        result.insert(min(max(pos, 1) - 1, len(result)), by_id[sid])
    return result, notes


def audit_references(loaded, rows, existing_ids=None, now=None):
    """Findings the editor must see. `existing_ids` (optional) is every event id that still
    exists in the database, which lets us tell 'unpublished/ineligible' from 'deleted or
    merged'. Nothing here is fatal: orphans are expected as the corpus churns."""
    if loaded is None or not loaded.ok:
        return []
    present = {str(r.get("id")) for r in rows}
    out = []

    def why(sid):
        if existing_ids is None:
            return "not_in_current_set"
        return "unpublished_or_ineligible" if sid in existing_ids else "deleted_or_merged"

    for sid in sorted(loaded.doc.get("stories", {}), key=int):
        if sid not in present:
            out.append({"kind": "orphan_story", "story_id": sid, "reason": why(sid), "severity": "warning"})
    for p in loaded.doc.get("placements", []):
        if p["story_id"] not in present:
            out.append({"kind": "orphan_placement", "story_id": p["story_id"],
                        "placement_id": p["id"], "reason": why(p["story_id"]), "severity": "warning"})
        if now is not None and "ends_at" in p and now >= parse_utc(p["ends_at"]):
            out.append({"kind": "expired_placement", "story_id": p["story_id"],
                        "placement_id": p["id"], "severity": "info"})
    applied = apply_to_rows(rows, loaded).report
    for s in applied["stale"]:
        out.append({"kind": "stale_override", "story_id": s["story_id"], "fields": s["fields"],
                    "severity": "warning"})
    for h in applied["missing_translation"]:
        out.append({"kind": "missing_translation", "story_id": h["story_id"], "field": h["field"],
                    "missing": h["missing"], "severity": "info"})
    return out
