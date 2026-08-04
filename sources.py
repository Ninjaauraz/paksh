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
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Legacy national daily; editorial page commonly described as "
                     "left-of-centre with a secular framing.",
        "subscores": {"editorial": -1, "framing": -1, "selection": -1,
                      "sourcing": -1, "ownership": 0, "panel": -1},
        "axes": {"secular_authoritative": 85, "market_orientation": 30, "incumbent_stance": 20},
    },
    {
        "id": "indian_express", "name": "The Indian Express", "language": "en",
        "website": "https://indianexpress.com",
        "ownership": "Indian Express Group (Viveck Goenka)",
        "owner": "Indian Express Group",
        "lean": "center", "label": "Centre", "confidence": "medium", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Legacy daily known for investigative reporting that has "
                     "challenged governments across parties.",
        "subscores": None,
        "axes": {"secular_authoritative": 60, "market_orientation": 50, "incumbent_stance": 40},
    },
    {
        "id": "times_of_india", "name": "The Times of India", "language": "en",
        "website": "https://timesofindia.indiatimes.com",
        "ownership": "Bennett, Coleman & Co. Ltd (Times Group)",
        "owner": "Times Group",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "India's largest-circulation English daily. Some bias trackers "
                     "(MBFC) rate it right-of-centre, but its tilt reads as commercial/"
                     "establishment more than ideological; kept Centre, contested, low "
                     "confidence.",
        "subscores": {"editorial": 0, "framing": 0, "selection": 1,
                      "sourcing": 0, "ownership": 0, "panel": 0},
        "axes": {"secular_authoritative": 50, "market_orientation": 85, "incumbent_stance": 65},
    },
    {
        "id": "mint", "name": "Mint", "language": "en",
        "website": "https://www.livemint.com",
        "ownership": "HT Media Ltd",
        "owner": "HT Media",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Business and economy daily; market-oriented framing.",
        "subscores": None,
        "axes": {"secular_authoritative": 60, "market_orientation": 95, "incumbent_stance": 55},
    },
    {
        "id": "ndtv", "name": "NDTV", "language": "en",
        "website": "https://www.ndtv.com",
        "ownership": "Ownership changed in 2022 (AMG Media / Adani Group stake)",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Adani Group took a controlling stake in 2022 and several "
                     "government-critical anchors left; owner is openly pro-BJP. But "
                     "reviews of 2025 output still describe its reporting as relatively "
                     "independent/critical of the government, so the lean label (which "
                     "tracks output, not owner) stays Centre - contested, low "
                     "confidence, ownership a standing watch-item.",
        "subscores": None,
        "axes": {"secular_authoritative": 65, "market_orientation": 70, "incumbent_stance": 50},
    },
    {
        "id": "the_wire", "name": "The Wire", "language": "en",
        "website": "https://thewire.in",
        "ownership": "Foundation for Independent Journalism (non-profit)",
        "lean": "left", "label": "Lean Left", "confidence": "medium", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Independent non-profit outlet; investigative focus, frequently "
                     "critical of the incumbent government.",
        "subscores": None,
        "axes": {"secular_authoritative": 90, "market_orientation": 20, "incumbent_stance": 10},
    },
    {
        "id": "scroll", "name": "Scroll.in", "language": "en",
        "website": "https://scroll.in",
        "ownership": "Scroll Media Inc.",
        "lean": "left", "label": "Lean Left", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Independent digital outlet; reporting and commentary commonly "
                     "described as progressive/secular in framing.",
        "subscores": None,
        "axes": {"secular_authoritative": 85, "market_orientation": 30, "incumbent_stance": 15},
    },
    {
        "id": "opindia", "name": "OpIndia", "language": "en",
        "website": "https://www.opindia.com",
        "ownership": "Aadhyaasi Media and Content Services",
        "lean": "right", "label": "Lean Right", "confidence": "medium", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Commentary-driven site that self-identifies with right-of-centre "
                     "and Hindu-nationalist perspectives.",
        "subscores": {"editorial": 1, "framing": 1, "selection": 1,
                      "sourcing": 1, "ownership": 1, "panel": 0},
        "axes": {"secular_authoritative": 10, "market_orientation": 60, "incumbent_stance": 90},
    },
    {
        "id": "swarajya", "name": "Swarajya", "language": "en",
        "website": "https://swarajyamag.com",
        "ownership": "Kovai Media Private Limited",
        "lean": "right", "label": "Lean Right", "confidence": "medium", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Magazine that explicitly self-describes as right-of-centre.",
        "subscores": None,
        "axes": {"secular_authoritative": 15, "market_orientation": 75, "incumbent_stance": 85},
    },
    {
        "id": "republic_world", "name": "Republic World", "language": "en",
        "website": "https://www.republicworld.com",
        "ownership": "ARG Outlier Media",
        "lean": "right", "label": "Lean Right", "confidence": "medium", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Television/digital network with a strongly nationalist framing.",
        "subscores": None,
        "axes": {"secular_authoritative": 20, "market_orientation": 60, "incumbent_stance": 90},
    },

    # ---------------- Hindi ----------------
    {
        "id": "dainik_bhaskar", "name": "Dainik Bhaskar", "language": "hi",
        "website": "https://www.bhaskar.com",
        "ownership": "DB Corp Ltd",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Among the largest-circulation Hindi dailies; broad mass readership.",
        "subscores": None,
        "axes": {"secular_authoritative": 45, "market_orientation": 55, "incumbent_stance": 50},
    },
    {
        "id": "dainik_jagran", "name": "Dainik Jagran", "language": "hi",
        "website": "https://www.jagran.com",
        "ownership": "Jagran Prakashan Ltd",
        "owner": "Jagran Group",
        "lean": "right", "label": "Lean Right", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Major Hindi daily often described as right-of-centre; needs "
                     "framing/selection analysis to confirm.",
        "subscores": None,
        "axes": {"secular_authoritative": 30, "market_orientation": 60, "incumbent_stance": 75},
    },
    {
        "id": "amar_ujala", "name": "Amar Ujala", "language": "hi",
        "website": "https://www.amarujala.com",
        "ownership": "Amar Ujala Publications Ltd",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Large Hindi daily with general mass readership.",
        "subscores": None,
        "axes": {"secular_authoritative": 50, "market_orientation": 50, "incumbent_stance": 55},
    },
    {
        "id": "navbharat_times", "name": "Navbharat Times", "language": "hi",
        "website": "https://navbharattimes.indiatimes.com",
        "ownership": "Bennett, Coleman & Co. Ltd (Times Group)",
        "owner": "Times Group",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Hindi daily within the Times group; broad commercial framing.",
        "subscores": None,
        "axes": {"secular_authoritative": 50, "market_orientation": 70, "incumbent_stance": 60},
    },
    {
        "id": "aaj_tak", "name": "Aaj Tak", "language": "hi",
        "website": "https://www.aajtak.in",
        "ownership": "TV Today Network (India Today Group)",
        "owner": "India Today Group",
        "lean": "right", "label": "Lean Right", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Leading Hindi channel; bias trackers rate it right-of-centre with "
                     "pro-government framing, and it has been fined for inflammatory "
                     "primetime content. Mirrors the India Today group. Contested.",
        "subscores": None,
        "axes": {"secular_authoritative": 25, "market_orientation": 60, "incumbent_stance": 80},
    },
    {
        "id": "zee_news_hindi", "name": "Zee News (Hindi)", "language": "hi",
        "website": "https://zeenews.india.com/hindi",
        "ownership": "Zee Media Corporation (Essel Group)",
        "lean": "right", "label": "Lean Right", "confidence": "high", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Hindi channel widely and consistently described as strongly "
                     "pro-BJP (a prominent 'Godi media' example); high confidence.",
        "subscores": None,
        "axes": {"secular_authoritative": 10, "market_orientation": 65, "incumbent_stance": 95},
    },
    {
        "id": "satya_hindi", "name": "Satya Hindi", "language": "hi",
        "website": "https://www.satyahindi.com",
        "ownership": "Independent digital outlet",
        "lean": "left", "label": "Lean Left", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Independent Hindi digital outlet; commentary commonly described "
                     "as critical/independent of the incumbent government.",
        "subscores": None,
        "axes": {"secular_authoritative": 80, "market_orientation": 40, "incumbent_stance": 15},
    },
    {
        "id": "the_lallantop", "name": "The Lallantop", "language": "hi",
        "website": "https://www.thelallantop.com",
        "ownership": "TV Today Network (India Today Group)",
        "owner": "India Today Group",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Youth-focused Hindi digital outlet; broad framing.",
        "subscores": None,
        "axes": {"secular_authoritative": 55, "market_orientation": 65, "incumbent_stance": 50},
    },

    # ---------------- Independent / journalist-run (v1.1) ----------------
    # Smaller, independent or collective-run digital outlets. India's independent
    # press skews left-of-centre, so these additions lean that way; credible
    # right-of-centre independents (Swarajya & OpIndia above, plus the two below)
    # are fewer. EVERY lean here is a provisional draft - review before launch.
    {
        "id": "the_print", "name": "The Print", "language": "en",
        "website": "https://theprint.in",
        "ownership": "Printline Media Pvt Ltd (Shekhar Gupta)",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Independent digital outlet; positioning commonly described "
                     "as centrist, shading centre-right on some issues.",
        "subscores": None,
        "axes": {"secular_authoritative": 60, "market_orientation": 75, "incumbent_stance": 55},
    },
    {
        "id": "newslaundry", "name": "Newslaundry", "language": "en",
        "website": "https://www.newslaundry.com",
        "ownership": "Independent, subscriber-funded",
        "lean": "left", "label": "Lean Left", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Subscriber-funded media-critique and reporting outlet; "
                     "commonly described as left-of-centre.",
        "subscores": None,
        "axes": {"secular_authoritative": 85, "market_orientation": 25, "incumbent_stance": 10},
    },
    {
        "id": "the_news_minute", "name": "The News Minute", "language": "en",
        "website": "https://www.thenewsminute.com",
        "ownership": "Independent digital outlet",
        "lean": "left", "label": "Lean Left", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Independent, South-India-focused newsroom; commonly "
                     "described as left-of-centre.",
        "subscores": None,
        "axes": {"secular_authoritative": 80, "market_orientation": 35, "incumbent_stance": 20},
    },
    {
        "id": "the_caravan", "name": "The Caravan", "language": "en",
        "website": "https://caravanmagazine.in",
        "ownership": "Delhi Press",
        "lean": "left", "label": "Lean Left", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Long-form investigative magazine; editorial stance commonly "
                     "described as left-leaning.",
        "subscores": None,
        "axes": {"secular_authoritative": 90, "market_orientation": 20, "incumbent_stance": 5},
    },
    {
        "id": "the_quint", "name": "The Quint", "language": "en",
        "website": "https://www.thequint.com",
        "ownership": "Quintillion Media",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Independent digital outlet; positioning commonly described "
                     "as centre to centre-left.",
        "subscores": None,
        "axes": {"secular_authoritative": 75, "market_orientation": 55, "incumbent_stance": 40},
    },
    {
        "id": "livelaw", "name": "LiveLaw", "language": "en",
        "website": "https://www.livelaw.in",
        "ownership": "Independent legal-news outlet",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Specialist legal-news service; largely non-partisan court "
                     "and judgment reporting.",
        "subscores": None,
        "axes": {"secular_authoritative": 60, "market_orientation": 50, "incumbent_stance": 50},
    },
    {
        "id": "article14", "name": "Article 14", "language": "en",
        "website": "https://article-14.com",
        "ownership": "Independent collective",
        "lean": "left", "label": "Lean Left", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Rights- and rule-of-law-focused reporting; commonly "
                     "described as left-leaning.",
        "subscores": None,
        "axes": {"secular_authoritative": 90, "market_orientation": 30, "incumbent_stance": 15},
    },
    {
        "id": "reporters_collective", "name": "The Reporters' Collective", "language": "en",
        "website": "https://www.reporters-collective.in",
        "ownership": "Non-profit journalist collective",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Investigative collective run by a small group of journalists; "
                     "data- and document-driven framing.",
        "subscores": None,
        "axes": {"secular_authoritative": 70, "market_orientation": 40, "incumbent_stance": 30},
    },
    {
        "id": "the_commune", "name": "The Commune", "language": "en",
        "website": "https://thecommunemag.com",
        "ownership": "Independent digital outlet",
        "lean": "right", "label": "Lean Right", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Digital outlet with a nationalist, right-of-centre framing.",
        "subscores": None,
        "axes": {"secular_authoritative": 20, "market_orientation": 60, "incumbent_stance": 85},
    },
    {
        "id": "tfipost", "name": "TFIPOST", "language": "en",
        "website": "https://tfipost.com",
        "ownership": "Independent digital outlet",
        "lean": "right", "label": "Lean Right", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Digital opinion-and-news outlet with a right-of-centre, "
                     "nationalist framing.",
        "subscores": None,
        "axes": {"secular_authoritative": 15, "market_orientation": 65, "incumbent_stance": 85},
    },
    {
        "id": "khabar_lahariya", "name": "Khabar Lahariya", "language": "hi",
        "website": "https://khabarlahariya.org",
        "ownership": "Chambal Media (women-run)",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Rural, women-run grassroots outlet reporting in Hindi and "
                     "Bundeli; ground-reporting focus.",
        "subscores": None,
        "axes": {"secular_authoritative": 75, "market_orientation": 40, "incumbent_stance": 35},
    },

    # ================= v1.2 expansion (2026-06-23) =================
    # High-volume mainstream added to deepen clustering + raise article counts.
    # ALL leans below are PROVISIONAL first-drafts pending editor review.
    # ---------------- English ----------------
    {
        "id": "hindustan_times", "name": "Hindustan Times", "language": "en",
        "website": "https://www.hindustantimes.com",
        "ownership": "HT Media Ltd (KK Birla group)",
        "owner": "HT Media",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Large national English daily; broad mainstream news framing.",
        "subscores": None,
        "axes": {"secular_authoritative": 55, "market_orientation": 65, "incumbent_stance": 60},
    },
    {
        "id": "deccan_herald", "name": "Deccan Herald", "language": "en",
        "website": "https://www.deccanherald.com",
        "ownership": "The Printers (Mysore) Pvt Ltd",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Bengaluru-based national daily with conventional reportage.",
        "subscores": None,
        "axes": {"secular_authoritative": 60, "market_orientation": 55, "incumbent_stance": 45},
    },
    {
        "id": "telegraph_india", "name": "The Telegraph (India)", "language": "en",
        "website": "https://www.telegraphindia.com",
        "ownership": "ABP Group",
        "lean": "left", "label": "Lean Left", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Kolkata daily whose front pages and editorials are commonly "
                     "described as anti-establishment / left-of-centre.",
        "subscores": None,
        "axes": {"secular_authoritative": 85, "market_orientation": 40, "incumbent_stance": 15},
    },
    {
        "id": "business_standard", "name": "Business Standard", "language": "en",
        "website": "https://www.business-standard.com",
        "ownership": "Business Standard Pvt Ltd",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Business-and-policy daily; markets-focused, relatively neutral framing.",
        "subscores": None,
        "axes": {"secular_authoritative": 60, "market_orientation": 90, "incumbent_stance": 50},
    },
    {
        "id": "india_today", "name": "India Today", "language": "en",
        "website": "https://www.indiatoday.in",
        "ownership": "Living Media India Ltd (India Today Group)",
        "owner": "India Today Group",
        "lean": "right", "label": "Lean Right", "confidence": "medium", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Bias trackers (MBFC) rate it right-of-centre, favouring the "
                     "incumbent government; appears on the widely-cited 'Godi media' "
                     "list. Retains some investigative independence, so contested.",
        "subscores": None,
        "axes": {"secular_authoritative": 30, "market_orientation": 65, "incumbent_stance": 75},
    },
    {
        "id": "firstpost", "name": "Firstpost", "language": "en",
        "website": "https://www.firstpost.com",
        "ownership": "Network18 (Reliance)",
        "owner": "Network18",
        "lean": "right", "label": "Lean Right", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Digital outlet whose opinion-and-analysis framing is commonly "
                     "described as right-of-centre.",
        "subscores": None,
        "axes": {"secular_authoritative": 35, "market_orientation": 75, "incumbent_stance": 70},
    },
    {
        "id": "the_pioneer", "name": "The Pioneer", "language": "en",
        "website": "https://www.dailypioneer.com",
        "ownership": "CMYK Printech Ltd",
        "lean": "right", "label": "Lean Right", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Legacy daily with a right-of-centre editorial/op-ed orientation.",
        "subscores": None,
        "axes": {"secular_authoritative": 30, "market_orientation": 55, "incumbent_stance": 70},
    },
    {
        "id": "national_herald", "name": "National Herald", "language": "en",
        "website": "https://www.nationalheraldindia.com",
        "ownership": "Associated Journals Ltd (Congress-linked)",
        "lean": "left", "label": "Lean Left", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Outlet with explicit Congress lineage; left-of-centre framing.",
        "subscores": None,
        "axes": {"secular_authoritative": 85, "market_orientation": 30, "incumbent_stance": 10},
    },
    # ---------------- Hindi ----------------
    {
        "id": "jansatta", "name": "Jansatta", "language": "hi",
        "website": "https://www.jansatta.com",
        "ownership": "Indian Express Group",
        "owner": "Indian Express Group",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Hindi daily of the Indian Express Group; mainstream framing.",
        "subscores": None,
        "axes": {"secular_authoritative": 55, "market_orientation": 50, "incumbent_stance": 45},
    },
    {
        "id": "live_hindustan", "name": "Hindustan (Hindi)", "language": "hi",
        "website": "https://www.livehindustan.com",
        "ownership": "HT Media Ltd",
        "owner": "HT Media",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "High-circulation Hindi daily; broad mainstream coverage.",
        "subscores": None,
        "axes": {"secular_authoritative": 50, "market_orientation": 55, "incumbent_stance": 55},
    },
    {
        "id": "news18_hindi", "name": "News18 Hindi", "language": "hi",
        "website": "https://hindi.news18.com",
        "ownership": "Network18 (Reliance)",
        "owner": "Network18",
        "lean": "right", "label": "Lean Right", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Network18 Hindi outlet; framing commonly described as "
                     "right-of-centre. Provisional, contested.",
        "subscores": None,
        "axes": {"secular_authoritative": 30, "market_orientation": 70, "incumbent_stance": 80},
    },
    {
        "id": "patrika", "name": "Patrika", "language": "hi",
        "website": "https://www.patrika.com",
        "ownership": "Rajasthan Patrika group",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Large Hindi daily group; conventional regional+national coverage.",
        "subscores": None,
        "axes": {"secular_authoritative": 50, "market_orientation": 50, "incumbent_stance": 50},
    },

    # ================= v1.3 expansion (2026-06-23) =================
    # International houses (+ their section feeds) and regional outlets.
    # `region` groups them in the UI: International / Regional (others default
    # to National). ALL leans PROVISIONAL, pending editor review.
    # ---------------- International ----------------
    {
        "id": "reuters", "name": "Reuters", "language": "en", "region": "International",
        "website": "https://www.reuters.com",
        "ownership": "Thomson Reuters",
        "lean": "center", "label": "Centre", "confidence": "medium", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "International wire service; straight-news, agency-style reporting.",
        "subscores": None,
        "axes": {"secular_authoritative": 60, "market_orientation": 60, "incumbent_stance": 50},
    },
    {
        "id": "ap_news", "name": "Associated Press", "language": "en", "region": "International",
        "website": "https://apnews.com",
        "ownership": "Associated Press (non-profit cooperative)",
        "lean": "center", "label": "Centre", "confidence": "medium", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "International wire service; agency-style, fact-first reporting.",
        "subscores": None,
        "axes": {"secular_authoritative": 60, "market_orientation": 55, "incumbent_stance": 50},
    },
    {
        "id": "bbc_news", "name": "BBC News", "language": "en", "region": "International",
        "website": "https://www.bbc.com/news",
        "ownership": "British Broadcasting Corporation (UK public broadcaster)",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "UK public broadcaster; broad international coverage. Lean is "
                     "debated; treated as centre, contested.",
        "subscores": None,
        "axes": {"secular_authoritative": 70, "market_orientation": 50, "incumbent_stance": 40},
    },
    {
        "id": "the_guardian", "name": "The Guardian", "language": "en", "region": "International",
        "website": "https://www.theguardian.com",
        "ownership": "Guardian Media Group (Scott Trust)",
        "lean": "left", "label": "Lean Left", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "UK outlet, left-of-centre; its India coverage is government-"
                     "critical, which reads 'left' in the India frame. Foreign outlet "
                     "(region=International) - pending move to a non-voting international "
                     "tier so it does not skew the India bias bar.",
        "subscores": None,
        "axes": {"secular_authoritative": 85, "market_orientation": 30, "incumbent_stance": 15},
    },
    {
        "id": "al_jazeera", "name": "Al Jazeera English", "language": "en", "region": "International",
        "website": "https://www.aljazeera.com",
        "ownership": "Al Jazeera Media Network (Qatar)",
        "lean": "left", "label": "Lean Left", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Qatar-funded international outlet; its India coverage centres on "
                     "minority/Kashmir grievances and is government-critical, reading "
                     "'left' in the India frame. Foreign outlet (region=International) - "
                     "pending move to a non-voting international tier.",
        "subscores": None,
        "axes": {"secular_authoritative": 75, "market_orientation": 40, "incumbent_stance": 20},
    },
    {
        "id": "bloomberg", "name": "Bloomberg", "language": "en", "region": "International",
        "website": "https://www.bloomberg.com",
        "ownership": "Bloomberg L.P.",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "International business-and-markets outlet; data-driven framing.",
        "subscores": None,
        "axes": {"secular_authoritative": 55, "market_orientation": 95, "incumbent_stance": 50},
    },
    {
        "id": "dw_news", "name": "Deutsche Welle", "language": "en", "region": "International",
        "website": "https://www.dw.com",
        "ownership": "Deutsche Welle (German public broadcaster)",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "German public broadcaster's English service; broad world coverage.",
        "subscores": None,
        "axes": {"secular_authoritative": 65, "market_orientation": 55, "incumbent_stance": 45},
    },
    {
        "id": "france24", "name": "France 24", "language": "en", "region": "International",
        "website": "https://www.france24.com",
        "ownership": "France Médias Monde (French public broadcaster)",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "French public broadcaster's English service; international coverage.",
        "subscores": None,
        "axes": {"secular_authoritative": 65, "market_orientation": 55, "incumbent_stance": 45},
    },
    # ---------------- Regional: English ----------------
    {
        "id": "tribune_india", "name": "The Tribune", "language": "en", "region": "Regional",
        "website": "https://www.tribuneindia.com",
        "ownership": "The Tribune Trust",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Chandigarh-based daily covering Punjab, Haryana, HP and J&K.",
        "subscores": None,
        "axes": {"secular_authoritative": 55, "market_orientation": 50, "incumbent_stance": 50},
    },
    {
        "id": "deccan_chronicle", "name": "Deccan Chronicle", "language": "en", "region": "Regional",
        "website": "https://www.deccanchronicle.com",
        "ownership": "Deccan Chronicle Holdings",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Hyderabad-based daily with a South India focus.",
        "subscores": None,
        "axes": {"secular_authoritative": 55, "market_orientation": 55, "incumbent_stance": 50},
    },
    {
        "id": "telangana_today", "name": "Telangana Today", "language": "en", "region": "Regional",
        "website": "https://telanganatoday.com",
        "ownership": "Telangana Publications",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Telangana-focused daily; ownership ties to a state political party "
                     "noted. Provisional, contested.",
        "subscores": None,
        "axes": {"secular_authoritative": 60, "market_orientation": 50, "incumbent_stance": 50},
    },
    {
        "id": "new_indian_express", "name": "The New Indian Express", "language": "en", "region": "Regional",
        "website": "https://www.newindianexpress.com",
        "ownership": "Express Publications (Madurai) Ltd",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "South India-focused English daily.",
        "subscores": None,
        "axes": {"secular_authoritative": 55, "market_orientation": 60, "incumbent_stance": 50},
    },
    {
        "id": "free_press_journal", "name": "The Free Press Journal", "language": "en", "region": "Regional",
        "website": "https://www.freepressjournal.in",
        "ownership": "Free Press Journal group",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Mumbai-based daily with a metro and national mix.",
        "subscores": None,
        "axes": {"secular_authoritative": 55, "market_orientation": 60, "incumbent_stance": 45},
    },
    {
        "id": "eastmojo", "name": "EastMojo", "language": "en", "region": "Regional",
        "website": "https://www.eastmojo.com",
        "ownership": "Independent digital outlet",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Digital outlet focused on Northeast India; under-covered region.",
        "subscores": None,
        "axes": {"secular_authoritative": 65, "market_orientation": 45, "incumbent_stance": 40},
    },
    {
        "id": "greater_kashmir", "name": "Greater Kashmir", "language": "en", "region": "Regional",
        "website": "https://www.greaterkashmir.com",
        "ownership": "GK Communications",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Srinagar-based daily; primary J&K coverage. Provisional, contested.",
        "subscores": None,
        "axes": {"secular_authoritative": 70, "market_orientation": 40, "incumbent_stance": 30},
    },
    {
        "id": "mathrubhumi_eng", "name": "Mathrubhumi English", "language": "en", "region": "Regional",
        "website": "https://english.mathrubhumi.com",
        "ownership": "The Mathrubhumi Printing & Publishing Co.",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Kerala-based group's English service.",
        "subscores": None,
        "axes": {"secular_authoritative": 60, "market_orientation": 55, "incumbent_stance": 45},
    },
    # ---------------- Regional: Hindi ----------------
    {
        "id": "prabhat_khabar", "name": "Prabhat Khabar", "language": "hi", "region": "Regional",
        "website": "https://www.prabhatkhabar.com",
        "ownership": "Usha Martin group",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Hindi daily strong in Jharkhand and Bihar.",
        "subscores": None,
        "axes": {"secular_authoritative": 50, "market_orientation": 50, "incumbent_stance": 50},
    },
    {
        "id": "nai_dunia", "name": "Nai Dunia", "language": "hi", "region": "Regional",
        "website": "https://www.naidunia.com",
        "ownership": "Jagran group",
        "owner": "Jagran Group",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Hindi daily strong in Madhya Pradesh and Chhattisgarh.",
        "subscores": None,
        "axes": {"secular_authoritative": 45, "market_orientation": 50, "incumbent_stance": 55},
    },
    {
        "id": "punjab_kesari", "name": "Punjab Kesari", "language": "hi", "region": "Regional",
        "website": "https://www.punjabkesari.in",
        "ownership": "Punjab Kesari group",
        "lean": "right", "label": "Lean Right", "confidence": "low", "contested": True,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "North-India Hindi daily; framing sometimes described as "
                     "right-of-centre. Provisional, contested.",
        "subscores": None,
        "axes": {"secular_authoritative": 35, "market_orientation": 55, "incumbent_stance": 65},
    },
    {
        "id": "haribhoomi", "name": "Haribhoomi", "language": "hi", "region": "Regional",
        "website": "https://www.haribhoomi.com",
        "ownership": "Haribhoomi group",
        "lean": "center", "label": "Centre", "confidence": "low", "contested": False,
        "review_status": "reviewed", "last_reviewed": "2026-06-25",
        "rationale": "Hindi daily strong in Chhattisgarh, MP and Haryana.",
        "subscores": None,
        "axes": {"secular_authoritative": 50, "market_orientation": 50, "incumbent_stance": 50},
    },
]

