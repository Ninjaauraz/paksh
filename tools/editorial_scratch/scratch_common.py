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

  On Windows the default (mod=None) resolves the deepest EXISTING ancestor through the OS
  (CreateFileW + GetFinalPathNameByHandleW, fallback realpath + GetLongPathNameW), so 8.3 short
  names, `subst`/mapped drives, junctions and symlinks collapse to one real location, and the
  not-yet-existing tail is appended. NB `os.path is ntpath` on Windows: `mod=ntpath` is the only
  way to ask for lexical behaviour, and `mod=None` the only way to ask for the filesystem.

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


def _lexical_nocase(p, extra_hosts=()):
    """Case-PRESERVING lexical step: strip \\\\?\\ and \\\\.\\ prefixes, convert local
    administrative-share UNC aliases to drive paths, collapse separators and dot segments."""
    s = str(p).replace("/", "\\")
    low = s.lower()
    if low.startswith("\\\\?\\unc\\") or low.startswith("\\\\.\\unc\\"):
        s = "\\\\" + s[8:]
    elif s.startswith("\\\\?\\") or s.startswith("\\\\.\\"):
        s = s[4:]
    m = _ADMIN_SHARE.match(s)
    if m and m.group(1).lower() in (local_host_names() | {h.lower() for h in extra_hosts}):
        s = "%s:\\%s" % (m.group(2).upper(), m.group(3) or "")
    return ntpath.normpath(s)


def lexical_windows(p, extra_hosts=()):
    """Normalise one Windows-style path lexically: strip \\\\?\\ and \\\\.\\ prefixes, convert
    local administrative-share UNC aliases to drive paths, collapse separators and dot segments."""
    return ntpath.normcase(_lexical_nocase(p, extra_hosts))


def real(p, mod=None, extra_hosts=()):
    """Canonical comparison form of a path (see the PATH MODEL note above).

    `mod=None` means "the platform this is running on, using the filesystem". It must be tested
    BEFORE comparing against ntpath: on Windows `os.path is ntpath`, so defaulting `mod` to
    os.path first made every default call purely lexical and left the resolving branch dead
    (the cause of the 3e/3f/3g self-test failures: 8.3 names and `subst` drives never resolved).
    An explicit `mod=ntpath` is always lexical, on every platform."""
    if mod is None or (mod is os.path and os.name != "nt"):
        s = str(p)
        if os.name == "nt":
            return _windows_real(s, extra_hosts)
        return os.path.normcase(os.path.realpath(os.path.abspath(s)))
    if mod is ntpath:
        return lexical_windows(p, extra_hosts)
    return mod.normcase(mod.normpath(str(p)))


# ---- Windows filesystem-aware resolution ---------------------------------------------------

