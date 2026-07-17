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


def bootstrap_python_deps():
    # torch/torchaudio need a different (CUDA vs CPU) package index depending
    # on the machine, which a single requirements.txt can't express - install
    # everything else normally, then those two separately below.
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
