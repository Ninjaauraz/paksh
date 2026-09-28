"""claim_extraction.py - Phase 7 PROTOTYPE (v2 hardening, 2026-09-28): EVIDENCE-BOUND
claim extraction. This revision exists because the v1 prototype's F1 negative-control
run produced a real FALSE_POSITIVE: the model extracted status=FORMER from "CM
Suvendu Adhikari" - text with no former/ex- marker at all - because the prompt taught
it "absence of former = CURRENT" for title appositives. That rule is REMOVED here.

The extractor's contract changed from "what is probably true" to "what does this
exact text explicitly state" - every claim now requires a verbatim `evidence_quote`,
checked with a hard, deterministic grounding invariant (grounded_claims() below):
a claim whose evidence_quote cannot be found verbatim (whitespace-normalized) inside
the supplied text is REJECTED before it ever reaches consistency_checks.py or
numeric_consistency.py. Absence of a marker now means UNSPECIFIED, never a guessed
opposite state - "a claim left UNSPECIFIED is preferable to a confidently invented
CURRENT/FORMER/ALLEGED/ESTABLISHED value" is the explicit success criterion this
file is built around, not recall.

NOT wired into production - analyze.py/build_prompt() is untouched.
"""
import json
import re

import ai_providers

# ---- EXPLICIT-only status vocabulary (v2) -----------------------------------------
# Every value ends in _EXPLICIT except UNSPECIFIED - this is deliberate, not
# decorative: it forces the extractor (and anyone reading the schema later) to
# remember that a status value is a claim about what the TEXT says, never an
# inference. UNSPECIFIED is the default and is what "CM Suvendu Adhikari" (no
# former/ex- marker) must now produce - CURRENT_EXPLICIT is reserved for text that
# actually says "current"/"incumbent"/"sitting" etc., not for silence.
STATUS_VOCAB = [
    "CURRENT_EXPLICIT", "FORMER_EXPLICIT", "INCOMING_EXPLICIT",
    "RESIGNED_EXPLICIT", "SERVING_EXPLICIT",
    "ANNOUNCED_EXPLICIT", "OCCURRED_EXPLICIT",
    "PROPOSED_EXPLICIT", "CONFIRMED_EXPLICIT",
    "ALLEGED_EXPLICIT", "CLAIMED_EXPLICIT", "ESTABLISHED_EXPLICIT",
    "CHARGED_EXPLICIT", "CONVICTED_EXPLICIT",
    "INJURED_EXPLICIT", "KILLED_EXPLICIT",
    "UNSPECIFIED",
]

FACT_TYPES = [
    "office_holder", "election_result", "appointment", "resignation", "death_toll",
    "injury_count", "casualty_count", "arrest_count", "vote_count", "percentage",
    "money_amount", "date", "event_status", "match_result", "score", "ranking",
    "location", "sport", "competition", "team",
]

# ---- temporal type vocabulary (fixes section 5's time-string bug) -----------------
EXPLICIT_DATE = "EXPLICIT_DATE"        # a calendar date/timestamp: "26 September 2026"
RELATIVE_DATE = "RELATIVE_DATE"        # "Monday", "yesterday", "last week"
DATE_RANGE = "DATE_RANGE"
TIME_DESCRIPTOR = "TIME_DESCRIPTOR"    # "as of Monday", "by Wednesday" - a QUALIFIER on a date, not a second date
SOURCE_DESCRIPTOR = "SOURCE_DESCRIPTOR"  # "the latest poll", "the report" - not a date at all
TIME_UNSPECIFIED = "UNSPECIFIED"
TIME_TYPES = [EXPLICIT_DATE, RELATIVE_DATE, DATE_RANGE, TIME_DESCRIPTOR, SOURCE_DESCRIPTOR, TIME_UNSPECIFIED]

