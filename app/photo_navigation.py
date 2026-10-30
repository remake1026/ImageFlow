"""主画布与水印编辑器共用的紧凑切图按钮。"""
import sys
from pathlib import Path

from app.qt.QtCore import QSize, Qt
from app.qt.QtGui import QIcon
from app.qt.QtWidgets import QHBoxLayout, QToolButton, QWidget


class PhotoNavigation(QWidget):
    def __init__(self, previous, following, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
        buttons = []
        for label, filename, handler in (
            ("上一张", "photo-previous.svg", previous),
            ("下一张", "photo-next.svg", following),
        ):
            button = QToolButton(self)
            button.setObjectName("photoNavigationButton")
            button.setIcon(QIcon(str(root / "resources" / filename)))
            button.setIconSize(QSize(20, 20))
            button.setFixedSize(24, 32)
            button.setToolTip(label)
            button.setAccessibleName(label)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(handler)
            layout.addWidget(button)
            buttons.append(button)
        self.previous_button, self.next_button = buttons
