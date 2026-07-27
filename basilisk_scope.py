#!/usr/bin/env python3
"""
basilisk_scope.py — the AUTHORISATION BOUNDARY, enforced structurally.

Before this module, "scope" was advice.  `basilisk_persona.py` told the model
to call `scope_check` before anything active, and exactly one tool
(`tool_sqlmap_plan`) actually enforced it — and even that fell open on an
exception.  Every other active command (nmap, nuclei, ffuf, hydra, curl,
gobuster, masscan, …) reached `tool_run_command` with no scope check at all.

On a leashed agent that is a documentation problem.  On an UNLEASHED one it is
the whole ballgame: the difference between a pentest and an intrusion is
authorisation, and a prompt-level control on an autonomous loop is one bad
parse, one poisoned page, or one model slip away from firing at a host nobody
authorised.

So this enforces it at the execution primitive, in the same shape and with the
same no-override posture as `is_catastrophic_command`:

    * FAIL CLOSED.  No scope, unparseable target, or no match  ⇒  REFUSED.
    * EXCLUSIONS BEAT SCOPE.  An RoE carve-out ("10.0.0.0/8 except the DC at
      10.1.1.0/24") is a first-class concept, checked before the allowlist.
    * ENGAGEMENT WINDOW.  Testing an in-scope host outside the authorised
      window is still unauthorised testing.
    * PASSIVE COMMANDS ARE UNTOUCHED.  `ls`, `cat`, `python3 -m pytest` do not
      go near this gate.  It engages only when a network-active binary is
      invoked, so it cannot break local work.

Design notes
------------
Tokenising reuses `basilisk_safety`'s hardened splitter (already fuzzed with
40k adversarial shell strings) rather than growing a second, weaker one: same
$IFS normalisation, same quote-aware sub-command split, same `sh -c` recursion.
A bypass found in one gate is then fixed for both.

stdlib only.  No network.  No I/O beyond reading the engagement JSON.
"""

from __future__ import annotations

import ipaddress
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

try:  # reuse the hardened tokeniser; degrade safely if it ever moves
    # NB: in basilisk_safety, _INTERPRETERS is the set of *language* runtimes
    # (python/perl/ruby/node/php) and _SHELLS is the set of shells. Conflating
    # them silently disables `sh -c` recursion — caught by test_scope.
    from basilisk_safety import (_normalize, _split_subcommands, _argv, _base,
                                 _SHELLS, _INTERPRETERS, _INLINE_FLAGS)
    _HAVE_SAFETY = True
except Exception:  # pragma: no cover - defensive
    _HAVE_SAFETY = False

    def _normalize(command: str) -> str:
        s = re.sub(r"\$\{IFS[^}]*\}", " ", command)
        return re.sub(r"\$IFS\b", " ", s)

    def _split_subcommands(command: str) -> List[str]:
        return [p.strip() for p in re.split(r"[;&|\n]+", command) if p.strip()]

    def _argv(sub: str) -> Optional[List[str]]:
        import shlex
        try:
            return shlex.split(sub, posix=True)
        except ValueError:
            return None

    def _base(arg: str) -> str:
        return os.path.basename(arg)

    _SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "ash", "fish"}
    _INTERPRETERS = {"python", "python2", "python3", "perl", "ruby", "node",
                     "nodejs", "php"}
    _INLINE_FLAGS = {"python": ("-c",), "python2": ("-c",), "python3": ("-c",),
                     "perl": ("-e", "-E"), "ruby": ("-e", "-E"),
                     "node": ("-e", "--eval"), "nodejs": ("-e", "--eval"),
                     "php": ("-r",)}


# ══════════════════════════════════════════════════════════════════════
# WHAT COUNTS AS AN ACTIVE, NETWORK-TOUCHING COMMAND
# ══════════════════════════════════════════════════════════════════════
# Only these engage the gate.  Anything else runs exactly as it did before —
# this list is the blast radius of the whole feature, so it is explicit rather
# than heuristic.  Add a scanner here the day you add it to the arsenal.

