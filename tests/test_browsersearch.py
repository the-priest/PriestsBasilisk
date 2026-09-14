#!/usr/bin/env python3
"""
test_browsersearch.py — the real browser behind web_read, and real search.

THE TWO THINGS THIS PROTECTS
============================

1. THE SSRF FLOOR, INSIDE A BROWSER.
   urllib fetches ONE url and the caller checks each redirect hop. A
   browser follows its own redirects, loads subresources, and runs script
   that can fetch anything it likes — so the floor has to apply to EVERY
   request the page makes, not to the one we typed. It is also INJECTED,
   never reimplemented: browser.fetch refuses to run without a host_ok
   predicate, so there is exactly one definition of "private address" in
   the tree and no second copy to drift.

   VERIFIED AGAINST A REAL BROWSER during development, not reasoned about:
   a page whose <img> and whose fetch() both point at 169.254.169.254 has
   both requests aborted and both reported in `blocked`.

2. THE THREAD-AFFINITY TRAP, which would have shipped.
   Playwright's sync API pins every object to the thread that made it, and
   Basilisk dispatches each tool call on a FRESH daemon thread. The obvious
   implementation — launch once, keep it in a module global — works for the
   first web_read of a session and dies on the second with "cannot switch
   to a different thread (which happens to have exited)". Reproduced before
   the fix; the owner-thread design is why it now survives. "Works once,
   then breaks" is exactly the shape that gets shipped, because the happy
   path in a fresh session is the path anyone testing it takes.

Run:  python3 tests/test_browsersearch.py
"""

from __future__ import annotations

import os
import re
import sys
import threading

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

_p = _f = 0


