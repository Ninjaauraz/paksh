"""editorial/schema.py - the versioned editorial document and its strict validator.

The editorial document is the ONLY thing editors change. It is stored and published
completely separately from the generated story intelligence (SQLite `analysis_json`),
which this package never reads from the database and never writes.

Design rules enforced here:
  * STRICT WHITELIST. Only the keys listed below are accepted anywhere in the document.
    Unknown keys are errors (never silently ignored), so a future field cannot slip in.
  * PROTECTED FIELDS. A second, independent denylist scan rejects any key that names a
    protected analytical field (bias values, lean counts, outlet leans, sources,
    evidence, framing, ...), anywhere in the document, with a specific error code. If
    the whitelist is ever loosened by mistake, this still holds.
  * STABLE IDS. Stories are referenced only by their numeric event id (as a string key).
    Never by headline, list position, or generated filename.
  * NO MARKUP. Editorial text is plain text; angle brackets and invisible/bidi control
    characters are rejected. No HTML, script or CSS can travel through the document.
  * LANGUAGES ARE INDEPENDENT. English and Hindi are separate optional values; one is
    never treated as a translation of the other.
  * PURE. No clock reads, no file or network access, no pipeline imports. Callers pass
    `now` where time matters.

Python 3.9 compatible (the Windows publishing machine runs the Microsoft Store Python).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone

SCHEMA_VERSION = 1
LANGS = ("en", "hi")

MAX_STORIES = 1000
MAX_PLACEMENTS = 1000
TITLE_MAX = 200
TEASER_MAX = 400
INTRO_MAX = 1200
NOTE_MAX = 200

TEXT_FIELDS = ("title", "teaser", "intro")
_TEXT_LIMITS = {"title": TITLE_MAX, "teaser": TEASER_MAX, "intro": INTRO_MAX}
# Only fields that have a generated counterpart can carry a staleness fingerprint.
BASE_KEYS = ("title_en", "title_hi", "teaser_en", "teaser_hi")

ACTIONS = ("pin", "hide", "feature")

# All patterns are STRICT: ASCII only (re.ASCII, and explicit [0-9] classes), and they are always
# applied with .fullmatch(). A '$' anchor would also accept a trailing newline ("5\n") and '\d'
# would accept non-ASCII digits (Devanagari, fullwidth); neither is wanted in an identifier,
# scope, fingerprint or timestamp. Do not "simplify" these back to match()/'$'.
_A = re.ASCII
STORY_ID_RE = re.compile(r"[1-9][0-9]{0,11}", _A)
PLACEMENT_ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}", _A)
SCOPE_RE = re.compile(r"home|section:[a-z0-9]+(?:-[a-z0-9]+)*", _A)
SHA256_RE = re.compile(r"[0-9a-f]{64}", _A)
_TS_RE = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})",
    _A)

# A real document is about 5 levels deep (document > stories > id > title > en). Anything deeper
# than this is rejected up front, WITHOUT recursing, so a hostile document cannot raise
# RecursionError out of the validator.
MAX_DEPTH = 12

# Keys that may never appear anywhere in an editorial document. These are the generated
# analytical / evidence / bias fields (see database._event_summary_row, the per-story
# export, sources.py and claude.md "THE INVARIANTS"). Matching is case-insensitive.
PROTECTED_KEYS = frozenset("""
analysis_json analysis blindspot dominant lean lean_counts leans bias bias_bar international
coverage framing framing_hi sources source source_count total_sources outlet outlets
ownership owner axes divergence omissions evidence evidence_status evidence_reason
content_complete summary_method summary_points summary_points_hi degraded storyline
storyline_id story_context is_demo importance feed_rank topic region created_at
updated_at published_at event_id articles article_url image_url
""".split())
# Any key starting with one of these is also protected (e.g. evidence_gate, lean_override).
PROTECTED_PREFIXES = ("evidence_", "lean_", "bias_", "source_", "si_", "pdi_")

_ALLOWED_ZERO_WIDTH = ("‌", "‍")  # ZWNJ / ZWJ are required for Devanagari conjuncts


class Issue(dict):
    """A validation finding: {path, code, message}. A dict so it serialises directly."""

    def __init__(self, path, code, message):
        super().__init__(path=path, code=code, message=message)


class ValidationResult:
    def __init__(self):
        self.errors = []
        self.warnings = []

    @property
    def ok(self):
        return not self.errors

    def error(self, path, code, message):
        self.errors.append(Issue(path, code, message))

    def warn(self, path, code, message):
        self.warnings.append(Issue(path, code, message))

    def codes(self):
        return sorted({e["code"] for e in self.errors})

    def to_dict(self):
        return {"ok": self.ok, "errors": list(self.errors), "warnings": list(self.warnings)}


def parse_utc(value):
    """Parse a strict ISO-8601 timestamp WITH an explicit offset into an aware UTC datetime.
    Raises ValueError (and ONLY ValueError) for anything malformed or unrepresentable.
    (No datetime.fromisoformat: it varies across Python versions.)"""
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    m = _TS_RE.fullmatch(value)
    if not m:
        raise ValueError("timestamp must look like 2026-10-10T06:00:00Z (offset required)")
    y, mo, d, h, mi, s = (int(x) for x in m.groups()[:6])
    tz = m.group(7)
    if tz == "Z":
        off = timedelta(0)
    else:
        sign = 1 if tz[0] == "+" else -1
        oh, om = int(tz[1:3]), int(tz[4:6])
        if oh > 23 or om > 59:
            raise ValueError("bad UTC offset")
        off = sign * timedelta(hours=oh, minutes=om)
    dt = datetime(y, mo, d, h, mi, s, tzinfo=timezone(off))  # ValueError on impossible dates
    try:
        return dt.astimezone(timezone.utc)
    except OverflowError:
        # e.g. 0001-01-01T00:00:00+05:00 or 9999-12-31T23:59:59-05:00: the local time is a
        # valid datetime but its UTC equivalent falls outside datetime's supported range.
        # Reject it as an ordinary validation failure; never let it escape as an exception.
        raise ValueError("timestamp is outside the supported date range once converted to UTC")


def _scan_protected(obj, path, res):
    """Reject protected analytical keys anywhere in the document, at any depth."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            lk = k.lower() if isinstance(k, str) else ""
            if lk in PROTECTED_KEYS or lk.startswith(PROTECTED_PREFIXES):
                res.error("%s.%s" % (path, k) if path else str(k), "protected_field",
                          "'%s' is a protected analytical field and cannot appear in "
                          "editorial configuration" % k)
            _scan_protected(v, "%s.%s" % (path, k) if path else str(k), res)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _scan_protected(v, "%s[%d]" % (path, i), res)


