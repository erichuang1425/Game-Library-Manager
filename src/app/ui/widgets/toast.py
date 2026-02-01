"""Toast notification system for non-modal feedback messages."""
from __future__ import annotations
from typing import Optional, List
from enum import Enum

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QPushButton, QGraphicsOpacityEffect, QApplication
)
from PySide6.QtGui import QColor

from app.ui.theme import current_theme


class ToastType(Enum):
    SUCCESS = "success"
    ERROR = "error"
    INFO = "info"
    WARNING = "warning"


class Toast(QWidget):
    """A single toast notification widget."""

    def __init__(
        self,
        message: str,
        toast_type: ToastType = ToastType.INFO,
        duration_ms: int = 4000,
        action_text: Optional[str] = None,
        action_callback: Optional[callable] = None,
        parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._duration_ms = duration_ms
        self._action_callback = action_callback

        theme = current_theme()

        # Colors based on toast type
        colors = {
            ToastType.SUCCESS: (QColor(46, 160, 67), "✓"),
            ToastType.ERROR: (QColor(218, 54, 51), "✕"),
            ToastType.INFO: (theme.accent, "ℹ"),
            ToastType.WARNING: (QColor(255, 152, 0), "⚠"),
        }
        bg_color, icon = colors.get(toast_type, (theme.accent, "ℹ"))

        # Container styling
        self.setStyleSheet(
            f"QWidget {{ "
            f"background: {theme.surface.name(QColor.HexArgb)}; "
            f"border: 1px solid {theme.outline.name(QColor.HexArgb)}; "
            f"border-radius: {theme.radius_md}px; "
            f"}} "
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        # Icon
        icon_label = QLabel(icon)
        icon_label.setStyleSheet(
            f"color: {bg_color.name()}; font-size: 16px; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(icon_label)

        # Message
        msg_label = QLabel(message)
        msg_label.setStyleSheet(
            f"color: {theme.text.name()}; font-size: 13px; "
            f"background: transparent; border: none;"
        )
        msg_label.setWordWrap(True)
        msg_label.setMaximumWidth(300)
        layout.addWidget(msg_label, 1)

        # Optional action button
        if action_text and action_callback:
            action_btn = QPushButton(action_text)
            action_btn.setStyleSheet(
                f"QPushButton {{ "
                f"color: {theme.accent.name()}; "
                f"background: transparent; "
                f"border: none; "
                f"font-weight: 600; "
                f"font-size: 12px; "
                f"padding: 4px 8px; "
                f"}} "
                f"QPushButton:hover {{ text-decoration: underline; }}"
            )
            action_btn.setCursor(Qt.PointingHandCursor)
            action_btn.clicked.connect(self._on_action)
            layout.addWidget(action_btn)

        # Close button
        close_btn = QPushButton("×")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet(
            f"QPushButton {{ "
            f"color: {theme.text_muted.name()}; "
            f"background: transparent; "
            f"border: none; "
            f"font-size: 16px; "
            f"font-weight: bold; "
            f"}} "
            f"QPushButton:hover {{ color: {theme.text.name()}; }}"
        )
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.dismiss)
        layout.addWidget(close_btn)

        # Opacity effect for animations
        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._opacity.setOpacity(0.0)

        # Animation for fade in/out
        self._fade_anim = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade_anim.setDuration(200)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)

        # Auto-dismiss timer
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self.dismiss)

        self.adjustSize()

    def show_toast(self) -> None:
        """Show the toast with fade-in animation."""
        self.show()
        self._fade_anim.stop()
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

        if self._duration_ms > 0:
            self._dismiss_timer.start(self._duration_ms)

    def dismiss(self) -> None:
        """Dismiss the toast with fade-out animation."""
        self._dismiss_timer.stop()
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self._opacity.opacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.finished.connect(self._on_fade_out_done)
        self._fade_anim.start()

    def _on_fade_out_done(self) -> None:
        """Clean up after fade out."""
        self.hide()
        self.deleteLater()

    def _on_action(self) -> None:
        """Handle action button click."""
        if self._action_callback:
            self._action_callback()
        self.dismiss()


class ToastManager:
    """Manages toast notifications for the application."""

    _instance: Optional["ToastManager"] = None
    _toasts: List[Toast] = []
    _margin: int = 16
    _spacing: int = 8

    @classmethod
    def instance(cls) -> "ToastManager":
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def show(
        self,
        message: str,
        toast_type: ToastType = ToastType.INFO,
        duration_ms: int = 4000,
        action_text: Optional[str] = None,
        action_callback: Optional[callable] = None,
    ) -> Toast:
        """Show a toast notification.

        Args:
            message: The message to display
            toast_type: Type of toast (affects color/icon)
            duration_ms: How long to show (0 for persistent)
            action_text: Optional action button text
            action_callback: Callback when action is clicked

        Returns:
            The created Toast widget
        """
        # Get main window as parent
        app = QApplication.instance()
        main_window = None
        if app:
            for widget in app.topLevelWidgets():
                if widget.isVisible() and hasattr(widget, 'centralWidget'):
                    main_window = widget
                    break

        toast = Toast(
            message=message,
            toast_type=toast_type,
            duration_ms=duration_ms,
            action_text=action_text,
            action_callback=action_callback,
            parent=None  # Top-level
        )

        # Position toast in bottom-right corner
        self._position_toast(toast, main_window)

        # Track and show
        self._toasts.append(toast)
        toast.show_toast()

        # Remove from list when dismissed
        toast.destroyed.connect(lambda: self._remove_toast(toast))

        return toast

    def _position_toast(self, toast: Toast, main_window: Optional[QWidget]) -> None:
        """Position the toast in the bottom-right corner."""
        if main_window:
            # Position relative to main window
            window_rect = main_window.geometry()
            x = window_rect.right() - toast.width() - self._margin
            y = window_rect.bottom() - toast.height() - self._margin

            # Stack above existing toasts
            for existing in self._toasts:
                if existing.isVisible():
                    y -= existing.height() + self._spacing
        else:
            # Fallback to screen
            screen = QApplication.primaryScreen()
            if screen:
                rect = screen.availableGeometry()
                x = rect.right() - toast.width() - self._margin
                y = rect.bottom() - toast.height() - self._margin
            else:
                x, y = 100, 100

        toast.move(x, y)

    def _remove_toast(self, toast: Toast) -> None:
        """Remove a toast from tracking."""
        if toast in self._toasts:
            self._toasts.remove(toast)

    def clear_all(self) -> None:
        """Dismiss all active toasts."""
        for toast in list(self._toasts):
            toast.dismiss()


# Convenience functions
def show_success(message: str, duration_ms: int = 4000, action_text: str = None, action_callback: callable = None) -> Toast:
    """Show a success toast."""
    return ToastManager.instance().show(message, ToastType.SUCCESS, duration_ms, action_text, action_callback)


def show_error(message: str, duration_ms: int = 6000, action_text: str = None, action_callback: callable = None) -> Toast:
    """Show an error toast."""
    return ToastManager.instance().show(message, ToastType.ERROR, duration_ms, action_text, action_callback)


def show_info(message: str, duration_ms: int = 4000, action_text: str = None, action_callback: callable = None) -> Toast:
    """Show an info toast."""
    return ToastManager.instance().show(message, ToastType.INFO, duration_ms, action_text, action_callback)


def show_warning(message: str, duration_ms: int = 5000, action_text: str = None, action_callback: callable = None) -> Toast:
    """Show a warning toast."""
    return ToastManager.instance().show(message, ToastType.WARNING, duration_ms, action_text, action_callback)
