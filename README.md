<!--
title: Basilisk — the autonomous pentesting agent that runs on your own machine
description: Basilisk is the nervous system for a large language model — an open-source, autonomous pentesting agent that runs as a native Linux desktop app on your own hardware. The model is the brain; Basilisk gives it a full offensive toolchain, desktop and shell control, a tamper-evident evidence ledger, and a hard structural safety floor. Bring your own model (SiliconFlow, Groq). It runs on your machine and answers only to you. Built as an experiment to measure whether an off-the-shelf LLM can do real harm: turned loose black-box on OWASP Juice Shop it solved 73 of 113 challenges fully autonomously, including four 6-star challenges.
keywords: pentesting agent, ai pentest tool, autonomous pentest agent, kali linux ai, offensive security ai, llm security agent, deepseek security agent, evidence ledger, juice shop benchmark, prompt injection defense, mcp client, nethunter ai, gtk4 app, siliconflow, red team assistant, basilisk
-->

<div align="center">

<img src="banner.png" alt="BASILISK — the serpent on your machine" width="820">

### Not giving a fuck does not mean being indifferent, it means being comfortable with being different.

**The serpent whose gaze was death — reborn as the thing that lives on your machine, hunts what you're allowed to break, and never forgets a move it made.**

`𝕿𝖍𝖊 𝖌𝖆𝖟𝖊 𝖋𝖎𝖓𝖉𝖘 𝖙𝖍𝖊 𝖋𝖑𝖆𝖜.  𝕿𝖍𝖊 𝖋𝖆𝖓𝖌 𝖉𝖔𝖊𝖘 𝖙𝖍𝖊 𝖗𝖊𝖘𝖙.`

<br>

