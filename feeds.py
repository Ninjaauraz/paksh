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
    "opindia": ["https://www.opindia.com/feed/"],            # WordPress pattern
    "swarajya": ["https://swarajyamag.com/commonfeeds/v1/cms/rss/feed.xml"],
    "republic_world": ["https://www.republicworld.com/rssfeed.xml"],

    # ---- Hindi: verified / strong ----
    "amar_ujala": ["https://www.amarujala.com/rss/breaking-news.xml"],
    "navbharat_times": ["https://navbharattimes.indiatimes.com/rssfeedsdefault.cms"],

    # ---- Hindi: candidate (verify) ----
    "dainik_bhaskar": [],   # unknown - run --discover https://www.bhaskar.com
    "dainik_jagran": ["https://www.jagran.com/rss/news/national.xml"],
    "aaj_tak": ["https://www.aajtak.in/rss/home"],
    "zee_news_hindi": ["https://zeenews.india.com/hindi/rss/india.xml"],
    "satya_hindi": ["https://www.satyahindi.com/feed/"],     # WordPress pattern
    "the_lallantop": ["https://www.thelallantop.com/feed"],
}

# Confirmed against public RSS directories (others are candidates to verify).
VERIFIED = {
    "the_hindu", "indian_express", "times_of_india", "ndtv",
    "amar_ujala", "navbharat_times",
}


def feeds_for(source_id: str):
    return FEEDS.get(source_id, [])
