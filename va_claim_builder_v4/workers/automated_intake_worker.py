
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal, Slot

from core.intake import AutomatedIntakeOrchestrator
from core.projects import ProjectInfo
from core.settings import SettingsManager


class AutomatedIntakeWorker(QObject):
    progress = Signal(int, str)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    finished = Signal()

    def __init__(self, project: ProjectInfo, document_ids: list[str], *, force: bool = False):
        super().__init__()
        self.project = project
        self.document_ids = document_ids
        self.force = force
        self._cancel = threading.Event()

    @Slot()
    def run(self):
        try:
            summary = AutomatedIntakeOrchestrator(
                self.project, app_settings=SettingsManager().load_app_settings()
            ).run_documents(
                self.document_ids, progress=self.progress.emit,
                cancelled=self._cancel.is_set, force=self.force,
            )
            if self._cancel.is_set():
                self.cancelled.emit()
            else:
                self.completed.emit(summary)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    @Slot()
    def cancel(self):
        self._cancel.set()
