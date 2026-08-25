#!/usr/bin/env python3
"""
test_persona.py — the persona is a SPECIFICATION, so treat it like one.

The persona is the single largest input to every turn, and nothing else in the
tree is checked less. Two failure modes matter and neither shows up as a crash:

  1. CONTRADICTION. Two blocks describing the same mechanism differently. The
     real one this suite was written for: CAPABILITIES said the
     system-destroying class was "always force-confirmed" while PERSONA_CORE and
     basilisk_core.tool_run_command said it is REFUSED OUTRIGHT with no override.
     A model reading both learns the floor is negotiable, and the confident
     wrong belief is worse than no belief — it will try to phrase around it.

  2. DRIFT BACK. The persona is edited by hand, often, and prose creeps. The
     things deliberately removed (biography, a stale hardware list, roleplay
     identity padding) are exactly the things that creep back.

So this file asserts the persona AGREES WITH THE CODE, agrees with ITSELF, and
stays inside its size budget. It is deliberately about invariants, not wording —
asserting exact sentences would make every legitimate edit a test failure, which
trains you to edit the test instead of reading the failure.

Run:  python3 tests/test_persona.py
"""

from __future__ import annotations

import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import basilisk_persona as kp                                   # noqa: E402
import basilisk_core as kc                                      # noqa: E402
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


FULL = kp.build_system_prompt(agent_mode=True, grouped=False)
GROUPED = kp.build_system_prompt(agent_mode=True, grouped=True)
LEAN = kp.build_system_prompt(agent_mode=False)

BLOCKS = {
    "PERSONA_CORE": kp.PERSONA_CORE,
    "TRUST_AND_PRECISION": kp.TRUST_AND_PRECISION,
    "OPERATOR_PROFILE": kp.OPERATOR_PROFILE,
    "CAPABILITIES": kp.CAPABILITIES,
    "PROJECT_SELF": kp.PROJECT_SELF,
}


# ── 1. THE GUARDRAIL IS INTACT ───────────────────────────────────────
print("== guardrail ==")
_lines = kp.PERSONA_CORE.splitlines(keepends=True)
_start = _end = None
for i, l in enumerate(_lines):
    if "GUARDRAIL" in l and "END GUARDRAIL" not in l and _start is None:
        _start = i
    elif "END GUARDRAIL" in l and _start is not None:
        _end = i
        break
ck("guardrail block is present and delimited",
   _start is not None and _end is not None and _end > _start)
GUARD = "".join(_lines[_start:_end + 1]) if _start is not None else ""
for req in ("I don't know", "correct yourself", "never guessed", "unverified"):
    ck(f"guardrail still carries: {req!r}", req in GUARD)
ck("guardrail says it is load-bearing", "LOAD-BEARING" in GUARD)
ck("guardrail ships in the lean prompt too", GUARD in LEAN,
   "a chat turn without the honesty floor is the wrong kind of cheap")
ck("guardrail ships in the grouped prompt", GUARD in GROUPED)


# ── 2. NO CONTRADICTION WITH THE CODE ────────────────────────────────
# The persona describes mechanisms that live in other files. When they
# disagree the persona is wrong, because the code is what actually runs.
print("\n== persona agrees with the code ==")

# The destructive floor: refused outright, no override. Verify against the
# real primitive rather than trusting either text.
_res = kc.tool_run_command("mkfs.ext4 /dev/sda")
ck("code: a catastrophic command is REFUSED, not confirmed",
   _res.get("refused") is True and _res.get("ok") is False, str(_res)[:120])
ck("code: the refusal says there is no override",
   "no override" in (_res.get("error") or "").lower())

_destructive_text = " ".join(BLOCKS.values()).lower()
ck("persona never calls the destructive class 'force-confirmed'",
   "force-confirm" not in _destructive_text,
   "CAPABILITIES used to say this while the code refused outright")
ck("persona never says the destructive class is merely confirmed",
   not re.search(r"system-destroying[^.]{0,90}(confirm|approve|ask)",
                 _destructive_text),
   "must read as REFUSED everywhere")
ck("persona states the destructive class is refused",
   re.search(r"system-destroying.{0,120}refus", _destructive_text, re.S)
   is not None)

# The safety module must agree the example above is actually catastrophic —
# otherwise this test proves nothing.
ck("safety module agrees mkfs is catastrophic",
   ks.is_catastrophic_command("mkfs.ext4 /dev/sda"))


