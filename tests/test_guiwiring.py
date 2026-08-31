#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_guiwiring.py — GUI bugs you can only find by RUNNING the thing.

WHY THIS EXISTS
===============
Every bug pinned here was invisible to the rest of the suite, because the rest
of the suite never builds a real window. They were found by launching the real
app headlessly against a seeded conversation and looking at what it drew and
what it printed to stderr:

  1. `Gtk.Button(label=" Listen")` followed by `set_icon_name(...)`. set_icon_name
     REPLACES the button's child, so the label was silently discarded and the
     read-aloud control rendered as a bare icon circle floating under the reply,
     attached to nothing. Nothing errored. It just looked broken.

  2. The chat watermark: a bright 2MB photographic PNG at opacity 0.5 with
     ContentFit.CONTAIN. Contain letterboxes a landscape image inside a tall
     chat pane, so the art appeared as a glowing BAND across the middle with
     plain background above and below it — it read as content someone had
     pasted into the conversation rather than as a backdrop, and it fought
     every line of text over it.

  3. Overlay scrollbars float ON TOP of content, so the rightmost thing in a
     row — the user's avatar — was drawn underneath the scrollbar.

  4. libadwaita warned 25 times in a 16-state sweep that the window "does not
     have a minimum size". Without one there is nothing for the adaptive
     machinery to break against, so a narrow window can squeeze children past
     their own minimums, which is how widgets end up overlapping.

  5. THE ONE THAT WOULD HAVE SHIPPED: pycairo is a HARD dependency (pyproject
     declares it) and install.sh — the recommended path, the one the README
     documents — never installed it. Without it PyGObject cannot marshal a
     cairo context into a Python draw callback AT ALL: it raises
     `TypeError: Couldn't find foreign struct converter for 'cairo.Context'`
     in the BINDING layer, before a line of the callback runs. So DragonSplash's
     own try/except never saw it, its docstring's promise to degrade gracefully
     "if no cairo" was false, the splash painted nothing, and stderr took that
     line at 60fps for the whole animation.