def _load_kernel32():
    """kernel32 with explicit prototypes, loaded at IMPORT time so no DLL load happens later
    inside an audit hook. A private WinDLL is used so the shared ctypes.windll prototypes are
    never altered. Returns None off Windows or if loading fails."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                  wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
        k.CreateFileW.restype = ctypes.c_void_p
        k.GetFinalPathNameByHandleW.argtypes = [ctypes.c_void_p, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
        k.GetFinalPathNameByHandleW.restype = wintypes.DWORD
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        k.CloseHandle.restype = wintypes.BOOL
        k.GetLongPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        k.GetLongPathNameW.restype = wintypes.DWORD
        k.GetShortPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        k.GetShortPathNameW.restype = wintypes.DWORD
        k.QueryDosDeviceW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        k.QueryDosDeviceW.restype = wintypes.DWORD
        return k
    except Exception:
        return None


_K32 = _load_kernel32()
_INVALID_HANDLE = None
if _K32 is not None:
    import ctypes as _ct
    _INVALID_HANDLE = _ct.c_void_p(-1).value       # INVALID_HANDLE_VALUE as ctypes reports it


def _long_path(p):
    """Expand 8.3 short-name components for the part of the path that exists (Windows only)."""
    if os.name != "nt" or _K32 is None:
        return p
    try:
        import ctypes
        size = 32768
        buf = ctypes.create_unicode_buffer(size)
        n = _K32.GetLongPathNameW(str(p), buf, size)
        return buf.value if 0 < n < size else p
    except Exception:
        return p


def short_path(path):
    """The 8.3 spelling of an EXISTING path (Windows), or None if none exists / 8.3 is disabled."""
    if os.name != "nt" or _K32 is None:
        return None
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(32768)
        n = _K32.GetShortPathNameW(str(path), buf, 32768)
        if 0 < n < 32768 and buf.value.lower() != str(path).lower():
            return buf.value
    except Exception:
        pass
    return None


def drive_aliases():
    """Live drive-letter aliases that point INTO the filesystem: `subst` drives and mapped network
    drives. Returns {"Z:": "<canonical target path>"}; real volumes are not listed. Windows only;
    [] semantics elsewhere ({}). Enumerates A:..Z: with QueryDosDeviceW at call time, so it sees
    mappings made after the process started. A letter that cannot be queried is skipped."""
    out = {}
    BS = chr(92)
    NT_PREFIX = BS + "??" + BS          # \??\ : the NT namespace prefix QueryDosDevice returns
    if os.name != "nt" or _K32 is None:
        return out
    import ctypes
    for code in range(ord("A"), ord("Z") + 1):
        letter = chr(code) + ":"
        try:
            buf = ctypes.create_unicode_buffer(4096)
            n = _K32.QueryDosDeviceW(letter, buf, 4096)
            if n == 0:
                continue
            first = buf.value                     # the first string of the multi-string is the live mapping
        except Exception:
            continue
        if first.startswith(NT_PREFIX + "UNC" + BS):
            out[letter] = "\\\\" + first[8:]
        elif first.startswith(NT_PREFIX) and len(first) > 6 and first[5] == ":":
            out[letter] = first[4:]
    return out


def _final_path_by_handle(path):
    """The fully resolved path of an EXISTING file/dir as the OS itself sees it: follows
    symlinks and junctions, expands 8.3 names, resolves `subst`/mapped drives to the real volume
    path. Returns None if it cannot be opened (caller falls back)."""
    if _K32 is None:
        return None
    import ctypes
    # FILE_READ_ATTRIBUTES, share read|write|delete, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS
    h = _K32.CreateFileW(str(path), 0x80, 0x7, None, 3, 0x02000000, None)
    if h is None or h == _INVALID_HANDLE:
        return None
    try:
        size = 1024
        for _ in range(3):
            buf = ctypes.create_unicode_buffer(size)
            n = _K32.GetFinalPathNameByHandleW(h, buf, size, 0)   # 0 = DOS volume name, normalized
            if n == 0:
                return None
            if n < size:
                return buf.value
            size = n + 1
        return None
    finally:
        _K32.CloseHandle(h)


def _resolve_existing(path):
    """Resolve an existing path to its real location. Handle-based first; if that cannot open
    the object (access denied, dangling link) fall back to os.path.realpath + 8.3 expansion. If
    BOTH fail to move the path nothing worse than the lexical form is returned, but that is the
    same string the caller already holds, never a guess about a different location."""
    fp = _final_path_by_handle(path)
    if fp:
        return fp
    try:
        return _long_path(os.path.realpath(path))
    except (OSError, ValueError):
        return str(path)


def _windows_real(p, extra_hosts=()):
    """Canonical form on a real Windows filesystem: lexical clean-up (prefixes, admin shares,
    separators, `.`/`..`), then the DEEPEST EXISTING ancestor is resolved through the OS (so 8.3
    short names, `subst`/mapped drives, junctions and symlinks collapse to one real location) and
    the not-yet-existing tail is re-attached, then the same lexical clean-up runs again (a
    resolved path may itself be \\\\?\\UNC\\localhost\\C$\\...). Case-folded last."""
    s = _lexical_nocase(p, extra_hosts)
    if not ntpath.isabs(s):
        s = ntpath.normpath(ntpath.abspath(s))
    cur, tail = s, []
    while not os.path.lexists(cur):
        parent, name = ntpath.split(cur)
        if not name or parent == cur:          # reached a root that does not exist
            cur = None
            break
        tail.insert(0, name)
        cur = parent
    if cur is not None:
        cur = _resolve_existing(cur)
        s = ntpath.join(cur, *tail) if tail else cur
    return ntpath.normcase(_lexical_nocase(s, extra_hosts))


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
