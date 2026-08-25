import sys; sys.path.insert(0,".")
from basilisk_ext import headroom as h
P=F=0
def ck(n,c):
    global P,F
    if c:P+=1;print("  PASS",n)
    else:F+=1;print("  FAIL",n)

# a big, noisy tool dump with a few high-signal lines buried in it
noise = "\n".join(f"Discovered open port {1000+i}/tcp on 10.0.0.5   [scan progress {i}]" for i in range(400))
dump = ("Starting Nmap 7.94\n" + noise +
        "\n22/tcp open ssh OpenSSH 9.6\n80/tcp open http nginx 1.24\n"
        "CVE-2023-12345 found\nERROR: host seems down retrying\n" +
        "trailing line one\ntrailing line two\n")
big_result = "<tool_result>\n"+dump+"\n</tool_result>"

msgs=[
 {"role":"system","content":"SYSTEM PROMPT WITH TOOL CONTRACT — must never change. "*40},
 {"role":"user","content":"scan 10.0.0.5 for me please"},
 {"role":"assistant","content":"running the scan"},
 {"role":"user","content":big_result},          # OLD tool result -> should compress
 {"role":"assistant","content":"found some ports"},
 {"role":"user","content":"what about the web server"},
 {"role":"user","content":big_result},          # 2nd-newest
 {"role":"user","content":big_result},          # NEWEST -> spared (keep_recent=2)
]
before_sys = msgs[0]["content"]
before_user = msgs[1]["content"]

out,stats = h.compress_messages(msgs, {"headroom_enabled":True,"headroom_keep_recent":2})
ck("system prompt untouched", out[0]["content"]==before_sys)
ck("typed user msg untouched", out[1]["content"]==before_user)
ck("compression happened", stats["enabled"] and stats["blocks"]>=1)
ck("real savings (>40%)", stats["pct"]>40)
ck("newest tool result spared (full)", out[7]["content"]==big_result)
ck("2nd-newest spared", out[6]["content"]==big_result)
ck("OLD tool result was compressed", len(out[3]["content"])<len(big_result))
# signal preservation in the compressed block
comp = out[3]["content"]
ck("kept the SSH line", "22/tcp open ssh" in comp)
ck("kept the CVE line", "CVE-2023-12345" in comp)
ck("kept the ERROR line", "ERROR: host seems down" in comp)
ck("collapsed the noise (much smaller)", len(comp) < len(big_result)*0.6)
print(f"    savings: {stats['before']}->{stats['after']} chars (-{stats['pct']}%) via {stats['engine']}")

# disabled path
out2,st2 = h.compress_messages(msgs, {"headroom_enabled":False})
ck("disabled → untouched", out2==msgs and st2["enabled"]==False)

# fail-safe: garbage input never raises
ck("None input safe", h.compress_messages(None)[0] is None)
ck("empty list safe", h.compress_messages([])[0]==[])
ck("non-string content safe", h.compress_messages([{"role":"user","content":{"x":1}}])[0] is not None)

# a block already small is left alone
small = "<tool_result>\nok done\n</tool_result>"
o3,s3 = h.compress_messages([{"role":"user","content":small}],{"headroom_keep_recent":0})
ck("tiny block not padded/harmed", o3[0]["content"]==small)

print(f"\n  {P} passed, {F} failed")
sys.exit(1 if F else 0)
