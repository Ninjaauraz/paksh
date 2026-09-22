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
import re
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

import paksh_paths
import runlocked

PY = sys.executable
CYCLE_MIN = 12
BACKFILL_N = 100

# Phase 21-fix (2026-09-23): live.py is Paksh's one production launcher (no scheduled
# task or shortcut starts it - it is always run by hand in a terminal, per this
# module's own docstring). Two incidents showed that letting every child process in
# the chain (refresh.py -> ingest/gdelt/cluster/analyze -> backfill -> export_static)
# independently re-derive the data directory from LOCALAPPDATA/data_dir.txt is
# fragile: LOCALAPPDATA can be absent (2026-09-22) or simply resolve to something
# that doesn't have data_dir.txt set up (2026-09-23) in whatever terminal happens to
# be running it, and neither is visible until the wrong (repo-local) database has
# already been used. So live.py now resolves the production data directory ONCE,
# explicitly, here - not via LOCALAPPDATA - and every child inherits it as a normal
# environment variable (subprocess.run() with no `env=` override already inherits
# the parent's os.environ, which is how PAKSH_LLM_BACKEND/PAKSH_BACKEND below already
# propagate). paksh_paths.require_ready() additionally requires a validated
# production marker inside this directory before trusting it - see paksh_paths.py.
PRODUCTION_DATA_DIR = r"D:\Paksh_Data"

# Phase 25B-D: live.py previously printed to stdout only - if the terminal was
# closed, or this ran headless with output not redirected, a crashed cycle at
# 3 AM left zero trace on disk. LOG_PATH matches the project's existing
# refresh_log.txt/reframe_log.txt/autopush_log.txt/backup_log.txt convention.
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "live_log.txt")
LOG_MAX_BYTES = 5 * 1024 * 1024   # bounded log: truncate rather than grow forever


def _stamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


_SECRET_RE = re.compile(r"(key|token|secret|password|apikey)[\"'=:\s]+[\w\-\.]{12,}", re.IGNORECASE)


def _redact(text: str) -> str:
    """Best-effort scrub before anything reaches the log file - a crash
    message that happens to embed a key/token (e.g. an HTTP client's error
    including the request URL) must never be written verbatim."""
    return _SECRET_RE.sub(lambda m: m.group(0).split(m.group(1))[0] + m.group(1) + "=<redacted>", text)


def _rotate_if_large():
    try:
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > LOG_MAX_BYTES:
            with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            keep = lines[-2000:]   # keep the most recent slice rather than the whole history
            with open(LOG_PATH, "w", encoding="utf-8") as f:
                f.writelines(keep)
    except OSError:
        pass   # logging must never be the reason a cycle fails


def _log(msg: str):
    """Prints (unchanged console behavior) AND appends to live_log.txt, so a
    crash or a closed terminal always leaves a durable, on-disk record."""
    print(msg)
    try:
        _rotate_if_large()
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{_stamp()}] {_redact(msg)}\n")
    except OSError:
        pass   # logging must never be the reason a cycle fails


def _run(args):
    _log(f"  $ {os.path.basename(PY)} {' '.join(args)}")
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
            _log("  (cleared stale .git/index.lock)")
        except OSError as e:
            _log(f"  ! could not remove .git/index.lock ({e}); close GitHub Desktop and retry")


