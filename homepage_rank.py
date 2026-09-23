"""
homepage_rank.py - deterministic Paksh homepage story ranking + section selection.

WHAT THIS REPLACES
-------------------
The home feed previously ordered by `feed_rank` = breadth * lean_mult * an 8h
recency decay * a fixed civic-topic weight (export_static.py::_feed_rank /
_civic_mult) - essentially "how many distinct outlets, decayed by age, with a
hand-picked topic multiplier". That is still a perfectly good BASE signal (it is
reused here as `breadth`), but it has no notion of momentum (a story accelerating
right now vs. one that peaked yesterday), no notion of a story materially
DEVELOPING again, and no notion of independent origins vs. syndicated copies
beyond the existing bias-bar dedup.

WHAT THIS ADDS
--------------
Reuses, rather than replaces, the existing distinct-outlet breadth counts,
Story Intelligence's independence classification and developments, and the
existing India/World region classification - see fetch_si_signals() and
fetch_velocity_signals() for the only new queries.

No LLM anywhere in this module. Every number here is arithmetic over data
Paksh already stores.

SIGNAL SUMMARY (each individually bounded/normalized - see homepage_rank_story()
for how they combine; the combination is NOT a plain weighted sum, see its
docstring for why)
  breadth      existing distinct rated+international outlet count (feed_row's own
               breadth signal) - log-scaled so outlet #20 matters far less than
               outlet #2. Never raw article/source_count, so syndicated copies of
               one wire can't inflate it (the existing one-vote-per-owner dedup
               already collapses those upstream, in analyze.py/source_selection.py).
  independence SI's independent-reporting-event count for this story (INDEPENDENT
               class only - DERIVED/ATTRIBUTED_REPETITION/UNCERTAIN never count).
               0/absent (not penalized) when SI hasn't processed this event yet -
               SI only covers a recent rolling window, see
               story_intelligence.recent_event_ids().
  velocity     count of DISTINCT publisher OWNERS whose first article on this
               story was fetched within the last VELOCITY_WINDOW_H hours (see
               fetch_velocity_signals) - a genuine "publishers per hour" proxy
               using articles.fetched_at (reliable ingest time), not the often-
               missing/noisy RSS `published` timestamp export_static.py already
               distrusts for this reason (see _importance()'s docstring).
  developments SI si_developments rows for this story, recency-decayed - a story
               that materially developed 30 minutes ago outranks one that is
               merely 10 minutes newer with nothing new to say.
  freshness    age since the MORE RECENT of (published_at, latest development) -
               so a genuine new development resets the clock, not just new copy.
  india        existing event.region (India/World, set by analyze.py) as the
               base, refined by the existing CIVIC_KEYWORDS nudge - bounded so
               it influences, never determines, the final score (a globally
               consequential World story can still lead).

Every sub-score is attached to the returned dict (see homepage_rank_story) so a
ranking can always be explained: "why did this story rank #3" has a real,
inspectable answer, not a black box.
"""
import math
from collections import defaultdict
from datetime import datetime

try:
    from sources import OWNER_BY_SOURCE
except ImportError:                          # pragma: no cover - only for ad hoc scripts
    OWNER_BY_SOURCE = {}

try:
    from export_static import CIVIC_KEYWORDS, CIVIC_TOPIC_WEIGHT
except ImportError:                          # pragma: no cover - keeps this module
    import re                                # importable standalone (e.g. from tests)
    CIVIC_KEYWORDS = re.compile(
        r"amendment|ordinance|\bbill\b|parliament|sansad|lok sabha|rajya sabha|"
        r"supreme court|high court|verdict|constitution|reservation|\bquota\b|"
        r"protest|andolan|movement|morcha|bandh|\bcabinet\b|governor|election|"
        r"\bpolicy\b|\bact\b", re.I)
    CIVIC_TOPIC_WEIGHT = {
        "Politics": 1.6, "Economy": 1.3, "Crime & Law": 1.3, "Environment": 1.1,
        "Science & Tech": 1.0, "Health": 1.0, "Society": 1.0, "International": 0.9,
        "Entertainment": 0.7, "Sports": 0.6,
    }

