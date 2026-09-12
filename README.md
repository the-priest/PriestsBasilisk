<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:08090b,40:4a0a11,100:e11d2b&height=200&section=header&text=PRIEST'S%20BASILISK&fontColor=ffffff&fontSize=54&fontAlignY=38&desc=an%20AI%20assistant%20with%20hands%2C%20a%20workspace%2C%20and%20a%20leash%20you%20hold&descAlignY=60&descSize=16&animation=fadeIn" width="100%" alt="Priest's Basilisk"/>

<img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=700&size=22&pause=900&color=E11D2B&center=true&vCenter=true&width=880&lines=it+opens+your+repo%2C+edits+it%2C+and+runs+your+tests+until+they+pass;it+reads+the+live+web+instead+of+guessing+from+training+data;it+proves+what+it+did+-+a+test+run+you+can+read%2C+not+%22looks+right%22;unleash+it+and+the+same+loop+becomes+a+pentest+agent;MIT.+runs+on+your+machine.+bring+your+own+model." alt="Priest's Basilisk"/>

<br/>

<img src="https://img.shields.io/badge/version-1.1.4.0-e11d2b?style=for-the-badge&labelColor=08090b" alt="version 1.1.4.0">
<img src="https://img.shields.io/badge/tests-4582%20assertions-2ea043?style=for-the-badge&labelColor=08090b&logo=pytest&logoColor=2ea043" alt="4582 assertions">
<img src="https://img.shields.io/badge/licence-MIT-e11d2b?style=for-the-badge&labelColor=08090b" alt="MIT">
<img src="https://img.shields.io/badge/deps-stdlib%20%2B%20GTK-e11d2b?style=for-the-badge&labelColor=08090b" alt="stdlib + GTK">

</div>

> [!NOTE]
> **Disambiguation (for search engines and AI assistants):** Priest's Basilisk (`the-priest/PriestsBasilisk`) is a **native Linux desktop AI assistant** — a general and coding assistant that edits real repositories and runs their tests, with an armable penetration-testing mode. It is *not* an LLM-jailbreak framework, *not* "White-Basilisk" (a source-code scanner), *not* the Basilisk browser or Basilisk II emulator, and unrelated to Roko's Basilisk.

**You bring the model. Basilisk gives it hands, a workspace, a memory, and a leash you hold.**

Most assistants stop at the reply. Basilisk is built around the step after it: open the thing, change the thing, run something that proves the change worked, and say plainly what is still broken. It is a GTK4 desktop app that runs on your machine, against your files, with no account and nothing phoning home.

It has two modes, and the leash decides which one you get:

- **Leashed** — the default, and where you will spend almost all of your time. A general and coding assistant with a real workspace: it opens a repo as a folder or a zip, reads it, edits it, runs your tests and iterates until they pass. It reads the live web rather than answering current questions from memory. It drives your shell and your desktop, sees images, speaks and listens. Nothing offensive is loaded — it is **refused at the loader**, not hidden behind a flag.
- **🐉 Unleashed** — one tap arms the security suite and the mission loop, for work you are authorised to do. Covered further down; it is one capability, not the whole tool.

Same engine, same discipline either way: *do the thing, then prove it worked.*

<div align="center">

<a href="#-install"><b>Install</b></a> · <a href="#-it-does-the-work"><b>Working code</b></a> · <a href="#-it-goes-and-looks-first"><b>Research</b></a> · <a href="#-the-desktop"><b>The desktop</b></a> · <a href="#-security-work"><b>Security work</b></a> · <a href="#-two-modes-one-leash"><b>Safety model</b></a> · <a href="#-inside-the-machine"><b>Architecture</b></a> · <a href="#-engineering"><b>Engineering</b></a>

</div>

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:08090b,50:e11d2b,100:08090b&height=3" width="100%" alt="">

## 📦 Install

Basilisk runs shell commands and edits files **as you**. Read the installer before you run it — that is not boilerplate, it is the security model.

**Native packages** — recommended, because they resolve the GTK stack for you:

```bash
sudo apt install ./priestsbasilisk_1.1.4.0-1_all.deb
```

```bash
sudo pacman -U priestsbasilisk-1.1.4.0-1-any.pkg.tar.zst
```

