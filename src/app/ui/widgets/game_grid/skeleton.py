"""
Skeleton card widget for loading state.

Displays a placeholder card with shimmer animation while games are loading.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QWidget, QSizePolicy,
    QGraphicsOpacityEffect,
)
from PySide6.QtGui import QColor

from app.ui.theme import current_theme, card_style, is_reduced_motion


class SkeletonCard(QFrame):
    """Placeholder card shown during loading with animated shimmer effect."""

    def __init__(self, view_mode: str = "comfortable", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        theme = current_theme()
        pad = theme.spacing_md if view_mode == "comfortable" else theme.spacing_sm

        self.setStyleSheet(
            f"QFrame {{ {card_style(theme)} }}"
        )
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(200 if view_mode == "comfortable" else 150)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(pad, pad, pad, pad)
        layout.setSpacing(8)

        # Skeleton icon area
        icon_skeleton = QFrame()
        icon_skeleton.setStyleSheet(
            f"background: {theme.surface_alt.name(QColor.HexArgb)}; "
            f"border-radius: 12px;"
        )
        icon_ratio = 0.78 if view_mode == "comfortable" else 0.6
        icon_skeleton.setMinimumHeight(int(self.minimumHeight() * icon_ratio))
        layout.addWidget(icon_skeleton)

        # Skeleton title
        title_skeleton = QFrame()
        title_skeleton.setFixedHeight(16)
        title_skeleton.setStyleSheet(
            f"background: {theme.surface_alt.lighter(105).name(QColor.HexArgb)}; "
            f"border-radius: 4px;"
        )
        layout.addWidget(title_skeleton)

        # Skeleton subtitle
        subtitle_skeleton = QFrame()
        subtitle_skeleton.setFixedHeight(12)
        subtitle_skeleton.setFixedWidth(120)
        subtitle_skeleton.setStyleSheet(
            f"background: {theme.surface_alt.name(QColor.HexArgb)}; "
            f"border-radius: 3px;"
        )
        layout.addWidget(subtitle_skeleton)

        layout.addStretch(1)

        # Pulse animation for shimmer effect (respects reduced motion)
        self._pulse_anim: Optional[QPropertyAnimation] = None
        if not is_reduced_motion():
            self._opacity = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(self._opacity)
            self._pulse_anim = QPropertyAnimation(self._opacity, b"opacity", self)
            self._pulse_anim.setDuration(1200)
            self._pulse_anim.setStartValue(0.4)
            self._pulse_anim.setEndValue(0.8)
            self._pulse_anim.setEasingCurve(QEasingCurve.InOutSine)
            self._pulse_anim.setLoopCount(-1)  # Infinite loop
            self._pulse_anim.start()

    def stop_animation(self) -> None:
        """Stop the shimmer animation."""
        if self._pulse_anim:
            self._pulse_anim.stop()
