"""
relationship_judgment.py - Phase 21E: ISOLATED, EXPERIMENTAL Stage 2
(RELATIONSHIP JUDGMENT) for Paksh's historical-context architecture.

NOT IMPORTED BY ANY PRODUCTION CODE PATH. analyze.py, reframe.py, cluster.py,
storylines.py, export_static.py, main.py, and context_retrieval.py are all
unmodified by this phase and do not import this file - it imports FROM
analyze.py (its existing, already-tested Gemini call helper), one direction
only, so production code has zero dependency on this module's existence.

Architecture boundary this module implements (Phase 21C/21D/21D.1/21E):

    STAGE 1 (context_retrieval.py) asks: "Could these events plausibly be
        related?" - deterministic, no LLM.
    STAGE 2 (THIS MODULE) asks: "Does the SUPPLIED EVIDENCE demonstrate that
        they are related?" - one bounded LLM call per current event, judging
        every Stage-1 candidate (<=3) independently, never using anything
        outside the current event's and each candidate's own stored
        title/summary/date/topic/region text.

Only Stage 2 may promote a Stage-1 candidate into VERIFIED HISTORICAL
CONTEXT. Nothing in this module writes to paksh.db, calls analyze_event(),
or touches a stored event row - every function here is read-only with
respect to Paksh's data, and the one write-shaped side effect (the LLM
call itself) is a stateless network request, never a database write.

RELATIONSHIP LABELS (Gate A) - unchanged from Phase 21B/21C/21D.1's own
taxonomy, now given exact, judge-facing definitions:

  R1 CONTINUATION - the historical event is demonstrably the same developing
      story (same incident, same investigation, same policy process, same
      dispute) reaching a further stage. Shared people/topic alone is NOT
      sufficient - there must be identifiable continuity of the underlying
      story itself.
  R2 RESPONSE - the current event is a documented reaction, answer,
      retaliation, countermeasure, ruling on, or protest against the
      historical event. Requires a stated or clearly implied DIRECTION
      (previous -> current), never inferred from chronology alone.
  R3 ESCALATION / MATERIAL DEVELOPMENT - stronger than R1: the current event
      represents a meaningful escalation, expansion, deterioration,
      widening, or reversal of the SAME underlying dispute/story the
      historical event established. Not every update is R3 - only a
      materially different state of the same situation.
  R4 NECESSARY BACKGROUND - the historical event is not itself the same
      continuing incident, but materially explains WHY the current event
      exists in its present form (a prior agreement explains a current
      diplomatic move, a prior ruling explains a current legal action).
      Narrower than "this has happened before" - if the previous event is
      merely interesting trivia, reject; if only topically related, N1.
  N1 TOPICAL SIMILARITY ONLY - same subject area/issue/theme/geography,
      without evidence of an actual event-level relationship. REJECTION.
  N2 ENTITY OVERLAP ONLY - same person/organization/institution/country,
      but no demonstrable relationship between the SPECIFIC events
      described. REJECTION. This is the canary category (Phase 21D.1's
      #11371/#8807 recurring-political-opponent false positive).
  A1 INSUFFICIENT EVIDENCE - a relationship is plausible but the supplied
      text does not establish it safely. REJECTION, not weak acceptance -
      the safety valve for thin, ambiguous, or contradictory evidence.

EVIDENCE MODEL (Gate B): the judge may use ONLY the current_title/summary/
date/topic/region and each candidate's own same fields (Gate C's Input
Contract) - never full article corpora, lean counts, coverage, framing, or
any information that could invite ideological or popularity-based inference.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, r"C:\paksh_project\paksh")
import analyze          # read-only reuse: _gemini_generate/_extract_json - never calls INTO this module
import cluster          # read-only reuse: _STOP/_GENERIC_KW only (Gate AA2) - same pattern
                         # context_retrieval.py already uses; never calls INTO cluster.py

RELATIONSHIP_TYPES = {"R1", "R2", "R3", "R4", "N1", "N2", "A1"}
CONFIDENCE_LEVELS = {"high", "medium", "low"}
POSITIVE_TYPES = {"R1", "R2", "R3", "R4"}


# --------------------------------------------------------------------------
# Gate C: input contract - the EXACT object the judge is given per candidate.
# Deliberately excludes lean_counts/coverage/framing/full article lists per
# the explicit instruction not to give the judge anything that could invite
# ideological or popularity-based inference.
# --------------------------------------------------------------------------

@dataclass
class JudgeCandidate:
    previous_event_id: int
    previous_title: str
    previous_summary: str
    previous_date: Optional[str]
    previous_topic: Optional[str]
    previous_region: Optional[str]
    semantic_similarity: float
    lexical_overlap_terms: list
    lexical_overlap_count: int
    same_storyline: bool
    thin_source: bool
    gap_days: Optional[int]


@dataclass
class JudgeResult:
    previous_event_id: int
    related: bool
    relationship_type: str
    confidence: str
    evidence: list
    raw_valid: bool = True             # False if this result was fail-closed-rejected
    reject_reason: Optional[str] = None


# --------------------------------------------------------------------------
# Gate E: prompt design.
# --------------------------------------------------------------------------

def build_judgment_prompt(current_event: dict, candidates: list[JudgeCandidate]) -> str:
    cur_block = (
        f"CURRENT EVENT\n"
        f"  title: {current_event.get('title','')}\n"
        f"  summary: {current_event.get('summary','') or '(no summary available)'}\n"
        f"  date: {current_event.get('date','') or 'unknown'}\n"
        f"  topic: {current_event.get('topic','') or 'unknown'}\n"
        f"  region: {current_event.get('region','') or 'unknown'}\n"
    )
    cand_blocks = []
    for i, c in enumerate(candidates):
        letter = chr(ord("A") + i)
        cand_blocks.append(
            f"CANDIDATE {letter} (previous_event_id={c.previous_event_id})\n"
            f"  title: {c.previous_title}\n"
            f"  summary: {c.previous_summary or '(no summary available)'}\n"
            f"  date: {c.previous_date or 'unknown'}\n"
            f"  topic: {c.previous_topic or 'unknown'}\n"
            f"  region: {c.previous_region or 'unknown'}\n"
        )
    cands_text = "\n".join(cand_blocks)
    ids_list = ", ".join(str(c.previous_event_id) for c in candidates)

    return f"""You are a STRICT relationship auditor for Paksh, a news-transparency
