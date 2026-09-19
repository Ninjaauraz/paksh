# PAKSH_EXECUTION_STATUS.md

Audit date: 2026-09-19. Method: repository read, live probes of https://paksh.news, Vercel and
Supabase project inspection (read-only), scheduler/log inspection. Labels: **OBSERVED** (seen
directly), **INFERRED** (reasoned from observation), **UNKNOWN** (not checkable from here).

> **Headline.** Paksh is *already in production* and is a **static export**, not a
> frontend + API + database system. The "staging to production cutover" in the brief describes an
> architecture that no longer exists here (the Render API and Supabase content tables were
> retired). The work that matters is therefore hardening, honesty of the public claims, protecting
> the accumulating dataset, and differentiation, not an API cutover. The brief's target
> (`USER -> FRONTEND -> API -> SUPABASE`) would also violate the first stated invariant in
> `CLAUDE.md` ("the site stays a static export; no server runtime, no API requirement"), so it
> was **not** built. That is a decision for Sameer (see section E).

---

## A. CURRENT ARCHITECTURE (as it actually is)

```
RSS feeds + GDELT
      |  ingest.py / gdelt_source.py           (one Windows PC, Task Scheduler + live.py)
      v
paksh.db  (SQLite, ~2.2 GB, WAL)  <-- single copy of the accumulated dataset, local disk
      |  cluster.py (bge-m3 via local Ollama) -> events
      |  analyze.py (Groq gpt-oss-120b / Gemini flash-lite pool) -> summary, framing, topic
      |  (bias bar + coverage gaps are pure arithmetic on editorial lean labels, sources.py)
      v
export_static.py  ->  _site/  (events.json, blindspots.json, storylines*, per-story JSON + HTML,
      |                          sitemap, robots, RSS, OG cards, vercel.json, freshness.json)
      v
safe_autopush.py  ->  git commit + push to github.com/Ninjaauraz/paksh (main)
      v
Vercel (project "paksh", Root Directory = _site)  ->  paksh.news
      v
Browser: React 18 (self-hosted) + app.js precompiled from static/app.jsx
   - data: same-origin /data/*.json   (probe of /api/topics -> 404 -> "static" mode)
   - search: client-side over events.json + events-archive.json
   - accounts (optional): Supabase Auth (email OTP) + 5 RLS-protected tables, anon key in client
```

| Item | Reality |
|---|---|
| Frontend | `static/app.jsx` (single file) -> `_site/static/app.js`; no bundler, no Babel in the browser. OBSERVED |
| API | `main.py` FastAPI exists in the repo and runs **locally only** (staging config in `.claude/launch.json`, port 8180). Not deployed anywhere. `/api/*` on paksh.news returns 404. Frontend code that probes `/api/*` therefore always falls back to static. OBSERVED |
| Database (content) | SQLite `paksh.db` on the publisher PC. **No content tables in Supabase.** OBSERVED |
| Database (accounts) | One Supabase project `zzjsjqqcpyyodatlmcux` ("Paksh", ap-south-1): `profiles`, `reading_history`, `saved_stories`, `follows_topic`, `follows_story`; RLS on for all. 7 profiles, 100 reading_history rows. OBSERVED |
| Hosting | Vercel project `paksh`, auto-deploy from `main`. Domains: `paksh.news` (primary), `www`, `paksh.vercel.app`; alternates 308-redirect to `paksh.news`. Latest production deployment = commit `ec9fa6ac51` (READY). OBSERVED |
| CI | **None.** No `.github/workflows`. `DEPLOY.md` (GitHub Pages + Actions) is obsolete. OBSERVED |
| Scheduler | 3 Windows Task Scheduler jobs (00:30 refresh, 05:30 nightly, 07:30 reframe) + manual `live.py`; `runlocked.py` interlock; `safe_autopush.py`. OBSERVED |
| Monitoring | `verify_fresh.py` (staleness + deploy-check), `check_scheduled_health.py` (missed/failed tasks), Desktop alert files, public `/data/freshness.json`. OBSERVED |
| Ads | Google AdSense loader (`ca-pub-3441154254234680`) is hard-coded in `static/index.html` and loads for every visitor; ad frames from `googleads.g.doubleclick.net` render. `ADSENSE_CLIENT` in `app.jsx` is `""`. OBSERVED |

### Environment separation (as required by the brief)

