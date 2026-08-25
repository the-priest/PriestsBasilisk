#!/usr/bin/env python3
"""
test_dispatch.py — every tool the persona advertises must actually run.

WHY THIS EXISTS
===============
basilisk.py has two places a tool name can be resolved:

  * `_pure_tool_fn`  — the parallel batch path, for read-only tools that can
                       run together in one turn, and
  * `dispatch`       — the map a SINGLE tool call goes through.

They are maintained by hand and they drift. v7.10.0 hit this and routed the
seventeen workspace tools through one shared mapper because of it. The drift is
invisible in normal use: a tool wired into one path works perfectly until it is
called the other way, and then it fails with a message the operator never sees
because the model swallows it.

This suite found the oracle in exactly that state. `oracle_arm`, `oracle_check`,
`oracle_status` and `oracle_listen` were in `_pure_tool_fn` only, so calling
`oracle_check` on its own — which is the normal way it is used, immediately
after firing an exploit — fell through to:

    self._feed_tool_result(f"Unknown tool '{call.name}'.")

The oracle is the verified-exploitation core. "No proof, no finding" depends on
it entirely, and every benchmark number in the README was produced with it. A
silent "unknown tool" turns every confirmed hit back into an assumption.

So the property here is blunt: the set of tools the persona SELLS and the set of
tools the app can RUN must be the same set. A tool the model is told it has and
cannot call is worse than one that does not exist — it will keep trying.

Run:  python3 tests/test_dispatch.py
"""

from __future__ import annotations

import io
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import basilisk_persona as kp                                   # noqa: E402

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

# Tools the persona tells the model it has.
ADVERTISED = set(re.findall(r'<tool name="([a-z_0-9]+)"', kp.TOOL_CONTRACT))

# The live single-call map: everything between `dispatch = {` and the lookup.
_i = SRC.index("        dispatch = {")
_j = SRC.index("        fn = dispatch.get(call.name)")
_BLOCK = SRC[_i:_j]
DISPATCH = set(re.findall(r'"([a-z_0-9]+)"\s*[:,]', _BLOCK))

# The parallel batch path.
PURE = set(re.findall(r'n == "([a-z_0-9]+)"', SRC))
for _g in re.findall(r'n in \(([^)]{0,400})\)', SRC):
    PURE |= set(re.findall(r'"([a-z_0-9]+)"', _g))

# Handled before dispatch, by the proposal-card path rather than the map.
CARD_HANDLED = {"propose", "propose_edit", "write_file"}


print("== the advertised set and the runnable set must match ==")
print(f"     advertised={len(ADVERTISED)}  dispatch={len(DISPATCH)}  "
      f"batch={len(PURE & ADVERTISED)}")

_unreachable = sorted(ADVERTISED - DISPATCH - CARD_HANDLED)
ck("every advertised tool is reachable by a SINGLE call",
   not _unreachable,
   f"unreachable: {_unreachable}")

for _t in sorted(CARD_HANDLED & ADVERTISED):
    ck(f"{_t} is handled by the card path before dispatch",
       f'call.name in ("propose", "propose_edit", "write_file")' in SRC
       or f'"{_t}"' in SRC)

# The oracle specifically — this is what the suite was written for, so name it
# rather than letting it hide inside an aggregate.
print("\n== the oracle is callable on its own ==")
for _o in ("oracle_arm", "oracle_check", "oracle_status", "oracle_listen"):
    ck(f"{_o} is advertised", _o in ADVERTISED)
    ck(f"{_o} is in the single-call dispatch map", _o in DISPATCH,
       "was batch-path only; a lone oracle_check returned 'Unknown tool'")
    ck(f"{_o} is in the batch path too", _o in PURE)

# A tool in ONE path only is the drift signature. Read-only tools that only
# appear in the batch path are the dangerous direction, because a single call
# to one of them dead-ends.
print("\n== no tool lives in the batch path alone ==")
_batch_only = sorted((PURE & ADVERTISED) - DISPATCH - CARD_HANDLED)
ck("nothing is batch-only", not _batch_only, f"batch-only: {_batch_only}")

print("\n== the unknown-tool path is honest ==")
ck("an unknown tool feeds a result rather than hanging",
   "Unknown tool" in SRC and "_feed_tool_result(f\"Unknown tool" in SRC,
   "the turn loop only advances on a fed result — a silent drop hangs it")
ck("an unknown tool is logged for the operator",
   'f"✗ unknown tool: {call.name}"' in SRC)

print("\n== the persona does not advertise a tool that isn't built ==")
# The reverse direction: a name in the contract with no implementation anywhere.
_ghost = sorted(ADVERTISED - DISPATCH - PURE - CARD_HANDLED)
ck("no advertised tool is entirely unimplemented", not _ghost, str(_ghost))

