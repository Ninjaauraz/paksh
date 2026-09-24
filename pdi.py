"""
pdi.py - Public Discourse Intelligence, V1 (shadow/offline mode).

WHAT THIS IS
------------
"Find out what the conventional news corpus does not fully reveal about how a
story is being understood, questioned, interpreted and experienced."

PDI is an ADDITIVE enrichment layer over an existing Paksh event. It never
creates a second story identity - every PDI row is keyed by the existing
events.id (see database.py). It discovers people-led public discourse
(Reddit, Substack, ...), narrows it deterministically, associates it
conservatively with the event, extracts atomic observations, clusters them
across sources while preserving provenance, and produces one compact,
story-level payload per run.

PDI is explicitly NOT: sentiment analysis, a public-opinion score, a truth
score, an importance score, an engagement score, comment-counting, consensus
detection, or a second Story Intelligence system. See ASSOCIATION_CLASSES and
OBSERVATION_TYPES below - the vocabulary itself is a product constraint, the
same convention story_intelligence.py already uses for the same reason.

SHADOW MODE (V1)
-----------------
PDI may READ existing Paksh data (events, articles, Story Intelligence,
homepage-level significance signals). PDI may discover external discourse and
persist PDI results into its OWN additive pdi_* tables. PDI MUST NOT modify
events.analysis_json, articles, Story Intelligence, clustering, homepage
ranking, section ranking, export_static behaviour, publication eligibility,
or the reader UI - and does not. This module is isolated exactly like
story_intelligence.py: nothing in ingest.py/cluster.py/analyze.py/
export_static.py/homepage_rank.py/section_rank.py/live.py imports it, and it
is never wired into refresh.py or live.py in this phase.

Pipeline (frozen):
  Paksh Story -> Eligibility -> Discourse Profile -> Query Generation ->
  Source Discovery -> Candidate Filtering -> Story Association ->
  Quality Filter -> Observation Extraction -> Cross-source Clustering ->
  Story-level PDI -> [SHADOW STOP]

DETERMINISTIC NARROWING FIRST: every stage through Quality Filter is pure,
deterministic, regex/lexical logic (the same style as story_intelligence.py's
independence classification) - no LLM call anywhere in V1. Observation
extraction and association use bounded, versioned, deterministic heuristics
rather than a semantic model, so the entire non-network portion of the
pipeline is reproducible (same input -> same output, every time - Test Q).
A future version may introduce bounded semantic processing at the
association/observation stages; when it does, DETERMINISTIC NARROWING FIRST
still applies (Part 24) - semantic processing only after the candidate space
has already been reduced by the deterministic filters below.

CLI (read-only unless --persist):
  py pdi.py --event 23360 [--persist] [--force]
  py pdi.py --eligible [--limit 20] [--persist]
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

PDI_VERSION = "pdi-v1"

# =====================================================================================
# vocabulary (product constraints, not implementation detail - see module docstring)
# =====================================================================================

MODE_STANDARD = "STANDARD"
MODE_DEEP = "DEEP"
MODES = (MODE_STANDARD, MODE_DEEP)

ASSOCIATION_DIRECT_EVENT = "DIRECT_EVENT"
ASSOCIATION_RELATED_CONTEXT = "RELATED_CONTEXT"
ASSOCIATION_BACKGROUND = "BACKGROUND"
ASSOCIATION_UNRELATED = "UNRELATED"
ASSOCIATION_CLASSES = (ASSOCIATION_DIRECT_EVENT, ASSOCIATION_RELATED_CONTEXT,
                        ASSOCIATION_BACKGROUND, ASSOCIATION_UNRELATED)

OBS_THEME = "THEME"
OBS_QUESTION = "QUESTION"
OBS_CONCERN = "CONCERN"
OBS_INTERPRETATION = "INTERPRETATION"
OBS_EXPERIENCE = "EXPERIENCE"
OBS_DISAGREEMENT = "DISAGREEMENT"
OBS_UNCERTAINTY = "UNCERTAINTY"
OBS_IMPLICATION = "IMPLICATION"
OBSERVATION_TYPES = (OBS_THEME, OBS_QUESTION, OBS_CONCERN, OBS_INTERPRETATION,
                      OBS_EXPERIENCE, OBS_DISAGREEMENT, OBS_UNCERTAINTY, OBS_IMPLICATION)
# Deliberately absent, forever: PUBLIC_OPINION, SENTIMENT, IMPORTANCE, TRUTH_SCORE,
# CONSENSUS_SCORE. Adding any of these would violate the frozen architecture.

RUN_RUNNING = "RUNNING"
RUN_VALID = "VALID"
RUN_STALE = "STALE"
RUN_SUPERSEDED = "SUPERSEDED"
RUN_NO_MEANINGFUL_DISCOURSE = "NO_MEANINGFUL_DISCOURSE"
RUN_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
RUN_FAILED = "FAILED"
RUN_STATUSES = (RUN_RUNNING, RUN_VALID, RUN_STALE, RUN_SUPERSEDED,
                 RUN_NO_MEANINGFUL_DISCOURSE, RUN_INSUFFICIENT_EVIDENCE, RUN_FAILED)
# Non-success outcomes that are NOT execution failures (Part 3):
NON_SUCCESS_OUTCOMES = (RUN_NO_MEANINGFUL_DISCOURSE, RUN_INSUFFICIENT_EVIDENCE)

QUALITY_SELECTED = "SELECTED"
QUALITY_REJECTED = "REJECTED"

QUERY_EVENT_DIRECT = "EVENT_DIRECT"
QUERY_ENTITY_CONSEQUENCE = "ENTITY_CONSEQUENCE"
QUERY_QUESTIONS = "QUESTIONS"
QUERY_INTERPRETATION = "INTERPRETATION"
QUERY_FAMILIES = (QUERY_EVENT_DIRECT, QUERY_ENTITY_CONSEQUENCE, QUERY_QUESTIONS, QUERY_INTERPRETATION)

PROVIDER_REDDIT = "reddit"
PROVIDER_SUBSTACK = "substack"

# retrieval budgets (Part 5) - budgets, not requirements to manufacture queries
QUERY_BUDGET = {MODE_STANDARD: (8, 10), MODE_DEEP: (12, 20)}
CANDIDATE_BUDGET_PER_QUERY = {MODE_STANDARD: 8, MODE_DEEP: 15}

DISCOURSE_WINDOW_DAYS = {MODE_STANDARD: 21, MODE_DEEP: 45}


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(dt):
    return dt.isoformat(timespec="seconds")


def jaccard(a, b):
    """Same convention as story_intelligence.py's own jaccard() - set overlap, no
    magic. Reused here rather than reinvented."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


_STOPWORDS = frozenset("""a an the of for to in on at by with and or but is are was were
be been being this that these those it its as from into about over after before""".split())


def _stem(w):
    """Crude, deterministic suffix-stripping (no NLP dependency) so 'Cuts'/'cut',
    'Rates'/'rate', 'discussing'/'discuss' overlap in relevance scoring - the same
    "bounded, explainable approximation" philosophy as _extract_entities(). Only
    strips when the remaining stem stays long enough to still be meaningful."""
    if len(w) > 6 and w.endswith("ing"):
        return w[:-3]
    if len(w) > 5 and w.endswith("ed"):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _tokens(text):
    words = re.findall(r"[a-z0-9ऀ-ॿ]+", (text or "").lower())
    return {_stem(w) for w in words} - _STOPWORDS


# =====================================================================================
# domain objects - normalized, deterministic, testable (Phase 2)
# =====================================================================================

@dataclass
class DiscourseProfile:
    event_id: int
    title: str
    summary: str
    topic: str
    region: str
    core_entities: list = field(default_factory=list)
    affected_groups: list = field(default_factory=list)
    likely_implications: list = field(default_factory=list)
    geography: list = field(default_factory=list)
    language_priorities: list = field(default_factory=list)
    mode: str = MODE_STANDARD


@dataclass
class Query:
    text: str
    family: str
    language: str


@dataclass
class QueryPlan:
    event_id: int
    mode: str
    queries: list = field(default_factory=list)  # list[Query]


@dataclass
class Candidate:
    provider: str
    provider_item_id: str
    url: str
    canonical_url: str
    title: str
    author: str
    published_at: str  # ISO or None
    language: str
    discovery_query: str
    discovery_rank: int
    content_hash: str
    body_text: str = ""          # ephemeral, kept in-memory only (Part 15: never persisted raw)
    engagement: dict = field(default_factory=dict)   # ephemeral, discovery-only signal (Part 9)


@dataclass
class Association:
    candidate: Candidate
    association: str
    association_score: float
    relevance_score: float
    specificity_score: float
    source_quality_score: float
    independence_score: float
    recency_score: float
    quality_status: str
    reason: str
    relevant_passage: str = ""   # ephemeral, never persisted as its own column (same
                                 # convention as Candidate.body_text) - the specific
                                 # passage that justified a semantic association, so
                                 # extract_observations() operates on what was actually
                                 # judged relevant rather than the whole candidate
                                 # document (hardening-pass Finding F). Empty when
                                 # semantic scoring wasn't used (deterministic-only
                                 # path has no passage concept - the whole document IS
                                 # what jaccard judged).


@dataclass
class Observation:
    candidate: Candidate
    observation_type: str
    text: str
    observation_hash: str
    cluster_key: str
    confidence: float


@dataclass
class StoryPDI:
    event_id: int
    recurring_themes: list
    recurring_questions: list
    interpretations: list
    experiences: list
    disagreements: list
    uncertainties: list
    implications: list
    coverage_gaps: list
    understanding_contribution: str


