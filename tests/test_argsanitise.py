#!/usr/bin/env python3
"""
test_argsanitise.py — model output can carry tokeniser / protocol junk, and a
tool must never crash on it.

THE REPORTED FAILURE
====================
A turn died with `web_read failed: UnicodeEncodeError: 'ascii' codec can't
encode character '\\u27e7'`. The model had stapled a stray special-token glyph
(U+27E7 "]") onto a URL; urllib encodes the request line as ASCII, so one
non-ASCII character raised deep in the socket write and killed the whole turn,
which then looped into the empty/degraded retry storm.

Fixing web_read alone would be treating the symptom. The DEFECT IS A CLASS:
every tool that shells out, opens a URL, hits the network, touches sqlite or
writes a file can choke on the same junk. So it is killed at ONE boundary —
parse_tool_calls runs sanitise_tool_args over every parsed argument — and the
URL sink additionally makes any URL ASCII-safe as defence in depth. This suite
proves BOTH: the boundary cleans args for every tool, and the sinks fail closed
(return a dict) instead of raising.

Run:  python3 tests/test_argsanitise.py
"""
from __future__ import annotations
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import basilisk_core as C  # noqa: E402

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


# Every junk character seen in the wild or plausibly emitted by a tokeniser.
_GLYPHS = ["\uff5c", "\u2581", "\u27e6", "\u27e7", "\u2983", "\u2984",
           "\u2e24", "\u2e25", "\ufffd"]
_CTRLS = ["\x00", "\x01", "\x07", "\x08", "\x0b", "\x0c", "\x1b", "\x7f", "\x9f"]
_ALL_JUNK = _GLYPHS + _CTRLS


def _clean_of_glyphs(s):
    return isinstance(s, str) and not any(g in s for g in _GLYPHS)


def _clean_of_ctrls(s):
    return isinstance(s, str) and not any(c in s for c in _CTRLS)


# ── 1. THE BOUNDARY CLEANS ARGS FOR EVERY TOOL ───────────────────────
# The sanitiser runs on every value regardless of tool name, so a call to ANY
# tool comes out clean. We drive it through the real parse path.
print("== boundary: every parsed tool call is cleaned ==")

# A broad, representative slice of the tool surface (names taken from the live
# dispatch map). The guarantee is universal — it does not depend on the name —
# but naming real tools makes the intent obvious and catches a future regression
# that special-cases dispatch.
_TOOLS = [
    "web_read", "web_sources", "cve_lookup", "read_file", "write_file",
    "list_dir", "run", "copy_path", "move_path", "delete_path", "make_dir",
    "path_info", "find_file", "open_url", "image_search", "analyze_image",
    "workspace_read", "workspace_write", "workspace_search", "scope_set",
    "report_findings", "methodology", "wordlist_find", "cheatsheet",
    "memory_read", "skill_run", "parse_output", "submit_flag",
]
_dirty_val = "https://x.example/a" + "".join(_ALL_JUNK) + "b"
_bad_parse = []
for _name in _TOOLS:
    call = f'<tool name="{_name}">{{"url": {_dirty_val!r}, "q": {_dirty_val!r}}}</tool>'
    try:
        calls = C.parse_tool_calls(call)
    except Exception as e:                       # parse itself must never raise
        _bad_parse.append(f"{_name}: parse raised {type(e).__name__}")
        continue
    for cobj in calls:
        for k, v in (cobj.args or {}).items():
            if isinstance(v, str) and not (_clean_of_glyphs(v) and _clean_of_ctrls(v)):
                _bad_parse.append(f"{_name}.{k} still dirty")
ck("parse_tool_calls never raises + cleans args for every tool",
   not _bad_parse, str(_bad_parse[:4]))

# Direct unit coverage of the sanitiser's contract.
ck("every protocol glyph is stripped from a data arg",
   _clean_of_glyphs(C.sanitise_tool_args({"url": "a" + "".join(_GLYPHS) + "b"})["url"]))
ck("every control char is stripped from a data arg",
   _clean_of_ctrls(C.sanitise_tool_args({"path": "a" + "".join(_CTRLS) + "b"})["path"]))
ck("NUL is stripped even from file content (it breaks the write)",
   "\x00" not in C.sanitise_tool_args({"content": "x\x00y"})["content"])
# A file body legitimately may contain a bracket glyph — content is NOT
# glyph-stripped, only control-stripped, so real file data survives.
ck("file content keeps its glyphs (a file body is text, whatever it looks like)",
   C.sanitise_tool_args({"content": "x\u27e7y"})["content"] == "x\u27e7y")
# Nested list / dict args are cleaned too (GLM can send a list value).
_nested = C.sanitise_tool_args({"queries": ["a\uff5cb", "c\x00d"]})["queries"]
ck("list-valued args are cleaned element-wise",
   _nested == ["ab", "cd"], str(_nested))


# ── 2. THE URL SINK IS ASCII-SAFE, NEVER RAISES ──────────────────────
print("\n== url sink hardening ==")
_killer = ("https://www.irishtimes.com/crime-law/2026/09/02/"
           "fairview-park-arrest-rel\u27e7ated")
_safe = C._ascii_safe_url(_killer)
ck("the exact killer URL becomes ASCII-safe", _safe.isascii() and _safe, _safe)
# A genuinely unicode / IDN URL is percent-encoded, not dropped — still usable.
_uni = C._ascii_safe_url("https://ru.wikipedia.org/wiki/\u041f\u0440\u0438\u0432\u0435\u0442")
ck("a real unicode URL is percent-encoded, not discarded",
   _uni.isascii() and "%D0" in _uni, _uni)
# web_read on the raw killer must NOT raise UnicodeEncodeError.
try:
    _r = C.tool_web_read(_killer)
    ck("web_read on the killer URL returns a dict, never raises",
       isinstance(_r, dict) and "UnicodeEncodeError" not in str(_r.get("error", "")))
except Exception as e:
    ck("web_read on the killer URL returns a dict, never raises", False,
       f"raised {type(e).__name__}: {e}")


# ── 3. SINK FUNCTIONS FAIL CLOSED ON RAW JUNK (bypassing the boundary) ─
# Even if junk somehow reaches a sink directly, it must return a dict, not throw.
print("\n== sinks fail closed on raw junk ==")
_junk_path = "/tmp/does\u27e7not\x00exist_" + "\uff5c"
_junk_url = "http://x.example/\u27e7\x00"
_sink_checks = [
    ("read_file",  lambda: C.tool_read_file(_junk_path)),
    ("list_dir",   lambda: C.tool_list_dir(_junk_path)),
    ("path_info",  lambda: C.tool_path_info(_junk_path)),
    ("web_read",   lambda: C.tool_web_read(_junk_url)),
    ("open_url",   lambda: C.tool_open_url(_junk_url)),
    ("web_sources", lambda: C.tool_web_sources()),
]
for _sname, _call in _sink_checks:
    try:
        _res = _call()
        ck(f"{_sname} returns a dict on junk (fails closed)", isinstance(_res, dict))
    except Exception as e:
        ck(f"{_sname} returns a dict on junk (fails closed)", False,
           f"raised {type(e).__name__}: {e}")


print(f"\nargsanitise: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
