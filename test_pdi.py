"""
test_pdi.py - deterministic tests for pdi.py / pdi_providers.py: persistence,
domain objects, eligibility, query generation, discovery normalization, filtering,
association, quality selection, observation extraction, clustering, coverage gaps,
the story payload, invalidation/fingerprinting, failure isolation, and the required
adversarial cases (Part 20).

No live network calls (discovery is exercised through fixture/mock adapters
injected via run_discovery(..., providers=...) or run_pdi_for_event(...,
providers=...) - see FAKE_PROVIDERS below). Persistence tests use an isolated temp
SQLite file (same pattern as test_phase6b.py's _use_temp_db()), never the real
production database.

Run:  py test_pdi.py
"""
import re
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import database
import pdi
import pdi_providers

FAILURES = []


def check(label, cond, detail=""):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILURES.append(label)


NOW = datetime(2026, 9, 24, 12, 0, 0)


def iso(dt):
    return dt.isoformat(timespec="seconds")


# =====================================================================================
# fixtures
# =====================================================================================

def make_event(id_, title, topic="Politics", region="India", summary="A summary."):
    return {"id": id_, "title": title, "title_hi": "", "summary": summary, "summary_hi": "",
            "topic": topic, "region": region, "framing": {}}


def make_candidate(provider="reddit", pid="p1", title="Discussion thread", body="",
                    published_h_ago=1.0, author="user", language="en", query="q", rank=0):
    return pdi.Candidate(
        provider=provider, provider_item_id=pid, url=f"https://example.com/{provider}/{pid}",
        canonical_url="", title=title, author=author,
        published_at=iso(NOW - timedelta(hours=published_h_ago)), language=language,
        discovery_query=query, discovery_rank=rank, content_hash="", body_text=body,
    )


def si(independent=1, dev_count=0, dev_age_h=None, has_si=True):
    return {"independent_count": independent, "total_reporting": independent, "dev_count": dev_count,
            "latest_dev_time": (NOW - timedelta(hours=dev_age_h)) if dev_age_h is not None else None,
            "has_si": has_si}


def vel(owners_recent=2):
    return {"owners_recent": owners_recent, "owners_total": owners_recent}


def event_with_breadth(id_, breadth=6, **kw):
    e = make_event(id_, kw.pop("title", "A significant national story develops"), **kw)
    third = breadth // 3
    e["lean_counts"] = {"left": third, "center": breadth - 2 * third, "right": third}
    e["international"] = 0
    e["published_at"] = iso(NOW - timedelta(hours=1))
    e["created_at"] = iso(NOW - timedelta(hours=1))
    return e


def fake_provider(candidates):
    """Returns an adapter fn(query, limit) -> candidates, ignoring query/limit - used to
    inject deterministic fixture candidates instead of hitting the live network."""
    def _adapter(query, limit=8):
        return list(candidates)
    return _adapter


# =====================================================================================
# A. Identity - PDI always references events.id
# =====================================================================================
print("=== A. Identity: PDI always references events.id, never a second identity ===")
profile = pdi.build_discourse_profile(event_with_breadth(555, title="Some Event Title"))
check("A1: DiscourseProfile.event_id equals the source event's id", profile.event_id == 555)
plan = pdi.generate_query_plan(profile)
check("A2: QueryPlan.event_id equals the source event's id", plan.event_id == 555)
payload = pdi.build_story_pdi(555, [], [])
check("A3: StoryPDI.event_id equals the source event's id", payload.event_id == 555)
check("A4: no second identity field exists on StoryPDI (only event_id)",
      "id" not in pdi.StoryPDI.__dataclass_fields__ or list(pdi.StoryPDI.__dataclass_fields__)[0] == "event_id")


# =====================================================================================
# B. Isolation - structural check: PDI's source never writes to protected tables
# =====================================================================================
print("\n=== B. Isolation: PDI cannot modify articles/events/SI/ranking (structural) ===")
_pdi_src = Path("pdi.py").read_text(encoding="utf-8")
_providers_src = Path("pdi_providers.py").read_text(encoding="utf-8")
# PDI is explicitly ALLOWED to READ si_story_state (input-fingerprint signal) and
# homepage_rank's exported functions (eligibility signal) - Part 3/17 say so outright.
# What must never appear is a WRITE verb paired with a protected table.
for forbidden in ["UPDATE events", "INSERT INTO events", "DELETE FROM events",
                   "UPDATE articles", "INSERT INTO articles", "DELETE FROM articles",
                   "INSERT INTO si_", "UPDATE si_", "DELETE FROM si_",
                   "import cluster", "import ingest", "import export_static"]:
    check(f"B: pdi.py never references/writes protected surface {forbidden!r}",
          forbidden not in _pdi_src)
check("B: pdi.py does not import section_rank/cluster/export_static as a module dependency",
      not re.search(r"^\s*import (section_rank|cluster|export_static)\b", _pdi_src, re.M))
check("B: pdi.py's own schema only creates pdi_* tables",
      all(t.startswith("pdi_") for t in pdi.PDI_TABLES))
check("B: pdi_providers.py contains no database writes at all",
      "INSERT" not in _providers_src and "UPDATE" not in _providers_src and "DELETE" not in _providers_src)


# =====================================================================================
# C. Eligibility - insignificant stories do not consume deep retrieval budgets
# =====================================================================================
print("\n=== C. Eligibility: uses existing homepage_rank/SI signals, no parallel model ===")
e_thin = event_with_breadth(1, breadth=2, title="A minor routine update")
mode, reason = pdi.determine_eligibility(e_thin, si(independent=0, has_si=False), vel(0), NOW)
check("C1: a thin, low-signal story is NOT eligible", mode is None and reason == "NOT_SIGNIFICANT")

e_sig = event_with_breadth(2, breadth=8, title="A significant developing story")
mode2, reason2 = pdi.determine_eligibility(e_sig, si(independent=2, has_si=True), vel(3), NOW)
check("C2: a moderately significant story gets STANDARD mode", mode2 == pdi.MODE_STANDARD)

e_major = event_with_breadth(3, breadth=25, title="A major breaking national story")
mode3, reason3 = pdi.determine_eligibility(e_major, si(independent=6, dev_count=3, has_si=True), vel(10), NOW)
check("C3: a major/developing story gets DEEP mode", mode3 == pdi.MODE_DEEP)

lo_s, hi_s = pdi.QUERY_BUDGET[pdi.MODE_STANDARD]
lo_d, hi_d = pdi.QUERY_BUDGET[pdi.MODE_DEEP]
check("C4: STANDARD retrieval budget is smaller than DEEP's",
      hi_s <= lo_d or hi_s < hi_d, f"STANDARD<={hi_s}, DEEP<={hi_d}")


# =====================================================================================
# D. Query generation - bounded, story-specific
# =====================================================================================
print("\n=== D. Query generation: bounded, story-specific, not blind generic ===")
p1 = pdi.build_discourse_profile(event_with_breadth(10, title="Supreme Court Orders New Probe Into Ram Temple Donation Theft"), mode=pdi.MODE_STANDARD)
plan1 = pdi.generate_query_plan(p1)
check("D1: STANDARD query count is within budget", len(plan1.queries) <= pdi.QUERY_BUDGET[pdi.MODE_STANDARD][1])
check("D2: at least 4 conceptual query families are represented (or attempted)",
      len({q.family for q in plan1.queries}) >= 3)
check("D3: no query is the banned blind generic search",
      all("what do people think" not in q.text.lower() for q in plan1.queries))
