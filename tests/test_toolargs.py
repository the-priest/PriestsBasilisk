#!/usr/bin/env python3
"""
test_toolargs.py — an argument the tool cannot see must never be silently
dropped.

FROM THE OPERATOR'S OWN TOOL AUDIT (2026-08-11)
===============================================
He ran Basilisk against its own tool surface and logged, among others:

    copy_path path=/etc/hostname   ->  ok:false, "source not found" with an
                                       EMPTY path string
    scan_net  target=127.0.0.1     ->  scanned 100.85.0.1/24 instead — the
                                       Proton VPN subnet — and reported success
    cve_lookup CVE-2024-3094       ->  ok:false, "no product"

Three different tools, one bug. Every handler in the dispatch table reads its
arguments with `a.get("src")` / `a.get("cidr")` / positional `product`, so a
key the tool does not know is INVISIBLE and the call proceeds on defaults.

The failure modes get worse down that list:
  * copy_path reported "source not found", which reads like the FILE is
    missing rather than like the argument never arrived — so the model
    "corrects" the wrong thing;
  * cve_lookup reported "no product", which reads like NVD had no data;
  * scan_net ran an ACTIVE SCAN of a network nobody named. On a pentest tool
    a silent default is not a no-op, it is unrequested traffic aimed at a
    third party.

THE FIX
=======
One normalisation step at the single dispatch choke point:
  * common synonyms are mapped onto the real key, but ONLY when the real key
    is absent, so a correct call is never rewritten; and
  * a call whose keys are ALL unknown is refused with the accepted names fed
    back, so the model re-issues it — the same "an unreadable call costs a
    round trip, never a wrong action" rule the tool-dialect handling uses.

The accepted names are parsed from the PERSONA SPECS — the very text the model
is shown — so the validator and the contract cannot drift apart. A
hand-maintained second list is exactly the failure this codebase keeps hitting.

Run:  python3 tests/test_toolargs.py
"""

from __future__ import annotations

import os
import sys
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)


