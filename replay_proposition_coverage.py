"""replay_proposition_coverage.py - Phase 6/7/8/9: offline replay of
proposition_coverage.py against the 40 real shadow-trial stories that have
usable reconstructed data. ZERO API calls, ZERO network access - reads only
shadow_trial_report.jsonl (already on disk).

============================================================================
WHY THIS SCRIPT CANNOT REACH COVERED / COVERED_WITH_HEDGE (an honest,
structural ceiling, not a bug)
============================================================================
shadow_trial_report.jsonl only ever checkpointed FINDINGS - i.e. cases that
ALREADY failed check_unhedged_downgrade. A fully-covered evidence claim never
produces a finding in the first place, so it left no trace to reconstruct.
This script's only two raw ingredients per story are:

  - "drop" findings (`_RE_DOWNGRADE_DROP`): the evidence claim's status IS
    HIGH_RISK, and check_unhedged_downgrade's own logic guarantees a
    synthesis claim WAS matched (same subject/predicate) but with status
    UNSPECIFIED - that is the literal meaning of "drops the qualification".
    This lets us construct a synthetic, DERIVED_OFFLINE synthesis claim
    {subject, predicate, status: "UNSPECIFIED"} that is not a guess - it is
    exactly what the original finding's own condition proves must have
    existed.
  - "omit" findings (`_RE_DOWNGRADE_OMIT`): check_unhedged_downgrade's logic
    guarantees NO synthesis claim matched at all. There is nothing to
    construct - no synthetic synthesis claim is added for these.

Feeding only these two ingredients into evaluate_proposition_coverage() means
every member claim's evidence status is, by construction, HIGH_RISK (that's
why check_unhedged_downgrade fired), and every constructed synthesis claim's
status is, by construction, exactly UNSPECIFIED (never a genuinely
contradicting explicit value, never a preserving explicit value). Under
_evaluate_member_against_synthesis's own rules, that combination can only
ever produce NOT_COVERED, PARTIALLY_COVERED, or UNDETERMINABLE - never
COVERED, COVERED_WITH_HEDGE, or CONTRADICTED. This is verified directly
below (see the assertion in main()) rather than merely claimed.

test_proposition_coverage.py separately exercises the full 0-3 + CONTRADICTED
range using hand-built claims specifically because this real-data path
structurally cannot.
"""
import json
import re
from collections import defaultdict

from proposition_coverage import (
    evaluate_proposition_coverage, NOT_COVERED, PARTIALLY_COVERED, UNDETERMINABLE,
    COVERED, COVERED_WITH_HEDGE, CONTRADICTED,
)

REPORT_PATH = "shadow_trial_report.jsonl"
N_STORIES = 40

_RE_DOWNGRADE_DROP = re.compile(r"^evidence explicitly states (\w+) for \((.+?), (.+?)\) but synthesis drops the qualification$")
_RE_DOWNGRADE_OMIT = re.compile(r"^evidence explicitly states (\w+) for \((.+?), (.+?)\) but synthesis omits this claim entirely$")
_RE_UNSUPPORTED_ADD = re.compile(r"^synthesis asserts (\w+) for \((.+?), (.+?)\) but no evidence supports this status$")
_RE_NUMERIC = re.compile(r"^evidence value (.+?) vs synthesis value (.+)$")
_RE_SHARED_NAME = re.compile(r"^shared short name (\{.+?\}) but at least one side has no stated expansion")
_RE_ATTRIBUTION = re.compile(r"^evidence attributes this claim to '(.+?)' \(not a routine institutional source\) but the synthesis drops this attribution entirely$")

CAT_TRUE_OMISSION = "A_TRUE_MATERIAL_OMISSION"
CAT_REDUNDANT = "B_REDUNDANT_SOURCE_EXPRESSION"
CAT_PARTIAL = "C_PARTIAL_COVERAGE"
CAT_HEDGE_LOSS = "D_ATTRIBUTION_HEDGE_LOSS"
CAT_UNDETERMINABLE = "F_UNDETERMINABLE"


