"""scratch_prepare.py - build (init) or remove (cleanup) a scratch test root.

    py scratch_prepare.py init    --scratch-root E:\\paksh_scratch\\editorial_test\\run1 ^
          --source-repo C:\\paksh_project\\paksh --backup-file D:\\Paksh_Data\\backups\\daily\\<file> ^
          --production-data-dir D:\\Paksh_Data --production-repo C:\\paksh_project\\paksh
    py scratch_prepare.py cleanup --scratch-root E:\\paksh_scratch\\editorial_test\\run1 ^
          --confirm-path E:\\paksh_scratch\\editorial_test\\run1

READS from the source repo and the backup file (opened read-only); WRITES only inside
--scratch-root. It never opens the live database, and refuses a backup file that IS the live
database or one of its sidecars. Layout created:

    <root>\\repo\\    code copy: NO .git, NO _site, NO secrets, NO databases, NO locks
    <root>\\data\\    database\\paksh.db (copy of the backup) + the production marker file
    <root>\\logs\\    run logs, metrics, baseline counts
    <root>\\tools\\   these scripts (the only place they will run from)
    <root>\\scratch_layout.json   the sentinel every other script requires

THE MARKER, honestly: export_static.py's guard (paksh_paths.require_production) only
accepts a data directory that carries a marker file with a known string. To let the real,
unmodified guard pass on a scratch directory, `init` writes that marker into <root>\\data.
The marker therefore proves nothing about isolation. Isolation is established by the
launcher's explicit path assertions and the monitors described in the procedure document.

PRODUCTION PATHS ARE VALIDATED, NOT TRUSTED. The deny-list, the overlap checks and the manifests
all protect whatever you typed as --production-data-dir/--production-repo, so a typo would
silently protect the wrong place. `init` therefore requires the data directory to carry the genuine
production marker and the live database, the repo to be a git work tree containing export_static.py,
and (when the repo has live.py) its PRODUCTION_DATA_DIR to be the same folder you named. Extra
protected roots (the folder named by %LOCALAPPDATA%\\Paksh\\data_dir.txt, an already-set
PAKSH_DATA_DIR, the source repo) are added automatically.

LINKS: symlinks, junctions and other reparse points are refused (scratch root and its existing
ancestors, the source tree outside excluded folders, the backup file, and - before any recursive
delete - everything inside a root being cleaned). Detection uses lstat + the Windows reparse-point
attribute; the real-junction behaviour is covered by test_editorial_scratch_windows.py, which has
only been written, not run on Windows.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
import time
import uuid
from pathlib import Path

from scratch_common import (LAYOUT_NAME, LAYOUT_VERSION, MIN_DEPTH, Refusal, ancestor_with_git, depth,
                            forbidden_in_tree, is_link_or_reparse, is_under, linked_ancestors,
                            links_in_tree, name_is_forbidden, overlaps, read_marker_magic, safe_rmtree, same,
                            walk_nolinks)

SLACK_BYTES = 1024 ** 3        # headroom added to the disk formula (patched by tests)

# Never copied from the source repo into the scratch repo.
EXCLUDE_DIRS = {".git", "_site", "_site.building", "_site.old", "__pycache__", "_og_preview",
                "signals", "backups", "logs", "archive", ".vscode", ".claude", ".github", "node_modules"}
EXCLUDE_SUFFIXES = (".log", ".pyc")
EXCLUDE_NAMES = {".gitignore", ".gitattributes", "live_log.txt", "autopush_log.txt", "gdelt_metrics.jsonl"}


def _excluded(name):
    low = name.lower()
    return name_is_forbidden(name) or low in EXCLUDE_NAMES or low.endswith(EXCLUDE_SUFFIXES)


def _ignore(dirpath, names):
    out = []
    for n in names:
        full = os.path.join(dirpath, n)
        if os.path.isdir(full) and n in EXCLUDE_DIRS:
            out.append(n)
        elif os.path.isfile(full) and _excluded(n):
            out.append(n)
    return out


def _ro_connect(path):
    """Read-only, immutable connection: opens no -wal/-shm and cannot modify the file."""
    uri = Path(path).resolve().as_uri() + "?mode=ro&immutable=1"
    return sqlite3.connect(uri, uri=True)


def check_scratch_root(scratch_root, protected_roots):
    sr = Path(scratch_root)
    if not sr.is_absolute():
        raise Refusal("--scratch-root must be an absolute path")
    if depth(sr) < MIN_DEPTH:
        raise Refusal("--scratch-root %s is too shallow: it needs at least %d folder levels below the drive "
                      "(for example E:\\paksh_scratch\\editorial_test\\run1)" % (sr, MIN_DEPTH))
    for p in protected_roots:
        if overlaps(sr, p):
            raise Refusal("--scratch-root %s overlaps protected path %s" % (sr, p))
    home = Path(os.path.expanduser("~"))
    if same(sr, home) or is_under(home, sr):
        raise Refusal("--scratch-root must not be (or contain) your home folder")
    bad = linked_ancestors(sr)
    if bad:
        raise Refusal("--scratch-root is, or sits under, a symlink/junction/reparse point (%s); choose a plain folder" % bad[0])
    g = ancestor_with_git(sr)
    if g:
        raise Refusal("--scratch-root lies inside a git work tree (%s); a git command run from the scratch "
                      "folder could reach that repository. Choose a location outside any repository." % g)


def discover_protected(production_data_dir, production_repo, source_repo, environ=None, local_app_data=None):
    """Validate the operator-supplied production paths and gather every other root that must be
    protected. Returns (roots, notes). Raises Refusal when the paths do not look like production."""
    environ = os.environ if environ is None else environ
    pd, pr, src = Path(production_data_dir), Path(production_repo), Path(source_repo)
    marker_name, magic = read_marker_magic(src)
    if not pd.is_dir():
        raise Refusal("--production-data-dir %s is not an existing folder (typo, or the drive is not mounted?)" % pd)
    mk = pd / marker_name
    try:
        ok = mk.is_file() and mk.read_text(encoding="utf-8").strip() == magic
    except OSError:
        ok = False
    if not ok:
        raise Refusal("--production-data-dir %s lacks the genuine production marker %s: it does not look like "
                      "the Paksh production data directory. Protecting the wrong folder would defeat every "
                      "other check, so init stops here." % (pd, marker_name))
    if not (pd / "database" / "paksh.db").is_file():
        raise Refusal("--production-data-dir %s has no database\\paksh.db" % pd)
    if not pr.is_dir() or not (pr / "export_static.py").is_file() or not (pr / ".git").exists():
        raise Refusal("--production-repo %s is not a git work tree containing export_static.py" % pr)
    notes = []
    live = pr / "live.py"
    if live.is_file():
        m = re.search(r'^PRODUCTION_DATA_DIR\s*=\s*r?["\']([^"\']+)["\']', live.read_text(encoding="utf-8", errors="replace"), re.M)
        if m and not same(m.group(1), pd):
            raise Refusal("--production-data-dir (%s) is not the PRODUCTION_DATA_DIR that live.py in the "
                          "production repo uses (%s): probable typo or the wrong repo" % (pd, m.group(1)))
        if m:
            notes.append("cross-checked against live.py PRODUCTION_DATA_DIR")
    roots = [str(pd), str(pr)]
    lad = local_app_data if local_app_data is not None else environ.get("LOCALAPPDATA")
    if lad:
        cfg = Path(lad) / "Paksh" / "data_dir.txt"
        try:
            for line in cfg.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    roots.append(line)
                    notes.append("also protecting the folder named by %s" % cfg)
                    break
        except OSError:
            pass
    pre = (environ.get("PAKSH_DATA_DIR") or "").strip()
    if pre:
        roots.append(pre)
        notes.append("also protecting PAKSH_DATA_DIR as currently set in this shell (%s)" % pre)
    roots.append(str(src))
    uniq = []
    for r in roots:
        if not any(same(r, u) for u in uniq):
            uniq.append(r)
    return uniq, notes


def tree_bytes(root):
    total = 0
    for dp, _, fns, _links in walk_nolinks(root):
        for f in fns:
            try:
                total += os.lstat(os.path.join(dp, f)).st_size
            except OSError:
                pass
    return total


def _nearest_existing(p):
    p = Path(os.path.abspath(str(p)))
    while not p.exists() and p != p.parent:
        p = p.parent
    return p


def _clear_children(sr):
    for child in sr.iterdir():
        if is_link_or_reparse(child):
            continue                    # never followed, never deleted here; a later init refuses it
        if child.is_dir():
            safe_rmtree(child)
        else:
            child.unlink()


def init(scratch_root, source_repo, backup_file, production_data_dir, production_repo, tools_src=None,
         environ=None, local_app_data=None):
    protected, notes = discover_protected(production_data_dir, production_repo, source_repo, environ, local_app_data)
    check_scratch_root(scratch_root, protected)
    sr, src, bf = Path(scratch_root), Path(source_repo), Path(backup_file)
    pre_existed = sr.exists()
    if pre_existed and any(sr.iterdir()):
        raise Refusal("%s already exists and is not empty; choose a new folder (or run cleanup)" % sr)
    for need in ("export_static.py", "paksh_paths.py", "static/index.html", "static/app.jsx"):
        if not (src / need).is_file():
            raise Refusal("--source-repo does not look like the Paksh repo: missing %s" % need)
    if not bf.is_file():
        raise Refusal("--backup-file %s is not a file" % bf)
    if is_link_or_reparse(bf):
        raise Refusal("--backup-file is a symlink/junction/reparse point; give the real file")
    live_db = Path(production_data_dir) / "database" / "paksh.db"
    if same(bf, live_db) or any(same(bf, str(live_db) + s) for s in ("-wal", "-shm", "-journal")):
        raise Refusal("--backup-file is the LIVE database (or a sidecar). Use a file from backups\\daily instead.")
    if is_under(bf, sr):
        raise Refusal("--backup-file is inside the scratch root")
    vend_ok = (src / "vendor" / "babel.min.js").is_file() and any(
        (src / "vendor" / n).is_file() for n in ("tailwindcss.exe", "tailwindcss"))
    if not vend_ok:
        raise Refusal("source repo is missing vendor/babel.min.js and/or vendor/tailwindcss(.exe): "
                      "the export cannot build without them (they are git-ignored; copy them into the source repo first)")
    links = links_in_tree(src, prune_dirs=EXCLUDE_DIRS)
    if links:
        raise Refusal("the source repo contains symlinks/junctions/reparse points that would be followed or copied "
                      "(first: %s; %d total). Remove them or exclude them, then retry." % (links[0], len(links)))
    marker_name, marker_magic = read_marker_magic(src)

    prod_site = Path(production_repo) / "_site"
    site_bytes = tree_bytes(prod_site) if prod_site.is_dir() else 0
    size0 = bf.stat().st_size
    need_now = size0 + 2 * site_bytes + SLACK_BYTES
    free = shutil.disk_usage(str(_nearest_existing(sr))).free
    if free < need_now:
        raise Refusal("not enough free disk space on the scratch drive: %.1f GB free, need %.1f GB "
                      "(backup %.1f GB + 2 x production _site %.1f GB + %.1f GB headroom)" % (
                          free / 1024.0 ** 3, need_now / 1024.0 ** 3, size0 / 1024.0 ** 3,
                          site_bytes / 1024.0 ** 3, SLACK_BYTES / 1024.0 ** 3))

    repo, data, logs, tools = sr / "repo", sr / "data", sr / "logs", sr / "tools"
    sr.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(str(src), str(repo), ignore=_ignore, symlinks=True)
        if not (repo / "vendor").is_dir():            # git-ignored in the source but required by the build
            shutil.copytree(str(src / "vendor"), str(repo / "vendor"), symlinks=True)
        leftover = forbidden_in_tree(repo)
        if leftover:
            raise Refusal("the scratch repo copy still contains forbidden items (first: %s)" % leftover[0])
        (data / "database").mkdir(parents=True)
        logs.mkdir()
        shutil.copyfile(str(bf), str(data / "database" / "paksh.db"))
        if bf.stat().st_size != size0:
            raise Refusal("backup file changed size while copying (is a backup still being written?)")
        (data / marker_name).write_text(marker_magic, encoding="utf-8")
        tools_src = Path(tools_src) if tools_src else Path(__file__).resolve().parent
        shutil.copytree(str(tools_src), str(tools), ignore=shutil.ignore_patterns("__pycache__"))
        try:
            conn = _ro_connect(data / "database" / "paksh.db")
            try:
                ic = conn.execute("PRAGMA integrity_check").fetchall()
                tables = sorted(r[0] for r in conn.execute("select name from sqlite_master where type='table'"))
                counts = {t: conn.execute('select count(*) from "%s"' % t).fetchone()[0]
                          for t in ("events", "articles") if t in tables}
            finally:
                conn.close()
        except sqlite3.Error as e:
            raise Refusal("the scratch copy of the backup is not a readable SQLite database (%s); "
                          "was the backup file complete?" % e.__class__.__name__)
        if [r[0] for r in ic] != ["ok"]:
            raise Refusal("integrity_check on the scratch copy did not return 'ok': %r" % (ic[:3],))
        if "events" not in tables:
            raise Refusal("the scratch database has no 'events' table; wrong backup file?")
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        baseline = {"taken_utc": stamp, "integrity_check": "ok", "tables": tables, "counts": counts,
                    "backup_source": str(bf), "backup_bytes": size0,
                    "backup_mtime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(bf.stat().st_mtime)),
                    "production_site_bytes": site_bytes, "protected_roots": protected, "notes": notes}
        (logs / "baseline_counts.json").write_text(json.dumps(baseline, indent=2), encoding="utf-8")
        layout = {"version": LAYOUT_VERSION, "scratch_root": str(sr), "repo": str(repo), "data": str(data),
                  "logs": str(logs), "tools": str(tools), "db_path": str(data / "database" / "paksh.db"),
                  "production_data_dir": str(production_data_dir), "production_repo": str(production_repo),
                  "protected_roots": protected, "production_site_bytes": site_bytes,
                  "required_free_bytes": 2 * site_bytes + SLACK_BYTES,
                  "token": uuid.uuid4().hex, "created_utc": stamp, "source_repo": str(src)}
        (sr / LAYOUT_NAME).write_text(json.dumps(layout, indent=2), encoding="utf-8")
        (sr / "SCRATCH_ROOT.txt").write_text(
            "Paksh editorial scratch-export test root. Safe to delete ONLY with:\n"
            "  py tools\\scratch_prepare.py cleanup --scratch-root <this folder> --confirm-path <this folder>\n"
            "Contains a COPY of a database backup. Not production.\n", encoding="utf-8")
    except BaseException:
        # a half-built scratch root is useless and must not be mistaken for a prepared one. If the
        # folder existed (empty) before we started, remove only what we created, not the folder.
        try:
            if sr.exists() and not (sr / LAYOUT_NAME).exists():
                if pre_existed:
                    _clear_children(sr)
                else:
                    safe_rmtree(sr)
        except (OSError, Refusal):
            pass
        raise
    return layout, baseline


_ALLOWED_TOP = ("repo", "data", "logs", "tools", "tmp", LAYOUT_NAME, "SCRATCH_ROOT.txt")


def cleanup(scratch_root, confirm_path):
    sr = Path(scratch_root)
    if not same(sr, confirm_path):
        raise Refusal("--confirm-path must be the exact same path as --scratch-root")
    if depth(sr) < MIN_DEPTH:
        raise Refusal("refusing to delete a path this shallow: %s" % sr)
    layout_file = sr / LAYOUT_NAME
    if not layout_file.is_file():
        raise Refusal("%s is not a prepared scratch root (no %s)" % (sr, LAYOUT_NAME))
    try:
        d = json.loads(layout_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Refusal("cannot read the sentinel %s; refusing" % layout_file)
    if not same(d.get("scratch_root", ""), sr):
        raise Refusal("sentinel does not name this folder; refusing")
    protected = list(d.get("protected_roots") or []) + [d.get("production_data_dir"), d.get("production_repo")]
    for p in protected:
        if p and overlaps(sr, p):
            raise Refusal("scratch root overlaps protected path %s; refusing" % p)
    bad = linked_ancestors(sr)
    if bad:
        raise Refusal("the scratch root is, or sits under, a symlink/junction/reparse point (%s); refusing to delete through it" % bad[0])
    for sub in sr.iterdir():
        if sub.name not in _ALLOWED_TOP and not sub.name.startswith(("before", "after", "run-", "procmon")):
            raise Refusal("unexpected item %s in the scratch root; refusing to delete a folder with unknown contents" % sub.name)
    links = links_in_tree(sr)
    if links:
        raise Refusal("%d symlink/junction/reparse point(s) inside the scratch root (first: %s); remove them by hand "
                      "(for a junction: `rmdir <path>` without /s) and retry. Nothing was deleted." % (len(links), links[0]))
    safe_rmtree(sr)                 # re-checks for links as it goes; never follows or deletes through one
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(prog="scratch_prepare")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init")
    for a in ("scratch-root", "source-repo", "backup-file", "production-data-dir", "production-repo"):
        i.add_argument("--" + a, required=True)
    c = sub.add_parser("cleanup")
    c.add_argument("--scratch-root", required=True)
    c.add_argument("--confirm-path", required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "init":
            layout, base = init(a.scratch_root, a.source_repo, a.backup_file, a.production_data_dir, a.production_repo)
            print("prepared %s" % layout["scratch_root"])
            print("  scratch database: %s" % layout["db_path"])
            print("  baseline: integrity_check=%s counts=%s" % (base["integrity_check"], base["counts"]))
            print("  protected roots : %s" % "; ".join(layout["protected_roots"]))
            for n in base["notes"]:
                print("  note: %s" % n)
            print("next: take the BASELINE manifest bound to this root, then run the preflight/plan:")
            print("  py %s\\tools\\scratch_export.py   (plan only; it will not run the export)" % layout["scratch_root"])
        else:
            cleanup(a.scratch_root, a.confirm_path)
            print("removed %s" % a.scratch_root)
        return 0
    except Refusal as e:
        print("REFUSED: %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
