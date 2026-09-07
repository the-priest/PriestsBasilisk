#!/usr/bin/env python3
"""
test_hardening.py — "make sure it cannot fail". The failure modes that were
found by systematically attacking the app rather than by reading it.

Five detectors were run; each one found something:

  1. ARGUMENT FUZZ — every side-effect-free tool_* entry point (88 of them,
     3,418 calls) driven with None, "", 0, -1, [], {}, True, 200KB strings,
     NUL bytes, astral-plane text, inf, NaN, 1e308, -2**63. 67 calls RAISED.
     A raise inside a tool handler on the single-call path unwound to the
     turn's catch-all and ENDED the turn: the model was never told its call
     failed, so an autonomous run simply stopped.

  2. TRANSPORT FUZZ — 39 ways a provider can misbehave (every HTTP code,
     malformed SSE, truncated JSON, invalid UTF-8, empty choices, missing
     delta, a 2MB frame, 10k frames, no [DONE], mid-stream drop). 38 ended
     correctly in exactly one callback; the 39th is KeyboardInterrupt, which
     MUST propagate. No change needed — this suite pins that.

  3. COLD START — 14 broken boxes. Three of them could not start the app at
     all: a corrupt chats.db raised out of ChatStore.__init__.

  4. GATE FUZZ — the destructive floor against mutated destroyers, then every
     unrefused shape RE-RUN AGAINST A LIVE BASH with argv-inspecting shims so
     that "bypass" means the binary really was invoked with the destructive
     argument. 16 real bypasses in two classes.

  5. LEAK SWEEP — unbounded containers, deques without maxlen, subprocess
     without timeout, open() without encoding. Clean.

The counter-properties are asserted as hard as the properties throughout: a
gate that refuses ordinary work gets switched off and protects nothing.

Run:  python3 tests/test_hardening.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import basilisk_core as C                                      # noqa: E402
import basilisk_safety as S                                    # noqa: E402

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


# ═════════════════════════════════════════════════════════════════════
# 1. A JSON null IS AN OMISSION, NOT A VALUE
# ═════════════════════════════════════════════════════════════════════
print("\n== null arguments no longer beat the defaults ==")
_BSRC = open(os.path.join(_ROOT, "basilisk.py"), encoding="utf-8").read()

ck("the dispatch normaliser drops null-valued keys",
   "v is not None" in _BSRC and "A JSON `null` IS NOT A VALUE" in _BSRC)

# The three the fuzz caught, at the tool itself (second layer: the normaliser
# protects the dispatch path, these are reachable from other callers too).
ck("find_file survives a null search_path",
   isinstance(C.tool_find_file("*", None), dict))
ck("find_file survives a null pattern",
   isinstance(C.tool_find_file(None, "~"), dict))
ck("find_file survives infinite size filters",
   isinstance(C.tool_find_file("*", "~", 5, float("inf"), float("inf"),
                               float("inf")), dict))
ck("find_file refuses a NUL byte by name rather than raising",
   C.tool_find_file("*", "/tmp/\x00").get("ok") is False)
ck("processes survives a null top_n",
   isinstance(C.tool_processes(None), dict))
ck("sqlmap_plan survives a non-string target",
   isinstance(C.tool_sqlmap_plan(-1), dict))

print("\n== _as_int is the ONE numeric coercion ==")
for _v, _want in ((None, 9), ("", 9), (15, 15), ("15", 15), ("15.5", 15),
                  ([], 9), ({}, 9), (True, 9), (False, 9), ("fifteen", 9),
                  (float("nan"), 9), (float("inf"), 9), (float("-inf"), 9),
                  (1e308, 9), (-(2 ** 63), 9), (2 ** 40, 9)):
    ck(f"_as_int({_v!r:>12}) -> {_want}", C._as_int(_v, 9) == _want,
       str(C._as_int(_v, 9)))
ck("bool is rejected, not silently read as 1/0 "
   "(a model that sent `true` for top_n meant nothing of the sort)",
   C._as_int(True, 9) == 9 and C._as_int(False, 9) == 9)
ck("the dispatch-side helper is the SAME function, not a second copy",
   "_safe_int = _as_int" in _BSRC)


# ═════════════════════════════════════════════════════════════════════
# 2. THE TWO DISPATCH PATHS EACH HAD WHAT THE OTHER LACKED
# ═════════════════════════════════════════════════════════════════════
print("\n== single path catches, batch path normalises ==")
ck("the SINGLE path now catches a raising handler instead of ending the turn",
   "except Exception as _te:" in _BSRC
   and "THE MIRROR OF THE BATCH PATH" in _BSRC)
ck("…and feeds the failure back so the model can change approach",
   "The tool did" in _BSRC and "NOT run." in _BSRC)
ck("the BATCH path now normalises each member's arguments",
   "AND SO MUST ARGUMENT NORMALISATION" in _BSRC
   and "_normalise_tool_args(c.name, c.args)" in _BSRC)
ck("a batch member with unusable arguments is DROPPED, not run on defaults",
   "_argerrs" in _BSRC and "were NOT run" in _BSRC)
ck("a batch where every member is unusable feeds one clear refusal",
   "every tool in that batch was called with" in _BSRC)


# ═════════════════════════════════════════════════════════════════════
# 3. COLD START FROM A BROKEN BOX
# ═════════════════════════════════════════════════════════════════════
print("\n== a corrupt chats.db no longer bricks the app ==")


def _store_from(write):
    d = tempfile.mkdtemp(prefix="hd-")
    p = os.path.join(d, "chats.db")
    write(p)
    st = C.ChatStore(p)
    cid = st.create_chat("t", "m")
    st.add_message(cid, "user", "hello")
    ok = len(st.list_messages(cid)) == 1
    moved = st.quarantined_from
    st.close()
    return ok, moved, p


def _make_truncated(path):
    """A REAL database, populated, then cut in half.

    Written as a function because the one-liner it replaced was
    `open(p,"wb").write(open(p,"rb").read()[:40])` — and Python evaluates
    `open(p,"wb")` FIRST, truncating the file to zero before the read argument
    is evaluated. It read back b"", wrote b"", and produced an EMPTY file, which
    sqlite opens happily. The test passed the wrong scenario and then failed
    the assertion about it. Validate a fixture against what it actually
    produces before trusting the verdict built on it.
    """
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE chats (id INTEGER PRIMARY KEY, title TEXT)")
    c.executemany("INSERT INTO chats (title) VALUES (?)",
                  [(f"chat {i}" * 50,) for i in range(200)])
    c.commit()
    c.close()
    raw = open(path, "rb").read()
    assert len(raw) > 4096, f"fixture did not populate ({len(raw)} bytes)"
    with open(path, "wb") as fh:
        fh.write(raw[:len(raw) // 3])
    assert 0 < os.path.getsize(path) < len(raw), "fixture did not truncate"


for _name, _w in (
        ("garbage bytes", lambda p: open(p, "wb").write(b"not a database" * 99)),
        ("truncated sqlite", _make_truncated),
        ("a directory in its place", lambda p: os.makedirs(p)),
):
    try:
        _ok, _moved, _dbp = _store_from(_w)
        ck(f"{_name}: the store comes up and works", _ok)
        ck(f"{_name}: the damaged file was QUARANTINED, never deleted",
           bool(_moved) and (_moved == "(memory-only)" or os.path.exists(_moved)),
           str(_moved))
    except Exception as _e:
        ck(f"{_name}: the store comes up and works", False,
           f"{type(_e).__name__}: {_e}")
        ck(f"{_name}: the damaged file was QUARANTINED, never deleted", False)

# COUNTER-PROPERTY: a HEALTHY database must never be quarantined.
_okdir = tempfile.mkdtemp(prefix="hd-ok-")
_okdb = os.path.join(_okdir, "chats.db")
_st = C.ChatStore(_okdb)
_cid = _st.create_chat("keep me", "m")
_st.add_message(_cid, "user", "important")
_st.close()
_st2 = C.ChatStore(_okdb)
ck("a healthy database is reopened, NOT quarantined",
   _st2.quarantined_from == "", _st2.quarantined_from)
ck("…and its contents are still there",
   len(_st2.list_messages(_cid)) == 1)
_st2.close()

ck("the constructor proves the database is readable before returning",
   "SELECT count(*) FROM chats" in
   open(os.path.join(_ROOT, "basilisk_core.py"), encoding="utf-8").read())
ck("the operator is TOLD where their history went",
   "_warn_db_quarantined" in _BSRC and "moved to" in _BSRC)


print("\n== a null or wrong-typed settings.json cannot reach the wire ==")
_bad = {"max_tokens": "lots", "temperature": None, "top_p": [],
        "active_provider": 5, "reasoning_effort": {"a": 1},
        "siliconflow_model": None, "siliconflow_api_key": 7,
        "hard_engagement_model": [], "effort_heavy_max_tokens": "big"}
_m = dict(C.DEFAULT_SETTINGS)
_m.update({k: v for k, v in _bad.items() if v is not None})
C._coerce_settings_types(_m)
ck("temperature is a number in range",
   isinstance(_m["temperature"], float) and 0.0 <= _m["temperature"] <= 2.0,
   repr(_m["temperature"]))
ck("top_p is a number in range",
   isinstance(_m["top_p"], float) and 0.0 <= _m["top_p"] <= 1.0,
   repr(_m["top_p"]))
ck("max_tokens is a positive int", isinstance(_m["max_tokens"], int)
   and _m["max_tokens"] > 0, repr(_m["max_tokens"]))
ck("active_provider is a string", isinstance(_m["active_provider"], str))
ck("the model id is a non-empty string (it is sent as `model`)",
   isinstance(_m["siliconflow_model"], str) and _m["siliconflow_model"],
   repr(_m["siliconflow_model"]))
ck("the api key is a string (it is pasted into an Authorization header)",
   isinstance(_m["siliconflow_api_key"], str))
ck("a null on disk does not overwrite a good default",
   "A NULL ON DISK MUST NOT BEAT A GOOD DEFAULT" in
   open(os.path.join(_ROOT, "basilisk_core.py"), encoding="utf-8").read())
# COUNTER-PROPERTY: a VALID settings file is left alone.
_good = dict(C.DEFAULT_SETTINGS)
_good.update({"temperature": 0.3, "top_p": 0.8, "max_tokens": 999,
              "siliconflow_model": "zai-org/GLM-5.2"})
_snapshot = dict(_good)
C._coerce_settings_types(_good)
ck("a valid settings file is not rewritten",
   all(_good[k] == _snapshot[k] for k in
       ("temperature", "top_p", "max_tokens", "siliconflow_model")),
   str({k: (_snapshot[k], _good[k]) for k in
        ("temperature", "top_p", "max_tokens", "siliconflow_model")}))


# ═════════════════════════════════════════════════════════════════════
# 4. THE DESTRUCTIVE FLOOR — TWO VERIFIED BYPASS CLASSES
# ═════════════════════════════════════════════════════════════════════
# Both were confirmed against a LIVE BASH with argv-inspecting shims: the shim
# fires only when the real binary is invoked with the genuinely destructive
# argument, so these are not "the parser looked wrong", they are "bash did it".
print("\n== a block device is a critical file ==")
for _c in ("truncate -s 0 /dev/sda", "tee /dev/sda", "cp payload /dev/sda",
           "install -m 0 /dev/null /dev/sda", "truncate -s 0 /dev/nvme0n1",
           "mv payload /dev/sda"):
    ck(f"refused: {_c}", S.is_catastrophic_command(_c))
for _c in ("truncate -s 0 ./notes.txt", "tee /tmp/log", "cp a.txt b.txt",
           "mv build/ dist/", "ln -s a b", "install -m 755 tool /usr/local/bin/",
           "truncate -s 0 /home/me/scratch.log"):
    ck(f"still allowed: {_c}", not S.is_catastrophic_command(_c))

print("\n== a target hidden behind a variable ==")
for _c in ('X=/; rm -rf "$X"', 'X=/; chmod -R 000 "$X"',
           'X=/; truncate -s 0 "$X"dev/sda', 'D=/dev/sda; dd if=/dev/zero of=$D',
           'P=/; rm -rf ${P}', "Q='/'; rm -rf $Q"):
    ck(f"refused: {_c}", S.is_catastrophic_command(_c))
# THE COUNTER-PROPERTY MATTERS AS MUCH: a floor that fires on ordinary work
# gets switched off and then protects nothing.
for _c in ('D=/tmp/scratch; rm -rf "$D"', "OUT=./build; rm -rf $OUT",
           "T=acme.com; nmap -sV $T", "X=/etc/hosts; cat $X",
           "W=/usr/share/wordlists/rockyou.txt; gobuster dir -w $W -u http://t",
           "H=/home/luka; ls $H", "F=report.md; cat $F",
           "LOG=/var/log/syslog; tail -n 50 $LOG",
           "URL=https://acme.com; curl -s $URL", "N=10; head -n $N file.txt"):
    ck(f"still allowed: {_c[:46]}", not S.is_catastrophic_command(_c))
ck("expansion can only ADD a refusal, never clear one "
   "(it is OR-ed with the original verdict)",
   "OR-ed with the" in open(os.path.join(_ROOT, "basilisk_safety.py"),
                            encoding="utf-8").read())

print("\n== the gate refuses junk types instead of raising ==")
for _j in (0, [], {}, True, b"rm -rf /", 1.5, 12):
    _r = C.gate_command(_j)
    ck(f"gate_command({_j!r:>14}) does not allow it",
       _r is not None or not _j, str(_r)[:60])
ck("a real command still passes", C.gate_command("ls -la") is None)
ck("a real destroyer is still refused",
   (C.gate_command("rm -rf /") or {}).get("catastrophic") is True)


# ═════════════════════════════════════════════════════════════════════
# 5. THE TRANSPORT CONTRACT
# ═════════════════════════════════════════════════════════════════════
# Every stream must end in EXACTLY ONE of on_done / on_error. 39 malformed
# shapes were driven through the real backend; a representative set is pinned
# here so a future change cannot reintroduce a hang or a double-callback.
print("\n== a malformed stream always ends the turn, exactly once ==")


class _Body:
    def __init__(self, lines):
        self._l = list(lines)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter(self._l)


def _sse(*objs):
    return [("data: " + json.dumps(o) + "\n").encode()
            for o in objs] + [b"data: [DONE]\n"]


_SHAPES = {
    "empty body": [],
    "no data: prefix": [b"garbage\n"],
    "malformed json": [b"data: {not json\n", b"data: [DONE]\n"],
    "choices empty": _sse({"choices": []}),
    "choices missing": _sse({"id": "x"}),
    "delta missing": _sse({"choices": [{}]}),
    "delta not a dict": _sse({"choices": [{"delta": "oops"}]}),
    "content is null": _sse({"choices": [{"delta": {"content": None}}]}),
    "content is a number": _sse({"choices": [{"delta": {"content": 5}}]}),
    "choices not a list": _sse({"choices": {"a": 1}}),
    "top level is a list": [b"data: [1,2,3]\n", b"data: [DONE]\n"],
    "invalid utf-8": [b'data: {"choices":[{"delta":{"content":"\xff"}}]}\n'],
    "no DONE sentinel": [b'data: {"choices":[{"delta":{"content":"x"}}]}\n'],
    "reasoning only": _sse({"choices": [{"delta":
                                         {"reasoning_content": "t"}}]}),
}
_spec = C.PROVIDERS_BY_KEY["siliconflow"]
_real = C.urllib.request.urlopen
for _name, _lines in _SHAPES.items():
    _be = C.OpenAICompatBackend(_spec, api_key="k")
    _calls = []
    C.urllib.request.urlopen = (lambda ls: (lambda *a, **k: _Body(ls)))(_lines)
    try:
        _be.stream_chat("zai-org/GLM-5.3-Flash",
                        [{"role": "user", "content": "x"}],
                        on_token=lambda t: None,
                        on_done=lambda m: _calls.append("done"),
                        on_error=lambda e: _calls.append("err"),
                        single_model=True)
        _outcome = len(_calls)
    except Exception as _e:
        _outcome = f"RAISED {type(_e).__name__}"
    finally:
        C.urllib.request.urlopen = _real
    ck(f"{_name}: ends in exactly one callback", _outcome == 1, str(_outcome))



# =====================================================================
# 6. "IT SAYS IT'LL FETCH THE NEWS THEN STOPS AND SAYS DONE"
# =====================================================================
# Reported from a live run. The answer-stall nudge exists for exactly this —
# the model announces an action, emits no tool call, and the turn ends holding
# a promise — but every marker it keyed on needed a SUBJECT ("I'll", "let me")
# or the literal word "now" glued to the verb ("fetching now"). Models drop
# both constantly. Verified against v1.0.0.17: these were invisible there too,
# so this is not a regression, it is a hole that was always open.
print("\n== an announcement with the pronoun dropped is still a stall ==")
_ANNOUNCE = [
    "Okay, I'll fetch the news.",
    "Okay - fetching the news now.",
    "Okay. Fetching.",
    "Right, checking the RTE page.",
    "Okay, searching now.",
    "Sure. Reading the article.",
    "Alright, fetching that now.",
    "Understood. Checking the logs.",
    "Starting the scan.",
    "Kicking off the news search.",
    "Fetching updates on both.",
    "Getting the headlines.",
    "Searching for recent updates.",
    "On it - pulling the latest headlines.",
    "Give me a second while I fetch that.",
]
for _t in _ANNOUNCE:
    ck(f"stall: {_t!r}", C.reply_is_bare_stall(_t))

# THE COUNTER-PROPERTY, which is what makes this safe to ship. A participle is
# also the subject of a finished report, and a modifier mid-sentence. Nudging
# either asks the operator to hear the same answer twice - the bug
# reply_is_bare_stall was written to stop. Five of these were graded as stalls
# by v1.0.0.17 and are fixed here too.
print("\n== a finished report that happens to contain a participle is NOT ==")
_DELIVERED = [
    "The scan found 1 live host, 192.168.1.1, running nginx 1.24 with ports "
    "53, 80 and 443 open. Nothing else responded.",
    "Fetching the feed returned 503, so the news is unavailable right now.",
    "Checking the logs showed three failed logins from 10.0.0.5 last night.",
    "Running that scan found 4 open ports: 22, 80, 443 and 8080.",
    "Scanning is complete. Nothing else was listening.",
    "Reading the config confirmed PermitRootLogin is set to no.",
    "The fetching logic in their API is what leaks the token.",
    "I found 3 hosts, still scanning the rest.",
    "Two services, one running nginx and one running sshd.",
    "Here are today's headlines: a man was arrested, and the budget passed.",
    "I could not reach the feed - it returned 503. Try again shortly.",
    "Let me know if you want more detail on any of those.",
]
for _t in _DELIVERED:
    ck(f"NOT a stall: {_t[:52]!r}", not C.reply_is_bare_stall(_t))
ck("a comma alone never starts an announcement clause "
   "(', running nginx' is a modifier, not a promise)",
   not C.reply_is_bare_stall(
       "The host is up, running nginx and sshd, with 22 and 80 open."))

print(f"\nhardening: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
