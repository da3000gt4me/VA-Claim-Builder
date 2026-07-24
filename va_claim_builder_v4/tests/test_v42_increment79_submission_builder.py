from __future__ import annotations
import csv,json,sqlite3,zipfile
from pathlib import Path
from docx import Document
from pypdf import PdfReader,PdfWriter
import pytest
from core.claims import ClaimManager
from core.dbq import DBQManager
from core.documents import DocumentManager
from core.evidence import EvidenceManager
from core.jobs import JobManager
from core.nexus import NexusLetterManager
from core.optimizer import OptimizerManager
from core.projects import AppPaths,ProjectManager
from core.rating_strategy import RatingStrategyManager
from core.submission import PACKAGE_TYPES,SECTION_DEFAULTS,SubmissionGenerationError,SubmissionGenerator,SubmissionManager
from core.timeline import TimelineManager
from workers import SubmissionGenerationWorker
def setup(tmp):root=tmp/"app";paths=AppPaths(root=root,projects=root/"Projects",logs=root/"Logs",backups=root/"Backups",settings_file=root/"settings.json").ensure();p=ProjectManager(paths).create_project("Submission");c=ClaimManager(p).create("Migraines",current_diagnosis="Migraine",service_event="Training onset",symptoms="Monthly headaches affecting work");return p,paths,c
def pdf(path):w=PdfWriter();w.add_blank_page(width=612,height=792);w.write(path)
def test_migration_crud_types_relationships_versions_order_duplicate_and_reopen(tmp_path):
 p,paths,c=setup(tmp_path);src=tmp_path/"record.pdf";pdf(src);doc,_=DocumentManager(p).import_file(src);ev=EvidenceManager(p).create("Record",document_id=doc.document_id);m=SubmissionManager(p);x=m.create("Claim Package","single_claim",claim_ids=[c.claim_id]);m.add_source(x.package_id,"document",doc.document_id,display_name="Medical record");m.add_source(x.package_id,"document",doc.document_id);m.add_source(x.package_id,"evidence",ev.evidence_id);assert len(m.get(x.package_id).sources)==2;m.move_source(x.package_id,"evidence",ev.evidence_id,-1);assert m.get(x.package_id).sources[0].source_type=="evidence";m.configure_source(x.package_id,"evidence",ev.evidence_id,display_name="Renamed exhibit",exhibit_id="EX-A");m.move_section(x.package_id,"submission_overview",-1);m.configure_section(x.package_id,"cover_page",enabled=False,title="Custom Cover");assert len(m.versions(x.package_id))>=5 and len(PACKAGE_TYPES)>=11 and len(SECTION_DEFAULTS)>=20
 copy=m.duplicate(x.package_id);assert len(copy.sources)==2 and copy.claim_ids==(c.claim_id,);assert m.list(package_type="single_claim",claim_id=c.claim_id,search="Claim Package");m.delete(copy.package_id);assert SubmissionManager(ProjectManager(paths).open_project(p.root)).get(x.package_id).sources[0].display_name=="Renamed exhibit"
 with sqlite3.connect(p.database_path) as db:assert db.execute("SELECT value FROM schema_metadata WHERE key='schema_version'").fetchone()==("11",)
def test_validation_blocking_warnings_unsigned_ai_missing_and_malformed_pdf(tmp_path):
 p,_,c=setup(tmp_path);m=SubmissionManager(p);x=m.create("Validation","single_claim",claim_ids=[c.claim_id]);m.add_source(x.package_id,"document","missing",display_name="Missing");issues=m.validate(x.package_id);assert any(i.level=="blocking" and i.code=="missing_source" for i in issues);m.remove_source(x.package_id,"document","missing");bad=tmp_path/"bad.pdf";bad.write_bytes(b"not pdf");doc,_=DocumentManager(p).import_file(bad);m.add_source(x.package_id,"document",doc.document_id);assert any(i.code=="unreadable_pdf" for i in m.validate(x.package_id));m.remove_source(x.package_id,"document",doc.document_id)
 nexus=NexusLetterManager(p).create(c.claim_id,"Draft nexus");m.add_source(x.package_id,"nexus",nexus.letter_id);dbq=DBQManager(p).create(c.claim_id,"headaches_migraines","DBQ");m.add_source(x.package_id,"dbq",dbq.dbq_id,user_confirmed=False);codes={i.code for i in m.validate(x.package_id)};assert {"draft_nexus","unsigned_nexus","examiner_fields","unsupported_ai"}<=codes
