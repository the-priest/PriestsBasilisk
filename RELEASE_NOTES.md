# v1.1.4.0

**The deep-debug pass. Four real bugs, one of them serious.**

> NOTE ON THE THEME: nothing in 1.1.3.0 or this release touches the stylesheet
> or any asset. 1.1.3.0 differed from 1.1.2.0 in exactly five files
> (`basilisk.py`, `basilisk_core.py`, and three markdown docs) — the emblem PNG
> is byte-identical across all three. If a build looks like the old red theme,
> it is an old copy being launched, not a revert.

## 1. The repeat guard was blocking the verification loop

The worst one, and it had been sitting there in plain sight.

`workspace_verify {}` takes no arguments, so its action label is the constant
string `"workspace_verify"`. The repeat guard refuses a **third** identical
action, and the action log is only reset when a *mission* latches — which never
happens in leashed work mode.

So in any repo job, the third `workspace_verify` was refused, and every one
after it, for the life of the chat. Meanwhile the persona says of that exact
tool, in the model's own instructions:

```
<tool name="workspace_verify">{}</tool>  // ... Call after every edit.
//   6. workspace_verify. Every time.
```

The instructions mandated a behaviour the guard forbade. Same for
`run: pytest -q`, and for `oracle_status {}` ("Consult it every planning turn"),
and for every other no-argument status read. **Any repo job over two edits was
flying blind** — and it silently caused exactly the unverified "done" the new
verification gate was built to stop.

The guard's reasoning was right about a *scanner* and wrong about a *verifier*.
nmap against the same host three times tells you nothing new; `workspace_verify`
after a third edit tells you something completely new, because the thing it
measures changed underneath it. It compared labels, so it could not tell them
apart.

It now counts a **window**: runs of an action since the last *different*
state-changing action. An action never resets its own window, which is what
keeps `pytest, pytest, pytest` blocked while `edit, pytest, edit, pytest` runs
forever.

## 2. A truncated write silently deleted code and reported success

Reproduced against the live workspace: a 59-line file written as three lines
ending `# ... rest unchanged ...` returned `ok: True`, and the functions below
the marker were gone.

Work mode warns about this twice, in capitals. That is advice. It is a gate
now, and it needs all three conditions — the file existed, the content carries
a placeholder **line**, and the file shrank below 60% of its lines. Measured
before shipping: 14 truncation shapes caught, **zero** false positives across
every source and markdown file in the repo rewritten byte-for-byte, across
honest 80% deletions, across prose that discusses patching, and across `.pyi`
stubs full of real `...`.

## 3. A replayed feed opened onto nothing

Mine, from the chip rewrite in 1.1.2.0. The step list floats from the window
overlay, but a feed replayed into the *transcript* built a panel nothing ever
parented. Verified under real GTK: parent `None`, mapped `False`. Clicking a
replayed feed set the chevron and put nothing on screen — a control that lies
about having opened. The widget now knows which of its two placements it is in.

## 4. The used-tool record saw only one of two execution paths

`_tools_used_this_request` is what the promise gate and the verification gate
both read. It was written at the single-call path only, under a comment saying
it was recorded "at the one place that dispatches". There are two. That sentence
has now been wrong three times in that method's neighbourhood. No gate set
intersects the batchable list today, so nothing was misreported — this closes
the seam before a tool added to both lists blinds a gate.

## Also

- New `tests/test_repeatwindow.py` (43) and `tests/test_truncwrite.py` (40).
- 4,582 assertions across 75 stdlib-only suites, zero red.
