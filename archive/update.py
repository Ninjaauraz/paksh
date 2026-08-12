import os

os.chdir(r"c:\Users\ambuj\Downloads\paksh_project\paksh")
html = open('static/index.html', encoding='utf-8').read()

start_style = html.find('<style>')
end_style = html.find('</style>') + len('</style>')
html = html[:start_style] + '<link rel="stylesheet" href="/static/styles.css"/>' + html[end_style:]

start_script = html.find('<script type="text/babel">')
end_script = html.find('</script>', start_script) + len('</script>')
html = html[:start_script] + '<script type="text/babel" src="/static/app.jsx"></script>' + html[end_script:]

# Fix icon links to be absolute for story detail pages
html = html.replace('href="static/favicon.png"', 'href="/static/favicon.png"')
html = html.replace('href="static/apple-touch-icon.png"', 'href="/static/apple-touch-icon.png"')

open('static/index.html', 'w', encoding='utf-8').write(html)
