"""
test_editorial_scratch_windows.py - Windows-ONLY self-test for the scratch tooling.

STATUS: WRITTEN BUT NEVER RUN ON WINDOWS. On any other platform running it prints SKIPPED and runs
zero checks (exit code 0 then means "nothing was checked", NOT "passed" - read the banner).

It exists because these properties cannot be verified on Linux:
  * a real NTFS junction / directory symlink is seen as a link (is_link_or_reparse, links_in_tree,
    walk_nolinks, linked_ancestors), makes `cleanup` refuse WITHOUT deleting through it, and is
    detached (never traversed) when this test removes its own temp folders;
  * Windows path normalisation of real paths: case, `\\\\?\\` prefix, 8.3 short names, the local
    administrative-share alias, and a `subst` drive letter;
  * the REAL shape of the subprocess.Popen audit event on Windows (flattened command line,
    executable=None) as seen by the real hook, including that a legitimate `node` launch is allowed
    and a `cmd.exe /c` launch is refused;
  * the psapi peak-memory reading, and UTF-8 output under a cp1252 pipe.

SAFE: it only creates folders and files under a fresh folder inside %TEMP% (or the folder given with
--base), plus one `subst` drive mapping that it removes again. It never touches Paksh paths, never
runs an export, never starts the launcher, and needs no network. Run it from the repo checkout that
holds tools/ on the Windows machine:

    py test_editorial_scratch_windows.py [--base C:\\some\\ordinary\\folder]

HOW IT AVOIDS PASSING FOR THE WRONG REASON
  * Every "X is refused / detected" check has a CONTROL that proves the same fixture is accepted /
    not flagged when the junction is absent, so a refusal can only be due to the junction.
  * The junction/cleanup sections run only if the temp base and ALL its ancestors are ordinary
    directories. If %TEMP% (or an ancestor) is a junction, symlink or other reparse point, those
    sections are reported as an explicit REQUIRED SKIP (exit code 3, "INCOMPLETE") and the redirect
    is printed; rerun with --base pointing at an ordinary folder.
  * Refusal checks assert the SPECIFIC message (names the junction path and the "inside the scratch
    root" rule), not just the word "symlink".
  * Link targets live in a separate DECOY folder; after cleanup the decoy files must still exist,
    which proves nothing was deleted through a link.

EXIT CODES   0 every check ran and passed | 1 a check failed | 3 incomplete: a required section was
skipped (redirected temp, junction could not be created). 3 is NOT a pass.

Send back the complete output. Any FAIL, or any SKIPPED line that is not explained, is a finding.
"""
import argparse
import collections
import ctypes
import json
import ntpath
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import textwrap
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOOLS = ROOT / "tools" / "editorial_scratch"
PREFIX = "paksh_win_selftest_"

sys.dont_write_bytecode = True
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import scratch_common as C          # noqa: E402
import scratch_guard as G           # noqa: E402
import scratch_metrics as MX        # noqa: E402
import scratch_prepare as P         # noqa: E402


# ----------------------------------------------------------------------------------------
# reporting
# ----------------------------------------------------------------------------------------

class Report:
    """Collects results. `required` skips make the run INCOMPLETE (exit 3)."""

    def __init__(self, out=print):
        self.out = out
        self.ran = []
        self.failures = []
        self.skips = []              # (label, why, required)

    def check(self, label, cond, detail=""):
        cond = bool(cond)
        self.ran.append(label)
        self.out("  %s ... %s%s" % (label, "OK" if cond else "FAIL", ("  (%s)" % detail) if detail and not cond else ""))
        if not cond:
            self.failures.append(label)
        return cond

    def skip(self, label, why, required=False):
        self.out("  %s ... SKIPPED%s (%s)" % (label, " [REQUIRED - run is INCOMPLETE]" if required else "", why))
        self.skips.append((label, why, required))

    def note(self, text):
        self.out("     " + text)

    @property
    def incomplete(self):
        return any(r for _, _, r in self.skips)

    def exit_code(self):
        return 1 if self.failures else (3 if self.incomplete else 0)