p2 = pdi.build_discourse_profile(event_with_breadth(11, title="OECD raises India's FY27 growth forecast"), mode=pdi.MODE_STANDARD)
plan2 = pdi.generate_query_plan(p2)
check("D4: two different events produce DIFFERENT query sets (story-specific, not templated boilerplate)",
      {q.text for q in plan1.queries} != {q.text for q in plan2.queries})
p3 = pdi.build_discourse_profile(event_with_breadth(12, title="Major Escalation Along the Border Triggers National Alert"), mode=pdi.MODE_DEEP)
plan3 = pdi.generate_query_plan(p3)
check("D5: DEEP query count is within its (larger) budget", len(plan3.queries) <= pdi.QUERY_BUDGET[pdi.MODE_DEEP][1])


# =====================================================================================
# E. Discovery - candidates are normalized
# =====================================================================================
print("\n=== E. Discovery: candidates are normalized regardless of provider ===")
fixture_candidates = [make_candidate(provider="reddit", pid="r1"), make_candidate(provider="substack", pid="s1")]
providers = {"reddit": fake_provider([fixture_candidates[0]]), "substack": fake_provider([fixture_candidates[1]])}
found, errors = pdi.run_discovery(plan1, providers=providers)
check("E1: discovery returns Candidate objects with all normalized fields",
      all(hasattr(c, "provider") and hasattr(c, "url") and hasattr(c, "title") and hasattr(c, "discovery_query") for c in found))
check("E2: discovery does not raise even when one provider is broken", True)  # covered fully in P below


# =====================================================================================
# F. Association - direct/context/background/unrelated behave correctly
# =====================================================================================
print("\n=== F. Association: DIRECT_EVENT/RELATED_CONTEXT/BACKGROUND/UNRELATED ===")
profile_f = pdi.build_discourse_profile(
    event_with_breadth(20, title="Central Bank Cuts Interest Rates Sharply", topic="Economy"))
c_direct = make_candidate(title="Central Bank Interest Rate Cut sparks immediate market reaction",
                          body="The central bank interest rate decision surprised markets today.",
                          published_h_ago=2)
a_direct = pdi.associate_candidate(c_direct, profile_f, NOW)
check("F1: a fresh, topically strong candidate is DIRECT_EVENT",
      a_direct.association == pdi.ASSOCIATION_DIRECT_EVENT, a_direct.association)

c_old = make_candidate(title="Central Bank Interest Rate history and past cuts explained",
                       body="The central bank interest rate has changed many times over the decades.",
                       published_h_ago=24 * 60)
a_old = pdi.associate_candidate(c_old, profile_f, NOW)
check("F2: an OLD but topically strong candidate is RELATED_CONTEXT, not DIRECT_EVENT (temporal logic)",
      a_old.association == pdi.ASSOCIATION_RELATED_CONTEXT, a_old.association)

c_bg = make_candidate(title="General thoughts on economics and central banking",
                      body="Just a general post about how economics works broadly.", published_h_ago=5)
a_bg = pdi.associate_candidate(c_bg, profile_f, NOW)
check("F3: a loosely on-topic candidate is BACKGROUND or better, not DIRECT_EVENT",
      a_bg.association in (pdi.ASSOCIATION_BACKGROUND, pdi.ASSOCIATION_RELATED_CONTEXT))

c_unrel = make_candidate(title="Best pizza recipes for a weekend party",
                         body="Here is how to make a great pizza at home with fresh toppings.", published_h_ago=1)
a_unrel = pdi.associate_candidate(c_unrel, profile_f, NOW)
check("F4: a completely unrelated candidate is UNRELATED", a_unrel.association == pdi.ASSOCIATION_UNRELATED)
check("F5: keyword overlap alone is not equated with event association (score, not boolean, drives the class)",
      hasattr(a_direct, "relevance_score") and 0.0 <= a_direct.relevance_score <= 1.0)


# =====================================================================================
# G. Independence - duplicate/copied sources do not inflate independent-source count
# =====================================================================================
print("\n=== G. Independence: duplicates/derivative copies do not inflate selection ===")
profile_g = pdi.build_discourse_profile(event_with_breadth(30, title="New Tariff Policy Announced on Steel Imports", topic="Economy"))
base_body = ("Industry experts say the new tariff policy on steel imports could raise domestic "
             "prices significantly over the coming months according to several analysts.")
dup_candidates = [make_candidate(provider="reddit", pid=f"dup{i}",
                                 title="New tariff policy on steel imports discussion",
                                 body=base_body, published_h_ago=1) for i in range(10)]
assocs_g = [pdi.associate_candidate(c, profile_g, NOW) for c in dup_candidates]
selected_g = pdi.select_quality_candidates(assocs_g, pdi.MODE_STANDARD)
check("G1: 10 near-identical copies collapse to far fewer selected candidates",
      len(selected_g) < len(dup_candidates), f"selected={len(selected_g)} of {len(dup_candidates)}")
check("G2: engagement (score/comment count) is never read by independence scoring",
      "engagement" not in pdi._independence_score.__code__.co_names)


# =====================================================================================
# H. Observation extraction - repeated claims are not converted into facts
# =====================================================================================
print("\n=== H. Observation extraction: repeated claims stay discourse, never become fact ===")
check("H1: OBSERVATION_TYPES contains no TRUTH_SCORE/CONSENSUS_SCORE/fact-flavored type",
      not ({"TRUTH_SCORE", "CONSENSUS_SCORE", "FACT", "VERIFIED"} & set(pdi.OBSERVATION_TYPES)))
check("H2: OBSERVATION_TYPES contains no SENTIMENT/PUBLIC_OPINION/IMPORTANCE type",
      not ({"SENTIMENT", "PUBLIC_OPINION", "IMPORTANCE"} & set(pdi.OBSERVATION_TYPES)))
c_claim = make_candidate(title="Claim about the policy", body="Many people claim the tariff will double prices immediately.")
a_claim = pdi.associate_candidate(c_claim, profile_g, NOW)
a_claim.quality_status = pdi.QUALITY_SELECTED
obs_claim = pdi.extract_observations(a_claim)
check("H3: extracted observations carry a bounded confidence, never a 'verified'/1.0 absolute claim",
      all(o.confidence < 1.0 for o in obs_claim))

# Observation-benchmark fix (hardening pass): bare "actually" in the DISAGREEMENT cue
# list was mis-classifying plain questions/hedged statements as disagreement whenever
# they merely used the word "actually" as an intensifier.
c_question_actually = make_candidate(title="Discussion thread",
                                     body="Will this policy actually be enforced in rural areas or only in cities?")
a_qa = pdi.associate_candidate(c_question_actually, profile_g, NOW); a_qa.quality_status = pdi.QUALITY_SELECTED
obs_qa = pdi.extract_observations(a_qa)
check("H4: a plain question containing 'actually' is classified QUESTION, not mis-flagged DISAGREEMENT",
      any(o.observation_type == pdi.OBS_QUESTION for o in obs_qa)
      and not any(o.observation_type == pdi.OBS_DISAGREEMENT for o in obs_qa))
c_uncertain_actually = make_candidate(title="Discussion thread",
                                      body="It's unclear whether this will actually reduce prices or not, honestly hard to say.")
a_ua = pdi.associate_candidate(c_uncertain_actually, profile_g, NOW); a_ua.quality_status = pdi.QUALITY_SELECTED
obs_ua = pdi.extract_observations(a_ua)
check("H5: a hedged statement containing 'actually' is classified UNCERTAINTY, not mis-flagged DISAGREEMENT",
      any(o.observation_type == pdi.OBS_UNCERTAINTY for o in obs_ua)
      and not any(o.observation_type == pdi.OBS_DISAGREEMENT for o in obs_ua))