platform. Your ONLY job is to decide, for each CANDIDATE below, whether it is
genuinely, demonstrably related to the CURRENT EVENT closely enough to be used
as verified historical context in a future summary.

HARD RULES - violating any of these makes your answer unusable:
1. Use ONLY the text supplied below (CURRENT EVENT + each CANDIDATE's own
   title/summary/date/topic/region). Do NOT use anything you know about the
   real world, these people, these organizations, or these events from your
   own training. If the supplied text doesn't say it, it doesn't count.
2. Never assume causality from chronology alone. An earlier date does not
   make a candidate "background" or a "response" target - you need the
   supplied text to actually connect them.
3. Two events sharing a person, organization, country, or institution is NOT
   evidence of a relationship by itself. This is the single most common
   mistake to avoid - a recurring public figure appears in many completely
   unrelated stories. Judge the SPECIFIC EVENTS DESCRIBED, not who's in them.
4. Two events sharing a topic or broad subject area is NOT evidence of a
   relationship by itself.
5. A candidate being part of the same Paksh "storyline" grouping is a WEAK
   hint, never proof - storylines are built from semantic/keyword similarity,
   not verified relationships. Judge the actual text.
6. When the evidence is genuinely insufficient to decide, you MUST answer
   A1 (insufficient evidence) rather than guess. A1 is a correct, safe,
   common, and successful answer - not a failure.
7. Judge each candidate INDEPENDENTLY. Do not let one candidate's
   relatedness make you more or less likely to accept another.
