from __future__ import annotations
"""
F95zone Login Dialog for Game Library Manager.
"""

from typing import Optional

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QFrame, QMessageBox, QProgressBar
)

from app.services.f95_auth import get_auth_manager, AuthResult
from app.logging_utils import get_logger, kv
from app.ui.theme import current_theme

_log = get_logger("ui.login")


class LoginWorker(QThread):
    """Worker thread for login operation."""

    finished = Signal(object)  # AuthResult

    def __init__(
        self,
        username: str,
        password: str,
        remember: bool,
        save_credentials: bool,
        parent: Optional[QThread] = None
    ) -> None:
        super().__init__(parent)
        self.username = username
        self.password = password
        self.remember = remember
        self.save_credentials = save_credentials

    def run(self) -> None:
        auth = get_auth_manager()
        result = auth.login(
            self.username,
            self.password,
            remember=self.remember,
            save_credentials=self.save_credentials,
        )
        self.finished.emit(result)


class F95LoginDialog(QDialog):
    """
    Dialog for logging into F95zone.
    """

    login_successful = Signal(str)  # username

    def __init__(self, parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self._theme = current_theme()
        self._worker: Optional[LoginWorker] = None

        self.setWindowTitle("F95zone Login")
        self.setModal(True)
        self.setMinimumWidth(400)

        self._setup_ui()
        self._load_saved_credentials()

    def _setup_ui(self) -> None:
        theme = self._theme

        layout = QVBoxLayout(self)
        layout.setSpacing(theme.spacing_md)
        layout.setContentsMargins(theme.spacing_lg, theme.spacing_lg, theme.spacing_lg, theme.spacing_lg)

        # Title
        title = QLabel("Sign in to F95zone")
        title.setStyleSheet(f"font-size: 18px; font-weight: 600; color: {theme.text.name(QColor.HexArgb)};")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Description
        desc = QLabel("Log in to access member-only features like watched threads and download links.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {theme.text_muted.name(QColor.HexArgb)};")
        desc.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc)

        layout.addSpacing(theme.spacing_sm)

        # Username field
        username_label = QLabel("Username")
        username_label.setStyleSheet(f"color: {theme.text.name(QColor.HexArgb)}; font-weight: 500;")
        layout.addWidget(username_label)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter your F95zone username")
        self.username_input.setMinimumHeight(36)
        self.username_input.setStyleSheet(f"""
            QLineEdit {{
                background: {theme.surface.name(QColor.HexArgb)};
                border: 1px solid {theme.border.name(QColor.HexArgb)};
                border-radius: {theme.radius_sm}px;
                padding: 8px;
                color: {theme.text.name(QColor.HexArgb)};
            }}
            QLineEdit:focus {{
                border-color: {theme.accent.name(QColor.HexArgb)};
            }}
        """)
        layout.addWidget(self.username_input)

        # Password field
        password_label = QLabel("Password")
        password_label.setStyleSheet(f"color: {theme.text.name(QColor.HexArgb)}; font-weight: 500;")
        layout.addWidget(password_label)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Enter your password")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setMinimumHeight(36)
        self.password_input.setStyleSheet(self.username_input.styleSheet())
        self.password_input.returnPressed.connect(self._on_login_clicked)
        layout.addWidget(self.password_input)

        # Options
        options_row = QHBoxLayout()

        self.remember_check = QCheckBox("Keep me logged in")
        self.remember_check.setChecked(True)
        self.remember_check.setStyleSheet(f"color: {theme.text.name(QColor.HexArgb)};")
        options_row.addWidget(self.remember_check)

        self.save_credentials_check = QCheckBox("Save credentials")
        self.save_credentials_check.setChecked(False)
        self.save_credentials_check.setToolTip("Save username and password for auto-login (encrypted)")
        self.save_credentials_check.setStyleSheet(f"color: {theme.text.name(QColor.HexArgb)};")
        options_row.addWidget(self.save_credentials_check)

        options_row.addStretch(1)
        layout.addLayout(options_row)

        # Error message
        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(f"color: {theme.error.name(QColor.HexArgb)};")
        self.error_label.hide()
        layout.addWidget(self.error_label)

        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        layout.addSpacing(theme.spacing_sm)

        # Buttons
        buttons_row = QHBoxLayout()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(36)
        self.cancel_btn.clicked.connect(self.reject)
        buttons_row.addWidget(self.cancel_btn)

        buttons_row.addStretch(1)

        self.login_btn = QPushButton("Sign In")
        self.login_btn.setMinimumHeight(36)
        self.login_btn.setMinimumWidth(100)
        self.login_btn.setStyleSheet(f"""
            QPushButton {{
                background: {theme.accent.name(QColor.HexArgb)};
                color: white;
                border: none;
                border-radius: {theme.radius_sm}px;
                padding: 8px 16px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {theme.accent.darker(110).name(QColor.HexArgb)};
            }}
            QPushButton:disabled {{
                background: {theme.border.name(QColor.HexArgb)};
            }}
        """)
        self.login_btn.clicked.connect(self._on_login_clicked)
        buttons_row.addWidget(self.login_btn)

        layout.addLayout(buttons_row)

        # Security note
        security_note = QLabel("Your credentials are encrypted and stored locally.")
        security_note.setStyleSheet(f"color: {theme.text_muted.name(QColor.HexArgb)}; font-size: 11px;")
        security_note.setAlignment(Qt.AlignCenter)
        layout.addWidget(security_note)

    def _load_saved_credentials(self) -> None:
        """Load saved credentials if available."""
        auth = get_auth_manager()
        creds = auth.load_credentials()
        if creds:
            username, password = creds
            self.username_input.setText(username)
            self.password_input.setText(password)
            self.save_credentials_check.setChecked(True)

    def _on_login_clicked(self) -> None:
        """Handle login button click."""
        username = self.username_input.text().strip()
        password = self.password_input.text()

        if not username:
            self.error_label.setText("Please enter your username.")
            self.error_label.show()
            self.username_input.setFocus()
            return

        if not password:
            self.error_label.setText("Please enter your password.")
            self.error_label.show()
            self.password_input.setFocus()
            return

        self.error_label.hide()
        self._set_loading(True)

        # Start login in background
        self._worker = LoginWorker(
            username=username,
            password=password,
            remember=self.remember_check.isChecked(),
            save_credentials=self.save_credentials_check.isChecked(),
        )
        self._worker.finished.connect(self._on_login_finished)
        self._worker.start()

    def _on_login_finished(self, result: AuthResult) -> None:
        """Handle login completion."""
        self._set_loading(False)

        if result.success:
            _log.info("login_dialog_success %s", kv(username=result.username))
            self.login_successful.emit(result.username)
            self.accept()
        else:
            _log.warning("login_dialog_failed %s", kv(error=result.error_code, message=result.message))

            if result.requires_2fa:
                self.error_label.setText(
                    "Two-factor authentication is enabled on your account. "
                    "Please disable it temporarily or use the website directly."
                )
            else:
                self.error_label.setText(result.message or "Login failed. Please check your credentials.")

            self.error_label.show()

    def _set_loading(self, loading: bool) -> None:
        """Set loading state."""
        self.login_btn.setEnabled(not loading)
        self.cancel_btn.setEnabled(not loading)
        self.username_input.setEnabled(not loading)
        self.password_input.setEnabled(not loading)
        self.remember_check.setEnabled(not loading)
        self.save_credentials_check.setEnabled(not loading)

        if loading:
            self.progress_bar.show()
            self.login_btn.setText("Signing in...")
        else:
            self.progress_bar.hide()
            self.login_btn.setText("Sign In")


