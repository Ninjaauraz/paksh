"""scratch_common.py - shared path-safety helpers for the Windows scratch-export tooling.

Standard library only; Python 3.9 compatible. NOT part of the pipeline and not imported by
it. These tools are designed to be COPIED into a scratch root (<root>\\tools) and run from
there; they refuse to run from anywhere else.

PATH MODEL
  Every comparison goes through `real()`. On the machine it runs on, `real()` uses
  os.path.realpath (resolves symlinks and, on Windows, junctions/subst/mapped drives and 8.3
  short names for paths that exist), then normcase. Callers may pass `mod=ntpath` (or
  posixpath) to get PURELY LEXICAL behaviour for that path flavour instead; that is how the
  Windows path rules below are unit-tested on Linux. Lexical mode cannot see the filesystem, so
  it cannot resolve links; the Windows self-test (test_editorial_scratch_windows.py) covers
  the filesystem-dependent properties on a real Windows machine.

  Windows alias handling that IS done lexically (any platform, `mod=ntpath`):
    * `\\\\?\\D:\\x` and `\\\\.\\D:\\x`  ->  `D:\\x`        (extended-length / device prefix)
    * `\\\\?\\UNC\\host\\share\\x`       ->  `\\\\host\\share\\x`
    * `\\\\localhost\\D$\\x`, `\\\\127.0.0.1\\D$\\x`, `\\\\<this PC name>\\D$\\x`  ->  `D:\\x`  (administrative-share alias of a local drive)
    * forward slashes, `.`/`..` segments, repeated separators, case.
  NOT detectable here: other network aliases of the same folder (a share with a custom name,
  a SMB path via an unknown host name or IP), and `subst`/mapped-drive aliases when running
  lexically.
"""
from __future__ import annotations

import fnmatch
import json
import ntpath
import os
import platform
import re
import stat as _stat
from pathlib import Path

LAYOUT_NAME = "scratch_layout.json"
LAYOUT_VERSION = 2
MIN_DEPTH = 3          # a scratch root needs at least this many path components below the drive
FILE_ATTRIBUTE_REPARSE_POINT = 0x400

# File/dir names that must never exist inside the scratch repo copy: git metadata (so an
# accidental push is impossible), credentials, databases, locks. NAME patterns only: file
# CONTENTS are not scanned, so a secret pasted into an ordinary source file is not detected.
FORBIDDEN_NAMES = (
    ".git", ".gitmodules", ".git-credentials", ".env", ".env.*", "ai_keys.env", "*.keys.env",
    "*.pem", "*.key", "*.pfx", "*.p12", "*.kdbx", "id_rsa*", "id_ed25519*", "id_ecdsa*",
    ".netrc", "_netrc", ".npmrc", ".pypirc", "credentials", "credentials.*", "secrets.*",
    ".pipeline.lock", "*.db", "*.db-*", "*.db.*", "*.sqlite", "*.sqlite3", "*.bak", "*.bak*",
    "paksh.db*", ".provider_health.json", "offsite_backup.env", "data_dir.txt",
)


class Refusal(Exception):
    """A safety condition failed. Always fatal; never caught-and-ignored by the tools."""


# ----------------------------------------------------------------------------------------
# lexical normalisation (Windows aliases) and canonical comparison form
# ----------------------------------------------------------------------------------------

def local_host_names():
    names = {"localhost", "127.0.0.1", "::1", "[::1]"}
    try:
        names.add(platform.node().lower())
    except Exception:
        pass
    return names


_ADMIN_SHARE = re.compile(r"^\\\\([^\\]+)\\([A-Za-z])\$(?:\\(.*))?$")


def lexical_windows(p, extra_hosts=()):
    """Normalise one Windows-style path lexically: strip \\\\?\\ and \\\\.\\ prefixes, convert
    local administrative-share UNC aliases to drive paths, collapse separators and dot segments."""
    s = str(p).replace("/", "\\")
    low = s.lower()
    if low.startswith("\\\\?\\unc\\") or low.startswith("\\\\.\\unc\\"):
        s = "\\\\" + s[8:]
    elif s.startswith("\\\\?\\") or s.startswith("\\\\.\\"):
        s = s[4:]
    m = _ADMIN_SHARE.match(s)
    if m and m.group(1).lower() in (local_host_names() | {h.lower() for h in extra_hosts}):
        s = "%s:\\%s" % (m.group(2).upper(), m.group(3) or "")
    return ntpath.normcase(ntpath.normpath(s))


