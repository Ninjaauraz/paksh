const {useState,useEffect,useMemo}=React;
    /* ---------------- icons ---------------- */
    const Search = (p) => <svg width={p.size||24} height={p.size||24} className={p.className||""} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>;
    const Sun = (p) => <svg width={p.size||24} height={p.size||24} className={p.className||""} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>;
    const Moon = (p) => <svg width={p.size||24} height={p.size||24} className={p.className||""} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>;
    const ArrowLeft = (p) => <svg width={p.size||24} height={p.size||24} className={p.className||""} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m12 19-7-7 7-7"/><path d="M19 12H5"/></svg>;
    const Eye = (p) => <svg width={p.size||24} height={p.size||24} className={p.className||""} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={p.strokeWidth||2} strokeLinecap="round" strokeLinejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>;
    const Sparkles = (p) => <svg width={p.size||24} height={p.size||24} className={p.className||""} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3L12 3Z"/></svg>;
    const Layers = (p) => <svg width={p.size||24} height={p.size||24} className={p.className||""} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m12 2 3 7h7l-5 5 2 7-7-4-7 4 2-7-5-5h7z"/></svg>;
    const ChevronRight = (p) => <svg width={p.size||24} height={p.size||24} className={p.className||""} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m9 18 6-6-6-6"/></svg>;
    const Menu = (p) => <svg width={p.size||24} height={p.size||24} className={p.className||""} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="4" x2="20" y1="12" y2="12"/><line x1="4" x2="20" y1="6" y2="6"/><line x1="4" x2="20" y1="18" y2="18"/></svg>;
    const X = (p) => <svg width={p.size||24} height={p.size||24} className={p.className||""} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>;
    const Scale = (p) => <svg width={p.size||24} height={p.size||24} className={p.className||""} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="M7 21h10M12 3v18M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/></svg>;
    const Home = (p) => <svg width={p.size||24} height={p.size||24} className={p.className||""} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/></svg>;
    const Grid = (p) => <svg width={p.size||24} height={p.size||24} className={p.className||""} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>;

    /* ---------------- config ---------------- */
    // Each side carries a COLOUR (mid-tone hex, for dots/badges) and a TEXTURE class
    // (seg-*, defined in styles.css with an oklch value + hex fallback). All three
    // sit at equal lightness; only hue + texture separate them, so no side reads louder.
    const BIAS = {
      left:   { color:"#4A6E80", tex:"seg-left",   soft:"#E3E8EA", en:"Left",   hi:"वाम" },
      center: { color:"#7E7768", tex:"seg-center", soft:"#ECE9E1", en:"Centre", hi:"केंद्र" },
      right:  { color:"#96603F", tex:"seg-right",  soft:"#EFE3DB", en:"Right",  hi:"दक्षिण" },
      international: { color:"#5E7E78", tex:"", soft:"#E3EAE8", en:"International", hi:"अंतरराष्ट्रीय" },
    };
    const TOKENS = {
      light: { bg:"bg-[#EAE6DB]", surface:"bg-[#F4F1EA]", soft:"bg-[#EFEBE1]", border:"border-[#D8D3C6]",
        tp:"text-[#15140F]", ts:"text-[#3A372F]", tf:"text-[#8A8371]", brand:"text-[#15140F]", brandBg:"bg-[#15140F]",
        blind:"text-[#75442E]", blindSoft:"bg-[#EFE3DB]", nav:"glass-nav-light",
        cta:"bg-[#15140F]", ctaT:"text-[#F4F1EA]", line:"#D8D3C6", ink:"#15140F", chip:"bg-[#EAE6DB]", centerSeg:"#8C8579",
        track:"#EAE6DB", gap:"#F4F1EA" },
      dark: { bg:"bg-[#1A1917]", surface:"bg-[#201F1C]", soft:"bg-[#262420]", border:"border-[#35322C]",
        tp:"text-[#EDEAE2]", ts:"text-[#B7B1A4]", tf:"text-[#847E72]", brand:"text-[#EDEAE2]", brandBg:"bg-[#EDEAE2]",
        blind:"text-[#C89170]", blindSoft:"bg-[#2E2019]", nav:"glass-nav-dark",
        cta:"bg-[#EDEAE2]", ctaT:"text-[#201F1C]", line:"#35322C", ink:"#EDEAE2", chip:"bg-[#2A2823]", centerSeg:"#8C8579",
        track:"#2A2823", gap:"#1A1917" },
    };
    const TOPIC_HI = {Politics:"राजनीति", Economy:"अर्थव्यवस्था", International:"अंतरराष्ट्रीय", Sports:"खेल",
      "Crime & Law":"अपराध व कानून", "Science & Tech":"विज्ञान व तकनीक", Health:"स्वास्थ्य",
      Entertainment:"मनोरंजन", Environment:"पर्यावरण", Society:"समाज", General:"सामान्य"};
    const SIGNALS = [
      {en:"Editorial stance", hi:"संपादकीय रुख", w:30}, {en:"Framing & word choice", hi:"फ़्रेमिंग और शब्द-चयन", w:25},
      {en:"Story selection", hi:"खबरों का चयन", w:20}, {en:"Sourcing & who they quote", hi:"स्रोत और उद्धरण", w:10},
      {en:"Ownership & affiliations", hi:"स्वामित्व और संबद्धता", w:10}, {en:"Cross-spectrum panel check", hi:"क्रॉस-स्पेक्ट्रम पैनल जाँच", w:5},
    ];
    const M_READ = {
      en:["The coloured bar shows how many of the covering outlets lean Left, Centre or Right.",
          "“Coverage Gaps” marks a story that outlets on one side of the spectrum covered while few or none on the other did - shown with the full Left · Centre · Right count.",
          "The neutral summary is generated automatically from the outlets' own coverage; the outlet labels and the counts come from editors and the registry, not the summary engine."],
      hi:["रंगीन बार दिखाता है कि कवर करने वाले कितने आउटलेट वाम, केंद्र या दक्षिण की ओर हैं।",
          "“कवरेज गैप” उस खबर को चिह्नित करता है जिसे स्पेक्ट्रम के एक तरफ़ के आउटलेट्स ने कवर किया पर दूसरी तरफ़ के बहुत कम या किसी ने नहीं - पूरे वाम · केंद्र · दक्षिण आँकड़े के साथ।",
          "तटस्थ सारांश आउटलेट्स की अपनी कवरेज से स्वचालित रूप से तैयार होता है; आउटलेट के लेबल और गिनती संपादकों और रजिस्ट्री से आती है, सारांश इंजन से नहीं।"],
    };
    const CONTACT = "corrections@paksh.example"; // <-- change to your real address
    const FORMSPREE_ENDPOINT = "https://formspree.io/f/mkolqann";

    const UI = {
      seeAll:{en:"See all", hi:"सभी देखें"}, top:{en:"Top", hi:"मुख्य"},
      sections:{en:"Sections", hi:"खंड"}, oneSided:{en:"One-Sided", hi:"एकतरफ़ा"},
      searchTab:{en:"Search", hi:"खोज"}, browse:{en:"Browse by topic", hi:"विषय से देखें"},
      searchHint:{en:"Search across all coverage", hi:"सभी कवरेज में खोजें"},
      groupBy:{en:"Group by", hi:"समूह"}, gLean:{en:"Lean", hi:"झुकाव"},
      gLang:{en:"Language", hi:"भाषा"}, gRegion:{en:"Region", hi:"क्षेत्र"},
      findOutlet:{en:"Find an outlet…", hi:"आउटलेट खोजें…"},
      National:{en:"National", hi:"राष्ट्रीय"}, Regional:{en:"Regional", hi:"क्षेत्रीय"},
      International:{en:"International", hi:"अंतरराष्ट्रीय"},
      registry:{en:"outlets tracked", hi:"आउटलेट"}, expandAll:{en:"Expand all", hi:"सभी खोलें"},
      collapseAll:{en:"Collapse all", hi:"सभी बंद करें"}, noOutlets:{en:"No outlets match.", hi:"कोई आउटलेट नहीं मिला।"},
    };
    const ui=(k,lang)=>(UI[k]||{})[lang]||(UI[k]||{}).en||k;

    const STR = {
      en: {
        navTop:"Top Stories", navOS:"Coverage Gaps", navSrc:"Sources", navMethod:"Method",
        search:"Search coverage…", tagline:"Compare how India's media covers each story - every side, side by side.",
        topNews:"Top Stories", osTitle:"Coverage Gaps",
        osSub:"A coverage gap is a story that outlets on one side of the spectrum covered while few or none on the other did. Paksh flags these by counting distinct outlets per lean - the same counts as the bias bar - and shows the full Left · Centre · Right tally on each. It's arithmetic, not a judgment about any outlet or about why a story was or wasn't covered. Outlets also differ in how much they publish, so an absence of coverage on one side may reflect an outlet's publishing volume rather than a deliberate omission.",
        gapLeftHead:"Covered more by Left-leaning outlets", gapRightHead:"Covered more by Right-leaning outlets",
        gapShowing:"Showing the {n} most lopsided of {total}", gapCovered:"Covered by",
        m_gapH:"How coverage gaps break down",
        m_gap:"Of the {total} stories Paksh flags as one-sided, {rh} are covered mainly by right-leaning outlets and {lh} mainly by left-leaning. This is not a measure of which side ignores more news. Paksh counts {lo} left-leaning and {ro} right-leaning outlets on India's spectrum, but they publish at very different volumes - the right-leaning set includes several high-volume TV and mass-market outlets, so right-leaning outlets appear about twice as often across all stories. Most of this imbalance reflects that volume difference, not editorial choice.",
        more:"More Top Stories", resultsFor:"Results for", noResults:"No stories match your search.",
        noResultsSub:"Try different keywords or browse top news.", noStories:"No stories to show right now. Please check back soon.",
        seeCoverage:"See coverage", most:"Most coverage", even:"Fairly even coverage", sources:"sources", source:"source",
        onlyLabel:"Only", back:"Back to feed", aiSummary:"Paksh neutral summary", aiSub:"neutral synthesis",
        autoTag:"Auto-summary", autoFrom:"from coverage",
        autoNote:"This headline comes straight from a covering outlet - a neutral Paksh summary is being prepared.",
        unratedTitle:"Unrated outlets", unratedNote:"Outlets we found covering this story but don't rate yet - they add coverage but don't affect the bias bar.",
        intlTitle:"International coverage", intlNote:"Foreign wire services (Reuters, AP, BBC…) covering this story - they add coverage but aren't rated on India's spectrum, so they don't affect the bias bar.",
        framingTitle:"How each side is framing it", framingSub:"A neutral read of what each side's coverage emphasises - based on the headlines collected, not opinion.", framingPending:"The side-by-side framing comparison appears once a full summary is generated for this story.",
        sideBySide:"Side by Side", coverageBreakdown:"Coverage Breakdown", totalSources:"Total news sources",
        whereLean:"Where the sources lean",
        aiNote:"Lean describes each publisher and is set by Paksh's editors, not generated per story. Summaries are generated automatically from the outlets' own coverage; the counts come from the sources.",
        osCalloutBody1:"Only", osCalloutBody2:"of the covering outlets lean this way - a count of outlets, not a judgment about why a side did or didn't cover it.",
        srcTitle:"Source ratings", srcIntro:"Every outlet Paksh tracks, how it's rated, and why.",
        srcDisclaimer:"All ratings are provisional - a documented starting point reviewed against our rubric, not a final verdict. Lean describes the publication, not any single article, and is open to appeal.",
        filterLean:"Lean", filterLang:"Language", langEN:"English", langHI:"Hindi", all:"All",
        ownership:"Ownership", whyRated:"Why this rating", signals:"Signals", confidence:"confidence",
        contested:"Contested", provisional:"Provisional", suggestFix:"Suggest a correction",
        methodTitle:"How Paksh works", m_doesH:"What Paksh does",
        m_does:"Paksh groups coverage of the same story from outlets across the spectrum, shows a neutral summary, and shows which sides are covering it - so you can see the whole picture and what your usual sources leave out.",
        m_ruleH:"The golden rule",
        m_rule:"A lean label belongs to the publication, not to any single article, and never to an algorithm. Paksh editors assign each outlet a lean using a fixed rubric. The automated summary only describes the coverage; it never decides anyone's politics. A story's bias bar is simple arithmetic: we count how many covering outlets fall on each side. And it is one vote per owner: when two mastheads share a parent company - say The Times of India and Navbharat Times, both Times Group - they count once on their side, so a single company cannot tilt the bar by publishing the same story under several names. We still show every masthead that covered the story; they just share one vote.",
        m_rateH:"How we rate a publication",
        m_rateLede:"We rate each publication on six signals, each scored from −2 to +2 and combined into one score from −10 (left) to +10 (right):",
        m_rateFoot:"Scores near zero are Centre; the further from zero, the stronger the lean.",
        m_axisH:"What “Left” and “Right” mean in India",
        m_axis:"In India, Left and Right aren't only about economics. Paksh blends a social-and-ideological axis (secular ↔ Hindutva) with an institutional one (critical of ↔ aligned with the incumbent), and tracks economic stance separately. “Left” and “Right” are descriptive, not insults - and the same scrutiny is applied across the spectrum.",
        m_partiesH:"Where India's parties roughly sit",
        m_parties:"These labels describe ideas, not teams - and they're rough, because parties shift over time and many regional parties don't fit neatly on one line. As a common-usage guide: the Left includes communist and socialist parties such as CPI(M) and CPI, and is associated with secular, pro-welfare, labour-first positions; the Right - most prominently the BJP - is associated with Hindutva-influenced cultural nationalism and a more market-friendly economic stance; the Centre spans the middle, where the Congress is often described as centre-left and many regional parties mix positions by issue. Remember: Paksh rates news outlets, not parties - an outlet's lean is about how it covers the news, not who it votes for.",
        m_provH:"Confidence, contested & provisional",
        m_prov:"Every rating today is provisional: a documented starting point based on ownership, self-described stance and well-established reputation, reviewed against the rubric - not a final verdict. Each shows a confidence level, and some are flagged Contested where lean is genuinely debated or ownership recently changed.",
        m_readH:"How to read a Paksh story", m_appealH:"Corrections & appeals",
        m_appeal:"Think a rating is wrong? Tell us the outlet, the rating you dispute, and a few specific examples - headlines or articles - and we'll re-review it against the rubric. Ratings are meant to be challenged.",
        footIndependence:"Paksh is an independent project and is not affiliated with any outlet shown. Lean labels are provisional and open to appeal.",
      },
      hi: {
        navTop:"मुख्य खबरें", navOS:"कवरेज गैप", navSrc:"स्रोत", navMethod:"कार्यप्रणाली",
        search:"कवरेज खोजें…", tagline:"देखिए भारत का मीडिया हर खबर को कैसे कवर करता है - हर पक्ष, आमने-सामने।",
        topNews:"मुख्य खबरें", osTitle:"कवरेज गैप",
        osSub:"कवरेज गैप वह ख़बर है जिसे स्पेक्ट्रम के एक तरफ़ के आउटलेट्स ने कवर किया पर दूसरी तरफ़ के बहुत कम या किसी ने नहीं। पक्ष हर झुकाव के अलग-अलग आउटलेट्स गिनकर इन्हें चिह्नित करता है - वही गिनती जो बायस बार में है - और हर एक पर पूरा वाम · केंद्र · दक्षिण आँकड़ा दिखाता है। यह अंकगणित है, किसी आउटलेट या कवरेज के कारण पर निर्णय नहीं। आउटलेट अलग-अलग मात्रा में प्रकाशित करते हैं, इसलिए एक तरफ़ कवरेज की अनुपस्थिति जानबूझकर की गई चूक के बजाय उस आउटलेट के प्रकाशन-आयतन को दर्शा सकती है।",
        gapLeftHead:"ज़्यादातर वाम-झुकाव आउटलेट्स द्वारा कवर", gapRightHead:"ज़्यादातर दक्षिण-झुकाव आउटलेट्स द्वारा कवर",
        gapShowing:"{total} में से {n} सबसे असंतुलित दिखाई जा रही हैं", gapCovered:"कवर किया गया:",
        m_gapH:"कवरेज गैप का ब्यौरा",
        m_gap:"पक्ष जिन {total} ख़बरों को एकतरफ़ा चिह्नित करता है, उनमें से {rh} ज़्यादातर दक्षिण-झुकाव आउटलेट्स ने और {lh} ज़्यादातर वाम-झुकाव आउटलेट्स ने कवर कीं। यह इस बात का माप नहीं है कि कौन-सा पक्ष ज़्यादा ख़बरें अनदेखा करता है। पक्ष भारत के स्पेक्ट्रम पर {lo} वाम-झुकाव और {ro} दक्षिण-झुकाव आउटलेट गिनता है, पर वे बहुत अलग मात्रा में प्रकाशित करते हैं - दक्षिण-झुकाव समूह में कई उच्च-आयतन टीवी और मास-मार्केट आउटलेट हैं, इसलिए दक्षिण-झुकाव आउटलेट सभी ख़बरों में लगभग दोगुनी बार दिखते हैं। इस असंतुलन का ज़्यादातर हिस्सा उस आयतन-अंतर को दर्शाता है, संपादकीय चयन को नहीं।",
        more:"और मुख्य खबरें", resultsFor:"खोज परिणाम:", noResults:"आपकी खोज से मेल खाती कोई खबर नहीं।",
        noResultsSub:"अलग शब्द आज़माएँ या मुख्य खबरें देखें।", noStories:"अभी दिखाने के लिए कोई खबर नहीं है। कृपया थोड़ी देर बाद देखें।",
        seeCoverage:"कवरेज देखें", most:"सबसे ज़्यादा कवरेज", even:"लगभग बराबर कवरेज", sources:"स्रोत", source:"स्रोत",
        onlyLabel:"केवल", back:"फ़ीड पर वापस", aiSummary:"पक्ष तटस्थ सारांश", aiSub:"तटस्थ संश्लेषण",
        autoTag:"स्वतः सारांश", autoFrom:"कवरेज से",
        autoNote:"यह शीर्षक सीधे कवरेज करने वाले एक आउटलेट से लिया गया है - पक्ष का तटस्थ सारांश तैयार किया जा रहा है।",
        unratedTitle:"बिना रेटिंग वाले आउटलेट", unratedNote:"ऐसे आउटलेट जो इस ख़बर को कवर कर रहे हैं पर अभी रेटेड नहीं हैं - ये कवरेज जोड़ते हैं पर बायस बार को प्रभावित नहीं करते।",
        intlTitle:"अंतरराष्ट्रीय कवरेज", intlNote:"इस ख़बर को कवर करने वाली विदेशी समाचार एजेंसियाँ (Reuters, AP, BBC…) - ये कवरेज जोड़ती हैं पर भारत के स्पेक्ट्रम पर रेटेड नहीं हैं, इसलिए बायस बार को प्रभावित नहीं करतीं।",
        framingTitle:"हर पक्ष इसे कैसे पेश कर रहा है", framingSub:"हर झुकाव की कवरेज किस बात पर ज़ोर दे रही है, इसका तटस्थ विश्लेषण - एकत्र की गई हेडलाइनों के आधार पर, राय नहीं।", framingPending:"इस ख़बर का पूरा सारांश तैयार होने पर पक्षों की तुलना यहाँ दिखाई देगी।",
        sideBySide:"आमने-सामने", coverageBreakdown:"कवरेज का ब्यौरा", totalSources:"कुल समाचार स्रोत",
        whereLean:"स्रोत किस ओर झुके हैं",
        aiNote:"झुकाव हर प्रकाशक का वर्णन करता है और पक्ष के संपादक तय करते हैं, हर खबर के लिए नहीं। सारांश आउटलेट्स की अपनी कवरेज से स्वचालित रूप से तैयार होते हैं; आँकड़े स्रोतों से आते हैं।",
        osCalloutBody1:"केवल", osCalloutBody2:"कवर करने वाले आउटलेट इस ओर झुके हैं - यह आउटलेट्स की गिनती है, इस बारे में निर्णय नहीं कि किसी पक्ष ने इसे क्यों कवर किया या नहीं।",
        srcTitle:"स्रोत रेटिंग", srcIntro:"पक्ष जिन आउटलेट्स को ट्रैक करता है, उनकी रेटिंग और कारण।",
        srcDisclaimer:"सभी रेटिंग अस्थायी हैं - रूब्रिक के विरुद्ध समीक्षित एक प्रलेखित शुरुआती बिंदु, अंतिम फ़ैसला नहीं। झुकाव प्रकाशन का वर्णन करता है, किसी एक लेख का नहीं, और अपील के लिए खुला है।",
        filterLean:"झुकाव", filterLang:"भाषा", langEN:"अंग्रेज़ी", langHI:"हिंदी", all:"सभी",
        ownership:"स्वामित्व", whyRated:"यह रेटिंग क्यों", signals:"संकेत", confidence:"विश्वास",
        contested:"विवादित", provisional:"अस्थायी", suggestFix:"सुधार सुझाएँ",
        methodTitle:"पक्ष कैसे काम करता है", m_doesH:"पक्ष क्या करता है",
        m_does:"पक्ष एक ही खबर की कवरेज को पूरे स्पेक्ट्रम के आउटलेट्स से इकट्ठा करता है, एक तटस्थ सारांश दिखाता है, और दिखाता है कि कौन-कौन से पक्ष इसे कवर कर रहे हैं - ताकि आप पूरी तस्वीर देख सकें और जान सकें कि आपके सामान्य स्रोत क्या छोड़ देते हैं।",
        m_ruleH:"मूल नियम",
        m_rule:"झुकाव का लेबल प्रकाशन का होता है, किसी एक लेख का नहीं, और कभी किसी एल्गोरिद्म का नहीं। पक्ष के संपादक एक निश्चित रूब्रिक से हर आउटलेट को झुकाव देते हैं। स्वचालित सारांश केवल कवरेज का वर्णन करता है; वह किसी की राजनीति तय नहीं करता। किसी खबर का बायस बार सीधा गणित है: हम गिनते हैं कि कवर करने वाले कितने आउटलेट किस ओर हैं। और यह एक-स्वामी-एक-वोट है: जब दो आउटलेट एक ही मूल कंपनी के हों - जैसे The Times of India और Navbharat Times, दोनों Times Group - तो वे अपने पक्ष में एक ही बार गिने जाते हैं, ताकि कोई एक कंपनी कई नामों से एक ही खबर छापकर बायस बार को झुका न सके। कवर करने वाला हर आउटलेट फिर भी दिखाया जाता है; बस उनका वोट एक साझा होता है।",
        m_rateH:"हम किसी प्रकाशन को कैसे आँकते हैं",
        m_rateLede:"हम हर प्रकाशन को छह संकेतों पर आँकते हैं, हर एक को −2 से +2 तक अंक देकर एक स्कोर में जोड़ा जाता है, −10 (वाम) से +10 (दक्षिण):",
        m_rateFoot:"शून्य के पास के स्कोर केंद्र हैं; शून्य से जितना दूर, झुकाव उतना मज़बूत।",
        m_axisH:"भारत में “वाम” और “दक्षिण” का अर्थ",
        m_axis:"भारत में वाम और दक्षिण केवल अर्थशास्त्र के बारे में नहीं हैं। पक्ष एक सामाजिक-वैचारिक अक्ष (धर्मनिरपेक्ष ↔ हिंदुत्व) को एक संस्थागत अक्ष (सत्ता के आलोचक ↔ सत्ता के साथ) के साथ जोड़ता है, और आर्थिक रुख को अलग से देखता है। “वाम” और “दक्षिण” वर्णनात्मक हैं, अपमान नहीं - और एक ही कसौटी पूरे स्पेक्ट्रम पर लागू होती है।",
        m_partiesH:"भारत की पार्टियाँ मोटे तौर पर कहाँ हैं",
        m_parties:"ये लेबल विचारों का वर्णन करते हैं, टीमों का नहीं - और ये मोटे अनुमान हैं, क्योंकि पार्टियाँ समय के साथ बदलती हैं और कई क्षेत्रीय पार्टियाँ किसी एक रेखा पर ठीक से नहीं बैठतीं। आम समझ के अनुसार: वाम में CPI(M) और CPI जैसी कम्युनिस्ट और समाजवादी पार्टियाँ आती हैं, जो धर्मनिरपेक्ष और कल्याण-समर्थक, श्रमिक-पहले रुख से जुड़ी हैं; दक्षिण - सबसे प्रमुख रूप से भाजपा - हिंदुत्व-प्रभावित सांस्कृतिक राष्ट्रवाद और अधिक बाज़ार-समर्थक आर्थिक रुख से जुड़ी है; केंद्र बीच में फैला है, जहाँ कांग्रेस को अक्सर केंद्र-वाम कहा जाता है और कई क्षेत्रीय पार्टियाँ मुद्दे के हिसाब से रुख मिलाती हैं। याद रखें: पक्ष समाचार आउटलेट्स को आँकता है, पार्टियों को नहीं - किसी आउटलेट का झुकाव इस बारे में है कि वह खबरों को कैसे कवर करता है, इस बारे में नहीं कि वह किसे वोट देता है।",
        m_provH:"विश्वास, विवादित और अस्थायी",
        m_prov:"आज हर रेटिंग अस्थायी है: स्वामित्व, स्व-घोषित रुख और स्थापित प्रतिष्ठा पर आधारित एक प्रलेखित शुरुआती बिंदु, रूब्रिक के विरुद्ध समीक्षित - अंतिम फ़ैसला नहीं। हर एक के साथ एक विश्वास-स्तर दिखता है, और कुछ को ‘विवादित’ चिह्नित किया गया है जहाँ झुकाव सचमुच बहस में है या स्वामित्व हाल में बदला है।",
        m_readH:"पक्ष की खबर कैसे पढ़ें", m_appealH:"सुधार और अपील",
        m_appeal:"लगता है कोई रेटिंग ग़लत है? हमें आउटलेट, जिस रेटिंग से असहमत हैं, और कुछ ठोस उदाहरण - हेडलाइन या लेख - बताएँ, और हम उसे रूब्रिक के विरुद्ध फिर से देखेंगे। रेटिंग्स को चुनौती देने के लिए ही हैं।",
        footIndependence:"पक्ष एक स्वतंत्र परियोजना है और किसी दिखाए गए आउटलेट से संबद्ध नहीं है। झुकाव के लेबल अस्थायी हैं और अपील के लिए खुले हैं।",
      }
    };

    /* ---------------- helpers ---------------- */
    const imgFor = (hue) => {
      const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='480' height='300'><defs><linearGradient id='a' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='hsl(${hue} 36% 44%)'/><stop offset='1' stop-color='hsl(${(hue+38)%360} 42% 19%)'/></linearGradient><radialGradient id='b' cx='28%' cy='22%' r='65%'><stop offset='0' stop-color='rgba(255,255,255,0.30)'/><stop offset='1' stop-color='rgba(255,255,255,0)'/></radialGradient></defs><rect width='480' height='300' fill='url(%23a)'/><rect width='480' height='300' fill='url(%23b)'/></svg>`;
      return `data:image/svg+xml,${encodeURIComponent(svg)}`;
    };
    const hueOf = (s) => { let h=0; for (const c of String(s||"")) h=(h*31+c.charCodeAt(0))%360; return h; };
    const biasPct = (lc) => { const tot=(lc.left+lc.center+lc.right)||1; return {left:Math.round(lc.left/tot*100), center:Math.round(lc.center/tot*100), right:Math.round(lc.right/tot*100)}; };
    const dominant = (b) => { const k=Object.keys(b).sort((x,y)=>b[y]-b[x])[0]; return {side:k, pct:b[k]}; };
    const lbl = (side, lang) => BIAS[side][lang] || BIAS[side].en;
    const confName = (c, lang) => (({en:{low:"Low",medium:"Medium",high:"High"},hi:{low:"कम",medium:"मध्यम",high:"उच्च"}}[lang])||{})[c] || c;

    let _mode;
    function detectMode(){ if(!_mode) _mode=(async()=>{ try{ const r=await fetch("/api/topics"); if(r.ok && (r.headers.get("content-type")||"").includes("json")) return "api"; }catch(e){} return "static"; })(); return _mode; }
    async function apiGet(res){ if(await detectMode()==="api"){ const r=await fetch("/api/"+res); if(r.ok && (r.headers.get("content-type")||"").includes("json")) return r.json(); } const r=await fetch("/data/"+res+".json?t="+Date.now()); if(!r.ok) throw new Error(res); const ct=(r.headers.get("content-type")||""); if(!ct.includes("json")) throw new Error("not-json:"+res); return r.json(); }
    async function loadAll(){
      try { const [e,b,tp,sr]=await Promise.all([apiGet("events"),apiGet("blindspots"),apiGet("topics"),apiGet("sources")]);
        return {events:e.events||[], blindspots:b.events||[], gaps:{left:b.left_heavier||[], right:b.right_heavier||[], agg:b.aggregate||{}}, topics:tp.topics||[], sources:sr.sources||[], summary:sr.summary||{}}; }
      catch(err){ console.error(err); return {events:[],blindspots:[],gaps:{left:[],right:[],agg:{}},topics:[],sources:[],summary:{}}; }
    }

    const toCard = (e, lang) => {
      const lc = e.lean_counts || {left:0,center:0,right:0};
      return { id:e.id, topic:e.topic, region:e.region||"India", srclang:e.lang||"en", created_at:e.created_at,
        headline:(lang==="hi"&&e.title_hi)?e.title_hi:e.title,
        lead:(lang==="hi"&&e.summary_hi)?e.summary_hi:e.summary,
        summary:(lang==="hi"&&e.summary_points_hi&&e.summary_points_hi.length)?e.summary_points_hi:(e.summary_points||[]),
        bias:biasPct(lc), counts:lc, sources:(lc.left+lc.center+lc.right)||e.total_sources||0,
        international:(e.international||0),
        importance:(typeof e.importance==="number"?e.importance:0),
        unrated:Math.max(0,(e.source_count||0)-(lc.left+lc.center+lc.right)-(e.international||0)),
        blindspot:e.blindspot?e.blindspot.side:null,
        auto:e.summary_method==="extractive",
        img:e.image_url||"",
        image:e.image_url||imgFor(hueOf(e.topic||e.title)) };
    };
    const toDetail = (e, lang) => { const c=toCard(e,lang);
      c.coverage=e.coverage||{}; c.outlets=e.sources||[];
      c.framing=(lang==="hi"&&e.framing_hi&&Object.keys(e.framing_hi).length)?e.framing_hi:(e.framing||{});
      return c; };

    const isHi = (lang) => lang==="hi" ? "deva" : "";
    // Reading text is serif in BOTH scripts: Source Serif 4 (Latin) / Tiro Devanagari
    // Hindi (with extra leading). Chrome/labels keep isHi() -> "deva" (Plex Devanagari).
    const readCls = (lang) => lang==="hi" ? "read-hi" : "serif";





    /* ---------------- extra icons ---------------- */
    const ArrowUpRight=(p)=><svg width={p.size||24} height={p.size||24} className={p.className||""} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M7 17 17 7M7 7h10v10"/></svg>;
    const Compass=(p)=><svg width={p.size||24} height={p.size||24} className={p.className||""} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><polygon points="16.2 7.8 14.1 14.1 7.8 16.2 9.9 9.9"/></svg>;
    const Globe=(p)=><svg width={p.size||24} height={p.size||24} className={p.className||""} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15 15 0 0 1 4 10 15 15 0 0 1-4 10 15 15 0 0 1-4-10 15 15 0 0 1 4-10Z"/></svg>;
    const Clock=(p)=><svg width={p.size||24} height={p.size||24} className={p.className||""} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 7v5l3 2"/></svg>;
    const LinkIcon=(p)=><svg width={p.size||24} height={p.size||24} className={p.className||""} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"/><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/></svg>;
    const Check=(p)=><svg width={p.size||24} height={p.size||24} className={p.className||""} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5"/></svg>;

    /* ---------------- helpers ---------------- */
    const _ts=(iso)=>{ if(!iso) return NaN; let x=(""+iso).replace(" ","T"); if(!/[zZ]|[+\-]\d\d:?\d\d$/.test(x)) x+="Z"; return Date.parse(x); };
    const timeAgo=(iso,lang)=>{ const ts=_ts(iso); if(isNaN(ts)) return ""; const m=Math.max(0,(Date.now()-ts)/60000); const hi=lang==="hi";
      if(m<60) return hi?`${Math.round(m)} मिनट पहले`:`${Math.round(m)}m ago`;
      const h=m/60; if(h<24) return hi?`${Math.round(h)} घंटे पहले`:`${Math.round(h)}h ago`;
      const d=Math.round(h/24); return hi?`${d} दिन पहले`:`${d}d ago`; };
    const domSide=(bias)=>["left","center","right"].reduce((a,b)=>(bias[b]||0)>(bias[a]||0)?b:a,"left");
    const tword=(lang)=> (n)=> n===1?STR[lang].source:STR[lang].sources;
    const covLine=(story,lang)=>{ const d=domSide(story.bias); const tot=story.sources+(story.unrated||0)+(story.international||0); return `${story.bias[d]}% ${lbl(d,lang)} · ${tot} ${tot===1?STR[lang].source:STR[lang].sources}`; };
    // Newspaper count line: raw distinct-outlet counts L · C · R, plus n and age. Reads
    // straight from the real per-lean counts (never a hardcoded ratio).
    const countLine=(story,lang)=>{ const c=story.counts||{}; const L=c.left||0,C=c.center||0,R=c.right||0; const n=L+C+R; const ta=timeAgo(story.created_at,lang); return `${L} · ${C} · ${R}   n=${n}${ta?" · "+ta:""}`; };

    function Thumb({ src, topic, title, ratio, t, lang, className }) {
      const [err,setErr]=useState(false);
      const real=src && !err;
      const tp=lang==="hi"?(TOPIC_HI[topic]||topic):(topic||"News");
      return (
        <div className={`relative overflow-hidden ${t.soft} ${className||""}`} style={{aspectRatio:ratio||"16 / 9"}}>
          {real
            ? <img src={src} alt="" loading="lazy" decoding="async" onError={()=>setErr(true)} className="absolute inset-0 h-full w-full object-cover" />
            : <div className="absolute inset-0 flex items-center justify-center">
                <span className={`mono text-[11px] font-semibold uppercase tracking-[0.16em] ${t.tf} ${lang==="hi"?"deva":""}`}>{tp}</span>
              </div>}
        </div>
      );
    }
    function OutletAvatar({ o, side, size }) {
      const [err,setErr]=useState(false);
      let host=""; try{ host=new URL(o.url).hostname.replace(/^www\./,""); }catch(e){}
      const s=size||26; const ring=side==="unrated"?"#B8B4AC":((BIAS[side]&&BIAS[side].color)||"#8A8F98");
      if(err||!host) return <span className="grid shrink-0 place-items-center rounded-md mono font-semibold text-white" style={{width:s,height:s,fontSize:s*0.42,backgroundColor:ring}}>{(o.source||"?")[0]}</span>;
      return <span className="grid shrink-0 place-items-center rounded-md bg-white" style={{width:s,height:s,boxShadow:`0 0 0 1.5px ${ring}`}}><img src={`https://www.google.com/s2/favicons?domain=${host}&sz=64`} alt="" width={s*0.62} height={s*0.62} loading="lazy" onError={()=>setErr(true)} className="object-contain"/></span>;
    }

    /* ---------------- bias bars ---------------- */
    // The signature instrument. Segment sizes come STRAIGHT from live counts
    // (flexGrow = bias%, itself computed from the distinct-outlet L/C/R totals) — never
    // hardcoded. Each side is textured (solid / 45deg hatch / vertical rule), separated by
    // a 1px paper gap, inside a hairline ink frame, with a fixed centre axis so skew is
    // judged against a constant. min-width 2px keeps a lone outlet visible. No animation.
    function BiasSegments({ bias, t, h, onPick, active, lang }) {
      const present=["left","center","right"].filter(k=>(bias[k]||0)>0);
      return (
        <div className="relative flex w-full" style={{height:h,border:`1px solid ${t.ink}`,background:t.track||"#EAE6DB"}}>
          {present.map((k,i)=>(
            <React.Fragment key={k}>
              {i>0 && <div style={{flex:"0 0 1px",background:t.gap||"#F4F1EA"}}/>}
              {onPick
                ? <button onClick={(e)=>{e.stopPropagation();e.preventDefault();onPick(k);}} aria-label={lbl(k,lang||"en")}
                    className={`${BIAS[k].tex} cursor-pointer hover:brightness-110 ${active&&active!==k?"opacity-40":""}`}
                    style={{flexGrow:bias[k],flexBasis:0,minWidth:2,border:0,padding:0}}/>
                : <div className={BIAS[k].tex} style={{flexGrow:bias[k],flexBasis:0,minWidth:2}}/>}
            </React.Fragment>
          ))}
          <div style={{position:"absolute",left:"50%",top:-3,bottom:-3,width:1,background:t.ink}}/>
        </div>
      );
    }
    function MiniBar({ bias, t }) { return <BiasSegments bias={bias} t={t} h={10} />; }
    // Larger bar. Pass `counts` (real L/C/R outlet counts) to print the label row + n above,
    // exactly like the design's story-page instrument.
    function BiasBar({ bias, t, lang, onPick, active, height, counts, showN, showScale }) {
      const h=height||26;
      const total=counts?["left","center","right"].reduce((s,k)=>s+(counts[k]||0),0):0;
      return (
        <div>
          {counts && (
            <div className="mb-2 flex items-baseline justify-between gap-3">
              <div className={`flex flex-wrap gap-x-4 gap-y-1 text-[10.5px] font-medium uppercase tracking-[0.1em] ${t.tp} ${lang==="hi"?"deva":""}`}>
                {["left","center","right"].map(k=>(counts[k]||0)>0 && <span key={k}>{lbl(k,lang)} <span className="mono" style={{letterSpacing:0}}>{counts[k]}</span></span>)}
              </div>
              {showN!==false && total>0 && <span className={`mono text-[10.5px] ${t.tf}`}>n = {total}</span>}
            </div>
          )}
          <BiasSegments bias={bias} t={t} h={h} onPick={onPick} active={active} lang={lang} />
          {showScale && (
            <div className="relative" style={{height:14,marginTop:3}}>
              {[25,50,75].map(p=><div key={p} style={{position:"absolute",left:p+"%",top:0,width:1,height:p===50?6:4,background:p===50?t.ink:t.line}}/>)}
              <span className={`mono text-[9px] ${t.tf}`} style={{position:"absolute",left:"50%",top:6,transform:"translateX(-50%)",whiteSpace:"nowrap"}}>{lang==="hi"?"कवरेज का 50%":"50% of coverage"}</span>
            </div>
          )}
        </div>
      );
    }
    // Coverage-gap viz: three EQUAL-WIDTH columns, bar height proportional to that side's
    // count, an absent side drawn as the dashed hatch — so absence takes as much room as
    // presence. Driven only by the same L/C/R distinct-outlet counts as the bias bar.
    function GapColumns({ counts, t, lang }) {
      const ks=["left","center","right"];
      const mx=Math.max(1,...ks.map(k=>counts[k]||0));
      return (
        <div className="grid grid-cols-3 gap-1.5">
          {ks.map(k=>{ const n=counts[k]||0; const pct=Math.round(n/mx*100);
            return (
              <div key={k}>
                <div className="flex items-end" style={{height:34,border:`1px solid ${t.ink}`,background:t.track||"#EAE6DB"}}>
                  {n>0 ? <div className={`w-full ${BIAS[k].tex}`} style={{height:`${Math.max(8,pct)}%`}}/>
                       : <div className="seg-absent w-full h-full"/>}
                </div>
                <div className={`mt-1.5 text-[9.5px] font-medium uppercase tracking-[0.1em] ${t.tp} ${lang==="hi"?"deva":""}`}>{lbl(k,lang)}</div>
                <div className="mono text-[10.5px]" style={{color:n>0?t.ink:"#75442E"}}>{n}</div>
              </div>
            );
          })}
        </div>
      );
    }
    const LeanBadge=({ side, lang, t })=> side==="unrated"
      ? <span className={`shrink-0 rounded mono px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${t.chip} ${t.tf}`}>{lang==="hi"?"अनरेटेड":"Unrated"}</span>
      : <span className="shrink-0 rounded mono px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white" style={{backgroundColor:BIAS[side].color}}>{lbl(side,lang)}</span>;
    function AutoTag({ lang, t }) { return <span className={`inline-flex items-center gap-1 rounded mono px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${t.chip} ${t.tf}`}>{STR[lang].autoTag}</span>; }
    function Eyebrow({ topic, created_at, blindspot, t, lang }) {
      const tp=lang==="hi"?(TOPIC_HI[topic]||topic):topic; const face=lang==="hi"?"deva":"mono";
      return (
        <div className={`flex flex-wrap items-center gap-x-2 gap-y-1 ${face} text-[11px] font-medium uppercase tracking-[0.1em]`}>
          <span className={t.ts}>{tp||"News"}</span>
          {created_at && <><span className={t.tf}>·</span><span className={t.tf}>{timeAgo(created_at,lang)}</span></>}
          {blindspot && <><span className={t.tf}>·</span><span className={t.blind}>{STR[lang].navOS}</span></>}
        </div>
      );
    }
    function SectionTitle({ children, t, lang, right }) {
      return (
        <div className={`mb-4 flex items-baseline justify-between gap-3 border-b pb-2 ${t.border}`}>
          <h2 className={`headline text-[15px] font-bold uppercase tracking-[0.08em] ${t.tp} ${isHi(lang)}`}>{children}</h2>
          {right}
        </div>
      );
    }

    /* ---------------- feed pieces (newspaper hierarchy) ---------------- */
    // A dated masthead sub-strip: today's date + how many outlets Paksh tracks.
    // The dated strip under the masthead: a 2px rule over a 1px rule (design 2a), carrying
    // the edition toggle + today's date on the left, the live tally in the centre, and the
    // freshness on the right. Every number is real (homeCards / sources / gaps / newest event).
    function DateStrip({ t, lang, stats, regionFilter, setRegionFilter }) {
      const today=new Date().toLocaleDateString(lang==="hi"?"hi-IN":"en-IN",{weekday:"long",year:"numeric",month:"long",day:"numeric"});
      const upd=stats.updated?timeAgo(stats.updated,lang):"";
      const ls=lang==="hi"?0:".14em";
      const eb=`eyebrow ${lang==="hi"?"deva":""}`;
      const region=(k,label)=>(
        <button onClick={()=>setRegionFilter&&setRegionFilter(k)} className={`${eb} ${regionFilter===k?t.tp:`${t.tf} hover:${t.tp}`}`} style={{letterSpacing:ls}}>{label}</button>
      );
      const tally=lang==="hi"
        ? `${stats.stories} ख़बरें · ${stats.outlets} स्रोत · ${stats.gaps} कवरेज गैप`
        : `${stats.stories} stories · ${stats.outlets} outlets tracked · ${stats.gaps} coverage gaps`;
      return (
        <div className="flex items-center justify-between gap-4 py-[7px]" style={{borderTop:`2px solid ${t.ink}`,borderBottom:`1px solid ${t.ink}`}}>
          <div className="flex items-center gap-3 sm:gap-4 min-w-0">
            {region("National", ui("National",lang))}
            {region("International", ui("International",lang))}
            <span className={`hidden md:inline ${eb} ${t.tf}`} style={{letterSpacing:ls}}>{today}</span>
          </div>
          <span className={`hidden sm:inline ${eb} ${t.tf} truncate`} style={{letterSpacing:ls}}>{tally}</span>
          <span className={`${eb} ${t.tf} shrink-0`} style={{letterSpacing:ls}}>{upd?(lang==="hi"?`अपडेट ${upd}`:`Updated ${upd}`):today}</span>
        </div>
      );
    }
    // LEAD — the most-covered story of the moment, given the largest type + full bias
    // instrument with the printed scale. Text-forward; a single 2:1 image if one exists.
    // LEAD — the single most-covered story, at 54px on desktop / 31px on mobile: the one
    // dominant moment that gives the eye somewhere to land (design 2a/2c). Text-forward,
    // no image. The bias block sits beside the lead paragraph on desktop, below on mobile;
    // every count/width is live (BiasSegments flex-grow = bias%, computed from L/C/R owners).
    function LeadStory({ story, t, lang, onOpen }) {
      const c=story.counts||{left:0,center:0,right:0};
      const L=c.left||0,C=c.center||0,R=c.right||0,n=L+C+R;
      const b=story.bias||{left:0,center:0,right:0};
      const tp=lang==="hi"?(TOPIC_HI[story.topic]||story.topic):story.topic;
      return (
        <a href={"/story/"+encodeURIComponent(story.id)} onClick={e=>{ if(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return; e.preventDefault(); onOpen(story.id); }} className="block no-underline group cursor-pointer">
          <div className={`eyebrow ${lang==="hi"?"deva":""}`} style={{color:BIAS.right.color,letterSpacing:lang==="hi"?0:".14em"}}>{lang==="hi"?"आज सबसे ज़्यादा कवरेज":"Most covered today"}{tp?` · ${tp}`:""}</div>
          <h2 className={`headline mt-3 text-[31px] sm:text-[42px] lg:text-[54px] ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-4`} style={{lineHeight:lang==="hi"?1.14:1.06,letterSpacing:lang==="hi"?0:"-0.022em",textWrap:"balance"}}>{story.headline}</h2>
          <div className="mt-5 grid gap-6 lg:grid-cols-[1fr_250px] lg:gap-8">
            {story.lead && <p className={`text-[16px] lg:text-[17.5px] ${t.ts} ${readCls(lang)} lc-4`} style={{lineHeight:lang==="hi"?1.85:1.6,textWrap:"pretty"}}>{story.lead}</p>}
            <div>
              <div className={`mb-2 flex justify-between text-[10px] font-medium uppercase tracking-[0.1em] ${t.tp} ${lang==="hi"?"deva":""}`}>
                {["left","center","right"].map(k=>(<span key={k}>{lang==="hi"?BIAS[k].hi:BIAS[k].en.charAt(0)} <span className="mono" style={{letterSpacing:0}}>{c[k]||0}</span></span>))}
              </div>
              <BiasSegments bias={b} t={t} h={28} lang={lang} />
              <div className={`mt-2 mono text-[10.5px] ${t.tf}`}>n = {n} · {b.left} / {b.center} / {b.right}%</div>
              <div className={`mt-3 text-[11px] font-medium uppercase tracking-[0.06em] ${t.tp} ${lang==="hi"?"deva":""}`}><span style={{borderBottom:`1px solid ${t.ink}`,paddingBottom:2}}>{lang==="hi"?"सभी पक्ष पढ़ें":"Read all sides"} →</span></div>
            </div>
          </div>
        </a>
      );
    }
    // SECONDARY — the middle tier: a real headline + a taste of the lead + a compact bias bar.
    function SecondaryStory({ story, t, lang, onOpen }) {
      return (
        <a href={"/story/"+encodeURIComponent(story.id)} onClick={e=>{ if(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return; e.preventDefault(); onOpen(story.id); }} className={`block no-underline group cursor-pointer border-b py-5 ${t.border}`}>
          <Eyebrow topic={story.topic} created_at={story.created_at} blindspot={story.blindspot} t={t} lang={lang} />
          <h3 className={`headline mt-1.5 text-[20px] sm:text-[21px] leading-[1.24] lc-2 ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`}>{story.headline}</h3>
          {story.lead && <p className={`mt-2 text-[14px] leading-[1.55] lc-2 ${t.ts} ${readCls(lang)}`}>{story.lead}</p>}
          <div className="mt-3"><BiasBar bias={story.bias} t={t} lang={lang} height={11} /></div>
          <div className={`mt-1.5 mono text-[11px] ${t.tf} ${lang==="hi"?"deva":""}`}>{countLine(story,lang)}</div>
        </a>
      );
    }
    // DENSE — the tail: a compact headline row with a mini bias bar. High information density.
    function DenseRow({ story, t, lang, onOpen, last }) {
      return (
        <a href={"/story/"+encodeURIComponent(story.id)} onClick={e=>{ if(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return; e.preventDefault(); onOpen(story.id); }} className={`block no-underline group cursor-pointer ${last?"":"border-b"} py-3.5 ${t.border}`}>
          <h4 className={`headline text-[16px] sm:text-[17.5px] leading-[1.24] lc-2 ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`}>{story.headline}</h4>
          <div className="mt-2 flex items-center gap-3">
            <div className="w-24 sm:w-28 shrink-0"><MiniBar bias={story.bias} t={t} /></div>
            <span className={`mono text-[10.5px] ${t.tf} ${lang==="hi"?"deva":""}`}>{countLine(story,lang)}</span>
          </div>
        </a>
      );
    }
    // SPECTRUM RAIL — an aggregate of the visible feed: total distinct-outlet coverage by
    // side. Pure arithmetic over the same per-lean counts; never a hardcoded ratio.
    // SPECTRUM RAIL — an aggregate of the visible feed: each side's SHARE of total
    // distinct-outlet coverage today. Pure arithmetic over the same per-lean counts as
    // the bias bars; never a hardcoded ratio. Rail-style (no card) per design 2a.
    function SpectrumRail({ cards, t, lang }) {
      const agg={left:0,center:0,right:0};
      cards.forEach(c=>{ const k=c.counts||{}; agg.left+=k.left||0; agg.center+=k.center||0; agg.right+=k.right||0; });
      const sum=Math.max(1,agg.left+agg.center+agg.right);
      return (
        <div>
          <div className={`eyebrow pb-2 ${t.tp} ${lang==="hi"?"deva":""}`} style={{borderBottom:`1px solid ${t.ink}`,letterSpacing:lang==="hi"?0:".14em"}}>{lang==="hi"?"आज का स्पेक्ट्रम":"The spectrum today"}</div>
          <div className="mt-3.5 flex flex-col gap-2.5">
            {["left","center","right"].map(k=>(
              <div key={k}>
                <div className="mb-1.5 flex items-center justify-between">
                  <span className={`text-[10px] font-medium uppercase tracking-[0.1em] ${t.ts} ${lang==="hi"?"deva":""}`}>{lbl(k,lang)}</span>
                  <span className="mono text-[11px]" style={{color:t.ink}}>{agg[k]}</span>
                </div>
                <div style={{height:7,background:t.track||"#E1DCCE",border:`1px solid ${t.line}`}}><div className={BIAS[k].tex} style={{width:`${Math.round(agg[k]/sum*100)}%`,height:"100%"}}/></div>
              </div>
            ))}
          </div>
          <div className={`mt-2.5 mono text-[10px] ${t.tf} ${lang==="hi"?"deva":""}`}>{lang==="hi"?"आज प्रति पक्ष ख़बरें":"Stories run per side, today"}</div>
        </div>
      );
    }
    function FeedRow({ story, t, lang, onOpen }) {
      return (
        <a href={"/story/"+encodeURIComponent(story.id)} onClick={e=>{ if(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return; e.preventDefault(); onOpen(story.id); }} className={`no-underline group flex cursor-pointer gap-4 border-b pb-6 ${t.border}`}>
          <div className="min-w-0 flex-1">
            <Eyebrow topic={story.topic} created_at={story.created_at} blindspot={story.blindspot} t={t} lang={lang} />
            <h3 className={`headline mt-1.5 text-lg sm:text-xl leading-[1.18] lc-3 ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`}>{story.headline}</h3>
            <div className="mt-2.5 flex items-center gap-3">
              <div className="w-28 sm:w-36"><MiniBar bias={story.bias} t={t} /></div>
              <span className={`mono text-[11px] ${t.tf} ${lang==="hi"?"deva":""}`}>{covLine(story,lang)}</span>
            </div>
          </div>
          {story.img && <div className="shrink-0"><Thumb src={story.img} topic={story.topic} title={story.headline} ratio="1 / 1" t={t} lang={lang} className="w-24 sm:w-32 rounded-md" /></div>}
        </a>
      );
    }
    function BriefItem({ story, t, lang, onOpen, last }) {
      return (
        <button onClick={()=>onOpen(story.id)} className={`block w-full text-left ${last?"":"border-b"} py-3 ${t.border}`}>
          <h4 className={`headline text-[15px] font-semibold leading-[1.2] lc-2 ${t.tp} ${readCls(lang)} hover:underline decoration-1 underline-offset-2`}>{story.headline}</h4>
          <div className="mt-2 flex items-center gap-2">
            <div className="w-16"><MiniBar bias={story.bias} t={t} /></div>
            <span className={`mono text-[10px] ${t.tf} ${lang==="hi"?"deva":""}`}>{covLine(story,lang)}</span>
          </div>
        </button>
      );
    }
    function BlindspotCard({ story, t, lang, onOpen }) {
      const c=story.counts||{left:0,center:0,right:0}; const L=c.left||0, C=c.center||0, R=c.right||0;
      const covered = lang==="hi" ? `${L} वाम · ${C} केंद्र · ${R} दक्षिण` : `${L} Left · ${C} Centre · ${R} Right`;
      return (
        <a href={"/story/"+encodeURIComponent(story.id)} onClick={e=>{ if(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return; e.preventDefault(); onOpen(story.id); }} className={`block no-underline group cursor-pointer border ${t.surface} ${t.border}`} style={{borderLeft:"3px solid #8D5B44"}}>
          <div className="p-4">
            <div className={`mono text-[10px] font-medium uppercase tracking-[0.14em] ${t.blind} ${lang==="hi"?"deva":""}`}>{STR[lang].navOS}</div>
            <h3 className={`headline mt-2 text-[17px] leading-[1.24] lc-3 ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`}>{story.headline}</h3>
            <div className="mt-3"><GapColumns counts={c} t={t} lang={lang} /></div>
            <div className={`mt-2.5 mono text-[11px] ${t.tf} ${lang==="hi"?"deva":""}`}>{STR[lang].gapCovered} {covered}</div>
          </div>
        </a>
      );
    }
    function GridCard({ story, t, lang, onOpen }) {
      return (
        <a href={"/story/"+encodeURIComponent(story.id)} onClick={e=>{ if(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return; e.preventDefault(); onOpen(story.id); }} className={`block no-underline group cursor-pointer overflow-hidden rounded-lg border ${t.surface} ${t.border}`}>
          {story.img && <Thumb src={story.img} topic={story.topic} title={story.headline} ratio="16 / 9" t={t} lang={lang} />}
          <div className="p-4">
            <Eyebrow topic={story.topic} created_at={story.created_at} blindspot={story.blindspot} t={t} lang={lang} />
            <h3 className={`headline mt-1.5 text-[17px] leading-[1.2] lc-3 ${t.tp} ${readCls(lang)}`}>{story.headline}</h3>
            <div className="mt-3"><MiniBar bias={story.bias} t={t} /></div>
            <div className={`mt-2 mono text-[11px] ${t.tf} ${lang==="hi"?"deva":""}`}>{covLine(story,lang)}</div>
          </div>
        </a>
      );
    }

    /* ---------------- shell ---------------- */
    function RegionSelect({ region, setRegion, t, lang }) {
      const states = ["Maharashtra", "Uttar Pradesh", "Karnataka", "Tamil Nadu", "Delhi", "Gujarat", "West Bengal"];
      return (
        <div className="relative shrink-0">
          <select value={region} onChange={e=>setRegion(e.target.value)} className={`appearance-none rounded-full border px-3 py-1 pl-3 pr-7 text-[12.5px] font-medium ${t.border} ${t.ts} hover:${t.soft} bg-transparent outline-none cursor-pointer ${lang==="hi"?"deva":""} transition-all duration-200`}>
            <option value="National">{ui("National", lang)}</option>
            <option value="International">{ui("International", lang)}</option>
            <optgroup label={lang==="hi"?"राज्य (जल्द आ रहे हैं)":"States (Pending)"}>
              {states.map(s=><option key={s} value={s} disabled>{s}</option>)}
            </optgroup>
          </select>
          <div className={`pointer-events-none absolute inset-y-0 right-2 flex items-center ${t.tf}`}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6"/></svg>
          </div>
        </div>
      );
    }

    function UtilityStrip({ t, lang, setLang, dark, setDark }) {
      const today=new Date().toLocaleDateString(lang==="hi"?"hi-IN":"en-IN",{weekday:"long",year:"numeric",month:"long",day:"numeric"});
      return (
        <div style={{backgroundColor:"#15140F"}} className="text-white/85">
          <div className="mx-auto flex max-w-[1800px] items-center justify-between px-4 sm:px-5" style={{height:34}}>
            <span className="mono text-[11px] tracking-wide text-white/55">{lang==="hi"?"भारत संस्करण":"India Edition"}</span>
            <div className="flex items-center gap-4">
              <span className={`hidden sm:inline mono text-[11px] text-white/55 ${lang==="hi"?"deva":""}`}>{today}</span>
              <div className="flex items-center gap-1">
                {["en","hi"].map(l=>(<button key={l} onClick={()=>setLang(l)} className={`px-1.5 mono text-[11px] font-semibold ${lang===l?"text-white underline underline-offset-4":"text-white/50 hover:text-white/80"} ${l==="hi"?"deva":""}`}>{l==="en"?"EN":"हिं"}</button>))}
              </div>
              <button onClick={()=>setDark(!dark)} className="text-white/55 hover:text-white" aria-label="Theme">{dark?<Sun size={15}/>:<Moon size={15}/>}</button>
            </div>
          </div>
        </div>
      );
    }
    // Language switch — the design's bordered EN/हिं toggle. Active side fills with ink,
    // inactive stays paper. 44px tap target on mobile. No caps on Devanagari.
    function LangToggle({ t, lang, setLang, dark }) {
      return (
        <span className="flex" style={{border:`1px solid ${t.ink}`}}>
          {["en","hi"].map(l=>{ const on=lang===l;
            return (
              <button key={l} onClick={()=>setLang(l)} aria-label={l==="en"?"English":"हिन्दी"}
                className={`flex items-center justify-center ${l==="hi"?"deva":""}`}
                style={{minWidth:40,minHeight:30,padding:"0 11px",
                  font:l==="en"?"500 11px/1 'IBM Plex Sans',sans-serif":"400 14px/1 'IBM Plex Sans Devanagari',sans-serif",
                  letterSpacing:l==="en"?".1em":0,
                  background:on?t.ink:"transparent", color:on?(dark?"#201F1C":"#F4F1EA"):t.ink}}>
                {l==="en"?"EN":"हिं"}
              </button>
            );
          })}
        </span>
      );
    }
    // Masthead — brand, inline nav with a 2px active underline, search as an icon, the
    // language toggle, and the theme switch. Ink-on-paper, hairline rule below; no dark
    // utility strip, no topic-chip rail (design spec 2a).
    function Header({ t, lang, setLang, dark, setDark, go, view }) {
      const NAV=[["home",STR[lang].navTop],["blindspot",STR[lang].navOS],["topics",ui("sections",lang)],["about",STR[lang].navMethod]];
      return (
        <div className={`sticky top-0 z-40 border-b ${t.border} ${t.nav}`}>
          <div className="mx-auto max-w-[1280px] px-4 sm:px-10">
            <div className="flex h-[58px] items-center gap-6">
              <button onClick={()=>go("home")} className="flex shrink-0 items-baseline gap-2" aria-label="Paksh home">
                <span className={`brand-hi text-[27px] leading-none ${t.tp}`}>पक्ष</span>
                <span className={`text-[17px] font-semibold uppercase tracking-[0.30em] ${t.tp}`}>Paksh</span>
              </button>
              <nav className="ml-1 hidden items-center gap-6 md:flex">
                {NAV.map(([k,label])=>(
                  <button key={k} onClick={()=>go(k)} className={`eyebrow relative py-1 ${view===k?t.tp:`${t.tf} hover:${t.tp}`} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>
                    {label}{view===k && <span className="absolute -bottom-[3px] left-0 right-0" style={{height:2,background:t.ink}}/>}
                  </button>
                ))}
              </nav>
              <div className="ml-auto flex items-center gap-3 sm:gap-4">
                <button onClick={()=>go("search")} aria-label="Search" className={`${t.tf} hover:${t.tp}`}><Search size={17}/></button>
                <LangToggle t={t} lang={lang} setLang={setLang} dark={dark} />
                <button onClick={()=>setDark(!dark)} className={`${t.tf} hover:${t.tp}`} aria-label="Theme">{dark?<Sun size={16}/>:<Moon size={16}/>}</button>
              </div>
            </div>
          </div>
        </div>
      );
    }
    function BottomNav({ t, lang, view, go }) {
      const items=[["home",STR[lang].navTop,Layers],["blindspot",STR[lang].navOS,Eye],["topics",ui("sections",lang),Compass],["sources",STR[lang].navSrc,Globe],["about",STR[lang].navMethod,Scale]];
      return (
        <nav className={`fixed inset-x-0 bottom-0 z-40 border-t md:hidden ${t.border} ${t.nav}`}>
          <div className="flex">
            {items.map(([k,label,Ic])=>(<button key={k} onClick={()=>go(k)} className={`flex flex-1 flex-col items-center gap-0.5 py-2 ${view===k?t.tp:t.tf}`}><Ic size={19}/><span className={`text-[9.5px] font-semibold ${lang==="hi"?"deva":""}`}>{label}</span></button>))}
          </div>
        </nav>
      );
    }
    function Footer({ t, lang, go }) {
      return (
        <footer className={`mt-12 border-t ${t.border} ${t.surface}`}>
          <div className="mx-auto max-w-[1800px] px-4 sm:px-5 py-9">
            <div className="flex flex-wrap items-end justify-between gap-6">
              <div className="max-w-md">
                <div className="flex items-baseline gap-1.5"><span className={`brand-hi text-xl ${t.tp}`}>पक्ष</span><span className={`text-[15px] font-semibold uppercase tracking-[0.24em] ${t.tp}`}>Paksh</span></div>
                <p className={`mt-2 text-[12.5px] leading-relaxed ${t.tf} ${isHi(lang)}`}>{STR[lang].footIndependence}</p>
              </div>
              <div className="flex flex-wrap gap-x-6 gap-y-2">
                {[["about",STR[lang].navMethod],["sources",STR[lang].navSrc],["blindspot",STR[lang].navOS],["topics",ui("sections",lang)],["contact",lang==="hi"?"संपर्क":"Contact"],["privacy",lang==="hi"?"गोपनीयता":"Privacy"]].map(([k,l])=>(
                  <button key={k} onClick={()=>go(k)} className={`text-[13px] font-medium ${t.ts} hover:${t.tp} ${lang==="hi"?"deva":""}`}>{l}</button>
                ))}
              </div>
            </div>
            <div className={`mt-7 border-t pt-5 ${t.border} mono text-[10.5px] uppercase tracking-wide ${t.tf}`}>© 2026 Paksh · A Redstocks Technology LLP product</div>
          </div>
        </footer>
      );
    }

    /* ---------------- HOME ---------------- */
    function AdSlot({ t, lang, h, label }) {
      return (
        <div className={`flex items-center justify-center border border-dashed ${t.border} ${t.soft}`} style={{minHeight:h||250}}>
          <span className={`eyebrow ${t.tf} ${lang==="hi"?"deva":""}`} style={{letterSpacing:".24em"}}>{label||(lang==="hi"?"विज्ञापन":"Advertisement")}</span>
        </div>
      );
    }
    function GridGrid({ items, render, t, lang, cols, gap }) {
      return <div className={`grid ${gap||"gap-5"} ${cols||"sm:grid-cols-2 lg:grid-cols-3"}`}>{items.map((it,i)=>render(it,i))}</div>;
    }
    // SECOND tier — the "Also leading" rail: 22px headline, a taste of the lead, a 12px
    // bias bar, mono counts. Data-driven like everything else.
    function AlsoLeadingItem({ story, t, lang, onOpen, last }) {
      const c=story.counts||{left:0,center:0,right:0};
      const L=c.left||0,C=c.center||0,R=c.right||0,n=L+C+R;
      return (
        <a href={"/story/"+encodeURIComponent(story.id)} onClick={e=>{ if(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return; e.preventDefault(); onOpen(story.id); }} className={`block no-underline group cursor-pointer py-4 ${last?"":"border-b"} ${t.border}`}>
          <h3 className={`headline text-[20px] sm:text-[22px] ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`} style={{lineHeight:lang==="hi"?1.34:1.24,letterSpacing:lang==="hi"?0:"-0.01em",textWrap:"pretty"}}>{story.headline}</h3>
          {story.lead && <p className={`mt-2 text-[13.5px] lc-2 ${t.ts} ${readCls(lang)}`} style={{lineHeight:lang==="hi"?1.7:1.55}}>{story.lead}</p>}
          <div className="mt-3"><BiasSegments bias={story.bias} t={t} h={12} lang={lang} /></div>
          <div className={`mt-2 mono text-[10.5px] ${t.tf}`}>{L} · {C} · {R} &nbsp;<span style={{color:t.ink,opacity:.55}}>n = {n}</span></div>
        </a>
      );
    }
    // SECTION tier — 4-up band: kicker + 19px headline + 10px bar + mono counts.
    function SectionCard({ story, t, lang, onOpen }) {
      const c=story.counts||{left:0,center:0,right:0};
      const L=c.left||0,C=c.center||0,R=c.right||0,n=L+C+R;
      const tp=lang==="hi"?(TOPIC_HI[story.topic]||story.topic):story.topic;
      return (
        <a href={"/story/"+encodeURIComponent(story.id)} onClick={e=>{ if(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return; e.preventDefault(); onOpen(story.id); }} className="block no-underline group cursor-pointer">
          <div className={`eyebrow ${t.tf} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{tp||"News"}</div>
          <h3 className={`headline mt-2 text-[18px] sm:text-[19px] ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`} style={{lineHeight:1.28,textWrap:"pretty"}}>{story.headline}</h3>
          <div className="mt-3"><BiasSegments bias={story.bias} t={t} h={10} lang={lang} /></div>
          <div className={`mt-1.5 mono text-[10.5px] ${t.tf}`}>{L} · {C} · {R} · n = {n}</div>
        </a>
      );
    }
    // BRIEF tier bar — 6px, FLAT fills (hatch would moiré this small), no centre axis; the
    // printed count carries the exact reading. Under 3 outlets: the hatched "too thin" state.
    function BriefBar({ bias, counts, t }) {
      const L=(counts.left||0),C=(counts.center||0),R=(counts.right||0),n=L+C+R;
      if(n<3) return <div style={{height:6,border:`1px dashed ${t.tf}`,background:"repeating-linear-gradient(45deg,#EAE6DB 0 3px,#E1DCCE 3px 6px)"}}/>;
      const clsOf={left:"seg-left",center:"seg-center-tight",right:"seg-right-flat"};
      const present=["left","center","right"].filter(k=>(bias[k]||0)>0);
      return (
        <div className="relative flex" style={{height:6,border:`1px solid ${t.ink}`,background:t.track||"#EAE6DB"}}>
          {present.map((k,i)=>(
            <React.Fragment key={k}>
              {i>0 && <div style={{flex:"0 0 1px",background:t.gap||"#F4F1EA"}}/>}
              <div className={clsOf[k]} style={{flexGrow:bias[k],flexBasis:0,minWidth:2}}/>
            </React.Fragment>
          ))}
        </div>
      );
    }
    // BRIEF tier row — 15px, no summary; a 64px mini-bar to the left with the printed count.
    function BriefRow({ story, t, lang, onOpen, first }) {
      const c=story.counts||{left:0,center:0,right:0};
      const L=c.left||0,C=c.center||0,R=c.right||0,n=L+C+R;
      return (
        <a href={"/story/"+encodeURIComponent(story.id)} onClick={e=>{ if(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return; e.preventDefault(); onOpen(story.id); }}
           className={`flex items-baseline gap-3 no-underline group cursor-pointer ${first?"":"border-t pt-2.5 mt-2.5"} ${t.border}`} style={{breakInside:"avoid",WebkitColumnBreakInside:"avoid"}}>
          <div className="shrink-0" style={{width:64}}>
            <BriefBar bias={story.bias} counts={c} t={t} />
            <div className={`mt-1 mono text-[10px] ${t.tf}`}>{n<3?"n<3":`${L}·${C}·${R}`}</div>
          </div>
          <h4 className={`text-[15px] ${t.ts} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`} style={{lineHeight:lang==="hi"?1.6:1.42,textWrap:"pretty"}}>{story.headline}</h4>
        </a>
      );
    }
    // THE ONE REVERSAL — the ink-filled Coverage Gaps band at the fold. The page's only
    // ink area; it spends that emphasis on what Paksh exists to say: what one side didn't
    // run. Each label ("Missing: Left · 1 of 12") is computed from the real per-lean counts.
    function InkGapBand({ items, t, lang, go, open }) {
      if(!items.length) return null;
      const paper="#F4F1EA", faint="rgba(244,241,234,.28)";
      return (
        <div style={{background:"#15140F"}} className="px-4 sm:px-10 py-5 sm:py-6">
          <div className="flex items-baseline justify-between gap-3 pb-3" style={{borderBottom:`1px solid ${faint}`}}>
            <span className={`eyebrow ${lang==="hi"?"deva":""}`} style={{color:paper,letterSpacing:lang==="hi"?0:".16em"}}>{lang==="hi"?"कवरेज गैप · जो एक पक्ष ने नहीं चलाया":"Coverage gaps · what one side didn’t run"}</span>
            <button onClick={()=>go("blindspot")} className="mono text-[10.5px] shrink-0" style={{color:"rgba(244,241,234,.6)"}}>{items.length} {lang==="hi"?"आज":"today"} · <span style={{borderBottom:"1px solid rgba(244,241,234,.5)"}}>{lang==="hi"?"सभी गैप":"all gaps"} →</span></button>
          </div>
          <div className="grid gap-y-5 sm:grid-cols-2 lg:grid-cols-3 pt-4">
            {items.map((it,i)=>(
              <a key={it.story.id} href={"/story/"+encodeURIComponent(it.story.id)} onClick={e=>{ if(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return; e.preventDefault(); open(it.story.id); }}
                 className={`block no-underline group cursor-pointer ${i>0?"sm:border-l sm:pl-8":""}`} style={i>0?{borderColor:faint}:{}}>
                <div className={`mono text-[10.5px] gap-accent ${lang==="hi"?"deva":""}`}>{it.label}</div>
                <div className={`headline mt-2 text-[17px] sm:text-[18px] ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`} style={{color:paper,lineHeight:1.3,textWrap:"pretty"}}>{it.story.headline}</div>
              </a>
            ))}
          </div>
        </div>
      );
    }
    // Right-rail companion to the spectrum: the stories where the spectrum agrees most —
    // 2+ sides present, smallest skew. Derived arithmetic over the same live counts.
    function WidestAgreement({ cards, t, lang, onOpen }) {
      const scored=cards.filter(c=>{ const k=c.counts||{}; return ((k.left>0?1:0)+(k.center>0?1:0)+(k.right>0?1:0))>=2; })
        .map(c=>{ const b=c.bias; const skew=Math.max(b.left,b.center,b.right)-Math.min(b.left,b.center,b.right); return {c,skew,n:c.sources}; })
        .sort((a,b)=>(a.skew-b.skew)||(b.n-a.n)).slice(0,2);
      if(!scored.length) return null;
      return (
        <div>
          <div className={`eyebrow pb-2 ${t.tp} ${lang==="hi"?"deva":""}`} style={{borderBottom:`1px solid ${t.ink}`,letterSpacing:lang==="hi"?0:".14em"}}>{lang==="hi"?"सबसे ज़्यादा सहमति":"Widest agreement"}</div>
          {scored.map(({c},i)=>{ const k=c.counts||{}; const L=k.left||0,C=k.center||0,R=k.right||0,n=L+C+R;
            return (
              <a key={c.id} href={"/story/"+encodeURIComponent(c.id)} onClick={e=>{ if(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return; e.preventDefault(); onOpen(c.id); }} className={`block no-underline group cursor-pointer py-3 ${i<scored.length-1?"border-b":""} ${t.border}`}>
                <div className={`headline text-[14.5px] ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`} style={{lineHeight:1.35,textWrap:"pretty"}}>{c.headline}</div>
                <div className="mt-2"><BiasSegments bias={c.bias} t={t} h={8} lang={lang} /></div>
                <div className={`mt-1.5 mono text-[10px] ${t.tf}`}>{L} · {C} · {R} · n = {n}</div>
              </a>
            );
          })}
        </div>
      );
    }
    function HomeView({ cards, gapLeft, gapRight, topics, counts, stats, t, lang, open, goTopic, go }) {
      // de-dup partition: every story appears in exactly ONE place. Ranking (importance:
      // breadth of distinct outlets across L/C/R, decayed by recency) is UNTOUCHED — the
      // top-ranked story leads, the rest fall into the tier ladder in ranked order.
      const used=new Set();
      const take=(arr,n)=>{ const out=[]; for(const c of arr){ if(out.length>=n) break; if(!used.has(c.id)){ out.push(c); used.add(c.id);} } return out; };
      const lead=cards[0]; if(lead) used.add(lead.id);
      const alsoLeading=take(cards,2);      // "Also leading" rail (2)
      const section=take(cards,4);          // 4-up Section band
      const brief=take(cards,15);           // "In brief" tier
      const notUsed=arr=>(arr||[]).filter(c=>!used.has(c.id));
      // Coverage-gap band items: right-heavier stories are "Missing: Left", left-heavier
      // are "Missing: Right". Labels read the real per-lean counts (N of total).
      const nOf=c=>{ const k=c.counts||{}; return (k.left||0)+(k.center||0)+(k.right||0); };
      const gapItems=[];
      notUsed(gapRight).slice(0,2).forEach(s=>{ const k=s.counts||{}; gapItems.push({story:s, label:(lang==="hi"?`ग़ायब: वाम · ${k.left||0}/${nOf(s)}`:`Missing: Left · ${k.left||0} of ${nOf(s)}`)}); });
      notUsed(gapLeft).slice(0,1).forEach(s=>{ const k=s.counts||{}; gapItems.push({story:s, label:(lang==="hi"?`ग़ायब: दक्षिण · ${k.right||0}/${nOf(s)}`:`Missing: Right · ${k.right||0} of ${nOf(s)}`)}); });
      gapItems.slice(0,3).forEach(g=>used.add(g.story.id));

      const pad="px-4 sm:px-10";
      const browse=(
        <div className="mt-9 flex justify-center">
          <button onClick={()=>go("topics")} className={`border px-5 py-2.5 eyebrow ${t.border} ${t.ts} hover:${t.tp} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".08em"}}>{lang==="hi"?"सभी सेक्शन देखें":"Browse all sections"} →</button>
        </div>
      );

      return (
        <div className="mx-auto max-w-[1280px]">
          <div className={pad}><DateStrip t={t} lang={lang} stats={stats} regionFilter={stats.regionFilter} setRegionFilter={stats.setRegionFilter} /></div>

          {/* HERO — 250 / 1fr / 280 with vertical hairlines on desktop; on mobile the lead
              leads, then the rail, then the spectrum (order utilities) */}
          <div className={pad}>
            <div className="grid lg:grid-cols-[250px_1fr_280px]" style={{}}>
              <div className="order-2 lg:order-1 py-4 lg:py-6 lg:pr-7 lg:border-r" style={{borderColor:t.line}}>
                <div className={`eyebrow pb-2 ${t.tp} ${lang==="hi"?"deva":""}`} style={{borderBottom:`1px solid ${t.ink}`,letterSpacing:lang==="hi"?0:".14em"}}>{lang==="hi"?"ये भी प्रमुख":"Also leading"}</div>
                {alsoLeading.map((s,i)=><AlsoLeadingItem key={s.id} story={s} t={t} lang={lang} onOpen={open} last={i===alsoLeading.length-1} />)}
              </div>
              <div className="order-1 lg:order-2 py-4 lg:py-6 lg:px-7 lg:border-r border-b-2 lg:border-b-0" style={{borderColor:t.line,borderBottomColor:t.ink}}>
                {lead && <LeadStory story={lead} t={t} lang={lang} onOpen={open} />}
              </div>
              <div className="order-3 py-4 lg:py-6 lg:pl-7 space-y-6">
                <SpectrumRail cards={cards} t={t} lang={lang} />
                <WidestAgreement cards={cards} t={t} lang={lang} onOpen={open} />
              </div>
            </div>
          </div>

          {/* THE INK BAND — full width within the frame */}
          <div style={{borderTop:`2px solid ${t.ink}`}}><InkGapBand items={gapItems.slice(0,3)} t={t} lang={lang} go={go} open={open} /></div>

          {/* SECTION band — 4-up on desktop, 2-up tablet, stacked mobile */}
          <div className={pad}>
            <div className="grid gap-x-6 gap-y-7 sm:grid-cols-2 lg:grid-cols-4 py-7" style={{borderBottom:`1px solid ${t.ink}`}}>
              {section.map((s,i)=>(
                <div key={s.id} className={i>0?"lg:border-l lg:pl-6":""} style={i>0?{borderColor:t.line}:{}}>
                  <SectionCard story={s} t={t} lang={lang} onOpen={open} />
                </div>
              ))}
            </div>
          </div>

          {/* IN BRIEF — everything else tracked today, in flowing columns */}
          {brief.length>0 && (
            <div className={pad}>
              <div className="py-7">
                <div className="mb-3.5 flex items-baseline justify-between">
                  <span className={`eyebrow ${t.tp} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".16em"}}>{lang==="hi"?"संक्षेप में · आज ट्रैक की गई बाक़ी सब":"In brief · everything else tracked today"}</span>
                </div>
                <div style={{columnGap:"2.25rem",columnRule:`1px solid ${t.line}`}} className="[column-count:1] sm:[column-count:2] lg:[column-count:3]">
                  {brief.map((s,i)=><BriefRow key={s.id} story={s} t={t} lang={lang} onOpen={open} first={i===0} />)}
                </div>
                {browse}
              </div>
            </div>
          )}
        </div>
      );
    }
    /* ---------------- STORY (tabbed) ---------------- */
    function StoryPage({ story, t, lang, go, openTopic }) {
      const fr=story.framing||{};
      const outlets=story.outlets||[];
      const counts={ left:outlets.filter(o=>o.lean==="left").length, center:outlets.filter(o=>o.lean==="center").length, right:outlets.filter(o=>o.lean==="right").length, international:outlets.filter(o=>o.lean==="international").length, unrated:outlets.filter(o=>o.lean==="unrated").length };
      // ONE VOTE PER OWNER: the bias bar counts distinct OWNERS, so co-owned mastheads
      // (Times of India + Navbharat Times) count once. voteRow() reads the authoritative
      // server coverage (count=owner votes, sources=distinct mastheads) and groups the
      // mastheads by owner so the reader can see WHY a side shows "N votes, M outlets".
      const ownerOf={}; outlets.forEach(o=>{ if(o.source) ownerOf[o.source]=o.owner||o.source; });
      const voteRow=(k)=>{ const b=(story.coverage&&story.coverage[k])||{}; const names=b.sources||[]; const votes=(typeof b.count==="number")?b.count:(counts[k]||0); const gm=new Map(); names.forEach(n=>{ const ow=ownerOf[n]||n; if(!gm.has(ow))gm.set(ow,[]); gm.get(ow).push(n); }); return {votes, outlets:names.length, groups:[...gm.entries()]}; };
      // The bias bar's widths come from the distinct-OWNER votes (vc); percentages are
      // derived from those, so the printed scale matches the segments exactly.
      const vc={left:voteRow("left").votes,center:voteRow("center").votes,right:voteRow("right").votes};
      const nVotes=vc.left+vc.center+vc.right;
      const bpct=biasPct(vc);
      const [atab,setAtab]=useState("all");
      const arts = atab==="all"?outlets:outlets.filter(o=>o.lean===atab);
      const total=story.sources+(story.unrated||0)+(story.international||0);
      const [copied,setCopied]=useState(false);
      const copy=()=>{ try{ navigator.clipboard.writeText(window.location.href); setCopied(true); setTimeout(()=>setCopied(false),1600);}catch(e){} };
      const tp=lang==="hi"?(TOPIC_HI[story.topic]||story.topic):story.topic;
      const region=lang==="hi"?(story.region==="World"?"विश्व":"भारत"):(story.region||"India");
      const metaLine=lang==="hi"
        ? `${total} स्रोत · वाम ${vc.left} · केंद्र ${vc.center} · दक्षिण ${vc.right} · ${timeAgo(story.created_at,lang)}`
        : `${total} outlets · ${vc.left} left · ${vc.center} centre · ${vc.right} right · ${timeAgo(story.created_at,lang)}`;
      const ATab=({k,n})=>{ const on=atab===k; const lab=k==="all"?(lang==="hi"?"सभी":"All"):lbl(k,lang);
        return <button onClick={()=>setAtab(k)} className={`flex items-center gap-1.5 border-b-2 px-1 pb-2 text-[13.5px] font-semibold ${on?t.tp:`${t.tf} hover:${t.ts}`}`} style={{borderColor:on?(k==="all"?t.ink:(k==="center"?t.ink:BIAS[k]&&BIAS[k].color)):"transparent"}}>{lab}<span className={`mono text-[11px] ${on?t.ts:t.tf}`}>{n}</span></button>; };
      const sides=["left","center","right"].filter(k=> fr[k] || counts[k]>0);
      return (
        <div className="mx-auto max-w-[1000px] px-4 sm:px-8 py-6">
          {/* secondary bar: back · breadcrumb · share */}
          <div className="mb-8 flex items-center justify-between gap-3 pb-3" style={{borderBottom:`1px solid ${t.ink}`}}>
            <button onClick={()=>go("home")} className={`inline-flex items-center gap-1.5 eyebrow ${t.ts} hover:${t.tp}`} style={{letterSpacing:lang==="hi"?0:".1em"}}><ArrowLeft size={14}/> {STR[lang].back}</button>
            <button onClick={()=>openTopic(story.topic)} className={`hidden sm:inline truncate eyebrow ${t.tf} hover:${t.tp} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{tp} · {region}</button>
            <button onClick={copy} className={`inline-flex shrink-0 items-center gap-1.5 eyebrow ${t.ts} hover:${t.tp}`} style={{letterSpacing:lang==="hi"?0:".1em"}}>{copied?<><Check size={13}/> {lang==="hi"?"कॉपी":"Copied"}</>:<><LinkIcon size={13}/> {lang==="hi"?"शेयर":"Share"}</>}</button>
          </div>

          {/* headline block — centered on desktop, left on mobile */}
          <div className="mx-auto max-w-[840px] text-left sm:text-center">
            <div className={`eyebrow sm:hidden ${t.tf} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{tp} · {region}</div>
            <h1 className={`headline mt-3 sm:mt-0 text-[28px] sm:text-[42px] lg:text-[50px] ${t.tp} ${readCls(lang)}`} style={{lineHeight:lang==="hi"?1.18:1.1,letterSpacing:lang==="hi"?0:"-0.02em",textWrap:"balance"}}>{story.headline}</h1>
            <div className={`mt-4 mono text-[11.5px] ${t.tf} ${lang==="hi"?"deva":""}`}>{metaLine}{story.auto && <> · <span className="uppercase">{STR[lang].autoTag}</span></>}</div>
          </div>

          {/* the bias instrument — border-y ink, printed scale; segments filter the article list */}
          <div className="mx-auto mt-8 max-w-[840px] py-6" style={{borderTop:`1px solid ${t.ink}`,borderBottom:`1px solid ${t.ink}`}}>
            <div className="mb-2.5 flex items-baseline justify-between gap-3">
              <div className={`flex gap-5 sm:gap-6 text-[11px] font-medium uppercase tracking-[0.12em] ${t.tp} ${lang==="hi"?"deva":""}`}>
                {["left","center","right"].map(k=>(vc[k]>0)?<span key={k}>{lbl(k,lang)} <span className="mono" style={{letterSpacing:0}}>{vc[k]}</span></span>:null)}
              </div>
              <span className={`mono text-[11px] shrink-0 ${t.tf}`}>n = {nVotes} · {bpct.left}/{bpct.center}/{bpct.right}%</span>
            </div>
            <BiasSegments bias={bpct} t={t} h={28} lang={lang} onPick={(k)=>{ setAtab(k); const el=document.getElementById("arts"); if(el) el.scrollIntoView({behavior:"smooth",block:"start"}); }} active={atab!=="all"?atab:null} />
            <div className="relative" style={{height:15,marginTop:3}}>
              {[25,50,75].map(p=><div key={p} style={{position:"absolute",left:p+"%",top:0,width:1,height:p===50?7:4,background:p===50?t.ink:t.line}}/>)}
              <span className={`mono text-[10px] ${t.tf}`} style={{position:"absolute",left:"50%",top:7,transform:"translateX(-50%)",whiteSpace:"nowrap"}}>{lang==="hi"?"कवरेज का 50%":"50% of coverage"}</span>
            </div>
          </div>

          {/* the story, without framing — label + note | summary */}
          <div className="mx-auto mt-9 max-w-[840px] grid gap-5 md:grid-cols-[200px_1fr] md:gap-11">
            <div>
              <div className={`eyebrow ${t.tp} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{lang==="hi"?"बिना फ़्रेमिंग की ख़बर":"The story, without framing"}</div>
              {story.auto && <div className={`mt-2 eyebrow ${t.tf} ${lang==="hi"?"deva":""}`} style={{textTransform:"none",letterSpacing:0}}>{STR[lang].autoFrom}</div>}
            </div>
            <div>
              {story.lead && <p className={`text-[16px] md:text-[19px] ${t.tp} ${readCls(lang)}`} style={{lineHeight:lang==="hi"?1.85:1.6}}>{story.lead}</p>}
              <ul className="mt-3 space-y-2.5">{(story.summary||[]).map((p,i)=><li key={i} className={`flex gap-2.5 text-[15px] md:text-[16px] ${t.ts} ${readCls(lang)}`} style={{lineHeight:lang==="hi"?1.8:1.6}}><span className="mt-[10px] h-1 w-2 shrink-0" style={{background:t.ink}}/>{p}</li>)}</ul>
              <p className={`mt-4 mono text-[10.5px] leading-[1.6] ${t.tf} ${isHi(lang)}`}>{STR[lang].aiNote}</p>
            </div>
          </div>

          {/* how each side framed it — 3-up bordered table (desktop) / stacked cards (mobile) */}
          {sides.length>0 && (
          <div className="mt-10">
            <div className="mb-4 flex items-baseline justify-between gap-3">
              <h3 className={`eyebrow ${t.tp} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{STR[lang].framingTitle}</h3>
              <span className={`mono text-[10.5px] hidden sm:inline ${t.tf} ${lang==="hi"?"deva":""}`}>{lang==="hi"?"बराबर कॉलम · क्रम बार जैसा":"equal columns · order matches the bar"}</span>
            </div>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3 md:gap-0 md:border" style={{borderColor:t.ink}}>
              {sides.map(k=>(
                <div key={k} className={`flex flex-col border md:border-0 md:border-r last:md:border-r-0 ${t.surface}`} style={{borderColor:t.ink}}>
                  <div className={BIAS[k].tex} style={{height:6}}/>
                  <div className="flex flex-1 flex-col p-5">
                    <div className="flex items-baseline justify-between">
                      <span className={`text-[11.5px] font-medium uppercase tracking-[0.14em] ${t.tp} ${lang==="hi"?"deva":""}`}>{lbl(k,lang)}</span>
                      <span className={`mono text-[10.5px] ${t.tf} ${lang==="hi"?"deva":""}`}>{counts[k]} {lang==="hi"?"स्रोत":(counts[k]===1?"outlet":"outlets")}</span>
                    </div>
                    {fr[k]
                      ? <p className={`mt-3.5 text-[14.5px] md:text-[15px] ${t.ts} ${readCls(lang)}`} style={{lineHeight:lang==="hi"?1.75:1.62}}>{fr[k]}</p>
                      : <p className={`mt-3.5 text-[13px] italic ${t.tf} ${readCls(lang)}`}>{STR[lang].framingPending}</p>}
                  </div>
                </div>
              ))}
            </div>
            <p className={`mt-3 mono text-[10.5px] leading-[1.6] ${t.tf} ${isHi(lang)}`}>{STR[lang].framingSub}</p>
          </div>
          )}

          {/* coverage breakdown — ONE VOTE PER OWNER (invariant display) */}
          <div className="mx-auto mt-10 max-w-[840px]">
            <div className="pb-2" style={{borderBottom:`1px solid ${t.ink}`}}><h3 className={`eyebrow ${t.tp} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{STR[lang].coverageBreakdown}</h3></div>
            <div className={`mt-2 flex items-center justify-between border-b py-2.5 ${t.border}`}>
              <span className={`text-[13px] font-semibold ${t.tp} ${readCls(lang)}`}>{STR[lang].totalSources}</span>
              <span className={`mono text-[14px] font-semibold ${t.tp}`}>{total}</span>
            </div>
            {["left","center","right"].map((k)=>{ const {votes,outlets:oc,groups}=voteRow(k); if(votes===0 && oc===0) return null;
              const coOwned=groups.some(([o,ms])=>ms.length>1);
              return (
              <div key={k} className={`border-b py-3 ${t.border}`}>
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-2.5"><span className={`${BIAS[k].tex} shrink-0`} style={{width:14,height:14,border:`1px solid ${t.ink}`}}/><span className={`text-[13px] ${t.ts} ${lang==="hi"?"deva":""}`}>{lbl(k,lang)}</span></span>
                  <span className={`mono text-[14px] font-semibold ${t.tp}`}>{votes}{oc>votes && <span className={`ml-1 text-[11px] font-normal ${t.tf}`}>{lang==="hi"?`(${oc} स्रोत)`:`(${oc} outlets)`}</span>}</span>
                </div>
                {coOwned && <div className="mt-1.5 space-y-0.5 pl-6">{groups.filter(([o,ms])=>ms.length>1).map(([o,ms],j)=>(
                  <div key={j} className={`text-[11px] leading-snug ${t.tf} ${isHi(lang)}`}>{ms.join(" · ")} <span className="italic">({o} — {lang==="hi"?"1 वोट":"1 vote"})</span></div>
                ))}</div>}
              </div>
              );
            })}
            {story.international>0 && <div className={`flex items-center justify-between border-b py-2.5 ${t.border}`}><span className={`text-[13px] ${t.ts} ${isHi(lang)}`}>{STR[lang].intlTitle}</span><span className={`mono text-[14px] font-semibold ${t.tp}`}>{story.international}</span></div>}
            {story.unrated>0 && <div className={`flex items-center justify-between border-b py-2.5 ${t.border}`}><span className={`text-[13px] ${t.ts} ${isHi(lang)}`}>{STR[lang].unratedTitle}</span><span className={`mono text-[14px] font-semibold ${t.tp}`}>{story.unrated}</span></div>}
            {story.blindspot && <div className={`mt-4 flex items-start gap-2 p-3 text-[12px] leading-relaxed ${t.blindSoft} ${t.blind} ${isHi(lang)}`}><Eye size={15} className="mt-0.5 shrink-0"/><span>{STR[lang].osCalloutBody1} <strong>{story.bias[story.blindspot]}%</strong> {STR[lang].osCalloutBody2}</span></div>}
            <p className={`mt-4 text-[11px] leading-relaxed ${t.tf} ${isHi(lang)}`}>{STR[lang].aiNote}</p>
          </div>

          {/* articles */}
          <div className="mx-auto mt-10 max-w-[840px]" id="arts">
            <div className={`mb-3 eyebrow ${t.tp} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{lang==="hi"?"किसने कवर किया":"Who covered it"}</div>
            <div className={`flex items-center gap-5 border-b ${t.border}`}>
              <ATab k="all" n={outlets.length} />
              {counts.left>0 && <ATab k="left" n={counts.left} />}
              {counts.center>0 && <ATab k="center" n={counts.center} />}
              {counts.right>0 && <ATab k="right" n={counts.right} />}
            </div>
            <div className="mt-4 space-y-2.5">
              {arts.map((o,i)=>(
                <a key={i} href={o.url||"#"} target="_blank" rel="noopener" className={`flex items-start gap-3 border p-3.5 ${t.surface} ${t.border} hover:${t.soft}`}>
                  <OutletAvatar o={o} side={o.lean} size={30} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className={`text-[13px] font-bold ${t.tp}`}>{o.source}</span>
                      <LeanBadge side={o.lean} lang={lang} t={t} />
                      <span className={`ml-auto mono text-[10px] ${t.tf}`}>{(o.language||"en").toUpperCase()}</span>
                    </div>
                    {o.headline && <div className={`mt-1 text-[14.5px] leading-snug ${t.ts} ${readCls(lang)}`}>{o.headline}</div>}
                  </div>
                  <ArrowUpRight size={15} className={`mt-0.5 shrink-0 ${t.tf}`} />
                </a>
              ))}
              {arts.length===0 && <div className={`py-10 text-center text-[13px] ${t.tf}`}>-</div>}
            </div>
          </div>
        </div>
      );
    }

    /* ---------------- other pages ---------------- */
    function PageWrap({ children }) { return <div className="mx-auto max-w-[1280px] px-4 sm:px-10 py-8">{children}</div>; }
    // Coverage-gap rate columns — three EQUAL-WIDTH slots; each fill's height is that side's
    // SHARE of its own tracked outlets that ran the story (a rate, not a raw count, so a
    // side with more tracked outlets is normalised, not penalised). The absent side is drawn
    // as a hatch so absence occupies space. Driven by live per-lean counts + the roster.
    function GapRateColumns({ counts, roster, gapSide, t, lang }) {
      const ks=["left","center","right"];
      return (
        <div className="grid grid-cols-3 gap-2">
          {ks.map(k=>{ const n=counts[k]||0; const m=roster[k]||0; const rate=m>0?Math.min(100,Math.round(n/m*100)):0; const isGap=k===gapSide;
            return (
              <div key={k}>
                <div className={`flex items-end ${n>0?"":"seg-absent"}`} style={{height:56,border:n>0?`1px solid ${t.ink}`:`1px dashed ${t.tf}`,background:n>0?(t.track||"#EAE6DB"):undefined}}>
                  {n>0 && <div className={`w-full ${BIAS[k].tex}`} style={{height:`${Math.max(8,rate)}%`}}/>}
                </div>
                <div className={`mt-1.5 text-[9.5px] font-medium uppercase tracking-[0.1em] ${t.tp} ${lang==="hi"?"deva":""}`}>{lbl(k,lang)}</div>
                <div className={`mono text-[10.5px] ${isGap?t.blind:t.tf}`}>{n} / {m}</div>
              </div>
            );
          })}
        </div>
      );
    }
    // A single coverage-gap card: which side missed it (eyebrow, clay), the headline, a
    // taste of the neutral summary, the rate columns, and a link into the story.
    function GapCard({ story, roster, gapSide, t, lang, onOpen }) {
      const c=story.counts||{left:0,center:0,right:0};
      const gapN=c[gapSide]||0;
      const sideWord=lang==="hi"?(gapSide==="left"?"वाम":"दक्षिण"):gapSide;
      const eyebrow=lang==="hi"
        ? (gapN===0?`${sideWord} पर अप्रकाशित`:`${sideWord} पर कम कवरेज`)
        : (gapN===0?`Unreported on the ${sideWord}`:`Under-covered on the ${sideWord}`);
      return (
        <a href={"/story/"+encodeURIComponent(story.id)} onClick={e=>{ if(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return; e.preventDefault(); onOpen(story.id); }} className="flex h-full flex-col no-underline group cursor-pointer">
          <div className={`eyebrow ${t.blind} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{eyebrow}</div>
          <h3 className={`headline mt-3 text-[20px] lg:text-[24px] ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`} style={{lineHeight:1.24,textWrap:"pretty"}}>{story.headline}</h3>
          {story.lead && <p className={`mt-2.5 text-[14px] lg:text-[15px] lc-3 ${t.ts} ${readCls(lang)}`} style={{lineHeight:lang==="hi"?1.7:1.6}}>{story.lead}</p>}
          <div className="mt-5"><GapRateColumns counts={c} roster={roster} gapSide={gapSide} t={t} lang={lang} /></div>
          <div className={`mt-4 eyebrow ${t.tp} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".06em"}}><span style={{borderBottom:`1px solid ${t.ink}`,paddingBottom:2}}>{lang==="hi"?"तटस्थ सारांश पढ़ें":"Read the neutral summary"} →</span></div>
        </a>
      );
    }
    function BlindspotPage({ left, right, roster, agg, stats, t, lang, open, go }) {
      // left = left_heavier (RIGHT is the under-covered side); right = right_heavier (LEFT is).
      const cards=[];
      (right||[]).forEach(s=>cards.push({story:s, gapSide:"left"}));
      (left||[]).forEach(s=>cards.push({story:s, gapSide:"right"}));
      // Starkest first: the smallest under-covered count (0 = unreported) leads.
      cards.sort((a,b)=>((a.story.counts||{})[a.gapSide]||0)-((b.story.counts||{})[b.gapSide]||0));
      const shown=cards.slice(0,15);
      const gapsToday=(agg.total!=null?agg.total:cards.length);
      const pad="px-4 sm:px-10";
      const explain=(head,body)=>(
        <div>
          <div className={`eyebrow ${t.tp} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{head}</div>
          <p className={`mt-2.5 text-[14px] ${t.ts} ${readCls(lang)}`} style={{lineHeight:lang==="hi"?1.75:1.65}}>{body}</p>
        </div>
      );
      return (
        <div className="mx-auto max-w-[1280px]">
          {/* header */}
          <div className={`${pad} pt-6`}>
            <div className="flex flex-wrap items-end justify-between gap-4 pb-5" style={{borderBottom:`2px solid ${t.ink}`}}>
              <div className="max-w-[62ch]">
                <h1 className={`headline text-[30px] sm:text-[40px] ${t.tp} ${readCls(lang)}`} style={{letterSpacing:lang==="hi"?0:"-0.018em"}}>{STR[lang].osTitle}</h1>
                <p className={`mt-3 text-[15px] sm:text-[16px] ${t.ts} ${readCls(lang)}`} style={{lineHeight:lang==="hi"?1.75:1.6}}>{STR[lang].osSub}</p>
              </div>
              <div className={`mono text-[11px] leading-[1.7] text-right shrink-0 ${t.tf}`}>
                {gapsToday} {lang==="hi"?"गैप आज":"gaps today"}<br/>{stats.stories} {lang==="hi"?"ख़बरें ट्रैक":"stories tracked"}
              </div>
            </div>
          </div>
          {/* gap cards */}
          <div className={pad}>
            {shown.length? (
              <div className="grid gap-x-6 gap-y-9 py-8 sm:grid-cols-2 lg:grid-cols-3" style={{borderBottom:`1px solid ${t.ink}`}}>
                {shown.map((g,i)=>(
                  <div key={g.story.id} className={i>0?"lg:border-l lg:pl-6":""} style={i>0?{borderColor:t.line}:{}}>
                    <GapCard story={g.story} roster={roster} gapSide={g.gapSide} t={t} lang={lang} onOpen={open} />
                  </div>
                ))}
              </div>
            ) : <div className={`my-8 border border-dashed p-10 text-center text-[13px] ${t.border} ${t.tf} ${readCls(lang)}`}>{STR[lang].noStories}</div>}
          </div>
          {/* explainer */}
          <div className={pad}>
            <div className={`my-8 grid gap-8 p-6 sm:p-8 md:grid-cols-2 ${t.soft}`}>
              {explain(lang==="hi"?"गैप कैसे तय होता है":"How a gap is declared", lang==="hi"?"पक्ष किसी ख़बर को गैप तब चिह्नित करता है जब स्पेक्ट्रम के एक तरफ़ के आउटलेट्स ने उसे कवर किया पर दूसरी तरफ़ के बहुत कम या किसी ने नहीं — वही अलग-अलग आउटलेट गिनती जो बायस बार में है। यह अंकगणित है, इस पर निर्णय नहीं कि किसी पक्ष ने इसे क्यों कवर किया या नहीं।":"Paksh flags a story as a gap when outlets on one side of the spectrum covered it while few or none on the other did — the same distinct-outlet-per-lean counting as the bias bar. It's arithmetic, not a judgment about why a side did or didn't cover it.")}
              {explain(lang==="hi"?"स्लॉट बराबर चौड़े क्यों":"Why the slots are equal width", lang==="hi"?"यह चार्ट बायस बार नहीं है। बायस बार जो मौजूद है उसे बाँटता है; गैप चार्ट हर पक्ष को बराबर स्लॉट देता है, ताकि ग़ैरमौजूद पक्ष ग़ायब होने के बजाय — हैच और शून्य के साथ — दिखे। अनुपस्थिति को दिखने के लिए जगह घेरनी पड़ती है।":"This chart is not the bias bar. The bias bar divides what exists; the gap chart reserves an equal slot per side, so the empty one is drawn — hatched and labelled zero — instead of vanishing. Absence has to occupy space to be seen.")}
            </div>
          </div>
        </div>
      );
    }
    function TopicsHub({ topics, counts, t, lang, goTopic }) {
      return (
        <PageWrap>
          <h1 className={`headline text-[30px] sm:text-[40px] ${t.tp} ${readCls(lang)}`} style={{letterSpacing:lang==="hi"?0:"-0.018em"}}>{ui("sections",lang)}</h1>
          <div className="mt-7 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {topics.map(tp=>(<button key={tp} onClick={()=>goTopic(tp)} className={`flex items-center justify-between border p-5 text-left ${t.surface} ${t.border} hover:${t.soft}`}><span className={`headline text-[18px] ${t.tp} ${readCls(lang)}`}>{lang==="hi"?(TOPIC_HI[tp]||tp):tp}</span><ChevronRight size={16} className={t.tf}/></button>))}
          </div>
        </PageWrap>
      );
    }
    function TopicPage({ topic, items, t, lang, open, go }) {
      return (
        <PageWrap>
          <button onClick={()=>go("topics")} className={`mb-4 inline-flex items-center gap-1.5 eyebrow ${t.ts} hover:${t.tp}`} style={{letterSpacing:lang==="hi"?0:".1em"}}><ArrowLeft size={14}/> {ui("sections",lang)}</button>
          <h1 className={`headline mb-7 text-[30px] sm:text-[40px] ${t.tp} ${readCls(lang)}`} style={{letterSpacing:lang==="hi"?0:"-0.018em"}}>{lang==="hi"?(TOPIC_HI[topic]||topic):topic}</h1>
          {items.length? <GridGrid items={items} t={t} lang={lang} render={(s)=><GridCard key={s.id} story={s} t={t} lang={lang} onOpen={open}/>} />
            : <div className={`py-24 text-center ${t.tf} ${isHi(lang)}`}>{STR[lang].noStories}</div>}
        </PageWrap>
      );
    }
    function SourceCard({ s, t, lang }) {
      const side=["left","center","right"].includes(s.lean)?s.lean:null;
      return (
        <div className={`rounded-lg border p-4 ${t.surface} ${t.border}`} style={side?{borderLeftWidth:3,borderLeftColor:BIAS[side].color}:{}}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0"><div className={`headline text-[15px] ${t.tp} ${readCls(lang)}`}>{s.name}</div>{s.website && <a href={s.website} target="_blank" rel="noopener" className={`mono text-[11px] break-all ${t.tf} hover:${t.ts}`}>{(s.website||"").replace(/^https?:\/\//,"")}</a>}</div>
            {side?<LeanBadge side={side} lang={lang} t={t}/>:<span className={`shrink-0 rounded mono px-1.5 py-0.5 text-[10px] font-bold uppercase ${t.chip} ${t.tf}`}>{s.label||"-"}</span>}
          </div>
          <div className="mt-2.5 flex flex-wrap items-center gap-2 mono text-[10px]">
            <span className={`uppercase ${t.tf}`}>{(s.language||"en").toUpperCase()}</span>
            {s.confidence && <span className={t.tf}>· conf {s.confidence}</span>}
            {s.contested && <span className={`rounded px-1.5 py-0.5 font-bold ${t.blindSoft} ${t.blind}`}>{STR[lang].contested}</span>}
          </div>
          {s.ownership && <div className={`mt-2.5 text-[12.5px] leading-[1.55] ${t.ts} ${readCls(lang)}`}><span className={`font-semibold ${t.tp}`}>{STR[lang].ownership}:</span> {s.ownership}</div>}
          {s.rationale && <p className={`mt-1.5 text-[12.5px] leading-[1.55] ${t.tf} ${readCls(lang)}`}>{s.rationale}</p>}
        </div>
      );
    }
    function SourcesPage({ t, lang, sources }) {
      const [f,setF]=useState("all");
      const list=(sources||[]).filter(s=>f==="all"||s.lean===f);
      const filters=[["all",lang==="hi"?"सभी":"All"],["left",lbl("left",lang)],["center",lbl("center",lang)],["right",lbl("right",lang)]];
      return (
        <PageWrap>
          <h1 className={`headline text-[30px] sm:text-[40px] ${t.tp} ${readCls(lang)}`} style={{letterSpacing:lang==="hi"?0:"-0.018em"}}>{STR[lang].srcTitle}</h1>
          <p className={`mb-5 mt-3 max-w-2xl text-[15px] leading-[1.6] ${t.ts} ${readCls(lang)}`}>{STR[lang].srcDisclaimer}</p>
          <div className="mb-6 flex flex-wrap gap-2">{filters.map(([k,label])=>(<button key={k} onClick={()=>setF(k)} className={`border px-3.5 py-1.5 eyebrow ${f===k?`${t.cta} ${t.ctaT} border-transparent`:`${t.surface} ${t.border} ${t.ts} hover:${t.tp}`} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".08em"}}>{label}</button>))}</div>
          <GridGrid items={list} t={t} lang={lang} gap="gap-4" render={(s)=><SourceCard key={s.id||s.name} s={s} t={t} lang={lang}/>} />
        </PageWrap>
      );
    }
    function AboutPage({ t, lang, agg }) {
      const Row=({h,children})=>(<div className={`border-b py-6 ${t.border}`}><h2 className={`headline text-[20px] ${t.tp} ${readCls(lang)} mb-2`}>{h}</h2><div className={`text-[15px] leading-[1.62] ${t.ts} ${readCls(lang)}`}>{children}</div></div>);
      const a=agg||{};
      const gapText=(STR[lang].m_gap||"").replace("{total}",a.total).replace("{rh}",a.right_heavier).replace("{lh}",a.left_heavier).replace("{lo}",a.left_outlets).replace("{ro}",a.right_outlets);
      return (
        <PageWrap>
          <div className="max-w-3xl">
            <h1 className={`headline text-[30px] sm:text-[40px] ${t.tp} ${readCls(lang)}`} style={{letterSpacing:lang==="hi"?0:"-0.018em"}}>{STR[lang].methodTitle}</h1>
            <p className={`mb-2 mt-3 text-[16px] leading-[1.62] ${t.ts} ${readCls(lang)}`}>{STR[lang].m_does}</p>
            <Row h={STR[lang].m_ruleH}>{STR[lang].m_rule}</Row>
            {a.total!=null && <Row h={STR[lang].m_gapH}>{gapText}</Row>}
            <Row h={STR[lang].m_rateH}><p className="mb-2">{STR[lang].m_rateLede}</p><p className={`text-[12px] ${t.tf}`}>{STR[lang].m_rateFoot}</p></Row>
            <Row h={STR[lang].m_axisH}>{STR[lang].m_axis}</Row>
            <Row h={STR[lang].m_partiesH}>{STR[lang].m_parties}</Row>
            <Row h={STR[lang].m_provH}>{STR[lang].m_prov}</Row>
            <Row h={STR[lang].m_readH}>{STR[lang].m_appeal}</Row>
          </div>
        </PageWrap>
      );
    }
    function ContactPage({ t, lang }) {
      const [status,setStatus]=useState("idle");
      const [err,setErr]=useState("");
      const L = lang==="hi" ? {
        title:"संपर्क करें", lede:"सवाल, सुधार या शिकायत? हमें लिखें - हम हर संदेश पढ़ते हैं।",
        name:"आपका नाम (वैकल्पिक)", email:"ईमेल", topic:"विषय",
        tQ:"सामान्य सवाल", tC:"सुधार / तथ्य-जाँच", tX:"शिकायत", tO:"अन्य",
        msg:"आपका संदेश", send:"भेजें", sending:"भेजा जा रहा है…",
        ok:"धन्यवाद - आपका संदेश मिल गया। हम जल्द जवाब देंगे।",
        err:"संदेश नहीं भेजा जा सका। कृपया दोबारा प्रयास करें।"
      } : {
        title:"Contact", lede:"A question, a correction, or a complaint? Write to us - we read every message.",
        name:"Your name (optional)", email:"Email", topic:"Topic",
        tQ:"General question", tC:"Correction / fact-check", tX:"Complaint", tO:"Other",
        msg:"Your message", send:"Send", sending:"Sending…",
        ok:"Thank you - your message reached us. We'll reply soon.",
        err:"Could not send your message. Please try again."
      };
      async function submit(e){
        e.preventDefault(); setStatus("sending"); setErr("");
        const form=e.currentTarget; const body=new FormData(form);
        try{
          const r=await fetch(FORMSPREE_ENDPOINT,{method:"POST",body,headers:{Accept:"application/json"}});
          if(r.ok){ setStatus("ok"); form.reset(); }
          else{ const j=await r.json().catch(()=>({})); setErr((j.errors&&j.errors.map(x=>x.message).join(", "))||L.err); setStatus("error"); }
        }catch(_){ setErr(L.err); setStatus("error"); }
      }
      const inp=`w-full rounded-lg border px-3.5 py-2.5 text-[14.5px] outline-none transition-colors ${t.surface} ${t.border} focus:border-[#15140F] ${t.tp} ${isHi(lang)}`;
      const lbl=`mb-1.5 block text-[12.5px] font-semibold ${t.ts} ${isHi(lang)}`;
      return (
        <PageWrap>
          <div className="max-w-xl">
            <h1 className={`headline text-[30px] sm:text-[40px] ${t.tp} ${readCls(lang)}`} style={{letterSpacing:lang==="hi"?0:"-0.018em"}}>{L.title}</h1>
            <p className={`mb-6 mt-3 text-[15px] leading-relaxed ${t.ts} ${isHi(lang)}`}>{L.lede}</p>
            {status==="ok" ? (
              <div className={`rounded-lg border p-5 ${t.border} ${t.surface}`}><p className={`text-[15px] font-medium ${t.tp} ${isHi(lang)}`}>{L.ok}</p></div>
            ) : (
              <form onSubmit={submit} className="space-y-4">
                <input type="text" name="_gotcha" style={{display:"none"}} tabIndex="-1" autoComplete="off" />
                <input type="hidden" name="_subject" value="New Paksh contact message" />
                <div><label className={lbl}>{L.name}</label><input name="name" type="text" className={inp} /></div>
                <div><label className={lbl}>{L.email}</label><input name="email" type="email" required className={inp} /></div>
                <div><label className={lbl}>{L.topic}</label>
                  <select name="topic" className={inp}><option>{L.tQ}</option><option>{L.tC}</option><option>{L.tX}</option><option>{L.tO}</option></select>
                </div>
                <div><label className={lbl}>{L.msg}</label><textarea name="message" required rows="6" className={inp} /></div>
                {status==="error" && <p className="text-[13px] font-medium" style={{color:"#C0392B"}}>{err}</p>}
                <button type="submit" disabled={status==="sending"} className={`rounded-full px-5 py-2.5 text-[14px] font-semibold ${t.cta} ${t.ctaT} disabled:opacity-60 ${isHi(lang)}`}>{status==="sending"?L.sending:L.send}</button>
              </form>
            )}
          </div>
        </PageWrap>
      );
    }
    function PrivacyPage({ t, lang }) {
      const Row=({h,children})=>(<div className={`border-b py-6 ${t.border}`}><h2 className={`headline text-[20px] ${t.tp} serif mb-2`}>{h}</h2><div className={`text-[15px] leading-[1.62] serif ${t.ts}`}>{children}</div></div>);
      return (
        <PageWrap>
          <div className="max-w-3xl">
            <h1 className={`headline text-[30px] sm:text-[40px] ${t.tp} serif`} style={{letterSpacing:"-0.018em"}}>Privacy Policy</h1>
            <p className={`mb-1 mt-3 text-[13px] ${t.tf}`}>Last updated: 2 July 2026 · Operated by Redstocks Technology LLP</p>
            {lang==="hi" && <p className={`mb-2 text-[12.5px] deva ${t.tf}`}>यह गोपनीयता नीति अंग्रेज़ी में उपलब्ध है।</p>}
            <Row h="Who we are">Paksh (पक्ष) is a media-transparency service that groups how different Indian outlets cover the same news story and shows the spread of that coverage across the political spectrum.</Row>
            <Row h="What we collect">When you use our contact form, we receive the email address and message you choose to send, so that we can reply; that form is processed on our behalf by Formspree. As with most websites, our host keeps standard technical logs (such as IP address and browser type) briefly, for security and reliability. We do not run analytics, and we do not build a profile of you.</Row>
            <Row h="Cookies and tracking">Paksh does not set advertising or analytics cookies, and does not track you across other websites. The site works without storing tracking cookies on your device, so there is nothing here to switch off. If we introduce advertising (through Google AdSense) in future, we will update this policy and ask for your consent before any advertising cookies are set.</Row>
            <Row h="How we use information">To respond to your messages, and to keep the site secure and reliable. If we add advertising in future, it would help support the site. We do not sell your personal information, and we do not profile you.</Row>
            <Row h="Third parties">We rely on Formspree (which processes contact-form messages) and Vercel (which hosts the site). If we add advertising in future, Google would also process data under its own policy, and we will note that here before it happens.</Row>
            <Row h="Your choices">You may ask us to access or delete the information you sent through the contact form. Reach us any time via the Contact page.</Row>
            <Row h="Children">Paksh is a general news service and is not directed at children.</Row>
            <Row h="Changes">We may update this policy from time to time; material changes will be reflected by the date shown above.</Row>
          </div>
        </PageWrap>
      );
    }
    function SearchPage({ t, lang, query, setQuery, results, open }) {
      return (
        <PageWrap>
          <h1 className={`headline mb-5 text-[30px] sm:text-[40px] ${t.tp} ${readCls(lang)}`} style={{letterSpacing:lang==="hi"?0:"-0.018em"}}>{ui("searchTab",lang)}</h1>
          <div className="mb-8 max-w-xl">
            <div className="relative">
              <Search size={17} className={`absolute left-3 top-1/2 -translate-y-1/2 ${t.tf}`} />
              <input autoFocus value={query||""} onChange={e=>setQuery(e.target.value)} placeholder={STR[lang].search} className={`w-full border py-2.5 pl-10 pr-3 text-[15px] outline-none ${t.surface} ${t.border} focus:border-[#15140F] ${t.tp} ${lang==="hi"?"deva":""}`} />
            </div>
          </div>
          {!query.trim() ? <div className={`py-24 text-center ${t.tf} ${isHi(lang)}`}>{ui("searchHint",lang)}</div>
            : results.length ? <GridGrid items={results} t={t} lang={lang} render={(s)=><GridCard key={s.id} story={s} t={t} lang={lang} onOpen={open}/>} />
            : <div className={`py-24 text-center ${t.tf} ${isHi(lang)}`}><p className={`text-lg font-bold ${t.ts}`}>{STR[lang].noResults}</p><p className="mt-1 text-sm">{STR[lang].noResultsSub}</p></div>}
        </PageWrap>
      );
    }
    function FeedSkeleton({ t }) {
      return (
        <div className="mx-auto max-w-[1280px] px-4 sm:px-10 py-6">
          <div className="py-[7px]" style={{borderTop:`2px solid ${t.ink}`,borderBottom:`1px solid ${t.ink}`}}><div className="skel h-3 w-40"/></div>
          <div className="grid lg:grid-cols-[250px_1fr_280px]" style={{borderBottom:`2px solid ${t.ink}`}}>
            <div className="order-2 lg:order-1 py-6 lg:pr-7 lg:border-r space-y-4" style={{borderColor:t.line}}>{[0,1].map(i=><div key={i} className="space-y-2"><div className="skel h-5 w-full"/><div className="skel h-3 w-24"/></div>)}</div>
            <div className="order-1 lg:order-2 py-6 lg:px-7 lg:border-r" style={{borderColor:t.line}}><div className="skel h-11 w-full mb-2.5"/><div className="skel h-11 w-4/5 mb-5"/><div className="skel h-24 w-full"/></div>
            <div className="order-3 py-6 lg:pl-7 space-y-3">{[0,1,2].map(i=><div key={i} className="skel h-4 w-full"/>)}</div>
          </div>
        </div>
      );
    }

    /* ---------------- routing + app ---------------- */
    function parsePath(){
      const p=(typeof window!=="undefined"?(window.location.pathname||"/"):"/");
      const seg=p.split("/").filter(Boolean);
      if(seg[0]==="story"&&seg[1]) return {view:"story", id:decodeURIComponent(seg[1])};
      if(seg[0]==="topic"&&seg[1]) return {view:"topic", topic:decodeURIComponent(seg[1])};
      if(seg.length===1 && ["blindspot","topics","sources","about","search","contact","privacy"].includes(seg[0])) return {view:seg[0]};
      return {view:"home"};
    }
    function PakshApp() {
      const [route,setRoute]=useState(parsePath());
      const [lang,setLang]=useState("en");
      const [dark,setDark]=useState(false);
      const [query,setQuery]=useState("");
      const [data,setData]=useState({events:[],blindspots:[],gaps:{left:[],right:[],agg:{}},topics:[],sources:[],summary:{}});
      const [detail,setDetail]=useState({});
      const [ready,setReady]=useState(false);

      useEffect(()=>{ loadAll().then(d=>{ setData(d); setReady(true); }); },[]);
      useEffect(()=>{ const on=()=>setRoute(parsePath()); window.addEventListener("popstate",on); return ()=>window.removeEventListener("popstate",on); },[]);
      useEffect(()=>{ document.documentElement.classList.toggle("dark",dark); document.body.style.backgroundColor=dark?"#1A1917":"#EAE6DB"; },[dark]);
      useEffect(()=>{ window.scrollTo(0,0); if(route.view==="story"&&route.id&&!detail[route.id]){ apiGet("events/"+route.id).then(full=>setDetail(d=>({...d,[route.id]:full}))).catch(()=>{ const f=(data.events||[]).concat(data.blindspots||[]).find(x=>String(x.id)===String(route.id)); if(f) setDetail(d=>({...d,[route.id]:f})); }); } },[route,data]);

      const t=dark?TOKENS.dark:TOKENS.light;
      const nav=(path)=>{ if(window.location.pathname!==path){ window.history.pushState(null,"",path); } setRoute(parsePath()); };
      const go=(v)=> nav(v==="home"?"/":"/"+v);
      const open=(id)=> nav("/story/"+encodeURIComponent(id));
      const goTopic=(tp)=> nav("/topic/"+encodeURIComponent(tp));

      const baseCards=data.events.map(e=>toCard(e,lang)).filter(c=>c.srclang===lang);
      const baseOne=data.blindspots.map(e=>toCard(e,lang)).filter(c=>c.srclang===lang);
      const gapL=(data.gaps.left||[]).map(e=>toCard(e,lang)).filter(c=>c.srclang===lang);
      const gapR=(data.gaps.right||[]).map(e=>toCard(e,lang)).filter(c=>c.srclang===lang);
      const gapAgg=data.gaps.agg||{};
      // --- India-first home ranking ------------------------------------------
      // Top Stories is strictly India-centric. Foreign stories (region "World", set
      // per-event by the pipeline) and Sports live in their own Sections, NOT on the
      // home feed. To allow world news back on the home, drop the region check below.
      const HOME_EXCLUDE_TOPICS = ["Sports"];
      const [regionFilter, setRegionFilter] = useState("National");
      const ageHours=c=>{ const tt=_ts(c.created_at); return isNaN(tt)?9999:Math.max(0,(Date.now()-tt)/3600000); };
      // Home feed leads by the EXPORT-TIME importance score (see export_static._importance):
      // distinct outlets across left/centre/right, decayed by recency. It is computed in
      // the pipeline (not here), carries no topic weighting, and is a plain field on each
      // event. The previous in-browser rank() with per-topic CIVIC weights was removed so
      // ordering is arithmetic and explainable. Ties fall back to newest-first.
      const rank=c=>(typeof c.importance==="number"?c.importance:0);
      const homeFilter=c=>{ if (HOME_EXCLUDE_TOPICS.includes(c.topic)) return false; const isWorld=(c.region||"India")==="World"; return regionFilter==="International"?isWorld:!isWorld; };
      const homeCards=baseCards.filter(homeFilter).sort((a,b)=>(rank(b)-rank(a))||(ageHours(a)-ageHours(b)));
      const homeOne=baseOne.filter(homeFilter).sort((a,b)=>(rank(b)-rank(a))||(ageHours(a)-ageHours(b)));
      // sections / search / topic pages: newest-first so new articles always show there too
      baseCards.sort((a,b)=>ageHours(a)-ageHours(b)); baseOne.sort((a,b)=>ageHours(a)-ageHours(b));
      const countsByTopic={}; baseCards.forEach(c=>{ const k=c.topic||"Society"; countsByTopic[k]=(countsByTopic[k]||0)+1; });
      const topicsOrdered=Object.keys(countsByTopic).sort((a,b)=>countsByTopic[b]-countsByTopic[a]);
      const lastTs=(data.events||[]).reduce((mx,e)=>{ const ts=Date.parse(e.created_at||""); return isNaN(ts)?mx:Math.max(mx,ts); },0);
      const stats={ stories:homeCards.length, outlets:(data.sources||[]).length,
        gaps:(gapAgg.total!=null?gapAgg.total:(gapL.length+gapR.length)),
        updated:(lastTs?new Date(lastTs).toISOString():""),
        regionFilter, setRegionFilter };
      // Roster size per lean (distinct outlets tracked), for the Coverage-Gaps rate columns.
      const rosterByLean={left:0,center:0,right:0};
      (data.sources||[]).forEach(s=>{ if(rosterByLean[s.lean]!=null) rosterByLean[s.lean]++; });
      const q=query.trim().toLowerCase();
      const results=q?baseCards.filter(c=>(c.headline||"").toLowerCase().includes(q)):[];
      const story = route.view==="story" ? (detail[route.id]?toDetail(detail[route.id],lang):null) : null;
      const headerView = route.view==="story" ? "" : route.view;

      return (
        <div className={`min-h-screen font-sans ${t.bg} ${t.tp}`}>
          <Header t={t} lang={lang} setLang={setLang} dark={dark} setDark={setDark} go={go} view={headerView} />
          <div className="pb-24 md:pb-10">
            {!ready ? <FeedSkeleton t={t} />
            : route.view==="story" ? (story ? <StoryPage story={story} t={t} lang={lang} go={go} openTopic={goTopic} /> : <FeedSkeleton t={t} />)
            : route.view==="blindspot" ? <BlindspotPage left={gapL} right={gapR} roster={rosterByLean} agg={gapAgg} stats={stats} t={t} lang={lang} open={open} go={go} />
            : route.view==="topics" ? <TopicsHub topics={topicsOrdered} counts={countsByTopic} t={t} lang={lang} goTopic={goTopic} />
            : route.view==="topic" ? <TopicPage topic={route.topic} items={baseCards.filter(c=>c.topic===route.topic)} t={t} lang={lang} open={open} go={go} />
            : route.view==="sources" ? <SourcesPage t={t} lang={lang} sources={data.sources} />
            : route.view==="about" ? <AboutPage t={t} lang={lang} agg={gapAgg} />
            : route.view==="contact" ? <ContactPage t={t} lang={lang} />
            : route.view==="privacy" ? <PrivacyPage t={t} lang={lang} />
            : route.view==="search" ? <SearchPage t={t} lang={lang} query={query} setQuery={setQuery} results={results} open={open} />
            : (!homeCards.length ? <PageWrap><div className={`py-28 text-center ${t.tf} ${isHi(lang)}`}>{STR[lang].noStories}</div></PageWrap>
               : <HomeView cards={homeCards} gapLeft={gapL} gapRight={gapR} topics={topicsOrdered} counts={countsByTopic} stats={stats} t={t} lang={lang} open={open} goTopic={goTopic} go={go} />)}
          </div>
          {route.view!=="story" && <Footer t={t} lang={lang} go={go} />}
          <BottomNav t={t} lang={lang} view={headerView} go={go} />
        </div>
      );
    }
    ReactDOM.createRoot(document.getElementById("root")).render(<PakshApp />);