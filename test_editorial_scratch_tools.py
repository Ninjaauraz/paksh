"""
test_editorial_scratch_tools.py - tests for tools/editorial_scratch/ (the Windows scratch-export
preparation tooling).

SAFE BY CONSTRUCTION: everything happens in throwaway directories under the system temp dir.
It never calls scratch_export.main(), never imports export_static, never runs any export,
never touches the real repo's _site, a real database, git history, or the network. The audit-hook
tests run a tiny DUMMY script in a subprocess; they do not run the launcher. `git` is used only
on repositories created inside the temp dir.

WHAT THIS PROVES, AND WHAT IT DOES NOT
  * Linux-tested: path logic, refusals, hook behaviour with POSIX events, link detection with real
    symlinks, manifest/baseline logic, encoding, OG analysis, concurrency.
  * Linux-SIMULATED: Windows rules. Tests marked "[win-lexical]" run the real code with
    mod=ntpath, i.e. Windows path SYNTAX (drive letters, \\\\?\\ prefixes, UNC admin shares, case)
    and Windows-SHAPED subprocess events (flattened command line, executable=None). That checks the
    parsing/decision logic; it does not touch a Windows filesystem or a Windows kernel.
  * NOT verified here: junctions, reparse points on disk, 8.3 names, subst/mapped drives, psapi,
    the real Windows subprocess event stream. test_editorial_scratch_windows.py covers those and
    has only been written, not run on Windows.

Run:  py test_editorial_scratch_tools.py
"""
import ast
import io
import json
import ntpath
import os
import posixpath
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOOLS = ROOT / "tools" / "editorial_scratch"
sys.dont_write_bytecode = True
sys.path.insert(0, str(TOOLS))

import scratch_common as C          # noqa: E402
import scratch_guard as G           # noqa: E402
import scratch_manifest as M        # noqa: E402
import scratch_metrics as MX        # noqa: E402
import scratch_prepare as P         # noqa: E402
import scratch_preflight as PF      # noqa: E402

FAILURES = []


def check(label, cond, detail=""):
    print(f"  {label} ... {'OK' if cond else 'FAIL'}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILURES.append(label)


def why(res, *needles):
    """True if `res` is a refusal/violation reason containing EVERY needle. A bare `is not None` accepts ANY
    refusal - including one for the wrong reason - so checks of 'X is refused' must name the reason."""
    return res is not None and all(n in res for n in needles)


def refuses(fn, *a, **k):
    try:
        fn(*a, **k)
    except C.Refusal as e:
        return str(e)
    except SystemExit:
        return "SystemExit"
    return None


TMP = Path(tempfile.mkdtemp(prefix="paksh_scratch_test_"))
HAVE_GIT = shutil.which("git") is not None
P.SLACK_BYTES = 1024            # tests must not demand a gigabyte of headroom


def mk(*parts):
    p = TMP.joinpath(*parts)
    p.mkdir(parents=True, exist_ok=True)
    return p


def write(p, text="x"):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def make_backup(path, events=7, articles=20):
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(path))
    c.execute("create table events (id integer primary key, title text)")
    c.execute("create table articles (id integer primary key, title text)")
    c.executemany("insert into events (title) values (?)", [("e%d" % i,) for i in range(events)])
    c.executemany("insert into articles (title) values (?)", [("a%d" % i,) for i in range(articles)])
    c.commit(); c.close()


def git(repo, *args):
    return subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "-C", str(repo)] + list(args),
                          capture_output=True, text=True, check=True)