Run:  python3 tests/test_guiwiring.py
"""

from __future__ import annotations

import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = open(os.path.join(_ROOT, "basilisk.py"), encoding="utf-8").read()
_SH = open(os.path.join(_ROOT, "install.sh"), encoding="utf-8").read()

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


def body(pattern):
    """Slice a def/class body, bounded by the next top-level one — never by a
    guessed byte count. A fixed window has reported code missing that was
    present three times in this project."""
    i = _SRC.find(pattern)
    if i < 0:
        return ""
    rest = _SRC[i:]
    nxt = re.search(r"\n(?:def |class )", rest[1:])
    return rest[:nxt.start() + 1] if nxt else rest


# ═══════════════════════════════════════════════════════════════════════
# 1. set_icon_name DESTROYS a label — nowhere may rely on both
# ═══════════════════════════════════════════════════════════════════════
print("== a button cannot have a label AND set_icon_name ==")

_lines = _SRC.split("\n")
_bad = []
for i, ln in enumerate(_lines):
    if "set_icon_name" not in ln:
        continue
    ctx = "\n".join(_lines[max(0, i - 4):i])
    # A label set on the SAME widget in the preceding lines is destroyed by
    # this call. An `else:` branch is the legitimate fallback shape and is not
    # a collision — the label path returned already.
    if re.search(r'Button\(\s*label\s*=', ctx) and "else:" not in ctx:
        _bad.append(i + 1)
ck("no button sets a label and then overwrites it with an icon",
   not _bad, "lines " + str(_bad))

ck("the Listen control builds its child explicitly",
   "_sb.append(Gtk.Label(label=\"Listen\"))" in _SRC
   and "self.speak_btn.set_child(_sb)" in _SRC,
   "an icon AND a word is two children, so the child has to be a box")

_speak = body("    def _build_shell(self):")
ck("the read-aloud button is still wired to the speak handler",
   "self._on_speak(self)" in _SRC)

# ═══════════════════════════════════════════════════════════════════════
# 2. The watermark has to be a watermark
# ═══════════════════════════════════════════════════════════════════════
print("\n== the chat backdrop ==")

_wm = body("    def _build_chat_watermark(self):")
ck("the watermark probe captured the method", "opacity" in _wm, str(len(_wm)))

_ops = [float(x) for x in re.findall(r"opacity\s*=\s*([0-9.]+)", _wm)]
ck("every watermark opacity is backdrop-strength (<= 0.20)",
   bool(_ops) and all(o <= 0.20 for o in _ops), str(_ops))
ck("the PNG path is not left at half opacity",
   all(o < 0.5 for o in _ops), str(_ops))
ck("it COVERs the pane instead of letterboxing a band across it",
   "Gtk.ContentFit.COVER" in _wm,
   "CONTAIN put a bright band across the middle of the chat with plain "
   "background above and below, which is what made it read as content")
ck("it stays non-interactive", "set_can_target(False)" in _wm)

# ═══════════════════════════════════════════════════════════════════════
# 3. Overlay scrollbars sit on top of the content
# ═══════════════════════════════════════════════════════════════════════
print("\n== the scrollbar gutter ==")

ck("the message list reserves a gutter for the overlay scrollbar",
   "_SCROLLBAR_GUTTER" in _SRC
   and "8 + self._SCROLLBAR_GUTTER" in _SRC,
   "without it the user's avatar is drawn underneath the scrollbar")
ck("overlay scrolling is still on (that is why the gutter is needed)",
   "set_overlay_scrolling(True)" in _SRC)

# ═══════════════════════════════════════════════════════════════════════
# 4. The window has a minimum size
# ═══════════════════════════════════════════════════════════════════════
print("\n== window minimum size ==")

_init = body("    def __init__(self, app: \"BasiliskApp\"):")
ck("MainWindow declares a minimum size",
   "set_size_request(" in _init,
   "libadwaita warns once per layout pass without one, and a window with no "
   "floor can squeeze children past their own minimums")
_m = re.search(r"set_size_request\((\d+),\s*(\d+)\)", _init)
# THIS ASSERTION USED TO READ `<= 420`, AND IT WAS ENFORCING THE BUG.
# The declared minimum was 360 -- narrower than the content pane's own
# measured minimum of 480 -- and a size request below what the children need
# does not make them fit, it makes GTK allocate less than the minimum and clip
# the rest off the right edge. At a 458px window the Close button was sliced in
# half, the model pill was truncated, the avatar was off screen, and
# libadwaita said so on every layout pass ("AdwToastOverlay exceeds MainWindow
# width: requested 462 px, 458 px available") -- the exact warning the
# set_size_request call above was added to silence.
#
# The honest property is not "as small as we wish" but "not smaller than we
# can draw", with an upper bound so nobody quietly makes the app desktop-only.
ck("the declared minimum is at least what the content can be drawn in",
   _m and int(_m.group(1)) >= 480,
   (_m.group(1) if _m else "?") + " -- a floor under the content's own "
   "minimum clips the header rather than shrinking it")
ck("...and is still modest enough for a small screen",
   _m and int(_m.group(1)) <= 560, _m.group(1) if _m else "?")

# ═══════════════════════════════════════════════════════════════════════
# 5. pycairo — the dependency the installer forgot
# ═══════════════════════════════════════════════════════════════════════
print("\n== pycairo ==")

_splash = body("class DragonSplash(Gtk.Window):")
ck("the splash probe captured the class", "DrawingArea" in _splash,
   str(len(_splash)))
_probe = _splash.find("import cairo as _cairo_probe")
_area = _splash.find("Gtk.DrawingArea()")
ck("DragonSplash probes for pycairo BEFORE building the DrawingArea",
   0 <= _probe < _area,
   "the try/except inside _draw cannot catch this: PyGObject fails while "
   "MARSHALLING the context, before the callback runs")

_pyproj = open(os.path.join(_ROOT, "pyproject.toml"), encoding="utf-8").read()
ck("pyproject still declares pycairo as a hard dependency",
   "pycairo" in _pyproj)

for mgr, pkg in (("apt-get", "python3-cairo"),
                 ("pacman", "python-cairo"),
                 ("dnf", "python3-cairo")):
    ck(f"install.sh installs the cairo binding for {mgr}", pkg in _SH)
ck("install.sh verifies pycairo separately from GTK",
   'python3 -c "import cairo"' in _SH,
   "python3-gi does not pull it in on Debian/Kali, so the GTK check passing "
   "says nothing about cairo")

# ═══════════════════════════════════════════════════════════════════════
# 6. Installer safety, kept from the CachyOS pass
# ═══════════════════════════════════════════════════════════════════════
print("\n== installer ==")

_bare_sudo = [i + 1 for i, ln in enumerate(_SH.split("\n"))
              if re.search(r"(?<![$\w])sudo ", ln)
              and "command -v sudo" not in ln]
ck("no bare `sudo` survives — escalation is detected",
   not _bare_sudo, "lines " + str(_bare_sudo))
# COMMENTS ARE NOT USES. The first version of this probe did a plain
# _SH.index("$ESC ") and matched the explanatory comment ABOVE the definition,
# reporting a shell-ordering bug in a script that was correctly ordered.
_sh_lines = _SH.split("\n")


def _first_line(pred):
    for i, ln in enumerate(_sh_lines):
        if ln.lstrip().startswith("#"):
            continue
        if pred(ln):
            return i + 1
    return 10 ** 9


_def_at = _first_line(lambda l: re.match(r'\s*ESC=', l))
_use_at = _first_line(lambda l: "$ESC " in l)
ck("the $ESC probe skips comments",
   _def_at < 10 ** 9 and _use_at < 10 ** 9,
   f"def@{_def_at} use@{_use_at}")
ck("$ESC is defined before any real use",
   _def_at < _use_at, f"defined line {_def_at}, used line {_use_at}")
ck("no `pacman -Sy` (a partial upgrade breaks Arch/CachyOS)",
   "pacman -Sy " not in _SH and "pacman -Sy\n" not in _SH)
ck("CachyOS and Kali are named explicitly",
   "*cachy*" in _SH and "*kali*" in _SH)

# ═══════════════════════════════════════════════════════════════════════
# 7. The activity feed is DOCKED, and nothing repaints at idle
# ═══════════════════════════════════════════════════════════════════════
print("\n== the docked status strip ==")

ck("the dock exists and lives in the composer area",
   "self.activity_dock" in _SRC
   and 'area.append(self.activity_dock)' in _SRC,
   "inside the message list it scrolled off the top after a few more "
   "messages, which is the one thing a status surface may not do")
ck("the dock is placed ABOVE the action buttons",
   _SRC.index("area.append(self.activity_dock)")
   < _SRC.index("area.append(actions_row)"))
ck("a new turn retires the previous feed through the dock",
   "self._dock_feed(feed)" in _SRC)
ck("retiring a feed stops its clock",
   "old.dispose_widget()" in body("    def _dock_feed(self, feed):"),
   "every turn would otherwise leave another 200ms timer running for the "
   "life of the process")
ck("switching chats empties the dock",
   "_clear_activity_dock()" in body("    def _load_chat(self, chat_id: int):"),
   "the dock is outside the message list, so clearing the list does not "
   "clear it and the old chat's strip stays pinned over the new one")
# Scoped to the LIVE-turn method: _append_history_feed still puts a replayed
# feed inline in the transcript, which is correct — that one is a record of a
# past turn, not a status strip. A global search would have called that a
# regression.
_newturn = body("    def _activity_new_turn(self):")
ck("the new-turn probe captured the method",
   "ActivityFeedWidget()" in _newturn, str(len(_newturn)))
ck("the LIVE feed is no longer appended to the message list",
   "msg_box.append" not in _newturn, _newturn[-200:])
ck("history feeds are still rendered inline in the transcript",
   "self.msg_box.append(feed)" in body("    def _append_history_feed(self, rows):"))

print("\n== nothing animates while the app is idle ==")

_css_i = _SRC.index('CSS = b"""')
_css = _SRC[_css_i:_SRC.index('"""', _css_i + 12)]
_STATE = (".busy", ".live", ".working", ".toggled", ".speaking",
          ".recording", ":hover", ":active")
