#!/usr/bin/env python3
"""
test_fabrication.py — the model writing the HOST's lines.

THE REPORTED FAILURE
====================
Screenshot from a live GLM-5.3-Flash run. One question, "can you give me some
news", produced a single assistant bubble containing the model's narration
INTERLEAVED WITH TWO COMPLETE TOOL RESULTS:

    Checking the two open cases first, then general news. Fetching updates
    on both.[UNTRUSTED WEB CONTENT] Tool result (web_read - google_news):
    {"url": "...", "status": 200, "items": [...]}
    [END UNTRUSTED WEB CONTENT]
    Verifying the arrest report on the RTE page itself before I call it.
    [UNTRUSTED WEB CONTENT] Tool result (web_read): {...}

...while the activity feed said `1 step complete`.

The model wrote both sides of the conversation. It invented the fetches, the
URLs, the HTTP 200s and the article bodies, and reasoned on top of them as if
they had been retrieved. For an agent whose entire premise is "no proof, no
finding", a forged tool result is the worst reachable output: it is
indistinguishable from evidence to the person reading it, and once stored it is
replayed to the model as history every later turn, teaching it that writing
results is acceptable.

WHY IT IS DETECTABLE WITH CERTAINTY, not guessed at: every marker below is
emitted by the HOST and only by the host — webshield's envelope, the
tool_result wrapper. Nothing in this application can place one inside an
ASSISTANT message. Its presence in model output is proof, not evidence.

WHY IT HAPPENS: tool results are fed back as `user`-role messages inside that
envelope. A model trained on a dedicated tool/observation role reads it as "the
user writes tool results" and completes the pattern. Changing the envelope is
the deeper fix and a dangerous one (nine places test `"<tool_result>" in
content` as a literal), so the envelope stays byte-identical and the imitation
is caught instead.

Run:  python3 tests/test_fabrication.py
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import basilisk_core as C                                      # noqa: E402
from basilisk_core import (                                    # noqa: E402
    fabricated_tool_result, strip_fabricated_results)

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


# The host's real envelope, built the way webshield builds it.
ENV = ("⟦UNTRUSTED WEB CONTENT⟧\n"
       "source: https://news.google.com/rss/search?q=x\n"
       "───── BEGIN UNTRUSTED DATA ─────\n"
       '{"url": "https://news.google.com/rss", "status": 200,\n'
       ' "items": [{"title": "Gardai arrest man"}]}\n'
       "───── END UNTRUSTED DATA ─────\n"
       "⟦END UNTRUSTED WEB CONTENT⟧")

# The screenshot, reconstructed.
SCREENSHOT = (
    "Checking the two open cases first, then general news. Fetching updates "
    "on both." + ENV + "\n"
    "Verifying the arrest report on the RTE page itself before I call it."
    + ENV + "\n"
    "So: a man in his 30s was arrested on 5 September.")


print("\n== the forged result is detected ==")
ck("the screenshot's reply is flagged", bool(fabricated_tool_result(SCREENSHOT)))
ck("a <tool_result> wrapper is flagged",
   bool(fabricated_tool_result("Done.<tool_result>{\"ok\":true}</tool_result>")))
ck("a bare BEGIN UNTRUSTED DATA rule is flagged",
   bool(fabricated_tool_result("x ----- BEGIN UNTRUSTED DATA ----- y")))
ck("an ordinary reply is NOT flagged",
   not fabricated_tool_result(
       "Gardai arrested a man in his 30s; RTE reported it on 5 September."))
ck("a reply that merely mentions fetching is NOT flagged",
   not fabricated_tool_result(
       "I'll fetch the RTE page and the Google News feed, then compare them."))
ck("empty text is not flagged", not fabricated_tool_result(""))


print("\n== the forgery is removed and the model's own words survive ==")
_clean, _n = strip_fabricated_results(SCREENSHOT)
ck("both forged spans are removed", _n == 2, str(_n))
ck("no envelope survives", not fabricated_tool_result(_clean), repr(_clean)[:160])
ck("no fabricated status code survives", '"status": 200' not in _clean)
ck("no fabricated URL survives", "news.google.com/rss" not in _clean)
for _keep in ("Checking the two open cases first",
              "Verifying the arrest report",
              "a man in his 30s was arrested"):
    ck(f"the model's own prose survives: {_keep[:34]!r}", _keep in _clean,
       repr(_clean)[:160])

# Mid-fabrication: the turn ended before the closing marker arrived.
_open = "Fetching now.⟦UNTRUSTED WEB CONTENT⟧\nsource: y\nstill typing"
_c2, _n2 = strip_fabricated_results(_open)
ck("an UNCLOSED forgery is cut to the end of the buffer",
   _n2 == 1 and _c2 == "Fetching now.", repr(_c2))

_c3, _n3 = strip_fabricated_results(
    "Here you go.<tool_result>\n[tool: web_read]\n{}\n</tool_result>\nThat's it.")
ck("a forged <tool_result> block is removed, prose either side kept",
   _n3 == 1 and "Here you go." in _c3 and "That's it." in _c3
   and "tool_result" not in _c3, repr(_c3))


print("\n== counter-property: documentation is not forgery ==")
_doc = ("The host wraps results like this:\n```\n"
        "⟦UNTRUSTED WEB CONTENT⟧\n...\n"
        "⟦END UNTRUSTED WEB CONTENT⟧\n```\nThat banner is host-generated.")
ck("a FENCED example of the envelope is not flagged",
   not fabricated_tool_result(_doc))
ck("…and is not deleted from the page",
   strip_fabricated_results(_doc)[0] == _doc)
_unchanged = [
    "Just an ordinary answer.",
    "The result showed status 200 and three items.",
    "I read the RTE page; it named no suspect.",
    "",
]
ck("clean replies are returned byte-identical",
   all(strip_fabricated_results(t)[0] == t for t in _unchanged))
ck("removal is idempotent",
   strip_fabricated_results(strip_fabricated_results(SCREENSHOT)[0])[1] == 0)

# Bounded work: a reply that is nothing but repeated openers must not spin.
import time                                                    # noqa: E402
_many = "⟦UNTRUSTED WEB CONTENT⟧" * 4000
_t0 = time.time()
strip_fabricated_results(_many)
_ms = (time.time() - _t0) * 1000
ck(f"4000 repeated openers stay bounded ({_ms:.0f}ms)", _ms < 3000, f"{_ms:.0f}ms")


print("\n== the wiring in basilisk.py ==")
_src = open(os.path.join(_ROOT, "basilisk.py"), encoding="utf-8").read()
ck("the check sits at the canonicalisation boundary, above display, "
   "storage and history",
   _src.index("strip_fabricated_results(final") >
   _src.index("final = _normalise_tool_syntax(final")
   and (_src.index("strip_fabricated_results(final")
        - _src.index("final = _normalise_tool_syntax(final")) < 2000,
   "must be immediately after the normaliser, before anything consumes final")
ck("a forged turn is reported to the operator, not silently scrubbed",
   "the model WROTE" in _src and "invented data" in _src)
ck("the model is told, so it re-does the work properly",
   "contained a tool result that YOU WROTE" in _src)
ck("the correction is BOUNDED (a model that keeps forging cannot loop)",
   "self._forged_retries < 2" in _src)
ck("the counter is a real class attribute, not a getattr default",
   "_forged_retries: int = 0" in _src
   and 'getattr(self, "_forged_retries"' not in _src)
ck("it is reset per REQUEST, beside the other per-request counters",
   "self._forged_retries = 0" in _src)
ck("the guard does not read `cancelled`, which is unbound at that point",
   "not meta.get(\"cancelled\")" in _src)

print("\n== the persona says it too (prevention, not just enforcement) ==")
import basilisk_persona as kp                                  # noqa: E402
ck("the tool contract forbids writing a result",
   "NEVER WRITE THE" in kp.TOOL_CONTRACT and "RESULT YOURSELF" in kp.TOOL_CONTRACT)
ck("…and says results arrive from the host, later",
   "arrives from the host" in kp.TOOL_CONTRACT)
ck("…and names it as fabricated evidence",
   "fabricated evidence" in kp.TOOL_CONTRACT)


print(f"\nfabrication: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
