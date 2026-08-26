"""
test_phase5.py - Phase 5 targeted regression tests.

Covers exactly the behaviors Phase 4/5 introduced that no existing test file
protects: lazy startup cost, the malformed-JSON fail-safe path, backend
selection in both modes, and the /health endpoint. Does NOT re-test anything
test_phase22.py/test_phase27.py/test_phase43.py already cover.

Run:  py test_phase5.py
"""
import json
import subprocess
import sys
from unittest import mock

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


# ============================================================ A: lazy startup
print("=== A: lazy startup - expensive modules absent from a fresh `import main` ===")
proc = subprocess.run(
    [sys.executable, "-X", "importtime", "-c", "import main"],
    capture_output=True, text=True, cwd=".",
)
trace = proc.stderr
check("subprocess exited cleanly", proc.returncode == 0)
for mod in ("verified_registry", "numpy", "storylines", "cluster"):
    # match the trailing "| <module>" column exactly, not a substring hit
    hit = any(line.rstrip().endswith(f"| {mod}") for line in trace.splitlines())
    check(f"A: {mod} does not appear in `import main`'s trace", not hit)


# ============================================================ B: malformed JSON fail-safe
print("\n=== B: malformed Supabase JSON -> retry -> SupabaseUnavailable -> SQLite fallback ===")
import supabase_content as sb
import main as main_module


def _bad_json_response():
    m = mock.MagicMock()
    m.status_code = 200
    m.json.side_effect = ValueError("not valid json")
    m.headers = {}
    return m


calls = {"n": 0}


def fake_get(url, headers=None, timeout=None):
    calls["n"] += 1
    return _bad_json_response()


with mock.patch.object(sb._session, "get", side_effect=fake_get), mock.patch("time.sleep"):
    try:
        sb._get("/topics?select=name", max_retries=2)
        raised = False
    except sb.SupabaseUnavailable:
        raised = True
check("B: malformed JSON eventually raises SupabaseUnavailable (not a raw ValueError)", raised)
check("B: retried the expected number of times (1 initial + 2 retries = 3)", calls["n"] == 3)

# End-to-end: main.py's route must still return real SQLite content, not a 500.
_orig_backend = main_module.CONTENT_BACKEND
_orig_get_topics = sb.get_topics
main_module.CONTENT_BACKEND = "supabase"
sb.get_topics = lambda: (_ for _ in ()).throw(sb.SupabaseUnavailable("malformed JSON (simulated)"))
try:
    result = main_module.list_topics()
    check("B: list_topics() falls back to real SQLite topics on malformed JSON",
          isinstance(result.get("topics"), list) and len(result["topics"]) > 0)
finally:
    sb.get_topics = _orig_get_topics
    main_module.CONTENT_BACKEND = _orig_backend
check("B: CONTENT_BACKEND restored after the fallback test", main_module.CONTENT_BACKEND == _orig_backend)


# ============================================================ C: backend selection, both modes
print("\n=== C: backend selection - both modes independently return real content ===")
_orig_backend = main_module.CONTENT_BACKEND

main_module.CONTENT_BACKEND = "sqlite"
sql_events = main_module.list_events()
check("C: SQLite mode /api/events returns real, non-empty content",
      len(sql_events.get("events", [])) > 0)

main_module.CONTENT_BACKEND = "supabase"
try:
    sb_events = main_module.list_events()
    check("C: Supabase mode /api/events returns real, non-empty content",
          len(sb_events.get("events", [])) > 0)
except Exception as e:
    print(f"  C: SKIPPED Supabase-mode check (unreachable from this environment: {e})")
main_module.CONTENT_BACKEND = _orig_backend
check("C: CONTENT_BACKEND restored after backend-selection test", main_module.CONTENT_BACKEND == _orig_backend)


# ============================================================ D: /health endpoint
print("\n=== D: /health - cheap, correct shape, never touches the full dataset ===")
check("D: /health route is registered", hasattr(main_module, "health"))

_orig_backend = main_module.CONTENT_BACKEND
main_module.CONTENT_BACKEND = "sqlite"
h_sql = main_module.health()
check("D: SQLite-mode /health reports status ok", h_sql.get("status") == "ok")
check("D: SQLite-mode /health reports the active backend", h_sql.get("content_backend") == "sqlite")
check("D: SQLite-mode /health does NOT report Supabase-only fields",
      "supabase_reachable" not in h_sql)

main_module.CONTENT_BACKEND = "supabase"
try:
    h_sb = main_module.health()
    check("D: Supabase-mode /health reports status ok", h_sb.get("status") == "ok")
    check("D: Supabase-mode /health reports supabase_reachable as a bool",
          isinstance(h_sb.get("supabase_reachable"), bool))
    check("D: Supabase-mode /health reports sqlite_fallback_available as a bool",
          isinstance(h_sb.get("sqlite_fallback_available"), bool))
except Exception as e:
    print(f"  D: SKIPPED Supabase-mode /health check (unreachable from this environment: {e})")
main_module.CONTENT_BACKEND = _orig_backend
check("D: CONTENT_BACKEND restored after /health test", main_module.CONTENT_BACKEND == _orig_backend)

# /health must not pull the full ~13k-event dataset - a real get_all_events()
# call would take measurably longer than a health probe should ever take.
import time
t0 = time.time()
main_module.CONTENT_BACKEND = "sqlite"
main_module.health()
dt = time.time() - t0
main_module.CONTENT_BACKEND = _orig_backend
check(f"D: SQLite-mode /health returns fast ({dt:.3f}s), doesn't scan the full dataset", dt < 1.0)


print(f"\n{'='*60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
