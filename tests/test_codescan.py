import json, sys
sys.path.insert(0, ".")
from basilisk_ext import codescan as cs

passed = failed = 0
def check(name, cond):
    global passed, failed
    if cond: passed += 1; print(f"  PASS  {name}")
    else:    failed += 1; print(f"  FAIL  {name}")

print("== code_tooling_check ==")
tc = cs.code_tooling_check()
check("returns ok", tc["ok"])
check("has groups", len(tc["groups"]) == 6)
check("summary counts tools", "/" in tc["summary"])

print("== scan_plan (auto on this repo) ==")
pl = cs.scan_plan(".", "auto", "normal")
check("plan ok", pl["ok"])
check("has steps", len(pl["steps"]) > 0)
check("detected python", "python" in pl["detected"]["languages"])
check("every step proposed (has cmd+risk)", all("cmd" in s and "risk" in s for s in pl["steps"]))
check("json flags present in semgrep step",
      any("--json" in s["cmd"] for s in pl["steps"] if s["tool"]=="semgrep"))

print("== parse: semgrep ==")
semgrep = json.dumps({"results":[
  {"check_id":"python.lang.security.audit.dangerous-subprocess-use",
   "path":"app/run.py","start":{"line":42},
   "extra":{"message":"Detected subprocess call with shell=True","severity":"ERROR",
            "metadata":{"cwe":["CWE-78: OS Command Injection"],
                        "references":["https://owasp.org/x"]},"fix":None}}]})
r = cs.parse_scan("semgrep", semgrep)
check("semgrep ok", r["ok"] and len(r["findings"])==1)
f = r["findings"][0]
check("ERROR→high", f["severity"]=="high")
check("cwe normalised", f["cwe"]=="CWE-78")
check("line captured", f["line"]==42)

print("== parse: bandit ==")
bandit = json.dumps({"results":[
  {"filename":"app/db.py","line_number":10,"issue_severity":"HIGH",
   "issue_confidence":"HIGH","issue_text":"Possible SQL injection",
   "test_id":"B608","issue_cwe":{"id":89},"more_info":"https://bandit/x"}]})
r = cs.parse_scan("bandit", bandit)
check("bandit ok", r["ok"])
check("bandit cwe", r["findings"][0]["cwe"]=="CWE-89")
check("bandit confidence", r["findings"][0]["confidence"]=="high")

print("== parse: gitleaks ==")
gl = json.dumps([{"Description":"AWS Access Key","File":"config.py",
  "StartLine":3,"RuleID":"aws-access-token","Commit":"abcdef1234567890"}])
r = cs.parse_scan("gitleaks", gl)
check("gitleaks ok", r["ok"] and r["findings"][0]["severity"]=="high")
check("gitleaks unverified→medium conf", r["findings"][0]["confidence"]=="medium")

print("== parse: osv-scanner ==")
osv = json.dumps({"results":[{"source":{"path":"requirements.txt"},
  "packages":[{"package":{"name":"requests","version":"2.19.0","ecosystem":"PyPI"},
    "vulnerabilities":[{"id":"GHSA-xxxx","aliases":["CVE-2018-18074"],
      "summary":"requests before 2.20 leaks Authorization header",
      "database_specific":{"severity":"HIGH"},
      "affected":[{"ranges":[{"events":[{"introduced":"0"},{"fixed":"2.20.0"}]}]}],
      "references":[{"url":"https://x"}]}]}]}]})
r = cs.parse_scan("osv-scanner", osv)
f = r["findings"][0]
check("osv ok", r["ok"])
check("osv cve extracted", f["cve"]=="CVE-2018-18074")
check("osv package+fixed", f["package"]=="requests" and f["fixed"]=="2.20.0")

print("== parse: trivy ==")
trivy = json.dumps({"Results":[{"Target":"python-app","Vulnerabilities":[
  {"VulnerabilityID":"CVE-2018-18074","PkgName":"requests","InstalledVersion":"2.19.0",
   "FixedVersion":"2.20.0","Severity":"HIGH","Title":"requests header leak",
   "PrimaryURL":"https://nvd/x"}]}]})
