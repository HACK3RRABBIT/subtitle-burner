from PySide6.QtCore import QThread
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from subtitleburner_gui.workers import BootstrapWorker


class BootstrapScreen(QMainWindow):
    """Shown before the main window on first launch (or whenever
    requirements.txt has changed) while bootstrap.py installs dependencies -
    a real progress bar and a live scrolling log of the actual pip/npm
    output, so setup is never a black box and never needs a console window.
    """

    def __init__(self, icon_path, on_success):
        super().__init__()
        self.on_success = on_success
        self.setWindowTitle("Subtitle Burner")
        self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(720, 520)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(12)

        title = QLabel("Setting up Subtitle Burner")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(title)

        self.phase_label = QLabel("Preparing...")
        layout.addWidget(self.phase_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        layout.addWidget(self.progress_bar)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        layout.addWidget(self.log_view, stretch=1)

        self.note = QLabel(
            "This only happens once - it downloads the speech/translation engine "
            "(a few GB) and needs an internet connection. Later launches are instant."
        )
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.note)

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(lambda: QApplication.instance().quit())
        self.close_button.hide()
        layout.addWidget(self.close_button)

        self.setCentralWidget(central)

        self._thread = None
        self._worker = None
        self._start_bootstrap()

    def _start_bootstrap(self):
        self._thread = QThread()
        self._worker = BootstrapWorker()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_progress(self, label: str, pct: int, line: str):
        self.phase_label.setText(label)
        self.progress_bar.setValue(pct)
        self.log_view.appendPlainText(line)

    def _on_finished(self, ok: bool, details: str):
        if ok:
            self.on_success()
        else:
            self.phase_label.setText("First-time setup failed - see the log above.")
            self.progress_bar.hide()
            self.note.hide()
            if details:
                self.log_view.appendPlainText("\n--- FAILED ---\n" + details)
            self.close_button.show()
