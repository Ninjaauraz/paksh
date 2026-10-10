"""
test_editorial_timestamps.py - Milestone 1.1: regression + seeded-fuzz tests for the
timestamp-validation defect (OverflowError escaping validate_document()/load_text()).

The defect: regex-valid timestamps whose UTC equivalent is outside datetime's range, e.g.
0001-01-01T00:00:00+05:00 and 9999-12-31T23:59:59-05:00, raised OverflowError out of
parse_utc(), violating the documented fail-safe contract.

Pure and deterministic (fixed seeds, no clock, no I/O, no network). Python 3.9 compatible.

Run:  py test_editorial_timestamps.py
"""
import json
import random
import re
import sys
from datetime import datetime, timedelta, timezone

from editorial import document as D
from editorial import schema as S

FAILURES = []


def check(label, cond, detail=""):
    print(f"  {label} ... {'OK' if cond else 'FAIL'}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILURES.append(label)


def doc_with(**times):
    p = {"id": "a", "scope": "home", "story_id": "5", "action": "pin"}
    p.update(times)
    return {"schema_version": 1, "stories": {}, "placements": [p]}


def outcome(fn):
    """('ok', value) | ('value_error', msg) | ('RAISED:<type>', msg) - never lets anything escape."""
    try:
        return "ok", fn()
    except ValueError as e:
        return "value_error", str(e)
    except BaseException as e:  # noqa: BLE001 - the whole point of this test
        return "RAISED:" + type(e).__name__, str(e)


# An INDEPENDENT oracle: deliberately NOT regex-based and sharing no pattern with the implementation.
# It checks the shape position by position using plain ASCII character sets, then does the range
# arithmetic differently from parse_utc (naive local time minus the offset, rather than astimezone).
# Accepted shape: YYYY-MM-DDTHH:MM:SS[.f{1,6}](Z|+HH:MM|-HH:MM), ASCII only, nothing before/after.
_DIG = "0123456789"


def _digits(s, n):
    return len(s) == n and all(c in _DIG for c in s)


def oracle_accepts(s):
    if not isinstance(s, str) or not s.isascii() or len(s) < 20:
        return False
    if s[4] != "-" or s[7] != "-" or s[10] != "T" or s[13] != ":" or s[16] != ":":
        return False
    y, mo, d, h, mi, sec = s[0:4], s[5:7], s[8:10], s[11:13], s[14:16], s[17:19]
    if not all(_digits(x, n) for x, n in ((y, 4), (mo, 2), (d, 2), (h, 2), (mi, 2), (sec, 2))):
        return False
    rest = s[19:]
    if rest.startswith("."):                 # 1..6 fractional digits, then the zone
        i = 1
        while i < len(rest) and rest[i] in _DIG:
            i += 1
        if not 2 <= i <= 7:
            return False
        rest = rest[i:]
    if rest == "Z":
        mins = 0
    elif len(rest) == 6 and rest[0] in "+-" and _digits(rest[1:3], 2) and rest[3] == ":" and _digits(rest[4:6], 2):
        oh, om = int(rest[1:3]), int(rest[4:6])
        if oh > 23 or om > 59:
            return False
        mins = (oh * 60 + om) * (1 if rest[0] == "+" else -1)
    else:
        return False
    try:
        local = datetime(int(y), int(mo), int(d), int(h), int(mi), int(sec))   # ValueError: impossible date/time
        local - timedelta(minutes=mins)                                         # OverflowError: UTC out of range
    except (ValueError, OverflowError):
        return False
    return True


print("1. the two reported timestamps")
for ts in ("0001-01-01T00:00:00+05:00", "9999-12-31T23:59:59-05:00"):
    kind, msg = outcome(lambda ts=ts: S.parse_utc(ts))
    check(f"1a: parse_utc({ts}) raises ValueError, not OverflowError", kind == "value_error", kind)
    check(f"1b: its message explains the range problem", "range" in msg)
    for key in ("starts_at", "ends_at"):
        kind, res = outcome(lambda ts=ts, key=key: S.validate_document(doc_with(**{key: ts})))
        check(f"1c: validate_document({key}={ts}) does not raise", kind == "ok", kind)
        if kind == "ok":
            check(f"1d: ...and reports invalid with code bad_timestamp",
                  (not res.ok) and "bad_timestamp" in res.codes(), str(res.codes()))
    kind, loaded = outcome(lambda ts=ts: D.load_text(json.dumps(doc_with(starts_at=ts))))
    check(f"1e: load_text with {ts} does not raise", kind == "ok", kind)
    if kind == "ok":
        check("1f: ...and the status is 'invalid' with no document handed to consumers",
              loaded.status == "invalid" and loaded.doc is None and loaded.doc_hash is None)

print("1b. explicit strictness cases (not generated)")
for label, ts in (("trailing newline", "2026-10-10T06:00:00Z\n"), ("trailing CRLF", "2026-10-10T06:00:00Z\r\n"),
                  ("leading newline", "\n2026-10-10T06:00:00Z"), ("trailing space", "2026-10-10T06:00:00Z "),
                  ("Devanagari digits", "\u0968\u0966\u0968\u096c-10-10T06:00:00Z"),
                  ("Arabic-Indic digits", "\u0662\u0660\u0662\u0666-10-10T06:00:00Z"),
                  ("fullwidth digits", "\uff12\uff10\uff12\uff16-10-10T06:00:00Z"),
                  ("fullwidth digit in seconds", "2026-10-10T06:00:\uff10\uff10Z"),
                  ("lowercase t / z", "2026-10-10t06:00:00z"), ("space instead of T", "2026-10-10 06:00:00Z"),
                  ("no zone", "2026-10-10T06:00:00"), ("7 fractional digits", "2026-10-10T06:00:00.1234567Z"),
                  ("zone +24:00", "2026-10-10T06:00:00+24:00"), ("zone without colon", "2026-10-10T06:00:00+0530"),
                  ("leap second", "2026-10-10T06:00:60Z")):
    check(f"1b: {label} rejected by parse_utc", outcome(lambda ts=ts: S.parse_utc(ts))[0] == "value_error")
    check(f"1b: {label} rejected by the oracle too (so the fuzz agrees)", oracle_accepts(ts) is False)
    kind, res = outcome(lambda ts=ts: S.validate_document(doc_with(starts_at=ts)))
    check(f"1b: {label} gives an invalid document, never an exception", kind == "ok" and not res.ok and "bad_timestamp" in res.codes())
    kind, ld = outcome(lambda ts=ts: D.load_text(json.dumps(doc_with(starts_at=ts))))
    check(f"1b: {label} loads as invalid", kind == "ok" and ld.status == "invalid")

print("2. valid timestamps keep working (unchanged behaviour)")
Z = timezone.utc
check("2a: Z", S.parse_utc("2026-10-10T06:00:00Z") == datetime(2026, 10, 10, 6, 0, tzinfo=Z))
check("2b: +05:30 normalises to UTC", S.parse_utc("2026-10-10T11:30:00+05:30") == datetime(2026, 10, 10, 6, 0, tzinfo=Z))
check("2c: -08:00 normalises to UTC", S.parse_utc("2026-10-10T00:00:00-08:00") == datetime(2026, 10, 10, 8, 0, tzinfo=Z))
check("2d: result is an aware UTC datetime", S.parse_utc("2026-10-10T06:00:00+01:00").utcoffset() == timedelta(0))
check("2e: fractional seconds accepted (and ignored, as before)", S.parse_utc("2026-10-10T06:00:00.123456Z") == datetime(2026, 10, 10, 6, 0, tzinfo=Z))
check("2f: -00:00 equals Z", S.parse_utc("2026-10-10T06:00:00-00:00") == S.parse_utc("2026-10-10T06:00:00Z"))
check("2g: a leap day is valid", S.parse_utc("2028-02-29T00:00:00Z").day == 29)
check("2h: a valid full document still validates",
      S.validate_document(doc_with(starts_at="2026-10-10T06:00:00Z", ends_at="2026-10-10T18:00:00+05:30")).ok)
check("2i: a valid document still loads as ok", D.load_text(json.dumps(doc_with(starts_at="2026-10-10T06:00:00Z"))).ok)

print("3. the representable boundary is exact (no over-rejection)")
check("3a: earliest representable instant accepted",
      S.parse_utc("0001-01-01T00:00:00Z") == datetime.min.replace(tzinfo=Z))
check("3b: local 0001-01-01T05:00+05:00 (= UTC min) accepted",
      S.parse_utc("0001-01-01T05:00:00+05:00") == datetime.min.replace(tzinfo=Z))
check("3c: one second earlier than UTC min rejected",
      outcome(lambda: S.parse_utc("0001-01-01T04:59:59+05:00"))[0] == "value_error")
check("3d: 9999-12-31T23:59:59Z accepted", S.parse_utc("9999-12-31T23:59:59Z").year == 9999)
check("3e: 9999-12-31T23:59:59+05:00 (earlier in UTC) accepted", S.parse_utc("9999-12-31T23:59:59+05:00").year == 9999)
check("3f: 9999-12-31T23:59:59-00:01 (just past UTC max) rejected",
      outcome(lambda: S.parse_utc("9999-12-31T23:59:59-00:01"))[0] == "value_error")
for ts in ("0001-01-01T00:00:00-23:59", "9999-12-31T23:59:59+23:59", "0001-01-01T00:00:00+23:59", "9999-12-31T23:59:59-23:59"):
    kind, _ = outcome(lambda ts=ts: S.parse_utc(ts))
    check(f"3g: {ts} -> {'accepted' if oracle_accepts(ts) else 'rejected'} exactly as the independent oracle says",
          (kind == "ok") == oracle_accepts(ts) and not kind.startswith("RAISED"), kind)

print("4. seeded fuzz over timestamp strings (reproducible)")
SEED = 20261010
rng = random.Random(SEED)
BASES = ["2026-10-10T06:00:00Z", "2026-10-10T11:30:00+05:30", "0001-01-01T00:00:00+05:00",
         "9999-12-31T23:59:59-05:00", "2028-02-29T23:59:59.999999-12:00", "1970-01-01T00:00:00+00:00"]
JUNK = ["", " ", "Z", "T", "+", "-", ":", "9", "0", "/", "०", " ", "\x00", "e", "\U0001F600"]


def mutate(s):
    kind = rng.randrange(7)
    i = rng.randrange(len(s)) if s else 0
    if kind == 0:   # substitute a char
        return s[:i] + rng.choice(JUNK + list("0123456789")) + s[i + 1:]
    if kind == 1:   # delete a char
        return s[:i] + s[i + 1:]
    if kind == 2:   # insert junk
        return s[:i] + rng.choice(JUNK) + s[i:]
    if kind == 3:   # push every digit to an extreme
        return re.sub(r"\d", lambda m: rng.choice("09"), s)
    if kind == 4:   # truncate
        return s[:rng.randrange(len(s) + 1)]
    if kind == 5:   # swap the offset for an extreme one
        return re.sub(r"(Z|[+-]\d{2}:\d{2})$", rng.choice(["+23:59", "-23:59", "+24:00", "-00:60", "Z", "+00:00"]), s)
    return s + rng.choice(JUNK)


def gen():
    if rng.random() < 0.35:   # structured: regex-valid extremes (the defect's family)
        y = rng.choice(["0001", "0002", "1969", "2026", "9998", "9999", "0000", "\u0968\u0966\u0968\u096c"])
        mo = rng.choice(["01", "02", "12", "00", "13"])
        d = rng.choice(["01", "28", "29", "30", "31", "00", "32"])
        t = "%s:%s:%s" % (rng.choice(["00", "05", "23", "24"]), rng.choice(["00", "59", "60"]), rng.choice(["00", "59", "60"]))
        off = rng.choice(["Z", "+00:00", "+05:00", "-05:00", "+23:59", "-23:59", "+24:00", "-12:00", "+14:00"])
        return "%s-%s-%sT%s%s%s" % (y, mo, d, t, off, rng.choice(["", "", "", "", "\n"]))
    s = rng.choice(BASES)
    for _ in range(rng.randrange(1, 4)):
        s = mutate(s)
    return s


N = 6000
seen = {"accepted": 0, "rejected": 0, "defect_family": 0}
escaped, disagree, doc_escaped, doc_disagree, load_disagree = [], [], [], [], []
for _ in range(N):
    s = gen()
    want = oracle_accepts(s)
    kind, val = outcome(lambda s=s: S.parse_utc(s))
    if kind.startswith("RAISED"):
        escaped.append((s, kind))
    elif (kind == "ok") != want:
        disagree.append((s, kind, want))
    seen["accepted" if want else "rejected"] += 1
    if want is False and s.isascii() and s[:4] in ("0001", "9999") and len(s) >= 20:
        seen["defect_family"] += 1
    # the same value through the public entry points
    dk, res = outcome(lambda s=s: S.validate_document(doc_with(starts_at=s)))
    if dk != "ok":
        doc_escaped.append((s, dk))
    elif res.ok != want:
        doc_disagree.append((s, res.ok, want))
    text = json.dumps(doc_with(starts_at=s))
    lk, ld = outcome(lambda text=text: D.load_text(text))
    if lk != "ok":
        doc_escaped.append((s, "load:" + lk))
    elif (ld.status == "ok") != want:
        load_disagree.append((s, ld.status, want))
check(f"4a: parse_utc never raised anything but ValueError over {N} generated strings", not escaped, str(escaped[:3]))
check("4b: parse_utc agrees with the independent oracle on every string (nothing bad accepted, nothing good rejected)", not disagree, str(disagree[:3]))
check("4c: validate_document never raised for any generated timestamp", not doc_escaped, str(doc_escaped[:3]))
check("4d: validate_document's ok/invalid verdict equals the oracle for every string", not doc_disagree, str(doc_disagree[:3]))
check("4e: load_text status ('ok' only if the oracle accepts) agrees for every string", not load_disagree, str(load_disagree[:3]))
check("4f: the fuzz genuinely exercised both outcomes and the defect family",
      seen["accepted"] > 200 and seen["rejected"] > 2000 and seen["defect_family"] > 20, str(seen))
rng = random.Random(SEED)
first = [gen() for _ in range(50)]
rng = random.Random(SEED)
check("4g: the same seed regenerates the same strings (reproducible)", first == [gen() for _ in range(50)])

print("5. seeded whole-document fuzz (the earlier failing seed family)")
rng = random.Random(1)
BASE_DOC = {"schema_version": 1, "stories": {"5": {"title": {"en": "x"}}},
            "placements": [{"id": "a", "scope": "home", "story_id": "5", "action": "pin", "position": 1,
                            "starts_at": "2026-10-10T06:00:00Z", "ends_at": "2026-10-11T06:00:00Z"}]}
VALS = [None, True, 0, -1, 10 ** 30, 1e999, "", "x" * 5000, [], {}, [[]], {"a": {"b": [None]}},
        "2026-13-45T99:99:99Z", "0001-01-01T00:00:00+23:59", "0001-01-01T00:00:00+05:00",
        "9999-12-31T23:59:59-05:00", "9999-12-31T23:59:59-23:59"]


def mut_doc(o):
    if isinstance(o, dict) and o:
        k = rng.choice(list(o)); o = dict(o)
        o[k] = rng.choice(VALS) if rng.random() < .4 else mut_doc(o[k]); return o
    if isinstance(o, list) and o:
        i = rng.randrange(len(o)); o = list(o)
        o[i] = rng.choice(VALS) if rng.random() < .4 else mut_doc(o[i]); return o
    return rng.choice(VALS)


bad, accepted_garbage = [], []
for _ in range(5000):
    d = BASE_DOC
    for _ in range(rng.randint(1, 3)):
        d = mut_doc(d)
    kind, res = outcome(lambda d=d: S.validate_document(d))
    if kind != "ok":
        bad.append((kind, json.dumps(d, default=str)[:100]))
        continue
    if res.ok:
        # Anything ACCEPTED must be genuinely clean: every placement timestamp it carries has to
        # pass the independent oracle. (Only timestamp fields count: the poisoned strings are
        # legitimate plain text inside a title and are rightly accepted there.)
        pls = d.get("placements") if isinstance(d, dict) else None
        for p in (pls if isinstance(pls, list) else []):
            for key in ("starts_at", "ends_at"):
                if isinstance(p, dict) and key in p and not oracle_accepts(p[key]):
                    accepted_garbage.append("%s=%r" % (key, p[key]))
check("5a: validate_document never raised over 5000 mutated documents", not bad, str(bad[:3]))
check("5b: no accepted document carries a timestamp the independent oracle rejects", not accepted_garbage, str(accepted_garbage[:3]))

print("6. documented contract for consumers")
check("6a: resolve.py's parse_utc calls are only reachable after validation (document is ok)",
      D.load_text(json.dumps(doc_with(ends_at="9999-12-31T23:59:59-05:00"))).doc is None)

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("=" * 60)
print("ALL EDITORIAL TIMESTAMP CHECKS PASSED")
