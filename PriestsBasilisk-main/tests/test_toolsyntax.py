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
import re
import random
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


# ── 9. DSML: DeepSeek-V4's tag dialect ───────────────────────────────
# THE SECOND REPORTED FAILURE, same class as the first but a different member.
# The operator asked for a Steam recommendation; the chat filled with
# `<｜DSML｜｜tool name="run">` / `<｜DSML｜｜parameter name="url" …>` and the
# log alternated between "syntax this build doesn't parse" and tool calls that
# ran with `{"_raw": "<｜DSML｜｜parameter …"}` as their arguments.
#
# Two distinct breakages produced that one screen, and they are tested apart
# because only one of them is visible:
#
#   A. sentinel on the OPENER  → TOOL_TAG_RE never matched → nothing ran and
#      nothing was stripped, so the markup was printed as chat text.
#   B. sentinel only on the CHILDREN → the tag matched, the body was not JSON,
#      and the arguments became {"_raw": …}.  The tool then ran with no url at
#      all.  THIS IS THE DANGEROUS ONE: it reports success, so the loop never
#      learns it got nothing and retries the same shape until the budget dies.
#   C. good JSON with a stray `</｜DSML｜｜invoke>` glued after it — a whole
#      valid object thrown away over a trailing tag.
print("\n== DSML dialect (DeepSeek-V4) ==")


def dsml(tag, attrs=""):
    return f"<{PIPE}DSML{PIPE}{PIPE}{tag}{attrs}>"


def dsml_close(tag):
    return f"</{PIPE}DSML{PIPE}{PIPE}{tag}>"


_A = ("Checking the Steam API.\n"
      + dsml("tool", ' name="run"') + "\n"
      + dsml("parameter", ' name="command" string="true"')
      + 'curl -s "https://store.steampowered.com/api/appdetails?appids=221910"'
      + dsml_close("parameter") + "\n"
      + dsml("parameter", ' name="reason" string="true"')
      + "Verify genre candidates" + dsml_close("parameter") + "\n"
      + dsml_close("invoke") + "\n" + dsml_close("tool"))

_c = parse_tool_calls(_A)
ck("A: sentinel on the opener still parses", len(_c) == 1, str(len(_c)))
ck("A: correct tool name", _c and _c[0].name == "run",
   _c[0].name if _c else "-")
ck("A: command survives byte-for-byte",
   _c and _c[0].args.get("command") ==
   'curl -s "https://store.steampowered.com/api/appdetails?appids=221910"',
   str(_c[0].args) if _c else "-")
ck("A: second parameter also decoded",
   _c and _c[0].args.get("reason") == "Verify genre candidates",
   str(_c[0].args) if _c else "-")
ck("A: no _raw fallback", _c and "_raw" not in _c[0].args,
   str(_c[0].args) if _c else "-")
ck("A: operator sees the prose only", strip_tool_calls(_A) == "Checking the "
   "Steam API.", repr(strip_tool_calls(_A)))

_B = ('<tool name="web_read">\n'
      + dsml("parameter", ' name="url" string="true"')
      + "https://www.bing.com/search?q=steam+games" + dsml_close("parameter")
      + "\n" + dsml_close("invoke") + "\n</tool>")
_c = parse_tool_calls(_B)
ck("B: sentinel on the children only still parses", len(_c) == 1, str(len(_c)))
ck("B: url is the real url, not _raw",
   _c and _c[0].args.get("url") == "https://www.bing.com/search?q=steam+games",
   str(_c[0].args) if _c else "-")
ck("B: the exact log line no longer reproduces",
   _c and not str(_c[0].args).startswith("{'_raw'"),
   str(_c[0].args) if _c else "-")

_C = ('<tool name="web_read">{"url": "https://html.duckduckgo.com/html/?q=x"}\n'
      + dsml_close("invoke") + "\n</tool>")
_c = parse_tool_calls(_C)
ck("C: valid JSON with a trailing dialect tag is recovered",
   _c and _c[0].args.get("url") == "https://html.duckduckgo.com/html/?q=x",
   str(_c[0].args) if _c else "-")

# The plain (sentinel-free) child-tag dialect — same decoder, and the shape
# other models emit.
_D = ('<invoke name="web_read">\n'
      '<parameter name="url">https://example.com</parameter>\n'
      '</invoke>')
_c = parse_tool_calls(_D)
ck("plain <parameter> children decode too",
   _c and _c[0].args.get("url") == "https://example.com",
   str(_c[0].args) if _c else "-")

