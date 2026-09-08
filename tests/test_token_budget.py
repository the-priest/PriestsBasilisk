#!/usr/bin/env python3
"""
test_token_budget.py — the operator pays for every token this app sends.

WHY THIS EXISTS
===============
Prompt size is the one cost that grows silently. Nobody adds 4,000 tokens in
one commit; it arrives fifty at a time, in edits that each look reasonable,
and the only place it shows up is a bill. So the shipped prompt gets a
ceiling, and the ceiling is a test.

Three properties are pinned here, all measured rather than reasoned about:

  1. THE SHIPPED PROMPT IS THE LAZY ONE. basilisk.py passes
     grouped=(not max_mode), and max_mode ships False — so the real prompt is
     the group-index form (~7.5k), not the every-spec-inline form (~12.4k
     leashed, ~24.2k armed). A change that flips that default, or that makes
     the grouped form stop being meaningfully smaller, is a silent 1.7-3x
     cost increase on every single turn.

  2. THE CACHEABLE PREFIX IS BYTE-STABLE. Providers cache by prefix match.
     Anything that varies per turn must sit at the END of the request or it
     truncates the cached prefix where it appears. A clock at position five
     once did exactly that, throwing away the discount on the whole prompt on
     every turn. Volatile content belongs in volatile_block, and nowhere else.

  3. THE PER-STEP ADDENDUM STAYS SMALL ON CONTINUATIONS. The addendum rides
     the volatile trailing message, which is the part a cache CANNOT reuse, so
     it is billed in full on every step. A hundred-step repo job pays it a
     hundred times: the work contract is ~745 tokens on turn 1 and ~175 on
     continuations, and losing that split costs ~70k tokens per long job.

Run:  python3 tests/test_token_budget.py
"""

from __future__ import annotations

import os
import sys
import time
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


