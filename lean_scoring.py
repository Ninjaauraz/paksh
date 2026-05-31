"""
Paksh - Media Lean Scoring (the rubric, made executable)
========================================================

This module turns a set of *documented sub-scores* about a publisher into a
single, transparent lean label plus a confidence level.

Two principles it enforces:
  1. Lean is a property of the PUBLISHER, not of an individual article.
  2. The label is a transparent FUNCTION of documented inputs - never an
     opaque pronouncement. Anyone can see which signals produced the rating.

Software (and AI) help *measure* the inputs at scale (framing, story
selection). Humans / cross-spectrum reviewers set the final sub-scores and
sign off. See METHODOLOGY.md for the full, public method.

Axis convention (matches the Paksh UI):
    -10 .......... 0 .......... +10
   LEFT        CENTRE        RIGHT
For India, the axis is a published blend of (a) social-ideological
(secular/pluralist <-> Hindu-nationalist) and (b) institutional stance
(critical of the incumbent <-> aligned with it). The economic dimension is
tracked separately - see METHODOLOGY.md.
"""

# key, human label, weight  (weights sum to 1.0)
DIMENSIONS = [
    ("editorial", "Editorial / opinion stance", 0.30),
    ("framing",   "News framing & language",    0.25),
    ("selection", "Story selection / agenda",   0.20),
    ("sourcing",  "Sourcing patterns",          0.10),
    ("ownership", "Ownership & affiliation",     0.10),
    ("panel",     "Cross-spectrum blind panel",  0.05),
]
WEIGHTS = {k: w for k, _label, w in DIMENSIONS}

# Each sub-score is an integer on this scale:
#   -2 strongly Left | -1 lean Left | 0 Centre | +1 lean Right | +2 strongly Right
SUBSCORE_MIN, SUBSCORE_MAX = -2, 2

# Bucket thresholds on the -10..+10 composite axis.
CENTRE_BAND = 2.0     # |composite| < 2  -> Centre
STRONG_BAND = 6.0     # |composite| >= 6 -> "Strong", else "Lean"

_NAME = {"left": "Left", "right": "Right", "center": "Centre", "unrated": "Unrated"}


def score_outlet(subscores: dict) -> dict:
    """
    subscores: {dimension_key: int in [-2, 2]}; missing/None dims are allowed
    (weights are renormalised over the dimensions actually provided).

    Returns a dict:
      composite     float in [-10, 10]
      lean          one of "left" | "center" | "right" | "unrated"  (3-bucket, for the UI)
      label         display label e.g. "Lean Left", "Strong Right", "Centre"
      confidence    "high" | "medium" | "low" | "none"
      completeness  fraction (0-1) of total weight that was scored
    """
    present = {k: int(v) for k, v in subscores.items()
               if k in WEIGHTS and v is not None}

    if not present:
        return {"composite": 0.0, "lean": "unrated", "label": "Unrated",
                "confidence": "none", "completeness": 0.0}

    weight_covered = sum(WEIGHTS[k] for k in present)
    weighted = sum(WEIGHTS[k] * present[k] for k in present) / weight_covered  # -2..2
    composite = round(weighted * 5.0, 1)                                       # -10..10

    if abs(composite) < CENTRE_BAND:
        lean, strength = "center", ""
    else:
        lean = "left" if composite < 0 else "right"
        strength = "Strong" if abs(composite) >= STRONG_BAND else "Lean"
    label = "Centre" if lean == "center" else f"{strength} {_NAME[lean]}"

    confidence = _confidence(list(present.values()), weight_covered)
    return {"composite": composite, "lean": lean, "label": label,
            "confidence": confidence, "completeness": round(weight_covered, 2)}


def _confidence(values, weight_covered) -> str:
    """Higher when signals are complete AND agree; lower when sparse or in conflict."""
    if not values:
        return "none"
    spread = max(values) - min(values)
    signs = {(1 if v > 0 else -1 if v < 0 else 0) for v in values if v != 0}
    conflict = len(signs) > 1                      # some signals Left, others Right
    if weight_covered >= 0.80 and not conflict and spread <= 2:
        return "high"
    if weight_covered >= 0.50 and not (conflict and spread >= 3) and spread <= 3:
        return "medium"
    return "low"


def explain(subscores: dict) -> str:
    """Human-readable breakdown - the kind of rationale shown on an outlet's page."""
    r = score_outlet(subscores)
    lines = [f"Lean: {r['label']}  (composite {r['composite']:+}, "
             f"confidence {r['confidence']}, {int(r['completeness']*100)}% scored)"]
    for key, label, w in DIMENSIONS:
        v = subscores.get(key)
        shown = "-" if v is None else f"{v:+d}"
        lines.append(f"  {label:<30} weight {int(w*100):>2}%   score {shown}")
    return "\n".join(lines)


if __name__ == "__main__":
    # Demo: three worked examples (illustrative sub-scores).
    examples = {
        "Outlet A (secular, critical of govt)": {
            "editorial": -1, "framing": -1, "selection": -1,
            "sourcing": -1, "ownership": 0, "panel": -1},
        "Outlet B (broad, commercial)": {
            "editorial": 0, "framing": 0, "selection": 1,
            "sourcing": 0, "ownership": 0, "panel": 0},
        "Outlet C (nationalist framing)": {
            "editorial": 1, "framing": 1, "selection": 1,
            "sourcing": 1, "ownership": 1, "panel": 0},
    }
    for name, ss in examples.items():
        print(f"\n## {name}")
        print(explain(ss))
