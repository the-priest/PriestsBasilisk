#!/usr/bin/env python3
"""
test_truncwrite.py — a placeholder is not an abbreviation, it is a deletion.

THE BUG
=======
A model writing a whole file sometimes writes the part it changed and then a
comment standing in for the rest:

    def add(a, b):
        return a + b
    # ... rest unchanged ...

Every function below that marker is gone. Reproduced against the live
workspace: a 59-line file written as 3 lines with that comment returned
`ok: True`, and `def sub` was no longer in the file.

WORK MODE's contract warns about it twice, in capitals — "NEVER write
`# ... rest unchanged ...` ... that DELETES the omitted code". That is advice,
and the write still landed. Same lesson as the verification gate: the model was
told, so make it a gate.

THE RULE NEEDS ALL THREE, and the third is what makes it safe to ship:
  1. the file ALREADY EXISTED (a new file has nothing to lose),
  2. the new content carries a placeholder LINE — a whole line whose only
     content is a stand-in, not a sentence that mentions one,
  3. and the file SHRANK to under 60% of its lines.

Run:  python3 tests/test_truncwrite.py
"""

from __future__ import annotations

import glob
import io
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from basilisk_core import truncated_write_refusal as refuse          # noqa: E402

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


BIG = "\n".join(f"def f{i}():\n    return {i}\n" for i in range(25))


# ── 1. THE SHAPES IT MUST CATCH ──────────────────────────────────────
print("\n== a placeholder write is refused ==")
MARKERS = [
    "# ... rest unchanged ...",
    "# ... rest of the file remains unchanged",
    "// existing code here",
    "    # keep the rest",
    "/* unchanged code */",
    "# rest of file",
    "<!-- no changes below -->",
    "# truncated for brevity",
    "# same as before",
    "-- existing implementation",
    "# ... etc",
    "  // leave the remaining",
    "# unchanged content",
    "# rest of the class",
]
for mk in MARKERS:
    new = "def f0():\n    return 0\n" + mk + "\n"
    r = refuse("app.py", BIG, new)
    ck(f"refused: {mk.strip()!r}", bool(r) and r.get("ok") is False)

_r = refuse("app.py", BIG, "def f0():\n    return 0\n# ... rest unchanged ...\n")
ck("the refusal says what it counted",
   "lines" in (_r.get("error") or "") and "%s" not in (_r.get("error") or ""))
ck("...quotes the offending line back",
   "rest unchanged" in (_r.get("error") or ""))
ck("...and says a placeholder is not an abbreviation",
   "not an abbreviation" in (_r.get("error") or ""))
ck("...and gives BOTH ways out, whole file or replace",
   "ENTIRE final content" in (_r.get("next") or "")
   and "workspace_replace" in (_r.get("next") or ""))
ck("...and forbids the obvious workaround",
   "Do not re-send this content with the placeholder reworded"
   in (_r.get("next") or ""),
   "otherwise the model just renames the marker and deletes the code anyway")
ck("it is flagged so a caller can tell it from any other refusal",
   _r.get("truncation_guard") is True)


# ── 2. THE COUNTER-PROPERTY — this one is the whole risk ─────────────
# A write guard with false positives is worse than none: it blocks real work
# with a confident wrong reason, and the model has no way round it.
print("\n== every real file in this repo, rewritten byte-for-byte ==")
_files = (glob.glob(os.path.join(_ROOT, "*.py"))
          + glob.glob(os.path.join(_ROOT, "basilisk_ext", "*.py"))
          + glob.glob(os.path.join(_ROOT, "tests", "*.py"))
          + glob.glob(os.path.join(_ROOT, "*.md"))
          + glob.glob(os.path.join(_ROOT, "*.txt")))
_fp = []
for _f2 in _files:
    try:
        t = io.open(_f2, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    if refuse(_f2, t, t):
        _fp.append(_f2)
ck(f"{len(_files)} files rewritten as-is, 0 refused", not _fp, str(_fp[:3]))
ck("the corpus is not empty", len(_files) > 60, str(len(_files)))

print("\n== honest edits are not refused ==")
ck("an honest 80% deletion with no placeholder",
   refuse("a.py", BIG, "\n".join(BIG.splitlines()[:8])) is None,
   "deleting code on purpose is allowed - the marker is the signal")
ck("a full rewrite of the same size", refuse("a.py", BIG, BIG.upper()) is None)
ck("a brand-new file (no previous content)",
   refuse("new.py", "", "x\n# ... rest unchanged ...\n") is None)
ck("a short file, even with a marker",
   refuse("a.py", "\n".join(["x"] * 10),
          "x\n# ... rest unchanged ...\n") is None,
   "under 12 lines there is nothing meaningful to lose")
ck("a marker ADDED without shrinking the file",
   refuse("a.py", BIG, BIG + "\n# ... rest unchanged ...\n") is None)
ck("prose that MENTIONS unchanged code mid-sentence",
   refuse("README.md", "\n".join(["prose"] * 80),
          "# Notes\nThe rest of the file remains unchanged when you patch "
          "it, which is why...\n") is None,
   "the rule is a placeholder LINE, not a sentence containing the words")
ck("a python stub file full of real Ellipsis",
   refuse("stub.pyi", "\n".join(["def f(): ..."] * 40),
          "\n".join(["def f(): ..."] * 10)) is None,
   "`...` as syntax is not `... rest unchanged ...` as a promise")


# ── 3. PURE AND TOTAL ────────────────────────────────────────────────
print("\n== junk in, None out ==")
for a, b in ((None, None), ("", ""), (BIG, None), (None, BIG),
             (123, 456), ([], {}), (BIG, object())):
    try:
        r = refuse("x", a, b)
        ok = r is None or isinstance(r, dict)
    except Exception as e:          # noqa: BLE001
        ok = False
        r = f"RAISED {type(e).__name__}: {e}"
    ck(f"survives ({type(a).__name__}, {type(b).__name__})", ok, str(r)[:80])


# ── 4. BOTH WRITE PRIMITIVES ARE GATED ───────────────────────────────
# "A guard only ever protects the function it is inlined in" — the lesson
# from gate_command, and tool_write_file has the wider reach of the two.
print("\n== the guard is on both write primitives ==")
CORE = io.open(os.path.join(_ROOT, "basilisk_core.py"), encoding="utf-8").read()
_wsw = CORE.split("def tool_workspace_write(")[1].split("\ndef ")[0]
ck("tool_workspace_write calls it", "truncated_write_refusal(" in _wsw)
ck("...before it writes anything",
   _wsw.index("truncated_write_refusal(") < _wsw.index(".write(path, content"))
_wf = CORE.split("def tool_write_file(")[1].split("\ndef ")[0]
ck("tool_write_file calls it", "truncated_write_refusal(" in _wf)
ck("...only on a replace, never an append",
   'if mode == "replace" and os.path.isfile(rp):' in _wf,
   "an append adds to the end and cannot delete what is above it")


print(f"\ntruncated write: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
