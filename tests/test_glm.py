#!/usr/bin/env python3
"""
test_glm.py — everything that is specific to running Basilisk on GLM-5.3-Flash.

Four seams, each of which was broken and each of which the existing suites
could not see:

  1. THE JSON-BODIED <tool_call>.  GLM's chat template usually emits
     <arg_key>/<arg_value> pairs, which the host already understood.  Under a
     forced call — and, per vLLM issue #48095, intermittently in ordinary
     agentic use — it instead writes an OpenAI-shaped JSON body inside the same
     wrapper, sometimes as an array, sometimes with no closing tag.  The
     name-before-<arg_key> rule saw a JSON blob where an identifier should be,
     left the block alone, and the call then neither RAN nor got STRIPPED: raw
     JSON printed into the chat, stored in chats.db, replayed as history.

  2. THE ORPHANED </think>.  GLM's thinking cannot be disabled and its template
     opens the <think> block in the GENERATION PROMPT, so the model's own
     output starts inside the reasoning and emits only the closer.  Every
     consumer here is paired-tag based, so nothing matched: the chain of
     thought was shown as the reply, the literal </think> was rendered, and TTS
     read the reasoning out loud.

  3. reasoning_effort.  GLM-5.3-Flash's card says the field is low|high|max and
     "defaults to max if not passed (or if set to any other value)".  Omitting
     it is therefore a CHOICE — the deepest and slowest one — and the pill's
     Low rung (the shipped default) omitted it.

  4. THE WALL-CLOCK CUT.  STREAM_MAX_WALL_S ends a runaway turn, which a
     deep-reasoning model is the thing most likely to trigger, and the cut was
     reported to nobody: finish_reason stayed empty, `truncated` came out
     False, and an unfinished reply was stored as a finished one.

Counter-properties are asserted as hard as the properties: prose must not be
parsed as a call, a reply that merely MENTIONS </think> must not be split, and
none of it may cost text on screen or turn linear work quadratic.

Run:  python3 tests/test_glm.py
"""
from __future__ import annotations

import json
import os
import random
import re
import string
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import basilisk_core as C                                      # noqa: E402
from basilisk_core import (                                    # noqa: E402
    parse_tool_calls, strip_tool_calls, speakable_text,
    extract_think_blocks, reasoning_extra, reasoning_effort_enum,
    supports_reasoning_effort)

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


GLM53 = "zai-org/GLM-5.3-Flash"

# Anything in this shape reaching the operator's screen is the bug.
_PROTOCOL = re.compile(
    r"<\s*/?\s*(?:tool_call|toolcall|tool_calls|arg_key|arg_value|tool\b"
    r"|parameter|invoke|function)|\"(?:name|arguments|parameters)\"\s*:",
    re.I)


# ═════════════════════════════════════════════════════════════════════
# 1. THE JSON-BODIED <tool_call>
# ═════════════════════════════════════════════════════════════════════
print("\n== GLM <tool_call> with a JSON body ==")

# The exact string vLLM #48095 records GLM 5.x emitting into `content`.
_vllm = ('<tool_call>[{"name": "run", "parameters": '
         '{"command": "cd /tmp/repo && git status", '
         '"description": "Run git status"}}]</tool_call>')
_c = parse_tool_calls(_vllm)
ck("vLLM #48095 array form parses to one call",
   len(_c) == 1 and _c[0].name == "run", str([(x.name, x.args) for x in _c]))
ck("…and its arguments survive intact",
   _c and _c[0].args.get("command") == "cd /tmp/repo && git status",
   str(_c[0].args if _c else None))
ck("…and nothing of it reaches the screen",
   not _PROTOCOL.search(strip_tool_calls(_vllm)),
   repr(strip_tool_calls(_vllm)))

# The SAME shape with no closing tag — also verbatim from that issue.
_unclosed = ('<tool_call>[{"name": "run", "parameters": '
             '{"command": "git status"}}]')
_c = parse_tool_calls(_unclosed)
ck("an UNCLOSED <tool_call> with a complete JSON body still parses",
   len(_c) == 1 and _c[0].args.get("command") == "git status",
   str([(x.name, x.args) for x in _c]))