# ---- extraction outcome taxonomy (unchanged from v1) -------------------------------
SUCCESS_WITH_CLAIMS = "SUCCESS_WITH_CLAIMS"
SUCCESS_EMPTY = "SUCCESS_EMPTY"
TIMEOUT = "TIMEOUT"
RATE_LIMIT = "RATE_LIMIT"
API_ERROR = "API_ERROR"
INVALID_RESPONSE = "INVALID_RESPONSE"
NO_PROVIDER = "NO_PROVIDER"
_MODEL_FAILURE_STATUSES = {TIMEOUT, RATE_LIMIT, API_ERROR, INVALID_RESPONSE, NO_PROVIDER}


def is_model_failure(status):
    return status in _MODEL_FAILURE_STATUSES


_PROMPT = """You are a strict evidence-grounding extractor. Your ONLY job is to report
what the text below EXPLICITLY states - word for word. You are NOT answering "what is
probably true", "what do you know about this person/event", or "what status is
logically implied". You have no world knowledge for this task; treat the text as the
entire universe of what is known.

HARD RULE - explicit status only: use an *_EXPLICIT status value ONLY when the text
itself directly conveys that specific status - either via one of the literal words
("former", "ex-", "current", "incumbent", "sitting", "alleged", "accused", "charged",
"convicted", "sworn in", "resigned") OR a clear semantically-equivalent phrasing of
the SAME status (e.g. "previously served as chief minister" conveys FORMER_EXPLICIT
just as much as the word "former" does; "was accused of" conveys ALLEGED_EXPLICIT;
"stepped down from" conveys RESIGNED_EXPLICIT). The test is always: does this exact
text explicitly assert that specific status, in either wording - never: could you
infer it, and never: is this word merely absent. If the text does NOT explicitly
convey any status for this subject, you MUST use "UNSPECIFIED" - NEVER infer the
opposite state from silence, and never invent a status that isn't there. Concretely:
  - "CM Suvendu Adhikari" contains NO former/ex-/current wording, literal or
    equivalent -> status=UNSPECIFIED. Do NOT output CURRENT_EXPLICIT here just
    because no "former" is present.
  - "former Chief Minister Mamata Banerjee" -> FORMER_EXPLICIT.
  - "Mamata Banerjee, who previously served as chief minister" -> ALSO
    FORMER_EXPLICIT (same status, different words - both are explicit).
  - "Police allege the suspect stole funds" -> ALLEGED_EXPLICIT.
  - "the suspect was accused of stealing funds" -> ALSO ALLEGED_EXPLICIT.
  - "The suspect stole the funds" (no hedge word or equivalent phrasing at all) ->
    UNSPECIFIED, NOT ESTABLISHED_EXPLICIT or CONFIRMED_EXPLICIT. A bare unhedged
    sentence is not itself evidence that the fact is officially established - only
    an explicit word or equivalent phrasing like "confirmed"/"established"/
    "convicted" earns that status.

HARD RULE - mandatory verbatim grounding: every claim MUST include an "evidence_quote"
field containing an EXACT, VERBATIM substring copied from the text below (not
paraphrased, not summarized). If you cannot find an exact quote in the text that
supports a claim, DO NOT emit that claim at all - do not guess, do not soften it into
a vaguer claim, simply omit it.

Still extract a role/title-appositive claim (e.g. "Chief Minister Jane Doe") as its
own claim (subject=person's name only, predicate="holds the role of", object=the
role, fact_type="office_holder") - just with status=UNSPECIFIED unless the text
itself carries an explicit marker.

For numeric claims (counts, amounts, percentages, scores), extract fact_type (closest
match in {fact_types}), and:
  - for fact_type="score" or "match_result": use home_value and away_value (two
    separate numbers) instead of a single value - NEVER collapse "3-1" into one number.
  - for all other numeric fact_types: use "value" (a plain number) and "unit" (e.g.
    "people", "%", "crore"), and "qualifier" ONLY if the text uses a hedge word
    directly attached to the number (e.g. "at least", "approximately", "more than",
    "confirmed", "missing") - otherwise qualifier=null.

For any time reference attached to a claim, classify it into time_type (one of
{time_types}) and keep the raw text in time_text:
  - "26 September 2026", "last Tuesday's date" -> EXPLICIT_DATE
  - "Monday", "yesterday" -> RELATIVE_DATE
  - "as of Monday", "by Wednesday" -> TIME_DESCRIPTOR (a qualifier on a date, not a
    distinct timestamp - "as of Monday" and "Monday" describe the SAME reference day)
  - "the latest poll", "the report" -> SOURCE_DESCRIPTOR (NOT a date at all)
  - nothing stated -> UNSPECIFIED

If the text contains an explicit acronym/expansion pairing (e.g. "Cockroach Janta
Party (CJP)" or "CJP (Chief Justice of Pakistan)"), record it in "entity_expansion" as
the full name string; otherwise null. Never supply an expansion from your own
knowledge - only when the TEXT itself states it.

If the text is describing a sport/field where domain confusion is plausible, tag
"domain" with a short lowercase sport/field name (e.g. "cricket", "rugby",
"football"); otherwise null.

Return ONLY a JSON object: {{"claims": [{{"subject": str, "predicate": str,
"object": str, "fact_type": one of {fact_types} or null, "value": number or null,
"unit": str or null, "qualifier": str or null, "home_value": number or null,
"away_value": number or null, "status": one of {status_vocab},
"time_type": one of {time_types}, "time_text": str or null,
"entity_expansion": str or null, "domain": str or null, "evidence_quote": str (EXACT
verbatim substring of the text below)}}]}}

Extract at most 10 of the most important claims.

TEXT (source: {source}):
{text}
"""


