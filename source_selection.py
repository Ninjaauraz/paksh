"""
source_selection.py - which of an event's articles the summary model gets to read.

An event can carry dozens of articles but the prompt has room for MAX_ARTICLES_PER_EVENT
(12). Until now the pick was: up to 2 articles per lean (in database order), then "the rest,
rated first". Database order is arbitrary, so the model often read six copies of one wire
story from one publisher family and never saw the outlet that actually added something.

This module chooses those articles. It is PURE (no DB, no network) and it can only choose
among the event's OWN articles - it never adds an outlet, never changes a lean label, never
touches the bias-bar arithmetic (which is computed from ALL of the event's articles in
analyze.postprocess, not from this subset). Full write-up: docs/SOURCE_SELECTION_ALGORITHM.md

Priorities, in order:
  1. independent reporting   - near-identical headlines from one lean, or one owner's
                               mastheads, collapse into ONE report (the richest copy)
  2. factual richness        - a report with a real excerpt beats a headline-only one
  3. regional diversity      - an outlet from a home region not yet in the pick gets a bonus
  4. ideological diversity   - the existing guarantee: up to MIN_PER_LEAN reports from EACH
                               lean that covered the story is picked before anything else
  5. freshness               - newer reports beat older ones
  6. publisher credibility   - reviewed registry outlets beat provisional / low-confidence ones
No quota beyond (4): if the coverage is lopsided the pick is lopsided.
"""
import re
from datetime import datetime, timezone

# Weights of the per-report score (sum to 1.0) and the two selection bonuses.
W_RICH, W_FRESH, W_CRED = 0.55, 0.25, 0.20
BONUS_NEW_REGION = 0.30     # first report from a home region that is not yet in the pick
BONUS_THIN_LEAN = 0.10      # tiny nudge toward the lean with the fewest picks (fill phase only)
BONUS_NEW_UNDERLYING = 0.50  # international tier: first report of an underlying lean not yet in the pick
RICH_FULL_CHARS = 300       # an excerpt this long counts as fully "rich" (SUMMARY_TRUNC in analyze.py)
SIM_SAME_REPORT = 0.75      # headline token-Jaccard at/above which two same-lean articles are one report

# Home region of the curated INTERNATIONAL outlets (headquarters country -> region). A descriptive
# fact used only to spread the pick geographically; it is not a lean label and never reaches the bar.
HOME_REGION_INTL = {
    "Associated Press": "US", "Bloomberg": "US", "The New York Times": "US", "The Washington Post": "US", "CNN": "US",
    "Fox News": "US", "NPR": "US", "TIME": "US", "NBC News": "US", "CBS News": "US", "USA Today": "US",
    "ABC News (US)": "US", "Politico": "US", "The Wall Street Journal": "US", "The Atlantic": "US",
    "The New Yorker": "US", "Business Insider": "US", "CNBC": "US", "Forbes": "US", "Fortune": "US",
    "Los Angeles Times": "US", "Chicago Tribune": "US", "Voice of America": "US",
    "Reuters": "UK", "BBC News": "UK", "The Guardian": "UK", "Sky News": "UK", "The Independent": "UK",
    "Daily Mail": "UK", "The Economist": "UK", "Financial Times": "UK", "The Daily Telegraph": "UK",
    "Evening Standard": "UK", "Daily Mirror": "UK", "Metro (UK)": "UK",
    "Deutsche Welle": "Europe", "France 24": "Europe", "Le Monde": "Europe", "Euronews": "Europe",
    "Irish Independent": "Europe",
    "Al Jazeera English": "Middle East", "The Jerusalem Post": "Middle East", "Gulf News": "Middle East",
    "South China Morning Post": "East Asia", "Channel News Asia": "East Asia", "The Japan Times": "East Asia",
    "ABC Australia": "Oceania", "The Sydney Morning Herald": "Oceania", "The Age": "Oceania",
    "Australian Financial Review": "Oceania",
    "CBC News": "North America", "The Globe and Mail": "North America", "Toronto Star": "North America",
    "Global News (Canada)": "North America", "CTV News": "North America",
}
_COUNTRY_REGION = {
    "India": "India", "United States": "US", "United Kingdom": "UK", "China": "East Asia", "Japan": "East Asia",
    "South Korea": "East Asia", "Taiwan": "East Asia", "Hong Kong": "East Asia", "Israel": "Middle East",
    "Turkey": "Middle East", "Iran": "Middle East", "Saudi Arabia": "Middle East", "Qatar": "Middle East",
    "United Arab Emirates": "Middle East", "Egypt": "Middle East", "Lebanon": "Middle East", "Iraq": "Middle East",
    "Jordan": "Middle East", "Canada": "North America", "Australia": "Oceania", "New Zealand": "Oceania",
}
_REGISTRY_REGION = {"Western Europe": "Europe", "Eastern Europe": "Europe", "Latin America": "Latin America",
                    "Africa": "Africa", "Middle East": "Middle East", "Asiatic Region": "Asia",
                    "Pacific Region": "Oceania", "Northern America": "North America"}
