"""
section_rank.py - deterministic per-section story classification, ranking, and
lead selection for the Paksh homepage's topical sections (Economy, Finance &
Markets, Defence & Security, Technology, India & World, India, World, Politics
& Policy, Society, Health, Science & Space, Sports, Culture & Entertainment).

WHAT THIS ADDS ON TOP OF homepage_rank.py
-------------------------------------------
homepage_rank.py answers "how interesting/fresh/India-relevant is this story in
general". That is still the base signal here (breadth, independence, velocity,
developments, freshness, india_relevance - all reused, not reimplemented). What
this module adds is SECTION IDENTITY: which section(s) a story belongs to, and,
within a section, an EDITORIAL SENIORITY ranking so a section is not simply
"everything tagged with this topic, sorted by generic score".

A section is not "all stories where topic == X". A story can belong to more
than one section (e.g. an India-China border story is eligible for both
Defence & Security and India & World) - sections are independent pools, exactly
like homepage_rank.py's existing "india"/"world"/"trending" pools already are.

NO LLM. Classification is deterministic regex over event title/title_hi (English
+ Hindi), the same style already used by analyze.py's own _guess_topic() keyword
fallback - reusing the existing event.topic/event.region fields as priors, never
replacing them, and never inventing a new keyword-spread heuristic broad enough
to swallow unrelated stories (cleanup.py's docstring warns explicitly against
that failure mode - the tiers here are narrow and specific on purpose).

SENIORITY, NOT JUST RELEVANCE
------------------------------
Each section with an explicit editorial priority order (Economy, Finance &
Markets, Defence & Security, Technology, India & World, Politics & Policy)
defines an ordered list of keyword TIERS, most editorially senior first (e.g.
Economy: macro > policy > inflation/growth > sectors > business > trade/infra >
finance_markets-adjacent). A story's tier is the FIRST (most senior) tier whose
keywords match - not a sum of all matches - and that tier converts to a
`seniority` multiplier in [0.4, 1.0] baked into the section score. This is what
lets "India's GDP growth forecast raised..." (tier 0: macro) outrank a stock
story even when the stock story has more raw coverage - the whole point of the
"section lead" requirement. It is a bounded multiplier, not a hard gate, so a
huge story can still win over a thin senior-tier one; it nudges, like
india_relevance() already does for the main homepage score. NOTE: Economy has
no "stocks" tier at all (removed in the editorial-validation fix) - individual
stock-price movements are Finance & Markets' territory, not Economy's; a pure
stock story only reaches Economy (if at all) via the weak topic-fallback below.

Several generic (non-explicit) tiers additionally require evidence of an actual
India connection before they can match - see _defence_generic_ok,
classify_india_world's needs_india_word, and classify_politics_policy's
_POLICY_GENERIC_NEEDS_INDIA. A bare institution/topic word ("army", "election",
"oil imports") is not by itself sufficient; a Korea border story, a Canadian
election, or China's own domestic oil demand must not qualify just because the
word appears.

Sections with no explicit priority order in the spec (Society, Health, Sports,
Culture & Entertainment, plus the broad India/World pools) have no seniority
tiers - they're topic/region-based inclusion, ranked purely by the general
interest/freshness/india formula, same as homepage_rank.py's existing
"india"/"world" sections.

Every eligible story keeps every sub-score used (see section_rank_story), so any
ranking is explainable: "why is this story in Defence & Security, and why does
it lead" always has a real, inspectable answer.
"""
import re
from collections import defaultdict

import homepage_rank as hr
from homepage_rank import (
    BREADTH_REF, DEV_HALF_LIFE_H, DEV_REF, INDEP_REF, RECENCY_HALF_LIFE_H,
    VELOCITY_REF, W_BREADTH, W_DEV, W_INDEP, W_VELOCITY,
    _breadth, _freshness_age_h, _hours_since, _log_norm, india_relevance,
)

# --- tunables --------------------------------------------------------------------------
SECTION_N = 20
MIN_SECTION_SIZE = 3            # below this, omit the section rather than pad it - matches
                                 # homepage_rank.select_homepage_sections' existing rule
TIER_CAP_FRAC = 0.4             # a single tier (e.g. "stocks") may not exceed this fraction
                                 # of a section - the direct fix for "Economy becomes a
                                 # stock-only feed" (Step 9/TESTS)
SENIORITY_FLOOR = 0.4           # weakest explicit tier match
SENIORITY_TOPIC_FALLBACK = 0.35 # weaker than any explicit tier: topic matched, no keyword
SENIORITY_NEUTRAL = 1.0         # sections with no priority order (no tiers to rank against)


