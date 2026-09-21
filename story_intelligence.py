"""
story_intelligence.py - Story Intelligence v1: what is INSIDE a story.

Paksh already knows which articles belong to one story (cluster.py -> events) and how stories relate to older stories
(context_retrieval -> relationship_judgment -> story_memory). What it did not know is what those articles actually ADD:
which reports are independent acts of reporting, which merely repeat one another, what changed over time, and where
reported figures disagree. This module derives that, deterministically (NO LLM in v1, so no cost, no rate limits, no
non-determinism), from data Paksh already holds: headlines, excerpts, publisher/owner, timestamps and the cached
bge-m3 vectors.

Shape: RETRIEVE -> JUDGE -> UPDATE, the same as Phase 21, applied within one story:
  RETRIEVE  for each article, candidate earlier articles of THE SAME STORY (bounded: a story has <= MAX_ARTICLES
            articles, so this is never a global pairwise scan) - nearest by cached vector / token overlap.
  JUDGE     rule-based independence classification and development detection with explicit evidence.
  UPDATE    idempotent, versioned rows in the additive si_* tables; `detected_at` is never rewritten.
The module is isolated exactly like story_memory.py: database.init_db() never calls it, only refresh's optional
step and the tools below do. Read the results through story_graph.py.

What it will NOT claim (these are product rules, encoded in the vocabulary):
  * A different publisher is not evidence of independence -> the classes are INDEPENDENT / DERIVED /
    ATTRIBUTED_REPETITION / UNCERTAIN, and UNCERTAIN is a first-class, common outcome (excerpts average ~100 chars).
  * "Independently reported" is not "verified true". Nothing here says anything is true.
  * "Contradictory figures" is not "false". A CONTRADICTS edge means two reports state different numbers.
  * More coverage is not a development. A development needs a typed cue (arrest, court order, ...) that no earlier
    article carried, or a changed figure.
  * Timestamps are never merged: `published_at` is the publisher's claim, `first_seen_at` is when Paksh fetched the
    article, `detected_at` is when this module first derived the row, `event_time` (when the thing happened) is left
    NULL unless a source states it (v1 does not infer it).

CLI (read-only unless --persist):  py story_intelligence.py --recent 30 --limit 200 [--persist]
"""
import functools
import hashlib
import json
import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

ENGINE_VERSION = "si-1"
MAX_ARTICLES = 80            # a story larger than this is analysed on its 80 earliest articles (bounded work)

INDEPENDENT = "INDEPENDENT"
DERIVED = "DERIVED"
ATTRIBUTED_REPETITION = "ATTRIBUTED_REPETITION"
UNCERTAIN = "UNCERTAIN"
CLASSES = (INDEPENDENT, DERIVED, ATTRIBUTED_REPETITION, UNCERTAIN)

# ---- thresholds (deliberately conservative; tuned on the evaluation sample, see docs) ----
NEAR_DUP_JACCARD = 0.70      # same-language headline+excerpt token overlap
NEAR_DUP_COS_SAME = 0.965    # same-language embedding cosine
NEAR_DUP_COS_CROSS = 0.96    # cross-language embedding cosine
RESTATE_COS = 0.80           # same-language cosine at/above which a different publisher is restating the earlier report
PARAPHRASE_COS = 0.76        # ...and at/above which we cannot tell a paraphrase from a separate report (-> UNCERTAIN)
DEV_SAME_EVENT_COS = 0.75    # a development must come from an article clearly about the same event as some earlier article
SAME_EVENT_COS = 0.70        # below this the article is only loosely related (feature / angle / off-topic), never "independent"
CLOCK_SKEW = timedelta(minutes=10)


# =====================================================================================
# time
# =====================================================================================

def parse_time(s):
    """-> (naive-UTC datetime | None, precision 'time' | 'date' | None). Never raises."""
    if not s:
        return None, None
    s = str(s).strip()
    try:
        m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", s)
        if m:
            return datetime(int(m[1]), int(m[2]), int(m[3])), "date"
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return datetime.fromisoformat(s), "date"
        if re.match(r"\d{4}-\d{2}-\d{2}[T ]\d", s):
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if d.tzinfo:
                d = d.astimezone(timezone.utc).replace(tzinfo=None)
            return d, "time"
        d = parsedate_to_datetime(s)                       # RFC 822 ("Sun, 20 Sep 2026 10:00:00 +0530")
        if d.tzinfo:
            d = d.astimezone(timezone.utc).replace(tzinfo=None)
        return d, "time"
    except Exception:
        return None, None


def order_time(pub_raw, fetched_raw):
    """The time used to ORDER an article, and how trustworthy it is.
    -> (datetime, basis) with basis 'published' | 'published_date' | 'fetched'. The raw claim is stored separately and
    never altered; a published time later than the fetch time (clock skew, 2.7% of articles) is not believed."""
    pub, prec = parse_time(pub_raw)
    fetched, _ = parse_time(fetched_raw)
    if pub is not None:
        if fetched is not None and pub > fetched + CLOCK_SKEW and not (prec == "date" and pub.date() <= fetched.date()):
            pass                                            # a claim from the future: fall through to fetched
        elif prec == "time":
            return pub, "published"
        else:
            return pub, "published_date"
    if fetched is not None:
        return fetched, "fetched"
    return datetime(1970, 1, 1), "none"


# =====================================================================================
# text signals
# =====================================================================================

_LATIN_STOP = set("""the and for with from that this have has had are was were will would could should about after before over
under into onto than then them they their there here what when where which while who whom whose why how not but you your our his her
its says said say new news live update updates latest breaking video photos watch report reports reported amid also more most
one two three four five six seven eight nine ten first last year years day days week today""".split())
_HI_STOP = set("के की का में से है हैं को और पर ने भी यह वह एक इस उस कि लिए तो था थे थी जा रहा रही रहे हो गया गई गए बाद कर करने साथ".split())
_MONTHS_DAYS = set("""january february march april may june july august september october november december monday tuesday
wednesday thursday friday saturday sunday""".split())


def _tokens(text):
    text = (text or "").lower()
    lat = {t for t in re.findall(r"[a-z][a-z0-9]{2,}", text) if t not in _LATIN_STOP}
    hi = {t for t in re.findall(r"[ऀ-ॿ]{2,}", text) if t not in _HI_STOP}
    return lat | hi


def _norm_title(t):
    """Headline without a trailing ' - Outlet' / ' | Outlet' suffix (so copies aren't penalised for the byline)."""
    t = re.sub(r"\s+[-|–—]\s+[^-|–—]{2,40}$", "", (t or "").strip())
    return t


