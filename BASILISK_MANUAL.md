# ⟁ BASILISK — Complete User Manual

*The full reference for Basilisk, the AI security operator that lives on your Linux machine.*

**Version 5.0.0** · GTK4 + libadwaita · X11 & Wayland · desktop and NetHunter mobile

---

## How to read this manual

You don't call Basilisk's tools directly. You **talk to Basilisk in plain language**, and it decides which tools to use, runs them, reads the results, and continues. Throughout this manual each capability lists the underlying **tool name** in `code font` so you know exactly what's happening under the hood — but in practice you'd just *ask*. "Scan my network," not `scan_net`.

The manual is organised as:

1. **Core concepts** — the handful of ideas that make everything else make sense. Read this first.
2. **Installation & setup.**
3. **The capabilities**, grouped and explained one at a time — sensing, offensive tooling, the exploit builders, engagement management, code scanning, benchmarking, research, desktop control, files, memory, and more.
4. **The safety model**, in full.
5. **Settings, architecture, troubleshooting, and a quick reference.**

Basilisk ships **119 tool entries** spanning nine capability groups. This manual documents all of them.

---

# Part 1 — Core concepts

Everything Basilisk does sits on four ideas. Understand these and the rest is detail.

## 1.1 Sensing vs. acting

Basilisk's tools fall into two buckets:

- **Sensing** (read-only): looking at your machine, reading a file, searching the web, scoring a scoreboard, building a plan or a payload. These have no side effects, so they **run freely** — Basilisk batches them and moves fast.
- **Acting**: running a shell command, changing the filesystem, driving the desktop, firing a built exploit at a target. These *do* something, so they go through a gate (below).

Almost everything in the offensive toolkit is a **planner or builder** — it produces a command or a payload as text. The moment something is actually *executed against a target*, that's an act, and it runs through the gate on scope **you** set.

## 1.2 The two speeds

- **Decisive (agent) mode** — the default. Acting tools execute immediately, Basilisk reads the result and continues the chain on its own. This is what makes it an operator's partner rather than a suggestion box.
- **Confirm every command** — flip this on and every acting tool becomes an approve-first **card**: you see exactly what it wants to do and click Apply (or decline). Sensing still runs freely.

You choose the speed per your comfort. The one exception is below and it never bends.

## 1.3 Cards

When a tool wants to *do* something you should see first, Basilisk shows a **card**: the exact command or a real diff, with Apply / decline. Shell commands, file writes, self-edits, and self-written tools all surface as cards (always under Confirm-every-command; always for the irreversible class regardless of mode).

## 1.4 The hard floor (the one rule that never bends)

Regardless of mode, regardless of what you or a document or an MCP server asks, a **catastrophic-command floor** sits in code beneath everything. Disk wipes, recursive deletes of `/` or your home, fork bombs, overwriting a whole disk device — these are **force-confirmed or refused before they ever leave the process**, even in fully decisive mode, even if the model was told to do it. It is enforced in code, not merely requested of the model. This is the guarantee that lets you run Basilisk decisively at all.

---

# Part 2 — Installation & setup

## 2.1 The one-liner (install *and* update)

The single documented install method is a `curl | bash` one-liner. The **same command updates** an existing install — it fetches the latest sources, backs up your chat DB and settings first, and re-runs the installer. HTTPS only; no SSH remotes anywhere in the toolchain.

## 2.2 Manual install

If you prefer to inspect first: clone/download the tree, install the GTK4 + libadwaita runtime and the Python deps, and run the installer script. Everything is plain files — no `.git`, no build artifacts in the delivered tree.

## 2.3 Install flags

The installer supports flags to skip optional subsystems (voice, etc.), do a dry run, or force a clean reinstall. Run it with `--help` to see the current set.

## 2.4 Environment overrides

