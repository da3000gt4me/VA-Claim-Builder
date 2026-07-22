from __future__ import annotations
import hashlib, json, shutil, zipfile
from datetime import datetime, timezone
from pathlib import Path

class ProjectBackupService:
    """Creates a portable, checksum-backed project snapshot without modifying source files."""

    def create(self, project_root: str | Path, output_dir: str | Path) -> dict:
        root = Path(project_root).resolve(); out = Path(output_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        zip_path = out / f"VA_Claim_Builder_Project_Backup_{stamp}.zip"
        files = []
        for path in sorted(root.rglob("*")):
            if not path.is_file() or out in path.parents:
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            files.append({"path": str(path.relative_to(root)), "size": path.stat().st_size, "sha256": digest})
        manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "project_root_name": root.name, "files": files}
        manifest_path = root / "backup_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for item in files:
                    zf.write(root / item["path"], item["path"])
                zf.write(manifest_path, "backup_manifest.json")
        finally:
            manifest_path.unlink(missing_ok=True)
        return {"backup_zip": str(zip_path), "file_count": len(files), "sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest()}

    def validate(self, zip_path: str | Path) -> dict:
        zp = Path(zip_path)
        with zipfile.ZipFile(zp) as zf:
            bad = zf.testzip()
            manifest = json.loads(zf.read("backup_manifest.json"))
            mismatches=[]
            for item in manifest["files"]:
                if hashlib.sha256(zf.read(item["path"])).hexdigest() != item["sha256"]:
                    mismatches.append(item["path"])
        return {"valid": bad is None and not mismatches, "bad_member": bad, "checksum_mismatches": mismatches, "file_count": len(manifest["files"])}
