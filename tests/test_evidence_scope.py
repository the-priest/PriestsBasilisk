#!/usr/bin/env python3
"""
test_evidence_scope.py — the evidence ledger must detect tampering, and the
scope gate must judge a RANGE as a range.

FOUND BY AUDIT, ALL REPRODUCED BEFORE FIXING
============================================

LEDGER (basilisk_ledger.py) — this is what "no proof, no finding" rests on,
and every benchmark number in the README was produced with it.

  1. verify() was BLIND whenever a recorded hash was None. A step whose stdout
     was empty records `stdout_sha256: None`, and the check read
         e.get("stdout_sha256") in (None, _sha256(so))
     which is unconditionally true when the recorded value is None. Forged
     output could be pasted into that artifact and verify() still said intact.

  2. verify() raised a FALSE "hash mismatch" on untouched evidence. It
     re-derived stdout/stderr by string-splitting the human-readable artifact
     on "\\n# --- stderr ---\\n", so any captured output containing that literal
     split the file in the wrong place. The tool contract actively tells
     Basilisk to read its own prior artifacts, so this was reachable in normal
     use — and the ledger accused itself.

  Both have one root cause: the integrity check RE-DERIVED the payload instead
  of hashing what was written. It now hashes the artifact bytes. Legacy events
  (no artifact_sha256) still verify via the section path, with the None hole
  closed.

SCOPE (basilisk_scope.py / basilisk_ext/engage.py) — the authorisation
boundary for an autonomous scanner.

  3. `_strip_to_host` split on "/" to drop a URL path and ate the CIDR PREFIX
     with it, so `10.0.0.0/8` was judged as the single address `10.0.0.0`.
     With scope 10.0.0.0/24 that ALLOWED a 16.7-million-host sweep.

  4. Exclusions used the authorisation test (containment), so `nmap
     10.0.0.0/24` was allowed while the single excluded host 10.0.0.1 inside
     it was correctly refused — the carve-out could be stepped over by naming
     the range around it. Exclusions now use OVERLAP.

  5. IP rules were compared as STRINGS, so `2001:db8::1` and
     `2001:db8:0:0:0:0:0:1` — one host — compared unequal.

  basilisk_scope and basilisk_ext.engage are documented as lockstep twins, and
  divergence is itself a bypass (the gate refuses while scope_check tells the
  operator he is in scope). Both were fixed together and the agreement is
  asserted here.

Run:  python3 tests/test_evidence_scope.py
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from basilisk_ledger import EvidenceLedger                      # noqa: E402
import basilisk_scope as S                                      # noqa: E402
from basilisk_ext import engage as E                            # noqa: E402

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


def _ledger():
    d = pathlib.Path(tempfile.mkdtemp(prefix="bz-ev-"))
    return d, EvidenceLedger(d)


def _artifact(d):
    return next(p for p in d.rglob("*") if p.is_file() and p.suffix == ".txt")


# ── 1. tampering is detected, including on an empty-output step ──────
print("\n== forged evidence is detected ==")
_d, _L = _ledger()
_L.record("mkdir -p /tmp/x", "make a dir",
          {"ok": False, "rc": 1, "stdout": "", "stderr": "permission denied"})
ck("a step with empty stdout still verifies clean before tampering",
   _L.verify()["intact"] is True)
_a = _artifact(_d)
_a.write_text(_a.read_text().replace(
    "# --- stdout ---\n", "# --- stdout ---\nFORGED: uid=0(root)\n"))
_v = _L.verify()
ck("…and tampering with it IS caught", _v["intact"] is False, str(_v))
ck("…reported as a hash mismatch",
   any(p.get("issue") == "hash mismatch" for p in _v["problems"]))

_d, _L = _ledger()
_L.record("id", "who am i", {"ok": True, "rc": 0,
                             "stdout": "uid=1000(user)\n", "stderr": ""})
_a = _artifact(_d)
_a.write_text(_a.read_text().replace("uid=1000(user)", "uid=0(root)"))
ck("ordinary tampering is still caught", _L.verify()["intact"] is False)

_d, _L = _ledger()
_L.record("whoami", "x", {"ok": True, "rc": 0, "stdout": "user\n", "stderr": ""})
_artifact(_d).unlink()
ck("a deleted artifact is reported",
   any(p.get("issue") == "artifact missing" for p in _L.verify()["problems"]))


# ── 2. …and untouched evidence is NOT accused ────────────────────────
print("\n== untouched evidence verifies clean ==")
_d, _L = _ledger()
_L.record("cat evidence/step-0001.txt", "review my own evidence",
          {"ok": True, "rc": 0,
           "stdout": "header\n# --- stderr ---\nbody\n", "stderr": ""})
ck("output containing the section marker does NOT false-alarm",
   _L.verify()["intact"] is True, str(_L.verify()))

_d, _L = _ledger()
for _i in range(4):
    _L.record(f"echo {_i}", "r", {"ok": True, "rc": 0,
                                  "stdout": f"out{_i}\n", "stderr": f"err{_i}\n"})
_v = _L.verify()
ck("a normal run verifies clean",
   _v["intact"] is True and _v["artifacts_matched"] == 4, str(_v))
ck("every event carries a whole-artifact hash",
   all(e.get("artifact_sha256") for e in _L.read_events() if e.get("artifact")))


# ── 3. a malformed ledger degrades, it does not crash ────────────────
print("\n== a junk ledger line does not take the evidence system down ==")
_lp = next(_d.glob("*.jsonl"))
_lp.write_text(_lp.read_text() + "null\n123\n[]\n\"str\"\nnot json at all\n")
for _fn, _nm in ((_L.summary, "summary"), (_L.verify, "verify"),
                 (_L.export_markdown, "export_markdown")):
    try:
        _fn()
        ck(f"{_nm}() survives non-object JSON lines", True)
    except Exception as _e:
        ck(f"{_nm}() survives non-object JSON lines", False,
           f"{type(_e).__name__}: {_e}")
ck("…and the real events are still all there", _L.summary()["steps"] == 4)

ck("read_events(limit=0) returns nothing, as it says",
   _L.read_events(limit=0) == [])
ck("read_events(limit=2) returns two", len(_L.read_events(limit=2)) == 2)
ck("read_events() with no limit returns all", len(_L.read_events()) == 4)


# ── 4. a range is judged as a range ──────────────────────────────────
print("\n== the scope gate judges a CIDR as a CIDR ==")
ST = {"scope": ["acme.com", "10.0.0.0/24"], "exclusions": ["10.0.0.1"],
      "authorised": True, "window": None}

for _cmd, _want, _why in [
    ("nmap -sS 10.0.0.0/8",   False, "16.7M hosts vs a /24 scope"),
    ("nmap 10.0.0.0/16",      False, "65k hosts vs a /24 scope"),
    ("nmap 10.0.0.0/24",      False, "overlaps the excluded 10.0.0.1"),
    ("nmap 10.0.0.128/25",    True,  "inside scope, misses the exclusion"),
    ("nmap 10.0.0.5",         True,  "single in-scope host"),
    ("nmap 10.0.0.1",         False, "the excluded host itself"),
    ("nmap 8.8.8.8",          False, "plainly out of scope"),
    ("curl https://acme.com", True,  "in-scope hostname"),
    ("nmap acme.com",         True,  "in-scope hostname"),
    ("nmap api.acme.com",     True,  "subdomain of an in-scope domain"),
]:
    _got = bool(S.check_command(_cmd, ST).get("allowed"))
    ck(f"{_cmd}  ->  {'allowed' if _want else 'refused'}  ({_why})",
       _got is _want, f"got allowed={_got}")

ck("the prefix survives host extraction",
   S._strip_to_host("10.0.0.0/8") == "10.0.0.0/8")
ck("…while a URL path is still stripped",
   S._strip_to_host("https://acme.com/admin?x=1") == "acme.com")
ck("…and host:port still works", S._strip_to_host("acme.com:8443") == "acme.com")
ck("…and bracketed IPv6 still works",
   S._strip_to_host("[2001:db8::1]:443") == "2001:db8::1")

print("\n== containment for scope, overlap for exclusions ==")
ck("a range inside an authorised range is authorised",
   S._match_rule("10.0.0.128/25", "10.0.0.0/24") is True)
ck("a range CONTAINING an authorised range is NOT",
   S._match_rule("10.0.0.0/8", "10.0.0.0/24") is False)
ck("an exclusion is TOUCHED by a range that overlaps it",
   S._touches_rule("10.0.0.0/24", "10.0.0.1") is True)
ck("…but not by a disjoint range",
   S._touches_rule("10.0.1.0/24", "10.0.0.1") is False)
ck("a hostname is not covered by an IP rule",
   S._match_rule("acme.com", "10.0.0.0/24") is False)
ck("an IP is not covered by a hostname rule",
   S._match_rule("10.0.0.5", "acme.com") is False)

print("\n== IPv6 is compared as an ADDRESS, not a string ==")
ck("expanded and compact forms are one host",
   S._match_rule("2001:db8::1", "2001:db8:0:0:0:0:0:1") is True)
ck("…and an IPv6 range still contains its members",
   S._match_rule("2001:db8::1", "2001:db8::/32") is True)
ck("…while a v4 target is not inside a v6 range",
   S._match_rule("10.0.0.5", "2001:db8::/32") is False)


# ── 5. the lockstep twins must not diverge ───────────────────────────
# The module docstring says these two must agree because divergence IS a
# bypass: the gate refuses while scope_check tells the operator he is in scope.
print("\n== basilisk_scope and engage agree, host for host ==")
for _h, _r in [("10.0.0.0/8", "10.0.0.0/24"), ("10.0.0.128/25", "10.0.0.0/24"),
               ("10.0.0.5", "10.0.0.0/24"), ("2001:db8::1", "2001:db8:0:0:0:0:0:1"),
               ("evil.com", "acme.com"), ("api.acme.com", "acme.com"),
               ("10.0.0.5", "acme.com"), ("acme.com", "10.0.0.0/24"),
               ("", "acme.com"), ("acme.com", "")]:
    ck(f"match({_h!r}, {_r!r}) agrees",
       S._match_rule(_h, _r) == E._match_one(_h, _r),
       f"scope={S._match_rule(_h, _r)} engage={E._match_one(_h, _r)}")

for _t in ["10.0.0.0/8", "https://acme.com/path", "[2001:db8::1]:443",
           "user@h.com:22", "acme.com", ""]:
    ck(f"host extraction agrees for {_t!r}",
       S._strip_to_host(_t) == E._host_of(_t),
       f"scope={S._strip_to_host(_t)!r} engage={E._host_of(_t)!r}")


# ── 6. nothing here may raise ────────────────────────────────────────
print("\n== fail-safe ==")
for _junk in ("", "/", "//", "1.2.3.4/99", "::/0", "a/b/c", "/32", "*.acme.com"):
    try:
        S._strip_to_host(_junk)
        S._match_rule(_junk, "acme.com")
        S._match_rule("acme.com", _junk)
        S._touches_rule(_junk, _junk)
        E._match_one(_junk, _junk)
        ck(f"junk is safe: {_junk!r}", True)
    except Exception as _e:
        ck(f"junk is safe: {_junk!r}", False, f"{type(_e).__name__}: {_e}")

print(f"\nevidence_scope: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
