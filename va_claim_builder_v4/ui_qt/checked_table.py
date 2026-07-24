from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QHeaderView, QStyle, QStyleOptionButton


class CheckableHeader(QHeaderView):
    """Tri-state checkbox in the first header section for visible-row selection."""

    toggled = Signal(object)

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._state = Qt.CheckState.Unchecked
        self.setSectionsClickable(True)

    def checkState(self):
        return self._state

    def setCheckState(self, state):
        self._state = Qt.CheckState(state)
        self.viewport().update()

    def paintSection(self, painter: QPainter, rect: QRect, logical_index: int) -> None:
        super().paintSection(painter, rect, logical_index)
        if logical_index != 0:
            return
        option = QStyleOptionButton()
        option.rect = QRect(rect.left() + 6, rect.center().y() - 8, 16, 16)
        option.state = QStyle.StateFlag.State_Enabled
        if self._state == Qt.CheckState.Checked:
            option.state |= QStyle.StateFlag.State_On
        elif self._state == Qt.CheckState.PartiallyChecked:
            option.state |= QStyle.StateFlag.State_NoChange
        else:
            option.state |= QStyle.StateFlag.State_Off
        self.style().drawControl(QStyle.ControlElement.CE_CheckBox, option, painter, self)

    def mousePressEvent(self, event) -> None:
        if self.logicalIndexAt(event.position().toPoint()) == 0:
            state = Qt.CheckState.Unchecked if self._state == Qt.CheckState.Checked else Qt.CheckState.Checked
            self.setCheckState(state)
            self.toggled.emit(state)
            event.accept()
            return
        super().mousePressEvent(event)

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            self.setToolTip("Select or clear every visible row")
        return super().event(event)
