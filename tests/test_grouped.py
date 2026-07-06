"""Offline tests for lazy tool groups: lossless partition, full reachability,
load_tools behaviour, real prompt-size savings, and non-grouped mode unchanged."""
import re
import sys
sys.path.insert(0, ".")
import kali_persona as kp
import kali_core as kc

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
ck("core is minimal (< 10 tools)", len(core) < 10)
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
ck("aliases work (pentest, scope, osint, gui)",
   all(kc.tool_load_tools(a)["ok"] for a in ("pentest", "scope", "osint", "gui")))
ck("unknown group errors with a list",
   kc.tool_load_tools("zzz")["ok"] is False and "available" in kc.tool_load_tools("zzz"))
ck("'all' loads everything", kc.tool_load_tools("all")["ok"])

print(f"\n  {P} passed, {F} failed")
sys.exit(1 if F else 0)
