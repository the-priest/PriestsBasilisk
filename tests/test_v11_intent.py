#!/usr/bin/env python3
"""test_v11_intent.py — adversarial sweep of leashed_intent + forced_search_url.

Written as a probe during the v1.1.0.0 debug pass and kept, because it found
thirteen real defects on its first run — including a structural one: several
words (`build`, `run`, `test`, `patch`, `import`, `commit`, `merge`, `diff`)
are legitimately BOTH weak verbs and code nouns, so the leading verb satisfied
its own object requirement and "build me a mental model of tcp" classified as
a repo job.

Wrong in the "task" direction puts workspace/iterate instructions on a plain
question; wrong in the "question" direction and the coding assistant goes back
to describing fixes instead of landing them. Both are hunted here.
"""
import itertools
import random
import os
import sys
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

# GTK stub so basilisk.py imports
class _Meta(type):
    def __getattr__(cls, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return _Obj
class _Obj(metaclass=_Meta):
    def __init__(self, *a, **k): pass
    def __call__(self, *a, **k): return _Obj()
    def __getattr__(self, n): return _Obj()
class _Mod(types.ModuleType):
    def __getattr__(self, n):
        if n.startswith("__"): raise AttributeError(n)
        return _Obj
    def require_version(self, *a, **k): pass
for _m in ("gi", "gi.repository", "gi.repository.Gtk", "gi.repository.Adw",
           "gi.repository.GLib", "gi.repository.Gio", "gi.repository.Gdk",
           "gi.repository.GdkPixbuf", "gi.repository.Pango",
           "gi.repository.GObject", "gi.repository.GtkSource",
           "gi.repository.Vte", "gi.repository.Soup"):
    sys.modules[_m] = _Mod(_m)
sys.modules["gi"].require_version = lambda *a, **k: None

import basilisk_core as C
import basilisk as Bk

I = C.leashed_intent
F = Bk.forced_search_url

bad = []


def want(text, expect, why=""):
    got = I(text)
    if got != expect:
        bad.append(f"intent  {expect:8s} != {got:8s}  {text!r}  {why}")


# ── 1. Real coding requests, phrased the way a tired person phrases them ──
TASKS = [
    "fix it",
    "fix this shit",
    "fix the bug",
    "yo fix the parser",
    "pls fix my repo",
    "can u fix the tests",
    "could you please refactor this module",
    "i want you to rewrite the auth handler",
    "i need you to add logging to every tool",
    "go ahead and clean up the imports",
    "lets refactor basilisk_core.py",
    "let's split this file in two",
    "add a --dry-run flag",
    "add tests for the new gate",
    "remove the dead code",
    "delete src/old.py",
    "rename the function to parse_reply",
    "move the classifier into core",
    "extract the retry logic into a helper",
    "migrate to httpx",
    "port this to python 3.12",
    "backport the fix to the 1.0 branch",
    "implement pagination",
    "write a script that dedupes a csv",
    "write me a python module for rate limiting",
    "make a cli for this",
    "build a parser for this log format",
    "generate the type stubs",
    "install the missing deps and run the tests",
    "run the test suite",
    "run the tests and fix what fails",
    "debug this traceback",
    "patch the off by one",
    "unfuck the makefile",
    "optimise the search function",
    "harden the input validation",
    "wire the new tool into the dispatcher",
    "hook up the logger",
    "convert the config to toml",
    "upgrade the deps",
    "finish the refactor",
    "the tests are failing, sort it out",
    "build is broken, fix it",
    "my repo wont build",
    "the parser crashes on empty input",
    "this module throws on import",
    "src/api.py is broken",
    "tests are red",
    "sort it out",
    "just make it work",
    "get the tests passing",
    "clean it up",
    "handle it",
    "take a look at the repo and clean it up",
    "ok now fix the auth bug in my repo",
    "and then add a flag for it",
    "also rewrite the readme generator",
    "fix calc.py",
    "fix ./src/main.py",
    "there's a bug in workspace.py, fix it",
]
for t in TASKS:
    want(t, "task")

# ── 2. Questions that MUST stay questions ──
QUESTIONS = [
    "what is a race condition",
    "what's the difference between a list and a tuple",
    "why does python have a gil",
    "how do i fix a merge conflict",
    "how do you write a decorator",
    "how would i add a flag to argparse",
    "when should i use a dataclass",
    "where does pip install packages",
    "who maintains requests",
    "which is faster, a set or a dict",
    "is my regex wrong",
    "are these tests any good",
    "does this function leak memory",
    "do i need a lock here",
    "did the last release break anything",
    "should i refactor this",
    "would it be better to use httpx",
    "could this be a race condition",
    "can i use asyncio here",
    "explain the promise gate",
    "explain how you fixed the parser",
    "describe the architecture",
    "summarise what changed in the last release",
    "compare pytest and unittest",
    "tell me about the workspace tools",
    "show me how the dispatcher works",
    "walk me through the retry logic",
    "run me through what happens on a tool call",
    "take me through the diff",
    "thoughts on rust",
    "any idea why this is slow",
    "what does workspace_verify do",
    "whats the latest nmap version",
    "who won the match",
    "hows the weather",
    "hi",
    "hello there",
    "thanks man",
    "nice one",
    "ok",
    "yeah",
    "cool",
    # prose/creative work must NOT become a repo job
    "write a poem about the sea",
    "write a short story about a lighthouse",
    "write me a birthday message for my mum",
    "make a case for using postgres",
    "make an argument against microservices",
    "create a metaphor for recursion",
    "build me a mental model of tcp",
    "add some colour to this paragraph",
    "improve this sentence",
    "clean up my email draft",
]
for t in QUESTIONS:
    want(t, "question")

# ── 3. Totality: nothing may raise, for any input at all ──
JUNK = [None, 0, 1, -1, 1.5, True, False, b"bytes", [], {}, set(), object(),
        "", " ", "\n", "\t\t", "?" * 500, "\x00\x01\x02",
        "😀" * 50, "a" * 100000, "fix " * 20000,
        "\\" * 500, "((((((((((", "]]]]]]", "%s%s%s", "{}{}{}",
        "fix\x00the\x00repo", "FIX THE REPO", "FiX tHe RePo",
        "  \n\n  fix the repo  \n\n  ",
        "fix\tthe\trepo", "fix the repo"]
for j in JUNK:
    try:
        r = I(j)
        if r not in ("question", "task"):
            bad.append(f"intent  returned {r!r} for {type(j).__name__}")
    except Exception as e:
        bad.append(f"intent  RAISED {type(e).__name__} on {type(j).__name__}: {e}")

# case-insensitivity must hold
for t in ("FIX THE REPO", "FiX tHe RePo", "  fix the repo  ",
          "fix\tthe repo"):
    want(t, "task", "(case/space normalisation)")

# ── 4. Catastrophic backtracking / pathological inputs ──
import time
SLOW = [
    "fix " * 5000,
    ("and " * 2000) + "fix the repo",
    ("what " * 3000),
    "a," * 20000,
    ("the tests are failing, " * 2000) + "sort it out",
    "x" * 200000,
]
for s in SLOW:
    t0 = time.time()
    try:
        I(s)
    except Exception as e:
        bad.append(f"intent  RAISED on pathological input: {type(e).__name__}")
    dt = time.time() - t0
    if dt > 0.5:
        bad.append(f"intent  SLOW: {dt:.2f}s on a {len(s)}-char input")

for s in SLOW:
    t0 = time.time()
    try:
        F(s, set(), False)
    except Exception as e:
        bad.append(f"forced  RAISED: {type(e).__name__}")
    dt = time.time() - t0
    if dt > 0.5:
        bad.append(f"forced  SLOW: {dt:.2f}s on a {len(s)}-char input")

# ── 5. forced_search_url: the URL must be safe and well-formed ──
import urllib.parse
EVIL = [
    'news about "><script>alert(1)</script>',
    "what's the latest on x' OR 1=1--",
    "latest news\r\nHost: evil.com",
    "latest news\n\nGET /admin HTTP/1.1",
    "latest news #fragment?a=b&c=d",
    "latest news " + "‮" * 10,
    "current events " + "\x00",
    "top stories " + "a" * 5000,
]
for q in EVIL:
    u = F(q, set(), False)
    if u is None:
        continue
    if not u.startswith("https://html.duckduckgo.com/html/?q="):
        bad.append(f"forced  wrong prefix: {u[:80]!r}")
    tail = u[len("https://html.duckduckgo.com/html/?q="):]
    for ch in ("\r", "\n", " ", "#", "&", "?", '"', "<", ">", "\x00"):
        if ch in tail:
            bad.append(f"forced  UNESCAPED {ch!r} in query: {u[:120]!r}")
    if len(u) > 2000:
        bad.append(f"forced  URL too long: {len(u)}")

# ── 6. the two functions must agree with each other ──
# A turn classified as a coding TASK must never be hijacked into a web search:
# that is the false positive that would shove a results page into a repo fix.
for t in TASKS:
    if I(t) == "task" and F(t, set(), False) is not None:
        bad.append(f"CONFLICT  a coding task also forces a web fetch: {t!r}")

print("\n".join(bad) if bad else "no findings")
print(f"\nv11_intent: {len(bad)} finding(s)")
sys.exit(1 if bad else 0)
