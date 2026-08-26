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
    "sftp", "ftp", "rsync", "openvpn",
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

# Flags that are BOOLEAN for a specific tool even though they are value-taking
# elsewhere. Flag arity is per-tool, and a flag mis-classed as value-taking is
# a BYPASS: it swallows the token after it, so an out-of-scope target sitting
# in that position is silently dropped and the command sails through on the
# in-scope operand beside it.
#
#   curl -i evil.com acme.com
#
# `-i` is --include (a boolean: show response headers) on curl and wget, but
# --identity (a keyfile, value-taking) on ssh/scp/sftp — so it lives in
# _VALUE_FLAGS_NOT_TARGET for the ssh case and ate `evil.com` on curl, exactly
# the laundering the bare-hostname note downstream fixed for positionals,
# reached through a flag. Resolve it by TOOL rather than by widening the set.
_TOOL_BOOLEAN_FLAGS: Dict[str, Set[str]] = {
    "curl": {"-i", "--include"},
    "wget": {"-i"},   # wget -i is actually an input-file flag; see note below
}
# NB wget's real `-i` IS a targets FILE (--input-file), which is 'uncertain',
# not boolean — but treating it as boolean here would UNDER-collect. wget is
# excluded from the boolean override and handled by the target-file path; only
# curl's -i is a true boolean. Keep the map honest:
_TOOL_BOOLEAN_FLAGS.pop("wget", None)

# Flags that take NO value. This set exists because flag arity cannot be
# guessed: `curl -s https://evil.com` and `nmap -p 80 host` look identical to a
# parser that does not know `-s` is boolean and `-p` is not. Getting it wrong in
# the boolean direction is a BYPASS — the flag eats the target and the command
# sails through — so the common no-value flags are enumerated explicitly.
_BOOLEAN_FLAGS: Set[str] = {
    # curl / wget
    "-s", "-S", "-k", "-L", "-I", "-v", "-f", "-g", "-N", "-q", "-4", "-6",
    "--silent", "--insecure", "--location", "--head", "--verbose", "--fail",
    "--compressed", "--no-check-certificate", "--globoff",
    # nmap
    "-Pn", "-sV", "-sC", "-sS", "-sT", "-sU", "-sn", "-A", "-O", "-v", "-vv",
    "-n", "-R", "-F", "--open", "--reason", "--traceroute", "-T0", "-T1",
    "-T2", "-T3", "-T4", "-T5",
    # nuclei / httpx / ffuf / gobuster
    "-silent", "-json", "-jsonl", "-nc", "-no-color", "-stats", "-follow-redirects",
    "-status-code", "-title", "-tech-detect", "-probe", "-ip", "-cdn",
    "--recursion", "-recursive", "-ac", "-r", "-D", "-fw",
    # sqlmap / hydra / general
    "--batch", "--random-agent", "--dbs", "--tables", "--dump", "--current-user",
    "--is-dba", "--forms", "--crawl", "-V", "-h", "--help", "--version",
}

# Flags whose VALUE is definitively NOT a target (wordlists, output files,
# ports, threads…).  Skipping these kills most false positives.
_VALUE_FLAGS_NOT_TARGET: Set[str] = {
    "-w", "--wordlist", "-o", "-oN", "-oX", "-oG", "-oA", "-oJ", "--output",
    "-p", "--ports", "--port", "-P", "--passwords", "--password",
    "-T", "--threads", "-c", "--cookie", "-b", "--data", "--data-raw",
    "-A", "--user-agent", "--rate", "-m", "--method",
    "--key", "-i", "--identity", "--format", "-j",
    "--timeout", "--retries", "--delay", "--resolvers",
    "-mc", "-fc", "-ms", "-fs", "-mr", "-fr", "-recursion-depth",
    "--severity", "--tags", "--templates", "-tags", "-severity", "-t",
    "--level", "--risk", "--technique", "--dbms", "-e", "-x",
}