def _text(event):
    return " ".join([event.get("title") or "", event.get("title_hi") or ""])


def _rx(*patterns):
    return re.compile(r"(?<!\w)(?:" + "|".join(patterns) + r")(?!\w)", re.I)


def _tier_match(text, tiers):
    """First (most senior) matching tier, or (None, None). `tiers` is ordered
    most-senior first, matching this module's whole seniority design."""
    for i, (name, rx) in enumerate(tiers):
        if rx.search(text):
            return i, name
    return None, None


def _seniority(idx, n_tiers):
    if idx is None:
        return SENIORITY_TOPIC_FALLBACK
    if n_tiers <= 1:
        return 1.0
    return round(1.0 - (idx / (n_tiers - 1)) * (1.0 - SENIORITY_FLOOR), 4)


# --- section keyword tiers ---------------------------------------------------------------
# Each list is ordered most editorially senior first, per the section-specific
# priorities given in the homepage-section-composition spec. English + Hindi terms,
# whole-word matched (same convention as analyze.py's _TOPIC_RE) so 'ai' can't fire
# inside 'said' or 'us' inside 'campus'.

ECONOMY_TIERS = [
    ("macro", _rx(r"\bgdp\b", r"economic growth", r"economic survey", r"recession",
                  r"economic slowdown", r"अर्थव्यवस्था", r"जीडीपी")),
    ("policy", _rx(r"economic policy", r"union budget", r"budget 20\d\d", r"fiscal policy",
                   r"disinvestment", r"customs duty", r"import duty", r"export duty",
                   r"बजट")),
    ("inflation_growth", _rx(r"inflation", r"\bcpi\b", r"\bwpi\b", r"unemployment",
                             r"jobs report", r"fiscal deficit", r"employment data",
                             r"महंगाई", r"बेरोज़गारी")),
    # Broadened per the editorial-validation fix: commodity/sector PRICE movements (steel,
    # cement, crude, metals...) are an economy-wide input-cost/inflation signal, not a
    # tradeable-security story - that distinction is what keeps them here rather than in
    # Finance & Markets' "commodities_currency" tier (which is about trading/market moves).
    ("sectors", _rx(r"manufacturing sector", r"agriculture sector", r"services sector",
                    r"auto sector", r"real estate sector", r"textile industry",
                    r"pharma sector", r"it sector", r"steel prices?", r"cement prices?",
                    r"metal prices?", r"commodity prices?", r"raw material cost")),
    # Broadened to catch business-development stories (new brand/plant/facility launches,
    # franchise deals) that are economy-wide business news, not stock-price movement -
    # this is the direct fix for "JSW Group Launches AMPSTAR..." and "McDonald's...
    # Franchisee Support Plan" falling through to the weak topic-fallback instead of a
    # real tier.
    # "launches/unveils" is bounded to a nearby product/brand/facility noun (not a bare
    # "launches new ___") - a bare pattern also matched "LTM Launches New AI Models",
    # which defeated the Economy->Technology fallback-suppression below by giving it a
    # REAL Economy tier match instead of falling through to the (suppressible) fallback.
    ("business", _rx(r"acquisition", r"merger", r"earnings report", r"quarterly results",
                     r"net profit", r"revenue grew", r"revenue rose",
                     r"launche?s?.{0,40}\b(brand|product line|vehicle)\b",
                     r"unveils?.{0,40}\b(brand|product line)\b",
                     r"expands? operations", r"opens? (a |new )?plant", r"franchise")),
    ("trade_infra", _rx(r"trade deal", r"free trade agreement", r"infrastructure project",
                        r"highway project", r"port project", r"exports? (rose|fell|grew|jumped)",
                        r"imports? (rose|fell|grew|jumped)")),
    ("finance_markets", _rx(r"\brbi\b", r"reserve bank of india", r"banking sector",
                            r"interest rate", r"repo rate")),
    # NOTE: deliberately NO "stocks" tier here (removed per the editorial-validation fix -
    # "Individual stock movements should primarily belong to Finance & Markets", Step 5).
    # A pure stock-price story (Sensex/Nifty/"shares rose"/IPO) no longer gets a real
    # Economy tier match at all; it only reaches Economy (if at all) via the weak
    # topic-fallback below, while Finance & Markets' own "stocks"/"indian_markets"/"ipo"
    # tiers give it a real, senior match there - this is classification, not a quota.
]

