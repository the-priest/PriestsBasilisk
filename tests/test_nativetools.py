#!/usr/bin/env python3
"""test_nativetools.py — v1.2.0.4: native function-calling.

The reference harnesses (Claude Code, opencode, DeepSeek's own app) drive the
model with a proper OpenAI `tools` schema and consume structured tool_calls;
the V4/V4.1 family is trained for exactly that. This suite guards that Basilisk
now does the same, from the SAME system prompt the model reads, and — the
load-bearing safety property — that a provider which rejects the tools field
DEGRADES to the text protocol instead of killing the turn.

Run:  python3 tests/test_nativetools.py
"""
import io
import json
import os
import sys
import types
import urllib.error

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


# ── 1. build_tools_schema ────────────────────────────────────────────
print("\n== the tools schema is built from the persona's own <tool> lines ==")
_SP = (
    'You may call:\n'
    '  <tool name="read_file">{"path": "src/api.py"}</tool>  // read a file\n'
    '  <tool name="run">{"command": "ls", "reason": "list"}</tool>  // run it\n'
    '  <tool name="processes">{"top_n": 15}</tool>  // top N by cpu\n'
    '  <tool name="flag">{"on": true}</tool>  // a boolean arg\n'
    '  <tool name="weird">not json here</tool>  // unparseable example\n'
    '  <tool name="read_file">{"path": "dup"}</tool>  // a duplicate\n')
_tools = C.build_tools_schema(_SP)
_names = [t["function"]["name"] for t in _tools]
ck("every declared tool appears once (dedup by name)",
   _names.count("read_file") == 1 and set(_names) ==
   {"read_file", "run", "processes", "flag", "weird"}, str(_names))
ck("every entry is a well-formed OpenAI function tool",
   all(t.get("type") == "function" and t["function"].get("name")
       and isinstance(t["function"].get("parameters"), dict) for t in _tools))


def _fn(name):
    return next(t["function"] for t in _tools if t["function"]["name"] == name)


ck("the // comment becomes the description",
   _fn("run")["description"] == "run it", _fn("run")["description"])
ck("property names are lifted from the example JSON",
   set(_fn("run")["parameters"]["properties"]) == {"command", "reason"},
   str(_fn("run")["parameters"]))
ck("a string arg is typed string",
   _fn("read_file")["parameters"]["properties"]["path"]["type"] == "string")
ck("an integer arg is typed integer",
   _fn("processes")["parameters"]["properties"]["top_n"]["type"] == "integer")
ck("a boolean arg is typed boolean",
   _fn("flag")["parameters"]["properties"]["on"]["type"] == "boolean")
ck("an unparseable example degrades to a permissive object",
   _fn("weird")["parameters"] == {"type": "object"},
   str(_fn("weird")["parameters"]))
ck("an empty prompt yields no tools", C.build_tools_schema("") == [])

# Against the REAL persona: it must produce a non-trivial, valid schema and
# never invent a tool that was not declared.
from basilisk_persona import build_system_prompt
_real_sp = build_system_prompt(agent_mode=True, grouped=True, unleashed=False,
                               preload_groups=["workspace"])
_real = C.build_tools_schema(_real_sp)
_real_names = {t["function"]["name"] for t in _real}
ck("the real persona yields a substantial schema", len(_real) >= 20,
   str(len(_real)))
ck("core coding tools are present",
   {"run", "read_file", "workspace_write", "workspace_append",
    "web_read"} <= _real_names,
   str(sorted(_real_names)[:12]))
import re as _re
_declared = set(_re.findall(r'<tool name="([a-zA-Z0-9_]+)"', _real_sp))
ck("the schema never lists a tool the prompt did not declare",
   _real_names <= _declared, str(_real_names - _declared))


# ── 2. the backend sends tools, and degrades when they are rejected ──
print("\n== tools ride in the payload, and a rejection degrades safely ==")


class _FakeHTTPError(urllib.error.HTTPError):
    def __init__(self, code, body):
        self._b = body.encode()
        super().__init__("http://x", code, "err", {}, io.BytesIO(self._b))

    def read(self):
        return self._b


