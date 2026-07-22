from __future__ import annotations
import json,sqlite3
from pathlib import Path
import pytest
from core.ai.types import AIResponse
from core.claims import ClaimManager
from core.documents import DocumentManager
from core.evidence import EvidenceManager
from core.jobs import JobManager
from core.ocr import OCRManager
from core.projects import AppPaths,ProjectManager
from core.settings import AISettings,SettingsManager
from core.timeline import TimelineExtractionError,TimelineExtractionService,TimelineManager
from workers import TimelineExtractionWorker
def paths(tmp):
 r=tmp/"app";return AppPaths(root=r,projects=r/"Projects",logs=r/"Logs",backups=r/"Backups",settings_file=r/"settings.json").ensure()
def project(tmp):p=paths(tmp);return ProjectManager(p).create_project("Timeline"),p
def event(title="Evaluation",**x):return {"event_date":"2024-03-02","end_date":"","date_precision":"exact","event_type":"diagnosis","title":title,"description":"Back pain evaluation","provider_facility":"Dr. Rivera","body_system_condition":"Spine","treatment":"PT","diagnosis":"Lumbar strain","symptoms":["pain"],"medications":["NSAID"],"testing_imaging":"X-ray","functional_impact":"lifting limited","service_period_relevance":"onset in service","notes":"reviewed",**x}
class Router:
 def __init__(self,payload=None,error=None):self.payload=payload;self.error=error;self.requests=[]
 def generate(self,request):self.requests.append(request);(_ for _ in ()).throw(self.error) if self.error else None;return AIResponse(provider="openai",model="fake",text="",parsed=self.payload)
def service(p,ap,router,settings=None):
 sm=SettingsManager(ap);sm.save_ai_settings(settings or AISettings(openai_api_key="key"));return TimelineExtractionService(p,settings_manager=sm,router_factory=lambda _:router)
def test_timeline_migration_is_idempotent(tmp_path):
 p,ap=project(tmp_path);ProjectManager(ap).open_project(p.root);ProjectManager(ap).open_project(p.root)
 with sqlite3.connect(p.database_path) as c:tables={x[0] for x in c.execute("SELECT name FROM sqlite_master WHERE type='table'")};version=c.execute("SELECT value FROM schema_metadata WHERE key='schema_version'").fetchone()
 assert {"medical_timeline_events","timeline_event_claims","timeline_extractions","timeline_candidates"}<=tables;assert version==("8",)
def test_crud_relationships_filters_sort_reopen_and_csv(tmp_path):
 p,ap=project(tmp_path);claim=ClaimManager(p).create("Back");src=tmp_path/"r.txt";src.write_text("record");doc,_=DocumentManager(p).import_file(src);ev=EvidenceManager(p).create("Evidence",document_id=doc.document_id);m=TimelineManager(p)
 a=m.create("Later",claim_ids=[claim.claim_id],document_id=doc.document_id,evidence_id=ev.evidence_id,**{k:v for k,v in event().items() if k!="title"});b=m.create("Earlier",event_date="2020",date_precision="year",event_type="treatment",provider_facility="VA",body_system_condition="Spine")
 assert [x.title for x in m.list()]==["Earlier","Later"];assert m.list(claim_id=claim.claim_id)[0].event_id==a.event_id;assert m.search("Rivera")[0].event_id==a.event_id
 m.link_claim(a.event_id,claim.claim_id);assert len(m.get(a.event_id).claim_ids)==1;m.unlink_claim(a.event_id,claim.claim_id);m.link_claim(a.event_id,claim.claim_id)
 assert m.update(a.event_id,notes="updated").notes=="updated";assert "Later" in m.narrative();out=m.export_csv(tmp_path/"timeline.csv");assert out.exists()
 reopened=ProjectManager(ap).open_project(p.root);assert TimelineManager(reopened).get(a.event_id).document_name=="r.txt";m.delete(b.event_id);assert len(m.list())==1
def test_duplicate_detection(tmp_path):
 p,_=project(tmp_path);m=TimelineManager(p);m.create(**event());assert m.likely_duplicates(event())
def test_extraction_privacy_structured_candidates_and_review(tmp_path):
 p,ap=project(tmp_path);claim=ClaimManager(p).create("Back");src=tmp_path/"ocr.txt";src.write_text("SSN 123-45-6789 visit");doc,_=DocumentManager(p).import_file(src);OCRManager(p).process(doc.document_id);ev=EvidenceManager(p).create("Record",document_id=doc.document_id)
 payload={"events":[{**event(),"claim_ids":[claim.claim_id],"document_id":doc.document_id,"evidence_id":ev.evidence_id}]};router=Router(payload);s=service(p,ap,router);run=s.extract(evidence_ids=[ev.evidence_id]);c=s.candidates(run.extraction_id)[0]
 assert run.status=="completed" and "123-45-6789" not in router.requests[0].user_prompt;assert s.update_candidate(c.candidate_id,title="Edited").event["title"]=="Edited";s.accept(c.candidate_id);saved=s.save_accepted();assert saved[0].title=="Edited" and saved[0].claim_ids==(claim.claim_id,)
 rejected=s._create_candidate(run.extraction_id,s._validate({**event(title="Reject"),"claim_ids":[]}),None,None);last=s.candidates(run.extraction_id)[-1];assert s.reject(last.candidate_id).status=="rejected"
def test_candidate_merge_and_malformed_failure(tmp_path):
 p,ap=project(tmp_path);s=service(p,ap,Router({"events":[event(title="One"),event(title="Two",description="")]}));run=s.extract();a,b=s.candidates(run.extraction_id);merged=s.merge(a.candidate_id,b.candidate_id);assert s.get_candidate(a.candidate_id).status=="merged" and merged.event["description"]
 bad=service(p,ap,Router({"wrong":[]}));
 with pytest.raises(TimelineExtractionError):bad.extract()
 failing=service(p,ap,Router(error=TimeoutError()))
 with pytest.raises(TimelineExtractionError,match="timed out"):failing.extract()
def test_local_only_background_and_cancellation(tmp_path):
 p,ap=project(tmp_path);router=Router({"events":[]});local=service(p,ap,router,AISettings(local_only=True,openai_api_key="key"))
 with pytest.raises(TimelineExtractionError,match="local-only"):local.extract()
 assert not router.requests
 normal=service(p,ap,Router({"events":[event()]}));w=TimelineExtractionWorker(p,service_factory=lambda _:normal);w.run();assert JobManager(p).get(w.job.job_id).status=="completed"
 cancelled=TimelineExtractionWorker(p,service_factory=lambda _:normal);cancelled.cancel();cancelled.run();assert JobManager(p).get(cancelled.job.job_id).status=="cancelled" and normal.get_extraction(cancelled.extraction.extraction_id).status=="cancelled"
 interrupted=JobManager(p).create("timeline_extraction");JobManager(p).update(interrupted.job_id,status="running");pending=normal.create_pending(job_id=interrupted.job_id);JobManager(p).recover_interrupted();assert normal.get_extraction(pending.extraction_id).status=="failed"
