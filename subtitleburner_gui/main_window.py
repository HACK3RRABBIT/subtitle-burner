from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent, QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QPlainTextEdit,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from subtitleburner_gui.api_client import ApiClient
from subtitleburner_gui.constants import (
    LANGUAGES,
    STATUS_LABELS,
    format_bytes,
    format_eta,
    model_label,
)
from subtitleburner_gui.login_dialog import LoginDialog
from subtitleburner_gui.settings_dialog import SettingsDialog
from subtitleburner_gui.workers import run_in_thread

ACTIVE_STATUSES = {
    "queued", "extracting_audio", "transcribing", "diarizing",
    "translating", "burning_in", "muxing_subtitles", "cancelling",
}


class DropArea(QFrame):
    def __init__(self, on_file_chosen):
        super().__init__()
        self.on_file_chosen = on_file_chosen
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumHeight(110)
        self.setStyleSheet(
            "QFrame { border: 2px dashed #888; border-radius: 8px; }"
            "QFrame:hover { border-color: #4a90d9; }"
        )
        layout = QVBoxLayout(self)
        self.label = QLabel("Click or drag a video file here")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

    def set_filename(self, name: str):
        self.label.setText(name)

    def mousePressEvent(self, event):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a video file", "", "Video files (*.*)")
        if path:
            self.on_file_chosen(path)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            self.on_file_chosen(urls[0].toLocalFile())


