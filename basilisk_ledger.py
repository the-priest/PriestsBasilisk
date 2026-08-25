"""
basilisk_ledger.py — an append-only, integrity-checkable evidence ledger for every
command Basilisk runs.

The difference between a chat transcript and a defensible pentest deliverable is
*evidence*: a tamper-evident record of exactly what ran, when, with what result,
and proof the output wasn't edited after the fact.  This module is that record.

For each executed command it appends one JSON line to
``~/.config/basilisk/evidence/<engagement>.jsonl`` capturing the timestamp,
engagement, monotonically increasing step number, the command and the model's
stated reason, the working directory and user, the exit code, the wall-clock
duration, and — critically — the SHA-256 of stdout and stderr.  The full output
is written to a side artifact file whose hash is recorded, so the ledger line
stays small while the evidence stays complete and verifiable: ``verify()``
re-hashes every artifact and reports any mismatch, which catches after-the-fact
tampering with the captured output.

Design rules:
  • Pure stdlib (json, os, time, hashlib, pathlib, threading) — GTK-free and
    trivially unit-testable offline.
  • FAIL-SAFE: a ledger write must never break command execution.  Every public
    entry point swallows its own errors and returns a sentinel rather than
    raising into the caller's run loop.
  • Append-only: events are never rewritten in place, so the file itself is the
    audit trail.
  • Thread-safe: a lock guards the append, since commands run on a worker
    thread.

Nothing here decides whether a command may run — that's the safety floor's job
(basilisk_safety).  The ledger only records what already happened.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_LOCK = threading.RLock()

# Only allow tame engagement names so they're safe as filenames.
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_DEFAULT_ENGAGEMENT = "default"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_name(name: Optional[str]) -> str:
    name = (name or "").strip() or _DEFAULT_ENGAGEMENT
    name = _SAFE_NAME_RE.sub("-", name).strip("-.") or _DEFAULT_ENGAGEMENT
    return name[:64]


class EvidenceLedger:
    """Append-only evidence store for a tree of engagements.

    ``base_dir`` defaults to ~/.config/basilisk/evidence.  One ``.jsonl`` file and
    one ``<engagement>.artifacts/`` directory exist per engagement.
    """

    def __init__(self, base_dir: Optional[Path] = None,
                 engagement: Optional[str] = None):
        if base_dir is None:
            base_dir = Path(os.path.expanduser("~")) / ".config" / "basilisk" / "evidence"
        self.base_dir = Path(base_dir)
        self._engagement = _safe_name(engagement)
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass  # fail-safe: recording will no-op if the dir can't be made

    # ── engagement selection ──────────────────────────────────────────
    @property
    def engagement(self) -> str:
        return self._engagement

    def set_engagement(self, name: str) -> str:
        """Switch the active engagement (creates it lazily on first write)."""
        with _LOCK:
            self._engagement = _safe_name(name)
        return self._engagement

    def list_engagements(self) -> List[str]:
        try:
            return sorted(p.stem for p in self.base_dir.glob("*.jsonl"))
        except Exception:
            return []

    def _ledger_path(self, engagement: Optional[str] = None) -> Path:
        return self.base_dir / f"{_safe_name(engagement or self._engagement)}.jsonl"

    def _artifact_dir(self, engagement: Optional[str] = None) -> Path:
        return self.base_dir / f"{_safe_name(engagement or self._engagement)}.artifacts"

    def _next_step(self, engagement: str) -> int:
        """One-based step counter — one past the HIGHEST step on record.

        This used to be `number of lines + 1`, which aliases the moment a
        line is removed: delete line 5 of 9 and the next event is numbered 9
        while step 9 already exists. That is not a cosmetic collision —
        `_write_artifact` names the file `step-0009.txt`, so the new event
        OVERWRITES the earlier event's captured output. A single deletion
        therefore destroyed a second, unrelated piece of evidence, silently,
        in a module whose entire purpose is that nothing goes missing
        without a trace.

        Taking the maximum recorded step means step numbers only ever move
        forward, so a gap stays visibly a gap and no artifact is ever
        reused. Falls back to the line count if nothing parses.
        """
        path = self._ledger_path(engagement)
        if not path.exists():
            return 1
        try:
            highest = 0
            lines = 0
            with open(path, "r", encoding="utf-8") as f:
                for ln in f:
                    if not ln.strip():
                        continue
                    lines += 1
                    try:
                        obj = json.loads(ln)
                    except Exception:
                        continue
                    if isinstance(obj, dict):
                        try:
                            highest = max(highest, int(obj.get("step") or 0))
                        except (TypeError, ValueError):
                            continue
            return max(highest, lines) + 1
        except Exception:
            return 1

    # ── the hash chain ────────────────────────────────────────────────
    # WHY THIS EXISTS.  Before it, every ledger line was integrity-checked in
    # ISOLATION: `verify()` re-hashed each artifact against the hash on its
    # own line. That catches editing a captured output. It does not catch —
    # and reported `intact: true` for — any of:
    #
    #   · deleting a whole line together with its artifact file: the scan
    #     that ran is simply not in the record, and nothing says so;
    #   · reordering lines, so the record no longer shows what ran first;
    #   · rewriting a line's command/reason/rc wholesale, since the only
    #     hash on the line covered the ARTIFACT, never the line itself.
    #
    # For a chat transcript that would be tolerable. For the artefact this
    # module's docstring calls "a defensible pentest deliverable", tamper
    # evidence that cannot see a deletion is the wrong shape entirely: the
    # cheapest and most likely edit is the one that leaves no mark.
    #
    # Each event now carries `prev` — the digest of the event before it —
    # and `entry_sha256`, its own digest. Removing, reordering or editing a
    # line breaks the link at that point and `verify()` names the step.
    _GENESIS = "0" * 64

    @staticmethod
    def _entry_digest(event: Dict[str, Any]) -> str:
        """Digest of one event, over a canonical form.

        Deliberately independent of how the line happens to be written:
        sorted keys, no spaces. A re-serialisation with different separators
        must not read as tampering.
        """
        body = {k: v for k, v in event.items() if k != "entry_sha256"}
        return _sha256(json.dumps(body, ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":")).encode("utf-8"))

    def _last_digest(self, engagement: str) -> str:
        """The digest to chain the next event onto."""
        events = self.read_events(engagement)
        for e in reversed(events):
            d = e.get("entry_sha256")
            if d:
                return str(d)
        return self._GENESIS

    # ── recording ─────────────────────────────────────────────────────
    def record(self, command: str, reason: str, result: Dict[str, Any],
               kind: str = "command") -> Optional[Dict[str, Any]]:
        """Append one evidence event for an executed command.

        ``result`` is the dict returned by tool_run_command:
        {ok, rc, stdout, stderr, error, ...}.  Returns the event dict that was
        written (handy for tests / display), or None if recording failed — and
        a None return must be treated as "carry on", never as an error.
        """
        try:
            with _LOCK:
                engagement = self._engagement
                step = self._next_step(engagement)
                ts = time.time()

                stdout = result.get("stdout") or ""
                stderr = result.get("stderr") or ""
                so_b = stdout.encode("utf-8", "replace")
                se_b = stderr.encode("utf-8", "replace")

                artifact_rel = None
                artifact_sha = None
                if so_b or se_b:
                    artifact_rel = self._write_artifact(
                        engagement, step, command, so_b, se_b)
                    # ── HASH THE FILE THAT WAS ACTUALLY WRITTEN ──
                    # The per-section hashes below stay, but they cannot BE the
                    # integrity check.  verify() had to RE-DERIVE stdout and
                    # stderr by string-splitting the human-readable artifact on
                    # "\n# --- stderr ---\n", and any captured output containing
                    # that literal split it in the wrong place — so an untouched
                    # artifact reported "hash mismatch" and the ledger accused
                    # itself.  Reading a previous artifact is something the tool
                    # contract actively tells Basilisk to do, so this was
                    # reachable in ordinary use.
                    #
                    # Hashing the whole file deletes the re-derivation step: any
                    # byte that changes is caught, whatever it happens to
                    # contain.  It also closes the hole where a step with EMPTY
                    # stdout recorded `stdout_sha256: None` and the check
                    # `None in (None, <hash>)` passed unconditionally — forged
                    # output could be pasted into that artifact and verify()
                    # still said intact.
                    if artifact_rel:
                        try:
                            artifact_sha = _sha256(
                                (self.base_dir / artifact_rel).read_bytes())
                        except Exception:
                            artifact_sha = None

                event = {
                    "ts": round(ts, 3),
                    "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
                    "engagement": engagement,
                    "step": step,
                    "kind": kind,
                    "command": command,
                    "reason": reason or "",
                    "cwd": _safe_cwd(),
                    "user": _safe_user(),
                    "ok": bool(result.get("ok", False)),
                    "rc": result.get("rc"),
                    "error": result.get("error"),
                    "duration_ms": result.get("duration_ms"),
                    "stdout_bytes": len(so_b),
                    "stderr_bytes": len(se_b),
                    "stdout_sha256": _sha256(so_b) if so_b else None,
                    "stderr_sha256": _sha256(se_b) if se_b else None,
                    "artifact": artifact_rel,
                    "artifact_sha256": artifact_sha,
                    "prev": self._last_digest(engagement),
                }
                event["entry_sha256"] = self._entry_digest(event)
                line = json.dumps(event, ensure_ascii=False)
                with open(self._ledger_path(engagement), "a",
                          encoding="utf-8") as f:
                    f.write(line + "\n")
                return event
        except Exception:
            return None  # fail-safe — never break the run loop

    def _write_artifact(self, engagement: str, step: int, command: str,
                        so_b: bytes, se_b: bytes) -> Optional[str]:
        try:
            adir = self._artifact_dir(engagement)
            adir.mkdir(parents=True, exist_ok=True)
            fname = f"step-{step:04d}.txt"
            blob = (b"# command: " + command.encode("utf-8", "replace") + b"\n"
                    b"# --- stdout ---\n" + so_b +
                    b"\n# --- stderr ---\n" + se_b + b"\n")
            (adir / fname).write_bytes(blob)
            return f"{adir.name}/{fname}"
        except Exception:
            return None

    # ── review / export ───────────────────────────────────────────────
    def read_events(self, engagement: Optional[str] = None,
                    limit: Optional[int] = None) -> List[Dict[str, Any]]:
        path = self._ledger_path(engagement)
        if not path.exists():
            return []
        events: List[Dict[str, Any]] = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for ln in f:
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        obj = json.loads(ln)
                    except Exception:
                        continue  # skip a corrupted line, keep the rest
                    # …and skip a line that PARSES but is not an event.
                    # `null`, `123` and `[]` are all valid JSON, so they got
                    # appended and every consumer then called e.get(...) on
                    # them: summary(), verify() and export_markdown() all died
                    # with AttributeError. Given this module's own threat model
                    # — someone editing the evidence directory — a five-byte
                    # append turned the whole evidence system into a traceback
                    # instead of a tamper report, which is denial-of-evidence.
                    if isinstance(obj, dict):
                        events.append(obj)
        except Exception:
            return events
        # `events[-0:]` is the WHOLE list, so `limit=0` returned everything —
        # the exact opposite of what it says. Latent today (no caller passes
        # it), which is also why nothing caught it.
        if limit is not None:
            if limit <= 0:
                return []
            return events[-limit:]
        return events

    def summary(self, engagement: Optional[str] = None) -> Dict[str, Any]:
        events = self.read_events(engagement)
        ok = sum(1 for e in events if e.get("ok"))
        failed = len(events) - ok
        return {
            "engagement": _safe_name(engagement or self._engagement),
            "steps": len(events),
            "ok": ok,
            "failed": failed,
            "first_ts": events[0].get("ts") if events else None,
            "last_ts": events[-1].get("ts") if events else None,
        }

    def verify(self, engagement: Optional[str] = None) -> Dict[str, Any]:
        """Re-hash every artifact and confirm it matches the recorded SHA-256.

        This is the tamper-evidence: if a captured output file was edited after
        the fact, its hash no longer matches the ledger line and it shows up
        here as a mismatch.
        """
        events = self.read_events(engagement)
        checked = matched = 0
        problems: List[Dict[str, Any]] = []
        for e in events:
            rel = e.get("artifact")
            if not rel:
                continue
            checked += 1
            apath = self.base_dir / rel
            if not apath.exists():
                problems.append({"step": e.get("step"), "issue": "artifact missing"})
                continue
            try:
                blob = apath.read_bytes()
            except Exception:
                problems.append({"step": e.get("step"), "issue": "artifact unreadable"})
                continue
            # ── WHOLE-FILE HASH IS THE CHECK ──
            # Nothing is re-derived: the bytes on disk are hashed and compared
            # to the hash taken the moment they were written. Whatever the
            # output contains — including this file's own section markers —
            # cannot confuse it, and there is no "missing hash" branch to pass
            # through, so a step whose stdout was empty is verified exactly as
            # strictly as one whose stdout was not.
            recorded = e.get("artifact_sha256")
            if recorded:
                if _sha256(blob) == recorded:
                    matched += 1
                else:
                    problems.append({"step": e.get("step"),
                                     "issue": "hash mismatch"})
                continue
            # LEGACY EVENT (written before artifact_sha256 existed). Fall back
            # to the section comparison so an older evidence directory still
            # verifies — but WITHOUT the hole: a recorded None now means "this
            # section must be empty", it is not a free pass.
            so = _extract_section(blob, b"# --- stdout ---\n",
                                  b"\n# --- stderr ---\n")
            se = _extract_section(blob, b"\n# --- stderr ---\n", None)
            so_ok = (e.get("stdout_sha256") or None) == (_sha256(so) if so else None)
            se_ok = (e.get("stderr_sha256") or None) == (_sha256(se) if se else None)
            if so_ok and se_ok:
                matched += 1
            else:
                problems.append({"step": e.get("step"),
                                 "issue": "hash mismatch",
                                 "legacy": True})
        # ── THE CHAIN ──────────────────────────────────────────────────
        # Everything above verifies each line against ITSELF, which is why
        # a deleted line used to come back `intact: true` — there was no
        # line left to disagree with. Walk the links instead: each event
        # names the digest of the one before it, so a removal, a reorder or
        # an edited command shows up as a break AT the step where it
        # happened, which is the report the operator actually needs.
        chain_checked = chain_ok = 0
        expected = self._GENESIS
        legacy = 0
        started = False
        for e in events:
            own = e.get("entry_sha256")
            if not own:
                # Written before the chain existed. Not a break — but it is
                # not evidence of continuity either, and saying so is the
                # honest report. A legacy prefix is tolerated; a legacy line
                # AFTER the chain has started is a break, because that is
                # what a stripped line looks like.
                if started:
                    problems.append({"step": e.get("step"),
                                     "issue": "unchained line inside a "
                                              "chained ledger"})
                else:
                    legacy += 1
                continue
            started = True
            chain_checked += 1
            recomputed = self._entry_digest(e)
            if recomputed != own:
                problems.append({"step": e.get("step"),
                                 "issue": "ledger line was edited "
                                          "(entry hash mismatch)"})
                expected = str(own)      # resync so one edit is one report
                continue
            if str(e.get("prev") or "") != expected:
                problems.append({"step": e.get("step"),
                                 "issue": ("chain break — the preceding "
                                           "event is missing, reordered or "
                                           "altered")})
            else:
                chain_ok += 1
            expected = str(own)

        return {
            "engagement": _safe_name(engagement or self._engagement),
            "artifacts_checked": checked,
            "artifacts_matched": matched,
            "chain_checked": chain_checked,
            "chain_ok": chain_ok,
            "legacy_unchained": legacy,
            "intact": len(problems) == 0,
            "problems": problems,
        }

    def export_markdown(self, engagement: Optional[str] = None) -> str:
        """A human-readable evidence report for the engagement."""
        eng = _safe_name(engagement or self._engagement)
        events = self.read_events(engagement)
        if not events:
            return f"# Evidence — {eng}\n\n_No recorded commands yet._\n"
        s = self.summary(engagement)
        out = [f"# Evidence ledger — {eng}", ""]
        out.append(f"- Steps: **{s['steps']}**  (ok {s['ok']} · failed {s['failed']})")
        if s["first_ts"] and s["last_ts"]:
            span = max(0, int(s["last_ts"] - s["first_ts"]))
            out.append(f"- Window: {events[0].get('iso','?')} → "
                       f"{events[-1].get('iso','?')}  ({span}s)")
        v = self.verify(engagement)
        out.append(f"- Integrity: {'✅ all artifacts intact' if v['intact'] else '⚠ ' + str(len(v['problems'])) + ' problem(s)'}")
        out.append("")
        out.append("| # | time (UTC) | rc | command | reason |")
        out.append("|---|---|---|---|---|")
        for e in events:
            rc = e.get("rc")
            rc_s = "—" if rc is None else str(rc)
            cmd = (e.get("command") or "").replace("|", "\\|")[:90]
            rsn = (e.get("reason") or "").replace("|", "\\|")[:60]
            out.append(f"| {e.get('step')} | {e.get('iso','?')} | {rc_s} | `{cmd}` | {rsn} |")
        return "\n".join(out) + "\n"


def _extract_section(blob: bytes, start: bytes, end: Optional[bytes]) -> bytes:
    i = blob.find(start)
    if i < 0:
        return b""
    i += len(start)
    if end is None:
        j = len(blob)
        # trim the single trailing newline added at write time
        seg = blob[i:j]
        return seg[:-1] if seg.endswith(b"\n") else seg
    j = blob.find(end, i)
    if j < 0:
        j = len(blob)
    return blob[i:j]


def _safe_cwd() -> str:
    try:
        return os.getcwd()
    except Exception:
        return "?"


def _safe_user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return os.environ.get("USER", "?")