# Flags that name a FILE full of targets — statically unknowable, so uncertain.
# Flags whose VALUE is a file of targets ("read the hosts from here"), which
# the gate cannot resolve statically and must therefore treat as uncertain.
#
# `-f` IS DELIBERATELY ABSENT. It was here, and it is also in _BOOLEAN_FLAGS,
# and the file branch is tested first — so `-f` swallowed the token after it on
# every tool where it is an ordinary boolean:
#
#     curl -f https://acme.com/health   -> REFUSED (uncertain)
#     nmap -f acme.com                  -> REFUSED (uncertain)
#     gobuster dir -f -u http://acme.com -w w.txt -> `-f` ate `-u`
#
# Those are in-scope, everyday commands. `-f` means --fail on curl, fragment
# packets on nmap, and force on a dozen other tools; it means "targets file"
# on almost nothing. A gate that refuses ordinary work is a gate the operator
# switches off, and then it protects nothing at all — so the false-refusal
# cost here is a SECURITY cost, not a convenience one.
#
# The real target-file flags below are unambiguous.
_TARGET_FILE_FLAGS: Set[str] = {
    "-iL", "--input-list", "-il", "--file", "--targets-file",
    "--target-file", "--hosts-file", "--host-list",
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

# Commands that PREFIX a real command rather than being one. `env FOO=1 nmap`
# looked like an invocation of `env` and sailed straight past the boundary
# until this list grew; the backstop below exists because this list will never
# be complete.
_WRAPPERS: Set[str] = {
    "sudo", "doas", "su", "runuser", "env", "time", "timeout", "nohup",
    "stdbuf", "unbuffer", "setsid", "nice", "ionice", "chrt", "taskset",
    "proxychains", "proxychains4", "torsocks", "firejail", "bwrap",
    "flatpak-spawn", "command", "exec", "busybox", "watch", "xargs",
    "script", "eatmydata", "systemd-run", "ssh-agent",
}
# Wrapper flags that consume the following token, so it is not the real command.
_WRAPPER_VALUE_FLAGS: Set[str] = {
    "-u", "--user", "-g", "--group", "-n", "-c", "--command", "-C", "--chdir",
    "-S", "--split-string", "-p", "--policy", "-k", "--kill-after", "-s",
    "--signal", "-N", "--name", "-a", "-l",
}
# Commands that legitimately take a scanner's NAME as an argument without
# running it. Without this exemption the backstop would refuse `apt install
# nmap` and `which nuclei`, which the agent does constantly during tooling_check.
_TOOL_NAME_CONSUMERS: Set[str] = {
    "which", "whereis", "type", "hash", "command", "man", "info", "whatis",
    "apt", "apt-get", "apt-cache", "apt-mark", "apt-file", "aptitude",
    "dpkg", "dpkg-query", "dnf", "yum", "rpm", "rpm-ostree", "pacman",
    "pkg", "xbps-query", "xbps-install", "equery", "eix", "nix", "nix-env",
    "guix", "conda", "poetry", "uv", "asdf", "mise", "update-alternatives",
    "yay", "paru", "zypper", "apk", "brew", "port", "emerge", "snap",
    "flatpak", "pip", "pip3", "pipx", "npm", "yarn", "gem", "cargo", "go",
    "echo", "printf", "cat", "grep", "rg", "ag", "ls", "stat", "file",
    "systemctl", "service", "journalctl",
    "test", "wc", "head", "tail", "sed", "awk",
}

# ── HEADS THAT MENTION A TOOL *AND* RUN IT ───────────────────────────
# The set above exists so `which nmap` and `apt install nmap` are not read as
# a scan: they NAME a tool without running it, so the unattributed-tool
# backstop must not fire. `find`, `docker`, `podman`, `kubectl`, `git`, `make`
# and `go` were in that set too — and they EXECUTE what follows:
#
#     find . -exec nmap 8.8.8.8 \;                       -> was ALLOWED
#     docker run --rm kalilinux/kali nmap -sS 8.8.8.8    -> was ALLOWED
#     sudo find . -exec masscan 198.51.100.0/24 \;       -> was ALLOWED
#
# Being on the introspection list skipped BOTH the quoted-argument recursion
# and the backstop, so the scan was invisible to the gate. Judge these on
# their arguments like any other command.
# bash/ksh socket redirection: /dev/tcp/<host>/<port> and /dev/udp/…
_DEV_SOCKET_RE = re.compile(
    r"/dev/(?:tcp|udp)/([^/\s'\"|;&>()]+)/\d+")

_TOOL_NAME_EXECUTORS: Set[str] = {
    "find", "docker", "podman", "kubectl", "git", "make", "cmake", "go",
    "nix-shell", "distrobox", "toolbox", "chroot", "ip", "ssh",
}
_TOOL_NAME_CONSUMERS -= _TOOL_NAME_EXECUTORS

# ── awk AND sed BELONG IN BOTH SETS, DEPENDING ON THE PROGRAM ────────
# They were left on the introspection list when find/docker/git were moved
# off it, and they execute just as happily:
#
#     awk 'BEGIN{system("nmap -sS 8.8.8.8")}'     -> was ALLOWED, tools=[]
#     sed 's/x/y/e' file                          (GNU sed runs the result)
#
# Membership in _TOOL_NAME_CONSUMERS short-circuits BOTH the quoted-argument
# recursion and the unattributed-tool backstop, so the scan was invisible.
#
# Moving them wholesale would be the wrong trade: `sed 's/nmap/x/' notes.txt`
# and `awk '{print $1}' scan.txt` are ordinary text processing that names a
# tool without running anything, and blocking those is exactly the
# over-blocking this module's counter-property corpus forbids. So the decision
# is made on the PROGRAM TEXT: only the forms that can actually spawn a
# process are treated as executors.
# awk executes a process three ways, and ONLY these three.  An earlier draft
# of this pattern matched a pipe character next to a quote, which made
# `awk 'BEGIN{FS="|"}{print $2}'` — setting the field separator to a pipe, the
# single most common awk idiom in this codebase's own corpus — read as an
# executor.  A false refusal on ordinary text processing is the failure this
# module's counter-property corpus exists to catch, so the pipe forms are
# matched as OPERATORS (output redirect into a command, or command-into-
# getline), never as a character that happens to sit beside a quote.
_AWK_EXEC_RE = re.compile(
    r"""system\s*\("""                      # system("...")
    r"""|\bprintf?\b[^;}\n]*\|"""           # print ... | "cmd"
    r"""|\|\s*&?\s*getline\b""",            # "cmd" | getline  /  co-process
    re.S)

# GNU sed executes two ways: the `e` FLAG on s///, and the `e` COMMAND.
#   s/x/y/e          run the whole pattern space after substituting
#   1e ls    /x/e c  run the given command (or the pattern space, bare `e`)
# The command form takes an optional address, so it is anchored at the start of
# a script or just after a `;` separator — anchoring on whitespace alone made
# `sed '1e ls'` invisible while `sed 's/end/END/' notes.md` stayed clean only
# by luck of spacing.
_SED_EXEC_RE = re.compile(
    r"""s([^\w\s])(?:[^\\]|\\.)*?\1(?:[^\\]|\\.)*?\1[a-df-z]*e"""
    r"""|(?:^|;)\s*(?:\d+(?:\s*,\s*(?:\d+|\$))?|\$|/(?:[^/\\]|\\.)*/)?\s*e(?:\s|$|;)""",
    re.S)

# `-e PROG` arrives as its own shlex token, but `--expression=PROG` does not:
# the program text is glued to a flag name, which defeats an anchored match.
_SED_LONG_EXPR_RE = re.compile(r"^--(?:e|ex|exp|expr|expre|expres|express|"
                               r"expressi|expressio|expression)=", re.I)


def _awk_sed_executes(argv: List[str]) -> bool:
    """True when an awk/sed invocation can spawn a process."""
    if not argv:
        return False
    head = os.path.basename((argv[0] or "").strip().strip("'\""))
    if head.endswith("awk") or head in ("awk", "gawk", "mawk", "nawk", "busybox"):
        rx = _AWK_EXEC_RE
    elif head in ("sed", "gsed"):
        rx = _SED_EXEC_RE
    else:
        return False
    for a in argv[1:]:
        a = a or ""
        if rx is _SED_EXEC_RE:
            a = _SED_LONG_EXPR_RE.sub("", a)
        if rx.search(a):
            return True
    return False

# Wrappers whose -c/--command argument is a COMMAND STRING to execute, so it
# must be recursed into exactly like a shell's. `su -c 'nmap 8.8.8.8' root`
# otherwise consumed the payload as an inert flag value and allowed the scan.
_CMD_STRING_WRAPPERS: Set[str] = {"su", "runuser", "script", "systemd-run",
                                  "flatpak-spawn", "watch"}

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
    # ── KEEP A CIDR PREFIX ──
    # The `/` split below exists to drop a URL PATH, and it was also eating the
    # prefix length of a NETWORK: `10.0.0.0/8` became `10.0.0.0`, so the gate
    # judged a 16-million-host sweep as a single address. With scope
    # 10.0.0.0/24 that made `nmap -sS 10.0.0.0/8` ALLOWED — and made
    # `nmap 10.0.0.0/24` allowed while the single host `10.0.0.1` inside it was
    # correctly EXCLUDED, so an exclusion could be swept just by naming the
    # range around it. Both directions are exactly what this gate exists to
    # prevent.
    try:
        ipaddress.ip_network(t, strict=False)
        return t.strip().lower()               # a real network — prefix kept
    except ValueError:
        pass
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

    # A path-shaped token is a file, not a host.
    #
    # NOTE: this deliberately does NOT stat the filesystem. An earlier version
    # called os.path.exists(t) here, which meant `touch evil.com && nmap
    # 10.0.0.5 evil.com` silently dropped evil.com from the extracted set and
    # the command was ALLOWED on the strength of the in-scope IP alone. An
    # authorisation decision must be a pure function of the command string —
    # the moment it depends on mutable disk state, anything that can create a
    # file can move the boundary.
    # A PATH is a file. `host/path` is a HOST.
    #
    # `os.sep in t` treated every token containing a "/" as a filename, so a
    # scheme-less URL vanished from the extracted set entirely:
    #
    #     curl acme.com evil.com/admin   -> targets ['acme.com'] -> ALLOWED
    #
    # …and curl fetches BOTH. One in-scope operand laundered an out-of-scope
    # one. The distinction that matters is where the slash is: a token that
    # STARTS with a path prefix is a path, and so is one whose first segment
    # is not host-shaped. `evil.com/admin` is neither.
    if t.startswith(("/", "./", "../", "~")):
        return False
    if os.sep in t:
        first = t.split("/", 1)[0]
        # No dot in the first segment (and not an IP) => a relative path like
        # `wordlists/big.txt`, not a host.
        if "." not in first:
            return False
        if not _HOSTNAME_RE.match(first.rstrip(".")):
            try:
                ipaddress.ip_address(first)
            except ValueError:
                return False
        # first segment IS host-shaped — fall through and judge it as a host.

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


def _is_strong_target(token: str) -> bool:
    """Unmistakably a network target: explicit scheme, bare IP, or CIDR.

    Deliberately narrower than _looks_like_target — used only to stop a
    value-flag from swallowing something that obviously is a host.
    """
    t = (token or "").strip()
    if not t or t.startswith("-"):
        return False
    if _SCHEME_RE.match(t):
        return True
    host = _strip_to_host(t)
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    try:
        ipaddress.ip_network(t, strict=False)
        return "/" in t
    except ValueError:
        return False


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


def _resolve_command(argv: List[str]) -> Tuple[str, int]:
    """Peel wrappers/env-assignments off the front and return (tool, index).

    `sudo -u root nmap`, `env FOO=1 nmap`, `timeout 1.5 nmap`, `nice -n 10 nmap`
    all resolve to nmap. Returns ("", -1) if nothing command-shaped is found.
    """
    idx = 0
    n = len(argv)
    guard = 0
    while idx < n and guard < 40:
        guard += 1
        tok = argv[idx]
        # VAR=value assignments (bare, or arguments to `env`)
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tok):
            idx += 1
            continue
        name = _base(tok).lower()
        if name in _WRAPPERS:
            idx += 1
            # consume this wrapper's own flags and their values
            while idx < n:
                a = argv[idx]
                if a.startswith("-"):
                    flag = a.split("=", 1)[0]
                    if "=" in a:
                        idx += 1
                    elif flag in _WRAPPER_VALUE_FLAGS:
                        idx += 2
                    else:
                        idx += 1
                    continue
                # a bare duration for timeout/watch/sleep-like wrappers
                if re.match(r"^\d+(\.\d+)?[smhd]?$", a):
                    idx += 1
                    continue
                break
            continue
        if idx < n:
            return name, idx
        break
    return ("", -1)


