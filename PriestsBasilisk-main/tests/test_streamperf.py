#!/usr/bin/env python3
"""
test_streamperf.py — the live reply must not get quadratically more expensive
the longer it gets.

WHY THIS EXISTS
===============
strip_tool_calls runs on EVERY streamed frame, over the WHOLE buffer so far, on
the GTK main thread.  That shape has produced a hard UI freeze twice now:
_ALT_PARTIAL_RE at 25 seconds (fixed in v9.6.0), and the four causes below,
which v9.6.0 shipped with.

  1. TOOL_TAG_RE's bare-word attribute alternative did not exclude '<', so one
     opener's attribute blob could swallow every FOLLOWING opener and then
     backtrack through the lot looking for a '>'.  3.5 SECONDS in a single pass
     on 4000 repeated `<tool ` openers.

  2. TOOL_PARTIAL_RE's `[^>]*` scanned to end-of-string from every `<tool`
     position before failing.  479ms on the same input.

  3. The final display scrub had the same unbounded run.  60ms.

  4. Worse than all three: the render recomputed the strip on the entire buffer
     ONCE PER TOKEN.  That is O(n^2) in reply length no matter how fast the
     regexes are — 38.7s of accumulated main-thread CPU for a single large
     write_file, which is the ORDINARY path for the workspace repair tools.

Causes 1-3 are worst-case latency: one blocking pass the operator experiences
as a freeze.  Cause 4 is throughput: no single pass is slow, but there are tens
of thousands of them.  They need different fixes and are tested separately.

The input is not exotic.  A model stuck repeating itself is a known Basilisk
failure mode — it is what v9.1.0's repeat guard exists for — and what a
repetitive model repeats, right after a tool call fails to parse, is a
tool-call opener.

Run:  python3 tests/test_streamperf.py
"""

from __future__ import annotations

import json
import os
import random
import re
import sys
import time
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import basilisk_core as C  # noqa: E402

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


_CODE = "\n".join(f"    if x[{i}] < 10 and y > 3:  # note" for i in range(9000))


def _writefile_reply(n):
    return ('<tool name="write_file">'
            + json.dumps({"path": "a.py", "content": _CODE[:n]}))


# ═══════════════════════════════════════════════════════════════════════
# 1. Worst-case SINGLE pass.  This is the number the operator feels.
# ═══════════════════════════════════════════════════════════════════════
print("== worst-case single strip_tool_calls pass ==")

SHAPES = [
    ("repeated bare opener x4000", "sorry, retrying\n" + "<tool " * 4000, 400),
    ("repeated full opener x3000", '<tool name="run_command">' * 3000, 400),
    ("repeated opener + one closer", "<tool " * 3000 + "</tool>", 400),
    ("large write_file 128k", _writefile_reply(128000), 400),
    ("prose 128k", "The quick brown fox. " * 6400, 200),
    ("unclosed think + openers", "<think>" + "<tool " * 2000, 400),
    ("mixed dialect storm",
     ('<tool_call name="x">' * 800 + "<function=y>" * 800 + "<tool " * 800), 400),
]
for name, text, ceiling_ms in SHAPES:
    t = time.perf_counter()
    C.strip_tool_calls(text)
    ms = (time.perf_counter() - t) * 1000
    ck(f"{name}: {ms:.0f}ms (ceiling {ceiling_ms}ms)", ms < ceiling_ms,
       "a single pass this slow is a visible UI freeze")


# ═══════════════════════════════════════════════════════════════════════
# 2. Scaling.  A ceiling passes by luck on a fast box; the EXPONENT does not.
#    Doubling the input must not quadruple the time.
# ═══════════════════════════════════════════════════════════════════════
print("\n== scaling must be sub-quadratic ==")


def _time(text):
    t = time.perf_counter()
    C.strip_tool_calls(text)
    return time.perf_counter() - t


for label, build in [
    ("repeated openers", lambda n: "<tool " * n),
    ("write_file body", lambda n: _writefile_reply(n * 30)),
]:
    small = max(_time(build(1000)), 1e-6)
    large = _time(build(4000))
    ratio = large / small
    # 4x the input.  Linear -> ~4x.  Quadratic -> ~16x.  8x is a generous
    # midpoint that still fails the shipped v9.6.0 behaviour.
    ck(f"{label}: 4x input costs {ratio:.1f}x time", ratio < 8.0,
       "quadratic scaling — the ceiling above will fail on a bigger reply")


