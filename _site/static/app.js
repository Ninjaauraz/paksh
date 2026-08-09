const {
  useState,
  useEffect,
  useMemo
} = React;
/* ---------------- icons ---------------- */
const Search = p => /*#__PURE__*/React.createElement("svg", {
  width: p.size || 24,
  height: p.size || 24,
  className: p.className || "",
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: "2",
  strokeLinecap: "round",
  strokeLinejoin: "round"
}, /*#__PURE__*/React.createElement("circle", {
  cx: "11",
  cy: "11",
  r: "8"
}), /*#__PURE__*/React.createElement("path", {
  d: "m21 21-4.3-4.3"
}));
const Sun = p => /*#__PURE__*/React.createElement("svg", {
  width: p.size || 24,
  height: p.size || 24,
  className: p.className || "",
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: "2",
  strokeLinecap: "round",
  strokeLinejoin: "round"
}, /*#__PURE__*/React.createElement("circle", {
  cx: "12",
  cy: "12",
  r: "4"
}), /*#__PURE__*/React.createElement("path", {
  d: "M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"
}));
const Moon = p => /*#__PURE__*/React.createElement("svg", {
  width: p.size || 24,
  height: p.size || 24,
  className: p.className || "",
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: "2",
  strokeLinecap: "round",
  strokeLinejoin: "round"
}, /*#__PURE__*/React.createElement("path", {
  d: "M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"
}));
const ArrowLeft = p => /*#__PURE__*/React.createElement("svg", {
  width: p.size || 24,
  height: p.size || 24,
  className: p.className || "",
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: "2",
  strokeLinecap: "round",
  strokeLinejoin: "round"
}, /*#__PURE__*/React.createElement("path", {
  d: "m12 19-7-7 7-7"
}), /*#__PURE__*/React.createElement("path", {
  d: "M19 12H5"
}));
const Eye = p => /*#__PURE__*/React.createElement("svg", {
  width: p.size || 24,
  height: p.size || 24,
  className: p.className || "",
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: p.strokeWidth || 2,
  strokeLinecap: "round",
  strokeLinejoin: "round"
}, /*#__PURE__*/React.createElement("path", {
  d: "M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"
}), /*#__PURE__*/React.createElement("circle", {
  cx: "12",
  cy: "12",
  r: "3"
}));
const Sparkles = p => /*#__PURE__*/React.createElement("svg", {
  width: p.size || 24,
  height: p.size || 24,
  className: p.className || "",
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: "2",
  strokeLinecap: "round",
  strokeLinejoin: "round"
}, /*#__PURE__*/React.createElement("path", {
  d: "m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3L12 3Z"
}));
const Layers = p => /*#__PURE__*/React.createElement("svg", {
  width: p.size || 24,
  height: p.size || 24,
  className: p.className || "",
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: "2",
  strokeLinecap: "round",
  strokeLinejoin: "round"
}, /*#__PURE__*/React.createElement("path", {
  d: "m12 2 3 7h7l-5 5 2 7-7-4-7 4 2-7-5-5h7z"
}));
const ChevronRight = p => /*#__PURE__*/React.createElement("svg", {
  width: p.size || 24,
  height: p.size || 24,
  className: p.className || "",
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: "2",
  strokeLinecap: "round",
  strokeLinejoin: "round"
}, /*#__PURE__*/React.createElement("path", {
  d: "m9 18 6-6-6-6"
}));
const Menu = p => /*#__PURE__*/React.createElement("svg", {
  width: p.size || 24,
  height: p.size || 24,
  className: p.className || "",
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: "2",
  strokeLinecap: "round",
  strokeLinejoin: "round"
}, /*#__PURE__*/React.createElement("line", {
  x1: "4",
  x2: "20",
  y1: "12",
  y2: "12"
}), /*#__PURE__*/React.createElement("line", {
  x1: "4",
  x2: "20",
  y1: "6",
  y2: "6"
}), /*#__PURE__*/React.createElement("line", {
  x1: "4",
  x2: "20",
  y1: "18",
  y2: "18"
}));
const X = p => /*#__PURE__*/React.createElement("svg", {
  width: p.size || 24,
  height: p.size || 24,
  className: p.className || "",
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: "2",
  strokeLinecap: "round",
  strokeLinejoin: "round"
}, /*#__PURE__*/React.createElement("path", {
  d: "M18 6 6 18"
}), /*#__PURE__*/React.createElement("path", {
  d: "m6 6 12 12"
}));
const Scale = p => /*#__PURE__*/React.createElement("svg", {
  width: p.size || 24,
  height: p.size || 24,
  className: p.className || "",
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: "2",
  strokeLinecap: "round",
  strokeLinejoin: "round"
}, /*#__PURE__*/React.createElement("path", {
  d: "m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"
}), /*#__PURE__*/React.createElement("path", {
  d: "m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"
}), /*#__PURE__*/React.createElement("path", {
  d: "M7 21h10M12 3v18M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"
}));
const Home = p => /*#__PURE__*/React.createElement("svg", {
  width: p.size || 24,
  height: p.size || 24,
  className: p.className || "",
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: "2",
  strokeLinecap: "round",
  strokeLinejoin: "round"
}, /*#__PURE__*/React.createElement("path", {
  d: "M3 10.5 12 3l9 7.5"
}), /*#__PURE__*/React.createElement("path", {
  d: "M5 9.5V21h14V9.5"
}));
const Grid = p => /*#__PURE__*/React.createElement("svg", {
  width: p.size || 24,
  height: p.size || 24,
  className: p.className || "",
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: "2",
  strokeLinecap: "round",
  strokeLinejoin: "round"
}, /*#__PURE__*/React.createElement("rect", {
  x: "3",
  y: "3",
  width: "7",
  height: "7",
  rx: "1.5"
}), /*#__PURE__*/React.createElement("rect", {
  x: "14",
  y: "3",
  width: "7",
  height: "7",
  rx: "1.5"
}), /*#__PURE__*/React.createElement("rect", {
  x: "3",
  y: "14",
  width: "7",
  height: "7",
  rx: "1.5"
}), /*#__PURE__*/React.createElement("rect", {
  x: "14",
  y: "14",
  width: "7",
  height: "7",
  rx: "1.5"
}));

/* ---------------- config ---------------- */
// Each side carries a COLOUR (mid-tone hex, for dots/badges) and a TEXTURE class
// (seg-*, defined in styles.css with an oklch value + hex fallback). All three
// sit at equal lightness; only hue + texture separate them, so no side reads louder.
const BIAS = {
  left: {
    color: "#4A6E80",
    tex: "seg-left",
    soft: "#E3E8EA",
    en: "Left",
    hi: "वाम"
  },
  center: {
    color: "#7E7768",
    tex: "seg-center",
    soft: "#ECE9E1",
    en: "Centre",
    hi: "केंद्र"
  },
  right: {
    color: "#96603F",
    tex: "seg-right",
    soft: "#EFE3DB",
    en: "Right",
    hi: "दक्षिण"
  },
  international: {
    color: "#5E7E78",
    tex: "",
    soft: "#E3EAE8",
    en: "International",
    hi: "अंतरराष्ट्रीय"
  }
};
// Editorial tonality axes (0-100), set per PUBLISHER by editors in sources.py -
// additive detail alongside the arithmetic Left/Centre/Right bias bar, never a
// per-article or AI-decided score. Each value is a position between two named poles.
const AXES = [{
  key: "secular_authoritative",
  color: "#4A6E80",
  en: {
    name: "Ideological",
    lo: "Authoritative",
    hi: "Secular"
  },
  hi: {
    name: "वैचारिक",
    lo: "सत्तावादी",
    hi: "धर्मनिरपेक्ष"
  }
}, {
  key: "market_orientation",
  color: "#7E7768",
  en: {
    name: "Economic",
    lo: "State-leaning",
    hi: "Pro-market"
  },
  hi: {
    name: "आर्थिक",
    lo: "राज्य-समर्थक",
    hi: "बाज़ार-समर्थक"
  }
}, {
  key: "incumbent_stance",
  color: "#96603F",
  en: {
    name: "Establishment",
    lo: "Critical",
    hi: "Pro-govt"
  },
  hi: {
    name: "सत्ता के प्रति",
    lo: "आलोचनात्मक",
    hi: "सत्ता-समर्थक"
  }
}];
const TOKENS = {
  light: {
    bg: "bg-[#EAE6DB]",
    surface: "bg-[#F4F1EA]",
    soft: "bg-[#EFEBE1]",
    border: "border-[#D8D3C6]",
    tp: "text-[#15140F]",
    ts: "text-[#3A372F]",
    tf: "text-[#8A8371]",
    brand: "text-[#15140F]",
    brandBg: "bg-[#15140F]",
    blind: "text-[#75442E]",
    blindSoft: "bg-[#EFE3DB]",
    nav: "glass-nav-light",
    cta: "bg-[#15140F]",
    ctaT: "text-[#F4F1EA]",
    line: "#D8D3C6",
    ink: "#15140F",
    chip: "bg-[#EAE6DB]",
    centerSeg: "#8C8579",
    track: "#EAE6DB",
    gap: "#F4F1EA"
  },
  dark: {
    bg: "bg-[#1A1917]",
    surface: "bg-[#201F1C]",
    soft: "bg-[#262420]",
    border: "border-[#35322C]",
    // tf was #847E72 = 4.36:1 on the dark surface, just under WCAG AA (4.5). #948E7E clears
    // AA (~5:1 on bg, ~4.7:1 on the soft card) while staying visibly "faint".
    tp: "text-[#EDEAE2]",
    ts: "text-[#B7B1A4]",
    tf: "text-[#948E7E]",
    brand: "text-[#EDEAE2]",
    brandBg: "bg-[#EDEAE2]",
    blind: "text-[#C89170]",
    blindSoft: "bg-[#2E2019]",
    nav: "glass-nav-dark",
    cta: "bg-[#EDEAE2]",
    ctaT: "text-[#201F1C]",
    line: "#35322C",
    ink: "#EDEAE2",
    chip: "bg-[#2A2823]",
    centerSeg: "#8C8579",
    track: "#2A2823",
    gap: "#1A1917"
  }
};
const TOPIC_HI = {
  Politics: "राजनीति",
  Economy: "अर्थव्यवस्था",
  International: "अंतरराष्ट्रीय",
  Sports: "खेल",
  "Crime & Law": "अपराध व कानून",
  "Science & Tech": "विज्ञान व तकनीक",
  Health: "स्वास्थ्य",
  Entertainment: "मनोरंजन",
  Environment: "पर्यावरण",
  Society: "समाज",
  General: "सामान्य"
};
const SIGNALS = [{
  en: "Editorial stance",
  hi: "संपादकीय रुख",
  w: 30
}, {
  en: "Framing & word choice",
  hi: "फ़्रेमिंग और शब्द-चयन",
  w: 25
}, {
  en: "Story selection",
  hi: "खबरों का चयन",
  w: 20
}, {
  en: "Sourcing & who they quote",
  hi: "स्रोत और उद्धरण",
  w: 10
}, {
  en: "Ownership & affiliations",
  hi: "स्वामित्व और संबद्धता",
  w: 10
}, {
  en: "Cross-spectrum panel check",
  hi: "क्रॉस-स्पेक्ट्रम पैनल जाँच",
  w: 5
}];
const M_READ = {
  en: ["The coloured bar shows how many of the covering outlets lean Left, Centre or Right.", "“Coverage Gaps” marks a story that outlets on one side of the spectrum covered while few or none on the other did, shown with the full Left · Centre · Right count.", "The neutral summary is generated automatically from the outlets' own coverage; the outlet labels and the counts come from editors and the registry, not the summary engine."],
  hi: ["रंगीन बार दिखाता है कि कवर करने वाले कितने आउटलेट वाम, केंद्र या दक्षिण की ओर हैं।", "“कवरेज गैप” उस खबर को चिह्नित करता है जिसे स्पेक्ट्रम के एक तरफ़ के आउटलेट्स ने कवर किया पर दूसरी तरफ़ के बहुत कम या किसी ने नहीं, पूरे वाम · केंद्र · दक्षिण आँकड़े के साथ।", "तटस्थ सारांश आउटलेट्स की अपनी कवरेज से स्वचालित रूप से तैयार होता है; आउटलेट के लेबल और गिनती संपादकों और रजिस्ट्री से आती है, सारांश इंजन से नहीं।"]
};
const CONTACT = "corrections@paksh.example"; // <-- change to your real address
const FORMSPREE_ENDPOINT = "https://formspree.io/f/mkolqann";
// Google AdSense publisher id, e.g. "ca-pub-1234567890123456". Empty = ads OFF: slots
// render as clean labelled placeholders and NO ad script/cookie loads (privacy-safe).
// To go live: set this, and uncomment the AdSense loader <script> in static/index.html.
const ADSENSE_CLIENT = "";

// --- Reader support (visible now; the CTA works the moment you fill these in) ----------
// Paksh is reader-supported. Fill in whichever you use - leave the rest "". While ALL are
// empty the Support page still shows the pitch but says "coming soon" instead of a dead
// button. `upi` = your UPI id (e.g. "paksh@okhdfcbank"); `url` = a Razorpay/Buy-Me-a-Coffee
// /donation page; `payeeName` labels the UPI intent. Nothing here loads a tracker or cookie.
const SUPPORT = {
  upi: "",
  url: "",
  payeeName: "Paksh"
};
const supportReady = () => !!(SUPPORT.upi || SUPPORT.url);
// A UPI deep link that opens the user's UPI app pre-filled (no amount forced).
const upiLink = () => SUPPORT.upi ? `upi://pay?pa=${encodeURIComponent(SUPPORT.upi)}&pn=${encodeURIComponent(SUPPORT.payeeName || "Paksh")}&cu=INR` : "";

// --- Sponsorship (stays INVISIBLE until you actually have a sponsor) -------------------
// Unlike reader support, an empty "Supported by ___" slot looks broken, so this renders
// NOTHING until a sponsor is configured. Fill one in only when a deal is signed.
const SPONSOR = {
  name: "",
  url: "",
  line: ""
}; // e.g. {name:"Acme", url:"https://…", line:"Media literacy for all"}

const UI = {
  seeAll: {
    en: "See all",
    hi: "सभी देखें"
  },
  top: {
    en: "Top",
    hi: "मुख्य"
  },
  sections: {
    en: "Sections",
    hi: "खंड"
  },
  oneSided: {
    en: "One-Sided",
    hi: "एकतरफ़ा"
  },
  searchTab: {
    en: "Search",
    hi: "खोज"
  },
  browse: {
    en: "Browse by topic",
    hi: "विषय से देखें"
  },
  searchHint: {
    en: "Search across all coverage",
    hi: "सभी कवरेज में खोजें"
  },
  groupBy: {
    en: "Group by",
    hi: "समूह"
  },
  gLean: {
    en: "Lean",
    hi: "झुकाव"
  },
  gLang: {
    en: "Language",
    hi: "भाषा"
  },
  gRegion: {
    en: "Region",
    hi: "क्षेत्र"
  },
  findOutlet: {
    en: "Find an outlet…",
    hi: "आउटलेट खोजें…"
  },
  National: {
    en: "National",
    hi: "राष्ट्रीय"
  },
  Regional: {
    en: "Regional",
    hi: "क्षेत्रीय"
  },
  International: {
    en: "International",
    hi: "अंतरराष्ट्रीय"
  },
  registry: {
    en: "outlets tracked",
    hi: "आउटलेट"
  },
  expandAll: {
    en: "Expand all",
    hi: "सभी खोलें"
  },
  collapseAll: {
    en: "Collapse all",
    hi: "सभी बंद करें"
  },
  noOutlets: {
    en: "No outlets match.",
    hi: "कोई आउटलेट नहीं मिला।"
  }
};
const ui = (k, lang) => (UI[k] || {})[lang] || (UI[k] || {}).en || k;
const STR = {
  en: {
    navTop: "Top Stories",
    navOS: "Coverage Gaps",
    navSrc: "Sources",
    navMethod: "Method",
    search: "Search coverage…",
    tagline: "Compare how India's media covers each story, every side, side by side.",
    topNews: "Top Stories",
    osTitle: "Coverage Gaps",
    osSub: "A coverage gap is a story that outlets on one side of the spectrum covered while few or none on the other did. Paksh flags these by counting distinct outlets per lean, the same counts as the bias bar, and shows the full Left · Centre · Right tally on each. It's arithmetic, not a judgment about any outlet or about why a story was or wasn't covered. Outlets also differ in how much they publish, so an absence of coverage on one side may reflect an outlet's publishing volume rather than a deliberate omission.",
    gapLeftHead: "Covered more by Left-leaning outlets",
    gapRightHead: "Covered more by Right-leaning outlets",
    gapShowing: "Showing the {n} most lopsided of {total}",
    gapCovered: "Covered by",
    m_gapH: "How coverage gaps break down",
    m_gap: "Of the {total} stories Paksh flags as one-sided, {rh} are covered mainly by right-leaning outlets and {lh} mainly by left-leaning. This is not a measure of which side ignores more news. Paksh counts {lo} left-leaning and {ro} right-leaning outlets on India's spectrum, but they publish at very different volumes, the right-leaning set includes several high-volume TV and mass-market outlets, so right-leaning outlets appear about twice as often across all stories. Most of this imbalance reflects that volume difference, not editorial choice.",
    more: "More Top Stories",
    resultsFor: "Results for",
    noResults: "No stories match your search.",
    noResultsSub: "Try different keywords or browse top news.",
    noStories: "No stories to show right now. Please check back soon.",
    seeCoverage: "See coverage",
    most: "Most coverage",
    even: "Fairly even coverage",
    sources: "sources",
    source: "source",
    onlyLabel: "Only",
    back: "Back to feed",
    aiSummary: "Paksh neutral summary",
    aiSub: "neutral synthesis",
    autoTag: "Auto-summary",
    autoFrom: "from coverage",
    autoNote: "This headline comes straight from a covering outlet, a neutral Paksh summary is being prepared.",
    unratedTitle: "Unrated outlets",
    unratedNote: "Outlets we found covering this story but don't rate yet, they add coverage but don't affect the bias bar.",
    intlTitle: "International coverage",
    intlNote: "Foreign wire services (Reuters, AP, BBC…) covering this story, they add coverage but aren't rated on India's spectrum, so they don't affect the bias bar.",
    framingTitle: "How each side is framing it",
    framingSub: "A neutral read of what each side's coverage emphasises, based on the headlines collected, not opinion.",
    framingPending: "The side-by-side framing comparison appears once a full summary is generated for this story.",
    framingThin: "Not enough unique coverage to create a summary.",
    sideBySide: "Side by Side",
    coverageBreakdown: "Coverage Breakdown",
    totalSources: "Total news sources",
    whereLean: "Where the sources lean",
    aiNote: "Lean describes each publisher and is set by Paksh's editors, not generated per story. Summaries are generated automatically from the outlets' own coverage; the counts come from the sources.",
    osCalloutBody1: "Only",
    osCalloutBody2: "of the covering outlets lean this way, a count of outlets, not a judgment about why a side did or didn't cover it.",
    srcTitle: "Source ratings",
    srcIntro: "Every outlet Paksh tracks, how it's rated, and why.",
    srcDisclaimer: "All ratings are provisional, a documented starting point reviewed against our rubric, not a final verdict. Lean describes the publication, not any single article, and is open to appeal.",
    filterLean: "Lean",
    filterLang: "Language",
    langEN: "English",
    langHI: "Hindi",
    all: "All",
    ownership: "Ownership",
    whyRated: "Why this rating",
    signals: "Signals",
    confidence: "confidence",
    contested: "Contested",
    provisional: "Provisional",
    suggestFix: "Suggest a correction",
    methodTitle: "How Paksh works",
    m_doesH: "What Paksh does",
    m_does: "Paksh groups coverage of the same story from outlets across the spectrum, shows a neutral summary, and shows which sides are covering it, so you can see the whole picture and what your usual sources leave out.",
    m_ruleH: "The golden rule",
    m_rule: "A lean label belongs to the publication, not to any single article, and never to an algorithm. Paksh editors assign each outlet a lean using a fixed rubric. The automated summary only describes the coverage; it never decides anyone's politics. A story's bias bar is simple arithmetic: we count how many covering outlets fall on each side. And it is one vote per owner: when two mastheads share a parent company, say The Times of India and Navbharat Times, both Times Group, they count once on their side, so a single company cannot tilt the bar by publishing the same story under several names. We still show every masthead that covered the story; they just share one vote, which is why a story can read “9 publishers · 13 mastheads” on a side.",
    m_aiH: "What the software does, and never does",
    m_ai: "Automation does exactly three things at Paksh, and no more: it groups articles about the same event into one story, writes the neutral summary, and drafts the per-side framing notes from the collected headlines. That is the entire role of the model. It never assigns an outlet's lean, never decides the bias bar, and never weighs one outlet more than another, those are fixed, editor-set labels and plain counts. If the summary engine is momentarily unavailable, a story still publishes with a headline taken straight from a covering outlet, clearly marked as automatic, rather than waiting.",
    m_orderH: "How the home feed is ordered",
    m_order: "The front page is India-first. Stories are ranked by how many distinct outlets across the spectrum are covering them, decayed by how recent they are, so a broadly-covered breaking story leads and yesterday's fades. On top of that arithmetic, the coverage that matters most to an Indian reader, politics and governance, the economy, the courts, big movements and amendments, is given priority over high-volume sport and entertainment, which sit in their own sections. No story is promoted or buried because of its politics; the weighting is a fixed, published rule, not an editorial thumb on the scale for any side.",
    m_freshH: "How current a story is",
    m_fresh: "The time on each story is the real publish time of its newest source article, not when our software last touched it, so “updated 2h ago” means the news itself is about two hours old. Paksh refreshes continuously as new coverage arrives; a story's bar and summary keep updating as more outlets pick it up.",
    m_rateH: "How we rate a publication",
    m_rateLede: "We rate each publication on six signals, each scored from −2 to +2 and combined into one score from −10 (left) to +10 (right):",
    m_rateFoot: "Scores near zero are Centre; the further from zero, the stronger the lean.",
    m_axisH: "What “Left” and “Right” mean in India",
    m_axis: "In India, Left and Right aren't only about economics. Paksh blends a social-and-ideological axis (secular ↔ Hindutva) with an institutional one (critical of ↔ aligned with the incumbent), and tracks economic stance separately. “Left” and “Right” are descriptive, not insults, and the same scrutiny is applied across the spectrum.",
    m_partiesH: "Where India's parties roughly sit",
    m_parties: "These labels describe ideas, not teams, and they're rough, because parties shift over time and many regional parties don't fit neatly on one line. As a common-usage guide: the Left includes communist and socialist parties such as CPI(M) and CPI, and is associated with secular, pro-welfare, labour-first positions; the Right, most prominently the BJP, is associated with Hindutva-influenced cultural nationalism and a more market-friendly economic stance; the Centre spans the middle, where the Congress is often described as centre-left and many regional parties mix positions by issue. Remember: Paksh rates news outlets, not parties, an outlet's lean is about how it covers the news, not who it votes for.",
    m_provH: "Confidence, contested & provisional",
    m_prov: "Every rating today is provisional: a documented starting point based on ownership, self-described stance and well-established reputation, reviewed against the rubric, not a final verdict. Each shows a confidence level, and some are flagged Contested where lean is genuinely debated or ownership recently changed.",
    m_readH: "How to read a Paksh story",
    m_appealH: "Corrections & appeals",
    m_appeal: "Think a rating is wrong? Tell us the outlet, the rating you dispute, and a few specific examples, headlines or articles, and we'll re-review it against the rubric. Ratings are meant to be challenged.",
    footIndependence: "Paksh is an independent project and is not affiliated with any outlet shown. Lean labels are provisional and open to appeal."
  },
  hi: {
    navTop: "मुख्य खबरें",
    navOS: "कवरेज गैप",
    navSrc: "स्रोत",
    navMethod: "कार्यप्रणाली",
    search: "कवरेज खोजें…",
    tagline: "देखिए भारत का मीडिया हर खबर को कैसे कवर करता है, हर पक्ष, आमने-सामने।",
    topNews: "मुख्य खबरें",
    osTitle: "कवरेज गैप",
    osSub: "कवरेज गैप वह ख़बर है जिसे स्पेक्ट्रम के एक तरफ़ के आउटलेट्स ने कवर किया पर दूसरी तरफ़ के बहुत कम या किसी ने नहीं। पक्ष हर झुकाव के अलग-अलग आउटलेट्स गिनकर इन्हें चिह्नित करता है, वही गिनती जो बायस बार में है, और हर एक पर पूरा वाम · केंद्र · दक्षिण आँकड़ा दिखाता है। यह अंकगणित है, किसी आउटलेट या कवरेज के कारण पर निर्णय नहीं। आउटलेट अलग-अलग मात्रा में प्रकाशित करते हैं, इसलिए एक तरफ़ कवरेज की अनुपस्थिति जानबूझकर की गई चूक के बजाय उस आउटलेट के प्रकाशन-आयतन को दर्शा सकती है।",
    gapLeftHead: "ज़्यादातर वाम-झुकाव आउटलेट्स द्वारा कवर",
    gapRightHead: "ज़्यादातर दक्षिण-झुकाव आउटलेट्स द्वारा कवर",
    gapShowing: "{total} में से {n} सबसे असंतुलित दिखाई जा रही हैं",
    gapCovered: "कवर किया गया:",
    m_gapH: "कवरेज गैप का ब्यौरा",
    m_gap: "पक्ष जिन {total} ख़बरों को एकतरफ़ा चिह्नित करता है, उनमें से {rh} ज़्यादातर दक्षिण-झुकाव आउटलेट्स ने और {lh} ज़्यादातर वाम-झुकाव आउटलेट्स ने कवर कीं। यह इस बात का माप नहीं है कि कौन-सा पक्ष ज़्यादा ख़बरें अनदेखा करता है। पक्ष भारत के स्पेक्ट्रम पर {lo} वाम-झुकाव और {ro} दक्षिण-झुकाव आउटलेट गिनता है, पर वे बहुत अलग मात्रा में प्रकाशित करते हैं, दक्षिण-झुकाव समूह में कई उच्च-आयतन टीवी और मास-मार्केट आउटलेट हैं, इसलिए दक्षिण-झुकाव आउटलेट सभी ख़बरों में लगभग दोगुनी बार दिखते हैं। इस असंतुलन का ज़्यादातर हिस्सा उस आयतन-अंतर को दर्शाता है, संपादकीय चयन को नहीं।",
    more: "और मुख्य खबरें",
    resultsFor: "खोज परिणाम:",
    noResults: "आपकी खोज से मेल खाती कोई खबर नहीं।",
    noResultsSub: "अलग शब्द आज़माएँ या मुख्य खबरें देखें।",
    noStories: "अभी दिखाने के लिए कोई खबर नहीं है। कृपया थोड़ी देर बाद देखें।",
    seeCoverage: "कवरेज देखें",
    most: "सबसे ज़्यादा कवरेज",
    even: "लगभग बराबर कवरेज",
    sources: "स्रोत",
    source: "स्रोत",
    onlyLabel: "केवल",
    back: "फ़ीड पर वापस",
    aiSummary: "पक्ष तटस्थ सारांश",
    aiSub: "तटस्थ संश्लेषण",
    autoTag: "स्वतः सारांश",
    autoFrom: "कवरेज से",
    autoNote: "यह शीर्षक सीधे कवरेज करने वाले एक आउटलेट से लिया गया है, पक्ष का तटस्थ सारांश तैयार किया जा रहा है।",
    unratedTitle: "बिना रेटिंग वाले आउटलेट",
    unratedNote: "ऐसे आउटलेट जो इस ख़बर को कवर कर रहे हैं पर अभी रेटेड नहीं हैं, ये कवरेज जोड़ते हैं पर बायस बार को प्रभावित नहीं करते।",
    intlTitle: "अंतरराष्ट्रीय कवरेज",
    intlNote: "इस ख़बर को कवर करने वाली विदेशी समाचार एजेंसियाँ (Reuters, AP, BBC…), ये कवरेज जोड़ती हैं पर भारत के स्पेक्ट्रम पर रेटेड नहीं हैं, इसलिए बायस बार को प्रभावित नहीं करतीं।",
    framingTitle: "हर पक्ष इसे कैसे पेश कर रहा है",
    framingSub: "हर झुकाव की कवरेज किस बात पर ज़ोर दे रही है, इसका तटस्थ विश्लेषण, एकत्र की गई हेडलाइनों के आधार पर, राय नहीं।",
    framingPending: "इस ख़बर का पूरा सारांश तैयार होने पर पक्षों की तुलना यहाँ दिखाई देगी।",
    framingThin: "सारांश बनाने के लिए पर्याप्त स्वतंत्र कवरेज नहीं।",
    sideBySide: "आमने-सामने",
    coverageBreakdown: "कवरेज का ब्यौरा",
    totalSources: "कुल समाचार स्रोत",
    whereLean: "स्रोत किस ओर झुके हैं",
    aiNote: "झुकाव हर प्रकाशक का वर्णन करता है और पक्ष के संपादक तय करते हैं, हर खबर के लिए नहीं। सारांश आउटलेट्स की अपनी कवरेज से स्वचालित रूप से तैयार होते हैं; आँकड़े स्रोतों से आते हैं।",
    osCalloutBody1: "केवल",
    osCalloutBody2: "कवर करने वाले आउटलेट इस ओर झुके हैं, यह आउटलेट्स की गिनती है, इस बारे में निर्णय नहीं कि किसी पक्ष ने इसे क्यों कवर किया या नहीं।",
    srcTitle: "स्रोत रेटिंग",
    srcIntro: "पक्ष जिन आउटलेट्स को ट्रैक करता है, उनकी रेटिंग और कारण।",
    srcDisclaimer: "सभी रेटिंग अस्थायी हैं, रूब्रिक के विरुद्ध समीक्षित एक प्रलेखित शुरुआती बिंदु, अंतिम फ़ैसला नहीं। झुकाव प्रकाशन का वर्णन करता है, किसी एक लेख का नहीं, और अपील के लिए खुला है।",
    filterLean: "झुकाव",
    filterLang: "भाषा",
    langEN: "अंग्रेज़ी",
    langHI: "हिंदी",
    all: "सभी",
    ownership: "स्वामित्व",
    whyRated: "यह रेटिंग क्यों",
    signals: "संकेत",
    confidence: "विश्वास",
    contested: "विवादित",
    provisional: "अस्थायी",
    suggestFix: "सुधार सुझाएँ",
    methodTitle: "पक्ष कैसे काम करता है",
    m_doesH: "पक्ष क्या करता है",
    m_does: "पक्ष एक ही खबर की कवरेज को पूरे स्पेक्ट्रम के आउटलेट्स से इकट्ठा करता है, एक तटस्थ सारांश दिखाता है, और दिखाता है कि कौन-कौन से पक्ष इसे कवर कर रहे हैं, ताकि आप पूरी तस्वीर देख सकें और जान सकें कि आपके सामान्य स्रोत क्या छोड़ देते हैं।",
    m_ruleH: "मूल नियम",
    m_rule: "झुकाव का लेबल प्रकाशन का होता है, किसी एक लेख का नहीं, और कभी किसी एल्गोरिद्म का नहीं। पक्ष के संपादक एक निश्चित रूब्रिक से हर आउटलेट को झुकाव देते हैं। स्वचालित सारांश केवल कवरेज का वर्णन करता है; वह किसी की राजनीति तय नहीं करता। किसी खबर का बायस बार सीधा गणित है: हम गिनते हैं कि कवर करने वाले कितने आउटलेट किस ओर हैं। और यह एक-स्वामी-एक-वोट है: जब दो आउटलेट एक ही मूल कंपनी के हों, जैसे The Times of India और Navbharat Times, दोनों Times Group, तो वे अपने पक्ष में एक ही बार गिने जाते हैं, ताकि कोई एक कंपनी कई नामों से एक ही खबर छापकर बायस बार को झुका न सके। कवर करने वाला हर आउटलेट फिर भी दिखाया जाता है; बस उनका वोट एक साझा होता है, इसीलिए किसी पक्ष पर खबर “9 प्रकाशक · 13 मास्टहेड” पढ़ सकती है।",
    m_aiH: "सॉफ़्टवेयर क्या करता है, और क्या कभी नहीं करता",
    m_ai: "पक्ष पर स्वचालन ठीक तीन काम करता है, इससे ज़्यादा नहीं: एक ही घटना के लेखों को एक खबर में समूहित करना, तटस्थ सारांश लिखना, और एकत्र हेडलाइनों से हर पक्ष के फ़्रेमिंग नोट तैयार करना। मॉडल की भूमिका बस इतनी है। यह किसी आउटलेट का झुकाव तय नहीं करता, बायस बार तय नहीं करता, और किसी आउटलेट को दूसरे से ज़्यादा भार नहीं देता, वे निश्चित, संपादक-निर्धारित लेबल और सीधी गिनती हैं। यदि सारांश इंजन कुछ देर के लिए उपलब्ध न हो, तो खबर फिर भी एक कवर करने वाले आउटलेट से लिया गया शीर्षक (स्पष्ट रूप से स्वतः चिह्नित) के साथ प्रकाशित होती है, प्रतीक्षा नहीं करती।",
    m_orderH: "मुख्य फ़ीड किस क्रम में सजती है",
    m_order: "मुख्य पृष्ठ भारत-पहले है। खबरों को इस आधार पर क्रम दिया जाता है कि स्पेक्ट्रम भर के कितने अलग-अलग आउटलेट उन्हें कवर कर रहे हैं, और वे कितनी हाल की हैं, ताकि व्यापक रूप से कवर की गई ताज़ा खबर आगे रहे और पुरानी पीछे चली जाए। इस अंकगणित के ऊपर, भारतीय पाठक के लिए सबसे मायने रखने वाली कवरेज, राजनीति और शासन, अर्थव्यवस्था, अदालतें, बड़े आंदोलन और संशोधन, को उच्च-आयतन खेल और मनोरंजन से पहले प्राथमिकता दी जाती है, जो अपने अलग सेक्शन में रहते हैं। किसी खबर को उसकी राजनीति के कारण न आगे बढ़ाया जाता है न दबाया जाता है; यह भार एक निश्चित, प्रकाशित नियम है, किसी पक्ष के लिए संपादकीय पक्षपात नहीं।",
    m_freshH: "कोई खबर कितनी ताज़ा है",
    m_fresh: "हर खबर पर दिखने वाला समय उसमें शामिल सबसे नए स्रोत-लेख का वास्तविक प्रकाशन समय है, न कि जब हमारे सॉफ़्टवेयर ने उसे आख़िरी बार छुआ, इसलिए “2 घंटे पहले अपडेट” का अर्थ है कि खबर स्वयं लगभग दो घंटे पुरानी है। जैसे-जैसे नई कवरेज आती है पक्ष लगातार ताज़ा होता रहता है; जैसे-जैसे और आउटलेट इसे उठाते हैं, खबर का बार और सारांश अपडेट होते रहते हैं।",
    m_rateH: "हम किसी प्रकाशन को कैसे आँकते हैं",
    m_rateLede: "हम हर प्रकाशन को छह संकेतों पर आँकते हैं, हर एक को −2 से +2 तक अंक देकर एक स्कोर में जोड़ा जाता है, −10 (वाम) से +10 (दक्षिण):",
    m_rateFoot: "शून्य के पास के स्कोर केंद्र हैं; शून्य से जितना दूर, झुकाव उतना मज़बूत।",
    m_axisH: "भारत में “वाम” और “दक्षिण” का अर्थ",
    m_axis: "भारत में वाम और दक्षिण केवल अर्थशास्त्र के बारे में नहीं हैं। पक्ष एक सामाजिक-वैचारिक अक्ष (धर्मनिरपेक्ष ↔ हिंदुत्व) को एक संस्थागत अक्ष (सत्ता के आलोचक ↔ सत्ता के साथ) के साथ जोड़ता है, और आर्थिक रुख को अलग से देखता है। “वाम” और “दक्षिण” वर्णनात्मक हैं, अपमान नहीं, और एक ही कसौटी पूरे स्पेक्ट्रम पर लागू होती है।",
    m_partiesH: "भारत की पार्टियाँ मोटे तौर पर कहाँ हैं",
    m_parties: "ये लेबल विचारों का वर्णन करते हैं, टीमों का नहीं, और ये मोटे अनुमान हैं, क्योंकि पार्टियाँ समय के साथ बदलती हैं और कई क्षेत्रीय पार्टियाँ किसी एक रेखा पर ठीक से नहीं बैठतीं। आम समझ के अनुसार: वाम में CPI(M) और CPI जैसी कम्युनिस्ट और समाजवादी पार्टियाँ आती हैं, जो धर्मनिरपेक्ष और कल्याण-समर्थक, श्रमिक-पहले रुख से जुड़ी हैं; दक्षिण, सबसे प्रमुख रूप से भाजपा, हिंदुत्व-प्रभावित सांस्कृतिक राष्ट्रवाद और अधिक बाज़ार-समर्थक आर्थिक रुख से जुड़ी है; केंद्र बीच में फैला है, जहाँ कांग्रेस को अक्सर केंद्र-वाम कहा जाता है और कई क्षेत्रीय पार्टियाँ मुद्दे के हिसाब से रुख मिलाती हैं। याद रखें: पक्ष समाचार आउटलेट्स को आँकता है, पार्टियों को नहीं, किसी आउटलेट का झुकाव इस बारे में है कि वह खबरों को कैसे कवर करता है, इस बारे में नहीं कि वह किसे वोट देता है।",
    m_provH: "विश्वास, विवादित और अस्थायी",
    m_prov: "आज हर रेटिंग अस्थायी है: स्वामित्व, स्व-घोषित रुख और स्थापित प्रतिष्ठा पर आधारित एक प्रलेखित शुरुआती बिंदु, रूब्रिक के विरुद्ध समीक्षित, अंतिम फ़ैसला नहीं। हर एक के साथ एक विश्वास-स्तर दिखता है, और कुछ को ‘विवादित’ चिह्नित किया गया है जहाँ झुकाव सचमुच बहस में है या स्वामित्व हाल में बदला है।",
    m_readH: "पक्ष की खबर कैसे पढ़ें",
    m_appealH: "सुधार और अपील",
    m_appeal: "लगता है कोई रेटिंग ग़लत है? हमें आउटलेट, जिस रेटिंग से असहमत हैं, और कुछ ठोस उदाहरण, हेडलाइन या लेख, बताएँ, और हम उसे रूब्रिक के विरुद्ध फिर से देखेंगे। रेटिंग्स को चुनौती देने के लिए ही हैं।",
    footIndependence: "पक्ष एक स्वतंत्र परियोजना है और किसी दिखाए गए आउटलेट से संबद्ध नहीं है। झुकाव के लेबल अस्थायी हैं और अपील के लिए खुले हैं।"
  }
};

