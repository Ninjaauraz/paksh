"""
ai_providers.py - Paksh multi-provider LLM pool (OpenAI-compatible, zero-dep)
============================================================================
A ROUND-ROBIN + FALLBACK pool of free, fast chat APIs for the summary/framing
step. Spreading events across several providers multiplies free-tier throughput
and adds resilience: if one provider rate-limits (429) or errors (5xx), the next
one takes over automatically. Used when PAKSH_LLM_BACKEND="pool" (see analyze.py).

=====================================================================
  TWO PLACES YOU CONTROL - no need to ask anyone to add more APIs
=====================================================================

1) ADD A KEY  ->  edit  ai_keys.env  (create it by copying ai_keys.example.env)
   One line per key, e.g.:   GROQ_API_KEY=gsk_xxxxxxxx
   ai_keys.env is GITIGNORED - it is never committed or pushed. Real keys must
   live ONLY there (or in your real environment variables).

2) ADD A PROVIDER  ->  append a dict to PROVIDERS below (copy the TEMPLATE):
   name + OpenAI-compatible base_url + model id. NO KEY GOES IN THIS FILE - the
   key is read from an env var named <NAME>_API_KEY (groq -> GROQ_API_KEY), whose
   VALUE you put in ai_keys.env. A provider auto-activates once its key is present.

Check what's live:   py ai_providers.py            (lists active providers)
Send a test call:    py ai_providers.py --ping

SECURITY: keys NEVER live in committed code. ai_keys.env is loaded into the
process environment at import (dotenv-style), so at runtime the key lives in an
environment variable - matching Paksh's "keys in env vars only" rule.
"""

import json
import os
import re
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_KEYS_FILE = _HERE / "ai_keys.env"


def _load_keys_file():
    """dotenv-lite: copy KEY=VALUE lines from ai_keys.env into os.environ.
    Real environment variables always win (we never overwrite them)."""
    try:
        text = _KEYS_FILE.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v


_load_keys_file()

# ---------------------------------------------------------------------------
# PROVIDER REGISTRY  -  add/edit rows here (see TEMPLATE at the bottom of list)
# ---------------------------------------------------------------------------
# base_url : an OpenAI-compatible endpoint ending in /v1 (or Google's /openai)
# model    : a chat model available on that provider (edit if a model is retired)
# enabled  : flip to False to park a provider without deleting it
#
# >>> THE KEY DOES NOT GO IN THIS FILE. <<<
# Each provider's key is read from an environment variable named  <NAME>_API_KEY
# (auto-derived from "name" - groq -> GROQ_API_KEY, cerebras -> CEREBRAS_API_KEY).
# Put the actual key value ONLY in ai_keys.env (gitignored), e.g.:
#     GROQ_API_KEY=gsk_xxxxxxxx
PROVIDERS = [
    {
        "name": "groq", "enabled": True,
        "base_url": "https://api.groq.com/openai/v1",
        # UPDATED 2026-09-04 (Phase 30C-B): "llama-3.3-70b-versatile" was retired -
        # HTTP 404 "model does not exist or is not accessible". Confirmed against
        # this account's live GET /v1/models (14 models total); of those, most are
        # unsuited to summarization (TTS, whisper transcription, guard/classifier
        # models, or Groq's tool-invoking "compound" agents). "openai/gpt-oss-120b"
        # is the largest general-purpose instruction model actually available, and
        # is already the SAME model id the (disabled) Cerebras entry below uses for
        # this identical workload - independent evidence this id is a real, already-
        # vetted fit for Paksh's summary/framing prompts, not an arbitrary pick.
        "model": "openai/gpt-oss-120b",
        "get_key": "https://console.groq.com/keys",   # key -> GROQ_API_KEY in ai_keys.env
        # Phase 30C-E: this account's free tier enforces a real TOKEN-PER-MINUTE
        # budget, not a request-count limit - a Phase 30C-D production-equivalent
        # run (77 events, 8 concurrent workers, no limiter) measured real 429
        # bodies reading "...on tokens per minute (TPM): Limit 8000, Used ~7100-
        # 7200...", and got exactly 1 success against 76 failures: every worker
        # converged on Groq within its first two attempts (round-robin start +
        # Gemini's near-instant non-transient 403), so the WHOLE 8000 TPM budget
        # was gone after the very first wave of concurrent calls, then stayed
        # exhausted for the rest of the run (a 60s sliding window). tpm_budget
        # is set well below the observed ceiling (imprecise char/4 token
        # estimate + other concurrent usage headroom); max_concurrent caps how
        # many workers can even be mid-request at once. Deliberately only on
        # THIS provider - see _RateLimiter/_LIMITERS below - Gemini and any
        # future provider get none of this unless they set it themselves.
        "tpm_budget": 6000, "max_concurrent": 2,
    },
    {
        # DISABLED 2026-08-08: this Cerebras account returns HTTP 402 "payment required"
        # for every model (gpt-oss-120b, zai-glm-4.7, gemma-4-31b) - no free-tier access.
        # Flip back to True after enabling billing / free access in the Cerebras dashboard.
        "name": "cerebras", "enabled": False,
        "base_url": "https://api.cerebras.ai/v1",
        "model": "gpt-oss-120b",   # this account's available models: gpt-oss-120b, zai-glm-4.7, gemma-4-31b
        "get_key": "https://cloud.cerebras.ai",        # key -> CEREBRAS_API_KEY in ai_keys.env
    },
    {
        "name": "gemini", "enabled": True,             # key -> GEMINI_API_KEY (env or ai_keys.env)
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.5-flash-lite",
        "get_key": "https://aistudio.google.com/apikey",
    },
    # ---- TEMPLATE: copy, set name/base_url/model, then add <NAME>_API_KEY to ai_keys.env
    # {
    #     "name": "sambanova", "enabled": True,        # key -> SAMBANOVA_API_KEY in ai_keys.env
    #     "base_url": "https://api.sambanova.ai/v1",
    #     "model": "Meta-Llama-3.3-70B-Instruct",
    #     "get_key": "https://cloud.sambanova.ai",
    # },
]