LinkOps = collections.namedtuple("LinkOps", "kind real_junction make remove")


def windows_link_ops():
    """Real NTFS junctions via `mklink /J`; removal via `rmdir` WITHOUT /s (the documented operator step)."""
    def make(link, target):
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True)
        return r.returncode == 0, (r.stderr or r.stdout).strip()[:120]

    def remove(link):
        subprocess.run(["cmd", "/c", "rmdir", str(link)], capture_output=True, text=True)
    return LinkOps("NTFS junction (mklink /J)", True, make, remove)


def posix_link_ops():
    """STAND-IN for the Linux logic tests only: a POSIX symlink. It is NOT a junction."""
    def make(link, target):
        try:
            os.symlink(str(target), str(link), target_is_directory=True)
            return True, ""
        except OSError as e:
            return False, str(e)

    def remove(link):
        os.unlink(str(link))
    return LinkOps("POSIX symlink stand-in (NOT a junction)", False, make, remove)


# ----------------------------------------------------------------------------------------
# 0. the temp base must be ordinary, or the junction checks could pass for the wrong reason
# ----------------------------------------------------------------------------------------

def inspect_base(base):
    base = os.path.abspath(str(base))
    linked = C.linked_ancestors(base)
    try:
        resolved = os.path.realpath(base)
    except OSError:
        resolved = base
    norm = lambda p: os.path.normcase(os.path.normpath(p))          # noqa: E731
    elsewhere = norm(resolved) != norm(C._long_path(base))
    return {"base": base, "resolved": resolved, "linked_ancestors": linked, "resolves_elsewhere": elsewhere}


def gate_base(R, base):
    """True if the junction/cleanup sections may run. Reports redirected temp roots explicitly."""
    info = inspect_base(base)
    R.note("temp base            : %s" % info["base"])
    R.note("resolves to          : %s%s" % (info["resolved"], "   <-- differs (8.3 name, subst, mapped drive or redirect)" if info["resolves_elsewhere"] else ""))
    R.note("link/reparse ancestors: %s" % (info["linked_ancestors"] or "none"))
    if info["linked_ancestors"]:
        R.skip("1-2 (junction + cleanup sections)",
               "the temp base is, or sits under, a symlink/junction/reparse point (%s). A cleanup refusal would then come from "
               "THAT ancestor, not from the junction under test, so the result would be meaningless. Rerun with "
               "--base <an ordinary folder on a normal local drive>" % info["linked_ancestors"][0], required=True)
        return False
    R.check("0a: the temp base and every ancestor are ordinary directories (no link/junction/reparse point)", True)
    return True


def make_workspace(base, prefix=PREFIX):
    tmp = Path(tempfile.mkdtemp(prefix=prefix, dir=str(base)))
    decoy = Path(tempfile.mkdtemp(prefix=prefix + "decoy_", dir=str(base)))
    return tmp, decoy


# ----------------------------------------------------------------------------------------
# 1. link detection
# ----------------------------------------------------------------------------------------