_NETWORK_TOOLS: Set[str] = {
    # discovery / mapping
    "nmap", "masscan", "naabu", "rustscan", "zmap", "unicornscan", "fping",
    "hping3", "arp-scan", "netdiscover", "traceroute", "tracepath", "ping",
    # web recon / content discovery
    "gobuster", "feroxbuster", "dirb", "dirsearch", "ffuf", "wfuzz", "dirbuster",
    "httpx", "httprobe", "katana", "hakrawler", "gau", "waybackurls", "gospider",
    # subdomain / dns
    "subfinder", "amass", "assetfinder", "sublist3r", "dnsrecon", "dnsenum",
    "fierce", "dig", "host", "nslookup", "dnsx", "puredns", "massdns",
    # vuln scanning
    "nuclei", "nikto", "wpscan", "joomscan", "droopescan", "whatweb", "wafw00f",
    "testssl.sh", "testssl", "sslscan", "sslyze", "openssl",
    # exploitation / injection
    "sqlmap", "commix", "xsser", "tplmap", "nosqlmap", "jwt_tool",
    "msfconsole", "msfvenom", "searchsploit", "hydra", "medusa", "ncrack",
    "patator", "crackmapexec", "nxc", "netexec", "evil-winrm", "impacket-psexec",
    # smb / ad
    "smbclient", "smbmap", "enum4linux", "enum4linux-ng", "rpcclient",
    "ldapsearch", "kerbrute", "bloodhound-python", "getuserspns.py",
    "gettgt.py", "secretsdump.py", "impacket-secretsdump",
    # generic transports that reach arbitrary hosts
    "curl", "wget", "nc", "ncat", "netcat", "socat", "telnet", "ssh", "scp",
    "sftp", "ftp", "rsync", "openvpn", "proxychains", "proxychains4",
    # api / graphql
    "graphqlmap", "clairvoyance", "arjun", "paramspider", "kiterunner",
}

# Flags whose VALUE is a target.  Short flags are catastrophically overloaded
# across this toolset — `-t` is target/templates/threads/tasks depending on the
# binary, `-l` is login-name for hydra but target-list for others, `-d` is
# domain for subfinder but POST-data for curl.  So the GLOBAL set holds only
# flags that are unambiguous everywhere, and anything overloaded is declared
# per-tool.  (A global set with an exception table was the first design; it got
# `-t cves/2024/` wrong on nuclei.  Allowlist per tool, don't blocklist.)
_TARGET_FLAGS: Set[str] = {
    "-u", "--url", "--urls", "--target", "--targets", "--target-url",
    "--host", "--hostname", "--rhost", "--rhosts",
}
_TOOL_TARGET_FLAGS: Dict[str, Set[str]] = {
    "subfinder": {"-d", "--domain"}, "amass": {"-d", "--domain"},
    "assetfinder": {"-d"}, "sublist3r": {"-d", "--domain"},
    "dnsrecon": {"-d", "--domain"}, "dnsenum": {"-d"}, "fierce": {"--domain"},
    "puredns": {"-d"}, "katana": {"-list"}, "httpx": {"-l", "--list"},
    "nuclei": {"-l", "--list"}, "naabu": {"-list"}, "dnsx": {"-l"},
    "smbmap": {"-H"}, "enum4linux": set(), "wpscan": {"--url"},
    "arjun": {"-u"}, "paramspider": {"-d", "--domain"},
}

# Tools where a normally-unambiguous target flag means something else. `-u` is
# the username on every AD/SMB tool in the arsenal, so it must not be read as
# a URL there.
_TOOL_NON_TARGET_FLAGS: Dict[str, Set[str]] = {
    t: {"-u", "--username"} for t in
    ("smbmap", "smbclient", "crackmapexec", "nxc", "netexec", "evil-winrm",
     "rpcclient", "ldapsearch", "enum4linux", "enum4linux-ng", "kerbrute",
     "impacket-psexec", "impacket-secretsdump", "medusa", "ncrack", "patator")
}

