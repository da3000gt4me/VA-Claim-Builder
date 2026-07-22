from __future__ import annotations
import json,sqlite3,uuid
from dataclasses import dataclass
from datetime import datetime,timezone
from typing import Any
from core.projects.manager import RATING_STRATEGY_SCHEMA
def _now():return datetime.now(timezone.utc).isoformat()
STRATEGY_STATUSES=("pending","completed","failed","cancelled")
LIST_FIELDS=("diagnostic_codes","supporting_evidence","contradictory_evidence","missing_evidence","recommended_actions","secondary_opportunities","aggravation_opportunities","presumptive_opportunities","strengths","weaknesses")
@dataclass(frozen=True,slots=True)
class RatingStrategy:
 strategy_id:str;claim_id:str;job_id:str|None;status:str;analysis_timestamp:str;analysis_version:str;confidence:str;diagnostic_codes:tuple[str,...];estimated_rating_range:str;supporting_evidence:tuple[str,...];contradictory_evidence:tuple[str,...];missing_evidence:tuple[str,...];recommended_actions:tuple[str,...];secondary_opportunities:tuple[str,...];aggravation_opportunities:tuple[str,...];presumptive_opportunities:tuple[str,...];strengths:tuple[str,...];weaknesses:tuple[str,...];generated_reasoning:str;ai_metadata:dict[str,Any];error_message:str;created_at:str;updated_at:str
class RatingStrategyManager:
 def __init__(self,project):self.project=project;self._ensure()
 def _connect(self):c=sqlite3.connect(self.project.database_path);c.row_factory=sqlite3.Row;c.execute("PRAGMA foreign_keys=ON");return c
 def create(self,claim_id,*,job_id=None,status="pending",analysis_version="1.0",confidence="low",estimated_rating_range="",generated_reasoning="",ai_metadata=None,error_message="",**lists):
  self._validate(status,confidence);sid=str(uuid.uuid4());now=_now();values={k:list(lists.get(k,[])) for k in LIST_FIELDS}
  with self._connect() as c:c.execute("INSERT INTO rating_strategies VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(sid,claim_id,job_id,status,now,analysis_version,confidence,json.dumps(values["diagnostic_codes"]),estimated_rating_range,json.dumps(values["supporting_evidence"]),json.dumps(values["contradictory_evidence"]),json.dumps(values["missing_evidence"]),json.dumps(values["recommended_actions"]),json.dumps(values["secondary_opportunities"]),json.dumps(values["aggravation_opportunities"]),json.dumps(values["presumptive_opportunities"]),json.dumps(values["strengths"]),json.dumps(values["weaknesses"]),generated_reasoning,json.dumps(ai_metadata or {}),error_message,now,now))
  return self.get(sid)
 def get(self,sid):
  with self._connect() as c:r=c.execute("SELECT * FROM rating_strategies WHERE strategy_id=?",(sid,)).fetchone()
  if not r:raise KeyError(sid)
  return self._row(r)
 def update(self,sid,**changes):
  old=self.get(sid);allowed={"status","confidence","estimated_rating_range","generated_reasoning","ai_metadata","error_message",*LIST_FIELDS};unknown=set(changes)-allowed
  if unknown:raise ValueError("Unsupported strategy fields: "+", ".join(sorted(unknown)))
  data={k:getattr(old,k) for k in allowed};data.update(changes);self._validate(data["status"],data["confidence"]);cols=[];args=[]
  for k,v in data.items():col=k+"_json" if k in LIST_FIELDS or k=="ai_metadata" else k;cols.append(col+"=?");args.append(json.dumps(list(v) if k in LIST_FIELDS else v) if k in LIST_FIELDS or k=="ai_metadata" else v)
  with self._connect() as c:c.execute("UPDATE rating_strategies SET "+",".join(cols)+",updated_at=? WHERE strategy_id=?",(*args,_now(),sid))
  return self.get(sid)
 def delete(self,sid):
  with self._connect() as c:
   if c.execute("DELETE FROM rating_strategies WHERE strategy_id=?",(sid,)).rowcount==0:raise KeyError(sid)
 def list(self,*,claim_id=None,status=None,confidence=None,search=""):
  q="SELECT * FROM rating_strategies WHERE 1=1";a=[]
  for col,val in (("claim_id",claim_id),("status",status),("confidence",confidence)):
   if val:q+=f" AND {col}=?";a.append(val)
  if search:q+=" AND (generated_reasoning LIKE ? OR estimated_rating_range LIKE ? OR supporting_evidence_json LIKE ? OR missing_evidence_json LIKE ? OR strengths_json LIKE ? OR weaknesses_json LIKE ? OR recommended_actions_json LIKE ? OR contradictory_evidence_json LIKE ?)";a += [f"%{search}%"]*8
  q+=" ORDER BY analysis_timestamp DESC,strategy_id"
  with self._connect() as c:rows=c.execute(q,a).fetchall()
  return [self._row(r) for r in rows]
 def history(self,claim_id):return self.list(claim_id=claim_id)
 def _ensure(self):
  with self._connect() as c:c.executescript(RATING_STRATEGY_SCHEMA)
 @staticmethod
 def _validate(status,confidence):
  if status not in STRATEGY_STATUSES:raise ValueError("Unsupported strategy status")
  if confidence not in {"low","medium","high"}:raise ValueError("Unsupported strategy confidence")
 @staticmethod
 def _row(r):return RatingStrategy(r[0],r[1],r[2],r[3],r[4],r[5],r[6],tuple(json.loads(r[7])),r[8],tuple(json.loads(r[9])),tuple(json.loads(r[10])),tuple(json.loads(r[11])),tuple(json.loads(r[12])),tuple(json.loads(r[13])),tuple(json.loads(r[14])),tuple(json.loads(r[15])),tuple(json.loads(r[16])),tuple(json.loads(r[17])),r[18],json.loads(r[19]),r[20],r[21],r[22])