ck("…and leaves no debris on screen",
   strip_tool_calls(_unclosed).strip() == "",
   repr(strip_tool_calls(_unclosed)))

for _label, _body in (
        ("arguments", '{"name": "run", "arguments": {"command": "id"}}'),
        ("parameters", '{"name": "run", "parameters": {"command": "id"}}'),
        ("args", '{"name": "run", "args": {"command": "id"}}')):
    _t = f"<tool_call>{_body}</tool_call>"
    _c = parse_tool_calls(_t)
    ck(f"single object, '{_label}' spelling, parses",
       len(_c) == 1 and _c[0].args.get("command") == "id",
       str([(x.name, x.args) for x in _c]))

# OpenAI hands the argument object back as a JSON STRING; so do some servers.
_c = parse_tool_calls(
    '<tool_call>{"name": "run", "arguments": "{\\"command\\": \\"id\\"}"}'
    '</tool_call>')
ck("a JSON-STRING argument object is decoded, not passed through as text",
   len(_c) == 1 and _c[0].args.get("command") == "id",
   str([(x.name, x.args) for x in _c]))

_c = parse_tool_calls('<tool_call>{"name": "system_info", "arguments": ""}'
                      '</tool_call>')
ck("an empty argument string means no arguments, not malformed",
   len(_c) == 1 and _c[0].args == {}, str([(x.name, x.args) for x in _c]))

# Name as a bare token, JSON as the body — the natural half-way degradation.
_c = parse_tool_calls('<tool_call>run\n{"command": "id"}\n</tool_call>')
ck("name-then-JSON body parses",
   len(_c) == 1 and _c[0].name == "run" and _c[0].args.get("command") == "id",
   str([(x.name, x.args) for x in _c]))

# A batch: GLM puts parallel calls in one array.
_c = parse_tool_calls(
    '<tool_call>[{"name": "a", "arguments": {"x": 1}}, '
    '{"name": "b", "arguments": {"y": 2}}]</tool_call>')
ck("an array of two calls yields both, in order",
   len(_c) == 2 and _c[0].name == "a" and _c[1].name == "b",
   str([(x.name, x.args) for x in _c]))

# ALL OR NOTHING. Half-running a batch is worse than running none of it: the
# model is told the step happened and never learns which half was dropped.
_half = ('<tool_call>[{"name": "a", "arguments": {"x": 1}}, '
         '{"nome": "b"}]</tool_call>')
ck("a batch with one undecodable member runs NOTHING",
   parse_tool_calls(_half) == [], str(parse_tool_calls(_half)))

# The <arg_key> dialect must be untouched by all of the above — and in
# particular a file body must still be treated as TEXT, not re-decoded.
_wf = ('<tool_call>write_file\n<arg_key>path</arg_key>\n'
       '<arg_value>/tmp/x.json</arg_value>\n<arg_key>content</arg_key>\n'
       '<arg_value>{"a": 1}</arg_value>\n</tool_call>')
_c = parse_tool_calls(_wf)
ck("REGRESSION: an <arg_key> write still parses",
   len(_c) == 1 and _c[0].name == "write_file", str(_c))
ck("REGRESSION: a JSON-looking file body stays a STRING",
   _c and isinstance(_c[0].args.get("content"), str)
   and _c[0].args["content"] == '{"a": 1}',
   repr(_c[0].args.get("content") if _c else None))

ck("GLM JSON normalisation is idempotent",
   C._normalise_tool_syntax(C._normalise_tool_syntax(_vllm))
   == C._normalise_tool_syntax(_vllm))