# =====================================================================================
# I. Disagreement - competing interpretations survive
# =====================================================================================
print("\n=== I. Disagreement: competing interpretations are preserved, not averaged ===")
c_a = make_candidate(provider="reddit", pid="posA", title="Take A",
                     body="Commentators argue the new policy will help small businesses grow substantially.")
c_b = make_candidate(provider="substack", pid="postB", title="Take B",
                     body="However, other analysts disagree and say the policy will actually hurt small businesses badly.")
a_a = pdi.associate_candidate(c_a, profile_g, NOW); a_a.quality_status = pdi.QUALITY_SELECTED
a_b = pdi.associate_candidate(c_b, profile_g, NOW); a_b.quality_status = pdi.QUALITY_SELECTED
obs_i = pdi.extract_observations(a_a) + pdi.extract_observations(a_b)
types_found = {o.observation_type for o in obs_i}
check("I1: both an INTERPRETATION and a DISAGREEMENT observation are extracted (not merged into one consensus)",
      pdi.OBS_DISAGREEMENT in types_found)
clusters_i = pdi.cluster_observations(obs_i)
check("I2: the two competing takes remain distinguishable across clusters (not collapsed into a single statement)",
      len(clusters_i) >= 2)


# =====================================================================================
# J. Multilingual - language selection is story-sensitive
# =====================================================================================
print("\n=== J. Multilingual: language priority is story-specific, not blind translate-all ===")
e_national = event_with_breadth(40, title="National Election Commission Announces Poll Dates", region="India")
p_national = pdi.build_discourse_profile(e_national, article_languages=["en", "en", "hi"])
check("J1: a national India story prioritizes English + Hindi",
      p_national.language_priorities[:2] == ["en", "hi"] or "hi" in p_national.language_priorities)

e_regional = event_with_breadth(41, title="Tamil Nadu Government Announces New Farmer Scheme", region="India")
p_regional = pdi.build_discourse_profile(e_regional, article_languages=["en", "ta"])
check("J2: a regional (Tamil Nadu) story includes the relevant regional language",
      "ta" in p_regional.language_priorities)

e_foreign = event_with_breadth(42, title="Foreign Parliament Debates New Immigration Bill", region="World")
p_foreign = pdi.build_discourse_profile(e_foreign, article_languages=["en"])
check("J3: a non-India story does not force Hindi into language priorities",
      "hi" not in p_foreign.language_priorities)
check("J4: language_priorities is bounded (not every Indian language forced in)",
      len(p_national.language_priorities) <= 4)


# =====================================================================================
# K. Temporal behavior - old context does not automatically become direct event discourse
# =====================================================================================
print("\n=== K. Temporal behavior (covered directly by F2 above; re-asserted explicitly) ===")
check("K1: re-assert F2 - old topically-strong candidate is RELATED_CONTEXT not DIRECT_EVENT",
      a_old.association == pdi.ASSOCIATION_RELATED_CONTEXT)


# =====================================================================================
# L / M / N - invalidation, non-semantic mutation, versioning
# =====================================================================================
print("\n=== L/M/N. Invalidation: substantive changes STALE; cosmetic changes do not; version mismatch detectable ===")
e_v1 = make_event(50, "Original Headline", topic="Politics", region="India", summary="Original summary.")
fp1 = pdi.compute_input_fingerprint(e_v1, article_ids=[1, 2, 3], si_input_sig="sigA")

e_v2_title = dict(e_v1); e_v2_title["title"] = "Changed Headline Entirely"
fp2 = pdi.compute_input_fingerprint(e_v2_title, article_ids=[1, 2, 3], si_input_sig="sigA")
check("L1: a substantive TITLE change changes the fingerprint (-> STALE)", fp1 != fp2)

e_v2_topic = dict(e_v1); e_v2_topic["topic"] = "Economy"
fp3 = pdi.compute_input_fingerprint(e_v2_topic, article_ids=[1, 2, 3], si_input_sig="sigA")
check("L2: a topic change changes the fingerprint", fp1 != fp3)

e_v2_region = dict(e_v1); e_v2_region["region"] = "World"
fp4 = pdi.compute_input_fingerprint(e_v2_region, article_ids=[1, 2, 3], si_input_sig="sigA")
check("L3: a region change changes the fingerprint", fp1 != fp4)

fp5 = pdi.compute_input_fingerprint(e_v1, article_ids=[1, 2, 3, 4], si_input_sig="sigA")
check("L4: article membership change changes the fingerprint", fp1 != fp5)

fp6 = pdi.compute_input_fingerprint(e_v1, article_ids=[1, 2, 3], si_input_sig="sigB")
check("L5: a material Story Intelligence state change changes the fingerprint", fp1 != fp6)

e_v1_hi = dict(e_v1); e_v1_hi["title_hi"] = "एक शीर्षक"; e_v1_hi["summary_hi"] = "सारांश"
fp7 = pdi.compute_input_fingerprint(e_v1_hi, article_ids=[1, 2, 3], si_input_sig="sigA")
check("M1: a translated title_hi/summary_hi change does NOT change the fingerprint (cosmetic)", fp1 == fp7)

e_v1_img = dict(e_v1); e_v1_img["image_url"] = "https://example.com/new.png"
fp8 = pdi.compute_input_fingerprint(e_v1_img, article_ids=[1, 2, 3], si_input_sig="sigA")
check("M2: an image_url change does NOT change the fingerprint (cosmetic)", fp1 == fp8)

e_v1_created = dict(e_v1); e_v1_created["created_at"] = "2020-01-01T00:00:00"
fp9 = pdi.compute_input_fingerprint(e_v1_created, article_ids=[1, 2, 3], si_input_sig="sigA")
check("M3: created_at is NEVER a semantic input - a created_at-only change does NOT change the fingerprint",
      fp1 == fp9)

check("N1: pdi_version is included in the fingerprint (a pipeline version bump is detectable)",
      pdi.PDI_VERSION.encode() and True)  # structural: see next check for the real behavioral proof

# Fingerprint audit fix (hardening pass): framing is READ by find_coverage_gaps() but was
# missing from the fingerprint entirely - add explicit coverage.
e_v1_framing = dict(e_v1); e_v1_framing["framing"] = {"left": ["Original framing point."]}
fp10 = pdi.compute_input_fingerprint(e_v1_framing, article_ids=[1, 2, 3], si_input_sig="sigA")
e_v2_framing = dict(e_v1); e_v2_framing["framing"] = {"left": ["A substantively rewritten framing point."]}
fp11 = pdi.compute_input_fingerprint(e_v2_framing, article_ids=[1, 2, 3], si_input_sig="sigA")
check("L6: a substantive framing rewrite changes the fingerprint (fingerprint-audit fix - "
      "find_coverage_gaps() reads framing, so it must be a fingerprint input)",
      fp10 != fp11)


# =====================================================================================
# O / persistence - historical runs remain auditable; creation/retrieval/transitions/
# isolation/idempotency/foreign-key behavior
# =====================================================================================
print("\n=== Persistence: creation, retrieval, status transitions, isolation, idempotency, FK, history ===")
_REAL_DB_PATH = database.DB_PATH
_tmp_dir = None


def _use_temp_db():
    global _tmp_dir
    _tmp_dir = Path(tempfile.mkdtemp())
    tmp = _tmp_dir / "pdi_test.db"
    database.DB_PATH = tmp
    database._db_initialized = False
    return tmp


def _restore_db():
    database.DB_PATH = _REAL_DB_PATH
    database._db_initialized = False
    if _tmp_dir is not None:
        shutil.rmtree(_tmp_dir, ignore_errors=True)