def _key_env(p):
    """Env-var NAME that holds this provider's key: <NAME>_API_KEY (e.g. groq ->
    GROQ_API_KEY). A provider may override with an explicit "key_env" only if its
    env var doesn't follow that pattern. The key VALUE lives in ai_keys.env."""
    return p.get("key_env") or (p["name"].upper().replace("-", "_") + "_API_KEY")


def active_providers():
    """Enabled providers that actually have a key present (order preserved)."""
    return [p for p in PROVIDERS if p.get("enabled") and os.environ.get(_key_env(p))]


# round-robin cursor so successive calls start at different providers -> load
# spreads across the pool instead of always hammering the first one.
_rr_lock = threading.Lock()
_rr_i = 0


def _next_start():
    global _rr_i
    with _rr_lock:
        i = _rr_i
        _rr_i += 1
        return i


# Groq and Cerebras sit behind Cloudflare, which blocks the default
# "Python-urllib/x.y" User-Agent with error 1010 ("browser signature banned").
# Send a normal browser UA so the API calls get through (same fix gdelt_source.py
# and cluster.py use). DO NOT REMOVE - without it Groq/Cerebras return HTTP 403 1010.
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


# ------------------------ Phase 30C-E: per-provider limiter ------------------------
# Opt-in: only a provider dict that sets "tpm_budget" and/or "max_concurrent" gets
# throttled (currently just groq - see PROVIDERS above). A provider with neither key
# is completely unaffected - no semaphore, no bookkeeping, no added latency.

_RETRY_AFTER_RE = re.compile(r"try again in\s*([\d.]+)\s*(ms|s)\b", re.IGNORECASE)


def _parse_retry_after(headers, body_text):
    """Seconds to wait before the next attempt, or None. Prefers the standard
    Retry-After response header (checked first - it's the authoritative signal
    when a provider sends one); falls back to Groq's own body-text hint
    ("...try again in 764ms.") when no header is present. Never raises."""
    try:
        ra = headers.get("Retry-After") if headers else None
        if ra:
            return float(ra)
    except (TypeError, ValueError):
        pass
    m = _RETRY_AFTER_RE.search(body_text or "")
    if m:
        val, unit = float(m.group(1)), m.group(2).lower()
        return val / 1000.0 if unit == "ms" else val
    return None


