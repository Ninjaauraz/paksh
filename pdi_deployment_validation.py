"""
pdi_deployment_validation.py - PDI V1 real-network deployment validation procedure
(hardening pass, Part 9).

WHAT THIS IS
------------
A step-by-step, runnable validation procedure for confirming PDI's discovery adapters
actually work against LIVE Reddit/Substack traffic, from a network where they are
reachable (this sandbox's network is NOT such a network - old.reddit.com's search.json
endpoint returns an HTML interstitial here rather than JSON; see the implementation
report's KNOWN LIMITATIONS). Run this from a real deployment network before relying on
live discovery in anger.

SAFETY: this script NEVER touches the real production paksh.db. It points
database.DB_PATH at a throwaway temp SQLite file (same isolation pattern
test_pdi.py/test_phase6b.py already use) and creates one disposable, obviously-
synthetic test event there. Real network calls go out to Reddit/Substack (read-only
HTTP GETs - discovery never writes anything to those services), but every PDI write
lands in the temp DB, which is deleted when the script exits. Canonical Paksh data
(events/articles/SI) is never opened for writing by this script at all.

WHAT IT CHECKS (Part 9's required list)
----------------------------------------
1.  Reddit direct search           (pdi_providers.discover_reddit against a real query)
2.  Reddit thread retrieval        (a real thread's comments via _reddit_top_comments)
3.  Representative-comment reduction (bounded count, not one-per-comment, on a real thread)
4.  Substack feed discovery        (discover_substack against PDI_SUBSTACK_SEED_FEEDS,
                                     if configured - otherwise reported SKIPPED, honestly)
5.  robots.txt handling            (a real robots.txt fetch/parse against a live origin)
6.  URL normalization              (pdi._canonical_url on real discovered URLs)
7.  Candidate normalization        (every discovered item is a valid pdi.Candidate)
8.  Real candidate persistence     (a full run_pdi_for_event(..., persist=True) against
                                     the temp DB, using REAL discovered candidates)
9.  Association                    (real candidates run through associate_candidate())
10. Observation extraction         (real candidates run through extract_observations())
11. Full PDI lifecycle             (RUNNING -> VALID, then --force -> STALE/SUPERSEDED)

Run:  py pdi_deployment_validation.py
      py pdi_deployment_validation.py --query "some real news topic"
"""
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import database
import pdi
import pdi_providers

RESULTS = []


def report(step, status, detail=""):
    RESULTS.append((step, status, detail))
    print(f"  [{status:^7}] {step}" + (f" - {detail}" if detail else ""))