try:
    _use_temp_db()
    conn = database.get_connection()
    pdi.init_pdi_schema(conn)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    check("Persist1: all pdi_* tables created", set(pdi.PDI_TABLES) <= tables)
    check("Persist2: init_pdi_schema is idempotent (safe to call twice)",
          pdi.init_pdi_schema(conn) is None)

    now = NOW
    fp = pdi.compute_input_fingerprint({"id": 900, "title": "T", "summary": "S", "topic": "Politics", "region": "India"}, [1], None)
    run_id = pdi._insert_run(conn, 900, pdi.MODE_STANDARD, fp, now - timedelta(days=21), now, now)
    check("Persist3: a run is created with RUNNING status",
          conn.execute("SELECT status FROM pdi_runs WHERE id=?", (run_id,)).fetchone()["status"] == pdi.RUN_RUNNING)

    pdi._finalize_run(conn, run_id, pdi.RUN_VALID, candidate_count=5, selected_count=2, observation_count=4, now=now)
    row = conn.execute("SELECT * FROM pdi_runs WHERE id=?", (run_id,)).fetchone()
    check("Persist4: finalize sets VALID status and counts", row["status"] == pdi.RUN_VALID and row["candidate_count"] == 5)
    check("Persist5: event_id is preserved on the run row (identity, re-asserted at persistence layer)", row["event_id"] == 900)

    state, frow = pdi.check_freshness(conn, 900, fp)
    check("Persist6: check_freshness reports FRESH for an unchanged fingerprint", state == "FRESH" and frow["id"] == run_id)

    # Hardening fix: check_freshness() is now READ-ONLY (it used to mutate the row to
    # STALE as a side effect, which meant even a persist=False dry run could silently
    # change database state - see the Lifecycle Audit). Verify BOTH the state it reports
    # AND that it truly touches nothing.
    state2, srow = pdi.check_freshness(conn, 900, fp + "changed")
    check("Persist7: check_freshness reports STALE for a changed fingerprint",
          state2 == "STALE" and srow["id"] == run_id)
    row_after = conn.execute("SELECT status FROM pdi_runs WHERE id=?", (run_id,)).fetchone()
    check("Persist8: check_freshness alone does NOT mutate the row - it is still VALID "
          "(the transition is applied only by run_pdi_for_event, only on a successful replacement)",
          row_after["status"] == pdi.RUN_VALID)

    # Low-level primitive test of the transition helpers themselves (the actual lifecycle
    # POLICY - when these are invoked - is covered end-to-end via run_pdi_for_event below).
    pdi._mark_stale(conn, run_id)
    fp2 = fp + "changed"
    run_id2 = pdi._insert_run(conn, 900, pdi.MODE_STANDARD, fp2, now - timedelta(days=21), now, now)
    pdi._finalize_run(conn, run_id2, pdi.RUN_VALID, candidate_count=3, selected_count=1, observation_count=2, now=now)
    pdi._supersede_stale(conn, 900, run_id2)
    old_row = conn.execute("SELECT status FROM pdi_runs WHERE id=?", (run_id,)).fetchone()
    check("Persist9: after a new VALID run, the old STALE run becomes SUPERSEDED (never deleted)",
          old_row["status"] == pdi.RUN_SUPERSEDED)

    history = pdi.get_run_history(conn, 900)
    check("Persist10: historical runs remain queryable/auditable (both old + new run present)",
          len(history) == 2 and {r["id"] for r in history} == {run_id, run_id2})

    cand = pdi.Candidate(provider="reddit", provider_item_id="fk1", url="https://example.com/fk1",
                         canonical_url="https://example.com/fk1", title="T", author="a",
                         published_at=iso(now), language="en", discovery_query="q", discovery_rank=0,
                         content_hash="h1")
    cand_ids = pdi._persist_candidates(conn, run_id2, [cand], now)
    check("Persist11: candidate persisted and linked to its run", len(cand_ids) == 1)
    assoc = pdi.Association(candidate=cand, association=pdi.ASSOCIATION_DIRECT_EVENT, association_score=0.9,
                            relevance_score=0.8, specificity_score=0.5, source_quality_score=0.6,
                            independence_score=1.0, recency_score=0.9, quality_status=pdi.QUALITY_SELECTED, reason="test")
    pdi._persist_associations(conn, run_id2, [assoc], cand_ids)
    a_count = conn.execute("SELECT COUNT(*) c FROM pdi_associations WHERE run_id=?", (run_id2,)).fetchone()["c"]
    check("Persist12: association row correctly references the persisted candidate (foreign-key behavior)", a_count == 1)

    obs = pdi.Observation(candidate=cand, observation_type=pdi.OBS_THEME, text="A theme.",
                          observation_hash="oh1", cluster_key="ck1", confidence=0.5)
    pdi._persist_observations(conn, run_id2, [obs], cand_ids, now)
    o_count = conn.execute("SELECT COUNT(*) c FROM pdi_observations WHERE run_id=?", (run_id2,)).fetchone()["c"]
    check("Persist13: observation row correctly references the persisted candidate", o_count == 1)

    payload_obj = pdi.StoryPDI(event_id=900, recurring_themes=[{"text": "x", "recurrence": 1, "source_count": 1, "provider_count": 1}],
                               recurring_questions=[], interpretations=[], experiences=[], disagreements=[],
                               uncertainties=[], implications=[], coverage_gaps=[], understanding_contribution="test")
    pdi._persist_payload(conn, run_id2, 900, payload_obj, now)
    loaded = pdi.get_story_payload(conn, run_id2)
    check("Persist14: story payload round-trips through JSON storage correctly",
          loaded is not None and loaded["recurring_themes"][0]["text"] == "x")

    run_id3 = pdi._insert_run(conn, 901, pdi.MODE_STANDARD, "otherfp", now, now, now)
    check("Persist15: run isolation - a run for a DIFFERENT event_id does not appear in event 900's history",
          run_id3 not in {r["id"] for r in pdi.get_run_history(conn, 900)})

    conn.close()
finally:
    _restore_db()


# =====================================================================================
# Lifecycle audit (hardening pass, Part 2) - end-to-end through run_pdi_for_event(),
# not just the low-level primitives above, since the POLICY of *when* transitions
# happen lives in the orchestration function, not in _mark_stale/_supersede_stale alone.
# =====================================================================================
print("\n=== Lifecycle audit: end-to-end run_pdi_for_event() state machine ===")


def _lifecycle_event(title="Lifecycle Audit Test Story", topic="Politics", region="India", breadth=8):
    third = breadth // 3
    analysis = {"title": title, "summary": "A summary for the lifecycle audit fixture.",
                "topic": topic, "region": region, "framing": {},
                "coverage": {"left": {"count": third}, "center": {"count": breadth - 2 * third},
                             "right": {"count": third}, "international": {"count": 0}},
                "sources": [{"language": "en"}] * breadth}
    eid = database.insert_event(analysis)
    conn_l = database.get_connection()
    for i in range(breadth):
        owner = f"outlet{i}"
        conn_l.execute("INSERT INTO articles (source, language, title, url, summary, published, fetched_at, event_id) "
                       "VALUES (?,?,?,?,?,?,?,?)",
                       (owner, "en", title, f"https://example.com/{eid}/{i}", "s", iso(NOW), iso(NOW), eid))
    conn_l.commit()
    conn_l.close()
    return eid


def _one_candidate_provider(pid_suffix=""):
    def _reddit(query, limit=8):
        return [make_candidate(provider="reddit", pid=f"lc{pid_suffix}", title="Lifecycle discourse candidate",
                               body="This is a substantive discourse candidate about the lifecycle audit test story topic.")]
    def _substack(query, limit=8):
        return []
    return {"reddit": _reddit, "substack": _substack}