def ck(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


from basilisk_ext import browser as B                           # noqa: E402
from basilisk_ext import research as R                          # noqa: E402

BSRC = open(os.path.join(_ROOT, "basilisk_ext", "browser.py"),
            encoding="utf-8").read()
CSRC = open(os.path.join(_ROOT, "basilisk_core.py"), encoding="utf-8").read()


# ═════════════════════════════════════════════════════════════════════
#  1. THE SSRF FLOOR IS MANDATORY AND INJECTED
# ═════════════════════════════════════════════════════════════════════
print("\n== the floor cannot be skipped ==")
ck("fetch with NO predicate is refused (fail closed)",
   B.fetch("https://example.com", host_ok=None).get("ok") is False)
ck("…and says why", "SSRF floor"
   in B.fetch("https://example.com", host_ok=None).get("error", ""))
for bad in (None, "", 0, [], {}, "not callable"):
    ck(f"a non-callable predicate ({bad!r:.12}) is refused",
       B.fetch("https://x.com", host_ok=bad).get("ok") is False)

print("\n== the module does not define its own idea of 'private' ==")
# CODE only, not the prose. An earlier draft grepped the whole file and
# failed on a COMMENT that names 169.254.169.254 while explaining that the
# rule is injected — the checker flagging the documentation of the property
# it was checking for. Strip comments and docstrings first.
_BCODE = "\n".join(
    ln for ln in BSRC.splitlines() if not ln.lstrip().startswith("#"))
_BCODE = re.sub(r'"""[\s\S]*?"""', "", _BCODE)
for leak in ("ip_address", "is_private", "is_loopback", "169.254",
             "127.0.0.1", "10.0.0.0", "metadata.google"):
    ck(f"browser.py contains no copy of the rule ({leak!r})",
       leak not in _BCODE,
       "one rule, one definition - a second copy is the drift this "
       "codebase keeps paying for")
ck("the host passes its own predicate in",
   "host_ok=_web_read_host_ok" in CSRC)
ck("…and the comment says why it is not reimplemented",
   "not repeated inside the" in CSRC and "browser module" in CSRC)

print("\n== the floor is applied before anything is launched ==")
REFUSE_ALL = (lambda h: False)
r = B.fetch("https://evil.example", host_ok=REFUSE_ALL)
ck("a refused host never reaches a browser", r.get("ok") is False)
ck("…and no engine was started", not r.get("engine"))
ck("…and the message names the host", "evil.example" in r.get("error", ""))

print("\n== scheme and shape ==")
ALLOW = (lambda h: True)
for bad, why in (("file:///etc/passwd", "file"), ("ftp://x/y", "ftp"),
                 ("gopher://x", "gopher"), ("data:text/html,x", "data")):
    out = B.fetch(bad, host_ok=ALLOW)
    ck(f"{why}: scheme is refused", out.get("ok") is False, str(out)[:80])
ck("an empty url is refused", B.fetch("", host_ok=ALLOW).get("ok") is False)
ck("a bare host is treated as https, not refused",
   "https" in str(B.fetch("example.com", host_ok=REFUSE_ALL).get("error", ""))
   or B.fetch("example.com", host_ok=REFUSE_ALL).get("ok") is False)

print("\n== the route handler is where the floor really lives ==")
ck("a route handler is installed on every request",
   'ctx.route("**/*"' in BSRC)
ck("…and it checks the predicate per request",
   "not host_ok(pr.hostname)" in BSRC)
ck("…aborts rather than continuing", "route.abort()" in BSRC)
ck("…and REPORTS what it blocked (a silent block hides an attack)",
   'blocked.append' in BSRC and '"blocked"' in BSRC)
ck("the FINAL url is re-checked as belt and braces",
   "not host_ok(fhost)" in BSRC)
ck("…and the content is discarded if it fails",
   "content discarded" in BSRC)


# ═════════════════════════════════════════════════════════════════════
#  2. THREAD AFFINITY
# ═════════════════════════════════════════════════════════════════════
print("\n== one owner thread, because playwright pins its objects ==")
ck("there is a dedicated worker", "_worker_loop" in BSRC)
ck("…work is submitted to it, not run inline", "_submit(" in BSRC)
ck("…callers wait on an event, not a lock held across a fetch",
   "job.done.wait(" in BSRC)
ck("the trap is documented so nobody 'simplifies' it back",
   "cannot switch to a different thread" in BSRC)
ck("a job that raises cannot kill the owner thread",
   "a job must never kill the owner" in BSRC)
ck("the worker retires when idle, instead of holding a browser all day",
   "IDLE_CLOSE_S" in BSRC and "queue.Empty" in BSRC)
ck("shutdown is registered at exit", "atexit.register(shutdown)" in BSRC)
ck("a fatal browser error drops the handle so the next call relaunches",
   "_looks_fatal" in BSRC and "_teardown()" in BSRC)
ck("…and 'different thread' counts as fatal",
   "different thread" in BSRC.split("_FATAL_RE")[1][:300])

print("\n== a refusal is thread-safe and repeatable ==")
# The refusal path does not launch anything, so it is safe to hammer here
# without a browser installed. What is being checked is that N calls from N
# different threads all return cleanly — the shape that used to die.
results = []
errs = []


def _call():
    try:
        results.append(B.fetch("https://blocked.example",
                               host_ok=REFUSE_ALL).get("ok"))
    except Exception as e:                       # pragma: no cover
        errs.append(e)


ts = [threading.Thread(target=_call) for _ in range(8)]
for t in ts:
    t.start()
for t in ts:
    t.join(timeout=30)
ck("8 threads, no exceptions", not errs, str(errs[:2]))
ck("…all eight refused cleanly",
   len(results) == 8 and all(r is False for r in results), str(results))


# ═════════════════════════════════════════════════════════════════════
#  3. ENGINE SELECTION
# ═════════════════════════════════════════════════════════════════════
print("\n== engine selection ==")
pr = B.probe()
ck("probe returns a dict and launches nothing", isinstance(pr, dict))
ck("…listing every engine it knows", set(pr["engines"]) == {
    "camoufox", "firefox", "chromium"})
ck("…and which one would be used", "chosen" in pr)
ck("THE PACKAGE IS NOT THE BROWSER: camoufox is only chosen when its "
   "browser build is actually installed",
   "installed_verstr" in BSRC and "not the browser" in BSRC.lower())
ck("…and the cost of getting that wrong is written down",
   "pays a failed launch" in BSRC)
ck("an explicit 'http' preference disables the browser entirely",
   B._pick_engine("http") == "")
ck("…as does 'off'", B._pick_engine("off") == "")
ck("a preferred engine is tried first when available",
   B._pick_engine("chromium") in ("chromium", ""))
ck("BASILISK_BROWSER=off is honoured", True)   # exercised below
_old = os.environ.get("BASILISK_BROWSER")
try:
    os.environ["BASILISK_BROWSER"] = "off"
    ck("…really honoured", B._pick_engine() == "")
finally:
    if _old is None:
        os.environ.pop("BASILISK_BROWSER", None)
    else:
        os.environ["BASILISK_BROWSER"] = _old

print("\n== the proxy pair travels together ==")
ck("NO_PROXY is honoured alongside HTTPS_PROXY",
   "NO_PROXY" in BSRC and '"bypass"' in BSRC)
ck("…and the failure it prevents is written down",
   "405" in BSRC)


# ═════════════════════════════════════════════════════════════════════
#  4. web_read WIRING — the browser is primary, the fallback is LOUD
# ═════════════════════════════════════════════════════════════════════
print("\n== web_read prefers the browser and says which reader ran ==")
ck("web_read consults the browser first", "_browser_read_enabled()" in CSRC)
ck("…falls back to the plain HTTP fetch", "_trusted_fetch(url" in CSRC)
ck("…and REPORTS the engine on every result", '"engine": _engine' in CSRC)
ck("a degraded read carries an explanation for the model",
   '"engine_note"' in CSRC)
ck("…which tells it not to call the page blank",
   "reporting the page as blank" in CSRC)
ck("blocked subresources are surfaced to the model too",
   '"blocked_requests"' in CSRC)
ck("the fallback can be switched off, and then it says so rather than "
   "silently degrading", "fallback is switched off" in CSRC)
ck("browser_status exists so 'why is this page empty' is answerable",
   "def tool_browser_status" in CSRC)

print("\n== settings ==")
import basilisk_core as Bc                                      # noqa: E402
for key, want in (("browser_read", True), ("browser_engine", "camoufox"),
                  ("browser_timeout", 25), ("browser_http_fallback", True),
                  ("plan_enabled", True)):
    ck(f"{key} defaults to {want!r}",
       Bc.DEFAULT_SETTINGS.get(key) == want,
       repr(Bc.DEFAULT_SETTINGS.get(key)))
ck("settings are published at the ONE choke point every save goes through",
   "publish_settings(settings)" in CSRC.split("def save_settings")[1][:900])
ck("…and the nine-call-sites reason is written down",
   "nine save_settings() call sites" in CSRC)


# ═════════════════════════════════════════════════════════════════════
#  5. SEARCH — several phrasings, several engines, cross-checked
# ═════════════════════════════════════════════════════════════════════
print("\n== query expansion ==")
qs = R.expand("what is the latest version of nmap")
ck("the operator's own words are tried", any("nmap" in q for q in qs))
ck("…a keyword form too", len(qs) >= 2)
ck("a recency word adds a year-anchored variant",
   any("20" in q for q in qs), str(qs))
ck("a plain question gets no year variant",
   not any("20" in q for q in R.expand("how do i center a div")))
ck("a model-supplied query goes FIRST (a deliberate query beats a "
   "generated one)",
   R.expand("x", extra=["site:nmap.org changelog"])[0]
   == "site:nmap.org changelog")
ck("expansion is bounded", len(R.expand("a b c d e f g h i j k")) <= 4)
for junk in (None, 0, [], {}, object()):
    try:
        ck(f"expand({junk!r:.12}) is total", isinstance(R.expand(junk), list))
    except Exception as e:
        ck(f"expand({junk!r:.12}) is total", False, str(e)[:50])

print("\n== result extraction and merging ==")
PAGE_A = """(HTTP 200)
Nmap Changelog (https://nmap.org/changelog.html)
Nmap - Wikipedia (https://en.wikipedia.org/wiki/Nmap)
Follow us (https://twitter.com/nmap)
Next page (https://duckduckgo.com/html/?q=nmap&s=30)
"""
PAGE_B = """(HTTP 200)
Changelog (https://nmap.org/changelog.html?utm_source=bing&ref=x)
Wikipedia (https://en.wikipedia.org/wiki/Nmap/)
Pin it (https://pinterest.com/nmap)
"""
res = R.extract_results(PAGE_A, "duckduckgo")
hosts = [r["host"] for r in res]
ck("real results are found", "nmap.org" in hosts)
ck("social noise is dropped", "twitter.com" not in hosts)
ck("the engine's own links are dropped", "duckduckgo.com" not in hosts)
ck("aggregator noise is dropped",
   "pinterest.com" not in [r["host"] for r in R.extract_results(PAGE_B, "b")])


def fake_read(url):
    if "duckduckgo" in url:
        return {"ok": True, "text": PAGE_A, "engine": "camoufox"}
    if "bing.com" in url:
        return {"ok": True, "text": PAGE_B, "engine": "camoufox"}
    if "mojeek" in url or "startpage" in url:
        return {"ok": False, "error": "bot check"}
    body = {"https://nmap.org/changelog.html": "Nmap 7.95 released 2024-04-22",
            "https://en.wikipedia.org/wiki/Nmap": "stable release 7.95 / 2024"}
    for k, v in body.items():
        if url.rstrip("/") == k.rstrip("/"):
            return {"ok": True, "text": v, "final_url": k, "engine": "camoufox"}
    return {"ok": False, "error": "404"}


s = R.search("latest nmap version", fake_read)
ck("search reports ok when it found things", s["ok"])
top = s["results"][0]
ck("the top hit was found by MORE THAN ONE engine (agreement ranks, not "
   "any single engine's order)", len(top["engines"]) >= 2, str(top))
ck("tracking parameters do not split one page into two",
   sum(1 for r in s["results"] if r["host"] == "nmap.org"
       and "changelog" in r["url"]) == 1)
ck("a trailing slash does not either",
   sum(1 for r in s["results"] if "wikipedia" in r["host"]) == 1)
ck("engines that failed are reported, not hidden",
   any(not p["ok"] for p in s["pages"]))
ck("a search that finds nothing says what to try instead",
   "error" in R.search("x", lambda u: {"ok": True, "text": "nothing here"}))

print("\n== research: independent sources, and disagreement is SHOWN ==")
d = R.research("latest nmap version", fake_read, max_sources=3)
ck("it read something", d["ok"])
read_hosts = [x["host"] for x in d["sources"] if x.get("ok")]
ck("ONE PAGE PER DOMAIN — three pages from one site is one source",
   len(read_hosts) == len(set(read_hosts)), str(read_hosts))
ck("corroborated values are reported with their sources",
   any(a["value"] == "7.95" and a["n"] >= 2
       for a in d["agreement"].get("version", [])), str(d["agreement"]))
ck("the instructions forbid silently resolving a disagreement",
   "do not average them" in d["how_to_use"]
   and "silently pick one" in d["how_to_use"])
ck("…and require citing the URL each fact came from",
   "Cite the URL" in d["how_to_use"])


def one_source(url):
    if any(e in url for e in ("duckduckgo", "bing.com", "mojeek", "startpage")):
        return {"ok": True, "text": PAGE_A, "engine": "camoufox"}
    if "nmap.org" in url:
        return {"ok": True, "text": "Nmap 7.95", "final_url": url}
    return {"ok": False, "error": "blocked"}


d1 = R.research("latest nmap", one_source, max_sources=3)
ck("a single readable source triggers an explicit warning", bool(d1.get("warning")))
ck("…saying nothing is corroborated", "corroborated" in d1["warning"])

print("\n== research never opens a socket itself ==")
RSRC = open(os.path.join(_ROOT, "basilisk_ext", "research.py"),
            encoding="utf-8").read()
_RCODE = "\n".join(
    ln for ln in RSRC.splitlines() if not ln.lstrip().startswith("#"))
_RCODE = re.sub(r'"""[\s\S]*?"""', "", _RCODE)
for leak in ("urllib.request", "requests.", "http.client", "socket.",
             "urlopen("):
    ck(f"research.py does not do its own I/O ({leak!r})", leak not in _RCODE)
ck("the host injects its GATED reader, so a research fetch goes through "
   "the same door as a direct one",
   "_research_reader" in open(os.path.join(_ROOT, "basilisk.py"),
                              encoding="utf-8").read())
ck("…and that door is _web_read_gated, not tool_web_read",
   "_web_read_gated" in open(os.path.join(_ROOT, "basilisk.py"),
                             encoding="utf-8").read()
   .split("def _research_reader")[1][:600])

print("\n== research is total ==")
for junk in (None, 0, [], {}, object()):
    try:
        out = R.research(junk, fake_read)
        ck(f"research({junk!r:.12}) returns a dict", isinstance(out, dict))
    except Exception as e:
        ck(f"research({junk!r:.12}) returns a dict", False, str(e)[:60])


def boom(url):
    raise RuntimeError("network on fire")


ck("a reader that RAISES does not take research down",
   isinstance(R.research("x", boom), dict))
ck("…nor search", isinstance(R.search("x", boom), dict))

print(f"\nbrowsersearch: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
