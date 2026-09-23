"""
diagnose_homepage.py - run homepage_rank.py's ranking over the real production
corpus and print the resulting sections, for manual inspection. Read-only: never
writes to the database, never touches _site.

Run:  py diagnose_homepage.py
      py diagnose_homepage.py --n 3000     # widen the candidate pool
"""
import sys
from datetime import datetime, timezone

import database
import homepage_rank as hr
from database import get_all_events, get_connection

CANDIDATE_POOL_N = 1500   # matches export_static.RECENT_FEED_N - ranking only matters
                          # for stories recent enough to plausibly reach the home feed


def rank_pool(events, now=None):
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    conn = get_connection()
    ids = [e["id"] for e in events]
    si = hr.fetch_si_signals(conn, ids)
    vel = hr.fetch_velocity_signals(conn, ids, now)
    conn.close()
    ranked = []
    for e in events:
        s = hr.homepage_rank_story(e, si[e["id"]], vel[e["id"]], now)
        s["momentum"] = hr.momentum_score(e, si[e["id"]], vel[e["id"]], now)
        s["event"] = e
        ranked.append(s)
    return ranked


def _fmt_row(rank, r):
    e = r["event"]
    return (f"{rank:>3}. #{e['id']:<6} score={r['score']:<8.3f} mom={r['momentum']:<7.3f} "
            f"breadth={r['breadth']:<3} indep={r['independent_count']:<2} "
            f"dev={r['dev_count']:<2} owners_recent={r['owners_recent']:<2} "
            f"india={r['india_relevance']:<4} fresh_age_h={r['freshness_age_h']:<6.1f} "
            f"region={e.get('region'):<5} topic={e.get('topic'):<14} "
            f"| {e.get('title', '')[:70]}")


def _print_section(name, rows, n=20):
    print(f"\n{'=' * 100}\n{name}  ({len(rows)} qualifying, showing top {min(n, len(rows))})\n{'=' * 100}")
    for i, r in enumerate(rows[:n], 1):
        print(_fmt_row(i, r))


def main():
    n = CANDIDATE_POOL_N
    if "--n" in sys.argv:
        n = int(sys.argv[sys.argv.index("--n") + 1])

    print(f"Resolved database: {database.DB_PATH}")
    events = get_all_events()
    print(f"Total publishable events: {len(events)}")
    pool = events[:n]
    print(f"Ranking candidate pool: {len(pool)} (newest {n} by created_at)")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ranked = rank_pool(pool, now)

    overall = sorted(ranked, key=lambda r: r["score"], reverse=True)
    _print_section("TOP 20 OVERALL", overall, 20)

    india = sorted([r for r in ranked if r["event"].get("region") == "India"],
                   key=lambda r: r["score"], reverse=True)
    _print_section("TOP INDIA (20)", india, 20)

    trending = sorted([r for r in ranked if r["momentum"] > 0],
                       key=lambda r: r["momentum"], reverse=True)
    _print_section("TOP TRENDING (20, by momentum)", trending, 20)

    changed = sorted([r for r in ranked if r["dev_count"] > 0
                       and r["freshness_age_h"] <= hr.WHAT_CHANGED_MAX_AGE_H],
                      key=lambda r: (r["dev_component"], r["score"]), reverse=True)
    _print_section("TOP WHAT-CHANGED (20)", changed, 20)

    worth = sorted([r for r in ranked if r["independent_count"] > 0
                     and r["freshness_age_h"] <= hr.WORTH_KNOWING_MAX_AGE_H],
                    key=lambda r: (r["independence_component"], r["breadth_component"]), reverse=True)
    _print_section("WORTH KNOWING (20)", worth, 20)

    sections = hr.select_homepage_sections(ranked)
    print(f"\n{'=' * 100}\nSECTIONS PRODUCED BY select_homepage_sections(): "
          f"{', '.join(f'{k} ({len(v)})' for k, v in sections.items())}\n{'=' * 100}")
    if "hero" in sections:
        _print_section("HERO", sections["hero"], HERO_N_DISPLAY)


HERO_N_DISPLAY = 3

if __name__ == "__main__":
    main()