def _body(a):
    """Headline plus excerpt - but the excerpt is dropped when it merely repeats the headline (very common)."""
    t = _norm_title(a["title"])
    ex = (a.get("summary") or "").strip()
    if ex and _tokens(ex) <= _tokens(t):
        ex = ""
    return (t + ". " + ex).strip(". ")


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


_DEVA_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_WORDNUM = {"two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
            "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
            "eighteen": "18", "nineteen": "19", "twenty": "20"}
_NUM_RX = re.compile(r"(?<![A-Za-z0-9])(\d[\d,]*(?:\.\d+)?)(\s?[kK](?![A-Za-z]))?|\b(" + "|".join(_WORDNUM) + r")\b", re.I)


def numbers_in(text):
    """Canonical numeric facts in a text: '4' == 'Four', '$5K' == '$5,000', '७' == '7'. (Formatting must never look like a new fact.)"""
    out = set()
    for m in _NUM_RX.finditer((text or "").translate(_DEVA_DIGITS)):
        if m.group(3):
            out.add(_WORDNUM[m.group(3).lower()])
            continue
        raw = m.group(1).replace(",", "")
        try:
            v = float(raw) * (1000 if m.group(2) else 1)
        except ValueError:
            continue
        out.add(("%f" % v).rstrip("0").rstrip("."))
    return out


def _anchors(text):
    """Facts a report can add: numbers, and mid-sentence capitalised words (names/places), Latin text only. Hindi text
    contributes only numbers - v1 has no honest way to pick names out of Devanagari."""
    out = numbers_in(text)
    words = re.findall(r"\S+", text or "")
    alpha = [w for w in words if re.sub(r"[^A-Za-z]", "", w)]
    if alpha and sum(1 for w in alpha if re.sub(r"[^A-Za-z]", "", w)[0].isupper()) / len(alpha) >= 0.6:
        return out                                       # Title Case headline: capitalisation carries no information
    for i, w in enumerate(words):
        w2 = re.sub(r"[^A-Za-z]", "", w)
        if i > 0 and len(w2) >= 4 and w2[0].isupper() and not w2.isupper() and w2.lower() not in _MONTHS_DAYS \
                and w2.lower() not in _LATIN_STOP:
            out.add(w2.lower())
    return out


WIRES = {"PTI": "PTI", "ANI": "ANI", "IANS": "IANS", "UNI": "UNI", "REUTERS": "Reuters", "AFP": "AFP", "AP": "AP",
         "BLOOMBERG": "Bloomberg", "भाषा": "PTI-Bhasha", "पीटीआई": "PTI", "एएनआई": "ANI", "आईएएनएस": "IANS"}
_WIRE_ALT = "|".join(sorted((re.escape(k) for k in WIRES), key=len, reverse=True))
# "(PTI)", "- PTI", "| ANI", "said news agency ANI", "as reported by Reuters", "according to PTI"
_WIRE_TAG = re.compile(r"(?:\(|[-–—|]\s*|news agency\s+|agency\s+|reported by\s+|according to\s+|told\s+|via\s+|source:\s*)(" + _WIRE_ALT + r")\b\)?",
                       re.I)
_GENERIC_ATTRIB = re.compile(r"\b(media reports?(?: say)?|news reports?|reports? say|according to (?:media )?reports?|as per (?:media )?reports?|reportedly|"
                             r"sources (?:say|said)|unnamed sources)\b", re.I)
_NAMED_CUE = ("according to", "as reported by", "reported by", "first reported by", "reports", "reported", "told", "said",
              "citing", "per", "via")


def _name_tokens():
    return _publisher_name_tokens()


@functools.lru_cache(maxsize=1)
def _publisher_name_tokens():
    return frozenset(t for n in _publisher_names() for t in re.findall(r"[a-z]{3,}", n.lower()))


def _publisher_names():
    try:
        import sources
        return sorted({s["name"] for s in sources.SOURCES if len(s["name"]) >= 4}, key=len, reverse=True)
    except Exception:
        return []


@functools.lru_cache(maxsize=4)
def _named_regexes(names):
    """One compiled pair of regexes for ALL publisher names (compiling one per name per article was 100x slower)."""
    if not names:
        never = re.compile(r"(?!x)x")
        return never, never
    alt = "|".join(re.escape(n) for n in names)                       # names arrive longest-first
    cues = "|".join(re.escape(c) for c in _NAMED_CUE)
    fwd = re.compile(r'\b(' + cues + r')\s+(?:the\s+)?(' + alt + r')\b')
    back = re.compile(r'\b(' + alt + r')\s+(' + cues + r')\b')
    return fwd, back


def _canon(names, matched):
    low = matched.lower()
    return next((n for n in names if n.lower() == low), None)


def find_attribution(a, publisher_names=None):
    """Explicit attributions in an article's headline/excerpt -> list of dicts
    {'kind': 'wire'|'outlet', 'name': str, 'cue': str}. Only patterns that say 'this came from X' count."""
    text = f"{a['title']} . {a.get('summary') or ''}"
    out, seen = [], set()
    for m in _WIRE_TAG.finditer(text):
        key = WIRES.get(m.group(1).upper(), WIRES.get(m.group(1)))
        if key and key.lower() != (a["source"] or "").lower() and ("wire", key) not in seen:
            seen.add(("wire", key))
            out.append({"kind": "wire", "name": key, "cue": m.group(0).strip()})
    g = _GENERIC_ATTRIB.search(text)
    if g:
        out.append({"kind": "generic", "name": "unnamed reports", "cue": g.group(0).lower()})
    names = tuple(publisher_names if publisher_names is not None else _publisher_names())
    fwd, back = _named_regexes(names)
    own = (a["source"] or "").lower()
    for rx, grp in ((fwd, 2), (back, 1)):
        for m in rx.finditer(text):
            n = _canon(names, m.group(grp))
            if n and n.lower() != own and ("outlet", n) not in seen:
                seen.add(("outlet", n))
                out.append({"kind": "outlet", "name": n, "cue": (m.group(1) if grp == 2 else m.group(2)).lower()})
    return out


# ---- quantity claims ----------------------------------------------------------------
_NUMWORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
             "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
             "eighteen": 18, "nineteen": 19, "twenty": 20}
