#!/usr/bin/env python3
"""
refresh.py - rebuild Paksh end to end, in one command.

Runs, in order, stopping on the first failure:
    ingest.py  ->  cluster.py  ->  analyze.py  ->  export_static.py

It uses whatever backend your environment is set to. By default that is your
local Ollama (free). To run against the Gemini API instead (e.g. on a server),
set these before running:
    PAKSH_BACKEND=gemini  PAKSH_LLM_BACKEND=gemini  GEMINI_API_KEY=...

Usage (Windows):   py refresh.py
                   py refresh.py --no-export      (skip the static export)

Notes
-----
* paksh.db is never deleted - the embedding cache is preserved, so most runs
  only embed the handful of new articles and are fast.
* Nothing is published by this script. After it finishes, preview locally and
  then publish via GitHub Desktop (or your chosen automation).
"""

import os
import sys
import time
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent

STEPS = [
    ("Ingesting feeds",          "ingest.py"),
    ("Clustering (embeddings)",  "cluster.py"),
    ("Summaries + topics",       "analyze.py"),
    ("Exporting static site",    "export_static.py"),
]

# Optional steps: derive extra data (never publishes anything, never changes the site). If one fails or is slow the
# cycle carries on - they are never allowed to block ingest / analyse / export. Inserted right after "Summaries + topics".
OPTIONAL_AFTER_ANALYZE = [
    ("Story intelligence (optional)", "story_intelligence.py", "--cycle"),
]


def run(title: str, script: str) -> None:
    print(f"\n=== {title}  ({script}) ===", flush=True)
    started = time.time()
    result = subprocess.run([sys.executable, str(ROOT / script)], cwd=str(ROOT))
    elapsed = time.time() - started
    if result.returncode != 0:
        print(f"\n[X] {script} failed (exit {result.returncode}) after {elapsed:.0f}s. "
              f"Stopping so nothing half-built gets published.", flush=True)
        sys.exit(result.returncode)
    print(f"[OK] {script} done in {elapsed:.0f}s", flush=True)


def run_optional(title: str, script: str, *args: str) -> None:
    """Like run(), but a failure is reported and swallowed: the pipeline continues."""
    print(f"\n=== {title}  ({script}) ===", flush=True)
    started = time.time()
    try:
        result = subprocess.run([sys.executable, str(ROOT / script), *args], cwd=str(ROOT), timeout=600)
        note = "done" if result.returncode == 0 else f"FAILED (exit {result.returncode}) - continuing without it"
    except Exception as e:                                        # noqa: BLE001 - must never stop the cycle
        note = f"FAILED ({type(e).__name__}: {e}) - continuing without it"
    print(f"[optional] {script} {note} after {time.time() - started:.0f}s", flush=True)


def main() -> None:
    backend = os.environ.get("PAKSH_BACKEND", "ollama").lower()
    label = "local Ollama (free)" if backend == "ollama" else f"{backend} (API)"
    print("Paksh refresh -- backend:", label)
    if backend == "ollama":
        print("  (make sure Ollama is running: it must be reachable at "
              + os.environ.get("OLLAMA_URL", "http://localhost:11434") + ")")

    steps = list(STEPS)
    if "--gdelt" in sys.argv:                       # firehose: runs right after ingest
        steps.insert(1, ("Pulling GDELT firehose", "gdelt_source.py"))
    if "--no-export" in sys.argv:
        steps = [s for s in steps if s[1] != "export_static.py"]
    start = time.time()
    for title, script in steps:
        run(title, script)
        if script == "analyze.py":
            for t, s, *a in OPTIONAL_AFTER_ANALYZE:
                run_optional(t, s, *a)

    total = time.time() - start
    print(f"\n[DONE] Pipeline finished in {total:.0f}s. _site/ is rebuilt.")
    print("  Preview:  py -m http.server -d _site 8080   ->  http://localhost:8080")
    print("  Publish:  GitHub Desktop -> Commit to main -> Push origin (Vercel redeploys)")


if __name__ == "__main__":
    main()