8. RECURRING MARKET / COMMODITY / CURRENCY / GLOBAL-MACRO REPORTS: this
   covers TWO related but equally dangerous shapes. (a) gold, silver, oil,
   crude, the rupee-dollar rate, and similar instruments get a fresh,
   INDEPENDENT report every trading day. (b) "global markets react to
   [geopolitical tensions / a conflict / oil prices]" is ALSO a recurring
   report TEMPLATE, re-filed every time the SAME ongoing tension produces a
   new day's market move - "Middle East tensions push oil higher, markets
   fall" on one date and a materially identical headline weeks later are
   normally TWO SEPARATE market reactions to a SLOWLY EVOLVING situation,
   not one continuing event, even though the underlying geopolitical
   situation genuinely is continuous. The DEFAULT for two such reports
   (either shape) is N1 (topical similarity only) - REJECT - even when they
   track the exact same instrument or conflict, mention the same boilerplate
   driver ("geopolitical tensions", "global economic factors", a named
   conflict), or contain numbers that happen to differ in a way that LOOKS
   like a trend. Do not construct a narrative arc by pattern-matching numbers
   or boilerplate phrasing across two independent reports - a "12% decline"
   in one report and a "sharp decline" in another is NOT a match unless the
   text itself ties them to the same specific move; "markets fell amid
   Middle East tensions" in one report and "markets fell amid Middle East
   tensions" in a later report is NOT a match just because the wording
   recurs - check whether the CURRENT report names a SPECIFIC NEW trigger
   (a specific strike, a specific policy move, a specific data release) that
   is DIFFERENT from the candidate's specific trigger; if so, that is
   evidence of two SEPARATE reactions, not one continuing one. Several of
   these reports are themselves aggregations of conflicting source figures
   (e.g. "some reports say decline, others say rise") - never cherry-pick
   whichever number happens to align with the current report; that conflict
   is a reason for MORE caution, not corroboration. Only override this
   REJECT default and accept R1/R3 if the CURRENT event's OWN text explicitly
   identifies itself as following, extending, or resuming the SPECIFIC prior
   report, level, or trigger the CANDIDATE describes - not merely "another
   report about the same instrument or the same broad tension, with
   different specifics".

   WORKED COUNTER-EXAMPLE - read this carefully, it is a real mistake a
   previous version of this system made: CURRENT says gold fell 12% in June
   (a specific, dated figure). CANDIDATE, from a few days earlier, says
   "some reports indicate a sharp decline, others a rise" (a vague, internally
   conflicting figure). A wrong answer reasons: "the current event's 12%
   decline directly follows the candidate's sharp decline" and accepts R1.
   This is WRONG, even though it sounds plausible - nowhere does either
   text say the 12% figure IS or CONTINUES the earlier "sharp decline";
   the judge INVENTED the word "follows" itself, which is exactly the kind
   of judge-fabricated connective language Hard Rule 1 already forbids.
   Before writing "directly follows", "continuation of", "aligns with", or
   similar connecting language in your evidence, check: does that exact
   connection appear in the supplied text, or did you just write it because
   the two events are topically similar and roughly sequential? If it is
   the latter, the correct answer is N1, not R1/R3.
9. RECURRING ADVERSARIAL / POLITICAL EXCHANGES: the same two politicians,
   parties, or institutions criticizing, accusing, or sparring with each
   other is an extremely common, recurring pattern - each instance is
   normally a SEPARATE remark on a SEPARATE occasion, prompted by a SEPARATE
   trigger, even when both instances share a broader ongoing theme (e.g. both
   concern the same protest movement or the same general grievance). Sharing
   that broader theme is NOT sufficient for R1/R2/R3/R4. Only accept when the
   text shows the CURRENT remark is actually responding to, following up on,
   or escalating the SPECIFIC incident or statement the CANDIDATE describes -
   not just that the same two sides are, once again, arguing.

LABELS (choose exactly one per candidate):
  R1 = CONTINUATION: the candidate is demonstrably the same developing story
       (same incident/investigation/policy process/dispute) at an earlier stage.
  R2 = RESPONSE: the current event is a documented reaction to, ruling on, or
       protest against the candidate - the text must show this direction.
  R3 = ESCALATION / MATERIAL DEVELOPMENT: same underlying dispute as the
       candidate, but the current event is a materially different, more
       serious, or substantially changed state of it.
  R4 = NECESSARY BACKGROUND: the candidate is not the same continuing
       incident, but the supplied text shows it materially explains why the
       current event exists in its present form.
  N1 = TOPICAL SIMILARITY ONLY (reject).
  N2 = ENTITY OVERLAP ONLY - same actor/institution, different specific
       event (reject). This is the most important category to get right.
  A1 = INSUFFICIENT EVIDENCE (reject).

