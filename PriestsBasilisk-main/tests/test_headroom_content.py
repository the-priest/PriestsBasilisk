#!/usr/bin/env python3
"""
test_headroom_content.py — the compressor must not destroy the content it was
asked to shrink.

THE REPORTED FAILURE (Basilisk's own bug report, 2026-08-11)
============================================================
Researching employment law, every page it fetched arrived as a stub:

    {"ok":true,"status":200,"text":"<<ccr:5eb8f2bbc609,string,6.6KB>>"}
    [headroom: 7359→335 chars via headroom-ai]

7,359 characters of page reduced to 335, and in one case to a hash. The tool
reported ok:true / status 200, so nothing looked broken — the content was
deleted AFTER the tool succeeded and BEFORE the model saw it. It concluded the
pages were empty and re-fetched them, until the repeat guard locked it out of
the only source that had the answer.

TWO ROOT CAUSES, both about trust
=================================
1. `_real_compress` accepted a third-party compressor's output on ONE test:
   `len(out) < len(text) * 0.95`. "Is it shorter?" is the question a cache
   REFERENCE always answers best — 67 chars for an 8KB page, a 99.2% "win".
   Length was the wrong question; READABILITY was the question.

2. The structural compressor assumes noise is repetitive and signal is
   keyword-shaped. That holds for an nmap dump and inverts for a document:
   `_SIGNAL_RE` matched the lines containing "http://" and "fail", and 114
   lines of the actual answer were dropped as "noise". Worse than an obvious
   hole, because the survivors reassemble into something that READS complete.

The fixes are about content, not about tool names — a `[tool: …]` tag is used
where it exists, but shape detection backstops every tool nobody tagged.

COUNTER-PROPERTY: the whole point of this module is saving tokens on a long
run. Scan and log dumps must still compress hard, or the fix has traded one
bug for a bill. That is asserted here as hard as the property.

Run:  python3 tests/test_headroom_content.py
"""

from __future__ import annotations

import json
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from basilisk_ext import headroom as H                         # noqa: E402
from basilisk_ext.recall import ActionLog, outcome_is_usable   # noqa: E402

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


PAGE = """Unfair Dismissal

Introduction
If you are dismissed from your job you may be entitled to bring a claim for
unfair dismissal under the Unfair Dismissals Acts 1977-2015. To bring a claim
you must generally have at least 12 months continuous service with the
employer. There are some exceptions to the service requirement.

Who is covered
The Acts apply to employees working under a contract of employment. Certain
categories are excluded, including people who have reached normal retiring age
and members of the Defence Forces.

Automatically unfair dismissal
Some dismissals are considered automatically unfair. These include dismissal
for trade union membership, for pregnancy or matters connected with pregnancy,
and for making a protected disclosure to a prescribed person.

What is fair
A dismissal is presumed unfair unless the employer can show substantial grounds
justifying it. Grounds that may justify dismissal include capability,
competence or qualifications, conduct, and redundancy of the role in question.

Procedures
The employer must follow fair procedures. This means the employee should be
told of the complaint, given a chance to respond, allowed representation, and
given a right of appeal against any decision that is reached.

How to apply
You must bring your claim to the Workplace Relations Commission within six
months of the date of dismissal. This can be extended to twelve months where
there is reasonable cause shown for the delay by the complainant.

Redress
There are three forms of redress: reinstatement, re-engagement, or
compensation. Compensation is limited to a maximum of 104 weeks remuneration
and is based on the actual financial loss that the employee has suffered.
"""

# Facts a researcher would actually need off that page.  Probed
# whitespace-insensitively because the source wraps mid-phrase ("within
# six\nmonths") and json.dumps escapes those newlines — a raw substring probe
# reports facts missing from the UNTOUCHED original, which is a checker bug
# masquerading as a finding.  Sanity-checked against the original below before
# any of it is trusted.
FACTS = ["104 weeks", "six months", "reinstatement", "protected disclosure",
         "fair procedures", "12 months continuous"]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\\n", " "))


def kept(text: str) -> int:
    n = _norm(text)
    return sum(1 for f in FACTS if f in n)


print("\n== checker sanity (validate the probe before trusting its verdict) ==")
ck("every fact is present in the untouched page", kept(PAGE) == len(FACTS))
ck("…and in the untouched JSON envelope",
   kept(json.dumps({"text": PAGE})) == len(FACTS))


class _Res:
    def __init__(self, m):
        self.messages = m


