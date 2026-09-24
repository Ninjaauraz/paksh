"""
test_section_rank.py - deterministic tests for section_rank.py: per-section
classification, tier seniority, section score, lead selection, and diversity.

No database, no LLM, no network - pure function tests against synthetic events
and synthetic SI/velocity signal dicts (the same shape homepage_rank.py's
fetch_si_signals()/fetch_velocity_signals() return). Fast and fully offline.

Run:  py test_section_rank.py
"""
from datetime import datetime, timedelta

import homepage_rank as hr
import section_rank as sr

FAILURES = []


def check(label, cond, detail=""):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILURES.append(label)


NOW = datetime(2026, 9, 23, 12, 0, 0)


def iso(dt):
    return dt.isoformat()


def event(id_, *, region="India", topic="Politics", breadth=6, title="", title_hi="",
           published_h_ago=0.5, storyline_id=None):
    third = breadth // 3
    lean_counts = {"left": third, "center": breadth - 2 * third, "right": third}
    return {
        "id": id_, "title": title, "title_hi": title_hi, "region": region, "topic": topic,
        "lean_counts": lean_counts, "international": 0,
        "published_at": iso(NOW - timedelta(hours=published_h_ago)),
        "created_at": iso(NOW - timedelta(hours=published_h_ago)),
        "storyline_id": storyline_id,
    }


def si(independent=1, dev_count=0, dev_age_h=None, has_si=True):
    return {
        "independent_count": independent, "total_reporting": independent,
        "dev_count": dev_count,
        "latest_dev_time": (NOW - timedelta(hours=dev_age_h)) if dev_age_h is not None else None,
        "has_si": has_si,
    }


def vel(owners_recent=2):
    return {"owners_recent": owners_recent, "owners_total": owners_recent}


SI = si()
VEL = vel()


def rank_pool(events, section_key):
    si_map = {e["id"]: SI for e in events}
    vel_map = {e["id"]: VEL for e in events}
    return sr.select_section(events, si_map, vel_map, NOW, section_key, n=sr.SECTION_N)


print("=== 1. Economy does not become a stock-only feed ===")
econ_events = (
    [event(100 + i, topic="Economy", breadth=8,
           title=f"Sensex and Nifty shares rally as stock {i} surged") for i in range(10)]
    + [event(1, topic="Economy", breadth=4, title="India's GDP growth forecast raised to 7.2%")]
    + [event(2, topic="Economy", breadth=4, title="Union Budget 2026 unveils new fiscal policy")]
    + [event(3, topic="Economy", breadth=4, title="Inflation eases as CPI data shows relief")]
    + [event(300 + i, topic="Economy", breadth=4,
             title=f"Manufacturing sector output rises in state {i}") for i in range(4)]
    + [event(400 + i, topic="Economy", breadth=4,
             title=f"Company {i} reports acquisition and merger deal") for i in range(4)]
    + [event(500 + i, topic="Economy", breadth=4,
             title=f"India signs new trade deal on exports {i}") for i in range(4)]
)
ranked, lead = rank_pool(econ_events, "economy")
stock_frac = sum(1 for r in ranked if r["tier"] == "stocks") / len(ranked)
check("1a: stock-tier stories capped below the tier cap fraction",
      stock_frac <= sr.TIER_CAP_FRAC + 1e-9, f"stock_frac={stock_frac} of {len(ranked)}")