def _check_text(path, value, maxlen, res, multiline=False):
    if not isinstance(value, str):
        res.error(path, "type", "must be a string")
        return
    if value == "" or value.strip() == "":
        res.error(path, "empty_text", "must not be empty (omit the language instead)")
        return
    if value != value.strip():
        res.error(path, "surrounding_whitespace", "must not start or end with whitespace")
    if len(value) > maxlen:
        res.error(path, "too_long", "is %d characters; the limit is %d" % (len(value), maxlen))
    if "<" in value or ">" in value:
        res.error(path, "markup", "plain text only: '<' and '>' are not allowed")
    for ch in value:
        if ch in _ALLOWED_ZERO_WIDTH:
            continue
        cat = unicodedata.category(ch)
        if multiline and ch == "\n":
            continue
        if cat in ("Cc", "Cf", "Cs", "Co", "Cn") or ch in (" ", " "):
            res.error(path, "control_character",
                      "contains a control, invisible or bidi character (U+%04X)" % ord(ch))
            break
    if "—" in value or "–" in value:
        res.warn(path, "dash", "em/en dashes are stripped from displayed prose by the "
                 "exporter; the published text will differ from what was typed")


def _check_lang_obj(path, obj, maxlen, res, multiline=False):
    """{'en': str, 'hi': str} with at least one language; languages are independent."""
    if not isinstance(obj, dict):
        res.error(path, "type", "must be an object with 'en' and/or 'hi'")
        return False
    unknown = sorted(set(obj) - set(LANGS))
    for k in unknown:
        res.error("%s.%s" % (path, k), "unknown_key", "only 'en' and 'hi' are allowed")
    present = [k for k in LANGS if k in obj]
    if not present and not unknown:
        res.error(path, "empty_override", "must set at least one language")
    for k in present:
        _check_text("%s.%s" % (path, k), obj[k], maxlen, res, multiline)
    return bool(present)


