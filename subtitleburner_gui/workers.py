import logging
import subprocess

from PySide6.QtCore import QObject, QThread, Signal

log = logging.getLogger("gui")

# The sequential steps bootstrap.py runs, matched against its own
# "+ <command>" progress markers so this can show a friendly label instead
# of a raw pip/npm log dump. Purely cosmetic: if bootstrap.py's own step
# order ever changes, this just mislabels a step rather than breaking
# anything - e.g. the rare case where a mismatched torch build is uninstalled
# first shifts every label by one for that run, which is harmless since the
# raw log line is always shown alongside the label.
PHASE_LABELS = [
    "Installing the speech engine (this is the largest download)...",
    "Installing core components...",
    "Installing the web interface...",
    "Finalizing the web interface...",
]


class ApiWorker(QObject):
    """Runs one blocking call (typically an ApiClient method) on a background
    thread. Qt signals marshal the result back onto whichever thread the
    connected slot lives on (the main/GUI thread, in every real use here)."""

    finished = Signal(object)
    error = Signal(Exception)
    auth_required = Signal()

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    def run(self):
        # Imported lazily so that BootstrapWorker (used before bootstrap.py
        # has installed anything, including httpx) can share this module
        # without pulling in api_client.py - only ApiWorker, which is never
        # used before bootstrap completes, actually needs it.
        from subtitleburner_gui.api_client import AuthRequiredError

        try:
            result = self.fn(*self.args, **self.kwargs)
        except AuthRequiredError:
            self.auth_required.emit()
        except Exception as e:
            self.error.emit(e)
        else:
            self.finished.emit(result)


def run_in_thread(fn, *args, on_finished=None, on_error=None, on_auth_required=None, **kwargs):
    """Starts fn(*args, **kwargs) on a new QThread. Returns (thread, worker) -
    the CALLER must keep a reference to this tuple alive (e.g. append to a
    list on self) until it's done; letting it get garbage-collected while the
    thread is still running crashes Qt.
    """
    thread = QThread()
    worker = ApiWorker(fn, *args, **kwargs)
    worker.moveToThread(thread)

    thread.started.connect(worker.run)
    if on_finished:
        worker.finished.connect(on_finished)
    if on_error:
        worker.error.connect(on_error)
    if on_auth_required:
        worker.auth_required.connect(on_auth_required)
    worker.finished.connect(thread.quit)
    worker.error.connect(thread.quit)
    worker.auth_required.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    worker.error.connect(worker.deleteLater)
    worker.auth_required.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)

    thread.start()
    return thread, worker


class BootstrapWorker(QObject):
    """Spawns bootstrap.py as a hidden subprocess (no console window) and
    parses its plain-text progress into friendly step updates - so a fresh
    install never needs a visible terminal. Functionally the same approach
    the old pywebview-based gui.py used (evaluate_js -> here, Qt signals)."""

    progress = Signal(str, int, str)  # label, percent, latest_log_line
    finished = Signal(bool, str)  # ok, details (last ~60 lines if it failed)

    def run(self):
        try:
            import bootstrap as bootstrap_module
            import launcher

            if not bootstrap_module.needs_bootstrap():
                log.info("Bootstrap not needed, skipping")
                self.finished.emit(True, "")
                return

            log.info("Starting bootstrap subprocess")
            proc = subprocess.Popen(
                [str(launcher.PYTHON_EXECUTABLE), "-u", str(launcher.BASE_DIR / "bootstrap.py")],
                cwd=str(launcher.BASE_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                **launcher.popen_kwargs(),
            )

            phase_index = -1
            log_lines: list[str] = []
            for line in proc.stdout:
                line = line.rstrip("\n")
                log_lines.append(line)
                if line.startswith("+ "):
                    phase_index = min(phase_index + 1, len(PHASE_LABELS) - 1)
                    log.info("Bootstrap phase %d: %s", phase_index, line)

                label = PHASE_LABELS[phase_index] if phase_index >= 0 else "Preparing..."
                pct = max(4, round((phase_index + 1) / len(PHASE_LABELS) * 100)) if phase_index >= 0 else 4
                self.progress.emit(label, pct, line)

            proc.wait()
            log.info("Bootstrap subprocess exited with code %s", proc.returncode)
            if proc.returncode != 0:
                details = "\n".join(log_lines[-60:])
                log.error("Bootstrap failed:\n%s", details)
                self.finished.emit(False, details)
            else:
                self.finished.emit(True, "")
        except Exception:
            log.exception("BootstrapWorker crashed unexpectedly")
            self.finished.emit(False, "An unexpected error occurred while checking/installing dependencies.")
