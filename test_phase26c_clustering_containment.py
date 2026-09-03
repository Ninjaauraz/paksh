"""
test_phase26c_clustering_containment.py - Phase 26C: deterministic tests for
the clustering containment fix (cluster.py's _gating_keywords()/_GENERIC_KW
additions), closing the confirmed root cause from Phase 26B: a generic
template word (e.g. "highlights") could be the SOLE shared keyword that
activates cluster_vectors()'s n>=1/STRONG_SIM escape hatch, letting unrelated
templated content (sports scorecards, horoscope columns, listing pages) merge
into one fake event.

Two layers are tested:
1. _gating_keywords() directly against REAL member-article titles pulled from
   the confirmed bad events (3563, 9367) and confirmed bad events found in the
   Phase 26B systemic scan (9256/24/6537 horoscope, 5263 columnist-listing) -
   real corpus evidence, not invented text, wherever it was available.
2. cluster_vectors() end-to-end with deterministic SYNTHETIC vectors (no live
   embedder call - cluster_vectors() takes vecs as a plain parameter, so this
   is fully deterministic and reproducible) combined with REAL _gating_keywords()
   output, covering the six required fixtures: sports-template, horoscope-
   template, listing-template (all "must not cluster"), a legitimate low-volume
   story, a legitimate reworded-same-story pair, and a recurring-entity/
   different-incident pair (all "must still behave correctly").

Never touches paksh.db, never calls a real embedder, never mutates production.

Run:  py test_phase26c_clustering_containment.py
"""
import numpy as np

import cluster

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


def unit(v):
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v)
    return v / n if n else v


def template_vecs(n, dim=32, base_sim=0.90, seed=0):
    """n unit vectors all mutually similar (>= base_sim), simulating real
    embedding-collapse on heavily templated text - the worst-case regime for
    the escape hatch (sim well above STRONG_SIM=0.79)."""
    rng = np.random.RandomState(seed)
    base = unit(rng.randn(dim))
    out = []
    # mix factor chosen so pairwise cosine similarity lands close to base_sim
    mix = np.sqrt(base_sim)
    noise_mix = np.sqrt(1 - base_sim)
    for i in range(n):
        noise = unit(rng.randn(dim))
        out.append(unit(mix * base + noise_mix * noise))
    return np.array(out)


print("TEST 1: SPORTS TEMPLATE - real member titles from confirmed bad event 3563 "
      "(verbatim, queried live from the production DB; same language only - see "
      "'Known Failure Replay' / cross-lingual note in the final report for why "
      "mixed-language articles are handled separately, not in this fixture)")
sports_titles = [
    "HUN vs AUT highlights (6/27/2026)",
    "DEN-W vs CHE-W highlights (6/28/2026)",
    "Upcoming GIB vs SER cricket match (7/12/2026): GIB vs SER ball by ball commentary, GIB vs SER stats",
    "Switzerland Women in Denmark, 4 T20I Series, 2026 Cricket Series 2026, Live Scores and Results",
    "Bangladesh in Zimbabwe, Only Test, 2026 Cricket Series 2026, Live Scores and Results",
]
kw_sports = [cluster._gating_keywords({"title": t, "summary": ""}) for t in sports_titles]
print(f"     keywords: {kw_sports}")
vecs_sports = template_vecs(len(sports_titles), base_sim=0.90, seed=1)
groups = cluster.cluster_vectors(vecs_sports, kw=kw_sports, langs=["en"] * len(sports_titles))
check("1a: 5 unrelated templated sports articles (same language) at 0.90 mutual "
      "similarity do NOT all collapse into one cluster", len(groups) > 1)
check("1b: no single cluster contains more than 1 of the 5 unrelated articles "
      "(each is a genuinely distinct match with zero real shared keywords once "
      "'highlights'/'cricket' are excluded from gating)",
      max(len(g) for g in groups) == 1)
print(f"     groups: {groups}")