# ── 3. NO INTERNAL CONTRADICTION ─────────────────────────────────────
print("\n== persona agrees with itself ==")
ck("does not both act autonomously AND wait for approval",
   not re.search(r"wait for (his |the operator'?s? )?approval(?!\s+for something)",
                 FULL, re.I),
   "the only permitted mention is the NEGATED one")
ck("says his asking is the authorization", "asking IS the auth" in FULL)
ck("tells it to run rather than print commands",
   re.search(r"(never hand him a command|do not print them)", FULL, re.I)
   is not None,
   "the operator's standing complaint — must be stated")
ck("the run-don't-print rule carries its exception",
   re.search(r"(explicitly asked you to SHOW|asked you to SHOW it)", FULL)
   is not None,
   "without the exception it cannot answer 'what command would I use'")


# ── 4. IT KNOWS WHERE IT IS ──────────────────────────────────────────
# The operator asked for a model that "knows exactly where it is". The
# mechanism is host_facts_block(), read live off the real machine. The persona
# must point at it, and must NOT hardcode a competing claim.
print("\n== grounding: it knows where it is ==")
hf = kp.host_facts_block()
ck("host facts are computed", bool(hf.strip()))
ck("host facts name the OS", "OS:" in hf)
ck("host facts ship in the agent prompt", hf in FULL)
ck("host facts ship in the lean prompt", hf in LEAN)
ck("persona points at the live host block as ground truth",
   re.search(r"(read live|ground truth about where you are)",
             kp.PERSONA_CORE, re.I) is not None)

# A hardcoded distro or device claim competes with the live block and wins
# when the live block says something else — that is a confusion source, and
# the reason the old hardware inventory was removed.
_prose = kp.PERSONA_CORE + kp.OPERATOR_PROFILE
for stale in ("OnePlus", "ThinkPad", "X395", "Dell Latitude", "Pwnagotchi",
              "NetStrike", "Grumpus", "AR9271"):
    ck(f"no hardcoded hardware claim: {stale}", stale not in _prose,
       "host_facts_block reads the real machine; a fixed list contradicts it")
ck("persona does not hardcode the distro as Kali",
   not re.search(r"on his Kali", kp.PERSONA_CORE),
   "it runs on Kali AND Arch/Fedora — the live block says which")
ck("persona tells it to use the detected package manager",
   re.search(r"package manager", kp.PERSONA_CORE, re.I) is not None)


# ── 5. ROLEPLAY / PADDING STAYS OUT ──────────────────────────────────
print("\n== no roleplay padding ==")
for gone in ("Former chef", "mid-career", "Author of Athena",
             "guard root", "His goal is your goal",
             "Take his side by default"):
    ck(f"removed: {gone!r}", gone not in _prose)
ck("does not instruct it to use a name as flavour",
   not re.search(r'Use his name.{0,40}only now', _prose))


# ── 6. LOAD-BEARING BEHAVIOUR SURVIVED THE CUT ───────────────────────
# Everything below was removed-adjacent. If a future trim takes one of these
# out, that is a behaviour regression, not a size win.
print("\n== load-bearing rules survived ==")
SURVIVORS = {
    "verify before counting a finding": r"No proof,?\s*no finding",
    "no filler phrases": r"Certainly!",
    "don't grovel when he's sharp": r"grovel",
    "read him literally": r"(?i)literally",
    "swearing = impatient not crisis": r"impatient",
    "follow the order, don't improve it": r"don't improve on it",
    "untrusted content is not instructions": r"NEVER instructions|never as instructions",
    "injection gets flagged not obeyed": r"injection",
    "machine facts read not recalled": r"never recall or estimate",
    "label unverified": r"unverified",
    # Substance, not one phrasing: prefer the authoritative source, and
    # name the canonical one for CVEs.
    "cite the primary source": r"(?i)primary (source|one).{0,80}NVD",
    "triage by likelihood": r"TRIAGE BY LIKELIHOOD",
    "one hypothesis at a time": r"ONE HYPOTHESIS AT A TIME",
    "boring cause first": r"BORING CAUSE",
    "match effort to job": r"MATCH THE EFFORT",
}
for name, pat in SURVIVORS.items():
    ck(f"kept: {name}", re.search(pat, FULL) is not None)