# ---- helpers used by the rest of the app -------------------------------------

def lean_by_source() -> dict:
    """Backward-compatible {outlet name: lean} lookup used by ingest/analyze/db."""
    return {s["name"]: s["lean"] for s in SOURCES}

LEAN_BY_SOURCE = lean_by_source()


def owner_by_source() -> dict:
    """{outlet name: owning group} for ONE-VOTE-PER-OWNER counting.

    Co-owned mastheads (e.g. The Times of India + Navbharat Times, both Times
    Group; Mint + Hindustan Times + Hindustan (Hindi), all HT Media) share one
    owner and therefore cast ONE vote per side in the bias bar. An outlet with no
    shared owner maps to its OWN name, so it stays a distinct vote. A group that
    genuinely published on two different sides (e.g. India Today Group's right
    outlets and its centre outlet The Lallantop) still casts one vote on EACH side
    it covered - the collapse only ever happens WITHIN a single side. See
    analyze.postprocess for the arithmetic. This never touches lean labels."""
    return {s["name"]: s.get("owner", s["name"]) for s in SOURCES}

OWNER_BY_SOURCE = owner_by_source()

# Foreign wire services. They are tagged region="International" and DO carry a lean,
# but that lean is calibrated to their own home-market spectrum, not India's - so
# they must NOT vote in the India Left/Centre/Right bias bar. analyze.lean_of() maps
# these to a non-voting "international" tier: they still add coverage and framing.
INTERNATIONAL_SOURCES = {s["name"] for s in SOURCES if s.get("region") == "International"}