# Value typing.  string="true" is the model saying "this is text" — an id or a
# version that happens to look numeric must not silently become an int.
_E = ('<tool name="run">'
      '<parameter name="a" string="true">221910</parameter>'
      '<parameter name="b">7</parameter>'
      '<parameter name="c">true</parameter>'
      '<parameter name="d">plain words</parameter>'
      '<parameter name="e">{"k": 1}</parameter>'
      '<parameter name="f">2 &lt; 3 &amp;&amp; 4 &gt; 1</parameter>'
      "</tool>")
_a = parse_tool_calls(_E)[0].args
ck("string=\"true\" keeps a numeric-looking value as text", _a.get("a") == "221910",
   repr(_a.get("a")))
ck("a bare integer becomes an int", _a.get("b") == 7, repr(_a.get("b")))
ck("a bare boolean becomes a bool", _a.get("c") is True, repr(_a.get("c")))
ck("a bare word stays a string", _a.get("d") == "plain words", repr(_a.get("d")))
ck("a JSON object value is parsed", _a.get("e") == {"k": 1}, repr(_a.get("e")))
ck("XML entities are unescaped", _a.get("f") == "2 < 3 && 4 > 1",
   repr(_a.get("f")))
ck("a semicolon-less entity is NOT touched (shell commands must survive)",
   parse_tool_calls('<tool name="run"><parameter name="x">curl '
                    "'a&copy=1'</parameter></tool>")[0].args.get("x")
   == "curl 'a&copy=1'")

# The parameter decoder must never take over a body that was always JSON.
_F = '<tool name="run">{"command": "ls", "reason": "list the parameter dir"}</tool>'
_a = parse_tool_calls(_F)[0].args
ck("a JSON body mentioning 'parameter' is still parsed as JSON",
   _a.get("command") == "ls", str(_a))

# An undecodable call must be DROPPED, not run with markup as its arguments.
# Running it reports "done", returns nothing, and the loop repeats forever.
_G = '<tool name="web_read"><parameter>no name attribute</parameter></tool>'
ck("a call whose arguments are undecoded markup is not dispatched",
   len(parse_tool_calls(_G)) == 0, str(parse_tool_calls(_G)))
ck("…and the host can still see it was a failed call",
   looks_like_failed_tool_call(_G))
# but merely MALFORMED JSON is still passed through as before
_H = '<tool name="propose_edit">{"path": "/tmp/x", "content": broken</tool>'
ck("malformed JSON still yields a call (not newly discarded)",
   len(parse_tool_calls(_H)) == 1, str(parse_tool_calls(_H)))

# Nothing leaks while a DSML call is still arriving.
_leaks = 0
_buf = ""
for _ch in _A:
    _buf += _ch
    _vis = scrub_tool_debris(strip_tool_calls(_buf))
    if any(_m in _vis for _m in
           (PIPE, "DSML", "parameter", "tool name=", "<invoke", "<tool")):
        _leaks += 1
ck(f"DSML never renders mid-stream ({_leaks} leaking frames)", _leaks == 0)

ck("DSML normalisation is idempotent",
   _normalise_tool_syntax(_normalise_tool_syntax(_A))
   == _normalise_tool_syntax(_A))
ck("a successfully decoded DSML call leaves no debris",
   not looks_like_failed_tool_call(strip_tool_calls(_A)),
   repr(strip_tool_calls(_A)))

# Robustness: the sentinel's pipe count varies with how the special token is
# rendered, and the slash can sit either side of it on a closing tag.
for _v in (f"<{PIPE}DSML{PIPE}tool name=\"run\">{{}}</{PIPE}DSML{PIPE}tool>",
           f"<{PIPE}{PIPE}DSML{PIPE}{PIPE}tool name=\"run\">{{}}"
           f"</{PIPE}{PIPE}DSML{PIPE}{PIPE}tool>",
           f"<{PIPE}DSML{PIPE}{PIPE}/tool>"):
    try:
        parse_tool_calls(_v)
        strip_tool_calls(_v)
        _ok = True
    except Exception as _e:                                     # pragma: no cover
        _ok = False
        print("      ", type(_e).__name__, _e)
    ck(f"survives sentinel variant {_v[:26]!r}", _ok)

