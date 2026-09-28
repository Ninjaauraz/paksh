"""replay_shadow_trial_offline.py - Step 6: offline replay of the 40 real
shadow-trial stories using claim_clustering.py. ZERO API calls, ZERO network
access - reads only shadow_trial_report.jsonl (already on disk).

IMPORTANT LABELING (per the task's explicit requirement): the raw structured
claim objects were never saved by shadow_trial.py (see this session's Step 1
report) - only pre-formatted, human-readable finding-reason STRINGS were
checkpointed. Everything this script extracts from those strings is DERIVED
OFFLINE, not CAPTURED - a lossy, approximate reconstruction via regex against
this codebase's OWN known reason-string templates (verified against the
source before writing this parser), never a replay of the true original
claim objects, and never presented as such. Fields that cannot be recovered
(evidence_quote, full provenance, unparsed claims from findings that don't
match a known template) are left MISSING, not guessed.
"""
import json
import re

from claim_clustering import cluster_evidence_claims

REPORT_PATH = "shadow_trial_report.jsonl"

# Regexes matching this session's OWN exact f-string templates (verified via
# `grep -n '"reason":' consistency_checks.py phase11_verification.py` before
# writing these, not assumed).
_RE_DOWNGRADE_DROP = re.compile(r"^evidence explicitly states (\w+) for \((.+?), (.+?)\) but synthesis drops the qualification$")
_RE_DOWNGRADE_OMIT = re.compile(r"^evidence explicitly states (\w+) for \((.+?), (.+?)\) but synthesis omits this claim entirely$")
_RE_UNSUPPORTED_ADD = re.compile(r"^synthesis asserts (\w+) for \((.+?), (.+?)\) but no evidence supports this status$")
_RE_NUMERIC = re.compile(r"^evidence value (.+?) vs synthesis value (.+)$")
_RE_SHARED_NAME = re.compile(r"^shared short name (\{.+?\}) but at least one side has no stated expansion")
_RE_ATTRIBUTION = re.compile(r"^evidence attributes this claim to '(.+?)' \(not a routine institutional source\) but the synthesis drops this attribution entirely$")


def derive_claims_from_findings(findings):
    """-> (evidence_claims_derived, synthesis_claims_derived, unparsed).
    DERIVED, approximate, lossy - see module docstring. Each derived claim
    dict carries only the fields recoverable from the reason string; every
    other claim_clustering.py-expected field is filled with a safe MISSING
    default (None/UNSPECIFIED), never guessed at a specific value."""
    ev_claims, synth_claims, unparsed = [], [], []
    for idx, f in enumerate(findings):
        m = _RE_DOWNGRADE_DROP.match(f) or _RE_DOWNGRADE_OMIT.match(f)
        if m:
            status, subj, pred = m.groups()
            ev_claims.append({"subject": subj, "predicate": pred, "object": None, "status": status,
                               "fact_type": None, "value": None, "domain": None,
                               "time_type": "UNSPECIFIED", "time_text": None, "source": f"derived_ev_{idx}",
                               "_derived_from": f})
            continue
        m = _RE_UNSUPPORTED_ADD.match(f)
        if m:
            status, subj, pred = m.groups()
            synth_claims.append({"subject": subj, "predicate": pred, "object": None, "status": status,
                                  "fact_type": None, "value": None, "domain": None,
                                  "time_type": "UNSPECIFIED", "time_text": None, "source": f"derived_synth_{idx}",
                                  "_derived_from": f})
            continue
        m = _RE_NUMERIC.match(f)
        if m:
            a_val, b_val = m.groups()
            unparsed.append(("numeric", f))  # numeric pairs are ALREADY pairwise in the
            # original finding, not individual claims - correctly excluded from clustering
            # input (clustering claims that are already a compared PAIR would be circular);
            # counted separately below as "numeric findings observed", not clustered.
            continue
        m = _RE_SHARED_NAME.match(f)
        if m:
            unparsed.append(("entity_ambiguity_pre_fix", f))  # already fixed separately (Fix from prior turn) - not this module's concern
            continue
        m = _RE_ATTRIBUTION.match(f)
        if m:
            unparsed.append(("attribution_loss", f))
            continue
        unparsed.append(("unrecognized_template", f))
    return ev_claims, synth_claims, unparsed