FINANCE_TIERS = [
    ("indian_markets", _rx(r"sensex", r"nifty", r"\bbse\b", r"\bnse\b",
                           r"indian stock market", r"dalal street", r"सेंसेक्स", r"निफ्टी")),
    ("rbi_monetary", _rx(r"\brbi\b", r"reserve bank of india", r"repo rate", r"monetary policy",
                         r"rbi governor", r"रिज़र्व बैंक", r"रेपो रेट")),
    # NOTE: deliberately no bare \bbank\b - it matched "Yamuna River Bank" in testing.
    # Hindi बैंक is kept bare: unlike English "bank", Hindi has no competing sense (a
    # riverbank is किनारा/तट), so बैंक alone is unambiguous.
    ("banking", _rx(r"banking sector", r"bank employees", r"bank strike", r"bank merger",
                    r"bank stock", r"private bank", r"public sector bank", r"psu bank",
                    r"central bank", r"\bnpas?\b", r"bad loans", r"\bsbi\b",
                    r"hdfc bank", r"icici bank", r"axis bank", r"punjab national bank",
                    r"bank of baroda", r"बैंक")),
    ("regulation", _rx(r"\bsebi\b", r"financial regulation", r"market regulator",
                       r"insider trading")),
    # Broadened per the editorial-validation fix to catch investment-fund stories (e.g.
    # "Kotak Alts Closes ₹5,000 Crore Fund from Domestic Investors") that were falling
    # through to Economy's weak topic-fallback instead of matching here (Step 5).
    ("institutions", _rx(r"mutual fund", r"insurance company", r"\bnbfc\b",
                         r"financial institution", r"investment fund",
                         r"alternative investment fund", r"\baif\b", r"fund clos",
                         r"fund rais", r"crore fund")),
    ("ipo", _rx(r"\bipo\b", r"initial public offering", r"stock market debut",
               r"listing gains", r"आईपीओ")),
    ("stocks", _rx(r"share price", r"stock price", r"\bstocks?\b",
                   r"shares? (rose|fell|jumped|gained|surged|tumbled|plunged)")),
    ("commodities_currency", _rx(r"rupee", r"dollar", r"gold price", r"silver price",
                                 r"crude oil price", r"bond yield", r"forex",
                                 r"रुपया", r"सोना", r"चांदी")),
    ("global_finance", _rx(r"wall street", r"federal reserve", r"fed rate", r"dow jones",
                           r"nasdaq", r"global markets")),
]

DEFENCE_TIERS = [
    # (name, regex, explicit) - "explicit" tiers use proper nouns/compounds that can only
    # mean Indian defence content (Rajnath Singh, DRDO, LAC, Galwan...) and are always
    # eligible. "Generic" (explicit=False) tiers use words ambiguous on their own (a bare
    # "army"/"military"/"submarine" could belong to ANY country's news, and Hindi सेना
    # ("army/forces") and सीमा ("boundary/limit" - matched "समय सीमा"/deadline and "वोट की
    # सीमा"/vote threshold in testing, nothing to do with a border) are similarly generic) -
    # these require an actual India/Pakistan/China connection (classify_defence_security's
    # gate below), which is the direct fix for "Defence dominated by foreign defence news"
    # (a Korea/US/Hong Kong military story with no India tie must NOT qualify just because
    # it says "military").
    ("armed_forces", _rx(r"indian army", r"indian navy", r"indian air force", r"\biaf\b",
                         r"defence ministry", r"rajnath singh", r"chief of defence staff",
                         r"रक्षा मंत्रालय", r"राजनाथ"), True),
    ("armed_forces_generic", _rx(r"सेना", r"वायुसेना", r"नौसेना"), False),
    ("border_security", _rx(r"line of control", r"\blac\b", r"line of actual control",
                            r"india-china border", r"india-pakistan border", r"galwan",
                            r"siachen", r"नियंत्रण रेखा"), True),
    ("border_security_generic", _rx(r"infiltration", r"ceasefire violation", r"cross-border"), False),
    ("terror_internal_security", _rx(r"terrorist", r"terror attack", r"terror module",
                                     r"naxal", r"maoist", r"insurgent", r"आतंकवादी",
                                     r"आतंकी हमला", r"नक्सल"), False),
    ("procurement_tech", _rx(r"rafale", r"tejas", r"brahmos", r"agni missile", r"\bdrdo\b",
                             r"हथियार सौदा", r"मिसाइल परीक्षण"), True),
    ("procurement_tech_generic", _rx(r"defence deal", r"arms deal", r"missile test",
                                     r"submarine", r"fighter jet", r"howitzer"), False),
    ("strategic_affairs", _rx(r"quad summit", r"indo-pacific", r"defence pact",
                              r"military cooperation", r"strategic partnership"), False),
    ("general_military", _rx(r"\bmilitary\b", r"\barmy\b", r"\bnavy\b", r"warship",
                             r"defence budget", r"armed forces"), False),
]