class ConnectionStatusWidget(QFrame):
    """
    Small widget showing F95zone connection status.
    Can be placed in toolbar or status bar.
    """

    login_requested = Signal()
    logout_requested = Signal()

    def __init__(self, parent: Optional[QFrame] = None) -> None:
        super().__init__(parent)
        self._theme = current_theme()
        self._setup_ui()
        self._update_status()

    def _setup_ui(self) -> None:
        theme = self._theme

        layout = QHBoxLayout(self)
        layout.setContentsMargins(theme.spacing_xs, theme.spacing_xs, theme.spacing_xs, theme.spacing_xs)
        layout.setSpacing(theme.spacing_xs)

        # Status indicator
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet(f"color: {theme.text_muted.name(QColor.HexArgb)};")
        layout.addWidget(self.status_dot)

        # Status text
        self.status_label = QLabel("Not connected")
        self.status_label.setStyleSheet(f"color: {theme.text_muted.name(QColor.HexArgb)}; font-size: 11px;")
        layout.addWidget(self.status_label)

        # Action button
        self.action_btn = QPushButton("Sign In")
        self.action_btn.setFixedHeight(24)
        self.action_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {theme.accent.name(QColor.HexArgb)};
                border: 1px solid {theme.accent.name(QColor.HexArgb)};
                border-radius: {theme.radius_sm}px;
                padding: 2px 8px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: {theme.accent.name(QColor.HexArgb)};
                color: white;
            }}
        """)
        self.action_btn.clicked.connect(self._on_action_clicked)
        layout.addWidget(self.action_btn)

    def _update_status(self) -> None:
        """Update status display."""
        theme = self._theme
        auth = get_auth_manager()

        if auth.is_authenticated():
            session = auth.get_session_info()
            self.status_dot.setStyleSheet(f"color: {theme.success.name(QColor.HexArgb)};")
            self.status_label.setText(f"Signed in as {session.username}")
            self.status_label.setStyleSheet(f"color: {theme.text.name(QColor.HexArgb)}; font-size: 11px;")
            self.action_btn.setText("Sign Out")
        else:
            self.status_dot.setStyleSheet(f"color: {theme.text_muted.name(QColor.HexArgb)};")
            self.status_label.setText("Not connected")
            self.status_label.setStyleSheet(f"color: {theme.text_muted.name(QColor.HexArgb)}; font-size: 11px;")
            self.action_btn.setText("Sign In")

    def _on_action_clicked(self) -> None:
        """Handle action button click."""
        auth = get_auth_manager()
        if auth.is_authenticated():
            auth.logout()
            self._update_status()
            self.logout_requested.emit()
        else:
            self.login_requested.emit()

    def refresh_status(self) -> None:
        """Refresh the status display."""
        self._update_status()