def _validate_story(sid, entry, res):
    path = "stories.%s" % sid
    if not STORY_ID_RE.fullmatch(sid):
        res.error(path, "bad_story_id", "story ids are plain positive integers (event ids)")
    if not isinstance(entry, dict):
        res.error(path, "type", "must be an object")
        return
    for k in sorted(set(entry) - set(TEXT_FIELDS) - {"base"}):
        res.error("%s.%s" % (path, k), "unknown_key", "not an editable field")
    overridden = set()
    for f in TEXT_FIELDS:
        if f in entry:
            if _check_lang_obj("%s.%s" % (path, f), entry[f], _TEXT_LIMITS[f], res,
                               multiline=(f == "intro")):
                for lang in LANGS:
                    if lang in entry[f]:
                        overridden.add("%s_%s" % (f, lang))
    if not any(f in entry for f in TEXT_FIELDS):
        res.error(path, "empty_override", "has no editable text field")
    base = entry.get("base", {})
    if not isinstance(base, dict):
        res.error(path + ".base", "type", "must be an object")
        base = {}
    for k, v in base.items():
        if k not in BASE_KEYS:
            res.error("%s.base.%s" % (path, k), "unknown_key", "not a fingerprintable field")
        elif not (isinstance(v, str) and SHA256_RE.fullmatch(v)):
            res.error("%s.base.%s" % (path, k), "bad_fingerprint", "must be a lowercase sha256 hex")
        elif k not in overridden:
            res.warn("%s.base.%s" % (path, k), "orphan_base", "fingerprint for a field that is not overridden")
    for k in sorted(overridden & set(BASE_KEYS)):
        if k not in base:
            res.warn("%s.base.%s" % (path, k), "missing_base",
                     "no fingerprint of the generated text: staleness cannot be detected")
    # Half-translated stories are allowed, but visible to the editor.
    for f in TEXT_FIELDS:
        if f in entry and isinstance(entry[f], dict):
            have = [l for l in LANGS if l in entry[f]]
            if len(have) == 1:
                missing = [l for l in LANGS if l not in entry[f]][0]
                res.warn("%s.%s" % (path, f), "missing_translation",
                         "only '%s' is overridden; '%s' keeps the generated text" % (have[0], missing))


def _window(p, res, path):
    """Return (start, end) as aware datetimes or None; report errors."""
    start = end = None
    for key in ("starts_at", "ends_at"):
        if key in p:
            try:
                val = parse_utc(p[key])
            except ValueError as e:
                res.error("%s.%s" % (path, key), "bad_timestamp", str(e))
                continue
            if key == "starts_at":
                start = val
            else:
                end = val
    if start and end and end <= start:
        res.error(path, "bad_window", "ends_at must be after starts_at")
    return start, end


def _overlap(a, b):
    (s1, e1), (s2, e2) = a, b
    lo = datetime.min.replace(tzinfo=timezone.utc)
    hi = datetime.max.replace(tzinfo=timezone.utc)
    return (s1 or lo) < (e2 or hi) and (s2 or lo) < (e1 or hi)