| Path | Actual |
|---|---|
| FRONTEND PRODUCTION -> API | none; same-origin static `/data/*.json` |
| API PRODUCTION -> DATABASE | no production API exists |
| FRONTEND PRODUCTION -> Supabase | project `zzjsjqqcpyyodatlmcux`, anon key (public by design), accounts only |
| STAGING FRONTEND -> STAGING API | local `main.py` on `127.0.0.1:8180`, or any URL put in `localStorage.paksh_api_base` by hand |
| STAGING API -> STAGING DATABASE | local `paksh.db` (SQLite); **the same physical file production exports from** |
| STAGING FRONTEND -> Supabase | **same production Supabase project.** There is no staging Supabase. Anyone testing the frontend locally with a real login writes to production account tables. |

No localhost / staging / dev URL is hard-coded in the deployed bundle or shell (only the
`paksh_api_base` / `PAKSH_API_BASE` override hooks, which default to same-origin). OBSERVED

---

## B. PRODUCTION STATUS

| # | Item | Class | Evidence / note |
|---|---|---|---|
| 1 | Site live on paksh.news, HTTPS, redirects, sitemap, robots, canonical, OG/Twitter, JSON-LD | SAFE TO SHIP | Verified live (Phase 40B, re-probed today) |
| 2 | Security headers (HSTS preload, X-Frame DENY, nosniff, COOP, Permissions-Policy, frame-ancestors) | SAFE TO SHIP | Live response headers |
| 3 | No secrets in repo/`_site`; only the public anon JWT (`role: anon`) is committed | SAFE TO SHIP | Pattern scan + JWT decode; `ai_keys.env`, `.env`, `*.db` are gitignored. Git history (excluding `_site`/docs) also clean for Groq/Gemini/Cerebras/Supabase-secret key shapes; the only `service_role` hit is a comment saying it is never used |
| 4 | Sensitive paths (`/.env`, `/.git/config`, `/paksh.db`, `/main.py`, `/static/app.jsx`) | SAFE TO SHIP | All return the 4,286-byte SPA shell; only `_site/` is served; `app.js.map` is 403 |
| 5 | Supabase RLS and policies | SAFE TO SHIP | Every policy scoped to `auth.uid()`. Advisor warnings are cosmetic (see #17, #18) |
| 6 | **Unconditional AdSense loader contradicts the privacy policy and the code's own comment** | **REQUIRED BEFORE CUTOVER (decision)** | Policy says "sets no advertising cookies ... will ask for your consent before any advertising cookies are set". Loader runs pre-consent. Not changed: revenue + AdSense verification + legal wording are Sameer's call |
| 7 | **No scheduled DB backup; newest backup is 2026-09-05 (14 days old); backups on the same disk** | **REQUIRED BEFORE CUTOVER** | `backup_db.py` exists, is documented as scheduled, but nothing invokes it. The DB *is* the moat |
| 8 | Coverage Gaps: aggregate says 314 gaps but the exporter keeps only 40 per column (max 80); code comment about "15 per column" is stale | REQUIRED BEFORE CUTOVER | `export_static.py` `_COL_N = 40`; live `blindspots.json` aggregate `total=314`, lists 40+40 |
| 9 | Developing Stories teaser + "View all developing stories (N)" | SAFE TO SHIP | Rail shows 4, link shows the true count N and opens the full hub (198 storylines) |
| 10 | Search | SAFE TO SHIP | Client-side over the same static data; debounced; empty/error states exist. There is **no dynamic search backend**, by design |
| 11 | Strict CSP is report-only and cannot be promoted as-is | POST-LAUNCH | Enforcing it would block AdSense (and its frames). Depends on decision #6 |
| 12 | Single publisher machine = single point of failure for data, ingest and deploy | POST-LAUNCH | Documented in `SETUP_HANDOFF.md`; two pushes failed on 2026-09-17 (DNS) and were alerted, not lost |
| 13 | No staging Supabase project | POST-LAUNCH | Only matters if account features are developed against production |
| 14 | `DEPLOY.md` describes a retired GitHub Pages setup | POST-LAUNCH (docs) | Bannered as obsolete in this pass |
| 15 | Unused `CONTACT = "corrections@paksh.example"` constant in `app.jsx` | POST-LAUNCH | Only defined, never rendered |
| 16 | `main.py` (local API): `CORS *`, no write endpoints, `/health` cheap | SAFE TO SHIP | Not deployed |
| 17 | Supabase `search_events` function: mutable `search_path`, references removed content tables | OBSOLETE | Leftover; anon-executable but has nothing to search. Drop in a future cleanup |
| 18 | Supabase "leaked password protection disabled" | OBSOLETE | Auth is email-OTP, no passwords |
| 19 | Render-based `/api/search`, Supabase content sync (`sync_to_supabase.py`, `migrate_to_supabase.py`, `supabase_content.py`, `content_cache.py`) | OBSOLETE | Retired per `app.jsx` comment; code remains in repo |
| 20 | anon/authenticated hold TRUNCATE/TRIGGER/REFERENCES grants on account tables | POST-LAUNCH (P3) | Supabase default; not reachable through PostgREST and RLS blocks rows. Hardening only |

---

## C. CUTOVER RISKS (real ones only)

1. **Unconsented advertising vs. published privacy claim** (item 6): a factual mismatch between
   what the site does and what its policy says. Highest legal/credibility exposure.
2. **Dataset loss** (item 7): one 2.2 GB file on one disk (C: is 94% full, 32 GB free), backups
   two weeks stale and co-located. A disk failure would erase the entire accumulated history that
   a copycat cannot reproduce.
3. **Coverage Gaps understatement** (item 8): the homepage stat and methodology text speak of
   314 gaps while at most 80 are reachable, fewer per language (the page filters to the reader's
   language).
4. **Publisher PC dependency** (item 12): if the PC sleeps/loses network, the site simply goes
   stale (freshness alerts exist, but only locally on that machine).

Not risks: exposed secrets, open write endpoints, SQL injection, staging leakage into the prod
bundle, debug routes. Each was checked and found clean (section in the final report).

---

## D. COPYCAT / COMPETITIVE EXPOSURE

| Layer | Exposure | Notes |
|---|---|---|
| 1. UI / visual concepts | **Easy to copy** | Fully visible in the browser; bias-bar, masthead, layout can be recreated from screenshots |
| 2. Publicly visible functionality | **Easy to copy** | Search, topic pages, storyline hub, coverage-gap columns are client-side JS shipped to every visitor |
| 3. Original content | Partly copyable | Every summary/framing is public in `/data/*.json` and per-story pages; bulk-scrapeable. Provenance is the defence (see `docs/COPYCAT_RESPONSE.md`) |
| 4. Proprietary data processing | **Not visible** | Ingest breadth (GDELT + RSS), embedding-based clustering thresholds, consolidation, story-identity logic live only in the Python pipeline |
| 5. Proprietary analysis | Output visible, method partly public | Per-side framing, coverage-gap ranking (recency-weighted), storyline threading. Method is deliberately documented (`METHODOLOGY.md`, About page); the *accumulated* results are the moat |
| 6. Backend logic | Not visible | Not deployed; nothing to attack or copy from the site |
| 7. Infrastructure | Low value | Static hosting; trivially reproducible and not a differentiator |
| 8. User / account data | Protected | Supabase RLS, per-user policies; 7 profiles today |

**What a clone cannot get from the browser:** the ~586k-article corpus and its history, the
editorial source-lean roster (`sources.py`, `verified_registry.py`), the clustering/consolidation
tuning, and the *time series* (how a story and its coverage evolved). Everything above that line
is the moat; everything else is visible.

---

## E. RECOMMENDED EXECUTION ORDER

Done or in this pass (small, reversible, no architecture change):
1. `audit:` this document.
2. Protect the dataset: take a verified backup now; wire `backup_db.py` into the daily chain.
3. Make Coverage Gaps honest: full ranked list available on demand (lazy file), no 40-item ceiling.
4. Provenance: richer JSON-LD (author, copyright holder, sources consulted); `docs/COPYCAT_RESPONSE.md`.
5. Bannered the obsolete `DEPLOY.md`.

Needs Sameer's decision before anything is changed:
- **A. Ads/consent.** Either (a) gate the AdSense loader behind the existing consent banner (revenue
  impact; AdSense re-verification risk), or (b) keep unconditional loading and rewrite the
  privacy/consent wording to say so. Until decided, CSP stays report-only.
- **B. Architecture.** Confirm that "static export, no server runtime" remains the rule. If a
  dynamic API is truly wanted, it is a new project (hosting, database for content, auth
  boundary, scheduled ingest not on a PC) and must be scoped separately.
- **C. Off-machine backup / second publisher.** Where should copies of `paksh.db` live (cloud
  bucket, external drive)? Nothing off-disk exists today.
