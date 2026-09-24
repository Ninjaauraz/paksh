"""
diagnose_sections.py - run section_rank.py's classification + ranking over the real
production corpus and print each section's top 20, for manual editorial inspection.
Read-only: never writes to the database, never touches _site.

Run:  py diagnose_sections.py
      py diagnose_sections.py --n 3000     # widen the candidate pool
      py diagnose_sections.py --section economy   # just one section
"""
import sys
from datetime import datetime, timezone

import database
import homepage_rank as hr
import section_rank as sr
from database import get_all_events, get_connection

CANDIDATE_POOL_N = 1500  # matches export_static.RECENT_FEED_N, same reasoning as
                          # diagnose_homepage.py: ranking only matters for stories
                          # recent enough to plausibly reach a home-feed section

REPORT_SECTIONS = ["economy", "finance_markets", "defence_security", "technology",
                    "india_world", "india"]


def _fmt_row(rank, r):
    e = r["event"]
    why = f"tier={r['tier']}" if r["tier_idx"] is not None else f"{r['tier']} (topic/region fallback)"
    return (f"{rank:>3}. #{e['id']:<6} score={r['score']:<8.4f} sen={r['seniority']:<5.3f} "
            f"india={r['india_relevance']:<4} breadth={r['breadth']:<3} "
            f"indep={r['independent_count']:<2} dev={r['dev_count']:<2} "
            f"fresh_h={r['freshness_age_h']:<6.1f} | {why:<32} | {e.get('title', '')[:64]}")


def _print_section(key, events, si_map, vel_map, now, n=20):
    label = sr.SECTIONS[key]["label"]
    ranked, lead = sr.select_section(events, si_map, vel_map, now, key, n)
    print(f"\n{'=' * 110}\n{label.upper()} - TOP {min(n, len(ranked))}  "
          f"({len(ranked)} selected)\n{'=' * 110}")
    if not ranked:
        print("  (fewer than 3 qualifying stories - section omitted)")
        return
    print(f"  LEAD: #{lead['event']['id']} {lead['event'].get('title', '')[:70]}  "
          f"(tier={lead['tier']}, score={lead['score']:.4f})")
    print()
    for i, r in enumerate(ranked, 1):
        print(_fmt_row(i, r))


def main():
    n = CANDIDATE_POOL_N
    if "--n" in sys.argv:
        n = int(sys.argv[sys.argv.index("--n") + 1])
    only = None
    if "--section" in sys.argv:
        only = sys.argv[sys.argv.index("--section") + 1]

    print(f"Resolved database: {database.DB_PATH}")
    events = get_all_events()
    print(f"Total publishable events: {len(events)}")
    pool = events[:n]
    print(f"Ranking candidate pool: {len(pool)} (newest {n} by created_at)")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conn = get_connection()
    ids = [e["id"] for e in pool]
    si_map = hr.fetch_si_signals(conn, ids)
    vel_map = hr.fetch_velocity_signals(conn, ids, now)
    conn.close()

    sections = only.split(",") if only else REPORT_SECTIONS
    for key in sections:
        _print_section(key, pool, si_map, vel_map, now)

    print(f"\n{'=' * 110}\nALL SECTIONS (including ones not in the detailed report above)\n{'=' * 110}")
    all_sections = sr.select_all_sections(pool, si_map, vel_map, now)
    for key, spec in sr.SECTIONS.items():
        count = len(all_sections[key]["stories"]) if key in all_sections else 0
        status = f"{count} stories" if count else "OMITTED (<3 qualifying)"
        print(f"  {spec['label']:<24} {status}")


if __name__ == "__main__":
    main()