# =====================================================================================
# Phase 3 - eligibility (reuses homepage_rank / Story Intelligence signals only)
# =====================================================================================

# Thresholds on homepage_rank's OWN "interest" scale (see homepage_rank.py: BREADTH_REF=10,
# INDEP_REF=5, VELOCITY_REF=5, DEV_REF=3 - the interest components are log-normalized
# against those references, so a value of ~1.0 already means "roughly reference-level
# coverage/velocity/independence", not an arbitrary new unit). No new significance model
# is computed here - these are literal thresholds on numbers homepage_rank.py already
# produces for the live homepage. `interest` (breadth/independence/velocity/developments,
# BEFORE the freshness/india_relevance gates) is used rather than the fully-gated `score`:
# `score` is dominated by freshness decay, which would make almost any brand-new-but-thin
# story look "significant" purely for being an hour old, and would unfairly deflate a
# genuinely major World story via the india_relevance floor - PDI eligibility should not
# inherit the same recency/India bias the homepage display ranking intentionally has.
DEEP_INTEREST_THRESHOLD = 3.0
DEEP_DEV_COUNT_THRESHOLD = 2
DEEP_MOMENTUM_THRESHOLD = 2.5
STANDARD_INTEREST_THRESHOLD = 1.0
MIN_BREADTH_FOR_ELIGIBILITY = 2   # matches get_all_events()'s own publish gate


def determine_eligibility(event, si, velocity, now=None):
    """Deterministic eligibility gate. Returns (mode_or_None, reason).
    mode is None (not eligible) with reason 'NOT_SIGNIFICANT' for the common case of an
    ordinary, non-significant story - PDI must not run for every event (Part 3)."""
    import homepage_rank as hr
    now = now or _now()
    breadth = hr._breadth(event)
    if breadth < MIN_BREADTH_FOR_ELIGIBILITY:
        return None, "NOT_SIGNIFICANT"
    ranked = hr.homepage_rank_story(event, si, velocity, now)
    momentum = hr.momentum_score(event, si, velocity, now)
    interest = ranked["interest"]
    dev_count = ranked["dev_count"]
    if interest >= DEEP_INTEREST_THRESHOLD or dev_count >= DEEP_DEV_COUNT_THRESHOLD or momentum >= DEEP_MOMENTUM_THRESHOLD:
        return MODE_DEEP, "MAJOR_OR_DEVELOPING"
    if interest >= STANDARD_INTEREST_THRESHOLD:
        return MODE_STANDARD, "SIGNIFICANT"
    return None, "NOT_SIGNIFICANT"


# =====================================================================================
# Phase 4 - discourse profile (derived from existing event/SI data, no reinvented identity)
# =====================================================================================

# A small, explicit regional-language nudge (Part 4: "A regional story may prioritize
# relevant regional languages" - not blind translation into every Indian language). Keyed
# on state/city names that plausibly appear in a title/summary; deliberately narrow.
_STATE_LANGUAGE = {
    "tamil nadu": "ta", "chennai": "ta",
    "kerala": "ml", "kochi": "ml", "thiruvananthapuram": "ml",
    "west bengal": "bn", "bengal": "bn", "kolkata": "bn",
    "maharashtra": "mr", "mumbai": "mr", "pune": "mr",
    "karnataka": "kn", "bengaluru": "kn", "bangalore": "kn",
    "telangana": "te", "andhra pradesh": "te", "hyderabad": "te",
    "punjab": "pa", "chandigarh": "pa",
    "gujarat": "gu", "ahmedabad": "gu",
    "odisha": "or", "bhubaneswar": "or",
    "assam": "as", "guwahati": "as",
}

_ENTITY_STOP_LEAD = frozenset({"The", "A", "An", "This", "That", "New", "After", "Amid", "Amidst"})

# Words that BREAK a proper-noun phrase even though headline title-case often capitalizes
# them too: common reporting verbs ("X Orders Y", "X Launches Y") and prepositions ("Probe
# Into Y"). Without this, naive Title-Case-run extraction merges the verb/preposition into
# the entity name ("Supreme Court Orders", "Probe Into Ram Temple...") and produces
# incoherent downstream queries ("how does Supreme Court Orders affect Supreme Court
# Orders"). Not a full POS tagger - a bounded, explainable denylist, same spirit as the
# rest of this module's deterministic heuristics.
_ENTITY_BREAK_WORDS = frozenset({
    "Orders", "Order", "Launches", "Launch", "Announces", "Announce", "Warns", "Warn",
    "Demands", "Demand", "Raises", "Raise", "Flags", "Flag", "Says", "Say", "Meets", "Meet",
    "Discusses", "Discuss", "Reveals", "Reveal", "Confirms", "Confirm", "Denies", "Deny",
    "Rejects", "Reject", "Approves", "Approve", "Slams", "Slam", "Blames", "Blame",
    "Criticizes", "Criticize", "Urges", "Urge", "Seeks", "Seek", "Wins", "Win", "Loses",
    "Lose", "Dies", "Die", "Visits", "Visit", "Signs", "Sign", "Calls", "Call", "Hits",
    "Hit", "Faces", "Face", "Sparks", "Spark", "Begins", "Begin", "Ends", "End", "Targets",
    "Target", "Delivers", "Deliver", "Secures", "Secure", "Unveils", "Unveil", "Considers",
    "Consider", "Acts", "Act", "Probes", "Probe", "Grants", "Grant", "Takes", "Take",
    "Into", "For", "With", "From", "On", "By", "Over", "About", "Against", "Amid", "Amidst",
    "To", "Of", "As", "At", "Says",
})


def _extract_entities(title, max_n=6):
    """Deterministic proper-noun-phrase extraction: consecutive Title-Case (or short
    ALLCAPS acronym) words, the same lightweight heuristic style already used elsewhere
    in this codebase (e.g. section_rank.py's keyword-tier regexes) rather than a new NLP
    dependency. Not full NER - a bounded, explainable approximation, adequate for
    generating story-specific search queries. Phrases are capped at 3 words so a long
    run-on Title Case headline still yields usable, query-sized entity phrases."""
    words = re.findall(r"[A-Za-z][A-Za-z0-9.'-]*|\S", title or "")
    phrases, cur = [], []
    for w in words:
        core = w.strip(".,'\"():;")
        is_proper = bool(core) and (core[0].isupper() and not core.isupper() and len(core) > 1
                                     or (core.isupper() and 2 <= len(core) <= 5))
        breaks = core in _ENTITY_BREAK_WORDS
        if is_proper and core not in _ENTITY_STOP_LEAD and not breaks and len(cur) < 3:
            cur.append(core)
        else:
            if cur:
                phrases.append(" ".join(cur))
            cur = []
    if cur:
        phrases.append(" ".join(cur))
    seen, out = set(), []
    for p in phrases:
        if p.lower() not in seen and len(p) > 1:
            seen.add(p.lower())
            out.append(p)
    return out[:max_n]


def _language_priorities(event, article_languages, geography):
    """Story-specific language priority list, derived from (a) the ACTUAL language mix
    of this event's own articles (a genuine Paksh-corpus signal, not a guess) and (b) a
    narrow regional nudge from recognized geography. English is always included as the
    baseline reporting language. This is deliberately NOT "translate into every Indian
    language" (Part 4's explicit anti-pattern)."""
    langs = ["en"]
    counts = {}
    for lg in article_languages:
        if lg:
            counts[lg] = counts.get(lg, 0) + 1
    for lg, _ in sorted(counts.items(), key=lambda kv: -kv[1]):
        if lg not in langs:
            langs.append(lg)
    if event.get("region") == "India" and "hi" not in langs:
        langs.insert(1, "hi")
    for g in geography:
        rl = _STATE_LANGUAGE.get(g.lower())
        if rl and rl not in langs:
            langs.append(rl)
    return langs[:4]   # bounded - a handful of priority languages, not every language


def build_discourse_profile(event, article_languages=None, mode=MODE_STANDARD):
    """Derived entirely from the EXISTING event dict (database.get_event's shape) - no
    second story identity, no new significance model. article_languages: iterable of
    articles.language values for this event's member articles (see
    database.get_articles_for_events), used only for the language-priority signal."""
    title = event.get("title") or ""
    summary = event.get("summary") or ""
    topic = event.get("topic") or "General"
    region = event.get("region") or "World"
    entities = _extract_entities(title)
    geography = [e for e in entities if e.lower() in _STATE_LANGUAGE] or ([region] if region else [])
    affected_groups = [g for g in entities if g not in geography][:4]
    likely_implications = []  # V1: left for the query-generation stage to phrase as questions;
                               # not populated from a second inference model here.
    langs = _language_priorities(event, article_languages or [], geography)
    return DiscourseProfile(
        event_id=event["id"], title=title, summary=summary, topic=topic, region=region,
        core_entities=entities, affected_groups=affected_groups,
        likely_implications=likely_implications, geography=geography,
        language_priorities=langs, mode=mode,
    )


# =====================================================================================
# Phase 4 (cont.) - query generation: 4 conceptual families, bounded, story-specific
# =====================================================================================