def section_links(R, tmp, decoy, ops):
    """Returns True if a link could be created and the section ran."""
    target = decoy / "target_dir"; target.mkdir()
    keep = target / "keep.txt"; keep.write_text("keep")
    inner = decoy / "inner_target"; inner.mkdir(); (inner / "keep2.txt").write_text("keep2")
    box = tmp / "box"; box.mkdir()
    R.check("1-ctl-a: BEFORE any link exists links_in_tree(box) is empty (the detector is not always-true)", C.links_in_tree(box) == [], str(C.links_in_tree(box)))
    R.check("1-ctl-b: ...and no ancestor of box is a link", C.linked_ancestors(box) == [], str(C.linked_ancestors(box)))
    R.check("1-ctl-c: a plain directory and a plain file are not reported as links", not C.is_link_or_reparse(target) and not C.is_link_or_reparse(keep))
    j = box / "junction"
    ok, detail = ops.make(j, target)
    if not ok:
        R.skip("1a-g", "could not create a %s: %s" % (ops.kind, detail), required=True)
        return False
    nested = target / "nested_link"
    ok_n, detail_n = ops.make(nested, inner)
    (target / "after_link.txt").write_text("created after the link")
    R.check("1-live: the link is a live view of the target (a file created later is visible through it), not a copied folder",
            (j / "after_link.txt").exists() and _text(j / "keep.txt") == "keep")
    if ops.real_junction:
        st = os.lstat(str(j))
        R.check("1a: an NTFS junction carries the reparse-point attribute", C.attrs_is_reparse(st), "st_file_attributes=%r" % getattr(st, "st_file_attributes", None))
        R.note("os.path.islink(junction) = %s  (False is expected: this is why detection must use the reparse attribute)" % os.path.islink(str(j)))
    else:
        R.skip("1a", "attribute check applies to real NTFS junctions only; UNVERIFIED on this platform")
    R.check("1b: is_link_or_reparse sees the link", C.is_link_or_reparse(j))
    R.check("1c: links_in_tree(box) is EXACTLY [the link]: it does not descend into it (a nested link inside the target would otherwise be listed too)",
            ok_n and C.links_in_tree(box) == [str(j)], "%s nested_created=%s %s" % (C.links_in_tree(box), ok_n, detail_n))
    seen_files, seen_links = [], []
    for dp, dn, fn, lk in C.walk_nolinks(box):
        seen_files += fn; seen_links += lk
    R.check("1c2: walk_nolinks reports the link and shows NONE of the target's files", seen_links == [str(j)] and not seen_files, "files=%s links=%s" % (seen_files, seen_links))
    R.check("1d: linked_ancestors of a path beneath the link is EXACTLY [the link]", C.linked_ancestors(j / "keep.txt") == [str(j)], str(C.linked_ancestors(j / "keep.txt")))
    R.check("1d2: control - a path in the same box but not beneath the link has no linked ancestor", C.linked_ancestors(box / "plain.txt") == [])
    R.check("1e: detection left the targets untouched", _text(keep) == "keep" and _text(inner / "keep2.txt") == "keep2")
    if ops.real_junction:
        dl = box / "dirsymlink"
        try:
            os.symlink(str(target), str(dl), target_is_directory=True)
            R.check("1f: a directory symlink is seen as a link", C.is_link_or_reparse(dl))
        except OSError as e:
            R.skip("1f", "symlink creation needs privilege/Developer Mode: %s" % e)
    return True


# ----------------------------------------------------------------------------------------
# 2. cleanup decisions
# ----------------------------------------------------------------------------------------

def make_scratch_root(parent, label, prod_a, prod_b):
    root = Path(parent) / label / "a" / "scratch_root"
    root.mkdir(parents=True)
    (root / "scratch_layout.json").write_text(json.dumps({"scratch_root": str(root), "production_data_dir": str(prod_a),
                                                          "production_repo": str(prod_b), "protected_roots": []}))
    (root / "repo").mkdir()
    (root / "repo" / "f.txt").write_text("x")
    return root


def _text(p):
    """File text, or None if it cannot be read: a deleted/missing file must make a check FAIL, not crash it."""
    try:
        return Path(p).read_text()
    except OSError:
        return None


def _call(fn, *a):
    try:
        return fn(*a), None
    except BaseException as e:              # noqa: BLE001 - the exception IS the datum
        return None, e