class _RateLimiter:
    """Thread-safe, provider-scoped concurrency + sliding-window token budget.
    Groq's free tier enforces a real TPM (tokens-per-minute) cap that the API
    never exposes before a call is made - so this throttles the CALLING side:
    a small semaphore bounds how many requests can be in flight at once (stops
    every worker from starting at the same instant), and a rolling 60s window
    of a cheap token ESTIMATE (~4 chars/token, the standard rough heuristic for
    English text - Groq doesn't return a pre-call token count either) keeps
    cumulative usage under a conservative budget. A thread that would exceed
    the budget waits (bounded) rather than firing a request that's very likely
    to 429; an actual 429's Retry-After/body hint sets a shared cooldown so
    every OTHER waiting thread benefits from the same observed signal, not
    just the one that got the error. Never sleeps at all when the provider is
    healthy and under budget."""

    MAX_WAIT_S = 20.0     # give up and let the caller fall through to the next
                           # provider rather than stalling one event indefinitely

    def __init__(self, max_concurrent, tpm_budget, window_s=60.0):
        self._sem = threading.Semaphore(max_concurrent)
        self._lock = threading.Lock()
        self._window_s = window_s
        self._tpm_budget = tpm_budget
        self._events = []              # [(monotonic_ts, est_tokens), ...]
        self._cooldown_until = 0.0     # monotonic time; set by an observed 429

    def _used(self, now):
        cutoff = now - self._window_s
        self._events = [(t, n) for t, n in self._events if t > cutoff]
        return sum(n for _, n in self._events)

    def acquire(self, est_tokens):
        """Blocks (bounded) until a request may proceed. Raises TimeoutError
        (caller treats this exactly like any other transient failure - falls
        through to the next provider) if MAX_WAIT_S is exceeded."""
        if not self._sem.acquire(timeout=self.MAX_WAIT_S):
            raise TimeoutError("limiter timeout: no concurrency slot became available")
        deadline = time.monotonic() + self.MAX_WAIT_S
        while True:
            with self._lock:
                now = time.monotonic()
                cooldown_left = self._cooldown_until - now
                if cooldown_left <= 0 and self._used(now) + est_tokens <= self._tpm_budget:
                    self._events.append((now, est_tokens))
                    return
            if now >= deadline:
                self._sem.release()
                raise TimeoutError("limiter timeout: TPM budget/cooldown did not clear in time")
            time.sleep(min(max(cooldown_left, 0.5), 2.0, deadline - now))

    def note_error(self, retry_after_s=None):
        with self._lock:
            if retry_after_s:
                self._cooldown_until = max(self._cooldown_until, time.monotonic() + retry_after_s)
        self._sem.release()

    def release(self):
        self._sem.release()

    # ---- Phase 30C-J: read-only peeks for ProviderCapacity's health/selection
    # logic. Neither method acquires the semaphore or mutates any state beyond
    # the routine window-pruning _used() already does on every call - pure
    # additions, acquire()/note_error()/release()'s own behavior is untouched. ----

    def in_cooldown(self):
        """True if a prior 429's Retry-After/body hint hasn't cleared yet -
        the SAME cooldown acquire() already blocks on, just inspectable
        without attempting a request."""
        with self._lock:
            return time.monotonic() < self._cooldown_until

    def headroom_estimate(self):
        """Remaining TPM budget in the current window, or None if this
        limiter has no token budget configured (i.e. -unbounded-). A rough
        number for SELECTION ranking only - never used to gate acquire()."""
        with self._lock:
            now = time.monotonic()
            return max(0, self._tpm_budget - self._used(now))

    @property
    def tpm_budget(self):
        return self._tpm_budget


_LIMITERS = {}   # provider name -> _RateLimiter, built lazily from each provider's own config


def _limiter_for(provider):
    if "tpm_budget" not in provider and "max_concurrent" not in provider:
        return None
    name = provider["name"]
    if name not in _LIMITERS:
        _LIMITERS[name] = _RateLimiter(
            max_concurrent=provider.get("max_concurrent", 4),
            tpm_budget=provider.get("tpm_budget", 1_000_000))   # effectively unbounded if unset
    return _LIMITERS[name]