print("\nTEST 1c (INFORMATIONAL, not a pass/fail gate on this fix): cross-language "
      "join is a SEPARATE, pre-existing, documented design path (cluster_vectors()'s "
      "eligible(): 'DIFFERENT language -> may join on similarity >= HIGH_SIM alone') "
      "that bypasses keyword gating entirely by design, for genuine cross-lingual "
      "same-event recall where no keywords can ever be shared. It is NOT the "
      "mechanism Phase 26B diagnosed (which was same-language, keyword-gated) and "
      "is explicitly out of scope for this fix per Section 8 ('if another materially "
      "different false-clustering mechanism appears, do not automatically expand "
      "the implementation - report it separately'). Demonstrating it here for the "
      "record, not asserting on it:")
hi_title = "SER vs CZE Central-Europe-Cup-2026 Match-6 Info in Hindi - Serbia vs Czechia मैच रिपोर्ट"
kw_cross = kw_sports[:2] + [cluster._gating_keywords({"title": hi_title, "summary": ""})]
vecs_cross = template_vecs(3, base_sim=0.90, seed=7)
groups_cross = cluster.cluster_vectors(vecs_cross, kw=kw_cross, langs=["en", "en", "hi"])
print(f"     (en/en/hi) groups at 0.90 cross-lingual similarity: {groups_cross}  "
      f"-> see report for disposition")

print("\nTEST 2: HOROSCOPE TEMPLATE - real member titles from confirmed bad events 9256/24/6537")
horoscope_titles = [
    "कुंभ राशि वालों को कोई अच्छी खबर मिलेगी, जानें अपनी राशि का हाल",   # event 9256, article 179368 (verbatim)
    "मेष राशि",                                                          # event 24, article 4587 (verbatim)
    "वृश्चिक राशि वाले जॉब में पाएंगे उन्नति, जानें अन्य राशियों का हाल",  # event 6537, article 108189 (verbatim)
    "कुंभ राशि वालों की बढ़ेगी आय और बजट, जानें क्या कहती है आपकी राशि",  # event 6537, article 113234 (verbatim)
    "पैसों की तंगी से लेकर करियर तक हर समस्या को होगा समाधान! कर्क और सिंह राशि वाले जातक जुलाई में क्या करें उपाय?",  # event 6537, article 103268 (verbatim)
]
kw_horo = [cluster._gating_keywords({"title": t, "summary": ""}) for t in horoscope_titles]
vecs_horo = template_vecs(len(horoscope_titles), base_sim=0.90, seed=2)
groups2 = cluster.cluster_vectors(vecs_horo, kw=kw_horo, langs=["hi"] * len(horoscope_titles))
check("2a: 5 unrelated horoscope-sign articles at 0.90 mutual similarity do NOT "
      "all collapse into one cluster", len(groups2) > 1)
check("2b: no single cluster contains more than 2 of the 5 unrelated sign articles",
      max(len(g) for g in groups2) <= 2)
print(f"     groups: {groups2}")

print("\nTEST 3: LISTING/EDITION TEMPLATE - real member titles from confirmed bad events 2604/2990/5263")
listing_titles = [
    "Tribune India Bathinda Edition, Thu, 25 Jun 26",
    "Tribune India Jalandhar Edition, Thu, 25 Jun 26",
    "Free Press Journal Free Press School - Mumbai Edition, Thu, 25 Jun 26",
    "Ashwini Kumar - Read the latest hindi news articles by Ashwini Kumar",
    "Sagar Kaushik Read all the latest hindi news from Sagar Kaushik | Jagran.com",
    "Parvez Ahmad Read all the latest hindi news from Parvez Ahmad | Jagran.com",
]
kw_listing = [cluster._gating_keywords({"title": t, "summary": ""}) for t in listing_titles]
vecs_listing = template_vecs(len(listing_titles), base_sim=0.90, seed=3)
groups3 = cluster.cluster_vectors(vecs_listing, kw=kw_listing, langs=["en"] * len(listing_titles))
check("3a: 6 unrelated edition/columnist-listing pages at 0.90 mutual similarity "
      "do NOT all collapse into one cluster", len(groups3) > 1)
check("3b: no single cluster contains more than 2 of the 6 unrelated listing pages",
      max(len(g) for g in groups3) <= 2)
print(f"     groups: {groups3}")