def section_cleanup(R, tmp, decoy, ops, cleanup_fn=None):
    cleanup_fn = cleanup_fn or P.cleanup
    prod_a, prod_b = tmp / "prod_data", tmp / "prod_repo"
    victim = decoy / "cleanup_target"; victim.mkdir(); (victim / "keep.txt").write_text("victim")
    ctl = make_scratch_root(tmp, "ctl", prod_a, prod_b)
    R.check("2-pre-a: the control root is deep enough for the real depth rule", C.depth(ctl) >= C.MIN_DEPTH, str(C.depth(ctl)))
    R.check("2-pre-b: the control root has no link inside and no link ancestor", C.links_in_tree(ctl) == [] and C.linked_ancestors(ctl) == [])
    res, err = _call(cleanup_fn, str(ctl), str(ctl))
    R.check("2-ctl: the IDENTICAL layout WITHOUT a junction is accepted and removed (so a refusal below can only be due to the junction)",
            res is True and not ctl.exists(), repr(err))

    bad = make_scratch_root(tmp, "bad", prod_a, prod_b)
    jj = bad / "data"
    ok, detail = ops.make(jj, victim)
    if not ok:
        R.skip("2", "could not create the second link: %s" % detail, required=True)
        return False
    R.check("2-pre-c: the link is inside the root and the root itself is not under a link", C.links_in_tree(bad) == [str(jj)] and C.linked_ancestors(bad) == [],
            "links=%s ancestors=%s" % (C.links_in_tree(bad), C.linked_ancestors(bad)))
    res, err = _call(cleanup_fn, str(bad), str(bad))
    msg = str(err) if err is not None else ""
    R.check("2a: cleanup refuses with a Refusal (not another exception, not success)", isinstance(err, C.Refusal) and res is None, repr(err))
    R.check("2a2: ...for THE intended reason: the message names this very junction and the 'inside the scratch root' rule and says nothing was deleted",
            str(jj) in msg and "inside the scratch root" in msg and "Nothing was deleted" in msg, msg[:300])
    R.check("2a3: ...and NOT for a different reason (ancestor link, overlap, unknown item, confirm-path, sentinel)",
            not any(w in msg for w in ("sits under", "overlaps", "unexpected item", "--confirm-path", "sentinel", "shallow", "not a prepared")), msg[:300])
    R.check("2a4: nothing was deleted: root files, the junction and the junction's target all still exist",
            (bad / "repo" / "f.txt").exists() and (bad / "scratch_layout.json").exists() and C.is_link_or_reparse(jj)
            and _text(victim / "keep.txt") == "victim" and (jj / "keep.txt").exists())
    ops.remove(jj)
    R.check("2b: after removing the junction (`rmdir`, no /s) the link is gone and the target still exists", not os.path.lexists(str(jj)) and _text(victim / "keep.txt") == "victim")
    res, err = _call(cleanup_fn, str(bad), str(bad))
    R.check("2c: with the junction gone, cleanup succeeds and the old target is still intact", res is True and not bad.exists() and (victim / "keep.txt").exists(), repr(err))

    # the scratch root path ITSELF is a link
    real_root = make_scratch_root(tmp, "real2", prod_a, prod_b)
    root_link = tmp / "rootlink"
    ok, detail = ops.make(root_link, real_root)
    if not ok:
        R.skip("2d", "could not create the root-level link: %s" % detail, required=True)
        return True
    layout = json.loads((real_root / "scratch_layout.json").read_text())
    layout["scratch_root"] = str(root_link)             # so `same(sentinel, root)` cannot be the reason for refusing
    (real_root / "scratch_layout.json").write_text(json.dumps(layout))
    res, err = _call(cleanup_fn, str(root_link), str(root_link))
    msg = str(err) if err is not None else ""
    R.check("2d: cleanup of a path that IS a link to the scratch root refuses, for the 'is, or sits under, a link' reason, and deletes nothing",
            isinstance(err, C.Refusal) and "is, or sits under" in msg and (real_root / "repo" / "f.txt").exists() and (real_root / "scratch_layout.json").exists(), msg[:300])
    ops.remove(root_link)
    return True