def make_source(root):
    """A fake source repo: REAL paksh_paths.py/database.py (read from this repo), stubs elsewhere,
    plus every kind of file that must NOT be copied."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(str(ROOT / "paksh_paths.py"), str(root / "paksh_paths.py"))
    shutil.copyfile(str(ROOT / "database.py"), str(root / "database.py"))
    write(root / "export_static.py", "# stub")
    write(root / "static" / "index.html", "<html></html>")
    write(root / "static" / "app.jsx", "// jsx")
    write(root / "vendor" / "babel.min.js", "// babel")
    write(root / "vendor" / "tailwindcss", "binary")
    # must be excluded:
    write(root / ".git" / "config", "[remote]\nurl=x")
    for n, t in ((".env", "KEY=secret"), ("ai_keys.env", "GROQ=secret"), ("paksh.db", "db"), ("paksh.db-wal", "wal"),
                 (".pipeline.lock", "live\n1\n"), ("live_log.txt", "log"), ("notes.bak", "bak"), (".netrc", "machine x"),
                 ("id_rsa", "KEY"), ("credentials.json", "{}"), ("cert.pfx", "x")):
        write(root / n, t)
    write(root / "_site" / "index.html", "PRODUCTION OUTPUT")
    write(root / "_site.old" / "x.html", "old")
    return root


name, magic = C.read_marker_magic(ROOT)

print("1. path-safety helpers")
a, b = mk("p1", "data"), mk("p1", "data", "sub")
check("1a: is_under true for a child, false for a sibling prefix", C.is_under(b, a) and not C.is_under(mk("p1", "data2"), a))
check("1b: a path is under itself unless strict", C.is_under(a, a) and not C.is_under(a, a, strict=True))
check("1c: overlaps is symmetric", C.overlaps(a, b) and C.overlaps(b, a) and not C.overlaps(mk("zz1"), mk("zz2")))
check("1d: depth counts components below the drive (posix)", C.depth("/a/b/c", posixpath) == 3 and C.depth("/a", posixpath) == 1)
check("1e: [win-lexical] depth ignores the drive", C.depth("E:\\a\\b\\c", ntpath) == 3 and C.depth("E:\\a\\b", ntpath) == 2 and C.depth("E:\\", ntpath) == 0)
fb = mk("ftree"); write(fb / "ok.py"); write(fb / ".git" / "HEAD"); write(fb / "sub" / "ai_keys.env"); write(fb / "x.DB"); write(fb / "paksh.db-wal")
for n in (".netrc", "id_rsa", "id_ed25519.pub", "credentials.json", "cert.pfx", "store.p12", "x.kdbx", ".npmrc", ".git-credentials"):
    write(fb / "cred" / n)
hits = {Path(h).name for h in C.forbidden_in_tree(fb)}
check("1f: forbidden_in_tree finds git, secrets, key files and databases but not source",
      {".git", "ai_keys.env", "x.DB", "paksh.db-wal", ".netrc", "id_rsa", "id_ed25519.pub", "credentials.json", "cert.pfx",
       "store.p12", "x.kdbx", ".npmrc", ".git-credentials"} <= hits and "ok.py" not in hits, str(hits))
check("1g: load_layout refuses the real tools folder of the production repo (for the right reason)", why(refuses(C.load_layout, TOOLS), "must be run from"), str(refuses(C.load_layout, TOOLS)))
check("1h: load_layout refuses a folder not named 'tools'", "tools" in (refuses(C.load_layout, mk("notools", "x")) or ""))
check("1i: marker name/magic read from the real paksh_paths.py as text", name == ".paksh-production" and magic == "paksh-production-data-root")

print("1w. [win-lexical] Windows path syntax and aliases (ntpath rules, no filesystem)")
D_ROOT = "D:\\Paksh_Data"
under = lambda p: C.is_under(p, D_ROOT, mod=ntpath)
check("1w-a: plain child", under("D:\\Paksh_Data\\database\\paksh.db"))
check("1w-b: case-insensitive", under("d:\\PAKSH_DATA\\Database\\PAKSH.DB"))
check("1w-c: forward slashes", under("D:/Paksh_Data/database/paksh.db"))
check("1w-d: repeated separators", under("D:\\\\Paksh_Data\\\\\\database"))
check("1w-e: dot and dot-dot segments", under("D:\\Paksh_Data\\x\\..\\database") and under("D:\\other\\..\\Paksh_Data\\x"))
check("1w-f: \\\\?\\ extended-length prefix", under("\\\\?\\D:\\Paksh_Data\\database"))
check("1w-g: \\\\.\\ device prefix", under("\\\\.\\D:\\Paksh_Data\\database"))
check("1w-h: //?/ with forward slashes", under("//?/D:/Paksh_Data/database"))
check("1w-i: \\\\localhost\\D$ administrative-share alias", under("\\\\localhost\\D$\\Paksh_Data\\database"))
check("1w-j: \\\\127.0.0.1\\d$ alias (lower-case drive)", under("\\\\127.0.0.1\\d$\\Paksh_Data\\database"))
check("1w-k: \\\\<this PC's name>\\D$ alias", all(under("\\\\%s\\D$\\Paksh_Data\\x" % h) for h in C.local_host_names() if h and "." not in h and h != "::1" and h != "[::1]"))
check("1w-l: \\\\?\\UNC\\localhost\\D$ form", under("\\\\?\\UNC\\localhost\\D$\\Paksh_Data\\x"))
check("1w-m: a sibling with the same prefix is NOT under it", not under("D:\\Paksh_Data2\\x") and not under("D:\\Paksh_Data_old"))
check("1w-n: another drive is not under it", not under("E:\\Paksh_Data\\x"))
check("1w-o: a REMOTE host's D$ share is not mapped to the local D: (documented limitation: other aliases are not detectable lexically)",
      not under("\\\\fileserver\\D$\\Paksh_Data\\x"))
check("1w-p: an alias of a protected root equals the root", C.same("\\\\localhost\\D$\\Paksh_Data", D_ROOT, mod=ntpath))
check("1w-q: overlaps works on Windows syntax", C.overlaps("D:\\Paksh_Data", "d:/paksh_data/backups", mod=ntpath))
check("1w-r: doc-style scratch path below another drive is not under D:", not under("E:\\paksh_scratch\\editorial_test\\run1\\repo"))

def mklink_dir(link, target):
    """Directory link without privilege: a symlink where permitted, else (Windows account without
    the symlink privilege) an NTFS junction via `mklink /J`, which needs none. Raises OSError."""
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
        return "symlink"
    except (OSError, NotImplementedError):
        if os.name != "nt":
            raise
    r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True)
    if r.returncode != 0:
        raise OSError("mklink /J failed: %s" % (r.stderr or r.stdout).strip()[:120])
    return "junction"


def file_symlink(link, target):
    try:
        os.symlink(str(target), str(link))
        return True
    except (OSError, NotImplementedError):
        return False


print("1l. symlinks, junctions, reparse points, git ancestors")
lroot = mk("links"); tgt = mk("links_target"); write(tgt / "keep.txt", "k")
try:
    LINK_KIND = mklink_dir(lroot / "dirlink", tgt)
    can_link = True
except (OSError, NotImplementedError):
    can_link, LINK_KIND = False, None
HAVE_FILE_LINK = can_link and file_symlink(lroot / "filelink", tgt / "keep.txt")
_expect_links = {"dirlink", "filelink"} if HAVE_FILE_LINK else {"dirlink"}
if can_link:
    print("  (directory links are %ss; file symlinks %s)" % (LINK_KIND, "available" if HAVE_FILE_LINK else "NOT permitted for this account, file-link checks skipped"))
    check("1l-a: is_link_or_reparse sees a directory link" + (" and a file symlink" if HAVE_FILE_LINK else ""),
          C.is_link_or_reparse(lroot / "dirlink") and (C.is_link_or_reparse(lroot / "filelink") if HAVE_FILE_LINK else True))
    check("1l-b: links_in_tree reports them and does not follow them", {Path(x).name for x in C.links_in_tree(lroot)} == _expect_links)
    check("1l-c: a link inside a PRUNED folder name is still reported (the link itself), contents are not walked",
          any("dirlink" in x for x in C.links_in_tree(lroot, prune_dirs={"dirlink"})))
    check("1l-d: linked_ancestors flags a path that sits under a symlink", bool(C.linked_ancestors(lroot / "dirlink" / "x")))
    check("1l-e: links_in_tree on a link itself returns it", C.links_in_tree(lroot / "dirlink") == [str(lroot / "dirlink")])
else:
    print("  1l-a..e: skipped (cannot create symlinks here)")
class _St:      # a stat-result stand-in
    def __init__(self, attrs): self.st_file_attributes = attrs
check("1l-f: the Windows reparse-point attribute (0x400) is recognised, others are not", C.attrs_is_reparse(_St(0x400)) and C.attrs_is_reparse(_St(0x400 | 0x10))
      and not C.attrs_is_reparse(_St(0x10)) and not C.attrs_is_reparse(object()))
real_lstat = os.lstat
fake_target = str(mk("fakejunction"))
def fake_lstat(p, *a, **k):
    st = real_lstat(p, *a, **k)
    if os.path.abspath(str(p)) == fake_target:
        class R:      # directory with the reparse attribute, as a junction presents on Windows
            st_mode = st.st_mode; st_file_attributes = 0x410
        return R()
    return st
os.lstat = fake_lstat
try:
    check("1l-g: a directory that presents the reparse attribute is treated as a link (junction simulation)", C.is_link_or_reparse(fake_target))
finally:
    os.lstat = real_lstat
gitroot = mk("gitancestor"); (gitroot / ".git").mkdir()
check("1l-h: ancestor_with_git finds a parent repository", C.ancestor_with_git(gitroot / "sub" / "scratch") == str(gitroot) and C.ancestor_with_git(mk("nogit", "a")) is None)

print("2. audit-hook policy, POSIX-shaped events (pure function)")
S, PROD = mk("scr", "root"), mk("prod", "Paksh_Data")
PREPO = mk("prod", "repo")
TW = str(S / "repo" / "vendor" / "tailwindcss.exe")
pol = G.Policy(str(S), [str(PROD), str(PREPO)], allowed_exec_names=("node", "node.exe"), allowed_exec_paths=(TW,))
ev = lambda e, *args: G.evaluate(e, args, pol)
check("2a: write inside scratch allowed", ev("open", str(S / "repo" / "_site" / "a.html"), "w", 0) is None)
check("2b: write outside scratch refused", "WRITE outside" in (ev("open", str(TMP / "elsewhere.txt"), "w", 0) or ""))
check("2c: READ of a production path refused", "production" in (ev("open", str(PROD / "database" / "paksh.db"), "rb", 0) or ""))
check("2d: read outside scratch (e.g. stdlib) allowed", ev("open", "/usr/lib/python3/os.py", "r", 0) is None)
check("2e: os.open with write flags outside scratch refused", why(ev("open", str(TMP / "f"), None, os.O_WRONLY | os.O_CREAT), "WRITE outside scratch root"))
check("2f: os.open read-only outside scratch allowed", ev("open", str(TMP / "f"), None, os.O_RDONLY) is None)
check("2g: file descriptors are ignored", ev("open", 3, "w", 0) is None)
check("2h: mkdir/remove/rmdir/rmtree outside scratch refused", all(why(ev(e, str(TMP / "x")), "outside scratch root") for e in ("os.mkdir", "os.remove", "os.rmdir", "shutil.rmtree")))
check("2i: the same inside scratch allowed", all(ev(e, str(S / "x")) is None for e in ("os.mkdir", "os.remove", "os.rmdir", "shutil.rmtree")))
check("2j: rename within scratch allowed (the _site.building -> _site swap)", ev("os.rename", str(S / "repo" / "_site.building"), str(S / "repo" / "_site")) is None)
check("2k: rename OUT of scratch refused", why(ev("os.rename", str(S / "a"), str(TMP / "b")), "destination outside scratch root"))
check("2l: rename INTO scratch from outside refused", why(ev("os.rename", str(TMP / "b"), str(S / "a")), "source outside scratch root"))
check("2m: rename touching production refused", why(ev("os.rename", str(PREPO / "_site"), str(S / "a")), "touches production path"))
check("2n: copy from production into scratch refused (reads production)", why(ev("shutil.copyfile", str(PROD / "x"), str(S / "x")), "touches production path"))
check("2o: sqlite3.connect to the scratch db allowed", ev("sqlite3.connect", str(S / "data" / "database" / "paksh.db")) is None)
check("2p: sqlite3.connect to production refused", why(ev("sqlite3.connect", str(PROD / "database" / "paksh.db")), "production path"))
check("2q: sqlite3 :memory: allowed; file: URI to production refused",
      ev("sqlite3.connect", ":memory:") is None and why(ev("sqlite3.connect", "file:" + str(PROD / "database" / "paksh.db") + "?mode=ro"), "production path"))
check("2r: sqlite3.connect outside scratch refused", why(ev("sqlite3.connect", str(TMP / "other.db")), "outside scratch root"))
check("2s: import resolving into production refused", why(ev("import", "evil", str(PREPO / "evil.py")), "production root"))
check("2t: POSIX-shaped: node with a scratch cwd allowed", ev("subprocess.Popen", "node", ["node", "-e", "1"], str(S / "repo"), None) is None)
check("2u: POSIX-shaped: the exact vendored Tailwind path allowed", ev("subprocess.Popen", TW, [TW, "-c", "y"], str(S / "repo"), None) is None)
check("2u2: a different program in the SAME vendor folder is refused (exact path, not folder)",
      why(ev("subprocess.Popen", str(S / "repo" / "vendor" / "evil.exe"), [str(S / "repo" / "vendor" / "evil.exe")], str(S / "repo"), None), "not on the allowlist"))
check("2v: git refused", "allowlist" in (ev("subprocess.Popen", "git", ["git", "push"], str(S), None) or ""))
check("2w: python/powershell refused", why(ev("subprocess.Popen", "python", ["python"], str(S), None), "not on the allowlist") and why(ev("subprocess.Popen", "powershell.exe", ["powershell"], str(S), None), "not on the allowlist"))
check("2x: node with cwd outside scratch refused", why(ev("subprocess.Popen", "node", ["node"], str(TMP), None), "working directory outside scratch root"))
check("2y: node with a production path in argv refused", why(ev("subprocess.Popen", "node", ["node", str(PROD / "x.js")], str(S), None), "protected root"))
check("2z: os.system / exec / startfile are FORBIDDEN outright (posix_spawn is not: it is evaluated as a launch, see 3n)", all(why(ev(e, "x"), "forbidden operation " + e) for e in ("os.system", "os.exec", "os.startfile")))
check("2za: chdir outside scratch refused, inside allowed", why(ev("os.chdir", str(TMP)), "os.chdir outside scratch root") and ev("os.chdir", str(S / "repo")) is None)
check("2zb: unknown events are ignored (socket.connect is recorded elsewhere, not blocked)", ev("socket.connect", object(), ("example.com", 443)) is None)
check("2zc: an unrecognised argument shape is refused (fail closed)", why(ev("subprocess.Popen", "node", 12345, str(S), None), "unrecognised subprocess argument shape"))

print("2w. [win-lexical] Windows-SHAPED subprocess events and paths (flattened command line, executable=None)")
WS = "E:\\paksh_scratch\\editorial_test\\run1"
WREPO = WS + "\\repo"
WTW = WREPO + "\\vendor\\tailwindcss.exe"
wpol = G.Policy(WS, ["D:\\Paksh_Data", "C:\\paksh_project\\paksh"], allowed_exec_names=("node", "node.exe"),
                allowed_exec_paths=(WTW,), mod=ntpath, getcwd=lambda: WREPO)
wev = lambda e, *args: G.evaluate(e, args, wpol)
cmd = subprocess.list2cmdline
ev_node = (None, cmd(["node", "-e", "const fs=require('fs'); console.log(\"hi there\")", WREPO + "\\vendor\\babel.min.js", WREPO + "\\static\\app.jsx", WS + "\\repo\\_site.building\\static\\app.js"]), WREPO, None)
check("2w-a: node via list2cmdline string, executable=None, scratch cwd -> allowed", wev("subprocess.Popen", *ev_node) is None)
check("2w-b: ...the SAME event as a list (POSIX shape) is also allowed", wev("subprocess.Popen", None, ["node", "-e", "1"], WREPO, None) is None)
check("2w-c: node with a quoted full path containing spaces, cwd=None (inherits an in-scratch cwd) -> allowed",
      wev("subprocess.Popen", None, cmd(["C:\\Program Files\\nodejs\\node.exe", "-v"]), None, None) is None)
check("2w-d: node.exe by bare name -> allowed", wev("subprocess.Popen", None, "node.exe -v", WREPO, None) is None)
check("2w-e: the exact vendored Tailwind path (quoted program, flattened args) -> allowed",
      wev("subprocess.Popen", None, cmd([WTW, "-c", WREPO + "\\tailwind.config.js", "-i", WREPO + "\\in.css", "-o", WREPO + "\\_site.building\\static\\tailwind.css", "--minify"]), WREPO, None) is None)
check("2w-f: Tailwind given as executable= with the string args -> allowed", wev("subprocess.Popen", WTW, cmd([WTW, "--minify"]), WREPO, None) is None)
check("2w-g: another exe in the vendor folder -> refused", "allowlist" in (wev("subprocess.Popen", None, cmd([WREPO + "\\vendor\\evil.exe", "x"]), WREPO, None) or ""))
check("2w-h: a copy of tailwindcss.exe elsewhere -> refused", why(wev("subprocess.Popen", None, cmd(["C:\\tmp\\tailwindcss.exe"]), WREPO, None), "not on the allowlist"))
check("2w-i: case/slash-style variants of the SAME Tailwind path are still the allowed program",
      wev("subprocess.Popen", None, cmd([WTW.lower().replace("\\", "/"), "-v"]), WREPO, None) is None)
for label, arg in (("backslashes", "D:\\Paksh_Data\\database\\paksh.db"), ("forward slashes", "D:/Paksh_Data/database/paksh.db"),
                   ("lower case", "d:\\paksh_data\\x"), ("extended-length prefix", "\\\\?\\D:\\Paksh_Data\\x"),
                   ("local admin share", "\\\\localhost\\D$\\Paksh_Data\\x"), ("dot-dot traversal", "D:\\other\\..\\Paksh_Data\\x"), ("dot-dot with dot segments", "d:\\a\\.\\b\\..\\..\\paksh_data\\x"), ("production repo", "C:\\paksh_project\\paksh\\_site\\index.html"), ("production repo, mixed case", "c:/PAKSH_PROJECT/paksh/_site")):
    check(f"2w-j: [{label}] production path as a LATER argument of an allowed program -> refused",
          why(wev("subprocess.Popen", None, cmd(["node", "-e", "1", arg]), WREPO, None), "protected root"), arg)
    check(f"2w-k: [{label}] ...as the only token of a quoted argument with spaces -> refused",
          why(wev("subprocess.Popen", None, cmd(["node", "x y", "pre " + arg]), WREPO, None), "protected root"))
check("2w-l: option glued to a production path (-oD:\\Paksh_Data\\x) -> refused", why(wev("subprocess.Popen", None, "node -oD:\\Paksh_Data\\x", WREPO, None), "protected root"))
check("2w-m: a similarly named but different folder (D:\\Paksh_Data2) is not mistaken for production", wev("subprocess.Popen", None, cmd(["node", "D:\\Paksh_Data2\\x"]), WREPO, None) is None)
check("2w-n: cmd.exe /c wrapper (shell=True) -> refused because cmd.exe is not on the allowlist", why(wev("subprocess.Popen", "C:\\Windows\\System32\\cmd.exe", 'C:\\Windows\\System32\\cmd.exe /c "node -e 1"', WREPO, None), "not on the allowlist", "cmd.exe"))
check("2w-o: powershell / git / python (by string command line) -> refused",
      all(why(wev("subprocess.Popen", None, c, WREPO, None), "not on the allowlist") for c in ("powershell -Command x", "git push", "python.exe -c pass", '"C:\\Program Files\\Git\\cmd\\git.exe" status')))
check("2w-p: a program NAMED node.exe inside production is refused because its PATH is protected",
      why(wev("subprocess.Popen", None, "D:\\Paksh_Data\\node.exe -v", WREPO, None), "program path is under a protected root")
      and why(wev("subprocess.Popen", None, cmd(["C:\\paksh_project\\paksh\\node.exe", "-v"]), WREPO, None), "program path is under a protected root"))
check("2w-q: working directory outside scratch -> refused", why(wev("subprocess.Popen", None, "node -v", "C:\\Windows", None), "working directory outside scratch root"))
bad_cwd_pol = G.Policy(WS, ["D:\\Paksh_Data"], mod=ntpath, getcwd=lambda: "C:\\Users\\someone")
check("2w-r: cwd=None while the process cwd is outside scratch -> refused", why(G.evaluate("subprocess.Popen", (None, "node -v", None, None), bad_cwd_pol), "working directory outside scratch root", "someone"))
check("2w-s: environment value pointing into production -> refused; benign environment allowed",
      why(wev("subprocess.Popen", None, "node -v", WREPO, {"X": "D:\\Paksh_Data\\y"}), "environment value X") and wev("subprocess.Popen", None, "node -v", WREPO, {"X": "1", "PATH": "C:\\Windows"}) is None)
check("2w-t: a non-allowlisted executable= with a node command line -> refused on the executable (allowlist)", why(wev("subprocess.Popen", "C:\\Windows\\System32\\cmd.exe", "node -v", WREPO, None), "not on the allowlist", "cmd.exe"))
check("2w-t2: an ALLOWLISTED executable= whose command line starts with a different, non-allowlisted program -> refused as a DISAGREEMENT",
      why(wev("subprocess.Popen", "node", "powershell -c x", WREPO, None), "disagrees with executable"))
check("2w-u: an empty command line -> refused", why(wev("subprocess.Popen", None, "", WREPO, None), "not on the allowlist", "<none>"))
check("2w-v: bytes command line handled", wev("subprocess.Popen", None, b"node -v", WREPO, None) is None)
check("2w-w: write in scratch allowed, with any case/slash style", wev("open", WREPO + "\\_site\\a.html", "w", 0) is None and wev("open", WS.lower().replace("\\", "/") + "/repo/_site/b.html", "w", 0) is None)
check("2w-x: write to production in several spellings refused",
      all(why(wev("open", p, "w", 0), "production path") for p in ("D:\\Paksh_Data\\database\\paksh.db", "d:/paksh_data/x", "\\\\?\\D:\\Paksh_Data\\x", "\\\\localhost\\D$\\Paksh_Data\\x")))
check("2w-y: ..\\ traversal out of scratch is a write outside scratch", why(wev("open", WS + "\\repo\\..\\..\\other\\x.txt", "w", 0), "WRITE outside scratch root"))
check("2w-z: rename out of scratch refused; sqlite file URI to production refused",
      why(wev("os.rename", WS + "\\a", "E:\\elsewhere\\b"), "destination outside scratch root") and why(wev("sqlite3.connect", "file:///D:/Paksh_Data/database/paksh.db?mode=ro"), "production path"))
rt = [["node", "-e", "console.log(\"a b\")", "C:\\x y\\z.js"], ["C:\\Program Files\\nodejs\\node.exe", "--flag=\"q\"", "tail\\"],
      ["prog", "", "a\\\\", "b\\\"c", "d e\\\\", "plain"], ["x", "\\\\server\\share\\f", 'say "hi"', "back\\\\\\\\\\\\"]]
check("2w-za: split_windows_cmdline inverts subprocess.list2cmdline on tricky argv (backslashes, quotes, empty, spaces)",
      all(G.split_windows_cmdline(cmd(a)) == a for a in rt), str([G.split_windows_cmdline(cmd(a)) for a in rt]))

print("3. the hook enforces it for real (dummy script in a subprocess; NOT the launcher)")
runner = TMP / "hook_runner.py"
runner.write_text(textwrap.dedent('''
    import sys, os
    sys.dont_write_bytecode = True
    sys.path.insert(0, %r)
    import scratch_guard as G
    scratch, prod, log, snippet = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    extra = tuple(sys.argv[5:])
    g = G.Guard(G.Policy(scratch, [prod], allowed_exec_paths=extra), log, hard_exit=True)
    g.install()
    os.chdir(scratch)
    exec(compile(snippet, "<snippet>", "exec"))
    print("SURVIVED")
''' % str(TOOLS)), encoding="utf-8")
GS, GP = mk("g", "scratch"), mk("g", "prod")
outside = TMP / "g" / "outside.txt"
victim = mk("g", "victim"); write(victim / "keep.txt", "keep")
prod_db = write(GP / "database" / "paksh.db", "PRODUCTION")


def run_hook(snippet, *extra, timeout=60):
    log = TMP / "g" / "guard.log"
    if log.exists():
        log.unlink()
    r = subprocess.run([sys.executable, "-B", str(runner), str(GS), str(GP), str(log), snippet] + list(extra),
                       capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, (log.read_text() if log.exists() else "")


rc, out, lg = run_hook("open(%r,'w').write('ok')" % str(GS / "inside.txt"))
check("3a: a write inside scratch is allowed and the script survives", rc == 0 and "SURVIVED" in out and (GS / "inside.txt").exists())
rc, out, lg = run_hook("open(%r,'w').write('bad')" % str(outside))
check("3b: a write outside scratch kills the process (exit 97) before the file exists",
      rc == G.EXIT_CODE_VIOLATION and "SURVIVED" not in out and not outside.exists() and "VIOLATION" in lg, "%s %s" % (rc, lg))
rc, out, lg = run_hook("try:\n    open(%r,'w')\nexcept BaseException:\n    pass\nprint('swallowed')" % str(outside))
check("3c: a try/except in the exporter cannot swallow it (hard exit, not an exception)", rc == G.EXIT_CODE_VIOLATION and "swallowed" not in out)
rc, out, lg = run_hook("open(%r,'rb').read()" % str(prod_db))
check("3d: even READING a production file is fatal", rc == G.EXIT_CODE_VIOLATION and "production" in lg)
rc, out, lg = run_hook("import shutil; shutil.rmtree(%r)" % str(victim))
check("3e: rmtree outside scratch is stopped before anything is deleted", rc == G.EXIT_CODE_VIOLATION and (victim / "keep.txt").exists())
rc, out, lg = run_hook("import os; os.rename(%r, %r)" % (str(GS / "inside.txt"), str(TMP / "g" / "moved.txt")))
check("3f: renaming a scratch file out of scratch is stopped", rc == G.EXIT_CODE_VIOLATION and not (TMP / "g" / "moved.txt").exists())
rc, out, lg = run_hook("import sqlite3; sqlite3.connect(%r)" % str(prod_db))
check("3g: opening the production database via sqlite3 is stopped", rc == G.EXIT_CODE_VIOLATION and prod_db.read_text() == "PRODUCTION")
rc, out, lg = run_hook("import subprocess, sys; subprocess.run([sys.executable, '-c', 'pass'])")
check("3h: launching a non-allowlisted program (here: python) is stopped", rc == G.EXIT_CODE_VIOLATION and "allowlist" in lg)
rc, out, lg = run_hook("import subprocess; subprocess.run(['git', 'status'])")
check("3i: launching git is stopped", rc == G.EXIT_CODE_VIOLATION)
rc, out, lg = run_hook("import os; os.system('echo hi')")
check("3j: os.system is stopped", rc == G.EXIT_CODE_VIOLATION)
rc, out, lg = run_hook("import os; os.makedirs(%r + '/sub/dir')" % str(GS))
check("3k: creating directories inside scratch is fine", rc == 0 and "SURVIVED" in out)
check("3l: the violation log names the reason and a timestamp", re.search(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d VIOLATION ", run_hook("open(%r,'w')" % str(outside))[2]) is not None)
if shutil.which("node"):
    rc, out, lg = run_hook("import subprocess; subprocess.run(['node', '-v'], check=True, capture_output=True)")
    check("3m: a REAL node launch (real POSIX event shape, scratch cwd) passes the allowlist end to end", rc == 0 and "SURVIVED" in out, lg or out)
else:
    print("  3m: skipped (node not installed)")
# A "#!/bin/sh" file cannot be launched by CreateProcess (WinError 193), so on Windows the stand-in
# programs are .cmd batch files. The guard decision (exact allowlisted path, sibling refused,
# protected argument refused) is made on the subprocess.Popen audit event BEFORE the OS launches
# anything, so 3n-3p test the same rules on both platforms.
_WIN = os.name == "nt"
fake_tw = GS / "repo" / "vendor" / ("tailwindcss.cmd" if _WIN else "tailwindcss")
fake_tw.parent.mkdir(parents=True, exist_ok=True)
fake_tw.write_text("@exit /b 0\r\n" if _WIN else "#!/bin/sh\nexit 0\n"); fake_tw.chmod(0o755)
evil = GS / "repo" / "vendor" / ("evil.cmd" if _WIN else "evil")
evil.write_text("@exit /b 0\r\n" if _WIN else "#!/bin/sh\nexit 0\n"); evil.chmod(0o755)
rc, out, lg = run_hook("import subprocess; subprocess.run([%r, '--minify'], check=True)" % str(fake_tw), str(fake_tw))
check("3n: the exact allowlisted Tailwind path (real subprocess) is allowed", rc == 0 and "SURVIVED" in out, lg or out)
rc, out, lg = run_hook("import subprocess; subprocess.run([%r], check=True)" % str(evil), str(fake_tw))
check("3o: a sibling program in the same folder is stopped (real subprocess)", rc == G.EXIT_CODE_VIOLATION and "allowlist" in lg)
rc, out, lg = run_hook("import subprocess; subprocess.run([%r, %r], check=True)" % (str(fake_tw), str(prod_db)), str(fake_tw))
check("3p: the allowed program given a production path argument is stopped", rc == G.EXIT_CODE_VIOLATION and "production" in lg.lower() or "protected" in lg.lower())

print("3t. concurrency: violations are evaluated whatever other threads are doing")
tl_pol = G.Policy(str(S), [str(PROD)])
g1 = G.Guard(tl_pol, str(TMP / "g1.log"), hard_exit=False)
bad = str(TMP / "outside_t.txt")
missed = [0]; lock = threading.Lock(); N_THREADS, PER = 8, 3000
def hammer():
    m = 0
    for _ in range(PER):
        try:
            g1.observe("open", (bad, "w", 0)); m += 1          # returning normally == NOT detected
        except PermissionError:
            pass
    with lock: missed[0] += m
ts = [threading.Thread(target=hammer) for _ in range(N_THREADS)]
[t.start() for t in ts]; [t.join() for t in ts]
check("3t-a: %d violating events from %d threads: every one detected (0 missed)" % (N_THREADS * PER, N_THREADS), missed[0] == 0, "missed=%d" % missed[0])
check("3t-b: counters are exact under contention (no lost updates)", g1.events["open"] == N_THREADS * PER and len(g1.violations) == N_THREADS * PER)
g2 = G.Guard(tl_pol, str(TMP / "g2.log"), hard_exit=False)
ok_path = str(S / "repo" / "_site" / "x.html")
stop = [False]; seen_ok = [0]
def spam():
    while not stop[0]:
        g2.observe("open", (ok_path, "w", os.O_WRONLY | os.O_CREAT)); seen_ok[0] += 1
sp = [threading.Thread(target=spam) for _ in range(4)]
[t.start() for t in sp]
time.sleep(0.05)
caught = 0
for _ in range(500):
    try:
        g2.observe("open", (bad, "w", 0))
    except PermissionError:
        caught += 1
stop[0] = True; [t.join() for t in sp]
check("3t-c: 500 violations from one thread while 4 others stream legitimate events: all 500 caught", caught == 500 and seen_ok[0] > 0, "caught=%d" % caught)
check("3t-d: the legitimate events from the busy threads did not produce violations", len(g2.violations) == 500)
snippet = textwrap.dedent('''
    import threading, time
    stop = False
    def spam(k):
        i = 0
        while not stop:
            with open(r'%s/spam_%%d_%%d.txt' %% (k, i %% 5), 'w') as f:
                f.write('x')
            i += 1
    ts = [threading.Thread(target=spam, args=(k,), daemon=True) for k in range(6)]
    [t.start() for t in ts]
    time.sleep(0.2)
    open(%r, 'w')
    print('SURVIVED')
''') % (str(GS), str(outside))
codes = [run_hook(snippet)[0] for _ in range(4)]
check("3t-e: a REAL installed hook still kills the process (exit 97) when a violation happens while 6 threads write legitimately (4 trials)", codes == [G.EXIT_CODE_VIOLATION] * 4, str(codes))
snippet2 = textwrap.dedent('''
    import threading, time
    def violate():
        time.sleep(0.05)
        open(%r, 'w')
    t = threading.Thread(target=violate); t.start()
    n = 0
    t0 = time.time()
    while time.time() - t0 < 2:
        with open(r'%s/busy.txt', 'w') as f:
            f.write('x')
        n += 1
    print('SURVIVED')
''') % (str(outside), str(GS))
codes = [run_hook(snippet2)[0] for _ in range(3)]
check("3t-f: a violation raised from a WORKER thread while the main thread is busy is also fatal (3 trials)", codes == [G.EXIT_CODE_VIOLATION] * 3, str(codes))

print("4. prepare / preflight on a synthetic scratch root")
SRC = make_source(TMP / "src_repo")
PRODDATA, PRODREPO = mk("prod_data"), mk("prod_repo")
BACKUP = PRODDATA / "backups" / "daily" / "paksh_2026.db"
make_backup(BACKUP)
LIVE = PRODDATA / "database" / "paksh.db"
make_backup(LIVE)
write(PRODDATA / name, magic)
write(PRODREPO / "export_static.py", "# production exporter stub")
write(PRODREPO / "live.py", 'PRODUCTION_DATA_DIR = r"%s"\n' % PRODDATA)
write(PRODREPO / "_site" / "index.html", "<html>live</html>")
write(PRODREPO / "_site" / "data" / "events.json", "{}")
if HAVE_GIT:
    subprocess.run(["git", "init", "-q", str(PRODREPO)], check=True)
    git(PRODREPO, "add", "-A"); git(PRODREPO, "commit", "-q", "-m", "init")
else:
    (PRODREPO / ".git").mkdir()
live_before = (LIVE.stat().st_size, LIVE.stat().st_mtime_ns)
INIT = lambda root, **k: P.init(str(root), k.pop("src", str(SRC)), k.pop("backup", str(BACKUP)), k.pop("pdata", str(PRODDATA)),
                                 k.pop("prepo", str(PRODREPO)), environ=k.pop("environ", {}), local_app_data=k.pop("lad", ""), **k)
root = TMP / "work" / "scratch_root"
layout, base = INIT(root)
check("4a: init created repo/data/logs/tools + sentinel", all((root / n).exists() for n in ("repo", "data", "logs", "tools", "scratch_layout.json", "SCRATCH_ROOT.txt")))
repo = root / "repo"
check("4b: the scratch repo has NO git metadata", not (repo / ".git").exists() and not C.forbidden_in_tree(repo), str(C.forbidden_in_tree(repo)))
check("4c: secrets, key files, databases, locks, logs and old outputs were not copied",
      not any((repo / n).exists() for n in (".env", "ai_keys.env", "paksh.db", "paksh.db-wal", ".pipeline.lock", "live_log.txt", "_site", "_site.old",
                                            "notes.bak", ".netrc", "id_rsa", "credentials.json", "cert.pfx")))
check("4d: code and the vendored build tools were copied", all((repo / n).is_file() for n in ("export_static.py", "paksh_paths.py", "database.py", "static/index.html", "vendor/babel.min.js", "vendor/tailwindcss")))
check("4e: the database is a copy of the BACKUP, with baseline counts recorded", base["counts"] == {"events": 7, "articles": 20} and base["integrity_check"] == "ok")
check("4f: the live database was neither opened for writing nor changed", (LIVE.stat().st_size, LIVE.stat().st_mtime_ns) == live_before)
check("4g: the marker carries the real magic string", (root / "data" / name).read_text() == magic)
check("4h: tools were copied into <root>/tools", (root / "tools" / "scratch_export.py").is_file() and (root / "tools" / "scratch_metrics.py").is_file())
check("4i: load_layout works from <root>/tools and reports the same paths", C.load_layout(root / "tools")["db_path"] == layout["db_path"])
check("4j: baseline_counts.json written to logs", json.loads((root / "logs" / "baseline_counts.json").read_text())["counts"]["events"] == 7)
check("4k: the layout records the protected roots (data, repo, source) and a disk requirement",
      all(any(C.same(r, x) for x in layout["protected_roots"]) for r in (PRODDATA, PRODREPO, SRC)) and layout["required_free_bytes"] == 2 * layout["production_site_bytes"] + P.SLACK_BYTES)
check("4l: the production _site size was measured (read-only) at init", layout["production_site_bytes"] > 0)

print("4p. production paths are validated, not trusted (a typo must not protect the wrong place)")
init_with = type("N", (), {"n": 0})
def tryit(**k):
    init_with.n += 1
    return refuses(INIT, TMP / "w" / ("p%d" % init_with.n), **k)
typo = mk("typo_data")
check("4p-a: a data dir that does not exist is refused", "not an existing folder" in (tryit(pdata=str(TMP / "Paksh_Dta")) or ""))
check("4p-b: an existing folder WITHOUT the production marker is refused (typo protecting the wrong place)", "genuine production marker" in (tryit(pdata=str(typo)) or ""))
write(typo / name, "wrong magic")
check("4p-c: a marker with the wrong content is refused", "genuine production marker" in (tryit(pdata=str(typo)) or ""))
write(typo / name, magic)
check("4p-d: a marked folder without database/paksh.db is refused", "paksh.db" in (tryit(pdata=str(typo)) or ""))
make_backup(typo / "database" / "paksh.db")
check("4p-e: a real-looking but DIFFERENT data dir contradicts live.py's PRODUCTION_DATA_DIR and is refused", "PRODUCTION_DATA_DIR" in (tryit(pdata=str(typo)) or ""))
check("4p-f: a production repo that does not exist / is not a git work tree is refused",
      "not a git work tree" in (tryit(prepo=str(TMP / "nope")) or "") and "not a git work tree" in (tryit(prepo=str(mk("plainrepo"))) or ""))
fakelad = mk("lad"); write(fakelad / "Paksh" / "data_dir.txt", "# comment\n%s\n" % mk("other_data"))
l2, b2 = INIT(TMP / "w" / "lad1", lad=str(fakelad))
check("4p-g: the folder named by data_dir.txt is added to the protected roots", any(C.same(r, TMP / "other_data") for r in l2["protected_roots"]) and any("data_dir.txt" in n for n in b2["notes"]))
l3, b3 = INIT(TMP / "w" / "env1", environ={"PAKSH_DATA_DIR": str(mk("env_data"))})
check("4p-h: an already-set PAKSH_DATA_DIR is added to the protected roots", any(C.same(r, TMP / "env_data") for r in l3["protected_roots"]))
check("4p-i: a scratch root that overlaps an EXTRA protected root is refused", "overlaps" in (refuses(INIT, TMP / "other_data" / "a" / "b", lad=str(fakelad)) or ""))

print("4r. refusals: roots, backups, links, disk")
nov = make_source(TMP / "src_novendor"); shutil.rmtree(str(nov / "vendor"))
# "/x" is absolute on POSIX but has no drive on Windows, where it is (correctly) refused as NOT
# ABSOLUTE - a different rule. abspath("/x") is "/x" on POSIX and "<current drive>:\x" on Windows:
# absolute and one level deep on both, so the depth rule is what is being tested.
SHALLOW = os.path.abspath("/x")
check("4r-pre: the shallow fixture is absolute and exactly one level deep on this platform",
      os.path.isabs(SHALLOW) and C.depth(SHALLOW) == 1, SHALLOW)
check("4r-a: init refuses a scratch root that is shallow", "shallow" in (refuses(INIT, SHALLOW) or ""))
check("4r-b: ...naming the folder depth it needs", "folder levels" in (refuses(INIT, SHALLOW) or ""))
check("4r-c0: control - a relative path is refused as NOT absolute (the rule that '/x' hit on Windows)",
      "absolute" in (refuses(INIT, "relative_dir") or ""))
check("4r-c: init refuses a non-empty scratch root", why(refuses(INIT, root), "already exists and is not empty"))
check("4r-d: init refuses a scratch root inside the production data dir", "overlaps" in (refuses(INIT, PRODDATA / "s" / "t") or ""))
check("4r-e: ...inside the production repo", "overlaps" in (refuses(INIT, PRODREPO / "x" / "y") or ""))
deep = mk("deep", "a", "b"); ddata = mk("deep", "a", "b", "c", "prod_data")
write(ddata / name, magic); make_backup(ddata / "database" / "paksh.db"); write(PRODREPO / "live.py", 'PRODUCTION_DATA_DIR = r"%s"\n' % ddata)
check("4r-f: ...that CONTAINS the production data dir", "overlaps" in (refuses(INIT, deep, pdata=str(ddata)) or ""))
write(PRODREPO / "live.py", 'PRODUCTION_DATA_DIR = r"%s"\n' % PRODDATA)
check("4r-g: init refuses the LIVE database as the backup", "LIVE" in (tryit(backup=str(LIVE)) or ""))
write(Path(str(LIVE) + "-wal"), "wal")
check("4r-h: ...and its -wal sidecar", "LIVE" in (tryit(backup=str(LIVE) + "-wal") or ""))
check("4r-i: init refuses a source without the vendored build tools", "vendor" in (tryit(src=str(nov)) or ""))
check("4r-j: a refused init leaves nothing behind", not (TMP / "w" / ("p%d" % init_with.n)).exists())
junk = TMP / "notadb.db"; junk.write_text("not sqlite")
r = tryit(backup=str(junk))
check("4r-k: a corrupt/non-SQLite backup is a clean refusal naming SQLite, and the half-built root is removed", r is not None and "SQLite" in r and not (TMP / "w" / ("p%d" % init_with.n)).exists(), str(r))
empty = TMP / "empty.db"; sqlite3.connect(str(empty)).close()
r = tryit(backup=str(empty))
check("4r-l: a SQLite file without an events table is refused (wrong backup)", r is not None and "events" in r, str(r))
preexist = mk("w", "preexisting_empty")
r = refuses(INIT, preexist, backup=str(junk))
check("4r-m: a failed init in a PRE-EXISTING empty folder removes only what it created and keeps the folder", r is not None and preexist.is_dir() and not any(preexist.iterdir()), str(r))
trunc = TMP / "truncated.db"; trunc.write_bytes((BACKUP.read_bytes())[:-300] if BACKUP.stat().st_size > 400 else b"")
check("4r-n: a truncated backup file is refused (integrity or readability), not copied through", (lambda r: why(r) and ("readable SQLite" in r or "integrity_check" in r or "changed size" in r))(tryit(backup=str(trunc))))
P.SLACK_BYTES = 10 ** 18
check("4r-o: init refuses when the drive lacks backup + 2 x _site + headroom (the documented formula)", "free disk space" in (tryit() or ""))
P.SLACK_BYTES = 1024
if can_link:
    srcl = make_source(TMP / "src_linked"); mklink_dir(srcl / "static" / "sneaky", tgt)
    check("4r-p: a symlink inside the source tree (outside excluded folders) is refused", "symlink" in (tryit(src=str(srcl)) or ""))
    srcl2 = make_source(TMP / "src_linked2"); mklink_dir(srcl2 / "_site" / "alias", tgt)
    l4, _ = INIT(TMP / "w" / "linkok")
    check("4r-q: ...but links inside excluded folders (never copied) do not block (control)", l4 is not None)
    blink = TMP / "backup_link.db"
    if file_symlink(blink, BACKUP):
        check("4r-r: a symlinked backup file is refused", "symlink" in (tryit(backup=str(blink)) or ""))
    else:
        print("  4r-r: skipped (file symlinks need a privilege this account lacks; junctions are directory-only)")
    realroot = mk("realparent"); mklink_dir(TMP / "linkparent", realroot)
    check("4r-s: a scratch root under a symlinked folder is refused", "symlink" in (refuses(INIT, TMP / "linkparent" / "a" / "b") or ""))
else:
    print("  4r-p..s: skipped (cannot create symlinks here)")
gitparent = mk("gitparent"); (gitparent / ".git").mkdir()
check("4r-t: a scratch root inside any git work tree is refused", "git work tree" in (refuses(INIT, gitparent / "a" / "b" / "run") or ""))

OK_ENV = dict(os.environ)
def pre(**kw):
    kw.setdefault("tools_dir", layout["tools"])
    return PF.preflight(layout, **kw)
for k in ("PAKSH_DATA_DIR", "PAKSH_ALLOW_NEW_DB", "PAKSH_ALLOW_EXPORT_COLLAPSE", "PYTHONPATH"):
    os.environ.pop(k, None)
errs, warns, info = pre()
check("4u: a correct scratch root passes preflight", not errs, str(errs))
res = info.get("resolved", {})
check("4v: the REAL paksh_paths/database resolve to the scratch database, from the scratch repo",
      C.same(res.get("db_path", ""), layout["db_path"]) and C.same(res.get("database_DB_PATH", ""), layout["db_path"])
      and C.is_under(res.get("paksh_paths_file", ""), repo), str(res))
check("4w: the existing production guard (unmodified) accepted it - because of the marker, which proves nothing about isolation", res.get("guard") == "passed")
os.environ["PAKSH_DATA_DIR"] = str(PRODDATA)
check("4x: PAKSH_DATA_DIR already set to something else is an error", any("PAKSH_DATA_DIR is already set" in e for e in pre()[0]))
os.environ["PAKSH_DATA_DIR"] = layout["data"]
check("4y: PAKSH_DATA_DIR already equal to the scratch data dir is fine", not pre()[0], str(pre()[0]))
os.environ.pop("PAKSH_DATA_DIR")
for var in ("PAKSH_ALLOW_NEW_DB", "PAKSH_ALLOW_EXPORT_COLLAPSE"):
    os.environ[var] = "1"
    check(f"4z: {var}=1 is refused (it weakens a production guard)", any(var in e for e in pre()[0]))
    os.environ.pop(var)
os.environ["PAKSH_STORYLINE_SIM"] = "0.1"
w_env = pre()[1]
check("4z2: other PAKSH_* variables that change export OUTPUT (not paths) are surfaced as a warning naming the variable, not its value",
      any("PAKSH_STORYLINE_SIM" in w for w in w_env) and not any("0.1" in w for w in w_env) and not pre()[0])
os.environ.pop("PAKSH_STORYLINE_SIM")
os.environ["PYTHONPATH"] = str(PRODREPO)
check("4za: a PYTHONPATH entry into production is refused", any("protected path" in e for e in pre()[0]))
os.environ.pop("PYTHONPATH")
write(repo / ".git" / "config", "x")
check("4zb: a .git directory appearing in the scratch repo is refused", any(".git" in e for e in pre()[0]))
shutil.rmtree(str(repo / ".git"))
write(repo / "ai_keys.env", "k")
check("4zc: a secrets file appearing in the scratch repo is refused", any("ai_keys.env" in e for e in pre()[0]))
(repo / "ai_keys.env").unlink()
write(repo / ".netrc", "machine x")
check("4zc2: a credential-style file (.netrc) appearing in the scratch repo is refused", any(".netrc" in e for e in pre()[0]))
(repo / ".netrc").unlink()
write(repo / "_site" / "index.html", "old")
check("4zd: a pre-existing _site is refused unless explicitly allowed", any("_site" in e for e in pre()[0]) and not pre(allow_existing_output=True)[0])
shutil.rmtree(str(repo / "_site"))
mk_path = root / "data" / name
saved = mk_path.read_text(); mk_path.unlink()
check("4ze: a missing scratch marker is an error", bool(pre()[0]))
mk_path.write_text(saved)
bad_layout = dict(layout, production_data_dir=str(root / "data"))
check("4zf: a layout whose production dir overlaps the scratch data dir is refused", bool(PF.preflight(bad_layout, tools_dir=layout["tools"])[0]))
check("4zg: running from a tools folder other than the layout's is refused", any("running from" in e for e in pre(tools_dir=str(TMP))[0]))
big = dict(layout, required_free_bytes=10 ** 18)
check("4zh: a disk requirement above the free space is refused, with the figures", any("GB free" in e and "needs" in e for e in PF.preflight(big, tools_dir=layout["tools"])[0]))
check("4zi: --min-free-gb can raise but never lower the requirement", any("GB free" in e for e in pre(min_free_gb=10 ** 9)[0]) and not any("GB free" in e for e in pre(min_free_gb=0)[0]))
moved = dict(layout, production_data_dir=str(mk("moved_prod")))
check("4zj: if the protected production dir no longer carries the marker (typo/unmounted), preflight refuses", any("production marker" in e for e in PF.preflight(moved, tools_dir=layout["tools"])[0]))
if can_link:
    mklink_dir(repo / "static" / "aliaslink", tgt)
    check("4zk: a symlink appearing inside the scratch tree is refused by preflight", any("symlink" in e for e in pre()[0]))
    C.remove_link_only(repo / "static" / "aliaslink")
os.environ.clear(); os.environ.update(OK_ENV)

print("5. production manifests: three-state result and baseline validation")
NOW = time.time()
snap = lambda **k: M.snapshot(str(PRODDATA), str(PRODREPO), hash_db=k.pop("hash_db", True), scratch_root=k.pop("scratch_root", None))
s1, s2 = snap(), snap()
d, u = M.compare(s1, s2)
if HAVE_GIT:
    check("5a: two snapshots of an unchanged tree are UNCHANGED and conclusive", d == [] and u == [], str((d, u)))
else:
    check("5a: (no git here) unchanged tree: no diffs, but inconclusive", d == [] and bool(u))
check("5b: snapshot records the db hash, file count, lock state and kind", len(s1["files"]["db"]["sha256"]) == 64 and s1["site"]["files"] == 2 and s1["files"]["pipeline_lock"]["exists"] is False and s1["kind"] == "production-baseline")
write(PRODREPO / "_site" / "data" / "new.json", "{}")
d, u = M.compare(s1, snap())
check("5c: a new file in the production _site is CHANGED", any("site." in x for x in d), str(d))
(PRODREPO / "_site" / "data" / "new.json").unlink()
os.utime(str(PRODREPO / "_site" / "index.html"), (1, 1))
check("5d: a changed mtime in _site is CHANGED", bool(M.compare(s1, snap())[0]))
write(PRODREPO / "_site" / "index.html", "<html>live</html>"); s1 = snap()
c = sqlite3.connect(str(LIVE)); c.execute("insert into events (title) values ('z')"); c.commit(); c.close()
check("5e: a change to the production database is CHANGED (size/mtime/hash)", any("db." in x for x in M.compare(s1, snap())[0]))
s1 = snap()
write(PRODREPO / ".pipeline.lock", "live\n1\n")
d, u = M.compare(s1, snap())
check("5f: appearance of the pipeline lock is CHANGED and flagged as inconclusive (production was active)", any("pipeline_lock" in x for x in d) and any("lock was present" in x for x in u))
(PRODREPO / ".pipeline.lock").unlink()
(PRODREPO / "_site.building").mkdir()
check("5g: appearance of _site.building is CHANGED", any("site_building" in x for x in M.compare(s1, snap())[0]))
(PRODREPO / "_site.building").rmdir()
s1 = snap()
nogit = json.loads(json.dumps(s1)); nogit["git_head"] = "unavailable"; nogit["git_status_digest"] = "unavailable"
d, u = M.compare(nogit, nogit)
check("5h: git unavailable on both sides is INCONCLUSIVE, never 'unchanged'", d == [] and any("git_head" in x for x in u) and any("git_status_digest" in x for x in u), str(u))
d, u = M.compare(s1, nogit)
check("5i: git unavailable on ONE side is also inconclusive (and does not invent a diff)", not any("git_head changed" in x for x in d) and any("unavailable" in x for x in u))
unhashed = snap(hash_db=False)
d, u = M.compare(unhashed, unhashed)
check("5j: neither snapshot hashed the database -> inconclusive with the reason", any("--hash-db" in x for x in u))
d, u = M.compare(unhashed, s1)
check("5k: mixed hashing settings -> inconclusive", any("different --hash-db" in x for x in u))
unreadable = json.loads(json.dumps(s1)); unreadable["files"]["db"] = {"exists": None, "error": "PermissionError"}
check("5l: an unreadable protected file makes the result inconclusive", any("could not be examined" in x for x in M.compare(unreadable, unreadable)[1]))
other = json.loads(json.dumps(s1)); other["production_repo"] = "C:\\somewhere\\else"
check("5m: snapshots of different production places are CHANGED (they cannot be compared)", any("different places" in x for x in M.compare(s1, other)[0]))
with __import__("contextlib").redirect_stdout(io.StringIO()) as cap:
    sp = TMP / "mf_unchanged.json"; json.dump(s1, open(str(sp), "w"))
    rc_ok = M.main(["compare", str(sp), str(sp)])
    sp2 = TMP / "mf_nogit.json"; json.dump(nogit, open(str(sp2), "w"))
    rc_inc = M.main(["compare", str(sp2), str(sp2)])
    sp3 = TMP / "mf_other.json"; json.dump(other, open(str(sp3), "w"))
    rc_chg = M.main(["compare", str(sp), str(sp3)])
out_text = cap.getvalue()
check("5n: CLI exit codes: 0 only when conclusive+unchanged, 3 inconclusive, 1 changed",
      (rc_ok == 0 if HAVE_GIT else True) and rc_inc == 3 and rc_chg == 1, "%s %s %s" % (rc_ok, rc_inc, rc_chg))
check("5o: the inconclusive output says it is NOT proof of no change", "NOT proof" in out_text or "not proof" in out_text.lower())
check("5p: --out inside the production repo is refused", M.main(["snapshot", "--out", str(PRODREPO / "m.json"), "--production-data-dir", str(PRODDATA), "--production-repo", str(PRODREPO)]) == 2 and not (PRODREPO / "m.json").exists())
check("5q: --scratch-root that is not a prepared root is refused", M.main(["snapshot", "--out", str(TMP / "m2.json"), "--production-data-dir", str(PRODDATA), "--production-repo", str(PRODREPO), "--scratch-root", str(TMP)]) == 2)
if HAVE_GIT:
    g1_, g2_ = snap(), (write(PRODREPO / "untracked.txt", "u") and snap())
    check("5r: an untracked file in the production repo changes the git-status digest", g1_["git_status_digest"] != g2_["git_status_digest"])
    (PRODREPO / "untracked.txt").unlink()
    idx = (PRODREPO / ".git" / "index"); before_idx = idx.stat().st_mtime_ns
    snap()
    check("5s: snapshotting did not create .git/index.lock or touch the index (--no-optional-locks)", not (PRODREPO / ".git" / "index.lock").exists() and idx.stat().st_mtime_ns == before_idx)
tm = (TOOLS / "scratch_manifest.py").read_text(encoding="utf-8")
check("5t: the only git subcommands the manifest tool can run are rev-parse and status", set(re.findall(r'_git\(\s*\w+,\s*"([a-z-]+)"', tm)) == {"rev-parse", "status"})

print("5b. the BEFORE manifest must be a meaningful baseline for THIS scratch run")
bound = M.snapshot(str(PRODDATA), str(PRODREPO), hash_db=True, scratch_root=str(root))
bp = TMP / "baseline.json"
def vb(m, **k):
    p = TMP / "vb.json"; p.write_text(json.dumps(m), encoding="utf-8")
    return M.validate_baseline(str(p), layout, now=k.pop("now", time.time()), **k)
if HAVE_GIT:
    check("5b-a: a fresh, bound, hashed baseline from a git-readable production is accepted", vb(bound) == [], str(vb(bound)))
mut = lambda **ch: dict(json.loads(json.dumps(bound)), **ch)
check("5b-b: an UNBOUND snapshot (no --scratch-root) is refused", any("not bound" in x for x in vb(mut(scratch_root=None, scratch_token=None))))
check("5b-c: a snapshot bound to ANOTHER scratch root/token is refused", any("not bound" in x for x in vb(mut(scratch_token="0" * 32))))
check("5b-d: a snapshot of different production paths is refused", any("production_repo" in x for x in vb(mut(production_repo="C:\\elsewhere"))) and any("production_data_dir" in x for x in vb(mut(production_data_dir="D:\\x"))))
check("5b-e: a stale baseline (by its own timestamp, not file mtime) is refused", any("hours old" in x for x in vb(bound, now=time.time() + 13 * 3600)))
check("5b-f: a baseline dated in the future is refused", any("future" in x for x in vb(mut(taken_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 7200))))))
check("5b-g: a missing/garbled timestamp is refused", any("timestamp" in x for x in vb(mut(taken_utc="yesterday"))))
unh = json.loads(json.dumps(bound)); unh["files"]["db"].pop("sha256")
check("5b-h: no database hash is refused by default, and accepted only with the explicit weaker flag", any("--hash-db" in x for x in vb(unh)) and not any("--hash-db" in x for x in vb(unh, require_hash=False)))
nodb = json.loads(json.dumps(bound)); nodb["files"]["db"] = {"exists": False}
check("5b-i: a baseline that does not show a production database is refused", any("existing production database" in x for x in vb(nodb)))
nosite = json.loads(json.dumps(bound)); nosite["site"] = {"exists": False}
check("5b-j: a baseline that does not show a populated _site is refused", any("_site" in x for x in vb(nosite)))
ng = json.loads(json.dumps(bound)); ng["git_head"] = "unavailable"
check("5b-k: a baseline with git unavailable is refused (it could only ever be inconclusive)", any("git_head" in x for x in vb(ng)))
lk = json.loads(json.dumps(bound)); lk["files"]["pipeline_lock"] = {"exists": True}
check("5b-l: a baseline taken while a pipeline lock existed is refused", any("pipeline lock" in x for x in vb(lk)))
check("5b-m: wrong version / kind is refused", any("version" in x for x in vb(mut(manifest_version=1))) and any("version" in x for x in vb(mut(kind="other"))))
check("5b-n: a non-JSON / empty / array file is refused, not crashed on",
      all(M.validate_baseline(str(p), layout) for p in (write(TMP / "e1.json", ""), write(TMP / "e2.json", "[]"), write(TMP / "e3.json", "{nope"), TMP / "does_not_exist.json")))
check("5b-o: an empty JSON object (what a freshly touched file would be) is refused with several reasons", len(vb({})) >= 5)

print("6. cleanup removes only a verified scratch root")
c_root = TMP / "work" / "to_delete"
INIT(c_root)
neighbour = write(TMP / "work" / "neighbour.txt", "keep")
check("6a: cleanup refuses when --confirm-path differs", "exact" in (refuses(P.cleanup, str(c_root), str(c_root) + "x") or "") and c_root.exists())
check("6b: cleanup refuses a folder with no sentinel", why(refuses(P.cleanup, str(TMP / "mf"), str(TMP / "mf")), "not a prepared scratch root"))
check("6c: cleanup refuses a shallow path", why(refuses(P.cleanup, "/tmp", "/tmp"), "this shallow"))
write(c_root / "surprise.docx", "personal file")
check("6d: cleanup refuses a root containing unknown items", "unexpected" in (refuses(P.cleanup, str(c_root), str(c_root)) or "") and c_root.exists())
(c_root / "surprise.docx").unlink()
tampered = json.loads((c_root / "scratch_layout.json").read_text()); tampered["production_data_dir"] = str(c_root / "data")
(c_root / "scratch_layout.json").write_text(json.dumps(tampered))
check("6e: cleanup refuses when the sentinel claims production lies inside the root", "overlaps" in (refuses(P.cleanup, str(c_root), str(c_root)) or ""))
tampered["production_data_dir"] = str(PRODDATA); tampered["protected_roots"] = list(tampered["protected_roots"]) + [str(c_root / "logs")]
(c_root / "scratch_layout.json").write_text(json.dumps(tampered))
check("6f: cleanup also honours the EXTRA protected roots recorded in the sentinel", "overlaps" in (refuses(P.cleanup, str(c_root), str(c_root)) or ""))
tampered["protected_roots"] = [r for r in tampered["protected_roots"] if r != str(c_root / "logs")]
(c_root / "scratch_layout.json").write_text(json.dumps(tampered))
if can_link:
    vict = mk("cleanup_victim"); write(vict / "important.txt", "important")
    mklink_dir(c_root / "tmp", vict)
    r = refuses(P.cleanup, str(c_root), str(c_root))
    check("6g: a symlink INSIDE the root makes cleanup refuse before deleting anything", why(r, str(c_root / "tmp"), "inside the scratch root", "Nothing was deleted") and not any(w in r for w in ("sits under", "overlaps", "unexpected item")) and c_root.exists() and (c_root / "repo").exists() and (vict / "important.txt").exists(), str(r))
    C.remove_link_only(c_root / "tmp")
    lr = TMP / "work" / "linked_root_alias"; mklink_dir(lr, c_root)
    check("6h: cleanup via a symlinked path to the root is refused", why(refuses(P.cleanup, str(lr), str(lr)), "is, or sits under") and c_root.exists() and (c_root / "repo").exists())
    C.remove_link_only(lr)
os.lstat = fake_lstat
fake_target = str(c_root / "logs" / "reparse_dir"); os.mkdir(fake_target)
try:
    r = refuses(P.cleanup, str(c_root), str(c_root))
finally:
    os.lstat = real_lstat
check("6i: [junction simulation] a directory presenting the reparse attribute inside the root makes cleanup refuse", why(r, fake_target, "inside the scratch root", "reparse") and c_root.exists() and os.path.isdir(fake_target), str(r))
os.rmdir(fake_target)
check("6j: cleanup of a verified, link-free root succeeds", P.cleanup(str(c_root), str(c_root)) is True and not c_root.exists())
check("6k: ...and touched nothing outside it (neighbour file, backup, live db, source repo, link target)",
      neighbour.exists() and BACKUP.exists() and LIVE.exists() and (SRC / "export_static.py").exists() and (not can_link or (vict / "important.txt").exists()))

print("7. output encoding, OG-card analysis, measurement helpers")
class Cp1252Console(io.TextIOWrapper):
    pass
raw = io.BytesIO()
console = io.TextIOWrapper(raw, encoding="cp1252", errors="strict", write_through=True)
HINDI = "\u092a\u0915\u094d\u0937 \u0938\u092e\u093e\u091a\u093e\u0930"
try:
    console.write(HINDI); before_ok = True
except UnicodeEncodeError:
    before_ok = False
check("7a: [control] a cp1252 stdout really cannot print Devanagari (the failure being prevented)", before_ok is False)
raw2 = io.BytesIO(); c2 = io.TextIOWrapper(raw2, encoding="cp1252", errors="strict", write_through=True)
left = MX.configure_output(c2)
try:
    c2.write(HINDI); c2.flush(); wrote = True
except UnicodeEncodeError:
    wrote = False                      # report a FAIL, don't crash the whole suite
check("7b: after configure_output the same stream prints it as UTF-8 without raising", left == [] and wrote and raw2.getvalue().decode("utf-8") == HINDI)
check("7c: a stream without reconfigure is reported back for wrapping", MX.configure_output(object()) != [])
raw3 = io.BytesIO(); c3 = io.TextIOWrapper(raw3, encoding="ascii", errors="strict")
logbuf = io.StringIO(); tee = MX.Tee(c3, logbuf, 0.0, clock=lambda: 12.5)
tee.write("headline \u092a\u0915\u094d\u0937 done\nsecond"); tee.close_partial(); tee.flush()
check("7d: Tee never raises on an unencodable character (replaces it) and keeps the full text in the log",
      raw3.getvalue().startswith(b"[+    12.5s] headline ") and "\u092a\u0915\u094d\u0937" in logbuf.getvalue() and logbuf.getvalue().count("\n") == 2)
check("7e: Tee prefixes elapsed time", logbuf.getvalue().startswith("[+    12.5s] headline"))
OGL = lambda *ls: MX.analyze_og(list(ls))
check("7f: all cards written -> complete", OGL("  [og] 1500/1500 share cards written in 312.4s")["status"] == "complete")
check("7g: fewer written than expected -> partial", OGL("  [og] 1400/1500 share cards written in 300.0s")["status"] == "partial")
check("7h: Pillow/fontTools missing ('skipped') -> skipped, with the line kept", OGL("  [og] share cards skipped (ModuleNotFoundError: fontTools); story pages fall back to their own photo")["status"] == "skipped"
      and OGL("  [og] share cards skipped (x)")["issues"])
check("7i: batch failure -> failed", OGL("  [og] story card batch failed (OSError: disk); story pages fall back")["status"] == "failed")
check("7j: root card failure with cards written -> partial, never complete", OGL("  [og] root card failed: boom", "  [og] 10/10 share cards written in 1.0s")["status"] == "partial")
check("7k: OG_CARD_N=0 -> disabled", OGL("  [og] story cards disabled (OG_CARD_N=0)")["status"] == "disabled")
check("7l: no [og] line at all -> unknown (never treated as success)", OGL("something else")["status"] == "unknown")
check("7m: zero expected / zero written -> partial, not complete", OGL("  [og] 0/0 share cards written in 0.0s")["status"] == "partial")
check("7n: benchmark verdict: full run needs complete cards", MX.benchmark_verdict("full", OGL("  [og] 5/5 share cards written in 1.0s"))[0]
      and not MX.benchmark_verdict("full", OGL("  [og] share cards skipped (x)"))[0] and not MX.benchmark_verdict("full", OGL("nothing"))[0]
      and not MX.benchmark_verdict("full", OGL("  [og] 4/5 share cards written in 1.0s"))[0])
check("7o: benchmark verdict: no-og-cards variant needs the step to be disabled (cards present would be a mislabelled run)",
      MX.benchmark_verdict("no-og-cards", OGL("  [og] story cards disabled (OG_CARD_N=0)"))[0] and not MX.benchmark_verdict("no-og-cards", OGL("  [og] 5/5 share cards written in 1.0s"))[0])
check("7p: a failed/partial verdict carries the exporter's own message as a reason", any("exporter said" in r for r in MX.benchmark_verdict("full", OGL("  [og] share cards skipped (boom)"))[1]))
ts_ = MX.tree_stats(TMP / "mf")
check("7q: tree_stats and peak_memory_bytes return sane values", ts_["files"] >= 0 and (MX.peak_memory_bytes() or 1) > 0)

print("8. static properties of the tooling and its documentation")
srcs = {f.name: f.read_text(encoding="utf-8") for f in TOOLS.glob("*.py")}
for fn, t in srcs.items():
    ast.parse(t, feature_version=(3, 9))
check("8a: all tool scripts parse under the Python 3.9 grammar (SYNTAX only; not executed on 3.9)", True)
exp = srcs["scratch_export.py"]
check("8b: the launcher loads the layout (and so refuses to run from the production repo) before importing export_static", exp.index("load_layout(HERE)") < exp.index("import export_static as ex"))
check("8c: the typed DB path and the validated baseline are required BEFORE the environment or guard is touched",
      exp.index("--confirm-db-path must name") < exp.index("guard.install()") and exp.index("validate_baseline(") < exp.index("guard.install()")
      and exp.index("validate_baseline(") < exp.index('os.environ["PAKSH_DATA_DIR"]'))
check("8d: the guard is installed before export_static is imported", exp.index("guard.install()") < exp.index("import export_static as ex"))
check("8e: output is made Unicode-safe before the guard/tee are installed", exp.index("configure_output(") < exp.index("guard.install()"))
check("8f: the launcher defaults to plan-only", "default: plan only" in exp and "if not a.run:" in exp)
check("8g: exit code 4 exists for a completed-but-invalid benchmark, 1 for a violation or failure", "return 0 if metrics[\"benchmark_valid\"] else 4" in exp and "if status != \"completed\" or guard.violations:" in exp)
nolive = {k: v.split('"""', 2)[-1] for k, v in srcs.items()}
nolive["scratch_prepare.py"] = nolive["scratch_prepare.py"].replace("live.py", "").replace("live = pr / \"\"", "live = pr / \"live\"")
check("8h: no tool references publishing/pipeline entry points (live.py is only READ as text, by the production-path cross-check)",
      not any(re.search(r"safe_autopush|refresh\.py|runlocked|live\.py|git (push|commit|add)|\"push\"|\"commit\"", t) for t in nolive.values()))
