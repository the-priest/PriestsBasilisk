#!/usr/bin/env python3
"""
test_bigwrite.py — "writing big code fails every time, it has to do it in
tiny sections".

FOUR bugs sat behind that one sentence, and only one of them was about size.

1. QUOTE DENSITY, NOT SIZE.  _loads_lenient repairs literal control characters
   inside a JSON string and nothing else, so an unescaped inner `"` — which is
   to say any real code — put the whole call in {"_raw": …}. A three-line
   function with a print() failed exactly as reliably as a 400-line module;
   tiny sections only "worked" because they are short enough to hand-escape.

2. THE REPLY WAS CUT OFF AND NOBODY LOOKED.  finish_reason was never read, so
   a call truncated at max_tokens was reported to the model as a SYNTAX
   problem — and the model re-sent the same oversized call into the same cap.

3. THE FILE BODY WAS INTERPRETED.  In the `<parameter>` dialect V4-Flash
   emits, _coerce_param turned config.json's contents into a dict and a file
   holding `42` into an int, so the write raised TypeError; it also .strip()ed
   the body, so such a file could never end in a newline.

4. A FILE CONTAINING `</tool>` cut its own call short.

Plus the floor: write_file was the one write primitive with no _fs_guard.

Run:  python3 tests/test_bigwrite.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

_HOME = tempfile.mkdtemp(prefix="bigwrite-home-")
os.environ["HOME"] = _HOME

import basilisk_core as C                                     # noqa: E402

_passed = 0
_failed = 0


def ck(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  PASS {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}   [{detail}]")


CODE = ('import os\n'
        'def greet(name):\n'
        '    print("hello, " + name)\n'
        '    return {"k": "v"}\n')
BIG = CODE * 80                      # ~5.7 KB, quotes on every third line


def _args(text):
    calls = C.parse_tool_calls(text)
    return calls[0].args if calls else None


# ── 1. THE SHAPES A MODEL ACTUALLY EMITS ─────────────────────────────
print("== a file body survives every shape a model writes it in ==")

a = _args('<tool name="write_file">'
          + json.dumps({"path": "/tmp/a.py", "content": BIG}) + "</tool>")
ck("properly escaped JSON still parses", a is not None and a.get("content") == BIG)

a = _args('<tool name="write_file">{"path": "/tmp/a.py", "content": "'
          + BIG + '"}</tool>')
ck("raw newlines AND unescaped quotes are recovered",
   a is not None and a.get("content") == BIG,
   "this is the shape that failed every time")

a = _args('<tool name="propose_edit">{"path": "/tmp/a.py", "content": "'
          + BIG + '", "explanation": "a new module"}</tool>')
ck("a trailing sibling key is not swallowed into the file",
   a is not None and a.get("content") == BIG
   and a.get("explanation") == "a new module",
   str(a)[:120] if a else "no call")

a = _args('<tool name="write_file">{"content": "' + BIG
          + '", "path": "/tmp/a.py"}</tool>')
ck("content first, path after", a is not None and a.get("content") == BIG
   and a.get("path") == "/tmp/a.py")

_embedded = 'cfg = \'{"a": "b"}\'\n' + BIG
a = _args('<tool name="write_file">{"path": "/tmp/a.py", "content": "'
          + _embedded + '"}</tool>')
ck("source that embeds JSON is not truncated at its own brace",
   a is not None and a.get("content") == _embedded,
   "the early candidate terminator won")

_wp = 'p = "C:\\Users\\me"\nrx = re.compile(r"\\d+\\s")\n'
a = _args('<tool name="write_file">{"path": "/tmp/a.py", "content": "'
          + _wp + '"}</tool>')
ck("a lone backslash is kept, not eaten",
   a is not None and a.get("content") == _wp, repr(a.get("content")) if a else "")

_tooly = 'HELP = "close it with </tool>"\n' + BIG
a = _args('<tool name="write_file">{"path": "/tmp/a.py", "content": "'
          + _tooly + '"}</tool>')
ck("a file containing </tool> does not cut its own call short",
   a is not None and a.get("content") == _tooly)

a = _args('<tool name="write_file">'
          '<parameter name="path">/tmp/a.py</parameter>'
          '<parameter name="content">\n' + BIG + '</parameter></tool>')
ck("the <parameter> dialect keeps the body byte-for-byte",
   a is not None and a.get("content") == BIG,
   f"len {len(a.get('content', '')) if a else 0} vs {len(BIG)}")

a = _args('<tool name="write_file">'
          '<parameter name="path">/tmp/c.json</parameter>'
          '<parameter name="content">{"a": 1, "b": [2, 3]}</parameter></tool>')
ck("a JSON file's contents stay a string",
   a is not None and isinstance(a.get("content"), str),
   f"got {type(a.get('content')).__name__ if a else None} — write() would raise")

a = _args('<tool name="write_file">'
          '<parameter name="path">/tmp/n.txt</parameter>'
          '<parameter name="content">42</parameter></tool>')
ck("a file holding a number stays a string",
   a is not None and a.get("content") == "42")


# ── 2. THE COUNTER-PROPERTY ──────────────────────────────────────────
# The repair is narrow on purpose: it must not turn unreadable arguments on
# OTHER tools into plausible-looking ones, because a `run` call assembled out
# of a guess is a command nobody asked for.
print("\n== and nothing else got looser ==")

a = _args('<tool name="run">{"command": "ls -la", "reason": "look"}</tool>')
ck("a normal run call is untouched", a == {"command": "ls -la", "reason": "look"})

a = _args('<tool name="run">{"command": "echo "hi""}</tool>')
ck("a run call with broken JSON still refuses to be guessed at",
   a is not None and list(a) == ["_raw"], str(a)[:100])

a = _args('<tool name="web_read">{"url": "https://example.org/a"}</tool>')
ck("web_read is untouched", a == {"url": "https://example.org/a"})

_cut = ('<tool name="write_file">{"path": "/tmp/a.py", "content": "'
        + BIG[:2000])
a = _args(_cut)
ck("a call cut off mid-file is NEVER salvaged into a half write",
   a is not None and list(a) == ["_raw"],
   "half a module must not reach the disk")
ck("…and the host can tell that it was cut off",
   not C.write_body_is_terminated('{"path": "x", "content": "def f():'))
ck("…while a complete body reads as complete",
   C.write_body_is_terminated('{"path": "x", "content": "def f(): pass"}'))


# ── 3. THE FLOOR ─────────────────────────────────────────────────────
# write_file was the fourth write primitive and the only one with no guard:
# delete/copy/move all REFUSED ~/.ssh/authorized_keys and write_file replaced
# it, ok:True.  gate_command's docstring is exactly right — a guard protects
# only the function it sits in.
print("\n== write_file asks the same question every other write asks ==")

_ssh = os.path.join(_HOME, ".ssh")
os.makedirs(_ssh, exist_ok=True)
_keys = os.path.join(_ssh, "authorized_keys")
with open(_keys, "w", encoding="utf-8") as f:
    f.write("ssh-rsa AAAA the-real-key\n")

r = C.tool_write_file(_keys, "ssh-rsa AAAA attacker\n", make_backup=False)
ck("a sensitive path is refused", r.get("ok") is False, str(r)[:120])
ck("…and the file on disk is untouched",
   open(_keys, encoding="utf-8").read().strip().endswith("the-real-key"))
ck("delete_path agrees (they must not disagree)",
   C.tool_delete_path(_keys).get("ok") is False)

_loot = os.path.join(_HOME, "loot")
os.makedirs(_loot, exist_ok=True)
r = C.tool_write_file(os.path.join(_loot, "notes.md"), "# notes\n")
ck("ordinary work is not refused", r.get("ok") is True, str(r)[:120])
r = C.tool_write_file(os.path.join(_loot, "basilisk_thing.py"), "x = 1\n")
ck("a self-edit is not refused", r.get("ok") is True, str(r)[:120])


# ── 4. SECTIONED WRITING ─────────────────────────────────────────────
# The workaround has to be a real, supported path — the model is told to use
# it whenever a file is too big for one reply.
print("\n== a file too big for one reply can be written in sections ==")

_big = os.path.join(_loot, "module.py")
r1 = C.tool_write_file(_big, "def a():\n    return 1\n")
r2 = C.tool_write_file(_big, "\ndef b():\n    return 2\n", mode="append")
ck("the first section writes", r1.get("ok") is True)
ck("the second section appends", r2.get("ok") is True and r2.get("mode") == "append")
ck("…and reports how much it added", r2.get("appended") == len("\ndef b():\n    return 2\n"))
_txt = open(_big, encoding="utf-8").read()
ck("the file is the two sections joined, in order",
   _txt == "def a():\n    return 1\n\ndef b():\n    return 2\n", repr(_txt))

r3 = C.tool_write_file(_big, "def broken(:\n", mode="append")
ck("an append that would break the file is refused",
   r3.get("ok") is False and r3.get("syntax_error") is True, str(r3)[:120])
ck("…against the ASSEMBLED file, and the file survives",
   "broken" not in open(_big, encoding="utf-8").read())

r4 = C.tool_write_file(os.path.join(_loot, "new.txt"), "first\n", mode="append")
ck("appending to a file that does not exist yet creates it",
   r4.get("ok") is True)
r5 = C.tool_write_file(_big, "x", mode="overwrite")
ck("an unknown mode is named, not guessed",
   r5.get("ok") is False and "mode" in str(r5.get("error", "")), str(r5)[:120])

a = _args('<tool name="write_file">{"path": "/tmp/a.py", "mode": "append", '
          '"content": "print(\\"x\\")\\n"}</tool>')
ck("mode survives the parser", a is not None and a.get("mode") == "append")


# ── 5. THE HOST TELLS THE TRUTH ABOUT WHY IT FAILED ──────────────────
print("\n== a cut-off reply is not reported as bad escaping ==")

_SRC = open(os.path.join(_ROOT, "basilisk.py"), encoding="utf-8").read()
ck("the window remembers the provider's finish_reason",
   "_last_stream_truncated" in _SRC)
ck("the operator is told about the token cap, not about quoting",
   "response-token cap" in _SRC)
ck("the model is told to split rather than re-send",
   "Do NOT re-send the same call" in _SRC or
   "Do NOT re-send" in _SRC)
_CORE = open(os.path.join(_ROOT, "basilisk_core.py"), encoding="utf-8").read()
ck("the backend reads finish_reason at all", 'finish_reason' in _CORE)
ck("…and reports truncation as its own field", '"truncated": _finish_reason' in _CORE)

# ── 6. THE REPAIR IS NOT PAID FOR BY ORDINARY REPLIES ────────────────
# Asserted as a SCALING EXPONENT, not a millisecond ceiling, so it fails the
# same way on a slow box: this parser runs once per streamed frame.
print("\n== the repair costs what it should ==")

import time                                                   # noqa: E402


def _t(txt, n=5):
    _t0 = time.time()
    for _ in range(n):
        C.parse_tool_calls(txt)
    return (time.time() - _t0) / n


_plain = "An ordinary reply with no tool call in it at all. " * 400
_normal = '<tool name="run">{"command": "ls -la"}</tool>' * 20
_small = _t(('<tool name="write_file">{"path": "/tmp/a.py", "content": "'
             + CODE * 200 + '"}</tool>'))
_large = _t(('<tool name="write_file">{"path": "/tmp/a.py", "content": "'
             + CODE * 800 + '"}</tool>'))
ck("prose pays nothing", _t(_plain) < 0.01, f"{_t(_plain)*1000:.1f} ms")
ck("normal tool calls pay nothing", _t(_normal) < 0.01, f"{_t(_normal)*1000:.1f} ms")
ck("4x the file is well under 16x the time (not quadratic)",
   _large < _small * 8, f"{_small*1000:.1f} ms -> {_large*1000:.1f} ms")


# ── 7. DISPLAY AND THE PARSER AGREE ──────────────────────────────────
print("\n== the operator sees what the parser saw ==")

_leaky = ('Writing it now.\n<tool name="write_file">{"path": "/tmp/a.py", '
          '"content": "HELP = \"</tool>\"\nprint(1)\n"}</tool>')
ck("the tail of a file containing </tool> is not printed into the chat",
   C.strip_tool_calls(_leaky).strip() == "Writing it now.",
   repr(C.strip_tool_calls(_leaky))[:120])

_two = ('First.\n<tool name="write_file">{"path": "/tmp/a.py", '
        '"content": "x = 1\n"}</tool>\nNow running it.\n'
        '<tool name="run">{"command": "python3 /tmp/a.py"}</tool>')
ck("prose between two calls survives",
   "Now running it." in C.strip_tool_calls(_two),
   repr(C.strip_tool_calls(_two))[:120])
ck("…and both calls still parse",
   [c.name for c in C.parse_tool_calls(_two)] == ["write_file", "run"])

# ── 8. A FLAKY FETCH RETRIES INSTEAD OF DYING ────────────────────────
# "can't even fetch news": a leashed answer-mode turn that got a single
# transient network miss tended to narrate or give up. web_read now retries
# once on a transient TRANSPORT failure and on a 5xx, but never on a real
# status (404/403) — that IS the answer.
print("\n== a transient web_read failure retries, a real status does not ==")

import urllib.error                                            # noqa: E402


class _FakeResp:
    def __init__(self, code, body):
        self._c, self._b = code, body.encode()

    def read(self, n=None):
        return self._b

    def getcode(self):
        return self._c

    def geturl(self):
        return "https://nvd.nist.gov/x"

    @property
    def headers(self):
        class _H:
            def get(self, k, d=""):
                return ""

            def get_content_charset(self):
                return "utf-8"
        return _H()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _run_fetch(seq):
    hits = {"n": 0}

    class _O:
        def open(self, req, timeout=20):
            hits["n"] += 1
            item = seq[min(hits["n"] - 1, len(seq) - 1)]
            if isinstance(item, Exception):
                raise item
            return _FakeResp(*item)

    _saved = C.urllib.request.build_opener
    C.urllib.request.build_opener = lambda *a: _O()
    try:
        status = None
        try:
            status, _b, _u = C._trusted_fetch("https://nvd.nist.gov/x", timeout=1)
        except Exception:
            status = "raised"
        return hits["n"], status
    finally:
        C.urllib.request.build_opener = _saved


_n, _st = _run_fetch([urllib.error.URLError("reset"), (200, "<html>ok</html>")])
ck("a transient transport error is retried once and then succeeds",
   _n == 2 and _st == 200, f"attempts={_n} status={_st}")

_n, _st = _run_fetch([urllib.error.HTTPError("u", 404, "nf", {}, None)])
ck("a real 404 is NOT retried (the status is the answer)",
   _n == 1, f"attempts={_n}")

_n, _st = _run_fetch([urllib.error.HTTPError("u", 503, "busy", {}, None),
                      (200, "<html>ok</html>")])
ck("a 503 IS retried once", _n == 2 and _st == 200, f"attempts={_n} status={_st}")


print(f"\nbigwrite: {_passed} passed, {_failed} failed")
sys.exit(1 if _failed else 0)
