# Deploying Paksh (free, auto-refreshing)

This puts Paksh on the internet for **free**, with **no server to manage** and
**no database to keep alive**. A scheduled GitHub Action runs the pipeline
(`ingest` → `analyze`), exports the site as static files, and publishes it to
**GitHub Pages**. Each run rebuilds a fresh snapshot of current coverage.

You need: a free **GitHub account**, and your **Gemini API key**.

---

## Before you deploy: sanity-check locally

CI can only build real stories if your feeds actually return articles. Do this
once on your machine first:

1. Fix/verify feeds (especially the Hindi + "candidate" ones in `feeds.py`):
   ```
   python ingest.py --discover https://www.bhaskar.com
   ```
   Paste any working feed URLs it finds into `feeds.py`.
2. Run the real pipeline once and confirm you get events:
   ```
   python ingest.py
   python analyze.py
   python export_static.py
   python -m http.server -d _site 8080
   ```
   Open http://localhost:8080 — if stories show here, CI will work too.

Also, two things from Part 8 to do before going public:
- Change `CONTACT` in `static/app.js` to a real email.
- Give the 18 provisional ratings in `sources.py` a real editorial review.

---

## Step 1 — Put the project on GitHub

Create a new **empty** repo on GitHub (e.g. `paksh`). Then, in the project
folder:

```
git init
git add .
git commit -m "Paksh"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/paksh.git
git push -u origin main
```

(Prefer clicking? **GitHub Desktop** does the same thing on Windows.)

> `paksh.db` and `_site/` don't need to be committed — they're rebuilt by CI.
> A `.gitignore` with those two lines is tidy but optional.

## Step 2 — Add your Gemini key as a secret

In the repo: **Settings → Secrets and variables → Actions → New repository
secret**.
- **Name:** `GEMINI_API_KEY`
- **Value:** your key

This is required — without it, the analysis step can't run and the site builds empty.

## Step 3 — Turn on GitHub Pages

**Settings → Pages → Build and deployment → Source: GitHub Actions.**
(That's it — don't pick a branch; the workflow handles publishing.)

## Step 4 — Run it

The workflow runs automatically on every push, but to trigger it now:
**Actions → "Build & publish Paksh" → Run workflow.**
Watch the steps run (install → ingest + analyze → export → deploy).

## Step 5 — Your live URL

When the run finishes, the **Deploy** step shows the URL, also visible under
**Settings → Pages**. It looks like:

```
https://YOUR_USERNAME.github.io/paksh/
```

Share that. Done.

---

## How it stays fresh

`.github/workflows/publish.yml` has:

```yaml
schedule:
  - cron: "0 */6 * * *"   # every 6 hours (UTC)
```

Change the cron to refresh more or less often. Note GitHub's scheduled runs use
**UTC** and can be delayed a few minutes at busy times — that's normal.

## What "fresh snapshot" means (and adding history later)

Each scheduled run starts with an empty database, pulls **current** RSS,
clusters, analyses, and publishes. Stories naturally roll over as the feeds
move — there's no long-term archive. That's a deliberate, zero-maintenance
choice for v1. When you want history, you have options:
- **Cache the DB** between runs with `actions/cache` (keyed on the day), or
  commit `paksh.db` back to the repo at the end of each run; or
- Move from SQLite to a free hosted **Postgres** (Neon or Supabase both have
  durable free tiers) and have both the pipeline and a server read it.

## Cost

Free across the board: GitHub Actions minutes are free for **public** repos,
GitHub Pages hosting is free, and the pipeline stays within Gemini's free tier
(≤ 8 events/run, embeddings for a bounded set of articles).

---

## Prefer a real (dynamic) server instead?

You can still run the live FastAPI app (e.g. on Render): set `GEMINI_API_KEY`
as an environment variable, start it with `uvicorn main:app`, and use an
external scheduler (GitHub Actions or cron-job.org) to run `ingest` + `analyze`.
The catch is storage — most free tiers wipe the disk on restart, so you'd need a
persistent volume or a hosted Postgres. The static route above avoids that
entirely, which is why it's the recommended path. The frontend already supports
both modes automatically, so nothing in the app needs to change either way.

---

## Troubleshooting

- **Site is empty / "No stories yet."** The pipeline produced no multi-outlet
  events. Open the failed-or-green Actions run and read the **ingest + analyze**
  step logs: usually some feeds returned nothing (fix them with `--discover`) or
  fewer than two outlets covered the same story in that window.
- **404 / blank page on the Pages URL.** Make sure **Pages → Source** is
  **GitHub Actions**, and that a run actually reached the **Deploy** step.
- **Analysis step errors about the key.** The `GEMINI_API_KEY` secret name must
  match exactly.
