# Releasing — how to publish the packages

Everything here assumes you are in the repo root and the version is already
bumped. `<VER>` below is `1.1.3.0`.

---

## 0. Before anything: the release must be green

The packages are built from the working tree, so a dirty or failing tree ships
as-is. Run the suite first, and do it from a **clean extract of the zip you are
about to publish**, not from the tree you built it in — that is the difference
between "it passes here" and "it passes for them".

```bash
for f in tests/test_*.py; do python3 "$f" >/dev/null || echo "FAILED: $f"; done
```

Then confirm nothing stale is in the tree. `python -m build` leaves `build/`
and `priestsbasilisk.egg-info/` behind, and the release zip is made by copying
the tree — that is how 11 MB of duplicate source shipped once already:

```bash
rm -rf build priestsbasilisk.egg-info .eggs
```

---

## 1. Tag the release

GitHub builds a release around a tag, so the tag comes first.

```bash
git add -A
```
```bash
git commit -m "v1.1.3.0 — leashed work mode, promise gate, native packages"
```
```bash
git tag -a v1.1.3.0 -m "v1.1.3.0"
```
```bash
git push origin main --follow-tags
```

If you have already pushed the tag and need to move it, delete it on the remote
first (`git push origin :refs/tags/v1.1.3.0`) — a moved tag that a release is
already attached to will confuse the release page rather than update it.

---

## 2. Create the GitHub Release and attach the files

### With the `gh` CLI (fastest)

```bash
gh release create v1.1.3.0 --title "v1.1.3.0" --notes-file RELEASE_NOTES.md
```
```bash
gh release upload v1.1.3.0 priestsbasilisk_1.1.3.0-1_all.deb priestsbasilisk-1.1.3.0-1-any.pkg.tar.zst PriestsBasilisk-1.1.3.0.zip SHA256SUMS
```

To replace a file you already uploaded, add `--clobber`:

```bash
gh release upload v1.1.3.0 priestsbasilisk_1.1.3.0-1_all.deb --clobber
```

### By hand

Go to **Releases → Draft a new release**, choose the `v1.1.3.0` tag, paste the
notes, then drag the four files into the "Attach binaries" box. Publish.

### What to attach, and nothing else

| File | Who it is for |
| --- | --- |
| `priestsbasilisk_1.1.3.0-1_all.deb` | Kali, Debian, Ubuntu |
| `priestsbasilisk-1.1.3.0-1-any.pkg.tar.zst` | Arch, CachyOS |
| `PriestsBasilisk-1.1.3.0.zip` | source, for people who want to read it first |
| `SHA256SUMS` | so they can check what they downloaded |

Do **not** attach the wheel unless you are also publishing to PyPI — a wheel on
a release page is something people `pip install` into a broken GTK environment
and then open an issue about.

---

## 3. Publish the checksums

Generate them from the exact files you are uploading, in the same directory:

```bash
sha256sum priestsbasilisk_1.1.3.0-1_all.deb priestsbasilisk-1.1.3.0-1-any.pkg.tar.zst PriestsBasilisk-1.1.3.0.zip > SHA256SUMS
```

Anyone can then verify with:

```bash
sha256sum -c SHA256SUMS
```

This matters more for you than for most projects: the README tells people to
read the installer before running it. Checksums are the same promise applied to
the binaries.

---

## 4. Optional — sign the release

If you have a GPG key, a detached signature over `SHA256SUMS` covers all three
files at once:

```bash
gpg --detach-sign --armor SHA256SUMS
```

Attach `SHA256SUMS.asc` alongside. Skip this if you do not already publish a
key somewhere people can find it — an unverifiable signature is theatre.

---

## 5. The AUR (Arch / CachyOS users expect this)

The `.pkg.tar.zst` on a release page is a convenience. Arch users install from
the AUR, and the AUR ships a **PKGBUILD, not a binary**.

Create the package base at <https://aur.archlinux.org/> (SSH key required),
then:

```bash
git clone ssh://aur@aur.archlinux.org/priestsbasilisk.git aur-priestsbasilisk
```
```bash
cp packaging/PKGBUILD aur-priestsbasilisk/
```
```bash
cd aur-priestsbasilisk && makepkg --printsrcinfo > .SRCINFO
```
```bash
git add PKGBUILD .SRCINFO && git commit -m "v1.1.3.0" && git push
```

Two things the AUR will reject or complain about:

- **`.SRCINFO` must be regenerated every time** the PKGBUILD changes. It is not
  optional and it is the most common first-submission rejection.
- **`sha256sums=('SKIP')`** is fine for a git source but frowned on for a
  tarball. Once the tag exists, replace it with the real hash:

```bash
makepkg -g
```

Paste what that prints into the PKGBUILD, then regenerate `.SRCINFO`.

Test the build in a clean chroot before you push, because AUR users will:

```bash
cd aur-priestsbasilisk && makepkg -si --noconfirm
```

---

## 6. Debian/Kali users: a repo is nicer than a file

A `.deb` on a release page has to be re-downloaded by hand for every update.
If you want `apt upgrade` to just work, the cheapest option is a GitHub Pages
apt repo:

```bash
mkdir -p apt-repo/pool/main && cp priestsbasilisk_1.1.3.0-1_all.deb apt-repo/pool/main/
```
```bash
cd apt-repo && dpkg-scanpackages pool /dev/null > Packages && gzip -k -f Packages
```

Then serve `apt-repo/` from the `gh-pages` branch and have people add:

```bash
echo "deb [trusted=yes] https://the-priest.github.io/PriestsBasilisk ./" | sudo tee /etc/apt/sources.list.d/basilisk.list
```

`[trusted=yes]` skips signature checking. That is acceptable for a personal
repo people opt into, but if you want it done properly, sign the `Release` file
with GPG and drop the flag. Do not put `[trusted=yes]` in the README as the
recommended path without saying what it means.

---

## 7. Update the pointers

The README pins the version in three install commands. They are now
`1.1.3.0` — if you cut `1.1.0.1`, these move with it:

- `README.md` — the two package install commands and the version badge
- `index.html` — the two copy-buttons in the install section, and the hero
  eyebrow (`open source · v1.1.3.0`)
- `pyproject.toml` and `basilisk.py` — the version itself

`tests/test_readme.py`, `tests/test_site.py` and `tests/test_packaging.py`
check that these agree, so a mismatch fails the suite rather than shipping.

---

## 8. Announce

The disambiguation block exists because "Basilisk" collides with four other
projects. When you post anywhere, lead with what it *is* — a local coding
assistant with an armable pentest mode — or the first reply will be someone
explaining Roko's Basilisk to you.

---

## Quick reference

```bash
rm -rf build priestsbasilisk.egg-info && for f in tests/test_*.py; do python3 "$f" >/dev/null || echo "FAILED: $f"; done
```
```bash
git tag -a v1.1.3.0 -m "v1.1.3.0" && git push origin main --follow-tags
```
```bash
sha256sum priestsbasilisk_1.1.3.0-1_all.deb priestsbasilisk-1.1.3.0-1-any.pkg.tar.zst PriestsBasilisk-1.1.3.0.zip > SHA256SUMS
```
```bash
gh release create v1.1.3.0 --title "v1.1.3.0" --notes-file RELEASE_NOTES.md
```
```bash
gh release upload v1.1.3.0 priestsbasilisk_1.1.3.0-1_all.deb priestsbasilisk-1.1.3.0-1-any.pkg.tar.zst PriestsBasilisk-1.1.3.0.zip SHA256SUMS
```
