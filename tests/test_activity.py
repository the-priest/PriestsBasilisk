#!/usr/bin/env python3
"""
test_activity.py — the live activity feed, and the honesty rules it exists for.

WHY THIS EXISTS
===============
This project has now had the same class of bug three times: the UI reported
something the run had not actually done.  `→ running <lambda>` for 150 of 151
tools.  `✓ done` printed unconditionally, over failures included.  A `⚙ used X`
row for a call the repeat guard had refused.  Every one of them was a display
that had drifted away from the thing it claimed to describe, and every one of
them survived because nothing tested the display.

The activity feed makes that failure mode WORSE if it is wrong, because it is
now the primary surface: it is where the operator looks to see what Basilisk is
doing, instead of the terminal panel he has to open on purpose.  So the rules it
promises are tested here as rules, not as pixels:

  1. a step is marked FAILED when its result says the tool did not run
     — a green tick over `NOT RUN — repeat guard` is the exact lie above;
  2. a replayed history row is NEUTRAL, never a tick, because the store records
     that a tool was CALLED and never records whether it worked;
  3. every _activity_* entry point is TOTAL — a window with no feed, a disposed
     feed or a torn-down turn must be a no-op and never an exception, because
     these are called from inside the tool chain and a raise there strands the
     turn (the same reason _feed_tool_result guards its whole body);
  4. the feed's clock is stopped on every teardown path, or a trimmed widget
     keeps a 200ms GLib timeout running for the life of the process.

Plus the two things the feed changed underneath it: bare tool-step bubbles are
no longer drawn (they are what made one answer look like four), and avatars are
decoded once instead of once per bubble.

Run:  python3 tests/test_activity.py
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


# ── GTK stub, same shape as test_toollog.py ──────────────────────────
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

_SRC = open(os.path.join(_ROOT, "basilisk.py"), encoding="utf-8").read()

ck("basilisk.py imports clean under the GTK stub", True)
ck("ActivityFeedWidget exists", hasattr(Bk, "ActivityFeedWidget"))


# ═══════════════════════════════════════════════════════════════════════
# 1. The clock the operator reads
# ═══════════════════════════════════════════════════════════════════════
print("\n== elapsed formatting ==")

E = Bk._fmt_elapsed
ck("sub-second is milliseconds", E(0.412) == "412ms", E(0.412))
ck("faster than the unit says so, rather than reading as never-ran",
   E(0) == "<1ms" and E(0.0004) == "<1ms", E(0.0004))
ck("a real millisecond is still a number", E(0.001) == "1ms", E(0.001))
ck("a second crosses to s", E(1.0) == "1.0s", E(1.0))
ck("seconds keep one decimal", E(12.34) == "12.3s", E(12.34))
ck("past a minute reads m/s, not 94.3s", E(94.3) == "1m34s", E(94.3))
ck("minutes zero-pad the seconds", E(125.0) == "2m05s", E(125.0))
ck("a negative clock does not produce a negative string",
   E(-5) == "<1ms", E(-5))
ck("garbage in does not raise", E("nope") == "" and E(None) == "")


# ═══════════════════════════════════════════════════════════════════════
# 2. The row must name the call, not dump it
# ═══════════════════════════════════════════════════════════════════════
print("\n== the detail is the argument that makes the call distinct ==")

D = Bk._feed_detail
ck("run shows the command",
   D("run", {"timeout": 30, "command": "nmap -sV 10.0.0.5"})
   == "nmap -sV 10.0.0.5")
ck("command wins over other strings even when it is not first",
   D("run", {"explanation": "scan the host", "command": "nmap -sV x"})
   == "nmap -sV x",
   "priority order must match _action_label, or the feed and the repeat "
   "guard name different things")
ck("web_read shows the url", D("web_read", {"url": "https://a/b"})
   == "https://a/b")
ck("read_file shows the path", D("read_file", {"path": "/etc/os-release"})
   == "/etc/os-release")
ck("whitespace is collapsed to one line",
   D("run", {"command": "nmap  -sV\n  10.0.0.5"}) == "nmap -sV 10.0.0.5")
ck("a long argument is truncated, not wrapped",
   len(D("web_read", {"url": "https://x/" + "a" * 400})) == 120)
ck("an unknown-shaped call still finds a string",
   D("weird", {"blob": "something"}) == "something")
ck("no strings at all is empty, not 'None'",
   D("x", {"n": 5, "ok": True}) == "")
ck("non-dict args do not raise", D("x", None) == "" and D("x", [1]) == "")


# ═══════════════════════════════════════════════════════════════════════
# 3. The preview is a receipt, and an error outranks a success field
# ═══════════════════════════════════════════════════════════════════════
print("\n== result preview ==")

P = Bk._feed_preview
ck("empty in, empty out", P("") == "" and P(None) == "")
ck("an error field is surfaced",
   P(json.dumps({"ok": True, "text": "hi", "error": "connection refused"}))
   == "connection refused",
   "an error must outrank a success field regardless of key order, or a "
   "failed tool previews as if it worked")
ck("ok:false with no message still reads as failed",
   P(json.dumps({"ok": False})) == "failed")
ck("a text body is previewed",
   P(json.dumps({"ok": True, "status": 200, "text": "Hello world"}))
   == "Hello world")
ck("a long body is truncated with an ellipsis",
   P(json.dumps({"text": "x" * 900})).endswith("..."))
ck("a shapeless dict at least names its keys",
   P(json.dumps({"cpu": 1, "mem": 2})).startswith("returned: "))
ck("plain text falls back to the first real line",
   P("\n\n  first line here\nsecond") == "first line here")
ck("malformed json does not raise",
   isinstance(P('{"ok": tru'), str))


# ═══════════════════════════════════════════════════════════════════════
# 4. A bare tool step is not an answer
# ═══════════════════════════════════════════════════════════════════════
print("\n== tool-only replies are steps, not replies ==")

T = Bk._reply_is_tool_only
ck("a bare tool call is a step",
   T('<tool name="web_read">{"url":"https://a"}</tool>'))
ck("prose plus a tool call is a reply",
   not T('Reading the changelog now.\n'
         '<tool name="web_read">{"url":"https://a"}</tool>'))
ck("prose alone is a reply", not T("The answer is 42."))
ck("empty is not a step", not T("") and not T("   "))
ck("a think block around a tool call is still a step",
   T('<think>which page</think><tool name="web_read">{"url":"https://a"}</tool>'))
ck("garbage does not raise", isinstance(T("<tool " * 50), bool))


# ═══════════════════════════════════════════════════════════════════════
# 5. THE HONESTY RULE: a refusal is not a success
# ═══════════════════════════════════════════════════════════════════════
print("\n== a step is only green if it actually worked ==")


class _Win:
    """MainWindow with just the feed entry points bound."""
    _activity = Bk.MainWindow._activity
    _activity_phase = Bk.MainWindow._activity_phase
    _activity_begin = Bk.MainWindow._activity_begin
    _activity_end = Bk.MainWindow._activity_end
    _activity_note = Bk.MainWindow._activity_note
    _activity_finish = Bk.MainWindow._activity_finish
    _activity_close_result = Bk.MainWindow._activity_close_result

    def __init__(self, feed=None):
        self._activity_feed = feed
        self._activity_sid = 0


class _FakeFeed:
    """Records the verdicts instead of drawing them."""
    _disposed = False

    def __init__(self):
        self.ended = []
        self.notes = []
        self.phases = []
        self.finished = None
        self._n = 0

    def begin_step(self, name, detail, kind):
        self._n += 1
        return self._n

    def end_step(self, sid, ok=True, detail="", preview=""):
        self.ended.append((sid, ok, preview))

    def note(self, text, kind="note"):
        self.notes.append((kind, text))

    def set_phase(self, text):
        self.phases.append(text)

    def finish(self, summary="", ok=True):
        self.finished = (summary, ok)


def _verdict(result_text):
    fd = _FakeFeed()
    w = _Win(fd)
    w._activity_sid = w._activity_begin("run", {"command": "id"})
    w._activity_close_result(result_text)
    return fd.ended[0][1] if fd.ended else None


ck("a real result is a success",
   _verdict(json.dumps({"ok": True, "text": "uid=0(root)"})) is True)
ck("NOT RUN is a FAILURE, not a tick",
   _verdict("NOT RUN — repeat guard: that already ran.") is False,
   "this is the `done` printed unconditionally, in a new costume")
ck("an unknown tool is a failure",
   _verdict("Unknown tool 'nope'.") is False)
ck("a bare error line is a failure",
   _verdict("error: TimeoutError: took too long") is False)
ck("ok:false is a failure even with a 200 beside it",
   _verdict(json.dumps({"ok": False, "status": 200})) is False)
ck("a batch error is a failure", _verdict("batch error: pool died") is False)
ck("a page whose TEXT merely contains the word error is not a failure",
   _verdict(json.dumps({"ok": True, "text": "Common error codes explained"}))
   is True,
   "the verdict must come from the envelope, not from the page body")

fd = _FakeFeed()
w = _Win(fd)
w._activity_sid = w._activity_begin("run", {"command": "id"})
w._activity_close_result(json.dumps({"ok": True}))
w._activity_close_result(json.dumps({"ok": True}))
ck("a step is closed once, not once per later result", len(fd.ended) == 1,
   str(fd.ended))


# ═══════════════════════════════════════════════════════════════════════
# 6. TOTALITY: display must never be able to strand a turn
# ═══════════════════════════════════════════════════════════════════════
print("\n== every entry point is total ==")


class _Boom:
    """A feed that raises on everything, i.e. the worst case."""
    _disposed = False

    def __getattr__(self, n):
        def _raise(*a, **k):
            raise RuntimeError("feed exploded")
        return _raise


for label, win in (("no feed at all", _Win(None)),
                   ("a feed that raises", _Win(_Boom()))):
    ok = True
    try:
        win._activity_phase("thinking")
        win._activity_note("note", "gate")
        sid = win._activity_begin("run", {"command": "id"})
        win._activity_end(sid, ok=True, preview="x")
        win._activity_close_result("anything")
        win._activity_finish()
    except Exception as e:
        ok = False
        detail = f"{type(e).__name__}: {e}"
    ck(f"{label}: no entry point raises", ok,
       locals().get("detail", ""))

_disposed_feed = _FakeFeed()
_disposed_feed._disposed = True
_w = _Win(_disposed_feed)
_w._activity_phase("x")
_w._activity_note("y")
ck("a disposed feed is ignored, not drawn into",
   not _disposed_feed.phases and not _disposed_feed.notes)


# ═══════════════════════════════════════════════════════════════════════
# 7. The wiring itself — the hooks have to be AT the choke points
# ═══════════════════════════════════════════════════════════════════════
print("\n== the hooks sit on the single choke points ==")


def _body(name):
    m = re.search(r"\n    def %s\(self.*?(?=\n    def )" % re.escape(name),
                  _SRC, re.S)
    return m.group(0) if m else ""


ck("a fresh feed is opened when the operator sends",
   "_activity_new_turn()" in _body("_send_user_message"))
ck("quick-chip actions open one too (they also kick a turn and run tools)",
   "_activity_new_turn()" in _body("_inject_user_request"))
ck("the feed is settled in the single turn-teardown path",
   "_activity_finish()" in _body("_finish_turn_cleanup"))
ck("the step is closed on the single tool-result choke point",
   "_activity_close_result(" in _body("_feed_tool_result"),
   "closing it at the dispatch sites instead is how ACTION RECALL would have "
   "drifted, and the same argument applies here")
ck("the batch opens one row per tool, not one for the batch",
   "_sids = [self._activity_begin(c.name, c.args) for c in calls]"
   in _body("_execute_tool_batch"))
ck("a batch member closes on its own worker's result",
   "_activity_end(_sids[i]" in _body("_execute_tool_batch"),
   "closing them all at the end paints four rows finishing at the slowest "
   "one's time, which is a false picture of a parallel run")
ck("the batch path does not leave a solo sid armed",
   "self._activity_sid = 0" in _body("_execute_tool_batch"),
   "a stale sid would be closed by the combined result and mark an "
   "unrelated tool")
ck("the status pill and the feed header read the same phrase",
   "_activity_phase(label" in _body("_set_working"))
ck("the repeat guard says WHY on the solo path",
   "repeat guard" in _body("_execute_tool_calls")
   and "_activity_note(" in _body("_execute_tool_calls"))

# Each safety refusal must reach the FEED, not only the terminal panel the
# operator has to open on purpose. Checked by proximity on real line numbers:
# the first version of this probe searched for the marker line with
# _SRC.index(), which finds the FIRST occurrence of that text anywhere in the
# file and so proved nothing about where the note actually sits.
_LINES = _SRC.splitlines()
_NOTE_LINES = [i for i, ln in enumerate(_LINES) if "_activity_note(" in ln]


def _noted_near(marker, window=8):
    for i, ln in enumerate(_LINES):
        if marker not in ln:
            continue
        if any(abs(j - i) <= window for j in _NOTE_LINES):
            return True
    return False


ck("the proximity probe can fail (a marker with no note nearby)",
   not _noted_near("def _build_history_for_model"),
   "a probe that cannot report absence cannot report presence either")

for _gate, _marker in (
        ("catastrophic command refused", "catastrophic command refused"),
        ("foresight refusal", "BLOCKED by foresight"),
        ("self-source tamper", "raw write to Basilisk's own source")):
    ck(f"the feed shows the {_gate}", _noted_near(_marker),
       "a hard refusal that only reaches the collapsed terminal panel is a "
       "stall with no reason attached")

ck("the two modes are named once per turn, not once per round-trip",
   "if not _continuation:" in _SRC
   and "LEASHED - answer mode" in _SRC
   and "UNLEASHED - mission active" in _SRC,
   "re-arming a directive on every round-trip is the bug that produced four "
   "identical answers; the same mistake in the feed would print the mode ten "
   "times")


# ═══════════════════════════════════════════════════════════════════════
# 8. Nothing is left ticking
# ═══════════════════════════════════════════════════════════════════════
print("\n== the clock is stopped on every teardown path ==")

# v1.0.0.0 widened this: the clear loop now disposes MessageWidget rows too,
# because a bubble's signal handlers hold a C-side closure back to the bubble
# and unparenting alone frees nothing (20 chats visited 3 times went 270 ->
# 452 -> 634 live bubbles). So the assertion is on the PROPERTY -- a removed
# feed is disposed -- rather than on the literal isinstance line, which is now
# a tuple and would have to be rewritten again the next time it grows.
_lc = _body("_load_chat")
ck("switching chat disposes the feeds it removes",
   "ActivityFeedWidget" in _lc and "dispose_widget()" in _lc)
ck("...and the message bubbles it removes, which leak the same way",
   "MessageWidget" in _lc and "dispose_widget()" in _lc,
   "a bubble unparented with its handlers still connected is never freed")
# v9.9.0 moved the live feed OUT of the message list and into a pinned dock
# above the composer, so "clear the reference" became "empty the dock", which
# does both. The property is unchanged: after a chat switch no feed from the
# previous conversation is still live or still on screen.
ck("switching chat empties the dock",
   "_clear_activity_dock()" in _body("_load_chat"))
ck("emptying the dock also drops the reference",
   "self._activity_feed = None" in _body("_clear_activity_dock"))
ck("and retiring a feed stops its clock",
   "dispose_widget()" in _body("_dock_feed"))
ck("the rolling trim disposes a feed it evicts",
   "isinstance(old, ActivityFeedWidget)" in _body("_append_message_widget"))
ck("the trim never disposes the LIVE feed",
   'old is not getattr(self, "_activity_feed", None)'
   in _body("_append_message_widget"),
   "the view's trim and the window's live pointer are independent — the same "
   "trap MessageWidget's dispose comment describes")
ck("finish() stops the tick before anything else can miss it",
   "_stop_tick()" in _SRC and "def _stop_tick" in _SRC)
ck("finish() marks still-running steps as stopped, never as done",
   "self.stop_running(" in _SRC.split("def finish(")[1][:600],
   "a spinner still spinning over an ended turn is the UI lying")
ck("the empty-state clear does not eat the feed",
   "(MessageWidget, ActivityFeedWidget)" in _body("_append_message_widget"))


# ═══════════════════════════════════════════════════════════════════════
# 9. History is replayed honestly
# ═══════════════════════════════════════════════════════════════════════
print("\n== replayed history claims nothing it cannot know ==")

_rs = _SRC.split("def replay_step(")[1][:1600]
ck("a replayed row does not claim success",
   '_GLYPH["ok"]' not in _rs,
   "the store records that a tool was CALLED and never records whether it "
   "worked; a tick there would be unfalsifiable")
ck("a replayed row carries no duration either", 'time_lbl' not in _rs)
ck("replayed feeds fold shut immediately, not on the live delay",
   "self.set_expanded(False)" in _SRC.split("def finish_history(")[1][:900])
ck("history parses the tool line already on disk, not a new column",
   "_HIST_CALL_RE" in _SRC and "tool:" in _SRC.split("_HIST_CALL_RE = ")[1][:80],
   "a new column would show history only for chats recorded after this build")
ck("a turn's tool calls collapse into ONE feed",
   'items.append(("feed", list(pending)))' in _body("_load_chat"))
ck("bare tool-step bubbles are not redrawn on reload",
   "_reply_is_tool_only(m.content)" in _body("_load_chat"),
   "they are what made one answered question look like four replies")


# ═══════════════════════════════════════════════════════════════════════
# 10. The bubble the feed replaced
# ═══════════════════════════════════════════════════════════════════════
print("\n== a bare tool step draws no bubble, a proposal still does ==")


class _Box:
    def __init__(self):
        self.children = []

    def get_first_child(self):
        return None

    def append(self, w):
        self.children.append(w)

    def remove(self, w):
        pass


def _render(text):
    w = object.__new__(Bk.MessageWidget)
    w.role = "assistant"
    w.meta = {}
    w._content = ""
    w._disposed = False
    w._thoughts = ""
    w._thoughts_container = None
    w._thoughts_label = None
    w._show_thoughts = False
    w._on_run_command = None
    w._on_apply_edit = None
    w._blocks_container = _Box()
    seen = {}
    w.set_visible = lambda v: seen.__setitem__("visible", v)
    w.add_css_class = lambda *a: None
    w.append = lambda *a: None
    w.set_content(text)
    return seen, w


_seen, _ = _render('<tool name="web_read">{"url":"https://a"}</tool>')
ck("a bare tool step hides its bubble", _seen.get("visible") is False,
   str(_seen))

_seen, _ = _render("Here is the answer.")
ck("a real reply is visible", _seen.get("visible") is True, str(_seen))

_seen, _ = _render('<tool name="propose">{"command":"nmap -sV x",'
                   '"explanation":"scan"}</tool>')
ck("a PROPOSAL keeps its bubble (the approval card lives in it)",
   _seen.get("visible") is True, str(_seen))
ck("visibility is derived from the bare-step flag, not from empty text",
   "_bare_tool_step" in _SRC and "set_visible(not _bare_tool_step)" in _SRC,
   "keying off `not display_text` would render an approval card into a "
   "hidden bubble and leave the operator waiting to click something that is "
   "not on screen")


# ═══════════════════════════════════════════════════════════════════════
# 11. Avatars are decoded once, not once per bubble
# ═══════════════════════════════════════════════════════════════════════
print("\n== the texture cache ==")

Bk._TEX_CACHE.clear()
Bk._TEX_MISSES.clear()
_calls = {"n": 0}
_orig = Bk.GdkPixbuf


class _PB:
    class Pixbuf:
        @staticmethod
        def new_from_file_at_size(path, w, h):
            _calls["n"] += 1
            return _Obj()


Bk.GdkPixbuf = _PB
try:
    for _ in range(20):
        Bk._cached_texture("/some/emblem.png", 96)
    ck("20 asks, one decode", _calls["n"] == 1, str(_calls["n"]))
    Bk._cached_texture("/some/emblem.png", 128)
    ck("a different size is its own texture", _calls["n"] == 2,
       "a texture carries its own resolution")

    _calls["n"] = 0

    class _Bad:
        class Pixbuf:
            @staticmethod
            def new_from_file_at_size(path, w, h):
                _calls["n"] += 1
                raise OSError("no such file")

    Bk.GdkPixbuf = _Bad
    for _ in range(20):
        ck_v = Bk._cached_texture("/missing.png", 96)
    ck("a missing file is tried once, not once per bubble",
       _calls["n"] == 1, str(_calls["n"]))
    ck("a miss returns None rather than a broken image", ck_v is None)
finally:
    Bk.GdkPixbuf = _orig
    Bk._TEX_CACHE.clear()
    Bk._TEX_MISSES.clear()

ck("Avatar no longer decodes from disk per bubble",
   "Gtk.Image.new_from_file" not in _body("Avatar") if _body("Avatar")
   else "Gtk.Image.new_from_file(_AVATAR_PNG_PATH)\n            img.set_pixel_size"
        not in _SRC)
_av = _SRC.split("def Avatar(")[1].split("\ndef ")[0]
ck("all four Avatar paths go through the cache",
   _av.count("_cached_image(") == 4 and "new_from_file" not in _av,
   "one uncached path is enough to keep the 9ms-per-bubble decode")
# Slice the WHOLE function, not a fixed byte window. The first version of
# this probe took [:900] and reported a miss on code that was correct — the
# docstring alone is longer than that. A probe that can fail for a reason
# unrelated to the property is not evidence, so it is bounded by the next
# top-level def instead of by a guessed number.
_svgfn = _SRC.split("def _svg_texture(")[1].split("\ndef ")[0]
ck("the _svg_texture probe actually captured the function body",
   "return " in _svgfn and len(_svgfn) > 200, str(len(_svgfn)))
ck("_svg_texture shares the same cache",
   "_cached_texture(path, px)" in _svgfn)


# ═══════════════════════════════════════════════════════════════════════
# 12. The stylesheet stays ASCII
# ═══════════════════════════════════════════════════════════════════════
print("\n== CSS is still a pure-ASCII bytes literal ==")

_raw = open(os.path.join(_ROOT, "basilisk.py"), "rb").read()
_s = _raw.index(b'CSS = b"""')
_e = _raw.index(b'"""', _s + 12)
_css = _raw[_s:_e]
ck("no non-ASCII byte reached the CSS",
   all(b < 128 for b in _css),
   "the CSS is a bytes literal; one smart quote is a startup decode error, "
   "i.e. a black window instead of a cosmetic bug")
