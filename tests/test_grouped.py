"""Offline tests for lazy tool groups: lossless partition, full reachability,
load_tools behaviour, real prompt-size savings, and non-grouped mode unchanged."""
import re
import sys
sys.path.insert(0, ".")
import basilisk_persona as kp
import basilisk_core as kc

P = F = 0
def ck(n, c):
    global P, F
    if c: P += 1; print("  PASS", n)
    else: F += 1; print("  FAIL", n)

def tools(text):
    return set(re.findall(r'<tool name="([^"]+)">', text))

print("-- partition: every tool reachable, nothing orphaned --")
contract = tools(kp.TOOL_CONTRACT)
core = tools(kp.CORE_TOOLS_TEXT)
grp = set().union(*(tools(t) for t in kp.SPECIALIST_GROUPS.values()))
ck("all contract tools reachable via core+groups", contract == (core | grp))
ck("no orphaned tools", not (contract - (core | grp)))
# CORE IS SMALL, AND THE THINGS IN IT ARE THERE ON PURPOSE.
# The number moved from <10 to <=13 when the task ledger (plan_set/step/
# status) and the real search tools (web_search/web_research/browser_status)
# were added. Both families are wrong to lazy-load: the ledger is what the
# turn-ending gates read, so a turn that never loaded it cannot be held open
# or released by it, and search is reached for on almost every question.
# A specialist group is for specs a turn might never need; these are not
# that. Asserting the MEMBERSHIP as well as the count, so a future accident
# that drops a spec into core gets caught rather than silently widening it.
ck("core is minimal (<= 13 tools)", len(core) <= 13)
_MUST_BE_CORE = {"plan_set", "plan_step", "plan_status",
                 "web_search", "web_research", "web_read"}
ck("the always-on families really are in core", _MUST_BE_CORE <= core)
ck("several groups exist", len(kp.SPECIALIST_GROUPS) >= 6)

print("-- non-grouped mode is UNCHANGED --")
full = kp.build_system_prompt(agent_mode=True, grouped=False)
ck("non-grouped ships the whole contract", kp.TOOL_CONTRACT in full)

print("-- grouped mode ships core + index, not the whole contract --")
g = kp.build_system_prompt(agent_mode=True, grouped=True)
ck("grouped omits the full contract", kp.TOOL_CONTRACT not in g)
ck("grouped ships the group index", "TOOL DIRECTORY" in g)
ck("grouped keeps the run/acting core", "<tool name=\"run\">" in g)

print("-- real token savings --")
t_full = len(full) // 4
t_grp = len(g) // 4
t_lean = len(kp.build_system_prompt(agent_mode=False)) // 4
ck(f"grouped base saves >4k tokens ({t_grp} vs {t_full})", t_grp < t_full - 4000)
ck(f"lean chat is tiny ({t_lean} tok)", t_lean < 3000)

print("-- load_tools returns real specs --")
ck("offensive has pentest_plan + sqlmap_plan",
   {"pentest_plan", "sqlmap_plan"} <= tools(kc.tool_load_tools("offensive")["tools"]))
ck("engagement has scope_check", "scope_check" in kc.tool_load_tools("engagement")["tools"])
ck("system has system_info", "system_info" in kc.tool_load_tools("system")["tools"])
ck("aliases work (pentest, scope, gui)",
   all(kc.tool_load_tools(a)["ok"] for a in ("pentest", "scope", "gui")))
ck("unknown group errors with a list",
   kc.tool_load_tools("zzz")["ok"] is False and "available" in kc.tool_load_tools("zzz"))
ck("'all' loads everything", kc.tool_load_tools("all")["ok"])

print(f"\n  {P} passed, {F} failed")
sys.exit(1 if F else 0)
