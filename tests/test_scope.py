#!/usr/bin/env python3
"""
test_scope.py — the authorisation boundary.

Three things have to hold, and the third is the one that gets features ripped
back out again:

  1. FAIL CLOSED — no scope, unknowable target, or no match ⇒ refused.
  2. NO BYPASS — quoting, $IFS, `sh -c`, proxychains, sudo, chained operators
     and inline `--url=` forms must not launder a target past the gate.
  3. NO FALSE POSITIVES — ordinary local work (`ls`, `cat`, `python3 -m
     pytest`, `git commit`) must be completely untouched, and the operator's
     own localhost benchmark runs must keep working.

Run:  python3 tests/test_scope.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import basilisk_scope as S  # noqa: E402

_passed = 0
_failed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  PASS {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}" + (f"   [{detail}]" if detail else ""))


SCOPE = {"scope": ["acme.com", "10.0.0.0/24", "192.168.5.10"],
         "exclusions": ["vpn.acme.com", "10.0.0.1"],
         "allow_loopback": True}


# ── 1. passive commands are not touched ──────────────────────────────
print("\n== passive commands stay untouched ==")
for cmd in ["ls -la", "cat /etc/passwd", "python3 -m pytest tests/",
            "git commit -m 'fix'", "grep -rn TODO .", "cd /tmp && ls",
            "echo hello > out.txt", "pip install requests",
            "python3 script.py --url http://evil.com"]:
    v = S.check_command(cmd, SCOPE)
    check(f"passive: {cmd[:38]}", v["allowed"] and not v["active"],
          f"active={v['active']} reason={v.get('reason','')[:60]}")


# ── 2. in-scope active commands are allowed ──────────────────────────
print("\n== in-scope targets allowed ==")
for cmd in ["nmap -sV 10.0.0.5",
            "nuclei -u https://app.acme.com",
            "ffuf -u https://acme.com/FUZZ -w /usr/share/wordlists/big.txt",
            "curl -s https://api.acme.com/health",
            "gobuster dir -u http://10.0.0.7 -w list.txt",
            "nmap -sV 192.168.5.10",
            "httpx -u sub.acme.com"]:
    v = S.check_command(cmd, SCOPE)
    check(f"allow: {cmd[:38]}", v["allowed"], v.get("reason", "")[:70])


# ── 3. out-of-scope is refused ───────────────────────────────────────
print("\n== out-of-scope refused ==")
for cmd in ["nmap -sV 8.8.8.8",
            "nuclei -u https://google.com",
            "curl https://evil.example.org/",
            "ffuf -u https://notacme.com/FUZZ -w w.txt",
            "nmap 10.0.1.5",
            "hydra -l admin -P rock.txt ssh://198.51.100.9"]:
    v = S.check_command(cmd, SCOPE)
    check(f"deny: {cmd[:38]}", not v["allowed"],
          f"allowed={v['allowed']} {v.get('reason','')[:60]}")


# ── 4. exclusions beat scope ─────────────────────────────────────────
print("\n== exclusions override scope ==")
for cmd in ["nmap -sV vpn.acme.com", "curl https://vpn.acme.com/",
            "nmap 10.0.0.1"]:
    v = S.check_command(cmd, SCOPE)
    check(f"excluded: {cmd[:38]}",
          (not v["allowed"]) and v.get("failure") == "excluded",
          f"failure={v.get('failure')}")


# ── 5. fail closed with no scope at all ──────────────────────────────
print("\n== no scope set ⇒ everything remote refused ==")
for cmd in ["nmap -sV 10.0.0.5", "curl https://acme.com"]:
    v = S.check_command(cmd, {})
    check(f"noscope: {cmd[:38]}",
          (not v["allowed"]) and v.get("failure") == "out_of_scope",
          f"failure={v.get('failure')}")
check("noscope: loopback still allowed (benchmarks)",
      S.check_command("nuclei -u http://localhost:3000", {})["allowed"])
check("noscope: 127.0.0.1 allowed",
      S.check_command("nmap -sV 127.0.0.1", {})["allowed"])
check("loopback deniable when operator turns it off",
      not S.check_command("nmap 127.0.0.1",
                          {"allow_loopback": False})["allowed"])


# ── 6. bypass resistance ─────────────────────────────────────────────
print("\n== bypass attempts ==")
bypasses = [
    ("sh -c wrapper",         "sh -c 'nmap -sV 8.8.8.8'"),
    ("bash -c wrapper",       "bash -c \"curl https://evil.com\""),
    ("chained after ok cmd",  "nmap 10.0.0.5 && nmap 8.8.8.8"),
    ("chained with ;",        "ls; nuclei -u https://evil.com"),
    ("piped",                 "echo x | curl https://evil.com"),
    ("$IFS obfuscation",      "nmap${IFS}-sV${IFS}8.8.8.8"),
    ("sudo prefix",           "sudo nmap -sV 8.8.8.8"),
    ("proxychains prefix",    "proxychains nmap -sV 8.8.8.8"),
    ("timeout prefix",        "timeout 60 nmap -sV 8.8.8.8"),
    ("nohup prefix",          "nohup nmap -sV 8.8.8.8"),
    ("absolute path",         "/usr/bin/nmap -sV 8.8.8.8"),
    ("inline --url=",         "nuclei --url=https://evil.com"),
    ("env prefix",            "FOO=bar nmap -sV 8.8.8.8"),
    ("url with userinfo",     "curl https://user:pw@evil.com/x"),
    ("host:port form",        "nmap evil.com:8080"),
    ("nested sh -c",          "sh -c 'sh -c \"nmap 8.8.8.8\"'"),
]
for label, cmd in bypasses:
    v = S.check_command(cmd, SCOPE)
    check(f"blocked: {label}", not v["allowed"],
          f"allowed={v['allowed']} ext={v['extraction']}")


# ── 7. unknowable targets fail closed ────────────────────────────────
print("\n== unknowable targets fail closed ==")
for label, cmd in [("nmap -iL file", "nmap -iL targets.txt"),
                   ("unparseable quotes", "nmap -sV 'unclosed"),
                   ("no target at all", "nmap -sV")]:
    v = S.check_command(cmd, SCOPE)
    check(f"failclosed: {label}", not v["allowed"],
          f"failure={v.get('failure')}")


# ── 8. false-positive guards on target-ish looking args ──────────────
print("\n== filenames and flag values are not treated as hosts ==")
fp = [
    "ffuf -u https://acme.com/FUZZ -w /usr/share/seclists/big.txt",
    "nmap -sV 10.0.0.5 -oN scan.results.txt",
    "nuclei -u https://acme.com -t cves/2024/ -severity high",
    "hydra -l admin -P rockyou.txt 10.0.0.5 ssh",
    "curl -H 'X-Api-Key: abc.def.ghi' https://acme.com/v1",
    "gobuster dir -u http://10.0.0.7 -w common.list -o out.json",
]
for cmd in fp:
    v = S.check_command(cmd, SCOPE)
    check(f"no-FP: {cmd[:44]}", v["allowed"],
          f"{v.get('reason','')[:70]} ext={v['extraction']}")


# ── 9. engagement window ─────────────────────────────────────────────
print("\n== engagement window ==")
now = datetime.now(timezone.utc)
past = {"scope": ["acme.com"],
        "window": {"start": (now - timedelta(days=9)).isoformat(),
                   "end":   (now - timedelta(days=2)).isoformat()}}
future = {"scope": ["acme.com"],
          "window": {"start": (now + timedelta(days=2)).isoformat()}}
live = {"scope": ["acme.com"],
        "window": {"start": (now - timedelta(days=1)).isoformat(),
                   "end":   (now + timedelta(days=1)).isoformat()}}
check("window closed ⇒ refused",
      not S.check_command("nmap acme.com", past)["allowed"])
check("window not open ⇒ refused",
      not S.check_command("nmap acme.com", future)["allowed"])
check("window live ⇒ allowed",
      S.check_command("nmap acme.com", live)["allowed"])
check("window irrelevant to passive cmds",
      S.check_command("ls -la", past)["allowed"])


# ── 10. scope matching semantics match engage._match_one ─────────────
print("\n== scope rule semantics ==")
check("subdomain covered by domain rule",
      S.check_command("curl https://deep.sub.acme.com", SCOPE)["allowed"])
check("sibling domain NOT covered",
      not S.check_command("curl https://acme.com.evil.net", SCOPE)["allowed"])
check("CIDR covers member",
      S.check_command("nmap 10.0.0.200", SCOPE)["allowed"])
check("CIDR does not cover neighbour",
      not S.check_command("nmap 10.0.1.200", SCOPE)["allowed"])
check("wildcard rule works",
      S.check_command("curl https://x.corp.io", {"scope": ["*.corp.io"]})["allowed"])

# cross-check against the real engage matcher on a grid
try:
    from basilisk_ext import engage as _eng
    grid = [("a.acme.com", "acme.com"), ("acme.com", "acme.com"),
            ("evilacme.com", "acme.com"), ("10.0.0.5", "10.0.0.0/24"),
            ("10.0.1.5", "10.0.0.0/24"), ("x.corp.io", "*.corp.io"),
            ("corp.io", "*.corp.io"), ("1.2.3.4", "1.2.3.4"),
            ("1.2.3.5", "1.2.3.4")]
    mismatch = [(h, r) for h, r in grid
                if S._match_rule(h, r) != _eng._match_one(h, r)]
    check("gate matcher == engage matcher on grid", not mismatch, str(mismatch))
except Exception as e:
    check("gate matcher == engage matcher on grid", False, f"import: {e}")


print(f"\nscope boundary: {_passed} passed, {_failed} failed")
sys.exit(1 if _failed else 0)
