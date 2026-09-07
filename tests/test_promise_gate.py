#!/usr/bin/env python3
"""
test_promise_gate.py — "okay, fetching the news now." and then the turn ends.

THE REPORTED FAILURE
====================
Operator asks for the news. The model replies with a sentence saying it is
about to fetch it, emits no tool call, and the turn ends. Nothing was fetched.
Asking "did you do it?" starts a fresh turn that has no memory of the promise.

Reported four times. Each previous fix made the app a BETTER READER OF THE
REPLY:

  * reply_intends_action / reply_is_bare_stall  — a phrase list
  * printed_url_target                          — recover a printed link
  * the bare-participle stall clause            — "Okay — fetching the news."

Every one of them is one unseen phrasing away from failing again, which is
exactly what kept happening: each fix caught the sentence in the screenshot
and missed the next one.

THE FIX UNDER TEST
==================
A gate that does not read the reply AT ALL. It reads two facts the app owns:

  1. the operator's question needs a live source (_needs_web_verification),
  2. no web tool ran during the entire request.

If both hold when the turn is about to end, the app runs the search ITSELF and
hands the results back to the model. Wording cannot defeat it, because wording
is not consulted. It fires at most once per request, and once it has fired a
web tool HAS run, so the condition cannot re-arm.

Run:  python3 tests/test_promise_gate.py
"""

from __future__ import annotations

import io
import os
import re
import sys
import types
import urllib.parse

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


# ── GTK stub, same shape as test_turn_directives.py ──────────────────
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

import basilisk as Bk                                           # noqa: E402

SRC = io.open(os.path.join(_ROOT, "basilisk.py"), encoding="utf-8").read()

F = Bk.forced_search_url


# ── 1. the exact reported failure ────────────────────────────────────
# These are the replies from the operator's own screenshots and every close
# variant. NONE of them is consulted by the gate — that is the point — so the
# test asserts on the QUESTION plus "nothing ran", which is all the gate sees.
print("\n== a current-events question with nothing fetched forces a search ==")

NEWS_QUESTIONS = [
    "get me the news",
    "whats going on in the world today",
    "give me the rundown of today's news",
    "any breaking news",
    "catch me up on what happened this week",
    "what is the latest version of nmap",
    "who won the game last night",
    "what's new with GLM 5.3",
    "current events please",
    "top stories",
    "how much does a pixel 10 cost",
    "who is the ceo of anthropic",
]
for q in NEWS_QUESTIONS:
    u = F(q, set(), False)
    ck(f"forces a fetch: {q[:44]!r}", bool(u), u)
    if u:
        ck("   …at a real search URL carrying his question",
           u.startswith("https://html.duckduckgo.com/html/?q=")
           and urllib.parse.quote_plus(q[:300]) in u, u)


# ── 2. it does NOT fire once something was actually fetched ──────────
print("\n== a turn that really did go and look is left alone ==")
for tool in ("web_read", "web_search", "open_url", "web_sources",
             "image_search"):
    ck(f"{tool} counts as having looked",
       F("get me the news", {tool}, False) is None)
ck("a mix counts too",
   F("whats the latest nmap", {"run", "web_read"}, False) is None)
ck("an unrelated tool does NOT count as having looked",
   F("get me the news", {"run", "list_dir", "workspace_read"}, False)
   is not None)


# ── 3. it fires at most once per request ─────────────────────────────
print("\n== the gate is a floor, not a loop ==")
ck("already-forced returns None even with nothing fetched",
   F("get me the news", set(), True) is None)
ck("…and that is the ONLY thing already_forced changes",
   F("get me the news", set(), False) is not None)


# ── 4. it never fires on a question the model can answer itself ──────
# A false positive here is its own bug: a needless fetch on every coding
# question, and a search-results page shoved into a conversation that did not
# ask for one.
print("\n== timeless and coding questions are never hijacked ==")
QUIET = [
    "explain how tcp works",
    "what is a buffer overflow",
    "write a python function to reverse a string",
    "fix the auth bug in my repo",
    "refactor the parser into three modules",
    "why is my regex not matching",
    "how do i grep recursively",
    "the tests are failing, sort it out",
    "concurrent processing in asyncio",
    "hello",
    "thanks",
]
for q in QUIET:
    ck(f"no forced fetch: {q[:44]!r}", F(q, set(), False) is None,
       F(q, set(), False))


