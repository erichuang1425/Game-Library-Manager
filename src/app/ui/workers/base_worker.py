"""
Base worker classes for background operations in the UI.

Provides standardized patterns for QThread-based workers with:
- Progress reporting
- Error handling
- Cancellation support
- Logging integration
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, Optional

from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker

from app.logging_utils import get_logger


class BaseWorker(QThread):
    """
    Base class for background workers with standard signals.

    Subclasses should override `do_work()` instead of `run()`.
    This ensures proper error handling and signal emission.

    Signals:
        progress: Emitted with (percent, message) during work
        finished_with_result: Emitted with the result when work completes
        error: Emitted with error message on failure

    Example:
        class MyWorker(BaseWorker):
            def do_work(self):
                for i in range(100):
                    if self.is_cancelled:
                        return None
                    self.report_progress(i, f"Processing item {i}")
                    # ... do work ...
                return result
    """

    # Signals
    progress = Signal(int, str)  # (percent, message)
    finished_with_result = Signal(object)  # result
    error = Signal(str)  # error message

    def __init__(self, parent: Optional[QThread] = None) -> None:
        super().__init__(parent)
        self._log = get_logger(self.__class__.__name__)
        self._cancelled = False
        self._mutex = QMutex()

    def run(self) -> None:
        """
        Execute the worker. Override `do_work()` instead of this method.
        """
        try:
            result = self.do_work()
            if not self._cancelled:
                self.finished_with_result.emit(result)
        except Exception as e:
            self._log.exception("Worker error in %s", self.__class__.__name__)
            if not self._cancelled:
                self.error.emit(str(e))

    @abstractmethod
    def do_work(self) -> Any:
        """
        Override this method to implement the work.

        Returns:
            The result to emit via finished_with_result signal
        """
        raise NotImplementedError("Subclasses must implement do_work()")

    def cancel(self) -> None:
        """Request cancellation of the worker."""
        with QMutexLocker(self._mutex):
            self._cancelled = True
        self._log.debug("Worker cancelled: %s", self.__class__.__name__)

    @property
    def is_cancelled(self) -> bool:
        """Check if cancellation was requested (thread-safe)."""
        with QMutexLocker(self._mutex):
            return self._cancelled

    def report_progress(self, percent: int, message: str = "") -> None:
        """
        Report progress from within do_work().

        Args:
            percent: Progress percentage (0-100)
            message: Optional status message
        """
        self.progress.emit(percent, message)


class CancellableWorker(BaseWorker):
    """
    Worker with enhanced cancellation support.

    Adds check_cancelled() method that raises an exception
    for cleaner cancellation handling in do_work().
    """

    class CancelledException(Exception):
        """Raised when worker is cancelled."""
        pass

    def run(self) -> None:
        """Execute with cancellation exception handling."""
        try:
            result = self.do_work()
            if not self._cancelled:
                self.finished_with_result.emit(result)
        except CancellableWorker.CancelledException:
            self._log.debug("Worker cancelled via exception: %s", self.__class__.__name__)
        except Exception as e:
            self._log.exception("Worker error in %s", self.__class__.__name__)
            if not self._cancelled:
                self.error.emit(str(e))

    def check_cancelled(self) -> None:
        """
        Check if cancelled and raise exception if so.

        Use this in loops within do_work() for clean cancellation:

            for item in items:
                self.check_cancelled()  # Raises if cancelled
                process(item)
        """
        if self.is_cancelled:
            raise CancellableWorker.CancelledException()


class ProgressWorker(BaseWorker):
    """
    Worker with item-based progress tracking.

    Automatically calculates percentage based on items processed.
    """

    # Additional signal for item-level progress
    item_progress = Signal(int, int, str)  # (current, total, item_description)

    def __init__(self, total_items: int = 0, parent: Optional[QThread] = None) -> None:
        super().__init__(parent)
        self._total_items = total_items
        self._processed_items = 0

    def set_total_items(self, total: int) -> None:
        """Set the total number of items to process."""
        self._total_items = total
        self._processed_items = 0

    def report_item_progress(self, description: str = "") -> None:
        """
        Report progress for one item.

        Automatically increments counter and calculates percentage.

        Args:
            description: Description of current item
        """
        self._processed_items += 1
        self.item_progress.emit(self._processed_items, self._total_items, description)

        if self._total_items > 0:
            percent = int((self._processed_items / self._total_items) * 100)
            self.progress.emit(percent, description)

    @property
    def items_remaining(self) -> int:
        """Number of items remaining to process."""
        return max(0, self._total_items - self._processed_items)
