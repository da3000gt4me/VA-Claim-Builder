from __future__ import annotations

import threading
from typing import Callable

from PySide6.QtCore import QObject, Signal, Slot

from core.evidence import EvidenceAnalysisError, EvidenceAnalysisService
from core.jobs import JobManager
from core.projects import ProjectInfo


class EvidenceAnalysisWorker(QObject):
    """Runs one or more evidence analyses without blocking the Qt event loop."""

    progress = Signal(int, str)
    analysis_updated = Signal(str)
    completed = Signal(int, int)
    failed = Signal(str)
    cancelled = Signal()
    finished = Signal()

    def __init__(self, project: ProjectInfo, evidence_ids: list[str], *,
                 service_factory: Callable[[ProjectInfo], EvidenceAnalysisService] | None = None) -> None:
        super().__init__()
        self.project = project
        self.evidence_ids = list(dict.fromkeys(evidence_ids))
        self._cancel_event = threading.Event()
        self.jobs = JobManager(project)
        self.job = self.jobs.create("evidence_analysis", {"evidence_ids": self.evidence_ids})
        self.service = (service_factory or EvidenceAnalysisService)(project)
        self.active_analysis_id: str | None = None

    @Slot()
    def run(self) -> None:
        completed = 0; failed = 0
        try:
            self.jobs.update(self.job.job_id, status="running", message="Starting evidence analysis")
            total = max(1, len(self.evidence_ids))
            for index, evidence_id in enumerate(self.evidence_ids):
                if self._cancel_event.is_set():
                    self._mark_cancelled(index, total); return
                pending = self.service.create_pending(evidence_id, job_id=self.job.job_id)
                self.active_analysis_id = pending.analysis_id
                self.analysis_updated.emit(pending.analysis_id)
                before = int(index / total * 100)
                self.progress.emit(before, f"Analyzing evidence {index + 1} of {total}")
                try:
                    result = self.service.analyze(
                        evidence_id, job_id=self.job.job_id, analysis_id=pending.analysis_id,
                        cancelled=self._cancel_event.is_set,
                    )
                    self.analysis_updated.emit(result.analysis_id)
                    if result.status == "cancelled":
                        self._mark_cancelled(index, total); return
                    completed += 1
                except EvidenceAnalysisError:
                    failed += 1
                    self.analysis_updated.emit(pending.analysis_id)
                percent = int((index + 1) / total * 100)
                self.jobs.update(self.job.job_id, progress=percent, message=f"Analyzed {index + 1} of {total}")
                self.progress.emit(percent, f"Analyzed {index + 1} of {total}")
            status = "completed" if completed else "failed"
            message = f"Evidence analysis finished: {completed} completed, {failed} failed"
            self.jobs.update(self.job.job_id, status=status, progress=100, message=message)
            if completed:
                self.completed.emit(completed, failed)
            else:
                self.failed.emit(message)
        except Exception as exc:
            message = f"Evidence analysis worker failed: {type(exc).__name__}"
            self.jobs.update(self.job.job_id, status="failed", message=message)
            self.failed.emit(message)
        finally:
            self.active_analysis_id = None
            self.finished.emit()

    @Slot()
    def cancel(self) -> None:
        self._cancel_event.set()
        self.jobs.update(self.job.job_id, status="cancelling", message="Cancellation requested")

    def _mark_cancelled(self, index: int, total: int) -> None:
        if self.active_analysis_id:
            self.service.cancel_pending(self.active_analysis_id)
        progress = int(index / total * 100)
        self.jobs.update(self.job.job_id, status="cancelled", progress=progress, message="Evidence analysis cancelled")
        self.cancelled.emit()
