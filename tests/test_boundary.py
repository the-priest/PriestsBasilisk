#!/usr/bin/env python3
"""
test_boundary.py — a stream becomes "the message" on THREE paths, and all three
must canonicalise.

THE REPORTED FAILURE
====================
Only the happy path did.  finish_streaming() folded the model's native dialect
to the canonical form; the STOP path (_finish_turn_cleanup) and the ERROR path
(_on_stream_error) both took `widget._content` raw and wrote it straight into
the store.

That store row is not just what gets redrawn — it is re-sent to the model as
history on every later turn.  strip_tool_calls' own docstring spells out the
cost of exactly this: "Every later turn then re-sent that garbage to the model
as history, which both wasted context and taught it the broken format was
acceptable."  So a single stopped or errored turn quietly poisoned every turn
after it, and the damage compounded over a long engagement rather than showing
up as one visible failure.

The fix is one boundary — MessageWidget.canonical_content() — used by all three
paths, instead of one path remembering and two forgetting.  These are checked at
SOURCE level (like tests/test_dispatch.py) because the paths are GTK widget
callbacks: what matters is that no path reads the raw attribute, and that
property is exactly what source inspection can assert.

Also covers: GroqBackend referenced a chain constant that was deleted when Groq
stopped being a chat provider, so constructing it raised NameError — a landmine
armed for whoever re-adds the provider.

Run:  python3 tests/test_boundary.py
"""

from __future__ import annotations

import io
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

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


SRC = io.open(os.path.join(_ROOT, "basilisk.py"), encoding="utf-8").read()


def body_of(name, src=SRC, lines=26, code_only=False):
    """The first `lines` source lines following a def, for coarse inspection.

    code_only drops comment lines: several of these fixes carry a comment
    QUOTING the broken code they replaced, and a naive substring check would
    match the explanation of the bug and report the bug still present.
    """
    m = re.search(r"^\s*def " + re.escape(name) + r"\b", src, re.M)
    if not m:
        return ""
    out = src[m.start():].splitlines()[:lines]
    if code_only:
        out = [ln for ln in out if not ln.lstrip().startswith("#")]
    return "\n".join(out)


# ── 1. one boundary, used by every path that ends a stream ───────────
print("\n== every path that ends a stream canonicalises ==")
ck("MessageWidget grew a single canonical_content() boundary",
   re.search(r"def canonical_content\(self\)", SRC) is not None)

_finish = body_of("finish_streaming")
ck("the FINISH path goes through it",
   "canonical_content()" in _finish, repr(_finish[:200]))

_stop = body_of("_finish_turn_cleanup")
ck("the STOP path goes through it",
   "canonical_content()" in _stop, repr(_stop[:300]))
ck("…and no longer reads _content raw",
   not re.search(r"streaming_msg_widget\._content", _stop), repr(_stop[:300]))

_err = body_of("_on_stream_error")
ck("the ERROR path goes through it",
   "canonical_content()" in _err, repr(_err[:300]))
ck("…and no longer reads _content raw",
   not re.search(r"streaming_msg_widget\._content", _err), repr(_err[:300]))


# ── 2. the speech consumers all use the one transform ────────────────
print("\n== every speech consumer uses speakable_text ==")
ck("basilisk.py imports it", "speakable_text" in SRC)

_feed = body_of("_feed_tts_stream", lines=40, code_only=True)
ck("the streaming feed uses it",
   "speakable_text" in _feed, repr(_feed[:400]))
ck("the suspend guard is dialect-blind, not a '<tool' substring",
   "contains_tool_markup" in _feed and '"<tool" in' not in _feed,
   repr(_feed[:500]))

_speak = body_of("_start_speaking_widget")
ck("the per-message speak button uses it",
   "speakable_text" in _speak, repr(_speak[:300]))

ck("the end-of-turn flush uses it",
   re.search(r"_tts_streamer\.flush\(speakable_text\(", SRC) is not None)


# ── 3. canonicalisation is idempotent, so doubling up is a no-op ─────
# The boundary is applied at finish_streaming AND again in _on_stream_done_body.
# That is only safe because normalising twice cannot change the answer.
print("\n== canonicalising twice is a no-op, not a second opinion ==")
PIPE = "｜"
_samples = [
    'Prose.\n<tool name="run">{"command": "id"}</tool>',
    f'Prose.\n<{PIPE}DSML{PIPE}{PIPE}tool name="run">\n'
    f'<{PIPE}DSML{PIPE}{PIPE}parameter name="command" string="true">id'
    f'</{PIPE}DSML{PIPE}{PIPE}parameter>\n</{PIPE}DSML{PIPE}{PIPE}tool>',
    'Prose.\n<invoke name="run">\n<parameter name="command">id</parameter>\n</invoke>',
    "just prose, no markup at all",
    "",
]
for s in _samples:
    once = C._normalise_tool_syntax(s)
    ck(f"idempotent on {s[:34]!r}...",
       C._normalise_tool_syntax(once) == once)


# ── 4. the GroqBackend landmine ──────────────────────────────────────
print("\n== GroqBackend constructs instead of raising NameError ==")
ck("GROQ_FALLBACK_CHAIN exists", hasattr(C, "GROQ_FALLBACK_CHAIN"))
try:
    _b = C.GroqBackend("sk-not-a-real-key")
    ck("GroqBackend(key) constructs", True)
    ck("…with a list chain, not an exception",
       isinstance(_b.fallback_chain, list))
    ck("…and an explicit chain still wins",
       C.GroqBackend("k", ["a", "b"]).fallback_chain == ["a", "b"])
except Exception as e:                                   # pragma: no cover
    ck("GroqBackend(key) constructs", False, f"{type(e).__name__}: {e}")
    ck("…with a list chain, not an exception", False)
    ck("…and an explicit chain still wins", False)

_errs = []
try:
    C.GroqBackend("sk-x").stream_chat(
        "", [], lambda t: None, lambda m: None, _errs.append)
    ck("an unconfigured chain reports a clear error, never NameError",
       len(_errs) == 1, str(_errs))
except Exception as e:
    ck("an unconfigured chain reports a clear error, never NameError",
       False, f"{type(e).__name__}: {e}")


print(f"\nboundary: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
