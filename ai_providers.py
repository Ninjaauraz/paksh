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
import threading
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


def _chat_once(provider, prompt, as_json, timeout=120):
    """One OpenAI-compatible /chat/completions call. If the provider rejects
    JSON mode (HTTP 400), retry the same call once WITHOUT it (the caller's
    tolerant JSON parser still recovers the object)."""
    url = provider["base_url"].rstrip("/") + "/chat/completions"
    key = os.environ[_key_env(provider)]

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
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                obj = json.loads(r.read().decode("utf-8", "replace"))
            return obj["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if json_mode and e.code == 400:
                continue                     # provider dislikes JSON mode -> retry plain
            # surface status + short body so fallback logic can read the code
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
            raise RuntimeError(f"HTTP {e.code} {detail}") from e
    raise RuntimeError("no response")


_TRANSIENT = ("429", "500", "502", "503", "529",
              "RESOURCE_EXHAUSTED", "UNAVAILABLE", "rate limit", "timeout")


def pool_generate(prompt, as_json=False, retries_per_provider=1):
    """Round-robin across active providers; fall through to the next on failure.
    Returns the model's text. Raises RuntimeError if NO provider is configured
    (so analyze.py can fall back to an extractive summary), or ValueError if
    every provider failed."""
    provs = active_providers()
    if not provs:
        raise RuntimeError(
            "No AI providers configured. Add a key to ai_keys.env "
            "(e.g. GROQ_API_KEY=...) - see ai_keys.example.env, or run "
            "`py ai_providers.py` to check.")
    n = len(provs)
    start = _next_start()
    errors = []
    for off in range(n):
        p = provs[(start + off) % n]
        for _ in range(retries_per_provider + 1):
            try:
                return _chat_once(p, prompt, as_json)
            except Exception as e:
                errors.append(f"{p['name']}: {e}")
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
