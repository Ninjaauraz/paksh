# PAKSH_EXECUTION_STATUS.md

Audit date: 2026-09-19. Method: repository read, live probes of https://paksh.news, Vercel and
Supabase project inspection (read-only), scheduler/log inspection. Labels: **OBSERVED** (seen
directly), **INFERRED** (reasoned from observation), **UNKNOWN** (not checkable from here).

## PRE-PUSH REPORT (2026-09-19, second pass) - read this first

> Sections A-E further down are the original audit written earlier the same day. Their item statuses are
> **superseded by this report**; they are kept as the record of what was found.

### PUSH DECISION: **READY TO PUSH**

Nothing technical blocks pushing. Two items need you but do not gate the push (section "Manual steps").
**Important:** the commits change *source*; production serves the generated `_site/`, which is not rebuilt
until the next pipeline export. The ads/consent fix, the enforced CSP, the cache rules and the Coverage Gaps
fix become live only after `py export_static.py` **and** a push of the regenerated `_site` (the scheduled
job does both at its next run). The post-push checklist below assumes that.

Nothing here has been pushed or deployed, so **no live-production claim is made for any change in this
pass.** Everything below was verified in a sandbox (a copy of the code with a copy of the verified database
backup, a freshly built `_site`, and scratch servers); the live site was not touched.

### Resolved since the first report

| Blocker | Resolution | Evidence |
|---|---|---|
| AdSense loaded before consent, contradicting the privacy policy | Loader removed from `static/index.html`; injected by `loadAdSense()` in `app.jsx` only after an explicit **advertising** consent (own key `paksh-consent-ads`, undecided by default). The old consent is analytics-only and its text says "no ad-tracking", so it could not authorise ads. Banner asks the ad question separately; Settings and Privacy have a toggle; withdrawing reloads the page. English + Hindi | Browser, real build: 0 Google requests before consent and after decline; after "Allow ads" the script, sodar and 2 ad frames load; withdrawal reloads with no ad traffic; 10 routes at 375 px clean. `test_ads_consent_csp.py` (21 checks) |
| CSP report-only "because of ads" | Promoted to **enforced** (`CSP_POLICY` in `export_static.py`). Live report-only evidence showed the only violations were Google's ad hosts, now allowlisted explicitly | Browser: no violations across 12 routes + the consent flow; a foreign script, an inline script and a foreign frame are blocked (`disposition: enforce`) |
| Off-machine backup did not exist | `offsite_backup.py` built and tested; **inactive until you create one config file** (see below) | 32-check test file; real-size trial (see Backup status) |
| 3 obsolete test failures | All three confirmed obsolete and resolved without changing production code (see Test status) | 46/46 test files pass in the sandbox |
| Coverage Gaps capped at 40 per column | Full ranked list in `blindspots-all.json`, fetched lazily (first pass) | 314/314 gaps; English page reaches all 187 |

### Remaining blockers

**None that stop the push.** Open items (none is a code defect):

1. **Off-machine backup credentials** - one manual step (below). Until done, the dataset exists on one disk plus
   same-disk backups. Not a push blocker; a data-safety one.
2. **Privacy-policy wording** - deliberately **not edited** (per instruction). With consent-gating in place the
   site now does what the policy *promises* ("ask for your consent before any advertising cookies are set"),
   but two sentences become inaccurate for a visitor who allows ads and need your review: "Paksh sets no
   advertising cookies and does not track you across other websites" and the Advertising card "No ad network is
   loaded until it's configured and disclosed, today the slots are inert placeholders". Google, not Paksh,
   sets the cookies; the wording is your/legal's call.
3. **Google's EEA/UK consent rule (UNKNOWN)** - Google requires a certified consent platform to serve ads to
   EEA/UK visitors. I did not add one (you asked for no framework unless insufficient); the audience is
   India-focused, but ad delivery to EEA/UK visitors may be limited. Not verifiable from here.

### Security status

