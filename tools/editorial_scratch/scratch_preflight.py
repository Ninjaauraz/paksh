"""scratch_preflight.py - every refusal condition, in one read-only place.

`preflight(layout)` returns (errors, warnings, info). The launcher refuses to run unless
`errors` is empty. Nothing here writes anywhere (the one subprocess it starts imports the
scratch repo's own paksh_paths/database modules with `-B`, so not even bytecode is written).

THE CRITICAL CHECK is `resolved_db`: a fresh Python process, with PAKSH_DATA_DIR pointed at
the scratch data directory and the scratch repo first on sys.path, reports the database path
that paksh_paths.db_path() and database.DB_PATH ACTUALLY resolve to, and whether the existing,
unmodified paksh_paths.require_production() guard accepts it. Those must equal the scratch
database and lie under the scratch root. The marker file is deliberately NOT treated as proof
of isolation: it is only what lets the real guard pass.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from scratch_common import (Refusal, ancestor_with_git, forbidden_in_tree, is_under, links_in_tree,
                            overlaps, read_marker_magic, same)

_PROBE = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import paksh_paths
out = {"paksh_paths_file": paksh_paths.__file__, "db_path": str(paksh_paths.db_path())}
try:
    paksh_paths.require_production(paksh_paths.db_path())
    out["guard"] = "passed"
except Exception as e:
    out["guard"] = "refused: %s: %s" % (type(e).__name__, str(e)[:300])
try:
    import database
    out["database_file"] = database.__file__
    out["database_DB_PATH"] = str(database.DB_PATH)
except Exception as e:
    out["database_import"] = type(e).__name__
print(json.dumps(out))
"""

SENSITIVE_ENV = ("PAKSH_ALLOW_NEW_DB", "PAKSH_ALLOW_EXPORT_COLLAPSE")