def _deploy():
    """Commit and push the BUILT SITE so Vercel redeploys.

    Stages and commits ONLY _site/ - never source (app.jsx, *.py), CLAUDE.md, or
    hand edits. So a content cycle can NEVER accidentally ship a code/structural
    change: deliberate code changes go out on purpose via GitHub Desktop (or a
    manual `git add` + commit). This mirrors safe_autopush.py's guarantee.
    This is the primary CONTENT deploy path; GitHub Desktop is the manual backup."""
    git = _git_exe()
    if not git:
        _log("  ! git not found (PATH or GitHub Desktop). Skipping push; "
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
        _log("  nothing new to deploy this cycle.")
        return
    # fold in anything pushed elsewhere (e.g. a manual GitHub Desktop push) so our
    # push isn't rejected as non-fast-forward; --autostash keeps it safe.
    subprocess.run([git, "pull", "--rebase", "--autostash"])
    rc = subprocess.run([git, "push"]).returncode
    _log("  deployed -> GitHub (Vercel will redeploy)" if rc == 0 else
         "  ! push failed - check GitHub Desktop sign-in / network")


def _verify_production_db_identity():
    """Phase 21-fix round 2 (2026-09-23): the 79-minutes-old live.py process that
    caused the 457-event export guard trip proved that setting PAKSH_DATA_DIR once,
    at process startup, is not enough on its own - a long-running process's
    os.environ is fixed for its entire lifetime the moment main() finishes its
    one-time setup, so a process already running when this fix was DEPLOYED never
    picks it up, and every cycle it runs keeps inheriting the same stale (missing
    PAKSH_DATA_DIR) environment into refresh.py -> ingest/cluster/analyze ->
    export_static.py. That earlier chain still let the export-collapse guard catch
    it, but only after burning a full ~28-minute cycle first. This re-verifies, at
    the START of EVERY cycle (not just once at process launch), that this process's
    environment resolves to EXACTLY the known production database path - not just
    "some validated marker exists somewhere". Any mismatch is fatal: raises
    SystemExit (a BaseException, so the loop's `except Exception` below does NOT
    swallow it - this must stop the whole process, not just skip one cycle, since
    a stale environment will stay stale for every future cycle too)."""
    expected = Path(PRODUCTION_DATA_DIR) / "database" / paksh_paths.DB_NAME
    try:
        paksh_paths.require_ready(paksh_paths.db_path())
    except paksh_paths.DataDirError as e:
        _log(f"FATAL: production database identity check failed - {e}")
        sys.exit(1)
    actual = paksh_paths.db_path()
    if actual != expected:
        _log(f"FATAL: production database identity check failed - resolved DB_PATH "
             f"{actual} does not match the expected production path {expected}. "
             f"Refusing to ingest/cluster/analyze/export against an unverified "
             f"database. This process's environment may predate a path-resolution "
             f"fix (PAKSH_DATA_DIR={os.environ.get('PAKSH_DATA_DIR')!r}) - restart it.")
        sys.exit(1)


def cycle(deploy, backfill_n):
    stamp = datetime.datetime.now().strftime("%H:%M:%S")
    backend = os.environ.get("PAKSH_LLM_BACKEND", "ollama")
    started = time.monotonic()
    _log(f"\n=== cycle @ {stamp}  backend={backend} ===")
    _log("  cycle started")
    _verify_production_db_identity()

    # Phase 25B-A: share the SAME .pipeline.lock the scheduled Task Scheduler
    # jobs use (via runlocked.py) for the whole DB-writing span of this cycle
    # (refresh -> backfill -> export -> deploy), not just one subprocess call.
    # If a scheduled job (or another live.py) already holds it, defer - do
    # nothing this cycle rather than write paksh.db/_site/git concurrently.
    # The outer loop is untouched: we just return early and try again next
    # sleep interval, exactly like the existing "refresh failed" defer path.
    if not runlocked.acquire("live"):
        _log("  cycle skipped - another pipeline job holds the lock; will retry next cycle.")
        return
    try:
        if _run(["refresh.py", "--gdelt"]) != 0:
            _log(f"  cycle failed (stage: refresh.py --gdelt) after {time.monotonic()-started:.0f}s; "
                 f"will retry next cycle.")
            return
        if backfill_n > 0:
            _run(["backfill.py", "--cap", str(backfill_n)])
            _run(["export_static.py"])      # publish the backfilled upgrades
        if deploy:
            _deploy()
        _log(f"  cycle completed in {time.monotonic()-started:.0f}s")
    finally:
        runlocked.release()


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
    # Explicit, authoritative production data directory - see PRODUCTION_DATA_DIR
    # above. setdefault (not a plain assignment) so an operator who explicitly sets
    # PAKSH_DATA_DIR themselves before running live.py (e.g. to point at a
    # deliberately different location) is still respected.
    os.environ.setdefault("PAKSH_DATA_DIR", PRODUCTION_DATA_DIR)

    # Fail closed HERE, at startup, in the terminal someone is actually watching -
    # not silently, three subprocesses deep, the first time some child happens to
    # touch the database. _verify_production_db_identity() is ALSO called at the
    # top of every single cycle() (not just here, once) - a long-running process's
    # environment never changes after this point, so a fix deployed while this
    # process is already running would otherwise go undetected until this process
    # is restarted; re-checking every cycle at least makes that failure immediate
    # and cheap instead of a wasted ~28-minute cycle ending at the export guard.
    _verify_production_db_identity()
    _log(f"Paksh data directory: {paksh_paths.describe()}")

    backend = os.environ.get("PAKSH_LLM_BACKEND", "ollama")
    emb = os.environ.get("PAKSH_BACKEND", "ollama")
    _log(f"Paksh live: every {every} min | backfill {backfill_n}/cycle | "
         f"deploy={deploy} | summaries={backend} | embeddings={emb}")
    if backend == "ollama":
        _log("NOTE: summary backend is OLLAMA (slow, ~80 min/cycle). "
             "Set PAKSH_LLM_BACKEND=pool (Groq/Gemini) for a fast cadence.")
    if deploy and not _git_exe():
        _log("NOTE: --deploy set but git not found; pushes will be skipped.")
    _log("Ctrl-C to stop.\n")

    try:
        while True:
            # Phase 25B-D: an ordinary exception inside one cycle (a bug in a
            # child script, a transient environment problem, anything not
            # already caught inside cycle()/its subprocesses) must not kill
            # this whole always-on loop - the prior behavior was that only
            # KeyboardInterrupt was handled, so any other exception took the
            # entire process down with zero durable record of why. Log the
            # full traceback, then continue to the next scheduled cycle,
            # exactly like the existing "refresh failed this cycle; will
            # retry next cycle" pattern. KeyboardInterrupt/SystemExit are
            # BaseException, not Exception, so they still propagate to the
            # outer handler below untouched - Ctrl-C still stops the loop.
            try:
                cycle(deploy, backfill_n)
            except Exception:
                _log("  ! cycle raised an unhandled exception - logging and continuing "
                     "(the always-on loop does not stop for this):")
                _log(_redact(traceback.format_exc()))
            if once:
                break
            _log(f"  sleeping {every} min ...")
            time.sleep(every * 60)
    except KeyboardInterrupt:
        _log("\nstopped.")


if __name__ == "__main__":
    main()