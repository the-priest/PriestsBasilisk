#!/usr/bin/env python3
"""
test_sandbox_skills.py — the two modules that execute agent-written code had
no test at all.

WHY THIS EXISTS
===============
A coverage map of the tree found six modules with no direct test — about 1,385
lines — and two of them were `sandbox.py` and `skills.py`: the pair that takes
Python the MODEL wrote and runs it. That is the last place in this codebase
that should be running unverified, and it is exactly the shape of the last
three bugs found here (the speech path, the headroom engine): the defect sits
where the suite cannot see it.

Four real defects were in those 1,385 lines:

  1. `run_skill(name)` did `self.dir / name` with NO validation, so
     `skill_run{name: "../elsewhere/planted"}` loaded and EXECUTED a skill.py
     from outside the store. That skips the whole commit path — ast check,
     static screen, and the sandbox test gate — and the store reported zero
     saved skills while running one.

  2. The bwrap tier ran with `preexec=None`, so the STRONGEST isolation tier
     was the only one with no resource limits. It confines the filesystem and
     the network and does nothing about memory or CPU — the module docstring
     promised "every tier adds ... rlimits".

  3. RLIMIT_CPU was hardcoded to DEFAULT_TIMEOUT, ignoring the caller's
     `timeout`, so `run_python(..., timeout=60)` was still SIGXCPU'd at 20s of
     CPU and reported as a skill failure rather than a limit being hit.

  4. `import resource` at module scope, unguarded. resource is POSIX-only,
     skills imports sandbox, extman imports skills, and basilisk_ext/__init__
     imports extman — so on Windows the ImportError took out the ENTIRE
     sidecar package (workspace, recall, memory, oracle, bench, headroom),
     silently, because the host's ext import is correctly guarded. CI
     publishes a Windows EXE.

Run:  python3 tests/test_sandbox_skills.py
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from basilisk_ext import sandbox as S                           # noqa: E402
from basilisk_ext.skills import SkillStore                      # noqa: E402

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


_TMP = tempfile.mkdtemp(prefix="basilisk-test-skills-")


def _script(code: str) -> str:
    d = tempfile.mkdtemp(dir=_TMP)
    p = os.path.join(d, "s.py")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(code)
    return p


# ── 1. the skills store is confined to the skills directory ──────────
print("\n== a skill can only be run from inside the store ==")
_sd = os.path.join(_TMP, "skills")
store = SkillStore(_sd)

# Plant something OUTSIDE the store that looks exactly like a valid skill —
# i.e. anything the model could have dropped there with write_file.
_outside = os.path.join(_TMP, "elsewhere", "planted")
os.makedirs(_outside, exist_ok=True)
_code = "def run(args):\n    return {'executed_from': 'OUTSIDE'}\n"
with open(os.path.join(_outside, "skill.py"), "w", encoding="utf-8") as fh:
    fh.write(_code)
with open(os.path.join(_outside, "manifest.json"), "w", encoding="utf-8") as fh:
    json.dump({"name": "planted", "capabilities": [],
               "hash": hashlib.sha256(_code.encode()).hexdigest()}, fh)

for _bad in ("../elsewhere/planted", "..", "../../etc", "/etc/passwd",
             "./planted", "planted/../../elsewhere/planted",
             "sub/planted", "a" * 60, "", "Adder", "add-er", "1adder",
             ".hidden", "adder/", "adder\\x00"):
    _r = store.run_skill(_bad, {})
    ck(f"refused: {_bad!r}", _r.get("ok") is False and "not a valid" in
       str(_r.get("error", "")), str(_r)[:110])

ck("…and nothing outside the store was executed",
   "OUTSIDE" not in json.dumps(store.run_skill("../elsewhere/planted", {})))

# The boundary helper itself, directly.
ck("_skill_dir rejects a traversal name",
   store._skill_dir("../x") is None)
ck("_skill_dir accepts a plain name",
   store._skill_dir("adder") is not None)
ck("_skill_dir keeps the result directly under the store",
   str(store._skill_dir("adder").parent) == str(store.dir.resolve()))

# A symlink planted INSIDE the store must not become a way out — resolve()
# before comparing is what catches this.
_link = os.path.join(_sd, "escape")
try:
    os.symlink(os.path.join(_TMP, "elsewhere"), _link)
    ck("a symlink inside the store does not lead out",
       store._skill_dir("escape") is None
       or str(store._skill_dir("escape")).startswith(str(store.dir.resolve())))
except (OSError, NotImplementedError):      # pragma: no cover
    ck("a symlink inside the store does not lead out (skipped: no symlinks)",
       True)


# ── 2. the legitimate path still works end to end ────────────────────
print("\n== the real commit -> run path is unaffected ==")
_good = "def run(args):\n    return {'sum': args.get('a', 0) + args.get('b', 0)}\n"
_test = "assert run({'a': 2, 'b': 3})['sum'] == 5\n"
_c = store.commit("adder", _good, _test, "adds two numbers", [])
ck("a valid skill commits", _c.get("ok") is True, str(_c)[:160])
_r = store.run_skill("adder", {"a": 40, "b": 2})
ck("…and runs", _r.get("ok") is True, str(_r)[:120])
ck("…returning its value", '"sum": 42' in (_r.get("stdout") or ""),
   (_r.get("stdout") or "")[:80])
ck("…and is listed", [s["name"] for s in store.list_skills()] == ["adder"])

_bad_commit = store.commit("adder2", "def run(args): return {}\n",
                           "assert False, 'this test fails'\n", "x", [])
ck("a skill whose test FAILS is not saved", _bad_commit.get("ok") is False)
ck("…and did not land in the store",
   "adder2" not in [s["name"] for s in store.list_skills()])

ck("a bad name is refused at commit",
   store.commit("../evil", _good, _test, "x", []).get("ok") is False)
ck("an unknown capability is refused",
   store.commit("capful", _good, _test, "x", ["root"]).get("ok") is False)
ck("code with no run() is refused",
   store.commit("norun", "x = 1\n", "assert True\n", "x", []).get("ok") is False)

# staging dirs must not leak into the listing or the store
ck("staging dirs are not listed as skills",
   [s["name"] for s in store.list_skills()] == ["adder"],
   str(os.listdir(_sd)))


# ── 3. a broken skill on disk is a broken skill, not a crash ─────────
print("\n== malformed state degrades, it does not raise ==")
_broken = os.path.join(_sd, "broken")
os.makedirs(_broken, exist_ok=True)
with open(os.path.join(_broken, "manifest.json"), "w", encoding="utf-8") as fh:
    fh.write("{not json")
with open(os.path.join(_broken, "skill.py"), "w", encoding="utf-8") as fh:
    fh.write("def run(a):\n    return {}\n")
_r = store.run_skill("broken", {})
ck("a corrupt manifest returns an error", _r.get("ok") is False)
ck("…that names the problem", "unreadable" in str(_r.get("error", "")),
   str(_r.get("error"))[:90])

_noname = os.path.join(_sd, "noname")
os.makedirs(_noname, exist_ok=True)
with open(os.path.join(_noname, "manifest.json"), "w", encoding="utf-8") as fh:
    fh.write('{"description": "manifest with no name field"}')
try:
    _pb = store.prompt_block()
    ck("prompt_block survives a manifest with no name", bool(_pb))
except Exception as e:
    ck("prompt_block survives a manifest with no name", False,
       f"{type(e).__name__}: {e}")
ck("…and that manifest is not advertised to the model",
   "None" not in store.prompt_block())

_nocode = os.path.join(_sd, "nocode")
os.makedirs(_nocode, exist_ok=True)
with open(os.path.join(_nocode, "manifest.json"), "w", encoding="utf-8") as fh:
    json.dump({"name": "nocode", "hash": "x"}, fh)
ck("a manifest with no skill.py returns an error",
   store.run_skill("nocode", {}).get("ok") is False)

_tamper = os.path.join(_sd, "adder", "skill.py")
with open(_tamper, "a", encoding="utf-8") as fh:
    fh.write("\n# edited by hand\n")
ck("a hand-edited skill is refused (hash check still holds)",
   "hash mismatch" in str(store.run_skill("adder", {}).get("error", "")))


# ── 4. every isolation tier caps resources ───────────────────────────
print("\n== the sandbox limits what it runs ==")
ck("capabilities_report names a tier",
   isinstance(S.capabilities_report().get("tier"), str))

_r = S.run_python(_script("import json, sys\nprint(json.dumps({'argv': sys.argv[1]}))"),
                  args_json='{"a": 1}')
ck("a basic script runs", _r["ok"] is True, str(_r)[:140])
# argv[1] is the args JSON as a STRING, so it comes back re-escaped — decode it
# rather than substring-matching the escaped form.
ck("…and receives its args verbatim on argv[1]",
   json.loads(json.loads(_r["stdout"])["argv"]) == {"a": 1},
   repr(_r["stdout"])[:90])

_r = S.run_python(_script("import time\ntime.sleep(30)\n"), timeout=3)
ck("the wall-clock timeout fires", _r["timed_out"] is True and _r["ok"] is False)
ck("…and does not wait for the full sleep", _r["duration"] < 10, str(_r["duration"]))

_r = S.run_python(_script("x = bytearray(600 * 1024 * 1024)\n"),
                  timeout=20, mem_mb=128)
ck("the memory rlimit fires ON THE ACTIVE TIER", _r["ok"] is False,
   f"tier={_r['tier']} rc={_r['rc']}")

_r = S.run_python(_script("open('big', 'wb').write(b'x' * (40 * 1024 * 1024))\n"),
                  timeout=20, fsize_mb=4)
ck("the file-size rlimit fires", _r["ok"] is False,
   f"tier={_r['tier']} rc={_r['rc']}")

# THE BUG: the CPU limit must track the caller's timeout, not DEFAULT_TIMEOUT.
_probe = _script("import resource, json\n"
                 "print(json.dumps({'cpu': resource.getrlimit(resource.RLIMIT_CPU)[0],\n"
                 "                  'as_mb': resource.getrlimit(resource.RLIMIT_AS)[0] // 1048576,\n"
                 "                  'fsize_mb': resource.getrlimit(resource.RLIMIT_FSIZE)[0] // 1048576}))\n")
for _t in (5, 45):
    _r = S.run_python(_probe, timeout=_t, mem_mb=64, fsize_mb=8)
    _seen = json.loads(_r["stdout"] or "{}") if _r["ok"] else {}
    ck(f"timeout={_t} gives the child a {_t}s CPU limit, not "
       f"{S.DEFAULT_TIMEOUT}s", _seen.get("cpu") == _t, str(_r)[:140])
    ck(f"…and the memory cap is honoured too (timeout={_t})",
       _seen.get("as_mb") == 64, str(_seen))
    ck(f"…and the file-size cap (timeout={_t})",
       _seen.get("fsize_mb") == 8, str(_seen))

_r = S.run_python(_script("import urllib.request as u\n"
                          "print(u.urlopen('http://example.com', timeout=5).status)\n"),
                  timeout=15)
ck("network is denied by default", _r["ok"] is False, str(_r)[:120])

_r = S.run_python(os.path.join(_TMP, "does-not-exist.py"))
ck("a missing script is an error, not an exception", _r["ok"] is False)
ck("…naming the staging failure", "stage" in _r["stderr"], _r["stderr"][:80])


# ── 5. the POSIX-only import must not sink the whole package ─────────
print("\n== the sidecar still imports where `resource` does not exist ==")


class _Block:
    """Simulate Windows: no `resource` module.

    THIS USED TO USE find_module/load_module, WHICH DO NOTHING ON 3.12.
    Python removed the legacy meta-path protocol in 3.12, so the blocker was
    silently ignored: `import resource` still succeeded, the four import
    assertions below passed against a module that had `resource` all along
    (vacuously green), and the refusal assertion failed because the sandbox
    picked its `unshare` tier instead. find_spec is the live protocol.
    """

    def find_spec(self, name, path=None, target=None):
        if name == "resource":
            raise ImportError("No module named 'resource'")
        return None


_saved = {k: v for k, v in sys.modules.items()
          if k == "resource" or k.startswith("basilisk_ext")}
for _k in list(sys.modules):
    if _k == "resource" or _k.startswith("basilisk_ext"):
        del sys.modules[_k]
sys.meta_path.insert(0, _Block())
try:
    for _mod in ("basilisk_ext.sandbox", "basilisk_ext.skills",
                 "basilisk_ext.extman", "basilisk_ext"):
        try:
            importlib.import_module(_mod)
            ck(f"{_mod} imports without `resource`", True)
        except Exception as e:
            ck(f"{_mod} imports without `resource`", False,
               f"{type(e).__name__}: {e}")
    # …and it must REFUSE to run, not run unconfined.
    try:
        _sb = importlib.import_module("basilisk_ext.sandbox")
        # …with the namespace tools hidden too: "no resource module" is a
        # Windows fact, and on Windows there is no bwrap and no unshare
        # either. Blocking only the import tested a machine that does not
        # exist, and let a Linux box answer a Windows question.
        _have0 = _sb._have
        _sb._have = lambda _c: False
        try:
            _res = _sb.run_python(_script("print('should not run')\n"))
        finally:
            _sb._have = _have0
        ck("…and refuses to execute agent code with no isolation at all",
           _res["ok"] is False and _res["tier"] == "none", str(_res)[:140])
        ck("…saying so plainly", "refusing" in _res["stderr"],
           _res["stderr"][:90])
    except Exception as e:
        ck("…and refuses to execute agent code with no isolation at all",
           False, f"{type(e).__name__}: {e}")
finally:
    sys.meta_path.pop(0)
    for _k in list(sys.modules):
        if _k == "resource" or _k.startswith("basilisk_ext"):
            del sys.modules[_k]
    sys.modules.update(_saved)

shutil.rmtree(_TMP, ignore_errors=True)

print(f"\nsandbox_skills: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
