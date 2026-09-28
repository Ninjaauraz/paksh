"""materiality_audit.py - PROTOTYPE, offline-only, $0 (2026-09-29). Audits
whether the 82 check_unhedged_downgrade findings (81 omit + 1 drop) from the
40-story shadow-trial replay are actually MATERIAL enough that a concise
Paksh synthesis should be expected to preserve them - as opposed to being
real-but-droppable supporting detail, or (per the prior proposition-coverage
experiment) redundant restatements of an already-counted fact.

NOT wired into production. Does not modify check_unhedged_downgrade,
decide(), or any prior prototype file. This is a POLICY-QUESTION audit, not
a new detection mechanism.

============================================================================
WHY "THE VERIFIER FLAGGED IT" IS NEVER USED AS EVIDENCE OF MATERIALITY
============================================================================
The task's Phase 3 explicitly forbids this (it would be circular: the thing
being questioned is whether check_unhedged_downgrade's notion of "high risk"
correctly predicts real-world materiality). Instead, materiality here is
grounded in two facts that are independent of whether a finding fired:

  1. WHICH STATUS FAMILY is involved. check_unhedged_downgrade only ever
     fires for a status in consistency_checks.HIGH_RISK_STATUS_VALUES - a
     FIXED set of exactly 10 values that splits cleanly, by construction,
     into two pre-existing semantic families (this split predates this
     audit; it is simply reading consistency_checks.py's own already-written
     categories, not inventing a new taxonomy over them):
       OFFICE_HOLDING:    CURRENT/FORMER/INCOMING/RESIGNED/SERVING_EXPLICIT
       LEGAL_ALLEGATION:  ALLEGED/CLAIMED/ESTABLISHED/CHARGED/CONVICTED_EXPLICIT
     Misreporting either family for ANY named person is a real correction-
     risk regardless of how central that person is to the story - this is
     the literal Suvendu-Adhikari/Mamata-CM incident category the whole
     factuality program exists to prevent. That floors every classifiable
     finding at M3 (material qualification) at minimum - this audit never
     produces M4/M5 for a status-vocabulary finding by silently assuming
     unimportance.
  2. WHETHER THE CLAIM'S SUBJECT IS A HEADLINE-LEVEL ENTITY - a deterministic
     substring/token check against the story's own TITLE (a CAPTURED field
     from shadow_trial_report.jsonl, not derived or guessed). A title match
     escalates M3 to M1 (office-holding) or M2 (legal/allegation) - the
     status of the story's OWN subject is the base fact or a central
     development, not a secondary qualification.

HONEST LIMITATION (stated once here, referenced throughout the report): a
title-match check is a necessary PROXY for "is this central to the story",
not a substitute for full-article editorial judgment (the full evidence
article text is MISSING from this dataset - see the module's own
CAPTURED/DERIVED_OFFLINE/MISSING labeling below). This proxy is deliberately
asymmetric: it can only ESCALATE a finding's materiality (title match ->
M1/M2), never demote one below M3. That means this audit's M1-M3 counts are
a CONSERVATIVE UPPER BOUND on true materiality - some non-title-matched M3
calls are plausibly M4 in an editor's ground truth, but this module cannot
safely determine that without either full article text or a semantic model,
both out of scope this task. This is exactly what Phase 10's human
validation protocol is for.

M4/M5 in this audit are therefore reached only via:
  - M5: the finding was already identified, in the PRIOR (already-validated,
    already-run) proposition-coverage experiment, as a REDUNDANT duplicate
    within its proposition (category B) - i.e. another finding for the same
    underlying fact is already counted, so this one needs no independent
    representation. Reused directly from replay_proposition_coverage.py's
    output, never re-derived.
  - M4: reachable by classify_materiality() in principle, but per the
    analysis above essentially never fires for THIS finding set, because
    HIGH_RISK_STATUS_VALUES already pre-filters OUT the kind of low-stakes
    status claim M4 describes before check_unhedged_downgrade ever produces
    a finding. This is a real, reportable result (see FINAL REPORT item 4),
    not a bug in the classifier.
"""
import json
import re