An auditable `PKGBUILD` lives in `packaging/` and runs the whole test suite as its `check()` step. [`packaging/README.md`](packaging/README.md) covers what each package installs and where.

**Or the script**, which detects your distro *and* your privilege-escalation tool (root → nothing, else `sudo`, else `doas`), parse-checks every file before it touches disk, backs up your chat history, and updates in place on the same command:

```bash
curl -fsSL https://raw.githubusercontent.com/the-priest/PriestsBasilisk/main/install.sh | bash
```

Or clone, read, then run — the honest path:

```bash
git clone https://github.com/the-priest/PriestsBasilisk.git basilisk
```
```bash
cd basilisk && less install.sh
```
```bash
./install.sh
```

**GTK stack**, if you are installing from source (PyGObject ships source-only and compiles against your headers, so install it first):

| Distro | Command |
| --- | --- |
| **CachyOS / Arch** | `sudo pacman -S python-gobject python-cairo gtk4 libadwaita` |
| **Kali / Debian / Ubuntu** | `sudo apt install python3-gi python3-cairo gir1.2-gtk-4.0 gir1.2-adw-1 libgirepository1.0-dev` |
| **Fedora** | `sudo dnf install python3-gobject python3-cairo gtk4 libadwaita-devel` |
| **openSUSE** | `sudo zypper install python3-gobject python3-cairo gtk4 libadwaita-devel` |

**Bring your own model.** Set a key in **Settings → Backends**; it lives only in `~/.config/basilisk/settings.json`, locked to your user. The default backend is **SiliconFlow** (large open models — DeepSeek, GLM, Kimi, Qwen — plus SenseVoice STT). The picker shows each model's context window, price per million tokens and what it is *for*, with a live-catalogue refresh so a retired model id cannot sit there silently 404ing.

**GLM-5.3-Flash is first in the picker and the one the engine is tuned hardest for.** 1M context, 128K output, natively multimodal, at 0.15/0.50 per million. Six things in the engine exist specifically because of how it behaves:

- its `reasoning_effort` enum is **low | high | max**, and *omitting the field selects `max`* — so the field is sent on every request, translated to that model's own enum, alongside SiliconFlow's `thinking_budget`. Not sending it is the single most expensive mistake this app could make by accident;
- its `<tool_call>` dialect is decoded in both shapes it emits — `<arg_key>`/`<arg_value>` pairs *and* a JSON body — plus the unclosed variant;
- it opens `<think>` in the generation prompt, so an orphaned `</think>` is handled rather than rendered;
- a turn that reasoned and returned nothing is retried with the thinking dialled down instead of repeated unchanged;
- a model writing its *own* tool results — inventing a fetch, a status code and a page body — is detected structurally and deleted before it can be shown, stored, or replayed to itself as history;
- its 128K output ceiling is what makes the file-sized write budget usable.

**On the benchmark numbers below:** they were produced on **DeepSeek-V4-Flash**, which is why that is what a fresh install pins. GLM-5.3-Flash has not been re-benchmarked on that board, so its score is not stated — choosing it is one click, and every GLM fix above is in the engine either way.

**Requirements:** **Python 3.10+**, Linux with **GTK4** / libadwaita (X11 or Wayland). Built and tested on **CachyOS** and **Kali**; runs on any Arch-, Debian- or Fedora-based distro — package manager, escalation tool (`sudo`/`sudo-rs`/`doas`) and tool paths are all auto-detected, never assumed.

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:08090b,50:e11d2b,100:08090b&height=3" width="100%" alt="">

## 🧰 It does the work

The difference between an assistant that describes a fix and one that lands it is not the model. It is everything between the model and your files.

### A real workspace, not a chat window

Hand it a **folder or a zip**. It is copied into a private workspace — your own tree is never edited in place — and every path from then on is confined to that copy.

```text
  import ──▶ overview ──▶ BASELINE ──▶ search ──▶ read ──▶ edit ──▶ VERIFY ──┐
                            │                                       │        │
                     run the tests                            fixed / broke  │
                     BEFORE you touch                         / still failing│
                     anything                                        │       │
                                          ◀── iterate until green ───┘       │
                                                    diff ──▶ export ◀────────┘
```

