<div align="center">

# Kali

**A local, loyal AI assistant that lives on your machine.**

Groq cloud primary. Ollama local fallback. Full OS access.
Reads files. Watches services. Audits security. Runs commands with your permission.

</div>

---

## What it is

Kali is a personal AI assistant in the shape of a GTK4 chat app, named for the Hindu goddess and the Linux distribution both. She talks to you, but she also has hands on your machine: she can read your files, snapshot system state, scan your network, audit your security posture, check for updates, watch your Downloads folder, tail your journal, and run shell commands (with a y/n prompt every time).

She's built for one operator — you — and she behaves like it. No corporate guardrails, no boilerplate hedging, no "as an AI language model." She's witty, direct, loyal, and stays on your side.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                       kali.py (UI)                      │
│              GTK4 + libadwaita, Catppuccin Mocha        │
└───────────────────────┬─────────────────────────────────┘
                        │
        ┌───────────────┴────────────────┐
        │                                │
   ┌────▼─────┐                    ┌─────▼──────┐
   │ kali_    │                    │ kali_      │
   │ core.py  │                    │ persona.py │
   │          │                    │            │
   │ backends │                    │ system     │
   │ tools    │                    │ prompt     │
   │ chat DB  │                    │ assembly   │
   │ audit    │                    └────────────┘
   │ watcher  │
   └────┬─────┘
        │
  ┌─────┴──────┐
  │            │
┌─▼──┐    ┌────▼────┐
│Groq│    │  Ollama │
│API │    │ (local) │
└────┘    └─────────┘
```

**Provider routing.** Kali prefers Groq when online and a key is configured. Falls back to Ollama when offline, when Groq rate-limits or errors, or when you toggle "Prefer Groq" off in Settings. The active provider is shown as a pill in the header.

## Install

**One-liner (recommended):**

```bash
curl -fsSL https://raw.githubusercontent.com/the-priest/oracle5/main/install.sh | bash
```

What it installs:

- Python 3.10+ check (fails fast if not present)
- GTK4 + libadwaita bindings (apt / pacman / dnf, auto-detected)
- `groq` Python library (cloud backend)
- Ollama + a small fallback model (`llama3.2:1b` by default, ~1.3 GB)
- The three Python files + dragon SVG icon
- A `kali` launcher in `~/.local/bin/`
- A `.desktop` entry so Kali shows up in your app grid
- A systemd `--user` unit so Ollama starts at login
- An optional prompt for your Groq API key (you can skip and add it later in Settings)

**Time:** ~3-8 min on first install (model download is the bottleneck). Re-runs are ~5 seconds.

**Update later:** re-run the same one-liner. It detects what's done and only does what's missing.

**Uninstall:** `~/.local/share/kali/install.sh --uninstall` (chat history kept).

### Removing a previous Oracle install

If you installed the older Oracle version of this app, the installer auto-detects it and prompts you to remove it. Or do it explicitly:

```bash
~/.local/share/kali/install.sh --remove-oracle
```

This stops and disables `oracle-ollama.service`, removes `~/.local/bin/oracle`, the desktop entry, the systemd unit, and wipes `~/.local/share/oracle/` and `~/.config/oracle/`. Your chat history migrates to Kali if Kali doesn't already have its own DB. Your Kali install is not touched.

### Manual install

```bash
git clone https://github.com/the-priest/oracle5.git kali
cd kali
./install.sh
```

### Flags

| flag                 | what it does                                            |
| -------------------- | ------------------------------------------------------- |
| `--update`           | explicit update (same as default install)               |
| `--uninstall`        | remove Kali (chat history kept)                         |
| `--remove-oracle`    | remove the old Oracle install (Kali untouched)          |
| `--refresh-ollama`   | re-run Ollama's installer to update it                  |
| `--no-systemd`       | don't install the systemd unit file                     |
| `--no-ollama`        | skip Ollama entirely (Groq-only setup)                  |
| `--no-model`         | don't pull a local model                                |
| `--no-groq`          | don't install the groq library or prompt for a key      |
| `--no-prompt`        | non-interactive (skips Groq key prompt)                 |

### Env overrides

```bash
KALI_MODEL=qwen2.5:0.5b   ./install.sh    # tiny but capable (~400 MB)
KALI_MODEL=llama3.2:3b    ./install.sh    # better but ~2 GB
GROQ_API_KEY=gsk_...      ./install.sh    # preset, no prompt
KALI_REPO=user/fork  KALI_BRANCH=dev  ./install.sh
```

## Get a Groq API key

Free, fast, the primary path: <https://console.groq.com>

Sign up, create a key (`gsk_...`), paste it into Settings → Backends → Groq → API key. Or pass it during install via the prompt or `GROQ_API_KEY=...`. Stored locally in `~/.config/kali/settings.json` only — never leaves your machine except in API calls to Groq.

## What Kali can do on your system

Everything below runs as your user (no sudo). Read-only tools fire without confirmation. `run` always prompts y/n with the exact command and her reason.

| tool                 | what it does                                                    |
| -------------------- | --------------------------------------------------------------- |
| `read_file`          | Read any file you can read.  Sensitive paths (~/.ssh, ~/.gnupg) prompt for permission. |
| `list_dir`           | List a directory.                                               |
| `find_file`          | Find files by name pattern.                                     |
| `system_info`        | uname, OS, uptime, RAM, load.                                   |
| `disk_usage`         | `df -h` filtered to real filesystems.                           |
| `processes`          | Top processes by CPU.                                           |
| `network_status`     | Interfaces, default gateway, online check.                      |
| `recent_downloads`   | What's new in ~/Downloads.                                      |
| `check_updates`      | `apt list --upgradable`, with security flagging.                |
| `service_status`     | Inspect any systemd service.                                    |
| `journal_tail`       | Recent system log lines (any unit).                             |
| `run`                | **Y/N-confirmed** shell command. She tells you why.             |
| `audit`              | 10-check parallel security audit. Grade A+ → F.                 |
| `scan_net`           | `nmap -sn` on your local subnet (ARP fallback if no nmap).      |

### Security audit checks

Firewall (ufw/iptables/nftables) · Listening ports on all interfaces · SSH server config · Pending security updates · Kernel age · Failed SSH login attempts · Disk encryption (LUKS) · Home directory permissions · AppArmor / SELinux · Shell history secret scan.

### Watcher (optional)

A background thread that periodically:

- Counts pending security updates (every 4h)
- Watches for new files in ~/Downloads (every cycle)
- Tails the journal for notable events (failed logins, USB device events, OOM kills)

Off by default. Enable in Settings → Behaviour → Watcher. Surfaces events as transient banners in the chat area.

## What Kali can NOT do

- **Modify her own code.** Hardcoded off. She can read her own source if you ask, but she can't write to it. This is deliberate.
- **Persist state outside the chat DB and settings file.** No hidden side-channels.
- **Reach the internet directly.** The Groq backend is for text generation only. She doesn't browse, scrape, or open URLs unless you do it through her by running `curl` via the `run` tool with your confirmation.
- **Run as root.** Everything runs as your user. If you want her to do something privileged, prefix the command with `sudo` and she'll show you the exact line before it runs.

## File layout

```
~/.local/share/kali/
  ├── kali.py                  # UI
  ├── kali_core.py             # backends, tools, audit
  ├── kali_persona.py          # personality + system prompt
  ├── kali-dragon.svg          # icon
  ├── chats.db                 # SQLite chat history
  ├── kali.log                 # diagnostics
  └── backups/
       └── chats-YYYYMMDD.db   # auto-backup before each install