def generate_query_plan(profile: DiscourseProfile) -> QueryPlan:
    """Bounded, story-specific, multilingual-where-justified query generation. Never a
    blind generic query ("what do people think about this?") - every query is templated
    from the profile's own entities/topic, and languages beyond English are only used
    when the profile's own language_priorities actually justify them (Part 4/5)."""
    lo, hi = QUERY_BUDGET[profile.mode]
    entities = profile.core_entities or [profile.title.split(" - ")[0][:60]]
    primary_entity = entities[0] if entities else profile.title[:60]
    secondary = entities[1] if len(entities) > 1 else profile.topic
    langs = profile.language_priorities[: (2 if profile.mode == MODE_STANDARD else 3)]

    templates = {
        QUERY_EVENT_DIRECT: [
            "{title}",
            "{primary} {topic}",
        ],
        QUERY_ENTITY_CONSEQUENCE: [
            "{primary} impact on {affected}",
            "how does {primary} affect {affected}",
        ],
        QUERY_QUESTIONS: [
            "why did {primary} {topic_lower}",
            "what happens next {primary}",
        ],
        QUERY_INTERPRETATION: [
            "{primary} analysis explained",
            "{primary} opinion",
        ],
    }
    # prefer an affected-group that is NOT the same as the primary entity, so
    # ENTITY_CONSEQUENCE queries don't become self-referential ("X impact on X")
    affected = next((g for g in profile.affected_groups if g.lower() != primary_entity.lower()), None) or secondary

    queries = []
    for family in QUERY_FAMILIES:
        for tmpl in templates[family]:
            text = tmpl.format(
                title=profile.title[:80], primary=primary_entity, affected=affected,
                topic=profile.topic, topic_lower=(profile.topic or "").lower(),
            ).strip()
            text = re.sub(r"\s+", " ", text)
            if not text:
                continue
            for lang in langs:
                queries.append(Query(text=text, family=family, language=lang))
                if profile.mode == MODE_STANDARD:
                    break  # STANDARD: only the top-priority language per query text

    # de-dupe, bound to the mode's budget (a budget, not a quota to fill - Part 5)
    seen, deduped = set(), []
    for q in queries:
        key = (q.text.lower(), q.language)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(q)
    deduped = deduped[:hi]
    return QueryPlan(event_id=profile.event_id, mode=profile.mode, queries=deduped)


# =====================================================================================
# Phase 6 - discovery (adapters live in pdi_providers.py; this stays provider-agnostic)
# =====================================================================================

def run_discovery(query_plan: QueryPlan, providers=None, budget_per_query=None):
    """Calls each registered provider adapter for each query, bounded per query. Fully
    permissive (Part 6): discovery does not judge relevance or trust, only normalizes.
    Any provider exception is caught here so one dead provider never aborts discovery for
    the others or for the run."""
    import pdi_providers
    providers = providers or pdi_providers.PROVIDERS
    budget = budget_per_query or CANDIDATE_BUDGET_PER_QUERY[query_plan.mode]
    candidates = []
    errors = []
    for q in query_plan.queries:
        for name, adapter in providers.items():
            try:
                found = adapter(q, limit=budget)
            except Exception as e:  # noqa: BLE001 - a provider failure must not abort discovery
                errors.append(f"{name}:{type(e).__name__}:{e}")
                continue
            for c in found:
                candidates.append(c)
    return candidates, errors


# =====================================================================================
# Phase 6 (cont.) / 7 - candidate filtering (cheap deterministic narrowing FIRST)
# =====================================================================================

_PROMO_RX = re.compile(
    r"\bsponsored\b|\bpromo code\b|\baffiliate link\b|\buse code\b|\bdiscount code\b|"
    r"\bswipe up\b|\blink in bio\b|\bsubscribe now\b.{0,20}\boff\b", re.I)
_LOW_CONTENT_RX = re.compile(r"^\s*\[(deleted|removed)\]\s*$", re.I)
MIN_CONTENT_CHARS = 40


def _canonical_url(url):
    url = (url or "").strip()
    url = re.sub(r"[?#].*$", "", url)   # drop query/fragment - tracking params aren't identity
    return url.rstrip("/").lower()


def filter_candidates(candidates, profile: DiscourseProfile, window_start, window_end):
    """Deterministic-only narrowing (Part 7 / Part 24: no semantic model here). Returns
    (kept, dropped_with_reason)."""
    seen_ids, seen_urls, kept, dropped = set(), set(), [], []
    lang_ok = set(profile.language_priorities) | {None, ""}
    profile_tokens = _tokens(" ".join([profile.title] + profile.core_entities + [profile.topic]))
    for c in candidates:
        c.canonical_url = _canonical_url(c.url)
        key_id = (c.provider, c.provider_item_id)
        if key_id in seen_ids or (c.canonical_url and c.canonical_url in seen_urls):
            dropped.append((c, "DUPLICATE"))
            continue
        seen_ids.add(key_id)
        if c.canonical_url:
            seen_urls.add(c.canonical_url)
        pub = _parse_ts(c.published_at)
        if pub is not None and not (window_start <= pub <= window_end):
            dropped.append((c, "OUT_OF_WINDOW"))
            continue
        if c.language and c.language not in lang_ok:
            dropped.append((c, "LANGUAGE_MISMATCH"))
            continue
        body = f"{c.title} {c.body_text}".strip()
        if _LOW_CONTENT_RX.match(c.title or "") or len(body) < MIN_CONTENT_CHARS:
            dropped.append((c, "LOW_CONTENT"))
            continue
        if _PROMO_RX.search(body):
            dropped.append((c, "PROMOTIONAL"))
            continue
        if jaccard(_tokens(body), profile_tokens) <= 0.0:
            dropped.append((c, "LEXICAL_IRRELEVANT"))
            continue
        c.content_hash = hashlib.sha256(body.lower().encode("utf-8", "replace")).hexdigest()[:24]
        kept.append(c)
    return kept, dropped


def _parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "").split("+")[0])
    except (ValueError, TypeError):
        return None


# =====================================================================================
# Phase 6 (cont.) / 8 - story association (conservative; temporal logic matters)
# =====================================================================================

RECENCY_DIRECT_MAX_DAYS = 10     # inside this window, a strong topical match can be DIRECT_EVENT
RELEVANCE_DIRECT_MIN = 0.30
RELEVANCE_RELATED_MIN = 0.12
RELEVANCE_BACKGROUND_MIN = 0.04

# Passage-level semantic similarity thresholds (bge-m3 cosine, via pdi_semantic.py).
# Calibrated against a labeled gold set of 18 cases (pdi_benchmark_association.py) -
# both synthetic adversarial cases AND real recurring candidates from the two live
# Substack shadow experiments (the "#360/#361/#362" false-positive posts, the
# India Judiciary Watch digest misapplied to an unrelated Naxal-conviction story, and
# the one plausibly-genuine Russia-sanctions candidate). NOT tuned to make a specific
# test pass - chosen as the values that best separate the labeled classes' real
# measured similarity distributions; the same real experiment then re-validates them
# on the held-out 12-story corpus (see the shadow-experiment report for those numbers,
# not just this gold set). Only meaningful on bge-m3's own scale - do not compare
# these to cluster.py's thresholds (different text genre: headline-vs-headline there,
# event-summary-vs-discourse-passage here).
SEM_DIRECT_MIN = 0.75
SEM_RELATED_MIN = 0.62
SEM_BACKGROUND_MIN = 0.50

# A semantic score that clears a threshold only marginally is DOMAIN relevance, not
# necessarily EVENT-SPECIFIC substantive relevance (final hardening pass, Part 11) -
# confirmed by the real 12-story experiment: a broad India Judiciary Watch weekly
# digest scored semantic=0.626 against event 18569 (barely above SEM_RELATED_MIN=
# 0.62) and was promoted to RELATED_CONTEXT/SELECTED, yet manually did not
# substantively discuss the specific event - its winning passage was a broad "the
# Supreme Court dealt with a wide spread of matters" summary sentence, not the
# judge's actual remarks. A comfortable margin above threshold is treated as
# sufficient evidence on its own (this is what lets genuine paraphrases/terminology
# variants/multilingual matches with NO lexical or entity overlap still reach
# DIRECT_EVENT/RELATED_CONTEXT - the entire point of adding semantic scoring); a
# MARGINAL score additionally requires deterministic corroboration (an actual
# entity-specific phrase hit, computed against the localized passage when one is
# available, or decent lexical relevance) before it can cross into
# DIRECT_EVENT/RELATED_CONTEXT. This is what distinguishes "touches the right broad
# subject" from "actually about this event," per the fix requirement - not achieved
# by raising SEM_RELATED_MIN itself, which would only shift the same problem to a
# new boundary rather than fixing the underlying decision rule.
SEM_MARGIN = 0.06

# Generic India-news vocabulary that would otherwise inflate relevance/specificity
# between two UNRELATED stories merely because both are India-focused (the same
# problem cluster.py's own _STOP set exists to solve for clustering - same failure
# mode, independently confirmed here in the real Substack experiments: e.g. the sole
# token shared between the "crude oil price" event and an unrelated "GDP debate"
# newsletter post was the word "india"). Deliberately NOT the general-purpose
# _STOPWORDS set above (that one must stay tiny/universal for filter_candidates and
# observation text) - this is specific to the relevance/specificity CALCULATION only.
_GENERIC_RELEVANCE_STOPWORDS = frozenset("""
    india indian govt government centre center minister ministry party parliament
    modi congress bjp court supreme delhi mumbai state national union today amid
    news report update says said asks seeks plans announces launches
""".split())


def _relevance_tokens(text):
    return _tokens(text) - _GENERIC_RELEVANCE_STOPWORDS


