from __future__ import annotations
from PySide6.QtCore import QObject, Signal, Slot
from typing import List

from app.models import Game
from app.services import check_updates_background
from app.logging_utils import get_logger, kv

_log = get_logger("worker.update")

class UpdateWorker(QObject):
    progress = Signal(str, int, int)   # message, done, total
    finished = Signal(list)            # results list
    failed = Signal(str)

    def __init__(self, games: List[Game]) -> None:
        super().__init__()
        self.games = games
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        try:
            _log.info("updates_worker_start %s", kv(count=len(self.games)))
            def progress_cb(msg: str, done: int, total: int):
                self.progress.emit(msg, done, total)
            def cancel_cb() -> bool:
                return self._cancelled

            results = check_updates_background(self.games, progress=progress_cb, cancel=cancel_cb)
            self.finished.emit(results)
        except Exception as e:
            _log.exception("updates_worker_error")
            self.failed.emit(str(e))