print("\n== group specs stay reachable ==")
_grouped = set()
for _t in kp.SPECIALIST_GROUPS.values():
    _grouped |= set(re.findall(r'<tool name="([a-z_0-9]+)"', _t))
_core = set(re.findall(r'<tool name="([a-z_0-9]+)"', kp.CORE_TOOLS_TEXT))
ck("every advertised tool is in core or a loadable group",
   ADVERTISED == (_core | _grouped),
   str(sorted(ADVERTISED ^ (_core | _grouped)))[:160])
ck("every tool in a group is runnable",
   not sorted(_grouped - DISPATCH - CARD_HANDLED),
   str(sorted(_grouped - DISPATCH - CARD_HANDLED))[:160])
ck("every core tool is runnable",
   not sorted(_core - DISPATCH - CARD_HANDLED),
   str(sorted(_core - DISPATCH - CARD_HANDLED))[:160])


# ── SETTINGS UI: no dead controls, no missing ones ───────────────────
# A Settings row that writes a key nothing reads is a button that does nothing,
# and a setting the operator needs with no row is a limit he cannot move. Both
# are invisible without a check like this — the app looks fine either way.
print("\n== settings UI matches the schema ==")
import basilisk_core as kc                                      # noqa: E402
import os as _os

_ALL = ""
for _r, _d, _fs in _os.walk(_ROOT):
    _d[:] = [x for x in _d if x not in ("__pycache__", ".git", "tests",
                                        "videos", "benchmarks")]
    for _fn in _fs:
        if _fn.endswith(".py"):
            _ALL += io.open(_os.path.join(_r, _fn), encoding="utf-8").read()

_UI_WRITES = set(re.findall(r'self\._set\(\s*"([a-z_0-9]+)"', SRC))
_READ = set(re.findall(r'\bget\(\s*"([a-z_0-9]+)"', _ALL))
_SCHEMA = set(kc.DEFAULT_SETTINGS)
_PROVIDER_KEYS = ({f"{p.key}_api_key" for p in kc.PROVIDERS}
                  | {f"{p.key}_model" for p in kc.PROVIDERS}
                  | {"groq_api_key"})   # Whisper STT keeps its own key row

_ghost = sorted(_UI_WRITES - _SCHEMA - _PROVIDER_KEYS)
ck("no Settings control writes a key outside the schema", not _ghost,
   f"dead controls: {_ghost}")

_unread = sorted(_UI_WRITES - _READ - _PROVIDER_KEYS)
ck("every Settings control writes something the app reads", not _unread,
   f"controls nothing reads: {_unread}")

# A key can be read INDIRECTLY — basilisk_voice.py stores
# {"model_setting": "stt_model_siliconflow"} and does settings.get(spec[...]),
# which no `.get("literal")` regex can see. An earlier draft of this check
# called that setting dead and would have had me delete a live one. So count a
# key as used if it appears as a quoted string anywhere outside its own
# DEFAULT_SETTINGS definition.
_DEFN = io.open(_os.path.join(_ROOT, "basilisk_core.py"), encoding="utf-8").read()
_defn_i = _DEFN.index("DEFAULT_SETTINGS")
_SCHEMA_BLOCK = _DEFN[_defn_i:_DEFN.index("\n}\n", _defn_i)]
_USED_ANYWHERE = {k for k in _SCHEMA
                  if _ALL.count(f'"{k}"') > _SCHEMA_BLOCK.count(f'"{k}"')}
_dead_settings = sorted(_SCHEMA - _READ - _USED_ANYWHERE - _PROVIDER_KEYS)
ck("no setting in the schema is never used", not _dead_settings,
   f"dead settings: {_dead_settings}")

# The limits the operator is realistically going to want to move must be
# reachable from Settings, not only by hand-editing JSON.
for _k in ("answer_tool_budget", "unleashed"):
    ck(f"{_k} is in the schema", _k in _SCHEMA)
ck("research depth has a Settings control",
   "answer_tool_budget" in _UI_WRITES,
   "he hit this cap in real use; it was a hardcoded 18 with no row")

# Groq is gone as a chat provider but still transcribes. The picker offers it,
# so there must be somewhere to put the key.
ck("the transcription picker still offers Groq Whisper",
   '"groq"' in SRC and "Whisper" in SRC)
ck("a Groq key row exists for Whisper",
   'self._set("groq_api_key"' in SRC,
   "the picker offered an option with nowhere to enter its key")
ck("no removed provider gets a chat key row",
   all(p.key not in ("groq", "google") for p in kc.PROVIDERS))


print(f"\ndispatch: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