ck("one-pipe sentinel still parses",
   len(parse_tool_calls(f'<{PIPE}DSML{PIPE}tool name="run">'
                        f'{{"command":"ls"}}</{PIPE}DSML{PIPE}tool>')) == 1)

for _n in (dsml("tool", ' name="run"') * 300,
           dsml("parameter", ' name="x"') + "y" * 50_000,
           "<" + PIPE + "DSML" + PIPE * 400,
           dsml("parameter", ' name="x"') + "</" + PIPE + "DSML"):
    try:
        parse_tool_calls(_n)
        strip_tool_calls(_n)
        scrub_tool_debris(_n)
        looks_like_failed_tool_call(_n)
        _ok = True
    except Exception as _e:                                     # pragma: no cover
        _ok = False
        print("      ", type(_e).__name__, _e)
    ck(f"survives nasty DSML {_n[:24]!r}", _ok)

_t0 = time.monotonic()
parse_tool_calls(_A * 300)
_el = time.monotonic() - _t0
ck(f"300 DSML calls parse fast ({_el*1000:.0f}ms)", _el < 2.0)

# The paired `<parameter …>(.*?)</parameter>` form this decoder started life as
# was QUADRATIC when openers outnumbered closers — 5000 unclosed openers took
# 2.06s, on the UI thread, on every streamed frame.  Pinned as a number, not a
# comment, because the paired form is the obvious way to write it and someone
# (me) will reach for it again.
for _label, _s in (
        ("5000 unclosed openers",
         '<tool name="run">' + '<parameter name="x">' * 5000),
        ("5000 openers, one closer",
         '<tool name="run">' + '<parameter name="x">' * 5000 + "</parameter>"),
        ("5000 complete parameters",
         '<tool name="run">' + '<parameter name="x">v</parameter>' * 5000
         + "</tool>"),
        ("400KB parameter value",
         '<tool name="run"><parameter name="x">' + "y" * 400_000
         + "</parameter></tool>")):
    _t0 = time.monotonic()
    parse_tool_calls(_s)
    strip_tool_calls(_s)
    _el = time.monotonic() - _t0
    ck(f"{_label} stays linear ({_el*1000:.0f}ms)", _el < 0.5)

# Correctness of the lockstep walk, which is easier to get subtly wrong than
# the regex it replaced.
_a = parse_tool_calls('<tool name="run"><parameter name="a">1</parameter>'
                      'junk between<parameter name="b">2</parameter>'
                      "</tool>")[0].args
ck("parameters separated by junk both decode", _a == {"a": 1, "b": 2}, str(_a))
_c = parse_tool_calls('<tool name="run"><parameter name="a">1</parameter>'
                      '<parameter name="b">truncated mid-val')
ck("a truncated trailing parameter is dropped, earlier ones kept",
   _c and _c[0].args == {"a": 1}, str(_c[0].args) if _c else "-")


# ── 10. NO QUADRATIC BLOWUP ON REPEATED OPENERS ──────────────────────
# Found while fixing the DSML bug, and worse than the bug that found it.
#
# The display path used tempered-dot regexes of the form
# `<open …>(?:(?!</close>).)*$` to hide a call that had not finished arriving.
# That costs a lookahead per character per starting position, and re.sub tries
# every position. On 3000 repeated `<tool_call name="x">` openers followed by
# ONE `</tool_call>` it took:
#
#     24,972 ms.
#
# strip_tool_calls runs on EVERY streamed frame, on the GTK main thread, with
# no cancellation — so that is a hard freeze, multiplied by the frame count.
#
# And the trigger is not exotic. A model stuck repeating itself is a KNOWN
# Basilisk failure mode (v9.1.0 shipped a repeat guard for it), and a
# repetitive model repeats whatever it was last emitting — which, right after
# a tool call fails to parse, is a tool-call opener. The two bugs compose:
# unparsed dialect → model retries → repetition → freeze.
#
# The paired `<open>(.*?)</close>` subs had the same shape for the opposite
# input (openers with NO closer): 1,475 ms for the dialect sub, 434 ms for
# THINK_RE.
#
# Numbers, not adjectives — the tempered form is the obvious way to write this
# and someone will reach for it again.
print("\n== no quadratic blowup on repeated openers ==")
_N = 3000
_PATHOLOGICAL = {
    "3000 tool_call openers, no closer": '<tool_call name="x">' * _N,
    "3000 tool_call openers + one closer":
        '<tool_call name="x">' * _N + "</tool_call>",
    "3000 invoke openers + one closer":
        '<invoke name="x">' * _N + "</invoke>",
    "3000 function= openers + one closer": "<function=x>" * _N + "</function>",
    "3000 think openers, no closer": "<think>" * _N,
    "3000 think openers + one closer": "<think>" * _N + "</think>",
    "3000 parameter openers, no closer": '<parameter name="x">' * _N,
    "mixed hostile reply":
        "prose " + "<think>" * 1000 + '<parameter name="x">' * 1000
        + '<tool_call name="x">' * 1000 + "</tool_call>",
}
from basilisk_core import extract_think_blocks                  # noqa: E402
for _label, _s in _PATHOLOGICAL.items():
    _t0 = time.monotonic()
    parse_tool_calls(_s)
    strip_tool_calls(_s)
    extract_think_blocks(_s)
    scrub_tool_debris(_s)
    looks_like_failed_tool_call(_s)
    _el = time.monotonic() - _t0
    ck(f"{_label}: {_el*1000:.0f}ms", _el < 0.5,
       "this ran for 25 SECONDS on the main thread before the linear rewrite")


