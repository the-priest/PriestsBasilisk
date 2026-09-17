#!/usr/bin/env python3
"""
test_speech.py — what the operator HEARS must be the reply, and only the reply.

THE REPORTED FAILURE
====================
Two symptoms, one disease:

  1. "it says dsml"  — the speaker read `<｜DSML｜｜tool name="run">` out loud.
     The operator was right that those letters are nowhere in the reply: they
     are in the TRANSPORT, and the transport was being spoken.

  2. "it speaks its thoughts" — after finishing the reply the speaker went back
     and read the model's <think> chain-of-thought, then repeated the reply.

THE ROOT CAUSE
==============
Basilisk canonicalises model output ONCE, at the boundary, and every consumer
is supposed to sit downstream of that: parse_tool_calls normalises before
matching, set_content renders from the normalised text, the stored message is
the normalised one.  README states the invariant outright.

Speech was the ONE consumer still sitting UPSTREAM of it.  So it had grown its
own, dialect-blind stripping in basilisk_voice, and:

  • the TTS suspend guard asked `"<tool" in content` — a literal substring that
    is FALSE for `<｜DSML｜｜tool …>`, `<invoke …>` and `<function=…>` — so on
    those dialects it never fired and the speaker ran straight through the call;
  • SpeechStreamer tracks a prefix ACROSS CALLS, and the GUI fed it
    think-stripped text per token but the RAW final text at flush.  Two
    different strings, so the line bookkeeping indexed into the wrong one and
    re-folded lines that were never new — the chain-of-thought.

Both are contract failures, not missing patterns.  So the fixes are structural:
speakable_text() is the single transform (mirroring the display chain exactly),
contains_tool_markup() is dialect-blind, SpeechStreamer CHECKS its contract
instead of assuming it, and basilisk_voice scrubs protocol at the one choke
point every spoken line passes through.

Run:  python3 tests/test_speech.py
"""

from __future__ import annotations

import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import basilisk_voice as V                                     # noqa: E402
from basilisk_core import (                                    # noqa: E402
    speakable_text, contains_tool_markup, strip_think_blocks,
    _normalise_tool_syntax)

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


PIPE = "｜"     # ｜  FULLWIDTH VERTICAL LINE
SEP = "▁"      # ▁  LOWER ONE EIGHTH BLOCK

# Anything in here reaching a speaker is the bug this file exists to prevent.
SPOKEN_MARKUP = re.compile(
    r"DSML|" + PIPE + "|" + SEP +
    r"|<\s*/?\s*tool\b|<\s*/?\s*invoke\b|<\s*/?\s*parameter\b"
    r"|<\s*/?\s*think\b|<\s*function\s*=", re.I)


def dsml_call():
    return (f'<{PIPE}DSML{PIPE}{PIPE}tool name="run">\n'
            f'<{PIPE}DSML{PIPE}{PIPE}parameter name="command" string="true">'
            f'nmap -sV 10.0.0.5</{PIPE}DSML{PIPE}{PIPE}parameter>\n'
            f'</{PIPE}DSML{PIPE}{PIPE}invoke>\n'
            f'</{PIPE}DSML{PIPE}{PIPE}tool>')


DIALECTS = {
    "canonical": '<tool name="run">{"command": "id"}</tool>',
    "DSML (DeepSeek-V4)": dsml_call(),
    "invoke": ('<invoke name="run">\n<parameter name="command">id'
               '</parameter>\n</invoke>'),
    "function=": '<function=web_read>{"url": "https://example.com"}</function>',
    "DeepSeek native": (f'<{PIPE}tool{SEP}calls{SEP}begin{PIPE}>'
                        f'<{PIPE}tool{SEP}call{SEP}begin{PIPE}>function'
                        f'<{PIPE}tool{SEP}sep{PIPE}>run\n```json\n'
                        f'{{"command":"id"}}\n```'
                        f'<{PIPE}tool{SEP}call{SEP}end{PIPE}>'),
    "tool_call": '<tool_call>{"name":"run","arguments":{"command":"id"}}</tool_call>',
}


# ── 1. the suspend guard must be dialect-blind ───────────────────────
# This is the exact defect: `"<tool" in text` is False for four of these six.
print("\n== the TTS suspend guard sees every dialect ==")
for name, call in DIALECTS.items():
    ck(f"contains_tool_markup detects {name}",
       contains_tool_markup("Checking that host.\n" + call), repr(call)[:80])

ck("…and does NOT fire on ordinary prose",
   not contains_tool_markup("Port 22 runs OpenSSH 9.6 and port 80 is nginx."))
