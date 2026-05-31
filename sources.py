"""
Paksh - Source Registry (English + Hindi, v1)
=============================================

The single source of truth for which outlets Paksh tracks and how each is
rated for political lean. Everything downstream (the bias bar, blindspots)
reads lean from here.

IMPORTANT - READ BEFORE PUBLISHING
----------------------------------
* Every rating below is a PROVISIONAL DRAFT (`review_status: "provisional"`).
  These reflect *commonly-documented positioning* (ownership, self-described
  stance, well-established reputation) - they are a starting point, NOT Paksh's
  final published verdict.
* Before going live, each rating must be reviewed by the editor and, ideally,
  a small cross-spectrum panel, with the rationale checked against sources.
  See METHODOLOGY.md for the rubric and process.
* Lean in India is genuinely contested and outlets shift (especially after
  ownership changes). `contested: True` and lower `confidence` flag the
  debatable ones. When unsure, set lean to "unrated" rather than guess.
* "Left" / "Right" here are descriptive, not pejorative. Paksh applies the
  same scrutiny across the spectrum.

Lean values used by the pipeline: "left" | "center" | "right" | "unrated".
Feed URLs are intentionally omitted here - feed discovery & validation is
Part 2 (Ingestion).
"""

from lean_scoring import score_outlet  # noqa: F401  (used by tooling/tests)

SOURCES = [
    # ---------------- English ----------------
    {
        "id": "the_hindu", "name": "The Hindu", "language": "en",
        "website": "https://www.thehindu.com",
        "ownership": "The Hindu Group (Kasturi & Sons Ltd)",
        "lean": "left", "label": "Lean Left", "confidence": "medium", "contested": True,
        "review_status": "provisional", "last_reviewed": "2026-05-31",
        "rationale": "Legacy national daily; editorial page commonly described as "
                     "left-of-centre with a secular framing.",
        "subscores": {"editorial": -1, "framing": -1, "selection": -1,
                      "sourcing": -1, "ownership": 0, "panel": -1},
    },
    {
        "id": "indian_express", "name": "The Indian Express", "language": "en",
        "website": "https://indianexpress.com",
        "ownership": "Indian Express Group (Viveck Goenka)",
        "lean": "center", "label": "Centre", "confidence": "medium", "contested": False,
        "review_status": "provisional", "last_reviewed": "2026-05-31",
        "rationale": "Legacy daily known for investigative reporting that has "
                     "challenged governments across parties.",
        "subscores": None,
    },
    {
        "id": "times_of_india", "name": "The Times of India", "language": "en",
        "website": "https://timesofindia.indiatimes.com",
        "ownership": "Bennett, Coleman & Co. Ltd (Times Group)",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "provisional", "last_reviewed": "2026-05-31",
        "rationale": "India's largest-circulation English daily; broad, commercial, "
                     "relatively non-ideological news framing.",
        "subscores": {"editorial": 0, "framing": 0, "selection": 1,
                      "sourcing": 0, "ownership": 0, "panel": 0},
    },
    {
        "id": "mint", "name": "Mint", "language": "en",
        "website": "https://www.livemint.com",
        "ownership": "HT Media Ltd",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "provisional", "last_reviewed": "2026-05-31",
        "rationale": "Business and economy daily; market-oriented framing.",
        "subscores": None,
    },
    {
        "id": "ndtv", "name": "NDTV", "language": "en",
        "website": "https://www.ndtv.com",
        "ownership": "Ownership changed in 2022 (AMG Media / Adani Group stake)",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": True,
        "review_status": "provisional", "last_reviewed": "2026-05-31",
        "rationale": "Television/digital broadcaster; ownership changed in 2022 and "
                     "positioning is in flux - flagged for priority re-review.",
        "subscores": None,
    },
    {
        "id": "the_wire", "name": "The Wire", "language": "en",
        "website": "https://thewire.in",
        "ownership": "Foundation for Independent Journalism (non-profit)",
        "lean": "left", "label": "Lean Left", "confidence": "medium", "contested": True,
        "review_status": "provisional", "last_reviewed": "2026-05-31",
        "rationale": "Independent non-profit outlet; investigative focus, frequently "
                     "critical of the incumbent government.",
        "subscores": None,
    },
    {
        "id": "scroll", "name": "Scroll.in", "language": "en",
        "website": "https://scroll.in",
        "ownership": "Scroll Media Inc.",
        "lean": "left", "label": "Lean Left", "confidence": "low", "contested": True,
        "review_status": "provisional", "last_reviewed": "2026-05-31",
        "rationale": "Independent digital outlet; reporting and commentary commonly "
                     "described as progressive/secular in framing.",
        "subscores": None,
    },
    {
        "id": "opindia", "name": "OpIndia", "language": "en",
        "website": "https://www.opindia.com",
        "ownership": "Aadhyaasi Media and Content Services",
        "lean": "right", "label": "Lean Right", "confidence": "medium", "contested": True,
        "review_status": "provisional", "last_reviewed": "2026-05-31",
        "rationale": "Commentary-driven site that self-identifies with right-of-centre "
                     "and Hindu-nationalist perspectives.",
        "subscores": {"editorial": 1, "framing": 1, "selection": 1,
                      "sourcing": 1, "ownership": 1, "panel": 0},
    },
    {
        "id": "swarajya", "name": "Swarajya", "language": "en",
        "website": "https://swarajyamag.com",
        "ownership": "Kovai Media Private Limited",
        "lean": "right", "label": "Lean Right", "confidence": "medium", "contested": False,
        "review_status": "provisional", "last_reviewed": "2026-05-31",
        "rationale": "Magazine that explicitly self-describes as right-of-centre.",
        "subscores": None,
    },
    {
        "id": "republic_world", "name": "Republic World", "language": "en",
        "website": "https://www.republicworld.com",
        "ownership": "ARG Outlier Media",
        "lean": "right", "label": "Lean Right", "confidence": "medium", "contested": True,
        "review_status": "provisional", "last_reviewed": "2026-05-31",
        "rationale": "Television/digital network with a strongly nationalist framing.",
        "subscores": None,
    },

    # ---------------- Hindi ----------------
    {
        "id": "dainik_bhaskar", "name": "Dainik Bhaskar", "language": "hi",
        "website": "https://www.bhaskar.com",
        "ownership": "DB Corp Ltd",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "provisional", "last_reviewed": "2026-05-31",
        "rationale": "Among the largest-circulation Hindi dailies; broad mass readership.",
        "subscores": None,
    },
    {
        "id": "dainik_jagran", "name": "Dainik Jagran", "language": "hi",
        "website": "https://www.jagran.com",
        "ownership": "Jagran Prakashan Ltd",
        "lean": "right", "label": "Lean Right", "confidence": "low", "contested": True,
        "review_status": "provisional", "last_reviewed": "2026-05-31",
        "rationale": "Major Hindi daily often described as right-of-centre; needs "
                     "framing/selection analysis to confirm.",
        "subscores": None,
    },
    {
        "id": "amar_ujala", "name": "Amar Ujala", "language": "hi",
        "website": "https://www.amarujala.com",
        "ownership": "Amar Ujala Publications Ltd",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "provisional", "last_reviewed": "2026-05-31",
        "rationale": "Large Hindi daily with general mass readership.",
        "subscores": None,
    },
    {
        "id": "navbharat_times", "name": "Navbharat Times", "language": "hi",
        "website": "https://navbharattimes.indiatimes.com",
        "ownership": "Bennett, Coleman & Co. Ltd (Times Group)",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "provisional", "last_reviewed": "2026-05-31",
        "rationale": "Hindi daily within the Times group; broad commercial framing.",
        "subscores": None,
    },
    {
        "id": "aaj_tak", "name": "Aaj Tak", "language": "hi",
        "website": "https://www.aajtak.in",
        "ownership": "TV Today Network (India Today Group)",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "provisional", "last_reviewed": "2026-05-31",
        "rationale": "Leading Hindi news channel; mass-market framing.",
        "subscores": None,
    },
    {
        "id": "zee_news_hindi", "name": "Zee News (Hindi)", "language": "hi",
        "website": "https://zeenews.india.com/hindi",
        "ownership": "Zee Media Corporation (Essel Group)",
        "lean": "right", "label": "Lean Right", "confidence": "medium", "contested": True,
        "review_status": "provisional", "last_reviewed": "2026-05-31",
        "rationale": "Hindi news channel commonly described as having a nationalist framing.",
        "subscores": None,
    },
    {
        "id": "satya_hindi", "name": "Satya Hindi", "language": "hi",
        "website": "https://www.satyahindi.com",
        "ownership": "Independent digital outlet",
        "lean": "left", "label": "Lean Left", "confidence": "low", "contested": True,
        "review_status": "provisional", "last_reviewed": "2026-05-31",
        "rationale": "Independent Hindi digital outlet; commentary commonly described "
                     "as critical/independent of the incumbent government.",
        "subscores": None,
    },
    {
        "id": "the_lallantop", "name": "The Lallantop", "language": "hi",
        "website": "https://www.thelallantop.com",
        "ownership": "TV Today Network (India Today Group)",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": True,
        "review_status": "provisional", "last_reviewed": "2026-05-31",
        "rationale": "Youth-focused Hindi digital outlet; broad framing.",
        "subscores": None,
    },
]