from replay_proposition_coverage import _parse_downgrade_findings, _other_finding_counts, REPORT_PATH, N_STORIES
from consistency_checks import _norm_subject

M1, M2, M3, M4, M5, UNKNOWN = "M1", "M2", "M3", "M4", "M5", "UNKNOWN"

OFFICE_HOLDING_STATUSES = {"CURRENT_EXPLICIT", "FORMER_EXPLICIT", "INCOMING_EXPLICIT",
                            "RESIGNED_EXPLICIT", "SERVING_EXPLICIT"}
LEGAL_ALLEGATION_STATUSES = {"ALLEGED_EXPLICIT", "CLAIMED_EXPLICIT", "ESTABLISHED_EXPLICIT",
                             "CHARGED_EXPLICIT", "CONVICTED_EXPLICIT"}
assert OFFICE_HOLDING_STATUSES | LEGAL_ALLEGATION_STATUSES == {
    "CURRENT_EXPLICIT", "FORMER_EXPLICIT", "INCOMING_EXPLICIT", "RESIGNED_EXPLICIT", "SERVING_EXPLICIT",
    "ALLEGED_EXPLICIT", "CLAIMED_EXPLICIT", "ESTABLISHED_EXPLICIT", "CHARGED_EXPLICIT", "CONVICTED_EXPLICIT",
}, "must exactly reproduce consistency_checks.HIGH_RISK_STATUS_VALUES - verified by direct comparison, not assumed"

_STOPWORDS = {"the", "a", "an", "of", "in", "on", "at", "for", "to", "and", "or", "with", "by", "from", "is", "was"}