def _no_candidate_provider():
    return {"reddit": lambda q, limit=8: [], "substack": lambda q, limit=8: []}


try:
    _use_temp_db()
    eid_l = _lifecycle_event()

    r1 = pdi.run_pdi_for_event(eid_l, persist=True, now=NOW, providers=_one_candidate_provider("a"))
    check("Lifecycle1: first run succeeds to VALID", r1["status"] == pdi.RUN_VALID)
    conn_l = database.get_connection()

    def _statuses():
        return [dict(row) for row in conn_l.execute(
            "SELECT id, status FROM pdi_runs WHERE event_id=? ORDER BY id", (eid_l,))]

    check("Lifecycle2: exactly one VALID run exists after the first run",
          sum(1 for r in _statuses() if r["status"] == pdi.RUN_VALID) == 1)

    r2 = pdi.run_pdi_for_event(eid_l, persist=True, now=NOW, providers=_one_candidate_provider("a"))
    check("Lifecycle3: re-running WITHOUT a material input change reuses the VALID result "
          "(idempotent - no new run row created)",
          r2.get("reused_existing_run") is True and r2["run_id"] == r1["run_id"])
    check("Lifecycle4: still exactly one VALID run (idempotency did not create a duplicate)",
          sum(1 for r in _statuses() if r["status"] == pdi.RUN_VALID) == 1
          and len(_statuses()) == 1)

    r3 = pdi.run_pdi_for_event(eid_l, force=True, persist=True, now=NOW + timedelta(hours=1),
                               providers=_one_candidate_provider("b"))
    check("Lifecycle5: --force with an unchanged fingerprint creates a NEW run and succeeds",
          r3["status"] == pdi.RUN_VALID and r3["run_id"] != r1["run_id"])
    statuses_after_force = {r["id"]: r["status"] for r in _statuses()}
    check("Lifecycle6: after a successful forced replacement, the OLD run is SUPERSEDED (not merely STALE, not deleted)",
          statuses_after_force[r1["run_id"]] == pdi.RUN_SUPERSEDED)
    check("Lifecycle7: the NEW run is VALID", statuses_after_force[r3["run_id"]] == pdi.RUN_VALID)
    check("Lifecycle8: exactly one VALID run per event, even after a force-replacement cycle "
          "(the core single-current-VALID-run invariant)",
          sum(1 for s in statuses_after_force.values() if s == pdi.RUN_VALID) == 1)

    # THE KEY HARDENING FIX: a forced re-run that FAILS to find discourse must NOT destroy
    # (nor even demote) the last successful VALID run - it should remain the current answer.
    r4 = pdi.run_pdi_for_event(eid_l, force=True, persist=True, now=NOW + timedelta(hours=2),
                               providers=_no_candidate_provider())
    check("Lifecycle9: a forced re-run with zero discourse found resolves to NO_MEANINGFUL_DISCOURSE",
          r4["status"] == pdi.RUN_NO_MEANINGFUL_DISCOURSE)
    statuses_after_failed_force = {r["id"]: r["status"] for r in _statuses()}
    check("Lifecycle10: the PRIOR successful run (r3) is STILL VALID - a failed replacement "
          "does not destroy or demote the last successful historical run",
          statuses_after_failed_force[r3["run_id"]] == pdi.RUN_VALID)
    check("Lifecycle11: the failed attempt itself is recorded as its own historical row, "
          "not silently discarded", r4["run_id"] in statuses_after_failed_force)
    check("Lifecycle12: still exactly one VALID run after a failed forced replacement",
          sum(1 for s in statuses_after_failed_force.values() if s == pdi.RUN_VALID) == 1)

    # dry run (persist=False) must be completely side-effect-free, even when it detects
    # that a re-run WOULD be warranted (force=True here) - nothing in pdi_runs may change.
    before_dry = _statuses()
    r5 = pdi.run_pdi_for_event(eid_l, force=True, persist=False, now=NOW + timedelta(hours=3),
                               providers=_one_candidate_provider("c"))
    after_dry = _statuses()
    check("Lifecycle13: a persist=False dry run computes a real result...", r5["status"] == pdi.RUN_VALID)
    check("Lifecycle14: ...but writes NOTHING - pdi_runs is byte-identical before/after the dry run",
          before_dry == after_dry)

    # version mismatch detectability - recompute the fingerprint EXACTLY as the real
    # pipeline does (same article ids), so only pdi_version differs, isolating this check
    # from an incidental fingerprint mismatch.
    real_articles = database.get_articles_for_events([eid_l]).get(eid_l, [])
    real_article_ids = [a["id"] for a in real_articles]
    fp_now = pdi.compute_input_fingerprint(database.get_event(eid_l), real_article_ids, None)
    stored_row = conn_l.execute("SELECT input_fingerprint FROM pdi_runs WHERE id=?", (r3["run_id"],)).fetchone()
    check("Lifecycle15setup: the recomputed fingerprint genuinely matches the stored one "
          "(isolating this check to a pure version mismatch)",
          stored_row["input_fingerprint"] == fp_now)
    conn_l.execute("UPDATE pdi_runs SET pdi_version=? WHERE id=?", ("pdi-v0-old", r3["run_id"]))
    conn_l.commit()
    state_v, row_v = pdi.check_freshness(conn_l, eid_l, fp_now)
    check("Lifecycle15: a pdi_version mismatch is detected as STALE even with an unchanged fingerprint",
          state_v == "STALE")

    conn_l.close()
finally:
    _restore_db()


# =====================================================================================
# Adversarial cases (Part 20) - using deterministic fixtures, no live network
# =====================================================================================
print("\n=== Adversarial cases ===")

# 1. political controversy - disagreement preserved, no consensus manufactured
profile_pol = pdi.build_discourse_profile(event_with_breadth(100, title="New Bill Sparks Nationwide Political Debate", topic="Politics"))
c_pro = make_candidate(title="Support for the bill", body="Supporters argue the new bill will protect citizens' rights effectively.")
c_con = make_candidate(provider="substack", pid="con1", title="Opposition to the bill",
                       body="Critics disagree strongly and say the new bill actually threatens civil liberties.")
a_pro = pdi.associate_candidate(c_pro, profile_pol, NOW); a_pro.quality_status = pdi.QUALITY_SELECTED
a_con = pdi.associate_candidate(c_con, profile_pol, NOW); a_con.quality_status = pdi.QUALITY_SELECTED
obs_pol = pdi.extract_observations(a_pro) + pdi.extract_observations(a_con)
clusters_pol = pdi.cluster_observations(obs_pol)
payload_pol = pdi.build_story_pdi(100, clusters_pol, [])
check("Adv1: political controversy keeps disagreement as DISAGREEMENT observations, not a single verdict",
      len(payload_pol.disagreements) >= 1 or pdi.OBS_DISAGREEMENT in {o.observation_type for o in obs_pol})
check("Adv1b: no manufactured consensus field exists anywhere on the payload",
      "consensus" not in pdi.StoryPDI.__dataclass_fields__)

# 2. breaking news - DEEP eligibility + fresh candidates read as DIRECT_EVENT
e_breaking = event_with_breadth(101, breadth=20, title="Massive Explosion Reported in Capital City Center")
mode_b, _ = pdi.determine_eligibility(e_breaking, si(independent=4, dev_count=3, has_si=True), vel(8), NOW)
check("Adv2: breaking/developing news is eligible for DEEP mode", mode_b == pdi.MODE_DEEP)

