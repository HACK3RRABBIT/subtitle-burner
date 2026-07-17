import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path
from typing import Optional

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

if getattr(sys, "frozen", False):
    # Legacy dev-exe path: a PyInstaller-frozen launcher.exe sitting next to a
    # fully provisioned dev venv (this venv's dependencies are managed by
    # hand, not by bootstrap.py).
    PYTHON_EXECUTABLE = (
        BASE_DIR / "venv" / "Scripts" / "python.exe" if sys.platform == "win32"
        else BASE_DIR / "venv" / "bin" / "python"
    )
else:
    # Running as a plain script - either the dev venv's own interpreter, or
    # (in an installed app) the portable Python bundled alongside this file.
    # Either way, reuse whatever interpreter is already running us: bootstrap.py
    # installs dependencies into that same interpreter, so they always match.
    PYTHON_EXECUTABLE = Path(sys.executable)

APP_SCRIPT = BASE_DIR / "app.py"
CONFIG_PATH = BASE_DIR / "config.json"
WEB_DIR = BASE_DIR / "web"
BUNDLED_FFMPEG_DIR = BASE_DIR / "ffmpeg"
BUNDLED_NODE_DIR = BASE_DIR / "node"
WEB_PORT = 3000


def get_backend_port() -> int:
    if CONFIG_PATH.exists():
        try:
            return int(json.loads(CONFIG_PATH.read_text(encoding="utf-8")).get("port", 8000))
        except (json.JSONDecodeError, OSError, ValueError):
            pass
    return 8000


def get_lan_ip() -> str | None:
    # No traffic is actually sent (UDP connect() just picks the outbound
    # interface/route) - this is the standard trick to find the LAN-facing
    # IP without parsing ipconfig output.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None


