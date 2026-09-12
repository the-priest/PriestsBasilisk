# v1.1.3.0

**"Not done until verified" stops being a request and becomes a gate.**

This release applies Anthropic's published agent-engineering guidance to the
half of Basilisk that needed it most: knowing when the work is actually
finished.

## The verification gate

Work mode already tells the model, at length, to run something that proves its
change — *"VERIFY, DON'T ASSUME"*, *"ITERATE UNTIL IT ACTUALLY PASSES"*. That is
advice, and advice is what a model drops on step forty of a long job.
Anthropic's own write-up names both the failure and the split:

> Claude stops when the work looks done. Without a check it can run, "looks
> done" is the only signal available, and you become the verification loop.

…and separates the mechanisms: a prompt instruction is advisory, a Stop hook is
deterministic and *"blocks the turn from ending until it passes."*

Basilisk already **had** the check. `workspace_verify` re-runs the repo's tests
and classifies the result against a baseline, so it reports what you fixed *and
what you broke*. The gap was never the check — it was that nothing made the
turn go through it.

So there is a gate now, built on the same architecture as the existing promise
gate and inheriting the property that made that one hold up: **it does not read
the reply.** Two facts decide it — files were written this request, and nothing
was ever run to check them. If both hold when the turn is about to end,
Basilisk runs the check itself and hands the model the result, with regressions
named as its own to fix. Once per request, never a loop.

## Budget ground truth

The model was told to iterate until green with a large tool budget, and never
told where in that budget it was — so it either wrapped up far too early or
walked into the cap mid-edit. Anthropic's multi-agent write-up puts explicit
effort rules in the prompt for exactly this reason; the agent-loop guidance is
that an agent should *"gain 'ground truth' from the environment at each step."*

Work-mode continuations now carry the real step count in three bands: plenty
left (**don't** rush or hand back a partial fix), enough to finish and verify
(converge), and nearly out (land what you have).

## Error messages are prompts

> …prompt-engineer your error responses to clearly communicate specific and
> actionable improvements.

Audited the coding surface. Two real offenders fixed:

- `workspace_verify` on a repo with no suite said *"no test command known"* —
  what failed, nothing about what to do. It now names the repair, names the
  fallback when there is genuinely no suite, and forbids reporting the change
  as verified anyway.
- `"no workspace open — import a repo zip first"` sent a model holding a
  *directory* looking for a way to zip it. `workspace_import` has taken either
  for several releases; the error string had never been updated.
- `workspace_verify` with no repo open reported a missing **test command**,
  which sent the model hunting for a test runner when the real problem was that
  there was no repo.

## Also

- New `tests/test_verifygate.py` (52 assertions), including the counter-property
  that a turn which *did* verify is never gated — a gate that fires on correct
  behaviour is a gate that gets switched off.
- 4,491 assertions across 73 stdlib-only suites, zero red.
