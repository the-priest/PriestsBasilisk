#!/usr/bin/env python3
"""
test_bubble_fit.py — the bubble must be as tall as the text inside it.

REPORTED AS: "text is still flowing out of bubbles and shit".

A reply's last paragraph drew BELOW its own bubble background, on top of the
Listen button. It only appeared at the UI scales real machines use, which is
why three earlier layout sweeps missed it: every harness ran at the headless
default scale, where the same reply happened to fit.

THE MECHANISM. The bubble was built with

    inner.set_halign(Gtk.Align.START)
    inner.set_hexpand(False)

inside a VERTICAL box. A vertical GtkBox asks its child "how tall are you at
MY width", then -- because halign=START means "take your natural width" --
allocates it something narrower. The bubble's content is wrapped text and a
two-column list, so narrower means taller: it was sized from the answer to a
question about a wider box. Measured at ui_scale 0.5: allocated 490px, needed
576px, and 43px of text drew outside.

THE FIX. A HORIZONTAL box settles every child's WIDTH first and only then
asks for height, so the width the bubble is measured at is the width it gets.
The bubble now fills a hug row whose trailing spacer eats the slack -- the
same pattern the user row already used -- so a short reply still draws a small
bubble instead of spanning the window.

This test is GUI-level and needs GTK. It SKIPS (exit 0) where GTK or a
display is unavailable, so it never fails the suite for an environment
reason -- but where it can run, it runs the real app.

Run:  python3 tests/test_bubble_fit.py
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Gtk, Adw, GLib          # noqa: F401
except Exception as _e:                                # pragma: no cover
    print(f"bubble fit: SKIPPED (no GTK4 bindings: {type(_e).__name__})")
    sys.exit(0)

if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
    print("bubble fit: SKIPPED (no display)")
    sys.exit(0)

os.environ.setdefault("HOME", tempfile.mkdtemp())
_cfg = pathlib.Path(os.environ["HOME"]) / ".config" / "basilisk"
_cfg.mkdir(parents=True, exist_ok=True)

_passed = 0
_failed = 0


def ck(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  PASS {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}" + (f"   [{detail}]" if detail else ""))


# A reply with the shapes that made the bug appear: wrapped bullets with bold
# leads, an emoji, and a closing paragraph -- that closing paragraph is what
# landed outside the bubble.
LONG = """Here's what's happening today:

- **Dolly Parton** died at 80 - country music legend, career spanning six decades.
- **USS Abraham Lincoln** heading to Thailand after 250+ days at sea, longest Middle East deployment in recent memory; crew conditions under scrutiny.
- **New Jersey migrant raid** - ~50 people arrested at a bonded warehouse in Oct 2025; deportations have torn apart dozens of families.
- **Venezuela** - two months after the earthquakes, La Guaira is slowly reopening (only 1,700 of ~7,000 businesses back).
- **Trump administration** facing a bond market squeeze; Treasury looking for unconventional ways to contain rising rates ahead of Jackson Hole.
- **China's Chang'e-7** moon mission delayed, reigniting the race with the US for the lunar south pole.
- **Brazil** - lynching in Copacabana: a man accused of stealing a bicycle was beaten to death by security guards and delivery workers; four jailed.
- **Argentina** - Tierra del Fuego denounces a British oil tanker in southern waters.

