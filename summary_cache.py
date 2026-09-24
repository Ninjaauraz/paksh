"""
summary_cache.py - fingerprinted reuse of a successful LLM summary/framing call,
so analyze_event() never pays to re-derive the SAME output for the SAME input.

2026-09-25 LLM cost campaign: reframe.py alone re-sends up to 300 events/day
through a full LLM call with NO memory of any previous attempt - a candidate
that fails today (e.g. a transient malformed-JSON hiccup, or a rate limit) is
sent again TOMORROW as a completely fresh, full-price call, even when its
article set never changed in between. This module closes exactly that gap,
narrowly:

  - the cache key (fingerprint) is a hash of the FULLY RENDERED prompt text
    plus a model-tier string - NOT a manually-maintained "prompt version"
    integer someone has to remember to bump. If build_prompt()'s template
    changes even one word, the rendered text changes, the hash changes, and
    every existing cache entry is a natural, automatic miss. Self-versioning,
    not maintained-versioning.
  - the tier string embeds the ACTUAL model id (e.g. "gemini:gemini-2.5-flash-lite"),
    so switching GEMINI_MODEL/OLLAMA_MODEL invalidates old entries for free.
  - ONLY the RAW model output (title/summary/framing/etc, exactly what
    _call_json() returns) is cached - never the postprocess()'d, evidence-
    gated result. analyze_event() always runs postprocess() fresh on every
    cache hit exactly as it does on a cache miss, so content_complete/
    evidence_status are recomputed from CURRENT logic every single time. A
    cached raw summary can never bypass or shortcut the evidence gate - see
    analyze_event()'s own call site for where this is wired in.
  - only a SUCCESSFUL call is ever stored. An exception, an extractive
    fallback, or a generic/empty result is never written - so a previously
    invalid result is never "cached as valid"; the next attempt is a normal,
    real, uncached call.
  - scope (deliberately narrow for this first pass): only the "gemini" and
    "ollama" string backends are cached, where the model actually used is
    known and stable for the whole call. "pool"/"unified"/"rounds" dispatch
    to a provider decided dynamically per-attempt (see ai_providers.py) -
    correctly fingerprinting THAT is more involved and is intentionally left
    out of this narrow implementation (see the LLM cost audit report,
    Phase 5, "not yet validated" section) rather than guessed at.

2026-09-25 INCIDENT FIX: get()/put()/prune() previously always resolved the
real `database` module's global DB_PATH with no way to redirect them - a
benchmark script that imported `database` without first isolating its own
DB_PATH (as any test using a temp fixture DB must) silently wrote real rows
into the PRODUCTION database (18 rows, confirmed harmless and removed - see
the incident report). Every public function here now accepts an explicit
`conn` (an already-open sqlite3 connection the CALLER owns and closes) so a
benchmark/test caller can point this at an isolated database with NO way to
fall through to production by omission. assert_not_production_path() is a
loud, fail-CLOSED guard any ad-hoc script MUST call before touching this
module (or analyze_event()) against anything other than an explicitly
isolated database - see its own docstring."""
import hashlib
import json
import os
from datetime import datetime, timezone

SCHEMA_VERSION = 1   # bump to invalidate every existing cache entry at once

CACHEABLE_BACKENDS = {"gemini", "ollama"}

# How long a cache hit is trusted before it's treated as stale and a fresh call
# is made anyway - a conservative ceiling so a cache entry can never silently
# serve genuinely old output forever. Independent of, and in addition to, the
# fingerprint itself changing whenever the input actually changes.
MAX_AGE_DAYS = 14


class ProductionDBGuardError(RuntimeError):
    """Raised by assert_not_production_path() - see its docstring. A benchmark
    or ad-hoc script hit this on purpose: it means the script is about to
    touch the real production database and was stopped before doing so."""


def assert_not_production_path(path):
    """Fail CLOSED: raise ProductionDBGuardError if `path` is the SAME file as
    the real, configured production database (via paksh_paths.db_path()).

    Call this ONCE, early, in any benchmark/ad-hoc/one-off script BEFORE it
    calls analyze_event() or anything in this module - especially before
    setting database.DB_PATH, so a copy-paste mistake that leaves DB_PATH
    unset (defaulting to whatever paksh_paths resolves, which on a configured
    production machine IS the real database) is caught immediately instead of
    silently writing real rows into production (the exact 2026-09-24
    incident: two benchmark scripts imported `database` with no override at
    all, and summary_cache.put() wrote 18 rows into the live production DB
    before anyone noticed).

    Does nothing (no exception) when `path` is anything else - including a
    temp file, an in-memory DB, or a path that doesn't exist yet."""
    import paksh_paths
    try:
        prod = paksh_paths.db_path()
    except Exception:
        return   # cannot even determine the production path -> nothing to compare against
    if os.path.normcase(os.path.abspath(str(path))) == os.path.normcase(os.path.abspath(str(prod))):
        raise ProductionDBGuardError(
            f"Refusing to proceed: {path} IS the real production database ({prod}). "
            f"A benchmark/test script must point database.DB_PATH at an isolated "
            f"temp file before calling analyze_event() or summary_cache functions. "
            f"See test_summary_cache.py for the correct isolation pattern.")