ck("the feed's styles are actually in there",
   b".activity-feed" in _css and b".activity-step" in _css
   and b".activity-header" in _css)
ck("the live rail is the only new animation",
   _css.count(b"@keyframes activityRail") == 1)

# The feed's glyphs sit inline with monospace text. A codepoint the emoji font
# claims (U+26D4, U+26A0, U+2757) is rendered by that font instead: wrong
# colour, wrong width, wrong baseline, and immune to the row's CSS. Refusals
# are the rows that must read clearly, so they get an ASCII mark.
_EMOJI_CLAIMED = ("\u26d4", "\u26a0", "\u2757", "\u274c", "\u2705",
                  "\U0001f6d1")
_glyphs = Bk.ActivityFeedWidget._GLYPH
ck("no feed glyph is one the emoji font takes over",
   not any(g in _EMOJI_CLAIMED for g in _glyphs.values()),
   str({k: v for k, v in _glyphs.items() if v in _EMOJI_CLAIMED}))
ck("the gate glyph is plain ASCII", _glyphs["gate"].isascii(),
   _glyphs["gate"])


# ═══════════════════════════════════════════════════════════════════════
# 13. Citations have to render as links, and the renderer must never emit
#     markup GTK will refuse
# ═══════════════════════════════════════════════════════════════════════
print("\n== cited sources render as links ==")

