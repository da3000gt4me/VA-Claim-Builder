from __future__ import annotations
import json,sqlite3,uuid
from datetime import datetime,timezone
from core.ai.router import AIRouter
from core.ai.types import AIRequest
from core.claims import ClaimManager
from core.evidence import EvidenceAnalysisService,EvidenceManager
from core.documents import DocumentManager
from core.ocr import OCRManager
from core.projects.manager import NEXUS_SCHEMA
from core.security.redaction import redact_identifiers
from core.settings import SettingsManager
from core.timeline import TimelineManager
from .manager import CONTENT_FIELDS,NexusLetterManager

def _now():return datetime.now(timezone.utc).isoformat()
class NexusGenerationError(RuntimeError):pass
class NexusGenerationService:
 def __init__(self,project,*,settings_manager=None,router_factory=None):
  self.project=project;self.settings=settings_manager or SettingsManager();self.router_factory=router_factory or self._router;self.manager=NexusLetterManager(project);self.claims=ClaimManager(project);self.evidence=EvidenceManager(project);self.timeline=TimelineManager(project);self.documents=DocumentManager(project);self.ocr=OCRManager(project)
  with self._connect() as c:c.executescript(NEXUS_SCHEMA)
 def _connect(self):c=sqlite3.connect(self.project.database_path);c.row_factory=sqlite3.Row;c.execute("PRAGMA foreign_keys=ON");return c
 def create_pending(self,lid,job_id=None):
  self.manager.get(lid);s=self.settings.load_ai_settings();gid=str(uuid.uuid4());model=s.model_openai if s.provider=="openai" else s.model_xai
  with self._connect() as c:c.execute("INSERT INTO nexus_generations VALUES(?,?,?,'pending',?,?,0,'',?,NULL)",(gid,lid,job_id,s.provider,model,_now()))
  return self.get(gid)
 def generate(self,lid,*,job_id=None,generation_id=None,cancelled=lambda:False):
  run=self.get(generation_id) if generation_id else self.create_pending(lid,job_id);s=self.settings.load_ai_settings()
  if cancelled():return self._finish(run["generation_id"],"cancelled",error="Generation cancelled")
  if s.local_only:return self._fail(run,"Nexus generation is unavailable while local-only mode is enabled")
  if s.provider not in {"openai","xai"}:return self._fail(run,"AI provider is unavailable")
  keys={"openai":s.openai_api_key,"xai":s.xai_api_key}
  if not any(keys.get(p) for p in (s.provider,s.fallback_provider)):return self._fail(run,"AI provider credentials are not configured")
  try:
   prompt=self._prompt(lid);redacted=bool(s.redact_before_cloud)
   if redacted:prompt,_=redact_identifiers(prompt)
   response=self.router_factory(s).generate(AIRequest(task="nexus_letter_generation",system_prompt="Draft advisory physician-review prose from supplied facts only. Never invent facts, credentials, findings, or citations. Mark unsupported facts. Return JSON only.",user_prompt=prompt,json_schema={"type":"object"}))
   if cancelled():return self._finish(run["generation_id"],"cancelled",provider=response.provider,model=response.model,redacted=redacted,error="Generation cancelled")
   content=self._validate(response.parsed);meta={"provider":response.provider,"model":response.model,"generated_at":_now(),"redaction_applied":redacted,"generation_version":"1.0","advisory":True}
   self.manager.create_ai_version(lid,content,meta);return self._finish(run["generation_id"],"completed",provider=response.provider,model=response.model,redacted=redacted)
  except Exception as exc:
   msg=str(exc) if isinstance(exc,NexusGenerationError) else ("AI provider timed out" if "timeout" in type(exc).__name__.lower() else f"AI provider failed: {type(exc).__name__}")
   self._finish(run["generation_id"],"failed",redacted=bool(s.redact_before_cloud),error=msg[:500]);raise NexusGenerationError(msg) from exc
 def cancel_pending(self,gid):return self._finish(gid,"cancelled",error="Generation cancelled")
 def get(self,gid):
  with self._connect() as c:r=c.execute("SELECT * FROM nexus_generations WHERE generation_id=?",(gid,)).fetchone()
  if not r:raise KeyError(gid)
  return dict(r)
 def _prompt(self,lid):
  x=self.manager.get(lid);claim=self.claims.get(x.claim_id);evidence=[]
  for eid in x.evidence_ids:
   e=self.evidence.get(eid);latest=EvidenceAnalysisService(self.project,settings_manager=self.settings).latest(eid)
   evidence.append({"source_evidence_id":eid,"title":e.title,"description":e.description,"date":e.evidence_date,"provider":e.provider_source,"relevance_notes":e.relevance_notes,"analysis":latest.result.to_dict() if latest and latest.result else None,"ocr_text":self.evidence.ocr_text(eid) or ""})
  events=[]
  for tid in x.timeline_event_ids:
   t=self.timeline.get(tid);events.append({"source_timeline_event_id":tid,"date":t.event_date,"title":t.title,"description":t.description,"provider":t.provider_facility,"diagnosis":t.diagnosis,"treatment":t.treatment,"notes":t.notes})
  documents=[]
  for did in x.document_ids:
   try:d=self.documents.get(did);o=self.ocr.get(did);text=o.text_path.read_text(encoding="utf-8",errors="replace")
   except (KeyError,OSError):text="";d=None
   documents.append({"source_document_id":did,"name":d.original_name if d else "","ocr_text":text})
  data={"claim":{"condition":claim.condition_name,"type":claim.claim_type,"description":claim.description,"service_event":claim.service_event,"diagnosis":claim.current_diagnosis,"symptoms":claim.symptoms},"primary_theory":x.primary_theory,"theories":x.theories,"provider":{"name":x.author_name,"credentials":x.author_credentials,"specialty":x.specialty},"user_facts":x.content.get("user_facts",""),"evidence":evidence,"timeline_events":events,"documents":documents}
  return "Return complete prose fields records_reviewed,service_history,current_diagnosis,medical_history,in_service_event,nexus_opinion,medical_rationale,favorable_evidence,unfavorable_evidence,limitations,signature_block plus missing_facts (array) and literature_search_terms (array). The opinion must say it is a draft requiring qualified professional review/signature. Do not choose final probability language; leave probability_language empty. Cite supplied source IDs in prose. Data:\n"+json.dumps(data)
 def _validate(self,payload):
  if not isinstance(payload,dict):raise NexusGenerationError("AI provider returned a malformed nexus response")
  required=set(CONTENT_FIELDS)-{"probability_language","user_facts"}
  if any(k not in payload for k in required):raise NexusGenerationError("AI provider response is missing required nexus sections")
  out={}
  for k in CONTENT_FIELDS:
   v=payload.get(k,[] if k=="missing_facts" else "")
   if k=="missing_facts":
    if not isinstance(v,list) or not all(isinstance(i,str) for i in v):raise NexusGenerationError("AI provider returned malformed missing facts")
   elif not isinstance(v,str):raise NexusGenerationError(f"AI provider returned malformed {k}")
   out[k]=v
  out["probability_language"]="";out["signature_block"]=(out["signature_block"]+"\nDRAFT — Requires review and signature by a qualified medical professional.").strip()
  return out
 def _fail(self,run,msg):self._finish(run["generation_id"],"failed",error=msg);raise NexusGenerationError(msg)
 def _finish(self,gid,status,provider=None,model=None,redacted=False,error=""):
  run=self.get(gid)
  with self._connect() as c:c.execute("UPDATE nexus_generations SET status=?,provider=?,model=?,redaction_applied=?,error_message=?,completed_at=? WHERE generation_id=?",(status,provider or run["provider"],model or run["model"],int(redacted),error,_now(),gid))
  return self.get(gid)
 def _router(self,s):self.settings.apply_to_environment(s);return AIRouter(s.provider,s.fallback_provider or None)