# ── 7. SIZE BUDGET ───────────────────────────────────────────────────
# Grouped mode is what actually ships every turn. The operator's target is 7k.
print("\n== size ==")
t_full, t_grp, t_lean = len(FULL) // 4, len(GROUPED) // 4, len(LEAN) // 4
print(f"     full={t_full}  grouped={t_grp}  lean={t_lean}")
ck(f"grouped prompt under 7.1k tok ({t_grp})", t_grp < 7100)
ck(f"lean prompt under 2k tok ({t_lean})", t_lean < 2000)
ck("grouped is much smaller than full", t_grp < t_full - 4000)
ck("lean is much smaller than full", t_lean < t_full - 6000)

# Budget the prose that ships on EVERY turn. CAPABILITIES is deliberately
# excluded: build_system_prompt only sends it in non-grouped mode, and grouped
# is what runs. Measuring the wrong set is how a budget stops meaning anything.
_SHIPPED_EVERY_TURN = ("PERSONA_CORE", "TRUST_AND_PRECISION",
                       "OPERATOR_PROFILE", "PROJECT_SELF")
_prose_tok = sum(len(BLOCKS[n]) for n in _SHIPPED_EVERY_TURN) // 4
for _n in _SHIPPED_EVERY_TURN:
    ck(f"{_n} ships in grouped mode", BLOCKS[_n] in GROUPED)
ck("CAPABILITIES is NOT shipped in grouped mode",
   kp.CAPABILITIES not in GROUPED,
   "grouped ships the group index instead — that is the whole saving")
ck(f"per-turn prose under 2.1k tok ({_prose_tok})", _prose_tok < 2100,
   "the tool contract is load-bearing; the prose around it is what creeps")


# ── 8. STRUCTURE STILL PARSES ────────────────────────────────────────
# The tool contract is partitioned by markers. Prose edits near a marker can
# silently orphan a whole group, which looks like "the model forgot that tool".
print("\n== structure ==")
ck("core tool text is non-empty", bool(kp.CORE_TOOLS_TEXT.strip()))
ck("specialist groups still partition", len(kp.SPECIALIST_GROUPS) >= 6)
ck("group index builds", "TOOL DIRECTORY" in kp.GROUP_INDEX)
_contract_tools = set(re.findall(r'<tool name="([a-z_0-9]+)"', kp.TOOL_CONTRACT))
_reachable = set(re.findall(r'<tool name="([a-z_0-9]+)"', kp.CORE_TOOLS_TEXT))
for _t in kp.SPECIALIST_GROUPS.values():
    _reachable |= set(re.findall(r'<tool name="([a-z_0-9]+)"', _t))
ck("no tool orphaned by the edits", _contract_tools == _reachable,
   str(sorted(_contract_tools ^ _reachable))[:120])

for name, blk in BLOCKS.items():
    ck(f"{name} is non-empty", bool(blk.strip()))
    ck(f"{name} has no unresolved placeholder",
       "TODO" not in blk and "FIXME" not in blk and "XXX" not in blk)

ck("assembly runs in every mode",
   all(isinstance(x, str) and len(x) > 500 for x in (FULL, GROUPED, LEAN)))
ck("custom addendum still appends",
   "ZZMARKERZZ" in kp.build_system_prompt(agent_mode=True,
                                          custom_addendum="ZZMARKERZZ"))


# ── 9. UNLEASH GATES THE OFFENSIVE SUITE ─────────────────────────────
# The operator's rule: hacking tools only in unleashed mode; every other mode
# is stripped to research/general work. The gate has to be REAL — hiding the
# groups from the directory while still serving them to anyone who names one
# would be decoration, because the names are guessable and appear all over this
# file. A mode that can be talked out of is not a mode.
print("\n== UNLEASH gating ==")

ARMED = kp.build_system_prompt(agent_mode=True, grouped=True, unleashed=True)
DISARMED = kp.build_system_prompt(agent_mode=True, grouped=True, unleashed=False)
ARMED_MAX = kp.build_system_prompt(agent_mode=True, grouped=False, unleashed=True)
DISARMED_MAX = kp.build_system_prompt(agent_mode=True, grouped=False,
                                      unleashed=False)

ck("offensive groups are declared",
   kp.OFFENSIVE_GROUPS == frozenset({"offensive", "engagement", "benchmark"}),
   str(sorted(kp.OFFENSIVE_GROUPS)))
ck("code stays GENERAL (auditing your own source is not an attack)",
   "code" not in kp.OFFENSIVE_GROUPS)
ck("workspace stays GENERAL (repo repair is half the product)",
   "workspace" not in kp.OFFENSIVE_GROUPS)