/* ---------------- analytics (consent-gated, cookieless) ---------------- */
// Vercel Web Analytics via its SCRIPT-TAG integration (not the npm/@vercel/analytics
// package, which needs a bundler Paksh deliberately doesn't have). It's cookieless, does
// no cross-site fingerprinting, and is aggregate - the privacy-first posture we chose.
// NOTHING loads or fires until the visitor accepts in the consent banner.
const consentState = () => {
  try {
    return localStorage.getItem("paksh-consent") || "";
  } catch (e) {
    return "";
  }
}; // "" | "granted" | "denied"
const loadVercelAnalytics = () => {
  if (window.__pakshVA || consentState() !== "granted") return;
  window.__pakshVA = true;
  window.va = window.va || function () {
    (window.vaq = window.vaq || []).push(arguments);
  };
  const s = document.createElement("script");
  s.defer = true;
  s.src = "/_vercel/insights/script.js";
  document.head.appendChild(s);
};
// track(name, props) - a no-op unless the user consented. Send only low-cardinality,
// non-identifying props (topic, side, device class) - NEVER the search query text, a URL,
// or anything that could single out a person. This is the one place events are emitted.
const track = (name, props) => {
  try {
    if (consentState() !== "granted" || typeof window.va !== "function") return;
    window.va("event", {
      name,
      ...(props || {})
    });
  } catch (e) {}
};
const deviceClass = () => {
  try {
    const w = window.innerWidth || 0;
    return w < 768 ? "mobile" : w < 1024 ? "tablet" : "desktop";
  } catch (e) {
    return "unknown";
  }
};

/* ---------------- "Your Paksh" — private, on-device personalization ----------------
   No account, no server, no network. Saved stories, followed topics and a private
   reading history live ONLY in this browser's localStorage; nothing ever leaves the
   device and nothing is tracked. Crucially, none of this touches the arithmetic bias
   bar - that stays a pure distinct-outlet count. The reading history is the reader's
   OWN consumption (which side each opened story leaned toward), shown back to them so
   they can SEE their spread and widen it. This is the mission made personal. */
const PS_KEYS = {
  saved: "paksh-saved",
  follow: "paksh-follow",
  hist: "paksh-hist"
};
const PStore = function () {
  const read = (k, def) => {
    try {
      const v = localStorage.getItem(k);
      return v ? JSON.parse(v) : def;
    } catch (e) {
      return def;
    }
  };
  const write = (k, v) => {
    try {
      localStorage.setItem(k, JSON.stringify(v));
    } catch (e) {}
  };
  let st = {
    saved: read(PS_KEYS.saved, []),
    follow: read(PS_KEYS.follow, []),
    hist: read(PS_KEYS.hist, [])
  };
  const subs = new Set();
  const emit = () => subs.forEach(fn => {
    try {
      fn();
    } catch (e) {}
  });
  return {
    subscribe: fn => {
      subs.add(fn);
      return () => subs.delete(fn);
    },
    saved: () => st.saved,
    follow: () => st.follow,
    hist: () => st.hist,
    isSaved: id => st.saved.indexOf(String(id)) >= 0,
    toggleSave: id => {
      id = String(id);
      const has = st.saved.indexOf(id) >= 0;
      const arr = has ? st.saved.filter(x => x !== id) : [id, ...st.saved];
      st = {
        ...st,
        saved: arr
      };
      write(PS_KEYS.saved, arr);
      emit();
    },
    isFollowing: tp => st.follow.indexOf(tp) >= 0,
    toggleFollow: tp => {
      const has = st.follow.indexOf(tp) >= 0;
      const arr = has ? st.follow.filter(x => x !== tp) : [tp, ...st.follow];
      st = {
        ...st,
        follow: arr
      };
      write(PS_KEYS.follow, arr);
      emit();
    },
    // record which side an opened story leaned toward (dominant lean of its coverage),
    // de-duped to newest, capped at 200 so localStorage never grows without bound.
    recordOpen: e => {
      const id = String(e.id);
      const arr = [{
        id,
        side: e.side || "",
        topic: e.topic || "",
        t: e.t || Date.now()
      }, ...st.hist.filter(h => h.id !== id)].slice(0, 200);
      st = {
        ...st,
        hist: arr
      };
      write(PS_KEYS.hist, arr);
      emit();
    },
    clearAll: () => {
      st = {
        saved: [],
        follow: [],
        hist: []
      };
      Object.keys(PS_KEYS).forEach(k => write(PS_KEYS[k], []));
      emit();
    },
    // Replace all state at once (used when merging cloud <-> local on login).
    hydrate: o => {
      st = {
        saved: o && o.saved || [],
        follow: o && o.follow || [],
        hist: o && o.hist || []
      };
      write(PS_KEYS.saved, st.saved);
      write(PS_KEYS.follow, st.follow);
      write(PS_KEYS.hist, st.hist);
      emit();
    }
  };
}();
// Subscribe a component to the store so it re-renders when saved/followed/history change.
function usePaksh() {
  const [, bump] = useState(0);
  useEffect(() => PStore.subscribe(() => bump(x => x + 1)), []);
  return PStore;
}

/* ---------------- Accounts (Supabase) — cross-device sync for Your Paksh ----------------
   Uses Supabase's REST auth + PostgREST DIRECTLY via fetch (no SDK), so the bundler-free
   build and strict CSP stay intact. The values below are the PUBLIC project url + publishable
   key (safe in the browser; Row-Level Security is what actually protects each user's row).
   Empty url/key => accounts OFF and the site is exactly the anonymous localStorage app.
   Sign-in is passwordless (magic-link email + Google), so Paksh never handles a password. */
