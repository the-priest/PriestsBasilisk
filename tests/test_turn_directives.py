#!/usr/bin/env python3
"""
test_turn_directives.py — a directive aimed at the OPERATOR's message must not
be re-fired at the model after every tool result.

THE REPORTED FAILURE
====================
One question ("can u test i fixed web reading") produced four separate replies
on screen, each a complete answer to the same question:

    Web reading works — just tested it: https://example.com returned HTTP 200…
    Web reading is working — tested it on https://example.com and got a clean 200…
    Web reading is verified working — example.com returned HTTP 200…
    Web reading is confirmed working — example.com returned HTTP 200, and
    raw.githubusercontent.com also returned clean.

…and four web_reads to establish a fact the first one had already established.
The terminal log showed the tell, repeated before every single round-trip:

    ⚡ urgency fast-path engaged
    💬 answer mode: research, confirm, answer once
    ── thinking…

THE ROOT CAUSE
==============
_kick_assistant_turn rebuilds the system-prompt addendum on EVERY model
round-trip, and three of those directives are properties of the operator's
REQUEST, not of the current turn:

  * "[URGENT …] Lead with the single most likely fix or answer"
  * "[ANSWER MODE] Deliver ONE complete, correct, verified answer, then STOP"
  * "[CHECK ONLINE FIRST] Your FIRST action MUST be to web_read a source"

They are derived by scanning `history` backwards PAST tool results to find the
operator's message — so on turn 2, 3 and 4 they found the same message and
re-armed the identical instruction. Immediately after every tool result the
model was told to lead with the answer, deliver one complete answer, and make
its first action a web_read. It did all three, every time.

The model was not being repetitive. It was being obedient.

THE FIX
=======
_tool_chain_depth already distinguishes "replying to the operator" (1) from
"continuing after a tool result" (2+); nothing consulted it. Now the
request-scoped directives fire on the first turn only, and the continuation
turns get the same rules restated from where the model actually is — with an
explicit ban on re-answering and on re-reading a source that already came back
clean.

Run:  python3 tests/test_turn_directives.py
"""

from __future__ import annotations

import io
import os
import sys
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


# ── GTK stub, same shape as test_toollog.py ──────────────────────────
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
import basilisk_core as Bc                                      # noqa: E402


class _Stop(Exception):
    """Unwind once we have the addendum; the rest of the turn needs a GUI."""


_CAP = {}


def _capture_volatile(addendum="", *a, **k):
    _CAP["addendum"] = addendum
    raise _Stop()


URGENT_Q = ("from the things that i made u do is there any things that are not "
            "working so i can fix bugs can u test i fiexd web reading")
WEBFACT_Q = "what is the latest version of nmap and when was it released"


def addendum_for(depth: int, question: str, tool_ran: bool = True):
    """Drive the REAL _kick_assistant_turn and return (addendum, log lines).

    tool_ran distinguishes the two ways a turn reaches depth > 1: a real tool
    CONTINUATION (a page was read) vs the answer-mode STALL nudge, which
    re-kicks with no tool having run. The continuation directives must fire
    for the first and NOT the second -- telling a model that fetched nothing
    "you already read a source, don't re-read" is what dead-ended the
    news-fetch stall. Default True preserves every existing call."""
    w = object.__new__(Bk.MainWindow)
    w.settings = dict(Bc.DEFAULT_SETTINGS)
    w.settings["approval_mode"] = "none"
    w._stop_requested = False
    w._tool_ran_this_request = tool_ran
    w._tool_chain_depth = depth - 1        # _kick increments to `depth`
    w._tools_locked = False
    w._force_answer_tries = 0
    w.streaming_chat_id = 1
    w.current_chat_id = 1
    w._unleashed = False
    w._mission_active = False
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
    logs = []
    w.terminal_log = lambda m, s="": logs.append(m)

    hist = [{"role": "user", "content": question}]
    for _ in range(depth - 1):
        hist += [
            {"role": "assistant",
             "content": "Web reading works — tested it, HTTP 200."},
            {"role": "user",
             "content": '<tool_result>\n[tool: web_read]\n'
                        '{"ok":true,"status":200,"text":"Example Domain"}\n'
                        '</tool_result>'},
        ]
    w._build_history_for_model = lambda *a, **k: hist

    _saved = Bk.volatile_block
    Bk.volatile_block = _capture_volatile
    _CAP.pop("addendum", None)
    try:
        w._kick_assistant_turn()
    except _Stop:
        pass
    finally:
        Bk.volatile_block = _saved
    return _CAP.get("addendum", ""), logs