def _estimate_tokens(prompt):
    """~4 chars/token, the standard rough estimate for English text - good
    enough to keep a sliding-window budget honest without needing a real
    tokenizer dependency. + a fixed output allowance: Paksh's actual
    summary/framing JSON responses run to a few hundred tokens in practice
    (confirmed via Phase 30C-B/30C-D's real responses), NOT anywhere near the
    8192 max_tokens ceiling _chat_once() requests (that field is a cap, not a
    target - using it as the estimate would make the budget math wildly over-
    conservative and effectively serialize every call)."""
    return len(prompt) // 4 + 700


# ------------------------ Phase 30C-J: provider health/capacity ------------------------
# Additive generalization of the Phase 30C-E limiter above - _RateLimiter is NOT
# replaced. ProviderCapacity composes it (or None, for a provider with no limiter
# configured) and adds a small, deterministic health-state machine on top, so
# provider SELECTION can become capacity/health-aware instead of blind round-robin,
# while _chat_once()'s actual request/limiter mechanics stay byte-for-byte the
# behavior Phase 30C-E already validated in real production traffic.

HEALTHY, DEGRADED, RATE_LIMITED, UNAVAILABLE, DISABLED = (
    "HEALTHY", "DEGRADED", "RATE_LIMITED", "UNAVAILABLE", "DISABLED")

# Small, deterministic, documented thresholds - NOT a statistical model. A single
# transient hiccup (one 5xx/timeout) must never poison a provider (Section 8 of the
# 30C-J brief), so DEGRADED needs a short RUN of them; UNAVAILABLE needs even fewer
# CONSECUTIVE non-transient (401/403/404-shaped) failures, because that pattern -
# proven directly by Gemini's real 403 dunning denial across this whole session -
# does not recover on retry within a run, so waiting longer only wastes more calls.
_DEGRADE_THRESHOLD = 3        # consecutive transient (5xx/timeout/connection) failures
_UNAVAILABLE_THRESHOLD = 2    # consecutive non-transient (401/403/404/other) failures

# 429 is deliberately NOT counted by either streak above - it is handled entirely by
# _RateLimiter's own cooldown (in_cooldown()/note_error()), which is the ALREADY-
# VALIDATED single source of truth for rate-limit state. This file must not grow a
# second, independent cooldown mechanism (explicit 30C-J requirement).
_RATE_LIMIT_MARKER = "429"
_TRANSIENT_DEGRADE_MARKERS = ("500", "502", "503", "529", "RESOURCE_EXHAUSTED",
                              "UNAVAILABLE", "timeout", "connection")
# Deliberately NOT a hardcoded 401/403/404 allowlist: ANY failure that is neither
# the rate-limit marker above nor one of the recognized transient-infra markers is
# treated as a candidate permanent failure. This is intentionally the same "else"
# bucket _TRANSIENT already implies by omission elsewhere in this file - see
# pool_generate() below, which is completely UNCHANGED in its own transient/retry
# semantics; this is a second, independent read of the same error string for a
# different purpose (health, not retry-vs-move-on).


