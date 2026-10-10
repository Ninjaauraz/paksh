"""editorial/cli.py - read-only command line for Milestone 1.

    py -m editorial.cli validate  DOC.json
    py -m editorial.cli audit     DOC.json --events events.json [--events more.json]
    py -m editorial.cli library   --events events.json [--doc DOC.json] [--q TEXT]
                                  [--id N] [--topic T] [--status S] [--from D] [--to D]

Every command only READS the files you name. It refuses SQLite files, writes nothing,
and cannot publish or build. Exit codes: 0 ok, 1 findings that block, 2 usage/IO error.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from .document import load_file
from .library import search_stories
from .resolve import audit_references

_DB_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".db-wal", ".db-shm", ".db-journal")


def _refuse_database(path):
    if str(path).lower().endswith(_DB_SUFFIXES) or "paksh.db" in str(path).lower():
        raise SystemExit("refused: %s looks like a database file; this tool never opens one" % path)


def _read_events(paths):
    rows = []
    for p in paths:
        _refuse_database(p)
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            raise SystemExit("cannot read events file %s: %s" % (p, e.__class__.__name__))
        rows.extend(data.get("events", []) if isinstance(data, dict) else data)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(prog="editorial")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate"); v.add_argument("doc")
    a = sub.add_parser("audit"); a.add_argument("doc"); a.add_argument("--events", action="append", required=True)
    l = sub.add_parser("library")
    l.add_argument("--events", action="append", required=True)
    l.add_argument("--doc"); l.add_argument("--q"); l.add_argument("--id"); l.add_argument("--topic")
    l.add_argument("--status"); l.add_argument("--from", dest="date_from"); l.add_argument("--to", dest="date_to")
    l.add_argument("--limit", type=int, default=50)
    args = ap.parse_args(argv)
    now = datetime.now(timezone.utc)

    if args.cmd in ("validate", "audit"):
        _refuse_database(args.doc)
        loaded = load_file(args.doc)
        print("status: %s%s" % (loaded.status, (" (%s)" % loaded.reason) if loaded.reason else ""))
        for e in loaded.errors:
            print("  ERROR   %s  %s  %s" % (e["path"] or "<root>", e["code"], e["message"]))
        for w in loaded.warnings:
            print("  warning %s  %s  %s" % (w["path"], w["code"], w["message"]))
        if loaded.ok:
            print("hash: %s" % loaded.doc_hash)
        if args.cmd == "audit" and loaded.ok:
            for f in audit_references(loaded, _read_events(args.events), None, now):
                print("  %-8s %-20s story %s %s" % (f["severity"], f["kind"], f["story_id"],
                                                    f.get("reason") or f.get("fields") or ""))
        return 0 if loaded.ok else 1

    rows = _read_events(args.events)
    loaded = None
    if args.doc:
        _refuse_database(args.doc)
        loaded = load_file(args.doc)
        if not loaded.ok:
            print("note: editorial document is %s; showing generated state only" % loaded.status)
    for r in search_stories(rows, loaded, now, args.q, args.id, args.topic, args.date_from,
                            args.date_to, args.status, args.limit):
        print("%-7s %-10s %-18s %s" % (r["id"], r["created_at"][:10] if r["created_at"] else "",
                                       ",".join(r["status"]), (r["title"] or "")[:80]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
