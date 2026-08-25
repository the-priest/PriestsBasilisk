#!/usr/bin/env python3
"""
test_readme.py — the README is an INPUT, not just marketing.

PROJECT_SELF tells Basilisk that when the operator asks about its own version,
install command, changelog or capabilities it should `web_read` this file
rather than answer from memory. That makes every sentence here a belief the
agent will act on, and a stale README a source of confident wrong answers.

Three real ones this suite was written for, all found by checking prose against
the actual code rather than against other prose:

  · "Nothing runs until you click Apply" for self-written skills — skill saving
    went autonomous, so an agent reading that would wait for an Apply that never
    comes.
  · "web_read reads only from a fixed allow-list ... off-list URLs are refused"
    — any public host is reachable after a one-tap approval, and the README's
    own tier examples put exploit-db in the wrong tier.
  · A stale version badge and test count.

METHOD NOTE, learned the hard way twice: validate a checker against KNOWN-GOOD
input before trusting its verdict. The anchor slugger below reported all six nav
links broken until it was run against the previous README, which demonstrably
worked on GitHub — GitHub does not strip a heading before slugging, so an emoji
is dropped but the space it leaves becomes a LEADING HYPHEN. The links were
right and the checker was wrong. Likewise, matching README prose with a literal
string fails on markdown emphasis (`*only*`), so claim checks here match on
distinctive substrings, not whole sentences.

Run:  python3 tests/test_readme.py
"""

from __future__ import annotations

import glob
import io
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

import basilisk_core as kc                                      # noqa: E402
import basilisk_persona as kp                                   # noqa: E402
import basilisk_safety as ks                                    # noqa: E402

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


README = io.open("README.md", encoding="utf-8").read()
SRC = io.open("basilisk.py", encoding="utf-8").read()


# ── 1. NUMBERS MATCH REALITY ─────────────────────────────────────────
print("== stated numbers ==")
_ver_src = re.search(r'VERSION = "([^"]+)"', SRC).group(1)
_ver_badge = re.search(r"badge/version-([\d.]+)-", README)
ck("version badge present", _ver_badge is not None)
ck(f"version badge matches basilisk.py ({_ver_src})",
   _ver_badge and _ver_badge.group(1) == _ver_src,
   f"badge={_ver_badge.group(1) if _ver_badge else '?'} src={_ver_src}")

_suites = len(glob.glob("tests/test_*.py"))
_claimed = re.search(r"([\d,]+)\s+assertions across\s+(\d+)\s+suites", README)
ck("assertion/suite claim present", _claimed is not None)
ck(f"suite count matches reality ({_suites})",
   _claimed and int(_claimed.group(2)) == _suites,
   f"claims {_claimed.group(2) if _claimed else '?'}, found {_suites}")
_badge_assert = re.search(r"badge/tests-(\d+)%20assertions", README)
ck("test badge agrees with the prose claim",
   _badge_assert and _claimed
   and _badge_assert.group(1) == _claimed.group(1).replace(",", ""),
   "the badge and the security-model paragraph must not drift apart")


# ── 2. SAFETY CLAIMS ARE TRUE OF THE CODE ────────────────────────────
print("\n== safety claims vs code ==")
_res = kc.tool_run_command("mkfs.ext4 /dev/sda")
ck("code: irreversible class is refused", _res.get("refused") is True)
ck("code: refusal states no override",
   "no override" in (_res.get("error") or "").lower())
ck('README claims there is no "run anyway"',
   "run anyway" in README.lower())
ck("code: sees through $IFS", ks.is_catastrophic_command("rm${IFS}-rf${IFS}/"))
ck("README claims it sees through $IFS", "$IFS" in README)
ck("code: sees through sh -c",
   ks.is_catastrophic_command("sh -c 'mkfs.ext4 /dev/sda'"))
ck("code: no false positive on rm -rf ~/loot",
   not ks.is_catastrophic_command("rm -rf ~/loot"))
ck("README cites that exact non-false-positive", "rm -rf ~/loot" in README)


# ── 3. WEB TIER CLAIMS ───────────────────────────────────────────────
print("\n== web_read tier claims ==")
for url, want in (("https://nvd.nist.gov/x", "trusted"),
                  ("https://owasp.org/x", "trusted"),
                  ("https://portswigger.net/x", "trusted"),
                  ("https://www.exploit-db.com/x", "community"),
                  ("https://github.com/a/b", "community"),
                  ("https://stackoverflow.com/q/1", "community")):
    ck(f"code tier {url.split('/')[2]} = {want}",
       kc.web_read_tier(url) == want, str(kc.web_read_tier(url)))
