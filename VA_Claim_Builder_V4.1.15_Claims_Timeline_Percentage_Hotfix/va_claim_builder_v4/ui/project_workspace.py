from __future__ import annotations
import tempfile
from pathlib import Path
import streamlit as st
from core.ingestion.categories import CATEGORY_DEFINITIONS, DocumentCategory
from core.ingestion.uploader import DocumentIngestor
from core.storage.project_db import ProjectDB
from core.timeline.reconciler import reconcile_events
from core.timeline.auto_populator import HistoricalTimelineAutoPopulator
from core.ingestion.processing_pipeline import ProcessingPipeline
from core.retrieval.hybrid_search import ClaimRetriever
from core.analysis.contradiction_engine import ContradictionEngine
from core.analysis.readiness import ReadinessEngine
from core.analysis.semantic_evidence import SemanticEvidenceAnalyzer
from core.analysis.evidence_autofill import EvidenceAutofillService
from core.analysis.claim_element_summary import ClaimElementSummary
from core.analysis.corroboration import CrossDocumentCorroborator
from core.analysis.claim_synthesis import ClaimSynthesisEngine
from core.drafting.synthesis_packet import SynthesisPacketGenerator
from core.drafting.final_package import FinalPackageGenerator
from core.drafting.fact_matrix import ApprovedFactMatrix
from core.drafting.fact_validator import DraftFactValidator
from core.drafting.claim_drafting_intelligence import ClaimDraftingIntelligence
from core.rating.criteria_engine import RatingCriteriaEngine
from core.rating.staged_severity import StagedSeverityAnalyzer
from core.decisions.denial_response import DenialDecisionAnalyzer
from core.analysis.submission_gate import SubmissionReadinessGate
from core.analysis.dbq_parser import DBQCPParser
from core.analysis.evidence_gap_planner import EvidenceGapActionPlanner
from core.analysis.package_assembly import FinalPackageAssemblyValidator
from core.analysis.literature_support import LiteratureSupportEngine
from core.drafting.specialist_packet import SpecialistPacketGenerator
from core.drafting.binder_assembler import SubmissionBinderAssembler
from core.analysis.unclaimed_conditions import PotentialClaimDiscoveryEngine
from core.workflow.candidate_promotion import CandidateClaimPromotionService
from core.workflow.project_backup import ProjectBackupService
from core.workflow.orchestrator import ProjectOrchestrator
from core.workflow.system_health import SystemHealthChecker
from core.analysis.adversarial_review import AdversarialReviewEngine
from core.analysis.theory_comparison import ClaimTheoryComparisonEngine
from core.analysis.cp_prep import CPExamPreparationGenerator
from core.analysis.factual_audit import FinalFactualAudit
from core.drafting.representative_export import AccreditedRepresentativeExport
from core.workflow.final_closeout import FinalCloseoutChecklist
from core.workflow.security_review import SecurityReview
from core.workflow.one_click import OneClickProjectProcessor
from core.workflow.recovery import WorkflowRecoveryService
from core.workflow.bulk_analysis import BulkProjectAnalysis

THEORIES = ["direct", "secondary", "aggravation", "presumptive", "multiple", "unknown"]

def _save_uploaded_file(uploaded) -> Path:
    suffix = Path(uploaded.name).suffix
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(uploaded.getbuffer()); tmp.close()
    return Path(tmp.name)

