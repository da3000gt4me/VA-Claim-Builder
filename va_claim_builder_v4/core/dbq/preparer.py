from __future__ import annotations
import json,sqlite3,uuid
from datetime import datetime,timezone
from core.ai.router import AIRouter
from core.ai.types import AIRequest
from core.claims import ClaimManager
from core.documents import DocumentManager
from core.evidence import EvidenceAnalysisService,EvidenceManager
from core.nexus import NexusLetterManager
from core.ocr import OCRManager
from core.projects.manager import DBQ_SCHEMA
from core.security.redaction import redact_identifiers
from core.settings import SettingsManager
from core.timeline import TimelineManager
from .manager import DBQManager
from .templates import get_template
def _now():return datetime.now(timezone.utc).isoformat()
class DBQPreparationError(RuntimeError):pass
class DBQPreparationService:
 def __init__(self,project,*,settings_manager=None,router_factory=None):
  self.project=project;self.settings=settings_manager or SettingsManager();self.router_factory=router_factory or self._router;self.manager=DBQManager(project);self.claims=ClaimManager(project);self.evidence=EvidenceManager(project);self.timeline=TimelineManager(project);self.documents=DocumentManager(project);self.ocr=OCRManager(project);self.nexus=NexusLetterManager(project)
  with self._connect() as c:c.executescript(DBQ_SCHEMA)
 def _connect(self):c=sqlite3.connect(self.project.database_path);c.row_factory=sqlite3.Row;c.execute("PRAGMA foreign_keys=ON");return c
 def create_pending(self,did,job_id=None):
  self.manager.get(did);s=self.settings.load_ai_settings();gid=str(uuid.uuid4());model=s.model_openai if s.provider=="openai" else s.model_xai
  with self._connect() as c:c.execute("INSERT INTO dbq_generations VALUES(?,?,?,'pending',?,?,0,'',?,NULL)",(gid,did,job_id,s.provider,model,_now()))
  return self.get(gid)
 def prepare(self,did,*,job_id=None,generation_id=None,cancelled=lambda:False):
  run=self.get(generation_id) if generation_id else self.create_pending(did,job_id);s=self.settings.load_ai_settings()
  if cancelled():return self._finish(run["generation_id"],"cancelled",error="Preparation cancelled")
  if s.local_only:return self._fail(run,"DBQ preparation is unavailable while local-only mode is enabled")
  if s.provider not in {"openai","xai"}:return self._fail(run,"AI provider is unavailable")
  if not any({"openai":s.openai_api_key,"xai":s.xai_api_key}.get(p) for p in (s.provider,s.fallback_provider)):return self._fail(run,"AI provider credentials are not configured")
  try:
   prompt=self._prompt(did);redacted=bool(s.redact_before_cloud)
   if redacted:prompt,_=redact_identifiers(prompt)
   response=self.router_factory(s).generate(AIRequest(task="dbq_preparation",system_prompt="Prepare advisory DBQ field suggestions from supplied facts only. Never invent diagnoses, measurements, test results, observations, or frequency. Examiner-only values must remain empty. Return JSON only.",user_prompt=prompt,json_schema={"type":"object"}))
   if cancelled():return self._finish(run["generation_id"],"cancelled",provider=response.provider,model=response.model,redacted=redacted,error="Preparation cancelled")
   suggestions=self._validate(did,response.parsed);meta={"provider":response.provider,"model":response.model,"generated_at":_now(),"redaction_applied":redacted,"version":"1.0","advisory":True};self.manager.create_ai_revision(did,suggestions,meta);return self._finish(run["generation_id"],"completed",provider=response.provider,model=response.model,redacted=redacted)
  except Exception as exc:
   msg=str(exc) if isinstance(exc,DBQPreparationError) else ("AI provider timed out" if "timeout" in type(exc).__name__.lower() else f"AI provider failed: {type(exc).__name__}");self._finish(run["generation_id"],"failed",redacted=bool(s.redact_before_cloud),error=msg[:500]);raise DBQPreparationError(msg) from exc
 def get(self,gid):
  with self._connect() as c:r=c.execute("SELECT * FROM dbq_generations WHERE generation_id=?",(gid,)).fetchone()
  if not r:raise KeyError(gid)
  return dict(r)
 def cancel_pending(self,gid):return self._finish(gid,"cancelled",error="Preparation cancelled")
 def _prompt(self,did):
  x=self.manager.get(did);claim=self.claims.get(x.claim_id);t=get_template(x.template_id);evidence=[]
  for eid in x.evidence_ids:
   e=self.evidence.get(eid);a=EvidenceAnalysisService(self.project,settings_manager=self.settings).latest(eid);evidence.append({"source_id":eid,"source_label":e.title,"description":e.description,"provider":e.provider_source,"notes":e.relevance_notes,"ocr_text":self.evidence.ocr_text(eid) or "","analysis":a.result.to_dict() if a and a.result else None})
  events=[]
  for tid in x.timeline_event_ids:
   z=self.timeline.get(tid);events.append({"source_id":tid,"source_label":z.title,"date":z.event_date,"description":z.description,"diagnosis":z.diagnosis,"symptoms":z.symptoms,"testing":z.testing_imaging,"impact":z.functional_impact})
  docs=[]
  for did2 in x.document_ids:
   try:d=self.documents.get(did2);o=self.ocr.get(did2);text=o.text_path.read_text(encoding="utf-8",errors="replace")
   except (KeyError,OSError):d=None;text=""
   docs.append({"source_id":did2,"source_label":d.original_name if d else "Document","ocr_text":text})
  nx=[{"title":n.title,"content":n.content} for n in self.nexus.list(claim_id=x.claim_id)];fields=[{"key":f.key,"label":f.label,"kind":f.kind,"required":f.required,"guidance":f.guidance} for f in t.fields];data={"template":t.name,"fields":fields,"claim":{"condition":claim.condition_name,"diagnosis":claim.current_diagnosis,"symptoms":claim.symptoms,"history":claim.description},"current_user_fields":x.fields,"evidence":evidence,"timeline":events,"documents":docs,"nexus_drafts":nx}
  return "Return {\"suggestions\":[{field_key,proposed_value,information_class,confidence,source_ids,source_labels,missing_information,conflicting_information,requires_examiner,advisory_note}]}. information_class is claimant_reported, documented, or ai_inferred. Examiner-only proposed_value must be empty and requires_examiner true. Data:\n"+json.dumps(data)
 def _validate(self,did,payload):
  if not isinstance(payload,dict) or not isinstance(payload.get("suggestions"),list):raise DBQPreparationError("AI provider returned a malformed DBQ response")
  template=get_template(self.manager.get(did).template_id);by={f.key:f for f in template.fields};out=[]
  for raw in payload["suggestions"]:
   if not isinstance(raw,dict) or raw.get("field_key") not in by:raise DBQPreparationError("AI provider returned an unsupported DBQ field")
   key=raw["field_key"];f=by[key];classification=str(raw.get("information_class","")).lower();confidence=str(raw.get("confidence","")).lower()
   if classification not in {"claimant_reported","documented","ai_inferred"} or confidence not in {"low","medium","high"}:raise DBQPreparationError("AI provider returned malformed DBQ suggestion metadata")
   value=str(raw.get("proposed_value","")).strip();requires=bool(raw.get("requires_examiner")) or f.kind=="examiner"
   if f.kind=="examiner":value="";requires=True
   lists={k:raw.get(k,[]) for k in ("source_ids","source_labels","missing_information")}
   if any(not isinstance(v,list) or not all(isinstance(i,str) for i in v) for v in lists.values()):raise DBQPreparationError("AI provider returned malformed source traceability")
   out.append({"field_key":key,"proposed_value":value,"information_class":classification,"confidence":confidence,**lists,"conflicting_information":str(raw.get("conflicting_information","")),"requires_examiner":requires,"advisory_note":str(raw.get("advisory_note","Requires verification.")),"decision":"pending"})
  return out
 def _fail(self,run,msg):self._finish(run["generation_id"],"failed",error=msg);raise DBQPreparationError(msg)
 def _finish(self,gid,status,provider=None,model=None,redacted=False,error=""):
  run=self.get(gid)
  with self._connect() as c:c.execute("UPDATE dbq_generations SET status=?,provider=?,model=?,redaction_applied=?,error_message=?,completed_at=? WHERE generation_id=?",(status,provider or run["provider"],model or run["model"],int(redacted),error,_now(),gid))
  return self.get(gid)
 def _router(self,s):self.settings.apply_to_environment(s);return AIRouter(s.provider,s.fallback_provider or None)