_CRED_CURATED = {"reviewed": 1.0, "provisional": 0.8}
_CRED_VERIFIED = {"high": 0.8, "medium": 0.65, "low": 0.5}
_STOP = frozenset("the a an of in on to for and or at by with from as is are was be after over amid says say said new".split())


class SourceInfo:
    """Registry-derived facts about an outlet (region + credibility). Built once from sources.py."""
    def __init__(self):
        import sources
        sources._load_verified_registry()
        self.curated = {s["name"]: s for s in sources.SOURCES}
        self.verified = sources.VERIFIED_BY_NAME

    def region(self, name):
        s = self.curated.get(name)
        if s is not None:
            return HOME_REGION_INTL.get(name, "International") if s.get("region") == "International" else "India"
        v = self.verified.get(name)
        if v is not None:
            return _COUNTRY_REGION.get(v.get("country")) or _REGISTRY_REGION.get(v.get("region")) or "Other"
        return None                                   # unknown long-tail domain: no region claim

    def credibility(self, name):
        s = self.curated.get(name)
        if s is not None:
            return _CRED_CURATED.get(s.get("review_status"), 0.8)
        v = self.verified.get(name)
        if v is not None:
            return _CRED_VERIFIED.get(v.get("confidence"), 0.5)
        return 0.3

    def underlying_lean(self, name):
        """The registry's own left/center/right label for an outlet, or None. Only used to keep
        INTERNATIONAL-tier outlets of different underlying leans apart: on a World story they vote on
        that lean (analyze.lean_of), so the prompt must still hear each of them."""
        s = self.curated.get(name) or self.verified.get(name)
        lean = (s or {}).get("lean")
        return lean if lean in ("left", "center", "right") else None


_INFO = None


def _info():
    global _INFO
    if _INFO is None:
        _INFO = SourceInfo()
    return _INFO


def _tokens(title):
    t = re.sub(r"\s+[-|–—]\s+[^-|–—]{2,40}$", "", (title or "").lower())   # drop a trailing " - Outlet"
    t = re.sub(r"[^\wऀ-ॿ ]+", " ", t)
    return frozenset(w for w in t.split() if w not in _STOP and len(w) > 1)


