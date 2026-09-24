"""ImageFlow 入口。Python 3.11 + PySide6 + Pillow。"""
from __future__ import annotations

import copy
import os
import sys
from pathlib import Path
from typing import Optional

from PIL import Image
from PySide6.QtCore import Qt, QPoint, QRect, QSize, QTimer, Signal, QItemSelectionModel
from PySide6.QtGui import QAction, QColor, QFontMetrics, QIcon, QKeySequence, QShortcut, QPainter, QPen, QPixmap, QIntValidator
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QFileDialog, QFormLayout, QFrame,
    QGridLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QProgressDialog, QScrollArea,
    QAbstractScrollArea, QSplitter, QSpinBox, QToolButton, QVBoxLayout, QWidget, QSizePolicy,
    QStyle, QStyleOptionViewItem, QStyledItemDelegate,
)

from app.check_box import GuideCheckBox
from app.combo_box import EditablePopupComboBox, StyledComboBox
from app.crop_canvas import CropCanvas
from app.anchor_selector import AnchorSelector
from app.crop_preview_dialog import CropPreviewDialog, create_crop_icon
from app.management_dialog import ManagementDialog
from app.watermark_editor_dialog import WatermarkEditorDialog
from app.exporter import ExportJob, ExportWorker, build_filename
from app.importer import ImportResult, ImportWorker
from app.image_processor import crop_box, load_thumbnail, output_size, paste_watermark, pil_to_pixmap
from app.models import CropSettings, ExportSettings, PhotoItem, SizeTemplate, WatermarkSettings, builtin_templates
from app.product_catalog import load_product_catalog
from app.window_style import CustomTitleBar, frameless_native_event
from app.slider_value_control import ResettableSlider, SliderValueControl
from app.presets import load_presets, save_presets
from app.project_io import load_project, save_project


IMAGE_FILTER = "图片文件 (*.jpg *.jpeg *.png *.webp *.tif *.tiff *.bmp);;所有文件 (*)"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}


class SequenceArrowButton(QToolButton):
    """与命名下拉框完全一致的实心三角箭头按钮。"""

    def __init__(self, points_up: bool, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._points_up = points_up
        self.setText("")

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center_x = self.width() // 2
        center_y = self.height() // 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#C9CACB"))
        if self._points_up:
            points = [
                QPoint(center_x - 5, center_y + 3),
                QPoint(center_x + 5, center_y + 3),
                QPoint(center_x, center_y - 3),
            ]
        else:
            points = [
                QPoint(center_x - 5, center_y - 3),
                QPoint(center_x + 5, center_y - 3),
                QPoint(center_x, center_y + 3),
            ]
        painter.drawPolygon(points)
        painter.end()


class OptionalSequenceControl(QWidget):
    """可留空的起始序号输入框；序号不会参与当前文件名规则。"""

    CONTROL_STRIP_WIDTH = StyledComboBox.CONTROL_STRIP_WIDTH
    value_changed = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("optionalSequenceControl")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._edit = QLineEdit(self)
        self._edit.setObjectName("sequenceTextEdit")
        self._edit.setValidator(QIntValidator(1, 999999, self))
        self._edit.setPlaceholderText("留空则不添加序号")
        self._edit.setToolTip("可直接删除；留空时文件名不会包含序号。")
        self._edit.textChanged.connect(lambda _text: self.value_changed.emit(self.value()))

        self._up = SequenceArrowButton(True, self)
        self._up.setObjectName("sequenceUpButton")
        self._up.setToolTip("增加起始序号")
        self._up.clicked.connect(lambda: self._step(1))
        self._down = SequenceArrowButton(False, self)
        self._down.setObjectName("sequenceDownButton")
        self._down.setToolTip("减少起始序号")
        self._down.clicked.connect(lambda: self._step(-1))

        buttons = QWidget(self)
        buttons.setObjectName("sequenceButtons")
        buttons.setFixedSize(self.CONTROL_STRIP_WIDTH, 38)
        button_layout = QVBoxLayout(buttons)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(0)
        button_layout.addWidget(self._up)
        button_layout.addWidget(self._down)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._edit, 1)
        layout.addWidget(buttons)
        buttons.setFixedWidth(self.CONTROL_STRIP_WIDTH)

    def value(self) -> Optional[int]:
        text = self._edit.text().strip()
        return int(text) if text else None

    def setValue(self, value: Optional[int]) -> None:
        self._edit.setText("" if value is None else str(max(1, min(999999, int(value)))))

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        outer = self.rect().adjusted(0, 0, -1, -1)
        painter.setBrush(QColor("#292A2B"))
        painter.setPen(QPen(QColor(255, 255, 255, 38), 1))
        painter.drawRoundedRect(outer, 9, 9)
        painter.setPen(QPen(QColor(255, 255, 255, 34), 1))
        separator_x = self.width() - self.CONTROL_STRIP_WIDTH
        painter.drawLine(separator_x, 5, separator_x, self.height() - 6)
        painter.end()

    def _step(self, direction: int) -> None:
        current = self.value()
        value = 1 if current is None else current + direction
        self.setValue(max(1, min(999999, value)))
        self._edit.setFocus()


