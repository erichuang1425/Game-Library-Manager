from __future__ import annotations
"""
Centralized logging utilities for the Manager app.

- Rotates `manager.log` to avoid runaway growth.
- Structured key/value helpers for consistent context (event=, game_id=, w=, h=, etc).
- Timing helpers to capture duration in ms.
- Lightweight rate limiter to avoid log spam on rapid events (e.g., resize).
- Safe slot wrapper to surface exceptions from Qt callbacks.

Debug verbosity can be raised by setting env var `GLM_DEBUG=1` or `GLM_LOG_LEVEL=DEBUG`.

# Logging guide (conventions)
# - Always use get_logger(...) from this module; avoid print().
# - Use kv(...) to attach fields:
#     * event=phase/action (e.g., event=startup, event=nav_change, event=scan_run)
#     * ui/layout: view=grid/main, w=, h=, cols=, duration_ms=
#     * data: game_id=, game_title=, path=, url=, count=, status=
# - Log start/done/error pairs with *_start / *_done / *_error suffixes, include duration_ms on completion.
# - Slot/thread/timer callbacks should be wrapped with wrap_slot(logger, "label") so exceptions are logged with tracebacks.
"""

import logging
import logging.handlers
import os
import time
import tempfile
from pathlib import Path
from typing import Any, Callable, Tuple
from functools import wraps
from datetime import datetime

from app.storage.paths import get_app_dir
from contextlib import suppress

_LOG_MESSAGE_SHOWN = False


def _select_log_dir() -> Tuple[Path, bool, str]:
    attempts = []
    env_dir = os.environ.get("GLM_LOG_DIR")
    if env_dir:
        p = Path(env_dir)
        return p, False, "env_glm_log_dir"
    # prefer roaming
    try:
        roam = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        p = roam / "GameLibraryManager" / "logs"
        return p, False, "appdata"
    except Exception as e:
        attempts.append(f"appdata:{e}")
    try:
        local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        p = local / "GameLibraryManager" / "logs"
        return p, True, "localappdata"
    except Exception as e:
        attempts.append(f"local:{e}")
    temp = Path(tempfile.gettempdir()) / "GameLibraryManager" / "logs"
    return temp, True, ";".join(attempts) or "temp"


