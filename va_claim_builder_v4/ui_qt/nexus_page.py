from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt,QThread
from PySide6.QtWidgets import (QComboBox,QFileDialog,QFormLayout,QHBoxLayout,QLabel,QLineEdit,QListWidget,QListWidgetItem,QMessageBox,QProgressBar,QPushButton,QSplitter,QTableWidget,QTableWidgetItem,QTabWidget,QTextEdit,QVBoxLayout,QWidget)
from core.claims import ClaimManager
from core.documents import DocumentManager
from core.evidence import EvidenceManager
from core.nexus import NEXUS_STATUSES,NEXUS_THEORIES,NexusGenerationService,NexusLetterManager
from core.projects import AppPaths
from core.settings import SettingsManager
from core.timeline import TimelineManager
from workers import NexusGenerationWorker

SECTIONS=(("records_reviewed","Records Reviewed"),("current_diagnosis","Current Diagnosis"),("service_history","Service History"),("medical_history","Medical History"),("in_service_event","In-Service Event / Exposure / Aggravation"),("nexus_opinion","Nexus Opinion (advisory draft)"),("medical_rationale","Medical Rationale"),("favorable_evidence","Favorable Evidence"),("unfavorable_evidence","Unfavorable Evidence"),("probability_language","Provider-reviewed Probability Language"),("limitations","Limitations / Caveats"),("signature_block","Signature Block"),("user_facts","User-entered Facts"),("missing_facts","Missing / Unsupported Facts"))
class NexusPage(QWidget):
 def __init__(self,project,parent=None):
  super().__init__(parent);self.project=project;self.manager=NexusLetterManager(project);self.claims=ClaimManager(project);self.evidence=EvidenceManager(project);self.timeline=TimelineManager(project);self.documents=DocumentManager(project);self.current_id=None;self.thread=None;self.worker=None
  heading=QLabel("Nexus Letters");heading.setStyleSheet("font-size:22px;font-weight:600;");notice=QLabel("AI output is advisory—not a medical or legal determination—and is never a signed opinion. Every draft requires review and signature by a qualified medical professional.");notice.setWordWrap(True)
  self.search=QLineEdit();self.search.setPlaceholderText("Search letters…");self.claim_filter=QComboBox();self.status_filter=QComboBox();self.status_filter.addItem("All statuses","");[self.status_filter.addItem(x.title(),x) for x in NEXUS_STATUSES];self.theory_filter=QComboBox();self.theory_filter.addItem("All theories","");[self.theory_filter.addItem(self._label(x),x) for x in NEXUS_THEORIES]
  for w in (self.search,):w.textChanged.connect(self.refresh)
  self.claim_filter.currentIndexChanged.connect(self.refresh);self.status_filter.currentIndexChanged.connect(self.refresh);self.theory_filter.currentIndexChanged.connect(self.refresh)
  refresh=QPushButton("Refresh");refresh.clicked.connect(self.refresh);filters=QHBoxLayout();[filters.addWidget(x) for x in (self.search,self.claim_filter,self.status_filter,self.theory_filter,refresh)]
  self.table=QTableWidget(0,6);self.table.setHorizontalHeaderLabels(["Title","Claim","Status","Primary Theory","Version","Updated"]);self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows);self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);self.table.itemSelectionChanged.connect(self._load);self.table.horizontalHeader().setStretchLastSection(True)
  self.title=QLineEdit();self.claim=QComboBox();self.status=QComboBox();self.status.addItems(NEXUS_STATUSES);self.letter_type=QLineEdit("physician_review");self.primary=QComboBox();[self.primary.addItem(self._label(x),x) for x in NEXUS_THEORIES];self.theories=QListWidget();self.author=QLineEdit();self.credentials=QLineEdit();self.specialty=QLineEdit();self.sections={k:QTextEdit() for k,_ in SECTIONS};self.sections["probability_language"].setPlaceholderText("Provider must explicitly choose: at least as likely as not, more likely than not, or less likely than not")
  form=QFormLayout()
  for label,w in (("Title",self.title),("Claim",self.claim),("Letter type",self.letter_type),("Status",self.status),("Primary theory",self.primary),("Additional theories",self.theories),("Provider / author",self.author),("Credentials",self.credentials),("Specialty",self.specialty)):form.addRow(label,w)
  for key,label in SECTIONS:form.addRow(label,self.sections[key])
  editor=QWidget();editor.setLayout(form);split=QSplitter();split.addWidget(self.table);split.addWidget(editor);split.setStretchFactor(0,2);split.setStretchFactor(1,3)
  new=QPushButton("Create Draft");new.clicked.connect(self.clear);save=QPushButton("Save Manual Edits");save.clicked.connect(self.save);duplicate=QPushButton("Duplicate Draft");duplicate.clicked.connect(self.duplicate);delete=QPushButton("Delete");delete.clicked.connect(self.delete);export=QPushButton("Export DOCX…");export.clicked.connect(self.export)
  actions=QHBoxLayout();[actions.addWidget(x) for x in (new,save,duplicate,delete,export)];actions.addStretch()
  draft=QWidget();dl=QVBoxLayout(draft);dl.addLayout(actions);dl.addLayout(filters);dl.addWidget(split)
  self.evidence_sources=QListWidget();self.timeline_sources=QListWidget();self.document_sources=QListWidget();sources=QSplitter();[sources.addWidget(w) for w in (self.evidence_sources,self.timeline_sources,self.document_sources)]
  self.generate=QPushButton("Generate AI-assisted Draft");self.generate.clicked.connect(self._generate);self.cancel=QPushButton("Cancel Generation");self.cancel.clicked.connect(self._cancel);self.cancel.setEnabled(False);self.progress=QProgressBar();self.generation_state=QLabel("Select sources and save the draft before generation.")
  self.lit_title=QLineEdit();self.lit_title.setPlaceholderText("Literature title");self.lit_author=QLineEdit();self.lit_author.setPlaceholderText("Author");self.lit_publication=QLineEdit();self.lit_publication.setPlaceholderText("Publication");self.lit_year=QLineEdit();self.lit_year.setPlaceholderText("Year");self.lit_url=QLineEdit();self.lit_url.setPlaceholderText("DOI or URL");self.lit_note=QLineEdit();self.lit_note.setPlaceholderText("Relevance note");self.lit_verified=QComboBox();self.lit_verified.addItem("Verified manual reference",True);self.lit_verified.addItem("Unverified candidate",False);add_lit=QPushButton("Add Literature Reference");add_lit.clicked.connect(self._add_literature);self.literature=QListWidget()
  genrow=QHBoxLayout();genrow.addWidget(self.generate);genrow.addWidget(self.cancel);genrow.addWidget(self.progress)
  litrow=QHBoxLayout();[litrow.addWidget(x) for x in (self.lit_title,self.lit_author,self.lit_publication,self.lit_year,self.lit_url,self.lit_note,self.lit_verified,add_lit)]
  source_tab=QWidget();sl=QVBoxLayout(source_tab);sl.addWidget(QLabel("Supporting Evidence | Confirmed Timeline Events | Documents (check sources; links are traceable)"));sl.addWidget(sources);sl.addWidget(QLabel("Literature references (AI may suggest search terms, but references must be manually entered and verified)"));sl.addLayout(litrow);sl.addWidget(self.literature);sl.addLayout(genrow);sl.addWidget(self.generation_state)
  self.revisions=QTableWidget(0,3);self.revisions.setHorizontalHeaderLabels(["Version","Created","Source"]);self.revisions.itemSelectionChanged.connect(self._compare);self.compare=QTextEdit();self.compare.setReadOnly(True);rev=QWidget();rl=QVBoxLayout(rev);rl.addWidget(QLabel("Select one or two revisions to inspect and compare."));rl.addWidget(self.revisions);rl.addWidget(self.compare)
  self.tabs=QTabWidget();self.tabs.addTab(draft,"Draft Editor");self.tabs.addTab(source_tab,"Sources & AI Generation");self.tabs.addTab(rev,"Revision History")
  lay=QVBoxLayout(self);lay.addWidget(heading);lay.addWidget(notice);lay.addWidget(self.tabs);self._options();self.refresh()
 def _options(self):
  self.claim.clear();self.claim_filter.clear();self.claim_filter.addItem("All claims","")
  for c in self.claims.list_claims():self.claim.addItem(c.condition_name,c.claim_id);self.claim_filter.addItem(c.condition_name,c.claim_id)
  self.theories.clear()
  for x in NEXUS_THEORIES:i=QListWidgetItem(self._label(x));i.setData(Qt.ItemDataRole.UserRole,x);i.setFlags(i.flags()|Qt.ItemFlag.ItemIsUserCheckable);i.setCheckState(Qt.CheckState.Unchecked);self.theories.addItem(i)
  self._fill_checks(self.evidence_sources,[(e.evidence_id,e.title) for e in self.evidence.list()]);self._fill_checks(self.timeline_sources,[(e.event_id,f"{e.event_date} — {e.title}") for e in self.timeline.list()]);self._fill_checks(self.document_sources,[(d.document_id,d.original_name) for d in self.documents.list_documents()])
 def _fill_checks(self,w,rows):
  w.clear()
  for key,label in rows:i=QListWidgetItem(label);i.setData(Qt.ItemDataRole.UserRole,key);i.setFlags(i.flags()|Qt.ItemFlag.ItemIsUserCheckable);i.setCheckState(Qt.CheckState.Unchecked);w.addItem(i)
 def refresh(self):
  selected=self.current_id;letters=self.manager.list(claim_id=self.claim_filter.currentData() or None,status=self.status_filter.currentData() or None,theory=self.theory_filter.currentData() or None,search=self.search.text());self.table.setRowCount(len(letters))
  names={c.claim_id:c.condition_name for c in self.claims.list_claims()}
  for r,x in enumerate(letters):
   for col,v in enumerate((x.title,names.get(x.claim_id,""),x.status,self._label(x.primary_theory),str(x.current_version),x.updated_at)):i=QTableWidgetItem(v);i.setData(Qt.ItemDataRole.UserRole,x.letter_id);self.table.setItem(r,col,i)
  for r in range(self.table.rowCount()):
   if self.table.item(r,0).data(Qt.ItemDataRole.UserRole)==selected:self.table.selectRow(r);break
 def clear(self):self.current_id=None;self.title.clear();self.status.setCurrentText("draft");[w.clear() for w in self.sections.values()];self.table.clearSelection();self._check_sources((),(),())
 def _checked(self,w):return [str(w.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(w.count()) if w.item(i).checkState()==Qt.CheckState.Checked]
 def _theories(self):return self._checked(self.theories)
 def save(self):
  if not self.claim.currentData():QMessageBox.warning(self,"Nexus letter","Create or select a claim first.");return
  content={k:(w.toPlainText().splitlines() if k=="missing_facts" else w.toPlainText()) for k,w in self.sections.items()};meta=dict(title=self.title.text(),letter_type=self.letter_type.text(),status=self.status.currentText(),primary_theory=self.primary.currentData(),theories=self._theories(),author_name=self.author.text(),author_credentials=self.credentials.text(),specialty=self.specialty.text())
  try:
   x=self.manager.update(self.current_id,**meta,**content) if self.current_id else self.manager.create(str(self.claim.currentData()),content=content,evidence_ids=self._checked(self.evidence_sources),timeline_event_ids=self._checked(self.timeline_sources),document_ids=self._checked(self.document_sources),**meta);self.current_id=x.letter_id
   for getter,link,unlink,old in ((self.evidence_sources,self.manager.link_evidence,self.manager.unlink_evidence,x.evidence_ids),(self.timeline_sources,self.manager.link_timeline_event,self.manager.unlink_timeline_event,x.timeline_event_ids),(self.document_sources,self.manager.link_document,self.manager.unlink_document,x.document_ids)):
    chosen=set(self._checked(getter));[link(x.letter_id,v) for v in chosen-set(old)];[unlink(x.letter_id,v) for v in set(old)-chosen]
   self.refresh();self._load_versions()
  except Exception as e:QMessageBox.warning(self,"Nexus letter",str(e))
 def _load(self):
  r=self.table.currentRow()
  if r<0:return
  x=self.manager.get(str(self.table.item(r,0).data(Qt.ItemDataRole.UserRole)));self.current_id=x.letter_id;self.title.setText(x.title);self.claim.setCurrentIndex(max(0,self.claim.findData(x.claim_id)));self.status.setCurrentText(x.status);self.letter_type.setText(x.letter_type);self.primary.setCurrentIndex(self.primary.findData(x.primary_theory));self.author.setText(x.author_name);self.credentials.setText(x.author_credentials);self.specialty.setText(x.specialty)
  for k,w in self.sections.items():v=x.content.get(k,[] if k=="missing_facts" else "");w.setPlainText("\n".join(v) if isinstance(v,list) else str(v))
  for i in range(self.theories.count()):self.theories.item(i).setCheckState(Qt.CheckState.Checked if self.theories.item(i).data(Qt.ItemDataRole.UserRole) in x.theories else Qt.CheckState.Unchecked)
  self._check_sources(x.evidence_ids,x.timeline_event_ids,x.document_ids);self._load_versions();self._load_literature()
 def _check_sources(self,e,t,d):
  for w,values in ((self.evidence_sources,e),(self.timeline_sources,t),(self.document_sources,d)):
   for i in range(w.count()):w.item(i).setCheckState(Qt.CheckState.Checked if w.item(i).data(Qt.ItemDataRole.UserRole) in values else Qt.CheckState.Unchecked)
 def duplicate(self):
  if self.current_id:self.current_id=self.manager.duplicate(self.current_id).letter_id;self.refresh()
 def delete(self):
  if self.current_id and QMessageBox.question(self,"Delete nexus letter","Delete this draft and its revision history?")==QMessageBox.StandardButton.Yes:self.manager.delete(self.current_id);self.clear();self.refresh()
 def export(self):
  if not self.current_id:return
  path,_=QFileDialog.getSaveFileName(self,"Export Nexus Letter","nexus-letter.docx","Word Document (*.docx)")
  if path:self.manager.export_docx(self.current_id,Path(path))
 def _generate(self):
  if not self.current_id:QMessageBox.information(self,"Nexus generation","Save the draft and source selections first.");return
  if self.thread:return
  paths=AppPaths(root=self.project.root.parent.parent).ensure();service=lambda p:NexusGenerationService(p,settings_manager=SettingsManager(paths));self.thread=QThread(self);self.worker=NexusGenerationWorker(self.project,self.current_id,service_factory=service);self.worker.moveToThread(self.thread);self.thread.started.connect(self.worker.run);self.worker.progress.connect(lambda p,m:(self.progress.setValue(p),self.generation_state.setText(m)));self.worker.completed.connect(lambda _:(self._load_current(),self.generation_state.setText("Completed — review all generated text and choose probability language explicitly.")));self.worker.failed.connect(lambda m:self.generation_state.setText("Failed — "+m));self.worker.cancelled.connect(lambda:self.generation_state.setText("Cancelled"));self.worker.finished.connect(self.thread.quit);self.thread.finished.connect(self._finished);self.cancel.setEnabled(True);self.thread.start()
 def _cancel(self):
  if self.worker:self.worker.cancel()
 def _finished(self):self.thread=None;self.worker=None;self.cancel.setEnabled(False);self._load_versions();self.refresh()
 def _load_current(self):
  self.refresh();self._load()
 def _load_versions(self):
  versions=self.manager.versions(self.current_id) if self.current_id else [];self.revisions.setRowCount(len(versions))
  for r,v in enumerate(versions):
   for c,val in enumerate((str(v.version_number),v.created_at,"AI" if v.ai_metadata else "Manual")):i=QTableWidgetItem(val);i.setData(Qt.ItemDataRole.UserRole,v.version_id);self.revisions.setItem(r,c,i)
 def _add_literature(self):
  if not self.current_id or not self.lit_title.text().strip():QMessageBox.information(self,"Literature","Save a draft and enter a literature title first.");return
  self.manager.add_literature(self.current_id,self.lit_title.text(),author=self.lit_author.text(),publication=self.lit_publication.text(),year=self.lit_year.text(),doi_url=self.lit_url.text(),relevance_note=self.lit_note.text(),verified=bool(self.lit_verified.currentData()));self.lit_title.clear();self._load_literature()
 def _load_literature(self):
  self.literature.clear()
  if self.current_id:
   for r in self.manager.literature(self.current_id):self.literature.addItem(f"{'Verified' if r['verified'] else 'UNVERIFIED'} — {r['title']} — {r['author']} ({r['year']}) — {r['doi_url']} — {r['relevance_note']}")
 def _compare(self):
  if not self.current_id:return
  selected={self.revisions.item(i.row(),0).data(Qt.ItemDataRole.UserRole) for i in self.revisions.selectionModel().selectedRows()};versions=[v for v in self.manager.versions(self.current_id) if v.version_id in selected];self.compare.setPlainText("\n\n".join(f"VERSION {v.version_number} ({'AI' if v.ai_metadata else 'Manual'})\n"+"\n".join(f"{k}: {v.content.get(k,'')}" for k,_ in SECTIONS) for v in versions))
 @staticmethod
 def _label(x):return x.replace("_"," ").title()