def tier_for(backend, gemini_model=None, ollama_model=None):
    """The model-tier string embedded in the fingerprint. None if this backend
    is not in the narrow cacheable scope (see module docstring)."""
    if backend == "gemini":
        return f"gemini:{gemini_model}"
    if backend == "ollama":
        return f"ollama:{ollama_model}"
    return None


def fingerprint(prompt_text: str, tier: str) -> str:
    """A hash of the FULLY RENDERED prompt (article selection, region label,
    PDI context if any, and the entire rule/schema template all live inside
    this string already - see build_prompt()) plus the model tier. Any
    material change to any of those - which articles, their text, the
    prompt's own wording, or which model would serve the request - changes
    this fingerprint automatically."""
    h = hashlib.sha256()
    h.update(str(SCHEMA_VERSION).encode("utf-8"))
    h.update(b"|")
    h.update((tier or "").encode("utf-8"))
    h.update(b"|")
    h.update(prompt_text.encode("utf-8"))
    return h.hexdigest()


def _with_conn(conn):
    """(connection, owns_it). If `conn` is given, the CALLER owns it (never
    closed here). Otherwise opens the normal production connection via
    database.get_connection() (unchanged default behavior for every existing
    production call site in analyze.py, which passes no conn)."""
    if conn is not None:
        return conn, False
    import database
    return database.get_connection(), True


def get(fp: str, conn=None):
    """Returns the previously-cached RAW model output dict, or None (cache
    miss, or any problem at all - this must never be able to break analysis).
    `conn`: an already-open connection to use instead of the default
    production connection (see module docstring's INCIDENT FIX note) -
    ordinary production callers omit it and get the unchanged default
    behavior."""
    try:
        c, owns = _with_conn(conn)
        try:
            _ensure_table(c)
            row = c.execute(
                "SELECT raw_json, created_at FROM summary_cache WHERE fingerprint = ?",
                (fp,)).fetchone()
        finally:
            if owns:
                c.close()
        if not row:
            return None
        age_days = _age_days(row["created_at"])
        if age_days is not None and age_days > MAX_AGE_DAYS:
            return None
        return json.loads(row["raw_json"])
    except Exception:
        return None


def put(fp: str, raw: dict, tier: str, conn=None):
    """Best-effort write of a SUCCESSFUL raw result. Never raises - a failure
    here must never be the reason analysis fails (same convention
    ai_providers.py's health cache already uses). `conn`: see get()."""
    try:
        c, owns = _with_conn(conn)
        try:
            _ensure_table(c)
            c.execute(
                "INSERT OR REPLACE INTO summary_cache (fingerprint, raw_json, model_tier, created_at, schema_version) "
                "VALUES (?, ?, ?, ?, ?)",
                (fp, json.dumps(raw, ensure_ascii=False), tier,
                 datetime.now(timezone.utc).isoformat(), SCHEMA_VERSION))
            c.commit()
        finally:
            if owns:
                c.close()
    except Exception:
        pass


def _ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS summary_cache (
            fingerprint    TEXT PRIMARY KEY,
            raw_json       TEXT NOT NULL,
            model_tier     TEXT NOT NULL,
            created_at     TEXT NOT NULL,
            schema_version INTEGER NOT NULL
        )
    """)


def _age_days(created_at_iso):
    try:
        created = datetime.fromisoformat(created_at_iso)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - created).total_seconds() / 86400.0
    except Exception:
        return None


def prune(max_age_days: int = MAX_AGE_DAYS, conn=None):
    """Best-effort deletion of entries older than max_age_days. Not called
    automatically anywhere yet - a narrow, opt-in maintenance helper, same
    pattern as prune_cache.py already uses for the embeddings cache. `conn`:
    see get()."""
    try:
        c, owns = _with_conn(conn)
        try:
            _ensure_table(c)
            rows = c.execute("SELECT fingerprint, created_at FROM summary_cache").fetchall()
            stale = [r["fingerprint"] for r in rows if (_age_days(r["created_at"]) or 0) > max_age_days]
            for i in range(0, len(stale), 400):
                chunk = stale[i:i + 400]
                ph = ",".join("?" for _ in chunk)
                c.execute(f"DELETE FROM summary_cache WHERE fingerprint IN ({ph})", chunk)
            c.commit()
        finally:
            if owns:
                c.close()
        return len(stale)
    except Exception:
        return 0
