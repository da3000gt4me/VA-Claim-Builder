from __future__ import annotations
import threading
from PySide6.QtCore import QObject,Signal,Slot
from core.jobs import JobManager
from core.nexus import NexusGenerationError,NexusGenerationService
class NexusGenerationWorker(QObject):
 progress=Signal(int,str);generation_updated=Signal(str);completed=Signal(str);failed=Signal(str);cancelled=Signal();finished=Signal()
 def __init__(self,project,letter_id,*,service_factory=None):
  super().__init__();self.project=project;self.letter_id=letter_id;self.cancel_event=threading.Event();self.jobs=JobManager(project);self.job=self.jobs.create("nexus_generation",{"letter_id":letter_id});self.service=(service_factory or NexusGenerationService)(project);self.generation=self.service.create_pending(letter_id,self.job.job_id)
 @Slot()
 def run(self):
  try:
   if self.cancel_event.is_set():self._cancel();return
   self.jobs.update(self.job.job_id,status="running",progress=10,message="Generating nexus draft");self.progress.emit(10,"Generating nexus draft")
   result=self.service.generate(self.letter_id,job_id=self.job.job_id,generation_id=self.generation["generation_id"],cancelled=self.cancel_event.is_set);self.generation_updated.emit(result["generation_id"])
   if result["status"]=="cancelled":self._cancel();return
   self.jobs.update(self.job.job_id,status="completed",progress=100,message="Nexus draft generated");self.progress.emit(100,"Nexus draft generated");self.completed.emit(self.letter_id)
  except NexusGenerationError as e:self.jobs.update(self.job.job_id,status="failed",message=str(e));self.failed.emit(str(e))
  finally:self.finished.emit()
 @Slot()
 def cancel(self):self.cancel_event.set();self.jobs.update(self.job.job_id,status="cancelling",message="Cancellation requested")
 def _cancel(self):self.service.cancel_pending(self.generation["generation_id"]);self.jobs.update(self.job.job_id,status="cancelled",message="Nexus generation cancelled");self.cancelled.emit()