# Flags whose VALUE is definitively NOT a target (wordlists, output files,
# ports, threads…).  Skipping these kills most false positives.
_VALUE_FLAGS_NOT_TARGET: Set[str] = {
    "-w", "--wordlist", "-o", "-oN", "-oX", "-oG", "-oA", "-oJ", "--output",
    "-p", "--ports", "--port", "-P", "--passwords", "--password", "-x", "-e",
    "-T", "--threads", "-c", "--cookie", "-b", "--data", "--data-raw",
    "-A", "--user-agent", "-r", "--rate", "-s", "-S", "-m", "--method",
    "-k", "--key", "-i", "--identity", "-f", "--format", "-n", "-j",
    "--timeout", "--retries", "--delay", "--proxy", "--resolvers",
    "-mc", "-fc", "-ms", "-fs", "-mr", "-fr", "-ac", "-recursion-depth",
    "--severity", "--tags", "--templates", "-tags", "-severity", "-t",
}

# Flags that name a FILE full of targets — statically unknowable, so uncertain.
_TARGET_FILE_FLAGS: Set[str] = {
    "-iL", "--input-list", "-il", "--file", "-f", "--targets-file",
}

# Extensions that make a dotted token a filename, not a hostname.
_FILE_EXTS: Set[str] = {
    "py", "sh", "txt", "json", "xml", "yaml", "yml", "log", "conf", "cfg",
    "csv", "tsv", "html", "htm", "js", "ts", "php", "rb", "go", "rs", "c",
    "cpp", "h", "java", "class", "jar", "pcap", "pcapng", "list", "lst",
    "dic", "dict", "out", "md", "ini", "db", "sqlite", "sql", "zip", "tar",
    "gz", "bz2", "xz", "7z", "pem", "crt", "key", "pub", "png", "jpg",
    "jpeg", "gif", "svg", "pdf", "bak", "old", "tmp", "swp", "so", "bin",
}

_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.\-]*)://(.*)$", re.S)
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[a-z0-9\-_]{1,63}(?<!-)"
    r"(\.(?!-)[a-z0-9\-_]{1,63}(?<!-))+\.?$", re.I)


# ══════════════════════════════════════════════════════════════════════
# TARGET EXTRACTION
# ══════════════════════════════════════════════════════════════════════

def _strip_to_host(token: str) -> str:
    """URL / host:port / user@host / raw host  →  bare host.

    Mirrors engage._host_of so the gate and `scope_check` agree on what a host
    is; divergence between the two would be a bypass.
    """
    t = (token or "").strip()
    if not t:
        return ""
    m = _SCHEME_RE.match(t)
    if m:
        t = m.group(2)
    t = t.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if "@" in t:
        t = t.rsplit("@", 1)[1]
    if t.startswith("["):                      # [::1]:8080
        mm = re.match(r"^\[([^\]]+)\]", t)
        return (mm.group(1) if mm else t).strip().lower()
    if t.count(":") == 1:                      # host:port
        head, tail = t.split(":", 1)
        if tail.isdigit() or tail == "":
            t = head
    return t.strip().lower().rstrip(".")


def _looks_like_target(token: str) -> bool:
    """Is this argv token a network target rather than a file/flag/value?"""
    t = (token or "").strip()
    if not t or t.startswith("-"):
        return False
    if _SCHEME_RE.match(t):
        return True

    host = _strip_to_host(t)
    if not host:
        return False

    # bare IP or CIDR
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    if "/" in t.split("?", 1)[0]:
        try:
            ipaddress.ip_network(t.split("/")[0] + "/" + t.split("/")[1],
                                 strict=False)
            return True
        except (ValueError, IndexError):
            pass

    # an existing path is a file, not a host
    if t.startswith(("/", "./", "../", "~")) or os.sep in t:
        return False
    if os.path.exists(t):
        return False

    if not _HOSTNAME_RE.match(host):
        return False
    tld = host.rstrip(".").rsplit(".", 1)[-1].lower()
    if tld in _FILE_EXTS:
        return False
    if tld.isdigit():                     # 192.168.1 style partials
        return False
    if len(tld) < 2:
        return False
    return True