TECHNOLOGY_TIERS = [
    # NOTE: deliberately NO bare \bai\b (editorial-validation fix, Step 2) - it matched
    # "Prince Harry's AI speech", "Elon Musk Predicts AI Mastery...", and two separate UN
    # General Assembly stories that merely listed AI among several agenda items. AI now
    # only qualifies when it is substantively the subject (a model/product/company/
    # regulation/research/etc.), not merely mentioned in passing. "artificial intelligence"
    # (the full phrase) is kept bare since spelling it out is itself substantive framing.
    ("ai_semiconductor", _rx(r"artificial intelligence", r"generative ai", r"\bai models?\b",
                             r"\bai products?\b", r"\bai compan(y|ies)\b",
                             r"\bai regulations?\b", r"\bai research\b", r"\bai r&d\b",
                             r"\bai infrastructure\b", r"\bai investments?\b",
                             r"\bai deployments?\b", r"\bai polic(y|ies)\b",
                             r"\bai startups?\b", r"\bai chips?\b", r"\bai tools?\b",
                             r"\bai systems?\b", r"\bai assistants?\b", r"\bai lab\b",
                             r"ai-powered", r"ai adoption",
                             r"chatgpt", r"semiconductor", r"\bchip\b", r"foundry",
                             r"nvidia", r"qualcomm", r"chip manufacturing")),
    ("telecom", _rx(r"\b5g\b", r"\b6g\b", r"telecom", r"\bjio\b", r"airtel", r"vodafone",
                    r"spectrum auction", r"\btrai\b")),
    ("cybersecurity", _rx(r"cyberattack", r"cybersecurity", r"data breach", r"hacked",
                          r"ransomware", r"phishing", r"साइबर")),
    ("startups", _rx(r"startup", r"unicorn", r"funding round", r"series [abc]\b",
                     r"venture capital", r"स्टार्टअप")),
    ("consumer_tech", _rx(r"smartphone", r"iphone", r"android", r"app store", r"\bgoogle\b",
                          r"\bmeta\b", r"\bmicrosoft\b", r"\bapple\b")),
]

SCIENCE_SPACE_TIERS = [
    ("space_isro", _rx(r"\bisro\b", r"chandrayaan", r"gaganyaan", r"spacex", r"\bnasa\b",
                       r"satellite launch", r"rocket launch", r"mars mission", r"moon mission",
                       r"lunar mission", r"इसरो", r"चंद्रयान", r"गगनयान", r"उपग्रह", r"अंतरिक्ष")),
    ("science_research", _rx(r"scientist", r"research study", r"\bfossil\b", r"physics",
                             r"astronomy", r"quantum computing")),
]

INDIA_WORLD_TIERS = [
    # (name, regex, needs_india_word) - "bilateral" and "trade_tariff" already encode the
    # India relationship directly in their own compound phrases (india-us, tariff ON
    # india, h-1b is a specifically India-associated US visa category), so they need no
    # extra check. "immigration_energy" is the tier that broke in the editorial
    # validation: "energy imports?"/"oil imports?" are bare and country-agnostic, so
    # "Goldman Sachs Predicts Subdued CHINESE Oil Imports" matched with zero India
    # relationship. needs_india_word=True means the tier's own regex match is NOT by
    # itself sufficient - classify_india_world below additionally requires an explicit
    # india/indian word in the same text (Step 3: "Require evidence of an actual
    # relationship involving India", not "contains India OR China OR Pakistan").
    ("bilateral", _rx(r"india-us", r"india-china", r"india-pakistan", r"india-russia",
                      r"indo-us", r"indo-pacific", r"india-middle east", r"india-eu",
                      r"quad summit"), False),
    ("trade_tariff", _rx(r"tariff on india", r"trade deal with india", r"india trade deal",
                         r"\bh-1b\b", r"\bh1b\b visa", r"exports? to india",
                         r"imports? from india"), False),
    ("immigration_energy", _rx(r"immigration policy", r"indian students? visa",
                               r"energy imports?", r"oil imports?", r"crude oil imports?",
                               r"lng imports?", r"gas imports?"), True),
]