class ProviderCapacity:
    """Per-provider health + (composed, unmodified) rate limiter. One instance
    per provider name, created lazily by _capacity_for() and reused for the
    life of the process - this is in-process, per-run state; only the small
    persisted summary in _load_health_cache()/_save_health_cache() survives
    across runs (Section 16-19 of the 30C-J brief).

    Deliberately NOT a generic telemetry framework: exactly the counters
    needed for the eligibility/selection decisions below, nothing else."""

    def __init__(self, provider):
        self.provider = provider
        self.limiter = _limiter_for(provider)          # None for an unlimited provider (e.g. Gemini today)
        self.transient_streak = 0
        self.permanent_streak = 0
        self.success_count = 0
        self.failure_count = 0

    def load_persisted(self, row):
        """Apply a prior run's cached summary as a STARTING point, never as
        truth (Section 17). A provider cached UNAVAILABLE gets exactly one
        trial's worth of slack this run (permanent_streak one short of the
        exclusion threshold) - eligible immediately, but re-excluded fast if
        the same permanent failure recurs; a single success resets it fully.
        DEGRADED is deliberately NOT carried forward - a transient infra blip
        in a PRIOR run predicts nothing about this one."""
        if not row:
            return
        if row.get("health") == UNAVAILABLE:
            self.permanent_streak = max(0, _UNAVAILABLE_THRESHOLD - 1)
        self.success_count = int(row.get("success", 0) or 0)
        self.failure_count = int(row.get("failure", 0) or 0)

    def current_health(self):
        """Computed fresh every call - never a stored/sticky field for the
        RATE_LIMITED case, so cooldown expiry (an _RateLimiter-owned fact)
        is reflected immediately with no separate transition logic."""
        if not self.provider.get("enabled"):
            return DISABLED
        if self.permanent_streak >= _UNAVAILABLE_THRESHOLD:
            return UNAVAILABLE
        if self.limiter and self.limiter.in_cooldown():
            return RATE_LIMITED
        if self.transient_streak >= _DEGRADE_THRESHOLD:
            return DEGRADED
        return HEALTHY

    def eligible_for_dispatch(self):
        """UNAVAILABLE/DISABLED are hard exclusions (the actual waste-
        elimination goal - Section 7). RATE_LIMITED is NOT excluded here: it
        stays a candidate so _RateLimiter's own bounded acquire()/cooldown
        logic (unchanged) still gets to decide, exactly as it does today -
        this function only decides ranking/exclusion, never re-implements
        the limiter's own wait behavior."""
        return self.current_health() not in (DISABLED, UNAVAILABLE)

    # Below this remaining-budget FRACTION, a limited provider is meaningfully
    # deprioritized (still eligible, just ranked after anything with real
    # room) - a bucket, not a continuous comparison. See selection_key()'s
    # docstring for why a continuous comparison is the wrong tool here.
    _LOW_HEADROOM_FRACTION = 0.2

    def selection_key(self):
        """Lower sorts first. HEALTHY beats DEGRADED beats RATE_LIMITED
        (Section 13: deterministic, explainable, no ML/weighted-random/
        statistical optimization). Within a health tier, meaningfully-low
        headroom is deprioritized.

        Deliberately BUCKETED (0 = has real room, 1 = running low), not a
        continuous fraction: an unlimited provider (no configured limiter,
        e.g. Gemini today) is always "has room" (bucket 0) - but so is any
        limited provider (e.g. Groq) that isn't yet close to its ceiling. A
        continuous comparison would make an unlimited provider's synthetic
        1.0 permanently beat a limited provider's real-but-still-healthy
        0.88-after-one-call, which would silently and permanently prefer the
        unlimited provider from the second call onward - caught directly by
        test_phase30ce_groq_rate_limit.py's check #21 (Groq stopped being
        tried at all after a single earlier success consumed a sliver of its
        budget). Bucketing means ordinary, healthy usage doesn't reshuffle
        provider preference - only genuine near-exhaustion does, and ties
        (the overwhelmingly common case) fall through to the round-robin
        tiebreak below, preserving the load-spreading this pool always had."""
        health = self.current_health()
        rank = {HEALTHY: 0, DEGRADED: 1, RATE_LIMITED: 2}.get(health, 9)
        if self.limiter and self.limiter.tpm_budget:
            fraction = self.limiter.headroom_estimate() / self.limiter.tpm_budget
        else:
            fraction = 1.0
        low_headroom = 1 if fraction < self._LOW_HEADROOM_FRACTION else 0
        return (rank, low_headroom)

    def record_success(self):
        self.success_count += 1
        was_unavailable_or_degraded = self.permanent_streak or self.transient_streak
        self.transient_streak = 0
        self.permanent_streak = 0
        if was_unavailable_or_degraded:
            _mark_dirty(self.provider["name"])

    def record_failure(self, err_str):
        self.failure_count += 1
        err_str = err_str or ""
        if _RATE_LIMIT_MARKER in err_str:
            return   # handled entirely by _RateLimiter's cooldown - no streak change
        if any(m in err_str for m in _TRANSIENT_DEGRADE_MARKERS):
            self.transient_streak += 1
            self.permanent_streak = 0
        else:
            self.permanent_streak += 1
            self.transient_streak = 0
        _mark_dirty(self.provider["name"])

    def as_cache_row(self):
        return {"health": self.current_health(),
                "success": self.success_count, "failure": self.failure_count,
                "transient_streak": self.transient_streak,
                "permanent_streak": self.permanent_streak}


_CAPACITIES = {}   # provider name -> ProviderCapacity, built lazily (mirrors _LIMITERS)
_dirty_providers = set()   # names needing a cache write - only real health TRANSITIONS
                            # mark dirty (see record_success/record_failure above), not
                            # every call, so persistence stays infrequent and cheap.


