"""
backfill_hindi.py - fill in MISSING Hindi on events that have English but no
Hindi translation (the summary engine occasionally returns English-only output).

For each such event it asks the LLM pool to TRANSLATE the existing English fields
into Hindi (Devanagari) - it never re-summarises or invents, so the neutral facts
and the bias bar are untouched. Only the *_hi fields are written; everything else
(created_at, coverage, English text) is preserved.

    py backfill_hindi.py                 # DRY RUN - just counts what's missing
    py backfill_hindi.py --apply         # translate + write (then run export_static.py)
    py backfill_hindi.py --apply --cap 20
    py backfill_hindi.py --apply --workers 4

Uses the provider pool (Groq/Gemini) directly, so it works regardless of
PAKSH_LLM_BACKEND. Keys come from ai_keys.env. Back up paksh.db before --apply.
"""

import json
import re
import sys

import database
from analyze import _call_json          # pool-aware JSON call + tolerant parse

DEV = re.compile(r'[ऀ-ॿ]')


def _has_en(s):
    return bool(isinstance(s, str) and s.strip())


def _has_hi(s):
    return bool(isinstance(s, str) and DEV.search(s))


def _pts_hi(v):
    return any(_has_hi(x) for x in (v or []) if isinstance(x, str))


def _needs_hi(data):
    """True if English exists but the Hindi counterpart is missing."""
    miss_title = _has_en(data.get("title")) and not _has_hi(data.get("title_hi"))
    miss_sum = _has_en(data.get("summary")) and not (
        _has_hi(data.get("summary_hi")) or _pts_hi(data.get("summary_points_hi")))
    return miss_title or miss_sum


def _prompt(data):
    payload = {
        "title": data.get("title", ""),
        "summary": data.get("summary", ""),
        "summary_points": data.get("summary_points") or [],
        "framing": data.get("framing") or {},
    }
    return (
        "You are a professional English->Hindi news translator. Translate the "
        "English fields below into natural, faithful HINDI (Devanagari script ONLY). "
        "Translate meaning, not word-for-word; do NOT add, drop or change any fact, "
        "number or name. Keep the SAME structure and the same number of bullets.\n\n"
        "Return ONLY a JSON object with EXACTLY these keys:\n"
        '{\n'
        '  "title_hi": "Hindi translation of title",\n'
        '  "summary_hi": "Hindi translation of summary",\n'
        '  "summary_points_hi": ["Hindi translation of each point, same order"],\n'
        '  "framing_hi": {"left": ["..."], "center": ["..."], "right": ["..."]}\n'
        '}\n'
        "For framing_hi, translate each side's bullets in order; use [] for any side "
        "that is [] in the English framing. Every value MUST be in Hindi/Devanagari.\n\n"
        "ENGLISH:\n" + json.dumps(payload, ensure_ascii=False)
    )


def _translate(data):
    """Return {title_hi, summary_hi, summary_points_hi, framing_hi} or None."""
    raw = _call_json(_prompt(data), backend="pool")
    if not isinstance(raw, dict):
        return None
    out = {}
    if _has_hi(raw.get("title_hi")):
        out["title_hi"] = raw["title_hi"].strip()
    if _has_hi(raw.get("summary_hi")):
        out["summary_hi"] = raw["summary_hi"].strip()
    pts = [p.strip() for p in (raw.get("summary_points_hi") or [])
           if isinstance(p, str) and _has_hi(p)]
    if pts:
        out["summary_points_hi"] = pts
    fr = raw.get("framing_hi")
    if isinstance(fr, dict):
        clean = {}
        for side in ("left", "center", "right"):
            vals = fr.get(side) or []
            if isinstance(vals, str):
                vals = [vals]
            clean[side] = [v.strip() for v in vals if isinstance(v, str) and _has_hi(v)]
        out["framing_hi"] = clean
    # only useful if we at least got a title or summary in Hindi
    return out if ("title_hi" in out or "summary_hi" in out) else None


def main():
    apply = "--apply" in sys.argv
    cap = None
    workers = 3
    if "--cap" in sys.argv:
        cap = int(sys.argv[sys.argv.index("--cap") + 1])
    if "--workers" in sys.argv:
        workers = max(1, int(sys.argv[sys.argv.index("--workers") + 1]))

    database.init_db()
    conn = database.get_connection()
    rows = conn.execute("SELECT id, analysis_json FROM events").fetchall()
    todo = []
    for r in rows:
        try:
            data = json.loads(r["analysis_json"])
        except Exception:
            continue
        if _needs_hi(data):
            todo.append((r["id"], data))
    if cap:
        todo = todo[:cap]

    print("\n%d event(s) missing Hindi%s" % (len(todo), (" (cap %d)" % cap) if cap else ""))
    if not todo:
        print("Nothing to backfill.\n")
        return
    if not apply:
        print("DRY RUN - showing first 10; re-run with --apply to translate + write.\n")
        for eid, data in todo[:10]:
            print("  #%s  %s" % (eid, (data.get("title") or "")[:70]))
        print("\n(back up paksh.db first, then: py backfill_hindi.py --apply)\n")
        return

    def one(item):
        eid, data = item
        try:
            hi = _translate(data)
        except Exception as e:
            return (eid, None, str(e)[:80])
        return (eid, hi, None)

    done = fail = 0
    results = []
    if workers > 1 and len(todo) > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(one, todo))
    else:
        results = [one(t) for t in todo]

    data_by_id = {eid: data for eid, data in todo}
    for eid, hi, err in results:
        if not hi:
            fail += 1
            print("  #%s  translate failed (%s)" % (eid, err or "no Hindi returned"))
            continue
        data = data_by_id[eid]
        data.update(hi)                          # write only the *_hi fields
        conn.execute("UPDATE events SET analysis_json=? WHERE id=?",
                     (json.dumps(data, ensure_ascii=False), eid))
        done += 1
        print("  #%s  ok  %s" % (eid, hi.get("title_hi", "")[:56]))
    conn.commit()
    conn.close()

    print("\n" + "=" * 44)
    print("  translated + written: %d" % done)
    print("  failed (left as-is) : %d" % fail)
    print("\nNext: py export_static.py   (then push / let live.py --deploy publish)\n")


if __name__ == "__main__":
    main()
