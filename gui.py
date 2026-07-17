import logging
import sys
import threading

from launcher import (
    BASE_DIR,
    check_prerequisites,
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


def main() -> int:
    log.info("gui.py starting, BASE_DIR=%s", BASE_DIR)

    from PySide6.QtWidgets import QApplication, QMessageBox

    # bootstrap_screen (and its BootstrapWorker) must be importable before
    # bootstrap.py has installed anything - main_window pulls in httpx via
    # ApiClient, which (like the rest of the ML/web stack) is only guaranteed
    # present after bootstrap succeeds, so it's imported later, once that's
    # actually true. Same chicken-and-egg shape as the old pywebview/pystray
    # pre-bundling requirement.
    from subtitleburner_gui.bootstrap_screen import BootstrapScreen

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    problem = check_prerequisites()
    if problem:
        log.error("check_prerequisites failed: %s", problem)
        QMessageBox.critical(None, "Subtitle Burner - Error", problem)
        return 1

    state = {"backend": None, "main_window": None, "tray": None}

    def shutdown():
        log.info("Shutting down")
        if state["backend"] is not None:
            stop_processes(state["backend"], None)
        app.quit()

    def show_main_window():
        if state["main_window"] is None:
            return
        state["main_window"].show()
        state["main_window"].raise_()
        state["main_window"].activateWindow()

    def start_backend_and_show_main_window():
        from subtitleburner_gui.main_window import MainWindow

        log.info("Bootstrap OK, starting backend")
        backend, _frontend, backend_port = start_processes(log_to_files=True, start_frontend=False)
        state["backend"] = backend

        backend_ready = wait_for_http(f"http://127.0.0.1:{backend_port}/api/models")
        log.info("backend_ready=%s", backend_ready)
        if not backend_ready:
            QMessageBox.critical(None, "Subtitle Burner - Error", "The backend did not start in time.")
            shutdown()
            return

        state["main_window"] = MainWindow(f"http://127.0.0.1:{backend_port}", ICON_PATH)
        state["tray"] = _start_tray_icon(app, show_main_window, shutdown)
        show_main_window()

    bootstrap_screen = BootstrapScreen(ICON_PATH, start_backend_and_show_main_window)
    bootstrap_screen.show()

    try:
        return app.exec()
    finally:
        log.info("app.exec() returned, shutting down")
        if state["backend"] is not None:
            stop_processes(state["backend"], None)


def _start_tray_icon(app, on_open, on_quit):
    """Best-effort system tray icon: lets the app keep running (and the
    backend keep serving) when the window is closed, with Open/Quit from the
    tray. Never fatal - if the tray isn't available for any reason, the app
    just runs without one instead of crashing."""
    try:
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QMenu, QSystemTrayIcon

        tray = QSystemTrayIcon(QIcon(str(ICON_PATH)), app)
        tray.setToolTip("Subtitle Burner")

        menu = QMenu()
        open_action = menu.addAction("Open Subtitle Burner")
        open_action.triggered.connect(on_open)
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(on_quit)
        tray.setContextMenu(menu)

        tray.activated.connect(
            lambda reason: on_open() if reason == QSystemTrayIcon.ActivationReason.Trigger else None
        )
        tray.show()
        log.info("Tray icon started")
        return tray
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
        # work even if Qt itself never got that far.
        log.exception("Fatal error in gui.py main()")
        import traceback
        tb = traceback.format_exc()
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, tb[-1500:], "Subtitle Burner - Error", 0x10)
        except Exception:
            pass
        sys.exit(1)
