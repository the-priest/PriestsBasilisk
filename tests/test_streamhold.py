#!/usr/bin/env python3
"""
test_streamhold.py — the live stream must never paint text it is about to
delete, and must never draw a bubble for a step that says nothing.

THE REPORT
==========
    "when it searches it types in chat and it gets deleted bubble pops in
     and out"

Three symptoms, one cause.

Every stripper in basilisk_core answers "is this text a tool call?".  A stream
asks a different question: "could this text still BECOME one?".  Until a marker
is long enough to be RECOGNISED, its characters are ordinary text, and the
renderer painted them:

    <          <t         <to        <too       → then gone

…the instant `<tool ` completed and TOOL_PARTIAL_RE engaged.  Same for
`<invok`, `<fun`, `<thin`, `<|`.  That is symptom one (types) and symptom two
(deleted).

Symptom three followed from it.  The chat bubble is attached lazily on the
first token carrying visible TEXT, precisely so a tool-only step never draws an
empty bubble — but a leaked `<too` IS visible text by that test.  So a search
step attached a bubble, painted a fragment, lost it, and then hid itself as a
bare tool step: popped in, popped out.

THE RULE (and the counter-property that bounds it)
==================================================
Never emit a tail that could still turn into markup — hold it one frame.  The
counter-property matters as much: ordinary prose containing `<` must survive
untouched, and the hold must be STREAM-ONLY, because a FINISHED message ending
in "<t" is text and has to be shown.

Run:  python3 tests/test_streamhold.py
"""

from __future__ import annotations

import io
import os
import re
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import basilisk_core as C                                       # noqa: E402
from basilisk_core import (                                     # noqa: E402
    stream_visible_text, hold_partial_marker, strip_tool_calls,
    strip_think_blocks, scrub_tool_debris, _normalise_tool_syntax,
    _STREAM_MARKER_OPENERS)

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
FULLW = "｜"        # the DSML fullwidth pipe


def final_display(text: str) -> str:
    """What the FINISHED message renders as — MessageWidget.set_content's chain."""
    visible = C.extract_think_blocks(_normalise_tool_syntax(text))[0]
    return scrub_tool_debris(strip_tool_calls(visible)).rstrip()


# Every dialect the app claims to understand.  A leak in any one of them is the
# reported bug; testing only the canonical form is how it survived this long.
DIALECTS = {
    "canonical":
        '<tool name="web_search">{"query": "owasp top 10"}</tool>',
    "canonical_multiline":
        '<tool name="run">\n{"command": "nmap -sV 10.0.0.1"}\n</tool>',
    "dsml_ascii":
        '<||DSML||tool name="web_search">'
        '<parameter name="query">owasp</parameter></||DSML||tool>',
    "dsml_fullwidth":
        f'<{FULLW}DSML{FULLW}{FULLW}tool name="web_read">'
        f'<parameter name="url">https://example.org</parameter></tool>',
    "antml_invoke":
        '<invoke name="web_search">'
        '<parameter name="query">owasp</parameter></invoke>',
    "tool_call":
        '<tool_call name="web_read">{"url": "https://example.org"}</tool_call>',
    "function_eq":
        '<function=web_search>{"query":"owasp"}</function>',
    "think_block":
        '<think>I should search for this first.</think>The answer is 42.',
}

PREFIX = "Let me look that up.\n\n"


# ── 1. THE HEADLINE: character-by-character, nothing is ever un-painted ──
print("\n== a stream never shows text it will take back ==")
for _name, _call in DIALECTS.items():
    full = PREFIX + _call
    final = final_display(full)
    leaks = []
    for n in range(1, len(full) + 1):
        shown = stream_visible_text(full[:n]).rstrip()
        # The ONLY honest streaming invariant: everything on screen so far must
        # still be on screen at the end. Monotonic growth toward `final`.
        if not final.startswith(shown):
            leaks.append((n, shown))
    ck(f"no frame paints doomed text: {_name}",
       not leaks,
       f"{len(leaks)} leaking frames, first={leaks[0] if leaks else None!r}")

# The pre-fix behaviour, pinned so a regression is unmistakable: the OLD
# transform (no hold) really does leak, so the test above is not vacuous.
_old = strip_tool_calls(strip_think_blocks(PREFIX + '<tool name="x">{}</tool>'
                                           )[:len(PREFIX) + 4])
ck("the suite is not vacuous — the unheld transform leaks on the same input",
   "<" in strip_tool_calls(strip_think_blocks(PREFIX + "<too")),
   "the old path no longer leaks, so these assertions prove nothing")


# ── 2. COUNTER-PROPERTY: a hold that never releases is not a fix ──────
print("\n== ordinary prose is untouched ==")
PROSE = [
    "compare a < b and c > d",
    "the answer is 42.",
    "use <p> tags for paragraphs",
    "x<y",
    "if (a<b) { return; }",
    "See RFC 2616 <https://www.rfc-editor.org/rfc/rfc2616>",
    "Content-Type: application/json",
    "no angle brackets here at all",
    "5 < 10 and 10 > 5",
    "shell redirect: cat < input.txt",
]
for _t in PROSE:
    ck(f"unchanged: {_t[:40]}", stream_visible_text(_t) == _t.strip(),
       repr(stream_visible_text(_t)))