check("8i: no tool disables or edits a production guard",
      not any(re.search(r"PAKSH_ALLOW_NEW_DB\s*=|PAKSH_ALLOW_EXPORT_COLLAPSE\s*=|require_production\s*=|monkeypatch", t) for t in srcs.values())
      and "os.environ.pop(k, None)" in exp)
check("8j: the production-path cross-check only READS live.py (no write/exec of it)", re.search(r'live\.read_text', srcs["scratch_prepare.py"]) is not None
      and not re.search(r"live\.(write|unlink|chmod)|open\(live", srcs["scratch_prepare.py"]))
top_level_imports = set()
for fn, tsrc in srcs.items():
    for node in ast.parse(tsrc).body:
        if isinstance(node, ast.Import):
            top_level_imports |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            top_level_imports.add(node.module.split(".")[0])
check("8k: no tool module imports a pipeline module at import time (export_static is imported only inside main; "
      "paksh_paths/database only inside the preflight's subprocess probe)",
      not (top_level_imports & {"export_static", "database", "paksh_paths", "analyze", "live", "refresh", "ingest", "cluster"}), str(sorted(top_level_imports)))
check("8l: the exporter and every protected pipeline/deployment file are untouched in the working tree",
      subprocess.run(["git", "diff", "--quiet", "HEAD", "--", "export_static.py", "live.py", "runlocked.py", "safe_autopush.py", "refresh.py",
                      "paksh_paths.py", "database.py", "og_images.py", "og_images_hi.py", "homepage_rank.py", "section_rank.py",
                      "static", "_site", "refresh_scheduled.bat", "reframe_scheduled.bat", "refresh.bat", ".github"], cwd=str(ROOT)).returncode == 0)