# Tools whose POSITIONAL arguments are host specifications and nothing else.
# Used to decide whether a leftover positional that does not parse as a target
# is a dropped host or an ordinary operand (a protocol word, a module name).
# Kept deliberately short. The first draft of this set included dig, amass and
# wpscan, and the counter-property corpus immediately refused `dig acme.com A`,
# `amass enum -d acme.com` and `wpscan --url ... --enumerate u` -- the record
# type, the subcommand and the enumeration mode are all positional words that
# are not hosts. Only tools whose positional grammar is "one or more host
# specifications, full stop" belong here.
_HOST_ONLY_POSITIONALS: Set[str] = {
    "nmap", "masscan", "naabu", "rustscan", "zmap", "unicornscan", "fping",
    "hping3", "arp-scan", "netdiscover", "traceroute", "tracepath", "ping",
    "ping6", "sslscan", "whatweb", "wafw00f",
}

# One DNS label: no dot, no slash, no scheme. `dc01`, `fileserver`, `web-01`.
_BARE_LABEL_RE = re.compile(r"^(?![-_])[A-Za-z0-9_-]{1,63}(?<![-_])$")


# ── DESTINATION-REDIRECT FLAGS ──
# Some flags override where a command ACTUALLY connects, independent of the
# hostname the operator typed. The gate keyed off the visible hostname, so
#
#     curl --resolve acme.com:443:8.8.8.8 https://acme.com
#     curl --connect-to acme.com:443:8.8.8.8:443 https://acme.com
#     ssh -o ProxyCommand='nc 8.8.8.8 22' acme.com
#     ssh -o ProxyJump=8.8.8.8 acme.com
#
# all sailed through on the in-scope `acme.com` while the packets went to
# 8.8.8.8. The redirect endpoint is the real target and MUST be scoped. Each
# flag's value carries the endpoint in a known position, so it is extractable.
_REDIRECT_FLAGS: Set[str] = {
    "--resolve", "--connect-to",     # curl
    "-o",                            # ssh -o ProxyCommand=/ProxyJump=
    "-J", "--proxy-jump",            # ssh short/long ProxyJump
    "--proxy",                       # curl --proxy host:port
    "-x",                            # curl -x proxy (also sqlmap; host-shaped only)
}


