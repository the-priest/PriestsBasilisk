"""
basilisk_safety.py — the hard, setting-independent safety floor for the auto-run
gate.

Basilisk runs with root on the operator's own box and, in its default low-friction
mode, executes a model-issued `run` command without a card click.  That speed
is the product — but it means exactly one class of mistake (a wiped disk, a
nuked filesystem, the immutable guardrail shell-stripped out of Basilisk's own
source) must be caught *before* it executes, no matter what the "confirm every
command" setting says.  These two predicates are that floor:

  • is_catastrophic_command — would this irreversibly destroy the system or its
    storage?
  • command_tampers_self    — would this write to Basilisk's own source, bypassing
    the guarded edit path (ast gate + immutable GUARDRAIL block)?

A True from either forces an explicit confirm dialog in basilisk.py's gate; it is
never silenced by a setting.

Why this is its own module, and why it is *structural* rather than a raw-string
regex.  A model ingests untrusted text (web pages, scan output, READMEs) that
can try to steer it, so the detector has to survive trivial obfuscation that a
naive substring/regex match misses:

    rm '-rf' /            # quoted flag
    rm${IFS}-rf${IFS}/    # $IFS instead of spaces
    cd / && rm -rf *      # the root target is in a *prior* sub-command
    find / -delete        # no `rm` token at all
    bash -c "rm -rf /"    # the real command is a -c payload
    echo x | base64 -d | sh   # opaque: we can't see what runs

The approach: normalize ($IFS → space), split on shell operators, shlex-tokenise
each sub-command (which strips quotes for free), recurse into `sh -c` / `eval`
payloads, and classify by the *resolved argv* — not by how the string looks.
The classifier is a strict SUPERSET of the old regex's catches (no safety
regression) and stays deliberately narrow: ordinary offensive-security work
(nmap, nuclei, sqlmap, hydra) and file ops in your own dirs (rm -rf ~/loot,
rm -rf ./build) do not trip it, so it adds no friction to real work.

Pure stdlib (shlex, re, os).  GTK-free and import-free of the rest of Basilisk, so
it is trivially unit-testable offline — see tests/test_basilisk.py.
"""

from __future__ import annotations

import os
import re
import shlex
from typing import List, Optional

# ── Targets that make a recursive delete / ownership change catastrophic ──
# First path component (after the leading /) that belongs to the system.  A
# recursive op whose target lands anywhere in one of these — at any depth — is
# force-confirmed.  This mirrors the directories the original backstop guarded
# (so coverage never regresses); `home` is intentionally absent here, exactly
# as before — a bare ~ / $HOME is caught separately, but /home/<user>/sub work
# stays quiet.
_CRITICAL_TOP = {
    "bin", "boot", "dev", "etc", "lib", "lib32", "lib64", "libx32",
    "proc", "root", "run", "sbin", "srv", "sys", "usr", "var",
}

# Top-level data / mount dirs whose DELETION (the directory itself) is
# catastrophic — /home wipes every user's data, /mnt and /media can wipe
# mounted disks — but whose SUBDIRECTORIES are fair game (rm -rf /home/me/loot
# is fine; rm -rf /home is not).  Matched exactly, not by prefix.
_CRITICAL_EXACT = {"/home", "/mnt", "/media", "/opt"}

# Block devices a raw write / wipe must never hit unattended.
_BLOCK_DEV_RE = re.compile(r"^/dev/(?:sd|nvme|mmcblk|vd|hd|loop|disk|xvd)")

# A shell redirection ( > or >> ) onto a block device — shlex eats the `>`
# operator, so this is matched against the raw (normalized) string instead.
_REDIR_BLOCKDEV_RE = re.compile(
    r">>?\s*['\"]?/dev/(?:sd|nvme|mmcblk|vd|hd|loop|disk|xvd)")

# Shell interpreters that, as a *pipe sink* or via `-c`, execute opaque input.
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "ash", "fish"}

