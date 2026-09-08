# v1.1.0.0

**Basilisk is a local AI coding assistant with an armable pentest mode.** This
release makes the leashed half the product it always was, and ships native
packages for Kali and CachyOS.

## What's new

- **Work mode.** A leashed turn is classified as a question or a job. A job
  gets told to act with tools, write complete files, run something that proves
  it, and iterate until the tests pass — with a tool budget sized for a repo.
- **The promise gate.** If your question needed a live source and no web tool
  ran all turn, the app runs the search itself. It never reads the reply, so no
  phrasing of "okay, fetching that now" can end a turn with nothing fetched.
- **Big writes work.** `max_tokens` shipped at 2048; a 400-line file is 6–8k
  tokens, so writes were cut mid-JSON. Work turns now get a file-sized budget
  and a wall clock that scales with it.
- **Open a folder, not just a zip.** `workspace_import` takes either.
- **Native packages** for Kali/Debian/Ubuntu and Arch/CachyOS, plus an
  auditable `PKGBUILD` that runs the full suite as its `check()` step.

## Fixed

- A 400 saying `max_tokens is too large` was reported to you as
  **"authentication failed — check your API key."** `"token"` was in the
  auth-word list.
- A weak verb satisfied its own object requirement, so "build me a mental
  model of tcp" classified as a repo job.
- An empty path made `workspace_import` import the current working directory.
- A ranged read could not read past the first 200 KB — the exact move the
  truncated-read note tells the model to make.
- The release zip shipped 11 MB of stale duplicate source from `build/`.

## Token cost

The shipped prompt is 7,498 tokens leashed, byte-stable and served from the
provider's prefix cache. The per-step work addendum dropped from 886 to 175
tokens on continuations — about 71k saved on a hundred-step job.

## Verified

67 stdlib-only suites, 4,225 assertions, green from a clean extract of the
zip below. Both packages extracted and import-tested under real GTK.

## Install

```
sudo apt install ./priestsbasilisk_1.1.0.0-1_all.deb
```
```
sudo pacman -U priestsbasilisk-1.1.0.0-1-any.pkg.tar.zst
```

Check what you downloaded with `sha256sum -c SHA256SUMS`.
