from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt,QThread
from PySide6.QtWidgets import QCheckBox,QComboBox,QFileDialog,QHBoxLayout,QInputDialog,QLabel,QLineEdit,QListWidget,QMessageBox,QProgressBar,QPushButton,QSplitter,QTableWidget,QTableWidgetItem,QTabWidget,QTextEdit,QVBoxLayout,QWidget
from core.claims import ClaimManager
from core.optimizer import ClaimOptimizerEngine,GAP_CATEGORIES,OptimizerManager
from core.projects import AppPaths
from core.settings import SettingsManager
from workers import OptimizerWorker
class OptimizerPage(QWidget):
 def __init__(self,project,parent=None):
  super().__init__(parent);self.project=project;self.claims=ClaimManager(project);self.manager=OptimizerManager(project);paths=AppPaths(root=project.root.parent.parent).ensure();self.engine_factory=lambda p:ClaimOptimizerEngine(p,settings_manager=SettingsManager(paths));self.current=None;self.thread=None;self.worker=None
  heading=QLabel("Claim Optimizer");heading.setStyleSheet("font-size:22px;font-weight:600;");warning=QLabel("Readiness scores and AI suggestions are advisory development aids. They do not guarantee VA approval or any disability percentage.");warning.setWordWrap(True)
  self.claims_list=QListWidget();self.claims_list.currentItemChanged.connect(lambda *_:self._claim_changed());self.history=QTableWidget(0,4);self.history.setHorizontalHeaderLabels(["Assessment","Status","Overall","Confidence"]);self.history.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows);self.history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);self.history.itemSelectionChanged.connect(self._load)
  analyze=QPushButton("Analyze Selected Claim");analyze.clicked.connect(self._analyze_selected);allb=QPushButton("Analyze All Claims");allb.clicked.connect(self._analyze_all);self.cancel=QPushButton("Cancel Analysis");self.cancel.clicked.connect(self._cancel);self.cancel.setEnabled(False);refresh=QPushButton("Refresh");refresh.clicked.connect(self.refresh);self.progress=QProgressBar();self.state=QLabel("Select a claim or run an analysis.");ar=QHBoxLayout();[ar.addWidget(x) for x in (analyze,allb,self.cancel,refresh,self.progress)]
  self.scores=QLabel("No completed assessment selected.");self.scores.setWordWrap(True);self.explanation=QTextEdit();self.explanation.setReadOnly(True);self.search=QLineEdit();self.search.setPlaceholderText("Search gaps…");self.priority=QComboBox();self.priority.addItem("All priorities",None);[self.priority.addItem(f"Priority {x}",x) for x in range(1,6)];self.category=QComboBox();self.category.addItem("All categories","");[self.category.addItem(x.replace("_"," ").title(),x) for x in GAP_CATEGORIES];self.status=QComboBox();self.status.addItem("All statuses","");[self.status.addItem(x.replace("_"," ").title(),x) for x in ("unresolved","resolved","not_applicable","rejected")];self.party=QLineEdit();self.party.setPlaceholderText("Responsible party");self.unresolved=QCheckBox("Unresolved only")
  for w in (self.search,self.party):w.textChanged.connect(self._tables)
  for w in (self.priority,self.category,self.status):w.currentIndexChanged.connect(self._tables)
  self.unresolved.stateChanged.connect(self._tables);fr=QHBoxLayout();[fr.addWidget(x) for x in (self.search,self.priority,self.category,self.status,self.party,self.unresolved)]
  self.gaps=QTableWidget(0,9);self.gaps.setHorizontalHeaderLabels(["Priority","Category","Severity","Description","Basis","Resolution","Party","Status","Origin"]);self.gaps.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows);self.gaps.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);self.actions=QTableWidget(0,7);self.actions.setHorizontalHeaderLabels(["Priority","Action","Expected value","Effort","Dependency","Status","Origin"])
  add=QPushButton("Add Manual Gap");add.clicked.connect(self._add);edit=QPushButton("Edit Gap");edit.clicked.connect(self._edit);resolve=QPushButton("Resolve Gap");resolve.clicked.connect(lambda:self._decision("resolve"));reopen=QPushButton("Reopen Gap");reopen.clicked.connect(lambda:self._decision("reopen"));na=QPushButton("Mark Not Applicable");na.clicked.connect(lambda:self._decision("na"));accept=QPushButton("Accept AI Suggestion");accept.clicked.connect(lambda:self._decision("accept"));reject=QPushButton("Reject AI Suggestion");reject.clicked.connect(lambda:self._decision("reject"));gr=QHBoxLayout();[gr.addWidget(x) for x in (add,edit,resolve,reopen,na,accept,reject)];gr.addStretch()
  complete_action=QPushButton("Mark Action Completed");complete_action.clicked.connect(self._complete_action);laydoc=QPushButton("Export Lay Statement DOCX…");laydoc.clicked.connect(self._lay);provider=QPushButton("Export Provider Request DOCX…");provider.clicked.connect(self._provider);er=QHBoxLayout();er.addWidget(complete_action);er.addWidget(laydoc);er.addWidget(provider);er.addStretch()
  gaps_tab=QWidget();gl=QVBoxLayout(gaps_tab);gl.addLayout(fr);gl.addWidget(self.gaps);gl.addLayout(gr);actions_tab=QWidget();al=QVBoxLayout(actions_tab);al.addWidget(self.actions);al.addLayout(er);score_tab=QWidget();sl=QVBoxLayout(score_tab);sl.addWidget(self.scores);sl.addWidget(self.explanation);tabs=QTabWidget();tabs.addTab(gaps_tab,"Gaps");tabs.addTab(actions_tab,"Prioritized Action Plan");tabs.addTab(score_tab,"Scoring & Traceability")
  left=QWidget();ll=QVBoxLayout(left);ll.addWidget(QLabel("Claims"));ll.addWidget(self.claims_list);ll.addLayout(ar);ll.addWidget(self.state);ll.addWidget(QLabel("Assessment History"));ll.addWidget(self.history);right=QWidget();rl=QVBoxLayout(right);rl.addWidget(tabs);split=QSplitter();split.addWidget(left);split.addWidget(right);split.setStretchFactor(1,3);root=QVBoxLayout(self);root.addWidget(heading);root.addWidget(warning);root.addWidget(split);self._options();self.refresh()
 def _options(self):
  self.claims_list.clear()
  for c in self.claims.list_claims():self.claims_list.addItem(c.condition_name);self.claims_list.item(self.claims_list.count()-1).setData(Qt.ItemDataRole.UserRole,c.claim_id)
 def _claim_id(self):return str(self.claims_list.currentItem().data(Qt.ItemDataRole.UserRole)) if self.claims_list.currentItem() else ""
 def _claim_changed(self):self.current=None;self.refresh()
 def refresh(self):
  rows=self.manager.history(self._claim_id()) if self._claim_id() else self.manager.list();self.history.setRowCount(len(rows))
  for r,x in enumerate(rows):
   for c,v in enumerate((x.assessment_timestamp,x.status,str(x.overall_score),x.confidence)):i=QTableWidgetItem(v);i.setData(Qt.ItemDataRole.UserRole,x.assessment_id);self.history.setItem(r,c,i)
  for r in range(self.history.rowCount()):
   if self.history.item(r,0).data(Qt.ItemDataRole.UserRole)==self.current:self.history.selectRow(r);break
  if not rows:self.state.setText("No optimizer assessment history. Analysis may be pending, failed, cancelled, or not yet run.")
 def _load(self):
  r=self.history.currentRow()
  if r<0:return
  self.current=str(self.history.item(r,0).data(Qt.ItemDataRole.UserRole));a=self.manager.get(self.current);self.scores.setText(f"Overall: {a.overall_score}% | Service connection: {a.service_connection_score}% | Rating/severity: {a.severity_rating_score}% | Evidence completeness: {a.evidence_quality_score}% | Evidence consistency: {a.evidence_consistency_score}% | Confidence: {a.confidence.title()}");self.explanation.setPlainText("\n".join(f"{k}: {v}" for k,v in a.score_explanation.items()));self._tables()
 def _tables(self):
  if not self.current:return
  rows=self.manager.gaps(self.current,priority=self.priority.currentData(),category=self.category.currentData(),status=self.status.currentData(),responsible_party=self.party.text(),unresolved_only=self.unresolved.isChecked(),search=self.search.text());self.gaps.setRowCount(len(rows))
  for r,g in enumerate(rows):
   for c,v in enumerate((str(g.priority),g.category.replace("_"," "),g.severity,g.description,"; ".join(g.evidence_basis),g.recommended_resolution,g.responsible_party,g.status,g.origin)):i=QTableWidgetItem(v);i.setData(Qt.ItemDataRole.UserRole,g.gap_id);self.gaps.setItem(r,c,i)
  acts=self.manager.actions(self.current);self.actions.setRowCount(len(acts))
  for r,a in enumerate(acts):
   for c,v in enumerate((str(a.priority),a.description,a.expected_value,a.effort_level,a.dependency,a.status,a.origin)):i=QTableWidgetItem(v);i.setData(Qt.ItemDataRole.UserRole,a.action_id);self.actions.setItem(r,c,i)
 def _gap(self):return str(self.gaps.item(self.gaps.currentRow(),0).data(Qt.ItemDataRole.UserRole)) if self.gaps.currentRow()>=0 else ""
 def _add(self):
  if not self.current:return
  text,ok=QInputDialog.getText(self,"Manual Gap","Gap description")
  if ok and text:self.manager.add_gap(self.current,"unsupported_factual_assertion",text,origin="manual",user_confirmation="confirmed");self._tables()
 def _edit(self):
  gid=self._gap()
  if not gid:return
  g=self.manager.get_gap(gid);text,ok=QInputDialog.getText(self,"Edit Gap","Description",text=g.description)
  if ok:self.manager.update_gap(gid,description=text);self._tables()
 def _decision(self,kind):
  gid=self._gap()
  if not gid:return
  if kind=="resolve":self.manager.resolve_gap(gid)
  elif kind=="reopen":self.manager.reopen_gap(gid)
  elif kind=="na":self.manager.not_applicable(gid)
  elif kind=="accept":self.manager.update_gap(gid,user_confirmation="confirmed")
  else:self.manager.reject_gap(gid)
  self._tables()
 def _lay(self):
  if not self.current:return
  path,_=QFileDialog.getSaveFileName(self,"Export Lay Statement","lay-statement-outline.docx","Word Document (*.docx)")
  if path:self.manager.export_lay_statement(self.current,Path(path))
 def _complete_action(self):
  r=self.actions.currentRow()
  if r>=0:self.manager.update_action(str(self.actions.item(r,0).data(Qt.ItemDataRole.UserRole)),status="completed",completion_notes="Completed by user");self._tables()
 def _provider(self):
  if not self.current:return
  path,_=QFileDialog.getSaveFileName(self,"Export Provider Request","provider-request.docx","Word Document (*.docx)")
  if path:self.manager.export_provider_request(self.current,Path(path))
 def _analyze_selected(self):
  if not self._claim_id():QMessageBox.information(self,"Claim Optimizer","Select a claim first.");return
  self._start([self._claim_id()])
 def _analyze_all(self):self._start([c.claim_id for c in self.claims.list_claims()])
 def _start(self,ids):
  if self.thread or not ids:return
  self.thread=QThread(self);self.worker=OptimizerWorker(self.project,ids,engine_factory=self.engine_factory);self.worker.moveToThread(self.thread);self.thread.started.connect(self.worker.run);self.worker.progress.connect(lambda p,m:(self.progress.setValue(p),self.state.setText(m)));self.worker.assessment_updated.connect(lambda aid:(setattr(self,"current",aid),self.refresh()));self.worker.completed.connect(lambda d,f:self.state.setText(f"Completed {d}; failed {f}. Review and confirm advisory gaps."));self.worker.failed.connect(lambda m:self.state.setText("Failed — "+m));self.worker.cancelled.connect(lambda:self.state.setText("Cancelled"));self.worker.finished.connect(self.thread.quit);self.thread.finished.connect(self._finished);self.cancel.setEnabled(True);self.thread.start()
 def _cancel(self):
  if self.worker:self.worker.cancel()
 def _finished(self):self.thread=None;self.worker=None;self.cancel.setEnabled(False);self.refresh()
