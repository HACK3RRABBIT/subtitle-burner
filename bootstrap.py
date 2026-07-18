import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
REQUIREMENTS = BASE_DIR / "requirements.txt"
MARKER = BASE_DIR / ".bootstrap_complete"
WEB_DIR = BASE_DIR / "web"


def _requirements_hash() -> str:
    return hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()


def _has_nvidia_gpu() -> bool:
    return shutil.which("nvidia-smi") is not None


def _npm_cmd() -> list[str]:
    # Prefer the portable Node bundled alongside an installed app (fully
    # self-contained, no system Node required); fall back to a system npm on
    # PATH for dev machines that already have Node installed.
    bundled = BASE_DIR / "node" / ("npm.cmd" if sys.platform == "win32" else "bin/npm")
    if bundled.exists():
        return [str(bundled)]
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("Could not find npm (no bundled 'node' folder, and npm isn't on PATH).")
    return [npm]


def _run(cmd: list, **kwargs):
    print("+ " + " ".join(str(c) for c in cmd), flush=True)
    subprocess.run(cmd, check=True, **kwargs)


def _installed_torch_build() -> str | None:
    """Returns the installed torch's version string (e.g. "2.13.0+cu126"),
    or None if torch isn't installed. Used to detect a stale/mismatched
    build left over from a previous bootstrap (e.g. the machine gained or
    lost a GPU between runs) before it can cause the exact corruption this
    guards against - see the uninstall step below."""
    try:
        out = subprocess.run(
            [sys.executable, "-c", "import torch; print(torch.__version__)"],
            capture_output=True, text=True, timeout=30,
        )
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def bootstrap_python_deps():
    # torch/torchaudio need a different (CUDA vs CPU) package index depending
    # on the machine, which a single requirements.txt can't express, so they're
    # installed separately from everything else in requirements.txt.
    #
    # Order matters: torch/torchaudio are installed FIRST, before the rest of
    # requirements.txt. pyannote.audio (installed below) depends on unpinned
    # "torch"/"torchaudio", so if it were installed first, pip would pull in
    # a plain CPU build to satisfy that - then installing the pinned CUDA
    # build afterward relies on pip cleanly replacing it, which has been
    # observed to leave two conflicting dist-info directories and a corrupted
    # torch/lib/c10.dll behind (surfaces as "OSError: WinError 1114" the
    # first time anything imports torch). Installing the real build first
    # means pyannote.audio's later resolution just sees it already satisfied.
    target_build = "2.13.0+cu126" if _has_nvidia_gpu() else "2.13.0"
    installed_build = _installed_torch_build()
    if installed_build is not None and installed_build != target_build:
        print(f"Removing mismatched torch/torchaudio build ({installed_build} != {target_build})...")
        _run([sys.executable, "-m", "pip", "uninstall", "-y", "torch", "torchaudio"])

    if _has_nvidia_gpu():
        print("NVIDIA GPU detected - installing the CUDA build of torch/torchaudio.")
        _run([
            sys.executable, "-m", "pip", "install",
            "torch==2.13.0+cu126", "torchaudio==2.11.0+cu126",
            "--index-url", "https://download.pytorch.org/whl/cu126",
        ])
    else:
        print("No NVIDIA GPU detected - installing CPU-only torch/torchaudio.")
        _run([sys.executable, "-m", "pip", "install", "torch==2.13.0", "torchaudio==2.11.0"])

    lines = REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    normal_reqs = [
        line for line in lines
        if line.strip() and not line.strip().startswith("#")
        and not line.strip().startswith(("torch==", "torchaudio=="))
    ]
    req_file = BASE_DIR / ".requirements_normal.txt"
    req_file.write_text("\n".join(normal_reqs), encoding="utf-8")
    try:
        _run([sys.executable, "-m", "pip", "install", "-r", str(req_file)])
    finally:
        req_file.unlink(missing_ok=True)


def bootstrap_web():
    npm = _npm_cmd()
    _run([*npm, "install"], cwd=str(WEB_DIR))
    _run([*npm, "run", "build"], cwd=str(WEB_DIR))


def needs_bootstrap() -> bool:
    if not MARKER.exists():
        return True
    try:
        return MARKER.read_text(encoding="utf-8").strip() != _requirements_hash()
    except OSError:
        return True


def run(force: bool = False):
    if not force and not needs_bootstrap():
        return
    print("=" * 60)
    print(" First-time setup: installing dependencies")
    print(" This can take a while and needs an internet connection.")
    print("=" * 60, flush=True)
    bootstrap_python_deps()
    bootstrap_web()
    MARKER.write_text(_requirements_hash(), encoding="utf-8")
    print("Setup complete.", flush=True)


if __name__ == "__main__":
    run(force="--force" in sys.argv)
