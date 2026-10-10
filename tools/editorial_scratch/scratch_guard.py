"""scratch_guard.py - in-process audit-hook guard for the scratch export.

WHAT IT DOES
  Installs a CPython audit hook (sys.addaudithook) that watches, inside the Python process
  that runs the export, every file open/rename/remove/mkdir/rmtree/copy, sqlite3.connect,
  import, chdir and subprocess launch, and:
    * treats ANY path under a protected (production) root as a violation (read or write);
    * treats any write-class operation outside the scratch root as a violation;
    * allows subprocess launches only for an allowlist - programs named `node`/`node.exe`, and the
      exact vendored Tailwind CLI path(s) - with an effective working directory inside the scratch
      root, and never with a protected path anywhere in the command line or environment;
    * forbids os.system / exec* / startfile / fork outright;
    * RECORDS (does not block) outbound socket connections, so external image fetches are visible.
  On a violation it writes the reason to a pre-opened log descriptor and calls os._exit(97):
  no `except Exception` in the exporter can swallow it, and no later code runs.

SUBPROCESS EVENT SHAPES (verified by reading CPython 3.13's subprocess.py)
  The event is ("subprocess.Popen", executable, args, cwd, env).
    POSIX  : `executable` is the program (defaults to args[0]); `args` is a LIST.
    Windows: `args` has ALREADY been flattened into ONE command-line string by list2cmdline, and
             `executable` is whatever the caller passed - None for subprocess.run(["node", ...]).
  `evaluate` handles both: a string is split with the Microsoft C-runtime rules (the inverse of
  list2cmdline), and when `executable` is None the program is the first token. The protected-path
  scan runs over the WHOLE command-line text (not only tokens), so quoting cannot hide a path.
  This was derived from the CPython source and exercised on Linux with Windows-shaped synthetic
  events; it has NOT been observed on a real Windows run.

THREAD SAFETY
  Re-entrancy is tracked per thread (threading.local); counters and the violation list are
  updated under a lock. (An earlier version used one shared flag, which silently skipped events
  from other threads while one thread was inside the hook.)

THE COMMAND-LINE SCAN IS A TRIPWIRE, NOT A CONTAINMENT
  The text scan for a protected root catches a protected path SPELLED OUT in a command line or
  environment value (raw, canonical, 8.3, doubled-backslash source escaping, and any live `subst` /
  mapped-drive spelling, enumerated at launch time). It cannot stop a child that BUILDS a path
  (string concatenation, path.join with `..`, a path read from a file, an environment lookup), and
  node can do all of that; the audit hook cannot see a child's file operations. The scan therefore
  does NOT make an allowlisted `node` launch safe. Restricting what node may execute needs a
  separate, reviewed launcher-level control (pinned script and code digests); none exists yet.

WHAT IT DOES NOT DO (see docs/EDITORIAL_WINDOWS_SCRATCH_TEST.md)
  * It cannot see what a CHILD process does (node, tailwindcss.exe): only that it was launched,
    from where, with what command line. Child file activity needs OS-level monitoring (Process Monitor).
  * It only sees operations that raise audit events. Some do not (e.g. os.stat, native extension
    code, ctypes/WinAPI calls, file handles inherited or duplicated from elsewhere).
  * Paths are compared after realpath() (on Windows also: \\\\?\\ prefix stripping, local admin-share
    UNC aliases, and 8.3 names / `subst` / mapped drives / junctions resolved through the OS for
    paths that exist). A custom-named network share of a protected folder is NOT knowable here and
    is a residual risk; Process Monitor and the production manifests are the backstop.
  * A child process's own file operations are never seen. The command-line scan is a tripwire for
    spelled-out paths only (see "NODE AND THE COMMAND-LINE SCAN"); it cannot contain `node`.
  * Audit hooks cannot be removed once installed; install in the launcher process only.
  * It adds per-event cost (path canonicalisation, tens of microseconds per event on Linux; more on
    Windows), so wall-clock numbers measured under the guard are slightly inflated.
"""
from __future__ import annotations

import os
import re
import sys
import threading
import time
from collections import Counter

from scratch_common import drive_aliases, is_under, real, short_path