TP = Bk.text_to_pango

ck("a markdown link becomes an anchor",
   '<a href="https://www.kernel.org/">kernel.org</a>'
   in TP("Source: [kernel.org](https://www.kernel.org/) front page."),
   "ANSWER MODE orders the model to cite its source, so every leashed answer "
   "ended in literal [text](url) at the bottom of the reply")
ck("a bare pasted url is linkified too",
   '<a href="https://example.org/a">https://example.org/a</a>'
   in TP("see https://example.org/a"))
ck("a url inside backticks stays code, not a destination",
   "<a href" not in TP("`https://in-code.example/x`"))
ck("the sentence's full stop is not swallowed into the href",
   TP("see https://a.org/p.").endswith("."))
ck("a comma after a url is not part of it",
   '<a href="https://a.org/p">' in TP("see https://a.org/p, then"))
ck("a model cannot forge a sentinel and inject a link",
   "<a href" not in TP("\ue0000\ue001 hi") and "<a href" not in TP("0 hi"),
   "the sentinel is Private Use Area precisely so model output cannot collide "
   "with it, but a forged one must still be inert")
ck("bold survives", "<b>x</b>" in TP("**x**"))
ck("italic survives", "<i>x</i>" in TP("*x*"))
ck("inline code survives", "JetBrains Mono" in TP("`x`"))
ck("plain text is left alone", TP("hello world") == "hello world")
ck("escaping still happens", TP("a < b & c") == "a &lt; b &amp; c")
ck("a quote inside a url is escaped as an ATTRIBUTE, not as body text",
   "&quot;" in TP('[x](https://a/?q="v")'),
   "the body escape does not touch quotes; an href must")