def _redirect_targets(flag: str, value: str) -> List[str]:
    """Pull the real destination host(s) out of a redirect flag's value.

    Fails toward EXTRACTING: an endpoint we cannot confidently parse is still
    surfaced when it is host-shaped, because a missed redirect is a scope
    bypass while a spurious one is only a fixable false refusal.
    """
    v = (value or "").strip().strip("'\"")
    if not v:
        return []
    out: List[str] = []

    if flag in ("--resolve", "--connect-to"):
        # host:port:ADDR  (--resolve)  or  host:port:ADDR:port (--connect-to)
        # The endpoint is the 3rd colon-field; a bracketed IPv6 may hold colons.
        parts = _split_hostport_triplet(v)
        # field 0 is the requested host (already scoped as the visible target),
        # the connect address is what actually gets dialed.
        for p in parts[2:]:
            if p and _looks_like_target(p):
                out.append(_strip_to_host(p))

    elif flag in ("-o",):
        # ssh -o KEY=VALUE. Only the destination-bearing keys matter.
        m = re.match(r"(?i)\s*(ProxyJump|ProxyCommand)\s*=?\s*(.*)$", v)
        if m:
            body = m.group(2).strip().strip("'\"")
            # ProxyJump: [user@]host[:port][,...]; ProxyCommand: a shell line
            # whose host tokens we harvest conservatively.
            for tok in re.split(r"[\s,]+", body):
                host = _redirect_host_token(tok)
                if host and _looks_like_target(host):
                    out.append(_strip_to_host(host))

    elif flag in ("-J", "--proxy-jump"):
        for tok in re.split(r"[\s,]+", v):
            host = _redirect_host_token(tok)
            if host and _looks_like_target(host):
                out.append(_strip_to_host(host))

    elif flag in ("--proxy", "-x"):
        host = _redirect_host_token(v)
        if host and _looks_like_target(host):
            out.append(_strip_to_host(host))

    return out