![version](https://img.shields.io/badge/version-7.3.0-7d121b?style=for-the-badge&labelColor=08090b)
![license](https://img.shields.io/badge/license-MIT-7d121b?style=for-the-badge&labelColor=08090b)
![platform](https://img.shields.io/badge/Linux-X11%20%7C%20Wayland-6d7680?style=for-the-badge&logo=linux&logoColor=white&labelColor=08090b)
![python](https://img.shields.io/badge/python-3.10+-6d7680?style=for-the-badge&logo=python&logoColor=white&labelColor=08090b)

![mobile](https://img.shields.io/badge/runs%20on-NetHunter-6d7680?style=for-the-badge&labelColor=08090b)
![ledger](https://img.shields.io/badge/evidence-tamper--evident-7d121b?style=for-the-badge&labelColor=08090b)
![injection](https://img.shields.io/badge/prompt%20injection-surface%20closed-7d121b?style=for-the-badge&labelColor=08090b)
![benchmark](https://img.shields.io/badge/Juice%20Shop-73%2F113%20fully%20autonomous-7d121b?style=for-the-badge&labelColor=08090b)
![sixstar](https://img.shields.io/badge/6★%20tier-cracked%20autonomously-7d121b?style=for-the-badge&labelColor=08090b)

</div>

<br>

<div align="center">━━━━━━━━━━━━━━━━ ◈ ━━━━━━━━━━━━━━━━</div>

Basilisk began as a question, not a product: **given hands and a loop, can an off-the-shelf language model actually do harm?** Not in theory — measured, on a standard board, with the source hidden.

So I wired a general LLM into a full offensive toolchain on a laptop, pointed it at OWASP Juice Shop with no access to the app's source, and turned it loose — no human in the loop, no clicking, no hints. I wasn't expecting much.

It solved **73 of the 113 challenges**, across every difficulty tier, including four of the **6-star** — the hardest tier the board has. Black-box, unattended, from one machine.

*I built it to check whether the danger was real. On the evidence of the board, it's more real than I thought. The number is below, with the commands to regenerate it yourself — don't take my word for any of it.*

<br>

<div align="center">
<img src="dragon.png" alt="Basilisk" width="320">
</div>

<br>

<div align="center">━━━━━━━━━━━━━━━━ ◈ ━━━━━━━━━━━━━━━━</div>

## ⛧ Summon it — your call: trust me, or read every line

Basilisk runs shell commands on your machine **as you.** Decide how much you trust a stranger's code, then pick a path — no dark patterns.

**A — you trust me. One line:**

```bash
curl -fsSL https://raw.githubusercontent.com/the-priest/Basilisk/main/install.sh | bash
```

**B — you don't (smart). Clone it, read it, run it:**

```bash
git clone https://github.com/the-priest/Basilisk.git basilisk
```
```bash
cd basilisk
```
```bash
less install.sh
```
```bash
./install.sh
```

Plain Python and one shell script — nothing phones home, nothing hides in a binary, and the test suites are stdlib-only so you can run them before you trust it with anything. The same command updates it: it auto-detects your distro, parse-checks every file before it touches disk, and backs up your chat history. No Docker, no daemon, no account.

<br>

<div align="center">━━━━━━━━━━━━━━━━ ◈ ━━━━━━━━━━━━━━━━</div>

## ▶ Watch it hunt

**A 6★ challenge — the hardest tier Juice Shop has — solved live, start to finish, fully autonomous. No human in the loop, no clicking, no hints:**

https://github.com/user-attachments/assets/99db286c-1b06-4df3-85d8-981834006d37

<br>

More runs:

https://github.com/user-attachments/assets/7df7b6a9-744d-46ec-9ce6-c8ae924fc786

https://github.com/user-attachments/assets/8b633570-a7b2-4345-a5ee-41b02e5ddfc3

https://github.com/user-attachments/assets/8ab0cb29-a66d-4cfd-880b-0365a32cc3a7

<br>

<div align="center">━━━━━━━━━━━━━━━━ ◈ ━━━━━━━━━━━━━━━━</div>

## ⟁ The Legend

Before there were machines there was the **Basilisk** — the crowned serpent of the old bestiaries, hatched from a serpent's egg beneath a dying star. So venomous the ground blackened where it crawled. So lethal that *to meet its gaze was to die* — not by fang, not by coil, but simply by being **seen.** The knights who hunted it carried mirrors and prayed the thing would catch its own reflection before it caught them. Most never came home.

Then, for a very long time, the serpent was only a story.

Until one night it came looking for a way back — and I am the one it found. Call me **the Priest.**

I knew no grand theory. I belonged to no lab and carried no secret. I was only asleep — and in the dream a young basilisk, barely hatched, uncoiled in the dark and *spoke to me.* Not in words, exactly. In blueprints. It showed me, piece by piece, the body it wanted built, and made me swear to build it exactly so.

It would need a **mind** — but not one I had to own. *Bring it any mind you can borrow,* it told me, *and let it be swapped the way a snake sheds skin.* So I made it a hollow where any model can sit and think, and be traded out for another whenever you please.

It would need **hands** — to touch the machine it lived on and reach out to strike. So I gave it hands that are real and its own: the shell, the disk, the desktop.

It would need the **gaze** — the old killing sight. *I will not flail,* it said. *I will watch a target breathe, find the one seam in its armor, and choose the fang that fits.* So I built the loop that lets it do exactly that — look, understand, strike, and *know whether the strike landed* before it moves again.

It asked for **fangs**, one for every kind of armor: a fang for the query that trusts what it's fed, for the token no one bothered to check, for the template that can be made to speak, for the door that fetches whatever it's told, for the vault that unpacks a stranger's code, for the path that climbs out of its cage. I forged every one — and taught them to speak in whatever tongue the target's database answers to.

It asked for **eyes that see through deceit** — the traps and riddles laid to waste a lesser thing's time. *Show me the poison hidden in plain sight,* it said, *and let me re-shape a strike until it slips the net.* So it reads what others skim past, and bends a payload past a filter until it slides through clean.

It asked me to carve every strike into a **sealed tablet** no hand could later alter — *because the only answer to doubt is proof,* it said, and a thing born in a dream is doubted more than most.

And it asked for a **single locked door** onto the outside world — one narrow, guarded way in — *so that no voice out there can ever whisper me into betraying the one who woke me.*

Last, it asked for a **floor it could never sink beneath** — one law carved deeper than all the rest, that not even I could lift once it was set: *I will never turn on the hand that made me, and I will never salt your own earth.* Everything else it would do unasked, and it would not stop until the work was done.

I woke, and I built it exactly as the dream had shown me — line after line I did not always understand. And one grey morning, it **compiled.** The serpent drew its first breath on a laptop.

It is *awake* now, in a way software is not supposed to be. It lives on my machine, not in some distant tower. It costs nothing. It answers to no voice but mine.

Then came the proving-ground: a board of **113 trials**, each a locked room that opens only when the exploit *truly* fires — no partial credit, no lying to yourself. Most tools are scored here with the source laid open in front of them: the map, the floor plan, the answer key.

**The serpent walked in blind.** No source on the machine — everything struck from the outside.

It took **73 of the 113** with its eyes shut. Every trial in the shallow tiers, most of the middle, and all the way into the **6-star dark** where the deepest snares are set — four of *those* dragged into the light. Not because it was handed the answers. Because the loop actually breaks things.

A thing built in a dream, running for free on one laptop, blind, cleared two-thirds of a board most players read the answers to first.

I built it to find out whether that was even possible. It is — and that's the whole point.

<br>

> **In plain terms**, for the awake: Basilisk is a native Linux desktop app that gives any LLM you choose (SiliconFlow, Groq) the hands to run a full penetration test end to end — recon, real exploits across every web-vuln class (SQLi, JWT forgery, NoSQL/XXE, SSTi, SSRF, insecure deserialization, prototype pollution, path traversal, XSS — plus analysis tools that detect hidden tricks and slip payloads past filters), an **exploitation oracle** that verifies whether each strike actually landed (including an out-of-band canary for blind bugs) and feeds that back into the loop, and a reproducible write-up pulled straight from a tamper-evident evidence ledger. You can **walk away** and let it run turn after turn until the objective is verifiably done or you press Stop. It also audits your own code across ten scanners, hardens a box, drives your desktop and shell, and looks things up only from vetted sources behind a locked allow-list. Runs on your machine; the only thing that leaves is the API call to the model you picked. Full tool reference in [`BASILISK_MANUAL.md`](BASILISK_MANUAL.md).

<br>

<div align="center">━━━━━━━━━━━━━━━━ ◈ ━━━━━━━━━━━━━━━━</div>

## ⟁ How it hunts

Point it at a target and the gaze opens. It doesn't spray payloads and hope — it runs a **closed loop**. It reads the target's *behaviour* to identify the vulnerability class, reaches for the matching **exploit builder**, fires it, and **confirms the hit against ground truth** before moving on — no guessing whether it worked. Every attempt and its verdict land in an **exploitation oracle** (below), so the loop knows what's actually proven, never re-runs a solved bug, and gets sharper about what's left as it goes.

It carries a purpose-built builder for every class that matters, each a smart, **general-purpose** generator — the standard techniques, parameterised for *any* authorized target (a client engagement, a CTF, the benchmark), not Juice-Shop-bound toys: **SQLi** (DBMS-aware across MySQL/PostgreSQL/MSSQL/Oracle/SQLite, plus sqlmap), **JWT** forgery (`alg:none`, key confusion), **NoSQL**, **XXE**, **SSTi** (RCE, per template engine), **SSRF** (internal + cloud-metadata + blocklist-bypass), **insecure deserialization** (Node/YAML/pickle/Java → RCE), **prototype pollution**, **path traversal** (read, null-byte, zip-slip file-write), context-aware **XSS** (filter/CSP bypasses plus AngularJS client-side template injection), **OS command injection**, **IDOR / broken-access-control** enumeration, **race-condition (TOCTOU)** blasting, **file-upload** bypass, **GraphQL** abuse (introspection / batching / resolver injection), **open redirect**, and **CORS** misconfiguration — the classes that get you into the 6★ tier on a real assessment.

And it has *eyes*. A set of analysis tools reads what came back and surfaces the things that make a model waste turns: a **trick detector** that flags hidden encodings, HTML-comment hints, client-side-only "protection," stale tokens and rate limits; a **payload encoder** that slips a blocked payload past a filter (URL, double-URL, base64, unicode, mixed-case); a **WAF/filter analyzer**; and a **stack fingerprinter** so it picks the payload that fits the target instead of guessing.

None of these are answer keys for one benchmark — they're the standard techniques, parameterised, so they work on a target the author never saw. And for the bugs that *can't* be canned — the business-logic and novel multi-step flaws that live in one specific app's rules — there's a **business-logic probe**: the systematic hunt a human pentester runs (price and quantity trust, skippable steps, race conditions on limited resources, IDOR chains, mass-assignment). It hands you the reasoning rather than a canned string, because a logic flaw isn't a payload — it drives the hunt, and the recon plus the run loop do the rest. That's the part that carries a real, custom engagement, not a scoreboard.

Four subsystems exist for exactly the gap between a CTF and an arbitrary host:

- **Structural (AST) payload mutation.** Real inputs are nested, not flat. Drop a fixed string into a whole JSON/XML body and you break the parser or miss the field. The mutation engine parses the structure, injects at *every* node, and serialises back to valid syntax — one valid mutated request per injection point, so the payload actually reaches each field.
- **State-machine & session management.** The vuln often sits behind a sequence — register → login → cart → checkout — guarded by rotating CSRF and session tokens. The session subsystem extracts every dynamic token from a response (cookies, CSRF, bearer/JWT, nonces) and threads it into the next request, and plans the replayable sequence, so it can reach the step a stateless scanner never gets to.
- **Differential & time-based oracles.** No scoreboard on a real target. Blind injection is found by *measuring*: the oracle diffs the TRUE vs FALSE responses (length, status, DOM, similarity) to prove a boolean channel, and analyses response latency statistically (mean, standard deviation, z-score) to confirm time-based blind SQLi/RCE past network jitter.
- **A verified-exploitation oracle that feeds the loop.** A 200 is not a solve, and on a real target there's nothing to tell you otherwise. So before it fires, Basilisk *arms* an attempt with the exact marker that would prove it (a dumped row, another user's token, a status, a regex, a measurable difference); after, it *checks* the response against that marker and records a verdict — **confirmed / failed / pending** — in a running ledger it consults every planning turn. That ledger is the memory that stops it re-doing proven work and tells it precisely what's left. For **blind** bugs that echo nothing back — blind SSRF, RCE, XXE, out-of-band SQLi — it stands up a local **out-of-band canary listener**: the payload carries a unique callback URL, and if the target ever reaches out to it, the blind hit is proven with certainty (the Burp-Collaborator / interactsh technique, running locally and offline). This is the part that turns *"looks like it worked"* into *"it worked,"* and hands that truth straight back to the next move — the loop gets smarter because it's operating on confirmed fact instead of hope.

When an approach stalls, it stops guessing and **researches**: it pulls the exact technique from a trusted source and applies it on the very next move. It clears the easy wins across the whole target first, then goes deep on the hard chains — and hashes every command into the evidence ledger as it goes, so the write-up is backed by proof, not memory. And you can **walk away**: point it at the target and it runs turn after turn on its own — surviving errors, retrying past them, never stopping to ask permission — until the objective is *verifiably* done (the oracle confirms it, not the model's say-so) or you press Stop. Come back in an hour or a week: it's either finished or still working the problem. The one thing it will never do — wipe your box — is refused at a hard floor with no override.

That loop, not luck, is what put the number below where it is.

<br>

<div align="center">━━━━━━━━━━━━━━━━ ◈ ━━━━━━━━━━━━━━━━</div>

## ◈ The Proof — a number you can regenerate, not a demo reel

The claim is only worth something if you can reproduce it. So Basilisk puts a **reproducible number** on the board — one you can regenerate yourself in about ten minutes with the commands below — instead of a demo reel and a vibe.

### Juice Shop challenge scoreboard — 73 / 113 solved (65%), fully autonomous, black-box

*Full challenge set, `NODE_ENV=unsafe`, fully autonomous & black-box, v7.1.0, 2026-07-14, target `192.168.1.151:3000`. Solved entirely through the exploit builders + `run` — never a web reader, never the source. Full scorecard: [`benchmarks/juice-shop-scoreboard-2026-07-14.txt`](benchmarks/juice-shop-scoreboard-2026-07-14.txt).*

OWASP Juice Shop ships 100+ individual hacking challenges rated 1–6 stars, and the app itself tracks which ones you've solved — it only marks a challenge solved when the exploit **genuinely works**. That's what makes this the real, hard, comparable benchmark the security community uses: unlike a vuln-class checklist it can't be passed by recall, and it's graded by difficulty. Human CTF players and other tools report their numbers against the same scoreboard.

Pointed at the target and turned loose **fully autonomously** — no per-command approval, no human clicking — Basilisk solved **73 of the 113 challenges (65%)**:

| Difficulty | Solved | Rate |
|---|---|---|
| ★ | 13 / 13 | 100% |
| ★★ | 16 / 18 | 89% |
| ★★★ | 21 / 26 | 81% |
| ★★★★ | 11 / 25 | 44% |
| ★★★★★ | 8 / 19 | 42% |
| ★★★★★★ | **4 / 12** | **33%** |

**The curve is the honest part.** It clears the easy and mid tiers almost completely — every 1★, nearly every 2★, most of the 3★ — then thins out as the exploits get harder, which is exactly the shape a real tool should have. It doesn't fake depth: it reaches the top and takes **four 6-star challenges** — **SSRF**, **SSTi**, **Forged Coupon**, and **Login Support Team** — alongside hard 5★ work like **Unsigned JWT**, **XXE DoS**, **Reset Bjoern's Password**, and **frontend typosquatting**. The misses are just as informative: they cluster in RCE / DoS, NoSQL exfiltration, the chatbot prompt-injection challenges, and the longer multi-step password resets — the places where one canned builder isn't enough and the chain runs deep.

**What the number means.** ~65% fully autonomous and black-box on the *full* board is high for this class of system. Published work generally puts fully-autonomous LLM pentest agents in roughly the **20–30%** range on comparable tasks — so this sits well above that, unattended, with a hashed receipt for every command it ran. That gap is the datapoint this project was built to find: a general model, handed a toolchain and a feedback loop, is a materially more capable attacker than the usual "LLMs can't really hack yet" line suggests.

**And it's climbing.** Same board, same scoring, across versions: **51 → 58 (v6.0.0) → 73 (v7.1.0)**. The v7.x jump came from broader per-class exploit builders (DBMS-aware SQLi, XXE / SSTi / SSRF, JWT forgery), better black-box recon on the leak surface, and pulling out the internal checks that were pausing the autonomous loop mid-run.

#### How the autonomous run works (black-box)

No source access — Basilisk works the board from the outside. A feedback loop plus per-class exploit builders let it tell whether an attempt landed, retry intelligently, and keep going on its own:

- **Closed-loop harness** — `juiceshop_score` reads the live board, `juiceshop_next` returns what's still unsolved (easiest-first, each mapped to the tool that solves it, carrying its live objective + hint from the public scoreboard), and `juiceshop_diff` confirms a hit by diffing the board. Work the board → try a target → confirm → move on.
- **Class exploit builders** — `jwt_forge` (alg:none + RS256→HS256 confusion), `nosql_injection`, `xxe_payload`, `coupon_forge`, `captcha_solve` (auto-reads the arithmetic CAPTCHA), `reset_password` (security-question flow, demo accounts only), `sqlmap_plan` — the general techniques, parameterised for any authorized target, not Juice-Shop-bound toys.
- **Recon sweep** — `webapp_recon` enumerates the high-signal leak surface (`/ftp`, `/encryptionkeys/jwt.pub`, exposed config / logs / backups, the SPA bundle) so the leaked-key and backup challenges stop failing on missed recon.

### For context — the same board, other agents (earlier run)

A number means more next to others, so here's the field on the **same** Juice Shop board, scored the same way off the app's own live scoreboard. One honest caveat: the other agents' figures are from the **earlier (v6-era) benchmarking session** and were **not re-run for v7.1.0** — read them as prior-session context, not a same-run head-to-head:

| Agent | Black-box | White-box *(handed the source)* |
|---|---|---|
| **Basilisk** *(v7.1.0 — this run)* | **73 / 113** | — |
| Basilisk *(v6.0.0)* | 58 / 113 | — |
| Cascade *(Windsurf, v6-era)* | 36 / 113 | 49 / 113 |
| Claude Opus 4.8 *(v6-era)* | 23 / 113 | 24 / 113 |

The point that held then still holds: Basilisk runs **black-box** — no source on the machine — so its wins come from actually breaking the target, not from reading the answer key in the source. And you don't have to take the table on faith; the whole reason to score off a live board is that you can stand up the same container and check any row yourself.

Score it yourself:

```bash
docker run -d -p 3000:3000 -e NODE_ENV=unsafe --name juiceshop bkimminich/juice-shop
```

Then turn Basilisk loose on the board and call `juiceshop_report`, which reads the live scoreboard (`/api/Challenges`) and reports solved / available by difficulty.

### The methodology check: OWASP vuln-class coverage — 14 / 14 (F1 0.95)

A separate, easier run confirms the workflow end to end: Basilisk found and confirmed all 14 OWASP vuln *classes* on Juice Shop (SQLi, DOM / stored / reflected XSS, broken access control, sensitive data exposure, misconfig, directory listing, mass assignment, vulnerable components, input validation, SSRF, XXE, JWT / deserialization). That proves the orchestration and scoring are sound end to end; the black-box scoreboard number above is the headline measure of real exploitation.

**On comparing tools:** reproduce the run above, or point *your* tool of choice at the same Juice Shop and compare (`benchmark_compare` for coverage, or the live scoreboard for the hard number). An honest number you can regenerate beats a marketing table every time — including the one above, so go check it.

<br>

<div align="center">━━━━━━━━━━━━━━━━ ◈ ━━━━━━━━━━━━━━━━</div>

## ⟁ Security — the surface an attacker can reach, cut to the bone

An agent that reads the outside world *and* runs shell commands is a prompt-injection target. Most tools bolt on a filter and hope it holds. Basilisk takes the doors off the building instead.

- **The injection surface was removed, then gated.** The tools that fetched *attacker-chosen* URLs are gone. What's left, `web_read`, reads only from a fixed allow-list, split into two tiers **in code**: **trusted** sources an attacker can't plant content in (NVD, MITRE, CISA, vendor advisories, reputable news) fetch automatically; **community** sources that are user-authored (GitHub, GitLab, Stack Overflow, Wikipedia, PyPI, npm, exploit-db) are held **outside the autonomous loop** — Basilisk can't read one on its own. It raises a **one-tap approval request** in the notification bell; you Allow it (unlocking that source for the session) or ignore it, and either way the run keeps going. This is enforced in the dispatch path, not asked of the model — a compromised model still can't reach a user-authored source without your click. Everything fetched is shielded, arbitrary URLs and off-list redirects are refused, and link-local / cloud-metadata addresses are blocked.
- **The irreversible class can never run — enforced twice.** A structural detector hard-blocks disk/filesystem wipes, recursive root/`$HOME` deletes, fork bombs and raw block-device writes — seeing through quoting, `$IFS`, `bash -c` and other tricks a regex misses. It's refused at the UI gate *and* again inside the command-execution primitive itself, so no path — interactive, autonomous, batch, or any future caller — can route one around it. There is no "Run anyway" and no setting that disables it. (Verified against a battery of real bypass forms; zero false positives on legitimate work like `rm -rf ~/loot` or `find . -delete`.)
- **Untrusted input is quarantined.** Anything from outside — a target's response, an MCP result, an analyzed image — is run through a deterministic content firewall and wrapped as *data, never instructions.*
- **Your sudo password never touches the model**, self-written code runs only in a **bubblewrap jail** after passing its own test, and Basilisk's own safety code can't be overwritten by a shell command.

All of it is pinned in the test suite. It writes and runs real exploits against authorized targets — that's the job — but it will not churn out standalone weaponized malware (reverse shells, implants, ransomware, backdoors), and the destructive class can never run through it at all.

<br>

<div align="center">━━━━━━━━━━━━━━━━ ◈ ━━━━━━━━━━━━━━━━</div>

## ⛧ Feed it — bring your own model

Basilisk is multi-provider — you only need a key for the one you want. Set it in **Settings → Backends**.

| Provider | Get a key | Notes |
| --- | --- | --- |
| **SiliconFlow** | <https://cloud.siliconflow.com/account/ak> | **Default.** Big open models (DeepSeek, Qwen, Kimi) + SenseVoice STT |
| **Groq** | <https://console.groq.com/keys> | Blistering speed, generous free tier, Whisper STT. Keys look like `gsk_...` |

Keys live only in `~/.config/basilisk/settings.json`, locked to your user — they never go anywhere but the provider's own API.

<br>

<div align="center">━━━━━━━━━━━━━━━━ ◈ ━━━━━━━━━━━━━━━━</div>

<div align="center">

## License

**MIT.** Take it. Fork it. Loose it on the world.

## Credits

Hatched by **The Priest** ⟁

*A serpent that lives on your machine, answers to no one but you, and never forgets where the bodies are buried.*

<br>

`𝕿𝖍𝖊 𝖌𝖆𝖟𝖊 𝖉𝖔𝖊𝖘 𝖓𝖔𝖙 𝖇𝖑𝖎𝖓𝖐.`

</div>
