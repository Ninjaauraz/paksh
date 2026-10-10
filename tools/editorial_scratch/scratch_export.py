"""scratch_export.py - the guarded launcher for a scratch (NON-production) export.

    py scratch_export.py                                   # PLAN ONLY: preflight + print what would run
    py scratch_export.py --run --confirm-db-path <path> --before-manifest before.json [--variant no-og-cards]

It will not run unless ALL hold:
  * it lives in <scratch_root>\\tools beside a valid scratch_layout.json (so it cannot be run from the production repo);
  * scratch_preflight passes (no .git, no secrets, no links/junctions, no protected-path overlap, the production
    paths still look like production, the real guard accepts, resolved DB == scratch DB, enough disk);
  * --confirm-db-path names the same file as the database path the real modules resolve to (compared after
    case/separator/symlink normalisation, not byte-for-byte) - you must read it and type it;
  * --before-manifest is a MEANINGFUL baseline (scratch_manifest.validate_baseline): parses, current version,
    bound to this scratch root and token, names the same production paths, recent by its own timestamp, shows
    the production database (with a SHA-256) and _site, a usable git state and no pipeline lock.
It does not edit, wrap or bypass any production guard. It runs the UNMODIFIED export_static.main()
from the scratch repo, in this process, under scratch_guard's audit hook.

EXIT CODES
  0  export completed, no guard violation, and the run is a valid benchmark for its variant
  1  preflight failed, the export raised/exited non-zero, or the guard recorded a violation
  2  not a prepared scratch root / run from the wrong place
  3  a required confirmation or baseline is missing or unacceptable (nothing was run)
  4  the export completed but is NOT a valid benchmark (e.g. share cards skipped or partial): see the metrics
  97 the audit-hook guard killed the process on a violation (reason in the .guard.log)

Variants (timing only; neither changes any exporter file):
  full          the export exactly as it is.
  no-og-cards   sets the exporter's own documented constant OG_CARD_N = 0 in memory before main()
                (export_static.py: "Set 0 to disable"). The difference in elapsed time versus `full` is the
                share-card cost (image fetches + rendering). Output differs (no cards): never compare it
                byte-for-byte with a `full` run.
THIS FILE HAS NOT BEEN RUN ON WINDOWS. See docs/EDITORIAL_WINDOWS_SCRATCH_TEST.md.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from scratch_common import Refusal, load_layout, real, same                         # noqa: E402
from scratch_guard import Guard, Policy                                              # noqa: E402
from scratch_manifest import validate_baseline                                       # noqa: E402
from scratch_metrics import (Tee, analyze_og, benchmark_verdict, configure_output,   # noqa: E402
                             peak_memory_bytes, tree_stats)
from scratch_preflight import preflight                                              # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(prog="scratch_export")
    ap.add_argument("--run", action="store_true", help="actually run the export (default: plan only)")
    ap.add_argument("--confirm-db-path", help="the resolved scratch database path, typed by you")
    ap.add_argument("--before-manifest", help="a scratch_manifest.py snapshot bound to this scratch root, taken just before this run")
    ap.add_argument("--accept-unhashed-baseline", action="store_true",
                    help="accept a baseline manifest taken without --hash-db (weaker: a size/mtime-preserving database write would go unnoticed)")
    ap.add_argument("--variant", choices=("full", "no-og-cards"), default="full")
    ap.add_argument("--tag", default="run")
    ap.add_argument("--allow-existing-output", action="store_true")
    ap.add_argument("--min-free-gb", type=float, default=None, help="raise (never lower) the disk requirement computed at init")
    a = ap.parse_args(argv)

    try:
        layout = load_layout(HERE)
    except Refusal as e:
        print("REFUSED: %s" % e)
        return 2
    errors, warnings, info = preflight(layout, a.allow_existing_output, a.min_free_gb, tools_dir=HERE)
    for k, v in sorted(info.items()):
        print("  info    %s: %s" % (k, v))
    for w in warnings:
        print("  warning %s" % w)
    for e in errors:
        print("  ERROR   %s" % e)
    if errors:
        print("PREFLIGHT FAILED: nothing was run.")
        return 1
    resolved = info["resolved"]["db_path"]
    print("\nPLAN")
    print("  scratch root          : %s" % layout["scratch_root"])
    print("  repo (export runs in) : %s" % layout["repo"])
    print("  output will be written: %s" % os.path.join(layout["repo"], "_site"))
    print("  RESOLVED DATABASE     : %s" % resolved)
    print("  protected roots       : %s" % " ; ".join(info["protected_roots"]))
    print("  variant               : %s" % a.variant)
    if not a.run:
        print("\nPLAN ONLY. To run: add --run --confirm-db-path \"%s\" --before-manifest <file>" % resolved)
        return 0

    # --- gates that need human input -------------------------------------------------------------
    if not a.confirm_db_path or not same(a.confirm_db_path, resolved):
        print("\nREFUSED: --confirm-db-path must name the same file as the RESOLVED DATABASE shown above. Read it, "
              "check it is under the scratch root, and type it.")
        return 3
    if not a.before_manifest:
        print("\nREFUSED: --before-manifest is required (py scratch_manifest.py snapshot --scratch-root ... --hash-db).")
        return 3
    problems = validate_baseline(a.before_manifest, layout, require_hash=not a.accept_unhashed_baseline)
    if problems:
        print("\nREFUSED: the BEFORE manifest is not an acceptable baseline for this run:")
        for p in problems:
            print("  - %s" % p)
        return 3

    # --- point THIS process at the scratch world, then install the guard ---------------------------
    os.environ["PAKSH_DATA_DIR"] = layout["data"]
    os.environ["PYTHONUTF8"] = "1"                     # for CHILD processes; does not change this process's stdout
    for k in ("PAKSH_ALLOW_NEW_DB", "PAKSH_ALLOW_EXPORT_COLLAPSE"):
        os.environ.pop(k, None)
    # Keep every incidental write inside the scratch root: no bytecode caches in site-packages,
    # and temp files go to <root>\tmp. Without this the guard would (correctly, but annoyingly)
    # stop the run on a harmless write to %TEMP%.
    sys.dont_write_bytecode = True
    tmp = Path(layout["scratch_root"]) / "tmp"
    tmp.mkdir(exist_ok=True)
    os.environ["TEMP"] = os.environ["TMP"] = os.environ["TMPDIR"] = str(tmp)
    os.chdir(layout["repo"])
    sys.path.insert(0, layout["repo"])
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_log = Path(layout["logs"]) / ("run-%s-%s.log" % (a.tag, stamp))
    guard_log = Path(layout["logs"]) / ("run-%s-%s.guard.log" % (a.tag, stamp))
    metrics_path = Path(layout["logs"]) / ("run-%s-%s.metrics.json" % (a.tag, stamp))
    vend = os.path.join(layout["repo"], "vendor")
    policy = Policy(layout["scratch_root"], list(info["protected_roots"]),
                    allowed_exec_names=("node", "node.exe"),
                    allowed_exec_paths=(os.path.join(vend, "tailwindcss.exe"), os.path.join(vend, "tailwindcss")))
    guard = Guard(policy, guard_log, hard_exit=True)
    logf = open(str(run_log), "w", encoding="utf-8")

    # Unicode-safe output BEFORE anything prints (Devanagari headlines under a cp1252 console/redirect)
    out_stream = sys.__stdout__
    left = configure_output(sys.__stdout__, sys.__stderr__)
    if sys.__stdout__ in left and hasattr(sys.__stdout__, "buffer"):
        out_stream = io.TextIOWrapper(sys.__stdout__.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    t0 = time.monotonic()
    cpu0 = time.process_time()
    tee = Tee(out_stream, logf, t0)
    sys.stdout = tee
    guard.install()
    status, error = "completed", None
    try:
        import export_static as ex
        if not real(ex.__file__).startswith(real(layout["repo"])):
            raise Refusal("export_static was imported from outside the scratch repo: %s" % ex.__file__)
        if not same(ex.ROOT, layout["repo"]):
            raise Refusal("export_static.ROOT is %s, expected %s" % (ex.ROOT, layout["repo"]))
        if not same(ex.database.DB_PATH, layout["db_path"]):
            raise Refusal("database.DB_PATH is %s, expected %s" % (ex.database.DB_PATH, layout["db_path"]))
        if a.variant == "no-og-cards":
            ex.OG_CARD_N = 0
        print("launcher: starting export_static.main() (variant=%s)" % a.variant)
        ex.main()
    except SystemExit as e:
        status, error = ("completed" if e.code in (None, 0) else "exited"), repr(e.code)
    except BaseException as e:                              # noqa: BLE001 - record, then report
        status, error = "failed", "%s: %s" % (type(e).__name__, str(e)[:300])
    wall = time.monotonic() - t0
    tee.close_partial()
    sys.stdout = sys.__stdout__
    logf.close()
    lines = run_log.read_text(encoding="utf-8", errors="replace").splitlines()
    og = analyze_og(lines)
    valid, reasons = benchmark_verdict(a.variant, og)
    site = Path(layout["repo"]) / "_site"
    metrics = {"variant": a.variant, "status": status, "error": error, "wall_seconds": round(wall, 1),
               "cpu_seconds_this_process": round(time.process_time() - cpu0, 1),
               "peak_working_set_bytes_this_process": peak_memory_bytes(),
               "output_site": tree_stats(site) if site.is_dir() else None,
               "og_cards": og, "benchmark_valid": bool(valid and status == "completed"),
               "benchmark_invalid_reasons": ([] if status == "completed" else ["export did not complete (%s)" % status]) + reasons,
               "guard": guard.summary(), "resolved_db": resolved, "python": sys.version.split()[0],
               "windows_verified": False,
               "notes": ["peak memory excludes child processes (node, tailwindcss); observe those in Process Monitor/Task Manager",
                         "timings include the audit-hook overhead (tens of microseconds per file/db event)",
                         "'complete' share cards means every card was rendered, not that every publisher photo was fetched"]}
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print("\nfinished: status=%s wall=%.1fs violations=%d share-cards=%s benchmark_valid=%s" % (
        status, wall, len(guard.violations), og["status"], metrics["benchmark_valid"]))
    for r in metrics["benchmark_invalid_reasons"]:
        print("  NOT A VALID BENCHMARK: %s" % r)
    print("metrics: %s" % metrics_path)
    print("NEXT: take the AFTER manifest and compare it with the BEFORE one (see the procedure document).")
    if status != "completed" or guard.violations:
        return 1
    return 0 if metrics["benchmark_valid"] else 4


if __name__ == "__main__":
    sys.exit(main())
