#!/usr/bin/env python3
"""test_structcalls.py — v1.2.0.3: the three fixes for the V4.1-Flash build loop.

The operator filmed a live V4.1-Flash build failing the same way over and over:
the model "thought for 50,000 characters and said nothing", and a legitimate
re-write of `index.html` was refused by the repeat guard ("already run 2×").
Both are here, plus the mechanism that makes a structured tool call survive an
empty content stream — the way DeepSeek's own harness consumes tool calls.

  1. STRUCTURED CALLS. The OpenAI-style `delta.tool_calls` channel is read,
     reassembled across streamed fragments, and rendered into the canonical
     `<tool …>` text so the ONE parser handles it — even when `content` is
     empty (which is exactly the "said nothing" turn).
  2. REASONING RECOVERY. A tool call the model emitted while THINKING (so it
     landed in reasoning, not content) is still parseable by the same
     canonicaliser — the host re-runs it over the captured reasoning.
  3. REPEAT-GUARD FINGERPRINT. Writing v1 → v2 → v3 of the same file is three
     DIFFERENT actions, so the third is not false-blocked; a byte-identical
     re-write still collapses to one label and is still caught.

Run:  python3 tests/test_structcalls.py
"""
import io
import json
import os
import sys
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import basilisk_core as C

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


# ── 1. _render_native_tool_calls: the fold-to-canonical renderer ─────
print("\n== structured calls render to the canonical text protocol ==")
_r = C._render_native_tool_calls(
    {0: {"name": "write_file",
         "args": '{"path": "index.html", "content": "<h1>x</h1>"}'}})
_calls = C.parse_tool_calls(_r)
ck("a structured write_file renders and re-parses",
   len(_calls) == 1 and _calls[0].name == "write_file"
   and _calls[0].args.get("path") == "index.html",
   _r)

# arguments arrive a few characters at a time — the accumulator concatenates
_frag = C._render_native_tool_calls(
    {0: {"name": "run", "args": '{"comm' + 'and": "ls -la"}'}})
ck("fragmented arguments are concatenated before parsing",
   C.parse_tool_calls(_frag)[0].args.get("command") == "ls -la", _frag)

# a call with no arguments degrades to {}
ck("an argument-less call renders {} and parses",
   bool(C.parse_tool_calls(
       C._render_native_tool_calls({0: {"name": "workspace_verify",
                                        "args": ""}}))))

# a fragment that never resolved a name is dropped, not rendered as junk
ck("a nameless fragment is dropped",
   C._render_native_tool_calls({0: {"name": "", "args": "{}"}}) == "")

# unparseable arguments do not raise — they pass through for the _raw fallback
ck("unparseable arguments do not raise",
   isinstance(C._render_native_tool_calls(
       {0: {"name": "run", "args": "{not json"}}), str))

# two calls in one turn keep their order
_two = C._render_native_tool_calls({
    1: {"name": "second", "args": "{}"},
    0: {"name": "first", "args": "{}"}})
ck("multiple calls render in index order",
   _two.index("first") < _two.index("second"), _two)


# ── 2. the streaming backend folds delta.tool_calls into the reply ───
print("\n== the backend recovers a call from an EMPTY content stream ==")


def _sse(*objs):
    out = []
    for o in objs:
        out.append(("data: " + json.dumps(o)).encode())
    out.append(b"data: [DONE]")
    return out


class _R:
    def __init__(self, lines):
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter(self._lines)


def _spec():
    return types.SimpleNamespace(
        key="probe", base_url="https://example.invalid/v1",
        chain=["m"], extra_headers={}, engine="openai")


def _drive(frames):
    b = C.OpenAICompatBackend(_spec(), api_key="k")
    out = {}

    def fake_urlopen(req, timeout=None):
        return _R(frames)

    real = C.urllib.request.urlopen
    C.urllib.request.urlopen = fake_urlopen
    try:
        b.stream_chat("m", [{"role": "user", "content": "x"}],
                      on_token=lambda t: None,
                      on_done=lambda d: out.update(d or {}),
                      on_error=lambda e: out.update({"error": e}),
                      options={"max_tokens": 1024})
    finally:
        C.urllib.request.urlopen = real
    return out


# The exact shape of the "said nothing" turn: reasoning tokens, NO content,
# and the tool call delivered structured. Before the fix `text` was empty and
# the turn died on the degraded-retry loop.
_empty_content = _drive(_sse(
    {"choices": [{"delta": {"reasoning_content": "let me think..."}}]},
    {"choices": [{"delta": {"tool_calls": [
        {"index": 0, "function": {"name": "write_file",
                                  "arguments": '{"path": "a.html",'}}]}}]},
    {"choices": [{"delta": {"tool_calls": [
        {"index": 0, "function": {"arguments": ' "content": "hi"}'}}]}}]},
))
_ec_calls = C.parse_tool_calls(_empty_content.get("text", ""))
ck("a structured call with EMPTY content is recovered into the reply text",
   len(_ec_calls) == 1 and _ec_calls[0].name == "write_file"
   and _ec_calls[0].args.get("path") == "a.html",
   repr(_empty_content.get("text")))
ck("...and the turn did not error",
   not _empty_content.get("error"), str(_empty_content.get("error")))