def _engine(fn, name="headroom-ai"):
    H._PKG_STATE.update(checked=True, name=name, fn=fn)


def _fallback():
    H._PKG_STATE.update(checked=True, name="fallback", fn=None)


BODY = json.dumps({"ok": True, "status": 200, "url": "https://x.ie/y",
                   "text": PAGE})

# ── 1. a compressor that returns a POINTER has compressed nothing ────
print("\n== an unreadable result is rejected, however small it is ==")
_engine(lambda m, **k: _Res([{"role": "user", "content":
                              '{"ok":true,"text":"<<ccr:5eb8f2bbc609,string,6.6KB>>"}'}]))
got = H._compress_block(BODY, 0.35)
ck("a ccr cache reference is refused", "<<ccr:" not in got, repr(got)[:120])
ck("…and the page is delivered intact instead", kept(got) == len(FACTS))

ck("_real_compress rejects it directly",
   H._real_compress(BODY, 0.35) is None)

for ref in ('<<ccr:abc123,string,6.6KB>>', '<<cache:deadbeef,text,2KB>>',
            '<<ref:0001,blob,9KB>>'):
    _engine(lambda m, _r=ref, **k: _Res([{"role": "user", "content": _r}]))
    ck(f"reference shape refused: {ref}",
       H._real_compress(BODY, 0.35) is None)

# ── 2. non-text content parts are data we cannot render back ─────────
print("\n== a content part we cannot render is refused, not dropped ==")
_engine(lambda m, **k: _Res([{"role": "user", "content": [
    {"type": "text", "text": "Unfair dismissal page."},
    {"type": "ccr", "ref": "5eb8f2bbc609"}]}]))
ck("a non-text part refuses the whole result",
   H._real_compress(BODY, 0.35) is None)
ck("…so the page survives", kept(H._compress_block(BODY, 0.35)) == len(FACTS))

# multi-message results ACCUMULATE rather than keeping only the last.
# Both halves are padded past the pointer floor, or the result is rejected as a
# reference and this asserts nothing about accumulation.
_engine(lambda m, **k: _Res([{"role": "user", "content": "first half " + "a" * 300},
                             {"role": "user", "content": "second half " + "b" * 300}]))
_r = H._real_compress("x" * 4000, 0.35)
ck("multiple returned messages are joined, not overwritten",
   _r is not None and "first half" in _r and "second half" in _r, repr(_r)[:100])

# ── 3. prose is protected from ANY engine, not just the fallback ─────
print("\n== a document is never summarised down to a topic ==")
_engine(lambda m, **k: _Res([{"role": "user", "content":
                              "Page about unfair dismissal. Mentions redress."}]))
got = H._compress_block(BODY, 0.35)
ck("a 4%-of-original 'summary' is refused for a document",
   kept(got) == len(FACTS), f"{len(BODY)}->{len(got)}")

ck("JSON-carried prose is recognised (newlines are escaped inside it)",
   H._json_carries_prose(BODY))
ck("a JSON scan result is NOT treated as prose",
   not H._json_carries_prose(json.dumps(
       {"ports": [{"port": 22, "state": "open"}] * 60})))

# ── 4. shape detection, independent of any tool name ─────────────────
print("\n== prose vs machine output is judged on shape ==")
ck("an article is prose", H._looks_like_prose(PAGE.split("\n")))
ck("an nmap dump is not", not H._looks_like_prose(
    [f"Discovered open port {1000+i}/tcp on 10.0.0.5" for i in range(60)]))
ck("a key=value config is not", not H._looks_like_prose(
    [f"setting_{i} = value{i}" for i in range(40)]))
ck("a JSON body is not", not H._looks_like_prose(
    json.dumps({"a": [1, 2, 3], "b": {"c": 4}}, indent=2).split("\n")))
ck("a two-line snippet is not (too little evidence)",
   not H._looks_like_prose(["Some words here in a line.", "And another one."]))

# ── 5. when a document IS cut, it is cut contiguously and loudly ─────
print("\n== a document is truncated, never shredded ==")
_fallback()
ck("an ordinary-sized document is not cut at all",
   H._crush(PAGE, 0.35) == PAGE, f"{len(PAGE)}")

BIG = PAGE * 12
big = H._crush(BIG, 0.35)
ck("a huge document is never cherry-picked by keyword",
   "noise lines omitted" not in big and "signal lines kept" not in big)
ck("…the gap is marked INCOMPLETE so the model knows to re-read",
   "[INCOMPLETE]" in big)
