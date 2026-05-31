"""
seed_demo.py
------------
OPTIONAL. Populates Paksh with clearly-marked DEMO events so you can see the
full V2 interface (cards, topics, Blindspot feed) before fetching real news.

Run with:   python seed_demo.py

SYNTHETIC data — made-up outlet names and framing. Does NOT represent any real
publication. Every demo event is tagged "DEMO". Two events are crafted as
Blindspots (one side barely covering) so that feed isn't empty. Delete any time
by deleting paksh.db. Demo events have no image, so they show the topic-coloured
placeholder; real ingested articles bring real images.
"""

from database import init_db, insert_event


def cov(sources, framings):
    c = {s: {"count": 0, "sources": [], "framing": framings.get(s, "")}
         for s in ("left", "center", "right")}
    for src in sources:
        c[src["lean"]]["count"] += 1
        c[src["lean"]]["sources"].append(src["source"])
    return c


# reusable demo outlets (generic names, fixed leans)
PW = {"source": "The Progressive Wire", "lean": "left", "language": "en"}
JA = {"source": "Jan Awaaz", "lean": "left", "language": "hi"}
DL = {"source": "The Daily Ledger", "lean": "center", "language": "en"}
ML = {"source": "Metro Ledger", "lean": "center", "language": "en"}
RS = {"source": "Rashtriya Samachar", "lean": "center", "language": "hi"}
NT = {"source": "The National Tribune", "lean": "right", "language": "en"}
BP = {"source": "Bharat Post", "lean": "right", "language": "hi"}


def src(base, headline, framing, tone, lang_words):
    return {**base, "url": "#", "headline": headline, "framing": framing,
            "tone": tone, "notable_language": lang_words}


