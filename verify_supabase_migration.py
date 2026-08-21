"""
verify_supabase_migration.py - Paksh 2.0 Phase 1: SQLite <-> Supabase integrity check.

Compares every migrated entity field-by-field against paksh.db (the source of
truth), using database.py's own functions for derived fields (dominant_lean,
blindspot, lean_counts) so the comparison can't drift from what production
already computes. Read-only against both sides. Prints a PASS/FAIL per field,
not just a row count - per the Phase 1 brief's explicit requirement.

Usage:  py verify_supabase_migration.py --ids 15944,15945,15946,15947,15948
        (Supabase side is pasted in below from the executed SELECT, since this
        environment has no direct Postgres connection - see the Phase 1 report
        for why. For a real deployment, replace SUPABASE_EVENTS with a live
        query via psycopg2/supabase-py.)
"""
import argparse
import json
import sys

import database

# Verbatim from the executed `SELECT ... FROM public.events WHERE id IN (...)`
SUPABASE_EVENTS = {
    15948: {"title": "Microdrama Emerges as Mainstream Entertainment Format in India, Report Finds",
            "topic": "Entertainment", "region": "India", "lean_left": 1, "lean_center": 1, "lean_right": 0,
            "international_count": 0, "unrated_count": 0, "total_sources": 2, "dominant_lean": "left",
            "dominant_pct": 50, "blindspot_side": None, "storyline_id": None,
            "created_at": "2026-08-18T10:30:17.896800", "sp_count": 4, "sphi_count": 4, "src_count": 2},
    15947: {"title": "Zeeba Appoints Chef Vikas Khanna as Global Brand Ambassador, Revamps Packaging",
            "topic": "Society", "region": "India", "lean_left": 1, "lean_center": 1, "lean_right": 0,
            "international_count": 0, "unrated_count": 0, "total_sources": 2, "dominant_lean": "left",
            "dominant_pct": 50, "blindspot_side": None, "storyline_id": None,
            "created_at": "2026-08-18T10:30:17.873244", "sp_count": 4, "sphi_count": 4, "src_count": 2},
    15946: {"title": "Vehere Appoints Middle East Distributor",
            "topic": "Society", "region": "World", "lean_left": 1, "lean_center": 1, "lean_right": 0,
            "international_count": 0, "unrated_count": 0, "total_sources": 2, "dominant_lean": "left",
            "dominant_pct": 50, "blindspot_side": None, "storyline_id": None,
            "created_at": "2026-08-18T10:30:17.848487", "sp_count": 4, "sphi_count": 4, "src_count": 2},
    15945: {"title": "Foreigners establish careers and homes in Taizhou",
            "topic": "Society", "region": "World", "lean_left": 1, "lean_center": 1, "lean_right": 0,
            "international_count": 0, "unrated_count": 0, "total_sources": 2, "dominant_lean": "left",
            "dominant_pct": 50, "blindspot_side": None, "storyline_id": None,
            "created_at": "2026-08-18T10:30:17.824862", "sp_count": 3, "sphi_count": 3, "src_count": 2},
    15944: {"title": "FDA Notices Issued Over Vimal Elaichi Advertisement",
            "topic": "Crime & Law", "region": "India", "lean_left": 0, "lean_center": 1, "lean_right": 1,
            "international_count": 0, "unrated_count": 0, "total_sources": 2, "dominant_lean": "center",
            "dominant_pct": 50, "blindspot_side": None, "storyline_id": "sl-14913",
            "created_at": "2026-08-18T10:30:17.802783", "sp_count": 4, "sphi_count": 4, "src_count": 2},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True)
    args = ap.parse_args()
    ids = [int(x) for x in args.ids.split(",")]

    database.init_db()
    passed = failed = 0
    for eid in ids:
        sb = SUPABASE_EVENTS.get(eid)
        if not sb:
            print(f"#{eid}  FAIL  not present in SUPABASE_EVENTS snapshot")
            failed += 1
            continue

        old = database.get_event(eid)
        if not old:
            print(f"#{eid}  FAIL  not found in SQLite")
            failed += 1
            continue

        lc = old["lean_counts"]
        dominant = old.get("dominant")
        blindspot = old.get("blindspot")
        checks = [
            ("title", old["title"], sb["title"]),
            ("topic", old.get("topic"), sb["topic"]),
            ("region", old.get("region"), sb["region"]),
            ("lean_left", lc.get("left", 0), sb["lean_left"]),
            ("lean_center", lc.get("center", 0), sb["lean_center"]),
            ("lean_right", lc.get("right", 0), sb["lean_right"]),
            ("international_count", old.get("coverage", {}).get("international", {}).get("count", 0), sb["international_count"]),
            ("unrated_count", old.get("coverage", {}).get("unrated", {}).get("count", 0), sb["unrated_count"]),
            ("total_sources", len(old.get("sources", [])), sb["total_sources"]),
            ("dominant_lean", dominant["side"] if dominant else None, sb["dominant_lean"]),
            ("dominant_pct", dominant["pct"] if dominant else None, sb["dominant_pct"]),
            ("blindspot_side", blindspot["side"] if blindspot else None, sb["blindspot_side"]),
            ("created_at", old["created_at"], sb["created_at"]),
            ("summary_points count", len(old.get("summary_points") or []), sb["sp_count"]),
            ("summary_points_hi count", len(old.get("summary_points_hi") or []), sb["sphi_count"]),
            ("sources count", len(old.get("sources") or []), sb["src_count"]),
        ]
        event_ok = True
        for field, want, got in checks:
            if want != got:
                print(f"#{eid}  FAIL  {field}: SQLite={want!r}  Supabase={got!r}")
                event_ok = False
        if event_ok:
            print(f"#{eid}  PASS  all {len(checks)} fields match")
            passed += 1
        else:
            failed += 1

    print(f"\n{passed} event(s) fully matched, {failed} had a discrepancy, out of {len(ids)} checked.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