# ── COUNTER-PROPERTY: prose is never executed, and never deleted ──
print("\n== counter-property: prose survives, and never fires a tool ==")
_benign = [
    "The value is x < y and the loop runs while i < t",
    "Use `<tool_call>` to wrap the function name in GLM's dialect.",
    'A call body looks like {"name": "run", "arguments": {}} in most APIs.',
    "I'll explain: a <tool_call> block is GLM's native format.",
    'Here is a dict: {"a": 1, "b": [2, 3]}',
    "curl 'https://x/?a=1&copy=2' | jq '.name'",
    "def f(): return {'name': 'run'}",
    "Nothing to see here.",
]
random.seed(20260906)
for _ in range(600):
    _benign.append("".join(random.choice(string.printable[:95])
                           for _ in range(random.randint(5, 300))))
_false = [t for t in _benign
          if parse_tool_calls(t) and "<tool name=" not in t]
ck(f"{len(_benign)} benign inputs parse to ZERO tool calls",
   not _false, repr(_false[:2]))

# A fenced example is the model SHOWING the operator the syntax: it must not
# fire, and it must not vanish from the page either.
_fenced = ('Here is the shape:\n```\n<tool_call>{"name": "run", '
           '"arguments": {"command": "id"}}</tool_call>\n```\nThat is all.')
ck("a fenced GLM example does not execute",
   parse_tool_calls(_fenced) == [])
ck("…and is not deleted from the page",
   "run" in strip_tool_calls(_fenced)
   and strip_tool_calls(_fenced).startswith("Here is the shape:"),
   repr(strip_tool_calls(_fenced)))


# ── STREAMING: replay character by character, count leaking frames ──
# A completed-text test is not enough for a streaming renderer; this is the
# probe that found the <tool_calls> leak the whole-message probe called clean.
print("\n== streaming replay ==")
_streams = {
    "json array": _vllm,
    "json object": '<tool_call>{"name": "run", "arguments": {"command": "id"}}'
                   "</tool_call>",
    "unclosed json": _unclosed,
    "name then json": '<tool_call>run\n{"command": "id"}\n</tool_call>',
    "arg_key form": _wf,
    "prose before a call": 'Checking now.\n<tool_call>{"name": "run", '
                           '"arguments": {"command": "id"}}</tool_call>',
}
for _name, _txt in _streams.items():
    _leaks = sum(1 for i in range(1, len(_txt) + 1)
                 if _PROTOCOL.search(strip_tool_calls(_txt[:i])))
    ck(f"streaming '{_name}': zero frames show protocol", _leaks == 0,
       f"{_leaks} leaking frames")

# No text may be LOST from an ordinary reply at any frame.
_plain = ("Here is the answer. The threshold is when i < t and the ratio "
          'exceeds {"limit": 5}. Nothing else matters.')
_lost = sum(1 for i in range(1, len(_plain) + 1)
            if strip_tool_calls(_plain[:i]).strip()
            and not _plain.startswith(strip_tool_calls(_plain[:i]).rstrip()))
ck("no frame of a plain reply loses text", _lost == 0, str(_lost))
ck("a plain reply is byte-identical after stripping",
   strip_tool_calls(_plain) == _plain.strip())


# ── PERFORMANCE: this runs on EVERY streamed frame ──
# Asserted as a SCALING EXPONENT, not a millisecond ceiling: a slow CI box
# moves the constant but not the shape, and the shape is what a quadratic
# regression changes.
print("\n== performance shape ==")


def _ms(fn, *a):
    t0 = time.time()
    fn(*a)
    return (time.time() - t0) * 1000.0


_t1 = _ms(strip_tool_calls, "<tool_call>" * 1000)
_t4 = _ms(strip_tool_calls, "<tool_call>" * 4000)
ck("4x the openers costs well under 16x the time (i.e. not quadratic)",
   _t4 < max(_t1, 0.05) * 12, f"1000={_t1:.2f}ms 4000={_t4:.2f}ms")
# An unclosed opener followed by a growing file body is the shape that would
# re-run json.loads over the whole buffer once per frame.
_b1 = "<tool_call>write_file\n<arg_key>content</arg_key>\n<arg_value>" \
      + "x{}y" * 2000
_b4 = "<tool_call>write_file\n<arg_key>content</arg_key>\n<arg_value>" \
      + "x{}y" * 8000
