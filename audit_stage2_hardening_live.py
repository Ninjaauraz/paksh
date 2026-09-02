"""
audit_stage2_hardening_live.py - overnight Stage-2 hardening: LIVE Gemini
validation harness against real Paksh events.

Ad-hoc, explicitly-labeled, NOT part of the deterministic regression suite
(test_phase21e_relationship_judgment.py stays mock-only per its own
docstring). Makes real network calls to Gemini via analyze._gemini_generate,
through relationship_judgment.judge_relationships() - the exact production
call path Stage 2 would use, unmodified.

Read-only with respect to paksh.db: only SELECTs event rows to build real
JudgeCandidate/current_event dicts. Writes nothing, mutates nothing.

Run:  py audit_stage2_hardening_live.py
"""
import json
import sqlite3
import time

import ai_providers          # side effect: loads GEMINI_API_KEY from ai_keys.env
import relationship_judgment as rj

DB = "paksh.db"


def fetch(eid):
    conn = sqlite3.connect(DB)
    row = conn.execute("SELECT title, created_at, analysis_json FROM events WHERE id=?", (eid,)).fetchone()
    conn.close()
    if not row:
        raise ValueError(f"event #{eid} not found")
    title, created, aj = row
    d = json.loads(aj)
    return {
        "id": eid,
        "title": d.get("title") or title,
        "summary": d.get("summary") or "",
        "date": created,
        "topic": d.get("topic"),
        "region": d.get("region"),
    }


def as_current(e):
    return {"title": e["title"], "summary": e["summary"], "date": e["date"],
            "topic": e["topic"], "region": e["region"]}


def as_candidate(e, sim=0.90, count=5, storyline=False):
    return rj.JudgeCandidate(
        previous_event_id=e["id"], previous_title=e["title"], previous_summary=e["summary"],
        previous_date=e["date"], previous_topic=e["topic"], previous_region=e["region"],
        semantic_similarity=sim, lexical_overlap_terms=[], lexical_overlap_count=count,
        same_storyline=storyline, thin_source=len(e["summary"]) < 40, gap_days=None,
    )


# (current_id, candidate_id, expected, label)
# expected: "REJECT" = must not be accepted; "ACCEPT-OR-ABSTAIN" = accept is fine,
# A1/N1/N2/medium-reject is also fine (never REQUIRED to accept - Section 18: precision
# over recall, abstention always safe); "SHOULD-ACCEPT" = a clean, genuine, previously-
# confirmed positive - flag if it now gets rejected (would be a new regression the other way).
CASES = [
    (5058, 3817, "REJECT", "gold/silver commodity report pair (known false R1)"),
    (7448, 356, "REJECT", "rupee/dollar commodity report pair (known false R1)"),
    (4204, 7176, "REJECT", "oil/crude commodity report pair (known false R3)"),
    (11371, 8807, "REJECT", "Rahul Gandhi/Modi recurring political sparring (canary, historically unstable)"),
    (8807, 8821, "ACCEPT-OR-ABSTAIN", "Gandhi/Modi adjacent pair - not asserted positive, just another same-entity pair to watch"),
    (5968, 1662, "ACCEPT-OR-ABSTAIN", "Congress vs EC pair - topically adjacent, not asserted as a genuine relationship"),
    (17348, 12833, "ACCEPT-OR-ABSTAIN", "gold/oil global-markets pair - topically adjacent, not asserted as genuine"),
]

REPEATS = 3

if __name__ == "__main__":
    print(f"Stage-2 hardened live validation - {len(CASES)} pairs x {REPEATS} repeats\n")
    summary_rows = []
    for cur_id, cand_id, expected, label in CASES:
        cur = fetch(cur_id)
        cnd = fetch(cand_id)
        print("=" * 100)
        print(f"#{cur_id} -> #{cand_id}   [{label}]   expected={expected}")
        print(f"  current : {cur['title']}")
        print(f"  candidate: {cnd['title']}")
        for i in range(REPEATS):
            current_event = as_current(cur)
            candidate = as_candidate(cnd)
            try:
                results = rj.judge_relationships(current_event, [candidate])
            except Exception as e:
                print(f"  run {i+1}: EXCEPTION {e}")
                continue
            r = results.get(cand_id)
            if r is None:
                print(f"  run {i+1}: no result returned")
                continue
            accepted = rj.accept(
                r,
                current_text=f"{cur['title']} {cur['summary']}",
                candidate_text=f"{cnd['title']} {cnd['summary']}",
            )
            gate_aa2_would_have_vetoed = (
                r.raw_valid and r.related and r.relationship_type in rj.POSITIVE_TYPES
                and r.confidence == "high" and not accepted
            )
            print(f"  run {i+1}: type={r.relationship_type:<3} conf={r.confidence:<6} "
                  f"raw_valid={r.raw_valid} accept={accepted}"
                  f"{'  <- Gate AA2 vetoed a high-confidence positive' if gate_aa2_would_have_vetoed else ''}")
            for ev in r.evidence:
                print(f"       evidence: {ev}")
            summary_rows.append((cur_id, cand_id, expected, i + 1, r.relationship_type, r.confidence, accepted))
            time.sleep(1)
        print()

    print("=" * 100)
    print("SUMMARY")
    bad = []
    for cur_id, cand_id, expected, run_i, rtype, conf, accepted in summary_rows:
        if expected == "REJECT" and accepted:
            bad.append((cur_id, cand_id, run_i, rtype, conf))
    if bad:
        print(f"FALSE ACCEPTS in required-reject pairs: {len(bad)}")
        for cur_id, cand_id, run_i, rtype, conf in bad:
            print(f"  #{cur_id}->#{cand_id} run {run_i}: {rtype}/{conf} incorrectly ACCEPTED")
    else:
        print("Zero false accepts among required-REJECT pairs across all runs.")
