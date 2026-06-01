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
    ],
    "indian_express": [
        "https://indianexpress.com/feed/",
        "https://indianexpress.com/section/india/feed/",
    ],
    "times_of_india": [
        "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
        "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms",  # India
    ],
    "ndtv": [
        "https://feeds.feedburner.com/ndtvnews-top-stories",
    ],

    # ---- English: candidate (verify) ----
    "mint": ["https://www.livemint.com/rss/news"],
    "the_wire": ["https://thewire.in/rss"],
    "scroll": ["https://scroll.in/feeds/all.rss"],
    "opindia": ["https://www.opindia.com/feed/"],            # native WordPress feed (works)
    # Republic & Swarajya killed public RSS -> bridge via Google News (site-scoped, last 2 days)
    "swarajya": ["https://news.google.com/rss/search?q=site:swarajyamag.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en"],
    "republic_world": ["https://news.google.com/rss/search?q=site:republicworld.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en"],

    # ---- Hindi: verified / strong ----
    "amar_ujala": ["https://www.amarujala.com/rss/breaking-news.xml"],
    "navbharat_times": ["https://navbharattimes.indiatimes.com/rssfeedsdefault.cms"],

    # ---- Hindi: candidate (verify) ----
    # These Hindi sites lack a working public RSS -> bridge via Google News (Hindi, site-scoped)
    "dainik_bhaskar": ["https://news.google.com/rss/search?q=site:bhaskar.com+when:2d&hl=hi-IN&gl=IN&ceid=IN:hi"],
    "dainik_jagran": ["https://news.google.com/rss/search?q=site:jagran.com+when:2d&hl=hi-IN&gl=IN&ceid=IN:hi"],
    "aaj_tak": ["https://www.aajtak.in/rss"],                 # native feed (works)
    "zee_news_hindi": ["https://news.google.com/rss/search?q=site:zeenews.india.com/hindi+when:2d&hl=hi-IN&gl=IN&ceid=IN:hi"],
    "satya_hindi": ["https://www.satyahindi.com/feed/"],     # native WordPress feed (works)
    "the_lallantop": ["https://news.google.com/rss/search?q=site:thelallantop.com+when:2d&hl=hi-IN&gl=IN&ceid=IN:hi"],
}

# Confirmed against public RSS directories (others are candidates to verify).
VERIFIED = {
    "the_hindu", "indian_express", "times_of_india", "ndtv",
    "amar_ujala", "navbharat_times", "aaj_tak",
}


def feeds_for(source_id: str):
    return FEEDS.get(source_id, [])