#!/usr/bin/env python3
"""
test_toollog.py — the terminal must say what actually happened.

WHY THIS EXISTS
===============
This suite is the second half of the DSML bug, and it is the half that made the
first half take so long to find.

The reported failure was that Basilisk printed protocol markup instead of
searching Steam. The parser fix is pinned in test_toolsyntax.py. But the
operator's log — the only instrument he had — was lying to him in three
separate ways at the same time, and every one of them pointed AWAY from the
real cause:

  1. `→ running <lambda>…` on every line.  `_tool_simple` took its label from
     `fn.__name__`, and 150 of the 151 dispatch entries wrap the call in a
     lambda to bind its arguments.  So the log could not tell you WHICH tool
     ran, which is the first question you ask.

  2. `✓ done` after a tool that failed.  The tick was printed unconditionally,
     so a `web_read` that came back with no url and an error read exactly like
     a successful fetch.  The run looked healthy while nothing was being
     learned — the same lie the parser bug told, told again one layer up.

  3. `── forcing the final answer (empty reply)` when the actual problem was an
     unreadable tool call.  The label had two branches for three cases, so at
     the exact moment the log had the answer, it named the wrong thing.

  4. The status line printed twice in a row, because `_set_working` logs on
     every call and is called more than once per tool with the same label.

None of these is a crash. All four are the reason a fifteen-minute bug took an
afternoon. A log that is wrong is worse than no log, because you believe it.

Run:  python3 tests/test_toollog.py
"""

from __future__ import annotations

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


# ── GTK stub, same shape as test_models.py ───────────────────────────
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

ck("basilisk.py imports clean under the GTK stub", True)


# ── 1. the label comes from the DISPATCHER, not from the closure ─────
print("\n== a tool logs its own name ==")


class _Rec:
    """MainWindow with just enough wired to run _tool_simple synchronously."""

    def __init__(self):
        self.lines = []
        self._dispatching_tool = ""

    terminal_log = lambda self, msg, kind="info": self.lines.append(          # noqa: E731
        (kind, msg))
    _tool_simple = Bk.MainWindow._tool_simple

    def _tool_thread(self, body, label):
        # Run the body inline instead of on a daemon thread, and record the
        # label the real _tool_thread would have used for its error message.
        self.thread_label = label
        body(lambda text: setattr(self, "fed", text))


# GLib.idle_add under the stub returns an _Obj and never runs the callback, so
# drive the log calls directly.
_real_idle = Bk.GLib.idle_add
Bk.GLib.idle_add = lambda fn, *a: (fn() if callable(fn) else None)

_r = _Rec()
_r._dispatching_tool = "web_read"
_r._tool_simple(lambda: {"ok": True, "text": "hello"})
_msgs = [m for _k, m in _r.lines]
ck("the running line names the real tool, not <lambda>",
   any("running web_read" in m for m in _msgs), str(_msgs))
ck("'<lambda>' appears nowhere in the log",
   not any("lambda" in m for m in _msgs), str(_msgs))
ck("the thread label is the tool name too (it names the error message)",
   _r.thread_label == "web_read", _r.thread_label)

# A bare function still labels itself, so nothing regressed for the one
# dispatch entry that passes one.
def tool_system_info():
    return {"ok": True}


_r2 = _Rec()
_r2._tool_simple(tool_system_info)
ck("a bare function still uses its own __name__",
   any("running tool_system_info" in m for _k, m in _r2.lines),
   str(_r2.lines))

# An explicit name wins over both.
_r3 = _Rec()
_r3._dispatching_tool = "wrong"
_r3._tool_simple(lambda: {"ok": True}, name="explicit_name")
ck("an explicit name overrides the dispatcher",
   any("running explicit_name" in m for _k, m in _r3.lines), str(_r3.lines))

# Nothing set anywhere → honest fallback, never a crash.
_r4 = _Rec()
_r4._tool_simple(lambda: {"ok": True})
ck("with no name available it falls back to 'tool', not '<lambda>'",
   any("running tool…" in m for _k, m in _r4.lines), str(_r4.lines))


# ── 2. a failed tool is not logged as a success ──────────────────────
print("\n== ✓ means it worked ==")

_r5 = _Rec()
_r5._dispatching_tool = "web_read"
_r5._tool_simple(lambda: {"ok": False, "error": "host is not reachable"})
_kinds = dict((m, k) for k, m in _r5.lines)
ck("ok:false does NOT print a tick",
   not any(m.startswith("✓") for _k, m in _r5.lines), str(_r5.lines))
