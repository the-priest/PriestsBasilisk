import sys; sys.path.insert(0,".")
from basilisk_ext import pentest as p
P=F=0
def ck(n,c):
    global P,F
    if c: P+=1; print("  PASS",n)
    else: F+=1; print("  FAIL",n)

# 1) ledger-grounded writeup (the killer feature)
events=[
 {"step":1,"command":"nmap -sV -p8080 10.0.0.5","reason":"identify the service","rc":0,"ok":True,"artifact":"default.artifacts/step-0001.txt","stdout_sha256":"a1b2c3d4e5f6aabbccdd"},
 {"step":2,"command":"curl -s http://10.0.0.5:8080/api/login -d 'user=admin&password=hunter2'","reason":"test default creds","rc":0,"ok":True,"artifact":"default.artifacts/step-0002.txt","stdout_sha256":"ffeeddccbbaa99887766"},
]
r=p.attack_writeup(access={"level":"authenticated admin","host":"10.0.0.5","account":"admin","vector":"default credentials"},
                   target="acme-web", scope_note="10.0.0.0/24, written authorisation on file",
                   impact="Full admin of the app; read/write of all tenant data.",
                   remediation="Force a credential change on first login; disable the default account.",
                   root_cause="Shipping default admin credentials enabled in production.",
                   ledger_events=events)
ck("ledger writeup ok", r["ok"])
ck("grounded_in_ledger flag", r["grounded_in_ledger"] is True)
md=r["report_markdown"]
ck("has Attack path", "Attack path (reproducible)" in md)
ck("weaves ledger commands", "nmap -sV" in md)
ck("shows evidence hash", "a1b2c3d4e5f6" in md)
ck("REDACTS the password in curl", "hunter2" not in md and "<redacted>" in md)
ck("has Remediation section", "### Remediation" in md)
ck("has Verification section", "### Verification" in md)
ck("access summary rendered", "authenticated admin" in md and "via default credentials" in md)

# 2) narrative-only (no ledger)
r2=p.attack_writeup(access="RCE as www-data",
     steps=[{"action":"Upload webshell via unrestricted file upload","command":"curl -F 'f=@s.php' http://t/upload","result":"200; shell at /uploads/s.php","significance":"arbitrary code execution"},
            {"action":"Confirm execution","command":"curl http://t/uploads/s.php?c=id","result":"uid=33(www-data)","significance":"code runs as the web user"}],
     target="t", impact="Server compromise.", remediation="Validate upload type; store outside webroot.")
ck("narrative writeup ok", r2["ok"])
ck("narrative step count", r2["step_count"]==2)
ck("narrative renders commands", "webshell" in r2["report_markdown"].lower())

# 3) honesty: thin input tells the truth instead of inventing
r3=p.attack_writeup(access="got in somehow")
ck("thin writeup still ok", r3["ok"])
ck("thin writeup admits missing steps", any("step" in t for t in r3["completeness_todo"]))
ck("thin writeup flags in body", "must list the reproducible steps" in r3["report_markdown"])

# 4) empty → honest failure
ck("empty → ok:false", p.attack_writeup()["ok"]==False)

print(f"\n  {P} passed, {F} failed")
sys.exit(1 if F else 0)
