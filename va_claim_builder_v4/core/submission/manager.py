from __future__ import annotations
import json,sqlite3,uuid
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
from core.projects.manager import SUBMISSION_SCHEMA
def _now():return datetime.now(timezone.utc).isoformat()
PACKAGE_TYPES=("complete_claim","single_claim","supplemental_evidence","higher_level_review_reference","physician_review","nexus_review","dbq_preparation","claimant_statement","witness_statement","evidence_only","internal_review")
SECTION_DEFAULTS=(("cover_page","Cover Page"),("submission_overview","Submission Overview"),("claim_list","Claim List"),("executive_summary","Executive Claim Summary"),("table_of_contents","Table of Contents"),("evidence_index","Evidence Index"),("exhibit_list","Exhibit List"),("service_history","Service History"),("medical_chronology","Medical Chronology"),("claim_evidence_summaries","Claim-Specific Evidence Summaries"),("claimant_statements","Claimant Statements"),("witness_statements","Buddy or Witness Statements"),("medical_records","Medical Records"),("service_records","Service Records"),("nexus_letters","Nexus Letters"),("dbq_materials","DBQ Preparation Materials"),("testing_imaging","Diagnostic Testing and Imaging Summaries"),("medications_treatment","Medication and Treatment History"),("rating_strategy","Rating Strategy Summary"),("optimizer_summary","Evidence-Gap and Readiness Summary"),("contradictory_evidence","Unfavorable or Contradictory Evidence Disclosure"),("appendices","Appendices"),("signature_pages","Signature Pages"),("validation_report","Validation Report"))
SOURCE_TYPES=("document","evidence","timeline","nexus","dbq","rating_strategy","optimizer","claimant_statement","witness_statement","provider_request")
@dataclass(frozen=True,slots=True)
class SubmissionSource:package_id:str;source_type:str;source_id:str;display_name:str;exhibit_id:str;sort_order:int;section_key:str;user_confirmed:bool
@dataclass(frozen=True,slots=True)
class SubmissionPackage:package_id:str;name:str;package_type:str;status:str;package_version:int;user_notes:str;generated_at:str|None;created_at:str;updated_at:str;claim_ids:tuple[str,...];sources:tuple[SubmissionSource,...];sections:tuple[dict[str,Any],...]
@dataclass(frozen=True,slots=True)
class ValidationIssue:level:str;code:str;message:str;source_type:str="";source_id:str=""
class SubmissionManager:
 def __init__(self,project):
  self.project=project
  from core.documents import DocumentManager
  DocumentManager(project);self._ensure()
 def _connect(self):c=sqlite3.connect(self.project.database_path);c.row_factory=sqlite3.Row;c.execute("PRAGMA foreign_keys=ON");return c
 def create(self,name,package_type,*,status="draft",claim_ids=(),user_notes=""):
  self._validate_meta(name,package_type,status);pid=str(uuid.uuid4());now=_now()
  with self._connect() as c:
   c.execute("INSERT INTO submission_packages VALUES(?,?,?,?,1,?,NULL,?,?)",(pid,name.strip(),package_type,status,user_notes,now,now));c.executemany("INSERT INTO submission_sections VALUES(?,?,?,1,?)",[(pid,k,t,i) for i,(k,t) in enumerate(SECTION_DEFAULTS)])
  for cid in claim_ids:self.link_claim(pid,cid)
  self._snapshot(pid);return self.get(pid)
 def get(self,pid):
  with self._connect() as c:
   r=c.execute("SELECT * FROM submission_packages WHERE package_id=?",(pid,)).fetchone()
   if not r:raise KeyError(pid)
   claims=tuple(x[0] for x in c.execute("SELECT claim_id FROM submission_claims WHERE package_id=? ORDER BY sort_order,claim_id",(pid,)));sources=tuple(SubmissionSource(x[0],x[1],x[2],x[3],x[4],x[5],x[6],bool(x[7])) for x in c.execute("SELECT * FROM submission_sources WHERE package_id=? ORDER BY sort_order,source_type,source_id",(pid,)));sections=tuple(dict(x) for x in c.execute("SELECT * FROM submission_sections WHERE package_id=? ORDER BY sort_order,section_key",(pid,)))
  return SubmissionPackage(*tuple(r),claims,sources,sections)
 def update(self,pid,**changes):
  allowed={"name","package_type","status","user_notes"};unknown=set(changes)-allowed
  if unknown:raise ValueError("Unsupported package fields")
  old=self.get(pid);self._validate_meta(changes.get("name",old.name),changes.get("package_type",old.package_type),changes.get("status",old.status));num=old.package_version+1
  with self._connect() as c:c.execute("UPDATE submission_packages SET "+",".join(f"{k}=?" for k in changes)+",package_version=?,updated_at=? WHERE package_id=?",(*changes.values(),num,_now(),pid))
  self._snapshot(pid);return self.get(pid)
 def delete(self,pid):
  with self._connect() as c:
   if c.execute("DELETE FROM submission_packages WHERE package_id=?",(pid,)).rowcount==0:raise KeyError(pid)
 def duplicate(self,pid):
  x=self.get(pid);copy=self.create("Copy of "+x.name,x.package_type,claim_ids=x.claim_ids,user_notes=x.user_notes)
  for s in x.sources:self.add_source(copy.package_id,s.source_type,s.source_id,display_name=s.display_name,section_key=s.section_key,user_confirmed=s.user_confirmed)
  for sec in x.sections:self.configure_section(copy.package_id,sec["section_key"],title=sec["title"],enabled=bool(sec["enabled"]),sort_order=sec["sort_order"])
  return self.get(copy.package_id)
 def list(self,*,package_type=None,status=None,claim_id=None,search=""):
  q="SELECT DISTINCT p.package_id FROM submission_packages p LEFT JOIN submission_claims c ON c.package_id=p.package_id WHERE 1=1";a=[]
  for col,val in (("p.package_type",package_type),("p.status",status),("c.claim_id",claim_id)):
   if val:q+=f" AND {col}=?";a.append(val)
  if search:q+=" AND (p.name LIKE ? OR p.user_notes LIKE ?)";a += [f"%{search}%"]*2
  q+=" ORDER BY p.updated_at DESC,p.package_id";
  with self._connect() as c:ids=[r[0] for r in c.execute(q,a)]
  return [self.get(x) for x in ids]
 def link_claim(self,pid,cid):
  with self._connect() as c:n=c.execute("SELECT COALESCE(MAX(sort_order),-1)+1 FROM submission_claims WHERE package_id=?",(pid,)).fetchone()[0];c.execute("INSERT OR IGNORE INTO submission_claims VALUES(?,?,?)",(pid,cid,n))
 def unlink_claim(self,pid,cid):
  with self._connect() as c:c.execute("DELETE FROM submission_claims WHERE package_id=? AND claim_id=?",(pid,cid))
 def add_source(self,pid,source_type,source_id,*,display_name="",section_key="appendices",user_confirmed=True):
  if source_type not in SOURCE_TYPES:raise ValueError("Unsupported submission source type")
  with self._connect() as c:n=c.execute("SELECT COALESCE(MAX(sort_order),-1)+1 FROM submission_sources WHERE package_id=?",(pid,)).fetchone()[0];ex=f"EX-{n+1:03d}";c.execute("INSERT OR IGNORE INTO submission_sources VALUES(?,?,?,?,?,?,?,?)",(pid,source_type,source_id,display_name,ex,n,section_key,int(user_confirmed)))
  self._bump(pid);return self.get(pid)
 def remove_source(self,pid,source_type,source_id):
  with self._connect() as c:c.execute("DELETE FROM submission_sources WHERE package_id=? AND source_type=? AND source_id=?",(pid,source_type,source_id))
  self._bump(pid)
 def configure_source(self,pid,source_type,source_id,**changes):
  allowed={"display_name","exhibit_id","sort_order","section_key","user_confirmed"}
  if set(changes)-allowed:raise ValueError("Unsupported source fields")
  with self._connect() as c:c.execute("UPDATE submission_sources SET "+",".join(f"{k}=?" for k in changes)+" WHERE package_id=? AND source_type=? AND source_id=?",(*[int(v) if k=="user_confirmed" else v for k,v in changes.items()],pid,source_type,source_id))
  self._bump(pid)
 def move_source(self,pid,source_type,source_id,offset):
  sources=list(self.get(pid).sources);i=next(i for i,s in enumerate(sources) if (s.source_type,s.source_id)==(source_type,source_id));j=max(0,min(len(sources)-1,i+offset));sources[i],sources[j]=sources[j],sources[i]
  with self._connect() as c:c.executemany("UPDATE submission_sources SET sort_order=?,exhibit_id=? WHERE package_id=? AND source_type=? AND source_id=?",[(n,f"EX-{n+1:03d}",pid,s.source_type,s.source_id) for n,s in enumerate(sources)])
  self._bump(pid)
 def configure_section(self,pid,key,**changes):
  allowed={"title","enabled","sort_order"}
  if set(changes)-allowed:raise ValueError("Unsupported section fields")
  with self._connect() as c:c.execute("UPDATE submission_sections SET "+",".join(f"{k}=?" for k in changes)+" WHERE package_id=? AND section_key=?",(*[int(v) if k=="enabled" else v for k,v in changes.items()],pid,key))
  self._bump(pid)
 def move_section(self,pid,key,offset):
  secs=list(self.get(pid).sections);i=next(i for i,s in enumerate(secs) if s["section_key"]==key);j=max(0,min(len(secs)-1,i+offset));secs[i],secs[j]=secs[j],secs[i]
  with self._connect() as c:c.executemany("UPDATE submission_sections SET sort_order=? WHERE package_id=? AND section_key=?",[(n,pid,s["section_key"]) for n,s in enumerate(secs)])
  self._bump(pid)
 def versions(self,pid):
  with self._connect() as c:return [dict(r) for r in c.execute("SELECT * FROM submission_versions WHERE package_id=? ORDER BY version_number DESC",(pid,))]
 def exports(self,pid):
  with self._connect() as c:return [dict(r) for r in c.execute("SELECT * FROM submission_exports WHERE package_id=? ORDER BY created_at DESC",(pid,))]
 def validate(self,pid,output_parent=None):
  p=self.get(pid);issues=[]
  if not p.claim_ids and p.package_type not in {"evidence_only","claimant_statement","witness_statement"}:issues.append(ValidationIssue("blocking","no_claims","Package requires at least one selected claim."))
  with self._connect() as c:
   for cid in p.claim_ids:
    r=c.execute("SELECT condition_name FROM claims WHERE claim_id=?",(cid,)).fetchone()
    if not r or not r[0].strip():issues.append(ValidationIssue("blocking","invalid_claim","Selected claim is missing or has no title.","claim",cid))
  exhibits=[s.exhibit_id for s in p.sources]
  if len(exhibits)!=len(set(exhibits)):issues.append(ValidationIssue("blocking","duplicate_exhibit","Exhibit identifiers must be unique."))
  orders=[s["sort_order"] for s in p.sections]
  if len(orders)!=len(set(orders)):issues.append(ValidationIssue("blocking","section_order","Section order contains duplicates."))
  for s in p.sources:issues += self._validate_source(s)
  if output_parent:
   parent=Path(output_parent)
   try:parent.mkdir(parents=True,exist_ok=True);probe=parent/".write-test";probe.write_text("ok");probe.unlink()
   except OSError:issues.append(ValidationIssue("blocking","output_not_writable","Package output location is not writable."))
  if not p.sources:issues.append(ValidationIssue("warning","empty_package","No package sources are selected."))
  issues.append(ValidationIssue("info","advisory","Package organization is not legal advice and does not guarantee VA approval."));return issues
 def _validate_source(self,s):
  out=[];table={"document":("documents","document_id"),"evidence":("evidence","evidence_id"),"timeline":("medical_timeline_events","event_id"),"nexus":("nexus_letters","letter_id"),"dbq":("dbq_records","dbq_id"),"rating_strategy":("rating_strategies","strategy_id"),"optimizer":("optimizer_assessments","assessment_id"),"claimant_statement":("documents","document_id"),"witness_statement":("documents","document_id"),"provider_request":("documents","document_id")}[s.source_type]
  with self._connect() as c:r=c.execute(f"SELECT * FROM {table[0]} WHERE {table[1]}=?",(s.source_id,)).fetchone()
  if not r:return [ValidationIssue("blocking","missing_source",f"Selected {s.source_type} source is unavailable.",s.source_type,s.source_id)]
  if s.source_type in {"document","claimant_statement","witness_statement","provider_request"}:
   from core.documents import DocumentManager
   d=DocumentManager(self.project).get(s.source_id)
   if not d.stored_path.is_file():out.append(ValidationIssue("blocking","missing_file",f"Source file is missing: {d.original_name}",s.source_type,s.source_id))
   elif d.stored_path.suffix.lower()==".pdf":
    try:
     from pypdf import PdfReader
     PdfReader(d.stored_path,strict=False)
    except Exception:out.append(ValidationIssue("blocking","unreadable_pdf",f"PDF is unreadable or encrypted: {d.original_name}",s.source_type,s.source_id))
  if s.source_type=="evidence" and (r[9]=="not_relevant" or r[11]):out.append(ValidationIssue("warning","duplicate_or_irrelevant","Selected evidence is duplicate or not relevant.",s.source_type,s.source_id))
  if s.source_type=="nexus":
   if r[4]!="final":out.append(ValidationIssue("warning","draft_nexus","Selected nexus letter is a draft requiring professional review and signature.",s.source_type,s.source_id))
   if not r[7] or not r[8]:out.append(ValidationIssue("warning","unsigned_nexus","Provider name or credentials are missing.",s.source_type,s.source_id))
  if s.source_type=="dbq":
   from core.dbq import DBQManager
   gaps=DBQManager(self.project).completeness(s.source_id)
   if gaps["examiner_only"]:out.append(ValidationIssue("warning","examiner_fields","Examiner-only DBQ fields are not represented as completed findings.",s.source_type,s.source_id))
  if s.source_type in {"claimant_statement","witness_statement"}:out.append(ValidationIssue("warning","unsigned_statement","Selected statement must be reviewed and signed by the actual witness.",s.source_type,s.source_id))
  if s.source_type in {"dbq","rating_strategy","optimizer"} and not s.user_confirmed:out.append(ValidationIssue("blocking","unsupported_ai","AI-assisted material is not user-confirmed.",s.source_type,s.source_id))
  return out
 def _snapshot(self,pid):
  p=self.get(pid);snap={"name":p.name,"package_type":p.package_type,"status":p.status,"claims":p.claim_ids,"sources":[s.__dict__ if hasattr(s,"__dict__") else {k:getattr(s,k) for k in s.__slots__} for s in p.sources],"sections":p.sections,"user_notes":p.user_notes};vid=str(uuid.uuid4())
  with self._connect() as c:c.execute("INSERT OR REPLACE INTO submission_versions VALUES(?,?,?,?,?)",(vid,pid,p.package_version,json.dumps(snap),_now()))
 def _bump(self,pid):
  with self._connect() as c:c.execute("UPDATE submission_packages SET package_version=package_version+1,updated_at=? WHERE package_id=?",(_now(),pid))
  self._snapshot(pid)
 def _ensure(self):
  with self._connect() as c:c.executescript(SUBMISSION_SCHEMA)
 @staticmethod
 def _validate_meta(name,t,status):
  if not str(name).strip():raise ValueError("Package name is required")
  if t not in PACKAGE_TYPES:raise ValueError("Unsupported package type")
  if status not in {"draft","validated","generating","completed","failed","cancelled","incomplete"}:raise ValueError("Unsupported package status")
