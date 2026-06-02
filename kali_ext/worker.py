#!/usr/bin/env python3
"""
worker — Kali's headless background companion.

Why a separate process and not "daemonize the GUI": Kali is a GTK app; you
don't systemd a window.  The reliability the Hermes video is selling comes
from the BACKGROUND responsibilities — periodic system checks, memory
consolidation, skill curation — which have no UI and genuinely want to run
as a supervised service.  So we split those out here.  The GUI stays a GUI;
this worker runs under `systemd --user` with auto-restart and writes events
to a spool file the GUI tails.

It is fully optional.  If it never runs, Kali works exactly as today (the
in-app watcher thread still exists).  If it does run, disable the in-app
watcher to avoid double-checking.

Talks to the system through kali_core's read-only tools IF that module is
importable (it lives next to this package in the install).  It imports
nothing UI.  It writes only under ~/.local/share/kali/ext/.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

EXT_DIR = Path(os.path.expanduser("~/.local/share/kali/ext"))
SPOOL = EXT_DIR / "events.jsonl"
HEARTBEAT = EXT_DIR / "worker.heartbeat"

_run = True


def _stop(*_a):
    global _run
    _run = False


def _emit(event: Dict[str, Any]) -> None:
    EXT_DIR.mkdir(parents=True, exist_ok=True)
    event["ts"] = time.time()
    with open(SPOOL, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
    # keep the spool bounded
    try:
        lines = SPOOL.read_text().splitlines()
        if len(lines) > 500:
            SPOOL.write_text("\n".join(lines[-500:]) + "\n")
    except Exception:
        pass


def _load_settings() -> Dict[str, Any]:
    p = Path(os.path.expanduser("~/.config/kali/settings.json"))
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _try_core():
    """Import kali_core for its read-only tools, if present.  None if not."""
    # The install puts kali_core.py in ~/.local/share/kali; add it to path.
    sys.path.insert(0, os.path.expanduser("~/.local/share/kali"))
    try:
        import kali_core  # type: ignore
        return kali_core
    except Exception:
        return None


def main() -> int:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    EXT_DIR.mkdir(parents=True, exist_ok=True)
    core = _try_core()

    last_update_check = 0.0
    last_curate = 0.0
    known_downloads: Optional[set] = None

    _emit({"kind": "worker", "msg": "started", "core": bool(core)})

    while _run:
        HEARTBEAT.write_text(str(time.time()))
        # Re-read settings every tick so enabling/disabling takes effect
        # without restarting the service.  If the worker is not explicitly
        # enabled, it does NOTHING — no checks, no curation, no reads.
        settings = _load_settings()
        if not settings.get("worker_enabled", False):
            for _ in range(30):
                if not _run:
                    break
                time.sleep(1)
            continue
        interval = max(60, int(settings.get("worker_interval_seconds", 300)))
        try:
            # ── downloads watch ──
            if core and settings.get("watcher_check_downloads", True):
                r = core.tool_recent_downloads(50)
                if r.get("ok"):
                    names = {f["name"] for f in r["files"]}
                    if known_downloads is None:
                        known_downloads = names  # prime, don't spam on boot
                    else:
                        new = [f for f in r["files"]
                               if f["name"] not in known_downloads
                               and not f["is_dir"]
                               and f.get("age_seconds", 9999) < 3600]
                        if new:
                            _emit({"kind": "downloads",
                                   "detail": ", ".join(f["name"] for f in new[:3])})
                        known_downloads = names

            # ── security updates (every 4h) ──
            now = time.time()
            if (core and settings.get("watcher_check_updates", True)
                    and now - last_update_check > 4 * 3600):
                last_update_check = now
                r = core.tool_check_updates()
                if r.get("ok") and r.get("security_count", 0) > 0:
                    _emit({"kind": "security_updates",
                           "count": r["security_count"]})

            # ── skill curation (daily) ──
            if now - last_curate > 24 * 3600:
                last_curate = now
                try:
                    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
                    from kali_ext import skills as _sk  # type: ignore
                    store = _sk.SkillStore(EXT_DIR / "skills")
                    res = store.curate()
                    if res.get("archived"):
                        _emit({"kind": "curator",
                               "archived": res["archived"]})
                except Exception as e:
                    _emit({"kind": "worker", "msg": f"curate error: {e}"})

        except Exception as e:
            _emit({"kind": "worker", "msg": f"tick error: {e}"})

        # responsive sleep
        for _ in range(interval):
            if not _run:
                break
            time.sleep(1)

    _emit({"kind": "worker", "msg": "stopped"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