def _capacity_for(provider):
    name = provider["name"]
    if name not in _CAPACITIES:
        cap = ProviderCapacity(provider)
        cap.load_persisted(_HEALTH_CACHE.get(name))
        _CAPACITIES[name] = cap
    return _CAPACITIES[name]


def _mark_dirty(name):
    _dirty_providers.add(name)
    _save_health_cache()   # best-effort, atomic, cheap (Section 19) - see below


_HEALTH_CACHE_FILE = _HERE / ".provider_health.json"


def _load_health_cache():
    """Best-effort load. Any problem at all (missing file, malformed JSON,
    wrong type, permission error) -> start fresh. The cache is advisory
    (Section 17) - it must never be able to crash or block the pipeline."""
    try:
        raw = json.loads(_HEALTH_CACHE_FILE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


_HEALTH_CACHE = _load_health_cache()


def _save_health_cache():
    """Atomic write (temp file + os.replace) so a mid-write crash can never
    leave a half-written cache. Best-effort: any failure here is swallowed -
    this must never be the reason a pipeline run fails (Section 19)."""
    try:
        rows = {name: cap.as_cache_row() for name, cap in _CAPACITIES.items()
                if name in _dirty_providers or name in _HEALTH_CACHE}
        # keep any provider not touched this process (e.g. disabled/no key) as-is
        merged = dict(_HEALTH_CACHE)
        merged.update(rows)
        # Section 18: bounded by construction - exactly one row per KNOWN provider
        # name, never a growing log. Drop rows for providers no longer configured
        # at all (Section 17's "provider removed from configuration").
        known = {p["name"] for p in PROVIDERS}
        merged = {k: v for k, v in merged.items() if k in known}
        tmp = _HEALTH_CACHE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(merged, indent=1), encoding="utf-8")
        os.replace(tmp, _HEALTH_CACHE_FILE)
    except Exception:
        pass   # best-effort - never let cache persistence break the pipeline


def _pick_providers_in_order(active):
    """Capacity/health-aware replacement for blind round-robin (Section 12).
    UNAVAILABLE/DISABLED providers are excluded entirely (the actual waste-
    elimination goal). Everything else is included, HEALTHY-first, with the
    existing round-robin cursor kept ONLY as a tiebreaker among equally-
    ranked candidates (e.g. two simultaneously-healthy, unlimited providers
    still spread load the way they always have - nothing regresses for a
    provider with no capacity configuration, matching Gemini today).
    Rolling, per-call, recomputed fresh every event - never a precomputed
    allocation (Section 14)."""
    caps = [_capacity_for(p) for p in active]
    eligible = [c for c in caps if c.eligible_for_dispatch()]
    if not eligible:
        return []
    start = _next_start()
    n = len(eligible)
    rotated = [eligible[(start + i) % n] for i in range(n)]
    rotated.sort(key=lambda c: c.selection_key())   # stable: ties keep round-robin order
    return [c.provider for c in rotated]