class MainWindow(QMainWindow):
    def __init__(self, base_url: str, icon_path):
        super().__init__()
        self.api = ApiClient(base_url)
        self.icon_path = icon_path
        self._threads = []
        self._pending_after_login = None

        self.video_path = None
        self.job_id = None
        self.job_result = None
        self._logs_since = 0

        self.setWindowTitle("Subtitle Burner")
        self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(720, 780)

        outer = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(outer)
        self.setCentralWidget(scroll)

        layout = QVBoxLayout(outer)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Subtitle Burner")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch(1)
        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self.open_settings)
        header.addWidget(self.settings_button)
        layout.addLayout(header)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #d33; font-weight: 500;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        self.drop_area = DropArea(self._on_file_chosen)
        layout.addWidget(self.drop_area)

        self.model_combo = QComboBox()
        layout.addWidget(QLabel("Whisper model"))
        layout.addWidget(self.model_combo)

        lang_row = QHBoxLayout()
        source_col = QVBoxLayout()
        source_col.addWidget(QLabel("Spoken language"))
        self.source_combo = self._lang_combo("Auto-detect")
        source_col.addWidget(self.source_combo)
        lang_row.addLayout(source_col)

        target_col = QVBoxLayout()
        target_col.addWidget(QLabel("Subtitle language"))
        self.target_combo = self._lang_combo("No translation (same as spoken)")
        target_col.addWidget(self.target_combo)
        lang_row.addLayout(target_col)
        layout.addLayout(lang_row)

        self.diarize_check = QCheckBox("Separate speakers (slower, needs a Hugging Face token in Settings)")
        layout.addWidget(self.diarize_check)

        mode_row = QHBoxLayout()
        self.hardsub_radio = QRadioButton("Hardsub (burn into video)")
        self.softsub_radio = QRadioButton("Softsub (selectable track)")
        self.hardsub_radio.setChecked(True)
        mode_row.addWidget(self.hardsub_radio)
        mode_row.addWidget(self.softsub_radio)
        layout.addLayout(mode_row)
        self.mode_hint = QLabel(
            "Subtitles are permanently drawn onto the video - works everywhere, can't be turned off."
        )
        self.mode_hint.setWordWrap(True)
        self.mode_hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.mode_hint)
        self.hardsub_radio.toggled.connect(self._update_mode_hint)

        self.submit_button = QPushButton("Upload && Process")
        self.submit_button.clicked.connect(self.submit_job)
        self.submit_button.setEnabled(False)
        layout.addWidget(self.submit_button)

        # --- progress ---
        self.progress_frame = QWidget()
        progress_layout = QVBoxLayout(self.progress_frame)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        self.status_label = QLabel("")
        progress_layout.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        progress_layout.addWidget(self.progress_bar)
        eta_row = QHBoxLayout()
        self.eta_label = QLabel("")
        self.eta_label.setStyleSheet("color: #888; font-size: 11px;")
        eta_row.addWidget(self.eta_label)
        eta_row.addStretch(1)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_job)
        eta_row.addWidget(self.cancel_button)
        progress_layout.addLayout(eta_row)
        self.progress_frame.hide()
        layout.addWidget(self.progress_frame)

        # --- results ---
        self.results_frame = QWidget()
        results_layout = QVBoxLayout(self.results_frame)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.addWidget(QLabel("Done!"))
        dl_row = QHBoxLayout()
        self.download_button = QPushButton("Download video")
        self.download_button.clicked.connect(self._open_download)
        dl_row.addWidget(self.download_button)
        self.transcript_button = QPushButton("Copy transcript")
        self.transcript_button.clicked.connect(self._copy_transcript)
        dl_row.addWidget(self.transcript_button)
        results_layout.addLayout(dl_row)
        self.transcript_view = QPlainTextEdit()
        self.transcript_view.setReadOnly(True)
        self.transcript_view.setMaximumHeight(160)
        results_layout.addWidget(self.transcript_view)

        rename_row = QHBoxLayout()
        self.speaker_names_edit = QLineEdit()
        self.speaker_names_edit.setPlaceholderText("SPEAKER_00=Alice, SPEAKER_01=Bob")
        rename_row.addWidget(self.speaker_names_edit)
        self.apply_names_button = QPushButton("Apply speaker names")
        self.apply_names_button.clicked.connect(self._apply_speaker_names)
        rename_row.addWidget(self.apply_names_button)
        results_layout.addLayout(rename_row)

        self.new_job_button = QPushButton("Start another job")
        self.new_job_button.clicked.connect(self.reset_for_new_job)
        results_layout.addWidget(self.new_job_button)

        self.results_frame.hide()
        layout.addWidget(self.results_frame)

        # --- log console ---
        self.log_toggle_button = QPushButton("Show backend log")
        self.log_toggle_button.setCheckable(True)
        self.log_toggle_button.toggled.connect(self._toggle_log_console)
        layout.addWidget(self.log_toggle_button)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(180)
        self.log_view.setStyleSheet("font-family: Consolas, monospace; font-size: 10px; background: #111; color: #ccc;")
        self.log_view.hide()
        layout.addWidget(self.log_view)

        layout.addStretch(1)

        self.job_timer = QTimer(self)
        self.job_timer.setInterval(1500)
        self.job_timer.timeout.connect(self._poll_job)

        self.log_timer = QTimer(self)
        self.log_timer.setInterval(2000)
        self.log_timer.timeout.connect(self._poll_logs)

        self._load_initial_data()

    # --- helpers ---
    def _lang_combo(self, placeholder: str) -> QComboBox:
        combo = QComboBox()
        combo.addItem(placeholder, "")
        for code, label in LANGUAGES:
            combo.addItem(label, code)
        return combo

    def _update_mode_hint(self):
        if self.hardsub_radio.isChecked():
            self.mode_hint.setText(
                "Subtitles are permanently drawn onto the video - works everywhere, can't be turned off."
            )
        else:
            self.mode_hint.setText(
                "Subtitles are embedded as a selectable track - smaller/faster, needs a player that supports it."
            )

    def _show_error(self, message: str):
        self.error_label.setText(message)
        self.error_label.show()

    def _clear_error(self):
        self.error_label.hide()

    # --- initial load / auth ---
    def _load_initial_data(self):
        t = run_in_thread(
            self.api.list_models,
            on_finished=self._on_models_loaded,
            on_error=self._on_load_error,
            on_auth_required=self._prompt_login,
        )
        self._threads.append(t)

    def _on_models_loaded(self, models: list[str]):
        self.models = models
        self.model_combo.clear()
        for m in models:
            self.model_combo.addItem(model_label(m), m)
        t = run_in_thread(self.api.get_settings, on_finished=self._on_settings_loaded, on_error=self._on_load_error)
        self._threads.append(t)

    def _on_settings_loaded(self, s: dict):
        default_model = s.get("default_model")
        if default_model:
            idx = self.model_combo.findData(default_model)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
        default_source = s.get("default_source_lang")
        if default_source:
            idx = self.source_combo.findData(default_source)
            if idx >= 0:
                self.source_combo.setCurrentIndex(idx)
        default_target = s.get("default_lang")
        if default_target:
            idx = self.target_combo.findData(default_target)
            if idx >= 0:
                self.target_combo.setCurrentIndex(idx)

    def _on_load_error(self, err: Exception):
        self._show_error(f"Couldn't reach the backend: {err}")

    def _prompt_login(self):
        dialog = LoginDialog(self)
        while True:
            if dialog.exec() != LoginDialog.DialogCode.Accepted:
                self._show_error("Password required to use this app.")
                return
            ok = self.api.login(dialog.password())
            if ok:
                self._clear_error()
                self._load_initial_data()
                return
            dialog.show_error("Incorrect password.")

    # --- file selection ---
    def _on_file_chosen(self, path: str):
        self.video_path = path
        self.drop_area.set_filename(Path(path).name)
        self.submit_button.setEnabled(True)

    # --- job submission ---
    def submit_job(self):
        if not self.video_path:
            return
        self._clear_error()
        self.submit_button.setEnabled(False)
        self.progress_frame.show()
        self.results_frame.hide()
        self.status_label.setText("Uploading...")
        self.progress_bar.setValue(0)
        self.eta_label.setText("")

        t = run_in_thread(
            self.api.create_job,
            self.video_path,
            self.model_combo.currentData(),
            self.source_combo.currentData(),
            self.target_combo.currentData(),
            self.diarize_check.isChecked(),
            "hardsub" if self.hardsub_radio.isChecked() else "softsub",
            on_finished=self._on_job_created,
            on_error=self._on_job_error,
            on_auth_required=self._prompt_login,
        )
        self._threads.append(t)

    def _on_job_created(self, job_id: str):
        self.job_id = job_id
        self.job_timer.start()

    def _on_job_error(self, err: Exception):
        self._show_error(f"Couldn't start the job: {err}")
        self.progress_frame.hide()
        self.submit_button.setEnabled(True)

    def _poll_job(self):
        if not self.job_id:
            self.job_timer.stop()
            return
        t = run_in_thread(self.api.get_job, self.job_id, on_finished=self._on_job_update, on_error=self._on_job_error)
        self._threads.append(t)

    def _on_job_update(self, job: dict):
        status = job.get("status")
        self.status_label.setText(STATUS_LABELS.get(status, status or ""))
        pct = job.get("percent")
        if pct is not None:
            self.progress_bar.setValue(int(pct))
        eta = format_eta(job.get("eta_seconds"))
        self.eta_label.setText(eta)

        if status not in ACTIVE_STATUSES:
            self.job_timer.stop()
            if status == "done":
                self.job_result = job
                self._show_results(job)
            elif status == "error":
                self._show_error(job.get("error") or "The job failed.")
                self.progress_frame.hide()
                self.submit_button.setEnabled(True)
            elif status == "cancelled":
                self.progress_frame.hide()
                self.submit_button.setEnabled(True)

    def cancel_job(self):
        if not self.job_id:
            return
        t = run_in_thread(self.api.cancel_job, self.job_id, on_finished=lambda _r: None, on_error=self._on_job_error)
        self._threads.append(t)

    # --- results ---
    def _show_results(self, job: dict):
        self.progress_frame.hide()
        self.results_frame.show()
        t = run_in_thread(self.api.get_transcript, self.job_id, on_finished=self._on_transcript_loaded, on_error=lambda e: None)
        self._threads.append(t)

    def _on_transcript_loaded(self, text: str):
        self.transcript_view.setPlainText(text)

    def _open_download(self):
        if self.job_id:
            QDesktopServices.openUrl(QUrl(self.api.download_url(self.job_id)))

    def _copy_transcript(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.transcript_view.toPlainText())

    def _apply_speaker_names(self):
        raw = self.speaker_names_edit.text().strip()
        if not raw or not self.job_id:
            return
        names = {}
        for pair in raw.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                names[k.strip()] = v.strip()
        t = run_in_thread(
            self.api.rename_speakers, self.job_id, names,
            on_finished=lambda _r: self._on_transcript_loaded_refresh(),
            on_error=self._on_job_error,
        )
        self._threads.append(t)

    def _on_transcript_loaded_refresh(self):
        t = run_in_thread(self.api.get_transcript, self.job_id, on_finished=self._on_transcript_loaded, on_error=lambda e: None)
        self._threads.append(t)

    def reset_for_new_job(self):
        self.job_id = None
        self.job_result = None
        self.video_path = None
        self.drop_area.set_filename("Click or drag a video file here")
        self.submit_button.setEnabled(False)
        self.results_frame.hide()
        self.progress_frame.hide()
        self._clear_error()

    # --- settings ---
    def open_settings(self):
        dialog = SettingsDialog(self.api, getattr(self, "models", []), self)
        dialog.exec()

    # --- log console ---
    def _toggle_log_console(self, checked: bool):
        if checked:
            self.log_view.show()
            self.log_toggle_button.setText("Hide backend log")
            self.log_timer.start()
        else:
            self.log_view.hide()
            self.log_toggle_button.setText("Show backend log")
            self.log_timer.stop()

    def _poll_logs(self):
        t = run_in_thread(self.api.get_logs, self._logs_since, on_finished=self._on_logs, on_error=lambda e: None)
        self._threads.append(t)

    def _on_logs(self, data: dict):
        lines = data.get("lines", [])
        self._logs_since = data.get("next_since", self._logs_since)
        for line in lines:
            self.log_view.appendPlainText(line)
        if lines:
            sb = self.log_view.verticalScrollBar()
            sb.setValue(sb.maximum())

    # --- window/tray behavior ---
    def closeEvent(self, event):
        event.ignore()
        self.hide()