POLICY_TIERS = [
    # (name, regex, explicit) - explicit tiers name Indian institutions/parties/Hindi terms
    # unambiguous on their own. Generic tiers use words that could describe ANY country's
    # politics (parliament, election, minister...) and therefore additionally require the
    # story to be India-linked (region India or an explicit india/indian word) in
    # classify_politics_policy below - the direct fix for "BC Premier Calls Snap Election
    # Citing Trump Threat" qualifying purely via the bare word "election" (Step 4). NOTE:
    # no bare \bparty\b ("house party" false-matched in testing) and no bare \bmp\b
    # (collides with "MP" as shorthand for the state Madhya Pradesh in Indian headlines) -
    # named parties + explicit "political/opposition/ruling party" phrasing instead.
    ("legislation_policy", _rx(r"lok sabha", r"rajya sabha", r"\bmla\b",
                               r"संसद", r"अध्यादेश", r"सुप्रीम कोर्ट"), True),
    ("legislation_policy_generic", _rx(r"amendment", r"ordinance", r"\bbill\b",
                                       r"\bparliament\b", r"supreme court", r"high court",
                                       r"\bverdict\b", r"constitution", r"reservation",
                                       r"\bquota\b", r"\bcabinet\b", r"\bgovernor\b",
                                       r"\bpolicy\b", r"\bact\b"), False),
    ("elections_parties", _rx(r"\bbjp\b", r"congress", r"\btmc\b", r"\baap\b", r"shiv sena",
                              r"चुनाव", r"विधायक", r"सांसद"), True),
    ("elections_parties_generic", _rx(r"\belection\b", r"\bcm\b", r"political party",
                                      r"opposition party", r"ruling party", r"\bpoll\b",
                                      r"\bvote\b"), False),
    ("general_political", _rx(r"\bminister\b", r"\bgovernment\b", r"सरकार", r"मंत्री"), False),
]


# --- classification: story -> (tier_idx, tier_name, seniority) or None (ineligible) -----

def _classify_tiered_with_topic_fallback(event, tiers, fallback_topic, suppress_if_matches=None):
    """suppress_if_matches: an optional other tier list - if the topic-fallback would
    otherwise fire, but the text substantively matches one of THOSE tiers instead, the
    fallback is withheld. Used so a story stored with topic="Economy" upstream but whose
    text is substantively an AI/tech story (e.g. "LTM Launches New AI Models for
    Enterprises") doesn't leak into Economy's weak fallback just because of its stored
    topic - its real editorial home is Technology, where it already matches a real tier
    (editorial-validation fix, Step 5)."""
    idx, name = _tier_match(_text(event), tiers)
    if idx is not None:
        return idx, name, _seniority(idx, len(tiers))
    if fallback_topic and event.get("topic") == fallback_topic:
        if suppress_if_matches is not None and _tier_match(_text(event), suppress_if_matches)[0] is not None:
            return None
        return None, "general", SENIORITY_TOPIC_FALLBACK
    return None


def classify_economy(event):
    return _classify_tiered_with_topic_fallback(event, ECONOMY_TIERS, "Economy",
                                                 suppress_if_matches=TECHNOLOGY_TIERS)


def classify_finance_markets(event):
    return _classify_tiered_with_topic_fallback(event, FINANCE_TIERS, "Economy",
                                                 suppress_if_matches=TECHNOLOGY_TIERS)


def classify_technology(event):
    return _classify_tiered_with_topic_fallback(event, TECHNOLOGY_TIERS, "Science & Tech")


def classify_science_space(event):
    idx, name = _tier_match(_text(event), SCIENCE_SPACE_TIERS)
    if idx is None:
        return None
    return idx, name, _seniority(idx, len(SCIENCE_SPACE_TIERS))


def _defence_generic_ok(event, text):
    """Gate for DEFENCE_TIERS' ambiguous (explicit=False) tiers: eligible if this is
    already an India-region story, or the text explicitly names India/Pakistan/China -
    the three countries the spec's own priority list calls out (India-Pakistan,
    India-China). A Korea/US/Hong Kong military story with none of those has no India
    tie and must not qualify just because it says "military" or "submarine"."""
    if event.get("region") == "India":
        return True
    return bool(re.search(r"\bindia\b|\bindian\b|\bpakistan\b|\bchina\b", text, re.I))


