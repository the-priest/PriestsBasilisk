"""Offline tests for kali_core.estimate_runtime — the command runtime awareness
that caps a hung server-start fast instead of blocking for the full window."""
import sys
sys.path.insert(0, ".")
import kali_core as k

P = F = 0
def ck(n, c):
    global P, F
    if c: P += 1; print("  PASS", n)
    else: F += 1; print("  FAIL", n)

ck("quick command -> ~30s", k.estimate_runtime("ls -la /tmp")["hard_timeout_seconds"] == 30)
ck("apt install -> 1800s", k.estimate_runtime("sudo apt-get install -y nmap")["hard_timeout_seconds"] == 1800)
ck("nmap -> long", k.estimate_runtime("nmap -sV 10.0.0.5")["kind"] == "long")
ck("git clone -> long", k.estimate_runtime("git clone https://x/y")["kind"] == "long")

for c in ["flask run", "python manage.py runserver", "python3 -m http.server 8000",
          "npm start", "npm run dev", "node server.js", "uvicorn app:app",
          "php -S localhost:8000", "rails s", "redis-server", "gunicorn app:app"]:
    r = k.estimate_runtime(c)
    ck(f"server {c!r} capped 25s", r["is_server"] and r["hard_timeout_seconds"] == 25)

ck("backgrounded server -> short", k.estimate_runtime("nohup npm start >/tmp/s.log 2>&1 &")["hard_timeout_seconds"] <= 15)
ck("trailing & -> backgrounded", k.estimate_runtime("python3 -m http.server 8000 &")["backgrounded"])
ck("&& is not background", not k.estimate_runtime("cd /tmp && ls")["backgrounded"])
ck("unknown -> 120s default", k.estimate_runtime("./weird_binary --x")["hard_timeout_seconds"] == 120)

note = k._timeout_note("npm start", 25)
ck("note has expected + won't finish", "expected" in note and "not going to finish" in note)
ck("server note says background", "background" in note.lower())
ck("non-server note omits server hint", "server/daemon" not in k._timeout_note("nmap -sV x", 1800))

print(f"\n  {P} passed, {F} failed")
sys.exit(1 if F else 0)
