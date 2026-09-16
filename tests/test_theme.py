#!/usr/bin/env python3
"""test_theme.py — the Claude-coloured dark theme is pinned, not described.

The accent has migrated red -> blue -> grey -> (interim green) -> Claude coral.
Each migration left cold accent hexes hardcoded in dozens of custom-widget rules
that a token-only change did not touch — which is exactly why the UI "still
looked black and grey" after the accent token alone was changed. This suite
fails if any of the retired accent colours creep back, if the coral stops
carrying the accent, or if a semantic colour (danger/amber/success) gets
swept up in a re-tint. Stdlib-only, no GTK needed.

Run:  python3 tests/test_theme.py
"""
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


_bsrc = open(os.path.join(_ROOT, "basilisk.py"), "rb").read()
_m = re.search(rb'CSS = b"""(.*?)"""', _bsrc, re.S)
ck("the CSS bytes literal is present", bool(_m))
_css_bytes = _m.group(1) if _m else b""
_css = _css_bytes.decode("latin-1")

print("\n== the bytes literal stays ASCII-only (GTK loads it as bytes) ==")
ck("CSS is ASCII-only",
   all(b < 128 for b in _css_bytes),
   str([hex(b) for b in _css_bytes if b > 127][:5]))

print("\n== retired accent colours are gone ==")
# Every accent colour from a previous era must be fully migrated — no stragglers
# hiding in a custom-widget rule.
for retired, era in (("#45484a", "grey accent-hi"),
                     ("#292a2b", "grey accent-base"),
                     ("#55c295", "interim phosphor-green"),
                     ("rgba(69, 72, 74", "grey accent glow"),
                     ("rgba(85, 194, 149", "green accent glow")):
    ck(f"no {era} ({retired}) remains", _css.count(retired) == 0,
       f"{_css.count(retired)} left")

print("\n== Claude coral carries the accent ==")
ck("coral #d97757 is used widely (not just one token)",
   _css.count("#d97757") >= 20, str(_css.count("#d97757")))
ck("a deeper coral #a94f34 provides the two-tone accent",
   _css.count("#a94f34") >= 1, str(_css.count("#a94f34")))
ck("coral glow rgba(217, 119, 87 is present",
   _css.count("rgba(217, 119, 87") >= 1, str(_css.count("rgba(217, 119, 87")))
ck("the accent token is coral",
   "@define-color accent_color              #d97757;" in _css
   or re.search(r"accent_color\s+#d97757;", _css) is not None)
ck("suggested-action fill is coral (#c15f3c), white text",
   re.search(r"accent_bg_color\s+#c15f3c;", _css) is not None
   and re.search(r"accent_fg_color\s+#ffffff;", _css) is not None)
ck("the online 'ready' dot is coral",
   re.search(r"\.online-dot\.online\s*\{[^}]*#d97757", _css) is not None)

print("\n== semantic colours were NOT swept into the re-tint ==")
ck("danger red #e5484d survived", _css.count("#e5484d") >= 5,
   str(_css.count("#e5484d")))
ck("warning amber #f0a500 survived", _css.count("#f0a500") >= 3,
   str(_css.count("#f0a500")))
ck("success green #2ecc71 survived", _css.count("#2ecc71") >= 3,
   str(_css.count("#2ecc71")))
# coral must not collide with danger red — they must stay distinguishable
ck("coral and danger red are different colours",
   "#d97757" != "#e5484d")

print("\n== the theme still describes itself honestly ==")
ck("the palette comment names the Claude/coral theme, not the old blue/Kali one",
   "Claude" in _css and "dragon-blue accent (#a94f34" not in _css)

print(f"\ntheme: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
