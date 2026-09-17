#!/usr/bin/env python3
"""
test_plangate.py — the deterministic turn-ending gates, and the second answer.

THE THREE REPORTED FAILURES
===========================
    "it still sometimes stops when it's supposed to keep working"
    "it still doesn't stop when it's supposed to"
    "...and sends two answers"

REPRODUCED against the pre-fix tree, so these are measurements and not
opinions:

  * "I've fixed two of the five files. The remaining three need the same
    treatment." — reply_is_bare_stall says False (correctly: it announced
    nothing), reply_intends_action says False, reply_is_strong_conclusion
    says False. Nothing pushed, the turn ENDED, three files untouched.
  * A verifier that came back RED, followed by an honest paragraph about
    the tests being red, also ended the turn — v1.1.3.0 made the turn RUN
    the check and nothing made it care what the check SAID.
  * A complete answer + a gate-forced tool = the model writes the answer
    again, because from its side a forced tool result is indistinguishable
    from an ordinary mid-research one. Two complete answers, one question.

WHAT IS ASSERTED
================
The gates fire when they must, DO NOT fire when they must not (the
counter-property gets as many asserts as the property — a gate that will
not let a turn end gets switched off, and then it protects nothing), and
are total.

Run:  python3 tests/test_plangate.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import types

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


# ── GTK stub ─────────────────────────────────────────────────────────
class _Meta(type):
    def __getattr__(cls, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return _Obj


class _Obj(metaclass=_Meta):
    def __init__(self, *a, **k):
        pass

    def __call__(self, *a, **k):
        return _Obj()

    def __getattr__(self, n):
        return _Obj()


class _Mod(types.ModuleType):
    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return _Obj

    def require_version(self, *a, **k):
        pass


for _m in ("gi", "gi.repository", "gi.repository.Gtk", "gi.repository.Adw",
           "gi.repository.GLib", "gi.repository.Gio", "gi.repository.Gdk",
           "gi.repository.GdkPixbuf", "gi.repository.Pango",
           "gi.repository.GObject", "gi.repository.GtkSource",
           "gi.repository.Vte", "gi.repository.Soup"):
    sys.modules[_m] = _Mod(_m)
sys.modules["gi"].require_version = lambda *a, **k: None

import basilisk as Bk                                           # noqa: E402
import basilisk_core as Bc                                      # noqa: E402
from basilisk_ext.tasks import TaskPlan                         # noqa: E402

SRC = open(os.path.join(_ROOT, "basilisk.py"), encoding="utf-8").read()


def plan(*pairs):
    """plan(("a","done"), ("b","open")) -> a TaskPlan in that state."""
    p = TaskPlan()
    p.set_plan([t for t, _ in pairs])
    for i, (_, st) in enumerate(pairs, 1):
        if st != "open":
            p.update(str(i), st,
                     "reason" if st in ("blocked", "dropped") else "")
    return p


# ═════════════════════════════════════════════════════════════════════
#  1. THE LEDGER GATE — unfinished_plan_gap
# ═════════════════════════════════════════════════════════════════════
print("\n== the ledger gate fires on unfinished work ==")
g = Bk.unfinished_plan_gap(plan(("read it", "done"), ("fix it", "open"),
                                ("test it", "open")), 0)
ck("open items produce a push", bool(g))
ck("…it is a tool_result envelope, like every other push",
   g.startswith("<tool_result>") and g.endswith("</tool_result>"))
ck("…it says plainly the turn is not over", "THE TURN IS NOT OVER" in g)
ck("…it names how many are left", "2 item(s) open" in g)
ck("…it names the items themselves", "fix it" in g and "test it" in g)
ck("…it names the NEXT one specifically", "'fix it'" in g)
ck("…it demands a tool call, not a description",
   "TOOL CALL" in g and "not a description of it" in g)
ck("…it offers the honest way out (blocked with a reason)",
   "blocked" in g and "exactly what stopped you" in g)
ck("…and the way out of a STALE plan (close it, then report)",
   "stale" in g and "final report" in g)

print("\n== the ledger gate does NOT fire when it must not ==")
ck("no plan at all -> silent (absent is not unfinished)",
   Bk.unfinished_plan_gap(None, 0) is None)
ck("an empty plan -> silent", Bk.unfinished_plan_gap(TaskPlan(), 0) is None)
ck("every item done -> silent",
   Bk.unfinished_plan_gap(plan(("a", "done"), ("b", "done")), 0) is None)
ck("done + BLOCKED -> silent (blocked closes an item)",
   Bk.unfinished_plan_gap(plan(("a", "done"), ("b", "blocked")), 0) is None)
ck("done + DROPPED -> silent",
   Bk.unfinished_plan_gap(plan(("a", "done"), ("b", "dropped")), 0) is None)
ck("the push cap stops it dead (a model that will not close an item "
   "cannot hold the turn forever)",
   Bk.unfinished_plan_gap(plan(("a", "open")), 6) is None)
ck("…at exactly the cap, not one past it",
   Bk.unfinished_plan_gap(plan(("a", "open")), 5) is not None)
ck("a cap of 0 disables it entirely",
   Bk.unfinished_plan_gap(plan(("a", "open")), 0, cap=0) is None)

print("\n== the ledger gate is total ==")
for junk in (None, 0, "", [], {}, object(), types.SimpleNamespace()):
    try:
        out = Bk.unfinished_plan_gap(junk, 0)
        ok = out is None or isinstance(out, str)
    except Exception as e:
        ok = False
        out = f"RAISED {type(e).__name__}"
    ck(f"junk plan {junk!r:.18} -> None or str", ok, str(out)[:60])
for junk in (None, "x", -1, 1e9, [], object()):
    try:
        Bk.unfinished_plan_gap(plan(("a", "open")), junk)
        ck(f"junk pushes {junk!r:.14} does not raise", True)
    except Exception as e:
        ck(f"junk pushes {junk!r:.14} does not raise", False, str(e)[:60])


# ═════════════════════════════════════════════════════════════════════
#  2. THE FAILING-VERIFICATION GATE
# ═════════════════════════════════════════════════════════════════════
print("\n== red is not a stopping point ==")
r = Bk.failing_verification_gap("regression: test_auth", 0)
ck("a regression produces a push", bool(r))
ck("…and says the change BROKE something", "BROKE something" in r)
ck("…and forbids stopping there", "never an acceptable place to stop" in r)
ck("…and offers revert as an honest outcome", "workspace_revert" in r)
n = Bk.failing_verification_gap("no-change", 0)
ck("a non-green verdict also pushes", bool(n))
ck("…and forbids re-guessing from the same reasoning",
   "same guess" in n)
ck("…and permits stopping on a PRE-EXISTING failure, named",
   "predates your changes" in n)

print("\n== …and does not fire when it must not ==")
ck("green -> silent", Bk.failing_verification_gap("", 0) is None)
ck("whitespace verdict -> silent", Bk.failing_verification_gap("   ", 0) is None)
ck("the cap stops it", Bk.failing_verification_gap("regression", 2) is None)
ck("…at exactly the cap", Bk.failing_verification_gap("regression", 1) is not None)
for junk in (None, 0, [], {}, object()):
    try:
        out = Bk.failing_verification_gap(junk, 0)
        ck(f"junk verdict {junk!r:.14} -> None or str",
           out is None or isinstance(out, str))
    except Exception as e:
        ck(f"junk verdict {junk!r:.14} -> None or str", False, str(e)[:50])


# ═════════════════════════════════════════════════════════════════════
#  3. GROUND TRUTH — verifier_verdict reads the TOOL, not the model
# ═════════════════════════════════════════════════════════════════════
print("\n== the verdict comes off the tool result, not the prose ==")
ck("a regression is detected and names what broke",
   Bk.verifier_verdict("workspace_verify",
                       json.dumps({"ok": True, "green": False,
                                   "broke": ["test_a", "test_b"],
                                   "verdict": "regression"}))
   .startswith("regression: test_a"))
ck("green is silence",
   Bk.verifier_verdict("workspace_verify",
                       json.dumps({"ok": True, "green": True,
                                   "verdict": "green"})) == "")
ck("a non-green verdict with nothing broken still reports",
   Bk.verifier_verdict("workspace_verify",
                       json.dumps({"ok": True, "green": False,
                                   "verdict": "no-change"})) == "no-change")
ck("a TOOL ERROR is not a red suite (no test command != failing tests)",
   Bk.verifier_verdict("workspace_verify",
                       json.dumps({"ok": False,
                                   "error": "no test command known"})) == "")
ck("no baseline means it attributes nothing, so it says nothing",
   Bk.verifier_verdict("workspace_verify",
                       json.dumps({"ok": True, "no_baseline": True})) == "")
ck("another tool's output is never read as a verdict",
   Bk.verifier_verdict("read_file",
                       json.dumps({"green": False,
                                   "verdict": "regression"})) == "")
ck("json embedded in surrounding text is still found",
   Bk.verifier_verdict("workspace_verify",
                       'ran it\n{"ok":true,"green":false,'
                       '"verdict":"regression","broke":["x"]}\ndone') != "")
print("  -- totality --")
for junk in (None, "", "not json", "{", "[]", "null", "123", b"bytes",
             json.dumps([1, 2, 3]), object()):
    try:
        out = Bk.verifier_verdict("workspace_verify", junk)
        ck(f"junk result {str(junk)[:16]!r} -> a string",
           isinstance(out, str))
    except Exception as e:
        ck(f"junk result {str(junk)[:16]!r} -> a string", False, str(e)[:50])
ck("a parse failure NEVER invents a red verdict",
   Bk.verifier_verdict("workspace_verify", "total garbage") == "")


# ═════════════════════════════════════════════════════════════════════
#  4. THE SECOND ANSWER
# ═════════════════════════════════════════════════════════════════════
# The gates fire at the moment a COMPLETE reply has been written and no
# tool call was emitted. That reply is already on screen. Unless the
# continuation is told so, the model answers the question again — which is
# exactly what the operator reported.
print("\n== the gate-forced continuation says the answer is already on screen ==")
NOTE = Bk._GATE_CONTINUATION_NOTE
ck("the note exists as ONE constant (two copies would drift)",
   SRC.count("_GATE_CONTINUATION_NOTE = (") == 1)
ck("…and is used by BOTH gates",
   SRC.count("+ _GATE_CONTINUATION_NOTE)") == 2)
ck("it states the reply is already on screen",
   "ALREADY ON SCREEN" in NOTE)
ck("…and that the operator has read it", "operator has read it" in NOTE)
ck("…and forbids answering again", "do NOT answer the question again" in NOTE)
ck("…and forbids a reworded restatement",
   "restate your conclusion in different words" in NOTE)
ck("…and names what a repeat reads like", "stutter" in NOTE)
ck("it asks for the DELTA instead", "DELTA" in NOTE)
ck("…and covers the agreeing branch (one short line)",
   "confirming it" in NOTE and "Two sentences at most" in NOTE)
ck("…the CONTRADICTING branch (correct yourself, cite it)",
   "CONTRADICTS" in NOTE and "correct the specific part" in NOTE)
ck("…and the more-work branch (stop writing, call the tool)",
   "emit the next" in NOTE and "tool call instead" in NOTE)

print("\n== both gates mark the turn as gate-forced ==")
ck("the fetch gate marks it", '_gate_forced = "fetch"' in SRC)
ck("the verify gate marks it", '_gate_forced = "verify"' in SRC)
ck("…and it is cleared per request, with the other per-request state",
   re.search(r"self\._forced_verify_done = False\s*\n.*\n.*_plan_reset\(\)",
             SRC) is not None
   or 'self._gate_forced = ""' in SRC.split("_plan_reset()")[1][:400])


# ═════════════════════════════════════════════════════════════════════
#  5. THE ORDERING — facts before heuristics
# ═════════════════════════════════════════════════════════════════════
print("\n== the deterministic gates run BEFORE the prose heuristic ==")
_tail = SRC.split("def _on_stream_done_body", 1)[1]
_i_plan = _tail.find("unfinished_plan_gap(")
_i_ver = _tail.find("failing_verification_gap(")
_i_stall = _tail.find("ANSWER-MODE STALL NUDGE (the block below is this one)")
ck("all three are present in the turn-ending body",
   min(_i_plan, _i_ver, _i_stall) > 0,
   f"plan={_i_plan} verify={_i_ver} stall={_i_stall}")
ck("the ledger gate runs before the stall detector", _i_plan < _i_stall)
ck("the verification gate runs before the stall detector", _i_ver < _i_stall)
ck("the ledger gate runs before the verification gate", _i_plan < _i_ver)

print("\n== a COMPLETE plan suppresses the prose nudge entirely ==")
ck("the completion branch exists", "_plan_complete" in SRC)
ck("…and it zeroes the nudge budget",
   re.search(r"if _plan_complete:\s*\n\s*_nudge_cap = 0", SRC) is not None)
ck("…and it is announced once, not once per round-trip",
   "_plan_done_announced" in SRC)

print("\n== every gate respects stop / locks / mission mode ==")
# THE CALL SITE, NOT THE DEFINITION. Each of these names appears twice in
# the file: once as `def ...` and once where the turn-ending body calls it.
# Slicing back from the FIRST occurrence measures the function's own
# docstring and reports a missing guard on correct code — the checker being
# wrong, which this project has now been bitten by often enough to check
# for. rsplit takes the last occurrence, which is the call.
for gate, needle in (("ledger", "unfinished_plan_gap("),
                     ("verification", "failing_verification_gap(")):
    assert SRC.count(needle) == 2, (gate, SRC.count(needle))
    _blk = SRC.rsplit(needle, 1)[0][-1200:]
    assert "def " + needle not in _blk, "still looking at the definition"
    ck(f"the {gate} gate is guarded on the stop button",
       "not self._stop_requested" in _blk)
    ck(f"the {gate} gate is guarded on tools being locked",
       "not self._tools_locked" in _blk)
    ck(f"the {gate} gate does not fire during a mission",
       "not self._mission_active" in _blk)
    ck(f"the {gate} gate does not fire on a cancelled turn",
       "not cancelled" in _blk)
ck("the ledger gate is behind its settings switch",
   'settings.get("plan_enabled"' in SRC)


# ═════════════════════════════════════════════════════════════════════
#  6. THE PLAN IS PER REQUEST
# ═════════════════════════════════════════════════════════════════════
print("\n== the ledger is reset per REQUEST, not per chat ==")
ck("_plan_reset exists", "def _plan_reset" in SRC)
ck("…and is called in the fresh-request block",
   "_plan_reset()" in SRC.split("if self.streaming_chat_id is None:")[1][:1400])
ck("…and it clears the push counters too",
   "_plan_pushes = 0" in SRC.split("def _plan_reset")[1][:700])
ck("the reason is written down (a stale item must not hold a new "
   "question hostage)",
   "hostage" in SRC.split("def _plan_reset")[1][:900])
ck("the verifier flag is reset with it",
   '_verify_red = ""' in SRC.split("_plan_reset()")[1][:400])

print("\n== ground truth is recorded at ONE choke point ==")
# Wide enough to reach the verdict block. An earlier draft took [:4000] and
# the block starts at 3804 — a probe that only just fails is a probe that
# will silently start failing when a neighbour grows by a line.
_feed = SRC.split("def _feed_tool_result")[1][:6000]
ck("verifier_verdict is called from _feed_tool_result", "verifier_verdict(" in _feed)
ck("…and it is the only call site (no second, drifting one)",
   SRC.count("verifier_verdict(_tool") == 1)
ck("a CLEAN verify clears the red flag (a fixed failure must not hold "
   "the turn open)", '_verify_red = ""' in _feed)

print(f"\nplangate: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
