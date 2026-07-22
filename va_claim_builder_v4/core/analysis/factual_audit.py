from __future__ import annotations
from pathlib import Path
import hashlib, json, re

class FinalFactualAudit:
    def audit_text(self, text: str, approved_facts: list[dict]) -> dict:
        source_terms = {str(a.get("finding", "")).strip().lower() for a in approved_facts if a.get("finding")}
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        unsupported = []
        for sentence in sentences:
            low = sentence.lower()
            if any(marker in low for marker in ["draft for", "clinician review", "veteran reports", "witness reports", "approximately"]):
                continue
            if not any(term and (term in low or low in term) for term in source_terms):
                unsupported.append(sentence)
        return {"sentence_count": len(sentences), "unsupported_count": len(unsupported), "unsupported_sentences": unsupported, "status": "pass" if not unsupported else "requires_review"}
    def audit_files(self, paths: list[str]) -> dict:
        rows=[]
        for raw in paths:
            p=Path(raw)
            if not p.exists(): rows.append({"path":str(p),"status":"missing"}); continue
            digest=hashlib.sha256(p.read_bytes()).hexdigest()
            rows.append({"path":str(p),"size":p.stat().st_size,"sha256":digest,"status":"present"})
        return {"files":rows,"all_present":all(r["status"]=="present" for r in rows)}
    def write_manifest(self, result: dict, output: Path) -> Path:
        output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(result, indent=2), encoding="utf-8"); return output
