#!/usr/bin/env python3
"""Tests for zdayfind — variant-analysis source scanner. Stdlib-only."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from basilisk_ext import zdayfind as z  # noqa: E402

P = F = 0


def ck(name, cond):
    global P, F
    if cond:
        P += 1
        print(f"  PASS {name}")
    else:
        F += 1
        print(f"  FAIL {name}")


def classes(res):
    return {f["class"] for f in res.get("findings", [])}


print("== signature catalog ==")
cat = z.signature_catalog()
ck("catalog non-trivial", cat["ok"] and cat["count"] >= 25)
ck("every signature has cwe + severity",
   all(s.get("cwe") and s.get("severity") in ("critical", "high", "medium", "low")
       for s in cat["signatures"]))

print("== python sink detection ==")
py = (
    "import yaml, pickle, os\n"
    "x = yaml.load(data)\n"
    "y = pickle.loads(blob)\n"
    "os.system('ping ' + request.args['h'])\n"
    "cursor.execute('SELECT * FROM u WHERE n = ' + name)\n"
    "requests.get(request.args['url'])\n"
    "open('/data/' + request.args['f'])\n"
    "token = 'sk_live_ABCDEF1234567890abcdef'\n"
)
r = z.scan_code(py, "app.py")
ck("scan returns ok + findings", r["ok"] and r["count"] >= 6)
ck("catches unsafe yaml.load", any("YAML" in c for c in classes(r)))
ck("catches pickle RCE", any("pickle" in c for c in classes(r)))
ck("catches command injection", any("command injection" in c for c in classes(r)))
ck("catches SQLi", any("SQL injection" in c for c in classes(r)))
ck("catches SSRF", any("SSRF" in c for c in classes(r)))
ck("catches hardcoded secret", any("secret" in c.lower() for c in classes(r)))
ck("parameterised %s query is NOT flagged as SQLi",
   not any("SQL injection" in c for c in
           classes(z.scan_code("cursor.execute('SELECT * FROM u WHERE id = %s', (uid,))", "q.py"))))
ck("findings ranked worst-first (critical before medium/low)",
   [f["severity"] for f in r["findings"]] ==
   sorted([f["severity"] for f in r["findings"]],
          key=lambda s: {"critical": 0, "high": 1, "medium": 2, "low": 3}[s]))

print("== safe yaml is NOT flagged (low false positives) ==")
safe = "import yaml\nx = yaml.safe_load(data)\ny = yaml.load(data, Loader=yaml.SafeLoader)\n"
rs = z.scan_code(safe, "safe.py")
ck("yaml.safe_load / SafeLoader not flagged as unsafe yaml",
   not any("YAML" in c for c in classes(rs)))

print("== javascript sinks ==")
js = (
    "app.get('/x',(req,res)=>{ eval(req.query.code); });\n"
    "const u = _.merge({}, req.body);\n"
    "el.innerHTML = req.query.h;\n"
    "res.send(`<div>${req.query.name}</div>`);\n"
)
rj = z.scan_code(js, "server.js")
ck("catches eval code injection", any("code injection" in c for c in classes(rj)))
ck("catches prototype pollution", any("prototype pollution" in c for c in classes(rj)))
ck("catches XSS sink", any("XSS" in c for c in classes(rj)))
ck("JS template literal is NOT a false shell-exec",
   not any("command injection" in c for c in classes(rj)))

print("== language scoping ==")
ck("python-only sig not applied to a .js file",
   not any("pickle" in c for c in classes(z.scan_code("pickle.loads(x)", "x.js"))))
ck("ruby backtick exec caught in .rb",
   any("Backtick" in c for c in classes(z.scan_code("system(`id #{params[:h]}`)", "x.rb"))))

print("== tree scan + skip dirs ==")
with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    (root / "app.py").write_text("import os\nos.system('x '+request.args['h'])\n")
    vend = root / "node_modules" / "lib"
    vend.mkdir(parents=True)
    (vend / "bad.py").write_text("eval(request.args['c'])\n")  # must be skipped
    rt = z.scan_tree(str(root))
    ck("tree scan finds the real file", rt["ok"] and rt["count"] >= 1)
    ck("vendored node_modules is skipped",
       not any("node_modules" in f["file"] for f in rt["top"]))

print("== variant mode (Project-Zero workflow) ==")
with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    (root / "a.py").write_text("data = pickle.loads(user_blob)\n")
    (root / "b.py").write_text("x = pickle.loads(f.read())\n")
    (root / "c.py").write_text("print('unrelated')\n")
    v = z.find_variants("obj = pickle.loads(req.data)", str(root))
    ck("variant extracts the sink", v["ok"] and "pickle.loads" in v["sinks"])
    ck("variant finds both siblings", v["count"] >= 2)
    ck("variant flags input-reachable ones", any(m["reachable_from_input"] for m in v["matches"]))

print("== focus filter ==")
rf = z.scan_code(py, "app.py", focus=["py-pickle"])
ck("focus restricts to requested class", all(f["id"] == "py-pickle" for f in rf["findings"]) and rf["count"] >= 1)

print("== dispatch entry shape ==")
ck("zday_scan with no args errors cleanly", z.zday_scan()["ok"] is False)
ck("zday_scan code mode works", z.zday_scan(code="eval(x)", filename="a.js")["ok"])

print()
print(f"zdayfind: {P} passed, {F} failed")
sys.exit(1 if F else 0)