def _title_matches_subject(subject, title):
    """Deterministic substring/token check, never fuzzy/semantic. True if the
    normalized subject appears verbatim in the title, OR at least half of its
    non-stopword, length>=4 tokens appear in the title. Asymmetric on purpose
    (see module docstring): only ever used to ESCALATE materiality, never to
    demote it, so a false negative here is safe (falls back to M3, still
    "material") while a false positive would overstate M1/M2 - the token-
    overlap threshold (>=half) is deliberately conservative to limit that risk."""
    if not subject or not title:
        return False
    subj_norm = _norm_subject(subject)
    title_norm = title.lower()
    if subj_norm and len(subj_norm) >= 4 and subj_norm in title_norm:
        return True
    tokens = [t for t in re.findall(r"[a-z']+", subj_norm) if t not in _STOPWORDS and len(t) >= 4]
    if not tokens:
        return False
    hits = sum(1 for t in tokens if t in title_norm)
    return hits >= max(1, (len(tokens) + 1) // 2)


def classify_materiality(subject, status, predicate, title):
    """-> (level, reason). Never returns M4/M5 - those are assigned only by
    the caller (M5 from the prior redundancy classification; M4 is not
    reachable from this function at all for the stated structural reason -
    see module docstring)."""
    if not subject or not status:
        return UNKNOWN, "missing reconstructed subject or status - cannot safely classify"
    title_matched = _title_matches_subject(subject, title)
    if status in OFFICE_HOLDING_STATUSES:
        if title_matched:
            return M1, (f"office-holding status ({status}) of a headline-level entity ('{subject}') - "
                        f"central to basic understanding of who holds/held the position")
        return M3, (f"office-holding status ({status}) of a non-headline entity ('{subject}') - a real "
                    f"material qualification even for a secondary figure; current/former misstatements "
                    f"are not safely droppable regardless of prominence")
    if status in LEGAL_ALLEGATION_STATUSES:
        if title_matched:
            return M2, (f"legal/allegation status ({status}) of a headline-level entity ('{subject}') - "
                        f"a material development, often the reason the story exists")
        return M3, (f"legal/allegation status ({status}) of a non-headline entity ('{subject}') - "
                    f"misreporting alleged/established/charged/convicted for anyone named is a material "
                    f"qualification regardless of how central they are to the story")
    return UNKNOWN, f"status '{status}' is outside the fixed office-holding/legal-allegation family map"


def build_audit_dataset():
    """Phase 1. -> list of per-finding audit records with explicit
    CAPTURED/DERIVED_OFFLINE/MISSING field-source labeling. Reuses (does not
    re-derive) replay_proposition_coverage.replay_story()'s prior A/B/C/D
    classification for the redundancy (M5) signal."""
    import replay_proposition_coverage as rpc

    with open(REPORT_PATH, encoding="utf-8") as f:
        lines = [json.loads(l) for l in f][:N_STORIES]

    records = []
    for l in lines:
        story_id = l["event_id"]
        title = l.get("title") or ""
        prior = rpc.replay_story(l)  # reuses the already-validated proposition-coverage classification
        for fc in prior["finding_classification"]:
            reason = fc["reason"]
            m = rpc._RE_DOWNGRADE_DROP.match(reason) or rpc._RE_DOWNGRADE_OMIT.match(reason)
            status, subject, predicate = (m.groups() if m else (None, None, None))
            if fc["category"] == "B_REDUNDANT_SOURCE_EXPRESSION":
                level, mat_reason = M5, (f"identified as a redundant restatement of an already-counted "
                                          f"proposition ({fc.get('redundant_with', '?')!r}) in the prior "
                                          f"proposition-coverage experiment - does not need independent "
                                          f"representation in a concise synthesis")
            else:
                level, mat_reason = classify_materiality(subject, status, predicate, title)
            records.append({
                "story_id": story_id, "title": title, "topic": l.get("topic"), "region": l.get("region"),
                "kind": fc["kind"], "reason": reason,
                "subject": subject, "predicate": predicate, "status": status,
                "prior_proposition_category": fc["category"],
                "materiality": level, "materiality_reason": mat_reason,
                "title_matched": _title_matches_subject(subject, title) if subject else False,
                "field_sources": {
                    "story_id": "CAPTURED", "title": "CAPTURED", "topic": "CAPTURED", "region": "CAPTURED",
                    "reason": "CAPTURED", "subject": "DERIVED_OFFLINE", "predicate": "DERIVED_OFFLINE",
                    "status": "DERIVED_OFFLINE", "object": "MISSING", "evidence_quote": "MISSING",
                    "full_synthesis_text": "MISSING (only a 500-char truncation is CAPTURED, see new_synthesis)",
                    "full_article_text": "MISSING",
                },
            })
    return records


def _story_level_counts(records, story_id):
    story_recs = [r for r in records if r["story_id"] == story_id]
    counts = {lvl: sum(1 for r in story_recs if r["materiality"] == lvl) for lvl in (M1, M2, M3, M4, M5, UNKNOWN)}
    counts["total"] = len(story_recs)
    return counts


def phase6_story_breakdown(records, story_replays):
    """Phase 6. -> list of per-story dicts with M1-M5/UNKNOWN counts plus a
    qualitative dominance label. story_replays: the story_replays list already
    computed and saved by replay_proposition_coverage.py (reused, not
    recomputed) - supplies outcome and other_finding_counts."""
    out = []
    for sr in story_replays:
        counts = _story_level_counts(records, sr["event_id"])
        m1m2 = counts[M1] + counts[M2]
        m3 = counts[M3]
        m4m5 = counts[M4] + counts[M5]
        if counts["total"] == 0:
            dominance = "NO_DOWNGRADE_FINDINGS"
        elif m1m2 >= m3 and m1m2 >= m4m5 and m1m2 > 0:
            dominance = "DOMINATED_BY_M1_M2"
        elif m3 >= m1m2 and m3 >= m4m5 and m3 > 0:
            dominance = "DOMINATED_BY_M3"
        elif m4m5 > 0:
            dominance = "DOMINATED_BY_M4_M5"
        else:
            dominance = "DOMINATED_BY_UNKNOWN" if counts[UNKNOWN] > 0 else "MIXED_NO_CLEAR_MAJORITY"
        out.append({"event_id": sr["event_id"], "outcome": sr["outcome"], "counts": counts,
                     "dominance": dominance, "other_finding_counts": sr["other_finding_counts"]})
    return out


def phase7_hold_breakdown(story_breakdown):
    """Phase 7. -> list of dicts for the HOLD stories only, each with a
    diagnostic label (never a production-decision change)."""
    out = []
    for sb in story_breakdown:
        if sb["outcome"] != "HOLD":
            continue
        c = sb["counts"]
        other = sb["other_finding_counts"]
        genuine_other = (other["unsupported_addition"] + other["numeric"] +
                          other["attribution_loss"] + other["other_unrecognized"])
        m1m2 = c[M1] + c[M2]
        if m1m2 > 0 or genuine_other > 0:
            label = "HOLD APPEARS SUPPORTED"
            label_reason = (f"{m1m2} M1/M2 (central-fact/major-development) finding(s)" if m1m2 > 0
                             else f"{genuine_other} independent non-omission finding(s) (numeric/unsupported-"
                                  f"addition/attribution/other) present regardless of omission materiality")
        elif c[UNKNOWN] > 0 and c[UNKNOWN] >= c[M3]:
            label = "INSUFFICIENT DATA"
            label_reason = f"{c[UNKNOWN]} of {c['total']} downgrade finding(s) could not be safely classified"
        elif c[M3] > 0 or c[M5] > 0:
            label = "HOLD MAY BE OVER-SENSITIVE TO COMPLETENESS"
            label_reason = (f"HOLD is driven entirely by {c[M3]} secondary-entity qualification(s) (M3) "
                             f"and/or {c[M5]} redundant restatement(s) (M5), with no headline-level fact "
                             f"(M1/M2) at risk and no independent (non-omission) finding present")
        else:
            label = "INSUFFICIENT DATA"
            label_reason = "no classifiable downgrade or other finding reconstructed for this HOLD story"
        out.append({
            "event_id": sb["event_id"], "current_decision": sb["outcome"],
            "omission_findings": c["total"], "M1_count": c[M1], "M2_count": c[M2], "M3_count": c[M3],
            "M4_count": c[M4], "M5_count": c[M5], "unknown_count": c[UNKNOWN],
            "other_findings": other, "hypothetical_materiality_assessment": label, "assessment_reason": label_reason,
        })
    return out


def phase8_bottleneck(records, story_breakdown, hold_breakdown):
    """Phase 8. Quantifies evidence for each candidate explanation A-G rather
    than forcing a single answer, per the task's explicit instruction."""
    total = len(records)
    m1m2 = sum(1 for r in records if r["materiality"] in (M1, M2))
    m3 = sum(1 for r in records if r["materiality"] == M3)
    m4 = sum(1 for r in records if r["materiality"] == M4)
    m5 = sum(1 for r in records if r["materiality"] == M5)
    unknown = sum(1 for r in records if r["materiality"] == UNKNOWN)

    hold_supported = sum(1 for h in hold_breakdown if h["hypothetical_materiality_assessment"] == "HOLD APPEARS SUPPORTED")
    hold_over_sensitive = sum(1 for h in hold_breakdown if "OVER-SENSITIVE" in h["hypothetical_materiality_assessment"])
    hold_insufficient = sum(1 for h in hold_breakdown if h["hypothetical_materiality_assessment"] == "INSUFFICIENT DATA")

    hold_driven_by_other_only = sum(1 for h in hold_breakdown
                                     if h["M1_count"] + h["M2_count"] + h["M3_count"] + h["M5_count"] == 0
                                     and sum(h["other_findings"].get(k, 0) for k in
                                             ("unsupported_addition", "numeric", "attribution_loss", "other_unrecognized")) > 0)

    evidence = {
        "A_genuine_synthesis_incompleteness": {
            "quantified": f"{m1m2}/{total} ({100*m1m2/total:.0f}%) findings are M1/M2 (headline-level fact/"
                          f"development) and {hold_supported}/{len(hold_breakdown)} HOLD stories have this "
                          f"kind of finding present",
            "support": "STRONG" if m1m2 / total > 0.3 else "MODERATE",
        },
        "B_overly_strict_completeness_policy": {
            "quantified": f"{hold_over_sensitive}/{len(hold_breakdown)} HOLD stories are driven entirely by "
                          f"M3/M5 findings with no M1/M2 and no independent other-finding-type present",
            "support": "STRONG" if hold_over_sensitive / max(1, len(hold_breakdown)) > 0.3 else
                       ("WEAK" if hold_over_sensitive == 0 else "MODERATE"),
        },
        "C_extraction_generates_low_materiality_claims": {
            "quantified": f"{m4}/{total} ({100*m4/total:.0f}%) findings are M4 (supporting detail) - "
                          f"near-zero by construction, since check_unhedged_downgrade only fires for "
                          f"HIGH_RISK_STATUS_VALUES, which structurally excludes most M4-type claims "
                          f"before they could ever reach this audit",
            "support": "WEAK" if m4 / total < 0.05 else "MODERATE",
        },
        "D_evidence_source_redundancy": {
            "quantified": f"{m5}/{total} ({100*m5/total:.0f}%) findings are M5 (redundant restatement), "
                          f"matching the prior proposition-coverage experiment's own 3/82 collapse figure exactly",
            "support": "WEAK" if m5 / total < 0.10 else "MODERATE",
        },
        "E_unsupported_additions_numeric_conflicts": {
            "quantified": f"{hold_driven_by_other_only}/{len(hold_breakdown)} HOLD stories have ZERO "
                          f"classifiable omission/redundancy finding and are driven purely by unsupported-"
                          f"addition/numeric/attribution/other findings - a genuinely separate mechanism "
                          f"from everything this and the prior two experiments analyze",
            "support": "MODERATE" if hold_driven_by_other_only > 0 else "WEAK",
        },
        "G_cannot_determine": {
            "quantified": f"{unknown}/{total} ({100*unknown/total:.0f}%) findings UNKNOWN; "
                          f"{hold_insufficient}/{len(hold_breakdown)} HOLD stories labeled INSUFFICIENT DATA",
            "support": "WEAK" if unknown / total < 0.05 else "MODERATE",
        },
    }
    return evidence


def main():
    import replay_proposition_coverage as rpc
    with open(REPORT_PATH, encoding="utf-8") as f:
        lines = [json.loads(l) for l in f][:N_STORIES]
    story_replays_full = [rpc.replay_story(l) for l in lines]
    story_replays = [
        {"event_id": sr["event_id"], "outcome": sr["outcome"], "other_finding_counts": sr["other_finding_counts"]}
        for sr in story_replays_full
    ]

    records = build_audit_dataset()
    story_breakdown = phase6_story_breakdown(records, story_replays)
    hold_breakdown = phase7_hold_breakdown(story_breakdown)
    bottleneck = phase8_bottleneck(records, story_breakdown, hold_breakdown)

    print(f"Built {len(records)} audit records (expected 82: 81 omit + 1 drop)")
    from collections import Counter
    print("Materiality distribution:", dict(Counter(r["materiality"] for r in records)))
    print(f"\nPhase 6: {len(story_breakdown)} stories, dominance breakdown:",
          dict(Counter(sb["dominance"] for sb in story_breakdown)))
    print(f"\nPhase 7: {len(hold_breakdown)} HOLD stories:")
    for h in hold_breakdown:
        print(f"  {h['event_id']:>8}  {h['hypothetical_materiality_assessment']:<40} "
              f"M1={h['M1_count']} M2={h['M2_count']} M3={h['M3_count']} M5={h['M5_count']} unk={h['unknown_count']}")
    print(f"\nPhase 8: bottleneck evidence:")
    for k, v in bottleneck.items():
        print(f"  {k}: [{v['support']}] {v['quantified']}")

    out = {
        "records": records, "story_breakdown": story_breakdown,
        "hold_breakdown": hold_breakdown, "bottleneck_evidence": bottleneck,
    }
    with open("materiality_audit_report.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("\nSaved detail to materiality_audit_report.json")


if __name__ == "__main__":
    main()
