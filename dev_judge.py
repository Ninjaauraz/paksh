"""
dev_judge.py - a NARROW, VETO-ONLY language-model check on development candidates (Intelligence Program, Phase 13).

Why it exists: the deterministic development detector (typed headline cues) measured only ~45 % precision on 90 hand-judged
candidates; its errors are semantic (the cue is there but the thing was already reported under other words, or the cue is a
descriptor, or the article is a tangent). Nothing else in Story Intelligence needs a model. The task is small and bounded, so this is
the one place a model is allowed - under these rules:

  * It can only REMOVE or DOWNGRADE a candidate the deterministic engine already produced. It never creates a development.
  * It sees ONLY headlines (the candidate + up to 6 earlier headlines of the same story). No outside knowledge is requested.
  * Structured output with an explicit abstention: NEW_DEVELOPMENT | ALREADY_REPORTED | NOT_A_DEVELOPMENT | CANNOT_TELL.
  * NEW_DEVELOPMENT must quote the phrase of the candidate headline that reports the step; a quote that is not in the headline is
    rejected (verdict becomes CANNOT_TELL). ALREADY_REPORTED must name the earlier headline; if it is not one of the given ones
    it is rejected too.
  * CANNOT_TELL / any failure / any malformed output => the candidate is KEPT unchanged (the model is never the reason a real
    development disappears silently, and a failure never blocks anything).
  * Cached by sha256(prompt version + prompt) so a candidate is judged once (reproducible: same prompt -> same stored verdict).
  * Nothing the model says is stored as a fact about the world: only a verdict about whether a HEADLINE reports a new step.
"""
import hashlib
import json
import re

PROMPT_VERSION = "dj-1"
VERDICTS = ("NEW_DEVELOPMENT", "ALREADY_REPORTED", "NOT_A_DEVELOPMENT", "CANNOT_TELL")
MAX_EARLIER = 6

_PROMPT = """You are checking one news headline against earlier headlines of the SAME story. Use ONLY the headlines below. Do not use outside knowledge.

A "development" is a NEW concrete step in the story: an arrest, a court order, a resignation or removal, an investigation opened, an official denial or apology, a formal decision, a rescue/restoration, a curfew/riot. It is NOT: a comment or opinion, a call for something, a description of someone ("convicted war criminal"), a claim about a past event, a repeat of something an earlier headline already says in other words, or an unrelated item.

Candidate cue type (guessed by a rule, may be wrong): {cue}
Candidate headline: {cand}

Earlier headlines of this story:
{earlier}

Answer with ONE JSON object and nothing else:
{{"verdict": "NEW_DEVELOPMENT" | "ALREADY_REPORTED" | "NOT_A_DEVELOPMENT" | "CANNOT_TELL",
  "quote": "<the exact words of the CANDIDATE headline that report the step; required for NEW_DEVELOPMENT, else empty>",
  "already_in": "<the EXACT earlier headline that already reports it; required for ALREADY_REPORTED, else empty>"}}
If you are not sure, answer CANNOT_TELL."""


def build_prompt(cue, candidate, earlier):
    ear = "\n".join(f"- {t}" for t in earlier[:MAX_EARLIER]) or "- (none)"
    return _PROMPT.format(cue=cue, cand=candidate, earlier=ear)


def cache_key(prompt):
    return hashlib.sha256((PROMPT_VERSION + "\n" + prompt).encode("utf-8")).hexdigest()


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def parse_and_validate(text, candidate, earlier):
    """-> dict(verdict, quote, already_in, valid, reason). Never raises. Anything doubtful becomes CANNOT_TELL."""
    bad = lambda why: {"verdict": "CANNOT_TELL", "quote": "", "already_in": "", "valid": False, "reason": why}
    try:
        m = re.search(r"\{.*\}", text or "", re.S)
        obj = json.loads(m.group(0)) if m else None
    except Exception:
        return bad("unparseable")
    if not isinstance(obj, dict):
        return bad("not_an_object")
    v = str(obj.get("verdict", "")).strip().upper()
    if v not in VERDICTS:
        return bad("unknown_verdict")
    quote, already = str(obj.get("quote") or ""), str(obj.get("already_in") or "")
    if v == "NEW_DEVELOPMENT" and (not quote or _norm(quote) not in _norm(candidate)):
        return bad("new_development_without_a_quote_from_the_headline")
    if v == "ALREADY_REPORTED" and not any(_norm(already) == _norm(e) or (len(_norm(already)) > 25 and _norm(already) in _norm(e)) for e in earlier[:MAX_EARLIER]):
        return bad("already_reported_without_naming_an_earlier_headline")
    return {"verdict": v, "quote": quote, "already_in": already, "valid": True, "reason": "ok"}


def judge(cue, candidate, earlier, generate=None, cache=None):
    """One candidate -> validated verdict (+ provenance). `generate(prompt) -> str` defaults to the existing provider pool.
    `cache` is any dict-like {key: json string}. Returns {"verdict","quote","already_in","valid","reason","cached","prompt_version"}."""
    prompt = build_prompt(cue, candidate, earlier)
    key = cache_key(prompt)
    if cache is not None and key in cache:
        out = json.loads(cache[key])
        out["cached"] = True
        return out
    try:
        if generate is None:
            import ai_providers
            generate = lambda p: ai_providers.pool_generate(p, as_json=True)
        raw = generate(prompt)
    except Exception as e:                                        # noqa: BLE001 - a failing model must never break anything
        return {"verdict": "CANNOT_TELL", "quote": "", "already_in": "", "valid": False, "reason": f"model_error:{type(e).__name__}",
                "cached": False, "prompt_version": PROMPT_VERSION}
    out = parse_and_validate(raw if isinstance(raw, str) else json.dumps(raw), candidate, earlier)
    out["prompt_version"] = PROMPT_VERSION
    out["cached"] = False
    if cache is not None and out["valid"]:                        # failures are not cached (they are retried next time)
        cache[key] = json.dumps({k: v for k, v in out.items() if k != "cached"})
    return out


def keep_candidate(verdict):
    """The veto rule: only a valid ALREADY_REPORTED or NOT_A_DEVELOPMENT removes a candidate; everything else keeps it."""
    return not (verdict.get("valid") and verdict.get("verdict") in ("ALREADY_REPORTED", "NOT_A_DEVELOPMENT"))
