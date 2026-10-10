"""
test_editorial_scratch_windows_logic.py - Linux-runnable tests of the LOGIC of the Windows self-test
and of the link-safe helpers it relies on (scratch_common.walk_nolinks / safe_rmtree /
remove_link_only, and their use by cleanup).

WHAT THIS PROVES, AND WHAT IT CANNOT
  * PROVES (Linux-tested): the self-test's decisions are sound. With POSIX symlinks standing in for
    junctions, every junction/cleanup/guard check passes on a correct implementation and FAILS when it
    would otherwise pass for the wrong reason: a redirected %TEMP%, a refusal for a different rule, a
    link maker that makes a plain folder, a cleanup that deletes through a link, a guard that refuses
    everything or refuses for the wrong reason.
  * PROVES: a "fake junction" (a REAL directory presenting the reparse attribute, which is how a
    junction looks on Windows: not a symlink, os.path.islink False, os.walk descends into it) is never
    descended into or deleted through by the tooling.
  * DOES NOT PROVE: real NTFS junction behaviour, real `mklink`/`rmdir`, `subst`, 8.3 names, the real
    Windows audit-event stream. Those are WINDOWS-UNVERIFIED until test_editorial_scratch_windows.py is
    run on the publishing machine. Anything below that says "stand-in" is a simulation.

Safe: creates and removes folders only under a fresh temp directory. Runs nothing from the pipeline.
"""
import ast
import importlib.util
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "tools" / "editorial_scratch"))
import scratch_common as C          # noqa: E402
import scratch_manifest as M        # noqa: E402
import scratch_metrics as MX        # noqa: E402
import scratch_prepare as P         # noqa: E402

spec = importlib.util.spec_from_file_location("selftest_win", str(ROOT / "test_editorial_scratch_windows.py"))
W = importlib.util.module_from_spec(spec)
spec.loader.exec_module(W)          # must be side-effect free and must NOT exit or run anything

FAILURES = []