ck("…nor on prose that merely says the word tool",
   not contains_tool_markup("I will use a different tool for this step."))


# ── 2. nothing a human hears contains protocol ───────────────────────
print("\n== no dialect survives into speech ==")
for name, call in DIALECTS.items():
    raw = "Let me check that host.\n" + call + "\nThat host is up."
    spoken = V.clean_for_speech(speakable_text(raw))
    ck(f"{name} is never spoken", not SPOKEN_MARKUP.search(spoken),
       repr(spoken)[:120])
    ck(f"…and the prose around {name} survives", "host" in spoken,
       repr(spoken)[:120])


# ── 3. reasoning is never spoken ─────────────────────────────────────
print("\n== the model's private reasoning stays private ==")
THINK = ("<think>\nThe user asked me to scan the host.\n"
         "I should not admit I am unsure about the subnet.\n</think>\n"
         "The host is up and running three services.\n"
         "Port 22 is OpenSSH and port 80 is nginx.\n")
_sp = V.clean_for_speech(speakable_text(THINK))
ck("no <think> markup is spoken", not SPOKEN_MARKUP.search(_sp), repr(_sp))
ck("no reasoning CONTENT is spoken", "subnet" not in _sp, repr(_sp))
ck("the actual reply is still spoken", "OpenSSH" in _sp, repr(_sp))


# ── 4. the streamer's contract is CHECKED, not assumed ───────────────
# Feeding one transform per token and a different one at flush is what read the
# chain-of-thought back at the operator.  The streamer must now refuse to
# re-speak rather than trust the caller.
print("\n== SpeechStreamer defends its own contract ==")
st = V.SpeechStreamer()
_out = []
_acc = ""
for i in range(0, len(THINK), 9):
    _acc += THINK[i:i + 9]
    _out.extend(st.feed(speakable_text(_acc)))
_out.extend(st.flush(speakable_text(THINK)))
_joined = " ".join(_out)
ck("streaming then flushing speaks the reply exactly once",
   _joined.count("OpenSSH") == 1, repr(_out))
ck("…and never reaches the reasoning", "subnet" not in _joined, repr(_out))

# The violation itself: hand it a DIFFERENT string at flush, as the GUI used to.
st2 = V.SpeechStreamer()
_a = []
_acc = ""
for i in range(0, len(THINK), 9):
    _acc += THINK[i:i + 9]
    _a.extend(st2.feed(strip_think_blocks(_acc)))       # stripped, per token
_a.extend(st2.flush(_normalise_tool_syntax(THINK)))      # RAW at flush — the bug
_j = " ".join(_a)
ck("a contract violation resyncs instead of re-speaking reasoning",
   "subnet" not in _j, repr(_a))
ck("…and does not repeat the reply either",
   _j.count("OpenSSH") <= 1, repr(_a))


# ── 5. the voice module is the last line of defence ──────────────────
# Callers are supposed to hand it speakable_text() output.  If one ever forgets,
# the operator must get SILENCE, not a recital of the transport.
print("\n== basilisk_voice scrubs protocol even when the caller forgets ==")
for name, call in DIALECTS.items():
    spoken = V.clean_for_speech("Checking.\n" + call + "\nDone.")
    ck(f"raw {name} handed straight to clean_for_speech is still not spoken",
       not SPOKEN_MARKUP.search(spoken), repr(spoken)[:120])

_raw_stream = V.SpeechStreamer()
_frag = "Checking.\n" + dsml_call() + "\nDone.\n"
_said = " ".join(_raw_stream.feed(_frag) + _raw_stream.flush(_frag))
ck("…and the same is true through the streaming path",
   not SPOKEN_MARKUP.search(_said), repr(_said)[:160])


# ── 6. display and speech agree ──────────────────────────────────────
# They are the same message reaching the operator through two senses; if they
# can disagree, one of them is wrong.  A third transform is how this bug
# happened, so the property is asserted rather than left to convention.
print("\n== what is shown and what is said agree ==")
for name, call in DIALECTS.items():
    raw = "Let me check that host.\n" + call + "\nThat host is up."
    ck(f"speakable_text leaves no debris for {name}",
       not SPOKEN_MARKUP.search(speakable_text(raw)),
       repr(speakable_text(raw))[:120])

ck("speakable_text is idempotent",
   speakable_text(speakable_text(THINK)) == speakable_text(THINK))
ck("speakable_text on empty input is safe", speakable_text("") == "")
ck("speakable_text on None-ish input is safe", speakable_text(None) == "")
ck("plain prose passes through untouched",
   speakable_text("Port 22 is open.") == "Port 22 is open.")


print(f"\nspeech: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
