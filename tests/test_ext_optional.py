#!/usr/bin/env python3
"""
test_ext_optional.py — a missing sidecar must never stop the app from starting.

basilisk.py states the rule in its own import comments: a sidecar module that
is absent or fails to import (a partial install, or a platform-specific import
error like the POSIX-only `resource` that once took out the whole ext package
on Windows) must DEGRADE the tools that use it, never crash startup. `recall`
followed the rule; `zdayfind` and `exploits` did NOT — they were bare
`from basilisk_ext import …` lines, so a broken exploits.py meant the whole GUI
failed to launch, taking every unrelated tool down with it.

This pins the fix two ways:
  · SOURCE — the offensive sidecar imports are guarded (try/except → None),
    and the offensive dispatch null-checks the module.
  · BEHAVIOUR — with exploits.py and zdayfind.py physically removed, importing
    basilisk still succeeds and the affected tools report `unavailable`.

Run:  python3 tests/test_ext_optional.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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


# ── SOURCE: the guards are present ───────────────────────────────────
print("== the offensive sidecar imports are defensive ==")
_SRC = open(os.path.join(_ROOT, "basilisk.py"), encoding="utf-8").read()

for _mod, _alias in (("zdayfind", "_zdayfind"), ("exploits", "_exploits")):
    # a guarded import assigns None in an except; a bare import does not.
    _guarded = (f"import {_mod} as {_alias}" in _SRC
                and f"{_alias} = None" in _SRC)
    ck(f"{_mod} is imported defensively (assigns None on failure)",
       _guarded,
       "a bare `from basilisk_ext import …` crashes startup on a partial "
       "install")

ck("there is a uniform 'module unavailable' degradation helper",
   "_ext_unavailable" in _SRC)
# every offensive tool that uses a sidecar module null-checks it.
for _tool in ("zday_scan", "saml_attack", "cloud_storage",
              "subdomain_takeover", "padding_oracle", "xslt_injection"):
    ck(f"{_tool} null-checks its module before calling it",
       f'_ext_unavailable("{_tool}"' in _SRC,
       "would raise AttributeError on None instead of degrading")


# ── BEHAVIOUR: the app starts with the modules gone ──────────────────
print("\n== the app starts even with the offensive modules removed ==")
_tmp = tempfile.mkdtemp(prefix="ext-optional-")
_proj = os.path.join(_tmp, "proj")
shutil.copytree(_ROOT, _proj,
                ignore=shutil.ignore_patterns("__pycache__", ".git", "tests"))
for _f in ("exploits.py", "zdayfind.py"):
    _p = os.path.join(_proj, "basilisk_ext", _f)
    if os.path.exists(_p):
        os.remove(_p)

# import basilisk from the mutilated copy in a clean module namespace
_saved = dict(sys.modules)
for _m in list(sys.modules):
    if _m.startswith("basilisk"):
        del sys.modules[_m]
sys.path.insert(0, _proj)
try:
    import basilisk as _Bk  # noqa
    ck("basilisk imports with exploits.py and zdayfind.py deleted", True)
    ck("_exploits degraded to None", getattr(_Bk, "_exploits", "x") is None)
    ck("_zdayfind degraded to None", getattr(_Bk, "_zdayfind", "x") is None)
    _r = _Bk._ext_unavailable("saml_attack", "exploits")()
    ck("a tool on the missing module returns a clean unavailable result",
       isinstance(_r, dict) and _r.get("ok") is False
       and _r.get("unavailable") is True,
       str(_r)[:120])
except Exception as e:  # noqa
    import traceback
    ck("basilisk imports with exploits.py and zdayfind.py deleted", False,
       f"{type(e).__name__}: {e}")
    traceback.print_exc()
finally:
    sys.path.remove(_proj)
    sys.modules.clear()
    sys.modules.update(_saved)
    shutil.rmtree(_tmp, ignore_errors=True)

print(f"\next_optional: {_passed} passed, {_failed} failed")
sys.exit(1 if _failed else 0)
