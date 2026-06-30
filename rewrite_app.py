import os
import re

os.chdir(r"c:\Users\ambuj\Downloads\paksh_project\paksh")
app_jsx = open('static/app.jsx', encoding='utf-8').read()

# 1. Add RegionSelect component
region_select = """
    function RegionSelect({ region, setRegion, t, lang }) {
      const states = ["Maharashtra", "Uttar Pradesh", "Karnataka", "Tamil Nadu", "Delhi", "Gujarat", "West Bengal"];
      return (
        <div className="relative shrink-0">
          <select value={region} onChange={e=>setRegion(e.target.value)} className={`appearance-none rounded-full border px-3 py-1 pl-3 pr-7 text-[12.5px] font-medium ${t.border} ${region==="National"||region==="International" ? 'bg-[#1B1A18] text-white dark:bg-white dark:text-black border-transparent' : t.ts} hover:${t.soft} bg-transparent outline-none cursor-pointer ${lang==="hi"?"deva":""} transition-all duration-200`}>
            <option value="National">{ui("National", lang)}</option>
            <option value="International">{ui("International", lang)}</option>
            <optgroup label={lang==="hi"?"राज्य (जल्द आ रहे हैं)":"States (Pending)"}>
              {states.map(s=><option key={s} value={s} disabled>{s}</option>)}
            </optgroup>
          </select>
          <div className={`pointer-events-none absolute inset-y-0 right-2 flex items-center ${region==="National"||region==="International" ? 'text-white dark:text-black' : t.tf}`}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6"/></svg>
          </div>
        </div>
      );
    }
"""
app_jsx = app_jsx.replace("/* ---------------- shell ---------------- */", "/* ---------------- shell ---------------- */" + region_select)

# 2. Update Header to take regionFilter and setRegionFilter
app_jsx = app_jsx.replace(
    "function Header({ t, lang, setLang, dark, setDark, go, view, topics, goTopic }) {",
    "function Header({ t, lang, setLang, dark, setDark, go, view, topics, goTopic, regionFilter, setRegionFilter }) {"
)

# 3. Insert RegionSelect before topics
app_jsx = app_jsx.replace(
    """<span className={`mono text-[10px] uppercase tracking-wide ${t.tf} shrink-0`}>{lang==="hi"?"विषय":"Topics"}</span>""",
    """<span className={`mono text-[10px] uppercase tracking-wide ${t.tf} shrink-0`}>{lang==="hi"?"विषय":"Topics"}</span>\n                {setRegionFilter && <RegionSelect region={regionFilter} setRegion={setRegionFilter} t={t} lang={lang} />}"""
)

# 4. Update Topic active state styles
app_jsx = app_jsx.replace(
    """<button key={tp} onClick={()=>goTopic(tp)} className={`shrink-0 rounded-full border px-3 py-1 text-[12.5px] font-medium ${t.border} ${t.ts} hover:${t.soft} ${lang==="hi"?"deva":""}`}>{lang==="hi"?(TOPIC_HI[tp]||tp):tp}</button>""",
    """<button key={tp} onClick={()=>goTopic(tp)} className={`shrink-0 rounded-full border px-3 py-1 text-[12.5px] font-medium transition-colors duration-200 ${view===tp ? 'bg-[#1B1A18] text-white dark:bg-[#E9EAEC] dark:text-[#1D1F24] border-transparent' : `${t.border} ${t.ts} hover:${t.soft}`} ${lang==="hi"?"deva":""}`}>{lang==="hi"?(TOPIC_HI[tp]||tp):tp}</button>"""
)

# 5. Update App component to have regionFilter
app_jsx = app_jsx.replace(
    "const HOME_EXCLUDE_TOPICS = [\"Sports\"];",
    "const HOME_EXCLUDE_TOPICS = [\"Sports\"];\n      const [regionFilter, setRegionFilter] = useState(\"National\");"
)
app_jsx = app_jsx.replace(
    "const homeFilter=c=>!HOME_EXCLUDE_TOPICS.includes(c.topic) && (c.region||\"India\")!==\"World\";",
    "const homeFilter=c=>{ if (HOME_EXCLUDE_TOPICS.includes(c.topic)) return false; const isWorld=(c.region||\"India\")===\"World\"; return regionFilter===\"International\"?isWorld:!isWorld; };"
)
app_jsx = app_jsx.replace(
    "topics={topicsOrdered} goTopic={goTopic}",
    "topics={topicsOrdered} goTopic={goTopic} regionFilter={regionFilter} setRegionFilter={setRegionFilter}"
)

