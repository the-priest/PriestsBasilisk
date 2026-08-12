#!/usr/bin/env python3
"""
test_sidecar_store.py — memory recall, source verification, and the install
manifest.  Three surfaces that shipped with no tests at all.

WHY THIS FILE EXISTS
====================
Test coverage has been the best predictor of where bugs live in this codebase,
and these were the modules with none.  Each defect below is the same shape the
rest of the suite keeps finding: ONE rule, TWO consumers, only one of them
wired.

  1. THE INDEX COULD VETO THE WRITE.  memory.py keeps an FTS5 index for fast
     keyword recall, maintained by two SQL TRIGGERS that live in the database
     file, not in the process.  Recall degrades gracefully without FTS5 — the
     module's docstring says so, because stock NetHunter python may not have
     it.  Writes did not.  Open a memory.db created where fts5 exists on a box
     where it doesn't and every `INSERT INTO memories` raises through the still
     -present trigger; remember() propagated it and record_turn() swallowed it
     into a log file.  Memory silently stopped persisting while the toggle
     still read "on".

     Worse, it could not even be DETECTED: `CREATE VIRTUAL TABLE IF NOT EXISTS`
     short-circuits on an existing table without loading the module, so the
     probe in _init_schema never raised and left self._fts wrongly True.

  2. THE STEMMER EXCLUDED ITS OWN EXAMPLE.  _prefix_match's docstring offers
     'fix'/'fixed' as a case it handles.  Its floor was 4 characters, and
     _tokens() only ever emits 3+, so every 3-char token — fix, dir, log, run,
     sql — got no stemming at all.  _SYNONYM_GROUPS expands 'dir' into
     'directory' at the same time, so the two halves of recall disagreed about
     whether a 3-char token was a stem.

  3. A SCRATCH SET ESCAPED INTO THE RESULT.  verify() strips its scoring sets
     before returning, because a tool result gets serialised to the model and
     json.dumps() cannot encode a set.  The strip named "salient".  When the
     anchor channel was added for the CVE case it produced a SECOND set,
     "anchors", and the name-list did not know about it.  (verify.py is not
     currently wired into dispatch, so this is latent rather than live — but it
     ships, it installs, and it would crash the first turn it was used.)

  4. THE INSTALL MANIFEST HAD NO BACKSTOP.  install.sh lists the sidecar
     modules to fetch in `curl|bash` mode.  A module added to the repo but not
     to that list is simply absent on a remote install, and nothing anywhere
     said so.

Run:  python3 tests/test_sidecar_store.py
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from basilisk_ext.memory import MemoryStore, _prefix_match     # noqa: E402
from basilisk_ext.verify import verify                         # noqa: E402

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


_TMP = tempfile.mkdtemp(prefix="basilisk-store-test-")
_TRIGGERS = "SELECT name FROM sqlite_master WHERE type='trigger'"


def _db(name):
    return os.path.join(_TMP, name)


# ── 1. the index is never allowed to veto a write ─────────────────────
print("\n== a memory survives an unusable FTS index ==")

# Build a healthy store, then break the index the way an fts5-less interpreter
# sees it: the virtual table and both triggers still in the schema, the index
# itself unusable.  Dropping the fts5 shadow table reproduces that exactly.
m = MemoryStore(_db("broken.db"))
ck("healthy store uses FTS", m._fts is True)
ck("healthy store keeps its triggers",
   sorted(r[0] for r in m._db.execute(_TRIGGERS)) == ["mem_ad", "mem_ai"])
m.remember("row one, written while the index was healthy", kind="fact")
m._db.close()

_c = sqlite3.connect(_db("broken.db"))
_c.execute("DROP TABLE mem_fts_data")
_c.commit()
# Prove the hazard is real before proving the fix: a raw insert through the
# still-live trigger must fail.  If this ever stops raising, the test below
# is no longer testing anything.
_raised = ""
try:
    _c.execute("INSERT INTO memories(ts,kind,text,salience,source) "
               "VALUES(1,'fact','x',0.5,'t')")
except sqlite3.DatabaseError as e:
    _raised = str(e)
_c.close()
ck("the hazard is real: a raw write through the trigger fails",
   bool(_raised), f"raised={_raised!r}")

m2 = MemoryStore(_db("broken.db"))
ck("the store DETECTS the unusable index", m2._fts is False)
ck("and removes the triggers that would fail writes",
   [r[0] for r in m2._db.execute(_TRIGGERS)] == [],
   str([r[0] for r in m2._db.execute(_TRIGGERS)]))
_rid = m2.remember("row two, written after the index went bad", kind="fact")
ck("remember() returns a rowid", isinstance(_rid, int) and _rid > 0, str(_rid))
ck("the memory is actually stored",
   m2._db.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 2)
ck("recall still finds the new row",
   any("index went bad" in r["text"] for r in m2.recall("index went bad")))
ck("recall still finds the pre-existing row",
   any("healthy" in r["text"] for r in m2.recall("written healthy")))
ck("forget() still works", m2.forget("row two") == 1)
ck("stats() reports FTS off", m2.stats()["fts"] is False)

# The same must hold when the index breaks MID-LIFE, not just at open.
print("\n   -- and when the index breaks after the store is already open --")
m3 = MemoryStore(_db("midlife.db"))
m3.remember("before", kind="fact")
m3._db.execute("DROP TABLE mem_fts")
m3._db.commit()
ck("a write after a mid-life index failure still stores",
   isinstance(m3.remember("after the index broke", kind="fact"), int))
ck("both rows present",
   m3._db.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 2)
ck("forget() after a mid-life failure still works", m3.forget("before") == 1)

# The scope line: none of this may change the healthy path.
print("\n   -- the healthy path is untouched --")
m4 = MemoryStore(_db("healthy.db"))
ck("FTS still enabled", m4._fts is True)
ck("triggers still installed",
   sorted(r[0] for r in m4._db.execute(_TRIGGERS)) == ["mem_ad", "mem_ai"])
m4.remember("operator prefers nmap over masscan", kind="preference")
m4.remember("target scope is 10.0.0.0/24", kind="fact")
ck("recall finds by keyword",
   [r["text"] for r in m4.recall("nmap")] ==
   ["operator prefers nmap over masscan"])
ck("recall finds the other one",
   [r["text"] for r in m4.recall("scope")] == ["target scope is 10.0.0.0/24"])
ck("recall returns nothing for an unrelated query", m4.recall("sqli") == [])
ck("duplicates are not stored twice",
   m4.remember("operator prefers nmap over masscan", kind="preference") is None)
ck("too-short text is not stored", m4.remember("ab") is None)
ck("stats() reports FTS on", m4.stats()["fts"] is True)


# ── 2. the stemmer honours its own documented examples ────────────────
print("\n== _prefix_match stems 3-char tokens, which _tokens() emits ==")
for _q, _h in [("command", "commands"), ("scan", "scanning"),
               ("fix", "fixed"), ("dir", "directory"), ("log", "login"),
               ("run", "running"), ("sql", "sqlmap"), ("web", "website")]:
    ck(f"{_q} ~ {_h}", _prefix_match(_q, _h) is True)
# The counter-property: stemming must not collapse different words.
print("\n   -- and does not collapse distinct words --")
for _q, _h in [("web", "went"), ("cat", "dog"), ("sql", "xss"),
               ("fix", "fox"), ("scan", "scope"), ("dir", "disk"),
               ("nmap", "nuclei")]:
    ck(f"{_q} !~ {_h}", _prefix_match(_q, _h) is False)
ck("stemming is symmetric",
   all(_prefix_match(a, b) == _prefix_match(b, a)
       for a, b in [("fix", "fixed"), ("dir", "directory"), ("web", "went")]))


# ── 3. a verify() result is always serialisable ───────────────────────
print("\n== verify() returns something json.dumps can encode ==")


def _search(q, max_results=10):
    return {"ok": True, "instant_answer": "", "results": [
        {"url": "https://nvd.nist.gov/vuln/detail/CVE-2024-6387",
         "title": "NVD", "snippet": "regreSSHion"},
        {"url": "https://www.qualys.com/regresshion",
         "title": "Qualys", "snippet": "CVE-2024-6387"},
        {"url": "https://theonion.com/x", "title": "Onion", "snippet": "satire"},
    ]}


def _read(url, max_chars=4000):
    return {"ok": True, "source": "direct",
            "text": "CVE-2024-6387 affects OpenSSH 8.5p1 through 9.7p1. CVSS 8.1."}


_r = verify("regreSSHion", _search, _read)
ck("verify succeeded", _r["ok"] is True)
try:
    json.dumps(_r)
    _ser = True
except TypeError as _e:
    _ser = False
ck("the whole result is JSON-serialisable", _ser,
   "a tool result gets handed to the model; a set crashes that")
ck("no set survives on any source",
   not any(isinstance(v, (set, frozenset))
           for s in _r["sources"] for v in s.values()))
ck("the useful fields are still there",
   {"url", "domain", "tier", "excerpt"} <= set(_r["sources"][0].keys()),
   str(sorted(_r["sources"][0].keys())))
ck("satire is flagged", "theonion.com" in _r["satire"])
ck("the primary source is recognised", _r["has_primary_source"] is True)

# Every early return must serialise too — they are results as much as the
# happy path is.
print("\n   -- including every failure path --")
for _label, _res in [
    ("empty query", verify("", _search, _read)),
    ("search raises", verify(
        "q", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")), _read)),
    ("search not ok", verify("q", lambda *a, **k: {"ok": False, "error": "no"}, _read)),
    ("no results", verify("q", lambda *a, **k: {"ok": True, "results": []}, _read)),
    ("read raises", verify(
        "q", _search, lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))),
]:
    try:
        json.dumps(_res)
        _ok = True
    except TypeError:
        _ok = False
    ck(f"serialisable: {_label}", _ok)


# ── 4. the install manifest matches the repo ──────────────────────────
print("\n== install.sh ships every module that exists ==")
_sh = open(os.path.join(_ROOT, "install.sh"), encoding="utf-8").read()


def _arr(name):
    m = re.search(name + r"=\((.*?)\)", _sh, re.S)
    return set(re.findall(r"[\w./-]+\.py", m.group(1))) if m else set()


_ext_listed = _arr("EXT_FILES")
_req_listed = _arr("REQUIRED_FILES")
_opt_listed = _arr("OPTIONAL_FILES")
_ext_real = {f for f in os.listdir(os.path.join(_ROOT, "basilisk_ext"))
             if f.endswith(".py")}
_top_real = {f for f in os.listdir(_ROOT)
             if f.endswith(".py") and f.startswith("basilisk")}

ck("EXT_FILES was parsed", bool(_ext_listed))
ck("REQUIRED_FILES was parsed", bool(_req_listed))
ck("every basilisk_ext module is in EXT_FILES",
   not (_ext_real - _ext_listed),
   f"missing from install.sh: {sorted(_ext_real - _ext_listed)}")
ck("EXT_FILES lists nothing that does not exist",
   not (_ext_listed - _ext_real),
   f"listed but absent: {sorted(_ext_listed - _ext_real)}")
ck("every top-level module is required or explicitly optional",
   not (_top_real - _req_listed - _opt_listed),
   f"unlisted: {sorted(_top_real - _req_listed - _opt_listed)}")
ck("REQUIRED_FILES names nothing that does not exist",
   not (_req_listed - _top_real),
   f"listed but absent: {sorted(_req_listed - _top_real)}")

print(f"\nsidecar_store: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