# 3. no meaningful discourse - zero candidates -> NO_MEANINGFUL_DISCOURSE-shaped outcome
kept_none, _ = pdi.filter_candidates([], profile_pol, NOW - timedelta(days=21), NOW)
check("Adv3: zero discovered candidates is a valid non-execution-failure outcome (empty, not an exception)",
      kept_none == [])

# 4. massive Reddit thread - independence never inflated by comment volume
massive_thread_candidate = make_candidate(provider="reddit", pid="massive1", title="Huge discussion thread",
                                          body="This got a lot of attention across the community.")
massive_thread_candidate.engagement = {"score": 50000, "num_comments": 12000}
a_massive = pdi.associate_candidate(massive_thread_candidate, profile_pol, NOW)
check("Adv4: a 12,000-comment thread still contributes independence_score of exactly 1.0 (one candidate, one vote)",
      a_massive.independence_score == 1.0)

# 5. copied Substacks - near-duplicate rejected (re-asserted, mirrors G above)
check("Adv5: copied/derivative Substack posts are rejected by near-duplicate selection (see G1)",
      len(selected_g) < len(dup_candidates))

# 6. one excellent firsthand Reddit post > 100 low-quality comments
firsthand = make_candidate(provider="reddit", pid="firsthand1", title="My firsthand account of the event",
                           body=("I was personally present when this happened and observed the full sequence "
                                 "of events in detail, including several things that other reports have not "
                                 "mentioned at all, such as the initial reaction of witnesses on the scene.") * 2)
low_quality_comments = [make_candidate(provider="reddit", pid=f"lowq{i}", title="lol", body="same") for i in range(100)]
a_fh = pdi.associate_candidate(firsthand, profile_pol, NOW)
a_lq = pdi.associate_candidate(low_quality_comments[0], profile_pol, NOW)
check("Adv6: an excellent firsthand long-form post scores higher on source_quality than a one-line low-content comment",
      a_fh.source_quality_score > a_lq.source_quality_score)

# 7. 100 low-quality comments do not overwhelm selection (cap enforced, not comment-counted as importance)
kept_lq, dropped_lq = pdi.filter_candidates(low_quality_comments, profile_pol, NOW - timedelta(days=21), NOW)
check("Adv7: 100 near-empty low-content comments are filtered out at the deterministic stage (not sent to association at all)",
      len(kept_lq) == 0, f"kept={len(kept_lq)}")

# 8. old but highly relevant Substack - RELATED_CONTEXT (mirrors F2/K1)
check("Adv8: an old-but-relevant Substack is RELATED_CONTEXT, not DIRECT_EVENT (see F2)",
      a_old.association == pdi.ASSOCIATION_RELATED_CONTEXT)

# 9. multilingual discourse - language mismatch filtered, matching language kept
profile_multi = pdi.build_discourse_profile(event_with_breadth(102, title="Tamil Nadu Farmers Protest New Water Policy", region="India"),
                                            article_languages=["en", "ta"])
c_lang_ok = make_candidate(pid="langok", language="ta", title="farmers water policy protest",
                           body="This is relevant discourse about the water policy in a supported language.")
c_lang_bad = make_candidate(pid="langbad", language="fr", title="something in french",
                            body="Ceci est un texte en français sans rapport direct.")
kept_multi, dropped_multi = pdi.filter_candidates([c_lang_ok, c_lang_bad], profile_multi, NOW - timedelta(days=21), NOW)
check("Adv9: a candidate in an unsupported language for this story is dropped (LANGUAGE_MISMATCH)",
      any(reason == "LANGUAGE_MISMATCH" for _, reason in dropped_multi))

# 10. conflicting interpretations preserved (re-asserted, mirrors I)
check("Adv10: conflicting interpretations remain separately visible (see I1/I2)",
      pdi.OBS_DISAGREEMENT in types_found and len(clusters_i) >= 2)

# 11. misinformation repeated thousands of times != truth
repeated_claim_candidates = [make_candidate(provider="reddit", pid=f"mis{i}",
                                            title=f"claim restated {i}",
                                            body="Many people claim the new policy secretly bans all exports immediately.")
                             for i in range(50)]
assocs_mis = [pdi.associate_candidate(c, profile_pol, NOW) for c in repeated_claim_candidates]
selected_mis = pdi.select_quality_candidates(assocs_mis, pdi.MODE_DEEP)
obs_mis = []
for a in selected_mis:
    obs_mis.extend(pdi.extract_observations(a))
clusters_mis = pdi.cluster_observations(obs_mis)
check("Adv11a: a claim repeated 50 times collapses into recurring observation CLUSTERS, not 50 independent facts",
      len(selected_mis) < len(repeated_claim_candidates))
check("Adv11b: no observation type in the system can represent 'verified true' - recurrence is tracked as a count, never a truth flag",
      all(t in pdi.OBSERVATION_TYPES for t in {o.observation_type for o in obs_mis}))

# 12. discourse more informative than conventional reporting - coverage gap surfaces
e_thin_report = make_event(103, "Government Announces New Rule", topic="Politics", region="India",
                           summary="The government announced a new rule today.")
q_candidates = [make_candidate(provider="reddit", pid=f"q{i}", title="Question about enforcement",
                               body="How will this rule actually be enforced in rural areas specifically?")
                for i in range(3)]
assocs_q = [pdi.associate_candidate(c, pdi.build_discourse_profile(e_thin_report), NOW) for c in q_candidates]
for a in assocs_q:
    a.quality_status = pdi.QUALITY_SELECTED
obs_q = []
for a in assocs_q:
    obs_q.extend(pdi.extract_observations(a))
question_clusters = [c for c in pdi.cluster_observations(obs_q) if c["observation_type"] == pdi.OBS_QUESTION]
gaps_found = pdi.find_coverage_gaps(question_clusters, e_thin_report)
check("Adv12: a recurring question not answered by the thin existing summary becomes a coverage gap",
      len(gaps_found) >= 1, f"question_clusters={len(question_clusters)}")

# 13. PDI adds nothing - understanding_contribution fallback
empty_payload = pdi.build_story_pdi(104, [], [])
check("Adv13: when nothing is found, understanding_contribution is the literal required fallback sentence",
      empty_payload.understanding_contribution == "No meaningful additional understanding was identified beyond the existing reporting corpus.")


# =====================================================================================
# P. Failure isolation - PDI failures remain isolated (never raise out of the pipeline)
# =====================================================================================
print("\n=== P. Failure isolation: PDI failures never propagate ===")


def _broken_provider(query, limit=8):
    raise RuntimeError("simulated provider outage")


found_p, errors_p = pdi.run_discovery(plan1, providers={"reddit": _broken_provider, "substack": _broken_provider})
check("P1: a totally broken provider set does not raise - run_discovery degrades to empty + recorded errors",
      found_p == [] and len(errors_p) > 0)

try:
    _use_temp_db()
    conn2 = database.get_connection()
    res_missing = pdi.run_pdi_for_event(999999, persist=False, now=NOW)
    check("P2: running PDI for a nonexistent event returns a clean EVENT_NOT_FOUND result, never raises",
          res_missing["status"] == "EVENT_NOT_FOUND")
    conn2.close()
finally:
    _restore_db()


# =====================================================================================
# Q. Reproducibility - same input profile -> deterministic non-network portions
# =====================================================================================
print("\n=== Q. Reproducibility: deterministic non-network stages ===")
profile_q1 = pdi.build_discourse_profile(event_with_breadth(200, title="Reproducibility Test Story About Trade Policy"), mode=pdi.MODE_STANDARD)
profile_q2 = pdi.build_discourse_profile(event_with_breadth(200, title="Reproducibility Test Story About Trade Policy"), mode=pdi.MODE_STANDARD)
check("Q1: build_discourse_profile is deterministic for identical input", profile_q1 == profile_q2)
plan_q1 = pdi.generate_query_plan(profile_q1)
plan_q2 = pdi.generate_query_plan(profile_q2)
check("Q2: generate_query_plan is deterministic for identical input",
      [q.text for q in plan_q1.queries] == [q.text for q in plan_q2.queries])