# ── GTK stub, same shape as the other UI-adjacent suites ─────────────
class _Meta(type):
    def __getattr__(cls, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return _Obj


class _Obj(metaclass=_Meta):
    def __init__(self, *a, **k): pass
    def __call__(self, *a, **k): return _Obj()
    def __getattr__(self, n): return _Obj()


class _Mod(types.ModuleType):
    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return _Obj

    def require_version(self, *a, **k): pass


for _m in ("gi", "gi.repository", "gi.repository.Gtk", "gi.repository.Adw",
           "gi.repository.GLib", "gi.repository.Gio", "gi.repository.Gdk",
           "gi.repository.GdkPixbuf", "gi.repository.Pango",
           "gi.repository.GObject", "gi.repository.GtkSource",
           "gi.repository.Vte", "gi.repository.Soup"):
    sys.modules[_m] = _Mod(_m)
sys.modules["gi"].require_version = lambda *a, **k: None

import basilisk as Bk                                            # noqa: E402
import basilisk_core as Bc                                       # noqa: E402
import basilisk_persona as Bp                                    # noqa: E402


def tok(s: str) -> int:
    """~3.6 chars/token is close enough for GLM/DeepSeek BPE on English and
    code. Every figure here is a budget, not an invoice."""
    return int(len(s or "") / 3.6)


# ── 1. THE SHIPPED PROMPT, AND ITS CEILING ───────────────────────────
print("== the prompt the operator actually pays for ==")

_S = Bc.load_settings()
ck("max_mode exists and ships OFF",
   "max_mode" in Bc.DEFAULT_SETTINGS and not _S.get("max_mode"),
   f"max_mode={_S.get('max_mode')}")

_grouped = not _S.get("max_mode", False)
_src = open(os.path.join(_ROOT, "basilisk.py"), encoding="utf-8").read()
ck("basilisk.py derives `grouped` from max_mode (not hard-coded)",
   'grouped=(not self.settings.get("max_mode", False))' in _src,
   "if this is ever hard-coded to False, every turn costs ~1.7x more")

_leashed = Bp.build_system_prompt(grouped=_grouped, unleashed=False)
_armed = Bp.build_system_prompt(grouped=_grouped, unleashed=True)

# Ceilings, not exact values: prose should be free to change, size should not.
LEASHED_CEIL = 8200
ARMED_CEIL = 8800
ck(f"leashed prompt is within budget ({tok(_leashed):,} <= {LEASHED_CEIL:,})",
   tok(_leashed) <= LEASHED_CEIL,
   "the group index exists to keep this small - something is inlining specs")
ck(f"armed prompt is within budget ({tok(_armed):,} <= {ARMED_CEIL:,})",
   tok(_armed) <= ARMED_CEIL)

# The lazy form must stay MEANINGFULLY smaller, or the mechanism is dead
# weight that still costs a code path.
_max_leashed = Bp.build_system_prompt(grouped=False, unleashed=False)
_max_armed = Bp.build_system_prompt(grouped=False, unleashed=True)
ck("the grouped form is much smaller than max mode, leashed",
   tok(_leashed) < tok(_max_leashed) * 0.75,
   f"{tok(_leashed):,} vs {tok(_max_leashed):,}")
ck("…and armed, where the saving is largest",
   tok(_armed) < tok(_max_armed) * 0.5,
   f"{tok(_armed):,} vs {tok(_max_armed):,}")

# Leashed must never cost MORE than armed: the offensive groups are removed,
# not added, so a leashed turn is strictly the cheaper one.
ck("leashed is not more expensive than armed",
   tok(_leashed) <= tok(_armed))

# The group index has to actually be there, or "lazy tools" is a promise the
# model cannot act on: it needs to know what it can load.
ck("the grouped prompt carries a group index",
   "load_tools" in _leashed,
   "without it the model cannot reach the tools that were left out")


# ── 2. THE CACHEABLE PREFIX IS BYTE-STABLE ───────────────────────────
print("\n== the provider's prompt cache is not being thrown away ==")

_a = Bp.build_system_prompt(grouped=_grouped, unleashed=False)
time.sleep(1.1)          # cross a second boundary; a clock inside would show
_b = Bp.build_system_prompt(grouped=_grouped, unleashed=False)
ck("the system prompt is byte-identical across a second boundary", _a == _b,
   "something time-varying is inside the cached prefix")

_hist = [{"role": "user", "content": "fix the auth bug in my repo"}]
_m1 = Bp.assemble_messages(_a, _hist, volatile=Bp.volatile_block("x"))
time.sleep(1.1)
_m2 = Bp.assemble_messages(_b, _hist, volatile=Bp.volatile_block("x"))
ck("everything before the volatile tail is identical between turns",
   _m1[:-1] == _m2[:-1],
   "the cache would break at the first differing byte")
# The property is STRUCTURAL: volatile content is appended as its own final
# message rather than merged into the last real one. (It is NOT that the two
# tails differ — the clock is minute-resolution, so two calls a second apart
# produce the same tail, which is a cache HIT and entirely desirable.)
_vol = Bp.volatile_block("marker-xyz")
_mv = Bp.assemble_messages(_a, _hist, volatile=_vol)
ck("the volatile material is its own TRAILING message",
   _mv[-1]["role"] == "user" and _mv[-1]["content"] == _vol
   and len(_mv) == len(_hist) + 2,
   "merging it into an earlier message ends the cache one message sooner")
ck("…and the real history is left untouched by it",
   _mv[1:-1] == _hist)

_cached = sum(len(m.get("content", "")) for m in _m1[:-1])
ck(f"the cached prefix is worth having ({tok(str(_cached) and ' ' * _cached):,} tok)",
   _cached > 20000, f"{_cached:,} chars")


# ── 3. THE PER-STEP ADDENDUM STAYS SMALL MID-JOB ─────────────────────
print("\n== the part that is billed on every single step ==")


class _Stop(Exception):
    pass


_CAP = {}


def _cap(addendum="", *a, **k):
    _CAP["a"] = addendum
    raise _Stop()


def addendum_for(q, depth=1, mission=False, unleashed=False):
    w = object.__new__(Bk.MainWindow)
    w.settings = dict(Bc.DEFAULT_SETTINGS)
    w.settings["approval_mode"] = "none"
    w._stop_requested = False
    w._tool_ran_this_request = True
    w._tool_chain_depth = depth - 1
    w._tools_locked = False
    w._force_answer_tries = 0
    w.streaming_chat_id = 1
    w.current_chat_id = 1
    w._unleashed = unleashed
    w._mission_active = mission
    w._unleash_kickoff_pending = False
    w._mission_directive = ""
    w._ext = None
    w._action_log = None
    w._error_retries = 0
    w._last_worked = None
    w._recent_commands = []
    w._last_tool_names = []
    w.streaming_msg_widget = None
    w.streaming_msg_db_id = None
    w.router = types.SimpleNamespace(any_available=lambda: True)
    w.store = types.SimpleNamespace(add_message=lambda *a, **k: 1)
    w._mark_turn_progress = lambda *a, **k: None
    w.terminal_log = lambda m, s="": None
    hist = [{"role": "user", "content": q}]
    for _ in range(depth - 1):
        hist += [{"role": "assistant", "content": "ok"},
                 {"role": "user", "content":
                  '<tool_result>\n[tool: run]\n{"ok":true}\n</tool_result>'}]
    w._build_history_for_model = lambda *a, **k: hist
    saved = Bk.volatile_block
    Bk.volatile_block = _cap
    _CAP.pop("a", None)
    try:
        w._kick_assistant_turn()
    except _Stop:
        pass
    finally:
        Bk.volatile_block = saved
    return _CAP.get("a", "")


_w1 = addendum_for("fix the auth bug in my repo", depth=1)
_w8 = addendum_for("fix the auth bug in my repo", depth=8)
_w60 = addendum_for("fix the auth bug in my repo", depth=60)

ck(f"turn 1 gets the full work contract ({tok(_w1):,} tok)", tok(_w1) > 400)
ck(f"a continuation is much cheaper ({tok(_w8):,} tok)",
   tok(_w8) < tok(_w1) * 0.5,
   "the whole contract re-sent every step is ~70k wasted on a long job")
ck("the continuation form does not grow with depth",
   tok(_w60) == tok(_w8), f"turn 8={tok(_w8)} turn 60={tok(_w60)}")

CONT_CEIL = 320
ck(f"the continuation addendum is within budget "
   f"({tok(_w8):,} <= {CONT_CEIL})", tok(_w8) <= CONT_CEIL)

# Cheaper must not mean toothless: these three are the failures that cost the
# operator real work, so they have to survive the trim.
for must, why in (("rest unchanged", "a partial write DELETES the omitted code"),
                  ("TOOL CALL", "narrating instead of calling is the stall"),
                  ("not verified", "a false 'done' is the worst outcome here")):
    ck(f"the cheap form still says {must!r}", must.lower() in _w8.lower(), why)

# Every turn shape stays bounded — no path may quietly balloon.
for label, a in (("leashed question t1", addendum_for("what is the latest nmap", 1)),
                 ("leashed question t8", addendum_for("what is the latest nmap", 8)),
                 ("armed mission t8",
                  addendum_for("own the box", 8, mission=True, unleashed=True))):
    ck(f"{label} addendum is bounded ({tok(a):,} tok)", tok(a) <= 900)


# ── 4. OUTPUT CEILINGS ARE CEILINGS, NOT SPENDS ──────────────────────
print("\n== output budgets ==")
ck("code_write_max_tokens is generous enough for a real file",
   _S.get("code_write_max_tokens", 0) >= 8192,
   "a 400-line file is 6-8k tokens; truncation here corrupts the write")
ck("…and is bounded, so a runaway reply cannot bill forever",
   _S.get("code_write_max_tokens", 0) <= 131072)
ck("ordinary chat keeps a small default",
   _S.get("max_tokens", 0) <= 4096,
   "the big budget is for work turns only, not every reply")
ck("reasoning_effort is sent explicitly",
   isinstance(_S.get("reasoning_effort"), str) and _S["reasoning_effort"],
   "GLM-5.x defaults to its DEEPEST setting when this field is omitted, "
   "which is the single most expensive thing this app could do by accident")


print(f"\ntoken_budget: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
