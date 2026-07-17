from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)


class LoginDialog(QDialog):
    """Shown reactively whenever the backend returns 401 - this instance has
    an app_password set (meant to protect LAN/web access), which also gates
    this native client since the backend can't tell a local first-party GUI
    apart from anyone else. Mirrors the web UI's redirect-to-/login."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Subtitle Burner - Password required")
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("This app is password-protected. Enter the password to continue:"))

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.returnPressed.connect(self.accept)
        layout.addWidget(self.password_edit)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #d33;")
        self.error_label.hide()
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def password(self) -> str:
        return self.password_edit.text()

    def show_error(self, message: str):
        self.error_label.setText(message)
        self.error_label.show()
