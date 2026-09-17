#!/usr/bin/env python3
"""
test_degraded_walk.py — the degraded/empty ESCAPE HATCH.

THE BUG THIS GUARDS (the one the operator filmed, over and over): a model
returns an EMPTY reply on this endpoint turn after turn — V4.1-Flash "thought
and said nothing", or a thinking mode the endpoint will not switch off. The
reply is a clean HTTP 200, so the backend's own chain-walk (which only fires on
HTTP *errors*) never triggers, and the host used to just re-ask the SAME model
three times and give up: "stream done / looked degraded / auto-retry, staying on
selected provider" on a loop, for ever.

The fix has two halves, and both are asserted here against the real code rather
than argued for in a comment:

  1. router.stream_chat(model_override=...) — a ONE-TURN override that replaces
     the picked model as the first attempt while the backend still appends the
     rest of the provider's own chain behind it, and thinking-off still reads
     the FINAL model id (so a walk to V4-Flash still gets enable_thinking:False).

  2. _next_chain_model_after(current) — walks to the NEXT model in the active
     provider's OWN fallback chain (V4.1-Flash -> V4-Flash -> GLM-5.3-Flash),
     never a cross-cloud hop, and returns "" at the end of the chain so the
     caller stops rather than looping.

Stdlib only, faked HTTP layer, no GTK needed for half (1); half (2) binds the
unbound method onto a tiny shim so no real window is built.

Run:  python3 tests/test_degraded_walk.py
"""

from __future__ import annotations

import json
import os
import sys
import types

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


# ── fake HTTP layer (same shape as test_effort) ──────────────────────
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


def _urlopen(req, timeout=None):
    body = json.loads(req.data.decode())
    SENT.append(body)
    return _Resp(_OK)


def _settings(**over):
    s = dict(C.DEFAULT_SETTINGS)
    s["active_provider"] = "siliconflow"
    s["siliconflow_api_key"] = "sk-test"
    s["headroom_enabled"] = False
    s["siliconflow_model"] = "deepseek-ai/DeepSeek-V4.1-Flash"
    s.update(over)
    return s


def _router(settings):
    cloud = {}
    for spec in C.PROVIDERS:
        key = settings.get(f"{spec.key}_api_key", "")
        cloud[spec.key] = (C.GroqBackend(key) if spec.engine == "groq"
                           else C.OpenAICompatBackend(spec, key))
    return C.BackendRouter(cloud, settings)


def _run(settings, **kw):
    SENT.clear()
    C.urllib.request.urlopen = _urlopen
    out = {}
    try:
        r = _router(settings)
        r.stream_chat(
            [{"role": "user", "content": "hi"}],
            on_token=lambda t: None,
            on_done=lambda d: out.update(d),
            on_error=lambda e: out.update({"error": e}),
            **kw)
    finally:
        C.urllib.request.urlopen = _real_urlopen
    return out


PINNED = "deepseek-ai/DeepSeek-V4.1-Flash"
BENCH = "deepseek-ai/DeepSeek-V4-Flash"
GLM = "zai-org/GLM-5.3-Flash"


# ── 1. router model_override changes the model actually sent ──────────
print("\n== model_override reaches the wire ==")
_out = _run(_settings())
ck("no override -> the picked (default) model is sent",
   SENT and SENT[0].get("model") == PINNED, str(SENT[:1]))

_out = _run(_settings(), model_override=BENCH)
ck("override -> that model is the FIRST attempt on the wire",
   SENT and SENT[0].get("model") == BENCH, str(SENT[:1]))

# thinking-off must read the FINAL (overridden) model, not the picked one.
ck("thinking-off follows the override (V4-Flash still gets enable_thinking:False)",
   SENT and SENT[0].get("enable_thinking") is False, str(sorted(SENT[0])))

# an empty / whitespace override is ignored (falls back to the picked model),
# so a stale or blank value can never dead-end the turn.
_out = _run(_settings(), model_override="   ")
ck("blank override is ignored -> picked model still sent",
   SENT and SENT[0].get("model") == PINNED, str(SENT[:1]))

_out = _run(_settings(), model_override=None)
ck("None override is ignored -> picked model still sent",
   SENT and SENT[0].get("model") == PINNED, str(SENT[:1]))


# ── 2. _next_chain_model_after walks the provider's own chain ─────────
print("\n== the chain walk (same provider, never a cloud hop) ==")


# GTK stub, same shape as test_promise_gate.py, so basilisk.py imports with no
# real GTK. Installed here (not at module top) because part 1 needs none of it.
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


class _Mod(types.ModuleType):
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
    sys.modules[_m] = _Mod(_m)
sys.modules["gi"].require_version = lambda *a, **k: None

import basilisk as B  # noqa: E402


def _shim(settings):
    """A tiny object carrying just a real router, with the unbound
    _next_chain_model_after method bound onto it. No window is built."""
    obj = types.SimpleNamespace()
    obj.router = _router(settings)
    obj._next_chain_model_after = types.MethodType(
        B.MainWindow._next_chain_model_after, obj)
    return obj


s = _shim(_settings())
ck("V4.1-Flash -> V4-Flash (the benchmarked fallback)",
   s._next_chain_model_after(PINNED) == BENCH, s._next_chain_model_after(PINNED))
ck("V4-Flash -> GLM-5.3-Flash",
   s._next_chain_model_after(BENCH) == GLM, s._next_chain_model_after(BENCH))
ck("GLM-5.3-Flash is last -> '' (stop, do not loop back to the top)",
   s._next_chain_model_after(GLM) == "", repr(s._next_chain_model_after(GLM)))
ck("an off-chain hand-typed id -> the top of the chain",
   s._next_chain_model_after("deepseek-ai/Made-Up-9000") == PINNED,
   s._next_chain_model_after("deepseek-ai/Made-Up-9000"))
ck("empty current -> the top of the chain (something to try)",
   s._next_chain_model_after("") == PINNED, s._next_chain_model_after(""))


# ── 3. the walk terminates: following it repeatedly hits '' ──────────
print("\n== the walk is finite (no infinite escalation) ==")
_seen = []
_cur = PINNED
for _ in range(10):
    _cur = s._next_chain_model_after(_cur)
    if not _cur:
        break
    _seen.append(_cur)
ck("walking from the default reaches the end in <= chain length",
   _seen == [BENCH, GLM], str(_seen))
ck("every walked model is distinct (no cycle)",
   len(_seen) == len(set(_seen)), str(_seen))


# ── 4. defensive: a broken router yields '' rather than raising ──────
print("\n== defensive: never raise, just decline the walk ==")
_broken = types.SimpleNamespace()
_broken.router = types.SimpleNamespace(
    active_cloud=lambda: (_ for _ in ()).throw(RuntimeError("no cloud")))
_broken._next_chain_model_after = types.MethodType(
    B.MainWindow._next_chain_model_after, _broken)
ck("a router that raises -> '' (caller just retries the same model)",
   _broken._next_chain_model_after(PINNED) == "")


print(f"\n{_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
