#!/usr/bin/env python3
"""
test_effort.py — the effort ladder and the light-turn thinking toggle.

WHAT THIS GUARDS: `fast_light_turns` adds a NON-STANDARD field
(`enable_thinking`) to the chat request body. That field is not in the
OpenAI schema, so a provider is entitled to reject it with a 400 — and this
runs on the operator's only working provider, mid-engagement. Three things
therefore have to hold, and all three are asserted end-to-end against a
faked HTTP layer rather than argued for in a comment:

  1. DEFAULT OFF means the request body is BYTE-IDENTICAL to the body sent
     before the feature existed. Opting out has to be free.
  2. A 400 caused by our own extra field strips it and retries the SAME
     model — it must NOT be mistaken for a stale model id, which would send
     the router hunting down the fallback chain for a model that was never
     broken.
  3. After one rejection the field is not sent again for the rest of the
     session, so the degradation costs one round-trip once, not every turn.

And the load-bearing safety property: the toggle NEVER applies to a
standard or heavy turn. Light turns are receipts and chat. Heavy turns are
live engagement work, which is exactly where reasoning earns its keep.

Run:  python3 tests/test_effort.py
"""

from __future__ import annotations

import io
import json
import sys
import os
import urllib.error

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import basilisk_core as C  # noqa: E402

_p = _f = 0


def ck(name: str, cond: bool, detail: str = "") -> None:
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


# ── fake HTTP layer ──────────────────────────────────────────────────
SENT: list = []
_real_urlopen = C.urllib.request.urlopen


class _Resp:
    def __init__(self, lines):
        self.lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter(self.lines)


_OK = [b'data: {"choices":[{"delta":{"content":"ok"}}]}\n', b'data: [DONE]\n']


def _urlopen_factory(reject_extras=False, reject_models=()):
    """reject_extras: 400 on any body carrying enable_thinking.
       reject_models: 400 on these model ids regardless (stale-id sim)."""
    def _u(req, timeout=None):
        body = json.loads(req.data.decode())
        SENT.append(body)
        bad = (reject_extras and "enable_thinking" in body) \
            or body.get("model") in reject_models
        if bad:
            raise urllib.error.HTTPError(
                req.full_url, 400, "Bad Request", {},
                io.BytesIO(b'{"error":{"message":"unrecognized field"}}'))
        return _Resp(_OK)
    return _u


def _settings(**over):
    s = dict(C.DEFAULT_SETTINGS)
    s["active_provider"] = "siliconflow"
    s["siliconflow_api_key"] = "sk-test"
    s["headroom_enabled"] = False      # keep the body deterministic
    # PIN THE MODEL THIS SUITE IS ABOUT rather than inheriting the shipped
    # default. fast_light_turns is the `enable_thinking` toggle, a DeepSeek
    # feature; when the pinned default moved to GLM-5.3-Flash (which has no
    # such toggle) every assertion here quietly started testing a model that
    # does not have the feature under test. A suite about a feature must name
    # a model that HAS it. The shipped default is asserted separately below.
    s["siliconflow_model"] = PINNED
    s.update(over)
    return s


def _router(settings):
    """Build a BackendRouter the way basilisk.py does."""
    cloud = {}
    for spec in C.PROVIDERS:
        key = settings.get(f"{spec.key}_api_key", "")
        cloud[spec.key] = (C.GroqBackend(key) if spec.engine == "groq"
                           else C.OpenAICompatBackend(spec, key))
    return C.BackendRouter(cloud, settings)


def _run(settings, effort, urlopen):
    SENT.clear()
    C.urllib.request.urlopen = urlopen
    out = {}
    try:
        r = _router(settings)
        r.stream_chat(
            [{"role": "user", "content": "hi"}],
            on_token=lambda t: None,
            on_done=lambda d: out.update(d),
            on_error=lambda e: out.update({"error": e}),
            effort=effort)
    finally:
        C.urllib.request.urlopen = _real_urlopen
    return out


PINNED = "deepseek-ai/DeepSeek-V4-Flash"


# ── 1. THINKING IS OFF BY DEFAULT ON THE DEEPSEEK FLASH FAMILY ───────
# v1.2.0.3: the DeepSeek V4/V4.1-Flash family default to a thinking mode that,
# in an agentic tool loop, spends the whole budget reasoning and returns an
# empty answer — "thought for 50,000 characters and said nothing", the loop the
# operator filmed. So enable_thinking:False is now sent by DEFAULT on EVERY
# turn (light/standard/heavy) for any model that HAS a think_off, and the old
# "no extra field unless you opt in" contract is gone for those models.
print("\n== thinking OFF by default on the DeepSeek Flash family ==")
ck("deepseek_thinking defaults to False",
   C.DEFAULT_SETTINGS.get("deepseek_thinking") is False,
   str(C.DEFAULT_SETTINGS.get("deepseek_thinking")))