def render_project_workspace(db: ProjectDB, project_id: str, project_root: Path):
    tabs = st.tabs(["1. Uploads", "2. Claims", "3. Run All OCR & Retrieval", "4. Historical Timeline", "5. Run All Semantic Evidence Review", "Contradictions", "Review Queue", "Corroboration & Synthesis", "Drafting Intelligence", "Rating & Denial Response", "DBQ & Action Plan", "Literature & Specialist Packet", "Potential Additional Claims", "Automation & Promotion", "Generate", "System & Recovery", "Final Adversarial Review"])
    with tabs[0]:
        st.subheader("Upload Documents First")
        st.caption("Upload the VA Form 20-0995 and supporting documents first. The application will extract the claimed conditions from the 20-0995 and build the claim list automatically.")
        claims = db.list_claims(project_id)
        claim_options = {f"{c['condition_name']} ({c['theory']})": c["id"] for c in claims}
        ingestor = DocumentIngestor(db, project_root)
        for definition in CATEGORY_DEFINITIONS:
            default_open = definition.category in {DocumentCategory.FORM_995, DocumentCategory.MEDICAL_RECORDS, DocumentCategory.PERSONAL_TIMELINES}
            with st.expander(definition.title, expanded=default_open):
                st.caption(definition.purpose)
                if definition.category == DocumentCategory.FORM_995:
                    st.info("Claims will be detected automatically from this form after ingestion. You do not need to create or select claims first.")
                if definition.editable_starting_point:
                    st.info("The original stays unchanged. A working copy becomes the starting point for evidence-grounded revision.")
                uploads = st.file_uploader("Select files", accept_multiple_files=True, key=f"upload_{definition.category.value}", type=["pdf","docx","txt","rtf","png","jpg","jpeg"])
                selected = []
                if claim_options and definition.category != DocumentCategory.FORM_995:
                    selected = st.multiselect("Optional: link to already-detected claims", claim_options.keys(), key=f"claims_{definition.category.value}")
                if st.button("Ingest files", key=f"ingest_{definition.category.value}", disabled=not uploads):
                    added_claims = []
                    for uploaded in uploads:
                        temp = _save_uploaded_file(uploaded)
                        result = ingestor.ingest_path(project_id, temp, definition.category, [claim_options[x] for x in selected])
                        temp.unlink(missing_ok=True)
                        if result.duplicate_of:
                            st.warning(f"{uploaded.name}: duplicate retained and linked.")
                        else:
                            st.success(f"{uploaded.name}: ingested.")
                        if definition.category == DocumentCategory.FORM_995:
                            try:
                                document = next(d for d in db.list_documents(project_id) if d['id'] == result.document_id)
                                ProcessingPipeline(db).process_document(project_id, document)
                                detection = BulkProjectAnalysis(db).detect_claims_from_form995(project_id)
                                added_claims.extend(detection.get('added', []))
                            except Exception as exc:
                                st.warning(f"The form was uploaded, but automatic claim detection needs the Run All OCR & Retrieval step: {exc}")
                    if added_claims:
                        st.success(f"Auto-created {len(added_claims)} claim(s) from the Form 20-0995.")
                    st.rerun()
        st.markdown("#### Uploaded document inventory")
        st.dataframe(db.list_documents(project_id), use_container_width=True, hide_index=True)

    with tabs[1]:
        st.subheader("Auto-Detected Claim List")
        st.caption("Claims are extracted from page 5, Section 21A of each uploaded VA Form 20-0995. Every extracted claim remains editable before analysis or document generation.")
        detected = db.list_claims(project_id)
        if detected:
            st.success(f"{len(detected)} claim(s) currently in the project.")
            claim_label_map = {f"{c['condition_name']} — {c['theory']}": c['id'] for c in detected}
            with st.expander("Bulk select and delete claims", expanded=len(detected) > 30):
                selected_claim_labels = st.multiselect("Select claims to delete", list(claim_label_map.keys()), key="bulk_delete_claims")
                confirm_bulk = st.checkbox(
                    f"I understand this will delete {len(selected_claim_labels)} selected claim(s) and remove or unassign their related links.",
                    key="confirm_bulk_delete_claims",
                )
                if st.button("Delete selected claims", type="primary", disabled=not selected_claim_labels or not confirm_bulk):
                    deleted = db.delete_claims([claim_label_map[x] for x in selected_claim_labels])
                    st.success(f"Deleted {deleted} claim(s).")
                    st.rerun()
            for claim in detected:
                with st.expander(f"{claim['condition_name']} — {claim['theory']}", expanded=False):
                    with st.form(f"edit_claim_{claim['id']}"):
                        name = st.text_input("Claimed condition", value=claim['condition_name'])
                        theory_index = THEORIES.index(claim['theory']) if claim['theory'] in THEORIES else THEORIES.index('unknown')
                        theory = st.selectbox("Theory", THEORIES, index=theory_index)
                        status_options = ["active", "inactive", "development", "withdrawn"]
                        current_status = claim.get('status', 'active')
                        status_index = status_options.index(current_status) if current_status in status_options else 0
                        status = st.selectbox("Status", status_options, index=status_index)
                        save = st.form_submit_button("Save changes", type="primary")
                        if save:
                            db.update_claim(claim['id'], condition_name=name, theory=theory, status=status)
                            st.success("Claim updated.")
                            st.rerun()
                    confirm_delete = st.checkbox(
                        "I understand deleting this claim removes its claim links and may unassign related timeline/evidence records.",
                        key=f"confirm_delete_{claim['id']}",
                    )
                    if st.button("Delete claim", key=f"delete_claim_{claim['id']}", disabled=not confirm_delete):
                        db.delete_claim(claim['id'])
                        st.rerun()
        else:
            st.warning("No claims have been detected yet. Upload a completed VA Form 20-0995 and run OCR & Retrieval.")

        form_pages = [p for p in db.list_chunks(project_id) if p.get('category') == DocumentCategory.FORM_995.value]
        if form_pages:
            from core.claims.form995_parser import Form995ClaimParser
            diagnostics = Form995ClaimParser().diagnostics(form_pages)
            with st.expander("Form 20-0995 Section 21A extraction diagnostics", expanded=diagnostics.get('parsed_total', 0) != 18):
                st.write({
                    "Form files found": len(diagnostics.get('forms', [])),
                    "Total claims parsed": diagnostics.get('parsed_total', 0),
                    "Expected from two nine-row forms": 18 if len(diagnostics.get('forms', [])) == 2 else "9 per form",
                })
                for form in diagnostics.get('forms', []):
                    st.markdown(f"**{form.get('document_name') or form.get('document_id')}**")
                    st.write({
                        "Physical page 5 found": form.get('physical_page_5_found'),
                        "Section 21A found": form.get('section_21a_found'),
                        "Source page": form.get('source_page'),
                        "Claims parsed": len(form.get('parsed_claims', [])),
                    })
                    st.write(form.get('parsed_claims', []))
                    if form.get('section_preview'):
                        st.text_area("Extracted Section 21A text", form['section_preview'], height=170, disabled=True, key=f"diag_{form.get('document_id')}")
                if st.button("Re-extract claims from all Form 20-0995 files", type="primary"):
                    result = BulkProjectAnalysis(db).detect_claims_from_form995(project_id)
                    st.session_state['form995_detection_result'] = result
                    st.rerun()
        detection_result = st.session_state.pop('form995_detection_result', None)
        if detection_result:
            st.success(f"Parsed {detection_result.get('parsed', 0)} issue(s) and added {len(detection_result.get('added', []))} new claim(s).")

        with st.expander("Manual correction or additional claim", expanded=False):
            with st.form("add_claim"):
                col1, col2 = st.columns([3, 1])
                name = col1.text_input("Claimed condition")
                theory = col2.selectbox("Theory", THEORIES)
                if st.form_submit_button("Add claim") and name.strip():
                    db.add_claim(project_id, name, theory)
                    st.rerun()
    with tabs[2]:
        st.subheader("Run All OCR and Claim Retrieval")
        st.caption("One run processes every awaiting document, extracts claims from every Form 20-0995, links relevant pages to every claim, and builds claim-specific retrieval results.")
        docs = db.list_documents(project_id)
        unprocessed = [d for d in docs if d.get('extraction_status') != 'complete']
        claims = db.list_claims(project_id)
        c1, c2, c3 = st.columns(3)
        c1.metric("Documents awaiting extraction", len(unprocessed))
        c2.metric("Detected claims", len(claims))
        c3.metric("Low-confidence pages", len(db.list_chunks(project_id, needs_review=True)))
        if st.button("Run All OCR & Retrieval", type="primary", disabled=not docs):
            with st.spinner("Processing all documents and claims..."):
                result = BulkProjectAnalysis(db).run_ocr_and_retrieval_all(project_id)
                st.session_state['bulk_ocr_result'] = result
            st.rerun()
        result = st.session_state.get('bulk_ocr_result')
        if result:
            detection = result.get('claim_detection', {})
            st.success(
                f"Processed {len(result.get('processed', []))} document(s); "
                f"created {len(detection.get('added', []))} new claim(s); "
                f"prepared retrieval for {len(result.get('retrieval', {}))} claim(s); "
                f"added {result.get('timeline_added', 0)} proposed timeline event(s)."
            )
            if result.get('errors'):
                st.error(f"{len(result['errors'])} document(s) could not be processed.")
                st.dataframe(result['errors'], use_container_width=True, hide_index=True)
            summary = []
            current_claims = {c['id']: c for c in db.list_claims(project_id)}
            for claim_id, rows in result.get('retrieval', {}).items():
                claim = current_claims.get(claim_id, {'condition_name': claim_id})
                summary.append({
                    'claim': claim['condition_name'],
                    'linked_pages': result.get('linked_pages', {}).get(claim_id, 0),
                    'retrieved_pages': len(rows),
                    'top_score': max((r.get('retrieval_score', 0) for r in rows), default=0),
                })
            if summary:
                st.dataframe(summary, use_container_width=True, hide_index=True)
        low = db.list_chunks(project_id, needs_review=True)
        if low:
            with st.expander(f"Low-confidence OCR pages requiring review ({len(low)})"):
                st.dataframe(low, use_container_width=True, hide_index=True)
        with st.expander("Optional single-claim retrieval diagnostic", expanded=False):
            claims = db.list_claims(project_id)
            if claims:
                labels = {c['condition_name']: c['id'] for c in claims}
                label = st.selectbox("Claim", labels.keys(), key="diagnostic_retrieval_claim")
                query = st.text_input("Focused query", key="diagnostic_retrieval_query")
                if st.button("Run diagnostic retrieval"):
                    st.session_state['retrieved'] = ClaimRetriever(db).retrieve(project_id, labels[label], query)
                if 'retrieved' in st.session_state:
                    st.dataframe(st.session_state['retrieved'], use_container_width=True, hide_index=True)
    with tabs[3]:
        st.subheader("Personal Statements and Historical Timeline")
        st.caption("The application proposes timeline entries from uploaded records, statements, lay evidence, and approved evidence findings. Proposed entries remain editable and are not treated as verified until you confirm them.")
        claims=db.list_claims(project_id); labels={"Unassigned":None,**{c['condition_name']:c['id'] for c in claims}}

        c1,c2=st.columns([1,2])
        with c1:
            if st.button("Auto-populate / refresh proposed timeline", type="primary"):
                proposals=HistoricalTimelineAutoPopulator().propose(
                    claims,
                    db.list_annotations_enriched(project_id),
                    db.list_chunks(project_id),
                )
                added=db.add_timeline_events_if_new(project_id,proposals)
                st.session_state['timeline_autofill_message']=f"Added {added} new proposed timeline event(s). Existing matching events were not duplicated."
                st.rerun()
        with c2:
            st.info(st.session_state.pop('timeline_autofill_message', 'Use auto-populate after document processing or Evidence Review. Review every proposed entry before final drafting.'))

        with st.expander("Add a timeline event manually", expanded=False):
            with st.form("timeline_event"):
                claim_label=st.selectbox("Claim",labels.keys()); c1,c2,c3=st.columns(3); start=c1.text_input("Start date/year"); end=c2.text_input("End date/year"); precision=c3.selectbox("Precision",["exact","month","year","range","approximate","service_period","unknown"])
                event_type=st.selectbox("Event type",["onset","worsening","diagnosis","treatment","exposure","incident","functional_impact","continuity","gap_explanation","other"])
                description=st.text_area("Event and functional impact"); source_type=st.selectbox("Source",["veteran_reported","witness_reported","medical_verified","military_verified","administrative_verified","ai_extracted"]); reporter=st.text_input("Reporter/witness")
                if st.form_submit_button("Add timeline event") and description.strip():
                    db.add_timeline_event(project_id,{"claim_id":labels[claim_label],"event_date_start":start or None,"event_date_end":end or None,"date_precision":precision,"event_type":event_type,"description":description,"source_type":source_type,"reporter":reporter or None,"verification_status":"user_confirmed"}); st.rerun()

        events=db.list_timeline(project_id)
        proposed=[e for e in events if e.get('verification_status') in {'proposed','unreviewed'}]
        confirmed=[e for e in events if e.get('verification_status') not in {'proposed','unreviewed'}]
        m1,m2,m3=st.columns(3); m1.metric("Total events",len(events)); m2.metric("Needs confirmation",len(proposed)); m3.metric("Confirmed/edited",len(confirmed))

        if events:
            event_labels={f"{e.get('event_date_start') or 'Undated'} | {e.get('event_type')} | {e.get('description','')[:80]}":e for e in events}
            selected_label=st.selectbox("Select an event to review or edit",event_labels.keys())
            selected=event_labels[selected_label]
            claim_name=next((name for name,cid in labels.items() if cid==selected.get('claim_id')),"Unassigned")
            with st.form("edit_timeline_event"):
                edit_claim=st.selectbox("Claim",labels.keys(),index=list(labels.keys()).index(claim_name),key="edit_timeline_claim")
                ec1,ec2,ec3=st.columns(3)
                edit_start=ec1.text_input("Start date/year",selected.get('event_date_start') or "")
                edit_end=ec2.text_input("End date/year",selected.get('event_date_end') or "")
                precisions=["exact","month","year","range","approximate","service_period","unknown"]
                current_precision=selected.get('date_precision') if selected.get('date_precision') in precisions else "unknown"
                edit_precision=ec3.selectbox("Precision",precisions,index=precisions.index(current_precision))
                event_types=["onset","worsening","diagnosis","treatment","exposure","incident","functional_impact","continuity","gap_explanation","other"]
                current_type=selected.get('event_type') if selected.get('event_type') in event_types else "other"
                edit_type=st.selectbox("Event type",event_types,index=event_types.index(current_type))
                edit_description=st.text_area("Event description",selected.get('description') or "",height=130)
                source_types=["veteran_reported","witness_reported","medical_verified","military_verified","administrative_verified","ai_extracted"]
                current_source=selected.get('source_type') if selected.get('source_type') in source_types else "ai_extracted"
                edit_source=st.selectbox("Source type",source_types,index=source_types.index(current_source))
                edit_reporter=st.text_input("Reporter/witness",selected.get('reporter') or "")
                verification_options=["proposed","user_confirmed","verified_from_source","needs_clarification","rejected"]
                current_verification=selected.get('verification_status') if selected.get('verification_status') in verification_options else "proposed"
                edit_verification=st.selectbox("Verification status",verification_options,index=verification_options.index(current_verification))
                b1,b2=st.columns(2)
                save=b1.form_submit_button("Save changes / confirm",type="primary")
                delete=b2.form_submit_button("Delete event")
                if save:
                    db.update_timeline_event(selected['id'],{"claim_id":labels[edit_claim],"event_date_start":edit_start or None,"event_date_end":edit_end or None,"date_precision":edit_precision,"event_type":edit_type,"description":edit_description.strip(),"source_type":edit_source,"reporter":edit_reporter or None,"verification_status":edit_verification}); st.rerun()
                if delete:
                    db.delete_timeline_event(selected['id']); st.rerun()

            display_cols=['event_date_start','event_date_end','date_precision','event_type','description','source_type','source_page','confidence','verification_status']
            st.dataframe([{k:e.get(k) for k in display_cols} for e in events],use_container_width=True,hide_index=True)
        else:
            st.warning("No historical timeline entries are available yet. Process the uploaded documents, then select Auto-populate / refresh proposed timeline.")

        conflicts=[c.model_dump() for c in reconcile_events(events)]
        if conflicts: st.warning(f"{len(conflicts)} timeline issue(s) require reconciliation."); st.dataframe(conflicts,use_container_width=True,hide_index=True)
    with tabs[4]:
        st.subheader("Run All Semantic Evidence Review")
        st.caption("One run evaluates every detected claim. It excludes negated findings, boilerplate, and keyword-only mentions, then places high-value findings into the review queue automatically.")
        claims = db.list_claims(project_id)
        if not claims:
            st.info("Upload and process a Form 20-0995 first so the claims can be detected automatically.")
        else:
            threshold_percent = st.slider("Minimum score for pending annotation (%)", 60, 95, 72, 1, key="bulk_semantic_threshold_percent")
            threshold = threshold_percent / 100.0
            st.caption(f"Findings scoring {threshold_percent}% or higher may enter the pending Evidence Review Queue.")
            auto_fill = st.checkbox("Automatically add qualifying findings to the Evidence Review Queue", value=True)
            if st.button("Run Semantic Evidence Review for All Claims", type="primary"):
                with st.spinner("Analyzing all claims and linked evidence..."):
                    st.session_state['bulk_semantic_result'] = BulkProjectAnalysis(db).run_semantic_all(project_id, threshold, auto_fill)
                st.rerun()
            result = st.session_state.get('bulk_semantic_result')
            if result:
                st.success(
                    f"Analyzed {result['total_claims']} claim(s), identified {result['total_candidates']} candidate finding(s), "
                    f"and created {result['created']} pending review item(s)."
                )
                rows = []
                for item in result['by_claim'].values():
                    candidates = item['candidates']
                    counts = {}
                    for candidate in candidates:
                        counts[candidate['auto_action']] = counts.get(candidate['auto_action'], 0) + 1
                    rows.append({
                        'claim': item['claim']['condition_name'],
                        'suggested_support': counts.get('suggest_for_autofill', 0),
                        'manual_review': counts.get('manual_review_only', 0),
                        'negative_context': counts.get('exclude_from_favorable_autofill', 0),
                        'suppressed': counts.get('suppress', 0),
                        'queue_created': item.get('autofill', {}).get('created', 0),
                    })
                st.dataframe(rows, use_container_width=True, hide_index=True)
                with st.expander("Review findings by claim", expanded=False):
                    labels = {item['claim']['condition_name']: item for item in result['by_claim'].values()}
                    selected = labels[st.selectbox("Claim", labels.keys(), key="bulk_semantic_detail_claim")]
                    shown = [dict(c, relevance_percent=round(float(c.get('relevance_score', 0)) * 100, 1)) for c in selected['candidates'] if c['auto_action'] != 'suppress']
                    st.dataframe(shown, use_container_width=True, hide_index=True, column_config={"relevance_percent": st.column_config.ProgressColumn("Relevance (%)", min_value=0, max_value=100, format="%.1f%%")})
                    coverage = ClaimElementSummary().build(selected['claim'], db.list_annotations(project_id), selected['candidates'])
                    st.markdown("#### Claim-element coverage")
                    st.dataframe(coverage, use_container_width=True, hide_index=True)
            else:
                st.info("Select Run Semantic Evidence Review for All Claims. No claim-by-claim selection is required.")
    with tabs[5]:
        st.subheader("Contradiction Review")
        if st.button("Rebuild contradiction analysis"):
            items=ContradictionEngine().analyze(db.list_annotations(project_id),db.list_timeline(project_id)); db.add_contradictions(project_id,items); st.rerun()
        conflicts=db.list_contradictions(project_id,"open")
        if not conflicts: st.success("No open contradictions in the current analysis.")
        for c in conflicts:
            with st.expander(f"{c['severity'].upper()} — {c['summary']}"):
                st.write(c['resolution_prompt']); note=st.text_area("Resolution note",key=f"cres_{c['id']}")
                if st.button("Mark resolved",key=f"cr_{c['id']}",disabled=not note.strip()): db.resolve_contradiction(c['id'],note); st.rerun()
    with tabs[6]:
        st.subheader("Evidence Approval Queue"); pending=db.list_annotations(project_id,"pending")
        if not pending: st.info("No pending AI evidence annotations.")
        for ann in pending:
            with st.expander(f"{ann['claim_element']}: {ann['finding'][:100]}"):
                st.code(ann.get('quote') or '')
                element=st.text_input("Claim element",value=ann['claim_element'],key=f"element_{ann['id']}")
                polarity=st.selectbox("Polarity",["favorable","unfavorable","neutral","ambiguous"],index=["favorable","unfavorable","neutral","ambiguous"].index(ann.get('polarity','ambiguous')),key=f"pol_{ann['id']}")
                finding=st.text_area("Evidence proposition",value=ann['finding'],key=f"finding_{ann['id']}")
                note=st.text_area("Reviewer rationale / correction",value=ann.get('reviewer_note') or '',key=f"note_{ann['id']}")
                c0,c1,c2,c3=st.columns(4)
                if c0.button("Save edits",key=f"s_{ann['id']}"):
                    db.update_annotation(ann['id'],claim_element=element,polarity=polarity,finding=finding,reviewer_note=note); st.rerun()
                if c1.button("Approve",key=f"a_{ann['id']}"):
                    db.update_annotation(ann['id'],claim_element=element,polarity=polarity,finding=finding,reviewer_note=note); db.review_annotation(ann['id'],"approved",note); st.rerun()
                if c2.button("Reject",key=f"r_{ann['id']}"): db.review_annotation(ann['id'],"rejected",note); st.rerun()
                if c3.button("Needs edit",key=f"e_{ann['id']}"): db.review_annotation(ann['id'],"needs_edit",note); st.rerun()
    with tabs[7]:
        st.subheader("Cross-Document Corroboration and Claim Synthesis")
        claims=db.list_claims(project_id)
        if not claims:
            st.info("Add a claim first.")
        else:
            labels={f"{c['condition_name']} ({c['theory']})":c for c in claims}
            chosen=labels[st.selectbox("Claim",labels.keys(),key="synthesis_claim")]
            enriched=db.list_annotations_enriched(project_id)
            clusters=[x for x in CrossDocumentCorroborator().build(enriched) if x['claim_id']==chosen['id']]
            st.caption("Repeated notes from the same chart are counted as one evidence stream. Independent documents and source types receive greater weight.")
            if clusters: st.dataframe(clusters,use_container_width=True,hide_index=True,column_config={"corroboration_score":st.column_config.ProgressColumn("Corroboration",min_value=0,max_value=1)})
            synthesis=ClaimSynthesisEngine().build(chosen,enriched,db.list_timeline(project_id),db.list_contradictions(project_id))
            st.markdown("#### Clear evidence ties")
            if synthesis['clear_ties']: st.dataframe(synthesis['clear_ties'],use_container_width=True,hide_index=True)
            else: st.info("No approved favorable evidence ties are available yet.")
            st.markdown("#### Timeline and bridge analysis")
            st.json({"timeline":synthesis['timeline'],"bridge_statements":synthesis['bridge_statements'],"missing_elements":synthesis['missing_elements'],"drafting_status":synthesis['drafting_status']})
            if st.button("Generate claim evidence synthesis",disabled=not synthesis['clear_ties']):
                paths=SynthesisPacketGenerator(project_root/'outputs').generate(synthesis); st.session_state['synthesis_paths']=[str(x) for x in paths]
            for path in st.session_state.get('synthesis_paths',[]):
                pth=Path(path); st.download_button(f"Download {pth.name}",pth.read_bytes(),file_name=pth.name,key=f"syn_{pth.name}")
    with tabs[8]:
        st.subheader("Claim Drafting Intelligence")
        claims=db.list_claims(project_id)
        if not claims:
            st.info("Add a claim first.")
        else:
            labels={f"{c['condition_name']} ({c['theory']})":c for c in claims}
            chosen=labels[st.selectbox("Claim for drafting",labels.keys(),key="drafting_claim")]
            document_type=st.selectbox("Review draft type",["doctor_nexus","personal_statement","buddy_letter"],key="draft_type")
            starting_text=st.text_area("Optional uploaded/current draft text",height=220,help="Paste the current working draft here. It will be preserved as the starting point and checked against approved facts.")
            matrix=ApprovedFactMatrix().build(chosen,db.list_annotations_enriched(project_id),db.list_timeline(project_id))
            st.metric("Approved draftable facts",matrix['draftable_fact_count'])
            if matrix['facts_by_element']:
                rows=[f for values in matrix['facts_by_element'].values() for f in values]
                st.dataframe(rows,use_container_width=True,hide_index=True)
            validation=DraftFactValidator().validate(starting_text,matrix,document_type) if starting_text.strip() else {"valid":True,"warnings":[]}
            if validation['warnings']:
                st.warning("The starting draft contains assertions requiring review.")
                st.dataframe(validation['warnings'],use_container_width=True,hide_index=True)
            package=ClaimDraftingIntelligence().build_sections(matrix,document_type,starting_text)
            with st.expander("Preview generated structure"):
                st.json(package)
            if st.button("Generate source-grounded review draft",disabled=matrix['draftable_fact_count']==0):
                paths=ClaimDraftingIntelligence().export(package,project_root/'outputs')
                st.session_state['draft_intelligence_paths']=[str(x) for x in paths]
            for path in st.session_state.get('draft_intelligence_paths',[]):
                pth=Path(path); st.download_button(f"Download {pth.name}",pth.read_bytes(),file_name=pth.name,key=f"di_{pth.name}")
    with tabs[9]:
        st.subheader("Rating Criteria, Staged Severity, and Denial Response")
        st.warning("This is a preliminary review aid. Verify the current VA regulation, diagnostic code, and original denial language before using any result.")
        claims=db.list_claims(project_id)
        if not claims:
            st.info("Add a claim first.")
        else:
            labels={f"{c['condition_name']} ({c['theory']})":c for c in claims}
            chosen=labels[st.selectbox("Claim to evaluate",labels.keys(),key="rating_claim")]
            approved=db.list_annotations_enriched(project_id,status="approved")
            timeline=db.list_timeline(project_id)
            rating=RatingCriteriaEngine().evaluate(chosen,approved,timeline)
            st.markdown("#### Evidence-to-criteria comparison")
            if rating.get("levels"):
                st.dataframe(rating["levels"],use_container_width=True,hide_index=True)
                st.caption(f"Preliminary highest fully matched level: {rating.get('best_supported_level') if rating.get('best_supported_level') is not None else 'None established'}")
            else:
                st.info(rating.get("warning"))
            staged=StagedSeverityAnalyzer().analyze(chosen['id'],approved,timeline)
            st.markdown("#### Staged severity review")
            if staged['stages']: st.dataframe(staged['stages'],use_container_width=True,hide_index=True)
            else: st.info("No dated approved evidence or timeline events are available for staged review.")
            st.caption(staged['warning'])
            st.markdown("#### Prior denial-letter response")
            denial_text=st.text_area("Paste extracted text from the applicable VA denial letter",height=180,key="denial_text")
            if denial_text.strip():
                analysis=DenialDecisionAnalyzer().analyze_text(denial_text,chosen['condition_name'])
                st.json(analysis)

    with tabs[10]:
        st.subheader("DBQ/C&P Examination Intelligence and Evidence Action Plan")
        st.caption("Paste extracted DBQ or C&P text for a conservative section-by-section review. Detected content remains unverified until compared with the original examination.")
        claims=db.list_claims(project_id)
        if not claims:
            st.info("Add a claim first.")
        else:
            labels={f"{c['condition_name']} ({c['theory']})":c for c in claims}
            chosen=labels[st.selectbox("Claim",labels.keys(),key="dbq_claim")]
            exam_text=st.text_area("Extracted DBQ/C&P text",height=240,key="dbq_text")
            parsed=DBQCPParser().parse(exam_text,"manual DBQ/C&P input") if exam_text.strip() else None
            if parsed:
                st.markdown("#### Structured examination review")
                st.json(parsed)
            anns=db.list_annotations(project_id); timeline=db.list_timeline(project_id); conflicts=db.list_contradictions(project_id)
            readiness=ReadinessEngine().assess(chosen,anns,timeline,conflicts)
            rating=RatingCriteriaEngine().evaluate(chosen,db.list_annotations_enriched(project_id,status="approved"),timeline)
            denial_text=st.text_area("Optional denial text for combined gap planning",height=120,key="action_denial")
            denial=DenialDecisionAnalyzer().analyze_text(denial_text,chosen['condition_name']) if denial_text.strip() else None
            plan=EvidenceGapActionPlanner().build(chosen,readiness,rating,denial,parsed)
            st.markdown("#### Prioritized evidence-development plan")
            if plan['actions']: st.dataframe(plan['actions'],use_container_width=True,hide_index=True)
            else: st.success("No unresolved evidence-development actions were generated from the current approved record.")
            st.caption(plan['warning'])

    with tabs[11]:
        st.subheader("Medical Literature and Specialist Nexus Review Packet")
        st.warning("Literature supports general medical principles only. It does not prove patient-specific causation and must be independently reviewed by the clinician.")
        claims=db.list_claims(project_id)
        if not claims:
            st.info("Add a claim first.")
        else:
            labels={f"{c['condition_name']} ({c['theory']})":c for c in claims}
            chosen=labels[st.selectbox("Claim",labels.keys(),key="literature_claim")]
            with st.form("literature_candidate"):
                title=st.text_input("Article or guideline title")
                authors=st.text_input("Authors")
                c1,c2=st.columns(2); year=c1.text_input("Year"); source=c2.text_input("Journal / issuing organization")
                c3,c4,c5=st.columns(3); doi=c3.text_input("DOI"); pmid=c4.text_input("PMID"); url=c5.text_input("Source URL")
                abstract=st.text_area("Abstract or verified summary",height=140)
                if st.form_submit_button("Assess and save literature candidate") and title.strip():
                    candidate={"title":title,"authors":authors,"year":year,"source":source,"doi":doi,"pmid":pmid,"url":url,"abstract":abstract}
                    assessment=LiteratureSupportEngine().assess_candidate(candidate,chosen)
                    candidate.update(assessment); candidate["claim_id"]=chosen['id']
                    db.add_literature_source(project_id,candidate); st.session_state['literature_assessment']=assessment; st.rerun()
            if 'literature_assessment' in st.session_state: st.json(st.session_state['literature_assessment'])
            literature=db.list_literature_sources(project_id,chosen['id'])
            if literature: st.dataframe(literature,use_container_width=True,hide_index=True)
            matrix=ApprovedFactMatrix().build(chosen,db.list_annotations_enriched(project_id),db.list_timeline(project_id))
            packet=SpecialistPacketGenerator().build(chosen,matrix,literature)
            st.caption(f"Suggested reviewing specialty: {packet['recommended_specialty']}")
            if st.button("Generate specialist nexus review packet",disabled=matrix.get('draftable_fact_count',0)==0):
                paths=SpecialistPacketGenerator().export(packet,project_root/'outputs')
                st.session_state['specialist_packet_paths']=[str(x) for x in paths]
            for path in st.session_state.get('specialist_packet_paths',[]):
                pth=Path(path); st.download_button(f"Download {pth.name}",pth.read_bytes(),file_name=pth.name,key=f"sp_{pth.name}")

    with tabs[12]:
        st.subheader("Potential Unclaimed Conditions Discovery")
        st.warning("This is a conservative discovery aid, not a diagnosis or filing recommendation. Review all candidates against the original records and current VA rules.")
        existing=db.list_claims(project_id)
        approved=db.list_annotations_enriched(project_id,status="approved")
        timeline=db.list_timeline(project_id)
        military_rows=[x for x in timeline if x.get("source_type") in {"military_verified","veteran_reported","witness_reported"}]
        military_rows += [x for x in approved if (x.get("category") or "") in {"military_records","smart_transcript","dd214","medical_records"}]
        current_rows=[x for x in approved if x.get("polarity")=="favorable"]
        if st.button("Scan for potentially unclaimed conditions"):
            st.session_state["potential_claim_discovery"]=PotentialClaimDiscoveryEngine().discover(existing,military_rows,current_rows)
        result=st.session_state.get("potential_claim_discovery")
        if result:
            if result["candidates"]:
                st.dataframe(result["candidates"],use_container_width=True,hide_index=True,column_config={"confidence":st.column_config.ProgressColumn("Discovery confidence",min_value=0,max_value=1)})
            else:
                st.info("No additional condition currently has both affirmative current evidence and a plausible military/service anchor.")
            st.markdown("#### Generated review prompt")
            st.text_area("Copy or retain this prompt",value=result["prompt"],height=300)
            st.caption(result["disclaimer"])

    with tabs[13]:
        st.subheader("Automation, Candidate Promotion, and Project Backup")
        st.caption("This workspace turns reviewed discovery candidates into full claim work plans and shows the exact project-wide actions remaining before final assembly.")
        result=st.session_state.get("potential_claim_discovery")
        if result and result.get("candidates"):
            names=[c["condition"] for c in result["candidates"]]
            selected_names=st.multiselect("Reviewed candidates to add as claims",names)
            if st.button("Promote selected candidates and create complete document plans",disabled=not selected_names):
                service=CandidateClaimPromotionService(); promoted=[]
                for candidate in result["candidates"]:
                    if candidate["condition"] in selected_names:
                        promoted.append(service.promote(db,project_id,candidate).__dict__)
                st.session_state["promoted_candidates"]=promoted
                st.rerun()
        else:
            st.info("Run Potential Unclaimed Conditions Discovery first. Only reviewed candidates can be promoted.")
        if st.session_state.get("promoted_candidates"):
            st.markdown("#### Added claims and planned associated documents")
            st.json(st.session_state["promoted_candidates"])
        plan=ProjectOrchestrator().build_plan(db,project_id)
        st.markdown("#### Project-wide completion plan")
        st.json(plan["summary"])
        if plan["next_actions"]: st.dataframe(plan["next_actions"],use_container_width=True,hide_index=True)
        else: st.success("No blocking project-wide actions remain. The project is ready for final assembly review.")
        if st.button("Create checksum-backed project backup"):
            backup=ProjectBackupService().create(project_root,project_root/'outputs'/'backups')
            st.session_state['project_backup']=backup
        if st.session_state.get('project_backup'):
            backup=st.session_state['project_backup']; st.json(backup)
            bp=Path(backup['backup_zip'])
            if bp.exists(): st.download_button("Download project backup",bp.read_bytes(),file_name=bp.name)

    with tabs[14]:
        st.subheader("Readiness and Final Review Package")
        claims=db.list_claims(project_id); anns=db.list_annotations(project_id); timeline=db.list_timeline(project_id); conflicts=db.list_contradictions(project_id)
        engine=ReadinessEngine(); readiness=[engine.assess(c,anns,timeline,conflicts) for c in claims]
        rating_engine=RatingCriteriaEngine(); gate_engine=SubmissionReadinessGate(); docs=db.list_documents(project_id)
        gates=[]
        for claim,ready in zip(claims,readiness):
            rating=rating_engine.evaluate(claim,db.list_annotations_enriched(project_id,status="approved"),timeline)
            gates.append(gate_engine.assess(claim,ready,rating,conflicts,docs))
        if readiness: st.dataframe(readiness,use_container_width=True,hide_index=True)
        if gates:
            st.markdown("#### Submission gates")
            st.dataframe(gates,use_container_width=True,hide_index=True)
        assembly=FinalPackageAssemblyValidator().validate(claims,docs,gates)
        st.markdown("#### Final package assembly validation")
        st.json(assembly)
        if st.button("Build checksum-backed final review binder",disabled=assembly.get('blocked',True)):
            generated=list(st.session_state.get('generated_paths',[]))+list(st.session_state.get('specialist_packet_paths',[]))+list(st.session_state.get('draft_intelligence_paths',[]))+list(st.session_state.get('synthesis_paths',[]))
            result=SubmissionBinderAssembler().assemble('VA Claim Builder Project',claims,docs,generated,project_root/'outputs'/'binder')
            st.session_state['binder_result']=result
        if st.session_state.get('binder_result'):
            st.json(st.session_state['binder_result'])
            z=st.session_state['binder_result'].get('binder_zip')
            if z and Path(z).exists(): st.download_button("Download final review binder ZIP",Path(z).read_bytes(),file_name=Path(z).name)
        if st.button("Generate readiness package",disabled=not readiness):
            out=project_root/'outputs'; paths=FinalPackageGenerator(out).generate('VA Claim Builder Project',readiness,[a for a in anns if a.get('review_status')=='approved'],timeline,conflicts)
            st.session_state['generated_paths']=[str(x) for x in paths]
        for path in st.session_state.get('generated_paths',[]):
            p=Path(path); st.download_button(f"Download {p.name}",p.read_bytes(),file_name=p.name)

    with tabs[15]:
        st.subheader("System Health, Security, and Recovery")
        health=SystemHealthChecker(project_root).run(db.path)
        st.json(health)
        security=SecurityReview().run(project_root)
        st.markdown("#### Security review")
        st.json(security)
        recovery=WorkflowRecoveryService(db.path)
        resumable=recovery.resumable(project_id)
        st.markdown("#### Interrupted or failed workflows")
        if resumable: st.dataframe(resumable,use_container_width=True,hide_index=True)
        else: st.success("No interrupted workflows require recovery.")
        if st.button("Run one-click project preflight",disabled=health.get("overall")!="ready"):
            try:
                st.session_state["one_click_result"]=OneClickProjectProcessor(db,project_id,project_root).run()
                st.success("Project preflight completed. Review each stage result before final generation.")
            except Exception as exc: st.error(str(exc))
        if st.session_state.get("one_click_result"): st.json(st.session_state["one_click_result"])
        st.caption("Installation helpers: scripts/install_windows.bat and scripts/install_mac_linux.sh")

    with tabs[16]:
        st.subheader("Final Adversarial Review, Representative Export, and Closeout")
        st.caption("This workspace tries to disprove or weaken each claim before final submission, so unsupported assertions and likely objections can be corrected.")
        claims=db.list_claims(project_id); approved=db.list_annotations_enriched(project_id,status="approved"); timeline=db.list_timeline(project_id); conflicts=db.list_contradictions(project_id)
        if not claims:
            st.info("Add claims and approve evidence first.")
        else:
            adversarial=[AdversarialReviewEngine().review(c,approved,timeline,conflicts) for c in claims]
            theories=[ClaimTheoryComparisonEngine().compare(c,approved) for c in claims]
            summary=[{"condition":r["condition"],"defensibility_score":r["defensibility_score"],"status":r["status"],"issue_count":len(r["findings"])} for r in adversarial]
            st.dataframe(summary,use_container_width=True,hide_index=True,column_config={"defensibility_score":st.column_config.ProgressColumn("Defensibility",min_value=0,max_value=100)})
            labels={c["condition_name"]:c for c in claims}; selected=labels[st.selectbox("Claim for detailed challenge review",labels.keys(),key="adv_claim")]
            review=next(r for r in adversarial if r["claim_id"]==selected["id"]); theory=next(r for r in theories if r["claim_id"]==selected["id"])
            st.markdown("#### Likely objections and corrective actions")
            if review["findings"]: st.dataframe(review["findings"],use_container_width=True,hide_index=True)
            else: st.success("No automated adversarial findings remain for this claim.")
            st.markdown("#### Alternative theory comparison")
            st.dataframe(theory["theories"],use_container_width=True,hide_index=True)
            if st.button("Generate factual C&P preparation packet"):
                packet=CPExamPreparationGenerator().build(selected,approved,timeline,conflicts); path=CPExamPreparationGenerator().export(packet,project_root/'outputs')
                st.session_state['cp_prep_path']=str(path)
            if st.session_state.get('cp_prep_path'):
                pth=Path(st.session_state['cp_prep_path']); st.download_button("Download C&P factual preparation packet",pth.read_bytes(),file_name=pth.name)
            if st.button("Generate accredited-representative review export"):
                package=AccreditedRepresentativeExport().build(claims,theories,adversarial,[],[])
                paths=AccreditedRepresentativeExport().export(package,project_root/'outputs'/'representative_review'); st.session_state['rep_paths']=[str(x) for x in paths]
            for raw in st.session_state.get('rep_paths',[]):
                pth=Path(raw); st.download_button(f"Download {pth.name}",pth.read_bytes(),file_name=pth.name,key=f"rep_{pth.name}")
            generated=list(st.session_state.get('generated_paths',[]))+list(st.session_state.get('specialist_packet_paths',[]))+list(st.session_state.get('draft_intelligence_paths',[]))+list(st.session_state.get('synthesis_paths',[]))+list(st.session_state.get('rep_paths',[]))
            audit=FinalFactualAudit().audit_files(generated) if generated else {"files":[],"all_present":True}
            health=SystemHealthChecker(project_root).run(db.path); security=SecurityReview().run(project_root)
            readiness_engine=ReadinessEngine(); rating_engine=RatingCriteriaEngine(); gate_engine=SubmissionReadinessGate(); docs=db.list_documents(project_id)
            gates=[]
            for c in claims:
                ready=readiness_engine.assess(c,db.list_annotations(project_id),timeline,conflicts); rating=rating_engine.evaluate(c,approved,timeline); gates.append(gate_engine.assess(c,ready,rating,conflicts,docs))
            closeout=FinalCloseoutChecklist().assess(health,security,claims,gates,audit)
            st.markdown("#### Final closeout status"); st.json(closeout)
