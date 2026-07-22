from __future__ import annotations
from pathlib import Path
import json
from PySide6.QtCore import Qt,QThread
from PySide6.QtWidgets import (QApplication,QComboBox,QFileDialog,QFormLayout,QHBoxLayout,QLabel,QLineEdit,QListWidget,QListWidgetItem,QMessageBox,QPushButton,QSplitter,QTableWidget,QTableWidgetItem,QTabWidget,QTextEdit,QVBoxLayout,QWidget)
from core.claims import ClaimManager
from core.documents import DocumentManager
from core.evidence import EvidenceManager
from core.projects import AppPaths,ProjectInfo
from core.settings import SettingsManager
from core.timeline import DATE_PRECISIONS,EVENT_TYPES,TimelineExtractionService,TimelineManager
from workers import TimelineExtractionWorker
class TimelinePage(QWidget):
 def __init__(self,project:ProjectInfo,parent=None):
  super().__init__(parent);self.project=project;self.manager=TimelineManager(project);self.claims=ClaimManager(project);self.documents=DocumentManager(project);self.evidence=EvidenceManager(project)
  paths=AppPaths(root=project.root.parent.parent).ensure();self.extractor=TimelineExtractionService(project,settings_manager=SettingsManager(paths));self.current_id=None;self.thread=None;self.worker=None
  heading=QLabel("Medical Timeline");heading.setStyleSheet("font-size:22px;font-weight:600;");advice=QLabel("Confirmed events are user-managed. AI-extracted candidates remain separate until reviewed and saved.");advice.setWordWrap(True)
  self.search=QLineEdit();self.search.setPlaceholderText("Search timeline…");self.date_from=QLineEdit();self.date_from.setPlaceholderText("From date");self.date_to=QLineEdit();self.date_to.setPlaceholderText("To date")
  self.type_filter=QComboBox();self.type_filter.addItem("All event types","");[self.type_filter.addItem(x.title(),x) for x in EVENT_TYPES]
  self.provider_filter=QLineEdit();self.provider_filter.setPlaceholderText("Provider");self.claim_filter=QComboBox();self.body_filter=QLineEdit();self.body_filter.setPlaceholderText("Body system / condition")
  refresh=QPushButton("Refresh");refresh.clicked.connect(self.refresh)
  for w in (self.search,self.date_from,self.date_to,self.provider_filter,self.body_filter):w.textChanged.connect(self.refresh)
  self.type_filter.currentIndexChanged.connect(self.refresh);self.claim_filter.currentIndexChanged.connect(self.refresh)
  filters=QHBoxLayout();[filters.addWidget(x) for x in (self.search,self.date_from,self.date_to,self.type_filter,self.provider_filter,self.claim_filter,self.body_filter,refresh)]
  self.table=QTableWidget(0,7);self.table.setHorizontalHeaderLabels(["Date","End","Type","Title","Provider / Facility","Condition","Source"]);self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows);self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);self.table.itemSelectionChanged.connect(self._load);self.table.horizontalHeader().setStretchLastSection(True)
  self.title=QLineEdit();self.event_date=QLineEdit();self.end_date=QLineEdit();self.precision=QComboBox();self.precision.addItems(DATE_PRECISIONS);self.event_type=QComboBox();self.event_type.addItems(EVENT_TYPES);self.description=QTextEdit();self.provider=QLineEdit();self.condition=QLineEdit();self.document=QComboBox();self.source_evidence=QComboBox();self.treatment=QLineEdit();self.diagnosis=QLineEdit();self.symptoms=QLineEdit();self.medications=QLineEdit();self.testing=QLineEdit();self.impact=QLineEdit();self.service=QLineEdit();self.notes=QTextEdit();self.claim_links=QListWidget()
  form=QFormLayout()
  for label,w in (("Title",self.title),("Event date",self.event_date),("End date",self.end_date),("Date precision",self.precision),("Event type",self.event_type),("Provider / facility",self.provider),("Body system / condition",self.condition),("Source document",self.document),("Source evidence",self.source_evidence),("Description",self.description),("Treatment",self.treatment),("Diagnosis",self.diagnosis),("Symptoms (semicolon separated)",self.symptoms),("Medications (semicolon separated)",self.medications),("Testing / imaging",self.testing),("Functional impact",self.impact),("Service-period relevance",self.service),("Notes",self.notes),("Linked claims",self.claim_links)):form.addRow(label,w)
  editor=QWidget();editor.setLayout(form);split=QSplitter();split.addWidget(self.table);split.addWidget(editor);split.setStretchFactor(0,3);split.setStretchFactor(1,2)
  new=QPushButton("New Event");new.clicked.connect(self.clear);save=QPushButton("Save Event");save.clicked.connect(self.save);delete=QPushButton("Delete Event");delete.clicked.connect(self.delete);copy=QPushButton("Copy Selected Text");copy.clicked.connect(self.copy);export=QPushButton("Export CSV…");export.clicked.connect(self.export)
  buttons=QHBoxLayout();[buttons.addWidget(x) for x in (new,save,delete,copy,export)];buttons.addStretch()
  confirmed=QWidget();cl=QVBoxLayout(confirmed);cl.addLayout(buttons);cl.addLayout(filters);cl.addWidget(split)
  self.evidence_sources=QListWidget();self.document_source=QComboBox();self.extract_evidence=QPushButton("Extract Checked Evidence");self.extract_evidence.clicked.connect(self._extract_evidence);self.extract_document=QPushButton("Extract Document");self.extract_document.clicked.connect(self._extract_document);self.cancel=QPushButton("Cancel Extraction");self.cancel.setEnabled(False);self.cancel.clicked.connect(self._cancel);self.extraction_status=QLabel("Ready")
  source_row=QHBoxLayout();[source_row.addWidget(x) for x in (self.document_source,self.extract_document,self.extract_evidence,self.cancel)]
  self.candidate_state=QLabel("No extracted candidates yet.");self.candidates=QTableWidget(0,6);self.candidates.setHorizontalHeaderLabels(["Status","Date","Type","Title","Provider","Duplicate?"]);self.candidates.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows);self.candidates.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection);self.candidates.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked);self.candidates.itemChanged.connect(self._candidate_edited);self.candidates.itemSelectionChanged.connect(self._load_candidate_editor)
  self.candidate_editor=QTextEdit();self.candidate_editor.setPlaceholderText("Select a candidate to edit all structured fields as JSON.");save_candidate_edit=QPushButton("Save Candidate Edits");save_candidate_edit.clicked.connect(self._save_candidate_editor)
  accept=QPushButton("Accept Candidate");accept.clicked.connect(lambda:self._candidate_action("accept"));reject=QPushButton("Reject Candidate");reject.clicked.connect(lambda:self._candidate_action("reject"));merge=QPushButton("Merge Into Selected Target");merge.clicked.connect(self._merge);save_candidates=QPushButton("Save Accepted Events");save_candidates.clicked.connect(self._save_candidates)
  cb=QHBoxLayout();[cb.addWidget(x) for x in (accept,reject,merge,save_candidates)];cb.addStretch()
  candidates=QWidget();xl=QVBoxLayout(candidates);xl.addWidget(QLabel("Evidence sources (check one or more; current filters are respected in the Evidence workspace):"));xl.addWidget(self.evidence_sources);xl.addLayout(source_row);xl.addWidget(self.extraction_status);xl.addWidget(self.candidate_state);xl.addWidget(self.candidates,1);xl.addWidget(QLabel("Selected candidate fields"));xl.addWidget(self.candidate_editor);xl.addWidget(save_candidate_edit);xl.addLayout(cb)
  self.narrative=QTextEdit();self.narrative.setReadOnly(True);narrative=QWidget();nl=QVBoxLayout(narrative);nl.addWidget(QLabel("Chronological narrative of confirmed timeline events"));nl.addWidget(self.narrative)
  self.tabs=QTabWidget();self.tabs.addTab(confirmed,"Structured Table");self.tabs.addTab(narrative,"Narrative");self.tabs.addTab(candidates,"Candidate Review")
  layout=QVBoxLayout(self);layout.addWidget(heading);layout.addWidget(advice);layout.addWidget(self.tabs);self._options();self.refresh()
 def _options(self):
  self.claim_filter.clear();self.claim_filter.addItem("All claims","");self.claim_links.clear()
  for c in self.claims.list_claims():self.claim_filter.addItem(c.condition_name,c.claim_id);i=QListWidgetItem(c.condition_name);i.setData(Qt.ItemDataRole.UserRole,c.claim_id);i.setFlags(i.flags()|Qt.ItemFlag.ItemIsUserCheckable);i.setCheckState(Qt.CheckState.Unchecked);self.claim_links.addItem(i)
  self.document.clear();self.document.addItem("No document",None);self.document_source.clear();self.document_source.addItem("Select document",None)
  for d in self.documents.list_documents():self.document.addItem(d.original_name,d.document_id);self.document_source.addItem(f"{d.original_name} — {d.status.replace('_',' ').title()}",d.document_id)
  self.source_evidence.clear();self.source_evidence.addItem("No evidence",None);self.evidence_sources.clear()
  for e in self.evidence.list():self.source_evidence.addItem(e.title,e.evidence_id);i=QListWidgetItem(e.title);i.setData(Qt.ItemDataRole.UserRole,e.evidence_id);i.setFlags(i.flags()|Qt.ItemFlag.ItemIsUserCheckable);i.setCheckState(Qt.CheckState.Unchecked);self.evidence_sources.addItem(i)
 def refresh(self):
  if not hasattr(self,"table"):return
  selected=self.current_id;events=self.manager.list(search=self.search.text(),date_from=self.date_from.text(),date_to=self.date_to.text(),event_type=self.type_filter.currentData() or "",provider=self.provider_filter.text(),claim_id=self.claim_filter.currentData() or "",body_system=self.body_filter.text());self.table.setRowCount(len(events))
  for r,e in enumerate(events):
   for c,v in enumerate((e.event_date,e.end_date,e.event_type.title(),e.title,e.provider_facility,e.body_system_condition,e.document_name or e.evidence_title or "Manual")):i=QTableWidgetItem(v);i.setData(Qt.ItemDataRole.UserRole,e.event_id);self.table.setItem(r,c,i)
  self.narrative.setPlainText(self.manager.narrative(events));self._refresh_candidates()
  for r in range(self.table.rowCount()):
   if self.table.item(r,0).data(Qt.ItemDataRole.UserRole)==selected:self.table.selectRow(r);break
 def clear(self):self.current_id=None;[w.clear() for w in (self.title,self.event_date,self.end_date,self.description,self.provider,self.condition,self.treatment,self.diagnosis,self.symptoms,self.medications,self.testing,self.impact,self.service,self.notes)];self.precision.setCurrentText("unknown");self.event_type.setCurrentText("other");self.document.setCurrentIndex(0);self.source_evidence.setCurrentIndex(0);self.table.clearSelection()
 def _values(self):return dict(event_date=self.event_date.text(),end_date=self.end_date.text(),date_precision=self.precision.currentText(),event_type=self.event_type.currentText(),description=self.description.toPlainText(),provider_facility=self.provider.text(),body_system_condition=self.condition.text(),document_id=self.document.currentData(),evidence_id=self.source_evidence.currentData(),treatment=self.treatment.text(),diagnosis=self.diagnosis.text(),symptoms=self.symptoms.text().split(";") if self.symptoms.text() else [],medications=self.medications.text().split(";") if self.medications.text() else [],testing_imaging=self.testing.text(),functional_impact=self.impact.text(),service_period_relevance=self.service.text(),notes=self.notes.toPlainText())
 def _claims(self):return [str(self.claim_links.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.claim_links.count()) if self.claim_links.item(i).checkState()==Qt.CheckState.Checked]
 def save(self):
  try:
   e=self.manager.update(self.current_id,title=self.title.text(),claim_ids=self._claims(),**self._values()) if self.current_id else self.manager.create(self.title.text(),claim_ids=self._claims(),**self._values());self.current_id=e.event_id;self.refresh()
  except Exception as exc:QMessageBox.warning(self,"Timeline",str(exc))
 def _load(self):
  r=self.table.currentRow()
  if r<0:return
  e=self.manager.get(str(self.table.item(r,0).data(Qt.ItemDataRole.UserRole)));self.current_id=e.event_id;self.title.setText(e.title);self.event_date.setText(e.event_date);self.end_date.setText(e.end_date);self.precision.setCurrentText(e.date_precision);self.event_type.setCurrentText(e.event_type);self.description.setPlainText(e.description);self.provider.setText(e.provider_facility);self.condition.setText(e.body_system_condition);self.document.setCurrentIndex(max(0,self.document.findData(e.document_id)));self.source_evidence.setCurrentIndex(max(0,self.source_evidence.findData(e.evidence_id)));self.treatment.setText(e.treatment);self.diagnosis.setText(e.diagnosis);self.symptoms.setText("; ".join(e.symptoms));self.medications.setText("; ".join(e.medications));self.testing.setText(e.testing_imaging);self.impact.setText(e.functional_impact);self.service.setText(e.service_period_relevance);self.notes.setPlainText(e.notes)
  for i in range(self.claim_links.count()):self.claim_links.item(i).setCheckState(Qt.CheckState.Checked if self.claim_links.item(i).data(Qt.ItemDataRole.UserRole) in e.claim_ids else Qt.CheckState.Unchecked)
 def delete(self):
  if self.current_id and QMessageBox.question(self,"Delete timeline event","Delete this confirmed timeline event?")==QMessageBox.StandardButton.Yes:self.manager.delete(self.current_id);self.clear();self.refresh()
 def copy(self):
  if self.current_id:QApplication.clipboard().setText(self.manager.narrative([self.manager.get(self.current_id)]))
 def export(self):
  path,_=QFileDialog.getSaveFileName(self,"Export Timeline CSV","medical-timeline.csv","CSV (*.csv)")
  if path:self.manager.export_csv(Path(path))
 def _checked_evidence(self):return [str(self.evidence_sources.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.evidence_sources.count()) if self.evidence_sources.item(i).checkState()==Qt.CheckState.Checked]
 def _extract_evidence(self):
  ids=self._checked_evidence()
  if not ids:QMessageBox.information(self,"Timeline extraction","Check evidence items first.");return
  self._start(evidence_ids=ids)
 def _extract_document(self):
  if not self.document_source.currentData():QMessageBox.information(self,"Timeline extraction","Select a document first.");return
  self._start(document_ids=[str(self.document_source.currentData())])
 def _start(self,**sources):
  if self.thread:return
  paths=AppPaths(root=self.project.root.parent.parent).ensure();thread=QThread(self);worker=TimelineExtractionWorker(self.project,service_factory=lambda p:TimelineExtractionService(p,settings_manager=SettingsManager(paths)),**sources);worker.moveToThread(thread);thread.started.connect(worker.run);worker.progress.connect(lambda p,m:self.extraction_status.setText(f"{p}% — {m}"));worker.completed.connect(lambda _:self._refresh_candidates());worker.failed.connect(lambda m:self.extraction_status.setText("Failed — "+m));worker.cancelled.connect(lambda:self.extraction_status.setText("Cancelled"));worker.finished.connect(thread.quit);worker.finished.connect(worker.deleteLater);thread.finished.connect(thread.deleteLater);thread.finished.connect(self._finished);self.thread=thread;self.worker=worker;self.cancel.setEnabled(True);thread.start()
 def _cancel(self):
  if self.worker:self.worker.cancel()
 def _finished(self):self.thread=None;self.worker=None;self.cancel.setEnabled(False);self._refresh_candidates()
 def _refresh_candidates(self):
  if not hasattr(self,"candidates"):return
  rows=self.extractor.candidates();self.candidates.blockSignals(True);self.candidates.setRowCount(len(rows))
  for r,c in enumerate(rows):
   dup="Likely" if self.extractor.duplicate_candidates(c.candidate_id) else ""
   for col,v in enumerate((c.status,c.event.get("event_date",""),c.event.get("event_type",""),c.event.get("title",""),c.event.get("provider_facility",""),dup)):i=QTableWidgetItem(str(v));i.setData(Qt.ItemDataRole.UserRole,c.candidate_id);self.candidates.setItem(r,col,i)
  self.candidates.blockSignals(False)
  self.candidate_state.setText(f"{len(rows)} candidate(s) awaiting or completing review." if rows else "No extracted candidates. Select OCR-ready evidence or a document; pending/no-text sources may yield no events.")
 def _candidate_edited(self,item):
  if item.column() in {1,2,3,4}:self.extractor.update_candidate(str(item.data(Qt.ItemDataRole.UserRole)),**{("event_date","event_type","title","provider_facility")[item.column()-1]:item.text()})
 def _load_candidate_editor(self):
  r=self.candidates.currentRow()
  if r>=0:self.candidate_editor.setPlainText(json.dumps(self.extractor.get_candidate(str(self.candidates.item(r,0).data(Qt.ItemDataRole.UserRole))).event,indent=2))
 def _save_candidate_editor(self):
  r=self.candidates.currentRow()
  if r<0:return
  try:self.extractor.update_candidate(str(self.candidates.item(r,0).data(Qt.ItemDataRole.UserRole)),**json.loads(self.candidate_editor.toPlainText()));self._refresh_candidates()
  except Exception as exc:QMessageBox.warning(self,"Candidate edits",str(exc))
 def _candidate_action(self,action):
  r=self.candidates.currentRow()
  if r>=0:getattr(self.extractor,action)(str(self.candidates.item(r,0).data(Qt.ItemDataRole.UserRole)));self._refresh_candidates()
 def _merge(self):
  rows=self.candidates.selectionModel().selectedRows()
  if len(rows)!=2:QMessageBox.information(self,"Merge candidates","Select exactly two candidates; the first is merged into the second.");return
  self.extractor.merge(str(self.candidates.item(rows[0].row(),0).data(Qt.ItemDataRole.UserRole)),str(self.candidates.item(rows[1].row(),0).data(Qt.ItemDataRole.UserRole)));self._refresh_candidates()
 def _save_candidates(self):self.extractor.save_accepted();self.refresh();self.tabs.setCurrentIndex(0)