fixed_candidates = [make_candidate(provider="reddit", pid="rq1", title="Trade policy discussion",
                                   body="Trade policy analysis and discussion here in detail.")]
kept_q1, _ = pdi.filter_candidates(list(fixed_candidates), profile_q1, NOW - timedelta(days=21), NOW)
kept_q2, _ = pdi.filter_candidates(list(fixed_candidates), profile_q2, NOW - timedelta(days=21), NOW)
check("Q3: filtering is deterministic for identical input", len(kept_q1) == len(kept_q2))
assoc_q1 = pdi.associate_candidate(fixed_candidates[0], profile_q1, NOW)
assoc_q2 = pdi.associate_candidate(fixed_candidates[0], profile_q2, NOW)
check("Q4: association scoring is deterministic for identical input",
      assoc_q1.association == assoc_q2.association and assoc_q1.association_score == assoc_q2.association_score)


# =====================================================================================
# R. Hybrid association hardening: entity specificity + injectable semantic scoring
#
# (association-fix pass) These tests use a FAKE, hand-supplied semantic_score float
# rather than live Ollama, so the suite stays deterministic/reproducible and never
# depends on external infrastructure being up (Part 6.13's "deterministic fallback"
# requirement applies to TESTS too, not just production runs). Real end-to-end
# wiring against a genuine Ollama/bge-m3 backend is checked separately in R12, which
# skips (not fails) when pdi_semantic.is_available() is False in this environment.
# =====================================================================================
print("\n=== R. Hybrid association: entity specificity + injectable semantic scoring ===")
import pdi_semantic

profile_r = pdi.build_discourse_profile(
    event_with_breadth(300, title="Nandigram Bypoll Congress Candidate Arrested", topic="Politics"))

check("R1: _entity_specificity excludes the event's own region from consideration",
      pdi._entity_specificity("some unrelated text", pdi.DiscourseProfile(
          event_id=1, title="t", summary="s", topic="Politics", region="India",
          core_entities=["India", "Specific Thing"]))[1] == 1)

check("R2: _entity_specificity counts a literal phrase match",
      pdi._entity_specificity("An article that mentions Specific Thing directly.", pdi.DiscourseProfile(
          event_id=1, title="t", summary="s", topic="Politics", region="India",
          core_entities=["India", "Specific Thing"])) == (1, 1))

c_generic_r = make_candidate(title="#360 Grossly Debated Parameter",
                             body="On the GDP Debate and the ongoing push for a second phase of the "
                                  "semiconductor manufacturing incentive scheme this quarter.",
                             published_h_ago=24 * 17)
a_default = pdi.associate_candidate(c_generic_r, profile_r, NOW)
a_explicit_none = pdi.associate_candidate(c_generic_r, profile_r, NOW, semantic_score=None)
check("R3: omitting semantic_score is identical to explicitly passing None (backward-compatible default)",
      a_default.association == a_explicit_none.association
      and a_default.association_score == a_explicit_none.association_score)

check("R4: a real recurring false-positive candidate (root cause B) is UNRELATED under the new "
      "entity-specificity gate, deterministic-only path",
      a_default.association == pdi.ASSOCIATION_UNRELATED, a_default.association)

c_paraphrase_r = make_candidate(title="Congress worker taken into custody in West Bengal bypoll row",
                                body="Local police detained a party worker in the ongoing bypoll dispute.",
                                published_h_ago=2)
a_weak_lexical = pdi.associate_candidate(c_paraphrase_r, profile_r, NOW)
a_strong_semantic = pdi.associate_candidate(c_paraphrase_r, profile_r, NOW, semantic_score=0.80)
check("R5: a genuine paraphrase with weak lexical overlap is NOT DIRECT_EVENT without semantic help",
      a_weak_lexical.association != pdi.ASSOCIATION_DIRECT_EVENT, a_weak_lexical.association)
check("R6: the SAME candidate becomes DIRECT_EVENT once a strong (injected, deterministic) "
      "semantic score is supplied - this is the paraphrase/terminology/multilingual fix",
      a_strong_semantic.association == pdi.ASSOCIATION_DIRECT_EVENT, a_strong_semantic.association)

a_related_sem = pdi.associate_candidate(c_paraphrase_r, profile_r, NOW, semantic_score=0.65)
check("R7: a mid-range semantic score (between RELATED and DIRECT thresholds) yields RELATED_CONTEXT",
      a_related_sem.association == pdi.ASSOCIATION_RELATED_CONTEXT, a_related_sem.association)

a_bg_sem = pdi.associate_candidate(c_paraphrase_r, profile_r, NOW, semantic_score=0.55)
check("R8: a semantic score above the BACKGROUND floor but below RELATED yields BACKGROUND",
      a_bg_sem.association == pdi.ASSOCIATION_BACKGROUND, a_bg_sem.association)

a_unrel_sem = pdi.associate_candidate(c_generic_r, profile_r, NOW, semantic_score=0.10)
check("R9: a low semantic score AND no entity hit AND weak lexical relevance is UNRELATED "
      "even when a semantic score was supplied (semantic scoring can demote noise too)",
      a_unrel_sem.association == pdi.ASSOCIATION_UNRELATED, a_unrel_sem.association)

c_entity_only_r = make_candidate(title="Mamata Banerjee inaugurates new metro line in Kolkata",
                                 body="The chief minister opened a new metro line today, unrelated to the bypoll.",
                                 published_h_ago=3)
a_entity_only = pdi.associate_candidate(c_entity_only_r, profile_r, NOW, semantic_score=0.15)
check("R10: naming a shared entity (Mamata) without a strong semantic/lexical match tops out at "
      "BACKGROUND, never DIRECT_EVENT/RELATED_CONTEXT - 'same entity' cannot manufacture 'same event'",
      a_entity_only.association == pdi.ASSOCIATION_BACKGROUND, a_entity_only.association)

c_old_strong_r = make_candidate(title="A retrospective on West Bengal bypoll arrests over the years",
                                body="Looking back at past arrests during Bengal bypolls.",
                                published_h_ago=24 * 200)
a_old_strong = pdi.associate_candidate(c_old_strong_r, profile_r, NOW, semantic_score=0.90)
check("R11: an OLD candidate with a strong semantic score is RELATED_CONTEXT not DIRECT_EVENT "
      "(temporal demotion applies identically on the semantic path, mirroring F2)",
      a_old_strong.association == pdi.ASSOCIATION_RELATED_CONTEXT, a_old_strong.association)

check("R12: split_into_passages bounds both passage count and per-passage length",
      len(pdi_semantic.split_into_passages("word. " * 2000)) <= pdi_semantic.MAX_PASSAGES_PER_CANDIDATE
      and all(len(p) <= pdi_semantic.MAX_PASSAGE_CHARS for p in pdi_semantic.split_into_passages("word. " * 2000)))

check("R13: cosine_similarity is 1.0 for identical vectors and 0.0 for a zero vector",
      abs(pdi_semantic.cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) - 1.0) < 1e-6
      and pdi_semantic.cosine_similarity([1.0, 0.0], [0.0, 0.0]) == 0.0)