const SUPABASE_URL = "https://zzjsjqqcpyyodatlmcux.supabase.co";
const SUPABASE_ANON = "sb_publishable_iPHpfSVKORMqq3JHjgKTfA_NeXPEgQw";
// Flip to true AFTER enabling the Google provider in the Supabase dashboard
// (Authentication -> Providers -> Google, with a Google OAuth client id/secret).
// Until then the Google button is hidden; magic-link email works regardless.
const GOOGLE_AUTH = false;
const authEnabled = () => !!(SUPABASE_URL && SUPABASE_ANON);
const _redirectTo = () => {
  try {
    return window.location.origin + "/you";
  } catch (e) {
    return "";
  }
};
const Auth = function () {
  const KEY = "paksh-auth";
  let sess = null;
  try {
    sess = JSON.parse(localStorage.getItem(KEY) || "null");
  } catch (e) {}
  const subs = new Set();
  const emit = () => subs.forEach(f => {
    try {
      f();
    } catch (e) {}
  });
  const save = s => {
    sess = s;
    try {
      s ? localStorage.setItem(KEY, JSON.stringify(s)) : localStorage.removeItem(KEY);
    } catch (e) {}
    emit();
  };
  const hdr = tok => ({
    "apikey": SUPABASE_ANON,
    "Authorization": "Bearer " + (tok || SUPABASE_ANON),
    "Content-Type": "application/json"
  });
  const store = tk => {
    if (!tk || !tk.access_token) return null;
    save({
      access_token: tk.access_token,
      refresh_token: tk.refresh_token,
      expires_at: Date.now() + (tk.expires_in || 3600) * 1000,
      user: tk.user || sess && sess.user || null
    });
    return sess;
  };
  async function fetchUser(tok) {
    try {
      const r = await fetch(SUPABASE_URL + "/auth/v1/user", {
        headers: hdr(tok)
      });
      if (r.ok) {
        const u = await r.json();
        if (sess) {
          sess.user = u;
          save(sess);
        }
        return u;
      }
    } catch (e) {}
    return null;
  }
  async function refresh() {
    if (!sess || !sess.refresh_token) return null;
    try {
      const r = await fetch(SUPABASE_URL + "/auth/v1/token?grant_type=refresh_token", {
        method: "POST",
        headers: hdr(),
        body: JSON.stringify({
          refresh_token: sess.refresh_token
        })
      });
      if (r.ok) return store(await r.json());
      save(null);
    } catch (e) {}
    return null;
  }
  async function token() {
    if (!sess) return null;
    if (Date.now() > sess.expires_at - 60000) {
      await refresh();
    }
    return sess ? sess.access_token : null;
  }
  return {
    subscribe: f => {
      subs.add(f);
      return () => subs.delete(f);
    },
    user: () => sess && sess.user,
    isLoggedIn: () => !!(sess && sess.access_token),
    token,
    // Process the token/error the provider (magic-link or Google) appends to the URL hash.
    async handleRedirect() {
      try {
        const h = window.location.hash || "";
        if (h.indexOf("access_token=") >= 0) {
          const p = new URLSearchParams(h.replace(/^#/, ""));
          store({
            access_token: p.get("access_token"),
            refresh_token: p.get("refresh_token"),
            expires_in: parseInt(p.get("expires_in") || "3600", 10)
          });
          history.replaceState(null, "", window.location.pathname + window.location.search);
          await fetchUser(p.get("access_token"));
          return true;
        }
        if (h.indexOf("error") >= 0) {
          history.replaceState(null, "", window.location.pathname + window.location.search);
        }
      } catch (e) {}
      return false;
    },
    async sendMagicLink(email) {
      const r = await fetch(SUPABASE_URL + "/auth/v1/otp?redirect_to=" + encodeURIComponent(_redirectTo()), {
        method: "POST",
        headers: hdr(),
        body: JSON.stringify({
          email,
          create_user: true
        })
      });
      if (!r.ok) {
        let m = "Could not send the sign-in link.";
        try {
          const j = await r.json();
          m = j.msg || j.error_description || j.error || m;
        } catch (e) {}
        throw new Error(m);
      }
      return true;
    },
    google() {
      window.location.href = SUPABASE_URL + "/auth/v1/authorize?provider=google&redirect_to=" + encodeURIComponent(_redirectTo());
    },
    async signOut() {
      try {
        const t = sess && sess.access_token;
        if (t) fetch(SUPABASE_URL + "/auth/v1/logout", {
          method: "POST",
          headers: hdr(t)
        });
      } catch (e) {}
      save(null);
    },
    async getPrefs() {
      const t = await token();
      if (!t || !sess.user) return null;
      try {
        const r = await fetch(SUPABASE_URL + "/rest/v1/profiles?select=prefs&id=eq." + sess.user.id, {
          headers: hdr(t)
        });
        if (r.ok) {
          const a = await r.json();
          return a[0] && a[0].prefs || {};
        }
      } catch (e) {}
      return null;
    },
    async putPrefs(prefs) {
      const t = await token();
      if (!t || !sess.user) return false;
      try {
        const r = await fetch(SUPABASE_URL + "/rest/v1/profiles?id=eq." + sess.user.id, {
          method: "PATCH",
          headers: {
            ...hdr(t),
            "Prefer": "return=minimal"
          },
          body: JSON.stringify({
            prefs
          })
        });
        return r.ok;
      } catch (e) {
        return false;
      }
    },
    async deleteData() {
      const t = await token();
      if (t && sess.user) {
        try {
          await fetch(SUPABASE_URL + "/rest/v1/profiles?id=eq." + sess.user.id, {
            method: "DELETE",
            headers: hdr(t)
          });
        } catch (e) {}
      }
      await this.signOut();
    }
  };
}();
function useAuth() {
  const [, b] = useState(0);
  useEffect(() => Auth.subscribe(() => b(x => x + 1)), []);
  return Auth;
}

// Bridge the on-device PStore to the cloud profile when logged in: merge both ways on
// login, then write-through (debounced) on every later change. Logged out => local only.
const PSync = function () {
  let pushT = null,
    active = false;
  const uniq = (a, b) => Array.from(new Set([...(a || []), ...(b || [])]));
  const mergeHist = (a, b) => {
    const seen = {},
      out = [];
    [...(a || []), ...(b || [])].forEach(h => {
      if (h && h.id && !seen[h.id]) {
        seen[h.id] = 1;
        out.push(h);
      }
    });
    return out.slice(0, 200);
  };
  async function onLogin() {
    const cloud = (await Auth.getPrefs()) || {};
    const merged = {
      saved: uniq(cloud.saved, PStore.saved()),
      follow: uniq(cloud.follow, PStore.follow()),
      hist: mergeHist(cloud.hist, PStore.hist())
    };
    PStore.hydrate(merged);
    active = true;
    await Auth.putPrefs(merged);
  }
  function push() {
    if (!active || !Auth.isLoggedIn()) return;
    clearTimeout(pushT);
    pushT = setTimeout(() => {
      Auth.putPrefs({
        saved: PStore.saved(),
        follow: PStore.follow(),
        hist: PStore.hist()
      });
    }, 900);
  }
  Auth.subscribe(() => {
    if (!Auth.isLoggedIn()) active = false;
  });
  PStore.subscribe(push);
  return {
    onLogin
  };
}();

/* ---------------- helpers ---------------- */
const imgFor = hue => {
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='480' height='300'><defs><linearGradient id='a' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='hsl(${hue} 36% 44%)'/><stop offset='1' stop-color='hsl(${(hue + 38) % 360} 42% 19%)'/></linearGradient><radialGradient id='b' cx='28%' cy='22%' r='65%'><stop offset='0' stop-color='rgba(255,255,255,0.30)'/><stop offset='1' stop-color='rgba(255,255,255,0)'/></radialGradient></defs><rect width='480' height='300' fill='url(%23a)'/><rect width='480' height='300' fill='url(%23b)'/></svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
};
const hueOf = s => {
  let h = 0;
  for (const c of String(s || "")) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
};
const biasPct = lc => {
  const tot = lc.left + lc.center + lc.right || 1;
  return {
    left: Math.round(lc.left / tot * 100),
    center: Math.round(lc.center / tot * 100),
    right: Math.round(lc.right / tot * 100)
  };
};
const dominant = b => {
  const k = Object.keys(b).sort((x, y) => b[y] - b[x])[0];
  return {
    side: k,
    pct: b[k]
  };
};
const lbl = (side, lang) => BIAS[side][lang] || BIAS[side].en;
const confName = (c, lang) => (({
  en: {
    low: "Low",
    medium: "Medium",
    high: "High"
  },
  hi: {
    low: "कम",
    medium: "मध्यम",
    high: "उच्च"
  }
})[lang] || {})[c] || c;
let _mode;
function detectMode() {
  if (!_mode) _mode = (async () => {
    try {
      const r = await fetch("/api/topics");
      if (r.ok && (r.headers.get("content-type") || "").includes("json")) return "api";
    } catch (e) {}
    return "static";
  })();
  return _mode;
}
async function apiGet(res) {
  if ((await detectMode()) === "api") {
    const r = await fetch("/api/" + res);
    if (r.ok && (r.headers.get("content-type") || "").includes("json")) return r.json();
  }
  const r = await fetch("/data/" + res + ".json?t=" + Date.now());
  if (!r.ok) throw new Error(res);
  const ct = r.headers.get("content-type") || "";
  if (!ct.includes("json")) throw new Error("not-json:" + res);
  return r.json();
}
async function loadAll() {
  try {
    const [e, b, tp, sr] = await Promise.all([apiGet("events"), apiGet("blindspots"), apiGet("topics"), apiGet("sources")]);
    return {
      events: e.events || [],
      blindspots: b.events || [],
      gaps: {
        left: b.left_heavier || [],
        right: b.right_heavier || [],
        agg: b.aggregate || {}
      },
      topics: tp.topics || [],
      sources: sr.sources || [],
      summary: sr.summary || {}
    };
  } catch (err) {
    console.error(err);
    return {
      events: [],
      blindspots: [],
      gaps: {
        left: [],
        right: [],
        agg: {}
      },
      topics: [],
      sources: [],
      summary: {}
    };
  }
}
const toCard = (e, lang) => {
  const lc = e.lean_counts || {
    left: 0,
    center: 0,
    right: 0
  };
  // created_at on the CARD is the real article publish time (published_at) when we have
  // it, so "x ago" reflects when the news happened, not when our pipeline touched it.
  // Falls back to the pipeline created_at for events analysed before published_at existed.
  return {
    id: e.id,
    topic: e.topic,
    region: e.region || "India",
    srclang: e.lang || "en",
    created_at: e.published_at || e.created_at,
    headline: lang === "hi" && e.title_hi ? e.title_hi : e.title,
    lead: lang === "hi" && e.summary_hi ? e.summary_hi : e.summary,
    summary: lang === "hi" && e.summary_points_hi && e.summary_points_hi.length ? e.summary_points_hi : e.summary_points || [],
    bias: biasPct(lc),
    counts: lc,
    sources: lc.left + lc.center + lc.right || e.total_sources || 0,
    international: e.international || 0,
    importance: typeof e.importance === "number" ? e.importance : 0,
    feed_rank: typeof e.feed_rank === "number" ? e.feed_rank : typeof e.importance === "number" ? e.importance : 0,
    unrated: Math.max(0, (e.source_count || 0) - (lc.left + lc.center + lc.right) - (e.international || 0)),
    blindspot: e.blindspot ? e.blindspot.side : null,
    auto: e.summary_method === "extractive",
    img: e.image_url || "",
    image: e.image_url || imgFor(hueOf(e.topic || e.title))
  };
};
// Keep each language view free of the OTHER language's script. The summary
// engine occasionally writes a framing note in the wrong language; this drops
// any bullet whose script doesn't match the active language, so the English
// view never shows Devanagari (and vice-versa). A side left empty just shows
// the usual "not enough unique coverage" note.
const _DEV = /[ऀ-ॿ]/;
const framingFor = (e, lang) => {
  const src = lang === "hi" && e.framing_hi && Object.keys(e.framing_hi).length ? e.framing_hi : e.framing || {};
  const wantHi = lang === "hi";
  const out = {};
  Object.keys(src || {}).forEach(k => {
    const arr = Array.isArray(src[k]) ? src[k] : src[k] ? [src[k]] : [];
    out[k] = arr.filter(s => typeof s === "string" && s.trim() && (wantHi ? _DEV.test(s) : !_DEV.test(s)));
  });
  return out;
};
const toDetail = (e, lang) => {
  const c = toCard(e, lang);
  c.coverage = e.coverage || {};
  c.outlets = e.sources || [];
  c.framing = framingFor(e, lang);
  return c;
};
const isHi = lang => lang === "hi" ? "deva" : "";
// Reading text is serif in BOTH scripts: Source Serif 4 (Latin) / Tiro Devanagari
// Hindi (with extra leading). Chrome/labels keep isHi() -> "deva" (Plex Devanagari).
const readCls = lang => lang === "hi" ? "read-hi" : "serif";

/* ---------------- extra icons ---------------- */
const ArrowUpRight = p => /*#__PURE__*/React.createElement("svg", {
  width: p.size || 24,
  height: p.size || 24,
  className: p.className || "",
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: "2",
  strokeLinecap: "round",
  strokeLinejoin: "round"
}, /*#__PURE__*/React.createElement("path", {
  d: "M7 17 17 7M7 7h10v10"
}));
const Compass = p => /*#__PURE__*/React.createElement("svg", {
  width: p.size || 24,
  height: p.size || 24,
  className: p.className || "",
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: "2",
  strokeLinecap: "round",
  strokeLinejoin: "round"
}, /*#__PURE__*/React.createElement("circle", {
  cx: "12",
  cy: "12",
  r: "10"
}), /*#__PURE__*/React.createElement("polygon", {
  points: "16.2 7.8 14.1 14.1 7.8 16.2 9.9 9.9"
}));
const Globe = p => /*#__PURE__*/React.createElement("svg", {
  width: p.size || 24,
  height: p.size || 24,
  className: p.className || "",
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: "2",
  strokeLinecap: "round",
  strokeLinejoin: "round"
}, /*#__PURE__*/React.createElement("circle", {
  cx: "12",
  cy: "12",
  r: "10"
}), /*#__PURE__*/React.createElement("path", {
  d: "M2 12h20M12 2a15 15 0 0 1 4 10 15 15 0 0 1-4 10 15 15 0 0 1-4-10 15 15 0 0 1 4-10Z"
}));
const Clock = p => /*#__PURE__*/React.createElement("svg", {
  width: p.size || 24,
  height: p.size || 24,
  className: p.className || "",
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: "2",
  strokeLinecap: "round",
  strokeLinejoin: "round"
}, /*#__PURE__*/React.createElement("circle", {
  cx: "12",
  cy: "12",
  r: "10"
}), /*#__PURE__*/React.createElement("path", {
  d: "M12 7v5l3 2"
}));
const LinkIcon = p => /*#__PURE__*/React.createElement("svg", {
  width: p.size || 24,
  height: p.size || 24,
  className: p.className || "",
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: "2",
  strokeLinecap: "round",
  strokeLinejoin: "round"
}, /*#__PURE__*/React.createElement("path", {
  d: "M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"
}), /*#__PURE__*/React.createElement("path", {
  d: "M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"
}));
const Check = p => /*#__PURE__*/React.createElement("svg", {
  width: p.size || 24,
  height: p.size || 24,
  className: p.className || "",
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: "2.4",
  strokeLinecap: "round",
  strokeLinejoin: "round"
}, /*#__PURE__*/React.createElement("path", {
  d: "M20 6 9 17l-5-5"
}));
const Bookmark = p => /*#__PURE__*/React.createElement("svg", {
  width: p.size || 24,
  height: p.size || 24,
  className: p.className || "",
  viewBox: "0 0 24 24",
  fill: p.fill || "none",
  stroke: "currentColor",
  strokeWidth: "2",
  strokeLinecap: "round",
  strokeLinejoin: "round"
}, /*#__PURE__*/React.createElement("path", {
  d: "M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"
}));
const Trash = p => /*#__PURE__*/React.createElement("svg", {
  width: p.size || 24,
  height: p.size || 24,
  className: p.className || "",
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: "2",
  strokeLinecap: "round",
  strokeLinejoin: "round"
}, /*#__PURE__*/React.createElement("path", {
  d: "M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m2 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"
}));

/* ---------------- helpers ---------------- */
const _ts = iso => {
  if (!iso) return NaN;
  let x = ("" + iso).replace(" ", "T");
  if (!/[zZ]|[+\-]\d\d:?\d\d$/.test(x)) x += "Z";
  return Date.parse(x);
};
const timeAgo = (iso, lang) => {
  const ts = _ts(iso);
  if (isNaN(ts)) return "";
  const m = Math.max(0, (Date.now() - ts) / 60000);
  const hi = lang === "hi";
  if (m < 60) return hi ? `${Math.round(m)} मिनट पहले` : `${Math.round(m)}m ago`;
  const h = m / 60;
  if (h < 24) return hi ? `${Math.round(h)} घंटे पहले` : `${Math.round(h)}h ago`;
  const d = Math.round(h / 24);
  return hi ? `${d} दिन पहले` : `${d}d ago`;
};
// Absolute publish date+time, e.g. "6 Aug 2026, 2:14 PM" (en) / Devanagari locale (hi).
// Shown ALONGSIDE the relative "x ago" so the timestamp is unambiguous on a story page.
const absDate = (iso, lang) => {
  const ts = _ts(iso);
  if (isNaN(ts)) return "";
  try {
    return new Date(ts).toLocaleString(lang === "hi" ? "hi-IN" : "en-IN", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit"
    });
  } catch (e) {
    return "";
  }
};
const domSide = bias => ["left", "center", "right"].reduce((a, b) => (bias[b] || 0) > (bias[a] || 0) ? b : a, "left");
const tword = lang => n => n === 1 ? STR[lang].source : STR[lang].sources;
const covLine = (story, lang) => {
  const d = domSide(story.bias);
  const tot = story.sources + (story.unrated || 0) + (story.international || 0);
  return `${story.bias[d]}% ${lbl(d, lang)} · ${tot} ${tot === 1 ? STR[lang].source : STR[lang].sources}`;
};
// Newspaper count line: raw distinct-outlet counts L · C · R, plus n and age. Reads
// straight from the real per-lean counts (never a hardcoded ratio).
const countLine = (story, lang) => {
  const c = story.counts || {};
  const L = c.left || 0,
    C = c.center || 0,
    R = c.right || 0;
  const n = L + C + R;
  const ta = timeAgo(story.created_at, lang);
  return `${L} · ${C} · ${R}   n=${n}${ta ? " · " + ta : ""}`;
};
function Thumb({
  src,
  topic,
  title,
  ratio,
  t,
  lang,
  className
}) {
  const [err, setErr] = useState(false);
  const real = src && !err;
  const tp = lang === "hi" ? TOPIC_HI[topic] || topic : topic || "News";
  return /*#__PURE__*/React.createElement("div", {
    className: `relative overflow-hidden ${t.soft} ${className || ""}`,
    style: {
      aspectRatio: ratio || "16 / 9"
    }
  }, real ? /*#__PURE__*/React.createElement("img", {
    src: src,
    alt: "",
    loading: "lazy",
    decoding: "async",
    referrerPolicy: "no-referrer",
    onError: () => setErr(true),
    className: "absolute inset-0 h-full w-full object-cover"
  }) : /*#__PURE__*/React.createElement("div", {
    className: "absolute inset-0 flex items-center justify-center"
  }, /*#__PURE__*/React.createElement("span", {
    className: `mono text-[11px] font-semibold uppercase tracking-[0.16em] ${t.tf} ${lang === "hi" ? "deva" : ""}`
  }, tp)));
}
function OutletAvatar({
  o,
  side,
  size
}) {
  const [err, setErr] = useState(false);
  let host = "";
  try {
    host = new URL(o.url).hostname.replace(/^www\./, "");
  } catch (e) {}
  const s = size || 26;
  const ring = side === "unrated" ? "#B8B4AC" : BIAS[side] && BIAS[side].color || "#8A8F98";
  if (err || !host) return /*#__PURE__*/React.createElement("span", {
    className: "grid shrink-0 place-items-center rounded-md mono font-semibold text-white",
    style: {
      width: s,
      height: s,
      fontSize: s * 0.42,
      backgroundColor: ring
    }
  }, (o.source || "?")[0]);
  return /*#__PURE__*/React.createElement("span", {
    className: "grid shrink-0 place-items-center rounded-md bg-white",
    style: {
      width: s,
      height: s,
      boxShadow: `0 0 0 1.5px ${ring}`
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: `https://www.google.com/s2/favicons?domain=${host}&sz=64`,
    alt: "",
    width: s * 0.62,
    height: s * 0.62,
    loading: "lazy",
    referrerPolicy: "no-referrer",
    onError: () => setErr(true),
    className: "object-contain"
  }));
}

/* ---------------- bias bars ---------------- */
// The signature instrument. Segment sizes come STRAIGHT from live counts
// (flexGrow = bias%, itself computed from the distinct-outlet L/C/R totals) — never
// hardcoded. Each side is textured (solid / 45deg hatch / vertical rule), separated by
// a 1px paper gap, inside a hairline ink frame, with a fixed centre axis so skew is
// judged against a constant. min-width 2px keeps a lone outlet visible. No animation.
function BiasSegments({
  bias,
  t,
  h,
  onPick,
  active,
  lang
}) {
  const present = ["left", "center", "right"].filter(k => (bias[k] || 0) > 0);
  return /*#__PURE__*/React.createElement("div", {
    className: "relative flex w-full",
    style: {
      height: h,
      border: `1px solid ${t.ink}`,
      background: t.track || "#EAE6DB"
    }
  }, present.map((k, i) => /*#__PURE__*/React.createElement(React.Fragment, {
    key: k
  }, i > 0 && /*#__PURE__*/React.createElement("div", {
    style: {
      flex: "0 0 1px",
      background: t.gap || "#F4F1EA"
    }
  }), onPick ? /*#__PURE__*/React.createElement("button", {
    onClick: e => {
      e.stopPropagation();
      e.preventDefault();
      onPick(k);
    },
    "aria-label": lbl(k, lang || "en"),
    className: `${BIAS[k].tex} cursor-pointer hover:brightness-110 ${active && active !== k ? "opacity-40" : ""}`,
    style: {
      flexGrow: bias[k],
      flexBasis: 0,
      minWidth: 2,
      border: 0,
      padding: 0
    }
  }) : /*#__PURE__*/React.createElement("div", {
    className: BIAS[k].tex,
    style: {
      flexGrow: bias[k],
      flexBasis: 0,
      minWidth: 2
    }
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      left: "50%",
      top: -3,
      bottom: -3,
      width: 1,
      background: t.ink
    }
  }));
}
function MiniBar({
  bias,
  t
}) {
  return /*#__PURE__*/React.createElement(BiasSegments, {
    bias: bias,
    t: t,
    h: 10
  });
}
// Larger bar. Pass `counts` (real L/C/R outlet counts) to print the label row + n above,
// exactly like the design's story-page instrument.
function BiasBar({
  bias,
  t,
  lang,
  onPick,
  active,
  height,
  counts,
  showN,
  showScale
}) {
  const h = height || 26;
  const total = counts ? ["left", "center", "right"].reduce((s, k) => s + (counts[k] || 0), 0) : 0;
  return /*#__PURE__*/React.createElement("div", null, counts && /*#__PURE__*/React.createElement("div", {
    className: "mb-2 flex items-baseline justify-between gap-3"
  }, /*#__PURE__*/React.createElement("div", {
    className: `flex flex-wrap gap-x-4 gap-y-1 text-[10.5px] font-medium uppercase tracking-[0.1em] ${t.tp} ${lang === "hi" ? "deva" : ""}`
  }, ["left", "center", "right"].map(k => (counts[k] || 0) > 0 && /*#__PURE__*/React.createElement("span", {
    key: k
  }, lbl(k, lang), " ", /*#__PURE__*/React.createElement("span", {
    className: "mono",
    style: {
      letterSpacing: 0
    }
  }, counts[k])))), showN !== false && total > 0 && /*#__PURE__*/React.createElement("span", {
    className: `mono text-[10.5px] ${t.tf}`
  }, "n = ", total)), /*#__PURE__*/React.createElement(BiasSegments, {
    bias: bias,
    t: t,
    h: h,
    onPick: onPick,
    active: active,
    lang: lang
  }), showScale && /*#__PURE__*/React.createElement("div", {
    className: "relative",
    style: {
      height: 14,
      marginTop: 3
    }
  }, [25, 50, 75].map(p => /*#__PURE__*/React.createElement("div", {
    key: p,
    style: {
      position: "absolute",
      left: p + "%",
      top: 0,
      width: 1,
      height: p === 50 ? 6 : 4,
      background: p === 50 ? t.ink : t.line
    }
  })), /*#__PURE__*/React.createElement("span", {
    className: `mono text-[9px] ${t.tf}`,
    style: {
      position: "absolute",
      left: "50%",
      top: 6,
      transform: "translateX(-50%)",
      whiteSpace: "nowrap"
    }
  }, lang === "hi" ? "कवरेज का 50%" : "50% of coverage")));
}
// Coverage-gap viz: three EQUAL-WIDTH columns, bar height proportional to that side's
// count, an absent side drawn as the dashed hatch — so absence takes as much room as
// presence. Driven only by the same L/C/R distinct-outlet counts as the bias bar.
function GapColumns({
  counts,
  t,
  lang
}) {
  const ks = ["left", "center", "right"];
  const mx = Math.max(1, ...ks.map(k => counts[k] || 0));
  return /*#__PURE__*/React.createElement("div", {
    className: "grid grid-cols-3 gap-1.5"
  }, ks.map(k => {
    const n = counts[k] || 0;
    const pct = Math.round(n / mx * 100);
    return /*#__PURE__*/React.createElement("div", {
      key: k
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-end",
      style: {
        height: 34,
        border: `1px solid ${t.ink}`,
        background: t.track || "#EAE6DB"
      }
    }, n > 0 ? /*#__PURE__*/React.createElement("div", {
      className: `w-full ${BIAS[k].tex}`,
      style: {
        height: `${Math.max(8, pct)}%`
      }
    }) : /*#__PURE__*/React.createElement("div", {
      className: "seg-absent w-full h-full"
    })), /*#__PURE__*/React.createElement("div", {
      className: `mt-1.5 text-[9.5px] font-medium uppercase tracking-[0.1em] ${t.tp} ${lang === "hi" ? "deva" : ""}`
    }, lbl(k, lang)), /*#__PURE__*/React.createElement("div", {
      className: "mono text-[10.5px]",
      style: {
        color: n > 0 ? t.ink : "#75442E"
      }
    }, n));
  }));
}
const LeanBadge = ({
  side,
  lang,
  t
}) => side === "unrated" ? /*#__PURE__*/React.createElement("span", {
  className: `shrink-0 rounded mono px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${t.chip} ${t.tf}`
}, lang === "hi" ? "अनरेटेड" : "Unrated") : /*#__PURE__*/React.createElement("span", {
  className: "shrink-0 rounded mono px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white",
  style: {
    backgroundColor: BIAS[side].color
  }
}, lbl(side, lang));
function AutoTag({
  lang,
  t
}) {
  return /*#__PURE__*/React.createElement("span", {
    className: `inline-flex items-center gap-1 rounded mono px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${t.chip} ${t.tf}`
  }, STR[lang].autoTag);
}
function Eyebrow({
  topic,
  created_at,
  blindspot,
  t,
  lang
}) {
  const tp = lang === "hi" ? TOPIC_HI[topic] || topic : topic;
  const face = lang === "hi" ? "deva" : "mono";
  return /*#__PURE__*/React.createElement("div", {
    className: `flex flex-wrap items-center gap-x-2 gap-y-1 ${face} text-[11px] font-medium uppercase tracking-[0.1em]`
  }, /*#__PURE__*/React.createElement("span", {
    className: t.ts
  }, tp || "News"), created_at && /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("span", {
    className: t.tf
  }, "\xB7"), /*#__PURE__*/React.createElement("span", {
    className: t.tf
  }, timeAgo(created_at, lang))), blindspot && /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("span", {
    className: t.tf
  }, "\xB7"), /*#__PURE__*/React.createElement("span", {
    className: t.blind
  }, STR[lang].navOS)));
}
function SectionTitle({
  children,
  t,
  lang,
  right
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: `mb-4 flex items-baseline justify-between gap-3 border-b pb-2 ${t.border}`
  }, /*#__PURE__*/React.createElement("h2", {
    className: `headline text-[15px] font-bold uppercase tracking-[0.08em] ${t.tp} ${isHi(lang)}`
  }, children), right);
}