class Extraction:
    """What a command will touch, as far as we can tell statically."""

    __slots__ = ("targets", "uncertain", "tools", "reason")

    def __init__(self) -> None:
        self.targets: List[str] = []
        self.uncertain: List[str] = []   # e.g. `nmap -iL hosts.txt`
        self.tools: List[str] = []
        self.reason: str = ""

    @property
    def is_active(self) -> bool:
        return bool(self.tools)

    def as_dict(self) -> Dict[str, Any]:
        return {"targets": sorted(set(self.targets)),
                "uncertain": sorted(set(self.uncertain)),
                "tools": sorted(set(self.tools)), "reason": self.reason}


def _extract_from_argv(argv: List[str], out: Extraction) -> None:
    if not argv:
        return
    tool = _base(argv[0]).lower()

    # step past leading env assignments:  FOO=bar nmap ...
    idx = 0
    while idx < len(argv) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", argv[idx]):
        idx += 1
    if idx >= len(argv):
        return
    tool = _base(argv[idx]).lower()

    # proxychains nmap ... → the real tool is the next word
    while tool in ("proxychains", "proxychains4", "sudo", "doas", "time",
                   "nohup", "stdbuf", "timeout") and idx + 1 < len(argv):
        idx += 1
        nxt = argv[idx]
        if nxt.startswith("-") or re.match(r"^\d+[smhd]?$", nxt):
            continue
        tool = _base(nxt).lower()

    if tool not in _NETWORK_TOOLS:
        return
    out.tools.append(tool)

    target_flags = ((_TARGET_FLAGS | _TOOL_TARGET_FLAGS.get(tool, set()))
                    - _TOOL_NON_TARGET_FLAGS.get(tool, set()))
    rest = argv[idx + 1:]
    i = 0
    while i < len(rest):
        tok = rest[i]

        if tok.startswith("-"):
            flag, inline = (tok.split("=", 1) + [None])[:2]

            if flag in _TARGET_FILE_FLAGS and flag not in target_flags:
                out.uncertain.append(inline if inline else
                                     (rest[i + 1] if i + 1 < len(rest) else flag))
                i += 1 if inline else 2
                continue

            if flag in target_flags:
                val = inline if inline is not None else (
                    rest[i + 1] if i + 1 < len(rest) else "")
                for piece in re.split(r"[,\s]+", val or ""):
                    if piece and _looks_like_target(piece):
                        out.targets.append(_strip_to_host(piece))
                    # A target flag whose value is NOT host-shaped is almost
                    # always an overloaded short flag (`smbmap -u guest`,
                    # `crackmapexec -u admin` — username, not URL). Ignoring it
                    # is safe: if the command genuinely had no extractable
                    # target, the `no_target` branch still refuses. Marking it
                    # uncertain instead blocked legitimate AD tooling.
                i += 1 if inline is not None else 2
                continue

            if flag in _VALUE_FLAGS_NOT_TARGET:
                if inline is not None:
                    i += 1
                    continue
                # We cannot know from the flag alone whether it takes a value:
                # curl's -s is boolean, nmap's -p is not. Blindly eating the
                # next token means `curl -s https://evil.com` loses its target
                # entirely — a silent BYPASS, not just a UX wart. So peek: if
                # the next token looks like a target, leave it for the main
                # loop. Over-collecting fails closed; under-collecting does not.
                nxt = rest[i + 1] if i + 1 < len(rest) else ""
                i += 1 if (nxt and _looks_like_target(nxt)) else 2
                continue

            i += 1
            continue

        if _looks_like_target(tok):
            out.targets.append(_strip_to_host(tok))
        i += 1