doc = (ROOT / "docs" / "EDITORIAL_WINDOWS_SCRATCH_TEST.md").read_text(encoding="utf-8")
ex_paths = re.findall(r'\$Scratch\s*=\s*"([^"]+)"', doc)
check("8m: the documentation gives a $Scratch example", bool(ex_paths))
check("8n: [win-lexical] every documented $Scratch example is absolute and deep enough for the REAL depth check",
      all(ntpath.isabs(p) and C.depth(p, ntpath) >= C.MIN_DEPTH for p in ex_paths), str([(p, C.depth(p, ntpath)) for p in ex_paths]))
check("8o: no stale example path from the earlier draft remains anywhere in the doc", "paksh_scratch\\run1" not in doc.replace("editorial_test\\run1", ""))
check("8p: the documented example is not under either documented production path",
      all(not C.overlaps(p, "D:\\Paksh_Data", mod=ntpath) and not C.overlaps(p, "C:\\paksh_project\\paksh", mod=ntpath) for p in ex_paths))
flags_in_code = set()
for fn, t in srcs.items():
    flags_in_code |= set(re.findall(r'add_argument\(\s*"(--[a-z0-9-]+)"', t))
flags_in_code |= set(re.findall(r'add_argument\(\s*"(--[a-z0-9-]+)"', (ROOT / "test_editorial_scratch_windows.py").read_text(encoding="utf-8")))   # the self-test's own parser
flags_in_code |= {"--" + x for x in ("scratch-root", "source-repo", "backup-file", "production-data-dir", "production-repo")}
used = set()
for line in doc.splitlines():
    if re.match(r"\s*(py|\$)\s", line) or "scratch_" in line:
        used |= set(re.findall(r"(?<![\w-])(--[a-z][a-z0-9-]*)", line))
used -= {"--allow", "--no-optional-locks"}
check("8q: every --flag the documentation tells the operator to type exists in a tool's argument parser", used <= flags_in_code, str(sorted(used - flags_in_code)))
check("8r: the doc no longer promises a byte-for-byte/'exactly as typed' confirmation", "character for character" not in doc and "exactly as typed" not in doc)
check("8s: the doc describes the three-state manifest result and the baseline binding", "INCONCLUSIVE" in doc and "--scratch-root" in doc and "bound" in doc)
check("8t: the doc states the disk formula that the code enforces", "2 x" in doc and "backup" in doc.lower() and "headroom" in doc.lower())
check("8u: the doc separates verified / Linux-tested / Windows-unverified properties", all(k in doc for k in ("Code-verified", "Linux-tested", "Windows-unverified")))
check("8v: the doc names the Windows self-test and exit code 4", "test_editorial_scratch_windows.py" in doc and "exit code 4" in doc.lower() or "`4`" in doc)

shutil.rmtree(str(TMP), ignore_errors=True)
print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("=" * 60)
print("ALL EDITORIAL SCRATCH-TOOLING CHECKS PASSED")