class _R:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        yield b'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}'
        yield b'data: [DONE]'


def _spec(chain=("m",)):
    return types.SimpleNamespace(
        key="probe", base_url="https://example.invalid/v1",
        chain=list(chain), extra_headers={}, engine="openai")


_TOOLS = [{"type": "function",
           "function": {"name": "run",
                        "description": "run", "parameters": {"type": "object"}}}]


def _drive(reject_fn, tools=_TOOLS, chain=("m",)):
    b = C.OpenAICompatBackend(_spec(chain), api_key="k")
    seen = []

    def fake_urlopen(req, timeout=None):
        p = json.loads(req.data.decode())
        seen.append(p)
        err = reject_fn(p)
        if err:
            raise err
        return _R()

    real = C.urllib.request.urlopen
    C.urllib.request.urlopen = fake_urlopen
    out = {}
    try:
        opts = {"max_tokens": 1024}
        if tools:
            opts["tools"] = tools
        b.stream_chat("m", [{"role": "user", "content": "x"}],
                      on_token=lambda t: None,
                      on_done=lambda d: out.update(d or {}),
                      on_error=lambda e: out.update({"error": e}),
                      options=opts)
    finally:
        C.urllib.request.urlopen = real
    return seen, out, b


# 2a. tools present -> payload carries tools + tool_choice
seen, out, _ = _drive(lambda p: None)
ck("payload carries the tools array", seen[0].get("tools") == _TOOLS,
   str(seen[0].get("tools")))
ck("payload sets tool_choice=auto", seen[0].get("tool_choice") == "auto",
   str(seen[0].get("tool_choice")))
ck("the turn succeeds", out.get("text") == "ok", str(out))

# 2b. no tools passed -> no tools key at all (byte-identical to before)
seen0, out0, _ = _drive(lambda p: None, tools=None)
ck("no tools passed -> no tools key in payload", "tools" not in seen0[0],
   str(sorted(seen0[0])))

# 2c. a 400 that names the tools field -> strip tools, retry SAME model, succeed
def _reject_tools_once(p):
    if "tools" in p:
        return _FakeHTTPError(400, json.dumps(
            {"error": {"message": "this model does not support tool use"}}))
    return None
seen2, out2, b2 = _drive(_reject_tools_once)
ck("tool rejection is survived (turn still succeeds)",
   out2.get("text") == "ok", str(out2.get("error")))
ck("the retry is the SAME model",
   [p["model"] for p in seen2] == ["m", "m"], str([p["model"] for p in seen2]))
ck("the retry dropped the tools field",
   "tools" not in seen2[1], str(sorted(seen2[1])))
ck("the model is remembered as tools-rejecting", "m" in b2._tools_rejected)

# 2d. a 400 NOT about tools must not be misread as a tools rejection
def _reject_other(p):
    return _FakeHTTPError(400, json.dumps(
        {"error": {"message": "invalid role in messages[0]"}}))
seen3, out3, b3 = _drive(_reject_other, chain=("m", "m2"))
ck("an unrelated 400 does not blame tools", "m" not in b3._tools_rejected,
   str(b3._tools_rejected))


# ── 3. the Router gates tools on the setting and on sidecar calls ─────
print("\n== the router gates tools correctly ==")


def _router(**over):
    s = dict(C.DEFAULT_SETTINGS)
    s["active_provider"] = "siliconflow"
    s["siliconflow_api_key"] = "sk-test"
    s["headroom_enabled"] = False
    s["siliconflow_model"] = "deepseek-ai/DeepSeek-V4.1-Flash"
    s.update(over)
    cloud = {}
    for spec in C.PROVIDERS:
        key = s.get(f"{spec.key}_api_key", "")
        cloud[spec.key] = (C.GroqBackend(key) if spec.engine == "groq"
                           else C.OpenAICompatBackend(spec, key))
    return C.BackendRouter(cloud, s)


_SENT = []


