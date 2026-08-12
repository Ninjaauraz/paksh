# Paksh backend — handoff setup guide

This zip is a self-contained copy of the Paksh backend for setting up on another PC.
It is a **full git repo** (history included) plus the live **database**. Read this whole
file before running anything. Architecture + invariants are in `CLAUDE.md`; where files
live is summarised in `README.md`; run-by-hand tools are in `MAINTENANCE.md`.

---

## 1. What's in this zip (and what's deliberately NOT)

**Included**
- All Python pipeline code in the root (`ingest.py`, `cluster.py`, `analyze.py`,
  `export_static.py`, `live.py`, `sources.py`, etc.)
- `static/` + `static/vendor/` — the self-hosted React/Tailwind frontend (no CDN)
- `_site/` — the already-built static site Vercel serves
- `paksh.db` — the live SQLite database (~48k articles, ~2385 events)
- Full `.git/` history — so you can review the code and its evolution
- `archive/` — obsolete one-off scripts (kept for history, not used)
- `.vscode/settings.json` — Explorer file-nesting so the file list looks tidy
- `ai_keys.example.env` — keyless template for your API keys
- `requirements.txt`

**Deliberately excluded (do NOT ask for these — provision your own):**
- `.env` and `ai_keys.env` — these hold Sameer's **live API keys** (Gemini, Groq,
  Cerebras, Cloudflare, etc.). Secrets are never shared in a handoff. You create your
  own — see step 3. Groq and Cerebras keys are **free**.
- `paksh.db.bak*` — old DB backups, not needed.
- `signals/` — internal Redstocks market-signal exports, not part of the public backend.
- `__pycache__/`, logs, local editor/tool config.

---

## 2. Prerequisites to install first

1. **Python** — the project calls it as `py` (Microsoft Store Python on Windows).
   Verify: `py --version`.
2. **Python packages:** `py -m pip install -r requirements.txt`
3. **Ollama** (required for embeddings/clustering AND local summaries):
   - Install from https://ollama.com ; `ollama serve` must be running (http://localhost:11434)
   - Pull the models: `ollama pull bge-m3` and `ollama pull llama3.2:3b`
   - **Never change the embedding model** — bge-m3 vectors must stay consistent with the DB.
4. **Git** — for reviewing history and (if you publish) pushing.

---

## 3. Provision your own keys / config (nothing here contains real keys)

1. Copy the template: `copy ai_keys.example.env ai_keys.env`
2. Paste your own **free** keys into `ai_keys.env`:
   - Groq: https://console.groq.com/keys
   - Cerebras: https://cloud.cerebras.ai
   - Gemini (optional): https://aistudio.google.com/apikey
3. Create a `.env` file (not included) with at least: `PAKSH_LLM_BACKEND=hybrid`
   (use `pool` to run the Groq/Cerebras/Gemini pool instead).
4. Verify keys load: `py ai_providers.py` then `py ai_providers.py --ping`

---

## 4. First run — just build the site (no Ollama, no keys needed)

The DB already has data, so you can render the site immediately:

```
py export_static.py
```

Then open `_site/index.html` (or serve `_site/`). Good first check the code works on your
machine. Verify against the checklist at the bottom of `CLAUDE.md`.

## 5. Full pipeline cycle (needs Ollama running + your keys)

```
set PAKSH_LLM_BACKEND=hybrid
py refresh.py
```

The always-on loop is `py live.py --deploy --every 180` — but read section 6 FIRST.

---

## 6. IMPORTANT — running this on 3 machines at once

The current code assumes **one machine, one database, one publisher**. It was not built
for 3 machines independently ingesting and pushing at the same time. If all three run
`live.py --deploy`, they will each build a **different** `_site/` from their **own** local
DB and fight over `git push` → the live site flip-flops and events can duplicate. The
pipeline lock (`.pipeline.lock`, `runlocked.py`) is **per-machine only**.

**Safe model to start with:** exactly **ONE** machine is the "publisher" that runs
`export_static.py` + `git push` (Vercel auto-deploys from the push). The other machines
use their copy for **code review and development**, not live publishing. Sharing the
ingest/analyze workload across machines while keeping one consistent published site needs
a shared database or a work-partitioning design — a real change to discuss with Sameer
before turning it on. Publishing also needs **write access to the GitHub repo**
(`github.com/Ninjaauraz/paksh`) — ask Sameer to add you as a collaborator. Never use the
Vercel CLI; deploys happen via the git push.

---

## 7. Fragile coupling to know before editing (from CLAUDE.md)

`export_static.py` builds each story page by splitting `static/index.html` on two exact
strings: `<div id="root">` and `<script src="/static/app.js"></script>`. If you change
`static/index.html`'s structure or rename `app.jsx`, you MUST update the split markers in
`_story_html()` in `export_static.py` in the same change, or every story page breaks.
Always re-run `py export_static.py` after touching either file. And never break the
invariants at the top of `CLAUDE.md` — above all, the bias bar counts **distinct outlets
by publisher lean** (one vote per publisher), and lean labels are editorial (`sources.py`),
never AI-generated.