_N = r"(\d[\d,]*(?:\.\d+)?|" + "|".join(_NUMWORDS) + r")"
CUMULATIVE = {"deaths", "injured", "arrested", "missing"}      # tolls only ever rise in honest updates
_CLAIM_PATTERNS = [
    ("deaths", re.compile(_N + r"\s+(?:people\s+|persons\s+|passengers\s+|workers\s+|devotees\s+)?(?:were\s+|are\s+)?(?:killed|dead|died|dies|lost their lives)\b", re.I)),
    ("deaths", re.compile(r"\b(?:kills?|killing|killed)\s+(?:at least\s+|over\s+)?" + _N + r"\b", re.I)),
    ("deaths", re.compile(r"death toll[^\d]{0,30}" + _N, re.I)),
    ("deaths", re.compile(r"(\d[\d,]*)\s*(?:लोगों\s*)?की\s*मौत")),
    ("injured", re.compile(_N + r"\s+(?:people\s+|persons\s+)?(?:were\s+|are\s+)?(?:injured|hurt|wounded)\b", re.I)),
    ("injured", re.compile(r"(\d[\d,]*)\s*(?:लोग\s*)?घायल")),
    ("arrested", re.compile(_N + r"\s+(?:people\s+|persons\s+|accused\s+|men\s+)?(?:were\s+|are\s+)?(?:arrested|detained)\b", re.I)),
    ("arrested", re.compile(r"(\d[\d,]*)\s*(?:आरोपी\s*|लोग\s*)?गिरफ्तार")),
    ("missing", re.compile(_N + r"\s+(?:people\s+|persons\s+)?(?:remain\s+|are\s+|were\s+)?missing\b", re.I)),
    ("money_crore", re.compile(r"(?:rs\.?|₹|inr)\s*([\d,]+(?:\.\d+)?)\s*(?:crore|cr)\b", re.I)),
    ("percent", re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|per\s?cent|percent)", re.I)),
    ("seats", re.compile(r"\b(\d{1,3})\s+seats\b", re.I)),
]


def extract_claims(a):
    """Quantity claims in the headline + excerpt: [{'key','value','span'}], at most one per key (the first)."""
    text = f"{_norm_title(a['title'])}. {a.get('summary') or ''}"
    out, seen = [], set()
    for key, rx in _CLAIM_PATTERNS:
        if key in seen:
            continue
        m = rx.search(text)
        if not m:
            continue
        raw = m.group(1).lower().replace(",", "")
        try:
            val = float(_NUMWORDS[raw]) if raw in _NUMWORDS else float(raw)
        except ValueError:
            continue
        if key == "percent" and val > 100:
            continue
        seen.add(key)
        out.append({"key": key, "value": val, "span": text[max(0, m.start() - 20):m.end() + 20].strip()})
    return out


# ---- developments -------------------------------------------------------------------
# Extensible taxonomy: name -> compiled cue. A development is a cue present in an article and absent from every earlier
# article of the story. Keep cues specific: a vague word (say, announce) would turn ordinary coverage into "developments".
DEVELOPMENT_TYPES = {}          # name -> (strict cue that can TRIGGER a development, lenient cue used to decide "was it already there?")
_NOT_A_CHANGE = re.compile(r"^(?:opinion|analysis|editorial|explained|watch|live)\b|\?|\b(?:calls? for|call for|demands?|urges?|could|may|might|would|"
                           r"if|plans? to|set to|likely to|threatens?|seeks?|pleads?|what (?:is|are|to)|why|how)\b[^.]{0,40}$"
                           r"|(?:कब|क्या|कैसे|क्यों|जानें)", re.I)


def register_development_type(name, patterns, seen_patterns=None):
    DEVELOPMENT_TYPES[name] = (re.compile("|".join(patterns), re.I), re.compile("|".join(seen_patterns or patterns), re.I))


register_development_type("ARREST", [r"\barrest(?:ed|s)?\b", r"\bnabbed\b", r"\btaken into custody\b", r"गिरफ्तार", r"हिरासत में"],
                          [r"\barrest", r"\bnabbed\b", r"\bcustody\b", r"\bheld\b", r"\bdetain", r"\bcaught\b", r"गिरफ्तार", r"हिरासत", r"पकड़"])
register_development_type("RESIGNATION_OR_REMOVAL", [r"\bresign(?:s|ed|ation)?\b", r"\bsacked\b", r"\bdismissed from\b", r"\bremoved as\b", r"\bsuspended\b",
                                                      r"इस्तीफ", r"बर्खास्त", r"निलंबित"],
                          [r"\bresign", r"\bquits?\b", r"\bstep(?:s|ped)? down\b", r"\bsack", r"\bremov", r"\bsuspen", r"\boust", r"इस्तीफ", r"बर्खास्त", r"निलंबित"])
register_development_type("COURT_OR_LEGAL_ORDER", [r"\b(?:high|supreme) court\b(?! must)", r"\b(?:SC|HC)\b", r"\bcourt (?:orders|directs|stays|quashes|rejects|dismisses|grants|refuses)\b",
                                                    r"\bbail\b", r"\bconvicted\b", r"\bsentenced\b", r"\bverdict\b", r"\bjudge (?:blocks|rules|orders|sets)\b",
                                                    r"जमानत", r"दोषी", r"सजा सुनाई", r"हाईकोर्ट", r"सुप्रीम कोर्ट"],
                          [r"\bcourt\b", r"\b(?:SC|HC)\b", r"\bjudge", r"\bbail\b", r"\bconvict", r"\bsentenc", r"\bverdict", r"\bruling\b", r"\bblocks\b", r"जमानत",
                           r"दोषी", r"सजा", r"कोर्ट", r"अदालत"])
register_development_type("INVESTIGATION_LAUNCHED", [r"\bFIR\b", r"\bprobe (?:ordered|launched|begins)\b", r"\b(?:orders|ordered|launches|launched) (?:a )?(?:probe|inquiry|investigation)\b",
                                                      r"\bSIT\b", r"\bCBI\b", r"\braid(?:s|ed)?\b", r"मामला दर्ज", r"जांच के आदेश", r"छापेमारी"],
                          [r"\bFIR\b", r"\bprobe\b", r"\binquiry\b", r"\binvestigat", r"\bSIT\b", r"\bCBI\b", r"\braid", r"\bcase (?:registered|filed)\b", r"मामला दर्ज", r"जांच", r"छापे"])
register_development_type("OFFICIAL_DENIAL_OR_CLARIFICATION", [r"\bdenies\b", r"\bdenied\b", r"\brejects claim\b", r"\bclarif(?:ies|ied)\b", r"\bapolog(?:ise|ises|ised|ize|izes|ized)\b",
                                                                r"खंडन", r"सफाई दी", r"माफी"],
                          [r"\bden(?:y|ies|ied|ial)\b", r"\bclarif", r"\bapolog", r"\bdismisses claim", r"खंडन", r"सफाई", r"माफी"])
