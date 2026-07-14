"""Offline tests for basilisk_ext/oracle.py — the exploitation-verification
oracle: verdict engine (contains/absent/status/regex/differential/oob), the
per-engagement ledger, and the out-of-band canary listener (loopback only, no
external network)."""
import sys, tempfile, time, urllib.request
sys.path.insert(0, ".")
from pathlib import Path
from basilisk_ext import oracle as o

P = F = 0
def ck(n, c):
    global P, F
    if c: P += 1; print("  PASS", n)
    else: F += 1; print("  FAIL", n)

d = Path(tempfile.mkdtemp()); E = "case"

print("== VERDICT ENGINE ==")
a = o.arm(E, objective="dump users", technique="sqli", criterion_type="contains",
          criterion_value="admin@juice-sh.op", base_dir=d)
ck("arm returns id + pending", a["ok"] and a["id"] == "atk-0001" and a["verdict"] == "pending")
ck("contains hit -> confirmed",
   o.check(E, a["id"], evidence='{"email":"admin@juice-sh.op"}', base_dir=d)["verdict"] == "confirmed")
a = o.arm(E, criterion_type="contains", criterion_value="SECRET", base_dir=d)
ck("contains miss -> failed",
   o.check(E, a["id"], evidence="nope", base_dir=d)["verdict"] == "failed")
a = o.arm(E, criterion_type="absent", criterion_value="Invalid token", base_dir=d)
ck("absent (gone) -> confirmed",
   o.check(E, a["id"], evidence="welcome admin", base_dir=d)["verdict"] == "confirmed")
a = o.arm(E, criterion_type="absent", criterion_value="denied", base_dir=d)
ck("absent (present) -> failed",
   o.check(E, a["id"], evidence="access denied", base_dir=d)["verdict"] == "failed")
a = o.arm(E, criterion_type="status", criterion_value="500", base_dir=d)
ck("status match -> confirmed",
   o.check(E, a["id"], evidence="x", status=500, base_dir=d)["verdict"] == "confirmed")
ck("status w/o value supplied -> inconclusive",
   o.check(E, o.arm(E, criterion_type="status", criterion_value="200", base_dir=d)["id"],
           evidence="x", base_dir=d)["verdict"] == "inconclusive")
a = o.arm(E, criterion_type="regex", criterion_value=r"flag\{[a-f0-9]+\}", base_dir=d)
ck("regex match -> confirmed",
   o.check(E, a["id"], evidence="flag{deadbeef}", base_dir=d)["verdict"] == "confirmed")
a = o.arm(E, criterion_type="differential", base_dir=d)
ck("differential distinct -> confirmed",
   o.check(E, a["id"], evidence="X"*100 + " LEAK " + "Y"*90, baseline="X"*100, base_dir=d)["verdict"] == "confirmed")
a = o.arm(E, criterion_type="differential", base_dir=d)
ck("differential identical -> failed",
   o.check(E, a["id"], evidence="same", baseline="same", base_dir=d)["verdict"] == "failed")
a = o.arm(E, criterion_type="differential", base_dir=d)
ck("differential w/o baseline -> inconclusive",
   o.check(E, a["id"], evidence="x", base_dir=d)["verdict"] == "inconclusive")

print("== LEDGER ==")
st = o.status(E, base_dir=d)
ck("ledger counts confirmed", st["counts"]["confirmed"] >= 4)
ck("ledger counts failed", st["counts"]["failed"] >= 3)
ck("total == armed count", st["total"] == len([x for x in st["confirmed"]]) + len(st["open"]) + len(st["failed"]))
ck("bad criterion type rejected", o.arm(E, criterion_type="bogus", base_dir=d)["ok"] is False)
ck("check with no attempts -> error", o.check("emptyeng", evidence="x", base_dir=d)["ok"] is False)
ck("check unknown id -> error", o.check(E, "atk-9999", evidence="x", base_dir=d)["ok"] is False)
# blank id defaults to most-recent-open
a = o.arm(E, criterion_type="contains", criterion_value="Z", base_dir=d)
ck("blank id targets most-recent-open",
   o.check(E, "", evidence="Z here", base_dir=d)["id"] == a["id"])

print("== PERSISTENCE ==")
st2 = o.status(E, base_dir=d)
ck("ledger persisted across reload", st2["total"] == st["total"] + 1)

print("== OUT-OF-BAND CANARY (loopback) ==")
a = o.arm(E, objective="blind SSRF", technique="ssrf-blind", blind=True, base_dir=d)
ck("blind arm returns canary url", bool(a.get("canary_url")))
ck("blind arm forces oob criterion",
   o.status(E, base_dir=d)["open"][-1]["id"] == a["id"])
ck("pre-callback -> pending", o.check(E, a["id"], base_dir=d)["verdict"] == "pending")
fired = False
try:
    urllib.request.urlopen(a["canary_url"], timeout=5).read()
    fired = True
except Exception as ex:
    print("   (callback error:", ex, ")")
ck("canary callback fired", fired)
time.sleep(0.3)
ck("post-callback -> confirmed", o.check(E, a["id"], base_dir=d)["verdict"] == "confirmed")
ck("listen() reports callbacks", o.listen(base_dir=d)["hits"] >= 1)
ck("status shows oob listening", o.status(E, base_dir=d)["oob"]["listening"] is True)

print(f"\n  {P} passed, {F} failed")
sys.exit(1 if F else 0)