def _chat_once(provider, prompt, as_json, timeout=120):
    """One OpenAI-compatible /chat/completions call. If the provider rejects
    JSON mode (HTTP 400), retry the same call once WITHOUT it (the caller's
    tolerant JSON parser still recovers the object).

    Phase 30C-E: if this provider configured a limiter (see _limiter_for()
    above - currently groq only), each real HTTP attempt below acquires it
    first (blocks briefly, bounded, only if the provider is actually near its
    budget) and always releases it afterwards - on success normally, on a 429/
    5xx via note_error() so an observed Retry-After/body hint becomes a shared
    cooldown for every other thread waiting on the same provider. A provider
    with no limiter configured (Gemini, Cerebras) takes this same code path
    with zero added behavior - _limiter_for() returns None immediately."""
    url = provider["base_url"].rstrip("/") + "/chat/completions"
    key = os.environ[_key_env(provider)]
    limiter = _limiter_for(provider)

    for json_mode in ([True, False] if as_json else [False]):
        body = {
            "model": provider["model"],
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 8192,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        req = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": "Bearer " + key,
                     "Content-Type": "application/json",
                     "Accept": "application/json",
                     "User-Agent": _UA})
        if limiter:
            limiter.acquire(_estimate_tokens(prompt))   # may raise TimeoutError - treated as transient by the caller
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                obj = json.loads(r.read().decode("utf-8", "replace"))
            if limiter:
                limiter.release()
            return obj["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:500]
            except Exception:
                pass
            if limiter:
                retry_after = _parse_retry_after(e.headers, detail) if e.code == 429 else None
                limiter.note_error(retry_after)
            if json_mode and e.code == 400:
                continue                     # provider dislikes JSON mode -> retry plain
            # surface status + short body so fallback logic can read the code
            raise RuntimeError(f"HTTP {e.code} {detail[:200]}") from e
        except Exception:
            if limiter:
                limiter.release()
            raise
    raise RuntimeError("no response")


_TRANSIENT = ("429", "500", "502", "503", "529",
              "RESOURCE_EXHAUSTED", "UNAVAILABLE", "rate limit", "timeout")


def pool_generate(prompt, as_json=False, retries_per_provider=1):
    """Capacity/health-aware dispatch across active providers (Phase 30C-J);
    falls through to the next on failure. Returns the model's text. Raises
    RuntimeError if NO provider is configured at all (so analyze.py can fall
    back to an extractive summary) - UNCHANGED interface/exception type from
    before this phase. Raises ValueError if every eligible provider failed OR
    if none is currently eligible (all UNAVAILABLE/DISABLED) - also the SAME
    exception type as before, so analyze.py's existing except-and-fall-back-
    to-extractive call site needs no change at all.

    The only real change from the pre-30C-J version: the provider ORDER now
    comes from _pick_providers_in_order() (health/capacity-ranked, UNAVAILABLE/
    DISABLED excluded entirely) instead of blind round-robin, and each
    attempt's outcome is recorded into that provider's ProviderCapacity so
    later calls (this run and, via the bounded cache, future runs) see it."""
    provs = active_providers()
    if not provs:
        raise RuntimeError(
            "No AI providers configured. Add a key to ai_keys.env "
            "(e.g. GROQ_API_KEY=...) - see ai_keys.example.env, or run "
            "`py ai_providers.py` to check.")
    ordered = _pick_providers_in_order(provs)
    if not ordered:
        raise ValueError("all providers currently ineligible (unavailable/disabled) -> "
                          + ", ".join(f"{p['name']}={_capacity_for(p).current_health()}" for p in provs))
    errors = []
    for p in ordered:
        cap = _capacity_for(p)
        for _ in range(retries_per_provider + 1):
            try:
                result = _chat_once(p, prompt, as_json)
                cap.record_success()
                return result
            except Exception as e:
                errors.append(f"{p['name']}: {e}")
                cap.record_failure(str(e))
                if any(t in str(e) for t in _TRANSIENT):
                    break                    # move to next provider immediately
    raise ValueError("all providers failed -> " + " | ".join(errors[-4:]))


def status_lines():
    """Human-readable per-provider status for the CLI + analyze.py startup."""
    out = []
    for p in PROVIDERS:
        if not p.get("enabled"):
            state = "disabled"
        elif os.environ.get(_key_env(p)):
            state = "ACTIVE"
        else:
            state = f"no key ({_key_env(p)} unset)"
        out.append(f"  {p['name']:<10} {p['model']:<28} {state}")
    return out


if __name__ == "__main__":
    import sys
    print("Paksh AI provider pool")
    print("keys file:", _KEYS_FILE, "(exists)" if _KEYS_FILE.exists() else "(not created yet)")
    print("\nproviders:")
    print("\n".join(status_lines()))
    act = active_providers()
    print(f"\n{len(act)} active provider(s): {', '.join(p['name'] for p in act) or 'NONE'}")
    if not act:
        print("\nAdd a key: copy ai_keys.example.env to ai_keys.env and paste a key,")
        print("e.g.  GROQ_API_KEY=gsk_...   (get one at https://console.groq.com/keys)")
    elif "--ping" in sys.argv:
        print("\nping (say 'ok'):")
        for p in act:
            try:
                r = _chat_once(p, "Reply with the single word: ok", as_json=False, timeout=30)
                print(f"  {p['name']:<10} -> {r.strip()[:40]!r}")
            except Exception as e:
                print(f"  {p['name']:<10} -> FAILED: {e}")