related = true ONLY for R1/R2/R3/R4. related = false for N1/N2/A1. These must
never contradict each other.

confidence reflects how well the SUPPLIED TEXT supports your classification -
not how important the story is, not your general certainty about the world.

evidence: 1-3 short, concrete statements a human could check against the text
above. Never write vague statements like "these seem related" - name the
specific detail from CURRENT EVENT and the specific detail from the CANDIDATE
that led to your decision (or, for a rejection, name what's missing).

{cur_block}
{cands_text}

Return ONLY a JSON object, no markdown fences, no commentary:
{{
  "judgments": [
    {{"previous_event_id": <int, one of: {ids_list}>, "related": <bool>,
      "relationship_type": "<R1|R2|R3|R4|N1|N2|A1>", "confidence": "<high|medium|low>",
      "evidence": ["...", "..."]}}
    // one object per candidate above, same previous_event_id values, any order
  ]
}}
"""


# --------------------------------------------------------------------------
# Gate N: fail-closed parsing/validation. Malformed or unsafe model output
# NEVER becomes historical context - it is converted into a JudgeResult with
# raw_valid=False, related=False, relationship_type="A1", which the
# acceptance policy (Gate AA) rejects identically to a genuine A1.
# --------------------------------------------------------------------------

def _reject(previous_event_id, reason) -> JudgeResult:
    return JudgeResult(previous_event_id=previous_event_id, related=False,
                        relationship_type="A1", confidence="low", evidence=[],
                        raw_valid=False, reject_reason=reason)


def _extract_json_loose(text: str):
    """Tolerates a model wrapping JSON in markdown fences - never tolerates
    genuinely malformed JSON (that still fails closed, at the caller)."""
    t = (text or "").strip()
    t = re.sub(r"^```(json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    return json.loads(t)


def parse_judgments(raw_text: str, expected_ids: list[int]) -> dict[int, JudgeResult]:
    """Returns {previous_event_id: JudgeResult} for every id in expected_ids.
    ANY problem (malformed JSON, missing field, invalid enum value,
    contradictory related/relationship_type, an id not in expected_ids, a
    missing id) results in that specific candidate's JudgeResult being a
    fail-closed rejection - never an exception, never a silent guess, never a
    partial promotion to acceptance. One malformed candidate never poisons
    the others in the same response."""
    out: dict[int, JudgeResult] = {}
    try:
        obj = _extract_json_loose(raw_text)
        judgments = obj.get("judgments")
        if not isinstance(judgments, list):
            raise ValueError("no judgments array")
    except Exception:
        # whole response unparseable -> every expected candidate fails closed
        for eid in expected_ids:
            out[eid] = _reject(eid, "unparseable model response")
        return out

    by_id = {}
    for j in judgments:
        if not isinstance(j, dict):
            continue
        pid = j.get("previous_event_id")
        if isinstance(pid, int):
            by_id[pid] = j

    for eid in expected_ids:
        j = by_id.get(eid)
        if j is None:
            out[eid] = _reject(eid, "missing from model response")
            continue
        related = j.get("related")
        rtype = j.get("relationship_type")
        conf = j.get("confidence")
        evidence = j.get("evidence")
        if not isinstance(related, bool):
            out[eid] = _reject(eid, "related is not a bool"); continue
        if rtype not in RELATIONSHIP_TYPES:
            out[eid] = _reject(eid, f"invalid relationship_type {rtype!r}"); continue
        if conf not in CONFIDENCE_LEVELS:
            out[eid] = _reject(eid, f"invalid confidence {conf!r}"); continue
        if related != (rtype in POSITIVE_TYPES):
            out[eid] = _reject(eid, "related/relationship_type contradict each other"); continue
        if not isinstance(evidence, list) or not all(isinstance(e, str) for e in evidence):
            out[eid] = _reject(eid, "evidence is not a list of strings"); continue
        out[eid] = JudgeResult(previous_event_id=eid, related=related,
                                relationship_type=rtype, confidence=conf,
                                evidence=[e.strip() for e in evidence if e.strip()],
                                raw_valid=True)
    return out


# --------------------------------------------------------------------------
# Gate AA2 (overnight Stage-2 hardening): a deterministic, mechanical
# evidence-specificity backstop, independent of the model's own self-report.
#
# Two prior prompt-only fixes (Phase 21E.1's shared_anchor field, Phase
# 21E.2's "substitution test" reasoning step) both asked the model to
# self-certify its own answer with an extra field or procedure, and both
# measurably caused MORE false acceptances, not fewer - giving the model a
# vehicle to construct a plausible-sounding justification appears to have
# made it more persuasively confident, not more conservative. This gate does
# the opposite: it never asks the model anything new, and it can only VETO an
# acceptance the model already gave - it never grants one.
#
# The real, confirmed false-accept pairs this session found (#5058/#3817,
# #7448/#356, #4204/#7176 - recurring commodity/currency reports; #11371/
# #8807 - recurring political sparring) all share one structural trait: the
# model's own "evidence" strings, once the vocabulary the two TITLES already
# share (the recurring subject itself - "gold", "silver", "rupee", "Rahul
# Gandhi", "Modi") is discounted, contain no remaining concrete, checkable
# content - just a restatement of the shared subject. A genuine relationship's
# evidence names a specific fact beyond the shared subject (a number, a
# ruling, a named action) and clears this easily.
# --------------------------------------------------------------------------

_STOP = cluster._STOP
_GENERIC_KW = cluster._GENERIC_KW

# cluster._STOP is tuned for TITLE/SUMMARY prose, not the connective/framing
# words a model's own "evidence" sentences are full of ("both", "mention",
# "states", "describes", "current", "candidate"...) - left unfiltered, these
# leak through as apparent "content" and silently defeat Gate AA2's whole
# point. Small, local to this module only - never touches cluster.py.
_EVIDENCE_STOP = {
    "both", "mention", "mentions", "mentioned", "state", "states", "stated",
    "describe", "describes", "described", "discuss", "discusses", "regarding",
    "concern", "concerns", "concerning", "current", "candidate", "event",
    "events", "text", "texts", "report", "reports", "reported", "indicate",
    "indicates", "indicating", "suggest", "suggests", "suggesting", "note",
    "notes", "noting", "detail", "details", "specific", "explicitly", "while",
}


def _content_tokens(text: str) -> set[str]:
    """Lowercase, non-stopword, non-generic tokens (>=3 chars). Reuses
    cluster.py's own stopword/generic-commodity-vocabulary lists (read-only)
    so 'generic' means the same thing here as it already does to Stage 1's
    retrieval gate, rather than inventing a second, different notion; adds
    _EVIDENCE_STOP on top for this module's own evidence-sentence framing
    words (see above)."""
    toks = set(re.findall(r"[a-z]{3,}", (text or "").lower()))
    return ((toks - _STOP) - _GENERIC_KW) - _EVIDENCE_STOP


def _evidence_is_specific(evidence: list, current_text: str, candidate_text: str) -> bool:
    """True if at least one evidence string contains >=2 content tokens
    beyond the vocabulary the two events' FULL text (title+summary) already
    shares. Title-only sharing was tried first and empirically failed to
    catch the real #11371/#8807 shape: both summaries independently mention
    "students", so an evidence bullet naming "students" reads as a distinct
    fact if only the (much shorter) titles are used as the discount baseline,
    even though it is really just the same broader recurring theme repeated.
    Using the full text closes that gap. Never called when current_text/
    candidate_text are not supplied - see accept()'s opt-in contract below."""
    shared_subject = _content_tokens(current_text) & _content_tokens(candidate_text)
    for ev in evidence:
        remaining = _content_tokens(ev) - shared_subject
        if len(remaining) >= 2:
            return True
    return False


# --------------------------------------------------------------------------
# Gate AA: acceptance policy. A DECISION, tested against real validation
# results in the Phase 21E report - not assumed here. R1/R2/R3 require high
# confidence; R4 (inherently the weakest-evidenced positive category) also
# requires high confidence given Principle 1 (false positive > false
# negative) - medium-confidence acceptance was tested and rejected, see the
# report's Gate AA section.
#
# current_text/candidate_text are OPTIONAL and default to None, which SKIPS
# Gate AA2 entirely - this preserves every pre-hardening call site's exact
# prior behavior (in particular every test in
# test_phase21e_relationship_judgment.py that calls accept(result) alone).
# Only a caller that supplies both (select_context(), below, and any future
# production caller) gets the new backstop applied. Each should be the
# event's title+summary combined, not title alone - see _evidence_is_specific.
#
# Gate AA4 (overnight Stage-2 hardening): Politics/Economy-topic R3/R4
# requires same_storyline corroboration. Live validation on the real
# #11371/#8807 canary (Politics) showed the failure is CONCENTRATED in R3/R4
# (the two vaguer categories - "materially escalates" / "materially
# explains" - that most invite rationalization) and that neither further
# prompt refinement (Hard Rule 9) nor independent two-pass confirmation
# reliably suppressed it: 8/8 two-pass-confirmed live trials still agreed on
# a false R3/high accept, and the pair's genuinely shared vocabulary (rahul,
# gandhi, narendra, prime, parliament, students - 9 tokens) is rich enough
# that no token-count threshold safely separates it from a real case either.
# Shadow replay against real, unseen recent events (2026-09-03) then
# surfaced the SAME pattern in Economy: two independent market reactions to
# an ongoing Middle East conflict (#12833/#17453, #15445/#17453), each
# citing a genuinely DIFFERENT specific trigger, both still accepted R3/high
# 6/6 across two rounds of live testing even after Hard Rule 8 was
# explicitly broadened to name this exact "recurring macro-narrative, new
# specific trigger each time" shape - prompt refinement alone did not
# generalize across topics either. Stage 1's same_storyline flag is an
# independent, already-computed, real signal (built from semantic
# clustering, not this module's own reasoning) - requiring it for the two
# riskiest categories in the two topics where this was actually measured is
# a genuine, structural risk reduction, not a claimed fix. R1/R2 (which
# already require explicit continuation/response language) are unaffected,
# and every OTHER topic is unaffected - this narrows only the two categories
# and the two topics actually implicated by real, live-tested evidence.
# same_storyline is OPTIONAL (default None) and, like current_text/
# candidate_text, this check is SKIPPED unless the caller supplies both
# current_topic and candidate_topic - old call sites are unaffected.
# --------------------------------------------------------------------------

_GATE_AA4_TOPICS = {"Politics", "Economy"}


def accept(result: JudgeResult, *, current_text: Optional[str] = None,
           candidate_text: Optional[str] = None, current_topic: Optional[str] = None,
           candidate_topic: Optional[str] = None, same_storyline: bool = False) -> bool:
    if not result.raw_valid:
        return False
    if not result.related:
        return False
    if result.relationship_type not in POSITIVE_TYPES:
        return False
    if result.confidence != "high":
        return False
    if current_text is not None and candidate_text is not None:
        if not _evidence_is_specific(result.evidence, current_text, candidate_text):
            return False
    if current_topic is not None and candidate_topic is not None:
        if (current_topic in _GATE_AA4_TOPICS and candidate_topic in _GATE_AA4_TOPICS
                and current_topic == candidate_topic
                and result.relationship_type in ("R3", "R4") and not same_storyline):
            return False
    return True


# --------------------------------------------------------------------------
# Gate AB/AC: context selection - up to 3 judged candidates -> at most 2
# VERIFIED historical predecessors, chronologically ordered, non-redundant.
# --------------------------------------------------------------------------

def select_context(current_event: dict, candidates: list[JudgeCandidate],
                    results: dict[int, JudgeResult], max_context: int = 2):
    cur_text = f"{current_event.get('title', '')} {current_event.get('summary', '') or ''}"
    cur_topic = current_event.get("topic")
    accepted = [(c, results[c.previous_event_id]) for c in candidates
                if c.previous_event_id in results and
                accept(results[c.previous_event_id], current_text=cur_text,
                       candidate_text=f"{c.previous_title} {c.previous_summary or ''}",
                       current_topic=cur_topic, candidate_topic=c.previous_topic,
                       same_storyline=c.same_storyline)]
    if not accepted:
        return []
    # Redundancy: drop a candidate whose title is near-identical to an
    # already-kept one (same-day, near-duplicate coverage of the same wire
    # story) - keep the one with the richer summary.
    kept = []
    for c, r in sorted(accepted, key=lambda cr: (cr[0].gap_days if cr[0].gap_days is not None else 1 << 30)):
        redundant = False
        for kc, kr in kept:
            if kc.previous_date == c.previous_date and \
               len(set(c.previous_title.lower().split()) &
                   set(kc.previous_title.lower().split())) >= 3:
                redundant = True
                break
        if not redundant:
            kept.append((c, r))
    kept.sort(key=lambda cr: cr[0].previous_date or "")
    return kept[:max_context]


# --------------------------------------------------------------------------
# Real (or mocked, via generate_fn) Gemini call - Gate P: reuses analyze.py's
# own, already-tested _gemini_generate, never reimplements the HTTP/retry
# logic. Isolated: analyze.py is READ from, never written to or called into
# this module from analyze.py's own pipeline.
# --------------------------------------------------------------------------

def judge_relationships(current_event: dict, candidates: list[JudgeCandidate],
                         generate_fn=None) -> dict[int, JudgeResult]:
    """generate_fn(prompt: str) -> str. Defaults to a real Gemini call via
    analyze._gemini_generate (as_json=True) - the SAME call path production
    reframe.py/analyze.py already use, per Gate P. Pass a mock generate_fn
    for deterministic tests; never called with generate_fn=None in a test."""
    if not candidates:
        return {}
    expected_ids = [c.previous_event_id for c in candidates]
    prompt = build_judgment_prompt(current_event, candidates)
    if generate_fn is None:
        generate_fn = lambda p: analyze._gemini_generate(p, as_json=True)
    try:
        raw_text = generate_fn(prompt)
    except Exception as e:
        return {eid: _reject(eid, f"LLM call failed: {e}") for eid in expected_ids}
    return parse_judgments(raw_text, expected_ids)


# --------------------------------------------------------------------------
# Gate AA3 (overnight Stage-2 hardening): two-pass confirmation.
#
# Live validation (2026-09-03) measured genuine, structural repeat-call
# instability on the real #11371/#8807 canary that prompt refinement alone
# (Hard Rule 9) did not resolve: 9 repeat live calls with the improved
# prompt still split 3 correct (medium/reject) to 6 incorrect (high/accept) -
# this is temperature-driven stochastic disagreement with itself, not a
# wording problem a single call's prompt can fix. Asking the SAME call to be
# MORE careful within one shot was already tried twice (shared_anchor,
# substitution-test) and made things worse, not better - so this asks the
# SAME question a SECOND, INDEPENDENT time instead, and only keeps a
# candidate if BOTH calls agree it should be accepted. This does not
# guarantee zero false accepts on a pair this unstable (if a single call's
# false-accept rate is p, two independent agreeing calls happen at roughly
# p^2, not zero) - it is a genuine, measured risk reduction, not a claimed
# fix, and Gate AA2/the prompt rules still apply identically to both passes.
# Only doubles cost for candidates that already cleared pass 1 (Gate 22G's
# cost guard), not every Stage-1 candidate.
# --------------------------------------------------------------------------

def judge_relationships_confirmed(current_event: dict, candidates: list[JudgeCandidate],
                                   generate_fn=None) -> dict[int, JudgeResult]:
    """Same contract as judge_relationships(), but every candidate that
    passes the base accept() gate (relationship_type/confidence only - Gate
    AA2's text-specificity check still applies afterward, in select_context())
    is re-judged once more, independently, and kept only if the second pass
    also passes. A candidate that disagrees on the second pass becomes a
    fail-closed rejection with reject_reason recording both passes, for
    auditability - never silently dropped, never silently kept."""
    first = judge_relationships(current_event, candidates, generate_fn)
    by_id = {c.previous_event_id: c for c in candidates}
    out = dict(first)
    for eid, r in first.items():
        if not accept(r):
            continue
        c = by_id.get(eid)
        if c is None:
            continue
        second = judge_relationships(current_event, [c], generate_fn)
        r2 = second.get(eid)
        if r2 is None or not accept(r2):
            p2_desc = f"{r2.relationship_type}/{r2.confidence}" if r2 else "no result"
            out[eid] = _reject(eid, "confirmation pass did not independently accept "
                                     f"(pass1={r.relationship_type}/{r.confidence}, pass2={p2_desc})")
    return out