def probe_resolution(layout, env=None):
    """Resolve paths in a fresh interpreter exactly as the export would. Returns a dict or raises Refusal."""
    e = dict(os.environ if env is None else env)
    e["PAKSH_DATA_DIR"] = layout["data"]
    for k in SENSITIVE_ENV:
        e.pop(k, None)
    e["PYTHONUTF8"] = "1"
    try:
        r = subprocess.run([sys.executable, "-B", "-c", _PROBE, layout["repo"]], cwd=layout["repo"],
                           env=e, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as ex:
        raise Refusal("could not run the path-resolution probe: %s" % ex.__class__.__name__)
    if r.returncode != 0:
        raise Refusal("path-resolution probe failed: %s" % (r.stderr.strip()[-300:] or r.returncode))
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise Refusal("path-resolution probe printed unreadable output")


def preflight(layout, allow_existing_output=False, min_free_gb=None, tools_dir=None):
    """`min_free_gb` (optional) raises the disk requirement above the layout's own computed figure
    (2 x the production _site size + headroom, recorded at init); it never lowers it."""
    errors, warnings, info = [], [], {}
    root, repo, data = layout["scratch_root"], layout["repo"], layout["data"]
    prod = [layout["production_data_dir"], layout["production_repo"]]
    protected = list(dict.fromkeys([p for p in list(layout.get("protected_roots") or []) + prod if p]))
    info["protected_roots"] = protected

    if sys.version_info < (3, 9):
        errors.append("Python 3.9+ required (found %s)" % sys.version.split()[0])
    info["python"] = sys.version.split()[0]
    if os.name != "nt":
        warnings.append("not running on Windows (os.name=%s): this procedure is designed for the Windows publishing machine" % os.name)

    # --- layout is inside the root and disjoint from every protected root ------------------------
    for k in ("repo", "data", "logs", "tools"):
        p = layout[k]
        if not os.path.isdir(p):
            errors.append("missing directory: %s" % p)
        elif not is_under(p, root, strict=True):
            errors.append("%s (%s) is not inside the scratch root" % (k, p))
    for p in protected:
        if overlaps(root, p):
            errors.append("scratch root %s overlaps protected path %s" % (root, p))
        for k in ("repo", "data", "db_path"):
            if is_under(layout[k], p) or same(layout[k], p):
                errors.append("%s (%s) lies under protected path %s" % (k, layout[k], p))
    if tools_dir is not None and not same(tools_dir, layout["tools"]):
        errors.append("running from %s, not from %s" % (tools_dir, layout["tools"]))
    if same(repo, layout["production_repo"]):
        errors.append("scratch repo IS the production repo")
    g = ancestor_with_git(root)
    if g:
        errors.append("the scratch root lies inside a git work tree (%s)" % g)

    # --- the protected paths must still look like production (a typo/moved drive protects nothing) --
    try:
        marker_name, magic = read_marker_magic(repo)
        pmk = Path(layout["production_data_dir"]) / marker_name
        if not (pmk.is_file() and pmk.read_text(encoding="utf-8").strip() == magic):
            errors.append("the protected production data dir %s no longer carries the production marker: "
                          "wrong path, unmounted drive, or the layout was edited" % layout["production_data_dir"])
        if not (Path(layout["production_repo"]) / "export_static.py").is_file():
            errors.append("the protected production repo %s no longer contains export_static.py" % layout["production_repo"])
    except (OSError, Refusal) as e:
        errors.append("cannot re-validate the protected production paths: %s" % e)

    # --- links / reparse points anywhere in the scratch tree --------------------------------------
    if os.path.isdir(root):
        lk = links_in_tree(root)
        for l in lk[:5]:
            errors.append("symlink/junction/reparse point inside the scratch root: %s" % l)
        if len(lk) > 5:
            errors.append("... and %d more links inside the scratch root" % (len(lk) - 5))

    # --- scratch repo contents ----------------------------------------------------------------
    if os.path.isdir(repo):
        bad = forbidden_in_tree(repo)
        for b in bad[:10]:
            errors.append("forbidden item in the scratch repo (git metadata / secret / database / lock): %s" % b)
        if len(bad) > 10:
            errors.append("... and %d more forbidden items" % (len(bad) - 10))
        for need in ("export_static.py", "paksh_paths.py", "database.py", "static/index.html", "static/app.jsx",
                     "vendor/babel.min.js"):
            if not os.path.isfile(os.path.join(repo, *need.split("/"))):
                errors.append("scratch repo is missing %s" % need)
        if not any(os.path.isfile(os.path.join(repo, "vendor", n)) for n in ("tailwindcss.exe", "tailwindcss")):
            errors.append("scratch repo is missing vendor/tailwindcss(.exe)")
        outs = [n for n in ("_site", "_site.building", "_site.old") if os.path.exists(os.path.join(repo, n))]
        if outs and not allow_existing_output:
            errors.append("scratch repo already contains %s (a previous run). Use a fresh scratch root, or pass "
                          "--allow-existing-output if you understand the collapse guard will compare against it." % outs)
    node = shutil.which("node")
    if node is None:
        errors.append("`node` is not on PATH (needed to precompile app.jsx)")
    else:
        info["node"] = node
        for p in protected:
            if is_under(node, p):
                errors.append("`node` resolves to %s, inside protected path %s" % (node, p))

    # --- environment ---------------------------------------------------------------------------
    pd = os.environ.get("PAKSH_DATA_DIR")
    if pd and not same(pd, data):
        errors.append("PAKSH_DATA_DIR is already set to %s in this shell. Open a NEW PowerShell and leave it unset; "
                      "the launcher sets it itself." % pd)
    for k in SENSITIVE_ENV:
        if os.environ.get(k):
            errors.append("%s is set; it weakens a production guard. Unset it." % k)
    for entry in [x for x in os.environ.get("PYTHONPATH", "").split(os.pathsep) if x] + [x for x in sys.path if x]:
        for p in protected:
            if is_under(entry, p):
                errors.append("a Python search path entry points into a protected path: %s" % entry)
    for k in sorted(os.environ):
        if k.startswith("PAKSH_") and k != "PAKSH_DATA_DIR" and k not in SENSITIVE_ENV:
            warnings.append("%s is set in this shell. It is not a path variable, but it can change what the export produces "
                            "(value not shown); unset it unless you set it on purpose." % k)
    lad = os.environ.get("LOCALAPPDATA")
    if lad and os.path.isfile(os.path.join(lad, "Paksh", "data_dir.txt")):
        info["note_data_dir_txt"] = ("%LOCALAPPDATA%\\Paksh\\data_dir.txt exists; it is ignored because "
                                     "PAKSH_DATA_DIR takes precedence in paksh_paths._resolve_config()")

    # --- data dir -------------------------------------------------------------------------------
    db = layout["db_path"]
    if not os.path.isfile(db):
        errors.append("scratch database missing: %s" % db)
    else:
        try:
            name, magic = read_marker_magic(repo)
            mk = Path(data) / name
            if not mk.is_file() or mk.read_text(encoding="utf-8").strip() != magic:
                errors.append("scratch data directory lacks the expected marker file %s" % mk)
        except Refusal as e:
            errors.append(str(e))
        try:
            c = sqlite3.connect(Path(db).resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
            try:
                info["events_in_scratch_db"] = c.execute("select count(*) from events").fetchone()[0]
            finally:
                c.close()
        except sqlite3.Error as e:
            errors.append("scratch database is not readable as SQLite with an events table: %s" % e.__class__.__name__)
    for s_ in ("-wal", "-shm", "-journal"):
        if os.path.exists(db + s_):
            warnings.append("scratch database has a leftover %s file from a previous run" % s_)

    # --- disk: the figure computed at init (2 x production _site + headroom), optionally raised ----
    try:
        need = int(layout.get("required_free_bytes") or 0)
        if min_free_gb is not None:
            need = max(need, int(min_free_gb * 1024.0 ** 3))
        free = shutil.disk_usage(root).free
        info["free_gb"] = round(free / 1024.0 ** 3, 1)
        info["required_free_gb"] = round(need / 1024.0 ** 3, 1)
        if free < need:
            errors.append("only %.1f GB free on the scratch drive; this run needs %.1f GB (2 x production _site + headroom, "
                          "computed at init)" % (free / 1024.0 ** 3, need / 1024.0 ** 3))
    except OSError:
        warnings.append("could not read free disk space")

    # --- THE critical check: what do the real modules resolve to? --------------------------------
    if not errors:
        try:
            res = probe_resolution(layout)
            info["resolved"] = res
            if not same(res["db_path"], db):
                errors.append("paksh_paths.db_path() resolves to %s, expected the scratch database %s" % (res["db_path"], db))
            if "database_DB_PATH" in res and not same(res["database_DB_PATH"], db):
                errors.append("database.DB_PATH resolves to %s, expected %s" % (res["database_DB_PATH"], db))
            for k in ("paksh_paths_file", "database_file"):
                if k in res and not is_under(res[k], repo):
                    errors.append("%s was imported from %s, which is outside the scratch repo" % (k, res[k]))
            if not is_under(res["db_path"], root):
                errors.append("resolved database path is outside the scratch root")
            for p in protected:
                if is_under(res["db_path"], p):
                    errors.append("resolved database path is under protected path %s" % p)
            if res.get("guard") != "passed":
                errors.append("the existing production guard refused the scratch directory: %s" % res.get("guard"))
        except Refusal as e:
            errors.append(str(e))
    return errors, warnings, info


def main(argv=None):
    from scratch_common import load_layout
    here = Path(__file__).resolve().parent
    try:
        layout = load_layout(here)
    except Refusal as e:
        print("REFUSED: %s" % e)
        return 2
    errors, warnings, info = preflight(layout, tools_dir=here)
    for k, v in sorted(info.items()):
        print("  info    %s: %s" % (k, v))
    for w in warnings:
        print("  warning %s" % w)
    for e in errors:
        print("  ERROR   %s" % e)
    print("PREFLIGHT %s" % ("FAILED" if errors else "PASSED"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