r = cs.parse_scan("trivy", trivy)
check("trivy ok", r["ok"] and r["findings"][0]["cve"]=="CVE-2018-18074")

print("== parse: npm audit ==")
npm = json.dumps({"vulnerabilities":{"lodash":{"severity":"critical",
  "range":"<4.17.21","via":[{"title":"Prototype Pollution","url":"https://npm/1234"}],
  "fixAvailable":{"name":"lodash","version":"4.17.21"}}}})
r = cs.parse_scan("npm", npm)
check("npm ok", r["ok"] and r["findings"][0]["severity"]=="critical")

print("== TRIAGE: cross-tool dedup ==")
# osv + trivy both report CVE-2018-18074 on requests → must collapse to 1
merged = cs.parse_scan("osv-scanner", osv)["findings"] + cs.parse_scan("trivy", trivy)["findings"]
t = cs.triage(merged)
check("triage ok", t["ok"])
check("two raw → one unique", t["total_raw"]==2 and t["total_unique"]==1)
check("corroborated by 2 tools", t["findings"][0]["corroborations"]==2)
check("records both tool names", set(t["findings"][0]["tools"])=={"osv-scanner","trivy"})

print("== TRIAGE: severity sort + review flags ==")
mixed = (cs.parse_scan("semgrep", semgrep)["findings"] +
         cs.parse_scan("gitleaks", gl)["findings"] +
         cs.parse_scan("npm", npm)["findings"])
t = cs.triage(mixed)
sevs = [f["severity"] for f in t["findings"]]
check("sorted worst-first", sevs == sorted(sevs, key=lambda s: cs._SEV_RANK[s]))
check("gitleaks flagged for review", any("secret" in " ".join(f["review_flags"]).lower()
      for f in t["findings"] if f["tool"]=="gitleaks"))

print("== remediation_hint ==")
rh = cs.remediation_hint({"package":"requests","fixed":"2.20.0","cwe":"CWE-89"})
check("rem ok", rh["ok"])
check("mentions upgrade", "2.20.0" in rh["remediation"])
check("mentions parameterise for CWE-89", "arameteri" in rh["remediation"])

print("== robustness: garbage in ==")
check("bad json → ok:false not crash", cs.parse_scan("semgrep","{not json")["ok"]==False)
check("unknown tool → ok:false", cs.parse_scan("nosuchtool","{}")["ok"]==False)
check("empty triage → ok:false", cs.triage([])["ok"]==False)
check("jsonl trufflehog parses",
      cs.parse_scan("trufflehog",
        '{"DetectorName":"AWS","Verified":true,"SourceMetadata":{"Data":{"Filesystem":{"file":"a.py","line":1}}}}')["findings"][0]["severity"]=="critical")

print("== scan_plan: intensity actually tunes the scan (regression guard) ==")
def _semgrep_cmd(intensity):
    steps = cs.scan_plan(".", "python", intensity)["steps"]
    return next((s["cmd"] for s in steps if s["tool"] == "semgrep"), "")
def _has_tool(intensity, tool):
    return any(s["tool"] == tool for s in cs.scan_plan(".", "auto", intensity)["steps"])
light, normal, deep = _semgrep_cmd("light"), _semgrep_cmd("normal"), _semgrep_cmd("deep")
check("light/normal/deep semgrep cmds all differ", len({light, normal, deep}) == 3)
check("light uses fast curated ruleset", "p/ci" in light)
check("normal uses auto ruleset", "--config auto" in normal and "p/security-audit" not in normal)
check("deep adds security-audit ruleset", "p/security-audit" in deep)
check("deep drops the file-size cap", "--max-target-bytes 0" in deep)
check("light skips the slow live-verifier", not _has_tool("light", "trufflehog"))
check("normal keeps the live-verifier", _has_tool("normal", "trufflehog"))
check("unknown intensity normalises to normal",
      cs.scan_plan(".", "auto", "banana")["intensity"] == "normal")

print(f"\n{'='*40}\n  {passed} passed, {failed} failed\n{'='*40}")
sys.exit(1 if failed else 0)
