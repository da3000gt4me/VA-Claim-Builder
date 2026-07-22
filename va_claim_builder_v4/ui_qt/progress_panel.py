from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget


class ProgressPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.label = QLabel("Ready")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)

        row = QHBoxLayout()
        row.addWidget(self.progress, 1)
        row.addWidget(self.cancel_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)
        layout.addLayout(row)
        self.setVisible(False)

    def start(self, message: str) -> None:
        self.label.setText(message)
        self.progress.setValue(0)
        self.cancel_button.setEnabled(True)
        self.setVisible(True)

    def update_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(max(0, min(100, percent)))
        self.label.setText(message)

    def finish(self, message: str) -> None:
        self.progress.setValue(100)
        self.label.setText(message)
        self.cancel_button.setEnabled(False)

    def reset(self) -> None:
        self.progress.setValue(0)
        self.label.setText("Ready")
        self.cancel_button.setEnabled(False)
        self.setVisible(False)