def _entity_specificity(candidate_text, profile: DiscourseProfile):
    """Deterministic event/entity specificity (Part 6's 'entity-aware matching'):
    does the candidate literally name one of THIS event's own extracted entity
    phrases (see _extract_entities), excluding the event's own region (e.g. "India"
    - present in nearly every India-focused candidate regardless of topic, so it
    carries no discriminating power; this mirrors _GENERIC_RELEVANCE_STOPWORDS above
    for the same reason). A phrase-level substring check, not bag-of-words overlap -
    "RBI" alone matching a completely different RBI story is NOT an entity hit here,
    only the full extracted phrase is. Returns (hit_count, considered_count)."""
    text_lower = (candidate_text or "").lower()
    region = (profile.region or "").strip().lower()
    considered = [e for e in profile.core_entities if e.strip().lower() != region]
    if not considered:
        return 0, 0
    hits = sum(1 for e in considered if e.lower() in text_lower)
    return hits, len(considered)


def _independence_score(candidate: Candidate):
    """Engagement volume never becomes independence (Part 9): a single Reddit thread
    with thousands of comments is still ONE candidate here (see pdi_providers.py's
    thread-to-representative-observations reduction) - this only distinguishes
    providers/authors, never raw comment/upvote counts."""
    return 1.0


def _source_quality_score(candidate: Candidate):
    if candidate.provider == PROVIDER_SUBSTACK:
        base = 0.7   # a written, authored piece - baseline higher than a forum comment
    else:
        base = 0.5
    if len(candidate.body_text or "") > 400:
        base += 0.2   # a substantive firsthand post outweighs a one-line comment (Part 20 case 6)
    return min(base, 1.0)


def _classify_deterministic(relevance, entity_hit_ratio, age_days):
    """The pure lexical/entity decision path - used whenever semantic scoring is
    unavailable (Ollama unreachable/not installed - pdi_semantic.is_available() is
    False) or not requested. This is the literal required fallback (Part 6.13): same
    thresholds and temporal logic as the original V1 implementation, with ONE
    evidence-driven change - the old BACKGROUND rule accepted ANY shared topic word
    (`jaccard(cand_tokens, topic_tokens) > 0`), which is what let a single recurring
    Substack post attach itself as "BACKGROUND" to several mutually unrelated
    real stories in both shadow experiments (root cause B). It's replaced by a real
    entity-specificity check: at least one of the EVENT's OWN extracted entity
    phrases must actually appear in the candidate, not merely a shared generic
    subject-matter word. This is strictly a precision improvement - it can only
    reject candidates the old rule wrongly accepted, never the reverse, since
    RELEVANCE_BACKGROUND_MIN's own OR-branch is unchanged."""
    if relevance >= RELEVANCE_DIRECT_MIN and (age_days is None or age_days <= RECENCY_DIRECT_MAX_DAYS):
        return ASSOCIATION_DIRECT_EVENT, "strong topical overlap within the discourse window"
    if relevance >= RELEVANCE_DIRECT_MIN and age_days is not None and age_days > RECENCY_DIRECT_MAX_DAYS:
        # Temporal logic matters (Part 8): strong topical match, but OLD - context, not the event itself.
        return ASSOCIATION_RELATED_CONTEXT, "topically strong but predates the discourse window (old context)"
    if relevance >= RELEVANCE_RELATED_MIN:
        return ASSOCIATION_RELATED_CONTEXT, "discusses the same underlying issue"
    if relevance >= RELEVANCE_BACKGROUND_MIN or entity_hit_ratio > 0:
        return ASSOCIATION_BACKGROUND, "general background on the topic only"
    return ASSOCIATION_UNRELATED, "no meaningful topical overlap"


def _classify_hybrid(relevance, entity_hit_ratio, semantic_score, age_days, require_corroboration=False):
    """Lexical + passage-level semantic decision path, used when a real semantic
    score is available (see pdi_semantic.py and associate_candidate's
    `semantic_score` parameter). Semantic similarity is passage-max-pooled, so it
    does not collapse as candidate documents grow the way whole-document Jaccard
    relevance does (the confirmed root cause of Experiment B's regression) - it is
    therefore the PRIMARY signal here, with the lexical relevance path kept as an
    alternate route so an exact/near-exact wording match (already correctly
    DIRECT_EVENT under the old logic) is never demoted just because semantic
    scoring happens to be available this run.

    entity_hit_ratio (computed by the caller against the LOCALIZED passage when one
    exists, not the whole document - see associate_candidate) plays two roles:
    - it can promote a candidate into BACKGROUND on real entity evidence alone, same
      as _classify_deterministic;
    - when require_corroboration=True (i.e. a specific passage was actually
      localized - see associate_candidate), it is the required CORROBORATION for a
      MARGINAL semantic score (within SEM_MARGIN of a threshold) to cross into
      DIRECT_EVENT/RELATED_CONTEXT - domain relevance alone is not enough at the
      margin when we know exactly which passage produced the score (see SEM_MARGIN's
      docstring). A COMFORTABLE semantic score (more than SEM_MARGIN above
      threshold) still needs no corroboration, which is what preserves genuine
      paraphrase/terminology/multilingual recovery (those cases have near-zero
      entity/lexical overlap by construction - that is the whole reason semantic
      scoring exists). When no specific passage was localized (require_corroboration
      =False - a bare semantic score with no passage attached), the margin/
      corroboration check is skipped entirely and the plain threshold applies,
      since there's no specific passage to second-guess against.
    Entity hits can never manufacture DIRECT_EVENT/RELATED_CONTEXT by themselves
    (Part 6's "same entity with same event" vs "same entity, different event"
    distinction) - they only ever corroborate an already-adequate semantic score."""
    corroborated = (not require_corroboration) or entity_hit_ratio > 0 or relevance >= RELEVANCE_RELATED_MIN

    direct_strength = (relevance >= RELEVANCE_DIRECT_MIN
                       or (semantic_score >= SEM_DIRECT_MIN
                           and (semantic_score >= SEM_DIRECT_MIN + SEM_MARGIN or corroborated)))
    related_strength = (relevance >= RELEVANCE_RELATED_MIN
                        or (semantic_score >= SEM_RELATED_MIN
                            and (semantic_score >= SEM_RELATED_MIN + SEM_MARGIN or corroborated)))
    background_strength = (semantic_score >= SEM_BACKGROUND_MIN or relevance >= RELEVANCE_BACKGROUND_MIN
                            or entity_hit_ratio > 0)
    tag = f"semantic={semantic_score:.3f}"
    if direct_strength and (age_days is None or age_days <= RECENCY_DIRECT_MAX_DAYS):
        return ASSOCIATION_DIRECT_EVENT, f"strong topical/semantic overlap within the discourse window ({tag})"
    if direct_strength and age_days is not None and age_days > RECENCY_DIRECT_MAX_DAYS:
        return ASSOCIATION_RELATED_CONTEXT, f"topically/semantically strong but predates the discourse window - old context ({tag})"
    if related_strength:
        return ASSOCIATION_RELATED_CONTEXT, f"discusses the same underlying issue ({tag})"
    if background_strength:
        return ASSOCIATION_BACKGROUND, f"general background on the topic only, not corroborated as event-specific ({tag})"
    return ASSOCIATION_UNRELATED, f"no meaningful topical or semantic overlap ({tag})"


def associate_candidate(candidate: Candidate, profile: DiscourseProfile, now,
                        semantic_score=None, relevant_passage=None) -> Association:
    """semantic_score: optional precomputed passage-max cosine similarity (see
    pdi_semantic.score_candidates(), called ONCE per run by run_pdi_for_event - not
    computed inside this function, so this stays cheap/pure/unit-testable and callers
    control exactly when a network-adjacent (local Ollama) call happens). Defaults to
    None, which reproduces the ORIGINAL deterministic-only behavior byte-for-byte -
    every existing caller/test that doesn't pass this argument is unaffected.

    relevant_passage: the specific passage text (see pdi_semantic.score_candidates's
    "passages" field) that produced semantic_score, when semantic scoring was used.
    Entity specificity is checked against THIS passage rather than the whole
    document when it's available - a document can name an entity anywhere (title,
    an unrelated section) without the passage that actually justified the semantic
    match discussing it, and it's the passage's own specificity that should
    corroborate (or fail to corroborate) a marginal semantic score (see SEM_MARGIN).
    Falls back to whole-document specificity when no passage is given, matching the
    pre-existing behavior exactly."""
    body = f"{candidate.title} {candidate.body_text}".strip()
    cand_tokens = _relevance_tokens(body)
    profile_tokens = _relevance_tokens(" ".join([profile.title, profile.summary] + profile.core_entities))
    relevance = jaccard(cand_tokens, profile_tokens)

    entity_hits, entity_considered = _entity_specificity(body, profile)
    entity_hit_ratio = (entity_hits / entity_considered) if entity_considered else 0.0

    if relevant_passage:
        passage_hits, passage_considered = _entity_specificity(
            f"{candidate.title} {relevant_passage}", profile)
        corroboration_ratio = (passage_hits / passage_considered) if passage_considered else 0.0
    else:
        corroboration_ratio = entity_hit_ratio

    pub = _parse_ts(candidate.published_at)
    age_days = (now - pub).total_seconds() / 86400.0 if pub else None
    recency = 0.5 ** (age_days / 14.0) if age_days is not None else 0.3  # unknown date: mild penalty, not zero

    source_quality = _source_quality_score(candidate)
    independence = _independence_score(candidate)

    if semantic_score is None:
        association, reason = _classify_deterministic(relevance, entity_hit_ratio, age_days)
        effective_relevance = relevance
    else:
        association, reason = _classify_hybrid(relevance, corroboration_ratio, semantic_score, age_days,
                                                require_corroboration=bool(relevant_passage))
        effective_relevance = max(relevance, semantic_score)
        if relevant_passage:
            reason = f"{reason}; passage={relevant_passage[:160]!r}"

    association_score = round(0.5 * effective_relevance + 0.2 * entity_hit_ratio
                              + 0.15 * source_quality + 0.15 * recency, 4)
    quality_status = QUALITY_SELECTED if association in (ASSOCIATION_DIRECT_EVENT, ASSOCIATION_RELATED_CONTEXT) else QUALITY_REJECTED
    return Association(
        candidate=candidate, association=association, association_score=association_score,
        relevance_score=round(relevance, 4), specificity_score=round(entity_hit_ratio, 4),
        source_quality_score=round(source_quality, 4), independence_score=round(independence, 4),
        recency_score=round(recency, 4), quality_status=quality_status, reason=reason,
        relevant_passage=relevant_passage or "",
    )


