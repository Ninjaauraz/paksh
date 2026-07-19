"""
safe_autopush.py - guarded auto-deploy of the GENERATED site only.

Invoked by the scheduled tasks AFTER a successful export_static.py. It commits and
pushes ONLY _site/ (the generated output Vercel serves), with hard safety guards so
an automated run can never publish a half-built site, sweep in source or hand-edited
files, or push a giant database/backup. Every run is logged.

Usage:
    py safe_autopush.py <label> [--dry-run]
      <label>    -> commit message "auto: <label> content update <date>"
      --dry-run  -> run every guard and report what WOULD be pushed, then unstage.
                    Makes no commit and no push.

Guards (map to the six requirements):
  1. Only runs on a successful export - the .bat chains it with `&&`, and this also
     refuses if _site/ is missing.
  2. Stages ONLY _site/. Never `git add -A`; never source, CLAUDE.md, or hand edits.
  3. Hard-refuses if ANY staged path matches *.db* / *.bak* or exceeds 50 MB - even
     if gitignore would have caught it (belt and braces).
  4. Refuses if the index already had staged changes this script did not create.
  5. Logs every run (ok/skip/abort/fail) with a timestamp, file count, and commit
     hash to autopush_log.txt in the project folder.
  6. Commit message: "auto: <label> content update <YYYY-MM-DD HH:MM>".
Never force-pushes; a rejected push (remote moved) aborts and leaves the commit local
for manual handling.
"""
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
SITE = ROOT / "_site"
LOG = ROOT / "autopush_log.txt"
MAX_BYTES = 50 * 1024 * 1024


def _git(*args, check=True):
    r = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def _log(line):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"[{stamp}] {line}\n")
    except OSError:
        pass
    print(f"[{stamp}] autopush: {line}")


def _unstage():
    """Undo only our own staging (safe: we only reach here after guard 4 confirmed
    the index started empty)."""
    try:
        _git("reset", "-q", check=False)
    except Exception:
        pass


def main():
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry = "--dry-run" in sys.argv
    label = args[0] if args else "content"

    # Guard 1: export must have produced a site
    if not SITE.is_dir():
        _log("ABORT - _site/ missing; export did not produce output. Not pushing.")
        sys.exit(1)

    # Guard 4: nothing may be pre-staged that we didn't add (don't touch the user's index)
    pre = _git("diff", "--cached", "--name-only")
    if pre:
        _log(f"ABORT - index already has staged changes (not ours): "
             f"{pre.splitlines()[:5]}. Refusing to commit someone else's work.")
        sys.exit(1)

    # Guard 2: stage ONLY _site/
    _git("add", "-A", "--", "_site")
    staged = [p for p in _git("diff", "--cached", "--name-only").splitlines() if p]

    if not staged:
        _log("skip - no _site changes to publish")
        sys.exit(0)

    # Guard 2 (double-check): every staged path is under _site/
    outside = [p for p in staged if not p.startswith("_site/")]
    if outside:
        _unstage()
        _log(f"ABORT - staged paths outside _site/: {outside[:5]}. Refusing.")
        sys.exit(1)

    # Guard 3: name + size safety, regardless of gitignore
    for p in staged:
        low = p.lower()
        if ".db" in low or ".bak" in low:
            _unstage()
            _log(f"ABORT - staged path looks like a db/backup: {p}. Refusing.")
            sys.exit(1)
        fp = ROOT / p
        try:
            if fp.is_file() and fp.stat().st_size > MAX_BYTES:
                _unstage()
                _log(f"ABORT - staged file over 50MB: {p} ({fp.stat().st_size} bytes). Refusing.")
                sys.exit(1)
        except OSError:
            pass

    if dry:
        _unstage()
        _log(f"dry-run - would publish {len(staged)} _site file(s) "
             f"(e.g. {staged[:3]}); no commit, no push")
        sys.exit(0)

    # Guard 6: clear automated commit message
    date = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = f"auto: {label} content update {date}"
    _git("commit", "-m", msg)
    commit = _git("rev-parse", "--short", "HEAD")

    # push - NEVER force. A rejected push (remote moved) aborts for manual handling.
    r = subprocess.run(["git", "push"], cwd=str(ROOT), capture_output=True, text=True)
    if r.returncode != 0:
        _log(f"PUSH FAILED - commit {commit} is LOCAL ONLY (not deployed): "
             f"{r.stderr.strip()[:200]}")
        sys.exit(2)

    _log(f"OK - pushed {len(staged)} _site file(s) as {commit}  |  {msg}")
    sys.exit(0)


if __name__ == "__main__":
    main()
