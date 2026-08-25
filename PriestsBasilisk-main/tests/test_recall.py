#!/usr/bin/env python3
"""
test_recall.py — the durable "already done this run" action log.

This module exists because the model repeated itself: not "twice in a row",
which the old loop-breaker caught, but re-running something from three or four
steps back with other actions in between.  The cause was structural — the
transcript is the model's only record of its own actions and the host trims it
(HISTORY_KEEP_FULL_TOOL_RESULTS=2, then headroom compression) while the mission
directive re-anchors on the original objective every turn.

So the properties pinned here are the ones that make the repetition fix real:

  · a repeat is recognised NO MATTER how many other actions came between,
  · an A-B-A-B cycle is detected (the old breaker only saw N identical
    CONSECUTIVE commands, so alternation was invisible to it),
  · two executions are always allowed and the THIRD is refused — because
    re-checking after a change is verification, not a loop, and blocking it
    would break correct behaviour,
  · normalisation is CONSERVATIVE: a false "you already did this" stops real
    work with a confident wrong reason, which is worse than a missed one,
  · the digest survives the ring buffer rolling over — "I did this ages ago"
    must stay true after the line scrolls off.

Run:  python3 tests/test_recall.py
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from basilisk_ext.recall import (          # noqa: E402
    ActionLog, digest_outcome, normalise)

_p = _f = 0


def ck(name: str, cond: bool, detail: str = "") -> None:
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


# ── normalisation ────────────────────────────────────────────────────
print("== normalise ==")
ck("collapses whitespace",
   normalise("run:  nmap   -sV  10.0.0.5") == "run: nmap -sV 10.0.0.5")
ck("strips a trailing semicolon",
   normalise("run: ls -la ;") == normalise("run: ls -la"))
ck("strips surrounding space", normalise("  run: id  ") == "run: id")
ck("empty stays empty", normalise("") == "")
ck("None-safe", normalise(None) == "")

# Conservative on purpose: these are DIFFERENT actions and must not collide.
ck("different flags are different actions",
   normalise("run: nmap -sV host") != normalise("run: nmap -sC host"))
ck("different targets are different actions",
   normalise("run: nmap 10.0.0.5") != normalise("run: nmap 10.0.0.6"))
ck("case is significant (paths are case-sensitive)",
   normalise("run: cat /etc/Passwd") != normalise("run: cat /etc/passwd"))
ck("a redirect makes it a different action",
   normalise("run: nmap x") != normalise("run: nmap x > out.txt"))


# ── outcome digest ───────────────────────────────────────────────────
print("\n== digest_outcome ==")
d = digest_outcome("$ systemctl status docker\n(rc=3)\nUnit docker is inactive")
ck("keeps the rc", "rc=3" in d, d)
ck("skips the echoed command line", "systemctl status" not in d, d)
ck("keeps the informative line", "inactive" in d, d)
ck("empty output is labelled", digest_outcome("") == "(no output)")
ck("whitespace-only output is labelled",
   digest_outcome("\n\n   \n") == "(no output)")
long_line = "x" * 5000
ck("a monster line is bounded", len(digest_outcome(long_line)) <= 115,
   str(len(digest_outcome(long_line))))
ck("rc=0 is kept too (worked vs failed is the useful bit)",
   "rc=0" in digest_outcome("$ id\n(rc=0)\nuid=0(root)"))


# ── recording and repeat counting ────────────────────────────────────
print("\n== record / times_run ==")
L = ActionLog()
ck("starts empty", len(L) == 0)
ck("empty action is not recorded", L.record("") == {} and len(L) == 0)

L.record("run: nmap -sV 10.0.0.5", "$ nmap\n(rc=0)\n22/tcp open ssh")
ck("first record lands", len(L) == 1)
ck("counted once", L.times_run("run: nmap -sV 10.0.0.5") == 1)
ck("unknown action counts zero", L.times_run("run: whoami") == 0)

# THE HEADLINE CASE: a repeat separated by other work.
for other in ("run: whoami", "run: id", "read_file: /etc/hosts",
              "run: uname -a"):
    L.record(other, "(rc=0)")
L.record("run: nmap -sV 10.0.0.5", "$ nmap\n(rc=0)\n22/tcp open ssh")
ck("repeat detected across FOUR intervening actions",
   L.times_run("run: nmap -sV 10.0.0.5") == 2)
ck("whitespace variant is the same action",
   L.times_run("run:  nmap  -sV   10.0.0.5") == 2)
ck("previous() returns the latest entry for it",
   (L.previous("run: nmap -sV 10.0.0.5") or {}).get("times") == 2)
ck("previous() is None for an unseen action",
   L.previous("run: nothing-like-this") is None)


# ── should_block: two allowed, third refused ─────────────────────────
print("\n== should_block ==")
B = ActionLog()
ck("nothing run yet → allowed", not B.should_block("run: x", 2))
B.record("run: x", "(rc=0)")
ck("first execution done → SECOND still allowed",
   not B.should_block("run: x", 2))
B.record("run: x", "(rc=0)")
ck("two executions done → THIRD is refused", B.should_block("run: x", 2))
ck("a different action is unaffected", not B.should_block("run: y", 2))
ck("limit=0 disables the guard entirely", not B.should_block("run: x", 0))
ck("limit=-1 disables it too", not B.should_block("run: x", -1))
ck("limit=1 refuses the second execution",
   ActionLog().__class__ and (lambda a: (a.record("run: z", ""),
                                         a.should_block("run: z", 1))[1])(
                                             ActionLog()))
ck("limit=3 → allows three, blocks the fourth",
   (lambda a: (a.record("run: q", ""), a.record("run: q", ""),
               a.record("run: q", ""), a.should_block("run: q", 3))[3])(
                   ActionLog()))

# The verification pattern must survive: check -> change -> check again.
V = ActionLog()
V.record("run: systemctl status docker", "(rc=3)\ninactive")
V.record("run: systemctl start docker", "(rc=0)")
ck("re-checking after a change is NOT blocked",
   not V.should_block("run: systemctl status docker", 3),
   "verification must stay legal")


# ── cycle detection ──────────────────────────────────────────────────
print("\n== cycle ==")
C = ActionLog()
ck("no cycle when empty", C.cycle() is None)
C.record("run: a", "")
C.record("run: b", "")
ck("no cycle from two distinct actions", C.cycle() is None)

AB = ActionLog()
for _ in range(2):
    AB.record("run: a", "")
    AB.record("run: b", "")
cyc = AB.cycle()
ck("A-B-A-B is detected", cyc is not None and len(cyc) == 2, str(cyc))
ck("the cycle names both actions",
   bool(cyc) and normalise("run: a") in cyc and normalise("run: b") in cyc,
   str(cyc))

ABC = ActionLog()
for _ in range(2):
    for x in "abc":
        ABC.record(f"run: {x}", "")
ck("A-B-C-A-B-C is detected", ABC.cycle() is not None)

AA = ActionLog()
AA.record("run: a", "")
AA.record("run: a", "")
AA.record("run: a", "")
ck("A-A-A (the classic) is detected", AA.cycle() is not None)
# TWO identical is NOT a cycle — re-checking after a change looks like that
AA2 = ActionLog()
AA2.record("run: a", "")
AA2.record("run: a", "")
ck("A-A alone is not flagged (could be a legit re-check)",
   AA2.cycle() is None)

PROG = ActionLog()
for x in "abcdefgh":
    PROG.record(f"run: {x}", "")
ck("steady progress is NOT a cycle", PROG.cycle() is None,
   "false cycle alarms would nag during normal work")

# A cycle that has been broken must stop being reported.
BROKE = ActionLog()
for _ in range(2):
    BROKE.record("run: a", "")
    BROKE.record("run: b", "")
BROKE.record("run: c", "")
ck("a broken cycle is no longer reported", BROKE.cycle() is None)


# ── digest / prompt block ────────────────────────────────────────────
print("\n== digest / prompt_block ==")
ck("empty log renders nothing", ActionLog().digest() == "")
ck("empty log has no prompt block", ActionLog().prompt_block() == "")

D = ActionLog()
D.record("run: nmap -sV 10.0.0.5", "$ nmap\n(rc=0)\n22/tcp open ssh")
D.record("run: whoami", "$ whoami\n(rc=0)\nroot")
dg = D.digest()
ck("digest lists both actions", "nmap -sV 10.0.0.5" in dg and "whoami" in dg)
ck("digest carries the outcome", "22/tcp open ssh" in dg)
ck("digest numbers the steps", "  1." in dg and "  2." in dg)

D.record("run: whoami", "$ whoami\n(rc=0)\nroot")
ck("a repeat is flagged with a count in the digest", "[x2]" in D.digest())

pb = D.prompt_block()
ck("prompt block is labelled ALREADY DONE", "ALREADY DONE" in pb)
ck("prompt block says it is not trimmed", "NOT trimmed" in pb)
ck("prompt block tells it not to repeat", "Do NOT repeat" in pb)
ck("prompt block is closed", pb.rstrip().endswith("]"))

LOOP = ActionLog()
for _ in range(2):
    LOOP.record("run: a", "")
    LOOP.record("run: b", "")
ck("prompt block shouts when in a loop", "YOU ARE IN A LOOP" in
   LOOP.prompt_block())
ck("no loop warning when there isn't one",
   "YOU ARE IN A LOOP" not in D.prompt_block())


# ── ring buffer: counts outlive the visible window ───────────────────
print("\n== ring buffer ==")
R = ActionLog(max_entries=5)
R.record("run: first", "(rc=0)")
for i in range(10):
    R.record(f"run: filler{i}", "(rc=0)")
ck("entry list is capped", len(R) == 5, str(len(R)))
ck("the scrolled-off action is no longer listed",
   "run: first" not in R.digest())
ck("but its COUNT survives — 'I did this ages ago' stays true",
   R.times_run("run: first") == 1)
R.record("run: first", "(rc=0)")
ck("so a very old repeat is still counted as a repeat",
   R.times_run("run: first") == 2)

BIG = ActionLog()
for i in range(200):
    BIG.record(f"run: cmd{i}", "x" * 400)
ck("digest length stays bounded on a long run",
   len(BIG.prompt_block()) < 12000, str(len(BIG.prompt_block())))
ck("digest says how many were omitted", "earlier action(s) not shown"
   in BIG.digest(10))


# ── reset ────────────────────────────────────────────────────────────
print("\n== reset ==")
Z = ActionLog()
Z.record("run: a", "")
Z.record("run: a", "")
ck("blocked before reset", Z.should_block("run: a", 2))
Z.reset()
ck("reset clears entries", len(Z) == 0)
ck("reset clears counts", Z.times_run("run: a") == 0)
ck("reset unblocks — a NEW objective is not the old one",
   not Z.should_block("run: a", 2))


# ── robustness ───────────────────────────────────────────────────────
print("\n== robustness ==")
import threading as _t                                     # noqa: E402

T = ActionLog(max_entries=500)
_errs = []


def _hammer(n):
    try:
        for i in range(80):
            T.record(f"run: cmd{n % 4}", f"(rc=0) out {i}")
            T.times_run(f"run: cmd{n % 4}")
            T.digest(5)
            T.cycle()
    except Exception as e:                                  # pragma: no cover
        _errs.append(e)


ths = [_t.Thread(target=_hammer, args=(i,)) for i in range(16)]
[t.start() for t in ths]
[t.join() for t in ths]
ck("16 threads recording concurrently: no exception", not _errs, str(_errs[:1]))
ck("16 threads: every record landed",
   sum(T.times_run(f"run: cmd{i}") for i in range(4)) == 16 * 80,
   str(sum(T.times_run(f"run: cmd{i}") for i in range(4))))

for junk in ("", " ", "\n", "\x00", "a" * 10000, "🙂" * 50, "{}", "]["):
    try:
        J = ActionLog()
        J.record(junk, junk)
        J.digest()
        J.prompt_block()
        J.cycle()
        J.should_block(junk, 3)
        ok = True
    except Exception:                                       # pragma: no cover
        ok = False
    ck(f"junk input survives: {junk[:12]!r}", ok)


print(f"\nrecall: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
