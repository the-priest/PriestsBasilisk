#!/usr/bin/env python3
"""
test_v1_regressions.py — the v1.0.0.0 bug set, each pinned by the property it
broke rather than by the line that broke it.

Every check below FAILS against v9.9.2. That is the bar: a regression test
that also passes on the broken build is documentation, not a test.

The set divides into two halves, and they came from opposite directions:

  · THE ANSWER ARRIVING TWICE. Four independent heuristics could each re-kick
    a finished turn, and none of them asked whether an answer had already been
    delivered. The operator asked one question and read the reply two or three
    times.

  · THE AUTHORISATION GATES FAILING OPEN. Clustered short options, awk/sed
    programs that spawn processes, and single-label hostnames each walked past
    a boundary that reported itself intact.

Run:  python3 tests/test_v1_regressions.py
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import basilisk_core as C           # noqa: E402
import basilisk_scope as S          # noqa: E402

_passed = 0
_failed = 0


def ck(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  PASS {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}" + (f"   [{detail}]" if detail else ""))


# ══════════════════════════════════════════════════════════════════════
# 1. THE SAME ANSWER, TWO AND THREE TIMES
# ══════════════════════════════════════════════════════════════════════
# The host compares parse_tool_calls() against looks_like_failed_tool_call().
# "nothing parsed, but protocol is present" is read as "the model tried to
# call a tool and we could not read it", which injects a scold and re-kicks
# the turn. The model has nothing new to send, so it repeats its answer.
#
# The two predicates disagreed about fences: the parser masks them (a fenced
# tag is an EXAMPLE, not a call), the detector did not. So any reply
# containing a fenced tag -- or merely an HTML snippet with a name attribute,
# because one debris pattern is a bare `name="..."`> -- was treated as a
# failed call. Asking Basilisk to explain its own tool syntax did it every
# time.
print("== a documented example is not a failed tool call ==")

_FENCED = [
    ("a fenced tool example",
     'Use this format:\n\n```xml\n<tool name="run">{"command":"ls"}</tool>\n```\n'
     'Done.'),
    ("a fenced HTML form",
     'Here is a login form:\n\n```html\n<input type="text" name="username">\n'
     '```\nThat is it.'),
    ("a fenced function-call dialect",
     'Other hosts use:\n\n```\n<function=web_read>{"url":"x"}</function>\n```'),
]
for _label, _t in _FENCED:
    ck(f"{_label}: parses as zero calls", not C.parse_tool_calls(_t))
    ck(f"{_label}: is NOT flagged as a failed call",
       not C.looks_like_failed_tool_call(_t),
       "the parser ignores it; the detector must agree or the turn re-kicks")

# The DISPLAY side has to agree too. scrub_tool_debris/strip_tool_calls ran
# over the whole reply including fences, so the example was deleted out of the
# code block and the operator was shown an empty ```xml ``` -- which reads as
# the app being broken, the exact impression those functions exist to prevent.
print("\n== and the example survives to the screen ==")
for _label, _t in _FENCED:
    _shown = C.scrub_tool_debris(C.strip_tool_calls(_t))
    ck(f"{_label}: the fenced body is still there",
       "```" in _shown and _shown.count("```") >= 2 and
       not re.search(r"```[a-z]*\s*```", _shown),
       repr(_shown[:80]))

# None of which may cost a real call its execution.
print("\n== a real call still runs, a broken one is still caught ==")
_real = 'Running it now. <tool name="run_command">{"command":"ls"}</tool>'
_calls = C.parse_tool_calls(_real)
ck("an unfenced call still parses", len(_calls) == 1 and
   _calls[0].name == "run_command")
ck("an unfenced call is still stripped from the display",
   "<tool" not in C.strip_tool_calls(_real))
ck("a genuinely broken call is still detected",
   C.looks_like_failed_tool_call('I will run it <tool name="run"'))
ck("plain prose is not",
   not C.looks_like_failed_tool_call("The answer is 42. Nothing here."))

# ── A SENTENCE CAN PROMISE AND DELIVER AT THE SAME TIME ──
# reply_is_bare_stall dropped every sentence containing an intent marker and
# measured what was left against an 80-character bar. When the promise and
# the answer shared one sentence, the answer went with it -- and the nudge
# budget is 2, so the operator saw the same short answer three times.
print("\n== a short answer is an answer, not a stall ==")
for _t in ("Let me check that for you: the answer is 42.",
           "I'll summarise: the host is up and port 22 is open.",
           "Let me be precise -- the CVE is CVE-2024-1234 and it is unpatched.",
           "I'll explain: nmap uses a SYN scan by default when run as root.",
           "First, I checked the host. It is up.",
           "I ran the scan. Ports 22 and 80 are open.",
           "The answer is 42.",
           "Let me know if you want more detail."):
    ck(f"delivered: {_t[:44]!r}", not C.reply_is_bare_stall(_t))

# The counter-property. A stall is a reply that promises and delivers
# NOTHING, and those must still be nudged or the mission loop stops moving.
print("\n== but a real stall is still a stall ==")
for _t in ("Let me run the scan now.",
           "I'll check that and get back to you.",
           "Next, I will enumerate the subdomains.",
           "Proceeding to the next step.",
           "I'm going to start the scan.",
           "Let me try a different approach.",
           "I'll start with recon. This is important.",
           "Let me look into that."):
    ck(f"stall: {_t[:44]!r}", C.reply_is_bare_stall(_t))

# ── ONE CHARACTER IS AN ANSWER ──
# looks_degraded's bar was `len(t) < 2`, and a degraded verdict costs a full
# extra turn whose reply lands BELOW the one already on screen -- so the
# shortest correct answers were the likeliest to be shown twice.
print("\n== the shortest answers are not degraded ==")
for _t in ("7", "y", "n", "42", "no"):
    ck(f"kept: {_t!r}", not C.looks_degraded(_t))
for _t in ("", "   ", "\n\n"):
    ck(f"degraded: {_t!r}", C.looks_degraded(_t))
ck("real repetition is still degraded",
   C.looks_degraded("the the the the the the the the the the"))


# ══════════════════════════════════════════════════════════════════════
# 2. THE GUI SIDE OF THE SAME BUG, AND THE LEAK
# ══════════════════════════════════════════════════════════════════════
# Source-level, because these are wiring properties and the GTK stack is not
# importable in every environment this suite runs in.
print("\n== the host does not ask again for an answer it already has ==")

_SRC = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "basilisk.py"), encoding="utf-8").read()

ck("a failed-call re-kick requires the answer to be MISSING",
   re.search(r"_bad_call\s*=\s*\(not cancelled and not executable\s*\n"
             r"\s*and not _visible", _SRC) is not None,
   "_empty_answer was gated on `not _visible` and _bad_call was not")
ck("a dropped-call re-kick requires the answer to be MISSING",
   "_drop_without_answer = bool(_locked_drop) and not _visible" in _SRC)

print("\n== a delayed kick is part of the turn ==")
ck("delayed kicks go through one cancellable helper",
   "def _schedule_kick(self, delay_ms: int):" in _SRC
   and "def _cancel_pending_kick(self):" in _SRC)
# Comment lines are stripped first: this file documents the old shape in a
# comment, and a test that trips over its own explanation is a bad test.
_CODE = "\n".join(l for l in _SRC.splitlines()
                  if not l.lstrip().startswith("#"))
ck("no bare timeout_add still schedules a kick",
   not re.search(r"GLib\.timeout_add\([^)]*lambda[^)]*_kick_assistant_turn",
                 _CODE, re.S),
   "an un-cancellable kick fires after Stop, because _send_user_message "
   "clears _stop_requested on the operator's next message")
ck("_is_busy() counts a pending kick",
   re.search(r"def _is_busy.*?_pending_kick_id", _SRC, re.S) is not None,
   "otherwise the app reports idle for up to 60s of back-off and accepts a "
   "second turn on top of the one already coming")
ck("Stop cancels a pending kick",
   re.search(r"def _request_stop.*?_cancel_pending_kick\(\)", _SRC, re.S)
   is not None)

print("\n== every stream carries its own identity ==")
ck("a stream epoch is captured and compared",
   "self._stream_epoch" in _SRC and "def _stale_stream(self, epoch)" in _SRC)
for _cb in ("_on_stream_token", "_on_stream_done", "_on_stream_error",
            "_on_stream_reasoning"):
    ck(f"{_cb} takes and checks the epoch",
       re.search(rf"def {_cb}\(self, \w+, epoch=None\)", _SRC) is not None
       and re.search(rf"def {_cb}\(self.*?_stale_stream\(epoch\)", _SRC, re.S)
       is not None,
       "an abandoned stream's tokens otherwise append to the NEXT turn's "
       "bubble and its error path retries a turn that is not its own")
ck("abandoning a stuck stream retires its epoch",
   re.search(r"watchdog|never reported back", _SRC) is not None
   and _SRC.count("self._stream_epoch = getattr(self, \"_stream_epoch\", 0) + 1")
   >= 2)

print("\n== a trimmed bubble is actually freed ==")
# dispose_widget nulled Python attributes and the docstring said that "breaks
# any reference cycle so CPython reclaims the widget". It did not: the cycle
# runs widget -> button -> C closure -> callback -> widget, and CPython cannot
# see the middle two hops. Measured before: 120 exchanges with a hard 20-row
# budget left 130 MessageWidgets and 120 CodeBlockWidgets alive. After: 20
# and 10, flat.
ck("signal handlers are tracked",
   "def _track_connect(owner, widget, signal: str, cb) -> int:" in _SRC)
ck("...and disconnected on disposal",
   "def _drop_signals(owner) -> None:" in _SRC
   and "_drop_signals(self)" in _SRC)
ck("...including every block inside the bubble",
   "def _drop_signals_recursive(root) -> None:" in _SRC
   and "_drop_signals_recursive(self)" in _SRC,
   "a CodeBlockWidget's copy button pins the code block the same way")
# Scoped to the PER-MESSAGE widget classes. MainWindow and the settings
# dialog also connect buttons, and those are long-lived singletons -- one
# handler each for the life of the app, not one per reply. The leak is
# specifically a widget built per message and trimmed per message.
def _class_body(name: str) -> str:
    m = re.search(rf"^class {name}\(.*?\):\n(.*?)(?=\n(?:class |def )\S)",
                  _SRC, re.S | re.M)
    return m.group(1) if m else ""


for _cls in ("MessageWidget", "CodeBlockWidget", "ProposedCommandWidget",
             "ProposedEditWidget", "ActivityFeedWidget"):
    _body_src = _class_body(_cls)
    ck(f"{_cls} captured for inspection", bool(_body_src))
    ck(f"{_cls} connects nothing untracked",
       not re.search(r"^\s+(?:self\.)?\w*(?:_btn|btn)\.connect\(",
                     _body_src, re.M),
       "an untracked handler on a per-message widget is an un-freeable widget")

print("\n== the view does not move under the operator ==")
ck("only a USER message forces the scroll",
   re.search(r'if role == "user":\s*\n\s*GLib\.idle_add\('
             r'self\._force_scroll_to_bottom\)\s*\n\s*else:\s*\n'
             r'\s*GLib\.idle_add\(self\._scroll_to_bottom\)', _SRC) is not None,
   "an arriving assistant bubble used to slam the view to the bottom and "
   "re-arm the stick, discarding the position just recorded")
ck("a snap that would be a no-op is forced through",
   re.search(r"if abs\(adj\.get_value\(\) - target\) < 0\.5:\s*\n"
             r"(?:\s*#.*\n)*\s*adj\.set_value\(0\.0\)", _SRC) is not None,
   "set_value() only emits when the number MOVES, so a snap to a value the "
   "adjustment already holds never reaches the viewport -- it paints the "
   "old offset while the scrollbar shows the new one")

print("\n== a reply in flight survives a chat switch ==")
ck("the streaming bubble is re-attached to its own chat",
   "_live = self.streaming_msg_widget" in _SRC
   and "self.streaming_chat_id == chat_id" in _SRC,
   "the clear loop unparents it and the rebuild skips it (its stored row is "
   "still empty), so the finished answer went to a widget with no parent")

print("\n== the row budget is spent on the conversation ==")
ck("_count_msg_rows counts bubbles, not feeds",
   re.search(r"def _count_msg_rows.*?isinstance\(c, MessageWidget\)",
             _SRC, re.S) is not None,
   "a 12-turn agentic chat rendered 13 bubbles + 7 feeds = 20 rows")
ck("an empty user message is not drawn as a blank bubble",
   'if not (m.content or "").strip():' in _SRC)
ck("the declared minimum width is not below what the content needs",
   re.search(r"self\.set_size_request\((\d+), \d+\)", _SRC)
   and int(re.search(r"self\.set_size_request\((\d+), \d+\)",
                     _SRC).group(1)) >= 480,
   "a floor under the content's own minimum clips the header rather than "
   "shrinking it")


# ══════════════════════════════════════════════════════════════════════
# 3. GATES THAT REPORTED THEMSELVES INTACT
# ══════════════════════════════════════════════════════════════════════
print("\n== clustered short options reach the payload ==")
# The interpreter/shell branches matched their inline-code flag as an EXACT
# token, so every POSIX cluster walked through: `-c` was recognised, `-Bc`
# was not, and `-Bc` is what actually runs the code. Each of these was
# confirmed to really execute in a real python3/bash before being fixed.
from basilisk_safety import is_catastrophic_command    # noqa: E402

_CLUSTERS = [
    'bash -cx "rm -rf /"',
    'bash -xc "rm -rf /"',
    'sh -ec "rm -rf /"',
    'sh -exc "rm -rf /"',
    'bash -lc "rm -rf /"',
    'python3 -Bc "import shutil; shutil.rmtree(\'/\')"',
    'python3 -uc "import shutil; shutil.rmtree(\'/\')"',
]
for _c in _CLUSTERS:
    ck(f"catastrophic through a cluster: {_c[:30]}",
       is_catastrophic_command(_c), "the floor did not see it")

_BENIGN_CLUSTERS = [
    'bash -c "echo hello"',
    'bash -lc "git status"',
    'python3 -c "print(1+1)"',
    'python3 -Bc "print(1+1)"',
    "sh -c 'ls -la'",
]
for _c in _BENIGN_CLUSTERS:
    ck(f"still allowed: {_c[:30]}", not is_catastrophic_command(_c))

print("\n== the scope gate, three ways it failed open ==")
_SCOPE = {"scope": ["acme.com", "10.0.0.0/24"], "exclusions": [],
          "allow_loopback": True}

_ATTACKS = [
    'python3 -Bc "import os; os.system(\'nmap 8.8.8.8\')"',
    'bash -cx "nmap -sS 8.8.8.8"',
    'sh -ec "nmap -sS 8.8.8.8"',
    'awk \'BEGIN{system("nmap -sS 8.8.8.8")}\'',
    'awk \'BEGIN{print | "nmap 8.8.8.8"}\'',
    "sed 's/x/y/e' file.txt",
    "sed '1e ls' file.txt",
    "nmap -sS acme.com dc01",
    "ping -c 1 dc01",
]
for _c in _ATTACKS:
    _v = S.check_command(_c, _SCOPE)
    ck(f"refused: {_c[:38]}", not _v.get("allowed"),
       str(_v.get("reason"))[:60])

# The counter-property corpus. An authorisation gate that refuses ordinary
# work is not a stricter gate, it is a broken one -- and the first draft of
# each of these fixes did exactly that.
_ORDINARY = [
    "sed 's/nmap/x/' notes.txt",
    "sed -n '1,20p' scan.txt",
    "sed -i.bak 's/foo/bar/g' report.md",
    "awk '{print $1}' scan.txt",
    'awk \'BEGIN{FS="|"}{print $2}\' data.psv',
    "awk -F'|' '{print $1}' data.psv",
    "awk 'NR>1{sum+=$3} END{print sum}' data.tsv",
    "nmap -sS -p- acme.com",
    "nmap -sV --script vuln 10.0.0.5",
    "nmap -A -T4 --script=http-title acme.com",
    "dig acme.com A",
    "amass enum -d acme.com",
    "wpscan --url https://acme.com --enumerate u",
    "hydra -l admin -P pw.txt 10.0.0.5 ssh",
    "which nmap",
    "grep -r nmap .",
]
for _c in _ORDINARY:
    _v = S.check_command(_c, _SCOPE)
    ck(f"allowed: {_c[:38]}", bool(_v.get("allowed")),
       str(_v.get("failure")) + " " + str(_v.get("reason"))[:50])


# ══════════════════════════════════════════════════════════════════════
# 4. FEATURES THAT SILENTLY DID NOTHING
# ══════════════════════════════════════════════════════════════════════
print("\n== settings that used to be decorative ==")

_CORE = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "basilisk_core.py"), encoding="utf-8").read()

ck("the heavy-effort rung is reachable",
   "elif effort == \"heavy\":" in _CORE
   and "elif effort == \"heavy\" and not _auton:" not in _CORE,
   "migrate_settings pops approval_mode, so `not _auton` was always False "
   "and hard_engagement_model was never consulted")

_vm = C.DEFAULT_SETTINGS.get("vision_model", "")
_sp = C.PROVIDERS_BY_KEY.get("siliconflow")
ck("the default vision model is one the provider actually carries",
   bool(_sp) and _sp.knows(_vm), _vm)
ck("a stale vision model id repairs itself",
   C._resolve_vision_model("Qwen/Qwen2.5-VL-7B-Instruct", _sp.base_url)
   != "Qwen/Qwen2.5-VL-7B-Instruct")
ck("a deliberate choice is left alone",
   C._resolve_vision_model("my/custom", "https://example.invalid/v1")
   == "my/custom")

ck("web_read's contract no longer claims a gate it does not have",
   "read directly while LEASHED" in C.tool_web_sources()[
       "any_other_public_host"],
   "the domain gate is in the GUI wrapper behind `if self._unleashed`; the "
   "docstring said it was unconditional")

print("\n== html reading is linear, not quadratic ==")
import time as _time                                  # noqa: E402
_times = []
for _n in (500, 1000, 2000, 4000):
    _h = "<script>x" * _n + "<p>tail</p>"
    _t0 = _time.perf_counter()
    C._wr_html_to_text(_h)
    _times.append(_time.perf_counter() - _t0)
ck("unclosed <script> openers do not scale quadratically",
   _times[-1] < max(_times[0], 1e-4) * 40,
   "n=500..4000 took " + ", ".join("%.4fs" % t for t in _times))
ck("the content still comes through",
   C._wr_html_to_text(
       '<p>hi <script>var x=1</script>there</p>').strip() == "hi there")

print("\n== a bare filename is a valid screenshot path ==")
_shot = re.search(r"def tool_screenshot\(.*?\n(?=def )", _CORE, re.S)
ck("tool_screenshot captured for inspection", _shot is not None)
ck("tool_screenshot does not makedirs('')",
   _shot is not None and "if parent:" in _shot.group(0)
   and "os.makedirs(os.path.dirname(path), exist_ok=True)"
   not in _shot.group(0),
   "os.makedirs('') raises FileNotFoundError, outside any try, so a bare "
   "filename -- the most natural argument -- was the one guaranteed to fail")
ck("a bare filename is anchored, not left to the process cwd",
   _shot is not None and "if not os.path.isabs(path):" in _shot.group(0))

print("\n== launch_app does not silently drop its arguments ==")
_APP = _SRC  # basilisk.py is the GUI; the tool lives in core
ck("gtk-launch is given the arguments",
   '_ro(["gtk-launch", desktop_id] + extra' in _CORE,
   "it reported ok:True after launching an empty browser")

print("\n== a namespaced tool name is readable ==")
_ns = C.parse_tool_calls(
    '<function=functions.web_read>{"url":"https://x"}</function>')
ck("functions.web_read resolves to web_read",
   len(_ns) == 1 and _ns[0].name == "web_read",
   str(_ns))

print("\n== askpass reaches every sudo the detector claims ==")
import basilisk_core as _bc                            # noqa: E402
ck("an env-prefixed sudo gets -A",
   _bc._inject_askpass("FOO=bar sudo apt update") == "FOO=bar sudo -A apt update",
   _bc._inject_askpass("FOO=bar sudo apt update"))
ck("...and the assignments stay before sudo",
   not _bc._inject_askpass("FOO=bar sudo id").startswith("sudo"))
ck("a plain sudo is unchanged in behaviour",
   _bc._inject_askpass("sudo apt update") == "sudo -A apt update")
ck("a chained sudo still gets it",
   _bc._inject_askpass("ls && sudo id") == "ls && sudo -A id")
ck("a word containing 'sudo' is untouched",
   _bc._inject_askpass("echo pseudo") == "echo pseudo")


# ══════════════════════════════════════════════════════════════════════
# 5. THE INVARIANTS THIS RELEASE MUST NOT HAVE MOVED
# ══════════════════════════════════════════════════════════════════════
print("\n== invariants ==")

import hashlib                                        # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The honesty guardrail is the one block of the persona that no refactor is
# allowed to soften. It was checked by hand this release and its digest is
# pinned here so the next one does not have to take anyone's word for it.
# (If this fails, read the block before changing the number: a diff here is
# either a deliberate edit or exactly the kind of quiet erosion it exists to
# prevent.)
_GR = C._extract_guardrail_blocks(
    open(os.path.join(_ROOT, "basilisk_persona.py"), encoding="utf-8").read())
ck("exactly one guardrail block", len(_GR) == 1, str(len(_GR)))
ck("the guardrail is unchanged",
   hashlib.sha256("\n".join(_GR).encode()).hexdigest()
   == "3c6d2daf3eb94b5fcc83f1e94bd566da1f80827779598cc037b8eba0e2583e90",
   hashlib.sha256("\n".join(_GR).encode()).hexdigest())
for _phrase in ('say "I don\'t know"',
                "correct yourself",
                "NEVER state a checkable fact as true without checking it",
                'label "unverified"'):
    ck(f"guardrail still says: {_phrase[:38]}", _phrase in _GR[0])

# The CSS is a bytes literal. One em-dash in a comment broke startup once;
# nothing about that is caught by the linters, so it is caught here.
_B = open(os.path.join(_ROOT, "basilisk.py"), "rb").read()
_css = re.search(rb'^CSS = b"""(.*?)"""', _B, re.S | re.M)
ck("the CSS block is found", _css is not None)
ck("the CSS is ASCII-only",
   _css is not None and not [b for b in _css.group(1) if b > 127],
   "a non-ASCII byte in a bytes literal is a SyntaxError at import")

# The point of this check is that the release LINE is intact and machine
# readable (test_packaging cross-checks it against pyproject and the README
# badge), not that the build is frozen at the version this suite was written
# for -- pinning that meant every later patch release started red.
ck("the version line is present and well formed",
   re.search(r'^VERSION = "1\.0\.0\.\d+"$', _B.decode("utf-8"), re.M)
   is not None)


# ══════════════════════════════════════════════════════════════════════
# 6. THE MODEL PROMISES AND NEVER DOES IT
# ══════════════════════════════════════════════════════════════════════
# Reported from a real session, three turns running on one question:
#
#   "hi can you give me some recent news from ireland"
#   -> "Looking up recent Irish news. <url> Let's read the top result."
#   "why did u stop?"
#   -> "You're right, I never actually fetched it. Let me do it properly."
#      ... and the same reply again.
#   "you didnt do it agasin."
#
# No tool ever ran. parse_tool_calls found nothing (the URL is prose, not a
# tag), looks_like_failed_tool_call found nothing (there is no protocol to
# see), and reply_is_bare_stall said DELIVERED -- because the preamble plus
# the URL cleared the 80-character substance bar. So no recovery, no nudge,
# and the turn ended "done" holding a promise.
print("\n== a printed URL is recovered into a real web_read call ==")

_PROMISES = [
    "Looking up recent Irish news from credible sources.\n\n"
    "https://html.duckduckgo.com/html/?q=ireland+news+august+2026\n\n"
    "Let's read the top result.",
    "You're right. Let me actually do it this time.\n\nFetching Irish news "
    "now:\n\nhttps://html.duckduckgo.com/html/?q=ireland+news\n\n"
    "Let me pull the top result and give you some actual headlines.",
    "First, get the search results page:\n\nhttps://duckduckgo.com/?q=x\n\n"
    "Now reading https://www.rte.ie/news/ from that page.",
]
for _t in _PROMISES:
    ck(f"url recovered: {_t[:34]!r}", bool(C.printed_url_target(_t)),
       "without this the turn ends having fetched nothing")

# THE COUNTER-PROPERTY, and it is the one that matters: a finished answer
# that CITES a source must never be re-fetched behind the operator's back.
for _label, _t in (
    ("markdown link with text",
     "The advisory is at [NVD CVE-2024-3094](https://nvd.nist.gov/vuln/"
     "detail/CVE-2024-3094) and it is patched in 5.6.1."),
    ("fenced example",
     'Call it like this:\n\n```\n<tool name="web_read">'
     '{"url": "https://example.com"}</tool>\n```'),
    ("fenced command",
     "Try:\n\n```bash\ncurl https://example.com/api\n```"),
    ("no url at all", "The answer is 42."),
):
    ck(f"not recovered: {_label}", not C.printed_url_target(_t),
       "a citation is not an intent to read")

print("\n== and a reply that only points at a URL is a stall ==")
ck("bare url + preamble is a stall",
   C.reply_is_bare_stall(_PROMISES[0]),
   "the URL used to count toward the substance bar, so no nudge fired")
for _label, _t in (
    ("answer that cites a source",
     "Ireland's budget passes on 12 September, the main change a EUR 2bn "
     "housing package. Source: https://www.rte.ie/news/budget"),
    ("answer with a markdown citation",
     "Per [the RTE report](https://www.rte.ie/news/) the vote is Tuesday "
     "and the margin was nine seats in the end."),
    ("plain answer", "The host is up and ports 22 and 80 are open."),
):
    ck(f"still delivered: {_label}", not C.reply_is_bare_stall(_t))

print("\n== the recovery is wired into the turn, behind the same gate ==")
ck("the printed-URL recovery exists",
   "printed_url_target(final)" in _SRC
   and 'name=\\"web_read\\"' in _SRC.replace('\\', '\\\\')
   or "printed_url_target(final)" in _SRC)
ck("it shares the shell recovery's two-tier gate",
   re.search(r"if _recover_fence and not self\._shell_block_command\(final\)",
             _SRC) is not None,
   "mission always; a regular turn only when the reply says it is ACTING")

print("\n== the contract tells the model this in one rule ==")
_PERSONA = open(os.path.join(_ROOT, "basilisk_persona.py"),
                encoding="utf-8").read()
import basilisk_persona as _P                          # noqa: E402
ck("the decision is stated up front",
   "ANSWER, or CALL A TOOL" in _P.TOOL_CONTRACT)
ck("...and the emit-the-tag rule with it",
   "MUST CARRY THE" in _P.TOOL_CONTRACT
   and "Describing a call is not making one" in _P.TOOL_CONTRACT)
ck("the narrate-then-stop instruction is gone",
   "in a SEPARATE reply" not in _P.TOOL_CONTRACT,
   "the search playbook used to tell it to read the result in a LATER "
   "reply, which is an invitation to end the turn with a promise")


print(f"\nv1.0.0.0 regressions: {_passed} passed, {_failed} failed")
sys.exit(1 if _failed else 0)