def check(label, cond, detail=""):
    print("  %s ... %s%s" % (label, "OK" if cond else "FAIL", ("  (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILURES.append(label)


BASE = Path(os.path.realpath(tempfile.mkdtemp(prefix="paksh_wlogic_")))


def mklink_dir(link, target):
    """Directory link WITHOUT privilege: a POSIX/dir symlink where allowed, else (Windows account
    without the symlink privilege) an NTFS junction via `mklink /J`, which needs no privilege."""
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
        return "symlink"
    except OSError:
        if os.name != "nt":
            raise
    ok, detail = W.windows_link_ops().make(link, target)
    if not ok:
        raise OSError("cannot create a directory link by symlink or junction: %s" % detail)
    return "junction"


def rmlink(link):
    C.remove_link_only(link)


def file_symlink_ok(link, target):
    """File symlinks need the symlink privilege on Windows and have no unprivileged equivalent
    (junctions are directory-only): returns False when they cannot be made, so callers skip."""
    try:
        os.symlink(str(target), str(link))
        return True
    except OSError:
        return False


_probe = BASE / "_probe_target"; _probe.mkdir()
try:
    os.symlink(str(_probe), str(BASE / "_probe_link"), target_is_directory=True)
    os.unlink(str(BASE / "_probe_link"))
    CAN_SYMLINK = True
except OSError:
    CAN_SYMLINK = False
# On Windows without the symlink privilege the end-to-end section A runs with REAL junctions, so
# the 1a (reparse attribute) check is exercised for real instead of skipped.
POSIX = W.posix_link_ops() if CAN_SYMLINK else W.windows_link_ops()
_n = [0]


def quiet():
    lines = []
    return W.Report(out=lines.append), lines


def fresh(base=None, prefix=W.PREFIX):
    """A clean (tmp, decoy) pair under an ordinary base."""
    _n[0] += 1
    b = Path(base or (BASE / ("b%d" % _n[0])))
    b.mkdir(parents=True, exist_ok=True)
    return b, *W.make_workspace(b, prefix)


def run_all(R, tmp, decoy, ops, base, cleanup_fn=None):
    linked = W.section_links(R, tmp, decoy, ops)
    if linked:
        W.section_cleanup(R, tmp, decoy, ops, cleanup_fn)
    return linked


# ---------------------------------------------------------------------------------------------
print("A. the self-test's own logic, run end to end with POSIX symlinks as stand-ins (NOT junctions)")
b, tmp, decoy = fresh()
R, lines = quiet()
check("A1: the base is an ordinary folder, so the gate lets the junction sections run", W.gate_base(R, b) is True)
run_all(R, tmp, decoy, POSIX, b)
W.cleanup_selftest(R, tmp, decoy, b, POSIX)
check("A2: with a correct implementation EVERY check passes", R.failures == [], str(R.failures))
check("A3: ...a substantial number of checks really ran (not vacuous)", len(R.ran) >= 30, str(len(R.ran)))
if POSIX.real_junction:
    check("A4: with REAL junctions (Windows, no symlink privilege) only the optional 1f (dir-symlink needs privilege) may be skipped and the attribute check 1a ran",
          [x[0] for x in R.skips] in ([], ["1f"]) and not R.incomplete and any(x.startswith("1a:") for x in R.ran), str(R.skips))
else:
    check("A4: ...only the junction-ATTRIBUTE check is skipped (it needs a real junction), it is not 'required', and says UNVERIFIED",
          [s[0] for s in R.skips] == ["1a"] and not R.incomplete and any("UNVERIFIED" in s[1] for s in R.skips))
check("A5: exit code 0 only because nothing failed and nothing required was skipped", R.exit_code() == 0)
check("A6: both self-test folders are gone afterwards", not tmp.exists() and not decoy.exists())
for lab in ("1-ctl-a", "1-live", "1c", "1c2", "1d", "1d2", "2-ctl", "2a", "2a2", "2a3", "2a4", "2b", "2c", "2d", "9a", "9b", "9c", "9d", "9e"):
    if not any(x.startswith(lab + ":") for x in R.ran):
        check("A7: the check %s exists in the run" % lab, False)
check("A7: every named junction/cleanup check ran", True)

# ---------------------------------------------------------------------------------------------
print("B. a redirected %TEMP% must be detected and must not let the junction checks pass for the wrong reason")
realp = BASE / "real_parent"; realp.mkdir()
redir = BASE / "redir"; mklink_dir(redir, realp)
R, lines = quiet()
check("B1: gate_base refuses a base that IS a link", W.gate_base(R, redir) is False)
check("B2: ...as a REQUIRED skip, so the run is INCOMPLETE (exit 3), not a pass", R.incomplete and R.exit_code() == 3)
text = "\n".join(lines)
check("B3: ...and the redirect is reported explicitly (the link path, and how to rerun)", str(redir) in text and "--base" in text and "link/reparse ancestors" in text, text[:300])
(realp / "inner").mkdir()
R, lines = quiet()
check("B4: a base that merely SITS UNDER a link is refused too", W.gate_base(R, redir / "inner") is False and R.exit_code() == 3)
R, lines = quiet()
check("B5: control - an ordinary base is accepted", W.gate_base(R, BASE) is True and R.failures == [] and not R.skips)
info = W.inspect_base(redir / "inner")
check("B6: inspect_base reports the linked ancestor and that the path resolves elsewhere", info["linked_ancestors"] == [str(redir)] and info["resolves_elsewhere"], str(info))

# if the sections were run anyway under a redirect, they must FAIL (never pass)
rb, tmp_r, decoy_r = fresh(base=redir / "run")
R, lines = quiet()
run_all(R, tmp_r, decoy_r, POSIX, rb)
check("B7: run under a redirected base, the 'no link ancestor' control FAILS (it cannot pass silently)", "1-ctl-b: ...and no ancestor of box is a link" in R.failures, str(R.failures))
check("B8: ...the cleanup control FAILS (the identical junction-free root is refused because of the ancestor)", any(f.startswith("2-ctl") for f in R.failures), str(R.failures))
check("B7b: ...the 'EXACTLY [the link]' ancestor check (1d) FAILS: the redirect shows up as an extra linked ancestor", any(f.startswith("1d:") for f in R.failures), str(R.failures))
check("B7c: ...and its control (1d2: nothing beneath a plain path is linked) FAILS too", any(f.startswith("1d2") for f in R.failures), str(R.failures))
check("B9: ...and the 'refused for THE intended reason' check FAILS", any(f.startswith("2a2") for f in R.failures) or any(f.startswith("2-pre-c") for f in R.failures), str(R.failures))
# the OLD assertions would have passed here: prove the old design was a false positive
bad_root = W.make_scratch_root(tmp_r, "oldstyle", tmp_r / "pa", tmp_r / "pb")
vict = tmp_r / "oldvictim"; vict.mkdir()
mklink_dir(bad_root / "data", vict)
try:
    P.cleanup(str(bad_root), str(bad_root)); old_msg = ""
except C.Refusal as e:
    old_msg = str(e)
check("B10: [regression evidence] the OLD check ('reparse' or 'symlink' in message) WOULD have passed for this redirected case",
      ("reparse" in old_msg or "symlink" in old_msg), old_msg[:160])
check("B11: ...while the NEW check correctly rejects it: the message is the ANCESTOR rule, not the inside-the-root rule",
      "sits under" in old_msg and "inside the scratch root" not in old_msg, old_msg[:200])
box = tmp_r / "plainbox"; box.mkdir()
check("B12: [regression evidence] the OLD 1d check (bool(linked_ancestors)) is TRUE even with no junction at all under a redirect",
      bool(C.linked_ancestors(box / "x.txt")) and C.linked_ancestors(box / "x.txt") != [str(box / "junction")])
C.safe_rmtree(str(rb.parent if False else BASE / "redir" / "run"), "detach") if (BASE / "redir" / "run").exists() else None

# ---------------------------------------------------------------------------------------------
print("C. a cleanup that refuses for the WRONG reason, or deletes, or does not refuse, must FAIL the checks")
real_cleanup = P.cleanup


def stub_generic(sr, cp):
    raise C.Refusal("sentinel does not name this folder; refusing")


def stub_vague(sr, cp):
    if C.links_in_tree(sr):
        raise C.Refusal("a symlink was found")
    return real_cleanup(sr, cp)


def stub_deleting(sr, cp):
    try:
        return real_cleanup(sr, cp)
    except C.Refusal:
        victim = Path(sr) / "data" / "keep.txt"
        if victim.exists():
            os.remove(str(victim))              # deletes THROUGH the link
        raise


def stub_no_refusal(sr, cp):
    return True


def stub_ancestor_reason(sr, cp):
    if C.links_in_tree(sr):
        raise C.Refusal("the scratch root is, or sits under, a symlink/junction/reparse point (%s); refusing to delete through it" % sr)
    return real_cleanup(sr, cp)


def stub_mixed(sr, cp):
    links = C.links_in_tree(sr)
    if links:
        raise C.Refusal("%d symlink/junction/reparse point(s) inside the scratch root (first: %s); Nothing was deleted. "
                        "Also: scratch root overlaps protected path X; refusing" % (len(links), links[0]))
    return real_cleanup(sr, cp)


def stub_other_exception(sr, cp):
    if C.links_in_tree(sr):
        raise RuntimeError("boom")
    return real_cleanup(sr, cp)


for name, stub, expect in (
        ("generic refusal for another rule", stub_generic, ("2-ctl", "2a2", "2d")),
        ("vague 'a symlink was found'", stub_vague, ("2a2", "2d")),
        ("refuses correctly but deletes the target through the link", stub_deleting, ("2a4",)),
        ("never refuses", stub_no_refusal, ("2a:",)),
        ("refuses with the ANCESTOR rule's message", stub_ancestor_reason, ("2a2",)),
        ("message names the junction but ALSO a different rule (overlap)", stub_mixed, ("2a3",)),
        ("raises an unexpected exception", stub_other_exception, ("2a:",))):
    cb, t, d = fresh()
    R, lines = quiet()
    W.section_links(R, t, d, POSIX)
    W.section_cleanup(R, t, d, POSIX, stub)
    missing = [e for e in expect if not any(f.startswith(e) for f in R.failures)]
    check("C: [%s] is caught by ALL of %s" % (name, "/".join(expect)), not missing, "not failing: %s; failures=%s" % (missing, R.failures))
    W.cleanup_selftest(quiet()[0], t, d, cb, POSIX)

# ---------------------------------------------------------------------------------------------
print("D. a link maker that silently creates a PLAIN FOLDER (mklink 'succeeds', nothing is a link) must FAIL")


def make_plain_copy(link, target):
    shutil.copytree(str(target), str(link))
    return True, ""


plain_ops = W.LinkOps("plain-folder impostor", False, make_plain_copy, lambda link: shutil.rmtree(str(link), ignore_errors=True))
db, t, d = fresh()
R, lines = quiet()
W.section_links(R, t, d, plain_ops)
W.section_cleanup(R, t, d, plain_ops)
check("D1: the 'link is a live view of the target' check FAILS for a copied folder", "1-live: the link is a live view of the target (a file created later is visible through it), not a copied folder" in R.failures, str(R.failures))
check("D2: is_link_or_reparse (1b) FAILS for it", "1b: is_link_or_reparse sees the link" in R.failures)
check("D3: the cleanup checks FAIL (it did not refuse, and the precondition that a link exists fails)", any(f.startswith("2a:") for f in R.failures) and any(f.startswith("2-pre-c") for f in R.failures), str(R.failures))
W.cleanup_selftest(quiet()[0], t, d, db, plain_ops)

print("D2. a detector that DESCENDS into the link target must fail 1c / 1c2 (the old os.walk behaviour on Windows junctions)")


def descending_links_in_tree(root, prune_dirs=()):
    hits = []
    for dp, dn, fn in os.walk(str(root), followlinks=True):
        for name in dn + fn:
            if os.path.islink(os.path.join(dp, name)):
                hits.append(os.path.join(dp, name))
    return hits


def descending_walk(root):
    for dp, dn, fn in os.walk(str(root), followlinks=True):
        yield dp, dn, fn, []


real_lit, real_walk = C.links_in_tree, C.walk_nolinks
db2, t2, d2 = fresh()
C.links_in_tree, C.walk_nolinks = descending_links_in_tree, descending_walk
try:
    R, lines = quiet()
    W.section_links(R, t2, d2, POSIX)
finally:
    C.links_in_tree, C.walk_nolinks = real_lit, real_walk
check("D2a: the descending detector is caught by 1c (a nested link inside the target is listed)", any(f.startswith("1c:") for f in R.failures), str(R.failures))
check("D2b: ...and by 1c2 (the target's files are listed)", any(f.startswith("1c2") for f in R.failures), str(R.failures))
W.cleanup_selftest(quiet()[0], t2, d2, db2, POSIX)

print("D3. detectors that are always-true or report phantom links must fail the CONTROLS (1-ctl-a/b/c)")
real_lit, real_isl = C.links_in_tree, C.is_link_or_reparse
db3, t3, d3 = fresh()
C.links_in_tree = lambda *a, **k: ["/phantom/link"]
try:
    R, lines = quiet()
    W.section_links(R, t3, d3, POSIX)
finally:
    C.links_in_tree = real_lit
check("D3a: a detector that always reports a link fails the 'empty before any link exists' control (1-ctl-a)", any(f.startswith("1-ctl-a") for f in R.failures), str(R.failures))
W.cleanup_selftest(quiet()[0], t3, d3, db3, POSIX)
db3, t3, d3 = fresh()
C.is_link_or_reparse = lambda p: True
try:
    R, lines = quiet()
    W.section_links(R, t3, d3, POSIX)
finally:
    C.is_link_or_reparse = real_isl
check("D3b: an is_link_or_reparse that is always True fails the plain-directory control (1-ctl-c)", any(f.startswith("1-ctl-c") for f in R.failures), str(R.failures))
W.cleanup_selftest(quiet()[0], t3, d3, db3, POSIX)

print("E. the self-test's own cleanup: decisions, and a traversing remover must FAIL")
eb, t, d = fresh()
R, lines = quiet()
W.section_links(R, t, d, POSIX)
W.cleanup_selftest(R, t, d, eb, POSIX)
check("E1: the real remover passes every cleanup check and leaves nothing", not [f for f in R.failures] and not t.exists() and not d.exists(), str(R.failures))


def traversing(path, links="detach"):
    for lk in C.links_in_tree(path):
        shutil.rmtree(os.path.realpath(lk))     # follows the link and deletes the TARGET
    shutil.rmtree(path)
    return 0


eb, t, d = fresh()
R, lines = quiet()
W.section_links(R, t, d, POSIX)
W.cleanup_selftest(R, t, d, eb, POSIX, rmtree_fn=traversing)
check("E2: a remover that follows links is caught by the 'nothing deleted through a link' check (9c)", any(f.startswith("9c") for f in R.failures), str(R.failures))
shutil.rmtree(str(eb), ignore_errors=True)

eb = BASE / "e3"; eb.mkdir()
notours = eb / "not_ours_folder"; notours.mkdir(); (notours / "keep.txt").write_text("k")
dd = Path(tempfile.mkdtemp(prefix=W.PREFIX + "decoy_", dir=str(eb)))
R, lines = quiet()
res = W.cleanup_selftest(R, notours, dd, eb, POSIX)
check("E3: a folder without the self-test prefix is NOT deleted, and the check fails", res is False and notours.exists() and any(f.startswith("9-pre") for f in R.failures), str(R.failures))
real_dir = Path(tempfile.mkdtemp(prefix="paksh_victim_", dir=str(eb))); (real_dir / "important.txt").write_text("imp")
linked_tmp = eb / (W.PREFIX + "linked"); mklink_dir(linked_tmp, real_dir)
R, lines = quiet()
res = W.cleanup_selftest(R, linked_tmp, dd, eb, POSIX)
check("E4: a temp folder that is itself a link is NOT followed or deleted", res is False and (real_dir / "important.txt").exists() and any(f.startswith("9-pre") for f in R.failures), str(R.failures))
other_base = BASE / "e5"; other_base.mkdir()
stray = Path(tempfile.mkdtemp(prefix=W.PREFIX, dir=str(other_base)))
R, lines = quiet()
res = W.cleanup_selftest(R, stray, dd, eb, POSIX)
check("E5: a folder with the right prefix but NOT a direct child of the base is refused", res is False and stray.exists(), str(R.failures))

# ---------------------------------------------------------------------------------------------
print("F. the guard section: assertions name the specific violation; a blanket-refusing or wrong-reason hook FAILS")
gb, t, d = fresh()
gs, gp = t / "g_scratch", t / "g_prod"; gs.mkdir(); gp.mkdir()
(gs / "ok_inside.txt").write_text("x")


def canned(wrong=None):
    def run_hook(snippet):
        if wrong == "everything":
            return 97, "", "ts VIOLATION forbidden operation os.system", ""
        if "ok_inside" in snippet:
            return 0, "SURVIVED\n", "", ""
        if "console.log(1)" in snippet:
            if wrong == "node_logged":
                return 0, "SURVIVED\nEVENT executable=None args_type=str args='node'\n", "ts VIOLATION something non-fatal", ""
            return 0, "SURVIVED\nEVENT executable=None args_type=str args='node -e console.log(1)'\n", "", ""
        if "cmd" in snippet:
            return 97, "", "ts VIOLATION " + ("open() for WRITE outside scratch root: x" if wrong == "cmd" else "subprocess executable not on the allowlist: cmd"), ""
        if "outside_win" in snippet:
            if wrong == "outside_created":
                (t / "outside_win.txt").write_text("x")
            return 97, "", "ts VIOLATION open() for WRITE outside scratch root: %s" % (t / "outside_win.txt"), ""
        if "'rb'" in snippet:
            return 97, "", "ts VIOLATION " + ("forbidden operation os.system" if wrong == "protected_read" else "open() touches production path %s" % (gp / "x")), ""
        if "x.js" in snippet:
            return 97, "", "ts VIOLATION " + ("subprocess executable not on the allowlist: node" if wrong == "node_refused" else "subprocess command line mentions protected root %s" % gp), ""
        return 0, "SURVIVED\n", "", ""
    return run_hook


R, lines = quiet()
W.section_guard(R, t, canned(), gs, gp, True)
check("F1: a hook that behaves correctly passes every guard check", R.failures == [] and len(R.ran) == 7, str(R.failures))
R, lines = quiet()
W.section_guard(R, t, canned("everything"), gs, gp, True)
check("F2: a hook that refuses EVERYTHING fails the control and every positive check, not just the refusals",
      all(any(f.startswith(x) for f in R.failures) for x in ("4-ctl", "4a", "4c", "4d", "4e", "4f")), str(R.failures))
for wrong, label in (("node_logged", "4a"), ("cmd", "4c"), ("protected_read", "4e"), ("node_refused", "4f"), ("outside_created", "4d")):
    (t / "outside_win.txt").unlink() if (t / "outside_win.txt").exists() else None
    R, lines = quiet()
    W.section_guard(R, t, canned(wrong), gs, gp, True)
    check("F3: [%s] exit 97 with the WRONG violation is caught by %s" % (wrong, label), any(f.startswith(label) for f in R.failures), str(R.failures))
    (t / "outside_win.txt").unlink() if (t / "outside_win.txt").exists() else None
R, lines = quiet()
W.section_guard(R, t, canned(), gs, gp, False)
check("F4: without node, the node checks are SKIPPED visibly (4a-b, 4f), not silently passed", [s[0] for s in R.skips] == ["4a-b", "4f"] and R.failures == [], str(R.skips))
check("F5: violation_logged needs the VIOLATION marker AND every needle", W.violation_logged("x VIOLATION foo bar", "foo", "bar") and not W.violation_logged("x foo bar", "foo") and not W.violation_logged("x VIOLATION foo", "foo", "bar"))

# ---------------------------------------------------------------------------------------------
print("F6. section 5 (helpers) runs on Linux too; its encoding CONTROL must fail when the pipe is not restrictive")
R, lines = quiet()
W.section_helpers(R)
check("F6a: on a restrictive cp1252 pipe the control and the real check both pass", R.failures == [] and any(x.startswith("5b-ctl") for x in R.ran), str(R.failures))


class _CP:
    def __init__(self, rc, out, err):
        self.returncode, self.stdout, self.stderr = rc, out, err


real_run = W.subprocess.run
W.subprocess.run = lambda *a, **k: _CP(0, "\u092a\u0915\u094d\u0937".encode("utf-8"), b"")          # a pipe that never fails
try:
    R, lines = quiet()
    W.section_helpers(R)
finally:
    W.subprocess.run = real_run
check("F6b: if the 'unconfigured' print does NOT fail, the control FAILS (the encoding check would otherwise pass for the wrong reason)", any(f.startswith("5b-ctl") for f in R.failures), str(R.failures))

print("G. report semantics")
R, _ = quiet(); R.check("x", True); R.skip("o", "optional")
check("G1: optional skip -> exit 0", R.exit_code() == 0)
R, _ = quiet(); R.skip("r", "required", required=True)
check("G2: required skip -> exit 3 (incomplete, not a pass)", R.exit_code() == 3)
R, _ = quiet(); R.check("x", False); R.skip("r", "required", required=True)
check("G3: a failure outranks an incomplete run -> exit 1", R.exit_code() == 1)

# ---------------------------------------------------------------------------------------------
print("H. the self-test file itself: no side effects on import, never touches production or runs the pipeline")
src = (ROOT / "test_editorial_scratch_windows.py").read_text(encoding="utf-8")
tree = ast.parse(src)
top_ok = all(isinstance(n, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef, ast.Assign, ast.Expr, ast.If)) for n in tree.body)
bad_top = [type(n).__name__ for n in tree.body if isinstance(n, ast.Expr) and not (isinstance(n.value, ast.Constant) and isinstance(n.value.value, str))]
check("H1: module level holds only imports, definitions, constants and the main guard (no work happens on import)", top_ok and not bad_top, str(bad_top))
check("H2: it is run only through the __main__ guard", 'if __name__ == "__main__":' in src and src.rstrip().endswith("sys.exit(main())"))
for needle in ("export_static", "scratch_export", "live.py", "refresh.py", "safe_autopush", "paksh.db", "Paksh_Data", "git push", "vercel"):
    check("H3: the self-test never mentions %r" % needle, needle not in src.replace("`scratch_export`", ""), needle)
calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
inits = [n for n in calls if isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == "P" and n.func.attr not in ("cleanup",)]
check("H4: of scratch_prepare it uses ONLY cleanup (never init)", not inits, str([ast.dump(n.func) for n in inits]))
rm = [n for n in calls if isinstance(n.func, ast.Attribute) and n.func.attr in ("rmtree",) or any(k.arg == "ignore_errors" for k in n.keywords)]
check("H5: it never uses shutil.rmtree or ignore_errors (all deletion goes through safe_rmtree, which refuses/detaches links)", not rm)
runs = [n for n in calls if isinstance(n.func, ast.Attribute) and n.func.attr == "run" and isinstance(n.func.value, ast.Name) and n.func.value.id == "subprocess"]
firsts = []
for n in runs:
    a0 = n.args[0] if n.args else None
    if isinstance(a0, ast.List) and a0.elts:
        e = a0.elts[0]
        firsts.append(e.value if isinstance(e, ast.Constant) else ast.dump(e)[:40])
    else:
        firsts.append("<dynamic>")
allowed = {"cmd", "subst", "<dynamic>"}
check("H6: every subprocess.run starts only cmd (mklink/rmdir), subst, or the guard-runner interpreter", all(f in allowed or "sys" in f for f in firsts), str(firsts))
strs = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
check("H7: the only cmd commands are mklink /J and rmdir, and no recursive-delete switch (/s) appears as a string anywhere",
      set(re.findall(r'"cmd", "/c", "([a-z]+)"', src)) == {"mklink", "rmdir"} and not ({"/s", "/S", "/q", "/Q"} & strs), str(set(re.findall(r'"cmd", "/c", "([a-z]+)"', src))))

# ---------------------------------------------------------------------------------------------
print("S. link-safe helpers: walk_nolinks / links_in_tree / remove_link_only / safe_rmtree / cleanup")
sb = BASE / "s"; sb.mkdir()
vict = sb / "victim"; (vict / "deep").mkdir(parents=True); (vict / "deep" / "v.txt").write_text("v"); (vict / "top.txt").write_text("t")

# S1 symlinks (directory and file) are reported, never descended
tree1 = sb / "t1"; (tree1 / "real").mkdir(parents=True); (tree1 / "real" / "f.txt").write_text("f")
mklink_dir(tree1 / "dlink", vict)
HAVE_FLINK = file_symlink_ok(tree1 / "flink", vict / "top.txt")
if not HAVE_FLINK:
    print("  (file symlink not permitted for this account: only the directory link is exercised in S1)")
EXPECT_LINKS = ["dlink", "flink"] if HAVE_FLINK else ["dlink"]
seen = []
for dp, dn, fn, lk in C.walk_nolinks(tree1):
    seen.append((os.path.relpath(dp, str(tree1)), sorted(dn), sorted(fn), sorted(os.path.relpath(x, str(tree1)) for x in lk)))
flat_files = [f for _, _, fs, _ in seen for f in fs]
check("S1: walk_nolinks reports directory and file links, never lists the target's files", sorted(l for _, _, _, ls in seen for l in ls) == EXPECT_LINKS and "v.txt" not in flat_files and "top.txt" not in flat_files, str(seen))
check("S1b: links_in_tree agrees and prune_dirs still works", sorted(os.path.relpath(x, str(tree1)) for x in C.links_in_tree(tree1)) == EXPECT_LINKS and C.links_in_tree(tree1, prune_dirs=("real",)) != [])
check("S1c: a link ROOT is reported as the only link, nothing walked", list(C.walk_nolinks(tree1 / "dlink")) == [(str(tree1 / "dlink"), [], [], [str(tree1 / "dlink")])])

# S2 a FAKE JUNCTION: a real directory that presents the reparse attribute (how a junction looks on Windows)
orig_attrs = C.attrs_is_reparse
FAKE = set()


def fake_attrs(st):
    return (st.st_dev, st.st_ino) in FAKE or orig_attrs(st)


def make_fake_junction(path, files=("inside.txt",)):
    os.makedirs(str(path), exist_ok=True)
    for f in files:
        (Path(path) / f).write_text("inside the junction target")
    st = os.lstat(str(path)); FAKE.add((st.st_dev, st.st_ino))


C.attrs_is_reparse = fake_attrs
try:
    tree2 = sb / "t2"; (tree2 / "real").mkdir(parents=True); (tree2 / "real" / "ok.txt").write_text("ok"); (tree2 / "real" / ".env").write_text("secret-shaped name")
    fj = tree2 / "junction"; make_fake_junction(fj, ("inside.txt", ".env"))
    check("S2-ctl: [control] plain os.walk DOES descend into the fake junction (as os.walk does into a real one on Windows) - so the next checks are meaningful",
          any("inside.txt" in fns for _, _, fns in os.walk(str(tree2), followlinks=False)))
    check("S2a: is_link_or_reparse flags it although it is not a symlink", C.is_link_or_reparse(fj) and not os.path.islink(str(fj)) and fj.is_dir())
    seen_files = [f for _, _, fs, _ in C.walk_nolinks(tree2) for f in fs]
    check("S2b: walk_nolinks reports it as a link and never lists its contents", "inside.txt" not in seen_files and C.links_in_tree(tree2) == [str(fj)] and "ok.txt" in seen_files, str(seen_files))
    check("S2c: forbidden_in_tree does not descend into it (its inner .env is not listed) but is still name-checked", [Path(x).name for x in C.forbidden_in_tree(tree2)] == [".env"] and not any("junction" in x for x in C.forbidden_in_tree(tree2)), str(C.forbidden_in_tree(tree2)))
    check("S2d: tree_bytes and tree_stats do not count the junction's contents",
          P.tree_bytes(tree2) == len("ok") + len("secret-shaped name") and MX.tree_stats(tree2)["files"] == 2, "%s %s" % (P.tree_bytes(tree2), MX.tree_stats(tree2)))
    d_before = M._tree_digest(tree2)
    (fj / "inside.txt").write_text("changed through the junction")
    check("S2e: the manifest digest does not read through it (a change inside does not alter the digest) ...", M._tree_digest(tree2)["digest"] == d_before["digest"])
    ln = tree2 / "extra_link"; mklink_dir(ln, vict)
    check("S2f: ...but ADDING a link changes the digest (links are recorded by name)", M._tree_digest(tree2)["digest"] != d_before["digest"])
    rmlink(ln)

    # safe_rmtree refuse mode: nothing deleted
    res, err = W._call(C.safe_rmtree, str(tree2))
    check("S3: safe_rmtree refuses a tree containing a (fake) junction, says nothing was deleted, and deletes nothing",
          isinstance(err, C.Refusal) and "nothing was deleted" in str(err) and (tree2 / "real" / "ok.txt").exists() and (fj / "inside.txt").exists(), repr(err))
    # detach mode with a NON-EMPTY junction: removal of the link cannot succeed without touching contents -> must stop, children survive
    res, err = W._call(C.safe_rmtree, str(tree2), "detach")
    check("S4: detaching a non-empty (fake) junction stops with an OS error instead of deleting its contents",
          isinstance(err, OSError) and (fj / "inside.txt").exists() and (fj / ".env").exists(), repr(err))
    # an empty one is detached (as rmdir removes a real junction), the rest deleted
    for f in list(fj.iterdir()):
        f.unlink()
    res, err = W._call(C.safe_rmtree, str(tree2), "detach")
    check("S5: an empty (fake) junction is detached and the remainder of the tree deleted", err is None and res == 1 and not tree2.exists(), repr(err))
    FAKE.clear()            # the fake junction is gone; its inode number may be reused by the next directories

    # cleanup() with a fake junction: names it, refuses, deletes nothing, target files survive
    cb, t, d = fresh()
    prod_a, prod_b = t / "pa", t / "pb"
    root = W.make_scratch_root(t, "cr", prod_a, prod_b)
    make_fake_junction(root / "data", ("db.bin",))
    res, err = W._call(P.cleanup, str(root), str(root))
    check("S6: P.cleanup refuses a root with a (fake) junction: names the junction, 'inside the scratch root', nothing deleted",
          isinstance(err, C.Refusal) and str(root / "data") in str(err) and "inside the scratch root" in str(err) and "Nothing was deleted" in str(err)
          and (root / "data" / "db.bin").exists() and (root / "repo" / "f.txt").exists(), repr(err))
    FAKE.clear()
    (root / "data" / "db.bin").unlink(); (root / "data").rmdir()
    res, err = W._call(P.cleanup, str(root), str(root))
    check("S7: [control] the same root without the junction is cleaned up", res is True and not root.exists(), repr(err))
finally:
    C.attrs_is_reparse = orig_attrs
    FAKE.clear()

# S8 symlink: refuse, then detach leaves the victim intact
tree3 = sb / "t3"; (tree3 / "a").mkdir(parents=True); (tree3 / "a" / "x.txt").write_text("x")
mklink_dir(tree3 / "a" / "lnk", vict)
res, err = W._call(C.safe_rmtree, str(tree3))
check("S8: refuse mode with a symlink: Refusal, nothing deleted", isinstance(err, C.Refusal) and (tree3 / "a" / "x.txt").exists() and (vict / "deep" / "v.txt").exists(), repr(err))
res, err = W._call(C.safe_rmtree, str(tree3), "detach")
check("S9: detach mode removes the symlink ITSELF and the tree, never the target", err is None and res == 1 and not tree3.exists() and (vict / "deep" / "v.txt").exists() and (vict / "top.txt").exists(), repr(err))
mklink_dir(sb / "rootlink", vict)
res, err = W._call(C.safe_rmtree, str(sb / "rootlink"), "detach")
check("S10: a link passed AS the root is always refused (even in detach mode) and the target survives", isinstance(err, C.Refusal) and (vict / "top.txt").exists() and C.is_link_or_reparse(sb / "rootlink"), repr(err))
res, err = W._call(C.remove_link_only, str(vict))
check("S11: remove_link_only refuses a real directory", isinstance(err, C.Refusal) and (vict / "top.txt").exists(), repr(err))
(sb / "plain.txt").write_text("p")
res, err = W._call(C.remove_link_only, str(sb / "plain.txt"))
check("S11b: ...and a real file", isinstance(err, C.Refusal) and (sb / "plain.txt").exists(), repr(err))
res, err = W._call(C.safe_rmtree, str(sb / "plain.txt"))
check("S11c: safe_rmtree on a FILE is an error, not a deletion of something unexpected", err is not None and (sb / "plain.txt").exists(), repr(err))
check("S11d: bad mode is rejected", isinstance(W._call(C.safe_rmtree, str(sb), "force")[1], ValueError))
rmlink(sb / "rootlink")

# S12 a link that APPEARS while deleting is not followed
race = sb / "race"; race.mkdir()
for i in range(3):
    (race / ("f%d.txt" % i)).write_text("x")
sub = race / "sub"; sub.mkdir(); (sub / "inner.txt").write_text("inner")
rvict = sb / "race_victim"; rvict.mkdir(); (rvict / "v.txt").write_text("v")
real_unlink, real_scandir, state = C._unlink_file, os.scandir, {"done": False}


class SortedScan:
    """os.scandir proxy that returns files before directories, so the swap below is deterministic."""
    def __init__(self, it):
        self._l = sorted(list(it), key=lambda e: (e.is_dir(follow_symlinks=False), e.name)); self._i = iter(self._l)

    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __iter__(self): return self
    def __next__(self): return next(self._i)
    def close(self): pass


def hooked_unlink(p):
    real_unlink(p)
    if not state["done"]:
        state["done"] = True
        os.rename(str(sub), str(sub) + "_moved")
        mklink_dir(sub, rvict)


C._unlink_file = hooked_unlink
os.scandir = lambda p: SortedScan(real_scandir(p))
try:
    res, err = W._call(C.safe_rmtree, str(race))
finally:
    C._unlink_file = real_unlink
    os.scandir = real_scandir
check("S12: a link that appears mid-deletion stops the deletion, is NOT followed and NOT removed, and the message says earlier deletions stand",
      isinstance(err, C.Refusal) and "stopped" in str(err) and "earlier deletions" in str(err) and (rvict / "v.txt").exists() and C.is_link_or_reparse(sub), repr(err))

# S13 init's failure path and _clear_children never delete through links
cb, t, d = fresh()
pre = t / "preexisting"; pre.mkdir(); (pre / "plain_dir").mkdir(); (pre / "plain_dir" / "a.txt").write_text("a")
mklink_dir(pre / "linkdir", vict)
(pre / "file.txt").write_text("f")
P._clear_children(pre)
check("S13: _clear_children removes ordinary children, leaves a link alone, and the link's target is intact",
      not (pre / "plain_dir").exists() and not (pre / "file.txt").exists() and C.is_link_or_reparse(pre / "linkdir") and (vict / "top.txt").exists())

# ---------------------------------------------------------------------------------------------
print("T. the earlier loose-assertion review (static): no remaining bare 'is not None' refusal checks in the tools test")
tt = (ROOT / "test_editorial_scratch_tools.py").read_text(encoding="utf-8")
loose = [l.strip()[:110] for l in tt.splitlines() if l.lstrip().startswith("check(") and re.search(r"\b(refuses|ev|wev|tryit)\(.*\) is not None", l)]
check("T1: every refusal/violation check in test_editorial_scratch_tools.py now names its reason (via why(...))", not loose, str(loose))

shutil.rmtree(str(BASE), ignore_errors=True)
print()
if FAILURES:
    print("FAILED: %d check(s) failed:" % len(FAILURES))
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("=" * 60)
print("ALL SELF-TEST LOGIC CHECKS PASSED (Linux; link/junction behaviour is simulated - Windows remains UNVERIFIED)")