# Editorial-validation fix (Step 1): a bare institution word ("army"/"सेना"/"military")
# must NOT be sufficient on its own - "Army Jawan Killed in Mizoram Road Rage Incident"
# matched purely because the victim happened to be a soldier, with nothing about the
# institution's own activity in the story. The two purely-generic institution tiers
# (armed_forces_generic, general_military - no proper noun, just "army"/"सेना"/"military")
# additionally require one of these substantive-activity terms, drawn directly from the
# fix spec's own list (procurement, operation, deployment, exercise, weapon/system,
# policy, strategic/security development, border/security incident). Explicit tiers
# (named entities like Rajnath Singh, DRDO, LAC) are unaffected - a story ABOUT the
# defence minister or a named defence programme is substantive by construction.
_DEFENCE_ACTIVITY_CONTEXT = _rx(
    r"procurement", r"acquisitions?", r"acquires?", r"\bcontract\b", r"\btender\b",
    r"defence deals?", r"arms deals?",
    r"military operations?", r"\bmissions?\b", r"\bstrikes?\b", r"\braids?\b", r"offensive",
    r"deployments?", r"\bdeployed\b", r"\bstationed\b", r"\bpatrols?\b",
    r"\bexercises?\b", r"\bdrills?\b", r"war ?games?",
    r"\bweapons?\b", r"\bmissiles?\b", r"fighter jets?", r"\bsubmarines?\b",
    r"\bwarships?\b", r"\btanks?\b", r"\bartillery\b", r"\bdrones?\b", r"\bradars?\b",
    r"defence systems?", r"weapon systems?", r"missile systems?",
    r"defence policy", r"military policy", r"\bdoctrine\b", r"defence budget",
    r"moderni[sz]ations?",
    r"\bstrategic\b", r"security cooperation", r"security pacts?", r"defence pacts?",
    r"defence alliances?",
    r"\bborder\b", r"\bincursions?\b", r"\bceasefire\b", r"\bskirmish(es)?\b",
    r"\bclash(es)?\b", r"\bstandoffs?\b", r"\bintrusions?\b", r"\bcaptured?\b",
    r"intelligence (team|operation|officer)",
    r"अभ्यास", r"तैनाती", r"हथियार", r"रक्षा नीति", r"ऑपरेशन", r"खरीद",
)
_DEFENCE_GENERIC_NEEDS_ACTIVITY = {"armed_forces_generic", "general_military"}


def classify_defence_security(event):
    text = _text(event)
    generic_ok = None
    for i, (name, rx, explicit) in enumerate(DEFENCE_TIERS):
        if not rx.search(text):
            continue
        if explicit:
            return i, name, _seniority(i, len(DEFENCE_TIERS))
        if name in _DEFENCE_GENERIC_NEEDS_ACTIVITY and not _DEFENCE_ACTIVITY_CONTEXT.search(text):
            # institution word present but nothing substantive about it (a crime/accident/
            # personal-dispute story that merely involves a soldier) - not Defence content
            continue
        if generic_ok is None:
            generic_ok = _defence_generic_ok(event, text)
        if generic_ok:
            return i, name, _seniority(i, len(DEFENCE_TIERS))
        # this generic tier matched but has no India/Pakistan/China connection - keep
        # scanning in case a later, less senior tier both matches AND qualifies
    return None


_INDIA_WORD = re.compile(r"\bindia\b|\bindian\b", re.I)

# Named-foreign-country/organization signal, used ONLY to gate the India & World fallback
# below - independent of INDIA_WORLD_TIERS' own curated phrases. Content mirrors the
# country list analyze.py's own _guess_topic() already uses for its "International" topic
# hint (kept as its own explicit list here rather than importing analyze.py's private
# name, to avoid a cross-module dependency on internals).
_FOREIGN_COUNTRY_OR_ORG = re.compile(
    r"\bus\b|u\.s\.|\biran\b|israel|pakistan|\bchina\b|chinese|russia|ukraine|"
    r"bangladesh|nepal|sri lanka|maldives|bhutan|myanmar|afghanistan|taliban|syria|"
    r"lebanon|yemen|turkey|türkiye|qatar|saudi|\buae\b|egypt|venezuela|brazil|mexico|"
    r"canada|australia|japan|\bkorea\b|taiwan|france|germany|italy|spain|britain|"
    r"\buk\b|u\.k\.|europe|european union|\beu\b|\bnato\b|united nations|\bun\b|"
    r"palestine|washington|blinken|kremlin|beijing|moscow|islamabad|dhaka|kathmandu",
    re.I,
)