LEAD_WITH_ANSWER = "Lead with the single most likely fix or answer"
ANSWER_NOW = "Deliver ONE complete, correct, verified answer"
FIRST_MUST_READ = "Your FIRST action MUST be to"
CONT_GUARD = "CONTINUATION TURN"
CONT_WEB = "STILL VERIFY, DON'T RECALL"


# ── 1. the turn that replies to the operator is unchanged ────────────
print("\n== turn 1 (replying to the operator) keeps every directive ==")
_a1, _l1 = addendum_for(1, URGENT_Q)
ck("harness reached the addendum", bool(_a1), repr(_a1)[:120])
ck("urgency fast-path still fires on turn 1", LEAD_WITH_ANSWER in _a1)
ck("answer mode still fires on turn 1", ANSWER_NOW in _a1)
ck("no continuation guard on turn 1", CONT_GUARD not in _a1)
ck("both log lines are printed once",
   sum(1 for m in _l1 if "urgency fast-path" in m) == 1
   and sum(1 for m in _l1 if "answer mode" in m) == 1, str(_l1))

_w1, _ = addendum_for(1, WEBFACT_Q)
ck("the check-online directive still fires on turn 1", FIRST_MUST_READ in _w1)


# ── 2. continuation turns must not be told to answer again ───────────
print("\n== continuation turns are not re-told to answer ==")
for _d in (2, 3, 4):
    _a, _l = addendum_for(_d, URGENT_Q)
    ck(f"turn {_d}: 'lead with the answer' is NOT re-armed",
       LEAD_WITH_ANSWER not in _a)
    ck(f"turn {_d}: the continuation guard IS present", CONT_GUARD in _a)
    ck(f"turn {_d}: it forbids restating a conclusion",
       "Do NOT restate" in _a)
    ck(f"turn {_d}: the log lines are NOT reprinted", _l == [], str(_l))

_a2, _ = addendum_for(2, URGENT_Q)
ck("the continuation guard names the real failure (a second 'confirmed')",
   "confirmed" in _a2 and "stutter" in _a2)
ck("…and offers exactly two moves: next tool, or final answer",
   "call the next tool" in _a2 and "FINAL answer" in _a2)


# ── 3. and not re-told that their FIRST action must be a web_read ────
print("\n== continuation turns are not re-told to start over with a read ==")
for _d in (2, 3):
    _w, _ = addendum_for(_d, WEBFACT_Q)
    ck(f"turn {_d}: 'FIRST action MUST be to web_read' is NOT re-armed",
       FIRST_MUST_READ not in _w)
    ck(f"turn {_d}: the mid-chain form replaces it", CONT_WEB in _w)
    ck(f"turn {_d}: it bans re-reading an already-read page",
       "re-read a page you have already read" in _w)
    ck(f"turn {_d}: …and re-confirming a clean result",
       "already came back clean" in _w)
    ck(f"turn {_d}: the don't-recall rule SURVIVES (it must not be lost)",
       "stating only what you actually read" in _w)


# ── 4. the safety-shaped directives are NOT weakened ─────────────────
# Only the "start here / answer now" framing is turn-scoped. Anything that
# constrains what the model may CLAIM has to hold on every turn, or this fix
# would have traded repetition for hallucination.
print("\n== nothing that constrains claims was made turn-1-only ==")
for _d in (1, 2, 3):
    _w, _ = addendum_for(_d, WEBFACT_Q)
    ck(f"turn {_d}: answer mode's verify-don't-recall rule is present",
       "CONFIRM, don't recall" in _w or "STILL VERIFY" in _w)
    ck(f"turn {_d}: citing the source is still required",
       "CITE what you used" in _w or "cite it" in _w)

# ── 5. the repeat guard must see BOTH execution paths ───────────────
# From the same log: system_info ran inside a 4-tool parallel batch and then
# again on its own one turn later. The guard was called only from
# _execute_tool_calls, and a batch recorded ONE combined recall entry
# ("system_info + disk_usage + processes + network_status") that no per-tool
# lookup can match — so it was blind to both halves. Same drift class as
# _pure_tool_fn vs dispatch, which is why tests/test_dispatch.py exists.
print("\n== a tool that ran in a batch is not invisible to the repeat guard ==")
from basilisk_ext.recall import ActionLog                       # noqa: E402

_w = object.__new__(Bk.MainWindow)
_w.settings = dict(Bc.DEFAULT_SETTINGS)
_w._action_log = ActionLog()
_w.terminal_log = lambda *a, **k: None


