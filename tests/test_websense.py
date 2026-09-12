#!/usr/bin/env python3
"""
test_websense.py — when Basilisk should go and look, and when it should just
answer.

THE REPORT
==========
    "make it so the ai also is even better at knowing when to send one answer
     and when to look online and search ... it has to be better at knowing
     when its time to stop"

Both halves of that were ONE defect, and it was a design property rather than
a missing phrase.

`_needs_web_verification` is a list of markers, and a list of markers can only
ever say YES. Every marker it gained to stop a missed fetch also made it fire
on ordinary work, and nothing anywhere said no. Measured against fourteen
plain coding questions, THIRTEEN forced a web fetch:

    "explain the cost of a hash table lookup"            -> cost
    "which python version does my pyproject require"     -> version
    "refactor the price calculation in cart.py"          -> price
    "why is worth() returning None in this file"         -> worth
    "the news feed component in my react app is broken"  -> news

And because forced_search_url reads the same predicate, the turn could not
END where it should have ended either: the model answered, the app fetched
anyway, and it came back with a second reply nobody asked for. "It searches
when it shouldn't" and "it doesn't know when to stop" are the same bug seen
from two sides.

THE RULE
========
Suppression needs POSITIVE EVIDENCE and may only ever downgrade a WEAK signal.
It fires when BOTH hold:

  1. nothing STRONG matched ("latest", "today", "who won", "weather",
     "ceo of", "out yet" — these name the live state of the world), and
  2. the question has a LOCAL referent (their files, their code) or a
     CONCEPTUAL one (a definition, a how-to, a thing to build).

So the failure mode is asymmetric on purpose: a question with neither still
fetches on a weak marker alone. A needless fetch costs a round trip; a missed
one costs a wrong answer.

Run:  python3 tests/test_websense.py
"""

from __future__ import annotations

import io
import os
import re
import sys

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


# Lift the decision out of basilisk.py without importing GTK. The region is
# bounded by two anchors that are themselves asserted below, so a refactor
# that moves the code fails loudly instead of silently testing nothing.
SRC = io.open(os.path.join(_ROOT, "basilisk.py"), encoding="utf-8").read()
_A = "\n_VERIFY_MARKERS = ("
_B = "# ── THE PROMISE GATE"
ck("the decision region is where this suite expects it",
   SRC.count(_A) == 1 and SRC.count(_B) >= 1)
_ns = {"re": re}
exec(SRC[SRC.index(_A):SRC.index(_B)], _ns)          # noqa: S102
ck("...and exporting the three functions this suite drives",
   all(k in _ns for k in ("_needs_web_verification",
                          "_needs_web_verification_raw",
                          "_verification_suppressed")))
needs = _ns["_needs_web_verification"]
raw = _ns["_needs_web_verification_raw"]
suppressed = _ns["_verification_suppressed"]


# ── 1. ORDINARY WORK MUST NOT GO TO THE WEB ──────────────────────────
print("\n== a question about their own code is not a web question ==")
LOCAL = [
    "explain the cost of a hash table lookup",
    "what's the time complexity, is the cost O(1)?",
    "how much is 2 + 2",
    "what does the current directory mean in bash",
    "my score function returns the wrong value, fix it",
    "which python version does my pyproject require",
    "write a changelog entry for my release script",
    "the news feed component in my react app is broken",
    "why is worth() returning None in this file",
    "add support for gzip to my parser",
    "is this function still maintained in my fork",
    "refactor the price calculation in cart.py",
    "what is the difference between a release build and a debug build",
    "explain how version pinning works in requirements.txt",
    "fix the deprecated api call in main.py",
    "how do i check the exit status of a command",
    "why does my test suite hang on the network mock",
    "review the scoring logic in `rank()`",
    "implement a cost function from scratch",
    "what does EOL mean in a csv parser",
    "the price calculation in my cart is wrong",
    "how much does this function cost in memory",
    "rename the score variable in ranker.py",
    "why is my build deprecated",
]
for q in LOCAL:
    ck(f"no fetch: {q[:52]}", not needs(q))

# The suite must not be vacuous: the RAW marker scan is still supposed to fire
# on most of these. If it stopped firing, the suppressor is being credited for
# something it never did.
_raw_hits = sum(1 for q in LOCAL if raw(q))
ck(f"the raw marker scan really does fire on these ({_raw_hits}/{len(LOCAL)})",
   _raw_hits >= len(LOCAL) - 5,
   "if raw() stopped matching, this suite proves nothing about suppression")