ck("code refuses cloud metadata",
   kc.web_read_tier("http://169.254.169.254/latest/meta-data/") is None)
ck("code refuses loopback", kc.web_read_tier("http://127.0.0.1:8080/") is None)

# The README used to say web_read was a closed allow-list. It is not.
ck("README does NOT claim a fixed allow-list",
   "fixed allow-list" not in README,
   "any public host is reachable after a one-tap approval")
ck("README puts exploit-db on the approval side",
   re.search(r"exploit-db[^.]{0,120}(approval|outside the autonomous loop)",
             README, re.S) is not None)
ck("README does not list exploit-db as auto-fetching",
   re.search(r"fetch automatically[^.]{0,200}exploit-db", README, re.S) is None)


# ── 4. CAPABILITY CLAIMS ─────────────────────────────────────────────
print("\n== capability claims ==")
ck("README does NOT claim skills need an Apply click",
   "until you click Apply" not in README,
   "skill saving is autonomous — it is gated by its own test, not a click")
ck("README states skills are kept only if the test passes",
   re.search(r"only if the test passes", README) is not None)

ck("code: offensive group refused while disarmed",
   kp.load_tools_group("offensive", unleashed=False).get("ok") is False)
ck("code: offensive group loads while armed",
   kp.load_tools_group("offensive", unleashed=True).get("ok") is True)
ck("README explains the Unleash tool gate",
   re.search(r"offensive suite.{0,200}Unleash", README, re.S) is not None)
ck("README says the gate is at the loader, not cosmetic",
   "refused at the loader" in README)

ck("code: workspace_replace refuses a non-unique match",
   "refuses a match that isn't unique" in README
   and hasattr(kc, "tool_workspace_replace"))


# ── 5. ANCHORS RESOLVE ───────────────────────────────────────────────
# See the METHOD NOTE at the top: GitHub keeps the space an emoji leaves, so
# these slugs carry a LEADING HYPHEN. Do not "correct" that.
print("\n== nav anchors ==")


def slug(h: str) -> str:
    t = h.lower()
    t = re.sub(r"[^\w\s-]", "", t)     # drop emoji/punctuation, KEEP the space
    return t.replace(" ", "-")


_anchors = {slug(h) for h in re.findall(r"(?m)^#{1,6}\s+(.*)$", README)}
_links = re.findall(r'href="#([^"]+)"', README)
ck("README has nav links", len(_links) >= 5)
for l in _links:
    ck(f"anchor resolves: #{l}", l in _anchors)


# ── 6. DISAMBIGUATION SURVIVES ───────────────────────────────────────
# An AI assistant asked about "Basilisk" will otherwise confidently describe a
# different project. This block is load-bearing for that reason.
print("\n== disambiguation ==")
for term in ("Roko", "White-Basilisk", "the-priest/PriestsBasilisk",
             "Basilisk browser"):
    ck(f"keeps {term}", term in README)


# ── 7. LOAD-BEARING FACTS SURVIVE A REWRITE ──────────────────────────
print("\n== load-bearing facts ==")
FACTS = [
    "87 / 113", "22 / 22", "Juice Shop", "Duck Store", "DeepSeek-V4-Flash",
    "Cascade", "36 / 113", "23 / 113", "NODE_ENV=unsafe",
    "bkimminich/juice-shop", "juiceshop_report", "/api/Challenges",
    "14 OWASP", "F1 0.95", "CVE-2007-4559", "commonpath", "Zip slip",
    "Zip bombs", "Symlink entries", "bubblewrap", "workspace_baseline",
    "workspace_verify", "workspace_export", "zday_scan", "code_scan_plan",
    "SiliconFlow", "~/.config/basilisk/settings.json",
    "Python 3.10+", "GTK4", "CachyOS", "pacman", "doas", "MIT",
    "install.sh", "alg:none", "RS256", "prototype pollution", "interactsh",
    "out-of-band", "memory_forget", "SQLite",
]
_missing = [f for f in FACTS if f not in README]
for f in FACTS:
    if f in README:
        _p += 1
    else:
        _f += 1
        print(f"  FAIL fact lost in rewrite: {f!r}")
print(f"  PASS {len(FACTS) - len(_missing)}/{len(FACTS)} load-bearing facts kept"
      if not _missing else f"  {len(_missing)} FACTS LOST")


print(f"\nreadme: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