# ----------------------------------------------------------------------------------------
# 9. the self-test's own cleanup: never traverses or deletes through a link
# ----------------------------------------------------------------------------------------

def cleanup_selftest(R, tmp, decoy, base, ops, prefix=PREFIX, rmtree_fn=None):
    rmtree_fn = rmtree_fn or C.safe_rmtree
    tmp, decoy, base = Path(tmp), Path(decoy), Path(base)
    for name, p in (("temp folder", tmp), ("decoy folder", decoy)):
        sane = p.name.startswith(prefix) and C.same(p.parent, base) and not C.is_link_or_reparse(p)
        if not R.check("9-pre: the %s is one this test created (name prefix, direct child of the base, not a link)" % name, sane, str(p)):
            R.note("NOT deleting %s; remove it by hand after checking it. Do not use `rmdir /s` if it contains a junction." % p)
            return False
    final_target = decoy / "final_target"; final_target.mkdir(); (final_target / "keep_final.txt").write_text("final")
    leftover = tmp / "leftover_link"
    made, detail = ops.make(leftover, final_target)
    if made:
        R.check("9-pre-link: a link is deliberately left inside the temp folder for the final cleanup to deal with", C.links_in_tree(tmp) != [], str(C.links_in_tree(tmp)))
    else:
        R.skip("9-link", "could not create the leftover link: %s" % detail, required=True)
    before = sorted(os.path.join(dp, f) for dp, _d, fns, _l in C.walk_nolinks(decoy) for f in fns)     # every decoy file, listed BEFORE cleanup
    R.check("9-pre-files: the decoy holds files to protect (the check below is not vacuous)", len(before) >= 1, str(before))
    n, err = _call(rmtree_fn, str(tmp), "detach")
    R.check("9a: the temp folder is removed", err is None and not tmp.exists(), repr(err))
    R.check("9b: links inside it were DETACHED (counted), not followed", err is None and ((n is not None and n >= 1) if made else True), "detached=%r" % (n,))
    missing = [f for f in before if not os.path.exists(f)]
    R.check("9c: NOTHING was deleted through a link: every decoy file that existed before the cleanup still exists", not missing, "missing: %s" % missing)
    n2, err2 = _call(rmtree_fn, str(decoy), "detach")
    R.check("9d: the decoy folder (which holds a nested link) is removed too, after the check above", err2 is None and not decoy.exists(), repr(err2))
    R.check("9e: CLEANUP STATUS - both self-test folders are gone", not tmp.exists() and not decoy.exists(), "tmp=%s decoy=%s" % (tmp.exists(), decoy.exists()))
    if tmp.exists() or decoy.exists():
        R.note("leftover for manual removal (use `rmdir` on any junction first, never `rmdir /s` through one): %s %s" %
               (tmp if tmp.exists() else "", decoy if decoy.exists() else ""))
    return True


# ----------------------------------------------------------------------------------------
# 3. path normalisation on real paths
# ----------------------------------------------------------------------------------------