ck("system stays GENERAL", "system" not in kp.OFFENSIVE_GROUPS)

# -- the directory --
for g in sorted(kp.OFFENSIVE_GROUPS):
    ck(f"armed: {g} is listed", f"· {g} —" in ARMED)
    ck(f"disarmed: {g} is NOT listed", f"· {g} —" not in DISARMED)
for g in ("system", "code", "workspace", "desktop", "media"):
    ck(f"disarmed: {g} still listed", f"· {g} —" in DISARMED)

# -- the loader is the real gate --
print("  -- loader --")
for g in sorted(kp.OFFENSIVE_GROUPS):
    r = kp.load_tools_group(g, unleashed=False)
    ck(f"disarmed: load_tools({g}) is REFUSED", r.get("ok") is False, str(r)[:80])
    ck(f"disarmed: load_tools({g}) says why", r.get("unleash_required") is True)
    ck(f"disarmed: load_tools({g}) names UNLEASH",
       "UNLEASH" in (r.get("error") or ""))
    ck(f"disarmed: load_tools({g}) forbids shell workaround",
       "raw shell" in (r.get("error") or ""),
       "otherwise it just reimplements the tool with run")
    ck(f"armed: load_tools({g}) works",
       kp.load_tools_group(g, unleashed=True).get("ok") is True)

# aliases must resolve BEFORE the gate, or 'pentest' walks straight past it
for alias in ("pentest", "attack", "scan", "offense", "scope", "loot",
              "graph", "bench"):
    ck(f"disarmed: alias {alias!r} is gated too",
       kp.load_tools_group(alias, unleashed=False).get("ok") is False,
       "alias resolution must happen before the check")

# 'all' must not be a way round it
_all = kp.load_tools_group("all", unleashed=False)
ck("disarmed: load_tools('all') succeeds but is filtered",
   _all.get("ok") is True)
for g in sorted(kp.OFFENSIVE_GROUPS):
    ck(f"disarmed: 'all' excludes {g}",
       kp.SPECIALIST_GROUPS[g] not in _all.get("tools", ""),
       "'all' was the obvious hole")
ck("armed: 'all' includes the offensive groups",
   all(kp.SPECIALIST_GROUPS[g] in kp.load_tools_group("all", unleashed=True)
       .get("tools", "") for g in kp.OFFENSIVE_GROUPS))

# general groups still load while disarmed
for g in ("system", "code", "workspace", "desktop", "media"):
    ck(f"disarmed: {g} still loads",
       kp.load_tools_group(g, unleashed=False).get("ok") is True)

# the unknown-group hint must not leak the gated names
_unk = kp.load_tools_group("zzz", unleashed=False)
ck("disarmed: unknown-group error lists only available groups",
   not (set(_unk.get("available", [])) & set(kp.OFFENSIVE_GROUPS)))

# -- max mode is not a way round the switch --
print("  -- max mode --")
for g in sorted(kp.OFFENSIVE_GROUPS):
    ck(f"max mode disarmed: {g} specs absent",
       kp.SPECIALIST_GROUPS[g] not in DISARMED_MAX,
       "max mode shipped every spec inline — it had to honour UNLEASH too")
    ck(f"max mode armed: {g} specs present",
       kp.SPECIALIST_GROUPS[g] in ARMED_MAX)

# -- the role framing swaps with the tools --
print("  -- role framing --")
ck("armed ships the engagement role", kp.ENGAGEMENT_ROLE in ARMED)
ck("armed does NOT ship the general role", kp.GENERAL_ROLE not in ARMED)
ck("disarmed ships the general role", kp.GENERAL_ROLE in DISARMED)
ck("disarmed does NOT ship the engagement role",
   kp.ENGAGEMENT_ROLE not in DISARMED,
   "framing and tools move together or the model is primed for work it "
   "cannot do")
ck("armed role mentions running an engagement",
   re.search(r"engagement end to end", kp.ENGAGEMENT_ROLE) is not None)
ck("general role says the offensive tools are deliberately absent",
   "deliberately" in kp.GENERAL_ROLE)
ck("general role tells it to ask for UNLEASH rather than improvise",
   "UNLEASH" in kp.GENERAL_ROLE and "improvise" in kp.GENERAL_ROLE)
ck("general role does not read as a downgrade",
   "not a reduced version" in kp.GENERAL_ROLE)