| Check | Result |
|---|---|
| Secrets | **Clean.** 919 built files scanned (every top-level/static/data file + a 1-in-25 sample of ~17k per-story files); the only JWT is the public `anon` key; `service_role` appears only in a code comment saying it is never used. Git history clean for Groq/Gemini/Cerebras/Supabase-secret key shapes (earlier pass) |
| Sensitive paths | 19,087 files in the deploy root: none of `.py .db .env .jsx .map .md .bat .pem .key .log`. (Live probes of `/.env` etc. were done in the first pass; they will be re-run after deploy) |
| `javascript:` URLs | Verified on the new build: a story whose first source is `javascript:alert(...)` renders 0 such links; the 9 real links are intact |
| RLS (live Supabase, read-only, re-run) | 5/5 tables RLS on; every policy scoped to `auth.uid()` (0 unscoped). Advisors unchanged: mutable `search_path` on the leftover `search_events()` and leaked-password protection (irrelevant to OTP-only login) |
| CSP | Enforced; no `unsafe-inline`/`unsafe-eval` in `script-src` |
| Local API (`main.py`, sandbox, not deployed) | Reads 200; POST/PUT/DELETE/PATCH = 405; unknown route 404; unpublished (`content_complete=false`) stories 404 by id. Notes: `CORS *`, FastAPI `/docs` exposed, `/api/events` is 27.8 MB unpaginated - all irrelevant while the app is not deployed, but fix before anyone deploys it |
| Production/staging separation | Production = static `_site` + Supabase accounts only; no production API exists. Staging = local `main.py` on the local SQLite (the same physical file production exports from) and the **same** Supabase project (no staging project). The bundle has no localhost/staging URL in executable code (one comment names a staging URL); the API base defaults to same-origin |

### Backup status

- **Layer 1 (local, on this disk):** `backup_db.py --keep 5`, scheduled daily; a verified backup was taken today.
- **Layer 2 (off-machine, encrypted):** `offsite_backup.py` - built, tested, **not active**. AES-256-GCM chunked
  encryption on this PC, S3-compatible target (R2/B2), size verified after upload, retention (default newest 7),
  `--restore-test`, `--restore` (never overwrites). Credentials live in
  `%LOCALAPPDATA%\Paksh\offsite_backup.env` (the tool refuses a config inside the repo). The scheduled job runs it
  only if that file exists.
- **Tested:** signing reproduces AWS's two published SigV4 vectors; encryption rejects wrong passphrase, bit flips,
  truncation, appended data and reordered chunks; full cycle vs a signature-verifying fake S3; the `.bat` block
  executed under `cmd.exe` in both states. **Real-size trial** (local fake S3): 2.32 GB -> 1.29 GB encrypted in
  45 s; restore-test PASSED in 55 s, `integrity_check = ok`, 19,652 events and 599,590 articles matching exactly.
- **Not tested (needs your account):** the real R2/B2 endpoint, real upload speed, the first scheduled run.
- Procedure, retention and restore steps: `docs/BACKUP_AND_RESTORE.md`.

### Test status

**46 of 46 test files pass** in the sandbox (a copy of the code + a copy of the verified database backup + a
freshly built `_site`), including the 5 new/replaced ones. Run there, not against the live database.

| Was failing | What it was | What happened |
|---|---|---|
| `test_phase22` | pinned "exactly 9,933 orphaned articles" in the real DB (a Phase 2.2 snapshot; 10,015 now after consolidate/cleanup). Intent: "this test never touches the real DB" | **Updated:** a read-only before/after comparison, which verifies that intent exactly (10,015 == 10,015) |
| `test_phase6b` (check 17) | made a live Supabase `search_events` call that can never succeed again (content tables retired) | **Updated:** the routing contract it protects still exists in `main.py`, so it is tested with a stubbed Supabase tier. Checks 1-16, 17b, 18 unchanged |
| `test_phase6d` | pinned the server-driven `/api/search` design Phase 18B reversed; its "compile check" ran the whole export | **Removed and replaced** by `test_search_client_side.py`: runs the app's real matcher in Node (AND, case, Hindi, hostile input), checks debounce/status states and archive loading, compiles into a temp file |

No assertion was weakened and no production code was changed to satisfy a test. New this pass:
`test_ads_consent_csp.py` (21), `test_offsite_backup.py` (32), `test_search_client_side.py`.

### Ads / consent status

Implemented and browser-verified (details above). Decision points still yours: the policy wording (blocker 2),
whether to add a certified consent platform for EEA/UK (blocker 3). Google cookies already set cannot be cleared
by withdrawal; the visitor clears them in their browser.

### CSP status

