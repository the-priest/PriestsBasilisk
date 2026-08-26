#!/usr/bin/env python3
"""
test_btn_art.py — the embedded button art is the ONE production module with no
direct test, and it is 11k lines of base64 that nothing else validates.

The art was embedded in a required .py precisely so it can never go missing on
an update the way a separate optional-PNG fetch could. But "present" is not
"valid": a corrupted paste, a truncated blob, or a key renamed on one side of
the wire would all leave the module importable and the buttons silently
falling back to symbolic icons — exactly the class of failure the embedding
was meant to end. This pins it:

  · every blob decodes to a real PNG (magic bytes), not just valid base64
  · every button the app requests (_BTN_*) has a matching blob
  · every blob is actually requested (no dead art, no typo'd key)

Run:  python3 tests/test_btn_art.py
"""

from __future__ import annotations

import base64
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import basilisk_btn_art as A                                   # noqa: E402

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


_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_ART = getattr(A, "BTN_ART_B64", None)

print("== the embedded art is present and shaped right ==")
ck("BTN_ART_B64 exists and is a non-empty dict",
   isinstance(_ART, dict) and len(_ART) > 0,
   f"got {type(_ART).__name__}")

print("\n== every blob decodes to a real PNG ==")
_decoded = {}
for _k, _v in (_ART or {}).items():
    try:
        _raw = base64.b64decode(_v, validate=True)
        _decoded[_k] = _raw
        ck(f"{_k}: valid base64 -> PNG",
           _raw[:8] == _PNG_MAGIC,
           "decodes but is not a PNG (magic bytes wrong) — button would be "
           "blank or fall back to symbolic")
    except Exception as e:
        ck(f"{_k}: valid base64", False, f"{type(e).__name__}: {e}")

# A PNG that decodes but is a 0-byte or stub image is still a silent failure.
print("\n== and each is a plausibly-real image, not a stub ==")
for _k, _raw in _decoded.items():
    ck(f"{_k}: non-trivial size", len(_raw) > 1000,
       f"only {len(_raw)} bytes — likely a truncated paste")

# ── the wire between the app and the art ──────────────────────────────
print("\n== every button the app asks for has art, and vice versa ==")
_APP = open(os.path.join(_ROOT, "basilisk.py"), encoding="utf-8").read()
_requested = set(re.findall(r'_BTN_[A-Z]+\s*=\s*_find_btn_png\("([a-z]+)"\)',
                            _APP))
_have = set(_ART or {})

ck("the app requests at least one button", bool(_requested))
for _key in sorted(_requested):
    ck(f"requested '{_key}' has embedded art", _key in _have,
       "the button would silently fall back to a symbolic icon")

# Dead art is not fatal, but it is almost always a renamed-key typo — the app
# asks for 'sound' while the blob is keyed 'audio', say. Flag it.
_dead = _have - _requested
ck("no embedded blob is left unrequested (a stray key is a typo)",
   not _dead, f"unreferenced art keys: {sorted(_dead)}")

print(f"\nbtn_art: {_passed} passed, {_failed} failed")
sys.exit(1 if _failed else 0)
