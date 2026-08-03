#!/usr/bin/env python3
"""
test_unblock.py — supervision by progress, not by a wall clock.

The property under test is the one the old timeout got wrong: a wall clock
cannot tell SLOW from STUCK, so it killed real work at the same number as a
dead socket — and then threw the real work away.

    except subprocess.TimeoutExpired:
        return {"ok": False, "rc": 124, "timed_out": True, ...}

`TimeoutExpired.stdout` holds every byte the process wrote. That handler never
read it, so a scan that enumerated 200 hosts and then hung reported NOTHING and
the agent re-ran the whole thing. "It times out and it's back on 0" was a
discarded-data bug, not a tuning problem.

So the assertions here are about behaviour, not timings:

  · output NEVER disappears, whatever the outcome,
  · a process producing output is never stopped, however long it runs,
  · a process burning CPU in total silence is never stopped either — that is a
    compile or a hash crack, and it is the case a wall clock always kills,
  · a process blocked on an interactive prompt gets UNBLOCKED and finishes,
    which no timeout can ever do,
  · a real stall yields a PARTIAL result plus a diagnosis, never an empty one.

Thresholds are passed in tiny so the suite stays fast. The production defaults
are ~45/90/240s of TOTAL silence, and the stall clock resets on any sign of
life, so nothing that is working can reach them.

Run:  python3 tests/test_unblock.py
"""

from __future__ import annotations

import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from basilisk_ext import unblock as U                          # noqa: E402

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


FAST = dict(stall_notice_s=0.8, stall_unblock_s=1.6, stall_harvest_s=3.0)


# ── 1. ordinary commands still behave like subprocess.run ────────────
print("== ordinary commands ==")
r = U.run_supervised("echo hello")
ck("stdout captured", r["stdout"].strip() == "hello", repr(r["stdout"]))
ck("rc is 0", r["rc"] == 0)
ck("ok is True", r["ok"] is True)
ck("not marked partial", r["partial"] is False)
ck("no diagnosis on success", not r["diagnosis"])

r = U.run_supervised("echo oops >&2; exit 3")
ck("stderr captured", r["stderr"].strip() == "oops", repr(r["stderr"]))
ck("non-zero rc reported", r["rc"] == 3)
ck("non-zero rc is not ok", r["ok"] is False)
ck("non-zero rc is NOT partial (it finished)", r["partial"] is False,
   "a command that fails cleanly has not stalled")

r = U.run_supervised("printf 'a\\nb\\nc\\n'")
ck("multi-line output intact", r["stdout"].count("\n") == 3)
ck("byte counter tracks output", r["bytes_out"] >= 6, str(r["bytes_out"]))

r = U.run_supervised("exit 0")
ck("empty output is fine", r["stdout"] == "" and r["ok"] is True)

r = U.run_supervised("this-command-does-not-exist-xyz")
ck("missing binary still returns cleanly", r["rc"] not in (None,))
ck("missing binary reports via stderr", "not found" in r["stderr"].lower(),
   repr(r["stderr"][:60]))


# ── 2. SLOW is not STUCK ─────────────────────────────────────────────
# The headline case. Thresholds below are far shorter than the runtime; it
# survives purely because it keeps producing output.
print("\n== slow work is not stopped ==")
t0 = time.monotonic()
r = U.run_supervised("for i in 1 2 3 4 5; do echo tick $i; sleep 0.6; done",
                     **FAST)
el = time.monotonic() - t0
ck("ran to completion despite a 3s harvest threshold", r["partial"] is False,
   f"elapsed {el:.1f}s")
ck("all five ticks present", r["stdout"].count("tick") == 5, r["stdout"])
ck("outlived the harvest threshold", el > 3.0, f"{el:.1f}s")
ck("finished ok", r["ok"] is True)


# ── 3. SILENT but working is not stuck either ────────────────────────
# The case a wall clock ALWAYS gets wrong: no output at all, but real CPU.
# A compile, a hash crack, a big crypto operation all look like this.
print("\n== silent CPU-bound work is not stopped ==")
_busy = ("python3 -c \"import time\ns=time.time()\nx=0\n"
         "while time.time()-s<4: x+=1\nprint(x)\"")
t0 = time.monotonic()
r = U.run_supervised(_busy, **FAST)
el = time.monotonic() - t0
ck("silent CPU work ran to completion", r["partial"] is False,
   f"elapsed {el:.1f}s partial={r['partial']}")
ck("CPU movement was detected", r["cpu_moved"] is True,
   "without /proc this degrades to output-only detection")
ck("it really was silent for longer than the threshold", el > 3.0,
   f"{el:.1f}s")
ck("its output came back", r["stdout"].strip().isdigit(), r["stdout"][:40])


# ── 4. A REAL stall: work is harvested, never lost ───────────────────
print("\n== a genuine stall keeps the work ==")
ev = []
r = U.run_supervised(
    "for i in $(seq 1 120); do echo host $i up; done; sleep 300",
    on_event=lambda k, d: ev.append(k), **FAST)
ck("marked partial", r["partial"] is True)
ck("marked stalled", r["stalled"] is True)
ck("ALL 120 lines survived the stall",
   r["stdout"].count("up") == 120, str(r["stdout"].count("up")))
ck("byte counter matches", r["bytes_out"] > 500, str(r["bytes_out"]))
ck("stall was noticed", "stalled" in ev, str(ev))
ck("harvest happened", "harvesting" in ev, str(ev))
ck("a diagnosis was produced", bool(r["diagnosis"]))
ck("diagnosis says the work is usable",
   "use it" in r["diagnosis"] and "Do NOT re-run" in r["diagnosis"])
ck("diagnosis tells it not to repeat identically",
   "identical place" in r["diagnosis"])