_run(_settings(), "light", _urlopen_factory())
_def_light = dict(SENT[0])
_run(_settings(), "standard", _urlopen_factory())
_def_std = dict(SENT[0])
_run(_settings(approval_mode="manual"), "heavy", _urlopen_factory())
_def_heavy = dict(SENT[0])
ck("DEFAULT: light turn disables thinking",
   _def_light.get("enable_thinking") is False, str(sorted(_def_light)))
ck("DEFAULT: standard turn disables thinking",
   _def_std.get("enable_thinking") is False, str(sorted(_def_std)))
ck("DEFAULT: heavy turn ALSO disables thinking (this is the build case)",
   _def_heavy.get("enable_thinking") is False, str(sorted(_def_heavy)))

# Opting thinking back ON restores the byte-identical, pre-feature body.
_EXPECTED_KEYS = {"messages", "temperature", "top_p", "max_tokens",
                  "stream", "model"}
_run(_settings(deepseek_thinking=True), "light", _urlopen_factory())
_on_light = dict(SENT[0])
ck("deepseek_thinking=True: no enable_thinking field (thinking restored)",
   "enable_thinking" not in _on_light, str(sorted(_on_light)))
ck("deepseek_thinking=True: body is exactly the pre-feature keys",
   set(_on_light) == _EXPECTED_KEYS, str(set(_on_light) ^ _EXPECTED_KEYS))


# ── 2. only where it belongs ─────────────────────────────────────────
print("\n== the toggle only touches models that have it ==")
ck("DEFAULT: the pinned DeepSeek model is still the one used",
   _def_light.get("model") == PINNED, str(_def_light.get("model")))

# A model with no toggle must not get one invented for it, default or not.
_run(_settings(siliconflow_model="moonshotai/Kimi-K3"), "light",
     _urlopen_factory())
ck("a model with no think_off gets no field by default",
   "enable_thinking" not in SENT[0], str(sorted(SENT[0])))

# The light cap still applies — the toggle must not have replaced it.
ck("light max_tokens cap still applied",
   _def_light.get("max_tokens")
   <= C.DEFAULT_SETTINGS["effort_light_max_tokens"],
   str(_def_light.get("max_tokens")))


# ── 3. rejection is survivable ───────────────────────────────────────
print("\n== a provider that rejects the field ==")
out = _run(_settings(fast_light_turns=True), "light",
           _urlopen_factory(reject_extras=True))
ck("rejected: the turn still SUCCEEDS", not out.get("error"), str(out.get("error")))
ck("rejected: the reply still streamed", out.get("text") == "ok", str(out.get("text")))
ck("rejected: exactly two requests (try, strip, done)", len(SENT) == 2,
   str(len(SENT)))
ck("rejected: retry is the SAME model, not the next in the chain",
   len(SENT) == 2 and SENT[0]["model"] == SENT[1]["model"] == PINNED,
   str([b.get("model") for b in SENT]))
ck("rejected: the retry dropped the field",
   len(SENT) == 2 and "enable_thinking" not in SENT[1],
   str(sorted(SENT[-1])))
ck("rejected: retry body matches the OFF body exactly",
   len(SENT) == 2 and set(SENT[1]) == _EXPECTED_KEYS)

# Second turn on the same backend: the memo must hold.
SENT.clear()
C.urllib.request.urlopen = _urlopen_factory(reject_extras=True)
try:
    r = _router(_settings(fast_light_turns=True))
    for _ in range(3):
        r.stream_chat([{"role": "user", "content": "hi"}],
                      on_token=lambda t: None, on_done=lambda d: None,
                      on_error=lambda e: None, effort="light")
finally:
    C.urllib.request.urlopen = _real_urlopen
ck("memo: 3 turns cost 4 requests, not 6 (one-time degradation)",
   len(SENT) == 4, str(len(SENT)))
ck("memo: only the very first request carried the field",
   sum(1 for b in SENT if "enable_thinking" in b) == 1,
   str([("enable_thinking" in b) for b in SENT]))


# ── 4. a real stale model id still walks the chain ───────────────────
# The strip-retry sits in front of the stale-id recovery, so this is the
# case that proves it did not swallow the path it sits in front of.
print("\n== stale model id is still handled ==")
SENT.clear()
out = _run(_settings(fast_light_turns=True), "light",
           _urlopen_factory(reject_models=(PINNED,)))