register_development_type("POLICY_OR_FORMAL_DECISION", [r"\bcabinet (?:approves|clears|okays)\b", r"\bnotif(?:ies|ied)\b", r"(?<!calls for )(?<!call for )\b(?:bans|banned|banning)\b",
                                                         r"\blifts? ban\b", r"\bbarred\b", r"\bbars\b", r"मंजूरी दी", r"प्रतिबंध लगा"],
                          [r"\bcabinet\b", r"\bnotif", r"\bban(?:s|ned|ning)?\b", r"\bbarr?(?:s|ed|ing)\b", r"मंजूरी", r"प्रतिबंध"])
register_development_type("RESOLUTION_OR_RESTORATION", [r"\brescued\b", r"\bcalled off\b", r"\bceasefire\b", r"\bwithdrawn\b", r"\bservices? (?:restored|resume[sd]?)\b", r"बचाया गया"],
                          [r"\brescu", r"\bcalled off\b", r"\bceasefire\b", r"\bwithdraw", r"\brestor", r"\bresum", r"बचाव", r"बचाया"])
register_development_type("ESCALATION_OR_UNREST", [r"\bcurfew\b", r"\bstone[- ]pelting\b", r"\briots?\b", r"\bclashes (?:erupt|break out)\b", r"कर्फ्यू", r"दंगे"],
                          [r"\bcurfew\b", r"\bstone[- ]pelting\b", r"\briot", r"\bclash", r"\bviolen", r"\bprotest", r"कर्फ्यू", r"दंगे", r"हिंसा", r"प्रदर्शन"])


def find_dev_cues(a, lenient=False):
    """Development types cued in the HEADLINE (excerpts are too often boilerplate) -> {type: matched text}.
    strict = may trigger a development; lenient = looser stems, used only to decide whether the thing was already in the story.
    Opinion pieces, questions and hypotheticals ('calls for a ban', 'could be arrested') never trigger."""
    t = _norm_title(a["title"])
    if not lenient and _NOT_A_CHANGE.search(t):
        return {}
    out = {}
    for name, (strict, seen) in DEVELOPMENT_TYPES.items():
        m = (seen if lenient else strict).search(t)
        if m:
            out[name] = m.group(0)
    return out


# =====================================================================================
# per-story derivation (pure - no DB)
# =====================================================================================

@dataclass
class Art:
    id: int
    source: str
    owner: str
    language: str
    title: str
    summary: str
    published: str
    fetched_at: str
    vec: object = None
    # derived
    order: datetime = None
    basis: str = ""
    toks: set = field(default_factory=set)
    anchors: set = field(default_factory=set)

    def d(self):
        return {"id": self.id, "source": self.source, "title": self.title, "summary": self.summary}


def _own_tokens(a):
    """Outlet names leak into headlines (' - The Hindu BusinessLine', 'Toronto Star', 'NDTV's'): never count them as new facts."""
    return {t.rstrip("s") for t in re.findall(r"[a-z]{3,}", a.source.lower())} | {t for t in re.findall(r"[a-z]{3,}", a.source.lower())}


def _cos(a, b):
    if a is None or b is None or a.shape != b.shape:
        return None
    na, nb = float((a * a).sum()) ** .5, float((b * b).sum()) ** .5
    if not na or not nb:
        return None
    return float((a * b).sum() / (na * nb))


def _ambiguous(x, y):
    """Is the order of these two articles uncertain? (date-only / fetched-time bases on the same day, or seconds apart.)"""
    if abs((x.order - y.order).total_seconds()) < 60:
        return True
    weak = lambda a: a.basis != "published"
    return (weak(x) or weak(y)) and x.order.date() == y.order.date()


