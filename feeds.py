"""
feeds.py - RSS endpoints for each source in the registry.

Kept separate from sources.py so that ratings stay clean, and so each outlet
can carry several section feeds.

VERIFIED  = URLs confirmed against curated public RSS directories. Still
            re-check on first run; feeds move over time.
CANDIDATE = best-guess using each site's usual RSS pattern. Confirm with:
                python ingest.py --discover https://the-site.com
            and paste the working URL(s) here.

Map: source id (from sources.py)  ->  list of feed URLs.
"""

FEEDS = {
    # ---- English: verified ----
    "the_hindu": [
        "https://www.thehindu.com/feeder/default.rss",
        "https://www.thehindu.com/news/national/feeder/default.rss",
        "https://www.thehindu.com/news/international/feeder/default.rss",
        "https://www.thehindu.com/business/feeder/default.rss",
        "https://www.thehindu.com/sport/feeder/default.rss",
    ],
    "indian_express": [
        "https://indianexpress.com/feed/",
        "https://indianexpress.com/section/india/feed/",
        "https://indianexpress.com/section/business/feed/",
        "https://indianexpress.com/section/world/feed/",
        "https://indianexpress.com/section/political-pulse/feed/",
    ],
    "times_of_india": [
        "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
        "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms",   # India
        "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms",     # World
        "https://timesofindia.indiatimes.com/rssfeeds/1898055.cms",       # Business
    ],
    "ndtv": [
        "https://feeds.feedburner.com/ndtvnews-top-stories",
        "https://feeds.feedburner.com/ndtvnews-india-news",
        "https://feeds.feedburner.com/ndtvnews-world-news",
    ],

    # ---- English: candidate (verify) ----
    "mint": ["https://www.livemint.com/rss/news",
             "https://www.livemint.com/rss/markets",
             "https://www.livemint.com/rss/companies"],
    # The Wire & Scroll native RSS is unreliable -> bridge via Google News (revives the Left side)
    "the_wire": ["https://news.google.com/rss/search?q=site:thewire.in+when:3d&hl=en-IN&gl=IN&ceid=IN:en"],
    "scroll": ["https://news.google.com/rss/search?q=site:scroll.in+when:3d&hl=en-IN&gl=IN&ceid=IN:en"],
    "opindia": ["https://www.opindia.com/feed/"],            # native WordPress feed (works)
    # Republic & Swarajya killed public RSS -> bridge via Google News (site-scoped, last 2 days)
    "swarajya": ["https://news.google.com/rss/search?q=site:swarajyamag.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en"],
    "republic_world": ["https://news.google.com/rss/search?q=site:republicworld.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en"],

    # ---- Hindi: verified / strong ----
    "amar_ujala": ["https://www.amarujala.com/rss/breaking-news.xml",
                   "https://www.amarujala.com/rss/india-news.xml"],
    "navbharat_times": ["https://news.google.com/rss/search?q=site:navbharattimes.indiatimes.com+when:2d&hl=hi-IN&gl=IN&ceid=IN:hi"],

    # ---- Hindi: candidate (verify) ----
    # These Hindi sites lack a working public RSS -> bridge via Google News (Hindi, site-scoped)
    "dainik_bhaskar": ["https://news.google.com/rss/search?q=site:bhaskar.com+when:2d&hl=hi-IN&gl=IN&ceid=IN:hi"],
    "dainik_jagran": ["https://news.google.com/rss/search?q=site:jagran.com+when:2d&hl=hi-IN&gl=IN&ceid=IN:hi"],
    "aaj_tak": ["https://www.aajtak.in/rss"],                 # native feed (works)
    "zee_news_hindi": ["https://news.google.com/rss/search?q=site:zeenews.india.com/hindi+when:2d&hl=hi-IN&gl=IN&ceid=IN:hi"],
    "satya_hindi": ["https://www.satyahindi.com/feed/"],     # native WordPress feed (works)
    "the_lallantop": ["https://news.google.com/rss/search?q=site:thelallantop.com+when:2d&hl=hi-IN&gl=IN&ceid=IN:hi"],

    # ---- Independent / journalist-run (v1.1) ----
    # WordPress sites expose a clean native /feed/; the rest are bridged via
    # Google News (site-scoped). Watch ingest output and swap bridges -> native
    # for any high-volume outlet to get fuller, cleaner data.
    "the_print": ["https://news.google.com/rss/search?q=site:theprint.in+when:2d&hl=en-IN&gl=IN&ceid=IN:en"],
    "the_commune": ["https://thecommunemag.com/feed/"],
    "tfipost": ["https://tfipost.com/feed/"],
    "newslaundry": ["https://news.google.com/rss/search?q=site:newslaundry.com+when:3d&hl=en-IN&gl=IN&ceid=IN:en"],
    "the_news_minute": ["https://news.google.com/rss/search?q=site:thenewsminute.com+when:3d&hl=en-IN&gl=IN&ceid=IN:en"],
    "the_caravan": ["https://caravanmagazine.in/feed",
                    "https://news.google.com/rss/search?q=site:caravanmagazine.in+when:14d&hl=en-IN&gl=IN&ceid=IN:en"],
    "the_quint": ["https://news.google.com/rss/search?q=site:thequint.com+when:3d&hl=en-IN&gl=IN&ceid=IN:en"],
    "livelaw": ["https://news.google.com/rss/search?q=site:livelaw.in+when:3d&hl=en-IN&gl=IN&ceid=IN:en"],
    "article14": ["https://news.google.com/rss/search?q=site:article-14.com+when:5d&hl=en-IN&gl=IN&ceid=IN:en"],
    "reporters_collective": ["https://news.google.com/rss/search?q=site:reporters-collective.in+when:7d&hl=en-IN&gl=IN&ceid=IN:en"],
    "khabar_lahariya": ["https://news.google.com/rss/search?q=site:khabarlahariya.org+when:5d&hl=hi-IN&gl=IN&ceid=IN:hi"],
}

# Confirmed against public RSS directories (others are candidates to verify).
VERIFIED = {
    "the_hindu", "indian_express", "times_of_india", "ndtv",
    "amar_ujala", "navbharat_times", "aaj_tak",
}


def feeds_for(source_id: str):
    return FEEDS.get(source_id, [])