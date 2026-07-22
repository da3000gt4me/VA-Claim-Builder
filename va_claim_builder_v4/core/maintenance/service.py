from __future__ import annotations
import hashlib,json,os,platform,shutil,sqlite3,sys,tempfile,uuid,zipfile
from datetime import datetime,timezone
from pathlib import Path,PurePosixPath
from core.projects import ProjectInfo,ProjectManager
from core.projects.manager import PROJECT_FOLDERS
from core.version import BUILD_VERSION
def _now():return datetime.now(timezone.utc).isoformat()
class MaintenanceError(RuntimeError):pass
class ProjectMaintenance:
 def __init__(self,project:ProjectInfo,manager:ProjectManager|None=None):self.project=project;self.manager=manager or ProjectManager()
 @staticmethod
 def checksum(path):
  h=hashlib.sha256()
  with Path(path).open("rb") as f:
   for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
  return h.hexdigest()
 def create_backup(self,destination=None,*,include_sources=True,retention=10):
  root=Path(destination or self.manager.paths.backups);root.mkdir(parents=True,exist_ok=True);stamp=datetime.now().strftime("%Y%m%d-%H%M%S");final=root/f"{self.project.root.name}-{stamp}.vcbbackup.zip";temp=final.with_suffix(".incomplete");files=[]
  for p in self.project.root.rglob("*"):
   if not p.is_file() or p.is_symlink():continue
   rel=p.relative_to(self.project.root)
   if not include_sources and rel.parts and rel.parts[0]=="uploads":continue
   if rel.parts and rel.parts[0] in {"temp","cache"}:continue
   files.append((p,rel.as_posix()))
  manifest={"format":"va-claim-builder-backup-v1","application_version":BUILD_VERSION,"project_id":self.project.project_id,"project_name":self.project.name,"created_at":_now(),"include_sources":include_sources,"files":[{"path":rel,"size":p.stat().st_size,"sha256":self.checksum(p)} for p,rel in files]}
  try:
   with zipfile.ZipFile(temp,"w",zipfile.ZIP_DEFLATED,allowZip64=True) as z:
    for p,rel in files:z.write(p,rel)
    z.writestr("backup-manifest.json",json.dumps(manifest,indent=2))
   temp.replace(final);self.validate_backup(final);self.cleanup_backups(root,retention);return final
  except Exception as e:temp.unlink(missing_ok=True);raise MaintenanceError(f"Backup failed: {type(e).__name__}") from e
 def validate_backup(self,path):
  path=Path(path)
  try:
   with zipfile.ZipFile(path) as z:
    if z.testzip():raise MaintenanceError("Backup archive contains a corrupted member")
    manifest=json.loads(z.read("backup-manifest.json"));members=set(z.namelist())
    if manifest.get("format")!="va-claim-builder-backup-v1":raise MaintenanceError("Unsupported backup format")
    for f in manifest["files"]:
     if not self._safe_member(f["path"]) or f["path"] not in members:raise MaintenanceError("Backup contains an unsafe or missing member")
     if hashlib.sha256(z.read(f["path"])).hexdigest()!=f["sha256"]:raise MaintenanceError("Backup checksum validation failed")
    return manifest
  except (OSError,zipfile.BadZipFile,KeyError,json.JSONDecodeError) as e:raise MaintenanceError("Backup is incomplete or corrupted") from e
 def restore_preview(self,path):
  m=self.validate_backup(path);return {"project_id":m["project_id"],"project_name":m["project_name"],"created_at":m["created_at"],"file_count":len(m["files"]),"include_sources":m["include_sources"]}
 def restore(self,path,destination,*,overwrite=False):
  manifest=self.validate_backup(path);dest=Path(destination).expanduser().resolve()
  if dest.exists() and any(dest.iterdir()) and not overwrite:raise MaintenanceError("Restore destination is not empty; explicit overwrite confirmation is required")
  parent=dest.parent;parent.mkdir(parents=True,exist_ok=True);temp=Path(tempfile.mkdtemp(prefix="restore-",dir=parent))
  try:
   with zipfile.ZipFile(path) as z:
    for f in manifest["files"]:
     if not self._safe_member(f["path"]):raise MaintenanceError("Unsafe archive path")
     target=(temp/f["path"]).resolve()
     if temp not in target.parents:raise MaintenanceError("Archive path traversal rejected")
     target.parent.mkdir(parents=True,exist_ok=True)
     with z.open(f["path"]) as src,target.open("wb") as out:shutil.copyfileobj(src,out)
   if overwrite and dest.exists():
    safety=dest.with_name(dest.name+".pre-restore-"+datetime.now().strftime("%Y%m%d%H%M%S"));dest.replace(safety)
   temp.replace(dest);return self.manager.open_project(dest)
  except Exception as e:shutil.rmtree(temp,ignore_errors=True);raise MaintenanceError(f"Restore failed: {type(e).__name__}") from e
 def validate_project(self):
  issues=[]
  try:m=json.loads(self.project.manifest_path.read_text(encoding="utf-8"))
  except Exception:m={};issues.append({"level":"blocking","code":"manifest_invalid","message":"Project manifest is missing or invalid."})
  if m.get("project_id")!=self.project.project_id:issues.append({"level":"blocking","code":"project_id","message":"Manifest project ID does not match the open project."})
  for folder in PROJECT_FOLDERS:
   if not (self.project.root/folder).is_dir():issues.append({"level":"warning","code":"missing_folder","message":f"Required folder is missing: {folder}","repairable":True})
  try:
   with sqlite3.connect(self.project.database_path) as c:
    integrity=c.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity!="ok":issues.append({"level":"blocking","code":"database_integrity","message":integrity})
    for row in c.execute("PRAGMA foreign_key_check"):issues.append({"level":"warning","code":"foreign_key","message":f"Orphaned relationship in table {row[0]}"})
    version=c.execute("SELECT value FROM schema_metadata WHERE key='schema_version'").fetchone()
    if not version or not str(version[0]).isdigit() or int(version[0])>10:issues.append({"level":"blocking","code":"schema_version","message":"Database schema version is invalid or unsupported."})
    if self._table(c,"documents"):
     for did,name,stored in c.execute("SELECT document_id,original_name,stored_name FROM documents"):
      if Path(stored).is_absolute() or ".." in Path(stored).parts:issues.append({"level":"blocking","code":"invalid_path","message":f"Unsafe stored path for {name}"})
      elif not (self.project.root/"uploads"/stored).is_file():issues.append({"level":"warning","code":"missing_source","message":f"Missing source file: {name}","source_id":did})
  except sqlite3.Error as e:issues.append({"level":"blocking","code":"database_error","message":f"Database validation failed: {type(e).__name__}"})
  stale=[p for p in (self.project.root/"temp").glob("*") if p.is_file()];
  if stale:issues.append({"level":"warning","code":"stale_temp","message":f"{len(stale)} stale temporary file(s) found.","repairable":True})
  return issues
 def repair_safe(self):
  actions=[]
  for f in PROJECT_FOLDERS:
   p=self.project.root/f
   if not p.exists():p.mkdir();actions.append(f"Recreated {f}")
  temp=self.project.root/"temp"
  for p in temp.iterdir():
   if p.is_file():p.unlink(missing_ok=True);actions.append("Removed stale temporary file")
   elif p.is_dir() and p.name.startswith(("submission-","restore-","backup-")):shutil.rmtree(p,ignore_errors=True);actions.append("Removed incomplete temporary directory")
  from core.jobs import JobManager
  count=JobManager(self.project).recover_interrupted();actions.append(f"Recovered {count} interrupted job(s)")
  with sqlite3.connect(self.project.database_path) as c:c.execute("REINDEX");c.execute("PRAGMA optimize")
  return actions
 def export_diagnostics(self,path):
  import importlib.metadata
  validation=self.validate_project();failed=[]
  try:
   with sqlite3.connect(self.project.database_path) as c:c.row_factory=sqlite3.Row;failed=[{"job_type":r[0],"status":r[1],"message":r[2][:200]} for r in c.execute("SELECT job_type,status,message FROM jobs WHERE status IN ('failed','interrupted') ORDER BY updated_at DESC LIMIT 50")]
  except sqlite3.Error:pass
  data={"application_version":BUILD_VERSION,"operating_system":platform.platform(),"python_version":sys.version,"dependencies":{n:self._dep(n) for n in ("PySide6","pypdf","python-docx","cryptography")},"schema_version":10,"project_id":self.project.project_id,"validation_summary":validation,"failed_jobs":failed,"privacy":"No source evidence, OCR text, statements, credentials, or provider payloads are included."};p=Path(path);p.write_text(json.dumps(data,indent=2),encoding="utf-8");return p
 def cleanup_backups(self,root,retention):
  files=sorted(Path(root).glob(f"{self.project.root.name}-*.vcbbackup.zip"),key=lambda p:p.stat().st_mtime,reverse=True)
  for p in files[max(1,int(retention)):]:p.unlink(missing_ok=True)
  for p in Path(root).glob("*.incomplete"):p.unlink(missing_ok=True)
 @staticmethod
 def _safe_member(name):
  p=PurePosixPath(name);return not p.is_absolute() and ".." not in p.parts and not any(part in {"","."} for part in p.parts)
 @staticmethod
 def _table(c,name):return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())
 @staticmethod
 def _dep(name):
  try:
   import importlib.metadata
   return importlib.metadata.version(name)
  except Exception:return "not installed"
