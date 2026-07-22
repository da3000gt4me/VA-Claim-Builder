from __future__ import annotations
import threading
from PySide6.QtCore import QObject,Signal,Slot
from core.dbq import DBQPreparationError,DBQPreparationService
from core.jobs import JobManager
class DBQPreparationWorker(QObject):
 progress=Signal(int,str);completed=Signal(str);failed=Signal(str);cancelled=Signal();finished=Signal()
 def __init__(self,project,dbq_id,*,service_factory=None):super().__init__();self.project=project;self.dbq_id=dbq_id;self.cancel_event=threading.Event();self.jobs=JobManager(project);self.job=self.jobs.create("dbq_preparation",{"dbq_id":dbq_id});self.service=(service_factory or DBQPreparationService)(project);self.generation=self.service.create_pending(dbq_id,self.job.job_id)
 @Slot()
 def run(self):
  try:
   if self.cancel_event.is_set():self._cancel();return
   self.jobs.update(self.job.job_id,status="running",progress=10,message="Preparing DBQ suggestions");self.progress.emit(10,"Preparing DBQ suggestions");r=self.service.prepare(self.dbq_id,generation_id=self.generation["generation_id"],cancelled=self.cancel_event.is_set)
   if r["status"]=="cancelled":self._cancel();return
   self.jobs.update(self.job.job_id,status="completed",progress=100,message="DBQ suggestions ready");self.progress.emit(100,"DBQ suggestions ready");self.completed.emit(self.dbq_id)
  except DBQPreparationError as e:self.jobs.update(self.job.job_id,status="failed",message=str(e));self.failed.emit(str(e))
  finally:self.finished.emit()
 @Slot()
 def cancel(self):self.cancel_event.set();self.jobs.update(self.job.job_id,status="cancelling",message="Cancellation requested")
 def _cancel(self):self.service.cancel_pending(self.generation["generation_id"]);self.jobs.update(self.job.job_id,status="cancelled",message="DBQ preparation cancelled");self.cancelled.emit()