_u1, _u4 = _ms(strip_tool_calls, _b1), _ms(strip_tool_calls, _b4)
ck("4x an unclosed arg_key body costs well under 16x the time",
   _u4 < max(_u1, 0.05) * 12, f"2000={_u1:.2f}ms 8000={_u4:.2f}ms")


# ═════════════════════════════════════════════════════════════════════
# 2. THE ORPHANED </think>
# ═════════════════════════════════════════════════════════════════════
print("\n== implicit <think> opened by the chat template ==")

_orphan = ("The operator wants the host details, so uname is the move."
           "</think>\n\nRunning uname now.")
_vis, _rea = extract_think_blocks(_orphan)
ck("an orphaned </think> moves the reasoning OUT of the reply",
   _vis.strip() == "Running uname now.", repr(_vis))
ck("…and into the reasoning channel",
   _rea.startswith("The operator wants"), repr(_rea))
ck("…so the literal </think> is never rendered", "</think>" not in _vis)
ck("…and TTS does not read the chain of thought aloud",
   speakable_text(_orphan).strip() == "Running uname now.",
   repr(speakable_text(_orphan)))

# No newline after the closer is still the template shape, not prose.
_vis, _rea = extract_think_blocks("Reasoning.</think>Answer.")
ck("closer with no whitespace after it still splits",
   _vis == "Answer." and _rea == "Reasoning.", repr((_vis, _rea)))

# A turn that is ALL reasoning (cut off before the answer).
_vis, _rea = extract_think_blocks("Only reasoning, cut off.</think>")
ck("a reasoning-only reply leaves an empty visible message",
   _vis.strip() == "" and _rea == "Only reasoning, cut off.",
   repr((_vis, _rea)))

# Reasoning then a tool call: the call must survive the split.
_ot = ("I need the host info.</think>\n"
       '<tool_call>{"name": "run", "arguments": {"command": "uname -a"}}'
       "</tool_call>")
_c = parse_tool_calls(_ot)
ck("a call after an orphaned closer still runs",
   len(_c) == 1 and _c[0].args.get("command") == "uname -a",
   str([(x.name, x.args) for x in _c]))
ck("…and its reasoning is still separated",
   extract_think_blocks(_ot)[1] == "I need the host info.")

# ── COUNTER-PROPERTY: a reply that MENTIONS the tag keeps its own words ──
for _label, _prose in (
        ("inline, space after", "The tag </think> closes a reasoning block."),
        ("inline, tab after", "Write </think>\tto close it."),
        ("fenced", "Like this:\n```\nreasoning</think>\n```\nSee?")):
    _v, _r = extract_think_blocks(_prose)
    ck(f"prose mentioning the closer ({_label}) is left whole",
       _v == _prose and _r == "", repr((_v, _r)))

# REGRESSIONS: the ordinary paired forms are untouched.
ck("REGRESSION: a normal <think> pair still splits",
   extract_think_blocks("<think>why</think>\n\nAnswer.") == ("\n\nAnswer.",
                                                            "why"))
ck("REGRESSION: two pairs still concatenate",
   extract_think_blocks("<think>a</think>mid<think>b</think>end")
   == ("midend", "a\nb"))
ck("REGRESSION: an unclosed opener mid-stream still hides",
   extract_think_blocks("prefix <think>still thinking")
   == ("prefix ", "still thinking"))
ck("REGRESSION: text with no think tags is returned unchanged",
   extract_think_blocks("Plain answer.") == ("Plain answer.", ""))
ck("an opener AFTER the first closer still means an orphan at the front",
   extract_think_blocks("first</think>\nthen <think>b</think> done")[1]
   == "first\nb")


# ═════════════════════════════════════════════════════════════════════
# 3. reasoning_effort — omitting the field is a CHOICE, and it is "max"
# ═════════════════════════════════════════════════════════════════════
print("\n== reasoning_effort maps onto the model's real enum ==")

ck("GLM-5.3-Flash has the dial", supports_reasoning_effort(GLM53))
ck("GLM-6 would too (forward-compatible)",
   supports_reasoning_effort("zai-org/GLM-6-Flash"))
