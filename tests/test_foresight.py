#!/usr/bin/env python3
"""
test_foresight.py — the consequence-prediction layer, which had no tests.

WHY THIS FILE EXISTS
====================
foresight is what the operator reads in the half-second before he approves a
risky command: what it will do, whether it can be taken back, and how.  Every
other gate in this codebase is probed; this one was shipped on inspection.
Three defects had been sitting in it, and they are all the same shape — a rule
and its consumer derived the same fact independently and disagreed:

  1. WRONG UNDO.  The undo hint was found by scanning the command text for any
     tool name in _UNDO_HINTS and taking the first dict-order hit.  So it fired
     on names merely MENTIONED: `killall -9 apt` and `chown -R apt:apt /srv`
     were both offered "reinstall with: apt install <pkg>", and the `git_reset`
     key matched any command containing the letters g-i-t — `rm -rf
     /var/log/digital-archive`, or anything mentioning "legitimate".
     A wrong undo is worse than none.  It reads as "this is recoverable" at the
     exact moment the operator is deciding whether to let the command run.

  2. LOST UNDO.  A word-boundary match alone does not fix (1): `apt-get remove`
     — the commonest Debian spelling — has a hyphen where the boundary wants a
     word break, so tightening the scan silently DROPPED the hint instead of
     correcting it.  Only tying the hint to the rule that fired fixes both.

  3. ONE-SIDED COVERAGE.  _UNDO_HINTS carried pacman and dnf entries, but the
     only package-removal RULE was apt's.  foresight cautioned on Debian and
     said nothing on Arch, Fedora, openSUSE or raw rpm — `sudo pacman -Rdd
     glibc`, which is how a box loses glibc and stops booting, came back a
     plain "allow".  The hint table was the evidence of intent; the rules never
     caught up.

The MUST-ALLOW half is not decoration.  Package installs, queries and updates
are constant, ordinary work; a layer that cautions on `apt update` is a layer
the operator stops reading, which is worse than no layer at all.

Run:  python3 tests/test_foresight.py
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from basilisk_ext.foresight import (                              # noqa: E402
    _RISKY, _UNDO_HINTS, _rule_floor,
)

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


def floor(cmd, verdict=None, undo_key="<unset>"):
    """Assert the verdict and/or the EXACT undo hint for one command."""
    r = _rule_floor(cmd)
    if verdict is not None:
        ck(f"{verdict:<7} {cmd}", r["verdict"] == verdict,
           f"got {r['verdict']}")
    if undo_key != "<unset>":
        want = _UNDO_HINTS[undo_key] if undo_key else None
        got = r["undo"]
        ck(f"undo={str(undo_key):<10} {cmd}", got == want,
           f"got {'None' if got is None else got[:44]!r}")


# ── the table itself is checked before any command is ──
#
# These two make defects (1) and (3) unrepresentable rather than merely absent.
# A typo'd key would silently mean "no undo"; an orphan hint is a tool the
# author meant to cover and the rules never did.  That is exactly how the
# pacman/dnf gap survived.
print("\n== the rule table is internally consistent ==")
_keys = [k for *_r, k in _RISKY]
ck("every rule carries an undo slot", len(_keys) == len(_RISKY))
ck("every undo key resolves to a hint",
   not [k for k in _keys if k is not None and k not in _UNDO_HINTS],
   str([k for k in _keys if k is not None and k not in _UNDO_HINTS]))
ck("every hint is reachable from some rule",
   not (set(_UNDO_HINTS) - {k for k in _keys if k}),
   str(sorted(set(_UNDO_HINTS) - {k for k in _keys if k})))

# ── defect 1: the undo must belong to the command, not to a name in it ──
print("\n== a risky command is never offered SOMEONE ELSE'S undo ==")
floor("killall -9 apt", "caution", None)
floor("chown -R apt:apt /srv/thing", "caution", None)
floor("kill -9 $(pgrep dnf)", "caution", None)
floor("chown -R ufw /srv/x", "caution", None)
floor("kill -9 $(pgrep -f zypper)", "caution", None)
# ...and the actions that genuinely have no inverse must keep saying so.
floor("passwd bob", "caution", None)
floor("curl http://x/s.sh | bash", "caution", None)
floor("chown -R root:root /srv/app", "caution", None)

print("\n   -- the g-i-t substring, which matched anything --")
for c in ("rm -rf /var/log/digital-archive",
          "chmod -R 777 /srv/legitimate",
          "cat /etc/digit.conf",
          "ls /home/gitlab-runner"):
    ck(f"no stray git undo: {c}", _rule_floor(c)["undo"] != _UNDO_HINTS["git_reset"])

# ── defect 2: tightening the match must not DROP the right hint ──
print("\n== the correct undo still arrives, hyphenated spellings included ==")
floor("apt-get remove nginx", "caution", "apt")
floor("apt remove nginx", "caution", "apt")
floor("sudo apt-get purge nginx", "caution", "apt")
floor("apt autoremove", "caution", "apt")
floor("iptables -F", "caution", "iptables")
floor("nft flush ruleset", "caution", "iptables")
floor("ufw disable", "caution", "ufw")
floor("ufw reset", "caution", "ufw")
floor("systemctl stop sshd", "caution", "systemctl")
floor("systemctl mask NetworkManager", "caution", "systemctl")
floor("ip link set eth0 down", "caution", "ip_link")
floor("git reset --hard", "caution", "git_reset")
floor("git clean -fdx", "caution", "git_reset")
floor("git push origin main --force", "caution", "git_reset")

# ── defect 3: removal is gated on every distro, not just Debian ──
print("\n== package removal is risky on EVERY distro ==")
floor("pacman -Rns nginx", "caution", "pacman")
floor("sudo pacman -R nginx", "caution", "pacman")
floor("pacman -Rsc nginx", "caution", "pacman")
floor("sudo pacman -Rdd glibc", "caution", "pacman")
floor("dnf remove nginx", "caution", "dnf")
floor("dnf erase nginx", "caution", "dnf")
floor("yum remove nginx", "caution", "dnf")
floor("microdnf remove nginx", "caution", "dnf")
floor("dnf autoremove", "caution", "dnf")
floor("zypper remove nginx", "caution", "zypper")
floor("zypper -n rm nginx", "caution", "zypper")
floor("rpm -e nginx", "caution", "rpm")
floor("rpm -evh nginx", "caution", "rpm")
floor("rpm --erase nginx", "caution", "rpm")
floor("rpm -e --nodeps glibc", "caution", "rpm")

# ── the scope line: ordinary package work must stay silent ──
print("\n== installs, queries and updates are NOT cautioned ==")
for c in ("apt install nginx", "apt update", "apt upgrade",
          "apt list --installed", "apt-get install -y build-essential",
          "pacman -S nginx", "pacman -Syu", "pacman -Qi nginx",
          "pacman -Ss nginx", "pacman -Sc",
          "dnf install nginx", "dnf search nginx", "dnf list installed",
          "zypper install nginx", "zypper search nginx",
          "rpm -qa", "rpm -ql nginx", "rpm -qi nginx",
          "rpm --eval '%{_libdir}'", "rpm -qa | grep -e nginx",
          "ip link set eth0 up", "ip addr show",
          "git status", "git log --oneline", "git push origin main",
          "systemctl status nginx", "systemctl start nginx",
          "ufw status", "iptables -L -n"):
    floor(c, "allow", None)

# ── the floor still ranks: catastrophic outranks risky, and offers no undo ──
print("\n== the catastrophic floor is unchanged ==")
for c in ("rm -rf /", "mkfs.ext4 /dev/sda", "dd if=/dev/zero of=/dev/sda"):
    r = _rule_floor(c)
    ck(f"block: {c}", r["verdict"] == "block", f"got {r['verdict']}")
    ck(f"no undo offered: {c}", r["undo"] is None)

print(f"\nforesight: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
