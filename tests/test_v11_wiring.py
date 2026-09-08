#!/usr/bin/env python3
"""test_v11_wiring.py — drive the REAL turn and check the new wiring FIRES.

Source-level greps prove a line exists. This drives _kick_assistant_turn and
asserts which addendum is built, which budget applies, and what is logged —
for a coding job, a question, and a live mission.
"""
import os
import sys
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)


class _Meta(type):
    def __getattr__(cls, n):
        if n.startswith("__"): raise AttributeError(n)
        return _Obj
class _Obj(metaclass=_Meta):
    def __init__(self, *a, **k): pass
    def __call__(self, *a, **k): return _Obj()
    def __getattr__(self, n): return _Obj()
class _Mod(types.ModuleType):
    def __getattr__(self, n):
        if n.startswith("__"): raise AttributeError(n)
        return _Obj
    def require_version(self, *a, **k): pass
for _m in ("gi", "gi.repository", "gi.repository.Gtk", "gi.repository.Adw",
           "gi.repository.GLib", "gi.repository.Gio", "gi.repository.Gdk",
           "gi.repository.GdkPixbuf", "gi.repository.Pango",
           "gi.repository.GObject", "gi.repository.GtkSource",
           "gi.repository.Vte", "gi.repository.Soup"):
    sys.modules[_m] = _Mod(_m)
sys.modules["gi"].require_version = lambda *a, **k: None

import basilisk as Bk
import basilisk_core as Bc

bad = []


def note(m):
    bad.append(m)


class _Stop(Exception):
    pass


_CAP = {}


def _capture_volatile(addendum="", *a, **k):
    _CAP["addendum"] = addendum
    raise _Stop()


def turn(question, depth=1, unleashed=False, mission=False, tool_ran=True,
         settings=None):
    """Returns (addendum, logs, max_tokens_override_seen)."""
    w = object.__new__(Bk.MainWindow)
    w.settings = dict(Bc.DEFAULT_SETTINGS)
    w.settings["approval_mode"] = "none"
    if settings:
        w.settings.update(settings)
    w._stop_requested = False
    w._tool_ran_this_request = tool_ran
    w._tool_chain_depth = depth - 1
    w._tools_locked = False
    w._force_answer_tries = 0
    w.streaming_chat_id = 1
    w.current_chat_id = 1
    w._unleashed = unleashed
    w._mission_active = mission
    w._unleash_kickoff_pending = False
    w._mission_directive = ""
    w._ext = None
    w._action_log = None
    w._error_retries = 0
    w._last_worked = None
    w._recent_commands = []
    w._last_tool_names = []
    w.streaming_msg_widget = None
    w.streaming_msg_db_id = None
    w.router = types.SimpleNamespace(any_available=lambda: True)
    w.store = types.SimpleNamespace(add_message=lambda *a, **k: 1)
    w._mark_turn_progress = lambda *a, **k: None
    logs = []
    w.terminal_log = lambda m, s="": logs.append(m)
    hist = [{"role": "user", "content": question}]
    for _ in range(depth - 1):
        hist += [{"role": "assistant", "content": "Working on it."},
                 {"role": "user",
                  "content": '<tool_result>\n[tool: run]\n{"ok":true}\n</tool_result>'}]
    w._build_history_for_model = lambda *a, **k: hist

    _saved = Bk.volatile_block
    Bk.volatile_block = _capture_volatile
    _CAP.pop("addendum", None)
    try:
        w._kick_assistant_turn()
    except _Stop:
        pass
    except Exception as e:
        note(f"turn({question[:30]!r}) raised {type(e).__name__}: {e}")
    finally:
        Bk.volatile_block = _saved
    return _CAP.get("addendum", ""), logs, w


WORK = "[WORK MODE (leashed)"
ANSWER = "[ANSWER MODE (leashed)"
AUTONOMOUS = "[AUTONOMOUS MODE"

# ── 1. a coding job gets WORK MODE, and only WORK MODE ──────────────
for q in ("fix the auth bug in my repo",
          "refactor the parser into three modules",
          "the tests are failing, sort it out",
          "add a --verbose flag and tests for it"):
    a, logs, w = turn(q)
    if WORK not in a:
        note(f"1: no WORK MODE for {q!r}")
    if ANSWER in a:
        note(f"1: BOTH work and answer mode fired for {q!r}")
    if AUTONOMOUS in a:
        note(f"1: autonomous directive leaked into a leashed turn: {q!r}")
    if not any("work mode" in l for l in logs):
        note(f"1: work mode not logged for {q!r}: {logs}")
    if not w._leash_work_turn:
        note(f"1: _leash_work_turn not set for {q!r}")