def _split_hostport_triplet(v: str) -> List[str]:
    """Split a curl --resolve/--connect-to value on ':' but keep a bracketed
    [IPv6] address whole."""
    parts: List[str] = []
    buf = ""
    depth = 0
    for ch in v:
        if ch == "[":
            depth += 1
            buf += ch
        elif ch == "]":
            depth = max(0, depth - 1)
            buf += ch
        elif ch == ":" and depth == 0:
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    parts.append(buf)
    return parts


def _redirect_host_token(tok: str) -> str:
    """Reduce a proxy/jump token ([user@]host[:port]) to its host."""
    t = (tok or "").strip().strip("'\"")
    if not t or t.startswith("-"):
        return ""
    if "@" in t:
        t = t.rsplit("@", 1)[1]
    # strip a trailing :port, but not the colons inside a bracketed IPv6
    if t.startswith("[") and "]" in t:
        return t[1:t.index("]")]
    if t.count(":") == 1:
        t = t.split(":", 1)[0]
    return t


def _extract_from_argv(argv: List[str], out: Extraction) -> None:
    if not argv:
        return
    raw_head = _base(argv[0]).lower()
    if (raw_head in _TOOL_NAME_CONSUMERS
            and not _awk_sed_executes(argv)) and (
            raw_head != "command" or any(a in ("-v", "-V") for a in argv[1:])):
        return          # `which nmap`, `apt install nuclei`, `command -v ffuf`
    tool, idx = _resolve_command(argv)
    if not tool or idx < 0 or tool not in _NETWORK_TOOLS:
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

            # DESTINATION-REDIRECT: harvest the real endpoint, then consume the
            # value like any other value-flag. This runs FIRST so the redirect
            # target is captured whether or not the flag also appears elsewhere.
            if flag in _REDIRECT_FLAGS:
                val = inline if inline is not None else (
                    rest[i + 1] if i + 1 < len(rest) else "")
                for host in _redirect_targets(flag, val):
                    out.targets.append(host)
                i += 1 if inline is not None else 2
                continue

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

            if flag in _BOOLEAN_FLAGS:
                i += 1
                continue

            # Per-tool boolean override: a flag that takes a value elsewhere but
            # is boolean for THIS tool (curl -i) must not swallow the next token.
            if flag in _TOOL_BOOLEAN_FLAGS.get(tool, set()):
                i += 1
                continue

            if flag in _VALUE_FLAGS_NOT_TARGET:
                if inline is not None:
                    i += 1
                    continue
                # Consume the value — but never swallow something unmistakably
                # a target (explicit scheme, bare IP, CIDR). That backstops a
                # flag mis-filed here as value-taking when it is really boolean;
                # without it, one wrong entry in the set above is a silent
                # bypass rather than a false positive.
                nxt = rest[i + 1] if i + 1 < len(rest) else ""
                i += 1 if (nxt and _is_strong_target(nxt)) else 2
                continue

            # Unknown flag: assume it takes no value. Over-collecting targets
            # fails CLOSED (a false refusal the operator can fix with
            # scope_set); under-collecting fails OPEN.
            i += 1
            continue

        if _looks_like_target(tok):
            out.targets.append(_strip_to_host(tok))
        elif (tool in _HOST_ONLY_POSITIONALS
              and _BARE_LABEL_RE.match(tok)
              and not (i > 0 and rest[i - 1].startswith("-"))):
            # SINGLE-LABEL HOSTS WERE DROPPED ON THE FLOOR.
            #
            #     nmap -sS acme.com dc01   ->  targets ['acme.com']  -> ALLOWED
            #
            # `dc01` has no dot, so _HOSTNAME_RE (which requires at least one)
            # rejected it and this walk skipped it in silence -- while nmap
            # resolves it perfectly well through the DNS search domain and
            # scans it. One in-scope operand laundered an unlisted host, which
            # is the same laundering the `evil.com/admin` note above fixed for
            # the dotted case, reached by a different door.
            #
            # It cannot be added to `targets`: a bare label has no
            # authoritative form to match a scope rule against (`dc01` may or
            # may not be `dc01.acme.com`). So it is UNCERTAIN -- the gate
            # refuses and tells the operator to name the host in full, which
            # is a fixable refusal rather than a silent scan.
            #
            # Two restrictions keep this from manufacturing false refusals.
            # First, the tool's positionals must be host specifications and
            # nothing else -- `hydra -l admin -P pw.txt 10.0.0.5 ssh` takes a
            # protocol word positionally. Second, the label must not sit
            # directly after a flag: an UNKNOWN flag is assumed above to take
            # no value, so `nmap -sV --script vuln 10.0.0.5` presents `vuln`
            # here as a positional when it is really --script's argument.
            # Escalating on an unknown flag's operand refused half the
            # ordinary nmap corpus; escalating on a label that follows a host
            # or another positional refuses none of it.
            out.uncertain.append(tok)
            out.reason = ("a single-label host (%s) cannot be matched against "
                          "the scope rules -- give it in full" % tok)
        i += 1