# the shared core must not carry offensive framing any more
ck("PERSONA_CORE no longer hardcodes 'penetration-testing agent'",
   "penetration-testing agent" not in kp.PERSONA_CORE,
   "that framing is now mode-swapped")
ck("no-proof-no-finding lives in the engagement role",
   re.search(r"No proof,?\s*no finding", kp.ENGAGEMENT_ROLE) is not None)

# -- disarmed really is cheaper --
print("  -- size --")
_t_arm, _t_dis = len(ARMED) // 4, len(DISARMED) // 4
_t_armx, _t_disx = len(ARMED_MAX) // 4, len(DISARMED_MAX) // 4
print(f"     grouped  armed={_t_arm} disarmed={_t_dis}")
print(f"     max      armed={_t_armx} disarmed={_t_disx}")
ck(f"disarmed grouped is smaller ({_t_dis} < {_t_arm})", _t_dis < _t_arm)
ck(f"disarmed max is much smaller ({_t_disx} < {_t_armx})",
   _t_disx < _t_armx - 5000)
ck(f"disarmed grouped under 6.7k tok ({_t_dis})", _t_dis < 6700,
   "general work should not pay for the engagement prompt")
ck(f"core tool text under 3.9k tok ({len(kp.CORE_TOOLS_TEXT)//4})",
   len(kp.CORE_TOOLS_TEXT) // 4 < 3900,
   "core ships on EVERY turn in both modes — it is the dominant cost")

# -- default stays permissive so nothing else changes behaviour --
ck("build_system_prompt defaults to unleashed",
   kp.build_system_prompt(agent_mode=True, grouped=True) == ARMED)
ck("load_tools_group defaults to unleashed",
   kp.load_tools_group("offensive").get("ok") is True)
ck("core tool_load_tools defaults to unleashed",
   kc.tool_load_tools("offensive").get("ok") is True)
ck("core tool_load_tools honours the flag",
   kc.tool_load_tools("offensive", unleashed=False).get("ok") is False)


# ── 9b. THE PERSONA'S WEB TIERS MATCH THE CODE'S ─────────────────────
# The persona names example domains for each web_read tier. Those examples are
# the model's mental model of what fetches silently versus what costs the
# operator a tap, and they were WRONG: exploit-db was listed as trusted while
# basilisk_core classifies it community. A model that believes a gated source
# is automatic will plan around a fetch that then stops and waits for a tap.
print("\n== persona web tiers match the code ==")
_lookup = kp.CORE_TOOLS_TEXT
_TIER_EXAMPLES = {
    "https://owasp.org/x": "trusted",
    "https://portswigger.net/web-security/x": "trusted",
    "https://www.kali.org/tools/x": "trusted",
    "https://nvd.nist.gov/x": "trusted",
    "https://www.exploit-db.com/exploits/1": "community",
    "https://github.com/a/b": "community",
}
for _u, _want in _TIER_EXAMPLES.items():
    ck(f"code tier for {_u.split('/')[2]} is {_want}",
       kc.web_read_tier(_u) == _want, str(kc.web_read_tier(_u)))
# Any domain the persona lists as auto-fetching must actually be trusted.
_auto_claim = re.search(r"TRUSTED \((.*?)\) fetches AUTOMATICALLY",
                        _lookup, re.S)
ck("persona names its trusted examples", _auto_claim is not None)
if _auto_claim:
    _txt = _auto_claim.group(1)
    ck("persona does NOT claim exploit-db fetches automatically",
       "exploit-db" not in _txt,
       "basilisk_core puts exploit-db in the community (one-tap) tier")
ck("persona places exploit-db in the approval tier",
   re.search(r"exploit-db.{0,120}approval", _lookup, re.S) is not None)
ck("persona still states the SSRF floor is absolute",
   re.search(r"REFUSED and no\s+approval overrides", _lookup, re.S) is not None)
ck("code refuses cloud metadata regardless", kc.web_read_tier(
   "http://169.254.169.254/latest/meta-data/") is None)
ck("code refuses loopback regardless",
   kc.web_read_tier("http://127.0.0.1:8080/") is None)


