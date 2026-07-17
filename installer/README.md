# Packaging

## Windows: `SubtitleBurnerSetup.exe`

Built with Inno Setup (`SubtitleBurner.iss`). Bundles a portable Python
(embeddable distribution, pip pre-bootstrapped), a portable Node.js, and a
static ffmpeg build under `runtimes/`, so the installer works on a clean
Windows PC with no prerequisites. Heavy ML dependencies (PyTorch, CUDA,
speech/translation models) are installed on first launch by `bootstrap.py`,
not bundled - that's what keeps the installer itself to ~90MB instead of
several GB.

Build:
```
"C:\Users\<you>\AppData\Local\Programs\Inno Setup 6\ISCC.exe" SubtitleBurner.iss
```
Output: `output\SubtitleBurnerSetup.exe`.

This has been built and tested end-to-end in this session: silent install,
first-run bootstrap (real pip/npm install using only the bundled runtimes),
and silent uninstall (including cleanup of shortcuts and the registry
uninstall key) all verified working.

The installer is per-user only (`PrivilegesRequired=lowest`) - deliberately
no "install for all users" option, since the app writes its own config and
job data under its own install directory at runtime, which wouldn't be
writable from a Program Files-style admin install.

FFmpeg is bundled under its own GPL license (this build includes libx264,
which the CPU encode fallback path needs) - it's invoked as a separate
subprocess, not linked into anything here, same as how HandBrake/OBS/Shotcut
bundle it. `runtimes/ffmpeg/LICENSE` ships alongside it.

## Linux: `subtitleburner_<version>_amd64.deb`

**Status: written but not built or tested anywhere.** This machine's WSL
Ubuntu-24.04 distro has a broken/missing disk image
(`D:\WSL\Ubuntu\ext4.vhdx` doesn't exist) and Docker isn't installed, so
there's no working Linux environment here to run `dpkg-deb` or `apt` against.
Everything below is written to the best of my knowledge of Debian packaging
conventions, but treat it as a first draft that needs a real test pass on an
actual Debian/Ubuntu machine (or a repaired WSL/Docker setup) before you rely
on it - in particular:

- The exact WebKitGTK package name (`gir1.2-webkit2-4.1` vs `-4.0`) needed by
  pywebview's Linux backend varies by distro version; `control` lists both as
  alternatives but this hasn't been verified against a real apt repository.
- The venv-creation and permission steps in `postinst` haven't been run.
- `build_deb.sh` itself hasn't been executed (it needs `dpkg-deb`, which
  doesn't exist on Windows).

Unlike the Windows build, this does **not** bundle portable Python/Node/
ffmpeg - it depends on the distro's own packages (see `DEBIAN/control`),
which is the normal convention for a `.deb` and avoids the architecture/libc
portability problems that bundling Linux binaries would introduce.

To build (on a real Linux box):
```
cd installer
./build_deb.sh
sudo apt install ./output/subtitleburner_1.0.0_amd64.deb
```

Layout:
- `debian/DEBIAN/control` - package metadata and dependencies
- `debian/DEBIAN/postinst` - creates the venv, opens up permissions for the
  single-user-desktop-app model this uses (see comment in the file for the
  shared-machine caveat)
- `debian/DEBIAN/postrm` - removes venv/runtime data on `apt purge`
- `debian/usr/share/applications/*.desktop` - app menu entries (GUI + TUI)
- `debian/usr/bin/subtitleburner` - CLI entry point (`--gui`, `--web`, or
  defaults to the TUI)
- `debian/opt/subtitleburner/` - populated by `build_deb.sh` from the repo's
  app source; not checked in itself