EVENTS = [
    {
        "title": "National budget raises infrastructure spending",
        "summary": "The annual budget sharply increased capital spending on roads and railways while leaving income-tax slabs unchanged.",
        "summary_points": [
            "Capital expenditure on infrastructure raised significantly year-on-year.",
            "Income-tax slabs left unchanged for individual taxpayers.",
            "Government projects the spending will create jobs and lift growth.",
            "Social-welfare allocations remained broadly flat.",
        ],
        "topic": "Economy", "image_url": "",
        "sources": [
            src(PW, "Budget pours billions into roads, but the poor are left waiting",
                "Frames the budget as favouring infrastructure over welfare.", "critical", ["left waiting"]),
            src(JA, "Welfare schemes see no real increase as capex takes priority",
                "Highlights flat social spending against the capex push.", "critical", ["no real increase"]),
            src(DL, "Budget raises capital spending, holds income-tax slabs steady",
                "Reports the announcement factually.", "neutral", []),
            src(RS, "Infrastructure budget up sharply; tax slabs unchanged",
                "Lays out the figures side by side.", "neutral", []),
            src(NT, "Bold capex push to power growth and create jobs, says government",
                "Presents the budget as decisive, growth-oriented reform.", "supportive", ["bold push", "growth engine"]),
        ],
        "divergence": "Left outlets centre what the budget withholds from welfare; right outlets centre growth and reform; centrist outlets report the figures plainly.",
        "omissions": "Supportive coverage barely mentions flat welfare spending; critical coverage downplays the infrastructure increase.",
        "_framings": {"left": "Left-leaning outlets argue the budget prioritises concrete over people.",
                      "center": "Centrist outlets report the capex rise and unchanged slabs as the two headline facts.",
                      "right": "Right-leaning outlets cast it as a bold, growth-first reform."},
    },
    {
        "title": "Parliament passes data protection law",
        "summary": "Parliament passed a data protection bill into law after debate, with rules to roll out over coming months.",
        "summary_points": [
            "Data protection bill passed by Parliament after debate.",
            "Law sets new obligations for how companies handle personal data.",
            "Government retains certain access provisions under the law.",
            "Detailed rules and timelines to follow in coming months.",
        ],
        "topic": "Politics", "image_url": "",
        "sources": [
            src(PW, "New data law hands government sweeping access, critics warn",
                "Centres civil-liberties concerns and state overreach.", "critical", ["sweeping access"]),
            src(DL, "Parliament passes data protection bill after debate",
                "Reports the vote and main provisions neutrally.", "neutral", []),
            src(ML, "Data bill becomes law; rules to follow in coming months",
                "Focuses on what changes for citizens and the timeline.", "neutral", []),
            src(NT, "Landmark data law to protect citizens and boost digital economy",
                "Frames the law as overdue protection and an economic enabler.", "supportive", ["landmark"]),
        ],
        "divergence": "Right coverage frames the law as protection and economic enabler; left coverage warns of overreach; centrist coverage focuses on provisions and timelines.",
        "omissions": "Supportive framing gives little attention to the government-access provisions the critical framing makes central.",
        "_framings": {"left": "Left-leaning outlets foreground civil-liberties risks.",
                      "center": "Centrist outlets report passage, provisions, and rollout.",
                      "right": "Right-leaning outlets frame it as overdue protection and a digital boost."},
    },
    {
        # LEFT BLINDSPOT — covered only by right + center (no left coverage)
        "title": "Government welfare scheme crosses 50 million beneficiaries",
        "summary": "A flagship government welfare scheme announced it had crossed 50 million enrolled beneficiaries.",
        "summary_points": [
            "Flagship welfare scheme reports crossing 50 million beneficiaries.",
            "Government cites the figure as evidence of delivery at scale.",
            "Independent verification of the enrolment data is still pending.",
        ],
        "topic": "Society", "image_url": "",
        "sources": [
            src(NT, "Historic milestone: welfare scheme touches 50 million lives",
                "Celebrates the figure as a delivery success.", "supportive", ["historic milestone"]),
            src(BP, "50 million now covered as flagship scheme expands rapidly",
                "Frames the expansion as rapid and successful.", "supportive", ["rapidly"]),
            src(DL, "Welfare scheme reports 50 million enrolments; data unverified",
                "Reports the claim while noting verification is pending.", "neutral", ["unverified"]),
        ],
        "divergence": "Right-leaning outlets present the milestone as a clear achievement; the centrist outlet reports it while flagging that the data is unverified.",
        "omissions": "No left-leaning outlet in the set covered this story at all — left-leaning readers would not see it.",
        "_framings": {"center": "The centrist outlet reports the figure while noting it is unverified.",
                      "right": "Right-leaning outlets present the milestone as a major delivery success."},
    },
    {
        # RIGHT BLINDSPOT — covered only by left + center (no right coverage)
        "title": "Workers protest new labour rules in multiple cities",
        "summary": "Trade unions held protests across several cities against newly notified labour rules they say weaken protections.",
        "summary_points": [
            "Trade unions protested newly notified labour rules in multiple cities.",
            "Unions say the rules weaken existing worker protections.",
            "The government says the rules modernise and simplify labour law.",
        ],
        "topic": "Politics", "image_url": "",
        "sources": [
            src(PW, "Thousands march as unions slam 'anti-worker' labour rules",
                "Centres the scale of protest and worker grievances.", "critical", ["anti-worker"]),
            src(JA, "Workers across cities rise against new labour code",
                "Frames the protests as a broad worker uprising.", "critical", ["rise against"]),
            src(ML, "Unions protest labour rule changes; government defends reform",
                "Reports both the protest and the government's defence.", "neutral", []),
        ],
        "divergence": "Left-leaning outlets foreground the scale of the protests and worker grievances; the centrist outlet balances protest coverage with the government's defence.",
        "omissions": "No right-leaning outlet in the set covered the protests — right-leaning readers would not see this story.",
        "_framings": {"left": "Left-leaning outlets foreground the scale of protest and worker grievances.",
                      "center": "The centrist outlet reports the protest alongside the government's defence."},
    },
]