print("\nTEST 4: LEGITIMATE LOW-VOLUME STORY - a genuine 2-outlet story must still cluster")
low_vol_titles = [
    "Bombay High Court Fines Police for Withholding FIR Copies",
    "Bombay High Court fines Palghar SHO Rs 25,000 for denying FIR copy to accused",
]
kw_lv = [cluster._gating_keywords({"title": t, "summary": ""}) for t in low_vol_titles]
print(f"     keywords: {kw_lv}")
check("4a: the two real headlines about the same real story share >= MIN_SHARED "
      "real (non-generic) keywords", len(kw_lv[0] & kw_lv[1]) >= cluster.MIN_SHARED)
vecs_lv = template_vecs(2, base_sim=0.85, seed=4)
groups4 = cluster.cluster_vectors(vecs_lv, kw=kw_lv, langs=["en", "en"])
check("4b: they DO still cluster together (false-negative guard)", len(groups4) == 1)

print("\nTEST 5: LEGITIMATE REWORDED SAME STORY - genuinely the same event, reworded "
      "headlines, at strong semantic similarity (protects the recall the "
      "STRONG_SIM escape hatch exists for)")
reworded_titles = [
    "Egypt holds nerve against Australia to make history with first knockout round win",
    "FIFA World Cup Round of 32 highlights: Egypt beat Australia 4-2 on penalties",
]
kw_rw = [cluster._gating_keywords({"title": t, "summary": ""}) for t in reworded_titles]
print(f"     keywords: {kw_rw}")
shared_rw = kw_rw[0] & kw_rw[1]
check("5a: at least one real (non-generic) shared keyword survives (real "
      "content words like 'egypt'/'australia' persist through rewording; "
      "'highlights' alone - the confirmed bad mechanism - is no longer "
      "sufficient by itself)", len(shared_rw) >= 1 and shared_rw != {"highlights"})
vecs_rw = template_vecs(2, base_sim=0.90, seed=5)  # >= STRONG_SIM, simulating a genuine same-event embedding match
groups5 = cluster.cluster_vectors(vecs_rw, kw=kw_rw, langs=["en", "en"])
check("5b: they DO still cluster together (recall preserved for a genuine "
      "same-story reworded-headline pair)", len(groups5) == 1)

print("\nTEST 5c: the STRONG_SIM escape hatch itself (exactly n=1 REAL shared "
      "keyword, not a generic one) still works - this is the specific path "
      "the fix must not break. Two real-style headlines about the same real "
      "local news event, worded so only the place name survives as a shared "
      "keyword:")
single_kw_titles = [
    "Massive blaze breaks out at Ghaziabad garment factory, no casualties reported",
    "Ghaziabad warehouse guts overnight in major fire, brigade brings situation under control",
]
kw_single = [cluster._gating_keywords({"title": t, "summary": ""}) for t in single_kw_titles]
print(f"     keywords: {kw_single}")
shared_single = kw_single[0] & kw_single[1]
check("5c-i: exactly one real shared keyword ('ghaziabad')", shared_single == {"ghaziabad"})
vecs_single = template_vecs(2, base_sim=0.90, seed=8)
groups5c = cluster.cluster_vectors(vecs_single, kw=kw_single, langs=["en", "en"])
check("5c-ii: they DO still cluster via the n=1/STRONG_SIM escape hatch when "
      "the single shared keyword is real content, not a generic template word",
      len(groups5c) == 1)

print("\nTEST 6: RECURRING POLITICAL STORY - same entities, different incidents, must NOT merge")
recurring_titles = [
    "BJP Criticizes Punjab AAP Govt Over Employee Protests, Unmet Promises",
    "BJP MP Raghav Chadha alleges 'political vendetta' after his name deleted from draft SIR rolls",
]
kw_rec = [cluster._gating_keywords({"title": t, "summary": ""}) for t in recurring_titles]
print(f"     keywords: {kw_rec}")
# Different specific incidents sharing only broad party-name overlap - embedding
# similarity for genuinely different news days is realistically moderate, well
# below the join/escape-hatch regime tested above.
vecs_rec = template_vecs(2, base_sim=0.55, seed=6)  # below JOIN_THRESHOLD (0.61)
groups6 = cluster.cluster_vectors(vecs_rec, kw=kw_rec, langs=["en", "en"])
check("6: two different incidents involving the same party, at realistic "
      "moderate similarity, do NOT merge into one event", len(groups6) == 2)

print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
