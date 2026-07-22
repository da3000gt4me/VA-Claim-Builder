from __future__ import annotations
import threading
from PySide6.QtCore import QObject,Signal,Slot
from core.jobs import JobManager
from core.projects import ProjectInfo
from core.timeline import TimelineExtractionError,TimelineExtractionService
class TimelineExtractionWorker(QObject):
 progress=Signal(int,str);completed=Signal(str);failed=Signal(str);cancelled=Signal();finished=Signal()
 def __init__(self,project:ProjectInfo,*,evidence_ids=(),document_ids=(),service_factory=None):
  super().__init__();self.project=project;self.evidence_ids=list(evidence_ids);self.document_ids=list(document_ids);self.cancel_event=threading.Event();self.jobs=JobManager(project);self.job=self.jobs.create("timeline_extraction",{"evidence_ids":self.evidence_ids,"document_ids":self.document_ids});self.service=(service_factory or TimelineExtractionService)(project);self.extraction=self.service.create_pending(job_id=self.job.job_id)
 @Slot()
 def run(self):
  try:
   self.jobs.update(self.job.job_id,status="running",progress=10,message="Extracting timeline candidates");self.progress.emit(10,"Extracting timeline candidates")
   result=self.service.extract(evidence_ids=self.evidence_ids,document_ids=self.document_ids,job_id=self.job.job_id,extraction_id=self.extraction.extraction_id,cancelled=self.cancel_event.is_set)
   if result.status=="cancelled":self.jobs.update(self.job.job_id,status="cancelled",message="Timeline extraction cancelled");self.cancelled.emit();return
   count=len(self.service.candidates(result.extraction_id));self.jobs.update(self.job.job_id,status="completed",progress=100,message=f"Extracted {count} candidate(s)");self.progress.emit(100,"Extraction complete");self.completed.emit(result.extraction_id)
  except TimelineExtractionError as exc:self.jobs.update(self.job.job_id,status="failed",message=str(exc));self.failed.emit(str(exc))
  finally:self.finished.emit()
 @Slot()
 def cancel(self):self.cancel_event.set();self.jobs.update(self.job.job_id,status="cancelling",message="Cancellation requested")
