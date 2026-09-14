#!/usr/bin/env python3
"""
test_repotools.py — the repo tools a real coding agent needs.

WHAT WAS MISSING, AND WHAT IT LOOKED LIKE
=========================================
"make it able to run whole repo work just like claude does ... stuff long
code and all that so it doesnt keep failing."

write() and replace() are enough to edit a file and not enough to work a
repo. Three ceilings, one symptom:

  1. ONE EDIT PER ROUND-TRIP — a rename across nine call sites was nine
     model turns, each a chance to hit the step budget or half-apply a
     change and leave the file unparseable.
  2. A FILE HAD TO FIT IN ONE REPLY — write() takes the whole file, so the
     biggest file the agent could create was bounded by max_tokens. Past
     that the reply is cut off mid-function and the write lands truncated
     or is refused. The v1.1.4.0 truncation guard catches the damage and
     left no route to the file at all: half a fix.
  3. NO WAY TO FIND FILES BY SHAPE — search() greps content; nothing
     matched paths.

THE ONE THAT MATTERS MOST HERE IS ATOMICITY. Applying four of six edits and
reporting a failure leaves the file in a state nobody designed and the
model holding a stale picture of it — strictly worse than refusing, because
the next edit is then computed against fiction.

Run:  python3 tests/test_repotools.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

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


from basilisk_ext import workspace as W                         # noqa: E402

APP = '''def greet(name):
    return "hi " + name


def farewell(name):
    return "bye " + name


def main():
    print(greet("a"))
    print(farewell("b"))
'''

_TMP = tempfile.mkdtemp(prefix="repotools-")
_SRC = os.path.join(_TMP, "proj")
os.makedirs(os.path.join(_SRC, "src"))
os.makedirs(os.path.join(_SRC, "tests"))
open(os.path.join(_SRC, "src", "app.py"), "w").write(APP)
open(os.path.join(_SRC, "tests", "test_app.py"), "w").write(
    "from src.app import greet\n\n\ndef test_greet():\n"
    "    assert greet('x') == 'hi x'\n")
open(os.path.join(_SRC, "README.md"), "w").write("# demo\n")

W.configure(tempfile.mkdtemp(prefix="repotools-ws-"))
_imp = W.import_dir(_SRC, "demo")
assert _imp.get("ok"), _imp


def body(path="src/app.py"):
    r = W.read(path, 1, 0)
    return r.get("content", "")


def reset():
    W.revert("")
    return body()


# ═════════════════════════════════════════════════════════════════════
#  MULTI-EDIT
# ═════════════════════════════════════════════════════════════════════
print("\n== many edits, one call ==")
r = W.edits("src/app.py", [
    {"old": 'return "hi " + name', "new": 'return f"hi {name}"'},
    {"old": 'return "bye " + name', "new": 'return f"bye {name}"'},
    {"old": 'print(greet("a"))', "new": 'print(greet("world"))'},
])
ck("three edits applied in one call", r.get("ok") and r["edits_applied"] == 3,
   str(r)[:120])
ck("…all three really landed",
   'f"hi {name}"' in body() and 'f"bye {name}"' in body()
   and 'greet("world")' in body())
ck("a diff comes back", bool(r.get("diff")))
ck("line counts before and after are reported",
   "lines_before" in r and "lines_after" in r)

print("\n== edits apply IN ORDER, each to the result of the last ==")
reset()
r = W.edits("src/app.py", [
    {"old": "def greet(", "new": "def hello("},
    {"old": "def hello(", "new": "def hi("},
])
ck("a later edit may target what an earlier one produced", r.get("ok"))
ck("…and the last one wins", "def hi(" in body())

print("\n== ATOMICITY: all or nothing ==")
before = reset()
r = W.edits("src/app.py", [
    {"old": "def farewell", "new": "def goodbye"},
    {"old": "THIS TEXT DOES NOT EXIST ANYWHERE", "new": "x"},
])
ck("a missing anchor refuses the whole call", not r.get("ok"))
ck("…names WHICH edit failed", r.get("failed_edit") == 2)
ck("…reports that nothing was applied", r.get("applied") == 0)
ck("…and the file is byte-identical", body() == before)
ck("…the message says so plainly, so the model does not re-read to check",
   "NOTHING was written" in r.get("error", ""))

r = W.edits("src/app.py", [{"old": "name", "new": "n"}])
ck("an AMBIGUOUS anchor refuses rather than picking one", not r.get("ok"))
ck("…and says how many times it appears", r.get("occurrences", 0) > 1)
ck("…and the file is untouched", body() == before)

r = W.edits("src/app.py", [{"old": "def main():", "new": "def main(:"}])
ck("the SYNTAX GATE still applies to a multi-edit", not r.get("ok"))
ck("…flagged as a syntax error", r.get("syntax_error"))
ck("…and the file is untouched", body() == before)
ck("…the message says nothing was written",
   "NOTHING was written" in r.get("error", ""))

print("\n== multi-edit refuses nonsense without crashing ==")
for junk, why in ((None, "None"), ([], "empty list"), ("", "empty string"),
                  ([{"new": "x"}], "no old text"),
                  (["not a dict"], "not an object"),
                  ([{"old": "", "new": "x"}], "empty anchor"),
                  ([{"old": "x"}] * 200, "too many")):
    out = W.edits("src/app.py", junk)
    ck(f"{why} is refused cleanly",
       isinstance(out, dict) and not out.get("ok"), str(out)[:70])
ck("…and the file survived all of it", body() == before)
ck("an unknown path is refused", not W.edits("nope.py", [{"old": "a",
                                                          "new": "b"}]
                                             ).get("ok"))
ck("confinement holds for multi-edit too",
   not W.edits("../escape.py", [{"old": "a", "new": "b"}]).get("ok"))


# ═════════════════════════════════════════════════════════════════════
#  APPEND — the long-file protocol
# ═════════════════════════════════════════════════════════════════════
print("\n== a long file, built in chunks ==")
a = W.append("src/big.py", "def part1():\n    return 1\n", create=True)
ck("the first chunk creates the file", a.get("ok") and a.get("created"))
a = W.append("src/big.py", "\n\ndef part2():\n    return 2\n")
ck("a later chunk appends", a.get("ok") and not a.get("created"))
ck("…and the running total is reported", a.get("total_lines", 0) >= 5)
ck("the whole file is there",
   "part1" in body("src/big.py") and "part2" in body("src/big.py"))
ck("appending to a MISSING file without create is refused",
   not W.append("src/never.py", "x").get("ok"))
ck("…and the refusal explains the protocol",
   "FIRST chunk" in W.append("src/never2.py", "x").get("error", ""))

print("\n== a chunk is NOT syntax-gated, on purpose ==")
# A half-written Python file does not parse. Refusing it would make the
# protocol unable to get past its own first chunk.
a = W.append("src/partial.py", "def f():\n    x = (\n", create=True)
ck("an unparseable chunk is accepted", a.get("ok"))
ck("…but it is REPORTED, not hidden", a.get("parses") is False)
ck("…with a note saying it must parse by the end",
   "does not parse YET" in (a.get("note") or ""))
a = W.append("src/partial.py", "        1,\n    )\n    return x\n")
ck("closing the file makes it parse again", a.get("parses") is True)
ck("…and the note is gone", not a.get("note"))

print("\n== the mid-line join, which silently merges two lines of code ==")
W.append("src/join.py", "x = 1", create=True)         # no trailing newline
j = W.append("src/join.py", "y = 2")
ck("the join is detected", j.get("joined_mid_line") is True)
ck("…and warned about", "did not end in a newline" in (j.get("warning") or ""))
k = W.append("src/join.py", "\nz = 3\n")
ck("a chunk that starts with a newline is not flagged",
   not k.get("joined_mid_line"))

print("\n== append is bounded and confined ==")
ck("confinement holds", not W.append("../out.py", "x", create=True).get("ok"))
ck("a non-python file needs no parse verdict",
   W.append("README.md", "\nmore\n").get("parses") is True)


# ═════════════════════════════════════════════════════════════════════
#  INSERT
# ═════════════════════════════════════════════════════════════════════
print("\n== insert at a position ==")
reset()
i = W.insert("src/app.py", "import os", after_line=0)
ck("after_line 0 puts it at the very top", i.get("ok")
   and body().startswith("import os"))
ck("…and reports where", i.get("inserted_at_line") == 1)
n_before = len(body().splitlines())
i = W.insert("src/app.py", "# a comment", after_line=2)
ck("insert after a line works", i.get("ok"))
ck("…the file grew by exactly one line",
   len(body().splitlines()) == n_before + 1)
ck("before_line works too",
   W.insert("src/app.py", "# top", before_line=1).get("ok"))
ck("passing BOTH is refused rather than guessed",
   not W.insert("src/app.py", "x", after_line=2, before_line=4).get("ok"))
i = W.insert("src/app.py", "x = 1", after_line=99999)
ck("a line past the end is refused", not i.get("ok"))
ck("…and it points at the right tool instead",
   "workspace_append" in i.get("error", ""))
ck("an insert that breaks the syntax is refused",
   not W.insert("src/app.py", "def broken(:", after_line=1).get("ok"))
ck("an unknown file is refused",
   not W.insert("nope.py", "x", after_line=1).get("ok"))


# ═════════════════════════════════════════════════════════════════════
#  GLOB + READ_MANY
# ═════════════════════════════════════════════════════════════════════
print("\n== find files by name ==")
g = W.glob_files("**/*.py")
paths = [x["path"] for x in g["files"]]
ck("recursive glob finds nested files", "src/app.py" in paths, str(paths))
ck("…and test files", "tests/test_app.py" in paths)
ck("a count comes back", g["count"] == len(paths) or g.get("truncated"))
g2 = W.glob_files("tests/*.py")
ck("a directory-scoped pattern works",
   [x["path"] for x in g2["files"]] == ["tests/test_app.py"])
g3 = W.glob_files("*.py")
ck("a non-recursive pattern matches only the root", g3["count"] == 0)
ck("…and SAYS that ** is what recurses",
   "**/" in (g3.get("note") or ""))
ck("a bad pattern is refused, not crashed",
   isinstance(W.glob_files("["), dict))
ck("the limit is honoured", len(W.glob_files("**/*", limit=1)["files"]) == 1)
ck("…and truncation is flagged",
   W.glob_files("**/*", limit=1).get("truncated") is True)

print("\n== read several files in one round-trip ==")
m = W.read_many(["src/app.py", "tests/test_app.py", "nope.py"])
ck("the readable ones came back", m["read"] == 2)
ck("…and the count of what was asked for", m["requested"] == 3)
ck("content is real, not an empty string from a key-shape mistake",
   any("def greet" in (x.get("content") or "")
       for x in m["files"] if x.get("ok")),
   str([list(x) for x in m["files"]])[:160])
ck("the missing one is reported per-file, not fatal",
   any(not x["ok"] for x in m["files"]))
ck("a comma string is accepted as well as a list",
   W.read_many("src/app.py,README.md")["read"] == 2)
ck("too many files at once is refused",
   not W.read_many([f"f{i}.py" for i in range(40)]).get("ok"))
ck("no paths is refused", not W.read_many([]).get("ok"))
# Against a file that is ACTUALLY longer than the cap. An earlier draft
# asserted this on src/app.py, which is ~180 chars — shorter than the 200
# floor, so `truncated` was correctly False and the checker was wrong, not
# the code. Validate the fixture before trusting the verdict.
W.append("src/long.py", "# filler\n" * 400, create=True)
_long = W.read_many(["src/long.py"], max_chars=300)["files"][0]
ck("the fixture really is longer than the cap",
   len(body("src/long.py")) > 300)
ck("per-file truncation is reported", _long["truncated"] is True)
ck("…and the content really is cut to the cap", len(_long["content"]) == 300)
# A FLOOR THAT ANNOUNCES ITSELF. max_chars=10 is not a useful read, so it is
# raised — but silently raising it means the caller's number was ignored and
# nothing said which one applied.
_m = W.read_many(["src/app.py"], max_chars=10)
ck("an unusably small max_chars is clamped", _m["chars_per_file"] == 200)
ck("…and the clamp is REPORTED, not silent",
   "clamped to 200" in _m.get("max_chars_note", ""))
ck("a sane max_chars is used as given",
   W.read_many(["src/app.py"], max_chars=5000)["chars_per_file"] == 5000)
ck("…and reports no clamp note",
   "max_chars_note" not in W.read_many(["src/app.py"], max_chars=5000))


# ═════════════════════════════════════════════════════════════════════
#  RUN IN THE REPO
# ═════════════════════════════════════════════════════════════════════
print("\n== commands run in the repo, not in $HOME ==")
ck("the root is exposed to the host", bool(W.repo_root()))
ck("…and it is the open workspace", os.path.isdir(W.repo_root()))
ck("…containing the repo's files",
   os.path.isfile(os.path.join(W.repo_root(), "src", "app.py")))
BSRC = open(os.path.join(_ROOT, "basilisk.py"), encoding="utf-8").read()
ck("the host passes it as cwd to run", "cwd=_cwd" in BSRC)
ck("…and the reason is written down (a guessed `cd` runs somewhere "
   "nobody intended)", "guessed cd" in BSRC or "guessed `cd`" in BSRC)
ck("with no workspace open it is empty, not a stray path",
   isinstance(W.repo_root(), str))


# ═════════════════════════════════════════════════════════════════════
#  WIRING PARITY — the drift this codebase keeps paying for
# ═════════════════════════════════════════════════════════════════════
print("\n== every new tool is wired on every path ==")
import re                                                       # noqa: E402
import basilisk_core as Bc                                      # noqa: E402
import basilisk_persona as Bp                                   # noqa: E402

NEW = ["workspace_edits", "workspace_append", "workspace_insert",
       "workspace_glob", "workspace_read_many"]
_table = set(re.findall(r'"(workspace_[a-z_]+)":\s+lambda a:', BSRC))
_mapper = set(re.findall(r'if n == "(workspace_[a-z_]+)"', BSRC))
_spec = set(re.findall(r'<tool name="(workspace_[a-z_]+)">',
                       Bp.SPECIALIST_GROUPS.get("workspace", "")))
for n in NEW:
    ck(f"{n}: implemented in core", hasattr(Bc, "tool_" + n))
    ck(f"{n}: in the dispatch table", n in _table)
    ck(f"{n}: in the shared arg-mapper", n in _mapper)
    ck(f"{n}: advertised in the persona", n in _spec)

print("\n== the long-file protocol is TAUGHT, not just available ==")
_ws = Bp.SPECIALIST_GROUPS.get("workspace", "")
ck("the persona says append is how to write a long file",
   "HOW YOU WRITE A LONG FILE" in _ws)
ck("…and names the failure it avoids (cut off at the token cap)",
   "token cap" in _ws)
ck("…and gives the create-then-append sequence",
   '"create": true' in _ws and "append each following chunk" in _ws)
ck("multi-edit is presented as the default for a multi-site change",
   "ALL-OR-NOTHING" in _ws)
ck("…and explicitly discourages nine turns for a nine-site rename",
   "nine call sites" in _ws)
ck("the method block tells it not to emit a huge file in one reply",
   "LONG FILES" in _ws)
ck("…and that a truncation placeholder is a wasted turn, not a shortcut",
   "rest unchanged" in _ws and "wasted turn" in _ws)
ck("the run-cwd fact is stated so it stops prefixing `cd`",
   "working directory" in _ws and "do NOT prefix commands" in _ws)

print("\n== the repo tools ship WITH the repo, not after a round-trip ==")
ck("preload_groups exists", "preload_groups" in Bp.build_system_prompt.__doc__
   or "preload_groups" in open(os.path.join(_ROOT, "basilisk_persona.py"),
                               encoding="utf-8").read())
_pre = Bp.build_system_prompt(grouped=True, unleashed=False,
                              preload_groups=("workspace",))
_base = Bp.build_system_prompt(grouped=True, unleashed=False)
ck("the base prompt does NOT inline the workspace specs",
   '<tool name="workspace_edits">' not in _base)
ck("…and the preloaded one DOES",
   '<tool name="workspace_edits">' in _pre)
ck("the host preloads it when a repo is open",
   "def _preload_groups" in BSRC and 'out.append("workspace")' in BSRC)
ck("…and on a leashed WORK turn even before one is imported",
   "_leash_work_turn" in BSRC.split("def _preload_groups")[1][:600])

shutil.rmtree(_TMP, ignore_errors=True)
print(f"\nrepotools: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