# ═══════════════════════════════════════════════════════════════════════
# 3. The fast path must be EXACT, not approximately right.
#    It skips every regex when the text has no '<' and no fullwidth pipe.
# ═══════════════════════════════════════════════════════════════════════
print("\n== no-markup fast path is byte-identical ==")

_DSP = C._DS_PIPE



random.seed(11)
_words = ["hello", "world", "the", "quick", "fox", "\n", "  ", "tab\t",
          "a" * 50, "json {\"a\": 1}", "100% done", "x>y", "a & b"]
_bad = 0
for _ in range(20000):
    s = " ".join(random.choice(_words) for _ in range(random.randint(0, 25)))
    if "<" in s or _DSP in s:
        continue
    # With no '<' and no pipe the ONLY defined effect is .strip()
    if C.strip_tool_calls(s) != s.strip():
        _bad += 1
ck("20000 no-markup inputs strip to exactly text.strip()", _bad == 0,
   f"{_bad} mismatches")

# And the guard must not swallow input that DOES carry a fullwidth pipe but
# no '<' — that is a partially-arrived DeepSeek token, not prose.
ck("fullwidth pipe alone does not take the fast path",
   _DSP in "x" + _DSP + "y" and C.strip_tool_calls("x" + _DSP + "y") is not None)


# ═══════════════════════════════════════════════════════════════════════
# 4. Bounded regexes must not change what matches.
# ═══════════════════════════════════════════════════════════════════════
print("\n== bounded partial-opener regex agrees with the unbounded form ==")

_OLD_PARTIAL = re.compile(r'<tool(?:\s[^>]*)?>\s*\{?[^<]*$',
                          re.DOTALL | re.IGNORECASE)
_FRAG = ['<tool name="run">', '</tool>', '{"a":1}', 'text ', '\n', '<tool ',
         '<tool>', '<tool a="b" c>', '>', '<', '   ', 'x' * 40]
_dis = 0
for _ in range(20000):
    s = "".join(random.choice(_FRAG) for _ in range(random.randint(0, 12)))
    if bool(_OLD_PARTIAL.search(s)) != bool(C.TOOL_PARTIAL_RE.search(s)):
        _dis += 1
ck("20000 corpus inputs, 0 disagreements", _dis == 0, f"{_dis} disagreements")
ck("divergence only past the 4000-char attribute bound",
   bool(_OLD_PARTIAL.search("<tool " + "a" * 5000 + ">x"))
   and not bool(C.TOOL_PARTIAL_RE.search("<tool " + "a" * 5000 + ">x")))

# The '<'-exclusion in the attribute blob must not change parsing of real calls.
print("\n== tool-call parsing is unchanged ==")
CALLS = [
    '<tool name="run_command">{"command": "ls -la"}</tool>',
    '<tool name="run_command">{"command": "echo a < b"}</tool>',
    "<tool>{\"name\": \"read_file\", \"path\": \"a.py\"}</tool>",
    '<tool name="x" json=\'{"a": 1}\'></tool>',
    '<tool name="x" json=\'{"a": 1}\'/>',
    '<tool tool name="run_command">{"command": "id"}</tool>',
    '<tool run>{"command": "id"}</tool>',
    '<tool name="write_file">{"path": "a.html", "content": "<div>hi</div>"}</tool>',
]
for raw in CALLS:
    calls = C.parse_tool_calls(raw)
    ck(f"parses: {raw[:52]}", len(calls) == 1 and bool(calls[0].name),
       f"got {calls}")
    ck(f"strips: {raw[:52]}", "<tool" not in C.strip_tool_calls(raw).lower())

# A quoted attribute may still contain '<' — only the BARE-word form excludes it.
_c = C.parse_tool_calls('<tool name="run_command" note="a<b">{"command": "id"}</tool>')
ck("'<' inside a quoted attribute still parses", len(_c) == 1 and _c[0].name == "run_command")


# ═══════════════════════════════════════════════════════════════════════
# 5. Render coalescing (the O(n^2) throughput fix), under a GTK stub.
# ═══════════════════════════════════════════════════════════════════════
print("\n== streaming render is coalesced ==")


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