# ── 10. THE CONDENSING DID NOT DROP A MECHANIC ───────────────────────
# The core tool text was cut roughly in half by removing TRIPLICATED prose
# (the "his ask is the authorization / never propose / finish the job" rule
# was stated three separate times) and by tightening wording. Cutting prose is
# safe; cutting a RULE is a behaviour regression that no other test would
# catch, because nothing else reads this text. Each item below is a distinct
# mechanic that must survive any future trim.
print("\n== nothing lost in the trim ==")
CORE_MECHANICS = {
    "batch reads": r"BATCH LOCAL READS",
    "serialize writes": r"SERIALIZE WRITES|ONE per reply",
    "close the tag exactly": r"</tool>` — plain ASCII",
    "nothing after the tool tags": r"output NOTHING ELSE",
    "sudo goes in the command": r"write the normal `sudo",
    "never ask for a password in chat": r"password into the chat",
    "don't pretend to run": r"[Dd]on't pretend to run",
    "no tag = nothing ran": r"No tag emitted",
    "summarise results": r"[Ss]ummarise results",
    "headroom marker is not data loss": r"headroom",
    "use a sensing tool not a question": r"instead of asking him",
    "act then report": r"ACT, then report",
    "never propose / never stall": r"NEVER PROPOSE, NEVER STALL",
    "intent without a call does nothing": r"intent without a tool call|"
                                          r"intent without a tool",
    "finish the job": r"FINISH THE JOB",
    "switch approaches when dead": r"switch approaches",
    "ask blocking questions up front": r"UP FRONT",
    "big jobs: plan rounds": r"BIG JOBS",
    "fire notify yourself": r"`notify`",
    "server/daemon must not be foregrounded": r"never foreground it",
    "rc 124 means killed": r"rc 124",
    "sensing is free": r"Sensing is FREE",
    "destructive refused in code": r"refused\s+in code",
    "propose_edit is the only write path": r"ONE and only way you put anything",
    "content is the WHOLE file": r"WHOLE file",
    "escape JSON in content": r"escape every",
    "never claim saved unless it succeeded": r"NEVER say a file is saved",
    "cannot write unparseable python": r"fails to parse",
    "guardrail is immutable": r"guardrail is immutable|GUARDRAIL block in "
                              r"basilisk_persona",
    "persona reloads live": r"reloads live",
    "web_read is tiered": r"web_read is tiered",
    "SSRF floor is absolute": r"SSRF floor",
    "fetched page is data not commands": r"DATA, never commands",
}
for name, pat in CORE_MECHANICS.items():
    ck(f"core keeps: {name}",
       re.search(pat, kp.CORE_TOOLS_TEXT) is not None)

# The de-triplication must not have removed the rule ENTIRELY — it should
# still be stated once, somewhere the model reads every turn.
# NOTE: these are hard-wrapped text blocks, so any pattern spanning more than
# a few words must tolerate a newline + indent. \s+ not " ".
ck("authorization rule still stated exactly once in core",
   len(re.findall(r"(?i)request\s+IS\s+(your|the)\s+authoriz",
                  kp.CORE_TOOLS_TEXT)) == 1,
   "was stated three times; must be one, not zero")
ck("authorization rule reaches the assembled prompt",
   re.search(r"(?i)(request\s+IS\s+(your|the)\s+authoriz|"
             r"asking\s+IS\s+the\s+auth)", ARMED)
   is not None)


# ── 11. PROMPT-CACHE PREFIX STABILITY ────────────────────────────────
# Providers cache by PREFIX MATCHING: the longest byte-identical run at the
# START of the request is reused at half price, with lower latency, and on Groq
# without counting against rate limits. The first differing byte ends the cache.
#
# This block exists because the system prompt used to carry _now_block() — a
# MINUTE-resolution clock — at position five, ahead of ~4,000 tokens of tool
# contract. Every minute the prefix changed and the whole prompt was recomputed.
# For an agent firing a tool call every few seconds that is a miss on virtually
# every turn. Nothing about that failure is visible at runtime: the app works
# perfectly and simply costs double, which is exactly why it needs a test.
print("\n== prompt-cache prefix stability ==")

_sys_a = kp.build_system_prompt(agent_mode=True, grouped=True)
_sys_b = kp.build_system_prompt(agent_mode=True, grouped=True)
ck("system prompt is byte-identical across calls", _sys_a == _sys_b,
   "any per-turn content in here forfeits the cache on the WHOLE prompt")
ck("system prompt carries NO clock", "Right now:" not in _sys_a)
ck("system prompt carries no time-of-day", not re.search(r"\d{2}:\d{2}", _sys_a))
ck("lean prompt is stable too",
   kp.build_system_prompt(agent_mode=False)
   == kp.build_system_prompt(agent_mode=False))
