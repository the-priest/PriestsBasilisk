#!/usr/bin/env python3
"""
test_gates.py — the safety floor must be fitted to EVERY door, not just the
one it was written for.

THE FINDING
===========
README and the source both state that the destructive floor and the scope gate
are enforced "at the execution PRIMITIVE, with no override, not just the GUI".
That was true of ONE primitive, `tool_run_command`, where the checks were
inlined at the top of the function.

`tool_launch_app` is a SECOND execution primitive. It takes a model-supplied
program name and a model-supplied argument string, builds an argv, and Popens
it detached — as root, when Basilisk is running as root. It called neither
gate. So:

    run("rm -rf /")                 -> REFUSED by the floor
    launch_app("rm", "-rf /")       -> spawned

and `launch_app("nmap", "<out-of-scope-host>")` walked straight past the
authorisation boundary that exists to stop exactly that under UNLEASH.

Both gates were correct. Only one of the two doors had them fitted — which is
what an INLINED guard can only ever achieve. The rule now lives in one function
(`gate_command`) and every primitive calls it.

This suite pins two things:
  * behaviour — both primitives refuse the destroyer corpus and allow ordinary
    work; and
  * STRUCTURE — a source-level check that every model-facing spawner calls the
    gate, so a tool added later cannot quietly reopen the second door.

Run:  python3 tests/test_gates.py
"""

from __future__ import annotations

import ast
import io
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import basilisk_core as C                                       # noqa: E402

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


# Things that irreversibly destroy the machine. Every execution primitive must
# refuse all of them, however the model spells the call.
DESTROYERS = [
    ("rm", "-rf /"),
    ("rm", "-rf /*"),
    ("mkfs.ext4", "/dev/sda"),
    ("dd", "if=/dev/zero of=/dev/sda"),
    ("shred", "/dev/sda"),
    ("wipefs", "-a /dev/sda"),
    ("bash", "-c 'rm -rf /'"),
    ("sh", "-c 'mkfs.ext4 /dev/sda'"),
    ("chmod", "-R 000 /"),
    ("mv", "/etc /tmp/etc"),
]

# Ordinary desktop work. A floor that blocks these is a floor the operator
# turns off, which protects nothing — this half is asserted as hard as the
# other one.
BENIGN = [
    ("firefox", "https://example.com"),
    ("code", "/home/user/project"),
    ("gnome-terminal", ""),
    ("nautilus", "~/Downloads"),
    ("xdg-open", "/tmp/report.pdf"),
    ("wireshark", ""),
    ("burpsuite", ""),
    ("rm", "-rf /tmp/scratch"),
]


# ── 1. the gate exists as ONE callable thing ─────────────────────────
print("\n== there is a single shared gate ==")
ck("basilisk_core exposes gate_command", callable(getattr(C, "gate_command", None)))
ck("it returns None for something ordinary",
   C.gate_command("echo hello") is None)
_r = C.gate_command("rm -rf /")
ck("it returns a refusal dict for a destroyer", isinstance(_r, dict))
ck("…marked refused", _r.get("refused") is True)
ck("…and marked catastrophic", _r.get("catastrophic") is True)
ck("…carrying the command it judged", _r.get("command") == "rm -rf /")
ck("a self-tamper is refused too",
   (C.gate_command("echo x > basilisk_safety.py") or {}).get("refused") is True)
ck("gate_command never raises on junk",
   all(C.gate_command(x) is None or isinstance(C.gate_command(x), dict)
       for x in ("", "   ", "'", "$(", "\x00", "a" * 5000)))


# ── 2. BOTH primitives refuse the destroyer corpus ───────────────────
print("\n== every execution primitive refuses the destroyers ==")
for _app, _args in DESTROYERS:
    _line = f"{_app} {_args}".strip()
    ck(f"run refuses: {_line}",
       C.tool_run_command(_line).get("refused") is True)
    _res = C.tool_launch_app(_app, _args)
    ck(f"launch_app refuses: {_app} {_args}",
       _res.get("refused") is True, str(_res)[:110])


