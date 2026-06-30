import sys
import os

os.chdir(r"c:\Users\ambuj\Downloads\paksh_project\paksh")

html = open('static/index.html', encoding='utf-8').read()

start_style = html.find('<style>') + len('<style>')
end_style = html.find('</style>')
styles = html[start_style:end_style].strip()

start_script = html.find('<script type="text/babel">') + len('<script type="text/babel">')
end_script = html.find('</script>', start_script)
script = html[start_script:end_script].strip()

open('static/styles.css', 'w', encoding='utf-8').write(styles)
open('static/app.jsx', 'w', encoding='utf-8').write(script)

print('Extracted styles length:', len(styles))
print('Extracted script length:', len(script))