# --- tunables, each documented at its use site below ---------------------------------
RECENCY_HALF_LIFE_H = 10.0     # main-score freshness half-life
MOMENTUM_HALF_LIFE_H = 6.0     # trending is stricter about staleness than the main score
DEV_HALF_LIFE_H = 14.0         # how fast a development's OWN boost fades
VELOCITY_WINDOW_H = 3.0        # "recent" window for the publisher-growth signal
BREADTH_REF = 10.0             # log-normalization reference points - see _log_norm
INDEP_REF = 5.0
VELOCITY_REF = 5.0
DEV_REF = 3.0
INTL_INDIA_MULT = 0.75         # India multiplier FLOOR for a World-region story. Tuned
                                # against the real production corpus (2026-09-23): 0.45
                                # let India-relevance functionally DECIDE the top of the
                                # page (every one of the top 20 was India, even against a
                                # 30-outlet/17-new-owners World story with the single
                                # highest raw interest score in the whole pool) - that is
                                # "determine", not "influence" (Step 6/Step 9 explicitly
                                # forbid this). 0.75 keeps a real, visible India edge
                                # (India stories still lead most rankings) while letting a
                                # genuinely large World story compete for the top instead
                                # of being structurally excluded from it.
CIVIC_NUDGE = 0.20             # small bounded India-relevance nudge from CIVIC_KEYWORDS
WHAT_CHANGED_MAX_AGE_H = 48.0  # a "development" from days ago is not "what changed" -
                                # tuned against the real corpus, which showed si_developments
                                # rows up to ~116h old ranking in a what-changed top 20
WORTH_KNOWING_MAX_AGE_H = 96.0  # "worth knowing" != "buried and forgotten" - same reason

# main-score weights: additive "how interesting is this" components, then gated
# (multiplied, not added) by freshness and India-relevance - see homepage_rank_story.
W_BREADTH, W_INDEP, W_VELOCITY, W_DEV = 1.0, 0.8, 1.1, 1.3
# momentum weights: same idea, shifted toward velocity/development, away from raw breadth,
# so a small-but-rapidly-growing story can out-trend a big-but-static one (Step 5).
MW_BREADTH, MW_INDEP, MW_VELOCITY, MW_DEV = 0.4, 0.6, 1.6, 1.6


def _parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "").split("+")[0])
    except (ValueError, TypeError):
        return None


def _hours_since(now, ts):
    if ts is None:
        return None
    return max((now - ts).total_seconds() / 3600.0, 0.0)


def _log_norm(x, ref):
    """log1p(x) / log1p(ref), i.e. reaches 1.0 at x==ref and keeps growing slowly
    past it - so outlet/owner/development #2 matters far more than #20, without
    ever hard-capping a genuinely huge story."""
    if x <= 0:
        return 0.0
    return math.log1p(x) / math.log1p(ref)