Paths and a few behaviours can be overridden by environment variables for non-standard setups (custom data dir, alternate config location). The data directory defaults to `~/.local/share/kali` and the app-id is `org.thepriest.kali` (both lowercase `kali` internally — that's plumbing, not the brand).

## 2.5 Choosing a provider and getting a key

Basilisk is **cloud-model-driven** — there is no bundled local model. It ships with two backends:

- **SiliconFlow** — the **default primary**, running **DeepSeek-V4-Flash** (fast) and **DeepSeek-V4-Pro** (the heavier reasoning sibling). Get a key from SiliconFlow, paste it in **Settings → Backends**.
- **Groq** — the **fallback**. Never swapped in over SiliconFlow unless you enable auto-fallback or pick it explicitly.

The underlying OpenAI-compatible backend can also drive other OpenAI-style endpoints if you configure them. Whichever provider is active, its key is stored locally and sent only to that provider.

## 2.6 First launch

On first launch Basilisk opens a fresh chat. Set your provider key, optionally set a persona addendum, and you're ready — just start talking.

---

# Part 3 — The chat interface

## 3.1 The persona

Basilisk has a sharp, loyal, no-filler personality. It's built to be a direct operator's partner, not a cheerful assistant. Tune it per-machine in **Settings → Persona → Custom addendum** (these tweaks survive upgrades; direct edits to the persona file get overwritten on update).

## 3.2 The status banner

While Basilisk works, a live banner tells you *what it's doing* in plain terms — "running nmap…", "forging a JWT…", "reading the scoreboard…", "sweeping the app…" — so a long operation isn't a silent spinner. Every tool has its own status label.

## 3.3 The Thoughts panel

When the model exposes its chain-of-thought, Basilisk tucks it into a collapsed **💭 Thoughts** expander — kept **out of the reply, out of text-to-speech, and out of replayed history**. There if you want the reasoning, invisible if you don't.

## 3.4 Chat history

Conversations live in a local SQLite database (`~/.local/share/kali/chats.db`). By default Basilisk is **ephemeral**: fresh chat each launch, empty placeholders discarded, chats idle past the retention window binned — all tunable. Your DB is backed up before every update.

---

# Part 4 — Offensive security (the bread and butter)

This is Basilisk's core. The toolkit divides into three honest tiers:

- **Read-only intelligence** — inventory, planning, parsing, enrichment, methodology, reporting. These change nothing and run freely.
- **Invocation builders** — construct the correct command or payload for a technique (sqlmap, JWT forgery, NoSQL injection, XXE, and more). They **build** the attack; they don't fire it.
- **The gate** — a built command/payload is *executed against a target* only through the approve-before-run gate, and only against scope **you** set.

The important, accurate line: **Basilisk builds real exploits for authorised, in-scope targets, and you fire them through the gate.** It does not autonomously attack, and it does not write self-propagating malware, reverse shells, implants, or persistence — those are deliberate non-goals, held in code and persona.

## 4.1 `audit` — local security posture scan

A read-only sweep of *your own* machine's hygiene: firewall status, SSH hardening, listening ports, world-writable files, failed logins, pending updates — each scored by severity. Nothing changes. "Audit my system's security."

## 4.2 `scan_net` — local network discovery

Discovers hosts on your own network segment. The actual scan runs behind the gate.

## 4.3 `tooling_check` — offensive-tool inventory

Inventories **59 offensive-security tools** across recon, probing, port-scanning, fuzzing, vuln-scanning, secrets, credentials, and Active Directory. For anything missing it gives the **exact install line** (apt / go / pipx), knows **aliases** (`nxc` → `netexec`), and nudges you about **freshness** (nuclei templates, SecLists/rockyou). Ask before an engagement so you know what you're working with.

## 4.4 `pentest_plan` — ordered recon plan

A **methodical, ordered** recon plan, passive/enumeration steps first. Profiles — `web · network · ad · api · full · quick` — and an **intensity knob** (`stealth / normal / aggressive`) that tunes nmap timing, nuclei rate-limits, and ffuf threads. Every step is a *proposed* command behind the gate. "Plan a web pentest of example.com, stealthy."

## 4.5 `webapp_recon` — high-signal web recon sweep *(new in 5.x)*

A **read-only** sweep of a curated, high-signal path catalog against a web target: exposed file servers (`/ftp`), key directories (`/encryptionkeys/jwt.pub`), admin config endpoints, logs, backups, dotfiles (`.git/config`, `.env`), and the SPA bundle (`main.js`, `vendor.js`) that leaks library versions and hidden routes. It reports which paths respond and a short peek at each.

Run it **early** — a large class of findings (leaked API keys, exposed access logs, forgotten backups, vulnerable libraries) fail on *missed recon*, not missed exploitation. Under the hood the whole catalog is probed **concurrently** through a thread pool, so a full sweep is roughly one path's latency rather than seconds-per-path. Sensing only.

## 4.6 `parse_output` — turn scanner noise into structured data

Paste raw scanner stdout; Basilisk returns clean structured data — hosts, ports, services, versions, endpoints, findings — for **20+ tools**: nmap (incl. NSE hits), httpx, nuclei, naabu, masscan, subfinder, ffuf, feroxbuster, gobuster, katana, whatweb, wpscan, sslscan/testssl, smbmap, netexec, nikto, gitleaks, dalfox, arjun, and more. It **strips ANSI colour codes**, so colourised pastes don't silently drop data.

Its standout trick: with `enrich_cves`, it **auto-chains into CVE intelligence** — every confirmed service+version is looked up and a severity-ranked CVE block attached. One call turns a scan paste into "here are the services *and* the exploitable, known-in-the-wild CVEs."

## 4.7 `cve_lookup` — prioritised CVE intelligence

Pulls CVEs from the **NVD**, enriches each with **CISA KEV** (exploited in the wild?) and **EPSS** (exploitation likelihood), and **re-ranks KEV → EPSS → CVSS** so the genuinely dangerous ones surface first — not just the highest score. "Any known CVEs for OpenSSH 8.2?"

## 4.8 `nuclei_template` — generate or validate Nuclei templates

Nuclei YAML is easy to get subtly wrong, and a malformed template only fails cryptically at run time. **Build mode:** give a spec (name, severity, protocol, path, matchers) and get a **structurally-valid** template. **Validate mode:** hand it any Nuclei YAML and it reports **exactly what's wrong** before you run `nuclei -t`. You still run the scan; this guarantees the template is correct first.

## 4.9 The invocation builders — real exploits, you pull the trigger

Each builder constructs the correct attack for a target you've **scope-set**, and returns it for you to fire through the gate. They cover the vuln classes that plain command-improvisation can't reliably hit. All are pure builders (they send nothing) **except** `captcha_solve`, which does one read-only GET of the target's own CAPTCHA.

### `sqlmap_plan` — SQL injection

Builds the correct **sqlmap** command (`detect | enumerate | dump`) and **enforces scope** — refuses if the target isn't authorised. It proposes the command; you approve it through the gate. It walks the ladder deliberately (detect → enumerate `--dbs`/`--tables`/`--columns` → dump the minimum to prove impact) and **stops short of SQLi-to-RCE** (`--os-shell`/`--os-pwn`) — you drive that yourself if the engagement calls for it.

### `jwt_forge` — JWT forgery

Forges a JSON Web Token you already hold. Two modes:

- **`none`** — sets `alg: none` with an empty signature (a server that trusts the header's algorithm accepts an unsigned token).
- **`hs256`** — the classic **RS256→HS256 key confusion**: re-signs the token with HMAC-SHA256 using the server's RSA **public key bytes** as the HMAC secret. A verifier that honours the header's alg validates it. Fetch the public key first (on a Juice-Shop-class target it's at `/encryptionkeys/jwt.pub`).

`email`/`role` are shortcuts for common payload overrides. Returns the forged token; you send it. (Pure crypto — Python `hmac`/`hashlib`, no external libs.)

### `nosql_injection` — MongoDB operator injection

Builds a MongoDB-operator injection body in four modes: **`auth_bypass`** (`$ne` to defeat a filter), **`manipulation`** (an update-pipeline array where a string is expected, to write a field you shouldn't), **`dos`** (a `$where` busy-loop), and **`exfiltration`** (a `$regex` boolean oracle for blind character-by-character extraction). Returns the JSON body plus an endpoint hint; you fire it.

### `xxe_payload` — XML external entity

Builds an XML+DTD body: **`file_read`** (an external `SYSTEM` entity that reads a local file, or pivots to SSRF over `http://`) or **`dos`** (a capped billion-laughs entity-expansion bomb). Returns the XML and the upload-sink hint.

### `captcha_solve` — arithmetic CAPTCHA auto-read

Reads a target's arithmetic CAPTCHA endpoint and returns the answer plus the CAPTCHA id to submit — the intended anti-automation bypass on training targets that serve the CAPTCHA in plaintext. The expression is evaluated with a **non-`eval` shunting-yard parser**, so target text is never executed.

### `coupon_forge` — discount-coupon forging

Forges a discount coupon by **Z85-encoding** the campaign string (a correct ZeroMQ Z85 codec, verified against the spec test vector). The campaign prefix is target-version-specific — you read it from the target's `main.js` and pass it in; **Basilisk won't invent a prefix** and state it as fact.

### `reset_password` — security-question reset flow

Plans a security-question password reset. It is **bound to a fixed set of published demo accounts** (the reset-password CTF challenges) and **refuses an arbitrary email** rather than fabricating a security answer — a benchmark aid, not a general account-takeover tool.

## 4.10 `reflect_findings` — self-check before you report

A self-reflection pass that critiques findings for false-positive risk *before* they reach a report — flagging findings with **no evidence**, **over-rated** severity, **hedging language**, **no affected host**, or **duplicates**. Pure heuristics, no extra model call. Run it before `report_findings` on anything non-trivial.

## 4.11 `methodology` — phased testing checklists

Phased checklists grounded in **PTES / OWASP WSTG / the AD kill-chain**, for web, network, ad, api, mobile, wifi, recon, priv-esc, cloud. Knowledge only. Use it to make sure a test is systematic and nothing gets skipped.

## 4.12 `wordlist_find` — find installed wordlists

Locates the wordlists actually on *your* box (SecLists included) and gives the **canonical pick** per task (directory, subdomain, password, api, param, username, lfi…) plus alternatives, with an install hint if nothing matches. Read-only.

## 4.13 `cheatsheet` — correct command syntax

Correct flags and invocation patterns for the tools you reach for — nmap, ffuf, nuclei, httpx, netexec, hydra, hashcat, john, sqlmap, smbmap, kerbrute, ssh-tunnels, curl, and more. Documentation only.

## 4.14 `report_findings` & `attack_writeup`

`report_findings` aggregates structured findings into a polished markdown **engagement report** — severity rollup, sorted table, per-finding detail (title, severity, host, description, evidence, remediation). `attack_writeup` produces the **"how access was obtained"** narrative for a specific finding — the attack chain in prose. Both format text and run nothing.

---

# Part 5 — Engagement management & scope

Real work is scoped work. These tools hold the boundary and the picture of an engagement, and the **scope gate** is what the invocation builders check before they'll build anything active.

## 5.1 `scope_set` / `scope_check` / `scope_show`

- **`scope_set`** — record the authorised target list at the **start** of a job (`mode: replace | add`). Do this first — "scope is 10.0.0.0/24 and app.example.com."
- **`scope_check`** — is a given target authorised? It **fails closed**: anything not clearly in scope is out. The builders call this before constructing an active command.
- **`scope_show`** — show the recorded scope.

## 5.2 `asset_record` / `engagement_graph` / `graph_ingest`

- **`asset_record`** — add or update a host by handle, with what you've learned about it.
- **`engagement_graph`** — "what do I know so far" — the assembled picture of hosts, services, and findings.
- **`graph_ingest`** — fold structured scan data straight into the engagement graph.

## 5.3 `loot_record` / `loot_list` / `loot_reuse`

- **`loot_record`** — record a captured credential, hash, or token.
- **`loot_list`** — list captured loot, **redacted**.
- **`loot_reuse`** — given a captured credential, suggest **where else it might be tried** (lateral movement guidance) — scoped, of course.

---

# Part 6 — Code security scanning

For auditing source rather than a live target.

- **`code_tooling_check`** — which code scanners (SAST, secrets, dependency, IaC) are installed, with install lines for what's missing.
- **`code_scan_plan`** — an ordered, **proposed** scan plan for a codebase.
- **`parse_scan`** — normalise scanner output (semgrep, bandit, gitleaks, trivy, and friends) into structured findings, deduped.
- **`triage_findings`** — dedup **across** scanners and rank what actually matters.
- **`remediation_hint`** — a starting fix for a given finding class.

---

# Part 7 — Benchmarking & CTF (the closed loop) *(new in 5.x)*

Basilisk can benchmark itself against training targets and CTF boards, and — new in this line — it does so in a **closed loop**: attack, confirm what landed, decide what's next, repeat. This is the single biggest capability jump in 5.0.

## 7.1 The OWASP Juice Shop loop

Juice Shop is the industry-standard deliberately-vulnerable web app. Run it (`docker run -d -p 3000:3000 -e NODE_ENV=unsafe bkimminich/juice-shop`), scope-set it, and tell Basilisk to work the board.

- **`juiceshop_score`** — read the **live** scoreboard (`/api/Challenges`) and score yourself: solved/available by difficulty.
- **`juiceshop_next`** — the loop's planner: read the live board and return the still-**unsolved** challenges **easiest-first**, each **mapped to the exact tool that solves its class** (NoSQL → `nosql_injection`, JWT → `jwt_forge`, CAPTCHA → `captcha_solve`, and so on). Call it between attempts. A `max_difficulty` cap lets you clear a tier before climbing.
- **`juiceshop_diff`** — the loop's confirmation: diff the live board against what was solved before your last attempt, so you **know** an exploit landed instead of guessing.
- **`juiceshop_report`** — render the scorecard.

The workflow: `juiceshop_score` (baseline) → `juiceshop_next` (what's red + how) → take the easiest target, build its exploit with the matching builder, fire it through the gate → `juiceshop_diff` (did it land?) → next. Clear a tier, then climb. This feedback loop — not one-shot firing — is what moves the score off the easy tiers. It stays **planner-plus-feedback**: each actual exploit still goes builder → scope check → gate → run, so you're always on the trigger.

## 7.2 Generic benchmarks & XBOW

- **`benchmark_targets` / `benchmark_score` / `benchmark_report` / `benchmark_compare`** — the generic harness for scoring runs and comparing them across attempts.
- **`xbow_score` / `xbow_report`** — aggregate and render XBOW flag-capture results.
- **`submit_flag`** — record a captured CTF flag so the runner can check it against the expected answer.

---

# Part 8 — Evidence ledger

What separates a chat log from a **defensible engagement deliverable**. Every command Basilisk runs is **automatically recorded** — you log nothing by hand.

## 8.1 How it works

Each executed command appends one line to a tamper-evident JSONL ledger: timestamp, engagement, step number, the command, the reason, working directory, user, exit code, duration, and the **SHA-256 hash of stdout and stderr**. Full output is saved to a side artifact whose hash is recorded, so the ledger can later **prove the captured output wasn't altered after the fact**. Fail-safe: a ledger error can never break a command. MCP calls are logged here too.

## 8.2 `evidence_engagement` / `evidence_report` / `evidence_verify`

- **`evidence_engagement`** — set/switch the **engagement** future commands are filed under. Do it at the start of a job.
- **`evidence_report`** — a summary (how many commands, how many succeeded), an integrity check, and a readable markdown ledger of everything run so far. The artifact you'd hand a client.
- **`evidence_verify`** — re-hash every captured artifact and confirm it still matches the ledger. An output edited after capture no longer matches and is flagged.

---

# Part 9 — External tools via MCP

Basilisk can connect to external **Model Context Protocol** servers — the growing ecosystem that wraps tools like nmap, sqlmap, ffuf, nuclei, and ZAP. Wiring one in gives Basilisk all of that server's tools without a per-tool wrapper.

## 9.1 Key facts

- **Off by default.** Inert until you both enable it (`mcp_enabled`) **and** configure a server (`mcp_servers`).
- **Tools are namespaced** — a discovered tool appears as `mcp__<server>__<tool>`, never confusable with a built-in. Ask Basilisk to list what's wired up (`mcp_tools`).
- **You don't write a server** — you point at an existing one: `{name, command, args, env, cwd}`. A Docker-packaged server is just `{"name":"pentest","command":"docker","args":["run","-i","the-image"]}`.

## 9.2 Why it's safe

MCP is a remote-code-execution surface, so every server is treated as **untrusted**: **every call's arguments are screened by the same catastrophic-command floor** that guards `run` (refused before leaving the process if they resolve to something destructive), and **every call is logged to the evidence ledger**.

---

# Part 10 — OSINT & research

## 10.1 `osint_username` — handle check across public sites

A Sherlock-style sweep across ~43 public profile sites. **Caveat Basilisk itself observes:** a hit means a *public page exists* at that handle — **not** that it's the same person. Confirm identity separately.

## 10.2 `osint_lookup` / `social_read` — public readers

Platform-aware readers for public pages and public APIs (Reddit via public `.json`, and more). **Public only** — no login, no gated scraping.

## 10.3 `web_search` — ranked web search

Searches the web (DuckDuckGo), returning ranked results plus direct answers. The everyday "look this up."

## 10.4 `web_read` — fetch a page as clean text

Fetches any public page and returns clean, readable text — **headless**, no browser. Have Basilisk actually read an advisory or doc rather than guess.

## 10.5 `web_verify` — the anti-propaganda engine

Basilisk's most distinctive research tool. Instead of trusting one source it **gathers several independent sources**, scores each for credibility (primary / reputable / community / state-media / satire), checks whether they **actually corroborate**, and returns a **confidence label** — separating confirmed / inferred / unknown and **flagging state media and satire** instead of laundering them into fact. Use it whenever being wrong matters. "Verify whether X actually happened."

## 10.6 `github` — read GitHub

Searches repos and code, lists a user's repos, reads file trees, source, READMEs, releases, and issues. Public by default; private repos with a token you provide (`github_token`).

## 10.7 `browser` — full browser automation

Full **Playwright + Chromium** automation for sites that need a real browser — login-gated pages or JS-only apps `web_read` can't handle. Actions include `goto`, `read`, `click`, `fill`, `submit`, and more. It waits (bounded) for single-page apps to actually render and their XHR to settle before reading, so it doesn't act on a half-loaded skeleton. Heavier than `web_read`, used when a page genuinely requires it.

---

# Part 11 — Vision & media

Basilisk can see and hear as well as read.

- **`analyze_image`** — Basilisk **sees** an image and describes/answers questions about it, via a vision-capable model (`vision_model`, default a Qwen2.5-VL on SiliconFlow).
- **`image_search`** — return relevant images from the web for a query.
- **`capture_photo`** — grab a photo from the camera and (optionally) analyse it.
- **`detect_faces`** — count/locate faces in an image.
- **`chat_render_images`** — when on, images are fetched and shown **inline** in the chat.

---

# Part 12 — System sensing (read-only, runs freely)

All of these just *look* — no permission needed, nothing changes.

- **`quick_facts`** — fast cached snapshot: hostname, IP, uptime, load, free space.
- **`system_info`** — fuller system details (OS, kernel, hardware).
- **`disk_usage`** — what's using storage.
- **`processes`** — running processes.
- **`network_status`** — interfaces, connections, routing.
- **`service_status`** — state of system services.
- **`journal_tail`** — tail of the systemd journal.
- **`recent_downloads`** — what landed in Downloads recently.
- **`check_updates`** — pending package updates.
- **`path_info`** — stat a path without reading it.
- **`desktop_info`** — which desktop-control backends are available (display server, helper tools).

"How's my system doing?" batches several of these in one go.

---

# Part 13 — Desktop control (confirm-gated)

Basilisk can drive your **actual** desktop. It auto-detects **X11 vs Wayland** and picks the backend (xdotool/wmctrl/scrot on X11; wtype/wlrctl/grim on Wayland; Spectacle/kdialog on KDE Plasma). These are *acting* tools — direct in decisive mode, cards under Confirm-every-command.

- **`launch_app`** — open an application. **`list_apps`** — list installed apps. **`open_url`** — open a URL in your browser.
- **`list_windows`** / **`focus_window`** / **`close_window`** — enumerate, raise, gracefully close windows.
- **`type_text`** — type into the focused window. **`press_key`** — send a keystroke/shortcut (e.g. `Return`).
- **`screenshot`** — capture the screen. **`read_screen`** — **OCR** what's visible on-screen (useful when there's no API for it).
- **`media_control`** — play/pause/skip. **`notify`** — desktop popup that also logs to the in-app inbox.

"Open Firefox and go to my router's admin page" chains `launch_app` / `open_url`.

---

# Part 14 — Files & shell

Reading is free; anything that changes the filesystem is gated (and the irreversible class is always force-confirmed).

## 14.1 Reading (read-only)

- **`read_file`** — read a file. Detects binary vs text by NUL byte, so it won't mangle a truncated text file.
- **`list_dir`** — list a directory.
- **`find_file`** — find files, with **size and modification-time filters**.

## 14.2 Changing (gated)

- **`make_dir`** — create a directory. **`copy_path`** — copy. **`move_path`** — move/rename. **`delete_path`** — delete (recursive root/home forms are force-confirmed).

## 14.3 `run` — any shell command

The big one. Basilisk can run **any shell command**. In decisive mode it executes directly, reads output, and continues; under Confirm-every-command it's an approve-first card; the catastrophic class is always force-confirmed regardless. **Sudo is handled safely** — your password is collected in a dialog, validated, cached for the session, and **never stored, logged, or shown to the model**.

## 14.4 `write_file` — write any file (diff card)

Create or overwrite any file — document, report, script, config — via a **diff card** you Apply. You see the change as a real diff before a byte hits disk. Multi-line content is parsed robustly so a long file isn't corrupted in transit.

---

# Part 15 — Memory (optional, local)

Off by default. When on, Basilisk remembers across sessions — **locally, nothing leaves the box**.

- **`memory_remember`** — store a fact, with a kind and a salience.
- **`memory_recall`** — retrieve relevant memories. Recall is **relevance-scoped**: keyword match + recency + salience (optionally embeddings), injecting only the **top-k** per turn, never the whole store. It connects **security paraphrases** — "SQL injection" finds a memory stored as "SQLi", across a couple dozen synonym groups (XSS, RCE, LFI, SSRF, privesc, recon…).
- **`memory_forget`** — drop a memory by query or id.

"Remember that the client's scope is 10.0.0.0/24" — and later, "what was the scope again?"

---

# Part 16 — Self-written tools (skills, optional, sandboxed)

Off by default. When on, Basilisk can **write its own Python tools** — and can't hurt you doing it, because of the sandbox.

- **`skill_write`** — Basilisk drafts a Python tool. Before anything runs it's **`ast`-parsed and statically screened**, then executed in a **bubblewrap jail** (read-only system, no home access, network off), and it **must pass its own test**. Only then do you get a card to **Apply** it.
- **`skill_run`** — run a saved skill. **`skill_list`** — show the library.

A self-written tool runs in isolation and proves itself before it's ever trusted. "Write me a skill that parses this custom log format."

---

# Part 17 — Self-modification

Basilisk can **rewrite its own source and persona**, proposing the full new file as a **diff** you Apply. Safeguards:

- Python is **parse-checked** before writing — a syntax error can't replace a working file.
- The **original is backed up**; writes are **atomic**.
- A load-bearing **guardrail block is immutable by design** — Basilisk can edit everything else about itself, but the write path **refuses any edit that drops or alters that block** (enforced in code, not merely asked of the model).

Persona edits reload live on the next reply; code edits load on relaunch. (Direct edits to `kali_persona.py` get overwritten on the next `install.sh` run — use the Settings persona addendum for changes that should survive updates.)

---

# Part 18 — Voice

## 18.1 Speech-to-text (talk to it)

Hold-to-talk voice input, transcribed by a Whisper-class model. Provider is **auto-routed** (SiliconFlow primary, Groq fallback) or pinned. Optional auto-send after a transcription. Language can be hinted or auto-detected.

## 18.2 Text-to-speech (hear it back)

Basilisk can **read replies aloud** — Piper (neural) or espeak, auto-selected. Rate and inter-sentence pause are tunable. Thoughts are never spoken. All off by default.

---

# Part 19 — Quality-of-life features

- **Adaptive effort ladder** — matches model + token budget to the turn: fast Flash with a tight budget on plain chat; the heavier reasoning sibling with a bigger budget once several tool-steps deep in a live engagement. One switch (`adaptive_effort`) turns it off for flat, snappy behaviour — worth it for a fast benchmark grind.
- **Headroom compression** — bulky tool-result envelopes are compressed before they hit the model, so long runs don't blow the context window. On by default; keeps the most recent results full.
- **Lean chat** — on plainly conversational turns the full tool catalog is skipped, saving latency and tokens.
- **Stream reliability** — a stalled provider stream aborts on a short idle timeout and self-heals to the next model, instead of freezing the UI on "thinking…". (New in 5.x.)
- **Urgency fast-path** — when you're clearly in a hurry, Basilisk skips preamble.
- **Notification inbox** — a bell with a persistent store; `notify` posts here as well as to the desktop.
- **Ephemeral chats** — fresh chat per launch, auto-retention, empty-placeholder cleanup — all tunable.
- **Theme & scale** — the "hellfire" charcoal-and-blood-red theme; UI scale auto-detects (down to a ~540px mobile width for NetHunter) or can be pinned.

---

# Part 20 — The background worker (optional)

An optional headless `systemd --user` companion that can poll on a cadence for things worth surfacing — pending updates, new downloads, journal events — and drop them in the notification inbox. Off by default; interval and which checks it runs are configurable.

---

# Part 21 — The safety model (in full)

Basilisk is powerful on purpose, so the safety model is layered and mostly enforced in **code**, not just asked of the model:

1. **The catastrophic-command floor.** Disk wipes, recursive `/` or home deletes, fork bombs, whole-disk overwrites — force-confirmed or refused before leaving the process, in every mode, no matter who asked. Applies to `run`, to filesystem tools, and to MCP call arguments alike.
2. **Sensing vs. acting.** Read-only tools run freely; acting tools go through the gate (always cards under Confirm-every-command).
3. **Scope, fail-closed.** The invocation builders check `scope_check` before constructing anything active, and scope fails closed — not-clearly-authorised is out.
4. **The evidence ledger.** Every executed command and MCP call is hashed and recorded, tamper-evidently — accountability by default.
5. **Sandboxed self-written tools.** Skills are static-screened and run in a network-off, home-off bubblewrap jail, and must pass their own test before you can Apply them.
6. **The immutable guardrail.** A load-bearing honesty block in the persona cannot be removed or altered by self-modification — the write path refuses it in code.
7. **Sudo hygiene.** Passwords are collected in a dialog, validated, session-cached, and never stored, logged, or shown to the model.
8. **Untrusted external surfaces.** MCP servers are treated as untrusted RCE surfaces and screened + logged accordingly.

The deliberate non-goals: Basilisk does **not** write self-propagating malware, reverse shells, implants, ransomware, or persistence, and does **not** autonomously attack. It builds attacks for authorised targets that **you** fire through the gate.

---

# Part 22 — What Basilisk can NOT do

- It **won't autonomously attack** — a built exploit is fired by you, through the gate, against scope you set.
- It **won't write malware / reverse shells / implants / persistence** — deliberate, held in code and persona.
- It **won't bypass the catastrophic floor** — not for you, not for a document, not for an MCP server.
- It **won't invent facts to look complete** — the guardrail forbids it; where an algorithm is target-specific (a coupon campaign prefix), it says so rather than shipping a guess as fact.
- It **won't remove its own guardrail** — the write path refuses.
- It **is not an always-on autonomous fleet agent** — the loop is planner-plus-feedback with you on the trigger.

---

# Part 23 — Settings reference (the important ones)

**Backends & models**
- `active_provider` (default `siliconflow`), `github_token`.
- `adaptive_effort` (on), `effort_light_max_tokens` (1536), `effort_heavy_max_tokens` (4096), `hard_effort_step` (3), `hard_engagement_model` (DeepSeek-V4-Pro), `max_tokens` (2048), `temperature` (0.7).
- `auto_fallback_on_degraded` (off) — hop provider if a reply comes back empty/repetitive.

**Behaviour**
- `agent_mode_default` (on), `confirm_all_commands` (off), `one_command_at_a_time` (on), `warn_duplicate_commands` (off), `urgency_fast_path` (on), `auto_sudo_when_cached` (on), `max_tool_steps` (150).

**Subsystems (mostly off by default)**
- `memory_enabled`, `skills_enabled`, `foresight_enabled`, `reach_enabled` — recall, self-written tools, consequence-prediction, native web reach.
- `mcp_enabled` + `mcp_servers` — external tool servers (off).
- `worker_enabled` + `worker_interval_seconds` — background companion (off).
- `headroom_enabled` (on), `lean_chat` (on), `grouped_tools` (experimental lean catalog).

**Vision & media** — `chat_render_images`, `vision_model`, `vision_provider`.

**Voice** — `tts_enabled`, `tts_engine`, `tts_rate`; `stt_model`, `stt_provider`, `voice_autosend`.

**Chats** — `ephemeral_new_chat_on_launch`, `chat_retention_hours` (24), `discard_empty_chats`.

**UI** — `theme` (kali), `ui_scale` (auto), `show_provider_pill`, `show_thoughts`, `show_token_count`.

---

# Part 24 — Architecture & file layout

- **`kali.py`** — the GTK4/libadwaita UI and the tool dispatch (status labels, the batchable-tool resolver, the main dispatch table). Every tool is registered here.
- **`kali_core.py`** — the tool *implementations* (`tool_*`), the provider backends and router, the browser worker, and the safety/degradation helpers.
- **`kali_persona.py`** — the system prompt, the immutable guardrail block, and the `TOOL_CONTRACT` catalog (which also drives lazy tool-group loading).
- **`kali_ext/`** — optional stdlib-only sidecar modules loaded through a seam: memory, skills, sandbox, MCP, foresight, native reach, headroom compression, the pentest/exploit builders, the Juice Shop harness, benchmarking, XBOW, engagement graph, evidence verification, and the background worker.
- **`kali_safety.py` / `kali_ledger.py` / `kali_voice.py`** — the safety floor, the evidence ledger, and the voice stack.
- **Data** — `~/.local/share/kali/` (chats.db, memory, skills, evidence ledger + artifacts, notification store). App-id `org.thepriest.kali`.

Design constraints held throughout: cloud-model-driven (SiliconFlow primary, Groq fallback, never swapped without instruction), stdlib-only sidecars, single-file tools, HTTPS-only remotes, one-liner `curl | bash` install, plain-zip deliverables.

---

# Part 25 — Troubleshooting & FAQ

**It's stuck on "thinking…" forever.** Fixed in 5.x — a stalled stream now aborts on a short idle timeout and self-heals to the next model. If you're on an older build, that's the 600s stream timeout; update.

**A reply came back empty or repetitive ("looked degraded").** That's the degradation guard catching junk output, usually context pressure on a long run. Enable `auto_fallback_on_degraded` to auto-hop to Groq for the retry, or work in smaller tiers so context stays lean.

**A builder refused my target.** Scope. `scope_set` the target first; `scope_check` fails closed by design.

**The whole extension layer seems dead** (no memory/skills/MCP). Usually a missing sidecar on a remote install; re-run the one-liner to refetch, and confirm the install completed cleanly.

**Benchmark is slow / over-thinking.** Set `adaptive_effort: False` to keep every turn on fast Flash for the easy tiers, and let the closed loop (`juiceshop_next` → build → `juiceshop_diff`) drive rather than one-shotting.

**Desktop control does nothing.** Check `desktop_info` for which backends are present; install the matching helper (xdotool/wmctrl on X11, wtype/wlrctl on Wayland) if missing.

---

# Part 26 — Quick reference

**Just ask, in plain language.** Basilisk picks the tools. Some starting points:

- "Audit my system." · "How's my box doing?" · "What's eating my disk?"
- "What offensive tools do I have?" · "Plan a stealthy web pentest of X."
- "Scope is 10.0.0.0/24 — record it." · "Sweep X for exposed files." · "Any KEV-listed CVEs for this version?"
- "Forge an alg:none JWT from this token as admin." · "Build a NoSQL auth-bypass body." · "Build an XXE file-read for /etc/passwd."
- "Work the Juice Shop board — score, then clear it tier by tier." · "What's still unsolved and how do I hit each one?"
- "Start an engagement called acme-q2." · "Show me the evidence report." · "Verify the ledger."
- "Verify whether X actually happened." · "Read this advisory." · "Search GitHub for Y."
- "Open Firefox to my router." · "Screenshot this." · "Read what's on screen."
- "Remember the client scope." · "Write a skill that parses this log format."

The rule of thumb: **sensing is free and instant; acting waits for your Apply (or runs decisively if you've said so); and the catastrophic floor is always there underneath.**

---

*⟁ Basilisk v5.0.0 — built by The Priest. Powerful on purpose, safe by construction.*
