import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import cluster

# 7 articles. Vectors are hand-set so we control similarity:
#   budget direction = axis0, cricket = axis1, monsoon = axis2
articles = [
    {"id": 1, "source": "Outlet X", "language": "en", "title": "Budget raises capex",      "summary": "A long, detailed summary of the budget capital spending decision."},
    {"id": 2, "source": "Outlet Y", "language": "hi", "title": "बजट में रिकॉर्ड खर्च",        "summary": "बजट सारांश"},
    {"id": 3, "source": "Outlet Z", "language": "en", "title": "Budget: capex up (wire)",     "summary": "Wire copy on the budget."},
    {"id": 4, "source": "Outlet X", "language": "en", "title": "Budget capex (repost)",       "summary": "short"},   # same outlet as #1 -> dup
    {"id": 5, "source": "Outlet Y", "language": "en", "title": "Cricket: India win series",   "summary": "Match report."},
    {"id": 6, "source": "Outlet Z", "language": "hi", "title": "क्रिकेट: भारत की जीत",          "summary": "मैच रिपोर्ट"},
    {"id": 7, "source": "Outlet W", "language": "en", "title": "Monsoon arrives early",        "summary": "Weather."},
]
VECS = np.array([
    [1.00, 0.00, 0.00, 0.00],   # 1 budget
    [0.95, 0.05, 0.00, 0.00],   # 2 budget (hindi)  -> cross-lingual
    [0.90, 0.00, 0.10, 0.00],   # 3 budget (wire)
    [0.99, 0.00, 0.00, 0.01],   # 4 budget dup of #1 (same outlet X)
    [0.00, 1.00, 0.00, 0.00],   # 5 cricket
    [0.03, 0.97, 0.00, 0.00],   # 6 cricket (hindi) -> cross-lingual
    [0.00, 0.00, 1.00, 0.00],   # 7 monsoon (single outlet)
], dtype=float)

stub = lambda texts: VECS

result = cluster.cluster_articles(articles, embedder=stub)
details = cluster.cluster_with_details(articles, embedder=stub)

print("Clusters that become events (2+ outlets):")
for ids in result:
    rows = [a for a in articles if a["id"] in ids]
    print(f"  ids={sorted(ids)}  outlets={sorted({r['source'] for r in rows})}  "
          f"langs={sorted({r['language'] for r in rows})}")

flat = [i for ids in result for i in ids]
budget = sorted(next(ids for ids in result if 1 in ids))
cricket = sorted(next(ids for ids in result if 5 in ids))

assert len(result) == 2, f"expected 2 events, got {len(result)}"
assert budget == [1, 2, 3], f"budget cluster wrong / dup not removed: {budget}"
assert cricket == [5, 6], f"cricket cluster wrong: {cricket}"
assert 4 not in flat, "same-outlet duplicate (#4) was NOT removed"
assert len(details) == 3, f"expected 3 raw clusters incl monsoon singleton, got {len(details)}"
assert any(d["source_count"] == 1 and d["ids"] == [7] for d in details), "monsoon singleton missing"

# cross-lingual check: both events mix en + hi
for ids in result:
    langs = {a["language"] for a in articles if a["id"] in ids}
    assert langs == {"en", "hi"}, f"cross-lingual grouping failed for {ids}: {langs}"

print("\nChecks:")
print("  cross-lingual en+hi grouped ........ OK")
print("  same-outlet duplicate removed ...... OK (#4 dropped)")
print("  unrelated stories kept apart ....... OK (budget / cricket / monsoon)")
print("  2-outlet rule excludes singleton ... OK (monsoon not an event)")
print("\nALL ASSERTIONS PASSED")
