"""应用内统一的自绘勾选框。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QCheckBox, QStyle, QStyleOptionButton


class GuideCheckBox(QCheckBox):
    """在主题橙色勾选框上稳定绘制白色对勾，不依赖系统主题图标。"""

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().paintEvent(event)
        if not self.isChecked():
            return
        option = QStyleOptionButton()
        self.initStyleOption(option)
        indicator = self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, self)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#FFFFFF"), 2.1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawLine(indicator.left() + 5, indicator.center().y(), indicator.left() + 9, indicator.bottom() - 5)
        painter.drawLine(indicator.left() + 9, indicator.bottom() - 5, indicator.right() - 4, indicator.top() + 5)
        painter.end()