def real(p, mod=None, extra_hosts=()):
    """Canonical comparison form of a path (see the PATH MODEL note above)."""
    if mod is None:
        mod = os.path
    if mod is ntpath:
        return lexical_windows(p, extra_hosts)
    if mod is os.path:
        s = str(p)
        if os.name == "nt":
            s = lexical_windows(s, extra_hosts)
            s = _long_path(s)
        return os.path.normcase(os.path.realpath(os.path.abspath(s)))
    return mod.normcase(mod.normpath(str(p)))


def _long_path(p):
    """Expand 8.3 short-name components for the part of the path that exists (Windows only)."""
    if os.name != "nt":
        return p
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(32768)
        n = ctypes.windll.kernel32.GetLongPathNameW(str(p), buf, len(buf))
        return buf.value if 0 < n < len(buf) else p
    except Exception:
        return p


def _sep(mod):
    return (mod or os.path).sep


def same(a, b, mod=None):
    return real(a, mod) == real(b, mod)


def is_under(p, root, strict=False, mod=None):
    pp, rr = real(p, mod), real(root, mod).rstrip("\\/")
    if pp == rr:
        return not strict
    return pp.startswith(rr + _sep(mod))


def overlaps(a, b, mod=None):
    return is_under(a, b, mod=mod) or is_under(b, a, mod=mod)


def depth(p, mod=None):
    """Number of path components BELOW the drive/root (E:\\a\\b\\c -> 3). Lexical, so it is
    identical for the same string on every platform when `mod` is given."""
    mod = mod or (ntpath if os.name == "nt" else os.path)
    _, rest = mod.splitdrive(str(p))
    return len([c for c in re.split(r"[\\/]+", rest) if c and c != "."])


# ----------------------------------------------------------------------------------------
# links, junctions and reparse points
# ----------------------------------------------------------------------------------------