~/.config/kali/
  └── settings.json            # all settings, including Groq key

~/.local/bin/kali              # launcher
~/.local/share/applications/kali.desktop
~/.config/systemd/user/kali-ollama.service
```

## Tweaking the persona

Open `~/.local/share/kali/kali_persona.py` in your editor. The persona is plain Python strings. Edit `PERSONA_CORE`, `OPERATOR_PROFILE`, `TOOL_CONTRACT`, or `CAPABILITIES`. Save and relaunch.

For lighter edits (per-machine notes that get appended to the prompt), use Settings → Persona → Custom addendum. This survives upgrades; edits to `kali_persona.py` directly will get clobbered when you re-run `install.sh`.

## Development

```bash
git clone https://github.com/the-priest/oracle5.git kali
cd kali

# Run from source
python3 kali.py

# Syntax check
python3 -c "import ast; [ast.parse(open(f).read()) for f in ('kali.py','kali_core.py','kali_persona.py')]"

# Push changes
./push.sh "your commit message"
```

## License

MIT.  See LICENSE.

## Credits

Built by The Priest. The dragon icon is original geometric art inspired by — but not a copy of — the official Kali Linux logo (which is a trademark of OffSec). To use the official logo instead, drop the SVG at `~/.local/share/kali/kali-dragon.svg`; the .desktop file will pick it up.

---

<sub>Kali is not affiliated with OffSec, Kali Linux, or Groq.</sub>
