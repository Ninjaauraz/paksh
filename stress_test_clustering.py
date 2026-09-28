"""stress_test_clustering.py - Step 8: stress test claim_clustering.py at scale
to confirm it does NOT exhibit the same pairwise-explosion the shadow trial
found in the original check_entity_ambiguity. Pure Python, zero API calls,
zero network access.

Run:  py stress_test_clustering.py
"""
import random
import time
import tracemalloc

from claim_clustering import cluster_evidence_claims

random.seed(20260928)

SUBJECTS = ["police", "officials", "the minister", "the court", "scientists",
            "the company", "the opposition", "an anonymous source", "the CM",
            "the president", "residents", "doctors"]
PREDICATES = ["said", "confirmed", "reported", "claimed", "announced", "stated",
              "alleged", "was charged with", "was convicted of", "holds the role of"]
STATUSES = ["UNSPECIFIED", "UNSPECIFIED", "UNSPECIFIED", "CLAIMED_EXPLICIT",
            "CONFIRMED_EXPLICIT", "CURRENT_EXPLICIT", "ALLEGED_EXPLICIT"]


def make_claims(n, repeat_fraction=0.6, acronym_fraction=0.2):
    """n claims: `repeat_fraction` are near-duplicates of a small set of
    "base" claims (simulating real redundant multi-source reporting - the
    exact pattern that caused the original explosion), the rest are distinct.
    `acronym_fraction` of subjects are replaced with a shared acronym-like
    token, to also stress the same dimension that broke check_entity_ambiguity."""
    n_bases = max(1, int(n * 0.1))
    bases = []
    for _ in range(n_bases):
        subj = random.choice(SUBJECTS)
        if random.random() < acronym_fraction:
            subj = random.choice(["FIFA", "US", "BJP", "NDMC", "BRICS"])
        bases.append({
            "subject": subj, "predicate": random.choice(PREDICATES),
            "object": f"claim about topic {random.randint(1, 5)}",
            "status": random.choice(STATUSES), "fact_type": None, "value": None,
            "domain": None, "time_type": "UNSPECIFIED", "time_text": None,
        })
    claims = []
    for i in range(n):
        if random.random() < repeat_fraction:
            base = dict(random.choice(bases))
            base["source"] = f"Outlet{i}"
            claims.append(base)
        else:
            subj = random.choice(SUBJECTS)
            if random.random() < acronym_fraction:
                subj = random.choice(["FIFA", "US", "BJP", "NDMC", "BRICS"])
            claims.append({
                "subject": subj, "predicate": random.choice(PREDICATES),
                "object": f"distinct claim {i}", "status": random.choice(STATUSES),
                "fact_type": None, "value": None, "domain": None,
                "time_type": "UNSPECIFIED", "time_text": None, "source": f"Outlet{i}",
            })
    return claims


print(f"{'n':>6} {'time_s':>10} {'comparisons':>14} {'clusters':>10} {'peak_kb':>10}")
for n in (10, 50, 100, 500, 1000):
    claims = make_claims(n)
    tracemalloc.start()
    t0 = time.perf_counter()
    clusters, comparisons = cluster_evidence_claims(claims)
    elapsed = time.perf_counter() - t0
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"{n:>6} {elapsed:>10.4f} {comparisons:>14} {len(clusters):>10} {peak/1024:>10.1f}")

print()
print("Reference: a naive O(n^2) all-pairs approach at n=1000 would perform")
print(f"  {1000*999//2:,} comparisons unconditionally, regardless of subject diversity.")
print("The bucketed approach above only compares WITHIN same-clustering-subject")
print("buckets, so its comparison count scales with bucket size, not n^2 globally -")
print("see the 'comparisons' column above versus that reference number.")