def fetch_si_signals(conn, event_ids):
    """Batched Story Intelligence lookup for a pool of event ids.
    Returns {event_id: {independent_count, total_reporting, dev_count,
    latest_dev_time (datetime or None), has_si (bool)}}.
    has_si=False means SI has never processed this event (it only covers a recent
    rolling window - story_intelligence.recent_event_ids) - callers must treat
    that as UNKNOWN, not as zero/negative evidence."""
    event_ids = [int(e) for e in event_ids]
    out = {eid: {"independent_count": 0, "total_reporting": 0,
                 "dev_count": 0, "latest_dev_time": None, "has_si": False}
           for eid in event_ids}
    if not event_ids:
        return out
    qmarks = ",".join("?" * len(event_ids))
    try:
        for eid, indep, n in conn.execute(
            f"SELECT event_id, independence, COUNT(*) FROM si_reporting_events "
            f"WHERE event_id IN ({qmarks}) GROUP BY event_id, independence", event_ids):
            row = out.get(eid)
            if row is None:
                continue
            row["has_si"] = True
            row["total_reporting"] += n
            if indep == "INDEPENDENT":
                row["independent_count"] += n
        for eid, event_time, published_at, first_seen_at in conn.execute(
            f"SELECT event_id, event_time, published_at, first_seen_at FROM si_developments "
            f"WHERE event_id IN ({qmarks})", event_ids):
            row = out.get(eid)
            if row is None:
                continue
            ts = _parse_ts(event_time) or _parse_ts(published_at) or _parse_ts(first_seen_at)
            row["has_si"] = True
            row["dev_count"] += 1
            if ts is not None and (row["latest_dev_time"] is None or ts > row["latest_dev_time"]):
                row["latest_dev_time"] = ts
    except Exception:
        # SI tables may not exist yet on an older/fresh database (init_si_schema not
        # run) - degrade to "no SI data anywhere", never crash the export over this.
        pass
    return out


def fetch_velocity_signals(conn, event_ids, now):
    """Batched, SI-independent coverage-velocity proxy: for each event, how many
    DISTINCT publisher owners were first seen covering it within the last
    VELOCITY_WINDOW_H hours, and in total - using articles.fetched_at (reliable
    ingest time; `published` is often missing/noisy from RSS - see
    export_static._importance()'s existing note on why that field isn't trusted
    for timing). Works for every event, not only ones SI has processed.
    Returns {event_id: {owners_total, owners_recent}}."""
    event_ids = [int(e) for e in event_ids]
    out = {eid: {"owners_total": 0, "owners_recent": 0} for eid in event_ids}
    if not event_ids:
        return out
    qmarks = ",".join("?" * len(event_ids))
    seen = defaultdict(set)
    recent = defaultdict(set)
    for eid, source, first_fetched in conn.execute(
        f"SELECT event_id, source, MIN(fetched_at) FROM articles "
        f"WHERE event_id IN ({qmarks}) GROUP BY event_id, source", event_ids):
        owner = OWNER_BY_SOURCE.get(source, source)
        seen[eid].add(owner)
        ts = _parse_ts(first_fetched)
        age = _hours_since(now, ts)
        if age is not None and age <= VELOCITY_WINDOW_H:
            recent[eid].add(owner)
    for eid in event_ids:
        out[eid]["owners_total"] = len(seen.get(eid, ()))
        out[eid]["owners_recent"] = len(recent.get(eid, ()))
    return out


def india_relevance(event):
    """Bounded India-relevance score in roughly [INTL_INDIA_MULT, 1.0 + CIVIC_NUDGE].
    Base signal is the EXISTING event.region (India/World - analyze.py's own
    classification, already stored, no new keyword list). Refined only by the
    EXISTING CIVIC_KEYWORDS regex (parliament/court/policy context Sameer already
    curates for front-page weighting) as a small, bounded nudge - never a second
    independent axis that could overwhelm the region signal."""
    base = 1.0 if event.get("region") == "India" else INTL_INDIA_MULT
    text = " ".join([event.get("title") or "", event.get("title_hi") or ""])
    nudge = CIVIC_NUDGE if CIVIC_KEYWORDS.search(text) else 0.0
    return round(min(base + nudge, 1.0 + CIVIC_NUDGE), 4)


def _breadth(event):
    lc = event.get("lean_counts") or {}
    rated = sum(lc.get(s, 0) for s in ("left", "center", "right"))
    return rated + (event.get("international", 0) or 0)


def _freshness_age_h(event, si, now):
    """Hours since the MORE RECENT of (real publish time, latest SI development) -
    a genuine development resets the staleness clock (Step 2.5 / Step 5's 'a story
    that materially developed 30 minutes ago should be able to rise again')."""
    published = _parse_ts(event.get("published_at") or event.get("created_at"))
    candidates = [t for t in (published, si.get("latest_dev_time")) if t is not None]
    if not candidates:
        return 1e6
    newest = max(candidates)
    return _hours_since(now, newest) or 0.0


