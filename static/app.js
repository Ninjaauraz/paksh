/* ============================================================
   Paksh frontend — wired to the live FastAPI backend.
   Renders the whole UI in JS so the EN/हिं toggle re-localizes
   everything (chrome + content) without a page reload.
   ============================================================ */

const STR = {
  en: {
    nav_sources:"Sources", nav_method:"Method", langEN:"English", langHI:"Hindi",
    filterLean:"Lean", filterLang:"Language", ownership:"Ownership", whyRated:"Why this rating",
    signals:"Signals", confidence:"confidence", contested:"Contested", provisional:"Provisional",
    srcTitle:"Source ratings", srcIntro:"Every outlet Paksh tracks, how it's rated, and why.",
    srcDisclaimer:"All ratings are provisional — a documented starting point reviewed against our rubric, not a final verdict. Lean describes the publication, not any single article, and is open to appeal.",
    suggestFix:"Suggest a correction", methodTitle:"How Paksh works",
    m_doesH:"What Paksh does", m_does:"Paksh groups coverage of the same story from outlets across the spectrum, shows a neutral summary, and reveals how each side framed it — so you can see the whole picture and what your usual sources leave out.",
    m_ruleH:"The golden rule", m_rule:"A lean label belongs to the publication, not to any single article — and never to the AI. Paksh editors assign each outlet a lean using a fixed rubric. The AI only writes neutral summaries and notes how outlets framed a story; it never decides anyone's politics. A story's bias bar is simple arithmetic: we count how many covering outlets fall on each side.",
    m_rateH:"How we rate a publication", m_rateLede:"We rate each publication on six signals, each scored from −2 to +2 and combined into one score from −10 (left) to +10 (right):", m_rateFoot:"Scores near zero are Centre; the further from zero, the stronger the lean. The full rubric lives in the open in our methodology file.",
    m_axisH:"What “Left” and “Right” mean in India", m_axis:"In India, Left and Right aren't only about economics. Paksh blends a social-and-ideological axis (secular ↔ Hindutva) with an institutional one (critical of ↔ aligned with the incumbent), and tracks economic stance separately. “Left” and “Right” are descriptive, not insults — and the same scrutiny is applied across the spectrum.",
    m_provH:"Confidence, contested & provisional", m_prov:"Every rating today is provisional: a documented starting point based on ownership, self-described stance and well-established reputation, reviewed against the rubric — not a final verdict. Each shows a confidence level, and some are flagged Contested where lean is genuinely debated or ownership recently changed.",
    m_readH:"How to read a Paksh story", m_appealH:"Corrections & appeals",
    m_partiesH:"Where India's parties roughly sit", m_parties:"These labels describe ideas, not teams — and they're rough, because parties shift over time and many regional parties don't fit neatly on one line. As a common-usage guide: the Left includes communist and socialist parties such as CPI(M) and CPI, and is associated with secular, pro-welfare, labour-first positions; the Right — most prominently the BJP — is associated with Hindutva-influenced cultural nationalism and a more market-friendly economic stance; the Centre spans the middle, where the Congress is often described as centre-left and many regional parties mix positions by issue. Remember: Paksh rates news outlets, not parties — an outlet's lean is about how it covers the news, not who it votes for.",
    m_appeal:"Think a rating is wrong? Tell us the outlet, the rating you dispute, and a few specific examples — headlines or articles — and we'll re-review it against the rubric. Ratings are meant to be challenged.",
    m_sourcesLink:"See every outlet and its rating on the",
    word:"Paksh", tag_pre:"Compare how India's media covers each story —", tag_b:"every side, side by side.",
    nav_top:"Top Stories", nav_os:"One-Sided", search:"Search stories",
    topStories:"Top Stories", osStories:"One-Sided Stories",
    osSub:"Stories mostly one side of the spectrum is covering — so the other side rarely sees them.",
    osShort:"One-Sided", sideBySide:"Side by Side", covBreak:"Coverage Breakdown",
    whereLean:"Where the sources lean", aiSummary:"Paksh neutral summary",
    aiNote:"Written by AI from the outlets' own coverage. Lean labels describe the publishers and are set by Paksh editors, not the AI; the counts come from the sources, not the summary.",
    myMix:"My Reading Mix", myMixSub:"How balanced is your own reading?",
    myMixNote:"Connect your reading to see how it spreads across the spectrum.", myMixSoon:"Coming soon",
    myMixCta:"See how it works", sources:"sources", source:"source",
    most:"Most coverage", even:"Fairly even coverage", onlyOn:"Only covered on the", notOn:"Not covered on the",
    sideWord:"side", divergence:"How coverage differs", omissions:"What gets left out",
    back:"Back", all:"All", demo:"Demo",
    noStories:"No stories to show right now. Please check back soon.",
    noOS:"No one-sided stories in the current set.",
    left:"Left", center:"Centre", right:"Right",
    footAbout:"About & method",
    footFine:"Paksh compares how outlets cover the same story. Lean labels describe publishers, set by a transparent rubric — they are provisional and open to appeal. Paksh is an independent project and is not affiliated with any outlet shown."
  },
  hi: {
    nav_sources:"स्रोत", nav_method:"कार्यप्रणाली", langEN:"अंग्रेज़ी", langHI:"हिंदी",
    filterLean:"झुकाव", filterLang:"भाषा", ownership:"स्वामित्व", whyRated:"यह रेटिंग क्यों",
    signals:"संकेत", confidence:"विश्वास", contested:"विवादित", provisional:"अस्थायी",
    srcTitle:"स्रोत रेटिंग", srcIntro:"पक्ष जिन आउटलेट्स को ट्रैक करता है, उनकी रेटिंग और कारण।",
    srcDisclaimer:"सभी रेटिंग अस्थायी हैं — रूब्रिक के विरुद्ध समीक्षित एक प्रलेखित शुरुआती बिंदु, अंतिम फ़ैसला नहीं। झुकाव प्रकाशन का वर्णन करता है, किसी एक लेख का नहीं, और अपील के लिए खुला है।",
    suggestFix:"सुधार सुझाएँ", methodTitle:"पक्ष कैसे काम करता है",
    m_doesH:"पक्ष क्या करता है", m_does:"पक्ष एक ही खबर की कवरेज को पूरे स्पेक्ट्रम के आउटलेट्स से इकट्ठा करता है, एक तटस्थ सारांश दिखाता है, और बताता है कि हर पक्ष ने उसे कैसे पेश किया — ताकि आप पूरी तस्वीर देख सकें और जान सकें कि आपके सामान्य स्रोत क्या छोड़ देते हैं।",
    m_ruleH:"मूल नियम", m_rule:"झुकाव का लेबल प्रकाशन का होता है, किसी एक लेख का नहीं — और कभी AI का नहीं। पक्ष के संपादक एक निश्चित रूब्रिक से हर आउटलेट को झुकाव देते हैं। AI सिर्फ़ तटस्थ सारांश लिखता है और बताता है कि आउटलेट्स ने खबर को कैसे पेश किया; वह किसी की राजनीति तय नहीं करता। किसी खबर का बायस बार सीधा गणित है: हम गिनते हैं कि कवर करने वाले कितने आउटलेट किस ओर हैं।",
    m_rateH:"हम किसी प्रकाशन को कैसे आँकते हैं", m_rateLede:"हम हर प्रकाशन को छह संकेतों पर आँकते हैं, हर एक को −2 से +2 तक अंक देकर एक स्कोर में जोड़ा जाता है, −10 (वाम) से +10 (दक्षिण):", m_rateFoot:"शून्य के पास के स्कोर केंद्र हैं; शून्य से जितना दूर, झुकाव उतना मज़बूत। पूरी रूब्रिक हमारी कार्यप्रणाली फ़ाइल में खुले तौर पर उपलब्ध है।",
    m_axisH:"भारत में “वाम” और “दक्षिण” का अर्थ", m_axis:"भारत में वाम और दक्षिण केवल अर्थशास्त्र के बारे में नहीं हैं। पक्ष एक सामाजिक-वैचारिक अक्ष (धर्मनिरपेक्ष ↔ हिंदुत्व) को एक संस्थागत अक्ष (सत्ता के आलोचक ↔ सत्ता के साथ) के साथ जोड़ता है, और आर्थिक रुख को अलग से देखता है। “वाम” और “दक्षिण” वर्णनात्मक हैं, अपमान नहीं — और एक ही कसौटी पूरे स्पेक्ट्रम पर लागू होती है।",
    m_provH:"विश्वास, विवादित और अस्थायी", m_prov:"आज हर रेटिंग अस्थायी है: स्वामित्व, स्व-घोषित रुख और स्थापित प्रतिष्ठा पर आधारित एक प्रलेखित शुरुआती बिंदु, रूब्रिक के विरुद्ध समीक्षित — अंतिम फ़ैसला नहीं। हर एक के साथ एक विश्वास-स्तर दिखता है, और कुछ को ‘विवादित’ चिह्नित किया गया है जहाँ झुकाव सचमुच बहस में है या स्वामित्व हाल में बदला है।",
    m_readH:"पक्ष की खबर कैसे पढ़ें", m_appealH:"सुधार और अपील",
    m_partiesH:"भारत की पार्टियाँ मोटे तौर पर कहाँ हैं", m_parties:"ये लेबल विचारों का वर्णन करते हैं, टीमों का नहीं — और ये मोटे अनुमान हैं, क्योंकि पार्टियाँ समय के साथ बदलती हैं और कई क्षेत्रीय पार्टियाँ किसी एक रेखा पर ठीक से नहीं बैठतीं। आम समझ के अनुसार: वाम में CPI(M) और CPI जैसी कम्युनिस्ट और समाजवादी पार्टियाँ आती हैं, जो धर्मनिरपेक्ष और कल्याण-समर्थक, श्रमिक-पहले रुख से जुड़ी हैं; दक्षिण — सबसे प्रमुख रूप से भाजपा — हिंदुत्व-प्रभावित सांस्कृतिक राष्ट्रवाद और अधिक बाज़ार-समर्थक आर्थिक रुख से जुड़ी है; केंद्र बीच में फैला है, जहाँ कांग्रेस को अक्सर केंद्र-वाम कहा जाता है और कई क्षेत्रीय पार्टियाँ मुद्दे के हिसाब से रुख मिलाती हैं। याद रखें: पक्ष समाचार आउटलेट्स को आँकता है, पार्टियों को नहीं — किसी आउटलेट का झुकाव इस बारे में है कि वह खबरों को कैसे कवर करता है, इस बारे में नहीं कि वह किसे वोट देता है।",
    m_appeal:"लगता है कोई रेटिंग ग़लत है? हमें आउटलेट, जिस रेटिंग से असहमत हैं, और कुछ ठोस उदाहरण — हेडलाइन या लेख — बताएँ, और हम उसे रूब्रिक के विरुद्ध फिर से देखेंगे। रेटिंग्स को चुनौती देने के लिए ही हैं।",
    m_sourcesLink:"हर आउटलेट और उसकी रेटिंग देखें —",
    word:"पक्ष", tag_pre:"देखिए भारत का मीडिया हर खबर को कैसे कवर करता है —", tag_b:"हर पक्ष, आमने-सामने।",
    nav_top:"मुख्य खबरें", nav_os:"एकतरफ़ा", search:"खबर खोजें",
    topStories:"मुख्य खबरें", osStories:"एकतरफ़ा खबरें",
    osSub:"ऐसी खबरें जिन्हें ज़्यादातर एक ही पक्ष कवर कर रहा है — दूसरे पक्ष के पाठक इन्हें शायद ही देख पाते हैं।",
    osShort:"एकतरफ़ा", sideBySide:"आमने-सामने", covBreak:"कवरेज का ब्यौरा",
    whereLean:"स्रोत किस ओर झुके हैं", aiSummary:"पक्ष तटस्थ सारांश",
    aiNote:"यह सारांश आउटलेट्स की अपनी कवरेज से AI द्वारा लिखा गया है। झुकाव के लेबल प्रकाशकों का वर्णन करते हैं और पक्ष के संपादक तय करते हैं, AI नहीं; आँकड़े स्रोतों से आते हैं, सारांश से नहीं।",
    myMix:"मेरा पठन संतुलन", myMixSub:"आपका अपना पठन कितना संतुलित है?",
    myMixNote:"अपने पठन को जोड़ें और देखें कि वह पूरे स्पेक्ट्रम में कैसे फैला है।", myMixSoon:"जल्द आ रहा है",
    myMixCta:"यह कैसे काम करता है", sources:"स्रोत", source:"स्रोत",
    most:"सबसे ज़्यादा कवरेज", even:"लगभग बराबर कवरेज", onlyOn:"केवल इस ओर कवर हुई:", notOn:"इस ओर कवर नहीं हुई:",
    sideWord:"", divergence:"कवरेज में अंतर कैसे है", omissions:"क्या छूट जाता है",
    back:"वापस", all:"सभी", demo:"डेमो",
    noStories:"अभी दिखाने के लिए कोई खबर नहीं है। कृपया थोड़ी देर बाद देखें।",
    noOS:"मौजूदा सेट में कोई एकतरफ़ा खबर नहीं।",
    left:"वाम", center:"केंद्र", right:"दक्षिण",
    footAbout:"परिचय और कार्यप्रणाली",
    footFine:"पक्ष दिखाता है कि अलग-अलग आउटलेट एक ही खबर को कैसे कवर करते हैं। झुकाव के लेबल प्रकाशकों का वर्णन करते हैं, एक पारदर्शी रूब्रिक से तय — ये अस्थायी हैं और अपील के लिए खुले हैं। पक्ष एक स्वतंत्र परियोजना है और किसी आउटलेट से संबद्ध नहीं है।"
  }
};
const TOPIC_HI = {Politics:"राजनीति", Economy:"अर्थव्यवस्था", International:"अंतरराष्ट्रीय", Sports:"खेल",
  "Crime & Law":"अपराध व कानून", "Science & Tech":"विज्ञान व तकनीक", Health:"स्वास्थ्य",
  Entertainment:"मनोरंजन", Environment:"पर्यावरण", Society:"समाज", General:"सामान्य"};