# A held fragment must be RELEASED as soon as the next character disproves it.
for frag, nxt in (("<t", "able>"), ("<i", "mage>"), ("<p", ">"), ("<f", "oo")):
    held = stream_visible_text("abc " + frag)
    released = stream_visible_text("abc " + frag + nxt)
    ck(f"'{frag}' is held then released by '{nxt}'",
       frag not in held and frag in released,
       f"held={held!r} released={released!r}")


# ── 3. THE HOLD IS STREAM-ONLY ───────────────────────────────────────
print("\n== a finished message ending in '<t' still shows it ==")
# "unclosed <think" is genuinely mid-flight markup and the FINAL renderer is
# right to drop it; "the tag is <t" and "trailing <" are prose and must survive
# a finished message intact. Both, in the STREAM, are held.
ck("a finished message keeps a trailing '<t'",
   final_display("the tag is <t") == "the tag is <t",
   repr(final_display("the tag is <t")))
ck("a finished message keeps a trailing '<'",
   final_display("trailing <") == "trailing <",
   repr(final_display("trailing <")))
for _t in ("the tag is <t", "unclosed <think", "trailing <"):
    ck(f"but the stream holds it: {_t!r}",
       len(stream_visible_text(_t)) < len(_t.strip()),
       repr(stream_visible_text(_t)))
ck("hold_partial_marker is NOT wired into strip_tool_calls",
   "hold_partial_marker" not in io.open(
       os.path.join(_ROOT, "basilisk_core.py"),
       encoding="utf-8").read().split("def strip_tool_calls")[1]
   .split("\ndef ")[0],
   "folding the hold into the shared stripper would eat real text")


# ── 4. THE OPENER TABLE AGREES WITH THE STRIPPERS ────────────────────
# The hold list and the recognisers are two consumers of one fact. This file
# has shipped that exact shape of bug before (parse vs strip, display vs
# speech), so assert the agreement rather than trusting it.
print("\n== every opener the strippers know is in the hold table ==")
for _op in ("<tool", "<tool_call", "<toolcall", "<function_call",
            "<function=", "<invoke", "<think", "<parameter", "<|",
            "<" + FULLW):
    ck(f"hold table covers {_op!r}", _op in _STREAM_MARKER_OPENERS)

# And each one, arriving one character at a time, is held the whole way.
for _op in _STREAM_MARKER_OPENERS:
    partials_held = all(
        hold_partial_marker("text " + _op[:k]) == "text "
        for k in range(1, len(_op) + 1))
    ck(f"held through every prefix of {_op!r}", partials_held)


# ── 5. THE BUBBLE DECISION USES THE SAME FUNCTION ────────────────────
# Symptom three was a SECOND consumer asking the same question a worse way
# ("did a token arrive?"). If these ever diverge again the bubble comes back.
print("\n== the bubble attaches on visible text, not on any token ==")
ck("_on_stream_token no longer attaches unconditionally",
   not re.search(r"self\._attach_streaming_bubble\(\)\s*\n\s*"
                 r"self\.streaming_msg_widget\.append_streaming", SRC),
   "attach still runs before anything is known about the token")
ck("…it asks stream_visible_text instead",
   re.search(r"if stream_visible_text\(\s*\n?\s*"
             r"self\.streaming_msg_widget\._content or \"\"\)\.strip\(\):"
             r"\s*\n\s*self\._attach_streaming_bubble\(\)", SRC) is not None)
ck("the renderer uses the same one transform",
   "self._streaming_label.set_text(stream_visible_text(self._content))" in SRC)
ck("a propose card can still reach the screen",
   "_will_show = self.streaming_msg_widget.get_visible()" in SRC,
   "an empty-text propose turn would render its approval card into a "
   "bubble nobody ever attached")


# ── 6. COST ──────────────────────────────────────────────────────────
# This runs on every streamed frame over the whole buffer. The window is
# bounded, so the hold must be O(1) in reply length, not O(n).
print("\n== the hold is constant-cost in reply length ==")


def _ms(fn, n):
    s = "word " * n
    t0 = time.perf_counter()
    for _ in range(200):
        fn(s)
    return (time.perf_counter() - t0) * 1000 / 200


small = _ms(hold_partial_marker, 100)
big = _ms(hold_partial_marker, 12800)      # 128x the text
ck(f"128x the reply is not 128x the cost ({small:.4f}ms -> {big:.4f}ms)",
   big < max(small * 8, 0.05),
   "the hold is scanning the whole buffer")

# Pathological input: thousands of unterminated openers, the shape that has
# frozen this file's regexes twice before.
evil = "<tool " * 4000
t0 = time.perf_counter()
stream_visible_text(evil)
el = (time.perf_counter() - t0) * 1000
ck(f"4000 unterminated openers in {el:.1f}ms", el < 500.0)


print(f"\nstream hold: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