# ── 5. it is TOTAL — a gate that raises fails open ───────────────────
print("\n== junk in, None out (never an exception) ==")
for junk in (None, 123, b"x", [], {}, object(), "", "  ", "a"):
    try:
        r = F(junk, set(), False)
        ck(f"no raise on {type(junk).__name__}", r is None or isinstance(r, str))
    except Exception as e:
        ck(f"no raise on {type(junk).__name__}", False, f"{type(e).__name__}: {e}")
for junk_tools in (None, 5, "web_read", object()):
    try:
        F("get me the news", junk_tools, False)
        ck(f"no raise on tools={type(junk_tools).__name__}", True)
    except Exception as e:
        ck(f"no raise on tools={type(junk_tools).__name__}", False, str(e))
# A STRING of tool names must not accidentally satisfy the "already looked"
# test by character containment — set("web_read") is a set of letters.
ck("a bare string is not mistaken for a tool set",
   F("get me the news", "web_read", False) is not None)


# ── 6. the wiring: the decision is actually consulted, and acted on ──
print("\n== the gate is wired into the end of the turn ==")
ck("the turn records WHICH tools ran, by name",
   "_tools_used_this_request" in SRC
   and re.search(r"self\._tools_used_this_request\.add\(call\.name\)", SRC)
   is not None)
ck("…and resets that per request, not per round-trip",
   re.search(r"self\._tools_used_this_request = set\(\)", SRC) is not None)
ck("the operator's question is captured for the gate",
   re.search(r"self\._turn_question = ", SRC) is not None)
ck("the completion path calls the gate",
   "forced_search_url(" in SRC.split("def _on_stream_done_body", 1)[-1])
ck("…and turns its answer into a REAL web_read call",
   re.search(r"forced_search_url\([\s\S]{0,400}?"
             r'<tool name="web_read">', SRC) is not None)
ck("…and marks it done so it cannot loop",
   re.search(r"forced_search_url\([\s\S]{0,600}?"
             r"self\._forced_fetch_done = True", SRC) is not None)
ck("the flags are CLASS attributes (the GTK stub makes getattr truthy)",
   re.search(r"^\s+_tools_used_this_request: set = ", SRC, re.M) is not None
   and re.search(r"^\s+_forced_fetch_done: bool = False", SRC, re.M) is not None)
# The guard clause, taken as everything between the block's own anchor comment
# and the call it guards — so the assertions cannot be broken by the comment
# above them growing or shrinking, which is a property of the prose, not of
# the code.
_GATE = SRC.split("THE PROMISE GATE: THE APP FETCHES", 1)[-1].split("forced_search_url(", 1)[0]
ck("the gate block is findable by its anchor", 200 < len(_GATE) < 6000,
   len(_GATE))
ck("it never fires during a mission (that loop has its own recovery)",
   "not self._mission_active" in _GATE, repr(_GATE[-400:]))
ck("it never fires on a cancelled or stopped turn",
   "not cancelled" in _GATE and "not self._stop_requested" in _GATE,
   repr(_GATE[-400:]))
ck("it never overrides tool calls the model DID emit",
   "not executable" in _GATE, repr(_GATE[-400:]))
ck("the model is told the search was run for it",
   "the search was run FOR you" in SRC)


# ── 7. the work-mode half of the same promise ────────────────────────
print("\n== a leashed WORK turn gets told saying-it-is-not-doing-it ==")
ck("work turns are classified, not guessed",
   "leashed_intent(" in SRC)
ck("the work nudge names the real failure",
   "NOTHING WAS WRITTEN AND NOTHING RAN" in SRC)
ck("…and says a fenced block changes nothing",
   "a fenced" in SRC and "changes no file" in SRC)
ck("work turns get a bigger stall budget than answer turns",
   re.search(r"ANSWER_STALL_NUDGE_MAX \* 2 if _work_turn", SRC) is not None)


print(f"\npromise_gate: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
