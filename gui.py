import subprocess
import sys
import threading

from launcher import (
    WEB_PORT,
    check_prerequisites,
    run_bootstrap_if_needed,
    start_processes,
    stop_processes,
    wait_for_http,
)

LOADING_HTML = """
<html><body style="margin:0;height:100vh;display:flex;align-items:center;
justify-content:center;background:#0f1115;color:#e6e6e6;
font-family:-apple-system,Segoe UI,sans-serif">
<div style="text-align:center">
<h2 style="font-weight:600;margin-bottom:8px">Starting Subtitle Burner...</h2>
<p style="color:#9aa0a6">First launch installs dependencies and can take several minutes -
later launches are much faster.</p>
</div></body></html>
"""

ERROR_HTML = """
<html><body style="margin:0;height:100vh;display:flex;align-items:center;
justify-content:center;background:#0f1115;color:#e6e6e6;
font-family:-apple-system,Segoe UI,sans-serif">
<div style="text-align:center;max-width:520px">
<h2 style="font-weight:600;margin-bottom:8px">Couldn't start Subtitle Burner</h2>
<p style="color:#9aa0a6">{message}</p>
</div></body></html>
"""


def main() -> int:
    problem = check_prerequisites()
    if problem:
        import webview
        webview.create_window(
            "Subtitle Burner", html=ERROR_HTML.format(message=problem),
            width=760, height=480,
        )
        webview.start()
        return 1

    # pywebview itself isn't installed until bootstrap has run (it's in
    # requirements.txt like everything else) - on a fresh install, importing
    # it before this point crashes immediately with ModuleNotFoundError, and
    # since this runs from a console-mode shortcut, that crash's traceback
    # flashes and the console window closes before anyone can read it.
    # Bootstrap runs first, with plain console output, so a first-run install
    # is at least visible instead of silently failing.
    try:
        run_bootstrap_if_needed()
    except subprocess.CalledProcessError as e:
        print(f"First-time setup failed: {e}")
        input("Press Enter to exit...")
        return 1

    import webview

    window = webview.create_window(
        "Subtitle Burner", html=LOADING_HTML,
        width=1280, height=860, min_size=(900, 600),
    )
    procs: dict = {}

    def start_and_load():
        backend, frontend, backend_port = start_processes()
        procs["backend"], procs["frontend"] = backend, frontend

        backend_ready = wait_for_http(f"http://127.0.0.1:{backend_port}/api/models")
        frontend_ready = wait_for_http(f"http://127.0.0.1:{WEB_PORT}/") if backend_ready else False
        if backend_ready and frontend_ready:
            window.load_url(f"http://127.0.0.1:{WEB_PORT}/")
        else:
            window.load_html(ERROR_HTML.format(
                message="The backend or web UI did not start in time. Check the console for errors."
            ))

    threading.Thread(target=start_and_load, daemon=True).start()

    try:
        webview.start()
    finally:
        if procs:
            stop_processes(procs["backend"], procs["frontend"])

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Launched from a console-mode shortcut - without this, an uncaught
        # exception prints its traceback and the window closes immediately
        # after, before anyone can read it ("it flashes and nothing happens").
        import traceback
        traceback.print_exc()
        input("Press Enter to exit...")
        sys.exit(1)