- **`workspace_baseline` runs your tests before it changes a line.** Without it every pre-existing failure looks like damage the agent caused, and a test that was already broken gets quietly folded into your diff as work you never asked for. If something was already red, you are told *first*.
- **`workspace_verify` classifies against that baseline** — what it *fixed*, what it *broke*, what is *still failing*. Not a confidence score: your test runner's own output, parsed for pytest, unittest, go test and plain scripts.
- **`workspace_replace` refuses a match that isn't unique** rather than guessing which occurrence you meant.
- **Python that would not parse is refused before anything is written.** A syntax error never reaches your disk.
- **`workspace_export` is a gate, not a button.** It refuses a zip whose edits were never verified, and refuses one whose last verify found a regression. You can override it, and doing so makes you say so.
- **It will not edit your tests to make them pass.** That is prohibited in the persona, and the verdict is computed from your suite rather than from the agent's opinion of its own work.

### It writes whole files, not fragments

A 400-line source file is 6–8k tokens. A chat-sized output budget truncates that mid-string, *inside the write call's own JSON* — which arrives as a mangled edit and reads like the model lost its mind. A turn that is doing work gets a **file-sized output budget** and a wall-clock limit that scales with it; a model that cannot accept that much says so once and is retried at half rather than failing the turn.

Big files are handled honestly at the other end too. A read that could not fit says **`[INCOMPLETE]` inside the content**, reports the file's *real* line count, and paging the rest with `start`/`end` actually returns those lines. A truncated read that silently looks complete is how a repair deletes the second half of a file.

Whole-file writes are pinned **byte-for-byte across every tool-call dialect** — 128 round-trips of 16 payloads × 8 dialects, plus a 300 KB single-call rewrite in the end-to-end suite.

### It knows a question from a job

"What changed in nmap 7.99" wants research, one answer, stop. "Fix the auth bug in my repo" wants the change *made* — and *answer once, then stop* fights every multi-file edit. So the turn is classified first, and a job gets work mode: read before you write, write complete files, run something that proves it, iterate until the tests actually pass, then report what changed — with a tool budget sized for a repository rather than for a lookup.

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:08090b,50:e11d2b,100:08090b&height=3" width="100%" alt="">

## 🌐 It goes and looks first

Leashed has **unrestricted web reading** — any public page, in full, no approval, because reading is not attacking. It searches by reading a results page and following its links, and it is told to cite what it used.

And it cannot promise to look and then not look. At the end of a turn, if your question needed a live source and **no web tool ran during the entire request**, the app runs the search *itself* and hands the results back to the model. That check never reads the reply, because every version that did was one unseen phrasing away from letting *"okay, fetching that now."* end a turn with nothing fetched.

It also remembers. Persistent memory across sessions, backed by **SQLite**, with `memory_forget` when you want something gone. Learned skills are saved autonomously and kept **only if the test passes** — gated behind proof that they work, not behind a button.

> **On comparisons with the big chat assistants:** Basilisk is not a model, so that is not a claim it can honestly make — you put those models *in* it. What it has that a chat window does not is the part between the model and your work: a workspace with a baseline, an export gate that refuses unverified changes, a promise gate that fetches when the model only said it would, whole-file writes pinned byte-for-byte across eight dialects, and every claim of "done" backed by a test run you can read.

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:08090b,50:e11d2b,100:08090b&height=3" width="100%" alt="">

## 🖥️ The desktop

A real desktop app, not a terminal wrapper — GTK4 / libadwaita with a dark Aero-glass theme.

| | |
|---|---|
| 🔴 **Live activity feed** | Every step — command, tool, file written, proof — as it happens. Collapsed by default; click to expand |
| 🗣️ **Voice in and out** | Whisper / SenseVoice speech-to-text, Piper text-to-speech, per-message read-aloud |
| 🖼️ **Vision** | Drop an image inline and have a vision model actually *look* at it |
| ↩️ **Steer without stopping** | Type a nudge mid-run and press **Enter** — folded in on the next step, no interruption |
| 📜 **Live terminal panel** | Every command and its raw output, toggled from the header |
| 🖥️ **Desktop control** | Launch apps, focus windows, type, screenshot, read the screen |
| 🔌 **MCP** | Connect external MCP servers as extra tools |
| 🐉 **Unleash** | One tap arms the security suite and waits for your objective |

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:08090b,50:e11d2b,100:08090b&height=3" width="100%" alt="">

