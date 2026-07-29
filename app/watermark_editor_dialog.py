"""图片水印编辑器：编辑参数并实时预览裁剪后的成图。"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Optional

from PIL import Image
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QVBoxLayout, QWidget, QInputDialog,
)

from .anchor_selector import AnchorSelector
from .check_box import GuideCheckBox
from .combo_box import StyledComboBox
from .image_processor import crop_box, paste_watermark, pil_to_pixmap
from .models import CropSettings, SizeTemplate, WatermarkSettings
from .slider_value_control import SliderValueControl


class WatermarkEditorDialog(QDialog):
    """所有位置和尺寸参数均以裁剪后图片为坐标基准。"""

    # 预设的保存、删除操作在编辑器内立即同步给主窗口，避免关闭窗口后才出现。
    preset_saved = Signal(str, object)
    preset_deleted = Signal(str)

    def __init__(
        self,
        source: Image.Image,
        template: SizeTemplate,
        crop: CropSettings,
        watermark_path: str,
        watermark: WatermarkSettings,
        watermark_presets: Optional[dict[str, dict[str, Any]]] = None,
        active_preset_name: str = "",
        preview_items: Optional[list[tuple[Image.Image, CropSettings]]] = None,
        preview_index: int = 0,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("水印编辑器")
        self.resize(1120, 720)
        self._preview_items = [(item_source.convert("RGBA"), copy.deepcopy(item_crop)) for item_source, item_crop in (preview_items or [(source, crop)])]
        self._preview_index = max(0, min(preview_index, len(self._preview_items) - 1))
        self._template = template
        self.watermark_path = watermark_path
        self.watermark = copy.deepcopy(watermark)
        self._watermark_presets = watermark_presets or {}
        self.selected_preset_name = active_preset_name
        self.created_presets: dict[str, dict[str, Any]] = {}
        self.deleted_preset_names: set[str] = set()
        self._watermark_thumbnail_path: Optional[str] = None

        root = QHBoxLayout(self)
        preview_column = QVBoxLayout()
        preview_toolbar = QHBoxLayout()
        self.preset_combo = StyledComboBox()
        self.preset_combo.setMinimumWidth(220)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        self.previous_button = QPushButton("◀")
        self.next_button = QPushButton("▶")
        self.previous_button.setFixedSize(32, 28)
        self.next_button.setFixedSize(32, 28)
        self.previous_button.setToolTip("查看上一张图片添加水印后的预览")
        self.next_button.setToolTip("查看下一张图片添加水印后的预览")
        self.previous_button.clicked.connect(lambda: self._move_preview(-1))
        self.next_button.clicked.connect(lambda: self._move_preview(1))
        preview_toolbar.addWidget(self.preset_combo)
        preview_toolbar.addStretch()
        preview_toolbar.addWidget(self.previous_button)
        preview_toolbar.addWidget(self.next_button)
        self.preview_label = QLabel("裁剪后图片预览")
        self.preview_label.setObjectName("watermarkPreviewCanvas")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(620, 580)
        preview_tip = QLabel("预览使用当前裁剪结果；水印的位置、边距和比例均以裁剪后图片计算。")
        preview_tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_column.addLayout(preview_toolbar)
        preview_column.addWidget(self.preview_label, 1)
        preview_column.addWidget(preview_tip)
        root.addLayout(preview_column, 1)

        controls = QWidget()
        controls.setObjectName("watermarkControls")
        controls.setMinimumWidth(330)
        form = QFormLayout(controls)
        self.choose_button = QPushButton("选择 PNG 水印图片")
        self.choose_button.clicked.connect(self.choose_watermark)
        self.file_label = QLabel()
        self.file_label.setWordWrap(True)
        self.watermark_preview_label = QLabel("未选择水印")
        self.watermark_preview_label.setObjectName("watermarkThumbnail")
        self.watermark_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.watermark_preview_label.setMinimumHeight(92)
        self.anchor_selector = AnchorSelector()
        self.anchor_selector.anchor_changed.connect(self._on_controls_changed)
        defaults = WatermarkSettings()
        self.size_control = SliderValueControl(1, 80, self.watermark.size_percent, 1, " %", "修改水印宽度", default_value=defaults.size_percent)
        self.opacity_control = SliderValueControl(0, 100, self.watermark.opacity, 0, "", "修改水印不透明度", default_value=defaults.opacity)
        self.rotation_control = SliderValueControl(-180, 180, self.watermark.rotation, 2, "°", "修改水印旋转角度", default_value=defaults.rotation)
        self.margin_control = SliderValueControl(0, 30, self.watermark.margin_percent, 1, " %", "修改水印边距", default_value=defaults.margin_percent)
        self.x_control = SliderValueControl(-50, 50, self.watermark.offset_x, 1, " %", "修改水平偏移", default_value=defaults.offset_x)
        self.y_control = SliderValueControl(-50, 50, self.watermark.offset_y, 1, " %", "修改垂直偏移", default_value=defaults.offset_y)
        self._value_controls = (self.size_control, self.opacity_control, self.rotation_control, self.margin_control, self.x_control, self.y_control)
        for control in self._value_controls:
            control.value_changed.connect(self._on_controls_changed)
        self.safe_check = GuideCheckBox("显示水印安全区域")
        self.safe_check.setChecked(self.watermark.safe_area)
        self.safe_check.toggled.connect(self._on_controls_changed)
        self.preset_name_edit = QLineEdit()
        self.preset_name_edit.setPlaceholderText("输入预设名称")
        self.save_preset_button = QPushButton("存储预设")
        self.save_preset_button.clicked.connect(self._save_preset)
        preset_save_row = QWidget()
        preset_save_layout = QHBoxLayout(preset_save_row)
        preset_save_layout.setContentsMargins(0, 0, 0, 0)
        preset_save_layout.addWidget(self.preset_name_edit, 1)
        preset_save_layout.addWidget(self.save_preset_button)
        self.anchor_selector.set_anchor(self.watermark.anchor)
        form.addRow(self.choose_button)
        form.addRow("当前文件", self.file_label)
        form.addRow("水印预览", self.watermark_preview_label)
        form.addRow("定位", self.anchor_selector)
        form.addRow("水印宽度（输出宽度%）", self.size_control)
        form.addRow("不透明度", self.opacity_control)
        form.addRow("旋转", self.rotation_control)
        form.addRow("边距（%）", self.margin_control)
        form.addRow("水平偏移（%）", self.x_control)
        form.addRow("垂直偏移（%）", self.y_control)
        form.addRow(self.safe_check)
        form.addRow("存储预设", preset_save_row)
        done = QPushButton("完成")
        done.setObjectName("primaryButton")
        done.clicked.connect(self.accept)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        buttons = QWidget(); button_layout = QHBoxLayout(buttons); button_layout.setContentsMargins(0, 8, 0, 0); button_layout.addWidget(done); button_layout.addWidget(cancel)
        form.addRow(buttons)
        root.addWidget(controls)
        self._rebuild_preset_combo(active_preset_name)
        self._refresh_preview()
        QApplication.instance().installEventFilter(self)

    @property
    def _source(self) -> Image.Image:
        return self._preview_items[self._preview_index][0]

    @property
    def _crop(self) -> CropSettings:
        return self._preview_items[self._preview_index][1]

    def choose_watermark(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择透明 PNG 水印", "", "PNG 图片 (*.png);;所有图片 (*.png *.webp)")
        if path:
            self.watermark_path = path
            self.watermark.enabled = True
            self.selected_preset_name = ""
            self._rebuild_preset_combo()
            self._refresh_preview()

    def _on_controls_changed(self, *_args) -> None:  # type: ignore[no-untyped-def]
        self.watermark.anchor = self.anchor_selector.anchor()
        self.watermark.size_percent = self.size_control.value()
        self.watermark.opacity = round(self.opacity_control.value())
        self.watermark.rotation = self.rotation_control.value()
        self.watermark.margin_percent = self.margin_control.value()
        self.watermark.offset_x = self.x_control.value()
        self.watermark.offset_y = self.y_control.value()
        self.watermark.safe_area = self.safe_check.isChecked()
        self._refresh_preview()

    def _on_preset_selected(self, index: int) -> None:
        action = self.preset_combo.itemData(index)
        if action == "delete":
            self._delete_selected_preset()
            return
        if action == "rename":
            self._rename_selected_preset()
            return
        if not isinstance(action, str) or not action.startswith("preset:"):
            return
        name = action.removeprefix("preset:")
        data = self._watermark_presets.get(name)
        if not data:
            return
        settings_data = data.get("settings", data)
        self.watermark = WatermarkSettings.from_dict(settings_data)
        self.watermark.enabled = True
        self.watermark_path = data.get("watermark_path", self.watermark_path)
        self.selected_preset_name = name
        self._sync_controls_from_watermark()
        self._rebuild_preset_combo(name)
        self._refresh_preview()

    def _rebuild_preset_combo(self, selected_name: str = "") -> None:
        """将预设和当前预设的操作项组织到同一个下拉菜单中。"""
        selected_name = selected_name if selected_name in self._watermark_presets else ""
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem("当前水印", "current")
        for name in sorted(self._watermark_presets):
            self.preset_combo.addItem(name, f"preset:{name}")
        if selected_name:
            self.preset_combo.insertSeparator(self.preset_combo.count())
            self.preset_combo.addItem(f"删除预设“{selected_name}”…", "delete")
            self.preset_combo.addItem(f"重命名预设“{selected_name}”…", "rename")
        index = self.preset_combo.findData(f"preset:{selected_name}") if selected_name else 0
        self.preset_combo.setCurrentIndex(index if index >= 0 else 0)
        self.preset_combo.blockSignals(False)

    def _delete_selected_preset(self) -> None:
        name = self.selected_preset_name
        if not name or name not in self._watermark_presets:
            self._rebuild_preset_combo()
            return
        answer = QMessageBox.question(
            self, "删除水印预设", f"确定删除预设“{name}”吗？此操作不会删除 PNG 水印文件。",
        )
        if answer != QMessageBox.StandardButton.Yes:
            self._rebuild_preset_combo(name)
            return
        self._watermark_presets.pop(name, None)
        self.created_presets.pop(name, None)
        self.deleted_preset_names.add(name)
        self.preset_deleted.emit(name)
        self.selected_preset_name = ""
        self._rebuild_preset_combo()

    def _rename_selected_preset(self) -> None:
        old_name = self.selected_preset_name
        if not old_name or old_name not in self._watermark_presets:
            self._rebuild_preset_combo()
            return
        new_name, accepted = QInputDialog.getText(self, "重命名水印预设", "新预设名称", text=old_name)
        new_name = new_name.strip()
        if not accepted or not new_name:
            self._rebuild_preset_combo(old_name)
            return
        if new_name != old_name and new_name in self._watermark_presets:
            QMessageBox.warning(self, "名称已存在", "已有同名水印预设，请使用其他名称。")
            self._rebuild_preset_combo(old_name)
            return
        if new_name == old_name:
            self._rebuild_preset_combo(old_name)
            return
        payload = self._watermark_presets.pop(old_name)
        self._watermark_presets[new_name] = payload
        self.created_presets.pop(old_name, None)
        self.created_presets[new_name] = payload
        self.deleted_preset_names.add(old_name)
        self.preset_deleted.emit(old_name)
        self.preset_saved.emit(new_name, payload)
        self.selected_preset_name = new_name
        self._rebuild_preset_combo(new_name)

    def _sync_controls_from_watermark(self) -> None:
        self.anchor_selector.set_anchor(self.watermark.anchor)
        self.size_control.setValue(self.watermark.size_percent)
        self.opacity_control.setValue(self.watermark.opacity)
        self.rotation_control.setValue(self.watermark.rotation)
        self.margin_control.setValue(self.watermark.margin_percent)
        self.x_control.setValue(self.watermark.offset_x)
        self.y_control.setValue(self.watermark.offset_y)
        self.safe_check.setChecked(self.watermark.safe_area)

    def _move_preview(self, direction: int) -> None:
        if len(self._preview_items) <= 1:
            return
        self._preview_index = (self._preview_index + direction) % len(self._preview_items)
        self._refresh_preview()

    def _save_preset(self) -> None:
        """将当前 PNG 路径和全部水印参数保存为可立即选择的预设。"""
        name = self.preset_name_edit.text().strip()
        if not name:
            self.preset_name_edit.setFocus()
            return
        payload = {
            "settings": self.watermark.to_dict(),
            "watermark_path": self.watermark_path,
        }
        self._watermark_presets[name] = payload
        self.deleted_preset_names.discard(name)
        self.created_presets[name] = payload
        self.selected_preset_name = name
        self.preset_saved.emit(name, payload)
        self._rebuild_preset_combo(name)
        self.preset_name_edit.clear()

    def _crop_image(self) -> Image.Image:
        aspect = self._source.width / self._source.height if self._template.id == "original" else self._template.aspect
        box = crop_box(self._source.size, aspect, self._crop)
        return self._source.crop(box).copy()

    def _refresh_preview(self) -> None:
        self.file_label.setText(Path(self.watermark_path).name if self.watermark_path else "未选择水印")
        has_many = len(self._preview_items) > 1
        self.previous_button.setEnabled(has_many)
        self.next_button.setEnabled(has_many)
        self._refresh_watermark_thumbnail()
        image = paste_watermark(self._crop_image(), self.watermark_path, self.watermark)
        pixmap = pil_to_pixmap(image)
        self.preview_label.setPixmap(pixmap.scaled(self.preview_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def _refresh_watermark_thumbnail(self) -> None:
        """独立显示 PNG 水印本身，透明区域以棋盘背景呈现。"""
        if self._watermark_thumbnail_path == self.watermark_path:
            return
        self._watermark_thumbnail_path = self.watermark_path
        if not self.watermark_path or not Path(self.watermark_path).is_file():
            self.watermark_preview_label.setPixmap(pil_to_pixmap(Image.new("RGBA", (1, 1))))
            self.watermark_preview_label.setText("未选择水印")
            return
        try:
            with Image.open(self.watermark_path) as source_mark:
                mark = source_mark.convert("RGBA")
            canvas = Image.new("RGBA", (240, 82), (24, 24, 24, 255))
            # 深灰双色棋盘同时保留透明通道提示，并让白色水印清晰可见。
            square = 10
            for y in range(0, canvas.height, square):
                for x in range(0, canvas.width, square):
                    if (x // square + y // square) % 2:
                        for yy in range(y, min(y + square, canvas.height)):
                            for xx in range(x, min(x + square, canvas.width)):
                                canvas.putpixel((xx, yy), (48, 48, 48, 255))
            mark.thumbnail((220, 66), Image.Resampling.LANCZOS)
            canvas.alpha_composite(mark, ((canvas.width - mark.width) // 2, (canvas.height - mark.height) // 2))
            self.watermark_preview_label.setText("")
            self.watermark_preview_label.setPixmap(pil_to_pixmap(canvas))
        except Exception:
            self.watermark_preview_label.setPixmap(pil_to_pixmap(Image.new("RGBA", (1, 1))))
            self.watermark_preview_label.setText("水印预览加载失败")

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._refresh_preview()

    def eventFilter(self, watched, event) -> bool:  # type: ignore[no-untyped-def]
        """点击编辑器任意空白/控件前，提交当前数值框并立即刷新预览。"""
        if self.isVisible() and event.type() == QEvent.Type.MouseButtonPress:
            for control in self._value_controls:
                if control.value_label.hasFocus() and watched is not control.value_label:
                    control.value_label.clearFocus()
        return super().eventFilter(watched, event)

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        QApplication.instance().removeEventFilter(self)
        super().closeEvent(event)
