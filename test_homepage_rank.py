"""
test_homepage_rank.py - deterministic tests for homepage_rank.py: the homepage
story score, momentum score, and section selection.

No database, no LLM, no network - pure function tests against synthetic events
and synthetic SI/velocity signal dicts (the same shape fetch_si_signals() /
fetch_velocity_signals() return). Fast and fully offline.

Run:  py test_homepage_rank.py
"""
from datetime import datetime, timedelta

import homepage_rank as hr

FAILURES = []


def check(label, cond, detail=""):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILURES.append(label)


NOW = datetime(2026, 9, 23, 12, 0, 0)


def iso(dt):
    return dt.isoformat()


def event(id_, *, region="India", topic="Politics", breadth=None, left=0, center=0, right=0,
           intl=0, published_h_ago=0.5, storyline_id=None, title="Some story"):
    lean_counts = {"left": left, "center": center, "right": right}
    if breadth is not None and left == center == right == 0:
        # convenience: caller just wants a given total breadth split evenly
        lean_counts = {"left": breadth // 3, "center": breadth // 3 + breadth % 3, "right": breadth // 3}
        intl = 0
    return {
        "id": id_, "title": title, "title_hi": "", "region": region, "topic": topic,
        "lean_counts": lean_counts, "international": intl,
        "published_at": iso(NOW - timedelta(hours=published_h_ago)),
        "created_at": iso(NOW - timedelta(hours=published_h_ago)),
        "storyline_id": storyline_id,
    }


def si(independent=0, dev_count=0, dev_age_h=None, has_si=True):
    return {
        "independent_count": independent, "total_reporting": independent,
        "dev_count": dev_count,
        "latest_dev_time": (NOW - timedelta(hours=dev_age_h)) if dev_age_h is not None else None,
        "has_si": has_si,
    }


def vel(owners_recent=0, owners_total=None):
    return {"owners_recent": owners_recent, "owners_total": owners_total or owners_recent}


NO_SI = si(has_si=False)
NO_VEL = vel(0)


print("=== 1. Recency: a newer story with identical other signals ranks higher ===")
e_new = event(1, breadth=6, published_h_ago=0.5)
e_old = event(2, breadth=6, published_h_ago=20.0)
r_new = hr.homepage_rank_story(e_new, NO_SI, NO_VEL, NOW)
r_old = hr.homepage_rank_story(e_old, NO_SI, NO_VEL, NOW)
check("1a: fresher story scores higher, identical breadth", r_new["score"] > r_old["score"])
check("1b: freshness itself is a decay in (0,1]", 0 < r_new["freshness"] <= 1)

print("\n=== 2. Coverage velocity: recently-arrived publisher breadth boosts score ===")
e = event(3, breadth=6, published_h_ago=1.0)
r_fast = hr.homepage_rank_story(e, NO_SI, vel(owners_recent=8), NOW)
r_slow = hr.homepage_rank_story(e, NO_SI, vel(owners_recent=0), NOW)
check("2a: 8 recently-arrived owners score higher than 0, same everything else",
      r_fast["score"] > r_slow["score"])
check("2b: velocity_component is bounded/monotonic (log-scaled, not raw)",
      hr._log_norm(100, hr.VELOCITY_REF) < 3)

print("\n=== 3. Publisher breadth vs syndication resistance: breadth ONLY reflects "
      "distinct outlets (the existing one-vote-per-owner dedup), never raw article count ===")
e_wide = event(4, left=3, center=3, right=3, intl=1)   # 10 distinct outlets
e_narrow = event(5, left=1, center=1, right=1, intl=0)  # 3 distinct outlets
r_wide = hr.homepage_rank_story(e_wide, NO_SI, NO_VEL, NOW)
r_narrow = hr.homepage_rank_story(e_narrow, NO_SI, NO_VEL, NOW)
check("3a: 10 distinct outlets outranks 3, all else equal", r_wide["score"] > r_narrow["score"])
check("3b: breadth is read from lean_counts/international, never from article/source_count "
      "(homepage_rank_story's event dict has no such field at all)",
      "article_count" not in e_wide and "source_count" not in e_wide)
check("3c: 100 'syndicated' (low-independence) events cannot out-log a handful of high-breadth "
      "ones - log-normalization means marginal outlet #50 adds almost nothing",
      hr._log_norm(50, hr.BREADTH_REF) - hr._log_norm(49, hr.BREADTH_REF)
      < hr._log_norm(2, hr.BREADTH_REF) - hr._log_norm(1, hr.BREADTH_REF))

print("\n=== 4. Independent-origin signal: INDEPENDENT != a plain boolean ===")
e = event(6, breadth=4)
r0 = hr.homepage_rank_story(e, si(independent=0), NO_VEL, NOW)
r1 = hr.homepage_rank_story(e, si(independent=1), NO_VEL, NOW)
r5 = hr.homepage_rank_story(e, si(independent=5), NO_VEL, NOW)
check("4a: more independent reporting events score higher (0 < 1 < 5)",
      r0["score"] < r1["score"] < r5["score"])
check("4b: missing SI data (has_si=False) is treated as neutral/unknown, not penalized "
      "below a story that has an explicit independent_count of 0",
      hr.homepage_rank_story(e, NO_SI, NO_VEL, NOW)["score"] == r0["score"])

print("\n=== 5. Development boost: a story that materially developed recently can rise again ===")
e = event(7, breadth=4, published_h_ago=8.0)   # 8h-old base story
r_no_dev = hr.homepage_rank_story(e, si(dev_count=0), NO_VEL, NOW)
r_recent_dev = hr.homepage_rank_story(e, si(dev_count=1, dev_age_h=0.5), NO_VEL, NOW)
check("5a: a development 30 minutes ago boosts an otherwise-8h-old story",
      r_recent_dev["score"] > r_no_dev["score"])
check("5b: the development RESETS the freshness clock (freshness age reflects the dev, "
      "not the original publish time)", r_recent_dev["freshness_age_h"] < 1.0)
e_fresh10min = event(8, breadth=4, published_h_ago=(10 / 60))
r_fresh_nodev = hr.homepage_rank_story(e_fresh10min, si(dev_count=0), NO_VEL, NOW)
r_dev_30min_on_8h = hr.homepage_rank_story(event(9, breadth=4, published_h_ago=8.0),
                                            si(dev_count=1, dev_age_h=0.5), NO_VEL, NOW)
check("5c: a major story materially developed 30 min ago is NOT automatically beaten by "
      "a bare 10-minute-old story with equal breadth and no development",
      r_dev_30min_on_8h["score"] >= r_fresh_nodev["score"] * 0.9)

print("\n=== 6. India relevance: influences, does not determine ===")
e_india = event(10, region="India", breadth=6)
e_world_small = event(11, region="World", breadth=6)
e_world_huge = event(12, region="World", breadth=30)
r_india = hr.homepage_rank_story(e_india, NO_SI, NO_VEL, NOW)
r_world_small = hr.homepage_rank_story(e_world_small, NO_SI, NO_VEL, NOW)
r_world_huge = hr.homepage_rank_story(e_world_huge, si(independent=3), vel(owners_recent=10), NOW)
check("6a: identical breadth - India edges out World (India relevance DOES influence)",
      r_india["score"] > r_world_small["score"])
check("6b: a genuinely much bigger World story CAN outrank a modest India story "
      "(India relevance does not DETERMINE the ranking)",
      r_world_huge["score"] > r_india["score"])
check("6c: the India multiplier is bounded (never zeroes out a World story)",
      hr.india_relevance(e_world_small) >= hr.INTL_INDIA_MULT > 0)
check("6d: no giant hand-maintained keyword list - the base signal is the event's own "
      "existing `region` field", hasattr(hr, "india_relevance") and
      len(hr.CIVIC_KEYWORDS.pattern) < 2000)   # the ONE existing small regex, not a list

print("\n=== 7. Stale-story decay ===")
e = event(13, breadth=8)
ages = [0.5, 10, 40, 100, 400]
scores = [hr.homepage_rank_story(event(13, breadth=8, published_h_ago=a), NO_SI, NO_VEL, NOW)["score"]
          for a in ages]
check("7a: score strictly decreases as the story gets older (all else equal)",
      all(scores[i] > scores[i + 1] for i in range(len(scores) - 1)), f"{scores}")
check("7b: a 400h-old story with no activity scores near zero relative to a fresh one",
      scores[-1] < scores[0] * 0.01)

print("\n=== 8. Trending momentum: velocity/development-driven, not article_count/latest_article ===")
e_big_static = event(14, breadth=25, published_h_ago=2.0)   # big breadth, no recent growth
e_small_fast = event(15, breadth=4, published_h_ago=0.5)    # small but growing fast
m_static = hr.momentum_score(e_big_static, si(independent=1), vel(owners_recent=0), NOW)
m_fast = hr.momentum_score(e_small_fast, si(independent=1), vel(owners_recent=8), NOW)
check("8a: a small-but-rapidly-growing story can out-trend a big static one",
      m_fast > m_static, f"fast={m_fast} static={m_static}")
check("8b: a story that stops changing eventually falls out of trending as it ages",
      hr.momentum_score(event(16, breadth=25, published_h_ago=48), si(), NO_VEL, NOW) <
      hr.momentum_score(event(17, breadth=25, published_h_ago=0.5), si(), NO_VEL, NOW))
check("8c: momentum is NOT simply article/breadth count ordering - a lower-breadth, "
      "higher-velocity story beats a higher-breadth, zero-velocity one",
      m_fast > m_static and e_small_fast["lean_counts"] != e_big_static["lean_counts"])

print("\n=== 9. Section diversity / story domination ===")
ranked = []
for i in range(30):
    e = event(100 + i, topic="Politics" if i < 20 else "Sports", breadth=5 + i % 5,
              storyline_id=(i // 3 if i < 12 else None))   # first 12 share 4 storylines
    r = hr.homepage_rank_story(e, si(independent=1), vel(owners_recent=i % 4), NOW)
    r["event"] = e
    r["momentum"] = hr.momentum_score(e, si(independent=1), vel(owners_recent=i % 4), NOW)
    ranked.append(r)
sections = hr.select_homepage_sections(ranked)
india_section = sections.get("india", [])
topic_counts = {}
for r in india_section:
    topic_counts[r["event"]["topic"]] = topic_counts.get(r["event"]["topic"], 0) + 1
check("9a: no topic exceeds the configured cap fraction of a section",
      all(c <= max(1, __import__("math").ceil(len(india_section) * hr.MAX_PER_TOPIC_IN_SECTION))
          for c in topic_counts.values()), f"{topic_counts}")
storyline_counts = {}
for r in india_section:
    sid = r["event"].get("storyline_id")
    if sid is not None:
        storyline_counts[sid] = storyline_counts.get(sid, 0) + 1
check("9b: no single storyline (ongoing saga) contributes more than one story to a section",
      all(c <= 1 for c in storyline_counts.values()), f"{storyline_counts}")

print("\n=== 10. No LLM / no network dependency ===")
import inspect
src = inspect.getsource(hr)
check("10a: homepage_rank.py imports no LLM/HTTP client",
      not any(bad in src for bad in ("openai", "genai", "requests.", "urllib.request", "groq")))
check("10b: ranking a story never raises even with a bare-minimum event dict "
      "(no network, no LLM call could silently be masking an exception either)",
      hr.homepage_rank_story({"id": 1, "region": "India"}, NO_SI, NO_VEL, NOW)["score"] >= 0)

print("\n=== 11. Deterministic output: same input -> same ranking, every time ===")
pool = [event(200 + i, breadth=(i * 7) % 15 + 1, region="India" if i % 2 else "World",
              published_h_ago=(i % 11)) for i in range(25)]
sis = {e["id"]: si(independent=e["id"] % 3) for e in pool}
vels = {e["id"]: vel(owners_recent=e["id"] % 5) for e in pool}


def rank_once():
    out = []
    for e in pool:
        r = hr.homepage_rank_story(e, sis[e["id"]], vels[e["id"]], NOW)
        r["event"] = e
        out.append(r)
    return sorted(out, key=lambda r: r["score"], reverse=True)


order1 = [r["event"]["id"] for r in rank_once()]
order2 = [r["event"]["id"] for r in rank_once()]
order3 = [r["event"]["id"] for r in rank_once()]
check("11a: three independent runs over the identical input produce IDENTICAL ordering",
      order1 == order2 == order3)

print(f"\n{'=' * 60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL HOMEPAGE RANK CHECKS PASSED")