_always = []
for _m in re.finditer(r"([^\n{}]+)\{([^{}]*animation:[^{}]*)\}", _css):
    _sel, _blk = _m.group(1).strip(), _m.group(2)
    _a = re.search(r"animation:\s*([^;]+);", _blk).group(1)
    if "infinite" in _a and not any(x in _sel for x in _STATE):
        _always.append(_sel)
ck("no infinite animation runs without a state class",
   not _always, str(_always))
# A probe that finds nothing proves nothing: assert it can still SEE the
# stateful animations before trusting its verdict about the always-on ones.
ck("the animation audit can actually see the animations",
   _css.count("infinite") >= 3, str(_css.count("infinite")))
ck("the selected sidebar row no longer animates forever",
   "animation: metalglow" not in _css,
   "it is on screen from launch to exit, so an infinite keyframe there is a "
   "permanent idle repaint loop")

print("\n== the watermark is not re-decoded or oversized ==")

ck("the chat watermark goes through the shared texture cache",
   "_cached_texture(path, 1100)" in _wm,
   "full resolution is 1672x941 = a 6MB RGBA texture that COVER rescales "
   "behind the chat on every scroll frame and every streamed token")
ck("and still falls back if the cache cannot load it",
   "Gdk.Texture.new_from_filename(path)" in _wm)


