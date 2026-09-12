#!/usr/bin/env python3
"""
test_repeatwindow.py — the repeat guard was blocking the loop the product is
built around.

THE BUG
=======
`workspace_verify {}` takes no arguments, so _action_label returns the constant
string "workspace_verify". The repeat guard refuses a THIRD identical action.
The action log is only reset when a MISSION latches, which never happens in
leashed work mode.

Therefore: in a repo job, the third `workspace_verify` was refused, and every
one after it, for the life of the chat.

Meanwhile the persona says of that exact tool, in the model's own instructions:

    <tool name="workspace_verify">{}</tool>  // ... Call after every edit.
    //   6. workspace_verify. Every time.

The instructions mandated a behaviour the guard forbade. Same for
`run: pytest -q`, and for `oracle_status {}` ("Consult it every planning turn"),
and for every other no-argument status read.

It is also what made the new verification gate unreliable: the gate synthesises
`workspace_verify`, the guard could refuse it, and the gate's one-shot was spent
on a refusal.

THE RULE
========
The guard's docstring was right about a SCANNER and wrong about a VERIFIER.
nmap against the same host three times tells you nothing new; workspace_verify
after a third edit tells you something completely new, because the thing it
measures changed underneath it. The guard compared labels, so it could not tell
them apart.

So it counts a WINDOW: runs of this action since the last DIFFERENT
state-changing action. An action never resets its OWN window — which is what
keeps `pytest, pytest, pytest` blocked while `edit, pytest, edit, pytest` runs
forever.

Run:  python3 tests/test_repeatwindow.py
"""

from __future__ import annotations

import io
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "basilisk_ext"))

from basilisk_ext import recall                                  # noqa: E402

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
PERSONA = io.open(os.path.join(_ROOT, "basilisk_persona.py"),
                  encoding="utf-8").read()
LIMIT = 2


def drive(seq):
    """Run a sequence of (label, changes_state) and report where it blocked."""
    log = recall.ActionLog()
    out = []
    for label, changes in seq:
        out.append((label, log.should_block(label, LIMIT)))
        log.record(label, '{"ok": true}', changes_state=changes)
    return out


def blocks_of(seq, label):
    return [b for l, b in drive(seq) if l == label]


# ── 1. THE REPORTED FAILURE, AND THAT IT IS REAL ─────────────────────
print("\n== the persona mandates what the guard forbade ==")
ck("the persona tells it to verify after every edit",
   "Call after every edit" in PERSONA)
ck("...and again, in the numbered loop",
   "workspace_verify. Every time." in PERSONA)
ck("...and to poll oracle_status every planning turn",
   "Consult it every planning turn" in PERSONA)
ck("a no-argument call really does produce a constant label",
   re.search(r'def _action_label\(self, call\)', SRC) is not None
   and "return n\n" in SRC.split("def _action_label")[1][:900],
   "if a bare tool name were not the label, none of this would bite")


# ── 2. THE FIX ───────────────────────────────────────────────────────
print("\n== the edit/verify loop is never blocked ==")
_loop = []
for n in range(1, 9):
    _loop.append((f"workspace_write: src/f{n}.py", True))
    _loop.append(("workspace_verify", False))
_vb = blocks_of(_loop, "workspace_verify")
ck(f"8 edit+verify rounds, 0 blocked (got {sum(_vb)})", not any(_vb))

_tl = []
for n in range(1, 7):
    _tl.append((f"workspace_replace: mod{n}.py", True))
    _tl.append(("run: pytest -q", True))
ck("a test command re-run after each edit is never blocked",
   not any(blocks_of(_tl, "run: pytest -q")))

ck("oracle_status polled between arms is never blocked",
   not any(blocks_of([("oracle_arm: sqli", True), ("oracle_status", False)] * 5,
                     "oracle_status")))


# ── 3. THE COUNTER-PROPERTY — the guard must still guard ─────────────
# This half matters more. A guard that stops firing is not a fix; the reason
# it exists is a model that repeats an action without reading the result.
print("\n== nothing changed, so it is still a repeat ==")
ck("verify x4 with no edits blocks at the third",
   blocks_of([("workspace_verify", False)] * 4, "workspace_verify")
   == [False, False, True, True])