check("1b: a macro story (GDP) outranks at least one stock story despite lower breadth",
      any(r["event"]["id"] == 1 for r in ranked[:len(ranked) // 2]))

print("\n=== 2. Section lead: seniority can beat raw score (macro beats a bigger stock story) ===")
e_macro = event(10, topic="Economy", breadth=5, title="India's GDP growth forecast raised amid recovery")
e_stock = event(11, topic="Economy", breadth=6, title="Reliance shares gained 3 percent in early trade")
cls_macro = sr.classify_economy(e_macro)
cls_stock = sr.classify_economy(e_stock)
check("2setup: fixture titles hit the tiers this test means to compare "
      "(stock story gets only the weak topic-fallback in Economy post-fix - Economy has "
      "no 'stocks' tier at all any more, see section 14 below)",
      cls_macro[1] == "macro" and cls_stock[1] == "general",
      f"macro tier={cls_macro[1]!r}, stock tier={cls_stock[1]!r}")
r_macro = sr.section_rank_story(e_macro, SI, VEL, NOW, *cls_macro)
r_stock = sr.section_rank_story(e_stock, SI, VEL, NOW, *cls_stock)
check("2a: the macro story outranks the stock story despite lower breadth (6) and identical everything else",
      r_macro["score"] > r_stock["score"],
      f"macro={r_macro['score']} (breadth 5) vs stock={r_stock['score']} (breadth 6)")

print("\n=== 3. Finance & Markets can surface stock/market stories strongly ===")
MARKET_TIERS = {"indian_markets", "stocks", "ipo", "rbi_monetary"}
fin_events = (
    [event(200 + i, topic="Economy", breadth=6,
           title=f"Sensex jumps as stock {i} price gains") for i in range(3)]
    + [event(20, topic="Economy", breadth=3, title="A quiet day for financial regulation news")]
    + [event(21, topic="Economy", breadth=3, title="Insurance company reports routine quarterly filing")]
)
ranked, lead = rank_pool(fin_events, "finance_markets")
check("3a: a market/stock-tier story is present near the top of Finance & Markets",
      any(r["tier"] in MARKET_TIERS for r in ranked[:3]),
      f"top-3 tiers: {[r['tier'] for r in ranked[:3]]}")

print("\n=== 4. India-relevant stories receive a section boost, never a determination ===")
e_india = event(30, region="India", topic="Politics", breadth=6, title="Parliament passes new amendment bill")
e_world = event(31, region="World", topic="Politics", breadth=6, title="Parliament passes new amendment bill")
r_india = sr.section_rank_story(e_india, SI, VEL, NOW, 0, "legislation_policy",
                                 sr._seniority(0, len(sr.POLICY_TIERS)))
r_world = sr.section_rank_story(e_world, SI, VEL, NOW, 0, "legislation_policy",
                                 sr._seniority(0, len(sr.POLICY_TIERS)))
check("4a: identical story scores higher when India-region vs World-region",
      r_india["score"] > r_world["score"])
check("4b: India relevance influences, not zeroes, a World story (still > 0)",
      r_world["score"] > 0)
e_world_huge = event(32, region="World", topic="International", breadth=40,
                     title="Historic global summit reshapes world trade")
e_india_small = event(33, region="India", topic="Politics", breadth=2, title="Local council meeting held")
r_huge = sr.section_rank_story(e_world_huge, SI, VEL, NOW, None, "general", 1.0)
r_small = sr.section_rank_story(e_india_small, SI, VEL, NOW, None, "general", 1.0)
check("4c: India relevance does not DETERMINE rank - a much bigger World story can still outscore a small India one",
      r_huge["score"] > r_small["score"])

print("\n=== 5. India & World requires meaningful India relevance ===")
e_generic_foreign = event(40, region="World", topic="International", breadth=8,
                          title="South Korea and Japan sign new defence pact")
e_india_us = event(41, region="World", topic="International", breadth=4,
                   title="India-US trade deal talks resume in Washington")
check("5a: a purely foreign story with no India connection is NOT eligible for India & World",
      sr.classify_india_world(e_generic_foreign) is None)
check("5b: an explicit India-foreign bilateral story IS eligible",
      sr.classify_india_world(e_india_us) is not None)

print("\n=== 6. World can still surface major global stories ===")
world_events = [
    event(50, region="World", topic="International", breadth=30, title="Global climate summit reaches historic deal"),
    event(51, region="India", topic="Politics", breadth=3, title="Local roads ministry announces repairs"),
    event(52, region="World", topic="Sports", breadth=3, title="Minor tennis tournament result"),
    event(53, region="World", topic="Entertainment", breadth=3, title="Foreign film festival opens"),
]
ranked, lead = rank_pool(world_events, "world")
check("6a: a high-breadth World story leads the World section",
      lead["event"]["id"] == 50)

print("\n=== 7. Defence & Security excludes foreign militaries with no India tie ===")
e_korea = event(60, region="World", topic="International", breadth=4,
               title="Explosion injures officers near North Korean border",
               title_hi="उत्तर कोरियाई सीमा के पास विस्फोट में अधिकारी घायल")
e_pak_terror = event(61, region="World", topic="International", breadth=4,
                     title="India demands Pakistan act on cross-border terrorism")
e_india_army = event(62, region="India", topic="Politics", breadth=4,
                     title="Indian Army conducts winter exercise near LAC")
check("7a: a foreign (Korea) border story with no India/Pakistan/China tie is excluded",
      sr.classify_defence_security(e_korea) is None)
check("7b: an India-Pakistan story IS eligible even without the word 'India' region-tagged",
      sr.classify_defence_security(e_pak_terror) is not None)
check("7c: an explicit Indian Army/LAC story is eligible",
      sr.classify_defence_security(e_india_army) is not None)

print("\n=== 8. Generic Hindi words don't cause false positives (सीमा != border) ===")
e_deadline = event(70, region="India", topic="Politics", breadth=4,
                   title="Supreme Court declines to set deadline for speaker",
                   title_hi="सुप्रीम कोर्ट ने स्पीकर को समय सीमा तय करने से इनकार किया")
check("8a: 'समय सीमा' (deadline) does not false-positive into Defence & Security",
      sr.classify_defence_security(e_deadline) is None)
e_riverbank = event(71, region="India", topic="Society", breadth=4,
                    title="Volunteer cleans Yamuna river bank in Delhi")
check("8b: 'river bank' does not false-positive into Finance & Markets banking tier",
      sr.classify_finance_markets(e_riverbank) is None)
e_westbank = event(72, region="World", topic="Crime & Law", breadth=4,
                   title="Israeli Ambassador's Son Critically Injured in West Bank Attack",
                   title_hi="वेस्ट बैंक हमले में इजरायली राजदूत के बेटे गंभीर रूप से घायल")
check("8c: Hindi 'वेस्ट बैंक' (West Bank territory) does not false-positive into "
      "Finance & Markets banking tier (regression: production event 23704)",
      sr.classify_finance_markets(e_westbank) is None)

print("\n=== 9. Sections do not become dominated by one story/topic (diversity cap) ===")
dom_events = [event(80 + i, topic="Economy", breadth=8,
                    title=f"Sensex surges as stock {i} price jumps") for i in range(15)]
dom_events += [event(95, topic="Economy", breadth=3, title="India's GDP growth accelerates")]
dom_events += [event(96, topic="Economy", breadth=3, title="Union Budget policy reform announced")]
dom_events += [event(97, topic="Economy", breadth=3, title="Inflation data shows fiscal deficit narrowing")]
ranked, lead = rank_pool(dom_events, "economy")
stock_count = sum(1 for r in ranked if r["tier"] == "stocks")
check("9a: 15 near-identical stock stories don't fill the whole section",
      stock_count < len(ranked), f"stock_count={stock_count} of {len(ranked)}")

print("\n=== 10. Topic-only sections (no tier hierarchy) are not artificially capped at the tier-cap fraction ===")
health_events = [event(300 + i, topic="Health", breadth=3,
                       title=f"Hospital reports new health development {i}",
                       published_h_ago=i * 0.3) for i in range(12)]
ranked, lead = rank_pool(health_events, "health")
check("10a: a monolithic-topic section (all same event.topic) is not stuck at ceil(20*0.4)=8",
      len(ranked) > 8, f"len(ranked)={len(ranked)}")

print("\n=== 11. Same input produces deterministic output ===")
mixed_events = econ_events + fin_events + world_events + dom_events
r1, l1 = rank_pool(mixed_events, "economy")
r2, l2 = rank_pool(mixed_events, "economy")
r3, l3 = rank_pool(mixed_events, "economy")
ids1 = [r["event"]["id"] for r in r1]
ids2 = [r["event"]["id"] for r in r2]
ids3 = [r["event"]["id"] for r in r3]
check("11a: three independent runs over the same input produce identical ordering",
      ids1 == ids2 == ids3)

print("\n=== 12. Existing Story Intelligence semantics are unchanged (reused, not redefined) ===")
check("12a: section_rank reuses homepage_rank's fetch_si_signals unmodified",
      sr.hr.fetch_si_signals is hr.fetch_si_signals)
check("12b: section_rank reuses homepage_rank's fetch_velocity_signals unmodified",
      sr.hr.fetch_velocity_signals is hr.fetch_velocity_signals)
check("12c: section_rank reuses homepage_rank's india_relevance unmodified",
      sr.india_relevance is hr.india_relevance)

print("\n=== 13. Extensibility: SECTIONS is a flat, generic registry ===")
check("13a: all 13 spec'd sections are registered",
      len(sr.SECTIONS) == 13, f"got {len(sr.SECTIONS)}")
check("13b: every section has a label and a callable classify function",
      all("label" in v and callable(v["classify"]) for v in sr.SECTIONS.values()))

print("\n=== 14. FIX Economy/Finance boundary - Economy has no 'stocks' tier any more ===")
e_stock_only = event(140, topic="Economy", breadth=6,
                     title="Reliance shares gained 3 percent in early trade")
check("14a: a pure stock-price story gets no real Economy tier (falls to weak fallback at best)",
      sr.classify_economy(e_stock_only)[1] in ("general",),
      f"got tier {sr.classify_economy(e_stock_only)}")
check("14b: the SAME stock-price story gets a real, senior Finance & Markets tier",
      sr.classify_finance_markets(e_stock_only)[1] == "stocks")
e_fund_close = event(141, topic="Economy", breadth=3,
                     title="Kotak Alts Closes Rs 5000 Crore Fund from Domestic Investors")
check("14c: a fund-close story matches Finance & Markets' broadened institutions tier",
      sr.classify_finance_markets(e_fund_close) is not None
      and sr.classify_finance_markets(e_fund_close)[1] == "institutions")
e_steel = event(142, topic="Economy", breadth=6,
               title="Steel Prices Reach 4-Year High Amid Strong Demand")
check("14d: a commodity/sector price story now matches Economy's broadened 'sectors' tier "
      "instead of falling to the weak fallback",
      sr.classify_economy(e_steel) is not None and sr.classify_economy(e_steel)[1] == "sectors")
e_ai_tagged_economy = event(143, topic="Economy", breadth=4,
                            title="LTM Launches New AI Models for Enterprises")
check("14e: an AI story stored with topic=Economy upstream is suppressed from Economy's "
      "fallback (its real home is Technology, where it still matches)",
      sr.classify_economy(e_ai_tagged_economy) is None)
check("14f: ...and the same story DOES match Technology",
      sr.classify_technology(e_ai_tagged_economy) is not None)

print("\n=== 15. FIX Defence - incidental military mentions must not qualify ===")
e_road_rage = event(150, region="India", topic="Crime & Law", breadth=3,
                    title="Army Jawan Killed in Mizoram Road Rage Incident",
                    title_hi="सेना के जवान की मिजोरम में सड़क हादसे में मौत")
check("15a: a crime/accident story where the victim happens to be a soldier is NOT Defence",
      sr.classify_defence_security(e_road_rage) is None)
e_genuine_military = event(151, region="India", topic="Politics", breadth=3,
                           title="Troops begin joint military exercise near border",
                           title_hi="सेना ने सीमा के पास संयुक्त सैन्य अभ्यास शुरू किया")
check("15b: a genuine military-exercise story (same generic 'military' wording) IS Defence",
      sr.classify_defence_security(e_genuine_military) is not None)

print("\n=== 16. FIX Technology - bare 'AI' mention is not sufficient ===")
e_ai_substantive = event(160, topic="Science & Tech", breadth=3,
                         title="Startup Launches New AI Model for Enterprise Search")
check("16a: a substantive AI-model story IS Technology",
      sr.classify_technology(e_ai_substantive) is not None
      and sr.classify_technology(e_ai_substantive)[1] == "ai_semiconductor")
e_ai_speech = event(161, region="World", topic="Society", breadth=3,
                    title="Prince Harry's AI speech interrupted by technical issue")
check("16b: a speech merely MENTIONING AI is NOT Technology solely because AI appears",
      sr.classify_technology(e_ai_speech) is None)
e_ai_un = event(162, region="World", topic="International", breadth=3,
               title="UN General Assembly to Address War, Climate, and AI")
check("16c: a general UN story listing AI as one of several agenda items is NOT Technology",
      sr.classify_technology(e_ai_un) is None)

print("\n=== 17. FIX India & World - meaningful India connection required ===")
e_china_oil = event(170, region="World", topic="International", breadth=4,
                    title="Goldman Sachs Predicts Subdued Chinese Oil Imports")
check("17a: a story about CHINESE oil demand (no India relationship) is NOT India & World",
      sr.classify_india_world(e_china_oil) is None)
e_india_oil = event(171, region="World", topic="International", breadth=4,
                    title="India's Russian Crude Oil Imports Declined in August")
check("17b: India's OWN energy-import story IS India & World",
      sr.classify_india_world(e_india_oil) is not None)

print("\n=== 17c-d. FIX India & World topic gate - India's OWN diplomacy is tagged "
      "topic=Politics/Economy upstream (never 'International'), so the fallback must "
      "not require topic=='International' ===")
e_jaishankar = event(172, region="India", topic="Politics", breadth=4,
                     title="India's EAM Jaishankar Meets US Secretary of State Blinken")
check("17c: an India-foreign diplomatic meeting tagged topic=Politics (not "
      "International) still qualifies for India & World",
      sr.classify_india_world(e_jaishankar) is not None)
e_india_only = event(173, region="India", topic="Politics", breadth=4,
                     title="Prime Minister inaugurates new metro line in Pune")
check("17d: a purely domestic India story (no named foreign country) still does NOT "
      "qualify, even with the topic-gate relaxed",
      sr.classify_india_world(e_india_only) is None)

print("\n=== 17e-f. FIX India & World fallback - Sports/Crime & Law excluded (re-validation follow-up) ===")
e_cricket_banter = event(174, region="India", topic="Sports", breadth=3,
                         title="Pakistan coach Hesson says team must 'catch up' with India in T20 cricket")
check("17e: cricket commentary mentioning India and a foreign team is NOT India & World "
      "(a match is not a diplomatic/economic/security relationship)",
      sr.classify_india_world(e_cricket_banter) is None)
e_foreign_accident = event(175, region="World", topic="Crime & Law", breadth=3,
                           title="Two Indian students die in Canada flight training accident")
check("17f: an individual's personal accident/legal matter abroad is NOT India & World "
      "even though it names India and a foreign country",
      sr.classify_india_world(e_foreign_accident) is None)
e_politics_unaffected = event(176, region="India", topic="Politics", breadth=4,
                              title="India seeks constructive ties with Bangladesh, says MEA")
check("17g: the Sports/Crime & Law exclusion does not affect other topics (Politics still qualifies)",
      sr.classify_india_world(e_politics_unaffected) is not None)

print("\n=== 18. FIX Politics & Policy - foreign election leakage ===")
e_indian_election = event(180, region="India", topic="Politics", breadth=4,
                          title="Eight Meghalaya MLAs Join BJP")
check("18a: an Indian election/party story IS Politics & Policy",
      sr.classify_politics_policy(e_indian_election) is not None)
e_foreign_election = event(181, region="World", topic="Politics", breadth=4,
                           title="BC Premier Calls Snap Election Citing Trump Threat")
check("18b: a foreign (Canadian) election is NOT Politics & Policy via generic 'election' alone",
      sr.classify_politics_policy(e_foreign_election) is None)

print(f"\n{'=' * 60}")
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S):")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
else:
    print("ALL CHECKS PASSED")