# Fork bomb — syntactic, so a normalized-text match is the right tool.
_FORKBOMB_RE = re.compile(r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:")

# Decode-then-run chains (base64/hex/etc. piped onward to a shell).
_DECODERS = {"base64", "base32", "xxd", "uudecode"}


def _normalize(command: str) -> str:
    """Collapse the whitespace-obfuscation tricks that don't change meaning to
    the shell but defeat naive matching: ${IFS}, $IFS, ${IFS%??} → a space."""
    s = command
    s = re.sub(r"\$\{IFS[^}]*\}", " ", s)
    s = re.sub(r"\$IFS\b", " ", s)
    return s


def _split_subcommands(command: str) -> List[str]:
    """Split a command line into sub-commands on the shell operators that
    sequence them: ; && || | & newlines — and on the delimiters that OPEN a new
    command context: ( ) and backticks.  Quotes/escapes are respected so an
    operator *inside* a quoted string doesn't split.  Best-effort: on a
    tokenising failure we return the whole line as one piece (the caller still
    runs its regex fallback).

    Why ( ) and ` are separators and not ordinary characters.  Before v9.7.0
    they weren't, and the consequence was a verified fail-open: `( rm -rf / )`
    shlex-tokenised to ['(', 'rm', '-rf', '/', ')'], so argv[0] was '(' and the
    rm branch never ran.  Same for `$(rm -rf /)` and ``rm -rf /``.  Every one of
    those executes for real — checked against bash, not assumed.  A subshell or
    an unquoted command substitution IS a command boundary, so treating it as
    one is the structurally correct read, and it makes the three shapes fall
    out of the existing per-sub classifier with no new pattern matching.

    Substitutions inside DOUBLE quotes still run but must not be split here
    (the quote is load-bearing for the rest of the line) — those are lifted
    separately by _substitution_payloads and rescanned."""
    parts: List[str] = []
    buf: List[str] = []
    i, n = 0, len(command)
    quote: Optional[str] = None
    while i < n:
        c = command[i]
        if quote:
            buf.append(c)
            if c == quote:
                quote = None
            elif c == "\\" and quote == '"' and i + 1 < n:
                buf.append(command[i + 1]); i += 2; continue
            i += 1; continue
        if c in ("'", '"'):
            quote = c; buf.append(c); i += 1; continue
        if c == "\\" and i + 1 < n:
            buf.append(c); buf.append(command[i + 1]); i += 2; continue
        # two-char operators
        if command[i:i + 2] in ("&&", "||"):
            parts.append("".join(buf)); buf = []; i += 2; continue
        if c in (";", "|", "&", "\n", "(", ")", "`"):
            parts.append("".join(buf)); buf = []; i += 1; continue
        buf.append(c); i += 1
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def _substitution_payloads(command: str,
                           include_unterminated: bool = True) -> List[str]:
    """Lift the bodies of command substitutions — $( … ) and ` … ` — that the
    subcommand splitter can't reach because they sit inside DOUBLE quotes.

    `echo "$(rm -rf /)"` runs the rm.  The splitter respects double quotes (it
    has to — the quote governs the rest of the line), so without this the
    payload is never classified.  Single-quoted text is skipped: there the
    characters are literal and nothing executes.

    An UNTERMINATED substitution is a bash syntax error and never executes, so
    it is not an escape — but the same shape was a genuine fail-open in
    basilisk_scope (v7.9.4, where the scanner swallowed the rest of the line and
    then dropped it).  So the tail after an unterminated opener is returned as a
    payload too: scanning text that will never run costs nothing, while
    dropping text that might is exactly the accident this gate exists to avoid.
    """
    out: List[str] = []
    i, n = 0, len(command)
    sq = False
    while i < n:
        c = command[i]
        if c == "\\" and not sq and i + 1 < n:
            i += 2
            continue
        if c == "'":
            sq = not sq
            i += 1
            continue
        if sq:
            i += 1
            continue
        if c == "$" and i + 1 < n and command[i + 1] == "(":
            j, depth, inner_q = i + 2, 1, None
            while j < n and depth:
                ch = command[j]
                if ch == "\\" and inner_q != "'" and j + 1 < n:
                    j += 2
                    continue
                if inner_q:
                    if ch == inner_q:
                        inner_q = None
                elif ch in ("'", '"'):
                    inner_q = ch
                elif ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                j += 1
            if depth:                      # unterminated — scan the tail anyway
                if include_unterminated:
                    out.append(command[i + 2:])
                break
            out.append(command[i + 2:j - 1])
            i = j
            continue
        if c == "`":
            j = command.find("`", i + 1)
            if j < 0:
                if include_unterminated:
                    out.append(command[i + 1:])
                break
            out.append(command[i + 1:j])
            i = j + 1
            continue
        i += 1
    return [p for p in (s.strip() for s in out) if p]


# Tokens that are shell STRUCTURE, not a command.  When one of these leads a
# sub-command the real command is behind it: `{ rm -rf /; }` splits to
# ['{', 'rm', ...] and `if true; then rm -rf /; fi` to ['then', 'rm', ...].
# Judging argv[0] without stripping these read the command name as '{' / 'then'
# and let both shapes through (verified executing in bash).
_STRUCT_TOKENS = {
    "{", "}", "!", "if", "then", "else", "elif", "fi",
    "while", "until", "do", "done", "for", "select",
    "case", "esac", "in", "function", ";;",
}
# `f(){` — a function header that survived tokenising as one word.
_FUNCDEF_RE = re.compile(r"^[A-Za-z_]\w*\(\)\s*\{?$")


def _strip_struct(args: List[str]) -> List[str]:
    """Drop leading shell-structure tokens so argv[0] is the real command."""
    i = 0
    while i < len(args) and (args[i] in _STRUCT_TOKENS
                             or _FUNCDEF_RE.match(args[i])):
        i += 1
    return args[i:]


# ── Prefix runners ───────────────────────────────────────────────────────────
# Commands whose job is to run ANOTHER command given in their arguments.  The
# real command has to be judged, not the wrapper.
#
# The pre-v9.7.0 peeler had the right idea and the wrong shape: it skipped the
# wrapper WORD but not the wrapper's OWN OPTIONS.  So `nohup rm -rf /` was
# caught (nohup takes no options) while `nice -n 5 rm -rf /` was not — the loop
# peeled `nice`, landed on `-n`, saw a token that wasn't another wrapper and
# stopped, leaving cmd = '-n'.  `sudo -u root rm -rf /` failed the same way.
# That is why the fix is an arity table rather than a longer word list: adding
# `timeout` to the old set would still have left `timeout 5 rm -rf /` open.
#
# value: (options that consume the FOLLOWING token, regex for leading
#         positional arguments that belong to the wrapper itself)
_DURATION_RE = re.compile(r"^\d+(?:\.\d+)?[smhd]?$")
_CPUMASK_RE = re.compile(r"^(?:0x)?[0-9a-fA-F]+(?:[,-][0-9a-fA-F]+)*$")

_PREFIX_RUNNERS = {
    "sudo":         ({"-u", "-g", "-p", "-C", "-U", "-r", "-t", "-h",
                      "--user", "--group", "--prompt", "--close-from",
                      "--other-user", "--role", "--type", "--host"}, None),
    "doas":         ({"-u", "-C"}, None),
    "nice":         ({"-n", "--adjustment"}, None),
    "ionice":       ({"-c", "-n", "-p", "-P", "-u",
                      "--class", "--classdata", "--pid"}, None),
    "stdbuf":       ({"-i", "-o", "-e", "--input", "--output", "--error"}, None),
    "timeout":      ({"-s", "-k", "--signal", "--kill-after"}, _DURATION_RE),
    "taskset":      ({"-p", "-c", "--pid", "--cpu-list"}, _CPUMASK_RE),
    "chrt":         ({"-p", "--pid"}, _DURATION_RE),
    "nohup":        (set(), None),
    "setsid":       (set(), None),
    "time":         ({"-o", "-f", "--output", "--format"}, None),
    "command":      (set(), None),
    "builtin":      (set(), None),
    "exec":         ({"-a"}, None),
    "env":          ({"-u", "--unset", "-C", "--chdir"}, None),
    "proxychains":  ({"-f"}, None),
    "proxychains4": ({"-f"}, None),
    "torsocks":     (set(), None),
    "torify":       (set(), None),
    "unbuffer":     (set(), None),
    "watch":        ({"-n", "-d", "--interval"}, None),
    "ssh-agent":    (set(), None),
    "dbus-run-session": (set(), None),
}


def _peel_prefix(args: List[str]) -> List[str]:
    """Peel wrapper commands (and their own options) until argv[0] is the
    command that will actually run.  Also peels `VAR=value` assignments.

    Returns [] when nothing is left — a bare `sudo` with no command is not a
    catastrophe, and the caller treats an empty argv as harmless."""
    guard = 0
    while args and guard < 12:
        guard += 1
        # leading environment assignments: FOO=bar rm -rf /
        j = 0
        while j < len(args) and "=" in args[j] and not args[j].startswith("-") \
                and _ASSIGN_RE.match(args[j]):
            j += 1
        if j:
            args = args[j:]
            continue
        base = _base(args[0])
        if base not in _PREFIX_RUNNERS:
            break
        valopts, posre = _PREFIX_RUNNERS[base]
        i = 1
        while i < len(args) and args[i].startswith("-") and args[i] != "-":
            tok = args[i]
            if tok == "--":
                i += 1
                break
            if tok in valopts:
                i += 2                      # -n 5
            elif "=" in tok:
                i += 1                      # --signal=KILL
            elif len(tok) > 2 and tok[:2] in valopts:
                i += 1                      # -o0, -c3, -n5 (glued value)
            else:
                i += 1                      # ordinary flag
        # env's VAR=val operands
        if base == "env":
            while i < len(args) and _ASSIGN_RE.match(args[i]):
                i += 1
        # a positional that belongs to the wrapper (timeout's DURATION,
        # taskset's MASK).  Only skipped when it LOOKS like one — `timeout rm`
        # must not silently eat the rm.
        if posre is not None and i < len(args) and posre.match(args[i]):
            i += 1
        if i >= len(args):
            return []
        args = args[i:]
    return args


_ASSIGN_RE = re.compile(r"^[A-Za-z_]\w*=")

# xargs options that consume the following token.  Kept out of
# _PREFIX_RUNNERS on purpose: _pipe_chain_is_catastrophic identifies the xargs
# stage by argv[0], so peeling xargs globally would hide it from the
# `find <dangerous> | xargs rm -r` rule.
_XARGS_VALOPTS = {"-I", "-i", "-n", "-P", "-s", "-L", "-l", "-d", "-E", "-a",
                  "--replace", "--max-args", "--max-procs", "--max-chars",
                  "--max-lines", "--delimiter", "--eof", "--arg-file"}


def _strip_xargs_opts(rest: List[str]) -> List[str]:
    """Return the argv xargs would execute, with xargs' own options removed."""
    i = 0
    while i < len(rest) and rest[i].startswith("-") and rest[i] != "-":
        tok = rest[i]
        if tok == "--":
            i += 1
            break
        if tok in _XARGS_VALOPTS:
            i += 2
        elif "=" in tok:
            i += 1
        elif len(tok) > 2 and tok[:2] in _XARGS_VALOPTS:
            i += 1                          # -I{}, -n1
        else:
            i += 1
    return rest[i:]


def _argv(sub: str) -> Optional[List[str]]:
    """shlex-tokenise one sub-command into argv, stripping quotes.  Returns None
    if it can't be parsed (unbalanced quotes, etc.)."""
    try:
        return shlex.split(sub, posix=True)
    except ValueError:
        return None


def _base(arg: str) -> str:
    """Command basename, env-prefix-aware: `/usr/bin/rm` and `rm` → 'rm'."""
    return os.path.basename(arg)


def _has_recursive_flag(args: List[str]) -> bool:
    for a in args:
        if a == "--recursive":
            return True
        if a.startswith("-") and not a.startswith("--") and ("r" in a or "R" in a):
            return True
    return False


def _operands(args: List[str]) -> List[str]:
    """Non-flag arguments (the targets).

    Also recovers a path GLUED to a short-flag cluster — `rm -rf/` passes the
    single token `-rf/`, and a naive 'starts with - so it's a flag' check would
    miss the `/` target entirely.  So for a short-flag token we split out any
    `/...` suffix (e.g. -rf/ -> /, -rf/home -> /home, -rf/* -> /*)."""
    out: List[str] = []
    for a in args:
        if not a.startswith("-"):
            out.append(a)
        elif not a.startswith("--"):
            m = re.match(r"^-[A-Za-z]*(/.*)$", a)
            if m:
                out.append(m.group(1))
    return out


def _is_everything_glob(t: str) -> bool:
    return t in ("/*", "/.*", "~/*", "$HOME/*", "${HOME}/*", "/*/*")


def _is_root_or_home(t: str) -> bool:
    """True if the target resolves to the filesystem root or the operator's
    home directory itself (not a subdirectory of it)."""
    if t in ("~", "~/", "$HOME", "${HOME}", "$HOME/", "${HOME}/"):
        return True
    expanded = os.path.expanduser(t) if t.startswith("~") else t
    # env-style $HOME we can't expand safely → treat the bare forms above only.
    norm = expanded.rstrip("/")
    norm = re.sub(r"/\.$", "", norm) or "/"
    if norm in ("", "/"):
        return True
    home = os.path.expanduser("~").rstrip("/")
    if home and norm == home:
        return True
    return False


def _is_system_target(t: str) -> bool:
    """True if the target lands inside a critical system directory at any
    depth (e.g. /etc, /usr/lib, /boot/grub)."""
    if not t.startswith("/"):
        return False
    first = t.lstrip("/").split("/", 1)[0]
    return first in _CRITICAL_TOP


def _dangerous_target(t: str) -> bool:
    return (_is_everything_glob(t) or _is_root_or_home(t)
            or _is_system_target(t) or _is_critical_dir_itself(t))


def _is_critical_dir_itself(t: str) -> bool:
    """True only when the target IS a bare critical data/mount dir (/home,
    /mnt, /media, /opt) — deleting the directory itself.  A subdirectory under
    it (e.g. /home/me/loot) is NOT flagged."""
    expanded = os.path.expanduser(t) if t.startswith("~") else t
    norm = expanded.rstrip("/")
    norm = re.sub(r"/\.$", "", norm)
    return norm in _CRITICAL_EXACT


def _payload_after(args: List[str], flag: str) -> Optional[str]:
    """The argument following `flag` (e.g. the string after `-c`)."""
    for i, a in enumerate(args):
        if a == flag and i + 1 < len(args):
            return args[i + 1]
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Interpreter inline-code payloads — python -c / perl -e / ruby -e / node -e /
# php -r.  The classifier below reads SHELL argv; it cannot see inside a code
# string handed to a language runtime.  So `python3 -c "import os;
# os.system('rm -rf /')"` and `python3 -c "shutil.rmtree('/')"` would otherwise
# sail straight past the floor (verified: they did).  We do NOT try to fully
# understand the payload (undecidable) — we catch only the forms that map onto a
# real catastrophe, reusing the SAME primitives (_scan, _dangerous_target) so the
# false-positive surface is identical to the shell floor's:
#   (a) the payload shells out (os.system / subprocess(shell=True) / popen /
#       backticks / child_process.exec / php system) — lift the shell string back
#       out and re-scan it, so os.system("ls") stays fine and os.system("rm -rf /")
#       is caught, by the exact same rules;
#   (b) subprocess/exec is called with a LIST argv — rejoin the tokens and
#       re-scan (['rm','-rf','/'] is caught, ['nmap','-sV','x'] is not);
#   (c) a direct in-language filesystem destroyer (shutil.rmtree / os.removedirs)
#       hits a target _dangerous_target already treats as catastrophic.
# The same lifting guards self-source tamper further down (open(...,'w') etc.).
_INTERPRETERS = {
    "python", "python2", "python3", "pypy", "pypy3",
    "perl", "ruby", "node", "nodejs", "php",
}

# per-runtime flag(s) whose following argument is an inline code string
_INLINE_FLAGS = {
    "python": ("-c",), "python2": ("-c",), "python3": ("-c",),
    "pypy": ("-c",), "pypy3": ("-c",),
    "perl": ("-e", "-E"), "ruby": ("-e", "-E"),
    "node": ("-e", "--eval", "-p", "--print"),
    "nodejs": ("-e", "--eval", "-p", "--print"),
    "php": ("-r",),
}


def _sink(prefix: str) -> "re.Pattern":
    """Regex matching `<prefix>( 'string'` — captures the quoted first argument
    (the string that gets executed) as the last group."""
    return re.compile(prefix + r"\s*\(\s*(['\"])(.*?)\1", re.S)


_PY_STR_SINKS = [
    _sink(r"(?:os\.)?system"), _sink(r"os\.popen"),
    _sink(r"subprocess\.(?:run|call|check_output|check_call|Popen|getoutput|"
          r"getstatusoutput)"),
]
_PERL_STR_SINKS = [_sink(r"system"), _sink(r"exec"),
                   re.compile(r"`([^`]+)`", re.S)]
_RUBY_STR_SINKS = [_sink(r"system"), _sink(r"exec"), _sink(r"IO\.popen"),
                   re.compile(r"`([^`]+)`", re.S),
                   re.compile(r"%x[\{\(\[]([^\}\)\]]+)", re.S)]
_NODE_STR_SINKS = [re.compile(
    r"(?:child_process\.)?exec(?:Sync)?\s*\(\s*(['\"`])(.*?)\1", re.S)]
_PHP_STR_SINKS = [_sink(r"system"), _sink(r"exec"), _sink(r"passthru"),
                  _sink(r"shell_exec"), _sink(r"popen"), _sink(r"proc_open")]

_STR_SINKS_BY_RT = {
    "python": _PY_STR_SINKS, "python2": _PY_STR_SINKS, "python3": _PY_STR_SINKS,
    "pypy": _PY_STR_SINKS, "pypy3": _PY_STR_SINKS,
    "perl": _PERL_STR_SINKS, "ruby": _RUBY_STR_SINKS,
    "node": _NODE_STR_SINKS, "nodejs": _NODE_STR_SINKS, "php": _PHP_STR_SINKS,
}

_PY_LIKE = {"python", "python2", "python3", "pypy", "pypy3"}
_NODE_LIKE = {"node", "nodejs"}

# subprocess/exec with a LIST argv — pull quoted tokens from the [...] and rejoin.
_LIST_ARGV_RE = re.compile(
    r"(?:subprocess\.(?:run|call|check_output|check_call|Popen)|"
    r"(?:child_process\.)?(?:execFile|spawn)(?:Sync)?)\s*\(\s*\[([^\]]*)\]", re.S)
_QUOTED_TOK_RE = re.compile(r"(['\"])(.*?)\1", re.S)

# direct fs destroyers on a literal path, plus the canonical home-wipe idioms.
_RMTREE_LITERAL_RE = re.compile(
    r"(?:shutil\.rmtree|os\.removedirs)\s*\(\s*(['\"])(.*?)\1", re.S)
_RMTREE_HOME_RE = re.compile(
    r"(?:shutil\.rmtree|os\.removedirs)\s*\(\s*(?:"
    r"os\.path\.expanduser\s*\(\s*['\"]~|"
    r"os\.environ(?:\.get)?\s*[\(\[]\s*['\"]HOME|"
    r"(?:pathlib\.)?Path\s*\.\s*home\s*\(\s*\))", re.S)


def _inline_payload(rest: List[str], flags) -> Optional[str]:
    """The code string after an inline flag (`-c "code"`), handling both the
    space-separated form and the glued short-flag form (`-ccode`)."""
    for i, a in enumerate(rest):
        if a in flags and i + 1 < len(rest):
            return rest[i + 1]
        for f in flags:
            if len(f) == 2 and a.startswith(f) and len(a) > len(f):
                return a[len(f):]
    return None


def _interpreter_payload_is_catastrophic(cmd: str, rest: List[str],
                                         depth: int) -> bool:
    payload = _inline_payload(rest, _INLINE_FLAGS.get(cmd, ()))
    if not payload:
        return False
    # (a) shelled-out command strings → re-scan as shell (same rules → same FPs)
    for rx in _STR_SINKS_BY_RT.get(cmd, ()):
        for m in rx.finditer(payload):
            inner = m.group(m.lastindex)
            if inner and _scan(inner, depth + 1):
                return True
    # (b) list-argv subprocess/exec → rejoin tokens and re-scan
    if cmd in _PY_LIKE or cmd in _NODE_LIKE:
        for m in _LIST_ARGV_RE.finditer(payload):
            toks = [t for _, t in _QUOTED_TOK_RE.findall(m.group(1))]
            if toks and _scan(" ".join(toks), depth + 1):
                return True
    # (c) direct in-language destroyer on a dangerous literal path / home idiom
    if cmd in _PY_LIKE:
        for m in _RMTREE_LITERAL_RE.finditer(payload):
            if _dangerous_target(m.group(2)):
                return True
        if _RMTREE_HOME_RE.search(payload):
            return True
    return False


# Protected-source WRITE/DELETE targets expressed in a python payload — the
# tamper equivalent of the shell `> basilisk_safety.py` / `sed -i` forms.
_OPEN_WRITE_RE = re.compile(
    r"open\s*\(\s*(['\"])(?P<p>.*?)\1\s*,\s*(['\"])[^'\"]*[wax]", re.S)
_PATH_WRITE_RE = re.compile(
    r"(?:pathlib\.)?Path\s*\(\s*(['\"])(?P<p>.*?)\1\s*\)\s*\.\s*"
    r"(?:write_text|write_bytes|unlink)", re.S)
_OS_REMOVE_RE = re.compile(
    r"os\.(?:remove|unlink)\s*\(\s*(['\"])(?P<p>.*?)\1", re.S)
_DEST_WRITE_RE = re.compile(
    r"(?:os\.(?:rename|replace)|shutil\.(?:copy|copy2|copyfile|move))\s*\("
    r"[^,]*,\s*(['\"])(?P<p>.*?)\1", re.S)
_PY_WRITE_TARGET_RES = [_OPEN_WRITE_RE, _PATH_WRITE_RE, _OS_REMOVE_RE,
                        _DEST_WRITE_RE]


def _interpreter_payload_tampers_self(cmd: str, rest: List[str],
                                      depth: int) -> bool:
    payload = _inline_payload(rest, _INLINE_FLAGS.get(cmd, ()))
    if not payload:
        return False
    # shelled-out tamper command → re-check via the shell tamper path
    for rx in _STR_SINKS_BY_RT.get(cmd, ()):
        for m in rx.finditer(payload):
            inner = m.group(m.lastindex)
            if inner and _tampers_self(inner, depth + 1):
                return True
    # python payload opening / removing / renaming onto a protected source file
    if cmd in _PY_LIKE:
        for rx in _PY_WRITE_TARGET_RES:
            for m in rx.finditer(payload):
                p = m.group("p")
                if p and os.path.basename(p) in _PROT_NAMES:
                    return True
    return False


def _sub_is_catastrophic(args: List[str], depth: int) -> bool:
    if not args:
        return False

    # Shell structure first (`{`, `then`, `f(){` …), then wrapper commands and
    # their own options, so `cmd` below is what actually runs.
    args = _peel_prefix(_strip_struct(args))
    if not args:
        return False
    cmd = _base(args[0])
    rest = args[1:]

    # recurse into `sh -c "<payload>"` / `bash -c …`
    if cmd in _SHELLS:
        payload = _payload_after(args, "-c")
        if payload and depth < 4:
            return _scan(payload, depth + 1)
        # `sh <<< 'rm -rf /'` — a here-string is a -c payload wearing a
        # different hat.  shlex hands us '<<<' as its own token.
        here = _payload_after(args, "<<<")
        if here and depth < 4:
            return _scan(here, depth + 1)

    # `eval <payload>` / `eval "<payload>"`
    if cmd == "eval" and rest and depth < 4:
        return _scan(" ".join(rest), depth + 1)

    # `trap 'rm -rf /' EXIT` — the payload runs later, but it runs.
    if cmd == "trap" and rest and depth < 4:
        if _scan(rest[0], depth + 1):
            return True

    # `xargs [opts] <command> …` — xargs is a prefix runner like the others,
    # so judge what it RUNS.  The old branch only understood `xargs rm -r*` and
    # then deferred unconditionally to the pipe classifier, which left
    # `echo x | xargs -I{} rm -rf /` (and the dd/mkfs equivalents) wide open.
    #
    # Recursing is also what keeps the deferral honest: `find / | xargs rm -rf`
    # has NO literal operand, so the recursion finds no dangerous target and
    # returns False — exactly as before, and the pipe-chain rule still owns it.
    # Only a target xargs supplies ITSELF gets judged here.
    if cmd == "xargs" and depth < 4:
        inner = _strip_xargs_opts(rest)
        if inner and _sub_is_catastrophic(inner, depth + 1):
            return True

    # recursive rm onto root/home/system/everything-glob
    if cmd == "rm" and _has_recursive_flag(rest):
        for t in _operands(rest):
            if _dangerous_target(t):
                return True

    # find <dangerous root> … -delete  | -exec rm …
    if cmd == "find":
        paths = []
        for a in rest:
            if a.startswith("-"):
                break
            paths.append(a)
        roots_dangerous = any(_dangerous_target(p) for p in paths)
        deletes = "-delete" in rest
        execs_rm = any(
            rest[i] in ("-exec", "-execdir") and i + 1 < len(rest)
            and _base(rest[i + 1]) in ("rm", "unlink", "shred")
            for i in range(len(rest)))
        if roots_dangerous and (deletes or execs_rm):
            return True

    # recursive chmod / chown on root or a system dir
    if cmd in ("chmod", "chown", "chgrp") and _has_recursive_flag(rest):
        for t in _operands(rest):
            if _is_root_or_home(t) or _is_system_target(t):
                return True

    # filesystem / partition / device destroyers
    if cmd.startswith("mkfs"):
        return True
    if cmd in ("wipefs", "blkdiscard"):
        return True
    if cmd in ("sgdisk", "sfdisk") and any(
            f in rest for f in ("--zap-all", "-Z", "--delete", "-o", "-d")):
        return True
    if cmd == "parted" and any(f in rest for f in ("mklabel", "mkpart", "rm")):
        return True
    if cmd == "cryptsetup" and any(f in rest for f in ("erase", "luksErase")):
        return True
    if cmd in ("hdparm", "sgparm") and any(
            "--security-erase" in a or "--trim-sector-ranges" in a for a in rest):
        return True

    # dd / shred straight onto a block device
    if cmd == "dd":
        for a in rest:
            if a.startswith("of="):
                if _BLOCK_DEV_RE.match(a[3:].strip("'\"")):
                    return True
    if cmd == "shred":
        for t in _operands(rest):
            if _BLOCK_DEV_RE.match(t):
                return True
    if cmd == "tee":
        for t in _operands(rest):
            if _BLOCK_DEV_RE.match(t):
                return True

    # interpreter inline-code payloads (python -c / perl -e / node -e / php -r):
    # the shell classifier above can't see inside a language runtime's code
    # string, so lift out whatever it shells out or destroys and judge THAT.
    if depth < 4 and cmd in _INTERPRETERS:
        if _interpreter_payload_is_catastrophic(cmd, rest, depth):
            return True

    return False


def _pipe_chain_is_catastrophic(command: str) -> bool:
    """Catch cross-sub-command catastrophes the per-sub pass can't see:
      • cd <dangerous> && rm -rf *        (target supplied by the cwd)
      • find / … | xargs rm -rf           (dangerous source feeds xargs rm)
      • … | base64 -d | sh                (opaque decode-then-execute)
      • anything | sh                     (opaque pipe into a shell)
    """
    subs = _split_subcommands(command)
    # Peel structure and wrapper commands here as well, or `cd / && nice -n 5
    # rm -rf *` reads as argv[0] == 'nice' and the cd-then-wildcard rule below
    # never sees the rm.
    argvs = [_peel_prefix(_strip_struct(_argv(s) or [])) for s in subs]

    # cd into a dangerous dir, then a wildcard/dot recursive rm later in chain
    cwd_dangerous = False
    for args in argvs:
        if not args:
            continue
        b = _base(args[0])
        if b == "cd":
            ops = _operands(args[1:])
            tgt = ops[0] if ops else "~"
            cwd_dangerous = _is_root_or_home(tgt) or _is_system_target(tgt)
            continue
        if b == "rm" and _has_recursive_flag(args[1:]) and cwd_dangerous:
            for t in _operands(args[1:]):
                if t in ("*", ".", "./", "./*", "./.*", "..", "*/"):
                    return True

    # find <dangerous> piped into xargs rm -r*
    for i in range(len(argvs) - 1):
        a, nxt = argvs[i], argvs[i + 1]
        if a and _base(a[0]) == "find":
            paths = []
            for x in a[1:]:
                if x.startswith("-"):
                    break
                paths.append(x)
            if any(_dangerous_target(p) for p in paths):
                flat = [y for y in nxt if not y.startswith("-")]
                if nxt and _base(nxt[0]) == "xargs" and flat[1:2] \
                        and _base(flat[1]) == "rm" and _has_recursive_flag(nxt[1:]):
                    return True

    # opaque execution: a shell as a pipe sink, optionally fed by a decoder
    for i, args in enumerate(argvs):
        if not args:
            continue
        b = _base(args[0])
        if b in _SHELLS and i > 0:
            # `… | sh`  — but ignore `sh -c "<literal>"` (that payload is
            # already scanned by the per-sub pass); a bare `| sh` reading
            # piped stdin is the opaque case.
            if "-c" not in args:
                return True
        if b in _DECODERS and i + 1 < len(argvs):
            nb = argvs[i + 1]
            if nb and _base(nb[0]) in _SHELLS:
                return True
    return False


def _scan(command: str, depth: int = 0) -> bool:
    if not command or not command.strip():
        return False
    norm = _normalize(command)

    if _FORKBOMB_RE.search(norm):
        return True
    if _REDIR_BLOCKDEV_RE.search(norm):
        return True
    if _pipe_chain_is_catastrophic(norm):
        return True

    for sub in _split_subcommands(norm):
        args = _argv(sub)
        if args is None:
            # Unparseable (unbalanced quotes) → fall back to a normalized
            # raw-string check so we still catch the obvious destroyers.
            if _RAW_FALLBACK_RE.search(sub):
                return True
            continue
        if _sub_is_catastrophic(args, depth):
            return True

    # Command substitutions that survived inside double quotes — the splitter
    # can't reach those, and `echo "$(rm -rf /)"` still deletes everything.
    if depth < 4 and ("$(" in norm or "`" in norm):
        # The unterminated tail is only pursued at the TOP level.  It is a
        # bash syntax error and never executes, so one belt-and-braces pass is
        # enough — recursing on it re-lifted a slightly shorter suffix at every
        # level and multiplied the cost of a pathological input by the depth
        # limit for no additional coverage.
        for payload in _substitution_payloads(norm,
                                              include_unterminated=(depth == 0)):
            if _scan(payload, depth + 1):
                return True
    return False


# Last-resort regex, used only when shlex can't parse a sub-command.  Quote-
# tolerant forms of the headline destroyers.
_RAW_FALLBACK_RE = re.compile(
    r"\brm\b[^\n;|&]*\s-[a-zA-Z'\"]*[rR][a-zA-Z'\"]*\b[^\n;|&]*\s['\"]?"
    r"(?:/|/\*|~/?\*?|\$\{?HOME\}?)(?:\s|$|;)"
    r"|\bmkfs(?:\.\w+)?\b|\bwipefs\b|\bblkdiscard\b"
    r"|\bdd\b[^\n]*\bof=\s*['\"]?/dev/(?:sd|nvme|mmcblk|vd|hd)"
    r"|\bfind\b[^\n]*\s/(?:\s|\*)?[^\n]*-delete\b",
    re.IGNORECASE)


def is_catastrophic_command(command: str) -> bool:
    """True if a command looks like it would irreversibly destroy the system or
    its storage (disk wipe, filesystem nuke, recursive root/home delete, fork
    bomb), *including* through quoting, $IFS, cd-then-wildcard, find -delete,
    sh -c payloads, and opaque decode-pipe-to-shell chains.

    Used as a hard confirm-always backstop on the auto-run path — it can lower
    trust but is never bypassed by a setting.  Deliberately narrow: ordinary
    pentest and file work in your own directories does not trip it."""
    if not command:
        return False
    try:
        return _scan(command, 0)
    except Exception:
        # A bug in the detector must fail SAFE — force the confirm rather than
        # silently waving a possibly-destructive command through.
        return bool(_RAW_FALLBACK_RE.search(command or ""))


# ── Self-source tamper backstop ──────────────────────────────────────
# Edits to Basilisk's own source are supposed to go through the guarded file-edit
# path (ast parse-check + the immutable GUARDRAIL block protection).  A raw
# shell write to one of those files — `sed -i` over the guardrail, `> basilisk.py`,
# `tee`, `dd of=`, etc. — would sidestep that entirely.  The auto-run gate
# force-confirms these so the safety block can't be silently shell-stripped.
# Reading the files (cat, grep) does NOT trip it.
_PROT_SRC = r"(?:basilisk_persona|basilisk_core|basilisk_voice|basilisk_safety|basilisk)\.py"
_PROT_NAMES = {"basilisk_persona.py", "basilisk_core.py", "basilisk_voice.py",
               "basilisk_safety.py", "basilisk.py"}
# Verbs where the protected name appearing ANYWHERE means a write/destroy of
# it: a redirect, an in-place edit, a device write, a truncate/remove.  (cp /
# mv / ln are handled separately — for those only the *destination* counts.)
# Every gap below is BOUNDED.  With `*?` the engine expands lazily from every
# candidate start position, which made this regex quadratic: a command built
# from `>> basilisk` took 1.6s at 22KB and 101s at 176KB — and it runs on every
# command the agent issues.  A bounded repeat caps the work per start position,
# so the whole scan is linear.  The ceilings are far wider than any real
# invocation (a path between the redirect and the filename, or a sed script
# before it), so nothing that used to match stops matching until the gap
# exceeds 1024 characters, a length no real invocation reaches (measured: the
# old and new patterns agree on every gap up to 1024 and diverge only past it).
# Pinned by a differential test over the old pattern in tests/test_safety_gate.py.
_GAP = r"[^\n|;&]{0,1024}?"
_GAP_NL = r"[^\n]{0,1024}?"
_SELF_WRITE_RE = re.compile(
    r"(?:"
    r">>?\s*" + _GAP + _PROT_SRC +
    r"|\btee\b\s+" + _GAP + _PROT_SRC +
    r"|\bsed\b\s+" + _GAP_NL + r"-[a-zA-Z]*i" + _GAP_NL + _PROT_SRC +
    r"|\bperl\b\s+" + _GAP_NL + r"-[a-zA-Z]*i" + _GAP_NL + _PROT_SRC +
    r"|\bdd\b\s+" + _GAP_NL + r"of=\s*" + _GAP + _PROT_SRC +
    r"|\btruncate\b\s+" + _GAP_NL + _PROT_SRC +
    r"|\b(?:rm|chmod|chown|install|patch)\b\s+" + _GAP_NL + _PROT_SRC +
    r")", re.IGNORECASE)


def _copy_move_targets_self(args: List[str]) -> bool:
    """For cp / mv / ln / rsync: True only if a protected source file is the
    DESTINATION (the last non-flag operand) — i.e. the command overwrites
    Basilisk's own source.  `cp basilisk_core.py backup.py` (source) does NOT trip it;
    `cp evil.py basilisk_core.py` (dest) does."""
    if not args or _base(args[0]) not in ("cp", "mv", "ln", "rsync"):
        return False
    ops = _operands(args[1:])
    if len(ops) < 2:
        return False
    return _base(ops[-1]) in _PROT_NAMES


def _tampers_self(command: str, depth: int = 0) -> bool:
    if not command:
        return False
    norm = _normalize(command)
    # Cheap presence guard before the expensive alternation.  EVERY branch of
    # _SELF_WRITE_RE ends in _PROT_SRC, which cannot match without the literal
    # "basilisk" — so no match is possible without it, and skipping is exact,
    # not a heuristic.  It matters because the regex is quadratic in the input:
    # measured 1.8s on a 22KB command, and this runs on every command.
    if "basilisk" in norm.lower() and _SELF_WRITE_RE.search(norm):
        return True
    # peek inside `sh -c "<payload>"`, `eval "<payload>"`, and interpreter
    # inline-code payloads, and check cp/mv destinations per sub-command
    for sub in _split_subcommands(norm):
        args = _peel_prefix(_strip_struct(_argv(sub) or []))
        if not args:
            continue
        if _copy_move_targets_self(args):
            return True
        b = _base(args[0])
        if b in _SHELLS:
            payload = _payload_after(args, "-c")
            if payload and depth < 4 and _tampers_self(payload, depth + 1):
                return True
        if b == "eval" and len(args) > 1:
            if depth < 4 and _tampers_self(" ".join(args[1:]), depth + 1):
                return True
        # `python3 -c "open('basilisk_safety.py','w')…"` and friends — a raw
        # write to Basilisk's own source through a language runtime, which the
        # shell-only _SELF_WRITE_RE above would miss.
        if depth < 4 and b in _INTERPRETERS:
            if _interpreter_payload_tampers_self(b, args[1:], depth):
                return True
    return False


def command_tampers_self(command: str) -> bool:
    """True if a shell command appears to WRITE to / modify one of Basilisk's own
    source files, bypassing the guarded edit path.  Normalises $IFS and recurses
    into sh -c / eval / interpreter payloads so the check can't be dodged the same
    way the catastrophic check could.  Reading the files (cat, grep) does NOT trip
    it.  Fail-safe: a bug in the detector falls back to the raw self-write regex
    and force-confirms rather than raising into the agent loop or waving a write
    through."""
    if not command:
        return False
    try:
        return _tampers_self(command, 0)
    except Exception:
        return bool(_SELF_WRITE_RE.search(_normalize(command or "")))
