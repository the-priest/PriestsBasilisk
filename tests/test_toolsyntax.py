#!/usr/bin/env python3
"""
test_toolsyntax.py — the host must understand the model's tool calls, and must
never fail silently when it doesn't.

THE REPORTED FAILURE
====================
On screen: pipes, boxes and the word `name="web_read"` printed as text, the
model apologising for "malformed calls", and the turn ending without doing the
work. It looked like the model was broken. It was not.

`TOOL_TAG_RE` matched exactly ONE dialect, `<tool name=...>`. Everything else
parsed to zero calls — which meant the text was neither executed NOR stripped,
so it leaked to the screen as raw protocol garbage and the turn ended with
nothing to run.

The worst offender was the model's OWN native format. DeepSeek emits function
calls as special tokens built from FULLWIDTH VERTICAL LINE (U+FF5C) and LOWER
ONE EIGHTH BLOCK (U+2581) — which is precisely why the screenshot is full of
pipe glyphs. The model was using its trained syntax; the host only spoke one
dialect and had no way to say so.

So two things are tested here:
  1. every dialect seen in the wild NORMALISES to a real call, and
  2. anything that still doesn't parse is DETECTED, so the host can ask the
     model to re-send instead of stopping — fixing the class, not one member.

Run:  python3 tests/test_toolsyntax.py
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from basilisk_core import (                                    # noqa: E402
    parse_tool_calls, strip_tool_calls, looks_like_failed_tool_call,
    scrub_tool_debris, _normalise_tool_syntax)

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


PIPE = "\uff5c"     # ｜
SEP = "\u2581"      # ▁


def ds_call(name, body, wrapped=True):
    inner = (f"<{PIPE}tool{SEP}call{SEP}begin{PIPE}>function"
             f"<{PIPE}tool{SEP}sep{PIPE}>{name}\n```json\n{body}\n```"
             f"<{PIPE}tool{SEP}call{SEP}end{PIPE}>")
    if wrapped:
        return (f"<{PIPE}tool{SEP}calls{SEP}begin{PIPE}>{inner}"
                f"<{PIPE}tool{SEP}calls{SEP}end{PIPE}>")
    return inner


# ── 1. every dialect parses ──────────────────────────────────────────
print("== dialects parse ==")
CASES = {
    "canonical": '<tool name="web_read">{"url": "https://x"}</tool>',
    "deepseek native tokens": ds_call("web_read", '{"url": "https://x"}'),
    "deepseek unwrapped": ds_call("web_read", '{"url": "https://x"}', False),
    "tool_call tag": '<tool_call name="web_read">{"url": "https://x"}</tool_call>',
    "toolcall tag": '<toolcall name="web_read">{"url": "https://x"}</toolcall>',
    "function_call tag":
        '<function_call name="web_read">{"url": "https://x"}</function_call>',
    "invoke tag": '<invoke name="web_read">{"url": "https://x"}</invoke>',
    "function=name": '<function=web_read>{"url": "https://x"}</function>',
    "fenced json body":
        '<tool_call name="web_read">```json\n{"url": "https://x"}\n```</tool_call>',
}
for label, raw in CASES.items():
    calls = parse_tool_calls(raw)
    ck(f"{label}: parses to one call", len(calls) == 1, str(len(calls)))
    if calls:
        ck(f"{label}: correct tool name", calls[0].name == "web_read",
           calls[0].name)
        ck(f"{label}: correct args",
           calls[0].args.get("url") == "https://x", str(calls[0].args))

# the exact shape from the bug report: two calls in one reply
_two = ("Doing it properly now:\n"
        + ds_call("web_read", '{"url": "https://a"}')
        + "\n" + ds_call("web_read", '{"url": "https://b"}'))
_c = parse_tool_calls(_two)
ck("two native calls in one reply both parse", len(_c) == 2, str(len(_c)))
ck("both carry their own url",
   len(_c) == 2 and {x.args.get("url") for x in _c} == {"https://a", "https://b"},
   str([x.args for x in _c]))


# ── 2. normalisation is CONSERVATIVE ─────────────────────────────────
# A false rewrite executes something the model meant as prose. That is much
# worse than a miss, because the backstop below recovers a miss.
print("\n== does not rewrite prose ==")
SAFE = [
    "Use the <tool> element in your HTML? No such thing.",
    "Compare a < b and c > d in that function=x expression",
    "I'd run `nmap -p- host` — see the docs for <function> syntax",
    "The name=\"x\" attribute is how HTML does it",
    "```python\nprint('<tool name=\"fake\">')\n```",
    "",
    "plain prose with no angle brackets at all",
]
for txt in SAFE:
    ck(f"no call invented from: {txt[:40]!r}",
       len(parse_tool_calls(txt)) == 0, str(parse_tool_calls(txt)))

ck("normalising leaves ordinary text untouched",
   _normalise_tool_syntax("hello world") == "hello world")
ck("normalising is idempotent",
   _normalise_tool_syntax(_normalise_tool_syntax(CASES["deepseek native tokens"]))
   == _normalise_tool_syntax(CASES["deepseek native tokens"]))
ck("a dialect tag with NO name is left alone (can't guess it)",
   len(parse_tool_calls('<tool_call>{"url":"x"}</tool_call>')) == 0)


# ── 3. the backstop detects what normalisation misses ────────────────
print("\n== unparsed debris is detected ==")
DEBRIS = [
    f"<{PIPE}tool{SEP}call{SEP}begin{PIPE}>something entirely new",
    '<tool_use name="web_read">{}</tool_use>',
    'blah <tool name="run"',
    'name="web_read">{"url":"x"}',
    "<function=mystery>",
    "</tool>",
]
for d in DEBRIS:
    ck(f"detected: {d[:38]!r}", looks_like_failed_tool_call(d))

CLEAN = [
    "Here is the answer: the service was not running.",
    "I checked three sources and they agree.",
    "",
    "a < b and c > d",
    "Set name to web_read in the config",
]
for c in CLEAN:
    ck(f"no false alarm: {c[:38]!r}", not looks_like_failed_tool_call(c))

# A reply that parsed FINE must not also look like debris after stripping —
# otherwise every successful tool turn would trigger the recovery.
_ok = strip_tool_calls(_normalise_tool_syntax(CASES["canonical"]))
ck("a successfully parsed call leaves no debris",
   not looks_like_failed_tool_call(_ok), repr(_ok))


# ── 4. the operator never sees protocol garbage ──────────────────────
print("\n== display is scrubbed ==")
_junk = "Reading the sources now.\n" + ds_call("web_read", '{"url":"x"}')
_shown = scrub_tool_debris(strip_tool_calls(_junk))
ck("prose survives scrubbing", "Reading the sources now." in _shown)
ck("fullwidth control tokens removed", PIPE not in _shown, repr(_shown))
ck("no stray tag text remains",
   "tool_call" not in _shown and "<tool" not in _shown, repr(_shown))
ck("scrubbing plain prose changes nothing",
   scrub_tool_debris("just an answer") == "just an answer")
ck("scrubbing empty is safe", scrub_tool_debris("") == "")
ck("scrubbing None-ish is safe", scrub_tool_debris(None) is None)


# ── 5. robustness ────────────────────────────────────────────────────
print("\n== robustness ==")
NASTY = [
    "<" * 500,
    PIPE * 200,
    ds_call("web_read", "not json at all"),
    ds_call("", "{}"),
    "<tool_call name=\"x\">" + "{" * 200 + "</tool_call>",
    f"<{PIPE}tool{SEP}sep{PIPE}>",
    "\x00<tool name=\"run\">{}</tool>",
    "🙂" * 100,
]
for n in NASTY:
    try:
        parse_tool_calls(n)
        _normalise_tool_syntax(n)
        looks_like_failed_tool_call(n)
        scrub_tool_debris(n)
        ok = True
    except Exception as e:                                      # pragma: no cover
        ok = False
        print("      ", type(e).__name__, e)
    ck(f"survives {n[:22]!r}", ok)

# An unterminated native call must not swallow the rest of the reply — the
# same swallow-bug shape that was found in the scope gate.
_unterm = (f"<{PIPE}tool{SEP}call{SEP}begin{PIPE}>function"
           f"<{PIPE}tool{SEP}sep{PIPE}>web_read\n{{\"url\":\"x\"}}")
_r = parse_tool_calls(_unterm)
ck("unterminated native call still yields the call", len(_r) == 1, str(len(_r)))

import time                                                     # noqa: E402
_big = ds_call("web_read", '{"url":"x"}') * 400
_t0 = time.monotonic()
parse_tool_calls(_big)
_el = time.monotonic() - _t0
ck(f"400 calls parse fast ({_el*1000:.0f}ms)", _el < 2.0)

_t0 = time.monotonic()
looks_like_failed_tool_call("a" * 400_000)
ck(f"debris check on 400KB is fast ({(time.monotonic()-_t0)*1000:.0f}ms)",
   time.monotonic() - _t0 < 1.0, "no catastrophic backtracking")


# ── 6. NOTHING LEAKS WHILE IT IS STILL STREAMING ─────────────────────
# The end state being correct is not enough. A reply arrives token by token and
# is rendered on every token, so a call is visible as raw text from the moment
# it starts until the moment it closes. Replaying the reported reply character
# by character showed 61 of 176 frames printing protocol text — which is what
# the operator actually watched happen. Fixing only the final message would
# have left the visible symptom completely intact.
print("\n== nothing leaks mid-stream ==")
from basilisk_core import strip_think_blocks                    # noqa: E402

_LEAK_MARKERS = (PIPE, SEP, '"url"', "tool name=", "tool_call", "<invoke",
                 "function=", "```json")

_STREAM_CASES = {
    "deepseek native": "Reading.\n" + ds_call("web_read", '{"url":"https://x"}'),
    "canonical": 'Reading.\n<tool name="web_read">{"url":"https://x"}</tool>',
    "tool_call": 'Reading.\n<tool_call name="web_read">{"url":"https://x"}</tool_call>',
    "invoke": 'Reading.\n<invoke name="web_read">{"url":"https://x"}</invoke>',
    "function=": 'Reading.\n<function=web_read>{"url":"https://x"}</function>',
}
for _label, _reply in _STREAM_CASES.items():
    _leaks, _worst, _buf = 0, "", ""
    for _ch in _reply:
        _buf += _ch
        _d = strip_tool_calls(strip_think_blocks(_buf))
        if any(_m in _d for _m in _LEAK_MARKERS):
            _leaks += 1
            if len(_d) > len(_worst):
                _worst = _d
    ck(f"{_label}: zero leaked frames while streaming", _leaks == 0,
       f"{_leaks} frames, worst={_worst[:60]!r}")
    ck(f"{_label}: prose still visible mid-stream",
       strip_tool_calls("Reading.\n").strip() == "Reading.")
    ck(f"{_label}: final text is the prose only",
       strip_tool_calls(_reply).strip() == "Reading.",
       repr(strip_tool_calls(_reply)))
    ck(f"{_label}: still parses to a real call",
       len(parse_tool_calls(_reply)) == 1)


# ── 7. PARSE AND STRIP MUST AGREE ────────────────────────────────────
# The invariant that was broken: parse normalised dialects, strip did not. So a
# native call EXECUTED (parse saw it) and SURVIVED stripping (strip did not) —
# the raw tokens went to the screen AND into the stored message, which then
# re-sent the garbage to the model as history on every later turn.
print("\n== parse and strip see the same text ==")
for _label, _raw in CASES.items():
    _stripped = strip_tool_calls(_raw)
    ck(f"{_label}: stripping removes what parsing consumed",
       not any(_m in _stripped for _m in
               (PIPE, SEP, "tool_call", "<invoke", "function=", "tool name=")),
       repr(_stripped[:70]))

_mixed = ("before " + CASES["deepseek native tokens"] + " middle "
          + CASES["invoke tag"] + " after")
ck("mixed dialects in one reply: both parse",
   len(parse_tool_calls(_mixed)) == 2, str(len(parse_tool_calls(_mixed))))
_ms = strip_tool_calls(_mixed)
ck("mixed dialects: prose survives",
   "before" in _ms and "middle" in _ms and "after" in _ms, repr(_ms))
ck("mixed dialects: no protocol text survives",
   not any(_m in _ms for _m in (PIPE, SEP, "<invoke", "tool name=")), repr(_ms))


# ── 8. ORDINARY PROSE IS NOT MANGLED ─────────────────────────────────
print("\n== prose with angle brackets is untouched ==")
for _t in ["Here is the answer: the service was not running.",
           "if a < b and c > d then x",
           "Use the <div> element, not <span>.",
           "Compare a<b, and note x > y in the function=f(x) form",
           "**bold** and <https://example.com> autolink",
           'run: grep -o "<[^>]*>" file.html']:
    ck(f"unchanged: {_t[:34]!r}", strip_tool_calls(_t).strip() == _t.strip(),
       repr(strip_tool_calls(_t)))


print(f"\ntoolsyntax: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
