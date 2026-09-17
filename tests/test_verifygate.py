#!/usr/bin/env python3
"""
test_verifygate.py — a turn that changed a repo and never ran anything is not
finished, whatever it says.

WHY THIS EXISTS
===============
WORK MODE's contract already tells the model to verify, at length:
"VERIFY, DON'T ASSUME", "ITERATE UNTIL IT ACTUALLY PASSES". That is advice,
and advice is what a model drops on step forty of a long job. Anthropic's
guidance names both the failure and the split:

    "Claude stops when the work looks done. Without a check it can run,
     'looks done' is the only signal available, and you become the
     verification loop."

...and: a prompt instruction is advisory; a Stop hook is deterministic and
"blocks the turn from ending until it passes".

Basilisk already HAD the check. `workspace_verify` re-runs the repo's tests and
classifies the result against a baseline, so it reports what you fixed AND what
you broke. The gap was never the check — it was that nothing made the turn go
through it.

THE SHAPE
=========
This is the promise gate's architecture aimed at the other half of the product,
and it inherits the property that made that one hold up: IT DOES NOT READ THE
REPLY. Every earlier attempt at "did it really finish?" was a better reader of
the model's prose, and each was one phrasing away from failing. Two facts
decide it — files were written this request, and nothing was ever run to check
them.

Run:  python3 tests/test_verifygate.py
"""

from __future__ import annotations

import io
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


SRC = io.open(os.path.join(_ROOT, "basilisk.py"), encoding="utf-8").read()
CORE = io.open(os.path.join(_ROOT, "basilisk_core.py"), encoding="utf-8").read()


def _joined(text: str) -> str:
    """Close the seams between adjacent string literals.

    Every directive in this file is a Python implicit-concatenation run, so a
    sentence in the source is split at whatever column the formatter chose.
    A raw substring probe for it then fails for a reason that is a property of
    the formatter and nothing to do with the code. test_placeholders.py hit
    this exact trap; the fix is to join before matching, not to write shorter
    probes."""
    return re.sub(r'"\s*\n\s*"', "", text)


SRCJ = _joined(SRC)
COREJ = _joined(CORE)
# The joiner must actually DO something, or every probe below silently
# degrades to a raw substring match on a sentence that is never contiguous.
ck("the literal joiner closes real seams",
   len(SRCJ) < len(SRC) and "BUDGET: step %d of %d" in SRCJ)

# Lift the pure decision out without importing GTK.
_A = "_WORKSPACE_WRITE_TOOLS = frozenset({"
_B = "def forced_search_url("
ck("the decision lives where this suite expects it",
   SRC.count(_A) == 1 and SRC.count(_B) == 1)
_ns = {}
exec(SRC[SRC.index(_A):SRC.index(_B)], _ns)                      # noqa: S102
gap = _ns["unverified_work_gap"]
WRITES = _ns["_WORKSPACE_WRITE_TOOLS"]
VERIFIERS = _ns["_VERIFY_TOOLS"]


# ── 1. THE PROPERTY ──────────────────────────────────────────────────
print("\n== a repo was changed and nothing was run ==")
ck("bare write -> verify",
   gap({"workspace_read", "workspace_write"}) == "workspace_verify")
ck("replace counts as a write",
   gap({"workspace_search", "workspace_replace"}) == "workspace_verify")
ck("revert counts too — reverting is a change",
   gap({"workspace_revert"}) == "workspace_verify")
ck("several writes and no check still one verify",
   gap({"workspace_write", "workspace_replace", "workspace_read",
        "workspace_tree"}) == "workspace_verify")


# ── 2. THE COUNTER-PROPERTY, which matters more ──────────────────────
# A gate that fires when the model DID verify is a gate that gets switched
# off. Every one of these must end the turn silently.
print("\n== it already checked its own work ==")
for v in sorted(VERIFIERS):
    ck(f"{v} satisfies the gate",
       gap({"workspace_write", v}) is None)
ck("a read-only turn is not gated",
   gap({"workspace_read", "workspace_search", "workspace_tree"}) is None)
ck("a pure research turn is not gated",
   gap({"web_read", "web_search"}) is None)
ck("a turn that ran a command and wrote nothing is not gated",
   gap({"run"}) is None)
ck("a plain write_file outside a workspace is not gated",
   gap({"write_file"}) is None,
   "there is no repo to re-run, so workspace_verify has nothing to do")
ck("propose_edit is not gated",
   gap({"propose_edit"}) is None,
   "supervised mode: the operator clicks it, the gate is not the reviewer")
ck("an empty turn is not gated", gap(set()) is None)