print("\n== the renderer never emits markup GTK will refuse ==")

WF = Bk._markup_is_wellformed
ck("nested tags are well formed", WF("<b>a<i>b</i>c</b>"))
ck("interleaved tags are NOT", not WF("<i>a<span>b</i>c</span>"),
   "this is exactly what three independent regex passes produce on stray "
   "asterisks and backticks, and GTK renders it as raw markup on screen")
ck("an unclosed tag is not well formed", not WF("<b>a"))
ck("a stray closer is not well formed", not WF("a</b>"))
ck("plain text is well formed", WF("no tags here"))
ck("a '>' inside an attribute does not end the tag",
   WF('<a href="https://a/?x=>">t</a>'),
   "a naive scanner would see the attribute's > as the tag's > and then "
   "reject every link with a > in its query string")

_ADVERSARIAL = [
    "))b`*(?_`-=)=:[ )&https://b**_>/*=https://",
    '?">=:**https://**`**z?#<z`/[x](/5\n\\ ?-5:<\n`:',
    "*" * 60, "`" * 60, "**a*b**c*", "`a*b`c*d*",
    "[x](https://a/*b*) and *c* and `d`",
    "<b>literal</b> plus **real**",
]
_bad = [c for c in _ADVERSARIAL if not WF(TP(c))]
ck("hand-picked adversarial inputs all render well formed",
   not _bad, repr(_bad[:2]))

