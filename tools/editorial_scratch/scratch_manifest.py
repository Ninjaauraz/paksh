"""scratch_manifest.py - before/after manifests of the PROTECTED production state.

    py scratch_manifest.py snapshot --out before.json --production-data-dir D:\\Paksh_Data ^
                                    --production-repo C:\\paksh_project\\paksh ^
                                    --scratch-root E:\\paksh_scratch\\editorial_test\\run1 --hash-db
    py scratch_manifest.py compare before.json after.json

READ-ONLY. It never opens a production file for writing and never launches anything but
`git --no-optional-locks rev-parse/status` (without --no-optional-locks, `git status` may
refresh and WRITE the index, which would itself be a production write).

Records, for the production data dir: the database file and its -wal/-shm/-journal sidecars
(size + mtime_ns, and with --hash-db a SHA-256 of the main file), the production marker, the
backups tree (names/sizes/mtimes). For the production repo: _site (file count, bytes, newest
mtime, and a digest over every (relative path, size, mtime_ns)), whether _site.building /
_site.old exist, `.pipeline.lock` (present? mtime), git HEAD and a digest of `git status
--porcelain`. With --scratch-root the snapshot is BOUND to that scratch root and its layout token,
which is what lets the launcher accept it as the baseline for that run (see validate_baseline).

THREE-STATE RESULT of `compare`:
    UNCHANGED     exit 0   every protected item matches AND every item could actually be checked
    CHANGED       exit 1   at least one protected item differs
    INCONCLUSIVE  exit 3   nothing differs, but something could not be determined (git unavailable
                           or failing, an unreadable file, mismatched snapshot settings, or a
                           pipeline lock present during the window). Never reported as UNCHANGED.

LIMITS: a manifest proves "unchanged between two instants", not "never touched in between"
(a file written and restored with the same size/mtime would not show; --hash-db narrows this for
the database). It is also meaningless if live.py or a scheduled task runs during the window:
pause them first.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from scratch_common import same, walk_nolinks

MANIFEST_VERSION = 2
MAX_BASELINE_AGE_S = 12 * 3600


def _stat(p):
    try:
        st = os.stat(str(p))
        return {"exists": True, "size": st.st_size, "mtime_ns": st.st_mtime_ns}
    except FileNotFoundError:
        return {"exists": False}
    except OSError as e:
        return {"exists": None, "error": e.__class__.__name__}


def _sha256(path, chunk=8 * 1024 * 1024):
    h = hashlib.sha256()
    with open(str(path), "rb") as f:          # read-only
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _tree_digest(root):
    root = Path(root)
    if not root.is_dir():
        return {"exists": False}
    h = hashlib.sha256()
    n = total = newest = 0
    for dirpath, dirnames, filenames, links in walk_nolinks(root):
        dirnames.sort()
        for lk in sorted(links):          # a link is recorded by name only; never followed
            h.update(("LINK|%s\n" % os.path.relpath(lk, str(root)).replace("\\", "/")).encode("utf-8", "replace"))
        for name in sorted(filenames):
            fp = os.path.join(dirpath, name)
            try:
                st = os.stat(fp)
            except OSError:
                continue
            rel = os.path.relpath(fp, str(root)).replace("\\", "/")
            h.update(("%s|%d|%d\n" % (rel, st.st_size, st.st_mtime_ns)).encode("utf-8", "replace"))
            n += 1
            total += st.st_size
            newest = max(newest, st.st_mtime_ns)
    return {"exists": True, "files": n, "bytes": total, "newest_mtime_ns": newest, "digest": h.hexdigest()}


def _git(repo, *args):
    try:
        r = subprocess.run(["git", "--no-optional-locks", "-C", str(repo)] + list(args),
                           capture_output=True, text=True, timeout=300)
        return r.returncode, r.stdout
    except (OSError, subprocess.SubprocessError) as e:
        return -1, "git unavailable: %s" % e.__class__.__name__


def snapshot(production_data_dir, production_repo, hash_db=False, scratch_root=None):
    d, r = Path(production_data_dir), Path(production_repo)
    db = d / "database" / "paksh.db"
    snap = {"manifest_version": MANIFEST_VERSION, "kind": "production-baseline",
            "taken_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "production_data_dir": str(d), "production_repo": str(r), "hash_db": bool(hash_db),
            "scratch_root": None, "scratch_token": None}
    if scratch_root:
        lay = json.loads((Path(scratch_root) / "scratch_layout.json").read_text(encoding="utf-8"))
        snap["scratch_root"], snap["scratch_token"] = str(scratch_root), lay["token"]
    files = {"db": db, "db-wal": Path(str(db) + "-wal"), "db-shm": Path(str(db) + "-shm"),
             "db-journal": Path(str(db) + "-journal"), "marker": d / ".paksh-production",
             "pipeline_lock": r / ".pipeline.lock"}
    snap["files"] = {k: _stat(v) for k, v in files.items()}
    if hash_db and snap["files"]["db"].get("exists"):
        snap["files"]["db"]["sha256"] = _sha256(db)
    snap["backups_tree"] = _tree_digest(d / "backups")
    snap["site"] = _tree_digest(r / "_site")
    snap["site_building_exists"] = (r / "_site.building").exists()
    snap["site_old_exists"] = (r / "_site.old").exists()
    rc, head = _git(r, "rev-parse", "HEAD")
    snap["git_head"] = head.strip() if rc == 0 else "unavailable"
    rc, st = _git(r, "status", "--porcelain")
    snap["git_status_digest"] = hashlib.sha256(st.encode("utf-8", "replace")).hexdigest() if rc == 0 else "unavailable"
    snap["git_status_lines"] = len(st.splitlines()) if rc == 0 else None
    return snap


def compare(before, after):
    """Returns (diffs, inconclusive): two lists of human-readable strings.
    diffs empty AND inconclusive empty == protected state verifiably unchanged."""
    diffs, unsure = [], []

    def cmp(label, a, b):
        if a != b:
            diffs.append("%s changed: %r -> %r" % (label, a, b))

    for k in ("production_data_dir", "production_repo"):
        if before.get(k) != after.get(k):
            diffs.append("%s differs between the snapshots (%r vs %r): they describe different places" % (k, before.get(k), after.get(k)))
    for k in sorted(set(before["files"]) | set(after["files"])):
        a, b = before["files"].get(k, {}), after["files"].get(k, {})
        for field in ("exists", "size", "mtime_ns", "sha256"):
            if field in a or field in b:
                cmp("%s.%s" % (k, field), a.get(field), b.get(field))
        for side, snap in (("before", a), ("after", b)):
            if snap.get("exists") is None:
                unsure.append("%s.%s could not be examined (%s)" % (k, side, snap.get("error", "unknown error")))
    for k in ("backups_tree", "site"):
        for field in ("exists", "files", "bytes", "newest_mtime_ns", "digest"):
            cmp("%s.%s" % (k, field), before[k].get(field), after[k].get(field))
    for k in ("site_building_exists", "site_old_exists"):
        cmp(k, before.get(k), after.get(k))
    for k in ("git_head", "git_status_digest"):
        for side, snap in (("before", before), ("after", after)):
            if snap.get(k) in (None, "unavailable"):
                unsure.append("%s is unavailable in the %s snapshot (git failed or is not installed): "
                              "the production repository state could not be verified" % (k, side))
        if before.get(k) not in (None, "unavailable") and after.get(k) not in (None, "unavailable"):
            cmp(k, before.get(k), after.get(k))
    if before.get("hash_db") != after.get("hash_db"):
        unsure.append("snapshots were taken with different --hash-db settings; the database comparison is weaker")
    elif not before.get("hash_db"):
        unsure.append("neither snapshot used --hash-db: a database write that preserved size and mtime would not be detected")
    for side, snap in (("before", before), ("after", after)):
        if snap["files"].get("pipeline_lock", {}).get("exists"):
            unsure.append("a pipeline lock was present in the %s snapshot: the live pipeline may have been running" % side)
    return diffs, unsure


def validate_baseline(path, layout, now=None, require_hash=True, max_age_s=MAX_BASELINE_AGE_S):
    """Is `path` a meaningful BEFORE manifest for THIS scratch run? Returns a list of problems
    (empty == acceptable). Checks content, not just file age: it must parse, be a current-version
    production-baseline, name the same production paths as the scratch layout, be bound to this
    scratch root and token, be recent by its own embedded timestamp, show an existing database and
    _site, have a usable git state, and show no pipeline lock."""
    now = time.time() if now is None else now
    try:
        m = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return ["cannot read the baseline manifest (%s)" % e.__class__.__name__]
    if not isinstance(m, dict):
        return ["the baseline manifest is not a JSON object"]
    errs = []
    if m.get("manifest_version") != MANIFEST_VERSION or m.get("kind") != "production-baseline":
        errs.append("not a production-baseline manifest of version %d" % MANIFEST_VERSION)
    for k in ("production_data_dir", "production_repo"):
        v = m.get(k)
        if not isinstance(v, str) or not same(v, layout[k]):
            errs.append("%s in the manifest (%r) is not the one this scratch root protects (%r)" % (k, v, layout[k]))
    if m.get("scratch_token") != layout["token"] or not isinstance(m.get("scratch_root"), str) \
            or not same(m["scratch_root"], layout["scratch_root"]):
        errs.append("the manifest is not bound to this scratch root/token: take it with --scratch-root %s" % layout["scratch_root"])
    try:
        t = calendar.timegm(time.strptime(m.get("taken_utc", ""), "%Y-%m-%dT%H:%M:%SZ"))
        age = now - t
        if age < -300:
            errs.append("the manifest's timestamp is in the future")
        elif age > max_age_s:
            errs.append("the manifest is %.1f hours old (limit %.0f)" % (age / 3600.0, max_age_s / 3600.0))
    except (ValueError, OverflowError):
        errs.append("the manifest has no valid taken_utc timestamp")
    files = m.get("files") if isinstance(m.get("files"), dict) else {}
    db = files.get("db", {})
    if db.get("exists") is not True or not isinstance(db.get("size"), int) or db.get("size") <= 0:
        errs.append("the manifest does not show an existing production database")
    elif require_hash and not (isinstance(db.get("sha256"), str) and len(db["sha256"]) == 64):
        errs.append("the manifest has no database SHA-256: take it with --hash-db (or pass --accept-unhashed-baseline to accept a weaker baseline)")
    site = m.get("site") if isinstance(m.get("site"), dict) else {}
    if site.get("exists") is not True or not isinstance(site.get("files"), int) or site["files"] <= 0:
        errs.append("the manifest does not show a populated production _site")
    for k in ("git_head", "git_status_digest"):
        if m.get(k) in (None, "unavailable"):
            errs.append("%s is unavailable in the manifest (git failed): the baseline would be inconclusive" % k)
    if files.get("pipeline_lock", {}).get("exists"):
        errs.append("a pipeline lock existed when the manifest was taken: production was active")
    return errs


def main(argv=None):
    ap = argparse.ArgumentParser(prog="scratch_manifest")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("--out", required=True)
    s.add_argument("--production-data-dir", required=True)
    s.add_argument("--production-repo", required=True)
    s.add_argument("--scratch-root", help="bind the snapshot to this prepared scratch root (required for the launcher's baseline)")
    s.add_argument("--hash-db", action="store_true")
    c = sub.add_parser("compare")
    c.add_argument("before"); c.add_argument("after")
    a = ap.parse_args(argv)
    if a.cmd == "snapshot":
        out = Path(a.out)
        for prod in (a.production_data_dir, a.production_repo):
            # the manifest file itself must never be written inside a protected location
            if os.path.normcase(os.path.abspath(str(out))).startswith(os.path.normcase(os.path.abspath(prod)) + os.sep):
                print("refused: --out must not be inside %s" % prod)
                return 2
        if a.scratch_root and not (Path(a.scratch_root) / "scratch_layout.json").is_file():
            print("refused: %s is not a prepared scratch root" % a.scratch_root)
            return 2
        snap = snapshot(a.production_data_dir, a.production_repo, a.hash_db, a.scratch_root)
        out.write_text(json.dumps(snap, indent=2, sort_keys=True), encoding="utf-8")
        print("wrote %s  (site files=%s, db bytes=%s, lock present=%s, git=%s, hashed=%s, bound=%s)" % (
            out, snap["site"].get("files"), snap["files"]["db"].get("size"), snap["files"]["pipeline_lock"].get("exists"),
            "ok" if snap["git_head"] != "unavailable" else "UNAVAILABLE", snap["hash_db"], bool(snap["scratch_root"])))
        return 0
    before = json.loads(Path(a.before).read_text(encoding="utf-8"))
    after = json.loads(Path(a.after).read_text(encoding="utf-8"))
    diffs, unsure = compare(before, after)
    if diffs:
        print("CHANGED (%d):" % len(diffs))
        for d in diffs:
            print("  - " + d)
    if unsure:
        print("%s (%d):" % ("also INCONCLUSIVE" if diffs else "INCONCLUSIVE", len(unsure)))
        for u in unsure:
            print("  ? " + u)
    if diffs:
        return 1
    if unsure:
        print("RESULT: INCONCLUSIVE - no difference was found, but the protected state could NOT be fully verified. "
              "This is not proof that production is unchanged.")
        return 3
    print("UNCHANGED: every protected production item matches between the two snapshots and every item was checkable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