/* ---------------- feed pieces (newspaper hierarchy) ---------------- */
// A dated masthead sub-strip: today's date + how many outlets Paksh tracks.
// The dated strip under the masthead: a 2px rule over a 1px rule (design 2a), carrying
// the edition toggle + today's date on the left, the live tally in the centre, and the
// freshness on the right. Every number is real (homeCards / sources / gaps / newest event).
function DateStrip({
  t,
  lang,
  stats,
  regionFilter,
  setRegionFilter
}) {
  const today = new Date().toLocaleDateString(lang === "hi" ? "hi-IN" : "en-IN", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric"
  });
  const ls = lang === "hi" ? 0 : ".14em";
  const eb = `eyebrow ${lang === "hi" ? "deva" : ""}`;
  const region = (k, label) => /*#__PURE__*/React.createElement("button", {
    onClick: () => setRegionFilter && setRegionFilter(k),
    className: `${eb} ${regionFilter === k ? t.tp : `${t.tf} hover:${t.tp}`}`,
    style: {
      letterSpacing: ls
    }
  }, label);
  const tally = lang === "hi" ? `${stats.stories} ख़बरें · ${stats.outlets} स्रोत · ${stats.gaps} कवरेज गैप` : `${stats.stories} stories · ${stats.outlets} outlets tracked · ${stats.gaps} coverage gaps`;
  return /*#__PURE__*/React.createElement("div", {
    className: "flex items-center justify-between gap-4 py-[7px]",
    style: {
      borderTop: `2px solid ${t.ink}`,
      borderBottom: `1px solid ${t.ink}`
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "flex items-center gap-3 sm:gap-4 min-w-0"
  }, region("National", ui("National", lang)), region("International", ui("International", lang)), /*#__PURE__*/React.createElement("span", {
    className: `hidden md:inline ${eb} ${t.tf}`,
    style: {
      letterSpacing: ls
    }
  }, today)), /*#__PURE__*/React.createElement("span", {
    className: `hidden sm:inline ${eb} ${t.tf} truncate`,
    style: {
      letterSpacing: ls
    }
  }, tally));
}
// LEAD — the most-covered story of the moment, given the largest type + full bias
// instrument with the printed scale. Text-forward; a single 2:1 image if one exists.
// LEAD — the single most-covered story, at 54px on desktop / 31px on mobile: the one
// dominant moment that gives the eye somewhere to land (design 2a/2c). Text-forward,
// no image. The bias block sits beside the lead paragraph on desktop, below on mobile;
// every count/width is live (BiasSegments flex-grow = bias%, computed from L/C/R owners).
function LeadStory({
  story,
  t,
  lang,
  onOpen
}) {
  const c = story.counts || {
    left: 0,
    center: 0,
    right: 0
  };
  const L = c.left || 0,
    C = c.center || 0,
    R = c.right || 0,
    n = L + C + R;
  const b = story.bias || {
    left: 0,
    center: 0,
    right: 0
  };
  const tp = lang === "hi" ? TOPIC_HI[story.topic] || story.topic : story.topic;
  return /*#__PURE__*/React.createElement("a", {
    href: "/story/" + encodeURIComponent(story.id),
    onClick: e => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      onOpen(story.id);
    },
    className: "block no-underline group cursor-pointer"
  }, /*#__PURE__*/React.createElement("div", {
    className: `eyebrow accent-clay ${lang === "hi" ? "deva" : ""}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : ".14em"
    }
  }, lang === "hi" ? "आज सबसे ज़्यादा कवरेज" : "Most covered today", tp ? ` · ${tp}` : ""), /*#__PURE__*/React.createElement("h2", {
    className: `headline mt-3 text-[31px] sm:text-[42px] lg:text-[54px] ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-4`,
    style: {
      lineHeight: lang === "hi" ? 1.14 : 1.06,
      letterSpacing: lang === "hi" ? 0 : "-0.022em",
      textWrap: "balance"
    }
  }, story.headline), story.img && /*#__PURE__*/React.createElement("div", {
    className: "mt-4 overflow-hidden"
  }, /*#__PURE__*/React.createElement(Thumb, {
    src: story.img,
    topic: story.topic,
    title: story.headline,
    ratio: "2 / 1",
    t: t,
    lang: lang
  })), /*#__PURE__*/React.createElement("div", {
    className: "mt-5 grid gap-6 lg:grid-cols-[1fr_250px] lg:gap-8"
  }, story.lead && /*#__PURE__*/React.createElement("p", {
    className: `text-[16px] lg:text-[17.5px] ${t.ts} ${readCls(lang)} lc-4`,
    style: {
      lineHeight: lang === "hi" ? 1.85 : 1.6,
      textWrap: "pretty"
    }
  }, story.lead), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: `mb-2 flex justify-between text-[10px] font-medium uppercase tracking-[0.1em] ${t.tp} ${lang === "hi" ? "deva" : ""}`
  }, ["left", "center", "right"].map(k => /*#__PURE__*/React.createElement("span", {
    key: k
  }, lang === "hi" ? BIAS[k].hi : BIAS[k].en.charAt(0), " ", /*#__PURE__*/React.createElement("span", {
    className: "mono",
    style: {
      letterSpacing: 0
    }
  }, c[k] || 0)))), /*#__PURE__*/React.createElement(BiasSegments, {
    bias: b,
    t: t,
    h: 28,
    lang: lang
  }), /*#__PURE__*/React.createElement("div", {
    className: `mt-2 mono text-[10.5px] ${t.tf}`
  }, "n = ", n, " \xB7 ", b.left, " / ", b.center, " / ", b.right, "%"), /*#__PURE__*/React.createElement("div", {
    className: `mt-3 text-[11px] font-medium uppercase tracking-[0.06em] ${t.tp} ${lang === "hi" ? "deva" : ""}`
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      borderBottom: `1px solid ${t.ink}`,
      paddingBottom: 2
    }
  }, lang === "hi" ? "सभी पक्ष पढ़ें" : "Read all sides", " \u2192")))));
}
// SECONDARY — the middle tier: a real headline + a taste of the lead + a compact bias bar.
function SecondaryStory({
  story,
  t,
  lang,
  onOpen
}) {
  return /*#__PURE__*/React.createElement("a", {
    href: "/story/" + encodeURIComponent(story.id),
    onClick: e => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      onOpen(story.id);
    },
    className: `block no-underline group cursor-pointer border-b py-5 ${t.border}`
  }, /*#__PURE__*/React.createElement(Eyebrow, {
    topic: story.topic,
    created_at: story.created_at,
    blindspot: story.blindspot,
    t: t,
    lang: lang
  }), /*#__PURE__*/React.createElement("h3", {
    className: `headline mt-1.5 text-[20px] sm:text-[21px] leading-[1.24] lc-2 ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`
  }, story.headline), story.lead && /*#__PURE__*/React.createElement("p", {
    className: `mt-2 text-[14px] leading-[1.55] lc-2 ${t.ts} ${readCls(lang)}`
  }, story.lead), /*#__PURE__*/React.createElement("div", {
    className: "mt-3"
  }, /*#__PURE__*/React.createElement(BiasBar, {
    bias: story.bias,
    t: t,
    lang: lang,
    height: 11
  })), /*#__PURE__*/React.createElement("div", {
    className: `mt-1.5 mono text-[11px] ${t.tf} ${lang === "hi" ? "deva" : ""}`
  }, countLine(story, lang)));
}
// DENSE — the tail: a compact headline row with a mini bias bar. High information density.
function DenseRow({
  story,
  t,
  lang,
  onOpen,
  last
}) {
  return /*#__PURE__*/React.createElement("a", {
    href: "/story/" + encodeURIComponent(story.id),
    onClick: e => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      onOpen(story.id);
    },
    className: `block no-underline group cursor-pointer ${last ? "" : "border-b"} py-3.5 ${t.border}`
  }, /*#__PURE__*/React.createElement("h4", {
    className: `headline text-[16px] sm:text-[17.5px] leading-[1.24] lc-2 ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`
  }, story.headline), /*#__PURE__*/React.createElement("div", {
    className: "mt-2 flex items-center gap-3"
  }, /*#__PURE__*/React.createElement("div", {
    className: "w-24 sm:w-28 shrink-0"
  }, /*#__PURE__*/React.createElement(MiniBar, {
    bias: story.bias,
    t: t
  })), /*#__PURE__*/React.createElement("span", {
    className: `mono text-[10.5px] ${t.tf} ${lang === "hi" ? "deva" : ""}`
  }, countLine(story, lang))));
}
// SPECTRUM RAIL — an aggregate of the visible feed: total distinct-outlet coverage by
// side. Pure arithmetic over the same per-lean counts; never a hardcoded ratio.
// SPECTRUM RAIL — an aggregate of the visible feed: each side's SHARE of total
// distinct-outlet coverage today. Pure arithmetic over the same per-lean counts as
// the bias bars; never a hardcoded ratio. Rail-style (no card) per design 2a.
function SpectrumRail({
  cards,
  t,
  lang
}) {
  const agg = {
    left: 0,
    center: 0,
    right: 0
  };
  cards.forEach(c => {
    const k = c.counts || {};
    agg.left += k.left || 0;
    agg.center += k.center || 0;
    agg.right += k.right || 0;
  });
  const sum = Math.max(1, agg.left + agg.center + agg.right);
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: `eyebrow pb-2 ${t.tp} ${lang === "hi" ? "deva" : ""}`,
    style: {
      borderBottom: `1px solid ${t.ink}`,
      letterSpacing: lang === "hi" ? 0 : ".14em"
    }
  }, lang === "hi" ? "आज का स्पेक्ट्रम" : "The spectrum today"), /*#__PURE__*/React.createElement("div", {
    className: "mt-3.5 flex flex-col gap-2.5"
  }, ["left", "center", "right"].map(k => /*#__PURE__*/React.createElement("div", {
    key: k
  }, /*#__PURE__*/React.createElement("div", {
    className: "mb-1.5 flex items-center justify-between"
  }, /*#__PURE__*/React.createElement("span", {
    className: `text-[10px] font-medium uppercase tracking-[0.1em] ${t.ts} ${lang === "hi" ? "deva" : ""}`
  }, lbl(k, lang)), /*#__PURE__*/React.createElement("span", {
    className: "mono text-[11px]",
    style: {
      color: t.ink
    }
  }, agg[k])), /*#__PURE__*/React.createElement("div", {
    style: {
      height: 7,
      background: t.track || "#E1DCCE",
      border: `1px solid ${t.line}`
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: BIAS[k].tex,
    style: {
      width: `${Math.round(agg[k] / sum * 100)}%`,
      height: "100%"
    }
  }))))), /*#__PURE__*/React.createElement("div", {
    className: `mt-2.5 mono text-[10px] ${t.tf} ${lang === "hi" ? "deva" : ""}`
  }, lang === "hi" ? "आज प्रति पक्ष ख़बरें" : "Stories run per side, today"));
}
function FeedRow({
  story,
  t,
  lang,
  onOpen
}) {
  return /*#__PURE__*/React.createElement("a", {
    href: "/story/" + encodeURIComponent(story.id),
    onClick: e => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      onOpen(story.id);
    },
    className: `no-underline group flex cursor-pointer gap-4 border-b pb-6 ${t.border}`
  }, /*#__PURE__*/React.createElement("div", {
    className: "min-w-0 flex-1"
  }, /*#__PURE__*/React.createElement(Eyebrow, {
    topic: story.topic,
    created_at: story.created_at,
    blindspot: story.blindspot,
    t: t,
    lang: lang
  }), /*#__PURE__*/React.createElement("h3", {
    className: `headline mt-1.5 text-lg sm:text-xl leading-[1.18] lc-3 ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`
  }, story.headline), /*#__PURE__*/React.createElement("div", {
    className: "mt-2.5 flex items-center gap-3"
  }, /*#__PURE__*/React.createElement("div", {
    className: "w-28 sm:w-36"
  }, /*#__PURE__*/React.createElement(MiniBar, {
    bias: story.bias,
    t: t
  })), /*#__PURE__*/React.createElement("span", {
    className: `mono text-[11px] ${t.tf} ${lang === "hi" ? "deva" : ""}`
  }, covLine(story, lang)))), story.img && /*#__PURE__*/React.createElement("div", {
    className: "shrink-0"
  }, /*#__PURE__*/React.createElement(Thumb, {
    src: story.img,
    topic: story.topic,
    title: story.headline,
    ratio: "1 / 1",
    t: t,
    lang: lang,
    className: "w-24 sm:w-32 rounded-md"
  })));
}
function BriefItem({
  story,
  t,
  lang,
  onOpen,
  last
}) {
  return /*#__PURE__*/React.createElement("button", {
    onClick: () => onOpen(story.id),
    className: `block w-full text-left ${last ? "" : "border-b"} py-3 ${t.border}`
  }, /*#__PURE__*/React.createElement("h4", {
    className: `headline text-[15px] font-semibold leading-[1.2] lc-2 ${t.tp} ${readCls(lang)} hover:underline decoration-1 underline-offset-2`
  }, story.headline), /*#__PURE__*/React.createElement("div", {
    className: "mt-2 flex items-center gap-2"
  }, /*#__PURE__*/React.createElement("div", {
    className: "w-16"
  }, /*#__PURE__*/React.createElement(MiniBar, {
    bias: story.bias,
    t: t
  })), /*#__PURE__*/React.createElement("span", {
    className: `mono text-[10px] ${t.tf} ${lang === "hi" ? "deva" : ""}`
  }, covLine(story, lang))));
}
function BlindspotCard({
  story,
  t,
  lang,
  onOpen
}) {
  const c = story.counts || {
    left: 0,
    center: 0,
    right: 0
  };
  const L = c.left || 0,
    C = c.center || 0,
    R = c.right || 0;
  const covered = lang === "hi" ? `${L} वाम · ${C} केंद्र · ${R} दक्षिण` : `${L} Left · ${C} Centre · ${R} Right`;
  return /*#__PURE__*/React.createElement("a", {
    href: "/story/" + encodeURIComponent(story.id),
    onClick: e => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      onOpen(story.id);
    },
    className: `block no-underline group cursor-pointer border ${t.surface} ${t.border}`,
    style: {
      borderLeft: "3px solid #8D5B44"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "p-4"
  }, /*#__PURE__*/React.createElement("div", {
    className: `mono text-[10px] font-medium uppercase tracking-[0.14em] ${t.blind} ${lang === "hi" ? "deva" : ""}`
  }, STR[lang].navOS), /*#__PURE__*/React.createElement("h3", {
    className: `headline mt-2 text-[17px] leading-[1.24] lc-3 ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`
  }, story.headline), /*#__PURE__*/React.createElement("div", {
    className: "mt-3"
  }, /*#__PURE__*/React.createElement(GapColumns, {
    counts: c,
    t: t,
    lang: lang
  })), /*#__PURE__*/React.createElement("div", {
    className: `mt-2.5 mono text-[11px] ${t.tf} ${lang === "hi" ? "deva" : ""}`
  }, STR[lang].gapCovered, " ", covered)));
}
function GridCard({
  story,
  t,
  lang,
  onOpen
}) {
  return /*#__PURE__*/React.createElement("a", {
    href: "/story/" + encodeURIComponent(story.id),
    onClick: e => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      onOpen(story.id);
    },
    className: `block no-underline group cursor-pointer overflow-hidden rounded-lg border ${t.surface} ${t.border}`
  }, story.img && /*#__PURE__*/React.createElement(Thumb, {
    src: story.img,
    topic: story.topic,
    title: story.headline,
    ratio: "16 / 9",
    t: t,
    lang: lang
  }), /*#__PURE__*/React.createElement("div", {
    className: "p-4"
  }, /*#__PURE__*/React.createElement(Eyebrow, {
    topic: story.topic,
    created_at: story.created_at,
    blindspot: story.blindspot,
    t: t,
    lang: lang
  }), /*#__PURE__*/React.createElement("h3", {
    className: `headline mt-1.5 text-[17px] leading-[1.2] lc-3 ${t.tp} ${readCls(lang)}`
  }, story.headline), /*#__PURE__*/React.createElement("div", {
    className: "mt-3"
  }, /*#__PURE__*/React.createElement(MiniBar, {
    bias: story.bias,
    t: t
  })), /*#__PURE__*/React.createElement("div", {
    className: `mt-2 mono text-[11px] ${t.tf} ${lang === "hi" ? "deva" : ""}`
  }, covLine(story, lang))));
}

/* ---------------- shell ---------------- */
function RegionSelect({
  region,
  setRegion,
  t,
  lang
}) {
  const states = ["Maharashtra", "Uttar Pradesh", "Karnataka", "Tamil Nadu", "Delhi", "Gujarat", "West Bengal"];
  return /*#__PURE__*/React.createElement("div", {
    className: "relative shrink-0"
  }, /*#__PURE__*/React.createElement("select", {
    value: region,
    onChange: e => setRegion(e.target.value),
    className: `appearance-none rounded-full border px-3 py-1 pl-3 pr-7 text-[12.5px] font-medium ${t.border} ${t.ts} hover:${t.soft} bg-transparent outline-none cursor-pointer ${lang === "hi" ? "deva" : ""} transition-all duration-200`
  }, /*#__PURE__*/React.createElement("option", {
    value: "National"
  }, ui("National", lang)), /*#__PURE__*/React.createElement("option", {
    value: "International"
  }, ui("International", lang)), /*#__PURE__*/React.createElement("optgroup", {
    label: lang === "hi" ? "राज्य (जल्द आ रहे हैं)" : "States (Pending)"
  }, states.map(s => /*#__PURE__*/React.createElement("option", {
    key: s,
    value: s,
    disabled: true
  }, s)))), /*#__PURE__*/React.createElement("div", {
    className: `pointer-events-none absolute inset-y-0 right-2 flex items-center ${t.tf}`
  }, /*#__PURE__*/React.createElement("svg", {
    width: "12",
    height: "12",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "2",
    strokeLinecap: "round",
    strokeLinejoin: "round"
  }, /*#__PURE__*/React.createElement("path", {
    d: "m6 9 6 6 6-6"
  }))));
}
function UtilityStrip({
  t,
  lang,
  setLang,
  dark,
  setDark
}) {
  const today = new Date().toLocaleDateString(lang === "hi" ? "hi-IN" : "en-IN", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric"
  });
  return /*#__PURE__*/React.createElement("div", {
    style: {
      backgroundColor: "#15140F"
    },
    className: "text-white/85"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mx-auto flex max-w-[1800px] items-center justify-between px-4 sm:px-5",
    style: {
      height: 34
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "mono text-[11px] tracking-wide text-white/55"
  }, lang === "hi" ? "भारत संस्करण" : "India Edition"), /*#__PURE__*/React.createElement("div", {
    className: "flex items-center gap-4"
  }, /*#__PURE__*/React.createElement("span", {
    className: `hidden sm:inline mono text-[11px] text-white/55 ${lang === "hi" ? "deva" : ""}`
  }, today), /*#__PURE__*/React.createElement("div", {
    className: "flex items-center gap-1"
  }, ["en", "hi"].map(l => /*#__PURE__*/React.createElement("button", {
    key: l,
    onClick: () => setLang(l),
    className: `px-1.5 mono text-[11px] font-semibold ${lang === l ? "text-white underline underline-offset-4" : "text-white/50 hover:text-white/80"} ${l === "hi" ? "deva" : ""}`
  }, l === "en" ? "EN" : "हिं"))), /*#__PURE__*/React.createElement("button", {
    onClick: () => setDark(!dark),
    className: "text-white/55 hover:text-white",
    "aria-label": "Theme"
  }, dark ? /*#__PURE__*/React.createElement(Sun, {
    size: 15
  }) : /*#__PURE__*/React.createElement(Moon, {
    size: 15
  })))));
}
// Language switch — the design's bordered EN/हिं toggle. Active side fills with ink,
// inactive stays paper. 44px tap target on mobile. No caps on Devanagari.
function LangToggle({
  t,
  lang,
  setLang,
  dark
}) {
  return /*#__PURE__*/React.createElement("span", {
    className: "flex",
    style: {
      border: `1px solid ${t.ink}`
    }
  }, ["en", "hi"].map(l => {
    const on = lang === l;
    return /*#__PURE__*/React.createElement("button", {
      key: l,
      onClick: () => setLang(l),
      "aria-label": l === "en" ? "English" : "हिन्दी",
      className: `flex items-center justify-center ${l === "hi" ? "deva" : ""}`,
      style: {
        minWidth: 40,
        minHeight: 30,
        padding: "0 11px",
        font: l === "en" ? "500 11px/1 'IBM Plex Sans',sans-serif" : "400 14px/1 'IBM Plex Sans Devanagari',sans-serif",
        letterSpacing: l === "en" ? ".1em" : 0,
        background: on ? t.ink : "transparent",
        color: on ? dark ? "#201F1C" : "#F4F1EA" : t.ink
      }
    }, l === "en" ? "EN" : "हिं");
  }));
}
// Masthead — brand, inline nav with a 2px active underline, search as an icon, the
// language toggle, and the theme switch. Ink-on-paper, hairline rule below; no dark
// utility strip, no topic-chip rail (design spec 2a).
// Save/unsave a story (bookmark). Stops the click from also opening the card.
function SaveButton({
  id,
  t,
  lang,
  compact
}) {
  const P = usePaksh();
  const on = P.isSaved(id);
  const label = on ? lang === "hi" ? "सहेजा" : "Saved" : lang === "hi" ? "सहेजें" : "Save";
  return /*#__PURE__*/React.createElement("button", {
    onClick: e => {
      e.stopPropagation();
      e.preventDefault();
      P.toggleSave(id);
    },
    "aria-pressed": on,
    title: label,
    className: `inline-flex shrink-0 items-center gap-1.5 eyebrow ${on ? t.tp : t.ts} hover:${t.tp}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : ".1em"
    }
  }, /*#__PURE__*/React.createElement(Bookmark, {
    size: 13,
    fill: on ? "currentColor" : "none"
  }), !compact && /*#__PURE__*/React.createElement("span", {
    className: lang === "hi" ? "deva" : ""
  }, label));
}
// Follow/unfollow a topic - drives the "For You" feed in Your Paksh.
function FollowButton({
  topic,
  t,
  lang
}) {
  const P = usePaksh();
  const on = P.isFollowing(topic);
  return /*#__PURE__*/React.createElement("button", {
    onClick: () => P.toggleFollow(topic),
    "aria-pressed": on,
    className: `inline-flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-[12.5px] font-semibold ${on ? `${t.cta} ${t.ctaT} border-transparent` : `${t.border} ${t.ts} hover:${t.tp}`} ${lang === "hi" ? "deva" : ""}`
  }, on ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Check, {
    size: 13
  }), " ", lang === "hi" ? "फ़ॉलो किया" : "Following") : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("span", {
    "aria-hidden": "true"
  }, "+"), " ", lang === "hi" ? "फ़ॉलो करें" : "Follow topic"));
}
// Header account control: an initial-avatar when signed in, "Sign in" otherwise.
// Renders nothing when accounts are disabled, so the anonymous site is unchanged.
function HeaderAuth({
  t,
  lang,
  go
}) {
  const A = useAuth();
  if (!authEnabled()) return null;
  if (A.isLoggedIn()) {
    const em = (A.user() || {}).email || "";
    const initial = (em[0] || "?").toUpperCase();
    return /*#__PURE__*/React.createElement("button", {
      onClick: () => go("you"),
      title: em,
      "aria-label": "Your account",
      className: `grid h-7 w-7 shrink-0 place-items-center rounded-full text-[12px] font-bold ${t.cta} ${t.ctaT}`
    }, initial);
  }
  return /*#__PURE__*/React.createElement("button", {
    onClick: () => go("login"),
    className: `text-[13px] font-semibold ${t.tf} hover:${t.tp} ${lang === "hi" ? "deva" : ""}`
  }, lang === "hi" ? "साइन इन" : "Sign in");
}
function Header({
  t,
  lang,
  setLang,
  dark,
  setDark,
  go,
  view
}) {
  const NAV = [["home", STR[lang].navTop], ["blindspot", STR[lang].navOS], ["topics", ui("sections", lang)], ["about", STR[lang].navMethod], ["you", lang === "hi" ? "आपका पक्ष" : "Your Paksh"]];
  return /*#__PURE__*/React.createElement("header", {
    className: `sticky top-0 z-40 border-b ${t.border} ${t.nav}`
  }, /*#__PURE__*/React.createElement("div", {
    className: "mx-auto max-w-[1280px] px-4 sm:px-10"
  }, /*#__PURE__*/React.createElement("div", {
    className: "flex h-[58px] items-center gap-6"
  }, /*#__PURE__*/React.createElement("button", {
    onClick: () => go("home"),
    className: "flex shrink-0 items-baseline gap-2",
    "aria-label": "Paksh home"
  }, /*#__PURE__*/React.createElement("span", {
    className: `brand-hi text-[27px] leading-none ${t.tp}`
  }, "\u092A\u0915\u094D\u0937"), /*#__PURE__*/React.createElement("span", {
    className: `text-[17px] font-semibold uppercase tracking-[0.30em] ${t.tp}`
  }, "Paksh")), /*#__PURE__*/React.createElement("nav", {
    className: "ml-1 hidden items-center gap-6 md:flex"
  }, NAV.map(([k, label]) => /*#__PURE__*/React.createElement("button", {
    key: k,
    onClick: () => go(k),
    className: `eyebrow relative py-1 ${view === k ? t.tp : `${t.tf} hover:${t.tp}`} ${lang === "hi" ? "deva" : ""}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : ".14em"
    }
  }, label, view === k && /*#__PURE__*/React.createElement("span", {
    className: "absolute -bottom-[3px] left-0 right-0",
    style: {
      height: 2,
      background: t.ink
    }
  })))), /*#__PURE__*/React.createElement("div", {
    className: "ml-auto flex items-center gap-3 sm:gap-4"
  }, /*#__PURE__*/React.createElement("button", {
    onClick: () => go("search"),
    "aria-label": "Search",
    className: `${t.tf} hover:${t.tp}`
  }, /*#__PURE__*/React.createElement(Search, {
    size: 17
  })), /*#__PURE__*/React.createElement(LangToggle, {
    t: t,
    lang: lang,
    setLang: setLang,
    dark: dark
  }), /*#__PURE__*/React.createElement("button", {
    onClick: () => setDark(!dark),
    className: `${t.tf} hover:${t.tp}`,
    "aria-label": "Theme"
  }, dark ? /*#__PURE__*/React.createElement(Sun, {
    size: 16
  }) : /*#__PURE__*/React.createElement(Moon, {
    size: 16
  })), /*#__PURE__*/React.createElement(HeaderAuth, {
    t: t,
    lang: lang,
    go: go
  })))));
}
function BottomNav({
  t,
  lang,
  view,
  go
}) {
  const items = [["home", STR[lang].navTop, Layers], ["blindspot", STR[lang].navOS, Eye], ["topics", ui("sections", lang), Compass], ["you", lang === "hi" ? "आपका" : "You", Bookmark]];
  return /*#__PURE__*/React.createElement("nav", {
    className: `fixed inset-x-0 bottom-0 z-40 border-t md:hidden ${t.border} ${t.nav}`
  }, /*#__PURE__*/React.createElement("div", {
    className: "flex"
  }, items.map(([k, label, Ic]) => /*#__PURE__*/React.createElement("button", {
    key: k,
    onClick: () => go(k),
    className: `flex flex-1 flex-col items-center gap-0.5 py-2 ${view === k ? t.tp : t.tf}`
  }, /*#__PURE__*/React.createElement(Ic, {
    size: 19
  }), /*#__PURE__*/React.createElement("span", {
    className: `text-[9.5px] font-semibold ${lang === "hi" ? "deva" : ""}`
  }, label)))));
}
function Footer({
  t,
  lang,
  go
}) {
  return /*#__PURE__*/React.createElement("footer", {
    className: `mt-12 border-t ${t.border} ${t.surface}`
  }, /*#__PURE__*/React.createElement("div", {
    className: "mx-auto max-w-[1800px] px-4 sm:px-5 py-9"
  }, /*#__PURE__*/React.createElement("div", {
    className: "flex flex-wrap items-end justify-between gap-6"
  }, /*#__PURE__*/React.createElement("div", {
    className: "max-w-md"
  }, /*#__PURE__*/React.createElement("div", {
    className: "flex items-baseline gap-1.5"
  }, /*#__PURE__*/React.createElement("span", {
    className: `brand-hi text-xl ${t.tp}`
  }, "\u092A\u0915\u094D\u0937"), /*#__PURE__*/React.createElement("span", {
    className: `text-[15px] font-semibold uppercase tracking-[0.24em] ${t.tp}`
  }, "Paksh")), /*#__PURE__*/React.createElement("p", {
    className: `mt-2 text-[12.5px] leading-relaxed ${t.tf} ${isHi(lang)}`
  }, STR[lang].footIndependence), /*#__PURE__*/React.createElement("button", {
    onClick: () => go("support"),
    className: `mt-3 inline-flex items-center rounded-full px-4 py-2 text-[12.5px] font-semibold ${t.cta} ${t.ctaT} ${isHi(lang)}`
  }, lang === "hi" ? "पक्ष का सहयोग करें" : "Support Paksh", " \u2192")), /*#__PURE__*/React.createElement("div", {
    className: "flex flex-wrap gap-x-6 gap-y-2"
  }, [["you", lang === "hi" ? "आपका पक्ष" : "Your Paksh"], ["about", STR[lang].navMethod], ["sources", STR[lang].navSrc], ["blindspot", STR[lang].navOS], ["topics", ui("sections", lang)], ["support", lang === "hi" ? "सहयोग" : "Support"], ["contact", lang === "hi" ? "संपर्क" : "Contact"], ["privacy", lang === "hi" ? "गोपनीयता" : "Privacy"]].map(([k, l]) => /*#__PURE__*/React.createElement("button", {
    key: k,
    onClick: () => go(k),
    className: `text-[13px] font-medium ${t.ts} hover:${t.tp} ${lang === "hi" ? "deva" : ""}`
  }, l)))), /*#__PURE__*/React.createElement(SponsorSlot, {
    t: t,
    lang: lang,
    className: "mt-7"
  }), /*#__PURE__*/React.createElement("div", {
    className: `mt-7 border-t pt-5 ${t.border} mono text-[10.5px] uppercase tracking-wide ${t.tf}`
  }, "\xA9 2026 Paksh \xB7 A Redstocks Technology LLP product")));
}

/* ---------------- HOME ---------------- */
// Ad slot — STRUCTURE ONLY until launch. The call sites (home / story / gaps / sources
// / topic) mark where ads go, but with no ADSENSE_CLIENT this renders NOTHING: no box,
// no label, no script, no cookie - zero footprint during review. Going live is the
// one-line ADSENSE_CLIENT change (+ uncomment the loader in index.html), which turns
// every reserved slot into a live responsive unit.
function AdSlot({
  t,
  lang,
  slot,
  format,
  h
}) {
  React.useEffect(() => {
    if (ADSENSE_CLIENT) {
      try {
        (window.adsbygoogle = window.adsbygoogle || []).push({});
      } catch (e) {}
    }
  }, []);
  if (!ADSENSE_CLIENT) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: `relative flex items-center justify-center overflow-hidden border ${t.border} ${t.soft}`,
    style: {
      minHeight: h || 250
    }
  }, /*#__PURE__*/React.createElement("ins", {
    className: "adsbygoogle",
    style: {
      display: "block",
      position: "absolute",
      inset: 0,
      width: "100%",
      height: "100%"
    },
    "data-ad-client": ADSENSE_CLIENT,
    "data-ad-slot": slot || "",
    "data-ad-format": format || "auto",
    "data-full-width-responsive": "true"
  }));
}
function GridGrid({
  items,
  render,
  t,
  lang,
  cols,
  gap
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: `grid ${gap || "gap-5"} ${cols || "sm:grid-cols-2 lg:grid-cols-3"}`
  }, items.map((it, i) => render(it, i)));
}
// SECOND tier — the "Also leading" rail: 22px headline, a taste of the lead, a 12px
// bias bar, mono counts. Data-driven like everything else.
function AlsoLeadingItem({
  story,
  t,
  lang,
  onOpen,
  last
}) {
  const c = story.counts || {
    left: 0,
    center: 0,
    right: 0
  };
  const L = c.left || 0,
    C = c.center || 0,
    R = c.right || 0,
    n = L + C + R;
  return /*#__PURE__*/React.createElement("a", {
    href: "/story/" + encodeURIComponent(story.id),
    onClick: e => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      onOpen(story.id);
    },
    className: `block no-underline group cursor-pointer py-4 ${last ? "" : "border-b"} ${t.border}`
  }, /*#__PURE__*/React.createElement("h3", {
    className: `headline text-[20px] sm:text-[22px] ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`,
    style: {
      lineHeight: lang === "hi" ? 1.34 : 1.24,
      letterSpacing: lang === "hi" ? 0 : "-0.01em",
      textWrap: "pretty"
    }
  }, story.headline), story.lead && /*#__PURE__*/React.createElement("p", {
    className: `mt-2 text-[13.5px] lc-2 ${t.ts} ${readCls(lang)}`,
    style: {
      lineHeight: lang === "hi" ? 1.7 : 1.55
    }
  }, story.lead), /*#__PURE__*/React.createElement("div", {
    className: "mt-3"
  }, /*#__PURE__*/React.createElement(BiasSegments, {
    bias: story.bias,
    t: t,
    h: 12,
    lang: lang
  })), /*#__PURE__*/React.createElement("div", {
    className: `mt-2 mono text-[10.5px] ${t.tf}`
  }, L, " \xB7 ", C, " \xB7 ", R, " \xA0", /*#__PURE__*/React.createElement("span", {
    style: {
      color: t.ink,
      opacity: .55
    }
  }, "n = ", n)));
}
// SECTION tier — 4-up band: kicker + 19px headline + 10px bar + mono counts.
function SectionCard({
  story,
  t,
  lang,
  onOpen
}) {
  const c = story.counts || {
    left: 0,
    center: 0,
    right: 0
  };
  const L = c.left || 0,
    C = c.center || 0,
    R = c.right || 0,
    n = L + C + R;
  const tp = lang === "hi" ? TOPIC_HI[story.topic] || story.topic : story.topic;
  return /*#__PURE__*/React.createElement("a", {
    href: "/story/" + encodeURIComponent(story.id),
    onClick: e => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      onOpen(story.id);
    },
    className: "block no-underline group cursor-pointer"
  }, story.img && /*#__PURE__*/React.createElement("div", {
    className: "mb-3 overflow-hidden"
  }, /*#__PURE__*/React.createElement(Thumb, {
    src: story.img,
    topic: story.topic,
    title: story.headline,
    ratio: "16 / 9",
    t: t,
    lang: lang
  })), /*#__PURE__*/React.createElement("div", {
    className: `eyebrow ${t.tf} ${lang === "hi" ? "deva" : ""}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : ".14em"
    }
  }, tp || "News"), /*#__PURE__*/React.createElement("h3", {
    className: `headline mt-2 text-[18px] sm:text-[19px] ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`,
    style: {
      lineHeight: 1.28,
      textWrap: "pretty"
    }
  }, story.headline), /*#__PURE__*/React.createElement("div", {
    className: "mt-3"
  }, /*#__PURE__*/React.createElement(BiasSegments, {
    bias: story.bias,
    t: t,
    h: 10,
    lang: lang
  })), /*#__PURE__*/React.createElement("div", {
    className: `mt-1.5 mono text-[10.5px] ${t.tf}`
  }, L, " \xB7 ", C, " \xB7 ", R, " \xB7 n = ", n));
}
// BRIEF tier bar — 6px, FLAT fills (hatch would moiré this small), no centre axis; the
// printed count carries the exact reading. Under 3 outlets: the hatched "too thin" state.
function BriefBar({
  bias,
  counts,
  t
}) {
  const L = counts.left || 0,
    C = counts.center || 0,
    R = counts.right || 0,
    n = L + C + R;
  if (n < 3) return /*#__PURE__*/React.createElement("div", {
    style: {
      height: 6,
      border: `1px dashed ${t.tf}`,
      background: "repeating-linear-gradient(45deg,#EAE6DB 0 3px,#E1DCCE 3px 6px)"
    }
  });
  const clsOf = {
    left: "seg-left",
    center: "seg-center-tight",
    right: "seg-right-flat"
  };
  const present = ["left", "center", "right"].filter(k => (bias[k] || 0) > 0);
  return /*#__PURE__*/React.createElement("div", {
    className: "relative flex",
    style: {
      height: 6,
      border: `1px solid ${t.ink}`,
      background: t.track || "#EAE6DB"
    }
  }, present.map((k, i) => /*#__PURE__*/React.createElement(React.Fragment, {
    key: k
  }, i > 0 && /*#__PURE__*/React.createElement("div", {
    style: {
      flex: "0 0 1px",
      background: t.gap || "#F4F1EA"
    }
  }), /*#__PURE__*/React.createElement("div", {
    className: clsOf[k],
    style: {
      flexGrow: bias[k],
      flexBasis: 0,
      minWidth: 2
    }
  }))));
}
// BRIEF tier row — 15px, no summary; a 64px mini-bar to the left with the printed count.
function BriefRow({
  story,
  t,
  lang,
  onOpen,
  first
}) {
  const c = story.counts || {
    left: 0,
    center: 0,
    right: 0
  };
  const L = c.left || 0,
    C = c.center || 0,
    R = c.right || 0,
    n = L + C + R;
  return /*#__PURE__*/React.createElement("a", {
    href: "/story/" + encodeURIComponent(story.id),
    onClick: e => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      onOpen(story.id);
    },
    className: `flex items-baseline gap-3 no-underline group cursor-pointer ${first ? "" : "border-t pt-2.5 mt-2.5"} ${t.border}`,
    style: {
      breakInside: "avoid",
      WebkitColumnBreakInside: "avoid"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "shrink-0",
    style: {
      width: 64
    }
  }, /*#__PURE__*/React.createElement(BriefBar, {
    bias: story.bias,
    counts: c,
    t: t
  }), /*#__PURE__*/React.createElement("div", {
    className: `mt-1 mono text-[10px] ${t.tf}`
  }, n < 3 ? "n<3" : `${L}·${C}·${R}`)), /*#__PURE__*/React.createElement("h4", {
    className: `text-[15px] ${t.ts} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`,
    style: {
      lineHeight: lang === "hi" ? 1.6 : 1.42,
      textWrap: "pretty"
    }
  }, story.headline));
}
// THE ONE REVERSAL — the ink-filled Coverage Gaps band at the fold. The page's only
// ink area; it spends that emphasis on what Paksh exists to say: what one side didn't
// run. Each label ("Missing: Left · 1 of 12") is computed from the real per-lean counts.
function InkGapBand({
  items,
  t,
  lang,
  go,
  open
}) {
  if (!items.length) return null;
  const paper = "#F4F1EA",
    faint = "rgba(244,241,234,.28)";
  return /*#__PURE__*/React.createElement("div", {
    style: {
      background: "#15140F"
    },
    className: "px-4 sm:px-10 py-5 sm:py-6"
  }, /*#__PURE__*/React.createElement("div", {
    className: "flex items-baseline justify-between gap-3 pb-3",
    style: {
      borderBottom: `1px solid ${faint}`
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: `eyebrow ${lang === "hi" ? "deva" : ""}`,
    style: {
      color: paper,
      letterSpacing: lang === "hi" ? 0 : ".16em"
    }
  }, lang === "hi" ? "कवरेज गैप · जो एक पक्ष ने नहीं चलाया" : "Coverage gaps · what one side didn’t run"), /*#__PURE__*/React.createElement("button", {
    onClick: () => go("blindspot"),
    className: "mono text-[10.5px] shrink-0",
    style: {
      color: "rgba(244,241,234,.6)"
    }
  }, items.length, " ", lang === "hi" ? "आज" : "today", " \xB7 ", /*#__PURE__*/React.createElement("span", {
    style: {
      borderBottom: "1px solid rgba(244,241,234,.5)"
    }
  }, lang === "hi" ? "सभी गैप" : "all gaps", " \u2192"))), /*#__PURE__*/React.createElement("div", {
    className: "grid gap-y-5 sm:grid-cols-2 lg:grid-cols-3 pt-4"
  }, items.map((it, i) => /*#__PURE__*/React.createElement("a", {
    key: it.story.id,
    href: "/story/" + encodeURIComponent(it.story.id),
    onClick: e => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      open(it.story.id);
    },
    className: `block no-underline group cursor-pointer ${i > 0 ? "sm:border-l sm:pl-8" : ""}`,
    style: i > 0 ? {
      borderColor: faint
    } : {}
  }, /*#__PURE__*/React.createElement("div", {
    className: `mono text-[10.5px] gap-accent ${lang === "hi" ? "deva" : ""}`
  }, it.label), /*#__PURE__*/React.createElement("div", {
    className: `headline mt-2 text-[17px] sm:text-[18px] ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`,
    style: {
      color: paper,
      lineHeight: 1.3,
      textWrap: "pretty"
    }
  }, it.story.headline)))));
}
// Right-rail companion to the spectrum: the stories where the spectrum agrees most —
// 2+ sides present, smallest skew. Derived arithmetic over the same live counts.
function WidestAgreement({
  cards,
  t,
  lang,
  onOpen
}) {
  const scored = cards.filter(c => {
    const k = c.counts || {};
    return (k.left > 0 ? 1 : 0) + (k.center > 0 ? 1 : 0) + (k.right > 0 ? 1 : 0) >= 2;
  }).map(c => {
    const b = c.bias;
    const skew = Math.max(b.left, b.center, b.right) - Math.min(b.left, b.center, b.right);
    return {
      c,
      skew,
      n: c.sources
    };
  }).sort((a, b) => a.skew - b.skew || b.n - a.n).slice(0, 2);
  if (!scored.length) return null;
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: `eyebrow pb-2 ${t.tp} ${lang === "hi" ? "deva" : ""}`,
    style: {
      borderBottom: `1px solid ${t.ink}`,
      letterSpacing: lang === "hi" ? 0 : ".14em"
    }
  }, lang === "hi" ? "सबसे ज़्यादा सहमति" : "Widest agreement"), scored.map(({
    c
  }, i) => {
    const k = c.counts || {};
    const L = k.left || 0,
      C = k.center || 0,
      R = k.right || 0,
      n = L + C + R;
    return /*#__PURE__*/React.createElement("a", {
      key: c.id,
      href: "/story/" + encodeURIComponent(c.id),
      onClick: e => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        onOpen(c.id);
      },
      className: `block no-underline group cursor-pointer py-3 ${i < scored.length - 1 ? "border-b" : ""} ${t.border}`
    }, /*#__PURE__*/React.createElement("div", {
      className: `headline text-[14.5px] ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`,
      style: {
        lineHeight: 1.35,
        textWrap: "pretty"
      }
    }, c.headline), /*#__PURE__*/React.createElement("div", {
      className: "mt-2"
    }, /*#__PURE__*/React.createElement(BiasSegments, {
      bias: c.bias,
      t: t,
      h: 8,
      lang: lang
    })), /*#__PURE__*/React.createElement("div", {
      className: `mt-1.5 mono text-[10px] ${t.tf}`
    }, L, " \xB7 ", C, " \xB7 ", R, " \xB7 n = ", n));
  }));
}
function HomeView({
  cards,
  gapLeft,
  gapRight,
  topics,
  counts,
  stats,
  t,
  lang,
  open,
  goTopic,
  go
}) {
  // de-dup partition: every story appears in exactly ONE place. Ranking (importance:
  // breadth of distinct outlets across L/C/R, decayed by recency) is UNTOUCHED — the
  // top-ranked story leads, the rest fall into the tier ladder in ranked order.
  const used = new Set();
  const take = (arr, n) => {
    const out = [];
    for (const c of arr) {
      if (out.length >= n) break;
      if (!used.has(c.id)) {
        out.push(c);
        used.add(c.id);
      }
    }
    return out;
  };
  const lead = cards[0];
  if (lead) used.add(lead.id);
  const alsoLeading = take(cards, 2); // "Also leading" rail (2)
  const section = take(cards, 4); // 4-up Section band
  const brief = take(cards, 15); // "In brief" tier
  const notUsed = arr => (arr || []).filter(c => !used.has(c.id));
  // Coverage-gap band items: right-heavier stories are "Missing: Left", left-heavier
  // are "Missing: Right". Labels read the real per-lean counts (N of total).
  const nOf = c => {
    const k = c.counts || {};
    return (k.left || 0) + (k.center || 0) + (k.right || 0);
  };
  const gapItems = [];
  notUsed(gapRight).slice(0, 2).forEach(s => {
    const k = s.counts || {};
    gapItems.push({
      story: s,
      label: lang === "hi" ? `ग़ायब: वाम · ${k.left || 0}/${nOf(s)}` : `Missing: Left · ${k.left || 0} of ${nOf(s)}`
    });
  });
  notUsed(gapLeft).slice(0, 1).forEach(s => {
    const k = s.counts || {};
    gapItems.push({
      story: s,
      label: lang === "hi" ? `ग़ायब: दक्षिण · ${k.right || 0}/${nOf(s)}` : `Missing: Right · ${k.right || 0} of ${nOf(s)}`
    });
  });
  gapItems.slice(0, 3).forEach(g => used.add(g.story.id));
  const pad = "px-4 sm:px-10";
  const browse = /*#__PURE__*/React.createElement("div", {
    className: "mt-9 flex justify-center"
  }, /*#__PURE__*/React.createElement("button", {
    onClick: () => go("topics"),
    className: `border px-5 py-2.5 eyebrow ${t.border} ${t.ts} hover:${t.tp} ${lang === "hi" ? "deva" : ""}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : ".08em"
    }
  }, lang === "hi" ? "सभी सेक्शन देखें" : "Browse all sections", " \u2192"));
  return /*#__PURE__*/React.createElement("div", {
    className: "mx-auto max-w-[1280px]"
  }, /*#__PURE__*/React.createElement("div", {
    className: pad
  }, /*#__PURE__*/React.createElement(DateStrip, {
    t: t,
    lang: lang,
    stats: stats,
    regionFilter: stats.regionFilter,
    setRegionFilter: stats.setRegionFilter
  })), /*#__PURE__*/React.createElement("h1", {
    className: "sr-only"
  }, lang === "hi" ? "पक्ष, भारत की खबरों का हर पक्ष" : "Paksh, every side of India's news"), /*#__PURE__*/React.createElement("div", {
    className: `${pad}`
  }, /*#__PURE__*/React.createElement("div", {
    className: `flex flex-wrap items-center gap-x-4 gap-y-1.5 border-b py-2 ${t.border}`
  }, /*#__PURE__*/React.createElement("span", {
    className: `eyebrow ${t.tf} ${lang === "hi" ? "deva" : ""}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : ".14em"
    }
  }, lang === "hi" ? "बायस बार" : "The bias bar"), ["left", "center", "right"].map(k => /*#__PURE__*/React.createElement("span", {
    key: k,
    className: "inline-flex items-center gap-1.5"
  }, /*#__PURE__*/React.createElement("span", {
    className: `${BIAS[k].tex} inline-block`,
    style: {
      width: 14,
      height: 10,
      border: `1px solid ${t.ink}`
    }
  }), /*#__PURE__*/React.createElement("span", {
    className: `text-[11px] ${t.ts} ${lang === "hi" ? "deva" : ""}`
  }, lbl(k, lang)))), /*#__PURE__*/React.createElement("span", {
    className: `text-[11px] ${t.tf} ${lang === "hi" ? "deva" : ""}`
  }, lang === "hi" ? "हर पक्ष के कितने अलग आउटलेट ने कवर किया · एक प्रकाशक = एक वोट" : "distinct outlets on each side that covered the story · one publisher = one vote"))), /*#__PURE__*/React.createElement("div", {
    className: pad
  }, /*#__PURE__*/React.createElement("div", {
    className: "grid lg:grid-cols-[250px_1fr_280px]",
    style: {}
  }, /*#__PURE__*/React.createElement("div", {
    className: "order-2 lg:order-1 py-4 lg:py-6 lg:pr-7 lg:border-r",
    style: {
      borderColor: t.line
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: `eyebrow pb-2 ${t.tp} ${lang === "hi" ? "deva" : ""}`,
    style: {
      borderBottom: `1px solid ${t.ink}`,
      letterSpacing: lang === "hi" ? 0 : ".14em"
    }
  }, lang === "hi" ? "ये भी प्रमुख" : "Also leading"), alsoLeading.map((s, i) => /*#__PURE__*/React.createElement(AlsoLeadingItem, {
    key: s.id,
    story: s,
    t: t,
    lang: lang,
    onOpen: open,
    last: i === alsoLeading.length - 1
  }))), /*#__PURE__*/React.createElement("div", {
    className: "order-1 lg:order-2 py-4 lg:py-6 lg:px-7 lg:border-r border-b-2 lg:border-b-0",
    style: {
      borderColor: t.line,
      borderBottomColor: t.ink
    }
  }, lead && /*#__PURE__*/React.createElement(LeadStory, {
    story: lead,
    t: t,
    lang: lang,
    onOpen: open
  })), /*#__PURE__*/React.createElement("div", {
    className: "order-3 py-4 lg:py-6 lg:pl-7 space-y-6"
  }, /*#__PURE__*/React.createElement(SpectrumRail, {
    cards: cards,
    t: t,
    lang: lang
  }), /*#__PURE__*/React.createElement(WidestAgreement, {
    cards: cards,
    t: t,
    lang: lang,
    onOpen: open
  })))), /*#__PURE__*/React.createElement("div", {
    style: {
      borderTop: `2px solid ${t.ink}`
    }
  }, /*#__PURE__*/React.createElement(InkGapBand, {
    items: gapItems.slice(0, 3),
    t: t,
    lang: lang,
    go: go,
    open: open
  })), /*#__PURE__*/React.createElement("div", {
    className: pad
  }, /*#__PURE__*/React.createElement("div", {
    className: "grid gap-x-6 gap-y-7 sm:grid-cols-2 lg:grid-cols-4 py-7",
    style: {
      borderBottom: `1px solid ${t.ink}`
    }
  }, section.map((s, i) => /*#__PURE__*/React.createElement("div", {
    key: s.id,
    className: i > 0 ? "lg:border-l lg:pl-6" : "",
    style: i > 0 ? {
      borderColor: t.line
    } : {}
  }, /*#__PURE__*/React.createElement(SectionCard, {
    story: s,
    t: t,
    lang: lang,
    onOpen: open
  }))))), /*#__PURE__*/React.createElement("div", {
    className: pad
  }, /*#__PURE__*/React.createElement("div", {
    className: "py-2"
  }, /*#__PURE__*/React.createElement(AdSlot, {
    t: t,
    lang: lang,
    h: 90,
    format: "horizontal"
  }))), brief.length > 0 && /*#__PURE__*/React.createElement("div", {
    className: pad
  }, /*#__PURE__*/React.createElement("div", {
    className: "py-7"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mb-3.5 flex items-baseline justify-between"
  }, /*#__PURE__*/React.createElement("span", {
    className: `eyebrow ${t.tp} ${lang === "hi" ? "deva" : ""}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : ".16em"
    }
  }, lang === "hi" ? "संक्षेप में · आज ट्रैक की गई बाक़ी सब" : "In brief · everything else tracked today")), /*#__PURE__*/React.createElement("div", {
    style: {
      columnGap: "2.25rem",
      columnRule: `1px solid ${t.line}`
    },
    className: "[column-count:1] sm:[column-count:2] lg:[column-count:3]"
  }, brief.map((s, i) => /*#__PURE__*/React.createElement(BriefRow, {
    key: s.id,
    story: s,
    t: t,
    lang: lang,
    onOpen: open,
    first: i === 0
  }))), browse)));
}
/* ---------------- STORY (tabbed) ---------------- */
function StoryPage({
  story,
  t,
  lang,
  go,
  openTopic,
  related = [],
  open
}) {
  const fr = story.framing || {};
  const outlets = story.outlets || [];
  const counts = {
    left: outlets.filter(o => o.lean === "left").length,
    center: outlets.filter(o => o.lean === "center").length,
    right: outlets.filter(o => o.lean === "right").length,
    international: outlets.filter(o => o.lean === "international").length,
    unrated: outlets.filter(o => o.lean === "unrated").length
  };
  // ONE VOTE PER OWNER: the bias bar counts distinct OWNERS, so co-owned mastheads
  // (Times of India + Navbharat Times) count once. voteRow() reads the authoritative
  // server coverage (count=owner votes, sources=distinct mastheads) and groups the
  // mastheads by owner so the reader can see WHY a side shows "N votes, M outlets".
  const ownerOf = {};
  outlets.forEach(o => {
    if (o.source) ownerOf[o.source] = o.owner || o.source;
  });
  const voteRow = k => {
    const b = story.coverage && story.coverage[k] || {};
    const names = b.sources || [];
    const votes = typeof b.count === "number" ? b.count : counts[k] || 0;
    const gm = new Map();
    names.forEach(n => {
      const ow = ownerOf[n] || n;
      if (!gm.has(ow)) gm.set(ow, []);
      gm.get(ow).push(n);
    });
    return {
      votes,
      outlets: names.length,
      groups: [...gm.entries()]
    };
  };
  // The bias bar's widths come from the distinct-OWNER votes (vc); percentages are
  // derived from those, so the printed scale matches the segments exactly.
  const vc = {
    left: voteRow("left").votes,
    center: voteRow("center").votes,
    right: voteRow("right").votes
  };
  const nVotes = vc.left + vc.center + vc.right;
  const bpct = biasPct(vc);
  const [atab, setAtab] = useState("all");
  const arts = atab === "all" ? outlets : outlets.filter(o => o.lean === atab);
  const total = story.sources + (story.unrated || 0) + (story.international || 0);
  const [copied, setCopied] = useState(false);
  const copy = () => {
    try {
      navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch (e) {}
  };
  const tp = lang === "hi" ? TOPIC_HI[story.topic] || story.topic : story.topic;
  const region = lang === "hi" ? story.region === "World" ? "विश्व" : "भारत" : story.region || "India";
  const metaLine = lang === "hi" ? `${total} स्रोत · वाम ${vc.left} · केंद्र ${vc.center} · दक्षिण ${vc.right} · ${timeAgo(story.created_at, lang)}` : `${total} outlets · ${vc.left} left · ${vc.center} centre · ${vc.right} right · ${timeAgo(story.created_at, lang)}`;
  const ATab = ({
    k,
    n
  }) => {
    const on = atab === k;
    const lab = k === "all" ? lang === "hi" ? "सभी" : "All" : k === "unrated" ? lang === "hi" ? "बिना रेटिंग" : "Unrated" : lbl(k, lang);
    return /*#__PURE__*/React.createElement("button", {
      onClick: () => setAtab(k),
      className: `flex items-center gap-1.5 border-b-2 px-1 pb-2 text-[13.5px] font-semibold ${on ? t.tp : `${t.tf} hover:${t.ts}`}`,
      style: {
        borderColor: on ? k === "all" || k === "center" ? t.ink : BIAS[k] && BIAS[k].color || "#B8B4AC" : "transparent"
      }
    }, lab, /*#__PURE__*/React.createElement("span", {
      className: `mono text-[11px] ${on ? t.ts : t.tf}`
    }, n));
  };
  const frLen = v => Array.isArray(v) ? v.length : typeof v === "string" && v.trim() ? 1 : 0;
  const sides = ["left", "center", "right"].filter(k => frLen(fr[k]) > 0 || counts[k] > 0);
  // Distinguish "this story isn't analysed yet" (all sides blank -> pending) from a side
  // that simply lacks enough unique coverage (some side has a summary, this one doesn't).
  const anyFraming = sides.some(k => frLen(fr[k]) > 0);
  return /*#__PURE__*/React.createElement("div", {
    className: "mx-auto max-w-[1000px] px-4 sm:px-8 py-6"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mb-8 flex items-center justify-between gap-3 pb-3",
    style: {
      borderBottom: `1px solid ${t.ink}`
    }
  }, /*#__PURE__*/React.createElement("button", {
    onClick: () => go("home"),
    className: `inline-flex items-center gap-1.5 eyebrow ${t.ts} hover:${t.tp}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : ".1em"
    }
  }, /*#__PURE__*/React.createElement(ArrowLeft, {
    size: 14
  }), " ", STR[lang].back), /*#__PURE__*/React.createElement("button", {
    onClick: () => openTopic(story.topic),
    className: `hidden sm:inline truncate eyebrow ${t.tf} hover:${t.tp} ${lang === "hi" ? "deva" : ""}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : ".14em"
    }
  }, tp, " \xB7 ", region), /*#__PURE__*/React.createElement("div", {
    className: "flex shrink-0 items-center gap-4"
  }, /*#__PURE__*/React.createElement(SaveButton, {
    id: story.id,
    t: t,
    lang: lang
  }), /*#__PURE__*/React.createElement("button", {
    onClick: copy,
    className: `inline-flex shrink-0 items-center gap-1.5 eyebrow ${t.ts} hover:${t.tp}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : ".1em"
    }
  }, copied ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Check, {
    size: 13
  }), " ", lang === "hi" ? "कॉपी" : "Copied") : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(LinkIcon, {
    size: 13
  }), " ", lang === "hi" ? "शेयर" : "Share")))), /*#__PURE__*/React.createElement("div", {
    className: "mx-auto max-w-[840px] text-left sm:text-center"
  }, /*#__PURE__*/React.createElement("div", {
    className: `eyebrow sm:hidden ${t.tf} ${lang === "hi" ? "deva" : ""}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : ".14em"
    }
  }, tp, " \xB7 ", region), /*#__PURE__*/React.createElement("h1", {
    className: `headline mt-3 sm:mt-0 text-[28px] sm:text-[42px] lg:text-[50px] ${t.tp} ${readCls(lang)}`,
    style: {
      lineHeight: lang === "hi" ? 1.18 : 1.1,
      letterSpacing: lang === "hi" ? 0 : "-0.02em",
      textWrap: "balance"
    }
  }, story.headline), /*#__PURE__*/React.createElement("div", {
    className: `mt-4 mono text-[11.5px] ${t.tf} ${lang === "hi" ? "deva" : ""}`
  }, metaLine, story.auto && /*#__PURE__*/React.createElement(React.Fragment, null, " \xB7 ", /*#__PURE__*/React.createElement("span", {
    className: "uppercase"
  }, STR[lang].autoTag))), absDate(story.created_at, lang) && /*#__PURE__*/React.createElement("div", {
    className: `mt-1 mono text-[10.5px] ${t.tf} ${lang === "hi" ? "deva" : ""}`,
    title: lang === "hi" ? "नवीनतम स्रोत का प्रकाशन समय" : "Newest source's publish time"
  }, absDate(story.created_at, lang))), /*#__PURE__*/React.createElement("div", {
    className: "mx-auto mt-8 max-w-[840px] py-6",
    style: {
      borderTop: `1px solid ${t.ink}`,
      borderBottom: `1px solid ${t.ink}`
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "mb-2.5 flex items-baseline justify-between gap-3"
  }, /*#__PURE__*/React.createElement("div", {
    className: `flex gap-5 sm:gap-6 text-[11px] font-medium uppercase tracking-[0.12em] ${t.tp} ${lang === "hi" ? "deva" : ""}`
  }, ["left", "center", "right"].map(k => vc[k] > 0 ? /*#__PURE__*/React.createElement("span", {
    key: k
  }, lbl(k, lang), " ", /*#__PURE__*/React.createElement("span", {
    className: "mono",
    style: {
      letterSpacing: 0
    }
  }, vc[k])) : null)), /*#__PURE__*/React.createElement("span", {
    className: `mono text-[11px] shrink-0 ${t.tf}`
  }, "n = ", nVotes, " \xB7 ", bpct.left, "/", bpct.center, "/", bpct.right, "%")), /*#__PURE__*/React.createElement(BiasSegments, {
    bias: bpct,
    t: t,
    h: 28,
    lang: lang,
    onPick: k => {
      track("bias_segment", {
        side: k
      });
      setAtab(k);
      const el = document.getElementById("arts");
      if (el) el.scrollIntoView({
        behavior: "smooth",
        block: "start"
      });
    },
    active: atab !== "all" ? atab : null
  }), /*#__PURE__*/React.createElement("div", {
    className: "relative",
    style: {
      height: 15,
      marginTop: 3
    }
  }, [25, 50, 75].map(p => /*#__PURE__*/React.createElement("div", {
    key: p,
    style: {
      position: "absolute",
      left: p + "%",
      top: 0,
      width: 1,
      height: p === 50 ? 7 : 4,
      background: p === 50 ? t.ink : t.line
    }
  })), /*#__PURE__*/React.createElement("span", {
    className: `mono text-[10px] ${t.tf}`,
    style: {
      position: "absolute",
      left: "50%",
      top: 7,
      transform: "translateX(-50%)",
      whiteSpace: "nowrap"
    }
  }, lang === "hi" ? "कवरेज का 50%" : "50% of coverage"))), /*#__PURE__*/React.createElement("div", {
    className: "mx-auto mt-9 max-w-[840px] grid gap-5 md:grid-cols-[200px_1fr] md:gap-11"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: `eyebrow ${t.tp} ${lang === "hi" ? "deva" : ""}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : ".14em"
    }
  }, lang === "hi" ? "बिना फ़्रेमिंग की ख़बर" : "The story, without framing"), story.auto && /*#__PURE__*/React.createElement("div", {
    className: `mt-2 eyebrow ${t.tf} ${lang === "hi" ? "deva" : ""}`,
    style: {
      textTransform: "none",
      letterSpacing: 0
    }
  }, STR[lang].autoFrom)), /*#__PURE__*/React.createElement("div", null, story.lead && /*#__PURE__*/React.createElement("p", {
    className: `text-[16px] md:text-[19px] ${t.tp} ${readCls(lang)}`,
    style: {
      lineHeight: lang === "hi" ? 1.85 : 1.6
    }
  }, story.lead), /*#__PURE__*/React.createElement("ul", {
    className: "mt-3 space-y-2.5"
  }, (story.summary || []).map((p, i) => /*#__PURE__*/React.createElement("li", {
    key: i,
    className: `flex gap-2.5 text-[15px] md:text-[16px] ${t.ts} ${readCls(lang)}`,
    style: {
      lineHeight: lang === "hi" ? 1.8 : 1.6
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "mt-[10px] h-1 w-2 shrink-0",
    style: {
      background: t.ink
    }
  }), p))), /*#__PURE__*/React.createElement("p", {
    className: `mt-4 mono text-[10.5px] leading-[1.6] ${t.tf} ${isHi(lang)}`
  }, STR[lang].aiNote))), sides.length > 0 && /*#__PURE__*/React.createElement("div", {
    className: "mt-10"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mb-4 flex items-baseline justify-between gap-3"
  }, /*#__PURE__*/React.createElement("h3", {
    className: `eyebrow ${t.tp} ${lang === "hi" ? "deva" : ""}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : ".14em"
    }
  }, STR[lang].framingTitle), /*#__PURE__*/React.createElement("span", {
    className: `mono text-[10.5px] hidden sm:inline ${t.tf} ${lang === "hi" ? "deva" : ""}`
  }, lang === "hi" ? "बराबर कॉलम · क्रम बार जैसा" : "equal columns · order matches the bar")), /*#__PURE__*/React.createElement("div", {
    className: "grid grid-cols-1 gap-4 md:grid-cols-3 md:gap-0 md:border",
    style: {
      borderColor: t.ink
    }
  }, sides.map(k => /*#__PURE__*/React.createElement("div", {
    key: k,
    className: `flex flex-col border md:border-0 md:border-r last:md:border-r-0 ${t.surface}`,
    style: {
      borderColor: t.ink
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: BIAS[k].tex,
    style: {
      height: 6
    }
  }), /*#__PURE__*/React.createElement("div", {
    className: "flex flex-1 flex-col p-5"
  }, /*#__PURE__*/React.createElement("div", {
    className: "flex items-baseline justify-between"
  }, /*#__PURE__*/React.createElement("span", {
    className: `text-[11.5px] font-medium uppercase tracking-[0.14em] ${t.tp} ${lang === "hi" ? "deva" : ""}`
  }, lbl(k, lang)), /*#__PURE__*/React.createElement("span", {
    className: `mono text-[10.5px] ${t.tf} ${lang === "hi" ? "deva" : ""}`
  }, counts[k], " ", lang === "hi" ? "मास्टहेड" : counts[k] === 1 ? "masthead" : "mastheads")), Array.isArray(fr[k]) && fr[k].length ? /*#__PURE__*/React.createElement("ul", {
    className: "mt-3.5 space-y-2"
  }, fr[k].map((p, i) => /*#__PURE__*/React.createElement("li", {
    key: i,
    className: `flex gap-2 text-[14px] md:text-[14.5px] ${t.ts} ${readCls(lang)}`,
    style: {
      lineHeight: lang === "hi" ? 1.7 : 1.55
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "mt-[8px] h-1.5 w-1.5 shrink-0 rounded-full",
    style: {
      background: BIAS[k].color
    }
  }), p))) : typeof fr[k] === "string" && fr[k].trim() ? /*#__PURE__*/React.createElement("p", {
    className: `mt-3.5 text-[14.5px] md:text-[15px] ${t.ts} ${readCls(lang)}`,
    style: {
      lineHeight: lang === "hi" ? 1.75 : 1.62
    }
  }, fr[k]) : /*#__PURE__*/React.createElement("p", {
    className: `mt-3.5 text-[13px] italic ${t.tf} ${readCls(lang)}`
  }, anyFraming ? STR[lang].framingThin : STR[lang].framingPending))))), /*#__PURE__*/React.createElement("p", {
    className: `mt-3 mono text-[10.5px] leading-[1.6] ${t.tf} ${isHi(lang)}`
  }, STR[lang].framingSub)), /*#__PURE__*/React.createElement("div", {
    className: "mx-auto mt-10 max-w-[840px]"
  }, /*#__PURE__*/React.createElement("div", {
    className: "pb-2",
    style: {
      borderBottom: `1px solid ${t.ink}`
    }
  }, /*#__PURE__*/React.createElement("h3", {
    className: `eyebrow ${t.tp} ${lang === "hi" ? "deva" : ""}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : ".14em"
    }
  }, STR[lang].coverageBreakdown)), /*#__PURE__*/React.createElement("div", {
    className: `mt-2 flex items-center justify-between border-b py-2.5 ${t.border}`
  }, /*#__PURE__*/React.createElement("span", {
    className: `text-[13px] font-semibold ${t.tp} ${readCls(lang)}`
  }, STR[lang].totalSources), /*#__PURE__*/React.createElement("span", {
    className: `mono text-[14px] font-semibold ${t.tp}`
  }, total)), ["left", "center", "right"].map(k => {
    const {
      votes,
      outlets: oc,
      groups
    } = voteRow(k);
    if (votes === 0 && oc === 0) return null;
    const coOwned = groups.some(([o, ms]) => ms.length > 1);
    return /*#__PURE__*/React.createElement("div", {
      key: k,
      className: `border-b py-3 ${t.border}`
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center justify-between"
    }, /*#__PURE__*/React.createElement("span", {
      className: "flex items-center gap-2.5"
    }, /*#__PURE__*/React.createElement("span", {
      className: `${BIAS[k].tex} shrink-0`,
      style: {
        width: 14,
        height: 14,
        border: `1px solid ${t.ink}`
      }
    }), /*#__PURE__*/React.createElement("span", {
      className: `text-[13px] ${t.ts} ${lang === "hi" ? "deva" : ""}`
    }, lbl(k, lang))), /*#__PURE__*/React.createElement("span", {
      className: `mono text-[14px] font-semibold ${t.tp}`
    }, votes, oc > votes && /*#__PURE__*/React.createElement("span", {
      className: `ml-1 text-[11px] font-normal ${t.tf}`
    }, lang === "hi" ? `प्रकाशक · ${oc} मास्टहेड` : `${votes === 1 ? "publisher" : "publishers"} · ${oc} mastheads`))), coOwned && /*#__PURE__*/React.createElement("div", {
      className: "mt-1.5 space-y-0.5 pl-6"
    }, groups.filter(([o, ms]) => ms.length > 1).map(([o, ms], j) => /*#__PURE__*/React.createElement("div", {
      key: j,
      className: `text-[11px] leading-snug ${t.tf} ${isHi(lang)}`
    }, ms.join(" · "), " ", /*#__PURE__*/React.createElement("span", {
      className: "italic"
    }, "(", o, " \u2014 ", lang === "hi" ? "1 वोट" : "1 vote", ")")))));
  }), story.international > 0 && /*#__PURE__*/React.createElement("div", {
    className: `flex items-center justify-between border-b py-2.5 ${t.border}`
  }, /*#__PURE__*/React.createElement("span", {
    className: `text-[13px] ${t.ts} ${isHi(lang)}`
  }, STR[lang].intlTitle), /*#__PURE__*/React.createElement("span", {
    className: `mono text-[14px] font-semibold ${t.tp}`
  }, story.international)), story.unrated > 0 && /*#__PURE__*/React.createElement("div", {
    className: `flex items-center justify-between border-b py-2.5 ${t.border}`
  }, /*#__PURE__*/React.createElement("span", {
    className: `text-[13px] ${t.ts} ${isHi(lang)}`
  }, STR[lang].unratedTitle), /*#__PURE__*/React.createElement("span", {
    className: `mono text-[14px] font-semibold ${t.tp}`
  }, story.unrated)), story.blindspot && /*#__PURE__*/React.createElement("div", {
    className: `mt-4 flex items-start gap-2 p-3 text-[12px] leading-relaxed ${t.blindSoft} ${t.blind} ${isHi(lang)}`
  }, /*#__PURE__*/React.createElement(Eye, {
    size: 15,
    className: "mt-0.5 shrink-0"
  }), /*#__PURE__*/React.createElement("span", null, STR[lang].osCalloutBody1, " ", /*#__PURE__*/React.createElement("strong", null, story.bias[story.blindspot], "%"), " ", STR[lang].osCalloutBody2)), /*#__PURE__*/React.createElement("p", {
    className: `mt-4 text-[11px] leading-relaxed ${t.tf} ${isHi(lang)}`
  }, STR[lang].aiNote)), /*#__PURE__*/React.createElement("div", {
    className: "mx-auto mt-10 max-w-[840px]"
  }, /*#__PURE__*/React.createElement(AdSlot, {
    t: t,
    lang: lang,
    h: 110,
    format: "horizontal"
  })), /*#__PURE__*/React.createElement("div", {
    className: "mx-auto mt-10 max-w-[840px]",
    id: "arts"
  }, /*#__PURE__*/React.createElement("div", {
    className: `mb-3 eyebrow ${t.tp} ${lang === "hi" ? "deva" : ""}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : ".14em"
    }
  }, lang === "hi" ? "किसने कवर किया" : "Who covered it"), /*#__PURE__*/React.createElement("div", {
    className: `flex items-center gap-5 border-b ${t.border}`
  }, /*#__PURE__*/React.createElement(ATab, {
    k: "all",
    n: outlets.length
  }), counts.left > 0 && /*#__PURE__*/React.createElement(ATab, {
    k: "left",
    n: counts.left
  }), counts.center > 0 && /*#__PURE__*/React.createElement(ATab, {
    k: "center",
    n: counts.center
  }), counts.right > 0 && /*#__PURE__*/React.createElement(ATab, {
    k: "right",
    n: counts.right
  }), counts.international > 0 && /*#__PURE__*/React.createElement(ATab, {
    k: "international",
    n: counts.international
  }), counts.unrated > 0 && /*#__PURE__*/React.createElement(ATab, {
    k: "unrated",
    n: counts.unrated
  })), /*#__PURE__*/React.createElement("div", {
    className: "mt-4 space-y-2.5"
  }, arts.map((o, i) => /*#__PURE__*/React.createElement("a", {
    key: i,
    href: o.url || "#",
    target: "_blank",
    rel: "nofollow noopener noreferrer",
    onClick: () => track("source_open", {
      side: o.lean
    }),
    className: `flex items-start gap-3 border p-3.5 ${t.surface} ${t.border} hover:${t.soft}`
  }, /*#__PURE__*/React.createElement(OutletAvatar, {
    o: o,
    side: o.lean,
    size: 30
  }), /*#__PURE__*/React.createElement("div", {
    className: "min-w-0 flex-1"
  }, /*#__PURE__*/React.createElement("div", {
    className: "flex items-center gap-2"
  }, /*#__PURE__*/React.createElement("span", {
    className: `text-[13px] font-bold ${t.tp}`
  }, o.source), /*#__PURE__*/React.createElement(LeanBadge, {
    side: o.lean,
    lang: lang,
    t: t
  }), /*#__PURE__*/React.createElement("span", {
    className: `ml-auto mono text-[10px] ${t.tf}`
  }, (o.language || "en").toUpperCase())), o.headline && /*#__PURE__*/React.createElement("div", {
    className: `mt-1 text-[14.5px] leading-snug ${t.ts} ${readCls(lang)}`
  }, o.headline)), /*#__PURE__*/React.createElement(ArrowUpRight, {
    size: 15,
    className: `mt-0.5 shrink-0 ${t.tf}`
  }))), arts.length === 0 && /*#__PURE__*/React.createElement("div", {
    className: `py-10 text-center text-[13px] ${t.tf}`
  }, "-"))), related && related.length > 0 && open && /*#__PURE__*/React.createElement("div", {
    className: "mx-auto mt-12 max-w-[1000px]"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mb-4 pb-2",
    style: {
      borderBottom: `1px solid ${t.ink}`
    }
  }, /*#__PURE__*/React.createElement("h3", {
    className: `eyebrow ${t.tp} ${lang === "hi" ? "deva" : ""}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : ".14em"
    }
  }, lang === "hi" ? `${tp} पर और खबरें` : `More on ${tp}`)), /*#__PURE__*/React.createElement("div", {
    className: "grid gap-x-7 gap-y-6 sm:grid-cols-2 lg:grid-cols-3"
  }, related.map(s => /*#__PURE__*/React.createElement(GridCard, {
    key: s.id,
    story: s,
    t: t,
    lang: lang,
    onOpen: open
  })))));
}

