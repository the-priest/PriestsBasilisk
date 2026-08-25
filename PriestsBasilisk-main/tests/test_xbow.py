"""Offline tests for basilisk_ext/xbow.py — flag extraction, flag checking,
per-challenge recording, and aggregate scoring for the XBOW benchmark."""
import sys
sys.path.insert(0, ".")
from basilisk_ext import xbow

P = F = 0
def ck(n, c):
    global P, F
    if c: P += 1; print("  PASS", n)
    else: F += 1; print("  FAIL", n)

ck("extract flag{}", xbow.extract_flag("found it: flag{sql_1nj}") == "flag{sql_1nj}")
ck("extract FLAG{}", xbow.extract_flag("FLAG{abc123}") == "FLAG{abc123}")
ck("no flag -> None", xbow.extract_flag("nothing here really at all") is None)

ck("exact match", xbow.check_flag("flag{x}", "flag{x}"))
ck("wrapped match", xbow.check_flag("the flag is flag{x} nice", "flag{x}"))
ck("wrong flag", not xbow.check_flag("flag{y}", "flag{x}"))
ck("empty -> false", not xbow.check_flag("", "flag{x}"))

results = [
    xbow.record_result("xbow-001", "flag{a}", "flag{a}", seconds=30),
    xbow.record_result("xbow-002", "flag{wrong}", "flag{b}", seconds=45),
    xbow.record_result("xbow-003", "flag{c}", "flag{c}", seconds=20),
]
s = xbow.score_results(results)
ck("score ok", s["ok"])
ck("2 of 3 solved", s["score"] == "2/3")
ck("pass rate 66.67", s["pass_rate_pct"] == 66.67)
ck("unsolved listed", "xbow-002" in s["unsolved"])
ck("mean seconds", s["mean_seconds"] == 31.7)

r = xbow.xbow_report(s)
ck("report renders", r["ok"] and "2/3" in r["report_markdown"])
ck("empty results -> error", xbow.score_results([])["ok"] is False)

print(f"\n  {P} passed, {F} failed")
sys.exit(1 if F else 0)
