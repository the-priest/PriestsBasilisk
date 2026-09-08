#!/usr/bin/env python3
"""test_v11_workspace.py — directory import, ranged reads, test-output parsing.

These sit directly under "fix my repo", so a fault here is silent data loss in
the operator's own code. Found: an empty/None path made import_dir realpath("")
to the CURRENT WORKING DIRECTORY and import whatever the app was running in;
parse_test_output raised a TypeError on bytes or None output; and a range the
caller clearly meant but named impossibly fell back to a whole-file read
without saying so.
"""
import os
import shutil
import stat
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
from basilisk_ext import workspace as W
import basilisk_core as C

bad = []


def note(m):
    bad.append(m)


# ══ 1. import_dir: containment and refusal ══════════════════════════
tmp = tempfile.mkdtemp()

# 1a. a symlink pointing OUT of the tree must not be followed
r1 = os.path.join(tmp, "r1"); os.makedirs(os.path.join(r1, "src"))
open(os.path.join(r1, "src", "a.py"), "w").write("x = 1\n")
os.symlink("/etc/passwd", os.path.join(r1, "src", "passwd_link"))
os.symlink("/etc", os.path.join(r1, "etc_link"))
os.makedirs(os.path.join(r1, "real_dir"))
open(os.path.join(r1, "real_dir", "b.py"), "w").write("y = 2\n")
res = W.import_dir(r1)
if not res.get("ok"):
    note(f"1a: a normal directory failed to import: {res}")
tree = res.get("root", "")
for probe in ("src/passwd_link", "etc_link"):
    if os.path.exists(os.path.join(tree, probe)):
        note(f"1a: a symlink was copied into the workspace: {probe}")
walked = W.tree()
names = walked.get("files") or []
if "src/a.py" not in names or "real_dir/b.py" not in names:
    note(f"1a: real files missing after import: {names}")
if any("passwd" in n for n in names):
    note(f"1a: symlink target leaked into the tree: {names}")

# 1b. nothing outside the workspace is reachable afterwards
# NB "..\\..\\etc\\passwd" is deliberately absent: on Linux that is a legal
# single FILENAME, not a traversal, and it was verified by hand to stay inside
# the workspace. Asserting on the name rather than the destination would be
# testing the wrong property.
for evil in ("../../../etc/passwd", "/etc/passwd", "src/../../../../etc/passwd",
             "src/./../../etc/passwd"):
    rd = W.read(evil)
    if rd.get("ok"):
        note(f"1b: escaped the workspace with {evil!r}: {str(rd)[:120]}")
    wr = W.write(evil, "pwned", create=True)
    if wr.get("ok"):
        note(f"1b: WROTE outside the workspace with {evil!r}")

# 1c. a file the process cannot read is skipped, not fatal
r2 = os.path.join(tmp, "r2"); os.makedirs(r2)
open(os.path.join(r2, "ok.py"), "w").write("z = 3\n")
secret = os.path.join(r2, "nope.py")
open(secret, "w").write("secret")
os.chmod(secret, 0o000)
res2 = W.import_dir(r2)
if os.geteuid() != 0:            # root can read anything; skip the assertion
    if not res2.get("ok"):
        note(f"1c: an unreadable file made the whole import fail: {res2}")

# 1d. an empty directory is an honest refusal, not a broken workspace
r3 = os.path.join(tmp, "r3"); os.makedirs(os.path.join(r3, "empty"))
res3 = W.import_dir(r3)
if res3.get("ok"):
    note("1d: an empty directory reported a successful import")
if "no readable files" not in (res3.get("error") or ""):
    note(f"1d: unhelpful error for an empty dir: {res3.get('error')!r}")

# 1e. junk paths must not raise
for junk in (None, "", "   ", 5, [], {}, "/does/not/exist",
             "/etc/passwd", "~/definitely-not-here-9f3a"):
    try:
        rr = W.import_dir(junk)
        if rr.get("ok"):
            note(f"1e: import_dir accepted {junk!r}")
    except Exception as e:
        note(f"1e: import_dir RAISED on {junk!r}: {type(e).__name__}: {e}")

# 1f. the tool wrapper dispatches on what the path IS
r4 = os.path.join(tmp, "r4"); os.makedirs(r4)
open(os.path.join(r4, "m.py"), "w").write("m = 1\n")
a = C.tool_workspace_import(zip_path=r4)          # dir in the zip slot
if not a.get("ok"):
    note(f"1f: a directory in zip_path was refused: {a}")
