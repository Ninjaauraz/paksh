const {useState,useEffect,useMemo}=React;
    // App context: save/clip state (feed cards get a ✂ CLIP action) + go() for nav from deep
    // components (e.g. a clicked ad box → the advertiser form) without prop-drilling.
    const SaveCtx = React.createContext({ saved:new Set(), toggle:()=>{}, on:false, go:()=>{} });
    // Set true when a reader clicks an ad box, so the Contact form opens pre-set to "Advertise".
    let _adIntent = false;
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
    // Editorial tonality axes (0-100), set per PUBLISHER by editors in sources.py -
    // additive detail alongside the arithmetic Left/Centre/Right bias bar, never a
    // per-article or AI-decided score. Each value is a position between two named poles.
    const AXES = [
      { key:"secular_authoritative", color:"#4A6E80",
        en:{ name:"Ideological",   lo:"Authoritative", hi:"Secular" },
        hi:{ name:"वैचारिक",       lo:"सत्तावादी",     hi:"धर्मनिरपेक्ष" } },
      { key:"market_orientation", color:"#7E7768",
        en:{ name:"Economic",      lo:"State-leaning", hi:"Pro-market" },
        hi:{ name:"आर्थिक",        lo:"राज्य-समर्थक",  hi:"बाज़ार-समर्थक" } },
      { key:"incumbent_stance", color:"#96603F",
        en:{ name:"Establishment", lo:"Critical",      hi:"Pro-govt" },
        hi:{ name:"सत्ता के प्रति", lo:"आलोचनात्मक",    hi:"सत्ता-समर्थक" } },
    ];
    const TOKENS = {
      light: { bg:"bg-[#EAE6DB]", surface:"bg-[#F4F1EA]", soft:"bg-[#EFEBE1]", border:"border-[#D8D3C6]",
        tp:"text-[#15140F]", ts:"text-[#3A372F]", tf:"text-[#8A8371]", brand:"text-[#15140F]", brandBg:"bg-[#15140F]",
        blind:"text-[#75442E]", blindSoft:"bg-[#EFE3DB]", nav:"glass-nav-light",
        cta:"bg-[#15140F]", ctaT:"text-[#F4F1EA]", line:"#D8D3C6", ink:"#15140F", chip:"bg-[#EAE6DB]", centerSeg:"#8C8579",
        track:"#EAE6DB", gap:"#F4F1EA" },
      dark: { bg:"bg-[#1A1917]", surface:"bg-[#201F1C]", soft:"bg-[#262420]", border:"border-[#35322C]",
        // tf was #847E72 = 4.36:1 on the dark surface, just under WCAG AA (4.5). #948E7E clears
        // AA (~5:1 on bg, ~4.7:1 on the soft card) while staying visibly "faint".
        tp:"text-[#EDEAE2]", ts:"text-[#B7B1A4]", tf:"text-[#948E7E]", brand:"text-[#EDEAE2]", brandBg:"bg-[#EDEAE2]",
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
          "“Coverage Gaps” marks a story that outlets on one side of the spectrum covered while few or none on the other did, shown with the full Left · Centre · Right count.",
          "The neutral summary is generated automatically from the outlets' own coverage; the outlet labels and the counts come from editors and the registry, not the summary engine."],
      hi:["रंगीन बार दिखाता है कि कवर करने वाले कितने आउटलेट वाम, केंद्र या दक्षिण की ओर हैं।",
          "“कवरेज गैप” उस खबर को चिह्नित करता है जिसे स्पेक्ट्रम के एक तरफ़ के आउटलेट्स ने कवर किया पर दूसरी तरफ़ के बहुत कम या किसी ने नहीं, पूरे वाम · केंद्र · दक्षिण आँकड़े के साथ।",
          "तटस्थ सारांश आउटलेट्स की अपनी कवरेज से स्वचालित रूप से तैयार होता है; आउटलेट के लेबल और गिनती संपादकों और रजिस्ट्री से आती है, सारांश इंजन से नहीं।"],
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
    const SUPPORT = { upi: "", url: "", payeeName: "Paksh" };
    const supportReady = () => !!(SUPPORT.upi || SUPPORT.url);
    // A UPI deep link that opens the user's UPI app pre-filled (no amount forced).
    const upiLink = (amt) => SUPPORT.upi
      ? `upi://pay?pa=${encodeURIComponent(SUPPORT.upi)}&pn=${encodeURIComponent(SUPPORT.payeeName||"Paksh")}&cu=INR${amt?`&am=${amt}`:""}`
      : "";

    // --- Sponsorship (stays INVISIBLE until you actually have a sponsor) -------------------
    // Unlike reader support, an empty "Supported by ___" slot looks broken, so this renders
    // NOTHING until a sponsor is configured. Fill one in only when a deal is signed.
    const SPONSOR = { name: "", url: "", line: "" };   // e.g. {name:"Acme", url:"https://…", line:"Media literacy for all"}

    /* ---------------- accounts (Supabase, NO SDK - direct REST, like the Formspree fetch) ----------------
       Static-site-safe: talks to Supabase's hosted Auth (GoTrue) + PostgREST over plain fetch.
       No CDN script, no bundler, no runtime dependency added. The key below is the PUBLIC
       "anon"/publishable key - it is DESIGNED to ship to browsers and is guarded by row-level
       security on every table, so it is NOT a secret. The secret service_role key is never used
       on the client and never appears here. News is NEVER gated by an account - only the personal
       features (Reading Lens, Saved) are. Leave SUPABASE.url = "" to switch accounts fully OFF:
       the Sign-in / account UI simply disappears and the rest of the site is unaffected. */
    const SUPABASE = {
      url: "https://zzjsjqqcpyyodatlmcux.supabase.co",
      anonKey: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inp6anNqcXFjcHl5b2RhdGxtY3V4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgxNzU1OTIsImV4cCI6MjA5Mzc1MTU5Mn0.U-TRJegvnt7iO1mM9nok319FJHszJ9HNzuRZLfuuvys",
    };
    const authOn = () => !!(SUPABASE.url && SUPABASE.anonKey);
    const AUTH_LS = "paksh-auth";
    const _readSession = () => { try { return JSON.parse(localStorage.getItem(AUTH_LS)||"null"); } catch(e){ return null; } };
    const _writeSession = (s) => { try { if(s) localStorage.setItem(AUTH_LS, JSON.stringify(s)); else localStorage.removeItem(AUTH_LS); } catch(e){} };
    const _mkSession = (s) => ({ access_token:s.access_token, refresh_token:s.refresh_token,
      expires_at:(Math.floor(Date.now()/1000))+(s.expires_in||3600), user:s.user||null });
    async function _sb(path, opts){
      opts=opts||{};
      const headers=Object.assign({ apikey:SUPABASE.anonKey, "Content-Type":"application/json" }, opts.headers||{});
      const r=await fetch(SUPABASE.url+path, Object.assign({}, opts, {headers}));
      const ct=(r.headers.get("content-type")||"");
      const body=ct.includes("json")?await r.json().catch(()=>({})):await r.text().catch(()=>"");
      if(!r.ok){ const m=(body&&(body.error_description||body.msg||body.error||body.message))||(typeof body==="string"&&body)||("HTTP "+r.status); throw new Error(m); }
      return body;
    }
    // Send a 6-digit email code. create_user:true means one flow both signs in AND registers.
    async function authSendCode(email){ return _sb("/auth/v1/otp", { method:"POST", body:JSON.stringify({ email, create_user:true }) }); }
    // Verify the code -> a session; persist it.
    async function authVerifyCode(email, token){ const s=_mkSession(await _sb("/auth/v1/verify",{ method:"POST", body:JSON.stringify({ type:"email", email, token }) })); _writeSession(s); return s; }
    // Password sign-in (GoTrue password grant). Supabase stores only a salted hash, never plaintext.
    async function authPasswordSignIn(email, password){ const s=_mkSession(await _sb("/auth/v1/token?grant_type=password",{ method:"POST", body:JSON.stringify({ email, password }) })); _writeSession(s); return s; }
    // Password sign-up. If email-confirmation is ON, no session is returned (user must confirm);
    // if OFF, a session comes back immediately. Caller handles the "confirm your email" case.
    async function authPasswordSignUp(email, password){ const r=await _sb("/auth/v1/signup",{ method:"POST", body:JSON.stringify({ email, password }) });
      if(r&&r.access_token){ const s=_mkSession(r); _writeSession(s); return { session:s }; } return { needsConfirm:true }; }
    // Magic-link / email-confirmation return: GoTrue redirects back with either an implicit hash
    // (#access_token=…&refresh_token=…) or a ?token_hash=…&type=… (PKCE-less verify). Parse whichever
    // is present on load, establish the session, and scrub the URL so tokens never linger in history.
    async function authSessionFromUrl(){
      try{
        const h=window.location.hash||""; const qs=new URLSearchParams(window.location.search||"");
        if(h.indexOf("access_token=")>-1){ const p=new URLSearchParams(h.replace(/^#/,""));
          const at=p.get("access_token"), rt=p.get("refresh_token");
          if(at&&rt){ const s={ access_token:at, refresh_token:rt, expires_at:(Math.floor(Date.now()/1000))+parseInt(p.get("expires_in")||"3600",10), user:null };
            _writeSession(s); try{ const u=await _sb("/auth/v1/user",{ headers:{ Authorization:"Bearer "+at } }); s.user=u; _writeSession(s); }catch(e){}
            history.replaceState(null,"",window.location.pathname); return s; } }
        const th=qs.get("token_hash"), ty=qs.get("type");
        if(th&&ty){ const s=_mkSession(await _sb("/auth/v1/verify",{ method:"POST", body:JSON.stringify({ token_hash:th, type:ty }) })); _writeSession(s);
          const clean=window.location.pathname; history.replaceState(null,"",clean); return s; }
      }catch(e){ /* leave signed-out on any failure */ }
      return null;
    }
    async function authRefresh(refresh_token){ const s=_mkSession(await _sb("/auth/v1/token?grant_type=refresh_token",{ method:"POST", body:JSON.stringify({ refresh_token }) })); _writeSession(s); return s; }
    async function authSignOut(){ const s=_readSession(); if(s&&s.access_token){ try{ await _sb("/auth/v1/logout",{ method:"POST", headers:{ Authorization:"Bearer "+s.access_token } }); }catch(e){} } _writeSession(null); }
    // Return a valid session, refreshing if the access token is within 2 min of expiry; null if signed out.
    async function authEnsure(){ let s=_readSession(); if(!s||!s.refresh_token) return null;
      if((s.expires_at||0)-(Date.now()/1000)<120){ try{ s=await authRefresh(s.refresh_token); }catch(e){ _writeSession(null); return null; } } return s; }
    // Authenticated PostgREST call (row-level security enforced by the user's bearer token).
    async function dbFetch(path, opts){ const s=await authEnsure(); if(!s) throw new Error("not signed in");
      opts=opts||{};
      const headers=Object.assign({ apikey:SUPABASE.anonKey, Authorization:"Bearer "+s.access_token, "Content-Type":"application/json" }, opts.headers||{});
      const r=await fetch(SUPABASE.url+"/rest/v1"+path, Object.assign({}, opts, {headers}));
      if(!r.ok){ const b=await r.text().catch(()=>""); throw new Error(b||("HTTP "+r.status)); }
      const ct=(r.headers.get("content-type")||""); return ct.includes("json")?r.json():null; }
    // Per-account preferences live in profiles.prefs (jsonb): { a11y:{...}, lang:"en"|"hi" }.
    async function loadPrefs(){ try{ const rows=await dbFetch("/profiles?select=prefs&limit=1"); return (rows&&rows[0]&&rows[0].prefs)||{}; }catch(e){ return {}; } }
    // Read-modify-write so a partial save (just lang, or just a11y) never clobbers the rest.
    async function savePrefsRemote(patch){ try{ const s=await authEnsure(); if(!s) return; const cur=await loadPrefs();
      const next=Object.assign({}, cur, patch);
      await dbFetch("/profiles?id=eq."+s.user.id, { method:"PATCH", headers:{ Prefer:"return=minimal" }, body:JSON.stringify({ prefs:next, updated_at:new Date().toISOString() }) }); }catch(e){} }
    const _uid = () => { const s=_readSession(); return s&&s.user?s.user.id:null; };
    const _sideOf = (story) => { const c=(story&&story.counts)||{}; const L=c.left||0,C=c.center||0,R=c.right||0; if(L+C+R===0) return null; return R>L&&R>=C?"right":(L>=C&&L>=R?"left":"center"); };
    // Reading Lens: record each opened story (upsert refreshes opened_at). Best-effort, never blocks.
    async function recordRead(story){ if(!authOn()||!_uid()||!story) return; try{
      await dbFetch("/reading_history", { method:"POST", headers:{ Prefer:"resolution=merge-duplicates,return=minimal" },
        body:JSON.stringify({ user_id:_uid(), story_id:String(story.id), topic:story.topic||null, side:_sideOf(story), title:(story.headline||story.title||"").slice(0,300), opened_at:new Date().toISOString() }) });
    }catch(e){} }
    async function listReading(days){ const since=new Date(Date.now()-(days||30)*86400000).toISOString();
      return dbFetch("/reading_history?select=story_id,topic,side,title,opened_at&opened_at=gte."+since+"&order=opened_at.desc"); }
    // Saved / clippings.
    async function listSaved(){ return dbFetch("/saved_stories?select=story_id,topic,title,saved_at&order=saved_at.desc"); }
    async function saveStory(story){ return dbFetch("/saved_stories", { method:"POST", headers:{ Prefer:"resolution=merge-duplicates,return=minimal" },
      body:JSON.stringify({ user_id:_uid(), story_id:String(story.id), topic:story.topic||null, title:(story.headline||story.title||"").slice(0,300), saved_at:new Date().toISOString() }) }); }
    async function unsaveStory(id){ return dbFetch("/saved_stories?story_id=eq."+encodeURIComponent(String(id)), { method:"DELETE", headers:{ Prefer:"return=minimal" } }); }

    /* ---------------- accessibility (works on EVERY page, not just Settings) ----------------
       Stored in localStorage so it applies for guests too (news is never gated), and mirrored
       into the account's profile when signed in. Applied as attributes/classes on <html>; the
       real CSS lives in styles.css (text-size zoom, high-contrast overrides, dyslexia font). */
    const A11Y_LS = "paksh-a11y";
    const DEFAULT_A11Y = { textSize:"standard", highContrast:false, dyslexiaFont:false, readAloud:false };
    const readA11y = () => { try{ return Object.assign({}, DEFAULT_A11Y, JSON.parse(localStorage.getItem(A11Y_LS)||"{}")); }catch(e){ return Object.assign({}, DEFAULT_A11Y); } };
    const writeA11y = (p) => { try{ localStorage.setItem(A11Y_LS, JSON.stringify(p)); }catch(e){} };
    const applyA11y = (p) => { try{ const el=document.documentElement;
      el.setAttribute("data-pk-text", p.textSize||"standard");
      el.classList.toggle("pk-hc", !!p.highContrast);
      el.classList.toggle("pk-dys", !!p.dyslexiaFont);
    }catch(e){} };
    // Read a block of text aloud with the browser's speech synthesiser (no network, no library).
    const canSpeak = () => { try{ return typeof window!=="undefined" && "speechSynthesis" in window; }catch(e){ return false; } };
    const speak = (text, lang) => { try{ if(!canSpeak()) return; const sy=window.speechSynthesis; sy.cancel();
      const u=new SpeechSynthesisUtterance(String(text||"")); u.lang=lang==="hi"?"hi-IN":"en-IN"; u.rate=1; sy.speak(u); }catch(e){} };
    const stopSpeak = () => { try{ if(canSpeak()) window.speechSynthesis.cancel(); }catch(e){} };

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
        search:"Search coverage…", tagline:"Compare how India's media covers each story, every side, side by side.",
        topNews:"Top Stories", osTitle:"Coverage Gaps",
        osSub:"A coverage gap is a story that outlets on one side of the spectrum covered while few or none on the other did. Paksh flags these by counting distinct outlets per lean, the same counts as the bias bar, and shows the full Left · Centre · Right tally on each. It's arithmetic, not a judgment about any outlet or about why a story was or wasn't covered. Outlets also differ in how much they publish, so an absence of coverage on one side may reflect an outlet's publishing volume rather than a deliberate omission.",
        gapLeftHead:"Covered more by Left-leaning outlets", gapRightHead:"Covered more by Right-leaning outlets",
        gapShowing:"Showing the {n} most lopsided of {total}", gapCovered:"Covered by",
        m_gapH:"How coverage gaps break down",
        m_gap:"Of the {total} stories Paksh flags as one-sided, {rh} are covered mainly by right-leaning outlets and {lh} mainly by left-leaning. This is not a measure of which side ignores more news. Paksh counts {lo} left-leaning and {ro} right-leaning outlets on India's spectrum, but they publish at very different volumes, the right-leaning set includes several high-volume TV and mass-market outlets, so right-leaning outlets appear about twice as often across all stories. Most of this imbalance reflects that volume difference, not editorial choice.",
        more:"More Top Stories", resultsFor:"Results for", noResults:"No stories match your search.",
        noResultsSub:"Try different keywords or browse top news.", noStories:"No stories to show right now. Please check back soon.",
        seeCoverage:"See coverage", most:"Most coverage", even:"Fairly even coverage", sources:"sources", source:"source",
        onlyLabel:"Only", back:"Back to feed", aiSummary:"Paksh neutral summary", aiSub:"neutral synthesis",
        autoTag:"Auto-summary", autoFrom:"from coverage",
        autoNote:"This headline comes straight from a covering outlet, a neutral Paksh summary is being prepared.",
        unratedTitle:"Unrated outlets", unratedNote:"Outlets we found covering this story but don't rate yet, they add coverage but don't affect the bias bar.",
        intlTitle:"International coverage", intlNote:"Foreign wire services (Reuters, AP, BBC…) covering this story, they add coverage but aren't rated on India's spectrum, so they don't affect the bias bar.",
        framingTitle:"How each side is framing it", framingSub:"A neutral read of what each side's coverage emphasises, based on the headlines collected, not opinion.", framingPending:"The side-by-side framing comparison appears once a full summary is generated for this story.", framingThin:"Not enough unique coverage to create a summary.",
        sideBySide:"Side by Side", coverageBreakdown:"Coverage Breakdown", totalSources:"Total news sources",
        whereLean:"Where the sources lean",
        aiNote:"Lean describes each publisher and is set by Paksh's editors, not generated per story. Summaries are generated automatically from the outlets' own coverage; the counts come from the sources.",
        osCalloutBody1:"Only", osCalloutBody2:"of the covering outlets lean this way, a count of outlets, not a judgment about why a side did or didn't cover it.",
        srcTitle:"Source ratings", srcIntro:"Every outlet Paksh tracks, how it's rated, and why.",
        srcDisclaimer:"All ratings are provisional, a documented starting point reviewed against our rubric, not a final verdict. Lean describes the publication, not any single article, and is open to appeal.",
        filterLean:"Lean", filterLang:"Language", langEN:"English", langHI:"Hindi", all:"All",
        ownership:"Ownership", whyRated:"Why this rating", signals:"Signals", confidence:"confidence",
        contested:"Contested", provisional:"Provisional", suggestFix:"Suggest a correction",
        methodTitle:"How Paksh works", m_doesH:"What Paksh does",
        m_does:"Paksh groups coverage of the same story from outlets across the spectrum, shows a neutral summary, and shows which sides are covering it, so you can see the whole picture and what your usual sources leave out.",
        m_ruleH:"The golden rule",
        m_rule:"A lean label belongs to the publication, not to any single article, and never to an algorithm. Paksh editors assign each outlet a lean using a fixed rubric. The automated summary only describes the coverage; it never decides anyone's politics. A story's bias bar is simple arithmetic: we count how many covering outlets fall on each side. And it is one vote per owner: when two mastheads share a parent company, say The Times of India and Navbharat Times, both Times Group, they count once on their side, so a single company cannot tilt the bar by publishing the same story under several names. We still show every masthead that covered the story; they just share one vote, which is why a story can read “9 publishers · 13 mastheads” on a side.",
        m_aiH:"What the software does, and never does",
        m_ai:"Automation does exactly three things at Paksh, and no more: it groups articles about the same event into one story, writes the neutral summary, and drafts the per-side framing notes from the collected headlines. That is the entire role of the model. It never assigns an outlet's lean, never decides the bias bar, and never weighs one outlet more than another, those are fixed, editor-set labels and plain counts. If the summary engine is momentarily unavailable, a story still publishes with a headline taken straight from a covering outlet, clearly marked as automatic, rather than waiting.",
        m_orderH:"How the home feed is ordered",
        m_order:"The front page is India-first. Stories are ranked by how many distinct outlets across the spectrum are covering them, decayed by how recent they are, so a broadly-covered breaking story leads and yesterday's fades. On top of that arithmetic, the coverage that matters most to an Indian reader, politics and governance, the economy, the courts, big movements and amendments, is given priority over high-volume sport and entertainment, which sit in their own sections. No story is promoted or buried because of its politics; the weighting is a fixed, published rule, not an editorial thumb on the scale for any side.",
        m_freshH:"How current a story is",
        m_fresh:"The time on each story is the real publish time of its newest source article, not when our software last touched it, so “updated 2h ago” means the news itself is about two hours old. Paksh refreshes continuously as new coverage arrives; a story's bar and summary keep updating as more outlets pick it up.",
        m_rateH:"How we rate a publication",
        m_rateLede:"We rate each publication on six signals, each scored from −2 to +2 and combined into one score from −10 (left) to +10 (right):",
        m_rateFoot:"Scores near zero are Centre; the further from zero, the stronger the lean.",
        m_axisH:"What “Left” and “Right” mean in India",
        m_axis:"In India, Left and Right aren't only about economics. Paksh blends a social-and-ideological axis (secular ↔ Hindutva) with an institutional one (critical of ↔ aligned with the incumbent), and tracks economic stance separately. “Left” and “Right” are descriptive, not insults, and the same scrutiny is applied across the spectrum.",
        m_partiesH:"Where India's parties roughly sit",
        m_parties:"These labels describe ideas, not teams, and they're rough, because parties shift over time and many regional parties don't fit neatly on one line. As a common-usage guide: the Left includes communist and socialist parties such as CPI(M) and CPI, and is associated with secular, pro-welfare, labour-first positions; the Right, most prominently the BJP, is associated with Hindutva-influenced cultural nationalism and a more market-friendly economic stance; the Centre spans the middle, where the Congress is often described as centre-left and many regional parties mix positions by issue. Remember: Paksh rates news outlets, not parties, an outlet's lean is about how it covers the news, not who it votes for.",
        m_provH:"Confidence, contested & provisional",
        m_prov:"Every rating today is provisional: a documented starting point based on ownership, self-described stance and well-established reputation, reviewed against the rubric, not a final verdict. Each shows a confidence level, and some are flagged Contested where lean is genuinely debated or ownership recently changed.",
        m_readH:"How to read a Paksh story", m_appealH:"Corrections & appeals",
        m_appeal:"Think a rating is wrong? Tell us the outlet, the rating you dispute, and a few specific examples, headlines or articles, and we'll re-review it against the rubric. Ratings are meant to be challenged.",
        footIndependence:"Paksh is an independent project and is not affiliated with any outlet shown. Lean labels are provisional and open to appeal.",
      },
      hi: {
        navTop:"मुख्य खबरें", navOS:"कवरेज गैप", navSrc:"स्रोत", navMethod:"कार्यप्रणाली",
        search:"कवरेज खोजें…", tagline:"देखिए भारत का मीडिया हर खबर को कैसे कवर करता है, हर पक्ष, आमने-सामने।",
        topNews:"मुख्य खबरें", osTitle:"कवरेज गैप",
        osSub:"कवरेज गैप वह ख़बर है जिसे स्पेक्ट्रम के एक तरफ़ के आउटलेट्स ने कवर किया पर दूसरी तरफ़ के बहुत कम या किसी ने नहीं। पक्ष हर झुकाव के अलग-अलग आउटलेट्स गिनकर इन्हें चिह्नित करता है, वही गिनती जो बायस बार में है, और हर एक पर पूरा वाम · केंद्र · दक्षिण आँकड़ा दिखाता है। यह अंकगणित है, किसी आउटलेट या कवरेज के कारण पर निर्णय नहीं। आउटलेट अलग-अलग मात्रा में प्रकाशित करते हैं, इसलिए एक तरफ़ कवरेज की अनुपस्थिति जानबूझकर की गई चूक के बजाय उस आउटलेट के प्रकाशन-आयतन को दर्शा सकती है।",
        gapLeftHead:"ज़्यादातर वाम-झुकाव आउटलेट्स द्वारा कवर", gapRightHead:"ज़्यादातर दक्षिण-झुकाव आउटलेट्स द्वारा कवर",
        gapShowing:"{total} में से {n} सबसे असंतुलित दिखाई जा रही हैं", gapCovered:"कवर किया गया:",
        m_gapH:"कवरेज गैप का ब्यौरा",
        m_gap:"पक्ष जिन {total} ख़बरों को एकतरफ़ा चिह्नित करता है, उनमें से {rh} ज़्यादातर दक्षिण-झुकाव आउटलेट्स ने और {lh} ज़्यादातर वाम-झुकाव आउटलेट्स ने कवर कीं। यह इस बात का माप नहीं है कि कौन-सा पक्ष ज़्यादा ख़बरें अनदेखा करता है। पक्ष भारत के स्पेक्ट्रम पर {lo} वाम-झुकाव और {ro} दक्षिण-झुकाव आउटलेट गिनता है, पर वे बहुत अलग मात्रा में प्रकाशित करते हैं, दक्षिण-झुकाव समूह में कई उच्च-आयतन टीवी और मास-मार्केट आउटलेट हैं, इसलिए दक्षिण-झुकाव आउटलेट सभी ख़बरों में लगभग दोगुनी बार दिखते हैं। इस असंतुलन का ज़्यादातर हिस्सा उस आयतन-अंतर को दर्शाता है, संपादकीय चयन को नहीं।",
        more:"और मुख्य खबरें", resultsFor:"खोज परिणाम:", noResults:"आपकी खोज से मेल खाती कोई खबर नहीं।",
        noResultsSub:"अलग शब्द आज़माएँ या मुख्य खबरें देखें।", noStories:"अभी दिखाने के लिए कोई खबर नहीं है। कृपया थोड़ी देर बाद देखें।",
        seeCoverage:"कवरेज देखें", most:"सबसे ज़्यादा कवरेज", even:"लगभग बराबर कवरेज", sources:"स्रोत", source:"स्रोत",
        onlyLabel:"केवल", back:"फ़ीड पर वापस", aiSummary:"पक्ष तटस्थ सारांश", aiSub:"तटस्थ संश्लेषण",
        autoTag:"स्वतः सारांश", autoFrom:"कवरेज से",
        autoNote:"यह शीर्षक सीधे कवरेज करने वाले एक आउटलेट से लिया गया है, पक्ष का तटस्थ सारांश तैयार किया जा रहा है।",
        unratedTitle:"बिना रेटिंग वाले आउटलेट", unratedNote:"ऐसे आउटलेट जो इस ख़बर को कवर कर रहे हैं पर अभी रेटेड नहीं हैं, ये कवरेज जोड़ते हैं पर बायस बार को प्रभावित नहीं करते।",
        intlTitle:"अंतरराष्ट्रीय कवरेज", intlNote:"इस ख़बर को कवर करने वाली विदेशी समाचार एजेंसियाँ (Reuters, AP, BBC…), ये कवरेज जोड़ती हैं पर भारत के स्पेक्ट्रम पर रेटेड नहीं हैं, इसलिए बायस बार को प्रभावित नहीं करतीं।",
        framingTitle:"हर पक्ष इसे कैसे पेश कर रहा है", framingSub:"हर झुकाव की कवरेज किस बात पर ज़ोर दे रही है, इसका तटस्थ विश्लेषण, एकत्र की गई हेडलाइनों के आधार पर, राय नहीं।", framingPending:"इस ख़बर का पूरा सारांश तैयार होने पर पक्षों की तुलना यहाँ दिखाई देगी।", framingThin:"सारांश बनाने के लिए पर्याप्त स्वतंत्र कवरेज नहीं।",
        sideBySide:"आमने-सामने", coverageBreakdown:"कवरेज का ब्यौरा", totalSources:"कुल समाचार स्रोत",
        whereLean:"स्रोत किस ओर झुके हैं",
        aiNote:"झुकाव हर प्रकाशक का वर्णन करता है और पक्ष के संपादक तय करते हैं, हर खबर के लिए नहीं। सारांश आउटलेट्स की अपनी कवरेज से स्वचालित रूप से तैयार होते हैं; आँकड़े स्रोतों से आते हैं।",
        osCalloutBody1:"केवल", osCalloutBody2:"कवर करने वाले आउटलेट इस ओर झुके हैं, यह आउटलेट्स की गिनती है, इस बारे में निर्णय नहीं कि किसी पक्ष ने इसे क्यों कवर किया या नहीं।",
        srcTitle:"स्रोत रेटिंग", srcIntro:"पक्ष जिन आउटलेट्स को ट्रैक करता है, उनकी रेटिंग और कारण।",
        srcDisclaimer:"सभी रेटिंग अस्थायी हैं, रूब्रिक के विरुद्ध समीक्षित एक प्रलेखित शुरुआती बिंदु, अंतिम फ़ैसला नहीं। झुकाव प्रकाशन का वर्णन करता है, किसी एक लेख का नहीं, और अपील के लिए खुला है।",
        filterLean:"झुकाव", filterLang:"भाषा", langEN:"अंग्रेज़ी", langHI:"हिंदी", all:"सभी",
        ownership:"स्वामित्व", whyRated:"यह रेटिंग क्यों", signals:"संकेत", confidence:"विश्वास",
        contested:"विवादित", provisional:"अस्थायी", suggestFix:"सुधार सुझाएँ",
        methodTitle:"पक्ष कैसे काम करता है", m_doesH:"पक्ष क्या करता है",
        m_does:"पक्ष एक ही खबर की कवरेज को पूरे स्पेक्ट्रम के आउटलेट्स से इकट्ठा करता है, एक तटस्थ सारांश दिखाता है, और दिखाता है कि कौन-कौन से पक्ष इसे कवर कर रहे हैं, ताकि आप पूरी तस्वीर देख सकें और जान सकें कि आपके सामान्य स्रोत क्या छोड़ देते हैं।",
        m_ruleH:"मूल नियम",
        m_rule:"झुकाव का लेबल प्रकाशन का होता है, किसी एक लेख का नहीं, और कभी किसी एल्गोरिद्म का नहीं। पक्ष के संपादक एक निश्चित रूब्रिक से हर आउटलेट को झुकाव देते हैं। स्वचालित सारांश केवल कवरेज का वर्णन करता है; वह किसी की राजनीति तय नहीं करता। किसी खबर का बायस बार सीधा गणित है: हम गिनते हैं कि कवर करने वाले कितने आउटलेट किस ओर हैं। और यह एक-स्वामी-एक-वोट है: जब दो आउटलेट एक ही मूल कंपनी के हों, जैसे The Times of India और Navbharat Times, दोनों Times Group, तो वे अपने पक्ष में एक ही बार गिने जाते हैं, ताकि कोई एक कंपनी कई नामों से एक ही खबर छापकर बायस बार को झुका न सके। कवर करने वाला हर आउटलेट फिर भी दिखाया जाता है; बस उनका वोट एक साझा होता है, इसीलिए किसी पक्ष पर खबर “9 प्रकाशक · 13 मास्टहेड” पढ़ सकती है।",
        m_aiH:"सॉफ़्टवेयर क्या करता है, और क्या कभी नहीं करता",
        m_ai:"पक्ष पर स्वचालन ठीक तीन काम करता है, इससे ज़्यादा नहीं: एक ही घटना के लेखों को एक खबर में समूहित करना, तटस्थ सारांश लिखना, और एकत्र हेडलाइनों से हर पक्ष के फ़्रेमिंग नोट तैयार करना। मॉडल की भूमिका बस इतनी है। यह किसी आउटलेट का झुकाव तय नहीं करता, बायस बार तय नहीं करता, और किसी आउटलेट को दूसरे से ज़्यादा भार नहीं देता, वे निश्चित, संपादक-निर्धारित लेबल और सीधी गिनती हैं। यदि सारांश इंजन कुछ देर के लिए उपलब्ध न हो, तो खबर फिर भी एक कवर करने वाले आउटलेट से लिया गया शीर्षक (स्पष्ट रूप से स्वतः चिह्नित) के साथ प्रकाशित होती है, प्रतीक्षा नहीं करती।",
        m_orderH:"मुख्य फ़ीड किस क्रम में सजती है",
        m_order:"मुख्य पृष्ठ भारत-पहले है। खबरों को इस आधार पर क्रम दिया जाता है कि स्पेक्ट्रम भर के कितने अलग-अलग आउटलेट उन्हें कवर कर रहे हैं, और वे कितनी हाल की हैं, ताकि व्यापक रूप से कवर की गई ताज़ा खबर आगे रहे और पुरानी पीछे चली जाए। इस अंकगणित के ऊपर, भारतीय पाठक के लिए सबसे मायने रखने वाली कवरेज, राजनीति और शासन, अर्थव्यवस्था, अदालतें, बड़े आंदोलन और संशोधन, को उच्च-आयतन खेल और मनोरंजन से पहले प्राथमिकता दी जाती है, जो अपने अलग सेक्शन में रहते हैं। किसी खबर को उसकी राजनीति के कारण न आगे बढ़ाया जाता है न दबाया जाता है; यह भार एक निश्चित, प्रकाशित नियम है, किसी पक्ष के लिए संपादकीय पक्षपात नहीं।",
        m_freshH:"कोई खबर कितनी ताज़ा है",
        m_fresh:"हर खबर पर दिखने वाला समय उसमें शामिल सबसे नए स्रोत-लेख का वास्तविक प्रकाशन समय है, न कि जब हमारे सॉफ़्टवेयर ने उसे आख़िरी बार छुआ, इसलिए “2 घंटे पहले अपडेट” का अर्थ है कि खबर स्वयं लगभग दो घंटे पुरानी है। जैसे-जैसे नई कवरेज आती है पक्ष लगातार ताज़ा होता रहता है; जैसे-जैसे और आउटलेट इसे उठाते हैं, खबर का बार और सारांश अपडेट होते रहते हैं।",
        m_rateH:"हम किसी प्रकाशन को कैसे आँकते हैं",
        m_rateLede:"हम हर प्रकाशन को छह संकेतों पर आँकते हैं, हर एक को −2 से +2 तक अंक देकर एक स्कोर में जोड़ा जाता है, −10 (वाम) से +10 (दक्षिण):",
        m_rateFoot:"शून्य के पास के स्कोर केंद्र हैं; शून्य से जितना दूर, झुकाव उतना मज़बूत।",
        m_axisH:"भारत में “वाम” और “दक्षिण” का अर्थ",
        m_axis:"भारत में वाम और दक्षिण केवल अर्थशास्त्र के बारे में नहीं हैं। पक्ष एक सामाजिक-वैचारिक अक्ष (धर्मनिरपेक्ष ↔ हिंदुत्व) को एक संस्थागत अक्ष (सत्ता के आलोचक ↔ सत्ता के साथ) के साथ जोड़ता है, और आर्थिक रुख को अलग से देखता है। “वाम” और “दक्षिण” वर्णनात्मक हैं, अपमान नहीं, और एक ही कसौटी पूरे स्पेक्ट्रम पर लागू होती है।",
        m_partiesH:"भारत की पार्टियाँ मोटे तौर पर कहाँ हैं",
        m_parties:"ये लेबल विचारों का वर्णन करते हैं, टीमों का नहीं, और ये मोटे अनुमान हैं, क्योंकि पार्टियाँ समय के साथ बदलती हैं और कई क्षेत्रीय पार्टियाँ किसी एक रेखा पर ठीक से नहीं बैठतीं। आम समझ के अनुसार: वाम में CPI(M) और CPI जैसी कम्युनिस्ट और समाजवादी पार्टियाँ आती हैं, जो धर्मनिरपेक्ष और कल्याण-समर्थक, श्रमिक-पहले रुख से जुड़ी हैं; दक्षिण, सबसे प्रमुख रूप से भाजपा, हिंदुत्व-प्रभावित सांस्कृतिक राष्ट्रवाद और अधिक बाज़ार-समर्थक आर्थिक रुख से जुड़ी है; केंद्र बीच में फैला है, जहाँ कांग्रेस को अक्सर केंद्र-वाम कहा जाता है और कई क्षेत्रीय पार्टियाँ मुद्दे के हिसाब से रुख मिलाती हैं। याद रखें: पक्ष समाचार आउटलेट्स को आँकता है, पार्टियों को नहीं, किसी आउटलेट का झुकाव इस बारे में है कि वह खबरों को कैसे कवर करता है, इस बारे में नहीं कि वह किसे वोट देता है।",
        m_provH:"विश्वास, विवादित और अस्थायी",
        m_prov:"आज हर रेटिंग अस्थायी है: स्वामित्व, स्व-घोषित रुख और स्थापित प्रतिष्ठा पर आधारित एक प्रलेखित शुरुआती बिंदु, रूब्रिक के विरुद्ध समीक्षित, अंतिम फ़ैसला नहीं। हर एक के साथ एक विश्वास-स्तर दिखता है, और कुछ को ‘विवादित’ चिह्नित किया गया है जहाँ झुकाव सचमुच बहस में है या स्वामित्व हाल में बदला है।",
        m_readH:"पक्ष की खबर कैसे पढ़ें", m_appealH:"सुधार और अपील",
        m_appeal:"लगता है कोई रेटिंग ग़लत है? हमें आउटलेट, जिस रेटिंग से असहमत हैं, और कुछ ठोस उदाहरण, हेडलाइन या लेख, बताएँ, और हम उसे रूब्रिक के विरुद्ध फिर से देखेंगे। रेटिंग्स को चुनौती देने के लिए ही हैं।",
        footIndependence:"पक्ष एक स्वतंत्र परियोजना है और किसी दिखाए गए आउटलेट से संबद्ध नहीं है। झुकाव के लेबल अस्थायी हैं और अपील के लिए खुले हैं।",
      }
    };

    /* ---------------- analytics (consent-gated, cookieless) ---------------- */
    // Vercel Web Analytics via its SCRIPT-TAG integration (not the npm/@vercel/analytics
    // package, which needs a bundler Paksh deliberately doesn't have). It's cookieless, does
    // no cross-site fingerprinting, and is aggregate - the privacy-first posture we chose.
    // NOTHING loads or fires until the visitor accepts in the consent banner.
    const consentState = () => { try { return localStorage.getItem("paksh-consent") || ""; } catch(e){ return ""; } };  // "" | "granted" | "denied"
    const loadVercelAnalytics = () => {
      if (window.__pakshVA || consentState()!=="granted") return;
      window.__pakshVA = true;
      window.va = window.va || function(){ (window.vaq = window.vaq || []).push(arguments); };
      const s = document.createElement("script"); s.defer = true; s.src = "/_vercel/insights/script.js";
      document.head.appendChild(s);
    };
    // track(name, props) - a no-op unless the user consented. Send only low-cardinality,
    // non-identifying props (topic, side, device class) - NEVER the search query text, a URL,
    // or anything that could single out a person. This is the one place events are emitted.
    const track = (name, props) => {
      try {
        if (consentState()!=="granted" || typeof window.va!=="function") return;
        window.va("event", { name, ...(props||{}) });
      } catch(e){}
    };
    const deviceClass = () => { try { const w=window.innerWidth||0; return w<768?"mobile":(w<1024?"tablet":"desktop"); } catch(e){ return "unknown"; } };

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
        // Storylines are derived + secondary — load them best-effort so a failure never blocks the feed.
        let storylines=[]; try{ const st=await apiGet("storylines"); storylines=st.storylines||[]; }catch(_){}
        return {events:e.events||[], blindspots:b.events||[], gaps:{left:b.left_heavier||[], right:b.right_heavier||[], agg:b.aggregate||{}}, topics:tp.topics||[], sources:sr.sources||[], summary:sr.summary||{}, storylines:storylines}; }
      catch(err){ console.error(err); return {events:[],blindspots:[],gaps:{left:[],right:[],agg:{}},topics:[],sources:[],summary:{},storylines:[]}; }
    }

    const toCard = (e, lang) => {
      const lc = e.lean_counts || {left:0,center:0,right:0};
      // created_at on the CARD is the real article publish time (published_at) when we have
      // it, so "x ago" reflects when the news happened, not when our pipeline touched it.
      // Falls back to the pipeline created_at for events analysed before published_at existed.
      return { id:e.id, topic:e.topic, region:e.region||"India", srclang:e.lang||"en", created_at:(e.published_at||e.created_at),
        headline:(lang==="hi"&&e.title_hi)?e.title_hi:e.title,
        lead:(lang==="hi"&&e.summary_hi)?e.summary_hi:e.summary,
        summary:(lang==="hi"&&e.summary_points_hi&&e.summary_points_hi.length)?e.summary_points_hi:(e.summary_points||[]),
        bias:biasPct(lc), counts:lc, sources:(lc.left+lc.center+lc.right)||e.total_sources||0,
        international:(e.international||0),
        importance:(typeof e.importance==="number"?e.importance:0),
        feed_rank:(typeof e.feed_rank==="number"?e.feed_rank:(typeof e.importance==="number"?e.importance:0)),
        unrated:Math.max(0,(e.source_count||0)-(lc.left+lc.center+lc.right)-(e.international||0)),
        blindspot:e.blindspot?e.blindspot.side:null,
        auto:e.summary_method==="extractive",
        storyline_id:e.storyline_id||null,
        img:e.image_url||"",
        image:e.image_url||imgFor(hueOf(e.topic||e.title)) };
    };
    // Keep each language view free of the OTHER language's script. The summary
    // engine occasionally writes a framing note in the wrong language; this drops
    // any bullet whose script doesn't match the active language, so the English
    // view never shows Devanagari (and vice-versa). A side left empty just shows
    // the usual "not enough unique coverage" note.
    const _DEV=/[ऀ-ॿ]/;
    const framingFor=(e,lang)=>{
      const src=(lang==="hi"&&e.framing_hi&&Object.keys(e.framing_hi).length)?e.framing_hi:(e.framing||{});
      const wantHi=lang==="hi"; const out={};
      Object.keys(src||{}).forEach(k=>{
        const arr=Array.isArray(src[k])?src[k]:(src[k]?[src[k]]:[]);
        out[k]=arr.filter(s=>typeof s==="string"&&s.trim()&&(wantHi?_DEV.test(s):!_DEV.test(s)));
      });
      return out;
    };
    const toDetail = (e, lang) => { const c=toCard(e,lang);
      c.coverage=e.coverage||{}; c.outlets=e.sources||[];
      c.framing=framingFor(e,lang);
      c.storyline=e.storyline||null;   // the saga thread this story belongs to (from the per-story JSON)
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
    const Bookmark=(p)=><svg width={p.size||24} height={p.size||24} className={p.className||""} viewBox="0 0 24 24" fill={p.fill||"none"} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>;
    const User=(p)=><svg width={p.size||24} height={p.size||24} className={p.className||""} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21a8 8 0 0 0-16 0"/><circle cx="12" cy="7" r="4"/></svg>;
    const Help=(p)=><svg width={p.size||24} height={p.size||24} className={p.className||""} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/></svg>;

    /* ---------------- helpers ---------------- */
    const _ts=(iso)=>{ if(!iso) return NaN; let x=(""+iso).replace(" ","T"); if(!/[zZ]|[+\-]\d\d:?\d\d$/.test(x)) x+="Z"; return Date.parse(x); };
    const timeAgo=(iso,lang)=>{ const ts=_ts(iso); if(isNaN(ts)) return ""; const m=Math.max(0,(Date.now()-ts)/60000); const hi=lang==="hi";
      if(m<60) return hi?`${Math.round(m)} मिनट पहले`:`${Math.round(m)}m ago`;
      const h=m/60; if(h<24) return hi?`${Math.round(h)} घंटे पहले`:`${Math.round(h)}h ago`;
      const d=Math.round(h/24); return hi?`${d} दिन पहले`:`${d}d ago`; };
    // Absolute publish date+time, e.g. "6 Aug 2026, 2:14 PM" (en) / Devanagari locale (hi).
    // Shown ALONGSIDE the relative "x ago" so the timestamp is unambiguous on a story page.
    const absDate=(iso,lang)=>{ const ts=_ts(iso); if(isNaN(ts)) return ""; try{ return new Date(ts).toLocaleString(lang==="hi"?"hi-IN":"en-IN",{day:"numeric",month:"short",year:"numeric",hour:"numeric",minute:"2-digit"}); }catch(e){ return ""; } };
    const domSide=(bias)=>["left","center","right"].reduce((a,b)=>(bias[b]||0)>(bias[a]||0)?b:a,"left");
    const tword=(lang)=> (n)=> n===1?STR[lang].source:STR[lang].sources;
    const covLine=(story,lang)=>{ const d=domSide(story.bias); const tot=story.sources+(story.unrated||0)+(story.international||0); return `${story.bias[d]}% ${lbl(d,lang)} · ${tot} ${tot===1?STR[lang].source:STR[lang].sources}`; };
    // Newspaper count line: raw distinct-outlet counts L · C · R, plus n and age. Reads
    // straight from the real per-lean counts (never a hardcoded ratio).
    // Newspaper count caption with L/C/R labels (design card): "L 4 · C 9 · R 3 · n=16".
    // Hindi uses वा/कें/द short marks. Reads straight from the real per-lean owner counts.
    const countLine=(story,lang)=>{ const c=story.counts||{}; const L=c.left||0,C=c.center||0,R=c.right||0; const n=L+C+R; const ta=timeAgo(story.created_at,lang);
      const lab=lang==="hi"?["वा","कें","द"]:["L","C","R"]; return `${lab[0]} ${L} · ${lab[1]} ${C} · ${lab[2]} ${R} · n=${n}${ta?" · "+ta:""}`; };

    function Thumb({ src, topic, title, ratio, t, lang, className }) {
      const [err,setErr]=useState(false);
      const real=src && !err;
      const tp=lang==="hi"?(TOPIC_HI[topic]||topic):(topic||"News");
      return (
        <div className={`relative overflow-hidden ${t.soft} ${className||""}`} style={{aspectRatio:ratio||"16 / 9"}}>
          {real
            ? <img src={src} alt="" loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={()=>setErr(true)} className="absolute inset-0 h-full w-full object-cover" />
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
      return <span className="grid shrink-0 place-items-center rounded-md bg-white" style={{width:s,height:s,boxShadow:`0 0 0 1.5px ${ring}`}}><img src={`https://www.google.com/s2/favicons?domain=${host}&sz=64`} alt="" width={s*0.62} height={s*0.62} loading="lazy" referrerPolicy="no-referrer" onError={()=>setErr(true)} className="object-contain"/></span>;
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
                    className={`${BIAS[k].tex} pk-seg cursor-pointer hover:brightness-110 ${active&&active!==k?"opacity-40":""}`}
                    style={{flexGrow:bias[k],flexBasis:0,minWidth:2,border:0,padding:0}}/>
                : <div className={`${BIAS[k].tex} pk-seg`} style={{flexGrow:bias[k],flexBasis:0,minWidth:2}}/>}
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
    // Blindspot / Coverage-Gap badge — bordered clay pill with a dot (design mobile card). `side`
    // is the UNDER-covered side; shown as "COVERAGE GAP · {SIDE}" when a side is known.
    function BlindspotBadge({ side, t, lang }) {
      const sideLab=side&&BIAS[side]?lbl(side,lang):"";
      return (
        <span className={`inline-flex items-center gap-1.5 mono text-[9px] font-bold uppercase tracking-[0.12em] ${t.blind} ${t.blindSoft} ${lang==="hi"?"deva":""}`} style={{padding:"2px 6px",border:"1px solid #E0CBB9"}}>
          <span style={{width:5,height:5,borderRadius:9,background:"#75442E",display:"inline-block"}}/>
          {STR[lang].navOS}{sideLab?` · ${sideLab}`:""}
        </span>
      );
    }
    function Eyebrow({ topic, created_at, blindspot, storyline, t, lang }) {
      const tp=lang==="hi"?(TOPIC_HI[topic]||topic):topic; const face=lang==="hi"?"deva":"mono";
      return (
        <div className={`flex flex-wrap items-center gap-x-2 gap-y-1.5 ${face} text-[11px] font-medium uppercase tracking-[0.1em]`}>
          {blindspot && <BlindspotBadge side={blindspot} t={t} lang={lang} />}
          {storyline && <DevelopingChip t={t} lang={lang} />}
          <span className={t.ts}>{tp||"News"}</span>
          {created_at && <><span className={t.tf}>·</span><span className={t.tf}>{timeAgo(created_at,lang)}</span></>}
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
    // BREAKING TICKER — the dark "DEVELOPING" strip above the masthead (design mobile prototype):
    // a pulsing dot + "DEVELOPING" label, then the freshest headlines cycling. Pure display of
    // real, recent headlines; no new data, no ranking change.
    function BreakingTicker({ cards, t, lang, open }) {
      const items=(cards||[]).slice(0,12).filter(c=>c.headline);
      if(!items.length) return null;
      const seq=items.concat(items);   // duplicated so the -50% keyframe loops seamlessly
      return (
        <div style={{background:"#15140F"}} className="overflow-hidden">
          <div className="mx-auto flex max-w-[1280px] items-center gap-3 px-4 sm:px-10" style={{height:30}}>
            <span className="flex shrink-0 items-center gap-1.5" style={{zIndex:1}}>
              <span className="pk-pulse" style={{width:6,height:6,borderRadius:9,background:"#C0392B",display:"inline-block"}}/>
              <span className="mono" style={{fontSize:9.5,fontWeight:700,letterSpacing:".18em",color:"#C89170"}}>{lang==="hi"?"ताज़ा ख़बर":"DEVELOPING"}</span>
            </span>
            <div className="relative min-w-0 flex-1 overflow-hidden" style={{height:30}}>
              <div className="pk-marquee flex items-center whitespace-nowrap" style={{position:"absolute",top:0,height:30,willChange:"transform"}}>
                {seq.map((c,i)=>(
                  <a key={i} href={"/story/"+encodeURIComponent(c.id)} onClick={e=>{ if(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return; e.preventDefault(); open&&open(c.id); }} className={`no-underline ${readCls(lang)}`} style={{color:"rgba(244,241,234,.9)",fontSize:12.5,marginRight:26,display:"inline-flex",alignItems:"center"}} aria-hidden={i>=items.length?"true":undefined} tabIndex={i>=items.length?-1:undefined}>
                    <span style={{color:"#C89170",marginRight:11}}>•</span>{c.headline}
                  </a>
                ))}
              </div>
            </div>
          </div>
        </div>
      );
    }
    // A dated masthead sub-strip: today's date + how many outlets Paksh tracks.
    // The dated strip under the masthead: a 2px rule over a 1px rule (design 2a), carrying
    // the edition toggle + today's date on the left, the live tally in the centre, and the
    // freshness on the right. Every number is real (homeCards / sources / gaps / newest event).
    function DateStrip({ t, lang, stats, regionFilter, setRegionFilter }) {
      const today=new Date().toLocaleDateString(lang==="hi"?"hi-IN":"en-IN",{weekday:"long",year:"numeric",month:"long",day:"numeric"});
      const ls=lang==="hi"?0:".14em";
      const eb=`eyebrow ${lang==="hi"?"deva":""}`;
      const region=(k,label)=>(
        <button onClick={()=>setRegionFilter&&setRegionFilter(k)} className={`${eb} ${regionFilter===k?t.tp:`${t.tf} hover:${t.tp}`}`} style={{letterSpacing:ls}}>{label}</button>
      );
      const tally=lang==="hi"
        ? `${stats.stories} ख़बरें · ${stats.outlets} स्रोत · ${stats.gaps} कवरेज गैप`
        : `${stats.stories} stories · ${stats.outlets} outlets tracked · ${stats.gaps} coverage gaps`;
      return (
        <div className="flex items-center justify-between gap-4 py-[7px]" style={{borderBottom:`1px solid ${t.ink}`}}>
          <div className="flex items-center gap-3 sm:gap-4 min-w-0">
            {region("National", ui("National",lang))}
            {region("International", ui("International",lang))}
            <span className={`hidden md:inline ${eb} ${t.tf}`} style={{letterSpacing:ls}}>{today}</span>
          </div>
          <span className={`hidden sm:inline ${eb} ${t.tf} truncate`} style={{letterSpacing:ls}}>{tally}</span>
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
          <div className="flex items-baseline justify-between gap-3">
            <div className={`eyebrow accent-clay ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{lang==="hi"?"आज सबसे ज़्यादा कवरेज":"Most covered today"}{tp?` · ${tp}`:""}</div>
            {n>0 && <span className={`shrink-0 mono text-[10.5px] ${t.tf} ${lang==="hi"?"deva":""}`}>{n} {n===1?STR[lang].source:STR[lang].sources}</span>}
          </div>
          <h2 className={`headline pk-rise mt-3 text-[36px] sm:text-[44px] lg:text-[54px] ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-4`} style={{lineHeight:lang==="hi"?1.12:1.04,letterSpacing:lang==="hi"?0:"-0.024em",textWrap:"balance"}}>{story.headline}</h2>
          {story.img && <div className="mt-4 overflow-hidden"><Thumb src={story.img} topic={story.topic} title={story.headline} ratio="2 / 1" t={t} lang={lang} /></div>}
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
          <Eyebrow topic={story.topic} created_at={story.created_at} blindspot={story.blindspot} storyline={story.storyline_id} t={t} lang={lang} />
          <h3 className={`headline mt-1.5 text-[20px] sm:text-[21px] leading-[1.24] lc-2 ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`}>{story.headline}</h3>
          {story.lead && <p className={`mt-2 text-[14px] leading-[1.55] lc-2 ${t.ts} ${readCls(lang)}`}>{story.lead}</p>}
          <div className="mt-3"><BiasBar bias={story.bias} t={t} lang={lang} height={11} /></div>
          <div className="mt-1.5 flex items-center justify-between gap-3">
            <span className={`mono text-[11px] ${t.tf} ${lang==="hi"?"deva":""}`}>{countLine(story,lang)}</span>
            <CardClip story={story} t={t} lang={lang} />
          </div>
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
            <Eyebrow topic={story.topic} created_at={story.created_at} blindspot={story.blindspot} storyline={story.storyline_id} t={t} lang={lang} />
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
            <Eyebrow topic={story.topic} created_at={story.created_at} blindspot={story.blindspot} storyline={story.storyline_id} t={t} lang={lang} />
            <h3 className={`headline mt-1.5 text-[17px] leading-[1.2] lc-3 ${t.tp} ${readCls(lang)}`}>{story.headline}</h3>
            <div className="mt-3"><MiniBar bias={story.bias} t={t} /></div>
            <div className="mt-2 flex items-center justify-between gap-3">
              <span className={`mono text-[11px] ${t.tf} ${lang==="hi"?"deva":""}`}>{covLine(story,lang)}</span>
              <CardClip story={story} t={t} lang={lang} />
            </div>
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
    // Masthead — recreated from the desktop prototype: a dateline strip, a CENTRED पक्ष Paksh
    // wordmark flanked by ♥ Support (left) and Sign-in / avatar (right), then a bordered nav row
    // with a right-aligned search. Theme-aware (token colours) and responsive (nav row is md+;
    // mobile leans on the bottom tab bar). Clay (#75442E) via t.blind so it lifts in dark mode.
    function Header({ t, lang, setLang, dark, setDark, go, view, auth, openHelp, savedCount }) {
      const NAV=[["home",STR[lang].navTop,false],["blindspot",STR[lang].navOS,true],["search",ui("searchTab",lang),false],
        ["topics",ui("sections",lang),false],["sources",STR[lang].navSrc,false],["about",STR[lang].navMethod,false]];
      const initials=(email)=>{ const s=(email||"").trim(); return s?s[0].toUpperCase():"?"; };
      const today=new Date().toLocaleDateString(lang==="hi"?"hi-IN":"en-IN",{weekday:"long",year:"numeric",month:"long",day:"numeric"});
      return (
        <header className={`sticky top-0 z-40 ${t.nav}`} style={{borderBottom:`1px solid ${t.ink}`}}>
          <div className="mx-auto max-w-[1280px]">
            {/* dateline strip */}
            <div className={`flex items-center justify-between gap-3 border-b px-4 py-2 sm:px-7 ${t.border}`}>
              <span className={`mono truncate text-[10px] ${t.tf} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".06em"}}>{today}</span>
              <div className="flex shrink-0 items-center gap-3">
                <span className={`hidden md:inline mono text-[10px] uppercase ${t.tf} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{lang==="hi"?"हर पक्ष, हर खबर":"Every side of the story"}</span>
                <LangToggle t={t} lang={lang} setLang={setLang} dark={dark} />
                <button onClick={()=>setDark(!dark)} className={`${t.tf} hover:${t.tp}`} aria-label="Theme">{dark?<Sun size={15}/>:<Moon size={15}/>}</button>
                {openHelp && <button onClick={openHelp} className={`hidden sm:inline ${t.tf} hover:${t.tp}`} aria-label={lang==="hi"?"पक्ष कैसे पढ़ें":"How Paksh works"}><Help size={15}/></button>}
              </div>
            </div>
            {/* wordmark row: Support · wordmark · Sign in / account */}
            <div className="grid grid-cols-[1fr_auto_1fr] items-center px-4 py-3 sm:px-7">
              <div className="flex items-center">
                <button onClick={()=>go("support")} className={`inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase ${t.blind}`} style={{border:"1px solid currentColor",padding:"7px 11px",letterSpacing:lang==="hi"?0:".06em"}} aria-label={lang==="hi"?"सहयोग":"Support"}><span aria-hidden="true">♥</span><span className={`hidden sm:inline ${lang==="hi"?"deva":""}`}>{lang==="hi"?"सहयोग":"Support"}</span></button>
              </div>
              <button onClick={()=>go("home")} className="flex items-baseline justify-center" aria-label="Paksh home">
                <span className={`brand-hi leading-none ${t.tp}`} style={{fontSize:30}}>पक्ष</span>
              </button>
              <div className="flex items-center justify-end gap-2.5">
                {authOn() && auth && <button onClick={()=>go("lens")} className={`hidden lg:inline text-[11px] font-medium ${view==="lens"?t.tp:`${t.ts} hover:${t.tp}`} ${lang==="hi"?"deva":""}`}>{lang==="hi"?"मेरा रीडिंग लेंस":"My Reading Lens"}</button>}
                {authOn() && auth && <button onClick={()=>go("saved")} aria-label={lang==="hi"?"सहेजी खबरें":"Saved"} className={`inline-flex items-center gap-1 mono text-[12px] ${view==="saved"?t.tp:`${t.tf} hover:${t.tp}`}`}><span aria-hidden="true">✂</span>{savedCount||0}</button>}
                {authOn() && (auth
                  ? <button onClick={()=>go("account")} aria-label={lang==="hi"?"मेरा खाता":"My account"} title={(auth.user&&auth.user.email)||""} className={`grid place-items-center text-[13px] font-semibold ${t.tp} ${t.soft}`} style={{width:34,height:34,border:`1px solid ${t.ink}`,fontFamily:"'Source Serif 4',Georgia,serif"}}>{initials(auth.user&&auth.user.email)}</button>
                  : <button onClick={()=>go("login")} className={`text-[10px] font-semibold uppercase ${t.ts} hover:${t.tp} ${lang==="hi"?"deva":""}`} style={{border:`1px solid ${t.ink}`,padding:"9px 13px",letterSpacing:lang==="hi"?0:".05em"}}>{lang==="hi"?"साइन इन":"Sign in"}</button>)}
              </div>
            </div>
            {/* nav row (desktop) */}
            <nav className={`hidden items-stretch md:flex ${t.surface}`} style={{borderTop:`1px solid ${t.ink}`}}>
              {NAV.map(([k,label,clay])=>(
                <button key={k} onClick={()=>go(k)} className={`relative text-[11px] font-semibold uppercase hover:${t.tp} ${view===k?t.tp:(clay?t.blind:t.ts)} ${lang==="hi"?"deva":""}`} style={{padding:"11px 20px",borderRight:`1px solid ${t.line}`,letterSpacing:lang==="hi"?0:".04em"}}>
                  {label}{view===k && <span style={{position:"absolute",left:0,right:0,bottom:-1,height:2,background:t.ink}}/>}
                </button>
              ))}
              <button onClick={()=>go("search")} className={`ml-auto flex items-center gap-2 ${t.tf} hover:${t.tp}`} style={{padding:"0 18px",borderLeft:`1px solid ${t.line}`}} aria-label="Search"><Search size={14}/><span className={`hidden lg:inline text-[12px] ${readCls(lang)}`}>{STR[lang].search}</span></button>
            </nav>
          </div>
        </header>
      );
    }
    function BottomNav({ t, lang, view, go, auth }) {
      // Front · Gaps · Search · Sections — same drawer whether signed in or not.
      // Login lives ONLY in the top-right; Saved sits behind the account button there.
      const items=[["home",lang==="hi"?"मुख":"Front",Home],["blindspot",lang==="hi"?"गैप":"Gaps",Eye],["search",ui("searchTab",lang),Search],
        ["topics", ui("sections",lang), Grid]];
      const active=(k)=>view===k;
      return (
        <nav className={`fixed inset-x-0 bottom-0 z-40 border-t md:hidden ${t.border} ${t.nav}`}>
          <div className="flex">
            {items.map(([k,label,Ic])=>(<button key={k} onClick={()=>go(k)} className={`flex flex-1 flex-col items-center gap-0.5 py-2 ${active(k)?t.tp:t.tf}`}><Ic size={19}/><span className={`text-[9.5px] font-semibold ${lang==="hi"?"deva":""}`}>{label}</span></button>))}
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
                {/* Support lives once in the masthead (♥ Support) + the footer link row below;
                    the big footer CTA was a duplicate and has been removed. */}
              </div>
              <div className="flex flex-wrap gap-x-6 gap-y-2">
                {[["about",STR[lang].navMethod],["sources",STR[lang].navSrc],["blindspot",STR[lang].navOS],["topics",ui("sections",lang)],["support",lang==="hi"?"सहयोग":"Support"],["contact",lang==="hi"?"संपर्क":"Contact"],["privacy",lang==="hi"?"गोपनीयता":"Privacy"],["settings",lang==="hi"?"सेटिंग्स":"Settings"]].map(([k,l])=>(
                  <button key={k} onClick={()=>go(k)} className={`text-[13px] font-medium ${t.ts} hover:${t.tp} ${lang==="hi"?"deva":""}`}>{l}</button>
                ))}
              </div>
            </div>
            {/* Sponsor credit - renders nothing until a sponsor is configured in SPONSOR */}
            <SponsorSlot t={t} lang={lang} className="mt-7" />
            <div className={`mt-7 border-t pt-5 ${t.border} mono text-[10.5px] uppercase tracking-wide ${t.tf}`}>© 2026 Paksh · A Redstocks Technology LLP product</div>
          </div>
        </footer>
      );
    }

    /* ---------------- HOME ---------------- */
    // Ad slot. With a live ADSENSE_CLIENT this is a responsive AdSense unit. With AdSense OFF
    // (the default) it renders the print-CLASSIFIEDS placeholder from the design: a 2px ink
    // frame + "Advertisement · Classifieds" label bar, DELIBERATELY walled off from editorial
    // so an ad can never be mistaken for a story (FLAG 1). No script, no cookie, no tracking.
    // The placeholder copy is an honest "space available" invitation, never a fabricated listing.
    function AdSlot({ t, lang, slot, format, h }) {
      React.useEffect(()=>{ if(ADSENSE_CLIENT){ try{ (window.adsbygoogle=window.adsbygoogle||[]).push({}); }catch(e){} } },[]);
      if(ADSENSE_CLIENT) return (
        <div className={`relative flex items-center justify-center overflow-hidden border ${t.border} ${t.soft}`} style={{minHeight:h||250}}>
          <ins className="adsbygoogle" style={{display:"block",position:"absolute",inset:0,width:"100%",height:"100%"}} data-ad-client={ADSENSE_CLIENT} data-ad-slot={slot||""} data-ad-format={format||"auto"} data-full-width-responsive="true"/>
        </div>
      );
      const label = lang==="hi" ? "विज्ञापन · क्लासिफ़ाइड" : "Advertisement · Classifieds";
      const cta = lang==="hi" ? "यहाँ विज्ञापन दें →" : "Advertise here →";
      const entries = lang==="hi"
        ? [["स्थान उपलब्ध","इस कॉलम में आपका विज्ञापन, पक्ष के पाठकों तक।"],["सूचना","पक्ष क्लासिफ़ाइड, बिना ट्रैकिंग वाले विज्ञापन।"]]
        : [["SPACE AVAILABLE","Your classified here, seen by Paksh readers."],["NOTICE","Paksh classifieds, ads without tracking."]];
      return (
        <AdCtaBox t={t} lang={lang} label={label}>
          <div className="grid gap-x-6 gap-y-3 p-4 sm:grid-cols-2">
            {entries.map(([k,v],i)=>(
              <div key={i}>
                <div className={`mono text-[9.5px] font-bold uppercase tracking-[0.12em] ${t.tf} ${lang==="hi"?"deva":""}`}>{k}</div>
                <div className={`mt-0.5 text-[12.5px] leading-snug ${t.ts} ${readCls(lang)}`}>{v}</div>
              </div>
            ))}
          </div>
          <div className={`px-4 pb-3 eyebrow ${t.blind} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".08em"}}>{cta}</div>
        </AdCtaBox>
      );
    }
    // The classifieds placeholder is CLICKABLE: any interested advertiser lands on the Contact
    // form pre-set to "Advertise" (the Formspree dropdown option). Still walled off from editorial.
    function AdCtaBox({ t, lang, label, children }) {
      const ctx=React.useContext(SaveCtx);
      const open=()=>{ _adIntent=true; if(ctx&&ctx.go) ctx.go("contact"); };
      return (
        <div role="button" tabIndex={0} onClick={open} onKeyDown={(e)=>{ if(e.key==="Enter"||e.key===" "){ e.preventDefault(); open(); } }}
          className={`${t.surface} cursor-pointer`} style={{border:`2px solid ${t.ink}`}} aria-label={(lang==="hi"?"विज्ञापन दें: ":"Advertise: ")+label}>
          <div className="text-center" style={{borderBottom:`1px solid ${t.ink}`,padding:"4px 0"}}>
            <span className="mono" style={{fontSize:8.5,fontWeight:700,letterSpacing:".22em",textTransform:"uppercase",color:t.ink}}>{label}</span>
          </div>
          {children}
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
          {story.img && <div className="mb-3 overflow-hidden"><Thumb src={story.img} topic={story.topic} title={story.headline} ratio="16 / 9" t={t} lang={lang} /></div>}
          <div className={`eyebrow ${t.tf} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{tp||"News"}</div>
          <h3 className={`headline mt-2 text-[18px] sm:text-[19px] ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`} style={{lineHeight:1.28,textWrap:"pretty"}}>{story.headline}</h3>
          <div className="mt-3"><BiasSegments bias={story.bias} t={t} h={10} lang={lang} /></div>
          <div className="mt-1.5 flex items-center justify-between gap-3">
            <span className={`mono text-[10.5px] ${t.tf} ${lang==="hi"?"deva":""}`}>{(lang==="hi"?["वा","कें","द"]:["L","C","R"])[0]} {L} · {(lang==="hi"?"कें":"C")} {C} · {(lang==="hi"?"द":"R")} {R} · n = {n}</span>
            <CardClip story={story} t={t} lang={lang} />
          </div>
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
    // Right-rail auth-aware card (Direction B, transparent personalization). Member: a "Because
    // you read {topic}" pointer to a story on the topic they read most. Guest: a "New to Paksh?"
    // explainer with a How-it-works link. Never reorders the feed; ranking stays arithmetic.
    function RailPersonalize({ auth, lens, cards, t, lang, go, open, openHelp }) {
      if(auth && lens && lens.total>0 && lens.topics.length){
        const topic=lens.topics[0];
        const pick=(cards||[]).find(c=>c.topic===topic)||(cards||[])[0];
        const tp=lang==="hi"?(TOPIC_HI[topic]||topic):topic;
        return (
          <div className={`border p-4 ${t.surface} ${t.border}`}>
            <div className={`eyebrow ${t.blind} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{lang==="hi"?`क्योंकि आपने ${tp} पढ़ा`:`Because you read ${tp}`}</div>
            {pick && (
              <a href={"/story/"+encodeURIComponent(pick.id)} onClick={e=>{ if(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return; e.preventDefault(); open(pick.id); }} className="block no-underline group cursor-pointer mt-2">
                <div className={`headline text-[15px] ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`} style={{lineHeight:1.3}}>{pick.headline}</div>
                <div className="mt-2"><BiasSegments bias={pick.bias} t={t} h={8} lang={lang} /></div>
              </a>
            )}
            <button onClick={()=>go("lens")} className={`mt-3 eyebrow ${t.ts} hover:${t.tp} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".08em"}}>{lang==="hi"?"मेरा रीडिंग लेंस →":"My Reading Lens →"}</button>
          </div>
        );
      }
      return (
        <div className={`border p-4 ${t.surface} ${t.border}`}>
          <div className={`eyebrow ${t.tp} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{lang==="hi"?"पक्ष में नए?":"New to Paksh?"}</div>
          <p className={`mt-2 text-[13px] ${t.ts} ${readCls(lang)}`} style={{lineHeight:lang==="hi"?1.7:1.55}}>{lang==="hi"?"पक्ष एक ही खबर को हर पक्ष से दिखाता है, कौन कवर कर रहा है और कौन नहीं, ताकि आप पूरी तस्वीर देख सकें।":"Paksh shows every side of the same story, who's covering it and who isn't, so you see the whole picture."}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {openHelp && <button onClick={openHelp} className={`border px-3 py-1.5 eyebrow ${t.border} ${t.ts} hover:${t.tp} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".08em"}}>{lang==="hi"?"यह कैसे काम करता है":"How it works"}</button>}
            {authOn() && !auth && <button onClick={()=>go("login")} className={`px-3 py-1.5 eyebrow ${t.cta} ${t.ctaT} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".08em"}}>{lang==="hi"?"साइन इन":"Sign in"}</button>}
          </div>
        </div>
      );
    }
    // Right-rail "Developing storylines" — the freshest sagas (multi-event threads). Each links
    // to the full storyline page. Pure chronology of coverage; no bias re-computation.
    function DevelopingRail({ storylines, t, lang, goStoryline }) {
      const items=(storylines||[]).filter(s=>s.n_events>=2).slice(0,4);
      if(!items.length) return null;
      return (
        <div>
          <div className={`eyebrow pb-2 ${t.tp} ${lang==="hi"?"deva":""}`} style={{borderBottom:`1px solid ${t.ink}`,letterSpacing:lang==="hi"?0:".14em"}}>{lang==="hi"?"विकसित होती खबरें":"Developing storylines"}</div>
          {items.map((s,i)=>{ const title=(lang==="hi"&&s.title_hi)?s.title_hi:s.title;
            return (
              <a key={s.id} href={"/storyline/"+encodeURIComponent(s.id)} onClick={e=>{ if(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return; e.preventDefault(); goStoryline&&goStoryline(s.id); }} className={`block no-underline group cursor-pointer py-3 ${i<items.length-1?"border-b":""} ${t.border}`}>
                <div className={`headline text-[14px] ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`} style={{lineHeight:1.3,textWrap:"pretty"}}>{title}</div>
                <div className={`mt-1 mono text-[10px] ${t.tf} ${lang==="hi"?"deva":""}`}><span aria-hidden="true">◇</span> {s.n_events} {lang==="hi"?"अपडेट":"updates"}</div>
              </a>
            );
          })}
        </div>
      );
    }
    function HomeView({ cards, gapLeft, gapRight, topics, counts, stats, t, lang, open, goTopic, go, auth, lens, openHelp, storylines, goStoryline }) {
      // de-dup partition: every story appears in exactly ONE place. Ranking (importance:
      // breadth of distinct outlets across L/C/R, decayed by recency) is UNTOUCHED — the
      // top-ranked story leads, the rest fall into the tier ladder in ranked order.
      const used=new Set();
      const take=(arr,n)=>{ const out=[]; for(const c of arr){ if(out.length>=n) break; if(!used.has(c.id)){ out.push(c); used.add(c.id);} } return out; };
      const lead=cards[0]; if(lead) used.add(lead.id);
      const section=take(cards,4);          // the 2×2 secondary grid in the main well
      // FOR YOU (member, additive) — up to 4 stories on the topics you read most. Purely additive:
      // the shared arithmetic feed is untouched, nothing is hidden or reordered — it just surfaces
      // more of what you already open. Computed before "In brief" so it gets first pick of matches.
      const _topTopics=(auth && lens && lens.total>0 && lens.topics) ? lens.topics.slice(0,4) : [];
      const forYou = _topTopics.length ? take(cards.filter(c=>_topTopics.includes(c.topic)),4) : [];
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
          {/* one h1 for the page + an always-on legend so a first-time visitor knows what the
              "3 · 9 · 4" bias counts mean, right where they see them */}
          <h1 className="sr-only">{lang==="hi"?"पक्ष, भारत की खबरों का हर पक्ष":"Paksh: every side of India's news"}</h1>
          <div className={`${pad}`}>
            <div className={`flex flex-wrap items-center gap-x-4 gap-y-1.5 border-b py-2 ${t.border}`}>
              <span className={`eyebrow ${t.tf} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{lang==="hi"?"बायस बार":"The bias bar"}</span>
              {["left","center","right"].map(k=>(
                <span key={k} className="inline-flex items-center gap-1.5">
                  <span className={`${BIAS[k].tex} inline-block`} style={{width:14,height:10,border:`1px solid ${t.ink}`}}/>
                  <span className={`text-[11px] ${t.ts} ${lang==="hi"?"deva":""}`}>{lbl(k,lang)}</span>
                </span>
              ))}
            </div>
          </div>

          {/* FRONT PAGE — prototype 2.1fr / 1fr: a main well (Top Stories header + hero + a 2×2
              secondary grid) beside a rail (personalization / onboarding · Coverage Gaps · ad). */}
          <div className={pad}>
            <div className="grid lg:grid-cols-[2.1fr_1fr]">
              {/* main well */}
              <div className="min-w-0 py-4 lg:py-6 lg:border-r lg:pr-7" style={{borderColor:t.line}}>
                <div className="flex items-baseline justify-between gap-3 pb-2" style={{borderBottom:`2px solid ${t.ink}`}}>
                  <span className={`text-[13px] font-bold uppercase ${t.tp} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".08em"}}>{STR[lang].topNews}</span>
                  {stats.updated && <span className={`mono text-[10px] ${t.tf} ${lang==="hi"?"deva":""}`}>{lang==="hi"?`${timeAgo(stats.updated,lang)} अपडेट`:`Updated ${timeAgo(stats.updated,lang)}`}</span>}
                </div>
                {lead && <div className="py-5" style={{borderBottom:`1px solid ${t.line}`}}><LeadStory story={lead} t={t} lang={lang} onOpen={open} /></div>}
                <div className="grid sm:grid-cols-2">
                  {section.map((s,i)=>(
                    <div key={s.id} className={`py-5 ${i<section.length-1?"border-b":""} ${i%2===1?"sm:border-l sm:pl-5":"sm:pr-5"} ${i>=2?"sm:border-b-0":""}`} style={{borderColor:t.line}}>
                      <SectionCard story={s} t={t} lang={lang} onOpen={open} />
                    </div>
                  ))}
                </div>
              </div>
              {/* right rail */}
              <div className="min-w-0 py-4 lg:py-6 lg:pl-7 space-y-7">
                <RailPersonalize auth={auth} lens={lens} cards={cards} t={t} lang={lang} go={go} open={open} openHelp={openHelp} />
                {gapItems.length>0 && (
                  <div>
                    <div className="pb-2" style={{borderBottom:`2px solid ${t.ink}`}}><span className={`text-[12px] font-bold uppercase ${t.blind} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".08em"}}>{STR[lang].navOS}</span></div>
                    {gapItems.slice(0,2).map((it,i)=>(
                      <a key={it.story.id} href={"/story/"+encodeURIComponent(it.story.id)} onClick={e=>{ if(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return; e.preventDefault(); open(it.story.id); }} className={`block no-underline group cursor-pointer py-3 ${i===0?"border-b":""} ${t.border}`}>
                        <div className={`headline text-[15px] ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`} style={{lineHeight:1.24,textWrap:"balance"}}>{it.story.headline}</div>
                        {i===0
                          ? <div className="mt-2 max-w-[180px]"><GapColumns counts={it.story.counts||{}} t={t} lang={lang} /></div>
                          : <div className={`mt-1.5 text-[11px] ${t.blind} ${lang==="hi"?"deva":""}`}>{it.label}</div>}
                      </a>
                    ))}
                  </div>
                )}
                <DevelopingRail storylines={storylines} t={t} lang={lang} goStoryline={goStoryline} />
                <AdSlot t={t} lang={lang} />
              </div>
            </div>
          </div>

          {/* FOR YOU — additive personalization for signed-in readers; the arithmetic feed above
              is untouched (honours "we never hide stories"). Each card says why it's here. */}
          {forYou.length>0 && (
            <div className={pad}>
              <div className="py-7" style={{borderBottom:`1px solid ${t.ink}`}}>
                <div className="mb-4 flex items-baseline justify-between gap-3 border-b pb-2" style={{borderColor:t.line}}>
                  <h2 className={`headline text-[15px] font-bold uppercase tracking-[0.08em] ${t.tp} ${isHi(lang)}`}>{lang==="hi"?"आपके लिए":"For you"}</h2>
                  <button onClick={()=>go("lens")} className={`mono text-[10.5px] ${t.tf} hover:${t.tp} ${lang==="hi"?"deva":""}`}>{lang==="hi"?"मेरा लेंस →":"My Reading Lens →"}</button>
                </div>
                <div className="grid gap-x-6 gap-y-7 sm:grid-cols-2 lg:grid-cols-4">
                  {forYou.map((s,i)=>{ const tp=lang==="hi"?(TOPIC_HI[s.topic]||s.topic):s.topic;
                    return (
                      <div key={s.id} className={i>0?"lg:border-l lg:pl-6":""} style={i>0?{borderColor:t.line}:{}}>
                        <div className={`eyebrow mb-1.5 ${t.blind} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".1em"}}>{lang==="hi"?`क्योंकि आपने ${tp} पढ़ा`:`Because you read ${tp}`}</div>
                        <SectionCard story={s} t={t} lang={lang} onOpen={open} />
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* AD — a single in-feed leaderboard at a natural break (calm, not cluttered) */}
          <div className={pad}><div className="py-2"><AdSlot t={t} lang={lang} h={90} format="horizontal" /></div></div>

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
    function StoryPage({ story, t, lang, go, openTopic, related=[], open, saved, onToggleSave, a11y, auth, goStoryline }) {
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
      // SWIPE L/C/R coverage (design mobile prototype): a horizontal swipe over the coverage
      // list cycles the side filter through the present sides. Keyboard/tab clicks still work.
      const _swipe=React.useRef({x:0,y:0});
      const _tabsOrder=()=>["all"].concat(["left","center","right","international","unrated"].filter(k=>counts[k]>0));
      const onTouchStart=(e)=>{ const p=e.touches&&e.touches[0]; if(p) _swipe.current={x:p.clientX,y:p.clientY}; };
      const onTouchEnd=(e)=>{ const p=e.changedTouches&&e.changedTouches[0]; if(!p) return; const dx=p.clientX-_swipe.current.x, dy=p.clientY-_swipe.current.y;
        if(Math.abs(dx)>48 && Math.abs(dx)>Math.abs(dy)*1.4){ const ord=_tabsOrder(); let i=ord.indexOf(atab); if(i<0)i=0; i=(i+(dx<0?1:-1)+ord.length)%ord.length; setAtab(ord[i]);
          const el=document.getElementById("arts"); if(el) el.scrollIntoView({behavior:"smooth",block:"start"}); } };
      const copy=()=>{ try{ navigator.clipboard.writeText(window.location.href); setCopied(true); setTimeout(()=>setCopied(false),1600);}catch(e){} };
      const tp=lang==="hi"?(TOPIC_HI[story.topic]||story.topic):story.topic;
      const region=lang==="hi"?(story.region==="World"?"विश्व":"भारत"):(story.region||"India");
      const metaLine=lang==="hi"
        ? `${total} स्रोत · वाम ${vc.left} · केंद्र ${vc.center} · दक्षिण ${vc.right} · ${timeAgo(story.created_at,lang)}`
        : `${total} outlets · ${vc.left} left · ${vc.center} centre · ${vc.right} right · ${timeAgo(story.created_at,lang)}`;
      const ATab=({k,n})=>{ const on=atab===k;
        const lab=k==="all"?(lang==="hi"?"सभी":"All"):(k==="unrated"?(lang==="hi"?"बिना रेटिंग":"Unrated"):lbl(k,lang));
        return <button onClick={()=>setAtab(k)} className={`flex shrink-0 items-center gap-1.5 whitespace-nowrap border-b-2 px-1 pb-2 text-[13.5px] font-semibold ${on?t.tp:`${t.tf} hover:${t.ts}`} ${lang==="hi"?"deva":""}`} style={{borderColor:on?(k==="all"||k==="center"?t.ink:((BIAS[k]&&BIAS[k].color)||"#B8B4AC")):"transparent"}}>{lab}<span className={`mono text-[11px] ${on?t.ts:t.tf}`}>{n}</span></button>; };
      const frLen=(v)=>Array.isArray(v)?v.length:(typeof v==="string"&&v.trim()?1:0);
      const sides=["left","center","right"].filter(k=> frLen(fr[k])>0 || counts[k]>0);
      // Distinguish "this story isn't analysed yet" (all sides blank -> pending) from a side
      // that simply lacks enough unique coverage (some side has a summary, this one doesn't).
      const anyFraming=sides.some(k=>frLen(fr[k])>0);
      return (
        <div className="mx-auto max-w-[1000px] px-4 sm:px-8 py-6">
          {/* secondary bar: back · breadcrumb · share */}
          <div className="mb-8 flex items-center justify-between gap-3 pb-3" style={{borderBottom:`1px solid ${t.ink}`}}>
            <button onClick={()=>go("home")} className={`inline-flex items-center gap-1.5 eyebrow ${t.ts} hover:${t.tp}`} style={{letterSpacing:lang==="hi"?0:".1em"}}><ArrowLeft size={14}/> {STR[lang].back}</button>
            <button onClick={()=>openTopic(story.topic)} className={`hidden sm:inline truncate eyebrow ${t.tf} hover:${t.tp} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{tp} · {region}</button>
            <div className="flex shrink-0 items-center gap-4">
              {authOn() && onToggleSave && <SaveButton story={story} saved={saved||new Set()} onToggle={onToggleSave} t={t} lang={lang} />}
              <button onClick={copy} className={`inline-flex shrink-0 items-center gap-1.5 eyebrow ${t.ts} hover:${t.tp}`} style={{letterSpacing:lang==="hi"?0:".1em"}}>{copied?<><Check size={13}/> {lang==="hi"?"कॉपी":"Copied"}</>:<><LinkIcon size={13}/> {lang==="hi"?"शेयर":"Share"}</>}</button>
            </div>
          </div>

          {/* headline block — left-aligned: kicker · region · time, 40px headline, 18px lead (prototype) */}
          <div className="mx-auto max-w-[840px]">
            <div className={`eyebrow ${t.tf} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{tp} · {region}{story.created_at?` · ${timeAgo(story.created_at,lang)}`:""}</div>
            <h1 className={`headline mt-3 text-[30px] sm:text-[40px] ${t.tp} ${readCls(lang)}`} style={{lineHeight:lang==="hi"?1.16:1.08,letterSpacing:lang==="hi"?0:"-0.022em",textWrap:"balance"}}>{story.headline}</h1>
            {story.lead && <p className={`mt-4 text-[17px] sm:text-[18px] ${t.tp} ${readCls(lang)}`} style={{lineHeight:lang==="hi"?1.85:1.62,maxWidth:"62ch",textWrap:"pretty"}}>{story.lead}</p>}
            <div className={`mt-4 mono text-[11px] ${t.tf} ${lang==="hi"?"deva":""}`}>{metaLine}{story.auto && <> · <span className="uppercase">{STR[lang].autoTag}</span></>}{absDate(story.created_at,lang)?` · ${absDate(story.created_at,lang)}`:""}</div>
          </div>

          {/* the bias instrument — border-y ink, printed scale; segments filter the article list */}
          <div className="mx-auto mt-8 max-w-[840px] py-6" style={{borderTop:`1px solid ${t.ink}`,borderBottom:`1px solid ${t.ink}`}}>
            <div className="mb-2.5 flex items-baseline justify-between gap-3">
              <div className={`flex gap-5 sm:gap-6 text-[11px] font-medium uppercase tracking-[0.12em] ${t.tp} ${lang==="hi"?"deva":""}`}>
                {["left","center","right"].map(k=>(vc[k]>0)?<span key={k}>{lbl(k,lang)} <span className="mono" style={{letterSpacing:0}}>{vc[k]}</span></span>:null)}
              </div>
              <span className={`mono text-[11px] shrink-0 ${t.tf}`}>n = {nVotes} · {bpct.left}/{bpct.center}/{bpct.right}%</span>
            </div>
            <BiasSegments bias={bpct} t={t} h={28} lang={lang} onPick={(k)=>{ track("bias_segment",{side:k}); setAtab(k); const el=document.getElementById("arts"); if(el) el.scrollIntoView({behavior:"smooth",block:"start"}); }} active={atab!=="all"?atab:null} />
            <div className="relative" style={{height:15,marginTop:3}}>
              {[25,50,75].map(p=><div key={p} style={{position:"absolute",left:p+"%",top:0,width:1,height:p===50?7:4,background:p===50?t.ink:t.line}}/>)}
              <span className={`mono text-[10px] ${t.tf}`} style={{position:"absolute",left:"50%",top:7,transform:"translateX(-50%)",whiteSpace:"nowrap"}}>{lang==="hi"?"कवरेज का 50%":"50% of coverage"}</span>
            </div>
          </div>

          {/* Reading Lens margin-mark (member) / sign-in nudge (guest). Private; never affects the bar. */}
          {authOn() && (
            <div className="mx-auto mt-3 max-w-[840px]">
              {auth
                ? <div className={`flex items-center gap-1.5 mono text-[10.5px] ${t.tf} ${isHi(lang)}`}><Check size={12}/> {lang==="hi"?"आपके रीडिंग लेंस में दर्ज · सिर्फ़ आपको दिखता है":"Recorded to your Reading Lens · visible only to you"}</div>
                : <button onClick={()=>go("login")} className={`mono text-[10.5px] ${t.tf} hover:${t.tp} ${isHi(lang)}`}>{lang==="hi"?"अपना रीडिंग लेंस बनाने के लिए साइन इन करें →":"Sign in to build your Reading Lens →"}</button>}
            </div>
          )}

          {/* STORYLINE — how this saga developed across days (only when linked to >1 event) */}
          {story.storyline && (story.storyline.events||[]).length>1 && (
            <div className="mx-auto mt-10 max-w-[840px]">
              <div className="mb-1 flex items-baseline justify-between gap-3 pb-2" style={{borderBottom:`1px solid ${t.ink}`}}>
                <h3 className={`eyebrow ${t.tp} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{lang==="hi"?"यह खबर कैसे विकसित हुई":"How this developed"}</h3>
                <button onClick={()=>goStoryline&&goStoryline(story.storyline.id)} className={`mono text-[10.5px] ${t.tf} hover:${t.tp} ${lang==="hi"?"deva":""}`}>{story.storyline.events.length} {lang==="hi"?"अपडेट · पूरी कड़ी →":"updates · full storyline →"}</button>
              </div>
              <StorylineTimeline storyline={story.storyline} currentId={story.id} t={t} lang={lang} open={open} />
            </div>
          )}

          {/* how each side framed it — 3-up bordered table (desktop) / stacked cards (mobile) */}
          {sides.length>0 && (
          <div className="mt-10">
            <div className="mb-4 flex items-baseline justify-between gap-3">
              <h3 className={`eyebrow ${t.tp} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{STR[lang].framingTitle}</h3>
              <span className={`mono text-[10.5px] hidden sm:inline ${t.tf} ${lang==="hi"?"deva":""}`}>{lang==="hi"?"बराबर कॉलम · क्रम बार जैसा":"equal columns · order matches the bar"}</span>
            </div>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3 md:gap-0 md:border" style={{borderColor:t.ink}}>
              {sides.map(k=>(
                <div key={k} className="flex flex-col border md:border-0 md:border-r last:md:border-r-0" style={{borderColor:t.ink}}>
                  <div className={`flex items-center justify-between ${t.soft}`} style={{padding:"8px 12px",borderBottom:`1px solid ${t.line}`}}>
                    <span className={`text-[10.5px] font-bold uppercase tracking-[0.06em] ${lang==="hi"?"deva":""}`} style={{color:BIAS[k].color}}>{lbl(k,lang)} · {counts[k]}</span>
                    <span className={BIAS[k].tex} style={{width:10,height:10,border:`1px solid ${t.ink}`}}/>
                  </div>
                  <div className={`flex flex-1 flex-col p-4 ${t.surface}`}>
                    {Array.isArray(fr[k]) && fr[k].length
                      ? <ul className="mt-3.5 space-y-2">{fr[k].map((p,i)=>(
                          <li key={i} className={`flex gap-2 text-[14px] md:text-[14.5px] ${t.ts} ${readCls(lang)}`} style={{lineHeight:lang==="hi"?1.7:1.55}}>
                            <span className="mt-[8px] h-1.5 w-1.5 shrink-0 rounded-full" style={{background:BIAS[k].color}}/>{p}</li>))}</ul>
                      : (typeof fr[k]==="string" && fr[k].trim())
                        ? <p className={`mt-3.5 text-[14.5px] md:text-[15px] ${t.ts} ${readCls(lang)}`} style={{lineHeight:lang==="hi"?1.75:1.62}}>{fr[k]}</p>
                        : <p className={`mt-3.5 text-[13px] italic ${t.tf} ${readCls(lang)}`}>{anyFraming?STR[lang].framingThin:STR[lang].framingPending}</p>}
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
                  <span className={`mono text-[14px] font-semibold ${t.tp}`}>{votes}{oc>votes && <span className={`ml-1 text-[11px] font-normal ${t.tf}`}>{lang==="hi"?`प्रकाशक · ${oc} मास्टहेड`:`${votes===1?"publisher":"publishers"} · ${oc} mastheads`}</span>}</span>
                </div>
                {coOwned && <div className="mt-1.5 space-y-0.5 pl-6">{groups.filter(([o,ms])=>ms.length>1).map(([o,ms],j)=>(
                  <div key={j} className={`text-[11px] leading-snug ${t.tf} ${isHi(lang)}`}>{ms.join(" · ")} <span className="italic">({o}, {lang==="hi"?"1 वोट":"1 vote"})</span></div>
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
          {/* AD — one in-content unit before the outlet list */}
          <div className="mx-auto mt-10 max-w-[840px]"><AdSlot t={t} lang={lang} h={110} format="horizontal" /></div>

          <div className="mx-auto mt-10 max-w-[840px]" id="arts" onTouchStart={onTouchStart} onTouchEnd={onTouchEnd}>
            <div className="mb-3 flex items-baseline justify-between gap-3">
              <div className={`eyebrow ${t.tp} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{lang==="hi"?"किसने कवर किया":"Who covered it"}</div>
              <span className={`md:hidden mono text-[9.5px] uppercase tracking-wide ${t.tf} ${lang==="hi"?"deva":""}`}>{lang==="hi"?"पक्ष बदलने को स्वाइप करें ⇄":"swipe to change side ⇄"}</span>
            </div>
            <div className={`flex items-center gap-5 overflow-x-auto border-b ${t.border}`} style={{scrollbarWidth:"none"}}>
              <ATab k="all" n={outlets.length} />
              {counts.left>0 && <ATab k="left" n={counts.left} />}
              {counts.center>0 && <ATab k="center" n={counts.center} />}
              {counts.right>0 && <ATab k="right" n={counts.right} />}
              {counts.international>0 && <ATab k="international" n={counts.international} />}
              {counts.unrated>0 && <ATab k="unrated" n={counts.unrated} />}
            </div>
            <div className="mt-4 space-y-2.5">
              {arts.map((o,i)=>(
                <a key={i} href={o.url||"#"} target="_blank" rel="nofollow noopener noreferrer" onClick={()=>track("source_open",{side:o.lean})} className={`flex items-start gap-3 border p-3.5 ${t.surface} ${t.border} hover:${t.soft}`}>
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

          {/* More on this topic — keep the reader moving instead of dead-ending here */}
          {related && related.length>0 && open && (
            <div className="mx-auto mt-12 max-w-[1000px]">
              <div className="mb-4 pb-2" style={{borderBottom:`1px solid ${t.ink}`}}>
                <h3 className={`eyebrow ${t.tp} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{lang==="hi"?`${tp} पर और खबरें`:`More on ${tp}`}</h3>
              </div>
              <div className="grid gap-x-7 gap-y-6 sm:grid-cols-2 lg:grid-cols-3">
                {related.map(s=><GridCard key={s.id} story={s} t={t} lang={lang} onOpen={open} />)}
              </div>
            </div>
          )}
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
    // Gap card (prototype): a bordered card — kicker · time + a clay "Gap" badge, headline, the
    // three EQUAL-WIDTH count columns (absence drawn as hatch), then a plain-language note.
    function GapCard({ story, gapSide, t, lang, onOpen }) {
      const c=story.counts||{left:0,center:0,right:0};
      const gapN=c[gapSide]||0; const L=c.left||0,C=c.center||0,R=c.right||0;
      const sideLab=lbl(gapSide,lang);
      const covered = gapSide==="left"
        ? (lang==="hi"?`${R} दक्षिण, ${C} केंद्र`:`${R} Right, ${C} Centre`)
        : (lang==="hi"?`${L} वाम, ${C} केंद्र`:`${L} Left, ${C} Centre`);
      const tail = gapN===0 ? (lang==="hi"?`— अभी ${sideLab} कवरेज नहीं।`:`— no ${sideLab} coverage yet.`)
                            : (lang==="hi"?`— ${sideLab} कम।`:`— ${sideLab} thin.`);
      const kick=lang==="hi"?(TOPIC_HI[story.topic]||story.topic):story.topic;
      return (
        <a href={"/story/"+encodeURIComponent(story.id)} onClick={e=>{ if(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return; e.preventDefault(); onOpen(story.id); }} className={`flex h-full flex-col no-underline group cursor-pointer border p-4 ${t.surface} ${t.border}`}>
          <div className="flex items-baseline justify-between gap-2">
            <span className={`eyebrow ${t.tf} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".1em"}}>{kick}{story.created_at?` · ${timeAgo(story.created_at,lang)}`:""}</span>
            <span className={`shrink-0 mono text-[9px] font-bold uppercase tracking-[0.06em] ${t.blind} ${t.blindSoft} ${lang==="hi"?"deva":""}`} style={{padding:"3px 6px"}}>{lang==="hi"?"गैप":"Gap"}</span>
          </div>
          <h3 className={`headline mt-2 text-[18px] ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`} style={{lineHeight:1.2,textWrap:"balance"}}>{story.headline}</h3>
          <div className="mt-3.5"><GapColumns counts={c} t={t} lang={lang} /></div>
          <div className={`mt-3 text-[12px] ${t.blind} ${readCls(lang)}`} style={{lineHeight:1.45}}>{covered} {tail}</div>
        </a>
      );
    }
    function BlindspotPage({ left, right, roster, agg, stats, t, lang, open, go, auth, lens }) {
      // left = left_heavier (RIGHT is the under-covered side); right = right_heavier (LEFT is).
      const cards=[];
      (right||[]).forEach(s=>cards.push({story:s, gapSide:"left"}));
      (left||[]).forEach(s=>cards.push({story:s, gapSide:"right"}));
      // Starkest first: the smallest under-covered count (0 = unreported) leads.
      cards.sort((a,b)=>((a.story.counts||{})[a.gapSide]||0)-((b.story.counts||{})[b.gapSide]||0));
      const shown=cards.slice(0,15);
      const gapsToday=(agg.total!=null?agg.total:cards.length);
      const pad="px-4 sm:px-10";
      // "Tuned to your reading" (member): the side you read LEAST is the side you most miss, so
      // surface up to 3 gaps where that side is the under-covered one, preferring topics you read.
      const sides=(lens&&lens.sides)||{};
      const leastSide=["left","center","right"].reduce((a,b)=>((sides[b]||0)<(sides[a]||0)?b:a),"left");
      const tuned=(auth&&lens&&lens.total>0)
        ? cards.filter(c=>c.gapSide===leastSide).sort((a,b)=>{ const at=lens.topics.indexOf(a.story.topic), bt=lens.topics.indexOf(b.story.topic); return (at<0?99:at)-(bt<0?99:bt); }).slice(0,3)
        : [];
      const explain=(head,body)=>(
        <div>
          <div className={`eyebrow ${t.tp} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{head}</div>
          <p className={`mt-2.5 text-[14px] ${t.ts} ${readCls(lang)}`} style={{lineHeight:lang==="hi"?1.75:1.65}}>{body}</p>
        </div>
      );
      const methodNote = lang==="hi"
        ? "किसी खबर को कवरेज गैप उसी अंकगणित से चिह्नित किया जाता है जैसे बार: प्रति झुकाव अलग कवर करने वाले आउटलेट, एक स्वामी एक वोट। कोई लेख आँका नहीं जाता, केवल गिना जाता है।"
        : "A story is flagged a Coverage Gap by the same arithmetic as the bar: distinct covering outlets per lean, one vote per owner. No article is judged, only counted.";
      return (
        <div className="mx-auto max-w-[1280px]">
          {/* header — clay eyebrow + title + sub, 2px ink rule (prototype) */}
          <div className={`${pad} pt-6`}>
            <div className="flex flex-wrap items-end justify-between gap-4 pb-5" style={{borderBottom:`2px solid ${t.ink}`}}>
              <div className="max-w-[70ch]">
                <div className={`eyebrow ${t.blind} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".16em"}}>{lang==="hi"?"कवरेज गैप · ब्लाइंडस्पॉट":"Coverage gaps · blindspots"}</div>
                <h1 className={`headline mt-2.5 text-[30px] sm:text-[40px] ${t.tp} ${readCls(lang)}`} style={{letterSpacing:lang==="hi"?0:"-0.018em"}}>{STR[lang].osTitle}</h1>
                <p className={`mt-3 text-[15px] sm:text-[16px] ${t.ts} ${readCls(lang)}`} style={{lineHeight:lang==="hi"?1.75:1.6}}>{STR[lang].osSub}</p>
              </div>
              <div className={`mono text-[11px] leading-[1.7] text-right shrink-0 ${t.tf}`}>
                {gapsToday} {lang==="hi"?"गैप आज":"gaps today"}<br/>{stats.stories} {lang==="hi"?"ख़बरें ट्रैक":"stories tracked"}
              </div>
            </div>
          </div>
          {/* 2fr / 1fr — gap-card grid beside the rail (Tuned to your reading + method note) */}
          <div className={pad}>
            <div className="grid lg:grid-cols-[2fr_1fr]">
              <div className="py-6 lg:border-r lg:pr-7" style={{borderColor:t.line}}>
                {shown.length
                  ? <div className="grid gap-5 sm:grid-cols-2">{shown.map(g=>(<GapCard key={g.story.id} story={g.story} gapSide={g.gapSide} t={t} lang={lang} onOpen={open} />))}</div>
                  : <div className={`border border-dashed p-10 text-center text-[13px] ${t.border} ${t.tf} ${readCls(lang)}`}>{STR[lang].noStories}</div>}
              </div>
              <div className="py-6 lg:pl-7 space-y-6">
                {tuned.length>0 && (
                  <div style={{borderLeft:`2px solid ${BIAS.left.color}`}} className={`${t.soft} p-4`}>
                    <div className="flex items-baseline justify-between gap-3">
                      <div className={`eyebrow ${t.blind} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".1em"}}>{lang==="hi"?"आपके पढ़ने के हिसाब से":"Tuned to your reading"}</div>
                      <button onClick={()=>go("lens")} className={`mono text-[10px] ${t.tf} hover:${t.tp} ${lang==="hi"?"deva":""}`}>{lang==="hi"?"लेंस →":"Lens →"}</button>
                    </div>
                    <p className={`mt-2 text-[13px] ${t.ts} ${readCls(lang)}`} style={{lineHeight:lang==="hi"?1.7:1.5}}>{lang==="hi"?`आप ${lbl(leastSide,lang)} की कवरेज सबसे कम पढ़ते हैं, ये उस पक्ष पर कम कवर हुई खबरें हैं।`:`You read ${lbl(leastSide,lang)} coverage the least, here are gaps where that side is under-covered.`}</p>
                    <div className="mt-3 space-y-2.5">
                      {tuned.map(g=>(
                        <a key={g.story.id} href={"/story/"+encodeURIComponent(g.story.id)} onClick={e=>{ if(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return; e.preventDefault(); open(g.story.id); }} className={`block no-underline group cursor-pointer headline text-[14px] ${t.tp} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`} style={{lineHeight:1.3}}>{g.story.headline}</a>
                      ))}
                    </div>
                  </div>
                )}
                <div className={`${t.surface} p-4`} style={{border:`1px solid ${t.line}`,borderLeft:`3px solid ${t.ink}`}}>
                  <p className={`text-[12.5px] ${t.ts} ${isHi(lang)}`} style={{lineHeight:1.55}}>{methodNote}</p>
                </div>
                <AdSlot t={t} lang={lang} />
              </div>
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
          <div className="mt-8"><AdSlot t={t} lang={lang} h={90} format="horizontal" /></div>
        </PageWrap>
      );
    }
    // AxisBars — the 3 editorial tonality axes as labelled position markers. A dot sits
    // at value% between the two poles; purely a display of the per-publisher `axes` set by
    // editors. Does not touch, replace or feed the arithmetic bias bar.
    function AxisBars({ axes, t, lang }) {
      if(!axes) return null;
      return (
        <div className="mt-3 space-y-2.5">
          {AXES.map(ax=>{
            const raw=axes[ax.key]; if(raw==null) return null;
            const v=Math.max(0,Math.min(100,raw));
            const L=ax[lang]||ax.en;
            return (
              <div key={ax.key}>
                <div className={`flex items-baseline justify-between mono text-[9px] uppercase tracking-wide ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".06em"}}>
                  <span className={t.tf}>{L.lo}</span>
                  <span className={`${t.ts} font-bold`}>{L.name}</span>
                  <span className={t.tf}>{L.hi}</span>
                </div>
                <div className="relative mt-1 h-1.5 rounded-full" style={{background:"rgba(120,119,104,0.20)"}}>
                  <div className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full" style={{left:`${v}%`,backgroundColor:ax.color,boxShadow:"0 0 0 2px rgba(255,255,255,0.85)"}} title={`${L.name}: ${v}/100`}/>
                </div>
              </div>
            );
          })}
        </div>
      );
    }
    function SourceCard({ s, t, lang }) {
      const side=["left","center","right"].includes(s.lean)?s.lean:null;
      const badge = side
        ? (side==="center"?lbl("center",lang):(lang==="hi"?lbl(side,lang):`${lbl(side,lang)}`))
        : (s.label||"-");
      const conf = s.confidence ? (lang==="hi"?`${confName(s.confidence,lang)} विश्वास`:`${confName(s.confidence,lang)} confidence`) : "";
      return (
        <div className={`border p-4 ${t.surface} ${t.border}`}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className={`flex flex-wrap items-baseline gap-2`}>
                <span className={`text-[16px] font-bold ${t.tp}`} style={{fontFamily:"'Source Serif 4',Georgia,serif"}}>{s.name}</span>
                <span className={`mono text-[9px] uppercase ${t.tf}`} style={{border:`1px solid ${t.line}`,padding:"1px 4px"}}>{(s.language||"en").toUpperCase()}</span>
              </div>
              {s.website && <a href={s.website} target="_blank" rel="nofollow noopener noreferrer" className={`mt-1 block text-[11.5px] font-semibold ${t.blind} hover:underline`}>{(s.website||"").replace(/^https?:\/\//,"").replace(/\/$/,"")}</a>}
            </div>
            <div className="shrink-0 text-right">
              {side
                ? <span className="mono text-[11px] font-bold uppercase text-white" style={{backgroundColor:BIAS[side].color,padding:"4px 9px",letterSpacing:".04em"}}>{badge}</span>
                : <span className={`mono text-[10px] font-bold uppercase ${t.chip} ${t.tf}`} style={{padding:"4px 9px"}}>{badge}</span>}
              {conf && <div className={`mt-1.5 text-[10px] font-medium ${t.tf} ${isHi(lang)}`}>{conf}</div>}
            </div>
          </div>
          {s.contested && <div className="mt-2.5"><span className={`mono text-[9.5px] font-bold uppercase ${t.blind} ${t.blindSoft} ${lang==="hi"?"deva":""}`} style={{border:`1px solid #E0CBB9`,padding:"3px 8px",letterSpacing:".06em"}}>{STR[lang].contested}</span></div>}
          {(s.ownership||s.rationale) && (
            <div className={`mt-2.5 text-[12.5px] leading-[1.5] ${t.ts} ${readCls(lang)}`}>
              {s.ownership && <><span className={`font-semibold ${t.tp}`}>{STR[lang].ownership}:</span> {s.ownership}</>}
              {s.ownership && s.rationale && " · "}
              {s.rationale && <><span className={`font-semibold ${t.tp}`}>{STR[lang].whyRated}:</span> {s.rationale}</>}
            </div>
          )}
          <SignalChips subscores={s.subscores} t={t} lang={lang} />
          <AxisBars axes={s.axes} t={t} lang={lang} />
        </div>
      );
    }
    // The six-signal rubric scores per outlet (-2..+2), shown as small chips. Only non-zero
    // signals are chipped (they're what pushed the lean); sign colours by side, magnitude by number.
    const SIG_LABELS={ editorial:{en:"Stance",hi:"रुख"}, framing:{en:"Framing",hi:"फ़्रेमिंग"}, selection:{en:"Selection",hi:"चयन"},
      sourcing:{en:"Sourcing",hi:"स्रोत"}, ownership:{en:"Ownership",hi:"स्वामित्व"}, panel:{en:"Panel",hi:"पैनल"} };
    function SignalChips({ subscores, t, lang }) {
      if(!subscores) return null;
      const order=["editorial","framing","selection","sourcing","ownership","panel"];
      const items=order.filter(k=>typeof subscores[k]==="number" && subscores[k]!==0);
      if(!items.length) return null;
      return (
        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          <span className={`mono text-[9px] font-semibold uppercase ${t.tf} ${lang==="hi"?"deva":""}`} style={{letterSpacing:".04em"}}>{STR[lang].signals}</span>
          {items.map(k=>{ const v=subscores[k]; const bg=v<0?BIAS.left.soft:BIAS.right.soft; const fg=v<0?"#3A4B54":"#75442E"; const lab=(SIG_LABELS[k]||{})[lang]||(SIG_LABELS[k]||{}).en||k;
            return <span key={k} className="mono text-[10px] font-semibold" style={{backgroundColor:bg,color:fg,padding:"2px 6px"}}>{lab} {v>0?`+${v}`:v}</span>;
          })}
        </div>
      );
    }
    function SourcesPage({ t, lang, sources }) {
      const [f,setF]=useState("all");
      const list=(sources||[]).filter(s=>f==="all"||s.lean===f);
      const filters=[["all",lang==="hi"?"सभी":"All"],["left",lbl("left",lang)],["center",lbl("center",lang)],["right",lbl("right",lang)]];
      return (
        <PageWrap>
          <div className="mx-auto max-w-[1180px]">
            <div className="flex flex-wrap items-end justify-between gap-3 pb-3" style={{borderBottom:`2px solid ${t.ink}`}}>
              <div>
                <div className={`eyebrow ${t.tf} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".16em"}}>{lang==="hi"?"रेटिंग रजिस्ट्री":"Ratings registry"}</div>
                <h1 className={`headline mt-2.5 text-[30px] sm:text-[34px] ${t.tp} ${readCls(lang)}`} style={{letterSpacing:lang==="hi"?0:"-0.02em"}}>{STR[lang].srcTitle}</h1>
              </div>
              <div className="flex flex-wrap gap-1.5">{filters.map(([k,label])=>{ const on=f===k;
                return <button key={k} onClick={()=>setF(k)} className={`text-[10px] font-semibold uppercase ${on?t.ctaT:t.ts} hover:${t.tp} ${lang==="hi"?"deva":""}`} style={{border:`1px solid ${t.ink}`,padding:"8px 12px",background:on?t.ink:"transparent",letterSpacing:lang==="hi"?0:".04em"}}>{label}</button>;
              })}</div>
            </div>
            <p className={`mt-3 mb-5 max-w-[74ch] text-[13.5px] leading-[1.55] ${t.ts} ${readCls(lang)}`}>{STR[lang].srcDisclaimer}</p>
            <div className="grid gap-4 sm:grid-cols-2">{list.map(s=><SourceCard key={s.id||s.name} s={s} t={t} lang={lang}/>)}</div>
            <div className="mt-8"><AdSlot t={t} lang={lang} h={90} format="horizontal" /></div>
          </div>
        </PageWrap>
      );
    }
    function AboutPage({ t, lang, agg, go }) {
      const Row=({h,children})=>(<div className={`border-b py-6 ${t.border}`}><h2 className={`headline text-[20px] ${t.tp} ${readCls(lang)} mb-2`}>{h}</h2><div className={`text-[15px] leading-[1.62] ${t.ts} ${readCls(lang)}`}>{children}</div></div>);
      const a=agg||{};
      const gapText=(STR[lang].m_gap||"").replace("{total}",a.total).replace("{rh}",a.right_heavier).replace("{lh}",a.left_heavier).replace("{lo}",a.left_outlets).replace("{ro}",a.right_outlets);
      const heroH1=lang==="hi"?"भारत की हर खबर, हर पक्ष — और उसके पीछे का अंकगणित":"Every side of India's news, and the arithmetic behind it";
      const bullets=M_READ[lang]||M_READ.en; const bulletColors=[BIAS.left.color,BIAS.center.color,BIAS.right.color];
      return (
        <PageWrap>
          <div className="mx-auto max-w-[1180px]">
            {/* header */}
            <div className="pb-3.5" style={{borderBottom:`2px solid ${t.ink}`}}>
              <div className={`eyebrow ${t.tf} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".16em"}}>{STR[lang].methodTitle}</div>
              <h1 className={`headline mt-3 text-[30px] sm:text-[38px] ${t.tp} ${readCls(lang)}`} style={{letterSpacing:lang==="hi"?0:"-0.022em",maxWidth:"22ch",textWrap:"balance"}}>{heroH1}</h1>
            </div>
            {/* 1.7fr / 1fr */}
            <div className="mt-6 grid lg:grid-cols-[1.7fr_1fr]">
              <div className="lg:border-r lg:pr-8" style={{borderColor:t.line}}>
                <p className={`text-[17px] ${t.ts} ${readCls(lang)}`} style={{lineHeight:1.62,maxWidth:"62ch"}}>{STR[lang].m_does}</p>
                <div className={`mt-6 ${t.surface} p-5`} style={{border:`1px solid ${t.line}`,borderLeft:`3px solid ${t.ink}`}}>
                  <div className={`eyebrow ${t.tp} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".06em"}}>{STR[lang].m_ruleH}</div>
                  <p className={`mt-2.5 text-[15px] ${t.ts} ${readCls(lang)}`} style={{lineHeight:1.6}}>{STR[lang].m_rule}</p>
                </div>
                <div className={`mt-7 eyebrow ${t.blind} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".06em"}}>{STR[lang].m_aiH}</div>
                <p className={`mt-2.5 text-[15px] ${t.ts} ${readCls(lang)}`} style={{lineHeight:1.62,maxWidth:"62ch"}}>{STR[lang].m_ai}</p>
                <div className={`mt-7 eyebrow ${t.blind} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".06em"}}>{STR[lang].m_rateH}</div>
                <p className={`mt-2.5 mb-3 text-[14px] ${t.ts} ${readCls(lang)}`} style={{lineHeight:1.55}}>{STR[lang].m_rateLede}</p>
                <div className="grid sm:grid-cols-2" style={{border:`1px solid ${t.line}`}}>
                  {SIGNALS.map((sig,i)=>(
                    <div key={i} className={`flex items-center justify-between gap-3 px-3.5 py-2.5 ${i<SIGNALS.length-(SIGNALS.length%2===0?2:1)?"border-b":""} ${i%2===0?"sm:border-r":""}`} style={{borderColor:t.line}}>
                      <span className={`text-[13px] ${t.ts} ${readCls(lang)}`}>{sig[lang]||sig.en}</span>
                      <span className={`mono text-[12px] font-semibold ${t.blind}`}>{sig.w}%</span>
                    </div>
                  ))}
                </div>
                <p className={`mt-3 text-[12px] ${t.tf} ${isHi(lang)}`}>{STR[lang].m_rateFoot}</p>
              </div>
              {/* rail */}
              <div className="mt-6 lg:mt-0 lg:pl-8 space-y-6">
                <div>
                  <div className={`eyebrow mb-3 ${t.blind} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".06em"}}>{STR[lang].m_readH}</div>
                  <ul className="space-y-3">{bullets.map((b,i)=>(
                    <li key={i} className={`relative pl-5 text-[13.5px] ${t.ts} ${readCls(lang)}`} style={{lineHeight:1.55}}><span style={{position:"absolute",left:2,top:8,width:6,height:6,background:bulletColors[i]||t.ink}}/>{b}</li>
                  ))}</ul>
                </div>
                <div style={{border:`1px solid #E0CBB9`}} className={`${t.blindSoft} p-4`}>
                  <div className={`eyebrow ${t.blind} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".06em"}}>{STR[lang].m_appealH}</div>
                  <p className={`mt-2 text-[13.5px] ${t.blind} ${readCls(lang)}`} style={{lineHeight:1.55}}>{STR[lang].m_appeal}</p>
                  <button onClick={()=>go&&go("contact")} className={`mt-3 text-[10px] font-semibold uppercase ${t.blind} ${lang==="hi"?"deva":""}`} style={{border:"1px solid currentColor",padding:"8px 13px",letterSpacing:lang==="hi"?0:".05em"}}>{lang==="hi"?"सुधार भेजें":"File a correction"}</button>
                </div>
                <p className={`text-[11.5px] ${t.tf} ${isHi(lang)}`} style={{lineHeight:1.5}}>{STR[lang].footIndependence}</p>
              </div>
            </div>
            {/* deeper method rows (kept for completeness) */}
            <div className="mt-8 max-w-3xl">
              <Row h={STR[lang].m_orderH}>{STR[lang].m_order}</Row>
              <Row h={STR[lang].m_freshH}>{STR[lang].m_fresh}</Row>
              {a.total!=null && <Row h={STR[lang].m_gapH}>{gapText}</Row>}
              <Row h={STR[lang].m_axisH}>{STR[lang].m_axis}</Row>
              <Row h={STR[lang].m_partiesH}>{STR[lang].m_parties}</Row>
              <Row h={STR[lang].m_provH}>{STR[lang].m_prov}</Row>
            </div>
          </div>
        </PageWrap>
      );
    }
    function ContactPage({ t, lang }) {
      const [status,setStatus]=useState("idle");
      const [err,setErr]=useState("");
      // Arriving from a clicked ad box pre-selects "Advertise"; the flag is one-shot.
      const [topic,setTopic]=useState(()=>{ if(_adIntent){ _adIntent=false; return "advertise"; } return "rating"; });
      const L = lang==="hi" ? {
        title:"संपर्क करें", lede:"सवाल, सुधार या शिकायत? हमें लिखें, हम हर संदेश पढ़ते हैं।",
        name:"आपका नाम (वैकल्पिक)", email:"ईमेल", topicL:"विषय",
        msg:"आपका संदेश", send:"डेस्क को भेजें", sending:"भेजा जा रहा है…",
        ok:"धन्यवाद, आपका संदेश मिल गया। हम जल्द जवाब देंगे।",
        err:"संदेश नहीं भेजा जा सका। कृपया दोबारा प्रयास करें।",
        chips:{rating:"रेटिंग सुधार", outlet:"नया आउटलेट सुझाएँ", advertise:"विज्ञापन दें", general:"सामान्य"},
        ph:{rating:"आउटलेट, जिस रेटिंग से असहमत हैं, और 2-3 उदाहरण हेडलाइन बताएँ…", outlet:"आउटलेट का नाम, वेबसाइट, भाषा और वह किस ओर झुका लगता है…", advertise:"आपकी कंपनी/उत्पाद, बजट का अंदाज़ा और आप किस तरह का विज्ञापन चाहते हैं…", general:"आपका संदेश…"},
        railH:"रेटिंग पर असहमति?", rail:"हमें आउटलेट, जिस रेटिंग से आप असहमत हैं, और 2-3 उदाहरण हेडलाइन/लेख बताएँ। हम उसे छह-संकेत रूब्रिक के विरुद्ध फिर से देखेंगे।",
        emailH:"सीधा ईमेल", indep:"पक्ष एक स्वतंत्र परियोजना है और किसी दिखाए गए आउटलेट से संबद्ध नहीं है।"
      } : {
        title:"Contact", lede:"A question, a correction, or a complaint? Write to us, we read every message.",
        name:"Your name (optional)", email:"Email", topicL:"Topic",
        msg:"Your message", send:"Send to the desk", sending:"Sending…",
        ok:"Thank you, your message reached us. We'll reply soon.",
        err:"Could not send your message. Please try again.",
        chips:{rating:"Rating correction", outlet:"Suggest an outlet", advertise:"Advertise with Paksh", general:"General"},
        ph:{rating:"Name the outlet, the rating you dispute, and 2-3 example headlines…", outlet:"Outlet name, website, language, and where it seems to lean…", advertise:"Your company/product, rough budget, and the kind of placement you want…", general:"Your message…"},
        railH:"Disputing a rating?", rail:"Tell us the outlet, the rating you dispute, and 2-3 example headlines or articles. We'll re-review it against the six-signal rubric.",
        emailH:"Direct email", indep:"Paksh is an independent project and is not affiliated with any outlet shown."
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
          <div className="mx-auto max-w-[1180px]">
            {/* header */}
            <div className="pb-3" style={{borderBottom:`2px solid ${t.ink}`}}>
              <div className={`eyebrow ${t.tf} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".16em"}}>{lang==="hi"?"संपर्क व सुधार":"Contact & corrections"}</div>
              <h1 className={`headline mt-2.5 text-[30px] sm:text-[34px] ${t.tp} ${readCls(lang)}`} style={{letterSpacing:lang==="hi"?0:"-0.02em"}}>{lang==="hi"?"डेस्क को लिखें":"Write to the desk"}</h1>
            </div>
            <div className="mt-6 grid lg:grid-cols-[1.4fr_1fr]">
            <div className="lg:border-r lg:pr-8" style={{borderColor:t.line}}>
              {status==="ok" ? (
                <div className={`border p-5 ${t.border} ${t.surface}`}><p className={`text-[15px] font-medium ${t.tp} ${isHi(lang)}`}>{L.ok}</p></div>
              ) : (
                <form onSubmit={submit} className="space-y-4">
                  <input type="text" name="_gotcha" style={{display:"none"}} tabIndex="-1" autoComplete="off" />
                  <input type="hidden" name="_subject" value="New Paksh contact message" />
                  <input type="hidden" name="topic" value={L.chips[topic]} />
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div><label className={lbl}>{L.name}</label><input name="name" type="text" className={inp} /></div>
                    <div><label className={lbl}>{L.email}</label><input name="email" type="email" required className={inp} /></div>
                  </div>
                  <div><label className={lbl}>{lang==="hi"?"यह किस बारे में है?":"What's this about?"}</label>
                    <div className="flex flex-wrap gap-2">
                      {["rating","outlet","advertise","general"].map(k=>(
                        <button key={k} type="button" onClick={()=>setTopic(k)} className={`border px-3.5 py-1.5 eyebrow ${topic===k?`${t.cta} ${t.ctaT} border-transparent`:`${t.surface} ${t.border} ${t.ts} hover:${t.tp}`} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".08em"}}>{L.chips[k]}</button>
                      ))}
                    </div>
                  </div>
                  <div><label className={lbl}>{L.msg}</label><textarea name="message" required rows="6" placeholder={L.ph[topic]} className={inp} /></div>
                  {status==="error" && <p className="text-[13px] font-medium" style={{color:"#C0392B"}}>{err}</p>}
                  <button type="submit" disabled={status==="sending"} className={`rounded-full px-5 py-2.5 text-[14px] font-semibold ${t.cta} ${t.ctaT} disabled:opacity-60 ${isHi(lang)}`}>{status==="sending"?L.sending:L.send}</button>
                  <div className={`text-[11px] ${t.tf} ${isHi(lang)}`}>{lang==="hi"?"Formspree द्वारा वितरित · हम असली इनबॉक्स से जवाब देते हैं।":"Delivered by Formspree · we reply from a real inbox, usually within a few days."}</div>
                </form>
              )}
            </div>
            <aside className="mt-6 lg:mt-0 lg:pl-8 space-y-6">
              <div className={`border p-5 ${t.surface} ${t.border}`} style={{borderLeft:`3px solid #75442E`}}>
                <div className={`eyebrow ${t.blind} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{L.railH}</div>
                <p className={`mt-2 text-[13.5px] leading-[1.6] ${t.ts} ${readCls(lang)}`}>{L.rail}</p>
              </div>
              <div className={`border p-5 ${t.surface} ${t.border}`}>
                <div className={`eyebrow ${t.tf} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{L.emailH}</div>
                <a href="mailto:hello@paksh.news" className={`mt-2 block mono text-[13px] ${t.ts} hover:${t.tp}`}>hello@paksh.news</a>
              </div>
              <p className={`text-[12px] leading-[1.6] ${t.tf} ${isHi(lang)}`}>{L.indep}</p>
            </aside>
            </div>
          </div>
        </PageWrap>
      );
    }
    // Sponsor slot: renders NOTHING until SPONSOR.name is set (an empty "supported by" looks
    // broken). Drop <SponsorSlot .../> wherever you want the credit to appear once you sign one.
    function SponsorSlot({ t, lang, className }) {
      if (!SPONSOR.name) return null;
      const inner = (
        <span className={`inline-flex flex-wrap items-center justify-center gap-x-2 ${isHi(lang)}`}>
          <span className={`mono text-[10px] uppercase tracking-[0.16em] ${t.tf}`}>{lang==="hi"?"सहयोग":"Supported by"}</span>
          <span className={`text-[13px] font-semibold ${t.tp}`}>{SPONSOR.name}</span>
          {SPONSOR.line && <span className={`text-[12px] ${t.tf}`}>· {SPONSOR.line}</span>}
        </span>
      );
      return (
        <div className={`text-center ${className||""}`}>
          {SPONSOR.url
            ? <a href={SPONSOR.url} target="_blank" rel="nofollow noopener noreferrer" className="inline-block hover:opacity-80">{inner}</a>
            : inner}
        </div>
      );
    }
    function SupportPage({ t, lang, go }) {
      const [copied,setCopied]=useState(false);
      const copyUpi=()=>{ try{ navigator.clipboard.writeText(SUPPORT.upi); setCopied(true); setTimeout(()=>setCopied(false),1600); }catch(e){} };
      const L = lang==="hi" ? {
        title:"पक्ष का सहयोग करें",
        lede:"पक्ष एक स्वतंत्र परियोजना है, कोई पेवॉल नहीं, कोई ट्रैकिंग-आधारित विज्ञापन नहीं। हर खबर को हर पक्ष से दिखाना संसाधन माँगता है। यदि पक्ष आपके काम आता है, तो आपका छोटा-सा सहयोग इसे सबके लिए मुफ़्त और स्वतंत्र रखता है।",
        whyH:"आपका पैसा किसमें जाता है", why:"आउटलेट्स की कवरेज इकट्ठा करने, उन्हें एक ही खबर में समूहित करने, और तटस्थ सारांश तैयार करने की कंप्यूटिंग लागत में, ताकि पक्ष बिना विज्ञापनदाताओं या किसी पक्ष के दबाव के चलता रहे।",
        upiH:"UPI से सहयोग करें", upiPay:"UPI ऐप में खोलें", copy:"UPI ID कॉपी करें", copied:"कॉपी हो गया",
        linkBtn:"पक्ष का सहयोग करें", soonH:"सहयोग विकल्प जल्द ही",
        soon:"हम सुरक्षित भुगतान का तरीक़ा जोड़ रहे हैं। तब तक, हौसला-आफ़ज़ाई या साझेदारी के लिए हमें लिखें।",
        contact:"संपर्क करें →", noStrings:"कोई सदस्यता ज़रूरी नहीं · कोई कंटेंट पेवॉल के पीछे नहीं · जितना चाहें उतना दें।"
      } : {
        title:"Support Paksh",
        lede:"Paksh is an independent project, no paywall, no tracking-based advertising. Showing every story from every side takes real resources. If Paksh is useful to you, a small contribution keeps it free and independent for everyone.",
        whyH:"Where your money goes", why:"Into the computing cost of gathering outlets' coverage, grouping it into one story, and generating the neutral summaries, so Paksh can run without advertisers or any side leaning on it.",
        upiH:"Support via UPI", upiPay:"Open in a UPI app", copy:"Copy UPI ID", copied:"Copied",
        linkBtn:"Support Paksh", soonH:"Support options coming soon",
        soon:"We're setting up a secure way to contribute. Until then, please reach out to cheer us on or discuss a partnership.",
        contact:"Contact us →", noStrings:"No membership required · nothing hidden behind a paywall · give whatever you like."
      };
      const btn=`inline-flex items-center justify-center rounded-full px-5 py-2.5 text-[14px] font-semibold ${t.cta} ${t.ctaT} ${isHi(lang)}`;
      const btn2=`inline-flex items-center justify-center rounded-full border px-5 py-2.5 text-[14px] font-semibold ${t.border} ${t.ts} hover:${t.tp} ${isHi(lang)}`;
      return (
        <PageWrap>
          <div className="max-w-2xl">
            <h1 className={`headline text-[30px] sm:text-[40px] ${t.tp} ${readCls(lang)}`} style={{letterSpacing:lang==="hi"?0:"-0.018em"}}>{L.title}</h1>
            <p className={`mt-4 text-[16px] leading-[1.62] ${t.ts} ${readCls(lang)}`}>{L.lede}</p>

            {supportReady() ? (
              <div className={`mt-8 border p-6 ${t.surface} ${t.border}`}>
                {SUPPORT.upi && (
                  <div className="mb-5">
                    <div className={`eyebrow mb-2 ${t.tf} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{L.upiH}</div>
                    <div className="mb-3 flex flex-wrap gap-2">
                      {[99,299,999].map(a=>(
                        <a key={a} href={upiLink(a)} className={`inline-flex items-center justify-center border px-4 py-2 text-[15px] font-semibold ${t.border} ${t.ts} hover:${t.cta} hover:${t.ctaT}`}>₹{a}</a>
                      ))}
                    </div>
                    <div className="flex flex-wrap items-center gap-3">
                      <a href={upiLink()} className={btn}>{L.upiPay}</a>
                      <button onClick={copyUpi} className={btn2}>{copied?L.copied:L.copy}</button>
                      <span className={`mono text-[13px] ${t.ts}`}>{SUPPORT.upi}</span>
                    </div>
                    <p className={`mt-3 text-[12px] ${t.tf} ${isHi(lang)}`}>{lang==="hi"?"एक-बार UPI · कोई खाता या आवर्ती शुल्क नहीं · भुगतान आपके बैंक से होता है, पक्ष इसे संग्रहीत नहीं करता।":"One-time UPI · no account or recurring charge · handled by your bank, never stored by Paksh."}</p>
                  </div>
                )}
                {SUPPORT.url && <a href={SUPPORT.url} target="_blank" rel="noopener noreferrer" className={btn}>{L.linkBtn}</a>}
                <p className={`mt-5 text-[12.5px] ${t.tf} ${isHi(lang)}`}>{L.noStrings}</p>
              </div>
            ) : (
              <div className={`mt-8 border p-6 ${t.surface} ${t.border}`}>
                <div className={`headline text-[18px] ${t.tp} ${readCls(lang)}`}>{L.soonH}</div>
                <p className={`mt-2 text-[14px] leading-[1.6] ${t.ts} ${readCls(lang)}`}>{L.soon}</p>
                <button onClick={()=>go("contact")} className={`mt-4 ${btn2}`}>{L.contact}</button>
              </div>
            )}

            <div className={`mt-8 border-t pt-6 ${t.border}`}>
              <div className={`headline text-[18px] ${t.tp} ${readCls(lang)}`}>{L.whyH}</div>
              <p className={`mt-2 text-[14.5px] leading-[1.62] ${t.ts} ${readCls(lang)}`}>{L.why}</p>
            </div>
          </div>
        </PageWrap>
      );
    }
    function PrivacyPage({ t, lang, consent, setConsent }) {
      const Row=({h,children})=>(<div className={`border-b py-6 ${t.border}`}><h2 className={`headline text-[20px] ${t.tp} serif mb-2`}>{h}</h2><div className={`text-[15px] leading-[1.62] serif ${t.ts}`}>{children}</div></div>);
      const P = lang==="hi" ? {
        eyebrow:"गोपनीयता", title:"हम क्या इकट्ठा करते हैं, और क्या नहीं",
        lede:"पक्ष बिना निगरानी के पढ़ने के लिए बना है। मुख्य साइट बिना खाते और बिना ट्रैकिंग के चलती है। जो थोड़ा-बहुत हम इकट्ठा करते हैं वह सिर्फ़ साइट चलाने के लिए है, और आपकी अनुमति से आपके रीडिंग लेंस के लिए।",
        c1H:"सेल्फ-होस्टेड फ़ॉन्ट व कोड", c1:"फ़ॉन्ट और ऐप कोड पक्ष के अपने डोमेन से आते हैं, पेज लोड करने के लिए किसी तीसरे-पक्ष CDN से संपर्क नहीं होता।",
        c2H:"विज्ञापन", c2:"विज्ञापन क्लासिफ़ाइड-शैली के और गैर-वैयक्तिकृत हैं। कॉन्फ़िगर व घोषित होने तक कोई विज्ञापन नेटवर्क लोड नहीं होता, अभी स्लॉट निष्क्रिय प्लेसहोल्डर हैं।",
        c3H:"आपका रीडिंग लेंस", c3:"साइन इन करने पर आप जो खबरें खोलते हैं वे आपके खाते में दर्ज होती हैं ताकि आपका पढ़ने का संतुलन निकले। यह निजी है, बेचा नहीं जाता, और यह नहीं बदलता कि आपको कौन-सी खबरें दिखें।",
        anH:"गुमनाम एनालिटिक्स", anSub:"गोपनीयता-सम्मानित गिनती, कोई विज्ञापन-ट्रैकिंग नहीं",
        note1:"आप एनालिटिक्स बंद करके भी हर सुविधा इस्तेमाल कर सकते हैं। बंद करने पर आपकी विज़िट की सारी समग्र माप रुक जाती है।",
        note2:"डेटा के बारे में सवाल? लिखें"
      } : {
        eyebrow:"Privacy", title:"What we collect, and what we don't",
        lede:"Paksh is built to be read without surveillance. The core site works with no account and no tracking. What little we collect exists only to keep the site running and, if you opt in, to power your Reading Lens.",
        c1H:"Self-hosted fonts & code", c1:"Fonts and app code are served from Paksh's own domain, no third-party CDN is contacted just to load the page, so reading leaks nothing to outside servers.",
        c2H:"Advertising", c2:"Ads are classifieds-style and non-personalised. No ad network is loaded until it's configured and disclosed, today the slots are inert placeholders.",
        c3H:"Your Reading Lens", c3:"If you sign in, the stories you open are recorded to your account to compute your reading balance. It is private to you, never sold, and never used to change which stories you're shown.",
        anH:"Anonymous analytics", anSub:"Privacy-respecting counts, no ad tracking",
        note1:"You can switch analytics off and still use every feature. Turning it off stops all aggregate measurement of your visit.",
        note2:"Questions about your data? Write to"
      };
      const card=(h,body)=>(<div className={`${t.surface} p-4`} style={{border:`1px solid ${t.line}`}}><div className={`eyebrow ${t.tp} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".06em"}}>{h}</div><p className={`mt-2 text-[13.5px] ${t.ts} ${readCls(lang)}`} style={{lineHeight:1.55}}>{body}</p></div>);
      return (
        <PageWrap>
          <div className="mx-auto max-w-[1180px]">
            {/* header */}
            <div className="pb-3" style={{borderBottom:`2px solid ${t.ink}`}}>
              <div className={`eyebrow ${t.tf} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".16em"}}>{P.eyebrow}</div>
              <h1 className={`headline mt-2.5 text-[30px] sm:text-[36px] ${t.tp} ${readCls(lang)}`} style={{letterSpacing:lang==="hi"?0:"-0.02em"}}>{P.title}</h1>
            </div>
            {/* 1.6fr / 1fr explainer */}
            <div className="mt-6 grid lg:grid-cols-[1.6fr_1fr]">
              <div className="lg:border-r lg:pr-8" style={{borderColor:t.line}}>
                <p className={`text-[16px] ${t.ts} ${readCls(lang)}`} style={{lineHeight:1.62,maxWidth:"62ch"}}>{P.lede}</p>
                <div className="mt-5 space-y-3.5">{card(P.c1H,P.c1)}{card(P.c2H,P.c2)}{card(P.c3H,P.c3)}</div>
              </div>
              <div className="mt-6 lg:mt-0 lg:pl-8 space-y-4">
                {setConsent && (
                  <div className={`${t.surface} p-4`} style={{border:`1px solid ${t.line}`}}>
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0"><div className={`text-[13px] font-semibold ${t.tp} ${readCls(lang)}`}>{P.anH}</div><div className={`mt-0.5 text-[10.5px] ${t.tf} ${isHi(lang)}`}>{P.anSub}</div></div>
                      <Toggle on={consent==="granted"} onChange={v=>setConsent(v?"granted":"denied")} label={P.anH} t={t} />
                    </div>
                  </div>
                )}
                <p className={`text-[12.5px] ${t.tf} ${readCls(lang)}`} style={{lineHeight:1.55}}>{P.note1}</p>
                <p className={`text-[11.5px] ${t.tf} ${isHi(lang)}`} style={{lineHeight:1.5}}>{P.note2} <a href="mailto:hello@paksh.news" className={`font-semibold ${t.ts} hover:${t.tp}`}>hello@paksh.news</a>.</p>
              </div>
            </div>
            {/* full legal policy */}
            <div className="mt-10 max-w-3xl">
            <h2 className={`headline text-[20px] ${t.tp} serif`}>Privacy Policy</h2>
            <p className={`mb-1 mt-2 text-[13px] ${t.tf}`}>Last updated: 9 August 2026 · Operated by Redstocks Technology LLP</p>
            {lang==="hi" && <p className={`mb-2 text-[12.5px] deva ${t.tf}`}>पूरी गोपनीयता नीति अंग्रेज़ी में उपलब्ध है।</p>}
            <Row h="Who we are">Paksh (पक्ष) is a media-transparency service that groups how different Indian outlets cover the same news story and shows the spread of that coverage across the political spectrum.</Row>
            <Row h="What we collect">When you use our contact form, we receive the email address and message you choose to send, so that we can reply; that form is processed on our behalf by Formspree. As with most websites, our host (Vercel) keeps standard technical logs (such as IP address and browser type) briefly, for security and reliability. With your consent, we also use Vercel’s privacy-first, cookieless Web Analytics to understand, only in aggregate, how the site is used: which stories are read, whether people compare sides, mobile versus desktop, and the like. It does not use cookies, does not identify you, and does not follow you across other websites. If you decline, none of this is collected.</Row>
            <Row h="Cookies and tracking">Paksh sets no advertising cookies and does not track you across other websites. Our analytics (Vercel Web Analytics) is cookieless and stores nothing on your device. You choose whether to allow it in the banner shown on your first visit, and declining is fully respected for the whole session. If we introduce advertising (e.g. through Google AdSense) in future, we will update this policy and ask for your consent before any advertising cookies are set.</Row>
            <Row h="How we use information">To respond to your messages, to keep the site secure and reliable, and, from consented, aggregate, non-identifying usage, to understand how readers engage with coverage, improve Paksh, and inform Redstocks Technology’s research. We do not sell your personal information, and we do not build a profile of you or track you across your devices.</Row>
            <Row h="Third parties">We rely on Formspree (which processes contact-form messages) and Vercel (which hosts the site and provides its cookieless Web Analytics). If we add advertising in future, Google would also process data under its own policy, and we will note that here before it happens.</Row>
            <Row h="Your choices">You may ask us to access or delete the information you sent through the contact form. Reach us any time via the Contact page.</Row>
            <Row h="Children">Paksh is a general news service and is not directed at children.</Row>
            <Row h="Changes">We may update this policy from time to time; material changes will be reflected by the date shown above.</Row>
            </div>
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

    /* ---------------- account + accessibility UI ---------------- */
    // The 42x24 switch from the design: 1px ink track, 20px knob, ink-fill when on.
    function Toggle({ on, onChange, label, t }) {
      return (
        <button type="button" role="switch" aria-checked={on?"true":"false"} aria-label={label||""} onClick={()=>onChange(!on)}
          className="relative shrink-0" style={{width:42,height:24,border:`1px solid ${t.ink}`,background:on?t.ink:"transparent"}}>
          <span style={{position:"absolute",top:1,left:on?19:1,width:20,height:20,background:on?(t.gap||"#F4F1EA"):t.ink,transition:"left .18s cubic-bezier(.4,0,.2,1)"}}/>
        </button>
      );
    }
    // Segmented choice (e.g. Standard / Large / Classic), active side ink-filled.
    function SegChoice({ value, options, onChange, t, lang }) {
      return (
        <div className="inline-flex" style={{border:`1px solid ${t.ink}`}}>
          {options.map(([k,label],i)=>{ const on=value===k;
            return <button key={k} type="button" onClick={()=>onChange(k)} className={lang==="hi"?"deva":""}
              style={{padding:"6px 14px",font:"600 12px 'IBM Plex Sans',sans-serif",borderLeft:i>0?`1px solid ${t.ink}`:"none",
                background:on?t.ink:"transparent",color:on?(t.gap||"#F4F1EA"):t.ink}}>{label}</button>;
          })}
        </div>
      );
    }
    // Read-aloud control (browser speech synthesis; no network, no library). Renders nothing
    // where speech isn't available. Shown next to summaries when "Read aloud" is on in Settings.
    function ListenButton({ text, lang, t }) {
      const [on,setOn]=useState(false);
      useEffect(()=>()=>stopSpeak(),[]);
      if(!canSpeak()) return null;
      const toggle=()=>{ if(on){ stopSpeak(); setOn(false); } else { speak(text,lang); setOn(true); } };
      return <button type="button" onClick={toggle} className={`inline-flex items-center gap-1.5 border px-2.5 py-1 mono text-[10.5px] uppercase tracking-wide ${t.border} ${t.ts} hover:${t.tp} ${lang==="hi"?"deva":""}`}>{on?"■":"▶"} {lang==="hi"?(on?"रोकें":"सुनें"):(on?"Stop":"Listen")}</button>;
    }
    const prettyAuthErr=(ex,L)=>{ const m=String((ex&&ex.message)||"").toLowerCase();
      if(m.includes("rate limit")||m.includes("too many")) return L.errRate;
      if(m.includes("invalid")||m.includes("expired")||m.includes("token")) return L.errCode;
      if(m.includes("signups not allowed")||m.includes("not allowed")) return L.errClosed;
      if(m.includes("failed to fetch")||m.includes("networkerror")) return L.errNet;
      return L.errGeneric; };

    // LOGIN / SIGN-UP - "the subscription desk". Email -> emailed sign-in code -> in. No
    // password, no Google, no phone. The code length follows the Supabase Auth setting (6-8
    // digits); the input accepts up to 10. Both tabs use one OTP flow (create_user = new+returning).
    function LoginPage({ t, lang, go, onAuthed }) {
      const [mode,setMode]=useState("signin");   // signin | signup
      const [method,setMethod]=useState("password"); // password | code
      const [step,setStep]=useState("email");     // (code method) email | code
      const [email,setEmail]=useState("");
      const [password,setPassword]=useState("");
      const [code,setCode]=useState("");
      const [busy,setBusy]=useState(false);
      const [err,setErr]=useState("");
      const [note,setNote]=useState("");
      const [cool,setCool]=useState(0);            // resend cooldown seconds
      useEffect(()=>{ if(cool<=0) return; const id=setInterval(()=>setCool(c=>c-1),1000); return ()=>clearInterval(id); },[cool]);
      const L = lang==="hi" ? {
        signin:"साइन इन", signup:"खाता बनाएँ",
        lede:"मुफ़्त, कोई पेवॉल नहीं। खाता सिर्फ़ निजीकरण जोड़ता है, पक्ष बिना खाते के भी पूरी तरह पढ़ा जा सकता है।",
        emailL:"ईमेल", emailP:"you@example.com", pwL:"पासवर्ड", pwP:"कम से कम 8 अक्षर",
        signinBtn:"साइन इन करें", createBtn:"खाता बनाएँ", working:"हो रहा है…",
        sendBtn:"मुझे साइन-इन कोड ईमेल करें", sending:"भेजा जा रहा है…",
        codeL:"ईमेल पर आया साइन-इन कोड", codeP:"कोड", verifyBtn:"साइन इन करें", verifying:"जाँच हो रही है…",
        sentTo:"कोड भेजा गया", change:"ईमेल बदलें", resend:"कोड फिर भेजें", resent:"नया कोड भेज दिया।", resendIn:"फिर भेजें",
        useCode:"पासवर्ड के बजाय ईमेल कोड इस्तेमाल करें", usePw:"पासवर्ड इस्तेमाल करें",
        confirm:"पुष्टि करने के लिए अपना ईमेल देखें, फिर साइन इन करें।",
        p1:"आप जो खबरें खोलते हैं उससे बनता आपका अपना ‘रीडिंग लेंस’, सिर्फ़ आपके लिए।",
        p2:"पढ़ने की सुलभता सेटिंग्स हर डिवाइस पर सहेजी जाती हैं।", p3:"पसंदीदा खबरें अख़बार-कतरन की तरह सहेजें।",
        propsH:"खाता क्या जोड़ता है",
        errRate:"बहुत सारे प्रयास। कृपया थोड़ी देर बाद फिर कोशिश करें।",
        errCode:"कोड ग़लत या समय-समाप्त। कृपया दोबारा जाँचें या नया कोड मँगाएँ।",
        errPw:"ईमेल या पासवर्ड ग़लत।", errWeak:"पासवर्ड कम से कम 8 अक्षर का हो।",
        errClosed:"अभी नए साइन-अप बंद हैं।", errNet:"नेटवर्क समस्या। कनेक्शन जाँचें।",
        errGeneric:"कुछ ग़लत हुआ। कृपया दोबारा प्रयास करें।",
        off:"खाते अभी उपलब्ध नहीं हैं।", back:"वापस"
      } : {
        signin:"Sign in", signup:"Create account",
        lede:"Free, no paywall. An account only adds personalisation, Paksh stays fully readable without one.",
        emailL:"Email", emailP:"you@example.com", pwL:"Password", pwP:"At least 8 characters",
        signinBtn:"Sign in", createBtn:"Create account", working:"Working…",
        sendBtn:"Email me a sign-in code", sending:"Sending…",
        codeL:"Sign-in code from your email", codeP:"Sign-in code", verifyBtn:"Sign in", verifying:"Checking…",
        sentTo:"Code sent to", change:"Change email", resend:"Resend code", resent:"New code sent.", resendIn:"Resend in",
        useCode:"Use an email code instead", usePw:"Use a password",
        confirm:"Check your email to confirm, then sign in.",
        p1:"Your own Reading Lens, built from the stories you open, visible only to you.",
        p2:"Your reading & accessibility settings saved across devices.", p3:"Clip and save stories like newspaper cuttings.",
        propsH:"What an account adds",
        errRate:"Too many attempts. Please wait a little and try again.",
        errCode:"That code is wrong or expired. Re-check it or request a new one.",
        errPw:"Wrong email or password.", errWeak:"Password must be at least 8 characters.",
        errClosed:"New sign-ups are closed right now.", errNet:"Network problem. Check your connection.",
        errGeneric:"Something went wrong. Please try again.",
        off:"Accounts aren't available yet.", back:"Back"
      };
      // Password sign in / create account.
      async function pwSubmit(e){ e.preventDefault(); if(!email.trim())return; setErr(""); setNote("");
        if(password.length<8){ setErr(L.errWeak); return; } setBusy(true);
        try{ if(mode==="signup"){ const r=await authPasswordSignUp(email.trim(),password); if(r.session){ onAuthed(r.session); } else { setNote(L.confirm); } }
          else { const s=await authPasswordSignIn(email.trim(),password); onAuthed(s); } }
        catch(ex){ const m=String((ex&&ex.message)||"").toLowerCase();
          setErr(m.includes("invalid login")||m.includes("credential")?L.errPw:m.includes("already registered")?(lang==="hi"?"यह ईमेल पहले से पंजीकृत है, साइन इन करें।":"That email is already registered, sign in instead."):prettyAuthErr(ex,L)); }
        finally{ setBusy(false); } }
      // Email OTP: send / verify / resend (with cooldown + feedback).
      async function send(e){ if(e&&e.preventDefault)e.preventDefault(); if(!email.trim())return; setErr(""); setNote(""); setBusy(true);
        try{ await authSendCode(email.trim()); setStep("code"); setNote(L.resent); setCool(30); }catch(ex){ setErr(prettyAuthErr(ex,L)); }finally{ setBusy(false); } }
      async function verify(e){ e.preventDefault(); if(!code.trim())return; setErr(""); setBusy(true);
        try{ const s=await authVerifyCode(email.trim(), code.trim()); onAuthed(s); }catch(ex){ setErr(prettyAuthErr(ex,L)); }finally{ setBusy(false); } }
      const inp=`w-full border px-3.5 py-2.5 text-[15px] outline-none ${t.surface} ${t.border} focus:border-[#15140F] ${t.tp}`;
      const lblc=`mb-1.5 block text-[12.5px] font-semibold ${t.ts} ${isHi(lang)}`;
      const btn=`w-full rounded-full px-5 py-2.5 text-[14px] font-semibold ${t.cta} ${t.ctaT} disabled:opacity-60 ${isHi(lang)}`;
      const link=`text-[12.5px] underline underline-offset-2 ${t.tf} hover:${t.tp} ${isHi(lang)}`;
      const props=(
        <div>
          <div className={`eyebrow ${t.tf} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{L.propsH}</div>
          <ul className="mt-4 space-y-3">{[L.p1,L.p2,L.p3].map((p,i)=>(
            <li key={i} className={`flex gap-2.5 text-[14px] ${t.ts} ${readCls(lang)}`} style={{lineHeight:lang==="hi"?1.7:1.55}}><span className="mt-[9px] h-1.5 w-1.5 shrink-0" style={{background:t.ink}}/>{p}</li>))}</ul>
          <p className={`mt-5 text-[12.5px] leading-[1.6] ${t.tf} ${isHi(lang)}`}>{L.lede}</p>
        </div>
      );
      const form=(
        <div>
          <div className="inline-flex mb-6" style={{border:`1px solid ${t.ink}`}}>
            {[["signin",L.signin],["signup",L.signup]].map(([k,label],i)=>{ const on=mode===k;
              return <button key={k} type="button" onClick={()=>{setMode(k);setErr("");setNote("");}} className={lang==="hi"?"deva":""}
                style={{padding:"7px 16px",font:"600 12px 'IBM Plex Sans',sans-serif",borderLeft:i>0?`1px solid ${t.ink}`:"none",background:on?t.ink:"transparent",color:on?(t.gap||"#F4F1EA"):t.ink}}>{label}</button>;
            })}
          </div>
          {!authOn() ? <p className={`text-[14px] ${t.tf} ${isHi(lang)}`}>{L.off}</p>
          : method==="password" ? (
            <form onSubmit={pwSubmit} className="space-y-4">
              <div><label className={lblc}>{L.emailL}</label><input value={email} onChange={e=>setEmail(e.target.value)} type="email" required autoFocus placeholder={L.emailP} className={inp} inputMode="email" autoComplete="email" /></div>
              <div><label className={lblc}>{L.pwL}</label><input value={password} onChange={e=>setPassword(e.target.value)} type="password" required placeholder={L.pwP} className={inp} autoComplete={mode==="signup"?"new-password":"current-password"} /></div>
              {err && <p className="text-[13px] font-medium" style={{color:"#C0392B"}}>{err}</p>}
              {note && <p className={`text-[13px] font-medium ${t.blind} ${isHi(lang)}`}>{note}</p>}
              <button type="submit" disabled={busy} className={btn}>{busy?L.working:(mode==="signup"?L.createBtn:L.signinBtn)}</button>
              <button type="button" onClick={()=>{setMethod("code");setErr("");setNote("");setStep("email");}} className={link}>{L.useCode}</button>
            </form>
          ) : step==="email" ? (
            <form onSubmit={send} className="space-y-4">
              <div><label className={lblc}>{L.emailL}</label><input value={email} onChange={e=>setEmail(e.target.value)} type="email" required autoFocus placeholder={L.emailP} className={inp} inputMode="email" autoComplete="email" /></div>
              {err && <p className="text-[13px] font-medium" style={{color:"#C0392B"}}>{err}</p>}
              <button type="submit" disabled={busy} className={btn}>{busy?L.sending:L.sendBtn}</button>
              <button type="button" onClick={()=>{setMethod("password");setErr("");setNote("");}} className={link}>{L.usePw}</button>
            </form>
          ) : (
            <form onSubmit={verify} className="space-y-4">
              <p className={`text-[13px] ${t.ts} ${isHi(lang)}`}>{L.sentTo} <span className="font-semibold">{email}</span>.</p>
              <div><label className={lblc}>{L.codeL}</label><input value={code} onChange={e=>setCode(e.target.value.replace(/[^0-9]/g,"").slice(0,10))} required autoFocus placeholder={L.codeP} className={`${inp} mono tracking-[0.3em] text-center text-[20px]`} inputMode="numeric" autoComplete="one-time-code" maxLength={10} /></div>
              {err && <p className="text-[13px] font-medium" style={{color:"#C0392B"}}>{err}</p>}
              {note && !err && <p className={`text-[13px] font-medium ${t.blind} ${isHi(lang)}`}>{note}</p>}
              <button type="submit" disabled={busy} className={btn}>{busy?L.verifying:L.verifyBtn}</button>
              <div className="flex items-center justify-between">
                <button type="button" onClick={()=>{setStep("email");setCode("");setErr("");setNote("");}} className={link}>{L.change}</button>
                <button type="button" onClick={send} disabled={busy||cool>0} className={link}>{cool>0?`${L.resendIn} ${cool}s`:L.resend}</button>
              </div>
            </form>
          )}
        </div>
      );
      return (
        <PageWrap>
          <button onClick={()=>go("home")} className={`mb-6 inline-flex items-center gap-1.5 eyebrow ${t.ts} hover:${t.tp}`} style={{letterSpacing:lang==="hi"?0:".1em"}}><ArrowLeft size={14}/> {L.back}</button>
          <div className={`mx-auto max-w-[760px] border md:grid md:grid-cols-2 ${t.border}`}>
            <div className="p-6 sm:p-8">
              <h1 className={`headline text-[26px] sm:text-[30px] ${t.tp} ${readCls(lang)}`} style={{letterSpacing:lang==="hi"?0:"-0.018em"}}>{mode==="signup"?L.signup:L.signin}</h1>
              <div className="mt-6">{form}</div>
            </div>
            <div className={`hidden md:block p-6 sm:p-8 border-l ${t.border} ${t.surface}`}>{props}</div>
          </div>
        </PageWrap>
      );
    }

    // SETTINGS - account + accessibility that actually works on every page (applied to <html>).
    function SettingsPage({ t, lang, setLang, a11y, setA11y, auth, onSignOut, consent, setConsent, go }) {
      const L = lang==="hi" ? {
        title:"सेटिंग्स", acc:"खाता", free:"मुफ़्त", email:"ईमेल", signout:"साइन आउट", support:"पक्ष का सहयोग करें →",
        guestH:"साइन इन नहीं हैं", guestP:"खाता निजीकरण जोड़ता है (रीडिंग लेंस, सहेजी खबरें)। खबरें हमेशा बिना खाते के खुली रहती हैं।", signin:"साइन इन",
        readLang:"डिफ़ॉल्ट पढ़ने की भाषा", a11yH:"पढ़ने और सुलभता",
        tSize:"अक्षर आकार", tStd:"मानक", tLg:"बड़ा", tCl:"क्लासिक",
        hc:"उच्च कंट्रास्ट", hcS:"गाढ़ा पाठ, सफ़ेद पृष्ठभूमि।",
        dys:"डिस्लेक्सिया-अनुकूल फ़ॉन्ट", dysS:"अधिक सुपाठ्य अक्षर-आकृतियाँ।",
        aloud:"ज़ोर से पढ़ें", aloudS:"सारांश के पास ‘सुनें’ बटन जोड़ता है।",
        anon:"गुमनाम एनालिटिक्स", anonS:"गोपनीयता-सम्मानित, कुकी-रहित। सब कुछ इसके बिना भी चलता है।",
        prevH:"झलक", prevBody:"यह नमूना पाठ ऊपर चुनी गई सेटिंग्स के साथ तुरंत बदलता है, ताकि असर तुरंत दिखे। पक्ष हर खबर को हर पक्ष से दिखाता है।"
      } : {
        title:"Settings", acc:"Account", free:"Free", email:"Email", signout:"Sign out", support:"Support Paksh →",
        guestH:"Not signed in", guestP:"An account adds personalisation (Reading Lens, Saved). The news itself is always open, no account needed.", signin:"Sign in",
        readLang:"Default reading language", a11yH:"Reading & accessibility",
        tSize:"Text size", tStd:"Standard", tLg:"Large", tCl:"Classic",
        hc:"High contrast", hcS:"Darker text on a white surface.",
        dys:"Dyslexia-friendly font", dysS:"More distinguishable letterforms.",
        aloud:"Read aloud", aloudS:"Adds a ‘Listen’ button next to summaries.",
        anon:"Anonymous analytics", anonS:"Privacy-respecting, cookieless. Everything works with it off.",
        prevH:"Preview", prevBody:"This sample text re-renders with the settings above so you can see the effect immediately. Paksh shows every side of every story."
      };
      const set=(k,v)=>setA11y(Object.assign({},a11y,{[k]:v}));
      const card=`border ${t.border} ${t.surface}`;
      const row=(label,sub,ctrl)=>(
        <div className={`flex items-center justify-between gap-4 border-b py-4 ${t.border} last:border-b-0`}>
          <div className="min-w-0"><div className={`text-[14px] font-semibold ${t.tp} ${isHi(lang)}`}>{label}</div>{sub&&<div className={`mt-0.5 text-[12.5px] ${t.tf} ${isHi(lang)}`}>{sub}</div>}</div>
          <div className="shrink-0">{ctrl}</div>
        </div>
      );
      const sample={ standard:{h:20,b:15,lh:1.62}, large:{h:24,b:18,lh:1.7}, classic:{h:29,b:22,lh:1.8} }[a11y.textSize]||{h:20,b:15,lh:1.62};
      return (
        <PageWrap>
          <div className="max-w-2xl">
            <h1 className={`headline text-[30px] sm:text-[40px] ${t.tp} ${readCls(lang)}`} style={{letterSpacing:lang==="hi"?0:"-0.018em"}}>{L.title}</h1>

            {/* Account */}
            <div className="mt-7">
              <div className={`eyebrow mb-3 ${t.tp} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{L.acc}</div>
              {auth ? (
                <div className={`p-5 ${card}`}>
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0"><div className={`mono text-[10px] uppercase tracking-wide ${t.tf}`}>{L.email}</div><div className={`truncate text-[15px] font-semibold ${t.tp}`}>{(auth.user&&auth.user.email)||""}</div></div>
                    <span className={`shrink-0 rounded mono px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${t.chip} ${t.ts}`}>{L.free}</span>
                  </div>
                  <div className={`mt-4 border-t pt-4 ${t.border}`}>{row(L.readLang,null,
                    <SegChoice value={lang} options={[["en","EN"],["hi","हिं"]]} onChange={setLang} t={t} lang={lang} />)}</div>
                  <div className="mt-4 flex flex-wrap items-center gap-3">
                    <button onClick={()=>go("support")} className={`text-[13px] font-semibold ${t.blind} hover:underline ${isHi(lang)}`}>{L.support}</button>
                    <button onClick={onSignOut} className={`ml-auto border px-4 py-2 text-[13px] font-semibold ${t.border} ${t.ts} hover:${t.tp} ${isHi(lang)}`}>{L.signout}</button>
                  </div>
                </div>
              ) : (
                <div className={`p-5 ${card}`}>
                  <div className={`text-[15px] font-semibold ${t.tp} ${isHi(lang)}`}>{L.guestH}</div>
                  <p className={`mt-1.5 text-[13px] ${t.tf} ${isHi(lang)}`}>{L.guestP}</p>
                  {authOn() && <button onClick={()=>go("login")} className={`mt-4 rounded-full px-5 py-2 text-[13px] font-semibold ${t.cta} ${t.ctaT} ${isHi(lang)}`}>{L.signin}</button>}
                </div>
              )}
            </div>

            {/* Accessibility */}
            <div className="mt-8">
              <div className={`eyebrow mb-3 ${t.tp} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{L.a11yH}</div>
              <div className={`px-5 ${card}`}>
                {row(L.tSize,null,<SegChoice value={a11y.textSize} options={[["standard",L.tStd],["large",L.tLg],["classic",L.tCl]]} onChange={v=>set("textSize",v)} t={t} lang={lang} />)}
                {row(L.hc,L.hcS,<Toggle on={a11y.highContrast} onChange={v=>set("highContrast",v)} label={L.hc} t={t} />)}
                {row(L.dys,L.dysS,<Toggle on={a11y.dyslexiaFont} onChange={v=>set("dyslexiaFont",v)} label={L.dys} t={t} />)}
                {row(L.aloud,L.aloudS,<Toggle on={a11y.readAloud} onChange={v=>set("readAloud",v)} label={L.aloud} t={t} />)}
                {row(L.anon,L.anonS,<Toggle on={consent==="granted"} onChange={v=>setConsent(v?"granted":"denied")} label={L.anon} t={t} />)}
              </div>
            </div>

            {/* Live preview */}
            <div className="mt-8">
              <div className={`eyebrow mb-3 ${t.tp} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{L.prevH}</div>
              <div className={`p-5 ${card}`}>
                <h3 className={`headline ${t.tp} ${readCls(lang)}`} style={{fontSize:sample.h,lineHeight:1.2}}>{lang==="hi"?"हर खबर, हर पक्ष":"Every story, every side"}</h3>
                <p className={`mt-2 ${t.ts} ${readCls(lang)}`} style={{fontSize:sample.b,lineHeight:sample.lh}}>{L.prevBody}</p>
                {a11y.readAloud && <div className="mt-3"><ListenButton text={(lang==="hi"?"हर खबर, हर पक्ष। ":"Every story, every side. ")+L.prevBody} lang={lang} t={t} /></div>}
              </div>
            </div>
          </div>
        </PageWrap>
      );
    }

    // ACCOUNT - the avatar's landing. Signed-in menu; a guest is sent to sign in.
    function AccountPage({ t, lang, auth, go, onSignOut }) {
      const L = lang==="hi" ? { title:"मेरा खाता", hi:"नमस्ते", lens:"मेरा रीडिंग लेंस", saved:"सहेजी खबरें", settings:"सेटिंग्स और सुलभता", support:"पक्ष का सहयोग करें", signout:"साइन आउट",
        guestP:"अपना रीडिंग लेंस और सहेजी खबरें देखने के लिए साइन इन करें।", signin:"साइन इन" }
        : { title:"My account", hi:"Hello", lens:"My Reading Lens", saved:"Saved", settings:"Settings & accessibility", support:"Support Paksh", signout:"Sign out",
        guestP:"Sign in to see your Reading Lens and saved stories.", signin:"Sign in" };
      const item=(label,onClick)=>(<button onClick={onClick} className={`flex w-full items-center justify-between border p-4 text-left ${t.surface} ${t.border} hover:${t.soft}`}><span className={`text-[14.5px] font-semibold ${t.tp} ${isHi(lang)}`}>{label}</span><ChevronRight size={16} className={t.tf}/></button>);
      return (
        <PageWrap>
          <div className="max-w-xl">
            <h1 className={`headline text-[30px] sm:text-[40px] ${t.tp} ${readCls(lang)}`} style={{letterSpacing:lang==="hi"?0:"-0.018em"}}>{L.title}</h1>
            {auth ? (
              <>
                <p className={`mt-3 text-[15px] ${t.ts} ${isHi(lang)}`}>{L.hi}, <span className="font-semibold">{(auth.user&&auth.user.email)||""}</span></p>
                <div className="mt-6 grid gap-3">
                  {item(L.lens,()=>go("lens"))}
                  {item(L.saved,()=>go("saved"))}
                  {item(L.settings,()=>go("settings"))}
                  {item(L.support,()=>go("support"))}
                </div>
                <button onClick={onSignOut} className={`mt-6 border px-4 py-2 text-[13px] font-semibold ${t.border} ${t.ts} hover:${t.tp} ${isHi(lang)}`}>{L.signout}</button>
              </>
            ) : (
              <>
                <p className={`mt-3 text-[15px] ${t.ts} ${isHi(lang)}`}>{L.guestP}</p>
                {authOn() && <button onClick={()=>go("login")} className={`mt-5 rounded-full px-5 py-2.5 text-[14px] font-semibold ${t.cta} ${t.ctaT} ${isHi(lang)}`}>{L.signin}</button>}
              </>
            )}
          </div>
        </PageWrap>
      );
    }

    // 404 - the "Misprint" newspaper treatment.
    function NotFoundPage({ t, lang, go }) {
      const L = lang==="hi" ? { kick:"त्रुटि 404", h:"यह पन्ना कभी दाख़िल ही नहीं हुआ।", p:"जो पता आपने खोला वह हमारे पास नहीं है, शायद कड़ी पुरानी हो या पता ग़लत टाइप हुआ हो।", home:"मुख पृष्ठ पर लौटें", links:"त्वरित कड़ियाँ" }
        : { kick:"Error 404", h:"This page was never filed.", p:"The address you opened isn't one we have, the link may be old, or the URL mistyped.", home:"Back to the front page", links:"Quick links" };
      const quick=[["blindspot",STR[lang].navOS],["sources",STR[lang].navSrc],["about",STR[lang].navMethod],["search",ui("searchTab",lang)]];
      return (
        <PageWrap>
          <div className="mx-auto max-w-[720px] py-8 text-center">
            <div className={`eyebrow ${t.blind} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".2em"}}>{L.kick}</div>
            <div className="my-5" style={{borderTop:`2px solid ${t.ink}`,borderBottom:`1px solid ${t.ink}`,padding:"20px 0"}}>
              <h1 className={`headline text-[30px] sm:text-[42px] ${t.tp} ${readCls(lang)}`} style={{letterSpacing:lang==="hi"?0:"-0.02em"}}>{L.h}</h1>
            </div>
            <p className={`mx-auto max-w-[52ch] text-[15px] ${t.ts} ${readCls(lang)}`} style={{lineHeight:lang==="hi"?1.75:1.6}}>{L.p}</p>
            <button onClick={()=>go("home")} className={`mt-7 rounded-full px-5 py-2.5 text-[14px] font-semibold ${t.cta} ${t.ctaT} ${isHi(lang)}`}>{L.home}</button>
            <div className={`mt-9 border-t pt-5 ${t.border}`}>
              <div className={`eyebrow mb-3 ${t.tf} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{L.links}</div>
              <div className="flex flex-wrap justify-center gap-x-6 gap-y-2">
                {quick.map(([k,l])=>(<button key={k} onClick={()=>go(k)} className={`text-[13px] font-medium ${t.ts} hover:${t.tp} ${lang==="hi"?"deva":""}`}>{l}</button>))}
              </div>
            </div>
          </div>
        </PageWrap>
      );
    }

    // Save/clip toggle. Ink-filled when saved. Guests are nudged to sign in by the handler.
    function SaveButton({ story, saved, onToggle, t, lang }) {
      const on=saved.has(String(story.id));
      return <button type="button" onClick={()=>onToggle(story)} aria-pressed={on?"true":"false"}
        className={`inline-flex items-center gap-1.5 border px-3 py-1.5 text-[12px] font-semibold ${on?`${t.cta} ${t.ctaT} border-transparent`:`${t.border} ${t.ts} hover:${t.tp}`} ${lang==="hi"?"deva":""}`}>
        <Bookmark key={on?"on":"off"} className={on?"pk-pop":""} size={14} fill={on?"currentColor":"none"}/>{on?(lang==="hi"?"सहेजा":"Saved"):(lang==="hi"?"सहेजें":"Save")}</button>;
    }
    // Per-card "✂ CLIP" action (design mobile card). Uses the shared SaveCtx so no card needs
    // save props threaded. Renders nothing when accounts are off; a guest tap routes to sign in.
    function CardClip({ story, t, lang }) {
      const ctx=React.useContext(SaveCtx);
      if(!ctx || !ctx.on) return null;
      const on=ctx.saved.has(String(story.id));
      const act=(e)=>{ e.stopPropagation(); e.preventDefault(); ctx.toggle(story); };
      return (
        <span role="button" tabIndex={0} aria-pressed={on?"true":"false"} onClick={act} onKeyDown={(e)=>{ if(e.key==="Enter"||e.key===" ") act(e); }}
          className={`inline-flex cursor-pointer items-center gap-1 mono text-[10px] font-semibold uppercase tracking-[0.1em] ${on?t.blind:t.tf} hover:${t.tp} ${lang==="hi"?"deva":""}`}>
          <span key={on?"on":"off"} className={on?"pk-pop":""} style={{display:"inline-block"}}>✂</span>{on?(lang==="hi"?"कतरा":"Clipped"):(lang==="hi"?"कतरें":"Clip")}
        </span>
      );
    }

    // Sign-in gate reused by Lens + Saved (the news is never gated; only these personal views are).
    function SignInGate({ t, lang, go, title, body }) {
      return (
        <PageWrap>
          <div className="mx-auto max-w-[520px] py-10 text-center">
            <h1 className={`headline text-[28px] sm:text-[34px] ${t.tp} ${readCls(lang)}`} style={{letterSpacing:lang==="hi"?0:"-0.018em"}}>{title}</h1>
            <p className={`mx-auto mt-3 max-w-[44ch] text-[15px] ${t.ts} ${readCls(lang)}`} style={{lineHeight:lang==="hi"?1.75:1.6}}>{body}</p>
            {authOn() && <button onClick={()=>go("login")} className={`mt-6 rounded-full px-5 py-2.5 text-[14px] font-semibold ${t.cta} ${t.ctaT} ${isHi(lang)}`}>{lang==="hi"?"साइन इन":"Sign in"}</button>}
          </div>
        </PageWrap>
      );
    }

    // MY READING LENS - the personal balance bar: distinct-publisher-lean of the stories YOU
    // opened, counted the SAME way a story's bar is (one publisher, one vote). Private to you.
    function LensPage({ t, lang, auth, go, open }) {
      const [rows,setRows]=useState(null);
      useEffect(()=>{ if(!auth) return; listReading(30).then(r=>setRows(r||[])).catch(()=>setRows([])); },[auth]);
      const L = lang==="hi" ? {
        title:"मेरा रीडिंग लेंस", sub:"पिछले 30 दिनों में आपने जो खबरें खोलीं, उनके प्रकाशक-झुकाव के हिसाब से, वही गिनती जो किसी खबर के बार में है। सिर्फ़ आपके लिए।",
        loading:"आपका लेंस तैयार हो रहा है…", empty:"अभी पर्याप्त पढ़ाई नहीं। कुछ खबरें खोलें, आपका संतुलन यहाँ बनेगा।",
        read:"पढ़ी · 30 दिन", least:"सबसे कम पढ़ा पक्ष", topics:"विषय",
        verdictEven:"आप जो खोलते हैं उसमें आपका पढ़ना काफ़ी संतुलित है।",
        nudgeH:"मैं क्या चूक रहा/रही हूँ", nudgeB:"आप सबसे कम जिस पक्ष को पढ़ते हैं, उस ओर की कवरेज गैप देखें।", nudgeBtn:"जो छूट रहा है देखें →",
        recent:"हाल में पढ़ी", none:"—",
        privacy:"जिस तरह किसी खबर का बार गिना जाता है उसी तरह: एक प्रकाशक, एक वोट। यह सिर्फ़ आपको दिखता है, और यह कभी नहीं बदलता कि आपको कौन-सी खबरें दिखाई जाती हैं। इतिहास बंद करना हो तो सेटिंग्स में।",
        gateB:"अपना रीडिंग लेंस देखने के लिए साइन इन करें। खबरें हमेशा बिना खाते के खुली रहती हैं।"
      } : {
        title:"My Reading Lens", sub:"The stories you opened in the last 30 days, by each source's publisher lean, counted the same way a story's bar is. Visible to no one but you.",
        loading:"Building your lens…", empty:"Not enough reading yet. Open a few stories and your balance will build here.",
        read:"Read · 30d", least:"Least-read side", topics:"Topics",
        verdictEven:"Your reading is fairly balanced across what you open.",
        nudgeH:"See what I'm missing", nudgeB:"Look at coverage gaps on the side you read least.", nudgeBtn:"See what I'm missing →",
        recent:"Recently read", none:"—",
        privacy:"Counted the same way a story's bar is: one publisher, one vote. Visible to no one but you, and it never changes what stories you're shown. Turn history off in Settings.",
        gateB:"Sign in to see your Reading Lens. The news itself is always open, no account needed."
      };
      if(!auth) return <SignInGate t={t} lang={lang} go={go} title={L.title} body={L.gateB} />;
      const list=rows||[];
      const agg={left:0,center:0,right:0}; list.forEach(r=>{ if(agg[r.side]!=null) agg[r.side]++; });
      const total=list.length;
      const bpct=biasPct(agg);
      const least=["left","center","right"].reduce((a,b)=>agg[b]<agg[a]?b:a,"left");
      const topics=new Set(list.map(r=>r.topic).filter(Boolean)).size;
      const hi=agg.left>=agg.right?"left":"right", lo=agg.left>=agg.right?"right":"left";
      const ratio=agg[lo]>0?(agg[hi]/agg[lo]):0;
      const verdict = total<3 ? "" : (agg.left===agg.right ? L.verdictEven
        : (lang==="hi"
          ? `आप ${lbl(hi,lang)} की ओर झुकते हैं, ${lbl(lo,lang)}-कवर खबरों से ${ratio>=2?`लगभग ${Math.round(ratio)} गुना`:"कुछ"} ज़्यादा ${lbl(hi,lang)}-कवर खबरें खोलते हैं।`
          : `You lean ${lbl(hi,lang)} in what you open, ${ratio>=2?`about ${Math.round(ratio)}x`:"somewhat"} as many ${lbl(hi,lang)}-covered stories as ${lbl(lo,lang)}-covered ones.`));
      const statCell=(n,label,clay,i)=>(
        <div className={`text-center ${i>0?"border-l":""} ${t.border}`} style={{padding:"14px 8px"}}>
          <div className={`text-[24px] font-semibold ${clay?t.blind:t.tp}`} style={{fontFamily:"'Source Serif 4',Georgia,serif",lineHeight:1}}>{n}</div>
          <div className={`mt-1.5 mono text-[8.5px] uppercase ${t.tf} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".06em",lineHeight:1.2}}>{label}</div>
        </div>
      );
      const balSub = lang==="hi"?"कोई फ़ैसला नहीं, आपने जो खबरें खोलीं उनके प्रकाशक-झुकाव की गिनती।":"Not a judgement, the arithmetic of the stories you opened, by each source's publisher lean.";
      return (
        <PageWrap>
          <div className="mx-auto max-w-[1180px]">
            {/* header: eyebrow + title + N stories · 30 days */}
            <div className="flex flex-wrap items-end justify-between gap-3 pb-3" style={{borderBottom:`2px solid ${t.ink}`}}>
              <div>
                <div className={`eyebrow ${t.tf} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".16em"}}>{lang==="hi"?"मेरा रीडिंग लेंस":"My reading lens"}</div>
                <h1 className={`headline mt-2 text-[30px] sm:text-[38px] ${t.tp} ${readCls(lang)}`} style={{letterSpacing:lang==="hi"?0:"-0.018em"}}>{lang==="hi"?"मेरा न्यूज़ झुकाव":"My news bias"}</h1>
              </div>
              {total>0 && <span className={`shrink-0 text-[13px] ${t.tf} ${readCls(lang)}`}>{total} {lang==="hi"?"खबरें · 30 दिन":"stories · 30 days"}</span>}
            </div>
            {rows===null ? <div className={`py-10 text-center text-[13px] ${t.tf} ${isHi(lang)}`}>{L.loading}</div>
            : total===0 ? <div className={`mt-8 border border-dashed p-10 text-center text-[14px] ${t.border} ${t.tf} ${readCls(lang)}`}>{L.empty}</div>
            : (
              <div className="mt-6 grid lg:grid-cols-[1.6fr_1fr]">
                {/* main: balance bar + verdict + recently read */}
                <div className="min-w-0 lg:border-r lg:pr-8" style={{borderColor:t.line}}>
                  <div className={`text-[11px] font-semibold uppercase ${t.tp} ${isHi(lang)}`} style={{letterSpacing:lang==="hi"?0:".08em"}}>{lang==="hi"?"आप क्या पढ़ते हैं, उसका संतुलन":"The balance of what you read"}</div>
                  <div className={`mt-1.5 text-[13px] ${t.tf} ${readCls(lang)}`} style={{lineHeight:lang==="hi"?1.6:1.5}}>{balSub}</div>
                  <div className={`mt-4 mb-2 mono text-[11px] uppercase ${t.tf} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".08em"}}>{lbl("left",lang)} {agg.left} · {lbl("center",lang)} {agg.center} · {lbl("right",lang)} {agg.right}</div>
                  <BiasSegments bias={bpct} t={t} h={30} lang={lang} />
                  {verdict && <div className="mt-4 flex items-start gap-2.5 p-3" style={{background:BIAS.left.soft,borderLeft:`2px solid ${BIAS.left.color}`}}><span style={{color:BIAS.left.color,fontSize:13}} aria-hidden="true">◪</span><span className={`text-[13.5px] ${readCls(lang)}`} style={{color:"#3A4B54",lineHeight:lang==="hi"?1.6:1.5}}>{verdict}</span></div>}
                  <p className={`mt-3 text-[11px] ${t.tf} ${isHi(lang)}`} style={{lineHeight:1.5}}>{lang==="hi"?"गिनती वैसी ही जैसी खबर की पट्टी में, एक प्रकाशक एक वोट। सिर्फ़ आपको दिखती है।":"Counted the same way a story's bar is: one publisher, one vote. Visible to no one but you."}</p>
                  <div className={`mt-6 mb-3 text-[11px] font-semibold uppercase ${t.tp} ${isHi(lang)}`} style={{letterSpacing:lang==="hi"?0:".08em"}}>{L.recent}</div>
                  <div style={{border:`1px solid ${t.line}`}}>
                    {list.slice(0,8).map((r,i)=>(
                      <button key={i} onClick={()=>open(r.story_id)} className={`flex w-full items-center justify-between gap-3 px-3.5 py-3 text-left ${i<Math.min(8,list.length)-1?"border-b":""} ${t.border}`}>
                        <span className={`min-w-0 flex-1 truncate headline text-[14.5px] ${t.tp} ${readCls(lang)}`}>{r.title||r.story_id}</span>
                        {r.side&&BIAS[r.side] && <span className="shrink-0 mono text-[9px] font-semibold uppercase" style={{backgroundColor:BIAS[r.side].soft,color:BIAS[r.side].color,padding:"3px 6px",letterSpacing:".04em"}}>{lbl(r.side,lang)}</span>}
                      </button>
                    ))}
                  </div>
                </div>
                {/* rail: stat row + blindspot nudge + privacy foot */}
                <div className="min-w-0 lg:pl-8 mt-6 lg:mt-0 space-y-5">
                  <div className="grid grid-cols-3" style={{border:`1px solid ${t.line}`}}>
                    {statCell(total,L.read,false,0)}
                    {statCell(agg[least],lang==="hi"?`कम पढ़ा: ${lbl(least,lang)}`:`Least: ${lbl(least,lang)}`,true,1)}
                    {statCell(topics,L.topics,false,2)}
                  </div>
                  <div style={{border:`1px solid #E0CBB9`}} className={`${t.blindSoft} p-4`}>
                    <div className={`eyebrow ${t.blind} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".08em"}}>{L.nudgeH}</div>
                    <div className={`mt-1.5 text-[13.5px] ${t.blind} ${readCls(lang)}`} style={{lineHeight:lang==="hi"?1.6:1.5}}>{L.nudgeB}</div>
                    <button onClick={()=>go("blindspot")} className={`mt-3 text-[10px] font-semibold uppercase ${t.blind} ${lang==="hi"?"deva":""}`} style={{border:"1px solid currentColor",padding:"8px 12px",letterSpacing:lang==="hi"?0:".05em"}}>{L.nudgeBtn}</button>
                  </div>
                  <p className={`pt-3 text-[11.5px] ${t.tf} ${isHi(lang)}`} style={{borderTop:`1px dashed ${t.line}`,lineHeight:1.55}}>{L.privacy}</p>
                </div>
              </div>
            )}
          </div>
        </PageWrap>
      );
    }

    // SAVED / clippings - newspaper-cutting treatment (dashed frame + a "clipped" tab).
    function SavedPage({ t, lang, auth, go, open, savedRows, onUnsave }) {
      const L = lang==="hi" ? { title:"सहेजी खबरें", empty:"अभी कुछ नहीं कतरा गया।", emptyB:"किसी खबर पर ‘सहेजें’ दबाएँ, वह यहाँ कतरन की तरह जुड़ जाएगी।",
        browse:"मुख्य खबरें देखें →", clipped:"कतरा", remove:"हटाएँ", gateB:"अपनी सहेजी खबरें देखने के लिए साइन इन करें।" }
        : { title:"Saved", empty:"Nothing clipped yet.", emptyB:"Press ‘Save’ on any story and it gets pinned here like a cutting.",
        browse:"Browse top stories →", clipped:"Clipped", remove:"Remove", gateB:"Sign in to see your saved stories." };
      if(!auth) return <SignInGate t={t} lang={lang} go={go} title={L.title} body={L.gateB} />;
      const rows=savedRows||[];
      return (
        <PageWrap>
          <h1 className={`headline text-[30px] sm:text-[40px] ${t.tp} ${readCls(lang)}`} style={{letterSpacing:lang==="hi"?0:"-0.018em"}}>{L.title}</h1>
          {savedRows===null ? <div className={`mt-8 py-10 text-center text-[13px] ${t.tf}`}>…</div>
          : rows.length===0 ? (
            <div className={`mt-8 border border-dashed p-12 text-center ${t.border}`}>
              <div className="text-[40px]" aria-hidden="true">✂</div>
              <div className={`mt-3 text-[16px] font-semibold ${t.tp} ${isHi(lang)}`}>{L.empty}</div>
              <p className={`mx-auto mt-1.5 max-w-[40ch] text-[13.5px] ${t.tf} ${readCls(lang)}`}>{L.emptyB}</p>
              <button onClick={()=>go("home")} className={`mt-5 border px-4 py-2 eyebrow ${t.border} ${t.ts} hover:${t.tp} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".08em"}}>{L.browse}</button>
            </div>
          ) : (
            <div className="mt-8 grid gap-6 sm:grid-cols-2">
              {rows.map((r)=>(
                <div key={r.story_id} className="relative" style={{border:`1px dashed #C4BEAE`,padding:"22px 18px 18px"}}>
                  <span className={`absolute mono text-[10px] uppercase tracking-wide ${t.cta} ${t.ctaT}`} style={{top:-9,left:14,padding:"2px 8px"}}>✂ {L.clipped} · {timeAgo(r.saved_at,lang)}</span>
                  <button onClick={()=>open(r.story_id)} className="block w-full text-left">
                    {r.topic && <div className={`eyebrow ${t.tf} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{lang==="hi"?(TOPIC_HI[r.topic]||r.topic):r.topic}</div>}
                    <h3 className={`headline mt-1.5 text-[18px] leading-[1.24] lc-3 ${t.tp} ${readCls(lang)} hover:underline decoration-1 underline-offset-2`}>{r.title||r.story_id}</h3>
                  </button>
                  <button onClick={()=>onUnsave(r.story_id)} className={`mt-3 mono text-[10.5px] uppercase tracking-wide ${t.tf} hover:${t.blind} ${lang==="hi"?"deva":""}`}>{L.remove}</button>
                </div>
              ))}
            </div>
          )}
        </PageWrap>
      );
    }

    // STORYLINE timeline — how a saga developed across days. Dated thread of the linked events,
    // the current one marked. Each entry is a real event with its own bias bar; the storyline is
    // purely a chronology of coverage, it never re-computes or merges any bias count.
    function StorylineTimeline({ storyline, currentId, t, lang, open, compact }) {
      if(!storyline || !(storyline.events||[]).length) return null;
      const evs=storyline.events;
      return (
        <ol className="relative mt-4" style={{marginLeft:6}}>
          <span style={{position:"absolute",left:0,top:4,bottom:4,width:2,background:t.line}}/>
          {evs.map((ev)=>{ const cur=String(ev.id)===String(currentId);
            const lc=ev.lean_counts||{}; const b=biasPct(lc);
            const title=(lang==="hi"&&ev.title_hi)?ev.title_hi:ev.title;
            return (
              <li key={ev.id} className="relative pb-5" style={{paddingLeft:22}}>
                <span style={{position:"absolute",left:-3,top:5,width:9,height:9,borderRadius:9,background:cur?t.ink:(t.gap||"#F4F1EA"),border:`2px solid ${t.ink}`}}/>
                <div className={`mono text-[10px] uppercase tracking-[0.1em] ${t.tf} ${lang==="hi"?"deva":""}`}>{absDate(ev.date,lang)||timeAgo(ev.date,lang)}</div>
                {cur
                  ? <div className={`headline mt-1 text-[15px] ${t.tp} ${readCls(lang)}`} style={{lineHeight:1.3}}>{title} <span className={`mono text-[9px] uppercase tracking-wide ${t.blind}`}>· {lang==="hi"?"यह खबर":"this story"}</span></div>
                  : <a href={"/story/"+encodeURIComponent(ev.id)} onClick={e=>{ if(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return; e.preventDefault(); open&&open(ev.id); }} className={`block no-underline group cursor-pointer mt-1 headline text-[15px] ${t.ts} ${readCls(lang)} group-hover:underline decoration-1 underline-offset-2`} style={{lineHeight:1.3}}>{title}</a>}
                {!compact && (lc.left+lc.center+lc.right)>0 && <div className="mt-2 w-40"><BiasSegments bias={b} t={t} h={8} lang={lang} /></div>}
              </li>
            );
          })}
        </ol>
      );
    }
    // STORYLINE page (/storyline/:id) — the whole saga: header + the full dated thread.
    // The index is lean (no events), so fetch the full per-saga file on open; `lean` gives an
    // instant header while it loads.
    function StorylinePage({ id, lean, t, lang, open, go }) {
      const [storyline,setStoryline]=useState(lean||null);
      useEffect(()=>{ let live=true; if(!id) return; apiGet("storylines/"+id).then(s=>{ if(live) setStoryline(s); }).catch(()=>{ if(live&&!lean) setStoryline(null); }); return ()=>{live=false;}; },[id]);
      const L = lang==="hi"
        ? { back:"वापस", eyebrow:"विकसित होती खबर", updates:"अपडेट", note:"यह एक ‘स्टोरीलाइन’ है, समय के साथ इसी घटनाक्रम पर आई अलग-अलग खबरों की कड़ी। हर कड़ी अपनी अलग बायस बार रखती है, स्टोरीलाइन सिर्फ़ क्रम दिखाती है, कोई गिनती दोबारा नहीं जोड़ती।", missing:"यह स्टोरीलाइन नहीं मिली।" }
        : { back:"Back", eyebrow:"Developing story", updates:"updates", note:"A storyline is a thread of separate stories about the same developing saga over time. Each entry keeps its own bias bar; the storyline only orders them, it never re-counts anything.", missing:"That storyline wasn't found." };
      if(!storyline) return (<PageWrap><div className={`py-16 text-center ${t.tf} ${isHi(lang)}`}>{L.missing}</div></PageWrap>);
      const title=(lang==="hi"&&storyline.title_hi)?storyline.title_hi:storyline.title;
      const tp=lang==="hi"?(TOPIC_HI[storyline.topic]||storyline.topic):storyline.topic;
      return (
        <PageWrap>
          <div className="mx-auto max-w-[840px]">
            <button onClick={()=>go("home")} className={`mb-5 inline-flex items-center gap-1.5 eyebrow ${t.ts} hover:${t.tp}`} style={{letterSpacing:lang==="hi"?0:".1em"}}><ArrowLeft size={14}/> {L.back}</button>
            <div className={`eyebrow ${t.blind} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".16em"}}>{L.eyebrow}{tp?` · ${tp}`:""}</div>
            <h1 className={`headline mt-2 text-[26px] sm:text-[34px] ${t.tp} ${readCls(lang)}`} style={{letterSpacing:lang==="hi"?0:"-0.018em"}}>{title}</h1>
            <div className={`mt-2 mono text-[11px] ${t.tf} ${lang==="hi"?"deva":""}`}>{storyline.n_events} {L.updates} · {absDate(storyline.start,lang)} → {absDate(storyline.end,lang)}</div>
            <div className="mt-6"><StorylineTimeline storyline={storyline} t={t} lang={lang} open={open} /></div>
            <p className={`mt-6 text-[12px] leading-[1.6] ${t.tf} ${isHi(lang)}`}>{L.note}</p>
          </div>
        </PageWrap>
      );
    }
    // "Developing" chip — marks a story that belongs to a saga thread (Eyebrow + story header).
    function DevelopingChip({ t, lang }) {
      return <span className={`inline-flex items-center gap-1 mono text-[9px] font-bold uppercase tracking-[0.12em] ${t.ts}`} style={{padding:"2px 6px",border:`1px solid ${t.line}`}}><span aria-hidden="true">◇</span>{lang==="hi"?"विकसित होती":"Developing"}</span>;
    }

    /* ---------------- routing + app ---------------- */
    function parsePath(){
      const p=(typeof window!=="undefined"?(window.location.pathname||"/"):"/");
      const seg=p.split("/").filter(Boolean);
      if(seg[0]==="story"&&seg[1]) return {view:"story", id:decodeURIComponent(seg[1])};
      if(seg[0]==="topic"&&seg[1]) return {view:"topic", topic:decodeURIComponent(seg[1])};
      if(seg[0]==="storyline"&&seg[1]) return {view:"storyline", id:decodeURIComponent(seg[1])};
      if(seg.length===0) return {view:"home"};
      if(seg.length===1 && ["blindspot","topics","sources","about","search","contact","privacy","support","login","settings","account","saved","lens"].includes(seg[0])) return {view:seg[0]};
      return {view:"404"};
    }
    // First-run onboarding: a reading-language ask + four one-line explainers of how to read
    // Paksh (the bias bar, coverage gaps, publisher-not-article, bilingual). Shown once, then
    // remembered in localStorage ("paksh-onboarded"). Dismissable at any step.
    function Onboarding({ t, lang, setLang, onDone }) {
      const [step,setStep]=useState(0);
      const steps = lang==="hi" ? [
        {k:"बायस बार", b:"रंगीन बार गिनता है कि कवर करने वाले कितने अलग-अलग आउटलेट वाम, केंद्र या दक्षिण की ओर हैं, एक प्रकाशक = एक वोट।"},
        {k:"कवरेज गैप", b:"जब एक पक्ष के आउटलेट कोई खबर चलाएँ पर दूसरे न चलाएँ, पक्ष उसे चिह्नित करता है, यह अंकगणित है, निर्णय नहीं।"},
        {k:"झुकाव प्रकाशन का, लेख का नहीं", b:"झुकाव का लेबल हर प्रकाशन का होता है और संपादक तय करते हैं, कोई एल्गोरिद्म नहीं।"},
        {k:"द्विभाषी", b:"हर खबर अंग्रेज़ी और हिंदी में, ऊपर के टॉगल से भाषा कभी भी बदलें।"},
      ] : [
        {k:"The bias bar", b:"The coloured bar counts how many distinct outlets covering a story lean Left, Centre or Right, one publisher = one vote."},
        {k:"Coverage gaps", b:"When one side's outlets run a story and the other's don't, Paksh flags it, arithmetic, not a judgment."},
        {k:"Lean is the publisher's, not the article's", b:"A lean label belongs to each publication and is set by editors, never by an algorithm."},
        {k:"Bilingual", b:"Every story in English and Hindi, switch language any time with the toggle up top."},
      ];
      const L = lang==="hi"
        ? { welcome:"पक्ष में आपका स्वागत है", pick:"पढ़ने की भाषा चुनें", next:"आगे", start:"शुरू करें", skip:"छोड़ें" }
        : { welcome:"Welcome to Paksh", pick:"Choose your reading language", next:"Next", start:"Get started", skip:"Skip" };
      const done=()=>onDone();
      return (
        <div className="fixed inset-0 z-[60] flex items-end justify-center p-0 sm:items-center sm:p-4" style={{background:"rgba(21,20,15,0.55)"}}>
          <div className={`pk-sheet w-full max-w-[460px] border-t sm:border ${t.surface} ${t.border}`} style={{boxShadow:"0 -8px 40px rgba(0,0,0,0.30)"}}>
            <div className="flex items-center justify-between px-5 pt-4">
              <span className="mono text-[10px] uppercase tracking-[0.16em]" style={{color:"#75442E"}}>{step===0?(lang==="hi"?"आपका स्वागत है":"Welcome"):`${lang==="hi"?"चरण":"Step"} ${step} ${lang==="hi"?"/":"of"} 4`}</span>
              <button onClick={done} className={`mono text-[11px] uppercase tracking-wide ${t.tf} hover:${t.tp} ${lang==="hi"?"deva":""}`}>{L.skip}</button>
            </div>
            {step===0 ? (
              <div className="px-5 pb-5 pt-4 text-center">
                <div className={`brand-hi text-[46px] leading-none ${t.tp}`}>पक्ष</div>
                <div className={`mt-2 eyebrow ${t.tf} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".18em"}}>{lang==="hi"?"भारत की खबरों का हर पक्ष":"Every side of India's news"}</div>
                <div className={`mt-5 eyebrow ${t.tf} ${lang==="hi"?"deva":""}`} style={{letterSpacing:lang==="hi"?0:".14em"}}>{L.pick}</div>
                <div className="mt-3 grid grid-cols-2 gap-3">
                  {[["en","English"],["hi","हिंदी"]].map(([k,label])=>(
                    <button key={k} onClick={()=>{ setLang(k); }} className={`border px-4 py-3 text-[15px] font-semibold ${lang===k?`${t.cta} ${t.ctaT} border-transparent`:`${t.border} ${t.ts} hover:${t.tp}`} ${k==="hi"?"deva":""}`}>{label}</button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="px-5 pb-5 pt-3">
                <h2 className={`headline mt-1 text-[21px] ${t.tp} ${readCls(lang)}`}>{steps[step-1].k}</h2>
                <p className={`mt-2 text-[14.5px] ${t.ts} ${readCls(lang)}`} style={{lineHeight:lang==="hi"?1.75:1.6}}>{steps[step-1].b}</p>
              </div>
            )}
            <div className={`flex items-center justify-between border-t px-5 py-3 ${t.border}`}>
              <div className="flex gap-1.5">{[0,1,2,3,4].map(i=><span key={i} style={{width:6,height:6,borderRadius:0,background:i===step?t.ink:t.line}}/>)}</div>
              <button onClick={()=> step<4?setStep(step+1):done()} className={`rounded-full px-5 py-2 text-[13px] font-semibold ${t.cta} ${t.ctaT} ${isHi(lang)}`}>{step<4?L.next:L.start}</button>
            </div>
          </div>
        </div>
      );
    }

    // Consent gate. Nothing is tracked until the visitor accepts here; "Decline" is honoured
    // for the whole session and remembered. Copy is deliberately plain about what's collected.
    function ConsentBanner({ t, lang, onChoose, go }) {
      const L = lang==="hi" ? {
        text:"पक्ष यह समझने के लिए कि लोग खबरें कैसे पढ़ते हैं, गोपनीयता-सम्मानित, कुकी-रहित एनालिटिक्स इस्तेमाल करना चाहता है। कोई व्यक्तिगत पहचान नहीं, कोई विज्ञापन-ट्रैकिंग नहीं।",
        accept:"स्वीकार करें", decline:"मना करें", more:"गोपनीयता"
      } : {
        text:"Paksh uses privacy-respecting, cookieless analytics to understand how people read the news. No personal identity, no ad-tracking.",
        accept:"Accept", decline:"Decline", more:"Privacy"
      };
      return (
        <div className="fixed inset-x-0 bottom-16 z-50 px-4 md:bottom-4">
          <div className={`mx-auto flex max-w-2xl flex-col gap-3 border p-4 sm:flex-row sm:items-center sm:gap-4 ${t.surface} ${t.border}`} style={{boxShadow:"0 6px 24px rgba(0,0,0,0.18)"}}>
            <p className={`text-[12.5px] leading-[1.55] ${t.ts} ${isHi(lang)}`}>{L.text} <button onClick={()=>go("privacy")} className={`underline underline-offset-2 ${t.tf} hover:${t.tp}`}>{L.more}</button></p>
            <div className="flex shrink-0 gap-2">
              <button onClick={()=>onChoose("denied")} className={`border px-3.5 py-1.5 text-[12.5px] font-semibold ${t.border} ${t.ts} hover:${t.tp} ${isHi(lang)}`}>{L.decline}</button>
              <button onClick={()=>onChoose("granted")} className={`px-3.5 py-1.5 text-[12.5px] font-semibold ${t.cta} ${t.ctaT} ${isHi(lang)}`}>{L.accept}</button>
            </div>
          </div>
        </div>
      );
    }

    function PakshApp() {
      const [route,setRoute]=useState(parsePath());
      // Default reading language: a remembered choice (set in Settings), else English.
      const [lang,setLang]=useState(()=>{ try{ const s=localStorage.getItem("paksh-lang"); return (s==="hi"||s==="en")?s:"en"; }catch(e){ return "en"; } });
      // Account session (Supabase, direct REST) + accessibility prefs. Accessibility is applied
      // to <html> for guests too (news is never gated); it's mirrored to the profile when signed in.
      const [auth,setAuth]=useState(null);
      const [a11y,setA11yState]=useState(readA11y);
      const [savedIds,setSavedIds]=useState(()=>new Set());   // story_ids the user has clipped
      const [savedRows,setSavedRows]=useState(null);          // full saved list for the Saved page
      const [lensStats,setLensStats]=useState({topics:[],sides:{left:0,center:0,right:0},total:0}); // reading summary → feed/gaps personalization
      const [onboard,setOnboard]=useState(()=>{ try{ return !localStorage.getItem("paksh-onboarded"); }catch(e){ return false; } });
      // Honour a remembered choice first, else the OS preference (prefers-color-scheme),
      // else light. Previously it always started light, ignoring a device set to dark.
      const [dark,setDark]=useState(()=>{ try{ const s=localStorage.getItem("paksh-theme"); if(s==="dark")return true; if(s==="light")return false; return !!(window.matchMedia&&window.matchMedia("(prefers-color-scheme: dark)").matches); }catch(e){ return false; } });
      const [query,setQuery]=useState("");
      const [data,setData]=useState({events:[],blindspots:[],gaps:{left:[],right:[],agg:{}},topics:[],sources:[],summary:{},storylines:[]});
      const [detail,setDetail]=useState({});
      const [archive,setArchive]=useState(null);   // older events, lazy-loaded for search/topic browsing
      const [ready,setReady]=useState(false);
      const [consent,setConsent]=useState(consentState);   // "" undecided | "granted" | "denied"

      useEffect(()=>{ loadAll().then(d=>{ setData(d); setReady(true); }); },[]);
      // Load cookieless Vercel Web Analytics ONLY after the visitor accepts. Denied/undecided
      // visitors get zero analytics script and zero beacons.
      useEffect(()=>{ if(consent==="granted") loadVercelAnalytics(); },[consent]);
      useEffect(()=>{ const on=()=>setRoute(parsePath()); window.addEventListener("popstate",on); return ()=>window.removeEventListener("popstate",on); },[]);
      useEffect(()=>{ document.documentElement.classList.toggle("dark",dark); document.body.style.backgroundColor=dark?"#1A1917":"#EAE6DB"; try{ localStorage.setItem("paksh-theme",dark?"dark":"light"); }catch(e){} },[dark]);
      useEffect(()=>{ window.scrollTo(0,0); if(route.view==="story"&&route.id&&!detail[route.id]){ apiGet("events/"+route.id).then(full=>setDetail(d=>({...d,[route.id]:full}))).catch(()=>{ const f=(data.events||[]).concat(data.blindspots||[]).find(x=>String(x.id)===String(route.id)); if(f) setDetail(d=>({...d,[route.id]:f})); }); } },[route,data]);
      // events.json is capped to recent stories for a light first paint; the older tail lives in
      // events-archive.json and is fetched ONCE, the first time the user browses beyond the feed
      // (Search / a Topic / Sections). Home + story pages never need it. Set to [] up front so the
      // fetch fires only once even if it fails (then search/topic just cover recent stories).
      useEffect(()=>{ if(archive!==null) return; if(!["search","topic","topics"].includes(route.view)) return; setArchive([]); apiGet("events-archive").then(a=>setArchive(a.events||[])).catch(()=>{}); },[route.view,archive]);

      // Apply accessibility to <html> immediately and whenever it changes (so every page reflects it).
      useEffect(()=>{ applyA11y(a11y); },[a11y]);
      // Restore a signed-in session on load (refreshes the token if needed); then pull the
      // account's saved prefs (accessibility + default language) and merge them in.
      useEffect(()=>{ if(!authOn()) return;
        // First honour a magic-link / email-confirm redirect (tokens in the URL), then fall back
        // to a stored session. Either way, hydrate prefs + saved + lens for cross-device continuity.
        authSessionFromUrl().then(()=>authEnsure()).then(s=>{ if(!s){ setAuth(null); return; } setAuth(s);
          loadPrefs().then(p=>{ if(!p) return;
            if(p.a11y) setA11yState(prev=>{ const merged=Object.assign({}, prev, p.a11y); writeA11y(merged); return merged; });
            if(p.lang==="en"||p.lang==="hi") setLang(p.lang);
          });
          refreshSaved(); refreshLens(); }).catch(()=>setAuth(null)); },[]);
      // Pull the saved list (ids for button state + rows for the Saved page).
      const refreshSaved=()=>{ listSaved().then(rows=>{ rows=rows||[]; setSavedRows(rows); setSavedIds(new Set(rows.map(r=>String(r.story_id)))); }).catch(()=>{ setSavedRows([]); }); };
      // Summarise the reader's last-30-day history (top topics + lean split) for the transparent
      // personalization rails on the feed and Coverage Gaps. Never changes ranking or the bias bar.
      const refreshLens=()=>{ if(!authOn()||!_uid()){ setLensStats({topics:[],sides:{left:0,center:0,right:0},total:0}); return; }
        listReading(30).then(rows=>{ rows=rows||[]; const sides={left:0,center:0,right:0}; const tc={};
          rows.forEach(r=>{ if(sides[r.side]!=null)sides[r.side]++; if(r.topic)tc[r.topic]=(tc[r.topic]||0)+1; });
          setLensStats({ topics:Object.keys(tc).sort((a,b)=>tc[b]-tc[a]), sides, total:rows.length }); }).catch(()=>{}); };
      // Record every opened story into the Reading Lens (signed-in only; best-effort).
      useEffect(()=>{ if(route.view==="story"&&route.id&&auth&&detail[route.id]){ recordRead(toCard(detail[route.id],lang)); } },[route.view,route.id,auth,detail]);

      const t=dark?TOKENS.dark:TOKENS.light;
      const nav=(path)=>{ if(window.location.pathname!==path){ window.history.pushState(null,"",path); } setRoute(parsePath()); };
      const go=(v)=> nav(v==="home"?"/":"/"+v);
      const open=(id)=>{ track("story_open",{device:deviceClass()}); nav("/story/"+encodeURIComponent(id)); };
      const goTopic=(tp)=> nav("/topic/"+encodeURIComponent(tp));
      const goStoryline=(id)=> nav("/storyline/"+encodeURIComponent(id));
      const chooseLang=(l)=>{ track("lang_switch",{to:l}); setLang(l); try{ localStorage.setItem("paksh-lang",l); }catch(e){} if(auth) savePrefsRemote({ lang:l }); };
      // Accessibility setter: update state, persist locally (applies for everyone), sync to the account.
      const setA11y=(p)=>{ setA11yState(p); writeA11y(p); if(auth) savePrefsRemote({ a11y:p }); };
      const onAuthed=(s)=>{ setAuth(s); track("sign_in",{}); loadPrefs().then(p=>{ if(p&&p.a11y){ const merged=Object.assign({},a11y,p.a11y); setA11yState(merged); writeA11y(merged); } if(p&&(p.lang==="en"||p.lang==="hi")) setLang(p.lang); }); refreshSaved(); refreshLens(); go("home"); };
      const onSignOut=()=>{ authSignOut().finally(()=>{ setAuth(null); setSavedIds(new Set()); setSavedRows(null); setLensStats({topics:[],sides:{left:0,center:0,right:0},total:0}); go("home"); }); };
      const setConsentChoice=(v)=>{ try{ localStorage.setItem("paksh-consent",v); }catch(e){} setConsent(v); };
      const finishOnboarding=()=>{ try{ localStorage.setItem("paksh-onboarded","1"); }catch(e){} setOnboard(false); };
      // Clip / unclip a story. A guest is sent to sign in (Saved is a personal feature; news is not).
      const toggleSave=(story)=>{ if(!auth){ go("login"); return; } const id=String(story.id); const on=savedIds.has(id);
        const next=new Set(savedIds); if(on){ next.delete(id); } else { next.add(id); } setSavedIds(next);
        if(on){ unsaveStory(id).then(refreshSaved).catch(refreshSaved); }
        else { saveStory(story).then(refreshSaved).catch(refreshSaved); } };

      // Combine recent (always loaded) with the lazy archive once it arrives, so Search / Topic /
      // Sections cover the FULL catalogue while the home feed's first paint stayed small. The two
      // lists are disjoint (recent = events[:N], archive = events[N:]), so there are no duplicates.
      const allEvents=(archive&&archive.length)?data.events.concat(archive):data.events;
      const baseCards=allEvents.map(e=>toCard(e,lang)).filter(c=>c.srclang===lang);
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
      // FRONT-PAGE ordering: recency-gated feed_rank (8h half-life, computed in
      // export_static._feed_rank) so the feed leads with what's current. Falls back to
      // importance if an older export hasn't written feed_rank yet. Sections/search/topic
      // stay newest-first (below); the importance score used elsewhere is unchanged.
      const rank=c=>(typeof c.feed_rank==="number"?c.feed_rank:0);
      const homeFilter=c=>{ if (HOME_EXCLUDE_TOPICS.includes(c.topic)) return false; const isWorld=(c.region||"India")==="World"; return regionFilter==="International"?isWorld:!isWorld; };
      const homeCards=baseCards.filter(homeFilter).sort((a,b)=>(rank(b)-rank(a))||(ageHours(a)-ageHours(b)));
      const homeOne=baseOne.filter(homeFilter).sort((a,b)=>(rank(b)-rank(a))||(ageHours(a)-ageHours(b)));
      // sections / search / topic pages: newest-first so new articles always show there too
      baseCards.sort((a,b)=>ageHours(a)-ageHours(b)); baseOne.sort((a,b)=>ageHours(a)-ageHours(b));
      const countsByTopic={}; baseCards.forEach(c=>{ const k=c.topic||"Society"; countsByTopic[k]=(countsByTopic[k]||0)+1; });
      const topicsOrdered=Object.keys(countsByTopic).sort((a,b)=>countsByTopic[b]-countsByTopic[a]);
      const lastTs=(data.events||[]).reduce((mx,e)=>{ const ts=Date.parse(e.published_at||e.created_at||""); return isNaN(ts)?mx:Math.max(mx,ts); },0);
      const stats={ stories:homeCards.length, outlets:(data.sources||[]).length,
        gaps:(gapAgg.total!=null?gapAgg.total:(gapL.length+gapR.length)),
        updated:(lastTs?new Date(lastTs).toISOString():""),
        regionFilter, setRegionFilter };
      // Roster size per lean (distinct outlets tracked), for the Coverage-Gaps rate columns.
      const rosterByLean={left:0,center:0,right:0};
      (data.sources||[]).forEach(s=>{ if(rosterByLean[s.lean]!=null) rosterByLean[s.lean]++; });
      // Token-AND search: every word in the query must appear SOMEWHERE in the card's
      // headline, summary snippet or topic. The old code required the whole query as one
      // contiguous substring of the headline, so "supreme court neet" matched nothing even
      // when all three words were present. Matches the localised (EN/HI) fields on the card.
      const qTokens=query.trim().toLowerCase().split(/\s+/).filter(Boolean);
      const _hay=(c)=>`${c.headline||""} ${c.lead||""} ${(c.summary||[]).join(" ")} ${c.topic||""}`.toLowerCase();
      const results=qTokens.length?baseCards.filter(c=>{ const h=_hay(c); return qTokens.every(tok=>h.includes(tok)); }):[];
      const story = route.view==="story" ? (detail[route.id]?toDetail(detail[route.id],lang):null) : null;
      // Same-topic stories to keep a reader moving instead of dead-ending at the article.
      const related = story ? baseCards.filter(c=>c.topic===story.topic && String(c.id)!==String(story.id)).slice(0,6) : [];
      const headerView = route.view==="story" ? "" : route.view;

      return (
        <SaveCtx.Provider value={{ saved:savedIds, toggle:toggleSave, on:authOn(), go }}>
        <div className={`min-h-screen font-sans ${t.bg} ${t.tp}`}>
          <a href="#main" className="sr-only-focusable">{lang==="hi"?"मुख्य सामग्री पर जाएँ":"Skip to content"}</a>
          {ready && homeCards.length>0 && <BreakingTicker cards={homeCards} t={t} lang={lang} open={open} />}
          <Header t={t} lang={lang} setLang={chooseLang} dark={dark} setDark={setDark} go={go} view={headerView} auth={auth} openHelp={()=>setOnboard(true)} savedCount={savedIds.size} />
          <main id="main" className="pb-24 md:pb-10">
            <div className="pk-page" key={route.view+(route.id||route.topic||"")}>
            {route.view==="login" ? <LoginPage t={t} lang={lang} go={go} onAuthed={onAuthed} />
            : route.view==="settings" ? <SettingsPage t={t} lang={lang} setLang={chooseLang} a11y={a11y} setA11y={setA11y} auth={auth} onSignOut={onSignOut} consent={consent} setConsent={setConsentChoice} go={go} />
            : route.view==="account" ? <AccountPage t={t} lang={lang} auth={auth} go={go} onSignOut={onSignOut} />
            : route.view==="storyline" ? <StorylinePage id={route.id} lean={(data.storylines||[]).find(s=>s.id===route.id)} t={t} lang={lang} open={open} go={go} />
            : route.view==="lens" ? <LensPage t={t} lang={lang} auth={auth} go={go} open={open} />
            : route.view==="saved" ? <SavedPage t={t} lang={lang} auth={auth} go={go} open={open} savedRows={savedRows} onUnsave={(id)=>toggleSave({id})} />
            : route.view==="404" ? <NotFoundPage t={t} lang={lang} go={go} />
            : !ready ? <FeedSkeleton t={t} />
            : route.view==="story" ? (story ? <StoryPage story={story} t={t} lang={lang} go={go} openTopic={goTopic} related={related} open={open} saved={savedIds} onToggleSave={toggleSave} a11y={a11y} auth={auth} goStoryline={goStoryline} /> : <FeedSkeleton t={t} />)
            : route.view==="blindspot" ? <BlindspotPage left={gapL} right={gapR} roster={rosterByLean} agg={gapAgg} stats={stats} t={t} lang={lang} open={open} go={go} auth={auth} lens={lensStats} />
            : route.view==="topics" ? <TopicsHub topics={topicsOrdered} counts={countsByTopic} t={t} lang={lang} goTopic={goTopic} />
            : route.view==="topic" ? <TopicPage topic={route.topic} items={baseCards.filter(c=>c.topic===route.topic)} t={t} lang={lang} open={open} go={go} />
            : route.view==="sources" ? <SourcesPage t={t} lang={lang} sources={data.sources} />
            : route.view==="about" ? <AboutPage t={t} lang={lang} agg={gapAgg} go={go} />
            : route.view==="contact" ? <ContactPage t={t} lang={lang} />
            : route.view==="privacy" ? <PrivacyPage t={t} lang={lang} consent={consent} setConsent={setConsentChoice} />
            : route.view==="support" ? <SupportPage t={t} lang={lang} go={go} />
            : route.view==="search" ? <SearchPage t={t} lang={lang} query={query} setQuery={setQuery} results={results} open={open} />
            : (!homeCards.length ? <PageWrap><div className={`py-28 text-center ${t.tf} ${isHi(lang)}`}>{STR[lang].noStories}</div></PageWrap>
               : <HomeView cards={homeCards} gapLeft={gapL} gapRight={gapR} topics={topicsOrdered} counts={countsByTopic} stats={stats} t={t} lang={lang} open={open} goTopic={goTopic} go={go} auth={auth} lens={lensStats} openHelp={()=>setOnboard(true)} storylines={data.storylines} goStoryline={goStoryline} />)}
            </div>
          </main>
          {route.view!=="story" && <Footer t={t} lang={lang} go={go} />}
          <BottomNav t={t} lang={lang} view={headerView} go={go} auth={auth} />
          {onboard && <Onboarding t={t} lang={lang} setLang={chooseLang} onDone={finishOnboarding} />}
          {!onboard && consent==="" && <ConsentBanner t={t} lang={lang} go={go}
            onChoose={(v)=>{ setConsentChoice(v); }} />}
        </div>
        </SaveCtx.Provider>
      );
    }
    ReactDOM.createRoot(document.getElementById("root")).render(<PakshApp />);