Want me to dig into any of these?"""

CASES = [
    ("short reply", "Yes."),
    ("two words", "Port 22."),
    ("one line", "The host is up and ports 22 and 80 are open."),
    ("a table", "| Tool | Speed |\n|---|---|\n| nuclei | fast |\n| ffuf | very fast |"),
    ("a code block", "```bash\nnmap -sS 10.0.0.1\necho done\n```"),
    ("a block quote",
     "> a quote that runs on and on and needs to wrap several times to show "
     "that the rail and the body stay aligned when it does"),
    ("the long list", LONG),
    ("long prose", "Plain paragraph that wraps. " * 30),
    ("an unbreakable token", "token " + "supercalifragilistic" * 12),
    ("a very long url", "See https://example.org/" + "a" * 250),
]

# The scales real machines pick. _detect_ui_scale returns 0.7 for a desktop
# monitor, 0.85 for a laptop, 0.9 for a phone -- the bug lived at all of them
# and at none of the headless defaults, which is the whole lesson here.
SCALES = [float(x) for x in
          (os.environ.get("BUBBLE_SCALES") or "0.5,0.7,0.85,1.0").split(",")]

_results: list = []


def _run_scale(scale: float) -> None:
    (_cfg / "settings.json").write_text(json.dumps({
        "siliconflow_api_key": "sk", "active_provider": "siliconflow",
        "ui_scale": scale}), encoding="utf-8")

    import importlib
    import basilisk as Bk
    importlib.reload(Bk) if "basilisk" in sys.modules else None
    Bk._default_window_size = lambda: (810, 719)
    app = Bk.BasiliskApp()

    out = {"scale": scale, "rows": [], "viewport": 0, "error": None}

    def win_of():
        for w in app.get_windows():
            if isinstance(w, Bk.MainWindow):
                return w
        return None

    def go(*_a):
        win = win_of()
        if win is None:
            return True
        st = win.store
        cid = st.create_chat("fit", "m")
        for label, body in CASES:
            st.add_message(cid, "user", label)
            st.add_message(cid, "assistant", body)
        win._load_chat(cid)

        def check():
            try:
                sw = win.msg_scroll
                out["viewport"] = sw.get_width()
                c = win.msg_box.get_first_child()
                idx = 0
                while c is not None:
                    if isinstance(c, Bk.MessageWidget):
                        b = c._blocks_container
                        if b is not None:
                            ok, ri = b.compute_bounds(sw)
                            if ok:
                                cls = b.get_css_classes() or []
                                role = ("user" if "msg-user" in cls
                                        else "assistant")
                                bb = ri.origin.y + ri.size.height
                                br = ri.origin.x + ri.size.width
                                over = 0.0
                                ch = b.get_first_child()
                                while ch is not None:
                                    ok2, rc = ch.compute_bounds(sw)
                                    if ok2:
                                        over = max(
                                            over,
                                            (rc.origin.y + rc.size.height) - bb,
                                            (rc.origin.x + rc.size.width) - br)
                                    ch = ch.get_next_sibling()
                                if role == "assistant":
                                    out["rows"].append({
                                        "label": CASES[idx][0] if idx < len(CASES) else "?",
                                        "w": ri.size.width, "h": ri.size.height,
                                        "over": max(0.0, over)})
                                    idx += 1
                    c = c.get_next_sibling()
            except Exception as e:
                out["error"] = f"{type(e).__name__}: {e}"
            app.quit()
            return False

        GLib.timeout_add(2800, check)
        return False

    GLib.timeout_add(1400, go)
    GLib.timeout_add(45000, lambda: (app.quit(), False)[1])
    app.run([])
    _results.append(out)


# ── ONE PROCESS PER SCALE ──
# GTK cannot run a second Gtk.Application in one process, so this used to be
# a loop with a `break` in it: SCALES listed four values and exactly one --
# 0.5 -- was ever measured. _detect_ui_scale() returns 0.7 for a desktop, 0.85
# for a laptop and 0.9 for a phone, so the regression test written because
# "the bug only exists at the scales real machines use" was guarding the one
# scale no machine picks. Each scale now runs in its own interpreter and
# reports its measurements back; the assertions all happen here, once.
if os.environ.get("BUBBLE_ONE_SCALE"):
    _run_scale(SCALES[0])
    print("RESULT " + json.dumps(_results[-1]))
    sys.exit(0)

import subprocess                                            # noqa: E402
def _measure(scale, attempt=0):
    """One child process, one scale. Retries an EMPTY measurement once.

    The first GTK process on a cold box pays font/icon cache warm-up and can
    miss the harness's own settle timer, which reports "no bubbles to
    measure" -- an environment flake, not an overflow. A retry distinguishes
    the two: a real failure is empty twice.
    """
    _env = dict(os.environ, BUBBLE_ONE_SCALE="1", BUBBLE_SCALES=str(scale))
    _r = subprocess.run([sys.executable, os.path.abspath(__file__)],
                        env=_env, capture_output=True, text=True, timeout=300)
    _line = ""
    for _l in (_r.stdout or "").splitlines():
        if _l.startswith("RESULT "):
            _line = _l[len("RESULT "):]
    if _line:
        _out = json.loads(_line)
        if _out.get("rows") or _out.get("error") or attempt:
            return _out
        return _measure(scale, attempt + 1)
    if not attempt:
        return _measure(scale, 1)
    return {"scale": scale, "rows": [], "viewport": 0,
            "error": f"harness process failed (rc {_r.returncode}): "
                     f"{(_r.stderr or '')[-160:]}"}


for _s in SCALES:
    _results.append(_measure(_s))

print("== the bubble is never shorter than its own text ==")
for res in _results:
    if res["error"]:
        ck(f"scale {res['scale']}: measured cleanly", False, res["error"])
        continue
    ck(f"scale {res['scale']}: rows were rendered", bool(res["rows"]),
       "the harness found no assistant bubbles to measure")
    for row in res["rows"]:
        ck(f"scale {res['scale']}: {row['label']} stays inside its bubble",
           row["over"] <= 1,
           f"{row['over']:.0f}px of content drew outside the background")
        ck(f"scale {res['scale']}: {row['label']} fits the viewport",
           row["w"] <= res["viewport"] + 2,
           f"bubble {row['w']:.0f} > viewport {res['viewport']}")

    # THE COUNTER-PROPERTY. The construction this replaced existed to stop a
    # two-word reply drawing a full-width bubble, and that must still hold --
    # a fix that makes every bubble span the window would pass every check
    # above and look wrong.
    _short = [r for r in res["rows"] if r["label"] in ("short reply", "two words")]
    for row in _short:
        ck(f"scale {res['scale']}: {row['label']} still hugs its text",
           row["w"] < res["viewport"] * 0.4,
           f"bubble {row['w']:.0f}px of a {res['viewport']}px viewport -- "
           f"hugging was lost")

print("\n== the wiring that guarantees it ==")
_SRC = open(os.path.join(_ROOT, "basilisk.py"), encoding="utf-8").read()
ck("the bubble is not halign=START inside a vertical box",
   "inner.set_halign(Gtk.Align.START)" not in _SRC,
   "that is the construction that sized the bubble from the wrong width")
ck("hugging moved to a horizontal row with a trailing spacer",
   "_hug = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)" in _SRC
   and "_hug_spacer" in _SRC)
# Assert on the RULE BODIES, not on the file: the comment above them quotes
# the old one-sided values on purpose, and a test that trips over its own
# explanation is a bad test (this one did, first time out).
def _rule_body(name: str) -> str:
    m = re.search(r"^\.%s \{(.*?)^\}" % re.escape(name), _SRC, re.S | re.M)
    return m.group(1) if m else ""


for _rule in ("msg-user", "msg-assistant"):
    _body = _rule_body(_rule)
    _m = re.search(r"^\s*margin:\s*([^;]+);", _body, re.M)
    ck(f".{_rule} declares a margin", _m is not None)
    _parts = (_m.group(1).split() if _m else [])
    ck(f".{_rule} margin is symmetric ({' '.join(_parts)})",
       len(_parts) == 2,
       "a one-sided margin widens the measure/allocate disagreement that "
       "sized the bubble from the wrong width")
ck("the far-side inset moved to the column",
   ".msg-column-assistant { margin-right: 48px; }" in _SRC
   and ".msg-column-user      { margin-left: 48px; }" in _SRC)

print(f"\nbubble fit: {_passed} passed, {_failed} failed")
sys.exit(1 if _failed else 0)