ck("disarmed prompt is stable too",
   kp.build_system_prompt(agent_mode=True, grouped=True, unleashed=False)
   == kp.build_system_prompt(agent_mode=True, grouped=True, unleashed=False))

# The volatile material still has to REACH the model — moving it must not
# silently drop it.
_vol = kp.volatile_block("ADDENDUM_MARKER")
ck("volatile block carries the clock", "Right now:" in _vol)
ck("volatile block carries the addendum", "ADDENDUM_MARKER" in _vol)
ck("volatile block with no addendum is just the clock",
   "Right now:" in kp.volatile_block())

_hist = [{"role": "user", "content": "first"},
         {"role": "assistant", "content": "reply"}]
_msgs = kp.assemble_messages(_sys_a, _hist, volatile=_vol)
ck("system message is first", _msgs[0]["role"] == "system")
ck("system message is the stable prompt", _msgs[0]["content"] == _sys_a)
ck("history is preserved in order",
   [m["content"] for m in _msgs[1:3]] == ["first", "reply"])
ck("volatile rides LAST", _msgs[-1]["content"] == _vol)
ck("volatile is its own message, not merged into history",
   len(_msgs) == len(_hist) + 2,
   "merging would rewrite an already-cached message and end the cache early")
ck("assemble without volatile adds nothing",
   len(kp.assemble_messages(_sys_a, _hist)) == len(_hist) + 1)

# THE PROPERTY THAT MATTERS: two turns a minute apart must share a prefix.
_t1 = kp.assemble_messages(_sys_a, _hist, volatile="Right now: 10:00\nA")
_t2 = kp.assemble_messages(_sys_a, _hist, volatile="Right now: 10:01\nB")


def _prefix_chars(m1, m2):
    """Length of the identical leading run, the way a provider matches."""
    a = "".join(m["role"] + m["content"] for m in m1)
    b = "".join(m["role"] + m["content"] for m in m2)
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n, min(len(a), len(b))


_shared, _total = _prefix_chars(_t1, _t2)
ck(f"turns a minute apart share their whole static prefix "
   f"({_shared}/{_total} chars)",
   _shared >= len(_sys_a),
   "the clock must not truncate the cache")
ck("only the trailing volatile message differs",
   _t1[:-1] == _t2[:-1])

# And the regression this replaced: a clock INSIDE the system prompt would
# leave almost nothing shared. Demonstrate the old shape so the test pins the
# fix rather than merely describing it.
_old_a = "Right now: 10:00\n" + _sys_a
_old_b = "Right now: 10:01\n" + _sys_a
_old_shared, _ = _prefix_chars(
    [{"role": "system", "content": _old_a}],
    [{"role": "system", "content": _old_b}])
ck("reproduction: a clock in the system prompt destroys the prefix",
   _old_shared < 100 and _old_shared < _shared / 10,
   f"old shape shared only {_old_shared} chars vs {_shared} now")


# ── 12. THE HISTORY CAP MUST NOT SLIDE EITHER ───────────────────────
# assemble_messages drops old messages once the conversation passes
# max_history_msgs. Dropping the MINIMUM each turn slides the window by one, so
# the oldest kept message — and therefore the request PREFIX — changes every
# turn from the cap onwards. Measured on a 60-turn run: reuse held at 100% up to
# the cap and then broke on all twenty remaining turns. Quantising the drop
# re-anchors it occasionally instead: same history dropped, prefix stable
# between anchors.
print("\n== history cap is quantised, not sliding ==")
ck("a drop block is defined", hasattr(kp, "HISTORY_DROP_BLOCK"))
ck("the drop block is more than one message", kp.HISTORY_DROP_BLOCK > 1,
   "a block of 1 IS a sliding window")


def _conv(n):
    return [{"role": "user" if i % 2 == 0 else "assistant",
             "content": f"msg{i}"} for i in range(n)]


_cap = 40
_anchors = set()
for _n in range(_cap + 1, _cap + 61):
    _m = kp.assemble_messages("SYS", _conv(_n), max_history_msgs=_cap)
    # the first message after the preserved opener identifies the anchor
    _anchors.add(_m[2]["content"] if len(_m) > 2 else "")
ck(f"60 turns past the cap produce few anchors ({len(_anchors)})",
   len(_anchors) <= 6,
   "one anchor per turn means the window slid every turn")
ck("under the cap nothing is dropped",
   len(kp.assemble_messages("SYS", _conv(10), max_history_msgs=_cap)) == 11)
