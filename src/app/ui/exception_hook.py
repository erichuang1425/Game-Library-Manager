from __future__ import annotations
"""
Crash capture and exception hooks for the Manager UI.

- sys.excepthook + threading.excepthook -> log to manager.log
- Qt event/slot exceptions are caught via SafeApplication.notify
- Optional non-modal dialog to inform the user
"""

import sys
import threading
import traceback
from pathlib import Path
from typing import Optional
from contextlib import suppress

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt, QTimer

from app.logging_utils import get_logger, kv, RateLimiter

_log = get_logger("crash")
_dialog_rate = RateLimiter()
_dialog_lock = threading.Lock()  # Thread-safe dialog flag protection
_dialog_shown = False
_notify_guard = threading.local()  # prevents re-entrancy


def _fallback_write(text: str) -> None:
    """
    Last-resort path: write straight to stderr and a temp log file without logging module.
    """
    with suppress(Exception):
        sys.__stderr__.write(text + "\n")
    try:
        base = Path.home() / "AppData" / "Roaming" / "GameLibraryManager" / "logs"
        base.mkdir(parents=True, exist_ok=True)
        f = base / "crash_fallback.log"
        with f.open("a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    except Exception:
        pass


def _log_exception(exc_type, exc_value, exc_tb, origin: str, context: Optional[str] = None) -> None:
    if getattr(_notify_guard, "active", False):
        # already handling an exception; avoid recursion
        _fallback_write(f"[fallback] unhandled_exception origin={origin} context={context} err={exc_value}")
        return
    _notify_guard.active = True
    try:
        tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        _log.critical("unhandled_exception %s\n%s", kv(origin=origin, context=context), tb)
        _show_dialog(origin)
    except RecursionError as e:
        # If the stack is already exhausted, avoid further logging recursion.
        _fallback_write(f"[fallback] recursion_error origin={origin} context={context} err={e}")
    except Exception as e:  # logging itself failed
        _fallback_write(f"[fallback] logging_failed origin={origin} context={context} err={e}")
    finally:
        _notify_guard.active = False


def _show_dialog(origin: str) -> None:
    """
    Best-effort, non-blocking error notification to the user.
    Thread-safe: uses lock to prevent multiple dialogs from concurrent exceptions.
    """
    global _dialog_shown

    # Thread-safe check-and-set with lock
    with _dialog_lock:
        if _dialog_shown or not _dialog_rate.allow("fatal_dialog", interval_ms=2000):
            return
        _dialog_shown = True

    app = QApplication.instance()
    if app is None:
        # Reset flag if we can't show dialog
        with _dialog_lock:
            _dialog_shown = False
        return

    def _do():
        global _dialog_shown
        # Double-check under lock (may have been reset by timeout)
        with _dialog_lock:
            if not _dialog_shown:
                return

        box = QMessageBox(QMessageBox.Critical, "Fatal error", "A fatal error occurred. See manager.log.", QMessageBox.Ok)
        box.setWindowModality(Qt.NonModal)
        box.setAttribute(Qt.WA_DeleteOnClose)
        box.show()

        # Allow subsequent dialogs only after this one closes
        def _reset():
            global _dialog_shown
            with _dialog_lock:
                _dialog_shown = False
        box.finished.connect(_reset)

    QTimer.singleShot(0, _do)


class SafeApplication(QApplication):
    """
    QApplication subclass that captures exceptions from event dispatch / Qt slots.
    """
    def notify(self, receiver, event):
        try:
            return super().notify(receiver, event)
        except Exception as exc:
            _log_exception(
                type(exc),
                exc,
                exc.__traceback__,
                origin="qt_notify",
                context=kv(
                    receiver=getattr(receiver, '__class__', type(receiver)).__name__,
                    event=getattr(event, '__class__', type(event)).__name__,
                ),
            )
            return False


def install() -> None:
    """
    Install global hooks for uncaught exceptions.
    """
    def _sys_hook(exc_type, exc_value, exc_tb):
        _log_exception(exc_type, exc_value, exc_tb, origin="sys")

    sys.excepthook = _sys_hook

    if hasattr(threading, "excepthook"):
        def _thread_hook(args):
            _log_exception(args.exc_type, args.exc_value, args.exc_traceback, origin="thread")
        threading.excepthook = _thread_hook

    if hasattr(sys, "unraisablehook"):
        def _unraisable_hook(unraisable):
            _log_exception(type(unraisable.exc_value), unraisable.exc_value, unraisable.exc_traceback, origin="unraisable")
        sys.unraisablehook = _unraisable_hook