def _published_ts(a):
    p = (a.get("published") or "").strip()
    try:
        if len(p) == 8 and p.isdigit():                                  # GDELT: YYYYMMDD
            return datetime.strptime(p, "%Y%m%d").replace(tzinfo=timezone.utc).timestamp()
        return datetime.fromisoformat(p.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def report_groups(articles, lean_of, owner_of):
    """Collapse an event's articles into INDEPENDENT REPORTS. Within one lean, articles from the
    same owner, or with near-identical headlines (a wire story republished under many mastheads),
    are copies of one report. Different leans never merge: each side keeps its own voice, so a
    side that only has a syndicated copy is still represented. `lean_of` may return any hashable
    key (select_sources passes (tier, underlying lean) so international outlets that will vote on
    different leans on a World story are never merged). Returns a list of article lists."""
    n = len(articles)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    toks = [_tokens(a.get("title")) for a in articles]
    leans = [lean_of(a["source"]) for a in articles]
    owners = [owner_of(a["source"]) for a in articles]
    for i in range(n):
        for j in range(i + 1, n):
            if leans[i] != leans[j]:
                continue
            ti, tj = toks[i], toks[j]
            sim = len(ti & tj) / len(ti | tj) if (ti and tj) else 0.0
            if owners[i] == owners[j] or sim >= SIM_SAME_REPORT:
                parent[find(i)] = find(j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(articles[i])
    return list(groups.values())


def _quality(a, info, ts_lo, ts_span):
    """Per-report score in [0, 1]: richness, freshness, credibility (fixed weights)."""
    rich = min(1.0, len((a.get("summary") or "").strip()) / RICH_FULL_CHARS)
    ts = _published_ts(a)
    fresh = 0.5 if (ts is None or ts_span <= 0) else (ts - ts_lo) / ts_span
    return W_RICH * rich + W_FRESH * fresh + W_CRED * info.credibility(a["source"])


def select_sources(articles, lean_of, owner_of, k=12, min_per_lean=2, info=None):
    """Choose <= k of the event's articles for the summary prompt (see the module docstring).
    Deterministic. Returns the picked articles: the per-lean guarantee first (left, centre, right,
    international, unrated), then the fill, each in selection order."""
    articles = list(articles)
    if len(articles) <= 1:
        return articles
    info = info or _info()
    # International-tier outlets vote on their UNDERLYING lean once a story is classified World, but
    # at prompt time they all read "international". Group and guarantee them by that underlying lean
    # so a syndicated headline shared between a left and a centre wire is never collapsed to one voice.
    group_key = lambda n: (lean_of(n), info.underlying_lean(n) if lean_of(n) == "international" else None)
    groups = report_groups(articles, group_key, owner_of)
    stamps = [t for t in (_published_ts(a) for a in articles) if t is not None]
    ts_lo = min(stamps) if stamps else 0.0
    ts_span = (max(stamps) - ts_lo) if stamps else 0.0

    reports = []                                        # one representative per independent report
    for g in groups:
        rep = max(g, key=lambda a: (_quality(a, info, ts_lo, ts_span), -int(a.get("id") or 0)))
        reports.append((rep, lean_of(rep["source"])))

    picked, taken, regions, per_lean, intl_leans = [], set(), set(), {}, set()

    def gain(rep, lean, thin_bonus):
        g = _quality(rep, info, ts_lo, ts_span)
        reg = info.region(rep["source"])
        if reg and reg not in regions:
            g += BONUS_NEW_REGION
        if lean == "international":
            u = info.underlying_lean(rep["source"])
            if u and u not in intl_leans:
                g += BONUS_NEW_UNDERLYING            # each potential World-story side is heard before any repeats
        if thin_bonus:
            g += BONUS_THIN_LEAN / (1 + per_lean.get(lean, 0))
        return g

    def take(rep, lean):
        picked.append(rep)
        taken.add(id(rep))
        per_lean[lean] = per_lean.get(lean, 0) + 1
        reg = info.region(rep["source"])
        if reg:
            regions.add(reg)
        if lean == "international":
            u = info.underlying_lean(rep["source"])
            if u:
                intl_leans.add(u)

    for lean in ("left", "center", "right", "international", "unrated"):        # ideological guarantee
        pool = [(r, l) for r, l in reports if l == lean]
        # the international tier stands for up to three sides on a World story, so it gets one slot per side
        for _ in range(max(min_per_lean, 3) if lean == "international" else min_per_lean):
            cand = [(r, l) for r, l in pool if id(r) not in taken]
            if not cand or len(picked) >= k:
                break
            r, l = max(cand, key=lambda rl: (gain(rl[0], rl[1], False), -int(rl[0].get("id") or 0)))
            take(r, l)
    while len(picked) < k:                                                       # fill by marginal gain
        cand = [(r, l) for r, l in reports if id(r) not in taken]
        if not cand:
            break
        # rated outlets always fill before the unrated long tail (the pre-existing guard: an unknown
        # domain never takes a slot from a registry outlet); the score ranks WITHIN each tier
        r, l = max(cand, key=lambda rl: (rl[1] != "unrated", gain(rl[0], rl[1], True), -int(rl[0].get("id") or 0)))
        take(r, l)
    return picked
