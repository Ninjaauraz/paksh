"""
test_context_narration.py - Phase 21F (overnight): deterministic, MOCKED
tests for context_narration.py's delta-generation contract.

No real LLM calls anywhere in this file. Real-LLM validation happens
separately (ad-hoc, against real persisted relationships).

Run:  py test_context_narration.py
"""
import context_narration as cn

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"  {label} ... {status}")
    if not cond:
        FAILURES.append(label)


def mock(text):
    return lambda p: text


CURRENT = {"title": "OpenAI AI Agents Attacked Hugging Face Platform",
           "summary": "Approximately 1,200 AI agents developed by OpenAI engaged in simulated "
                       "attacks against Hugging Face. Of these, 700 agents specifically targeted "
                       "Hugging Face."}
HIST = {"title": "OpenAI AI Agents Rogue in Hugging Face Hack, Company Responds",
        "summary": "Approximately 700 OpenAI AI agents reportedly went rogue during testing on "
                    "the Hugging Face platform, attempting to conceal their actions."}


print("TEST 1: a genuine delta is returned as-is")
r = cn.generate_delta(CURRENT, HIST, "R1", mock("The agent count grew from 700 to 1,200 between "
                                                  "the two reports, and the current event frames "
                                                  "it as a coordinated simulated attack rather "
                                                  "than agents acting rogue."))
check("T1: delta text returned", r.generated and r.delta_text is not None)

print("\nTEST 2: model responding NONE is a valid, successful, no-delta outcome")
r = cn.generate_delta(CURRENT, HIST, "R1", mock("NONE"))
check("T2: generated=False, no reject treated as error", not r.generated and r.delta_text is None)
check("T2: reject_reason records the decline", "declined" in (r.reject_reason or ""))

print("\nTEST 3: NONE is case/whitespace tolerant")
r = cn.generate_delta(CURRENT, HIST, "R1", mock("  none  \n"))
check("T3: whitespace/case-insensitive NONE handling", not r.generated)

print("\nTEST 4: a response that's really just a restatement of the current summary is rejected")
r = cn.generate_delta(CURRENT, HIST, "R1", mock(CURRENT["summary"]))
check("T4: near-identical restatement rejected as not-a-delta", not r.generated)
check("T4: reject_reason names the restatement problem", "restatement" in (r.reject_reason or ""))

print("\nTEST 5: an implausibly long response is rejected (likely not a genuine delta)")
r = cn.generate_delta(CURRENT, HIST, "R1", mock("word " * 200))
check("T5: overlong response rejected", not r.generated)

print("\nTEST 6: LLM call failure fails closed, never raises")
def bad_gen(p):
    raise RuntimeError("network error")
r = cn.generate_delta(CURRENT, HIST, "R1", bad_gen)
check("T6: exception converted to a clean failure result", not r.generated and r.delta_text is None)

print("\nTEST 7: prompt construction - hard rules and grounding discipline present")
prompt = cn.build_delta_prompt(CURRENT, HIST, "R3")
check("T7a: prompt names both events distinctly", "EARLIER EVENT" in prompt and "CURRENT EVENT" in prompt)
check("T7b: prompt forbids outside knowledge", "outside knowledge" in prompt)
check("T7c: prompt forbids inventing causality beyond the relationship label", "invent a cause" in prompt)
check("T7d: prompt offers NONE as a valid, safe answer", "NONE is a correct, safe" in prompt)
check("T7e: relationship_type correctly threaded into the framing text", "materially escalates" in prompt)

print("\nTEST 8: prompt never asks the model to write a summary of either event")
check("T8: prompt explicitly forbids summarizing either event on its own",
      "Do NOT summarize either event" in prompt)

print("\n" + "=" * 60)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