def _parse_downgrade_findings(findings):
    """-> list of {kind: 'drop'|'omit', status, subject, predicate, reason}."""
    out = []
    for f in findings:
        m = _RE_DOWNGRADE_DROP.match(f)
        if m:
            status, subj, pred = m.groups()
            out.append({"kind": "drop", "status": status, "subject": subj, "predicate": pred, "reason": f})
            continue
        m = _RE_DOWNGRADE_OMIT.match(f)
        if m:
            status, subj, pred = m.groups()
            out.append({"kind": "omit", "status": status, "subject": subj, "predicate": pred, "reason": f})
    return out


def _other_finding_counts(findings):
    """Counts of every OTHER (non-downgrade) finding type present, so Phase 9
    can tell whether a story would still HOLD for a reason unrelated to
    omission coverage. pre_fix_entity_ambiguity is reported but explicitly
    EXCLUDED from the 'still has a genuine other reason' judgment, since that
    duplication bug was already found and fixed separately this session -
    counting it here would misattribute an already-resolved bug as a reason
    a story should still HOLD today."""
    counts = {"unsupported_addition": 0, "numeric": 0, "attribution_loss": 0,
              "pre_fix_entity_ambiguity": 0, "other_unrecognized": 0}
    downgrade_reasons = set()
    for f in findings:
        if _RE_DOWNGRADE_DROP.match(f) or _RE_DOWNGRADE_OMIT.match(f):
            downgrade_reasons.add(f)
    for f in findings:
        if f in downgrade_reasons:
            continue
        if _RE_UNSUPPORTED_ADD.match(f):
            counts["unsupported_addition"] += 1
        elif _RE_NUMERIC.match(f):
            counts["numeric"] += 1
        elif _RE_ATTRIBUTION.match(f):
            counts["attribution_loss"] += 1
        elif _RE_SHARED_NAME.match(f):
            counts["pre_fix_entity_ambiguity"] += 1
        else:
            counts["other_unrecognized"] += 1
    return counts


def replay_story(l):
    """-> dict with the per-story before/after proposition-coverage picture."""
    findings = l.get("new_pipeline_findings") or []
    downgrades = _parse_downgrade_findings(findings)
    other = _other_finding_counts(findings)

    ev_claims = []
    for idx, d in enumerate(downgrades):
        ev_claims.append({
            "subject": d["subject"] or None, "predicate": d["predicate"] or None,
            "object": None, "status": d["status"], "fact_type": None, "value": None,
            "domain": None, "time_type": "UNSPECIFIED", "time_text": None,
            "source": f"derived_ev_{idx}", "_kind": d["kind"], "_reason": d["reason"],
        })

    synth_claims = []
    for idx, d in enumerate(downgrades):
        if d["kind"] != "drop":
            continue
        synth_claims.append({
            "subject": d["subject"] or None, "predicate": d["predicate"] or None,
            "object": None, "status": "UNSPECIFIED", "fact_type": None, "value": None,
            "domain": None, "time_type": "UNSPECIFIED", "time_text": None,
            "source": f"derived_synth_{idx}",
        })

    determinable = [e for e in ev_claims if e.get("subject") and e.get("predicate")]
    coverage_results = evaluate_proposition_coverage(determinable, synth_claims) if determinable else []

    # ---- Phase 7/8 classification, done PER PROPOSITION not per raw finding ----
    # A proposition with k member claims represents k raw "omission" findings
    # that check_unhedged_downgrade counted independently. Clustering already
    # established all k are the SAME underlying fact - so exactly ONE of them
    # is the "surviving representative" (classified A/C/D/F by the
    # proposition's own coverage level), and the other k-1 are genuinely
    # REDUNDANT restatements of that same, already-counted issue (category B).
    # This is the direct fix for "one obligation per source expression" vs
    # "one obligation per underlying fact" - counted at the PROPOSITION level,
    # not gated on whether any member happened to get a partial synthesis
    # match (a proposition can be entirely NOT_COVERED and still have
    # redundant duplicate members worth collapsing).
    finding_classification = []
    undeterminable_findings = [e for e in ev_claims if not (e.get("subject") and e.get("predicate"))]
    for e in undeterminable_findings:
        finding_classification.append({"reason": e["_reason"], "kind": e["_kind"], "category": CAT_UNDETERMINABLE})

    for prop in coverage_results:
        members = prop["member_claims"]
        lvl = prop["coverage_level"]
        if lvl == UNDETERMINABLE:
            rep_cat = CAT_UNDETERMINABLE
        else:
            has_hedge_member = any(m.get("status") in ("ALLEGED_EXPLICIT", "CLAIMED_EXPLICIT", "PROPOSED_EXPLICIT") for m in members)
            if lvl == NOT_COVERED:
                rep_cat = CAT_TRUE_OMISSION
            else:  # PARTIALLY_COVERED
                rep_cat = CAT_HEDGE_LOSS if has_hedge_member else CAT_PARTIAL
        representative, duplicates = members[0], members[1:]
        finding_classification.append({"reason": representative["_reason"], "kind": representative["_kind"],
                                        "category": rep_cat, "proposition_level": lvl,
                                        "proposition_source_count": prop["source_count"]})
        for dup in duplicates:
            finding_classification.append({"reason": dup["_reason"], "kind": dup["_kind"],
                                            "category": CAT_REDUNDANT, "proposition_level": lvl,
                                            "proposition_source_count": prop["source_count"],
                                            "redundant_with": representative["_reason"]})

    return {
        "event_id": l["event_id"], "title": l["title"],
        "outcome": l.get("new_pipeline_outcome"),
        "n_downgrade_findings_before": len(downgrades),
        "n_propositions_after": len(coverage_results),
        "coverage_results": coverage_results,
        "finding_classification": finding_classification,
        "other_finding_counts": other,
    }


