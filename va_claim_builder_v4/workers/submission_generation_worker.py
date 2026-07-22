from __future__ import annotations
import threading
from PySide6.QtCore import QObject,Signal,Slot
from core.jobs import JobManager
from core.submission import SubmissionGenerationError,SubmissionGenerator
class SubmissionGenerationWorker(QObject):
 progress=Signal(int,str);completed=Signal(str);failed=Signal(str);cancelled=Signal();finished=Signal()
 def __init__(self,project,package_id,*,allow_incomplete=False,generator_factory=None):super().__init__();self.project=project;self.package_id=package_id;self.allow_incomplete=allow_incomplete;self.cancel_event=threading.Event();self.jobs=JobManager(project);self.job=self.jobs.create("submission_generation",{"package_id":package_id});self.generator=(generator_factory or SubmissionGenerator)(project)
 @Slot()
 def run(self):
  try:
   if self.cancel_event.is_set():self._cancel();return
   self.jobs.update(self.job.job_id,status="running",message="Generating submission package");r=self.generator.generate(self.package_id,job_id=self.job.job_id,allow_incomplete=self.allow_incomplete,cancelled=self.cancel_event.is_set,progress=self._progress)
   if r.get("status")=="cancelled":self._cancel();return
   self.jobs.update(self.job.job_id,status="completed",progress=100,message="Submission package generated");self.completed.emit(str(r["output_folder"]))
  except SubmissionGenerationError as e:self.jobs.update(self.job.job_id,status="failed",message=str(e));self.failed.emit(str(e))
  finally:self.finished.emit()
 def _progress(self,p,m):self.jobs.update(self.job.job_id,progress=p,message=m);self.progress.emit(p,m)
 @Slot()
 def cancel(self):self.cancel_event.set();self.jobs.update(self.job.job_id,status="cancelling",message="Cancellation requested")
 def _cancel(self):self.jobs.update(self.job.job_id,status="cancelled",message="Submission generation cancelled");self.cancelled.emit()
