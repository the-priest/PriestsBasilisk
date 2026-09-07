#!/usr/bin/env python3
"""
test_repofix.py — "it can't write big code at once, and when it fixes a repo
the write doesn't go through or the code comes back scrambled".

Four faults behind that one sentence. Three were reachable every single time
Basilisk was pointed at its own source, which is the repo it gets pointed at
most.

1. A FILE CONTAINING `</tool>` CUT ITS OWN CALL SHORT — in two dialects that
   had never been given the repair the JSON body already had. TOOL_TAG_RE is
   non-greedy, so a write whose CONTENT holds the literal `</tool>` ends the
   match inside the file. The JSON path re-cuts at the LAST closer; the
   `<parameter>` dialect never got there, because _params_to_args "succeeded"
   on the parameters that arrived before the premature cut and dropped the
   rest. Measured: the content argument vanished (args=['path']), so the write
   ran with no file body. Basilisk's own persona, tests and source are full of
   `</tool>`.

2. THE SAME REPAIR, DEFEATED BY A FENCE. The re-cut re-reads RAW text, so a
   ```json fence came back with the widened span and the recovered characters
   then failed to parse — straight into {"_raw": ...}.

3. THE SYNTAX GUARD DEADLOCKED REPO REPAIR. It judged the RESULT only, so any
   edit to a file that did not already parse was refused — including an edit
   with nothing to do with the breakage:

       repo file broken at line 1
       replace "return 2" -> "return 22" at line 5
       => "refused: Python syntax error at line 1. Nothing was written."

   The model did not cause that error, but the message reads as a complaint
   about ITS edit, so it retries with different escaping and is refused
   identically. A broken file could only be edited by an edit that made the
   whole file valid in ONE shot — which is exactly what repairing a repo with
   several faults cannot do.

4. A TRUNCATED READ DID NOT SAY SO IN THE CONTENT. A big file came back cut at
   max_bytes with `truncated: true` in a sibling field and nothing in the text.
   A model that reads a 16,000-line file and is asked to fix it writes back
   what it read, deleting everything past the cut. `total_lines` was counted
   from the TRUNCATED text too, so the model was told 5,212 lines for a file
   that has 16,000 and believed it had all of it.

Run:  python3 tests/test_repofix.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import zipfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

_HOME = tempfile.mkdtemp(prefix="repofix-home-")
os.environ["HOME"] = _HOME
os.environ["XDG_CONFIG_HOME"] = os.path.join(_HOME, ".config")
os.environ["XDG_DATA_HOME"] = os.path.join(_HOME, ".local", "share")

import basilisk_core as C                                      # noqa: E402

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


def _head(rel, n):
    with open(os.path.join(_ROOT, rel), encoding="utf-8") as fh:
        return "".join(fh.readlines()[:n])


# ═════════════════════════════════════════════════════════════════════
# 1-2. A BIG FILE SURVIVES THE ROUND TRIP, BYTE FOR BYTE, IN EVERY DIALECT
# ═════════════════════════════════════════════════════════════════════
print("\n== a write survives every dialect, byte for byte ==")

_PAYLOADS = {
    "python_small": _head("basilisk_ext/xbow.py", 40),
    "python_large": _head("basilisk_core.py", 900),
    "html": _head("index.html", 160),
    "shell": _head("install.sh", 250),
    "json_file": json.dumps({"a": [1, 2, {"b": 'c"d'}], "e": None}, indent=2),
    # THE ONE THAT BROKE. Basilisk's own source says `</tool>` constantly.
    "has_close_tag": ("x = 1\n# the string </tool> appears here\n"
                      "print('</tool>')\n"),
    "backslashes": "p = re.compile(r'\\d+\\s*\\\\')\nw = 'C:\\\\Users\\\\x'\n",
    "triple_quotes": 'def f():\n    """doc \'\'\' inside"""\n    return 1\n',
    "unicode": "s = '\u27e6\u27e7 \uff5c \u2581 \U0001D54C caf\u00e9'\n",
    "trailing_newlines": "final = 1\n\n\n",
    "no_trailing_newline": "final = 1",
    "just_a_number": "42",
}
_PIPE = "\uff5c"