def _call(n, a=None):
    return types.SimpleNamespace(name=n, args=a or {})


_BATCH = [_call("system_info"), _call("disk_usage"),
          _call("processes"), _call("network_status")]
_members = [_w._action_label(c) for c in _BATCH]
_combined = " + ".join(_members)

ck("a batch member gets its own recall label",
   "system_info" in _members, str(_members))
ck("…which the combined label can never match",
   _w._action_log.times_run("system_info") == 0)

# what _feed_tool_result now does for a batch
for _round in range(2):
    _w._action_log.record(_combined, "ok")
    for _m in _members:
        if _m != _combined:
            _w._action_log.record(_m, "ok")

ck("after two batches, system_info counts as run twice",
   _w._action_log.times_run("system_info") == 2,
   str(_w._action_log.times_run("system_info")))
ck("a later SOLO call of that tool is now recognised as a repeat",
   _w._repeat_guard_blocks("system_info") is True)
ck("an unrelated tool is unaffected",
   _w._repeat_guard_blocks("read_file: /etc/hosts") is False)
ck("the decision helper is side-effect free (no message, no log)",
   _w._repeat_guard_blocks("system_info") is True
   and _w._action_log.times_run("system_info") == 2)

_w2 = object.__new__(Bk.MainWindow)
_w2.settings = dict(Bc.DEFAULT_SETTINGS)
_w2._action_log = None
_w2.terminal_log = lambda *a, **k: None
ck("with no action log the guard never blocks",
   _w2._repeat_guard_blocks("system_info") is False)
_w3 = object.__new__(Bk.MainWindow)
_w3.settings = dict(Bc.DEFAULT_SETTINGS)
_w3.settings["repeat_block_after"] = 0
_w3._action_log = _w._action_log
_w3.terminal_log = lambda *a, **k: None
ck("repeat_block_after=0 still disables the guard entirely",
   _w3._repeat_guard_blocks("system_info") is False)

# ── the same answer three times ──────────────────────────────────────
#
# Reported from real use: "it answers a question 3 times sometimes".  The count
# is not a coincidence -- it is 1 answer + ANSWER_STALL_NUDGE_MAX (2) nudged
# re-answers, and _answer_stall_nudges resets per question, so every question
# could spend the full budget.
#
# The answer-mode stall nudge was wired to reply_intends_action(), whose own
# docstring says it is the MISSION loop's predicate: "is it mid-task, or
# finished?"  Answer mode asks a different question -- "did it answer, or only
# narrate?" -- and the two disagree on exactly the common case: a COMPLETE
# answer that also mentions a next step, or that simply ends with the courtesy
# "Let me know if you want more".  "let me know" contains the intent marker
# "let me ", so a finished reply was classified as a stall, nudged, answered
# again, classified again, nudged again.  One predicate, two consumers, second
# consumer asking something else -- the same shape as every other defect in
# this file.
#
# Two fixes, tested separately: sign-offs are no longer read as intent (which
# helps the mission loop too -- a finished report ending "let me know" was
# reading as mid-task), and answer mode now asks whether the reply DELIVERED
# anything, because a reply carrying facts, a list, a table or a code block has
# already given the operator something and nudging it can only duplicate it.
print("\n== a complete answer is never nudged into repeating itself ==")

_COMPLETE = [
    "You're on kernel 7.1.8-1-cachyos, Ryzen 5 PRO 4650U, 12 cores, 15.7 GiB "
    "RAM. Let me know if you want the full uname output.",
    "The audit came back Grade C, score 12: 1 high (SSH root login permitted), "
    "3 medium, 1 low, 2 info. The high is in /etc/ssh/sshd_config -- "
    "PermitRootLogin is set to yes. Let me know if you want the mediums.",
    "I'll summarise what I found:\n\n- 192.168.1.1 is the only live host\n"
    "- ports 53, 80, 443 open\n- nginx 1.24 on 80/443\n\nThat's the subnet.",
    "Here's the answer: CVE-2024-3094 scores 10.0 CRITICAL. It's the xz-utils "
    "backdoor. Let me know if you need the affected version range.",
    "Done -- 6 files in ~/Downloads, newest is tor-browser. Let me know if you "
    "want them sorted differently.",
    "Your disk usage: / is 116 GiB, /home 549 GiB, swap 2.0 GiB. Nothing is "
    "close to full. I'll be happy to dig into any mount point.",
    "```\nPermitRootLogin yes\n```\nThat's the offending line. I'll fix it if "
    "you say go.",
    "| port | service |\n|---|---|\n| 80 | nginx |\n| 443 | nginx |\n\n"
    "I'll scan the rest next if you want.",
    "The scan found 1 live host, 192.168.1.1, running nginx 1.24 with ports 53, "
    "80 and 443 open. Nothing else responded. Next step would be a version "
    "sweep.",
]
for _t in _COMPLETE:
    ck(f"not a stall: {_t[:44]!r}", Bc.reply_is_bare_stall(_t) is False)

