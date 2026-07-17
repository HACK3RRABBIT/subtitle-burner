import json
import logging
import subprocess
import sys
import threading
import time

from launcher import (
    BASE_DIR,
    PYTHON_EXECUTABLE,
    WEB_PORT,
    check_prerequisites,
    popen_kwargs,
    start_processes,
    stop_processes,
    wait_for_http,
)

ICON_PATH = BASE_DIR / "assets" / "icon.ico"

# Launched windowless (pythonw.exe, no console) - a log file is the only way
# to see what happened if something goes wrong, since there's no terminal to
# print to and stderr isn't attached to anything.
logging.basicConfig(
    filename=str(BASE_DIR / "gui.log"),
    filemode="w",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("gui")


def _log_thread_exceptions(args):
    log.error("Unhandled exception in thread %s", args.thread.name if args.thread else "?",
              exc_info=(args.exc_type, args.exc_value, args.exc_traceback))


threading.excepthook = _log_thread_exceptions

BASE_CSS = """
margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
background:#0f1115;color:#e6e6e6;font-family:-apple-system,Segoe UI,sans-serif;
"""

SETUP_HTML = f"""
<html><body style="{BASE_CSS}">
<div style="text-align:center;max-width:560px;padding:24px">
<h2 style="font-weight:600;margin-bottom:16px">Setting up Subtitle Burner</h2>
<div id="phase" style="font-size:15px;color:#c7cbd1;margin-bottom:10px">Preparing...</div>
<div style="background:#1c1f26;border-radius:8px;height:8px;overflow:hidden;margin:0 auto 10px;max-width:420px">
  <div id="bar" style="background:#2563eb;height:100%;width:4%;transition:width 0.4s"></div>
</div>
<div id="detail" style="font-size:11px;color:#6b7178;font-family:Consolas,monospace;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:480px;margin:0 auto"></div>
<p style="color:#5a616a;font-size:12px;margin-top:22px">This only happens once - it downloads the
speech/translation engine (a few GB) and needs an internet connection. Later launches are instant.</p>
</div></body></html>
"""

LOADING_HTML = f"""
<html><body style="{BASE_CSS}">
<div style="text-align:center">
<h2 style="font-weight:600;margin-bottom:8px">Starting Subtitle Burner...</h2>
</div></body></html>
"""

ERROR_HTML_TEMPLATE = """
<html><body style="{css}">
<div style="text-align:center;max-width:640px;padding:24px">
<h2 style="font-weight:600;margin-bottom:8px">Couldn't start Subtitle Burner</h2>
<p style="color:#9aa0a6">{message}</p>
{details_block}
</div></body></html>
"""

# The four sequential steps bootstrap.py runs, in order - matched against its
# own "+ <command>" progress markers so this can show a friendly label instead
# of a raw pip/npm log dump. Purely cosmetic: if bootstrap.py's own step order
# ever changes, this just mislabels a step rather than breaking anything.
PHASE_LABELS = [
    "Installing core components...",
    "Installing the speech engine (this is the largest download)...",
    "Installing the web interface...",
    "Finalizing the web interface...",
]


def _error_html(message: str, details: str = "") -> str:
    details_block = ""
    if details:
        escaped = (
            details.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        details_block = (
            '<pre style="text-align:left;max-height:220px;overflow:auto;background:#1c1f26;'
            'padding:10px;border-radius:6px;font-size:11px;color:#9aa0a6">' + escaped + "</pre>"
        )
    return ERROR_HTML_TEMPLATE.format(css=BASE_CSS, message=message, details_block=details_block)


def run_bootstrap_with_progress(window) -> tuple[bool, str]:
    """Runs bootstrap.py as a hidden subprocess (no console window), parsing
    its plain-text progress into friendly step updates pushed into the
    loading window - so a fresh install never needs a visible terminal."""
    import bootstrap as bootstrap_module

    if not bootstrap_module.needs_bootstrap():
        log.info("Bootstrap not needed, skipping")
        return True, ""

    log.info("Starting bootstrap subprocess")
    proc = subprocess.Popen(
        [str(PYTHON_EXECUTABLE), "-u", str(BASE_DIR / "bootstrap.py")],
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        **popen_kwargs(),
    )

    phase_index = -1
    log_lines: list[str] = []
    last_update = 0.0
    for line in proc.stdout:
        line = line.rstrip("\n")
        log_lines.append(line)
        if line.startswith("+ "):
            phase_index = min(phase_index + 1, len(PHASE_LABELS) - 1)
            log.info("Bootstrap phase %d: %s", phase_index, line)

        now = time.time()
        if now - last_update < 0.2:
            continue
        last_update = now

        label = PHASE_LABELS[phase_index] if phase_index >= 0 else "Preparing..."
        pct = max(4, round((phase_index + 1) / len(PHASE_LABELS) * 100)) if phase_index >= 0 else 4
        try:
            window.evaluate_js(
                "document.getElementById('phase').textContent = " + json.dumps(label) + ";"
                "document.getElementById('bar').style.width = " + json.dumps(f"{pct}%") + ";"
                "document.getElementById('detail').textContent = " + json.dumps(line[-140:]) + ";"
            )
        except Exception:
            log.exception("evaluate_js failed while updating bootstrap progress")

    proc.wait()
    log.info("Bootstrap subprocess exited with code %s", proc.returncode)
    if proc.returncode != 0:
        return False, "\n".join(log_lines[-60:])
    return True, ""


def start_and_load(window, procs: dict):
    try:
        ok, details = run_bootstrap_with_progress(window)
        if not ok:
            log.error("Bootstrap failed:\n%s", details)
            window.load_html(_error_html("First-time setup failed. Details below:", details))
            return

        log.info("Bootstrap OK, starting backend/frontend")
        window.load_html(LOADING_HTML)
        backend, frontend, backend_port = start_processes()
        procs["backend"], procs["frontend"] = backend, frontend

        backend_ready = wait_for_http(f"http://127.0.0.1:{backend_port}/api/models")
        frontend_ready = wait_for_http(f"http://127.0.0.1:{WEB_PORT}/") if backend_ready else False
        log.info("backend_ready=%s frontend_ready=%s", backend_ready, frontend_ready)
        if backend_ready and frontend_ready:
            window.load_url(f"http://127.0.0.1:{WEB_PORT}/")
        else:
            window.load_html(_error_html("The backend or web UI did not start in time."))
    except Exception:
        log.exception("start_and_load failed")
        try:
            window.load_html(_error_html("An unexpected error occurred during startup."))
        except Exception:
            log.exception("Could not even show the error in the window")


def main() -> int:
    log.info("gui.py starting, BASE_DIR=%s", BASE_DIR)
    import webview

    problem = check_prerequisites()
    if problem:
        log.error("check_prerequisites failed: %s", problem)
        webview.create_window("Subtitle Burner", html=_error_html(problem), width=760, height=480)
        webview.start()
        return 1

    window = webview.create_window(
        "Subtitle Burner", html=SETUP_HTML,
        width=1280, height=860, min_size=(900, 600),
    )
    procs: dict = {}
    quitting = threading.Event()

    def on_closing():
        # Closing the window just hides it (minimize to tray) unless the
        # tray's own "Quit" action requested a real close.
        if quitting.is_set():
            return None
        window.hide()
        return False

    window.events.closing += on_closing

    threading.Thread(target=start_and_load, args=(window, procs), daemon=True).start()

    tray_icon = _start_tray_icon(window, quitting)

    try:
        webview.start()
    finally:
        log.info("webview.start() returned, shutting down")
        if tray_icon:
            tray_icon.stop()
        if procs:
            stop_processes(procs["backend"], procs["frontend"])

    return 0


def _start_tray_icon(window, quitting: threading.Event):
    """Best-effort system tray icon: lets the app keep running (and the
    backend/frontend keep serving) when the window is closed, with Open/Quit
    from the tray. Never fatal - if the tray backend isn't available for any
    reason, the app just runs without one instead of crashing."""
    try:
        import pystray
        from PIL import Image

        image = Image.open(ICON_PATH)

        def on_open(icon, item):
            window.show()

        def on_quit(icon, item):
            quitting.set()
            icon.stop()
            window.destroy()

        menu = pystray.Menu(
            pystray.MenuItem("Open Subtitle Burner", on_open, default=True),
            pystray.MenuItem("Quit", on_quit),
        )
        icon = pystray.Icon("subtitleburner", image, "Subtitle Burner", menu)
        icon.run_detached()
        log.info("Tray icon started")
        return icon
    except Exception:
        log.exception("Could not start tray icon; continuing without one")
        return None


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Launched from a windowless (pythonw.exe) shortcut with no console at
        # all - without this, an uncaught exception here would fail completely
        # silently. A native message box is the only surface guaranteed to
        # work even if webview itself never got that far.
        log.exception("Fatal error in gui.py main()")
        import traceback
        tb = traceback.format_exc()
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, tb[-1500:], "Subtitle Burner - Error", 0x10)
        except Exception:
            pass
        sys.exit(1)