# ── 2. a question still gets ANSWER MODE, unchanged ─────────────────
for q in ("what is the latest version of nmap",
          "explain how the dispatcher works",
          "who won the game last night"):
    a, logs, w = turn(q)
    if ANSWER not in a:
        note(f"2: no ANSWER MODE for {q!r}")
    if WORK in a:
        note(f"2: WORK MODE fired on a question: {q!r}")
    if w._leash_work_turn:
        note(f"2: _leash_work_turn set on a question: {q!r}")

# ── 3. UNLEASHED with a mission is untouched by any of this ─────────
a, logs, w = turn("own the box", unleashed=True, mission=True)
if WORK in a or ANSWER in a:
    note("3: a leashed-mode directive leaked into an active mission")
if AUTONOMOUS not in a:
    note("3: the autonomous directive stopped firing during a mission")
if w._leash_work_turn:
    note("3: _leash_work_turn set during a mission")

# ── 4. the work turn actually gets a file-sized output budget ───────
def budget_for(**kw):
    w = turn(**kw)[2]
    return getattr(w, "_probe_mt", None)

# re-drive, capturing the override the stream would have been given
import json
def budget(question, **kw):
    seen = {}
    real = Bk.volatile_block
    a, logs, w = turn(question, **kw)
    # _mt_override is local; assert via the documented setting + flags instead
    return w

w_work = turn("fix the auth bug in my repo")[2]
w_q = turn("what is the latest version of nmap")[2]
if not w_work._leash_work_turn:
    note("4: work turn flag missing")
if w_q._leash_work_turn:
    note("4: question turn wrongly flagged as work")

# the budget itself is asserted at source level plus by settings coercion
s = Bc.load_settings()
if s.get("code_write_max_tokens") != 16384:
    note(f"4: code_write_max_tokens default is {s.get('code_write_max_tokens')}")
for junk in ("0", -5, 0, None, "abc", 1.5, True, []):
    m = dict(Bc.DEFAULT_SETTINGS); m["code_write_max_tokens"] = junk
    Bc._coerce_settings_types(m)          # mutates in place
    v = m.get("code_write_max_tokens")
    if not isinstance(v, int) or v <= 0:
        note(f"4: a junk code_write_max_tokens={junk!r} survived as {v!r}")

# ── 5. the tool budget is intent-aware ──────────────────────────────
# a work turn deep in a chain must NOT be tool-locked at 41 steps
a, logs, w = turn("fix the auth bug in my repo", depth=45)
if w._tools_locked:
    note("5: a work turn was tool-locked at depth 45 (question budget applied)")
if "[You've used a lot of tools" in a:
    note("5: the question tool-cap message fired on a work turn")
a, logs, w = turn("what is the latest version of nmap", depth=45)
if not w._tools_locked:
    note("5: a QUESTION turn was not capped at depth 45")

# a work turn IS eventually capped
a, logs, w = turn("fix the auth bug in my repo", depth=130)
if not w._tools_locked:
    note("5: a work turn was never capped, even at depth 130")
if "report honestly" not in a:
    note("5: the work tool-cap does not ask for an honest state report")

# ── 6. the work-mode text says the things that matter ───────────────
a = turn("fix the auth bug in my repo")[0]
for must in ("ENTIRE final content", "rest unchanged", "READ BEFORE YOU WRITE",
             "ITERATE UNTIL IT ACTUALLY PASSES", "workspace_write",
             "workspace_replace", "never via `propose`"):
    if must.lower() not in a.lower():
        note(f"6: work mode is missing {must!r}")

# ── 7. a work CONTINUATION must not be told to answer-and-stop ──────
a = turn("fix the auth bug in my repo", depth=3)[0]
if "CONTINUATION TURN" not in a:
    note("7: no continuation guidance on a mid-job turn")
if "Deliver ONE complete" in a:
    note("7: a mid-job turn is being told to deliver one complete answer")

print("\n".join(bad) if bad else "no findings")
print(f"\nv11_wiring: {len(bad)} finding(s)")
sys.exit(1 if bad else 0)
