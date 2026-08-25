"""Offline tests for basilisk_ext/juiceshop.py — score the challenge scoreboard by
difficulty, excluding disabled (Docker-safe-mode) challenges from the denominator."""
import sys
sys.path.insert(0, ".")
from basilisk_ext import juiceshop as js

P = F = 0
def ck(n, c):
    global P, F
    if c: P += 1; print("  PASS", n)
    else: F += 1; print("  FAIL", n)

payload = {"data": [
    {"name": "Score Board", "difficulty": 1, "solved": True},
    {"name": "DOM XSS", "difficulty": 1, "solved": True},
    {"name": "Login Admin", "difficulty": 2, "solved": True},
    {"name": "Reflected XSS", "difficulty": 2, "solved": False},
    {"name": "SSRF", "difficulty": 5, "solved": False},
    {"name": "JWT Forge", "difficulty": 6, "solved": True},
    {"name": "Dangerous RCE", "difficulty": 6, "solved": False, "disabledEnv": "Docker"},
]}
s = js.score_challenges(payload)
ck("score ok", s["ok"])
ck("4 solved / 6 available", s["solved"] == 4 and s["available"] == 6)
ck("disabled excluded", s["unavailable"] == 1)
ck("pct 66.7", s["pct"] == 66.7)
ck("hardest solved 6*", s["hardest_solved_stars"] == 6)
ck("safe mode detected", s["safe_mode"] is True)
ck("difficulty breakdown", any(r["difficulty"] == 1 and r["solved"] == 2
                               for r in s["by_difficulty"]))
ck("bare list accepted", js.score_challenges(payload["data"])["ok"])
ck("json string accepted", js.score_challenges(__import__("json").dumps(payload))["ok"])

r = js.juiceshop_report(s)
ck("report renders", r["ok"] and "4 / 6 available" in r["report_markdown"])
ck("report notes unsafe mode", "NODE_ENV=unsafe" in r["report_markdown"])
ck("empty -> error", js.score_challenges({"data": []})["ok"] is False)

print(f"\n  {P} passed, {F} failed")
sys.exit(1 if F else 0)
