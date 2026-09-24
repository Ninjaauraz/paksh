"""
evidence_gate_migrate.py - backfill/apply the evidence-sufficiency gate
(analyze.py::compute_evidence_status) across the EXISTING corpus.

2026-09-24 story-quality campaign (event #23887/#23755): every event analysed
before this field existed has no `evidence_status` key at all, which
database._is_publishable() treats as publishable (the same grandfather rule
content_complete already uses - see that field's own docstring). This script
computes the real verdict for every event and, ONLY for the specific
NEEDS_REVIEW case (a repairable picker failure - real evidence exists among
the member articles but an old, unfixed _representative() picked a title-echo
instead), deterministically re-derives a real extractive summary from the
CURRENT (fixed) picker. It makes NO model/LLM calls, ever.

INSUFFICIENT_EVIDENCE events are NEVER modified or fabricated - only their
evidence_status is recorded, which hides them from the public set via
database._is_publishable(). They remain in the database unchanged and become
eligible again automatically whenever the event is next reanalysed with more
or better articles (a normal merge/reframe/backfill pass).

    python evidence_gate_migrate.py                  # DRY RUN: report what would change
    python evidence_gate_migrate.py --apply          # write the backfill + repairs
    python evidence_gate_migrate.py --days 30        # limit to recent events

BACK UP paksh.db before running with --apply.
"""
import argparse

import analyze
import database

# Preserve everything postprocess() would otherwise need us to re-derive, EXCEPT
# summary/summary_method, which come from the (possibly repaired) extractive raw
# output below rather than from the old event - the whole point of this script.
_PRESERVE = ("title", "summary_points", "title_hi", "summary_hi",
             "summary_points_hi", "framing", "framing_hi", "topic", "region")


def _article_dicts(rows):
    return [{"id": a["id"], "source": a.get("source"), "language": a.get("language") or "en",
              "title": a.get("title"), "url": a.get("url", ""), "image_url": a.get("image_url", ""),
              "summary": a.get("summary") or ""} for a in rows]


def main():
    ap = argparse.ArgumentParser(description="Backfill/apply the evidence-sufficiency gate.")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--days", type=int, default=None, help="limit to events from the last N days")
    ap.add_argument("--limit-print", type=int, default=30, help="max changed events to print")
    args = ap.parse_args()

    database.init_db()
    ids = database.get_event_ids(days=args.days)
    print(f"\n{len(ids)} event(s) to scan" + (f" (last {args.days} days)" if args.days else " (all)"))

    scanned = backfilled_publishable = repaired = insufficient = unchanged_verdict = 0
    repair_failed = 0
    shown = 0
    changes = []

    for eid in ids:
        old = database.get_event(eid)
        if not old:
            continue
        rows = database.get_event_articles(eid)
        if not rows:
            continue
        scanned += 1
        article_dicts = _article_dicts(rows)
        old_status = old.get("evidence_status")
        old_summary = old.get("summary", "")
        old_title = old.get("title", "")
        old_method = old.get("summary_method", "llm")

        status, reason = analyze.compute_evidence_status(old_summary, old_title, old_method, article_dicts)

        new_summary, new_summary_hi, new_summary_method = old_summary, old.get("summary_hi", ""), old_method
        final_status, final_reason = status, reason

        if status == analyze.EVIDENCE_NEEDS_REVIEW:
            # Deterministic repair attempt: re-run the FIXED extractive picker against
            # the SAME stored articles. No LLM call. This should always resolve NEEDS_REVIEW
            # to PUBLISHABLE by construction (NEEDS_REVIEW only fires when >=MIN_USABLE_CHARS
            # of real text already exists among the articles) - verified defensively below.
            fresh = analyze._extractive_raw(article_dicts)
            repaired_status, repaired_reason = analyze.compute_evidence_status(
                fresh["summary"], fresh["title"], "extractive", article_dicts)
            if repaired_status == analyze.EVIDENCE_PUBLISHABLE:
                new_summary, new_summary_hi = fresh["summary"], fresh["summary_hi"]
                new_summary_method = "extractive"
                final_status, final_reason = repaired_status, "repaired_" + repaired_reason
                repaired += 1
            else:
                # Should not happen (see docstring) - fail safe rather than publish a
                # still-broken summary or leave the event ambiguously "under review" forever.
                final_status, final_reason = analyze.EVIDENCE_INSUFFICIENT, "repair_attempt_failed"
                repair_failed += 1
        elif status == analyze.EVIDENCE_INSUFFICIENT:
            insufficient += 1
        else:
            if old_status != status:
                backfilled_publishable += 1
            else:
                unchanged_verdict += 1

        if final_status != old_status and shown < args.limit_print:
            shown += 1
            changes.append((eid, old_title[:60], old_status, final_status, final_reason))
            print(f"  #{eid} {old_title[:60]!r}")
            print(f"     evidence_status: {old_status!r} -> {final_status!r}  ({final_reason})")
            if new_summary != old_summary:
                print(f"     summary: {old_summary[:70]!r}")
                print(f"           -> {new_summary[:70]!r}")

        if args.apply:
            raw = {k: old.get(k) for k in _PRESERVE}
            raw["summary"] = new_summary
            raw["summary_hi"] = new_summary_hi
            raw["summary_method"] = new_summary_method
            new = analyze.postprocess(raw, article_dicts)
            database.update_event(eid, new, bump_created=False)

    print("\n" + "=" * 60)
    print(f"  scanned .......................... {scanned}")
    print(f"  backfilled as PUBLISHABLE (no change) {backfilled_publishable}")
    print(f"  already-correct, unchanged ....... {unchanged_verdict}")
    print(f"  repaired (NEEDS_REVIEW -> fixed) .. {repaired}")
    print(f"  repair attempt failed (fail-safe)   {repair_failed}")
    print(f"  INSUFFICIENT_EVIDENCE (hidden) .... {insufficient}")
    if args.apply:
        print("\nAPPLIED. Next: python export_static.py\n")
    else:
        print("\nDRY RUN - nothing written. Back up paksh.db, then re-run with --apply.\n")


if __name__ == "__main__":
    main()