import random as _rnd                                            # noqa: E402
_rnd.seed(11)
_alph = list("abz *`_[]()<>&\"'\\/:.?=#-\n") + ["https://", "**", "[x](", ")"]
_fuzz_bad = 0
for _ in range(4000):
    _c = "".join(_rnd.choice(_alph) for _ in range(_rnd.randint(1, 40)))
    if not WF(TP(_c)):
        _fuzz_bad += 1
ck("4000 fuzzed inputs all render well formed", _fuzz_bad == 0,
   str(_fuzz_bad))

# COUNTER-PROPERTY: a renderer that gives up is not a fix.
_kept = 0
for _ in range(400):
    _c = ("Some **bold** and a [link](https://example.org/%d) and `code`."
          % _rnd.randint(1, 999))
    _o = TP(_c)
    if "<b>bold</b>" in _o and "<a href" in _o and "JetBrains Mono" in _o:
        _kept += 1
ck("ordinary prose still gets the FULL formatting, not the fallback",
   _kept == 400, str(_kept),
   )

# And it must stay linear: this runs once per rendered message, over the whole
# message, and this file has shipped a quadratic display path twice.
import time as _t                                                # noqa: E402
_base = "Some **bold** and a [link](https://example.org/x) and `code`. "


def _ms(mult):
    _txt = _base * mult
    _n = 12
    _s0 = _t.perf_counter()
    for _ in range(_n):
        TP(_txt)
    return (_t.perf_counter() - _s0) / _n


_small = _ms(300)
_big = _ms(1200)
ck("4x the input costs less than 8x the time (linear, not quadratic)",
   _big < _small * 8, f"{_small*1000:.2f}ms -> {_big*1000:.2f}ms")


print(f"\n{_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
