
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from core.documents import DocumentManager
from core.jobs import JobManager
from core.intake import AutomatedIntakeOrchestrator
from core.projects import ProjectInfo
from core.settings import SettingsManager


class DocumentImportWorker(QObject):
    progress = Signal(int, str)
    completed = Signal(int, int, object)
    failed = Signal(str)
    cancelled = Signal()
    finished = Signal()

    def __init__(self, project: ProjectInfo, filenames: list[str], *, auto_analyze: bool = True) -> None:
        super().__init__()
        self.project = project
        self.filenames = filenames
        self._cancel_event = threading.Event()
        self.auto_analyze = auto_analyze
        self.jobs = JobManager(project)
        self.job = self.jobs.create("document_import", {"files": filenames})

    @Slot()
    def run(self) -> None:
        imported_count = 0
        duplicate_count = 0
        intake_summary = None
        imported_ids: list[str] = []
        try:
            self.jobs.update(self.job.job_id, status="running", message="Starting import")
            manager = DocumentManager(self.project)
            total = max(1, len(self.filenames))
            for index, filename in enumerate(self.filenames, start=1):
                if self._cancel_event.is_set():
                    self.jobs.update(
                        self.job.job_id,
                        status="cancelled",
                        progress=max(0, int(((index - 1) / total) * 100)),
                        message="Import cancelled",
                    )
                    self.cancelled.emit()
                    return
                path = Path(filename)
                percent_before = int(((index - 1) / total) * (35 if self.auto_analyze else 100))
                self.progress.emit(percent_before, f"Importing {path.name} ({index}/{total})")
                imported, duplicates = manager.import_files([path])
                imported_count += len(imported)
                duplicate_count += len(duplicates)
                imported_ids.extend(item.document_id for item in imported)
                percent = int((index / total) * (35 if self.auto_analyze else 100))
                message = f"Processed {index} of {total}: {path.name}"
                self.jobs.update(self.job.job_id, progress=percent, message=message)
                self.progress.emit(percent, message)
            if self.auto_analyze and imported_count:
                orchestrator = AutomatedIntakeOrchestrator(
                    self.project, app_settings=SettingsManager().load_app_settings()
                )
                orchestrator.queue(imported_ids)
                intake_summary = orchestrator.run_documents(
                    imported_ids, cancelled=self._cancel_event.is_set,
                    progress=lambda value, message: self.progress.emit(35 + int(value * .65), message),
                )
                if self._cancel_event.is_set():
                    self.jobs.update(self.job.job_id, status="cancelled", message="Import completed; analysis cancelled with partial results preserved")
                    self.cancelled.emit()
                    return
            self.jobs.update(self.job.job_id, status="completed", progress=100, message="Import and automatic intake complete")
            self.completed.emit(imported_count, duplicate_count, intake_summary)
        except Exception as exc:
            self.jobs.update(self.job.job_id, status="failed", message=str(exc))
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    @Slot()
    def cancel(self) -> None:
        self._cancel_event.set()
        self.jobs.update(self.job.job_id, status="cancelling", message="Cancellation requested")
