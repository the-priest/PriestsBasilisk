#!/usr/bin/env python3
"""
test_tasks.py — the TASK LEDGER: basilisk_ext/tasks.py.

WHAT THIS IS PROTECTING
=======================
Two operator complaints, one missing mechanism:

    "it still sometimes stops when it's supposed to keep working"
    "it still doesn't stop when it's supposed to and sends two answers"

Both are the same gap: nothing in the app knew what the model set out to
do, so "is this turn finished?" could only be answered by reading prose —
and a prose reader is one phrasing away from being wrong in BOTH directions
at once. The ledger replaces the reading with state the app owns.

The asserts below are in three groups, and the second is the one that
matters most:

  1. the ledger tracks what it says it tracks;
  2. THE COUNTER-PROPERTIES — blocked/dropped really do close an item, a
     plan that does not exist is not "complete", re-planning does not
     resurrect finished work. Each of these is a way the gate could hang a
     turn open forever, which is worse than the bug it fixes;
  3. it is TOTAL — junk in, a dict out, never an exception. This thing is
     read on the path that ENDS turns; if it raises, it takes the turn with
     it.

Run:  python3 tests/test_tasks.py
"""

from __future__ import annotations

import os
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


from basilisk_ext.tasks import (                                # noqa: E402
    TaskPlan, normalise_status, OPEN_STATES, CLOSED_STATES, VALID_STATES,
)


def plan(*titles):
    p = TaskPlan()
    p.set_plan(list(titles))
    return p


# ── 1. the state model ───────────────────────────────────────────────
print("\n== the state model ==")
ck("open and doing are OPEN", OPEN_STATES == {"open", "doing"})
ck("done, blocked and dropped all CLOSE an item",
   CLOSED_STATES == {"done", "blocked", "dropped"})
ck("the two sets do not overlap", not (OPEN_STATES & CLOSED_STATES))
ck("VALID_STATES is exactly their union",
   VALID_STATES == (OPEN_STATES | CLOSED_STATES))

print("\n== status synonyms the model actually emits ==")
for word, want in (("todo", "open"), ("pending", "open"),
                   ("in progress", "doing"), ("in_progress", "doing"),
                   ("WIP", "doing"), ("Completed", "done"),
                   ("finished", "done"), ("stuck", "blocked"),
                   ("skipped", "dropped"), ("not needed", "dropped"),
                   ("DONE", "done"), ("  In-Progress  ", "doing")):
    ck(f"{word!r} -> {want}", normalise_status(word) == want,
       repr(normalise_status(word)))
ck("an unmappable word maps to nothing (never a silent default)",
   normalise_status("bananas") == "")
ck("normalise_status is total on junk",
   all(normalise_status(x) == "" for x in (None, 123, [], {}, object())))


# ── 2. building a plan ───────────────────────────────────────────────
print("\n== building a plan ==")
p = TaskPlan()
r = p.set_plan(["read the test", "fix the parser", "run the suite"],
               goal="fix the repo")
ck("set_plan reports ok", r.get("ok"))
ck("ids are 1..n", [i["id"] for i in p.items] == ["1", "2", "3"])
ck("everything starts open", all(i["status"] == "open" for i in p.items))
ck("the goal is kept", p.goal == "fix the repo")
ck("a fresh plan is NOT complete", not p.is_complete())
ck("the intro tells it the plan is not the work",
   "the plan is not the work" in (r.get("reminder") or "").lower())

ck("a newline-separated string is accepted, not refused",
   TaskPlan().set_plan("a\nb\nc").get("ok"))
ck("numbering is stripped from pasted items",
   TaskPlan().set_plan(["1. read it", "2) fix it"]).get("items")[0]["title"]
   == "read it")
ck("duplicate steps collapse to one",
   len(TaskPlan().set_plan(["run tests", "Run Tests", "ship"]).get("items"))
   == 2)
ck("dict items with a status are honoured",
   TaskPlan().set_plan([{"title": "a", "status": "done"},
                        {"title": "b"}]).get("counts")["done"] == 1)
