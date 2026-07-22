from __future__ import annotations
import threading
from PySide6.QtCore import QObject,Signal,Slot
from core.jobs import JobManager
from core.rating_strategy import RatingStrategyEngine,RatingStrategyError
class RatingStrategyWorker(QObject):
 progress=Signal(int,str);strategy_updated=Signal(str);completed=Signal(int,int);failed=Signal(str);cancelled=Signal();finished=Signal()
 def __init__(self,project,claim_ids,*,engine_factory=None):super().__init__();self.project=project;self.claim_ids=list(dict.fromkeys(claim_ids));self.cancel_event=threading.Event();self.jobs=JobManager(project);self.job=self.jobs.create("rating_strategy",{"claim_ids":self.claim_ids});self.engine=(engine_factory or RatingStrategyEngine)(project);self.active=None
 @Slot()
 def run(self):
  done=failed=0
  try:
   self.jobs.update(self.job.job_id,status="running",message="Starting rating strategy analysis");total=max(1,len(self.claim_ids))
   for i,cid in enumerate(self.claim_ids):
    if self.cancel_event.is_set():self._cancel(i,total);return
    self.active=self.engine.create_pending(cid,self.job.job_id);self.strategy_updated.emit(self.active.strategy_id);self.progress.emit(int(i/total*100),f"Analyzing claim {i+1} of {total}")
    try:
     r=self.engine.analyze(cid,strategy_id=self.active.strategy_id,cancelled=self.cancel_event.is_set);self.strategy_updated.emit(r.strategy_id)
     if r.status=="cancelled":self._cancel(i,total);return
     done+=1
    except RatingStrategyError:failed+=1
    p=int((i+1)/total*100);self.jobs.update(self.job.job_id,progress=p,message=f"Analyzed {i+1} of {total}");self.progress.emit(p,f"Analyzed {i+1} of {total}")
   status="completed" if done else "failed";msg=f"Rating strategy finished: {done} completed, {failed} failed";self.jobs.update(self.job.job_id,status=status,progress=100,message=msg);self.completed.emit(done,failed) if done else self.failed.emit(msg)
  except Exception as e:msg=f"Rating strategy worker failed: {type(e).__name__}";self.jobs.update(self.job.job_id,status="failed",message=msg);self.failed.emit(msg)
  finally:self.active=None;self.finished.emit()
 @Slot()
 def cancel(self):self.cancel_event.set();self.jobs.update(self.job.job_id,status="cancelling",message="Cancellation requested")
 def _cancel(self,i,total):
  if self.active:self.engine.cancel_pending(self.active.strategy_id)
  self.jobs.update(self.job.job_id,status="cancelled",progress=int(i/total*100),message="Rating strategy cancelled");self.cancelled.emit()
