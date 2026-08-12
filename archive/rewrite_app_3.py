import os

os.chdir(r"c:\Users\ambuj\Downloads\paksh_project\paksh")
app_jsx = open('static/app.jsx', encoding='utf-8').read()

# Fix the RegionSelect class
# The current is: `appearance-none rounded-full border px-3 py-1 pl-3 pr-7 text-[12.5px] font-medium ${t.border} ${region==="National"||region==="International" ? 'bg-[#1B1A18] text-white dark:bg-white dark:text-black border-transparent' : t.ts} hover:${t.soft} bg-transparent outline-none cursor-pointer ${lang==="hi"?"deva":""} transition-all duration-200`
# We want to change to use standard t.cta and t.ctaT tokens, and use !bg- to override default tailwind forms plugin (if any).

old_class = "`appearance-none rounded-full border px-3 py-1 pl-3 pr-7 text-[12.5px] font-medium ${t.border} ${region===\"National\"||region===\"International\" ? 'bg-[#1B1A18] text-white dark:bg-white dark:text-black border-transparent' : t.ts} hover:${t.soft} bg-transparent outline-none cursor-pointer ${lang===\"hi\"?\"deva\":\"\"} transition-all duration-200`"

new_class = "`appearance-none rounded-full border px-3 py-1 pl-3 pr-7 text-[12.5px] font-medium ${region===\"National\"||region===\"International\" ? `${t.cta} ${t.ctaT} border-transparent` : `${t.border} ${t.ts} hover:${t.soft} bg-transparent`} outline-none cursor-pointer ${lang===\"hi\"?\"deva\":\"\"} transition-all duration-200`"

if old_class in app_jsx:
    app_jsx = app_jsx.replace(old_class, new_class)
else:
    print("Warning: old_class not found!")

# Also fix the chevron icon color
old_chevron_class = "`pointer-events-none absolute inset-y-0 right-2 flex items-center ${region===\"National\"||region===\"International\" ? 'text-white dark:text-black' : t.tf}`"
new_chevron_class = "`pointer-events-none absolute inset-y-0 right-2 flex items-center ${region===\"National\"||region===\"International\" ? t.ctaT : t.tf}`"

if old_chevron_class in app_jsx:
    app_jsx = app_jsx.replace(old_chevron_class, new_chevron_class)
else:
    print("Warning: old_chevron_class not found!")

open('static/app.jsx', 'w', encoding='utf-8').write(app_jsx)
print("Updated RegionSelect.")