# =====================================================================================
# Phase 9 - quality / selection (independence over volume; penalize duplicates/derivative)
# =====================================================================================

NEAR_DUP_JACCARD = 0.85
MAX_SELECTED_PER_RUN = {MODE_STANDARD: 25, MODE_DEEP: 60}


def select_quality_candidates(associations, mode):
    """From SELECTED-status associations, drop near-duplicate/derivative bodies (copied
    Substacks, reposted threads) and cap total selection. Independence, not volume:
    ranks by association_score but a near-duplicate of an already-kept item is rejected
    regardless of its own score."""
    selected = [a for a in associations if a.quality_status == QUALITY_SELECTED]
    selected.sort(key=lambda a: a.association_score, reverse=True)
    kept, kept_token_sets = [], []
    cap = MAX_SELECTED_PER_RUN[mode]
    for a in selected:
        if len(kept) >= cap:
            a.quality_status = QUALITY_REJECTED
            a.reason = "over selection cap"
            continue
        body_tokens = _tokens(f"{a.candidate.title} {a.candidate.body_text}")
        is_dup = any(jaccard(body_tokens, kt) >= NEAR_DUP_JACCARD for kt in kept_token_sets)
        if is_dup:
            a.quality_status = QUALITY_REJECTED
            a.reason = "near-duplicate/derivative of an already-selected candidate"
            continue
        kept.append(a)
        kept_token_sets.append(body_tokens)
    return kept


# =====================================================================================
# Phase 7 (cont.) - observation extraction (ATOMIC, typed; repeated != factual)
# =====================================================================================

_SENT_SPLIT_RX = re.compile(r"(?<=[.!?])\s+|\n+")

_OBS_CUES = [
    (OBS_QUESTION, re.compile(r"\?\s*$")),
    # NOTE: bare "actually" was removed from this list (benchmark finding, hardening
    # pass) - it's a generic intensifier ("will this ACTUALLY work", "unclear whether
    # this will ACTUALLY reduce prices"), not a disagreement-specific word, and being
    # checked before UNCERTAINTY/QUESTION was mis-classifying plain questions and hedged
    # statements as DISAGREEMENT whenever they merely contained "actually".
    (OBS_DISAGREEMENT, re.compile(r"\bdisagree|\bnot true\b|that'?s wrong|\bincorrect\b|contrary to|however,? ", re.I)),
    (OBS_UNCERTAINTY, re.compile(r"\b(might|may|unclear|not sure|uncertain|possibly|perhaps|unverified|hard to say)\b", re.I)),
    (OBS_CONCERN, re.compile(r"\b(worried|concern(ed)?|fear|risk|problem|afraid)\b", re.I)),
    (OBS_IMPLICATION, re.compile(r"\b(could lead to|as a result|this means|will (likely )?(affect|impact)|knock-on effect)\b", re.I)),
    (OBS_INTERPRETATION, re.compile(r"\b(argue[sd]?|suggests?|implies?|means that|reads? as|framing)\b", re.I)),
    (OBS_EXPERIENCE, re.compile(r"\b(i |i'm |i've |my |we |our |personally|in my experience)\b", re.I)),
]


def extract_observations(association: Association, max_per_candidate=3):
    """ATOMIC observation extraction, pattern-based and deterministic (Part 24: no LLM
    call is required and none is used here). A recurring claim is stored as a
    recurring OBSERVATION, never promoted to a fact/importance/truth signal - there is
    no code path in this module that could do that (see OBSERVATION_TYPES).

    Operates on association.relevant_passage when the association was reached via
    semantic scoring, NOT the whole candidate document (hardening-pass Finding F: the
    real 12-story experiment's one SELECTED candidate was a broad weekly digest whose
    semantic match came from one passage about the target event, but observation
    extraction previously processed the ENTIRE document and produced observations
    about a completely different, unrelated court matter mentioned elsewhere in the
    same digest). Falls back to the whole document when no passage was localized
    (the deterministic-only path, where whole-document Jaccard is itself what judged
    relevance, so there is no narrower material to prefer)."""
    if association.quality_status != QUALITY_SELECTED:
        return []
    body_text = association.relevant_passage or association.candidate.body_text
    text = f"{association.candidate.title}. {body_text}"
    sentences = [s.strip() for s in _SENT_SPLIT_RX.split(text) if s.strip()]
    out = []
    for s in sentences:
        if len(s) < 15:
            continue
        obs_type = OBS_THEME
        for t, rx in _OBS_CUES:
            if rx.search(s):
                obs_type = t
                break
        h = hashlib.sha256(re.sub(r"\s+", " ", s.lower()).encode("utf-8", "replace")).hexdigest()[:24]
        confidence = min(0.9, 0.4 + 0.1 * min(len(s.split()), 5))
        out.append(Observation(candidate=association.candidate, observation_type=obs_type, text=s,
                                observation_hash=h, cluster_key="", confidence=round(confidence, 3)))
        if len(out) >= max_per_candidate:
            break
    return out


# =====================================================================================
# Phase 7 (cont.) - cross-source clustering (semantically equivalent, provenance kept)
# =====================================================================================

CLUSTER_JACCARD = 0.45


def cluster_observations(observations):
    """Groups semantically-similar SAME-TYPE observations. Returns a list of clusters:
    {"cluster_key", "observation_type", "representative_text", "members": [Observation,...]}.
    Provenance is preserved per member (candidate/provider/discovery_query/time) - never
    collapsed into an anonymous sentence (Part 11)."""
    by_type = {}
    for o in observations:
        by_type.setdefault(o.observation_type, []).append(o)
    clusters = []
    for obs_type, obs_list in by_type.items():
        assigned = [False] * len(obs_list)
        tok_cache = [_tokens(o.text) for o in obs_list]
        for i, o in enumerate(obs_list):
            if assigned[i]:
                continue
            members = [o]
            assigned[i] = True
            for j in range(i + 1, len(obs_list)):
                if assigned[j]:
                    continue
                if jaccard(tok_cache[i], tok_cache[j]) >= CLUSTER_JACCARD:
                    members.append(obs_list[j])
                    assigned[j] = True
            key = hashlib.sha256(f"{obs_type}:{members[0].text.lower()}".encode("utf-8", "replace")).hexdigest()[:16]
            for m in members:
                m.cluster_key = key
            clusters.append({
                "cluster_key": key, "observation_type": obs_type,
                "representative_text": members[0].text,
                "members": members,
            })
    return clusters


def _cluster_provenance(cluster):
    providers = sorted({m.candidate.provider for m in cluster["members"]})
    candidate_ids = sorted({m.candidate.provider_item_id for m in cluster["members"]})
    queries = sorted({m.candidate.discovery_query for m in cluster["members"] if m.candidate.discovery_query})
    return {"providers": providers, "candidate_ids": candidate_ids, "discovery_queries": queries,
            "source_count": len(candidate_ids), "provider_count": len(providers)}


# =====================================================================================
# Phase 12 - coverage gaps
# =====================================================================================

MIN_RECURRENCE_FOR_GAP = 2
MIN_PROVIDER_DIVERSITY_FOR_GAP = 1


def _framing_text(event):
    """event['framing'] (database.get_event's real shape) is {side: [str, ...]} - a LIST
    of framing sentences per side, not a single string per side. Defensively handles a
    plain-string value too, since this is reading data this module does not own."""
    framing = event.get("framing")
    if not isinstance(framing, dict):
        return ""
    parts = []
    for v in framing.values():
        if isinstance(v, list):
            parts.extend(str(x) for x in v)
        elif isinstance(v, str):
            parts.append(v)
    return " ".join(parts)


def find_coverage_gaps(question_clusters, event):
    """recurring question -> compare with Paksh's own evidence (title+summary+framing
    text) -> already answered => not a gap; not answered => candidate gap. A single
    unusual question is not automatically a gap (Part 12) - recurrence/diversity gate."""
    existing_text = " ".join(filter(None, [event.get("title"), event.get("summary"), _framing_text(event)]))
    existing_tokens = _tokens(existing_text)
    gaps = []
    for c in question_clusters:
        prov = _cluster_provenance(c)
        if len(c["members"]) < MIN_RECURRENCE_FOR_GAP and prov["provider_count"] < 2:
            continue
        q_tokens = _tokens(c["representative_text"])
        answered = jaccard(q_tokens, existing_tokens) >= 0.25
        if not answered:
            gaps.append({"question": c["representative_text"], "recurrence": len(c["members"]),
                         "provider_diversity": prov["provider_count"], "provenance": prov})
    return gaps


# =====================================================================================
# Phase 8 - story payload (compact; NO raw external content, queries, or engagement)
# =====================================================================================

def _cluster_summary(c, min_members=1):
    prov = _cluster_provenance(c)
    return {"text": c["representative_text"], "recurrence": len(c["members"]),
            "source_count": prov["source_count"], "provider_count": prov["provider_count"]}