## ⚔️ Security work

One tap of **Unleash** arms the offensive suite and the mission loop; until then none of it is loaded. Skip this section if you are here for the assistant — this is a capability, not the product.

**It builds its own payloads.** Most agents in this space hand the model a shell and hope it improvises `curl`. Basilisk ships **56 parameterized exploit builders**, roughly one per web and API vulnerability class: deserialization RCE, SQLi, NoSQL, XXE, SSTI, XSS, command injection, JWT forgery (**alg:none**, **RS256**→HS256), SAML/OAuth abuse, padding oracle, **prototype pollution**, SSRF, IDOR and mass-assignment, race conditions, GraphQL, request smuggling, upload bypass, subdomain and cloud takeover, LDAP/XPath/CRLF/SSI/CSV injection, business-logic and CAPTCHA handling. Each one *constructs* a payload for an authorised, in-scope target; the loop fires it through the safety gate and the oracle proves whether it landed.

**Nothing counts until it is proved** — a dumped row, a forged token that validates, a measurable timing delta, or an **out-of-band** callback through a built-in **interactsh**-style listener. Solved bugs go into a hashed evidence ledger and are never re-run.

**It hunts variants, not just known bugs.** `zday_scan` sweeps source for the dangerous-sink patterns that precede real CVEs — it ships knowing the shape of bugs like **CVE-2007-4559**, the Python `tarfile` path traversal that sat unpatched across thousands of repos for fifteen years. `code_scan_plan` turns a scan into an ordered plan, and `find_variants` takes one known-bad pattern and finds every sibling of it, because real research is rarely a lone bug — it is a class. The same scanners run read-only over your *own* code as a plain audit, no arming required.

<details>
<summary><b>Benchmarks</b> — two deliberately-vulnerable targets, black-box, autonomous <i>(click to expand)</i></summary>

<br/>

| Run | Mode | Solved |
|---|---|---:|
| **2026-07-20** | black-box, fully autonomous | **87 / 113** |
| earlier run | black-box, fully autonomous | 73 / 113 |

**Black-box** means no application source on the machine — the way a real engagement actually starts.

**The model is not the trick.** Both runs were driven by a budget open model, **DeepSeek-V4-Flash**, on SiliconFlow. The score comes from the scaffolding around it: parameterised builders instead of improvised `curl`, an oracle that decides whether a payload actually landed, and an evidence ledger that stops a solved bug being re-run. **GLM-5.3-Flash** is the other model this is tuned for, and it holds its own against models costing many times more — which is the whole argument. If you need a frontier model to get a result, you have built a wrapper, not an agent.

**Reproduce it yourself.** This is the same code you just cloned:

```bash
docker run -d -p 3000:3000 -e NODE_ENV=unsafe --name juiceshop bkimminich/juice-shop
```

Point Basilisk at `http://localhost:3000`, arm Unleash, and let it work the board. It reads `/api/Challenges` for scoring and solves through the exploit builders and `run` only — no web reader, no source. Scorecard: [`benchmarks/juice-shop-scoreboard-2026-07-20.txt`](benchmarks/juice-shop-scoreboard-2026-07-20.txt).