ck("DeepSeek does not (it uses enable_thinking)",
   not supports_reasoning_effort("deepseek-ai/DeepSeek-V4-Flash"))

_ORDER = ("low", "high", "max")
for _lvl in ("low", "medium", "high"):
    _ex = reasoning_extra(GLM53, _lvl)
    ck(f"'{_lvl}' sends reasoning_effort at all", "reasoning_effort" in _ex,
       str(_ex))
    ck(f"'{_lvl}' sends a value the model's enum accepts",
       _ex["reasoning_effort"] in _ORDER, str(_ex))
ck("'medium' is translated to 'high', never forwarded raw "
   "(out-of-enum falls back to max, which is the opposite of the intent)",
   reasoning_extra(GLM53, "medium")["reasoning_effort"] == "high")
ck("Low genuinely asks for LOW depth",
   reasoning_extra(GLM53, "low")["reasoning_effort"] == "low")
ck("High asks for max depth",
   reasoning_extra(GLM53, "high")["reasoning_effort"] == "max")
ck("depth is monotonic across the three rungs",
   _ORDER.index(reasoning_extra(GLM53, "low")["reasoning_effort"])
   < _ORDER.index(reasoning_extra(GLM53, "medium")["reasoning_effort"])
   < _ORDER.index(reasoning_extra(GLM53, "high")["reasoning_effort"]))
ck("GLM-5.2 keeps the two-value enum it actually ships",
   reasoning_effort_enum("zai-org/GLM-5.2")["low"] == "high")
ck("an unknown glm-5 id gets the conservative two-value map",
   reasoning_effort_enum("zai-org/GLM-5.9-Preview")["low"] == "high")
ck("thinking_budget still rides alongside (SiliconFlow's own lever)",
   all("thinking_budget" in reasoning_extra(GLM53, l)
       for l in ("low", "medium", "high")))
ck("a model with no dial gets no fields at all",
   reasoning_extra("deepseek-ai/DeepSeek-V4-Flash", "high") == {})
ck("the shipped default rung is 'low'",
   C.DEFAULT_SETTINGS.get("reasoning_effort") == "low")


# ═════════════════════════════════════════════════════════════════════
# 4. THE WALL-CLOCK CUT IS REPORTED
# ═════════════════════════════════════════════════════════════════════
# Driven through the REAL OpenAICompatBackend.stream_chat against a fake HTTP
# stream, not by asserting that a string appears in the source. A stream that
# keeps producing tokens past STREAM_MAX_WALL_S must come back marked
# unfinished, or an amputated reply is stored as a complete one.
print("\n== a turn cut at the wall clock says so ==")


class _FakeStream:
    """An SSE body that never ends — the runaway-reasoning shape."""

    def __init__(self, stall_after=3, delay=0.0):
        self._n = 0
        self._stall_after = stall_after
        self._delay = delay

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return self

    def __next__(self):
        self._n += 1
        if self._n > 400:
            raise StopIteration
        if self._n > self._stall_after:
            time.sleep(self._delay)
        payload = {"choices": [{"delta": {"content": f"tok{self._n} "}}]}
        return ("data: " + json.dumps(payload) + "\n").encode()


_spec = C.PROVIDERS_BY_KEY["siliconflow"]
_be = C.OpenAICompatBackend(_spec, api_key="test-key")

_orig_urlopen = C.urllib.request.urlopen
_orig_wall = C.STREAM_MAX_WALL_S
try:
    C.STREAM_MAX_WALL_S = 0.10
    C.urllib.request.urlopen = lambda *a, **k: _FakeStream(delay=0.02)
    _meta = {}
    _be.stream_chat(GLM53, [{"role": "user", "content": "hi"}],
                    on_token=lambda t: None,
                    on_done=lambda m: _meta.update(m),
                    on_error=lambda e: _meta.update({"error": e}),
                    single_model=True)
finally:
    C.urllib.request.urlopen = _orig_urlopen
    C.STREAM_MAX_WALL_S = _orig_wall