# ── 2. COUNTER-PROPERTY: IT MUST STILL FETCH ─────────────────────────
# A gate that stops firing is not a fix. This half matters more than the
# first: a needless fetch costs a round trip, a missed one costs a wrong
# answer stated confidently.
print("\n== a question about the world still gets looked up ==")
WORLD = [
    "what's the latest version of nmap",
    "who won the champions league final last night",
    "what's the news today",
    "is python 3.14 out yet",
    "how much is a tesla model 3 right now",
    "who is the ceo of anthropic",
    "what's the weather in dublin",
    "top stories in the world today",
    "did they release nmap 8 yet",
    "what happened in ireland this week",
    "is nmap 7.95 still the current release",
    "what's the latest version of the requests library for my project",
    "has there been a new kali release",
    "what is the price of bitcoin",
    "give me the rundown on what's happening",
    "is CVE-2026-1234 patched yet",
    "what's new with GLM 5.3",
    "current events in ireland",
    "what's the 2026 roadmap for gtk",
    "is log4j still supported",
    "how much is a claude subscription",
    "whats the score in the ireland match",
    "any new exploits for struts",
    "is metasploit still maintained",
]
for q in WORLD:
    ck(f"fetches: {q[:52]}", needs(q))


# ── 3. THE THREE BUGS I PUT IN WHILE WRITING IT ──────────────────────
# Each of these passed the eye and failed the corpus. They are pinned
# individually because each is a whole CLASS, not one string.
print("\n== the near-misses, pinned ==")

# (a) An identifier is not a sum. The first arithmetic guard was
#     \d+\s*[-+*/^%]\s*\d+, so "CVE-2026-1234" read as 2026 minus 1234 and
#     suppressed a live vulnerability question. That is the single worst
#     thing this predicate can get wrong.
ck("a hyphenated identifier is not arithmetic",
   needs("is CVE-2026-1234 patched yet")
   and needs("does CVE-2024-3094 affect xz 5.6.1"))
ck("...but real arithmetic still is",
   not needs("how much is 2 + 2") and not needs("how much is 100 / 4"))

# (b) "in <det> <any word>" as a local referent matched "in the news",
#     "in the world" and "in the ireland match" — the exact questions that
#     must never be suppressed.
ck("'in the ireland match' is not a local scope",
   needs("whats the score in the ireland match")
   and needs("what's going on in the world today"))

# (c) "how much is/does" was strong, so it was immune — and "how much does
#     this function cost in memory" fetched.
ck("a price phrase about their own code is suppressed",
   not needs("how much does this function cost in memory"))
ck("...and about a thing in the world is not",
   needs("how much is a claude subscription"))


# ── 4. THE SHAPE OF THE RULE ─────────────────────────────────────────
print("\n== suppression can only ever downgrade a weak signal ==")
ck("a strong marker is never suppressed",
   not suppressed(" what is the latest version in my repo "),
   "'latest' is strong; a local referent must not silence it")
ck("a current-era year is never suppressed",
   not suppressed(" what changed in my repo in 2026 "))
ck("suppression requires positive evidence",
   not suppressed(" is there a cost "),
   "a weak marker with no local or conceptual referent must still fetch")
ck("the suppressor is a separate, testable function",
   "def _verification_suppressed(" in SRC)
ck("the raw marker scan is still reachable on its own",
   "_needs_web_verification_raw = _needs_web_verification" in SRC)
ck("the public predicate is the composition of the two",
   "if not _needs_web_verification_raw(text):" in SRC
   and "return not _verification_suppressed(t)" in SRC)

# The promise gate reads the SAME predicate, which is why this fix ends turns
# that used to run on: no marker, no forced fetch, no extra reply.
ck("the promise gate reads this predicate and no other",
   "if not _needs_web_verification(q):" in SRC)


# ── 5. COST ──────────────────────────────────────────────────────────
# This runs once per round-trip on the operator's message, not per frame, but
# it is still four regex passes over a sentence and must not be silly.
print("\n== cost ==")
import time                                                      # noqa: E402
_long = ("refactor the price calculation in cart.py and explain the cost " * 40)
t0 = time.perf_counter()
for _ in range(500):
    needs(_long)
_ms = (time.perf_counter() - t0) * 1000 / 500
ck(f"a 3KB message decides in {_ms:.3f}ms", _ms < 5.0)


print(f"\nwebsense: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
