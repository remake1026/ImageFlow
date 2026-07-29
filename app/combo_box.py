"""应用内统一的自绘下拉框。"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QTimer, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QAbstractScrollArea, QComboBox, QStyle, QStyleOptionComboBox


POPUP_LIST_STYLE = """
QAbstractItemView {
    color: #F2F2F2;
    background: #1B1C1E;
    border: 1px solid rgba(255,255,255,0.16);
    border-radius: 8px;
    outline: none;
    padding: 4px;
}
QAbstractItemView::item {
    min-height: 32px;
    padding: 0 10px;
    color: #E6E7E9;
    background: transparent;
    border: none;
    border-radius: 5px;
}
QAbstractItemView::item:hover {
    color: #FFFFFF;
    background: rgba(245,166,35,0.16);
}
QAbstractItemView::item:selected {
    color: #181818;
    background: #F5A623;
}
QScrollBar:vertical {
    width: 10px;
    margin: 6px 3px 6px 0;
    background: transparent;
}
QScrollBar::handle:vertical {
    min-height: 28px;
    background: #55585D;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover { background: #F5A623; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


class StyledComboBox(QComboBox):
    """固定 28px 箭头栏及分割线，不受平台原生箭头样式影响。"""

    CONTROL_STRIP_WIDTH = 28
    MAX_POPUP_HEIGHT = 320

    def __init__(self, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.setProperty("unifiedCombo", True)
        self.setMaxVisibleItems(9)
        popup = self.view()
        popup.setObjectName("comboPopupList")
        popup.setStyleSheet(POPUP_LIST_STYLE)
        popup.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        popup.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        # 仅由 Qt 绘制框体和文字，箭头与分割线完全由本控件负责。
        option.subControls = QStyle.SubControl.SC_ComboBoxFrame | QStyle.SubControl.SC_ComboBoxEditField
        painter = QPainter(self)
        self.style().drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option, painter, self)
        self.style().drawControl(QStyle.ControlElement.CE_ComboBoxLabel, option, painter, self)
        if self.width() <= self.CONTROL_STRIP_WIDTH:
            painter.end()
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        separator_x = self.width() - self.CONTROL_STRIP_WIDTH
        painter.setPen(QPen(QColor(255, 255, 255, 34), 1))
        painter.drawLine(separator_x, 5, separator_x, self.height() - 6)
        center_x = separator_x + self.CONTROL_STRIP_WIDTH // 2
        center_y = self.height() // 2 + 1
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#C9CACB"))
        painter.drawPolygon([
            QPoint(center_x - 5, center_y - 3),
            QPoint(center_x + 5, center_y - 3),
            QPoint(center_x, center_y + 3),
        ])
        painter.end()

    def showPopup(self) -> None:  # type: ignore[no-untyped-def]
        super().showPopup()
        # Qt 创建完 popup 容器后再调整，避免平台样式把列表盖到输入框上。
        QTimer.singleShot(0, self._position_popup)

    def event(self, event) -> bool:  # type: ignore[no-untyped-def]
        if (
            event.type() == QEvent.Type.Wheel
            and self.property("ignoreWheelSelection")
            and not self.view().window().isVisible()
        ):
            self.wheelEvent(event)
            return True
        return super().event(event)

    def wheelEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        """可选择让父级滚动区接管关闭状态下的滚轮事件。"""
        if self.property("ignoreWheelSelection") and not self.view().isVisible():
            # 不在关闭的组合框上切换当前项；将滚轮明确交给最近的外层滚动区。
            parent = self.parentWidget()
            while parent is not None:
                if isinstance(parent, QAbstractScrollArea):
                    scrollbar = parent.verticalScrollBar()
                    pixel_delta = event.pixelDelta().y()
                    angle_delta = event.angleDelta().y()
                    if pixel_delta:
                        scrollbar.setValue(scrollbar.value() - pixel_delta)
                    elif angle_delta:
                        steps = angle_delta / 120
                        scrollbar.setValue(scrollbar.value() - round(steps * scrollbar.singleStep() * 3))
                    event.accept()
                    return
                parent = parent.parentWidget()
            event.ignore()
            return
        super().wheelEvent(event)

    def _position_popup(self) -> None:
        popup = self.view().window()
        if not popup.isVisible():
            return
        row_height = max(34, self.view().sizeHintForRow(0))
        desired_height = min(self.MAX_POPUP_HEIGHT, row_height * min(self.count(), self.maxVisibleItems()) + 10)
        combo_top = self.mapToGlobal(QPoint(0, 0))
        combo_bottom = self.mapToGlobal(QPoint(0, self.height()))
        screen = QGuiApplication.screenAt(self.mapToGlobal(self.rect().center())) or self.screen()
        if screen is None:
            return
        area = screen.availableGeometry()
        below_space = max(0, area.bottom() - combo_bottom.y() + 1)
        above_space = max(0, combo_top.y() - area.top())
        open_below = below_space >= desired_height or below_space >= above_space
        available_height = below_space if open_below else above_space
        height = min(desired_height, available_height)
        if height <= 0:
            return
        top = combo_bottom if open_below else QPoint(combo_top.x(), combo_top.y() - height)
        popup.setFixedSize(self.width(), height)
        popup.move(top)


class EditablePopupComboBox(StyledComboBox):
    """可编辑下拉框；弹窗固定贴在输入框外侧，且始终与其等宽。"""

    def __init__(self, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.setEditable(True)
        self.lineEdit().setStyleSheet(
            "background: transparent; border: none; padding: 0 8px; color: #F2F2F2;"
        )
