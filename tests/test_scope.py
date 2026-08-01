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


# ── 6b. bypasses found in this gate's own review ─────────────────────
print("\n== regressions: bypasses this gate itself shipped with ==")
import tempfile
_cwd = os.getcwd()
_tmp = tempfile.mkdtemp()
os.chdir(_tmp)
for _f in ("acme.com", "evil.com", "8.8.8.8"):
    open(_f, "w").write("x")
# The extractor must not stat the filesystem: `touch evil.com` once dropped the
# host from the extracted set, and an in-scope IP alongside it carried the
# whole command through.
for label, cmd in [("decoy file masks host", "nmap 10.0.0.5 evil.com"),
                   ("decoy file alone", "nmap evil.com"),
                   ("decoy named as IP", "nmap 8.8.8.8")]:
    v = S.check_command(cmd, {"scope": ["10.0.0.0/24"]})
    check(f"decoy: {label}", not v["allowed"], str(v["extraction"]))
os.chdir(_cwd)

# Boolean flags must never swallow the target. `-s`/`-k` are no-value on curl;
# treating them as value-taking ate the URL entirely.
for label, cmd in [("curl -s", "curl -s https://evil.com"),
                   ("curl -k", "curl -k https://evil.com"),
                   ("curl -sk bundled", "curl -sk https://evil.com"),
                   ("wget -q", "wget -q https://evil.com"),
                   ("nmap -Pn", "nmap -Pn 8.8.8.8"),
                   ("nmap -sV -T4", "nmap -sV -T4 8.8.8.8"),
                   ("nuclei -silent", "nuclei -silent -u https://evil.com"),
                   ("unknown flag", "nmap --some-future-flag 8.8.8.8")]:
    v = S.check_command(cmd, SCOPE)
    check(f"boolflag: {label}", not v["allowed"], str(v["extraction"]))



# ── 6c. wrapper, substitution and quoted-command bypass classes ──────
print("\n== wrapper / substitution bypass classes ==")
_W = {"scope": ["10.0.0.0/24"]}
for label, cmd in [
    ("env assignment wrapper",  "env FOO=1 nmap 8.8.8.8"),
    ("env -i",                  "env -i nmap 8.8.8.8"),
    ("sudo -u takes a value",   "sudo -u root nmap 8.8.8.8"),
    ("timeout float duration",  "timeout 1.5 nmap 8.8.8.8"),
    ("nice -n",                 "nice -n 10 nmap 8.8.8.8"),
    ("ionice",                  "ionice -c3 nmap 8.8.8.8"),
    ("setsid",                  "setsid nmap 8.8.8.8"),
    ("unbuffer",                "unbuffer nmap 8.8.8.8"),
    ("torsocks",                "torsocks nmap 8.8.8.8"),
    ("firejail",                "firejail nmap 8.8.8.8"),
    ("chrt",                    "chrt -f 99 nmap 8.8.8.8"),
    ("taskset",                 "taskset -c 0 nmap 8.8.8.8"),
    ("busybox",                 "busybox nmap 8.8.8.8"),
    ("command builtin",         "command nmap 8.8.8.8"),
    ("exec",                    "exec nmap 8.8.8.8"),
    ("su -c command string",    "su -c 'nmap 8.8.8.8' root"),
    ("runuser -c",              "runuser -u x -c 'curl https://evil.com'"),
    ("script -qc",              "script -qc 'nmap 8.8.8.8' /dev/null"),
    ("watch positional cmd",    "watch -n1 'nmap 8.8.8.8'"),
    ("xargs sh -c",             "xargs -I{} sh -c 'nmap 8.8.8.8'"),
    ("$( ) substitution",       "echo $(nmap 8.8.8.8)"),
    ("backtick substitution",   "echo `nmap 8.8.8.8`"),
    ("assignment substitution", "X=$(nmap 8.8.8.8); echo $X"),
    ("nested substitution",     "echo $(echo $(nmap 8.8.8.8))"),
    ("substitution in args",    "nmap `curl -s https://evil.com`"),
    ("${IFS} obfuscation",      "nmap${IFS}8.8.8.8"),
]:
    v = S.check_command(cmd, _W)
    check(f"wrapper: {label}", not v["allowed"], str(v["extraction"]))

print("\n== wrappers must not create FALSE refusals ==")
for label, cmd in [
    ("proxychains in-scope",  "proxychains nmap 10.0.0.5"),
    ("sudo in-scope",         "sudo nmap -sV 10.0.0.5"),
    ("env in-scope",          "env FOO=1 nmap 10.0.0.5"),
    ("su -c in-scope",        "su -c 'nmap 10.0.0.5' root"),
    ("which nmap",            "which nmap"),
    ("apt install",           "apt install -y nuclei"),
    ("apt-cache policy",      "apt-cache policy nmap"),
    ("command -v",            "command -v ffuf"),
    ("man page",              "man curl"),
    ("hydra proto arg",       "hydra -l admin -P pw.txt 10.0.0.5 ssh"),
    ("harmless substitution", "echo $(date +%s)"),
    ("nested harmless subst", "cd $(dirname $(readlink -f x))"),
]:
    v = S.check_command(cmd, _W)
    check(f"no-FP: {label}", v["allowed"], f"{v.get('reason','')[:60]} {v['extraction']}")

# Structural invariant: a name cannot be both a wrapper and a tool, or the
# backstop fires on every legitimate use of it (proxychains hit exactly this).
check("no wrapper/tool set overlap", not (S._WRAPPERS & S._NETWORK_TOOLS),
      str(S._WRAPPERS & S._NETWORK_TOOLS))


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


# ── unterminated command substitution (v7.9.4) ───────────────────────
# A single leading backtick made _substitution_payloads consume the REST of
# the command string and then DROP it, so "`nmap evil.com" came back as
# "passive/local command -- scope boundary not engaged". Not exploitable
# (bash and sh both reject an unterminated backquote as a syntax error, and
# that was checked against the real shells rather than assumed) -- but a
# fail-OPEN verdict reached by accident is precisely what this gate exists
# not to do. The unterminated "$(" form had the same shape.
print("\n== unterminated substitution fails closed ==")
for _c in ("`nmap evil.com",
           "$(nmap evil.com",
           "`nmap 10.0.0.5",          # in-scope target, still unparseable
           "`curl https://evil.com",
           "echo `nmap evil.com"):
    _v = S.check_command(_c, SCOPE)
    check(f"unterminated refused: {_c[:24]}", not _v.get("allowed"),
          str(_v.get("reason"))[:70])

# The fix must not sweep up terminated forms or ordinary commands.
for _c, _want in (("echo `nmap evil.com`", False),
                  ("echo $(nmap evil.com)", False),
                  ("echo `nmap 10.0.0.5`", True),
                  ("echo $(id)", True),
                  ("ls -la", True),
                  ("echo hello", True)):
    _v = S.check_command(_c, SCOPE)
    check(f"unchanged: {_c[:26]}", bool(_v.get("allowed")) is _want,
          str(_v.get("reason"))[:60])

print(f"\nscope boundary: {_passed} passed, {_failed} failed")
sys.exit(1 if _failed else 0)
