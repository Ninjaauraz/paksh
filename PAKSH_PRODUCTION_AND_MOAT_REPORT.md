# PAKSH_PRODUCTION_AND_MOAT_REPORT.md

Date: 2026-09-19. Companion to `PAKSH_EXECUTION_STATUS.md` (the audit). Labels: **OBSERVED**
(seen directly), **VERIFIED** (tested, result recorded), **INFERRED** (reasoned), **UNKNOWN**.

## EXECUTIVE STATUS: **READY WITH BLOCKERS**

Paksh is already live at https://paksh.news and healthy (VERIFIED today: 200s, HSTS, redirects,
fresh data, 8,654 events, 8,670 sitemap URLs). What the brief called a "cutover" does not apply:
production is a **static export on Vercel** with a small Supabase project used only for accounts;
there is no deployed API and no content database to cut over to. The brief's `FRONTEND -> API ->
SUPABASE` target would break the first invariant in `CLAUDE.md` (static export, no server runtime),
so it was **not** built; that is Sameer's call to change, not mine.

Two items are called blockers because they are decisions only Sameer can make, not because the
site is broken:

1. **Advertising vs. the privacy policy.** The Google AdSense loader in `static/index.html` runs for
   every visitor before any consent, and ad frames render. The published privacy policy says Paksh
   "sets no advertising cookies" and will "ask for your consent before any advertising cookies are
   set". The code's own comment says ads are OFF. Either the site or the policy must change; I did
   not choose (revenue, AdSense verification and legal wording are yours).
2. **Off-machine backup.** The accumulated dataset (~2.3 GB, ~600k articles) exists on one disk. A
   verified backup was taken today and a daily one is now scheduled, but they share that disk.

**Nothing was pushed or deployed.** All work is in 9 local commits on `main`. Vercel deploys when you
push (GitHub Desktop, as usual).

---

## PRODUCTION

### Changed (9 commits, `ec9fa6ac51..HEAD`)

| Commit | What | Why |
|---|---|---|
| `audit: document production state` | `PAKSH_EXECUTION_STATUS.md` | The real architecture, environment map, classified findings |
| `fix: production environment wiring` | `reframe_scheduled.bat` runs `backup_db.py --keep 5` daily | Backups were documented as scheduled but never invoked; newest was 14 days old. `--keep 5` (~11.5 GB) because C: has ~32 GB free |
| `fix: production smoke test failures` | Coverage Gaps reaches every gap (`export_static.py`, `app.jsx`) | Header counted 314 gaps but only 40/column (max 80, fewer per language) were reachable |
| `feat: strengthen Paksh differentiation` | Story JSON-LD: author, copyright holder/year, `isBasedOn` (<=8 cited sources) | Machine-readable provenance on every story |
| `docs: document provenance and copycat response` | `docs/COPYCAT_RESPONSE.md`, `provenance_manifest.py`, METHODOLOGY s9, `DEPLOY.md` banner | Evidence system; methodology now matches the code |
| `fix: production performance` | 1-year immutable cache for hashed fonts; 1 day for pinned React | Everything was `max-age=0`; returning readers re-checked ~8 fonts per page |
| `feat: observability` | `site_watch.py`, `.github/workflows/site-watch.yml`, `docs/OPERATIONS.md` | Every existing alert runs on the publisher PC and cannot fire if it is down |
| `fix: production security issues` | Only `http(s)` source URLs become links | Feed-supplied `javascript:` URLs were rendered as hrefs |

Also done, outside git: a verified DB backup (`paksh_backup_20260919_183813.db`: 19,652 events,
599,590 articles, integrity ok).

### Verified

- **Live site (OBSERVED):** headers, 308 redirects for `www`/`paksh.vercel.app`/project aliases,
  robots + sitemap, real 404 + `noindex` for bad story IDs, canonical/OG/Twitter/JSON-LD, Brotli on,
  no source maps, `/.env` `/.git/config` `/paksh.db` `/main.py` `/static/app.jsx` all return only the
  4,286-byte app shell.
- **Full build (VERIFIED):** `export_static.py` run twice in a sandbox against a copy of the verified
  backup: 8,654 events, 124 sources, `vercel.json` valid.
- **Coverage Gaps (VERIFIED):** 314/314 gaps exported; teaser file is an exact prefix of the full list;
  the English page reaches all 187 English gaps (was <=40 per column).
- **Mobile smoke (VERIFIED, 375 px):** home, Developing Stories ("View all (198)" = 198 storylines;
  hub expands to all 198), Topics, About, Sources, Privacy, Contact, Login, Saved, Account, Lens,
  My Paksh, Settings: no horizontal overflow, no script errors. Search: English (227 results), Hindi
  (223), no-match (0), blank (browse), and `((<script>alert(1)</script>[*` (0, no crash).
- **URL fix (VERIFIED in browser):** story with first source `javascript:alert(...)` renders 0
  `javascript:` hrefs; the 9 real links are unchanged.

### Not verified (be aware)

- **Real sign-in (OTP), session persistence and logout.** Needs an email inbox; I only confirmed the
  login form renders and that account routes render (their data is protected by RLS regardless).
- **The caching headers on the live site.** They are in the generated `vercel.json` but only take
  effect after your next push. After deploying, check: `curl -sI https://paksh.news/static/fonts/<any>.woff2`
  should show `max-age=31536000, immutable`. If Vercel ignores it, nothing breaks; caching just stays as-is.
- **`site-watch` workflow.** The script is tested; the GitHub Action only starts running after the
  push (Actions must be enabled for the repo).
- **Lighthouse/Core Web Vitals.** Not measured. Payloads (VERIFIED): app.js 95 KB, events.json 587 KB,
  blindspots 38 KB (Brotli); TTFB ~0.4 s. The 2.8 MB archive loads only when Search/Topics are used.

### Remaining blockers

The two decisions above (ads/consent; off-machine backup).

### Remaining P2/P3 debt

- Strict CSP stays report-only: enforcing it would block AdSense (see blocker 1).
- Unused `CONTACT = "corrections@paksh.example"` constant in `app.jsx` (defined, never rendered).
- Obsolete Supabase remnants: `search_events()` function; retired code (`supabase_content.py`,
  `sync_to_supabase.py`, `migrate_to_supabase.py`, `content_cache.py`) still in the repo.
- Three obsolete tests fail (details under Tests). Not rewritten, per the brief.
- ~10 GB of old unmanaged `paksh.db.bak*` / `paksh.db.pre_phase*` files in the project root.
- No staging Supabase project: testing the frontend with a real login writes to production accounts.
- anon/authenticated hold TRUNCATE/TRIGGER/REFERENCES grants on account tables (Supabase default;
  not reachable via the API and RLS blocks rows).

---

## SECURITY

| Area | Result |
|---|---|
| Secrets | **Clean (VERIFIED).** Only the public Supabase `anon` JWT is committed (decoded: `role: anon`, designed for browsers). `ai_keys.env`, `.env`, `*.db` gitignored. No Groq/Gemini/Cerebras/Supabase-secret key shapes in tracked files, `_site`, or git history (excl. generated pages/docs). |
| Supabase | RLS enabled on all 5 tables; every policy scoped to `auth.uid()`; `handle_new_user` is security-definer with a pinned `search_path`; no edge functions. Advisor warnings: mutable `search_path` on the leftover `search_events()` and "leaked-password protection off" (irrelevant: OTP-only login). |
| Environments | No localhost/staging/dev URL hard-coded in the deployed bundle or shell. Staging shares the **production** Supabase project (documented risk). |
| Exposure | No debug/admin routes on the live site; `main.py` (not deployed) has no write endpoints; `CORS *` there is irrelevant to production. |
| Injection | JSON-LD escaping re-tested against hostile titles and sources (`test_phase42_provenance.py`). No `innerHTML`/`eval`/`dangerouslySetInnerHTML`; all `target=_blank` links use `noopener`. |
| **Issue found and fixed** | Feed-supplied `javascript:` URLs could render as clickable links (React 18 only warns). Now `http(s)` only. |
| **Issue found, not fixed (decision)** | Unconditional AdSense loading contradicts the privacy policy and the code's comment. |
| Residual risks | Anyone with a key to your Vercel/GitHub/Supabase accounts can publish; enable 2FA on all three (not checkable from here). The `paksh_api_base` localStorage override only affects the reader's own browser and the API mode is unused in production. |

---

## COMPETITIVE MOAT

**Defensible today (not obtainable from the browser):** the ~600k-article, 3-month corpus with
per-article `published`/`fetched_at` and outlet attribution; the hand-verified source-lean roster
(124 outlets, ~6.5k registry entries); clustering/consolidation tuning; the pipeline that keeps it
fresh; account data.

**Easily copyable:** everything visible: layout, bias-bar treatment, the coverage-gap concept, client
JS, and the text of every summary and framing (bulk-scrapeable from `/data/*.json`). Copyright
protects the *expression* (code, artwork, text), not the idea of a lean bar.

**A finding that changes the roadmap (OBSERVED + INFERRED).** The "story memory" tables are nearly
empty (4 relationships, 2 deltas) and `analysis_json` stores only the *latest* coverage snapshot, so
the time-series of how coverage of a story changed is not stored as such. But all 599,590 articles
carry `published` and `fetched_at`, and in a sample of 816 recent multi-article stories 775 (95%)
had articles arriving across two or more distinct hours. **Coverage evolution can therefore be
reconstructed retroactively from data already being kept.** That is the cheapest, most defensible
new feature Paksh can build, and a copycat cannot fake a history it never collected.

**Strengthened this pass:** provenance metadata on every story; a dated evidence manifest; an
off-PC uptime/freshness watchdog; the Coverage Gaps page now honestly reflects the data; a scheduled
backup of the dataset.

### Differentiators, ranked

Scores 1-5 (5 = best; complexity 5 = easiest). Ranked by value x differentiation x defensibility.

| # | Feature | User value | Differ. | Ease | Data needed | Defensible | Notes |
|---|---|---|---|---|---|---|---|
| 1 | **Coverage evolution**: "who joined the story when" timeline per story, and gap open/close over time | 5 | 5 | 3 | Exists (article timestamps, reconstructible) | 5 | Also enables "this gap closed after 6h" |
| 2 | **Story evolution timeline**: how the neutral account changed as reporting arrived | 5 | 4 | 2 | Needs snapshots going forward (summary history); partly derivable | 5 | Start appending snapshots now so history accrues |
| 3 | **Crawlable storyline pages** + sitemap entries | 4 | 4 | 4 | Exists (198 storylines) | 3 | Currently SPA-only, not in the sitemap; pure SEO + surface area |
| 4 | **Transparency panel**: "why is this a Coverage Gap / developing story?" with the actual numbers (L, R, threshold 4 & 25%) | 4 | 3 | 5 | Exists | 3 | Backed by METHODOLOGY s9 |
| 5 | **Source landscape / regional perspective**: national vs regional, English vs Hindi coverage of the same story | 4 | 4 | 3 | Outlet `region`/language exist | 4 | Needs a careful, non-judgemental presentation |
| 6 | **Monthly Coverage Gap report** (original data journalism, citable, dated) | 4 | 4 | 4 | Exists | 4 | Creates provenance and press value a clone cannot copy |
| 7 | **Historical story search** with date/topic/outlet filters over the archive | 3 | 3 | 3 | Exists (8,654 events) | 3 | The archive already loads lazily |
| 8 | **Related stories** (`event_relationships`) | 3 | 3 | 2 | Only 4 rows; judgement pipeline is in shadow mode | 4 | Needs the judge enabled first; scope separately |
| 9 | **Reading Lens that changes the feed** (not cosmetic) | 3 | 2 | 3 | Reading history exists | 2 | Easily copied concept; value is retention |
| 10 | Second publisher / cloud cron | 2 | 1 | 1 | n/a | n/a | Reliability, not differentiation; big change |

---

## COPYCAT RESPONSE

- **Evidence/provenance system (built):** `docs/COPYCAT_RESPONSE.md` (what is original, public,
  proprietary; a step-by-step evidence checklist; a response ladder that stays honest about what
  copyright covers) and `provenance_manifest.py` (read-only dated snapshot: git head and first
  commit, SHA-256 of core files, DB counts/date ranges, site freshness). Run monthly and commit the
  output so git stamps it. Facts already citable: first commit `7b1d08d75b` on 2026-06-01, 505 commits
  by one author account, Vercel project created 2026-05-31, `paksh.news` attached 2026-08-08,
  Supabase project 2026-05-07.
- **If copying is detected:** preserve first (screenshots, saved HTML, Wayback captures, a match
  table, a fresh manifest), assess *expression vs. idea*, and only then contact, file a platform
  report, or involve counsel. Nothing is automatic and no legal threats are published.
- **Do not** spend effort obscuring the frontend.

---

## TEST RESULTS

Run in a **sandbox copy** (code + a copy of the verified backup as `paksh.db` + a freshly built
`_site`), never against the live database.

| Suite | Result |
|---|---|
| All 44 test files (`test_*.py`, `tests/`) | **41 pass, 3 fail** |
| New: `test_phase41_synthesis_prompt.py` (31 checks) | pass |
| New: `test_phase42_provenance.py` (11 checks) | pass |
| Site/vercel.json-dependent: `test_phase9`, `6c`, `7b`, `24b`, `30cg` | pass against the rebuilt `_site` |
| `test_phase22` | FAIL: pins an exact historical DB count ("exactly 9,933 orphaned articles"); data has moved on. Not caused by this work |
| `test_phase6b` | FAIL: needs the retired Supabase `search_events` RPC (404) |
| `test_phase6d` | FAIL: asserts the old server-side `/api/search` code that Phase 18B replaced with client-side search |
| `site_watch.py` | healthy on live (exit 0); strict limits (exit 1); unreachable host (exit 1, no crash) |
| Browser smoke (mobile 375) | as listed under Production |

The three failures are obsolete tests, unchanged by this work (they failed identically in an earlier
sandbox run). I did not rewrite them. Not run: end-to-end OTP login; the on-PC scheduled jobs
themselves (their `.bat` edit is 6 lines, reviewed but not executed end to end).

---

## NEXT 30 DAYS (features that widen the lead, not redesigns)

**Week 1 - decide and protect**
- Decide ads/consent (blocker 1). Then either gate the loader behind the existing consent banner or
  rewrite the policy; then promote the CSP.
- Push; verify: font cache headers, `site-watch` first run, `py provenance_manifest.py` committed.
- Copy the newest backup off the machine; archive the ~10 GB of old root `.bak` files.

**Week 2 - start accumulating what a clone cannot**
- Append-only snapshot per event each export (lean counts + summary hash) so evolution accrues
  automatically (differentiator #2).
- Crawlable `/storyline/<id>` pages + sitemap entries (#3).

**Week 3 - ship the first data-backed feature**
- Coverage-evolution timeline on the story page, reconstructed from article timestamps (#1), with
  the transparency panel (#4). Desktop and mobile; no new dependencies.

**Week 4 - publish original analysis**
- First monthly Coverage Gap report from the archive (#6); commit the provenance manifest.
- Review whether to enable the relationship judge (#8) or leave it in shadow mode.

## FINAL OPERATING NOTE

The site does not need to be uncopyable. It needs to keep collecting and correctly interpreting a
history nobody else has. This pass fixed what was misleading (gap counts, the ads/policy mismatch
flagged), protected what is irreplaceable (the dataset), and pointed the next month at features whose
value grows with every day of data.