# ═══════════════════════════════════════════════════════════════════════
# 8. Scrolling: a one-shot scroll cannot reach a bottom it has not measured
# ═══════════════════════════════════════════════════════════════════════
print("\n== the newest message has to land visible ==")

ck("the view sticks to the bottom via the adjustment's own signal",
   '_on_vadj_changed' in _SRC and 'adj.connect("changed"' in _SRC,
   "GLib.idle_add + set_value(upper) reads `upper` from BEFORE the new bubble "
   "was laid out, so the view jumped to the OLD bottom and the newest message "
   "sat below the fold behind the composer")
ck("the operator scrolling up clears the stick",
   "_on_vadj_value_changed" in _SRC
   and "self._stick_bottom = at_bottom" in body("    def _on_vadj_value_changed(self, adj):"))
ck("our own snap does not count as the operator moving",
   "_scroll_self" in body("    def _snap_bottom(self, adj=None):")
   and "_scroll_self" in body("    def _on_vadj_value_changed(self, adj):"),
   "without the guard the snap would immediately clear the flag it just set")
ck("the stickiness is actually wired up",
   "self._wire_scroll_stickiness()" in _SRC)
ck("a forced scroll re-arms the stick",
   "self._stick_bottom = True" in body("    def _force_scroll_to_bottom(self):"),
   "so the snap survives the layout passes that follow it")

print("\n== no block may set a floor under the window width ==")

# The list once carried a set_width_chars floor to keep a Gtk.Grid's minimum
# width down. But that ALSO fixed the natural width, so a bulleted reply hugged
# the whole bubble narrow and the list towered. The list is a box of rows now
# (see test_richblocks) and needs no such floor — pin that it is gone, so it
# cannot drift back and re-tower the bubble.
ck("the list body no longer pins its width",
   re.search(r"body\.set_width_chars\(", _SRC) is None,
   "set_width_chars fixed natural width too and hugged the bubble narrow")
_tblsrc = _SRC.split("class TableWidget")[1].split("\nclass ")[0]
_TBL_WC = re.search(r"lbl\.set_width_chars\((\d+)\)", _tblsrc)
ck("table cells keep a small minimum too (they scroll horizontally)",
   _TBL_WC is None or int(_TBL_WC.group(1)) <= 8)


# ── backdrop brightness setting (Display page) ───────────────────────
print("\n== the backdrop brightness control is wired ==")
_CORE = open(os.path.join(_ROOT, "basilisk_core.py"), encoding="utf-8").read()
ck("backdrop_brightness has a default",
   '"backdrop_brightness":' in _CORE)
ck("its default is the mid value (50)",
   '"backdrop_brightness": 50' in _CORE)
ck("MainWindow has the live-apply method",
   "_apply_backdrop_brightness" in _SRC)
ck("the scrim reference is captured for live re-tint",
   "self._chat_scrim = scrim" in _SRC)
ck("the Display page builds a brightness SpinRow",
   "self.brightness_row" in _SRC and "Background brightness" in _SRC)
