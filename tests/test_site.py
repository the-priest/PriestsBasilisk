#!/usr/bin/env python3
"""
test_site.py — index.html is a public claim about this code. Pin it.

WHY THIS EXISTS
===============
README.md has had `tests/test_readme.py` guarding its numbers and its
load-bearing facts for a long time. index.html — a 110 KB page making the same
claims to a wider audience, and feeding structured data to search engines and
answer engines — had nothing. Only that it existed and referenced its images.

The cost showed up during the v1.1.0.0 docs pass, twice:

  * the page still said "4,170 assertions across 61 suites" after the repo
    reached 65, in four separate places;
  * a rewrite of the repo-work section was applied by a script that raised
    before its write, so the edit was reported as done and silently was not.
    Nothing caught it. It was found by looking at a screenshot.

A page nobody checks drifts from the code it describes, and the drift is
invisible because prose always looks fine. So: every NUMBER on the page is
computed from the repo here, the structured data must parse, every in-page
anchor must resolve, and the positioning claims must agree with README.md
rather than contradicting it.

Run:  python3 tests/test_site.py
"""

from __future__ import annotations

import glob
import html.parser
import io
import json
import os
import re
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


def rel(*a):
    return os.path.join(_ROOT, *a)


SITE = io.open(rel("index.html"), encoding="utf-8").read()
README = io.open(rel("README.md"), encoding="utf-8").read()
BASILISK = io.open(rel("basilisk.py"), encoding="utf-8").read()


# ── 1. IT IS WELL-FORMED, AND ITS STRUCTURED DATA PARSES ─────────────
print("== the page is well-formed ==")


class _P(html.parser.HTMLParser):
    def error(self, msg):
        raise AssertionError(msg)


try:
    _P().feed(SITE)
    ck("index.html parses", True)
except Exception as e:
    ck("index.html parses", False, str(e))

_ld = re.findall(r'<script type="application/ld\+json">(.*?)</script>',
                 SITE, re.S)
ck("carries JSON-LD structured data", len(_ld) >= 1, f"{len(_ld)} blocks")
for i, blk in enumerate(_ld):
    try:
        json.loads(blk)
        ck(f"JSON-LD block {i + 1} is valid JSON", True)
    except Exception as e:
        ck(f"JSON-LD block {i + 1} is valid JSON", False, str(e)[:120])

# An anchor that goes nowhere is a broken nav on a one-page site.
_ids = set(re.findall(r'id="([^"]+)"', SITE))
_hrefs = {h for h in re.findall(r'href="#([^"]*)"', SITE) if h}
_broken = sorted(h for h in _hrefs if h not in _ids)
ck("every in-page anchor resolves", not _broken, str(_broken))
ck("the nav is not empty", len(_hrefs) >= 5, f"{len(_hrefs)} anchors")


# ── 2. EVERY NUMBER MATCHES THE REPO ─────────────────────────────────
print("\n== stated numbers match the code ==")

_ver = re.search(r'VERSION = "([^"]+)"', BASILISK).group(1)
ck(f"the site states the shipped version ({_ver})",
   f"v{_ver}" in SITE, "the hero eyebrow carries it")

_suites = len(glob.glob(rel("tests", "test_*.py")))
_claims = re.findall(r"assertions?\s+across\s+(\d+)\s+", SITE)
_claims += re.findall(r"Assertions\s*·\s*(\d+)\s+suites", SITE)
ck("the site states a suite count", bool(_claims))
for c in set(_claims):
    ck(f"suite count {c} matches the repo ({_suites})", int(c) == _suites)

# The assertion total must agree with README's, which test_readme pins to the
# badge. Two pages quoting different totals is the drift this file exists for.
_rm = re.search(r"([\d,]+)\s+assertions across", README)
ck("README states an assertion total", _rm is not None)
if _rm:
    _site_totals = set(re.findall(r"([\d,]+)\s+(?:stdlib-only\s+)?assertions",
                                  SITE))
    _site_totals |= set(re.findall(r'<div class="n">([\d,]+)</div>\s*'
                                   r'<div class="l">Assertions', SITE))
    ck("the site's assertion total agrees with the README's",
       _rm.group(1) in _site_totals or not _site_totals,
       f"README={_rm.group(1)} site={sorted(_site_totals)}")

# Tool count: the site and README both quote it; core is the source of truth.
_tools = len(re.findall(r"^def tool_[a-z0-9_]+\(",
                        io.open(rel("basilisk_core.py"), encoding="utf-8").read(),
                        re.M))
for _c in set(re.findall(r'<div class="n">(\d+)</div>\s*<div class="l">Tools',
                         SITE)):
    ck(f"the site's tool count {_c} matches basilisk_core ({_tools})",
       int(_c) == _tools)


# ── 3. POSITIONING AGREES WITH THE README ────────────────────────────
# Not a style opinion: an answer engine reads the site's structured data and
# the README's opening, and if they disagree it will confidently describe the
# wrong product. These two files have to tell the same story.
print("\n== the site and the README describe the same product ==")

ck("the page presents the assistant, not only the pentest agent",
   re.search(r"(coding assistant|desktop AI assistant|general and coding)",
             SITE, re.I) is not None)
ck("…in the <title>",
   re.search(r"<title>[^<]*(assistant|coding)[^<]*</title>", SITE, re.I)
   is not None,
   re.search(r"<title>(.*?)</title>", SITE, re.S).group(1)[:90])
ck("…and in the meta description",
   re.search(r'<meta name="description" content="[^"]*'
             r'(coding assistant|AI assistant)', SITE, re.I) is not None)

ck("the armed mode is still described honestly",
   "Unleash" in SITE and "authoriz" in SITE.lower())
ck("the page says the offensive suite is not loaded until armed",
   re.search(r"(refused at the loader|not loaded until|until you arm it)",
             SITE, re.I) is not None)

# Repo work takes a folder OR a zip. The site said zip-only for months after
# folders shipped, which is a capability the reader would not know they had.
ck("repo work is not described as zip-only",
   re.search(r"folder\s+or\s+a\s*(<[^>]+>)?\s*\.?zip", SITE, re.I) is not None,
   "index.html should say folder or zip, as README does")
ck("README agrees",
   re.search(r"folder\s+or\s+a\s+\*\*?zip", README, re.I) is not None
   or "**folder or a zip**" in README)

# The site must not claim an install path that is no longer offered.
ck("the site does not advertise the stale PyPI release",
   "pip install priestsbasilisk" not in SITE)
ck("…nor does the README",
   "pip install priestsbasilisk" not in README)
ck("the site documents the native packages instead",
   "pacman -U priestsbasilisk" in SITE and "apt install ./priestsbasilisk" in SITE)


# ── 4. THE DANGER NOTICE SURVIVES ANY REWRITE ────────────────────────
# This is the one block on the page that is not marketing. A rewrite that
# quietly softens it is the worst edit anyone could make here.
print("\n== the safety notice is intact ==")
for phrase, why in [
    ("explicit written authorization", "the legal line for armed use"),
    ("run anyway", "the page must state there is NO override"),
    ("install.sh", "readers are told to read the installer"),
]:
    ck(f"keeps: {phrase!r}", phrase in SITE, why)
ck("states the irreversible class is blocked below the model",
   re.search(r"irreversible[^.]{0,120}(hard-blocked|blocked)", SITE, re.I)
   is not None)


print(f"\nsite: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