const SIGNALS = [
  {en:"Editorial stance", hi:"संपादकीय रुख", w:30},
  {en:"Framing & word choice", hi:"फ़्रेमिंग और शब्द-चयन", w:25},
  {en:"Story selection", hi:"खबरों का चयन", w:20},
  {en:"Sourcing & who they quote", hi:"स्रोत और उद्धरण", w:10},
  {en:"Ownership & affiliations", hi:"स्वामित्व और संबद्धता", w:10},
  {en:"Cross-spectrum panel check", hi:"क्रॉस-स्पेक्ट्रम पैनल जाँच", w:5},
];
const M_READ = {
  en: [
    "The coloured bar shows how many of the covering outlets lean Left, Centre or Right.",
    "“One-Sided” marks a story that mostly one side of the spectrum is covering — so the other side's readers rarely see it.",
    "The neutral summary is written by AI from the outlets' own coverage; the outlet labels and the counts come from editors and the registry, not the AI.",
  ],
  hi: [
    "रंगीन बार दिखाता है कि कवर करने वाले कितने आउटलेट वाम, केंद्र या दक्षिण की ओर हैं।",
    "“एकतरफ़ा” उस खबर को चिह्नित करता है जिसे ज़्यादातर एक ही पक्ष कवर कर रहा है — इसलिए दूसरे पक्ष के पाठक उसे शायद ही देखते हैं।",
    "तटस्थ सारांश AI द्वारा आउटलेट्स की अपनी कवरेज से लिखा जाता है; आउटलेट के लेबल और गिनती संपादकों और रजिस्ट्री से आती है, AI से नहीं।",
  ],
};
const CONTACT = "corrections@paksh.example";  // <-- change to your real address