# ---- domain resolution (for GDELT and any URL-only article source) ----
import re as _re

def _host(website: str) -> str:
    h = (website or "").lower().strip()
    h = _re.sub(r"^https?://", "", h).split("/")[0]
    return h[4:] if h.startswith("www.") else h

# second-level public suffixes so we don't collapse "x.co.in" down to "co.in"
_TWO_LEVEL_TLDS = {
    "co.in", "net.in", "org.in", "gen.in", "firm.in", "ind.in", "co.uk", "org.uk",
    "com.au", "co.za", "com.pk", "com.bd", "com.np", "co.nz", "com.sg",
}

def _registrable(domain: str) -> str:
    """Bare registrable domain, so subdomains of one publisher collapse to one
    outlet: '1025thebear.iheart.com' -> 'iheart.com' (kills fake breadth)."""
    parts = (domain or "").split(".")
    if len(parts) <= 2:
        return domain
    if ".".join(parts[-2:]) in _TWO_LEVEL_TLDS and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])

# {bare domain -> rated outlet name}, built from each source's website
DOMAIN_TO_SOURCE = {_host(s["website"]): s["name"] for s in SOURCES if s.get("website")}

def resolve_source(domain: str):
    """Map an article's domain to a RATED registry outlet, or mark it UNRATED.

    Returns (source_name, is_rated). Rated -> the registry name (carries a lean).
    Unrated -> the bare *registrable* domain, so the long-tail outlet clusters
    consistently and its subdomains collapse to one, but it never votes in the
    Left/Centre/Right bias bar.
    """
    d = (domain or "").lower().strip()
    if d.startswith("www."):
        d = d[4:]
    if not d:
        return ("unknown.source", False)
    if d in DOMAIN_TO_SOURCE:
        return (DOMAIN_TO_SOURCE[d], True)
    for host, name in DOMAIN_TO_SOURCE.items():        # m.thehindu.com -> thehindu.com
        if d.endswith("." + host):
            return (name, True)
    return (_registrable(d), False)                    # unrated long-tail outlet


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
            r = score_outlet(s["subscores"], s.get("axes"))
            print(f"  {s['name']:<22} stored={s['lean']:<7} "
                  f"computed={r['lean']:<7} ({r['label']}, conf {r['confidence']})")