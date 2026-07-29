"""水印九宫格圆点定位控件。"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QPushButton, QWidget


class AnchorSelector(QWidget):
    """以 3×3 可点击圆点选择水印锚点，替代不直观的下拉框。"""

    anchor_changed = Signal(str)
    _positions = (
        ("左上", 0, 0), ("上中", 0, 1), ("右上", 0, 2),
        ("左中", 1, 0), ("居中", 1, 1), ("右中", 1, 2),
        ("左下", 2, 0), ("下中", 2, 1), ("右下", 2, 2),
    )

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("anchorSelector")
        self._buttons: dict[str, QPushButton] = {}
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(4)
        layout.setVerticalSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        for anchor, row, column in self._positions:
            button = QPushButton()
            button.setCheckable(True)
            button.setObjectName("anchorButton")
            button.setFixedSize(16, 16)
            button.setToolTip(anchor)
            button.setAccessibleName(f"水印定位：{anchor}")
            button.clicked.connect(lambda checked=False, value=anchor: self._select_from_user(value))
            layout.addWidget(button, row, column)
            self._buttons[anchor] = button
        # QSS 边框会占用额外像素；预留 62px 可完整容纳三列圆点，避免最右侧被裁切。
        self.setFixedSize(62, 62)
        self.set_anchor("右下")

    def anchor(self) -> str:
        return next((name for name, button in self._buttons.items() if button.isChecked()), "右下")

    def _select_from_user(self, anchor: str) -> None:
        """用户点击时始终立即发信号，即使重复点选当前定位。"""
        self.set_anchor(anchor, emit=True, force_emit=True)

    def set_anchor(self, anchor: str, emit: bool = False, force_emit: bool = False) -> None:
        if anchor not in self._buttons:
            anchor = "右下"
        changed = self.anchor() != anchor
        for name, button in self._buttons.items():
            button.blockSignals(True)
            button.setChecked(name == anchor)
            button.blockSignals(False)
        if emit and (changed or force_emit):
            self.anchor_changed.emit(anchor)