_op = lambda b: 0.78 - (max(0, min(100, b)) / 100.0) * (0.78 - 0.06)
ck("opacity stays within [0.06, 0.78] across the range",
   all(0.06 <= _op(b) <= 0.78 for b in (0, 25, 50, 75, 100)))
ck("50 maps to about the shipped default scrim (~0.42)",
   abs(_op(50) - 0.42) < 0.02)


# ── Unleash arms and waits; it does not auto-fire a turn ─────────────
print("\n== pressing Unleash arms and waits (no auto-kickoff) ==")
# The handler must NOT call _kick_assistant_turn and must NOT latch a mission
# from stale history. Pressing Unleash arms the suite + mode and then waits for
# the operator's objective, exactly like leashed waits. The operator reported
# it "just goes off" the instant the button was pressed.
_uh = _SRC[_SRC.index("def _on_unleash_toggled"):
           _SRC.index("def _open_settings")]
ck("unleash handler does not kick a turn",
   "_kick_assistant_turn()" not in _uh,
   "arming must not auto-fire a turn - it arms and waits for the objective")
ck("unleash handler does not latch a mission from history",
   "_mission_active = True" not in _uh,
   "arming must not latch a mission onto stale history the operator did not "
   "re-issue")
ck("arming still forces agent mode on",
   "agent_toggle.set_active(True)" in _uh)
ck("arming still opens a chat if none exists",
   "_new_chat()" in _uh)


# ── composer buttons: camera & suggestion gone, terminal moved to header ──
print("\n== composer button changes ==")
# Enter while working sends a suggestion (nudge without stopping); the mouse
# Stop control is untouched. Camera and the Suggestion button are removed.
_key = _SRC[_SRC.index("def _on_input_key"):_SRC.index("def _on_send_or_stop")]
ck("Enter while busy sends a suggestion, not a stop",
   "_send_suggestion()" in _key and "if self._is_busy():" in _key,
   "typing + Enter mid-run must nudge without stopping")
ck("send/stop button still stops on click (unchanged)",
   "_request_stop()" in _SRC[_SRC.index("def _on_send_or_stop"):
                             _SRC.index("def _set_send_mode")])
ck("Suggestion button is gone",
   "self.suggest_btn" not in _SRC,
   "removed - Enter replaces it")
ck("Camera button is gone from the composer loop",
   "_user_action_camera, _BTN_CAMERA" not in _SRC)
ck("Terminal toggle is built in the header (moved up)",
   "hb.pack_end(self.terminal_toggle_btn)" in _SRC)
ck("Terminal toggle is a glyph button, not PNG art",
   '_glyph_button(\n            ">_"' in _SRC or '_glyph_button(">_"' in _SRC
   or ('_glyph_button(' in _SRC and '">_"' in _SRC))
ck("glyph-btn CSS exists for the image-free buttons",
   ".glyph-btn {" in _SRC and ".glyph-btn.active" in _SRC)


# ── the streaming bubble is deferred until the first real text token ──
print("\n== streaming bubble defers past tool-only activity ==")
# The empty assistant bubble used to appear the instant a turn started, then
# sit blank through a web-search/tool call and flicker back out. Now it's built
# detached and only attached to the chat on the first TEXT token (or at finish
# if it ended up with content). A pure tool-only turn attaches nothing.
_kick = _SRC[_SRC.index("_streaming_attached = False"):
             _SRC.index("self.streaming_msg_db_id = self.store.add_message")]
ck("turn start builds the bubble detached (no immediate append)",
   "_streaming_attached = False" in _kick
   and "_append_message_widget(\n" not in _kick,
   "bubble must not be appended at turn start")
ck("first text token attaches the bubble",
   "_attach_streaming_bubble()" in _SRC[_SRC.index("def _on_stream_token"):
                                        _SRC.index("def _on_stream_reasoning")])
ck("attach helper is idempotent and guards content",
   "_attach_streaming_bubble" in _SRC
   and "if getattr(self, \"_streaming_attached\", True):" in _SRC)
ck("teardown attaches a deferred bubble only if it has content",
   "_attach_streaming_bubble()" in _SRC[_SRC.index("def _finish_turn_cleanup"):
                                        _SRC.index("def _mission_continue")])


print(f"\n{_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