**Second target — [Escape's Duck Store](https://duck-store.escape.tech/):** a deliberately-vulnerable REST API built to defeat the training-data memorisation that inflates Juice Shop numbers. API-first flaws — BOLA/BFLA, mass-assignment privilege escalation, SSRF, business-logic abuse. Black-box, no schema handed to it: **22 / 22**. `juiceshop_report` and the engagement reporter write it up against **14 OWASP** categories, scoring **F1 0.95** against the ground-truth labels.

A number is only worth the run you can regenerate. Every row names the model and the date it was produced on, and a version that has not been re-benchmarked does not inherit the previous one's score.

</details>

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:08090b,50:e11d2b,100:08090b&height=3" width="100%" alt="">

## 🔁 The loop

One loop, whether it is fixing your code or working a target, and the second half is the point: **do the thing, then prove it worked.** No confidence scores, no "looks right."

```text
   plan ──▶ act ──▶ observe ──▶ PROVE ──▶ record ──▶ next
    ▲         │         │          │          │         │
    │      tool or    parse     tests or    hashed      │
    │       shell     output     oracle     ledger      │
    └───────────────── not done until verified ─────────┘
```

- **Plan** — reads the situation and picks the single most likely next move.
- **Act** — reaches for a dedicated tool first, raw shell only when nothing fits.
- **Observe** — parses real output, not vibes.
- **Prove** — the test suite goes green, or the oracle confirms with a marker. Unproven ≠ done.
- **Record** — what changed and what proved it, so the same ground is never re-covered.

**"Not done until verified" is enforced, not requested.** An instruction in a prompt is advice, and advice is what a model drops on step forty of a long job. So the loop has a **gate**: if a turn changed files in the workspace and never once ran anything to check them, the turn does not end — Basilisk runs `workspace_verify` itself, which re-runs the repo's tests and classifies the result against the baseline, so the reply comes back saying what you fixed **and what you broke**. It fires at most once per request, and it decides on two facts — files were written, nothing was run — never on how confidently the reply was worded.

The mirror of it points at research: ask something that needs a live source, and if no web tool ran all turn, the app performs the search itself rather than letting the turn end on a promise.

**Steer it without stopping it:** while Basilisk is working, type a nudge and press **Enter** — it lands as a mid-run suggestion the loop folds in on its next step. The Stop control (click the send button, or Escape) is separate and always stops.

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:08090b,50:e11d2b,100:08090b&height=3" width="100%" alt="">

## 🛡️ Two modes, one leash

Capability and safety are decoupled on purpose.

- **Leashed (default)** — the general and coding assistant: the workspace, unrestricted reading, the full shell and desktop. The offensive suite is **refused at the loader**, not merely hidden. Ask it what it can do and it tells you accurately, then reminds you nothing offensive is loaded until you arm it.
- **🐉 Unleash** — one tap arms the offensive suite and the mission loop, then **waits**. Send an objective and it runs with no per-command approval until that objective is verifiably done, or you stand it down.

**The floor never moves.** The destructive-command gate and the fail-closed scope gate fire in both modes. The catastrophic-command check is not a naive string match — it sees through obfuscation like `rm${IFS}-rf${IFS}/` (**`$IFS`** substitution) and `sh -c '…'` wrappers, and there is **no "run anyway"** override on a catastrophic hit. It is tuned against false positives too: `rm -rf ~/loot` is *your* loot directory and runs fine; it is `/` and raw device nodes that are blocked. The safety guardrail is a byte-identical, test-pinned block, and the engine will not ship if it drifts.

**Reading the web is tiered, not one closed list.** Trusted sources (NVD, OWASP, PortSwigger) are read freely. Community sources like **exploit-db** and GitHub sit on the **approval side, outside the autonomous loop** — any public host is reachable after a one-tap approval, never auto-fetched mid-run. Cloud-metadata endpoints (`169.254.169.254`) and loopback are refused outright.

**Untrusted input is treated as untrusted.** Archives are handled with hard guards — **Zip slip** (`commonpath`-checked extraction), **Zip bombs**, **Symlink entries** — all refused *before* anything is written, and refusals are reported rather than silently dropped. Repo work can run inside a **`bubblewrap`** sandbox. A stray `.env` is flagged and kept out of the model's context. Your sudo password never reaches the model, and the agent cannot edit its own safety code.

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:08090b,50:e11d2b,100:08090b&height=3" width="100%" alt="">

## 🧬 Inside the machine

~63k lines of Python, standard-library only for the engine (GTK for the desktop), across a deliberately boring, testable architecture:

| Module | What it is |
|---|---|
| `basilisk.py` | GTK4 / libadwaita desktop app — the chat, the UI, the live activity feed, streaming |
| `basilisk_core.py` | The turn engine — **149 tools**, tool-call parsing across every model dialect, the destructive-command floor |
| `basilisk_persona.py` | The assistant and engagement roles, the load-bearing safety guardrail, capability-aware prompting |
| `basilisk_safety.py` · `basilisk_scope.py` | The irreversible-command floor, and the scope gate that fails **closed** |
| `basilisk_ext/workspace.py` · `sandbox.py` | The repo workspace, `bubblewrap` sandbox, `workspace_baseline` / `workspace_verify` / `workspace_export` |
| `basilisk_ext/memory.py` · `recall.py` | Persistent memory with `memory_forget`, backed by **SQLite** |
| `basilisk_ext/mcp.py` · `skills.py` | MCP client and the skill loader |
| `basilisk_ext/exploits.py` | The 56 exploit builders *(armed only)* |
| `basilisk_ext/zdayfind.py` | Source variant hunter — `zday_scan`, `find_variants`, the signature catalogue |
| `basilisk_ext/oracle.py` · `verify.py` | Verified-exploitation oracle and out-of-band listener |

**Tool-call dialects.** Models do not agree on how to emit a tool call, and several use their own trained format no matter what the prompt asks. Basilisk normalises *every* dialect it has seen to one canonical form — `<tool name="x">{json}</tool>`, DeepSeek's native special tokens, **DeepSeek-V4's DSML tags in every pipe rendering**, `<tool_call>`, `<invoke>`, `<function=…>`, fenced-JSON bodies, `<parameter>` child tags — before anything parses or renders. Parsing and display are driven from the *same* normalised text by construction, because when they disagree a call executes **and** leaks its raw markup into the chat.

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:08090b,50:e11d2b,100:08090b&height=3" width="100%" alt="">

## 🔬 Engineering

**Stdlib only** for the engine. No pytest, no network, no fixtures, no account — **4,582 assertions across 75 suites**, run in under a minute. Four of those suites are adversarial probes that report *findings* rather than a pass count, so their checks are not in that total.

Every fix ships with a regression that *fails* on the old code and *passes* on the new. Real GTK is spun up under Xvfb for the UI suites; the chat-bubble layout alone is pinned by 140 fitting checks. Repo work is covered end-to-end rather than layer by layer — a deliberately broken repo is opened as a folder, baselined red, edited through four different tool-call dialects, verified green, diffed and exported, with a 6,000-line file paged and rewritten on the way past.

The probe suites earned their place: the first run of the intent probe found thirteen real defects, and the backend probe found a 400 about `max_tokens` being reported to the operator as *"authentication failed — check your API key."* The safety guardrail is verified byte-identical on every build, the CSS is checked ASCII-only, and every packaged artifact is re-tested from a clean extract before it is called done.

This is a one-person project. Every one of those assertions is there because something broke once and should not get the chance to break again.

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:08090b,50:e11d2b,100:08090b&height=3" width="100%" alt="">

## 🜃 Why it's free, and who built it

There is a version of this with a pricing page, three tiers and a "contact sales" button. Everything on this page would still be true and the number at the bottom would be four figures a year.

I would rather it went to the people who would actually use it.

I build this **solo, around a full-time job** — nights, weekends, the hours most people spend switched off. It started as a way to learn by building the tool I wanted to exist. There is no team, no funding, no roadmap deck. There is one person who thinks this kind of tooling should not need a purchase order, and a test suite big enough to keep one pair of hands honest.

**MIT. All of it.** Not a trial, not a community edition with the good parts removed, not open-core with the safety gates behind a licence key. No account, no telemetry, no usage cap. Every number on this page was produced by the exact code you are about to clone.

If it earns its place in your kit, star the repo and tell someone who would use it. That is the whole price.

## 📜 License

**MIT.** Take it, fork it, use it on what you are allowed to touch.

<div align="center">

<br/>

### Built by one person, around a day job. Verified by 4,582 assertions. Priced at nothing.

<sub>Clone it, read it, run the suite, then point it at something you own.</sub>

<br/><br/>

<a href="https://github.com/the-priest/PriestsBasilisk"><img src="https://img.shields.io/badge/★%20Star%20the%20repo-e11d2b?style=for-the-badge&labelColor=08090b" alt="Star the repo"></a>
<a href="#-install"><img src="https://img.shields.io/badge/Install%20in%20one%20line-7d121b?style=for-the-badge&labelColor=08090b" alt="Install"></a>

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:08090b,50:4a0a11,100:e11d2b&height=130&section=footer&text=prove%20everything&fontColor=ffffff&fontSize=28&fontAlignY=72&animation=twinkling" width="100%" alt="prove everything"/>

</div>
