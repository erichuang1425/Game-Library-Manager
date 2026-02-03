"""
Background workers for Bulk Archive Import operations.

This module contains QObject-based workers for scanning and importing archives
in background threads.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, TYPE_CHECKING

from PySide6.QtCore import Signal, QObject

if TYPE_CHECKING:
    from app.services import BulkArchiveImporter, ImportItem, ImportResult


class ScanWorker(QObject):
    """Worker for scanning archives in background."""
    finished = Signal(list)  # List[ImportItem]
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, importer: "BulkArchiveImporter", source_folder: Path, recursive: bool):
        super().__init__()
        self.importer = importer
        self.source_folder = source_folder
        self.recursive = recursive

    def run(self):
        try:
            self.progress.emit(f"Scanning {self.source_folder}...")
            items = self.importer.scan_folder(self.source_folder, self.recursive)
            self.finished.emit(items)
        except Exception as e:
            self.error.emit(str(e))


class ImportWorker(QObject):
    """Worker for importing archives in background."""
    finished = Signal(object)  # ImportResult
    error = Signal(str)
    progress = Signal(str, int, int, str)  # stage, current, total, message

    def __init__(
        self,
        importer: "BulkArchiveImporter",
        items: List["ImportItem"],
        delete_archives: bool
    ):
        super().__init__()
        self.importer = importer
        self.items = items
        self.delete_archives = delete_archives

    def run(self):
        try:
            result = self.importer.execute_import(
                self.items,
                progress=self._on_progress,
                delete_archives=self.delete_archives,
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))

    def _on_progress(self, stage: str, current: int, total: int, message: str):
        self.progress.emit(stage, current, total, message)