# The counter-property is the whole reason the nudge exists: a reply that
# promises work and delivers nothing must still be pushed, or answer mode goes
# back to dying mid-task with a promise the operator never sees kept.
print("\n   -- but a bare stall is still nudged --")
for _t in [
    "I've got the site and the paper metadata. Let me grab the HN discussion "
    "thread... and also look for a news writeup.",
    "Let me check the sshd config first.",
    "I'll run a port scan on the subnet now.",
    "Next, I'll enumerate the web server.",
    "Now I'll look at the firewall rules.",
    "First, I'll check what's listening.",
    "Proceeding to the next check...",
]:
    ck(f"still a stall: {_t[:44]!r}", Bc.reply_is_bare_stall(_t) is True)

print("\n   -- and an empty / degraded reply is not a stall to nudge --")
for _t in ("", "   ", "\n"):
    ck(f"empty is not a stall: {_t!r}", Bc.reply_is_bare_stall(_t) is False)

# The mission loop keeps its own predicate, and gains the sign-off fix.
print("\n== the mission predicate still answers ITS question ==")
for _t, _want in [
    ("I'll now enumerate the web server.", True),
    ("Found 3 hosts. Let me scan them.", True),
    ("Next step: test the login form.", True),
    ("Assessment complete. Let me know if you want the report.", False),
    ("Found 3 hosts. Let me know if you want detail.", False),
    ("I'd be happy to go deeper on any of these.", False),
    ("Mission complete.", False),
]:
    ck(f"intends_action={_want}: {_t[:44]!r}",
       Bc.reply_intends_action(_t) is _want)

# The arithmetic that produced "three times" is pinned so the budget cannot be
# raised without someone reading this.
ck("the nudge budget is 2 (1 answer + 2 nudges was the '3 times')",
   Bk.ANSWER_STALL_NUDGE_MAX == 2, str(Bk.ANSWER_STALL_NUDGE_MAX))
_gsrc = io.open(os.path.join(_ROOT, "basilisk.py"), encoding="utf-8").read()
ck("answer mode is wired to reply_is_bare_stall, not the mission predicate",
   "and reply_is_bare_stall(final)" in _gsrc)
ck("reply_is_bare_stall is imported by the host",
   "reply_is_bare_stall," in _gsrc)


# ── the news-fetch dead end: a bare stall must be told to FETCH ──────
# The answer-mode stall nudge re-kicks the turn with no tool having run.
# Before the fix, _continuation keyed purely on _tool_chain_depth, so that
# re-kick was treated as a continuation and the model was handed the
# mid-chain "you already read a source this turn, don't re-read" text --
# when it had read NOTHING. That steered it to answer from memory (or stop)
# exactly when it needed to go fetch, which is the "can't even fetch news"
# report. The fix: a continuation requires a tool to have ACTUALLY run.
print("\n== a stall with no tool run is told to FETCH, not that it already did ==")

# depth 2, but NO tool ran (the stall path).
_sa, _ = addendum_for(2, WEBFACT_Q, tool_ran=False)
ck("the FULL check-online directive fires (fetch is forced)",
   FIRST_MUST_READ in _sa,
   "a bare stall must be pushed to read a source, not answer from memory")
ck("it is NOT told it already read a source",
   "already read at least one source" not in _sa,
   "telling a model that fetched nothing it already fetched is the dead end")
ck("…and NOT told not to restate a conclusion it never reached",
   "do not simply repeat" not in _sa.lower()
   or "already read at least one source" not in _sa)

# the counter-property: a REAL continuation (a page was read) is unchanged.
_ca, _ = addendum_for(2, WEBFACT_Q, tool_ran=True)
ck("a real tool continuation still gets the mid-chain form",
   "already read at least one source" in _ca)
ck("…and is NOT re-told to start over with a read",
   FIRST_MUST_READ not in _ca)