def homepage_rank_story(event, si, velocity, now):
    """The main homepage score. NOT a plain weighted sum (explicitly required):
    an `interest` sum of bounded/log-scaled evidence-of-attention signals
    (breadth, independence, velocity, developments) is GATED (multiplied) by two
    separate bounded factors - `freshness` (a decay, so it can only shrink
    interest, never invert its ordering) and `india` (bounded to roughly
    [0.45, 1.2], so it nudges but can never zero out or 10x a story). This is
    what stops, e.g., a firehose of 100 syndicated copies (low `independence`,
    breadth already deduped) from beating 8 genuinely independent publishers, and
    what stops India relevance from being the sole determinant of rank.
    Returns a dict with every sub-score attached, so any ranking is explainable."""
    breadth = _breadth(event)
    breadth_c = _log_norm(breadth, BREADTH_REF)
    indep_c = _log_norm(si.get("independent_count", 0), INDEP_REF)
    velocity_c = _log_norm(velocity.get("owners_recent", 0), VELOCITY_REF)
    dev_latest = si.get("latest_dev_time")
    dev_age_h = _hours_since(now, dev_latest)
    dev_recency = (0.5 ** (dev_age_h / DEV_HALF_LIFE_H)) if dev_age_h is not None else 0.0
    dev_c = _log_norm(si.get("dev_count", 0), DEV_REF) * dev_recency

    interest = (W_BREADTH * breadth_c + W_INDEP * indep_c
                + W_VELOCITY * velocity_c + W_DEV * dev_c)

    age_h = _freshness_age_h(event, si, now)
    freshness = 0.5 ** (age_h / RECENCY_HALF_LIFE_H)
    india = india_relevance(event)

    score = interest * freshness * india
    return {
        "score": round(score, 5),
        "breadth": breadth,
        "breadth_component": round(breadth_c, 4),
        "independent_count": si.get("independent_count", 0),
        "independence_component": round(indep_c, 4),
        "owners_recent": velocity.get("owners_recent", 0),
        "velocity_component": round(velocity_c, 4),
        "dev_count": si.get("dev_count", 0),
        "dev_component": round(dev_c, 4),
        "freshness_age_h": round(age_h, 2),
        "freshness": round(freshness, 4),
        "india_relevance": india,
        "has_si": si.get("has_si", False),
        "interest": round(interest, 4),
    }


def momentum_score(event, si, velocity, now):
    """Trending-specific score: same ingredients as homepage_rank_story, reweighted
    toward velocity/developments and away from raw breadth (Step 5) so a small
    story with real momentum can outrank a big story that has stopped changing,
    with a stricter (shorter) freshness half-life so Trending decays faster than
    the main homepage. India relevance is deliberately NOT applied here - Trending
    is about momentum, not regional weighting (India-first pressure already comes
    from the India section and the main score)."""
    breadth_c = _log_norm(_breadth(event), BREADTH_REF)
    indep_c = _log_norm(si.get("independent_count", 0), INDEP_REF)
    velocity_c = _log_norm(velocity.get("owners_recent", 0), VELOCITY_REF)
    dev_latest = si.get("latest_dev_time")
    dev_age_h = _hours_since(now, dev_latest)
    dev_recency = (0.5 ** (dev_age_h / DEV_HALF_LIFE_H)) if dev_age_h is not None else 0.0
    dev_c = _log_norm(si.get("dev_count", 0), DEV_REF) * dev_recency

    interest = (MW_BREADTH * breadth_c + MW_INDEP * indep_c
                + MW_VELOCITY * velocity_c + MW_DEV * dev_c)
    age_h = _freshness_age_h(event, si, now)
    freshness = 0.5 ** (age_h / MOMENTUM_HALF_LIFE_H)
    return round(interest * freshness, 5)


