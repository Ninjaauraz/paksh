"""
test_pool_generate_interface.py - guards against analyze.py and ai_providers.py
drifting apart (2026-10-14 incident: a stale ai_providers.py lacked the
max_billed_attempts parameter, so every pool_generate() call raised TypeError and
events fell back to extractive summaries).

No network, no database, does not import analyze.py (parsed with ast only).

Run:  py test_pool_generate_interface.py
"""
import ast
import inspect
from pathlib import Path

import ai_providers as ap

FAILURES = []


def check(label, cond):
    print(f"  {label} ... {'OK' if cond else 'FAIL'}")
    if not cond:
        FAILURES.append(label)


params = inspect.signature(ap.pool_generate).parameters
check("pool_generate accepts max_billed_attempts", "max_billed_attempts" in params)
check("max_billed_attempts defaults to None",
      params.get("max_billed_attempts") is not None
      and params["max_billed_attempts"].default is None)

# every keyword analyze.py passes to pool_generate must exist in the signature
tree = ast.parse((Path(__file__).parent / "analyze.py").read_text(encoding="utf-8"))
kwargs_used, calls = set(), 0
for node in ast.walk(tree):
    if isinstance(node, ast.Call):
        f = node.func
        name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)
        if name == "pool_generate":
            calls += 1
            kwargs_used |= {k.arg for k in node.keywords if k.arg}
check("analyze.py calls pool_generate at least once", calls > 0)
check(f"every kwarg analyze.py passes exists in signature ({sorted(kwargs_used)})",
      kwargs_used <= set(params))

by_name = {p["name"]: p for p in ap.PROVIDERS}
check("gemini is marked billed", by_name.get("gemini", {}).get("billed") is True)
check("groq is not billed", not by_name.get("groq", {}).get("billed"))
check("groq model is not the retired llama-3.3-70b-versatile",
      by_name.get("groq", {}).get("model") != "llama-3.3-70b-versatile")
check("no unconfigured template provider (sambanova) is enabled",
      "sambanova" not in by_name)

print("\nFAILURES:", FAILURES if FAILURES else "none")
raise SystemExit(1 if FAILURES else 0)