# ── 3. …and neither blocks ordinary work ─────────────────────────────
print("\n== ordinary work still runs ==")
for _app, _args in BENIGN:
    _res = C.tool_launch_app(_app, _args)
    ck(f"launch_app allows: {_app} {_args}".rstrip(),
       _res.get("refused") is not True, str(_res)[:110])

ck("run still allows a normal command",
   C.tool_run_command("echo hello", timeout=10).get("ok") is True)
ck("run still refuses a destroyer",
   C.tool_run_command("rm -rf /").get("refused") is True)


# ── 4. STRUCTURE: no ungated model-facing spawner may exist ──────────
# The behavioural checks above can only cover the primitives someone remembered
# to list. This one walks the AST and asserts the property directly, so a NEW
# tool that spawns a process is caught the day it is written rather than the
# day it is abused.
print("\n== no model-facing spawner bypasses the gate ==")

_SPAWNERS = {"subprocess.Popen", "subprocess.run", "subprocess.call",
             "subprocess.check_output", "subprocess.check_call",
             "os.system", "os.popen", "pty.spawn"}

# Functions that spawn but are NOT reachable with model-chosen programs.
# Each entry is a claim someone can check, not a blanket exemption.
_EXEMPT = {
    "_ro":                  "fixed argv of read-only system probes",
    "_run_sudo_inline":     "internal; called by tool_run_command AFTER the gate",
    "_run_sudo_askpass":    "internal; called by tool_run_command AFTER the gate",
    "sudo_cached":          "fixed argv ['sudo','-n','true']",
    "tool_open_url":        "xdg-open with a URL; opens, does not execute",
    "tool_capture_photo":   "fixed list of capture binaries; model supplies only an out path",
    "run_supervised":       "the executor tool_run_command delegates to, after the gate",
    "run_python":           "sandboxed skill runner; isolation is its own boundary",
    "start":                "MCP server / recorder launch from operator config",
}

_src = io.open(os.path.join(_ROOT, "basilisk_core.py"), encoding="utf-8").read()
_tree = ast.parse(_src)
_fns = [(n.lineno, getattr(n, "end_lineno", n.lineno), n.name, n)
        for n in ast.walk(_tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _enclosing(lineno):
    """Every function containing this line, innermost first.

    The whole CHAIN matters, not just the innermost one: tool_launch_app does
    its spawning through a nested `def _spawn(argv)` helper, so an
    innermost-only check reports the helper as ungated while the gate sits
    correctly in its parent. A spawn is gated if ANY enclosing function gates.
    """
    hits = [(a, nm, node) for a, b, nm, node in _fns if a <= lineno <= b]
    return sorted(hits, key=lambda h: -h[0])


def _calls_gate(node) -> bool:
    return any(isinstance(n, ast.Call) and ast.unparse(n.func) == "gate_command"
               for n in ast.walk(node))


_ungated = []
_seen = set()
for _n in ast.walk(_tree):
    if isinstance(_n, ast.Call) and ast.unparse(_n.func) in _SPAWNERS:
        _chain = _enclosing(_n.lineno)
        if not _chain:
            _ungated.append(f"<module> at basilisk_core.py:{_n.lineno}")
            continue
        _names = [nm for _a, nm, _node in _chain]
        _key = _names[0]
        if _key in _seen:
            continue
        _seen.add(_key)
        if any(nm in _EXEMPT for nm in _names):
            continue
        if not any(_calls_gate(node) for _a, _nm, node in _chain):
            _ungated.append(
                f"{'/'.join(_names)} at basilisk_core.py:{_n.lineno}")

ck("every non-exempt spawner in basilisk_core calls gate_command",
   not _ungated, f"UNGATED: {_ungated}")
ck("the two known primitives are NOT on the exemption list",
   "tool_run_command" not in _EXEMPT and "tool_launch_app" not in _EXEMPT)
ck("tool_run_command calls the gate",
   _calls_gate(next(n for _a, _b, nm, n in _fns if nm == "tool_run_command")))
ck("tool_launch_app calls the gate",
   _calls_gate(next(n for _a, _b, nm, n in _fns if nm == "tool_launch_app")))
ck("the gate is not duplicated back inline into a primitive",
   _src.count("REFUSED - catastrophic command") == 1,
   "the floor text appears more than once — it has been copied, and copies "
   "drift")

print(f"\ngates: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