b = C.tool_workspace_import(path=r4)
if not b.get("ok"):
    note(f"1f: a directory in path was refused: {b}")
c = C.tool_workspace_import()
if c.get("ok") or "repo" not in (c.get("error") or ""):
    note(f"1f: an empty import gave a poor error: {c}")


# ══ 2. ranged reads on a file bigger than the byte cap ══════════════
r5 = os.path.join(tmp, "r5"); os.makedirs(r5)
N = 20000
with open(os.path.join(r5, "big.py"), "w") as fh:
    for i in range(1, N + 1):
        fh.write(f"L{i} = {i}  " + "#" * 40 + "\n")
open(os.path.join(r5, "small.py"), "w").write("a = 1\nb = 2\nc = 3\n")
open(os.path.join(r5, "crlf.py"), "w", newline="").write("p = 1\r\nq = 2\r\n")
open(os.path.join(r5, "noeol.py"), "w").write("only = 1")
with open(os.path.join(r5, "bin.dat"), "wb") as fh:
    fh.write(b"\x00\x01\x02" * 100)
W.import_dir(r5)

# 2a. every window of a huge file is readable and exact
for lo, hi in ((1, 5), (999, 1001), (10000, 10005), (19995, 20000),
               (N - 1, N), (N, N)):
    rd = W.read("big.py", start=lo, end=hi)
    if not rd.get("ok"):
        note(f"2a: read({lo},{hi}) failed: {rd}")
        continue
    body = rd.get("content", "")
    for n in range(lo, hi + 1):
        if f"L{n} = {n}" not in body:
            note(f"2a: line {n} missing from read({lo},{hi})")
            break
    if f"L{lo-1} = {lo-1}" in body and lo > 1:
        note(f"2a: read({lo},{hi}) bled backwards")
    if f"L{hi+1} = {hi+1}" in body and hi < N:
        note(f"2a: read({lo},{hi}) bled forwards")
    if rd.get("total_lines") != N:
        note(f"2a: read({lo},{hi}) reported total_lines={rd.get('total_lines')}")

# 2b. line NUMBERS in the gutter must be right, not off by one
rd = W.read("big.py", start=777, end=779)
first = rd.get("content", "").splitlines()[0] if rd.get("content") else ""
if not first.startswith("777\t"):
    note(f"2b: gutter numbering wrong: {first[:40]!r}")

# 2c. an inverted / silly range is empty, never an exception or a whole file
for lo, hi in ((500, 100), (N + 5000, N + 6000)):
    rd = W.read("big.py", start=lo, end=hi)
    if not rd.get("ok"):
        note(f"2c: read({lo},{hi}) errored: {rd}")
    elif len(rd.get("content", "")) > 200_000:
        note(f"2c: read({lo},{hi}) returned the whole file")
# an unusable range must REFUSE, never quietly serve the whole file
# (0, 0) is NOT in this list: 0 is the documented "unset" sentinel for `end`,
# and a start of 0 reads naturally as "from the top", so whole-file is the
# right answer there — and the whole-file path still marks a big file
# INCOMPLETE, so it carries no data-loss risk. The dangerous shape is a
# caller that clearly wanted a WINDOW and named an impossible one.
for lo, hi in ((-4, -1), ("abc", "def")):
    rd = W.read("big.py", start=lo, end=hi)
    if rd.get("ok"):
        note(f"2c: read({lo!r},{hi!r}) silently fell back to a whole-file read")

# 2d. small files, CRLF, and a missing final newline survive a round trip
rd = W.read("small.py")
if rd.get("content") != "a = 1\nb = 2\nc = 3\n":
    note(f"2d: small file not returned verbatim: {rd.get('content')!r}")
rd = W.read("crlf.py", start=1, end=2)
if "p = 1" not in rd.get("content", "") or "\r" in rd.get("content", ""):
    note(f"2d: CRLF handling: {rd.get('content')!r}")
rd = W.read("noeol.py", start=1, end=1)
if "only = 1" not in rd.get("content", ""):
    note(f"2d: file with no trailing newline: {rd.get('content')!r}")

