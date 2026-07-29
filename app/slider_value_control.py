"""滑块与可双击精确编辑数值的组合控件。"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QSlider, QStyle, QStyleOptionSlider, QWidget


class _InlineValueEdit(QLineEdit):
    double_clicked = Signal()

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() == Qt.MouseButton.LeftButton:
            super().mouseDoubleClickEvent(event)
            self.setReadOnly(False)
            self.setFocus()
            self.selectAll()
            self.double_clicked.emit()
            return
        super().mouseDoubleClickEvent(event)


class ResettableSlider(QSlider):
    """仅当双击滑块圆点时触发恢复默认，避免误触轨道。"""

    reset_requested = Signal()

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        handle = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            option,
            QStyle.SubControl.SC_SliderHandle,
            self,
        )
        if event.button() == Qt.MouseButton.LeftButton and handle.contains(event.position().toPoint()):
            self.reset_requested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class SliderValueControl(QWidget):
    """滑块负责快速调整，右侧数值双击后可进行精确输入。"""

    value_changed = Signal(float)

    def __init__(
        self,
        minimum: float,
        maximum: float,
        value: float,
        decimals: int = 1,
        suffix: str = "",
        title: str = "修改参数",
        parent: Optional[QWidget] = None,
        default_value: Optional[float] = None,
        reset_on_handle_double_click: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("sliderValueControl")
        self._minimum = minimum
        self._maximum = maximum
        self._decimals = decimals
        self._factor = 10 ** decimals
        self._suffix = suffix
        self._title = title
        self._default_value = value if default_value is None else default_value
        self._reset_on_handle_double_click = reset_on_handle_double_click

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.slider = ResettableSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(round(minimum * self._factor), round(maximum * self._factor))
        self.slider.setSingleStep(1)
        self.slider.valueChanged.connect(self._on_slider_changed)
        if self._reset_on_handle_double_click:
            self.slider.reset_requested.connect(self.reset_to_default)
        self.value_label = _InlineValueEdit()
        self.value_label.setObjectName("inlineValueEdit")
        self.value_label.setFixedWidth(76)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value_label.setCursor(Qt.CursorShape.IBeamCursor)
        self.value_label.setReadOnly(True)
        self.value_label.setToolTip("双击可精确输入数值")
        self.value_label.editingFinished.connect(self._commit_inline_value)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.value_label)
        self.setValue(value)

    def value(self) -> float:
        return self.slider.value() / self._factor

    def setValue(self, value: float) -> None:
        raw_value = max(self._minimum, min(self._maximum, value))
        self.slider.blockSignals(True)
        self.slider.setValue(round(raw_value * self._factor))
        self.slider.blockSignals(False)
        self._update_label()

    def reset_to_default(self) -> None:
        """双击滑块圆点时恢复构造时定义的默认值。"""
        self.slider.setValue(round(self._default_value * self._factor))

    def _on_slider_changed(self, _raw_value: int) -> None:
        self._update_label()
        self.value_changed.emit(self.value())

    def _update_label(self) -> None:
        self.value_label.setText(f"{self.value():.{self._decimals}f}{self._suffix}")

    def _commit_inline_value(self) -> None:
        """结束编辑时解析当前输入；按 Enter 或失焦都会回写到同一数值框。"""
        text = self.value_label.text().strip().removesuffix(self._suffix).strip()
        try:
            value = float(text)
        except ValueError:
            value = self.value()
        self.value_label.setReadOnly(True)
        self.slider.setValue(round(max(self._minimum, min(self._maximum, value)) * self._factor))
        self._update_label()
