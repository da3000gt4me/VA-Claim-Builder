from __future__ import annotations
from PySide6.QtCore import Qt,QThread
from PySide6.QtWidgets import QComboBox,QHBoxLayout,QLabel,QLineEdit,QListWidget,QMessageBox,QProgressBar,QPushButton,QSplitter,QTableWidget,QTableWidgetItem,QTabWidget,QTextEdit,QVBoxLayout,QWidget
from core.claims import ClaimManager
from core.projects import AppPaths
from core.rating_strategy import RatingStrategyEngine,RatingStrategyManager,STRATEGY_STATUSES
from core.settings import SettingsManager
from workers import RatingStrategyWorker
class RatingStrategyPage(QWidget):
 def __init__(self,project,parent=None):
  super().__init__(parent);self.project=project;self.claims=ClaimManager(project);self.manager=RatingStrategyManager(project);paths=AppPaths(root=project.root.parent.parent).ensure();self.engine_factory=lambda p:RatingStrategyEngine(p,settings_manager=SettingsManager(paths));self.current_strategy=None;self.thread=None;self.worker=None
  heading=QLabel("VA Rating Strategy");heading.setStyleSheet("font-size:22px;font-weight:600;");warning=QLabel("Advisory claim-development analysis only. Estimated ratings and relationship opportunities are not guaranteed decisions; verify current law, diagnostic codes, and medical evidence.");warning.setWordWrap(True)
  self.search=QLineEdit();self.search.setPlaceholderText("Search analyses…");self.claim_filter=QComboBox();self.status_filter=QComboBox();self.status_filter.addItem("All statuses","");[self.status_filter.addItem(x.title(),x) for x in STRATEGY_STATUSES];self.confidence_filter=QComboBox();self.confidence_filter.addItem("All confidence","");[self.confidence_filter.addItem(x.title(),x) for x in ("low","medium","high")];refresh=QPushButton("Refresh");refresh.clicked.connect(self.refresh)
  self.search.textChanged.connect(self.refresh);self.claim_filter.currentIndexChanged.connect(self.refresh);self.status_filter.currentIndexChanged.connect(self.refresh);self.confidence_filter.currentIndexChanged.connect(self.refresh);fr=QHBoxLayout();[fr.addWidget(x) for x in (self.search,self.claim_filter,self.status_filter,self.confidence_filter,refresh)]
  self.claim_list=QListWidget();self.claim_list.currentItemChanged.connect(lambda *_:self._select_claim());analyze=QPushButton("Analyze Selected Claim");analyze.clicked.connect(self._analyze_selected);analyze_all=QPushButton("Analyze Filtered Claims");analyze_all.clicked.connect(self._analyze_filtered);self.cancel=QPushButton("Cancel Analysis");self.cancel.clicked.connect(self._cancel);self.cancel.setEnabled(False);self.progress=QProgressBar();self.state=QLabel("Select a claim to review strategy history.");ar=QHBoxLayout();[ar.addWidget(x) for x in (analyze,analyze_all,self.cancel,self.progress)]
  self.history=QTableWidget(0,5);self.history.setHorizontalHeaderLabels(["Analyzed","Status","Estimated rating","Confidence","Diagnostic code(s)"]);self.history.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows);self.history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);self.history.itemSelectionChanged.connect(self._load)
  self.summary=QLabel("No strategy selected.");self.summary.setWordWrap(True);self.sections={k:QTextEdit() for k in ("strengths","weaknesses","missing_evidence","contradictory_evidence","recommended_actions","supporting_evidence","secondary_opportunities","aggravation_opportunities","presumptive_opportunities","generated_reasoning")}
  tabs=QTabWidget()
  for key,title in (("strengths","Strengths"),("weaknesses","Weaknesses"),("missing_evidence","Evidence Gaps"),("contradictory_evidence","Contradictions"),("recommended_actions","Recommended Actions"),("supporting_evidence","Supporting Evidence"),("secondary_opportunities","Secondary Opportunities"),("aggravation_opportunities","Aggravation Opportunities"),("presumptive_opportunities","Presumptive Opportunities"),("generated_reasoning","Reasoning")):self.sections[key].setReadOnly(True);tabs.addTab(self.sections[key],title)
  left=QWidget();ll=QVBoxLayout(left);ll.addWidget(QLabel("Claims"));ll.addWidget(self.claim_list);ll.addLayout(ar);ll.addWidget(self.state);right=QWidget();rl=QVBoxLayout(right);rl.addWidget(QLabel("Analysis History"));rl.addWidget(self.history);rl.addWidget(self.summary);rl.addWidget(tabs);split=QSplitter();split.addWidget(left);split.addWidget(right);split.setStretchFactor(1,3);lay=QVBoxLayout(self);lay.addWidget(heading);lay.addWidget(warning);lay.addLayout(fr);lay.addWidget(split);self._options();self.refresh()
 def _options(self):
  self.claim_filter.clear();self.claim_filter.addItem("All claims","");self.claim_list.clear()
  for c in self.claims.list_claims():self.claim_filter.addItem(c.condition_name,c.claim_id);self.claim_list.addItem(c.condition_name);self.claim_list.item(self.claim_list.count()-1).setData(Qt.ItemDataRole.UserRole,c.claim_id)
 def _selected_claim(self):return str(self.claim_list.currentItem().data(Qt.ItemDataRole.UserRole)) if self.claim_list.currentItem() else ""
 def _select_claim(self):
  cid=self._selected_claim();i=self.claim_filter.findData(cid)
  if i>=0:self.claim_filter.setCurrentIndex(i)
  self.refresh()
 def refresh(self):
  rows=self.manager.list(claim_id=self.claim_filter.currentData() or None,status=self.status_filter.currentData() or None,confidence=self.confidence_filter.currentData() or None,search=self.search.text());selected=self.current_strategy;self.history.setRowCount(len(rows))
  for r,x in enumerate(rows):
   for c,v in enumerate((x.analysis_timestamp,x.status,x.estimated_rating_range,x.confidence,", ".join(x.diagnostic_codes))):i=QTableWidgetItem(v);i.setData(Qt.ItemDataRole.UserRole,x.strategy_id);self.history.setItem(r,c,i)
  for r in range(self.history.rowCount()):
   if self.history.item(r,0).data(Qt.ItemDataRole.UserRole)==selected:self.history.selectRow(r);break
  if not rows:self.state.setText("No rating-strategy history for the current filters.")
 def _load(self):
  r=self.history.currentRow()
  if r<0:return
  x=self.manager.get(str(self.history.item(r,0).data(Qt.ItemDataRole.UserRole)));self.current_strategy=x.strategy_id;self.summary.setText(f"Estimated rating: {x.estimated_rating_range or 'Pending'} | Confidence: {x.confidence.title()} | Status: {x.status.title()} | Codes: {', '.join(x.diagnostic_codes) or 'Needs verified profile'}")
  for k,w in self.sections.items():v=getattr(x,k);w.setPlainText(v if isinstance(v,str) else "\n\n".join(f"• {i}" for i in v) or "None identified.")
 def _analyze_selected(self):
  cid=self._selected_claim() or self.claim_filter.currentData()
  if not cid:QMessageBox.information(self,"Rating Strategy","Select a claim first.");return
  self._start([str(cid)])
 def _analyze_filtered(self):
  cid=self.claim_filter.currentData();ids=[str(cid)] if cid else [c.claim_id for c in self.claims.list_claims()]
  if not ids:QMessageBox.information(self,"Rating Strategy","No claims are available.");return
  self._start(ids)
 def _start(self,ids):
  if self.thread:return
  self.thread=QThread(self);self.worker=RatingStrategyWorker(self.project,ids,engine_factory=self.engine_factory);self.worker.moveToThread(self.thread);self.thread.started.connect(self.worker.run);self.worker.progress.connect(lambda p,m:(self.progress.setValue(p),self.state.setText(m)));self.worker.strategy_updated.connect(lambda sid:(setattr(self,"current_strategy",sid),self.refresh()));self.worker.completed.connect(lambda d,f:self.state.setText(f"Completed {d}; failed {f}. Review estimates and gaps."));self.worker.failed.connect(lambda m:self.state.setText("Failed — "+m));self.worker.cancelled.connect(lambda:self.state.setText("Cancelled"));self.worker.finished.connect(self.thread.quit);self.thread.finished.connect(self._finished);self.cancel.setEnabled(True);self.thread.start()
 def _cancel(self):
  if self.worker:self.worker.cancel()
 def _finished(self):self.thread=None;self.worker=None;self.cancel.setEnabled(False);self.refresh()