_WRITE_FLAGS = 0
for _n in ("O_WRONLY", "O_RDWR", "O_CREAT", "O_TRUNC", "O_APPEND"):
    _WRITE_FLAGS |= getattr(os, _n, 0)

EXIT_CODE_VIOLATION = 97

# events whose first argument is a path that is modified
_WRITE_PATH1 = {"os.mkdir", "os.remove", "os.rmdir", "os.truncate", "os.chmod", "os.chown",
                "os.utime", "os.mkfifo", "os.mknod", "shutil.rmtree", "os.setxattr", "os.removexattr"}
# events with (src, dst): both are modified/created
_WRITE_PATH2 = {"os.rename", "os.link", "os.symlink", "shutil.copyfile", "shutil.copymode",
                "shutil.copystat", "shutil.copytree", "shutil.move", "shutil.unpack_archive"}
# read-class events with a path first argument
_READ_PATH1 = {"os.listdir", "os.scandir", "os.chdir", "glob.glob", "os.walk"}
_FORBIDDEN = {"os.system", "os.exec", "os.spawn", "os.startfile", "os.fork", "os.forkpty"}


class Policy:
    def __init__(self, scratch_root, production_roots, allowed_exec_names=("node", "node.exe"),
                 allowed_exec_paths=(), mod=None, getcwd=None):
        """mod: None = the running platform (os.path + realpath); ntpath/posixpath = purely lexical
        comparison for that flavour (used by tests to exercise Windows rules on Linux).
        getcwd: override for tests; defaults to os.getcwd."""
        self.scratch_root = scratch_root
        self.production_roots = [r for r in production_roots if r]
        self.allowed_exec_names = tuple(n.lower() for n in allowed_exec_names)
        self.allowed_exec_paths = tuple(allowed_exec_paths)
        self.mod = mod
        self.getcwd = getcwd or os.getcwd


def _path(x):
    """str path from str/bytes/PathLike, else None (file descriptors and None are ignored)."""
    if isinstance(x, (str, bytes, os.PathLike)):
        try:
            p = os.fsdecode(x)
        except Exception:
            return None
        return p or None
    return None


def _in_production(p, policy):
    try:
        return any(is_under(p, r, mod=policy.mod) for r in policy.production_roots)
    except (OSError, ValueError):
        return True            # cannot canonicalise => treat as dangerous (fail closed)


def _under_scratch(p, policy):
    try:
        return is_under(p, policy.scratch_root, mod=policy.mod)
    except (OSError, ValueError):
        return False


def _sqlite_target(p):
    """Extract a filesystem path from a sqlite3.connect() target (handles :memory: and file: URIs)."""
    if p in (":memory:", ""):
        return None
    if p.lower().startswith("file:"):
        rest = p[5:].split("?", 1)[0]
        while rest.startswith("//") and not rest.startswith("///"):
            rest = rest[2:]
        if rest.startswith("///"):
            rest = rest[3:]
        if len(rest) > 2 and rest[0] == "/" and rest[2] == ":":      # /C:/x on Windows
            rest = rest[1:]
        return rest or None
    return p


# ---------------------------------------------------------------------------------------------
# command lines
# ---------------------------------------------------------------------------------------------