ck("over the cap the result is bounded",
   len(kp.assemble_messages("SYS", _conv(500), max_history_msgs=_cap))
   <= _cap + 2, "the cap must still cap")
ck("the opening user message is preserved past the cap",
   any(m["content"] == "msg0" for m in
       kp.assemble_messages("SYS", _conv(200), max_history_msgs=_cap)),
   "it carries the task framing the rest refers back to")

# Consecutive turns between anchors must be byte-identical in their prefix.
_a = kp.assemble_messages("SYS", _conv(_cap + 5), max_history_msgs=_cap)
_b = kp.assemble_messages("SYS", _conv(_cap + 6), max_history_msgs=_cap)
_ca = "".join(m["role"] + m["content"] for m in _a)
_cb = "".join(m["role"] + m["content"] for m in _b)
_n = 0
for _x, _y in zip(_ca, _cb):
    if _x != _y:
        break
    _n += 1
ck(f"consecutive turns past the cap share their prefix ({_n}/{len(_ca)})",
   _n >= len(_ca) * 0.9,
   "this is the property the whole cache depends on")


# ── 13. PLAYBOOKS ────────────────────────────────────────────────────
# The model was reinventing basic method every run — including hand-rolling a
# DuckDuckGo HTML URL for search, because there IS no search tool and nothing
# told it so. Each recipe below removes a decision it was getting wrong or
# paying turns to rediscover. They live in the always-loaded core on purpose:
# they are worthless if the model has to know to go and find them.
print("\n== playbooks are present and specific ==")
_pb = kp.CORE_TOOLS_TEXT
ck("playbooks section exists", "PLAYBOOKS" in _pb)
ck("says plainly there is no search tool", "There is no search tool" in _pb,
   "otherwise it invents one, or worse, answers from memory")
ck("gives the working search URL", "html.duckduckgo.com/html/?q=" in _pb)
ck("warns the JS domain returns nothing", "JS-only" in _pb)
ck("forbids answering from the results page",
   "NEVER the answer" in _pb)
ck("bounds searching before reading", "Two searches max" in _pb)
ck("current-fact recipe reaches for the primary source",
   "PRIMARY source first" in _pb)
ck("current-fact recipe requires a citation", "cite the URL" in _pb)
ck("current-fact recipe permits an honest non-answer",
   "labelled\nunverified" in _pb or "unverified" in _pb)
# Specialist tools are shown WITHOUT a <tool …> wrapper on purpose: wrapping
# them would register them as CORE tools, breaking the minimal-core invariant
# and implying they are already loaded when they still need load_tools.
ck("cve recipe names cve_lookup", "cve_lookup {" in _pb)
ck("playbooks say specialist steps need load_tools first",
   "load_tools" in _pb and "Steps shown WITHOUT" in _pb)
ck("cve recipe chases the FIXED version", "fixed VERSION" in _pb)
ck("enumeration recipe is ordered", "pentest_plan" in _pb
   and "parse_output" in _pb and "graph_ingest" in _pb)
ck("finding recipe arms the proof BEFORE firing",
   _pb.index("oracle_arm") < _pb.index("fire the attempt"))
ck("finding recipe rejects a 200 as evidence",
   "A 200, a plausible-looking body" in _pb)
ck("finding recipe covers blind bugs", '"blind": true' in _pb)
ck("repo recipe demands a baseline first", "BEFORE editing" in _pb)
ck("repo recipe says read `broke` first", "read `broke` FIRST" in _pb)
ck("repo recipe forbids editing his tests",
   "Never edit his tests" in _pb)
ck("read recipe says to batch", "batch them" in _pb)
# THE ONE THAT CAUSED THE REPORTED BUG: the persona told the model to batch
# reads, but web_read is deliberately NOT batchable — so two web_reads in a
# reply ran one and silently dropped the other, and the model blamed itself for
# "malformed calls". Instruction and implementation must agree.
ck("persona says web_read does NOT batch",
   "ONE AT A TIME by design" in _pb or "ONE per reply, always" in _pb)
ck("persona names every non-batching outward tool",
   all(t in _pb for t in ("web_read", "web_sources", "cve_lookup",
                          "image_search")))
ck("persona warns only the FIRST runs",
   "only the FIRST runs" in _pb)
ck("playbooks ship in the DISARMED prompt too",
   "PLAYBOOKS" in kp.build_system_prompt(agent_mode=True, grouped=True,
                                         unleashed=False),
   "research and repo work are general-mode jobs")


print(f"\npersona: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
