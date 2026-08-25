#!/usr/bin/env python3
"""
test_packaging.py — pyproject.toml must keep telling the truth about the repo.

WHY THIS FILE EXISTS
====================
This project already learned what an unchecked file manifest costs.  install.sh
lists the sidecar modules to fetch, and a module added to the repo but not to
that list is simply ABSENT on a remote install — no error, just a feature that
isn't there.  tests/test_sidecar_store.py pins that list now.

pyproject.toml is the same manifest problem with a wider blast radius, because
a wheel is what a stranger installs:

  * `py-modules` is written out explicitly rather than auto-discovered.  That
    is deliberate — auto-discovery on a flat layout sweeps up tests/ and any
    stray top-level .py — but it means a new basilisk_*.py module is silently
    DROPPED from the wheel, and the app ImportErrors on someone else's machine.
  * `package-data` globs by extension.  Add a .webp to the art and it silently
    does not ship; the app falls back to no icon and nobody finds out.
  * The version is written twice (here and basilisk.VERSION) because reading it
    dynamically would make the BUILD import basilisk.py, which imports gi at
    module scope — you would need GTK installed just to learn a version string.
    Two copies of one fact is the defect shape this codebase keeps finding, so
    it gets pinned instead of trusted.
  * Dependencies are declared by hand.  A new unguarded `import requests` at
    module scope is a broken install for everyone who doesn't happen to have it.

Every check below is derived FROM THE REPO, so it fails when reality moves and
the manifest doesn't.  None of it imports basilisk.py — that needs GTK.

Run:  python3 tests/test_packaging.py
"""

from __future__ import annotations

import ast
import io
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


def _rel(*parts):
    return os.path.join(_ROOT, *parts)


_PYPROJECT_PATH = _rel("pyproject.toml")
_RAW = io.open(_PYPROJECT_PATH, encoding="utf-8").read()

# tomllib is 3.11+; requires-python is 3.10.  Parse properly when we can and
# fall back to targeted extraction when we can't, so this suite runs on the
# floor it claims to support.
try:
    import tomllib
    _TOML = tomllib.loads(_RAW)
    _HAVE_TOML = True
except Exception:
    _TOML = {}
    _HAVE_TOML = False


def _list_field(section_re: str, key: str) -> list:
    """Pull a TOML array of strings without a parser."""
    m = re.search(section_re + r".*?\b" + key + r"\s*=\s*\[(.*?)\]", _RAW, re.S)
    return re.findall(r'"([^"]+)"', m.group(1)) if m else []


if _HAVE_TOML:
    _PROJECT = _TOML.get("project", {})
    _ST = _TOML.get("tool", {}).get("setuptools", {})
    _PY_MODULES = _ST.get("py-modules", [])
    _PACKAGES = _ST.get("packages", [])
    _PKG_DIR = _ST.get("package-dir", {})
    _PKG_DATA = _ST.get("package-data", {})
    _DEPS = _PROJECT.get("dependencies", [])
    _NAME = _PROJECT.get("name", "")
    _VERSION = _PROJECT.get("version", "")
    _REQ_PY = _PROJECT.get("requires-python", "")
    _SCRIPTS = _PROJECT.get("scripts", {})
else:
    _PY_MODULES = _list_field(r"\[tool\.setuptools\]", "py-modules")
    _PACKAGES = _list_field(r"\[tool\.setuptools\]", "packages")
    _DEPS = _list_field(r"\[project\]", "dependencies")
    _PKG_DIR = dict(re.findall(r'^\s*([\w.]+)\s*=\s*"([^"]+)"\s*$',
                    _RAW.split("[tool.setuptools.package-dir]")[-1]
                    .split("[")[0], re.M)) if "package-dir" in _RAW else {}
    _PKG_DATA = {"basilisk_assets": _list_field(
        r"\[tool\.setuptools\.package-data\]", "basilisk_assets")}
    _NAME = (re.search(r'^name\s*=\s*"([^"]+)"', _RAW, re.M) or [None, ""])[1]
    _VERSION = (re.search(r'^version\s*=\s*"([^"]+)"', _RAW, re.M) or [None, ""])[1]
    _REQ_PY = (re.search(r'^requires-python\s*=\s*"([^"]+)"', _RAW, re.M) or [None, ""])[1]
    _SCRIPTS = dict(re.findall(r'^\s*([\w-]+)\s*=\s*"([^"]+)"\s*$',
                    _RAW.split("[project.scripts]")[-1].split("[")[0], re.M)) \
        if "[project.scripts]" in _RAW else {}