def attrs_is_reparse(st):
    """True if an os.stat_result / lstat result carries the Windows reparse-point attribute
    (junctions, symlinks, OneDrive placeholders, mount points). Pure: unit-testable anywhere."""
    return bool(getattr(st, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT)


def is_link_or_reparse(path):
    """Symlink on any platform, or a Windows reparse point (junction etc.). Does not follow."""
    try:
        st = os.lstat(str(path))
    except OSError:
        return False
    return _stat.S_ISLNK(st.st_mode) or attrs_is_reparse(st)


def walk_nolinks(root):
    """Like os.walk(root) but NEVER descends into a symlink, junction or other reparse point.

    On Windows os.walk(followlinks=False) still descends into a junction, because
    os.path.islink() is False for junctions; this walker checks the reparse attribute instead.
    Yields (dirpath, dirnames, filenames, links): `links` holds the FULL paths of link entries
    (directory or file links) found directly in `dirpath`; they are removed from `dirnames` and
    `filenames`. If `root` itself is a link, one tuple is yielded with links=[root]. The lists
    are the live ones, so a caller may sort `dirnames` in place."""
    root = str(root)
    if is_link_or_reparse(root):
        yield root, [], [], [root]
        return
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        links = []
        for lst in (dirnames, filenames):
            for name in list(lst):
                full = os.path.join(dirpath, name)
                if is_link_or_reparse(full):
                    links.append(full)
                    lst.remove(name)
        yield dirpath, dirnames, filenames, links


def links_in_tree(root, prune_dirs=()):
    """Every symlink/junction/reparse point inside `root` (including `root` itself). Never
    follows links. `prune_dirs` names are not descended into (e.g. an excluded _site)."""
    hits = []
    for dirpath, dirnames, filenames, links in walk_nolinks(root):
        hits.extend(links)
        dirnames[:] = [d for d in dirnames if d not in prune_dirs]
    return hits


def remove_link_only(path):
    """Remove a symlink/junction/reparse point WITHOUT touching what it points at. Refuses
    anything that is not a link. `os.unlink` removes file links and POSIX directory links;
    `os.rmdir` removes a Windows junction or directory symlink (it fails on a non-empty real
    directory, and `os.unlink` fails on a real directory, so neither can remove a real folder
    by mistake)."""
    if not is_link_or_reparse(path):
        raise Refusal("not a link/junction/reparse point; refusing to remove it as one: %s" % path)
    try:
        os.unlink(str(path))
    except OSError:
        os.rmdir(str(path))


def _unlink_file(path):
    try:
        os.unlink(path)
    except PermissionError:
        os.chmod(path, _stat.S_IWRITE | _stat.S_IREAD)      # Windows read-only attribute
        os.unlink(path)


def safe_rmtree(path, links="refuse"):
    """Delete `path` and everything beneath it without EVER following or deleting through a link.

    links="refuse" (default): if any symlink/junction/reparse point exists anywhere inside (or
        `path` itself is one), raise Refusal BEFORE deleting anything. A link that appears
        while deleting stops the deletion at once ("stopped") and is neither followed nor
        removed; what was already deleted stays deleted, which the message states.
    links="detach": first remove each link entry itself (never its target), then delete the
        remainder. A link to a directory is detached with os.rmdir/os.unlink, never rmtree.
    Returns the number of links detached. A link ROOT is always refused."""
    if links not in ("refuse", "detach"):
        raise ValueError("links must be 'refuse' or 'detach'")
    path = str(path)
    if is_link_or_reparse(path):
        raise Refusal("refusing to delete a path that is itself a symlink/junction/reparse point: %s" % path)
    found = links_in_tree(path)
    if found and links == "refuse":
        raise Refusal("%d symlink/junction/reparse point(s) inside %s (first: %s); nothing was deleted" % (len(found), path, found[0]))
    for lk in found:
        remove_link_only(lk)

    def _rm(d):
        if is_link_or_reparse(d):
            raise Refusal("stopped: a link/junction/reparse point appeared at %s while deleting; it was not followed or removed; "
                          "earlier deletions are already done" % d)
        with os.scandir(d) as it:
            entries = list(it)
        for e in entries:
            if is_link_or_reparse(e.path):
                raise Refusal("stopped: a link/junction/reparse point appeared at %s while deleting; it was not followed or removed; "
                              "earlier deletions are already done" % e.path)
            if e.is_dir(follow_symlinks=False):
                _rm(e.path)
            else:
                _unlink_file(e.path)
        os.rmdir(d)

    _rm(path)
    return len(found)


def linked_ancestors(path):
    """Existing ancestors of `path` (and `path` itself, if it exists) that are links/reparse points."""
    out = []
    p = Path(os.path.abspath(str(path)))
    for cand in [p] + list(p.parents):
        if cand.exists() and is_link_or_reparse(cand):
            out.append(str(cand))
    return out


def ancestor_with_git(path):
    """First ancestor directory (excluding `path` itself) that contains a `.git`, else None."""
    p = Path(os.path.abspath(str(path)))
    for cand in p.parents:
        if (cand / ".git").exists():
            return str(cand)
    return None


# ----------------------------------------------------------------------------------------
# forbidden content
# ----------------------------------------------------------------------------------------

def name_is_forbidden(name):
    low = name.lower()
    return any(fnmatch.fnmatchcase(low, pat.lower()) for pat in FORBIDDEN_NAMES)


def forbidden_in_tree(root):
    """Names under `root` matching FORBIDDEN_NAMES. Pure read; never descends into a link
    (a link entry itself is still name-checked)."""
    hits = []
    for dirpath, dirnames, filenames, links in walk_nolinks(root):
        for name in list(dirnames) + list(filenames) + [os.path.basename(x) for x in links]:
            if name_is_forbidden(name):
                hits.append(os.path.join(dirpath, name))
    return hits


def read_marker_magic(repo):
    """The production-marker magic string, read from the repo's paksh_paths.py as TEXT
    (never imported: importing is what preflight does later, in a subprocess)."""
    src = (Path(repo) / "paksh_paths.py").read_text(encoding="utf-8")
    m = re.search(r'^PRODUCTION_MARKER_MAGIC\s*=\s*"([^"]+)"', src, re.M)
    n = re.search(r'^PRODUCTION_MARKER_NAME\s*=\s*"([^"]+)"', src, re.M)
    if not m or not n:
        raise Refusal("cannot find PRODUCTION_MARKER_MAGIC / PRODUCTION_MARKER_NAME in paksh_paths.py")
    return n.group(1), m.group(1)


def load_layout(tools_dir):
    """Locate and validate the scratch layout from where THIS script lives. Refuses to run
    from the production repo (or any folder that is not <scratch_root>\\tools)."""
    tools = Path(tools_dir).resolve()
    if tools.name.lower() != "tools":
        raise Refusal("these scripts must be run from <scratch_root>\\tools (found %s); copy them there "
                      "with scratch_prepare.py init" % tools)
    root = tools.parent
    f = root / LAYOUT_NAME
    if not f.is_file():
        raise Refusal("%s not found: %s is not a prepared scratch root" % (LAYOUT_NAME, root))
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Refusal("cannot read %s: %s" % (f, e.__class__.__name__))
    need = ("version", "scratch_root", "repo", "data", "logs", "tools", "db_path",
            "production_data_dir", "production_repo", "protected_roots", "token",
            "required_free_bytes")
    if any(k not in d for k in need) or d["version"] != LAYOUT_VERSION:
        raise Refusal("%s is incomplete or from another version" % f)
    if not same(d["scratch_root"], root) or not same(d["tools"], tools):
        raise Refusal("scratch layout was created for %s but this is %s (folder moved or copied); "
                      "re-run scratch_prepare.py init" % (d["scratch_root"], root))
    return d