# ---------------------------------------------------------------------------------------
# section selection / diversity
# ---------------------------------------------------------------------------------------

HERO_N = 3
SECTION_N = 20
MAX_PER_TOPIC_IN_SECTION = 0.5   # a single topic may not exceed this fraction of a section
MAX_PER_STORYLINE_IN_SECTION = 1  # a single storyline (ongoing saga) appears at most once
                                  # per section - the diversity rule Step 4 asks for


def _diversify(ranked, n, key=lambda r: r["score"], topic_cap_frac=MAX_PER_TOPIC_IN_SECTION):
    """Greedy top-N selection with two anti-domination constraints (Step 4):
    (a) no more than `topic_cap_frac` of the section from one topic, (b) no
    storyline (ongoing saga) contributes more than one story to the same
    section. Both are soft caps (skip, don't crash, if too few qualifying
    stories exist to fill the section - Step 3 explicitly allows a thin
    section rather than backfilling with weak stories)."""
    topic_cap = max(1, math.ceil(n * topic_cap_frac))
    chosen, topic_count, storyline_seen = [], defaultdict(int), set()
    for r in sorted(ranked, key=key, reverse=True):
        if len(chosen) >= n:
            break
        topic = r["event"].get("topic") or "General"
        sid = r["event"].get("storyline_id")
        if topic_count[topic] >= topic_cap:
            continue
        if sid is not None and sid in storyline_seen:
            continue
        chosen.append(r)
        topic_count[topic] += 1
        if sid is not None:
            storyline_seen.add(sid)
    return chosen


def select_homepage_sections(ranked):
    """ranked: list of {"event": event_dict, **homepage_rank_story(...) fields,
    "momentum": momentum_score(...)}. Returns an ordered dict of section name ->
    list of ranked entries. A section is omitted (not padded with weak filler)
    if fewer than 3 stories qualify - Step 3's explicit instruction."""
    sections = {}

    hero = _diversify(ranked, HERO_N, topic_cap_frac=1.0)  # hero may repeat topic (it's 1-3 stories)
    if hero:
        sections["hero"] = hero

    india_pool = [r for r in ranked if r["event"].get("region") == "India"]
    india = _diversify(india_pool, SECTION_N)
    if len(india) >= 3:
        sections["india"] = india

    world_pool = [r for r in ranked if r["event"].get("region") != "India"]
    world = _diversify(world_pool, SECTION_N)
    if len(world) >= 3:
        sections["world"] = world

    # "what changed" requires a development that is ITSELF recent, not just any
    # si_developments row regardless of age - see WHAT_CHANGED_MAX_AGE_H.
    changed_pool = [r for r in ranked if r["dev_count"] > 0
                     and r["freshness_age_h"] <= WHAT_CHANGED_MAX_AGE_H]
    changed = _diversify(changed_pool, SECTION_N,
                          key=lambda r: (r["dev_component"], r["score"]))
    if len(changed) >= 3:
        sections["what_changed"] = changed

    trending = _diversify(ranked, SECTION_N, key=lambda r: r["momentum"])
    trending = [r for r in trending if r["momentum"] > 0]
    if len(trending) >= 3:
        sections["trending"] = trending

    # Worth knowing: high-information but not necessarily the biggest/newest -
    # independence-heavy stories that AREN'T already the hero, ranked by
    # independence/breadth rather than raw score (so it surfaces different
    # stories than the top list, not just a shorter copy of it).
    hero_ids = {r["event"]["id"] for r in hero}
    worth_pool = [r for r in ranked
                  if r["event"]["id"] not in hero_ids and r["independent_count"] > 0
                  and r["freshness_age_h"] <= WORTH_KNOWING_MAX_AGE_H]
    worth = _diversify(worth_pool, SECTION_N,
                        key=lambda r: (r["independence_component"], r["breadth_component"]))
    if len(worth) >= 3:
        sections["worth_knowing"] = worth

    return sections