print(f"  (toml parser: {'tomllib' if _HAVE_TOML else 'regex fallback'})")


# ── 1. the version is written twice; the copies must agree ────────────
print("\n== the two copies of the version agree ==")
_src = io.open(_rel("basilisk.py"), encoding="utf-8").read()
_code_version = re.search(r'^VERSION\s*=\s*"([^"]+)"', _src, re.M)
ck("basilisk.py declares VERSION", _code_version is not None)
ck(f"pyproject version matches basilisk.VERSION ({_code_version.group(1)})",
   _VERSION == _code_version.group(1),
   f"pyproject={_VERSION!r} code={_code_version.group(1)!r}")
ck("the README badge agrees too",
   f"badge/version-{_VERSION}-" in io.open(_rel("README.md"), encoding="utf-8").read(),
   f"README badge must show {_VERSION}")
ck("distribution name is set", _NAME == "priestsbasilisk", _NAME)


# ── 2. every shipped module is actually listed ────────────────────────
print("\n== the wheel carries every module in the repo ==")
_top_real = {f[:-3] for f in os.listdir(_ROOT)
             if f.endswith(".py") and f.startswith("basilisk")}
_listed = set(_PY_MODULES)
ck("py-modules was parsed", bool(_listed))
ck("no top-level module is missing from py-modules",
   not (_top_real - _listed),
   f"would ship WITHOUT: {sorted(_top_real - _listed)}")
ck("py-modules lists nothing that does not exist",
   not (_listed - _top_real),
   f"listed but absent: {sorted(_listed - _top_real)}")
ck("basilisk_ext ships as a package", "basilisk_ext" in _PACKAGES)
ck("basilisk_assets ships as a package", "basilisk_assets" in _PACKAGES)
ck("tests/ is NOT shipped as an importable package",
   not any(p.startswith("tests") for p in _PACKAGES),
   "the suite belongs in the sdist, not in site-packages")


# ── 3. the assets package maps onto the real art directory ────────────
print("\n== the art ships, once, from where it already lives ==")
ck("package-dir maps basilisk_assets onto assets/app",
   _PKG_DIR.get("basilisk_assets") == "assets/app", str(_PKG_DIR))
ck("assets/app has an __init__.py so it is importable",
   os.path.isfile(_rel("assets", "app", "__init__.py")))
ck("the art is not duplicated into a second directory",
   not os.path.isdir(_rel("basilisk_assets")),
   "a second copy of a 7MB tree would drift from the first")

_globs = _PKG_DATA.get("basilisk_assets", [])
_ext_declared = {g.lstrip("*") for g in _globs}
_ext_real = {os.path.splitext(f)[1] for f in os.listdir(_rel("assets", "app"))
             if not f.endswith(".py") and os.path.splitext(f)[1]}
ck("package-data globs were parsed", bool(_ext_declared))
ck("every art file extension present is declared",
   not (_ext_real - _ext_declared),
   f"these would be silently dropped from the wheel: "
   f"{sorted(_ext_real - _ext_declared)}")

# The app looks the art up at runtime; the search must include the wheel.
ck("basilisk.py searches the packaged asset dir",
   "_PKG_ASSET_DIR" in _src and "basilisk_assets" in _src)
ck("the packaged dir is searched LAST",
   _src.index("legacy flat") < _src.index("# wheel"),
   "a dev checkout and an install.sh install must win over the wheel copy")
ck("the asset import can never take the app down",
   re.search(r"def _packaged_asset_dir.*?except Exception:\s*\n\s*return None",
             _src, re.S) is not None)