def _dialects(path, content):
    j = json.dumps({"path": path, "content": content})
    yield "canonical", f'<tool name="write_file">{j}</tool>'
    yield "canonical_in_prose", f'Writing.\n<tool name="write_file">{j}</tool>\nDone.'
    yield "dsml", (f'<{_PIPE}DSML{_PIPE}{_PIPE}tool name="write_file">'
                   f'<{_PIPE}DSML{_PIPE}{_PIPE}parameter name="path">{path}'
                   f'</{_PIPE}DSML{_PIPE}{_PIPE}parameter>'
                   f'<{_PIPE}DSML{_PIPE}{_PIPE}parameter name="content">{content}'
                   f'</{_PIPE}DSML{_PIPE}{_PIPE}parameter>'
                   f'</{_PIPE}DSML{_PIPE}{_PIPE}tool>')
    yield "dsml_ascii", (f'<||DSML||tool name="write_file">'
                         f'<||DSML||parameter name="path">{path}</||DSML||parameter>'
                         f'<||DSML||parameter name="content">{content}</||DSML||parameter>'
                         f'</||DSML||tool>')
    yield "glm_argkey", (f"<tool_call>write_file\n<arg_key>path</arg_key>\n"
                         f"<arg_value>{path}</arg_value>\n"
                         f"<arg_key>content</arg_key>\n"
                         f"<arg_value>{content}</arg_value>\n</tool_call>")
    yield "glm_json", ('<tool_call>{"name": "write_file", "arguments": '
                       + j + "}</tool_call>")
    yield "invoke", f'<invoke name="write_file">{j}</invoke>'
    yield "fenced_json", f'<tool name="write_file">\n```json\n{j}\n```\n</tool>'


_broken = []
_total = 0
for _pn, _content in _PAYLOADS.items():
    for _dn, _raw in _dialects(f"/tmp/{_pn}.txt", _content):
        _total += 1
        _calls = C.parse_tool_calls(_raw)
        if len(_calls) != 1:
            _broken.append(f"{_pn}/{_dn}: parsed {len(_calls)} calls")
            continue
        _got = _calls[0].args.get("content")
        if not isinstance(_got, str):
            _broken.append(f"{_pn}/{_dn}: content is "
                           f"{type(_got).__name__}, args={list(_calls[0].args)}")
        elif _got != _content:
            _broken.append(f"{_pn}/{_dn}: len {len(_content)} -> {len(_got)}")
ck(f"{_total} round trips, every one byte-identical", not _broken,
   "; ".join(_broken[:4]))

# The specific shape, called out so a regression names itself.
_tricky = "a = 1\nprint('</tool>')\n"
for _dn, _raw in _dialects("/tmp/t.py", _tricky):
    _c = C.parse_tool_calls(_raw)
    ck(f"a file containing </tool> survives the {_dn} dialect",
       len(_c) == 1 and _c[0].args.get("content") == _tricky,
       str(_c[0].args if _c else "no call"))

# COUNTER-PROPERTY: widening must never swallow a following call.
_two = ('<tool name="read_file">{"path": "/a"}</tool>\n'
        '<tool name="read_file">{"path": "/b"}</tool>')
_c = C.parse_tool_calls(_two)
ck("two ordinary calls stay two calls (the re-cut cannot merge them)",
   len(_c) == 2 and _c[0].args.get("path") == "/a"
   and _c[1].args.get("path") == "/b", str([x.args for x in _c]))


# ═════════════════════════════════════════════════════════════════════
# 3. THE SYNTAX GUARD MUST NOT DEADLOCK A REPAIR
# ═════════════════════════════════════════════════════════════════════
print("\n== repairing an already-broken file ==")

_BROKEN_SRC = "def f(:\n    return 1\n\ndef g():\n    return 2\n"
_GOOD_SRC = "def h():\n    return 3\n"


def _fresh_repo(name):
    src = tempfile.mkdtemp(prefix="repo-")
    with open(os.path.join(src, "broken.py"), "w") as fh:
        fh.write(_BROKEN_SRC)
    with open(os.path.join(src, "good.py"), "w") as fh:
        fh.write(_GOOD_SRC)
    zp = os.path.join(_HOME, name + ".zip")
    with zipfile.ZipFile(zp, "w") as z:
        for f in os.listdir(src):
            z.write(os.path.join(src, f), f)
    C.tool_workspace_import(zp, name)


_fresh_repo("r1")
_r = C.tool_workspace_replace("broken.py", "return 2", "return 22")
ck("an edit ELSEWHERE in a broken file is allowed "
   "(it did not cause the error and was not fixing it)",
   _r.get("ok") is True, str(_r.get("error"))[:110])