ck("…at least 60% is retained", len(big) >= len(BIG) * 0.6,
   f"{len(BIG)}->{len(big)}")
ck("…and both the opening AND the conclusion survive",
   big.startswith("Unfair Dismissal") and "104 weeks" in _norm(big[-3000:]))

# ── 6. the explicit [tool: …] tag ────────────────────────────────────
print("\n== the source tag, and the envelope it must not break ==")
env = f"<tool_result>\n[tool: web_read]\n{BODY}\n</tool_result>"
ck("the tag is readable", H._source_tool(f"[tool: web_read]\n{BODY}") == "web_read")
ck("an untagged body yields ''", H._source_tool(BODY) == "")
ck("THE ENVELOPE IS UNCHANGED — `\"<tool_result>\" in content` still holds",
   "<tool_result>" in env and env.count("</tool_result>") == 1)
ck("…and headroom's own _TOOL_RE still matches it",
   H._TOOL_RE.search(env) is not None)

_engine(lambda m, **k: _Res([{"role": "user", "content": "gutted"}]))
pad = [{"role": "user", "content": "<tool_result>\n" + ("z\n" * 800)
        + "</tool_result>"} for _ in range(2)]
out, _st = H.compress_messages(
    [{"role": "system", "content": "s"}, {"role": "user", "content": env}] + pad,
    {"headroom_enabled": True})
ck("a tagged web_read result passes through untouched", out[1]["content"] == env)

# Configurability is asserted on a NON-prose payload, so it measures the skip
# list itself and not the prose floor.  (Emptying the list does NOT re-expose a
# document to destruction — the content protection is independent and still
# applies. That is defence in depth, and it is why this needs a scan dump.)
_scan = "\n".join(f"Discovered open port {1000+i}/tcp on 10.0.0.5"
                  for i in range(300))
env_tagged = f"<tool_result>\n[tool: web_read]\n{_scan}\n</tool_result>"
_fallback()
_on = H.compress_messages(
    [{"role": "system", "content": "s"},
     {"role": "user", "content": env_tagged}] + pad,
    {"headroom_enabled": True})[0][1]["content"]
_off = H.compress_messages(
    [{"role": "system", "content": "s"},
     {"role": "user", "content": env_tagged}] + pad,
    {"headroom_enabled": True, "headroom_skip_tools": []})[0][1]["content"]
ck("a tagged tool is skipped while it is on the list", _on == env_tagged)
ck("…and the list is configurable — emptying it re-enables compression",
   _off != env_tagged and len(_off) < len(env_tagged))
ck("a comma-separated string setting is accepted too",
   H.compress_messages(
       [{"role": "system", "content": "s"}, {"role": "user", "content": env}] + pad,
       {"headroom_enabled": True,
        "headroom_skip_tools": "web_read, read_file"})[0][1]["content"] == env)

# ── 7. COUNTER-PROPERTY: the token saving must survive ───────────────
print("\n== machine output still compresses hard (the saving is the point) ==")
_fallback()
dump = ("Starting Nmap 7.94\n"
        + "\n".join(f"Discovered open port {1000+i}/tcp on 10.0.0.5   "
                    f"[scan progress {i}]" for i in range(400))
        + "\n22/tcp open ssh OpenSSH 9.6\nCVE-2023-12345 found\n"
          "ERROR: host seems down retrying\ntrailing line\n")
env_run = f"<tool_result>\n[tool: run]\n{dump}\n</tool_result>"
out, st = H.compress_messages(
    [{"role": "system", "content": "s"},
     {"role": "user", "content": env_run}] + pad,
    {"headroom_enabled": True})
comp = out[1]["content"]
ck("a scan dump is still crushed hard", len(comp) < len(env_run) * 0.25,
   f"{len(env_run)}->{len(comp)}")
ck("…and its findings still survive",
   "22/tcp open ssh" in comp and "CVE-2023-12345" in comp
   and "ERROR: host seems down" in comp)
ck("…and the stats still report a real saving", st["pct"] > 40, str(st))

# ── 8. the repeat guard vs a result that never arrived ───────────────
print("\n== the repeat guard counts DELIVERED runs, not attempts ==")
ck("a headroom stub is 'damaged in transit'",
   not outcome_is_usable("{...}\n[headroom: 7359→335 chars via headroom-ai]"))
ck("a ccr reference is too",
   not outcome_is_usable('{"text":"<<ccr:5eb8f2bbc609,string,6.6KB>>"}'))
