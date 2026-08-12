"""
live.py - keep Paksh fresh, hands-off. One long-running process: every CYCLE
minutes it runs the full pipeline (ingest + GDELT + cluster + summarize +
export), ripens a few extractive events via backfill, and - if you ask it to -
commits and pushes so Vercel redeploys. Leave it running in a terminal window;
press Ctrl-C to stop.

    set PAKSH_LLM_BACKEND=gemini
    py live.py                 # refresh every 1 min (no auto-deploy)
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
CYCLE_MIN = 1
BACKFILL_N = 50


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


def _clear_stale_lock():
    """A crashed git op - or GitHub Desktop stuck 'refreshing' - can leave
    .git/index.lock behind, which silently blocks every commit (this has hung the
    repo before). live.py is the PRIMARY deployer here (GitHub Desktop is the manual
    backup), so clear a leftover lock before committing."""
    lock = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".git", "index.lock")
    if os.path.exists(lock):
        try:
            os.remove(lock)
            print("  (cleared stale .git/index.lock)")
        except OSError as e:
            print(f"  ! could not remove .git/index.lock ({e}); close GitHub Desktop and retry")


def _deploy():
    """Commit and push the BUILT SITE so Vercel redeploys.

    Stages and commits ONLY _site/ - never source (app.jsx, *.py), CLAUDE.md, or
    hand edits. So a content cycle can NEVER accidentally ship a code/structural
    change: deliberate code changes go out on purpose via GitHub Desktop (or a
    manual `git add` + commit). This mirrors safe_autopush.py's guarantee.
    This is the primary CONTENT deploy path; GitHub Desktop is the manual backup."""
    git = _git_exe()
    if not git:
        print("  ! git not found (PATH or GitHub Desktop). Skipping push; "
              "deploy manually via GitHub Desktop.")
        return
    _clear_stale_lock()
    msg = "live refresh " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    # Stage only the built site. The '-- _site' pathspec on BOTH add and commit
    # means that even if a source file was already staged by hand, it cannot ride
    # along in this automated commit - only _site/ is ever committed here.
    subprocess.run([git, "add", "--", "_site"])
    commit = subprocess.run([git, "commit", "-m", msg, "--", "_site"], capture_output=True, text=True)
    if "nothing to commit" in (commit.stdout or "") + (commit.stderr or ""):
        print("  nothing new to deploy this cycle.")
        return
    # fold in anything pushed elsewhere (e.g. a manual GitHub Desktop push) so our
    # push isn't rejected as non-fast-forward; --autostash keeps it safe.
    subprocess.run([git, "pull", "--rebase", "--autostash"])
    rc = subprocess.run([git, "push"]).returncode
    print("  deployed -> GitHub (Vercel will redeploy)" if rc == 0 else
          "  ! push failed - check GitHub Desktop sign-in / network")


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

    # Use the fast backends by DEFAULT even when this terminal didn't inherit the
    # setx'd env vars - setx never reaches already-open terminals or apps that cache
    # their environment (VS Code, GitHub Desktop), which is the #1 reason a plain
    # `py live.py` shows backend=ollama. Children (refresh -> cluster/analyze) inherit
    # these via the environment. An explicitly-set env var still overrides (setdefault).
    os.environ.setdefault("PAKSH_LLM_BACKEND", "pool")      # Groq/Gemini summary pool
    os.environ.setdefault("PAKSH_BACKEND", "cloudflare")    # Cloudflare bge-m3 embeddings
    os.environ.setdefault("PYTHONUTF8", "1")                # UTF-8 for child processes

    backend = os.environ.get("PAKSH_LLM_BACKEND", "ollama")
    emb = os.environ.get("PAKSH_BACKEND", "ollama")
    print(f"Paksh live: every {every} min | backfill {backfill_n}/cycle | "
          f"deploy={deploy} | summaries={backend} | embeddings={emb}")
    if backend == "ollama":
        print("NOTE: summary backend is OLLAMA (slow, ~80 min/cycle). "
              "Set PAKSH_LLM_BACKEND=pool (Groq/Gemini) for a fast cadence.")
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