# ---- helpers used by the rest of the app -------------------------------------

def lean_by_source() -> dict:
    """Backward-compatible {outlet name: lean} lookup used by ingest/analyze/db."""
    return {s["name"]: s["lean"] for s in SOURCES}

LEAN_BY_SOURCE = lean_by_source()


def get_sources(language=None) -> list:
    return [s for s in SOURCES if language is None or s["language"] == language]


def get_source(name: str):
    return next((s for s in SOURCES if s["name"] == name or s["id"] == name), None)


def coverage_summary() -> dict:
    """Quick registry stats - handy for a methodology/transparency page."""
    out = {"total": len(SOURCES), "by_language": {}, "by_lean": {},
           "contested": sum(1 for s in SOURCES if s.get("contested"))}
    for s in SOURCES:
        out["by_language"][s["language"]] = out["by_language"].get(s["language"], 0) + 1
        out["by_lean"][s["lean"]] = out["by_lean"].get(s["lean"], 0) + 1
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(coverage_summary(), indent=2, ensure_ascii=False))
    print("\nWorked examples (lean recomputed from sub-scores via the rubric):")
    for s in SOURCES:
        if s.get("subscores"):
            r = score_outlet(s["subscores"])
            print(f"  {s['name']:<22} stored={s['lean']:<7} "
                  f"computed={r['lean']:<7} ({r['label']}, conf {r['confidence']})")