def analyze_story(rows, owner_of=None, publisher_names=None):
    """rows: list of dicts with id, source, language, title, summary, published, fetched_at, optional vec (np.ndarray).
    -> dict with keys: articles, reporting_events, developments, claims, relationships, stats.  Pure and deterministic."""
    owner_of = owner_of or (lambda n: n)
    arts = []
    for r in rows:
        a = Art(id=r["id"], source=r["source"], owner=owner_of(r["source"]), language=(r.get("language") or "en"),
                title=r["title"] or "", summary=r.get("summary") or "", published=r.get("published") or "",
                fetched_at=r.get("fetched_at") or "", vec=r.get("vec"))
        a.order, a.basis = order_time(a.published, a.fetched_at)
        body = _body(a.d())
        a.toks = _tokens(body)
        a.anchors = _anchors(body) if a.language == "en" else numbers_in(body)
        a.anchors = {x for x in a.anchors if x[0].isdigit() or (x not in _publisher_name_tokens() and x not in _own_tokens(a))}
        arts.append(a)
    arts.sort(key=lambda a: (a.order, a.id))
    arts = arts[:MAX_ARTICLES]
    by_id = {a.id: a for a in arts}
    pub_names = publisher_names if publisher_names is not None else _publisher_names()

    roles = {}          # article id -> dict(role, target (article id|None), external (str|None), reason, confidence, evidence)
    for i, b in enumerate(arts):
        earlier = arts[:i]
        att = find_attribution(b.d(), pub_names)
        ev = {}
        # 1. explicit attribution
        named = [x for x in att if x["kind"] == "outlet"]
        wires = [x for x in att if x["kind"] == "wire"]
        target = None
        for x in named:
            for a in earlier:
                if a.source.lower() == x["name"].lower() or a.owner.lower() == owner_of(x["name"]).lower():
                    target = a
                    break
            if target:
                roles[b.id] = dict(role=ATTRIBUTED_REPETITION, target=target.id, external=None, reason="ATTRIBUTED_TO_OUTLET_IN_STORY",
                                   confidence=0.85, evidence={"attribution": x})
                break
        if b.id in roles:
            continue
        if named:
            roles[b.id] = dict(role=ATTRIBUTED_REPETITION, target=None, external=named[0]["name"], reason="ATTRIBUTED_TO_OUTLET_NOT_IN_STORY",
                               confidence=0.7, evidence={"attribution": named[0]})
            continue
        if wires:
            roles[b.id] = dict(role=ATTRIBUTED_REPETITION, target=None, external=wires[0]["name"], reason="WIRE_ATTRIBUTION",
                               confidence=0.8, evidence={"attribution": wires[0]})
            continue
        generic = [x for x in att if x["kind"] == "generic"]
        if generic:
            roles[b.id] = dict(role=ATTRIBUTED_REPETITION, target=None, external=None, reason="SECONDHAND_CUE", confidence=0.55,
                               evidence={"attribution": generic[0]})
            continue
        # 2. same owner as an earlier article: one newsroom / group is one voice
        same_owner = [a for a in earlier if a.owner == b.owner]
        if same_owner:
            a = same_owner[-1]
            roles[b.id] = dict(role=DERIVED, target=a.id, external=None, reason="SAME_OWNER", confidence=0.7,
                               evidence={"kind": "voice_accounting", "owner": b.owner, "earlier_source": a.source,
                                         "note": "same publisher/owner group: counts as one voice (one vote per owner); says nothing about copying"})
            continue
        # 3. near-duplicate of an earlier article from another owner
        best, best_sim, kind = None, 0.0, None
        for a in earlier:
            na, nb = {x for x in a.anchors if x[0].isdigit()}, {x for x in b.anchors if x[0].isdigit()}
            if na and nb and na != nb:
                continue                                  # a changed figure is a different report (an update), not a copy
            if a.language == b.language:
                j = jaccard(a.toks, b.toks)
                c = _cos(a.vec, b.vec)
                sim = max(j if j >= NEAR_DUP_JACCARD else 0.0, c if (c is not None and c >= NEAR_DUP_COS_SAME) else 0.0)
                k = "jaccard" if (j >= NEAR_DUP_JACCARD and (c is None or j >= c or c < NEAR_DUP_COS_SAME)) else "cosine"
            else:
                c = _cos(a.vec, b.vec)
                sim = c if (c is not None and c >= NEAR_DUP_COS_CROSS) else 0.0
                k = "cosine_cross_language"
            if sim > best_sim:
                best, best_sim, kind = a, sim, k
        if best is not None:
            conf = 0.55 + 0.4 * min(1.0, (best_sim - 0.6) / 0.4)
            if _ambiguous(best, b):
                conf = min(conf, 0.5)
            roles[b.id] = dict(role=DERIVED, target=best.id, external=None, reason="NEAR_DUPLICATE_TEXT", confidence=round(conf, 2),
                               evidence={"similarity": round(best_sim, 3), "measure": kind, "earlier_source": best.source,
                                         "order_ambiguous": _ambiguous(best, b)})
            continue
        # 3b. same-language restatement by a different publisher (high embedding similarity, different words)
        same_lang_earlier = [a for a in earlier if a.language == b.language]
        best_c, best_a, best_conflict = None, None, False
        for a in same_lang_earlier:
            c = _cos(a.vec, b.vec)
            na, nb = {x for x in a.anchors if x[0].isdigit()}, {x for x in b.anchors if x[0].isdigit()}
            conflicting = bool(na and nb and na.isdisjoint(nb))   # they state different figures: not a restatement
            if c is not None and (best_c is None or c > best_c):
                best_c, best_a, best_conflict = c, a, conflicting
        if best_c is not None and best_c >= RESTATE_COS and not best_conflict:
            roles[b.id] = dict(role=DERIVED, target=best_a.id, external=None, reason="RESTATES_EARLIER_REPORT",
                               confidence=round(0.5 + 0.3 * min(1.0, (best_c - RESTATE_COS) / 0.08), 2),
                               evidence={"similarity": round(best_c, 3), "measure": "cosine", "earlier_source": best_a.source,
                                         "order_ambiguous": _ambiguous(best_a, b),
                                         "note": "same facts restated; whether it was copied or re-reported cannot be told from headlines"})
            continue
        # 4. no derivation evidence: independent only with positive evidence, otherwise honestly uncertain
        if i == 0:
            nxt = arts[1] if len(arts) > 1 else None
            amb = bool(nxt is not None and _ambiguous(b, nxt))
            roles[b.id] = dict(role=INDEPENDENT, target=None, external=None, reason="EARLIEST_IN_CORPUS",
                               confidence=0.4 if amb else 0.5, evidence={"order_basis": b.basis, "order_ambiguous": amb,
                                                                          "note": "no earlier report in Paksh's corpus to derive from"})
            continue
        if not same_lang_earlier:
            roles[b.id] = dict(role=UNCERTAIN, target=None, external=None, reason="CROSS_LANGUAGE_NO_TEXTUAL_BASIS", confidence=0.3,
                               evidence={"note": "no earlier article in this language to compare against"})
            continue
        seen = set().union(*(a.anchors for a in same_lang_earlier))
        novel = sorted(b.anchors - seen)
        all_nums = set().union(*(a.anchors for a in earlier)) if earlier else set()
        novel_nums = sorted(x for x in b.anchors if x[0].isdigit() and x not in all_nums)
        if best_c is None:                                   # no cached vectors: text evidence only, held to a higher bar
            if novel_nums and len(novel) >= 2:
                roles[b.id] = dict(role=INDEPENDENT, target=None, external=None, reason="ADDS_NEW_FACTS_TEXT_ONLY", confidence=0.4,
                                   evidence={"novel_anchors": novel[:6]})
            else:
                roles[b.id] = dict(role=UNCERTAIN, target=None, external=None, reason="NO_POSITIVE_EVIDENCE", confidence=0.35,
                                   evidence={"note": "distinct publisher, but nothing shows it reported independently"})
        elif best_c >= PARAPHRASE_COS:
            roles[b.id] = dict(role=UNCERTAIN, target=None, external=None, reason="POSSIBLE_PARAPHRASE", confidence=0.35,
                               evidence={"similarity": round(best_c, 3), "nearest_source": best_a.source, "novel_anchors": novel[:6]})
        elif best_c >= SAME_EVENT_COS and novel_nums:
            roles[b.id] = dict(role=INDEPENDENT, target=None, external=None, reason="NEW_SPECIFIC_FIGURES",
                               confidence=round(min(0.65, 0.5 + 0.05 * (len(novel_nums) - 1)), 2),
                               evidence={"similarity_to_nearest_earlier": round(best_c, 3), "novel_figures": novel_nums[:6],
                                         "note": "same event, and states figures no earlier report in Paksh carried"})
        elif best_c >= SAME_EVENT_COS:
            roles[b.id] = dict(role=UNCERTAIN, target=None, external=None, reason="NO_POSITIVE_EVIDENCE", confidence=0.4,
                               evidence={"similarity": round(best_c, 3), "note": "distinct publisher and wording, but no new figures or facts to show independent reporting"})
        else:
            roles[b.id] = dict(role=UNCERTAIN, target=None, external=None, reason="LOOSELY_RELATED", confidence=0.3,
                               evidence={"similarity": round(best_c, 3), "note": "a feature/angle/related piece rather than a report of the same event"})

    # ---- reporting events: connected components over in-story links, plus one group per external origin ----
    parent = {a.id: a.id for a in arts}
    ext_first = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    for a in arts:
        r = roles[a.id]
        if r["target"] is not None:
            union(a.id, r["target"])
        elif r["external"]:
            k = r["external"]
            if k in ext_first:
                union(a.id, ext_first[k])
            else:
                ext_first[k] = a.id
    comps = {}
    for a in arts:
        comps.setdefault(find(a.id), []).append(a)
    reporting_events = []
    for members in comps.values():
        members.sort(key=lambda a: (a.order, a.id))
        root = members[0]
        rr = roles[root.id]
        externals = sorted({roles[m.id]["external"] for m in members if roles[m.id]["external"]})
        if externals:
            indep, reason = ATTRIBUTED_REPETITION, "ORIGIN_OUTSIDE_CORPUS:" + ",".join(externals)
            conf = min(roles[m.id]["confidence"] for m in members if roles[m.id]["external"])
        else:
            indep, reason, conf = rr["role"], rr["reason"], rr["confidence"]
        reporting_events.append({"root_article_id": root.id, "independence": indep, "reason": reason, "confidence": conf,
                                 "origin_external": externals, "members": [m.id for m in members],
                                 "first_published_at": (root.published or None), "first_order_time": root.order.isoformat(),
                                 "order_basis": root.basis})
    reporting_events.sort(key=lambda e: (e["first_order_time"], e["root_article_id"]))
    ev_of = {m: e["root_article_id"] for e in reporting_events for m in e["members"]}
    for a in arts:                                   # roots of a group that has an INDEPENDENT/UNCERTAIN class keep their role;
        roles[a.id]["reporting_event_root"] = ev_of[a.id]   # every other member is recorded as what it is

    # ---- claims, updates, contradictions ----
    # Every quantity is STORED as a claim, but only person-count tallies (deaths / injured / arrested / missing) are COMPARED:
    # the first percentage or rupee figure in a headline rarely refers to the same measure across reports (18% vs 17.5% is
    # rounding; "Rs 72 cr on day 27" vs "Rs 86 cr on day 28" is a time series), so comparing them would invent contradictions.
    claims = []
    for a in arts:
        for c in extract_claims(a.d()):
            claims.append({"article_id": a.id, "key": c["key"], "value": c["value"], "span": c["span"], "reporting_event_root": ev_of[a.id]})
    relationships, developments = [], []
    for key in sorted(CUMULATIVE):
        groups = {}
        for c in sorted((c for c in claims if c["key"] == key), key=lambda c: (by_id[c["article_id"]].order, c["article_id"])):
            groups.setdefault(c["value"], []).append(c["article_id"])
        if len(groups) < 2:
            continue
        seq = sorted(groups, key=lambda v: (by_id[groups[v][0]].order, groups[v][0]))     # values in order of first appearance
        run_v = seq[0]
        for v in seq[1:]:
            ea, la = by_id[groups[run_v][0]], by_id[groups[v][0]]
            if ea.language != la.language and (_cos(ea.vec, la.vec) or 0) < 0.75:
                continue
            if ea.language == la.language and len(ea.toks & la.toks) < 2:
                continue                                       # not demonstrably about the same thing
            if min(v, run_v) >= 100 and abs(v - run_v) / max(v, run_v) < 0.05:
                continue                                       # 903 vs '900 mark': rounding, not a different figure
            amb = _ambiguous(ea, la)
            ev = {"key": key, "earlier": {"value": run_v, "article_ids": groups[run_v][:5]}, "later": {"value": v, "article_ids": groups[v][:5]},
                  "order_ambiguous": amb, "note": "two reports state different figures; this does not say which is right"}
            if v > run_v and not amb:
                relationships.append(("UPDATES", "claim", f"{ea.id}:{key}", "claim", f"{la.id}:{key}", 0.7, ev))
                developments.append({"type": "FIGURE_UPDATE", "trigger_article_id": la.id, "description": f"{key}: {run_v:g} -> {v:g}",
                                     "confidence": 0.7, "dev_key": f"FIGURE_UPDATE:{key}:{v:g}", "corroborating_owners": 1})
            else:
                relationships.append(("CONTRADICTS", "claim", f"{ea.id}:{key}", "claim", f"{la.id}:{key}", 0.6 if not amb else 0.45, ev))
            if v > run_v:
                run_v = v

    # ---- developments from typed cues ----
    # A development is a strict cue in an article when NO earlier article carried even a lenient form of it ("held" counts as
    # an arrest already reported), the story did not begin with it, and the article is about the same event, not a tangent.
    first_lenient, cue_owners = {}, {}
    for idx, a in enumerate(arts):
        for t in find_dev_cues(a.d(), lenient=True):
            first_lenient.setdefault(t, idx)
    baseline = set(find_dev_cues(arts[0].d(), lenient=True)) if arts else set()
    for idx, a in enumerate(arts):
        for t, txt in find_dev_cues(a.d()).items():
            cue_owners.setdefault(t, set()).add(a.owner)
            if idx == 0 or t in baseline or first_lenient.get(t) != idx or any(d["type"] == t for d in developments):
                continue
            near = [c for c in (_cos(x.vec, a.vec) for x in arts[:idx] if x.language == a.language) if c is not None]
            if near and max(near) < DEV_SAME_EVENT_COS:
                continue                                        # a tangent (grab-bag member), not a step in THIS story
            developments.append({"type": t, "trigger_article_id": a.id, "dev_key": f"{t}:{a.id}", "confidence": 0.45, "corroborating_owners": 1,
                                 "description": f"first appears in: \"{_norm_title(a.title)[:120]}\" (cue: {txt})"})
    for d in developments:
        if d["type"] in cue_owners:
            d["corroborating_owners"] = len(cue_owners[d["type"]])
            d["confidence"] = round(min(0.9, 0.45 + 0.15 * (d["corroborating_owners"] - 1)), 2)
    uniq = {}
    for d in developments:                                     # one row per natural key (several claim pairs can imply the same update)
        uniq.setdefault(d["dev_key"], d)
    developments = list(uniq.values())
    for d in developments:
        a = by_id[d["trigger_article_id"]]
        d["published_at"] = a.published or None
        d["first_seen_at"] = a.fetched_at or None
        d["event_time"] = None                                # never inferred in v1
        d["order_basis"] = a.basis
    developments.sort(key=lambda d: (by_id[d["trigger_article_id"]].order, d["dev_key"]))

    # ---- edges ----
    for a in arts:
        r = roles[a.id]
        if r["target"] is not None:
            relationships.append(("DERIVED_FROM", "article", str(a.id), "article", str(r["target"]), r["confidence"],
                                  {"reason": r["reason"], **r["evidence"]}))
        if ev_of[a.id] != a.id:
            relationships.append(("SAME_REPORTING_EVENT", "article", str(a.id), "article", str(ev_of[a.id]), r["confidence"], {"reason": r["reason"]}))
    indep_events = [e for e in reporting_events if e["independence"] == INDEPENDENT]
    if indep_events:
        first = indep_events[0]
        for e in indep_events[1:]:
            relationships.append(("INDEPENDENT_CORROBORATION", "reporting_event", str(e["root_article_id"]), "reporting_event",
                                  str(first["root_article_id"]), round(min(e["confidence"], first["confidence"]), 2),
                                  {"note": "reported independently; this does not establish that either report is true"}))
    for d in developments:
        relationships.append(("NEW_DEVELOPMENT", "article", str(d["trigger_article_id"]), "development", d["dev_key"], d["confidence"], {"type": d["type"]}))

    counts = {c: 0 for c in CLASSES}
    for a in arts:
        counts[roles[a.id]["role"]] += 1
    stats = {"articles": len(arts), "reporting_events": len(reporting_events), "role_counts": counts,
             "independent_events": len(indep_events), "developments": len(developments), "claims": len(claims),
             "contradictions": sum(1 for r in relationships if r[0] == "CONTRADICTS"),
             "distinct_owners": len({a.owner for a in arts})}
    return {"articles": [{"id": a.id, "source": a.source, "owner": a.owner, "language": a.language, "title": a.title,
                          "published": a.published or None, "fetched_at": a.fetched_at or None, "order_time": a.order.isoformat(),
                          "order_basis": a.basis, **roles[a.id]} for a in arts],
            "reporting_events": reporting_events, "developments": developments, "claims": claims,
            "relationships": relationships, "stats": stats}


