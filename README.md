<p align="center">
  <img src="assets/logo.png" alt="Subtitle Burner logo" width="128" height="128">
</p>

<h1 align="center">Subtitle Burner</h1>

<p align="center">
  Transcribe, translate, and burn subtitles into any video &mdash; fully offline, GPU-accelerated.
</p>

<p align="center">
  <a href="https://github.com/HACK3RRABBIT/subtitle-burner/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/HACK3RRABBIT/subtitle-burner?display_name=tag"></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue.svg"></a>
  <img alt="Platforms" src="https://img.shields.io/badge/platform-Windows%20%7C%20Linux-informational">
</p>

---

## What it does

Point it at a video, and it will:

1. **Transcribe** the speech (Whisper, via [faster-whisper](https://github.com/SYSTRAN/faster-whisper)) - with automatic NVIDIA GPU acceleration and CPU fallback.
2. **Optionally translate** the subtitles into another language ([Argos Translate](https://github.com/argosopentech/argos-translate)), with per-segment language detection so mixed-language content (e.g. a podcast that switches languages mid-recording) is handled correctly.
3. **Optionally separate speakers** ([pyannote.audio](https://github.com/pyannote/pyannote-audio)), labeling the transcript "Speaker 1", "Speaker 2", etc. - renameable afterwards.
4. **Deliver the result** either as **hardsub** (burned directly into the video, works in every player) or **softsub** (a selectable subtitle track, fast lossless mux, no re-encode).

Everything runs locally - no cloud APIs, no data leaves your machine.

## Interfaces

The same backend is usable three ways:

- **Web UI** - a polished Next.js frontend (upload, live progress, log viewer, settings).
- **Desktop GUI** - the same web UI in a native window (via [pywebview](https://pywebview.flowrl.com/)), no browser needed.
- **Terminal UI** - a full [Textual](https://github.com/Textualize/textual) TUI for headless/server use, including a built-in file browser.

You can also cancel an in-progress job at any point, and unload models on demand to free GPU/RAM for other apps.

## Installation

### Windows

Download `SubtitleBurnerSetup.exe` from the [latest release](https://github.com/HACK3RRABBIT/subtitle-burner/releases/latest) and run it.

- You choose the install directory (nothing is forced into `Program Files`).
- The installer bundles its own portable Python, Node.js, and ffmpeg - **no prerequisites needed** on a clean machine.
- First launch downloads the heavier ML dependencies (PyTorch, speech/translation models - a few GB) and needs an internet connection; this is one-time.

### Linux

A `.deb` package is planned but not published yet. In the meantime, run from source:

```bash
git clone https://github.com/HACK3RRABBIT/subtitle-burner.git
cd subtitle-burner
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd web && npm install && npm run build && cd ..
python app.py          # backend, then in another terminal:
cd web && npm start    # frontend
```

(See `installer/build_deb.sh` / `installer/debian/` if you want to build the `.deb` yourself on a real Linux machine - it isn't tested yet, see `installer/README.md`.)

## Architecture

The backend (`subburn/`) is organized in layers, with ASR/translation/diarization each behind a small plugin registry - adding a new engine is a new file plus one registration call, no changes to the core pipeline:

```
subburn/
  core/        job state, cancellation, pipeline orchestration
  engines/     ASREngine / TranslationEngine / DiarizationEngine base classes + registry
               (faster-whisper, Argos Translate, pyannote.audio implementations)
  models/      resident-model caching (used by engines, and the model-management API)
  subtitles/   SRT + transcript generation
  media/       ffmpeg (extract, burn-in, softsub mux)
  web/         FastAPI routers (auth, jobs, models, settings, logs)
```

`app.py`, `launcher.py`, `gui.py`, and `tui.py` are thin entry points on top of this.

## Tech stack

FastAPI &middot; Next.js &middot; faster-whisper &middot; Argos Translate &middot; pyannote.audio &middot; pywebview &middot; Textual &middot; ffmpeg

## License

[MIT](LICENSE). FFmpeg is bundled with the Windows installer under its own GPL license (invoked as a separate subprocess, not linked into anything here) - see `installer/README.md`.