const app = document.getElementById("app");
const S = { lang:"en", mode:"top", topic:null, query:"", detailId:null, fLean:null, fLang:null };
const DATA = { events:null, blindspots:null, topics:null };
const DETAIL = {};

const t = k => STR[S.lang][k];
const esc = s => (s==null?"":String(s)).replace(/[&<>"']/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const hiClass = () => S.lang === "hi" ? "hi" : "";
const titleOf = e => (S.lang==="hi" && e.title_hi) ? e.title_hi : e.title;
const summaryOf = e => (S.lang==="hi" && e.summary_hi) ? e.summary_hi : e.summary;
const pointsOf = e => (S.lang==="hi" && e.summary_points_hi && e.summary_points_hi.length)
  ? e.summary_points_hi : (e.summary_points || []);
const leanName = side => t(side);
const topicLabel = tp => S.lang==="hi" ? (TOPIC_HI[tp] || tp) : tp;

const confName = c => (({en:{low:"Low",medium:"Medium",high:"High"},hi:{low:"कम",medium:"मध्यम",high:"उच्च"}}[S.lang])||{})[c] || c;

function hueOf(s){ let h=0; for(const ch of String(s)) h=(h*31+ch.charCodeAt(0))%360; return h; }
function thumb(e){
  if (e.image_url) return `<div class="thumb"><img src="${esc(e.image_url)}" alt="" loading="lazy"></div>`;
  const h = hueOf(e.topic || e.title);
  const bg = `linear-gradient(135deg, hsl(${h} 42% 40%), hsl(${(h+40)%360} 50% 30%))`;
  return `<div class="thumb"><div class="ph" style="background:${bg}"><span>${esc(topicLabel(e.topic))}</span></div></div>`;
}

// Two data modes, auto-detected: a live API (local FastAPI / self-hosted) OR
// pre-built static JSON files (GitHub Pages). Probe once, then stick with it.
let _mode;
function detectMode(){
  if (!_mode) _mode = (async () => {
    try { const r = await fetch("/api/topics"); if (r.ok) return "api"; } catch (e) {}
    return "static";   // no live API -> use the exported data/*.json files
  })();
  return _mode;
}
async function apiGet(resource){
  if (await detectMode() === "api"){
    const r = await fetch("/api/" + resource);
    if (r.ok) return r.json();
  }
  const r = await fetch("data/" + resource + ".json");
  if (!r.ok) throw new Error("data/" + resource);
  return r.json();
}

async function load(){
  try{
    const [e,b,tp,sr] = await Promise.all([
      apiGet("events"), apiGet("blindspots"), apiGet("topics"), apiGet("sources")]);
    DATA.events = e.events; DATA.blindspots = b.events; DATA.topics = tp.topics;
    DATA.sources = sr.sources; DATA.sourcesSummary = sr.summary;
  }catch(err){ console.error(err); DATA.events=[]; DATA.blindspots=[]; DATA.topics=[]; DATA.sources=[]; }
  render();
}

/* ---------- bias bar (Paksh treatment: gapped segments + legend below) ---------- */
function counts(e){ const c = e.lean_counts || {left:0,center:0,right:0};
  return {left:c.left||0, center:c.center||0, right:c.right||0}; }
function biasBar(e, withCaption=true){
  const c = counts(e), total = c.left + c.center + c.right || 1;
  const pct = s => Math.round(c[s]/total*100);
  const seg = s => c[s] ? `<div class="seg ${s}" style="width:${c[s]/total*100}%"></div>` : "";
  const lg = s => c[s] ? `<span class="lg"><span class="swatch ${s}"></span>${leanName(s)} ${pct(s)}%</span>` : "";
  let caption = "";
  if (withCaption){
    const top = ["left","center","right"].sort((a,b)=>c[b]-c[a]);
    const lead = top[0], even = (c[lead]-c[top[1]]) <= 0;
    const n = c.left+c.center+c.right;
    const word = n===1 ? t("source") : t("sources");
    caption = `<div class="bias-caption">${ even
      ? `<b>${t("even")}</b>` : `${t("most")}: <b>${leanName(lead)}</b>` }
      <span class="pin">· ${n} ${word}</span></div>`;
  }
  return `<div class="bias">
    <div class="bias-track">${seg("left")}${seg("center")}${seg("right")}</div>
    <div class="bias-legend">${lg("left")}${lg("center")}${lg("right")}</div>
    ${caption}</div>`;
}

/* ---------- cards ---------- */
function card(e, featured=false){
  const cls = featured ? "card featured" : "card row-card";
  const demo = e.is_demo ? `<span class="demo">${t("demo")}</span>` : "";
  return `<article class="${cls}" data-act="open:${e.id}">
    ${thumb(e)}
    <div class="card-body">
      <div class="eyebrow"><span class="topic">${esc(topicLabel(e.topic))}</span>${demo}</div>
      <h3 class="headline ${hiClass()}">${esc(titleOf(e))}</h3>
      <p class="dek ${hiClass()}">${esc(summaryOf(e))}</p>
      ${biasBar(e)}
    </div>
  </article>`;
}

function osItem(e){
  const side = e.blindspot ? e.blindspot.side : null;
  const missLabel = side ? `<span class="os-miss"><span class="tag ${side}">${t("notOn")} ${leanName(side)}</span></span>` : "";
  const n = (counts(e).left+counts(e).center+counts(e).right);
  return `<button class="os-item" data-act="open:${e.id}">
    ${missLabel}
    <div class="h ${hiClass()}">${esc(titleOf(e))}</div>
    <div class="m">${esc(topicLabel(e.topic))} · ${n} ${n===1?t("source"):t("sources")}</div>
  </button>`;
}

function readingMix(){
  return `<div class="panel">
    <div class="panel-h"><h3 class="${hiClass()}">${t("myMix")}</h3><p class="${hiClass()}">${t("myMixSub")}</p></div>
    <div class="mix-body">
      <div class="mix-bar">
        <div class="seg left" style="width:34%;background:var(--left)">34%</div>
        <div class="seg center" style="width:38%;background:var(--center)">38%</div>
        <div class="seg right" style="width:28%;background:var(--right)">28%</div>
      </div>
      <p class="mix-note ${hiClass()}">${t("myMixNote")} <b>${t("myMixSoon")}</b></p>
      <button class="mix-cta ${hiClass()}" data-act="about">${t("myMixCta")}</button>
    </div>
  </div>`;
}

function sidebar(){
  const os = (DATA.blindspots || []).slice(0,4).map(osItem).join("") ||
    `<div style="padding:16px" class="m ${hiClass()}">${t("noOS")}</div>`;
  return `<aside class="side">
    <div class="panel">
      <div class="panel-h">
        <div class="kicker"><span class="badge-os">● ${t("osShort")}</span></div>
        <h3 class="${hiClass()}">${t("osStories")}</h3>
        <p class="${hiClass()}">${t("osSub")}</p>
      </div>
      ${os}
    </div>
    ${readingMix()}
  </aside>`;
}

/* ---------- feed view ---------- */
function filterList(list){
  let r = list || [];
  if (S.topic) r = r.filter(e => e.topic === S.topic);
  if (S.query){ const q = S.query.toLowerCase();
    r = r.filter(e => (e.title||"").toLowerCase().includes(q) || (e.title_hi||"").includes(S.query)); }
  return r;
}
function feedView(){
  const isOS = S.mode === "oneSided";
  const base = isOS ? DATA.blindspots : DATA.events;
  const list = filterList(base);
  const head = isOS
    ? `<div class="section-h"><h2 class="${hiClass()}">${t("osStories")}</h2><div class="rule"></div></div>`
    : `<div class="section-h"><h2 class="${hiClass()}">${t("topStories")}</h2><div class="rule"></div></div>`;
  let body;
  if (!list.length){
    body = `<div class="empty ${hiClass()}">${isOS ? t("noOS") : t("noStories")}</div>`;
  } else if (isOS){
    body = `<div class="feed">${list.map(e=>card(e)).join("")}</div>`;
  } else {
    const [first, ...rest] = list;
    body = `<div class="feed">${card(first,true)}${rest.map(e=>card(e)).join("")}</div>`;
  }
  return `<div class="cols"><div>${head}${body}</div>${sidebar()}</div>`;
}

/* ---------- detail view ---------- */
function outletRow(o){
  return `<div class="outlet ${o.lean}">
    <div class="bar"></div>
    <div>
      <div class="nm">${esc(o.source)} <span class="lang">${(o.language||"en").toUpperCase()}</span></div>
      ${o.headline ? `<div class="hl">${esc(o.headline)}</div>`:""}
      ${o.framing ? `<div class="frm">${esc(o.framing)}</div>`:""}
    </div>
  </div>`;
}
function sbsSide(e, side){
  const cov = (e.coverage||{})[side] || {count:0, sources:[], framing:""};
  if (!cov.count) return "";
  const outlets = (e.sources||[]).filter(s=>s.lean===side).map(outletRow).join("");
  return `<div class="sbs-side ${side}">
    <div class="top"><span>${leanName(side)}</span><span>${cov.count}</span></div>
    ${cov.framing ? `<div class="fr ${hiClass()}">${esc(cov.framing)}</div>`:""}
    ${outlets}
  </div>`;
}
function detailView(e){
  const c = counts(e), n = c.left+c.center+c.right;
  const hero = e.image_url
    ? `<img class="hero-img" src="${esc(e.image_url)}" alt="">`
    : `<div class="hero-ph" style="background:linear-gradient(135deg,hsl(${hueOf(e.topic||e.title)} 42% 40%),hsl(${(hueOf(e.topic||e.title)+40)%360} 50% 30%))"><span style="font-weight:700;text-transform:uppercase;letter-spacing:.06em">${esc(topicLabel(e.topic))}</span></div>`;
  const os = e.blindspot ? `<div class="os-callout ${hiClass()}"><span>●</span><div><b>${t("osShort")}.</b> ${t("notOn")} <b>${leanName(e.blindspot.side)}</b> ${t("sideWord")}.</div></div>` : "";
  const pts = pointsOf(e).map(p=>`<li class="${hiClass()}">${esc(p)}</li>`).join("");
  const sbs = ["left","center","right"].map(s=>sbsSide(e,s)).join("");
  const covRows = ["left","center","right"].map(s=>{
    const ct = (e.coverage&&e.coverage[s]) ? e.coverage[s].count : 0;
    return `<div class="cov-row"><span class="nm"><span class="swatch ${s}"></span>${leanName(s)}</span><span class="ct">${ct}</span></div>`;
  }).join("");
  return `<div class="detail">
    <button class="back ${hiClass()}" data-act="back">← ${t("back")}</button>
    ${hero}
    ${os}
    <div class="meta"><span class="topic">${esc(topicLabel(e.topic))}</span><span>·</span><span>${n} ${n===1?t("source"):t("sources")}</span>${e.is_demo?`<span>·</span><span>${t("demo")}</span>`:""}</div>
    <h1 class="${hiClass()}">${esc(titleOf(e))}</h1>
    <div class="summary-card">
      <div class="lab ${hiClass()}">${t("aiSummary")}</div>
      <p class="lede ${hiClass()}">${esc(summaryOf(e))}</p>
      <ul>${pts}</ul>
      <div class="ai-note ${hiClass()}">${t("aiNote")}</div>
    </div>
    <div class="cov-grid">
      <div>
        <div class="block-h ${hiClass()}">${t("sideBySide")}</div>
        <div class="sbs">${sbs}</div>
      </div>
      <div>
        <div class="cov-panel">
          <div class="ttl ${hiClass()}">${t("whereLean")}</div>
          ${biasBar(e,false)}
          <div style="margin-top:12px">${covRows}</div>
        </div>
        ${e.divergence ? `<div class="divergence ${hiClass()}"><b>${t("divergence")}.</b> ${esc(S.lang==="hi"&&e.divergence_hi?e.divergence_hi:e.divergence)}</div>`:""}
        ${e.omissions ? `<div class="divergence ${hiClass()}"><b>${t("omissions")}.</b> ${esc(S.lang==="hi"&&e.omissions_hi?e.omissions_hi:e.omissions)}</div>`:""}
      </div>
    </div>
  </div>`;
}

/* ---------- sources (transparency) ---------- */
function srcCard(s){
  const labels = {editorial:"Ed", framing:"Fr", selection:"Sel", sourcing:"Src", ownership:"Own", panel:"Pan"};
  const sub = s.subscores ? `<div class="signals"><span class="sg-lab ${hiClass()}">${t("signals")}:</span>` +
    Object.entries(labels).map(([k,lab])=>{ const v=s.subscores[k]; const cls=v<0?"neg":v>0?"pos":"zero";
      return `<span class="sg ${cls}">${lab} ${v>0?"+"+v:v}</span>`; }).join("") + `</div>` : "";
  const contested = s.contested ? `<span class="contested ${hiClass()}">${t("contested")}</span>` : "";
  const site = (s.website||"").replace(/^https?:\/\//,"");
  const body = "Outlet: "+s.name+"\nCurrent rating: "+(s.label||s.lean)+
    "\n\nI think this should be reviewed because (please give specific headlines or articles):\n\n";
  const fix = `mailto:${CONTACT}?subject=${encodeURIComponent("Paksh rating appeal: "+s.name)}&body=${encodeURIComponent(body)}`;
  return `<div class="src-card">
    <div class="src-head">
      <div>
        <div class="src-name">${esc(s.name)} <span class="lang">${(s.language||"en").toUpperCase()}</span></div>
        <a class="src-site" href="${esc(s.website)}" target="_blank" rel="noopener">${esc(site)}</a>
      </div>
      <div class="src-rate">
        <span class="lean-chip ${s.lean}">${leanName(s.lean)}</span>
        <span class="conf ${hiClass()}">${confName(s.confidence)} ${t("confidence")}</span>
        ${contested}
      </div>
    </div>
    <div class="src-meta ${hiClass()}"><b>${t("ownership")}:</b> ${esc(s.ownership)}</div>
    <div class="src-why ${hiClass()}"><b>${t("whyRated")}:</b> ${esc(s.rationale)}</div>
    ${sub}
    <a class="src-fix ${hiClass()}" href="${fix}">${t("suggestFix")} →</a>
  </div>`;
}
function sourcesView(){
  let list = DATA.sources || [];
  if (S.fLean) list = list.filter(s => s.lean === S.fLean);
  if (S.fLang) list = list.filter(s => s.language === S.fLang);
  const leanF = ["", "left","center","right"].map(v =>
    `<button class="chip ${(S.fLean||"")===v?"on":""} ${hiClass()}" data-act="flean:${v}">${v?leanName(v):t("all")}</button>`).join("");
  const langF = ["", "en","hi"].map(v =>
    `<button class="chip ${(S.fLang||"")===v?"on":""} ${hiClass()}" data-act="flang:${v}">${v?(v==="en"?t("langEN"):t("langHI")):t("all")}</button>`).join("");
  const cards = list.length ? list.map(srcCard).join("") : `<div class="empty">—</div>`;
  return `<div class="doc">
    <h1 class="${hiClass()}">${t("srcTitle")}</h1>
    <p class="lede ${hiClass()}">${t("srcIntro")}</p>
    <div class="callout ${hiClass()}"><b>${t("provisional")}.</b> ${t("srcDisclaimer")}</div>
    <div class="filters">
      <span class="flab ${hiClass()}">${t("filterLean")}:</span>${leanF}
      <span class="flab ${hiClass()}" style="margin-left:8px">${t("filterLang")}:</span>${langF}
    </div>
    <div class="src-list">${cards}</div>
  </div>`;
}

/* ---------- method (how it works) ---------- */
function methodView(){
  const sig = SIGNALS.map(s =>
    `<li class="sig-li"><span class="sig-name ${hiClass()}">${S.lang==="hi"?s.hi:s.en}</span><span class="sig-w">${s.w}%</span></li>`).join("");
  const reads = (S.lang==="hi"?M_READ.hi:M_READ.en).map(x => `<li class="${hiClass()}">${x}</li>`).join("");
  const body = "Outlet:\nCurrent rating:\n\nWhy it should be reviewed (specific headlines or articles):\n\n";
  const fix = `mailto:${CONTACT}?subject=${encodeURIComponent("Paksh rating appeal")}&body=${encodeURIComponent(body)}`;
  return `<div class="doc">
    <h1 class="${hiClass()}">${t("methodTitle")}</h1>
    <h2 class="${hiClass()}">${t("m_doesH")}</h2>
    <p class="${hiClass()}">${t("m_does")}</p>
    <div class="callout ${hiClass()}"><b>${t("m_ruleH")}.</b> ${t("m_rule")}</div>
    <h2 class="${hiClass()}">${t("m_rateH")}</h2>
    <p class="${hiClass()}">${t("m_rateLede")}</p>
    <ul class="sig-list">${sig}</ul>
    <p class="fineprint ${hiClass()}">${t("m_rateFoot")}</p>
    <h2 class="${hiClass()}">${t("m_axisH")}</h2>
    <p class="${hiClass()}">${t("m_axis")}</p>
    <h2 class="${hiClass()}">${t("m_partiesH")}</h2>
    <p class="${hiClass()}">${t("m_parties")}</p>
    <h2 class="${hiClass()}">${t("m_provH")}</h2>
    <p class="${hiClass()}">${t("m_prov")}</p>
    <h2 class="${hiClass()}">${t("m_readH")}</h2>
    <ul class="read-list">${reads}</ul>
    <h2 class="${hiClass()}">${t("m_appealH")}</h2>
    <p class="${hiClass()}">${t("m_appeal")}</p>
    <a class="btn-primary ${hiClass()}" href="${fix}">${t("suggestFix")}</a>
    <p class="fineprint ${hiClass()}" style="margin-top:18px">${t("m_sourcesLink")} <a data-act="view-sources" style="color:var(--brand-ink);font-weight:700;cursor:pointer">${t("nav_sources")} →</a></p>
  </div>`;
}

/* ---------- chrome ---------- */
function header(){
  const chips = [`<button class="chip ${!S.topic?"on":""}" data-act="topic:">${t("all")}</button>`]
    .concat((DATA.topics||[]).map(tp =>
      `<button class="chip ${S.topic===tp?"on":""} ${hiClass()}" data-act="topic:${esc(tp)}">${esc(topicLabel(tp))}</button>`)).join("");
  return `<header class="brandbar">
    <div class="wrap brandbar-row">
      <a class="logo" data-act="home"><span class="mark">पक्ष</span><span class="word">Paksh</span><span class="dot"></span></a>
      <nav class="nav">
        <button class="${S.mode==="top"?"on":""} ${hiClass()}" data-act="view-top">${t("nav_top")}</button>
        <button class="${S.mode==="oneSided"?"on":""} ${hiClass()}" data-act="view-os">${t("nav_os")}</button>
        <button class="${S.mode==="sources"?"on":""} ${hiClass()}" data-act="view-sources">${t("nav_sources")}</button>
        <button class="${S.mode==="method"?"on":""} ${hiClass()}" data-act="view-method">${t("nav_method")}</button>
      </nav>
      <div class="spring"></div>
      <div class="search">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
        <input id="q" placeholder="${t("search")}" value="${esc(S.query)}" />
      </div>
      <div class="langtog">
        <button class="${S.lang==="en"?"on":""}" data-act="lang:en">EN</button>
        <button class="${S.lang==="hi"?"on":""}" data-act="lang:hi">हिं</button>
      </div>
    </div>
    <div class="subbar"><div class="wrap subbar-row">
      <span class="tagline ${hiClass()}">${t("tag_pre")} <b>${t("tag_b")}</b></span>
      <div class="chips">${chips}</div>
    </div></div>
  </header>`;
}
function footer(){
  return `<footer class="foot"><div class="wrap foot-row">
    <div><a data-act="about" class="${hiClass()}">${t("footAbout")}</a> · <a data-act="view-sources" class="${hiClass()}">${t("nav_sources")}</a></div>
    <div class="fine ${hiClass()}">${t("footFine")}</div>
  </div></footer>`;
}

/* ---------- render ---------- */
function render(){
  let view;
  if (S.detailId != null && DETAIL[S.detailId]) view = detailView(DETAIL[S.detailId]);
  else if (S.mode === "sources") view = sourcesView();
  else if (S.mode === "method") view = methodView();
  else view = feedView();
  app.innerHTML = header() + `<main class="wrap page">${view}</main>` + footer();
  const q = document.getElementById("q");
  if (q && document.activeElement !== q && S.query){ q.focus(); q.selectionStart = q.value.length; }
}

async function openEvent(id){
  if (!DETAIL[id]){
    try { DETAIL[id] = await apiGet("events/" + id); }
    catch(err){ console.error(err); return; }
  }
  S.detailId = id; window.scrollTo(0,0); render();
}

/* ---------- events ---------- */
app.addEventListener("click", e => {
  const el = e.target.closest("[data-act]"); if (!el) return;
  const act = el.getAttribute("data-act");
  if (act === "home" || act === "view-top"){ S.mode="top"; S.detailId=null; }
  else if (act === "view-os"){ S.mode="oneSided"; S.detailId=null; }
  else if (act === "view-sources"){ S.mode="sources"; S.detailId=null; }
  else if (act === "view-method" || act === "about"){ S.mode="method"; S.detailId=null; }
  else if (act === "back"){ S.detailId=null; }
  else if (act.startsWith("open:")){ openEvent(parseInt(act.slice(5),10)); return; }
  else if (act.startsWith("topic:")){ const v=act.slice(6); S.topic = v || null; S.detailId=null; }
  else if (act.startsWith("flean:")){ const v=act.slice(6); S.fLean = v || null; }
  else if (act.startsWith("flang:")){ const v=act.slice(6); S.fLang = v || null; }
  else if (act.startsWith("lang:")){ S.lang = act.slice(5); }
  if (act.startsWith("view-") || act === "home" || act === "about") window.scrollTo(0,0);
  render();
});
app.addEventListener("input", e => {
  if (e.target.id === "q"){ S.query = e.target.value; S.detailId=null; render(); }
});

load();