def section_paths(R, tmp):
    sysroot = os.environ.get("SystemRoot", "C:\\Windows")
    R.check("3a: case-insensitive", C.same(sysroot.lower(), sysroot.upper()))
    R.check("3b: \\\\?\\ prefix", C.same("\\\\?\\" + sysroot, sysroot))
    R.check("3c: forward slashes", C.same(sysroot.replace("\\", "/"), sysroot))
    drive = ntpath.splitdrive(sysroot)[0]
    R.check("3d: local administrative share alias \\\\localhost\\C$\\Windows", C.same("\\\\localhost\\%s$%s" % (drive[0], sysroot[2:]), sysroot),
            "if admin shares are disabled this alias cannot be opened but should still compare equal lexically")
    R.check("3-neg: controls - two different folders are NOT the same, with or without the prefix", not C.same(sysroot, tmp) and not C.same("\\\\?\\" + str(tmp), sysroot))
    long_dir = tmp / "A_Very_Long_Directory_Name_For_8dot3"; long_dir.mkdir(); (long_dir / "f.txt").write_text("x")
    buf = ctypes.create_unicode_buffer(1024)
    n = ctypes.windll.kernel32.GetShortPathNameW(str(long_dir), buf, 1024)
    if n and buf.value and buf.value.lower() != str(long_dir).lower():
        R.check("3e: an 8.3 short-name alias of a real folder compares equal to the long name", C.same(buf.value, str(long_dir)), buf.value)
        R.check("3f: ...and a file beneath the short alias is 'under' the long folder", C.is_under(buf.value + "\\f.txt", long_dir))
        R.check("3f2: control - the short alias is not 'under' a different folder", not C.is_under(buf.value + "\\f.txt", tmp / "box"))
    else:
        R.skip("3e-f", "8.3 short names are disabled on this volume")
    for letter in "ZYXWV":
        if Path(letter + ":\\").exists():
            continue
        sub = subprocess.run(["subst", letter + ":", str(tmp)], capture_output=True, text=True)
        if sub.returncode != 0:
            R.skip("3g", "subst failed: %s" % sub.stderr.strip()[:80])
            return
        try:
            R.check("3g: a `subst` drive letter resolves to the folder it maps (aliasing a protected root through subst is caught)",
                    C.same(letter + ":\\box", tmp / "box"), "%s: -> %s" % (letter, tmp))
            R.check("3g2: control - the subst alias is not equal to an unrelated folder", not C.same(letter + ":\\box", tmp / "other"))
        finally:
            subprocess.run(["subst", letter + ":", "/D"], capture_output=True, text=True)
        listing = subprocess.run(["subst"], capture_output=True, text=True).stdout
        R.check("3h: the temporary `subst` mapping %s: was removed again" % letter, (letter + ":\\") not in listing and not Path(letter + ":\\").exists(), listing[:200])
        return
    R.skip("3g", "no free drive letter for subst")


# ----------------------------------------------------------------------------------------
# 4. the real guard under the real Windows event shape
# ----------------------------------------------------------------------------------------

RUNNER_SRC = textwrap.dedent('''
    import sys, os
    sys.dont_write_bytecode = True
    sys.path.insert(0, %r)
    import scratch_guard as G
    scratch, prod, log, snippet = sys.argv[1:5]
    events = []
    sys.addaudithook(lambda e, a: events.append((e, a)) if e == "subprocess.Popen" else None)
    g = G.Guard(G.Policy(scratch, [prod]), log, hard_exit=True)
    g.install()
    os.chdir(scratch)
    exec(compile(snippet, "<snippet>", "exec"))
    print("SURVIVED")
    for e, a in events:
        print("EVENT executable=%%r args_type=%%s args=%%r" %% (a[0], type(a[1]).__name__, a[1] if isinstance(a[1], str) else list(a[1])))
''')


def violation_logged(lg, *needles):
    """A guard violation was logged AND it is the specific one expected."""
    return "VIOLATION" in lg and all(n.lower() in lg.lower() for n in needles)


