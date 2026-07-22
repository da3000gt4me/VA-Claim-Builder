from __future__ import annotations
import json,re
from datetime import datetime,timezone
from core.ai.router import AIRouter
from core.ai.types import AIRequest
from core.claims import ClaimManager
from core.dbq import DBQManager
from core.evidence import EvidenceManager
from core.nexus import NexusLetterManager
from core.rating_strategy import RatingStrategyManager
from core.security.redaction import redact_identifiers
from core.settings import SettingsManager
from core.timeline import TimelineManager
from .manager import OptimizerManager
from .taxonomy import GAP_CATEGORIES
class OptimizerError(RuntimeError):pass
RULES={
"missing_current_diagnosis":("Current diagnosis is not documented.","critical",1,"Obtain or identify competent current diagnosis evidence.","claimant/provider"),"weak_in_service_event":("In-service event documentation is missing or weak.","critical",1,"Request service treatment, personnel, or duty records and prepare a fact-specific statement.","claimant/records custodian"),"weak_nexus_evidence":("A medically reasoned nexus is missing or incomplete.","critical",1,"Obtain a medical nexus opinion or complete qualified-provider review of the nexus draft.","provider"),"missing_chronicity":("Chronicity is not adequately documented.","high",2,"Obtain longitudinal treatment records documenting persistence.","claimant"),"missing_continuity":("Continuity from onset to the present is not adequately documented.","high",2,"Prepare a claimant statement and link dated records showing continuity.","claimant"),"insufficient_severity":("Current severity evidence is incomplete.","high",2,"Complete an appropriate examination or DBQ and document current severity.","provider"),"insufficient_frequency_duration":("Frequency or duration evidence is incomplete.","medium",3,"Maintain a condition-specific symptom log with dates, frequency, and duration.","claimant"),"missing_functional_impact":("Functional-loss evidence is missing.","high",2,"Document specific functional limitations, including flare-ups and repeated use.","claimant/provider"),"missing_occupational_impact":("Occupational-impact evidence is missing.","medium",3,"Document work limitations, absences, accommodations, and productivity impact.","claimant/employer"),"missing_activities_daily_living":("Activities-of-daily-living impact is missing.","medium",4,"Document personally observed effects on routine daily activities.","claimant/witness"),"missing_flare_ups":("Flare-up evidence is missing.","medium",3,"Document flare-up frequency, duration, triggers, and functional effects.","claimant"),"missing_repeated_use":("Repeated-use limitations are missing.","medium",3,"Ask the examiner to address repeated-use functional loss.","provider"),"missing_examiner_findings":("Required examiner-only findings or measurements are missing.","critical",1,"Complete an official examination or provider-completed DBQ.","provider"),"missing_treatment_history":("Medication or treatment history is incomplete.","medium",4,"Obtain medication lists and treatment records.","claimant/provider"),"missing_testing_imaging":("Relevant diagnostic testing or imaging is missing.","medium",3,"Obtain clinically appropriate testing or imaging if the provider determines it is needed.","provider"),"missing_lay_evidence":("Lay evidence could strengthen observable symptom and continuity facts.","low",5,"Prepare a claimant statement using confirmed facts.","claimant"),"missing_buddy_statement":("A service buddy statement may help corroborate personally observed events.","low",5,"Ask a witness with personal knowledge for a signed statement.","service buddy"),"missing_provider_statement":("Provider clarification is missing.","high",2,"Send a focused provider-review request without requesting a predetermined outcome.","provider"),"conflicting_diagnosis":("Project sources contain conflicting diagnoses.","critical",1,"Request provider clarification of the diagnoses and supporting rationale.","provider"),"conflicting_date":("Project sources contain conflicting dates.","high",2,"Clarify dates and preserve each source record.","claimant/provider"),"conflicting_severity":("Project sources contain conflicting severity descriptions.","high",2,"Reconcile severity across dates and explain changes or flare-ups.","claimant/provider"),"conflicting_provider_opinion":("Project sources contain conflicting provider opinions.","critical",1,"Obtain clarification addressing both favorable and unfavorable reasoning.","provider"),"duplicate_irrelevant_evidence":("Duplicate or irrelevant evidence needs review.","low",5,"Mark duplicates or irrelevant items without deleting source records.","claimant"),"unsupported_factual_assertion":("A factual assertion lacks traceable support.","high",2,"Verify the fact against a source record or remove it from the work product.","claimant"),"unverified_ai_information":("AI-generated information remains unverified.","high",2,"Verify the AI-suggested fact against source records before use.","claimant/provider")}
class ClaimOptimizerEngine:
 def __init__(self,project,*,settings_manager=None,router_factory=None):self.project=project;self.settings=settings_manager or SettingsManager();self.router_factory=router_factory or self._router;self.manager=OptimizerManager(project);self.claims=ClaimManager(project);self.evidence=EvidenceManager(project);self.timeline=TimelineManager(project);self.nexus=NexusLetterManager(project);self.dbqs=DBQManager(project);self.strategies=RatingStrategyManager(project)
 def create_pending(self,cid,job_id=None):self.claims.get(cid);return self.manager.create(cid,job_id=job_id)
 def analyze(self,cid,*,job_id=None,assessment_id=None,cancelled=lambda:False):
  run=self.manager.get(assessment_id) if assessment_id else self.create_pending(cid,job_id);s=self.settings.load_ai_settings()
  if cancelled():return self.manager.update(run.assessment_id,status="cancelled",error_message="Optimization cancelled")
  if s.local_only:return self._fail(run,"Claim optimization is unavailable while local-only mode is enabled")
  if s.provider not in {"openai","xai"}:return self._fail(run,"AI provider is unavailable")
  if not any({"openai":s.openai_api_key,"xai":s.xai_api_key}.get(p) for p in (s.provider,s.fallback_provider)):return self._fail(run,"AI provider credentials are not configured")
  try:
   context=self._context(cid);rule_gaps=self._rule_gaps(context);scores=self._scores(context,rule_gaps);prompt=json.dumps({"confirmed_project_context":context,"rule_based_gaps":rule_gaps,"deterministic_scores":scores});redacted=bool(s.redact_before_cloud)
   if redacted:prompt,_=redact_identifiers(prompt)
   response=self.router_factory(s).generate(AIRequest(task="claim_optimizer",system_prompt="Suggest evidence-development gaps and actions using supplied facts only. Never invent evidence, medical findings, witnesses, or completion. Return JSON only.",user_prompt="Return {gaps:[{category,description,severity,priority,confidence,evidence_basis,recommended_resolution,responsible_party}], actions:[{description,priority,expected_value,effort_level,dependency}], reasoning}. Suggestions are advisory. Data:\n"+prompt,json_schema={"type":"object"}))
   if cancelled():return self.manager.update(run.assessment_id,status="cancelled",error_message="Optimization cancelled")
   ai=self._validate(response.parsed);existing=set();gap_map={}
   for g in rule_gaps+ai["gaps"]:
    key=(g["category"],g["description"].lower())
    if key in existing:continue
    existing.add(key);record=self.manager.add_gap(run.assessment_id,origin="rule" if g in rule_gaps else "ai",user_confirmation="pending" if g not in rule_gaps else "confirmed",**g);gap_map[g["category"]]=record.gap_id
   prior_completed=self._completed_actions(cid);actions=self._rank_actions(rule_gaps,ai["actions"])
   for a in actions:
    if a["description"].strip().lower() in prior_completed:continue
    self.manager.add_action(run.assessment_id,gap_id=gap_map.get(a.pop("category",None)),origin=a.pop("origin","rule"),**a)
   meta={"provider":response.provider,"model":response.model,"redaction_applied":redacted,"generated_at":datetime.now(timezone.utc).isoformat(),"advisory":True,"ai_reasoning":ai["reasoning"]};return self.manager.update(run.assessment_id,status="completed",confidence=scores["confidence"],ai_metadata=meta,**scores["values"],score_explanation=scores["explanation"])
  except Exception as exc:
   msg=str(exc) if isinstance(exc,OptimizerError) else ("AI provider timed out" if "timeout" in type(exc).__name__.lower() else f"AI provider failed: {type(exc).__name__}");self.manager.update(run.assessment_id,status="failed",error_message=msg[:500]);raise OptimizerError(msg) from exc
 def cancel_pending(self,aid):return self.manager.update(aid,status="cancelled",error_message="Optimization cancelled")
 def _context(self,cid):
  c=self.claims.get(cid);ev=self.evidence.list(claim_id=cid);timeline=self.timeline.list(claim_id=cid);nexus=self.nexus.list(claim_id=cid);dbqs=self.dbqs.list(claim_id=cid);strategies=self.strategies.history(cid);latest=strategies[0] if strategies else None
  return {"claim":{"condition":c.condition_name,"type":c.claim_type,"diagnosis":c.current_diagnosis,"service_event":c.service_event,"symptoms":c.symptoms,"description":c.description,"notes":c.notes},"evidence":[{"source":e.title,"review_status":e.review_status,"duplicate":bool(e.duplicate_of_evidence_id),"description":e.description,"notes":e.relevance_notes,"ocr_available":e.ocr_text_available} for e in ev],"timeline":[{"source":t.title,"date":t.event_date,"diagnosis":t.diagnosis,"treatment":t.treatment,"testing":t.testing_imaging,"impact":t.functional_impact,"service_relevance":t.service_period_relevance} for t in timeline],"nexus":[{"title":n.title,"status":n.status,"content":n.content} for n in nexus],"dbqs":[{"title":d.title,"status":d.status,"fields":d.fields,"completeness":self.dbqs.completeness(d.dbq_id),"suggestions":d.suggestions} for d in dbqs],"rating_strategy":{"strengths":latest.strengths,"weaknesses":latest.weaknesses,"missing":latest.missing_evidence,"contradictions":latest.contradictory_evidence,"actions":latest.recommended_actions} if latest else None}
 def _rule_gaps(self,x):
  text=json.dumps(x).lower();c=x["claim"];cats=[]
  def add(cat,basis=()):
   d,severity,priority,resolution,party=RULES[cat];cats.append({"category":cat,"description":d,"severity":severity,"priority":priority,"confidence":"high","evidence_basis":list(basis),"recommended_resolution":resolution,"responsible_party":party})
  if not c["diagnosis"].strip():add("missing_current_diagnosis")
  if not c["service_event"].strip() and not any(t["service_relevance"] for t in x["timeline"]):add("weak_in_service_event")
  if not x["nexus"]:add("weak_nexus_evidence")
  if len(x["timeline"])<2:add("missing_chronicity")
  if not x["timeline"]:add("missing_continuity")
  if not re.search(r"severe|moderate|mild|frequency|daily|weekly|monthly",text):add("insufficient_severity")
  if not re.search(r"daily|weekly|monthly|duration|hours|days",text):add("insufficient_frequency_duration")
  if not re.search(r"functional|limit|unable|impair",text):add("missing_functional_impact")
  if not re.search(r"work|occupation|employment|absence|accommodation",text):add("missing_occupational_impact")
  if not re.search(r"daily living|bathing|dressing|chores|driving",text):add("missing_activities_daily_living")
  if not re.search(r"flare",text):add("missing_flare_ups")
  if not re.search(r"repeated use",text):add("missing_repeated_use")
  if not x["dbqs"] or any(d["completeness"]["examiner_only"] for d in x["dbqs"]):add("missing_examiner_findings")
  if not re.search(r"medication|treatment|therapy|surgery",text):add("missing_treatment_history")
  if not re.search(r"imaging|x-ray|mri|ct|test|study",text):add("missing_testing_imaging")
  if not re.search(r"statement|lay evidence|spouse|buddy",text):add("missing_lay_evidence")
  for e in x["evidence"]:
   if e["duplicate"] or e["review_status"]=="not_relevant":add("duplicate_irrelevant_evidence",[e["source"]]);break
  if any(d.get("suggestions") and any(s.get("decision")=="pending" for s in d["suggestions"]) for d in x["dbqs"]):add("unverified_ai_information")
  if x["rating_strategy"]:
   mapping=(("conflicting diagnos","conflicting_diagnosis"),("conflicting dates","conflicting_date"),("severity descriptions","conflicting_severity"),("provider opinion","conflicting_provider_opinion"))
   for item in x["rating_strategy"]["contradictions"]:
    for needle,cat in mapping:
     if needle in item.lower():add(cat,[item])
  return cats
 def _scores(self,x,gaps):
  cats={g["category"] for g in gaps};critical=sum(g["severity"]=="critical" for g in gaps);service=max(0,100-sum(25 for c in ("missing_current_diagnosis","weak_in_service_event","weak_nexus_evidence","missing_chronicity","missing_continuity") if c in cats));severity=max(0,100-sum(15 for c in ("insufficient_severity","insufficient_frequency_duration","missing_functional_impact","missing_occupational_impact","missing_flare_ups","missing_repeated_use","missing_examiner_findings") if c in cats));quality=max(0,100-min(70,len(gaps)*5));consistency=max(0,100-sum(20 for c in ("conflicting_diagnosis","conflicting_date","conflicting_severity","conflicting_provider_opinion","duplicate_irrelevant_evidence","unverified_ai_information") if c in cats));overall=round(service*.35+severity*.3+quality*.2+consistency*.15);values={"overall_score":overall,"service_connection_score":service,"severity_rating_score":severity,"evidence_quality_score":quality,"evidence_consistency_score":consistency};explanation={"formula":"overall = 35% service connection + 30% severity/rating + 20% evidence quality + 15% consistency","increasing_factors":[k for k,v in values.items() if v>=75],"decreasing_factors":[g["category"] for g in gaps],"component_scores":values,"disclaimer":"Readiness scores are deterministic development aids and do not guarantee VA approval or any disability percentage."};return {"values":values,"explanation":explanation,"confidence":"low" if critical>=2 else "medium" if gaps else "high"}
 def _validate(self,p):
  if not isinstance(p,dict) or not isinstance(p.get("gaps"),list) or not isinstance(p.get("actions"),list) or not isinstance(p.get("reasoning"),str):raise OptimizerError("AI provider returned a malformed optimizer response")
  gaps=[]
  for g in p["gaps"]:
   if not isinstance(g,dict) or g.get("category") not in GAP_CATEGORIES:raise OptimizerError("AI provider returned an unsupported gap category")
   if g.get("severity") not in {"low","medium","high","critical"} or g.get("confidence") not in {"low","medium","high"}:raise OptimizerError("AI provider returned malformed gap metadata")
   gaps.append({"category":g["category"],"description":str(g.get("description","")),"severity":g["severity"],"priority":max(1,min(5,int(g.get("priority",3)))),"confidence":g["confidence"],"evidence_basis":[str(v) for v in g.get("evidence_basis",[])],"recommended_resolution":str(g.get("recommended_resolution","")),"responsible_party":str(g.get("responsible_party",""))})
  actions=[]
  for a in p["actions"]:
   if not isinstance(a,dict):raise OptimizerError("AI provider returned malformed action plan")
   actions.append({"description":str(a.get("description","")),"priority":max(1,min(5,int(a.get("priority",3)))),"expected_value":str(a.get("expected_value","medium")),"effort_level":str(a.get("effort_level","medium")),"dependency":str(a.get("dependency","")),"origin":"ai"})
  return {"gaps":gaps,"actions":actions,"reasoning":p["reasoning"]}
 def _rank_actions(self,gaps,ai):
  rule=[{"description":g["recommended_resolution"],"priority":g["priority"],"expected_value":"high" if g["severity"] in {"critical","high"} else "medium","effort_level":"medium","dependency":"Resolve supporting gap first" if g["priority"]>1 else "","category":g["category"],"origin":"rule"} for g in gaps];seen=set();out=[]
  for a in sorted(rule+ai,key=lambda x:(x["priority"],{"high":0,"medium":1,"low":2}.get(x["expected_value"],1))):
   key=a["description"].strip().lower()
   if key and key not in seen:seen.add(key);out.append(dict(a))
  return out
 def _completed_actions(self,cid):
  history=self.manager.history(cid);result=set()
  for assessment in history:
   for a in self.manager.actions(assessment.assessment_id,status="completed"):result.add(a.description.strip().lower())
  return result
 def _fail(self,run,msg):self.manager.update(run.assessment_id,status="failed",error_message=msg);raise OptimizerError(msg)
 def _router(self,s):self.settings.apply_to_environment(s);return AIRouter(s.provider,s.fallback_provider or None)
