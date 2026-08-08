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
    "satya_hindi": ["https://news.google.com/rss/search?q=site:satyahindi.com+when:3d&hl=hi-IN&gl=IN&ceid=IN:hi"],  # was native /feed/ (caps at 10, under-captured); GN returns ~100/3d
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
    "the_caravan": ["https://news.google.com/rss/search?q=site:caravanmagazine.in+when:30d&hl=en-IN&gl=IN&ceid=IN:en"],  # native /feed broke (Cloudflare/HTML); dropped it, widened GN 14d->30d (low-volume monthly)
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

    # ===== v1.6 auto-added feeds (build_missing_feeds.py) =====
    # Google News bridges (reliable) + native RSS where known. All
    # CANDIDATE - verify/replace natives with `py ingest.py --discover URL`.
    # The Economic Times (en) [+native]
    "economic_times": [
        "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
        "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "https://news.google.com/rss/search?q=site:economictimes.indiatimes.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    # The Financial Express (en) [+native]
    "financial_express": [
        "https://www.financialexpress.com/feed/",
        "https://news.google.com/rss/search?q=site:financialexpress.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    # The Hindu BusinessLine (en) [+native]
    "hindu_business_line": [
        "https://www.thehindubusinessline.com/feeder/default.rss",
        "https://news.google.com/rss/search?q=site:thehindubusinessline.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    # Business Today (en)
    "business_today": [
        "https://news.google.com/rss/search?q=site:businesstoday.in+when:2d&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    # Outlook India (en)
    "outlook_india": [
        "https://news.google.com/rss/search?q=site:outlookindia.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    # DNA (Daily News & Analysis) (en)
    "dna_india": [
        "https://news.google.com/rss/search?q=site:dnaindia.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    # The Statesman (en) [+native]
    "the_statesman": [
        "https://www.thestatesman.com/feed",
        "https://news.google.com/rss/search?q=site:thestatesman.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    # Malayala Manorama (en)
    "malayala_manorama": [
        "https://news.google.com/rss/search?q=site:manoramaonline.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    # Mathrubhumi (en)
    "mathrubhumi": [
        "https://news.google.com/rss/search?q=site:mathrubhumi.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    # Anandabazar Patrika (en)
    "anandabazar_patrika": [
        "https://news.google.com/rss/search?q=site:anandabazar.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    # Lokmat (en)
    "lokmat": [
        "https://news.google.com/rss/search?q=site:lokmat.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    # Sakal (en)
    "sakal": [
        "https://news.google.com/rss/search?q=site:esakal.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    # Eenadu (en)
    "eenadu": [
        "https://news.google.com/rss/search?q=site:eenadu.net+when:2d&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    # Daily Thanthi (en)
    "daily_thanthi": [
        "https://news.google.com/rss/search?q=site:dailythanthi.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    # Divya Bhaskar (hi)
    "divya_bhaskar": [
        "https://news.google.com/rss/search?q=site:divyabhaskar.co.in+when:2d&hl=hi-IN&gl=IN&ceid=IN:hi",
    ],
    # Times Now (en)
    "times_now": [
        "https://news.google.com/rss/search?q=site:timesnownews.com+when:2d&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    # The New York Times (intl) [+native]
    "nyt": [
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
        "https://news.google.com/rss/search?q=site:nytimes.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # The Washington Post (intl) [+native]
    "washington_post": [
        "https://feeds.washingtonpost.com/rss/world",
        "https://news.google.com/rss/search?q=site:washingtonpost.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # CNN (intl)
    "cnn": [
        "https://news.google.com/rss/search?q=site:edition.cnn.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # Fox News (intl)
    "fox_news": [
        "https://news.google.com/rss/search?q=site:foxnews.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # NPR (intl) [+native]
    "npr": [
        "https://feeds.npr.org/1001/rss.xml",
        "https://news.google.com/rss/search?q=site:npr.org+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # TIME (intl) [+native]
    "time_magazine": [
        "https://time.com/feed/",
        "https://news.google.com/rss/search?q=site:time.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # Sky News (intl) [+native]
    "sky_news": [
        "https://feeds.skynews.com/feeds/rss/world.xml",
        "https://news.google.com/rss/search?q=site:news.sky.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # The Independent (intl) [+native]
    "the_independent": [
        "https://www.independent.co.uk/news/world/rss",
        "https://news.google.com/rss/search?q=site:independent.co.uk+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # Daily Mail (intl)
    "daily_mail": [
        "https://news.google.com/rss/search?q=site:dailymail.co.uk+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # Le Monde (intl) [+native]
    "le_monde": [
        "https://www.lemonde.fr/en/rss/une.xml",
        "https://news.google.com/rss/search?q=site:lemonde.fr+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # ABC Australia (intl) [+native]
    "abc_australia": [
        "https://www.abc.net.au/news/feed/51120/rss.xml",
        "https://news.google.com/rss/search?q=site:abc.net.au+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # CBC News (intl) [+native]
    "cbc_news": [
        "https://www.cbc.ca/webfeed/rss/rss-world",
        "https://news.google.com/rss/search?q=site:cbc.ca+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # NBC News (intl) [+native]
    "nbc_news": [
        "https://feeds.nbcnews.com/nbcnews/public/world",
        "https://news.google.com/rss/search?q=site:nbcnews.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # CBS News (intl) [+native]
    "cbs_news": [
        "https://www.cbsnews.com/latest/rss/world",
        "https://news.google.com/rss/search?q=site:cbsnews.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # USA Today (intl)
    "usa_today": [
        "https://news.google.com/rss/search?q=site:usatoday.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # ABC News (US) (intl)
    "abc_news_us": [
        "https://news.google.com/rss/search?q=site:abcnews.go.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # Politico (intl)
    "politico": [
        "https://news.google.com/rss/search?q=site:politico.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # The Wall Street Journal (intl)
    "wsj": [
        "https://news.google.com/rss/search?q=site:wsj.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # The Atlantic (intl) [+native]
    "the_atlantic": [
        "https://www.theatlantic.com/feed/all/",
        "https://news.google.com/rss/search?q=site:theatlantic.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # The New Yorker (intl)
    "new_yorker": [
        "https://news.google.com/rss/search?q=site:newyorker.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # Business Insider (intl)
    "business_insider": [
        "https://news.google.com/rss/search?q=site:businessinsider.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # CNBC (intl)
    "cnbc": [
        "https://news.google.com/rss/search?q=site:cnbc.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # Forbes (intl) [+native]
    "forbes": [
        "https://www.forbes.com/business/feed/",
        "https://news.google.com/rss/search?q=site:forbes.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # Fortune (intl) [+native]
    "fortune": [
        "https://fortune.com/feed/",
        "https://news.google.com/rss/search?q=site:fortune.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # Los Angeles Times (intl)
    "la_times": [
        "https://news.google.com/rss/search?q=site:latimes.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # Chicago Tribune (intl)
    "chicago_tribune": [
        "https://news.google.com/rss/search?q=site:chicagotribune.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # Voice of America (intl)
    "voa": [
        "https://news.google.com/rss/search?q=site:voanews.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # The Economist (intl) [+native]
    "the_economist": [
        "https://www.economist.com/international/rss.xml",
        "https://news.google.com/rss/search?q=site:economist.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # Financial Times (intl) [+native]
    "financial_times": [
        "https://www.ft.com/rss/home",
        "https://news.google.com/rss/search?q=site:ft.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # The Daily Telegraph (intl)
    "daily_telegraph": [
        "https://news.google.com/rss/search?q=site:telegraph.co.uk+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # Evening Standard (intl)
    "evening_standard": [
        "https://news.google.com/rss/search?q=site:standard.co.uk+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # Daily Mirror (intl)
    "daily_mirror": [
        "https://news.google.com/rss/search?q=site:mirror.co.uk+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # Metro (UK) (intl) [+native]
    "metro_uk": [
        "https://metro.co.uk/feed/",
        "https://news.google.com/rss/search?q=site:metro.co.uk+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # The Globe and Mail (intl)
    "globe_and_mail": [
        "https://news.google.com/rss/search?q=site:theglobeandmail.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # Toronto Star (intl)
    "toronto_star": [
        "https://news.google.com/rss/search?q=site:thestar.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # Global News (Canada) (intl) [+native]
    "global_news_ca": [
        "https://globalnews.ca/feed/",
        "https://news.google.com/rss/search?q=site:globalnews.ca+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # CTV News (intl)
    "ctv_news": [
        "https://news.google.com/rss/search?q=site:ctvnews.ca+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # The Sydney Morning Herald (intl)
    "smh": [
        "https://news.google.com/rss/search?q=site:smh.com.au+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # The Age (intl)
    "the_age": [
        "https://news.google.com/rss/search?q=site:theage.com.au+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # Australian Financial Review (intl)
    "afr": [
        "https://news.google.com/rss/search?q=site:afr.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # South China Morning Post (intl) [+native]
    "scmp": [
        "https://www.scmp.com/rss/91/feed",
        "https://news.google.com/rss/search?q=site:scmp.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # Channel News Asia (intl) [+native]
    "cna": [
        "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml",
        "https://news.google.com/rss/search?q=site:channelnewsasia.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # The Japan Times (intl) [+native]
    "japan_times": [
        "https://www.japantimes.co.jp/feed/",
        "https://news.google.com/rss/search?q=site:japantimes.co.jp+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # The Jerusalem Post (intl)
    "jerusalem_post": [
        "https://news.google.com/rss/search?q=site:jpost.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # Gulf News (intl)
    "gulf_news": [
        "https://news.google.com/rss/search?q=site:gulfnews.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # Euronews (intl) [+native]
    "euronews": [
        "https://www.euronews.com/rss",
        "https://news.google.com/rss/search?q=site:euronews.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
    # Irish Independent (intl)
    "irish_independent": [
        "https://news.google.com/rss/search?q=site:independent.ie+when:2d&hl=en-US&gl=US&ceid=US:en",
    ],
}

# Confirmed against public RSS directories (others are candidates to verify).
VERIFIED = {
    "the_hindu", "indian_express", "times_of_india", "ndtv",
    "amar_ujala", "navbharat_times", "aaj_tak",
}


def feeds_for(source_id: str):
    return FEEDS.get(source_id, [])