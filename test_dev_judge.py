"""
test_dev_judge.py - the veto-only development judge (dev_judge.py): prompt, validation, cache, failure behaviour. No network: a fake
generator stands in for the provider pool. NOT wired into the pipeline (measured, not adopted: docs/PHASE13). Run: py test_dev_judge.py
"""
import json

import dev_judge as dj

FAILURES = []


def check(label, cond, extra=""):
    print(f"  {label} ... {'OK' if cond else 'FAIL'} {extra if not cond else ''}")
    if not cond:
        FAILURES.append(label)


CAND = "Police arrest owner of chemical plant after fatal blaze"
EARLIER = ["Fire at chemical plant kills twelve workers", "Rescue teams pull survivors from burning chemical plant"]

print("TEST 1: prompt")
p = dj.build_prompt("ARREST", CAND, EARLIER + [f"h{i}" for i in range(20)])
check("1a: the prompt carries only the candidate, the cue and at most 6 earlier headlines, and asks for CANNOT_TELL when unsure",
      CAND in p and p.count("\n- ") == dj.MAX_EARLIER and "CANNOT_TELL" in p and "outside knowledge" in p)
check("1b: the cache key depends on the prompt version and the prompt", dj.cache_key(p) == dj.cache_key(p) and dj.cache_key(p) != dj.cache_key(p + " "))

print("\nTEST 2: validation - a verdict must be backed by the headlines")
v = dj.parse_and_validate('{"verdict": "NEW_DEVELOPMENT", "quote": "Police arrest owner of chemical plant", "already_in": ""}', CAND, EARLIER)
check("2a: NEW_DEVELOPMENT with a real quote from the candidate is accepted", v["valid"] and v["verdict"] == "NEW_DEVELOPMENT")
v = dj.parse_and_validate('{"verdict": "NEW_DEVELOPMENT", "quote": "the owner confessed", "already_in": ""}', CAND, EARLIER)
check("2b: NEW_DEVELOPMENT quoting words that are not in the headline is rejected -> CANNOT_TELL", not v["valid"] and v["verdict"] == "CANNOT_TELL")
v = dj.parse_and_validate('{"verdict": "ALREADY_REPORTED", "quote": "", "already_in": "' + EARLIER[0] + '"}', CAND, EARLIER)
check("2c: ALREADY_REPORTED naming one of the given earlier headlines is accepted", v["valid"] and v["verdict"] == "ALREADY_REPORTED")
v = dj.parse_and_validate('{"verdict": "ALREADY_REPORTED", "quote": "", "already_in": "some headline I invented that is long enough"}', CAND, EARLIER)
check("2d: ALREADY_REPORTED naming a headline that was not given is rejected", not v["valid"])
for bad in ("not json at all", '{"verdict": "PROBABLY"}', "[1,2]", "", None):
    check(f"2e: malformed output {str(bad)[:18]!r} -> CANNOT_TELL, never an exception", dj.parse_and_validate(bad, CAND, EARLIER)["verdict"] == "CANNOT_TELL")
v = dj.parse_and_validate('Sure! {"verdict": "NOT_A_DEVELOPMENT", "quote": "", "already_in": ""} hope that helps', CAND, EARLIER)
check("2f: JSON wrapped in chatter is still read", v["valid"] and v["verdict"] == "NOT_A_DEVELOPMENT")

print("\nTEST 3: veto-only semantics")
mk = lambda verdict, valid=True: {"verdict": verdict, "valid": valid}
check("3a: only a VALID already-reported / not-a-development removes a candidate",
      not dj.keep_candidate(mk("ALREADY_REPORTED")) and not dj.keep_candidate(mk("NOT_A_DEVELOPMENT")))
check("3b: NEW_DEVELOPMENT, CANNOT_TELL and every invalid answer KEEP the candidate (the model never makes a real development disappear silently)",
      dj.keep_candidate(mk("NEW_DEVELOPMENT")) and dj.keep_candidate(mk("CANNOT_TELL")) and dj.keep_candidate(mk("ALREADY_REPORTED", valid=False)))

print("\nTEST 4: cache and failure")
calls = []


def gen(prompt):
    calls.append(prompt)
    return json.dumps({"verdict": "NEW_DEVELOPMENT", "quote": "Police arrest owner", "already_in": ""})


cache = {}
a = dj.judge("ARREST", CAND, EARLIER, generate=gen, cache=cache)
b = dj.judge("ARREST", CAND, EARLIER, generate=gen, cache=cache)
check("4a: a candidate is judged once; the second call is a cache hit with the same verdict", len(calls) == 1 and not a["cached"] and b["cached"] and a["verdict"] == b["verdict"])


def boom(prompt):
    raise RuntimeError("provider down")


f = dj.judge("ARREST", CAND + " (2)", EARLIER, generate=boom, cache=cache)
check("4b: a provider failure returns CANNOT_TELL/invalid (candidate kept), is not cached, and never raises", f["verdict"] == "CANNOT_TELL" and not f["valid"] and dj.keep_candidate(f) and len(cache) == 1)

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
    raise SystemExit(1)
print("ALL dev_judge CHECKS PASSED")