def section_guard(R, tmp, run_hook, gs, gp, have_node):
    ok_file = Path(gs) / "ok_inside.txt"
    rc, out, lg, err = run_hook("open(%r, 'w').write('x')" % str(ok_file))
    R.check("4-ctl: control - a write INSIDE the scratch root is allowed, the guard is installed, and nothing is logged",
            rc == 0 and "SURVIVED" in out and ok_file.exists() and "VIOLATION" not in lg, "rc=%s log=%s err=%s" % (rc, lg, err[-200:]))
    if have_node:
        rc, out, lg, err = run_hook("import subprocess; subprocess.run(['node', '-e', 'console.log(1)'], check=True, capture_output=True)")
        R.check("4a: a legitimate `node` launch (flattened command line, executable=None) is ALLOWED by the real hook, with nothing logged",
                rc == 0 and "SURVIVED" in out and "VIOLATION" not in lg, "rc=%s log=%s err=%s" % (rc, lg, (err or "")[-300:]))
        ev = [l for l in out.splitlines() if l.startswith("EVENT")]
        R.check("4b: the event really has the documented Windows shape (args is a str, executable is None)", bool(ev) and "args_type=str" in ev[0] and "executable=None" in ev[0], ev[0] if ev else out)
        R.note("observed: %s" % (ev[0] if ev else "(none)"))
    else:
        R.skip("4a-b", "node is not installed")
    rc, out, lg, err = run_hook("import subprocess; subprocess.run(['cmd', '/c', 'echo hi'])")
    R.check("4c: `cmd /c ...` is refused (exit 97) because cmd is NOT ON THE ALLOWLIST (not for some other reason)",
            rc == G.EXIT_CODE_VIOLATION and violation_logged(lg, "not on the allowlist", "cmd"), "rc=%s log=%s" % (rc, lg))
    outside = Path(tmp) / "outside_win.txt"
    rc, out, lg, err = run_hook("open(%r, 'w').write('x')" % str(outside))
    R.check("4d: a write outside the scratch root is fatal for THAT reason (WRITE outside scratch root, naming the file) and creates no file",
            rc == G.EXIT_CODE_VIOLATION and violation_logged(lg, "for WRITE outside scratch root", outside.name) and not outside.exists(), "rc=%s log=%s" % (rc, lg))
    rc, out, lg, err = run_hook("open(%r, 'rb')" % str(Path(gp) / "x"))
    R.check("4e: even opening a protected path is fatal, as a production-path violation naming that path",
            rc == G.EXIT_CODE_VIOLATION and violation_logged(lg, "production path", Path(gp).name), "rc=%s log=%s" % (rc, lg))
    if have_node:
        rc, out, lg, err = run_hook("import subprocess; subprocess.run(['node', '-e', '1', %r])" % str(Path(gp) / "x.js"))
        R.check("4f: node given a protected path argument is refused because of the PROTECTED PATH (node itself is allowed - see 4a)",
                rc == G.EXIT_CODE_VIOLATION and violation_logged(lg, "protected root", Path(gp).name), "rc=%s log=%s" % (rc, lg))
    else:
        R.skip("4f", "node is not installed")


def make_hook_runner(tmp, gs, gp):
    runner = Path(tmp) / "hook_runner.py"
    runner.write_text(RUNNER_SRC % str(TOOLS), encoding="utf-8")
    log = Path(tmp) / "guard.log"

    def run_hook(snippet):
        if log.exists():
            log.unlink()
        p = subprocess.run([sys.executable, "-B", str(runner), str(gs), str(gp), str(log), snippet], capture_output=True, text=True, timeout=120)
        return p.returncode, p.stdout, (log.read_text() if log.exists() else ""), p.stderr
    return run_hook


# ----------------------------------------------------------------------------------------
# 5. measurement and output helpers
# ----------------------------------------------------------------------------------------