def _substitution_payloads(command: str) -> List[str]:
    """Inner text of every `$(...)` and backtick substitution.

    `echo $(nmap 8.8.8.8)` runs nmap. shlex hands back the token `$(nmap`,
    whose basename matches nothing, so neither the walk nor the backstop saw
    it. These spans are lifted out and re-parsed as commands in their own right.
    """
    UNTERMINATED = "\x00<unterminated substitution>"

    out: List[str] = []
    i, n = 0, len(command)
    while i < n:
        c = command[i]
        if c == "\\" and i + 1 < n:
            i += 2
            continue
        if c == "$" and i + 1 < n and command[i + 1] == "(":
            depth, j = 1, i + 2
            start = j
            while j < n and depth:
                if command[j] == "\\":
                    j += 2
                    continue
                if command[j] == "(":
                    depth += 1
                elif command[j] == ")":
                    depth -= 1
                j += 1
            if depth == 0:
                out.append(command[start:j - 1])
            else:
                # UNTERMINATED.  `$(nmap evil.com` with no closing paren.  A
                # real shell rejects this outright (syntax error), so it is
                # not an exploitable bypass -- but the scan below has just
                # CONSUMED the rest of the string, and the caller would grade
                # what is left as a passive/local command. That is a
                # fail-OPEN verdict reached by accident. Signal it instead
                # and let the caller refuse.
                out.append(UNTERMINATED)
                out.append(command[start:])
            i = j
            continue
        if c == "`":
            j = i + 1
            while j < n and command[j] != "`":
                if command[j] == "\\":
                    j += 2
                    continue
                j += 1
            if j < n:
                out.append(command[i + 1:j])
            else:
                # Same story for the legacy backtick form, which had the
                # extra wrinkle that a SINGLE leading backtick swallowed the
                # entire command.
                out.append(UNTERMINATED)
                out.append(command[i + 1:])
            i = j + 1
            continue
        i += 1
    return out


