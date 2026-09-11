"""窗口标题栏外观与自定义标题栏控件。"""
from __future__ import annotations

import ctypes
import sys
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget


def enable_dark_title_bar(window: QWidget) -> None:
    """在支持的 Windows 版本上将原生标题栏切换为深色。"""
    if sys.platform != "win32":
        return
    try:
        handle = int(window.winId())
        enabled = ctypes.c_int(1)
        dwmapi = ctypes.windll.dwmapi
        # Windows 10 1903+ 使用 20；部分较旧版本使用 19。
        result = dwmapi.DwmSetWindowAttribute(
            handle,
            20,
            ctypes.byref(enabled),
            ctypes.sizeof(enabled),
        )
        if result != 0:
            dwmapi.DwmSetWindowAttribute(
                handle,
                19,
                ctypes.byref(enabled),
                ctypes.sizeof(enabled),
            )
    except (AttributeError, OSError, TypeError, ValueError):
        # 标题栏着色失败不影响软件主体功能。
        return


class CustomTitleBar(QFrame):
    """与应用主题一致的紧凑标题栏，包含品牌、菜单和窗口按钮。"""

    def __init__(
        self,
        window: QWidget,
        logo_path: Path,
        management_handler: Callable[[], None],
    ) -> None:
        super().__init__(window)
        self._window = window
        self.setObjectName("customTitleBar")
        self.setFixedHeight(40)

        logo = QLabel(self)
        logo.setObjectName("titleBarLogo")
        logo.setFixedSize(22, 22)
        logo.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        pixmap = QPixmap(str(logo_path)).scaled(
            QSize(22, 22),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        logo.setPixmap(pixmap)

        brand = QLabel("ImageFlow", self)
        brand.setObjectName("titleBarBrand")
        brand.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        management = QPushButton("管理后台", self)
        management.setObjectName("titleBarMenuButton")
        management.setCursor(Qt.CursorShape.PointingHandCursor)
        management.setToolTip("清除预览缓存，添加、修改或删除命名用 SKU")
        management.clicked.connect(management_handler)

        self._minimize_button = self._window_button("—", "最小化", "minimize")
        self._maximize_button = self._window_button("□", "最大化", "maximize")
        self._close_button = self._window_button("×", "关闭", "close")
        self._minimize_button.clicked.connect(window.showMinimized)
        self._maximize_button.clicked.connect(self._toggle_maximized)
        self._close_button.clicked.connect(window.close)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(logo)
        layout.addWidget(brand)
        layout.addSpacing(8)
        layout.addWidget(management)
        layout.addStretch(1)
        layout.addWidget(self._minimize_button)
        layout.addWidget(self._maximize_button)
        layout.addWidget(self._close_button)

        window.installEventFilter(self)

    def _window_button(self, text: str, tooltip: str, role: str) -> QPushButton:
        button = QPushButton(text, self)
        button.setObjectName("titleBarWindowButton")
        button.setProperty("windowRole", role)
        button.setToolTip(tooltip)
        button.setFixedSize(46, 40)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return button

    def _toggle_maximized(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()
        self._sync_maximize_button()

    def _sync_maximize_button(self) -> None:
        maximized = self._window.isMaximized()
        self._maximize_button.setText("❐" if maximized else "□")
        self._maximize_button.setToolTip("还原" if maximized else "最大化")

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if watched is self._window and event.type() == QEvent.Type.WindowStateChange:
            self._sync_maximize_button()
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._window.windowHandle()
            if handle is not None:
                handle.startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


def frameless_native_event(window: QWidget, message: object) -> Optional[int]:
    """为无边框主窗口保留 Windows 原生八方向缩放热区。"""
    if sys.platform != "win32" or window.isMaximized() or window.isFullScreen():
        return None
    try:
        from ctypes import wintypes

        msg = wintypes.MSG.from_address(int(message))
        if msg.message != 0x0084:  # WM_NCHITTEST
            return None
        local = window.mapFromGlobal(window.cursor().pos())
        border = 7
        left = local.x() < border
        right = local.x() >= window.width() - border
        top = local.y() < border
        bottom = local.y() >= window.height() - border
        if top and left:
            return 13  # HTTOPLEFT
        if top and right:
            return 14  # HTTOPRIGHT
        if bottom and left:
            return 16  # HTBOTTOMLEFT
        if bottom and right:
            return 17  # HTBOTTOMRIGHT
        if left:
            return 10  # HTLEFT
        if right:
            return 11  # HTRIGHT
        if top:
            return 12  # HTTOP
        if bottom:
            return 15  # HTBOTTOM
    except (AttributeError, TypeError, ValueError):
        return None
    return None
