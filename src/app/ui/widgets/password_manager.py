"""
Password Manager Widget for archive extraction.

Provides a reusable widget for managing custom archive extraction passwords.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QGroupBox, QTextEdit, QListWidget, QCheckBox
)

from app.services import (
    get_custom_passwords, add_custom_password,
    remove_custom_password, load_custom_passwords
)


class PasswordManagerWidget(QWidget):
    """
    Widget for managing custom archive extraction passwords.

    Displays:
    - List of custom passwords (masked)
    - Input field to add new passwords
    - Remove button for selected password
    - Read-only list of built-in common passwords
    """

    passwords_changed = Signal()  # Emitted when password list changes

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._connect_signals()

        # Load existing passwords
        load_custom_passwords()
        self._refresh_passwords_list()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Info label
        info = QLabel(
            "Common F95zone passwords are automatically tried.\n"
            "Add your own custom passwords below for encrypted archives."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # Custom passwords group
        pwd_group = QGroupBox("Custom Passwords")
        pwd_layout = QVBoxLayout(pwd_group)

        # Password list
        self.passwords_list = QListWidget()
        pwd_layout.addWidget(self.passwords_list, 1)

        # Add password row
        add_row = QHBoxLayout()

        self.new_password_edit = QLineEdit()
        self.new_password_edit.setPlaceholderText("Enter new password...")
        self.new_password_edit.setEchoMode(QLineEdit.Password)
        add_row.addWidget(self.new_password_edit, 1)

        self.show_password_check = QCheckBox("Show")
        add_row.addWidget(self.show_password_check)

        self.add_btn = QPushButton("Add")
        add_row.addWidget(self.add_btn)

        self.remove_btn = QPushButton("Remove Selected")
        add_row.addWidget(self.remove_btn)

        pwd_layout.addLayout(add_row)
        layout.addWidget(pwd_group, 1)

        # Built-in passwords (read-only reference)
        common_group = QGroupBox("Built-in Passwords (read-only)")
        common_layout = QVBoxLayout(common_group)
        common_list = QTextEdit()
        common_list.setReadOnly(True)
        common_list.setPlainText(
            "f95zone\nf95\nwww.f95zone.to\nf95zone.to\n"
            "www.f95zone.com\nf95zone.com\n(empty)"
        )
        common_list.setMaximumHeight(120)
        common_layout.addWidget(common_list)
        layout.addWidget(common_group)

    def _connect_signals(self):
        self.show_password_check.toggled.connect(self._toggle_password_visibility)
        self.add_btn.clicked.connect(self._add_password)
        self.remove_btn.clicked.connect(self._remove_password)
        self.new_password_edit.returnPressed.connect(self._add_password)

    def _refresh_passwords_list(self):
        """Refresh the passwords list widget."""
        self.passwords_list.clear()
        for pwd in get_custom_passwords():
            self.passwords_list.addItem("*" * len(pwd))

    def _toggle_password_visibility(self, show: bool):
        self.new_password_edit.setEchoMode(
            QLineEdit.Normal if show else QLineEdit.Password
        )

    def _add_password(self):
        pwd = self.new_password_edit.text().strip()
        if pwd:
            add_custom_password(pwd)
            self._refresh_passwords_list()
            self.new_password_edit.clear()
            self.passwords_changed.emit()

    def _remove_password(self):
        row = self.passwords_list.currentRow()
        if row >= 0:
            passwords = get_custom_passwords()
            if row < len(passwords):
                remove_custom_password(passwords[row])
                self._refresh_passwords_list()
                self.passwords_changed.emit()

    def get_custom_passwords(self):
        """Get the current list of custom passwords."""
        return get_custom_passwords()