ck("the failure names the tool and the reason",
   any("web_read" in m and "not reachable" in m for _k, m in _r5.lines),
   str(_r5.lines))
ck("the failure line is logged at error level",
   any(k == "error" for k, m in _r5.lines if m.startswith("✗")), str(_r5.lines))

_r6 = _Rec()
_r6._dispatching_tool = "web_read"
_r6._tool_simple(lambda: {"error": "blocked"})
ck("a bare error key is enough to lose the tick",
   not any(m.startswith("✓") for _k, m in _r6.lines), str(_r6.lines))

_r7 = _Rec()
_r7._dispatching_tool = "system_info"
_r7._tool_simple(lambda: {"ok": True, "cpu": "x"})
ck("a genuine success still prints ✓ done",
   any(m == "✓ done" for _k, m in _r7.lines), str(_r7.lines))

# Non-dict results (a list, a string) must not crash the success check.
for _res in ([1, 2, 3], "plain text", None, 42):
    _r8 = _Rec()
    _r8._dispatching_tool = "x"
    try:
        _r8._tool_simple(lambda r=_res: r)
        _ok = True
    except Exception as _e:                                     # pragma: no cover
        _ok = False
        print("      ", type(_e).__name__, _e)
    ck(f"non-dict result {type(_res).__name__} does not crash the logger", _ok)

# The result still reaches the model unchanged — the log fix must not touch
# what gets fed back.
_r9 = _Rec()
_r9._dispatching_tool = "web_read"
_r9._tool_simple(lambda: {"ok": False, "error": "nope"})
ck("the failing result is still fed to the model",
   "nope" in getattr(_r9, "fed", ""), getattr(_r9, "fed", ""))

Bk.GLib.idle_add = _real_idle


# ── 3. the dispatcher publishes the name, and always clears it ───────
print("\n== the dispatcher sets and clears the name ==")
_src = open(os.path.join(_ROOT, "basilisk.py"), encoding="utf-8").read()

ck("_dispatching_tool is initialised in __init__",
   re.search(r"self\._dispatching_tool:\s*str\s*=", _src) is not None)
ck("it is set immediately before the dispatch call",
   re.search(r"self\._dispatching_tool = call\.name\s*\n\s*try:\s*\n\s*"
             r"fn\(call\.args\)", _src) is not None,
   "a set without the try means a raising tool leaves a stale name behind")
ck("it is cleared in a finally, not after the call",
   re.search(r"finally:\s*\n\s*self\._dispatching_tool = \"\"", _src)
   is not None,
   "a stale name mislabels the NEXT tool, which is worse than no name")


# ── 4. the re-send case is not announced as an empty reply ───────────
print("\n== the log names the right problem ==")
ck("an unreadable tool call is announced as a re-send",
   "asking the model to re-send its tool call" in _src)
ck("the three cases have three labels",
   _src.count("unreadable tool call — asking for a re-send") == 1
   and "dropped tool call" in _src and "empty reply" in _src)
ck("the re-send instruction names the DSML dialect the model actually emits",
   "DSML tags" in _src and "<parameter name=" in _src,
   "telling a model 'that was wrong' without naming the format it used "
   "leaves it guessing")
ck("a spent re-send budget tells the operator instead of going quiet",
   "couldn't be read after 2" in _src)


# ── 5. the status line does not stutter ──────────────────────────────
print("\n== the status line logs on change only ==")


class _Pill:
    _set_working = Bk.MainWindow._set_working

    def __init__(self):
        self.lines = []

    terminal_log = lambda self, msg, kind="info": self.lines.append(msg)      # noqa: E731


Bk._CURRENT_ACTION = ""
_pl = _Pill()
_pl._set_working(True, "checking a trusted source…")
_pl._set_working(True, "checking a trusted source…")
_pl._set_working(True, "checking a trusted source…")
ck("the same label three times logs once", len(_pl.lines) == 1,
   str(_pl.lines))
_pl._set_working(True, "running nmap…")
ck("a changed label does log", len(_pl.lines) == 2, str(_pl.lines))
_pl._set_working(False)
_pl._set_working(True, "running nmap…")
ck("the same label AFTER idle logs again (a new run is news)",
   len(_pl.lines) == 3, str(_pl.lines))
ck("going idle logs nothing",
   not any("idle" in m for m in _pl.lines), str(_pl.lines))


print(f"\ntoollog: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
