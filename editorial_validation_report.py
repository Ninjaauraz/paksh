"""
editorial_validation_report.py - ONE-OFF, READ-ONLY editorial validation report.

Produces the full Top 20 for every section_rank.py section against the real
production database, with per-story explainability fields and per-section
composition stats, for manual editorial review BEFORE section_rank.py is wired
into export_static.py/the frontend.

Does not modify section_rank.py, homepage_rank.py, export_static.py, the
database, or _site in any way - pure read-only reporting on top of the
existing, unmodified implementation.

Run:  py editorial_validation_report.py
"""
from collections import Counter
from datetime import datetime, timezone

import database
import homepage_rank as hr
import section_rank as sr
from database import get_all_events, get_connection

CANDIDATE_POOL_N = 1500
REPORT_ORDER = ["economy", "finance_markets", "defence_security", "technology",
                 "india_world", "india", "politics_policy", "world", "society",
                 "health", "science_space", "sports", "culture_entertainment"]


def _finance_flavored(event):
    """Cross-check signal used only for the composition summary below (not part of
    section_rank.py's actual classification) - does this story's text match ANY
    Economy/Finance keyword tier, regardless of which section it actually landed in."""
    text = sr._text(event)
    return (sr._tier_match(text, sr.ECONOMY_TIERS)[0] is not None
            or sr._tier_match(text, sr.FINANCE_TIERS)[0] is not None)


def _group_key(r):
    return r["tier"] if r["tier"] != "general" else (r["event"].get("topic") or "general")


def _fmt_ts(ts):
    if ts is None:
        return None
    return ts.strftime("%Y-%m-%d %H:%M")


def _latest_update(r, si):
    dev_ts = si.get("latest_dev_time")
    if dev_ts is not None:
        return f"development tracked at {_fmt_ts(dev_ts)} UTC (age {r['freshness_age_h']:.1f}h)"
    return f"no tracked development since publish (fresh_age {r['freshness_age_h']:.1f}h)"


def _why(r):
    tier_desc = f"tier={r['tier']}" if r["tier_idx"] is not None else f"{r['tier']} (topic/region fallback, no specific keyword matched)"
    return (f"{tier_desc} [seniority {r['seniority']:.3f}]; {r['breadth']} outlet(s), "
            f"{r['independent_count']} independent-origin signal(s), {r['dev_count']} development(s); "
            f"fresh_age={r['freshness_age_h']:.1f}h; india_relevance={r['india_relevance']}; "
            f"= score {r['score']:.4f}")


def _print_story(rank, section_label, r, si):
    e = r["event"]
    print(f"  {rank:>2}. ID #{e['id']}")
    print(f"      Headline: {e.get('title', '')}")
    print(f"      Section: {section_label}")
    print(f"      Section score: {r['score']:.4f}")
    print(f"      India relevance: {r['india_relevance']}")
    tier_disp = r["tier"] if r["tier_idx"] is not None else f"{r['tier']} (fallback)"
    print(f"      Editorial seniority tier: {tier_disp} (seniority={r['seniority']:.3f})")
    print(f"      Publisher count (breadth): {r['breadth']}")
    print(f"      Independent-origin signal: {r['independent_count']}")
    print(f"      Recent development signal: {r['dev_count']}")
    print(f"      Latest meaningful update: {_latest_update(r, si)}")
    print(f"      Why it ranked here: {_why(r)}")
    print()


def _composition(key, ranked):
    n = len(ranked)
    india_n = sum(1 for r in ranked if r["event"].get("region") == "India")
    finance_n = sum(1 for r in ranked if _finance_flavored(r["event"]))
    groups = Counter(_group_key(r) for r in ranked)
    dominant = groups.most_common(1)[0] if groups else (None, 0)
    by_age = sorted(ranked, key=lambda r: r["freshness_age_h"])
    newest, oldest = by_age[0], by_age[-1]
    print(f"  --- Composition summary: {sr.SECTIONS[key]['label']} ---")
    print(f"    India stories: {india_n}/{n} ({100*india_n/n:.0f}%)")
    print(f"    Foreign stories: {n-india_n}/{n} ({100*(n-india_n)/n:.0f}%)")
    print(f"    Finance/market-flavored stories: {finance_n}/{n} ({100*finance_n/n:.0f}%)")
    print(f"    Dominant subtopic: {dominant[0]} ({dominant[1]}/{n})")
    print(f"    Distinct subtopics represented: {len(groups)}  -> {dict(groups)}")
    print(f"    Newest story in top 20: #{newest['event']['id']} "
          f"({newest['freshness_age_h']:.1f}h old) - {newest['event'].get('title','')[:70]}")
    print(f"    Oldest story in top 20: #{oldest['event']['id']} "
          f"({oldest['freshness_age_h']:.1f}h old) - {oldest['event'].get('title','')[:70]}")
    print()


def main():
    print(f"Resolved database: {database.DB_PATH}")
    events = get_all_events()
    print(f"Total publishable events: {len(events)}")
    pool = events[:CANDIDATE_POOL_N]
    print(f"Ranking candidate pool: {len(pool)} (newest {CANDIDATE_POOL_N} by created_at)")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conn = get_connection()
    ids = [e["id"] for e in pool]
    si_map = hr.fetch_si_signals(conn, ids)
    vel_map = hr.fetch_velocity_signals(conn, ids, now)
    conn.close()

    for key in REPORT_ORDER:
        label = sr.SECTIONS[key]["label"]
        ranked, lead = sr.select_section(pool, si_map, vel_map, now, key, n=20)
        print(f"\n{'=' * 115}\n{label.upper()} - TOP {len(ranked)}\n{'=' * 115}\n")
        if not ranked:
            print("  (fewer than 3 qualifying stories - section omitted in production)\n")
            continue
        for i, r in enumerate(ranked, 1):
            si = si_map.get(r["event"]["id"], {})
            _print_story(i, label, r, si)
        _composition(key, ranked)


if __name__ == "__main__":
    main()
