"""
test_launch_path_hardening.py - offline regression tests for the 2026-10-14 launch-path review:
  * runlocked.acquire() is atomic (O_EXCL) and never steals an uncertain lock
  * live._deploy() never deletes .git/index.lock, never autostashes/pulls, bounds + checks every
    git call, and only reports remote_ok after an authoritative ls-remote read-back
  * live.cycle() does not deploy when export_static.py fails

No network, no real git, no database: every git call and subprocess is faked, locks live in a
temp directory.   Run:  py test_launch_path_hardening.py
"""
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import runlocked
import live

FAILURES = []


def check(label, cond):
    print(f"  {label} ... {'OK' if cond else 'FAIL'}")
    if not cond:
        FAILURES.append(label)


tmp = Path(tempfile.mkdtemp(prefix="paksh_hardening_"))
live.LOG_PATH = str(tmp / "live_log.txt")

# ------------------------------------------------------------------ runlocked
print("runlocked: atomic acquire / contention / stale / unreadable")
runlocked.LOCK = tmp / ".pipeline.lock"


def fresh():
    for p in tmp.glob(".pipeline.lock*"):
        p.unlink()


fresh()
N = 16
results = []
barrier = threading.Barrier(N)


def contender(i):
    barrier.wait()
    results.append(runlocked.acquire(f"c{i}"))


ts = [threading.Thread(target=contender, args=(i,)) for i in range(N)]
[t.start() for t in ts]
[t.join() for t in ts]
check("16 simultaneous acquirers on a free lock -> exactly one wins", sum(results) == 1)

fresh()
runlocked.LOCK.write_text("deadjob\n999999\n2026-01-01 00:00:00\n", encoding="utf-8")
orig_alive = runlocked._pid_alive
runlocked._pid_alive = lambda pid: pid == os.getpid()   # the stale holder (999999) is dead; this process is alive
results.clear(); barrier = threading.Barrier(N)
ts = [threading.Thread(target=contender, args=(i,)) for i in range(N)]
[t.start() for t in ts]
[t.join() for t in ts]
check("stale lock (dead pid) with 16 racers -> exactly one reclaims it", sum(results) == 1)
check("no reclaim guard left behind", not list(tmp.glob(".pipeline.lock.reclaim")))

fresh()
runlocked._pid_alive = lambda pid: True
runlocked.LOCK.write_text("livejob\n4242\n2026-01-01 00:00:00\n", encoding="utf-8")
check("live holder -> acquire refused", runlocked.acquire("x") is False)
check("live holder's lock file untouched", runlocked.LOCK.read_text(encoding="utf-8").startswith("livejob"))

fresh()
runlocked.LOCK.write_text("garbage-without-pid", encoding="utf-8")
runlocked._pid_alive = lambda pid: False
check("unreadable lock -> treated as HELD, not reclaimed", runlocked.acquire("x") is False)
check("unreadable lock file preserved", runlocked.LOCK.exists())

fresh()
runlocked._pid_alive = orig_alive
check("acquire on a clean slate", runlocked.acquire("mine") is True)
runlocked.release()
check("release removes our own lock", not runlocked.LOCK.exists())
runlocked.LOCK.write_text(f"other\n{os.getpid() + 1}\nt\n", encoding="utf-8")
runlocked.release()
check("release never removes someone else's lock", runlocked.LOCK.exists())

# ------------------------------------------------------------------ live._deploy
print("\nlive._deploy: git safety, bounded calls, remote read-back")
fake_repo = tmp / "repo"
(fake_repo / ".git").mkdir(parents=True)
live.__file__ = str(fake_repo / "live.py")      # _git_lock_present()/_git cwd resolve relative to this
live._git_exe = lambda: "git"


class FakeGit:
    """Programmable fake. responses: dict keyed by git subcommand -> (rc, out, err)."""
    def __init__(self, **resp):
        self.calls, self.resp = [], resp
        self.head = "a" * 40

    def __call__(self, git, args, timeout=0):
        self.calls.append((args[0], timeout, list(args)))
        sub = args[0]
        if sub == "rev-parse" and "--abbrev-ref" in args:
            return self.resp.get("branch", (0, "main\n", ""))
        if sub == "rev-parse":
            return self.resp.get("head", (0, self.head + "\n", ""))
        return self.resp.get(sub, (0, "", ""))


def run_deploy(**resp):
    g = FakeGit(**resp)
    live._git = g
    r = live._deploy()
    return r, g


