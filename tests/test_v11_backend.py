#!/usr/bin/env python3
"""test_v11_backend.py — the learned max_tokens ceiling and the scaled wall cap.

Both sit on the path EVERY turn takes, so a mistake here is not a corner case,
it is every reply. This suite caught a bad one: `"token"` was in the auth-word
list, so a 400 saying "max_tokens is too large for this model" came back to
the operator as "authentication failed (HTTP 400). Check the API key" — which
sends him to re-paste a key that was never wrong, while the real problem (an
output budget one notch too high) went unreported and unretried.
"""
import io
import json
import os
import sys
import types
import urllib.error
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
import basilisk_core as C

bad = []


def note(msg):
    bad.append(msg)


# ── 1. wall_cap_for: monotonic, bounded, total ──────────────────────
prev = 0.0
for mt in (1, 512, 2048, 2049, 3000, 4096, 8192, 16384, 65536, 131072, 10**9):
    v = C.wall_cap_for(mt)
    if v < C.STREAM_MAX_WALL_S:
        note(f"wall_cap_for({mt}) = {v} is BELOW the historical floor")
    if v > C.STREAM_WALL_HARD_MAX_S:
        note(f"wall_cap_for({mt}) = {v} exceeds the hard max")
    if v < prev:
        note(f"wall_cap_for is not monotonic at {mt}: {prev} -> {v}")
    prev = v
if C.wall_cap_for(2048) != float(C.STREAM_MAX_WALL_S):
    note("wall_cap_for(2048) must be exactly the historical 150s default")
for junk in (None, "x", [], {}, object(), float("nan"), float("inf"),
             -1, True, False, b"4096"):
    try:
        v = C.wall_cap_for(junk)
        if not isinstance(v, float) or v <= 0:
            note(f"wall_cap_for({junk!r}) returned {v!r}")
    except Exception as e:
        note(f"wall_cap_for RAISED on {junk!r}: {type(e).__name__}")


# ── 2. the learned max_tokens ceiling on the OpenAI-compatible backend ──
class _FakeHTTPError(urllib.error.HTTPError):
    def __init__(self, code, body):
        self._body = body.encode()
        super().__init__("http://x", code, "err", {}, io.BytesIO(self._body))

    def read(self):
        return self._body


def make_backend(chain=("model-a", "model-b")):
    spec = types.SimpleNamespace(
        key="probe", base_url="https://example.invalid/v1",
        chain=list(chain), extra_headers={}, engine="openai")
    b = C.OpenAICompatBackend(spec, api_key="k")
    return b


def run(backend, reject_fn, max_tokens=16384):
    """Drive stream_chat with a urlopen that calls reject_fn(payload)."""
    seen = []

    def fake_urlopen(req, timeout=None):
        payload = json.loads(req.data.decode())
        seen.append(payload)
        err = reject_fn(payload)
        if err is not None:
            raise err
        class _R:
            def __enter__(self_): return self_
            def __exit__(self_, *a): return False
            def __iter__(self_):
                yield b'data: {"choices":[{"delta":{"content":"hi"},"finish_reason":"stop"}]}'
                yield b'data: [DONE]'
        return _R()

    real = urllib.request.urlopen
    urllib.request.urlopen = fake_urlopen
    out = {}
    try:
        backend.stream_chat(
            "model-a", [{"role": "user", "content": "x"}],
            on_token=lambda t: None,
            on_done=lambda d: out.update(d or {}),
            on_error=lambda e: out.update({"error": e}),
            options={"max_tokens": max_tokens})
    finally:
        urllib.request.urlopen = real
    return seen, out


# 2a. a provider that refuses anything over 4096 must be found by halving,
#     on the SAME model, and the turn must still succeed.
b = make_backend()
def reject_over_4096(p):
    if p["max_tokens"] > 4096:
        return _FakeHTTPError(400, json.dumps(
            {"error": {"message": "max_tokens is too large for this model"}}))
    return None
seen, out = run(b, reject_over_4096)
if out.get("error"):
    note(f"2a: a recoverable max_tokens rejection FAILED the turn: {out['error']}")
if out.get("text") != "hi":
    note(f"2a: the turn did not complete after halving: {out!r}")
models = [p["model"] for p in seen]
if set(models) != {"model-a"}:
    note(f"2a: halving must retry the SAME model, walked the chain instead: {models}")
budgets = [p["max_tokens"] for p in seen]
if budgets != [16384, 8192, 4096]:
    note(f"2a: expected 16384->8192->4096, got {budgets}")

# 2b. the ceiling is REMEMBERED — a second turn must not re-pay the probe
seen2, out2 = run(b, reject_over_4096)
if [p["max_tokens"] for p in seen2] != [4096]:
    note(f"2b: the learned ceiling was not reused: "
         f"{[p['max_tokens'] for p in seen2]}")
if out2.get("text") != "hi":
    note("2b: second turn did not complete")

# 2c. a request BELOW the learned ceiling must not be raised to it
seen3, out3 = run(b, reject_over_4096, max_tokens=1000)
if [p["max_tokens"] for p in seen3] != [1000]:
    note(f"2c: the cap raised a small request: {[p['max_tokens'] for p in seen3]}")

# 2d. halving must terminate — a provider that refuses everything must not spin
b2 = make_backend(chain=("model-a",))
calls = {"n": 0}
def reject_all(p):
    calls["n"] += 1
    if calls["n"] > 40:
        raise AssertionError("runaway retry loop")
    return _FakeHTTPError(400, json.dumps(
        {"error": {"message": "max_tokens exceeds the limit"}}))
try:
    seen4, out4 = run(b2, reject_all)
    if calls["n"] > 12:
        note(f"2d: too many retries before giving up: {calls['n']}")
    if not out4.get("error"):
        note("2d: a permanently-refusing provider must surface an error")
except AssertionError as e:
    note(f"2d: {e}")

# 2e. a 400 that is NOT about max_tokens must NOT be misread as one
b3 = make_backend()
def reject_badreq(p):
    return _FakeHTTPError(400, json.dumps(
        {"error": {"message": "invalid role in messages[0]"}}))
seen5, out5 = run(b3, reject_badreq)
if any(p["max_tokens"] != 16384 for p in seen5):
    note(f"2e: an unrelated 400 halved the budget: "
         f"{[p['max_tokens'] for p in seen5]}")

# 2f. an AUTH failure must still short-circuit, not get eaten by the new branch
b4 = make_backend()
def reject_auth(p):
    return _FakeHTTPError(401, json.dumps(
        {"error": {"message": "invalid api key"}}))
seen6, out6 = run(b4, reject_auth)
if "authentication" not in (out6.get("error") or "").lower():
    note(f"2f: auth failure no longer reported as auth: {out6.get('error')!r}")
if len(seen6) != 1:
    note(f"2f: auth failure walked the chain ({len(seen6)} attempts)")

# 2g. the wall cap actually applied is derived from the SENT budget, not the
#     module constant — assert the code reads the payload, at source level.
SRC = io.open(os.path.join(_ROOT, "basilisk_core.py"), encoding="utf-8").read()
if 'wall_cap_for(payload.get("max_tokens"))' not in SRC:
    note("2g: the http backend does not derive its wall cap from the payload")
if "wall_cap_for(_mt)" not in SRC:
    note("2g: the groq backend does not derive its wall cap from the budget")
if SRC.count("> STREAM_MAX_WALL_S") != 0:
    note("2g: a flat STREAM_MAX_WALL_S comparison survives somewhere")

print("\n".join(bad) if bad else "no findings")
print(f"\nv11_backend: {len(bad)} finding(s)")
sys.exit(1 if bad else 0)