def extract_targets(command: str, _depth: int = 0) -> Extraction:
    """Every network target `command` will touch, plus anything unknowable.

    Recurses into `sh -c "..."` exactly like the catastrophic gate, so wrapping
    a scan in a shell does not launder it past the boundary.
    """
    out = Extraction()
    if not command or not command.strip() or _depth > 6:
        if _depth > 6:
            out.uncertain.append("<substitution nesting too deep>")
        return out
    try:
        norm = _normalize(command)

        # ── /dev/tcp AND /dev/udp: A CONNECTION WITH NO BINARY ──
        # The whole gate keys off recognising a network TOOL by its basename,
        # so bash's own socket redirection was invisible to it:
        #
        #     cat < /dev/tcp/evil.com/80          -> ALLOWED, and it connects
        #     exec 3<>/dev/tcp/evil.com/80        -> ALLOWED
        #     printf 'GET / HTTP/1.0\r\n\r\n' > /dev/tcp/evil.com/80
        #
        # There is no nmap, no curl, nothing to attribute — just a redirection
        # bash turns into a TCP connection. Matched on the raw string because
        # shlex hands the redirection back as an ordinary token and the host
        # sits inside the pseudo-path.
        for _m in _DEV_SOCKET_RE.finditer(norm):
            _h = _strip_to_host(_m.group(1))
            if _h:
                out.tools.append("bash-" + _m.group(0).split("/")[1])
                out.targets.append(_h)

        # Command substitutions execute independently of the line that contains
        # them — lift them out and parse each as its own command.
        for payload in _substitution_payloads(norm):
            if payload == "\x00<unterminated substitution>":
                out.uncertain.append("<unterminated substitution>")
                out.reason = ("command has an unterminated $( or backtick "
                              "substitution and cannot be parsed")
                continue
            if payload.strip():
                inner = extract_targets(payload, _depth + 1)
                out.targets.extend(inner.targets)
                out.uncertain.extend(inner.uncertain)
                out.tools.extend(inner.tools)

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
            if b in _SHELLS or b in _CMD_STRING_WRAPPERS:
                payload = None
                for j in range(1, len(argv) - 1):
                    if argv[j] in ("-c", "--command", "-qc"):
                        payload = argv[j + 1]
                        break
                if payload:
                    inner = extract_targets(payload, _depth + 1)
                    out.targets.extend(inner.targets)
                    out.uncertain.extend(inner.uncertain)
                    out.tools.extend(inner.tools)
                    continue

            # `python3 -c "...os.system('nmap 8.8.8.8')..."` — we are not going
            # to statically evaluate arbitrary code, so if inline source even
            # mentions a network tool, refuse rather than reason about it.
            if b in _INTERPRETERS:
                flags = _INLINE_FLAGS.get(b, ("-c",))
                # SHORT OPTIONS CLUSTER. `python3 -Bc "…"`, `-uc`, `-BOc` all
                # put the code where an exact-token match cannot see it, and
                # this gate then graded the command "passive/local" — the exact
                # fail-OPEN the module exists to prevent. Same defect and same
                # fix as _short_opt_payloads in basilisk_safety.
                letters = "".join(f[1:] for f in flags
                                  if len(f) == 2 and f.startswith("-"))
                payloads = []
                for j, a in enumerate(argv[1:], start=1):
                    if a in flags and j + 1 < len(argv):
                        payloads.append(argv[j + 1])
                        continue
                    if (letters and a.startswith("-")
                            and not a.startswith("--") and len(a) > 1):
                        body = a[1:]
                        hit = next((k for k, ch in enumerate(body)
                                    if ch in letters), None)
                        if hit is None:
                            continue
                        if hit < len(body) - 1:
                            payloads.append(body[hit + 1:])
                        if j + 1 < len(argv):
                            payloads.append(argv[j + 1])
                if payloads:
                    _hit = False
                    for payload in payloads:
                        low = (payload or "").lower()
                        for t in _NETWORK_TOOLS:
                            if re.search(rf"\b{re.escape(t)}\b", low):
                                out.tools.append(t)
                                out.uncertain.append(
                                    f"<inline {b} code invoking {t}>")
                                _hit = True
                                break
                        if _hit:
                            break
                    continue
            _before = len(out.tools)
            _extract_from_argv(argv, out)

            # ── BACKSTOP ────────────────────────────────────────────────
            # The structured walk above depends on recognising the wrapper
            # chain, and that recognition will never be complete — `env FOO=1
            # nmap 8.8.8.8` was allowed until `env` was added to _WRAPPERS, and
            # the next torsocks/firejail/chrt variant would have been too.
            #
            # So: if a network tool's name appears in a sub-command that the
            # walk could not attribute AT ALL, refuse. That turns every present
            # and future parsing gap from a SILENT BYPASS into a loud, fixable
            # refusal — the only safe direction for a gap in an authorisation
            # boundary.
            #
            # Only when the walk found nothing, though: `hydra -l admin -P
            # pw.txt 10.0.0.5 ssh` names ssh as a PROTOCOL argument to an
            # already-attributed tool, and second-guessing a successful parse
            # just manufactures false refusals.
            if len(out.tools) != _before:
                continue

            head, _hi = _resolve_command(argv)
            raw_head = _base(argv[0]).lower()
            # `command -v ffuf` is introspection; bare `command ffuf …` really
            # runs it. Check the raw head as well as the resolved one, or the
            # wrapper peel turns the former into an apparent ffuf invocation.
            introspective = (raw_head in _TOOL_NAME_CONSUMERS
                             and not _awk_sed_executes(argv)
                             and (raw_head != "command"
                                  or any(a in ("-v", "-V") for a in argv[1:])))
            # `head` is the RESOLVED command (after the wrapper peel), and it
            # was tested against the introspection list unguarded — so an awk
            # whose program spawns a process still short-circuited here even
            # though `introspective` had correctly gone False. Both disjuncts
            # need the executor guard, not just the raw-head one.
            if _awk_sed_executes(argv):
                introspective = False
            elif head in _TOOL_NAME_CONSUMERS or introspective:
                continue

            # ── awk/sed PROGRAM TEXT IS INLINE CODE ─────────────────────
            # Dropping awk and sed off the introspection list stopped them
            # short-circuiting the walk, but that alone changed no verdict:
            # the program text is a SINGLE shlex token whose basename is the
            # whole program, so neither the quoted-argument recursion (which
            # re-shlexes `BEGIN{system("nmap ...")}` into `BEGIN{system(nmap`)
            # nor the unattributed-name scan (which compares basenames) can
            # see the tool inside it.  Read it the same way an interpreter's
            # -c payload is read: search the text for a known network tool and
            # refuse as UNCERTAIN, because what a spawned process will
            # actually touch cannot be determined statically.
            if _awk_sed_executes(argv):
                _hit = False
                for tok in argv[1:]:
                    low = (tok or "").lower()
                    for t in _NETWORK_TOOLS:
                        if re.search(rf"\b{re.escape(t)}\b", low):
                            out.tools.append(t)
                            out.uncertain.append(
                                f"<{raw_head} program spawning {t}>")
                            out.reason = (
                                "an awk/sed program that can spawn a process "
                                "names a network tool; its real targets are "
                                "not statically determinable")
                            _hit = True
                            break
                    if _hit:
                        break
                if _hit:
                    continue
                # awk's system("...") argument is normally right there in the
                # program text, so the word scan above is enough for it. GNU
                # sed's `e` is not: it executes the PATTERN SPACE -- text
                # produced at run time from the input file -- so there is
                # nothing in the command string to scan and no way to know
                # what it will run. That is the definition of uncertain.
                if raw_head in ("sed", "gsed"):
                    out.tools.append("sed-e")
                    out.uncertain.append("<sed `e` executes generated text>")
                    out.reason = ("this sed script executes the text it "
                                  "produces; what it will touch cannot be "
                                  "determined from the command")
                    continue

            # Nothing was attributed, so a quoted argument may itself BE the
            # command: `watch -n1 'nmap 8.8.8.8'` passes the scan positionally
            # rather than behind -c, so neither the wrapper peel nor the name
            # scan below sees it (the shlex token is the whole string
            # "nmap 8.8.8.8", whose basename matches nothing).
            _recursed = False
            for tok in argv[1:]:
                if _depth <= 6 and (" " in tok or "\t" in tok):
                    inner = extract_targets(tok, _depth + 1)
                    if inner.tools:
                        out.targets.extend(inner.targets)
                        out.uncertain.extend(inner.uncertain)
                        out.tools.extend(inner.tools)
                        _recursed = True
            if _recursed:
                continue

            attributed = set(out.tools)
            for tok in argv:
                nm = _base(tok).lower()
                if nm in _NETWORK_TOOLS and nm not in attributed:
                    out.tools.append(nm)
                    out.uncertain.append(
                        f"<unattributed invocation of {nm}>")
                    out.reason = ("a known network tool appears in the command "
                                  "but could not be attributed to a parsed "
                                  "invocation")
                    break
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