def section_helpers(R):
    peak = MX.peak_memory_bytes()
    R.check("5a: psapi peak working set returns a plausible number", isinstance(peak, int) and 5 * 1024 * 1024 < peak < 64 * 1024 ** 3, str(peak))
    env = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
    prog = "import sys; sys.path.insert(0, %r); from scratch_metrics import configure_output; %s print('\\u092a\\u0915\\u094d\\u0937')"
    bare = subprocess.run([sys.executable, "-c", prog % (str(TOOLS), "")], capture_output=True, env=env)
    R.check("5b-ctl: control - WITHOUT configure_output the same print FAILS under a cp1252 pipe (so the pipe really is restrictive)",
            bare.returncode != 0 and b"UnicodeEncodeError" in bare.stderr, "rc=%s %s" % (bare.returncode, bare.stderr[-150:]))
    p = subprocess.run([sys.executable, "-c", prog % (str(TOOLS), "configure_output(sys.stdout);")], capture_output=True, env=env)
    R.check("5b: under a cp1252 pipe, configure_output makes Devanagari print as UTF-8 (no UnicodeEncodeError)",
            p.returncode == 0 and "\u092a\u0915\u094d\u0937" in p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")[-200:])


# ----------------------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------------------

def _guarded(R, name, fn, *a):
    try:
        return fn(*a)
    except Exception:                       # noqa: BLE001 - a crash must be a visible FAIL, never silence
        R.check("%s ran to completion without an unexpected exception" % name, False, traceback.format_exc()[-500:])
        return None


def main(argv=None):
    if os.name != "nt":
        print("=" * 70)
        print("SKIPPED: this self-test only runs on Windows (os.name=%r). 0 checks were run." % os.name)
        print("This is NOT a pass. The Windows-specific properties remain UNVERIFIED.")
        print("=" * 70)
        return 0
    ap = argparse.ArgumentParser(description="Windows-only self-test for the scratch tooling")
    ap.add_argument("--base", help="ordinary folder in which to create the test folders (default: %%TEMP%%)")
    args = ap.parse_args(argv)
    R = Report()
    base = Path(args.base) if args.base else Path(tempfile.gettempdir())
    print("Windows self-test | %s | python %s | %s" % (platform.platform(), sys.version.split()[0], sys.executable))
    if not base.is_dir():
        print("FAILED: --base %s is not an existing folder" % base)
        return 1
    print("0. environment")
    gate_ok = gate_base(R, base)
    tmp, decoy = make_workspace(base)
    print("   work folder: %s\n   decoy folder: %s" % (tmp, decoy))
    ops = windows_link_ops()
    try:
        if gate_ok:
            print("1. real links, junctions and reparse points")
            linked = _guarded(R, "section 1", section_links, R, tmp, decoy, ops)
            print("2. cleanup refuses a root containing a junction, and deletes nothing")
            if linked:
                _guarded(R, "section 2", section_cleanup, R, tmp, decoy, ops)
            else:
                R.skip("2", "no junction available", required=True)
        print("3. Windows path normalisation on REAL paths")
        _guarded(R, "section 3", section_paths, R, tmp)
        print("4. the REAL Windows subprocess audit-event shape, seen by the real hook (dummy script, not the launcher)")
        gs, gp = tmp / "g_scratch", tmp / "g_prod"; gs.mkdir(); gp.mkdir()
        _guarded(R, "section 4", section_guard, R, tmp, make_hook_runner(tmp, gs, gp), gs, gp, bool(shutil.which("node")))
        print("5. measurement and output helpers")
        _guarded(R, "section 5", section_helpers, R)
    finally:
        print("9. cleanup (links are detached, never followed; targets live in a separate decoy folder and must survive)")
        _guarded(R, "section 9", cleanup_selftest, R, tmp, decoy, base, ops)
    print()
    print("CHECKS RUN: %d | FAILED: %d | SKIPPED: %d (%d required)" % (len(R.ran), len(R.failures), len(R.skips), sum(1 for s in R.skips if s[2])))
    for label, why, req in R.skips:
        print("  skipped%s %s: %s" % (" [REQUIRED]" if req else "", label, why))
    if R.failures:
        print("FAILED: %d check(s) failed:" % len(R.failures))
        for f in R.failures:
            print("  -", f)
    elif R.incomplete:
        print("INCOMPLETE: a required section could not run. This is NOT a pass (exit code 3).")
    else:
        print("=" * 60)
        print("WINDOWS SELF-TEST COMPLETED" + (" WITH OPTIONAL SKIPS (see above)" if R.skips else ""))
    return R.exit_code()


if __name__ == "__main__":
    sys.exit(main())