def test_generation_pdf_docx_indexes_zip_manifest_checksum_and_history(tmp_path):
 p,_,c=setup(tmp_path);source=tmp_path/"medical.pdf";pdf(source);doc,_=DocumentManager(p).import_file(source);ev=EvidenceManager(p).create("Medical evidence",document_id=doc.document_id);EvidenceManager(p).link_claim(ev.evidence_id,c.claim_id);timeline=TimelineManager(p).create("Neurology visit",claim_ids=[c.claim_id],event_date="2024-01-01",functional_impact="Missed work");rating=RatingStrategyManager(p).create(c.claim_id,status="completed",confidence="medium",estimated_rating_range="10%–30%",contradictory_evidence=["Conflicting date disclosed"],generated_reasoning="Advisory only");opt=OptimizerManager(p).create(c.claim_id,status="completed",overall_score=70,score_explanation={"disclaimer":"No guarantee"});m=SubmissionManager(p);x=m.create("Complete Package","complete_claim",claim_ids=[c.claim_id]);
 for typ,sid,name in (("document",doc.document_id,"Medical PDF"),("evidence",ev.evidence_id,"Evidence"),("timeline",timeline.event_id,"Timeline"),("rating_strategy",rating.strategy_id,"Rating"),("optimizer",opt.assessment_id,"Readiness")):m.add_source(x.package_id,typ,sid,display_name=name)
 result=SubmissionGenerator(p).generate(x.package_id);folder=result["output_folder"];assert (folder/"submission-summary.docx").exists() and (folder/"evidence-index.docx").exists() and (folder/"evidence-index.csv").exists() and (folder/"consolidated-evidence.pdf").exists() and result["zip_path"].exists();assert len(PdfReader(folder/"consolidated-evidence.pdf").pages)==1;manifest=json.loads((folder/"package-manifest.json").read_text());assert manifest["source_checksums"][0]["sha256"]==doc.sha256 and manifest["included_claims"]==["Migraines"] and manifest["validation_summary"]["blocking"]==0;assert len(list(csv.reader((folder/"evidence-index.csv").open())))==6;assert "not legal representation" in "\n".join(p.text for p in Document(folder/"submission-summary.docx").paragraphs);assert zipfile.is_zipfile(result["zip_path"]) and SubmissionManager(p).exports(x.package_id)[0]["status"]=="completed"
def test_blocking_generation_override_cancellation_cleanup_and_recovery(tmp_path):
 p,_,c=setup(tmp_path);m=SubmissionManager(p);x=m.create("Incomplete","single_claim",claim_ids=[c.claim_id]);m.add_source(x.package_id,"document","missing")
 with pytest.raises(SubmissionGenerationError,match="Blocking"):SubmissionGenerator(p).generate(x.package_id)
 result=SubmissionGenerator(p).generate(x.package_id,allow_incomplete=True,cancelled=lambda:True);assert result["status"]=="cancelled" and not any((p.root/"temp").glob("submission-*"));worker=SubmissionGenerationWorker(p,x.package_id,allow_incomplete=True);worker.cancel();worker.run();assert JobManager(p).get(worker.job.job_id).status=="cancelled";j=JobManager(p).create("submission_generation");JobManager(p).update(j.job_id,status="running")
 with m._connect() as db:db.execute("INSERT INTO submission_exports VALUES(?,?,1,'pending','','[]','[]','{}','{}',?,'',?,NULL)",("interrupted",x.package_id,j.job_id,"2026-01-01"))
 JobManager(p).recover_interrupted();assert any(e["export_id"]=="interrupted" and e["status"]=="failed" for e in m.exports(x.package_id))
