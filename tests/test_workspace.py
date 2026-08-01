#!/usr/bin/env python3
"""
test_workspace.py — the repo workspace and, mostly, its containment boundary.

WHY THE BALANCE OF THIS FILE IS 70% SECURITY: the workspace is the first
feature that takes a FILE FROM OUTSIDE and writes its contents to disk under
a name the file itself chooses. Every other input Basilisk handles is a
command string it parses. A zip is different: `extractall()` on an archive
containing "../../.ssh/authorized_keys" writes outside the destination, and
that is CVE-2007-4559, still shipping in Python's own tarfile in 2022.

The three attacks asserted here are the three that actually happen:
  · ZIP SLIP     — a member name that traverses out of the destination
  · SYMLINK      — a link entry pointing at /, followed by a write through it
  · ZIP BOMB     — 42 KB expanding to petabytes of the operator's disk

Plus the one that is not an attack at all but an agent mistake: Basilisk is
autonomous under UNLEASH, and a model that decides the fix belongs in
~/.bashrc is not misbehaving in any way it can detect. `_confine()` is what
makes that impossible rather than merely discouraged.

Run:  python3 tests/test_workspace.py
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile
import zipfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from basilisk_ext import workspace as W  # noqa: E402

_p = _f = 0


def ck(name: str, cond: bool, detail: str = "") -> None:
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


BASE = tempfile.mkdtemp(prefix="bz-ws-test-")
W.configure(BASE)
OUTSIDE = os.path.join(BASE, "OUTSIDE-CANARY.txt")


def _mkzip(path, entries, symlinks=(), dirs=()):
    with zipfile.ZipFile(path, "w") as zf:
        for d in dirs:
            zf.writestr(d if d.endswith("/") else d + "/", "")
        for name, body in entries:
            zf.writestr(name, body)
        for name, target in symlinks:
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, target)


GOOD = [
    ("repo/main.py", "def f():\n    return 1\n"),
    ("repo/util.py", "A = 1\nB = 2\n"),
    ("repo/README.md", "# demo\n"),
    ("repo/tests/test_a.py", "def test_x():\n    assert True\n"),
    ("repo/.env", "API_KEY=hunter2\n"),
    ("repo/package.json", '{"name":"demo"}\n'),
]


def fresh(name="demo", entries=GOOD, **kw):
    z = os.path.join(BASE, f"{name}.zip")
    _mkzip(z, entries, **kw)
    return W.import_zip(z, name), z


# ── 1. ZIP SLIP ──────────────────────────────────────────────────────
print("\n== zip slip ==")
_slip = list(GOOD) + [
    ("../../../../../../tmp/bz-slip-canary", "pwned\n"),
    ("repo/../../../bz-slip2", "pwned\n"),
    ("/tmp/bz-slip-abs", "pwned\n"),
    ("repo/ok/../../../../bz-slip3", "pwned\n"),
]
r, _ = fresh("slip", _slip)
ck("import still succeeds (good members survive)", r.get("ok"), str(r.get("error")))
ck("traversal members were refused",
   r.get("rejected_count", 0) >= 3, str(r.get("rejected")))
for canary in ("/tmp/bz-slip-canary", "/tmp/bz-slip-abs",
               os.path.join(BASE, "bz-slip2"),
               os.path.join(BASE, "bz-slip3")):
    ck(f"nothing written outside: {os.path.basename(canary)}",
       not os.path.exists(canary), canary)
ck("legitimate files still landed",
   r.get("files", 0) >= 5, str(r.get("files")))


# ── 2. SYMLINK ENTRIES ───────────────────────────────────────────────
# The subtle one. Rejecting ".." does NOT catch this: the member name is
# clean, and the escape happens later when something writes THROUGH the
# extracted link.
print("\n== symlink entries ==")
r, _ = fresh("link", GOOD, symlinks=[("repo/escape", "/tmp"),
                                     ("repo/sub/up", "../../../..")])
ck("symlink members refused",
   any("symlink" in x for x in r.get("rejected", [])), str(r.get("rejected")))
root = W.status()["root"]
ck("no symlink exists in the tree",
   not any(os.path.islink(os.path.join(dp, f))
           for dp, _dn, fs in os.walk(root) for f in fs))


# ── 3. ZIP BOMB ──────────────────────────────────────────────────────
print("\n== zip bomb ==")
bomb = os.path.join(BASE, "bomb.zip")
with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("repo/ok.py", "x = 1\n")
    zf.writestr("repo/huge.bin", b"\0" * (60 * 1024 * 1024))
rb = W.import_zip(bomb, "bomb")
ck("high-ratio member refused",
   any("ratio" in x for x in rb.get("rejected", [])), str(rb.get("rejected")))
ck("the rest of the archive still imported", rb.get("ok"), str(rb.get("error")))


# ── 4. _confine — the agent-mistake boundary ─────────────────────────
print("\n== path confinement ==")
fresh("main")
with open(OUTSIDE, "w", encoding="utf-8") as fh:
    fh.write("do not touch\n")

ESCAPES = [
    "../../../etc/passwd",
    "../OUTSIDE-CANARY.txt",
    "/etc/passwd",
    "/etc/../etc/passwd",
    "sub/../../../../etc/passwd",
    "./../../OUTSIDE-CANARY.txt",
    "~/.bashrc",
]
for bad in ESCAPES:
    for op, fn in (("read", lambda: W.read(bad)),
                   ("write", lambda: W.write(bad, "x\n", create=True)),
                   ("delete", lambda: W.delete(bad))):
        res = fn()
        ck(f"{op} refused: {bad[:30]}", not res.get("ok"),
           str(res)[:70])
ck("the canary outside the tree is untouched",
   open(OUTSIDE, encoding="utf-8").read() == "do not touch\n")

# startswith would pass this; commonpath must not. A sibling directory whose
# name merely BEGINS with the root's name is a different directory.
_root = W.status()["root"]
_sibling = _root + "-evil"
os.makedirs(_sibling, exist_ok=True)
with open(os.path.join(_sibling, "x.txt"), "w", encoding="utf-8") as fh:
    fh.write("nope\n")
ck("prefix-sibling directory is NOT inside the root (commonpath, not startswith)",
   not W.read(os.path.join(_sibling, "x.txt")).get("ok"))

# A symlink created INSIDE the tree pointing out of it must not be a door.
_link = os.path.join(_root, "backdoor")
try:
    os.symlink("/etc", _link)
    ck("symlink inside the tree does not grant escape",
       not W.read("backdoor/passwd").get("ok"))
except OSError:
    ck("symlink inside the tree does not grant escape (skipped: no symlink support)", True)


# ── 5. secrets ───────────────────────────────────────────────────────
print("\n== credential handling ==")
r, _ = fresh("sec")
ck("credential file flagged on import",
   ".env" in (r.get("possible_secrets") or []), str(r.get("possible_secrets")))
ck("credential file refused for reading", not W.read(".env").get("ok"))
ck("credential file excluded from search hits",
   all(h["path"] != ".env" for h in W.search("hunter2")["hits"]))
e = W.export_zip()
ck("credential file excluded from export",
   ".env" in (e.get("excluded_secrets") or []), str(e.get("excluded_secrets")))
with zipfile.ZipFile(e["zip"]) as zf:
    ck("and is genuinely absent from the zip bytes",
       ".env" not in zf.namelist(), str(zf.namelist()))
e2 = W.export_zip(include_secrets=True)
with zipfile.ZipFile(e2["zip"]) as zf:
    ck("include_secrets=True does include it", ".env" in zf.namelist())


# ── 6. edit semantics ────────────────────────────────────────────────
print("\n== edits ==")
fresh("edit")
ck("replace works", W.replace("main.py", "return 1", "return 42").get("ok"))
ck("edit landed", "return 42" in W.read("main.py")["content"])
ck("replace refuses a non-unique match",
   not W.replace("util.py", " = ", " := ").get("ok"))
ck("replace refuses a missing match",
   not W.replace("main.py", "nonexistent_text", "x").get("ok"))
_bad = W.write("main.py", "def broken(\n")
ck("python syntax error refused", not _bad.get("ok") and _bad.get("syntax_error"))
ck("and the file was NOT damaged", "return 42" in W.read("main.py")["content"])
ck("non-python is not syntax-checked",
   W.write("README.md", "# still fine (\n").get("ok"))
ck("writing a new file needs create=True",
   not W.write("brand_new.py", "x = 1\n").get("ok"))
ck("create=True works", W.write("brand_new.py", "x = 1\n", create=True).get("ok"))


# ── 7. diff / revert ─────────────────────────────────────────────────
# The property that matters: the ORIGINAL is what came out of the zip, not
# the state before the most recent edit. Stashing on every write instead of
# once per file would make revert walk back exactly one step and stop.
print("\n== diff and revert ==")
d = W.diff()
ck("diff reports the changed files", d["changed"] >= 2, str(d["changed"]))
ck("diff text is a real unified diff", "@@" in d["diff"] or "---" in d["diff"])
W.replace("main.py", "return 42", "return 99")
W.replace("main.py", "return 99", "return 123")
ck("multi-edit file still tracked once",
   W.status()["modified"].count("main.py") == 1)
rv = W.revert()
ck("revert reports what it undid", rv["count"] >= 2, str(rv))
ck("revert restores the ORIGINAL zip content, not the previous edit",
   "return 1" in W.read("main.py")["content"],
   W.read("main.py")["content"][:40])
ck("revert removes a created file",
   not W.read("brand_new.py").get("ok"))
ck("workspace is clean again", not W.status()["dirty"])

# delete is recoverable too
W.delete("util.py")
ck("delete removes the file", not W.read("util.py").get("ok"))
W.revert()
ck("revert brings a deleted file back", W.read("util.py").get("ok"))


# ── 8. orientation ───────────────────────────────────────────────────
print("\n== orientation ==")
fresh("orient")
ov = W.overview()
ck("overview detects python", ov["languages"].get("python", 0) >= 3,
   str(ov["languages"]))
ck("overview finds the manifest", "package.json" in ov["manifests"],
   str(ov["manifests"]))
ck("overview finds the tests", ov["test_count"] >= 1, str(ov["test_count"]))
ck("overview counts lines", ov["lines_of_code"].get("python", 0) > 0)
srch = W.search("return")
ck("search finds a known string", srch["count"] >= 1, str(srch))
ck("search glob filters", W.search("A", glob="*.md")["count"] == 0)
ck("search regex mode", W.search(r"def\s+\w+", regex=True)["count"] >= 1)
ck("bad regex is reported, not raised",
   not W.search("(unclosed", regex=True).get("ok"))
ck("tree filters build noise",
   all("__pycache__" not in f for f in W.tree()["files"]))


# ── 9. top-level directory hoist ─────────────────────────────────────
# GitHub zips wrap everything in "<repo>-main/". Without hoisting, every
# path the operator types is wrong by one prefix.
print("\n== top-dir hoist ==")
fresh("hoist")
ck("wrapping directory stripped — paths match GitHub",
   W.read("main.py").get("ok"))
ck("nested paths survive the hoist", W.read("tests/test_a.py").get("ok"))
_flat = [("a.py", "x = 1\n"), ("b.py", "y = 2\n")]
r, _ = fresh("flat", _flat)
ck("an already-flat zip is not mangled", W.read("a.py").get("ok"))


# ── 10. no workspace open ────────────────────────────────────────────
print("\n== closed state ==")
W.close(discard=True)
ck("status reports closed", not W.status()["open"])
for op, fn in (("read", lambda: W.read("x.py")),
               ("write", lambda: W.write("x.py", "y\n", create=True)),
               ("search", lambda: W.search("x")),
               ("export", lambda: W.export_zip()),
               ("diff", lambda: W.diff())):
    ck(f"{op} refuses with no workspace open", not fn().get("ok"))

ck("junk path to import is refused",
   not W.import_zip("/nonexistent/nope.zip").get("ok"))
_notzip = os.path.join(BASE, "notazip.zip")
with open(_notzip, "w", encoding="utf-8") as fh:
    fh.write("this is not a zip\n")
ck("a non-zip file is refused", not W.import_zip(_notzip).get("ok"))

ck("the canary is STILL untouched after every test",
   os.path.exists(OUTSIDE)
   and open(OUTSIDE, encoding="utf-8").read() == "do not touch\n")


# ── 10b. THE VERIFY LOOP ─────────────────────────────────────────────
# This is what turns "edits code" into "fixes code", and the property that
# carries it is `broke`: counts alone cannot distinguish "fixed one, broke
# another" from "nothing changed" -- both read as 3 failed.
print("\n== verify loop ==")
_ZV = os.path.join(BASE, "verify.zip")
_mkzip(_ZV, [
    ("repo/pyproject.toml", '[project]\nname = "d"\n'),
    ("repo/Makefile", "test:\n\tpytest -q\n"),
    ("repo/src/a.py", "def add(a, b):\n    return a - b\n"),
    ("repo/tests/test_a.py", "def test_add():\n    assert True\n"),
])
W.import_zip(_ZV, "verify")

_det = W.detect_test_command()
ck("test runner detected", bool(_det.get("command")), str(_det))
ck("Makefile with a real test: target wins", _det["command"] == "make test",
   _det["command"])
ck("detection reports what it inferred from",
   _det["candidates"][0]["from"] == "Makefile")

BASE_LOG = ("FAILED tests/test_a.py::test_add - assert -1 == 3\n"
            "FAILED tests/test_b.py::test_z\n1 passed, 2 failed")
_bl = W.record_baseline(BASE_LOG, 1, "pytest -q")
ck("baseline captures failing NAMES, not just counts",
   set(_bl["already_failing"]) == {"tests/test_a.py::test_add",
                                   "tests/test_b.py::test_z"},
   str(_bl["already_failing"]))
ck("baseline warns that tests were already red", "note" in _bl)

_c = W.compare_to_baseline("FAILED tests/test_b.py::test_z\n2 passed, 1 failed", 1)
ck("progress verdict", _c["verdict"] == "progress", _c["verdict"])
ck("fixed set is right", _c["fixed"] == ["tests/test_a.py::test_add"])
ck("still_failing set is right", _c["still_failing"] == ["tests/test_b.py::test_z"])
ck("nothing falsely reported as broken", _c["broke"] == [])

# The case counts cannot see: one fixed, one broken. Same "2 failed" total
# as the baseline, so a count-only comparison would call this no-change.
_c2 = W.compare_to_baseline(
    "FAILED tests/test_a.py::test_add\nFAILED tests/test_c.py::test_new\n"
    "1 passed, 2 failed", 1)
ck("REGRESSION detected even though the failure COUNT is unchanged",
   _c2["verdict"] == "regression", _c2["verdict"])
ck("the newly-broken test is named", _c2["broke"] == ["tests/test_c.py::test_new"],
   str(_c2["broke"]))
ck("regression action says do not export",
   "DO NOT EXPORT" in _c2["action"].upper(), _c2["action"][:60])

_c3 = W.compare_to_baseline("5 passed", 0)
ck("green verdict", _c3["verdict"] == "green" and _c3["green"])
ck("green run reports the pre-existing tests it also fixed",
   len(_c3["fixed"]) == 2, str(_c3["fixed"]))

# The dangerous default: an unknown runner we cannot parse. Treating
# "unparseable" as "passed" would be the worst possible failure mode.
_c4 = W.compare_to_baseline("gibberish from some unknown runner", 1)
ck("unparseable output with rc!=0 is NOT green", not _c4["green"])
ck("and it says so rather than pretending", bool(_c4.get("parse_warning")))
_c5 = W.compare_to_baseline("", 1)
ck("empty output with rc!=0 is NOT green", not _c5["green"])

# No baseline at all must not silently produce a confident verdict.
W.close(discard=True)
W.import_zip(_ZV, "verify2")
_nb = W.compare_to_baseline("FAILED x\n1 failed", 1)
ck("no baseline => refuses to attribute", _nb.get("no_baseline") is True)
ck("and warns explicitly", "warning" in _nb)

# A baseline belongs to exactly one repo. Carrying one across an import
# would mark every name in repo B as broken and every name in A as fixed.
W.record_baseline("FAILED old_repo_test\n1 failed", 1, "x")
W.import_zip(_ZV, "verify3")
ck("importing a new repo clears the baseline",
   not W.baseline_status()["have_baseline"])
W.record_baseline("FAILED t\n1 failed", 1, "x")
W.close(discard=True)
ck("closing clears the baseline", not W.baseline_status()["have_baseline"])

# Baseline taken after edits is not a baseline; it must say so.
W.import_zip(_ZV, "verify4")
W.replace("src/a.py", "a - b", "a + b")
_dirty = W.record_baseline("1 passed", 0, "x")
ck("baseline taken on a dirty tree warns", "warning" in _dirty, str(_dirty)[:80])


# ── 10c. STATIC HEALTH SWEEP ─────────────────────────────────────────
print("\n== health sweep ==")
W.close(discard=True)
_ZH = os.path.join(BASE, "health.zip")
_mkzip(_ZH, [
    ("repo/bad.py",
     "import subprocess\n"
     "def f(x=[]):\n"
     "    try:\n"
     "        subprocess.run('ls')\n"
     "    except:\n"
     "        pass\n"
     "    if x is 'a':\n"
     "        return 1\n"),
    ("repo/good.py", "def g(x=None):\n    return x\n"),
])
W.import_zip(_ZH, "health")
_h = W.health()
_kinds = {i["kind"] for i in _h["issues"]}
for k in ("mutable-default", "bare-except", "subprocess-no-timeout",
          "is-with-literal"):
    ck(f"health finds {k}", k in _kinds, str(_kinds))
ck("clean file produces no findings",
   all(i["path"] != "good.py" for i in _h["issues"]),
   str([i["path"] for i in _h["issues"]]))
ck("findings carry a line number",
   all(isinstance(i.get("line"), int) for i in _h["issues"]))
ck("high severity sorts first", _h["issues"][0]["severity"] == "high",
   str(_h["issues"][0]))
W.close(discard=True)


# ── 10d. CONCURRENCY ─────────────────────────────────────────────────
# Tool calls run on worker threads. _stash_original() was check-then-act
# ("if the original exists, return", then copy) and shutil.copy2 releases
# the GIL during I/O -- so two threads editing the same file could BOTH
# pass the check, and the second would stash the ALREADY-EDITED content as
# the "original". revert() then restores a modified file and the true
# baseline is gone silently. That is the worst bug this module could have:
# the undo button is precisely what the operator reaches for when something
# has already gone wrong.
#
# Same shape as the engage.py loot race fixed in v7.9.1, which also did not
# look reproducible until it was measured (120 concurrent records landed 1
# of 60). Asserted here rather than argued about.
print("\n== concurrency ==")
import threading as _th  # noqa: E402

_ZC = os.path.join(BASE, "conc.zip")
_mkzip(_ZC, [("repo/s.py", "ORIGINAL = 0\n")])
_clean = 0
_TRIALS = 6
for _t in range(_TRIALS):
    W.close(discard=True)
    W.import_zip(_ZC, f"conc{_t}")
    _bar = _th.Barrier(16)

    def _worker(i):
        _bar.wait()
        W.write("s.py", f"ORIGINAL = {i + 1}\n")

    _threads = [_th.Thread(target=_worker, args=(i,)) for i in range(16)]
    for _th_ in _threads:
        _th_.start()
    for _th_ in _threads:
        _th_.join()
    _st = W.status()
    _dup = len(_st["modified"]) != len(set(_st["modified"]))
    W.revert()
    _got = W.read("s.py")["content"].strip()
    if not _dup and _got == "ORIGINAL = 0":
        _clean += 1
ck(f"16-way concurrent writes: revert still restores the TRUE original "
   f"({_clean}/{_TRIALS} trials)", _clean == _TRIALS, f"{_clean}/{_TRIALS}")

# A bare acquire/release around revert would wedge the module forever if
# anything raised in between -- strictly worse than the race it fixes.
W.close(discard=True)
W.revert()                      # error path: no workspace open
W.import_zip(_ZC, "after-error")
ck("module is still responsive after an error inside a locked section",
   W.write("s.py", "ORIGINAL = 9\n").get("ok"))
W.close(discard=True)


# ── 11. WIRING PARITY ────────────────────────────────────────────────
# basilisk.py has TWO dispatch paths (autonomous, and approval-gated) and
# they have drifted before: a tool wired into one and not the other works
# perfectly until the operator flips approval mode, then vanishes with no
# error. Assert all four registries agree.
print("\n== wiring parity ==")
import re as _re  # noqa: E402

_src = open(os.path.join(_ROOT, "basilisk.py"), encoding="utf-8").read()
_table = set(_re.findall(r'"(workspace_[a-z_]+)":\s+lambda a:', _src))
_mapper = set(_re.findall(r'if n == "(workspace_[a-z_]+)"', _src))

import basilisk_persona as _P  # noqa: E402
_spec = set(_re.findall(r'<tool name="(workspace_[a-z_]+)">',
                        _P.SPECIALIST_GROUPS.get("workspace", "")))
import basilisk_core as _C  # noqa: E402
_core = {n[len("tool_"):] for n in dir(_C)
         if n.startswith("tool_workspace_")}

ck("persona advertises every workspace tool", len(_spec) == 17, str(len(_spec)))
ck("core implements exactly what persona advertises", _spec == _core,
   str(_spec ^ _core))
ck("approval-gated dispatch table matches", _spec == _table, str(_spec ^ _table))
ck("shared arg-mapper covers every tool", _spec <= _mapper, str(_spec - _mapper))
ck("autonomous path routes workspace_* to the shared mapper",
   'if n.startswith("workspace_"):' in _src)
ck("workspace group is reachable by alias",
   _P.load_tools_group("repo").get("group") == "workspace")
ck("workspace.py is in install.sh EXT_FILES",
   "workspace.py" in open(os.path.join(_ROOT, "install.sh"),
                          encoding="utf-8").read())

shutil.rmtree(BASE, ignore_errors=True)
print(f"\nworkspace: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