def get_groq_provider():
    for p in ai_providers.active_providers():
        if p["name"] == "groq":
            return p
    return None


def get_paid_provider():
    for p in ai_providers.active_providers():
        if p.get("billed"):
            return p
    return None


def get_benchmark_provider():
    return get_paid_provider() or get_groq_provider()


def _extract_json(raw):
    try:
        return json.loads(raw), True
    except (json.JSONDecodeError, TypeError):
        m = re.search(r"\{.*\}", raw or "", re.S)
        if m:
            try:
                return json.loads(m.group(0)), True
            except json.JSONDecodeError:
                pass
    return {"claims": []}, False


_RATE_LIMIT_MARKERS = ("rate limit", "tpm", "429", "quota", "too many requests")
_TIMEOUT_MARKERS = ("timeout", "timed out")


def _classify_exception(e):
    msg = str(e).lower()
    if any(m in msg for m in _RATE_LIMIT_MARKERS):
        return RATE_LIMIT
    if any(m in msg for m in _TIMEOUT_MARKERS):
        return TIMEOUT
    return API_ERROR


def _normalize_for_grounding(s):
    """Whitespace/quote normalization for the verbatim-grounding check - NOT a
    semantic normalization. Collapses whitespace runs and normalizes curly quotes
    to straight ones so trivial JSON-encoding artifacts don't cause a legitimate
    verbatim quote to be rejected, while still requiring the actual WORDS to match
    exactly (no paraphrase tolerance)."""
    if not s:
        return ""
    s = s.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def is_grounded(evidence_quote, source_text):
    """The hard deterministic grounding invariant (section 4): True iff
    evidence_quote is a verbatim (whitespace/quote-normalized) substring of
    source_text. Pure function, independently testable without any LLM call."""
    if not evidence_quote or not source_text:
        return False
    return _normalize_for_grounding(evidence_quote) in _normalize_for_grounding(source_text)