def _select_log_path() -> Tuple[Path, bool, str]:
    """
    Per-launch log file with timestamp; ensures directory exists and cleans retention.
    """
    folder, fb, reason = _select_log_dir()
    folder.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = folder / f"manager_{ts}.log"

    # retention: keep latest 20 files
    logs = sorted(folder.glob("manager_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in logs[20:]:
        with suppress(Exception):
            old.unlink()

    with open(log_path, "a", encoding="utf-8") as _:
        pass
    return log_path, fb, reason


LOG_PATH, _FALLBACK_USED, _FALLBACK_REASON = _select_log_path()
_LOG_LEVEL_NAME = os.environ.get("GLM_LOG_LEVEL", "INFO").upper()
_DEBUG_FLAG = os.environ.get("GLM_DEBUG", "0") == "1"
_LOG_LEVEL = logging.DEBUG if _DEBUG_FLAG else getattr(logging, _LOG_LEVEL_NAME, logging.INFO)
_CONFIGURED = False

_FORMAT = "%(asctime)s.%(msecs)03d %(levelname)s %(name)s %(funcName)s:%(lineno)d %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _ensure_configured() -> None:
    """
    Configure root logger once with rotating file + console output.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(_LOG_LEVEL)

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    # Per-launch file handler
    existing_files = {getattr(h, "baseFilename", None) for h in root.handlers}
    if str(LOG_PATH) not in existing_files:
        fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
        fh.setLevel(_LOG_LEVEL)
        fh.setFormatter(formatter)
        root.addHandler(fh)

    # Console handler (warning+ by default to avoid noise)
    sh = logging.StreamHandler()
    sh.setLevel(_LOG_LEVEL if _DEBUG_FLAG else logging.WARNING)
    sh.setFormatter(formatter)
    root.addHandler(sh)

    logging.raiseExceptions = False  # prevent handler errors bubbling in production

    _CONFIGURED = True
    root.info(
        "log_path_selected %s",
        kv(path=str(LOG_PATH), dir=str(LOG_PATH.parent), fallback_used=_FALLBACK_USED, reason=_FALLBACK_REASON, level=logging.getLevelName(_LOG_LEVEL)),
    )
    # Paths header
    try:
        from app.storage.paths import library_json_path, settings_json_path
        root.info(
            "paths %s",
            kv(
                log_dir=str(LOG_PATH.parent),
                log_file=str(LOG_PATH.name),
                settings=str(settings_json_path()),
                library=str(library_json_path()),
            ),
        )
    except Exception:
        pass


def get_logger(name: str = "manager") -> logging.Logger:
    """
    Returns a logger with global configuration applied.
    Child loggers inherit handlers from root; no per-module handlers are added.
    """
    _ensure_configured()
    logger = logging.getLogger(name)
    logger.setLevel(_LOG_LEVEL)
    return logger


# -------- structured helpers --------

def kv(**fields: Any) -> str:
    """
    Format arbitrary key/value pairs into `k=v` tokens separated by spaces.
    Floats are formatted with 3 decimal places, bools lower-case.
    """
    parts = []
    for k, v in fields.items():
        if v is None:
            parts.append(f"{k}=None")
        elif isinstance(v, float):
            parts.append(f"{k}={v:.3f}")
        elif isinstance(v, bool):
            parts.append(f"{k}={'true' if v else 'false'}")
        else:
            parts.append(f"{k}={v}")
    return " ".join(parts)


def elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000.0


class RateLimiter:
    """
    Simple per-key rate limiter to avoid log spam.
    """
    def __init__(self) -> None:
        self._last: dict[str, float] = {}

    def allow(self, key: str, interval_ms: int = 300) -> bool:
        now = time.perf_counter()
        prev = self._last.get(key)
        if prev is None or (now - prev) * 1000 >= interval_ms:
            self._last[key] = now
            return True
        return False


class timed:
    """
    Context manager to log elapsed time automatically.
    Usage:
        with timed(logger, "grid_render", event="grid_render"):
            ...
    """
    def __init__(self, logger: logging.Logger, label: str, level: int = logging.INFO, **fields: Any) -> None:
        self.logger = logger
        self.label = label
        self.level = level
        self.fields = fields
        self._start = 0.0

    def __enter__(self):
        self._start = time.perf_counter()
        self.logger.log(self.level, "%s_start %s", self.label, kv(**self.fields))
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        duration = elapsed_ms(self._start)
        extra = dict(self.fields)
        extra["duration_ms"] = round(duration, 1)
        if exc_type:
            self.logger.exception("%s_error %s", self.label, kv(**extra))
        else:
            self.logger.log(self.level, "%s_done %s", self.label, kv(**extra))
        # propagate exception (do not suppress)
        return False


def wrap_slot(logger: logging.Logger, label: str, **context: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator to wrap Qt slots/callbacks so exceptions are logged with tracebacks.
    """
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception:
                logger.exception("qt_slot_exception %s", kv(slot=label or fn.__qualname__, **context))
                raise
        return wrapper
    return decorator


def connect_safe(signal, fn: Callable[..., Any], logger: logging.Logger, label: str, **context: Any):
    """
    Connect a Qt signal to a slot with automatic exception logging.
    """
    signal.connect(wrap_slot(logger, label, **context)(fn))


def show_log_path_message():
    """
    One-time message box to surface log destination when a fallback was used.
    """
    global _LOG_MESSAGE_SHOWN
    if _LOG_MESSAGE_SHOWN:
        return
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        from PySide6.QtCore import Qt
        app = QApplication.instance()
        if app is None:
            return
        box = QMessageBox(QMessageBox.Information, "Log location", f"Logs are written to:\n{LOG_PATH}", QMessageBox.Ok)
        box.setWindowModality(Qt.NonModal if hasattr(box, "setWindowModality") else 0)
        box.setAttribute(Qt.WA_DeleteOnClose)
        box.show()
        _LOG_MESSAGE_SHOWN = True
    except Exception:
        # swallow to avoid import cycle issues
        pass
