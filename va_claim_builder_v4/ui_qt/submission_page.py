from __future__ import annotations
from PySide6.QtCore import Qt,QThread,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox,QComboBox,QFileDialog,QHBoxLayout,QInputDialog,QLabel,QLineEdit,QListWidget,QListWidgetItem,QMessageBox,QProgressBar,QPushButton,QSplitter,QTableWidget,QTableWidgetItem,QTabWidget,QTextEdit,QVBoxLayout,QWidget
from core.claims import ClaimManager
from core.dbq import DBQManager
from core.documents import DocumentManager
from core.evidence import EvidenceManager
from core.nexus import NexusLetterManager
from core.optimizer import OptimizerManager
from core.rating_strategy import RatingStrategyManager
from core.submission import PACKAGE_TYPES,SubmissionManager
from core.timeline import TimelineManager
from workers import SubmissionGenerationWorker
class SubmissionPage(QWidget):
 def __init__(self,project,parent=None):
  super().__init__(parent);self.project=project;self.manager=SubmissionManager(project);self.claims=ClaimManager(project);self.documents=DocumentManager(project);self.evidence=EvidenceManager(project);self.timeline=TimelineManager(project);self.nexus=NexusLetterManager(project);self.dbq=DBQManager(project);self.rating=RatingStrategyManager(project);self.optimizer=OptimizerManager(project);self.current=None;self.thread=None;self.worker=None;self.output_path=""
  heading=QLabel("Final Submission Builder");heading.setStyleSheet("font-size:22px;font-weight:600;");notice=QLabel("Local package assembly preserves original sources. Package type and organization are not legal advice and do not guarantee VA approval.");notice.setWordWrap(True)
  self.search=QLineEdit();self.search.setPlaceholderText("Search packages…");self.type_filter=QComboBox();self.type_filter.addItem("All package types","");[self.type_filter.addItem(x.replace("_"," ").title(),x) for x in PACKAGE_TYPES];self.status_filter=QComboBox();self.status_filter.addItem("All statuses","");[self.status_filter.addItem(x.title(),x) for x in ("draft","validated","generating","completed","failed","cancelled","incomplete")];refresh=QPushButton("Refresh");refresh.clicked.connect(self.refresh);self.search.textChanged.connect(self.refresh);self.type_filter.currentIndexChanged.connect(self.refresh);self.status_filter.currentIndexChanged.connect(self.refresh);fr=QHBoxLayout();[fr.addWidget(x) for x in (self.search,self.type_filter,self.status_filter,refresh)]
  self.packages=QTableWidget(0,5);self.packages.setHorizontalHeaderLabels(["Package","Type","Status","Version","Updated"]);self.packages.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows);self.packages.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);self.packages.itemSelectionChanged.connect(self._load)
  self.name=QLineEdit();self.package_type=QComboBox();[self.package_type.addItem(x.replace("_"," ").title(),x) for x in PACKAGE_TYPES];self.notes=QTextEdit();self.claim_select=QListWidget();self.source_lists={};source_tabs=QTabWidget()
  for key,title in (("document","Documents"),("evidence","Evidence"),("timeline","Timeline"),("nexus","Nexus Letters"),("dbq","DBQ Packets"),("rating_strategy","Rating Reports"),("optimizer","Optimizer Reports"),("claimant_statement","Claimant Statements"),("witness_statement","Witness Statements")):w=QListWidget();self.source_lists[key]=w;source_tabs.addTab(w,title)
  new=QPushButton("Create Package");new.clicked.connect(self.clear);save=QPushButton("Save Package Configuration");save.clicked.connect(self.save);duplicate=QPushButton("Duplicate Package");duplicate.clicked.connect(self.duplicate);delete=QPushButton("Delete Package");delete.clicked.connect(self.delete);pr=QHBoxLayout();[pr.addWidget(x) for x in (new,save,duplicate,delete)];pr.addStretch()
  edit=QWidget();el=QVBoxLayout(edit);el.addLayout(pr);el.addWidget(QLabel("Package name"));el.addWidget(self.name);el.addWidget(self.package_type);el.addWidget(QLabel("User notes"));el.addWidget(self.notes);el.addWidget(QLabel("Included claims"));el.addWidget(self.claim_select);el.addWidget(source_tabs)
  self.sections=QTableWidget(0,4);self.sections.setHorizontalHeaderLabels(["Enabled","Order","Section","Key"]);self.sections.itemChanged.connect(self._section_toggle);upsec=QPushButton("Move Section Up");upsec.clicked.connect(lambda:self._move_section(-1));downsec=QPushButton("Move Section Down");downsec.clicked.connect(lambda:self._move_section(1));rename=QPushButton("Rename Section");rename.clicked.connect(self._rename_section);sr=QHBoxLayout();sr.addWidget(upsec);sr.addWidget(downsec);sr.addWidget(rename);self.exhibits=QTableWidget(0,5);self.exhibits.setHorizontalHeaderLabels(["Exhibit","Title","Type","Section","Order"]);upex=QPushButton("Move Exhibit Up");upex.clicked.connect(lambda:self._move_exhibit(-1));downex=QPushButton("Move Exhibit Down");downex.clicked.connect(lambda:self._move_exhibit(1));renameex=QPushButton("Rename Exhibit");renameex.clicked.connect(self._rename_exhibit);er=QHBoxLayout();er.addWidget(upex);er.addWidget(downex);er.addWidget(renameex);config=QWidget();cl=QVBoxLayout(config);cl.addWidget(QLabel("Configurable sections"));cl.addWidget(self.sections);cl.addLayout(sr);cl.addWidget(QLabel("Stable exhibits"));cl.addWidget(self.exhibits);cl.addLayout(er)
  self.validation=QTextEdit();self.validation.setReadOnly(True);validate=QPushButton("Validate Package");validate.clicked.connect(self._validate);self.allow_incomplete=QCheckBox("Allow explicitly incomplete draft export");generate=QPushButton("Generate Package");generate.clicked.connect(self._generate);self.cancel=QPushButton("Cancel Generation");self.cancel.clicked.connect(self._cancel);self.cancel.setEnabled(False);openfolder=QPushButton("Open Output Folder");openfolder.clicked.connect(self._open);self.progress=QProgressBar();self.state=QLabel("Select or create a package.");vr=QHBoxLayout();[vr.addWidget(x) for x in (validate,self.allow_incomplete,generate,self.cancel,openfolder,self.progress)];self.exports=QTableWidget(0,5);self.exports.setHorizontalHeaderLabels(["Created","Version","Status","Formats","Output"]);generate_tab=QWidget();gl=QVBoxLayout(generate_tab);gl.addLayout(vr);gl.addWidget(self.state);gl.addWidget(self.validation);gl.addWidget(QLabel("Export history"));gl.addWidget(self.exports)
  detail=QTabWidget();detail.addTab(edit,"Package & Sources");detail.addTab(config,"Sections & Exhibits");detail.addTab(generate_tab,"Validation & Generation");split=QSplitter();split.addWidget(self.packages);split.addWidget(detail);split.setStretchFactor(1,3);root=QVBoxLayout(self);root.addWidget(heading);root.addWidget(notice);root.addLayout(fr);root.addWidget(split);self._options();self.refresh()
 def _check_item(self,w,label,key):i=QListWidgetItem(label);i.setData(Qt.ItemDataRole.UserRole,key);i.setFlags(i.flags()|Qt.ItemFlag.ItemIsUserCheckable);i.setCheckState(Qt.CheckState.Unchecked);w.addItem(i)
 def _options(self):
  for w in [self.claim_select,*self.source_lists.values()]:w.clear()
  for c in self.claims.list_claims():self._check_item(self.claim_select,c.condition_name,c.claim_id)
  docs=self.documents.list_documents()
  for d in docs:
   self._check_item(self.source_lists["document"],d.original_name,d.document_id);self._check_item(self.source_lists["claimant_statement"],d.original_name,d.document_id);self._check_item(self.source_lists["witness_statement"],d.original_name,d.document_id)
  for e in self.evidence.list():self._check_item(self.source_lists["evidence"],e.title,e.evidence_id)
  for t in self.timeline.list():self._check_item(self.source_lists["timeline"],f"{t.event_date} — {t.title}",t.event_id)
  for c in self.claims.list_claims():
   for n in self.nexus.list(claim_id=c.claim_id):self._check_item(self.source_lists["nexus"],n.title,n.letter_id)
   for d in self.dbq.list(claim_id=c.claim_id):self._check_item(self.source_lists["dbq"],d.title,d.dbq_id)
   for r in self.rating.history(c.claim_id):self._check_item(self.source_lists["rating_strategy"],f"{c.condition_name} — {r.analysis_timestamp}",r.strategy_id)
   for o in self.optimizer.history(c.claim_id):self._check_item(self.source_lists["optimizer"],f"{c.condition_name} — {o.assessment_timestamp}",o.assessment_id)
 def refresh(self):
  rows=self.manager.list(package_type=self.type_filter.currentData() or None,status=self.status_filter.currentData() or None,search=self.search.text());self.packages.setRowCount(len(rows))
  for r,p in enumerate(rows):
   for c,v in enumerate((p.name,p.package_type.replace("_"," "),p.status,str(p.package_version),p.updated_at)):i=QTableWidgetItem(v);i.setData(Qt.ItemDataRole.UserRole,p.package_id);self.packages.setItem(r,c,i)
  for r in range(self.packages.rowCount()):
   if self.packages.item(r,0).data(Qt.ItemDataRole.UserRole)==self.current:self.packages.selectRow(r);break
 def clear(self):self.current=None;self.name.clear();self.notes.clear();self.package_type.setCurrentIndex(0);self.packages.clearSelection();self._set_checks((),())
 def _checked(self,w):return [str(w.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(w.count()) if w.item(i).checkState()==Qt.CheckState.Checked]
 def _set_checks(self,claims,sources):
  for i in range(self.claim_select.count()):self.claim_select.item(i).setCheckState(Qt.CheckState.Checked if self.claim_select.item(i).data(Qt.ItemDataRole.UserRole) in claims else Qt.CheckState.Unchecked)
  selected={(s.source_type,s.source_id) for s in sources}
  for typ,w in self.source_lists.items():
   for i in range(w.count()):w.item(i).setCheckState(Qt.CheckState.Checked if (typ,w.item(i).data(Qt.ItemDataRole.UserRole)) in selected else Qt.CheckState.Unchecked)
 def save(self):
  try:
   if self.current:p=self.manager.update(self.current,name=self.name.text(),package_type=self.package_type.currentData(),user_notes=self.notes.toPlainText())
   else:p=self.manager.create(self.name.text(),self.package_type.currentData(),claim_ids=self._checked(self.claim_select),user_notes=self.notes.toPlainText());self.current=p.package_id
   chosen_claims=set(self._checked(self.claim_select));[self.manager.link_claim(p.package_id,x) for x in chosen_claims-set(p.claim_ids)];[self.manager.unlink_claim(p.package_id,x) for x in set(p.claim_ids)-chosen_claims]
   current={(s.source_type,s.source_id) for s in p.sources};chosen={(typ,x) for typ,w in self.source_lists.items() for x in self._checked(w)}
   for typ,x in chosen-current:self.manager.add_source(p.package_id,typ,x,display_name=self._label(typ,x),section_key=self._section(typ))
   for typ,x in current-chosen:self.manager.remove_source(p.package_id,typ,x)
   self.refresh();self._panels()
  except Exception as e:QMessageBox.warning(self,"Submission Builder",str(e))
 def _load(self):
  r=self.packages.currentRow()
  if r<0:return
  p=self.manager.get(str(self.packages.item(r,0).data(Qt.ItemDataRole.UserRole)));self.current=p.package_id;self.name.setText(p.name);self.package_type.setCurrentIndex(self.package_type.findData(p.package_type));self.notes.setPlainText(p.user_notes);self._set_checks(p.claim_ids,p.sources);self._panels()
 def _panels(self):
  if not self.current:return
  p=self.manager.get(self.current);self.sections.blockSignals(True);self.sections.setRowCount(len(p.sections))
  for r,s in enumerate(p.sections):
   enabled=QTableWidgetItem("Yes" if s["enabled"] else "No");enabled.setCheckState(Qt.CheckState.Checked if s["enabled"] else Qt.CheckState.Unchecked);enabled.setData(Qt.ItemDataRole.UserRole,s["section_key"]);self.sections.setItem(r,0,enabled);self.sections.setItem(r,1,QTableWidgetItem(str(s["sort_order"])));self.sections.setItem(r,2,QTableWidgetItem(s["title"]));self.sections.setItem(r,3,QTableWidgetItem(s["section_key"]))
  self.sections.blockSignals(False);self.exhibits.setRowCount(len(p.sources))
  for r,s in enumerate(p.sources):
   for c,v in enumerate((s.exhibit_id,s.display_name or self._label(s.source_type,s.source_id),s.source_type,s.section_key,str(s.sort_order))):i=QTableWidgetItem(v);i.setData(Qt.ItemDataRole.UserRole,(s.source_type,s.source_id));self.exhibits.setItem(r,c,i)
  exports=self.manager.exports(self.current);self.exports.setRowCount(len(exports))
  for r,e in enumerate(exports):
   for c,v in enumerate((e["created_at"],str(e["version_number"]),e["status"],", ".join(__import__("json").loads(e["formats_json"])),e["output_path"])):self.exports.setItem(r,c,QTableWidgetItem(v))
  if exports and exports[0]["output_path"]:self.output_path=exports[0]["output_path"]
 def _move_section(self,d):
  r=self.sections.currentRow()
  if r>=0:self.manager.move_section(self.current,self.sections.item(r,3).text(),d);self._panels()
 def _section_toggle(self,item):
  if self.current and item.column()==0:self.manager.configure_section(self.current,str(item.data(Qt.ItemDataRole.UserRole)),enabled=item.checkState()==Qt.CheckState.Checked)
 def _rename_section(self):
  r=self.sections.currentRow()
  if r<0:return
  text,ok=QInputDialog.getText(self,"Rename Section","Section title",text=self.sections.item(r,2).text())
  if ok:self.manager.configure_section(self.current,self.sections.item(r,3).text(),title=text,enabled=self.sections.item(r,0).checkState()==Qt.CheckState.Checked);self._panels()
 def _move_exhibit(self,d):
  r=self.exhibits.currentRow()
  if r>=0:t,i=self.exhibits.item(r,0).data(Qt.ItemDataRole.UserRole);self.manager.move_source(self.current,t,i,d);self._panels()
 def _rename_exhibit(self):
  r=self.exhibits.currentRow()
  if r<0:return
  text,ok=QInputDialog.getText(self,"Rename Exhibit","Exhibit title",text=self.exhibits.item(r,1).text())
  if ok:t,i=self.exhibits.item(r,0).data(Qt.ItemDataRole.UserRole);self.manager.configure_source(self.current,t,i,display_name=text);self._panels()
 def _validate(self):
  if not self.current:return
  issues=self.manager.validate(self.current,self.project.root/"reports"/"submissions");self.validation.setPlainText("\n".join(f"{i.level.upper()}: {i.message}" for i in issues));self.state.setText("Validation complete: "+", ".join(f"{x} {sum(i.level==x for i in issues)}" for x in ("blocking","warning","info")))
 def _generate(self):
  if not self.current:return
  issues=self.manager.validate(self.current,self.project.root/"reports"/"submissions");blocking=any(i.level=="blocking" for i in issues)
  if blocking and not self.allow_incomplete.isChecked():QMessageBox.warning(self,"Submission Builder","Resolve blocking errors or explicitly allow an incomplete draft export.");self._validate();return
  self.thread=QThread(self);self.worker=SubmissionGenerationWorker(self.project,self.current,allow_incomplete=self.allow_incomplete.isChecked());self.worker.moveToThread(self.thread);self.thread.started.connect(self.worker.run);self.worker.progress.connect(lambda p,m:(self.progress.setValue(p),self.state.setText(m)));self.worker.completed.connect(lambda path:(setattr(self,"output_path",path),self.state.setText("Completed — "+path)));self.worker.failed.connect(lambda m:self.state.setText("Failed — "+m));self.worker.cancelled.connect(lambda:self.state.setText("Cancelled; temporary outputs cleaned."));self.worker.finished.connect(self.thread.quit);self.thread.finished.connect(self._finished);self.cancel.setEnabled(True);self.thread.start()
 def _cancel(self):
  if self.worker:self.worker.cancel()
 def _finished(self):self.thread=None;self.worker=None;self.cancel.setEnabled(False);self.refresh();self._panels()
 def _open(self):
  if self.output_path:QDesktopServices.openUrl(QUrl.fromLocalFile(self.output_path))
 def duplicate(self):
  if self.current:self.current=self.manager.duplicate(self.current).package_id;self.refresh()
 def delete(self):
  if self.current and QMessageBox.question(self,"Delete Package","Delete this package configuration and export history?")==QMessageBox.StandardButton.Yes:self.manager.delete(self.current);self.clear();self.refresh()
 def _label(self,t,x):
  try:return {"document":lambda:self.documents.get(x).original_name,"claimant_statement":lambda:self.documents.get(x).original_name,"witness_statement":lambda:self.documents.get(x).original_name,"evidence":lambda:self.evidence.get(x).title,"timeline":lambda:self.timeline.get(x).title,"nexus":lambda:self.nexus.get(x).title,"dbq":lambda:self.dbq.get(x).title,"rating_strategy":lambda:"Rating Strategy Report","optimizer":lambda:"Claim Optimizer Report"}[t]()
  except Exception:return "Unavailable source"
 @staticmethod
 def _section(t):return {"document":"medical_records","evidence":"evidence_index","timeline":"medical_chronology","nexus":"nexus_letters","dbq":"dbq_materials","rating_strategy":"rating_strategy","optimizer":"optimizer_summary","claimant_statement":"claimant_statements","witness_statement":"witness_statements"}.get(t,"appendices")