# ── 11. THE LINEAR REWRITE MAKES THE SAME DECISION ───────────────────
# A faster function that answers differently is not a fix. _cut_unclosed
# replaces a regex, so it is checked AGAINST that regex on every input the
# regex was fast enough to answer — the same discipline as pinning the old
# sort alongside the new one in test_models.py.
print("\n== the linear cut agrees with the regex it replaced ==")
from basilisk_core import (                                     # noqa: E402
    _cut_unclosed, _ALT_OPEN_RE, _ALT_CLOSE_RE, _FUNC_OPEN_RE, _FUNC_CLOSE_RE)

_OLD_ALT = re.compile(
    r"<\s*(?:tool_call|toolcall|function_call|invoke|antml:invoke)\b[^>]*>?"
    r"(?:(?!</\s*(?:tool_call|toolcall|function_call|invoke|antml:invoke)"
    r"\s*>).)*$", re.S | re.I)
_OLD_FUNC = re.compile(r"<\s*function\s*=(?:(?!<\s*/\s*function\s*>).)*$",
                       re.S | re.I)

_FRAG = ['<tool_call name="x">', "</tool_call>", '<invoke name="y">',
         "</invoke>", "prose ", "<function=z>", "</function>", "<toolcall>",
         '{"a":1}', "\n", "<", ">", "</ invoke >", '<function_call name="k">',
         "</function_call>", ""]
random.seed(5)
_diff = 0
for _i in range(40000):
    _s = "".join(random.choice(_FRAG) for _ in range(random.randint(1, 9)))
    if (_OLD_ALT.sub("", _s) != _cut_unclosed(_s, _ALT_OPEN_RE, _ALT_CLOSE_RE)
            or _OLD_FUNC.sub("", _s)
            != _cut_unclosed(_s, _FUNC_OPEN_RE, _FUNC_CLOSE_RE)):
        _diff += 1
        if _diff < 4:
            print("      DIFF", repr(_s)[:100])
ck(f"40000 random inputs, {_diff} disagreements with the old regex", _diff == 0)

# The specific decisions, spelled out rather than left to the fuzzer.
ck("a complete call is left alone",
   _cut_unclosed('<invoke name="x">{}</invoke> after',
                 _ALT_OPEN_RE, _ALT_CLOSE_RE)
   == '<invoke name="x">{}</invoke> after')
ck("an unclosed trailing opener is cut",
   _cut_unclosed('done. <invoke name="x">{"url"',
                 _ALT_OPEN_RE, _ALT_CLOSE_RE) == "done. ")
ck("the cut starts at the FIRST unclosed opener, not the last",
   _cut_unclosed('a<invoke name="x">b<invoke name="y">c',
                 _ALT_OPEN_RE, _ALT_CLOSE_RE) == "a")
ck("openers before the last closer are not cut",
   _cut_unclosed('<invoke name="x">b</invoke>tail',
                 _ALT_OPEN_RE, _ALT_CLOSE_RE) == '<invoke name="x">b</invoke>tail')
ck("no opener at all changes nothing",
   _cut_unclosed("just prose", _ALT_OPEN_RE, _ALT_CLOSE_RE) == "just prose")
ck("empty input is safe",
   _cut_unclosed("", _ALT_OPEN_RE, _ALT_CLOSE_RE) == "")


print(f"\ntoolsyntax: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
