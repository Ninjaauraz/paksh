"""editorial/library.py - the READ-ONLY story library (search / filter / status).

Operates on generated rows handed in by the caller (e.g. parsed from a data/events.json
file or, later, loaded from SQLite by the publishing machine). Returns small summaries;
never raw analysis, never a write.
"""
from __future__ import annotations

from .resolve import apply_to_rows, evaluate_placements

STATUSES = ("generated", "overridden", "stale", "pinned", "hidden", "featured")


def search_stories(rows, loaded, now, q=None, story_id=None, topic=None,
                   date_from=None, date_to=None, status=None, limit=200):
    applied = apply_to_rows(rows, loaded)
    by_id = {str(r.get("id")): r for r in applied.rows}
    ev = evaluate_placements(rows, loaded, now)
    flags = {}
    for sc in ev["scopes"].values():
        for p in sc["pinned"]:
            flags.setdefault(p["story_id"], set()).add("pinned")
        for p in sc["featured"]:
            flags.setdefault(p["story_id"], set()).add("featured")
        for sid in sc["hidden"]:
            flags.setdefault(sid, set()).add("hidden")
    needle = (q or "").strip().lower()
    out = []
    for r in rows:
        sid = str(r.get("id"))
        row = by_id[sid]
        edit = row.get("editorial")
        st = set(flags.get(sid, ()))
        if edit:
            st.add("overridden")
            if edit["stale"]:
                st.add("stale")
        if not st:
            st.add("generated")
        if story_id is not None and sid != str(story_id):
            continue
        if topic and (r.get("topic") or "") != topic:
            continue
        created = (r.get("created_at") or "")[:10]
        if date_from and created < date_from:
            continue
        if date_to and created > date_to:
            continue
        if status and status not in st:
            continue
        if needle:
            hay = " ".join(str(x) for x in (
                r.get("title"), r.get("title_hi"),
                *(v for f in (edit or {}).get("display", {}).values() for v in f.values()))
                if x).lower()
            if needle not in hay:
                continue
        out.append({"id": sid, "title": r.get("title"), "title_hi": r.get("title_hi"),
                    "topic": r.get("topic"), "region": r.get("region"),
                    "created_at": r.get("created_at"), "source_count": r.get("source_count"),
                    "status": sorted(st),
                    "override": (edit or {}).get("display")})
        if len(out) >= limit:
            break
    return out
