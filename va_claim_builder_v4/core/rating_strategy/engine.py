from __future__ import annotations
import json,re
from datetime import datetime,timezone
from core.ai.router import AIRouter
from core.ai.types import AIRequest
from core.claims import ClaimManager
from core.dbq import DBQManager
from core.documents import DocumentManager
from core.evidence import EvidenceAnalysisService,EvidenceManager
from core.nexus import NexusLetterManager
from core.ocr import OCRManager
from core.rating.criteria_engine import RatingCriteriaEngine,STARTER_CRITERIA
from core.security.redaction import redact_identifiers
from core.settings import SettingsManager
from core.timeline import TimelineManager
from .manager import RatingStrategyManager
class RatingStrategyError(RuntimeError):pass
SECONDARY={"anxiety":("IBS","Erectile dysfunction"),"neck":("Headaches",),"cervical":("Headaches",),"knee":("Back condition",),"rhinitis":("Sinusitis",)}
class RatingStrategyEngine:
 def __init__(self,project,*,settings_manager=None,router_factory=None):
  self.project=project;self.settings=settings_manager or SettingsManager();self.router_factory=router_factory or self._router;self.manager=RatingStrategyManager(project);self.claims=ClaimManager(project);self.evidence=EvidenceManager(project);self.timeline=TimelineManager(project);self.nexus=NexusLetterManager(project);self.dbqs=DBQManager(project);self.documents=DocumentManager(project);self.ocr=OCRManager(project)
 def create_pending(self,claim_id,job_id=None):self.claims.get(claim_id);return self.manager.create(claim_id,job_id=job_id)
 def analyze(self,claim_id,*,job_id=None,strategy_id=None,cancelled=lambda:False):
  run=self.manager.get(strategy_id) if strategy_id else self.create_pending(claim_id,job_id);s=self.settings.load_ai_settings()
  if cancelled():return self.manager.update(run.strategy_id,status="cancelled",error_message="Analysis cancelled")
  if s.local_only:return self._fail(run,"Rating strategy analysis is unavailable while local-only mode is enabled")
  if s.provider not in {"openai","xai"}:return self._fail(run,"AI provider is unavailable")
  if not any({"openai":s.openai_api_key,"xai":s.xai_api_key}.get(p) for p in (s.provider,s.fallback_provider)):return self._fail(run,"AI provider credentials are not configured")
  try:
   context=self._context(claim_id);baseline=self._baseline(context);prompt=json.dumps({"context":context,"deterministic_review":baseline});redacted=bool(s.redact_before_cloud)
   if redacted:prompt,_=redact_identifiers(prompt)
   response=self.router_factory(s).generate(AIRequest(task="rating_strategy",system_prompt="Analyze claim development using only supplied project facts. Ratings and secondary relationships are non-guaranteed suggestions. Do not invent facts or legal conclusions. Return JSON only.",user_prompt="Return structured strengths, weaknesses, contradictory_evidence, missing_evidence, recommended_actions, secondary_opportunities, aggravation_opportunities, presumptive_opportunities, supporting_evidence, confidence, generated_reasoning. Preserve supplied diagnostic codes and estimate. Data:\n"+prompt,json_schema={"type":"object"}))
   if cancelled():return self.manager.update(run.strategy_id,status="cancelled",error_message="Analysis cancelled")
   ai=self._validate(response.parsed);merged={k:list(dict.fromkeys(baseline[k]+ai[k])) for k in ("strengths","weaknesses","contradictory_evidence","missing_evidence","recommended_actions","secondary_opportunities","aggravation_opportunities","presumptive_opportunities","supporting_evidence")};confidence=self._confidence(merged,baseline["estimated_rating_range"])
   return self.manager.update(run.strategy_id,status="completed",confidence=confidence,diagnostic_codes=baseline["diagnostic_codes"],estimated_rating_range=baseline["estimated_rating_range"],generated_reasoning=ai["generated_reasoning"]+"\n\nEstimate rationale: "+baseline["estimate_reasoning"]+" This estimate is preliminary and is not guaranteed.",ai_metadata={"provider":response.provider,"model":response.model,"redaction_applied":redacted,"generated_at":datetime.now(timezone.utc).isoformat(),"advisory":True},**merged)
  except Exception as exc:
   msg=str(exc) if isinstance(exc,RatingStrategyError) else ("AI provider timed out" if "timeout" in type(exc).__name__.lower() else f"AI provider failed: {type(exc).__name__}");self.manager.update(run.strategy_id,status="failed",error_message=msg[:500]);raise RatingStrategyError(msg) from exc
 def cancel_pending(self,sid):return self.manager.update(sid,status="cancelled",error_message="Analysis cancelled")
 def _context(self,cid):
  c=self.claims.get(cid);evs=self.evidence.list(claim_id=cid);evidence=[];doc_ids=set()
  for e in evs:
   if e.document_id:doc_ids.add(e.document_id)
   a=EvidenceAnalysisService(self.project,settings_manager=self.settings).latest(e.evidence_id);evidence.append({"source":e.title,"date":e.evidence_date,"provider":e.provider_source,"review_status":e.review_status,"description":e.description,"relevance":e.relevance_notes,"analysis":a.result.to_dict() if a and a.result else None,"ocr_text":self.evidence.ocr_text(e.evidence_id) or ""})
  timeline=[]
  for t in self.timeline.list(claim_id=cid):
   if t.document_id:doc_ids.add(t.document_id)
   timeline.append({"source":t.title,"date":t.event_date,"provider":t.provider_facility,"diagnosis":t.diagnosis,"description":t.description,"symptoms":t.symptoms,"functional_impact":t.functional_impact,"service_relevance":t.service_period_relevance})
  nexus=[]
  for n in self.nexus.list(claim_id=cid):doc_ids.update(n.document_ids);nexus.append({"title":n.title,"status":n.status,"theories":n.theories,"content":n.content})
  dbqs=[]
  for d in self.dbqs.list(claim_id=cid):doc_ids.update(d.document_ids);dbqs.append({"title":d.title,"template":d.template_id,"status":d.status,"fields":d.fields,"completeness":self.dbqs.completeness(d.dbq_id)})
  documents=[]
  for did in doc_ids:
   try:d=self.documents.get(did);o=self.ocr.get(did);text=o.text_path.read_text(encoding="utf-8",errors="replace")
   except (KeyError,OSError):d=None;text=""
   documents.append({"source":d.original_name if d else "Document","ocr_text":text})
  return {"claim":{"id":cid,"condition_name":c.condition_name,"type":c.claim_type,"secondary_to":c.secondary_to,"description":c.description,"service_event":c.service_event,"current_diagnosis":c.current_diagnosis,"symptoms":c.symptoms,"notes":c.notes},"evidence":evidence,"timeline":timeline,"nexus_letters":nexus,"dbqs":dbqs,"documents":documents}
 def _baseline(self,x):
  c=x["claim"];alltext=json.dumps(x).lower();strengths=[];weak=[];missing=[];actions=[];support=[];contr=[]
  if c["current_diagnosis"].strip():strengths.append("Current diagnosis is recorded in claim metadata.")
  else:missing.append("Missing current diagnosis documentation.");actions.append("Obtain or identify competent diagnosis evidence.")
  if x["evidence"]:strengths.append(f"{len(x['evidence'])} claim-linked evidence item(s) are available.");support += [f"Evidence: {e['source']}" for e in x["evidence"] if e["review_status"]!="not_relevant"]
  else:missing.append("No claim-linked evidence.");actions.append("Review and link supporting evidence to this claim.")
  if not x["nexus_letters"]:missing.append("Missing nexus evidence or physician-review draft.");actions.append("Develop a medically reasoned nexus opinion where required.")
  if not x["timeline"]:missing.append("Missing chronicity and continuity timeline.");actions.append("Add confirmed timeline events documenting onset and continuity.")
  if not re.search(r"functional|limit|impair|unable",alltext):missing.append("Missing functional-loss evidence.")
  if not re.search(r"work|occupation|employment|economic",alltext):missing.append("Missing occupational-impact evidence.")
  if not re.search(r"severe|moderate|mild|frequency|monthly|weekly|daily|range of motion",alltext):missing.append("Missing severity or frequency evidence.")
  diagnoses={v.strip().lower() for v in [c["current_diagnosis"],*[t["diagnosis"] for t in x["timeline"]]] if v.strip()}
  if len(diagnoses)>1:contr.append("Conflicting diagnoses: "+", ".join(sorted(diagnoses)))
  titles={};
  for t in x["timeline"]:
   key=re.sub(r"\W+"," ",t["source"].lower()).strip();titles.setdefault(key,set()).add(t["date"])
  for key,dates in titles.items():
   if key and len({d for d in dates if d})>1:contr.append(f"Conflicting dates for {key}: "+", ".join(sorted(dates)))
  severity={term for term in ("mild","moderate","severe") if term in alltext}
  if len(severity)>1:contr.append("Conflicting severity descriptions: "+", ".join(sorted(severity)))
  opinions=[]
  for n in x["nexus_letters"]:
   opinion=str(n["content"].get("nexus_opinion","")).lower()
   if any(k in opinion for k in ("less likely","unlikely","not related")):opinions.append("unfavorable")
   if any(k in opinion for k in ("at least as likely","more likely","related")):opinions.append("favorable")
  if len(set(opinions))>1:contr.append("Conflicting provider opinion language appears in nexus drafts.")
  if contr:weak.append("Project sources contain unresolved contradictions.");actions.append("Reconcile contradictory dates, diagnoses, opinions, or severity descriptions without deleting source records.")
  profile=RatingCriteriaEngine().identify_profile(c["condition_name"]);codes=[];estimate="Insufficient evidence for a reliable range";reason="No verified starter diagnostic-code profile is mapped."
  if profile:
   p=STARTER_CRITERIA[profile];codes=[str(p["diagnostic_code"])];supported=[l.percentage for l in p["levels"] if all(term in alltext for term in l.required_concepts)];partial=[l.percentage for l in p["levels"] if any(term in alltext for term in l.required_concepts)];low=max(supported or [0]);high=max(partial or [low]);estimate=f"{low}%–{high}% preliminary evidence-supported range";reason=f"Mapped to the verified-in-app starter profile {profile}; lower bound reflects fully matched concepts and upper bound partially matched concepts. Current criteria must be independently verified."
  secondary=[]
  for source,targets in SECONDARY.items():
   if source in c["condition_name"].lower() or source in alltext:secondary += [f"Possible secondary relationship: {c['condition_name']} → {t}; requires medical and legal review." for t in targets if t.lower() not in c["condition_name"].lower()]
  aggravation=["Consider aggravation theory because worsening/aggravation language appears in project sources; medical baseline and natural progression evidence are needed."] if re.search(r"aggravat|worsen|progress",alltext) else []
  presumptive=["Review possible presumptive theory; verify service, exposure, location, timing, and current law."] if re.search(r"exposure|presumptive|burn pit|agent orange|gulf war",alltext) else []
  weak += missing;return {"strengths":strengths,"weaknesses":weak,"contradictory_evidence":contr,"missing_evidence":missing,"recommended_actions":actions,"secondary_opportunities":secondary,"aggravation_opportunities":aggravation,"presumptive_opportunities":presumptive,"supporting_evidence":support,"diagnostic_codes":codes,"estimated_rating_range":estimate,"estimate_reasoning":reason}
 def _validate(self,p):
  fields=("strengths","weaknesses","contradictory_evidence","missing_evidence","recommended_actions","secondary_opportunities","aggravation_opportunities","presumptive_opportunities","supporting_evidence")
  if not isinstance(p,dict) or any(not isinstance(p.get(k),list) or not all(isinstance(v,str) for v in p[k]) for k in fields) or not isinstance(p.get("generated_reasoning"),str):raise RatingStrategyError("AI provider returned a malformed rating strategy response")
  if str(p.get("confidence","")).lower() not in {"low","medium","high"}:raise RatingStrategyError("AI provider returned invalid confidence")
  return {**{k:[v.strip() for v in p[k] if v.strip()] for k in fields},"generated_reasoning":p["generated_reasoning"].strip(),"confidence":p["confidence"]}
 @staticmethod
 def _confidence(data,estimate):
  penalty=len(data["missing_evidence"])+len(data["contradictory_evidence"]);return "low" if penalty>=4 or estimate.startswith("Insufficient") else "medium" if penalty else "high"
 def _fail(self,run,msg):self.manager.update(run.strategy_id,status="failed",error_message=msg);raise RatingStrategyError(msg)
 def _router(self,s):self.settings.apply_to_environment(s);return AIRouter(s.provider,s.fallback_provider or None)
