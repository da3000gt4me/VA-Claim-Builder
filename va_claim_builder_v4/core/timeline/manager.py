from __future__ import annotations
import csv, json, sqlite3, uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable
from core.projects import ProjectInfo
from core.projects.manager import TIMELINE_SCHEMA

DATE_PRECISIONS=("exact","month","year","range","approximate","service period","unknown")
EVENT_TYPES=("onset","worsening","diagnosis","treatment","exposure","incident","testing","medication","functional impact","continuity","other")
def _now(): return datetime.now(timezone.utc).isoformat()

@dataclass(frozen=True,slots=True)
class TimelineEvent:
    event_id:str; event_date:str; end_date:str; date_precision:str; event_type:str; title:str; description:str
    provider_facility:str; body_system_condition:str; document_id:str|None; evidence_id:str|None
    treatment:str; diagnosis:str; symptoms:list[str]; medications:list[str]; testing_imaging:str
    functional_impact:str; service_period_relevance:str; notes:str; created_at:str; updated_at:str
    document_name:str|None=None; evidence_title:str|None=None; claim_ids:tuple[str,...]=()

class TimelineManager:
    FIELDS=("event_date","end_date","date_precision","event_type","title","description","provider_facility",
            "body_system_condition","document_id","evidence_id","treatment","diagnosis","symptoms","medications",
            "testing_imaging","functional_impact","service_period_relevance","notes")
    def __init__(self,project:ProjectInfo): self.project=project; self._ensure()
    def _connect(self):
        c=sqlite3.connect(self.project.database_path); c.row_factory=sqlite3.Row; c.execute("PRAGMA foreign_keys=ON"); return c
    def create(self,title:str,*,claim_ids:Iterable[str]=(),**values)->TimelineEvent:
        values={**{k:"" for k in self.FIELDS},**values,"title":title}
        values["date_precision"]=values["date_precision"] or "unknown";values["event_type"]=values["event_type"] or "other"
        values=self._validate(values); event_id=str(uuid.uuid4()); now=_now()
        with self._connect() as c:
            c.execute("INSERT INTO medical_timeline_events VALUES("+",".join("?" for _ in range(21))+")",
                      (event_id,*self._db_values(values),now,now))
            self._replace_claims(c,event_id,claim_ids)
        return self.get(event_id)
    def get(self,event_id:str)->TimelineEvent:
        with self._connect() as c: row=c.execute(self._select()+" WHERE t.event_id=?",(event_id,)).fetchone()
        if not row: raise KeyError(event_id)
        return self._row(row)
    def update(self,event_id:str,*,claim_ids:Iterable[str]|None=None,**changes)->TimelineEvent:
        if set(changes)-set(self.FIELDS): raise ValueError("Unsupported timeline fields")
        current=self.get(event_id); values={k:getattr(current,k) for k in self.FIELDS}; values.update(changes); values=self._validate(values)
        with self._connect() as c:
            c.execute("UPDATE medical_timeline_events SET "+",".join(f"{self._col(k)}=?" for k in self.FIELDS)+",updated_at=? WHERE event_id=?",
                      (*self._db_values(values),_now(),event_id))
            if claim_ids is not None:self._replace_claims(c,event_id,claim_ids)
        return self.get(event_id)
    def delete(self,event_id:str):
        with self._connect() as c:
            if not c.execute("DELETE FROM medical_timeline_events WHERE event_id=?",(event_id,)).rowcount: raise KeyError(event_id)
    def list(self,*,search="",date_from="",date_to="",event_type="",provider="",claim_id="",body_system="",descending=False)->list[TimelineEvent]:
        clauses=[];args=[]
        if date_from:clauses.append("t.event_date>=?");args.append(date_from)
        if date_to:clauses.append("t.event_date<=?");args.append(date_to)
        if event_type:clauses.append("t.event_type=?");args.append(event_type)
        if provider:clauses.append("t.provider_facility LIKE ?");args.append(f"%{provider}%")
        if body_system:clauses.append("t.body_system_condition LIKE ?");args.append(f"%{body_system}%")
        if claim_id:clauses.append("EXISTS(SELECT 1 FROM timeline_event_claims x WHERE x.event_id=t.event_id AND x.claim_id=?)");args.append(claim_id)
        if search:
            clauses.append("(t.title LIKE ? OR t.description LIKE ? OR t.provider_facility LIKE ? OR t.diagnosis LIKE ? OR t.notes LIKE ?)");args += [f"%{search}%"]*5
        where=" WHERE "+" AND ".join(clauses) if clauses else ""
        direction="DESC" if descending else "ASC"
        with self._connect() as c: rows=c.execute(self._select()+where+f" ORDER BY CASE WHEN t.event_date='' THEN 1 ELSE 0 END, t.event_date {direction},t.created_at,t.event_id",args).fetchall()
        return [self._row(r) for r in rows]
    search=lambda self,q:self.list(search=q)
    def link_claim(self,event_id,claim_id):
        self.get(event_id)
        with self._connect() as c:c.execute("INSERT OR IGNORE INTO timeline_event_claims VALUES(?,?,?)",(event_id,claim_id,_now()))
    def unlink_claim(self,event_id,claim_id):
        with self._connect() as c:c.execute("DELETE FROM timeline_event_claims WHERE event_id=? AND claim_id=?",(event_id,claim_id))
    def link_document(self,event_id,document_id): return self.update(event_id,document_id=document_id)
    def unlink_document(self,event_id): return self.update(event_id,document_id=None)
    def link_evidence(self,event_id,evidence_id): return self.update(event_id,evidence_id=evidence_id)
    def unlink_evidence(self,event_id): return self.update(event_id,evidence_id=None)
    def likely_duplicates(self,candidate:dict,threshold=.72)->list[TimelineEvent]:
        out=[]
        for event in self.list():
            exact=sum([event.event_date==candidate.get("event_date",""),event.provider_facility.lower()==str(candidate.get("provider_facility","")).lower(),event.event_type==candidate.get("event_type"),event.document_id==candidate.get("document_id"),event.evidence_id==candidate.get("evidence_id")])
            similarity=SequenceMatcher(None,(event.title+" "+event.description).lower(),(str(candidate.get("title",""))+" "+str(candidate.get("description",""))).lower()).ratio()
            if exact/5*.55+similarity*.45>=threshold:out.append(event)
        return out
    def narrative(self,events=None)->str:
        return "\n\n".join(f"{e.event_date or 'Date unknown'} — {e.title}\n{e.description}" for e in (events or self.list()))
    def export_csv(self,path:Path,events=None)->Path:
        with Path(path).open("w",newline="",encoding="utf-8") as f:
            w=csv.writer(f);w.writerow(["Date","End Date","Type","Title","Provider/Facility","Condition","Description","Claims"])
            for e in events or self.list():w.writerow([e.event_date,e.end_date,e.event_type,e.title,e.provider_facility,e.body_system_condition,e.description,";".join(e.claim_ids)])
        return Path(path)
    @staticmethod
    def _col(k): return {"symptoms":"symptoms_json","medications":"medications_json"}.get(k,k)
    def _db_values(self,v): return tuple(json.dumps(v[k]) if k in {"symptoms","medications"} else v[k] for k in self.FIELDS)
    def _validate(self,v):
        v=dict(v)
        for k in self.FIELDS:
            if k in {"symptoms","medications"}:v[k]=[str(x).strip() for x in (v.get(k) or []) if str(x).strip()]
            elif k in {"document_id","evidence_id"}:v[k]=str(v.get(k)).strip() if v.get(k) else None
            else:v[k]=str(v.get(k) or "").strip()
        if not v["title"]:raise ValueError("Timeline event title is required")
        if v["date_precision"] not in DATE_PRECISIONS:raise ValueError("Unsupported date precision")
        if v["event_type"] not in EVENT_TYPES:raise ValueError("Unsupported event type")
        return v
    def _replace_claims(self,c,event_id,ids):
        c.execute("DELETE FROM timeline_event_claims WHERE event_id=?",(event_id,)); unique=dict.fromkeys(str(x) for x in ids)
        c.executemany("INSERT INTO timeline_event_claims VALUES(?,?,?)",[(event_id,x,_now()) for x in unique])
    @staticmethod
    def _select():
        return """SELECT t.*,d.original_name document_name,e.title evidence_title,
        COALESCE((SELECT group_concat(claim_id,',') FROM timeline_event_claims x WHERE x.event_id=t.event_id),'') claim_ids
        FROM medical_timeline_events t LEFT JOIN documents d ON d.document_id=t.document_id LEFT JOIN evidence e ON e.evidence_id=t.evidence_id"""
    @staticmethod
    def _row(r):
        return TimelineEvent(r["event_id"],r["event_date"],r["end_date"],r["date_precision"],r["event_type"],r["title"],r["description"],r["provider_facility"],r["body_system_condition"],r["document_id"],r["evidence_id"],r["treatment"],r["diagnosis"],json.loads(r["symptoms_json"]),json.loads(r["medications_json"]),r["testing_imaging"],r["functional_impact"],r["service_period_relevance"],r["notes"],r["created_at"],r["updated_at"],r["document_name"],r["evidence_title"],tuple(x for x in r["claim_ids"].split(",") if x))
    def _ensure(self):
        from core.claims import ClaimManager
        from core.documents import DocumentManager
        from core.evidence import EvidenceManager
        ClaimManager(self.project);DocumentManager(self.project);EvidenceManager(self.project)
        with self._connect() as c:c.executescript(TIMELINE_SCHEMA)
