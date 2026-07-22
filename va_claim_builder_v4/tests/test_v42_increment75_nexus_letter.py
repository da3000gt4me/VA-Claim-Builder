from __future__ import annotations
import sqlite3
from docx import Document
import pytest
from core.ai.types import AIResponse
from core.claims import ClaimManager
from core.documents import DocumentManager
from core.evidence import EvidenceManager
from core.jobs import JobManager
from core.nexus import NEXUS_THEORIES,NexusGenerationError,NexusGenerationService,NexusLetterManager
from core.projects import AppPaths,ProjectManager
from core.settings import AISettings,SettingsManager
from core.timeline import TimelineManager
from workers import NexusGenerationWorker
def setup(tmp):
 root=tmp/"app";paths=AppPaths(root=root,projects=root/"Projects",logs=root/"Logs",backups=root/"Backups",settings_file=root/"settings.json").ensure();p=ProjectManager(paths).create_project("Nexus");claim=ClaimManager(p).create("Lumbar strain",description="Back disability",service_event="Training injury",current_diagnosis="Lumbar strain",symptoms="Pain");return p,paths,claim
def payload():return {"records_reviewed":"Reviewed Evidence [E1] and Timeline [T1].","service_history":"Training period described in supplied record.","current_diagnosis":"Lumbar strain is documented in the supplied claim.","medical_history":"Symptoms followed the reported injury.","in_service_event":"Training injury is reported; confirmation requires review.","nexus_opinion":"Advisory draft for physician review; no final probability selected.","medical_rationale":"Chronology and a plausible mechanical mechanism support review, while gaps are addressed below.","favorable_evidence":"Documented diagnosis and chronology.","unfavorable_evidence":"No contradictory evidence supplied.","limitations":"Service record confirmation is missing.","signature_block":"Provider name and credentials to be verified.","missing_facts":["Verified service record"],"literature_search_terms":["lumbar strain prognosis"]}
class Router:
 def __init__(self,data=None,error=None):self.data=data;self.error=error;self.requests=[]
 def generate(self,request):self.requests.append(request);(_ for _ in ()).throw(self.error) if self.error else None;return AIResponse(provider="openai",model="fake",text="",parsed=self.data)
def service(p,paths,router,settings=None):sm=SettingsManager(paths);sm.save_ai_settings(settings or AISettings(openai_api_key="key"));return NexusGenerationService(p,settings_manager=sm,router_factory=lambda _:router)
def test_migration_crud_relationships_revisions_duplicate_reopen(tmp_path):
 p,paths,claim=setup(tmp_path);src=tmp_path/"record.txt";src.write_text("record");doc,_=DocumentManager(p).import_file(src);ev=EvidenceManager(p).create("Record",document_id=doc.document_id);event=TimelineManager(p).create("Evaluation");m=NexusLetterManager(p);x=m.create(claim.claim_id,"Lumbar Nexus",primary_theory="direct",theories=("continuity",),content={"current_diagnosis":"Lumbar strain"},evidence_ids=[ev.evidence_id],timeline_event_ids=[event.event_id],document_ids=[doc.document_id])
 m.link_evidence(x.letter_id,ev.evidence_id);assert len(m.get(x.letter_id).evidence_ids)==1;x=m.update(x.letter_id,medical_rationale="Reasoned chronology");assert x.current_version==2 and len(m.versions(x.letter_id))==2
 copy=m.duplicate(x.letter_id);assert copy.current_version==1 and copy.evidence_ids==x.evidence_ids;assert m.list(claim_id=claim.claim_id,theory="direct",search="Lumbar");m.unlink_evidence(copy.letter_id,ev.evidence_id);m.delete(copy.letter_id)
 reopened=ProjectManager(paths).open_project(p.root);assert NexusLetterManager(reopened).get(x.letter_id).content["medical_rationale"]=="Reasoned chronology"
 with sqlite3.connect(p.database_path) as c:assert c.execute("SELECT value FROM schema_metadata WHERE key='schema_version'").fetchone()==("7",);assert c.execute("SELECT count(*) FROM nexus_letter_versions").fetchone()[0]==2
def test_supported_theories_literature_and_docx_export(tmp_path):
 p,_,claim=setup(tmp_path);m=NexusLetterManager(p)
 for theory in NEXUS_THEORIES:
  x=m.create(claim.claim_id,f"{theory} draft",primary_theory=theory,theories=NEXUS_THEORIES);assert x.primary_theory==theory
 lid=x.letter_id;m.update(lid,records_reviewed="Service and treatment records",nexus_opinion="Draft opinion",medical_rationale="Evidence-linked rationale",signature_block="Provider signature placeholder");m.add_literature(lid,"Manual verified article",author="A. Author",year="2020",doi_url="https://doi.example",verified=True);m.add_literature(lid,"Candidate reference",verified=False)
 out=m.export_docx(lid,tmp_path/"nexus.docx",claimant_name="Veteran Name",include_claimant=False);text="\n".join(p.text for p in Document(out).paragraphs);assert "Veteran Name" not in text and "Requires review and signature" in text and "Manual verified article" in text and lid not in text
def test_ai_structured_redaction_missing_facts_and_no_final_probability(tmp_path):
 p,paths,claim=setup(tmp_path);ev=EvidenceManager(p).create("Private record",description="SSN 123-45-6789");event=TimelineManager(p).create("Evaluation",event_date="2020");m=NexusLetterManager(p);x=m.create(claim.claim_id,"Draft",primary_theory="secondary",theories=("secondary_aggravation",),content={"user_facts":"Only supplied facts"},evidence_ids=[ev.evidence_id],timeline_event_ids=[event.event_id]);router=Router(payload());s=service(p,paths,router);run=s.generate(x.letter_id);saved=m.get(x.letter_id)
 assert run["status"]=="completed" and run["redaction_applied"] and "123-45-6789" not in router.requests[0].user_prompt;assert saved.content["probability_language"]=="" and saved.content["missing_facts"]==["Verified service record"] and "Requires review" in saved.content["signature_block"];assert m.versions(x.letter_id)[0].ai_metadata["advisory"]
def test_local_only_malformed_provider_failure_and_cancellation(tmp_path):
 p,paths,claim=setup(tmp_path);x=NexusLetterManager(p).create(claim.claim_id,"Draft");router=Router(payload());local=service(p,paths,router,AISettings(local_only=True,openai_api_key="key"))
 with pytest.raises(NexusGenerationError,match="local-only"):local.generate(x.letter_id)
 assert not router.requests
 for bad,match in ((Router({"bad":1}),"missing required"),(Router(error=TimeoutError()),"timed out")):
  with pytest.raises(NexusGenerationError,match=match):service(p,paths,bad).generate(x.letter_id)
 normal=service(p,paths,Router(payload()));w=NexusGenerationWorker(p,x.letter_id,service_factory=lambda _:normal);w.cancel();w.run();assert JobManager(p).get(w.job.job_id).status=="cancelled" and normal.get(w.generation["generation_id"])["status"]=="cancelled"
 interrupted=JobManager(p).create("nexus_generation");JobManager(p).update(interrupted.job_id,status="running");pending=normal.create_pending(x.letter_id,interrupted.job_id);JobManager(p).recover_interrupted();assert normal.get(pending["generation_id"])["status"]=="failed"