def split_windows_cmdline(s):
    """Split a Windows command line into argv using the Microsoft C-runtime rules (the inverse of
    subprocess.list2cmdline). The FIRST token follows the simpler program-name rule used by
    CreateProcess: if it starts with a quote it ends at the next quote (no backslash escapes)."""
    s = str(s)
    n = len(s)
    i = 0
    while i < n and s[i] in " \t":
        i += 1
    argv = []
    if i < n:
        if s[i] == '"':
            j = s.find('"', i + 1)
            j = n if j < 0 else j
            argv.append(s[i + 1:j])
            i = j + 1
        else:
            j = i
            while j < n and s[j] not in " \t":
                j += 1
            argv.append(s[i:j])
            i = j
    while i < n:
        while i < n and s[i] in " \t":
            i += 1
        if i >= n:
            break
        buf, in_q = [], False
        while i < n:
            c = s[i]
            if c == "\\":
                j = i
                while j < n and s[j] == "\\":
                    j += 1
                nb = j - i
                if j < n and s[j] == '"':
                    buf.append("\\" * (nb // 2))
                    if nb % 2:
                        buf.append('"')
                        i = j + 1
                    else:
                        i = j
                    continue
                buf.append("\\" * nb)
                i = j
                continue
            if c == '"':
                in_q = not in_q
                i += 1
                continue
            if c in " \t" and not in_q:
                break
            buf.append(c)
            i += 1
        argv.append("".join(buf))
    return argv


def _scan_forms(root, policy):
    """The spellings of a protected root to look for inside raw command-line text."""
    forms = set()
    raw = str(root).replace("/", "\\").lower().rstrip("\\")
    forms.add(raw)
    try:
        forms.add(real(root, policy.mod).replace("/", "\\").lower().rstrip("\\"))
    except (OSError, ValueError):
        pass
    forms.add(str(root).lower().rstrip("\\/"))
    if policy.mod is None and os.name == "nt":
        # Spellings the lexical forms above cannot produce: the 8.3 form of the root, and every
        # live `subst`/mapped-drive spelling of it (Z:\Paksh_Data when Z: maps C:\...\ or D:\).
        # Both are evaluated NOW (not cached), so a mapping created after start-up is seen at the
        # next launch. A mapping created AFTER a launch by a child process is not (see module doc).
        try:
            sp = short_path(root)
            if sp:
                forms.add(sp.replace("/", "\\").lower().rstrip("\\"))
            rr = real(root, None).rstrip("\\/")
            for letter, target in drive_aliases().items():
                tt = real(target, None).rstrip("\\/")
                if rr == tt or rr.startswith(tt + "\\"):
                    forms.add((letter + rr[len(tt):]).lower().rstrip("\\"))
        except (OSError, ValueError):
            pass
    return {f for f in forms if f}


_DOTDOT = re.compile(r"\\[^\\\s\"']+\\\.\.(?=[\\\s\"']|$)")
_DOT = re.compile(r"\\\.(?=\\)")


def _collapse_dots(low):
    """Resolve `\\x\\..` and `\\.\\` segments INSIDE arbitrary text, so a traversal such as
    "pre D:\\other\\..\\Paksh_Data\\x" cannot hide a protected root from a plain-text scan."""
    for _ in range(40):
        new = _DOT.sub("", _DOTDOT.sub("", low))
        if new == low:
            break
        low = new
    return low


def _text_mentions_protected(text, policy):
    """Does the raw text mention a protected root, whatever slash style, case, \\\\?\\ prefix or
    local admin-share spelling it uses? Boundaries are enforced so D:\\Paksh_Data2 is not D:\\Paksh_Data.

    The text is scanned in TWO forms: as written, and with every run of backslashes collapsed to
    one. The second form exists because source code escapes the separator ('C:\\\\Paksh_Data\\\\x'
    in a JavaScript or Python string literal is a doubled backslash on the command line), which a
    one-backslash root form would otherwise never match."""
    if not text:
        return None
    flat = text.replace("/", "\\")
    for variant, lead in ((flat, r"\\\\"), (re.sub(r"\\{2,}", r"\\", flat), r"\\+")):
        hit = _scan_one_form(variant, lead, policy)
        if hit:
            return hit
    return None


def _scan_one_form(flat, lead, policy):
    """`lead` is the regex for the leading backslashes of a UNC spelling (exactly two as written;
    one or more in the collapsed form)."""
    low = flat.lower()
    # strip extended-length / device prefixes wherever they appear, then rewrite local admin-share aliases
    low = low.replace("\\\\?\\unc\\", "\\\\").replace("\\\\?\\", "").replace("\\\\.\\", "")
    low = low.replace("\\?\\unc\\", "\\").replace("\\?\\", "")        # the collapsed spelling of the same prefixes
    low = re.sub(lead + r"(?:" + "|".join(re.escape(h) for h in ("localhost", "127.0.0.1", "[::1]")) +
                 r")\\([a-z])\$", lambda m: m.group(1) + ":", low)
    try:
        import platform as _pl
        low = re.sub(lead + re.escape(_pl.node().lower()) + r"\\([a-z])\$", lambda m: m.group(1) + ":", low)
    except Exception:
        pass
    low = _collapse_dots(low)
    for r in policy.production_roots:
        for form in _scan_forms(r, policy):
            # No leading boundary on purpose: "-oD:\\Paksh_Data\\x" (option glued to the path) must still be caught.
            # A false positive on an unrelated string ending in the same root text is the safe failure.
            if re.search(re.escape(form) + r"(?=$|[\\\s\"'])", low):
                return r
    return None


def _basename_lower(p):
    return re.split(r"[\\/]", p.rstrip("\\/"))[-1].lower()


def _program_ok(prog, policy):
    if not prog:
        return False
    if _basename_lower(prog) in policy.allowed_exec_names:
        return True
    return any(same_path(prog, ap, policy) for ap in policy.allowed_exec_paths)


def same_path(a, b, policy):
    try:
        return real(a, policy.mod) == real(b, policy.mod)
    except (OSError, ValueError):
        return False


def _evaluate_subprocess(args, policy):
    executable = args[0] if len(args) > 0 else None
    raw_args = args[1] if len(args) > 1 else ()
    cwd = _path(args[2]) if len(args) > 2 else None
    env = args[3] if len(args) > 3 else None
    exe = _path(executable)
    if isinstance(raw_args, (list, tuple)):
        argv = [os.fsdecode(a) if isinstance(a, (bytes, os.PathLike)) else str(a) for a in raw_args]
        text = " ".join(argv)
    elif isinstance(raw_args, (str, bytes, os.PathLike)):
        text = os.fsdecode(raw_args)
        argv = split_windows_cmdline(text)
    else:
        return "unrecognised subprocess argument shape (%s)" % type(raw_args).__name__
    program = exe if exe else (argv[0] if argv else "")
    if not _program_ok(program, policy):
        return "subprocess executable not on the allowlist: %s" % (program or "<none>")
    if exe and argv and _basename_lower(argv[0]) != _basename_lower(exe) and not _program_ok(argv[0], policy):
        return "subprocess argv[0] (%s) disagrees with executable (%s) and is not allowlisted" % (argv[0], exe)
    if _basename_lower(program) in policy.allowed_exec_names and _in_production(program, policy) \
            and ("\\" in program or "/" in program):
        return "subprocess program path is under a protected root: %s" % program
    hit = _text_mentions_protected(text, policy)
    if hit:
        return "subprocess command line mentions protected root %s" % hit
    for tok in argv:
        if 0 < len(tok) <= 1024 and "\n" not in tok and ("\\" in tok or "/" in tok or ":" in tok) \
                and _in_production(tok, policy):
            return "subprocess argument is under a protected root: %s" % tok[:200]
    if isinstance(env, dict):
        for k, v in env.items():
            hit = _text_mentions_protected(str(v), policy)
            if hit:
                return "subprocess environment value %s mentions protected root %s" % (str(k)[:40], hit)
    eff_cwd = cwd if cwd else policy.getcwd()
    if not _under_scratch(eff_cwd, policy):
        return "subprocess working directory outside scratch root: %s" % eff_cwd
    return None


def evaluate(event, args, policy):
    """Return None if the event is acceptable, else a human-readable violation reason.
    A pure function of its arguments (plus os.getcwd for subprocess events), so it is unit-testable
    on any platform."""
    if event == "open":
        p = _path(args[0]) if args else None
        if p is None:
            return None
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 else None
        if _in_production(p, policy):
            return "open() touches production path %s" % p
        writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or \
                  (isinstance(flags, int) and bool(flags & _WRITE_FLAGS))
        if writing and not _under_scratch(p, policy):
            return "open() for WRITE outside scratch root: %s" % p
        return None
    if event == "import":
        fn = _path(args[1]) if len(args) > 1 else None
        if fn and _in_production(fn, policy):
            return "import resolved to a file under a production root: %s" % fn
        return None
    if event in _FORBIDDEN or any(event.startswith(f + ".") for f in _FORBIDDEN):
        return "forbidden operation %s" % event
    if event in _WRITE_PATH1:
        p = _path(args[0]) if args else None
        if p is None:
            return None
        if _in_production(p, policy):
            return "%s touches production path %s" % (event, p)
        if not _under_scratch(p, policy):
            return "%s outside scratch root: %s" % (event, p)
        return None
    if event in _WRITE_PATH2:
        for a in args[:2]:
            p = _path(a)
            if p is not None and _in_production(p, policy):
                return "%s touches production path %s" % (event, p)
        d = _path(args[1]) if len(args) > 1 else None
        if event == "os.rename":
            s = _path(args[0])
            if not (d and _under_scratch(d, policy)):
                return "os.rename destination outside scratch root: %s" % d
            if not (s and _under_scratch(s, policy)):
                return "os.rename source outside scratch root: %s" % s
        elif d is not None and not _under_scratch(d, policy):
            return "%s destination outside scratch root: %s" % (event, d)
        return None
    if event in _READ_PATH1:
        p = _path(args[0]) if args else None
        if p and _in_production(p, policy):
            return "%s touches production path %s" % (event, p)
        if event == "os.chdir" and p and not _under_scratch(p, policy):
            return "os.chdir outside scratch root: %s" % p
        return None
    if event == "sqlite3.connect":
        p = _path(args[0]) if args else None
        t = _sqlite_target(p) if p else None
        if t is None:
            return None
        if _in_production(t, policy):
            return "sqlite3.connect to production path %s" % t
        if not _under_scratch(t, policy):
            return "sqlite3.connect outside scratch root: %s" % t
        return None
    if event == "subprocess.Popen":
        return _evaluate_subprocess(args, policy)
    if event == "os.posix_spawn":
        # POSIX only: subprocess uses posix_spawn for absolute-path programs. Event args are
        # (path, argv, env); evaluate it exactly like a subprocess launch (cwd = this process's cwd).
        a = tuple(args) + (None,) * 3
        return _evaluate_subprocess((a[0], a[1], None, a[2]), policy)
    return None


class Guard:
    """Holds counters and the pre-opened log descriptor. `observe` is the audit hook body."""

    def __init__(self, policy, log_path, hard_exit=True):
        self.policy = policy
        self.hard_exit = hard_exit
        self.events = Counter()
        self.write_dirs = Counter()
        self.connections = Counter()
        self.subprocesses = []
        self.violations = []
        self._tls = threading.local()      # per-thread re-entrancy flag (NOT shared between threads)
        self._lock = threading.Lock()      # protects the counters and lists above
        # os.open BEFORE the hook exists; os.write raises no audit event, so logging from inside
        # the hook cannot recurse.
        self._fd = os.open(str(log_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)

    def _log(self, line):
        try:
            os.write(self._fd, ("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), line)).encode("utf-8", "replace"))
        except OSError:
            pass

    def observe(self, event, args):
        if getattr(self._tls, "busy", False):
            return
        self._tls.busy = True
        try:
            try:
                reason = evaluate(event, args, self.policy)
            except Exception as e:                       # fail CLOSED on an evaluator bug
                reason = "guard evaluation error on %s: %s" % (event, e.__class__.__name__)
            with self._lock:
                self.events[event] += 1
                if event == "socket.connect" and len(args) > 1:
                    try:
                        self.connections["%s:%s" % (args[1][0], args[1][1])] += 1
                    except Exception:
                        self.connections["?"] += 1
                if event == "subprocess.Popen" and len(self.subprocesses) < 50:
                    a = args[1] if len(args) > 1 else ()
                    self.subprocesses.append([str(x) for x in a][:6] if isinstance(a, (list, tuple)) else [str(a)[:200]])
                if reason is None:
                    if event == "open" and args and len(args) > 2 and isinstance(args[2], int) \
                            and args[2] & _WRITE_FLAGS:
                        p = _path(args[0])
                        if p:
                            try:
                                rel = os.path.relpath(p, self.policy.scratch_root).split(os.sep)
                                self.write_dirs[os.sep.join(rel[:2])] += 1
                            except ValueError:
                                pass
                    return
                self.violations.append(reason)
            self._log("VIOLATION %s" % reason)
            if self.hard_exit:
                os._exit(EXIT_CODE_VIOLATION)
            raise PermissionError("scratch guard: " + reason)
        finally:
            self._tls.busy = False

    def install(self):
        sys.addaudithook(self.observe)

    def summary(self):
        with self._lock:
            return {"events": dict(self.events.most_common(30)),
                    "write_dirs_top": dict(self.write_dirs.most_common(15)),
                    "outbound_connections": dict(self.connections.most_common(30)),
                    "subprocesses": list(self.subprocesses[:20]),
                    "violations": list(self.violations)}