**Enforced**, not report-only. There is no demonstrated technical reason to keep report-only: the only
violations ever observed came from Google's ad hosts, which are now explicitly allowlisted (script:
`pagead2.googlesyndication.com`, `*.adtrafficquality.google`; frame: `googleads.g.doubleclick.net`,
`tpc.googlesyndication.com`, `*.adtrafficquality.google`, `www.google.com`; connect: sodar hosts).
**One thing only a deploy can prove:** whether *ad fill* on `paksh.news` needs any further Google host. If it
does, ads (not the site) degrade; the fix is one line in `CSP_POLICY`, and the rollback is reverting commit
`cd75db9252`'s `export_static.py` change and re-exporting.

### Production readiness

Sandbox verification of the rebuilt output: **static checks 30/30** (files, secrets, ad tags, canonical/OG/
JSON-LD provenance, sitemap 8,670 URLs unique and canonical-host, robots, 308 redirect config, real-404 route,
CSP enforced with no report-only header, cache rules, Coverage Gaps data); **browser checks** on desktop and
375 px (consent, Coverage Gaps totals, story page, search EN/HI/hostile, login form, settings, 10 routes, zero
CSP violations); watchdog script HEALTHY against the local build; workflow YAML valid. Verified **against the
generated configuration**, not against Vercel: cache-header and redirect behavior on the real platform, and
everything on the live domain, are confirmable only after deploy.

Not verified: real email sign-in (needs an inbox); Lighthouse; the GitHub Action running (it has not been
pushed; **no external execution is claimed**).

### Story Evolution design status

`docs/STORY_EVOLUTION_DESIGN.md` written; **not implemented**. Measured on the real data: derivation for all
19,637 stories takes 2.4 s; ~390 B per story; no schema change for v1; article-derived owner sets equal the
stored coverage in 99.98% of stories; median first-to-last outlet span 13.7 h; in 9,606 stories a second side
appears >3 h after the first. Reuses `storylines.py`/`StorylineTimeline`, not the shadow story-memory tables.
Four decisions needed before implementation are listed at the end of that document.

### Manual steps (yours)

1. **Backup (data safety, not a push gate):** create an R2/B2 bucket + bucket-scoped token, create
   `%LOCALAPPDATA%\Paksh\offsite_backup.env`, save the passphrase in your password manager, then
   `py offsite_backup.py --check`, `--run`, `--restore-test`. Full steps: `docs/BACKUP_AND_RESTORE.md`.
2. **Privacy wording review** (blocker 2 above).
3. Enable 2FA on GitHub, Vercel and Supabase (not checkable from here).

### Post-push verification (do not skip; nothing above has been checked on the live site)

1. Publish the regenerated site: `py export_static.py`, then commit/push the `_site` changes with GitHub Desktop
   (or let the next scheduled job do it). Wait for the Vercel deployment to be READY.
2. Headers and no ad tag (expect one enforced `content-security-policy`, no `-report-only`, and **no** ad host in the page):
   `curl -sI https://paksh.news/ | grep -i content-security-policy` and `curl -s https://paksh.news/ | grep -c -i googlesyndication` (expect 0).
3. Cache rule (expect `max-age=31536000, immutable`; if it is not there nothing breaks, the rule just has no effect):
   `curl -sI https://paksh.news/static/fonts/-F63fjptAgt5VM-kVkqdyU8n1i8q1w.woff2 | grep -i cache-control`
4. Coverage Gaps file exists and totals match: `curl -s https://paksh.news/data/blindspots-all.json | py -c "import sys,json;a=json.load(sys.stdin)['aggregate'];print(a)"`
5. External watchdog: `py site_watch.py`, and confirm the **Site watch** workflow appears and passes under GitHub -> Actions (enable Actions if prompted).
6. **In a fresh/private browser window on https://paksh.news:** DevTools -> Network: before touching the banner there must be **no** request to google/doubleclick/googlesyndication; click **Decline** + **No ads** and reload (still none); then in a new private window click **Allow ads** and confirm ads request Google **and the Console shows no "Content Security Policy" errors** (if it does, note the blocked host and tell me).
7. Repeat step 6 at phone width, and open a story, Coverage Gaps, search and Settings.
8. Rollback if needed: revert the relevant commit in GitHub Desktop, run `py export_static.py`, push.

---

## Original audit (earlier on 2026-09-19)

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