ck("…and the result SAYS the file still does not parse",
   "STILL does not parse" in str(_r.get("note", "")), str(_r.get("note"))[:90])
ck("…and marks it machine-readably", _r.get("parses") is False)
_r2 = C.tool_workspace_replace("broken.py", "def f(:", "def f():")
ck("the fix itself then applies", _r2.get("ok") is True, str(_r2.get("error")))
ck("…and once valid, no still-broken note is attached",
   "note" not in _r2 or "STILL does not parse" not in str(_r2.get("note", "")))

# THE COUNTER-PROPERTY, which is the whole reason the guard exists.
print("\n== but breaking WORKING code is still refused ==")
_fresh_repo("r2")
_b1 = C.tool_workspace_replace("good.py", "def h():", "def h(:")
ck("a replace that breaks a valid file is refused",
   _b1.get("ok") is False and _b1.get("syntax_error") is True,
   str(_b1)[:110])
_b2 = C.tool_workspace_write("good.py", "def h(:\n    return 3\n")
ck("a whole-file write that breaks a valid file is refused",
   _b2.get("ok") is False and _b2.get("syntax_error") is True,
   str(_b2)[:110])
ck("…and the file on disk is untouched",
   C.tool_workspace_read("good.py").get("content") == _GOOD_SRC)
_b3 = C.tool_workspace_write("good.py", "def h():\n    return 33\n")
ck("a valid rewrite still goes through", _b3.get("ok") is True)
_b4 = C.tool_workspace_write("brand_new.py", "def z(:\n", create=True)
ck("a NEW file must still be valid (nothing existed to be broken)",
   _b4.get("ok") is False, str(_b4)[:90])
_b5 = C.tool_workspace_write("brand_new.py", "def z():\n    pass\n", create=True)
ck("…and a valid new file is created", _b5.get("ok") is True)
_b6 = C.tool_workspace_write("page.html", "<p>unclosed", create=True)
ck("non-Python files are not syntax-checked at all", _b6.get("ok") is True)


# ═════════════════════════════════════════════════════════════════════
# 4. A TRUNCATED READ SAYS SO WHERE THE MODEL CANNOT MISS IT
# ═════════════════════════════════════════════════════════════════════
print("\n== a big file reads back honestly ==")

_src = tempfile.mkdtemp(prefix="bigrepo-")
_HUGE = _head("basilisk.py", 16000)
_SMALL = _head("basilisk_ext/xbow.py", 137)
with open(os.path.join(_src, "huge.py"), "w", encoding="utf-8") as fh:
    fh.write(_HUGE)
with open(os.path.join(_src, "small.py"), "w", encoding="utf-8") as fh:
    fh.write(_SMALL)
_zp = os.path.join(_HOME, "big.zip")
with zipfile.ZipFile(_zp, "w") as z:
    for f in os.listdir(_src):
        z.write(os.path.join(_src, f), f)
C.tool_workspace_import(_zp, "bigrepo")

_rs = C.tool_workspace_read("small.py")
ck("a small file is returned whole and unmarked",
   _rs.get("content") == _SMALL and _rs.get("truncated") is False)
ck("…with no INCOMPLETE marker in the content",
   "[INCOMPLETE" not in _rs.get("content", ""))

_rh = C.tool_workspace_read("huge.py")
_real_lines = _HUGE.count("\n") + (0 if _HUGE.endswith("\n") else 1)
ck("a huge file is flagged truncated", _rh.get("truncated") is True)
ck("the INCOMPLETE marker is IN THE CONTENT, not just beside it "
   "(a flag beside it is a flag the model can skip)",
   "[INCOMPLETE" in _rh.get("content", ""))
ck("total_lines counts the REAL file, not the truncated text "
   f"({_rh.get('total_lines')} vs {_real_lines})",
   _rh.get("total_lines") == _real_lines,
   f"{_rh.get('total_lines')} != {_real_lines}")
ck("shown_lines says how much actually arrived",
   isinstance(_rh.get("shown_lines"), int)
   and _rh["shown_lines"] < _rh["total_lines"])
ck("the note tells it NOT to write this back as the whole file",
   "Do NOT write this back" in str(_rh.get("note", "")))
ck("…and points at the way to get the rest",
   "start/end" in str(_rh.get("note", ""))
   or "workspace_replace" in str(_rh.get("note", "")))


print(f"\nrepofix: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