# ── 3. ONCE PER REQUEST, NEVER A LOOP ────────────────────────────────
print("\n== a floor, not a loop ==")
ck("already_forced short-circuits",
   gap({"workspace_write"}, True) is None)
ck("and once it fires, a verifier has run, so it cannot re-arm",
   gap({"workspace_write", "workspace_verify"}) is None,
   "the gate's own action is what disarms it — belt as well as braces")
ck("the wiring carries a one-shot flag",
   "_forced_verify_done" in SRC
   and "self._forced_verify_done = True" in SRC)
ck("...reset per operator request, beside the other one-shots",
   re.search(r"self\._forced_fetch_done = False\n\s*"
             r"self\._forced_verify_done = False", SRC) is not None)


# ── 4. PURE AND TOTAL ────────────────────────────────────────────────
# A gate that raises is a gate that fails open on exactly the turn it exists
# to catch. This file has shipped that mistake before.
print("\n== junk in, None out ==")
for junk in (None, 0, "", "workspace_write", 12, object(), [None], {None: 1}):
    try:
        r = gap(junk)
        ok = r is None or r == "workspace_verify"
    except Exception as e:      # noqa: BLE001
        ok = False
        r = f"RAISED {type(e).__name__}"
    ck(f"survives {type(junk).__name__} input", ok, str(r))
# A string is iterable, so set("workspace_write") is a set of CHARACTERS —
# it must not accidentally match anything.
ck("a bare string argument cannot match a tool name",
   gap("workspace_write") is None)


# ── 5. THE WIRING ────────────────────────────────────────────────────
print("\n== wired at the turn-ending point, with the same guards ==")
_blk = SRC.split("# ── THE VERIFICATION GATE ──")
ck("the gate block exists", len(_blk) == 2)
_blk = _blk[1][:2600] if len(_blk) == 2 else ""
for guard in ("not executable", "not cancelled", "not self._stop_requested",
              "self.current_agent_mode", "not self._tools_locked",
              "not self._mission_active"):
    ck(f"guarded on {guard}", guard in _blk)
ck("it only fires when the turn is otherwise ENDING",
   _blk.index("not executable") < _blk.index("unverified_work_gap("),
   "firing mid-chain would interrupt a model that was still working")
ck("the synthesised call is a real parsed tool call",
   "parse_tool_calls(" in _blk and "executable = _rec" in _blk)
ck("the operator is told, not just the model",
   "self._activity_note(" in _blk and "self.terminal_log(" in _blk)
ck("the model is told why it got a result it did not ask for",
   "_deferred_note" in _blk and "CHANGED FILES" in _blk)
ck("...and is told that regressions are its own",
   "`broke` is non-empty those are YOUR regressions" in _joined(_blk))
ck("...and is told NOT to invent a verification",
   "not invent a verification you did not run" in _joined(_blk))


# ── 6. THE ERROR MESSAGE IS A PROMPT ─────────────────────────────────
# "prompt-engineer your error responses to clearly communicate specific and
# actionable improvements" — the gate can fire on a repo with no suite, and
# "no test command known" told the model what failed and nothing about what
# to do instead.
print("\n== the no-suite path is actionable ==")
ck("the bare error string is gone",
   '"error": "no test command known"}' not in CORE)
ck("it names the repair", '\\"command\\": \\"pytest -q\\"' in COREJ)
ck("...and the fallback when there is no suite at all",
   "prove the change another way" in COREJ)
ck("...and forbids reporting it as verified anyway",
   "Do not report the change as verified when nothing verified it" in COREJ)


# ── 7. BUDGET GROUND TRUTH ───────────────────────────────────────────
# "it's crucial for the agents to gain 'ground truth' from the environment at
# each step". The model was told to iterate until green with a large budget
# and never told where in that budget it was.
print("\n== the model is told where it is in its budget ==")
ck("a budget line is built for work turns", "_budget_line" in SRC)
ck("only on continuations",
   re.search(r'_budget_line = ""\n\s*if _continuation:', SRC) is not None,
   "on turn 1 it is always '1 of N' and says nothing")
ck("three bands, not one number",
   SRC.count("BUDGET: step %d of %d") == 3)
ck("nearly-out says land it",
   "you are nearly out" in SRC and "Do not start" in SRC)
ck("plenty-left says DON'T rush",
   "Do not rush the job or hand back a partial fix to save steps" in SRCJ,
   "a budget signal that only ever says 'hurry' makes it stop early — the "
   "exact thing this is meant to prevent")
ck("it rides the work addendum, not the cached system prompt",
   SRC.index("_budget_line = \"\"") > SRC.index("elif _leash_work:") - 3000)


print(f"\nverify gate: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
