import os
import re

os.chdir(r"c:\Users\ambuj\Downloads\paksh_project\paksh")
app_jsx = open('static/app.jsx', encoding='utf-8').read()

# 1. Update Header props to accept query and setQuery
app_jsx = app_jsx.replace(
    "function Header({ t, lang, setLang, dark, setDark, go, view, topics, goTopic, regionFilter, setRegionFilter }) {",
    "function Header({ t, lang, setLang, dark, setDark, go, view, topics, goTopic, regionFilter, setRegionFilter, query, setQuery }) {"
)

# 2. Replace the search icon in Header with the continuous search bar
old_search_icon = """<div className="ml-auto flex items-center gap-2">
                <button onClick={()=>go("search")} aria-label="Search" className={`grid h-9 w-9 place-items-center rounded-full ${t.ts} hover:${t.soft}`}><Search size={18}/></button>
              </div>"""

new_search_bar = """<div className="ml-auto flex items-center max-w-xs w-full sm:max-w-sm">
                <div className="relative w-full">
                  <Search size={16} className={`absolute left-3 top-1/2 -translate-y-1/2 ${t.tf}`} />
                  <input value={query||""} onChange={(e)=>{ if (setQuery) { setQuery(e.target.value); if (view !== "search" && e.target.value.trim()) go("search"); } }} placeholder={STR[lang].search} className={`w-full rounded-full border py-1.5 pl-9 pr-3 text-[14px] outline-none transition-colors ${t.surface} ${t.border} focus:border-[#2D5BD0] ${t.tp} ${lang==="hi"?"deva":""}`} />
                </div>
              </div>"""

if old_search_icon in app_jsx:
    app_jsx = app_jsx.replace(old_search_icon, new_search_bar)
else:
    print("Warning: old_search_icon not found!")

# 3. Add query and setQuery to Header invocation in App
app_jsx = app_jsx.replace(
    "topics={topicsOrdered} goTopic={goTopic} regionFilter={regionFilter} setRegionFilter={setRegionFilter}",
    "topics={topicsOrdered} goTopic={goTopic} regionFilter={regionFilter} setRegionFilter={setRegionFilter} query={query} setQuery={setQuery}"
)

# 4. Remove the large search input from SearchPage since it is now in the Header
old_search_page_input = """          <div className="relative mb-6 max-w-xl">
            <Search size={18} className={`absolute left-4 top-1/2 -translate-y-1/2 ${t.tf}`} />
            <input autoFocus value={query} onChange={(e)=>setQuery(e.target.value)} placeholder={STR[lang].search} className={`w-full rounded-full border py-3 pl-11 pr-4 text-base outline-none focus:border-[#2D5BD0] ${t.surface} ${t.border} ${t.tp} ${isHi(lang)}`} />
          </div>"""

if old_search_page_input in app_jsx:
    app_jsx = app_jsx.replace(old_search_page_input, "")
else:
    print("Warning: old_search_page_input not found!")

open('static/app.jsx', 'w', encoding='utf-8').write(app_jsx)
print("Updated search bar.")