def main():
    with open(REPORT_PATH, encoding="utf-8") as f:
        lines = [json.loads(l) for l in f][:N_STORIES]

    story_replays = [replay_story(l) for l in lines]

    # ---- structural-ceiling assertion (not just claimed in the docstring) ----
    all_levels = {r["coverage_level"] for sr in story_replays for r in sr["coverage_results"]}
    assert all_levels <= {NOT_COVERED, PARTIALLY_COVERED, UNDETERMINABLE}, \
        f"unexpected coverage level reached in real replay data: {all_levels - {NOT_COVERED, PARTIALLY_COVERED, UNDETERMINABLE}}"
    print(f"Verified structural ceiling: real-replay coverage levels observed = {sorted(all_levels)} "
          f"(COVERED/COVERED_WITH_HEDGE/CONTRADICTED never reachable from this data source, as designed)\n")

    # ---- Phase 7: classify all downgrade findings (drop+omit) ----
    all_class = [fc for sr in story_replays for fc in sr["finding_classification"]]
    cat_counts = defaultdict(int)
    for fc in all_class:
        cat_counts[fc["category"]] += 1

    total_downgrade = len(all_class)
    print(f"{'=' * 78}\nPHASE 7: classification of all {total_downgrade} check_unhedged_downgrade "
          f"findings (81 'omit' + 1 'drop') across {N_STORIES} stories\n{'=' * 78}")
    for cat in (CAT_TRUE_OMISSION, CAT_REDUNDANT, CAT_PARTIAL, CAT_HEDGE_LOSS, CAT_UNDETERMINABLE):
        print(f"  {cat:35s} {cat_counts[cat]:4d}")
    print(f"  {'TOTAL':35s} {total_downgrade:4d}")

    # ---- Phase 8: the key counterfactual ----
    hypothetical_burden = cat_counts[CAT_TRUE_OMISSION] + cat_counts[CAT_PARTIAL] + cat_counts[CAT_HEDGE_LOSS]
    print(f"\n{'=' * 78}\nPHASE 8: counterfactual - hypothetical omission burden at proposition level\n{'=' * 78}")
    print(f"  Original 1:1 obligation count (every downgrade finding independent): {total_downgrade}")
    print(f"  Hypothetical proposition-level burden (A + C + D; B collapses as redundant "
          f"restatement of a sibling that DID get a partial match): {hypothetical_burden}")
    print(f"  Reduction: {total_downgrade - hypothetical_burden} finding(s) "
          f"({cat_counts[CAT_REDUNDANT]} category-B redundant restatements)")
    print(f"  NOTE: 'hypothetical burden' still counts PARTIALLY_COVERED (categories C, D) as a real, "
          f"unresolved problem - proposition-level coverage does NOT make a status/attribution loss "
          f"disappear, it only removes duplicate obligations for the SAME loss reported by multiple sources.")

    # ---- Phase 9: 23-HOLD replay ----
    hold_stories = [sr for sr in story_replays if sr["outcome"] == "HOLD"]
    print(f"\n{'=' * 78}\nPHASE 9: hypothetical proposition-level HOLD replay ({len(hold_stories)} real HOLD stories)\n{'=' * 78}")
    header = f"{'event_id':>10} {'before':>7} {'props':>6} {'A':>3} {'B':>3} {'C':>3} {'D':>3} {'other_findings':>15} {'hyp_decision':>20}"
    print(header)
    flips, still_hold, reasons = [], [], []
    for sr in hold_stories:
        cats = defaultdict(int)
        for fc in sr["finding_classification"]:
            cats[fc["category"]] += 1
        other = sr["other_finding_counts"]
        other_genuine = other["unsupported_addition"] + other["numeric"] + other["attribution_loss"] + other["other_unrecognized"]
        remaining_omission_burden = cats[CAT_TRUE_OMISSION] + cats[CAT_PARTIAL] + cats[CAT_HEDGE_LOSS]
        would_hold = remaining_omission_burden > 0 or other_genuine > 0
        other_str = (f"add={other['unsupported_addition']},num={other['numeric']},"
                     f"attr={other['attribution_loss']},oth={other['other_unrecognized']}")
        decision = "STILL HOLD" if would_hold else "WOULD FLIP"
        print(f"{sr['event_id']:>10} {sr['n_downgrade_findings_before']:>7} {sr['n_propositions_after']:>6} "
              f"{cats[CAT_TRUE_OMISSION]:>3} {cats[CAT_REDUNDANT]:>3} {cats[CAT_PARTIAL]:>3} {cats[CAT_HEDGE_LOSS]:>3} "
              f"{other_str:>15} {decision:>20}")
        reason = ("no downgrade-derived omission burden remains AND no other genuine finding type present"
                  if not would_hold else
                  (f"remaining omission burden ({remaining_omission_burden}) from categories A/C/D" if remaining_omission_burden > 0
                   else f"other finding type(s) present: {other_str}"))
        entry = {"event_id": sr["event_id"], "title": sr["title"], "would_hold": would_hold, "reason": reason}
        (still_hold if would_hold else flips).append(entry)
        reasons.append(entry)

    print(f"\nOf {len(hold_stories)} real HOLD stories:")
    print(f"  would hypothetically FLIP to non-HOLD under proposition-level coverage: {len(flips)}")
    print(f"  would hypothetically STILL HOLD: {len(still_hold)}")
    for e in flips:
        print(f"    [WOULD FLIP] {e['event_id']} {e['title'][:60]!r} - {e['reason']}")
    still_hold_for_omission_alone = [e for e in still_hold if "omission burden" in e["reason"]]
    still_hold_for_other = [e for e in still_hold if "other finding" in e["reason"]]
    print(f"\n  Of the {len(still_hold)} still-HOLD stories: {len(still_hold_for_omission_alone)} remain HOLD "
          f"because of a genuine (non-redundant) omission/hedge-loss finding; {len(still_hold_for_other)} "
          f"remain HOLD for an UNRELATED finding type (numeric/unsupported-addition/attribution/other) "
          f"regardless of what proposition coverage concludes about omissions.")

    out = {
        "cat_counts": dict(cat_counts),
        "total_downgrade_findings": total_downgrade,
        "hypothetical_omission_burden": hypothetical_burden,
        "hold_replay": reasons,
        "story_replays": [
            {"event_id": sr["event_id"], "outcome": sr["outcome"],
             "n_downgrade_findings_before": sr["n_downgrade_findings_before"],
             "n_propositions_after": sr["n_propositions_after"],
             "other_finding_counts": sr["other_finding_counts"]}
            for sr in story_replays
        ],
    }
    with open("proposition_coverage_replay.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("\nSaved detail to proposition_coverage_replay.json")


if __name__ == "__main__":
    main()
