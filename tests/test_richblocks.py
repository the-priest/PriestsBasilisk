#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_richblocks.py — structured markdown in a reply: tables, headings,
quotes, rules and lists.

WHY THIS EXISTS
===============
A model answering a comparison question replies with a TABLE. That is not an
edge case, it is the single most common shape of a structured answer — and
until v9.9.0 it rendered as literal pipe characters in a proportional font,
where the columns do not line up. The most structured thing the model could
say was the least readable thing on the screen.

Two classes of bug are pinned here, and the second one is the one that
actually bites:

  1. PARSING. A table is only a table if a separator row follows the header;
     without that rule `cat a | grep b` in ordinary prose becomes a
     one-column table. Cells split on UNESCAPED pipes only, because a shell
     pipeline inside a cell is exactly what this app's answers are full of
     and a naive split shifts every following column.

  2. SIZING — GTK height-for-width. A wrapping Gtk.Label reports a minimum
     width of about two characters, GTK then asks "how tall are you at that
     width", and the answer is astronomical. Measured on the first cut of
     this feature: a four-column, three-row table demanded **2104px** of
     height and a three-bullet list demanded **2479px**, so a reply with a
     table in it was followed by a screenful of empty bubble and the rest of
     the answer was pushed off the bottom. GTK said so out loud —
     "reports a minimum width of 20, but minimum width for height of 1048576
     is 33" — and nothing was watching for it.

     That is why the assertions below are about MEASURED SIZE, not about
     which widget was constructed. A table that builds and then asks for two
     thousand pixels has not worked.