/* ---------------- other pages ---------------- */
function PageWrap({
  children
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "mx-auto max-w-[1280px] px-4 sm:px-10 py-8"
  }, children);
}
// Coverage-gap rate columns — three EQUAL-WIDTH slots; each fill's height is that side's
// SHARE of its own tracked outlets that ran the story (a rate, not a raw count, so a
// side with more tracked outlets is normalised, not penalised). The absent side is drawn
// as a hatch so absence occupies space. Driven by live per-lean counts + the roster.
function GapRateColumns({
  counts,
  roster,
  gapSide,
  t,
  lang
}) {
  const ks = ["left", "center", "right"];
  return /*#__PURE__*/React.createElement("div", {
    className: "grid grid-cols-3 gap-2"
  }, ks.map(k => {
    const n = counts[k] || 0;
    const m = roster[k] || 0;
    const rate = m > 0 ? Math.min(100, Math.round(n / m * 100)) : 0;
    const isGap = k === gapSide;
    return /*#__PURE__*/React.createElement("div", {
      key: k
    }, /*#__PURE__*/React.createElement("div", {
      className: `flex items-end ${n > 0 ? "" : "seg-absent"}`,
      style: {
        height: 56,
        border: n > 0 ? `1px solid ${t.ink}` : `1px dashed ${t.tf}`,
        background: n > 0 ? t.track || "#EAE6DB" : undefined
      }
    }, n > 0 && /*#__PURE__*/React.createElement("div", {
      className: `w-full ${BIAS[k].tex}`,
      style: {
        height: `${Math.max(8, rate)}%`
      }
    })), /*#__PURE__*/React.createElement("div", {
      className: `mt-1.5 text-[9.5px] font-medium uppercase tracking-[0.1em] ${t.tp} ${lang === "hi" ? "deva" : ""}`
    }, lbl(k, lang)), /*#__PURE__*/React.createElement("div", {
      className: `mono text-[10.5px] ${isGap ? t.blind : t.tf}`
    }, n, " / ", m));
  }));
}
// A single coverage-gap card: which side missed it (eyebrow, clay), the headline, a
// taste of the neutral summary, the rate columns, and a link into the story.
function GapCard({
  story,
  roster,
  gapSide,
  t,
  lang,
  onOpen
}) {
  const c = story.counts || {
    left: 0,
    center: 0,
    right: 0
  };
  const gapN = c[gapSide] || 0;
  const sideWord = lang === "hi" ? gapSide === "left" ? "वाम" : "दक्षिण" : gapSide;
  const eyebrow = lang === "hi" ? gapN === 0 ? `${sideWord} पर अप्रकाशित` : `${sideWord} पर कम कवरेज` : gapN === 0 ? `Unreported on the ${sideWord}` : `Under-covered on the ${sideWord}`;
  return /*#__PURE__*/React.createElement("a", {
    href: "/story/" + encodeURIComponent(story.id),
    onClick: e => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      onOpen(story.id);
    },
    className: "flex h-full flex-col no-underline group cursor-pointer"
  }, /*#__PURE__*/React.createElement("div", {
    className: `eyebrow ${t.blind} ${lang === "hi" ? "deva" : ""}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : ".14em"
    }
  }, eyebrow), /*#__PURE__*/React.createElement("h3", {
    className: `headline mt-3 text-[20px] lg:text-[24px] ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`,
    style: {
      lineHeight: 1.24,
      textWrap: "pretty"
    }
  }, story.headline), story.lead && /*#__PURE__*/React.createElement("p", {
    className: `mt-2.5 text-[14px] lg:text-[15px] lc-3 ${t.ts} ${readCls(lang)}`,
    style: {
      lineHeight: lang === "hi" ? 1.7 : 1.6
    }
  }, story.lead), /*#__PURE__*/React.createElement("div", {
    className: "mt-5"
  }, /*#__PURE__*/React.createElement(GapRateColumns, {
    counts: c,
    roster: roster,
    gapSide: gapSide,
    t: t,
    lang: lang
  })), /*#__PURE__*/React.createElement("div", {
    className: `mt-4 eyebrow ${t.tp} ${lang === "hi" ? "deva" : ""}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : ".06em"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      borderBottom: `1px solid ${t.ink}`,
      paddingBottom: 2
    }
  }, lang === "hi" ? "तटस्थ सारांश पढ़ें" : "Read the neutral summary", " \u2192")));
}
function BlindspotPage({
  left,
  right,
  roster,
  agg,
  stats,
  t,
  lang,
  open,
  go
}) {
  // left = left_heavier (RIGHT is the under-covered side); right = right_heavier (LEFT is).
  const cards = [];
  (right || []).forEach(s => cards.push({
    story: s,
    gapSide: "left"
  }));
  (left || []).forEach(s => cards.push({
    story: s,
    gapSide: "right"
  }));
  // Starkest first: the smallest under-covered count (0 = unreported) leads.
  cards.sort((a, b) => ((a.story.counts || {})[a.gapSide] || 0) - ((b.story.counts || {})[b.gapSide] || 0));
  const shown = cards.slice(0, 15);
  const gapsToday = agg.total != null ? agg.total : cards.length;
  const pad = "px-4 sm:px-10";
  const explain = (head, body) => /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: `eyebrow ${t.tp} ${lang === "hi" ? "deva" : ""}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : ".14em"
    }
  }, head), /*#__PURE__*/React.createElement("p", {
    className: `mt-2.5 text-[14px] ${t.ts} ${readCls(lang)}`,
    style: {
      lineHeight: lang === "hi" ? 1.75 : 1.65
    }
  }, body));
  return /*#__PURE__*/React.createElement("div", {
    className: "mx-auto max-w-[1280px]"
  }, /*#__PURE__*/React.createElement("div", {
    className: `${pad} pt-6`
  }, /*#__PURE__*/React.createElement("div", {
    className: "flex flex-wrap items-end justify-between gap-4 pb-5",
    style: {
      borderBottom: `2px solid ${t.ink}`
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "max-w-[62ch]"
  }, /*#__PURE__*/React.createElement("h1", {
    className: `headline text-[30px] sm:text-[40px] ${t.tp} ${readCls(lang)}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : "-0.018em"
    }
  }, STR[lang].osTitle), /*#__PURE__*/React.createElement("p", {
    className: `mt-3 text-[15px] sm:text-[16px] ${t.ts} ${readCls(lang)}`,
    style: {
      lineHeight: lang === "hi" ? 1.75 : 1.6
    }
  }, STR[lang].osSub)), /*#__PURE__*/React.createElement("div", {
    className: `mono text-[11px] leading-[1.7] text-right shrink-0 ${t.tf}`
  }, gapsToday, " ", lang === "hi" ? "गैप आज" : "gaps today", /*#__PURE__*/React.createElement("br", null), stats.stories, " ", lang === "hi" ? "ख़बरें ट्रैक" : "stories tracked"))), /*#__PURE__*/React.createElement("div", {
    className: pad
  }, shown.length ? /*#__PURE__*/React.createElement("div", {
    className: "grid gap-x-6 gap-y-9 py-8 sm:grid-cols-2 lg:grid-cols-3",
    style: {
      borderBottom: `1px solid ${t.ink}`
    }
  }, shown.map((g, i) => /*#__PURE__*/React.createElement("div", {
    key: g.story.id,
    className: i > 0 ? "lg:border-l lg:pl-6" : "",
    style: i > 0 ? {
      borderColor: t.line
    } : {}
  }, /*#__PURE__*/React.createElement(GapCard, {
    story: g.story,
    roster: roster,
    gapSide: g.gapSide,
    t: t,
    lang: lang,
    onOpen: open
  })))) : /*#__PURE__*/React.createElement("div", {
    className: `my-8 border border-dashed p-10 text-center text-[13px] ${t.border} ${t.tf} ${readCls(lang)}`
  }, STR[lang].noStories)), /*#__PURE__*/React.createElement("div", {
    className: pad
  }, /*#__PURE__*/React.createElement("div", {
    className: "py-6"
  }, /*#__PURE__*/React.createElement(AdSlot, {
    t: t,
    lang: lang,
    h: 90,
    format: "horizontal"
  }))), /*#__PURE__*/React.createElement("div", {
    className: pad
  }, /*#__PURE__*/React.createElement("div", {
    className: `my-8 grid gap-8 p-6 sm:p-8 md:grid-cols-2 ${t.soft}`
  }, explain(lang === "hi" ? "गैप कैसे तय होता है" : "How a gap is declared", lang === "hi" ? "पक्ष किसी ख़बर को गैप तब चिह्नित करता है जब स्पेक्ट्रम के एक तरफ़ के आउटलेट्स ने उसे कवर किया पर दूसरी तरफ़ के बहुत कम या किसी ने नहीं, वही अलग-अलग आउटलेट गिनती जो बायस बार में है। यह अंकगणित है, इस पर निर्णय नहीं कि किसी पक्ष ने इसे क्यों कवर किया या नहीं।" : "Paksh flags a story as a gap when outlets on one side of the spectrum covered it while few or none on the other did, the same distinct-outlet-per-lean counting as the bias bar. It's arithmetic, not a judgment about why a side did or didn't cover it."), explain(lang === "hi" ? "स्लॉट बराबर चौड़े क्यों" : "Why the slots are equal width", lang === "hi" ? "यह चार्ट बायस बार नहीं है। बायस बार जो मौजूद है उसे बाँटता है; गैप चार्ट हर पक्ष को बराबर स्लॉट देता है, ताकि ग़ैरमौजूद पक्ष ग़ायब होने के बजाय, हैच और शून्य के साथ, दिखे। अनुपस्थिति को दिखने के लिए जगह घेरनी पड़ती है।" : "This chart is not the bias bar. The bias bar divides what exists; the gap chart reserves an equal slot per side, so the empty one is drawn, hatched and labelled zero, instead of vanishing. Absence has to occupy space to be seen."))));
}
function TopicsHub({
  topics,
  counts,
  t,
  lang,
  goTopic
}) {
  return /*#__PURE__*/React.createElement(PageWrap, null, /*#__PURE__*/React.createElement("h1", {
    className: `headline text-[30px] sm:text-[40px] ${t.tp} ${readCls(lang)}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : "-0.018em"
    }
  }, ui("sections", lang)), /*#__PURE__*/React.createElement("div", {
    className: "mt-7 grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
  }, topics.map(tp => /*#__PURE__*/React.createElement("button", {
    key: tp,
    onClick: () => goTopic(tp),
    className: `flex items-center justify-between border p-5 text-left ${t.surface} ${t.border} hover:${t.soft}`
  }, /*#__PURE__*/React.createElement("span", {
    className: `headline text-[18px] ${t.tp} ${readCls(lang)}`
  }, lang === "hi" ? TOPIC_HI[tp] || tp : tp), /*#__PURE__*/React.createElement(ChevronRight, {
    size: 16,
    className: t.tf
  })))));
}
function TopicPage({
  topic,
  items,
  t,
  lang,
  open,
  go
}) {
  return /*#__PURE__*/React.createElement(PageWrap, null, /*#__PURE__*/React.createElement("button", {
    onClick: () => go("topics"),
    className: `mb-4 inline-flex items-center gap-1.5 eyebrow ${t.ts} hover:${t.tp}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : ".1em"
    }
  }, /*#__PURE__*/React.createElement(ArrowLeft, {
    size: 14
  }), " ", ui("sections", lang)), /*#__PURE__*/React.createElement("div", {
    className: "mb-7 flex flex-wrap items-center justify-between gap-4"
  }, /*#__PURE__*/React.createElement("h1", {
    className: `headline text-[30px] sm:text-[40px] ${t.tp} ${readCls(lang)}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : "-0.018em"
    }
  }, lang === "hi" ? TOPIC_HI[topic] || topic : topic), /*#__PURE__*/React.createElement(FollowButton, {
    topic: topic,
    t: t,
    lang: lang
  })), items.length ? /*#__PURE__*/React.createElement(GridGrid, {
    items: items,
    t: t,
    lang: lang,
    render: s => /*#__PURE__*/React.createElement(GridCard, {
      key: s.id,
      story: s,
      t: t,
      lang: lang,
      onOpen: open
    })
  }) : /*#__PURE__*/React.createElement("div", {
    className: `py-24 text-center ${t.tf} ${isHi(lang)}`
  }, STR[lang].noStories), /*#__PURE__*/React.createElement("div", {
    className: "mt-8"
  }, /*#__PURE__*/React.createElement(AdSlot, {
    t: t,
    lang: lang,
    h: 90,
    format: "horizontal"
  })));
}
// AxisBars — the 3 editorial tonality axes as labelled position markers. A dot sits
// at value% between the two poles; purely a display of the per-publisher `axes` set by
// editors. Does not touch, replace or feed the arithmetic bias bar.
function AxisBars({
  axes,
  t,
  lang
}) {
  if (!axes) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "mt-3 space-y-2.5"
  }, AXES.map(ax => {
    const raw = axes[ax.key];
    if (raw == null) return null;
    const v = Math.max(0, Math.min(100, raw));
    const L = ax[lang] || ax.en;
    return /*#__PURE__*/React.createElement("div", {
      key: ax.key
    }, /*#__PURE__*/React.createElement("div", {
      className: `flex items-baseline justify-between mono text-[9px] uppercase tracking-wide ${lang === "hi" ? "deva" : ""}`,
      style: {
        letterSpacing: lang === "hi" ? 0 : ".06em"
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: t.tf
    }, L.lo), /*#__PURE__*/React.createElement("span", {
      className: `${t.ts} font-bold`
    }, L.name), /*#__PURE__*/React.createElement("span", {
      className: t.tf
    }, L.hi)), /*#__PURE__*/React.createElement("div", {
      className: "relative mt-1 h-1.5 rounded-full",
      style: {
        background: "rgba(120,119,104,0.20)"
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full",
      style: {
        left: `${v}%`,
        backgroundColor: ax.color,
        boxShadow: "0 0 0 2px rgba(255,255,255,0.85)"
      },
      title: `${L.name}: ${v}/100`
    })));
  }));
}
function SourceCard({
  s,
  t,
  lang
}) {
  const side = ["left", "center", "right"].includes(s.lean) ? s.lean : null;
  return /*#__PURE__*/React.createElement("div", {
    className: `rounded-lg border p-4 ${t.surface} ${t.border}`,
    style: side ? {
      borderLeftWidth: 3,
      borderLeftColor: BIAS[side].color
    } : {}
  }, /*#__PURE__*/React.createElement("div", {
    className: "flex items-start justify-between gap-3"
  }, /*#__PURE__*/React.createElement("div", {
    className: "min-w-0"
  }, /*#__PURE__*/React.createElement("div", {
    className: `headline text-[15px] ${t.tp} ${readCls(lang)}`
  }, s.name), s.website && /*#__PURE__*/React.createElement("a", {
    href: s.website,
    target: "_blank",
    rel: "nofollow noopener noreferrer",
    className: `mono text-[11px] break-all ${t.tf} hover:${t.ts}`
  }, (s.website || "").replace(/^https?:\/\//, ""))), side ? /*#__PURE__*/React.createElement(LeanBadge, {
    side: side,
    lang: lang,
    t: t
  }) : /*#__PURE__*/React.createElement("span", {
    className: `shrink-0 rounded mono px-1.5 py-0.5 text-[10px] font-bold uppercase ${t.chip} ${t.tf}`
  }, s.label || "-")), /*#__PURE__*/React.createElement("div", {
    className: "mt-2.5 flex flex-wrap items-center gap-2 mono text-[10px]"
  }, /*#__PURE__*/React.createElement("span", {
    className: `uppercase ${t.tf}`
  }, (s.language || "en").toUpperCase()), s.confidence && /*#__PURE__*/React.createElement("span", {
    className: t.tf
  }, "\xB7 conf ", s.confidence), s.contested && /*#__PURE__*/React.createElement("span", {
    className: `rounded px-1.5 py-0.5 font-bold ${t.blindSoft} ${t.blind}`
  }, STR[lang].contested)), s.ownership && /*#__PURE__*/React.createElement("div", {
    className: `mt-2.5 text-[12.5px] leading-[1.55] ${t.ts} ${readCls(lang)}`
  }, /*#__PURE__*/React.createElement("span", {
    className: `font-semibold ${t.tp}`
  }, STR[lang].ownership, ":"), " ", s.ownership), s.rationale && /*#__PURE__*/React.createElement("p", {
    className: `mt-1.5 text-[12.5px] leading-[1.55] ${t.tf} ${readCls(lang)}`
  }, s.rationale), /*#__PURE__*/React.createElement(AxisBars, {
    axes: s.axes,
    t: t,
    lang: lang
  }));
}
function SourcesPage({
  t,
  lang,
  sources
}) {
  const [f, setF] = useState("all");
  const list = (sources || []).filter(s => f === "all" || s.lean === f);
  const filters = [["all", lang === "hi" ? "सभी" : "All"], ["left", lbl("left", lang)], ["center", lbl("center", lang)], ["right", lbl("right", lang)]];
  return /*#__PURE__*/React.createElement(PageWrap, null, /*#__PURE__*/React.createElement("h1", {
    className: `headline text-[30px] sm:text-[40px] ${t.tp} ${readCls(lang)}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : "-0.018em"
    }
  }, STR[lang].srcTitle), /*#__PURE__*/React.createElement("p", {
    className: `mb-5 mt-3 max-w-2xl text-[15px] leading-[1.6] ${t.ts} ${readCls(lang)}`
  }, STR[lang].srcDisclaimer), /*#__PURE__*/React.createElement("div", {
    className: "mb-6 flex flex-wrap gap-2"
  }, filters.map(([k, label]) => /*#__PURE__*/React.createElement("button", {
    key: k,
    onClick: () => setF(k),
    className: `border px-3.5 py-1.5 eyebrow ${f === k ? `${t.cta} ${t.ctaT} border-transparent` : `${t.surface} ${t.border} ${t.ts} hover:${t.tp}`} ${lang === "hi" ? "deva" : ""}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : ".08em"
    }
  }, label))), /*#__PURE__*/React.createElement(GridGrid, {
    items: list,
    t: t,
    lang: lang,
    gap: "gap-4",
    render: s => /*#__PURE__*/React.createElement(SourceCard, {
      key: s.id || s.name,
      s: s,
      t: t,
      lang: lang
    })
  }), /*#__PURE__*/React.createElement("div", {
    className: "mt-8"
  }, /*#__PURE__*/React.createElement(AdSlot, {
    t: t,
    lang: lang,
    h: 90,
    format: "horizontal"
  })));
}
function AboutPage({
  t,
  lang,
  agg
}) {
  const Row = ({
    h,
    children
  }) => /*#__PURE__*/React.createElement("div", {
    className: `border-b py-6 ${t.border}`
  }, /*#__PURE__*/React.createElement("h2", {
    className: `headline text-[20px] ${t.tp} ${readCls(lang)} mb-2`
  }, h), /*#__PURE__*/React.createElement("div", {
    className: `text-[15px] leading-[1.62] ${t.ts} ${readCls(lang)}`
  }, children));
  const a = agg || {};
  const gapText = (STR[lang].m_gap || "").replace("{total}", a.total).replace("{rh}", a.right_heavier).replace("{lh}", a.left_heavier).replace("{lo}", a.left_outlets).replace("{ro}", a.right_outlets);
  return /*#__PURE__*/React.createElement(PageWrap, null, /*#__PURE__*/React.createElement("div", {
    className: "max-w-3xl"
  }, /*#__PURE__*/React.createElement("h1", {
    className: `headline text-[30px] sm:text-[40px] ${t.tp} ${readCls(lang)}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : "-0.018em"
    }
  }, STR[lang].methodTitle), /*#__PURE__*/React.createElement("p", {
    className: `mb-2 mt-3 text-[16px] leading-[1.62] ${t.ts} ${readCls(lang)}`
  }, STR[lang].m_does), /*#__PURE__*/React.createElement(Row, {
    h: STR[lang].m_ruleH
  }, STR[lang].m_rule), /*#__PURE__*/React.createElement(Row, {
    h: STR[lang].m_aiH
  }, STR[lang].m_ai), /*#__PURE__*/React.createElement(Row, {
    h: STR[lang].m_orderH
  }, STR[lang].m_order), /*#__PURE__*/React.createElement(Row, {
    h: STR[lang].m_freshH
  }, STR[lang].m_fresh), a.total != null && /*#__PURE__*/React.createElement(Row, {
    h: STR[lang].m_gapH
  }, gapText), /*#__PURE__*/React.createElement(Row, {
    h: STR[lang].m_rateH
  }, /*#__PURE__*/React.createElement("p", {
    className: "mb-2"
  }, STR[lang].m_rateLede), /*#__PURE__*/React.createElement("p", {
    className: `text-[12px] ${t.tf}`
  }, STR[lang].m_rateFoot)), /*#__PURE__*/React.createElement(Row, {
    h: STR[lang].m_axisH
  }, STR[lang].m_axis), /*#__PURE__*/React.createElement(Row, {
    h: STR[lang].m_partiesH
  }, STR[lang].m_parties), /*#__PURE__*/React.createElement(Row, {
    h: STR[lang].m_provH
  }, STR[lang].m_prov), /*#__PURE__*/React.createElement(Row, {
    h: STR[lang].m_readH
  }, STR[lang].m_appeal)));
}
function ContactPage({
  t,
  lang
}) {
  const [status, setStatus] = useState("idle");
  const [err, setErr] = useState("");
  const L = lang === "hi" ? {
    title: "संपर्क करें",
    lede: "सवाल, सुधार या शिकायत? हमें लिखें, हम हर संदेश पढ़ते हैं।",
    name: "आपका नाम (वैकल्पिक)",
    email: "ईमेल",
    topic: "विषय",
    tQ: "सामान्य सवाल",
    tC: "सुधार / तथ्य-जाँच",
    tX: "शिकायत",
    tO: "अन्य",
    msg: "आपका संदेश",
    send: "भेजें",
    sending: "भेजा जा रहा है…",
    ok: "धन्यवाद, आपका संदेश मिल गया। हम जल्द जवाब देंगे।",
    err: "संदेश नहीं भेजा जा सका। कृपया दोबारा प्रयास करें।"
  } : {
    title: "Contact",
    lede: "A question, a correction, or a complaint? Write to us, we read every message.",
    name: "Your name (optional)",
    email: "Email",
    topic: "Topic",
    tQ: "General question",
    tC: "Correction / fact-check",
    tX: "Complaint",
    tO: "Other",
    msg: "Your message",
    send: "Send",
    sending: "Sending…",
    ok: "Thank you, your message reached us. We'll reply soon.",
    err: "Could not send your message. Please try again."
  };
  async function submit(e) {
    e.preventDefault();
    setStatus("sending");
    setErr("");
    const form = e.currentTarget;
    const body = new FormData(form);
    try {
      const r = await fetch(FORMSPREE_ENDPOINT, {
        method: "POST",
        body,
        headers: {
          Accept: "application/json"
        }
      });
      if (r.ok) {
        setStatus("ok");
        form.reset();
      } else {
        const j = await r.json().catch(() => ({}));
        setErr(j.errors && j.errors.map(x => x.message).join(", ") || L.err);
        setStatus("error");
      }
    } catch (_) {
      setErr(L.err);
      setStatus("error");
    }
  }
  const inp = `w-full rounded-lg border px-3.5 py-2.5 text-[14.5px] outline-none transition-colors ${t.surface} ${t.border} focus:border-[#15140F] ${t.tp} ${isHi(lang)}`;
  const lbl = `mb-1.5 block text-[12.5px] font-semibold ${t.ts} ${isHi(lang)}`;
  return /*#__PURE__*/React.createElement(PageWrap, null, /*#__PURE__*/React.createElement("div", {
    className: "max-w-xl"
  }, /*#__PURE__*/React.createElement("h1", {
    className: `headline text-[30px] sm:text-[40px] ${t.tp} ${readCls(lang)}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : "-0.018em"
    }
  }, L.title), /*#__PURE__*/React.createElement("p", {
    className: `mb-6 mt-3 text-[15px] leading-relaxed ${t.ts} ${isHi(lang)}`
  }, L.lede), status === "ok" ? /*#__PURE__*/React.createElement("div", {
    className: `rounded-lg border p-5 ${t.border} ${t.surface}`
  }, /*#__PURE__*/React.createElement("p", {
    className: `text-[15px] font-medium ${t.tp} ${isHi(lang)}`
  }, L.ok)) : /*#__PURE__*/React.createElement("form", {
    onSubmit: submit,
    className: "space-y-4"
  }, /*#__PURE__*/React.createElement("input", {
    type: "text",
    name: "_gotcha",
    style: {
      display: "none"
    },
    tabIndex: "-1",
    autoComplete: "off"
  }), /*#__PURE__*/React.createElement("input", {
    type: "hidden",
    name: "_subject",
    value: "New Paksh contact message"
  }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("label", {
    className: lbl
  }, L.name), /*#__PURE__*/React.createElement("input", {
    name: "name",
    type: "text",
    className: inp
  })), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("label", {
    className: lbl
  }, L.email), /*#__PURE__*/React.createElement("input", {
    name: "email",
    type: "email",
    required: true,
    className: inp
  })), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("label", {
    className: lbl
  }, L.topic), /*#__PURE__*/React.createElement("select", {
    name: "topic",
    className: inp
  }, /*#__PURE__*/React.createElement("option", null, L.tQ), /*#__PURE__*/React.createElement("option", null, L.tC), /*#__PURE__*/React.createElement("option", null, L.tX), /*#__PURE__*/React.createElement("option", null, L.tO))), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("label", {
    className: lbl
  }, L.msg), /*#__PURE__*/React.createElement("textarea", {
    name: "message",
    required: true,
    rows: "6",
    className: inp
  })), status === "error" && /*#__PURE__*/React.createElement("p", {
    className: "text-[13px] font-medium",
    style: {
      color: "#C0392B"
    }
  }, err), /*#__PURE__*/React.createElement("button", {
    type: "submit",
    disabled: status === "sending",
    className: `rounded-full px-5 py-2.5 text-[14px] font-semibold ${t.cta} ${t.ctaT} disabled:opacity-60 ${isHi(lang)}`
  }, status === "sending" ? L.sending : L.send))));
}
// Sponsor slot: renders NOTHING until SPONSOR.name is set (an empty "supported by" looks
// broken). Drop <SponsorSlot .../> wherever you want the credit to appear once you sign one.
function SponsorSlot({
  t,
  lang,
  className
}) {
  if (!SPONSOR.name) return null;
  const inner = /*#__PURE__*/React.createElement("span", {
    className: `inline-flex flex-wrap items-center justify-center gap-x-2 ${isHi(lang)}`
  }, /*#__PURE__*/React.createElement("span", {
    className: `mono text-[10px] uppercase tracking-[0.16em] ${t.tf}`
  }, lang === "hi" ? "सहयोग" : "Supported by"), /*#__PURE__*/React.createElement("span", {
    className: `text-[13px] font-semibold ${t.tp}`
  }, SPONSOR.name), SPONSOR.line && /*#__PURE__*/React.createElement("span", {
    className: `text-[12px] ${t.tf}`
  }, "\xB7 ", SPONSOR.line));
  return /*#__PURE__*/React.createElement("div", {
    className: `text-center ${className || ""}`
  }, SPONSOR.url ? /*#__PURE__*/React.createElement("a", {
    href: SPONSOR.url,
    target: "_blank",
    rel: "nofollow noopener noreferrer",
    className: "inline-block hover:opacity-80"
  }, inner) : inner);
}
function SupportPage({
  t,
  lang,
  go
}) {
  const [copied, setCopied] = useState(false);
  const copyUpi = () => {
    try {
      navigator.clipboard.writeText(SUPPORT.upi);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch (e) {}
  };
  const L = lang === "hi" ? {
    title: "पक्ष का सहयोग करें",
    lede: "पक्ष एक स्वतंत्र परियोजना है, कोई पेवॉल नहीं, कोई ट्रैकिंग-आधारित विज्ञापन नहीं। हर खबर को हर पक्ष से दिखाना संसाधन माँगता है। यदि पक्ष आपके काम आता है, तो आपका छोटा-सा सहयोग इसे सबके लिए मुफ़्त और स्वतंत्र रखता है।",
    whyH: "आपका पैसा किसमें जाता है",
    why: "आउटलेट्स की कवरेज इकट्ठा करने, उन्हें एक ही खबर में समूहित करने, और तटस्थ सारांश तैयार करने की कंप्यूटिंग लागत में, ताकि पक्ष बिना विज्ञापनदाताओं या किसी पक्ष के दबाव के चलता रहे।",
    upiH: "UPI से सहयोग करें",
    upiPay: "UPI ऐप में खोलें",
    copy: "UPI ID कॉपी करें",
    copied: "कॉपी हो गया",
    linkBtn: "पक्ष का सहयोग करें",
    soonH: "सहयोग विकल्प जल्द ही",
    soon: "हम सुरक्षित भुगतान का तरीक़ा जोड़ रहे हैं। तब तक, हौसला-आफ़ज़ाई या साझेदारी के लिए हमें लिखें।",
    contact: "संपर्क करें →",
    noStrings: "कोई सदस्यता ज़रूरी नहीं · कोई कंटेंट पेवॉल के पीछे नहीं · जितना चाहें उतना दें।"
  } : {
    title: "Support Paksh",
    lede: "Paksh is an independent project, no paywall, no tracking-based advertising. Showing every story from every side takes real resources. If Paksh is useful to you, a small contribution keeps it free and independent for everyone.",
    whyH: "Where your money goes",
    why: "Into the computing cost of gathering outlets' coverage, grouping it into one story, and generating the neutral summaries, so Paksh can run without advertisers or any side leaning on it.",
    upiH: "Support via UPI",
    upiPay: "Open in a UPI app",
    copy: "Copy UPI ID",
    copied: "Copied",
    linkBtn: "Support Paksh",
    soonH: "Support options coming soon",
    soon: "We're setting up a secure way to contribute. Until then, please reach out to cheer us on or discuss a partnership.",
    contact: "Contact us →",
    noStrings: "No membership required · nothing hidden behind a paywall · give whatever you like."
  };
  const btn = `inline-flex items-center justify-center rounded-full px-5 py-2.5 text-[14px] font-semibold ${t.cta} ${t.ctaT} ${isHi(lang)}`;
  const btn2 = `inline-flex items-center justify-center rounded-full border px-5 py-2.5 text-[14px] font-semibold ${t.border} ${t.ts} hover:${t.tp} ${isHi(lang)}`;
  return /*#__PURE__*/React.createElement(PageWrap, null, /*#__PURE__*/React.createElement("div", {
    className: "max-w-2xl"
  }, /*#__PURE__*/React.createElement("h1", {
    className: `headline text-[30px] sm:text-[40px] ${t.tp} ${readCls(lang)}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : "-0.018em"
    }
  }, L.title), /*#__PURE__*/React.createElement("p", {
    className: `mt-4 text-[16px] leading-[1.62] ${t.ts} ${readCls(lang)}`
  }, L.lede), supportReady() ? /*#__PURE__*/React.createElement("div", {
    className: `mt-8 border p-6 ${t.surface} ${t.border}`
  }, SUPPORT.upi && /*#__PURE__*/React.createElement("div", {
    className: "mb-5"
  }, /*#__PURE__*/React.createElement("div", {
    className: `eyebrow mb-2 ${t.tf} ${lang === "hi" ? "deva" : ""}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : ".14em"
    }
  }, L.upiH), /*#__PURE__*/React.createElement("div", {
    className: "flex flex-wrap items-center gap-3"
  }, /*#__PURE__*/React.createElement("a", {
    href: upiLink(),
    className: btn
  }, L.upiPay), /*#__PURE__*/React.createElement("button", {
    onClick: copyUpi,
    className: btn2
  }, copied ? L.copied : L.copy), /*#__PURE__*/React.createElement("span", {
    className: `mono text-[13px] ${t.ts}`
  }, SUPPORT.upi))), SUPPORT.url && /*#__PURE__*/React.createElement("a", {
    href: SUPPORT.url,
    target: "_blank",
    rel: "noopener noreferrer",
    className: btn
  }, L.linkBtn), /*#__PURE__*/React.createElement("p", {
    className: `mt-5 text-[12.5px] ${t.tf} ${isHi(lang)}`
  }, L.noStrings)) : /*#__PURE__*/React.createElement("div", {
    className: `mt-8 border p-6 ${t.surface} ${t.border}`
  }, /*#__PURE__*/React.createElement("div", {
    className: `headline text-[18px] ${t.tp} ${readCls(lang)}`
  }, L.soonH), /*#__PURE__*/React.createElement("p", {
    className: `mt-2 text-[14px] leading-[1.6] ${t.ts} ${readCls(lang)}`
  }, L.soon), /*#__PURE__*/React.createElement("button", {
    onClick: () => go("contact"),
    className: `mt-4 ${btn2}`
  }, L.contact)), /*#__PURE__*/React.createElement("div", {
    className: `mt-8 border-t pt-6 ${t.border}`
  }, /*#__PURE__*/React.createElement("div", {
    className: `headline text-[18px] ${t.tp} ${readCls(lang)}`
  }, L.whyH), /*#__PURE__*/React.createElement("p", {
    className: `mt-2 text-[14.5px] leading-[1.62] ${t.ts} ${readCls(lang)}`
  }, L.why))));
}
function PrivacyPage({
  t,
  lang
}) {
  const Row = ({
    h,
    children
  }) => /*#__PURE__*/React.createElement("div", {
    className: `border-b py-6 ${t.border}`
  }, /*#__PURE__*/React.createElement("h2", {
    className: `headline text-[20px] ${t.tp} serif mb-2`
  }, h), /*#__PURE__*/React.createElement("div", {
    className: `text-[15px] leading-[1.62] serif ${t.ts}`
  }, children));
  return /*#__PURE__*/React.createElement(PageWrap, null, /*#__PURE__*/React.createElement("div", {
    className: "max-w-3xl"
  }, /*#__PURE__*/React.createElement("h1", {
    className: `headline text-[30px] sm:text-[40px] ${t.tp} serif`,
    style: {
      letterSpacing: "-0.018em"
    }
  }, "Privacy Policy"), /*#__PURE__*/React.createElement("p", {
    className: `mb-1 mt-3 text-[13px] ${t.tf}`
  }, "Last updated: 6 August 2026 \xB7 Operated by Redstocks Technology LLP"), lang === "hi" && /*#__PURE__*/React.createElement("p", {
    className: `mb-2 text-[12.5px] deva ${t.tf}`
  }, "\u092F\u0939 \u0917\u094B\u092A\u0928\u0940\u092F\u0924\u093E \u0928\u0940\u0924\u093F \u0905\u0902\u0917\u094D\u0930\u0947\u091C\u093C\u0940 \u092E\u0947\u0902 \u0909\u092A\u0932\u092C\u094D\u0927 \u0939\u0948\u0964"), /*#__PURE__*/React.createElement(Row, {
    h: "Who we are"
  }, "Paksh (\u092A\u0915\u094D\u0937) is a media-transparency service that groups how different Indian outlets cover the same news story and shows the spread of that coverage across the political spectrum."), /*#__PURE__*/React.createElement(Row, {
    h: "What we collect"
  }, "When you use our contact form, we receive the email address and message you choose to send, so that we can reply; that form is processed on our behalf by Formspree. As with most websites, our host (Vercel) keeps standard technical logs (such as IP address and browser type) briefly, for security and reliability. With your consent, we also use Vercel\u2019s privacy-first, cookieless Web Analytics to understand \u2014 only in aggregate \u2014 how the site is used: which stories are read, whether people compare sides, mobile versus desktop, and the like. It does not use cookies, does not identify you, and does not follow you across other websites. If you decline, none of this is collected."), /*#__PURE__*/React.createElement(Row, {
    h: "Cookies and tracking"
  }, "Paksh sets no advertising cookies and does not track you across other websites. Our analytics (Vercel Web Analytics) is cookieless and stores nothing on your device. You choose whether to allow it in the banner shown on your first visit, and declining is fully respected for the whole session. If we introduce advertising (e.g. through Google AdSense) in future, we will update this policy and ask for your consent before any advertising cookies are set."), /*#__PURE__*/React.createElement(Row, {
    h: "How we use information"
  }, "To respond to your messages, to keep the site secure and reliable, and \u2014 from consented, aggregate, non-identifying usage \u2014 to understand how readers engage with coverage, improve Paksh, and inform Redstocks Technology\u2019s research. We do not sell your personal information, and we do not build a profile of you or track you across your devices."), /*#__PURE__*/React.createElement(Row, {
    h: "Third parties"
  }, "We rely on Formspree (which processes contact-form messages) and Vercel (which hosts the site and provides its cookieless Web Analytics). If we add advertising in future, Google would also process data under its own policy, and we will note that here before it happens."), /*#__PURE__*/React.createElement(Row, {
    h: "Your choices"
  }, "You may ask us to access or delete the information you sent through the contact form. Reach us any time via the Contact page."), /*#__PURE__*/React.createElement(Row, {
    h: "Children"
  }, "Paksh is a general news service and is not directed at children."), /*#__PURE__*/React.createElement(Row, {
    h: "Changes"
  }, "We may update this policy from time to time; material changes will be reflected by the date shown above.")));
}
function SearchPage({
  t,
  lang,
  query,
  setQuery,
  results,
  open
}) {
  return /*#__PURE__*/React.createElement(PageWrap, null, /*#__PURE__*/React.createElement("h1", {
    className: `headline mb-5 text-[30px] sm:text-[40px] ${t.tp} ${readCls(lang)}`,
    style: {
      letterSpacing: lang === "hi" ? 0 : "-0.018em"
    }
  }, ui("searchTab", lang)), /*#__PURE__*/React.createElement("div", {
    className: "mb-8 max-w-xl"
  }, /*#__PURE__*/React.createElement("div", {
    className: "relative"
  }, /*#__PURE__*/React.createElement(Search, {
    size: 17,
    className: `absolute left-3 top-1/2 -translate-y-1/2 ${t.tf}`
  }), /*#__PURE__*/React.createElement("input", {
    autoFocus: true,
    value: query || "",
    onChange: e => setQuery(e.target.value),
    placeholder: STR[lang].search,
    className: `w-full border py-2.5 pl-10 pr-3 text-[15px] outline-none ${t.surface} ${t.border} focus:border-[#15140F] ${t.tp} ${lang === "hi" ? "deva" : ""}`
  }))), !query.trim() ? /*#__PURE__*/React.createElement("div", {
    className: `py-24 text-center ${t.tf} ${isHi(lang)}`
  }, ui("searchHint", lang)) : results.length ? /*#__PURE__*/React.createElement(GridGrid, {
    items: results,
    t: t,
    lang: lang,
    render: s => /*#__PURE__*/React.createElement(GridCard, {
      key: s.id,
      story: s,
      t: t,
      lang: lang,
      onOpen: open
    })
  }) : /*#__PURE__*/React.createElement("div", {
    className: `py-24 text-center ${t.tf} ${isHi(lang)}`
  }, /*#__PURE__*/React.createElement("p", {
    className: `text-lg font-bold ${t.ts}`
  }, STR[lang].noResults), /*#__PURE__*/React.createElement("p", {
    className: "mt-1 text-sm"
  }, STR[lang].noResultsSub)));
}
function FeedSkeleton({
  t
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "mx-auto max-w-[1280px] px-4 sm:px-10 py-6"
  }, /*#__PURE__*/React.createElement("div", {
    className: "py-[7px]",
    style: {
      borderTop: `2px solid ${t.ink}`,
      borderBottom: `1px solid ${t.ink}`
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "skel h-3 w-40"
  })), /*#__PURE__*/React.createElement("div", {
    className: "grid lg:grid-cols-[250px_1fr_280px]",
    style: {
      borderBottom: `2px solid ${t.ink}`
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "order-2 lg:order-1 py-6 lg:pr-7 lg:border-r space-y-4",
    style: {
      borderColor: t.line
    }
  }, [0, 1].map(i => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "space-y-2"
  }, /*#__PURE__*/React.createElement("div", {
    className: "skel h-5 w-full"
  }), /*#__PURE__*/React.createElement("div", {
    className: "skel h-3 w-24"
  })))), /*#__PURE__*/React.createElement("div", {
    className: "order-1 lg:order-2 py-6 lg:px-7 lg:border-r",
    style: {
      borderColor: t.line
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "skel h-11 w-full mb-2.5"
  }), /*#__PURE__*/React.createElement("div", {
    className: "skel h-11 w-4/5 mb-5"
  }), /*#__PURE__*/React.createElement("div", {
    className: "skel h-24 w-full"
  })), /*#__PURE__*/React.createElement("div", {
    className: "order-3 py-6 lg:pl-7 space-y-3"
  }, [0, 1, 2].map(i => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "skel h-4 w-full"
  })))));
}

