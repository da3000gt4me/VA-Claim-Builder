from __future__ import annotations
import json, os
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv
from core.ai.router import AIRouter
from core.ai.multi_agent import MultiAgentOrchestrator
from core.analysis.evidence_engine import EvidenceEngine
from core.security.redaction import redact_identifiers
from core.storage.project_db import ProjectDB
from core.workflow.migrations import MigrationManager
from ui.ai_settings import render_ai_settings
from ui.project_workspace import render_project_workspace
from core.version import FULL_NAME

load_dotenv()
BASE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("VCB_DATA_DIR", str(BASE / "data")))
DATA.mkdir(parents=True, exist_ok=True)
db = ProjectDB(DATA / "va_claim_builder.db")
MigrationManager(db.path).migrate()
project_id = db.ensure_default_project()
project_root = DATA / "projects" / project_id

st.set_page_config(page_title=FULL_NAME, layout="wide")
st.title(f"{FULL_NAME} — AI Evidence Intelligence")
st.warning("Human review is required. This application does not provide medical or legal opinions and cannot guarantee a VA outcome.")

workspace, ai_test = st.tabs(["Project Workspace", "AI Evidence Test Console"])
with workspace:
    render_project_workspace(db, project_id, project_root)
with ai_test:
    settings = render_ai_settings()
    claim = st.text_input("Claimed condition", key="ai_claim")
    theory = st.selectbox("Theory", ["direct", "secondary", "aggravation", "presumptive", "multiple", "unknown"], key="ai_theory")
    source_text = st.text_area("Paste retrieved, page-labeled evidence chunks", height=300,
        placeholder='Example: [{"document_id":"doc1","filename":"record.pdf","page":12,"text":"..."}]')
    if st.button("Run AI Evidence Assessment", type="primary"):
        try:
            chunks = json.loads(source_text)
            if settings["redact"]:
                for chunk in chunks:
                    chunk["text"], chunk["redaction_counts"] = redact_identifiers(chunk.get("text", ""))
            os.environ["VCB_LOCAL_ONLY"] = str(settings["local_only"]).lower()
            router = AIRouter(settings["provider"], settings["fallback"])
            if settings["mode"] == "ensemble":
                os.environ["VCB_AI_MAX_CONCURRENCY"] = str(settings["max_concurrency"])
                engine = EvidenceEngine(router)
                request = engine.build_request(claim, theory, chunks) if hasattr(engine, "build_request") else None
                if request is None:
                    raise RuntimeError("The current EvidenceEngine does not expose a structured request for ensemble mode.")
                result = MultiAgentOrchestrator(router, settings["ensemble"], settings["adjudicator"]).run(request)
                st.session_state["assessment"] = {
                    "mode": "parallel_multi_agent",
                    "consensus_level": result.consensus_level,
                    "warnings": result.warnings,
                    "agents": [{"provider": r.provider, "model": r.model, "error": r.error} for r in result.agent_results],
                    "findings": [f.__dict__ if hasattr(f, "__dict__") else {name: getattr(f, name) for name in f.__slots__} for f in result.findings],
                }
            else:
                assessment = EvidenceEngine(router).assess_claim(claim, theory, chunks)
                st.session_state["assessment"] = assessment.model_dump()
            st.success("Assessment completed. Review every citation and finding before approval.")
        except Exception as exc: st.error(str(exc))
    if "assessment" in st.session_state:
        st.json(st.session_state["assessment"])
        st.download_button("Download assessment JSON", json.dumps(st.session_state["assessment"], indent=2),
            file_name="claim_assessment.json", mime="application/json")
