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

    # ---- v1.2 expansion (2026-06-23): high-volume mainstream via Google News bridges ----
    # Reliable out of the box. For the big English dailies you can later run
    #   py ingest.py --discover https://www.hindustantimes.com
    # to find a native RSS feed and swap it in for fuller article counts.
    "hindustan_times":  ["https://news.google.com/rss/search?q=site:hindustantimes.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en"],
    "deccan_herald":    ["https://news.google.com/rss/search?q=site:deccanherald.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en"],
    "telegraph_india":  ["https://news.google.com/rss/search?q=site:telegraphindia.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en"],
    "business_standard":["https://news.google.com/rss/search?q=site:business-standard.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en"],
    "india_today":      ["https://news.google.com/rss/search?q=site:indiatoday.in+when:2d&hl=en-IN&gl=IN&ceid=IN:en"],
    "firstpost":        ["https://news.google.com/rss/search?q=site:firstpost.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en"],
    "the_pioneer":      ["https://news.google.com/rss/search?q=site:dailypioneer.com+when:3d&hl=en-IN&gl=IN&ceid=IN:en"],
    "national_herald":  ["https://news.google.com/rss/search?q=site:nationalheraldindia.com+when:3d&hl=en-IN&gl=IN&ceid=IN:en"],
    "jansatta":         ["https://news.google.com/rss/search?q=site:jansatta.com+when:2d&hl=hi-IN&gl=IN&ceid=IN:hi"],
    "live_hindustan":   ["https://news.google.com/rss/search?q=site:livehindustan.com+when:2d&hl=hi-IN&gl=IN&ceid=IN:hi"],
    "news18_hindi":     ["https://news.google.com/rss/search?q=site:hindi.news18.com+when:2d&hl=hi-IN&gl=IN&ceid=IN:hi"],
    "patrika":          ["https://news.google.com/rss/search?q=site:patrika.com+when:2d&hl=hi-IN&gl=IN&ceid=IN:hi"],

    # ---- v1.3: international (with section feeds) + regional ----
    # International — native RSS where stable, with section feeds.
    "bbc_news": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://feeds.bbci.co.uk/news/world/asia/india/rss.xml",
        "https://feeds.bbci.co.uk/news/business/rss.xml",
        "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "https://feeds.bbci.co.uk/sport/rss.xml",
    ],
    "the_guardian": [
        "https://www.theguardian.com/world/india/rss",
        "https://www.theguardian.com/world/rss",
        "https://www.theguardian.com/business/rss",
        "https://www.theguardian.com/technology/rss",
    ],
    "al_jazeera": [
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://news.google.com/rss/search?q=site:aljazeera.com+India+when:2d&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    "dw_news": [
        "https://rss.dw.com/xml/rss-en-world",
        "https://news.google.com/rss/search?q=site:dw.com+India+when:3d&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    "france24": [
        "https://www.france24.com/en/rss",
        "https://news.google.com/rss/search?q=site:france24.com+India+when:3d&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    # Reuters / AP / Bloomberg dropped public RSS -> Google News bridges.
    "reuters": [
        "https://news.google.com/rss/search?q=site:reuters.com+India+when:2d&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=site:reuters.com+world+when:2d&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    "ap_news":   ["https://news.google.com/rss/search?q=site:apnews.com+India+when:2d&hl=en-IN&gl=IN&ceid=IN:en"],
    "bloomberg": ["https://news.google.com/rss/search?q=site:bloomberg.com+India+when:2d&hl=en-IN&gl=IN&ceid=IN:en"],

    # Regional: English (Google News bridges)
    "tribune_india":      ["https://news.google.com/rss/search?q=site:tribuneindia.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en"],
    "deccan_chronicle":   ["https://news.google.com/rss/search?q=site:deccanchronicle.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en"],
    "telangana_today":    ["https://news.google.com/rss/search?q=site:telanganatoday.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en"],
    "new_indian_express": ["https://news.google.com/rss/search?q=site:newindianexpress.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en"],
    "free_press_journal": ["https://news.google.com/rss/search?q=site:freepressjournal.in+when:2d&hl=en-IN&gl=IN&ceid=IN:en"],
    "eastmojo":           ["https://news.google.com/rss/search?q=site:eastmojo.com+when:3d&hl=en-IN&gl=IN&ceid=IN:en"],
    "greater_kashmir":    ["https://news.google.com/rss/search?q=site:greaterkashmir.com+when:3d&hl=en-IN&gl=IN&ceid=IN:en"],
    "mathrubhumi_eng":    ["https://news.google.com/rss/search?q=site:english.mathrubhumi.com+when:3d&hl=en-IN&gl=IN&ceid=IN:en"],

    # Regional: Hindi (Google News bridges)
    "prabhat_khabar":     ["https://news.google.com/rss/search?q=site:prabhatkhabar.com+when:2d&hl=hi-IN&gl=IN&ceid=IN:hi"],
    "nai_dunia":          ["https://news.google.com/rss/search?q=site:naidunia.com+when:2d&hl=hi-IN&gl=IN&ceid=IN:hi"],
    "punjab_kesari":      ["https://news.google.com/rss/search?q=site:punjabkesari.in+when:2d&hl=hi-IN&gl=IN&ceid=IN:hi"],
    "haribhoomi":         ["https://news.google.com/rss/search?q=site:haribhoomi.com+when:3d&hl=hi-IN&gl=IN&ceid=IN:hi"],
}

# Confirmed against public RSS directories (others are candidates to verify).
VERIFIED = {
    "the_hindu", "indian_express", "times_of_india", "ndtv",
    "amar_ujala", "navbharat_times", "aaj_tak",
}


def feeds_for(source_id: str):
    return FEEDS.get(source_id, [])