# =====================================================================================
# persistence (additive, isolated, idempotent, versioned)
# =====================================================================================

_SCHEMA = """
CREATE TABLE IF NOT EXISTS si_story_state (
    event_id INTEGER PRIMARY KEY, engine_version TEXT NOT NULL, input_sig TEXT NOT NULL,
    n_articles INTEGER, computed_at TEXT NOT NULL, stats_json TEXT);
CREATE TABLE IF NOT EXISTS si_reporting_events (
    event_id INTEGER NOT NULL, root_article_id INTEGER NOT NULL, independence TEXT NOT NULL, confidence REAL, reason TEXT,
    origin_external TEXT, n_articles INTEGER, first_published_at TEXT, first_order_time TEXT, order_basis TEXT,
    engine_version TEXT NOT NULL, detected_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY (event_id, root_article_id));
CREATE TABLE IF NOT EXISTS si_reporting_event_articles (
    event_id INTEGER NOT NULL, article_id INTEGER NOT NULL, reporting_event_root INTEGER NOT NULL, role TEXT NOT NULL,
    derives_from_article_id INTEGER, derives_from_external TEXT, reason TEXT, confidence REAL, evidence_json TEXT,
    published_at TEXT, first_seen_at TEXT, order_time TEXT, order_basis TEXT,
    engine_version TEXT NOT NULL, detected_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY (event_id, article_id));
CREATE TABLE IF NOT EXISTS si_developments (
    event_id INTEGER NOT NULL, dev_key TEXT NOT NULL, type TEXT NOT NULL, description TEXT, trigger_article_id INTEGER,
    event_time TEXT, published_at TEXT, first_seen_at TEXT, order_basis TEXT, confidence REAL, corroborating_owners INTEGER,
    engine_version TEXT NOT NULL, detected_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY (event_id, dev_key));
CREATE TABLE IF NOT EXISTS si_claims (
    event_id INTEGER NOT NULL, article_id INTEGER NOT NULL, claim_key TEXT NOT NULL, value REAL NOT NULL, span TEXT,
    reporting_event_root INTEGER, engine_version TEXT NOT NULL, detected_at TEXT NOT NULL,
    PRIMARY KEY (event_id, article_id, claim_key));
CREATE TABLE IF NOT EXISTS si_relationships (
    event_id INTEGER NOT NULL, rel_type TEXT NOT NULL, src_kind TEXT NOT NULL, src_id TEXT NOT NULL,
    dst_kind TEXT NOT NULL, dst_id TEXT NOT NULL, confidence REAL, evidence_json TEXT,
    engine_version TEXT NOT NULL, detected_at TEXT NOT NULL,
    PRIMARY KEY (event_id, rel_type, src_kind, src_id, dst_kind, dst_id));
CREATE INDEX IF NOT EXISTS idx_si_rel_event ON si_relationships(event_id);
CREATE INDEX IF NOT EXISTS idx_si_dev_event ON si_developments(event_id);
CREATE INDEX IF NOT EXISTS idx_si_rea_event ON si_reporting_event_articles(event_id);
"""