/* ---------------- routing + app ---------------- */
function parsePath() {
  const p = typeof window !== "undefined" ? window.location.pathname || "/" : "/";
  const seg = p.split("/").filter(Boolean);
  if (seg[0] === "story" && seg[1]) return {
    view: "story",
    id: decodeURIComponent(seg[1])
  };
  if (seg[0] === "topic" && seg[1]) return {
    view: "topic",
    topic: decodeURIComponent(seg[1])
  };
  if (seg.length === 1 && ["blindspot", "topics", "sources", "about", "search", "contact", "privacy", "support", "you", "login"].includes(seg[0])) return {
    view: seg[0]
  };
  return {
    view: "home"
  };
}
// Consent gate. Nothing is tracked until the visitor accepts here; "Decline" is honoured
// for the whole session and remembered. Copy is deliberately plain about what's collected.
function ConsentBanner({
  t,
  lang,
  onChoose,
  go
}) {
  const L = lang === "hi" ? {
    text: "पक्ष यह समझने के लिए कि लोग खबरें कैसे पढ़ते हैं, गोपनीयता-सम्मानित, कुकी-रहित एनालिटिक्स इस्तेमाल करना चाहता है। कोई व्यक्तिगत पहचान नहीं, कोई विज्ञापन-ट्रैकिंग नहीं।",
    accept: "स्वीकार करें",
    decline: "मना करें",
    more: "गोपनीयता"
  } : {
    text: "Paksh uses privacy-respecting, cookieless analytics to understand how people read the news. No personal identity, no ad-tracking.",
    accept: "Accept",
    decline: "Decline",
    more: "Privacy"
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "fixed inset-x-0 bottom-16 z-50 px-4 md:bottom-4"
  }, /*#__PURE__*/React.createElement("div", {
    className: `mx-auto flex max-w-2xl flex-col gap-3 border p-4 sm:flex-row sm:items-center sm:gap-4 ${t.surface} ${t.border}`,
    style: {
      boxShadow: "0 6px 24px rgba(0,0,0,0.18)"
    }
  }, /*#__PURE__*/React.createElement("p", {
    className: `text-[12.5px] leading-[1.55] ${t.ts} ${isHi(lang)}`
  }, L.text, " ", /*#__PURE__*/React.createElement("button", {
    onClick: () => go("privacy"),
    className: `underline underline-offset-2 ${t.tf} hover:${t.tp}`
  }, L.more)), /*#__PURE__*/React.createElement("div", {
    className: "flex shrink-0 gap-2"
  }, /*#__PURE__*/React.createElement("button", {
    onClick: () => onChoose("denied"),
    className: `border px-3.5 py-1.5 text-[12.5px] font-semibold ${t.border} ${t.ts} hover:${t.tp} ${isHi(lang)}`
  }, L.decline), /*#__PURE__*/React.createElement("button", {
    onClick: () => onChoose("granted"),
    className: `px-3.5 py-1.5 text-[12.5px] font-semibold ${t.cta} ${t.ctaT} ${isHi(lang)}`
  }, L.accept))));
}
/* ---------------- SIGN IN ---------------- */
function LoginPage({
  t,
  lang,
  go
}) {
  const A = useAuth();
  const HI = lang === "hi";
  const tt = (e, h) => HI ? h : e;
  const [email, setEmail] = useState("");
  const [agree, setAgree] = useState(false);
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => {
    if (A.isLoggedIn()) go("you");
  }, [A.isLoggedIn()]);
  const emailOk = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim());
  const sendLink = async e => {
    e.preventDefault();
    if (!agree || !emailOk || busy) return;
    setErr("");
    setBusy(true);
    try {
      await Auth.sendMagicLink(email.trim());
      setSent(true);
    } catch (ex) {
      setErr(ex.message || tt("Something went wrong.", "कुछ गड़बड़ हुई।"));
    }
    setBusy(false);
  };
  const line = `border ${t.border} ${t.surface}`;
  if (sent) return /*#__PURE__*/React.createElement(PageWrap, null, /*#__PURE__*/React.createElement("div", {
    className: "mx-auto max-w-md py-16 text-center"
  }, /*#__PURE__*/React.createElement("div", {
    className: `mx-auto mb-5 grid h-12 w-12 place-items-center rounded-full ${t.chip}`
  }, /*#__PURE__*/React.createElement(Check, {
    size: 22
  })), /*#__PURE__*/React.createElement("h1", {
    className: `headline text-[26px] ${t.tp} ${readCls(lang)}`
  }, tt("Check your inbox", "अपना इनबॉक्स देखें")), /*#__PURE__*/React.createElement("p", {
    className: `mt-3 text-[14px] leading-relaxed ${t.ts} ${isHi(lang)}`
  }, tt("We emailed a one-tap sign-in link to", "हमने एक-टैप साइन-इन लिंक भेजा है"), " ", /*#__PURE__*/React.createElement("span", {
    className: "font-semibold"
  }, email.trim()), ". ", tt("Open it on any device to sign in.", "किसी भी डिवाइस पर इसे खोलकर साइन इन करें।")), /*#__PURE__*/React.createElement("button", {
    onClick: () => {
      setSent(false);
    },
    className: `mt-6 eyebrow ${t.tf} hover:${t.tp}`,
    style: {
      letterSpacing: HI ? 0 : ".1em"
    }
  }, tt("Use a different email", "दूसरा ईमेल इस्तेमाल करें"))));
  return /*#__PURE__*/React.createElement(PageWrap, null, /*#__PURE__*/React.createElement("div", {
    className: "mx-auto max-w-md py-10"
  }, /*#__PURE__*/React.createElement("h1", {
    className: `headline text-[30px] sm:text-[34px] ${t.tp} ${readCls(lang)}`,
    style: {
      letterSpacing: HI ? 0 : "-0.018em"
    }
  }, tt("Sign in to Paksh", "पक्ष में साइन इन करें")), /*#__PURE__*/React.createElement("p", {
    className: `mt-2.5 text-[14px] leading-relaxed ${t.ts} ${isHi(lang)}`
  }, tt("Save stories and follow the topics you care about, then get the same feed on every device. Free, and no password.", "खबरें सहेजें और अपने पसंद के विषय फ़ॉलो करें, फिर हर डिवाइस पर वही फ़ीड पाएँ। मुफ़्त, और कोई पासवर्ड नहीं।")), /*#__PURE__*/React.createElement("form", {
    onSubmit: sendLink,
    className: "mt-7 space-y-3"
  }, /*#__PURE__*/React.createElement("input", {
    type: "email",
    value: email,
    onChange: e => setEmail(e.target.value),
    placeholder: tt("you@email.com", "you@email.com"),
    autoComplete: "email",
    className: `w-full rounded-lg px-4 py-3 text-[15px] outline-none ${line} ${t.tp}`,
    style: {
      colorScheme: "light"
    }
  }), /*#__PURE__*/React.createElement("button", {
    type: "submit",
    disabled: !agree || !emailOk || busy,
    className: `w-full rounded-lg px-4 py-3 text-[14px] font-semibold ${t.cta} ${t.ctaT} ${!agree || !emailOk || busy ? "opacity-40" : ""} ${isHi(lang)}`
  }, busy ? tt("Sending…", "भेजा जा रहा…") : tt("Email me a sign-in link", "मुझे साइन-इन लिंक ईमेल करें"))), GOOGLE_AUTH && /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "my-4 flex items-center gap-3"
  }, /*#__PURE__*/React.createElement("div", {
    className: "h-px flex-1",
    style: {
      background: t.line
    }
  }), /*#__PURE__*/React.createElement("span", {
    className: `mono text-[10px] uppercase ${t.tf}`
  }, tt("or", "या")), /*#__PURE__*/React.createElement("div", {
    className: "h-px flex-1",
    style: {
      background: t.line
    }
  })), /*#__PURE__*/React.createElement("button", {
    onClick: () => {
      if (agree) Auth.google();
    },
    disabled: !agree,
    className: `flex w-full items-center justify-center gap-2.5 rounded-lg px-4 py-3 text-[14px] font-semibold ${line} ${t.tp} ${!agree ? "opacity-40" : `hover:${t.soft}`} ${isHi(lang)}`
  }, /*#__PURE__*/React.createElement("svg", {
    width: "17",
    height: "17",
    viewBox: "0 0 24 24"
  }, /*#__PURE__*/React.createElement("path", {
    fill: "#4285F4",
    d: "M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1Z"
  }), /*#__PURE__*/React.createElement("path", {
    fill: "#34A853",
    d: "M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23Z"
  }), /*#__PURE__*/React.createElement("path", {
    fill: "#FBBC05",
    d: "M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84Z"
  }), /*#__PURE__*/React.createElement("path", {
    fill: "#EA4335",
    d: "M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84C6.71 7.3 9.14 5.38 12 5.38Z"
  })), tt("Continue with Google", "Google से जारी रखें"))), err && /*#__PURE__*/React.createElement("p", {
    className: `mt-4 text-[13px] ${t.blind} ${isHi(lang)}`
  }, err), /*#__PURE__*/React.createElement("label", {
    className: "mt-6 flex cursor-pointer items-start gap-2.5"
  }, /*#__PURE__*/React.createElement("input", {
    type: "checkbox",
    checked: agree,
    onChange: e => setAgree(e.target.checked),
    className: "mt-0.5 h-4 w-4 shrink-0"
  }), /*#__PURE__*/React.createElement("span", {
    className: `text-[12px] leading-relaxed ${t.tf} ${isHi(lang)}`
  }, tt("I'm signing up for myself and agree to the ", "मैं स्वयं के लिए साइन अप कर रहा/रही हूँ और सहमत हूँ "), /*#__PURE__*/React.createElement("button", {
    type: "button",
    onClick: () => go("privacy"),
    className: `underline ${t.ts} hover:${t.tp}`
  }, tt("Privacy Policy", "गोपनीयता नीति")), tt(". Paksh isn't directed at children under 18; a minor should have a parent's permission.", ". पक्ष 18 वर्ष से कम बच्चों के लिए नहीं है; नाबालिग को अभिभावक की अनुमति लेनी चाहिए।")))));
}

