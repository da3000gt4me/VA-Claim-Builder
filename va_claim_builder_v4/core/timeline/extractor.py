from __future__ import annotations
import json,sqlite3,uuid
from dataclasses import dataclass
from datetime import datetime,timezone
from typing import Any,Callable
from core.ai.router import AIRouter
from core.ai.types import AIRequest
from core.evidence import EvidenceManager
from core.ocr import OCRManager
from core.projects import ProjectInfo
from core.projects.manager import TIMELINE_SCHEMA
from core.security.redaction import redact_identifiers
from core.settings import AISettings,SettingsManager
from .manager import DATE_PRECISIONS,EVENT_TYPES,TimelineManager
def _now():return datetime.now(timezone.utc).isoformat()
class TimelineExtractionError(RuntimeError):pass
@dataclass(frozen=True,slots=True)
class TimelineCandidate:
 candidate_id:str;extraction_id:str;status:str;event:dict[str,Any];document_id:str|None;evidence_id:str|None;merged_into_candidate_id:str|None;created_at:str;updated_at:str
@dataclass(frozen=True,slots=True)
class TimelineExtraction:
 extraction_id:str;job_id:str|None;status:str;provider:str;model:str;redaction_applied:bool;error_message:str;created_at:str;completed_at:str|None
class TimelineExtractionService:
 def __init__(self,project:ProjectInfo,*,settings_manager=None,router_factory=None):
  self.project=project;self.settings=settings_manager or SettingsManager();self.router_factory=router_factory or self._router
  self.timeline=TimelineManager(project);self.evidence=EvidenceManager(project);self.ocr=OCRManager(project)
  with self._connect() as c:c.executescript(TIMELINE_SCHEMA)
 def _connect(self):c=sqlite3.connect(self.project.database_path);c.row_factory=sqlite3.Row;c.execute("PRAGMA foreign_keys=ON");return c
 def create_pending(self,*,job_id=None):
  s=self.settings.load_ai_settings();eid=str(uuid.uuid4());now=_now();model=s.model_openai if s.provider=="openai" else s.model_xai
  with self._connect() as c:c.execute("INSERT INTO timeline_extractions VALUES(?,?,? ,?,?,0,'',?,NULL)",(eid,job_id,"pending",s.provider,model,now))
  return self.get_extraction(eid)
 def extract(self,*,evidence_ids=(),document_ids=(),job_id=None,extraction_id=None,cancelled=lambda:False):
  run=self.get_extraction(extraction_id) if extraction_id else self.create_pending(job_id=job_id);s=self.settings.load_ai_settings()
  if cancelled():return self._finish(run.extraction_id,"cancelled",error="Extraction cancelled")
  if s.local_only:return self._fail(run,"Timeline extraction is unavailable while local-only mode is enabled")
  creds={"openai":s.openai_api_key,"xai":s.xai_api_key}; providers=[s.provider,s.fallback_provider]
  if s.provider not in {"openai","xai"}:return self._fail(run,"AI provider is unavailable")
  if not any(creds.get(p) for p in providers):return self._fail(run,"AI provider credentials are not configured")
  try:
   prompt=self._prompt(list(evidence_ids),list(document_ids));redacted=bool(s.redact_before_cloud)
   if redacted:prompt,_=redact_identifiers(prompt)
   response=self.router_factory(s).generate(AIRequest(task="timeline_extraction",system_prompt="Extract factual medical timeline candidates. Output JSON only. Candidates are advisory and require user review.",user_prompt=prompt,json_schema={"type":"object"}))
   if cancelled():return self._finish(run.extraction_id,"cancelled",provider=response.provider,model=response.model,redacted=redacted,error="Extraction cancelled")
   items=response.parsed.get("events") if isinstance(response.parsed,dict) else None
   if not isinstance(items,list):raise TimelineExtractionError("AI provider returned a malformed timeline response")
   for item in items:self._create_candidate(run.extraction_id,self._validate(item),item.get("document_id"),item.get("evidence_id"))
   return self._finish(run.extraction_id,"completed",provider=response.provider,model=response.model,redacted=redacted)
  except Exception as exc:
   msg=str(exc) if isinstance(exc,TimelineExtractionError) else ("AI provider timed out" if "timeout" in type(exc).__name__.lower() else f"AI provider failed: {type(exc).__name__}")
   self._finish(run.extraction_id,"failed",redacted=bool(s.redact_before_cloud),error=msg[:500]);raise TimelineExtractionError(msg) from exc
 def _fail(self,run,msg):self._finish(run.extraction_id,"failed",error=msg);raise TimelineExtractionError(msg)
 def candidates(self,extraction_id=None,status=None):
  q="SELECT * FROM timeline_candidates";clauses=[];args=[]
  if extraction_id:clauses.append("extraction_id=?");args.append(extraction_id)
  if status:clauses.append("status=?");args.append(status)
  if clauses:q+=" WHERE "+" AND ".join(clauses)
  q+=" ORDER BY created_at,candidate_id"
  with self._connect() as c:rows=c.execute(q,args).fetchall()
  return [self._candidate(r) for r in rows]
 def get_candidate(self,candidate_id):
  with self._connect() as c:r=c.execute("SELECT * FROM timeline_candidates WHERE candidate_id=?",(candidate_id,)).fetchone()
  if not r:raise KeyError(candidate_id)
  return self._candidate(r)
 def update_candidate(self,candidate_id,**changes):
  x=self.get_candidate(candidate_id);event={**x.event,**changes};event=self._validate(event)
  with self._connect() as c:c.execute("UPDATE timeline_candidates SET event_json=?,updated_at=? WHERE candidate_id=?",(json.dumps(event),_now(),candidate_id))
  return self.get_candidate(candidate_id)
 def accept(self,candidate_id):return self._candidate_status(candidate_id,"accepted")
 def reject(self,candidate_id):return self._candidate_status(candidate_id,"rejected")
 def merge(self,source_id,target_id):
  if source_id==target_id:raise ValueError("Cannot merge a candidate into itself")
  source=self.get_candidate(source_id);target=self.get_candidate(target_id);merged=dict(target.event)
  for k,v in source.event.items():
   if not merged.get(k) and v:merged[k]=v
  self.update_candidate(target_id,**merged)
  with self._connect() as c:c.execute("UPDATE timeline_candidates SET status='merged',merged_into_candidate_id=?,updated_at=? WHERE candidate_id=?",(target_id,_now(),source_id))
  return self.get_candidate(target_id)
 def save_accepted(self,candidate_ids=None):
  selected=set(candidate_ids or []);saved=[]
  for c in self.candidates(status="accepted"):
   if selected and c.candidate_id not in selected:continue
   event=dict(c.event);claims=event.pop("claim_ids",[]);event.pop("document_id",None);event.pop("evidence_id",None)
   created=self.timeline.create(event.pop("title"),claim_ids=claims,document_id=c.document_id,evidence_id=c.evidence_id,**event);saved.append(created)
   self._candidate_status(c.candidate_id,"saved")
  return saved
 def duplicate_candidates(self,candidate_id):
  c=self.get_candidate(candidate_id);return self.timeline.likely_duplicates({**c.event,"document_id":c.document_id,"evidence_id":c.evidence_id})
 def get_extraction(self,eid):
  with self._connect() as c:r=c.execute("SELECT * FROM timeline_extractions WHERE extraction_id=?",(eid,)).fetchone()
  if not r:raise KeyError(eid)
  return TimelineExtraction(r[0],r[1],r[2],r[3],r[4],bool(r[5]),r[6],r[7],r[8])
 def _prompt(self,eids,dids):
  sources=[]
  for eid in eids:
   e=self.evidence.get(eid);sources.append({"evidence_id":eid,"document_id":e.document_id,"title":e.title,"date":e.evidence_date,"provider":e.provider_source,"description":e.description,"notes":e.relevance_notes,"ocr_text":self.evidence.ocr_text(eid) or ""})
  for did in dids:
   try:r=self.ocr.get(did);text=r.text_path.read_text(encoding="utf-8",errors="replace")
   except (KeyError,OSError):text=""
   sources.append({"document_id":did,"ocr_text":text})
  return "Return {\"events\":[...]}. Each event must include all timeline fields plus claim_ids, document_id, evidence_id. Sources:\n"+json.dumps(sources)
 def _validate(self,x):
  if not isinstance(x,dict) or not str(x.get("title","")).strip():raise TimelineExtractionError("AI provider returned a malformed timeline candidate")
  out={k:x.get(k,[] if k in {"symptoms","medications","claim_ids"} else "") for k in self.timeline.FIELDS};out["title"]=str(x["title"]).strip()
  out["date_precision"]=out["date_precision"] or "unknown";out["event_type"]=out["event_type"] or "other"
  if out["date_precision"] not in DATE_PRECISIONS or out["event_type"] not in EVENT_TYPES:raise TimelineExtractionError("AI provider returned unsupported timeline values")
  out["claim_ids"]=[str(v) for v in x.get("claim_ids",[])];out["document_id"]=x.get("document_id") or None;out["evidence_id"]=x.get("evidence_id") or None
  return out
 def _create_candidate(self,eid,event,did,vid):
  cid=str(uuid.uuid4());now=_now()
  with self._connect() as c:c.execute("INSERT INTO timeline_candidates VALUES(?,?, 'pending',?,?,?,?,?,?)",(cid,eid,json.dumps(event),did or None,vid or None,None,now,now))
 def _candidate_status(self,cid,status):
  with self._connect() as c:c.execute("UPDATE timeline_candidates SET status=?,updated_at=? WHERE candidate_id=?",(status,_now(),cid))
  return self.get_candidate(cid)
 def _finish(self,eid,status,provider=None,model=None,redacted=False,error=""):
  run=self.get_extraction(eid)
  with self._connect() as c:c.execute("UPDATE timeline_extractions SET status=?,provider=?,model=?,redaction_applied=?,error_message=?,completed_at=? WHERE extraction_id=?",(status,provider or run.provider,model or run.model,int(redacted),error,_now(),eid))
  return self.get_extraction(eid)
 def _router(self,s):self.settings.apply_to_environment(s);return AIRouter(s.provider,s.fallback_provider or None)
 @staticmethod
 def _candidate(r):return TimelineCandidate(r[0],r[1],r[2],json.loads(r[3]),r[4],r[5],r[6],r[7],r[8])