def build_story_pdi(event_id, clusters, coverage_gaps) -> StoryPDI:
    by_type = {}
    for c in clusters:
        by_type.setdefault(c["observation_type"], []).append(c)

    def top(obs_type, n=8):
        items = sorted(by_type.get(obs_type, []), key=lambda c: -len(c["members"]))
        return [_cluster_summary(c) for c in items[:n]]

    themes = top(OBS_THEME)
    questions = top(OBS_QUESTION)
    interpretations = top(OBS_INTERPRETATION)
    experiences = top(OBS_EXPERIENCE)
    disagreements = top(OBS_DISAGREEMENT)
    uncertainties = top(OBS_UNCERTAINTY)
    implications = top(OBS_IMPLICATION)

    total_items = sum(len(v) for v in (themes, questions, interpretations, experiences,
                                        disagreements, uncertainties, implications, coverage_gaps))
    if total_items == 0:
        contribution = "No meaningful additional understanding was identified beyond the existing reporting corpus."
    else:
        parts = []
        if disagreements:
            parts.append(f"{len(disagreements)} point(s) of disagreement")
        if coverage_gaps:
            parts.append(f"{len(coverage_gaps)} recurring question(s) not yet answered by existing coverage")
        if interpretations:
            parts.append(f"{len(interpretations)} independent interpretation(s)")
        if experiences:
            parts.append(f"{len(experiences)} firsthand account(s)")
        if themes and not parts:
            parts.append(f"{len(themes)} recurring theme(s)")
        contribution = ("Public discourse surfaces " + "; ".join(parts) +
                         " not fully captured by the existing reporting corpus.") if parts else \
                        "Public discourse largely mirrors the existing reporting corpus."

    return StoryPDI(
        event_id=event_id, recurring_themes=themes, recurring_questions=questions,
        interpretations=interpretations, experiences=experiences, disagreements=disagreements,
        uncertainties=uncertainties, implications=implications, coverage_gaps=coverage_gaps,
        understanding_contribution=contribution,
    )


# =====================================================================================
# PDI -> analyze.py contract (final campaign, Phase 7/8): the ONLY function analyze.py
# is allowed to call. Renders a compact, human-readable text block from a StoryPDI
# payload - NEVER raw candidate/provider content, discovery queries, engagement
# counts, or full external documents (Part 18's explicit "must NOT receive" list).
# Returns None (not an empty string) when there is nothing worth surfacing, so
# analyze.py's build_prompt() can skip the block entirely rather than emit an empty
# section - "when there is nothing to add, PDI should quietly say so" applies at this
# boundary too, not only inside PDI's own status codes.
# =====================================================================================

def format_payload_for_analyze(payload: "StoryPDI") -> str | None:
    """The compact PUBLIC DISCOURSE INTELLIGENCE block. Every item here already
    passed the full pipeline (discovery -> deterministic filtering -> event-specific
    + semantic association -> corroboration-margin quality gate -> passage-localized
    observation extraction -> cross-source clustering) - this function does no
    further judgment, it only formats. Deliberately excludes: engagement/score
    numbers, provider names, discovery queries, raw URLs in the body text (provenance
    stays in pdi_* tables for audit, not in what the model sees) - analyze.py gets
    understanding, not a reading list."""
    if payload is None:
        return None
    sections = [
        ("Recurring themes", payload.recurring_themes),
        ("Recurring questions", payload.recurring_questions),
        ("Meaningful interpretations", payload.interpretations),
        ("Reported experiences", payload.experiences),
        ("Meaningful disagreements", payload.disagreements),
        ("Uncertainties", payload.uncertainties),
    ]
    gap_texts = [g.get("question") for g in (payload.coverage_gaps or []) if g.get("question")]
    if not any(items for _, items in sections) and not payload.implications and not gap_texts:
        return None   # nothing survived to SELECTED for this run - say nothing, not "nothing found"

    lines = ["PUBLIC DISCOURSE INTELLIGENCE", ""]
    for label, items in sections:
        if not items:
            continue
        lines.append(f"{label}:")
        for it in items:
            lines.append(f"- {it['text']}")
        lines.append("")
    if payload.implications:
        lines.append("Potential implications (as raised in discourse, not established fact):")
        for it in payload.implications:
            lines.append(f"- {it['text']}")
        lines.append("")
    if gap_texts:
        lines.append("Potential coverage gaps (recurring questions not yet answered by existing coverage):")
        for q in gap_texts:
            lines.append(f"- {q}")
        lines.append("")
    lines.append(f"Understanding contribution: {payload.understanding_contribution}")
    return "\n".join(lines)


# =====================================================================================
# Phase 1 - persistence (additive, isolated, idempotent, versioned)
# Same convention as story_intelligence.py's own _SCHEMA/init_si_schema: a single
# executescript() of CREATE TABLE/INDEX IF NOT EXISTS statements, called lazily. Never
# touches events/articles/si_*/homepage/section tables - only the pdi_* tables below.
# =====================================================================================

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pdi_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    mode TEXT,
    pdi_version TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL,
    run_started_at TEXT NOT NULL,
    run_completed_at TEXT,
    discourse_window_start TEXT,
    discourse_window_end TEXT,
    candidate_count INTEGER DEFAULT 0,
    selected_candidate_count INTEGER DEFAULT 0,
    observation_count INTEGER DEFAULT 0,
    error_code TEXT,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_pdi_runs_event ON pdi_runs(event_id);
CREATE INDEX IF NOT EXISTS idx_pdi_runs_event_status ON pdi_runs(event_id, status);

CREATE TABLE IF NOT EXISTS pdi_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES pdi_runs(id),
    provider TEXT NOT NULL,
    provider_item_id TEXT NOT NULL,
    url TEXT,
    canonical_url TEXT,
    title TEXT,
    author TEXT,
    published_at TEXT,
    language TEXT,
    discovery_query TEXT,
    discovery_rank INTEGER,
    content_hash TEXT,
    discovered_at TEXT NOT NULL,
    UNIQUE(run_id, provider, provider_item_id)
);
CREATE INDEX IF NOT EXISTS idx_pdi_candidates_run ON pdi_candidates(run_id);

CREATE TABLE IF NOT EXISTS pdi_associations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES pdi_runs(id),
    candidate_id INTEGER NOT NULL REFERENCES pdi_candidates(id),
    association TEXT NOT NULL,
    association_score REAL,
    relevance_score REAL,
    specificity_score REAL,
    source_quality_score REAL,
    independence_score REAL,
    recency_score REAL,
    quality_status TEXT NOT NULL,
    reason TEXT,
    UNIQUE(run_id, candidate_id)
);
CREATE INDEX IF NOT EXISTS idx_pdi_assoc_run ON pdi_associations(run_id);

CREATE TABLE IF NOT EXISTS pdi_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES pdi_runs(id),
    candidate_id INTEGER NOT NULL REFERENCES pdi_candidates(id),
    observation_type TEXT NOT NULL,
    text TEXT NOT NULL,
    observation_hash TEXT NOT NULL,
    cluster_key TEXT,
    confidence REAL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pdi_obs_run ON pdi_observations(run_id);
CREATE INDEX IF NOT EXISTS idx_pdi_obs_cluster ON pdi_observations(run_id, cluster_key);