def classify_india_world(event):
    text = _text(event)
    for i, (name, rx, needs_india_word) in enumerate(INDIA_WORLD_TIERS):
        if not rx.search(text):
            continue
        if needs_india_word and not _INDIA_WORD.search(text):
            # e.g. "oil imports" matched but nothing in the text ties it to India - a
            # story purely about Chinese oil demand must not qualify just because
            # "oil imports" appears (Step 3)
            continue
        return i, name, _seniority(i, len(INDIA_WORLD_TIERS))
    # Fallback - FIXED after the false-negative validation pass: this used to require
    # event.get("topic") == "International", but analyze.py only tags a story
    # "International" when it occurs mainly OUTSIDE India - so India's OWN diplomatic
    # activity (its foreign minister meeting a counterpart, India raising tariff concerns,
    # a bilateral cooperation readout) is tagged "Politics"/"Economy" upstream and never
    # reached this fallback at all, structurally excluding the section's own core content
    # type (verified real misses: "India's EAM Jaishankar Meets US Secretary of State
    # Blinken", "India seeks constructive ties with Bangladesh", "India, France, UAE
    # Discuss Cooperation at UNGA", "India raises concerns over potential 100% tariff on
    # Russian oil"). Replaced the topic check with a direct textual signal: an explicit
    # India word co-occurring with a NAMED foreign country/organization is stronger,
    # unambiguous evidence of an actual relationship, regardless of the stored topic - a
    # story purely about India-only news still needs a named foreign counterpart to
    # qualify, and a purely-foreign story (no India word) is still excluded exactly as
    # before.
    #
    # Sports and Crime & Law are excluded from this fallback entirely (re-validation
    # follow-up): India-word + foreign-country-word co-occurrence is too loose for these
    # two topics specifically - "Pakistan coach Hesson says team must 'catch up' with
    # India in T20 cricket" and "Two Indian students die in Canada flight training
    # accident" both satisfy the co-occurrence check without being an actual India-
    # foreign RELATIONSHIP story; a cricket match or an individual's personal legal/
    # accident matter abroad is not diplomacy, trade, or security. Every other topic
    # (Politics, Economy, International, etc.) is unaffected.
    if (event.get("topic") not in ("Sports", "Crime & Law")
            and _INDIA_WORD.search(text) and _FOREIGN_COUNTRY_OR_ORG.search(text)):
        return None, "india_mentioned", SENIORITY_TOPIC_FALLBACK
    return None


_POLICY_GENERIC_NEEDS_INDIA = {"legislation_policy_generic", "elections_parties_generic",
                               "general_political"}


def classify_politics_policy(event):
    text = _text(event)
    india_ok = event.get("region") == "India" or _INDIA_WORD.search(text) is not None
    for i, (name, rx, explicit) in enumerate(POLICY_TIERS):
        if not rx.search(text):
            continue
        if explicit:
            return i, name, _seniority(i, len(POLICY_TIERS))
        if name in _POLICY_GENERIC_NEEDS_INDIA and not india_ok:
            # a foreign election/parliament/minister story with no India link - the
            # generic keyword alone is not enough (Step 4)
            continue
        return i, name, _seniority(i, len(POLICY_TIERS))
    if event.get("topic") == "Politics" and india_ok:
        return None, "general", SENIORITY_TOPIC_FALLBACK
    return None


def _classify_by_topic(topic_name):
    def _fn(event):
        if event.get("topic") == topic_name:
            return None, "general", SENIORITY_NEUTRAL
        return None
    return _fn


def classify_india(event):
    if event.get("region") == "India":
        return None, "general", SENIORITY_NEUTRAL
    return None


def classify_world(event):
    if event.get("region") != "India":
        return None, "general", SENIORITY_NEUTRAL
    return None


SECTIONS = {
    "india":                 {"label": "India",                  "classify": classify_india},
    "politics_policy":       {"label": "Politics & Policy",       "classify": classify_politics_policy},
    "economy":               {"label": "Economy",                 "classify": classify_economy},
    "finance_markets":       {"label": "Finance & Markets",       "classify": classify_finance_markets},
    "defence_security":      {"label": "Defence & Security",      "classify": classify_defence_security},
    "technology":            {"label": "Technology",              "classify": classify_technology},
    "india_world":           {"label": "India & World",           "classify": classify_india_world},
    "world":                 {"label": "World",                   "classify": classify_world},
    "society":               {"label": "Society",                 "classify": _classify_by_topic("Society")},
    "health":                {"label": "Health",                  "classify": _classify_by_topic("Health")},
    "science_space":         {"label": "Science & Space",         "classify": classify_science_space},
    "sports":                {"label": "Sports",                  "classify": _classify_by_topic("Sports")},
    "culture_entertainment": {"label": "Culture & Entertainment", "classify": _classify_by_topic("Entertainment")},
}
# Extensible by construction: adding a section is one new entry (label + classify fn),
# nothing elsewhere needs to change - select_section()/build_section_pool() are generic
# over SECTIONS.