def extract_targets(command: str) -> Extraction:
    """Every network target `command` will touch, plus anything unknowable.

    Recurses into `sh -c "..."` exactly like the catastrophic gate, so wrapping
    a scan in a shell does not launder it past the boundary.
    """
    out = Extraction()
    if not command or not command.strip():
        return out
    try:
        norm = _normalize(command)
        for sub in _split_subcommands(norm):
            argv = _argv(sub)
            if argv is None:
                # unparseable: if it smells network-active, force uncertainty
                low = sub.lower()
                for t in _NETWORK_TOOLS:
                    if re.search(rf"\b{re.escape(t)}\b", low):
                        out.tools.append(t)
                        out.uncertain.append("<unparseable command>")
                        out.reason = "command could not be tokenised"
                        break
                continue
            if not argv:
                continue

            # `sh -c "<payload>"` → the payload is another command line, so
            # recurse into it. Without this, wrapping any scan in a shell walks
            # straight past the boundary.
            b = _base(argv[0]).lower()
            if b in _SHELLS:
                payload = None
                for j in range(1, len(argv) - 1):
                    if argv[j] == "-c":
                        payload = argv[j + 1]
                        break
                if payload:
                    inner = extract_targets(payload)
                    out.targets.extend(inner.targets)
                    out.uncertain.extend(inner.uncertain)
                    out.tools.extend(inner.tools)
                    continue

            # `python3 -c "...os.system('nmap 8.8.8.8')..."` — we are not going
            # to statically evaluate arbitrary code, so if inline source even
            # mentions a network tool, refuse rather than reason about it.
            if b in _INTERPRETERS:
                flags = _INLINE_FLAGS.get(b, ("-c",))
                payload = None
                for j in range(1, len(argv) - 1):
                    if argv[j] in flags:
                        payload = argv[j + 1]
                        break
                if payload:
                    low = payload.lower()
                    for t in _NETWORK_TOOLS:
                        if re.search(rf"\b{re.escape(t)}\b", low):
                            out.tools.append(t)
                            out.uncertain.append(
                                f"<inline {b} code invoking {t}>")
                            break
                    continue
            _extract_from_argv(argv, out)
    except Exception as e:  # never let the extractor crash the gate
        out.uncertain.append("<extractor error>")
        out.reason = f"extractor error: {type(e).__name__}"
    return out


# ══════════════════════════════════════════════════════════════════════
# THE BOUNDARY
# ══════════════════════════════════════════════════════════════════════

_LOOPBACK_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost"}


def _is_loopback(host: str) -> bool:
    if host in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _match_rule(host: str, rule: str) -> bool:
    """Identical semantics to engage._match_one — kept in lockstep."""
    rule = (rule or "").strip().lower().rstrip(".")
    if not rule or not host:
        return False
    if "/" in rule:
        try:
            net = ipaddress.ip_network(rule, strict=False)
            try:
                return ipaddress.ip_address(host) in net
            except ValueError:
                return False
        except ValueError:
            pass
    try:
        ipaddress.ip_address(rule)
        return host == rule
    except ValueError:
        pass
    if host == rule or host.endswith("." + rule):
        return True
    if rule.startswith("*."):
        bare = rule[2:]
        return host == bare or host.endswith("." + bare)
    return False


def _window_open(state: Dict[str, Any], now: Optional[datetime] = None
                 ) -> Tuple[bool, str]:
    """Is `now` inside the engagement's authorised testing window?"""
    win = state.get("window") or {}
    if not win:
        return True, ""
    now = now or datetime.now(timezone.utc)

    def _parse(v: str) -> Optional[datetime]:
        try:
            d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except Exception:
            return None

    start, end = _parse(win.get("start", "")), _parse(win.get("end", ""))
    if start and now < start:
        return False, f"engagement window has not opened (starts {start.isoformat()})"
    if end and now > end:
        return False, f"engagement window closed at {end.isoformat()}"
    return True, ""