lock = fake_repo / ".git" / "index.lock"
lock.write_text("x")
r, g = run_deploy()
check("index.lock present -> deploy refused", r["remote_ok"] is False and r["commit_ok"] is False)
check("index.lock present -> NO git command issued at all", g.calls == [])
check("index.lock NOT deleted", lock.exists())
lock.unlink()

r, g = run_deploy(commit=(0, "1 file changed", ""), fetch=(0, "", ""),
                  **{"rev-list": (0, "1\t0\n", "")}, push=(0, "", ""),
                  **{"ls-remote": (0, "a" * 40 + "\trefs/heads/main\n", "")})
subs = [c[0] for c in g.calls]
check("happy path -> remote_ok True", r["remote_ok"] is True and r["push_ok"] is True)
check("happy path: no pull / rebase / stash / autostash ever issued",
      not any(s in ("pull", "rebase", "stash") for s in subs) and not any("--autostash" in c[2] for c in g.calls))
check("every network git call carries an explicit timeout",
      all(t > 0 for s, t, a in g.calls if s in ("fetch", "push", "ls-remote")))
check("only _site is added/committed", ["add", "--", "_site"] in [c[2] for c in g.calls]
      and ["commit", "-m", g.calls[[c[0] for c in g.calls].index("commit")][2][2], "--", "_site"] in [c[2] for c in g.calls])

r, g = run_deploy(fetch=(-1, "", "timeout after 300s"))
check("fetch timeout -> stopped, no push attempted", r["remote_ok"] is False and "push" not in [c[0] for c in g.calls])

r, g = run_deploy(commit=(0, "ok", ""), **{"rev-list": (0, "1\t3\n", "")})
check("remote is ahead -> stopped, no push, no pull", r["remote_ok"] is False
      and "push" not in [c[0] for c in g.calls] and "pull" not in [c[0] for c in g.calls])

r, g = run_deploy(commit=(0, "ok", ""), **{"rev-list": (0, "1\t0\n", "")}, push=(1, "", "rejected"))
check("push rejected -> remote_ok False, push_ok False", r["remote_ok"] is False and r["push_ok"] is False)

r, g = run_deploy(commit=(0, "ok", ""), **{"rev-list": (0, "1\t0\n", "")}, push=(-1, "", "timeout after 300s"))
check("push timeout -> not deployed", r["remote_ok"] is False and r["push_ok"] is False)

r, g = run_deploy(commit=(0, "ok", ""), **{"rev-list": (0, "1\t0\n", "")}, push=(0, "", ""),
                  **{"ls-remote": (0, "b" * 40 + "\trefs/heads/main\n", "")})
check("push exit 0 but remote head differs -> push_ok True, remote_ok FALSE", r["push_ok"] is True and r["remote_ok"] is False)

r, g = run_deploy(commit=(0, "ok", ""), **{"rev-list": (0, "1\t0\n", "")}, push=(0, "", ""),
                  **{"ls-remote": (-1, "", "timeout")})
check("read-back failure -> not reported as deployed", r["remote_ok"] is False)

r, g = run_deploy(commit=(1, "nothing to commit, working tree clean", ""), **{"rev-list": (0, "0\t0\n", "")})
check("nothing new and in sync -> no push", "push" not in [c[0] for c in g.calls] and r["remote_ok"] is True)

r, g = run_deploy(commit=(1, "", "fatal: cannot lock ref"))
check("commit failure -> stopped, no fetch/push", r["remote_ok"] is False and "push" not in [c[0] for c in g.calls])

# ------------------------------------------------------------------ live.cycle
print("\nlive.cycle: export failure must not deploy; success must verify")
live._verify_production_db_identity = lambda: None
live.runlocked = type("RL", (), {"acquire": staticmethod(lambda l: True), "release": staticmethod(lambda: None)})
ran, deployed = [], []
live._run = lambda args: (ran.append(args[0]), 1 if args[0] == "export_static.py" else 0)[1]
live._deploy = lambda: deployed.append(1) or {"remote_ok": True, "detail": "x"}
live.cycle(deploy=True, backfill_n=5)
check("export_static.py failure -> _deploy not called", deployed == [])
live._run = lambda args: 0
deployed.clear()
live.cycle(deploy=True, backfill_n=5)
check("all stages ok -> _deploy called once", deployed == [1])

print("\nFAILURES:", FAILURES if FAILURES else "none")
raise SystemExit(1 if FAILURES else 0)