def _as_network(t: str):
    """`t` as an ip_network, or None when it is not an address/range at all."""
    try:
        return ipaddress.ip_network((t or "").strip(), strict=False)
    except ValueError:
        return None


def _match_rule(host: str, rule: str) -> bool:
    """Is `host` AUTHORISED by `rule`?  Lockstep twin of engage._match_one.

    CONTAINMENT, not equality, whenever both sides are addresses or ranges.
    A target may be a whole network now that _strip_to_host keeps the prefix,
    and "the operator authorised 10.0.0.0/24" must NOT authorise a scan of
    10.0.0.0/8 that merely starts at the same address. Comparing IPs as
    STRINGS was wrong for the same reason: `2001:db8::1` and
    `2001:db8:0:0:0:0:0:1` are one host and compared unequal.
    """
    rule = (rule or "").strip().lower().rstrip(".")
    if not rule or not host:
        return False
    rnet, hnet = _as_network(rule), _as_network(host)
    if rnet is not None:
        # An address/range target is authorised only if it lies ENTIRELY
        # inside the authorised range.
        if hnet is None:
            return False
        return hnet.version == rnet.version and hnet.subnet_of(rnet)
    if hnet is not None:
        # Numeric target vs a hostname rule — never a match.
        return False
    if host == rule or host.endswith("." + rule):
        return True
    if rule.startswith("*."):
        bare = rule[2:]
        return host == bare or host.endswith("." + bare)
    return False


def _touches_rule(host: str, rule: str) -> bool:
    """Does `host` REACH anything covered by `rule`?  Used for EXCLUSIONS.

    Deliberately weaker than _match_rule: any overlap counts.  Authorisation
    asks "is all of this inside the permitted set" (containment); an exclusion
    asks "does any part of this hit the carve-out" (overlap).  Using the
    authorisation test for exclusions is what let a /24 sweep step over a
    single excluded address inside it.
    """
    rule = (rule or "").strip().lower().rstrip(".")
    if not rule or not host:
        return False
    rnet, hnet = _as_network(rule), _as_network(host)
    if rnet is not None and hnet is not None:
        return hnet.version == rnet.version and hnet.overlaps(rnet)
    if rnet is not None or hnet is not None:
        return False            # one numeric, one a name — no relation
    return _match_rule(host, rule)      # hostname semantics are unchanged


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

    # EXCLUSIONS USE OVERLAP, NOT CONTAINMENT.
    # _match_rule answers "is this target authorised BY this rule", which needs
    # containment. An exclusion asks the opposite question — "does this command
    # TOUCH the carved-out host" — and a range that merely overlaps an excluded
    # address touches it. With containment only, `nmap 10.0.0.0/24` sailed past
    # an exclusion of 10.0.0.1 that `nmap 10.0.0.1` was correctly refused for,
    # which is a carve-out anyone can step over by naming the range around it.
    excluded = [t for t in targets
                if any(_touches_rule(t, r) for r in exclusions)]
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
