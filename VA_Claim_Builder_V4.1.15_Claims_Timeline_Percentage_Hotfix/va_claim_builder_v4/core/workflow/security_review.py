from __future__ import annotations
import os, stat
from pathlib import Path

class SecurityReview:
    def run(self, project_root: str | Path) -> dict:
        root=Path(project_root); findings=[]
        env=root.parent.parent/'.env'
        if env.exists():
            mode=stat.S_IMODE(env.stat().st_mode)
            findings.append({"severity":"warning" if mode & 0o077 else "pass","check":"API-key file permissions","detail":oct(mode)})
        else:
            findings.append({"severity":"pass","check":"API-key file","detail":"No .env file stored in project directory"})
        temp_files=[str(p) for p in root.rglob('*') if p.is_file() and p.suffix.lower() in {'.tmp','.temp'}]
        findings.append({"severity":"warning" if temp_files else "pass","check":"Temporary files","detail":f"{len(temp_files)} found"})
        cloud = os.getenv('VCB_LOCAL_ONLY','false').lower() != 'true'
        findings.append({"severity":"info" if cloud else "pass","check":"Cloud transmission mode","detail":"enabled with redaction/review controls" if cloud else "local-only"})
        return {"status":"review_required" if any(x['severity']=='warning' for x in findings) else "pass","findings":findings}