_models = [b.get("model") for b in SENT]
ck("stale id: moved on to a different model", len(set(_models)) > 1, str(_models))
ck("stale id: the turn still completed", out.get("text") == "ok",
   str(out.get("error") or out.get("text")))


# ── 5. the escalation gate still behaves ─────────────────────────────
print("\n== effort escalation ==")
SENT.clear()
# v1.2.0.5: an operator-named SAME-FAMILY heavier sibling still escalates the
# model id. PINNED is DeepSeek-V4-Flash; V4.1-Flash is same-family and valid.
_run(_settings(approval_mode="manual",
               hard_engagement_model="deepseek-ai/DeepSeek-V4.1-Flash"),
     "heavy", _urlopen_factory())
ck("heavy: a named same-family sibling still escalates the model id",
   SENT[0].get("model") == "deepseek-ai/DeepSeek-V4.1-Flash",
   str(SENT[0].get("model")))
SENT.clear()
_run(_settings(approval_mode="manual",
               hard_engagement_model="acme/NotAModel"),
     "heavy", _urlopen_factory())
ck("heavy: a bogus heavy model is ignored, not sent",
   SENT[0].get("model") == PINNED, str(SENT[0].get("model")))
SENT.clear()
_run(_settings(adaptive_effort=False, fast_light_turns=True),
     "light", _urlopen_factory())
ck("adaptive_effort=False does NOT re-enable thinking — the think-off "
   "default is a baseline, not a rung of the effort ladder",
   SENT[0].get("enable_thinking") is False, str(sorted(SENT[0])))
SENT.clear()
_run(_settings(adaptive_effort=False, deepseek_thinking=True),
     "light", _urlopen_factory())
ck("deepseek_thinking=True with adaptive_effort=False sends no field",
   "enable_thinking" not in SENT[0], str(sorted(SENT[0])))



# == 4. THE SHIPPED DEFAULT IS A DIFFERENT KIND OF MODEL =============
# GLM-5.3-Flash cannot have its thinking turned off, and OMITTING
# reasoning_effort selects its DEEPEST mode -- so the two dials must not be
# confused. fast_light_turns must invent no toggle for it, and every turn must
# still carry an explicit depth.
print("\n== the shipped default (GLM-5.3-Flash) ==")
_GLM = "zai-org/GLM-5.3-Flash"   # explicitly, not via the default
ck("the shipped default is DeepSeek-V4.1-Flash (v1.2.0.0)",
   C.DEFAULT_SETTINGS["siliconflow_model"] == "deepseek-ai/DeepSeek-V4.1-Flash",
   C.DEFAULT_SETTINGS["siliconflow_model"])
_run(_settings(siliconflow_model=_GLM, fast_light_turns=True), "light",
     _urlopen_factory())
_glm_light = dict(SENT[0])
ck("GLM: fast_light_turns invents no enable_thinking",
   "enable_thinking" not in _glm_light, str(sorted(_glm_light)))
ck("GLM: a light turn still carries an explicit reasoning_effort",
   _glm_light.get("reasoning_effort") in ("low", "high", "max"),
   str(_glm_light.get("reasoning_effort")))
ck("GLM: ...and it is the cheap end on a light turn",
   _glm_light.get("reasoning_effort") == "low",
   str(_glm_light.get("reasoning_effort")))
_run(_settings(siliconflow_model=_GLM), "heavy", _urlopen_factory())
_glm_heavy = dict(SENT[0])
ck("GLM: a HEAVY turn stays on the operator's model instead of swapping "
   "family to hard_engagement_model",
   _glm_heavy.get("model") == _GLM, str(_glm_heavy.get("model")))
ck("GLM: ...and escalates the reasoning dial instead",
   _glm_heavy.get("reasoning_effort") == "max",
   str(_glm_heavy.get("reasoning_effort")))
# v1.2.0.5: hard_engagement_model ships empty, so a default heavy turn on the
# DeepSeek default no longer swaps models — V4.1-Flash IS the best of the three.
# It has no reasoning dial (it uses enable_thinking), so heavy just keeps the
# bigger token budget and stays on the model.
SENT.clear()
_run(_settings(), "heavy", _urlopen_factory())
ck("DeepSeek: a default heavy turn stays on the model (no sibling to escalate)",
   SENT[0].get("model") == PINNED, str(SENT[0].get("model")))
ck("DeepSeek: ...and does not sprout a reasoning_effort dial it lacks",
   "reasoning_effort" not in SENT[0], str(sorted(SENT[0])))
print(f"\neffort: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