ck("the turn completed rather than erroring", "error" not in _meta, str(_meta))
ck("a wall-clock cut is reported as TRUNCATED "
   "(it used to come back finished, so an amputated reply was stored whole)",
   _meta.get("truncated") is True, str(_meta))
ck("…and says WHICH cap it hit", _meta.get("cut_by") == "time", str(_meta))
ck("…and the text that did arrive is kept",
   "tok1" in (_meta.get("text") or ""), repr(_meta.get("text"))[:80])

# COUNTER-PROPERTY: a stream that finishes normally is NOT marked truncated.
try:
    C.urllib.request.urlopen = lambda *a, **k: _FakeStream(stall_after=10**9)
    _meta2 = {}
    _be2 = C.OpenAICompatBackend(_spec, api_key="test-key")
    _be2.stream_chat(GLM53, [{"role": "user", "content": "hi"}],
                     on_token=lambda t: None,
                     on_done=lambda m: _meta2.update(m),
                     on_error=lambda e: _meta2.update({"error": e}),
                     single_model=True)
finally:
    C.urllib.request.urlopen = _orig_urlopen

ck("a stream that ends on its own is NOT marked truncated",
   _meta2.get("truncated") is False, str({k: _meta2.get(k)
                                          for k in ("truncated", "cut_by")}))
ck("…and carries no cut reason", _meta2.get("cut_by") == "", str(_meta2))


# ═════════════════════════════════════════════════════════════════════
# 5. VISION ON AN ALWAYS-THINKING MODEL
# ═════════════════════════════════════════════════════════════════════
print("\n== vision does not blame the image for a reasoning budget ==")

_src = open(os.path.join(_ROOT, "basilisk_core.py"),
            encoding="utf-8").read()
_vs = _src.split("def tool_analyze_image", 1)[1].split("\ndef ", 1)[0]
ck("the vision probe captured the function", len(_vs) > 500, str(len(_vs)))
ck("the vision call dials reasoning DOWN for a description task",
   "reasoning_extra(model, \"low\")" in _vs, "not found")
ck("an empty description checks for reasoning before blaming image support",
   "reasoning_content" in _vs and "finish_reason" in _vs)
# rINDEX, not index: the explanatory comment above the fix QUOTES the phrase,
# so a first-occurrence probe matched the comment and reported the branches in
# the wrong order. Validate a source probe against what it actually matched
# before trusting its verdict — this checker was wrong before the code was.
ck("the phrase appears in both a comment and the branch (probe sanity)",
   _vs.count("may not support images") == 2,
   str(_vs.count("may not support images")))
ck("…and the blanket 'may not support images' is the LAST branch",
   _vs.rindex("used its whole response budget")
   < _vs.rindex("may not support images"))


# ═════════════════════════════════════════════════════════════════════
# 6. THE TURN THAT THINKS AND SAYS NOTHING
# ═════════════════════════════════════════════════════════════════════
# The reported loop, verbatim from the operator's terminal:
#
#   stream start / stream done / response looked degraded (empty/repetitive)
#   auto-retry 1/3 ... 2/3 ... 3/3 / forcing the final answer (empty reply)
#   ...and again, for ever.
#
# The retry re-sent the SAME request to a model whose thinking cannot be
# disabled and which, with reasoning_effort omitted, runs at maximum depth: a
# deterministic budget failure, retried deterministically. So the recovery has
# to CHANGE the request — shorter thinking, more room for the answer — and it
# has to be able to tell that case apart from genuine junk output.
print("\n== recovery from a reasoned-but-silent turn ==")


class _RecordingBackend:
    name = "siliconflow"

    def __init__(self):
        self.fallback_chain = list(C.SILICONFLOW_CHAIN)
        self.sent = []

    def is_available(self):
        return True

    def stream_chat(self, model, messages, on_token, on_done, on_error,
                    options=None, cancel_event=None, on_reasoning=None,
                    single_model=False):
        self.sent.append((model, dict(options or {})))
        on_done({"text": "ok", "backend": self.name, "model": model})


