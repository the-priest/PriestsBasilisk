# Distribution packages

Two native packages, built from this tree. Both install the same thing: the
engine, the GTK4 app, the desktop entry and the icon. Neither one installs a
model or a key — Basilisk is the harness, you bring the brain.

## Kali / Debian / Ubuntu — `.deb`

```
sudo apt install ./priestsbasilisk_1.1.1.0-1_all.deb
```

apt resolves the GTK stack itself (`python3-gi`, `python3-gi-cairo`,
`python3-cairo`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`). `nmap` and `sqlmap` are
*Recommends*, so a default apt install pulls them; `ffuf`, `nikto`, `nuclei`
and `bubblewrap` are *Suggests* and are picked up at runtime if present —
`tooling_check` tells you what is missing with a distro-correct install line.

Modules land in `/usr/lib/python3/dist-packages`, which is version-independent
on Debian by design.

Run it from the app grid, or:

```
basilisk
```

Remove it with `sudo apt remove priestsbasilisk`. Your chats and settings live
in `~/.local/share/basilisk` and `~/.config/basilisk` and are **not** touched.

## CachyOS / Arch — `.pkg.tar.zst`

```
sudo pacman -U priestsbasilisk-1.1.1.0-1-any.pkg.tar.zst
```

Or build it yourself from the `PKGBUILD` beside this file, which is the
honest path and runs the whole test suite as its `check()` step:

```
makepkg -si
```

### Why not site-packages

Arch is rolling. A path pinned to `python3.13/site-packages` stops being
importable the day python moves to 3.14, and the failure is a bare
`ImportError` with nothing to point at. So the modules install to
`/usr/share/priestsbasilisk` and the launcher adds that one directory to
`sys.path`. It survives every python bump and costs one line.

## Neither of those

`install.sh` in the repo root still works everywhere (it detects the distro
and the privilege-escalation tool), and `pip install priestsbasilisk` gives
you the app and the command without the desktop entry.

## After installing

Set a model API key in **Settings → Backends**. It is written to
`~/.config/basilisk/settings.json`, locked to your user, and goes nowhere else.