def check_command(command: str, state: Optional[Dict[str, Any]] = None,
                  now: Optional[datetime] = None) -> Dict[str, Any]:
    """The authorisation decision for one command.  FAILS CLOSED.

    `state` is the engagement dict (scope / exclusions / window / allow_loopback).
    Returns {"allowed": bool, "active": bool, ...}.  A passive command is always
    allowed and never inspected further.
    """
    ext = extract_targets(command)
    verdict: Dict[str, Any] = {"allowed": True, "active": ext.is_active,
                               "extraction": ext.as_dict()}
    if not ext.is_active:
        verdict["reason"] = "passive/local command — scope boundary not engaged"
        return verdict

    state = state or {}
    scope = [str(s).strip().lower() for s in (state.get("scope") or []) if str(s).strip()]
    exclusions = [str(s).strip().lower() for s in
                  (state.get("exclusions") or []) if str(s).strip()]
    allow_loopback = state.get("allow_loopback", True)

    ok, why = _window_open(state, now)
    if not ok:
        verdict.update(allowed=False, reason=why, failure="window")
        return verdict

    targets = sorted(set(ext.targets))
    uncertain = sorted(set(ext.uncertain))

    if uncertain:
        verdict.update(
            allowed=False, failure="uncertain",
            reason=("cannot statically determine every target this command will "
                    "touch (%s) — refusing rather than guessing. Name the hosts "
                    "explicitly, or scope_set them and re-run."
                    % ", ".join(uncertain[:4])))
        return verdict

    if not targets:
        verdict.update(
            allowed=False, failure="no_target",
            reason=("an active tool (%s) was invoked but no target could be "
                    "extracted; refusing rather than firing blind."
                    % ", ".join(sorted(set(ext.tools)))))
        return verdict

    excluded = [t for t in targets
                if any(_match_rule(t, r) for r in exclusions)]
    if excluded:
        verdict.update(
            allowed=False, failure="excluded", excluded=excluded,
            reason=("target(s) %s are on the engagement's EXCLUSION list — "
                    "explicitly carved out of the rules of engagement. "
                    "Exclusions override scope; this does not run."
                    % ", ".join(excluded)))
        return verdict

    unauthorised = []
    for t in targets:
        if allow_loopback and _is_loopback(t):
            continue
        if not any(_match_rule(t, r) for r in scope):
            unauthorised.append(t)

    if unauthorised:
        verdict.update(
            allowed=False, failure="out_of_scope", out_of_scope=unauthorised,
            reason=(("no authorised scope is set for this engagement, so every "
                     "remote target is out of scope (fail-closed): %s"
                     if not scope else
                     "target(s) %s are NOT in the authorised scope")
                    % ", ".join(unauthorised)),
            hint=("If you are authorised to test these, record it with "
                  "scope_set and re-run. Scope is the authorisation boundary; "
                  "it is not bypassable from the model side."))
        return verdict

    verdict["reason"] = "all targets within authorised scope"
    verdict["targets"] = targets
    return verdict


def load_state(engagement: str = "default",
               base_dir: Optional[Any] = None) -> Dict[str, Any]:
    """Read engagement state via engage._load so there is ONE schema."""
    try:
        from basilisk_ext import engage as _eng
        return _eng._load(engagement, base_dir)
    except Exception:
        return {}


def enforce(command: str, engagement: str = "default",
            base_dir: Optional[Any] = None,
            now: Optional[datetime] = None) -> Dict[str, Any]:
    """Convenience wrapper used by the execution primitive."""
    return check_command(command, load_state(engagement, base_dir), now=now)