CREATE TABLE IF NOT EXISTS pdi_story_payload (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES pdi_runs(id),
    event_id INTEGER NOT NULL,
    recurring_themes TEXT,
    recurring_questions TEXT,
    interpretations TEXT,
    experiences TEXT,
    disagreements TEXT,
    uncertainties TEXT,
    implications TEXT,
    coverage_gaps TEXT,
    understanding_contribution TEXT,
    payload_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(run_id)
);
CREATE INDEX IF NOT EXISTS idx_pdi_payload_event ON pdi_story_payload(event_id);
"""

PDI_TABLES = ["pdi_runs", "pdi_candidates", "pdi_associations", "pdi_observations", "pdi_story_payload"]

PAYLOAD_VERSION = "pdi-payload-v1"


def init_pdi_schema(conn):
    conn.execute("PRAGMA foreign_keys = ON")   # per-connection; does not touch database.py's own PRAGMAs
    conn.executescript(_SCHEMA)
    conn.commit()


# --- input fingerprint (Part 17) -------------------------------------------------------

def compute_input_fingerprint(event, article_ids, si_input_sig=None):
    """Deterministic fingerprint over ONLY the fields PDI actually depends on. Explicitly
    excludes image_url, title_hi/summary_hi (translations), summary_points (PDI never
    reads it), export position, created_at, and any other cosmetic/presentation field -
    the same "what does this module actually read" discipline as story_intelligence.py's
    input_signature(). created_at is NEVER a semantic input here (Part 16/17): recount/
    update behavior can touch it without changing anything PDI cares about, so it must
    not cause a spurious STALE.

    Fingerprint-audit fix (hardening pass): `framing` was read by find_coverage_gaps()
    (via _framing_text()) but was missing from this fingerprint entirely - a substantive
    reframe.py rewrite of the per-side framing text could silently leave a stale
    coverage-gap conclusion (computed against the OLD framing) marked VALID forever.
    Added below."""
    h = hashlib.sha256()
    h.update(PDI_VERSION.encode())
    h.update(f"|id:{event.get('id')}".encode())
    h.update(f"|title:{event.get('title') or ''}".encode("utf-8", "replace"))
    h.update(f"|summary:{event.get('summary') or ''}".encode("utf-8", "replace"))
    h.update(f"|topic:{event.get('topic') or ''}".encode("utf-8", "replace"))
    h.update(f"|region:{event.get('region') or ''}".encode("utf-8", "replace"))
    h.update(f"|framing:{_framing_text(event)}".encode("utf-8", "replace"))
    h.update(f"|si:{si_input_sig or ''}".encode())
    h.update(f"|articles:{','.join(str(i) for i in sorted(article_ids))}".encode())
    return h.hexdigest()[:32]


def _fetch_si_input_sig(conn, event_id):
    try:
        row = conn.execute("SELECT input_sig FROM si_story_state WHERE event_id=?", (event_id,)).fetchone()
        return row["input_sig"] if row else None
    except Exception:
        return None   # si_* tables may not exist yet on a fresh DB - fingerprint just omits this input


# --- run lifecycle (Part 16) ------------------------------------------------------------

def get_latest_run(conn, event_id, statuses=None):
    statuses = statuses or (RUN_VALID, RUN_STALE, RUN_NO_MEANINGFUL_DISCOURSE, RUN_INSUFFICIENT_EVIDENCE, RUN_FAILED)
    ph = ",".join("?" * len(statuses))
    row = conn.execute(
        f"SELECT * FROM pdi_runs WHERE event_id=? AND status IN ({ph}) "
        f"ORDER BY id DESC LIMIT 1", (event_id, *statuses)).fetchone()
    return row


def get_run_history(conn, event_id):
    """All historical runs for an event, newest first - old PDI is never destroyed (Part 16)."""
    return conn.execute("SELECT * FROM pdi_runs WHERE event_id=? ORDER BY id DESC", (event_id,)).fetchall()


def _mark_stale(conn, run_id):
    conn.execute("UPDATE pdi_runs SET status=? WHERE id=? AND status=?", (RUN_STALE, run_id, RUN_VALID))
    conn.commit()


def _supersede_stale(conn, event_id, new_run_id):
    """After a NEW run becomes VALID, any STALE predecessor for the same event is marked
    SUPERSEDED (Part 16: 'old run -> STALE, new run -> VALID, old run -> SUPERSEDED').
    Historical rows are kept, never deleted."""
    conn.execute("UPDATE pdi_runs SET status=? WHERE event_id=? AND status=? AND id != ?",
                 (RUN_SUPERSEDED, event_id, RUN_STALE, new_run_id))
    conn.commit()


def check_freshness(conn, event_id, fingerprint):
    """READ-ONLY (hardening fix - this used to mutate the row to STALE as a side effect,
    which meant even a persist=False dry run could silently change database state; a
    dry run must be exactly as side-effect-free as story_intelligence.py's own default
    --persist-gated CLI convention). Returns ('FRESH', valid_row) if an up-to-date VALID
    run already exists (no work needed), ('STALE', row) if the most recent run's input no
    longer matches OR is already STALE, or ('NONE', None) if the event has never been
    PDI-processed. The actual STALE/SUPERSEDED status transition is applied by the CALLER
    (run_pdi_for_event) ONLY when persist=True AND the replacement run actually succeeds -
    see that function's docstring for why the transition is deliberately deferred."""
    row = get_latest_run(conn, event_id, statuses=(RUN_VALID, RUN_STALE))
    if row is None:
        return "NONE", None
    if row["status"] == RUN_VALID and row["input_fingerprint"] == fingerprint and row["pdi_version"] == PDI_VERSION:
        return "FRESH", row
    return "STALE", row


# --- writes (one transaction per run, same discipline as story_intelligence.persist_story) --

def _insert_run(conn, event_id, mode, fingerprint, window_start, window_end, now):
    cur = conn.execute(
        "INSERT INTO pdi_runs (event_id, status, mode, pdi_version, input_fingerprint, "
        "run_started_at, discourse_window_start, discourse_window_end) VALUES (?,?,?,?,?,?,?,?)",
        (event_id, RUN_RUNNING, mode, PDI_VERSION, fingerprint, _iso(now),
         _iso(window_start), _iso(window_end)))
    conn.commit()
    return cur.lastrowid


def _finalize_run(conn, run_id, status, candidate_count=0, selected_count=0, observation_count=0,
                   error_code=None, error_message=None, now=None):
    now = now or _now()
    conn.execute(
        "UPDATE pdi_runs SET status=?, run_completed_at=?, candidate_count=?, "
        "selected_candidate_count=?, observation_count=?, error_code=?, error_message=? WHERE id=?",
        (status, _iso(now), candidate_count, selected_count, observation_count,
         error_code, error_message, run_id))
    conn.commit()


def _persist_candidates(conn, run_id, candidates, now):
    id_by_key = {}
    for c in candidates:
        cur = conn.execute(
            "INSERT OR IGNORE INTO pdi_candidates (run_id, provider, provider_item_id, url, "
            "canonical_url, title, author, published_at, language, discovery_query, "
            "discovery_rank, content_hash, discovered_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, c.provider, c.provider_item_id, c.url, c.canonical_url, c.title, c.author,
             c.published_at, c.language, c.discovery_query, c.discovery_rank, c.content_hash, _iso(now)))
        if cur.lastrowid:
            row_id = cur.lastrowid
        else:
            row_id = conn.execute(
                "SELECT id FROM pdi_candidates WHERE run_id=? AND provider=? AND provider_item_id=?",
                (run_id, c.provider, c.provider_item_id)).fetchone()["id"]
        id_by_key[(c.provider, c.provider_item_id)] = row_id
    conn.commit()
    return id_by_key


def _persist_associations(conn, run_id, associations, cand_ids):
    for a in associations:
        key = (a.candidate.provider, a.candidate.provider_item_id)
        cid = cand_ids.get(key)
        if cid is None:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO pdi_associations (run_id, candidate_id, association, "
            "association_score, relevance_score, specificity_score, source_quality_score, "
            "independence_score, recency_score, quality_status, reason) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, cid, a.association, a.association_score, a.relevance_score, a.specificity_score,
             a.source_quality_score, a.independence_score, a.recency_score, a.quality_status, a.reason))
    conn.commit()


def _persist_observations(conn, run_id, observations, cand_ids, now):
    for o in observations:
        key = (o.candidate.provider, o.candidate.provider_item_id)
        cid = cand_ids.get(key)
        if cid is None:
            continue
        conn.execute(
            "INSERT INTO pdi_observations (run_id, candidate_id, observation_type, text, "
            "observation_hash, cluster_key, confidence, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (run_id, cid, o.observation_type, o.text, o.observation_hash, o.cluster_key,
             o.confidence, _iso(now)))
    conn.commit()


def _payload_to_row(payload: StoryPDI):
    return {
        "recurring_themes": json.dumps(payload.recurring_themes, ensure_ascii=False),
        "recurring_questions": json.dumps(payload.recurring_questions, ensure_ascii=False),
        "interpretations": json.dumps(payload.interpretations, ensure_ascii=False),
        "experiences": json.dumps(payload.experiences, ensure_ascii=False),
        "disagreements": json.dumps(payload.disagreements, ensure_ascii=False),
        "uncertainties": json.dumps(payload.uncertainties, ensure_ascii=False),
        "implications": json.dumps(payload.implications, ensure_ascii=False),
        "coverage_gaps": json.dumps(payload.coverage_gaps, ensure_ascii=False),
    }


def _persist_payload(conn, run_id, event_id, payload: StoryPDI, now):
    row = _payload_to_row(payload)
    conn.execute(
        "INSERT OR REPLACE INTO pdi_story_payload (run_id, event_id, recurring_themes, "
        "recurring_questions, interpretations, experiences, disagreements, uncertainties, "
        "implications, coverage_gaps, understanding_contribution, payload_version, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (run_id, event_id, row["recurring_themes"], row["recurring_questions"], row["interpretations"],
         row["experiences"], row["disagreements"], row["uncertainties"], row["implications"],
         row["coverage_gaps"], payload.understanding_contribution, PAYLOAD_VERSION, _iso(now)))
    conn.commit()


def get_story_payload(conn, run_id):
    row = conn.execute("SELECT * FROM pdi_story_payload WHERE run_id=?", (run_id,)).fetchone()
    if not row:
        return None
    out = dict(row)
    for k in ("recurring_themes", "recurring_questions", "interpretations", "experiences",
              "disagreements", "uncertainties", "implications", "coverage_gaps"):
        out[k] = json.loads(out[k]) if out[k] else []
    return out


# =====================================================================================
# Phase 9 - orchestration / runner (replayable, non-fatal, isolated from live.py)
# =====================================================================================

