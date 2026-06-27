"""
audit.py - editorial review report for lean labels + framing fairness.

Generates a self-contained audit.html you can open in a browser before launch:

  1. LEAN ROSTER - every rated outlet grouped by lean, with its label,
     confidence, a CONTESTED flag where the lean is disputed, the rationale,
     when it was last reviewed, how many of its articles are in the DB, and a
     few recent sample headlines - so you can eyeball "is this label right?".
  2. UNRATED, FREQUENTLY SEEN - outlets covering a lot of stories that aren't
     rated yet (candidates to add to sources.py).
  3. FRAMING FAIRNESS - events that cover 2+ sides but only carry framing text
     for some of them, i.e. a lopsided comparison worth a manual look.

Read-only. Makes no model calls and writes nothing except audit.html.

    python audit.py                 # -> audit.html
    python audit.py --days 30       # only events from the last N days for framing
    python audit.py --samples 6     # sample headlines per outlet
"""
import argparse
import html as _html

import sources
import database

LEANS = [("left", "Lean Left"), ("center", "Centre"), ("right", "Lean Right")]


# ----------------------------- data gathering -----------------------------

def _article_index(limit=40000):
    """Recent articles -> per-source count + sample headlines."""
    conn = database.get_connection()
    rows = conn.execute(
        "SELECT source, title FROM articles ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    counts, samples = {}, {}
    for r in rows:
        s = r["source"] or "(unknown)"
        counts[s] = counts.get(s, 0) + 1
        if len(samples.setdefault(s, [])) < 8 and (r["title"] or "").strip():
            samples[s].append(r["title"].strip())
    return counts, samples


def gather_roster(samples_n):
    counts, samples = _article_index()
    rated_names = {s["name"] for s in sources.SOURCES}

    roster = {k: [] for k, _ in LEANS}
    international = []
    for s in sources.SOURCES:
        entry = {
            "name": s["name"],
            "label": s.get("label", s.get("lean", "")),
            "lean": s.get("lean", "unrated"),
            "confidence": s.get("confidence", ""),
            "contested": bool(s.get("contested")),
            "region": s.get("region", "India"),
            "last_reviewed": s.get("last_reviewed", ""),
            "rationale": (s.get("rationale") or "").strip(),
            "count": counts.get(s["name"], 0),
            "samples": samples.get(s["name"], [])[:samples_n],
        }
        if s["name"] in sources.INTERNATIONAL_SOURCES:
            international.append(entry)
        elif entry["lean"] in roster:
            roster[entry["lean"]].append(entry)
    for k in roster:
        roster[k].sort(key=lambda e: -e["count"])
    international.sort(key=lambda e: -e["count"])

    unrated = [{"name": n, "count": c, "samples": samples.get(n, [])[:samples_n]}
               for n, c in counts.items() if n not in rated_names]
    unrated.sort(key=lambda e: -e["count"])
    return roster, international, unrated[:40]


def gather_framing_flags(days):
    flags = []
    for eid in database.get_event_ids(days=days):
        e = database.get_event(eid)
        if not e or e.get("summary_method") != "llm":
            continue                                  # extractive events have no framing
        cov = e.get("coverage", {})
        fr = e.get("framing") or {}
        covered = [s for s, _ in LEANS if cov.get(s, {}).get("count", 0) > 0]
        framed = [s for s, _ in LEANS if (fr.get(s) or "").strip()]
        missing = [s for s in covered if s not in framed]
        if len(covered) >= 2 and missing:
            flags.append({
                "id": eid, "title": e.get("title", ""),
                "covered": covered, "framed": framed, "missing": missing,
            })
    return flags


# ------------------------------- rendering --------------------------------

_CSS = """
:root{--ink:#1B1A18;--bg:#EDEAE4;--card:#fff;--line:#DAD5CC;--mut:#6B655C;
--left:#2D5BD0;--center:#7A736A;--right:#C26A1B;--intl:#2F8F83;--warn:#B23B3B}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;line-height:1.5}
.wrap{max-width:1080px;margin:0 auto;padding:32px 20px 80px}
h1{font-size:26px;margin:0 0 4px}.sub{color:var(--mut);font-size:14px;margin-bottom:24px}
h2{font-size:18px;margin:34px 0 12px;padding-bottom:6px;border-bottom:2px solid var(--ink)}
.stat{display:inline-block;background:var(--card);border:1px solid var(--line);border-radius:8px;
padding:8px 14px;margin:0 8px 8px 0;font-size:13px}.stat b{font-size:18px;display:block}
.o{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--line);
border-radius:8px;padding:12px 14px;margin-bottom:10px}
.o.left{border-left-color:var(--left)}.o.center{border-left-color:var(--center)}
.o.right{border-left-color:var(--right)}.o.intl{border-left-color:var(--intl)}
.o h3{margin:0;font-size:15px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.tag{font-size:11px;font-weight:600;padding:2px 7px;border-radius:99px;border:1px solid var(--line)}
.tag.lbl{background:#EAF0FC;color:var(--left)}.tag.cbl{background:#F0EEEA;color:var(--center)}
.tag.rbl{background:#F8EDDD;color:var(--right)}.tag.ibl{background:#E1EFEC;color:var(--intl)}
.tag.con{background:#FBE9E9;color:var(--warn);border-color:#E7C3C3}
.tag.low{background:#FBF3E3;color:#9A6B12;border-color:#E8D6AC}
.meta{color:var(--mut);font-size:12px;margin:4px 0}
.rat{font-size:13px;margin:6px 0}.cnt{font-weight:600}
ul.s{margin:6px 0 0;padding-left:18px}ul.s li{font-size:12.5px;color:#46423B;margin:2px 0}
.flag{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--warn);
border-radius:8px;padding:10px 14px;margin-bottom:8px;font-size:13px}
.flag b{font-size:14px}.miss{color:var(--warn);font-weight:600}
.empty{color:var(--mut);font-style:italic;padding:8px 0}
"""

def _esc(t): return _html.escape(str(t or ""))

def _outlet_html(e, lean_cls):
    tagcls = {"left": "lbl", "center": "cbl", "right": "rbl"}.get(e["lean"], "ibl")
    badges = ['<span class="tag %s">%s</span>' % (tagcls, _esc(e["label"]))]
    if e.get("contested"):
        badges.append('<span class="tag con">contested</span>')
    if e.get("confidence") == "low":
        badges.append('<span class="tag low">low confidence</span>')
    samples = "".join("<li>%s</li>" % _esc(t) for t in e.get("samples", []))
    samples = ('<ul class="s">%s</ul>' % samples) if samples else ""
    meta = " · ".join(filter(None, [
        e.get("region", ""), ("reviewed " + e["last_reviewed"]) if e.get("last_reviewed") else ""]))
    rat = ('<div class="rat">%s</div>' % _esc(e["rationale"])) if e.get("rationale") else ""
    return ("""<div class="o %s"><h3>%s %s <span class="cnt" style="margin-left:auto;color:#6B655C;font-weight:600">%d articles</span></h3>
<div class="meta">%s</div>%s%s</div>""" % (
        lean_cls, _esc(e["name"]), "".join(badges), e.get("count", 0), _esc(meta), rat, samples))


def render_report(roster, international, unrated, flags, generated):
    n_rated = sum(len(roster[k]) for k, _ in LEANS)
    out = ['<!doctype html><meta charset="utf-8"><title>Paksh editorial audit</title>',
           "<style>%s</style><div class='wrap'>" % _CSS]
    out.append("<h1>Paksh editorial audit</h1>")
    out.append("<div class='sub'>Lean labels &amp; framing fairness &middot; generated %s</div>" % _esc(generated))
    # summary stats
    out.append("".join([
        "<span class='stat'><b>%d</b> rated outlets</span>" % n_rated,
        "<span class='stat'><b>%d</b> Left</span>" % len(roster["left"]),
        "<span class='stat'><b>%d</b> Centre</span>" % len(roster["center"]),
        "<span class='stat'><b>%d</b> Right</span>" % len(roster["right"]),
        "<span class='stat'><b>%d</b> international</span>" % len(international),
        "<span class='stat'><b>%d</b> contested labels</span>" %
        sum(1 for k, _ in LEANS for e in roster[k] if e["contested"]),
        "<span class='stat'><b>%d</b> framing flags</span>" % len(flags),
    ]))
    # roster
    for key, title in LEANS:
        out.append("<h2>%s &middot; %d outlets</h2>" % (title, len(roster[key])))
        if not roster[key]:
            out.append("<div class='empty'>none</div>")
        for e in roster[key]:
            out.append(_outlet_html(e, key))
    # international
    out.append("<h2>International tier (non-voting) &middot; %d</h2>" % len(international))
    for e in international:
        out.append(_outlet_html(e, "intl"))
    # unrated candidates
    out.append("<h2>Unrated, frequently seen &middot; top %d</h2>" % len(unrated))
    out.append("<div class='sub'>High-volume outlets not yet in sources.py — candidates to rate.</div>")
    if not unrated:
        out.append("<div class='empty'>none</div>")
    for e in unrated:
        samples = "".join("<li>%s</li>" % _esc(t) for t in e.get("samples", []))
        out.append("<div class='o'><h3>%s <span style='margin-left:auto;color:#6B655C'>%d articles</span></h3>%s</div>"
                   % (_esc(e["name"]), e["count"], ("<ul class='s'>%s</ul>" % samples) if samples else ""))
    # framing flags
    out.append("<h2>Framing fairness &middot; %d to review</h2>" % len(flags))
    out.append("<div class='sub'>Events covering 2+ sides but missing framing text on a covered side.</div>")
    if not flags:
        out.append("<div class='empty'>No lopsided framing found.</div>")
    for f in flags:
        out.append("<div class='flag'><b>#%s %s</b><br>covers: %s &nbsp;|&nbsp; framed: %s &nbsp;|&nbsp; <span class='miss'>missing framing: %s</span></div>"
                   % (f["id"], _esc(f["title"]), ", ".join(f["covered"]),
                      ", ".join(f["framed"]) or "—", ", ".join(f["missing"])))
    out.append("</div>")
    return "".join(out)


def main():
    import datetime
    ap = argparse.ArgumentParser(description="Editorial lean + framing audit -> audit.html")
    ap.add_argument("--days", type=int, default=None, help="window for framing flags")
    ap.add_argument("--samples", type=int, default=4, help="sample headlines per outlet")
    ap.add_argument("--out", default="audit.html")
    args = ap.parse_args()

    database.init_db()
    roster, international, unrated = gather_roster(args.samples)
    flags = gather_framing_flags(args.days)
    html_doc = render_report(roster, international, unrated, flags,
                             datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(html_doc)
    print("Wrote %s  (%d rated outlets, %d unrated candidates, %d framing flags)"
          % (args.out, sum(len(roster[k]) for k, _ in LEANS), len(unrated), len(flags)))


if __name__ == "__main__":
    main()