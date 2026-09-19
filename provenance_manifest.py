"""
provenance_manifest.py - write a dated, hash-stamped snapshot that lets Paksh establish provenance
if its work is ever copied. READ-ONLY: it reads git metadata, hashes a fixed list of source files,
and counts rows in paksh.db (opened mode=ro). It changes nothing except writing the manifest file.

    py provenance_manifest.py                 # writes provenance/manifest_<UTC date>.json and prints it
    py provenance_manifest.py --print-only    # print, write nothing

Commit the resulting file (git gives it an independent, immutable timestamp). Run it monthly and
whenever a copy is suspected; see docs/COPYCAT_RESPONSE.md for the full evidence checklist.
"""
import hashlib
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# The files that embody Paksh's original work. Extend, never silently drop.
KEY_FILES = [
    "sources.py", "verified_registry.py", "cluster.py", "consolidate.py", "analyze.py",
    "export_static.py", "story_memory.py", "storylines.py", "static/app.jsx", "static/styles.css",
    "static/index.html", "METHODOLOGY.md", "CLAUDE.md",
]


def _git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception:
        return ""


def _sha256(path: Path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _db_counts():
    p = ROOT / "paksh.db"
    if not p.exists():
        return {"available": False}
    try:
        c = sqlite3.connect("file:%s?mode=ro" % p.as_posix(), uri=True)
        q = lambda sql: c.execute(sql).fetchone()[0]
        out = {
            "available": True,
            "events": q("SELECT COUNT(*) FROM events WHERE is_demo = 0"),
            "articles": q("SELECT COUNT(*) FROM articles"),
            "earliest_event_created_at": q("SELECT MIN(created_at) FROM events WHERE is_demo = 0"),
            "latest_event_created_at": q("SELECT MAX(created_at) FROM events WHERE is_demo = 0"),
            "earliest_article_fetched_at": q("SELECT MIN(fetched_at) FROM articles"),
        }
        try:
            out["event_relationships"] = q("SELECT COUNT(*) FROM event_relationships")
            out["event_deltas"] = q("SELECT COUNT(*) FROM event_deltas")
        except sqlite3.Error:
            pass
        c.close()
        return out
    except Exception as e:
        return {"available": False, "error": str(e)[:120]}


def build():
    files = {}
    for rel in KEY_FILES:
        p = ROOT / rel
        files[rel] = {"sha256": _sha256(p), "bytes": p.stat().st_size} if p.exists() else None
    fresh = ROOT / "_site" / "data" / "freshness.json"
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git": {
            "head": _git("rev-parse", "HEAD"),
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "remote": _git("remote", "get-url", "origin"),
            "first_commit": _git("show", "-s", "--format=%H %aI", _git("rev-list", "--max-parents=0", "HEAD").split()[0]),
            "commit_count": _git("rev-list", "--count", "HEAD"),
            "working_tree_dirty": bool(_git("status", "--porcelain")),
        },
        "key_files": files,
        "database": _db_counts(),
        "published_site_freshness": json.loads(fresh.read_text(encoding="utf-8")) if fresh.exists() else None,
    }


def main():
    m = build()
    text = json.dumps(m, indent=2, ensure_ascii=False)
    print(text)
    if "--print-only" not in sys.argv:
        out = ROOT / "provenance"
        out.mkdir(exist_ok=True)
        f = out / ("manifest_%s.json" % datetime.now(timezone.utc).strftime("%Y%m%d"))
        f.write_text(text + "\n", encoding="utf-8")
        print("\nwrote", f.relative_to(ROOT), file=sys.stderr)


if __name__ == "__main__":
    main()
