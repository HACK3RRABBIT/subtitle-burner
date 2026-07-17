from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from subtitleburner_gui.constants import LANGUAGES, model_label
from subtitleburner_gui.workers import run_in_thread


def _lang_combo(placeholder: str) -> QComboBox:
    combo = QComboBox()
    combo.addItem(placeholder, "")
    for code, label in LANGUAGES:
        combo.addItem(label, code)
    return combo


def _set_combo_value(combo: QComboBox, value: str):
    idx = combo.findData(value or "")
    combo.setCurrentIndex(idx if idx >= 0 else 0)


class SettingsDialog(QDialog):
    def __init__(self, api, models: list[str], parent=None):
        super().__init__(parent)
        self.api = api
        self.models = models
        self._threads = []

        self.setWindowTitle("Settings")
        self.resize(480, 560)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Saved locally and reused as defaults for new jobs."))

        tabs = QTabWidget()
        layout.addWidget(tabs, stretch=1)

        # --- Access tab ---
        access = QWidget()
        access_form = QFormLayout(access)
        self.hf_token_edit = QLineEdit()
        self.hf_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.hf_token_edit.setPlaceholderText("For speaker separation")
        self.hf_token_hint = QLabel()
        self.hf_token_hint.setWordWrap(True)
        access_form.addRow("Hugging Face token", self.hf_token_edit)
        access_form.addRow("", self.hf_token_hint)

        self.app_password_edit = QLineEdit()
        self.app_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.app_password_edit.setPlaceholderText("Protects this app once reachable off this PC")
        self.app_password_hint = QLabel()
        self.app_password_hint.setWordWrap(True)
        access_form.addRow("App password", self.app_password_edit)
        access_form.addRow("", self.app_password_hint)
        tabs.addTab(access, "Access")

        # --- Defaults tab ---
        defaults = QWidget()
        defaults_form = QFormLayout(defaults)
        self.default_model_combo = QComboBox()
        for m in self.models:
            self.default_model_combo.addItem(model_label(m), m)
        defaults_form.addRow("Default Whisper model", self.default_model_combo)

        self.default_source_combo = _lang_combo("Auto-detect")
        defaults_form.addRow("Spoken language", self.default_source_combo)
        self.default_target_combo = _lang_combo("No translation")
        defaults_form.addRow("Subtitle language", self.default_target_combo)

        self.force_cpu_check = QCheckBox("Skip GPU/CUDA - useful if GPU transcription ever misbehaves")
        defaults_form.addRow("Force CPU-only", self.force_cpu_check)
        tabs.addTab(defaults, "Defaults")

        # --- Server tab ---
        server = QWidget()
        server_form = QFormLayout(server)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(8000)
        server_form.addRow("Port", self.port_spin)
        server_form.addRow("", QLabel("Requires restarting the app to take effect."))
        tabs.addTab(server, "Server")

        # --- Memory tab ---
        memory = QWidget()
        memory_layout = QVBoxLayout(memory)
        self.memory_list = QListWidget()
        memory_layout.addWidget(self.memory_list)
        memory_layout.addWidget(QLabel(
            "Loaded models stay resident (GPU/RAM) between jobs so the next one starts "
            "faster. Unload them to free that memory for other apps - they reload "
            "automatically next time they're needed."
        ))
        unload_row = QHBoxLayout()
        self.unload_button = QPushButton("Unload models")
        self.unload_button.clicked.connect(self._unload_models)
        unload_row.addWidget(self.unload_button)
        unload_row.addStretch(1)
        memory_layout.addLayout(unload_row)
        self.memory_status_label = QLabel("")
        memory_layout.addWidget(self.memory_status_label)
        memory_layout.addStretch(1)
        tabs.addTab(memory, "Memory")

        # --- Footer ---
        footer = QHBoxLayout()
        self.status_label = QLabel("")
        footer.addWidget(self.status_label)
        footer.addStretch(1)
        self.logout_button = QPushButton("Log out")
        self.logout_button.clicked.connect(self._logout)
        self.logout_button.hide()
        footer.addWidget(self.logout_button)
        self.save_button = QPushButton("Save settings")
        self.save_button.clicked.connect(self._save)
        footer.addWidget(self.save_button)
        layout.addLayout(footer)

        self._hf_token_set = False
        self._app_password_set = False
        self._load_settings()
        self._load_memory()

    # --- data loading ---
    def _load_settings(self):
        t = run_in_thread(self.api.get_settings, on_finished=self._on_settings_loaded, on_error=self._on_error)
        self._threads.append(t)

    def _on_settings_loaded(self, s: dict):
        self._hf_token_set = bool(s.get("hf_token_set"))
        self._app_password_set = bool(s.get("app_password_set"))
        self.hf_token_hint.setText(
            "A token is currently saved. Leave blank to keep it, or enter a new one to replace it."
            if self._hf_token_set else "No token saved yet. Required for speaker separation."
        )
        self.app_password_hint.setText(
            "A password is currently set. Leave blank to keep it, enter a new one to replace it, "
            "or save empty to remove it."
            if self._app_password_set else "No password set - anyone who can reach this app over the network can use it."
        )
        _set_combo_value(self.default_model_combo, s.get("default_model") or "")
        _set_combo_value(self.default_source_combo, s.get("default_source_lang") or "")
        _set_combo_value(self.default_target_combo, s.get("default_lang") or "")
        self.force_cpu_check.setChecked(bool(s.get("force_cpu")))
        self.port_spin.setValue(int(s.get("port") or 8000))
        self.logout_button.setVisible(self._app_password_set)

    def _load_memory(self):
        t = run_in_thread(self.api.get_loaded_models, on_finished=self._on_memory_loaded, on_error=self._on_error)
        self._threads.append(t)

    def _on_memory_loaded(self, data: dict):
        self.memory_list.clear()
        whisper_models = data.get("whisper_models", [])
        diarization_loaded = data.get("diarization_loaded", False)
        if not whisper_models and not diarization_loaded:
            self.memory_list.addItem("No models currently loaded in memory.")
            self.unload_button.setEnabled(False)
        else:
            for m in whisper_models:
                self.memory_list.addItem(f"Whisper {m['model_size']} — {m['device']}")
            if diarization_loaded:
                self.memory_list.addItem("Speaker-diarization pipeline")
            self.unload_button.setEnabled(True)

    def _unload_models(self):
        self.memory_status_label.setText("Unloading...")
        t = run_in_thread(self.api.unload_models, on_finished=self._on_unloaded, on_error=self._on_error)
        self._threads.append(t)

    def _on_unloaded(self, _result):
        self.memory_status_label.setText("Models unloaded - memory freed.")
        self._load_memory()

    # --- save/logout ---
    def _save(self):
        body = {
            "default_model": self.default_model_combo.currentData(),
            "default_lang": self.default_target_combo.currentData(),
            "default_source_lang": self.default_source_combo.currentData(),
            "force_cpu": self.force_cpu_check.isChecked(),
            "port": self.port_spin.value(),
        }
        if self.hf_token_edit.text().strip():
            body["hf_token"] = self.hf_token_edit.text().strip()
        if self.app_password_edit.text().strip():
            body["app_password"] = self.app_password_edit.text().strip()

        self.status_label.setText("Saving...")
        t = run_in_thread(self.api.update_settings, body, on_finished=self._on_saved, on_error=self._on_error)
        self._threads.append(t)

    def _on_saved(self, s: dict):
        was_unset = not self._app_password_set
        self._hf_token_set = bool(s.get("hf_token_set"))
        self._app_password_set = bool(s.get("app_password_set"))
        self.hf_token_edit.clear()
        self.app_password_edit.clear()
        self.logout_button.setVisible(self._app_password_set)
        if was_unset and self._app_password_set:
            self.status_label.setText("Saved. You'll need that password next time this app starts.")
        else:
            self.status_label.setText("Saved.")

    def _logout(self):
        # Native GUI convenience only - clears this session so the next
        # protected call re-prompts via LoginDialog, mirroring the web UI's
        # logout button.
        t = run_in_thread(lambda: self.api.client.post("/api/auth/logout"),
                           on_finished=lambda _r: self.status_label.setText("Logged out."),
                           on_error=self._on_error)
        self._threads.append(t)

    def _on_error(self, err: Exception):
        self.status_label.setText(str(err))
