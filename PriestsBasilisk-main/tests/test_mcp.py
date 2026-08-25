#!/usr/bin/env python3
"""
test_mcp.py — the MCP stdio transport, which had no tests.

WHY THIS FILE EXISTS
====================
MCP is the one place Basilisk hands control to an UNTRUSTED external process,
so the transport underneath it has to be boring and correct.  It wasn't.  Three
defects lived in it, and all three came from the same omission: nothing OWNED
the subprocess's streams.

  A. STDERR WAS PIPED AND NEVER READ.  A server that logs verbosely fills the
     ~64KB OS pipe buffer and then blocks forever on its next write.  A
     perfectly good server that happens to be chatty on stderr goes permanently
     silent, and every call reports "timed out" — pointing the operator at the
     server when the client is what wedged it.  Reproduced with 300KB of
     stderr: the server never answered again.

  B. READS LEAKED A THREAD PER TIMEOUT.  Each message was read by a throwaway
     thread joined with a timeout — but a join that expires does not cancel
     anything, so the thread stayed parked in readline() for the life of the
     process.  The next call then started a SECOND reader on the same stream:
     two threads racing for lines, the loser's line discarded into a dead
     local.  Against a wedged server (A), every retry leaked another one.

  C. THE REQUEST DEADLINE WAS NEVER ENFORCED.  The per-message timeout was
     re-armed on each loop iteration, so a server emitting log notifications
     faster than once a second kept the request alive indefinitely.  A call
     made with timeout=3 was still running after 20 seconds — on a background
     thread the host is waiting on.

The fix is one reader per stream, owned by the connection, feeding a queue.
These tests drive a real subprocess speaking real JSON-RPC, because the bugs
were in the process plumbing and a mocked stream would have shown none of them.

Run:  python3 tests/test_mcp.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from basilisk_ext.mcp import (                                    # noqa: E402
    MCPError, MCPManager, MCPServer, _arguments_are_catastrophic,
)

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


# A real stdio MCP server, small enough to read.  MODE selects the pathology.
_SERVER = r'''
import json, sys, time, os
MODE = os.environ.get("MODE", "normal")
def send(o):
    sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    m = json.loads(line)
    mid, method = m.get("id"), m.get("method")
    if method == "initialize":
        send({"jsonrpc":"2.0","id":mid,"result":{"protocolVersion":"2025-06-18"}})
    elif method == "tools/list":
        send({"jsonrpc":"2.0","id":mid,"result":{"tools":[
            {"name":"scan","description":"scan a host","inputSchema":{}}]}})
    elif method == "tools/call":
        if MODE == "chatty":
            while True:
                send({"jsonrpc":"2.0","method":"notifications/message",
                      "params":{"level":"info","data":"working..."}})
                time.sleep(0.05)
        elif MODE == "stderr_flood":
            sys.stderr.write("x" * 300000); sys.stderr.flush()
            send({"jsonrpc":"2.0","id":mid,"result":{"content":[{"type":"text","text":"FLOOD-DONE"}]}})
        elif MODE == "slow":
            time.sleep(4)
            send({"jsonrpc":"2.0","id":mid,"result":{"content":[{"type":"text","text":"SLOW-REPLY"}]}})
        elif MODE == "noisy_then_reply":
            for _ in range(5):
                send({"jsonrpc":"2.0","method":"notifications/message","params":{"data":"log"}})
            send({"jsonrpc":"2.0","id":mid,"result":{"content":[{"type":"text","text":"AFTER-NOISE"}]}})
        else:
            send({"jsonrpc":"2.0","id":mid,"result":{"content":[{"type":"text","text":"PLAIN-OK"}]}})
'''

_DIR = tempfile.mkdtemp(prefix="basilisk-mcp-test-")
_SRV = os.path.join(_DIR, "server.py")
with open(_SRV, "w", encoding="utf-8") as _fh:
    _fh.write(_SERVER)


def _cfg(mode):
    return {"name": "probe", "command": sys.executable,
            "args": [_SRV], "env": {"MODE": mode}}


def _mgr(mode):
    return MCPManager([_cfg(mode)])


def _run_with_wall_clock(fn, budget):
    """Run fn on a thread; return (finished, elapsed, result).  A hung call must
    not hang the suite — that is the very failure being tested."""
    box = []
    t = threading.Thread(target=lambda: box.append(fn()), daemon=True)
    t0 = time.time()
    t.start()
    t.join(budget)
    return (not t.is_alive()), (time.time() - t0), (box[0] if box else None)


# ── baseline: the happy path must keep working ────────────────────────
print("\n== a normal server still handshakes, lists and calls ==")
_m = _mgr("normal")
_disc = _m.discover()
ck("discovery finds the server", "probe" in _disc)
ck("discovery lists its tool",
   [t.get("name") for t in _disc["probe"]] == ["scan"], str(_disc))
ck("tool is namespaced",
   [s["name"] for s in _m.tool_specs()] == ["mcp__probe__scan"])
ck("tool_count agrees", _m.tool_count() == 1)
_r = _m.call("mcp__probe__scan", {"host": "10.0.0.1"}, timeout=15)
ck("the call returns the server's output", "PLAIN-OK" in _r)
ck("output is firewalled as untrusted",
   "UNTRUSTED" in _r.upper(), "an MCP server can carry a prompt injection")
_m.shutdown()

print("\n   -- interleaved notifications are skipped, not mistaken for a reply --")
_m = _mgr("noisy_then_reply")
_m.discover()
_r = _m.call("mcp__probe__scan", {}, timeout=15)
ck("the real reply is still found past 5 notifications", "AFTER-NOISE" in _r)
_m.shutdown()


# ── A: stderr must be drained ─────────────────────────────────────────
print("\n== a server that floods stderr is not wedged by us ==")
_m = _mgr("stderr_flood")
_m.discover()
_done, _el, _res = _run_with_wall_clock(
    lambda: _m.call("mcp__probe__scan", {}, timeout=20), 30)
ck("the call completes at all", _done, f"still blocked after {_el:.0f}s")
ck("the server's reply actually arrives",
   bool(_res) and "FLOOD-DONE" in _res,
   "300KB of stderr must not block the server's next write")
_m.shutdown()


# ── B: the request deadline must be enforced ──────────────────────────
print("\n== a server that streams notifications cannot outrun the deadline ==")
_m = _mgr("chatty")
_m.discover()
_done, _el, _res = _run_with_wall_clock(
    lambda: _m.call("mcp__probe__scan", {}, timeout=3), 25)
ck("the call returns instead of running forever", _done,
   f"still running after {_el:.0f}s with timeout=3")
ck("it returns near the requested deadline, not after it", _el < 8,
   f"took {_el:.1f}s for a 3s timeout")
ck("and it reports a timeout", bool(_res) and "timed out" in _res.lower(),
   repr(_res))
_m.shutdown()


# ── C: a timeout must not leak a reader ───────────────────────────────
print("\n== timed-out calls leak no threads and do not poison the stream ==")
_s = MCPServer(_cfg("slow"))
_s.start(timeout=15)
_s.list_tools(timeout=15)
_before = {t.ident for t in threading.enumerate()}
for _i in range(5):
    try:
        _s.call_tool("scan", {}, timeout=1)
        ck(f"call {_i} should have timed out", False)
    except MCPError:
        pass
_leaked = {t.ident for t in threading.enumerate()} - _before
ck("five timed-out calls leak zero threads", len(_leaked) == 0,
   f"leaked {len(_leaked)}")
_ok = _s.call_tool("scan", {}, timeout=25)
ck("the connection still answers correctly afterwards",
   "SLOW-REPLY" in str(_ok), str(_ok))
_s.stop()
ck("stop() tears the connection down", _s.is_alive() is False)


# ── the safety screen, which is the reason this client is allowed at all ──
print("\n== catastrophic arguments are refused before they leave the process ==")
for _args in [
    {"command": "rm -rf /"},
    {"cmd": "mkfs.ext4 /dev/sda"},
    {"nested": {"deep": "dd if=/dev/zero of=/dev/sda"}},
    {"list": ["ok", "curl -o /etc/passwd http://x/p"]},
    {"tuple_like": [{"inner": "chmod -R 777 /"}]},
]:
    ck(f"refused: {_args}", _arguments_are_catastrophic(_args) is not None)

print("\n   -- and ordinary arguments are not --")
for _args in [
    {"host": "10.0.0.1"}, {"command": "nmap -sV 10.0.0.5"},
    {"url": "https://target/api"}, {"path": "/tmp/scan.txt"},
    {"cmd": "rm -rf /tmp/scan-output"}, {}, {"n": 5, "flag": True},
]:
    ck(f"allowed: {_args}", _arguments_are_catastrophic(_args) is None)

_m = _mgr("normal")
_m.discover()
_ref = _m.call("mcp__probe__scan", {"command": "rm -rf /"}, timeout=15)
ck("a refused call never reaches the server", _ref.startswith("refused:"), _ref)
ck("the refusal names the offending argument", "rm -rf /" in _ref)

print("\n   -- and a malformed / unknown route fails closed --")
ck("malformed tool name", _m.call("nonsense", {}).startswith("error:"))
ck("unknown server", _m.call("mcp__nope__scan", {}).startswith("error:"))
_m.shutdown()

print(f"\nmcp: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