def main():
    with open(REPORT_PATH, encoding="utf-8") as f:
        lines = [json.loads(l) for l in f][:40]

    print(f"{'story':>8} {'before':>8} {'after_clusters':>15} {'collapsed':>10} {'unparsed':>10}")
    total_before = total_after = total_collapsed = total_unparsed = 0
    hypothetical_flips = []
    rows = []

    for l in lines:
        findings = l.get("new_pipeline_findings") or []
        ev_claims, synth_claims, unparsed = derive_claims_from_findings(findings)
        all_derived = ev_claims + synth_claims
        before = len(all_derived)
        if before == 0:
            clusters, _ = [], 0
        else:
            clusters, _ = cluster_evidence_claims(all_derived)
        after = len(clusters)
        collapsed = before - after
        total_before += before
        total_after += after
        total_collapsed += collapsed
        total_unparsed += len(unparsed)
        rows.append((l["event_id"], before, after, collapsed, len(unparsed)))
        print(f"{l['event_id']:>8} {before:>8} {after:>15} {collapsed:>10} {len(unparsed):>10}")

        # HYPOTHETICAL_OFFLINE_OUTCOME: would this story's HOLD status change if
        # the collapsed (redundant) downgrade/addition claims no longer each
        # produced their own finding? Conservative estimate only - see caveats
        # printed at the end. Does NOT touch the recorded historical outcome.
        if l.get("new_pipeline_outcome") == "HOLD":
            # count genuinely DISTINCT clusters that still show a real disagreement
            # or a cluster with zero matching counterpart (still a real, non-redundant finding)
            remaining_real = sum(1 for c in clusters if c["claim_count"] == 1 or c["disagreement"])
            numeric_findings = sum(1 for kind, _ in unparsed if kind == "numeric")
            hypothetical_flips.append({
                "event_id": l["event_id"], "title": l["title"],
                "original_finding_count": before,
                "hypothetical_remaining_findings": remaining_real + numeric_findings,
                "would_still_hold_hypothetically": (remaining_real + numeric_findings) > 0,
            })

    print(f"\n{'=' * 70}")
    print(f"TOTALS across 40 stories: before={total_before} after_clusters={total_after} "
          f"collapsed={total_collapsed} unparsed={total_unparsed}")
    print(f"(unparsed includes: numeric findings - excluded from this module's clustering "
          f"input by design; pre-fix entity_ambiguity duplicates - already handled by a "
          f"separate, already-applied fix; any reason string not matching a known template)")

    print(f"\n{'=' * 70}\nHYPOTHETICAL_OFFLINE_OUTCOME (NOT a real rerun - conservative, derived-data estimate only)")
    would_flip = [h for h in hypothetical_flips if not h["would_still_hold_hypothetically"]]
    would_still_hold = [h for h in hypothetical_flips if h["would_still_hold_hypothetically"]]
    print(f"Of {len(hypothetical_flips)} real HOLD stories:")
    print(f"  would hypothetically have ZERO remaining findings after clustering: {len(would_flip)}")
    print(f"  would hypothetically STILL show a genuine remaining finding: {len(would_still_hold)}")
    for h in would_flip:
        print(f"    [WOULD FLIP] {h['event_id']} {h['title'][:60]!r} ({h['original_finding_count']} -> 0)")

    with open("shadow_trial_offline_replay.json", "w", encoding="utf-8") as f:
        json.dump({"rows": rows, "hypothetical_flips": hypothetical_flips}, f, indent=2, ensure_ascii=False)
    print("\nSaved detail to shadow_trial_offline_replay.json")


if __name__ == "__main__":
    main()