# When the model DID write a textual tool call, the structured channel must not
# double it.
_both = _drive(_sse(
    {"choices": [{"delta": {"content":
                            '<tool name="run">{"command":"ls"}</tool>'}}]},
    {"choices": [{"delta": {"tool_calls": [
        {"index": 0, "function": {"name": "run",
                                  "arguments": '{"command":"ls"}'}}]}}]},
))
ck("a textual call is not double-dispatched by the structured channel",
   len(C.parse_tool_calls(_both.get("text", ""))) == 1,
   repr(_both.get("text")))

# An ordinary content-only reply is completely unchanged.
_plain = _drive(_sse(
    {"choices": [{"delta": {"content": "just an answer"}}]}))
ck("a plain content reply is untouched",
   _plain.get("text") == "just an answer", repr(_plain.get("text")))


# ── 3. reasoning recovery is wired into the stream-done handler ───────
print("\n== a call emitted while THINKING is recovered by the same parser ==")
# The recovery re-runs the canonicaliser over the captured reasoning. Prove the
# canonicaliser handles a DeepSeek native-token call sitting in a reasoning
# blob (the host feeds it get_thoughts()).
_reason = ("I should list the directory first.\n"
           "<｜tool▁calls▁begin｜>"
           "<｜tool▁call▁begin｜>function"
           "<｜tool▁sep｜>run\n```json\n"
           '{"command": "ls"}\n```'
           "<｜tool▁call▁end｜>"
           "<｜tool▁calls▁end｜>")
_norm = C._normalise_tool_syntax(_reason)
_rc = C.parse_tool_calls(_norm)
ck("a native-token call inside reasoning normalises and parses",
   len(_rc) == 1 and _rc[0].name == "run"
   and _rc[0].args.get("command") == "ls", _norm)

_BSRC = io.open(os.path.join(_ROOT, "basilisk.py"), encoding="utf-8").read()
ck("the stream-done handler recovers a call from the reasoning stream",
   "recovered a tool call from the reasoning stream" in _BSRC)
ck("...gated on there being no visible answer and no call already found",
   "not executable and not calls and not cancelled" in _BSRC)


# ── 4. the repeat-guard content fingerprint ──────────────────────────
print("\n== iterating on one file is not a repeat; re-writing bytes is ==")

# GTK stub so basilisk imports
class _Meta(type):
    def __getattr__(cls, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return _Obj


class _Obj(metaclass=_Meta):
    def __init__(self, *a, **k):
        pass

    def __call__(self, *a, **k):
        return _Obj()

    def __getattr__(self, n):
        return _Obj()


class _ModStub(types.ModuleType):
    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return _Obj

    def require_version(self, *a, **k):
        pass


for _m in ("gi", "gi.repository", "gi.repository.Gtk", "gi.repository.Adw",
           "gi.repository.GLib", "gi.repository.Gio", "gi.repository.Gdk",
           "gi.repository.GdkPixbuf", "gi.repository.Pango",
           "gi.repository.GObject", "gi.repository.GtkSource",
           "gi.repository.Vte", "gi.repository.Soup"):
    sys.modules[_m] = _ModStub(_m)
sys.modules["gi"].require_version = lambda *a, **k: None

import basilisk as Bk

_label = Bk.MainWindow._action_label


def _call(name, **args):
    return types.SimpleNamespace(name=name, args=args)


_l1 = _label(None, _call("write_file", path="index.html", content="<h1>v1</h1>"))
_l2 = _label(None, _call("write_file", path="index.html", content="<h1>v2</h1>"))
_l3 = _label(None, _call("write_file", path="index.html", content="<h1>v1</h1>"))
ck("different content to the same path -> different labels", _l1 != _l2,
   f"{_l1!r} == {_l2!r}")
ck("identical content to the same path -> identical labels", _l1 == _l3,
   f"{_l1!r} != {_l3!r}")
ck("the path is still visible in the label", "index.html" in _l1, _l1)

# `run` must NOT be fingerprinted — its command IS its label, so
# pytest/pytest/pytest must still collapse and be blockable.
_r1 = _label(None, _call("run", command="pytest -q"))
_r2 = _label(None, _call("run", command="pytest -q"))
ck("run with the same command still collapses to one label", _r1 == _r2, _r1)

# A no-argument call still returns the bare tool name (the constant-label
# property the whole repeat guard rests on).
ck("a no-argument call is still the bare tool name",
   _label(None, _call("workspace_verify")) == "workspace_verify")

# Now prove the guard behaviour end to end with the real ActionLog.
from basilisk_ext.recall import ActionLog

_log = ActionLog()
_limit = 2
# three DIFFERENT writes to index.html — none may block (labels differ)
_blocked = []
for i in range(3):
    lbl = _label(None, _call("write_file", path="index.html",
                             content=f"<h1>v{i}</h1>"))
    _blocked.append(_log.should_block(lbl, _limit))
    _log.record(lbl, "ok", changes_state=True)
ck("3 iterative edits of index.html, 0 blocked", not any(_blocked),
   str(_blocked))

# the SAME bytes written three times DOES block on the third
_log2 = ActionLog()
_same = _label(None, _call("write_file", path="x.html", content="same"))
_blk = []
for _ in range(3):
    _blk.append(_log2.should_block(_same, _limit))
    _log2.record(_same, "ok", changes_state=True)
ck("3 identical re-writes: the third is blocked", _blk == [False, False, True],
   str(_blk))


print(f"\nstructcalls: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