def _run_router(router, tools, single_model=False):
    _SENT.clear()

    def fake_urlopen(req, timeout=None):
        _SENT.append(json.loads(req.data.decode()))
        return _R()

    real = C.urllib.request.urlopen
    C.urllib.request.urlopen = fake_urlopen
    try:
        router.stream_chat([{"role": "user", "content": "x"}],
                           on_token=lambda t: None, on_done=lambda d: None,
                           on_error=lambda e: None,
                           tools=tools, single_model=single_model)
    finally:
        C.urllib.request.urlopen = real


# v1.2.0.9: native tools ship OFF — the text `<tool>` protocol is the reliable
# default on the live stack. The structured implementation stays wired and
# correct as an opt-in (tested below), but the default request carries NO tools.
ck("native_tool_calls defaults to OFF",
   C.DEFAULT_SETTINGS.get("native_tool_calls") is False,
   str(C.DEFAULT_SETTINGS.get("native_tool_calls")))
_run_router(_router(), _TOOLS)
ck("default (OFF) -> no tools sent, model uses the text protocol",
   "tools" not in (_SENT[0] if _SENT else {}),
   str(sorted(_SENT[0])) if _SENT else "no request")

_run_router(_router(native_tool_calls=True), _TOOLS)
ck("native_tool_calls=True -> tools sent (opt-in still works)",
   _SENT and _SENT[0].get("tools") == _TOOLS,
   str(_SENT[0].get("tools") if _SENT else None))

_run_router(_router(), _TOOLS, single_model=True)
ck("a sidecar (single_model) call never sends tools",
   "tools" not in (_SENT[0] if _SENT else {}), str(sorted(_SENT[0])) if _SENT else "?")

_run_router(_router(), None)
ck("no tools built -> no tools sent", "tools" not in (_SENT[0] if _SENT else {}))


# ── 4. structured round-trip: history is structured when tools go out ──
# The core of "the DeepSeek way": the model must see ONE channel. When tools
# are sent, the text tool history is rewritten to assistant.tool_calls +
# role:tool so there is no mixed signal. This is what actually fixes the
# narrate-instead-of-call loop.
print("\n== the conversation the model sees is fully structured ==")


def _msgs_sent_with_history(history, native=True):
    # native tools ship OFF, so exercise the structured path via explicit opt-in
    r = _router(native_tool_calls=True) if native else _router(native_tool_calls=False)
    _SENT2 = {}

    def fake_urlopen(req, timeout=None):
        _SENT2["payload"] = json.loads(req.data.decode())
        return _R()
    real = C.urllib.request.urlopen
    C.urllib.request.urlopen = fake_urlopen
    try:
        r.stream_chat(history, on_token=lambda t: None,
                      on_done=lambda d: None, on_error=lambda e: None,
                      tools=_TOOLS)
    finally:
        C.urllib.request.urlopen = real
    return _SENT2.get("payload", {}).get("messages", [])


_hist = [
    {"role": "user", "content": "get me news"},
    {"role": "assistant",
     "content": '<tool name="web_read">{"url":"http://x"}</tool>'},
    {"role": "user",
     "content": "<tool_result>\n[tool: web_read]\nHEADLINES\n</tool_result>"},
    {"role": "assistant", "content": "Here is the news."},
]
_out = _msgs_sent_with_history(_hist, native=True)
_asst_tc = [m for m in _out if m.get("role") == "assistant" and m.get("tool_calls")]
_toolmsgs = [m for m in _out if m.get("role") == "tool"]
ck("the assistant tool call is sent as structured tool_calls",
   len(_asst_tc) == 1 and _asst_tc[0]["tool_calls"][0]["function"]["name"] == "web_read",
   str(_asst_tc))
ck("the result is sent as a role:tool message with the matching id",
   len(_toolmsgs) == 1
   and _toolmsgs[0]["tool_call_id"] == _asst_tc[0]["tool_calls"][0]["id"]
   and "HEADLINES" in _toolmsgs[0]["content"],
   str(_toolmsgs))
ck("no raw <tool_result> text leaks into the structured request",
   not any("<tool_result>" in (m.get("content") or "") for m in _out))
# with native OFF, the SAME history stays as text (no structuring)
_out_off = _msgs_sent_with_history(_hist, native=False)
ck("with tools off, history is left as text (no structuring)",
   any("<tool_result>" in (m.get("content") or "") for m in _out_off)
   and not any(m.get("role") == "tool" for m in _out_off))