import basilisk as Bk  # noqa: E402

ck("basilisk.py imports clean under the GTK stub", True)
ck("render interval is a sane 20fps-ish floor",
   0 < Bk._STREAM_RENDER_MIN_S <= 0.2 and
   Bk._STREAM_RENDER_MIN_MS == int(Bk._STREAM_RENDER_MIN_S * 1000))


class _Label:
    def __init__(self):
        self.text = ""
        self.sets = 0

    def set_text(self, s):
        self.text = s
        self.sets += 1


class _Clock:
    def __init__(self):
        self.t = 1000.0

    def monotonic(self):
        return self.t


def _widget():
    """A MessageWidget without running __init__ (which would build real GTK)."""
    w = object.__new__(Bk.MessageWidget)
    w._disposed = False
    w._content = ""
    w._streaming_label = _Label()
    w._last_stream_render = 0.0
    w._stream_render_pending = False
    return w


_clock = _Clock()
_real_time = Bk.time
_real_glib = Bk.GLib
_scheduled = []


class _FakeGLib:
    @staticmethod
    def timeout_add(ms, fn, *a):
        _scheduled.append((ms, fn))
        return 1

    def __getattr__(self, n):
        return getattr(_real_glib, n)


Bk.time = _clock
Bk.GLib = _FakeGLib()

try:
    # 2000 tokens arriving at 1ms of virtual time apart = 2 seconds of stream.
    w = _widget()
    _strip_calls = [0]
    _real_strip = Bk.strip_tool_calls

    def _counting(t):
        _strip_calls[0] += 1
        return _real_strip(t)

    Bk.strip_tool_calls = _counting
    for i in range(2000):
        _clock.t += 0.001
        w.append_streaming("tok ")
    ck(f"2000 tokens over 2s of stream caused {_strip_calls[0]} full strips, "
       f"not 2000", _strip_calls[0] <= 60,
       "per-token stripping is quadratic in reply length")
    ck("some rendering did happen", _strip_calls[0] >= 20)
    ck("the buffer itself is complete", w._content == "tok " * 2000)

    # Trailing edge: a burst that stops mid-interval must still schedule a
    # flush, or the tail of a reply is never painted.
    w2 = _widget()
    _scheduled.clear()
    _clock.t += 10.0
    w2.append_streaming("first")          # immediate (last_render == 0)
    _clock.t += 0.001
    w2.append_streaming(" second")        # inside the interval -> deferred
    ck("a deferred token schedules exactly one flush", len(_scheduled) == 1,
       f"{len(_scheduled)} scheduled")
    ck("a second deferred token does not schedule another",
       (w2.append_streaming(" third"), len(_scheduled))[1] == 1)
    _scheduled[0][1]()
    ck("the flush paints the whole buffer",
       w2._streaming_label.text == _real_strip(
           Bk.strip_think_blocks(w2._content)))
    ck("the flush clears the pending flag", w2._stream_render_pending is False)
    ck("the flush is one-shot", w2._flush_stream_render() is False)

    # A disposed bubble can still receive a late flush — see dispose_widget.
    w3 = _widget()
    w3.append_streaming("x")
    w3._disposed = True
    w3._streaming_label = None
    try:
        w3._flush_stream_render()
        w3.append_streaming("y")
        ck("a flush after disposal is a no-op, not an AttributeError", True)
    except Exception as e:
        ck("a flush after disposal is a no-op, not an AttributeError", False,
           repr(e))

    # A brand-new stream must paint its first token at once, or a reply that
    # opens slowly reads as a hang.
    w4 = _widget()
    w4._last_stream_render = _clock.monotonic()   # pretend a prior stream ran
    w4._blocks_container = None
    w4._streaming_label = _Label()
    w4._last_stream_render = 0.0
    w4._stream_render_pending = False
    n0 = w4._streaming_label.sets
    w4.append_streaming("hello")
    ck("first token of a stream paints immediately",
       w4._streaming_label.sets > n0)
finally:
    Bk.time = _real_time
    Bk.GLib = _real_glib
    Bk.strip_tool_calls = _real_strip

print(f"\nstream perf: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