ck("the same scan x4 blocks at the third",
   blocks_of([("run: nmap -sV 10.0.0.1", True)] * 4, "run: nmap -sV 10.0.0.1")
   == [False, False, True, True])
ck("pytest x4 with no edits blocks at the third",
   blocks_of([("run: pytest -q", True)] * 4, "run: pytest -q")
   == [False, False, True, True],
   "same code, same command - re-running it cannot say anything new")
ck("system_info x4 blocks at the third",
   blocks_of([("system_info", False)] * 4, "system_info")
   == [False, False, True, True])

# An action must never reset its OWN window. That asymmetry is the whole
# reason the two cases above can both be right at once.
_log = recall.ActionLog()
for _ in range(3):
    _log.record("run: pytest -q", "ok", changes_state=True)
ck("a state-changing action does not excuse its own repeat",
   _log.should_block("run: pytest -q", LIMIT))


# ── 4. THE CLASSIFICATION ────────────────────────────────────────────
print("\n== which actions change the answer ==")
_A = "_STATE_CHANGING_TOOLS = frozenset({"
ck("the table lives in basilisk.py", SRC.count(_A) == 1)
_ns = {}
exec(SRC[SRC.index(_A):SRC.index("def unverified_work_gap(")], _ns)   # noqa: S102
changes = _ns["_action_changes_state"]
for lbl in ("workspace_write: a.py", "workspace_replace: b.py", "run: ls",
            "write_file: /tmp/x", "delete_path: /tmp/y", "oracle_arm: xss",
            "submit_flag: abc", "scope_set: acme.com"):
    ck(f"changing: {lbl}", changes(lbl))
for lbl in ("workspace_verify", "workspace_status", "workspace_read: a.py",
            "system_info", "oracle_status", "read_file: /etc/hostname",
            "list_dir: /tmp", "web_read: https://x", "juiceshop_score"):
    ck(f"not changing: {lbl}", not changes(lbl))
ck("an unknown tool is treated as NOT changing",
   not changes("some_future_tool: x") and not changes(""),
   "the conservative direction - it leaves the guard as strict as it was")
for junk in (None, 0, [], object()):
    ck(f"total on {type(junk).__name__}", changes(junk) is False)

ck("the host passes it at the one record site",
   "changes_state=_action_changes_state(self._pending_action)" in SRC)
ck("...and for every member of a batch",
   "changes_state=_action_changes_state(_m)" in SRC,
   "the batch path has been the forgotten half three times in this method")


# ── 5. LIFETIME TOTALS STAY TRUTHFUL ─────────────────────────────────
# The refusal message quotes times_run back at the model. "You have already
# done this twice" has to be literally true, so the window must not rewrite
# the totals.
print("\n== the numbers the refusal quotes are still lifetime ==")
_log = recall.ActionLog()
for n in range(4):
    _log.record("workspace_verify", "ok")
    _log.record(f"workspace_write: f{n}.py", "ok", changes_state=True)
ck("times_run reports the lifetime total, not the window",
   _log.times_run("workspace_verify") == 4,
   str(_log.times_run("workspace_verify")))
ck("times_delivered likewise",
   _log.times_delivered("workspace_verify") == 4)
ck("...while the guard, correctly, is not blocking",
   not _log.should_block("workspace_verify", LIMIT))


# ── 6. THE DEFAULT IS THE OLD BEHAVIOUR ──────────────────────────────
# A caller that does not classify its tools must get exactly what it got
# before, or this change reaches further than it was meant to.
print("\n== an unclassified caller sees no change ==")
ck("record() defaults changes_state to False",
   "changes_state: bool = False" in io.open(
       os.path.join(_ROOT, "basilisk_ext", "recall.py"),
       encoding="utf-8").read())
ck("and then the window equals the lifetime",
   blocks_of([("anything", False)] * 4, "anything")
   == [False, False, True, True])
ck("reset() clears the window too",
   (lambda lg: (lg.record("x", "ok"), lg.record("x", "ok"),
                lg.reset(), not lg.should_block("x", LIMIT))[-1])(
       recall.ActionLog()))


print(f"\nrepeat window: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