# ── the stall classifier covers the phrasings a model actually stalls in ──
print("\n== every 'announced but did nothing' phrasing is a stall ==")
_STALLS = [
    "I'll check the latest headlines for you now.",
    "Let me search for that.",
    "Give me a moment while I check.",
    "One moment while I look that up.",
    "Hang on, let me check the sshd config.",
    "Bear with me, fetching the advisory.",
    "On it -- pulling the release notes.",
    "Sure -- searching now.",
    "Working on it.",
    # Bare action-gerund OPENERS: the model announces a fetch with no "let me"
    # / "I'll" / "now", calls no tool, and the turn dies having said "fetching
    # news" without fetching. These matched no intent phrase before, so no
    # nudge fired -- the "says it, doesn't do it" bug.
    "Fetching the latest news for you.",
    "Getting the latest headlines.",
    "Searching for the latest news.",
    "Pulling the latest headlines now.",
    "Gathering the latest news.",
    "Finding the latest updates.",
    "Collecting recent headlines.",
]
for _s in _STALLS:
    ck(f"stall: {_s[:38]!r}", Bc.reply_is_bare_stall(_s), _s)

print("\n== and these are NOT stalls (nudging them loops or repeats) ==")
_NOT = [
    ("a delivered answer", "The latest nmap is 7.95, released in 2024."),
    ("a promise that also delivers", "Let me check: the answer is 42."),
    ("a report with a gerund mid-sentence",
     "Found 3 hosts, still scanning the rest -- 192.168.1.1 is up."),
    ("a request for the operator's input", "Give me the target and I'll scan it."),
    ("a bare operator question", "Which target should I scan?"),
    ("a courtesy sign-off", "Let me know if you want me to dig into any of these."),
    # gerund-opener IDIOMS that are ordinary prose, not action announcements
    ("a getting-started idiom",
     "Getting started with Python is easy: install it first."),
    ("a looking-at idiom", "Looking at this, the answer is 42."),
    ("running-low idiom", "Running low on time, but the host is up."),
]
for _label, _s in _NOT:
    ck(f"not a stall: {_label}", not Bc.reply_is_bare_stall(_s), _s)


# ── the fetch trigger covers the questions people actually ask ──────
# _needs_web_verification decides whether the "read a source before you
# answer" directive fires. A MISS here is the "makes something up instead of
# checking" failure: the model answers a current-state question from stale
# training. These were untested, and two real phrasings slipped through.
print("\n== current-state questions trigger a fetch ==")
_FETCH = [
    "give me some recent news from ireland",
    "what's happening in the world right now",
    "any news today",
    "whats the latest on the situation",
    "who won the match last night",
    "final score of the game yesterday",
    "is python 3.13 out yet",
    "what's the newest nmap",
    "current bitcoin price",
    "what happened this week in tech",
    "whats new with the linux kernel",
    "any updates on the CVE",
    "what's going on with openssl",
    # casual "give me the news" phrasings that carried no latest/news word and
    # were answering from stale memory instead of fetching.
    "what's going on in the world",
    "any headlines",
    "show me the headlines",
    "what are the headlines",
    "catch me up",
    "give me the rundown",
    "whats up today",
    "top stories",
    "any breaking news",
    "current events",
    "fill me in",
]
for _q in _FETCH:
    ck(f"fetch: {_q[:40]!r}", Bk._needs_web_verification(_q), _q)

print("\n== timeless questions do NOT waste a fetch ==")
_NOFETCH = [
    "explain how tcp works",
    "what is a buffer overflow",
    "write a python function to reverse a string",
    "what does the -sV flag do in nmap",
    "how do i grep recursively",
    "why is my regex not matching",
    # 'headline'/'rundown' as plain nouns in a code/design question must NOT
    # fetch -- the false-positive direction of the news-phrasing fix.
    "headlines aren't showing in my css",
    "my headline font is too big",
    "the rundown of how git works",
    "what's happening in my code",
]
for _q in _NOFETCH:
    ck(f"no fetch: {_q[:40]!r}", not Bk._needs_web_verification(_q), _q)
# Word-boundary matching: single-word markers ("current", "cost", "news",
# "score") must NOT fire inside longer words. A raw-substring `in` triggered a
# needless fetch on ordinary coding questions -- a false-positive class present
# since v1.0.0.0.
print("\n== markers do not collide inside longer words ==")
for _q in ["concurrent processing", "recurrent event handler",
           "costume ideas", "underscore the point", "newsletter signup form",
           "restore from backup", "the scoreboard component"]:
    ck(f"no collision: {_q[:34]!r}", not Bk._needs_web_verification(_q), _q)
# but the real words still fetch
for _q in ["what's the current version", "whats the score", "stock price",
           "how much does it cost"]:
    ck(f"real word still fetches: {_q[:30]!r}", Bk._needs_web_verification(_q), _q)



print(f"\nturn_directives: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