# Hindi versions of the demo briefs, keyed by English title. Real events get
# these fields from analyze.py; here we supply them so the EN/हिं toggle has
# something to show in the demo.
HI = {
    "National budget raises infrastructure spending": {
        "title_hi": "राष्ट्रीय बजट में बुनियादी ढांचे पर खर्च बढ़ा",
        "summary_hi": "वार्षिक बजट में सड़कों और रेलवे पर पूंजीगत व्यय तेज़ी से बढ़ाया गया, जबकि आयकर स्लैब अपरिवर्तित रखे गए।",
        "summary_points_hi": [
            "बुनियादी ढांचे पर पूंजीगत व्यय साल-दर-साल काफी बढ़ाया गया।",
            "व्यक्तिगत करदाताओं के लिए आयकर स्लैब अपरिवर्तित रखे गए।",
            "सरकार का अनुमान है कि इस खर्च से रोज़गार बढ़ेगा और विकास को गति मिलेगी।",
            "सामाजिक कल्याण आवंटन मोटे तौर पर स्थिर रहा।",
        ],
    },
    "Parliament passes data protection law": {
        "title_hi": "संसद ने डेटा संरक्षण कानून पारित किया",
        "summary_hi": "संसद ने बहस के बाद डेटा संरक्षण विधेयक को कानून बना दिया, जिसके नियम आने वाले महीनों में लागू होंगे।",
        "summary_points_hi": [
            "बहस के बाद संसद ने डेटा संरक्षण विधेयक पारित किया।",
            "कानून कंपनियों के लिए व्यक्तिगत डेटा संभालने के नए दायित्व तय करता है।",
            "कानून के तहत सरकार कुछ पहुँच अधिकार अपने पास रखती है।",
            "विस्तृत नियम और समयसीमा आने वाले महीनों में आएंगे।",
        ],
    },
    "Government welfare scheme crosses 50 million beneficiaries": {
        "title_hi": "सरकारी कल्याण योजना ने 5 करोड़ लाभार्थियों का आँकड़ा पार किया",
        "summary_hi": "एक प्रमुख सरकारी कल्याण योजना ने 5 करोड़ नामांकित लाभार्थियों का आँकड़ा पार करने की घोषणा की।",
        "summary_points_hi": [
            "प्रमुख कल्याण योजना ने 5 करोड़ लाभार्थियों का आँकड़ा पार करने की सूचना दी।",
            "सरकार इस आँकड़े को बड़े पैमाने पर क्रियान्वयन का प्रमाण बताती है।",
            "नामांकन आँकड़ों का स्वतंत्र सत्यापन अभी बाकी है।",
        ],
    },
    "Workers protest new labour rules in multiple cities": {
        "title_hi": "कई शहरों में मज़दूरों का नए श्रम नियमों के खिलाफ प्रदर्शन",
        "summary_hi": "ट्रेड यूनियनों ने नए अधिसूचित श्रम नियमों के खिलाफ कई शहरों में प्रदर्शन किए, जिन्हें वे श्रमिक सुरक्षा कमज़ोर करने वाला बताते हैं।",
        "summary_points_hi": [
            "ट्रेड यूनियनों ने कई शहरों में नए श्रम नियमों के खिलाफ प्रदर्शन किया।",
            "यूनियनों का कहना है कि नियम मौजूदा श्रमिक सुरक्षा को कमज़ोर करते हैं।",
            "सरकार का कहना है कि नियम श्रम कानून को आधुनिक और सरल बनाते हैं।",
        ],
    },
}


def main():
    init_db()
    for ev in EVENTS:
        ev = dict(ev)
        ev.update(HI.get(ev["title"], {}))
        framings = ev.pop("_framings", {})
        ev["coverage"] = cov(ev["sources"], framings)
        ev["total_sources"] = len(ev["sources"])
        insert_event(ev, is_demo=True)
    print(f"Inserted {len(EVENTS)} DEMO events (2 of them Blindspots).")
    print("Start the server and open http://127.0.0.1:8000 :\n")
    print("    uvicorn main:app --reload\n")


if __name__ == "__main__":
    main()