class TemplateCheckDelegate(QStyledItemDelegate):
    """尺寸列表：用持续的中性灰高亮标记当前编辑项。"""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:  # type: ignore[no-untyped-def]
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 每一行实底重绘，滚动时不会把前一帧的半透明阴影带入下一行。
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        background = QColor("#343434") if selected else QColor("#252525") if hovered else QColor("#1E1E1E")
        painter.fillRect(option.rect, background)
        if selected:
            painter.fillRect(QRect(option.rect.left(), option.rect.top(), 3, option.rect.height()), QColor("#8A8A8A"))
        box = QRect(option.rect.left() + 6, option.rect.center().y() - 8, 16, 16)
        painter.setBrush(QColor("#0B0D0F"))
        painter.setPen(QPen(QColor(255, 255, 255, 38), 1))
        painter.drawRoundedRect(box, 3, 3)
        check_state = index.data(Qt.ItemDataRole.CheckStateRole)
        if check_state == Qt.CheckState.Checked or check_state == 2:
            painter.setPen(QPen(QColor("#F5A623"), 2.1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawLine(box.left() + 4, box.center().y(), box.left() + 7, box.bottom() - 4)
            painter.drawLine(box.left() + 7, box.bottom() - 4, box.right() - 3, box.top() + 4)
        painter.setPen(QColor("#F5F5F5") if selected else QColor("#B9B9B9"))
        painter.drawText(option.rect.adjusted(30, 0, -6, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(index.data(Qt.ItemDataRole.DisplayRole) or ""))
        painter.restore()


class FixedThumbnailList(QListWidget):
    """固定预览缩略图条，滚轮不会改变缩略图的位置。"""

    def wheelEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        event.accept()


class ElidedPathLabel(QLabel):
    """单行只读路径预览；空间不足时保留首尾信息。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._path = ""
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

    def setPath(self, path: str) -> None:
        self._path = path
        self.setToolTip(path)
        self._refresh_text()

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._refresh_text()

    def _refresh_text(self) -> None:
        if not self._path:
            super().setText("尚未选择输出文件夹")
            return
        available_width = max(0, self.contentsRect().width())
        text = QFontMetrics(self.font()).elidedText(self._path, Qt.TextElideMode.ElideMiddle, available_width)
        super().setText(text)


class AccordionHeader(QToolButton):
    """带右侧箭头与短橙色灯条的设置区标题，仅负责视觉与点击状态。"""

    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsAccordionHeader")
        self._title = title
        # 标题由 paintEvent 绘制，确保所有 Accordion 文本严格左对齐。
        self.setText("")
        self.setCheckable(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.isChecked():
            center_y = self.height() / 2
            # 外层半透明笔触模拟小面积橙色辉光，内层是 5×28px 的圆角灯条。
            painter.setPen(QPen(QColor(245, 166, 35, 46), 13, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(11, round(center_y - 10), 11, round(center_y + 10))
            painter.setPen(QPen(QColor("#F5A623"), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(11, round(center_y - 12), 11, round(center_y + 12))
        painter.setPen(QColor("#F2F2F2") if self.isChecked() else QColor("#B4B6BA"))
        painter.drawText(self.rect().adjusted(28, 0, -50, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._title)
        arrow = "⌄" if self.isChecked() else "›"
        painter.drawText(self.rect().adjusted(0, 0, -16, 0), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, arrow)
        painter.end()


class SettingsAccordion(QWidget):
    """支持多项同时展开的轻量设置折叠容器。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsAccordion")
        self._headers: list[AccordionHeader] = []
        self._pages: list[QWidget] = []
        self._expanded: list[bool] = []
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)

    def addItem(self, page: QWidget, title: str) -> int:
        index = len(self._pages)
        header = AccordionHeader(title, self)
        header.clicked.connect(lambda _checked=False, item_index=index: self._toggle_item(item_index))
        self._headers.append(header)
        self._pages.append(page)
        self._expanded.append(index == 0)
        self._layout.addWidget(header)
        self._layout.addWidget(page)
        header.setChecked(self._expanded[index])
        page.setVisible(self._expanded[index])
        return index

    def count(self) -> int:
        return len(self._pages)

    def widget(self, index: int) -> QWidget:
        return self._pages[index]

    def setCurrentIndex(self, index: int) -> None:
        """兼容旧调用：仅展开指定项，不影响其他已展开的项。"""
        if index != -1 and not 0 <= index < len(self._pages):
            return
        if index == -1:
            for item_index in range(len(self._pages)):
                self.setItemExpanded(item_index, False)
        else:
            self.setItemExpanded(index, True)

    def setItemExpanded(self, index: int, expanded: bool) -> None:
        if not 0 <= index < len(self._pages):
            return
        self._expanded[index] = expanded
        self._headers[index].setChecked(expanded)
        self._pages[index].setVisible(expanded)

    def isItemExpanded(self, index: int) -> bool:
        return 0 <= index < len(self._expanded) and self._expanded[index]

    def _toggle_item(self, index: int) -> None:
        """每个标题独立切换，不影响其他已展开的设置页。"""
        self.setItemExpanded(index, not self.isItemExpanded(index))

    def currentIndex(self) -> int:
        return next((index for index, expanded in enumerate(self._expanded) if expanded), -1)

    def setItemIcon(self, index: int, icon: QIcon) -> None:
        # 标题统一采用文字与右侧箭头，避免个别图标破坏左对齐节奏。
        del index, icon

    def setItemToolTip(self, index: int, text: str) -> None:
        self._headers[index].setToolTip(text)


class CustomSizeDialog(QDialog):
    """在同一个窗口中编辑自定义尺寸的名称、宽度与高度。"""

    def __init__(
        self,
        title: str,
        name: str = "",
        width: int = 1080,
        height: int = 1080,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("customSizeDialog")
        self.setWindowTitle(title)
        self.setModal(True)
        self.setFixedWidth(390)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(10)

        name_label = QLabel("名称")
        name_label.setObjectName("customSizeFieldLabel")
        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("例如：电商横图")
        self.name_edit.setClearButtonEnabled(True)
        root.addWidget(name_label)
        root.addWidget(self.name_edit)

        size_label = QLabel("尺寸（像素）")
        size_label.setObjectName("customSizeFieldLabel")
        root.addWidget(size_label)

        size_row = QHBoxLayout()
        size_row.setSpacing(10)
        width_column = QVBoxLayout()
        width_column.setSpacing(5)
        width_column.addWidget(QLabel("宽度"))
        self.width_spin = QSpinBox()
        self.width_spin.setObjectName("customSizeSpinBox")
        self.width_spin.setRange(1, 20000)
        self.width_spin.setValue(width)
        width_column.addWidget(self.width_spin)

        multiply = QLabel("×")
        multiply.setObjectName("customSizeMultiply")
        multiply.setAlignment(Qt.AlignmentFlag.AlignCenter)

        height_column = QVBoxLayout()
        height_column.setSpacing(5)
        height_column.addWidget(QLabel("高度"))
        self.height_spin = QSpinBox()
        self.height_spin.setObjectName("customSizeSpinBox")
        self.height_spin.setRange(1, 20000)
        self.height_spin.setValue(height)
        height_column.addWidget(self.height_spin)

        size_row.addLayout(width_column, 1)
        size_row.addWidget(multiply)
        size_row.addLayout(height_column, 1)
        root.addLayout(size_row)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 8, 0, 0)
        buttons.setSpacing(10)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        confirm = QPushButton("确定")
        confirm.setObjectName("primaryCompactButton")
        confirm.setDefault(True)
        confirm.clicked.connect(self._accept_if_valid)
        buttons.addWidget(cancel, 1)
        buttons.addWidget(confirm, 1)
        root.addLayout(buttons)

        self.name_edit.returnPressed.connect(self._accept_if_valid)
        self.name_edit.setFocus()

    def values(self) -> tuple[str, int, int]:
        return self.name_edit.text().strip(), self.width_spin.value(), self.height_spin.value()

    def _accept_if_valid(self) -> None:
        if not self.name_edit.text().strip():
            self.name_edit.setFocus()
            return
        self.accept()


class MainWindow(QMainWindow):
    """单窗口桌面应用。业务状态集中于模型，控件只负责读写模型。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowTitle("ImageFlow")
        self.resize(1580, 920)
        self.setAcceptDrops(True)
        self.photos: list[PhotoItem] = []
        self.templates = builtin_templates()
        self.watermark_path = ""
        self.active_watermark_preset = ""
        self.export_settings = ExportSettings()
        self.current_photo_index = -1
        self.current_template_id = "original"
        self.thumbnail_cache: dict[str, Image.Image] = {}
        self._undo_stack: list[dict[str, object]] = []
        self._restoring_undo = False
        self._syncing = False
        self._syncing_photo_selection = False
        # 拖动裁剪框时只刷新画布；缩略图条在用户停下后再批量重绘，避免水印
        # 合成抢占主线程造成拖动卡顿。
        self._size_preview_refresh_timer = QTimer(self)
        self._size_preview_refresh_timer.setSingleShot(True)
        self._size_preview_refresh_timer.setInterval(180)
        self._size_preview_refresh_timer.timeout.connect(self._refresh_size_previews)
        self.worker: Optional[ExportWorker] = None
        self._exporting_photos: list[PhotoItem] = []
        self.import_worker: Optional[ImportWorker] = None
        self.startup_worker: Optional[ImportWorker] = None
        self.presets = load_presets()
        self.product_catalog = load_product_catalog()
        self.recent_color_by_product: dict[str, str] = {
            product: color
            for product, color in self.presets.get("recent_color_by_product", {}).items()
            if isinstance(product, str) and isinstance(color, str)
        }
        self.export_settings.output_folder = self.presets.get("last_output", "")
        self._build_ui()
        self._restore_last_session()
        self._refresh_template_list()
        self._write_export_controls()
        # 先用占位图构建界面，让窗口立即出现；上次会话的照片随后在后台解码。
        self._refresh_photo_list(cached_only=True)
        self._refresh_size_preview_selector()
        self._sync_crop_controls()
        self._sync_watermark_controls()
        self._update_naming_rule_preview()
        if self.photos:
            self.statusBar().showMessage("正在后台恢复上次任务…")
            QTimer.singleShot(0, self._start_restored_session_loading)
        else:
            self._refresh_all()

    # ---------- 界面搭建 ----------
    def _build_ui(self) -> None:
        self._title_bar = CustomTitleBar(
            self,
            _resource_path("resources/imageflow-logo.png"),
            self.open_management_dialog,
        )
        self.setMenuWidget(self._title_bar)

        toolbar = self.addToolBar("主工具")
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        actions = [
            ("导入照片", self.import_photos), ("保存项目", self.save_project),
            ("打开项目", self.open_project), ("上一张", self.previous_photo), ("下一张", self.next_photo),
        ]
        for text, handler in actions:
            action = QAction(text, self)
            action.triggered.connect(handler)
            toolbar.addAction(action)
        self.undo_action = QAction("撤销", self)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.undo_action.setToolTip("撤销上一步操作（Ctrl+Z）")
        self.undo_action.triggered.connect(self.undo_last_action)
        self.addAction(self.undo_action)
        toolbar.addAction(self.undo_action)
        toolbar_spacer = QWidget()
        toolbar_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(toolbar_spacer)
        self._main_toolbar = toolbar
        self._toolbar_crop_group = QWidget()
        self._toolbar_crop_group.setObjectName("cropToolbarGroup")
        self._toolbar_crop_layout = QHBoxLayout(self._toolbar_crop_group)
        self._toolbar_crop_layout.setContentsMargins(0, 0, 0, 0)
        self._toolbar_crop_layout.setSpacing(6)
        toolbar.addWidget(self._toolbar_crop_group)
        self._toolbar_right_reserve = QWidget()
        self._toolbar_right_reserve.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(self._toolbar_right_reserve)
        self.restore_composition_preview_button = QPushButton("恢复默认构图预览")
        self.restore_composition_preview_button.setObjectName("restoreCompositionPreviewButton")
        self.restore_composition_preview_button.setToolTip("从裁剪后预览返回默认构图编辑；不会改动裁剪参数")
        self.restore_composition_preview_button.clicked.connect(self._restore_default_composition_preview)
        self._toolbar_crop_layout.addWidget(self.restore_composition_preview_button)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("mainSplitter")
        splitter.addWidget(self._build_left_panel())
        self._center_panel = self._build_center_panel()
        splitter.addWidget(self._center_panel)
        splitter.addWidget(self._build_right_panel())
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 5)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([240, 850, 380])
        splitter.widget(0).setMinimumWidth(220)
        splitter.widget(1).setMinimumWidth(420)
        splitter.widget(2).setMinimumWidth(380)
        splitter.splitterMoved.connect(lambda _position, _index: self._align_crop_toolbar_to_canvas())
        self.setCentralWidget(splitter)
        QTimer.singleShot(0, self._align_crop_toolbar_to_canvas)
        self.statusBar().showMessage("就绪：导入修图成片后开始制作交付图。")

    def _align_crop_toolbar_to_canvas(self) -> None:
        """为顶部裁剪工具预留右侧栏空间，使其右缘与画布右缘对齐。"""
        if not hasattr(self, "_center_panel"):
            return
        canvas_right = self._center_panel.mapTo(self, QPoint(self._center_panel.width() - 12, 0)).x()
        toolbar_left = self._main_toolbar.mapTo(self, QPoint(0, 0)).x()
        # QToolBar 末端保留 5px 的平台布局边距，扣除后与画布右缘像素对齐。
        reserve_width = max(0, self._main_toolbar.width() - (canvas_right - toolbar_left) - 5)
        self._toolbar_right_reserve.setFixedWidth(reserve_width)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("leftPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        heading = QLabel("已导入照片")
        heading.setObjectName("panelHeading")
        layout.addWidget(heading)
        self.photo_list = QListWidget()
        self.photo_list.setObjectName("photoList")
        self.photo_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.photo_list.setIconSize(QSize(42, 42))
        self.photo_list.setSpacing(4)
        self.photo_list.currentRowChanged.connect(self._on_photo_changed)
        self.photo_list.itemSelectionChanged.connect(self._on_photo_list_selection_changed)
        self._add_select_all_shortcut(self.photo_list)
        layout.addWidget(self.photo_list)
        row = QHBoxLayout()
        add = QPushButton("导入")
        add.setObjectName("secondaryButton")
        add.clicked.connect(self.import_photos)
        delete = QPushButton("删除选中")
        delete.setObjectName("dangerButton")
        delete.clicked.connect(self.delete_selected_photos)
        row.addWidget(add)
        row.addWidget(delete)
        layout.addLayout(row)
        nav = QHBoxLayout()
        prev = QPushButton("← 上一张")
        prev.setObjectName("secondaryButton")
        prev.clicked.connect(self.previous_photo)
        next_ = QPushButton("下一张 →")
        next_.setObjectName("secondaryButton")
        next_.clicked.connect(self.next_photo)
        nav.addWidget(prev)
        nav.addWidget(next_)
        layout.addLayout(nav)
        return panel

    def _build_center_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("centerPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        self.canvas = CropCanvas()
        self.canvas.setObjectName("cropCanvas")
        self.canvas.crop_changed.connect(self._on_canvas_crop_changed)
        self.canvas.watermark_changed.connect(self._on_canvas_watermark_changed)
        self.canvas.restore_requested.connect(self.auto_center)
        self.canvas.result_preview_requested.connect(self._show_crop_result_preview)
        self.canvas.edit_started.connect(self._push_undo_state)
        layout.addWidget(self.canvas, 1)
        controls_frame = QFrame()
        controls_frame.setObjectName("previewToolbar")
        controls = QHBoxLayout(controls_frame)
        controls.setContentsMargins(8, 6, 8, 6)
        controls.setSpacing(6)
        self._crop_edit_controls: list[QWidget] = []
        for title, dx, dy in [("↑", 0, -1), ("↓", 0, 1), ("←", -1, 0), ("→", 1, 0)]:
            button = QPushButton(title)
            button.setObjectName("previewControlButton")
            button.setToolTip("构图微调 1 像素")
            button.clicked.connect(lambda _=False, x=dx, y=dy: self.nudge_crop(x, y))
            controls.addWidget(button)
            self._crop_edit_controls.append(button)
        fit = QPushButton("适合窗口")
        fit.setObjectName("previewControlButton")
        fit.setToolTip("恢复自动适配的裁剪视图")
        fit.clicked.connect(self.auto_center)
        controls.addWidget(fit)
        self._crop_edit_controls.append(fit)
        self.guide_check = GuideCheckBox("显示三分法辅助线")
        self.guide_check.setObjectName("guideCheck")
        self.guide_check.setChecked(True)
        self.guide_check.toggled.connect(self._toggle_guides)
        self.guide_check.pressed.connect(self._push_undo_state)
        controls.addWidget(self.guide_check)
        self._crop_edit_controls.append(self.guide_check)
        controls.addStretch()
        layout.addWidget(controls_frame)
        preview_row = QHBoxLayout()
        preview_row.setContentsMargins(4, 2, 4, 0)
        preview_title = QLabel("尺寸预览")
        preview_title.setObjectName("previewHeading")
        preview_row.addWidget(preview_title)
        self.size_preview_selector = StyledComboBox()
        self.size_preview_selector.setObjectName("previewSelector")
        self.size_preview_selector.setToolTip("选择要在下方查看和编辑的尺寸版本")
        self.size_preview_selector.currentIndexChanged.connect(self._on_size_preview_selected)
        preview_row.addWidget(self.size_preview_selector)
        preview_row.addStretch(1)
        layout.addLayout(preview_row)
        # 紧凑横向缩略图条：展示当前尺寸下所有已导入照片的预览。
        self.size_preview_list = FixedThumbnailList()
        self.size_preview_list.setObjectName("sizePreviewList")
        self.size_preview_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.size_preview_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.size_preview_list.setFlow(QListWidget.Flow.LeftToRight)
        self.size_preview_list.setWrapping(False)
        self.size_preview_list.setIconSize(QSize(66, 50))
        # 卡片宽约 56px；网格宽 70px 留出约一半的原有横向间距。
        self.size_preview_list.setGridSize(QSize(70, 70))
        # 为项目高度、内边距和横向滚动条分别预留空间，避免滚动条压住照片
        # 下缘或选中框；宽度仍跟随中间工作区，而不是缩略图数量。
        self.size_preview_list.setFixedHeight(108)
        self.size_preview_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.size_preview_list.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        self.size_preview_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.size_preview_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.size_preview_list.setToolTip("当前尺寸下的全部照片预览；支持 Ctrl / Shift 多选，并与左侧照片列表同步")
        self.size_preview_list.itemSelectionChanged.connect(self._on_size_preview_selection_changed)
        self.size_preview_list.itemClicked.connect(self._on_size_preview_photo_clicked)
        self._add_select_all_shortcut(self.size_preview_list)
        layout.addWidget(self.size_preview_list)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("rightPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 16)
        panel_layout.setSpacing(12)

        self.right_settings_scroll = QScrollArea()
        self.right_settings_scroll.setObjectName("rightSettingsScroll")
        self.right_settings_scroll.setWidgetResizable(True)
        self.right_settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.right_settings_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.right_settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        root = QWidget()
        root.setObjectName("rightPanelRoot")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        self.toolbox = SettingsAccordion()
        settings_pages = [
            (self._size_page(), "尺寸设置"),
            (self._crop_page(), "裁剪设置"),
            (self._watermark_page(), "水印设置"),
            (self._naming_page(), "命名设置"),
            (self._export_page(), "导出设置"),
        ]
        for page, title in settings_pages:
            self._apply_glass_card_effect(page)
            self.toolbox.addItem(page, title)
        self.toolbox.setItemIcon(1, create_crop_icon())
        self.toolbox.setItemToolTip(1, "裁剪设置；使用下方裁剪图标打开当前裁剪预览")
        # 右侧面板的滚轮优先用于浏览设置内容；展开下拉列表后仍可滚动列表本身。
        for combo in self.toolbox.findChildren(StyledComboBox):
            combo.setProperty("ignoreWheelSelection", True)
        layout.addWidget(self.toolbox)
        layout.addStretch()
        self.right_settings_scroll.setWidget(root)
        panel_layout.addWidget(self.right_settings_scroll, 1)

        export_footer = QWidget()
        export_footer.setObjectName("exportFooter")
        export_footer_layout = QVBoxLayout(export_footer)
        # 与滚动设置区内容使用相同的水平内边距，使底部导出按钮与折叠标题对齐。
        export_footer_layout.setContentsMargins(16, 0, 16, 0)
        export_footer_layout.setSpacing(8)

        self.export_all_button = QPushButton("一键导出全部")
        self.export_all_button.setObjectName("primaryButton")
        self.export_all_button.setProperty("footerButton", True)
        # clicked 会携带 checked 状态；显式无参调用可保证始终导出全部已导入照片。
        self.export_all_button.clicked.connect(lambda: self.start_export())
        export_footer_layout.addWidget(self.export_all_button)
        self.export_selected_button = QPushButton("导出选中照片")
        self.export_selected_button.setObjectName("secondaryExportButton")
        self.export_selected_button.setToolTip("导出左侧列表当前选中的一张或多张照片（支持 Ctrl / Shift 多选）")
        self.export_selected_button.clicked.connect(self.start_export_selected)
        export_footer_layout.addWidget(self.export_selected_button)
        self._update_export_selected_button()
        panel_layout.addWidget(export_footer)
        return panel

    @staticmethod
    def _apply_glass_card_effect(page: QWidget) -> None:
        """保留设置页的圆角玻璃样式，不叠加会割裂版面的黑色阴影。"""
        page.setProperty("glassCard", True)
        page.setGraphicsEffect(None)

    def _size_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("settingsPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)
        self.template_list = QListWidget()
        self.template_list.setObjectName("templateList")
        self.template_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.template_list.setItemDelegate(TemplateCheckDelegate(self.template_list))
        self.template_list.itemChanged.connect(self._on_template_checked)
        self.template_list.currentItemChanged.connect(self._on_template_selected)
        layout.addWidget(self.template_list)
        buttons = QHBoxLayout()
        add = QPushButton("新增自定义")
        add.setObjectName("secondaryButton")
        add.clicked.connect(self.add_custom_template)
        edit = QPushButton("修改")
        edit.setObjectName("secondaryButton")
        edit.clicked.connect(self.edit_custom_template)
        remove = QPushButton("删除")
        remove.setObjectName("dangerButton")
        remove.clicked.connect(self.delete_custom_template)
        for button in (add, edit, remove):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        return page

    def _crop_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("settingsPage")
        form = QFormLayout(page)
        form.setContentsMargins(18, 18, 18, 18)
        form.setVerticalSpacing(14)
        form.setHorizontalSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.crop_preview_button = QToolButton()
        self.crop_preview_button.setObjectName("secondaryToolButton")
        self.crop_preview_button.setIcon(create_crop_icon())
        self.crop_preview_button.setIconSize(QSize(20, 20))
        self.crop_preview_button.setText("打开当前裁剪预览")
        self.crop_preview_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.crop_preview_button.setToolTip("打开当前裁剪预览；在预览窗口双击可查看裁剪后的图片")
        self.crop_preview_button.clicked.connect(self.open_crop_preview)
        form.addRow("裁剪预览", self.crop_preview_button)
        self.zoom_control = SliderValueControl(1, 12, 1, 2, "", "修改缩放比例", default_value=1, reset_on_handle_double_click=True)
        self.zoom_control.value_changed.connect(self._on_zoom_control)
        self.zoom_control.slider.sliderPressed.connect(self._push_undo_state)
        form.addRow("缩放比例", self.zoom_control)
        scale_hint = QLabel("提示：拖动裁剪框四角可等比例缩放；鼠标滚轮也可缩放。")
        scale_hint.setToolTip("按住 Ctrl 拖动裁剪框角点，将以裁剪框中心为锚点等比例缩放。")
        scale_hint.setWordWrap(True)
        scale_hint.setObjectName("helperText")
        form.addRow(scale_hint)
        self.x_slider = ResettableSlider(Qt.Orientation.Horizontal); self.x_slider.setRange(-100, 100); self.x_slider.setToolTip("双击圆点恢复默认位置"); self.x_slider.valueChanged.connect(lambda value: self._on_position_slider("x", value)); self.x_slider.reset_requested.connect(self._push_undo_state); self.x_slider.reset_requested.connect(lambda: self.x_slider.setValue(0)); self.x_slider.sliderPressed.connect(self._push_undo_state)
        self.y_slider = ResettableSlider(Qt.Orientation.Horizontal); self.y_slider.setRange(-100, 100); self.y_slider.setToolTip("双击圆点恢复默认位置"); self.y_slider.valueChanged.connect(lambda value: self._on_position_slider("y", value)); self.y_slider.reset_requested.connect(self._push_undo_state); self.y_slider.reset_requested.connect(lambda: self.y_slider.setValue(0)); self.y_slider.sliderPressed.connect(self._push_undo_state)
        form.addRow("水平位置", self.x_slider)
        form.addRow("垂直位置", self.y_slider)
        quick_title = QLabel("快捷操作")
        quick_title.setObjectName("cropQuickHeading")
        quick = QWidget(); quick_layout = QGridLayout(quick); quick_layout.setContentsMargins(0, 0, 0, 0); quick_layout.setHorizontalSpacing(8); quick_layout.setVerticalSpacing(8); quick_layout.setColumnStretch(0, 1); quick_layout.setColumnStretch(1, 1)
        quick_actions = [
            ("主体偏上", lambda: self.quick_position(-0.5), 0, 0),
            ("主体偏下", lambda: self.quick_position(0.5), 0, 1),
            ("复制构图到其他尺寸", self.copy_crop_to_all, 1, 0),
            ("适合窗口 / 重置视图", self.auto_center, 1, 1),
        ]
        for title, func, row, column in quick_actions:
            button = QPushButton(title); button.setObjectName("secondaryButton"); button.setMinimumWidth(0); button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred); button.clicked.connect(func); quick_layout.addWidget(button, row, column)
        form.addRow(quick_title)
        form.addRow(quick)
        return page

    def _watermark_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("settingsPage")
        form = QFormLayout(page)
        form.setContentsMargins(18, 18, 18, 18)
        form.setVerticalSpacing(14)
        form.setHorizontalSpacing(12)
        self.watermark_enable = GuideCheckBox("启用水印（默认应用到全部输出图片）")
        self.watermark_enable.setObjectName("watermarkEnable")
        self.watermark_enable.toggled.connect(self._on_watermark_enabled)
        self.watermark_enable.pressed.connect(self._push_undo_state)
        self.watermark_combo = StyledComboBox()
        self.watermark_combo.setObjectName("watermarkFileSelector")
        self.watermark_combo.setToolTip("选择已保存水印预设，或点击“选择 PNG 水印…”和“编辑水印…”")
        self.watermark_combo.currentIndexChanged.connect(self._on_watermark_combo_selected)
        hint = QLabel("在下拉列表中选择或编辑水印；编辑器会实时预览裁剪后的图片。")
        hint.setWordWrap(True)
        hint.setObjectName("helperText")
        form.addRow(self.watermark_enable)
        form.addRow("水印文件", self.watermark_combo)
        form.addRow(hint)
        apply_all = QPushButton("应用当前水印设置到所有尺寸")
        apply_all.setObjectName("watermarkApplyButton")
        apply_all.clicked.connect(self.apply_watermark_to_all)
        save = QPushButton("保存水印预设")
        save.setObjectName("watermarkSaveButton")
        save.clicked.connect(self.save_watermark_preset)
        form.addRow(apply_all); form.addRow(save)
        return page

    def _naming_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("settingsPage")
        form = QFormLayout(page)
        form.setContentsMargins(18, 18, 18, 18)
        form.setVerticalSpacing(14)
        form.setHorizontalSpacing(12)
        self.brand_edit = QLineEdit()
        self.product_combo = EditablePopupComboBox()
        self.color_combo = EditablePopupComboBox()
        self.product_combo.setObjectName("namingProductCombo")
        self.color_combo.setObjectName("namingColorCombo")
        self.product_combo.setPlaceholderText("选择产品")
        self.color_combo.setPlaceholderText("选择颜色")
        self.product_combo.addItems(self.product_catalog)
        self.date_edit = QLineEdit()
        self.date_edit.setObjectName("namingDateEdit")
        self.date_edit.setPlaceholderText("可留空，例如 2026-07-28")
        self.naming_preview_label = QLabel()
        self.naming_preview_label.setObjectName("namingPreview")
        self.naming_preview_label.setWordWrap(True)
        self.sequence_spin = OptionalSequenceControl()
        self.replace_original_name_check = GuideCheckBox("是否覆盖原名称")
        self.sequence_spin.value_changed.connect(self._update_naming_rule_preview)
        form.addRow("品牌", self.brand_edit); form.addRow("产品", self.product_combo); form.addRow("颜色", self.color_combo)
        form.addRow("日期", self.date_edit); form.addRow("起始序号", self.sequence_spin)
        form.addRow(self.replace_original_name_check)
        form.addRow("命名预览", self.naming_preview_label)
        save = QPushButton("保存命名预设")
        save.setObjectName("secondaryButton")
        save.clicked.connect(self.save_naming_preset)
        form.addRow(save)
        self.brand_edit.textChanged.connect(self._update_naming_rule_preview)
        self.date_edit.textChanged.connect(self._update_naming_rule_preview)
        self.product_combo.currentTextChanged.connect(self._update_naming_rule_preview)
        self.product_combo.activated.connect(lambda _index: self._on_product_changed(self.product_combo.currentText()))
        self.product_combo.lineEdit().editingFinished.connect(lambda: self._on_product_changed(self.product_combo.currentText()))
        self.color_combo.currentTextChanged.connect(self._on_color_changed)
        self.replace_original_name_check.toggled.connect(self._update_naming_rule_preview)
        self._update_naming_rule_preview()
        return page

    def _on_product_changed(self, product: str) -> None:
        colors = self.product_catalog.get(product.strip(), [])
        preferred_color = self.recent_color_by_product.get(product.strip(), "")
        current_color = self.color_combo.currentText().strip()
        self.color_combo.blockSignals(True)
        self.color_combo.clear()
        self.color_combo.addItems(colors)
        if preferred_color in colors:
            self.color_combo.setCurrentText(preferred_color)
        elif current_color:
            self.color_combo.setEditText(current_color)
        elif colors:
            self.color_combo.setCurrentIndex(0)
        self.color_combo.blockSignals(False)
        self._on_color_changed(self.color_combo.currentText())

    def _on_color_changed(self, color: str) -> None:
        product = self.product_combo.currentText().strip()
        selected_color = color.strip()
        if product and selected_color and self.recent_color_by_product.get(product) != selected_color:
            self.recent_color_by_product[product] = selected_color
            self.presets["recent_color_by_product"] = dict(self.recent_color_by_product)
            save_presets(self.presets)
        self._update_naming_rule_preview()

    def open_management_dialog(self) -> None:
        """打开独立管理页面，维护缓存和命名用产品。"""
        dialog = ManagementDialog(self.product_catalog, self)
        dialog.catalog_changed.connect(self._on_product_catalog_changed)
        dialog.exec()

    def nativeEvent(self, event_type: object, message: object) -> tuple[bool, int]:
        """无边框标题栏下仍使用 Windows 的原生窗口边缘缩放。"""
        hit_test = frameless_native_event(self, message)
        if hit_test is not None:
            return True, hit_test
        return super().nativeEvent(event_type, message)

    def _on_product_catalog_changed(self, catalog: object) -> None:
        """后台保存后立即刷新主界面的产品/颜色下拉框。"""
        if not isinstance(catalog, dict):
            return
        previous_catalog = self.product_catalog
        current_product = self.product_combo.currentText().strip()
        cleaned_catalog = {
            str(product): [str(color) for color in colors]
            for product, colors in catalog.items()
            if isinstance(product, str) and isinstance(colors, list)
        }
        self.product_catalog = cleaned_catalog
        removed_current = current_product in previous_catalog and current_product not in cleaned_catalog
        self.product_combo.blockSignals(True)
        self.product_combo.clear()
        self.product_combo.addItems(cleaned_catalog)
        if current_product and not removed_current:
            self.product_combo.setEditText(current_product)
        else:
            self.product_combo.setCurrentIndex(-1)
            self.product_combo.setEditText("")
        self.product_combo.blockSignals(False)
        if removed_current:
            self.color_combo.blockSignals(True)
            self.color_combo.clear()
            self.color_combo.setCurrentIndex(-1)
            self.color_combo.setEditText("")
            self.color_combo.blockSignals(False)
            self._update_naming_rule_preview()
        else:
            self._on_product_changed(self.product_combo.currentText())
        self.statusBar().showMessage("产品数据已更新。", 3000)

    def _update_naming_rule_preview(self, _value: str = "") -> None:
        prefix = " ".join(part for part in (
            self.brand_edit.text().strip(),
            self.product_combo.currentText().strip(),
            self.color_combo.currentText().strip(),
            self.date_edit.text().strip(),
        ) if part)
        start_sequence = self.sequence_spin.value()
        replace_original_name = self.replace_original_name_check.isChecked()
        if start_sequence is None and not replace_original_name:
            original_name = self.current_photo().filename if self.current_photo_index >= 0 else "原图片名.jpg"
            self.naming_preview_label.setText(f"{prefix} {original_name}".strip())
            return
        start_sequence = start_sequence or 1
        preview_settings = copy.copy(self.export_settings)
        preview_settings.brand = self.brand_edit.text().strip()
        preview_settings.product = self.product_combo.currentText().strip()
        preview_settings.color = self.color_combo.currentText().strip()
        preview_settings.date = self.date_edit.text().strip()
        preview_settings.start_sequence = start_sequence
        preview_settings.replace_original_name = replace_original_name
        filenames = [photo.filename for photo in self.photos[:3]] or ["图片 1.jpg", "图片 2.jpg", "图片 3.jpg"]
        extension = (self.format_combo.currentText() if hasattr(self, "format_combo") else preview_settings.image_format).lower()
        lines = [
            f"{index + 1}. {build_filename(preview_settings, self.current_template(), start_sequence + index, filename)}.{extension}"
            for index, filename in enumerate(filenames)
        ]
        self.naming_preview_label.setText("多图导出顺序：\n" + "\n".join(lines))

    def _export_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("settingsPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        top_grid = QGridLayout()
        top_grid.setHorizontalSpacing(12)
        top_grid.setVerticalSpacing(6)
        top_grid.setColumnStretch(0, 1)
        top_grid.setColumnStretch(1, 1)
        self.output_edit = QLineEdit(self.export_settings.output_folder, page)
        self.output_edit.setVisible(False)
        browse = QPushButton("选择输出文件夹")
        browse.setObjectName("secondaryButton")
        browse.clicked.connect(self.choose_output_folder)
        folder_label = QLabel("输出文件夹")
        folder_label.setObjectName("exportFieldLabel")
        folder_column = QWidget()
        folder_column.setObjectName("exportLayoutGroup")
        folder_layout = QVBoxLayout(folder_column)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.setSpacing(6)
        folder_layout.addWidget(folder_label)
        folder_layout.addWidget(browse)

        # 复用产品下拉框的固定箭头栏，保持下拉箭头和右侧分割线位置一致。
        self.format_combo = StyledComboBox(); self.format_combo.setObjectName("exportFormatCombo"); self.format_combo.addItems(["JPG", "PNG", "WEBP"])
        format_label = QLabel("格式")
        format_label.setObjectName("exportFieldLabel")
        format_column = QWidget()
        format_column.setObjectName("exportLayoutGroup")
        format_layout = QVBoxLayout(format_column)
        format_layout.setContentsMargins(0, 0, 0, 0)
        format_layout.setSpacing(6)
        format_layout.addWidget(format_label)
        format_layout.addWidget(self.format_combo)
        top_grid.addWidget(folder_column, 0, 0)
        top_grid.addWidget(format_column, 0, 1)
        layout.addLayout(top_grid)

        output_path_row = QWidget()
        output_path_row.setObjectName("exportLayoutGroup")
        output_path_layout = QHBoxLayout(output_path_row)
        output_path_layout.setContentsMargins(0, 0, 0, 0)
        output_path_layout.setSpacing(12)
        output_path_caption = QLabel("输出位置")
        output_path_caption.setObjectName("outputPathCaption")
        self.output_path_preview = ElidedPathLabel()
        self.output_path_preview.setObjectName("outputPathPreview")
        output_path_layout.addWidget(output_path_caption)
        output_path_layout.addWidget(self.output_path_preview, 1)
        self.output_edit.textChanged.connect(self.output_path_preview.setPath)
        self.output_path_preview.setPath(self.output_edit.text())
        layout.addWidget(output_path_row)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setVerticalSpacing(14)
        form.setHorizontalSpacing(12)
        self.quality_control = SliderValueControl(1, 100, 100, 0, "", "修改 JPG/WebP 质量", default_value=100)
        self.quality_control.value_changed.connect(self._on_quality_changed)
        self.quality_control.slider.sliderPressed.connect(self._push_undo_state)
        self.preserve_resolution_check = GuideCheckBox("保留原图分辨率（不压缩）")
        self.preserve_resolution_check.setChecked(self.export_settings.preserve_source_resolution)
        self.preserve_resolution_check.setToolTip("按所选比例裁剪，但不缩小像素尺寸；取消勾选后按模板的固定像素尺寸导出。")
        # 与预览区“显示三分法辅助线”复用同一勾选控件：选中时在橙色方块上
        # 绘制白色对勾，避免仅显示色块而看不出当前是否已启用。
        self.subfolder_check = GuideCheckBox("按尺寸建立子文件夹"); self.subfolder_check.setChecked(True)
        self.overwrite_check = GuideCheckBox("允许覆盖同名文件")
        self.icc_check = GuideCheckBox("保留 ICC 色彩配置"); self.icc_check.setChecked(True)
        self.exif_check = GuideCheckBox("保留 EXIF 信息")
        form.addRow("JPG/WebP 质量", self.quality_control)
        form.addRow(self.preserve_resolution_check); form.addRow(self.subfolder_check); form.addRow(self.overwrite_check); form.addRow(self.icc_check); form.addRow(self.exif_check)
        layout.addLayout(form)
        return page

    # ---------- 数据和选中状态 ----------
    def current_photo(self) -> Optional[PhotoItem]:
        return self.photos[self.current_photo_index] if 0 <= self.current_photo_index < len(self.photos) else None

    def current_template(self) -> SizeTemplate:
        return next((item for item in self.templates if item.id == self.current_template_id), self.templates[0])

    def _refresh_template_list(self) -> None:
        self._syncing = True
        self.template_list.clear()
        current_item: Optional[QListWidgetItem] = None
        for template in self.templates:
            item = QListWidgetItem(template.display_name)
            item.setData(Qt.ItemDataRole.UserRole, template.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if template.selected else Qt.CheckState.Unchecked)
            self.template_list.addItem(item)
            if template.id == self.current_template_id:
                current_item = item
        if current_item:
            self.template_list.setCurrentItem(current_item)
        self._syncing = False

    def _refresh_photo_list(self, cached_only: bool = False) -> None:
        selected_photo_ids = {
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.photo_list.selectedItems()
            if isinstance(item.data(Qt.ItemDataRole.UserRole), str)
        }
        self._syncing_photo_selection = True
        self.photo_list.blockSignals(True)
        self.photo_list.clear()
        for photo in self.photos:
            state, state_key = self._photo_state(photo)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, photo.id)
            item.setSizeHint(QSize(0, 64))
            try:
                # 左侧图标只能缩放副本，不能破坏中央大预览使用的缓存。
                source = self.thumbnail_cache.get(photo.path) if cached_only else self._thumbnail(photo.path)
                thumb = source.copy() if source is not None else None
                if thumb is not None:
                    thumb.thumbnail((42, 42))
            except Exception:
                thumb = None
            self.photo_list.addItem(item)
            content = QWidget()
            content.setObjectName("photoListItem")
            content_layout = QHBoxLayout(content)
            content_layout.setContentsMargins(8, 6, 8, 6)
            content_layout.setSpacing(10)
            thumbnail = QLabel()
            thumbnail.setObjectName("photoThumbnail")
            thumbnail.setFixedSize(42, 42)
            thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if thumb is not None:
                thumbnail.setPixmap(pil_to_pixmap(thumb))
            text_column = QVBoxLayout()
            text_column.setContentsMargins(0, 0, 0, 0)
            text_column.setSpacing(2)
            filename = QLabel(photo.filename)
            filename.setObjectName("photoFilename")
            filename.setToolTip(photo.filename)
            state_label = QLabel(state)
            state_label.setObjectName("photoState")
            state_label.setProperty("photoState", state_key)
            text_column.addWidget(filename)
            text_column.addWidget(state_label)
            content_layout.addWidget(thumbnail)
            content_layout.addLayout(text_column, 1)
            self.photo_list.setItemWidget(item, content)
        if self.photos:
            self.current_photo_index = min(max(0, self.current_photo_index), len(self.photos) - 1)
            for row, photo in enumerate(self.photos):
                self.photo_list.item(row).setSelected(photo.id in selected_photo_ids)
            if not self.photo_list.selectedItems():
                self.photo_list.item(self.current_photo_index).setSelected(True)
            current_index = self.photo_list.model().index(self.current_photo_index, 0)
            self.photo_list.selectionModel().setCurrentIndex(current_index, QItemSelectionModel.SelectionFlag.NoUpdate)
        else:
            self.current_photo_index = -1
        self.photo_list.blockSignals(False)
        self._syncing_photo_selection = False
        self._on_photo_list_selection_changed()

    @staticmethod
    def _photo_state(photo: PhotoItem) -> tuple[str, str]:
        """仅从既有编辑数据推导列表状态，不写入或改变图片处理逻辑。"""
        if getattr(photo, "exported", False):
            return "已导出", "exported"
        adjusted_crop = any(
            crop.zoom != 1.0 or crop.offset_x != 0.0 or crop.offset_y != 0.0
            for crop in photo.crop_by_template.values()
        )
        adjusted_watermark = any(watermark.enabled for watermark in photo.watermark_by_template.values())
        return ("已调整", "adjusted") if adjusted_crop or adjusted_watermark else ("待处理", "pending")

    def _refresh_photo_statuses(self) -> None:
        """轻量刷新状态文字，避免重建列表造成当前选中项跳动。"""
        for row, photo in enumerate(self.photos):
            content = self.photo_list.itemWidget(self.photo_list.item(row))
            state_label = content.findChild(QLabel, "photoState") if content else None
            if state_label:
                state, state_key = self._photo_state(photo)
                state_label.setText(state)
                state_label.setProperty("photoState", state_key)
                state_label.style().unpolish(state_label)
                state_label.style().polish(state_label)

    def _thumbnail(self, path: str) -> Image.Image:
        if path not in self.thumbnail_cache:
            self.thumbnail_cache[path] = load_thumbnail(path)
        return self.thumbnail_cache[path]

    def _refresh_all(self) -> None:
        self._refresh_canvas()
        self._sync_crop_controls()
        self._sync_watermark_controls()
        self._refresh_size_previews()
        self._update_naming_rule_preview()

    def _refresh_canvas(self) -> None:
        photo = self.current_photo()
        if not photo:
            self.canvas.set_content(Image.new("RGBA", (1, 1)), SizeTemplate("empty", "", 1, 1), CropSettings(), "", WatermarkSettings())
            return
        try:
            template = self.current_template()
            self.canvas.set_content(self._thumbnail(photo.path), template, photo.crop(template.id), self.watermark_path, photo.watermark(template.id))
            self.statusBar().showMessage(f"正在编辑：{photo.filename} · {template.display_name}")
        except Exception as error:
            self._error("无法读取图片", str(error))

    def _refresh_size_previews(self) -> None:
        if self._size_preview_refresh_timer.isActive():
            self._size_preview_refresh_timer.stop()
        scroll_value = self.size_preview_list.horizontalScrollBar().value()
        self._refresh_size_preview_selector()
        selected_rows = {item.row() for item in self.photo_list.selectedIndexes()}
        self._syncing_photo_selection = True
        self.size_preview_list.blockSignals(True)
        self.size_preview_list.clear()
        if not self.photos:
            self.size_preview_list.blockSignals(False)
            self._syncing_photo_selection = False
            return
        try:
            template = self.current_template()
            for index, photo in enumerate(self.photos):
                source = self._thumbnail(photo.path)
                size = output_size(source.size, template)
                aspect = size[0] / size[1]
                preview = source.crop(crop_box(source.size, aspect, photo.crop(template.id))).copy()
                # 缩略图仅用于界面展示，先缩小再叠加水印即可保持最终效果的相对
                # 尺寸和位置，避免在 2K 预览图上反复进行昂贵的水印合成。
                preview.thumbnail((132, 100), Image.Resampling.LANCZOS)
                # 缩略图同样叠加当前尺寸水印，便于识别最终交付效果。
                preview = paste_watermark(preview, self.watermark_path, photo.watermark(template.id))
                preview.thumbnail((66, 50), Image.Resampling.LANCZOS)
                # 为 Selected 模式显式复用原始缩略图，避免 Qt 使用系统蓝色
                # selection tint 生成选中态图标；橙色外框是唯一的选中视觉。
                preview_pixmap = pil_to_pixmap(preview)
                preview_icon = QIcon()
                for mode in (QIcon.Mode.Normal, QIcon.Mode.Active, QIcon.Mode.Selected):
                    preview_icon.addPixmap(preview_pixmap, mode)
                item = QListWidgetItem(preview_icon, "")
                item.setData(Qt.ItemDataRole.UserRole, index)
                item.setToolTip(photo.filename)
                self.size_preview_list.addItem(item)
                if index in selected_rows:
                    item.setSelected(True)
        except Exception:
            self.size_preview_list.clear()
            self.size_preview_list.blockSignals(False)
            self._syncing_photo_selection = False
            return
        if 0 <= self.current_photo_index < self.size_preview_list.count():
            current_index = self.size_preview_list.model().index(self.current_photo_index, 0)
            self.size_preview_list.selectionModel().setCurrentIndex(current_index, QItemSelectionModel.SelectionFlag.NoUpdate)
        self.size_preview_list.blockSignals(False)
        self._syncing_photo_selection = False
        # clear()/重建列表会将滚动条复位；等待 Qt 更新范围后恢复用户原位置。
        QTimer.singleShot(0, lambda value=scroll_value: self._restore_size_preview_scroll(value))

    def _refresh_size_preview_selector(self) -> None:
        """刷新尺寸下拉框，不触发任何图片读取。"""
        self.size_preview_selector.blockSignals(True)
        self.size_preview_selector.clear()
        current_index = 0
        preview_templates = [
            template
            for template in self.templates
            if template.id == "original" or template.selected
        ]
        for index, template in enumerate(preview_templates):
            self.size_preview_selector.addItem(template.display_name, template.id)
            if template.id == self.current_template_id:
                current_index = index
        self.size_preview_selector.setCurrentIndex(current_index)
        self.size_preview_selector.blockSignals(False)

    def _restore_size_preview_scroll(self, value: int) -> None:
        bar = self.size_preview_list.horizontalScrollBar()
        bar.setValue(max(bar.minimum(), min(value, bar.maximum())))

    def _on_photo_changed(self, row: int) -> None:
        if row >= 0:
            self.current_photo_index = row
            photo = self.current_photo()
            if self.startup_worker and photo and photo.path not in self.thumbnail_cache:
                self.statusBar().showMessage(f"正在后台加载：{photo.filename}")
                return
            self._refresh_all()

    def set_current_template(self, template_id: str) -> None:
        if template_id not in [item.id for item in self.templates]:
            return
        self.current_template_id = template_id
        for row in range(self.template_list.count()):
            item = self.template_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == template_id:
                self.template_list.setCurrentItem(item)
                break
        self._refresh_all()

    def _on_size_preview_selected(self, index: int) -> None:
        if self._syncing or index < 0:
            return
        template_id = self.size_preview_selector.itemData(index)
        if template_id:
            self.set_current_template(template_id)

    @staticmethod
    def _add_select_all_shortcut(list_widget: QListWidget) -> None:
        """仅在对应列表拥有焦点时响应 Ctrl+A，避免影响其他输入控件。"""
        shortcut = QShortcut(QKeySequence.StandardKey.SelectAll, list_widget)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(list_widget.selectAll)

    @staticmethod
    def _set_list_selection(list_widget: QListWidget, selected_rows: set[int]) -> None:
        for row in range(list_widget.count()):
            list_widget.item(row).setSelected(row in selected_rows)

    def _on_photo_list_selection_changed(self) -> None:
        """左侧列表是选中状态的权威来源，并同步给底部缩略图。"""
        self._update_export_selected_button()
        if self._syncing_photo_selection:
            return
        selected_rows = {item.row() for item in self.photo_list.selectedIndexes()}
        self._syncing_photo_selection = True
        self.size_preview_list.blockSignals(True)
        self._set_list_selection(self.size_preview_list, selected_rows)
        current_row = self.photo_list.currentRow()
        if 0 <= current_row < self.size_preview_list.count():
            current_index = self.size_preview_list.model().index(current_row, 0)
            self.size_preview_list.selectionModel().setCurrentIndex(current_index, QItemSelectionModel.SelectionFlag.NoUpdate)
        self.size_preview_list.blockSignals(False)
        self._syncing_photo_selection = False

    def _on_size_preview_selection_changed(self) -> None:
        """底部缩略图的 Ctrl / Shift 多选同步到左侧与选中导出。"""
        if self._syncing_photo_selection:
            return
        selected_rows = {item.row() for item in self.size_preview_list.selectedIndexes()}
        self._syncing_photo_selection = True
        self.photo_list.blockSignals(True)
        self._set_list_selection(self.photo_list, selected_rows)
        current_row = self.size_preview_list.currentRow()
        if 0 <= current_row < self.photo_list.count():
            current_index = self.photo_list.model().index(current_row, 0)
            self.photo_list.selectionModel().setCurrentIndex(current_index, QItemSelectionModel.SelectionFlag.NoUpdate)
        self.photo_list.blockSignals(False)
        self._syncing_photo_selection = False
        self._update_export_selected_button()

    def _on_size_preview_photo_clicked(self, item: QListWidgetItem) -> None:
        """点击底部任意照片预览时保持多选，仅切换当前编辑照片。"""
        index = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(index, int) and 0 <= index < len(self.photos):
            self._syncing_photo_selection = True
            current_index = self.photo_list.model().index(index, 0)
            self.photo_list.selectionModel().setCurrentIndex(current_index, QItemSelectionModel.SelectionFlag.NoUpdate)
            self._syncing_photo_selection = False
            self._on_photo_changed(index)

    def _on_template_selected(
        self,
        current: Optional[QListWidgetItem],
        _previous: Optional[QListWidgetItem],
    ) -> None:
        """切换尺寸列表行时持续标记当前编辑的尺寸。"""
        if self._syncing or not current:
            return
        template_id = current.data(Qt.ItemDataRole.UserRole)
        if isinstance(template_id, str) and template_id != self.current_template_id:
            self.current_template_id = template_id
            self._refresh_all()

    def _on_template_checked(self, item: QListWidgetItem) -> None:
        if self._syncing:
            return
        self._push_undo_state()
        template = next(item_ for item_ in self.templates if item_.id == item.data(Qt.ItemDataRole.UserRole))
        template.selected = item.checkState() == Qt.CheckState.Checked
        # 原图比例始终可预览；取消当前尺寸后，立即回到固定可用的原图比例。
        if not template.selected and template.id == self.current_template_id and template.id != "original":
            self.set_current_template("original")
            return
        self._refresh_all()

    # ---------- 撤销与拖放 ----------
    def _capture_undo_state(self) -> dict[str, object]:
        return {
            "photos": copy.deepcopy(self.photos),
            "templates": copy.deepcopy(self.templates),
            "watermark_path": self.watermark_path,
            "active_watermark_preset": self.active_watermark_preset,
            "export_settings": copy.deepcopy(self.export_settings),
            "current_photo_index": self.current_photo_index,
            "current_template_id": self.current_template_id,
        }

    def _push_undo_state(self, *_args) -> None:  # type: ignore[no-untyped-def]
        if self._restoring_undo:
            return
        state = self._capture_undo_state()
        if self._undo_stack and self._undo_stack[-1] == state:
            return
        self._undo_stack.append(state)
        if len(self._undo_stack) > 100:
            self._undo_stack.pop(0)

    def undo_last_action(self) -> None:
        if not self._undo_stack:
            self.statusBar().showMessage("没有可撤销的操作。", 2000)
            return
        state = self._undo_stack.pop()
        self._restoring_undo = True
        try:
            self.photos = state["photos"]  # type: ignore[assignment]
            self.templates = state["templates"]  # type: ignore[assignment]
            self.watermark_path = state["watermark_path"]  # type: ignore[assignment]
            self.active_watermark_preset = state["active_watermark_preset"]  # type: ignore[assignment]
            self.export_settings = state["export_settings"]  # type: ignore[assignment]
            self.current_photo_index = state["current_photo_index"]  # type: ignore[assignment]
            self.current_template_id = state["current_template_id"]  # type: ignore[assignment]
            self.thumbnail_cache.clear()
            self.quality_control.setValue(self.export_settings.jpg_quality)
            self._refresh_template_list()
            self._refresh_photo_list()
            self._refresh_all()
        finally:
            self._restoring_undo = False
        self.statusBar().showMessage("已撤销上一步操作。", 2000)

    # ---------- 自动恢复上次任务 ----------
    def _session_payload(self) -> dict[str, object]:
        """生成可写入预设文件的当前任务快照，不包含可撤销历史。"""
        self._read_export_controls()
        export = self.export_settings.to_dict()
        export["replace_original_name"] = self.export_settings.replace_original_name
        return {
            "version": 1,
            "photos": [photo.to_dict() for photo in self.photos],
            "templates": [template.to_dict() for template in self.templates],
            "watermark_path": self.watermark_path,
            "active_watermark_preset": self.active_watermark_preset,
            "export": export,
            "current_photo_index": self.current_photo_index,
            "current_template_id": self.current_template_id,
        }

    def _save_last_session(self) -> None:
        try:
            self.presets["last_session"] = self._session_payload()
            save_presets(self.presets)
        except (OSError, TypeError, ValueError):
            # 自动保存失败不应阻止用户正常关闭窗口。
            pass

    def _restore_last_session(self) -> None:
        data = self.presets.get("last_session")
        if not isinstance(data, dict):
            return
        try:
            photos = [PhotoItem.from_dict(item) for item in data.get("photos", []) if isinstance(item, dict)]
            self.photos = [photo for photo in photos if Path(photo.path).is_file()]
            templates = [SizeTemplate.from_dict(item) for item in data.get("templates", []) if isinstance(item, dict)]
            if templates:
                self.templates = templates
            watermark_path = data.get("watermark_path", "")
            self.watermark_path = watermark_path if isinstance(watermark_path, str) and Path(watermark_path).is_file() else ""
            self.active_watermark_preset = str(data.get("active_watermark_preset", ""))
            export = data.get("export", {})
            if isinstance(export, dict):
                self.export_settings = ExportSettings.from_dict(export)
            self.current_photo_index = int(data.get("current_photo_index", 0)) if self.photos else -1
            requested_template = data.get("current_template_id", "original")
            available_templates = {template.id for template in self.templates}
            self.current_template_id = requested_template if requested_template in available_templates else self.templates[0].id
            # 会话中的活动预设名称是权威来源。启动时立即套用其定位、尺寸、
            # 透明度等参数，避免界面显示已选预设但实际仍使用旧的照片参数。
            self._restore_active_watermark_preset()
        except (KeyError, TypeError, ValueError):
            return

    def _start_restored_session_loading(self) -> None:
        """在窗口显示后后台解码上次会话图片，当前照片优先。"""
        if not self.photos or self.startup_worker is not None:
            return
        current_path = self.current_photo().path if self.current_photo() else ""
        paths = [photo.path for photo in self.photos]
        if current_path in paths:
            paths.remove(current_path)
            paths.insert(0, current_path)
        self.startup_worker = ImportWorker(paths)
        self.startup_worker.thumbnail_ready.connect(self._on_startup_thumbnail_ready)
        self.startup_worker.progress.connect(self._on_startup_loading_progress)
        self.startup_worker.completed.connect(self._on_startup_loading_completed)
        self.startup_worker.cancelled.connect(self._on_startup_loading_completed)
        self.startup_worker.finished.connect(self._on_startup_worker_finished)
        self.startup_worker.start()

    def _on_startup_thumbnail_ready(self, path: str, thumbnail: Image.Image) -> None:
        """逐张填充缓存和左侧图标；当前照片就绪后立即显示中央画布。"""
        self.thumbnail_cache[path] = thumbnail
        for row, photo in enumerate(self.photos):
            if photo.path != path:
                continue
            content = self.photo_list.itemWidget(self.photo_list.item(row))
            label = content.findChild(QLabel, "photoThumbnail") if content else None
            if label:
                small = thumbnail.copy()
                small.thumbnail((42, 42))
                label.setPixmap(pil_to_pixmap(small))
            break
        current = self.current_photo()
        if current and current.path == path:
            self._refresh_canvas()

    def _on_startup_loading_progress(self, current: int, total: int, path: str) -> None:
        self.statusBar().showMessage(f"正在后台恢复照片 {current}/{total}：{Path(path).name}")

    def _on_startup_loading_completed(self, result: ImportResult) -> None:
        """全部缩略图就绪后再生成底部构图预览。"""
        for path, thumbnail in result.thumbnails:
            self.thumbnail_cache[path] = thumbnail
        self._refresh_all()
        if result.failed_paths:
            self.statusBar().showMessage(f"任务已恢复，{len(result.failed_paths)} 张照片读取失败。", 5000)
        else:
            self.statusBar().showMessage(f"已恢复上次任务：{len(result.thumbnails)} 张照片。", 3000)

    def _on_startup_worker_finished(self) -> None:
        if self.startup_worker:
            self.startup_worker.deleteLater()
        self.startup_worker = None

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.startup_worker and self.startup_worker.isRunning():
            self.startup_worker.cancel()
            self.startup_worker.wait(2000)
        self._save_last_session()
        super().closeEvent(event)

    def dragEnterEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.mimeData().hasUrls() and any(
            url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in IMAGE_SUFFIXES
            for url in event.mimeData().urls()
        ):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in IMAGE_SUFFIXES
        ]
        if paths:
            self._import_photo_paths(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    # ---------- 图片与尺寸 ----------
    def import_photos(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择修图成片", "", IMAGE_FILTER)
        self._import_photo_paths(paths)

    def _import_photo_paths(self, paths: list[str]) -> None:
        existing_paths = {item.path for item in self.photos}
        new_paths: list[str] = []
        for path in paths:
            if path and path not in existing_paths:
                new_paths.append(path)
                existing_paths.add(path)
        if not new_paths:
            if paths:
                self._info("没有导入新图片", "所选图片已在当前任务中。")
            return

        self.import_worker = ImportWorker(new_paths)
        self.import_progress = QProgressDialog("正在准备导入…", "取消导入", 0, len(new_paths), self)
        self.import_progress.setWindowTitle("导入照片")
        self.import_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.import_progress.setMinimumDuration(0)
        self.import_progress.setAutoClose(False)
        self.import_progress.setAutoReset(False)
        self.import_progress.canceled.connect(self.import_worker.cancel)
        self.import_worker.progress.connect(self._on_import_progress)
        self.import_worker.completed.connect(self._on_import_completed)
        self.import_worker.cancelled.connect(self._on_import_cancelled)
        self.import_progress.show()
        self.import_worker.start()

    def _on_import_progress(self, current: int, total: int, path: str) -> None:
        self.import_progress.setMaximum(total)
        self.import_progress.setValue(current)
        self.import_progress.setLabelText(f"正在导入 {current}/{total}：{Path(path).name}")

    def _finish_import(self, result: ImportResult, was_cancelled: bool = False) -> None:
        self.import_progress.close()
        self.import_worker = None
        added = len(result.thumbnails)
        if added:
            self._push_undo_state()
            self.current_photo_index = len(self.photos)
            for path, thumbnail in result.thumbnails:
                self.photos.append(PhotoItem(path))
                self.thumbnail_cache[path] = thumbnail
            self._refresh_photo_list()
            self._refresh_all()
        if result.failed_paths:
            filenames = "、".join(Path(path).name for path in result.failed_paths[:3])
            suffix = "等" if len(result.failed_paths) > 3 else ""
            self._info("部分图片未能导入", f"以下 {len(result.failed_paths)} 张图片无法读取：{filenames}{suffix}")
        if was_cancelled:
            message = f"已导入 {added} 张图片，未开始处理的图片未导入。" if added else "没有图片被导入。"
            self._info("已取消导入", message)
        elif added:
            self.statusBar().showMessage(f"已导入 {added} 张图片。", 3000)

    def _on_import_completed(self, result: ImportResult) -> None:
        self._finish_import(result)

    def _on_import_cancelled(self, result: ImportResult) -> None:
        self._finish_import(result, was_cancelled=True)


    def delete_selected_photos(self) -> None:
        rows = sorted({item.row() for item in self.photo_list.selectedIndexes()}, reverse=True)
        if not rows:
            return
        self._push_undo_state()
        for row in rows:
            removed = self.photos.pop(row)
            self.thumbnail_cache.pop(removed.path, None)
        self._refresh_photo_list(); self._refresh_all()

    def previous_photo(self) -> None:
        if self.photos:
            self.photo_list.setCurrentRow((self.current_photo_index - 1) % len(self.photos))

    def next_photo(self) -> None:
        if self.photos:
            self.photo_list.setCurrentRow((self.current_photo_index + 1) % len(self.photos))

    def add_custom_template(self) -> None:
        dialog = CustomSizeDialog("新增自定义尺寸", parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, width, height = dialog.values()
        template = SizeTemplate(f"custom_{len(self.templates)}_{width}x{height}", f"{name}（{width}×{height}）", width, height, True, False)
        self._push_undo_state()
        self.templates.append(template); self.current_template_id = template.id; self._refresh_template_list(); self._refresh_all()

    def _selected_template_for_edit(self) -> Optional[SizeTemplate]:
        item = self.template_list.currentItem()
        if not item: return None
        return next((template for template in self.templates if template.id == item.data(Qt.ItemDataRole.UserRole)), None)

    def edit_custom_template(self) -> None:
        template = self._selected_template_for_edit()
        if not template: return
        base_name = template.name.split("（")[0]
        dialog = CustomSizeDialog("修改尺寸", base_name, template.width, template.height, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, width, height = dialog.values()
        self._push_undo_state()
        template.width, template.height, template.name = width, height, f"{name}（{width}×{height}）"
        self._refresh_template_list(); self._refresh_all()

    def delete_custom_template(self) -> None:
        template = self._selected_template_for_edit()
        if not template or template.builtin:
            self._info("无法删除", "内置尺寸模板不可删除。")
            return
        self._push_undo_state()
        self.templates.remove(template)
        self.current_template_id = self.templates[0].id
        self._refresh_template_list(); self._refresh_all()

    # ---------- 裁剪交互 ----------
    def _on_canvas_crop_changed(self) -> None:
        self._sync_crop_controls()
        self._refresh_photo_statuses()
        # 底部缩略图需要对每张图片执行裁剪和水印合成；等待拖动停止后只做一次。
        self._size_preview_refresh_timer.start()

    def _sync_crop_controls(self) -> None:
        photo = self.current_photo()
        self._syncing = True
        editing_enabled = photo is not None and not self.canvas.is_result_preview()
        self.restore_composition_preview_button.setEnabled(photo is not None and self.canvas.is_result_preview())
        for widget in (self.zoom_control, self.x_slider, self.y_slider, *self._crop_edit_controls):
            widget.setEnabled(editing_enabled)
        if photo:
            crop = photo.crop(self.current_template_id)
            self.zoom_control.setValue(crop.zoom)
            self.x_slider.setValue(round(crop.offset_x * 100)); self.y_slider.setValue(round(crop.offset_y * 100)); self.guide_check.setChecked(crop.guide_enabled)
        self._syncing = False

    def _show_crop_result_preview(self) -> None:
        """双击画布，在默认构图和裁剪后成图预览之间循环切换。"""
        if not self.current_photo():
            return
        self.canvas.set_result_preview(not self.canvas.is_result_preview())
        self._sync_crop_controls()

    def _restore_default_composition_preview(self) -> None:
        """返回默认构图编辑预览，不改动任何裁剪参数。"""
        self.canvas.set_result_preview(False)
        self._sync_crop_controls()

    def _on_zoom_control(self, value: float) -> None:
        if self._syncing or self.canvas.is_result_preview() or not self.current_photo(): return
        self.canvas.set_zoom_from_center(value)

    def _on_position_slider(self, axis: str, value: int) -> None:
        if self._syncing or self.canvas.is_result_preview() or not self.current_photo(): return
        setattr(self.current_photo().crop(self.current_template_id), f"offset_{axis}", value / 100)
        self._refresh_canvas()
        self._size_preview_refresh_timer.start()

    def _on_quality_changed(self, value: float) -> None:
        if not self._syncing:
            self.export_settings.jpg_quality = round(value)

    def _toggle_guides(self, checked: bool) -> None:
        if not self._syncing and not self.canvas.is_result_preview() and self.current_photo():
            self.current_photo().crop(self.current_template_id).guide_enabled = checked
            self._refresh_canvas()

    def nudge_crop(self, x: int, y: int) -> None:
        if not self.canvas.is_result_preview() and self.current_photo():
            self._push_undo_state()
            self.canvas.nudge_frame(x, y)

    def auto_center(self) -> None:
        if self.canvas.is_result_preview() or not self.current_photo(): return
        self._push_undo_state()
        crop = self.current_photo().crop(self.current_template_id); crop.zoom = 1; crop.offset_x = crop.offset_y = 0
        self._refresh_all()

    def quick_position(self, vertical: float) -> None:
        if not self.canvas.is_result_preview() and self.current_photo(): self._push_undo_state(); self.current_photo().crop(self.current_template_id).offset_y = vertical; self._refresh_all()

    def copy_crop_to_all(self) -> None:
        photo = self.current_photo()
        if not photo: return
        self._push_undo_state()
        source = photo.crop(self.current_template_id)
        for template in self.templates:
            if template.id != self.current_template_id: photo.crop_by_template[template.id] = copy.deepcopy(source)
        self._refresh_all(); self.statusBar().showMessage("已复制当前构图到其他尺寸。", 3000)

    # ---------- 水印 ----------
    def choose_watermark(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择透明 PNG 水印", "", "PNG 图片 (*.png);;所有图片 (*.png *.webp)")
        if path:
            self._push_undo_state()
            self.watermark_path = path
            self.active_watermark_preset = ""
            photo = self.current_photo()
            if photo:
                photo.watermark(self.current_template_id).enabled = True
                self._apply_current_watermark_to_all_outputs()
            self._refresh_all()

    def _sync_watermark_controls(self) -> None:
        photo = self.current_photo()
        self._syncing = True
        self.watermark_enable.setEnabled(photo is not None)
        self.watermark_combo.setEnabled(photo is not None)
        self.watermark_combo.blockSignals(True)
        self.watermark_combo.clear()
        watermark_presets = self.presets.get("watermarks", {})
        active_preset_exists = (
            isinstance(watermark_presets, dict)
            and self.active_watermark_preset in watermark_presets
        )
        # 已选中预设时，文件名只是该预设包含的资源，不应再作为一条水印
        # 重复显示；仅在使用未保存的临时水印时显示当前文件名。
        if not active_preset_exists:
            self.watermark_combo.addItem(
                Path(self.watermark_path).name if self.watermark_path else "未选择水印",
                "current",
            )
        for name in sorted(watermark_presets if isinstance(watermark_presets, dict) else {}):
            self.watermark_combo.addItem(name, f"preset:{name}")
        self.watermark_combo.addItem("选择透明 PNG 水印…", "choose")
        self.watermark_combo.addItem("编辑水印…", "edit")
        active_index = self.watermark_combo.findData(f"preset:{self.active_watermark_preset}")
        self.watermark_combo.setCurrentIndex(active_index if active_index >= 0 else 0)
        self.watermark_combo.blockSignals(False)
        if photo:
            wm = photo.watermark(self.current_template_id)
            self.watermark_enable.setChecked(wm.enabled)
        self._syncing = False

    def _on_watermark_combo_selected(self, index: int) -> None:
        if self._syncing or index < 0:
            return
        action = self.watermark_combo.itemData(index)
        if action == "choose":
            self.choose_watermark()
        elif action == "edit":
            self.open_watermark_editor()
        elif isinstance(action, str) and action.startswith("preset:"):
            name = action.removeprefix("preset:")
            self._apply_watermark_preset(name)
        self._sync_watermark_controls()

    def _apply_watermark_preset(self, name: str) -> None:
        """应用已保存的预设；新版预设同时保存 PNG 路径与水印参数。"""
        photo = self.current_photo()
        data = self.presets.get("watermarks", {}).get(name)
        if not photo or not data:
            return
        self._push_undo_state()
        settings_data = data.get("settings", data)
        photo.watermark_by_template[self.current_template_id] = WatermarkSettings.from_dict(settings_data)
        photo.watermark(self.current_template_id).enabled = True
        if data.get("watermark_path"):
            self.watermark_path = data["watermark_path"]
        self.active_watermark_preset = name
        self._apply_current_watermark_to_all_outputs()
        self._refresh_all()

    def _restore_active_watermark_preset(self) -> None:
        """启动恢复时以活动预设校准水印参数，同时保留任务原有的启用状态。"""
        watermark_presets = self.presets.get("watermarks", {})
        if not isinstance(watermark_presets, dict):
            self.active_watermark_preset = ""
            return
        data = watermark_presets.get(self.active_watermark_preset)
        if not isinstance(data, dict):
            self.active_watermark_preset = ""
            return
        settings_data = data.get("settings", data)
        if not isinstance(settings_data, dict):
            self.active_watermark_preset = ""
            return
        try:
            preset_settings = WatermarkSettings.from_dict(settings_data)
        except TypeError:
            self.active_watermark_preset = ""
            return
        preset_path = data.get("watermark_path")
        if isinstance(preset_path, str) and Path(preset_path).is_file():
            self.watermark_path = preset_path
        for photo in self.photos:
            for template in self.templates:
                enabled = photo.watermark(template.id).enabled
                restored = copy.deepcopy(preset_settings)
                restored.enabled = enabled
                photo.watermark_by_template[template.id] = restored

    def _on_watermark_enabled(self, checked: bool) -> None:
        """将水印开关同步到本任务的全部照片和尺寸。"""
        if self._syncing or not self.current_photo():
            return
        wm = self.current_photo().watermark(self.current_template_id)
        wm.enabled = checked
        if checked:
            self._apply_current_watermark_to_all_outputs()
            self.statusBar().showMessage("水印已默认应用到全部输出图片。", 3000)
        else:
            # 预览和导出均根据各自的 enabled 标记决定是否合成水印。
            for photo in self.photos:
                for template in self.templates:
                    photo.watermark(template.id).enabled = False
            self.statusBar().showMessage("水印已从全部预览和输出图片中关闭。", 3000)
        self._refresh_all()

    def _apply_current_watermark_to_all_outputs(self) -> None:
        """将当前尺寸的水印配置复制到所有照片、所有尺寸的导出参数。"""
        photo = self.current_photo()
        if not photo:
            return
        source = copy.deepcopy(photo.watermark(self.current_template_id))
        for target_photo in self.photos:
            for template in self.templates:
                target_photo.watermark_by_template[template.id] = copy.deepcopy(source)

    def _on_canvas_watermark_changed(self) -> None:
        self._sync_watermark_controls(); self._refresh_size_previews(); self._refresh_photo_statuses()

    def open_watermark_editor(self) -> None:
        """在独立编辑器中调整水印，实时预览始终基于当前裁剪后的图片。"""
        photo = self.current_photo()
        if not photo:
            self._info("没有可编辑的照片", "请先导入并选择一张照片。")
            return
        dialog = WatermarkEditorDialog(
            self._thumbnail(photo.path).copy(),
            self.current_template(),
            photo.crop(self.current_template_id),
            self.watermark_path,
            photo.watermark(self.current_template_id),
            self.presets.get("watermarks", {}),
            self.active_watermark_preset,
            [(self._thumbnail(item.path).copy(), item.crop(self.current_template_id)) for item in self.photos],
            self.current_photo_index,
            self,
        )
        # 编辑器中的“存储 / 删除 / 重命名”预设应立刻出现在主界面的下拉框中。
        dialog.preset_saved.connect(self._on_editor_preset_saved)
        dialog.preset_deleted.connect(self._on_editor_preset_deleted)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._push_undo_state()
            if dialog.created_presets or dialog.deleted_preset_names:
                watermark_presets = self.presets.setdefault("watermarks", {})
                for name in dialog.deleted_preset_names:
                    watermark_presets.pop(name, None)
                watermark_presets.update(dialog.created_presets)
                save_presets(self.presets)
            self.watermark_path = dialog.watermark_path
            self.active_watermark_preset = dialog.selected_preset_name
            photo.watermark_by_template[self.current_template_id] = copy.deepcopy(dialog.watermark)
            if dialog.watermark.enabled:
                self._apply_current_watermark_to_all_outputs()
            self._refresh_all()

    def _on_editor_preset_saved(self, name: str, payload: object) -> None:
        """在编辑器点击“存储预设”后，立刻保存并刷新主窗口的水印列表。"""
        if not isinstance(payload, dict):
            return
        self.presets.setdefault("watermarks", {})[name] = payload
        save_presets(self.presets)
        self._sync_watermark_controls()

    def _on_editor_preset_deleted(self, name: str) -> None:
        """编辑器删除或重命名预设时，同步移除主窗口中的旧项目。"""
        self.presets.setdefault("watermarks", {}).pop(name, None)
        if self.active_watermark_preset == name:
            self.active_watermark_preset = ""
        save_presets(self.presets)
        self._sync_watermark_controls()

    def open_crop_preview(self) -> None:
        """打开当前照片与尺寸的裁剪预览；不会修改任何原图或编辑参数。"""
        photo = self.current_photo()
        if not photo:
            self._info("没有可预览的照片", "请先导入并选择一张照片。")
            return
        try:
            dialog = CropPreviewDialog(
                self._thumbnail(photo.path).copy(),
                self.current_template(),
                copy.deepcopy(photo.crop(self.current_template_id)),
                self.watermark_path,
                copy.deepcopy(photo.watermark(self.current_template_id)),
                self,
            )
            dialog.exec()
        except Exception as error:
            self._error("无法生成裁剪预览", str(error))

    def apply_watermark_to_all(self) -> None:
        photo = self.current_photo()
        if not photo: return
        source = photo.watermark(self.current_template_id)
        for template in self.templates:
            if template.id != self.current_template_id: photo.watermark_by_template[template.id] = copy.deepcopy(source)
        self._refresh_all(); self.statusBar().showMessage("已应用当前水印设置到所有尺寸。", 3000)

    def save_watermark_preset(self) -> None:
        photo = self.current_photo()
        if not photo: return
        name, ok = QInputDialog.getText(self, "保存水印预设", "预设名称")
        if ok and name.strip():
            preset_name = name.strip()
            self.presets.setdefault("watermarks", {})[preset_name] = {
                "settings": photo.watermark(self.current_template_id).to_dict(),
                "watermark_path": self.watermark_path,
            }
            self.active_watermark_preset = preset_name
            save_presets(self.presets); self._sync_watermark_controls(); self.statusBar().showMessage(f"已保存水印预设：{preset_name}", 3000)

    def save_naming_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "保存命名预设", "预设名称")
        if ok and name.strip():
            self._read_export_controls()
            self.presets.setdefault("naming", {})[name.strip()] = self.export_settings.to_dict()
            save_presets(self.presets); self.statusBar().showMessage(f"已保存命名预设：{name.strip()}", 3000)

    # ---------- 导出 ----------
    def choose_output_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择输出文件夹", self.output_edit.text() or str(Path.home()))
        if path: self.output_edit.setText(path)

    def _read_export_controls(self) -> None:
        s = self.export_settings
        s.output_folder = self.output_edit.text().strip(); s.image_format = self.format_combo.currentText(); s.jpg_quality = round(self.quality_control.value())
        s.preserve_source_resolution = self.preserve_resolution_check.isChecked(); s.subfolders = self.subfolder_check.isChecked(); s.overwrite = self.overwrite_check.isChecked(); s.keep_icc = self.icc_check.isChecked(); s.keep_exif = self.exif_check.isChecked()
        s.brand = self.brand_edit.text().strip(); s.product = self.product_combo.currentText().strip(); s.color = self.color_combo.currentText().strip(); s.date = self.date_edit.text().strip(); s.start_sequence = self.sequence_spin.value(); s.replace_original_name = self.replace_original_name_check.isChecked(); s.naming_pattern = "{brand} {product} {color} {date} {sequence} {original}"

    def _write_export_controls(self) -> None:
        s = self.export_settings
        self.output_edit.setText(s.output_folder); self.format_combo.setCurrentText(s.image_format); self.quality_control.setValue(s.jpg_quality); self.preserve_resolution_check.setChecked(s.preserve_source_resolution); self.subfolder_check.setChecked(s.subfolders); self.overwrite_check.setChecked(s.overwrite); self.icc_check.setChecked(s.keep_icc); self.exif_check.setChecked(s.keep_exif)
        self.brand_edit.setText(s.brand); self.date_edit.setText(s.date)
        product_index = self.product_combo.findText(s.product)
        self.product_combo.setCurrentIndex(product_index if product_index >= 0 else -1)
        self._on_product_changed(self.product_combo.currentText())
        color_index = self.color_combo.findText(s.color)
        self.color_combo.setCurrentIndex(color_index if color_index >= 0 else -1)
        self.sequence_spin.setValue(s.start_sequence)
        self.replace_original_name_check.setChecked(s.replace_original_name)
        self._update_naming_rule_preview()

    def _selected_photos_for_export(self) -> list[PhotoItem]:
        """按列表顺序返回当前多选照片，保证序号与导出顺序稳定。"""
        rows = sorted({item.row() for item in self.photo_list.selectedIndexes()})
        return [self.photos[row] for row in rows if 0 <= row < len(self.photos)]

    def _update_export_selected_button(self) -> None:
        if not hasattr(self, "export_selected_button"):
            return
        count = len(self._selected_photos_for_export()) if hasattr(self, "photo_list") else 0
        self.export_selected_button.setEnabled(count > 0)
        self.export_selected_button.setText("导出选中照片" if count == 0 else f"导出选中照片（{count}）")

    def start_export_selected(self) -> None:
        selected_photos = self._selected_photos_for_export()
        if not selected_photos:
            self._info("未选择照片", "请在左侧列表选择一张或多张照片后再导出。")
            return
        self.start_export(selected_photos)

    def start_export(self, photos_to_export: Optional[list[PhotoItem]] = None) -> None:
        photos = self.photos if photos_to_export is None else photos_to_export
        if not photos:
            return self._info("没有可导出的照片", "请先导入一张或多张修图成片。")
        selected = [template for template in self.templates if template.selected]
        if not selected:
            return self._info("未选择尺寸", "请在“尺寸设置”中勾选至少一个尺寸。")
        self._read_export_controls()
        if not self.export_settings.output_folder:
            self.choose_output_folder(); self._read_export_controls()
        if not self.export_settings.output_folder:
            return
        sequence_start = self.export_settings.start_sequence or 1
        if self.export_settings.replace_original_name:
            # 原名称不参与文件名时，每个导出任务都使用不同的连续序号。
            jobs = [
                ExportJob(photo, template, sequence_start + index)
                for index, (photo, template) in enumerate(
                    (photo, template) for photo in photos for template in selected
                )
            ]
        else:
            jobs = [ExportJob(photo, template, sequence_start + photo_index) for photo_index, photo in enumerate(photos) for template in selected]
        preview = "\n".join(build_filename(self.export_settings, job.template, job.sequence, job.photo.filename) + "." + self.export_settings.image_format.lower() for job in jobs[:6])
        if len(jobs) > 6: preview += "\n……"
        answer = QMessageBox.question(self, "确认导出", f"将导出 {len(jobs)} 个文件（共 {len(photos)} 张照片）。\n\n文件名预览：\n{preview}\n\n是否开始？")
        if answer != QMessageBox.StandardButton.Yes: return
        self.presets["last_output"] = self.export_settings.output_folder; save_presets(self.presets)
        self._exporting_photos = list(photos)
        self.worker = ExportWorker(jobs, self.watermark_path, copy.deepcopy(self.export_settings))
        self.progress = QProgressDialog("正在准备导出……", "取消导出", 0, len(jobs), self)
        self.progress.setWindowTitle("批量导出")
        self.progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress.canceled.connect(self.worker.cancel)
        self.worker.progress.connect(self._on_export_progress); self.worker.failed.connect(self._on_export_failed); self.worker.completed.connect(self._on_export_completed); self.worker.cancelled.connect(self._on_export_cancelled)
        self.worker.start()

    def _on_export_progress(self, current: int, total: int, filename: str) -> None:
        self.progress.setMaximum(total); self.progress.setValue(current); self.progress.setLabelText(f"正在导出 {current}/{total}：{filename}")

    def _on_export_failed(self, error: str) -> None:
        self.progress.close(); self._exporting_photos = []; self._error("导出失败", error)

    def _on_export_cancelled(self) -> None:
        self.progress.close(); self._exporting_photos = []; self._info("已取消导出", "已完成的文件会保留，未开始的文件不会导出。")

    def _on_export_completed(self, folder: str) -> None:
        self.progress.close()
        for photo in self._exporting_photos:
            setattr(photo, "exported", True)
        self._exporting_photos = []
        self._refresh_photo_list()
        result = QMessageBox.question(self, "导出完成", f"全部文件已导出至：\n{folder}\n\n是否打开输出文件夹？")
        if result == QMessageBox.StandardButton.Yes: os.startfile(folder)

    # ---------- 项目文件 ----------
    def save_project(self) -> None:
        self._read_export_controls()
        path, _ = QFileDialog.getSaveFileName(self, "保存项目", "", "ImageFlow 项目 (*.imageflowproject)")
        if path:
            try:
                save_project(path, self.photos, self.templates, self.watermark_path, self.export_settings)
                self.statusBar().showMessage(f"项目已保存：{path}", 4000)
            except Exception as error: self._error("保存项目失败", str(error))

    def open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "打开项目", "", "ImageFlow 项目 (*.imageflowproject)")
        if not path: return
        try:
            photos, templates, watermark, settings = load_project(path)
            for photo in photos:
                if not Path(photo.path).is_file():
                    new_path, _ = QFileDialog.getOpenFileName(self, "图片路径失效，请重新定位：" + Path(photo.path).name, "", IMAGE_FILTER)
                    if new_path: photo.path = new_path
            self.photos = [photo for photo in photos if Path(photo.path).is_file()]
            self.templates = templates or builtin_templates(); self.watermark_path = watermark if Path(watermark).is_file() else ""; self.export_settings = settings
            self.thumbnail_cache.clear(); self.current_photo_index = 0 if self.photos else -1
            self.current_template_id = next((template.id for template in self.templates if template.id == "original"), self.templates[0].id)
            self._refresh_template_list(); self._write_export_controls(); self._refresh_photo_list(); self._refresh_all()
            self.statusBar().showMessage("项目已恢复。", 3000)
        except Exception as error: self._error("打开项目失败", str(error))

    # ---------- 提示 ----------
    def _info(self, title: str, message: str) -> None:
        QMessageBox.information(self, title, message)

    def _error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)


def _resource_path(relative_path: str) -> Path:
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_dir / relative_path


def _load_stylesheet() -> str:
    """从源码目录或 PyInstaller 的运行目录加载基础主题与玻璃层级覆盖。"""
    theme_paths = (
        _resource_path("resources/styles/imageflow_dark_orange.qss"),
        _resource_path("resources/styles/imageflow_glass_dark.qss"),
    )
    try:
        return "\n\n".join(path.read_text(encoding="utf-8") for path in theme_paths)
    except OSError:
        # 主题文件缺失时仍可启动，避免影响导入、裁剪和导出等业务流程。
        return ""


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("ImageFlow")
    app.setOrganizationName("ImageFlow")
    app.setWindowIcon(QIcon(str(_resource_path("resources/imageflow-logo.ico"))))
    app.setStyle("Fusion")
    app.setStyleSheet(_load_stylesheet())
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
