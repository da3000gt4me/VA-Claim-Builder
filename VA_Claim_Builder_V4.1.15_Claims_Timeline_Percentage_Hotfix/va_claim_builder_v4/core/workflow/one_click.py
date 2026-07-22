from __future__ import annotations
from core.workflow.recovery import WorkflowRecoveryService

class OneClickProjectProcessor:
    STAGES=("ingestion_validation","text_extraction","semantic_review_preparation","contradiction_scan","readiness_refresh","package_preflight")
    def __init__(self, db, project_id: str, project_root):
        self.db=db; self.project_id=project_id; self.project_root=project_root
        self.recovery=WorkflowRecoveryService(db.path)
    def run(self) -> dict:
        run_id=self.recovery.start(self.project_id,"one_click")
        results=[]
        try:
            docs=self.db.list_documents(self.project_id)
            claims=self.db.list_claims(self.project_id)
            for index,stage in enumerate(self.STAGES,1):
                result=self._run_stage(stage,docs,claims)
                results.append({"stage":stage,"result":result})
                self.recovery.checkpoint(run_id,index/len(self.STAGES),{"completed":[x['stage'] for x in results]})
            output={"run_id":run_id,"status":"complete","stages":results}
            self.recovery.complete(run_id,output); return output
        except Exception as exc:
            self.recovery.fail(run_id,str(exc)); raise
    def _run_stage(self, stage, docs, claims):
        if stage=='ingestion_validation': return {"documents":len(docs),"missing_files":sum(not __import__('pathlib').Path(d['original_path']).exists() for d in docs)}
        if stage=='text_extraction': return {"awaiting":sum(d.get('extraction_status')!='complete' for d in docs)}
        if stage=='semantic_review_preparation': return {"claims":len(claims),"pending_annotations":len(self.db.list_annotations(self.project_id,'pending'))}
        if stage=='contradiction_scan': return {"open":len(self.db.list_contradictions(self.project_id,'open'))}
        if stage=='readiness_refresh': return {"active_claims":len([c for c in claims if c.get('status')=='active'])}
        return {"included_documents":sum(bool(d.get('include_in_final')) for d in docs)}
