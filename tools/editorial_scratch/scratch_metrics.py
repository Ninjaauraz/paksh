"""scratch_metrics.py - output encoding, run-log analysis and measurement helpers for the launcher.

Kept separate from scratch_export.py so it can be unit-tested without importing or running
anything from the export.
"""
from __future__ import annotations

import io
import os
import re
import time

from scratch_common import walk_nolinks


def configure_output(*streams):
    """Make the given text streams safe for Unicode (Devanagari headlines etc.) regardless of the
    console code page or redirection: UTF-8 with 'replace' on encode errors. Uses
    TextIOWrapper.reconfigure (Python 3.7+). Setting PYTHONUTF8 after interpreter start does NOT
    change the already-created sys.stdout, which is why this is done explicitly. Returns the
    streams it could NOT reconfigure (no reconfigure method), so the caller can wrap them."""
    leftovers = []
    for st in streams:
        fn = getattr(st, "reconfigure", None)
        if fn is None:
            leftovers.append(st)
            continue
        try:
            fn(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            leftovers.append(st)
    return leftovers


class Tee:
    """Prefixes every output line with seconds-since-start and mirrors it to the run log.
    Never raises on an unencodable character: a cosmetic logging problem must not fail an export."""

    def __init__(self, stream, logf, t0, clock=time.monotonic):
        self.stream, self.logf, self.t0, self.clock, self._buf = stream, logf, t0, clock, ""

    def _emit(self, target, text):
        try:
            target.write(text)
        except UnicodeEncodeError:
            enc = getattr(target, "encoding", None) or "ascii"
            target.write(text.encode(enc, "replace").decode(enc, "replace"))

    def write(self, s):
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            out = "[+%8.1fs] %s\n" % (self.clock() - self.t0, line)
            self._emit(self.stream, out)
            self._emit(self.logf, out)
        try:
            self.logf.flush()
        except (OSError, ValueError):
            pass
        return len(s)

    def flush(self):
        try:
            self.stream.flush()
        except (OSError, ValueError):
            pass

    def close_partial(self):
        """Emit any trailing text that never got a newline."""
        if self._buf:
            self.write("\n")


# --- OG-card outcome, from the exporter's own log lines (export_static._build_og_cards) --------------

_OG_WRITTEN = re.compile(r"\[og\]\s+(\d+)/(\d+)\s+share cards written in\s+([0-9.]+)s")
_OG_SKIPPED = re.compile(r"\[og\]\s+share cards skipped")
_OG_BATCH_FAILED = re.compile(r"\[og\]\s+story card batch failed")
_OG_ROOT_FAILED = re.compile(r"\[og\]\s+root card failed")
_OG_DISABLED = re.compile(r"\[og\]\s+story cards disabled")


def analyze_og(lines):
    """Classify the share-card step from the run's output lines (the exporter's own `[og]` messages).
    Returns {"status": complete|partial|skipped|failed|disabled|unknown, written, expected, seconds, issues}.
    LIMITS: the exporter swallows per-card and per-image-fetch failures silently (cards fall back to
    the no-image design), so 'complete' means 'every card was rendered', NOT 'every publisher photo
    was fetched'. 'unknown' (no [og] line at all) is never treated as success."""
    res = {"status": "unknown", "written": None, "expected": None, "seconds": None, "issues": []}
    skipped = failed = root_failed = disabled = False
    for ln in lines:
        m = _OG_WRITTEN.search(ln)
        if m:
            res["written"], res["expected"], res["seconds"] = int(m.group(1)), int(m.group(2)), float(m.group(3))
        if _OG_SKIPPED.search(ln):
            skipped = True
            res["issues"].append(ln.strip()[:240])
        if _OG_BATCH_FAILED.search(ln):
            failed = True
            res["issues"].append(ln.strip()[:240])
        if _OG_ROOT_FAILED.search(ln):
            root_failed = True
            res["issues"].append(ln.strip()[:240])
        if _OG_DISABLED.search(ln):
            disabled = True
    if disabled:
        res["status"] = "disabled"
    elif skipped:
        res["status"] = "skipped"
    elif failed:
        res["status"] = "failed"
    elif res["written"] is not None:
        ok = res["expected"] and res["written"] == res["expected"] and not root_failed
        res["status"] = "complete" if ok else "partial"
    elif root_failed:
        res["status"] = "partial"
    return res


def benchmark_verdict(variant, og):
    """(valid, reasons). A run is a valid benchmark only if the share-card step matches what the
    variant claims to measure."""
    reasons = []
    if variant == "no-og-cards":
        if og["status"] != "disabled":
            reasons.append("variant no-og-cards expected the share-card step to be disabled, saw: %s" % og["status"])
    else:
        if og["status"] != "complete":
            reasons.append("share-card step was %s (expected complete)%s" % (
                og["status"], "; written %s of %s" % (og["written"], og["expected"]) if og["written"] is not None else ""))
        for i in og["issues"][:3]:
            reasons.append("exporter said: " + i)
    return (not reasons), reasons


def peak_memory_bytes():
    """Peak working set of THIS process (the export runs in-process). Children (node, Tailwind) excluded.
    Windows path (psapi via ctypes) is untested on a real Windows machine."""
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            fn = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
            fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
            fn.restype = wintypes.BOOL
            pmc = PMC()
            pmc.cb = ctypes.sizeof(pmc)
            return int(pmc.PeakWorkingSetSize) if fn(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb) else None
        import resource
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024
    except Exception:
        return None


def tree_stats(root):
    n = total = 0
    for dp, _, fns, _links in walk_nolinks(root):
        for f in fns:
            try:
                total += os.path.getsize(os.path.join(dp, f))
                n += 1
            except OSError:
                pass
    return {"files": n, "bytes": total}