ck("an empty plan is refused", not TaskPlan().set_plan([]).get("ok"))
ck("…and the refusal shows the shape to send",
   '"items"' in TaskPlan().set_plan([]).get("error", ""))
ck("a plan of blank strings is refused",
   not TaskPlan().set_plan(["", "   "]).get("ok"))
ck("an absurdly long plan is refused",
   not TaskPlan().set_plan([f"step {i}" for i in range(80)]).get("ok"))


# ── 3. moving items ──────────────────────────────────────────────────
print("\n== moving items ==")
p = plan("read the test", "fix the parser", "run the suite")
ck("by id", p.update("2", "doing").get("ok"))
ck("…and it stuck", p.items[1]["status"] == "doing")
ck("by exact title", p.update("run the suite", "done").get("ok"))
ck("by unique substring", p.update("parser", "done").get("ok"))
ck("an AMBIGUOUS substring is refused, never guessed",
   not plan("fix the parser", "fix the printer").update("fix the", "done"
                                                        ).get("ok"))
ck("an unknown id is refused", not p.update("99", "done").get("ok"))
ck("…and the refusal lists the real items",
   "read the test" in p.update("99", "done").get("error", ""))
ck("an unknown status is refused", not p.update("1", "banana").get("ok"))
ck("…and names the five valid ones",
   all(w in p.update("1", "banana").get("error", "")
       for w in ("open", "doing", "done", "blocked", "dropped")))

print("\n== blocked and dropped need a reason ==")
p = plan("a", "b")
ck("blocked with no note is REFUSED",
   not p.update("1", "blocked").get("ok"))
ck("…because a silent block is indistinguishable from giving up",
   "reason" in p.update("1", "blocked").get("error", ""))
ck("dropped with no note is REFUSED", not p.update("1", "dropped").get("ok"))
ck("blocked WITH a note is accepted",
   p.update("1", "blocked", "the API key is missing").get("ok"))
ck("…and the note is kept for the operator to read",
   p.items[0]["note"] == "the API key is missing")
ck("done needs no note", p.update("2", "done").get("ok"))


# ── 4. THE COUNTER-PROPERTIES ────────────────────────────────────────
# Every one of these is a way the gate could hold a turn open forever.
# That is a WORSE failure than the one the ledger fixes: an early stop
# costs a follow-up message, a hung turn costs the whole session.
print("\n== completion: the ways a turn is allowed to end ==")
p = plan("a", "b", "c")
p.update("1", "done")
p.update("2", "blocked", "no network")
ck("still open while one item is open", not p.is_complete())
p.update("3", "dropped", "not needed after all")
ck("done + blocked + dropped IS complete", p.is_complete())
ck("…and `open` counts zero", p.counts()["open"] == 0)

p2 = plan("a")
p2.update("1", "doing")
ck("`doing` is OPEN — a plan marked all-doing is not finished",
   not p2.is_complete())

ck("an EMPTY ledger is not 'complete' (absent != finished)",
   not TaskPlan().is_complete())
ck("…and is falsey, so a caller can tell absent from unfinished",
   not bool(TaskPlan()))
ck("a plan with items is truthy", bool(plan("a")))

print("\n== re-planning does not resurrect finished work ==")
p = plan("read it", "fix it", "test it")
p.update("read it", "done")
p.set_plan(["read it", "fix it", "test it", "document it"])
ck("an unchanged title keeps its status",
   p.items[0]["status"] == "done", str(p.items[0]))
ck("a new item arrives open", p.items[3]["status"] == "open")
ck("a dropped item really is gone after a re-plan",
   len(plan("a", "b").set_plan(["a"])["items"]) == 1)

print("\n== churn: re-opening a closed item is counted, not hidden ==")
p = plan("a")
p.update("1", "done")
p.update("1", "open")
ck("churn increments on done -> open", p.churn == 1)
p.update("1", "done")
p.update("1", "doing")
ck("…and again", p.churn == 2)
ck("a normal open -> done does not count as churn", plan("x").churn == 0)