def _validate_placements(placements, res):
    if not isinstance(placements, list):
        res.error("placements", "type", "must be a list")
        return
    if len(placements) > MAX_PLACEMENTS:
        res.error("placements", "too_many", "more than %d placements" % MAX_PLACEMENTS)
        return
    seen_ids = set()
    parsed = []  # (idx, scope, story_id, action, window)
    for i, p in enumerate(placements):
        path = "placements[%d]" % i
        if not isinstance(p, dict):
            res.error(path, "type", "must be an object")
            continue
        for k in sorted(set(p) - {"id", "scope", "story_id", "action", "position",
                                  "starts_at", "ends_at", "note"}):
            res.error("%s.%s" % (path, k), "unknown_key", "not a placement field")
        pid = p.get("id")
        if not (isinstance(pid, str) and PLACEMENT_ID_RE.fullmatch(pid)):
            res.error(path + ".id", "bad_placement_id", "must match [a-z0-9][a-z0-9_-]{0,39}")
        elif pid in seen_ids:
            res.error(path + ".id", "duplicate_id", "placement id '%s' is used twice" % pid)
        else:
            seen_ids.add(pid)
        scope = p.get("scope")
        if not (isinstance(scope, str) and SCOPE_RE.fullmatch(scope)):
            res.error(path + ".scope", "bad_scope", "must be 'home' or 'section:<slug>'")
        sid = p.get("story_id")
        if not (isinstance(sid, str) and STORY_ID_RE.fullmatch(sid)):
            res.error(path + ".story_id", "bad_story_id",
                      "must be a stable story id string (digits), never a headline or position")
        action = p.get("action")
        if action not in ACTIONS:
            res.error(path + ".action", "bad_action", "must be one of %s" % ", ".join(ACTIONS))
        if "position" in p:
            pos = p["position"]
            if action == "hide":
                res.error(path + ".position", "position_not_allowed", "hide has no position")
            elif isinstance(pos, bool) or not isinstance(pos, int) or not (1 <= pos <= 100):
                res.error(path + ".position", "bad_position", "must be an integer 1..100")
        if "note" in p:
            _check_text(path + ".note", p["note"], NOTE_MAX, res)
        window = _window(p, res, path)
        if (isinstance(scope, str) and isinstance(sid, str) and action in ACTIONS):
            parsed.append((i, scope, sid, action, window))
    # Contradictions / duplicates that are simultaneously active.
    for a in range(len(parsed)):
        for b in range(a + 1, len(parsed)):
            ia, sa, ka, aa, wa = parsed[a]
            ib, sb, kb, ab, wb = parsed[b]
            if sa != sb or ka != kb or not _overlap(wa, wb):
                continue
            if aa == ab:
                res.error("placements[%d]" % ib, "duplicate_placement",
                          "same story, scope and action as placements[%d] at overlapping times" % ia)
            elif "hide" in (aa, ab):
                res.error("placements[%d]" % ib, "contradictory_placements",
                          "hide conflicts with %s on placements[%d] at overlapping times"
                          % (aa if ab == "hide" else ab, ia))


def _too_deep(obj, limit):
    """True if `obj` nests deeper than `limit` containers. ITERATIVE (explicit stack), so it
    cannot itself hit the interpreter's recursion limit however hostile the input is."""
    stack = [(obj, 1)]
    seen = 0
    while stack:
        cur, d = stack.pop()
        if isinstance(cur, dict):
            kids = cur.values()
        elif isinstance(cur, (list, tuple)):
            kids = cur
        else:
            continue
        if d > limit:
            return True
        seen += 1
        if seen > 200000:           # absurdly large: treat as hostile rather than walk it all
            return True
        for k in kids:
            if isinstance(k, (dict, list, tuple)):
                stack.append((k, d + 1))
    return False


def validate_document(doc):
    """Validate an editorial document (already parsed JSON). Returns a ValidationResult.
    Never raises on bad input: every problem becomes an error entry."""
    res = ValidationResult()
    if not isinstance(doc, dict):
        res.error("", "type", "the document must be a JSON object")
        return res
    if _too_deep(doc, MAX_DEPTH):
        res.error("", "too_deep", "the document is nested deeper than %d levels or is implausibly large" % MAX_DEPTH)
        return res
    _scan_protected(doc, "", res)
    ver = doc.get("schema_version")
    if isinstance(ver, bool) or not isinstance(ver, int):
        res.error("schema_version", "missing_version", "schema_version (integer) is required")
    elif ver != SCHEMA_VERSION:
        res.error("schema_version", "unsupported_version",
                  "document is version %d; this build supports version %d" % (ver, SCHEMA_VERSION))
    for k in sorted(set(doc) - {"schema_version", "stories", "placements"}):
        res.error(k, "unknown_key", "top-level section '%s' is not supported by schema version %d"
                  % (k, SCHEMA_VERSION))
    stories = doc.get("stories", {})
    if not isinstance(stories, dict):
        res.error("stories", "type", "must be an object keyed by story id")
    else:
        if len(stories) > MAX_STORIES:
            res.error("stories", "too_many", "more than %d story overrides" % MAX_STORIES)
        else:
            for sid, entry in stories.items():
                _validate_story(sid if isinstance(sid, str) else str(sid), entry, res)
    if "placements" in doc:
        _validate_placements(doc["placements"], res)
    return res


def empty_document():
    """A valid document that changes nothing."""
    return {"schema_version": SCHEMA_VERSION, "stories": {}, "placements": []}
