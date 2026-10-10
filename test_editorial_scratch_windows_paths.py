"""
test_editorial_scratch_windows_paths.py - Windows-ONLY regression tests for path equivalence and
containment (8.3 short names, `subst` drives, case, separators, \\\\?\\ prefix, `..`).

Regression for the first real Windows self-test, which failed 3e / 3f / 3g: on Windows
`os.path is ntpath`, so scratch_common.real() took its purely lexical branch for the DEFAULT call
and never asked the filesystem; a short name or a `subst` drive never collapsed to its real folder.

Runs only on Windows (elsewhere: prints SKIPPED and exits 0 having checked nothing - read the
banner). Creates folders under a fresh temp dir plus one `subst` mapping that it removes again.
Never touches Paksh paths. Exit codes: 0 all ran and passed | 1 a check failed | 3 a required
check could not run (8.3 disabled / no free drive letter) - 3 is NOT a pass.
"""
import ctypes
import ntpath
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "tools" / "editorial_scratch"))

if os.name != "nt":
    print("SKIPPED: Windows-only; zero checks ran (this is NOT a pass).")
    sys.exit(0)

import scratch_common as C          # noqa: E402
import scratch_guard as G           # noqa: E402

SEP = chr(92)
FAILURES, SKIPS = [], []


def check(label, cond, detail=""):
    print("  %s ... %s%s" % (label, "OK" if cond else "FAIL", ("  (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILURES.append(label)


def skip(label, why):
    print("  %s ... SKIPPED (%s)" % (label, why))
    SKIPS.append(label)


def short_name(p):
    buf = ctypes.create_unicode_buffer(2048)
    n = ctypes.windll.kernel32.GetShortPathNameW(str(p), buf, 2048)
    return buf.value if n and buf.value and buf.value.lower() != str(p).lower() else None


def violation(path, prod, scratch):
    pol = G.Policy(str(scratch), [str(prod)])
    return G.evaluate("open", (str(path), "r", 0), pol)


def popen_event(command, cwd, env=None):
    """The Windows event shape: executable=None, args = ONE flattened command-line string."""
    return ("subprocess.Popen", (None, subprocess.list2cmdline(command), str(cwd), env))


def section_command_line(base, prod, scratch, other, letter_for_subst):
    pol = G.Policy(str(scratch), [str(prod)])

    def ev(command, env=None):
        ev_name, a = popen_event(command, scratch, env)
        return G.evaluate(ev_name, a, pol)

    print("R4. command-line scan: 8.3 and live `subst` spellings of a protected root")
    sh = short_name(prod)
    if sh:
        r = ev(["node", "-e", "require('fs').readFileSync(%r)" % (sh + SEP + "secret.txt")])
        check("R4a: a node command line that spells the protected root by its 8.3 name is refused",
              r is not None and "mentions protected root" in r, repr(r))
    r = ev(["node", "-e", "require('fs').readFileSync(%r)" % (str(other) + SEP + "f.txt")])
    check("R4b: control - the same command with an UNRELATED path is not refused by the scan", r is None, repr(r))
    # %r doubles every backslash, exactly as a JavaScript/Python string literal in source does.
    doubled = str(prod / "secret.txt").replace("\\", "\\\\")
    r = ev(["node", "-e", "require('fs').readFileSync('%s')" % doubled])
    check("R4g: the PLAIN protected path with source-escaped (doubled) backslashes is refused "
          "(the scan previously missed this spelling)", r is not None and "mentions protected root" in r, repr(r))
    adm = "\\\\\\\\localhost\\\\" + str(prod)[0] + "$" + str(prod)[2:].replace("\\", "\\\\") + "\\\\secret.txt"
    r = ev(["node", "-e", "require('fs').readFileSync('%s')" % adm])
    check("R4h: doubled-backslash local administrative-share spelling is refused", r is not None, "%r | %s" % (r, adm))
    r = ev(["node", "-e", "require('fs').readFileSync('%s')" % str(other / "f.txt").replace("\\", "\\\\")])
    check("R4i: control - an UNRELATED path with doubled backslashes is not refused", r is None, repr(r))
    if letter_for_subst:
        d = letter_for_subst + ":\\"
        cmd = ["node", "-e", "require('fs').readFileSync(%r)" % (d + prod.name + SEP + "secret.txt")]
        r = ev(cmd)
        check("R4c: a node command line using a live `subst` spelling of the protected root is refused",
              r is not None and "mentions protected root" in r, repr(r))
        real_aliases = G.drive_aliases
        G.drive_aliases = lambda: {}
        try:
            r0 = ev(cmd)
        finally:
            G.drive_aliases = real_aliases
        check("R4d: regression evidence - WITHOUT the alias enumeration the same line is NOT caught (so R4c is due to it)", r0 is None, repr(r0))
        r = ev(["node", "-e", "require('fs').readFileSync(%r)" % (d + other.name + SEP + "f.txt")])
        check("R4e: control - the subst drive spelling of an UNRELATED folder is not refused", r is None, repr(r))
        r = ev(["node", "-e", "require('fs').readFileSync(%r)" % (d + prod.name + "_sibling" + SEP + "x")])
        check("R4f: boundary - <protected>_sibling on the subst drive is not refused", r is None, repr(r))

    print("R5. KNOWN LIMITATION, demonstrated: a script that BUILDS the path is not caught by the scan "
          "(the scan is a tripwire; see the guard docstring)")
    built = "require('fs').readFileSync(%r + %r + %r)" % (str(prod.parent), SEP, prod.name + SEP + "secret.txt")
    r = ev(["node", "-e", "const p=require('path');" + built])
    check("R5a: (limitation) a node launch that concatenates the path at run time is ALLOWED by the scan", r is None, repr(r))


def main():
    base = Path(tempfile.mkdtemp(prefix="paksh_win_paths_")).resolve()
    letter = None
    cl_done = False
    try:
        prod = base / "A_Very_Long_Protected_Directory_Name"
        prod.mkdir()
        (prod / "secret.txt").write_text("x")
        scratch = base / "scratch_area"
        scratch.mkdir()
        other = base / "Another_Quite_Long_Unrelated_Folder"
        other.mkdir()
        (other / "f.txt").write_text("y")

        print("R0. the default call must hit the filesystem; explicit ntpath must stay lexical")
        sh = short_name(prod)
        check("R0a: this is the situation that caused the bug: os.path is ntpath", os.path is ntpath)
        if sh:
            check("R0b: mod=ntpath on a short name stays LEXICAL (does not resolve): documented contract",
                  C.real(sh, mod=ntpath) == ntpath.normcase(ntpath.normpath(sh)))
            check("R0c: the default call DOES resolve the short name to the long path",
                  C.real(sh) == ntpath.normcase(str(prod)), "%s -> %s" % (sh, C.real(sh)))

        print("R1. 8.3 short names (3e / 3f)")
        if not sh:
            skip("R1", "8.3 short names are disabled on this volume")
        else:
            check("R1a: short alias of a real folder == its long name", C.same(sh, prod), sh)
            check("R1b: file beneath the short alias is under the long folder", C.is_under(sh + "\\secret.txt", prod))
            check("R1c: long file path is under the short alias folder", C.is_under(prod / "secret.txt", sh))
            check("R1d: short alias of a NOT-YET-EXISTING child is still under the long folder",
                  C.is_under(sh + "\\no_such_new_file.txt", prod))
            check("R1e: lowercase / UPPERCASE / forward-slash short alias equal as well",
                  C.same(sh.lower(), prod) and C.same(sh.upper().replace("\\", "/"), prod))
            check("R1f: \\\\?\\ prefixed short alias equal as well", C.same("\\\\?\\" + sh, prod))
            check("R1g: .. traversal through the short alias is resolved",
                  C.is_under(sh + "\\..\\" + prod.name + "\\secret.txt", prod))
            check("R1-neg-a: short alias is NOT the unrelated folder", not C.same(sh, other))
            check("R1-neg-b: short alias file is NOT under the unrelated folder", not C.is_under(sh + "\\secret.txt", other))
            check("R1-neg-c: unrelated folder is NOT under the protected folder (via its short alias)",
                  not C.is_under(other / "f.txt", sh))
            check("R1-neg-d: sibling sharing a prefix is not 'under' (boundary): <prod>_x",
                  not C.is_under(str(prod) + "_x\\f.txt", prod))
            print("R1g. guard: opening a protected file through its short alias is a violation")
            r = violation(sh + "\\secret.txt", prod, scratch)
            check("R1h: guard flags the short-alias open as a PRODUCTION access", r is not None and "production path" in r, repr(r))
            r2 = violation(other / "f.txt", prod, scratch)
            check("R1i: control - an unrelated read is NOT flagged", r2 is None, repr(r2))

        print("R2. `subst` drive aliases (3g)")
        for l in "ZYXWVUTSR":
            if not Path(l + ":\\").exists():
                letter = l
                break
        if letter is None:
            skip("R2", "no free drive letter for subst")
        else:
            sub = subprocess.run(["subst", letter + ":", str(base)], capture_output=True, text=True)
            if sub.returncode != 0:
                skip("R2", "subst failed: %s" % sub.stderr.strip()[:80])
                letter = None
            else:
                d = letter + ":\\"
                try:
                    check("R2a: drive root equals the folder it maps", C.same(d, base), "%s -> %s" % (d, C.real(d)))
                    check("R2b: existing child via the drive equals the long path", C.same(d + prod.name, prod))
                    check("R2c: NOT-YET-EXISTING child via the drive equals the mapped path", C.same(d + "box", base / "box"))
                    check("R2d: file via the drive is under the protected folder", C.is_under(d + prod.name + "\\secret.txt", prod))
                    check("R2e: protected file is under the subst drive root (reverse direction)", C.is_under(prod / "secret.txt", d))
                    check("R2f: forward slashes / lowercase drive / \\\\?\\ prefix on the subst path",
                          C.same(d.lower() + prod.name.upper(), prod) and C.same("\\\\?\\" + d + prod.name, prod)
                          and C.same(d.replace("\\", "/") + prod.name, prod))
                    check("R2g: .. traversal on the subst drive is resolved",
                          C.same(d + other.name + "\\..\\" + prod.name, prod))
                    check("R2h: the drive root is NOT 'under' the protected folder (it is its parent)",
                          not C.is_under(d, prod) and C.is_under(prod, d))
                    check("R2-neg-a: drive path is NOT equal to an unrelated folder", not C.same(d + "box", other))
                    check("R2-neg-b: drive-rooted unrelated file is NOT under the protected folder",
                          not C.is_under(d + other.name + "\\f.txt", prod))
                    check("R2-neg-c: a path on a different, real, unmapped drive is not equal",
                          not C.same(d + prod.name, os.environ.get("SystemRoot", "C:\\Windows")))
                    r = violation(d + prod.name + "\\secret.txt", prod, scratch)
                    check("R2i: guard flags opening a protected file through the subst drive as a PRODUCTION access",
                          r is not None and "production path" in r, repr(r))
                    r = violation(d + other.name + "\\f.txt", prod, scratch)
                    check("R2j: control - unrelated file through the subst drive is NOT flagged", r is None, repr(r))
                    section_command_line(base, prod, scratch, other, letter)     # needs the mapping alive
                    cl_done = True
                finally:
                    subprocess.run(["subst", letter + ":", "/D"], capture_output=True, text=True)
                listing = subprocess.run(["subst"], capture_output=True, text=True).stdout
                check("R2k: the temporary subst mapping %s: was removed again" % letter,
                      (letter + ":\\") not in listing and not Path(letter + ":\\").exists(), listing[:200])

        if not cl_done:
            section_command_line(base, prod, scratch, other, None)
        print("R3. case, separators, \\\\?\\ prefix, .. on real paths (must not regress)")
        low, up = str(prod).lower(), str(prod).upper()
        check("R3a: case-insensitive", C.same(low, up))
        check("R3b: forward slashes", C.same(str(prod).replace("\\", "/"), prod))
        check("R3c: \\\\?\\ prefix", C.same("\\\\?\\" + str(prod), prod))
        check("R3d: repeated separators and . segments", C.same(str(base) + "\\\\.\\" + prod.name, prod))
        check("R3e: .. traversal", C.same(str(other) + "\\..\\" + prod.name, prod))
        check("R3f: unreachable drive / nonexistent path degrades to lexical, not an exception",
              C.real("Q:\\definitely\\not\\here\\..\\x") == "q:\\definitely\\not\\x")
        check("R3g: relative path resolves against cwd", C.same(os.path.relpath(str(prod)), prod)
              if os.path.splitdrive(os.getcwd())[0].lower() == os.path.splitdrive(str(prod))[0].lower() else True)
        check("R3-neg: different folders are not equal, with or without prefix",
              not C.same(prod, other) and not C.same("\\\\?\\" + str(other), prod))
    finally:
        if letter:
            subprocess.run(["subst", letter + ":", "/D"], capture_output=True, text=True)
        shutil.rmtree(str(base), ignore_errors=True)
        check("R9: cleanup - temp folder removed", not base.exists())


if __name__ == "__main__":
    main()
    print()
    if FAILURES:
        print("FAILED: %d check(s):" % len(FAILURES))
        for f in FAILURES:
            print("  -", f)
        sys.exit(1)
    if SKIPS:
        print("INCOMPLETE: %d required check group(s) skipped: %s  (exit 3 is NOT a pass)" % (len(SKIPS), SKIPS))
        sys.exit(3)
    print("ALL WINDOWS PATH REGRESSION CHECKS PASSED")