# ── 5. what the host reads ───────────────────────────────────────────
print("\n== the status payload the gates and the UI read ==")
p = plan("alpha", "beta", "gamma")
p.update("1", "done")
st = p.status()
ck("counts every state", st["counts"]["done"] == 1 and st["counts"]["open"] == 2)
ck("reports how many are open", st["open"] == 2)
ck("names the NEXT open item", st["next"] == "beta")
ck("lists what is still open", st["still_open"] == ["beta", "gamma"])
ck("reminds it the turn will not end", "will not end" in st["reminder"])
for i in ("2", "3"):
    p.update(i, "done")
st2 = p.status()
ck("a complete plan says so", st2["complete"])
ck("…and the reminder switches to STOP",
   "STOP" in st2["reminder"] and "final report" in st2["reminder"])
ck("…and forbids restating what is on screen",
   "already on screen" in st2["reminder"])

print("\n== render + summary (what the operator sees) ==")
p = plan("alpha", "beta", "gamma")
p.update("1", "done")
p.update("2", "doing")
r = p.render()
ck("done rows are ticked", "[x] alpha" in r)
ck("in-progress rows are marked", "[~] beta" in r)
ck("open rows are empty boxes", "[ ] gamma" in r)
ck("render is ASCII-only (the emoji font hijacks coloured glyphs)",
   all(ord(c) < 128 for c in r), repr([c for c in r if ord(c) > 127][:5]))
ck("summary counts done out of total", p.summary_line().startswith("1/3 done"))
ck("…and names work in progress", "1 in progress" in p.summary_line())
p.update("3", "blocked", "no key")
ck("…and blocked", "1 blocked" in p.summary_line())
ck("a blocked row shows its reason on screen", "no key" in p.render())
ck("an empty plan renders as nothing", TaskPlan().render() == "")
ck("…and summarises as nothing", TaskPlan().summary_line() == "")
# width=0 (the default) means DO NOT truncate - the terminal log wants the
# whole line. A width is passed only where the row has to fit a column.
ck("render does not truncate by default",
   len(max(plan("x" * 200).render().splitlines(), key=len)) > 100)
ck("render truncates when a width IS given",
   len(max(plan("x" * 200).render(width=40).splitlines(), key=len)) <= 44)


# ── 6. TOTALITY — it is read on the path that ENDS turns ─────────────
print("\n== total: junk in, a dict out, never an exception ==")
JUNK = (None, 0, 1.5, "", "   ", [], {}, object(), [None], [{}],
        [{"title": None}], b"bytes", ["ok", None, 3])
for j in JUNK:
    try:
        out = TaskPlan().set_plan(j)
        ok = isinstance(out, dict) and "ok" in out
    except Exception as e:
        ok = False
        out = f"RAISED {type(e).__name__}: {e}"
    ck(f"set_plan({j!r:.24}) returns a dict", ok, str(out)[:90])

p = plan("a")
for j in JUNK:
    try:
        out = p.update(j, j)
        ok = isinstance(out, dict) and "ok" in out
    except Exception as e:
        ok = False
        out = f"RAISED {type(e).__name__}: {e}"
    ck(f"update({j!r:.20}) returns a dict", ok, str(out)[:80])

for name, fn in (("status", lambda: p.status()),
                 ("items", lambda: p.items),
                 ("open_items", lambda: p.open_items()),
                 ("counts", lambda: p.counts()),
                 ("is_complete", lambda: p.is_complete()),
                 ("render", lambda: p.render()),
                 ("summary_line", lambda: p.summary_line()),
                 ("len", lambda: len(p)),
                 ("clear", lambda: p.clear())):
    try:
        fn()
        ck(f"{name}() does not raise", True)
    except Exception as e:
        ck(f"{name}() does not raise", False, f"{type(e).__name__}: {e}")

print("\n== clear() really clears ==")
p = plan("a", "b")
p.update("1", "done")
p.clear()
ck("no items", len(p) == 0)
ck("not complete (absent, not finished)", not p.is_complete())
ck("churn reset", p.churn == 0)
ck("goal reset", p.goal == "")

print("\n== items() hands out copies, not the live rows ==")
p = plan("a")
got = p.items
got[0]["status"] = "done"
ck("mutating the returned list cannot corrupt the ledger",
   p.items[0]["status"] == "open")

print(f"\ntasks: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