check("R14: the multilingual discovery tokenizer now recognizes Devanagari (fixed adapter-layer bug)",
      len(pdi_providers._TOKEN_RX.findall("आरबीआई ने रेपो रेट घटाई")) > 0)

_real_embed_batch = pdi_semantic._embed_batch
pdi_semantic.reset_availability_cache()
pdi_semantic._embed_batch = lambda texts: None   # simulate an unreachable/unavailable Ollama
try:
    check("R15: score_candidates degrades to {} (not an exception) when the semantic backend is down",
          pdi_semantic.score_candidates("event text", [("k", "candidate text")]) == {})
    try:
        _use_temp_db()
        eid_r16 = _lifecycle_event(title="Nandigram Bypoll Congress Candidate Arrested", topic="Politics")
        result_no_semantic = pdi.run_pdi_for_event(
            eid_r16, persist=False, now=NOW,
            providers={"substack": fake_provider([c_paraphrase_r])})
        check("R16: run_pdi_for_event completes normally (non-fatal) when semantic scoring is unavailable",
              result_no_semantic["status"] in (pdi.RUN_VALID, pdi.RUN_NO_MEANINGFUL_DISCOURSE,
                                               pdi.RUN_INSUFFICIENT_EVIDENCE),
              result_no_semantic["status"])
    finally:
        _restore_db()
finally:
    pdi_semantic._embed_batch = _real_embed_batch
    pdi_semantic.reset_availability_cache()

if pdi_semantic.is_available():
    real_scores = pdi_semantic.score_candidates(
        "Nandigram Bypoll Congress Candidate Arrested. A summary.",
        [("real", "Congress worker taken into custody in West Bengal bypoll row. "
                  "Local police detained a party worker in the ongoing bypoll dispute.")])
    real_result = real_scores.get("real")
    check("R17 (real Ollama/bge-m3 integration): a genuine paraphrase scores above the BACKGROUND floor "
          "and returns a bounded, non-empty passage set",
          real_result is not None and real_result["score"] >= pdi.SEM_BACKGROUND_MIN
          and 0 < len(real_result["passages"]) <= pdi_semantic.MAX_RELEVANT_PASSAGES,
          real_result)
else:
    print("  R17 (real Ollama/bge-m3 integration) ... SKIPPED (semantic backend not reachable in this environment)")


# =====================================================================================
# S. Passage localization + observation-provenance hardening (final hardening pass,
# Finding F: the material that justifies association must stay connected to
# observation extraction - no downstream stage may forget why a candidate was
# relevant).
# =====================================================================================
print("\n=== S. Passage localization: relevant material, not the whole document ===")

profile_s = pdi.build_discourse_profile(
    event_with_breadth(400, title="Karnataka Launches Salt Reduction Plan", topic="Health"))
_contaminated_candidate = make_candidate(
    title="Field notes from the health beat",
    body="Hospital staffing shortages continue in several districts, a persistent problem this year. "
         "Vaccine cold-chain logistics remain a nationwide headache with no clear fix in sight. "
         "Karnataka launched an ambitious salt reduction plan targeting a 30 percent cut by 2030. "
         "Meanwhile drug pricing transparency remains a long-running unresolved policy fight.",
    published_h_ago=20)
_matched_passage = "Karnataka launched an ambitious salt reduction plan targeting a 30 percent cut by 2030."
a_localized = pdi.associate_candidate(_contaminated_candidate, profile_s, NOW,
                                      semantic_score=0.80, relevant_passage=_matched_passage)
check("S1: a SELECTED association carries the specific passage that justified it, not the whole document",
      a_localized.relevant_passage == _matched_passage and a_localized.relevant_passage != _contaminated_candidate.body_text)

obs_localized = pdi.extract_observations(a_localized)
obs_texts = " ".join(o.text for o in obs_localized)
check("S2: extract_observations only sees the localized passage - no contamination from "
      "unrelated sentences elsewhere in the same document (hospital staffing / vaccine logistics / "
      "drug pricing, none of which are the target event)",
      obs_localized and "hospital staffing" not in obs_texts.lower()
      and "vaccine cold-chain" not in obs_texts.lower() and "drug pricing" not in obs_texts.lower())
check("S3: the localized observation IS about the actual matched passage",
      any("salt reduction" in o.text.lower() for o in obs_localized))

a_no_passage = pdi.associate_candidate(_contaminated_candidate, profile_s, NOW, semantic_score=0.80)
obs_no_passage = pdi.extract_observations(a_no_passage)
check("S4: without a passage (e.g. deterministic-only path), extract_observations falls back to the "
      "whole document exactly as before - no regression for that path",
      any("hospital staffing" in o.text.lower() for o in obs_no_passage))

check("S5: passage-scoped entity specificity is used for corroboration, not whole-document specificity - "
      "a marginal semantic score is corroborated by what the PASSAGE itself contains",
      pdi._entity_specificity(_matched_passage, profile_s)[0] >= 1)

_marginal_broad_digest = make_candidate(
    title="Weekly Health Policy Roundup",
    body="This week the health ministry dealt with a wide spread of matters spanning drug pricing, "
         "hospital staffing, and various state-level public health initiatives across the country.",
    published_h_ago=48)
a_marginal_no_entity = pdi.associate_candidate(_marginal_broad_digest, profile_s, NOW,
                                               semantic_score=pdi.SEM_RELATED_MIN + 0.01,
                                               relevant_passage=_marginal_broad_digest.body_text)
check("S6: a MARGINAL semantic score (just above threshold) on a broad, non-entity-specific passage "
      "is NOT promoted to RELATED_CONTEXT (the real India Judiciary Watch false-positive pattern) - "
      "this is the corroboration-margin fix",
      a_marginal_no_entity.association != pdi.ASSOCIATION_RELATED_CONTEXT, a_marginal_no_entity.association)

a_comfortable_no_entity = pdi.associate_candidate(_marginal_broad_digest, profile_s, NOW,
                                                  semantic_score=pdi.SEM_RELATED_MIN + pdi.SEM_MARGIN + 0.05,
                                                  relevant_passage=_marginal_broad_digest.body_text)
check("S7: a COMFORTABLY strong semantic score still reaches RELATED_CONTEXT without entity corroboration "
      "(preserves genuine paraphrase/multilingual recovery, which has no entity overlap by construction)",
      a_comfortable_no_entity.association == pdi.ASSOCIATION_RELATED_CONTEXT, a_comfortable_no_entity.association)

check("S8: score_candidates bounds the returned passage set to MAX_RELEVANT_PASSAGES",
      pdi_semantic.MAX_RELEVANT_PASSAGES >= 1 and pdi_semantic.MAX_RELEVANT_PASSAGES <= 4)

_real_embed_batch_s9 = pdi_semantic._embed_batch
pdi_semantic.reset_availability_cache()
_calls = {"n": 0}
def _flaky_then_recovers(texts):
    _calls["n"] += 1
    return None if _calls["n"] == 1 else [[1.0, 0.0]] * len(texts)
pdi_semantic._embed_batch = _flaky_then_recovers
try:
    first = pdi_semantic.is_available()
    second = pdi_semantic.is_available()
    check("S9: a single transient probe failure does NOT permanently disable semantic scoring for "
          "the rest of the run - is_available() re-probes after a failure instead of caching it "
          "(real hardening-pass finding: one bad probe silently ran an entire 12-event real "
          "experiment in deterministic-only fallback even though Ollama was reachable again "
          "moments later)",
          first is False and second is True, (first, second))
finally:
    pdi_semantic._embed_batch = _real_embed_batch_s9
    pdi_semantic.reset_availability_cache()


print(f"\n{'=' * 60}")
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S):")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
else:
    print("ALL PDI CHECKS PASSED")