# ── 4. the entry point resolves ───────────────────────────────────────
print("\n== the console script points at something real ==")
ck("a 'basilisk' console script is declared", "basilisk" in _SCRIPTS, str(_SCRIPTS))
_target = _SCRIPTS.get("basilisk", "")
ck("it targets basilisk:main", _target == "basilisk:main", _target)
_tree = ast.parse(_src)
_module_level_fns = {n.name for n in _tree.body
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
ck("basilisk.py defines main() at module level", "main" in _module_level_fns)
for _alias, _tgt in _SCRIPTS.items():
    _mod, _, _fn = _tgt.partition(":")
    ck(f"script {_alias!r} -> {_tgt} is resolvable",
       _mod in _top_real and _fn in _module_level_fns, _tgt)


# ── 5. declared dependencies cover the unguarded imports ──────────────
#
# "Unguarded" = a direct child of the module body.  Anything inside a try/except
# or a function is a lazy, optional import the app already survives without —
# those belong in optional-dependencies, not here.
print("\n== every import the app cannot start without is declared ==")
_IMPORT_TO_DIST = {
    "gi": "pygobject",
    "cairo": "pycairo",
    "cv2": "opencv-python-headless",
    "yaml": "pyyaml",
    "brotli": "brotli",
}
_LOCAL = _top_real | {"basilisk_ext", "basilisk_assets", "headroom"}
_STD = set(sys.stdlib_module_names)

_shipped = [_rel(f + ".py") for f in sorted(_top_real)]
_shipped += [_rel("basilisk_ext", f) for f in sorted(os.listdir(_rel("basilisk_ext")))
             if f.endswith(".py")]

_unguarded: dict = {}
for _path in _shipped:
    for _node in ast.parse(io.open(_path, encoding="utf-8").read()).body:
        _names = []
        if isinstance(_node, ast.Import):
            _names = [a.name.split(".")[0] for a in _node.names]
        elif isinstance(_node, ast.ImportFrom) and _node.level == 0 and _node.module:
            _names = [_node.module.split(".")[0]]
        for _n in _names:
            if _n not in _STD and _n not in _LOCAL and _n != "__future__":
                _unguarded.setdefault(_n, set()).add(os.path.basename(_path))

_declared = {re.split(r"[<>=!\[; ]", d)[0].strip().lower() for d in _DEPS}
ck("dependencies were parsed", bool(_declared), str(_DEPS))
for _imp, _where in sorted(_unguarded.items()):
    _dist = _IMPORT_TO_DIST.get(_imp, _imp).lower()
    ck(f"unguarded import {_imp!r} ({', '.join(sorted(_where))}) is declared",
       _dist in _declared,
       f"add {_dist!r} to [project] dependencies")
ck("gi is among them (the app is a GTK4 app)", "gi" in _unguarded)
ck("nothing else is unguarded",
   set(_unguarded) == {"gi"},
   f"new hard dependency introduced: {sorted(set(_unguarded) - {'gi'})}")

# The lazily-imported extras must still be offered, or a user has no
# documented way to turn those features on.
_extras_raw = _RAW.split("[project.optional-dependencies]")[-1].split("\n[")[0] \
    if "[project.optional-dependencies]" in _RAW else ""
for _feature in ("opencv", "brotli", "yaml"):
    ck(f"optional extra offered for {_feature}",
       _feature in _extras_raw.lower(), "lazy imports need an install path")


# ── 6. the sdist carries what an auditor needs ────────────────────────
print("\n== the source distribution is auditable ==")
_mani = io.open(_rel("MANIFEST.in"), encoding="utf-8").read()
for _need, _why in [
    ("tests", "the suite is the evidence; an sdist without it cannot be checked"),
    ("LICENSE", "MIT licence must travel with the source"),
    ("README.md", "the long_description is read from it"),
    ("install.sh", "the documented install path"),
]:
    ck(f"MANIFEST.in ships {_need}", _need in _mani, _why)
for _junk in ("__pycache__", "*.py[cod]"):
    ck(f"MANIFEST.in excludes {_junk}", _junk in _mani)


# ── 7. the declared floor is real ─────────────────────────────────────
print("\n== the python floor is honest ==")
ck("requires-python is declared", bool(_REQ_PY), _REQ_PY)
_floor = re.search(r"(\d+)\.(\d+)", _REQ_PY)
ck("floor is at least 3.10 (PyGObject's own floor)",
   _floor and (int(_floor.group(1)), int(_floor.group(2))) >= (3, 10), _REQ_PY)
ck("this interpreter meets the declared floor",
   sys.version_info[:2] >= (int(_floor.group(1)), int(_floor.group(2))))

print(f"\npackaging: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
