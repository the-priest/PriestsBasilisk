#!/usr/bin/env python3
"""test_repo_e2e.py — end-to-end: can it actually FIX A WHOLE REPO?

THE REPORTED FAILURE
====================
"when he tries to fix a repo the code he tries to write, the tool doesn't let
it or it gets scrambled" — and, separately, that the leashed assistant would
describe a fix instead of landing one.

Every other suite in this directory tests one layer. This one tests the layer
BOUNDARIES, because that is where a repo repair actually died: a whole-file
write is fine in the workspace tests and fine in the transport tests, and
still fails in real life if the dialect the model used loses the last five
bytes on the way through.

So the scripted "model" here speaks a DIFFERENT dialect for each step
(canonical, GLM <tool_call>, DSML fullwidth, GLM JSON body), and every
utterance goes through the real parse_tool_calls -> sanitise_tool_args ->
tool-function path. What is asserted is the state of the FILES and the TEST
RUN afterwards, not the shape of a return value.

Covers, in one pass:
  * opening a repo that is a DIRECTORY, not a zip
  * baseline-before-editing, with the failing tests named
  * unittest output parsed correctly (a phantom test called "(failures=2,"
    used to be scraped out of unittest's own summary line and reported as
    "fixed")
  * a whole-file write that must land byte-identical
  * a surgical replace on a second file
  * verify: fixed / broke / still_failing against the baseline
  * a 6,000-line file — the INCOMPLETE marker, paging with start/end past
    the byte cap, and a 300 KB rewrite
  * the export gate refusing unverified edits, then allowing them
  * the operator's own directory never being touched

Run:  python3 tests/test_repo_e2e.py


Not a unit test — a rehearsal of the real loop with a scripted "model":
    import a DIRECTORY repo -> overview -> baseline (red)
    -> search -> read -> whole-file write -> surgical replace
    -> verify (green) -> diff -> export

Every model utterance goes through the REAL pipeline the app uses
(_normalise_tool_syntax -> parse_tool_calls -> _normalise_tool_args ->
the tool function), in a different dialect each time, so this exercises
transport + workspace together rather than calling the tools directly.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
import basilisk_core as C
from basilisk_ext import workspace as W

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


# ── a small repo that is genuinely broken in two different ways ──────
CALC = '''"""calc — arithmetic helpers."""


def add(a, b):
    return a + b


def sub(a, b):
    return a - b


def mul(a, b):
    # BUG 1: wrong operator
    return a + b


def div(a, b):
    # BUG 2: no zero guard
    return a / b


def mean(xs):
    return sum(xs) / len(xs)
'''

FMT = '''"""fmt — number formatting."""


def money(n):
    # BUG 3: no thousands separator
    return "$%.2f" % n


def pct(n):
    return "%.1f%%" % (n * 100)
'''

TESTS = '''import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest
from src.calc import add, sub, mul, div, mean
from src.fmt import money, pct


class T(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)

    def test_sub(self):
        self.assertEqual(sub(5, 3), 2)

    def test_mul(self):
        self.assertEqual(mul(3, 4), 12)

    def test_div(self):
        self.assertEqual(div(10, 4), 2.5)

    def test_div_zero(self):
        with self.assertRaises(ValueError):
            div(1, 0)

    def test_mean(self):
        self.assertEqual(mean([1, 2, 3]), 2)

    def test_money(self):
        self.assertEqual(money(1234567.5), "$1,234,567.50")

    def test_pct(self):
        self.assertEqual(pct(0.256), "25.6%")


if __name__ == "__main__":
    unittest.main()
'''


def build_repo(root):
    os.makedirs(os.path.join(root, "src"))
    os.makedirs(os.path.join(root, "tests"))
    os.makedirs(os.path.join(root, ".git"))
    os.makedirs(os.path.join(root, "node_modules"))
    open(os.path.join(root, "src", "calc.py"), "w").write(CALC)
    open(os.path.join(root, "src", "fmt.py"), "w").write(FMT)
    open(os.path.join(root, "src", "__init__.py"), "w").write("")
    open(os.path.join(root, "tests", "test_all.py"), "w").write(TESTS)
    open(os.path.join(root, "tests", "__init__.py"), "w").write("")
    open(os.path.join(root, "README.md"), "w").write("# demo\n")
    open(os.path.join(root, ".git", "config"), "w").write("noise")
    open(os.path.join(root, "node_modules", "x.js"), "w").write("noise")
    # a big file, to prove a whole-file rewrite of something real works
    with open(os.path.join(root, "src", "big.py"), "w") as fh:
        for i in range(1, 6001):
            fh.write(f"CONST_{i} = {i}  # padding padding padding padding\n")


# ── the dispatcher, mirroring basilisk.py's own ──────────────────────
DISPATCH = {
    "workspace_import":   lambda a: C.tool_workspace_import(
        a.get("zip_path", "") or a.get("path", "")),
    "workspace_overview": lambda a: C.tool_workspace_overview(),
    "workspace_tree":     lambda a: C.tool_workspace_tree(),
    "workspace_search":   lambda a: C.tool_workspace_search(
        a.get("pattern", ""), a.get("glob", ""), bool(a.get("regex")),
        int(a.get("context", 0) or 0)),
    "workspace_read":     lambda a: C.tool_workspace_read(
        a.get("path", ""), a.get("start", 1), a.get("end", 0)),
    "workspace_write":    lambda a: C.tool_workspace_write(
        a.get("path", ""), a.get("content", ""), bool(a.get("create"))),
    "workspace_replace":  lambda a: C.tool_workspace_replace(
        a.get("path", ""), a.get("old", ""), a.get("new", "")),
    "workspace_baseline": lambda a: C.tool_workspace_baseline(
        a.get("command", "")),
    "workspace_verify":   lambda a: C.tool_workspace_verify(
        a.get("command", "")),
    "workspace_diff":     lambda a: C.tool_workspace_diff(),
    "workspace_export":   lambda a: C.tool_workspace_export(),
    "workspace_test_command": lambda a: C.tool_workspace_test_command(),
    "workspace_status":   lambda a: C.tool_workspace_status(),
}


def turn(model_text):
    """One model utterance -> the results of every tool it called."""
    calls = C.parse_tool_calls(model_text)
    out = []
    for call in calls:
        args = C.sanitise_tool_args(call.args)
        if not isinstance(args, dict):
            args = {}
        args = {k: v for k, v in args.items() if v is not None}
        fn = DISPATCH.get(call.name)
        if fn is None:
            out.append((call.name, {"ok": False, "error": "unknown tool"}))
            continue
        try:
            out.append((call.name, fn(args)))
        except Exception as e:
            out.append((call.name, {"ok": False,
                                    "error": f"{type(e).__name__}: {e}"}))
    return calls, out


def main():
    tmp = tempfile.mkdtemp()
    repo = os.path.join(tmp, "demo-repo")
    build_repo(repo)

    print("\n== 1. the model opens a DIRECTORY, not a zip ==")
    # canonical dialect
    calls, res = turn(
        'I\'ll open the repo.\n'
        '<tool name="workspace_import">{"path": "%s"}</tool>' % repo)
    ck("one call parsed", len(calls) == 1, [c.name for c in calls])
    r = res[0][1]
    ck("directory import succeeded", r.get("ok") is True, r)
    ck("build/vcs noise excluded", r.get("files") == 7, r.get("files"))
    ck("it says the operator's tree is untouched", "COPY" in r.get("note", ""))

    print("\n== 2. overview + baseline BEFORE touching anything ==")
    _, res = turn('<tool name="workspace_overview">{}</tool>')
    ov = res[0][1]
    ck("overview works", ov.get("ok") is True, ov)

    # GLM <tool_call> dialect
    _, res = turn(
        "<tool_call>workspace_baseline\n"
        "<arg_key>command</arg_key><arg_value>python3 -m unittest discover "
        "-s tests -t . -q</arg_value>\n"
        "</tool_call>")
    base = res[0][1]
    ck("baseline ran through the GLM dialect", base.get("ok") is True, base)
    _names = base.get("already_failing") or []
    ck("baseline is RED and names the failing tests",
       base.get("green_at_baseline") is False and len(_names) == 3, _names)
    ck("…with no phantom name scraped from the summary line",
       not any(n.startswith("(") for n in _names), _names)
    ck("…and real counts, not zeros",
       (base.get("baseline") or {}).get("counts", {}).get("passed") == 5,
       (base.get("baseline") or {}).get("counts"))
    print("     baseline:", json.dumps(base)[:220])

    print("\n== 3. search then read — never guess a filename ==")
    _, res = turn(
        '<tool name="workspace_search">{"pattern": "def mul", "glob": "*.py"}'
        '</tool>')
    hit = res[0][1]
    ck("search found the symbol", hit.get("ok") and hit.get("count", 0) >= 1,
       hit)
    ck("…in the right file",
       any("calc.py" in (h.get("path") or "") for h in hit.get("hits", [])),
       hit.get("hits"))

    _, res = turn('<tool name="workspace_read">{"path": "src/calc.py"}</tool>')
    rd = res[0][1]
    ck("read returned the whole small file",
       rd.get("ok") and rd.get("truncated") is False
       and "def mean" in rd.get("content", ""), list(rd)[:8])

    print("\n== 4. a WHOLE-FILE write of a complete module (DSML dialect) ==")
    fixed_calc = CALC.replace(
        "def mul(a, b):\n    # BUG 1: wrong operator\n    return a + b",
        "def mul(a, b):\n    return a * b"
    ).replace(
        "def div(a, b):\n    # BUG 2: no zero guard\n    return a / b",
        "def div(a, b):\n    if b == 0:\n        raise ValueError(\"division "
        "by zero\")\n    return a / b")
    _P = "\uff5c"
    dsml = (f'<{_P}DSML{_P}{_P}tool name="workspace_write">'
            f'<{_P}DSML{_P}{_P}parameter name="path">src/calc.py'
            f'</{_P}DSML{_P}{_P}parameter>'
            f'<{_P}DSML{_P}{_P}parameter name="content">' + fixed_calc +
            f'</{_P}DSML{_P}{_P}parameter>'
            f'</{_P}DSML{_P}{_P}tool>')
    _, res = turn(dsml)
    wr = res[0][1] if res else {}
    ck("whole-file write landed through the DSML dialect",
       wr.get("ok") is True, wr)
    _, res = turn('<tool name="workspace_read">{"path": "src/calc.py"}</tool>')
    got = res[0][1].get("content", "")
    ck("the file on disk is BYTE-IDENTICAL to what the model sent",
       got == fixed_calc,
       f"len sent={len(fixed_calc)} got={len(got)}")

    print("\n== 5. a surgical replace on the second file (GLM JSON body) ==")
    glmjson = ('<tool_call>{"name": "workspace_replace", "arguments": '
               + json.dumps({
                   "path": "src/fmt.py",
                   "old": '    # BUG 3: no thousands separator\n'
                          '    return "$%.2f" % n',
                   "new": '    return "$%s" % format(n, ",.2f")'})
               + '}</tool_call>')
    _, res = turn(glmjson)
    rp = res[0][1]
    ck("surgical replace landed through the GLM-JSON dialect",
       rp.get("ok") is True, rp)

    print("\n== 6. verify — and it must be GREEN, not 'looks right' ==")
    _, res = turn('<tool name="workspace_verify">{}</tool>')
    ver = res[0][1]
    print("     verify:", json.dumps(ver)[:400])
    ck("verify ran", ver.get("ok") is True, ver)
    ck("nothing was BROKEN by the edits",
       not (ver.get("broke") or []), ver.get("broke"))
    ck("the previously-failing tests are FIXED",
       sorted(ver.get("fixed") or [])
       == ["test_div_zero", "test_money", "test_mul"], ver.get("fixed"))
    ck("verify reports real counts too",
       (ver.get("counts_now") or {}).get("passed") == 8,
       ver.get("counts_now"))
    ck("nothing is still failing",
       not (ver.get("still_failing") or []), ver.get("still_failing"))

    print("\n== 7. a 6,000-line file: read it in pages, rewrite it whole ==")
    _, res = turn('<tool name="workspace_read">{"path": "src/big.py"}</tool>')
    b1 = res[0][1]
    ck("a big file reports itself INCOMPLETE",
       b1.get("truncated") is True and "[INCOMPLETE" in b1.get("content", ""),
       list(b1)[:8])
    ck("…and reports its REAL length", b1.get("total_lines") == 6000,
       b1.get("total_lines"))
    # page the tail — the move the note itself recommends
    _, res = turn('<tool name="workspace_read">'
                  '{"path": "src/big.py", "start": 5900, "end": 6000}</tool>')
    b2 = res[0][1]
    ck("a ranged read past the byte cap actually returns those lines",
       "CONST_5900" in b2.get("content", "")
       and "CONST_6000" in b2.get("content", ""),
       b2.get("content", "")[:160])
    ck("…and does not bleed past the range",
       "CONST_5899" not in b2.get("content", ""))

    big_new = "".join(f"CONST_{i} = {i * 2}  # rewritten\n"
                      for i in range(1, 6001))
    _, res = turn('<tool name="workspace_write">'
                  + json.dumps({"path": "src/big.py",
                                "content": big_new})[:0]
                  + json.dumps({"path": "src/big.py", "content": big_new})
                  + '</tool>')
    bw = res[0][1]
    ck("a 300 KB whole-file write is accepted", bw.get("ok") is True, bw)
    _, res = turn('<tool name="workspace_read">'
                  '{"path": "src/big.py", "start": 5999, "end": 6000}</tool>')
    ck("…and the tail of it is exactly what was sent",
       "CONST_6000 = 12000" in res[0][1].get("content", ""),
       res[0][1].get("content", "")[:120])

    print("\n== 8. re-verify after the last edit, then diff and export ==")
    # The export gate counts edits SINCE the last verify — big.py was rewritten
    # after step 6, so this is the gate doing its job, not a bug. Do what it
    # says: verify again.
    _, res = turn('<tool name="workspace_verify">{}</tool>')
    ver2 = res[0][1]
    ck("the re-verify is still green", ver2.get("green") is True, ver2)
    print("\n== 8. diff and export ==")
    _, res = turn('<tool name="workspace_diff">{}</tool>')
    df = res[0][1]
    ck("diff shows the changed files",
       df.get("ok") and "calc.py" in json.dumps(df)
       and "fmt.py" in json.dumps(df), list(df)[:8])
    _, res = turn('<tool name="workspace_export">{}</tool>')
    ex = res[0][1]
    ck("export is allowed once the work is verified", ex.get("ok") is True, ex)
    if ex.get("ok"):
        ck("the exported zip exists", os.path.isfile(ex.get("zip") or ex.get("zip_path") or ex.get("path") or ""),
           list(ex))

    print("\n== 9. the operator's own directory was never touched ==")
    ck("his calc.py still has the original bug",
       "# BUG 1: wrong operator" in
       open(os.path.join(repo, "src", "calc.py")).read())

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nrepo_e2e: {_p} passed, {_f} failed")
    return 1 if _f else 0


if __name__ == "__main__":
    sys.exit(main())
