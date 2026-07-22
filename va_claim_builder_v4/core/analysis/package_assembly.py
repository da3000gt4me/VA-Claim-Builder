from __future__ import annotations
from pathlib import Path
from typing import Any

class FinalPackageAssemblyValidator:
    def validate(self, claims:list[dict[str,Any]], documents:list[dict[str,Any]], gates:list[dict[str,Any]], output_paths:list[str|Path] | None=None) -> dict[str,Any]:
        blockers=[]; warnings=[]
        blocked=[g for g in gates if g.get("blocked")]
        if blocked: blockers.append(f"{len(blocked)} claim(s) remain blocked by readiness gates")
        included=[d for d in documents if d.get("include_in_final")]
        if not included: blockers.append("No source documents are marked for final inclusion")
        unsigned=[d for d in included if d.get("signed_status") in {"draft","unsigned"}]
        if unsigned: blockers.append(f"{len(unsigned)} included document(s) remain draft or unsigned")
        duplicates=[d for d in included if d.get("duplicate_of")]
        if duplicates: warnings.append(f"{len(duplicates)} included document(s) are exact duplicates")
        unclassified=[d for d in included if not d.get("classification_reviewed")]
        if unclassified: warnings.append(f"{len(unclassified)} included document(s) have not had category classification confirmed")
        missing_files=[]
        for d in included:
            p=d.get("original_path")
            if p and not Path(p).exists(): missing_files.append(d.get("original_name") or d.get("id"))
        if missing_files: blockers.append(f"{len(missing_files)} included source file(s) cannot be found on disk")
        if output_paths:
            absent=[str(p) for p in output_paths if not Path(p).exists()]
            if absent: blockers.append(f"{len(absent)} generated output file(s) are missing")
        return {"claim_count":len(claims),"included_document_count":len(included),"blocked":bool(blockers),"blockers":blockers,"warnings":warnings,"status":"blocked" if blockers else ("review_with_warnings" if warnings else "assembly_validated")}
