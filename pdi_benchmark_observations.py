"""
pdi_benchmark_observations.py - deterministic observation-extraction benchmark
(hardening pass, Part 5). A REPORT, not a pass/fail gate for the same reason as
pdi_benchmark_association.py: the goal is an honest account of the pattern-based
extractor's behavior, especially the invariant that matters most - observations must
NEVER silently become factual claims, no matter how many times a claim repeats, how
conditionally it's phrased, or how confidently it's stated.

Run:  py pdi_benchmark_observations.py
"""
import pdi

CASES = [
    ("theme", "Many commentators are discussing the new policy's rollout timeline in detail."),
    ("question", "Will this policy actually be enforced in rural areas or only in cities?"),
    ("concern", "I'm genuinely worried this change will hurt small businesses the most."),
    ("interpretation", "Analysts argue this move signals a broader shift in government strategy."),
    ("experience", "I personally waited three hours at the office to get this processed myself."),
    ("disagreement", "However, other experts disagree and say the policy will have no real effect at all."),
    ("uncertainty", "It's unclear whether this will actually reduce prices or not, honestly hard to say."),
    ("implication", "This could lead to higher costs for consumers as a result of the new rules."),
    ("repeated misinformation (still just an observation, never a fact)",
     "Many people claim the policy secretly bans all future exports immediately, though officials deny this."),
    ("conditional language",
     "If the policy is implemented as announced, prices might rise, but this depends on several factors."),
    ("conflicting claims in one passage",
     "Some say the reform helps farmers directly. Others disagree and argue it mainly benefits large corporations."),
    ("firsthand experience with specifics",
     "I run a small shop and I saw my supply costs jump the very week this rule took effect."),
    ("generic opinion with no specifics", "This is just bad policy overall, in my opinion."),
]


def main():
    print(f"OBSERVATION_TYPES (frozen vocabulary): {pdi.OBSERVATION_TYPES}\n")
    print(f"{'intended pattern':<55} {'extracted type(s)':<40} {'never a fact?'}")
    print("-" * 120)
    never_a_fact_violations = 0
    for label, text in CASES:
        cand = pdi.Candidate(provider="reddit", provider_item_id=label[:12], url="https://example.com/x",
                             canonical_url="", title="Discussion thread", author="a", published_at=None,
                             language="en", discovery_query="q", discovery_rank=0, content_hash="",
                             body_text=text)
        assoc = pdi.Association(candidate=cand, association=pdi.ASSOCIATION_DIRECT_EVENT,
                                association_score=0.9, relevance_score=0.5, specificity_score=0.5,
                                source_quality_score=0.5, independence_score=1.0, recency_score=0.9,
                                quality_status=pdi.QUALITY_SELECTED, reason="benchmark fixture")
        obs = pdi.extract_observations(assoc)
        types = [o.observation_type for o in obs]
        never_fact = all(t in pdi.OBSERVATION_TYPES for t in types) and all(o.confidence < 1.0 for o in obs)
        never_a_fact_violations += (0 if never_fact else 1)
        print(f"{label:<55} {str(types):<40} {'OK' if never_fact else 'VIOLATION'}")
        for o in obs:
            print(f"    -> [{o.observation_type}] {o.text!r} (confidence={o.confidence})")
    print("-" * 120)
    print(f"\n'never becomes a fact' invariant violations: {never_a_fact_violations}/{len(CASES)}")
    print("(A 'violation' would mean an observation type outside OBSERVATION_TYPES, or a "
          "confidence of 1.0/absolute certainty - neither is structurally possible in this "
          "module, since no such type or confidence path exists in the code.)")


if __name__ == "__main__":
    main()