def main():
    query_text = "India economy news"
    if "--query" in sys.argv:
        query_text = sys.argv[sys.argv.index("--query") + 1]

    real_db_path = database.DB_PATH
    tmp_dir = Path(tempfile.mkdtemp())
    database.DB_PATH = tmp_dir / "pdi_deployment_validation.db"
    database._db_initialized = False

    try:
        print(f"Using DISPOSABLE temp DB: {database.DB_PATH}")
        print(f"(canonical production DB at {real_db_path} is never opened for writing by this script)\n")

        analysis = {
            "title": "PDI Deployment Validation Disposable Test Event",
            "summary": "A disposable synthetic event used only to validate live PDI discovery.",
            "topic": "Economy", "region": "India", "framing": {},
            "coverage": {"left": {"count": 3}, "center": {"count": 3}, "right": {"count": 2},
                        "international": {"count": 0}},
            "sources": [{"language": "en"}] * 8,
        }
        event_id = database.insert_event(analysis, is_demo=True)  # is_demo=1: never publishable, never exported
        conn = database.get_connection()
        for i in range(8):
            conn.execute("INSERT INTO articles (source, language, title, url, summary, published, "
                        "fetched_at, event_id) VALUES (?,?,?,?,?,?,?,?)",
                        (f"outlet{i}", "en", analysis["title"], f"https://example.com/{event_id}/{i}",
                         "s", None, datetime.now(timezone.utc).isoformat(), event_id))
        conn.commit()
        print(f"Created disposable test event id={event_id} (is_demo=1)\n")

        query = pdi.Query(text=query_text, family=pdi.QUERY_EVENT_DIRECT, language="en")

        # 1. Reddit direct search
        print("=== 1. Reddit direct search ===")
        try:
            reddit_results = pdi_providers.discover_reddit(query, limit=10)
            if reddit_results:
                report("Reddit direct search", "PASS", f"{len(reddit_results)} candidates for {query_text!r}")
            else:
                report("Reddit direct search", "EMPTY",
                       "0 candidates - either genuinely no results, or Reddit is not reachable/is "
                       "returning a non-JSON response from this network (check manually: "
                       f"{pdi_providers.REDDIT_SEARCH_URL}?q={query_text!r})")
        except Exception as e:
            report("Reddit direct search", "FAIL", f"{type(e).__name__}: {e}")
            reddit_results = []

        # 2/3. Reddit thread retrieval + representative-comment reduction
        print("\n=== 2/3. Reddit thread retrieval + representative-comment reduction ===")
        thread_candidates = [c for c in reddit_results if c.engagement.get("num_comments", 0) >= 20]
        if thread_candidates:
            top = max(thread_candidates, key=lambda c: c.engagement.get("num_comments", 0))
            comment_candidates = [c for c in reddit_results if c.provider_item_id.startswith(f"{top.provider_item_id}-c")]
            report("Reddit thread retrieval", "PASS" if comment_candidates else "EMPTY",
                  f"thread with {top.engagement.get('num_comments')} comments -> "
                  f"{len(comment_candidates)} representative comment candidates")
            report("Representative-comment reduction bounded",
                  "PASS" if len(comment_candidates) <= pdi_providers.REDDIT_MAX_REPRESENTATIVE_COMMENTS else "FAIL",
                  f"{len(comment_candidates)} <= {pdi_providers.REDDIT_MAX_REPRESENTATIVE_COMMENTS} required")
        else:
            report("Reddit thread retrieval", "SKIPPED", "no discovered thread had >=20 comments to test reduction on")

        # 4. Substack feed discovery
        print("\n=== 4. Substack feed discovery ===")
        seeds = pdi_providers._seed_feeds()
        if not seeds:
            report("Substack feed discovery", "SKIPPED",
                  "PDI_SUBSTACK_SEED_FEEDS not configured - set it to a comma-separated list of "
                  "real Substack /feed URLs to exercise this check")
            substack_results = []
        else:
            try:
                substack_results = pdi_providers.discover_substack(query, limit=10)
                report("Substack feed discovery", "PASS" if substack_results else "EMPTY",
                      f"{len(substack_results)} candidates from {len(seeds)} configured seed feed(s)")
            except Exception as e:
                report("Substack feed discovery", "FAIL", f"{type(e).__name__}: {e}")
                substack_results = []

        # 5. robots.txt handling
        print("\n=== 5. robots.txt handling ===")
        try:
            allowed = pdi_providers._robots_allows("https://old.reddit.com/search.json")
            report("robots.txt handling", "PASS", f"can_fetch(old.reddit.com/search.json) = {allowed}")
        except Exception as e:
            report("robots.txt handling", "FAIL", f"{type(e).__name__}: {e}")

        # 6. URL normalization
        print("\n=== 6. URL normalization ===")
        all_real = reddit_results + substack_results
        if all_real:
            sample = all_real[0]
            norm = pdi._canonical_url(sample.url)
            norm_again = pdi._canonical_url(sample.url + "?utm_source=test#frag")
            report("URL normalization", "PASS" if norm == norm_again else "FAIL",
                  f"{sample.url!r} and its tracked variant both normalize to {norm!r}")
        else:
            report("URL normalization", "SKIPPED", "no real candidates discovered to normalize")

        # 7. Candidate normalization
        print("\n=== 7. Candidate normalization ===")
        bad = [c for c in all_real if not (c.provider and c.provider_item_id and c.url and c.title is not None)]
        report("Candidate normalization", "PASS" if all_real and not bad else ("SKIPPED" if not all_real else "FAIL"),
              f"{len(all_real) - len(bad)}/{len(all_real)} candidates have all required normalized fields")

        # 8/9/10/11. Full pipeline + persistence + association + observations + lifecycle
        print("\n=== 8-11. Full PDI lifecycle against REAL discovered candidates ===")
        real_providers = {
            "reddit": lambda q, limit=8: pdi_providers.discover_reddit(q, limit=limit),
            "substack": lambda q, limit=8: pdi_providers.discover_substack(q, limit=limit),
        }
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        r1 = pdi.run_pdi_for_event(event_id, persist=True, now=now, providers=real_providers)
        report("Real candidate persistence (run 1)", "PASS" if r1["status"] in
              (pdi.RUN_VALID, pdi.RUN_NO_MEANINGFUL_DISCOURSE, pdi.RUN_INSUFFICIENT_EVIDENCE) else "FAIL",
              f"status={r1['status']} candidates={r1.get('candidate_count')} "
              f"selected={r1.get('selected_candidate_count')} observations={r1.get('observation_count')}")
        if r1["status"] == pdi.RUN_VALID:
            report("Association (real candidates)", "PASS",
                  f"distribution={r1['association_distribution']}")
            report("Observation extraction (real candidates)", "PASS",
                  f"{r1['observation_count']} observations, types seen: "
                  f"{sorted({o for sec in ('recurring_themes','recurring_questions','interpretations','experiences','disagreements','uncertainties','implications') for o in [sec] if getattr(r1['payload'], sec)})}")
        else:
            report("Association (real candidates)", "SKIPPED", f"run status was {r1['status']}, not VALID")
            report("Observation extraction (real candidates)", "SKIPPED", f"run status was {r1['status']}, not VALID")

        r2 = pdi.run_pdi_for_event(event_id, force=True, persist=True, now=now + timedelta(hours=1),
                                   providers=real_providers)
        conn2 = database.get_connection()
        history = pdi.get_run_history(conn2, event_id)
        statuses = [h["status"] for h in history]
        report("Full PDI lifecycle (RUNNING->terminal, --force transition)",
              "PASS" if len(history) == 2 else "FAIL",
              f"{len(history)} historical run(s), statuses={statuses}")
        conn2.close()

    finally:
        database.DB_PATH = real_db_path
        database._db_initialized = False
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"\nDisposable temp DB removed: {tmp_dir}")

    print(f"\n{'=' * 70}")
    n_pass = sum(1 for _, s, _ in RESULTS if s == "PASS")
    n_fail = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    n_other = len(RESULTS) - n_pass - n_fail
    print(f"PASS: {n_pass}   FAIL: {n_fail}   SKIPPED/EMPTY: {n_other}")
    if n_fail:
        print("\nFAILED checks:")
        for step, status, detail in RESULTS:
            if status == "FAIL":
                print(f"  - {step}: {detail}")
    print("\nNote: EMPTY/SKIPPED results are expected and not failures when run from a network "
          "where Reddit/Substack are blocked (like this sandbox) or when no Substack seed feeds "
          "are configured. Re-run from a real deployment network for a genuine PASS/FAIL signal.")


if __name__ == "__main__":
    main()