# ── 5. robustness of the structured transform + fallback ─────────────
print("\n== the transform is valid by construction and degrades coherently ==")
S = C.structure_tool_messages
D = C.destructure_tool_messages


def _valid(msgs):
    """No assistant.tool_calls without matching following role:tool; no orphan
    role:tool — the two shapes an API 400s on."""
    i, n = 0, len(msgs)
    while i < n:
        m = msgs[i]
        if m.get("role") == "assistant" and m.get("tool_calls"):
            ids = [t["id"] for t in m["tool_calls"]]
            for k, cid in enumerate(ids):
                if i + 1 + k >= n:
                    return False
                nxt = msgs[i + 1 + k]
                if nxt.get("role") != "tool" or nxt.get("tool_call_id") != cid:
                    return False
            i += 1 + len(ids)
            continue
        if m.get("role") == "tool":
            return False
        i += 1
    return True


# a pre-structured / malformed INPUT (orphan role:tool, dangling tool_calls) is
# normalised so the OUTPUT is always valid — the unconditional guarantee.
_bad = [{"role": "tool", "tool_call_id": "x", "content": "orphan"},
        {"role": "assistant", "tool_calls": [
            {"id": "y", "type": "function",
             "function": {"name": "a", "arguments": "{}"}}]},
        {"role": "user", "content": "hi"}]
ck("pre-structured/malformed input is normalised to a VALID structure",
   _valid(S(_bad)))
# a clean pair round-trips: structure -> destructure -> pure text again
_pair = [{"role": "assistant", "content": '<tool name="run">{"command":"ls"}</tool>'},
         {"role": "user", "content": "<tool_result>\nOUT\n</tool_result>"}]
_st = S(_pair)
ck("a clean pair structures and is valid",
   _valid(_st) and any(m.get("tool_calls") for m in _st))
_ds = D(_st)
ck("destructure folds it back to text (no structured messages remain)",
   not any(m.get("role") == "tool" or m.get("tool_calls") for m in _ds)
   and any("<tool_result>" in (m.get("content") or "") for m in _ds))
# a human message that merely QUOTES <tool_result> is not eaten as a result
_hq = [{"role": "assistant", "content": '<tool name="run">{}</tool>'},
       {"role": "user", "content": "why is <tool_result> in the log?"}]
ck("a human message quoting <tool_result> is not folded into a role:tool",
   not any(m.get("tool_calls") for m in S(_hq)))

# HIGH fix: with native ON, once a model is in _tools_rejected the router sends
# NO tools AND leaves the history as text — the fallback is coherent, not split.
_r = _router(native_tool_calls=True)
_bk = _r.active_cloud()[0]
_bk._tools_rejected.add("deepseek-ai/DeepSeek-V4.1-Flash")
_SENT.clear()
_run_router_hist = None


def _sent_payload(router, history):
    box = {}

    def fake(req, timeout=None):
        box["p"] = json.loads(req.data.decode())
        return _R()
    real = C.urllib.request.urlopen
    C.urllib.request.urlopen = fake
    try:
        router.stream_chat(history, on_token=lambda t: None,
                           on_done=lambda d: None, on_error=lambda e: None,
                           tools=_TOOLS)
    finally:
        C.urllib.request.urlopen = real
    return box.get("p", {})


_p_rej = _sent_payload(_r, [
    {"role": "user", "content": "go"},
    {"role": "assistant", "content": '<tool name="run">{"command":"ls"}</tool>'},
    {"role": "user", "content": "<tool_result>\nOUT\n</tool_result>"}])
ck("a tools-rejected model gets NO tools field",
   "tools" not in _p_rej, str(sorted(_p_rej)))
ck("...and its history stays TEXT (no structured tool messages)",
   not any(m.get("role") == "tool" or m.get("tool_calls")
           for m in _p_rej.get("messages", []))
   and any("<tool_result>" in (m.get("content") or "")
           for m in _p_rej.get("messages", [])),
   "coherent text fallback")


print(f"\nnativetools: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
