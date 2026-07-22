from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt,QThread
from PySide6.QtWidgets import (QComboBox,QFileDialog,QFormLayout,QHBoxLayout,QLabel,QLineEdit,QListWidget,QListWidgetItem,QMessageBox,QProgressBar,QPushButton,QScrollArea,QSplitter,QTableWidget,QTableWidgetItem,QTabWidget,QTextEdit,QVBoxLayout,QWidget)
from core.claims import ClaimManager
from core.dbq import DBQManager,DBQPreparationService,DBQ_STATUSES,get_template,list_templates
from core.documents import DocumentManager
from core.evidence import EvidenceManager
from core.projects import AppPaths
from core.settings import SettingsManager
from core.timeline import TimelineManager
from workers import DBQPreparationWorker
class DBQPage(QWidget):
 def __init__(self,project,parent=None):
  super().__init__(parent);self.project=project;self.manager=DBQManager(project);self.claims=ClaimManager(project);self.evidence=EvidenceManager(project);self.timeline=TimelineManager(project);self.documents=DocumentManager(project);self.current_id=None;self.field_widgets={};self.thread=None;self.worker=None
  heading=QLabel("DBQ Assistant");heading.setStyleSheet("font-size:22px;font-weight:600;");notice=QLabel("Preparation and review aid only — not an official VA DBQ and not a replacement for an examination or provider-completed DBQ. AI suggestions require verification.");notice.setWordWrap(True)
  self.search=QLineEdit();self.search.setPlaceholderText("Search DBQs…");self.claim_filter=QComboBox();self.template_filter=QComboBox();self.template_filter.addItem("All DBQ types","");self.status_filter=QComboBox();self.status_filter.addItem("All statuses","");[self.status_filter.addItem(x.title(),x) for x in DBQ_STATUSES];refresh=QPushButton("Refresh");refresh.clicked.connect(self.refresh)
  self.search.textChanged.connect(self.refresh);self.claim_filter.currentIndexChanged.connect(self.refresh);self.template_filter.currentIndexChanged.connect(self.refresh);self.status_filter.currentIndexChanged.connect(self.refresh);filters=QHBoxLayout();[filters.addWidget(x) for x in (self.search,self.claim_filter,self.template_filter,self.status_filter,refresh)]
  self.table=QTableWidget(0,6);self.table.setHorizontalHeaderLabels(["Title","Claim","DBQ Type","Status","Revision","Updated"]);self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows);self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);self.table.itemSelectionChanged.connect(self._load)
  self.title=QLineEdit();self.claim=QComboBox();self.template=QComboBox();[self.template.addItem(t.name,t.template_id) for t in list_templates()];self.template.currentIndexChanged.connect(self._build_fields);self.status=QComboBox();self.status.addItems(DBQ_STATUSES);self.condition=QLineEdit();self.exam_date=QLineEdit();self.examiner=QLineEdit();self.credentials=QLineEdit();self.specialty=QLineEdit();self.form=QFormLayout();self.form_widget=QWidget();self.form_widget.setLayout(self.form);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(self.form_widget);self._build_fields()
  meta=QFormLayout();[meta.addRow(label,w) for label,w in (("Title",self.title),("Claim",self.claim),("DBQ template",self.template),("Status",self.status),("Condition",self.condition),("Exam date",self.exam_date),("Examiner / provider",self.examiner),("Credentials",self.credentials),("Specialty",self.specialty))];edit=QWidget();el=QVBoxLayout(edit);el.addLayout(meta);el.addWidget(scroll)
  split=QSplitter();split.addWidget(self.table);split.addWidget(edit);split.setStretchFactor(0,2);split.setStretchFactor(1,3);new=QPushButton("Create DBQ Work Product");new.clicked.connect(self.clear);save=QPushButton("Save Manual Edits");save.clicked.connect(self.save);duplicate=QPushButton("Duplicate");duplicate.clicked.connect(self.duplicate);delete=QPushButton("Delete");delete.clicked.connect(self.delete);export=QPushButton("Export DOCX…");export.clicked.connect(self.export);row=QHBoxLayout();[row.addWidget(x) for x in (new,save,duplicate,delete,export)];row.addStretch();editor=QWidget();ed=QVBoxLayout(editor);ed.addLayout(row);ed.addLayout(filters);ed.addWidget(split)
  self.evidence_sources=QListWidget();self.timeline_sources=QListWidget();self.document_sources=QListWidget();sources=QSplitter();[sources.addWidget(w) for w in (self.evidence_sources,self.timeline_sources,self.document_sources)];self.generate=QPushButton("Generate AI Suggestions");self.generate.clicked.connect(self._generate);self.cancel=QPushButton("Cancel Generation");self.cancel.clicked.connect(self._cancel);self.cancel.setEnabled(False);self.progress=QProgressBar();self.generation_state=QLabel("Save a DBQ and select sources before generation.");gr=QHBoxLayout();[gr.addWidget(x) for x in (self.generate,self.cancel,self.progress)]
  self.suggestions=QTableWidget(0,7);self.suggestions.setHorizontalHeaderLabels(["Field","Class","Suggestion","Confidence","Sources","Missing / Conflict","Decision"]);self.suggestions.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows);accept=QPushButton("Accept Suggestion");accept.clicked.connect(lambda:self._decide(True));reject=QPushButton("Reject Suggestion");reject.clicked.connect(lambda:self._decide(False));sr=QHBoxLayout();sr.addWidget(accept);sr.addWidget(reject);sr.addStretch();source_tab=QWidget();sl=QVBoxLayout(source_tab);sl.addWidget(QLabel("Evidence | Confirmed Timeline Events | Documents (checked sources are traceable)"));sl.addWidget(sources);sl.addLayout(gr);sl.addWidget(self.generation_state);sl.addWidget(self.suggestions);sl.addLayout(sr)
  self.completeness=QTextEdit();self.completeness.setReadOnly(True);self.revisions=QTableWidget(0,3);self.revisions.setHorizontalHeaderLabels(["Revision","Created","Source"]);self.revisions.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection);self.revisions.itemSelectionChanged.connect(self._compare);self.compare=QTextEdit();self.compare.setReadOnly(True);review=QWidget();rl=QVBoxLayout(review);rl.addWidget(QLabel("Completeness is informational and does not guarantee a rating or favorable decision."));rl.addWidget(self.completeness);rl.addWidget(self.revisions);rl.addWidget(self.compare)
  self.tabs=QTabWidget();self.tabs.addTab(editor,"DBQ Editor");self.tabs.addTab(source_tab,"Sources & Suggestions");self.tabs.addTab(review,"Completeness & Revisions");lay=QVBoxLayout(self);lay.addWidget(heading);lay.addWidget(notice);lay.addWidget(self.tabs);self._options();self.refresh()
 def _options(self):
  self.claim.clear();self.claim_filter.clear();self.claim_filter.addItem("All claims","")
  for c in self.claims.list_claims():self.claim.addItem(c.condition_name,c.claim_id);self.claim_filter.addItem(c.condition_name,c.claim_id)
  for t in list_templates():self.template_filter.addItem(t.name,t.template_id)
  self._fill(self.evidence_sources,[(x.evidence_id,x.title) for x in self.evidence.list()]);self._fill(self.timeline_sources,[(x.event_id,f"{x.event_date} — {x.title}") for x in self.timeline.list()]);self._fill(self.document_sources,[(x.document_id,x.original_name) for x in self.documents.list_documents()])
 def _fill(self,w,rows):
  w.clear()
  for key,label in rows:i=QListWidgetItem(label);i.setData(Qt.ItemDataRole.UserRole,key);i.setFlags(i.flags()|Qt.ItemFlag.ItemIsUserCheckable);i.setCheckState(Qt.CheckState.Unchecked);w.addItem(i)
 def _build_fields(self):
  while self.form.rowCount():self.form.removeRow(0)
  self.field_widgets={};template=get_template(self.template.currentData() or "general_medical")
  for f in template.fields:w=QTextEdit();w.setMaximumHeight(75);w.setReadOnly(f.kind=="examiner");w.setPlaceholderText(("EXAMINER ONLY — " if f.kind=="examiner" else f.kind.replace("_"," ").title()+" — ")+f.guidance);self.form.addRow(f"{f.section}: {f.label}"+(" *" if f.required else ""),w);self.field_widgets[f.key]=w
 def refresh(self):
  selected=self.current_id;rows=self.manager.list(claim_id=self.claim_filter.currentData() or None,template_id=self.template_filter.currentData() or None,status=self.status_filter.currentData() or None,search=self.search.text());names={c.claim_id:c.condition_name for c in self.claims.list_claims()};self.table.setRowCount(len(rows))
  for r,x in enumerate(rows):
   for c,v in enumerate((x.title,names.get(x.claim_id,""),get_template(x.template_id).name,x.status,str(x.revision_number),x.updated_at)):i=QTableWidgetItem(v);i.setData(Qt.ItemDataRole.UserRole,x.dbq_id);self.table.setItem(r,c,i)
  for r in range(self.table.rowCount()):
   if self.table.item(r,0).data(Qt.ItemDataRole.UserRole)==selected:self.table.selectRow(r);break
 def clear(self):self.current_id=None;self.title.clear();self.status.setCurrentText("draft");[w.clear() for w in self.field_widgets.values()];self.table.clearSelection();self._checks((),(),())
 def _checked(self,w):return [str(w.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(w.count()) if w.item(i).checkState()==Qt.CheckState.Checked]
 def save(self):
  if not self.claim.currentData():QMessageBox.warning(self,"DBQ Assistant","Create or select a claim first.");return
  fields={k:w.toPlainText() for k,w in self.field_widgets.items()};meta=dict(template_id=self.template.currentData(),status=self.status.currentText(),title=self.title.text(),condition=self.condition.text(),exam_date=self.exam_date.text(),examiner_name=self.examiner.text(),examiner_credentials=self.credentials.text(),specialty=self.specialty.text())
  try:
   x=self.manager.update(self.current_id,**meta,**fields) if self.current_id else self.manager.create(str(self.claim.currentData()),fields=fields,evidence_ids=self._checked(self.evidence_sources),timeline_event_ids=self._checked(self.timeline_sources),document_ids=self._checked(self.document_sources),**meta);self.current_id=x.dbq_id
   for w,link,unlink,old in ((self.evidence_sources,self.manager.link_evidence,self.manager.unlink_evidence,x.evidence_ids),(self.timeline_sources,self.manager.link_timeline_event,self.manager.unlink_timeline_event,x.timeline_event_ids),(self.document_sources,self.manager.link_document,self.manager.unlink_document,x.document_ids)):
    chosen=set(self._checked(w));[link(x.dbq_id,v) for v in chosen-set(old)];[unlink(x.dbq_id,v) for v in set(old)-chosen]
   self.refresh();self._panels()
  except Exception as e:QMessageBox.warning(self,"DBQ Assistant",str(e))
 def _load(self):
  r=self.table.currentRow()
  if r<0:return
  x=self.manager.get(str(self.table.item(r,0).data(Qt.ItemDataRole.UserRole)));self.current_id=x.dbq_id;self.title.setText(x.title);self.claim.setCurrentIndex(max(0,self.claim.findData(x.claim_id)));self.template.setCurrentIndex(max(0,self.template.findData(x.template_id)));self.status.setCurrentText(x.status);self.condition.setText(x.condition);self.exam_date.setText(x.exam_date);self.examiner.setText(x.examiner_name);self.credentials.setText(x.examiner_credentials);self.specialty.setText(x.specialty)
  for k,w in self.field_widgets.items():w.setPlainText(x.fields.get(k,""))
  self._checks(x.evidence_ids,x.timeline_event_ids,x.document_ids);self._panels()
 def _checks(self,e,t,d):
  for w,vals in ((self.evidence_sources,e),(self.timeline_sources,t),(self.document_sources,d)):
   for i in range(w.count()):w.item(i).setCheckState(Qt.CheckState.Checked if w.item(i).data(Qt.ItemDataRole.UserRole) in vals else Qt.CheckState.Unchecked)
 def duplicate(self):
  if self.current_id:self.current_id=self.manager.duplicate(self.current_id).dbq_id;self.refresh()
 def delete(self):
  if self.current_id and QMessageBox.question(self,"Delete DBQ","Delete this DBQ and its revisions?")==QMessageBox.StandardButton.Yes:self.manager.delete(self.current_id);self.clear();self.refresh()
 def export(self):
  if not self.current_id:return
  path,_=QFileDialog.getSaveFileName(self,"Export DBQ Preparation Packet","dbq-preparation.docx","Word Document (*.docx)")
  if path:self.manager.export_docx(self.current_id,Path(path))
 def _generate(self):
  if not self.current_id:QMessageBox.information(self,"DBQ preparation","Save the DBQ and source selections first.");return
  if self.thread:return
  paths=AppPaths(root=self.project.root.parent.parent).ensure();factory=lambda p:DBQPreparationService(p,settings_manager=SettingsManager(paths));self.thread=QThread(self);self.worker=DBQPreparationWorker(self.project,self.current_id,service_factory=factory);self.worker.moveToThread(self.thread);self.thread.started.connect(self.worker.run);self.worker.progress.connect(lambda p,m:(self.progress.setValue(p),self.generation_state.setText(m)));self.worker.completed.connect(lambda _:(self.generation_state.setText("Suggestions ready — review and accept or reject each field."),self._reload()));self.worker.failed.connect(lambda m:self.generation_state.setText("Failed — "+m));self.worker.cancelled.connect(lambda:self.generation_state.setText("Cancelled"));self.worker.finished.connect(self.thread.quit);self.thread.finished.connect(self._finished);self.cancel.setEnabled(True);self.thread.start()
 def _cancel(self):
  if self.worker:self.worker.cancel()
 def _finished(self):self.thread=None;self.worker=None;self.cancel.setEnabled(False);self._panels();self.refresh()
 def _reload(self):self._load();self.refresh()
 def _panels(self):
  if not self.current_id:return
  x=self.manager.get(self.current_id);self.suggestions.setRowCount(len(x.suggestions))
  for r,s in enumerate(x.suggestions):
   gap="; ".join(s.get("missing_information",[])+([s.get("conflicting_information","")] if s.get("conflicting_information") else []))
   for c,v in enumerate((s["field_key"],s["information_class"],s["proposed_value"] or ("EXAMINER ONLY" if s["requires_examiner"] else ""),s["confidence"],", ".join(s["source_labels"]),gap,s["decision"])):i=QTableWidgetItem(v);i.setData(Qt.ItemDataRole.UserRole,s["field_key"]);self.suggestions.setItem(r,c,i)
  g=self.manager.completeness(self.current_id);self.completeness.setPlainText(f"Score: {g['score']}%\nCompleted: {', '.join(g['completed']) or 'None'}\nIncomplete: {', '.join(g['incomplete']) or 'None'}\nConflicts: {', '.join(g['conflicting']) or 'None'}\nExaminer-only: {', '.join(g['examiner_only']) or 'None'}\nSupporting sources: {g['supporting_evidence_count']}\nEvidence gaps: {', '.join(g['evidence_gaps']) or 'None'}\n\n{g['disclaimer']}");versions=self.manager.revisions(self.current_id);self.revisions.setRowCount(len(versions))
  for r,v in enumerate(versions):
   for c,val in enumerate((str(v.revision_number),v.created_at,"AI" if v.ai_metadata else "Manual")):i=QTableWidgetItem(val);i.setData(Qt.ItemDataRole.UserRole,v.revision_id);self.revisions.setItem(r,c,i)
 def _decide(self,accept):
  r=self.suggestions.currentRow()
  if r>=0:self.manager.decide_suggestion(self.current_id,str(self.suggestions.item(r,0).data(Qt.ItemDataRole.UserRole)),accept);self._load()
 def _compare(self):
  if not self.current_id:return
  ids={self.revisions.item(i.row(),0).data(Qt.ItemDataRole.UserRole) for i in self.revisions.selectionModel().selectedRows()};vs=[v for v in self.manager.revisions(self.current_id) if v.revision_id in ids];self.compare.setPlainText("\n\n".join(f"REVISION {v.revision_number}\n"+"\n".join(f"{k}: {val}" for k,val in v.fields.items()) for v in vs))
