from __future__ import annotations
import sqlite3
from docx import Document
import pytest
from core.ai.types import AIResponse
from core.claims import ClaimManager
from core.dbq import DBQManager,DBQPreparationError,DBQPreparationService,get_template,list_templates
from core.documents import DocumentManager
from core.evidence import EvidenceManager
from core.jobs import JobManager
from core.nexus import NexusLetterManager
from core.projects import AppPaths,ProjectManager
from core.settings import AISettings,SettingsManager
from core.timeline import TimelineManager
from workers import DBQPreparationWorker
def setup(tmp):root=tmp/"app";paths=AppPaths(root=root,projects=root/"Projects",logs=root/"Logs",backups=root/"Backups",settings_file=root/"settings.json").ensure();p=ProjectManager(paths).create_project("DBQ");claim=ClaimManager(p).create("Migraines",current_diagnosis="Migraine",symptoms="Headache and nausea");return p,paths,claim
class Router:
 def __init__(self,data=None,error=None):self.data=data;self.error=error;self.requests=[]
 def generate(self,request):self.requests.append(request);(_ for _ in ()).throw(self.error) if self.error else None;return AIResponse(provider="openai",model="fake",text="",parsed=self.data)
def suggestion(field="claimant_reported_symptoms",value="Weekly headaches",kind="claimant_reported",conflict=""):return {"field_key":field,"proposed_value":value,"information_class":kind,"confidence":"medium","source_ids":["E1"],"source_labels":["Headache diary"],"missing_information":[],"conflicting_information":conflict,"requires_examiner":False,"advisory_note":"Verify frequency."}
def service(p,paths,router,settings=None):sm=SettingsManager(paths);sm.save_ai_settings(settings or AISettings(openai_api_key="key"));return DBQPreparationService(p,settings_manager=sm,router_factory=lambda _:router)
def test_templates_cover_required_types_and_examiner_fields():
 assert len(list_templates())>=14;assert get_template("general_medical").name=="General Medical";assert get_template("back_thoracolumbar").fields[-1].key=="range_of_motion" and get_template("back_thoracolumbar").fields[-1].kind=="examiner";assert get_template("mental_disorders").fields[-1].kind=="examiner"
def test_migration_crud_relationships_revisions_duplicate_and_reopen(tmp_path):
 p,paths,claim=setup(tmp_path);src=tmp_path/"r.txt";src.write_text("medical");doc,_=DocumentManager(p).import_file(src);ev=EvidenceManager(p).create("Diary",document_id=doc.document_id);event=TimelineManager(p).create("Visit");m=DBQManager(p);x=m.create(claim.claim_id,"headaches_migraines","Migraine DBQ",condition="Migraines",fields={"claimant_reported_symptoms":"Headache"},evidence_ids=[ev.evidence_id],timeline_event_ids=[event.event_id],document_ids=[doc.document_id]);m.link_evidence(x.dbq_id,ev.evidence_id);assert len(m.get(x.dbq_id).evidence_ids)==1;x=m.update(x.dbq_id,treatment_history="Medication");assert x.revision_number==2 and len(m.revisions(x.dbq_id))==2;copy=m.duplicate(x.dbq_id);assert copy.evidence_ids==x.evidence_ids;m.unlink_evidence(copy.dbq_id,ev.evidence_id);m.delete(copy.dbq_id);assert DBQManager(ProjectManager(paths).open_project(p.root)).get(x.dbq_id).fields["treatment_history"]=="Medication"
 with sqlite3.connect(p.database_path) as c:assert c.execute("SELECT value FROM schema_metadata WHERE key='schema_version'").fetchone()==("10",);assert {"dbq_records","dbq_revisions","dbq_generations"}<={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
def test_structured_ai_redaction_classification_accept_reject_and_no_fabrication(tmp_path):
 p,paths,claim=setup(tmp_path);ev=EvidenceManager(p).create("Headache diary",description="SSN 123-45-6789 weekly symptoms");event=TimelineManager(p).create("Neurology visit");NexusLetterManager(p).create(claim.claim_id,"Nexus context");m=DBQManager(p);x=m.create(claim.claim_id,"headaches_migraines","Migraine DBQ",evidence_ids=[ev.evidence_id],timeline_event_ids=[event.event_id]);exam=suggestion("prostrating_attacks","Three monthly","documented");data={"suggestions":[suggestion(),exam]};router=Router(data);s=service(p,paths,router);run=s.prepare(x.dbq_id);saved=m.get(x.dbq_id)
 assert run["status"]=="completed" and "123-45-6789" not in router.requests[0].user_prompt;assert saved.suggestions[1]["proposed_value"]=="" and saved.suggestions[1]["requires_examiner"] is True;assert saved.suggestions[0]["information_class"]=="claimant_reported";m.decide_suggestion(x.dbq_id,"claimant_reported_symptoms",True);assert m.get(x.dbq_id).fields["claimant_reported_symptoms"]=="Weekly headaches";m.decide_suggestion(x.dbq_id,"prostrating_attacks",False);assert m.get(x.dbq_id).fields["prostrating_attacks"]==""
def test_completeness_gaps_conflicts_and_docx(tmp_path):
 p,_,claim=setup(tmp_path);m=DBQManager(p);x=m.create(claim.claim_id,"general_medical","General DBQ",condition="Migraines",fields={"claimant_reported_symptoms":"Pain","diagnoses":"Migraine"});m.create_ai_revision(x.dbq_id,[suggestion(conflict="Frequency differs across sources")],{"advisory":True});g=m.completeness(x.dbq_id);assert g["score"]<100 and "medical_history" in g["incomplete"] and "claimant_reported_symptoms" in g["conflicting"] and "objective_findings" in g["examiner_only"] and "guarantee" in g["disclaimer"]
 out=m.export_docx(x.dbq_id,tmp_path/"dbq.docx");text="\n".join(x.text for x in Document(out).paragraphs);assert "not an official VA DBQ" in text and "Examiner/provider completion required" in text and x.dbq_id not in text
def test_local_only_malformed_failure_background_and_cancellation(tmp_path):
 p,paths,claim=setup(tmp_path);x=DBQManager(p).create(claim.claim_id,"general_medical","DBQ");router=Router({"suggestions":[]});local=service(p,paths,router,AISettings(local_only=True,openai_api_key="key"))
 with pytest.raises(DBQPreparationError,match="local-only"):local.prepare(x.dbq_id)
 assert not router.requests
 for bad,match in ((Router({"wrong":[]}),"malformed"),(Router(error=TimeoutError()),"timed out")):
  with pytest.raises(DBQPreparationError,match=match):service(p,paths,bad).prepare(x.dbq_id)
 normal=service(p,paths,Router({"suggestions":[]}));w=DBQPreparationWorker(p,x.dbq_id,service_factory=lambda _:normal);w.cancel();w.run();assert JobManager(p).get(w.job.job_id).status=="cancelled" and normal.get(w.generation["generation_id"])["status"]=="cancelled";j=JobManager(p).create("dbq_preparation");JobManager(p).update(j.job_id,status="running");pending=normal.create_pending(x.dbq_id,j.job_id);JobManager(p).recover_interrupted();assert normal.get(pending["generation_id"])["status"]=="failed"