SI_TABLES = ["si_story_state", "si_reporting_events", "si_reporting_event_articles", "si_developments", "si_claims", "si_relationships"]


def init_si_schema(conn):
    conn.executescript(_SCHEMA)
    conn.commit()


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def input_signature(rows):
    h = hashlib.sha256()
    h.update(ENGINE_VERSION.encode())
    for r in sorted(rows, key=lambda r: r["id"]):
        h.update(f"|{r['id']}:{r['source']}:{r.get('title') or ''}:{r.get('published') or ''}".encode("utf-8", "replace"))
    return h.hexdigest()[:24]


def persist_story(conn, event_id, result, sig, now=None):
    """Replace this story's derived rows in ONE transaction. Rows whose natural key already exists keep their original
    `detected_at` (never rewritten); rows whose key no longer exists (an article left the story) are removed."""
    now = now or _now()
    cur = conn.cursor()
    cur.execute("BEGIN")
    try:
        def prior(table, cols):
            return {tuple(r[:-1]): r[-1] for r in cur.execute(f"SELECT {cols}, detected_at FROM {table} WHERE event_id=?", (event_id,))}
        p_re = prior("si_reporting_events", "root_article_id")
        p_rea = prior("si_reporting_event_articles", "article_id")
        p_dev = prior("si_developments", "dev_key")
        p_cl = prior("si_claims", "article_id, claim_key")
        p_rel = prior("si_relationships", "rel_type, src_kind, src_id, dst_kind, dst_id")
        for t in ("si_reporting_events", "si_reporting_event_articles", "si_developments", "si_claims", "si_relationships"):
            cur.execute(f"DELETE FROM {t} WHERE event_id=?", (event_id,))
        for e in result["reporting_events"]:
            cur.execute("INSERT INTO si_reporting_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (event_id, e["root_article_id"], e["independence"], e["confidence"], e["reason"], ",".join(e["origin_external"]) or None,
                         len(e["members"]), e["first_published_at"], e["first_order_time"], e["order_basis"], ENGINE_VERSION,
                         p_re.get((e["root_article_id"],), now), now))
        for a in result["articles"]:
            cur.execute("INSERT INTO si_reporting_event_articles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (event_id, a["id"], a["reporting_event_root"], a["role"], a["target"], a["external"], a["reason"], a["confidence"],
                         json.dumps(a["evidence"], ensure_ascii=False, default=str), a["published"], a["fetched_at"], a["order_time"], a["order_basis"],
                         ENGINE_VERSION, p_rea.get((a["id"],), now), now))
        for d in result["developments"]:
            cur.execute("INSERT INTO si_developments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (event_id, d["dev_key"], d["type"], d["description"], d["trigger_article_id"], d["event_time"], d["published_at"],
                         d["first_seen_at"], d["order_basis"], d["confidence"], d["corroborating_owners"], ENGINE_VERSION,
                         p_dev.get((d["dev_key"],), now), now))
        for c in result["claims"]:
            cur.execute("INSERT OR REPLACE INTO si_claims VALUES (?,?,?,?,?,?,?,?)",
                        (event_id, c["article_id"], c["key"], c["value"], c["span"], c["reporting_event_root"], ENGINE_VERSION,
                         p_cl.get((c["article_id"], c["key"]), now)))
        for (rt, sk, si, dk, di, conf, ev) in result["relationships"]:
            cur.execute("INSERT OR REPLACE INTO si_relationships VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (event_id, rt, sk, si, dk, di, conf, json.dumps(ev, ensure_ascii=False, default=str), ENGINE_VERSION,
                         p_rel.get((rt, sk, si, dk, di), now)))
        cur.execute("INSERT OR REPLACE INTO si_story_state VALUES (?,?,?,?,?,?)",
                    (event_id, ENGINE_VERSION, sig, result["stats"]["articles"], now, json.dumps(result["stats"])))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# =====================================================================================