def extract_claims(text, source="unknown", url=None, tier=None, group_id=None,
                    article_id=None, provider=None):
    """-> (claims, status, rejection_stats). claims: list of GROUNDED claim dicts
    only - any claim whose evidence_quote fails is_grounded() against `text` is
    dropped before being returned, never silently kept. status: one of
    SUCCESS_WITH_CLAIMS / SUCCESS_EMPTY / TIMEOUT / RATE_LIMIT / API_ERROR /
    INVALID_RESPONSE / NO_PROVIDER. rejection_stats: {"missing_quote": n,
    "quote_not_verbatim": n} - section 10's required rejection counters. Never
    raises."""
    stats = {"missing_quote": 0, "quote_not_verbatim": 0}
    if not text or not text.strip():
        return [], SUCCESS_EMPTY, stats
    provider = provider or get_groq_provider()
    if provider is None:
        return [], NO_PROVIDER, stats
    prompt = _PROMPT.format(fact_types=FACT_TYPES, status_vocab=STATUS_VOCAB,
                             time_types=TIME_TYPES, source=source, text=text[:4000])
    try:
        raw = ai_providers.chat_with_provider(provider, prompt, as_json=True)
    except Exception as e:
        return [], _classify_exception(e), stats
    data, parsed_ok = _extract_json(raw)
    if not parsed_ok:
        return [], INVALID_RESPONSE, stats
    claims = data.get("claims")
    if not isinstance(claims, list):
        return [], INVALID_RESPONSE, stats

    out = []
    for c in claims:
        if not isinstance(c, dict) or "subject" not in c:
            continue
        quote = c.get("evidence_quote")
        if not quote:
            stats["missing_quote"] += 1
            continue
        if not is_grounded(quote, text):
            stats["quote_not_verbatim"] += 1
            continue

        status = c.get("status")
        status = status.upper() if isinstance(status, str) and status.upper() in STATUS_VOCAB else "UNSPECIFIED"
        fact_type = c.get("fact_type")
        fact_type = fact_type.lower() if isinstance(fact_type, str) and fact_type.lower() in FACT_TYPES else None
        time_type = c.get("time_type")
        time_type = time_type.upper() if isinstance(time_type, str) and time_type.upper() in TIME_TYPES else TIME_UNSPECIFIED

        out.append({
            "subject": c.get("subject"),
            "predicate": c.get("predicate"),
            "object": c.get("object"),
            "fact_type": fact_type,
            "value": c.get("value") if isinstance(c.get("value"), (int, float)) else None,
            "unit": c.get("unit") if isinstance(c.get("unit"), str) else None,
            "qualifier": c.get("qualifier") if isinstance(c.get("qualifier"), str) else None,
            "home_value": c.get("home_value") if isinstance(c.get("home_value"), (int, float)) else None,
            "away_value": c.get("away_value") if isinstance(c.get("away_value"), (int, float)) else None,
            "status": status,
            "time_type": time_type,
            "time_text": c.get("time_text") if isinstance(c.get("time_text"), str) else None,
            "entity_expansion": c.get("entity_expansion") if isinstance(c.get("entity_expansion"), str) else None,
            "domain": (c.get("domain") or "").lower() or None,
            "evidence_quote": quote,
            "evidence_span": quote,   # kept for backward compatibility with earlier code paths
            "provenance": {"article_id": article_id, "source": source, "url": url, "tier": tier, "group_id": group_id},
            "source": source,
        })
    return out, (SUCCESS_WITH_CLAIMS if out else SUCCESS_EMPTY), stats


def extract_claims_multi(evidence_groups, provider=None):
    all_claims, statuses, agg_stats = [], [], {"missing_quote": 0, "quote_not_verbatim": 0}
    for idx, g in enumerate(evidence_groups):
        claims, status, stats = extract_claims(
            g.get("representative_text", ""), source=g.get("representative_source", "unknown"),
            url=g.get("url"), tier=g.get("tier"), group_id=g.get("group_id", idx),
            article_id=g.get("article_id"), provider=provider)
        for c in claims:
            c["group_size"] = g.get("group_size")
        all_claims.extend(claims)
        statuses.append(status)
        agg_stats["missing_quote"] += stats["missing_quote"]
        agg_stats["quote_not_verbatim"] += stats["quote_not_verbatim"]
    return all_claims, statuses, agg_stats
