#!/usr/bin/env python3
"""
test_secrets.py — the API key must be unreadable by the agent and unleakable
through any output, and no secret may ever ride along in the repo.

Three defences, each proven here:
  1. SHIELD  — the key store (settings.json / config dir) is a sensitive path,
     and the read tools (read_file / list_dir / find_file) REFUSE it. An
     autonomous agent must not be able to read the key it runs on.
  2. REDACT  — the one path a read-guard can't cover is the shell (`cat
     settings.json`, `env`). Command output and every log line are scrubbed of
     known key values and key-shaped tokens before the model/history/log see
     them.
  3. OFF-DISK — a key in <PROVIDER>_API_KEY is used at runtime and never written
     back to settings.json, so it can live entirely in the environment.

Plus a repo scan: no secret-shaped string is committed anywhere in the tree.

Run:  python3 tests/test_secrets.py
"""
from __future__ import annotations
import glob
import os
import re
import sys
import tempfile
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import basilisk_core as C  # noqa: E402

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


# ── 1. SHIELD: the key store is off-limits to the read tools ──────────
print("== shield: the agent cannot read its own key store ==")
_sj = str(C.SETTINGS_JSON)
_cfg = str(C.CONFIG_DIR)
ck("settings.json is a sensitive path", C.is_sensitive_path(_sj))
ck("the config dir is a sensitive path", C.is_sensitive_path(_cfg))
ck("the private data dir is a sensitive path", C.is_sensitive_path(str(C.DATA_DIR)))
ck("ssh material is still sensitive", C.is_sensitive_path("~/.ssh/id_rsa"))
ck("read_file REFUSES settings.json",
   C.tool_read_file(_sj).get("ok") is False
   and "refused" in C.tool_read_file(_sj).get("error", ""))
ck("list_dir REFUSES the config dir",
   C.tool_list_dir(_cfg).get("ok") is False)
ck("find_file REFUSES searching the config dir",
   C.tool_find_file("*.json", _cfg).get("ok") is False)
# …but ordinary files are untouched — the guard must not over-block.
ck("read_file still reads an ordinary file",
   C.tool_read_file("/etc/hostname").get("ok") is True)


# ── 2. REDACT: keys never survive into output or logs ─────────────────
print("\n== redact: no key survives into output ==")
C.register_secret("sk-liveSECRET0123456789abcdef")
ck("a registered key value is scrubbed",
   "sk-liveSECRET0123456789abcdef" not in
   C.redact_secrets("using sk-liveSECRET0123456789abcdef now")
   and "REDACTED" in C.redact_secrets("using sk-liveSECRET0123456789abcdef now"))
ck("an unknown sk- token is scrubbed by shape",
   "abcd" not in C.redact_secrets("key sk-abcdEFGH12345678 zzz").split("sk-")[-1][:4]
   or "REDACTED" in C.redact_secrets("key sk-abcdEFGH12345678 zzz"))
ck("a Bearer token is scrubbed",
   "REDACTED" in C.redact_secrets("Authorization: Bearer abcdEFGH12345678ijkl"))
ck("a json api_key value is scrubbed",
   "REDACTED" in C.redact_secrets('{"siliconflow_api_key": "myverysecretkey123456"}'))
# The SHELL path: command output is scrubbed before the model can see it.
_p_stub = types.SimpleNamespace(
    returncode=0,
    stdout='{"siliconflow_api_key": "sk-liveSECRET0123456789abcdef"}',
    stderr="")
_res = C._format_run_result("cat settings.json", _p_stub, False)
ck("command stdout is redacted (cat settings.json leaks nothing)",
   "sk-liveSECRET0123456789abcdef" not in _res.get("stdout", "")
   and "REDACTED" in _res.get("stdout", ""))
ck("redact_secrets is a no-op on clean text",
   C.redact_secrets("just a normal sentence") == "just a normal sentence")


# ── 3. OFF-DISK: an env key is used but never persisted ───────────────
print("\n== off-disk: env key never written to settings.json ==")
_saved_env = os.environ.get("SILICONFLOW_API_KEY")
_orig_path = C.SETTINGS_JSON
try:
    os.environ["SILICONFLOW_API_KEY"] = "env-only-key-abcdefghij"
    _s = C.load_settings()
    ck("env key is used at runtime",
       _s.get("siliconflow_api_key") == "env-only-key-abcdefghij")
    ck("env key is tracked as env-sourced",
       "siliconflow_api_key" in C._ENV_SOURCED_KEYS)
    # Save to a throwaway path and confirm the env key is NOT written.
    _tmp = os.path.join(tempfile.mkdtemp(), "settings.json")
    C.SETTINGS_JSON = type(C.SETTINGS_JSON)(_tmp)
    C.save_settings(_s)
    _on_disk = open(_tmp, encoding="utf-8").read()
    ck("env key is NOT written to settings.json",
       "env-only-key-abcdefghij" not in _on_disk, _on_disk[:80])
finally:
    C.SETTINGS_JSON = _orig_path
    if _saved_env is None:
        os.environ.pop("SILICONFLOW_API_KEY", None)
    else:
        os.environ["SILICONFLOW_API_KEY"] = _saved_env


# ── 4. REPO: no secret-shaped string is committed anywhere ────────────
print("\n== repo: nothing secret-shaped is committed ==")
_secret_shapes = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r'(?i)(api[_-]?key|token|secret|password)"?\s*[:=]\s*"[A-Za-z0-9]{20,}"'),
]
_allow = ("REDACTED", "your-", "xxxx", "example", "placeholder", "<", "sk-****")
_hits = []
for _pat in ("*.py", "*.sh", "*.json", "*.md", "*.txt", "*.cfg", "*.toml"):
    for _fp in glob.glob(os.path.join(_ROOT, "**", _pat), recursive=True):
        # Test files carry intentional FAKE secret-shaped fixtures — skip them;
        # the scan's job is real secrets in app / config / docs.
        if (os.sep + "tests" + os.sep) in _fp:
            continue
        try:
            _txt = open(_fp, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for _rx in _secret_shapes:
            for _m in _rx.finditer(_txt):
                _seg = _m.group(0)
                if not any(a in _seg for a in _allow):
                    _hits.append(f"{os.path.basename(_fp)}: {_seg[:40]}")
ck("no committed secret-shaped strings in the tree", not _hits, str(_hits[:3]))
ck(".gitignore excludes settings.json",
   "settings.json" in open(os.path.join(_ROOT, ".gitignore"),
                           encoding="utf-8").read())


print(f"\nsecrets: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