# 6. Redesign Framing Blocks in StoryDetail
old_framing = """              {/* framing tabs */}
              <div className={`mt-7 rounded-lg border ${t.surface} ${t.border}`}>
                <div className={`flex flex-wrap items-center gap-1.5 border-b p-2 ${t.border}`}>
                  <Scale size={15} className={`mx-1 ${t.tf}`} />
                  {sideTabs.map(k=><SideTab key={k} k={k} />)}
                </div>
                <div className="p-5">
                  {side==="overview" ? (
                    <div>
                      <div className={`mb-3 flex items-center gap-2 mono text-[11px] uppercase tracking-wide ${t.tf}`}>{story.auto?STR[lang].autoTag:STR[lang].aiSummary}{story.auto && <span className={`${isHi(lang)} normal-case`}>· {STR[lang].autoFrom}</span>}</div>
                      {story.lead && <p className={`mb-4 text-[16px] font-medium leading-relaxed ${t.tp} ${isHi(lang)}`}>{story.lead}</p>}
                      <ul className="space-y-2.5">{(story.summary||[]).map((p,i)=><li key={i} className={`flex gap-2.5 text-[14.5px] leading-relaxed ${t.tp} ${isHi(lang)}`}><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full" style={{background:t.ink}}/>{p}</li>)}</ul>
                    </div>
                  ) : (
                    <div>
                      <div className="mb-3 flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full" style={{backgroundColor:BIAS[side].color}}/><span className="mono text-[11px] font-bold uppercase tracking-wide" style={{color:BIAS[side].color}}>{lbl(side,lang)} · {STR[lang].framingTitle}</span></div>
                      <p className={`text-[15px] leading-relaxed ${t.tp} ${isHi(lang)}`}>{fr[side]}</p>
                    </div>
                  )}
                </div>
              </div>"""

new_framing = """              {/* Overview / AI Summary */}
              <div className={`mt-7 rounded-lg border ${t.surface} ${t.border}`}>
                <div className="p-5">
                  <div className={`mb-3 flex items-center gap-2 mono text-[11px] uppercase tracking-wide ${t.tf}`}>{story.auto?STR[lang].autoTag:STR[lang].aiSummary}{story.auto && <span className={`${isHi(lang)} normal-case`}>· {STR[lang].autoFrom}</span>}</div>
                  {story.lead && <p className={`mb-4 text-[16px] font-medium leading-relaxed ${t.tp} ${isHi(lang)}`}>{story.lead}</p>}
                  <ul className="space-y-2.5">{(story.summary||[]).map((p,i)=><li key={i} className={`flex gap-2.5 text-[14.5px] leading-relaxed ${t.tp} ${isHi(lang)}`}><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full" style={{background:t.ink}}/>{p}</li>)}</ul>
                </div>
              </div>

              {/* framing grid */}
              <div className={`mt-7`}>
                <div className={`mb-4 flex items-center gap-2`}><Scale size={18} className={t.tf}/><h3 className={`headline text-[17px] font-bold ${t.tp} ${isHi(lang)}`}>{STR[lang].framingTitle}</h3></div>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                  {["left","center","right"].map(k=> (fr[k] || counts[k]>0) ? (
                    <div key={k} className={`rounded-lg border p-4 ${t.surface} ${t.border} flex flex-col hover:-translate-y-0.5 hover:shadow-md transition-all duration-300`}>
                      <div className="mb-3 flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full" style={{backgroundColor:BIAS[k].color}}/><span className="mono text-[11px] font-bold uppercase tracking-wide" style={{color:BIAS[k].color}}>{lbl(k,lang)}</span></div>
                      {fr[k] ? (
                        <p className={`text-[14.5px] leading-relaxed ${t.tp} ${isHi(lang)}`}>{fr[k]}</p>
                      ) : (
                        <p className={`text-[13px] italic ${t.tf} ${isHi(lang)}`}>{STR[lang].framingPending}</p>
                      )}
                    </div>
                  ) : null)}
                </div>
              </div>"""

if old_framing in app_jsx:
    app_jsx = app_jsx.replace(old_framing, new_framing)
else:
    print("Warning: old_framing not found!")

# Remove sideTab component and states
app_jsx = re.sub(r'const sideTabs=\["overview", \.\.\.\["left","center","right"\].filter\(k=>fr\[k\]\|\|counts\[k\]>0\)\];\s*const \[side,setSide\]=useState\("overview"\);\s*const SideTab = \(\{ k \}\) => \{[^}]+\};\s*', '', app_jsx)
app_jsx = re.sub(r'const SideTab = \(\{ k \}\) => \{\s*const act=side===k;[^\}]+\};\s*', '', app_jsx)


open('static/app.jsx', 'w', encoding='utf-8').write(app_jsx)
print("Updated static/app.jsx successfully.")
