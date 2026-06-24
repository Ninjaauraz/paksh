"""
live.py - keep Paksh fresh, hands-off. One long-running process: every CYCLE
minutes it runs the full pipeline (ingest + GDELT + cluster + summarize +
export), ripens a few extractive events via backfill, and - if you ask it to -
commits and pushes so Vercel redeploys. Leave it running in a terminal window;
press Ctrl-C to stop.

    set PAKSH_LLM_BACKEND=gemini
    py live.py                 # refresh every 20 min (no auto-deploy)
    py live.py --deploy        # also git commit+push each cycle (Vercel redeploys)
    py live.py --every 15      # change cadence (minutes)
    py live.py --backfill 10   # upgrade up to N extractive events each cycle
    py live.py --once          # run a single cycle and exit (good for testing)

The Gemini key must live in your environment (or a .gitignored .env) - NEVER in
this file or the repo. live.py only inherits whatever PAKSH_LLM_BACKEND /
GEMINI_API_KEY you've set, so child runs use the same backend.
"""

import datetime
import glob
import os
import shutil
import subprocess
import sys
import time

PY = sys.executable
CYCLE_MIN = 20
BACKFILL_N = 10


def _run(args):
    print(f"  $ {os.path.basename(PY)} {' '.join(args)}")
    return subprocess.run([PY, *args]).returncode


def _git_exe():
    """Find git: PATH first, then the copy GitHub Desktop bundles."""
    g = shutil.which("git")
    if g:
        return g
    pat = os.path.expandvars(
        r"%LOCALAPPDATA%\GitHubDesktop\app-*\resources\app\git\cmd\git.exe")
    hits = glob.glob(pat)
    return hits[0] if hits else None


def _deploy():
    git = _git_exe()
    if not git:
        print("  ! git not found (PATH or GitHub Desktop). Skipping push; "
              "deploy manually via GitHub Desktop.")
        return
    msg = "live refresh " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    subprocess.run([git, "add", "-A"])
    subprocess.run([git, "commit", "-m", msg])          # no-op if nothing changed
    rc = subprocess.run([git, "push"]).returncode
    print("  push ok" if rc == 0 else
          "  ! push failed - check GitHub Desktop sign-in / remote")


def cycle(deploy, backfill_n):
    stamp = datetime.datetime.now().strftime("%H:%M:%S")
    backend = os.environ.get("PAKSH_LLM_BACKEND", "ollama")
    print(f"\n=== cycle @ {stamp}  backend={backend} ===")
    if _run(["refresh.py", "--gdelt"]) != 0:
        print("  refresh failed this cycle; will retry next cycle.")
        return
    if backfill_n > 0:
        _run(["backfill.py", "--cap", str(backfill_n)])
        _run(["export_static.py"])      # publish the backfilled upgrades
    if deploy:
        _deploy()


def main():
    args = sys.argv[1:]
    deploy = "--deploy" in args
    once = "--once" in args
    every, backfill_n = CYCLE_MIN, BACKFILL_N
    if "--every" in args:
        every = int(args[args.index("--every") + 1])
    if "--backfill" in args:
        backfill_n = int(args[args.index("--backfill") + 1])

    backend = os.environ.get("PAKSH_LLM_BACKEND", "ollama")
    print(f"Paksh live: every {every} min | backfill {backfill_n}/cycle | "
          f"deploy={deploy} | backend={backend}")
    if backend == "ollama":
        print("NOTE: backend is OLLAMA (slow, ~80 min/cycle). For a live cadence "
              "set PAKSH_LLM_BACKEND=gemini before running this.")
    if deploy and not _git_exe():
        print("NOTE: --deploy set but git not found; pushes will be skipped.")
    print("Ctrl-C to stop.\n")

    try:
        while True:
            cycle(deploy, backfill_n)
            if once:
                break
            print(f"  sleeping {every} min ...")
            time.sleep(every * 60)
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()