class _Meta(type):
    def __getattr__(cls, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return _Obj


class _Obj(metaclass=_Meta):
    def __init__(self, *a, **k):
        pass

    def __call__(self, *a, **k):
        return _Obj()

    def __getattr__(self, n):
        return _Obj()


class _Mod(types.ModuleType):
    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return _Obj

    def require_version(self, *a, **k):
        pass


for _m in ("gi", "gi.repository", "gi.repository.Gtk", "gi.repository.Adw",
           "gi.repository.GLib", "gi.repository.Gio", "gi.repository.Gdk",
           "gi.repository.GdkPixbuf", "gi.repository.Pango",
           "gi.repository.GObject", "gi.repository.GtkSource",
           "gi.repository.Vte", "gi.repository.Soup"):
    sys.modules[_m] = _Mod(_m)
sys.modules["gi"].require_version = lambda *a, **k: None

import basilisk as Bk                                          # noqa: E402

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


def norm(tool, args):
    return Bk._normalise_tool_args(tool, args)


# ── 1. the contract is readable, and it is the model's contract ──────
print("\n== accepted names come from the persona spec ==")
_spec = Bk._spec_arg_names()
ck("specs parsed from basilisk_persona", len(_spec) > 100, str(len(_spec)))
ck("copy_path declares src/dst", _spec.get("copy_path") == {"src", "dst"},
   str(_spec.get("copy_path")))
ck("read_file declares path", "path" in _spec.get("read_file", set()))
ck("run declares command", "command" in _spec.get("run", set()))
ck("cve_lookup declares product",
   "product" in _spec.get("cve_lookup", set()), str(_spec.get("cve_lookup")))


# ── 2. the three calls from his audit ────────────────────────────────
print("\n== the exact failures from the tool audit ==")
_a, _e = norm("copy_path", {"path": "/etc/hostname"})
ck("copy_path path= now reaches src", _a.get("src") == "/etc/hostname", str(_a))
ck("…and is not refused", _e == "")

_a, _e = norm("scan_net", {"target": "127.0.0.1"})
ck("scan_net target= now reaches cidr", _a.get("cidr") == "127.0.0.1", str(_a))
ck("…so it can no longer sweep a network nobody named", _e == "")

_a, _e = norm("cve_lookup", {"cve": "CVE-2024-3094"})
ck("cve_lookup cve= now reaches product",
   _a.get("product") == "CVE-2024-3094", str(_a))


# ── 3. more synonyms a model reaches for ─────────────────────────────
print("\n== the common slips just work ==")
for _t, _in, _key, _val in [
    ("copy_path",   {"source": "/a", "to": "/b"},        "src", "/a"),
    ("move_path",   {"from": "/a", "destination": "/b"}, "dst", "/b"),
    ("read_file",   {"file": "/etc/hosts"},              "path", "/etc/hosts"),
    ("delete_path", {"filename": "/tmp/x"},              "path", "/tmp/x"),
    ("make_dir",    {"folder": "/tmp/d"},                "path", "/tmp/d"),
    ("web_read",    {"link": "https://x.com"},           "url", "https://x.com"),
    ("find_file",   {"query": "*.conf"},                 "pattern", "*.conf"),
    ("run",         {"cmd": "id"},                       "command", "id"),
    ("scan_net",    {"subnet": "10.0.0.0/24"},           "cidr", "10.0.0.0/24"),
]:
    _a, _e = norm(_t, _in)
    ck(f"{_t}: {list(_in)[0]} -> {_key}", _a.get(_key) == _val and not _e, str(_a))


# ── 4. a CORRECT call is never touched ───────────────────────────────
# This is the half that makes the fix safe to ship: aliasing only fills a key
# that is absent, so nothing that already worked can change.
print("\n== correct calls pass through byte-identical ==")
for _t, _in in [
    ("copy_path", {"src": "/a", "dst": "/b"}),
    ("move_path", {"src": "/a", "dst": "/b"}),
    ("read_file", {"path": "/etc/hosts"}),
    ("run", {"command": "nmap -sV 10.0.0.5", "reason": "service scan"}),
    ("web_read", {"url": "https://example.com"}),
    ("cve_lookup", {"product": "OpenSSH", "version": "9.6"}),
    ("scan_net", {}),
    ("scan_net", {"cidr": "10.0.0.0/24"}),
]:
    _a, _e = norm(_t, _in)
    ck(f"unchanged: {_t}({_in})", _a == _in and _e == "", f"got {_a} err={_e!r}")

# …and an alias must NOT override a real key that is already present.
_a, _e = norm("copy_path", {"src": "/real", "path": "/decoy", "dst": "/b"})
ck("a present real key wins over its alias", _a.get("src") == "/real", str(_a))


# ── 5. an all-unknown call is REFUSED, with the names fed back ───────
print("\n== a call with no usable argument is refused, not guessed ==")
for _t, _in in [("copy_path", {"foo": "bar"}),
                ("read_file", {"nonsense": 1}),
                ("web_read", {"wrong": "x"}),
                ("run", {"bogus": "id"})]:
    _a, _e = norm(_t, _in)
    ck(f"{_t}({_in}) is refused", bool(_e), str(_a))
    ck(f"…and names the accepted arguments",
       all(k in _e for k in sorted(_spec.get(_t, set()))), _e[:100])
    ck(f"…and says it would otherwise have run on none of them",
       "none of them" in _e, _e[:80])

# One right key is enough — a partially-odd call still runs, so this can never
# block work that used to succeed.
_a, _e = norm("run", {"command": "id", "extra_nonsense": 1})
ck("one correct key is enough to run", _e == "" and _a.get("command") == "id")


# ── 6. fail-safe ─────────────────────────────────────────────────────
print("\n== nothing here may raise or block the unknown ==")
for _t, _in in [("no_such_tool", {"x": 1}), ("run", None), ("run", "notadict"),
                ("run", {}), ("", {}), ("copy_path", []),
                ("copy_path", {"src": None}), ("scan_net", {"cidr": ""})]:
    try:
        _a, _e = norm(_t, _in)
        ck(f"safe: {_t}({_in!r})", isinstance(_a, dict) and isinstance(_e, str),
           f"{_a!r} {_e!r}")
    except Exception as _ex:
        ck(f"safe: {_t}({_in!r})", False, f"{type(_ex).__name__}: {_ex}")

ck("a tool with no declared contract is never refused",
   norm("no_such_tool", {"anything": 1})[1] == "")

# The dispatcher must actually USE it.
_src = open(os.path.join(_ROOT, "basilisk.py"), encoding="utf-8").read()
ck("the dispatcher normalises before calling the handler",
   "_normalise_tool_args(call.name, call.args)" in _src)
ck("…and refuses rather than running on a bad arg set",
   'self._feed_tool_result(f"NOT RUN — {_argerr}")' in _src)

print(f"\ntoolargs: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
