"""Offline tests for lean-chat: conversational_turn must send the lean prompt on
plain talk and keep the full toolset the moment a message hints at an action."""
import sys
sys.path.insert(0, ".")
import basilisk_persona as kp

P = F = 0
def ck(n, c):
    global P, F
    if c: P += 1; print("  PASS", n)
    else: F += 1; print("  FAIL", n)

print("-- plain conversation -> LEAN (skip tools) --")
for m in ["hi", "hey basilisk", "thanks!", "how are you?", "what do you think about rust?",
          "ok cool", "lol nice", "good morning", "who are you",
          "yeah that makes sense", "basilisk", "thank you so much", "gn", "bye"]:
    ck(f"lean: {m!r}", kp.conversational_turn(m) is True)

print("-- any action / work -> KEEP TOOLS --")
for m in ["scan 10.0.0.5", "check my system", "run nmap", "benchmark juice shop",
          "find open ports", "what tools should i use for wifi", "read /etc/passwd",
          "start the server", "look up CVE-2023-1234", "list my files",
          "can you audit my box", "pull up my repo", "hey run that scan for me",
          "thanks now scan the host", "open the ftp directory"]:
    ck(f"tools: {m!r}", kp.conversational_turn(m) is False)

print("-- elliptical mid-conversation follow-ups -> KEEP TOOLS "
      "(the 'works cold, struggles after a chat' bug) --")
for m in ["do it", "ok do it", "yeah do it", "go on", "yeah go on", "go ahead",
          "keep going", "carry on", "continue", "proceed", "try again",
          "run it", "run that", "do that", "sure try that",
          "cool now the next one", "alright the next host", "again",
          "get to work", "onto the next target", "yeah go for it", "keep at it"]:
    ck(f"follow-up keeps tools: {m!r}", kp.conversational_turn(m) is False)

print("-- direct_answer_turn: QUESTION -> answer & stop (no mission) --")
for m in ["how does the oracle system decide a bug is confirmed?",
          "what does the kid injection payload actually do",
          "why did that sqli payload fail?", "should i use spray or brute here",
          "whats the difference between jku and jwk", "explain the mission loop",
          "how do i use jwt_attack", "is HS256 crackable if the secret is long?",
          "can you explain how autonomous mode works", "describe the memory system",
          "ok so how does auth_attack pick a wordlist?", "do you support websocket testing?",
          "which is better for blind sqli, timing or oob?", "what is a polyglot upload"]:
    ck(f"question: {m!r}", kp.direct_answer_turn(m) is True)

print("-- direct_answer_turn: TASK -> stays a mission --")
for m in ["scan example.com", "pentest 10.0.0.5", "find vulnerabilities in https://target.io",
          "run auth_attack against the login", "exploit the SSTI on the app", "do it",
          "go ahead", "ok do it", "yeah run that", "the next one", "continue",
          "enumerate the subdomains", "can you scan example.com",
          "could you brute force the admin panel", "what vulnerabilities does example.com have",
          "crack this jwt for me", "go", "nmap the target", "find zero days in this codebase"]:
    ck(f"task: {m!r}", kp.direct_answer_turn(m) is False)

ck("empty is not a direct-answer", kp.direct_answer_turn("") is False)
ck("bare greeting is not a direct-answer (conversational handles it)",
   kp.direct_answer_turn("hey") is False)

print("-- prompt sizes --")
lean = len(kp.build_system_prompt(agent_mode=False)) // 4
full = len(kp.build_system_prompt(agent_mode=True)) // 4
ck(f"lean prompt >6k tokens smaller ({lean} vs {full})", lean < full - 6000)
ck("empty message is not 'conversational'", kp.conversational_turn("") is False)
ck("long message keeps tools", kp.conversational_turn("hi " + "word " * 20) is False)

print(f"\n  {P} passed, {F} failed")
sys.exit(1 if F else 0)