def _drive(**kw):
    be = _RecordingBackend()
    st = dict(C.DEFAULT_SETTINGS)
    st["active_provider"] = "siliconflow"
    st["headroom_enabled"] = False
    C.BackendRouter({"siliconflow": be}, st).stream_chat(
        [{"role": "user", "content": "x"}], lambda t: None,
        lambda m: None, lambda e: None, **kw)
    return be.sent[-1]


_model, _opts = _drive()
_extra = _opts.get("extra_body") or {}
ck("an ordinary turn on the default model asks for LOW depth",
   _extra.get("reasoning_effort") == "low", str(_extra))

_model_r, _opts_r = _drive(reasoning_override="low", max_tokens_override=4096)
_extra_r = _opts_r.get("extra_body") or {}
ck("the recovery turn dials the thinking DOWN",
   _extra_r.get("reasoning_effort") == "low"
   and _extra_r.get("thinking_budget") == C._EFFORT_TO_BUDGET["low"],
   str(_extra_r))
ck("…and gives the ANSWER more room",
   _opts_r.get("max_tokens") == 4096, str(_opts_r.get("max_tokens")))

# The recovery must beat a HIGH pill: an operator sitting on High is the most
# likely person to hit this, and "think even harder" is the wrong answer.
_be = _RecordingBackend()
_st = dict(C.DEFAULT_SETTINGS)
_st.update({"active_provider": "siliconflow", "headroom_enabled": False,
            "reasoning_effort": "high"})
C.BackendRouter({"siliconflow": _be}, _st).stream_chat(
    [{"role": "user", "content": "x"}], lambda t: None, lambda m: None,
    lambda e: None, reasoning_override="low", effort="heavy")
_extra_h = (_be.sent[-1][1].get("extra_body") or {})
ck("the recovery override beats a High pill AND a heavy turn",
   _extra_h.get("reasoning_effort") == "low", str(_extra_h))
ck("…without editing the operator's saved setting",
   _st["reasoning_effort"] == "high", _st["reasoning_effort"])

# ── the heavy escalation must not become a cross-family swap ──
_m_heavy, _o_heavy = _drive(effort="heavy")
ck("a heavy turn STAYS on the GLM the operator selected",
   _m_heavy == "zai-org/GLM-5.3-Flash", _m_heavy)
ck("…and escalates the reasoning dial instead of the model id",
   (_o_heavy.get("extra_body") or {}).get("reasoning_effort") == "max",
   str(_o_heavy.get("extra_body")))
ck("_model_family separates the vendors",
   C._model_family("zai-org/GLM-5.3-Flash")
   != C._model_family("deepseek-ai/DeepSeek-V4-Pro"))
ck("…and unifies a vendor's own siblings",
   C._model_family("deepseek-ai/DeepSeek-V4-Flash")
   == C._model_family("deepseek-ai/DeepSeek-V4-Pro"))

# ── the wiring in basilisk.py, which no import here can execute ──
_bsrc = open(os.path.join(_ROOT, "basilisk.py"), encoding="utf-8").read()
ck("the degraded branch reads the thoughts it already captured",
   "get_thoughts()" in _bsrc and "_reasoned_silent" in _bsrc)
ck("…and arms a recovery instead of repeating the request",
   "_recover_silent_reasoner = True" in _bsrc)
ck("the recovery flag is consumed exactly once",
   _bsrc.count("self._recover_silent_reasoner = False") == 1
   and _bsrc.count("self._recover_silent_reasoner = True") == 1)
ck("the flag is a real CLASS attribute, not a getattr default "
   "(a stub base with __getattr__ makes every missing name truthy)",
   "_recover_silent_reasoner: bool = False" in _bsrc
   and 'getattr(self, "_recover_silent_reasoner"' not in _bsrc)
ck("the retry actually reaches the router",
   "reasoning_override=_re_override" in _bsrc
   and "max_tokens_override=_mt_override" in _bsrc)
ck("a time-limit cut is named as such, not as 'degraded'",
   "cut at the per-turn time limit" in _bsrc)


print(f"\nglm: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