ck("diagnosis reports it was waiting on something external",
   "waiting on something external" in r["diagnosis"],
   "sleep burns no CPU, so this is the correct read")
ck("elapsed is recorded", r["elapsed_s"] > 0)

# A stall with NO output must still be honest rather than silent.
r = U.run_supervised("sleep 300", **FAST)
ck("output-less stall is still partial", r["partial"] is True)
ck("output-less stall says so plainly",
   "no output at all" in r["diagnosis"], r["diagnosis"][:80])


# ── 5. THE UNBLOCK: a prompt is answered, not killed ─────────────────
# No timeout can do this. The process is not broken, it asked a question.
print("\n== blocked on stdin gets unblocked ==")
ev = []
r = U.run_supervised(
    'echo "Continue? [y/N]"; read ans; echo "went ahead"; echo DONE',
    on_event=lambda k, d: ev.append(k),
    stall_notice_s=0.8, stall_unblock_s=1.5, stall_harvest_s=30.0)
ck("the stall was detected", "stalled" in ev, str(ev))
ck("an unblock was attempted", "unblocking" in ev, str(ev))
ck("it RESUMED rather than being killed", "resumed" in ev, str(ev))
ck("it finished cleanly", r["partial"] is False and r["rc"] == 0,
   f"partial={r['partial']} rc={r['rc']}")
ck("the work after the prompt actually ran", "DONE" in r["stdout"],
   repr(r["stdout"]))
ck("the intervention is reported", "stdin" in (r["unblocked"] or ""),
   str(r["unblocked"]))
ck("no harvest was needed", "harvesting" not in ev, str(ev))


# ── 6. salvage_timeout: nothing is binned on the legacy path ─────────
print("\n== salvage_timeout ==")
import subprocess                                              # noqa: E402
try:
    subprocess.run("for i in $(seq 1 50); do echo line $i; done; sleep 30",
                   shell=True, stdout=subprocess.PIPE,
                   stderr=subprocess.PIPE, timeout=1.5)
    raise AssertionError("expected a timeout")
except subprocess.TimeoutExpired as exc:
    sal = U.salvage_timeout(exc, "test", 1.5)
ck("salvage recovers the output", sal["stdout"].count("line") == 50,
   str(sal["stdout"].count("line")))
ck("salvage marks it partial", sal["partial"] is True)
ck("salvage keeps rc 124 for legacy callers", sal["rc"] == 124)
ck("salvage explains the output is usable",
   "that work is done" in sal["diagnosis"])
ck("salvage handles an exception with no output",
   U.salvage_timeout(subprocess.TimeoutExpired("x", 1), "x", 1)["stdout"] == "")


# ── 7. capture cap ───────────────────────────────────────────────────
print("\n== capture bounds ==")
c = U.Capture(limit=64 * 1024)
for _ in range(400):
    c.feed(b"x" * 1024)
txt = c.text()
ck("capture is bounded", len(txt) < 1_000_000, str(len(txt)))
ck("capture keeps the head", txt.startswith("x"))
ck("capture says it truncated", "capture cap" in txt)
ck("byte counter is the TRUE total, not the kept amount",
   c.bytes_seen == 400 * 1024, str(c.bytes_seen))

c2 = U.Capture()
c2.feed(b"")
ck("empty feed is a no-op", c2.text() == "" and c2.bytes_seen == 0)
c2.feed("nonbytes".encode())
ck("normal feed works after an empty one", "nonbytes" in c2.text())


# ── 8. helpers degrade instead of raising ────────────────────────────
print("\n== /proc helpers are fail-soft ==")
ck("cpu read of a bogus pid returns None",
   U._read_cpu_jiffies(999_999_999) is None)
ck("state of a bogus pid is '?'", U._proc_state(999_999_999) == "?")
ck("stdin check on a bogus pid is False",
   U._waiting_on_stdin(999_999_999) is False)
ck("group cpu of a bogus group does not raise",
   U._group_cpu(999_999_999, 999_999_999) is None
   or isinstance(U._group_cpu(999_999_999, 999_999_999), int))
ck("own pid reports real cpu", isinstance(U._read_cpu_jiffies(os.getpid()), int))
ck("own state is a single letter", len(U._proc_state(os.getpid())) == 1)

r = U.run_supervised("echo x", cwd="/definitely/not/a/dir/xyz")
ck("a bad cwd returns a result instead of raising", isinstance(r, dict))
ck("a bad cwd is not reported as ok", r.get("ok") is not True)


# ── 9. no wall clock by default ──────────────────────────────────────
print("\n== no wall-clock limit ==")
import inspect                                                 # noqa: E402
_sig = inspect.signature(U.run_supervised)
ck("max_wall_s defaults to None (no limit)",
   _sig.parameters["max_wall_s"].default is None,
   "a default wall clock would reintroduce exactly the bug being fixed")
ck("stall thresholds are ordered notice < unblock < harvest",
   U.STALL_NOTICE_S < U.STALL_UNBLOCK_S < U.STALL_HARVEST_S)
ck("harvest threshold is generous",
   U.STALL_HARVEST_S >= 120,
   "must exceed a long DNS/TCP backoff so normal retries are not called stalls")

# An explicit wall limit still works for callers that genuinely need one.
t0 = time.monotonic()
r = U.run_supervised("sleep 60", max_wall_s=1.5,
                     stall_notice_s=30, stall_unblock_s=40,
                     stall_harvest_s=50)
ck("explicit max_wall_s is honoured", (time.monotonic() - t0) < 10)
ck("wall-limited result is still partial with a diagnosis",
   r["partial"] is True and bool(r["diagnosis"]))


print(f"\nunblock: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