def run_pdi_for_event(event_id, force=False, persist=False, now=None, providers=None):
    """The whole pipeline for ONE event. Never raises - any failure is captured into the
    run's own status/error fields (Part 23) so a PDI failure can never propagate into
    ingest/cluster/analyze/export/live. Read-only (nothing written to pdi_* tables)
    unless persist=True, matching story_intelligence.py's own --persist convention."""
    import database
    import homepage_rank as hr

    now = now or _now()
    result = {"event_id": event_id, "status": None, "mode": None, "reason": None}
    conn = database.get_connection()
    try:
        event = database.get_event(event_id)
        if not event:
            result["status"] = "EVENT_NOT_FOUND"
            return result

        articles = database.get_articles_for_events([event_id]).get(event_id, [])
        article_ids = [a["id"] for a in articles]
        article_languages = [a.get("language") for a in articles]

        si_map = hr.fetch_si_signals(conn, [event_id])
        vel_map = hr.fetch_velocity_signals(conn, [event_id], now)
        si = si_map.get(event_id, {"independent_count": 0, "dev_count": 0, "latest_dev_time": None, "has_si": False})
        velocity = vel_map.get(event_id, {"owners_total": 0, "owners_recent": 0})

        mode, elig_reason = determine_eligibility(event, si, velocity, now)
        result["mode"] = mode
        result["reason"] = elig_reason
        if mode is None:
            result["status"] = "NOT_ELIGIBLE"
            return result   # PDI must not run for every event (Part 3) - no run row created

        si_sig = _fetch_si_input_sig(conn, event_id)
        fingerprint = compute_input_fingerprint(event, article_ids, si_sig)

        init_pdi_schema(conn)
        state, row = check_freshness(conn, event_id, fingerprint)
        if not force and state == "FRESH":
            result["status"] = RUN_VALID
            result["run_id"] = row["id"]
            result["reused_existing_run"] = True
            return result
        # The prior VALID run (if any) is retired (STALE -> SUPERSEDED) ONLY once we know
        # the replacement actually succeeds - see the persist block below. Hardening fix:
        # the previous version marked it STALE HERE, before discovery even ran, so a
        # forced re-run that then failed (NO_MEANINGFUL_DISCOURSE/INSUFFICIENT_EVIDENCE/
        # FAILED) left the event with NO current VALID run at all, even though nothing
        # had actually replaced the last good one - "a failed replacement does not
        # destroy the last successful historical run" (lifecycle audit, Part 2) means the
        # old run must still be the CURRENT answer, not merely preserved-but-demoted, when
        # its replacement doesn't pan out. A genuinely stale row (row["status"] already
        # STALE, or fingerprint already known to differ) is left exactly as check_freshness
        # reported it - only a currently-VALID row's retirement is deferred.
        prior_valid_run_id = row["id"] if (row is not None and row["status"] == RUN_VALID) else None

        window_days = DISCOURSE_WINDOW_DAYS[mode]
        window_end = now
        window_start = now - timedelta(days=window_days)

        run_id = None
        if persist:
            run_id = _insert_run(conn, event_id, mode, fingerprint, window_start, window_end, now)

        profile = build_discourse_profile(event, article_languages, mode)
        query_plan = generate_query_plan(profile)
        candidates, discovery_errors = run_discovery(query_plan, providers=providers)
        kept, dropped = filter_candidates(candidates, profile, window_start, window_end)

        # Passage-level semantic scoring (Part 24 cont.): ONE batched call for the
        # event representation + ONE batched call for every kept candidate's passages
        # (see pdi_semantic.score_candidates - never one call per candidate). Fully
        # optional and non-fatal: an unreachable/unavailable Ollama makes this an
        # empty dict, and every associate_candidate() call below then silently uses
        # its pure deterministic fallback - no exception, no behavior change beyond
        # that fallback, exactly the "what happens when semantic infra is
        # unavailable" contract this module documents.
        import pdi_semantic
        event_text = f"{profile.title}. {profile.summary}"
        semantic_results = pdi_semantic.score_candidates(
            event_text, [(id(c), f"{c.title}. {c.body_text}") for c in kept])

        def _associate(c):
            r = semantic_results.get(id(c))
            if r is None:
                return associate_candidate(c, profile, now)
            passage = " ".join(r["passages"]) if r["passages"] else None
            return associate_candidate(c, profile, now, semantic_score=r["score"], relevant_passage=passage)

        associations = [_associate(c) for c in kept]
        selected = select_quality_candidates(associations, mode)

        observations = []
        for a in selected:
            observations.extend(extract_observations(a))
        clusters = cluster_observations(observations)
        question_clusters = [c for c in clusters if c["observation_type"] == OBS_QUESTION]
        coverage_gaps = find_coverage_gaps(question_clusters, event)
        payload = build_story_pdi(event_id, clusters, coverage_gaps)

        if len(candidates) == 0:
            status = RUN_NO_MEANINGFUL_DISCOURSE
            error_code = "DISCOVERY_UNAVAILABLE" if discovery_errors and len(discovery_errors) >= len(query_plan.queries) else None
        elif len(selected) == 0 or len(observations) == 0:
            status = RUN_INSUFFICIENT_EVIDENCE
            error_code = None
        else:
            status = RUN_VALID
            error_code = None

        result.update({
            "status": status, "candidate_count": len(candidates), "kept_count": len(kept),
            "selected_candidate_count": len(selected), "observation_count": len(observations),
            "cluster_count": len(clusters), "association_distribution": _assoc_distribution(associations),
            "discovery_errors": discovery_errors, "payload": payload, "profile": profile,
            "query_plan": query_plan,
        })

        if persist and run_id is not None:
            cand_ids = _persist_candidates(conn, run_id, kept, now)
            _persist_associations(conn, run_id, associations, cand_ids)
            _persist_observations(conn, run_id, observations, cand_ids, now)
            _persist_payload(conn, run_id, event_id, payload, now)
            _finalize_run(conn, run_id, status, candidate_count=len(candidates),
                          selected_count=len(selected), observation_count=len(observations),
                          error_code=error_code, now=now)
            if status == RUN_VALID:
                # Only now, with a genuine successful replacement in hand, retire the
                # prior VALID run (if there was one) and sweep any already-STALE
                # predecessors to SUPERSEDED in the same step - see the comment above
                # for why this is deferred this far rather than done eagerly.
                if prior_valid_run_id is not None:
                    _mark_stale(conn, prior_valid_run_id)
                _supersede_stale(conn, event_id, run_id)
            result["run_id"] = run_id
        return result
    except Exception as e:  # noqa: BLE001 - PDI failure must never propagate (Part 23)
        try:
            failed_run_id = locals().get("run_id")
            if persist and failed_run_id is not None:
                _finalize_run(conn, failed_run_id, RUN_FAILED, error_code=type(e).__name__, error_message=str(e), now=now)
        except Exception:
            pass
        result["status"] = RUN_FAILED
        result["error"] = f"{type(e).__name__}: {e}"
        return result
    finally:
        conn.close()


def _assoc_distribution(associations):
    dist = {k: 0 for k in ASSOCIATION_CLASSES}
    for a in associations:
        dist[a.association] = dist.get(a.association, 0) + 1
    return dist


def eligible_event_ids(conn, limit=50, days=14):
    """Candidate pool for `pdi.py --eligible`: recent, publishable events - reuses
    Story Intelligence's own recent-window helper rather than a new query (Part 3/21)."""
    import story_intelligence as si_mod
    return si_mod.recent_event_ids(conn, days=days, limit=limit)


def run_pdi_eligible(limit=50, days=14, persist=False, now=None):
    """`pdi.py --eligible`: run the SAME per-event pipeline over the recent-events pool,
    skipping ones the eligibility gate rejects. Bounded, non-fatal per event."""
    import database
    now = now or _now()
    conn = database.get_connection()
    ids = eligible_event_ids(conn, limit=limit, days=days)
    conn.close()
    summary = {"considered": len(ids), "eligible": 0, "not_eligible": 0, "results": []}
    for eid in ids:
        r = run_pdi_for_event(eid, persist=persist, now=now)
        summary["results"].append(r)
        if r["status"] == "NOT_ELIGIBLE":
            summary["not_eligible"] += 1
        else:
            summary["eligible"] += 1
    return summary


# =====================================================================================
# CLI
# =====================================================================================

def _print_result(r):
    print(f"event_id={r['event_id']} status={r['status']} mode={r.get('mode')} reason={r.get('reason')}")
    if r.get("reused_existing_run"):
        print(f"  (existing VALID run reused: run_id={r.get('run_id')}, fingerprint unchanged - use --force to re-run)")
        return
    if r["status"] in ("EVENT_NOT_FOUND", "NOT_ELIGIBLE", RUN_FAILED):
        if r.get("error"):
            print(f"  error: {r['error']}")
        return
    print(f"  queries: {len(r['query_plan'].queries)}  candidates: {r['candidate_count']}  "
          f"kept(filtered): {r['kept_count']}  selected: {r['selected_candidate_count']}  "
          f"observations: {r['observation_count']}  clusters: {r['cluster_count']}")
    print(f"  association distribution: {r['association_distribution']}")
    if r.get("discovery_errors"):
        print(f"  discovery errors: {r['discovery_errors']}")
    p = r["payload"]
    print(f"  recurring_themes={len(p.recurring_themes)} recurring_questions={len(p.recurring_questions)} "
          f"interpretations={len(p.interpretations)} experiences={len(p.experiences)} "
          f"disagreements={len(p.disagreements)} uncertainties={len(p.uncertainties)} "
          f"implications={len(p.implications)} coverage_gaps={len(p.coverage_gaps)}")
    print(f"  understanding_contribution: {p.understanding_contribution}")
    if r.get("run_id"):
        print(f"  run_id={r['run_id']} (persisted)")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="PDI V1 - Public Discourse Intelligence (shadow/offline mode).")
    ap.add_argument("--event", type=int, help="run PDI for one event id")
    ap.add_argument("--eligible", action="store_true", help="run PDI over the recent-events eligible pool")
    ap.add_argument("--limit", type=int, default=50, help="--eligible: how many recent events to consider")
    ap.add_argument("--days", type=int, default=14, help="--eligible: recent-events window")
    ap.add_argument("--persist", action="store_true", help="write pdi_* rows (default: dry run, nothing written)")
    ap.add_argument("--force", action="store_true", help="re-run even if a fresh VALID run already exists")
    a = ap.parse_args()

    t0 = time.time()
    if a.event is not None:
        res = run_pdi_for_event(a.event, force=a.force, persist=a.persist)
        _print_result(res)
    elif a.eligible:
        summary = run_pdi_eligible(limit=a.limit, days=a.days, persist=a.persist)
        print(f"considered={summary['considered']} eligible={summary['eligible']} "
              f"not_eligible={summary['not_eligible']}")
        for r in summary["results"]:
            if r["status"] != "NOT_ELIGIBLE":
                _print_result(r)
    else:
        ap.print_help()
    print(f"\n(runtime: {time.time() - t0:.1f}s)")