ck("a history-trim marker is too",
   not outcome_is_usable("head…[earlier tool output trimmed to save tokens]"))
ck("an INCOMPLETE marker is too", not outcome_is_usable("a [INCOMPLETE] b"))
ck("an ordinary result is NOT", outcome_is_usable("Compensation: 104 weeks."))
ck("an EMPTY result is NOT damaged — silent success is a real answer",
   outcome_is_usable(""))
ck("a tool FAILURE is NOT damaged either — repeating it is still pointless",
   outcome_is_usable("error: host unreachable (rc=1)"))

ACT = "web_read: https://www.citizensinformation.ie/en/employment/x"
L = ActionLog()
L.record(ACT, "{...}\n[headroom: 7359→335 chars via headroom-ai]")
L.record(ACT, '{"text":"<<ccr:5eb8f2bbc609,string,6.6KB>>"}')
ck("two GUTTED reads do not trip the guard", not L.should_block(ACT, 2))
ck("…and are counted as attempts but not deliveries",
   L.times_run(ACT) == 2 and L.times_delivered(ACT) == 0)
L.record(ACT, "Compensation is limited to 104 weeks remuneration.")
L.record(ACT, "Compensation is limited to 104 weeks remuneration.")
ck("two DELIVERED reads do trip it", L.should_block(ACT, 2))

L2 = ActionLog()
for _ in range(4):
    L2.record("web_read: https://x", "[headroom: 9000→200 chars via headroom-ai]")
ck("a permanently-gutted read still stops at the grace ceiling — no infinite "
   "retry", L2.should_block("web_read: https://x", 2),
   f"attempts={L2.times_run('web_read: https://x')}")

L3 = ActionLog()
L3.record("run: nmap -sV 10.0.0.5", "error: host unreachable (rc=1)")
L3.record("run: nmap -sV 10.0.0.5", "error: host unreachable (rc=1)")
ck("a repeatedly FAILING tool is still blocked",
   L3.should_block("run: nmap -sV 10.0.0.5", 2))

# ── 9. the shape test must stay cheap ────────────────────────────────
# The first version of _looks_like_prose scanned every line and ran twice per
# block, which made a 1MB request 3.5x slower — a compressor that costs more
# than it saves is not a compressor.  Asserted as a SCALING EXPONENT rather
# than a millisecond ceiling, because a ceiling passes or fails on how busy the
# machine is and this has to mean something on a slow box too.
print("\n== the content checks scale, they do not scan everything ==")
import time                                                     # noqa: E402

_small = "\n".join(f"Discovered open port {1000+i}/tcp on 10.0.0.5"
                   for i in range(2000))
_large = "\n".join(f"Discovered open port {1000+i}/tcp on 10.0.0.5"
                   for i in range(16000))          # 8x the lines


def _time(fn, *a):
    t = time.perf_counter()
    for _ in range(5):
        fn(*a)
    return (time.perf_counter() - t) / 5


_ts = _time(H._looks_like_prose, _small.split("\n"))
_tl = _time(H._looks_like_prose, _large.split("\n"))
_ratio = (_tl / _ts) if _ts > 0 else 0
ck(f"8x the lines costs well under 8x the time (sampled, not scanned) "
   f"— measured {_ratio:.1f}x", _ratio < 4.0, f"{_ts*1000:.2f}ms -> {_tl*1000:.2f}ms")
ck("…and the verdict is unchanged by sampling",
   H._looks_like_prose(_small.split("\n")) is False
   and H._looks_like_prose(_large.split("\n")) is False)
ck("a long document is still recognised despite sampling",
   H._looks_like_prose((PAGE * 20).split("\n")))
ck("a log with a prose preamble is NOT called prose "
   "(sampling strides, it does not read the header)",
   not H._looks_like_prose((PAGE + "\n" + _large).split("\n")))


# ── 10. nothing here may raise ───────────────────────────────────────
print("\n== fail-safe ==")
for bad in (None, "", "{", "<<ccr:>>", "[tool: ]", "\x00\x01"):
    try:
        H._source_tool(bad or "")
        H._looks_like_prose((bad or "").split("\n"))
        H._json_carries_prose(bad or "")
        H._compress_block(bad or "", 0.35)
        outcome_is_usable(bad)
        ok = True
    except Exception as e:
        ok = False
        print(f"       raised on {bad!r}: {type(e).__name__}: {e}")
    ck(f"junk input safe: {bad!r}", ok)

print(f"\nheadroom_content: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
