from __future__ import annotations
import sqlite3
import pytest
from core.ai.types import AIResponse
from core.claims import ClaimManager
from core.dbq import DBQManager
from core.evidence import EvidenceManager
from core.jobs import JobManager
from core.nexus import NexusLetterManager
from core.projects import AppPaths,ProjectManager
from core.rating_strategy import RatingStrategyEngine,RatingStrategyError,RatingStrategyManager
from core.settings import AISettings,SettingsManager
from core.timeline import TimelineManager
from workers import RatingStrategyWorker
def setup(tmp,name="Migraines",**claim_data):root=tmp/"app";paths=AppPaths(root=root,projects=root/"Projects",logs=root/"Logs",backups=root/"Backups",settings_file=root/"settings.json").ensure();p=ProjectManager(paths).create_project("Strategy");c=ClaimManager(p).create(name,**claim_data);return p,paths,c
def response(**extra):
 base={"strengths":["Corroborating project evidence"],"weaknesses":[],"contradictory_evidence":[],"missing_evidence":[],"recommended_actions":["Verify current rating criteria"],"secondary_opportunities":[],"aggravation_opportunities":[],"presumptive_opportunities":[],"supporting_evidence":["Headache diary"],"confidence":"medium","generated_reasoning":"The evidence supports preliminary development recommendations without guaranteeing an outcome."};base.update(extra);return base
class Router:
 def __init__(self,data=None,error=None):self.data=data;self.error=error;self.requests=[]
 def generate(self,request):self.requests.append(request);(_ for _ in ()).throw(self.error) if self.error else None;return AIResponse(provider="openai",model="fake",text="",parsed=self.data)
def engine(p,paths,router,settings=None):sm=SettingsManager(paths);sm.save_ai_settings(settings or AISettings(openai_api_key="key"));return RatingStrategyEngine(p,settings_manager=sm,router_factory=lambda _:router)
def test_migration_manager_history_filter_search_and_reopen(tmp_path):
 p,paths,c=setup(tmp_path,current_diagnosis="Migraine");m=RatingStrategyManager(p);a=m.create(c.claim_id,status="completed",confidence="medium",estimated_rating_range="10%–30%",strengths=["Diagnosis"]);b=m.create(c.claim_id,status="failed",error_message="provider failure");assert len(m.history(c.claim_id))==2 and m.list(status="completed",confidence="medium",search="Diagnosis")[0].strategy_id==a.strategy_id;m.update(b.strategy_id,status="cancelled");m.delete(b.strategy_id);assert RatingStrategyManager(ProjectManager(paths).open_project(p.root)).get(a.strategy_id).estimated_rating_range=="10%–30%"
 with sqlite3.connect(p.database_path) as db:assert db.execute("SELECT value FROM schema_metadata WHERE key='schema_version'").fetchone()==("8",);assert db.execute("SELECT count(*) FROM rating_strategies").fetchone()==(1,)
def test_integrated_estimation_gaps_and_all_project_sources(tmp_path):
 p,paths,c=setup(tmp_path,current_diagnosis="Migraine",symptoms="Monthly prostrating headaches with severe work impairment");ev=EvidenceManager(p).create("Headache diary",description="Monthly prostrating attacks and mild days");EvidenceManager(p).link_claim(ev.evidence_id,c.claim_id,relevance_notes="severity");TimelineManager(p).create("Neurology visit",claim_ids=[c.claim_id],event_date="2024-01-01",diagnosis="Migraine",functional_impact="Missed work");NexusLetterManager(p).create(c.claim_id,"Migraine nexus",content={"nexus_opinion":"At least as likely as not related"});DBQManager(p).create(c.claim_id,"headaches_migraines","Migraine DBQ",fields={"claimant_reported_symptoms":"Monthly prostrating attacks","diagnoses":"Migraine","medical_history":"Chronic headaches","functional_impact":"Missed work"});router=Router(response());result=engine(p,paths,router).analyze(c.claim_id)
 assert result.status=="completed" and result.diagnostic_codes==("8100",) and result.estimated_rating_range.startswith("30%–50%") and "not guaranteed" in result.generated_reasoning;prompt=router.requests[0].user_prompt;assert all(x in prompt for x in ("Headache diary","Neurology visit","Migraine nexus","Migraine DBQ"));assert result.supporting_evidence
def test_contradictions_secondary_aggravation_presumptive_and_confidence(tmp_path):
 p,paths,c=setup(tmp_path,"Anxiety",current_diagnosis="Generalized anxiety",description="Symptoms worsened after burn pit exposure; severe episodes");TimelineManager(p).create("Evaluation",claim_ids=[c.claim_id],event_date="2020",diagnosis="Panic disorder",description="mild symptoms");TimelineManager(p).create("Evaluation",claim_ids=[c.claim_id],event_date="2021",diagnosis="Anxiety",description="severe symptoms");NexusLetterManager(p).create(c.claim_id,"Positive",content={"nexus_opinion":"At least as likely as not related"});NexusLetterManager(p).create(c.claim_id,"Negative",content={"nexus_opinion":"Less likely than not related"});r=engine(p,paths,Router(response())).analyze(c.claim_id)
 assert any("Conflicting dates" in x for x in r.contradictory_evidence) and any("Conflicting diagnoses" in x for x in r.contradictory_evidence) and any("provider opinion" in x for x in r.contradictory_evidence);assert any("IBS" in x for x in r.secondary_opportunities) and r.aggravation_opportunities and r.presumptive_opportunities and r.confidence=="low"
def test_privacy_malformed_provider_failure_background_cancel_and_recovery(tmp_path):
 p,paths,c=setup(tmp_path,current_diagnosis="Migraine",notes="SSN 123-45-6789");router=Router(response());s=engine(p,paths,router);r=s.analyze(c.claim_id);assert r.ai_metadata["redaction_applied"] and "123-45-6789" not in router.requests[0].user_prompt
 local=engine(p,paths,router,AISettings(local_only=True,openai_api_key="key"))
 with pytest.raises(RatingStrategyError,match="local-only"):local.analyze(c.claim_id)
 for bad,match in ((Router({"bad":1}),"malformed"),(Router(error=TimeoutError()),"timed out")):
  with pytest.raises(RatingStrategyError,match=match):engine(p,paths,bad).analyze(c.claim_id)
 normal=engine(p,paths,Router(response()));w=RatingStrategyWorker(p,[c.claim_id],engine_factory=lambda _:normal);w.cancel();w.run();assert JobManager(p).get(w.job.job_id).status=="cancelled";j=JobManager(p).create("rating_strategy");JobManager(p).update(j.job_id,status="running");pending=normal.create_pending(c.claim_id,j.job_id);JobManager(p).recover_interrupted();assert normal.manager.get(pending.strategy_id).status=="failed"