# --- scoring: reuses homepage_rank.py's exact interest/freshness/india ingredients,
#     gated by the section-specific seniority multiplier -------------------------------

def section_rank_story(event, si, velocity, now, tier_idx, tier_name, seniority):
    """Same interest/freshness/india formula as homepage_rank.homepage_rank_story,
    additionally gated (multiplied, not added - same reasoning as freshness/india
    already being multiplicative gates there) by `seniority`, the section-editorial-
    hierarchy signal. Returns a fully explainable dict."""
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

    score = interest * freshness * india * seniority
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
        "tier": tier_name,
        "tier_idx": tier_idx,
        "seniority": seniority,
    }


def build_section_pool(events, si_map, vel_map, now, section_key):
    """All events eligible for `section_key`, each scored - unordered."""
    classify = SECTIONS[section_key]["classify"]
    out = []
    for e in events:
        cls = classify(e)
        if cls is None:
            continue
        tier_idx, tier_name, seniority = cls
        si = si_map.get(e["id"], {"independent_count": 0, "dev_count": 0,
                                   "latest_dev_time": None, "has_si": False})
        vel = vel_map.get(e["id"], {"owners_total": 0, "owners_recent": 0})
        r = section_rank_story(e, si, vel, now, tier_idx, tier_name, seniority)
        r["event"] = e
        out.append(r)
    return out


def _diversify_section(pool, n=SECTION_N, cap_frac=TIER_CAP_FRAC):
    """Greedy top-N by score with two anti-domination constraints (Step 9/10 and
    the 'Economy does not become a stock-only feed' test): (a) no single group
    exceeds `cap_frac` of the section, (b) no storyline appears twice.

    The group for (a) is the story's TIER when the section has real tiers (e.g.
    Economy's 'stocks' vs 'macro') - but sections with no priority tiers at all
    (India/World/Society/Health/Sports/Culture & Entertainment, whose classify
    functions always return tier='general') fall back to the story's own
    event.topic instead. Without this fallback every story in a topic-only
    section shares the same tier ('general'), so the cap would apply to the
    WHOLE section at once and silently truncate it to `cap_frac * n` stories
    regardless of how many genuinely qualify - caught in testing: India/World/
    Society/Health/Sports/Culture & Entertainment were all stuck at exactly 8
    (ceil(20*0.4)) instead of up to 20.

    Society/Health/Sports/Culture & Entertainment/Science & Space still hit the
    SAME failure even with the event.topic fallback above: those sections filter
    to one fixed event.topic by construction (_classify_by_topic), so every story
    in the pool shares that one topic too - one group, still capped at 8. There is
    nothing to "diversify against" when the whole pool is one group, so the cap
    only kicks in once the pool actually contains 2+ distinct groups."""
    import math

    def _group(r):
        return r["tier"] if r["tier"] != "general" else (r["event"].get("topic") or "general")

    groups_present = {_group(r) for r in pool}
    cap = max(1, math.ceil(n * cap_frac)) if len(groups_present) > 1 else n
    chosen, group_count, storyline_seen = [], defaultdict(int), set()
    for r in sorted(pool, key=lambda r: r["score"], reverse=True):
        if len(chosen) >= n:
            break
        group = _group(r)
        sid = r["event"].get("storyline_id")
        if group_count[group] >= cap:
            continue
        if sid is not None and sid in storyline_seen:
            continue
        chosen.append(r)
        group_count[group] += 1
        if sid is not None:
            storyline_seen.add(sid)
    return chosen


def select_section(events, si_map, vel_map, now, section_key, n=SECTION_N):
    """Returns (ranked_list, lead_or_None) for one section, or ([], None) if
    fewer than MIN_SECTION_SIZE stories qualify (omit-not-pad, same rule
    homepage_rank.select_homepage_sections already uses)."""
    pool = build_section_pool(events, si_map, vel_map, now, section_key)
    ranked = _diversify_section(pool, n)
    if len(ranked) < MIN_SECTION_SIZE:
        return [], None
    return ranked, ranked[0]


def select_all_sections(events, si_map, vel_map, now, n=SECTION_N):
    """Returns {section_key: {"label", "stories", "lead"}} for every section in
    SECTIONS that clears MIN_SECTION_SIZE."""
    out = {}
    for key, spec in SECTIONS.items():
        ranked, lead = select_section(events, si_map, vel_map, now, key, n)
        if ranked:
            out[key] = {"label": spec["label"], "stories": ranked, "lead": lead}
    return out