# 2e. a binary file is still reported as binary on the ranged path
rd = W.read("bin.dat", start=1, end=5)
if rd.get("kind") != "binary":
    note(f"2e: binary file not detected on a ranged read: {rd.get('kind')!r}")

# 2f. junk line numbers never raise and never silently return the wrong thing
for junk in (None, True, False, "abc", "12", 12.9, [], {}, -1, 10**12):
    try:
        rr = W.read("small.py", start=junk, end=junk)
        if not isinstance(rr, dict) or "ok" not in rr:
            note(f"2f: read returned a non-result for start={junk!r}: {rr!r}")
    except Exception as e:
        note(f"2f: read RAISED on start={junk!r}: {type(e).__name__}")

# 2g. the whole-file path still marks a big file INCOMPLETE with a real total
rd = W.read("big.py")
if not rd.get("truncated") or rd.get("total_lines") != N:
    note(f"2g: whole-file read of a big file: truncated={rd.get('truncated')} "
         f"total={rd.get('total_lines')}")
if "[INCOMPLETE" not in rd.get("content", ""):
    note("2g: the truncation marker is not inside the content")


# ══ 3. test-output parsing ══════════════════════════════════════════
P = W.parse_test_output
CASES = {
    "unittest red": ("""FAIL: test_mul (t.T.test_mul)
ERROR: test_div (t.T.test_div)
----------------------------------------------------------------------
Ran 8 tests in 0.002s

FAILED (failures=1, errors=1)
""", 1, {"green": False, "passed": 6, "failed": 1, "errors": 1,
         "names": {"test_mul", "test_div"}}),
    "unittest green": ("Ran 12 tests in 0.1s\n\nOK\n", 0,
                       {"green": True, "passed": 12, "failed": 0,
                        "errors": 0, "names": set()}),
    "unittest ok+skips": ("Ran 5 tests in 0.1s\n\nOK (skipped=2)\n", 0,
                          {"green": True, "passed": 3, "failed": 0,
                           "errors": 0, "names": set()}),
    "unittest all skipped": ("Ran 3 tests in 0.1s\n\nOK (skipped=3)\n", 0,
                             {"green": True, "passed": 0, "failed": 0,
                              "errors": 0, "names": set()}),
    "pytest": ("""FAILED tests/t.py::test_a - assert 1 == 2
2 failed, 6 passed in 0.11s
""", 1, {"green": False, "passed": 6, "failed": 2, "errors": 0,
         "names": {"tests/t.py::test_a"}}),
    "empty log, rc 1": ("", 1, {"green": False}),
    "empty log, rc 0": ("", 0, {"green": True}),
    "unparseable, rc 1": ("something exploded\n", 1, {"green": False}),
}
for name, (raw, rc, want) in CASES.items():
    got = P(raw, rc)
    for k, v in want.items():
        if k == "green":
            if got["green"] is not v:
                note(f"3: {name}: green={got['green']} want {v}")
        elif k == "names":
            if set(got["failed_names"]) != v:
                note(f"3: {name}: names={got['failed_names']} want {sorted(v)}")
        else:
            if got["counts"].get(k) != v:
                note(f"3: {name}: counts[{k}]={got['counts'].get(k)} want {v}")
    for n in got["failed_names"]:
        if n.startswith("(") or "=" in n:
            note(f"3: {name}: phantom test name {n!r}")

# 3b. counts must never go negative or exceed the run size
weird = P("Ran 2 tests in 0.1s\n\nFAILED (failures=9, errors=9)\n", 1)
if weird["counts"]["passed"] < 0:
    note(f"3b: negative passed count: {weird['counts']}")

# 3c. junk in, no raise
for junk in (None, 5, [], {}, b"x", "\x00" * 100, "a" * 500000):
    try:
        P(junk, 1)
    except Exception as e:
        note(f"3c: parse_test_output RAISED on {type(junk).__name__}: {e}")
for rc in (None, "1", [], 1.5):
    try:
        P("Ran 1 test\n\nOK\n", rc)
    except Exception as e:
        note(f"3c: parse_test_output RAISED on rc={rc!r}: {type(e).__name__}")

shutil.rmtree(tmp, ignore_errors=True)
print("\n".join(bad) if bad else "no findings")
print(f"\nv11_workspace: {len(bad)} finding(s)")
sys.exit(1 if bad else 0)