def wait_for_http(url: str, timeout: float = 180.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return True
        except Exception:
            time.sleep(1)
    return False


def popen_kwargs() -> dict:
    """Extra kwargs for subprocess.Popen/run so child processes never pop up
    their own console window on Windows. Safe to use even when the parent
    itself has a console (launcher.py's own CLI mode): the child still
    inherits and writes to that existing console since this only suppresses
    creating a *new* one - it only matters when the parent has no console at
    all (gui.py, launched via pythonw.exe), where it prevents a window from
    flashing open for each spawned subprocess."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def child_env() -> dict:
    """Environment for the backend/frontend subprocesses: prepends the bundled
    ffmpeg directory to PATH when present, so an installed app finds it without
    requiring a system-wide ffmpeg install."""
    env = os.environ.copy()
    if BUNDLED_FFMPEG_DIR.exists():
        env["PATH"] = str(BUNDLED_FFMPEG_DIR) + os.pathsep + env.get("PATH", "")
    return env


def npm_command() -> list[str]:
    bundled = BUNDLED_NODE_DIR / ("npm.cmd" if sys.platform == "win32" else "bin/npm")
    if bundled.exists():
        return [str(bundled)]
    npm = shutil.which("npm")
    if npm:
        return [npm]
    return []


def check_prerequisites() -> Optional[str]:
    """Returns an error message if something required is missing, else None."""
    if not PYTHON_EXECUTABLE.exists():
        return (
            f"Could not find {PYTHON_EXECUTABLE}.\n"
            "This launcher expects to sit next to the 'venv' (or bundled 'python') folder it was set up with."
        )
    if not WEB_DIR.exists() or not npm_command():
        return "Could not find the 'web' folder, or no npm available (checked bundled 'node' folder and PATH)."
    return None


def run_bootstrap_if_needed():
    """Installs/updates dependencies on first run (or after an update changes
    requirements.txt). Skipped for the legacy frozen dev-exe, which already
    has a hand-provisioned venv rather than a bootstrap.py-managed one."""
    if getattr(sys, "frozen", False):
        return
    import bootstrap

    if bootstrap.needs_bootstrap():
        subprocess.run(
            [str(PYTHON_EXECUTABLE), "-u", str(BASE_DIR / "bootstrap.py")],
            cwd=str(BASE_DIR), check=True, **popen_kwargs(),
        )


def start_processes(
    log_to_files: bool = False, start_frontend: bool = True
) -> tuple[subprocess.Popen, Optional[subprocess.Popen], int]:
    """Starts the FastAPI backend (and, unless told not to, the Next.js
    frontend) as subprocesses.

    Caller is responsible for checking check_prerequisites() first and for
    calling stop_processes() to tear these down.

    log_to_files: when False (launcher.py's own console-mode default), the
    children inherit this process's stdout/stderr, which is exactly what a
    console-mode caller wants. When True (gui.py, launched via pythonw.exe
    with no console at all), that inherited stdout/stderr is invalid/closed -
    uvicorn (and Next.js) crash outright the moment they try to log anything
    to it. Redirecting to real files avoids that crash and doubles as a
    diagnostic log when something goes wrong.

    start_frontend: the Windows native GUI renders its own UI with Qt and
    never talks to Next.js - it only needs the FastAPI backend. Pass False to
    skip spawning the frontend entirely; the returned frontend is then None.
    """
    backend_port = get_backend_port()
    env = child_env()

    backend_kwargs = {}
    if log_to_files:
        backend_kwargs["stdout"] = open(BASE_DIR / "backend.log", "w", encoding="utf-8")
        backend_kwargs["stderr"] = subprocess.STDOUT

    backend = subprocess.Popen(
        [str(PYTHON_EXECUTABLE), "-u", str(APP_SCRIPT)],
        cwd=str(BASE_DIR),
        env=env,
        **popen_kwargs(),
        **backend_kwargs,
    )

    frontend = None
    if start_frontend:
        npm = npm_command()
        frontend_kwargs = {}
        if log_to_files:
            frontend_kwargs["stdout"] = open(BASE_DIR / "frontend.log", "w", encoding="utf-8")
            frontend_kwargs["stderr"] = subprocess.STDOUT
        frontend = subprocess.Popen(
            [*npm, "run", "start", "--", "-H", "0.0.0.0", "-p", str(WEB_PORT)],
            cwd=str(WEB_DIR),
            env=env,
            **popen_kwargs(),
            **frontend_kwargs,
        )
    return backend, frontend, backend_port


def stop_processes(backend: subprocess.Popen, frontend: Optional[subprocess.Popen]):
    procs = [p for p in (backend, frontend) if p is not None]
    for proc in procs:
        if proc.poll() is None:
            proc.terminate()
    for proc in procs:
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def main():
    print("=" * 60)
    print(" Subtitle Burner - starting server")
    print("=" * 60)

    problem = check_prerequisites()
    if problem:
        print(f"ERROR: {problem}")
        input("Press Enter to exit...")
        return 1

    try:
        run_bootstrap_if_needed()
    except subprocess.CalledProcessError as e:
        print(f"ERROR: first-time setup failed ({e}). Check the output above.")
        input("Press Enter to exit...")
        return 1

    backend, frontend, backend_port = start_processes()
    print(f"Working directory: {BASE_DIR}")
    print(f"Backend (API) port: {backend_port}   Web UI port: {WEB_PORT}")
    print("Log output follows below. Close this window or press Ctrl+C to stop everything.\n")

    try:
        print("Waiting for the backend to become ready...")
        backend_ready = wait_for_http(f"http://127.0.0.1:{backend_port}/api/models")
        print("Waiting for the web UI to become ready...")
        frontend_ready = wait_for_http(f"http://127.0.0.1:{WEB_PORT}/") if backend_ready else False

        if backend_ready and frontend_ready:
            url = f"http://127.0.0.1:{WEB_PORT}/"
            print(f"Ready. Opening {url}")
            lan_ip = get_lan_ip()
            if lan_ip:
                print(f"Other devices on the same network (phone, etc.) can use: http://{lan_ip}:{WEB_PORT}/")
                print("(Requires a Windows Firewall inbound rule for this port - see setup notes if it doesn't load.)")
            webbrowser.open(url)
        else:
            print("Did not become ready in time. Check the log output above for errors.")

        # Either process exiting means the app is done; stop waiting on the other.
        while backend.poll() is None and frontend.poll() is None:
            time.sleep(1)
        print("\nOne of the processes exited; shutting down the other.")
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        stop_processes(backend, frontend)

    input("Press Enter to close this window...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