# orchestration
# =====================================================================================

def _load_rows(conn, event_ids):
    out = {}
    CH = 400
    for i in range(0, len(event_ids), CH):
        chunk = event_ids[i:i + CH]
        ph = ",".join("?" for _ in chunk)
        for r in conn.execute(f"SELECT id, event_id, source, language, title, summary, published, fetched_at FROM articles WHERE event_id IN ({ph})", chunk):
            out.setdefault(r["event_id"], []).append(dict(r))
    return out


def _attach_vectors(rows_by_event):
    """Attach cached bge-m3 vectors (read-only; NO embedding call is ever made here)."""
    import numpy as np
    import cluster
    import database
    keys = {}
    for rows in rows_by_event.values():
        for r in rows:
            r["_k"] = cluster._emb_key(cluster._text_of(r))
            keys[r["_k"]] = None
    cached = database.embeddings_get(list(keys))
    for rows in rows_by_event.values():
        for r in rows:
            b = cached.get(r["_k"])
            r["vec"] = np.frombuffer(b, dtype=np.float32) if b else None
            del r["_k"]


def process_events(conn, event_ids, use_vectors=True, force=False, budget_s=None, now=None):
    """Analyse the given events (skipping unchanged ones). Returns a summary dict. Never raises for one bad story."""
    from sources import OWNER_BY_SOURCE
    owner_of = lambda n: OWNER_BY_SOURCE.get(n, n)
    t0 = time.time()
    init_si_schema(conn)
    rows_by_event = _load_rows(conn, list(event_ids))
    state = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT event_id, engine_version, input_sig FROM si_story_state")}
    todo = {}
    for eid in event_ids:
        rows = rows_by_event.get(eid, [])
        if len(rows) < 2:
            continue
        sig = input_signature(rows)
        if not force and state.get(eid) == (ENGINE_VERSION, sig):
            continue
        todo[eid] = (rows, sig)
    if use_vectors and todo:
        try:
            _attach_vectors({e: v[0] for e, v in todo.items()})
        except Exception as e:
            print(f"  story_intelligence: vectors unavailable ({type(e).__name__}: {e}); continuing text-only")
    pub_names = _publisher_names()
    done = failed = skipped_budget = 0
    for eid, (rows, sig) in todo.items():
        if budget_s is not None and time.time() - t0 > budget_s:
            skipped_budget = len(todo) - done - failed
            break
        try:
            persist_story(conn, eid, analyze_story(rows, owner_of, pub_names), sig, now=now)
            done += 1
        except Exception as e:
            failed += 1
            print(f"  story_intelligence: story {eid} failed: {type(e).__name__}: {e}")
    return {"considered": len(list(event_ids)), "changed": len(todo), "processed": done, "failed": failed,
            "deferred_by_budget": skipped_budget, "seconds": round(time.time() - t0, 1)}


def recent_event_ids(conn, days=14, limit=200):
    since = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)).isoformat(timespec="seconds")
    return [r[0] for r in conn.execute(
        "SELECT id FROM events WHERE is_demo=0 AND created_at >= ? ORDER BY updated_at DESC, id DESC LIMIT ?", (since, limit))]


def run_cycle_step(days=14, limit=200, budget_s=180):
    """The pipeline hook: bounded, non-fatal, never blocks publication. Returns a summary (or an error note)."""
    try:
        import database
        conn = database.get_connection()
        try:
            return process_events(conn, recent_event_ids(conn, days, limit), budget_s=budget_s)
        finally:
            conn.close()
    except Exception as e:                                        # noqa: BLE001 - the step must never break a cycle
        return {"error": f"{type(e).__name__}: {e}"}


if __name__ == "__main__":
    import sys
    if "--cycle" in sys.argv:                 # the pipeline step: bounded, prints a one-line summary, ALWAYS exits 0
        print("story_intelligence:", run_cycle_step())
        sys.exit(0)
    import argparse
    import database
    ap = argparse.ArgumentParser(description="Story Intelligence: derive independence / developments / claims for recent stories.")
    ap.add_argument("--recent", type=int, default=14, help="look at stories created in the last N days")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--persist", action="store_true", help="write si_* rows (default: dry run, nothing written)")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    c = database.get_connection()
    ids = recent_event_ids(c, a.recent, a.limit)
    if a.persist:
        print(process_events(c, ids, force=a.force))
    else:
        from sources import OWNER_BY_SOURCE
        rows = _load_rows(c, ids)
        _attach_vectors(rows)
        agg = {k: 0 for k in CLASSES}
        n = 0
        for eid, rs in rows.items():
            if len(rs) >= 2:
                st = analyze_story(rs, lambda x: OWNER_BY_SOURCE.get(x, x))["stats"]
                n += 1
                for k, v in st["role_counts"].items():
                    agg[k] += v
        print(f"dry run over {n} stories:", agg)
    c.close()