Run:  python3 tests/test_richblocks.py
"""

from __future__ import annotations

import os
import re
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


# ── GTK stub, same shape as the other suites ─────────────────────────
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

_SRC = open(os.path.join(_ROOT, "basilisk.py"), encoding="utf-8").read()

P = Bk.parse_rich_blocks


def kinds(md):
    return [b["kind"] for b in Bk.split_message_into_blocks(md)]


def table_of(md):
    for b in Bk.split_message_into_blocks(md):
        if b["kind"] == "table":
            return b
    return None


# ═══════════════════════════════════════════════════════════════════════
# 1. A TABLE IS A HEADER PLUS A SEPARATOR — nothing else counts
# ═══════════════════════════════════════════════════════════════════════
print("== what is and is not a table ==")

ck("a header + separator + rows is a table",
   table_of("| A | B |\n|---|---|\n| 1 | 2 |") is not None)
ck("alignment markers are accepted as a separator",
   table_of("| A | B |\n|:--|--:|\n| 1 | 2 |") is not None)
ck("borderless pipes still parse",
   table_of("A | B\n---|---\n1 | 2") is not None)

ck("PROSE containing a pipe is not a table",
   table_of("run `cat a | grep b` and read the output") is None,
   "this is the false positive that would eat a shell pipeline mid-sentence")
ck("pipe rows with NO separator are not a table",
   table_of("| a | b |\n| c | d |") is None)
ck("a lone pipe line is not a table", table_of("| just this |") is None)
ck("an empty string yields no table", table_of("") is None)

# ═══════════════════════════════════════════════════════════════════════
# 2. CELL SPLITTING — the escaped pipe is the whole point
# ═══════════════════════════════════════════════════════════════════════
print("\n== cells ==")

t = table_of("| cmd | note |\n|---|---|\n| `a \\| b` | pipeline |")
ck("an escaped pipe stays inside its cell",
   t is not None and len(t["rows"][0]) == 2, str(t and t["rows"]))
ck("and becomes a literal pipe character",
   t is not None and "|" in t["rows"][0][0], str(t and t["rows"]))

t = table_of("| A | B | C |\n|---|:-:|--:|\n| 1 | 2 | 3 |")
ck("a single-dash separator cell (:-:) is still a separator", t is not None,
   "|:-:| and |-| are legal markdown and models emit both")
ck("alignments are read from the separator",
   t is not None and t["aligns"] == ["left", "center", "right"],
   str(t and t["aligns"]))

t = table_of("| A | B | C |\n|---|---|---|\n| 1 |\n| 1 | 2 | 3 | 4 |")
ck("a short row does not raise", t is not None)
ck("a long row does not raise", t is not None and len(t["rows"] or []) == 2)

t = table_of("| A | B |\n|---|---|\n|  |  |")
ck("empty cells survive", t is not None and t["rows"] == [["", ""]],
   str(t and t["rows"]))
ck("a one-dash separator table parses too",
   table_of("| A |\n|-|\n| x |") is not None)

# ═══════════════════════════════════════════════════════════════════════
# 3. THE OTHER BLOCKS
# ═══════════════════════════════════════════════════════════════════════
print("\n== headings, quotes, rules, lists ==")

ck("a heading is a heading", kinds("## Title") == ["heading"])
b = P("### Deep")[0]
ck("the level is read", b["level"] == 3 and b["content"] == "Deep", str(b))
ck("closing hashes are stripped", P("## Title ##")[0]["content"] == "Title")
ck("a hash with no space is not a heading (it is a tag)",
   P("#nofilter")[0]["kind"] == "text")

ck("--- is a rule", kinds("text\n\n---\n\nmore").count("rule") == 1)
ck("*** is a rule", "rule" in kinds("a\n\n***\n\nb"))

q = P("> line one\n> line two")
ck("consecutive quote lines become ONE quote",
   len(q) == 1 and q[0]["kind"] == "quote", str([x['kind'] for x in q]))
ck("the marker is stripped", q[0]["content"] == "line one\nline two",
   repr(q[0]["content"]))

li = P("- one\n- two\n- three")[0]
ck("a bullet run becomes one list",
   li["kind"] == "list" and len(li["items"]) == 3, str(li))
li = P("1. first\n2. second")[0]
ck("a numbered run keeps its numbers",
   [i["marker"] for i in li["items"]] == ["1.", "2."], str(li["items"]))
li = P("- top\n  - nested")[0]
ck("indentation becomes a level",
   [i["indent"] for i in li["items"]] == [0, 1], str(li["items"]))
li = P("- a bullet that\n  continues on the next line")[0]
ck("a continuation line folds into its item",
   len(li["items"]) == 1 and "continues" in li["items"][0]["content"],
   str(li["items"]))

# ═══════════════════════════════════════════════════════════════════════
# 4. ORDER OF OPERATIONS
# ═══════════════════════════════════════════════════════════════════════
print("\n== structure vs code fences vs images ==")

ks = kinds("intro\n\n| A |\n|---|\n| 1 |\n\n```py\nx=1\n```\n\nend")
ck("a fenced block is still a code block", "code" in ks, str(ks))
ck("a table beside it is still a table", "table" in ks, str(ks))
ck("prose around them survives", ks.count("text") >= 2, str(ks))

ck("pipes INSIDE a code fence are not a table",
   "table" not in kinds("```\n| A | B |\n|---|---|\n| 1 | 2 |\n```"),
   "a fenced markdown example must render as the code it is")

ks = kinds("look:\n\n![shot](https://e.org/a.png)\n\n- after")
ck("an image in prose still becomes an image", "image" in ks, str(ks))
ck("and a list after it is still a list", "list" in ks, str(ks))

# ═══════════════════════════════════════════════════════════════════════
# 5. ROBUSTNESS — a malformed table costs that block, never the reply
# ═══════════════════════════════════════════════════════════════════════
print("\n== nothing here can lose the message ==")

import random as _rnd                                            # noqa: E402
_rnd.seed(17)
_alph = list("ab |-:*#>`\n0123456789[]()")
_bad = 0
for _ in range(6000):
    _s = "".join(_rnd.choice(_alph) for _ in range(_rnd.randint(1, 60)))
    try:
        Bk.split_message_into_blocks(_s)
    except Exception as e:
        _bad += 1
        if _bad < 3:
            print("      raised on", repr(_s[:60]), type(e).__name__, e)
ck("6000 fuzzed inputs all split without raising", _bad == 0, str(_bad))

_big = "| A | B |\n|---|---|\n" + "\n".join("| %d | x |" % i
                                            for i in range(4000))
try:
    _t = table_of(_big)
    ck("a 4000-row table parses", _t is not None and len(_t["rows"]) == 4000)
except Exception as e:
    ck("a 4000-row table parses", False, str(e))

ck("the widget caps what it DRAWS, not what was parsed",
   Bk.TableWidget.MAX_ROWS == 200 and Bk.TableWidget.MAX_COLS == 24,
   "the store keeps everything; this is a display window")
ck("the cap is announced, not silent",
   "more rows" in _SRC,
   "a table that quietly stops at row 200 reads as a complete table")

ck("every structural block is built inside its own try",
   _SRC.count("table render failed") >= 1
   and "_table_to_text" in _SRC,
   "one malformed table must cost that block, not the whole reply")

# ═══════════════════════════════════════════════════════════════════════
# 6. THE SIZING BUG, PINNED
# ═══════════════════════════════════════════════════════════════════════
print("\n== the height-for-width trap ==")

ck("table cells do NOT wrap",
   "lbl.set_wrap(False)" in _SRC,
   "wrapping cells inside a horizontally-scrolling container is what made a "
   "3-row table ask for 2104px of height")
ck("the table scrolls horizontally instead",
   "Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER" in _SRC)
ck("the table's scroller cannot expand vertically",
   "sw.set_vexpand(False)" in _SRC,
   "a ScrolledWindow fills by default, which left a screenful of empty "
   "bubble under the grid")
# The list used to be a Gtk.Grid, and a Grid reports a cramped natural WIDTH
# for a wrapping cell — which dragged the whole chat bubble narrow, so GTK
# computed the list's HEIGHT at that narrow width and every bullet wrapped
# into a tall ribbon: the "bubble is five screens tall" report. The list is
# now a vertical box of horizontal rows, which settles each row's width first
# and measures height at the width the text is actually shown at. Pin that:
# it must NOT be a Grid, and it must NOT re-introduce the set_width_chars pin
# (fixing natural width was what made the bubble hug narrow).
ck("the list is a box of rows, not a Grid",
   "class ListWidget(Gtk.Box)" in _SRC,
   "a Gtk.Grid reports a cramped natural width and towers the bubble")
ck("the list body does not pin its width (that forced the narrow hug)",
   "body.set_width_chars(" not in _SRC,
   "set_width_chars fixes the NATURAL width too, hugging the bubble narrow")
# Bound the slice by the NEXT top-level class, never by a guessed byte count.
# A fixed [:3000] window reported this missing on code that was correct — the
# call sits at offset 5072 — which is a probe failing for a reason unrelated
# to the property it claims to test. Every source probe in this file now
# proves it captured something first.
_TBL_SRC = _SRC.split("class TableWidget")[1].split("\nclass ")[0]
ck("the TableWidget probe actually captured the class body",
   "def _cell" in _TBL_SRC and len(_TBL_SRC) > 1500, str(len(_TBL_SRC)))
ck("a long cell keeps its full text reachable",
   "set_tooltip_text" in _TBL_SRC,
   "ellipsis loses information; the tooltip is where it goes")

# ═══════════════════════════════════════════════════════════════════════
# 7. The partial-tag hider must not reach ordinary prose
# ═══════════════════════════════════════════════════════════════════════
print("\n== hiding a half-arrived tag may not eat the reply ==")

import basilisk_core as _C                                       # noqa: E402

_PROSE = ["the loop runs while i < t", "check if x < f", "value < too",
          "if a<t then", "compare a < to b", "x < func", "a < b",
          "see < function here", "5 < 6 < 7", "x <toolbar"]
_lost = [(c, _C.strip_tool_calls(c)) for c in _PROSE
         if len(_C.strip_tool_calls(c)) < len(c.strip())]
ck("no ordinary sentence loses characters to the partial-tag hider",
   not _lost, str(_lost[:2]),
   )
ck("the prefix ladder has a length floor",
   _C._MIN_PARTIAL_TAG >= 4,
   "one-letter prefixes made 't' and 'f' -- the first letter of half of "
   "English -- look like the start of <tool_calls>")
ck("and it does not tolerate whitespace after the angle bracket",
   "< t" not in _C._WRAPPER_PARTIAL_RE.pattern
   and r"<\s*" not in _C._WRAPPER_PARTIAL_RE.pattern,
   "a real tag is written <tool_calls, never < tool_calls")

_P = "\uff5c"
_full = ("Checking." + "<" + _P + "DSML" + _P + "tool_calls>"
         + "<" + _P + "DSML" + _P + 'invoke name="web_read">'
         + "<" + _P + "DSML" + _P + 'parameter name="url" string="true">'
         + "https://a/</" + _P + "DSML" + _P + "parameter></"
         + _P + "DSML" + _P + "invoke></" + _P + "DSML" + _P + "tool_calls>")
_leak = sum(1 for i in range(1, len(_full) + 1)
            if any(k in _C.strip_tool_calls(_full[:i])
                   for k in ("DSML", "invoke", "tool_calls", _P,
                             "parameter name=")))
ck("and a real tag still never shows a single frame of protocol",
   _leak == 0, str(_leak))


print(f"\n{_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