/* ---------------- YOUR PAKSH (private, on-device) ---------------- */
function YouPage({
  cards,
  topics,
  t,
  lang,
  open,
  go
}) {
  const P = usePaksh();
  const A = useAuth();
  const saved = P.saved(),
    follow = P.follow(),
    hist = P.hist();
  const HI = lang === "hi";
  const tt = (en, hi) => HI ? hi : en;
  const authed = authEnabled() && A.isLoggedIn();
  const email = (A.user() || {}).email || "";
  const byId = useMemo(() => {
    const m = {};
    (cards || []).forEach(c => {
      m[String(c.id)] = c;
    });
    return m;
  }, [cards]);

  // Reading balance: tally opens by the dominant lean of each opened story.
  const tally = {
    left: 0,
    center: 0,
    right: 0
  };
  hist.forEach(h => {
    if (tally[h.side] != null) tally[h.side]++;
  });
  const totalRead = tally.left + tally.center + tally.right;
  const pct = biasPct(tally);
  // the side you open LEAST (prefer flagging Left/Right over Centre on a tie).
  const underSide = ["left", "right", "center"].slice().sort((a, b) => tally[a] - tally[b])[0];
  const underCards = (cards || []).filter(c => domSide(c.bias) === underSide).slice(0, 4);
  const savedCards = saved.map(id => byId[String(id)]).filter(Boolean);
  const forYou = follow.length ? (cards || []).filter(c => follow.indexOf(c.topic) >= 0).slice(0, 12) : [];
  const suggest = (topics || []).filter(tp => follow.indexOf(tp) < 0).slice(0, 8);
  const Row = ({
    s,
    last
  }) => /*#__PURE__*/React.createElement("div", {
    className: `flex items-start gap-3 py-4 ${last ? "" : "border-b"} ${t.border}`
  }, /*#__PURE__*/React.createElement("a", {
    href: "/story/" + encodeURIComponent(s.id),
    onClick: e => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      open(s.id);
    },
    className: "block no-underline group min-w-0 flex-1 cursor-pointer"
  }, /*#__PURE__*/React.createElement("h3", {
    className: `headline text-[18px] sm:text-[19px] ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`,
    style: {
      lineHeight: HI ? 1.34 : 1.24,
      textWrap: "pretty"
    }
  }, s.headline), /*#__PURE__*/React.createElement("div", {
    className: "mt-2 max-w-[280px]"
  }, /*#__PURE__*/React.createElement(BiasSegments, {
    bias: s.bias,
    t: t,
    h: 10,
    lang: lang
  })), /*#__PURE__*/React.createElement("div", {
    className: `mt-1.5 mono text-[10.5px] ${t.tf}`
  }, s.counts.left || 0, " \xB7 ", s.counts.center || 0, " \xB7 ", s.counts.right || 0, " \xB7 n = ", (s.counts.left || 0) + (s.counts.center || 0) + (s.counts.right || 0), timeAgo(s.created_at, lang) ? " · " + timeAgo(s.created_at, lang) : "")), /*#__PURE__*/React.createElement("div", {
    className: "pt-1"
  }, /*#__PURE__*/React.createElement(SaveButton, {
    id: s.id,
    t: t,
    lang: lang,
    compact: true
  })));
  const List = ({
    items
  }) => /*#__PURE__*/React.createElement("div", {
    className: "mt-3"
  }, items.map((s, i) => /*#__PURE__*/React.createElement(Row, {
    key: s.id,
    s: s,
    last: i === items.length - 1
  })));
  const Empty = ({
    children
  }) => /*#__PURE__*/React.createElement("div", {
    className: `mt-4 border ${t.border} ${t.soft} p-5 text-[13.5px] ${t.ts} ${isHi(lang)}`
  }, children);
  const Head = ({
    title,
    sub
  }) => /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("h2", {
    className: `headline text-[22px] sm:text-[26px] ${t.tp} ${readCls(lang)}`
  }, title), sub && /*#__PURE__*/React.createElement("p", {
    className: `mt-1.5 text-[13px] ${t.tf} ${isHi(lang)}`
  }, sub));
  return /*#__PURE__*/React.createElement(PageWrap, null, /*#__PURE__*/React.createElement("div", {
    className: "flex items-start justify-between gap-4"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h1", {
    className: `headline text-[30px] sm:text-[40px] ${t.tp} ${readCls(lang)}`,
    style: {
      letterSpacing: HI ? 0 : "-0.018em"
    }
  }, tt("Your Paksh", "आपका पक्ष")), /*#__PURE__*/React.createElement("p", {
    className: `mt-2 text-[13px] ${t.tf} ${isHi(lang)}`
  }, authed ? tt("Synced to your account, on every device you sign in on.", "आपके खाते से जुड़ा, हर डिवाइस पर जहाँ आप साइन इन करें।") : authEnabled() ? tt("Saved on this device. Sign in to sync everywhere.", "इस डिवाइस पर सहेजा। हर जगह सिंक के लिए साइन इन करें।") : tt("Private to this browser. No account, nothing leaves your device.", "सिर्फ़ इस ब्राउज़र में। कोई खाता नहीं, कुछ भी आपके डिवाइस से बाहर नहीं जाता।"))), saved.length || follow.length || hist.length ? /*#__PURE__*/React.createElement("button", {
    onClick: () => {
      if (window.confirm(tt("Clear your saved stories, followed topics and reading history on this device?", "इस डिवाइस पर सहेजी खबरें, फ़ॉलो किए विषय और पढ़ने का इतिहास साफ़ करें?"))) P.clearAll();
    },
    className: `inline-flex shrink-0 items-center gap-1.5 eyebrow ${t.tf} hover:${t.tp}`,
    style: {
      letterSpacing: HI ? 0 : ".1em"
    }
  }, /*#__PURE__*/React.createElement(Trash, {
    size: 13
  }), " ", tt("Clear", "साफ़ करें")) : null), authEnabled() && (authed ? /*#__PURE__*/React.createElement("div", {
    className: `mt-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border ${t.border} ${t.soft} px-4 py-3`
  }, /*#__PURE__*/React.createElement("div", {
    className: `text-[13px] ${t.ts} ${isHi(lang)}`
  }, tt("Signed in as", "साइन इन:"), " ", /*#__PURE__*/React.createElement("span", {
    className: "font-semibold"
  }, email)), /*#__PURE__*/React.createElement("div", {
    className: "flex items-center gap-5"
  }, /*#__PURE__*/React.createElement("button", {
    onClick: () => Auth.signOut(),
    className: `eyebrow ${t.tf} hover:${t.tp}`,
    style: {
      letterSpacing: HI ? 0 : ".1em"
    }
  }, tt("Sign out", "साइन आउट")), /*#__PURE__*/React.createElement("button", {
    onClick: () => {
      if (window.confirm(tt("Delete your synced account data (topics, saved stories, reading history)? This can't be undone.", "आपका सिंक किया डेटा (विषय, सहेजी खबरें, इतिहास) हटाएँ? यह वापस नहीं होगा।"))) Auth.deleteData();
    },
    className: `eyebrow ${t.blind} hover:opacity-80`,
    style: {
      letterSpacing: HI ? 0 : ".1em"
    }
  }, tt("Delete data", "डेटा हटाएँ")))) : /*#__PURE__*/React.createElement("div", {
    className: `mt-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border ${t.border} ${t.soft} px-4 py-3`
  }, /*#__PURE__*/React.createElement("div", {
    className: `text-[13px] ${t.ts} ${isHi(lang)}`
  }, tt("Sign in to sync your feed across phone, laptop and tablet.", "फ़ोन, लैपटॉप और टैबलेट में अपनी फ़ीड सिंक करने के लिए साइन इन करें।")), /*#__PURE__*/React.createElement("button", {
    onClick: () => go("login"),
    className: `shrink-0 rounded-full px-4 py-1.5 text-[12.5px] font-semibold ${t.cta} ${t.ctaT} ${isHi(lang)}`
  }, tt("Sign in", "साइन इन")))), /*#__PURE__*/React.createElement("section", {
    className: "mt-9"
  }, /*#__PURE__*/React.createElement(Head, {
    title: tt("Your topics", "आपके विषय"),
    sub: tt("Tap the sections you want to follow, they shape your For You feed.", "जिन खंडों को फ़ॉलो करना है उन्हें चुनें, ये आपकी 'आपके लिए' फ़ीड बनाते हैं।")
  }), /*#__PURE__*/React.createElement("div", {
    className: "mt-3 flex flex-wrap gap-2"
  }, (topics || []).map(tp => {
    const on = follow.indexOf(tp) >= 0;
    return /*#__PURE__*/React.createElement("button", {
      key: tp,
      onClick: () => P.toggleFollow(tp),
      "aria-pressed": on,
      className: `inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[12.5px] font-semibold ${on ? `${t.cta} ${t.ctaT} border border-transparent` : `border ${t.border} ${t.ts} hover:${t.tp}`} ${HI ? "deva" : ""}`
    }, on && /*#__PURE__*/React.createElement(Check, {
      size: 12
    }), HI ? TOPIC_HI[tp] || tp : tp);
  }))), /*#__PURE__*/React.createElement("section", {
    className: "mt-9"
  }, /*#__PURE__*/React.createElement(Head, {
    title: tt("Your reading balance", "आपका पढ़ने का संतुलन"),
    sub: tt("Which way the stories you open tend to lean, your own spread, not a score. Private to you.", "आप जो खबरें खोलते हैं वे किस ओर झुकी होती हैं, आपका अपना फैलाव, कोई स्कोर नहीं। सिर्फ़ आपके लिए।")
  }), totalRead < 3 ? /*#__PURE__*/React.createElement(Empty, null, tt("Open a few stories and your reading balance appears here.", "कुछ खबरें खोलें और आपका पढ़ने का संतुलन यहाँ दिखेगा।")) : /*#__PURE__*/React.createElement("div", {
    className: "mt-4"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mb-2 flex items-baseline justify-between"
  }, /*#__PURE__*/React.createElement("div", {
    className: `flex gap-5 text-[11px] font-medium uppercase tracking-[0.12em] ${t.tp} ${HI ? "deva" : ""}`
  }, ["left", "center", "right"].map(k => tally[k] > 0 ? /*#__PURE__*/React.createElement("span", {
    key: k
  }, lbl(k, lang), " ", /*#__PURE__*/React.createElement("span", {
    className: "mono",
    style: {
      letterSpacing: 0
    }
  }, pct[k], "%")) : null)), /*#__PURE__*/React.createElement("span", {
    className: `mono text-[11px] ${t.tf}`
  }, "n = ", totalRead)), /*#__PURE__*/React.createElement(BiasSegments, {
    bias: pct,
    t: t,
    h: 22,
    lang: lang
  }), underCards.length > 0 && /*#__PURE__*/React.createElement("div", {
    className: "mt-6"
  }, /*#__PURE__*/React.createElement("div", {
    className: `eyebrow ${t.blind} ${HI ? "deva" : ""}`,
    style: {
      letterSpacing: HI ? 0 : ".14em"
    }
  }, tt("Widen your view", "अपना नज़रिया बढ़ाएँ")), /*#__PURE__*/React.createElement("p", {
    className: `mt-1 text-[13px] ${t.tf} ${isHi(lang)}`
  }, tt("Recent stories led by " + lbl(underSide, "en") + "-leaning outlets, the side you open least.", BIAS[underSide].hi + "-झुकाव आउटलेट्स की हाल की खबरें, जिन्हें आप सबसे कम खोलते हैं।")), /*#__PURE__*/React.createElement(List, {
    items: underCards
  })))), /*#__PURE__*/React.createElement("section", {
    className: "mt-11"
  }, /*#__PURE__*/React.createElement(Head, {
    title: tt("Saved", "सहेजी गई")
  }), savedCards.length ? /*#__PURE__*/React.createElement(List, {
    items: savedCards
  }) : /*#__PURE__*/React.createElement(Empty, null, tt("Tap “Save” on any story to keep it here for later.", "किसी भी खबर पर “सहेजें” दबाएँ ताकि वह यहाँ बाद के लिए रहे।"))), /*#__PURE__*/React.createElement("section", {
    className: "mt-11"
  }, /*#__PURE__*/React.createElement(Head, {
    title: tt("For you", "आपके लिए"),
    sub: tt("Latest in the topics you follow.", "आपके फ़ॉलो किए विषयों की ताज़ा खबरें।")
  }), follow.length > 0 && /*#__PURE__*/React.createElement("div", {
    className: "mt-3 flex flex-wrap gap-2"
  }, follow.map(tp => /*#__PURE__*/React.createElement("button", {
    key: tp,
    onClick: () => P.toggleFollow(tp),
    title: tt("Unfollow", "अनफ़ॉलो"),
    className: `inline-flex items-center gap-1.5 rounded-full ${t.cta} ${t.ctaT} px-3 py-1 text-[12px] font-semibold ${HI ? "deva" : ""}`
  }, HI ? TOPIC_HI[tp] || tp : tp, " ", /*#__PURE__*/React.createElement(X, {
    size: 11
  })))), forYou.length ? /*#__PURE__*/React.createElement(List, {
    items: forYou
  }) : /*#__PURE__*/React.createElement(Empty, null, /*#__PURE__*/React.createElement("p", {
    className: isHi(lang)
  }, tt("Follow a topic to build your feed:", "अपनी फ़ीड बनाने के लिए कोई विषय फ़ॉलो करें:")), /*#__PURE__*/React.createElement("div", {
    className: "mt-3 flex flex-wrap gap-2"
  }, suggest.map(tp => /*#__PURE__*/React.createElement("button", {
    key: tp,
    onClick: () => P.toggleFollow(tp),
    className: `inline-flex items-center gap-1.5 rounded-full border ${t.border} ${t.ts} hover:${t.tp} px-3 py-1 text-[12px] font-semibold ${HI ? "deva" : ""}`
  }, /*#__PURE__*/React.createElement("span", {
    "aria-hidden": "true"
  }, "+"), " ", HI ? TOPIC_HI[tp] || tp : tp))))));
}
function PakshApp() {
  const [route, setRoute] = useState(parsePath());
  const [lang, setLang] = useState("en");
  // Honour a remembered choice first, else the OS preference (prefers-color-scheme),
  // else light. Previously it always started light, ignoring a device set to dark.
  const [dark, setDark] = useState(() => {
    try {
      const s = localStorage.getItem("paksh-theme");
      if (s === "dark") return true;
      if (s === "light") return false;
      return !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
    } catch (e) {
      return false;
    }
  });
  const [query, setQuery] = useState("");
  const [data, setData] = useState({
    events: [],
    blindspots: [],
    gaps: {
      left: [],
      right: [],
      agg: {}
    },
    topics: [],
    sources: [],
    summary: {}
  });
  const [detail, setDetail] = useState({});
  const [archive, setArchive] = useState(null); // older events, lazy-loaded for search/topic browsing
  const [ready, setReady] = useState(false);
  const [consent, setConsent] = useState(consentState); // "" undecided | "granted" | "denied"

  useEffect(() => {
    loadAll().then(d => {
      setData(d);
      setReady(true);
    });
  }, []);
  // Accounts: process a magic-link/Google redirect landing in the URL hash, then, if a
  // session exists (fresh or restored), merge cloud <-> on-device prefs. No-op if OFF.
  useEffect(() => {
    if (!authEnabled()) return;
    Auth.handleRedirect().then(() => {
      if (Auth.isLoggedIn()) PSync.onLogin();
    });
  }, []);
  // Load cookieless Vercel Web Analytics ONLY after the visitor accepts. Denied/undecided
  // visitors get zero analytics script and zero beacons.
  useEffect(() => {
    if (consent === "granted") loadVercelAnalytics();
  }, [consent]);
  useEffect(() => {
    const on = () => setRoute(parsePath());
    window.addEventListener("popstate", on);
    return () => window.removeEventListener("popstate", on);
  }, []);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    document.body.style.backgroundColor = dark ? "#1A1917" : "#EAE6DB";
    try {
      localStorage.setItem("paksh-theme", dark ? "dark" : "light");
    } catch (e) {}
  }, [dark]);
  useEffect(() => {
    window.scrollTo(0, 0);
    if (route.view === "story" && route.id && !detail[route.id]) {
      apiGet("events/" + route.id).then(full => setDetail(d => ({
        ...d,
        [route.id]: full
      }))).catch(() => {
        const f = (data.events || []).concat(data.blindspots || []).find(x => String(x.id) === String(route.id));
        if (f) setDetail(d => ({
          ...d,
          [route.id]: f
        }));
      });
    }
  }, [route, data]);
  // events.json is capped to recent stories for a light first paint; the older tail lives in
  // events-archive.json and is fetched ONCE, the first time the user browses beyond the feed
  // (Search / a Topic / Sections). Home + story pages never need it. Set to [] up front so the
  // fetch fires only once even if it fails (then search/topic just cover recent stories).
  useEffect(() => {
    if (archive !== null) return;
    if (!["search", "topic", "topics", "you"].includes(route.view)) return;
    setArchive([]);
    apiGet("events-archive").then(a => setArchive(a.events || [])).catch(() => {});
  }, [route.view, archive]);
  const t = dark ? TOKENS.dark : TOKENS.light;
  const nav = path => {
    if (window.location.pathname !== path) {
      window.history.pushState(null, "", path);
    }
    setRoute(parsePath());
  };
  const go = v => nav(v === "home" ? "/" : "/" + v);
  const open = id => {
    track("story_open", {
      device: deviceClass()
    });
    // record the open for the private on-device reading balance (which side the
    // story's coverage leaned toward). Never networked; localStorage only.
    try {
      const ev = (allEvents || []).find(e => String(e.id) === String(id)) || (data.blindspots || []).find(e => String(e.id) === String(id));
      if (ev) {
        const c = ev.lean_counts || {};
        const side = domSide({
          left: c.left || 0,
          center: c.center || 0,
          right: c.right || 0
        });
        PStore.recordOpen({
          id,
          side,
          topic: ev.topic || "",
          t: Date.now()
        });
      }
    } catch (e) {}
    nav("/story/" + encodeURIComponent(id));
  };
  const goTopic = tp => nav("/topic/" + encodeURIComponent(tp));
  const chooseLang = l => {
    track("lang_switch", {
      to: l
    });
    setLang(l);
  }; // wrap so the toggle is measured

  // Combine recent (always loaded) with the lazy archive once it arrives, so Search / Topic /
  // Sections cover the FULL catalogue while the home feed's first paint stayed small. The two
  // lists are disjoint (recent = events[:N], archive = events[N:]), so there are no duplicates.
  const allEvents = archive && archive.length ? data.events.concat(archive) : data.events;
  const baseCards = allEvents.map(e => toCard(e, lang)).filter(c => c.srclang === lang);
  const baseOne = data.blindspots.map(e => toCard(e, lang)).filter(c => c.srclang === lang);
  const gapL = (data.gaps.left || []).map(e => toCard(e, lang)).filter(c => c.srclang === lang);
  const gapR = (data.gaps.right || []).map(e => toCard(e, lang)).filter(c => c.srclang === lang);
  const gapAgg = data.gaps.agg || {};
  // --- India-first home ranking ------------------------------------------
  // Top Stories is strictly India-centric. Foreign stories (region "World", set
  // per-event by the pipeline) and Sports live in their own Sections, NOT on the
  // home feed. To allow world news back on the home, drop the region check below.
  const HOME_EXCLUDE_TOPICS = ["Sports"];
  const [regionFilter, setRegionFilter] = useState("National");
  const ageHours = c => {
    const tt = _ts(c.created_at);
    return isNaN(tt) ? 9999 : Math.max(0, (Date.now() - tt) / 3600000);
  };
  // Home feed leads by the EXPORT-TIME importance score (see export_static._importance):
  // distinct outlets across left/centre/right, decayed by recency. It is computed in
  // the pipeline (not here), carries no topic weighting, and is a plain field on each
  // event. The previous in-browser rank() with per-topic CIVIC weights was removed so
  // ordering is arithmetic and explainable. Ties fall back to newest-first.
  // FRONT-PAGE ordering: recency-gated feed_rank (8h half-life, computed in
  // export_static._feed_rank) so the feed leads with what's current. Falls back to
  // importance if an older export hasn't written feed_rank yet. Sections/search/topic
  // stay newest-first (below); the importance score used elsewhere is unchanged.
  const rank = c => typeof c.feed_rank === "number" ? c.feed_rank : 0;
  const homeFilter = c => {
    if (HOME_EXCLUDE_TOPICS.includes(c.topic)) return false;
    const isWorld = (c.region || "India") === "World";
    return regionFilter === "International" ? isWorld : !isWorld;
  };
  const homeCards = baseCards.filter(homeFilter).sort((a, b) => rank(b) - rank(a) || ageHours(a) - ageHours(b));
  const homeOne = baseOne.filter(homeFilter).sort((a, b) => rank(b) - rank(a) || ageHours(a) - ageHours(b));
  // sections / search / topic pages: newest-first so new articles always show there too
  baseCards.sort((a, b) => ageHours(a) - ageHours(b));
  baseOne.sort((a, b) => ageHours(a) - ageHours(b));
  const countsByTopic = {};
  baseCards.forEach(c => {
    const k = c.topic || "Society";
    countsByTopic[k] = (countsByTopic[k] || 0) + 1;
  });
  const topicsOrdered = Object.keys(countsByTopic).sort((a, b) => countsByTopic[b] - countsByTopic[a]);
  const lastTs = (data.events || []).reduce((mx, e) => {
    const ts = Date.parse(e.published_at || e.created_at || "");
    return isNaN(ts) ? mx : Math.max(mx, ts);
  }, 0);
  const stats = {
    stories: homeCards.length,
    outlets: (data.sources || []).length,
    gaps: gapAgg.total != null ? gapAgg.total : gapL.length + gapR.length,
    updated: lastTs ? new Date(lastTs).toISOString() : "",
    regionFilter,
    setRegionFilter
  };
  // Roster size per lean (distinct outlets tracked), for the Coverage-Gaps rate columns.
  const rosterByLean = {
    left: 0,
    center: 0,
    right: 0
  };
  (data.sources || []).forEach(s => {
    if (rosterByLean[s.lean] != null) rosterByLean[s.lean]++;
  });
  // Token-AND search: every word in the query must appear SOMEWHERE in the card's
  // headline, summary snippet or topic. The old code required the whole query as one
  // contiguous substring of the headline, so "supreme court neet" matched nothing even
  // when all three words were present. Matches the localised (EN/HI) fields on the card.
  const qTokens = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const _hay = c => `${c.headline || ""} ${c.lead || ""} ${(c.summary || []).join(" ")} ${c.topic || ""}`.toLowerCase();
  const results = qTokens.length ? baseCards.filter(c => {
    const h = _hay(c);
    return qTokens.every(tok => h.includes(tok));
  }) : [];
  const story = route.view === "story" ? detail[route.id] ? toDetail(detail[route.id], lang) : null : null;
  // Same-topic stories to keep a reader moving instead of dead-ending at the article.
  const related = story ? baseCards.filter(c => c.topic === story.topic && String(c.id) !== String(story.id)).slice(0, 6) : [];
  const headerView = route.view === "story" ? "" : route.view;
  return /*#__PURE__*/React.createElement("div", {
    className: `min-h-screen font-sans ${t.bg} ${t.tp}`
  }, /*#__PURE__*/React.createElement("a", {
    href: "#main",
    className: "sr-only-focusable"
  }, lang === "hi" ? "मुख्य सामग्री पर जाएँ" : "Skip to content"), /*#__PURE__*/React.createElement(Header, {
    t: t,
    lang: lang,
    setLang: chooseLang,
    dark: dark,
    setDark: setDark,
    go: go,
    view: headerView
  }), /*#__PURE__*/React.createElement("main", {
    id: "main",
    className: "pb-24 md:pb-10"
  }, !ready ? /*#__PURE__*/React.createElement(FeedSkeleton, {
    t: t
  }) : route.view === "story" ? story ? /*#__PURE__*/React.createElement(StoryPage, {
    story: story,
    t: t,
    lang: lang,
    go: go,
    openTopic: goTopic,
    related: related,
    open: open
  }) : /*#__PURE__*/React.createElement(FeedSkeleton, {
    t: t
  }) : route.view === "blindspot" ? /*#__PURE__*/React.createElement(BlindspotPage, {
    left: gapL,
    right: gapR,
    roster: rosterByLean,
    agg: gapAgg,
    stats: stats,
    t: t,
    lang: lang,
    open: open,
    go: go
  }) : route.view === "topics" ? /*#__PURE__*/React.createElement(TopicsHub, {
    topics: topicsOrdered,
    counts: countsByTopic,
    t: t,
    lang: lang,
    goTopic: goTopic
  }) : route.view === "topic" ? /*#__PURE__*/React.createElement(TopicPage, {
    topic: route.topic,
    items: baseCards.filter(c => c.topic === route.topic),
    t: t,
    lang: lang,
    open: open,
    go: go
  }) : route.view === "sources" ? /*#__PURE__*/React.createElement(SourcesPage, {
    t: t,
    lang: lang,
    sources: data.sources
  }) : route.view === "about" ? /*#__PURE__*/React.createElement(AboutPage, {
    t: t,
    lang: lang,
    agg: gapAgg
  }) : route.view === "contact" ? /*#__PURE__*/React.createElement(ContactPage, {
    t: t,
    lang: lang
  }) : route.view === "privacy" ? /*#__PURE__*/React.createElement(PrivacyPage, {
    t: t,
    lang: lang
  }) : route.view === "support" ? /*#__PURE__*/React.createElement(SupportPage, {
    t: t,
    lang: lang,
    go: go
  }) : route.view === "you" ? /*#__PURE__*/React.createElement(YouPage, {
    cards: baseCards,
    topics: topicsOrdered,
    t: t,
    lang: lang,
    open: open,
    go: go
  }) : route.view === "login" ? /*#__PURE__*/React.createElement(LoginPage, {
    t: t,
    lang: lang,
    go: go
  }) : route.view === "search" ? /*#__PURE__*/React.createElement(SearchPage, {
    t: t,
    lang: lang,
    query: query,
    setQuery: setQuery,
    results: results,
    open: open
  }) : !homeCards.length ? /*#__PURE__*/React.createElement(PageWrap, null, /*#__PURE__*/React.createElement("div", {
    className: `py-28 text-center ${t.tf} ${isHi(lang)}`
  }, STR[lang].noStories)) : /*#__PURE__*/React.createElement(HomeView, {
    cards: homeCards,
    gapLeft: gapL,
    gapRight: gapR,
    topics: topicsOrdered,
    counts: countsByTopic,
    stats: stats,
    t: t,
    lang: lang,
    open: open,
    goTopic: goTopic,
    go: go
  })), route.view !== "story" && /*#__PURE__*/React.createElement(Footer, {
    t: t,
    lang: lang,
    go: go
  }), /*#__PURE__*/React.createElement(BottomNav, {
    t: t,
    lang: lang,
    view: headerView,
    go: go
  }), consent === "" && /*#__PURE__*/React.createElement(ConsentBanner, {
    t: t,
    lang: lang,
    go: go,
    onChoose: v => {
      try {
        localStorage.setItem("paksh-consent", v);
      } catch (e) {}
      setConsent(v);
    }
  }));
}
ReactDOM.createRoot(document.getElementById("root")).render( /*#__PURE__*/React.createElement(PakshApp, null));